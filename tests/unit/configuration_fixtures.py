"""把既有内核测试构造的配置片段整理为当前公开形式。

仅供迁移既有测试夹具，不是产品兼容入口。公开旧字段拒绝由configuration_groups、
configuration_names等专项直接调用产品验证，不经此函数。普通数据/结果JSON原样返回。
"""
from chronaxis.planning.config_groups import public_configuration


def current_fixture(value):
    """参数为测试生成的原生对象；返回当前配置副本或原非配置值，不读取文件。

    错误形状夹具仍交产品入口检查，不能在这里替它修复业务字段。
    """
    if type(value) is not dict or value.get('config_version') != 4:
        return value
    if type(value.get('sources')) is not list or type(value.get('signals')) is not list:
        return value
    if any(type(item) is not dict for item in (*value['sources'], *value['signals'])):
        return value
    return public_configuration(value)
