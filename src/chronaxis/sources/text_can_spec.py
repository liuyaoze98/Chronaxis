"""冻结ASC/BLF连续来源或原始CSV到DBC信号的声明，不在构造时读取文件。

每个输入保留A/B已校验的解析配置，文件严格按声明顺序接续，不排序或猜测换日。
时间在各解析器中已变为纳秒；本层不再施加偏移。通用时基由调用方显式提供。
混合BLF复用python-can格式读取；既有纯BLF的LegacyCANSpec调用路径保持原样。
"""

from dataclasses import dataclass
from pathlib import Path
from ..core.models import TimebaseSpec
from ..core.validation import require_identifier
from .asc import ASCSpec
from .raw_csv import CANCSVSpec
from .blf import BLFSpec


@dataclass(frozen=True)
class CANTextSpec:
    """同一来源的显式连续输入、单通道/DBC和已声明的共同时间基准。"""

    name: str  # 来源安全名称，不是DBC消息名。
    inputs: tuple[ASCSpec | CANCSVSpec | BLFSpec, ...]  # ASC/BLF可混合；CSV需统一布局。
    dbc_path: Path  # 单次只读加载的DBC，不在构造时核存在性。
    channel: int  # 0基目标信号通道；其他通道原帧仍向导出层交付。
    timebase: TimebaseSpec  # 相同ID本身不证明物理同步。

    decode_policy: str = 'legacy'  # 旧文本失败停止；新strict/partial解码失败置无效继续。
    input_check: str = 'auto'  # full检查全部帧时间顺序；auto按实际消费者选择。
    file_merge: str = 'concatenate'  # concatenate按文件顺序；time_order按原时间稳定归并。

    def __post_init__(self):
        """核声明与支持范围。参数: 无。返回: None。异常: 名称/类型/文件集合或时基不合法。
        """
        # ASC/BLF自描述帧可连续；CSV需要专门布局，不能混入这组自动识别文件。
        from ..legacy.decode_policy import validate_decode_policy
        validate_decode_policy(self.decode_policy)
        if type(self.input_check) is not str or self.input_check not in ('auto','full'):
            raise ValueError('文本CAN input_check需要auto或full')
        if type(self.file_merge) is not str or self.file_merge not in ('concatenate', 'time_order'):
            raise ValueError('file_merge需要concatenate或time_order')
        require_identifier(self.name,'text_can.name')
        if (type(self.inputs) is not tuple or not 1 <= len(self.inputs) <= 4096
                or any(type(item) not in (ASCSpec,CANCSVSpec,BLFSpec) for item in self.inputs)
                or any(type(item) is CANCSVSpec for item in self.inputs)
                and any(type(item) is not CANCSVSpec for item in self.inputs)):
            raise ValueError('CAN需要1到4096个ASC/BLF或同布局CSV解析声明')
        if not isinstance(self.dbc_path,Path) or not isinstance(self.timebase,TimebaseSpec):
            raise TypeError('文本CAN需要DBC Path及TimebaseSpec')
        if type(self.channel) is not int or self.channel < 0:
            raise ValueError('文本CAN通道需要非负原生整数')

    @property
    def source_type(self):
        """区分原始来源。返回can_asc、asc_or_blf或raw_can_csv，不发生I/O。
        """
        if any(type(item) is BLFSpec for item in self.inputs):
            return 'asc_or_blf'
        return 'can_asc' if type(self.inputs[0]) is ASCSpec else 'raw_can_csv'

    @property
    def offset_ns(self):
        """说明本层不再移动解析后时间。参数: 无。返回: 0。异常: 无。
        """
        return 0
