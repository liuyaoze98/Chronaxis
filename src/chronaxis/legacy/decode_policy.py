"""原始报文的长度检查与显式纯BLF串行解码政策。

只对所需数据帧核所选长度规则。串行兼容函数保留唯一ID和多定义ID的既有异常
范围；普通并行和文本入口不自动使用这一兼容规则。返回空值时不继承前值。"""


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


def decode_serial_frame(database, frame, message, duplicate_ids):
    """保留纯BLF串行的既有解码政策，不重复检查报文长度或缩放物理值。

    参数: database为本次DBC；frame为当前原消息；message为按实际帧型选择的定义或None；
        duplicate_ids为同ID多定义集合。返回: 解码值字典或失败时的空字典。
    异常: 唯一ID捕获普通Exception；多定义仅捕获DecodeError，其他错误原样传播。
        这一区别只用于明确的串行兼容入口，普通并行和文本入口不自动套用。
    """
    if message is None or frame.arbitration_id not in duplicate_ids:
        try:
            return database.decode_message(frame.arbitration_id, frame.data,
                decode_choices=False, allow_truncated=True)
        except Exception:
            return {}
    from cantools.database.errors import DecodeError
    try:
        return message.decode(frame.data, decode_choices=False, allow_truncated=True)
    except DecodeError:
        return {}
