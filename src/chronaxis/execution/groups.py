"""把已封存且全部来源EOF的历史归并为完整同刻更新组。

输入只来自已解码磁盘历史，整数纳秒排序不会重读或重排旧文件链。
每来源一个前瞻样本，跨批同刻更新全部收入同一组；不同原序号不collapse。
游标、有限堆和当前组计入共享账本，超大组明确失败，不缓存全量历史。
本组件是离线封存重放，不冒充未完成输入的在线watermark调度或算子执行。
返回组须即时消费，调用方自行长期保留输出的内存不在内部预算保证内。
"""

# 冻结组模型、有限堆与复用既有行估算，不依赖任何数值后端。
from dataclasses import dataclass
import heapq
from sys import getsizeof
from ..timebase.conversion import require_int64_ns
from ..results.codec import _estimate
from ..results.errors import AnalysisError, ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .record_sample import RecordSample
from .history_records import HistorySample, HistoryProgress, estimate_record_bytes


@dataclass(frozen=True)
class DecodedTimeGroup:
    """保存一个session在同一整数ns的全部更新；来源和原sequence仍独立。"""

    time_ns: int  # 完整组的共同纳秒坐标。
    samples: tuple[HistorySample, ...]  # 同组全部原观测，不套用last_by_sequence策略。

    def __post_init__(self) -> None:
        """检查同刻、同会话和唯一原身份，不执行绑定或表达式。

        参数: 无；读取time_ns/samples。返回: None。
        异常: TypeError/ValueError/OverflowError为结构或身份错误。
        """
        require_int64_ns(self.time_ns)
        if type(self.samples) is not tuple or not self.samples or any(type(item) not in (HistorySample,RecordSample) for item in self.samples):
            raise TypeError('完整时间组需要非空HistorySample tuple')
        if any(item.time_ns != self.time_ns for item in self.samples) or len({item.source_ref.session_id for item in self.samples}) != 1:
            raise ValueError('时间组不能混用时间或session')
        # 每别名原来源/sequence定位唯一，同原行不同列仍各自保留。
        identities = {(item.source_ref, item.name, item.sequence) for item in self.samples}
        if len(identities) != len(self.samples):
            raise ValueError('完整时间组重复原观测')


