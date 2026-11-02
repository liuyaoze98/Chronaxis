"""检查统计与积分在裁剪范围、部分缺失和条件筛选下返回什么。

输入为合成信号、明确选择条件和时间窗口，输出为unittest断言。先用手算
验证按上次值保持的面积，再独立比较参考与NumPy的完整结果及未知范围。
有效零、无观测、部分可核实结果和全程False分别检查；严格完整政策在
有缺失时返回null。只统计实际更新，整数极值保持精度，浮点归约允许明确小误差。
对应T17—T19、T21—T22、T25、T34、T43—T44；固定种子只用于合成对照，
不读取旧文件，不作真实日志、性能或M2时间统计能力的完成证明。
"""

# 冻结模型局部替换用于明确输入范围/政策变体。
from dataclasses import replace
# 真实验收断言，不吞失败或改预期让测试通过。
import unittest
# 固定可复现输入，手算基准另外独立核对。
import random
# 当前typed内存原行/绑定模型。
from chronaxis.core import (Interval, MemoryRow, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType as D, SourceSpec, TimebaseSpec, TimeType, compile_expression)
# 指标协议与独立数值实现，不采用旧总数作正确性基准。
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
# 独立标量裁剪/求和/样本统计。
from chronaxis.core.calculations_reference import compute_reference
# 真正数组UFUNC/掩码/归约，不调用参考内核。
from chronaxis.core.calculations_numpy import compute_numpy
# 完整原行到结果两条独立执行链。
from chronaxis.core.calculations_memory_reference import build_calculation_series_reference, compute_memory_reference
# 实际数组保持/表达式/指标接线。
from chronaxis.core.calculations_memory_numpy import build_calculation_series_numpy, compute_memory_numpy
# 明确ScalarValue有效性及质量，不把invalid占位当0。
from chronaxis.core.numeric import ScalarValue
# 原因保持当前合法质量组合。
from chronaxis.core.types import QualityFlag as Q


def _series(values, *, conditions=None, times=(0, 1_000_000_000, 3_000_000_000), unit='W', dtype=D.FLOAT64, actual=None):
    """建立明示合成连续表示和实际样本证据。

    参数: values正常原生同dtype数值或None；条件bool/None；times完整ns；unit/dtype/actual明确。
    返回: CalculationSeries，unknown为MISSING，终点值不额外贡献面积。
    异常: typed模型/时间错误传播，测试不绕过校验。
    """
    # 无效None是有原因未知，不填正常零。
    numeric = tuple(ScalarValue(value, dtype, value is not None, Q.NONE if value is not None else Q.MISSING) for value in values)
    # TRUE/FALSE已知，与UNKNOWN原因严格分开。
    condition = None if conditions is None else tuple(ScalarValue(value, D.BOOL, value is not None, Q.NONE if value is not None else Q.MISSING) for value in conditions)
    # actual可明确timer不是样本，默认每输入边界为真实合成更新。
    return CalculationSeries(Interval(times[0], times[-1]), tuple(times), numeric, tuple(True for _ in times) if actual is None else tuple(actual), unit, condition)


def _memory(*, age=5_000_000_000, rows=None, end=3_000_000_000, unit='W', dtype=D.FLOAT64):
    """建立T17实际原行和可选BOOL字段，不编造不存在的绑定。

    参数: age/end明确ns；rows可选原time/字典序列；unit/dtype声明当前物理值。
    返回: 当前SignalBindings，原字段/时钟/范围全部可追溯。
    异常: 模型/绑定校验失败传播，不假定未知周期。
    """
    # 默认4000W/6000W/0W，末样本只提供3s边界。
    rows = rows if rows is not None else ((0, {'raw': 4000.}), (1_000_000_000, {'raw': 6000.}), (3_000_000_000, {'raw': 0.}))
    # 明示合成公共原点，不证明实际跨源同步。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'calculations-synthetic-v1')
    # 来源内原顺序不重新排序或筛掉无效更新。
    source = SourceSpec('sensor', clock, tuple(MemoryRow(time, value, index) for index, (time, value) in enumerate(rows)), observation_start_ns=0, observation_end_ns=end)
    # 原字段是否真实存在决定绑定，而非全部模板字段。
    signals = (SignalDefinition('power', 'sensor', 'raw', dtype, unit, age),)
    # 可选实际条件来源字段，TTL也明确。
    if any('selected' in value for _, value in rows):
        # 条件策略独立定义，不暗示原period。
        signals += (SignalDefinition('selected', 'sensor', 'selected', D.BOOL, '1', age),)
    # 当前计划不从上次运行继承别名绑定。
    return SignalBindings(SessionSpec('session', clock, 0, end, (source,)), signals)


