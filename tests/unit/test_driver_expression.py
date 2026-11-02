"""核对真实完整组→驱动表达式→周期积分，实际有效期不随固定周期改变。

使用已归一化的小样本进入既有LatestSignalState，同刻政策由原组件执行。
只建必要最新值与有限积分缓冲，不创建历史仓；手算预期独立于两数值后端。
"""

from dataclasses import replace
import unittest
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import validate_expression
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.state import LatestSignalState
from chronaxis.execution.driver_expression import DriverExpression
from chronaxis.execution.record_integral import RecordIntegral
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError, BudgetExceededError
from test_stream_state import make_sample


class DriverExpressionTests(unittest.TestCase):
    """逐个提交完整同刻组，验证原始声明/实际最新状态绑定及失败资源生命周期。"""

    def test_boundary_queries_do_not_advance_driver_or_extend_source(self):
        """TTL查询不消耗驱动组；来源末点可用但右侧已未知，不产生第二时间轴。"""
        for backend in ('reference','numpy'):
            driver,state,budget=self.setup_owner(backend)
            self.group(state,0,(('voltage',400.),('current',10.)))
            value,deadline=driver.evaluate_at(0)
            self.assertEqual((value.value,deadline),(4000.,150_000_000))
            self.assertIsNotNone(driver.evaluate())
            stale,_=driver.evaluate_at(150_000_000)
            self.assertFalse(stale.valid)
            self.assertTrue(stale.quality & Q.STALE)
            driver._observation_ends={'bus':100_000_000}
            point,_=driver.evaluate_at(100_000_000,continuous=False)
            right,_=driver.evaluate_at(100_000_000)
            self.assertTrue(point.valid)
            self.assertFalse(right.valid)
            self.assertTrue(right.quality & Q.MISSING)
            driver.close();state.close()
            self.assertEqual(budget.ram_bytes,0)

    def setup_owner(self, backend='numpy', *, voltage_age=150_000_000, expr='voltage * current'):
        """构造两信号同源声明及真实状态。参数: 后端/有效期/公式。返回: driver,state,budget。异常: 构造失败。"""
        clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'test_origin')
        self.voltage = SignalDefinition('voltage', 'bus', 'raw.v', D.FLOAT64, 'V', voltage_age,
                                        same_time_policy='last_by_sequence')
        self.current = SignalDefinition('current', 'bus', 'raw.i', D.FLOAT64, 'A', 10**9,
                                        same_time_policy='last_by_sequence')
        declarations = DeclarationBindings('session', clock, Interval(0, 10**9),
            (DeclaredSource('bus', clock, 'synthetic'),), (self.voltage, self.current))
        budget = ResourceBudget()
        state = LatestSignalState(budget, declarations.signals, 'session')
        self.addCleanup(state.close)
        driver = DriverExpression(validate_expression(expr, declarations), state, 'current', backend=backend)
        self.addCleanup(driver.close)
        return driver, state, budget

    def group(self, state, time, pairs):
        """按显式别名/值提交完整组。参数: state/time/pairs。返回: None。异常: 原状态政策错误。"""
        state.apply(DecodedTimeGroup(time, tuple(make_sample(state.definitions[name], time, index, value)
            for index, (name, value) in enumerate(pairs))))

    def test_expiry_and_new_voltage_recovery_into_integral(self):
        """0.15秒过期，0.36新电压只更新状态，0.4驱动才恢复；间隙不补算。"""
        for backend in ('reference', 'numpy'):
            driver, state, budget = self.setup_owner(backend)
            integral = RecordIntegral(budget, CalculationDefinition('energy', 'integral', Interval(0, 600_000_000)),
                                      'W', D.FLOAT64, 100_000_000, backend=backend, batch_intervals=1)
            self.addCleanup(integral.close)
            for time, pairs, valid in (
                (0, (('voltage', 400.), ('current', 10.)), True),
                (180_000_000, (('current', 12.),), False),
                (360_000_000, (('voltage', 400.),), None),
                (400_000_000, (('current', 10.),), True),
                (600_000_000, (('current', 10.),), False)):
                self.group(state, time, pairs)
                row = driver.evaluate()
                if valid is None:
                    self.assertIsNone(row)
                else:
                    self.assertEqual(row[1].valid, valid)
                    if not valid:
                        self.assertTrue(row[1].quality & Q.STALE)
                    integral.consume((row,))
                self.assertIsNone(driver.evaluate())
            result = integral.finish()
            self.assertAlmostEqual(result.value, 400. * 150 / 180 + 400. * 110 / 200)
            self.assertEqual(result.status, 'partial')
            integral.close()
            driver.close()
            self.assertFalse(state.closed)
            state.close()
            self.assertEqual(budget.ram_bytes, 0)
            self.assertEqual(budget.spool_bytes, 0)

    def test_atomic_same_time_missing_and_fresh_boundary(self):
        """同刻最后序号值先提交；缺值覆盖旧值；到旧值到期时的新值立即可用。"""
        for backend in ('reference', 'numpy'):
            driver, state, _ = self.setup_owner(backend)
            self.group(state, 0, (('current', 10.), ('voltage', 350.), ('voltage', 400.)))
            self.assertEqual(driver.evaluate()[1].value, 4000.)
            self.group(state, 100_000_000, (('voltage', None), ('current', 10.)))
            self.assertFalse(driver.evaluate()[1].valid)
            self.group(state, 150_000_000, (('current', 10.), ('voltage', 410.)))
            row = driver.evaluate()
            self.assertEqual(row[1].value, 4100.)
            self.assertEqual(row[2], 300_000_000)

    def test_missing_dependency_and_skipped_group(self):
        """未观测电压保持未知；漏消费完整组不能用最新状态伪装历史计算。"""
        driver, state, _ = self.setup_owner()
        self.group(state, 0, (('current', 10.),))
        row = driver.evaluate()
        self.assertFalse(row[1].valid)
        self.assertTrue(row[1].quality & Q.MISSING)
        self.group(state, 1, (('current', 11.),))
        self.group(state, 2, (('current', 12.),))
        with self.assertRaises(ValueError):
            driver.evaluate()
        with self.assertRaises(ResultClosedError):
            driver.evaluate()

    def test_non_driver_invalid_update_stops_pending_power(self):
        """电压中途报无效立即截断旧功率；新电压到来不能倒填缺口。"""
        for backend in ('reference', 'numpy'):
            driver, state, budget = self.setup_owner(backend)
            integral = RecordIntegral(budget, CalculationDefinition('energy', 'integral', Interval(0, 400_000_000)),
                                      'W', D.FLOAT64, 100_000_000, backend=backend, batch_intervals=1)
            self.addCleanup(integral.close)
            for time, pairs in ((0, (('voltage', 400.), ('current', 10.))),
                (50_000_000, (('voltage', None),)), (100_000_000, (('current', 10.),)),
                (200_000_000, (('voltage', 400.),)), (300_000_000, (('current', 10.),)),
                (400_000_000, (('current', 10.),))):
                self.group(state, time, pairs)
                row = driver.evaluate()
                if driver.invalidated_at is not None:
                    integral.expire_at(driver.invalidated_at)
                if row is not None:
                    integral.consume((row,))
            self.assertAlmostEqual(integral.finish().value, 400.)

    def test_budget_failure_and_close_retry(self):
        """求值前超预算不得交值；释放失败可重试且不关闭借入状态。"""
        driver, state, budget = self.setup_owner()
        self.group(state, 0, (('current', 10.), ('voltage', 400.)))
        budget.memory_budget_bytes = budget.ram_bytes
        with self.assertRaises(BudgetExceededError):
            driver.evaluate()
        with patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                driver.close()
        driver.close()
        state.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_constant_and_unbounded_expiry_do_not_invent_times(self):
        """常量仍按显式驱动触发；实际有效期超int64末端时不回绕失效。"""
        for backend in ('reference', 'numpy'):
            driver, state, _ = self.setup_owner(backend, expr='2')
            self.group(state, 0, (('current', None),))
            row = driver.evaluate()
            self.assertEqual(row[1].value, 2)
            self.assertIsNone(row[2])
            driver, state, _ = self.setup_owner(backend)
            self.group(state, (1 << 63) - 2, (('current', 10.), ('voltage', 400.)))
            row = driver.evaluate()
            self.assertTrue(row[1].valid)
            self.assertIsNone(row[2])

    def test_mismatched_definition_and_static_mutation_rejected(self):
        """公开声明不能替换实际单位/有效期，合法文本被改动也需重新校验。"""
        driver, state, budget = self.setup_owner()
        static = driver._static
        before = budget.ram_bytes
        altered = replace(static, text='voltage + current')
        with self.assertRaises(ValueError):
            DriverExpression(altered, state, 'current')
        self.assertEqual(budget.ram_bytes, before)
        other = LatestSignalState(budget, (replace(self.voltage, valid_for_ns=1), self.current), 'session')
        try:
            with self.assertRaises(ValueError):
                DriverExpression(static, other, 'current')
        finally:
            other.close()

    def test_boolean_expiry_preserves_three_value_short_circuit(self):
        """TRUE or UNKNOWN仍为TRUE，不能按最早无关依赖截止提前失效。"""
        for backend in ('reference', 'numpy'):
            driver, state, _ = self.setup_owner(backend, expr='(voltage > 350) or (current > 5)')
            self.group(state, 0, (('voltage', 400.), ('current', 10.)))
            row = driver.evaluate()
            self.assertTrue(row[1].value)
            self.assertEqual(row[2], 10**9)
            self.group(state, 100_000_000, (('voltage', None),))
            self.assertIsNone(driver.evaluate())
            self.assertIsNone(driver.invalidated_at)
            self.group(state, 200_000_000, (('current', 2.),))
            self.assertFalse(driver.evaluate()[1].valid)
            driver, state, _ = self.setup_owner(backend, expr='False and (current > 5)')
            self.group(state, 0, (('current', None),))
            row = driver.evaluate()
            self.assertTrue(row[1].valid)
            self.assertFalse(row[1].value)
            self.assertIsNone(row[2])

    def test_condition_expression_reaches_same_integral_owner(self):
        """功率与选择条件使用同一完整组，TRUE/FALSE分别加400J/0J。"""
        for backend in ('reference', 'numpy'):
            driver, state, budget = self.setup_owner(backend, voltage_age=10**9)
            condition = DriverExpression(validate_expression('current > 0', driver._static.bindings),
                                         state, 'current', backend=backend)
            self.addCleanup(condition.close)
            integral = RecordIntegral(budget, CalculationDefinition('energy', 'integral', Interval(0, 300_000_000)),
                'W', D.FLOAT64, 100_000_000, backend=backend, batch_intervals=1, conditioned=True)
            self.addCleanup(integral.close)
            for time, value in ((0, 10.), (120_000_000, -5.), (300_000_000, 10.)):
                self.group(state, time, (('voltage', 400.), ('current', value)))
                row, selected = driver.evaluate(), condition.evaluate()
                integral.consume((row,), conditions=(selected[1],), condition_valid_until_ns=(selected[2],))
            result = integral.finish()
            self.assertEqual((result.value, result.status), (400., 'complete'))
