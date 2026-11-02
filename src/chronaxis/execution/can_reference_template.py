"""复用已校验CAN定位的固定部分，逐条仍验证原序号、原时间和量化标志。

输入是同一运行绑定中的固定来源字段；构造时调用公开CANSourceRef完整验证一次。
输出仍是原生冻结CANSourceRef，所有字段及公开编码不变。这里只省固定声明的重复
规范JSON编码，不读取DBC、不改变reader/decoder，也不缓存报文。模板费用及生成引用
的费用由调用owner在创建前支付；模板随该owner释放，没有全局缓存或独立I/O。
"""

from math import isfinite
from types import MappingProxyType
from dataclasses import dataclass

from ..sources.can_spec import CANSourceRef, _nonnegative_integer


@dataclass(frozen=True, slots=True, init=False)
class CANReferenceTemplate:
    """持有一份只读固定字段快照；每次at只创建当前报文引用，不复用可变行。"""

    _fields: object  # 公开模型完整校验后的只读字段，不借用外部dict。

    def __init__(self, session_id, source_name, field, path, profile, channel,
                 signal, frame_id, is_extended, is_fd):
        """先用公开构造器校验固定字段，再保存独立只读快照。

        参数: 与CANSourceRef相同的十项固定字段；帧类型必须为实际值。
        返回: 已校验模板。异常: 原公开模型的身份/定位/类型/编码错误。
        """
        seed = None
        try:
            seed = CANSourceRef(session_id, source_name, field, path, profile, channel,
                signal, frame_id, is_extended, is_fd, 0, 0.0, False)
            # seed只有原生不可变字段；不把外部可变dict借给后续引用。
            object.__setattr__(self, '_fields', MappingProxyType(seed.__dict__.copy()))
        finally:
            seed = None

    def at(self, yield_sequence, timestamp_s, time_quantized):
        """校验逐条变化的事实，复制固定快照并交付原CANSourceRef。

        参数: 原yield非负整数、有限原生float秒、原生bool量化标志。
        返回: 新的冻结CANSourceRef；原始float位值和全部定位保持。
        异常: 与公开构造器动态字段相同的TypeError/ValueError，不隐式转换。
        """
        result = None
        try:
            _nonnegative_integer(yield_sequence, 'can_ref.yield_sequence')
            if type(timestamp_s) is not float:
                raise TypeError('CANSourceRef timestamp需要原生float秒')
            if not isfinite(timestamp_s):
                raise ValueError('CANSourceRef timestamp必须有限')
            if type(time_quantized) is not bool:
                raise TypeError('CANSourceRef time_quantized需要bool')
            # 固定字段只来自上面完整验证后的私有快照；不接自由dict或未验证模型。
            result = object.__new__(CANSourceRef)
            result.__dict__.update(self._fields)
            result.__dict__.update(yield_sequence=yield_sequence, timestamp=timestamp_s,
                time_quantized=time_quantized)
            return result
        finally:
            self = result = None
