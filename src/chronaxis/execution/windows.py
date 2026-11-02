"""在分配窗口临时数组和片段元数据前申请预算，并拥有可关闭的查询结果。

输入是caller已提供的完整有限Event tuple、WindowSpec和真实观测Interval。
独立参考/NumPy内核仍分别扩展、分组、裁剪和计算覆盖，本层不重写数值算法。
完整冻结输入元数据与N事件临时量在内核前预留，整个workspace由SegmentBatch保有到close。
仅保守约束新查询层；caller预先物化的输入、外部另存引用和整个进程RSS另行说明。
不把独立batch当作可跨批分组的流式输入，不读取旧链/历史、不发布公共AnalysisRunner。
"""

# 仅共享模型、预算和链式生命周期；两种数值执行入口保持独立。
from ..core.models import Interval
from ..core.temporal import Event
from ..core.windows import WindowSpec
from ..core.windows_reference import build_segments_reference
from ..core.windows_numpy import build_segments_numpy
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
from .temporal_buffer import _BatchRegistry


class SegmentBatch:
    """拥有一份完整窗口结果和预留成本，和其他已交付查询相互独立。

父事件ID/状态/完整SourceRef由片段引用，workspace覆盖这些冻结元数据的存活。
链指针放在本对象中，关闭不遗留随历史调用数增长的容器槽位。
"""

    def __init__(self, owner, cost, segments):
        """在已预留成本中构造局部批，不负责登记。

        参数: owner真实查询、cost bytes、segments独立内核生成的tuple。
        返回: 新批。异常: 分配/取消由外层抵销成本，未发布不隐藏失败。
        """
        self._owner, self._cost, self._segments, self._closed = owner, cost, segments, False
        self._registry = self._previous = self._next = None

    @property
    def closed(self):
        """读取关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def segments(self):
        """读取本查询全部片段。参数: 无。返回: Segment tuple。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('窗口片段批已关闭')
        return self._segments

    def _discard(self):
        """脱离登记并丢弃输出，不重复扣账。

        参数: 无。返回: None。异常: 脱链取消传播，finally仍标closed并丢弃元数据。
        """
        try:
            self._owner._results.discard(self)
        finally:
            self._closed, self._cost = True, 0
            self._owner = self._segments = None

    def close(self):
        """释放输出成本，区分扣账前后取消，重复关闭幂等。

        参数: 无。返回: None。异常: 预算/取消传播；已抵销时仍完成最小关闭。
        """
        if self._closed:
            return
        budget, cost = self._owner._budget, self._cost
        before, released = budget.ram_bytes, False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            if released or budget.ram_bytes == before - cost:
                self._discard()


class WindowQueries:
    """为完整有限窗口输入提供预算边界，自有批必须及时close。

此owner无跨批活动/分组状态，每次build都要求该窗口的完整事件集合。
数值或协议失败不改变先前输出，也不把一个查询当作下一查询的部分输入。
"""

    def __init__(self, budget: ResourceBudget, *, backend='numpy'):
        """校验配置并申请固定生命周期开销后选择实际数值入口。

        参数: 共享budget、reference或numpy后端。返回: 新owner。
        异常: 类型/后端/预算/取消传播，申请返回取消也抵销固定成本。
        """
        if not isinstance(budget, ResourceBudget) or backend not in ('reference', 'numpy'):
            raise TypeError('窗口查询需要ResourceBudget与reference/numpy后端')
        self._budget, self._fixed_cost, self._closed = budget, 0, False
        self._results = self._build = None
        fixed, before = 65536, budget.ram_bytes
        try:
            budget.reserve_ram(fixed)
            self._fixed_cost = fixed
            self._results = _BatchRegistry()
            self._build = build_segments_reference if backend == 'reference' else build_segments_numpy
        except BaseException:
            if self._fixed_cost == 0 and budget.ram_bytes == before + fixed:
                self._fixed_cost = fixed
            self.close()
            raise

    @property
    def closed(self):
        """读取关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def _ensure_open(self):
        """拒绝关闭后执行。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('窗口查询已关闭')

    def _construct(self, cost, segments):
        """构造局部结果。参数: 已预留bytes/内核结果tuple。返回: SegmentBatch。异常: 分配/取消。"""
        return SegmentBatch(self, cost, segments)

    def build(self, events: tuple[Event, ...], spec: WindowSpec, observation: Interval) -> SegmentBatch:
        """在预算门槛后执行一个完整窗口集合，保留全部真实父事件。

        参数: 完整有序events、冻结spec及实际观测域observation，不用请求补EOF。
        返回: 须close的SegmentBatch，空事件返回拥有成本的空批。
        异常: typed协议/窗口归属/排序/时间溢出/预算/内核/交付取消均传播。
        失败清理本次预留和局部登记，旧批仍可读；无数值状态变化，可再次合法查询。
        """
        self._ensure_open()
        # 此前只做常数空间类型遍历；详细窗口校验中的集合/数值数组由下方预留覆盖。
        if (type(events) is not tuple or any(not isinstance(event, Event) for event in events)
                or not isinstance(spec, WindowSpec) or not isinstance(observation, Interval)):
            raise TypeError('窗口查询需要完整Event tuple/WindowSpec/真实Interval')
        # N端点/掩码/分组索引为一维数组；参考临时分组、父关联与稳定ID串同样预先计入。
        # 元数据估算读取完整SourceRef子类字段；保留全workspace至close，不宣称精确RSS。
        cost = 65536 + 8192 * len(events) + 16 * _metadata_bytes((events, spec, observation))
        before, reserved, result = self._budget.ram_bytes, False, None
        try:
            self._budget.reserve_ram(cost)
            reserved = True
            segments = self._build(events, spec, observation)
            result = self._construct(cost, segments)
            self._results.add(result)
            return result
        except BaseException:
            try:
                if result is not None:
                    result._discard()
            finally:
                if reserved or self._budget.ram_bytes == before + cost:
                    self._budget.release_ram(cost)
            raise

    def close(self):
        """关闭全部自有结果再抵销固定成本，支持关闭中断后重试。

        参数: 无。返回: None，幂等。异常: 子结果/预算/取消传播，已扣账字段最小清理。
        """
        if self._closed:
            return
        # 结果已扣账但脱链取消时可留下closed孤儿，owner最终清理登记且不再次扣账。
        while self._results:
            result = next(iter(self._results))
            result.close()
            self._results.discard(result)
        cost, before, released = self._fixed_cost, self._budget.ram_bytes, False
        try:
            self._budget.release_ram(cost)
            released = True
        finally:
            if released or self._budget.ram_bytes == before - cost:
                self._closed, self._fixed_cost = True, 0
                self._results = self._build = None
