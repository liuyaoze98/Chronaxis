"""用手算端点和独立后端对照，检查数值计算及原值换算。

输入为明确64位整数、浮点数和逻辑值的合成数据，输出为unittest断言。
参考实现用Python精确整数，NumPy使用数组运算与有效性掩码；两者比较
类型、可用值和全部质量原因。检查上溢、下溢、大整数比较、除零、非有限值，
以及显式单位系数和choices逻辑映射。固定种子扩展端点组合而不作为真值来源。
T50、T51及内存适配连接在此核对；不读历史资源，不作文件接入或性能结论。
"""

# unittest报告实际失败；固定随机种子不作为真值来源。
import random
# unittest报告真实断言，不吞失败或调整预期。
import unittest
# NumPy显式加载，承担真实typed列/ufunc与掩码计算。
import numpy as np

# 公共模型与实际两个后端入口；不mock计算内核。
from chronaxis.core import (MemoryRow, QualityFlag as Q, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType as D, SourceSpec, TimebaseSpec, TimeType)
# 使用已接线的chronaxis.core.numeric入口；不采用mock或未实现占位。
from chronaxis.core.numeric import (ScalarValue, binary_reference, memory_series_reference,
                                    normalize_reference, result_dtype, to_float_reference, unary_reference)
# 使用已接线的chronaxis.core.numeric_numpy入口；不采用mock或未实现占位。
from chronaxis.core.numeric_numpy import (DTYPES, NumericArray, binary_numpy, to_float_numpy, unary_numpy)
# 使用已接线的chronaxis.core.normalize_numpy入口；不采用mock或未实现占位。
from chronaxis.core.normalize_numpy import memory_series_numpy, normalize_numpy


def _array(scalars):
    """仅装箱标量为同dtype列，不执行被测数值逻辑。

    参数: scalars为非空同型ScalarValue序列。
    返回: NumericArray；invalid占位0/False并保留原因，enum明示编码。
    异常: 类型/域不一致由模型拒绝。
    """
    # 声明不能靠normal值推断。
    dtype, labels = scalars[0].dtype, scalars[0].labels
    # invalid数值存储与逻辑真值分开。
    values = [labels.index(item.value) if labels and item.valid else item.value if item.valid else 0 for item in scalars]
    # 仅打包同型数组，不数值promotion。
    return NumericArray(dtype, np.array(values, dtype=DTYPES[dtype]), np.array([item.valid for item in scalars], dtype=bool),
                        np.array([int(item.quality) for item in scalars], dtype=np.uint16), labels)


def _definition(dtype=D.INT64, **kwargs):
    """构造通用未知单位的显式转换声明供边界测试。

    参数: dtype目标数值类型；kwargs明示额外参数。
    返回: 冻结SignalDefinition，unknown单位无隐藏换算。
    异常: 声明错误由真实模型拒绝。
    """
    # 测试仿射数值不假装物理单位已核实。
    return SignalDefinition('signal_a', 'source_a', 'raw', dtype, 'test_unit', 2, **kwargs)


