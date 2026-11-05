"""检查转换系数和范围端点的原生有限数值；单位关系由 unit_registry 统一提供。"""

from math import isfinite


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
