"""集中导出信号分析的模型、消息表达式绑定和标准库参考实现。

调用者可从本入口构造来源、会话与绑定，再执行信号保持、数值转换、受限表达式、
持续条件、边沿事件及指标计算。参考指标包含前值保持积分、样本/时间统计与BOOL时长；
选择行迭代器保留真实更新、UNKNOWN诊断与原类型。内存桥接连接原行、表达式与输出。
窗口入口扩展、合并和裁剪已完成事件，保存原活动关联；start_only固定窗口抑制跨批保持。
顺序核心将已有请求/响应事件配对，区分明确未响应与观测不足，跨批保存等待状态。
消息表达式另用实际记录仓绑定，参数不参与普通保持或TTL。
此文件只重导出实际模块，
不启动分析、不读取文件、不加载CAN组件或NumPy，也不保存全局会话状态。
数组实现须显式导入对应NumPy模块；完整产品配置和执行接口属于上层入口。
"""

# 导出已实现校验的核心模型。
from .models import DatasetSpec, Interval, MemoryRow, SessionSpec, SignalSample, SourceRef, SourceSpec, TimebaseSpec
# 绑定只处理冻结声明，不读取旧来源或执行样本运算。
from .binding import SignalBindings, SignalDefinition, SynchronizationEvidence
from .lookup import LookupTablePlan
# 消息域声明与真实仓证据使用独立身份，不伪造普通信号历史。
from .message_binding import ExpressionParameter, MessageDeclarations, MessageSourceEvidence, MessageBindings
# 参考状态只依赖标准库，数组入口须显式导入state_numpy。
from .state import AtomicUpdateBuffer, SignalSeries, StateValue, TimeGroup, align_reference, common_timeline, iter_time_groups
# 只读静态映射或明确的质量和类型枚举用于结构协议。
from .types import QualityFlag, SignalDType, SourceType, TimeType, Truth
# 数值参考独立标准库，数组入口通过numeric_numpy/normalize_numpy明确加载。
from .numeric import ScalarValue, binary_reference, memory_series_reference, normalize_reference, to_float_reference, unary_reference
# 编译及标量解释仅依赖标准库，不加载NumPy或旧DBC。
from .expression import CompiledExpression, StaticExpression, DerivedDefinition, compile_expression, validate_expression
# 真正参考执行包含三值和原依赖诊断，数组执行另行明确导入。
from .expression_reference import Evaluation, evaluate_memory_reference, evaluate_reference
# 不可变的时序证据、事件及独立参考检测器，不加载NumPy或旧来源。
from .temporal import ConditionSpan, ConditionTick, ConditionTimeline, Event, TemporalRule, timeline_from_spans
# 真实跨批候选/边沿只在显式检测调用持有实例状态。
from .temporal_reference import ReferenceTemporalDetector, detect_reference
# 参考memory桥接完整连接原行/保持/表达式/deadline/事件。
from .temporal_memory_reference import build_timeline_reference, detect_memory_reference
# 指标协议/独立参考仅标准库，数组后端通过对应模块显式导入。
from .calculations import CalculationResult, CalculationSeries, CalculationDefinition
# 独立参考前值保持积分、样本统计及覆盖率策略，不加载旧CAN路径。
from .calculations_reference import compute_reference, select_reference
# 内存计算入口串联原始行、保持值、表达式求值和指标计算。
from .calculations_memory_reference import build_calculation_series_reference, compute_memory_reference, select_memory_reference
# 行流typed输出；此标准库导出不隐式引入NumPy或旧I/O。
from .selection import SelectionRow
# 独立窗口/片段模型与标准库实现，不加载数组后端或旧writer。
from .windows import WindowSpec, Segment
from .windows_reference import build_segments_reference
# 顺序核心消费已有事件和条件证据，配置解析与运行调度由上层负责。
from .sequence import SequenceRule, SequenceTick, SequenceResult
from .sequence_reference import SequenceDetector, pair_sequence
# 完整窗口变化量的模型与标准库参考；数组核仍由对应模块显式导入。
from .window_delta import DeltaSpan, WindowDeltaSpec, WindowDeltaResult
from .window_delta_reference import window_delta_reference
# 迟滞/双向防抖共用有序状态协议，默认参考入口不加载NumPy。
from .stability import StabilitySpec, StabilityDetector
from .start_end import StartEndSpec, StartEndDetector

# 明确当前模型范围，调用者通过chronaxis.core显式选用。
__all__ = ["DatasetSpec", "Interval", "MemoryRow", "SessionSpec", "SignalSample", "SourceRef",
           "SourceSpec", "TimebaseSpec", "QualityFlag", "SignalDType", "SourceType", "TimeType", "Truth",
           "SignalBindings", "SignalDefinition", "SynchronizationEvidence", "SignalSeries", "StateValue", "LookupTablePlan",
           "TimeGroup", "AtomicUpdateBuffer", "align_reference", "common_timeline", "iter_time_groups",
           "ScalarValue", "binary_reference", "memory_series_reference", "normalize_reference", "to_float_reference", "unary_reference",
           "CompiledExpression", "DerivedDefinition", "compile_expression", "Evaluation", "evaluate_reference", "evaluate_memory_reference",
           "ConditionSpan", "ConditionTick", "ConditionTimeline", "Event", "TemporalRule", "timeline_from_spans",
           "ReferenceTemporalDetector", "detect_reference", "build_timeline_reference", "detect_memory_reference",
           "CalculationResult", "CalculationSeries", "CalculationDefinition", "compute_reference", "build_calculation_series_reference", "compute_memory_reference",
           "SelectionRow", "select_reference", "select_memory_reference", "WindowSpec", "Segment", "build_segments_reference",
           "ExpressionParameter", "MessageDeclarations", "MessageSourceEvidence", "MessageBindings", "StaticExpression", "validate_expression",
           "SequenceRule", "SequenceTick", "SequenceResult", "SequenceDetector", "pair_sequence",
           "DeltaSpan", "WindowDeltaSpec", "WindowDeltaResult", "window_delta_reference",
           "StabilitySpec", "StabilityDetector", "StartEndSpec", "StartEndDetector"]
