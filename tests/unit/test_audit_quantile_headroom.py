"""验证分位数分块同时容纳临时工作区与本块新增的保留样本。

使用整数序列的手算秩作为真值，外部占用模拟仍存活的读取队列；不读日志。
覆盖两后端、连续批、共享账本、端点、真正不足及取消后的费用归属。
"""

import unittest
from statistics import median
from unittest.mock import patch

from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.record_time_calculation import RecordTimeCalculation
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError


class QuantileHeadroomTests(unittest.TestCase):
    """精确保留费用不能被分块的临时预付抢光，也不能放宽共享限额。"""

    def owner(self, budget, backend, *, operation='sample_median', q=None, end=128):
        """创建64区间批的统计器。参数: 预算、后端、算子、概率及右端。返回: owner。异常: 构造错误。"""
        spec = CalculationDefinition('rank', operation, Interval(0, end), q=q)
        return RecordTimeCalculation(budget, spec, 'V', D.INT64, None,
                                     backend=backend, batch_intervals=64)

    def consume(self, owner, start, end, *, offset=0):
        """输入半开整数索引段。参数: owner、首尾索引及值偏移。返回: None。异常: 产品错误。"""
        rows = tuple((i, ScalarValue(i + offset, D.INT64)) for i in range(start, end))
        owner.consume(rows, actual_value_updates=(True,) * len(rows))

    def test_full_workspace_no_longer_starves_sample_storage(self):
        """原先刚好付完工作区就失败的两后端均分块得正确秩。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for operation, q, expected in (('sample_median', None, 63.5),
                                            ('sample_quantile', .25, 31.75)):
                with self.subTest(backend=backend, operation=operation):
                    budget = ResourceBudget(12 * 1024**2)
                    owner = self.owner(budget, backend, operation=operation, q=q)
                    # 保留的空间恰等于旧算法65点的临时费，新增样本必须靠缩小批次容纳。
                    external = budget.memory_budget_bytes - budget.ram_bytes - (65536 + 65 * 36864)
                    budget.reserve_ram(external)
                    try:
                        self.consume(owner, 0, 65)
                        self.consume(owner, 65, 129)
                        result = owner.finish()
                        self.assertEqual(result.value, expected)
                        self.assertEqual(result.status, 'complete')
                        self.assertEqual(owner._reduction._quantile._size, 128)
                        self.assertLessEqual(budget.peak_ram_bytes, budget.memory_budget_bytes)
                    finally:
                        owner.close()
                        self.assertEqual(budget.ram_bytes, external)
                        budget.release_ram(external)

    def test_two_reducers_share_remaining_space_without_losing_samples(self):
        """先推进一项后另一项必须重新看余额，不能重复使用旧余量。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                budget = ResourceBudget(16 * 1024**2)
                owners = [self.owner(budget, backend) for _ in range(2)]
                external = budget.memory_budget_bytes - budget.ram_bytes - (65536 + 65 * 36864)
                budget.reserve_ram(external)
                try:
                    for start, end in ((0, 65), (65, 129)):
                        for index, owner in enumerate(owners):
                            self.consume(owner, start, end, offset=index * 100)
                    self.assertEqual([owner.finish().value for owner in owners], [63.5, 163.5])
                    self.assertEqual([owner._reduction._quantile._size for owner in owners], [128, 128])
                    self.assertLessEqual(budget.peak_ram_bytes, budget.memory_budget_bytes)
                finally:
                    for owner in owners:
                        owner.close()
                    self.assertEqual(budget.ram_bytes, external)
                    budget.release_ram(external)

    def test_endpoint_quantiles_do_not_require_sample_storage(self):
        """q端点只保极值，最小两点临时空间足够时不得要求存储余量。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for q in (0, 1):
                with self.subTest(backend=backend, q=q):
                    budget = ResourceBudget()
                    owner = self.owner(budget, backend, operation='sample_quantile', q=q, end=1)
                    external = budget.memory_budget_bytes - budget.ram_bytes - 139264
                    budget.reserve_ram(external)
                    try:
                        self.consume(owner, 0, 2, offset=7)
                        self.assertEqual(owner.finish().value, 7)
                        self.assertEqual(owner._reduction._quantile._buffer_cost, 0)
                    finally:
                        owner.close()
                        self.assertEqual(budget.ram_bytes, external)
                        budget.release_ram(external)

    def test_split_keeps_only_selected_real_updates_across_ttl_points(self):
        """失效插入点及共享右端都不得变成额外样本。参数: 无。返回: None。异常: 断言失败。"""
        chosen = [i for i in range(128) if i % 3 == 0 and i % 7 != 0 and i % 5 != 0]
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                budget = ResourceBudget(12 * 1024**2)
                owner = RecordTimeCalculation(budget,
                    CalculationDefinition('selected_rank', 'sample_median', Interval(0, 1280)),
                    'V', D.INT64, None, backend=backend, batch_intervals=64, conditioned=True)
                external = budget.memory_budget_bytes - budget.ram_bytes - (65536 + 65 * 36864)
                budget.reserve_ram(external)
                try:
                    for start, end in ((0, 65), (65, 129)):
                        # 每10ns一个真实点，值和条件分别在+6/+8ns失效；每5个点中
                        # 有一个仅为其他信号驱动，不能算新的目标信号样本。
                        rows = tuple((10 * i, ScalarValue(None, D.INT64, False, Q.MISSING)
                                      if i % 7 == 0 else ScalarValue(i, D.INT64), 10 * i + 6)
                                     for i in range(start, end))
                        owner.consume(rows,
                            conditions=tuple(ScalarValue(i % 3 == 0, D.BOOL) for i in range(start, end)),
                            condition_valid_until_ns=tuple(10 * i + 8 for i in range(start, end)),
                            actual_value_updates=tuple(i % 5 != 0 for i in range(start, end)))
                    result = owner.finish()
                    self.assertEqual(result.value, median(chosen))
                    self.assertEqual(owner._reduction._quantile._size, len(chosen))
                    self.assertEqual(result.status, 'partial')
                finally:
                    owner.close()
                    self.assertEqual(budget.ram_bytes, external)
                    budget.release_ram(external)

    def test_real_minimum_shortfall_still_fails_and_refunds(self):
        """缺少一个字节也不能偷偷挪用外部费用。参数: 无。返回: None。异常: 断言失败。"""
        for backend, storage in (('reference', 320), ('numpy', 264)):
            with self.subTest(backend=backend):
                budget = ResourceBudget()
                owner = self.owner(budget, backend, end=1)
                external = budget.memory_budget_bytes - budget.ram_bytes - (139264 + storage - 1)
                budget.reserve_ram(external)
                try:
                    self.consume(owner, 0, 2)
                    with self.assertRaisesRegex(BudgetExceededError, 'rank.*必要样本存储'):
                        owner.finish()
                    self.assertEqual(owner._reduction._quantile._size, 0)
                finally:
                    owner.close()
                    self.assertEqual(budget.ram_bytes, external)
                    budget.release_ram(external)

    def test_cancel_during_retained_sample_payment_releases_only_own_cost(self):
        """样本真实付款后取消，原取消保留且关闭不退还别人的占用。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                budget = ResourceBudget()
                owner = self.owner(budget, backend, end=64)
                external = budget.memory_budget_bytes - budget.ram_bytes - (65536 + 65 * 36864)
                budget.reserve_ram(external)
                original = budget.reserve_ram
                cancellation = KeyboardInterrupt('sample append cancellation')

                def reserve_then_cancel(amount):
                    """只在持久样本付款后取消。参数: 新增金额。返回: None。异常: 原取消对象。"""
                    original(amount)
                    if amount < 65536:
                        raise cancellation

                try:
                    with patch.object(budget, 'reserve_ram', side_effect=reserve_then_cancel):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            self.consume(owner, 0, 65)
                    self.assertIs(caught.exception, cancellation)
                    self.assertTrue(owner._failed)
                finally:
                    owner.close()
                    self.assertEqual(budget.ram_bytes, external)
                    budget.release_ram(external)
