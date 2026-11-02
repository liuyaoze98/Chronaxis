"""保存原始CAN记录及位置；文本用物理行，BLF用记录序号。

文本解析器输出RawCANRecord：整数纳秒供分析，LegacyRawFrame仅复用已有报文
字段模型供后续DBC和写出接口使用。其float秒是兼容表示，不替代精确时间。
本模块不打开文件、不加载DBC、不生成信号，CAN身份不会进入通用时序核心。
"""

from dataclasses import dataclass
from pathlib import Path

from ..legacy.records import LegacyRawFrame
from ..timebase.conversion import require_int64_ns


class CANTextError(ValueError):
    """表示具体文本文件某物理行不能解释为所选版本的报文。"""

    def __init__(self, path, line_number, reason):
        """保留可程序读取的位置。参数: path路径、line_number物理行、reason原因。

        返回: 定位异常。异常: 无；不包含整行私人载荷或隐式记录日志。
        """
        # 消息包含定位和失败原因，消费者无需从整段输入猜测出错记录。
        self.path, self.line_number, self.reason = Path(path), line_number, reason
        position = str(line_number) if line_number is not None else '二进制记录'
        super().__init__(f'{self.path}:{position}: {reason}')


@dataclass(frozen=True)
class RawCANRecord:
    """保存一次真实输入；文本直接转纳秒，BLF沿用读取库的浮点秒转换。"""

    frame: LegacyRawFrame  # 原帧公开字段，通道统一从0开始。
    time_ns: int  # 按明确参考原点解释后的精确int64纳秒。
    path: Path  # 实际读取文件，不声明为绝对路径或内容指纹。
    line_number: int | None  # 文本物理行；二进制BLF没有行号，使用sequence定位。
    sequence: int  # 同次读取从0开始，允许同时间不同载荷。
    raw_time: str | None  # 仅原文诊断请求保留；普通计算为None。
    parser_version: str  # 固定格式版本，不在半途自动切换。
    dlc_code: int | None  # 真正DLC编码，错误帧没有该值。
    time_quantized: bool = False  # 文本比纳秒更细时的实际舍入事实。
    source_time_ns: int | None = None  # 显式平移前的精确时间；手工旧构造省略时与time_ns相同。

    def __post_init__(self):
        """检查定位和快照。参数: 无。返回: None。异常: 类型、时间或位置错误。
        """
        # 类型保持明确，不能用bool充当序号，也不把扩展帧标志从ID猜出。
        if type(self.frame) is not LegacyRawFrame or not isinstance(self.path, Path):
            raise TypeError('文本CAN记录需要原帧快照和Path')
        require_int64_ns(self.time_ns)
        if self.source_time_ns is not None:
            require_int64_ns(self.source_time_ns)
        if ((self.line_number is None and self.parser_version != 'blf-v1')
                or self.line_number is not None and (type(self.line_number) is not int or self.line_number < 1)
                or type(self.sequence) is not int or self.sequence < 0):
            raise ValueError('文本CAN位置需要正物理行和非负序号')
        if (self.raw_time is not None and (type(self.raw_time) is not str or not self.raw_time)
                or type(self.parser_version) is not str or not self.parser_version
                or type(self.time_quantized) is not bool):
            raise ValueError('文本CAN记录需要时间原文、版本和量化标志')
        if self.dlc_code is not None and (type(self.dlc_code) is not int or not 0 <= self.dlc_code <= 15):
            raise ValueError('DLC编码需0到15或None')
