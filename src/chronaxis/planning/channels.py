"""把用户配置的 CAN 通道转换为内部编号，不读取报文或修改原始数据。

公共配置统一从1开始，底层模型从0开始。只在构造模型前调用；配置展开、
序列化与路径解析保留公共编号，避免往返时反复减1。CSV文件列的channel_origin
描述原始文件格式，不经过此转换。
"""
import re

from .checks import PlanValidationError


def channel_index(value, path, *, key=False):
    """校验公共通道并返回0基编号。

    参数: value为从1开始的整数；key=True时为无前导零的正整数十进制字符串；
    path为出错时显示的配置位置。省略通道时由调用方先确定来源的唯一通道，
    本函数不把None解释为省略。
    返回: int，用户配置的通道1转换为内部编号0。
    异常: PlanValidationError，值的类型或取值不符合上述规则，或文本整数超过解析能力。
    """
    # 映射键不能靠int接受空格、符号、前导零或其他进制；bool也不是通道整数。
    if key:
        if type(value) is not str or re.fullmatch(r'[1-9][0-9]*', value) is None:
            raise PlanValidationError(path, '配置CAN通道从1开始，DBC通道键须为无前导零的正整数文本',
                hint='按采集通道编号填写无前导零的正整数文本；第一路写字符串"1"，原始文件中的通道列保持原样')
        try:
            value = int(value)
        except ValueError as error:
            raise PlanValidationError(path, '通道键超过当前整数能力') from error
    elif type(value) is not int or value < 1:
        raise PlanValidationError(path, '配置CAN通道须为从1开始的整数',
            hint='填写从1开始的整数，第一路写1；省略时采用所选来源的唯一通道')
    return value - 1