class CalculationTests(unittest.TestCase):
    """用完整事实差分与独立手算验证指标结果政策。

    浮点sum顺序差只允许数值小误差，范围/质量/计数/状态必须完全一致。
    """

    def _compare(self, series, spec):
        """独立执行两个数值内核，严格核对除浮点舍入外全部结果。

        参数: series完整typed输入，spec当前请求/政策。
        返回: 独立参考CalculationResult，供手算额外检查。
        异常: 事实或数值差分失败由unittest报告。
        """
        # 参考不调用NumPy，被测数组不以参考输出为输入。
        reference, array = compute_reference(series, spec), compute_numpy(series, spec)
        # 有正常浮点归约才允许最后数值小误差，其他字段不放宽。
        if type(reference.value) is float and type(array.value) is float:
            # 单位范围按相对1e-12及小绝对误差核对，不放宽quality。
            self.assertAlmostEqual(reference.value, array.value, delta=max(1e-12, abs(reference.value)*1e-12))
            # 完整覆盖/原因/来源/输入身份须相同。
            self.assertEqual(reference, replace(array, value=reference.value))
        else:
            # 精确整数、None、状态及零选择必须完全相同。
            self.assertEqual(reference, array)
        # 不改原Series，让调用者继续独立检查。
        return reference

    def _memory_compare(self, bindings, spec, *, expression='power', condition=None):
        """从原行通过两个独立保持/表达式/指标链对照。

        参数: 当前bindings/spec；表达式与可选条件均为合法简单别名DSL。
        返回: 独立参考结果，不修改原行或配置。
        异常: 绑定/表达式/数值或完整事实差异由unittest报告。
        """
        # 各计划在当前真实绑定编译，不只靠相同文本复用。
        numeric = compile_expression(expression, bindings)
        # 选择条件需同一个完整执行binding identity。
        selected = compile_expression(condition, bindings) if condition is not None else None
        # 两条独立原行链分别构造相同完整轴与样本事实。
        reference = build_calculation_series_reference(numeric, spec, condition=selected)
        # 数组原行/保持/表达式真正接线。
        array = build_calculation_series_numpy(numeric, spec, condition=selected)
        # 完整时间/actual/诊断不能因窗口端点不同而改变。
        self.assertEqual(reference.times_ns, array.times_ns)
        # 不把裁剪保持值当新样本。
        self.assertEqual(reference.actual_value_updates, array.actual_value_updates)
        # 原依赖未知诊断完整相同。
        self.assertEqual(reference.diagnostics, array.diagnostics)
        # 使用完整独立数值核对与当前参考手算事实。
        result = self._compare(reference, spec)
        # 公共原行入口也必须实际运行，不能只有声明。
        self.assertEqual(result, compute_memory_reference(numeric, spec, condition=selected))
        # 每次数组重新求当前输入结果，不喂参考列。
        computed = compute_memory_numpy(numeric, spec, condition=selected)
        # 当前固定用例总面积可精确一致。
        self.assertEqual(result, computed)
        # 留给具体测试检查独立预期。
        return result

    def test_t17_t18_zoh_units_and_clipping(self):
        """默认ZOH16000J/Wh，窗口先裁剪为11000J。

        参数: 无；明确4000W@0/6000W@1/0W@3的真实原行。
        返回: None。
        异常: 手算/单位/覆盖或两后端差异由unittest报告。
        """
        # T17完整[0,3)不能给最后0W增加周期。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 3_000_000_000))
        # 完整真实memory链核实，不只测试合成ScalarValue。
        result = self._memory_compare(_memory(), spec)
        # 手算4000*1+6000*2=16000J。
        self.assertEqual((result.value, result.unit, result.value_coverage, result.status), (16000., 'J', 1., 'complete'))
        # 明确输出Wh只应用一次/3600。
        result = self._memory_compare(_memory(), replace(spec, output_unit='Wh'))
        # 原period/DBC因子未重复乘。
        self.assertAlmostEqual(result.value, 4.444444444444445)
        # T18左/右端在采样间，先剪再乘dt。
        result = self._memory_compare(_memory(), replace(spec, window=Interval(500_000_000, 2_500_000_000)))
        # 手算4000*.5+6000*1.5=11000J。
        self.assertEqual(result.value, 11000.)
        # 实际窗口时长2s，非原域3s。
        self.assertEqual(result.window_duration_ns, 2_000_000_000)
        # 常见输入kW数学乘秒推到J，不是重复原行转换。
        result = self._compare(_series((4., 6., 0.), unit='kW'), spec)
        # 单位表明确倍率1000。
        self.assertEqual((result.value, result.unit), (16000., 'J'))
        # 有符号电流积分，不能靠正负命名充电或取绝对值。
        result = self._compare(_series((-1000., -2000., 0.), unit='mA'), replace(spec, output_unit='Ah'))
        # -1A*1s-2A*2s=-5A·s。
        self.assertAlmostEqual(result.value, -5/3600)

    def test_t19_t34_partial_strict_unknown_and_zero(self):
        """部分有效/全无效/有效零分开，strict不能补零。

        参数: 无；T19 TTL和T34明确无效输入。
        返回: None。
        异常: 结果/状态/覆盖/未知范围失败由unittest报告。
        """
        # T19 TTL1秒，第二样本到2秒失效，不等3秒原更新。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 3_000_000_000))
        # 独立原行链证明10000J及[2,3)未知。
        result = self._memory_compare(_memory(age=1_000_000_000), spec)
        # 手算4000*1+6000*1=10000，覆盖2/3。
        self.assertEqual((result.value, result.value_coverage, result.status), (10000., 2/3, 'partial'))
        # 失效范围明确，不填假0。
        self.assertEqual(result.value_unknown_ranges, (Interval(2_000_000_000, 3_000_000_000),))
        # strict覆盖不足返回null，事实仍保存。
        strict = self._memory_compare(_memory(age=1_000_000_000), replace(spec, partial_policy='strict'))
        # 数值与政策分开，保留2/3覆盖。
        self.assertEqual((strict.value, strict.status, strict.value_coverage), (None, 'indeterminate', 2/3))
        # T34 [1,3)全部无效，正常部分4000J。
        result = self._compare(_series((4000., None, None)), spec)
        # 不能跨unknown保持更早4000。
        self.assertEqual((result.value, result.value_coverage, result.status), (4000., 1/3, 'partial'))
        # 全无效不能用空sum得到正常0。
        result = self._compare(_series((None, None, None)), spec)
        # 明确value=null且无覆盖。
        self.assertEqual((result.value, result.value_coverage), (None, 0.))
        # 所有值为有效0，面积真为0且覆盖完整。
        result = self._compare(_series((0., 0., 0.)), spec)
        # 与全无效结果政策分开。
        self.assertEqual((result.value, result.value_coverage, result.status), (0., 1., 'complete'))

    def test_t21_t22_zero_domain_no_observation_and_eof(self):
        """有效零、无观测与零请求分开；EOF裁剪不声称完整。

        参数: 无；2秒有效零及明确请求范围/实际EOF。
        返回: None。
        异常: null/覆盖/状态/原因不符由unittest报告。
        """
        # T21有效P0的2秒域，面积是真0。
        series = _series((0., 0.), times=(0, 2_000_000_000))
        # 手算零面积但覆盖完整。
        result = self._compare(series, CalculationDefinition('zero', 'integral', Interval(0, 2_000_000_000)))
        # 与全未知null区分。
        self.assertEqual((result.value, result.value_coverage), (0., 1.))
        # T22值只在请求区间外，无交集不能使用0sum。
        spec = CalculationDefinition('energy', 'integral', Interval(4_000_000_000, 5_000_000_000))
        # 大域外间隔也不发生反序int64差wrap。
        result = self._compare(series, spec)
        # 无观测原因独立，不是空选择。
        self.assertEqual((result.value, result.reason, result.requested_coverage), (None, 'no_observation', 0.))
        # 零请求时没有面积，分母比例应为None。
        result = self._compare(series, replace(spec, window=Interval(1, 1)))
        # 不把零长度视作全FALSE积分0。
        self.assertEqual((result.value, result.reason, result.value_coverage, result.requested_coverage), (None, 'zero_length_window', None, None))
        # 请求超实际EOF，实际部分能量保留但必须partial。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 5_000_000_000))
        # 原行域3秒，不能给最后边界补2秒。
        result = self._memory_compare(_memory(), spec)
        # requested coverage按3/5而非值有效比例1。
        self.assertEqual((result.value, result.status, result.requested_coverage, result.value_coverage), (16000., 'partial', .6, 1.))
        # strict请求不足不输出部分正常值。
        result = self._memory_compare(_memory(), replace(spec, partial_policy='strict'))
        # 实际范围仍保留，而非静默改请求。
        self.assertEqual((result.value, result.actual_window), (None, Interval(0, 3_000_000_000)))

    def test_t25_t43_known_false_empty_selection(self):
        """FALSE是已知排除；全FALSE积分0而空样本统计null。

        参数: 无；充分观测3秒域，实际BOOL选择及有效或无效值。
        返回: None。
        异常: 空/未知混同或覆盖不符由unittest报告。
        """
        # T25排除第一秒4000J，保留两秒6000W。
        rows = ((0, {'raw': 4000., 'selected': False}), (1_000_000_000, {'raw': 6000., 'selected': True}), (3_000_000_000, {'raw': 0., 'selected': False}))
        # 当前数值/选择同绑定，真实条件更新不丢。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 3_000_000_000))
        # 全链条件选择，而非直接修改数组mask冒充配置。
        result = self._memory_compare(_memory(rows=rows), spec, condition='selected')
        # FALSE不记为条件缺失。
        self.assertEqual((result.value, result.condition_coverage, result.selected_duration_ns, result.status), (12000., 1., 2_000_000_000, 'complete'))
        # T43有充分条件证据，即使数值全部无效也可证明所选集合为空。
        series = _series((None, None, None), conditions=(False, False, False))
        # 两政策均为可核实0，不是未知补零。
        for policy in ('report', 'strict'):
            # 选择规则本身全部已知FALSE。
            result = self._compare(series, replace(spec, partial_policy=policy))
            # 完整空选择积分，原数值无效coverage仍保留。
            self.assertEqual((result.value, result.reason, result.status, result.value_coverage, result.condition_coverage), (0., 'empty_selection', 'complete', 0., 1.))
            # 原无效原因仍可审查，不用结果0掩盖输入MISSING。
            self.assertTrue(result.quality & Q.MISSING)
        # 空统计没有正常极值或平均，不能把sum空值0套用mean。
        for operation in ('sample_minimum', 'sample_maximum', 'sample_mean'):
            # 同样全FALSE证据。
            result = self._compare(series, replace(spec, operation=operation))
            # 所有选中样本为空，原因明确。
            self.assertEqual((result.value, result.reason, result.selected_duration_ns), (None, 'empty_selection', 0))
        # EOF裁剪的全FALSE仍不能证明完整请求为空。
        result = self._compare(series, replace(spec, window=Interval(0, 5_000_000_000)))
        # 不能用部分已知FALSE冒充完整积分0。
        self.assertIsNone(result.value)

    def test_t44_condition_unknown_and_invalid_selected_values(self):
        """部分选择未知有可核实1000J；全未知或选中值全无效null。

        参数: 无；P1000W，条件TRUE[0,1)/UNKNOWN[1,2)。
        返回: None。
        异常: partial/strict/空未知政策或未知范围失败由unittest报告。
        """
        # 值持续可用，条件在1秒实际invalid，不当FALSE。
        rows = ((0, {'raw': 1000., 'selected': True}), (1_000_000_000, {'selected': None}))
        # 观测2秒，原行无最后假周期。
        bindings = _memory(rows=rows, end=2_000_000_000)
        # 两条件独立执行与值相交。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 2_000_000_000))
        # report保留第一秒面积，不把第二秒未知补0。
        result = self._memory_compare(bindings, spec, condition='selected')
        # 真值1000J，条件coverage1/2。
        self.assertEqual((result.value, result.condition_coverage, result.status), (1000., .5, 'partial'))
        # UNKNOWN范围按真实边界保留。
        self.assertEqual(result.condition_unknown_ranges, (Interval(1_000_000_000, 2_000_000_000),))
        # strict同样覆盖事实，但value=null。
        result = self._memory_compare(bindings, replace(spec, partial_policy='strict'), condition='selected')
        # 严格政策不改变条件unknown。
        self.assertEqual((result.value, result.status, result.condition_coverage), (None, 'indeterminate', .5))
        # 全条件未知不能返回正常0。
        series = _series((1000., 1000.), conditions=(None, None), times=(0, 2_000_000_000))
        # 数值有效不是选择已知证据。
        result = self._compare(series, spec)
        # 原因unknown_selection，而非empty_selection。
        self.assertEqual((result.value, result.reason, result.condition_coverage), (None, 'unknown_selection', 0.))
        # 选择已知TRUE但值全无效，不能套全FALSE零值规则。
        result = self._compare(_series((None, None), conditions=(True, True), times=(0, 2_000_000_000)), spec)
        # 无有效选中值明确null。
        self.assertEqual((result.value, result.selected_duration_ns), (None, 0))

    def test_samples_are_actual_updates_and_integer_extremes(self):
        """样本口径排除保持/TTL/条件独自更新，整数极值不转float。

        参数: 无；采样0/1/3秒和落在样本间的窗口。
        返回: None。
        异常: 样本数量/极值/mean或精度失败由unittest报告。
        """
        # M1统计明确samples，窗口左端的4000保持值不是样本。
        window = Interval(500_000_000, 2_500_000_000)
        # 0秒样本排除，1秒6000真实，3秒末样本排除。
        for operation in ('sample_minimum', 'sample_maximum', 'sample_mean'):
            # 原行桥接轴新增0.5/2.5，但actual=False。
            result = self._memory_compare(_memory(), CalculationDefinition('stats', operation, window))
            # 不与min_time或time_weighted_mean混同。
            self.assertEqual((result.value, result.valid_sample_count), (6000., 1))
        # 只有保持值而无区间内真实更新时，无samples统计。
        result = self._memory_compare(_memory(), CalculationDefinition('stats', 'sample_minimum', Interval(100_000_000, 900_000_000)))
        # ZOH仍有有效时间，但不产生合成样本。
        self.assertEqual((result.value, result.reason, result.value_coverage), (None, 'no_samples', 1.))
        # 条件独自更新不增加数值样本数。
        rows = ((0, {'raw': 10., 'selected': True}), (1_000_000_000, {'selected': True}))
        # 同一数值保持，不额外重复采样。
        result = self._memory_compare(_memory(rows=rows, end=2_000_000_000), CalculationDefinition('stats', 'sample_mean', Interval(0, 2_000_000_000)), condition='selected')
        # 只有0秒真实数值依赖更新。
        self.assertEqual((result.value, result.valid_sample_count), (10., 1))
        # UINT64大整数极值允许精确比较，不能无声提升float。
        series = _series((2 ** 64-1, 2 ** 53+1, 0), dtype=D.UINT64, unit='1')
        # min/max只用真实样本，3秒0不在窗口内。
        for operation, expected in (('sample_minimum', 2 ** 53+1), ('sample_maximum', 2 ** 64-1)):
            # 全程数值正常，整数极值保持native int。
            result = self._compare(series, CalculationDefinition('stats', operation, Interval(0, 3_000_000_000)))
            # 严格精确整数手算。
            self.assertEqual(result.value, expected)
            # 不接受近似float碰巧显示相同数值。
            self.assertIs(type(result.value), int)
        # 积分/mean须将输入转float，两个奇数均不精确，因此null。
        for operation in ('integral', 'sample_mean'):
            # 拒绝无声精度丢失，未知范围/原因保存。
            result = self._compare(series, CalculationDefinition('stats', operation, Interval(0, 3_000_000_000)))
            # 完全无可核实浮点结果，不补0。
            self.assertIsNone(result.value)
            # 既有合法质量位，不新增破坏schema。
            self.assertTrue(result.quality & Q.PRECISION_LOSS)

    def test_numeric_failures_and_extreme_time_clipping(self):
        """面积溢出/下溢显式未知，大绝对时间1ns和域外差不wrap。

        参数: 无；有限极值数值及int64极值短域。
        返回: None。
        异常: 值/质量/精确区间或负例失败由unittest报告。
        """
        # 有限输入1e308乘2秒面积溢出，不能输出Inf。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 2_000_000_000))
        # 只有一有效连续区间，失效后无可信面积。
        result = self._compare(_series((1e308, 0.), times=(0, 2_000_000_000)), spec)
        # 算术失败与有效0不同。
        self.assertIsNone(result.value)
        # 明确非有限面积质量。
        self.assertTrue(result.quality & Q.NONFINITE)
        # 最小正float乘1ns被舍掉，不能当正常0。
        spec = replace(spec, window=Interval(0, 1))
        # 普通输入值有限，但面积不可核实。
        result = self._compare(_series((5e-324, 0.), times=(0, 1)), spec)
        # 明确下溢精度失效。
        self.assertEqual((result.value, result.value_coverage), (None, 0.))
        # 精度原因不靠隐藏warning/忽略assert。
        self.assertTrue(result.quality & Q.PRECISION_LOSS)
        # 接近int64最大，相邻1ns面积仍按精确整数差计算。
        start = 2 ** 63-4
        # 独立手算1000W*1e-9s=1e-6J。
        series = _series((1000., 0.), times=(start, start+1))
        # 大绝对时间不能先转float导致差为0。
        result = self._compare(series, replace(spec, window=Interval(start, start+1)))
        # 整数1ns差精确，面积float仅允许相对1e-12的IEEE舍入。
        self.assertAlmostEqual(result.value, 1e-6, delta=1e-18)
        # 请求负最小附近完全在正极值观测域外，反序端点差不wrap。
        result = self._compare(series, replace(spec, window=Interval(-(2 ** 63), -(2 ** 63)+1)))
        # 无观测，而非错误大面积。
        self.assertEqual((result.value, result.reason), (None, 'no_observation'))

    def test_random_input_policy_and_validation(self):
        """固定种子值/条件/窗口对照，非法shape/单位/绑定不静默修正。

        参数: 无；48个短完整轴及typed配置负例。
        返回: None。
        异常: 差分由unittest报告，非法配置由assertRaises检查。
        """
        # 固定数据身份，原单位和更新标志明确。
        rng = random.Random(174344)
        # 不同真/假/未知交集与两覆盖政策均需独立数值一致。
        for _ in range(48):
            # 小整数ns递增，每步10—100ms，和值跨度安全。
            times, time = [0], 0
            # 最后样本只有边界，不增加周期。
            for _ in range(7):
                # 请求端点可落采样间而非仅对齐整行。
                time += rng.randint(1, 10) * 10_000_000
                # 输入保持当前真实顺序。
                times.append(time)
            # 同型FLOAT64，明确未知和值正负零。
            values = tuple(None if rng.randrange(5) == 0 else float(rng.randrange(-100, 101)) for _ in times)
            # 各位置选择三值独立，FALSE不计未知。
            conditions = tuple(rng.choice((True, False, None)) for _ in times)
            # 额外timer明确actual=False，不影响真实样本统计。
            series = _series(values, conditions=conditions, times=tuple(times), actual=tuple(bool(rng.randrange(2)) for _ in times))
            # 请求可超过EOF，也可能无交集，均不补数据。
            window = Interval(rng.randrange(0, time+1), time+rng.randrange(1, 100))
            # 全部M1算子分别执行两政策，不放宽完整事实。
            for operation in ('integral', 'sample_minimum', 'sample_maximum', 'sample_mean'):
                # 数值归约允许IEEE小误差，其他字段必须一致。
                for policy in ('report', 'strict'):
                    # 两内核从相同输入独立执行，不拿一方作真值。
                    self._compare(series, CalculationDefinition('random', operation, window, policy))
        # 不提供模糊mean，不提前实现M2时间统计。
        with self.assertRaises(ValueError):
            # 调用者必须选择已有明确算子。
            CalculationDefinition('stats', 'mean', Interval(0, 1))
        # 不能把单位不同维度强行转换。
        with self.assertRaises(ValueError):
            # J→V不是相同物理类别。
            compute_reference(_series((1., 1., 1.)), CalculationDefinition('bad', 'integral', Interval(0, 1), output_unit='V'))
        # shape与时间不匹配不能靠truncate补齐。
        with self.assertRaises(ValueError):
            # 同长typed输入为真实执行门槛。
            replace(_series((1., 2., 3.)), values=(ScalarValue(1., D.FLOAT64),))
        # 与另一输入数据相同名称的条件不能重用旧执行绑定。
        bindings = _memory(rows=((0, {'raw': 1., 'selected': True}),))
        # 同一个变量名但另一实际原值改变完整身份。
        other = _memory(rows=((0, {'raw': 2., 'selected': True}),))
        # 执行前拒绝跨输入binding，不能继承上次任务选择。
        with self.assertRaises(ValueError):
            # 当前两个表达式实际身份不相同。
            compute_memory_reference(compile_expression('power', bindings), CalculationDefinition('bad', 'integral', Interval(0, 1)), condition=compile_expression('selected', other))
