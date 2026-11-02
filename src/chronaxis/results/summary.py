"""定义按需执行的精简指标行，不要求不存在的完整输入证明。

只保留结果身份、业务数值、单位及完成/质量状态。事件或片段通过parent_id关联，
不逐行重复配置、信号定义、时间对照或贡献；公开结果只接受当前扁平模型。
本模型只校验结果字段，不读取输入或执行指标计算。
"""

from dataclasses import dataclass
import json
from math import isfinite

from ..core.types import QualityFlag as Q
from ..core.validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class SummaryCalculationRow:
    """一条精简指标；未知用None，不能把缺失转换为正常零。"""

    # 固定身份只用于关联本次结果，不代替原始输入哈希或逐条来源。
    sequence: int
    dataset_id: str
    entity_id: str
    session_id: str
    calculation_id: str
    # 算子及父范围给出业务含义；session没有父对象。
    operation: str
    scope: str
    parent_id: str | None
    # 数值与质量必须一起读取，None不等于有效零。
    value: int | float | None
    unit: str
    status: str
    reason: str
    quality: Q

    def __post_init__(self):
        """核对身份、数值类型及状态，不补造来源或时间信息。

        参数: 无。返回: None。异常: TypeError/ValueError为字段或组合错误。
        """
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError('精简指标序号需要非负原生int')
        for name in ('dataset_id', 'entity_id', 'session_id', 'calculation_id'):
            require_identifier(getattr(self, name), 'summary.'+name)
        if self.operation not in ('integral', 'duration', 'min_time', 'max_time', 'time_weighted_mean',
                           'sample_minimum', 'sample_maximum', 'sample_mean', 'legacy_sum'):
            raise ValueError('精简指标不支持该算子')
        if self.scope not in ('session', 'event', 'segment'):
            raise ValueError('精简指标scope无效')
        if self.scope == 'session':
            if self.parent_id is not None:
                raise ValueError('会话指标不能声明父事件或片段')
        else:
            require_text(self.parent_id, 'summary.parent_id')
        if self.value is not None and (type(self.value) not in (int, float)
                or type(self.value) is float and not isfinite(self.value)):
            raise ValueError('精简指标值需要有限数值或None')
        require_text(self.unit, 'summary.unit')
        require_text(self.reason, 'summary.reason')
        if self.status not in ('complete', 'partial', 'indeterminate'):
            raise ValueError('精简指标status无效')
        if self.status == 'indeterminate' and self.value is not None:
            raise ValueError('无法确定的指标不能含可用数值')
        if not isinstance(self.quality, Q):
            raise TypeError('精简指标质量需要QualityFlag')


SUMMARY_FIELDS = ('sequence', 'dataset_id', 'entity_id', 'session_id', 'calculation_id', 'operation',
                  'scope', 'parent_id', 'value', 'unit', 'status', 'reason', 'quality')


@dataclass(frozen=True)
class SummaryCoverageCalculationRow(SummaryCalculationRow):
    """仅明确设置覆盖门槛时补一个判定，不重复输出时长、比例或输入明细。"""

    coverage_status: str

    def __post_init__(self):
        """保留数值政策与覆盖门槛两个不同事实。参数: 无。返回: None。异常: 非法判定。"""
        super().__post_init__()
        if self.coverage_status not in ('sufficient','indeterminate'):
            raise ValueError('覆盖门槛判定无效')


def _require_row_identity(row):
    """核精简事件和配对的公共身份。参数: 冻结行。返回: None。异常: 类型或字段错误。"""
    if type(row.sequence) is not int or row.sequence < 0:
        raise ValueError('精简结果序号需要非负原生int')
    for name in ('dataset_id','entity_id','session_id','rule_id'):
        require_identifier(getattr(row,name),'summary.'+name)
    if not isinstance(row.quality,Q):
        raise TypeError('精简结果质量需要QualityFlag')


@dataclass(frozen=True)
class SummaryEventRow:
    """一条业务事件；开始、确认、结束各有不同含义，不含原帧或逐条来源副本。"""

    sequence: int
    dataset_id: str
    entity_id: str
    session_id: str
    rule_id: str
    event_id: str
    start_ns: int
    confirmed_ns: int
    end_ns: int | None
    status: str
    trigger: str
    quality: Q

    def __post_init__(self):
        """核实际业务端点，不能把未知结束填为零。参数: 无。返回: None。异常: 合同错误。"""
        _require_row_identity(self)
        require_text(self.event_id,'event_id')
        start=require_int64_ns(self.start_ns,'start_ns')
        confirmed=require_int64_ns(self.confirmed_ns,'confirmed_ns')
        if confirmed < start:
            raise ValueError('确认不能早于开始')
        if self.status == 'point':
            if self.end_ns is not None or start != confirmed:
                raise ValueError('点事件没有活动结束时间')
        elif self.status in ('closed','interrupted','truncated','timeout'):
            end=require_int64_ns(self.end_ns,'end_ns')
            if not start < end or confirmed > end:
                raise ValueError('活动实际端点顺序无效')
        else:
            raise ValueError('精简事件状态无效')
        require_text(self.trigger,'trigger')