class _TimeGroupIterator:
    """保留有限来源前瞻、当前组预算及活动游标。

    readers为预分配槽位，未安装子游标由_uninstalled_reader单独持有。
    close中断后保留尚未释放的句柄、组登记和预算，_closing期间只允许重试close。
    closed只在真实子资源关闭且组预算抵销后成立，不能凭尝试关闭就解除所有权。
    _held_cost仅含本层_state_cost与_group_cost，不包含子reader或借用history金额。
    """

    def __init__(self, owner, *, sources=None):
        """先申请状态预算，再为已封存历史打开各来源独立游标。

        参数: owner为DecodedHistoryStore；sources为唯一已知来源名tuple，None选择全部。
        返回: 新组迭代器，只有所选来源参与完整同刻组。
        异常: 生命周期/预算/打开或解析原错；持续清理失败从time_group_iterator_cleanup_owner恢复。
        """
        owner._check('sealed')
        # 子集输入先做常量附加空间校验；禁止字符串/列表、未知或重复名偷偷扩充来源。
        # 重复检查不预先建立set，按来源数增长的临时容器必须等预算预约成功后再创建。
        if sources is not None:
            if type(sources) is not tuple or any(type(name) is not str for name in sources):
                raise TypeError('时间组来源子集需要来源名tuple或None')
            for index, name in enumerate(sources):
                if name not in owner.validators:
                    raise ValueError('时间组来源子集包含未知来源')
                if any(sources[previous] == name for previous in range(index)):
                    raise ValueError('时间组来源子集不能重复')
        # 常量空间计算原tuple估算，不在预留前构造按来源数增长的排序列表或tuple。
        selected = owner.validators if sources is None else sources
        count = len(selected)
        tuple_bytes = getsizeof(()) + count * (getsizeof((None,)) - getsizeof(()))
        names_cost = tuple_bytes + sum(_estimate(name) + 32 for name in selected)
        state_cost = 8192 + count * 2048 + names_cost * 16
        # 最小清理字段先建立，按来源数分配的结构、真实申请及打开都在保护区内。
        self.owner, self.closed = owner, False
        self._budget, self._held_cost = owner.budget, 0
        self._closing = False
        self._state_cost = self._group_cost = 0
        self.readers, self.heap, self.last_times = [], [], []
        self._current_group = None
        self._uninstalled_reader = None
        try:
            # 仅围绕本层单笔预约检查实际账本，不从深子失败后的共享总额反推费用。
            _reserve_owned_ram(self, state_cost, '_state_cost')
            # 排序只规范所选来源顺序；未选来源不打开游标，也不并入相同时刻的更新。
            names = tuple(sorted(selected))
            self.readers = [None] * count
            self.last_times = [None] * len(names)
            for index, source in enumerate(names):
                # 保存真实子游标以后才安装；安装前后失败都保有可关闭的句柄。
                self._uninstalled_reader = owner.iter_records(source)
                self.readers[index] = self._uninstalled_reader
                self._uninstalled_reader = None
            for index in range(len(self.readers)):
                self._advance(index)
        except BaseException as exc:
            # 子reader构造或注册失败可能尚未赋值；只接管尚未在本组槽位拥有的实际恢复句柄。
            reader = getattr(exc, 'history_iterator_cleanup_owner', None)
            if (reader is not None and self._uninstalled_reader is None
                    and not any(reader is installed for installed in self.readers)):
                self._uninstalled_reader = reader
            _cleanup_owner(self, exc, 'time_group_iterator_cleanup_owner', '时间组游标构造')
            raise

    def _advance(self, index: int) -> None:
        """略过保留在历史中的批次进度，读取该来源下一个真实更新。

        参数: index为固定来源游标编号。返回: None，必要时heap增加一个前瞻。
        异常: 历史损坏/读取错误传播；真实EOF由游标校验完整计数与摘要。
        """
        for record in self.readers[index]:
            # 所有来源已经EOF并seal，略过进度不会凭单批推断在线组完整。
            if isinstance(record, HistoryProgress):
                continue
            previous = self.last_times[index]
            if previous is not None and record.time_ns < previous:
                raise ResultFormatError('解码历史重放时间回退')
            self.last_times[index] = record.time_ns
            # 一来源最多一个前瞻，index确保不同来源之间无需比较模型对象。
            heapq.heappush(self.heap, (record.time_ns, index, record))
            return

    def __iter__(self) -> '_TimeGroupIterator':
        """返回当前独立组游标。

        参数: 无。返回: self。异常: 无。
        """
        return self

    def __next__(self) -> DecodedTimeGroup:
        """一次提交全部同刻更新，跨批/跨来源不拆成部分上下文。

        参数: 无。返回: 一个DecodedTimeGroup。
        异常: StopIteration为全部历史校验完成；预算/损坏/关闭错误不丢组继续。
        """
        if self.owner.closed:
            raise ResultClosedError('解码历史已关闭')
        if self.closed:
            raise StopIteration
        if self._closing:
            raise ResultClosedError('完整时间组游标正在关闭')
        # 上个组只在请求下一组或关闭时释放；调用方长期持有返回对象须自行预算。
        self._current_group = None
        if self._group_cost:
            # 上个组实际释放后即清槽，返回取消也不能在close时再次扣同一笔借用金额。
            _release_owned_ram(self, self._group_cost, '_group_cost')
        if not self.heap:
            self.close()
            raise StopIteration
        samples = []
        time = self.heap[0][0]
        try:
            while self.heap and self.heap[0][0] == time:
                _, index, record = heapq.heappop(self.heap)
                cost = estimate_record_bytes(record)
                # 每个record的直接预约成功后即登记，即使返回取消也由当前group唯一清理。
                _reserve_owned_ram(self, cost, '_group_cost')
                samples.append(record)
                # 继续同来源直到更晚样本或真正EOF，确保跨批同刻组全部读齐。
                self._advance(index)
            # 排序仅规范同组跨列输出顺序，事件执行时仍原子应用整组而非按此顺序触发。
            samples.sort(key=lambda item: (item.source_ref.source_name, item.sequence, item.name))
            self._current_group = DecodedTimeGroup(time, tuple(samples))
            return self._current_group
        except BaseException as exc:
            _cleanup_owner(self, exc, 'time_group_iterator_cleanup_owner', '时间组重放')
            # 取消和既有AnalysisError原样传播，不用错误空组代替。
            if isinstance(exc, (KeyboardInterrupt, SystemExit, AnalysisError)):
                raise
            error = AnalysisError('完整时间组重放失败')
            # 保持已有AnalysisError包装合同；持续清理的顶层恢复入口在外层和原cause均可达。
            recovery = getattr(exc, 'time_group_iterator_cleanup_owner', None)
            if recovery is not None:
                error.time_group_iterator_cleanup_owner = recovery
                for note in getattr(exc, '__notes__', ()):
                    error.add_note(note)
            raise error from exc

    def close(self) -> None:
        """幂等关闭全部源游标并释放当前组/固定状态，不删除历史文件。

        参数: 无。返回: None，重复关闭安全。
        异常: 首个真实子关闭错误，仍尝试其余游标；预算/取消传播。
            动作前失败保留所有权供重试，实际释放后的取消只完成最小关闭。
        """
        if self.closed:
            # 释放后登记移除中断可能留下已关闭孤儿，重试只修登记而不再扣账。
            self.owner._groups.discard(self)
            return
        self._closing = True
        first_error = None
        try:
            # 安装失败可能只留下局部子游标；即使同时在槽位中，子close也须幂等。
            if self._uninstalled_reader is not None:
                try:
                    self._uninstalled_reader.close()
                except BaseException as exc:
                    first_error = exc
            for reader in self.readers:
                if reader is None:
                    continue
                try:
                    reader.close()
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
        finally:
            # 子资源未真正关闭时保留所有字段和组成本，不能丢句柄或提前解除登记。
            children_closed = all(reader is None or reader.closed for reader in self.readers)
            uninstalled_closed = self._uninstalled_reader is None or self._uninstalled_reader.closed
            if children_closed and uninstalled_closed:
                budget, cost = self.owner.budget, self._state_cost + self._group_cost
                before, released = budget.ram_bytes, False
                try:
                    # 本层两槽合计一次归还；空owner无需调用外部预算，也不扣任何子/借用金额。
                    if cost:
                        budget.release_ram(cost)
                    released = True
                finally:
                    # 已抵销后先清成本/closed，再解除登记；动作前失败则完整保留供重试。
                    if released or budget.ram_bytes == before - cost:
                        self._held_cost -= cost
                        self.closed = True
                        self._state_cost = self._group_cost = 0
                        self.readers.clear()
                        self.heap.clear()
                        self.last_times.clear()
                        self._current_group = self._uninstalled_reader = None
                        self.owner._groups.discard(self)
        if first_error is not None:
            raise first_error
