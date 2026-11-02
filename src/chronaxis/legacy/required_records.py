"""[home] 保存按需分析使用的CAN身份和值，允许明确不采集时间。

输入是已匹配原消息的必要身份和所需解码值；输出为冻结模型与有界JSON记录。
时间为None表示没有采集，不能代替零秒。记录不保存载荷、DLC和写出标志，不能
用于原始BLF导出。复用既有严格数值、非有限标签和64KiB限制；无I/O或跨请求状态。
"""

from collections.abc import Mapping
from dataclasses import dataclass
import json
from math import isfinite
from types import MappingProxyType

from .records import (MAX_WIRE_BYTES, _integer, _shape, _wire_tree, _decoded_values_size,
    _decoded_entry_size, _value_to_wire, _value_from_wire, _unique_object, _reject_constant)


_FRAME_FIELDS = ('timestamp', 'arbitration_id', 'channel', 'is_extended_id', 'is_fd',
                 'is_remote_frame', 'is_error_frame')


@dataclass(frozen=True)
class RequiredCANFrame:
    """仅持有所需匹配身份，时间None明确表示未采集；模型不具备原始写出能力。"""

    timestamp: float | None  # 有限原float秒，或本任务未采集。
    arbitration_id: int  # 原29位以内ID，不含通道。
    channel: int | str | None  # 原通道身份，保持原类型，不猜测。
    is_extended_id: bool  # 原标准/扩展标志。
    is_fd: bool  # 原经典CAN/FD标志。
    is_remote_frame: bool  # 匹配时排除远程帧所需。
    is_error_frame: bool  # 匹配时排除错误帧所需。

    def __post_init__(self):
        """检查身份及可选时间。参数: 无。返回: None。异常: 原类型或边界错误。"""
        if self.timestamp is not None and (type(self.timestamp) is not float or not isfinite(self.timestamp)):
            raise ValueError('所需报文timestamp需要有限float秒或None')
        _integer(self.arbitration_id, 'arbitration_id', maximum=0x1fffffff)
        if self.channel is not None and type(self.channel) not in (int, str):
            raise TypeError('所需报文channel需要int/str/None')
        if type(self.channel) is str and len(self.channel) > MAX_WIRE_BYTES:
            raise ValueError('所需报文channel文本过长')
        for name in ('is_extended_id', 'is_fd', 'is_remote_frame', 'is_error_frame'):
            if type(getattr(self, name)) is not bool:
                raise TypeError(name + '需要bool')


def required_frame_to_dict(frame):
    """输出固定身份字段。参数: frame为RequiredCANFrame。返回: dict。异常: TypeError。"""
    if type(frame) is not RequiredCANFrame:
        raise TypeError('需要RequiredCANFrame')
    return {name: getattr(frame, name) for name in _FRAME_FIELDS}


@dataclass(frozen=True)
class RequiredDecodedFrame:
    """持有一次目标原序号和冻结所需值；不根据未采集的时间建立时序坐标。"""

    sequence: int  # 原yield序号，可有无关帧形成的间隙。
    frame: RequiredCANFrame  # 必要身份与可选时间。
    values: Mapping[str, int | float | bool]  # 缺键保持缺失，诊断非有限值保留。

    def __post_init__(self):
        """先检查上界再复制外部Mapping。参数: 无。返回: None。异常: 类型、编码或超限错误。"""
        _integer(self.sequence, 'sequence', maximum=(1 << 64)-1)
        if type(self.frame) is not RequiredCANFrame or not isinstance(self.values, Mapping):
            raise TypeError('按需记录需要RequiredCANFrame与数值Mapping')
        # 外壳与值共用64KiB上限；复制时继续以这次精确余量防止可变Mapping扩大前缀。
        base = _wire_tree({'op': 'item', 'request_id': self.sequence,
            'record': {'sequence': self.sequence, 'frame': required_frame_to_dict(self.frame), 'values': {}}})
        available = MAX_WIRE_BYTES-base+2
        _decoded_values_size(self.values, available)
        copied, used = {}, 2
        for name, value in self.values.items():
            # 外部Mapping两次遍历可变化，每个插入仍须验证；常见worker原生字典复用上界。
            separator = 1 if copied else 0
            used += separator + _decoded_entry_size(name, value, available-used-separator)
            copied[name] = value
        object.__setattr__(self, 'values', MappingProxyType(copied))


def required_to_dict(record):
    """编码固定按需记录。参数: record为RequiredDecodedFrame。返回: dict。异常: 类型或值错误。"""
    if type(record) is not RequiredDecodedFrame:
        raise TypeError('需要RequiredDecodedFrame')
    return {'sequence': record.sequence, 'frame': required_frame_to_dict(record.frame),
            'values': {name: _value_to_wire(value) for name, value in record.values.items()}}


def required_from_dict(value):
    """从独立JSON树恢复按需记录。参数: value为固定dict。返回: 冻结模型。异常: 形状、类型或限额错误。"""
    _shape(value, ('sequence', 'frame', 'values'), 'required decoded frame')
    _wire_tree(value)
    _shape(value['frame'], _FRAME_FIELDS, 'required CAN frame')
    if type(value['values']) is not dict:
        raise TypeError('required decoded values需要dict')
    return RequiredDecodedFrame(value['sequence'], RequiredCANFrame(**value['frame']),
        {name: _value_from_wire(item) for name, item in value['values'].items()})


def required_from_packet(payload):
    """严格解析单条按需JSON，固定模型检查代替同一树的重复通用遍历。

    参数: payload为64KiB内bytes。返回: 独立冻结模型。
    异常: UTF-8、重复键、深度、裸非有限常量或模型错误；不解任意对象标签。
    """
    parsed = values = frame = None
    try:
        if type(payload) is not bytes or not 0 < len(payload) <= MAX_WIRE_BYTES:
            raise ValueError('按需记录需要65536字节内bytes')
        parsed = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
        _shape(parsed, ('sequence', 'frame', 'values'), 'required decoded frame')
        _shape(parsed['frame'], _FRAME_FIELDS, 'required CAN frame')
        if type(parsed['values']) is not dict:
            raise TypeError('required decoded values需要dict')
        frame = RequiredCANFrame(**parsed['frame'])
        values = {name: _value_from_wire(item) for name, item in parsed['values'].items()}
        # 所有可接受容器都是固定浅层结构；未知嵌套先拒绝，不需要再次遍历JSON树。
        return RequiredDecodedFrame(parsed['sequence'], frame, values)
    finally:
        payload = parsed = values = frame = None
