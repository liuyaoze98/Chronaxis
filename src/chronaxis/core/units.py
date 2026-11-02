"""检查信号声明的线性单位转换是否与已知单位关系一致。

输入为原单位、目标单位、scale、offset和方向因子；输出verified或unverified。
已知单位用精确分数核对倍率，未知单位保留未校验状态。本模块检查转换声明，
不转换样本值，也不推断物理方向。仅依赖标准库，没有文件操作或会话状态；
温度和复杂量纲不在当前单位表中。
"""

# 分数用于校验声明系数，避免0.001的二进制近似误报配置冲突。
from fractions import Fraction
from math import isfinite
# 单位表不可由调用者原地修改，否则已编译转换身份会失去依据。
from types import MappingProxyType

# 每项为物理类别及相对于该类别基准的精确倍率；不据名称推测方向。
UNIT_TABLE = MappingProxyType({"1": ("dimensionless", Fraction(1)), "V": ("voltage", Fraction(1)),
              "mV": ("voltage", Fraction(1, 1000)), "A": ("current", Fraction(1)),
              "mA": ("current", Fraction(1, 1000)), "W": ("power", Fraction(1)),
              "kW": ("power", Fraction(1000)), "J": ("energy", Fraction(1)),
              "Wh": ("energy", Fraction(3600)), "kWh": ("energy", Fraction(3600000)),
              "s": ("time", Fraction(1)), "ms": ("time", Fraction(1, 1000)),
              "Ah": ("charge", Fraction(3600)), "A·s": ("charge", Fraction(1))})


def require_number(value: int | float, field: str) -> int | float:
    """要求有限原生数值，拒绝bool及未经声明的隐式标量转换。

    参数: value为原生int或有限float；field用于诊断位置。
    返回: 原数值，不改变整数精度。
    异常: TypeError为其他类型；ValueError为非有限float。
    """
    # bool不能作为工程转换系数或范围端点。
    if type(value) not in (int, float):
        # 配置层负责显式解析，不从任意对象取数值。
        raise TypeError(f"{field}必须为原生int或float")
    # 无界int本身有限，不能先转float造成伪溢出。
    if type(value) is float and not isfinite(value):
        # 非有限系数会污染全部输入，在执行前拒绝。
        raise ValueError(f"{field}必须有限")
    # 返回原值供精确配置和后续数值层使用。
    return value


def validate_conversion(input_unit: str, unit: str, scale: int | float,
                        offset: int | float, direction_factor: int) -> str:
    """核对已知单位的转换系数，无法识别单位时返回unverified。

    参数:
        input_unit (str): 已校验的非空原单位标签。
        unit (str): 已校验的非空目标单位标签。
        scale (int | float): 显式倍率，必须已经包含direction_factor。
        offset (int | float): 显式偏移；已知单位的当前转换只接受0。
        direction_factor (int): 已声明的1或-1，表示方向保持或反转。
    返回:
        str: 已知单位关系通过时为verified，任一单位未知时为unverified。
        函数不会补全系数、推断方向或执行样本转换。
    异常:
        ValueError: 已知单位量纲不兼容，倍率不符合单位关系，或偏移不为0。
    """
    # 未知标签只能按显式声明使用，不能宣称量纲校验成功。
    if input_unit not in UNIT_TABLE or unit not in UNIT_TABLE:
        # 同名未知标签也不冒充已知单位。
        return "unverified"
    # 同维度单位才存在首版线性单位换算。
    input_dimension, input_factor = UNIT_TABLE[input_unit]
    # 目标倍率与输入同样使用精确分数。
    output_dimension, output_factor = UNIT_TABLE[unit]
    # 不把电压等不同物理量以一个scale伪装成相同。
    if input_dimension != output_dimension:
        # 编译前明确拒绝单位冲突。
        raise ValueError(f"已知单位不兼容：{input_unit}→{unit}")
    # 用户声明的scale须已经包含显式方向因子。
    expected = input_factor / output_factor * direction_factor
    # 十进制精确倍率或精确倍率唯一的float64舍入值均合法，不放宽任意容差。
    matches = Fraction(str(scale)) == expected or (type(scale) is float and scale == float(expected))
    # 非终止倍率如J→Wh允许标准float64表示；实际样本仍由数值层检查精度损失和质量原因。
    if not matches or offset != 0:
        # 不自动修正错误系数或再次施加DBC缩放。
        raise ValueError(f"已知单位转换需要scale={expected}、offset=0")
    # 这里只证明单位关系，尚不证明预设角色或样本数值有效。
    return "verified"
