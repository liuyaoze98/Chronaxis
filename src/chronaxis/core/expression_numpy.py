"""在同长度信号列上批量求值表达式，并逐位置保留质量诊断。

evaluate_numpy接收当前编译绑定和context中的NumericArray，输出
ArrayEvaluation：数值结果列与独立的uint16依赖诊断列均为形状(N,)。
布尔逻辑用掩码区分TRUE、FALSE和UNKNOWN（未知），不把无效False占位
当作条件不成立；已知值决定结果时，原依赖异常仍留在诊断列。

解释器按表达式树遍历节点，每个节点用NumPy逐元素函数计算整列。
isclose使用显式atol与rtol计算abs(a-b) <= atol + rtol*abs(b)。
evaluate_memory_numpy从已有内存行归一化信号，用searchsorted找到每个
查询时间的最近观测，再按有效期保持并求值，不额外读取或解码。

依赖NumPy及核心编译、数值和对齐模块；共享检查协议，不调用参考数值
求值器。结果为独立只读存储，当前批次缓存不跨调用保留，不修改输入。
"""

# 冻结输出及明确映射接口。
from dataclasses import dataclass
# 数组依赖显式，不污染标准库core导入。
import numpy as np
# 当前静态树是共享已校验协议，不共享样本数值内核。
from .expression import CompiledExpression
# 真实绑定参与执行身份检查。
from .binding import SignalBindings
# 解码运行证据与实际memory绑定共用检查协议，不共享参考数值计算。
from .decoded_binding import DecodedBindings
# 消息绑定只扩显式typed context，不改变普通数值核或memory时间保持入口。
from .message_binding import MessageBindings
# 只共享dtype常量，精确整数比较literal不转float。
from .numeric import INTEGER_BOUNDS
# 数组真实数值入口与布局模型。
from .numeric_numpy import (COMPARE_UFUNCS, DTYPES, NumericArray, _output, _readonly,
                            binary_numpy, to_float_numpy, unary_numpy)
# 此函数只校验身份与列映射，没有参考数值运算。
from .expression_reference import require_context
# 原行批量适配独立于参考转换。
from .normalize_numpy import memory_series_numpy
# 独立NumPy保持，不调用参考对齐。
from .state_numpy import align_numpy, build_signal_array, _require_axis
# 基础质量及bool有效mask实施三值，不对数组bool求值。
from .types import QualityFlag as Q, SignalDType as D


@dataclass(frozen=True)
class ArrayEvaluation:
    """保存同长度的计算结果列与依赖质量诊断列。

    value为NumericArray，dependency_quality是形状(N,)的uint16数组。
    布尔结果可能因已知TRUE或FALSE而有效，诊断仍可包含非零的原依赖原因；
    不能因此把UNKNOWN填为FALSE。构造时检查诊断布局并复制为只读存储。
    实例不可重新赋值，不持有跨批次的求值状态。
    """

    value: NumericArray  # 真实逻辑结果列。
    dependency_quality: np.ndarray  # 同长uint16原因并集。

    def __post_init__(self):
        """验证诊断布局和已知位后复制只读列。

        参数: 无，读取value与dependency_quality。
        返回: None，不修改调用侧数组。
        异常: TypeError/ValueError为结构/长度/未知位。
        """
        # 真实typed结果需与诊断同一布局。
        if not isinstance(self.value, NumericArray) or type(self.dependency_quality) is not np.ndarray or self.dependency_quality.ndim != 1 or self.dependency_quality.dtype != np.dtype('uint16'):
            # 不用广播/隐式cast修正错误接口。
            raise TypeError('ArrayEvaluation诊断需1维uint16列')
        # 未知位不能以诊断为名通过。
        if len(self.dependency_quality) != len(self.value.values) or np.any(self.dependency_quality > 511):
            # 正常BOOL可带诊断，但结构仍严格。
            raise ValueError('ArrayEvaluation诊断长度/原因不合法')
        # 结果与诊断都具独立所有权。
        object.__setattr__(self, 'dependency_quality', _readonly(self.dependency_quality))


