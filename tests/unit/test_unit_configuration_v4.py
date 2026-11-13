"""检查版本4在公开配置入口只换算一次，并保留版本3行为。

输入是合成内存配置和临时DBC，输出是计划、两种归一化结果及拒绝断言。
手算1500ms=1.5s、0℃=273.15K作为真值；大整数另核质量原因。
不读取用户日志；临时文件仅用于DBC元数据和配置重载，测试结束自动清理。
"""

# 独立合成输入与临时目录保证测试之间没有共享可变配置。
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from chronaxis import AnalysisPlan, PlanValidationError
from chronaxis.configuration.resolution import resolved_configuration
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.message_binding import ExpressionParameter, MessageDeclarations
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.numeric import normalize_reference
from chronaxis.core.normalize_numpy import normalize_numpy
from chronaxis.core.types import SignalDType as D, QualityFlag, TimeType
from chronaxis.core.unit_conversion import affine_conversion, converted_dtype


def configuration(version=4):
    """建立单信号毫秒到秒转换配置。

    参数: version为目标配置版本，默认4。
    返回: 独立dict；1500为整数输入，目标s不要求用户改dtype。
    异常: 无；构造本函数不解析计划。
    """
    # 没有额外分析节点，专门核对声明编译，不把计划通过冒充运行验收。
    return dict(config_version=version, dataset=dict(name='units'),
        sources=[dict(name='table', source_type='memory',
            rows=[dict(time='0s', values={'raw': 1500})])],
        signals=[dict(name='elapsed', field='raw', dtype='int64', unit='s',
            valid_for='1s', conversion=dict(input_unit='ms'))])


