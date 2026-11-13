"""直接核对独立积分数值核在异常回溯中的借用释放；owner故障由record专项覆盖。"""
import gc
import unittest
import weakref
from unittest.mock import patch
import numpy as np
from chronaxis.core.integral_sum_reference import ReferenceIntegralSum
from chronaxis.core.integral_sum_numpy import NumpyIntegralSum
from chronaxis.core.integral_sum import IntegralStateLimitError
import chronaxis.core.integral_sum_reference as reference_module

class AddObserver:
    """透明保存真实accumulate产物的弱引用，不额外持有数组。"""
    def __init__(self, original, references):
        """参数: 原ufunc与引用列表。返回: 包装器。异常: 无。"""
        self.original, self.references = original, references
    def __call__(self, *args, **kwargs):
        """参数: 原操作参数。返回: 原数值。异常: 原错误。"""
        return self.original(*args, **kwargs)
    def accumulate(self, *args, **kwargs):
        """参数: 原数组参数。返回: 原数组。异常: 原错误；不保存强引用。"""
        result = self.original.accumulate(*args, **kwargs)
        self.references.append(weakref.ref(result))
        return result

class IntegralTracebackCleanupTests(unittest.TestCase):
    """保留异常和外部guard，核本层输入、临时数组及累计器不被回溯钉住。"""
    def exercise(self, stage):
        """构造有限数值并命中真实故障。参数: 故障阶段。返回: 原错和弱引用。异常: 未命中断言。"""
        refs, highs = [], []
        failure = KeyboardInterrupt('kernel-' + stage)
        original_finite, original_subtract = np.isfinite, np.subtract
        kernel = values = valid = None
        error = None
        try:
            kernel = ReferenceIntegralSum(1 if stage == 'capacity' else 4096) if stage in ('capacity','validation') else NumpyIntegralSum()
            refs.append(weakref.ref(kernel))
            if stage in ('capacity','validation'):
                values, valid = (1e16, 1., -1e16), (True, True, True)
                if stage == 'validation':
                    with patch.object(reference_module, 'isfinite', side_effect=failure):
                        kernel.push_values(values, valid)
                else:
                    kernel.push_values(values, valid)
            else:
                values = np.array((1e16, 1., 1e-16)); valid = np.ones(3,dtype=bool)
                values.setflags(write=False); valid.setflags(write=False)
                refs.extend((weakref.ref(values),weakref.ref(valid),weakref.ref(kernel._partials)))
                if stage == 'advance':
                    def finite(value, *args, **kwargs):
                        """仅实际advance的highs处取消。参数: 原值。返回: 原掩码。异常: 指定取消。"""
                        try:
                            if any(item() is value for item in highs):
                                raise failure
                            return original_finite(value,*args,**kwargs)
                        finally:
                            value = args = kwargs = None
                    with patch.object(np,'add',AddObserver(np.add,highs)), patch.object(np,'isfinite',finite):
                        kernel.push_values(values,valid)
                else:
                    kernel.push_values(values,valid)
                    refs.append(weakref.ref(kernel._partials))
                    def subtract(*args, **kwargs):
                        """真实差列生成后取消。参数: 原值。返回: 不返回。异常: 指定取消。"""
                        result = None
                        try:
                            result=original_subtract(*args,**kwargs)
                            refs.append(weakref.ref(result))
                            raise failure
                        finally:
                            args=kwargs=result=None
                    with patch.object(np,'subtract',subtract):
                        kernel.finish('J')
        except BaseException as caught:
            error = caught
        finally:
            kernel = values = valid = None
        self.assertIsNotNone(error)
        if stage == 'capacity':
            self.assertIsInstance(error,IntegralStateLimitError)
        else:
            self.assertIs(error,failure)
        gc.collect()
        self.assertTrue(all(item() is None for item in refs+highs))
        return error
    def test_reference_capacity_clears_own_kernel(self):
        """容量拒绝保原类型并释放本层引用。参数: 无。返回: None。异常: 断言。"""
        self.exercise('capacity')
    def test_reference_validation_has_no_hidden_zip(self):
        """验证取消不留下捕获整列的生成器。参数: 无。返回: None。异常: 断言。"""
        error=self.exercise('validation'); cursor=error.__traceback__
        while cursor is not None:
            frame=cursor.tb_frame
            self.assertFalse(frame.f_globals.get('__name__')==reference_module.__name__ and frame.f_code.co_name=='<genexpr>')
            cursor=cursor.tb_next
    def test_numpy_advance_releases_real_temporaries(self):
        """真实accumulate后取消不留临时/旧视图。参数: 无。返回: None。异常: 断言。"""
        guard={'caller':'retained'};self.exercise('advance');self.assertEqual(guard,{'caller':'retained'})
    def test_numpy_rounding_releases_real_temporaries(self):
        """真实舍入差列取消不留reverse视图。参数: 无。返回: None。异常: 断言。"""
        self.exercise('rounding')
