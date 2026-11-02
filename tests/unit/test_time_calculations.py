"""用手算真值和独立双后端核对时间统计、TRUE时长及最低覆盖率。

输入为声明单位、纳秒窗口和三值有效性的合成保持序列；输出为unittest断言。
流程覆盖样本与时间口径差异、裁剪、缺失、EOF、精度和类型错误。
复用既有测试夹具与完整结果差分助手，不复用被测数值；不读旧日志或写文件。
此模块不证明真实数据验收、生产内存预算或性能提升。
"""

# 冻结模型变体保留原输入，测试基准来自下方明示手算。
from dataclasses import replace
# 标准断言报告所有失败，不跳过边界。
import unittest
# 固定种子扩展裁剪与未知组合；手算基准由前面测试单独给出。
import random
# 独立输入/完整事实比较助手，不继承旧测试集合。
import test_calculations as fixtures
from test_calculations import _series
# 当前typed请求、窗口和输入类型。
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
# 两个真实计算入口直接检查拒绝行为。
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy


class TimeCalculationTests(unittest.TestCase):
    """核对连续时间统计的不变量；数值容差仅由既有差分助手用于浮点舍入。

    实例没有跨测试信号状态，所有输入为局部合成数据。
    """

    def compare(self, series, spec):
        """执行独立双后端并比较全部结果字段。

        参数: series为完整CalculationSeries，spec为当前指标。
        返回: 参考结果，供额外手算断言。
        异常: 数值或事实不一致由unittest报告。
        """
        # 仅复用测试断言，不共享实现计算。
        return fixtures.CalculationTests._compare(self, series, spec)

    def test_time_weight_and_clipped_hold(self):
        """2保持1秒、8保持3秒得到时间均值6.5，样本均值5。

        参数: 无；合成W序列。
        返回: None。
        异常: 边界或双后端差异产生断言失败。
        """
        # EOF的99不贡献时间；裁剪[.5,2)保留2*.5+8*1，均值6。
        series = _series((2., 8., 99.), times=(0, 1_000_000_000, 4_000_000_000))
        spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 4_000_000_000))
        self.assertEqual(self.compare(series, spec).value, 6.5)
        self.assertEqual(self.compare(series, replace(spec, operation='sample_mean')).value, 5.)
        clipped = replace(spec, window=Interval(500_000_000, 2_000_000_000))
        self.assertEqual(self.compare(series, clipped).value, 6.)
        # 左边界保持2纳入时间极值，但没有伪造真实样本。
        self.assertEqual(self.compare(series, replace(clipped, operation='min_time')).value, 2.)
        self.assertEqual(self.compare(series, replace(clipped, operation='max_time')).value, 8.)
        self.assertEqual(self.compare(series, replace(clipped, operation='sample_minimum')).value, 8.)

    def test_missing_condition_and_value_policy(self):
        """未知值和未知条件分别降低覆盖，report保留部分值而strict返回None。

        参数: 无；3秒域内首秒2W，后两秒未知。
        返回: None。
        异常: 缺失政策或双实现差异由断言报告。
        """
        # 手算仅首秒可核实，均值2且值覆盖1/3。
        spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 3_000_000_000), minimum_coverage=.9)
        result = self.compare(_series((2., None, 9.)), spec)
        self.assertEqual((result.value, result.status, result.value_coverage, result.coverage_status), (2., 'partial', 1/3, 'indeterminate'))
        # 门槛恰好等于覆盖率也充分，且不改变诊断均值或partial状态。
        equal = self.compare(_series((2., None, 9.)), replace(spec, minimum_coverage=1/3))
        self.assertEqual((equal.value, equal.status, equal.coverage_status), (2., 'partial', 'sufficient'))
        self.assertEqual(result.value_unknown_ranges, (Interval(1_000_000_000, 3_000_000_000),))
        self.assertIsNone(self.compare(_series((2., None, 9.)), replace(spec, partial_policy='strict')).value)
        # 条件未知不能视为FALSE；没有任何已知选择时结果为None。
        result = self.compare(_series((2., 8., 9.), conditions=(True, None, False)), spec)
        self.assertEqual((result.value, result.condition_coverage, result.status), (2., 1/3, 'partial'))
        self.assertIsNone(self.compare(_series((2., 8., 9.), conditions=(None, None, False)), spec).value)

    def test_false_selection_and_zero_window(self):
        """完整FALSE选择的统计为空，零窗口和无观测独立解释。

        参数: 无；包括全未知主值的FALSE选择。
        返回: None。
        异常: 空选择被伪造为统计零时断言失败。
        """
        # 完整FALSE证据不要求主值有效，但不能形成平均值零。
        series = _series((None, None, None), conditions=(False, False, False))
        spec = CalculationDefinition('mean', 'time_weighted_mean', series.observation)
        result = self.compare(series, spec)
        self.assertEqual((result.value, result.reason, result.condition_coverage), (None, 'empty_selection', 1.))
        # 零窗口、无交集不能借全FALSE证明正常值。
        self.assertEqual(self.compare(series, replace(spec, window=Interval(1, 1))).reason, 'zero_length_window')
        self.assertEqual(self.compare(series, replace(spec, window=Interval(4_000_000_000, 5_000_000_000))).reason, 'no_observation')

    def test_duration_true_false_unknown(self):
        """TRUE首秒、FALSE后两秒的时长为1秒；全未知不能返回零。

        参数: 无；无量纲BOOL信号及外部选择条件。
        返回: None。
        异常: UNKNOWN政策或覆盖差异产生断言失败。
        """
        # 已知FALSE仍计值覆盖，末点TRUE不增加时长。
        spec = CalculationDefinition('active', 'duration', Interval(0, 3_000_000_000))
        result = self.compare(_series((True, False, True), dtype=D.BOOL, unit='1'), spec)
        self.assertEqual((result.value, result.unit, result.selected_duration_ns, result.value_coverage), (1., 's', 1_000_000_000, 1.))
        self.assertEqual(self.compare(_series((False, False, True), dtype=D.BOOL, unit='1'), spec).value, 0.)
        self.assertIsNone(self.compare(_series((None, None, None), dtype=D.BOOL, unit='1'), spec).value)
        # 已知FALSE+未知只能报告部分零，不能报完整零；严格政策清空数值。
        series = _series((False, None, True), dtype=D.BOOL, unit='1')
        self.assertEqual((self.compare(series, spec).value, self.compare(series, spec).status), (0., 'partial'))
        self.assertIsNone(self.compare(series, replace(spec, partial_policy='strict')).value)
        # 外部选择全部未知，即使主BOOL已知也无可核实结果。
        series = _series((True, False, True), dtype=D.BOOL, unit='1', conditions=(None, None, None))
        self.assertIsNone(self.compare(series, spec).value)
        self.assertEqual(self.compare(replace(series, conditions=_series((0., 0., 0.), conditions=(False, False, False)).conditions), spec).value, 0.)

    def test_eof_and_large_absolute_nanosecond(self):
        """EOF外不补周期，大绝对时间仍准确计算1纳秒TRUE时长。

        参数: 无；纳秒坐标来自合法int64范围。
        返回: None。
        异常: 请求覆盖或时间精度差异由断言报告。
        """
        # 请求5秒仅观测3秒，均值按已知观测计算，标partial。
        spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 5_000_000_000))
        result = self.compare(_series((2., 8., 0.)), spec)
        self.assertEqual((result.value, result.requested_coverage, result.status), (6., .6, 'partial'))
        self.assertIsNone(self.compare(_series((2., 8., 0.)), replace(spec, partial_policy='strict')).value)
        # 先整数求差，绝对时间不转float造成1ns消失。
        origin = 8_000_000_000_000_000_000
        series = _series((True, False, False), times=(origin, origin+1, origin+3), dtype=D.BOOL, unit='1')
        result = self.compare(series, CalculationDefinition('duration', 'duration', series.observation))
        self.assertEqual((result.value, result.selected_duration_ns), (1e-9, 1))

    def test_integer_extrema_and_mean_precision(self):
        """时间极值保留int64/uint64，浮点平均拒绝不可精确转换的大整数。

        参数: 无；明确定宽边界数据。
        返回: None。
        异常: 静默精度丢失或双后端差异由断言报告。
        """
        # 时间极值无需转换为float，大整数按原生值返回。
        for dtype, low, high in ((D.INT64, -(2**63), 2**63-1), (D.UINT64, 0, 2**64-1)):
            series = _series((low, high, 0), dtype=dtype)
            spec = CalculationDefinition('extreme', 'min_time', series.observation)
            self.assertEqual(self.compare(series, spec).value, low)
            self.assertEqual(self.compare(series, replace(spec, operation='max_time')).value, high)
        # 2**53+1不能精确转float64，不伪造均值。
        series = _series((2**53+1, 2**53+1, 0), dtype=D.INT64)
        result = self.compare(series, CalculationDefinition('mean', 'time_weighted_mean', series.observation))
        self.assertIsNone(result.value)
        self.assertTrue(result.quality & Q.PRECISION_LOSS)

    def test_finite_mean_and_unit_conversion(self):
        """规范化权重避免有限均值的中间面积溢出，单位仅最终转换一次。

        参数: 无；float64大值及kW合成输入。
        返回: None。
        异常: 错误溢出、下溢或单位结果由断言报告。
        """
        # 原值乘3秒可溢出，但时间均值1e308可核实。
        series = _series((1e308, 1e308, 0.))
        result = self.compare(series, CalculationDefinition('mean', 'time_weighted_mean', series.observation))
        self.assertAlmostEqual(result.value / 1e308, 1.)
        self.assertEqual(result.quality, Q.NONE)
        # 明确kW→W，权重归约后仅一次乘1000。
        series = _series((2., 8., 0.), unit='kW')
        result = self.compare(series, CalculationDefinition('mean', 'time_weighted_mean', series.observation, output_unit='W'))
        self.assertEqual((result.value, result.unit), (6000., 'W'))
        # 非零权重乘最小次正规值消失，不能报告正常0。
        series = _series((5e-324, 0., 0.))
        result = self.compare(series, CalculationDefinition('mean', 'time_weighted_mean', series.observation))
        self.assertEqual(result.reason, 'calculation_failed')
        self.assertTrue(result.quality & Q.PRECISION_LOSS)

    def test_fixed_seed_clipping_and_unknown_differential(self):
        """固定种子扩展不规则纳秒间隔、窗口与未知组合的独立差分。

        参数: 无；32组明示合成数据，数值不作真实日志结论。
        返回: None。
        异常: 两后端任意数值或覆盖/质量/范围不一致由断言报告。
        """
        rng = random.Random(20261009)
        # 小数值避免无关浮点溢出，专门核对裁剪/选择与覆盖边界。
        for _ in range(32):
            times = [0]
            for _ in range(6):
                times.append(times[-1] + rng.randrange(1, 1000))
            values = tuple(rng.choice((None, -8., 0., 2., 9.)) for _ in times)
            conditions = tuple(rng.choice((True, False, None)) for _ in times)
            series = _series(values, conditions=conditions, times=tuple(times))
            start, end = sorted((rng.randrange(-10, times[-1]+11), rng.randrange(-10, times[-1]+11)))
            # 相同输入交给独立归约，整结构差分不只比数值。
            for operation in ('min_time', 'max_time', 'time_weighted_mean'):
                self.compare(series, CalculationDefinition('calculation', operation, Interval(start, end), partial_policy=rng.choice(('report', 'strict'))))
            # BOOL原值的FALSE与UNKNOWN不同，时长不用数字占位判断。
            booleans = tuple(rng.choice((True, False, None)) for _ in times)
            series = _series(booleans, conditions=conditions, times=tuple(times), unit='1', dtype=D.BOOL)
            self.compare(series, CalculationDefinition('calculation', 'duration', Interval(start, end)))

    def test_operator_dtype_and_coverage_validation(self):
        """算子类型、duration单位和最低覆盖率在执行前明确拒绝错误。

        参数: 无；故意不匹配的typed配置。
        返回: None。
        异常: 未拒绝配置或非法阈值由断言报告。
        """
        # BOOL不能算数值平均，数字不能当TRUE时长；select不返回标量。
        for compute in (compute_reference, compute_numpy):
            with self.assertRaises(ValueError):
                compute(_series((True, False, True), dtype=D.BOOL, unit='1'), CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 3_000_000_000)))
            with self.assertRaises(ValueError):
                compute(_series((2., 8., 0.)), CalculationDefinition('duration', 'duration', Interval(0, 3_000_000_000)))
            with self.assertRaises(ValueError):
                compute(_series((True, False, True), dtype=D.BOOL, unit='W'), CalculationDefinition('duration', 'duration', Interval(0, 3_000_000_000)))
            with self.assertRaises(ValueError):
                compute(_series((2., 8., 0.)), CalculationDefinition('rows', 'select', Interval(0, 3_000_000_000)))
        # bool/非有限/域外/巨大整数不能作为覆盖率比例。
        for threshold in (True, float('nan'), float('inf'), -.1, 1.1, 10**500):
            with self.assertRaises(ValueError):
                CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 3), minimum_coverage=threshold)


# 直接运行同一验收集；不创建缓存或额外资源。
if __name__ == '__main__':
    unittest.main()