@dataclass(frozen=True)
class SummarySequenceRow:
    """一条配对结论，只关联既有事件ID并保存所选口径的延迟。"""

    sequence: int
    dataset_id: str
    entity_id: str
    session_id: str
    rule_id: str
    result_id: str
    request_id: str
    response_id: str | None
    decided_ns: int
    delay_ns: int | None
    status: str
    quality: Q

    def __post_init__(self):
        """核配对及未知结果，不逐行重复规则和事件。参数: 无。返回: None。异常: 合同错误。"""
        _require_row_identity(self)
        for name in ('result_id','request_id'):
            require_text(getattr(self,name),name)
        require_int64_ns(self.decided_ns,'decided_ns')
        if self.status == 'matched':
            require_text(self.response_id,'response_id')
            if require_int64_ns(self.delay_ns,'delay_ns') < 0:
                raise ValueError('配对延迟不能为负')
        elif self.status in ('no_response','indeterminate'):
            if self.response_id is not None or self.delay_ns is not None:
                raise ValueError('未匹配结果不能伪造响应和延迟')
            if self.status == 'indeterminate' and self.quality == Q.NONE:
                raise ValueError('未知配对必须说明质量原因')
            if self.status == 'no_response' and self.quality != Q.NONE:
                raise ValueError('缺失观测不能声明确定未响应')
        else:
            raise ValueError('精简配对状态无效')


@dataclass(frozen=True)
class SummarySegmentRow:
    """片段只输出实际边界、状态和父事件ID，不重复请求边界/原事件/来源。"""
    sequence: int
    dataset_id: str
    entity_id: str
    session_id: str
    window_id: str
    segment_id: str
    start_ns: int | None
    end_ns: int | None
    status: str
    parent_event_ids: tuple[str,...]
    quality: Q

    def __post_init__(self):
        """检查实际范围和必需父关联。参数: 无。返回: None。异常: 字段/组合错误。"""
        if type(self.sequence) is not int or self.sequence<0:
            raise ValueError('片段sequence需非负原生int')
        for name in ('dataset_id','entity_id','session_id','window_id'):
            require_identifier(getattr(self,name),name)
        require_text(self.segment_id,'segment_id')
        if not isinstance(self.quality,Q) or type(self.parent_event_ids) is not tuple or not self.parent_event_ids:
            raise TypeError('片段需质量及非空父ID tuple')
        if len(set(self.parent_event_ids))!=len(self.parent_event_ids):
            raise ValueError('片段父ID不能重复')
        for parent in self.parent_event_ids:
            require_text(parent,'parent_event_id')
        if self.status=='empty':
            if self.start_ns is not None or self.end_ns is not None:
                raise ValueError('空片段不能伪造实际范围')
        elif self.status in ('complete','partial'):
            if require_int64_ns(self.start_ns)>=require_int64_ns(self.end_ns):
                raise ValueError('片段需要正实际范围')
        else:
            raise ValueError('片段状态错误')


SUMMARY_EVENT_FIELDS = ('sequence','dataset_id','entity_id','session_id','rule_id','event_id',
    'start_ns','confirmed_ns','end_ns','status','trigger','quality')
SUMMARY_SEQUENCE_FIELDS = ('sequence','dataset_id','entity_id','session_id','rule_id','result_id',
    'request_id','response_id','decided_ns','delay_ns','status','quality')
SUMMARY_MODELS = {SummaryCalculationRow: ('calculations',SUMMARY_FIELDS,7),
    SummaryEventRow: ('events',SUMMARY_EVENT_FIELDS,8), SummarySequenceRow: ('sequences',SUMMARY_SEQUENCE_FIELDS,9)}
SUMMARY_MODELS[SummarySegmentRow]=('segments',('sequence','dataset_id','entity_id','session_id','window_id',
    'segment_id','start_ns','end_ns','status','parent_event_ids','quality'),11)
@dataclass(frozen=True)
class SummaryContributionRow:
    """一条明确请求的逐消息贡献；仅定位计算，不复制原帧或输入值。"""

    sequence: int
    dataset_id: str
    entity_id: str
    session_id: str
    calculation_id: str
    source: str
    original_sequence: int
    evaluation_index: int
    value: float | None
    reason: str
    quality: Q

    def __post_init__(self):
        """核定位及贡献/跳过互斥。参数: 无。返回: None。异常: 类型或字段错误。"""
        for name in ('sequence','original_sequence','evaluation_index'):
            if type(getattr(self,name)) is not int or getattr(self,name)<0:
                raise ValueError('贡献定位需非负原生整数')
        for name in ('dataset_id','entity_id','session_id','calculation_id','source'):
            require_identifier(getattr(self,name),name)
        if not isinstance(self.quality,Q):
            raise TypeError('贡献质量需QualityFlag')
        if self.value is None:
            if self.reason not in ('missing_input','condition_false','evaluation_error','nonfinite_input'):
                raise ValueError('跳过贡献需要明确原因')
        elif type(self.value) is not float or not isfinite(self.value) or self.reason!='contributed':
            raise ValueError('有效贡献需要有限float及contributed状态')


