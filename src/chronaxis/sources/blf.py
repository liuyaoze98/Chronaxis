"""将既有python-can BLFReader接入有序混合来源；不重新实现BLF格式解析。

只保留当前报文，DBC由混合来源共用一次。账本计入本层对象；第三方解压器内部
分配与原BLF路径一样不代表硬RSS上限。不扫描文件、不补日期、不改原帧字段。
"""
from dataclasses import dataclass
from pathlib import Path

from ..legacy.worker import _frame
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..timebase.conversion import convert_time, checked_add_ns, require_int64_ns
from .raw_can import RawCANRecord, CANTextError


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
                 retain_source_time=False, selected_ids=None, emit_frame_ids=None,
                 channel=None, projection_only=False, time_check_all=False, time_scope='source'):
        """参数为单文件声明、共享账本及按需选择；返回reader；失败附恢复owner。"""
        if type(spec) is not BLFSpec:
            raise TypeError('BLFRead需要BLFSpec')
        self.spec, self._budget, self._check_cancel = spec, budget, check_cancel
        self._retain_source_time = retain_source_time
        self._selected_ids = selected_ids
        self._emit_frame_ids = None if emit_frame_ids is None else frozenset(emit_frame_ids)
        self._channel=channel
        self._projection_only=projection_only and self._emit_frame_ids is not None
        self._time_check_all=time_check_all
        self._time_scope=time_scope
        if time_scope not in ('source','selected','none') or time_scope!='source' and not self._projection_only:
            raise ValueError('按需BLF时间范围必须配合明确的目标帧投影')
        self.first_ns=self.last_ns=self.first_order_ns=self.last_order_ns=None
        if self._projection_only:
            # 复用已有批读取的精确二进制秒转换，避免对无关帧建立完整模型。
            from ..execution.can_batch_reader import _float_seconds_ns
            self._convert_float=_float_seconds_ns
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
                if self._projection_only:
                    selected=message.channel==self._channel and message.arbitration_id in self._emit_frame_ids
                    # 纯消息公式不读取时间；保留原消息供同次DBC解码，不制造零秒或原帧导出能力。
                    if self._time_scope=='none':
                        if not selected:
                            continue
                        return _UntimedBLFRecord(message,self.spec.path,sequence)
                    if self._time_scope=='selected' and not selected:
                        continue
                    raw_ns,quantized=self._convert_float(message.timestamp)
                    mapped=checked_add_ns(raw_ns,self.spec.offset_ns)
                    self.first_ns=mapped if self.first_ns is None else min(self.first_ns,mapped)
                    self.last_ns=mapped if self.last_ns is None else max(self.last_ns,mapped)
                    if self._time_check_all or selected:
                        if self.last_order_ns is not None and mapped<self.last_order_ns:
                            raise CANTextError(self.spec.path,None,f'原记录{sequence}时间回退')
                        if self.first_order_ns is None:
                            self.first_order_ns=mapped
                        self.last_order_ns=mapped
                    if not selected:
                        continue
                if self._selected_ids is not None and message.arbitration_id not in self._selected_ids:
                    continue
                frame = _frame(message)
                if not self._projection_only:
                    timestamp = convert_time(frame.timestamp,'s')
                    raw_ns,quantized=timestamp.time_ns,timestamp.quantized
                    mapped=checked_add_ns(raw_ns,self.spec.offset_ns)
                return RawCANRecord(frame,mapped,self.spec.path,None,sequence,None,'blf-v1',None,
                    quantized,raw_ns if self._retain_source_time else None)
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


@dataclass(frozen=True)
class _UntimedBLFRecord:
    """内部按需消息：保存真实输入身份与载荷，明确没有采集分析时间，禁止原帧导出。

    参数: 本次python-can消息、路径、原序号。返回: 有限内部记录。异常: 工厂以真实解析输入构造。
    生命周期仅覆盖同次解码和有界传输；不作为公开RawCANRecord或时间线样本。
    """
    frame: object
    path: Path
    sequence: int
    time_ns: None = None
    raw_time: None = None
    line_number: None = None
