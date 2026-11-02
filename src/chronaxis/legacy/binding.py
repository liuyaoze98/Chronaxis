"""用报文 ID、所需信号和实际帧类型选择 DBC 定义。

本模块只使用调用方已加载的数据库，不打开 DBC 或日志。候选表仅覆盖当前
请求字段；每次运行保存有限的已见身份，避免省略帧型时混合两种同 ID 报文。
"""


def field_matches(field, frame):
    """检查声明是否接受当前实际帧。参数: field定位、frame原帧。返回: bool。异常: 属性错误。
    """
    # 只把未填写的类型当作开放条件；False是明确的标准帧或经典CAN约束。
    return (field.channel == frame.channel and field.frame_id == frame.arbitration_id
            and (field.is_extended is None or field.is_extended == frame.is_extended_id)
            and (field.is_fd is None or field.is_fd == frame.is_fd))


def dbc_candidates(db, frame_id, signal_names=(), is_extended=None, is_fd=None):
    """筛出定义候选，保留同 ID 不同帧型，不采用数据库的最后一项覆盖。

    参数: db为已加载数据库；frame_id整数；signal_names所需名称；两个帧型可省略。
    返回: 候选消息tuple。异常: ValueError为报文或信号不存在；不读取日志。
    """
    # 同数值ID可以同时有标准帧和扩展帧定义，不能使用只保留其中一项的ID字典。
    messages = tuple(message for message in db.messages if message.frame_id == frame_id)
    if not messages:
        raise ValueError('DBC中没有报文ID: ' + str(frame_id))
    # 先区分缺失信号，避免把错误名称误报为缺少帧型。
    named = tuple(message for message in messages
                  if all(sum(signal.name == name for signal in message.signals) == 1
                         for name in signal_names))
    if not named:
        raise ValueError('DBC报文中没有唯一的所需信号: ' + ', '.join(signal_names))
    # 保留用户批准的单向兼容：DBC标为FD、实际选择经典CAN；反方向不放宽。
    selected = tuple(message for message in named
                     if (is_extended is None or message.is_extended_frame == is_extended)
                     and (is_fd is None or message.is_fd == is_fd
                          or message.is_fd is True and is_fd is False))
    if not selected:
        raise ValueError('DBC报文与指定标准/扩展帧或CAN/FD不匹配: ' + str(frame_id))
    # 同一帧型仍有两份定义时，之后读取实际帧也无法消除歧义，须现在拒绝。
    kinds = [(message.is_extended_frame, message.is_fd) for message in selected]
    if len(set(kinds)) != len(kinds):
        raise ValueError('DBC报文在相同ID、信号和帧型下仍不唯一，请修正DBC')
    return selected


def select_message(candidates, frame):
    """按实际类型选唯一定义，允许已批准的 DBC FD 与实际经典 CAN 差异。

    参数: candidates消息tuple、frame实际帧。返回: 唯一消息或None表示不匹配。
    异常: ValueError为实际类型仍不能消除多定义歧义。
    """
    # 按文件中真实帧型筛选，不用载荷长度或ID大小推测类型。
    typed = tuple(message for message in candidates
                  if message.is_extended_frame == frame.is_extended_id
                  and (message.is_fd == frame.is_fd or message.is_fd and not frame.is_fd))
    # 同型定义优先，只有没有同型定义时才使用已批准的单向兼容。
    exact = tuple(message for message in typed if message.is_fd == frame.is_fd)
    selected = exact or typed
    if len(selected) > 1:
        raise ValueError('DBC中同ID和帧型仍有多个定义，请修正DBC或信号绑定')
    return selected[0] if selected else None


