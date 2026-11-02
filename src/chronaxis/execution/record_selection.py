"""把真实样本更新有界地交给原select核，并直接写最终选择表。

条件独自变化、TTL和裁剪边界不输出行。TRUE与UNKNOWN保持区别；只保存一批及
共享右端，没有完整选择历史或第二套算法。事件范围由必要历史提供相同协议。
"""
from ..core.calculations_reference import select_reference
from ..core.calculations_numpy import select_numpy
from ..results.budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from .record_point_buffer import RecordPointBuffer
from .record_sample_series import sample_series


class RecordSelection(RecordPointBuffer):
    """拥有有限样本缓冲；结果行只在回调期间借用，不累计输出列表。"""
    def __init__(self,budget,spec,input_unit,dtype,step_ns,*,backend='numpy',batch_intervals=64,
                 conditioned=False,consumer=None):
        """预约必要缓冲。参数: 共享预算/选择请求/类型/后端/回调。返回: owner。异常: 配置或预算错。"""
        if spec.operation!='select' or step_ns is not None or backend not in ('reference','numpy') or not callable(consumer):
            raise ValueError('选择需要select、无周期和明确后端及行消费者')
        if type(batch_intervals) is not int or not 1<=batch_intervals<=4096 or type(conditioned) is not bool:
            raise ValueError('选择需要合法批大小及条件开关')
        self._budget,self._spec,self._input_unit,self._dtype=budget,spec,input_unit,dtype
        self._consumer,self._backend=consumer,backend
        self._limit,self._conditioned,self._samples=batch_intervals,conditioned,True
        self._held_cost=self._fixed_cost=self._workspace_cost=0
        self._rows=None;self._last_time=None
        self._closed=self._closing=self._failed=self._finished=False
        try:
            _reserve_owned_ram(self,65536+(batch_intervals+1)*4096,'_fixed_cost')
            self._rows=[]
        except BaseException as error:
            _cleanup_owner(self,error,'record_selection_cleanup_owner','样本选择');raise

    def _flush(self):
        """消费当前正时段，留下右端供下一批。参数: 无。返回: None。异常: 核或输出错误。"""
        if len(self._rows)<2:return
        series=row=iterator=None
        try:
            _reserve_owned_ram(self,65536+len(self._rows)*36864,'_workspace_cost')
            series=sample_series(self._rows,self._input_unit,self._conditioned)
            iterator=(select_reference if self._backend=='reference' else select_numpy)(series,self._spec)
            for row in iterator:self._consumer(row)
            self._rows[:]=self._rows[-1:]
        except BaseException:
            self._failed=True;raise
        finally:
            if iterator is not None:iterator.close()
            series=row=iterator=None
            _release_owned_ram(self,self._workspace_cost,'_workspace_cost')

    def finish(self):
        """EOF后输出最后正范围，无末尾假样本。参数: 无。返回: None。异常: 原计算/写入错。"""
        self._require_open()
        if not self._finished:self._flush();self._finished=True

    def close(self):
        """释放缓冲及回调，实际费用归零后关闭。参数: 无。返回: None。异常: 预算释放错。"""
        if self._closed:return
        self._closing=True;self._rows=self._consumer=None
        _release_owned_ram(self,self._workspace_cost,'_workspace_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
