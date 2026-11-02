"""验收真实历史的有限样本统计输入，不声称整窗归约或select已接线。

memory/CSV历史与两后端提供有限CalculationSeries；既有指标核即时计算并关闭每块。
手算只统计窗口内的真实数值更新，TTL、条件更新、裁剪保持和右端点不新增样本。
测试保留小型块结果及真实更新时间，不把各块均值简单合成为整窗均值。
新分块者拥有回读与输出，原history/state借用；预算拒绝后显式关闭至fixture基线。
所有合成数据只在work创建，原工厂最终清理并核对RAM0。
"""

# 工厂用模块别名，避免unittest重复发现原测试类。
import unittest
from unittest.mock import patch
import test_historical_conditional_blocks as real_history
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.calculation_blocks import HistoricalCalculationBlocks
from chronaxis.execution.historical_conditional_blocks import HistoricalConditionalBlocks
from chronaxis.results.errors import BudgetExceededError
from chronaxis.sources.csv_spec import CSVSourceRef


class HistoricalSampleBlocksTests(unittest.TestCase):
    """每块计算与关闭，自有分块者关闭后原历史和state不受影响。"""

    def prepare(self, *, joint=False, backend='numpy', kind='memory', size=1, operation='sample_mean', window=None, ttl=10, condition=None):
        """建立0/2/4ns值4/8/12的实际历史，4ns只作为EOF右边界。

        参数: joint指定联合输入；后端/来源/大小/operation/窗口/TTL/固定条件为明确配置。
        返回: fixture,owner,spec,baseline。异常: 原工厂或构造错误传播。
        """
        factory = real_history.HistoricalConditionalBlocksTests('runTest')
        # 原工厂负责历史、绑定和保持对象，先登记清理，后续新owner构造失败也能收尾。
        self.addCleanup(self.cleanup_factory, factory)
        # 默认条件在0/1/2/3/4ns为T/F/T/U/T，数值只在0/2/4ns真实更新。
        condition_values = (1, 0, 1, None, 1) if condition is None else (condition,) * 5
        fixture = factory.fixture(backend=backend, kind=kind, size=size, domain=(0, 4),
            definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', ttl),
                         SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 10)),
            rows_by_source={'table': tuple(MemoryRow(time, {'raw.a': value}, index)
                for index, (time, value) in enumerate(((0, 4), (2, 8), (4, 12)))),
                'other': tuple(MemoryRow(index, {'raw.b': value}, index) for index, value in enumerate(condition_values))})
        # 先记录借用资源基线，再创建并登记自有分块者；关闭owner不能释放原工厂金额。
        baseline = fixture.budget.ram_bytes
        spec = CalculationDefinition('samples', operation, Interval(0, 4) if window is None else window)
        args = (fixture.history, fixture.holds._context, fixture.lease.bindings, fixture.compiled[0], spec)
        owner = (HistoricalConditionalBlocks(*args, fixture.compiled[1], backend=backend, batch_intervals=size)
                 if joint else HistoricalCalculationBlocks(*args, backend=backend, batch_intervals=size))
        self.addCleanup(owner.close)
        return fixture, owner, spec, baseline

    def cleanup_factory(self, factory):
        """核对原工厂RAM0。参数: 原工厂。返回: None。异常: 清理断言失败。"""
        self.assertTrue(factory.doCleanups())

    def consume(self, owner, spec, backend):
        """逐块调用既有核并关闭，仅保存小型结果和块内真实更新时间。

        参数: owner/spec/后端实际输入。返回: 结果列表与真实更新时间列表。异常: 原计算错误。
        """
        compute = compute_reference if backend == 'reference' else compute_numpy
        results, updates = [], []
        for block in owner:
            try:
                series = block.series
                # 块右端点归后块；测试只收集该块半开范围内的原数值更新，条件边界不在标志中。
                updates.extend(time for time, real in zip(series.times_ns, series.actual_value_updates)
                               if real and series.observation.start_ns <= time < series.observation.end_ns)
                results.append(compute(series, spec))
            finally:
                block.close()
        return results, updates

    def close_and_check(self, fixture, owner, baseline):
        """关闭自有分块者并保留借用历史，重复关闭不重复释放。

        参数: 实际资源及原金额。返回: None。异常: 账本或借用责任不符。
        """
        # 两次关闭验证自有资源只释放一次；历史、原state及原金额仍归工厂。
        owner.close()
        owner.close()
        self.assertEqual(fixture.budget.ram_bytes, baseline)
        self.assertFalse(fixture.history.closed)
        self.assertEqual(fixture.state.revision, 0)

    def test_three_sample_ops_real_sources_backends_splits_keep_true_updates(self):
        """无条件真实样本仅0ns的4与2ns的8；整块已有核得min4/max8/mean6。

        参数: 无。返回: None。异常: 来源/后端/切分改变真实输入或单块手算。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    for operation, expected in (('sample_minimum', 4.), ('sample_maximum', 8.), ('sample_mean', 6.)):
                        fixture, owner, spec, baseline = self.prepare(kind=kind, backend=backend, size=size, operation=operation)
                        results, updates = self.consume(owner, spec, backend)
                        self.assertEqual(updates, [0, 2])
                        self.assertEqual(sum(result.valid_sample_count for result in results), 2)
                        if size == 7:
                            self.assertEqual(results[0].value, expected)  # 只断言一个完整有限块，不冒充跨块均值。
                        if kind == 'csv':
                            self.assertTrue(any(isinstance(ref, CSVSourceRef) and ref.path for result in results for ref in result.source_refs))
                        self.close_and_check(fixture, owner, baseline)

    def test_joint_three_ops_condition_updates_do_not_create_samples(self):
        """T/F/T/U联合边界仍只有原值更新0/2ns，两选中样本；1/3ns条件更新不计样本。

        参数: 无。返回: None。异常: 条件边界、块边界或两后端改变样本输入。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    for operation, expected in (('sample_minimum', 4.), ('sample_maximum', 8.), ('sample_mean', 6.)):
                        fixture, owner, spec, baseline = self.prepare(joint=True, kind=kind, backend=backend, size=size, operation=operation)
                        results, updates = self.consume(owner, spec, backend)
                        self.assertEqual(updates, [0, 2])
                        self.assertEqual(sum(result.valid_sample_count for result in results), 2)
                        self.assertEqual(sum(result.condition_known_duration_ns for result in results), 3)
                        if size == 7:
                            self.assertEqual(results[0].value, expected)
                        self.close_and_check(fixture, owner, baseline)

    def test_ttl_boundaries_preserve_updates_without_counting_stale_transitions(self):
        """值TTL1ns产生1/3ns失效边界，仍只计0/2ns两个真实有效样本。

        参数: 无。返回: None。异常: TTL边界被伪造为更新或真实更新丢失。
        """
        for backend in ('reference', 'numpy'):
            for joint in (False, True):
                fixture, owner, spec, baseline = self.prepare(backend=backend, joint=joint, ttl=1)
                results, updates = self.consume(owner, spec, backend)
                self.assertEqual(updates, [0, 2])
                self.assertEqual(sum(result.valid_sample_count for result in results), 2)
                self.assertEqual(sum(result.value_valid_duration_ns for result in results), 2)
                self.close_and_check(fixture, owner, baseline)

    def test_clipped_held_value_right_endpoint_point_and_outside_have_no_samples(self):
        """[1,2)只有继承4W而无真实更新，2ns右端、点请求及域外均不增加样本。

        参数: 无。返回: None。异常: 窗口边界或右末点被计作样本。
        """
        for backend in ('reference', 'numpy'):
            for joint in (False, True):
                for window in (Interval(1, 2), Interval(4, 4), Interval(5, 6)):
                    fixture, owner, spec, baseline = self.prepare(backend=backend, joint=joint, window=window)
                    results, updates = self.consume(owner, spec, backend)
                    self.assertEqual(updates, [])
                    self.assertEqual(sum(result.valid_sample_count for result in results), 0)
                    self.assertTrue(all(result.value is None for result in results))
                    self.close_and_check(fixture, owner, baseline)

    def test_false_and_unknown_condition_do_not_select_real_value_updates(self):
        """外FALSE或UNKNOWN不选真实样本，数值更新标志仍保留而不是被条件改写。

        参数: 无。返回: None。异常: 条件被当FALSE填值或样本来源标志被删除。
        """
        for backend in ('reference', 'numpy'):
            for condition in (0, None):
                # UNKNOWN用原缺失行明确构造，区别于prepare默认T/F/T/U条件。
                fixture, owner, spec, baseline = self.prepare(backend=backend, joint=True, size=7, condition=0)
                if condition is None:
                    # prepare的None表示默认条件，UNKNOWN必须另建缺失输入；先关原owner，两个工厂均保留清理。
                    owner.close()
                    factory = real_history.HistoricalConditionalBlocksTests('runTest')
                    self.addCleanup(self.cleanup_factory, factory)
                    fixture = factory.fixture(backend=backend, domain=(0, 4),
                        definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', 10), SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 10)),
                        rows_by_source={'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(4, {'raw.a': 4}, 1)),
                                        'other': (MemoryRow(0, {'raw.b': None}, 0), MemoryRow(4, {'raw.b': None}, 1))})
                    # 后续owner只借用新fixture，关闭断言改用该工厂的真实基线。
                    baseline = fixture.budget.ram_bytes
                    owner = factory.owner(fixture, spec, backend=backend, batch_intervals=7)
                results, updates = self.consume(owner, spec, backend)
                self.assertTrue(updates)
                self.assertEqual(sum(result.valid_sample_count for result in results), 0)
                self.assertTrue(all(result.value is None for result in results))
                self.assertEqual(results[0].reason, 'empty_selection' if condition == 0 else 'unknown_selection')
                self.close_and_check(fixture, owner, baseline)

    def test_budget_rejection_precedes_new_history_read_and_close_preserves_borrowed_resources(self):
        """第一个有限块预算不足时不读取新历史，自有owner关闭回原基线。

        参数: 无。返回: None。异常: 预算后仍读取或关闭借用历史。
        """
        for joint in (False, True):
            fixture, owner, spec, baseline = self.prepare(joint=joint)
            fixture.budget.memory_budget_bytes = fixture.budget.ram_bytes
            # 构造已完成；仅卡第一次推进的有限空间，不能把构造拒绝冒充读取预算验证。
            with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('read-after-budget')) as opened:
                with self.assertRaises(BudgetExceededError):
                    next(owner)
                opened.assert_not_called()
            self.close_and_check(fixture, owner, baseline)
