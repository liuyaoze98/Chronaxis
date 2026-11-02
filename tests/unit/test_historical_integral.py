"""验证最终积分分类、真实有限分块接线及借用资源的关闭边界。

手算覆盖与数值作为真值，两个数值后端分别执行原面积核和新归约核。
memory/CSV真实夹具只在work创建合成历史，覆盖TTL、EOF、样本边界和完整来源。
预算在数组/最终分类之前申请，取消时封闭前缀；本owner不关闭借用分块者。
旧回读构造持续清理风险072只作已知边界，不能把本专项写成已修复它。
"""

# 复用工厂模块而不重复收集其测试类，数值真值不由被测后端生成。
from dataclasses import replace
import unittest
from unittest.mock import patch
import test_calculation_blocks as real_history
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.integral_result import make_integral_result
from chronaxis.core.integral_sum import IntegralSumResult
from chronaxis.core.integral_terms import IntegralFacts
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, MemoryRow, SourceRef
from chronaxis.core.types import QualityFlag as Q, SignalDType as D
from chronaxis.execution import historical_integral as module
from chronaxis.execution.historical_integral import HistoricalIntegral
from chronaxis.execution.history import _metadata_bytes
from chronaxis.execution.retained_metadata import retained_metadata_bytes
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


class IntegralResultTests(unittest.TestCase):
    """直接核实冻结分类结果，用明确整数跨度和已换单位的面积作输入。"""

    def inputs(self, *, actual=Interval(0, 10), valid=6, count=2, terms=3,
               unknown=(Interval(2, 6),), value=7.0, policy='report', threshold=0.0):
        """建立明确合成事实与数值，无条件覆盖10ns、有效6ns和未知4ns。

        参数: 覆盖、计数、数值与政策均由测试指定。返回: (facts, number)。
        异常: 冻结模型校验错误传播。
        """
        # 保留真实CSV子类字段，用相同基础来源测试最终模型不会重新造定位。
        spec = CalculationDefinition('area', 'integral', Interval(0, 10), policy, 'J', minimum_coverage=threshold)
        ref = CSVSourceRef('session', 'table', 'raw.a', 'synthetic.csv', 2, '0', '7', False)
        facts = IntegralFacts(spec, actual, valid, count, unknown, Q.STALE, 'W', 'result-test', (ref,))
        return facts, IntegralSumResult(value, 'J', False, Q.NONE, terms)

    def test_report_partial_retains_hand_value_coverage_and_full_csv_identity(self):
        """10ns中6ns有效、4ns未知，report保留7J和0.6覆盖，而非正常完整结果。

        参数: 无。返回: None。异常: 数值、覆盖、状态或完整定位不符。
        """
        facts, number = self.inputs()
        result = make_integral_result(facts, number)
        # 全部关键事实直接按手算断言；面积项3与实际样本2不得互换。
        self.assertEqual((result.value, result.unit, result.status, result.reason), (7.0, 'J', 'partial', 'partial_coverage'))
        self.assertEqual((result.window_duration_ns, result.value_valid_duration_ns, result.condition_known_duration_ns,
                          result.selected_duration_ns, result.valid_sample_count), (10, 6, 10, 6, 2))
        self.assertEqual((result.value_coverage, result.condition_coverage, result.requested_coverage), (0.6, 1.0, 1.0))
        self.assertEqual(result.condition_unknown_ranges, ())
        self.assertEqual(result.value_unknown_ranges, (Interval(2, 6),))
        self.assertEqual(result.quality, Q.STALE)
        self.assertEqual(result.binding_identity, 'result-test')
        self.assertIs(result.source_refs, facts.source_refs)
        self.assertIs(result.spec, facts.spec)

    def test_strict_and_minimum_threshold_keep_distinct_policies(self):
        """strict删除部分数值，最低覆盖门槛只标质量，不删除report值。

        参数: 无。返回: None。异常: 最低门槛改变数值政策或strict不保留事实。
        """
        for policy, expected in (('report', 7.0), ('strict', None)):
            facts, number = self.inputs(policy=policy, threshold=0.8)
            result = make_integral_result(facts, number)
            self.assertEqual(result.value, expected)
            self.assertEqual(result.coverage_status, 'indeterminate')
            self.assertEqual(result.value_valid_duration_ns, 6)
            self.assertEqual(result.status, 'partial' if policy == 'report' else 'indeterminate')
            self.assertEqual(result.reason, 'partial_coverage' if policy == 'report' else 'insufficient_coverage')

    def test_request_truncation_preserves_original_scope_and_requested_coverage(self):
        """观测仅2—8ns但请求0—10ns，实际数据完整仍属于请求的部分结果。

        参数: 无。返回: None。异常: 请求被改写或截断被标完整。
        """
        facts, number = self.inputs(actual=Interval(2, 8), valid=6, unknown=())
        facts = replace(facts, spec=replace(facts.spec, scope='event', minimum_coverage=0.8))
        result = make_integral_result(facts, number)
        self.assertEqual(result.requested_coverage, 0.6)
        self.assertEqual(result.value_coverage, 1.0)
        self.assertEqual(result.status, 'partial')
        self.assertEqual(result.coverage_status, 'indeterminate')
        self.assertEqual(result.spec.scope, 'event')
        self.assertEqual(result.spec.window, Interval(0, 10))

    def test_complete_valid_zero_differs_from_all_unknown(self):
        """有效零面积是完整0J，全部未知是None，不能使用空求和的零。

        参数: 无。返回: None。异常: 两种证据被混同。
        """
        facts, number = self.inputs(valid=10, unknown=(), value=0.0)
        result = make_integral_result(facts, number)
        self.assertEqual((result.value, result.status, result.reason), (0.0, 'complete', 'ok'))
        facts, number = self.inputs(valid=0, count=0, terms=0, unknown=(Interval(0, 10),), value=None)
        result = make_integral_result(facts, number)
        self.assertEqual((result.value, result.status, result.reason), (None, 'indeterminate', 'no_valid_selected_data'))
        self.assertEqual(result.value_coverage, 0.0)

    def test_zero_request_no_intersection_and_touching_point_keep_reasons(self):
        """零请求、无交集及端点相接保留各自真实范围和空值原因。

        参数: 无。返回: None。异常: 观测被外推或零分母未保留None。
        """
        number = IntegralSumResult(None, 'J', False, Q.NONE, 0)
        for window, actual, reason in ((Interval(2, 2), Interval(2, 2), 'zero_length_window'),
                                       (Interval(0, 10), None, 'no_observation'),
                                       (Interval(0, 10), Interval(10, 10), 'no_observation')):
            facts = IntegralFacts(CalculationDefinition('area', 'integral', window), actual, 0, 0, (), Q.NONE,
                                  'W', 'point-test', ())
            result = make_integral_result(facts, number)
            self.assertEqual(result.reason, reason)
            self.assertEqual(result.actual_window, actual)
            self.assertIsNone(result.value)
            self.assertIsNone(result.value_coverage)

    def test_only_number_failure_is_total_calculation_failure(self):
        """输入面积曾无效可报告部分值，归约/转换失败才使最终值不可用。

        参数: 无。返回: None。异常: 输入质量和整窗数值失败混同。
        """
        facts, number = self.inputs()
        facts = replace(facts, quality=Q.NONFINITE)
        result = make_integral_result(facts, number)
        self.assertEqual((result.value, result.reason), (7.0, 'partial_coverage'))
        number = IntegralSumResult(None, 'J', True, Q.PRECISION_LOSS, 3)
        result = make_integral_result(facts, number)
        self.assertEqual((result.value, result.status, result.reason), (None, 'indeterminate', 'calculation_failed'))
        self.assertEqual(result.quality, Q.NONFINITE | Q.PRECISION_LOSS)
        self.assertEqual(result.value_valid_duration_ns, 6)

    def test_bad_units_counts_bounds_and_partition_are_rejected(self):
        """不能用不匹配单位、越界范围或不完整划分制造可信最终结果。

        参数: 无。返回: None。异常: 矛盾输入被接受。
        """
        facts, number = self.inputs()
        bad = ((facts, replace(number, unit='Wh')),
               (replace(facts, valid_sample_count=4), number),
               (replace(facts, actual_window=Interval(-1, 10)), number),
               (replace(facts, value_unknown_ranges=(Interval(2, 5),)), number),
               (replace(facts, value_unknown_ranges=(Interval(2, 4), Interval(3, 5))), number),
               (replace(facts, value_unknown_ranges=(Interval(4, 6), Interval(2, 4))), number),
               (facts, replace(number, valid_term_count=7)),
               (replace(facts, valid_sample_count=0), IntegralSumResult(None, 'J', False, Q.NONE, 0)))
        for pair in bad:
            with self.assertRaises(ValueError):
                make_integral_result(*pair)
        for pair in ((object(), number), (facts, object())):
            with self.assertRaises(TypeError):
                make_integral_result(*pair)