class UnitConfigurationV4Tests(unittest.TestCase):
    """验证声明、源单位推导、版本身份与完整系数的稳定重载。

    每项计划局部创建，数值参考和数组入口独立执行同一手算样本。
    """

    def test_automatic_fraction_promotes_and_normalizes_both_backends(self):
        """整数毫秒自动提升为浮点秒，两个后端都得到1.5。

        参数: 无。返回: None。异常: 类型、倍率或双后端结果偏差触发断言。
        """
        # 类型在编译时确定；不能要求1500能整除1000才能运行。
        plan = AnalysisPlan.from_dict(configuration())
        signal = plan.signals[0].definition
        self.assertEqual((signal.config_version, signal.dtype, signal.input_dtype), (4, D.FLOAT64, D.INT64))
        self.assertTrue(signal.unit_conversion_promoted)
        self.assertEqual((signal.scale, signal.offset, signal.unit_status), (.001, 0, 'verified'))
        self.assertEqual(normalize_reference(signal, 1500).value, 1.5)
        array = normalize_numpy(signal, np.array([1500], dtype=np.int64))
        self.assertEqual(array.values.tolist(), [1.5])
        self.assertTrue(array.valid[0])

    def test_explicit_coefficients_are_complete_not_extra(self):
        """旧完整系数不会再乘一次，新版错误显式系数仍拒绝。

        参数: 无。返回: None。异常: 重复缩放或静默修正显式错误触发断言。
        """
        raw = configuration()
        raw['signals'][0]['conversion']['scale'] = .001
        signal = AnalysisPlan.from_dict(raw).signals[0].definition
        self.assertEqual(normalize_reference(signal, 1500).value, 1.5)
        # 只写offset也属于显式完整转换；不能把缺省scale自动修成.001。
        for conversion in ({'input_unit': 'ms', 'scale': 1}, {'input_unit': 'ms', 'offset': 0}):
            raw['signals'][0]['conversion'] = conversion
            with self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(raw)

    def test_empty_conversion_does_not_force_explicit_identity(self):
        """空对象等于未填系数；现单位不变时保持整数类型。

        参数: 无。返回: None。异常: 空对象误判显式系数或类型变化触发断言。
        """
        raw = configuration()
        raw['signals'][0]['conversion'] = {}
        signal = AnalysisPlan.from_dict(raw).signals[0].definition
        self.assertEqual((signal.dtype, signal.scale, signal.offset), (D.INT64, 1, 0))
        self.assertFalse(signal.unit_conversion_promoted)

    def test_unknown_units_require_explicit_different_label_conversion(self):
        """同名未知标签可原样使用，异名未知关系不能猜恒等换算。

        参数: 无。返回: None。异常: 自动猜测未知单位关系或显式政策丢失触发断言。
        """
        raw = configuration()
        raw['signals'][0].update(unit='custom', conversion={'input_unit': 'custom'})
        signal = AnalysisPlan.from_dict(raw).signals[0].definition
        self.assertEqual((signal.scale, signal.offset, signal.unit_status), (1, 0, 'unverified'))
        raw['signals'][0]['unit'] = 'V'
        with self.assertRaisesRegex(PlanValidationError, '完整scale/offset'):
            AnalysisPlan.from_dict(raw)
        # 明确系数可以保留，但不能把未知关系标成verified。
        raw['signals'][0]['conversion'].update(scale=2, offset=3)
        explicit = AnalysisPlan.from_dict(raw).signals[0].definition
        self.assertEqual((explicit.scale, explicit.offset, explicit.unit_status), (2, 3, 'unverified'))

    def test_temperature_offset_and_large_integer_quality(self):
        """温度偏移只应用一次，大整数提升不允许静默丢精度。

        参数: 无。返回: None。异常: 合法绝对零被当下溢或大整数被默默舍入触发断言。
        """
        raw = configuration()
        raw['signals'][0].update(unit='K', conversion={'input_unit': 'degC'})
        signal = AnalysisPlan.from_dict(raw).signals[0].definition
        self.assertEqual(normalize_reference(signal, 0).value, 273.15)
        self.assertEqual(normalize_reference(signal, -273.15).value, 0)
        promoted = AnalysisPlan.from_dict(configuration()).signals[0].definition
        for actual in (normalize_reference(promoted, 2 ** 53 + 1),):
            self.assertFalse(actual.valid)
            self.assertTrue(actual.quality & QualityFlag.PRECISION_LOSS)
        array = normalize_numpy(promoted, np.array([2 ** 53 + 1], dtype=np.int64))
        self.assertFalse(array.valid[0])
        self.assertTrue(int(array.quality[0]) & int(QualityFlag.PRECISION_LOSS))

    def test_integer_affine_and_logical_types_do_not_promote(self):
        """整倍率保持整数，bool和enum不会变成普通数值。

        参数: 无。返回: None。异常: 不必要或非法提升触发断言。
        """
        self.assertEqual(affine_conversion('s', 'ms'), (1000, 0, 'verified'))
        self.assertIs(converted_dtype(D.INT64, 1000, 0), D.INT64)
        self.assertIs(converted_dtype(D.BOOL, .001, 0), D.BOOL)
        self.assertIs(converted_dtype(D.ENUM, .001, 0), D.ENUM)
        # 用户把整数系数写成1.0时仍应走安全整数路径，不舍入大整数。
        signal = SignalDefinition('value', 'table', 'raw', D.INT64, 's', 1,
            scale=1.0, offset=0.0, config_version=4)
        self.assertIs(type(signal.scale), int)
        self.assertEqual(normalize_reference(signal, 2 ** 53 + 1).value, 2 ** 53 + 1)

    def test_version_three_and_low_level_explicit_contract(self):
        """旧配置不自动换算，低层v4定义也不能把scale=1猜成省略。

        参数: 无。返回: None。异常: 旧语义被改变或低层猜系数触发断言。
        """
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(configuration(3))
        with self.assertRaises(ValueError):
            SignalDefinition('elapsed', 'table', 'raw', D.FLOAT64, 's', 1,
                input_unit='ms', config_version=4)
        low = SignalDefinition('elapsed', 'table', 'raw', D.FLOAT64, 's', 1,
            input_unit='ms', scale=.001, config_version=4)
        self.assertFalse(low.unit_conversion_promoted)

    def test_empty_and_parameter_only_bindings_keep_version(self):
        """无信号声明和仅参数消息也保留显式4，版本混用拒绝。

        参数: 无。返回: None。异常: 空绑定降级或混版本被接受触发断言。
        """
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'test')
        source = DeclaredSource('table', clock, 'fixture')
        old = DeclarationBindings('run', clock, None, (source,), ())
        new = replace(old, config_version=4)
        self.assertEqual(old.config_version, 4)
        self.assertEqual(old.identity, new.identity)
        params = (ExpressionParameter('duration', 1500, 'us', config_version=4),)
        messages = MessageDeclarations(new, 'table', params)
        self.assertEqual(messages.config_version, 4)
        self.assertEqual(params[0].unit_status, 'verified')
        with self.assertRaises(ValueError):
            MessageDeclarations(old, 'table', params, config_version=3)
        plan = AnalysisPlan.from_dict(configuration())
        with self.assertRaises(ValueError):
            replace(plan.bindings, config_version=3)

    def test_resolved_configuration_round_trip_preserves_input_dtype(self):
        """导出完整默认值后仍用原输入类型声明，重新加载只换算一次。

        参数: 无。返回: None。异常: 配置重载改变倍率、类型来源或值触发断言。
        """
        with TemporaryDirectory(prefix='chronaxis-units-') as folder:
            path = Path(folder) / 'units.json'
            path.write_text(json.dumps(configuration()), encoding='utf-8')
            raw = resolved_configuration(path, defaults=True)
            self.assertEqual(raw['signals'][0]['dtype'], 'int64')
            reloaded = AnalysisPlan.from_dict(raw).signals[0].definition
            self.assertTrue(reloaded.unit_conversion_promoted)
            self.assertEqual(normalize_reference(reloaded, 1500).value, 1.5)

    def test_dbc_target_unit_still_loads_original_unit_once(self):
        """显式目标V不能遮住DBC的mV；两个字段共用一次元数据读取。

        参数: 无。返回: None。异常: 漏读原单位、重复DBC加载或重缩放触发断言。
        """
        import cantools
        with TemporaryDirectory(prefix='chronaxis-unit-dbc-') as folder:
            dbc = Path(folder) / 'sample.dbc'
            dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 2 Node\n'
                ' SG_ Voltage : 0|16@1+ (1,0) [0|65535] "mV" Node\n', encoding='utf-8')
            raw = dict(config_version=4, dataset=dict(name='dbc_units'),
                sources=[dict(path=str(Path(folder) / 'input.asc'), dbc_by_channel={'1': str(dbc)})],
                signals=[dict(name=name, field=dict(frame_id=256, signal='Voltage'),
                    dtype='int64', unit='V', valid_for='1s') for name in ('voltage', 'voltage_copy')])
            with patch('cantools.database.load', wraps=cantools.database.load) as load:
                plan = AnalysisPlan.from_dict(raw)
            self.assertEqual(load.call_count, 1)
            signal = plan.signals[0].definition
            self.assertEqual((signal.input_unit, signal.scale, signal.dtype), ('mV', .001, D.FLOAT64))
            self.assertEqual(normalize_reference(signal, 1500).value, 1.5)

    def test_message_configuration_parameters_inherit_analysis_version(self):
        """消息参数继承分析版本，无信号参数任务仍保持4。

        参数: 无。返回: None。异常: 参数或空绑定降级为3触发断言。
        """
        from test_plan_message_calculations import legacy_config
        # 固定原输入单位，静态分析不必读取不存在的DBC。
        raw = legacy_config()
        raw['config_version'] = 4
        raw['signals'][0]['conversion'] = {'input_unit': 'W'}
        plan = AnalysisPlan.from_dict(raw)
        calculation = plan.message_calculations[0]
        self.assertTrue(all(item.config_version == 4 for item in calculation.parameters))
        self.assertEqual(calculation.expr.bindings.config_version, 4)
        # 仅参数公式不构造伪信号或借默认3；单位常量计算仍按当前版本。
        raw['signals'] = []
        raw['message_calculations'][0].update(expr='energy', parameters={'energy': {'value': 1, 'unit': 'J'}})
        only = AnalysisPlan.from_dict(raw).message_calculations[0]
        self.assertEqual(only.expr.bindings.config_version, 4)
        self.assertEqual(only.expr.dependencies, ())



# 单文件运行同样使用标准unittest，不增加独立测试入口行为。
if __name__ == '__main__':
    unittest.main()