def _logic(operator, values):
    """独立以整列掩码实现and/or/not三值真值表。

    参数: operator固定逻辑名；values为同长BOOL列tuple。
    返回: NumericArray，known决定时质量NONE，否则UNKNOWN原因并集。
    异常: 调用者保证static BOOL及shape，分配错误传播。
    """
    # not不将invalid False占位当作真False。
    if operator == 'not':
        # 正常位置取反，valid/原因不改变。
        result = np.zeros(len(values[0].values), dtype=bool)
        # where避免对invalid占位作正常逻辑。
        np.logical_not(values[0].values, out=result, where=values[0].valid)
        # 原原因保持，不清UNKNOWN。
        return _output(D.BOOL, result, values[0].quality.copy())
    # 行数明确，不对数组做Python truthiness。
    size = len(values[0].values)
    # 默认没有known决断/没有原因。
    decided = np.zeros(size, dtype=bool)
    # uint16保留高位诊断。
    quality = np.zeros(size, dtype=np.uint16)
    # 逻辑节点的静态操作数循环，每次都真实整列mask。
    for value in values:
        # unknown原因先并集，decision后只清结果质量。
        quality |= value.quality
        # and由knownFalse决定，or由knownTrue决定。
        decided |= value.valid & (~value.values if operator == 'and' else value.values)
    # 已知决断给正常结果，原诊断由ArrayEvaluation另保存。
    quality[decided] = 0
    # and没有knownFalse且没有unknown时TRUE；or仅decided位置TRUE。
    result = ~decided if operator == 'and' else decided
    # unknown存储值不解释为正常bool，valid由quality决定。
    return _output(D.BOOL, result, quality)


def _constant(node, size):
    """将已校验literal装箱同长typed列，不猜dtype或enum域。

    参数: node为const，size为非负明确行数。
    返回: 正常NumericArray；integer边界此前静态检查。
    异常: 模型/分配错误传播，不自动promotion。
    """
    # enum固定标签域，正常code由当前域唯一确定。
    value = node.labels.index(node.value) if node.labels else node.value
    # 常量复制为整列，不靠广播误配输入。
    values = np.full(size, value, dtype=DTYPES[node.dtype])
    # literal没有上游质量异常。
    return _output(node.dtype, values, np.zeros(size, dtype=np.uint16), node.labels)


def _literal_compare(node, value):
    """在整数域比较原列与任意精确Python整数常量边界。

    参数: node含固定比较名/原整数边界；value为定宽整数列。
    返回: BOOL列，invalid保持原原因，不转float或cast越界常量。
    异常: 编译器保证类型与注册比较，分配错误传播。
    """
    # 边界上下限是精确Python静态配置，不是逐样本计算。
    lower, upper = INTEGER_BOUNDS[value.dtype]
    # 运算名来自白名单编译节点。
    operator = node.operator[12:]
    # 输出占位不正常使用。
    result = np.zeros(len(value.values), dtype=bool)
    # 太小边界：所有正常原值都大于它。
    if node.value < lower:
        # 不把超界常量cast成机器整数。
        result[value.valid] = operator in ('ne', 'gt', 'ge')
    # 太大边界：所有正常原值都小于它。
    elif node.value > upper:
        # 即使2**100也精确判定，不经过float。
        result[value.valid] = operator in ('ne', 'lt', 'le')
    else:
        # 已证明可表示，才按相同dtype精确ufunc比较。
        COMPARE_UFUNCS[operator](value.values, DTYPES[value.dtype].type(node.value), out=result, where=value.valid)
    # known比较正常，unknown原因原样保持。
    return _output(D.BOOL, result, value.quality.copy())


