"""声明已解码信号层的选择行，保留时间、原值、三值状态和来源身份。

输入为CalculationSeries和select请求，输出由各独立后端逐行迭代SelectionRow。
TRUE行是已知选中；UNKNOWN行用于保留无法决定的诊断，消费方必须检查selection。
FALSE行被过滤。只输出目标表达式依赖的真实时间组更新，不伪造裁剪或TTL样本。
本模块仅验证不可变协议，不计算筛选掩码、不读写文件、不改变旧读取或解码。
来源定位是绑定字段与时间组，不宣称保存旧日志的物理行号或逐消息求值序号。
输入仍为完整内存历史；逐行输出不意味着AnalysisRunner的内存预算已经实现。
"""

# 冻结行协议避免消费者修改结果身份。
from dataclasses import dataclass
# 只共享静态模型，不包含筛选数值内核。
from .calculations import CalculationSeries, CalculationDefinition
from .models import SourceRef
from .numeric import ScalarValue
from .types import Truth, QualityFlag as Q
from .validation import require_text
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class SelectionRow:
    """保存一个真实表达式更新时间组的选择结果。

    value保持原dtype、枚举标签、有效性和质量；selection只允许TRUE或UNKNOWN。
    quality汇总原依赖、值及条件原因；binding_identity与source_refs定位当前输入。
    unit保留当前分析值单位；行流不执行隐式单位换算。
    所有字段不可变，没有跨任务状态；UNKNOWN不是已知选中，不能隐式转bool。
    """

    time_ns: int  # 原子更新时间组的精确纳秒时间。
    value: ScalarValue  # 原typed值，未知不填正常零，枚举不输出内部整数编码。
    selection: Truth  # TRUE选中或UNKNOWN诊断，不包含明确FALSE行。
    quality: Q  # 原值、条件与依赖的完整质量原因。
    binding_identity: str  # 当前表达式/选择条件的实际执行身份。
    source_refs: tuple[SourceRef, ...]  # 当前所有依赖的原字段定位。
    unit: str  # 当前分析值单位，和原typed值一起保留。

    def __post_init__(self):
        """验证行类型、时间和当前来源身份，不执行筛选。

        参数: 无；读取冻结字段。
        返回: None。
        异常: TypeError/ValueError/OverflowError为不合法协议。
        """
        # 保持精确int64时间，不接受float或bool冒充坐标。
        require_int64_ns(self.time_ns, 'selection.time_ns')
        # FALSE不属于输出，value即使无效也必须有完整typed质量。
        if not isinstance(self.value, ScalarValue) or self.selection not in (Truth.TRUE, Truth.UNKNOWN) or not isinstance(self.quality, Q):
            raise TypeError('选择行需typed值、TRUE/UNKNOWN及QualityFlag')
        # 身份不可为空；来源引用必须冻结且是完整字段模型。
        require_text(self.binding_identity, 'selection.binding_identity')
        require_text(self.unit, 'selection.unit')
        if not isinstance(self.source_refs, tuple) or any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            raise TypeError('选择行来源需tuple SourceRef')
        # 输出不能隐藏原值原因，UNKNOWN必须保留至少一个质量诊断。
        if self.quality & self.value.quality != self.value.quality or self.selection is Truth.UNKNOWN and self.quality == Q.NONE:
            raise ValueError('选择行质量不能隐藏无效值或UNKNOWN原因')


def require_selection(series, spec):
    """验证选择行流的输入，不把行流当成标量或隐式换单位。

    参数: series为CalculationSeries，spec为operation=select的CalculationDefinition。
    返回: None。
    异常: TypeError为模型错误；ValueError为算子或单位转换请求。
    """
    # 两个后端共享已校验协议，筛选算法仍独立。
    if not isinstance(series, CalculationSeries) or not isinstance(spec, CalculationDefinition):
        raise TypeError('选择行流需CalculationSeries和CalculationDefinition')
    # 此入口保留原值，转换需要先在分析表达式/绑定中明确完成。
    if spec.operation != 'select' or spec.output_unit not in (None, series.unit):
        raise ValueError('选择行流需select且保留输入单位')
