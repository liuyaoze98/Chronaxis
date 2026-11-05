"""在配置编译时确定版本4的单位转换和数值类型。

输入是声明单位、完整转换系数和dtype，输出系数、校验状态及固定目标类型。
只复用不可变单位注册表；不读取DBC、不处理样本、不创建运行时全局状态。
当前只接受版本4；未知单位仍须明确转换，不隐式回退到旧单位规则。
"""

# 精确分数用于验证配置；数值执行继续使用既有两个独立后端。
from fractions import Fraction

from .types import SignalDType
from .units import require_number
from .unit_registry import conversion, resolve_unit


def require_config_version(version: int) -> int:
    """检查已有配置版本选择，不把bool当作整数版本。

    参数: version为原生整数4。
    返回: 原版本。
    异常: ValueError为未支持的版本或错误类型。
    """
    # 版本在计划内冻结，不能从全局状态隐式切换。
    if type(version) is not int or version != 4:
        raise ValueError('当前仅支持config_version=4；请按当前配置重新填写旧版本')
    return version


def binding_version(definitions, explicit: int | None = None) -> int:
    """校验所有定义与可选显式版本，仅返回当前版本4。

    参数: definitions为已检查的定义序列，explicit可省略；空绑定同样使用4。
    返回: 4。异常: ValueError为任一定义或显式参数不支持的版本。
    """
    # 不把空绑定作为旧规则回退入口；逐项校验也拒绝伪造的旧定义。
    for definition in definitions:
        require_config_version(definition.config_version)
    if explicit is not None:
        require_config_version(explicit)
    return 4


def affine_conversion(input_unit: str, unit: str) -> tuple[int | float, int | float, str]:
    """生成一次源单位到目标单位的完整转换。

    参数: input_unit为已经解码值的单位，unit为目标单位。
    返回: (scale, offset, status)；整数系数保留int，同名未知标签保持1、0、unverified。
    异常: ValueError为已知单位冲突、异名未知关系、非法语法或float倍率不可表示。
    """
    # 未知标签不能据拼写相同假称已验证，也不能猜测隐含工程倍率。
    source, target = resolve_unit(input_unit), resolve_unit(unit)
    if source is None or target is None:
        if input_unit != unit:
            raise ValueError('未知单位之间不能自动推导转换，请填写完整scale/offset')
        return 1, 0, 'unverified'
    scale, offset = conversion(source, target)
    factor = (scale.factor.numerator if scale.pi_power == 0 and scale.factor.denominator == 1
              else scale.to_float())
    shift = offset.numerator if offset.denominator == 1 else float(offset)
    return factor, shift, 'verified'


def validate_conversion_v4(input_unit: str, unit: str, scale: int | float,
                           offset: int | float, direction_factor: int = 1) -> str:
    """验证调用方已经确定的完整转换，不再次叠加单位倍率。

    参数: input_unit/unit为单位；scale/offset为完整转换；direction_factor为已核实方向。
    返回: verified或unverified。
    异常: TypeError为非原生系数；ValueError为单位或系数冲突。
    """
    # 显式完整系数不得被错误地当成额外标定后再次缩放。
    require_number(scale, 'signal.scale')
    require_number(offset, 'signal.offset')
    source, target = resolve_unit(input_unit), resolve_unit(unit)
    if source is None or target is None:
        return 'unverified'
    expected, shift = conversion(source, target)
    # 有理数检查优先，非终止/含pi倍率接受唯一的float64表示，不使用宽松容差。
    factor_matches = (expected.pi_power == 0 and
                      Fraction(str(scale)) == expected.factor * direction_factor)
    if not factor_matches:
        factor_matches = type(scale) is float and scale == expected.to_float() * direction_factor
    offset_matches = Fraction(str(offset)) == shift or type(offset) is float and offset == float(shift)
    if not factor_matches or not offset_matches:
        raise ValueError(f'已知单位转换系数与{input_unit}→{unit}不一致')
    return 'verified'


def converted_dtype(dtype: SignalDType, scale: int | float, offset: int | float) -> SignalDType:
    """在编译期决定单位转换是否需要浮点类型。

    参数: dtype为原声明类型，scale/offset为完整有限转换系数。
    返回: 有分数倍率或偏移的整数提升FLOAT64，其余保持原类型。
    异常: TypeError为错误dtype或系数；ValueError为非有限系数。
    """
    # 提升与样本值无关；大整数是否可精确转float仍由实际数值核检查。
    if not isinstance(dtype, SignalDType):
        raise TypeError('dtype必须为SignalDType')
    require_number(scale, 'scale')
    require_number(offset, 'offset')
    if dtype in (SignalDType.INT64, SignalDType.UINT64):
        if Fraction(str(scale)).denominator != 1 or Fraction(str(offset)).denominator != 1:
            return SignalDType.FLOAT64
    return dtype
