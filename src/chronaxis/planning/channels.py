"""把用户配置的 CAN 通道转换为内部编号，不读取报文或修改原始数据。

公共配置统一从1开始，底层模型从0开始。只在构造模型前调用；配置展开、
序列化与路径解析保留公共编号，避免往返时反复减1。CSV文件列的channel_origin
描述原始文件格式，不经过此转换。
"""
import re

from .checks import PlanValidationError


def channel_index(value, path, *, key=False):
    """校验公共通道并返回0基编号。

    参数: value为正整数；key=True时为DBC映射的规范十进制字符串；path为配置位置。
    返回: int，用户1对应内部0。异常: PlanValidationError，非法或旧0基声明。
    """
    # 映射键不能靠int接受空格、符号、前导零或其他进制；bool也不是通道整数。
    if key:
        if type(value) is not str or re.fullmatch(r'[1-9][0-9]*', value) is None:
            raise PlanValidationError(path, '配置CAN通道从1开始，DBC通道键须为无前导零的正整数文本',
                hint='第一路填写\'1\'；旧0基配置的通道编号整体加1，原始文件通道列不修改')
        try:
            value = int(value)
        except ValueError as error:
            raise PlanValidationError(path, '通道键超过当前整数能力') from error
    elif type(value) is not int or value < 1:
        raise PlanValidationError(path, '配置CAN通道须为从1开始的整数',
            hint='第一路填写1；省略时继承来源唯一通道，旧0基配置整体加1')
    return value - 1
