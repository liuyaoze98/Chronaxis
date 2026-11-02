"""校验批次中不再保存的原报文，避免为丢弃的数据建立完整解码记录副本。

输入是旧parse_frame刚返回的原msg、完整values和原yield序号；成功返回None。
先沿用原公开帧字段检查。常见原生消息用安全上界证明完整ITEM不超过64KiB；
无法证明时，精确计算原ITEM包字节并检查完整values，保留原类型和非有限诊断。
本模块不读取或解码报文，不改公共records模型，不写文件或保留输入引用。
原帧临时对象和标量编码的费用由调用方在批次许可前预约；不承诺旧库RSS受控。
"""

from collections.abc import Mapping
from math import isfinite

from .records import (MAX_WIRE_BYTES, _decoded_values_size, _integer, _scalar_size,
                      _ITEM_FIXED_BYTES, _SMALL_ITEM_BASE_UPPER, _small_item_fits)
from .worker import _frame


def _item_base_size(frame, sequence):
    """计算合法原帧的ITEM空值包大小，不建立固定字段的多层JSON字典。

    参数: frame为本次_frame刚校验的LegacyRawFrame；sequence为已校验原生非负int。
    返回: 含空values字典的精确UTF-8字节数。异常: 原整数转换、文本编码或大小错误。
    边界: 标志按true/false计长，未知is_rx按null计长；原浮点repr保负零和指数，data每字节为两位hex。
    """
    # 序号在request_id和record.sequence各出现一次；沿用原标量的超大整数限制。
    size = (_ITEM_FIXED_BYTES + 2 * _scalar_size(sequence, MAX_WIRE_BYTES)
            + len(repr(frame.timestamp)) + len(str(frame.arbitration_id))
            + len(str(frame.dlc)) + 2 * len(frame.data))
    # 六个严格bool及可未知的is_rx：false为5字节，true/null均4字节。
    size += 35 - sum((frame.is_extended_id, frame.is_remote_frame, frame.is_error_frame,
                      frame.is_fd, frame.is_rx is not False, frame.bitrate_switch, frame.error_state_indicator))
    # channel可能是Unicode/转义文本、int或None，继续使用原精确标量编码规则。
    size += _scalar_size(frame.channel, MAX_WIRE_BYTES)
    if size > MAX_WIRE_BYTES:
        raise ValueError('wire包超过65536字节')
    return size


