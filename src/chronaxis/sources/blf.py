"""将既有python-can BLFReader接入有序混合来源；不重新实现BLF格式解析。

只保留当前报文，DBC由混合来源共用一次。账本计入本层对象；第三方解压器内部
分配与原BLF路径一样不代表硬RSS上限。不扫描文件、不补日期、不改原帧字段。
"""
from dataclasses import dataclass
from pathlib import Path

from ..legacy.worker import _frame
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..timebase.conversion import convert_time, checked_add_ns, require_int64_ns
from .raw_can import RawCANRecord


@dataclass(frozen=True)
class BLFSpec:
    """单文件BLF声明；offset_ns仅平移分析坐标，原timestamp不改。"""
    path: Path
    offset_ns: int = 0

    def __post_init__(self):
        """核对静态路径与偏移，不打开输入。失败抛类型或范围错误。"""
        if not isinstance(self.path, Path) or self.path.suffix.lower() != '.blf':
            raise ValueError('BLFSpec需要.blf文件Path')
        require_int64_ns(self.offset_ns)


class BLFRead:
    """持有一个真实BLFReader与当前迭代器，EOF、失败、取消均关闭本次文件。"""

    def __init__(self, spec, budget, *, check_cancel=None, retain_original=False,
                 retain_source_time=False, selected_ids=None):
        """参数为单文件声明、共享账本及按需选择；返回reader；失败附恢复owner。"""
        if type(spec) is not BLFSpec:
            raise TypeError('BLFRead需要BLFSpec')
        self.spec, self._budget, self._check_cancel = spec, budget, check_cancel
        self._retain_source_time = retain_source_time
        self._selected_ids = selected_ids
        self._file = self._reader = self._iterator = None
        self._fixed_cost = self._held_cost = 0
        self._closed = False
        self.count = 0
        try:
            _reserve_owned_ram(self,65536,'_fixed_cost')
            if check_cancel is not None: check_cancel()
            from ..can_dependencies import import_can_dependency
            can = import_can_dependency('can')
            # 文件先安装到owner；BLF头解析失败时也能关闭，不依赖析构回收。
            self._file = spec.path.open('rb')
            self._reader = can.BLFReader(self._file)
            self._iterator = iter(self._reader)
        except BaseException as error:
            _cleanup_owner(self,error,'blf_read_cleanup_owner','混合来源BLF构造')
            raise

    @property
    def closed(self):
        """返回本层所有文件和费用是否已释放。"""
        return self._closed

    def __iter__(self):
        """返回同次迭代器，不重复打开文件。"""
        return self

    def __next__(self):
        """读取下一实际帧，先按ID选择再转换；失败保原异常并清理。"""
        if self._closed: raise StopIteration
        try:
            while True:
                if self._check_cancel is not None: self._check_cancel()
                message = next(self._iterator)
                sequence = self.count
                self.count += 1
                if self._selected_ids is not None and message.arbitration_id not in self._selected_ids:
                    continue
                frame = _frame(message)
                timestamp = convert_time(frame.timestamp,'s')
                return RawCANRecord(frame,checked_add_ns(timestamp.time_ns,self.spec.offset_ns),
                    self.spec.path,None,sequence,None,'blf-v1',None,timestamp.quantized,
                    timestamp.time_ns if self._retain_source_time else None)
        except StopIteration:
            self.close()
            raise
        except BaseException as error:
            _cleanup_owner(self,error,'blf_read_cleanup_owner','混合来源BLF读取')
            raise

    def close(self):
        """关闭本次库迭代器和文件再释放费用；失败保留owner以便重试。"""
        if self._closed: return
        if self._iterator is not None:
            self._iterator.close()
            self._iterator = None
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._fixed_cost: _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed = True