class HistoricalIntegralTests(unittest.TestCase):
    """新owner与借用分块者分别关闭，完整工厂最后核对RAM0。"""

    def prepare(self, *, backend='numpy', spec=None, size=1, partial_limit=4096, **kwargs):
        """准备真实已封存历史、未消费分块者和新分析，分别登记关闭。

        参数: backend/size/limit 为明确配置；kwargs 传真实原工厂；spec 默认2—7ns积分。
        返回: (fixture, blocks, owner)。异常: 真实构造错误传播。
        """
        helper = real_history.CalculationBlocksTests('runTest')
        self.addCleanup(self.assert_helper_closed, helper)
        fixture = helper.fixture(backend=backend, size=size, **kwargs)
        spec = CalculationDefinition('area', 'integral', Interval(2, 7)) if spec is None else spec
        blocks = helper.owner(fixture, spec, backend=backend, batch_intervals=size)
        owner = HistoricalIntegral(blocks, fixture.holds._context.domain, partial_limit=partial_limit)
        self.addCleanup(owner.close)
        return fixture, blocks, owner

    def assert_helper_closed(self, helper):
        """核对真实工厂清理。参数: helper 为原夹具。返回: None。异常: 清理失败断言。"""
        self.assertTrue(helper.doCleanups())  # 工厂内部继续检查最终RAM0。

    def consume(self, owner):
        """逐步消费有限块，不收集全轴或面积。

        参数: owner 为历史积分。返回: 完成后的CalculationResult借用引用。异常: 真实推进错误。
        """
        while owner.step():
            pass  # 状态推进由生产step完成，测试只等待完整EOF分类。
        return owner.result

    def cancel_at(self, original, *, after=False, call=1, target=None):
        """在指定动作前或成功后取消一次，其余调用执行真实账本。

        参数: original 原方法；call 为匹配次；target 可过滤金额；after 为时机。
        返回: 注入函数。异常: 目标动作一次KeyboardInterrupt。
        """
        calls = 0

        def invoke(amount):
            """执行一次取消。参数: amount 为 bytes。返回: 原结果。异常: 一次取消。"""
            nonlocal calls
            if target is None or amount == target:
                calls += 1
                if calls == call:
                    if after:
                        original(amount)
                    raise KeyboardInterrupt('historical-integral-test')
            return original(amount)

        return invoke

    def energy_fixture(self, backend, kind, areas, *, unit='W', output='J', size=1):
        """用1秒正区间的真实信号更新建立抵消/溢出样例。

        参数: areas 是输入值序列，单位unit；output为最终单位，size为切分。
        返回: fixture/blocks/owner。异常: 原工厂错误。
        """
        # 末点0只给EOF边界，不贡献面积；TTL覆盖整个有限合成域。
        end = len(areas) * 1_000_000_000
        rows = tuple(MemoryRow(index * 1_000_000_000, {'raw.a': value}, index)
                     for index, value in enumerate(tuple(areas) + (0.0,)))
        definition = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, unit, end + 1)
        spec = CalculationDefinition('area', 'integral', Interval(0, end), output_unit=output)
        return self.prepare(backend=backend, kind=kind, spec=spec, size=size, domain=(0, end),
                            definitions=(definition,), rows_by_source={'table': rows})

    def test_memory_csv_all_splits_match_hand_ttl_truth_and_keep_sources(self):
        """真实0/5/8ns更新在2—7ns得到5e-9s、有效3ns、样本1和未知3—5ns。

        参数: 无。返回: None。异常: 切分/后端改变数值、政策、来源或原状态。
        """
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1), MemoryRow(8, {'raw.a': 2}, 2))}
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        fixture, blocks, owner = self.prepare(backend=backend, kind=kind, size=size, rows_by_source=rows)
                        result = self.consume(owner)
                        self.assertEqual((result.value, result.status, result.reason), (5e-9, 'partial', 'partial_coverage'))
                        self.assertEqual((result.window_duration_ns, result.value_valid_duration_ns,
                                          result.condition_known_duration_ns, result.selected_duration_ns, result.valid_sample_count),
                                         (5, 3, 5, 3, 1))
                        self.assertEqual((result.value_coverage, result.condition_coverage, result.requested_coverage), (0.6, 1.0, 1.0))
                        self.assertEqual(result.value_unknown_ranges, (Interval(3, 5),))
                        self.assertEqual(result.binding_identity, fixture.compiled[0].identity)
                        if kind == 'csv':
                            self.assertTrue(any(isinstance(ref, CSVSourceRef) for ref in result.source_refs))
                        self.assertEqual(fixture.state.revision, 0)
                        self.assertFalse(owner.step())
                        owner.close()
                        self.assertFalse(blocks.closed)  # 借用分块者须由原调用方另行关闭。

    def test_real_strict_and_threshold_do_not_change_coverage_facts(self):
        """同一真实TTL缺口下strict为空，report保留值；高门槛只标覆盖不足。

        参数: 无。返回: None。异常: 政策或事实被混同。
        """
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1), MemoryRow(8, {'raw.a': 2}, 2))}
        for backend in ('reference', 'numpy'):
            for policy in ('report', 'strict'):
                spec = CalculationDefinition('area', 'integral', Interval(2, 7), policy, minimum_coverage=0.8)
                _, _, owner = self.prepare(backend=backend, spec=spec, rows_by_source=rows)
                result = self.consume(owner)
                self.assertEqual(result.value, 5e-9 if policy == 'report' else None)
                self.assertEqual(result.coverage_status, 'indeterminate')
                self.assertEqual((result.value_valid_duration_ns, result.valid_sample_count), (3, 1))

    def test_request_beyond_observation_keeps_truncation_and_event_scope(self):
        """请求2—10ns而真实域止于8ns，报告7e-9s和0.75请求覆盖，不重写请求。

        参数: 无。返回: None。异常: 截断、未知范围或scope改变。
        """
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1), MemoryRow(8, {'raw.a': 2}, 2))}
        spec = CalculationDefinition('area', 'integral', Interval(2, 10), scope='event')
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                _, _, owner = self.prepare(backend=backend, kind=kind, spec=spec, rows_by_source=rows)
                result = self.consume(owner)
                self.assertEqual(result.value, 7e-9)
                self.assertEqual(result.actual_window, Interval(2, 8))
                self.assertEqual(result.requested_coverage, 0.75)
                self.assertEqual(result.status, 'partial')
                self.assertIs(result.spec, spec)

    def test_no_intersection_point_touch_and_all_unknown_keep_null_reasons(self):
        """空交集、零请求、相接端点及空来源保留真实范围，不产生正常零。

        参数: 无。返回: None。异常: 空数据或端点被补为面积。
        """
        for backend in ('reference', 'numpy'):
            for window, reason, actual in ((Interval(9, 10), 'no_observation', None),
                                            (Interval(5, 5), 'zero_length_window', Interval(5, 5)),
                                            (Interval(8, 10), 'no_observation', Interval(8, 8))):
                spec = CalculationDefinition('area', 'integral', window)
                _, _, owner = self.prepare(backend=backend, spec=spec)
                result = self.consume(owner)
                self.assertEqual((result.value, result.reason, result.actual_window), (None, reason, actual))
                self.assertEqual(result.valid_sample_count, 0)
            _, _, owner = self.prepare(backend=backend, rows_by_source={'table': ()})
            result = self.consume(owner)
            self.assertEqual((result.value, result.reason), (None, 'no_valid_selected_data'))
            self.assertEqual(result.value_unknown_ranges, (Interval(2, 7),))

    def test_left_held_value_and_terminal_update_are_not_new_samples(self):
        """1—2ns左端只保持0ns样本，面积1e-9但实际样本数0。

        参数: 无。返回: None。异常: 合成边界或右末点被重复计样本。
        """
        for backend in ('reference', 'numpy'):
            spec = CalculationDefinition('area', 'integral', Interval(1, 2))
            _, _, owner = self.prepare(backend=backend, spec=spec)
            result = self.consume(owner)
            self.assertEqual((result.value, result.valid_sample_count, result.status), (1e-9, 0, 'complete'))

    def test_real_cancellation_registered_conversion_and_zero_all_splits(self):
        """真实1秒分块抵消保留1，kW到J一次乘1000，有效零保持完整0。

        参数: 无。返回: None。异常: 切分丢失低位或重复单位倍率。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    _, _, owner = self.energy_fixture(backend, kind, (1e16, 1.0, -1e16), unit='kW', size=size)
                    result = self.consume(owner)
                    self.assertEqual((result.value, result.unit, result.status, result.valid_sample_count), (1000.0, 'J', 'complete', 3))
                _, _, owner = self.energy_fixture(backend, kind, (0.0, 0.0))
                self.assertEqual((self.consume(owner).value, owner.result.status), (0.0, 'complete'))

    def test_real_intermediate_overflow_and_final_conversion_failures(self):
        """中途溢出、最终换算溢出和非零下溢都交付calculation_failed及完整覆盖。

        参数: 无。返回: None。异常: 溢出被后项恢复或故障丢失覆盖。
        """
        cases = (((1e308, 1e308, -1e308), 'W', 'J', Q.NONFINITE),
                 ((1e308,), 'kW', 'J', Q.NONFINITE), ((1e-320,), 'W', 'kWh', Q.PRECISION_LOSS))
        for backend in ('reference', 'numpy'):
            for areas, unit, output, quality in cases:
                _, _, owner = self.energy_fixture(backend, 'memory', areas, unit=unit, output=output)
                result = self.consume(owner)
                self.assertEqual((result.value, result.status, result.reason), (None, 'indeterminate', 'calculation_failed'))
                self.assertTrue(result.quality & quality)
                self.assertEqual(result.value_coverage, 1.0)

    def test_real_area_product_overflow_preserves_reportable_other_interval(self):
        """真实首段1e308W保持2秒乘积无效，后段2W保持1秒仍报告2J部分值。

        参数: 无。返回: None。异常: 输入面积故障被误作整窗累计失败。
        """
        times = (0, 2_000_000_000, 3_000_000_000)
        rows = tuple(MemoryRow(time, {'raw.a': value}, index)
                     for index, (time, value) in enumerate(zip(times, (1e308, 2.0, 0.0))))
        definition = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', 4_000_000_000)
        spec = CalculationDefinition('area', 'integral', Interval(0, times[-1]), output_unit='J')
        for backend in ('reference', 'numpy'):
            _, _, owner = self.prepare(backend=backend, spec=spec, domain=(0, times[-1]),
                                       definitions=(definition,), rows_by_source={'table': rows})
            result = self.consume(owner)
            self.assertEqual((result.value, result.status, result.reason), (2.0, 'partial', 'partial_coverage'))
            self.assertEqual(result.value_unknown_ranges, (Interval(0, 2_000_000_000),))
            self.assertEqual(result.valid_sample_count, 1)
            self.assertTrue(result.quality & Q.NONFINITE)

    def test_final_metadata_charge_grows_with_disjoint_unknown_ranges_and_csv_refs(self):
        """100个分开的TTL未知区间及CSV行定位都计入实体保留和诊断容器空间，不以固定64KiB冒充。

        参数: 无。返回: None。异常: 诊断截断或预算未随完整元数据增长。
        """
        # 每2ns更新一次且TTL1ns，100个有效1ns与100个未知1ns交替；末点不增加面积。
        rows = tuple(MemoryRow(time, {'raw.a': 1.0}, index) for index, time in enumerate(range(0, 201, 2)))
        definition = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 1)
        spec = CalculationDefinition('area', 'integral', Interval(0, 200))
        fixture, blocks, owner = self.prepare(kind='csv', spec=spec, domain=(0, 200), size=7,
                                             definitions=(definition,), rows_by_source={'table': rows})
        while not blocks._done:
            owner.step()
        # 读取测试中的已累积内部事实仅计算预期费用，不提前开放生产result接口。
        facts = owner._reduction._facts_owner._state
        expected = 65536 + retained_metadata_bytes(facts) + 4096 * len(facts.value_unknown_ranges)
        before = fixture.budget.ram_bytes
        self.assertFalse(owner.step())
        self.assertEqual(fixture.budget.ram_bytes - before, expected)
        self.assertGreater(expected, 65536 + 4096 * 100)
        self.assertEqual((owner.result.value_valid_duration_ns, owner.result.valid_sample_count), (100, 100))
        self.assertEqual(len(owner.result.value_unknown_ranges), 100)
        self.assertEqual(owner.result.value, 100 * 1e-9)
        self.assertGreaterEqual(sum(isinstance(ref, CSVSourceRef) for ref in owner.result.source_refs), 100)

    def test_bad_or_consumed_borrowed_blocks_are_rejected_without_new_budget(self):
        """已消费分块者或错误真实范围不能加入另一次积分，拒绝时不申请新资源。

        参数: 无。返回: None。异常: 状态/范围门槛或预算不符。
        """
        fixture, blocks, owner = self.prepare()
        before = fixture.budget.ram_bytes
        with self.assertRaises(ValueError):
            HistoricalIntegral(blocks, Interval(3, 7))
        self.assertEqual(fixture.budget.ram_bytes, before)
        self.assertTrue(owner.step())
        before = fixture.budget.ram_bytes
        with self.assertRaises(ValueError):
            HistoricalIntegral(blocks, fixture.holds._context.domain)
        self.assertEqual(fixture.budget.ram_bytes, before)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        with self.assertRaises(TypeError):
            HistoricalIntegral(object(), fixture.holds._context.domain)

    def test_workspace_budget_fails_before_area_kernel_and_keeps_borrowed_blocks_open(self):
        """有限面积临时空间不足时不调用面积核，失败owner可关闭且不关闭借用块源。

        参数: 无。返回: None。异常: 越过预算执行核或借用资源误关闭。
        """
        fixture, blocks, owner = self.prepare()
        # 借用分块者先真实交付一块，注入后只让本层额外workspace申请失败。
        original = fixture.budget.reserve_ram

        def reject_workspace(amount):
            """拒绝本层工作空间。参数: amount 为bytes。返回: 原结果。异常: 目标超限。"""
            if amount == 65536 + 1024 * 2:
                raise BudgetExceededError('area-workspace')
            return original(amount)

        with patch.object(fixture.budget, 'reserve_ram', reject_workspace), patch.object(module, 'compute_integral_terms_numpy') as compute:
            with self.assertRaises(BudgetExceededError):
                owner.step()
            compute.assert_not_called()
        self.assertTrue(owner.failed)
        owner.close()
        self.assertFalse(blocks.closed)

    def test_final_metadata_budget_precedes_classification_and_failure_hides_prefix(self):
        """EOF后结果容器预算不足时不执行分类，不借出已累计的前缀。

        参数: 无。返回: None。异常: 分类越过预算或失败结果可读。
        """
        fixture, blocks, owner = self.prepare()
        while not blocks._done:
            self.assertTrue(owner.step())
        fixture.budget.memory_budget_bytes = fixture.budget.ram_bytes
        with patch.object(module, 'make_integral_result') as classify:
            with self.assertRaises(BudgetExceededError):
                owner.step()
            classify.assert_not_called()
        self.assertTrue(owner.failed)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        owner.close()
        self.assertFalse(blocks.closed)

    def test_constructor_parent_child_cancel_and_persistent_cleanup_recovery(self):
        """本层及自有归约构造取消前后恢复，不接管已有blocks构造或关闭。

        参数: 无。返回: None。异常: 清理句柄丢失或借用分块者被关闭。
        """
        fixture, blocks, existing = self.prepare()
        existing.close()  # 未推进的借用blocks仍新鲜，可以用于另一次独立构造。
        baseline = fixture.budget.ram_bytes
        for call in (1, 2, 3):
            for after in (False, True):
                with patch.object(fixture.budget, 'reserve_ram', self.cancel_at(fixture.budget.reserve_ram, call=call, after=after)):
                    with self.assertRaises(KeyboardInterrupt):
                        HistoricalIntegral(blocks, fixture.holds._context.domain)
                self.assertEqual(fixture.budget.ram_bytes, baseline)
                self.assertFalse(blocks.closed)
        # 两层清理均持续失败，恢复入口保留父owner及自有归约句柄。
        with patch.object(fixture.budget, 'reserve_ram', self.cancel_at(fixture.budget.reserve_ram, call=2, after=True)), patch.object(
                fixture.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                HistoricalIntegral(blocks, fixture.holds._context.domain)
        recovery = caught.exception.historical_integral_cleanup_owner
        recovery.close()
        recovery.close()
        self.assertEqual(fixture.budget.ram_bytes, baseline)
        self.assertFalse(blocks.closed)

    def test_area_allocation_failure_retains_current_block_for_explicit_close(self):
        """面积核分配失败保留取得块，显式关闭清理自有金额并保留借用分块者。

        参数: 无。返回: None。异常: 原异常替换、前缀可读或当前块失去句柄。
        """
        _, blocks, owner = self.prepare()
        original = MemoryError('area-array')
        with patch.object(module, 'compute_integral_terms_numpy', side_effect=original):
            with self.assertRaises(MemoryError) as caught:
                owner.step()
        self.assertIs(caught.exception, original)
        self.assertIsNotNone(owner._current_block)
        with self.assertRaises(RuntimeError):
            owner.step()
        owner.close()
        self.assertFalse(blocks.closed)

    def test_step_workspace_reserve_and_release_cancel_can_close_once(self):
        """本层面积workspace申请/释放前后取消，状态失败但自有金额仍可归还。

        参数: 无。返回: None。异常: 已释放金额重复扣账或失败前缀被交付。
        """
        for method in ('reserve_ram', 'release_ram'):
            for after in (False, True):
                fixture, blocks, owner = self.prepare()
                original = getattr(fixture.budget, method)
                with patch.object(fixture.budget, method, self.cancel_at(original, after=after, target=65536 + 1024 * 2)):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.step()
                self.assertTrue(owner.failed)
                owner.close()
                owner.close()
                self.assertFalse(blocks.closed)

    def test_final_classification_cancel_keeps_owned_cleanup_reachable(self):
        """分类取消后的完整事实不开放为成功结果，拥有的所有句柄仍可清理。

        参数: 无。返回: None。异常: 取消后结果可读或资源清理失败。
        """
        _, blocks, owner = self.prepare()
        while not blocks._done:
            owner.step()
        with patch.object(module, 'make_integral_result', side_effect=KeyboardInterrupt('classification')):
            with self.assertRaises(KeyboardInterrupt):
                owner.step()
        with self.assertRaises(RuntimeError):
            _ = owner.result
        owner.close()
        self.assertFalse(blocks.closed)

    def test_current_block_close_cancel_before_after_is_retryable(self):
        """取得块的实际释放前后取消均使推进失败，close重试不重复释放块预算。

        参数: 无。返回: None。异常: 当前块清理句柄或原分块者所有权不符。
        """
        from chronaxis.execution.calculation_blocks import CalculationBlock
        for after in (False, True):
            _, blocks, owner = self.prepare()
            original = CalculationBlock.close

            def cancel_close(block):
                """取消一次本步块关闭。参数: block 为实际块。返回: None。异常: 本次取消。"""
                if after:
                    original(block)
                raise KeyboardInterrupt('block-close')

            with patch.object(CalculationBlock, 'close', cancel_close):
                with self.assertRaises(KeyboardInterrupt):
                    owner.step()
            self.assertTrue(owner.failed)
            owner.close()
            self.assertFalse(blocks.closed)

    def test_final_owner_close_cancel_before_after_preserves_borrowed_budget(self):
        """最终结果owner释放前后取消按实际账本处理，关闭不扣借用资源金额。

        参数: 无。返回: None。异常: 重复扣账或借用分块者误关闭。
        """
        for after in (False, True):
            fixture, blocks, owner = self.prepare()
            self.consume(owner)
            target = owner._held_cost
            with patch.object(fixture.budget, 'release_ram', self.cancel_at(fixture.budget.release_ram, after=after, target=target)):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            owner.close()
            owner.close()
            self.assertTrue(owner.closed)
            self.assertFalse(blocks.closed)
            with self.assertRaises(ResultClosedError):
                _ = owner.result


if __name__ == '__main__':
    # 手动执行仍采用登记的独立清理，真实夹具只写新项目work目录。
    unittest.main()
