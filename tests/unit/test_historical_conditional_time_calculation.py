"""用真实封存历史验收四个条件时间指标及有限两遍均值。

memory/CSV只由原工厂读取一次；新owner只回读已解码的新历史，不重扫原来源。
明确T/F/U区间、真实值更新及手算权重提供真值，两后端不互相充当参考答案。
均值第一遍事实必须持续计费，第二遍覆盖和来源一致后才能开放最终结果。
预算、构造、分配和取消故障覆盖自有资源恢复；原历史、上下文和绑定始终借用。
文件仅写新项目work，全部资源由测试与原工厂分别关闭并核对RAM0。
"""

# 以模块别名复用工厂和注入助手，避免重复发现已有测试类。
import unittest
from unittest.mock import patch
import test_historical_conditional_blocks as real_history
import test_historical_conditional_integral as integral_tests
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution import historical_conditional_time_calculation as module
from chronaxis.execution.historical_conditional_time_calculation import HistoricalConditionalTimeCalculation
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.calculation_blocks import CalculationBlock
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


class HistoricalConditionalTimeCalculationTests(unittest.TestCase):
    """新owner拥有联合块源；关闭后借用原历史和state继续开放且账本恢复原基线。"""

    def prepare(self, operation='time_weighted_mean', *, spec=None, backend='numpy', kind='memory', size=1, **kwargs):
        """构造实际历史及时间分析，登记与原工厂分开的清理责任。

        参数: operation/spec指定请求；backend/kind/size实际配置；kwargs传入真实工厂。
        返回: (fixture,owner,baseline)。异常: 实际来源或构造错误传播。
        """
        factory = real_history.HistoricalConditionalBlocksTests('runTest')
        self.addCleanup(self.cleanup_factory, factory)
        fixture = factory.fixture(backend=backend, kind=kind, size=size, **kwargs)
        baseline = fixture.budget.ram_bytes
        spec = CalculationDefinition('stat', operation, fixture.domain) if spec is None else spec
        owner = self.make_owner(fixture, spec, backend, size)
        return fixture, owner, baseline

    def cleanup_factory(self, factory):
        """核对原工厂清理。参数: 真实工厂。返回: None。异常: 最终RAM0断言失败。"""
        self.assertTrue(factory.doCleanups())

    def make_owner(self, fixture, spec, backend='numpy', size=1):
        """创建实际时间owner并注册关闭，异常时由生产恢复句柄处理。

        参数: fixture真实输入；spec/backend/size原配置。返回: 新owner。异常: 原构造错误。
        """
        owner = HistoricalConditionalTimeCalculation(fixture.history, fixture.holds._context,
            fixture.lease.bindings, fixture.compiled[0], spec, fixture.compiled[1],
            backend=backend, batch_intervals=size)
        self.addCleanup(owner.close)
        return owner

    def consume(self, owner):
        """每次只推进一个有限块，等待生产完整分类。

        参数: 实际owner。返回: 最终CalculationResult借用引用。异常: 原推进错误。
        """
        while owner.step():
            pass  # 不保存时间轴、候选数组或每块均值，真实两遍由owner管理。
        self.assertTrue(owner.finished)
        self.assertFalse(owner.step())
        return owner.result

    def close_and_check(self, fixture, owner, baseline):
        """关闭全部自有状态，借用历史保持开放，金额恢复fixture基线。

        参数: 实际资源及分析前金额。返回: None。异常: 所有权或账本不符。
        """
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertFalse(fixture.history.closed)
        self.assertEqual(fixture.state.revision, 0)
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def cancel_at(self, original, **kwargs):
        """复用已验证的真实账本前后一次故障助手，不新增测试类发现。

        参数: 原账本方法及call/target/after/exception配置。返回: 注入函数。异常: 原助手错误。
        """
        return integral_tests.HistoricalConditionalIntegralTests('runTest').cancel_at(original, **kwargs)

    def long_fixture(self, values, *, backend='numpy', kind='memory', size=1, unit='W', dtype=D.FLOAT64, operation='time_weighted_mean', output=None):
        """构造每值保持一秒、外条件全TRUE的真实输入，不预计算被测均值。

        参数: values手算输入及真实dtype/单位/配置。返回: prepare三元组。异常: 原工厂错误。
        """
        end = len(values) * 1_000_000_000
        definitions = (SignalDefinition('a', 'table', 'raw.a', dtype, unit, end + 1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', end + 1))
        rows = {'table': tuple(MemoryRow(index * 1_000_000_000, {'raw.a': value}, index)
                              for index, value in enumerate(tuple(values) + (values[-1],))),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(end, {'raw.b': 0}, 1))}
        return self.prepare(backend=backend, kind=kind, size=size,
            spec=CalculationDefinition('stat', operation, Interval(0, end), output_unit=output),
            domain=(0, end), definitions=definitions, rows_by_source=rows)

    def test_real_sources_backends_and_splits_keep_four_operator_hand_truth_without_rescan(self):
        """4W与T/F/U/T各1s得极值/均值4，BOOL主值TRUE得duration2s，事实4/3/2s样本1。

        参数: 无。返回: None。异常: 后端/切分改变手算或均值二遍重新扫描原adapter。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    for operation in ('min_time', 'max_time', 'time_weighted_mean', 'duration'):
                        with self.subTest(kind=kind, backend=backend, size=size, operation=operation):
                            kwargs = {}
                            if operation == 'duration':
                                # 原CSV工厂用str写原值，不为raw BOOL生成小写文本；比较树仍提供真实BOOL分析值。
                                kwargs['texts'] = ('a > 0', 'b > 0')
                            fixture, owner, baseline = self.prepare(operation, backend=backend, kind=kind, size=size, **kwargs)
                            with patch.object(BudgetedMemorySourceAdapter, 'iter_batches', side_effect=AssertionError('memory-rescan')) as memory_scan:
                                with patch.object(BudgetedSignalCSVSourceAdapter, 'iter_batches', side_effect=AssertionError('csv-rescan')) as csv_scan:
                                    result = self.consume(owner)
                                    memory_scan.assert_not_called()
                                    csv_scan.assert_not_called()
                            self.assertEqual((result.value, result.unit, result.status),
                                (2., 's', 'partial') if operation == 'duration' else (4., 'W', 'partial'))
                            self.assertEqual((result.value_valid_duration_ns, result.condition_known_duration_ns,
                                result.selected_duration_ns, result.valid_sample_count), (4_000_000_000, 3_000_000_000, 2_000_000_000, 1))
                            self.assertEqual(result.condition_unknown_ranges, (Interval(2_000_000_000, 3_000_000_000),))
                            self.assertEqual(result.binding_identity, fixture.compiled[0].identity)
                            self.assertEqual(owner._second_pass, operation == 'time_weighted_mean')
                            if kind == 'csv':
                                self.assertTrue(any(isinstance(ref, CSVSourceRef) and ref.field == 'raw.b'
                                    and ref.value_text == '' and ref.line_number >= 2 and ref.path for ref in result.source_refs))
                            self.close_and_check(fixture, owner, baseline)

    def test_main_bool_false_is_valid_zero_and_outer_false_is_empty_selection(self):
        """外TRUE且主BOOL全FALSE是有效0/ok；外全FALSE由空选择证明0时长或None极值。

        参数: 无。返回: None。异常: 两种FALSE证据或无效值诊断被混同。
        """
        end = 4_000_000_000
        for backend in ('reference', 'numpy'):
            fixture, owner, baseline = self.long_fixture((False,) * 4, backend=backend, dtype=D.BOOL, unit='1', operation='duration')
            result = self.consume(owner)
            self.assertEqual((result.value, result.status, result.reason, result.selected_duration_ns, result.valid_sample_count),
                             (0., 'complete', 'ok', 0, 0))
            self.assertEqual(result.value_valid_duration_ns, end)
            self.close_and_check(fixture, owner, baseline)
            for operation in ('min_time', 'max_time', 'time_weighted_mean', 'duration'):
                dtype, unit = (D.BOOL, '1') if operation == 'duration' else (D.FLOAT64, 'W')
                definitions = (SignalDefinition('a', 'table', 'raw.a', dtype, unit, end+1),
                               SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', end+1))
                rows = {'table': (MemoryRow(0, {'raw.a': None}, 0), MemoryRow(end, {'raw.a': None}, 1)),
                        'other': (MemoryRow(0, {'raw.b': 0}, 0), MemoryRow(end, {'raw.b': 0}, 1))}
                fixture, owner, baseline = self.prepare(operation, backend=backend, definitions=definitions, rows_by_source=rows)
                result = self.consume(owner)
                self.assertEqual((result.value, result.status, result.reason),
                                 (0. if operation == 'duration' else None, 'complete', 'empty_selection'))
                self.assertEqual(result.value_unknown_ranges, (Interval(0, end),))
                self.assertEqual((result.condition_known_duration_ns, result.selected_duration_ns), (end, 0))
                self.close_and_check(fixture, owner, baseline)

    def test_unknown_invalid_point_no_observation_and_eof_clip_keep_null_evidence(self):
        """均值无TRUE有效证据、点请求、域外及截断FALSE都不得返回正常0。

        参数: 无。返回: None。异常: 空选择证明被扩大或观测外推。
        """
        end = 4_000_000_000
        cases = ((4, None, Interval(0, end), 'unknown_selection'),
                 (None, 1, Interval(0, end), 'no_valid_selected_data'),
                 (4, 0, Interval(1, 1), 'zero_length_window'),
                 (4, 0, Interval(end+1, end+2), 'no_observation'),
                 (4, 0, Interval(0, end+1_000_000_000), 'no_valid_selected_data'))
        for backend in ('reference', 'numpy'):
            for value, condition, window, reason in cases:
                rows = {'table': (MemoryRow(0, {'raw.a': value}, 0), MemoryRow(end, {'raw.a': value}, 1)),
                        'other': (MemoryRow(0, {'raw.b': condition}, 0), MemoryRow(end, {'raw.b': condition}, 1))}
                fixture, owner, baseline = self.prepare(backend=backend, spec=CalculationDefinition('stat', 'time_weighted_mean', window), rows_by_source=rows)
                result = self.consume(owner)
                self.assertIsNone(result.value)
                self.assertEqual(result.reason, reason)
                self.assertFalse(owner._second_pass)
                self.close_and_check(fixture, owner, baseline)

    def test_strict_minimum_coverage_and_request_scope_preserve_facts(self):
        """部分条件report保留4W而strict删值；最低门槛仅标覆盖，原event请求保留。

        参数: 无。返回: None。异常: 策略改变实际事实或请求被裁剪改写。
        """
        for backend in ('reference', 'numpy'):
            for policy in ('report', 'strict'):
                spec = CalculationDefinition('stat', 'time_weighted_mean', Interval(0, 5_000_000_000), policy,
                                  minimum_coverage=.9, scope='event')
                fixture, owner, baseline = self.prepare(backend=backend, spec=spec)
                result = self.consume(owner)
                self.assertIs(result.spec, spec)
                self.assertEqual(result.value, 4. if policy == 'report' else None)
                self.assertEqual((result.value_coverage, result.condition_coverage, result.requested_coverage), (1., .75, .8))
                self.assertEqual(result.coverage_status, 'indeterminate')
                self.assertEqual(result.status, 'partial' if policy == 'report' else 'indeterminate')
                self.close_and_check(fixture, owner, baseline)

    def test_condition_ttl_and_simultaneous_value_update_keep_mean_denominator_and_samples(self):
        """T/U/T/U只选4W与8W各1秒，均值6W且样本2；裁剪继承值样本0。

        参数: 无。返回: None。异常: 条件/TTL边界被当数值更新或二遍分母不符。
        """
        end = 4_000_000_000
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', end+1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 1_000_000_000))
        rows = {'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(2_000_000_000, {'raw.a': 8}, 1), MemoryRow(end, {'raw.a': 0}, 2)),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(2_000_000_000, {'raw.b': 1}, 1), MemoryRow(end, {'raw.b': 0}, 2))}
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                fixture, owner, baseline = self.prepare(backend=backend, size=size, definitions=definitions, rows_by_source=rows)
                result = self.consume(owner)
                self.assertEqual((result.value, result.selected_duration_ns, result.valid_sample_count), (6., 2_000_000_000, 2))
                self.assertEqual(result.condition_unknown_ranges, (Interval(1_000_000_000, 2_000_000_000), Interval(3_000_000_000, end)))
                self.close_and_check(fixture, owner, baseline)
            fixture, owner, baseline = self.prepare(backend=backend, spec=CalculationDefinition('stat', 'time_weighted_mean', Interval(500_000_000, 2_500_000_000)))
            self.assertEqual((self.consume(owner).value, owner.result.valid_sample_count), (4., 0))
            self.close_and_check(fixture, owner, baseline)

    def test_uint64_extrema_remain_exact_while_mean_conversion_loss_is_unknown(self):
        """uint64两极值保留原整数；均值无法精确转float时保留精度未知，不启动二遍。

        参数: 无。返回: None。异常: 偷转float或丢失原精度诊断。
        """
        for backend in ('reference', 'numpy'):
            for operation, expected in (('min_time', 2**64-3), ('max_time', 2**64-1), ('time_weighted_mean', None)):
                fixture, owner, baseline = self.long_fixture((2**64-1, 2**64-3), backend=backend, unit='1', dtype=D.UINT64, operation=operation)
                result = self.consume(owner)
                self.assertEqual(result.value, expected)
                if operation == 'time_weighted_mean':
                    self.assertEqual(result.value_valid_duration_ns, 0)
                    self.assertTrue(result.quality & Q.PRECISION_LOSS)
                    self.assertFalse(owner._second_pass)
                else:
                    self.assertIs(type(result.value), int)
                self.close_and_check(fixture, owner, baseline)

    def test_mean_normalizes_weight_before_multiply_and_final_conversion_is_once(self):
        """巨大有限均值不先算溢出面积；最终V转mV失败保留两遍完整输入覆盖。

        参数: 无。返回: None。异常: 权重先乘巨大时长或最终失败改写覆盖。
        """
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                fixture, owner, baseline = self.long_fixture((1e308, 1e308), backend=backend, size=size)
                result = self.consume(owner)
                self.assertEqual((result.value, result.status), (1e308, 'complete'))
                self.close_and_check(fixture, owner, baseline)
            fixture, owner, baseline = self.long_fixture((1e308,), backend=backend, unit='V', output='mV')
            result = self.consume(owner)
            self.assertEqual((result.value, result.reason, result.value_coverage), (None, 'calculation_failed', 1.))
            self.assertTrue(result.quality & Q.NONFINITE)
            self.close_and_check(fixture, owner, baseline)

    def test_two_pass_facts_mismatch_cannot_publish_finite_mean(self):
        """二遍质量事实损坏即使数值有限也不能交付；第一遍借用快照仍由owner计费。

        参数: 无。返回: None。异常: 两遍差异被忽略或失败前缀可读。
        """
        fixture, owner, baseline = self.prepare()
        # 先完整完成第一遍并推进至第二遍最后一块；此时最终EOF比较尚未运行，结果仍不得开放。
        while not owner._second_pass or owner._cursor != owner._actual.end_ns:
            owner.step()
        self.assertIsNotNone(owner._first_facts)
        owner._quality |= Q.NONFINITE  # 只注入私有状态损坏，不改变冻结输入或原来源。
        # 原输入仍相同，只有第二遍事实被破坏；完整比较必须拒绝而非交付有限数值。
        with self.assertRaisesRegex(ValueError, '两遍'):
            owner.step()
        self.assertTrue(owner.failed)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        # 失败状态持有的第一遍快照和第二遍自有层一起关闭，借用历史金额保持。
        self.close_and_check(fixture, owner, baseline)

    def test_two_pass_unknown_ranges_csv_refs_and_final_metadata_are_all_budgeted(self):
        """100个分离条件未知和完整CSV来源两遍保持，最终预约随全部诊断增长。

        参数: 无。返回: None。异常: 诊断截断、事实快照提前免费或最后预算未增长。
        """
        # 原条件每2ns更新、TTL仅1ns；每次有效1ns后有未知1ns，保持100个已知间隔而不能合并填平。
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', 201),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 1))
        rows = {'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(200, {'raw.a': 0}, 1)),
                'other': tuple(MemoryRow(time, {'raw.b': 1}, index) for index, time in enumerate(range(0, 201, 2)))}
        for backend in ('reference', 'numpy'):
            fixture, owner, baseline = self.prepare(backend=backend, kind='csv', size=7, domain=(0, 200), definitions=definitions, rows_by_source=rows)
            # 此正向用例声明256MiB，容纳两遍完整来源/联合回读保守峰值；预算拒绝在独立用例核实。
            fixture.budget.memory_budget_bytes = 256 * 1024 * 1024
            # 第一遍未知和来源快照继续存活；第二遍重复回读同一新历史，直到最终快照预约前。
            while not owner._second_pass or owner._cursor != owner._actual.end_ns:
                owner.step()
            before = fixture.budget.ram_bytes
            self.assertFalse(owner.step())
            # 最后一笔新增金额属于完整快照/分类；必须随100个缺口及全部定位增长。
            self.assertGreater(fixture.budget.ram_bytes-before, 65536+4096*100)
            result = owner.result
            self.assertEqual((result.value, result.value_valid_duration_ns, result.condition_known_duration_ns,
                              result.selected_duration_ns, result.valid_sample_count), (4., 200, 100, 100, 1))
            self.assertEqual(len(result.condition_unknown_ranges), 100)
            self.assertEqual(owner._first_facts.condition_unknown_ranges, result.condition_unknown_ranges)
            # 定位保留CSV子类的路径、行号、原时间和原值，不能只留下通用source_id。
            refs = [ref for ref in result.source_refs if isinstance(ref, CSVSourceRef) and ref.field == 'raw.b']
            self.assertGreaterEqual(len(refs), 100)
            self.assertTrue(all(ref.path and ref.line_number >= 2 and ref.time_text and ref.value_text == '1' for ref in refs))
            self.close_and_check(fixture, owner, baseline)

    def test_workspace_and_final_metadata_fail_before_numeric_kernel_and_snapshot(self):
        """有限块workspace及最终事实容器在数值核/快照前预约，不足不产生半结果。

        参数: 无。返回: None。异常: 越预算执行分配或失败前缀开放。
        """
        fixture, owner, baseline = self.prepare('min_time')
        # next已交付有限块后，本owner第一次_reserve正是含完整来源的核workspace；不套用旧固定金额。
        with patch.object(owner, '_reserve', side_effect=BudgetExceededError('conditional-time-workspace')), patch.object(owner._reducer, 'push') as push:
            with self.assertRaises(BudgetExceededError):
                owner.step()
            push.assert_not_called()
        self.close_and_check(fixture, owner, baseline)
        # 第二个独立owner已交付全部有限块，但还未收到最终EOF；只卡最后事实容器的预约。
        fixture, owner, baseline = self.prepare('min_time')
        while owner._cursor != owner._actual.end_ns:
            owner.step()
        fixture.budget.memory_budget_bytes = fixture.budget.ram_bytes
        # 账本再无可用空间，预约必须先失败，冻结快照分配入口不能被调用。
        with patch.object(owner, '_facts_snapshot') as snapshot:
            with self.assertRaises(BudgetExceededError):
                owner.step()
            snapshot.assert_not_called()
        self.assertTrue(owner.failed)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        # 全部已见事实只是失败前缀；显式关闭归还金额，不能把它们作为成功结果。
        self.close_and_check(fixture, owner, baseline)

    def test_initial_constructor_child_cleanup_preserves_original_and_parent_recovery(self):
        """新联合子构造申请后失败且持续清理取消，原异常附父恢复owner完整归还自有金额。

        参数: 无。返回: None。异常: 原异常替换、子句柄丢失或借用金额损坏。
        """
        fixture, existing, baseline = self.prepare('min_time')
        # 先关闭正常owner而保留原fixture，后续构造失败可直接与原借用金额比较。
        existing.close()
        original = MemoryError('conditional-time-constructor')
        # 父固定费用先申请，第2笔为联合子固定费用；申请成功后故障，父子持续释放取消。
        with patch.object(fixture.budget, 'reserve_ram', self.cancel_at(fixture.budget.reserve_ram,
                call=2, after=True, exception=original)), patch.object(fixture.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-cleanup')):
            with self.assertRaises(MemoryError) as caught:
                self.make_owner(fixture, CalculationDefinition('stat', 'min_time', fixture.domain))
        # 构造没有返回正常owner，必须从同一个原MemoryError取得父恢复句柄再关闭。
        self.assertIs(caught.exception, original)
        recovery = original.historical_conditional_time_calculation_cleanup_owner
        self.addCleanup(recovery.close)
        self.close_and_check(fixture, recovery, baseline)

    def test_second_pass_real_child_constructor_persistent_cleanup_is_recoverable(self):
        """二遍实际子构造失败并持续清理取消时保留原异常与子句柄，均值前缀不开放。

        参数: 无。返回: None。异常: 第一遍关闭误注入或未赋值子owner失去清理入口。
        """
        fixture, owner, baseline = self.prepare()
        # 只消费到第一遍末块，不提前触发换遍，以下单次step才负责快照、旧子关闭与新子构造。
        while owner._cursor != owner._actual.end_ns:
            owner.step()
        original = MemoryError('conditional-time-second-constructor')
        reserve, release = fixture.budget.reserve_ram, fixture.budget.release_ram
        calls, failed = 0, False

        def fail_second_reserve(amount):
            """在快照预约后的新子申请失败。参数: bytes。返回: 原结果。异常: 原构造故障。"""
            nonlocal calls, failed
            calls += 1
            reserve(amount)
            # 本步第1笔是第一遍快照，第2笔是二遍联合子费用；成功后故障留下真实待清理金额。
            if calls == 2:
                failed = True
                raise original

        def fail_cleanup_after_constructor(amount):
            """先允许第一遍真实关闭。参数: bytes。返回: 原结果。异常: 子构造后持续取消。"""
            # 故障前允许旧子正常释放；故障后才持续取消，保证测试真正到达新子构造而非提前失败。
            if failed:
                raise KeyboardInterrupt('second-child-persistent-cleanup')
            return release(amount)

        with patch.object(fixture.budget, 'reserve_ram', fail_second_reserve), patch.object(fixture.budget, 'release_ram', fail_cleanup_after_constructor):
            with self.assertRaises(MemoryError) as caught:
                owner.step()
        # 尚未赋值的新子经公开恢复句柄接管到owner；恢复账本后close负责它，第一遍仍不能发布。
        self.assertIs(caught.exception, original)
        self.assertTrue(owner.failed)
        self.assertIsNotNone(owner._blocks)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        self.close_and_check(fixture, owner, baseline)

    def test_array_failure_and_step_workspace_cancel_keep_owned_cleanup_reachable(self):
        """核分配失败及workspace申请/释放前后取消均封闭前缀，close精确归还自有费用。

        参数: 无。返回: None。异常: 原异常损坏、失败状态漏报或资源不可恢复。
        """
        fixture, owner, baseline = self.prepare('min_time')
        original = MemoryError('conditional-time-array')
        # 第一组只在已经取得块并预约workspace后模拟核分配失败，原异常必须保留。
        with patch.object(owner._reducer, 'push', side_effect=original):
            with self.assertRaises(MemoryError) as caught:
                owner.step()
        self.assertIs(caught.exception, original)
        self.close_and_check(fixture, owner, baseline)
        # 后四组独立检查本层workspace申请/释放的真实动作前后，不能因取消而重复扣账。
        for method in ('_reserve', '_release'):
            for after in (False, True):
                fixture, owner, baseline = self.prepare('min_time')
                actual = getattr(owner, method)
                cancel = self.cancel_at(actual, after=after)

                def cancel_positive(amount):
                    """跳过初次空事实释放。参数: bytes。返回: 原结果。异常: 正workspace动作一次取消。"""
                    # 首块事实旧费用为0；其后第一笔正释放才是本层workspace，所有实际记账仍由owner完成。
                    return cancel(amount) if amount > 0 else actual(amount)

                with patch.object(owner, method, cancel_positive):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.step()
                self.assertTrue(owner.failed)
                # 注入已撤除，关闭负责当前块、联合子及所有本层金额，原历史仍由工厂持有。
                self.close_and_check(fixture, owner, baseline)

    def test_current_block_close_cancel_before_after_retains_owned_handle(self):
        """当前联合块关闭前后取消可重试，父新owner继续拥有子层而原history不被关闭。

        参数: 无。返回: None。异常: 当前句柄或已释放账目损坏。
        """
        for after in (False, True):
            fixture, owner, baseline = self.prepare('min_time')
            original = CalculationBlock.close

            def cancel_close(block):
                """取消块关闭。参数: 实际块。返回: None。异常: 指定时机取消。"""
                if after:
                    original(block)
                raise KeyboardInterrupt('conditional-time-block-close')

            # 关闭前取消保留块；关闭后取消块金额已释放，两种情况均由owner保存句柄并封闭结果。
            with patch.object(CalculationBlock, 'close', cancel_close):
                with self.assertRaises(KeyboardInterrupt):
                    owner.step()
            self.assertTrue(owner.failed)
            self.close_and_check(fixture, owner, baseline)

    def test_final_owner_release_cancel_before_after_preserves_borrowed_history(self):
        """均值完成后最终owner释放前后取消均可收尾，重复close不扣原history费用。

        参数: 无。返回: None。异常: 重复扣账或关闭后结果仍可访问。
        """
        for after in (False, True):
            fixture, owner, baseline = self.prepare()
            self.consume(owner)
            # 两遍已完成且最终结果存在；只在自有子关闭后的父剩余金额动作前后取消。
            with patch.object(fixture.budget, 'release_ram', self.cancel_at(fixture.budget.release_ram,
                    target=owner._held_cost, after=after)):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.close_and_check(fixture, owner, baseline)
            with self.assertRaises(ResultClosedError):
                _ = owner.result
