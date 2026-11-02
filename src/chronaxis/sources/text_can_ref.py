"""保存新文本CAN样本的精确原行引用，供信号历史和结果白名单编码。

输入是已有规范CAN字段键和实际读取的文件/行/原时间，输出冻结SourceRef子类。
字段键仍区分通道、消息、信号、ID及帧型；本引用另外保留文件次序与文件内序号。
不打开文件、不解码、不将float秒当作精确时间，也不冒称冻结旧profile的输出。
"""

from dataclasses import dataclass
from ..core.models import SourceRef
from ..core.validation import require_text
from .can_spec import can_field_from_key


@dataclass(frozen=True)
class CANTextSourceRef(SourceRef):
    """定位一个实际文本记录中的信号；通用field保存完整规范CAN定位。"""

    path: str  # 实际输入路径，保持读取声明，不做隐式resolve。
    parser_version: str  # ASC或原始CSV解析版本。
    line_number: int | None  # 文本物理行；BLF为None，以record_sequence定位。
    input_index: int  # 显式文件列表中的0基位置。
    record_sequence: int  # 文件内原记录序号，同刻不同帧不去重。
    yield_sequence: int  # 本次连续文件读取的全局0基原帧序号。
    raw_time: str | None  # 文本原文字；BLF没有时间文字，不构造副本。
    time_quantized: bool  # 源文字转纳秒时是否实际量化。

    def __post_init__(self):
        """核对冻结定位的结构。参数: 无。返回: None。异常: 类型/规范字段/位置非法。
        """
        # 先核会话/来源归属，再核原CAN六字段；不把原信号名改成表达式别名。
        super().__post_init__()
        can_field_from_key(self.field)
        for label in ('path','parser_version'):
            require_text(getattr(self,label),'text_can_ref.'+label)
        if self.parser_version == 'blf-v1':
            if self.line_number is not None or self.raw_time is not None:
                raise ValueError('BLF引用没有物理行号或原时间文字')
        else:
            require_text(self.raw_time,'text_can_ref.raw_time')
        # 物理行从1开始，其余序号从0开始，bool不能作为整数通过。
        for label in ('line_number','input_index','record_sequence','yield_sequence'):
            value = getattr(self,label)
            if label == 'line_number' and self.parser_version == 'blf-v1':
                continue
            if type(value) is not int or value < (1 if label=='line_number' else 0):
                raise ValueError('文本CAN引用位置非法: '+label)
        if type(self.time_quantized) is not bool:
            raise TypeError('文本CAN量化标志需要bool')
