"""验证显式实际观测域贯穿历史指标，而原请求、上下文与来源证明保持不变。

输入由真实load_analysis_plan、memory/CSV读取、历史封存和运行绑定建立；只检查独立数学入口。
公开事件和片段计算由test_event_calculation_origin/test_record_scope_calculations/test_record_windows验证。
有限手算例的请求为0—12ns，真实两源分别到8/5ns；片段请求5—13ns，实际5—8ns。
六数学入口须共用这个明确域，按各信号自己的EOF保留缺失，不能缩短原context或补零。
本专项只收有限夹具结果；生产有界性、借出行和预算责任仍由各真实owner执行。
故障注入只包真实单笔预算，保留原异常、最高恢复owner及实际文件关闭证据。
所有独立工作证据标home；测试不修改旧来源、旧专项、配置模型或全局账本。
"""

# 只导入旧工厂模块，不把其TestCase绑定到本模块而重复discovery。
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from history_test_fixture import HistoricalMathFixture
from chronaxis.core.expression import compile_expression
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.execution.calculation_blocks import HistoricalCalculationBlocks
from chronaxis.execution.historical_conditional_blocks import HistoricalConditionalBlocks
from chronaxis.execution.historical_integral import HistoricalIntegral
from chronaxis.execution.historical_time_calculation import HistoricalTimeCalculation
from chronaxis.execution.historical_conditional_time_calculation import HistoricalConditionalTimeCalculation
from chronaxis.execution.historical_sample_calculation import HistoricalSampleCalculation
from chronaxis.execution.historical_selection_rows import HistoricalSelectionRows


# 区分省略参数和显式None，才能检查旧调用费用没有被隐式显式化。
_OMITTED = object()


