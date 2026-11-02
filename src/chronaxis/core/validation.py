"""检查核心模型的文本、简单名称、来源序号和不可变标量。

输入为已经解析的Python对象；文本检查返回原文，序号检查返回精确Python整数，
标量检查只判断类型。原字段可以含点号；标识符须符合ASCII简单名称规则，
不得占用Python关键字或已注册的表达式函数名。本模块不裁剪或改名，不把bool
当整数，不检查样本质量。仅依赖标准库，没有数据读取、日志或会话状态。
"""

# 标准库提供明确的名称语法和整数协议，不用eval或对象反射。
import keyword
import re
from numbers import Integral

# 名称语法来自设计9.2；两个首版函数名保留给表达式层。
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# 首版注册函数名占用统一名称空间，避免信号遮蔽函数语义。
RESERVED_NAMES = frozenset({"abs", "isclose"})
# 逻辑标量只接受这些不可变Python类型，数组标量由适配层显式转换。
SCALAR_TYPES = (int, float, bool, str, type(None))


def require_text(value: str, field: str) -> str:
    """检查非空来源文本并保留原文本身份，不自动strip或改名。

    参数: value (str)为来源名或原字段文本；field (str)用于错误定位。
    返回: str；原文本，点号及两端非全空白不被改写。
    异常: TypeError为非文本；ValueError为空或全空白。
    """
    # 来源身份不能由任意对象的str猜测。
    if not isinstance(value, str):
        # 精确指出哪个模型字段类型错误。
        raise TypeError(f"{field}必须为字符串")
    # 全空白不是可定位的来源标识；正常文本不作归一化。
    if not value.strip():
        # 缺项不能用空名字继续分析。
        raise ValueError(f"{field}不能为空或全空白")
    # 返回原文本以保留字段定位身份。
    return value


def require_identifier(value: str, field: str) -> str:
    """校验设计9.2的简单标识符，不接受属性路径或隐藏替换。

    参数: value (str)为标识符、来源名或表达式别名；field (str)用于错误定位。
    返回: str；原合法标识，大小写保留。
    异常: TypeError为非文本；ValueError为语法、关键字或保留名冲突。
    """
    # 先处理缺项和类型，后续regex只看到明确文本。
    text = require_text(value, field)
    # fullmatch不允许点号、空格、非ASCII或尾随其他字符。
    if IDENTIFIER_PATTERN.fullmatch(text) is None or keyword.iskeyword(text) or text in RESERVED_NAMES:
        # 不自动把点号替换为下划线；保留名按首版契约拒绝。
        raise ValueError(f"{field}须为非关键字/保留名的ASCII简单标识符")
    # 名称只做校验，不改变不同大小写的身份。
    return text


def require_sequence(value: int) -> int:
    """校验来源内非负精确序号，不设置未经设计要求的64位上限。

    参数: value (Integral)为原来源稳定序号；bool不属于序号。
    返回: int；精确序号，不使用float或取模。
    异常: TypeError为非整数或bool；ValueError为负序号。
    """
    # True不能被当作来源序号1。
    if isinstance(value, bool) or not isinstance(value, Integral):
        # 非整数不靠截断转换修补。
        raise TypeError("sequence必须为非布尔整数")
    # 不损失位值地归一到Python整数。
    result = int(value)
    # 来源序号非负，不自动重编号负输入。
    if result < 0:
        # 错误序号不能作为合法样本身份。
        raise ValueError("sequence必须非负")
    # 返回不可变精确身份。
    return result


def require_scalar(value: int | float | bool | str | None) -> None:
    """限制逻辑样本的值类型，允许保留尚未检查质量的原始值。

    参数:
        value: 原生int、float、bool、str或None；不接受数组、容器和自定义对象。
    返回:
        None: 只验证值属于允许的不可变标量类型。有效性、数值范围和声明类型
        由后续模型及数值层检查，None和非有限浮点可以保留为诊断值。
    异常:
        TypeError: 输入不是允许的原生标量类型。
    """
    # 精确类型避免自定义数值子类或容器携带可变状态。
    if type(value) not in SCALAR_TYPES:
        # 数组标量不能未经适配校验就伪装成逻辑输入。
        raise TypeError("逻辑值仅接受原生int/float/bool/str/None")
