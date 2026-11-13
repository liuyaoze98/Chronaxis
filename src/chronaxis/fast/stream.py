"""流式读取单文件并产出当前帧贡献，不维护跨帧信号或最终累计。

输入为已编译声明和DBC；输出(time_ns, 原记录序号, 计算项贡献tuple)。
只保存当前帧，文件关闭后才提供最终计数。父会话负责顺序和结果发布。
"""
from pathlib import Path
from time import perf_counter
import can
import cantools

from ..results.budget import _cleanup_owner
from ..legacy.decode_policy import check_decode_length
from ..timebase.conversion import convert_time, checked_add_ns
from .can_io import _prepare, _UNSUPPORTED_FD


class FileContributions:
    """持有一个读取器和有限公式组；同帧仅解码一次，计数按计算项隔离。"""

    def __init__(self, spec, database, cancel=None, budget=None, *, _programs_checked=False):
        """打开单文件。参数: spec编译声明，database已载DBC，cancel可选事件，budget账本。
        返回: 迭代器。异常: 配置、文件或DBC错误；已取得的读取器在后续构造失败时清理。
        ASC/BLF共用各自文件owner；第三方BLF文件头构造失败也保留实际文件关闭责任。
        _programs_checked只供已完成公式准备的内部调用；普通调用仍检查原公式。
        """
        # 在任何配置准备或实际打开前安装最小关闭字段，半构造对象也可恢复。
        self.reader, self._pending_reader = None, None
        self.closed, self.text = False, False
        try:
            self.spec, self.cancel = spec, cancel
            self.groups, self.metrics = _prepare(spec, database, _programs_checked=_programs_checked)
            self.names = tuple(self.metrics)
            self.ids = {name: i for i, name in enumerate(self.names)}
            self.raw_count = 0
            self.targets = [0] * len(self.names)
            self.valid = [0] * len(self.names)
            self.selected = [0] * len(self.names)
            self.kinds = [0] * len(self.names)
            self.compatible = set()
            self.last_time = None
            self.reader = None
            self.finished = False
            self.closed = False
            self.domain = spec.get('domain_ns')
            self.profile = spec.get('_profile', False)
            self.timings = dict(read_seconds=0.0, decode_seconds=0.0, formula_seconds=0.0)
            self.ordered = spec.get('file_merge', 'concatenate') == 'time_order'
            self.channel = spec['channel'] - 1
            self.path = Path(spec['path'])
            self.text = self.path.suffix.lower() == '.asc'
            if self.text:
                from ..sources.asc import ASCRead, ASCSpec
                from ..results.budget import ResourceBudget
                self.reader = ASCRead(ASCSpec(self.path, **spec.get('asc_options', {})),
                    budget if budget is not None else ResourceBudget(),
                    retain_original=False, retain_source_time=False,
                    time_selector=self._selected_time)
            elif self.path.suffix.lower() == '.blf':
                from ..sources.blf import BLFRead, BLFSpec
                from ..results.budget import ResourceBudget
                self.reader = BLFRead(BLFSpec(self.path),
                    budget if budget is not None else ResourceBudget(), frame_only=True)
            else:
                raise ValueError('fast仅支持ASC/BLF')
            self.iterator = iter(self.reader)
            if self.profile:
                self.iterator = self._measured(self.iterator)
        except BaseException as error:
            # 来源构造器提供实际未关闭对象；不从总账余额猜测应退金额。
            self._pending_reader = getattr(error, 'asc_read_cleanup_owner', None)
            if self._pending_reader is None:
                self._pending_reader = getattr(error, 'blf_read_cleanup_owner', None)
            _cleanup_owner(self, error, 'fast_reader_cleanup_owner', 'fast贡献读取器')
            raise

    def _measured(self, iterator):
        """仅诊断运行计量解析迭代。参数: 原读取迭代器。返回: 原记录生成器。异常: 原错误。
        正式执行不使用此包装，避免每条原始报文计时开销。
        """
        while True:
            started = perf_counter()
            try:
                record = next(iterator)
            except StopIteration:
                self.timings['read_seconds'] += perf_counter() - started
                return
            self.timings['read_seconds'] += perf_counter() - started
            yield record

    def _selected_time(self, frame):
        """确定ASC精确时间检查集合。参数: 原帧。返回: bool。异常: 无。
        范围过滤前选择，零贡献和方向不影响集合；无时间消费者不加强检查。
        """
        return ((self.ordered or self.domain is not None) and frame.channel == self.channel
                and not frame.is_error_frame and not frame.is_remote_frame
                and (frame.is_extended_id, frame.is_fd) in self.groups.get(frame.arbitration_id, {}))

    def __iter__(self):
        """返回自身。参数: 无。返回: 当前迭代器。异常: 无。"""
        return self

    def __next__(self):
        """跳过无关帧并返回一条目标贡献。参数: 无。返回: 时间/序号/贡献元组。
        异常: 解析、时间、解码、公式错误或取消；EOF在读取资源成功关闭后抛出。
        """
        if self.finished or self.closed:
            raise StopIteration
        try:
            for record in self.iterator:
                index = self.raw_count
                self.raw_count += 1
                if not (index & 4095) and self.cancel is not None and self.cancel.is_set():
                    raise InterruptedError('读取贡献时取消')
                frame = record.frame if self.text else record
                candidates = self.groups.get(frame.arbitration_id)
                if (candidates is None or frame.channel != self.channel
                        or frame.is_error_frame or frame.is_remote_frame):
                    continue
                kind = frame.is_extended_id, frame.is_fd
                group = candidates.get(kind)
                if group is None:
                    continue
                timestamp = 0
                if self.ordered or self.domain is not None:
                    timestamp = record.time_ns if self.text else checked_add_ns(
                        convert_time(frame.timestamp, 's').time_ns, self.spec.get('offset_ns', 0))
                    if self.ordered and self.last_time is not None and timestamp < self.last_time:
                        raise ValueError('目标报文在文件内部时间回退')
                    self.last_time = timestamp
                if group is not _UNSUPPORTED_FD:
                    for name, _, _ in group.entries:
                        self.targets[self.ids[name]] += 1
                # 不提前break：concatenate的后续记录可能重新落回分析范围。
                if self.domain is not None and not self.domain[0] <= timestamp < self.domain[1]:
                    continue
                if group is _UNSUPPORTED_FD:
                    raise ValueError('实录为FD但DBC只定义经典CAN')
                if not frame.is_fd and frame.dlc > 8:
                    raise ValueError('经典CAN载荷不能超过8字节')
                check_decode_length(frame, group.message.length, 'strict')
                started = perf_counter() if self.profile else 0
                values = group.message.decode(frame.data, decode_choices=False, scaling=True,
                                              allow_truncated=False, allow_excess=False)
                if self.profile:
                    self.timings['decode_seconds'] += perf_counter() - started
                    started = perf_counter()
                if group.message.is_fd and not frame.is_fd:
                    self.compatible.add(frame.arbitration_id)
                entries = []
                for name, metric, observed in group.entries:
                    number = self.ids[name]
                    mask = 1 << (int(kind[0]) * 2 + int(kind[1]))
                    self.kinds[number] |= mask
                    if observed is not None and self.kinds[number].bit_count() > 1:
                        raise ValueError(name + '匹配多种实际帧型')
                    value, keep = metric.contribution(values)
                    self.valid[number] += 1
                    self.selected[number] += int(keep)
                    entries.append((number, value, keep))
                if self.profile:
                    self.timings['formula_seconds'] += perf_counter() - started
                return timestamp, index, tuple(entries)
            self.close()
            self.finished = True
            raise StopIteration
        except (ArithmeticError, ValueError, TypeError, KeyError, cantools.database.DecodeError) as error:
            raise ValueError(f'{self.path.name} 第 {self.raw_count} 条记录：{error}') from error

    def summary(self):
        """取得关闭后的文件事实。参数: 无。返回: 有限dict。异常: 未成功EOF时拒绝。"""
        if not self.finished or not self.closed:
            raise RuntimeError('尚未成功关闭文件')
        return dict(raw=self.raw_count, targets=self.targets, valid=self.valid,
                    selected=self.selected, kinds=self.kinds, compatible=sorted(self.compatible))


    def close(self):
        """关闭本读取器及未返回的实际来源子所有者，失败保留原对象供重试。

        参数: 无。返回: None。异常: 原关闭错误；失败继续保留实际owner供重试。
        """
        if self.closed:
            return
        if self._pending_reader is not None:
            self._pending_reader.close()
            if not self._pending_reader.closed:
                raise RuntimeError('来源构造恢复对象未完成关闭')
            self._pending_reader = None
        if self.reader is not None:
            self.reader.close()
        self.closed = True
