"""通过真实封存历史验收有限条件积分、完整事实和独立关闭责任。

输入是work中生成的memory/CSV合成原行；原工厂只读取一次，分析只回读新历史。
4W与TRUE/FALSE/UNKNOWN的明确手算、TTL、真实样本和单位转换提供独立真值。
两后端和不同切分均执行实际入口，不以某个被测后端结果作为另一个的预期值。
预算、分配与取消故障只注入新owner；构造原异常、恢复句柄和借用资源必须保留。
测试自己关闭最终owner与借用分块者，原工厂最后核对总RAM为零；不改历史快照。
"""

# 只用模块别名复用真实工厂，避免unittest再次发现被导入的既有测试类。
import unittest
from unittest.mock import patch
import test_historical_conditional_blocks as real_history
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import QualityFlag as Q, SignalDType as D
from chronaxis.execution import historical_conditional_integral as module
from chronaxis.execution.historical_conditional_integral import HistoricalConditionalIntegral
from chronaxis.execution.history import _metadata_bytes
from chronaxis.execution.retained_metadata import retained_metadata_bytes
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.calculation_blocks import CalculationBlock
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


class HistoricalConditionalIntegralTests(unittest.TestCase):
    """用同一真实联合块源核对结果；新分析关闭时不接管源、历史或原state。"""

    def prepare(self, *, backend='numpy', kind='memory', size=1, spec=None,
                partial_limit=4096, **kwargs):
        """登记真实工厂、借用联合块及新分析的独立清理顺序。

        参数: backend/kind/size为真实配置；spec默认全域积分；kwargs传给原工厂。
        返回: (fixture, blocks, owner, fixture_baseline)。异常: 实际构造错误传播。
        """
        helper = real_history.HistoricalConditionalBlocksTests('runTest')
        self.addCleanup(self.assert_helper_closed, helper)
        fixture = helper.fixture(backend=backend, kind=kind, size=size, **kwargs)
        baseline = fixture.budget.ram_bytes
        spec = CalculationDefinition('area', 'integral', fixture.domain) if spec is None else spec
        blocks = helper.owner(fixture, spec, backend=backend, batch_intervals=size)
        owner = HistoricalConditionalIntegral(blocks, fixture.holds._context.domain,
                                              partial_limit=partial_limit)
        self.addCleanup(owner.close)
        return fixture, blocks, owner, baseline

    def assert_helper_closed(self, helper):
        """核对工厂清理及RAM0。参数: 原工厂。返回: None。异常: 清理断言失败。"""
        self.assertTrue(helper.doCleanups())  # 原工厂继续核对借用state/history的关闭。

    def consume(self, owner):
        """只推进生产入口，不保存全部时间轴或面积列。

        参数: owner为新历史积分。返回: 最终CalculationResult借用引用。异常: 原推进错误。
        """
        while owner.step():
            pass  # 一个有限块一次推进，最后EOF分类由生产owner执行。
        self.assertTrue(owner.finished)
        self.assertFalse(owner.step())
        return owner.result

    def close_and_check(self, fixture, blocks, owner, baseline):
        """分别关闭自有分析和借用块源，避免把源的持续费用误报为分析泄漏。

        参数: 三个实际资源及块源构造前的fixture金额。返回: None。异常: 所有权或金额不符。
        """
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertFalse(blocks.closed)
        self.assertFalse(fixture.history.closed)
        self.assertEqual(fixture.state.revision, 0)
        blocks.close()
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def energy_fixture(self, backend, values, *, kind='memory', size=1, unit='W', output='J'):
        """构造全TRUE条件下每个输入值保持一秒的实际信号历史。

        参数: values是手算面积输入；unit/output明确单位；其余为真实配置。
        返回: prepare四元组。异常: 实际工厂错误传播。
        """
        end = len(values) * 1_000_000_000
        rows = tuple(MemoryRow(index * 1_000_000_000, {'raw.a': value}, index)
                     for index, value in enumerate(tuple(values) + (0.0,)))
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, unit, end + 1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', end + 1))
        other = (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(end, {'raw.b': 0}, 1))
        spec = CalculationDefinition('area', 'integral', Interval(0, end), output_unit=output)
        return self.prepare(backend=backend, kind=kind, size=size, spec=spec,
                            domain=(0, end), definitions=definitions,
                            rows_by_source={'table': rows, 'other': other})

    def cancel_at(self, original, *, after=False, call=1, target=None, exception=None):
        """在目标账本动作前或成功后注入一次，其他调用仍执行实际方法。

        参数: original原方法；call匹配次；target可限定金额；exception可固定原异常身份。
        返回: 注入函数。异常: 指定原异常或一次KeyboardInterrupt。
        """
        calls = 0
        error = KeyboardInterrupt('conditional-integral-test') if exception is None else exception

        def invoke(amount):
            """执行一次注入。参数: amount为bytes。返回: 原结果。异常: 指定故障一次。"""
            nonlocal calls
            if target is None or amount == target:
                calls += 1
                if calls == call:
                    if after:
                        original(amount)
                    raise error
            return original(amount)

        return invoke

    def test_real_sources_both_backends_and_splits_match_four_second_hand_truth(self):
        """4W乘T/F/U/T各一秒为8J，完整值4s、已知条件3s、选中2s及真实样本1。

        参数: 无。返回: None。异常: 原来源重扫、切分或后端改变手算事实与完整定位。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        fixture, blocks, owner, baseline = self.prepare(kind=kind, backend=backend, size=size)
                        # 历史已经封存，禁用两个原adapter后仍需成功完成本次积分。
                        with patch.object(BudgetedMemorySourceAdapter, 'iter_batches', side_effect=AssertionError('memory-rescan')) as memory_scan:
                            with patch.object(BudgetedSignalCSVSourceAdapter, 'iter_batches', side_effect=AssertionError('csv-rescan')) as csv_scan:
                                result = self.consume(owner)
                                memory_scan.assert_not_called()
                                csv_scan.assert_not_called()
                        self.assertEqual((result.value, result.unit, result.status, result.reason),
                                         (8.0, 'J', 'partial', 'partial_coverage'))
                        self.assertEqual((result.value_valid_duration_ns, result.condition_known_duration_ns,
                                          result.selected_duration_ns, result.valid_sample_count),
                                         (4_000_000_000, 3_000_000_000, 2_000_000_000, 1))
                        self.assertEqual((result.value_coverage, result.condition_coverage, result.requested_coverage),
                                         (1.0, .75, 1.0))
                        self.assertEqual(result.value_unknown_ranges, ())
                        self.assertEqual(result.condition_unknown_ranges, (Interval(2_000_000_000, 3_000_000_000),))
                        self.assertEqual(result.binding_identity, fixture.compiled[0].identity)
                        if kind == 'csv':
                            missing = [ref for ref in result.source_refs
                                       if isinstance(ref, CSVSourceRef) and ref.field == 'raw.b' and ref.value_text == '']
                            self.assertTrue(missing)
                            self.assertTrue(all(ref.path and ref.line_number >= 2 and ref.time_text for ref in missing))
                        self.close_and_check(fixture, blocks, owner, baseline)

    def test_strict_and_threshold_preserve_distinct_numeric_policies(self):
        """条件覆盖3/4时strict删值，report门槛0.9仅标覆盖不确定且保留8J。

        参数: 无。返回: None。异常: 政策混同或覆盖事实被改写。
        """
        for backend in ('reference', 'numpy'):
            for policy, value, status, reason in (('report', 8., 'partial', 'partial_coverage'),
                                                ('strict', None, 'indeterminate', 'insufficient_coverage')):
                spec = CalculationDefinition('area', 'integral', Interval(0, 4_000_000_000),
                                  policy, 'J', minimum_coverage=.9)
                fixture, blocks, owner, baseline = self.prepare(backend=backend, spec=spec)
                result = self.consume(owner)
                self.assertEqual((result.value, result.status, result.reason), (value, status, reason))
                self.assertEqual(result.coverage_status, 'indeterminate')
                self.assertEqual((result.value_coverage, result.condition_coverage), (1.0, .75))
                self.close_and_check(fixture, blocks, owner, baseline)

    def test_complete_false_proves_zero_even_when_values_are_all_unknown(self):
        """全窗FALSE可证明空选择0J，即使数值全未知；仍完整保留值未知诊断。

        参数: 无。返回: None。异常: UNKNOWN被填零或FALSE证明丢失。
        """
        end = 4_000_000_000
        rows = {'table': (MemoryRow(0, {'raw.a': None}, 0), MemoryRow(end, {'raw.a': None}, 1)),
                'other': (MemoryRow(0, {'raw.b': 0}, 0), MemoryRow(end, {'raw.b': 0}, 1))}
        for backend in ('reference', 'numpy'):
            fixture, blocks, owner, baseline = self.prepare(backend=backend, rows_by_source=rows)
            result = self.consume(owner)
            self.assertEqual((result.value, result.unit, result.status, result.reason), (0., 'J', 'complete', 'empty_selection'))
            self.assertEqual((result.value_valid_duration_ns, result.condition_known_duration_ns,
                              result.selected_duration_ns, result.valid_sample_count), (0, end, 0, 0))
            self.assertEqual(result.value_unknown_ranges, (Interval(0, end),))
            self.assertEqual(result.condition_unknown_ranges, ())
            self.assertNotEqual(result.quality, Q.NONE)
            self.close_and_check(fixture, blocks, owner, baseline)

    def test_unknown_true_invalid_point_no_intersection_and_eof_clip_never_invent_zero(self):
        """没有TRUE有效证据的未知、点、域外和截断FALSE请求均不能借空和返回0。

        参数: 无。返回: None。异常: 无证据被误作完整FALSE证明或外推观测。
        """
        end = 4_000_000_000
        cases = ((4, None, Interval(0, end), 'unknown_selection'),
                 (None, 1, Interval(0, end), 'no_valid_selected_data'),
                 (4, 0, Interval(1_000_000_000, 1_000_000_000), 'zero_length_window'),
                 (4, 0, Interval(end + 1, end + 2), 'no_observation'),
                 (4, 0, Interval(0, end + 1_000_000_000), 'no_valid_selected_data'))
        for backend in ('reference', 'numpy'):
            for value, condition, window, reason in cases:
                with self.subTest(backend=backend, value=value, condition=condition, window=window):
                    rows = {'table': (MemoryRow(0, {'raw.a': value}, 0), MemoryRow(end, {'raw.a': value}, 1)),
                            'other': (MemoryRow(0, {'raw.b': condition}, 0), MemoryRow(end, {'raw.b': condition}, 1))}
                    spec = CalculationDefinition('area', 'integral', window)
                    fixture, blocks, owner, baseline = self.prepare(backend=backend, spec=spec, rows_by_source=rows)
                    result = self.consume(owner)
                    self.assertIsNone(result.value)
                    self.assertEqual(result.reason, reason)
                    if window.end_ns > end and window.start_ns == 0:
                        self.assertEqual(result.actual_window, Interval(0, end))
                        self.assertEqual(result.requested_coverage, .8)
                    self.close_and_check(fixture, blocks, owner, baseline)

    def test_ttl_simultaneous_updates_and_clipped_left_boundary_keep_real_samples(self):
        """条件TTL产生T/U/T/U且同刻值更新仅计两样本；裁剪继承值不新增样本。

        参数: 无。返回: None。异常: TTL/条件边界被计作值样本或样本被漏计。
        """
        end = 4_000_000_000
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', end + 1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 1_000_000_000))
        rows = {'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(2_000_000_000, {'raw.a': 8}, 1), MemoryRow(end, {'raw.a': 0}, 2)),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(2_000_000_000, {'raw.b': 1}, 1), MemoryRow(end, {'raw.b': 0}, 2))}
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                fixture, blocks, owner, baseline = self.prepare(backend=backend, size=size, definitions=definitions, rows_by_source=rows)
                result = self.consume(owner)
                self.assertEqual((result.value, result.condition_known_duration_ns, result.selected_duration_ns,
                                  result.valid_sample_count), (12., 2_000_000_000, 2_000_000_000, 2))
                self.assertEqual(result.condition_unknown_ranges, (Interval(1_000_000_000, 2_000_000_000), Interval(3_000_000_000, end)))
                self.close_and_check(fixture, blocks, owner, baseline)
            # 半秒后开始的窗口继承4W，原0秒更新在窗外；条件更新仍不增加样本。
            spec = CalculationDefinition('area', 'integral', Interval(500_000_000, 2_500_000_000))
            fixture, blocks, owner, baseline = self.prepare(backend=backend, spec=spec)
            self.assertEqual((self.consume(owner).value, owner.result.valid_sample_count), (2., 0))
            self.close_and_check(fixture, blocks, owner, baseline)

    def test_original_order_cancellation_and_single_final_unit_conversion(self):
        """1e16+1-1e16在两后端和任意有限切分保留1，再一次kW转J得1000。

        参数: 无。返回: None。异常: 跨块抵消精度或单位转换次数不符。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    fixture, blocks, owner, baseline = self.energy_fixture(backend, (1e16, 1., -1e16), kind=kind, size=size, unit='kW')
                    result = self.consume(owner)
                    self.assertEqual((result.value, result.unit, result.status, result.valid_sample_count), (1000., 'J', 'complete', 3))
                    self.close_and_check(fixture, blocks, owner, baseline)

    def test_area_failure_only_masks_true_intervals_and_retains_other_usable_area(self):
        """1e308W保持2秒仅在TRUE时面积失效；FALSE/UNKNOWN不做乘法，后段2J仍可用。

        参数: 无。返回: None。异常: 选中掩码或输入面积失效覆盖被误分类。
        """
        end = 3_000_000_000
        rows_a = (MemoryRow(0, {'raw.a': 1e308}, 0), MemoryRow(2_000_000_000, {'raw.a': 2}, 1), MemoryRow(end, {'raw.a': 0}, 2))
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', end + 1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', end + 1))
        for backend in ('reference', 'numpy'):
            for condition in (1, 0, None):
                rows_b = (MemoryRow(0, {'raw.b': condition}, 0), MemoryRow(2_000_000_000, {'raw.b': 1}, 1), MemoryRow(end, {'raw.b': 0}, 2))
                fixture, blocks, owner, baseline = self.prepare(backend=backend, size=7, domain=(0, end),
                    definitions=definitions, rows_by_source={'table': rows_a, 'other': rows_b})
                result = self.consume(owner)
                self.assertEqual((result.value, result.valid_sample_count), (2., 1))
                self.assertEqual(bool(result.quality & Q.NONFINITE), condition == 1)
                self.assertEqual(result.value_valid_duration_ns, 1_000_000_000 if condition == 1 else end)
                self.assertEqual(result.value_unknown_ranges, (Interval(0, 2_000_000_000),) if condition == 1 else ())
                self.assertEqual(result.status, 'complete' if condition == 0 else 'partial')
                self.close_and_check(fixture, blocks, owner, baseline)

    def test_cumulative_overflow_and_final_conversion_failure_keep_input_coverage(self):
        """累计溢出、最终换算溢出及非零下溢均为整窗计算失败，输入覆盖仍为1。

        参数: 无。返回: None。异常: 后项恢复溢出或数值故障改写输入事实。
        """
        cases = (((1e308, 1e308, -1e308), 'W', 'J', Q.NONFINITE),
                 ((1e308,), 'kW', 'J', Q.NONFINITE), ((1e-320,), 'W', 'kWh', Q.PRECISION_LOSS))
        for backend in ('reference', 'numpy'):
            for values, unit, output, quality in cases:
                fixture, blocks, owner, baseline = self.energy_fixture(backend, values, unit=unit, output=output)
                result = self.consume(owner)
                self.assertEqual((result.value, result.status, result.reason), (None, 'indeterminate', 'calculation_failed'))
                self.assertTrue(result.quality & quality)
                self.assertEqual((result.value_coverage, result.condition_coverage, result.requested_coverage), (1., 1., 1.))
                self.close_and_check(fixture, blocks, owner, baseline)

    def test_final_charge_grows_with_all_unknown_ranges_and_complete_csv_refs(self):
        """100段条件TTL未知与全部CSV行定位进入最终预算和结果，不用固定空间截断。

        参数: 无。返回: None。异常: 诊断丢失、来源退化或结果实体/诊断容器空间未增长。
        """
        # 数值4W始终有效；条件每2ns更新且TTL1ns，100个T与100个U交替。
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', 201),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 1))
        rows = {'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(200, {'raw.a': 0}, 1)),
                'other': tuple(MemoryRow(time, {'raw.b': 1}, index) for index, time in enumerate(range(0, 201, 2)))}
        fixture, blocks, owner, baseline = self.prepare(kind='csv', size=7, domain=(0, 200),
                                                       definitions=definitions, rows_by_source=rows)
        while not blocks._done:
            owner.step()
        facts = owner._reduction._facts_owner._state
        expected = 65536 + retained_metadata_bytes(facts) + 4096 * (len(facts.value_unknown_ranges) + len(facts.condition_unknown_ranges))
        before = fixture.budget.ram_bytes
        self.assertFalse(owner.step())
        self.assertEqual(fixture.budget.ram_bytes - before, expected)
        self.assertGreater(expected, 65536 + 4096 * 100)
        result = owner.result
        self.assertEqual((result.value_valid_duration_ns, result.condition_known_duration_ns,
                          result.selected_duration_ns, result.valid_sample_count), (200, 100, 100, 1))
        self.assertEqual(len(result.condition_unknown_ranges), 100)
        self.assertAlmostEqual(result.value, 4e-7, places=20)
        refs = [ref for ref in result.source_refs if isinstance(ref, CSVSourceRef) and ref.field == 'raw.b']
        self.assertGreaterEqual(len(refs), 100)
        self.assertEqual(len({(ref.path, ref.line_number, ref.time_text, ref.value_text) for ref in refs}), len(refs))
        self.close_and_check(fixture, blocks, owner, baseline)

    def test_bad_or_consumed_borrowed_blocks_reject_before_new_budget_and_prefix_result(self):
        """错范围、错输入和已消费块源在新申请前拒绝，未完成分析不开放前缀结果。

        参数: 无。返回: None。异常: 生命周期门槛或借用块源金额不符。
        """
        fixture, blocks, owner, baseline = self.prepare()
        before = fixture.budget.ram_bytes
        with self.assertRaises(ValueError):
            HistoricalConditionalIntegral(blocks, Interval(1, 4_000_000_000))
        with self.assertRaises(TypeError):
            HistoricalConditionalIntegral(object(), fixture.domain)
        self.assertEqual(fixture.budget.ram_bytes, before)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        self.assertTrue(owner.step())
        before = fixture.budget.ram_bytes
        with self.assertRaises(ValueError):
            HistoricalConditionalIntegral(blocks, fixture.domain)
        self.assertEqual(fixture.budget.ram_bytes, before)
        self.close_and_check(fixture, blocks, owner, baseline)

    def test_either_child_closed_failed_or_closing_rejects_before_new_budget(self):
        """两路任一子owner无效时先拒绝，不能读取关闭后已清空的spec或申请新资源。

        参数: 无。返回: None。异常: 错误异常类型、新预算或借用历史责任变化。
        closed通过真实close产生；failed/closing只控制非法生命周期输入，不伪称实际失败复现。
        """
        for index in (0, 1):
            for state in ('closed', 'failed', 'closing'):
                with self.subTest(child=index, state=state):
                    fixture, blocks, existing, baseline = self.prepare()
                    existing.close()  # 只关闭未推进分析，借用的两路仍未消费。
                    child = blocks._blocks[index]
                    attribute = '_failed' if state == 'failed' else '_closing'
                    old_state = getattr(child, attribute)
                    if state == 'closed':
                        child.close()  # 真实关闭清空内部请求，覆盖原AttributeError触发条件。
                    else:
                        setattr(child, attribute, True)  # 只用于检查构造门槛，finally恢复供工厂安全清理。
                    before = fixture.budget.ram_bytes
                    attempted = None
                    try:
                        with self.assertRaises(ValueError):
                            attempted = HistoricalConditionalIntegral(blocks, fixture.domain)
                        self.assertEqual(fixture.budget.ram_bytes, before)
                        self.assertFalse(blocks.closed)
                        self.assertFalse(fixture.history.closed)
                        self.assertEqual(fixture.state.revision, 0)
                    finally:
                        # 回归失败而意外交付owner时仍保留其清理句柄；无效输入字段不带入工厂收尾。
                        if state != 'closed':
                            setattr(child, attribute, old_state)
                        if attempted is not None:
                            attempted.close()
                    self.close_and_check(fixture, blocks, existing, baseline)

    def test_workspace_and_final_metadata_budget_precede_kernel_and_classification(self):
        """面积workspace和EOF元数据分别在面积核与最终分类前预约，失败隐藏前缀。

        参数: 无。返回: None。异常: 预算失败后仍执行核或误关闭借用资源。
        """
        fixture, blocks, owner, baseline = self.prepare()
        original = fixture.budget.reserve_ram

        def reject_workspace(amount):
            """拒绝面积空间。参数: amount为bytes。返回: 原结果。异常: 目标超限。"""
            if amount == 65536 + 1024 * 2:
                raise BudgetExceededError('conditional-area-workspace')
            return original(amount)

        with patch.object(fixture.budget, 'reserve_ram', reject_workspace), patch.object(module, 'compute_conditional_integral_terms_numpy') as kernel:
            with self.assertRaises(BudgetExceededError):
                owner.step()
            kernel.assert_not_called()
        self.assertTrue(owner.failed)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        self.close_and_check(fixture, blocks, owner, baseline)
        fixture, blocks, owner, baseline = self.prepare()
        while not blocks._done:
            owner.step()
        fixture.budget.memory_budget_bytes = fixture.budget.ram_bytes
        with patch.object(module, 'make_conditional_integral_result') as classify:
            with self.assertRaises(BudgetExceededError):
                owner.step()
            classify.assert_not_called()
        self.assertTrue(owner.failed)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        self.close_and_check(fixture, blocks, owner, baseline)

    def test_constructor_nested_reserve_and_persistent_cleanup_keep_original_and_recovery(self):
        """父、归约、事实构造申请前后失败不丢原异常；持续清理失败交出父恢复句柄。

        参数: 无。返回: None。异常: 原异常身份、恢复句柄或借用预算损坏。
        """
        fixture, blocks, existing, baseline = self.prepare()
        existing.close()  # 尚未推进的联合源仍新鲜，可用于以下独立构造故障。
        borrowed = fixture.budget.ram_bytes
        for call in (1, 2, 3):
            for after in (False, True):
                original = MemoryError('conditional-constructor-original')
                with patch.object(fixture.budget, 'reserve_ram', self.cancel_at(fixture.budget.reserve_ram,
                        call=call, after=after, exception=original)):
                    with self.assertRaises(MemoryError) as caught:
                        HistoricalConditionalIntegral(blocks, fixture.domain)
                self.assertIs(caught.exception, original)
                self.assertEqual(fixture.budget.ram_bytes, borrowed)
                self.assertFalse(blocks.closed)
        # 每层子赋值之前均可能出错；持续释放取消必须经父句柄保留已申请的所有层。
        for call in (1, 2, 3):
            original = MemoryError('nested-original')
            with patch.object(fixture.budget, 'reserve_ram', self.cancel_at(fixture.budget.reserve_ram,
                    call=call, after=True, exception=original)), patch.object(
                    fixture.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-cleanup')):
                with self.assertRaises(MemoryError) as caught:
                    HistoricalConditionalIntegral(blocks, fixture.domain)
            self.assertIs(caught.exception, original)
            recovery = original.historical_conditional_integral_cleanup_owner
            self.addCleanup(recovery.close)
            self.assertFalse(recovery.closed)
            recovery.close()
            recovery.close()
            self.assertEqual(fixture.budget.ram_bytes, borrowed)
            self.assertFalse(blocks.closed)
        self.close_and_check(fixture, blocks, existing, baseline)

    def test_area_allocation_and_final_classification_failure_hide_prefix_keep_cleanup(self):
        """面积分配和最终分类的原异常传播；失败仅能关闭并保留借用源。

        参数: 无。返回: None。异常: 原异常被替换、前缀可读或自有句柄不可恢复。
        """
        fixture, blocks, owner, baseline = self.prepare()
        original = MemoryError('conditional-area-array')
        with patch.object(module, 'compute_conditional_integral_terms_numpy', side_effect=original):
            with self.assertRaises(MemoryError) as caught:
                owner.step()
        self.assertIs(caught.exception, original)
        self.assertIsNotNone(owner._current_block)
        with self.assertRaises(RuntimeError):
            owner.step()
        self.close_and_check(fixture, blocks, owner, baseline)
        fixture, blocks, owner, baseline = self.prepare()
        while not blocks._done:
            owner.step()
        original = KeyboardInterrupt('conditional-classification')
        with patch.object(module, 'make_conditional_integral_result', side_effect=original):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.step()
        self.assertIs(caught.exception, original)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        self.close_and_check(fixture, blocks, owner, baseline)

    def test_step_workspace_reserve_release_cancel_before_after_can_close_once(self):
        """面积workspace申请/释放前后取消仍按实际金额关闭，不重复扣账且不交付前缀。

        参数: 无。返回: None。异常: 金额损坏、失败状态漏报或借用资源被关闭。
        """
        for method in ('reserve_ram', 'release_ram'):
            for after in (False, True):
                fixture, blocks, owner, baseline = self.prepare()
                with patch.object(fixture.budget, method, self.cancel_at(getattr(fixture.budget, method),
                        after=after, target=65536 + 1024 * 2)):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.step()
                self.assertTrue(owner.failed)
                with self.assertRaises(RuntimeError):
                    _ = owner.result
                self.close_and_check(fixture, blocks, owner, baseline)

    def test_current_block_close_cancel_before_after_retains_retry_handle(self):
        """当前联合块关闭前后取消不丢句柄，重试只释放自己的块及分析状态。

        参数: 无。返回: None。异常: 恢复句柄丢失或已释放金额被重复归还。
        """
        for after in (False, True):
            fixture, blocks, owner, baseline = self.prepare()
            original = CalculationBlock.close

            def cancel_close(block):
                """取消本步块关闭。参数: 实际块。返回: None。异常: 一次关闭取消。"""
                if after:
                    original(block)
                raise KeyboardInterrupt('conditional-block-close')

            with patch.object(CalculationBlock, 'close', cancel_close):
                with self.assertRaises(KeyboardInterrupt):
                    owner.step()
            self.assertTrue(owner.failed)
            self.close_and_check(fixture, blocks, owner, baseline)

    def test_final_owner_close_cancel_before_after_preserves_borrowed_responsibility(self):
        """最终owner释放前后取消按真实账本重试，借用块源和历史仍由调用方关闭。

        参数: 无。返回: None。异常: 关闭状态、重复扣账或借用责任不符。
        """
        for after in (False, True):
            fixture, blocks, owner, baseline = self.prepare()
            self.consume(owner)
            target = owner._held_cost
            with patch.object(fixture.budget, 'release_ram', self.cancel_at(fixture.budget.release_ram,
                    after=after, target=target)):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.close_and_check(fixture, blocks, owner, baseline)
            with self.assertRaises(ResultClosedError):
                _ = owner.result
