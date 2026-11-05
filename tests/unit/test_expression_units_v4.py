"""从合成原值验证v4自动单位换算、常量锚点、温度与版本隔离。

每组数据交给独立参考和NumPy后端，另与手算结果比较。输入时刻为0ns，
保持范围为2ns；不读文件、不依赖DBC、不把新单位注册当作整项DSL交付。
"""

# 合成绑定沿已验证测试夹具，数值期望由本文件明确给出。
import unittest
import numpy as np
from test_expression import _bindings
from chronaxis.core import SignalDefinition, SignalDType as D, QualityFlag as Q
from chronaxis.core.expression import compile_expression, DerivedDefinition
from chronaxis.core.expression_reference import evaluate_memory_reference
from chronaxis.core.expression_numpy import evaluate_memory_numpy


def bindings(*entries, derived_names=()):
    """按名称、单位、值构造明确版本4的单条原始记录。

    参数: entries为(name,unit,value)序列，derived_names为派生名tuple。
    返回: 真实SignalBindings；整数和float类型按输入明确选择。
    异常: 原模型错误直接传播。
    """
    # 每个原字段与别名相同，避免在单位测试引入额外映射差异。
    definitions = tuple(SignalDefinition(name, 'sensor', name, D.FLOAT64 if type(value) is float else D.INT64,
                                        unit, 2, config_version=4) for name, unit, value in entries)
    return _bindings(rows=({name: value for name, _, value in entries},), definitions=definitions,
                     derived_names=derived_names)


