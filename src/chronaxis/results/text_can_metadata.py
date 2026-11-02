"""保存新文本CAN同次读取取得的DBC身份、解析声明和实际观测事实。

这是can-text-v1的独立清单，不冒充旧进程READY或未计算的原文件哈希。
声明的路径/格式与实际读取计数分别保留；空来源不伪造首末时间。
"""

from dataclasses import dataclass
from ..core.validation import require_identifier,require_text
from ..timebase.conversion import require_int64_ns
from .can_metadata import CANUnitCheck,CANFrameFormatNotice


@dataclass(frozen=True)
class TextCANSourceMetadata:
    """仅接受冻结有限字段；实际事实由完成的ObservedSourceScan交付。"""

    source: str
    session_id: str
    source_type: str
    read_identity: str
    inputs: tuple[tuple[str,str,int], ...]
    dbc_path: str
    dbc_sha256: str
    cantools_version: str
    record_count: int
    decode_calls: int
    first_ns: int | None
    last_ns: int | None
    unit_checks: tuple[CANUnitCheck,...]
    frame_format_notices: tuple[CANFrameFormatNotice,...]=()
    profile: str='can-text-v1'
    decode_scope: str='requested'
    time_scope: str='source'

    def __post_init__(self):
        """核实结构及计数一致性，不读文件。参数: 冻结字段。返回: None。异常: 类型/值错误。
        """
        for name in ('source','session_id'):
            require_identifier(getattr(self,name),name)
        for name in ('read_identity','dbc_path','cantools_version'):
            require_text(getattr(self,name),name)
        if (self.source_type not in ('can_asc','asc_or_blf','raw_can_csv') or self.profile!='can-text-v1'
                or self.decode_scope!='requested' or self.time_scope!='source'):
            raise ValueError('文本CAN清单策略错误')
        if type(self.dbc_sha256) is not str or len(self.dbc_sha256)!=64 or any(c not in '0123456789abcdef' for c in self.dbc_sha256):
            raise ValueError('文本CAN清单需要实际DBC SHA256')
        if type(self.inputs) is not tuple or not 1<=len(self.inputs)<=4096:
            raise ValueError('文本CAN清单需要有限有序输入')
        for item in self.inputs:
            if type(item) is not tuple or len(item)!=3:
                raise ValueError('输入清单需要(path,parser,offset_ns)')
            require_text(item[0],'path'); require_text(item[1],'parser'); require_int64_ns(item[2],'offset_ns')
        if type(self.record_count) is not int or self.record_count<0 or type(self.decode_calls) is not int or not 0<=self.decode_calls<=self.record_count:
            raise ValueError('文本CAN实际帧数与解码次数错误')
        if not self.record_count:
            if self.first_ns is not None or self.last_ns is not None:
                raise ValueError('空文本CAN不能声明观测时间')
        else:
            require_int64_ns(self.first_ns,'first_ns'); require_int64_ns(self.last_ns,'last_ns')
            if self.first_ns>self.last_ns:
                raise ValueError('文本CAN观测时间倒退')
        if (type(self.unit_checks) is not tuple or any(type(x) is not CANUnitCheck for x in self.unit_checks)
                or type(self.frame_format_notices) is not tuple or any(type(x) is not CANFrameFormatNotice for x in self.frame_format_notices)):
            raise TypeError('文本CAN单位/帧型清单需要冻结模型tuple')
