"""从有序信号历史生成离线线性网格，每个别名只保留相邻两组真实样本。

目标网格origin+k*period贯穿文件和批次，限制在明确半开导出范围。先收齐同刻
更新，按原绑定的last_by_sequence或冲突政策确定候选；缺两侧、无效更新或
间隔过大均产出空值及原因。其他状态信号由原始CSV路径保留，不进入本计算。
所有保留样本及有限网格块计费，失败/取消由上层文件owner接管关闭。
"""

from dataclasses import dataclass
from math import isnan
from ..core.binding import SignalDefinition
from ..core.models import Interval
from ..core.types import SignalDType
from ..core.validation import require_identifier
from ..core.export_interpolation import linear_reference, linear_numpy
from ..timebase.conversion import require_int64_ns
from ..execution.record_sample import RecordSample
from ..execution.history_records import HistorySample, estimate_record_bytes
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .errors import ResultClosedError


@dataclass(frozen=True)
class SignalGridSpec:
    """显式连续信号及统一网格；不从DBC名字、dtype或消息周期推断类别/间隔。"""

    continuous: tuple[str,...]
    period_ns: int | None  # None仅用于尚未解析的DBC声明；运行网格必须已解析。
    origin_ns: int
    max_gap_ns: int

    def __post_init__(self):
        """核静态网格。参数: 无。返回: None。异常: 类型/数量/时间或名称非法。
        """
        if type(self.continuous) is not tuple or not 1 <= len(self.continuous) <= 4096:
            raise ValueError('连续信号需要有限非空tuple')
        for name in self.continuous:
            require_identifier(name,'signal_grid.continuous')
        if len(set(self.continuous))!=len(self.continuous):
            raise ValueError('连续信号重复')
        for key in ('period_ns','origin_ns','max_gap_ns'):
            value=getattr(self,key)
            if key=='period_ns' and value is None:continue
            if type(value) is not int:
                raise TypeError('网格时间需要原生int纳秒')
            require_int64_ns(value,key)
        if self.period_ns is not None and self.period_ns<=0 or self.max_gap_ns<=0:
            raise ValueError('网格周期和最大间隔必须为正')


@dataclass(frozen=True)
class GridRow:
    """一个目标点的估计或缺失；左右引用是实际样本，不能伪造为目标点观测。"""

    time_ns: int
    name: str
    unit: str
    value: int | float | None
    status: str
    reason: str
    quality: int
    left: HistorySample | None
    right: HistorySample | None


def _same_fact(left,right):
    """沿既有同刻事实比较，包括无效NaN。参数: 两HistorySample。返回: bool。异常: 模型属性错误。
    """
    a,b=left.value,right.value
    return (a.valid==b.valid and a.quality==b.quality and type(a.value) is type(b.value)
            and (a.value==b.value or type(a.value) is float and isnan(a.value) and isnan(b.value)))


