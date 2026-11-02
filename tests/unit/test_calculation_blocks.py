"""用真实封存历史验证有限指标分块及其资源所有权。

输入为合成memory/CSV原行，独立手算区间、TTL和EOF；两个表达式后端分别运行。
每块交给已有独立指标核，检查半开边界只计一次、值/样本/来源完整保持。
生产不保存全轴；只有测试收集小型手算摘要，长流测试逐块关闭。
故障覆盖本步预算、构造/交付和关闭取消，旧块与原调用方资源必须保持。
所有文件由原真实工厂写入work，最终关闭全部资源并检查RAM0。
"""

# 模块别名避免把复用的原测试类重复收集。
from dataclasses import replace
import unittest
from unittest.mock import patch
import test_window_replay as real_history
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import SignalDType as D
from chronaxis.execution import calculation_blocks as module
from chronaxis.execution.calculation_blocks import HistoricalCalculationBlocks
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.timebase.conversion import INT64_MAX


class CalculationBlocksTests(unittest.TestCase):
    """复用实际回读工厂，分块资源与借用资源逆序独立关闭。"""

    def fixture(self, **kwargs):
        """准备真实新历史。

        参数: kwargs传给原回读夹具。返回: 实际fixture。异常: 工厂/最终RAM0错误。
        """
        factory = real_history.WindowReplayTests('runTest')
        fixture = factory.fixture(**kwargs)
        self.addCleanup(self.assert_factory_closed, factory)
        return fixture

    def assert_factory_closed(self, factory):
        """执行原关闭检查。参数: factory为真实工厂。返回: None。异常: 失败断言。"""
        self.assertTrue(factory.doCleanups())

    def owner(self, fixture, spec=None, **kwargs):
        """创建分块者并登记关闭。

        参数: fixture为原输入；spec默认积分2—7ns；kwargs可覆盖构造参数。
        返回: HistoricalCalculationBlocks。异常: 实际构造错误传播。
        """
        spec = CalculationDefinition('area', 'integral', Interval(2, 7)) if spec is None else spec
        owner = HistoricalCalculationBlocks(fixture.history, kwargs.pop('context', fixture.holds._context),
            kwargs.pop('bindings', fixture.lease.bindings), fixture.compiled[0], spec, **kwargs)
        self.addCleanup(owner.close)
        return owner

    def compute_blocks(self, owner, spec, backend):
        """即时计算并关闭块，测试只保留小型数值事实。

        参数: owner为分块者；spec为原请求；backend为独立指标后端。
        返回: (时间tuple, CalculationResult)列表。异常: 原核/关闭错误传播。
        """
        result = []
        compute = compute_reference if backend == 'reference' else compute_numpy
        for block in owner:
            try:
                result.append((block.series.times_ns, compute(block.series, spec)))
            finally:
                block.close()
        return result

    def test_hand_integral_ttl_and_sample_count_at_all_chunk_splits(self):
        """0/5/8ns来源回读2—7ns，面积5e-9、覆盖3ns且只有5ns一个真实样本。

        参数: 无。返回: None。异常: 切块重计面积/样本、两核或真实来源变化断言失败。
        """
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1), MemoryRow(8, {'raw.a': 2}, 2))}
        spec = CalculationDefinition('area', 'integral', Interval(2, 7))
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for count in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, intervals=count):
                        fixture = self.fixture(kind=kind, backend=backend, rows_by_source=rows, size=count)
                        baseline = fixture.budget.ram_bytes
                        owner = self.owner(fixture, spec, backend=backend, batch_intervals=count)
                        result = self.compute_blocks(owner, spec, backend)
                        self.assertAlmostEqual(sum(value.value for _, value in result if value.value is not None), 5e-9, places=20)
                        self.assertEqual(sum(value.value_valid_duration_ns for _, value in result), 3)
                        self.assertEqual(sum(value.valid_sample_count for _, value in result), 1)
                        self.assertEqual(sum(value.window_duration_ns for _, value in result), 5)
                        self.assertEqual(result[0][0][0], 2)
                        self.assertEqual(result[-1][0][-1], 7)
                        for index, (times, value) in enumerate(result):
                            self.assertLessEqual(len(times), count + 1)
                            self.assertEqual(value.binding_identity, fixture.compiled[0].identity)
                            if index:
                                self.assertEqual(result[index - 1][0][-1], times[0])
                        owner.close()
                        self.assertEqual(fixture.budget.ram_bytes, baseline)
                        self.assertEqual(fixture.state.revision, 0)

    def test_original_time_kernels_compute_exact_large_integer_and_bool_duration(self):
        """时间极值保留uint精度，BOOL时长明确只累加TRUE区间。

        参数: 无。返回: None。异常: 统计口径或原dtype变化断言失败。
        """
        large = 2 ** 63 + 1
        definition = SignalDefinition('a', 'table', 'raw.a', D.UINT64, '1', 20)
        rows = {'table': (MemoryRow(0, {'raw.a': large}, 0), MemoryRow(5, {'raw.a': large + 2}, 1))}
        for backend in ('reference', 'numpy'):
            for operation, expected in (('min_time', large), ('max_time', large + 2)):
                fixture = self.fixture(definitions=(definition,), rows_by_source=rows)
                spec = CalculationDefinition('extreme', operation, Interval(2, 7))
                result = self.compute_blocks(self.owner(fixture, spec, backend=backend, batch_intervals=1), spec, backend)
                actual = min(value.value for _, value in result) if operation == 'min_time' else max(value.value for _, value in result)
                self.assertEqual(actual, expected)
                self.assertIs(type(actual), int)
            # BOOL夹具单独使用浮点输入，不改下一后端仍需使用的精确uint定义。
            bool_definition = replace(definition, dtype=D.FLOAT64)
            fixture = self.fixture(definitions=(bool_definition,), texts=('a > 1',))
            spec = CalculationDefinition('truth', 'duration', Interval(0, 8))
            result = self.compute_blocks(self.owner(fixture, spec, backend=backend, batch_intervals=1), spec, backend)
            self.assertAlmostEqual(sum(value.value for _, value in result), 3e-9, places=20)
            self.assertEqual(sum(value.selected_duration_ns for _, value in result), 3)

    def test_actual_csv_eof_does_not_turn_terminal_sample_into_continuous_area(self):
        """真实CSV EOF5ns点值2不延长面积，5—7ns为UNKNOWN。

        参数: 无。返回: None。异常: EOF点延长/未知置零/样本重复断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(kind='csv')
            owner = self.owner(fixture, backend=backend, batch_intervals=1)
            blocks = self.compute_blocks(owner, CalculationDefinition('area', 'integral', Interval(2, 7)), backend)
            self.assertAlmostEqual(sum(value.value for _, value in blocks if value.value is not None), 1e-9, places=20)
            self.assertEqual(sum(value.valid_sample_count for _, value in blocks), 0)
            self.assertEqual(sum(value.selected_duration_ns for _, value in blocks), 1)
            self.assertTrue(any(value.value_unknown_ranges for _, value in blocks))

    def test_clipping_zero_no_intersection_empty_invalid_and_constant(self):
        """请求先与原域求交，零域/无交集不制造面积，空值和常量分开。

        参数: 无。返回: None。异常: 假观测、未知当零或重复样本断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.fixture()
            owner = self.owner(fixture, CalculationDefinition('area', 'integral', Interval(-2, 12)), backend=backend)
            block = next(owner)
            self.assertEqual(block.series.observation, Interval(0, 8))
            block.close()
            owner = self.owner(fixture, CalculationDefinition('none', 'integral', Interval(9, 10)), backend=backend)
            with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('无交集不读')) as opened:
                self.assertEqual(list(owner), [])
                opened.assert_not_called()
            spec = CalculationDefinition('zero', 'integral', Interval(5, 5))
            result = self.compute_blocks(self.owner(fixture, spec, backend=backend), spec, backend)
            self.assertEqual(result[0][0], (5,))
            self.assertIsNone(result[0][1].value)
            self.assertEqual(result[0][1].reason, 'zero_length_window')
            for rows in ((), (MemoryRow(0, {'raw.a': None}, 0),)):
                fixture = self.fixture(rows_by_source={'table': rows})
                spec = CalculationDefinition('unknown', 'integral', Interval(2, 7))
                result = self.compute_blocks(self.owner(fixture, spec, backend=backend), spec, backend)
                self.assertIsNone(result[0][1].value)
                self.assertEqual(result[0][1].value_valid_duration_ns, 0)
            fixture = self.fixture(texts=('2.0',))
            spec = CalculationDefinition('constant', 'integral', Interval(2, 7))
            result = self.compute_blocks(self.owner(fixture, spec, backend=backend), spec, backend)
            self.assertAlmostEqual(result[0][1].value, 1e-8, places=20)
            self.assertEqual(result[0][1].valid_sample_count, 0)

    def test_old_block_and_full_csv_source_metadata_survive_later_progress(self):
        """保留旧块后推进不改其列，长列名及CSVSourceRef完整保留。

        参数: 无。返回: None。异常: 装箱漏字段、旧块被改写或借用资源被关断言失败。
        """
        field = 'raw.' + '长列' * 128
        definition = SignalDefinition('a', 'table', field, D.FLOAT64, '1', 3)
        rows = {'table': (MemoryRow(0, {field: 1}, 0), MemoryRow(5, {field: 2}, 1), MemoryRow(8, {field: 2}, 2))}
        fixture = self.fixture(kind='csv', definitions=(definition,), rows_by_source=rows)
        baseline = fixture.budget.ram_bytes
        owner = self.owner(fixture, batch_intervals=1)
        first = next(owner)
        saved = first.series
        self.assertTrue(saved.source_refs)
        self.assertTrue(all(type(ref).__name__ == 'CSVSourceRef' and ref.field == field for ref in saved.source_refs))
        next(owner).close()
        self.assertIs(first.series, saved)
        self.assertEqual(first.series.values[0].value, 1.0)
        owner.close()
        with self.assertRaises(ResultClosedError):
            first.series
        self.assertFalse(fixture.history.closed)
        self.assertFalse(fixture.state.closed)
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_bad_capability_batch_type_and_actual_history_contract_reject_before_read(self):
        """拒绝select的输出单位转换、错误数量/后端或替造实际EOF契约。

        参数: 无。返回: None。异常: 误支持未接线能力或拒绝漏账断言失败。
        """
        fixture = self.fixture(kind='csv')
        baseline = fixture.budget.ram_bytes
        with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('拒绝前读')) as opened:
            for operation in ('select',):
                with self.assertRaises(ValueError):
                    self.owner(fixture, CalculationDefinition('bad', operation, Interval(2, 7), output_unit='kW'))
            for count in (True, 0, -1, 1.5):
                with self.assertRaises(ValueError):
                    self.owner(fixture, batch_intervals=count)
            with self.assertRaises(ValueError):
                self.owner(fixture, backend='bad')
            completion = replace(fixture.holds._context.completions[0], sample_count=123)
            with self.assertRaises(ValueError):
                self.owner(fixture, context=replace(fixture.holds._context, completions=(completion,)))
            opened.assert_not_called()
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_first_block_budget_cancel_precedes_history_reads_and_reclaims_cost(self):
        """块空间超限或申请成功返回取消均不读取历史，owner可关闭回原基线。

        参数: 无。返回: None。异常: 超限后推进/取消漏账/借用状态变化断言失败。
        """
        for stage in ('limit', 'before', 'after'):
            fixture = self.fixture()
            baseline = fixture.budget.ram_bytes
            owner = self.owner(fixture, batch_intervals=1)
            current = fixture.budget.ram_bytes
            if stage == 'limit':
                fixture.budget.memory_budget_bytes = current + owner._step_cost - 1
                failure = patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('预算前读'))
                error = BudgetExceededError
            else:
                helper = real_history.WindowReplayTests('runTest')
                failure = patch.object(fixture.budget, 'reserve_ram', helper.cancel_once(fixture.budget.reserve_ram, stage == 'after', owner._step_cost))
                error = KeyboardInterrupt
            with failure:
                with self.assertRaises(error):
                    next(owner)
            self.assertTrue(owner.failed)
            self.assertEqual(fixture.budget.ram_bytes, current)
            owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_current_capture_constructor_or_registry_failure_preserves_old_block(self):
        """消费后失败不可重试，已交付块保持，当前未交付申请最终可回收。

        参数: 无。返回: None。异常: 旧块被撤销、重试获准或关闭漏账断言失败。
        """
        for stage in ('capture', 'constructor', 'registry', 'partial_registry'):
            fixture = self.fixture()
            baseline = fixture.budget.ram_bytes
            owner = self.owner(fixture, batch_intervals=1)
            first = next(owner)
            if stage == 'capture':
                failure = patch.object(owner, '_capture', side_effect=MemoryError('capture'))
            elif stage == 'constructor':
                failure = patch.object(module, 'CalculationBlock', side_effect=MemoryError('block'))
            elif stage == 'registry':
                failure = patch.object(owner._results, 'add', side_effect=MemoryError('registry'))
            else:
                original = owner._results.add

                def fail_registered(block):
                    """在真实登记之后注入交付失败。

                    参数: block为本次新块。返回: 无。异常: MemoryError在实际安装之后。
                    """
                    original(block)
                    raise MemoryError('installed-registry')

                failure = patch.object(owner._results, 'add', fail_registered)
            with failure:
                with self.assertRaises(MemoryError):
                    next(owner)
            self.assertTrue(owner.failed)
            self.assertEqual(first.series.values[0].value, 1.0)
            with self.assertRaises(ResultClosedError):
                next(owner)
            owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_constructor_reserve_cancel_or_child_failure_never_opens_history(self):
        """构造申请前后取消和回读子构造失败，真实借用历史未打开且本次账本归零。

        参数: 无。返回: None。异常: 未构造成功时漏账或读取历史断言失败。
        """
        helper = real_history.WindowReplayTests('runTest')
        for stage in ('before', 'after', 'child'):
            fixture = self.fixture()
            baseline = fixture.budget.ram_bytes
            if stage == 'child':
                failure = patch.object(module, 'HistoricalWindowReplay', side_effect=MemoryError('replay-child'))
                error = MemoryError
            else:
                failure = patch.object(fixture.budget, 'reserve_ram', helper.cancel_once(fixture.budget.reserve_ram, stage == 'after'))
                error = KeyboardInterrupt
            with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('构造不可读')) as opened, failure:
                with self.assertRaises(error):
                    self.owner(fixture, batch_intervals=1)
                opened.assert_not_called()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_failed_capture_cleanup_cancel_keeps_unpublished_cost_for_retry_close(self):
        """当前块未交付且清理被取消，已创建owner仍须拥有真实未释放成本。

        参数: 无。返回: None。异常: close后未发布workspace漏账断言失败。
        """
        helper = real_history.WindowReplayTests('runTest')
        for stage in ('capture', 'constructor', 'registry'):
            for after in (False, True):
                with self.subTest(stage=stage, after=after):
                    fixture = self.fixture()
                    baseline = fixture.budget.ram_bytes
                    owner = self.owner(fixture, batch_intervals=1)
                    first = next(owner)
                    release = fixture.budget.release_ram
                    if stage == 'capture':
                        failure = patch.object(owner, '_capture', side_effect=MemoryError('capture-failure'))
                    elif stage == 'constructor':
                        failure = patch.object(module, 'CalculationBlock', side_effect=MemoryError('constructor-failure'))
                    else:
                        failure = patch.object(owner._results, 'add', side_effect=MemoryError('registry-failure'))
                    with failure, patch.object(
                            fixture.budget, 'release_ram', helper.cancel_once(release, after, owner._step_cost)):
                        with self.assertRaises(KeyboardInterrupt):
                            next(owner)
                    self.assertTrue(owner.failed)
                    self.assertEqual(first.series.values[0].value, 1.0)
                    owner.close()
                    self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_close_before_and_after_release_cancel_is_retryable_and_once(self):
        """块或owner固定成本释放前后取消，真实账本与关闭状态一致。

        参数: 无。返回: None。异常: 重复扣账、提前closed或不能重试断言失败。
        """
        helper = real_history.WindowReplayTests('runTest')
        for target in ('block', 'owner'):
            for after in (False, True):
                fixture = self.fixture()
                baseline = fixture.budget.ram_bytes
                owner = self.owner(fixture, batch_intervals=1)
                block = next(owner)
                object_ = block if target == 'block' else owner
                cost = block._cost if target == 'block' else owner._fixed_cost
                with patch.object(fixture.budget, 'release_ram', helper.cancel_once(fixture.budget.release_ram, after, cost)):
                    with self.assertRaises(KeyboardInterrupt):
                        object_.close()
                self.assertEqual(object_.closed, after)
                object_.close()
                owner.close()
                owner.close()
                self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_long_stream_closing_each_block_keeps_one_front_and_bounded_live_budget(self):
        """129点输入逐块关闭，始终只持一个前瞻，不随已交付块数保留轴或登记。

        参数: 无。返回: None。异常: 同时前瞻/输出或账本随历史块增长断言失败。
        """
        rows = {'table': tuple(MemoryRow(index, {'raw.a': index}, index) for index in range(129))}
        fixture = self.fixture(rows_by_source=rows, domain=(0, 128))
        owner = self.owner(fixture, CalculationDefinition('many', 'integral', Interval(0, 128)), batch_intervals=1)
        count, steady_live = 0, None
        for block in owner:
            self.assertEqual(len(block.series.times_ns), 2)
            self.assertEqual(len(owner._results), 1)
            self.assertLessEqual(len(owner._replay._results), 1)
            block.close()
            self.assertEqual(len(owner._results), 0)
            if count > 2:
                live = fixture.budget.ram_bytes
                # EOF读者或末点前瞻真实释放可降低账本；只禁止随交付数增长。
                steady_live = live if steady_live is None else steady_live
                self.assertLess(live - steady_live, 4096)
            count += 1
        self.assertEqual(count, 128)

    def test_mean_time_and_large_absolute_ns_use_only_positive_intervals(self):
        """大绝对时间仍按整数小差结算，time_weighted_mean依正区间而非点或样本数量。

        参数: 无。返回: None。异常: float绝对坐标失真或边界重复面积断言失败。
        """
        start = INT64_MAX - 8
        definition = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20)
        rows = {'table': (MemoryRow(start, {'raw.a': 1}, 0), MemoryRow(start + 5, {'raw.a': 2}, 1))}
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(definitions=(definition,), rows_by_source=rows, domain=(start, INT64_MAX))
            spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(start + 2, start + 7))
            result = self.compute_blocks(self.owner(fixture, spec, backend=backend, batch_intervals=1), spec, backend)
            mean = sum(value.value * value.selected_duration_ns for _, value in result) / 5
            self.assertEqual(mean, 1.4)
            self.assertEqual(sum(value.selected_duration_ns for _, value in result), 5)

    def test_multisource_atomic_boundaries_preserve_all_dependency_refs(self):
        """不同来源的更新及TTL共用准确轴，块切分不改联合表达式和原字段关联。

        参数: 无。返回: None。异常: 原子轴、面积或全依赖来源丢失断言失败。
        """
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 3),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 20))
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1)),
                'other': (MemoryRow(0, {'raw.b': 10}, 0), MemoryRow(4, {'raw.b': 20}, 1))}
        for backend in ('reference', 'numpy'):
            for count in (1, 2, 7):
                fixture = self.fixture(definitions=definitions, rows_by_source=rows, texts=('a + b',), size=count)
                spec = CalculationDefinition('joint', 'integral', Interval(2, 7))
                result = self.compute_blocks(self.owner(fixture, spec, backend=backend, batch_intervals=count), spec, backend)
                self.assertAlmostEqual(sum(value.value for _, value in result if value.value is not None), 55e-9, places=20)
                self.assertEqual(sum(value.selected_duration_ns for _, value in result), 3)
                self.assertEqual(sum(value.valid_sample_count for _, value in result), 1)
                self.assertTrue(all({ref.source_name for ref in value.source_refs} == {'table', 'other'} for _, value in result))
