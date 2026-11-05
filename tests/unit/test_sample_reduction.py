"""手算验证有限样本统计两独立纯核，真实更新、覆盖和数值故障分别检查。

共用小型typed输入，但极值/算术均值、样本数和覆盖预期来自人工计算。验证可选
BOOL条件、非均匀每块样本数、原序抵消、原整数精度、raw求和/除法/换算失败、
半开/点/裁剪边界与完整来源；不调用一后端为另一后端生成预期。不读真实来源，
测试无文件副作用，正式执行日志由命令保存在work专用目录。
"""

# 冻结模型制造明确边界及拒绝输入；两后端各自维护数值状态。
from dataclasses import replace
import unittest
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.sample_reduction import SampleReductionResult
from chronaxis.core.sample_reduction_reference import ReferenceSampleReduction
from chronaxis.core.sample_reduction_numpy import NumpySampleReduction
from chronaxis.core.types import QualityFlag as Q, SignalDType as D
from chronaxis.sources.csv_spec import CSVSourceRef
from chronaxis.timebase.conversion import INT64_MIN, INT64_MAX


class SampleReductionTests(unittest.TestCase):
    """真实样本口径由手算断言，不把保持时长或条件更新当作均值分母。"""

    def series(self, times=(0, 1), values=(4.0, 99.0), conditions=None, *,
               dtype=D.FLOAT64, unit='W', actual=None, refs=None, diagnostics=()):
        """构造明确typed有限输入，None值/条件为MISSING，条件列None为全TRUE。

        参数: times完整ns轴、values/conditions同长原值；dtype/unit声明类型/单位；
            actual真实原值更新、refs完整来源、diagnostics额外依赖原因。
        返回: 冻结CalculationSeries。异常: 原typed模型错误传播。
        """
        # 缺值和条件缺失各有质量，不将None隐式转为正常零或False。
        values = tuple(ScalarValue(value, dtype) if value is not None else ScalarValue(None, dtype, False, Q.MISSING) for value in values)
        conditions = None if conditions is None else tuple(ScalarValue(value, D.BOOL) if value is not None else ScalarValue(None, D.BOOL, False, Q.MISSING) for value in conditions)
        actual = tuple(True for _ in times) if actual is None else actual
        refs = (SourceRef('session', 'table', 'raw.value'),) if refs is None else refs
        return CalculationSeries(Interval(times[0], times[-1]), times, values, actual, unit, conditions,
                            diagnostics, 'explicit-sample-reduction-synthetic', refs)

    def reducer(self, series, operation, backend, *, spec=None, partial_limit=4096):
        """建立一个后端独立纯状态，默认请求原观察域。

        参数: series给出原dtype/unit，operation三samples之一，backend声明独立核；
            spec可指定原窗/输出单位，partial_limit误差容量。
        返回: 新ReferenceSampleReduction或NumpySampleReduction。异常: 配置错误传播。
        """
        # 每次单独建立后端状态，均值不共享参考或数组累计结果。
        cls = ReferenceSampleReduction if backend == 'reference' else NumpySampleReduction
        spec = CalculationDefinition('samples', operation, series.observation) if spec is None else spec
        return cls(spec, series.unit, series.values[0].dtype, partial_limit=partial_limit)

    def test_hand_unconditional_samples_ignore_holding_duration(self):
        """2、4、8三个真实样本均值14/3，不因8保持更久而按时长加权。

        参数: 无。返回: None。异常: 样本口径、可选条件或覆盖不符手算断言失败。
        """
        # 区间时长1/1/8ns故意不均匀，右端999只给边界，不贡献第4个样本。
        series = self.series((0, 1, 2, 10), (2.0, 4.0, 8.0, 999.0))
        for backend in ('reference', 'numpy'):
            for operation, expected in (('sample_minimum', 2.0), ('sample_maximum', 8.0), ('sample_mean', 14/3)):
                reducer = self.reducer(series, operation, backend)
                facts, number = reducer.push(series), reducer.finish()
                # 真实计数3与保持有效10ns分开；无条件已知覆盖10ns、FALSE和两未知均空。
                self.assertEqual((number.value, number.unit, number.valid_sample_count, number.calculation_failed), (expected, 'W', 3, False))
                self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                    facts.selected_duration_ns, facts.false_duration_ns, facts.valid_sample_count), (10, 10, 10, 0, 3))
                self.assertEqual((facts.value_unknown_ranges, facts.condition_unknown_ranges, facts.quality), ((), (), Q.NONE))
                self.assertEqual((reducer.value_valid_duration_ns, reducer.selected_duration_ns, reducer.valid_sample_count), (10, 10, 3))

    def test_conditions_two_unknown_partitions_and_only_real_selected_updates(self):
        """T/F/U/T缺值/T保持中仅2是有效真实样本，保持8不参与样本候选。

        参数: 无。返回: None。异常: 条件/值未知混合、条件更新误计样本断言失败。
        """
        # 4ns的8为条件或边界更新actual=False，尽管贡献TRUE有效保持时长也没有样本。
        series = self.series((0, 1, 2, 3, 4, 5), (2.0, 99.0, -100.0, None, 8.0, 999.0),
            (True, False, None, True, True, False), actual=(True, True, True, True, False, True))
        for backend in ('reference', 'numpy'):
            for operation in ('sample_minimum', 'sample_maximum', 'sample_mean'):
                reducer = self.reducer(series, operation, backend)
                facts, number = reducer.push(series), reducer.finish()
                self.assertEqual((number.value, number.valid_sample_count), (2.0, 1))
                self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                    facts.selected_duration_ns, facts.selected_value_unknown_duration_ns,
                    facts.false_duration_ns, facts.valid_sample_count), (4, 4, 2, 1, 1, 1))
                self.assertEqual(facts.value_unknown_ranges, (Interval(3, 4),))
                self.assertEqual(facts.condition_unknown_ranges, (Interval(2, 3),))
                self.assertEqual(facts.quality, Q.MISSING)

    def test_different_counts_per_block_use_global_sample_denominator(self):
        """每块2/3/1样本必须全局(1+3+5+7+9+11)/6=6，不平均三个块均值。

        参数: 无。返回: None。异常: 块均值拼接、右端重复或累计计数错误断言失败。
        """
        # 相邻共享右端各为actual=False，下一块首点才表示该时刻真实更新。
        blocks = (self.series((0, 1, 2), (1.0, 3.0, 99.0), actual=(True, True, False)),
                  self.series((2, 3, 4, 5), (5.0, 7.0, 9.0, 99.0), actual=(True, True, True, False)),
                  self.series((5, 6), (11.0, 99.0), actual=(True, False)))
        spec = CalculationDefinition('global_mean', 'sample_mean', Interval(0, 6))
        for backend in ('reference', 'numpy'):
            reducer = self.reducer(blocks[0], 'sample_mean', backend, spec=spec)
            facts = tuple(reducer.push(block) for block in blocks)
            number = reducer.finish()
            self.assertEqual(tuple(fact.valid_sample_count for fact in facts), (2, 3, 1))
            self.assertEqual((number.value, number.valid_sample_count, reducer.selected_duration_ns), (6.0, 6, 6))

    def test_extrema_preserve_uint64_and_int64_original_precision(self):
        """uint64最大值与INT64两端极值保持原int，不经mean的浮点精度门槛。

        参数: 无。返回: None。异常: 大整数舍入、FALSE样本或dtype精度误拒绝断言失败。
        """
        # 中间有效样本外FALSE排除，只比较首两个TRUE整数；最末点仍是边界。
        cases = ((D.UINT64, (2**64-1, 2**64-2, 0, 0), 2**64-2, 2**64-1),
                 (D.INT64, (-2**63, 2**63-1, 0, 0), -2**63, 2**63-1))
        for dtype, values, minimum, maximum in cases:
            for backend in ('reference', 'numpy'):
                series = self.series((0, 1, 2, 3), values, (True, True, False, False), dtype=dtype)
                for operation, expected in (('sample_minimum', minimum), ('sample_maximum', maximum)):
                    reducer = self.reducer(series, operation, backend)
                    facts, number = reducer.push(series), reducer.finish()
                    self.assertIs(type(number.value), int)
                    self.assertEqual((number.value, number.valid_sample_count, facts.quality), (expected, 2, Q.NONE))

    def test_mean_integer_precision_changes_value_coverage_and_selected_samples(self):
        """2**53+1即使FALSE仍丢值覆盖；TRUE精确2可统计，2**63精确表示仍允许mean。

        参数: 无。返回: None。异常: 舍入输入冒充样本、精确大数误拒绝断言失败。
        """
        # 同一不可精确数各在TRUE/FALSE一段，第三段TRUE精确2，样本分母仅1。
        series = self.series((0, 1, 2, 3), (2**53+1, 2**53+1, 2, 0), (True, False, True, False), dtype=D.UINT64)
        for backend in ('reference', 'numpy'):
            reducer = self.reducer(series, 'sample_mean', backend)
            facts, number = reducer.push(series), reducer.finish()
            self.assertEqual((number.value, number.valid_sample_count), (2.0, 1))
            self.assertEqual((facts.value_valid_duration_ns, facts.selected_duration_ns,
                facts.selected_value_unknown_duration_ns, facts.false_duration_ns, facts.quality), (1, 1, 1, 1, Q.PRECISION_LOSS))
            self.assertEqual(facts.value_unknown_ranges, (Interval(0, 2),))
            # 数值幅度大不自动失效，2**63浮点精确可表示，单样本均值原量级保留。
            exact = self.series(values=(2**63, 0), dtype=D.UINT64)
            reducer = self.reducer(exact, 'sample_mean', backend)
            self.assertEqual(reducer.push(exact).quality, Q.NONE)
            self.assertEqual(reducer.finish().value, float(2**63))

    def test_original_order_cancellation_then_global_mean_and_final_conversion(self):
        """原序1e16/1/-1e16保留raw总和1，除3后kW转W一次得到1000/3。

        参数: 无。返回: None。异常: 先块求和、抵消丢小项或转换顺序错误断言失败。
        """
        # 每样本一有限块，同一原spec/global窗保留一条有界误差状态；末点不进样本。
        blocks = tuple(self.series((i, i+1), (value, 0.0), actual=(True, False), unit='kW') for i, value in enumerate((1e16, 1.0, -1e16)))
        spec = CalculationDefinition('cancel', 'sample_mean', Interval(0, 3), output_unit='W')
        for backend in ('reference', 'numpy'):
            reducer = self.reducer(blocks[0], 'sample_mean', backend, spec=spec)
            for block in blocks:
                reducer.push(block)
            number = reducer.finish()
            self.assertEqual(number.value, (1/3)*1000)
            self.assertEqual((number.unit, number.valid_sample_count, number.quality), ('W', 3, Q.NONE))
            self.assertEqual(reducer.finish(), number)

    def test_raw_intermediate_overflow_remains_failure_even_when_mean_is_finite(self):
        """1e308+1e308原量纲中途溢出永久失败，不改成先除样本数的时间均值算法。

        参数: 无。返回: None。异常: 中间失败靠抵消恢复或被预规范化绕过断言失败。
        """
        # 两正大数的算术均值数学上有限，原序sum政策仍失败；加第三负数也不恢复。
        for values in ((1e308, 1e308, 0.0), (1e308, 1e308, -1e308, 0.0)):
            times = tuple(range(len(values)))
            for backend in ('reference', 'numpy'):
                series = self.series(times, values)
                reducer = self.reducer(series, 'sample_mean', backend)
                facts, number = reducer.push(series), reducer.finish()
                # 数值故障与输入有效性分开，全选覆盖和真实样本仍完整。
                count = len(values)-1
                self.assertEqual((number.value, number.calculation_failed, number.quality, number.valid_sample_count), (None, True, Q.NONFINITE, count))
                self.assertEqual((facts.value_valid_duration_ns, facts.selected_duration_ns, facts.valid_sample_count, facts.quality), (count, count, count, Q.NONE))

    def test_division_and_output_underflow_are_number_failures_not_unknown_coverage(self):
        """最小非零总和除2下溢，或均值最终缩小单位下溢，都保留原完整覆盖与样本数。

        参数: 无。返回: None。异常: 除法/换算故障被当正常零或改值覆盖断言失败。
        """
        # raw总和5e-324为正常非零，但除两个真实样本后0不可作为合法均值。
        for backend in ('reference', 'numpy'):
            series = self.series((0, 1, 2), (5e-324, 0.0, 0.0))
            reducer = self.reducer(series, 'sample_mean', backend)
            facts, number = reducer.push(series), reducer.finish()
            self.assertEqual((number.value, number.calculation_failed, number.quality), (None, True, Q.PRECISION_LOSS))
            self.assertEqual((facts.value_valid_duration_ns, facts.selected_duration_ns, facts.valid_sample_count, facts.quality), (2, 2, 2, Q.NONE))
            # 单个W样本均值无除法丢失，最后换kW的1/1000倍率才导致非零消失。
            tiny = self.series(values=(5e-324, 0.0))
            reducer = self.reducer(tiny, 'sample_mean', backend, spec=CalculationDefinition('tiny', 'sample_mean', tiny.observation, output_unit='kW'))
            self.assertEqual(reducer.push(tiny).quality, Q.NONE)
            self.assertEqual(reducer.finish().quality, Q.PRECISION_LOSS)

    def test_empty_false_unknown_missing_and_valid_zero_sample_are_distinct(self):
        """空选择或未知都没有纯数值候选，唯有真实有效零样本返回0与计数1。

        参数: 无。返回: None。异常: 空sum补0、UNKNOWN当FALSE或正常零丢失断言失败。
        """
        # None条件列表示全TRUE；显式FALSE/UNKNOWN、缺值以及没有actual更新分别无样本。
        cases = ((self.series(conditions=(False, False)), None, 0),
                 (self.series(conditions=(None, None)), None, 0),
                 (self.series(values=(None, None)), None, 0),
                 (self.series(actual=(False, True)), None, 0),
                 (self.series(values=(0.0, 999.0)), 0.0, 1))
        for series, expected, count in cases:
            for backend in ('reference', 'numpy'):
                for operation in ('sample_minimum', 'sample_maximum', 'sample_mean'):
                    reducer = self.reducer(series, operation, backend)
                    facts, number = reducer.push(series), reducer.finish()
                    self.assertEqual((number.value, number.valid_sample_count, facts.valid_sample_count), (expected, count, count))
                    self.assertFalse(number.calculation_failed)

    def test_half_open_clipping_int64_edges_point_and_no_intersection(self):
        """裁剪保持不造样本，极大绝对时间仍精确半开；点或无交集没有样本证据。

        参数: 无。返回: None。异常: 左保持/右端点计样本或空域误出数值断言失败。
        """
        # 请求2—7ns包含1和2的保持区间，但只有5ns实际原值更新2进入样本，8ns末点排除。
        for base in (0, INT64_MIN, INT64_MAX-8):
            series = self.series(tuple(base+i for i in (0, 3, 5, 8)), (1.0, 99.0, 2.0, None), actual=(True, False, True, True))
            for backend in ('reference', 'numpy'):
                reducer = self.reducer(series, 'sample_mean', backend, spec=CalculationDefinition('clip', 'sample_mean', Interval(base+2, base+7)))
                facts, number = reducer.push(series), reducer.finish()
                self.assertEqual((number.value, facts.value_valid_duration_ns, facts.valid_sample_count, facts.quality), (2.0, 5, 1, Q.NONE))
        # 零请求/不相交/单点观测不以边界点提供一个正常样本。
        for backend in ('reference', 'numpy'):
            for series, window, actual in ((self.series(), Interval(0, 0), Interval(0, 0)),
                    (self.series(), Interval(2, 3), None), (self.series((5,), (4.0,)), Interval(0, 10), Interval(5, 5))):
                reducer = self.reducer(series, 'sample_minimum', backend, spec=CalculationDefinition('empty', 'sample_minimum', window))
                facts, number = reducer.push(series), reducer.finish()
                self.assertEqual((facts.actual_window, number.value, number.valid_sample_count), (actual, None, 0))

    def test_units_sources_dependency_quality_and_output_failure_preserve_facts(self):
        """CSV子类与依赖STALE保留，最终单位精度/溢出故障不改有效原样本覆盖。

        参数: 无。返回: None。异常: 来源降格、双转换或数值故障重写事实断言失败。
        """
        # 单个2kW真实样本只最后换成2000W；依赖STALE不使明确正常逻辑值变未知。
        ref = CSVSourceRef('session', 'table', 'raw.value', 'synthetic.csv', 3, '0', '2', False)
        series = self.series(values=(2.0, 99.0), unit='kW', refs=(ref,), diagnostics=(Q.STALE, Q.MISSING))
        for backend in ('reference', 'numpy'):
            reducer = self.reducer(series, 'sample_mean', backend, spec=CalculationDefinition('unit', 'sample_mean', series.observation, output_unit='W'))
            facts, number = reducer.push(series), reducer.finish()
            self.assertEqual((number.value, number.unit, facts.quality), (2000.0, 'W', Q.STALE))
            self.assertIs(facts.source_refs, series.source_refs)
            self.assertIs(facts.source_refs[0], ref)
            # 原极值完整有效，非1倍率只在finish核对目标整数范围或浮点乘法溢出。
            for dtype, value, quality in ((D.UINT64, 2**64-1, Q.OVERFLOW), (D.FLOAT64, 1e308, Q.NONFINITE)):
                bad = self.series(values=(value, value), dtype=dtype, unit='kW')
                reducer = self.reducer(bad, 'sample_maximum', backend, spec=CalculationDefinition('bad_unit', 'sample_maximum', bad.observation, output_unit='W'))
                facts, number = reducer.push(bad), reducer.finish()
                self.assertEqual((number.value, number.calculation_failed, number.quality), (None, True, quality))
                self.assertEqual((facts.value_valid_duration_ns, facts.valid_sample_count, facts.quality), (1, 1, Q.NONE))

    def test_typed_configuration_identity_capacity_and_frozen_partitions_reject_errors(self):
        """数值能力、单位/dtype、身份和容量严格，冻结事实/结果不修补矛盾。

        参数: 无。返回: None。异常: 非法配置或不可能覆盖/样本结果被接受断言失败。
        """
        # 正常基线先分离结构错误与业务无样本，BOOL主值和错误算子不被自动转成数值。
        series = self.series()
        for backend in ('reference', 'numpy'):
            for bad in (replace(series, unit='kW'), self.series(values=(4, 99), dtype=D.INT64)):
                with self.assertRaises(ValueError):
                    self.reducer(series, 'sample_minimum', backend).push(bad)
            for operation, bad in (('time_weighted_mean', series), ('sample_minimum', self.series(values=(True, False), dtype=D.BOOL, unit='1'))):
                with self.assertRaises((TypeError, ValueError)):
                    self.reducer(bad, operation, backend)
            with self.assertRaises(ValueError):
                self.reducer(series, 'sample_mean', backend, partial_limit=True)
            reducer = self.reducer(series, 'sample_minimum', backend)
            facts = reducer.push(series)
            with self.assertRaises(ValueError):
                reducer.push(replace(series, binding_identity='different'))
            # 选择交集不能伪造TRUE未知；bool纳秒、未知重叠、条件缺口、越界及来源降格均拒绝。
            changes = ({'selected_duration_ns': 0, 'selected_value_unknown_duration_ns': 1},
                       {'value_valid_duration_ns': True}, {'valid_sample_count': 2},
                       {'value_valid_duration_ns': 0, 'value_unknown_ranges': (Interval(0, 1), Interval(0, 1))},
                       {'condition_known_duration_ns': 0}, {'actual_window': Interval(0, 2)}, {'source_refs': ['raw.value']})
            for change in changes:
                with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                    replace(facts, **change)
        # own数值模型计真实样本：无样本却有值、失败无样本或非有限正常值都是矛盾。
        for arguments in ((0.0, 'W', False, Q.NONE, 0), (None, 'W', True, Q.NONFINITE, 0),
                          (float('inf'), 'W', False, Q.NONE, 1), (None, 'W', False, Q.NONE, True)):
            with self.assertRaises((TypeError, ValueError)):
                SampleReductionResult(*arguments)


# 专项可独立运行，真实历史入口与完整回归由主任务统一执行。
if __name__ == '__main__':
    unittest.main()
