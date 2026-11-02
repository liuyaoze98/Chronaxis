"""检验有限条件积分owner复用同一数值核，TRUE/FALSE/UNKNOWN与实际截止不混淆。"""

import unittest
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.record_integral import RecordIntegral
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError
from test_record_integral import point


def flag(value):
    """构造显式三值条件。参数: bool或None。返回: ScalarValue。异常: 模型错误。"""
    return ScalarValue(value, D.BOOL) if value is not None else ScalarValue(None, D.BOOL, False, Q.MISSING)


class RecordConditionalIntegralTests(unittest.TestCase):
    """不新增另一套积分owner，测试同一对象的条件分支与默认无明细。"""

    def owner(self, backend, *, size=1, policy='report'):
        """建立共享预算和三段请求。参数: 后端/批大小/政策。返回: owner,budget。异常: 构造失败。"""
        budget = ResourceBudget()
        owner = RecordIntegral(budget, CalculationDefinition('energy', 'integral', Interval(0, 360_000_000),
            partial_policy=policy), 'W', D.FLOAT64, 100_000_000, backend=backend,
            batch_intervals=size, conditioned=True)
        self.addCleanup(owner.close)
        return owner, budget

    def test_true_false_unknown_and_batch_sizes(self):
        """三段TRUE/FALSE/UNKNOWN仅首段400J，strict不交付部分正常值。"""
        for backend in ('reference','numpy'):
            for size in (1,2,64):
                for policy in ('report','strict'):
                    owner, budget = self.owner(backend, size=size, policy=policy)
                    for index, selected in enumerate((True, False, None, True)):
                        owner.consume((point(index*120_000_000, 4000.),), conditions=(flag(selected),))
                    result = owner.finish()
                    self.assertEqual(result.value, 400. if policy=='report' else None)
                    self.assertEqual(result.status, 'partial' if policy=='report' else 'indeterminate')
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)
                    self.assertEqual(budget.spool_bytes, 0)

    def test_complete_false_is_zero_even_when_values_missing(self):
        """完整已知FALSE是有效空选择零，无效值不能把它改成未知。"""
        for backend in ('reference','numpy'):
            owner, _ = self.owner(backend)
            for index in range(4):
                owner.consume((point(index*120_000_000, None),), conditions=(flag(False),))
            result = owner.finish()
            self.assertEqual((result.value,result.status,result.reason), (0.,'complete','empty_selection'))

    def test_independent_condition_expiry_and_invalidation(self):
        """值持续有效、选择中途未知：只积首半周期，后续不补缺口。"""
        for backend in ('reference','numpy'):
            owner, _ = self.owner(backend)
            owner.consume((point(0,4000.),), conditions=(flag(True),))
            owner.expire_at(60_000_000, condition=True)
            for index in range(1,4):
                owner.consume((point(index*120_000_000,4000.),), conditions=(flag(None),))
            result = owner.finish()
            self.assertEqual((result.value,result.status),(200.,'partial'))

    def test_condition_shape_failure_blocks_finish(self):
        """条件长度/类型错误失败，不吞成FALSE并发布前缀。"""
        owner, budget = self.owner('numpy')
        with self.assertRaises(ValueError):
            owner.consume((point(0,4000.),), conditions=())
        with self.assertRaises(ResultClosedError):
            owner.finish()
        owner.close()
        self.assertEqual(budget.ram_bytes,0)
