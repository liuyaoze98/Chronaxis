"""用手算单位关系检查版本4的单位目录、转换和受限文本解析。

输入为明确的工程单位文字及不可变单位元数据，输出为 unittest 断言。
先核对目录与精确倍率，再检查温度角色、量种隔离和复合运算；最后验证
未知单位、非法语法、资源上限及版本3的原14单位表仍保持原行为。
这里只测试编译期元数据，不读取日志、调用DBC或声称配置入口已支持新版本。
依赖标准库和被测单位模块，没有文件写入，也不调用NumPy作为参考答案。
"""

# 分数和圆周率只用于独立的手算期望，不执行被测转换器中的数值路径。
from fractions import Fraction
from math import pi
# 冻结声明的不可变性属于计划身份保证，不允许调用方修改一次编译后的规则。
from dataclasses import FrozenInstanceError
import unittest

# 新旧单位入口分别导入，确保新增能力不会改变已发布版本的默认注册范围。
from chronaxis.core.unit_registry import (
    Scale, canonical_unit, conversion, divide, multiply, resolve_unit,
    square, square_root,
)
from chronaxis.core.unit_conversion import validate_conversion_v4, require_config_version


class UnitRegistryTests(unittest.TestCase):
    """核对单位本身的含义，不用目录条数代替正确性验证。

    每个测试只构造本地不可变对象；没有共享可变状态或待关闭资源。
    数值真值使用基本单位定义和手算比例，组合测试另验证结合与逆运算。
    """

    def unit(self, text):
        """取得本测试明确要求存在的已知单位。

        参数: text为合同列明的单位或合法组合文字。
        返回: 已解析的Unit，用于继续验证其关系。
        异常: 解析错误传播；未登记会触发断言失败而不是跳过用例。
        """
        # 必须真正得到已知模型，不能让后续None比较掩盖漏登记。
        result = resolve_unit(text)
        self.assertIsNotNone(result, text)
        return result

    def assert_conversion(self, source, target, factor, offset=0, pi_power=0):
        """将单位转换与独立给出的精确公式比较。

        参数: source/target为单位文字；factor/offset为手算有理系数，
            pi_power为倍率中π的整数指数，默认0。
        返回: None；断言目标值等于原值乘倍率再加偏移。
        异常: 被测函数的拒绝传播，错误系数触发断言失败。
        """
        # 分开检查系数和偏移，避免只验证一个碰巧抵消错误的样本。
        scale, actual_offset = conversion(self.unit(source), self.unit(target))
        self.assertEqual(scale.factor, Fraction(factor), (source, target))
        self.assertEqual(scale.pi_power, pi_power, (source, target))
        self.assertEqual(actual_offset, Fraction(offset), (source, target))

    def test_catalogue_factors_and_default_scales(self):
        """每个目录成员的默认基准和倍率都采用明确工程定义。

        参数: 无。
        返回: None；全部目录项均可解析并转换到各自基准。
        异常: 注册缺失、倍率或默认名称错误触发断言失败。
        """
        # 表中的分数为工程定义；它们不从被测注册表生成，防止漏项自证。
        cases = (
            ('1', '1', 1), ('%', '1', Fraction(1, 100)),
            ('V', 'V', 1), ('mV', 'V', Fraction(1, 1000)),
            ('A', 'A', 1), ('mA', 'A', Fraction(1, 1000)),
            ('W', 'W', 1), ('kW', 'W', 1000),
            ('J', 'J', 1), ('Wh', 'J', 3600), ('kWh', 'J', 3600000),
            ('A*s', 'A*s', 1), ('Ah', 'A*s', 3600),
            ('s', 's', 1), ('ms', 's', Fraction(1, 1000)),
            ('us', 's', Fraction(1, 1000000)), ('ns', 's', Fraction(1, 1000000000)),
            ('K', 'K', 1), ('delta_K', 'delta_K', 1), ('delta_degC', 'delta_K', 1),
            ('Ohm', 'Ohm', 1), ('mOhm', 'Ohm', Fraction(1, 1000)),
            ('kOhm', 'Ohm', 1000), ('MOhm', 'Ohm', 1000000),
            ('m', 'm', 1), ('m/s', 'm/s', 1), ('m/s^2', 'm/s^2', 1),
            ('Hz', 'Hz', 1), ('rad', 'rad', 1), ('rad/s', 'rad/s', 1),
            ('N', 'N', 1), ('N*m', 'N*m', 1),
            ('Pa', 'Pa', 1), ('kPa', 'Pa', 1000), ('bar', 'Pa', 100000),
        )
        # 默认单位应稳定，不由用户先写哪一个兼容单位决定。
        for source, target, factor in cases:
            with self.subTest(source=source):
                self.assert_conversion(source, target, factor)
                self.assertEqual(canonical_unit(self.unit(source)).symbol, target)

    def test_all_registered_aliases_preserve_meaning(self):
        """已登记的排版别名保留同一量种、倍率和温度偏移。

        参数: 无。
        返回: None；所有合同别名与规范文字恒等转换。
        异常: 别名漏登或错误映射触发断言失败。
        """
        # 摄氏符号和温差符号分列，避免Δ被去除后冒充绝对温度。
        aliases = {
            'A·s': 'A*s', 'µs': 'us', 'μs': 'us',
            '°C': 'degC', '℃': 'degC', 'ΔK': 'delta_K',
            'Δ°C': 'delta_degC', 'Δ℃': 'delta_degC',
            'Ω': 'Ohm', 'Ω': 'Ohm', 'mΩ': 'mOhm',
            'kΩ': 'kOhm', 'MΩ': 'MOhm', 'm/s²': 'm/s^2',
            '°': 'deg', 'N·m': 'N*m',
        }
        # 外侧空白不改变已登记名字；内部符号仍由语法解析。
        for alias, canonical in aliases.items():
            with self.subTest(alias=alias):
                self.assert_conversion(alias, canonical, 1)
                self.assertEqual(self.unit('  ' + alias + '  '), self.unit(alias))

    def test_si_dimensions_have_independent_physical_truth(self):
        """物理维度按质量、长度、时间、电流、温度排列。

        参数: 无。
        返回: None；基本工程单位的SI指数符合定义。
        异常: 指数顺序或定义错误触发断言失败。
        """
        # 这些SI定义独立于新模型的量种基，不靠同一个乘除实现推导预期。
        expected = {
            'V': (1, 2, -3, -1, 0), 'A': (0, 0, 0, 1, 0),
            's': (0, 0, 1, 0, 0), 'W': (1, 2, -3, 0, 0),
            'J': (1, 2, -2, 0, 0), 'N': (1, 1, -2, 0, 0),
            'Pa': (1, -1, -2, 0, 0), 'Ohm': (1, 2, -3, -2, 0),
            'K': (0, 0, 0, 0, 1), 'delta_K': (0, 0, 0, 0, 1),
            'rad': (0, 0, 0, 0, 0),
        }
        # 同一物理维度不等于转换许可；许可另由量种测试覆盖。
        for name, dimensions in expected.items():
            with self.subTest(unit=name):
                self.assertEqual(self.unit(name).dimensions, dimensions)

    def test_temperature_offsets_and_differences(self):
        """绝对摄氏转换加273.15，温差转换不添加任何偏移。

        参数: 无。
        返回: None；正反转换、默认尺度和温度角色均正确。
        异常: 绝对温度与温差混淆触发断言失败。
        """
        # 0℃=273.15K、100℃=373.15K均由同一个精确仿射关系得到。
        self.assert_conversion('degC', 'K', 1, Fraction(27315, 100))
        self.assert_conversion('K', 'degC', 1, Fraction(-27315, 100))
        self.assert_conversion('delta_degC', 'delta_K', 1)
        self.assertEqual(canonical_unit(self.unit('degC')).symbol, 'K')
        # 相同维度仍不能让10℃绝对温度被解释成10K温差。
        for source, target in (('K', 'delta_K'), ('degC', 'delta_degC'),
                               ('delta_K', 'K'), ('delta_degC', 'degC')):
            with self.subTest(source=source, target=target), self.assertRaises(ValueError):
                conversion(self.unit(source), self.unit(target))

    def test_angle_and_rotation_keep_pi_symbolic(self):
        """度和转速使用明确π倍率，不转换成周期频率。

        参数: 无。
        返回: None；角度正反和转速倍率符合一周2π弧度。
        异常: 丢失π或错误周期定义触发断言失败。
        """
        # 180deg=πrad，60rpm=2πrad/s；避免把rpm直接当Hz。
        self.assert_conversion('deg', 'rad', Fraction(1, 180), pi_power=1)
        self.assert_conversion('rad', 'deg', 180, pi_power=-1)
        self.assert_conversion('rpm', 'rad/s', Fraction(1, 30), pi_power=1)
        scale, offset = conversion(self.unit('rpm'), self.unit('rad/s'))
        self.assertAlmostEqual(60 * float(scale.factor) * pi ** scale.pi_power + float(offset), 2 * pi)
        self.assertEqual(canonical_unit(self.unit('deg')).symbol, 'rad')
        self.assertEqual(canonical_unit(self.unit('rpm')).symbol, 'rad/s')

    def test_same_dimension_does_not_erase_quantity_kind(self):
        """力矩、能量、频率和角速度不能仅因SI指数相同互换。

        参数: 无。
        返回: None；已登记但量种不同的关系明确拒绝。
        异常: 误开放跨量种转换触发断言失败。
        """
        # 第一层断言确保此测试真正覆盖同维度、不同量种，而非普通维度冲突。
        for source, target in (('N*m', 'J'), ('N', 'J/m'), ('N*m/s', 'W'),
                               ('Hz', 'rad/s'), ('rad', '1'), ('K', 'delta_K')):
            with self.subTest(source=source, target=target):
                left, right = self.unit(source), self.unit(target)
                self.assertEqual(left.dimensions, right.dimensions)
                self.assertNotEqual(left.kind, right.kind)
                with self.assertRaises(ValueError):
                    conversion(left, right)

    def test_electrical_energy_is_independent_of_parentheses(self):
        """电压、电流、时间的两种乘法括号都得到焦耳。

        参数: 无。
        返回: None；括号及交换顺序不改单位关系或倍率。
        异常: 配对硬编码造成结合错误时断言失败。
        """
        # 这里检验元数据代数，不授权执行器重新结合浮点数值运算。
        voltage, current, duration = self.unit('V'), self.unit('A'), self.unit('s')
        products = (
            multiply(multiply(voltage, current), duration),
            multiply(voltage, multiply(current, duration)),
            multiply(duration, multiply(current, voltage)),
            self.unit('V*(A*s)'), self.unit('(V*A)*s'),
        )
        for product in products:
            with self.subTest(product=product.symbol):
                self.assertEqual(canonical_unit(product).symbol, 'J')
                scale, offset = conversion(product, self.unit('J'))
                self.assertEqual((scale.factor, scale.pi_power, offset), (Fraction(1), 0, Fraction(0)))

    def test_scaled_products_retain_their_numeric_factor(self):
        """组合mV、mA和kW时不能只改标签而遗漏倍率。

        参数: 无。
        返回: None；千分之一、百万分之一和千倍关系均正确。
        异常: 元数据丢失倍率时断言失败。
        """
        # 1000mV*1000mA=1W；2kW*3s=6000J只依赖这两个单位倍率。
        self.assert_conversion('mV*mA', 'W', Fraction(1, 1000000))
        self.assert_conversion('kW*s', 'J', 1000)
        self.assert_conversion('mA*s', 'A*s', Fraction(1, 1000))
        self.assert_conversion('mV/A', 'Ohm', Fraction(1, 1000))
        self.assert_conversion('%*A', 'A', Fraction(1, 100))

    def test_quotients_and_inverse_relations(self):
        """除法同时消去量种指数和倍率，组合结果可再次解析。

        参数: 无。
        返回: None；电阻、电流和频率的基本逆运算成立。
        异常: 分母结合或规范文本错误触发断言失败。
        """
        # 1/(mA/A)的倍率是1000，不能因最终无量纲而强制变成1。
        self.assert_conversion('1/(mA/A)', '1', 1000)
        self.assert_conversion('V/A', 'Ohm', 1)
        self.assert_conversion('W/V', 'A', 1)
        self.assert_conversion('1/s', 'Hz', 1)
        self.assert_conversion('N/m^2', 'Pa', 1)
        # 遍历不同分母结构，规范输出重新解析后仍有相同关系。
        for text in ('V/(A*s)', 'V/A/s', 'V/(A/s)', 'A^2', 'V/s', 'm/(s*s)'):
            with self.subTest(text=text):
                base = canonical_unit(self.unit(text))
                reread = self.unit(base.symbol)
                self.assertEqual((reread.dimensions, reread.kind, reread.scale, reread.offset),
                                 (base.dimensions, base.kind, base.scale, base.offset))
        # 乘再除回原单位，避免只验证parser而遗漏独立除法入口。
        self.assertEqual(canonical_unit(divide(multiply(self.unit('V'), self.unit('A')), self.unit('A'))).symbol, 'V')

    def test_square_and_root_restore_scale_and_temperature_role(self):
        """平方后开方恢复倍率和原量种，包括绝对温度与温差。

        参数: 无。
        返回: None；偶数指数开方与原单位关系恒等。
        异常: 温度角色、π指数或倍率平方根丢失触发断言失败。
        """
        # K与delta_K分别回到自身；degC有偏移，不能进入这一合法列表。
        for text in ('A', 'mA', 'V/s', 'K', 'delta_K', 'deg', '%'):
            with self.subTest(text=text):
                original = self.unit(text)
                restored = square_root(square(original))
                scale, offset = conversion(restored, original)
                self.assertEqual((scale.factor, scale.pi_power, offset), (Fraction(1), 0, Fraction(0)))
        self.assertEqual(canonical_unit(square(self.unit('A'))).symbol, 'A^2')
        self.assertEqual(canonical_unit(square_root(self.unit('K^2'))).symbol, 'K')
        self.assertEqual(canonical_unit(square_root(self.unit('delta_K^2'))).symbol, 'delta_K')

    def test_root_rejects_odd_quantity_exponents(self):
        """不能只看SI维度为偶数就对不合法的量种开方。

        参数: 无。
        返回: None；电流、角度和能量的奇指数均被拒绝。
        异常: 非法量种被接受时断言失败。
        """
        # rad物理维度为零，但角度量种指数为1，不能误当普通比例开方。
        for text in ('A', 'rad', 'J', 'V/A', 'delta_K'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                square_root(self.unit(text))

    def test_offset_temperature_cannot_enter_products_or_powers(self):
        """偏移温度必须先显式换到K，不能被单位代数悄悄改成温差。

        参数: 无。
        返回: None；文本及模型运算均拒绝带偏移的摄氏量。
        异常: 放行偏移乘除、平方或开方时断言失败。
        """
        # 即使乘以1或摄氏相除，也不能借化简跳过原单位的合法性检查。
        for text in ('degC/s', 'degC*1', 'degC/degC', 'degC^2', '1/degC'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                resolve_unit(text)
        celsius, second = self.unit('degC'), self.unit('s')
        for function, arguments in ((multiply, (celsius, second)), (divide, (celsius, second)),
                                    (square, (celsius,)), (square_root, (celsius,))):
            with self.subTest(operation=function.__name__), self.assertRaises(ValueError):
                function(*arguments)

    def test_unknown_atoms_stay_unknown_and_case_is_significant(self):
        """未知单位和未登记前缀不会自动升级为已验证关系。

        参数: 无。
        返回: None；未列单位返回None，大小写不擅自纠正。
        异常: 未批准目录项被识别或大小写被猜测时断言失败。
        """
        # km/h语法合法但原子未登记，与损坏语法的拒绝行为不同。
        for text in ('mAh', 'kg', 'psi', 'degF', 'km/h', 'custom_unit', 'v', 'MV', 'ohm'):
            with self.subTest(text=text):
                self.assertIsNone(resolve_unit(text))

    def test_malformed_unit_language_is_rejected(self):
        """单位解析器不接受Python表达式、属性或缺少操作数的文本。

        参数: 无。
        返回: None；坏语法在编译期明确失败。
        异常: 非白名单语法被接受或吞成未知单位时断言失败。
        """
        # 这些输入均有结构错误；不能将整串当成一个无害的未知原子。
        for text in ('', ' ', 'V//A', 'V**A', 'V+A', 'V^', '(V', 'V)',
                     'V^1.5', 'V()', 'V[0]', 'V.__class__', '__import__("os")', 'V A'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                resolve_unit(text)
        for value in (None, 1, True, ['V']):
            with self.subTest(value=value), self.assertRaises(TypeError):
                resolve_unit(value)

    def test_unit_text_and_token_budgets(self):
        """过长文本和过多词元必须在解析时失败，不能无限递归。

        参数: 无。
        返回: None；字符和词元各自的界限都起作用。
        异常: 超限被接受或以内存/递归崩溃替代明确拒绝时断言失败。
        """
        # 第一例超过256字符；第二例仅65字符但含65词元，分别覆盖两种限制。
        for text in ('V*' * 129 + 'V', '(' * 32 + 'V' + ')' * 32):
            with self.subTest(length=len(text)), self.assertRaises(ValueError):
                resolve_unit(text)
        # 63词元的合法嵌套仍需工作，不能把防护实现成一律拒绝括号。
        self.assert_conversion('(' * 31 + 'V' + ')' * 31, 'V', 1)

    def test_exponent_limits_and_large_canonical_round_trip(self):
        """合法组合的大指数仍可规范输出后重读，超限明确拒绝。

        参数: 无。
        返回: None；文本和组合量种指数共用32的界限，SI维度由其推导。
        异常: 合法规范文本无法重读或溢出限制不起作用时断言失败。
        """
        # 电流的SI维度与量种指数同为一，不会提前触发别的物理维度限制。
        for text in ('A^16', 'A^32', 'A^-32', 'A^16*A^16', 'V^32', '(V/N)^32'):
            with self.subTest(text=text):
                base = canonical_unit(self.unit(text))
                reread = self.unit(base.symbol)
                self.assertEqual((reread.dimensions, reread.kind), (base.dimensions, base.kind))
        # 同一量种组合后超过32也必须拒绝，不能只限制文本中每个幂。
        for text in ('A^33', 'A^-33', 'A^32*A', 'A^-32/A'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                resolve_unit(text)

    def test_scale_float_boundary_rejects_overflow_and_underflow(self):
        """编译倍率转为float时不能产生无穷或被舍成零。

        参数: 无。
        返回: None；正常比例可表示，超出float范围则明确失败。
        异常: 无穷或零倍率被当成合法转换时断言失败。
        """
        # 极大、极小正分数在元数据阶段精确，在执行边界必须检查表示范围。
        for factor in (Fraction(10 ** 400), Fraction(1, 10 ** 400)):
            with self.subTest(factor=factor), self.assertRaises(ValueError):
                Scale(factor).to_float()
        self.assertEqual(Scale(Fraction(1, 1000)).to_float(), .001)
        self.assertAlmostEqual(Scale(Fraction(1, 180), 1).to_float() * 180, pi)

    def test_registry_objects_are_immutable(self):
        """编译时取得的单位和倍率不能被调用方原地改写。

        参数: 无。
        返回: None；修改冻结字段明确失败，后续解析结果保持。
        异常: 模型可被篡改时断言失败。
        """
        # 不通过修改全局表验证不可变性，只尝试修改单个返回对象。
        unit = self.unit('mV')
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            unit.symbol = 'V'
        scale = Scale(Fraction(1, 1000))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            scale.factor = Fraction(1)
        self.assert_conversion('mV', 'V', Fraction(1, 1000))

    def test_scale_combines_pi_before_float_rounding(self):
        """有理系数单独不可表示时，完整转换仍可能是合法的有限倍率。

        参数: 无。
        返回: None；分别覆盖系数先下溢和先上溢的情形。
        异常: 合法完整倍率被拒绝或发生提前舍入时断言失败。
        """
        # Decimal高精度独立组合二进制pi值，最后一次转换为float作真值。
        from decimal import Decimal, localcontext
        with localcontext() as context:
            context.prec = 400
            for exponent, pi_power in ((-325, 32), (310, -32)):
                expected = float(Decimal(10) ** exponent * Decimal.from_float(pi) ** pi_power)
                actual = Scale(Fraction(10) ** exponent, pi_power).to_float()
                self.assertGreater(actual, 0)
                self.assertEqual(actual, expected)

    def test_dimensionless_powers_obey_fraction_budget(self):
        """百分比幂不增加量种指数，但仍受有理数存储上限约束。

        参数: 无。
        返回: None；4096位允许，4097位及嵌套超限拒绝。
        异常: 大整数绕过限制或正常边界被拒绝时断言失败。
        """
        # 分子、分母各自限制；嵌套表达式只有少量字符，不能只靠词元限额。
        Scale(Fraction(2 ** 4095))
        Scale(Fraction(1, 2 ** 4095))
        for factor in (Fraction(2 ** 4096), Fraction(1, 2 ** 4096)):
            with self.assertRaisesRegex(ValueError, '4096'):
                Scale(factor)
        with self.assertRaisesRegex(ValueError, '4096'):
            resolve_unit('(%^32)^32')

    def test_current_registry_replaces_old_version_contract(self):
        """当前单位全部来自同一目录，旧版本不能重新激活旧14单位规则。"""
        self.assertEqual(validate_conversion_v4('mV', 'V', .001, 0, 1), 'verified')
        self.assertEqual(validate_conversion_v4('degC', 'K', 1, 273.15, 1), 'verified')
        self.assertEqual(validate_conversion_v4('us', 's', .000001, 0, 1), 'verified')
        with self.assertRaises(ValueError):
            require_config_version(3)
        with self.assertRaises(ValueError):
            validate_conversion_v4('mV', 'V', 1, 0, 1)


# 允许作为独立专项执行；不创建输出或自行加载真实数据。
if __name__ == '__main__':
    unittest.main()