class HistoricalObservationScopeTests(unittest.TestCase):
    """每个真实会话保留借用基线，指标只关闭自己的回读、结果和费用。"""

    def fixture(self, *, kind='memory', backend='numpy', size=2, **changes):
        """读取同计划真实历史并记录明确观测域。

        参数: kind/backend/size控制真实来源、数值后端和切批；changes传旧工厂明确参数。
        返回: 含data/observation/baseline的有限夹具。
        异常: 原计划、读取、检测、窗口核错误或调用方最终余额断言失败。
        """
        builder = HistoricalMathFixture('runTest')
        self.addCleanup(self.cleanup_factory, builder)
        arguments = dict(kind=kind, backend=backend, size=size, buffer=1, domain=(0, 12),
                         other_rows=((0, 4), (5, 4)))
        arguments.update(changes)
        data = builder.fixture(**arguments)
        # 数学入口只借同一实际观测域，无需构造已经退役的公开事件/片段包装行。
        observation = Interval(0, max(item.observed_end_ns for item in data.context.completions))
        return SimpleNamespace(data=data, observation=observation,
                               baseline=data.budget.ram_bytes, backend=backend, size=size)

    def cleanup_factory(self, builder):
        """执行旧工厂完整清理并核对最终0。参数: 原builder。返回: None。异常: 资源断言失败。"""
        self.assertTrue(builder.doCleanups())

    def compiled(self, fixture, text):
        """用原运行绑定和同计划derived编译。参数: fixture/表达式。返回: compiled。异常: 原编译错误。"""
        data = fixture.data
        return compile_expression(text, data.lease.bindings,
                                  derived=tuple(item.definition for item in data.plan.derived))


    def close_check(self, fixture, owner):
        """两次close须只归还自有预算。参数: fixture/owner。返回: None。异常: 借用或FD断言失败。"""
        # 第二次关闭验证实际金额只扣一次；历史和绑定lease均仍由调用方持有。
        owner.close()
        owner.close()
        data = fixture.data
        self.assertEqual(data.budget.ram_bytes, fixture.baseline)
        self.assertFalse(data.history.closed)
        self.assertFalse(data.lease.closed)
        self.assertFalse(data.history._iterators)
        self.assertFalse(data.history._groups)

    def finish(self, owner):
        """有限推进标量到完整结果。参数: 实际owner。返回: CalculationResult。异常: 原错或不终止。"""
        for _ in range(1000):
            if not owner.step():
                self.assertTrue(owner.finished)
                return owner.result
        self.fail('有限观测夹具未完成')

    def entries(self, fixture, *, observation=_OMITTED, spec=None):
        """提供六数学入口的真实参数，不预先创建任何子owner。

        参数: fixture、可省略/None/显式范围、可选原spec。
        返回: (名称, 类, 位置参数, 关键字参数)有限tuple。
        异常: 原表达式或模型校验错误。
        """
        data = fixture.data
        spec = CalculationDefinition('calculation', 'time_weighted_mean', Interval(5, 13), scope='segment') if spec is None else spec
        base = (data.history, data.context, data.lease.bindings, self.compiled(fixture, 'a'), spec)
        condition = self.compiled(fixture, 'a > 0')
        common = dict(backend=fixture.backend, batch_intervals=fixture.size)
        if observation is not _OMITTED:
            common['observation'] = observation
        sample = replace(spec, operation='sample_mean')
        select = replace(spec, operation='select')
        return (('blocks', HistoricalCalculationBlocks, base, dict(common)),
                ('conditional_blocks', HistoricalConditionalBlocks, base + (condition,), dict(common)),
                ('time', HistoricalTimeCalculation, base, dict(common)),
                ('conditional_time', HistoricalConditionalTimeCalculation, base + (condition,), dict(common)),
                ('samples', HistoricalSampleCalculation, base[:4] + (sample,), dict(common)),
                ('selection', HistoricalSelectionRows, base[:4] + (select,), dict(common)))



    def test_longer_source_sets_session_extent_each_expression_keeps_own_missing(self):
        """长8短5及短3长8均保留八纳秒会话，缺失只进入相应表达式的值覆盖。

        参数: 无。返回: None。异常: 按短源/单表达式裁会话或EOF外补值。
        """
        cases = ((((0, 1), (3, 0), (5, 1), (8, 0)), ((0, 4), (5, 4)), {'a': (8, 6e-9), 'b': (5, 20e-9)}),
                 (((0, 1), (3, 1)), ((0, 4), (8, 4)), {'a': (3, 3e-9), 'b': (8, 32e-9)}))
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for rows, other, expected in cases:
                    fixture = self.fixture(kind=kind, backend=backend, rows=rows, other_rows=other)
                    data = fixture.data
                    self.assertEqual(fixture.observation, Interval(0, 8))
                    for text, (valid, value) in expected.items():
                        with self.subTest(kind=kind, backend=backend, source=text, valid=valid):
                            spec = CalculationDefinition('whole', 'integral', data.context.domain)
                            blocks = HistoricalCalculationBlocks(data.history, data.context, data.lease.bindings,
                                self.compiled(fixture, text), spec, backend=backend, batch_intervals=2,
                                observation=fixture.observation)
                            self.addCleanup(blocks.close)
                            owner = HistoricalIntegral(blocks, fixture.observation)
                            self.addCleanup(owner.close)
                            result = self.finish(owner)
                            self.assertEqual((result.actual_window, result.window_duration_ns,
                                result.value_valid_duration_ns, result.requested_coverage), (Interval(0, 8), 8, valid, 2/3))
                            self.assertAlmostEqual(result.value, value, delta=1e-23)
                            self.assertEqual(result.value_unknown_ranges, () if valid == 8 else (Interval(valid, 8),))
                            owner.close()
                            blocks.close()
                            self.close_check(fixture, owner)

    def test_both_mean_passes_keep_original_context_and_same_explicit_observation(self):
        """两遍时间均值真实重建分块时都保留显式域，原上下文及绑定身份不能收窄。

        参数: 无。返回: None。异常: 第二遍漏传范围、事实不一致或原ctx被替换。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(kind='csv', backend=backend, size=1)
            for joint in (False, True):
                factory = HistoricalConditionalTimeCalculation if joint else HistoricalTimeCalculation
                actual = factory._make_blocks
                seen = []

                def record_blocks(owner):
                    """观察真实工厂输出而不替换子构造。参数: owner。返回: 原blocks。异常: 原构造错误。"""
                    blocks = actual(owner)
                    seen.append((owner._context, owner._observation, blocks._actual))
                    return blocks

                data = fixture.data
                arguments = (data.history, data.context, data.lease.bindings, self.compiled(fixture, 'a'),
                             CalculationDefinition('mean', 'time_weighted_mean', Interval(5, 13), scope='segment'))
                if joint:
                    arguments += (self.compiled(fixture, 'a > 0'),)
                with patch.object(factory, '_make_blocks', record_blocks):
                    owner = factory(*arguments, backend=backend, batch_intervals=1, observation=fixture.observation)
                    self.addCleanup(owner.close)
                    result = self.finish(owner)
                self.assertEqual(len(seen), 2)
                self.assertTrue(all(context is data.context and observed is fixture.observation and actual_range == Interval(5, 8)
                                    for context, observed, actual_range in seen))
                self.assertEqual((result.value, result.window_duration_ns, result.requested_coverage), (1., 3, 3/8))
                self.assertTrue(owner._second_pass)
                self.close_check(fixture, owner)

    def test_omitted_none_preserve_old_constructor_cost_and_results_explicit_domain_is_charged(self):
        """省略与None保持六数学入口旧固定费用和结果，显式原domain另计引用且关闭归零。

        参数: 无。返回: None。异常: 默认调用被隐式扩费、旧结果改变或新增引用漏计。
        """
        fixture = self.fixture(kind='csv')
        # 首片段请求0—8与原domain交集一致，旧默认合法；不拿第二片段的旧拒绝假称兼容。
        spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 8), scope='segment')
        snapshots = {}
        for label, observation in (('omitted', _OMITTED), ('none', None), ('domain', fixture.data.context.domain)):
            for name, factory, args, kwargs in self.entries(fixture, observation=observation, spec=spec):
                owner = factory(*args, **kwargs)
                self.addCleanup(owner.close)
                cost = fixture.data.budget.ram_bytes - fixture.baseline
                # 不保留大列；每块实际关闭。只记有限可比事实，推进完成后再关闭固定费用。
                if name in ('blocks', 'conditional_blocks'):
                    facts = []
                    for block in owner:
                        facts.append((block.series.observation, block.series.times_ns))
                        block.close()
                    signature = tuple(facts)
                elif name == 'selection':
                    rows = tuple(owner)
                    signature = rows
                else:
                    signature = self.finish(owner)
                snapshots[label, name] = (cost, signature)
                self.close_check(fixture, owner)
        for name, _, _, _ in self.entries(fixture, spec=spec):
            self.assertEqual(snapshots['omitted', name], snapshots['none', name])
            self.assertEqual(snapshots['domain', name][1], snapshots['none', name][1])
            self.assertGreater(snapshots['domain', name][0], snapshots['none', name][0])

    def test_invalid_observation_fails_before_reservation(self):
        """非法类型或越原域在首笔自有预约前拒绝，不隐式改写请求。

        参数: 无。返回: None。异常: 校验过晚、错误归属或借用余额变化。
        """
        fixture = self.fixture()
        for observation, expected in ((7, TypeError), ((0, 8), TypeError),
                                      (Interval(-1, 8), ValueError), (Interval(0, 13), ValueError)):
            for name, factory, args, kwargs in self.entries(fixture, observation=observation):
                with self.subTest(entry=name, observation=observation):
                    with patch.object(fixture.data.budget, 'reserve_ram', side_effect=AssertionError('validation reserved')) as reserve:
                        with self.assertRaises(expected):
                            factory(*args, **kwargs)
                    reserve.assert_not_called()
                    self.assertEqual(fixture.data.budget.ram_bytes, fixture.baseline)

    def test_zero_touching_and_disjoint_windows_do_not_manufacture_zero_or_selection_rows(self):
        """低层零长、碰右端和域外请求保留原因，不能制造正常零或右端样本行。

        参数: 无。返回: None。异常: 空窗补零、末点输出或请求被改写。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(kind='csv', backend=backend)
            data = fixture.data
            for window, actual, reason in ((Interval(5, 5), Interval(5, 5), 'zero_length_window'),
                                            (Interval(8, 10), Interval(8, 8), 'no_observation'),
                                            (Interval(9, 10), None, 'no_observation')):
                for operation in ('time_weighted_mean', 'sample_mean', 'select'):
                    spec = CalculationDefinition('empty', operation, window)
                    factory = HistoricalTimeCalculation if operation == 'time_weighted_mean' else HistoricalSampleCalculation if operation == 'sample_mean' else HistoricalSelectionRows
                    owner = factory(data.history, data.context, data.lease.bindings, self.compiled(fixture, 'a'),
                                    spec, backend=backend, batch_intervals=2, observation=fixture.observation)
                    self.addCleanup(owner.close)
                    if operation == 'select':
                        self.assertEqual(tuple(owner), ())
                    else:
                        result = self.finish(owner)
                        self.assertEqual((result.value, result.actual_window, result.reason), (None, actual, reason))
                        self.assertEqual(result.spec.window, window)
                    self.close_check(fixture, owner)
