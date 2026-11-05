"""用明确数值验证v4指标单位转换，同时保留v3兼容范围。

样例仅含有限合成内存信号；温度、倍率、积分和精度的期望由手算给出。
同一真值分别检查参考和数组完整核，以及三类流式归约，不读写真实文件。
"""

from dataclasses import replace
import unittest
from tempfile import TemporaryDirectory
from chronaxis.core.calculations import CalculationDefinition, CalculationSeries, calculation_conversion, calculation_unit
from chronaxis.core.calculations_reference import compute_reference, select_reference
from chronaxis.core.calculations_numpy import compute_numpy, select_numpy
from chronaxis.core.sample_reduction_reference import ReferenceSampleReduction
from chronaxis.core.sample_reduction_numpy import NumpySampleReduction
from chronaxis.core.time_reduction_reference import ReferenceTimeReduction
from chronaxis.core.time_reduction_numpy import NumpyTimeReduction
from chronaxis.core.conditional_time_reduction_reference import ReferenceConditionalTimeReduction
from chronaxis.core.conditional_time_reduction_numpy import NumpyConditionalTimeReduction
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.record_time_calculation import RecordTimeCalculation
from chronaxis.results.budget import ResourceBudget
from chronaxis import AnalysisPlan, PlanValidationError


class CalculationUnitV4Tests(unittest.TestCase):
    """各后端分别面对手算期望，不用一后端输出作为另一后端答案。"""

    def series(self, values, unit, dtype=D.FLOAT64, conditions=None, times=(0, 1, 4)):
        """构造三点信号，末点只结束观测、不参与样本或面积。

        参数: values及unit为原数据；dtype为数值或BOOL；conditions为可选布尔列。
        返回: 已验证CalculationSeries。异常: 模型错误传播。
        """
        # None明确缺失，不能在温度换算时变成一个正常绝对值。
        rows = tuple(ScalarValue(value, dtype) if value is not None else
                     ScalarValue(None, dtype, False, Q.MISSING) for value in values)
        condition_rows = None if conditions is None else tuple(ScalarValue(value, D.BOOL) for value in conditions)
        return CalculationSeries(Interval(times[0], times[-1]), times, rows, (True,) * len(times), unit, condition_rows)

    def spec(self, operation, unit=None, window=Interval(0, 4)):
        """建立v4请求，使用旧位置参数并显式指定新版本。

        参数: operation为已实现操作，unit为目标，window为真实范围。
        返回: CalculationDefinition。异常: 配置非法时传播。
        """
        return CalculationDefinition('result', operation, window, output_unit=unit, config_version=4)

    def test_full_memory_temperature_means_and_extrema(self):
        """0℃和100℃的样本均值50℃，按1:3时长加权为75℃。

        参数: 无。返回: None。异常: 单位、偏移或均值顺序错误导致断言失败。
        """
        series = self.series((0.0, 100.0, 999.0), 'degC')
        expected = {'sample_minimum': 273.15, 'sample_maximum': 373.15, 'sample_mean': 323.15,
                    'min_time': 273.15, 'max_time': 373.15, 'time_weighted_mean': 348.15}
        for backend in (compute_reference, compute_numpy):
            for operation, value in expected.items():
                with self.subTest(backend=backend.__name__, operation=operation):
                    result = backend(series, self.spec(operation))
                    self.assertAlmostEqual(result.value, value)
                    self.assertEqual(result.unit, 'K')
                    self.assertFalse(result.quality & (Q.NONFINITE | Q.PRECISION_LOSS))

    def test_streaming_temperature_all_reducers(self):
        """各流式均值先完整归约，再加一次273.15，极值也只换算一次。

        参数: 无。返回: None。异常: 重复偏移、丢偏移或分母错误导致断言失败。
        """
        sample = self.series((0.0, 100.0, 999.0), 'degC')
        for cls in (ReferenceSampleReduction, NumpySampleReduction):
            for operation, expected in (('sample_minimum', 273.15), ('sample_maximum', 373.15), ('sample_mean', 323.15)):
                kernel = cls(self.spec(operation), sample.unit, D.FLOAT64)
                kernel.push(sample)
                self.assertAlmostEqual(kernel.finish().value, expected)
        for cls in (ReferenceTimeReduction, NumpyTimeReduction,
                    ReferenceConditionalTimeReduction, NumpyConditionalTimeReduction):
            series = replace(sample, conditions=(ScalarValue(True, D.BOOL),) * 3) if 'Conditional' in cls.__name__ else sample
            for operation, expected in (('min_time', 273.15), ('max_time', 373.15), ('time_weighted_mean', 348.15)):
                denominator = 4 if operation == 'time_weighted_mean' else None
                kernel = cls(self.spec(operation), series.unit, D.FLOAT64, selected_duration_ns=denominator)
                kernel.push(series)
                number = kernel.finish()
                self.assertEqual(number.unit, 'K')
                self.assertAlmostEqual(number.value, expected)

    def test_affine_zero_and_missing_are_distinct(self):
        """-273.15℃得到有效0K，缺失温度仍为空，不能凭偏移补值。

        参数: 无。返回: None。异常: 合法抵消误报下溢或空值补零导致断言失败。
        """
        for backend in (compute_reference, compute_numpy):
            zero = backend(self.series((-273.15, -273.15, 0.0), 'degC'), self.spec('sample_mean'))
            self.assertEqual(zero.value, 0.0)
            self.assertFalse(zero.quality & Q.PRECISION_LOSS)
            empty = backend(self.series((None, None, None), 'degC'), self.spec('sample_mean'))
            self.assertIsNone(empty.value)

    def test_integral_compound_units_and_offset_rejection(self):
        """2kW保持3秒得到6000J；摄氏积分必须先明确换绝对尺度。

        参数: 无。返回: None。异常: 重复倍率或积分误加温度偏移导致断言失败。
        """
        series = self.series((2.0, 2.0, 0.0), 'kW', times=(0, 1_000_000_000, 3_000_000_000))
        for backend in (compute_reference, compute_numpy):
            result = backend(series, self.spec('integral', window=series.observation))
            self.assertEqual((result.value, result.unit), (6000.0, 'J'))
            charge = backend(replace(series, unit='A'), self.spec('integral', 'Ah', series.observation))
            self.assertAlmostEqual(charge.value, 6 / 3600)
            with self.assertRaises(ValueError):
                backend(replace(series, unit='degC'), self.spec('integral', window=series.observation))
        # 二元兼容入口不得把非零偏移悄悄忽略。
        with self.assertRaises(ValueError):
            calculation_unit(self.spec('sample_mean', 'K'), 'degC')

    def test_select_value_dtype_quality_and_units(self):
        """1500ms输出1.5s；大整数小数转换标精度不足，整数倍率保持精确。

        参数: 无。返回: None。异常: 标签与值不同步或静默丢精度导致断言失败。
        """
        for select in (select_reference, select_numpy):
            series = self.series((1500, 2000, 0), 'ms', D.INT64)
            rows = tuple(select(series, self.spec('select', 's')))
            self.assertEqual([(r.value.value, r.value.dtype, r.unit) for r in rows], [(1.5, D.FLOAT64, 's'), (2.0, D.FLOAT64, 's')])
            big = self.series((2 ** 53 + 1, 1, 0), 'ms', D.INT64)
            row = next(select(big, self.spec('select', 's')))
            self.assertFalse(row.value.valid)
            self.assertTrue(row.quality & Q.PRECISION_LOSS)
            exact = next(select(self.series((2 ** 53 + 1, 1, 0), 's', D.INT64), self.spec('select', 'ms')))
            self.assertEqual(exact.value.value, (2 ** 53 + 1) * 1000)
            self.assertIs(exact.value.dtype, D.INT64)

    def test_select_identity_preserves_boolean_and_unknown_units(self):
        """恒等选择不把布尔或未登记标签变成新数值单位。

        参数: 无。返回: None。异常: 不必要转换破坏类型或未知单位导致断言失败。
        """
        for select in (select_reference, select_numpy):
            booleans = self.series((True, False, False), '1', D.BOOL)
            self.assertIs(next(select(booleans, self.spec('select'))).value.dtype, D.BOOL)
            with self.assertRaises(ValueError):
                tuple(select(booleans, self.spec('select', '%')))
            unknown = self.series((1, 2, 0), 'custom', D.INT64)
            self.assertEqual(next(select(unknown, self.spec('select'))).value.value, 1)

    def test_version_and_torque_are_not_guessed(self):
        """版本必须明确，力矩不能只因物理量纲相同被标成能量。

        参数: 无。返回: None。异常: 非法版本或量种转换被接受时断言失败。
        """
        for version in (True, 2, 5, '4'):
            with self.assertRaises(ValueError):
                CalculationDefinition('bad', 'sample_mean', Interval(0, 1), config_version=version)
        with self.assertRaises(ValueError):
            calculation_conversion(self.spec('sample_mean', 'J'), 'N*m')

    def test_explicit_unit_labels_are_public_spellings(self):
        """复合目标不输出内部括号描述，原子别名使用规范名称。

        参数: 无。返回: None。异常: 输出标签与可读公开拼写不一致时断言失败。
        """
        for source, target, expected in (('m/s', 'm/s', 'm/s'), ('V/s', 'mV/s', 'mV/s'),
                                         ('N*m', 'N·m', 'N*m'), ('K', '℃', 'degC')):
            self.assertEqual(calculation_conversion(self.spec('sample_mean', target), source).unit, expected)

    def test_public_integral_requires_explicit_absolute_temperature_scale(self):
        """默认把温度显示为K不能自动放行摄氏积分，显式K及温差允许。

        参数: 无。返回: None。异常: 配置校验绕过偏移积分限制或误拒合法尺度时断言失败。
        """
        # 仅静态配置校核；实际积分和温度数值另由两后端手算专项验证。
        raw = dict(config_version=4, dataset=dict(name='temperature'),
            sources=[dict(name='table', source_type='memory',
                rows=[dict(time='0s', values={'raw': 0.0}), dict(time='2s', values={'raw': 100.0})])],
            signals=[dict(name='temperature', field='raw', dtype='float64', unit='degC', valid_for='3s')],
            calculations=[dict(name='area', operation='integral', expr='temperature')])
        with self.assertRaisesRegex(PlanValidationError, 'to_unit'):
            AnalysisPlan.from_dict(raw)
        raw['calculations'][0]['expr'] = 'to_unit(temperature,"K")'
        self.assertEqual(AnalysisPlan.from_dict(raw).calculations[0].unit, 's*K')
        raw['calculations'][0]['expr'] = 'temperature'
        raw['signals'][0]['unit'] = 'delta_K'
        self.assertEqual(AnalysisPlan.from_dict(raw).calculations[0].unit, 's*delta_K')

    def test_record_time_mean_converts_after_spooled_reduction(self):
        """生产记录流均值跨两批仍只加一次偏移，关闭后释放自有RAM。

        参数: 无。返回: None。异常: 暂存归约漏换算、重复换算或费用未释放时断言失败。
        """
        # 此临时目录只保存本测试的必要均值项，两个后端各自生成和关闭owner。
        with TemporaryDirectory(prefix='chronaxis-unit-mean-') as folder:
            for backend in ('reference', 'numpy'):
                budget = ResourceBudget()
                owner = RecordTimeCalculation(budget, self.spec('time_weighted_mean'),
                    'degC', D.FLOAT64, None, backend=backend, batch_intervals=1, work_dir=folder)
                try:
                    owner.consume(((0, ScalarValue(0.0, D.FLOAT64)), (1, ScalarValue(100.0, D.FLOAT64))))
                    owner.consume(((4, ScalarValue(999.0, D.FLOAT64)),))
                    result = owner.finish()
                    self.assertEqual(result.unit, 'K')
                    self.assertAlmostEqual(result.value, 348.15)
                finally:
                    owner.close()
                self.assertEqual(budget.ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
