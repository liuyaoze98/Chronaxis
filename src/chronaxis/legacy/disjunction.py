"""声明按本条原解码方向值分正负桶，并保存不经转换的选择追溯。

LegacyDisjunction给出已绑定别名、positive/negative桶及固定raw_decoded-v1策略。
运行层须核同一完整消息定位，从当前decoded字典直接取方向原值，不能施加
SignalDefinition的scale、offset、direction_factor或TTL，也不能补前一次值。
原生True按正值、False按零；缺字段、非有限值和未选桶的跳过由运行层决定，
本模块不执行分类、表达式、累计或数值转换。

LegacyDisjunctionTrace保存冻结选择器、原field定位、原生方向值和SourceRef。
None明确表示方向字段缺失；NaN/Inf保留原诊断，不改成零或字符串。模型只核
结构，不声称来自真实消息、文件EOF或旧ChrgInfo整条调用链。配置和返回追溯
由调用方拥有；本模块不创建预算、I/O、缓存或NumPy依赖。
"""

# 两端共享冻结选择器和追溯，不在计划、结果和运行层各造一套可变字典。
from dataclasses import dataclass

from ..core.models import SourceRef
from ..core.validation import require_identifier, require_text


@dataclass(frozen=True)
class LegacyDisjunction:
    """选择同条消息的原数值方向桶，不修改表达式贡献的正负号。

    signal是分析别名，原字段和完整消息定位仍由当前绑定解析；bucket只允许
    positive/negative。该声明不自行拆分指标，也不证明方向在表达式依赖中。
    """

    signal: str  # 已绑定简单别名，可不出现在表达式中。
    bucket: str  # positive或negative，各指标独立累计。
    value_policy: str = 'raw_decoded-v1'  # 只看原decoded值，不施转换或保持。

    def __post_init__(self) -> None:
        """校验安全别名和固定桶/取值策略，不解析来源或输入值。

        参数: 无，读取三个冻结字段。返回: None，保原生文本原样。
        异常: TypeError为非原生文本；ValueError为别名、桶或策略不支持。
        """
        # 不按truthiness或str隐式转换选桶，避免配置拼错后悄悄进入另一种策略。
        if type(self.signal) is not str or type(self.bucket) is not str or type(self.value_policy) is not str:
            raise TypeError('disjunction别名、桶和value_policy需要原生str')
        require_identifier(self.signal, 'disjunction.signal')
        if self.bucket not in ('positive', 'negative'):
            raise ValueError('disjunction.bucket仅支持positive或negative')
        if self.value_policy != 'raw_decoded-v1':
            raise ValueError('disjunction.value_policy仅支持raw_decoded-v1')


@dataclass(frozen=True)
class LegacyDisjunctionTrace:
    """保存本次方向的原定位和值，结构冻结但不假造真实读取证明。

    raw_value保int/float/bool原类型，None只表示明确缺字段；非有限float不在
    模型层改写或拒绝。source_ref原对象保持，实际CAN逐序身份由运行/结果层核。
    """

    selection: LegacyDisjunction  # 实际指标使用的同一选择器。
    field: str  # 原SignalDefinition.field，CAN路径为规范六项定位。
    raw_value: int | float | bool | None  # 未归一化方向值；None为缺失。
    source_ref: SourceRef  # 同条原消息的真实来源引用。

    def __post_init__(self) -> None:
        """核选择器、原字段、原生值及引用一致性，不作数值强制转换。

        参数: 无，读取冻结追溯字段。返回: None；保NaN/Inf、负零和原bool。
        异常: TypeError为非模型/原生数值；ValueError为原字段与引用不一致。
        """
        # 选择器必须已由共享模型校验，字段全文保留，不从别名反猜原字典键。
        if type(self.selection) is not LegacyDisjunction or type(self.field) is not str:
            raise TypeError('disjunction追溯需要LegacyDisjunction及原生field文本')
        require_text(self.field, 'disjunction.field')
        # None不代表零或无效浮点；数值原类型限定，拒绝str、enum和NumPy scalar。
        if self.raw_value is not None and type(self.raw_value) not in (int, float, bool):
            raise TypeError('disjunction原值需要原生int/float/bool或明确缺失None')
        if not isinstance(self.source_ref, SourceRef):
            raise TypeError('disjunction追溯需要SourceRef')
        if self.source_ref.field != self.field:
            raise ValueError('disjunction原field与来源引用不一致')