class FrameBindingResolver:
    """持有本次所需定义及已见身份；不保存报文载荷或无关信号。
    """

    def __init__(self, db, fields):
        """建立有限候选表。参数: db已有DBC、fields字段tuple。返回: None。异常: 定位错误。
        """
        # 候选与缓存只属于本次读取；按ID缩小逐帧工作范围，不保存原帧内容。
        self.by_id = {}
        self.database = db
        self.candidates = {}
        self.seen = {}
        self.resolved = {}
        for field in dict.fromkeys(fields):
            self.candidates[field] = dbc_candidates(db, field.frame_id, (field.signal,),
                                                    field.is_extended, field.is_fd)
            self.by_id.setdefault(field.frame_id, []).append(field)

    def fields_for(self, frame):
        """取得真实匹配字段，并拒绝后续帧改变同一省略型绑定的身份。

        参数: frame实际数据帧。返回: 匹配字段tuple。异常: ValueError为运行中出现歧义。
        """
        # 远程帧和错误帧没有普通信号更新；成功匹配的身份可在后续同型帧复用。
        if frame.is_remote_frame or frame.is_error_frame:
            return ()
        key = (frame.channel, frame.arbitration_id, frame.is_extended_id, frame.is_fd)
        if key in self.resolved:
            return self.resolved[key][0]
        # 对每个实际包含目标信号的候选检查身份；无关类型不清掉原信号的有效值。
        result = []
        for field in self.by_id.get(frame.arbitration_id, ()):
            if not field_matches(field, frame) or select_message(self.candidates[field], frame) is None:
                continue
            identity = (frame.is_extended_id, frame.is_fd)
            previous = self.seen.get(field)
            if previous is not None and previous != identity:
                missing = 'is_extended' if previous[0] != identity[0] else 'is_fd'
                raise ValueError('同一绑定匹配多种实际帧，请补充 ' + missing + ': ' + field.signal)
            self.seen[field] = identity
            result.append(field)
        # 只缓存匹配到已声明字段的帧，避免无关ID使缓存随日志规模增长。
        fields = tuple(result)
        if fields:
            self.resolved[key] = (fields, self.message_for(frame, fields))
        return fields

    def message_for(self, frame, fields):
        """核同一帧的字段来自同一解码定义。参数: frame原帧、fields匹配字段。返回: 消息或None。异常: 歧义。
        """
        # 同一帧的多个目标信号必须共用同一DBC消息对象，不能拼接不同定义的结果。
        key = (frame.channel, frame.arbitration_id, frame.is_extended_id, frame.is_fd)
        if key in self.resolved:
            return self.resolved[key][1]
        messages = []
        for field in fields:
            message = select_message(self.candidates[field], frame)
            if message is not None and all(message is not other for other in messages):
                messages.append(message)
        if len(messages) > 1:
            raise ValueError('同一帧的信号指向多个DBC定义，无法唯一解码')
        return messages[0] if messages else None

    def missing_flags(self, channel, frame_id, extended, fd):
        """为缺少帧型列的原始CSV寻找唯一声明，绝不按小ID或短载荷猜经典帧。

        参数: channel/frame_id为已解析身份；extended/fd为实际列值或None。
        返回: 两个已确定bool。异常: ValueError提示缺失的源列或绑定帧型。
        """
        # 已绑定字段先提供候选；DBC为FD时不能据此猜实际CSV一定是FD。
        choices = set()
        fields = tuple(field for field in self.by_id.get(frame_id, ()) if field.channel == channel)
        for field in fields:
            for message in self.candidates[field]:
                for candidate_fd in ((field.is_fd,) if field.is_fd is not None
                                     else (False, True) if message.is_fd else (False,)):
                    choices.add((message.is_extended_frame, candidate_fd))
        if not fields:
            # 导出未绑定的原帧仍需完整身份，不能替无关帧伪造标准/经典标记。
            for message in self.database.messages:
                if message.frame_id == frame_id:
                    for candidate_fd in ((False, True) if message.is_fd else (False,)):
                        choices.add((message.is_extended_frame, candidate_fd))
        # 有列值时以实际列值收窄；只有唯一剩余组合才能补齐缺列。
        choices = {pair for pair in choices if (extended is None or pair[0] == extended)
                   and (fd is None or pair[1] == fd)}
        if len(choices) != 1:
            missing = 'is_extended_id / is_extended' if extended is None and len({p[0] for p in choices}) != 1 else 'is_fd'
            raise ValueError('CSV缺少可唯一确定的帧型，请补充列映射或绑定参数 ' + missing)
        return next(iter(choices))
