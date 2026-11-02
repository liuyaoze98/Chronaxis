"""仅在请求报警累计时，按实际有效区间折算所选周期。

状态变化可能发生在两个驱动报文之间，例如温度在中途过期。每对报文只保
实际已知/报警长度，收到右端后按该对完整跨度折算，不保存逐点轨迹。没有
右端的末段不补固定周期；实际模式则累计已经确认存在的连续观测区间。
"""

from ..core.types import Truth as T
from ..core.integral_sum_reference import ReferenceIntegralSum
from ..core.integral_sum_numpy import NumpyIntegralSum
from ..results.errors import ResultClosedError,AnalysisError
from ..results.spool import _reserve_owned_ram,_release_owned_ram,_cleanup_owner


class RecordAlarmDuration:
    """拥有一个待完成记录对和有限求和状态，不读取来源或构造明细。"""

    def __init__(self,budget,step_ns,backend,window):
        """预付统计费用。参数: 共享预算、实际None/正周期、后端。返回: owner。异常: 构造原错附owner。"""
        self._budget,self._step=budget,step_ns
        self._backend=backend
        self._window=window
        self._held_cost=self._fixed_cost=0
        self._last=self._driver=None
        self._state=T.UNKNOWN
        self._pair_known=self._pair_active=0
        self._known=self._observed=0
        self._active_ns=0
        self._sum=None
        self._closed=self._finished=False
        try:
            _reserve_owned_ram(self,65536+(4096*256 if step_ns is not None else 0),'_fixed_cost')
            if step_ns is not None:
                self._sum=(ReferenceIntegralSum if backend=='reference' else NumpyIntegralSum)(4096)
        except BaseException as error:
            _cleanup_owner(self,error,'record_alarm_cleanup_owner','报警时长构造')
            raise

    def consume(self,time_ns,state,driver=False):
        """先结算前态，再记当前态；中途未知只裁剪本对有效部分。

        参数: 实际时间、已确认报警三态、是否真实驱动更新。返回: None。异常: 顺序/数值/关闭错误。
        """
        if self._closed or self._finished:
            raise ResultClosedError('报警累计已结束')
        if self._last is not None:
            if time_ns<self._last:
                raise ValueError('报警累计时间不能回退')
            length=max(0,min(time_ns,self._window.end_ns)-max(self._last,self._window.start_ns))
            known=length if self._state is not T.UNKNOWN else 0
            active=length if self._state is T.TRUE else 0
            if self._step is None:
                self._observed+=length
                self._known+=known
                self._active_ns+=active
            elif self._driver is not None:
                self._pair_known+=known
                self._pair_active+=active
        if self._step is not None and driver:
            if self._driver is not None:
                span=time_ns-self._driver
                overlap=max(0,min(time_ns,self._window.end_ns)-max(self._driver,self._window.start_ns))
                self._observed+=overlap
                self._known+=self._pair_known
                seconds=(self._step*self._pair_active)/(span*1_000_000_000)
                if self._backend=='reference':
                    self._sum.push_values((seconds,),(True,))
                else:
                    import numpy as np
                    values=np.array([seconds],dtype=np.float64)
                    valid=np.array([True],dtype=np.bool_)
                    values.setflags(write=False);valid.setflags(write=False)
                    self._sum.push_values(values,valid)
            self._driver=time_ns
            self._pair_known=self._pair_active=0
        self._last,self._state=time_ns,state

    def driver(self,time_ns):
        """接收原始驱动端点，包括请求域两侧用于比例的点。参数: 实际时间。返回: None。异常: 顺序错误。"""
        if self._step is None or self._driver is not None and self._driver>=self._window.end_ns:
            return
        self.consume(time_ns,self._state,True)

    def finish(self):
        """返回单一秒数及完整性；不结算没有右端的周期。

        参数: 无。返回: (可核实报警秒数或None,状态)。异常: 求和失败/关闭错误。
        """
        if self._closed:
            raise ResultClosedError('报警累计已关闭')
        if self._sum is None:
            active=self._active_ns/1e9
        else:
            result=self._sum.finish('s')
            if result.calculation_failed:
                raise AnalysisError('报警累计数值溢出')
            active=0. if result.value is None else result.value
        status=('no_observation' if not self._observed else 'indeterminate' if not self._known
                else 'partial' if self._known<self._observed else 'complete')
        self._finished=True
        return (active if status in ('complete','partial') else None),status

    @property
    def closed(self):
        """返回关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """丢弃统计状态并归还自己的费用。参数: 无。返回: None。异常: 释放原错可重试。"""
        if self._closed:
            return
        self._sum=None
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
