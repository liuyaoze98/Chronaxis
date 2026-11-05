"""验证精确分位数的排序、秩、两种数值后端与预约/释放协议。

各批次独立给定原样本，即使切成不同大小也按全体排序。预算故障分别
触发在存储样本和排序副本阶段，检查已付费用可收回及外部费用保留。
"""

import unittest
import numpy as np
from chronaxis.core.quantiles import ExactQuantileBuffer
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError


def push_rows(buffer, backend, dtype, values):
    """将一批全有效测试原值交给所选后端，数值不在夹具内归约。

    参数: buffer/后端/声明dtype与原值序列。返回: None。异常: 原预算/数据异常传播。
    """
    if backend == 'reference':
        buffer.append(values)
    else:
        buffer.append(np.array(values,dtype=dtype.value),np.ones(len(values),dtype=bool))


class QuantileBufferTests(unittest.TestCase):
    """用手算样本及小额度预算分别检验数值和失败后的资源归属。"""

    def test_whole_population_ranks_precision_and_extreme_floats(self):
        """端点返回原整数，插值精确核查必要端点，不让异号大数溢出。

        参数: 无。返回: None。异常: 值、原生类型、精度位或清理错误使断言失败。
        """
        examples = (
            (D.INT64,((20,0),(30,),(),(10,)),.95,28.5,Q.NONE),
            (D.INT64,((20,0),(30,10)),.5,15.,Q.NONE),
            (D.UINT64,((2**64-1,),),.5,2**64-1,Q.NONE),
            (D.UINT64,((9,2**64-1),(7,)),1,2**64-1,Q.NONE),
            (D.INT64,((2**53+1,0),(2**53+5,)),.5,2**53+1,Q.NONE),
            (D.INT64,((2**53+1,2**53+5),),.5,None,Q.PRECISION_LOSS),
            (D.INT64,((2**53,2**53+2),),.5,None,Q.PRECISION_LOSS),
            (D.FLOAT64,((-1.7e308,1.7e308),),.5,0.,Q.NONE),
            (D.FLOAT64,((0.,float(np.nextafter(0.,1.))),),.25,None,Q.PRECISION_LOSS),
            (D.FLOAT64,((),),.25,None,Q.NONE))
        for backend in ('reference','numpy'):
            for dtype,batches,q,expected,quality in examples:
                with self.subTest(backend=backend,batches=batches,q=q):
                    budget = ResourceBudget()
                    buf = ExactQuantileBuffer('sample_quantile',q,dtype,backend,budget)
                    try:
                        for batch in batches:
                            push_rows(buf,backend,dtype,batch)
                        value, reason = buf.finish()
                        self.assertEqual((value,reason,type(value)),(expected,quality,type(expected)))
                    finally:
                        buf.close()
                    self.assertEqual(budget.ram_bytes,0)

    def test_storage_and_sort_budget_fail_before_allocation(self):
        """分别耗尽保留费与排序费，失败后只释放本缓冲的费用。

        参数: 无。返回: None。异常: 退化成近似、泄漏、重复释放或外部费用被抵销时失败。
        """
        for backend in ('reference','numpy'):
            for limit in (200,600):
                with self.subTest(backend=backend,limit=limit):
                    budget = ResourceBudget(limit)
                    budget.reserve_ram(32)
                    owner = ExactQuantileBuffer('sample_median',None,D.INT64,backend,budget)
                    with self.assertRaises(BudgetExceededError):
                        push_rows(owner,backend,D.INT64,(1,2))
                        owner.finish()
                    with self.assertRaises(RuntimeError):
                        owner.finish()
                    owner.close()
                    owner.close()
                    self.assertEqual(budget.ram_bytes,32)

    def test_endpoints_are_streaming_and_median_rejects_q(self):
        """端点只需一个极值，不随输入增长；只接受公开有限概率。

        参数: 无。返回: None。异常: 端点分配全历史或静态接受错误字段时失败。
        """
        for op,q in (('sample_quantile',None),('sample_median',.5),('sample_quantile',True),
                     ('sample_quantile',-0.1),('sample_quantile',1.1),('sample_quantile',float('nan'))):
            with self.subTest(op=op,q=q),self.assertRaises(ValueError):
                ExactQuantileBuffer(op,q,D.INT64,'reference')
        for backend in ('reference','numpy'):
            for q in (0,1):
                budget = ResourceBudget(128)
                owner = ExactQuantileBuffer('sample_quantile',q,D.INT64,backend,budget)
                for i in range(64):
                    push_rows(owner,backend,D.INT64,(i,127-i))
                self.assertEqual(owner.finish(),(0 if q==0 else 127,Q.NONE))
                owner.close()
                self.assertEqual(budget.ram_bytes,0)