class SignalGrid:
    """拥有每信号两个有界样本与单调目标游标；push/finish产出必须在下一次push前耗尽。"""

    def __init__(self,spec,definitions,interval,budget,*,backend='numpy',check_cancel=None):
        """核声明并预付有限状态。参数: spec/definitions/interval/budget、backend和取消回调。

        返回: owner。异常: 声明/预算错；持续释放失败附signal_grid_cleanup_owner。
        """
        if type(spec) is not SignalGridSpec or spec.period_ns is None or type(interval) is not Interval or backend not in ('reference','numpy'):
            raise TypeError('线性导出需要明确网格、范围和后端')
        if type(definitions) is not tuple or any(type(d) is not SignalDefinition for d in definitions):
            raise TypeError('线性导出需要原绑定定义tuple')
        # 类型声明必须在读取之前核对，空文件也不能让状态/枚举误入连续插值。
        for name in spec.continuous:
            matches=tuple(d for d in definitions if d.name==name)
            if len(matches)!=1 or matches[0].dtype not in (SignalDType.FLOAT64,SignalDType.INT64,SignalDType.UINT64):
                raise ValueError('连续信号需要唯一数值绑定: '+name)
        self.spec,self.interval,self.backend,self._check_cancel=spec,interval,backend,check_cancel
        self._budget=budget
        self._held_cost=self._fixed_cost=self._sample_cost=0
        self._closed=self._finished=False
        self.states=None
        try:
            _reserve_owned_ram(self,262144+len(spec.continuous)*4096,'_fixed_cost')
            # ceil除法保证负时间、非零origin及跨文件都落在同一网格，不重置到首个样本。
            first=spec.origin_ns+(-((spec.origin_ns-interval.start_ns)//spec.period_ns))*spec.period_ns
            self.states={name:{'definition':next(d for d in definitions if d.name==name),'next':first,
                'left':None,'pending':None,'left_conflict':False,'pending_conflict':False,
                'left_cost':0,'pending_cost':0} for name in spec.continuous}
        except BaseException as error:
            _cleanup_owner(self,error,'signal_grid_cleanup_owner','线性网格构造')
            raise

    def _row(self,state,time_ns,value,status,reason,left,right):
        """构造单个有限结果。参数: state/目标/值/状态/原因/两端。返回: GridRow。异常: 无。
        """
        definition=state['definition']
        quality=(0 if left is None else int(left.value.quality)) | (0 if right is None else int(right.value.quality))
        return GridRow(time_ns,definition.name,definition.unit,value,status,reason,quality,left,right)

    def _until(self,state,limit_ns,right,conflict):
        """输出limit_ns之前的完整有限块。参数: state、独占limit_ns、右端/冲突。返回: GridRow迭代。异常: 数值/取消错误。
        """
        left=state['left']; end=min(limit_ns,self.interval.end_ns)
        if left is None and right is None:
            reason='no_observation'
        elif left is None:
            reason='missing_left'
        elif right is None:
            reason='missing_right'
        elif state['left_conflict'] or conflict:
            reason='same_time_conflict'
        elif not left.value.valid or not right.value.valid:
            reason='invalid_neighbor'
        elif right.time_ns-left.time_ns>self.spec.max_gap_ns:
            reason='gap_too_large'
        else:
            reason=''
        while state['next']<end:
            if self._check_cancel is not None:
                self._check_cancel()
            # 每块最多256个点，内存费用已在构造预付；很长范围不会建立整段网格数组。
            count=min(256,(end-1-state['next'])//self.spec.period_ns+1)
            times=tuple(state['next']+i*self.spec.period_ns for i in range(count))
            if reason:
                values=(None,)*count
            else:
                kernel=linear_reference if self.backend=='reference' else linear_numpy
                values=kernel(times,left.time_ns,right.time_ns,left.value.value,right.value.value)
            for time,value in zip(times,values):
                yield self._row(state,time,None if value is None else float(value),
                                'missing' if reason else 'estimated',reason,left,right)
                state['next']=time+self.spec.period_ns

    def _resolve(self,state):
        """结算已收齐的同刻更新。参数: state。返回: GridRow迭代。异常: 数值/预算/取消错误。
        """
        right=state['pending']
        if right is None:
            return
        conflict=state['pending_conflict']
        yield from self._until(state,right.time_ns,right,conflict)
        # 命中真实点直接使用该点，即使前一端缺失/无效/间隔太大也不阻止真实观测。
        if state['next']==right.time_ns and state['next']<self.interval.end_ns:
            reason='same_time_conflict' if conflict else '' if right.value.valid else 'invalid_update'
            yield self._row(state,right.time_ns,None if reason else right.value.value,
                            'missing' if reason else 'observed',reason,right,right)
            state['next']+=self.spec.period_ns
        _release_owned_ram(self,state['left_cost'],'_sample_cost')
        state.update(left=right,left_cost=state['pending_cost'],left_conflict=conflict,
                     pending=None,pending_cost=0,pending_conflict=False)

    def push(self,sample):
        """处理一个连续信号更新，不跨范围借样本。参数: sample历史记录。返回: 已确定网格行迭代。异常: 声明/顺序/资源错。
        """
        if self._closed or self._finished:
            raise ResultClosedError('网格已关闭或完成')
        if type(sample) not in (HistorySample,RecordSample) or sample.name not in self.states:
            raise TypeError('网格需要所选连续信号历史')
        state=self.states[sample.name]; definition=state['definition']
        if (sample.value.dtype is not definition.dtype or sample.unit!=definition.unit
                or sample.source_ref.source_name!=definition.source or sample.source_ref.field!=definition.field):
            raise ValueError('网格样本与原绑定不一致')
        if not self.interval.start_ns<=sample.time_ns<self.interval.end_ns:
            return
        pending=state['pending']
        if pending is not None and sample.time_ns<pending.time_ns:
            raise ValueError('网格输入同信号时间回退')
        if pending is not None and sample.time_ns==pending.time_ns:
            # 默认冲突产生明确缺值；last_by_sequence只按稳定原序号选定，不按到达次序。
            if sample.sequence==pending.sequence:
                raise ValueError('网格同刻原序号重复')
            conflict=state['pending_conflict'] or not _same_fact(pending,sample) and definition.same_time_policy=='error'
            if sample.sequence<pending.sequence:
                state['pending_conflict']=conflict
                return
            cost=estimate_record_bytes(sample)
            _reserve_owned_ram(self,cost,'_sample_cost')
            old=state['pending_cost']
            state.update(pending=sample,pending_cost=cost,pending_conflict=conflict)
            _release_owned_ram(self,old,'_sample_cost')
        else:
            yield from self._resolve(state)
            cost=estimate_record_bytes(sample)
            _reserve_owned_ram(self,cost,'_sample_cost')
            state.update(pending=sample,pending_cost=cost,pending_conflict=False)

    def finish(self):
        """完整EOF后输出剩余真实点及缺后侧网格。参数: 无。返回: GridRow迭代。异常: 资源/取消错。
        """
        if self._closed or self._finished:
            raise ResultClosedError('网格不可再次完成')
        for state in self.states.values():
            yield from self._resolve(state)
            yield from self._until(state,self.interval.end_ns,None,False)
        self._finished=True

    def close(self):
        """释放保留样本与有限状态，可重试。参数: 无。返回: None。异常: 原预算释放错误。
        """
        if self._closed:
            return
        self.states=None
        _release_owned_ram(self,self._sample_cost,'_sample_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
