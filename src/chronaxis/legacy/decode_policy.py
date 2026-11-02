"""新原始报文入口的长度政策；只检查实际需要解码的数据帧。

不改旧解码函数，也不再次解码。旧函数返回空值时，下游把所需字段置为无效；
旧接口没有暴露失败原因，本层不猜测原因。legacy保留原来的调用行为。
"""


def validate_decode_policy(value):
    """核验长度政策。参数: value为政策名。返回: 原字符串。异常: ValueError。
    """
    if type(value) is not str or value not in ('legacy', 'strict', 'partial'):
        raise ValueError('decode_policy需要legacy、strict或partial')
    return value


def check_decode_length(frame, expected, policy):
    """解码前检查所需帧长度，不复制载荷或检查无关报文。

    参数: frame为当前原帧；expected为DBC长度；policy已经过静态核验。
    返回: None；partial仅允许载荷短于DBC，不能掩盖DLC与实际字节不一致。
    异常: ValueError表示结构或所选长度政策不符；属性访问错误原样传播。
    """
    if policy == 'legacy':
        return
    size = len(frame.data)
    if (type(frame.dlc) is not int or not 0 <= frame.dlc <= 64 or frame.dlc != size
            or (size != expected if policy == 'strict' else size > expected)):
        raise ValueError('已选DBC报文载荷长度不一致')
