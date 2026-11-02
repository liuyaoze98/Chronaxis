"""把三种原始报文入口的必要值交付给同一个逐消息计算模型。

投影只保存有限字段定位和可共享的来源引用。BLF交付的键是DBC信号名，
文本入口交付的键是规范字段；转换后均为原DBC信号名，不保留载荷副本、
原时间字符串或第二套时间。LegacyDecodedUpdate是已有计算模型的名称，
使用它不代表复现旧程序的缓存行为。
"""

from types import MappingProxyType

from ..core.models import SourceRef
from ..core.validation import require_identifier
from ..legacy.records import LegacyCANField
from ..legacy.updates import LegacyDecodedUpdate, LegacyUntimedUpdate


def require_message_keys(keys, *, channel=None):
    """校验有限触发声明。参数: keys完整定位tuple、可选来源通道。返回: 原tuple。异常: ValueError。"""
    if type(keys) is not tuple or len(keys) > 4096:
        raise ValueError('消息触发定位需要最多4096项tuple')
    for key in keys:
        if (type(key) is not tuple or len(key) != 4 or type(key[0]) is not int or key[0] < 0
                or type(key[1]) is not int or key[2] is not None and type(key[2]) is not bool
                or key[3] is not None and type(key[3]) is not bool
                or not 0 <= key[1] <= (0x7ff if key[2] is False else 0x1fffffff)
                or channel is not None and key[0] != channel):
            raise ValueError('消息触发定位需要合法通道、ID、扩展及FD标志，且属于当前来源通道')
    return keys


class CANUpdateProjection:
    """按完整报文身份索引所需字段；同一帧的多个别名只传一次物理值。"""

    def __init__(self, source, session_id, fields, *, message_keys=(), clock_fields=()):
        """建立有限投影，不读取DBC或输入文件。

        参数: source/session_id为来源和会话；fields为所需LegacyCANField元组；
            message_keys为无值公式仍需触发的(channel,id,extended,fd)元组；
            clock_fields只借DBC候选确定驱动帧，不加入值解码或值输出。
        返回: None；初始化实例状态。异常: TypeError/ValueError为字段、身份或同帧信号定位冲突。
        """
        if (type(fields) is not tuple or type(clock_fields) is not tuple
                or any(type(field) is not LegacyCANField for field in (*fields,*clock_fields))):
            raise TypeError('消息投影需要LegacyCANField tuple')
        require_identifier(source, 'message.source')
        require_identifier(session_id, 'message.session_id')
        groups = {}
        for key in require_message_keys(message_keys):
            groups.setdefault(key, {})
        self._value_fields = frozenset(fields)
        for field in dict.fromkeys((*fields, *clock_fields)):
            key = (field.channel, field.frame_id, field.is_extended, field.is_fd)
            group = groups.setdefault(key, {})
            if field.signal in group and group[field.signal] != field:
                raise ValueError('同一报文信号存在不同定位')
            group[field.signal] = field
        # 引用只标识必需的来源及代表字段，逐帧序号由已有更新模型保存一次。
        self._groups = MappingProxyType({key: (tuple(group.values()),
            SourceRef(session_id, source, next(iter(group.values())).key if group else '__raw_message__'))
            for key, group in groups.items()})
        self.source = source
        self._seen = {}
        self._resolved = {}
        self._dbc_frames = {}
        self.compatibility_fields = {}

    def configure_metadata(self, facts):
        """安装同次DBC的有限候选。参数: facts字段事实。返回: None。异常: 非法定位错误。
        """
        from ..legacy.records import field_from_dict
        self._dbc_frames = {field_from_dict(dict(fact['locator'])): tuple(tuple(pair) for pair in fact['dbc_frames'])
                            for fact in facts if 'dbc_frames' in fact}

    def for_read(self, facts):
        """为单次读取隔离已见状态。参数: facts同次DBC事实。返回: 新投影。异常: 元数据错误。
        """
        from copy import copy
        result = copy(self)
        result._seen = {}
        result._resolved = {}
        result.compatibility_fields = {}
        result.configure_metadata(facts)
        return result

    def _matching(self, frame):
        """匹配四种可选选择器，记录唯一实际身份。参数: frame。返回: 字段和引用或None。异常: 迟到歧义。
        """
        if frame.is_remote_frame or frame.is_error_frame:
            return None
        frame_key = (frame.channel, frame.arbitration_id, frame.is_extended_id, frame.is_fd)
        if frame_key in self._resolved:
            return self._resolved[frame_key]
        actual = (frame.is_extended_id, frame.is_fd)
        fields, reference = {}, None
        for extended in (frame.is_extended_id, None):
            for fd in (frame.is_fd, None):
                key = (frame.channel, frame.arbitration_id, extended, fd)
                item = self._groups.get(key)
                if item is None:
                    continue
                # 候选定义里没有该信号的另一种同ID帧属于无关输入，不制造失效更新。
                selected = []
                for field in item[0]:
                    candidates = self._dbc_frames.get(field)
                    if candidates is not None and not any(e == actual[0] and (f == actual[1] or f and not actual[1])
                                                          for e, f in candidates):
                        continue
                    selected.append(field)
                    if candidates is not None and not actual[1] and (actual[0], False) not in candidates:
                        self.compatibility_fields[field] = actual[0]
                if item[0] and not selected:
                    continue
                for identity_key in selected or (key,):
                    previous = self._seen.get(identity_key)
                    if previous is not None and previous != actual:
                        missing = 'is_extended' if previous[0] != actual[0] else 'is_fd'
                        raise ValueError('同一报文绑定匹配多种实际帧，请补充 ' + missing)
                    self._seen[identity_key] = actual
                fields.update((field, None) for field in selected)
                reference = reference or item[1]
        if reference is None:
            return None
        result = (tuple(fields), reference)
        # 只缓存已声明且成功匹配的身份，最多每声明四种，不随无关报文数量增长。
        self._resolved[frame_key] = result
        return result

    def accepts_frame(self, frame):
        """判断是否有值或触发需求。参数: 原帧。返回: bool。异常: 非原帧属性错。"""
        return self._matching(frame) is not None

    def fields_for(self, frame):
        """定位目标数据帧，未知ID/其他通道或帧型不参与本投影。

        参数: frame为实际读取器交付且已校验的原帧。返回: 字段元组，非目标为空。
        异常: 非原帧对象缺少必需属性时AttributeError；不吞读取错误。
        """
        item = self._matching(frame)
        return () if item is None else item[0]

    def build(self, frame, sequence, values, time_ns, *, canonical_keys=False):
        """只拣选计算字段，复用已有有时间/无时间更新及其严格值检查。

        参数: frame为原帧，sequence为本来源原序号，values为已解码映射，
            time_ns为实际映射时间或明确未采集的None；canonical_keys说明文本字段键。
        返回: LegacyDecodedUpdate/LegacyUntimedUpdate；非目标数据帧返回None。
        异常: 类型/数值/身份错误原样传播，不缓存前条值补齐缺失。
        """
        if type(canonical_keys) is not bool:
            raise TypeError('canonical_keys需要bool')
        item = self._matching(frame)
        if item is None:
            return None
        fields, reference = item
        selected = {field.signal: values.get(field.key if canonical_keys else field.signal)
                    for field in fields if field in self._value_fields}
        update_type = LegacyUntimedUpdate if time_ns is None else LegacyDecodedUpdate
        return update_type(time_ns, self.source, frame.channel, frame.arbitration_id,
                    frame.is_extended_id, frame.is_fd, frame.is_remote_frame,
                    frame.is_error_frame, reference, sequence, sequence, selected)