def _evaluate(node, context, size, cache):
    """按静态节点结构调用真实批量数值/逻辑内核。

    参数: node冻结树；context当前同长列；size行数；cache本次batch局部缓存。
    返回: ArrayEvaluation，完整诊断不因known逻辑结果丢失。
    异常: 静态/输入模型问题传播，不调用reference/eval/逐样本Python。
    """
    # 当前batch/真实绑定局部公共子表达式复用。
    if node in cache:
        # 不能跨batch/会话继承数值。
        return cache[node]
    # 裸literal仅类型装箱，没有逐样本计算。
    if node.operator == 'const':
        # shape与所有信号相同。
        value = _constant(node, size)
        # 常量没有原依赖异常。
        result = ArrayEvaluation(value, value.quality)
    # Name只取当前显式context已解码列。
    elif node.operator == 'name':
        # 外层已校验dtype/labels/shape及真实绑定身份。
        value = context[node.name]
        # 原质量同步保存在诊断列。
        result = ArrayEvaluation(value, value.quality)
    else:
        # 对静态子树递归，每个节点执行整列，不逐样本解释。
        children = tuple(_evaluate(arg, context, size, cache) for arg in node.args)
        # 真正数值输入不是diagnostic数组。
        values = tuple(child.value for child in children)
        # 诊断逐节点整列并集，不借normal bool清原因。
        diagnostic = np.zeros(size, dtype=np.uint16)
        # 此循环维度是表达式静态操作数个数。
        for child in children:
            # 所有求值子树的原/计算质量纳入诊断。
            diagnostic |= child.dependency_quality
        # 三值布尔核独立于标量参考真值表代码。
        if node.operator in ('and', 'or', 'not'):
            # 已知决断可normal；diagnostic仍保留UNKNOWN。
            value = _logic(node.operator, values)
        # 数值单目先检查定宽再ufunc。
        elif node.operator in ('abs', 'neg'):
            # 调用真实数组数值核，而非np.vectorize。
            value = unary_numpy(node.operator, values[0])
        # 显式常量float上下文仍用独立尾位精度核。
        elif node.operator == 'to_float':
            # 大整数不默默变近似float。
            value = to_float_numpy(values[0])
        # 常量大边界不能塞进定宽列后wrap。
        elif node.operator.startswith('int_literal_'):
            # 独立静态端点判定及正常整数ufunc。
            value = _literal_compare(node, values[0])
        # 显式isclose判据由安全批量数值原语实施。
        elif node.operator == 'isclose':
            # 四个实参各自先检查整数精度，不调用np.isclose默认策略。
            a, b, atol, rtol = (to_float_numpy(item) for item in values)
            # 左边abs(a-b)，非有限中间结果UNKNOWN。
            distance = unary_numpy('abs', binary_numpy('sub', a, b))
            # 右边rtol*abs(b)，保持判据非对称。
            relative = binary_numpy('mul', rtol, unary_numpy('abs', b))
            # atol+relative真实float64列。
            tolerance = binary_numpy('add', atol, relative)
            # 不把非有限容差当作可正常无限阈值。
            value = binary_numpy('le', distance, tolerance)
            # 计算中间诊断同步纳入整列统计。
            diagnostic |= a.quality | b.quality | atol.quality | rtol.quality | distance.quality | tolerance.quality
        else:
            # 只对静态白名单operator执行真实批量数值。
            value = binary_numpy(node.operator, values[0], values[1], allow_float_literal=node.allow_float_literal)
        # known逻辑输出可以有效，诊断是独立原因列。
        result = ArrayEvaluation(value, diagnostic | value.quality)
    # 局部cache只存当前批列结果。
    cache[node] = result
    # 不持有跨调用输入绑定或信号状态。
    return result