def _validate_native_frame(msg, values, sequence):
    """校验原生CAN消息的字段快照，不为不会保存的帧构造冻结模型。

    参数: msg已由调用方确认是同次旧库的精确Message类型；values和sequence仍未校验。
    返回: None。异常: 与原_frame及未选记录检查一致的字段、值、编码或大小错误。
    流程: 按原构造实参顺序读取字段和转换data，随后保持原模型的校验先后。
    常见完整值字典可用安全上界证明合法；无法证明时仍走原精确检查函数。
    """
    timestamp = arbitration_id = extended = remote = error = channel = dlc = data = None
    fd = rx = bitrate = indicator = name = value = None
    try:
        if len(msg.data) > 64:
            raise ValueError('原报文data超过64字节，不能先复制再拒绝')
        timestamp = msg.timestamp
        arbitration_id = msg.arbitration_id
        extended = msg.is_extended_id
        remote = msg.is_remote_frame
        error = msg.is_error_frame
        channel = msg.channel
        dlc = msg.dlc
        # bytes转换在后四个标志取值之前；自定义data的异常和副作用不得被提前校验改变。
        data = bytes(msg.data)
        fd = msg.is_fd
        rx = msg.is_rx
        bitrate = msg.bitrate_switch
        indicator = msg.error_state_indicator
        if type(timestamp) is not float or not isfinite(timestamp):
            raise ValueError('原报文timestamp需要有限float秒')
        _integer(arbitration_id, 'arbitration_id', maximum=0x1FFFFFFF)
        _integer(dlc, 'dlc', maximum=64)
        if type(data) is not bytes or len(data) > 64:
            raise ValueError('原报文data需要不超过64字节的bytes')
        if channel is not None and type(channel) not in (int, str):
            raise TypeError('原报文channel需要int/str/None')
        if type(channel) is str and len(channel) > MAX_WIRE_BYTES:
            raise ValueError('原报文channel文本过长')
        # 公共原帧先检查可未知方向，再检查其余严格布尔标志。
        if rx is not None and type(rx) is not bool:
            raise TypeError('is_rx需要bool或未知None')
        if not (type(extended) is bool and type(remote) is bool and type(error) is bool
                and type(fd) is bool and (type(rx) is bool or rx is None) and type(bitrate) is bool
                and type(indicator) is bool):
            # 只在错误路径建立名称对照，仍报告原循环遇到的第一个坏标志。
            for name, value in (('is_extended_id', extended), ('is_remote_frame', remote),
                    ('is_error_frame', error), ('is_fd', fd), ('is_rx', rx),
                    ('bitrate_switch', bitrate), ('error_state_indicator', indicator)):
                if name == 'is_rx':
                    if type(value) is not bool and value is not None:
                        raise TypeError('is_rx需要bool或未知None')
                elif type(value) is not bool:
                    raise TypeError(name + '需要bool')
        _integer(sequence, 'sequence')
        if not isinstance(values, Mapping):
            raise TypeError('解码记录需要LegacyRawFrame与数值Mapping')
        # 只保存校验结论，没有后续编码或复制；完整上界已足够时无需算出精确长度。
        if _small_item_fits(values, sequence, channel):
            return
        # 与_item_base_size相同的原ITEM外壳；直接使用刚核过的局部快照，不重读消息。
        size = (_ITEM_FIXED_BYTES + 2 * _scalar_size(sequence, MAX_WIRE_BYTES)
            + len(repr(timestamp)) + len(str(arbitration_id)) + len(str(dlc)) + 2 * len(data)
            + 35 - (extended + remote + error + fd + (rx is not False) + bitrate + indicator))
        size += _scalar_size(channel, MAX_WIRE_BYTES)
        if size > MAX_WIRE_BYTES:
            raise ValueError('wire包超过65536字节')
        _decoded_values_size(values, MAX_WIRE_BYTES - size + 2)
    finally:
        # 上层保留原异常时，traceback不继续占用当前消息、完整值或原payload快照。
        msg = values = sequence = timestamp = arbitration_id = extended = remote = error = channel = None
        dlc = data = fd = rx = bitrate = indicator = name = value = None


def validate_discarded(msg, values, sequence, *, native_message_type=None):
    """确认未保留原消息仍满足完整记录边界，不因批次选择跳过坏数据。

    参数: msg为本次原yield消息；values为原parse返回的完整Mapping；sequence为原序号。
        native_message_type可由worker在旧库加载完成后传入其真实Message类；默认不启用快路。
    返回: None；既不复制values，也不持有通过检查的数据。
    异常: 原帧、序号、Mapping、信号名称/类型、Unicode或单条超限错误原样传播。
    处理流程: 原字段校验→安全上界正证明，或原ITEM精确计长与完整values检查。没有待保存副本，
        所以不执行公共LegacyDecodedFrame为防止复制时Mapping变化而进行的第二遍检查。
    """
    frame = None
    try:
        if native_message_type is not None and type(msg) is native_message_type:
            return _validate_native_frame(msg, values, sequence)
        # 保留原调用表达式的检查先后：先构造原帧，再检查序号和返回值容器。
        frame = _frame(msg)
        _integer(sequence, 'sequence')
        if not isinstance(values, Mapping):
            raise TypeError('解码记录需要LegacyRawFrame与数值Mapping')
        # 外壳已含{}的两个字节，扣除外壳后须还给values这两个字节的可用量。
        available = MAX_WIRE_BYTES - _item_base_size(frame, sequence) + 2
        _decoded_values_size(values, available)
    finally:
        # 调用方可能保存原异常，辅助函数的traceback不额外保活本条msg/values/原帧。
        msg = values = frame = None
