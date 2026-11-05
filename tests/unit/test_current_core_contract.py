"""核对唯一v4入口、显式null拒绝与isclose现行容差尺度。

只用内存数据，不创建日志或修改用户配置；参考和NumPy各自计算手算真值。
"""

from dataclasses import replace
import unittest

import numpy as np

from chronaxis import AnalysisPlan, PlanValidationError
from chronaxis.core import SignalDefinition, SignalDType as D
from chronaxis.core.calculations import CalculationDefinition, CalculationConversion
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import compile_expression
from chronaxis.core.expression_reference import evaluate_memory_reference
from chronaxis.core.expression_numpy import evaluate_memory_numpy
from chronaxis.core.message_binding import ExpressionParameter, MessageDeclarations
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.types import TimeType
from chronaxis.core.function_contracts import builtin_function_specs
from chronaxis.core.numeric import normalize_reference
from test_expression_units_v4 import bindings
from test_unit_configuration_v4 import configuration


class CurrentCoreContractTests(unittest.TestCase):
    """旧版本不能借低层默认、空绑定或直接计划构造重新启用。"""

    def test_low_level_defaults_and_old_version_rejection(self):
        """省略版本得到4；显式旧版本和布尔伪整数在各声明入口均拒绝。"""
        factories = (
            lambda **kw: SignalDefinition('v', 'sensor', 'raw', D.FLOAT64, 'V', 1, **kw),
            lambda **kw: ExpressionParameter('period', .1, 's', **kw),
            lambda **kw: CalculationDefinition('energy', 'integral', Interval(0, 1), **kw),
        )
        for factory in factories:
            self.assertEqual(factory().config_version, 4)
            for version in (3, 2, True):
                with self.subTest(factory=factory, version=version), self.assertRaises(ValueError):
                    factory(config_version=version)
        self.assertEqual(CalculationConversion('V', 1).version, 4)
        with self.assertRaises(ValueError):
            CalculationConversion('V', 1, version=3)
        with self.assertRaises(ValueError):
            builtin_function_specs(3)
        self.assertIn('lookup', builtin_function_specs())

    def test_empty_and_parameter_only_bindings_default_to_current(self):
        """空声明也有当前规则身份；参数独立使用新单位目录。"""
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'start')
        empty = DeclarationBindings('session', clock, None,
                                    (DeclaredSource('sensor', clock, 'memory'),), ())
        self.assertEqual(empty.config_version, 4)
        messages = MessageDeclarations(empty, 'sensor', (ExpressionParameter('period', 1, 'us'),))
        self.assertEqual(messages.config_version, 4)
        self.assertEqual(messages.parameters[0].unit_status, 'verified')
        with self.assertRaises(ValueError):
            replace(empty, config_version=3)

    def test_plan_and_signal_null_are_explicit_errors(self):
        """null不等同省略，显式系数不能绕过同一单位类型校验。"""
        for extra in ({}, {'scale': 1}, {'offset': 0}, {'scale': 1, 'offset': 0}):
            raw = configuration()
            raw['signals'][0]['conversion'] = {'input_unit': None, **extra}
            with self.subTest(extra=extra), self.assertRaisesRegex(PlanValidationError, '省略'):
                AnalysisPlan.from_dict(raw)
        raw = configuration()
        definition = AnalysisPlan.from_dict(raw).signals[0].definition
        self.assertEqual(normalize_reference(definition, 1500).value, 1.5)
        del raw['signals'][0]['conversion']
        self.assertEqual(normalize_reference(AnalysisPlan.from_dict(raw).signals[0].definition, 1500).value, 1500)
        plan = AnalysisPlan.from_dict(raw)
        with self.assertRaises(ValueError):
            replace(plan, config_version=3)
        raw['config_version'] = 3
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(raw)

    def test_isclose_absolute_tolerance_uses_canonical_unit(self):
        """500mV和501mV差0.001V；atol=.1按V为真，.0001按V为假。"""
        data = bindings(('v', 'mV', 500.))
        cases = (
            ('isclose(v,501,atol=0.1,rtol=0)', True),
            ('isclose(v,501,atol=0.0001,rtol=0)', False),
            ('isclose(to_unit(v,"mV"),501,atol=0.1,rtol=0)', True),
        )
        for expression, expected in cases:
            compiled = compile_expression(expression, data)
            scalar = evaluate_memory_reference(compiled, (0,))[0].value
            array = evaluate_memory_numpy(compiled, np.array([0], dtype=np.int64)).value
            self.assertEqual(compiled.root.args[2].unit, 'V')
            self.assertTrue(scalar.valid)
            self.assertEqual(scalar.value, expected)
            self.assertEqual(array.values.tolist(), [expected])
        with self.assertRaisesRegex(ValueError, '字面量'):
            compile_expression('isclose(v,501,atol=quantity(0.1,"mV"),rtol=0)', data)


if __name__ == '__main__':
    unittest.main()
