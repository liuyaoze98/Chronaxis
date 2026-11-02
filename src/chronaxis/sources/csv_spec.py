"""声明独立已解码信号表的格式，并保存每个CSV样本的位置。

SignalCSVSpec接收有序路径、时间列、时间单位、时区、编码、分隔符和
缺失标记，输出冻结配置；构造仅检查声明，不打开文件或根据后缀猜格式。
CSVSourceRef在通用来源引用上增加文件路径、记录末物理行和原始单元格
文本，供实际读取后追溯。时间量化诊断单独保留，不从文件名推断观测范围。
"""

# encoding合法性可以静态检查，不读取输入表内容。
import codecs
# 冻结配置与继承来源引用，不创建可变全局状态。
from dataclasses import dataclass
# 绝对日期没有自身时区偏移时需要明确tzinfo，不能采用机器当前时区。
from datetime import tzinfo
# 文件路径只作声明，不查询文件状态、不打开文件，也不重新排序。
from pathlib import Path
# 每样本引用沿用已验收的会话/来源/字段校验。
from ..core.models import SourceRef, TimebaseSpec
# 时间类型区别于表示单位，不能互相猜测。
from ..core.types import TimeType
# 字段保留原文，来源名是简单标识。
from ..core.validation import require_identifier, require_text
# offset遵守精确纳秒范围。
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class SignalCSVSpec:
    """保存已解码信号表的格式和时钟声明，保留paths的给定顺序。

    name标识来源，paths指定连续输入文件；timebase给出相对公共起点或绝对
    时钟，time_column与unit解释时间单元格，offset_ns是显式纳秒偏移。
    timezone只用于缺少自身时区的绝对日期。encoding、sep和missing_values
    明确表格解析规则；声明检查不会核实文件存在性或实际表头。

    实际适配器把每行每个请求列当作一次观测。缺失文本精确匹配后转None，
    表示明确缺失更新；旧Filter输出中的空白未更新含义须另按旧来源契约接入。
    """

    name: str  # 当前计划来源名。
    paths: tuple[Path, ...]  # 明确连续文件顺序，不扫描目录自动排序。
    timebase: TimebaseSpec  # relative公共起点/absolute明确声明。
    time_column: str  # 原时间列名，必须在每个表头存在。
    unit: str  # s/ms/us/ns或absolute的ISO8601。
    offset_ns: int = 0  # 显式固定偏移，不能证明同步。
    timezone: tzinfo | None = None  # ISO无offset时明确采用的时区。
    encoding: str = 'utf-8'  # 不猜文件编码。
    delimiter: str = ','  # 单字符分隔符，不自动sniff。
    missing_values: tuple[str, ...] = ('',)  # 精确匹配原cell，不strip标记。

    def __post_init__(self) -> None:
        """检查表格格式与时间声明，保持路径和缺失标记的原顺序。

        参数:
            无。使用name、paths、timebase、time_column、unit、offset_ns、
            timezone、encoding、sep和missing_values字段。
        返回:
            None。只检查冻结实例，不读取表头或数据。
        异常:
            TypeError: 路径、时区或声明结构类型错误。
            ValueError: 时间单位、名称、分隔符或缺失标记不合法。
            LookupError: 编码名称不受本机编码注册表支持。
            OverflowError: offset_ns超出整数纳秒范围。
        """
        # 来源名必须是计划内安全别名。
        require_identifier(self.name, 'csv.name')
        # paths必须明确非空，不能接受字符串作为可迭代字符路径。
        if not isinstance(self.paths, tuple) or not self.paths or any(not isinstance(path, Path) for path in self.paths):
            # 不从目录猜测会话/文件顺序。
            raise TypeError('csv.paths需要非空tuple[Path]')
        # 必须明确时基/表示单位，ISO只用于absolute。
        if not isinstance(self.timebase, TimebaseSpec) or self.unit not in ('s', 'ms', 'us', 'ns', 'ISO8601') or self.unit == 'ISO8601' and self.timebase.time_type is not TimeType.ABSOLUTE:
            # 原始报文时间策略不在此通用表接口猜测。
            raise ValueError('csv时基/时间单位错误')
        # 原列名完整保留，不自动改名。
        require_text(self.time_column, 'csv.time_column')
        # 合法偏移也不会自动证明与另一来源已同步。
        require_int64_ns(self.offset_ns, 'csv.offset_ns')
        # 时区仅接受已经解析的显式tzinfo。
        if self.timezone is not None and not isinstance(self.timezone, tzinfo):
            # 配置解析层负责把地区时区名称或固定偏移文本转换为tzinfo。
            raise TypeError('csv.timezone需要tzinfo')
        # 编码名称是明确配置，查询注册表不会读取CSV文件。
        require_text(self.encoding, 'csv.encoding')
        # 未知编码在执行前报告，不尝试自动检测。
        codecs.lookup(self.encoding)
        # csv标准reader只接一个非换行分隔符。
        if type(self.delimiter) is not str or len(self.delimiter) != 1 or self.delimiter in '\r\n':
            # TSV可显式用tab，任意多字符分隔拒绝。
            raise ValueError('csv.delimiter需要单个非换行字符')
        # 标记可为空字符串但必须原生str、唯一冻结tuple。
        if not isinstance(self.missing_values, tuple) or any(type(item) is not str for item in self.missing_values) or len(set(self.missing_values)) != len(self.missing_values):
            # 不把未知格式猜为无效0。
            raise ValueError('csv.missing_values需要唯一字符串tuple')


@dataclass(frozen=True)
class CSVSourceRef(SourceRef):
    """保留单个已读取样本的文件位置和原始文本。

    继承的session_id、source_name和field确定会话、来源及原字段。
    path指出文件，line_number是CSV记录结束的物理行，time_text和value_text
    保留原单元格文本；time_quantized标记时间是否发生纳秒量化。
    引用不保存sequence，稳定原行序号由SignalSeries的sequence列另行保存。
    引号内跨多行的记录以最后物理行为位置，不能把它解释成记录首行。
    """

    path: str  # 实际读取路径原文。
    line_number: int  # csv reader给出的记录末物理行，1开始。
    time_text: str  # 原时间cell文本。
    value_text: str  # 原字段cell文本，解析异常诊断不丢原文。
    time_quantized: bool  # 时间转换曾按纳秒half-even量化。

    def __post_init__(self) -> None:
        """检查继承的来源身份和CSV附加定位，不访问路径。

        参数:
            无。读取来源身份、path、line_number、time_text、value_text和time_quantized。
        返回:
            None。文本保持原样，缺失单元格允许value_text为空字符串。
        异常:
            TypeError或ValueError: 来源名称、字段、路径、正整数行号或附加字段类型错误。
        副作用:
            无文件访问；引用构造本身不能证明path已经成功打开。
        """
        # 基类校验会话/来源/原字段，不能省略而只留下行号。
        super().__post_init__()
        # 路径文本必须非空；是否成功打开由实际读取适配器另行核实。
        require_text(self.path, 'csv_ref.path')
        # 物理行号明确正数，不接受True或0。
        if type(self.line_number) is not int or self.line_number <= 0 or type(self.time_text) is not str or type(self.value_text) is not str or type(self.time_quantized) is not bool:
            # 缺失cell可以value_text为空，不因此丢来源。
            raise ValueError('CSVSourceRef行号/文本/量化类型错误')
