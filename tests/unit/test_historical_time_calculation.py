"""用真实新历史验收有限时间统计的最终结果、两遍均值及资源恢复。

输入为合成memory/CSV真实行和TTL，手算时间权重及未知区间，不以另一后端生成预期。
每个生产step只取有限块，测试可收集小型结果；所有文件仅写work，由工厂最终关闭。
覆盖两后端/切分、整数精度、时间均值全窗分母、BOOL零时长及最终单位故障。
注入资源与第二遍构造失败后，禁止借出前缀结果，恢复close不扣借用历史费用。
"""

# 模块别名复用工厂，避免把其他测试类重复纳入发现。
import unittest
from unittest.mock import patch
import test_calculation_blocks as real_history
import test_window_replay as replay_tests
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.sources.csv_spec import CSVSourceRef
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution import historical_time_calculation as module
from chronaxis.execution.historical_time_calculation import HistoricalTimeCalculation
from chronaxis.results.errors import ResultClosedError, BudgetExceededError


class HistoricalTimeCalculationTests(unittest.TestCase):
    """每个owner与借用工厂分开逆序关闭，原状态始终不因回读改变。"""

    def fixture(self, **kwargs):
        """准备真实封存历史，并在所有新owner之后关闭原工厂。

        参数: kwargs传给原工厂。返回: 真实fixture。异常: 工厂或最终清理断言。
        """
        factory = real_history.CalculationBlocksTests('runTest')
        fixture = factory.fixture(**kwargs)
        self.addCleanup(self.cleanup_factory, factory)
        return fixture

    def cleanup_factory(self, factory):
        """关闭工厂并执行原RAM0检查。

        参数: factory为原测试工厂。返回: None。异常: 清理断言失败。
        """
        self.assertTrue(factory.doCleanups())

    def owner(self, fixture, spec, backend='numpy', size=1):
        """创建时间统计owner并注册独立关闭。

        参数: fixture为真实输入、spec为请求、backend为后端、size为块上限。
        返回: HistoricalTimeCalculation。异常: 实际构造故障传播。
        """
        owner = HistoricalTimeCalculation(fixture.history, fixture.holds._context, fixture.lease.bindings,
                                     fixture.compiled[0], spec, backend=backend, batch_intervals=size)
        self.addCleanup(owner.close)
        return owner

    def consume(self, owner):
        """推进到完整分类，测试不保存各块数组。

        参数: owner为时间统计。返回: CalculationResult。异常: 实际step错误传播。
        """
        while owner.step():
            pass
        return owner.result

    def long_fixture(self, values, *, backend='numpy', kind='memory', unit='1', dtype=D.FLOAT64, size=1):
        """以1秒正区间构造长保持、精度和抵消手算输入。

        参数: values为区间值；其余声明真实后端/来源/单位/dtype/批大小。
        返回: 真实fixture。异常: 原类型或来源校验错误。
        """
        end = len(values) * 1_000_000_000
        rows = tuple(MemoryRow(index * 1_000_000_000, {'raw.a': value}, index)
                     for index, value in enumerate(tuple(values) + (values[-1],)))
        definition = SignalDefinition('a', 'table', 'raw.a', dtype, unit, end + 1)
        return self.fixture(backend=backend, kind=kind, domain=(0, end), definitions=(definition,),
                            rows_by_source={'table': rows}, size=size)

    def test_real_ttl_statistics_match_hand_truth_at_all_splits(self):
        """2—7ns只有1ns的1和2ns的2，极值1/2、时间均值5/3，未知3—5ns。

        参数: 无。返回: None。异常: 切分/来源/后端改变手算事实。
        """
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1), MemoryRow(8, {'raw.a': 2}, 2))}
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    for operation, expected in (('min_time', 1), ('max_time', 2), ('time_weighted_mean', 5/3)):
                        with self.subTest(kind=kind, backend=backend, size=size, operation=operation):
                            fixture = self.fixture(kind=kind, backend=backend, size=size, rows_by_source=rows)
                            baseline = fixture.budget.ram_bytes
                            owner = self.owner(fixture, CalculationDefinition('stat', operation, Interval(2, 7)), backend, size)
                            result = self.consume(owner)
                            self.assertAlmostEqual(result.value, expected, places=14)
                            self.assertEqual((result.status, result.value_valid_duration_ns,
                                              result.selected_duration_ns, result.valid_sample_count), ('partial', 3, 3, 1))
                            self.assertEqual(result.value_unknown_ranges, (Interval(3, 5),))
                            self.assertEqual(result.binding_identity, fixture.compiled[0].identity)
                            if kind == 'csv':
                                self.assertTrue(any(isinstance(ref, CSVSourceRef) for ref in result.source_refs))
                            self.assertEqual(owner._second_pass, operation == 'time_weighted_mean')
                            owner.close()
                            self.assertEqual(fixture.budget.ram_bytes, baseline)
                            self.assertEqual(fixture.state.revision, 0)

    def test_boolean_false_is_valid_zero_duration_and_true_sample_count_is_separate(self):
        """有效FALSE计覆盖，只有TRUE计持续时间与真实样本；全FALSE正常0。

        参数: 无。返回: None。异常: FALSE误判未知或样本重复。
        """
        for backend in ('reference', 'numpy'):
            for expression, expected, samples in (('a > 1', 2e-9, 1), ('a < 0', 0.0, 0)):
                fixture = self.fixture(backend=backend, texts=(expression,), rows_by_source={'table': (
                    MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1), MemoryRow(8, {'raw.a': 2}, 2))})
                result = self.consume(self.owner(fixture, CalculationDefinition('time', 'duration', Interval(2, 7)), backend))
                self.assertEqual((result.value, result.unit, result.valid_sample_count), (expected, 's', samples))
                self.assertEqual((result.value_valid_duration_ns, result.condition_known_duration_ns), (3, 5))
                self.assertEqual(result.status, 'partial')
            # 工厂默认数值树，重新编译BOOL必须采用真实fixture创建而非替换假输出。
            end = 2_000_000_000
            bool_fixture = self.fixture(backend=backend, domain=(0, end), texts=('a > 0',),
                definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', end+1),),
                rows_by_source={'table': (MemoryRow(0, {'raw.a': -1.}, 0), MemoryRow(end, {'raw.a': -1.}, 1))})
            result = self.consume(self.owner(bool_fixture, CalculationDefinition('time', 'duration', Interval(0, end)), backend))
            self.assertEqual((result.value, result.status, result.value_valid_duration_ns), (0.0, 'complete', end))

    def test_strict_threshold_and_eof_scope_preserve_original_request(self):
        """均值部分值受strict控制，最低覆盖只标质量，请求截断不改scope。

        参数: 无。返回: None。异常: 结果政策与事实混同。
        """
        for backend in ('reference', 'numpy'):
            for policy in ('report', 'strict'):
                fixture = self.fixture(backend=backend)
                spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(2, 10), policy, minimum_coverage=0.9, scope='event')
                result = self.consume(self.owner(fixture, spec, backend))
                self.assertIs(result.spec, spec)
                self.assertEqual(result.actual_window, Interval(2, 8))
                self.assertEqual(result.requested_coverage, 0.75)
                self.assertEqual(result.coverage_status, 'indeterminate')
                if policy == 'strict':
                    self.assertIsNone(result.value)
                else:
                    self.assertIsNotNone(result.value)

    def test_empty_point_touch_and_unknown_never_report_normal_zero(self):
        """无交集/零请求/边界相接/全未知保持空结果，均值不启动第二遍。

        参数: 无。返回: None。异常: 空归约冒充正常0。
        """
        for backend in ('reference', 'numpy'):
            for window, reason, rows in ((Interval(9, 10), 'no_observation', None),
                                        (Interval(5, 5), 'zero_length_window', None),
                                        (Interval(8, 10), 'no_observation', None),
                                        (Interval(0, 8), 'no_valid_selected_data', {'table': ()})):
                fixture = self.fixture(backend=backend, rows_by_source=rows)
                owner = self.owner(fixture, CalculationDefinition('mean', 'time_weighted_mean', window), backend)
                result = self.consume(owner)
                self.assertIsNone(result.value)
                self.assertEqual(result.reason, reason)
                self.assertFalse(owner._second_pass)

    def test_uint64_extrema_are_exact_but_mean_precision_loss_remains_unknown(self):
        """未换单位的uint64极值保持整数，不能为均值偷偷转float。

        参数: 无。返回: None。异常: 原整数被截断或精度失败未标未知。
        """
        values = (2**64-1, 2**64-3)
        for backend in ('reference', 'numpy'):
            fixture = self.long_fixture(values, backend=backend, dtype=D.UINT64)
            for operation, expected in (('min_time', values[1]), ('max_time', values[0])):
                result = self.consume(self.owner(fixture, CalculationDefinition('stat', operation, Interval(0, 2_000_000_000)), backend))
                self.assertEqual(result.value, expected)
                self.assertIs(type(result.value), int)
            result = self.consume(self.owner(fixture, CalculationDefinition('stat', 'time_weighted_mean', Interval(0, 2_000_000_000)), backend))
            self.assertIsNone(result.value)
            self.assertEqual(result.value_valid_duration_ns, 0)
            self.assertTrue(result.quality & Q.PRECISION_LOSS)

    def test_time_mean_normalizes_before_multiplication_and_preserves_cancelled_small_term(self):
        """巨大有限均值不先乘纳秒；三项抵消仍保留1/3，不求各块均值。

        参数: 无。返回: None。异常: 中间面积溢出或小项被抹掉。
        """
        for backend in ('reference', 'numpy'):
            for values, expected in (((1e308, 1e308), 1e308), ((1e16, 1., -1e16), 1/3)):
                for size in (1, 2, 7):
                    fixture = self.long_fixture(values, backend=backend, size=size)
                    result = self.consume(self.owner(fixture, CalculationDefinition('mean', 'time_weighted_mean',
                        Interval(0, len(values)*1_000_000_000)), backend, size))
                    self.assertAlmostEqual(result.value / expected, 1.0, places=14)
                    self.assertEqual(result.status, 'complete')

    def test_output_conversion_failure_does_not_change_mean_coverage(self):
        """V到mV的最终溢出是计算失败，第一遍和第二遍的覆盖仍完整。

        参数: 无。返回: None。异常: 换算失败被写成部分未知或正常Inf。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.long_fixture((1e308,), backend=backend, unit='V')
            result = self.consume(self.owner(fixture, CalculationDefinition('mean', 'time_weighted_mean',
                Interval(0, 1_000_000_000), output_unit='mV'), backend))
            self.assertEqual((result.value, result.reason, result.value_coverage), (None, 'calculation_failed', 1.0))
            self.assertTrue(result.quality & Q.NONFINITE)

    def test_second_pass_failure_hides_first_pass_and_closes_own_resources(self):
        """第一遍已完成但第二遍构造失败时，没有可借出的最终均值。

        参数: 无。返回: None。异常: 前缀开放或借用预算受损。
        """
        fixture = self.fixture()
        baseline = fixture.budget.ram_bytes
        owner = self.owner(fixture, CalculationDefinition('mean', 'time_weighted_mean', Interval(2, 7)))
        while owner._cursor != owner._actual.end_ns:
            self.assertTrue(owner.step())
        original = MemoryError('second-pass-constructor')
        with patch.object(owner, '_make_blocks', side_effect=original):
            with self.assertRaises(MemoryError) as caught:
                owner.step()
        self.assertIs(caught.exception, original)
        self.assertTrue(owner.failed)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        owner.close()
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_first_push_and_final_metadata_budget_fail_before_result_is_exposed(self):
        """有限数值分配失败及最终元数据超限都只允许close，不给部分结果。

        参数: 无。返回: None。异常: 前缀结果或泄漏断言失败。
        """
        for final in (False, True):
            fixture = self.fixture()
            baseline = fixture.budget.ram_bytes
            owner = self.owner(fixture, CalculationDefinition('stat', 'min_time', Interval(2, 7)))
            if final:
                while owner._cursor != owner._actual.end_ns:
                    owner.step()
                fault = patch.object(owner, '_reserve', side_effect=BudgetExceededError('final-metadata'))
            else:
                fault = patch.object(owner._reducer, 'push', side_effect=MemoryError('finite-array'))
            with fault, self.assertRaises((MemoryError, BudgetExceededError)):
                owner.step()
            self.assertTrue(owner.failed)
            with self.assertRaises(RuntimeError):
                _ = owner.result
            owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_constructor_reserve_cancel_and_persistent_cleanup_expose_recovery(self):
        """固定申请成功后取消且清理持续失败时，异常持有真实恢复owner。

        参数: 无。返回: None。异常: 构造原异常或自有预算丢失。
        """
        fixture = self.fixture()
        baseline = fixture.budget.ram_bytes
        helper = replay_tests.WindowReplayTests('runTest')
        with patch.object(fixture.budget, 'reserve_ram', helper.cancel_once(fixture.budget.reserve_ram, True)):
            with patch.object(fixture.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-cleanup')):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    self.owner(fixture, CalculationDefinition('stat', 'min_time', Interval(2, 7)))
        recovery = caught.exception.historical_time_calculation_cleanup_owner
        recovery.close()
        self.assertTrue(recovery.closed)
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_owner_release_cancel_before_and_after_can_retry_once(self):
        """关闭前取消保留金额，成功后取消记录关闭，不重复扣借用预算。

        参数: 无。返回: None。异常: 重试或关闭后的输出访问断言失败。
        """
        for after in (False, True):
            fixture = self.fixture()
            baseline = fixture.budget.ram_bytes
            owner = self.owner(fixture, CalculationDefinition('stat', 'max_time', Interval(2, 7)))
            self.consume(owner)
            helper = replay_tests.WindowReplayTests('runTest')
            with patch.object(fixture.budget, 'release_ram', helper.cancel_once(fixture.budget.release_ram, after, owner._held_cost)):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)
            with self.assertRaises(ResultClosedError):
                _ = owner.result

    def test_two_pass_mean_keeps_one_hundred_unknown_ranges_and_full_csv_refs_budgeted(self):
        """100个分离缺口在两遍都完整保留，最终分类预算随真实定位增长。

        参数: 无。返回: None。异常: 诊断截断、两遍分母错或最终元数据未计费。
        """
        for backend in ('reference', 'numpy'):
            definition = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 1)
            rows = tuple(MemoryRow(index*2, {'raw.a': 1.}, index) for index in range(101))
            fixture = self.fixture(backend=backend, kind='csv', domain=(0, 200), size=7,
                definitions=(definition,), rows_by_source={'table': rows})
            owner = self.owner(fixture, CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 200)), backend, 7)
            # 最后一块之后、最终分类之前记录本owner新增预约，而非所有子层总费用。
            while not owner._second_pass or owner._cursor != owner._actual.end_ns:
                self.assertTrue(owner.step())
            cost = 65536 + 16 * module._metadata_bytes((owner._unknown, owner._refs))
            before = fixture.budget.ram_bytes
            self.assertFalse(owner.step())
            self.assertEqual(fixture.budget.ram_bytes-before, cost)
            self.assertGreater(cost, 65536+4096*100)
            result = owner.result
            self.assertEqual((result.value, result.value_valid_duration_ns, result.valid_sample_count), (1., 100, 100))
            self.assertEqual(len(result.value_unknown_ranges), 100)
            self.assertGreaterEqual(len(result.source_refs), 100)
            self.assertEqual(result.value_coverage, 0.5)
            self.assertEqual(owner._first_facts.value_unknown_ranges, result.value_unknown_ranges)

    def test_second_pass_facts_mismatch_cannot_open_result(self):
        """第二遍覆盖/来源事实不同，即使数值有限也不得交付整窗结果。

        参数: 无。返回: None。异常: 忽略真实重放身份差异或漏账。
        """
        fixture = self.fixture()
        baseline = fixture.budget.ram_bytes
        owner = self.owner(fixture, CalculationDefinition('mean', 'time_weighted_mean', Interval(2, 7)))
        while not owner._second_pass or owner._cursor != owner._actual.end_ns:
            self.assertTrue(owner.step())
        # 手工改私有字段只注入损坏，生产并不提供对已冻结事实的修改入口。
        owner._quality |= Q.NONFINITE
        with self.assertRaisesRegex(ValueError, '两遍'):
            owner.step()
        with self.assertRaises(RuntimeError):
            _ = owner.result
        owner.close()
        self.assertEqual(fixture.budget.ram_bytes, baseline)


# 发现或直接执行均保留相同真实断言，不导入额外测试类。
if __name__ == '__main__':
    unittest.main()