class NumericTests(unittest.TestCase):
    """核对定宽/精度真值与两个独立内核的全部质量。

    差分不能替代端点手算；正常0和False始终带独立valid。
    """

    def _equal(self, reference, array):
        """比较完整结果类型、质量及正常逻辑值。

        参数: reference为ScalarValue序列；array为实际NumericArray。
        返回: None，失败由unittest定位。
        异常: 测试失败以AssertionError报告。
        """
        # invalid占位值不充当业务计算结果。
        self.assertEqual([item.valid for item in reference], array.valid.tolist())
        # 同时校验所有原因，而非只比valid。
        self.assertEqual([int(item.quality) for item in reference], array.quality.tolist())
        # 输出类型与每个标量相同。
        for index, item in enumerate(reference):
            # 类型提升必须符合静态协议。
            self.assertEqual(item.dtype, array.dtype)
            # 只有合法掩码位置才解释数组值。
            if item.valid:
                # enum编码按真实同一域解释。
                value = array.labels[int(array.values[index])] if array.labels else array.values[index].item()
                # 算术采用同IEEE步骤，整数保持精确。
                self.assertEqual(item.value, value)

    def _binary(self, operation, left, right, **kwargs):
        """执行同组输入的独立标量与数组并核对。

        参数: operation/left/right为静态运算与同长标量；kwargs为字面量证明。
        返回: 实际标量结果序列，供手算断言。
        异常: 运算/测试失败传播。
        """
        # 独立参考不调用数组计算。
        reference = [binary_reference(operation, a, b, **kwargs) for a, b in zip(left, right)]
        # 被测路径是真实列ufunc，不np.vectorize。
        array = binary_numpy(operation, _array(left), _array(right), **kwargs)
        # 完整质量和正常值核对。
        self._equal(reference, array)
        # 手算验收可以直接读取逻辑结果。
        return reference

    def test_t50_signed_endpoints_and_mask(self):
        """T50上溢、min翻转和正常0用手算验证，不执行invalid算术。

        参数: 无，signed端点与无效诊断。
        返回: None。
        异常: 回归失败由unittest报告。
        """
        # 精确signed两端，不先转float。
        low, high = -(2 ** 63), 2 ** 63 - 1
        # max+1失败；min+1合法；invalid max不增加overflow。
        left = [ScalarValue(high, D.INT64), ScalarValue(low, D.INT64), ScalarValue(high, D.INT64, False, Q.STALE)]
        # 所有分母/右侧是真实正常1。
        right = [ScalarValue(1, D.INT64)] * 3
        # 两后端实际执行后与手算质量比较。
        results = self._binary('add', left, right)
        # 不允许wrap正常min，invalid只保留STALE。
        self.assertEqual([item.quality for item in results], [Q.OVERFLOW, Q.NONE, Q.STALE])
        # min+1真实正常值仍精确。
        self.assertEqual(results[1].value, low + 1)
        # min*(-1)与max*1分开手算。
        products = self._binary('mul', [ScalarValue(low, D.INT64), ScalarValue(high, D.INT64)], [ScalarValue(-1, D.INT64), ScalarValue(1, D.INT64)])
        # 符号翻转不能返回正常负min。
        self.assertEqual([item.quality for item in products], [Q.OVERFLOW, Q.NONE])
        # abs/neg最小值及0均比较真实独立实现。
        for operation in ('abs', 'neg'):
            # 0合法，min失败，invalid原因不得新增。
            inputs = [ScalarValue(low, D.INT64), ScalarValue(0, D.INT64), ScalarValue(low, D.INT64, False, Q.DECODE_ERROR)]
            # 标量独立真值先计算。
            reference = [unary_reference(operation, item) for item in inputs]
            # 数组实际运行掩码ufunc。
            self._equal(reference, unary_numpy(operation, _array(inputs)))
            # 手算端点质量不依赖差分共同错误。
            self.assertEqual([item.quality for item in reference], [Q.OVERFLOW, Q.NONE, Q.DECODE_ERROR])

    def test_t51_unsigned_and_exact_comparison(self):
        """T51 unsigned下溢/上溢与大于2**53的整数精确比较。

        参数: 无；uint64 max及signed/unsigned交界。
        返回: None。
        异常: 回归失败由unittest报告。
        """
        # unsigned两端手算。
        values = [ScalarValue(0, D.UINT64), ScalarValue(2 ** 64 - 1, D.UINT64)]
        # 0-1应失败；max-1合法。
        results = self._binary('sub', values, [ScalarValue(1, D.UINT64)] * 2)
        # 禁止0-1wrap成正常max。
        self.assertEqual([item.quality for item in results], [Q.OVERFLOW, Q.NONE])
        # max+1应失败。
        self.assertEqual(self._binary('add', values, [ScalarValue(1, D.UINT64)] * 2)[1].quality, Q.OVERFLOW)
        # 与uint64 max比较，signed负数序不能依赖float。
        left = [ScalarValue(-1, D.INT64), ScalarValue(2 ** 53 + 1, D.INT64), ScalarValue(2 ** 63 - 1, D.INT64)]
        # 第二对相邻大整数比较必须是gt。
        right = [ScalarValue(0, D.UINT64), ScalarValue(2 ** 53, D.UINT64), ScalarValue(2 ** 64 - 1, D.UINT64)]
        # 完整比较白名单和两种操作数方向。
        for operation in ('eq', 'ne', 'lt', 'le', 'gt', 'ge'):
            # 不提前将大整数变为近似float。
            self._binary(operation, left, right)
            # 反向同样明确符号分段。
            self._binary(operation, right, left)
        # 手算大整数相邻值真值。
        self.assertTrue(self._binary('gt', left, right)[1].value)

    def test_float_precision_domain_and_nonfinite(self):
        """显式float转换精度、除零和计算非有限有独立质量真值。

        参数: 无；2**53周围、2**63/2**64及极大float。
        返回: None。
        异常: 回归失败由unittest报告。
        """
        # 有signed min/max及无效大数，结果合法掩码独立。
        signed = [ScalarValue(value, D.INT64) for value in (2 ** 53, 2 ** 53 + 1, -(2 ** 63), 2 ** 63 - 1)]
        # 精确表示min不能因为超过2**53就一律失败。
        reference = [to_float_reference(item) for item in signed]
        # 数组固定尾位算法与往返参考对照。
        self._equal(reference, to_float_numpy(_array(signed)))
        # 手算精度质量序列。
        self.assertEqual([item.quality for item in reference], [Q.NONE, Q.PRECISION_LOSS, Q.NONE, Q.PRECISION_LOSS])
        # unsigned极大数也能有精确2**63，不放行max。
        unsigned = [ScalarValue(value, D.UINT64) for value in (2 ** 63, 2 ** 64 - 1)]
        # 真正独立两个转换内核。
        self._equal([to_float_reference(item) for item in unsigned], to_float_numpy(_array(unsigned)))
        # 除法需要先整数精度，再域检查。
        results = self._binary('div', [ScalarValue(0, D.INT64), ScalarValue(2 ** 53 + 1, D.INT64), ScalarValue(4, D.INT64)], [ScalarValue(0, D.INT64), ScalarValue(0, D.INT64), ScalarValue(2, D.INT64)])
        # 精度失败不继续执行除零，0/0独立域错误。
        self.assertEqual([item.quality for item in results], [Q.DOMAIN_ERROR, Q.PRECISION_LOSS, Q.NONE])
        # 有限float乘法超界变NONFINITE，无效输入不产生新错误。
        results = self._binary('mul', [ScalarValue(1e308, D.FLOAT64), ScalarValue(None, D.FLOAT64, False, Q.MISSING)], [ScalarValue(1e308, D.FLOAT64)] * 2)
        # 上游原因保留，不能用isfinite掩盖整数溢出。
        self.assertEqual([item.quality for item in results], [Q.NONFINITE, Q.MISSING])
        # 浮点字面量路径仍要求整数精确表示。
        results = self._binary('add', signed[:2], [ScalarValue(.5, D.FLOAT64)] * 2, allow_float_literal=True)
        # 含大奇数位置不使用舍入值。
        self.assertEqual(results[1].quality, Q.PRECISION_LOSS)

    def test_static_types_logic_and_array_ownership(self):
        """不同dtype算术配置拒绝；逻辑域和所有权不隐式改变。

        参数: 无；typed错误/空列/enum及bool正常False。
        返回: None。
        异常: 预期异常由assertRaises核对。
        """
        # signed/unsigned算术不能跟随NumPy隐式promotion。
        for left, right in ((D.INT64, D.UINT64), (D.INT64, D.FLOAT64)):
            # 静态拒绝与实际两个执行入口拒绝。
            with self.assertRaises(ValueError):
                # 不通过样本invalid绕过类型校验。
                result_dtype('add', left, right)
        # 任意pow函数不在注册白名单。
        with self.assertRaises(ValueError):
            # 枚举/逻辑只能等值。
            result_dtype('pow', D.INT64, D.INT64)
        # 正常False参与同型等值，不是UNKNOWN。
        result = self._binary('eq', [ScalarValue(False, D.BOOL)], [ScalarValue(False, D.BOOL)])
        # 手算两个False相等。
        self.assertTrue(result[0].value)
        # enum固定域且未映射标签不能默认选择。
        self._binary('ne', [ScalarValue('a', D.ENUM, labels=('a', 'b'))], [ScalarValue('b', D.ENUM, labels=('a', 'b'))])
        # 原列调用侧可变，输出独立只读。
        raw = np.array([1], dtype=np.int64)
        # 真正模型处理自有副本。
        array = NumericArray(D.INT64, raw, np.array([True]), np.array([0], dtype=np.uint16))
        # 原列可以继续改变，不污染结果。
        raw[0] = 9
        # 内核看到的是当时值。
        self.assertEqual(array.values.tolist(), [1])
        # 输出普通修改必须拒绝。
        with self.assertRaises(ValueError):
            # 原地覆盖会破坏冻结契约。
            array.values[0] = 5
        # invalid必须有原因，包括质量256不被截断。
        with self.assertRaises(ValueError):
            # 不允许invalid质量NONE。
            NumericArray(D.INT64, raw, np.array([False]), np.array([0], dtype=np.uint16))
        # 已知高位DOMAIN_ERROR正常保留。
        self.assertEqual(_array([ScalarValue(None, D.INT64, False, Q.DOMAIN_ERROR)]).quality.tolist(), [256])
        # 空列仍真实执行静态拒绝，invalid不能绕过不同dtype信号门槛。
        for dtype in (D.UINT64, D.FLOAT64):
            # 两输入都invalid仍应报告配置错误。
            left, right = ScalarValue(None, D.INT64, False, Q.MISSING), ScalarValue(None, dtype, False, Q.MISSING)
            # 标量入口也先做类型检查。
            with self.assertRaises(ValueError):
                # 不把配置冲突算作UNKNOWN。
                binary_reference('add', left, right)
            # 数组入口先类型检查而非直接返回invalid。
            with self.assertRaises(ValueError):
                # 与静态dtype协议一致。
                binary_numpy('add', _array([left]), _array([right]))
        # 不同标签域的同编码不得当相同枚举值。
        with self.assertRaises(ValueError):
            # 此拒绝在执行前发生。
            self._binary('eq', [ScalarValue('a', D.ENUM, labels=('a',))], [ScalarValue('b', D.ENUM, labels=('b',))])
        # 空正常列不需要伪造样本，返回同长空结果。
        empty = NumericArray(D.INT64, np.array([], dtype=np.int64), np.array([], dtype=bool), np.array([], dtype=np.uint16))
        # 数组ufunc/转换安全处理N=0。
        self.assertEqual(binary_numpy('div', empty, empty).values.tolist(), [])
        # 隐式int32/MaskArray和错误shape在接口拒绝。
        for raw in (np.array([1], dtype=np.int32), np.array([[1]], dtype=np.int64), np.ma.array([1], mask=[True])):
            # 包装不能顺手astype或忽略隐藏mask。
            with self.assertRaises(TypeError):
                # dtype/shape错误是配置，不能伪装缺失。
                NumericArray(D.INT64, raw, np.array([True]), np.array([0], dtype=np.uint16))

    def test_randomized_integer_and_float_kernels(self):
        """固定种子600行每dtype含端点及无效的独立差分。

        参数: 无，seed20261008。
        返回: None。
        异常: 任意值/quality差异报告失败。
        """
        # 固定种子仅决定输入，不生成期望。
        rng = random.Random(20261008)
        # 每种定宽覆盖端点及随机全域。
        for dtype, low, high in ((D.INT64, -(2 ** 63), 2 ** 63 - 1), (D.UINT64, 0, 2 ** 64 - 1)):
            # 明示端点/零优先，让随机不决定关键验收覆盖。
            domain = [low, high, 0, 1, 2 ** 53, 2 ** 53 + 1]
            # signed还包括-1/min+1。
            domain += [-1, low + 1] if dtype is D.INT64 else [high - 1]
            # 真实随机整数范围，不经float采样。
            numbers = domain + [rng.randint(low, high) for _ in range(600)]
            # 无效位置带上游原因以核对掩码优先级。
            left = [ScalarValue(value, dtype, index % 17 != 0, Q.NONE if index % 17 else Q.STALE) for index, value in enumerate(numbers)]
            # 右侧包含端点/0，不固定全1。
            right = [ScalarValue(rng.choice(domain) if index % 2 else rng.randint(low, high), dtype) for index in range(len(left))]
            # 每运算都由独立reference给完整结果。
            for operation in ('add', 'sub', 'mul', 'div', 'eq', 'lt', 'ge'):
                # 同长真实array一次执行整列。
                self._binary(operation, left, right)
            # 单目及精度转换另行覆盖。
            for operation in ('abs', 'neg'):
                # 不用binary变形伪造独立unary参考。
                self._equal([unary_reference(operation, item) for item in left], unary_numpy(operation, _array(left)))
            # float准确性检查严格不宽容2**53以上奇数。
            self._equal([to_float_reference(item) for item in left], to_float_numpy(_array(left)))
        # 浮点双后端遵守同样两步IEEE运算。
        left = [ScalarValue(rng.uniform(-1e100, 1e100), D.FLOAT64) for _ in range(100)]
        # 除数为有限非零随机值。
        right = [ScalarValue(rng.uniform(-1e100, 1e100), D.FLOAT64) for _ in range(100)]
        # 浮点比较/除法和overflow掩码全部实际执行。
        for operation in ('add', 'sub', 'mul', 'div', 'eq', 'lt'):
            # IEEE标量和array数值完全一致。
            self._binary(operation, left, right)

    def _normalize(self, definition, raw, quality=None):
        """执行同质原值的独立归一化并核对所有正常值。

        参数: definition为声明；raw为实际typed ndarray；quality可选uint16。
        返回: 参考ScalarValue列表。
        异常: 回归失败由unittest定位。
        """
        # 原生装箱不参与数值运算，只恢复typed标量。
        reference = [normalize_reference(definition, item.item(), Q(int(quality[index])) if quality is not None else Q.NONE) for index, item in enumerate(raw)]
        # 实际数组归一化从原typed列独立执行。
        array = normalize_numpy(definition, raw, quality)
        # 完整类型/质量/值都比较。
        self._equal(reference, array)
        # 供手算与无效原诊断进一步核对。
        return reference

    def test_normalization_units_types_and_quality(self):
        """单位变换、目标整型精度及invalid/range与手算一致。

        参数: 无；明示mA→A及工程有效范围。
        返回: None。
        异常: 回归失败由unittest报告。
        """
        # 这是额外显式单位换算，不重复DBC factor。
        definition = SignalDefinition('signal_a', 'source_a', 'raw', D.FLOAT64, 'A', 2, input_unit='mA', scale=.001, valid_range=(-1, 1), invalid_values=(-9999,))
        # 输入包含正常0、invalid码、越工程范围、大整数精度失败。
        results = self._normalize(definition, np.array([0, 500, -9999, 2000, 2 ** 53 + 1], dtype=np.int64))
        # 手算0.5A合法，invalid原码不能按工程范围正常转换。
        self.assertEqual(results[1].value, .5)
        # 完整质量与约定优先级相同。
        self.assertEqual([item.quality for item in results], [Q.NONE, Q.NONE, Q.OUT_OF_RANGE, Q.OUT_OF_RANGE, Q.PRECISION_LOSS])
        # float→int不能截断或cast超过exclusive上界。
        results = self._normalize(_definition(), np.array([0., 1.5, float(2 ** 63), float(-(2 ** 63)), float('inf'), float('nan')], dtype=np.float64))
        # signed min精确可表示，max的向上舍入值无效。
        self.assertEqual([item.quality for item in results], [Q.NONE, Q.PRECISION_LOSS, Q.OVERFLOW, Q.NONE, Q.NONFINITE, Q.NONFINITE])
        # scale0不能恢复非有限原输入。
        self.assertEqual(self._normalize(_definition(D.FLOAT64, scale=0), np.array([float('inf')]))[0].quality, Q.NONFINITE)
        # 非数值字符串不能解析成正常数字。
        self.assertEqual(self._normalize(_definition(), np.array(['1', 'bad']))[0].quality, Q.DECODE_ERROR)
        # 常量本身精度问题也不隐藏；与原值失败独立并集。
        results = self._normalize(_definition(D.FLOAT64, scale=2 ** 53 + 1, offset=10 ** 400), np.array([1, 2 ** 53 + 1], dtype=np.int64))
        # 精度与非有限两个原因同时保留。
        self.assertEqual([item.quality for item in results], [Q.PRECISION_LOSS | Q.NONFINITE] * 2)

    def test_exact_affine_cancellation_and_extreme_coefficients(self):
        """整数仿射最终合法即成功，中间数学超界不误判。

        参数: 无；全signed/unsigned跨度、负scale及极大配置系数。
        返回: None。
        异常: 差分或手算失败由unittest报告。
        """
        # 原生配置常量无界不代表原样本类型无界。
        cases = [(D.INT64, 2, -(2 ** 63)), (D.INT64, -1, -1), (D.INT64, 1, -(2 ** 63)),
                 (D.UINT64, 1, 2 ** 63), (D.UINT64, -2, 2 ** 64 - 1), (D.INT64, 10 ** 80, -10 ** 80 + 7),
                 (D.INT64, 0, 2 ** 63), (D.UINT64, 0, 0)]
        # 明示端点/零/单值抵消真值。
        signed = np.array([-(2 ** 63), -1, 0, 1, 2 ** 62, 2 ** 63 - 1], dtype=np.int64)
        # unsigned跨度可能大于signed max，不隐式提升。
        unsigned = np.array([0, 1, 2 ** 63, 2 ** 64 - 1], dtype=np.uint64)
        # 每配置都独立参考和真实批量仿射执行。
        for dtype, scale, offset in cases:
            # unknown测试单位允许明确校准，不虚报单位verified。
            definition = _definition(dtype, scale=scale, offset=offset)
            # signed/unsigned原类型分别处理。
            self._normalize(definition, signed)
            # 整数幅度边界另在无符号域核对。
            self._normalize(definition, unsigned)
        # 手算2*(2**62)-2**63=0，不能因中间2**63失败。
        self.assertEqual(self._normalize(_definition(scale=2, offset=-(2 ** 63)), np.array([2 ** 62], dtype=np.int64))[0].value, 0)
        # 大配置常量抵消后的7不依赖危险uint64 cast。
        self.assertEqual(self._normalize(_definition(scale=10 ** 80, offset=-10 ** 80 + 7), np.array([1], dtype=np.int64))[0].value, 7)

    def test_logic_choices_exact_range_and_upstream_mask(self):
        """显式逻辑映射/工程整数边界/上游质量不被占位改写。

        参数: 无；码到标签、False及2**53周围边界。
        返回: None。
        异常: 回归失败由unittest报告。
        """
        # 标签域保持大小写和原次序，重复标签允许多码同义。
        definition = _definition(D.ENUM, choices=((0, 'Idle'), (1, 'Run'), (2, 'Run')))
        # 未声明9不能取第一项。
        results = self._normalize(definition, np.array([0, 1, 2, 9], dtype=np.int64))
        # 显式映射真实标签。
        self.assertEqual([item.value for item in results[:3]], ['Idle', 'Run', 'Run'])
        # 缺码质量不能隐藏。
        self.assertEqual(results[3].quality, Q.OUT_OF_RANGE)
        # 正常False与UNKNOWN严格分开。
        self.assertFalse(self._normalize(_definition(D.BOOL), np.array([False]))[0].value)
        # 不把原整数0隐式转bool。
        self.assertEqual(self._normalize(_definition(D.BOOL), np.array([0], dtype=np.int64))[0].quality, Q.OUT_OF_RANGE)
        # float范围比较必须保留精确整数端点，不把lower向下舍入。
        results = self._normalize(_definition(D.FLOAT64, valid_range=(2 ** 53 + 1, 2 ** 53 + 4)), np.array([float(2 ** 53), float(2 ** 53 + 2)]))
        # 前值在精确下界之外，后值正常。
        self.assertEqual([item.quality for item in results], [Q.OUT_OF_RANGE, Q.NONE])
        # invalid上游占位即使极大亦不触发附加精度/overflow。
        results = self._normalize(_definition(D.FLOAT64), np.array([2 ** 63 - 1], dtype=np.int64), np.array([int(Q.STALE | Q.DOMAIN_ERROR)], dtype=np.uint16))
        # 质量高位及原因完整保留。
        self.assertEqual(results[0].quality, Q.STALE | Q.DOMAIN_ERROR)

    def test_randomized_affine_normalization(self):
        """100组固定种子随机仿射/目标类型/端点独立对照。

        参数: 无；seed20261009，每组40行。
        返回: None。
        异常: 差分失败报告配置和实际值。
        """
        # 固定种子允许复现输入，不改变语义期望。
        rng = random.Random(20261009)
        # 100配置包含正负scale与巨大offset以及signed/unsigned输入。
        for index in range(100):
            # 目标类型按组交替。
            dtype = D.INT64 if index % 2 else D.UINT64
            # 静态配置常量可超signed64但不隐式float化。
            definition = _definition(dtype, scale=rng.choice((-10 ** 40, -10, -1, 0, 1, 2, 1000, 10 ** 40)), offset=rng.randint(-(2 ** 65), 2 ** 65))
            # 原输入物理类型明确。
            signed = index % 3 != 0
            # 包含全范围端点与真实随机整数。
            low, high = (-(2 ** 63), 2 ** 63 - 1) if signed else (0, 2 ** 64 - 1)
            # 每组40行实际批量运算。
            raw = np.array([low, high, 0, 1] + [rng.randint(low, high) for _ in range(36)], dtype=np.int64 if signed else np.uint64)
            # 独立核对全部质量和正常值。
            self._normalize(definition, raw)

    def test_memory_adapters_preserve_raw_identity(self):
        """两种适配连接真实绑定/保持，保留invalid原值和序号。

        参数: 无；混合原值、缺列、未知及超宽整数。
        返回: None。
        异常: 回归失败报告原样本。
        """
        # 同一相对时间基准，无跨来源同步假设。
        timebase = TimebaseSpec('clock_a', TimeType.RELATIVE, 'numeric-memory-v1')
        # 缺列行不伪造当前信号更新。
        originals = [0, 500, None, float('nan'), 'bad', True, 2 ** 64, 2 ** 53 + 1]
        # 原行拥有稳定序号且时间已排序。
        rows = tuple(MemoryRow(index, {'raw': value}, index) for index, value in enumerate(originals)) + (MemoryRow(8, {'other': 7}, 8),)
        # 明示观测窗口，不按周期延长。
        source = SourceSpec('source_a', timebase, rows, observation_start_ns=0, observation_end_ns=10)
        # 当前实体/会话保持来源身份。
        session = SessionSpec('session_a', timebase, 0, 10, (source,))
        # 一次单位换算，0.5 A手算正确。
        definition = SignalDefinition('signal_a', 'source_a', 'raw', D.FLOAT64, 'A', 2, input_unit='mA', scale=.001)
        # 绑定不可从全局继承。
        bindings = SignalBindings(session, (definition,))
        # 两种适配各自从相同原行独立计算。
        reference, array = memory_series_reference(bindings, 'signal_a'), memory_series_numpy(bindings, 'signal_a')
        # 缺列不产生第9个更新。
        self.assertEqual(len(reference.samples), 8)
        # 正常单位结果手算。
        self.assertEqual(reference.samples[1].value, .5)
        # 完整原身份与数值政策对照；NaN不能用==核对。
        for a, b in zip(reference.samples, array.samples):
            # 保留真实time/ref/seq，不重新安排来源行。
            self.assertEqual((a.time_ns, a.source_ref, a.sequence, a.valid, a.quality), (b.time_ns, b.source_ref, b.sequence, b.valid, b.quality))
            # invalid原NaN诊断由原对象保留。
            if a.sequence != 3:
                # 其他原值正常0/None/str/bool/超宽整数均保留。
                self.assertEqual(a.value, b.value)
        # 超宽原整数不是额外dtype，原诊断未被截断。
        self.assertEqual(reference.samples[6].quality, Q.OVERFLOW)
        # 保留原超宽数值，不能wrap。
        self.assertEqual(reference.samples[6].value, 2 ** 64)