class ExpressionUnitsV4Tests(unittest.TestCase):
    """验证编译时单位与运行数值、dtype和质量始终匹配。

    每个案例独享绑定和编译树，后端不共享求值结果。
    """

    def evaluate(self, text, data, expected, unit, *, target=None, derived=(), quality=Q.NONE):
        """执行两个数值后端，并核对手算值和目标标签。

        参数: text/data为表达式和绑定，expected/unit为独立期望；target/derived为编译选项。
            quality为期望质量，非NONE时不比较无效占位数值。
        返回: 编译对象，供调用方额外核对dtype或身份。
        异常: 任何后端差异或期望不符触发断言失败。
        """
        # 参考按标量归一化；数组按列独立归一化和计算。
        compiled = compile_expression(text, data, unit=target, derived=derived)
        scalar = evaluate_memory_reference(compiled, (0,))[0]
        array = evaluate_memory_numpy(compiled, np.array([0], dtype=np.int64))
        self.assertEqual(compiled.root.unit, unit)
        self.assertEqual(scalar.value.valid, quality == Q.NONE)
        self.assertEqual(array.value.valid.tolist(), [quality == Q.NONE])
        self.assertEqual(scalar.value.quality, quality)
        self.assertEqual(int(array.value.quality[0]), int(quality))
        self.assertEqual(scalar.value.dtype, array.value.dtype)
        if quality == Q.NONE:
            self.assertAlmostEqual(scalar.value.value, expected)
            self.assertAlmostEqual(array.value.values[0].item(), expected)
        return compiled

    def test_compatible_signals_and_fractional_integer_conversion(self):
        """不同时间/电压单位自动统一，整数毫秒不能丢失小数。

        参数: 无。
        返回: None；手算1000ms+2s=3s，500mV+2V=2.5V。
        异常: 数值或dtype不符时断言失败。
        """
        # 两个原始信号均为整数；只有单位比例导致float提升。
        self.evaluate('a+b', bindings(('a','ms',1000),('b','s',2)), 3., 's')
        self.evaluate('a+b', bindings(('a','mV',500),('b','V',2)), 2.5, 'V')
        result = self.evaluate('a', bindings(('a','ms',1500)), 1.5, 's')
        self.assertIs(result.root.dtype, D.FLOAT64)

    def test_constants_keep_declared_scale(self):
        """裸阈值先按信号声明单位解释，不能把500mV当500V。

        参数: 无。
        返回: None；500mV+500mV=1V，500mV<600mV。
        异常: 阈值错误缩放时断言失败。
        """
        data = bindings(('v','mV',500))
        self.evaluate('v+500', data, 1., 'V')
        self.evaluate('v<600', data, True, '1')
        self.evaluate('600>v', data, True, '1')
        self.evaluate('v*2', data, 1., 'V')
        with self.assertRaises(ValueError):
            compile_expression('v+to_unit(1,"1")', data)
        self.evaluate('to_unit(t,"℃")', bindings(('t','℃',15.0)), 15.0, 'degC')
        self.evaluate('quantity(3,"V*A")', data, 3, 'W')

    def test_explicit_quantities_and_result_units(self):
        """带单位常量与显式目标同步转换数值，不仅更换标签。

        参数: 无。
        返回: None；1kW*2s=2000J，50%*10A=5A。
        异常: 倍率遗漏或重复时断言失败。
        """
        data = bindings(('v','V',2))
        self.evaluate('quantity(1,"kW")*quantity(2,"s")', data, 2000, 'J')
        self.evaluate('quantity(50,"%")*quantity(10,"A")', data, 5., 'A')
        self.evaluate('v+quantity(500,"mV")', data, 2500., 'mV', target='mV')
        self.evaluate('to_unit(v,"mV")', data, 2000, 'mV')
        self.evaluate('to_unit(to_unit(v,"mV"),"V")', data, 2., 'V')
        self.evaluate('v+quantity(0.5,"V")', data, 2.5, 'V')
        self.evaluate('quantity(0.5,"V")+v', data, 2.5, 'V')

    def test_temperature_roles_and_zero_kelvin(self):
        """摄氏偏移只用于绝对温度，温差没有273.15偏移。

        参数: 无。
        返回: None；80C=353.15K，80C-20C=60delta_K，绝对零度合法。
        异常: 偏移重复或零值被误判无效时断言失败。
        """
        data = bindings(('hot','degC',80.),('cold','degC',20.),('zero','degC',-273.15))
        self.evaluate('hot>75', data, True, '1')
        self.evaluate('hot-cold', data, 60., 'delta_K')
        self.evaluate('hot+quantity(5,"delta_degC")', data, 358.15, 'K')
        self.evaluate('quantity(5,"delta_K")+hot', data, 358.15, 'K')
        self.evaluate('to_unit(zero,"K")', data, 0., 'K')
        self.evaluate('to_unit(hot,"K")*2', data, 706.3, 'K')
        for text in ('hot+cold', 'hot*2', 'hot/2', 'quantity(5,"delta_K")-hot'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                compile_expression(text, data)

    def test_isclose_uses_canonical_absolute_tolerance(self):
        """绝对容差按统一后的V解释，交换不同标签不改变容差尺度。

        参数: 无。
        返回: None；1V与1.05V在0.1V容差内。
        异常: 容差被当成0.1mV时断言失败。
        """
        data = bindings(('a','mV',1000.),('b','V',1.05))
        self.evaluate('isclose(a,b,atol=0.1,rtol=0)', data, True, '1')
        self.evaluate('isclose(b,a,atol=0.1,rtol=0)', data, True, '1')
        # 手册的0.1mV容差必须写成0.0001V；相差1mV时两个声明尺度均不通过。
        self.evaluate('isclose(v,501,atol=0.0001,rtol=0)',
                      bindings(('v', 'mV', 500.)), False, '1')
        self.evaluate('isclose(v,0.501,atol=0.0001,rtol=0)',
                      bindings(('v', 'V', 0.5)), False, '1')

    def test_precision_and_derived_declared_anchor(self):
        """大整数转换不静默舍入，派生显式单位继续作为后续阈值锚点。

        参数: 无。
        返回: None；超精度输入无效，2V派生为2000mV后加500得到2.5V。
        异常: 精度丢失漏报或派生阈值单位变化时断言失败。
        """
        self.evaluate('a', bindings(('a','ms',2**53+1)), None, 's', quality=Q.PRECISION_LOSS)
        data = bindings(('v','V',2.), derived_names=('mv',))
        self.evaluate('mv+500', data, 2.5, 'V', derived=(DerivedDefinition('mv','v','mV'),))

    def test_kind_safety_signatures_and_version_isolation(self):
        """新入口拒绝不兼容量种和自由语法，旧入口仍拒绝新增函数。

        参数: 无。
        返回: None；版本冲突、函数签名、单位未知与原混合dtype均拒绝。
        异常: 违法表达式通过时断言失败。
        """
        data = bindings(('v','V',2),('a','A',3),('f','V',2.))
        for text in ('v+a', 'v+f', 'to_unit(v,"A")', 'to_unit(v,"unknown")',
                     'quantity(v,"V")', 'quantity(1+2,"V")', 'quantity(True,"V")',
                     'to_unit(v,unit="mV")', 'to_unit(v,a)', 'v.real', 'v**2'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                compile_expression(text, data)
        with self.assertRaises(ValueError):
            compile_expression('v', data, config_version=3)
        with self.assertRaises(ValueError):
            SignalDefinition('old', 'sensor', 'raw_i', D.FLOAT64, 'A', 2, config_version=3)
        reserved = _bindings(definitions=(SignalDefinition('quantity','sensor','raw_i',D.FLOAT64,'A',2),))
        with self.assertRaises(ValueError):
            compile_expression('quantity', reserved)



# 单独执行仅运行合成单位用例，不加载真实业务文件。
if __name__ == '__main__':
    unittest.main()