def evaluate_numpy(compiled: CompiledExpression, context, bindings: SignalBindings | DecodedBindings | MessageBindings, *, size: int | None = None) -> ArrayEvaluation:
    """检查绑定、依赖列与行数后，批量计算一个表达式。

    参数:
        compiled: 当前CompiledExpression；bindings为对应普通或MessageBindings运行绑定。
        context: 以精确依赖别名为键的NumericArray映射；所有列须同长同布局。
        size: 可选的非负行数N。可从第一列推断，纯常量无依赖时必须显式提供。
    返回:
        ArrayEvaluation，结果和诊断均为形状(N,)的独立只读数组，允许N为零。
    异常:
        TypeError、ValueError: 模型、绑定身份、依赖键、类型、枚举域或形状不合法。
        数值失败追加质量原因；内存分配异常直接传播。
    边界:
        不广播或补齐错位列。每次调用创建新缓存，只复用当前批次的公共子树。
    """
    # 共享协议校验不包含参考数据计算。
    require_context(compiled, context, bindings)
    # 显式行数不得用bool或任意隐式整数对象替代。
    if size is not None and (type(size) is not int or size < 0):
        # 不按int truthiness解读shape。
        raise TypeError('size需要非负原生int')
    # 每个实际依赖列都需相同当前dtype和enum域。
    for name, value in context.items():
        # 对照当前真实定义，不从全局查找。
        definition = bindings.resolve(name)
        # 不接裸数组或错误类型并偷偷astype。
        if not isinstance(value, NumericArray) or value.dtype is not definition.dtype:
            # 类型错误不能补成UNKNOWN。
            raise TypeError('context列dtype与当前绑定不同')
        # 当前声明固定标签域。
        labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is D.ENUM else ()
        # 相同代码但不同域不允许。
        if value.labels != labels:
            # 来源语义必须明确隔离。
            raise ValueError('context enum域不同')
        # 没有显式行数时取第一合法列，不broadcast。
        if size is None:
            # 只有真正数据列决定N。
            size = len(value.values)
        # 错行数必须执行前拒绝。
        if len(value.values) != size:
            # 不补齐或截断以凑shape。
            raise ValueError('context各列shape不同')
    # 常量无依赖也不能猜输出行数。
    if size is None:
        # 此时context为空，没有合法可推断shape。
        raise ValueError('纯常量批量执行须明确size')
    # 每次批量求值创建新缓存；编译树可复用，上一批的数值结果不继承。
    return _evaluate(compiled.root, context, size, {})


def evaluate_memory_numpy(compiled: CompiledExpression, times: np.ndarray, *, point: bool = False) -> ArrayEvaluation:
    """从已有内存信号批量对齐到查询时间，再计算表达式。

    参数:
        compiled: 关联真实输入的CompiledExpression。
        times: 非递减的一维int64纳秒轴，形状(N,)；point控制真实末点查询视图。
    返回:
        同形状ArrayEvaluation，保留有效掩码、质量原因和绑定身份。
    异常:
        TypeError: 非memory绑定，包括DecodedBindings；其他时间/归属/形状异常原样传播。
    流程:
        只建立实际依赖的历史列，独立归一化并按有效期对齐，再整列求值。
        纯常量也检查时间轴；保留完整历史，结果复制存储，不额外读取或解码。
    """
    # 纯常量也不能绕过memory来源门槛，显式错误避免解码绑定缺session属性的偶发异常。
    if not isinstance(compiled, CompiledExpression) or not isinstance(compiled.bindings, SignalBindings):
        raise TypeError('memory快捷求值需要真实SignalBindings的CompiledExpression')
    # 常量表达式也校验真正时间轴，拒绝MaskArray/回退/浮点时间。
    _require_axis(times)
    # 末点控制必须明确bool，不猜truthiness。
    if type(point) is not bool:
        # 保持协议与reference一致。
        raise TypeError('point需要bool')
    # 局部context只材料化实际依赖列。
    context = {}
    # 循环维度是依赖列，列内对齐/计算实际数组化。
    for name in compiled.dependencies:
        # 原输出→独立NumPy额外转换，不重复DBC factor。
        history = memory_series_numpy(compiled.bindings, name)
        # 用searchsorted定位最近观测，并结合有效期与质量掩码决定哪些保持值可用。
        aligned = align_numpy(build_signal_array(history), times, point=point)
        # 原valid/质量保留，包括最新invalid覆盖，enum代码域来自历史。
        context[name] = NumericArray(history.bindings.resolve(name).dtype, aligned.values, aligned.valid, aligned.quality, aligned.history.labels)
    # 精确行数还覆盖无依赖/空查询情况。
    return evaluate_numpy(compiled, context, compiled.bindings, size=len(times))
