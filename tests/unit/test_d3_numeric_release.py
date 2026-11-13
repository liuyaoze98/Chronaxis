"""保留异常时核验排序和滚动窗口本层副本释放，不修改外部回溯或借用输入。

两排序核心先分配真实副本再注入失败；滚动测试保留生成的历史段弱引用。
只检查具体对象和本层局部，不把预算归零宣称为整个进程RSS保证。
"""
import gc
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref
import numpy as np
from chronaxis.core import quantile_reference, quantile_numpy
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.transform_stream import TransformStage
from chronaxis import extension_runtime
from test_d3_resource_boundaries import capture_failure, local_values


class WeakList(list):
    """可弱引用的真实排序列表，用于证明本层已释放全长副本。"""


class BrokenArray(np.ndarray):
    """排序完成后在索引处模拟IO/资源失败，不在测试自身回溯保留数组。"""
    def __getitem__(self, key):
        """参数: 原下秩。返回: 不返回。异常: 指定故障，先清本测试帧引用。"""
        try:
            raise OSError('after numpy sort')
        finally:
            self = None


class Span:
    """仅由一次历史遍历产生的段，可弱引用；没有跨调用缓存。"""
    def __init__(self):
        """参数: 无。返回: 0至20秒的完整值段。异常: 无。"""
        self.value = self.point = ScalarValue(10., D.FLOAT64, True)
        self.deadline = None
        self.start = 0
        self.update = True


class TemporaryNumericReleaseTests(unittest.TestCase):
    """异常对象始终存活，检查自有副本已释放且调用者输入保持。"""
    def test_reference_sorted_copy_released(self):
        """排序后转换失败，原chunks保留，新的排序副本不留在traceback。"""
        references=[]; chunks=[[float(i) for i in range(20000)]]
        original=chunks[0][:]
        def sort_copy(items):
            """参数: 借用值流。返回: 可弱引用的排序副本。异常: 分配错误。"""
            result=WeakList(sorted(items)); references.append(weakref.ref(result)); return result
        def fail(value):
            """参数: 单个端点。返回: 无。异常: 模拟端点处理失败。"""
            raise OSError('after reference sort')
        with patch.object(quantile_reference,'sorted',new=sort_copy,create=True),patch.object(quantile_reference,'_exact_float',new=fail):
            error=capture_failure(lambda: quantile_reference.ordered_reference(chunks,10000,1,2))
        gc.collect(); self.assertIsInstance(error,OSError); self.assertIsNone(references[0]())
        frame=local_values(error,quantile_reference.__name__,'ordered_reference')
        self.assertIsNone(frame['ordered']); self.assertIsNone(frame['chunks']); self.assertEqual(chunks[0],original)

    def test_numpy_sorted_copy_released(self):
        """NumPy排序后的索引失败也释放全长副本，原dtype输入不变。"""
        references=[];chunks=[np.arange(20000,dtype=np.uint64)];original=chunks[0].copy()
        concatenate=np.concatenate
        def copy(items):
            """参数: 借用列块。返回: 故障索引数组。异常: 分配错误。"""
            value=concatenate(items).view(BrokenArray);references.append(weakref.ref(value));return value
        with patch.object(quantile_numpy.np,'concatenate',new=copy):
            error=capture_failure(lambda: quantile_numpy.ordered_numpy(chunks,10000,1,2))
        gc.collect();self.assertIsInstance(error,OSError);self.assertIsNone(references[0]())
        frame=local_values(error,quantile_numpy.__name__,'ordered_numpy')
        self.assertIsNone(frame['values']);self.assertIsNone(frame['chunks']);np.testing.assert_array_equal(chunks[0],original)

    def test_rolling_window_locals_released_after_host_failure(self):
        """宿主计算失败后，本层不保留窗口列表及最后段，不清宿主错误回溯。"""
        references=[]
        def slices(time):
            """参数: 网格点。返回: 新建单段。异常: 无；段不写入额外缓存。"""
            span=Span();references.append(weakref.ref(span));yield span,0,20,1
        def fail(host,time,window,values,weights,conversion):
            """参数: 当前网格数据。返回: 无。异常: 原宿主故障；本测试不持有输入。"""
            try:
                raise OSError('host rolling failure')
            finally:
                host=values=weights=conversion=None
        stage=object.__new__(TransformStage)
        stage.item=SimpleNamespace(operation='rolling_mean',window_ns=20,partial_policy='partial',minimum_coverage=0,conversion=None)
        stage.history=SimpleNamespace(slices=slices);stage.host=object();stage.backend='numpy'
        with patch.object(extension_runtime,'advance_grid',new=fail):
            error=capture_failure(lambda: stage._at_grid(20,None,False))
        gc.collect();self.assertIsInstance(error,OSError);self.assertIsNone(references[0]())
        frame=local_values(error,TransformStage.__module__,'_at_grid')
        for name in ('values','weights','fit','span','left_value','right_value','point','value'):
            self.assertIsNone(frame[name],name)
        self.assertIn('fail',[trace.tb_frame.f_code.co_name for trace in self.traces(error)])

    def traces(self,error):
        """参数: 原错。返回: 未修改的回溯节点流。异常: 无。"""
        trace=error.__traceback__
        while trace is not None:
            yield trace;trace=trace.tb_next
