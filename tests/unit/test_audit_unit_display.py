"""核对复合单位显示的可读形式、回读语义和不变的数值尺度。

使用工程单位手算与有限指数枚举；不读取业务日志，不用显示文字代替量种检查。
"""
from fractions import Fraction
from itertools import product
import unittest
from chronaxis.core.unit_registry import (
    REGISTRY_VERSION, canonical_unit, conversion, output_label, resolve_unit, square_root,
)


class AuditUnitDisplayTests(unittest.TestCase):
    """规范名称可以缩短，但量种、倍率、温度角色及解析边界仍须一致。"""

    def test_readable_electrical_compounds_and_round_trip(self):
        """采用W/J写复合式并完整回读。参数: 无。返回: None。异常: 语义/显示断言失败。"""
        examples = {'s/(V*A)': 's/W', 'V*A/s': 'W/s', '1/(V*A)': '1/W',
                    '1/(V*A*s)': '1/J', 'V^2*A^2': 'W^2', 'V*A*s^2': 'J*s',
                    'N*m': 'N*m', 'N*m/s': 'N*m/s', 'V/A': 'Ohm'}
        for spelling, expected in examples.items():
            with self.subTest(spelling=spelling):
                original = resolve_unit(spelling)
                canonical = canonical_unit(original)
                self.assertEqual(canonical.symbol, expected)
                self.assertEqual(canonical_unit(resolve_unit(expected)), canonical)
                self.assertEqual(conversion(original, canonical), (canonical.scale, Fraction(0)))
        self.assertEqual(REGISTRY_VERSION, 'chronaxis-units-v4.2')

    def test_mixed_signed_exponents_round_trip_without_changing_kind(self):
        """343组正负指数及32边界回读。参数: 无。返回: None。异常: 解析/量种断言失败。"""
        triples = list(product(range(-3, 4), repeat=3)) + [(32,32,32),(-32,-32,-32),(32,31,-32)]
        for voltage, current, time in triples:
            spelling = f'V^{voltage}*A^{current}*s^{time}'
            with self.subTest(unit=spelling):
                original = resolve_unit(spelling)
                canonical = canonical_unit(original)
                decoded = resolve_unit(canonical.symbol)
                self.assertEqual(canonical_unit(decoded), canonical)
                self.assertEqual(decoded.kind, original.kind)
                self.assertEqual(decoded.dimensions, original.dimensions)
                self.assertEqual(decoded.scale.factor, 1)

    def test_scaled_units_and_temperature_are_not_relabelled_without_conversion(self):
        """尺度和温度不随名称折叠改变。参数: 无。返回: None。异常: 换算/量种断言失败。"""
        scaled = resolve_unit('mA*V/s')
        canonical = canonical_unit(scaled)
        self.assertEqual(canonical.symbol, 'W/s')
        self.assertEqual(output_label(scaled, 'mA*V/s'), 'mA*V/s')
        self.assertEqual(conversion(scaled, canonical)[0].factor, Fraction(1, 1000))
        self.assertEqual(conversion(resolve_unit('degC'), resolve_unit('K'))[1], Fraction(27315,100))
        for a,b in [('N*m','J'),('N*m/s','W'),('delta_K','K')]:
            with self.subTest(source=a,target=b), self.assertRaises(ValueError):
                conversion(resolve_unit(a),resolve_unit(b))
        for spelling, expected in [('A^2','A'),('K^2','K'),('delta_K^2','delta_K')]:
            self.assertEqual(canonical_unit(square_root(resolve_unit(spelling))).symbol,expected)
        with self.assertRaises(ValueError):
            square_root(resolve_unit('W'))


if __name__ == '__main__':
    unittest.main()