SUMMARY_MODELS[SummaryContributionRow]=('contributions',('sequence','dataset_id','entity_id','session_id',
    'calculation_id','source','original_sequence','evaluation_index','value','reason','quality'),12)
@dataclass(frozen=True)
class SummaryInputRow:
    """按请求保存一次所需输入；字段原值一份，不保存双时间表示或原帧副本。"""
    sequence: int
    dataset_id: str
    entity_id: str
    session_id: str
    source: str
    original_sequence: int
    time_ns: int | None
    record_type: str
    locator: str
    values_json: str
    quality: Q

    def __post_init__(self):
        """核定位与有限JSON标量，拒绝任意嵌套模型。参数: 无。返回: None。异常: 字段/格式错误。"""
        for name in ('sequence','original_sequence'):
            if type(getattr(self,name)) is not int or getattr(self,name)<0:raise ValueError('追溯序号需非负int')
        for name in ('dataset_id','entity_id','session_id','source'):require_identifier(getattr(self,name),name)
        if self.time_ns is not None:require_int64_ns(self.time_ns)
        if self.record_type not in ('decoded_message','signal_sample','signal_clock') or not isinstance(self.quality,Q):
            raise ValueError('追溯类型/质量无效')
        require_text(self.locator,'trace.locator')
        if type(self.values_json) is not str:raise TypeError('追溯值需JSON文本')
        values=json.loads(self.values_json)
        if type(values) is not dict:raise ValueError('追溯值需字段对象')
        for name,value in values.items():
            require_text(name,'trace.field')
            if type(value) is dict:
                if set(value)!= {'nonfinite'} or value['nonfinite'] not in ('nan','inf','-inf'):
                    raise ValueError('追溯只允许明确非有限值标签')
            elif value is not None and (type(value) not in (str,int,float,bool)
                    or type(value) is float and not isfinite(value)):
                raise ValueError('追溯字段需有限标量或明确非有限标签')


SUMMARY_MODELS[SummaryInputRow]=('input_trace',('sequence','dataset_id','entity_id','session_id',
    'source','original_sequence','time_ns','record_type','locator','values_json','quality'),13)
@dataclass(frozen=True)
class SummarySelectionRow:
    """一条真实更新的选择结果；保业务值及三值选择，不重复输入证明。"""
    sequence: int
    dataset_id: str
    entity_id: str
    session_id: str
    calculation_id: str
    scope: str
    parent_id: str | None
    time_ns: int
    value: int | float | bool | str | None
    dtype: str
    unit: str
    valid: bool
    selection: str
    quality: Q

    def __post_init__(self):
        """核选择行身份和值类型。参数: 无。返回: None。异常: 类型/结构错误。"""
        if type(self.sequence) is not int or self.sequence<0:raise ValueError('选择序号需要非负int')
        for name in ('dataset_id','entity_id','session_id','calculation_id'):require_identifier(getattr(self,name),name)
        if self.scope not in ('session','event','segment'):raise ValueError('选择范围类型无效')
        if self.scope=='session':
            if self.parent_id is not None:raise ValueError('会话选择不能声明父对象')
        else:require_text(self.parent_id,'selection.parent_id')
        require_int64_ns(self.time_ns);require_text(self.unit,'selection.unit')
        kinds={'float64':float,'int64':int,'uint64':int,'bool':bool,'enum':str}
        if self.dtype not in kinds or type(self.valid) is not bool or not isinstance(self.quality,Q):
            raise TypeError('选择类型/有效性/质量错误')
        if self.selection not in ('true','unknown') or self.selection=='unknown' and self.quality==Q.NONE:
            raise ValueError('选择仅支持TRUE或有质量原因的UNKNOWN')
        if self.valid:
            if type(self.value) is not kinds[self.dtype] or type(self.value) is float and not isfinite(self.value):
                raise ValueError('选择有效值与dtype不符')
            if self.dtype=='int64' and not -(1<<63)<=self.value<(1<<63) or self.dtype=='uint64' and not 0<=self.value<(1<<64):
                raise ValueError('选择整数超出dtype')
        elif self.value is not None or self.quality==Q.NONE:
            raise ValueError('选择无效值必须为空并保留质量原因')


SUMMARY_MODELS[SummarySelectionRow]=('selections',('sequence','dataset_id','entity_id','session_id','calculation_id',
    'scope','parent_id','time_ns','value','dtype','unit','valid','selection','quality'),14)
SUMMARY_COLUMNS = {table: names for table,names,_ in SUMMARY_MODELS.values()}
SUMMARY_MODELS[SummaryCoverageCalculationRow] = ('calculations',SUMMARY_FIELDS+('coverage_status',),10)


def summary_fields(row):
    """转换必要平坦字段，CSV和JSONL共用，不附另一份row_json。

    参数: SummaryCalculationRow。返回: 固定字段dict。异常: TypeError为错误根类型。
    """
    try:
        if type(row) not in SUMMARY_MODELS:
            raise TypeError('精简字段需要SummaryCalculationRow')
        result = {name: getattr(row, name) for name in SUMMARY_MODELS[type(row)][1]}
        result['quality'] = int(row.quality)
        return result
    finally:
        row = None
