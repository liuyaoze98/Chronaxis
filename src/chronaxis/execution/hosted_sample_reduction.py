"""把有限真实样本块交给明确注册的宿主归约，复用原半开选择、覆盖与独立数值后端。"""

from dataclasses import replace
from ..core.calculation_output_numpy import convert_result_numpy
from ..core.calculation_output_reference import convert_result_reference
from ..core.sample_reduction import SampleReductionResult
from ..core.sample_reduction_numpy import NumpySampleReduction
from ..core.sample_reduction_reference import ReferenceSampleReduction
from ..core.types import QualityFlag as Q
from ..extension_runtime import HostedReduction
from ..results.budget import _cleanup_owner


class HostedSampleReduction:
    """一个会话、事件或窗口持有一个插件状态；插件不决定是否选入样本及结果显示单位。"""

    def __init__(self, spec, input_unit, dtype, descriptor, conversion, backend, budget, partial_limit):
        """创建所选后端的覆盖计算器及宿主状态。参数: 已校验请求、描述、单位及预算。

        返回: 独立归约owner。异常: 宿主工厂或预算失败转交可重试清理句柄。
        """
        self._host=self._coverage=None
        self._conversion=conversion
        self._convert=convert_result_reference if backend=='reference' else convert_result_numpy
        self._closed=self._finished=self.partial=False
        try:
            coverage_spec=replace(spec,operation='sample_count',output_unit='1')
            kernel=ReferenceSampleReduction if backend=='reference' else NumpySampleReduction
            self._coverage=kernel(coverage_spec,input_unit,dtype,partial_limit=partial_limit)
            self._host=HostedReduction(descriptor,backend,budget)
        except BaseException as error:
            self._host=getattr(error,'extension_cleanup_owner',self._host)
            _cleanup_owner(self,error,'hosted_sample_cleanup_owner','宿主样本归约')
            raise

    def push(self,series):
        """沿同一选中掩码消费并返回覆盖事实。参数: 有限 CalculationSeries。返回: 本块 facts。异常: 回调或输入错误。"""
        return self._coverage.push(series,sample_consumer=self._host.consume)

    def finish(self):
        """无参与值保留空结果，输出单位只变换一次。参数: 无。返回: SampleReductionResult。异常: 回调或转换错误。"""
        count=self._coverage.valid_sample_count
        number,quality=None,Q.NONE
        if count:
            value=self._host.finalize()
            self.partial=value.partial
            if value.valid:
                number,quality=self._convert(value.value,value.dtype,self._conversion)
            else:
                quality=value.quality
        self._finished=True
        return SampleReductionResult(number,self._conversion.unit,bool(quality),quality,count)

    def close(self):
        """未正常结束时通知取消，释放宿主和覆盖状态。参数: 无。返回: None。异常: 清理失败可重试。"""
        if self._closed:
            return
        if self._host is not None:
            self._host.close(cancelled=not self._finished)
        if self._coverage is not None:
            self._coverage.close()
        self._closed=True
