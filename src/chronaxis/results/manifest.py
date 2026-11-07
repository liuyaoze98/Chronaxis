"""定义结果清单中的运行事实和已发布输出身份。

输入为执行侧明确提供的时间/身份/后端，输出为冻结元数据模型。
不会推断CAN、DBC或同步关系；软件/Python版本、资源统计和输出由结果层补齐。
调用者须提供真实信息，模型校验不能证明真实日志已经验收。
"""

# 清单字段冻结；带时区时间及int64会话边界与核心协议一致。
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from math import isfinite, isnan
from pathlib import Path
from sys import getsizeof
from .._version import software_version
from ..core.validation import require_text, require_identifier
from ..core.models import Interval
from ..core.binding import SignalDefinition
from ..core.types import QualityFlag
from .binding_metadata import PresetBindingMetadata, PresetRoleMetadata
from .can_metadata import CANSourceMetadata, CANUnitCheck, CANFrameFormatNotice
from .text_can_metadata import TextCANSourceMetadata
from .threshold_metadata import ThresholdDurationMetadata,SummaryThresholdDuration
from .input_diagnostics import InputDiagnostic
from .analysis_outcome import AnalysisOutcome, RuleOutcome
from ..legacy.records import LegacyCANField


@dataclass(frozen=True)
class RunMetadata:
    """保存运行身份、实际后端、时间解释、会话边界与兼容限制。

    started_at须含时区；session_boundaries为(session_id,start_ns,end_ns)tuple。
    映射/DBC/依赖事实未涉及时使用空tuple，不能把空值当成验证通过。
    字段只保存明确输入；新层资源/输出/结束时间由实际执行结果补充。
    signal_bindings保本次实际定义，preset_bindings保最终角色；可选语义仍是声明，
    角色契约通过也不表示物理事实已测量。can_sources保存同次真实CAN读取/暂存/
    单位核对的结构化事实；text_can_sources保存新文本解析/DBC/观测事实。
    未提供的详细事实不作为当前运行的验证证明。
    """

    run_id: str
    input_identity: str | None
    plan_hash: str
    backend: str
    config_version: int
    source_time_interpretation: str
    session_boundaries: tuple[tuple[str, int, int], ...]
    started_at: str
    mapping_hashes: tuple[str, ...] = ()
    dbc_hashes: tuple[str, ...] = ()
    parsing_policy: str = 'decoded-results'
    worker_config: str = 'single-thread'
    dependency_versions: tuple[tuple[str, str], ...] = ()
    limitations: tuple[str, ...] = ()
    software_version: str = software_version()  # 默认记录当前源码/构建包版本；显式历史身份保持调用值。
    device_label: str = 'pending'
    signal_bindings: tuple[SignalDefinition, ...] = ()  # 本次实际完整定义，不含样本或输入行。
    preset_bindings: tuple[PresetBindingMetadata, ...] = ()  # 原预设版本及最终角色。
    can_sources: tuple[CANSourceMetadata, ...] = ()  # 同次实际CAN read事实，不含样本或伪造DBC哈希。
    session_ids: tuple[str, ...] = ()  # 无时间请求仍明确会话身份，绝不伪造边界。
    text_can_sources: tuple[TextCANSourceMetadata,...] = ()  # 新文本入口同次DBC/解析/观测事实。
    threshold_durations: tuple[SummaryThresholdDuration, ...] = ()  # 仅显式阈值预设的同次状态累计。
    detailed_diagnostics: bool = False  # 按显式请求输出额外质量明细和摘要。
    retain_work: bool = False  # 显式现场留存请求，不默认保留工作文件。
    input_diagnostics: tuple[InputDiagnostic,...] = ()  # 仅按请求记录同次所需输入范围。
    trace_requested: bool = False  # input_trace表独立于贡献和哈希。
    integrity_diagnostics: bool = False  # 摘要独立于逐条追溯。
    frame_format_notices: tuple[tuple[str, CANFrameFormatNotice], ...] = ()  # 同次已核差异始终提示，独立于可选诊断。

    analysis_outcome: AnalysisOutcome | None = None  # 同次推进的轻量业务结果概况，非逐条追溯。
    aggregation_definitions: tuple = ()  # 本次组级总体、单位及排除政策，每项只登记一次。

    def __post_init__(self) -> None:
        """验证清单文本与明确会话范围，不访问外部输入。

        参数: 无。返回: None。异常: TypeError/ValueError为结构或事实格式错误。
        """
        if self.analysis_outcome is not None and type(self.analysis_outcome) is not AnalysisOutcome:
            raise TypeError('分析结果概况需要AnalysisOutcome或None')
        if self.aggregation_definitions:
            from ..planning.aggregations import AggregationPlan
            if type(self.aggregation_definitions) is not tuple or any(type(a) is not AggregationPlan for a in self.aggregation_definitions):
                raise TypeError('聚合清单需要已冻结的聚合定义')
        # 必填文本不能用空字符串表示已经取得的运行身份。
        for name in ('run_id', 'plan_hash', 'source_time_interpretation',
                     'parsing_policy', 'worker_config', 'software_version', 'device_label'):
            require_text(getattr(self, name), name)
        if self.backend not in ('reference', 'numpy') or type(self.config_version) is not int or self.config_version != 4:
            raise ValueError('结果清单需实际reference/numpy及配置版本4')
        if (self.input_identity is not None):
            require_text(self.input_identity, 'input_identity')
        if type(self.detailed_diagnostics) is not bool or type(self.retain_work) is not bool:
            raise TypeError('诊断/现场保留需要bool')
        if type(self.trace_requested) is not bool or type(self.integrity_diagnostics) is not bool:
            raise TypeError('输入诊断开关需要bool')
        if (type(self.input_diagnostics) is not tuple
                or any(type(item) is not InputDiagnostic for item in self.input_diagnostics)):
            raise TypeError('输入诊断需InputDiagnostic tuple')
        if self.input_diagnostics and not (self.trace_requested or self.integrity_diagnostics):
            raise ValueError('未请求不能附输入诊断')
        if (type(self.frame_format_notices) is not tuple or any(type(pair) is not tuple or len(pair) != 2
                or type(pair[1]) is not CANFrameFormatNotice for pair in self.frame_format_notices)):
            raise TypeError('帧型提示需要来源与CANFrameFormatNotice的tuple')
        for source, notice in self.frame_format_notices:
            require_identifier(source, 'frame_format.source')
        if len({(source, notice.alias) for source, notice in self.frame_format_notices}) != len(self.frame_format_notices):
            raise ValueError('同来源信号的帧型提示不能重复')
        require_text(self.started_at, 'started_at')
        if datetime.fromisoformat(self.started_at).utcoffset() is None:
            raise ValueError('started_at必须带时区')
        # 会话边界只验证半开范围，空会话允许start=end；不自动联合或平移。
        if type(self.session_boundaries) is not tuple:
            raise TypeError('session_boundaries需tuple')
        for boundary in self.session_boundaries:
            if type(boundary) is not tuple or len(boundary) != 3:
                raise TypeError('会话边界需(session_id,start,end)')
            require_identifier(boundary[0], 'session_id')
            # 清单直接JSON序列化，固定原生整数，bool及NumPy容器不能偷偷换类型。
            if type(boundary[1]) is not int or type(boundary[2]) is not int:
                raise TypeError('清单会话边界需原生int纳秒')
            Interval(boundary[1], boundary[2])
        for values in (self.mapping_hashes, self.dbc_hashes, self.limitations):
            if type(values) is not tuple or any(type(value) is not str or not value for value in values):
                raise TypeError('清单映射/限制需要非空文本tuple')
        if type(self.dependency_versions) is not tuple or any(type(item) is not tuple or len(item) != 2
                or any(type(value) is not str or not value for value in item) for item in self.dependency_versions):
            raise TypeError('依赖版本需(name,version)tuple')

        # 新快照只接不可变定义和有限角色记录，拒绝自由字典或原样本模型。
        if (type(self.signal_bindings) is not tuple
                or any(type(item) is not SignalDefinition for item in self.signal_bindings)
                or type(self.preset_bindings) is not tuple
                or any(type(item) is not PresetBindingMetadata for item in self.preset_bindings)):
            raise TypeError('运行绑定清单需SignalDefinition及PresetBindingMetadata tuple')
        names = {item.name for item in self.signal_bindings}
        if len(names) != len(self.signal_bindings):
            raise ValueError('运行绑定清单不能重复别名')
        if len({item.preset_id for item in self.preset_bindings}) != len(self.preset_bindings):
            raise ValueError('运行绑定清单不能重复预设ID')
        if any(role.alias not in names for preset in self.preset_bindings for role in preset.roles):
            raise ValueError('预设最终角色必须引用本清单实际信号别名')
        if (type(self.threshold_durations) is not tuple
                or any(type(item) is not (SummaryThresholdDuration)
                       for item in self.threshold_durations)):
            raise TypeError('阈值汇总需ThresholdDurationMetadata tuple')
        preset_ids = {item.preset_id for item in self.preset_bindings if item.preset_type == 'threshold_excursion'}
        if (len({item.preset_id for item in self.threshold_durations}) != len(self.threshold_durations)
                or any((item.rule_id != item.preset_id + '_activity')
                       for item in self.threshold_durations)):
            raise ValueError('阈值汇总必须对应本次预设及生成规则，不能重复')
        if type(self.session_ids) is not tuple or len(set(self.session_ids)) != len(self.session_ids):
            raise TypeError('独立会话身份需要无重复tuple')
        for session_id in self.session_ids:
            require_identifier(session_id, 'session_id')
        # CAN仅接受登记冻结模型；会话、来源和单位事实必须关联本次原绑定，不能借旧任务别名。
        if type(self.text_can_sources) is not tuple or any(type(item) is not TextCANSourceMetadata for item in self.text_can_sources):
            raise TypeError('文本CAN清单需要TextCANSourceMetadata tuple')
        if len({item.source for item in self.text_can_sources})!=len(self.text_can_sources):
            raise ValueError('文本CAN清单来源重复')
        for source in self.text_can_sources:
            if source.session_id not in ({b[0] for b in self.session_boundaries}|set(self.session_ids)):
                raise ValueError('文本CAN清单会话错误')
            expected={s.name:s.input_unit for s in self.signal_bindings if s.source==source.source}
            if {c.alias:c.input_unit for c in source.unit_checks}!=expected or len(source.unit_checks)!=len(expected):
                raise ValueError('文本CAN单位清单必须覆盖实际绑定')
        if type(self.can_sources) is not tuple or any(type(item) is not CANSourceMetadata for item in self.can_sources):
            raise TypeError('CAN运行清单需要CANSourceMetadata tuple')
        if len({item.source for item in self.can_sources}) != len(self.can_sources):
            raise ValueError('CAN运行清单来源重复')
        # 空默认不为旧运行再构造来源/单位索引，实际CAN存在时才核本次对应关系。
        if self.can_sources:
            sessions = {boundary[0] for boundary in self.session_boundaries} | set(self.session_ids)
            definitions = {item.name: item for item in self.signal_bindings}
            for source in self.can_sources:
                if source.session_id not in sessions:
                    raise ValueError('CAN运行清单会话不属于本次session_boundaries')
                expected = {name for name, definition in definitions.items() if definition.source == source.source}
                if {check.alias for check in source.unit_checks} != expected:
                    raise ValueError('CAN单位清单必须恰好覆盖同来源本次实际绑定别名')
                for check in source.unit_checks:
                    definition = definitions.get(check.alias)
                    if (definition is None or definition.source != source.source
                            or definition.input_unit != check.input_unit):
                        raise ValueError('CAN单位核对别名/来源/input_unit与本次原声明不同')
                    if source.decode_scope == 'requested':
                        # requested可服务普通/混合/导出计划；只核实际需求，不由结果模式猜范围。
                        # 仍要求原完整CAN定位和通道吻合，固定ID必须覆盖每个实际所需字段。
                        # 实际需要CAN字段才导入来源包，保持纯预算/旧默认元数据的轻量导入。
                        from ..sources.can_spec import can_field_from_key
                        selected_field = can_field_from_key(definition.field)
                        if (selected_field.channel != source.channel
                                or selected_field.frame_id not in source.decode_frame_ids):
                            raise ValueError('requested固定解码集合须覆盖本次实际绑定字段及同来源通道')
                for notice in source.frame_format_notices:
                    # 提示必须满足本次信号定位；省略的帧型允许由同次实际读取补齐。
                    from ..sources.can_spec import can_field_from_key
                    definition = definitions.get(notice.alias)
                    field = None if definition is None else can_field_from_key(definition.field)
                    if (definition is None or definition.source != source.source
                            or (field.channel,field.frame_id,field.signal)!=(notice.channel,notice.frame_id,notice.signal)
                            or field.is_extended is not None and field.is_extended!=notice.is_extended
                            or field.is_fd is not None and field.is_fd!=notice.requested_is_fd):
                        raise ValueError('CAN帧型提示必须对应本次原信号完整定位')

    def estimated_bytes(self) -> int:
        """在asdict/JSON复制前估算元数据与其临时对象开销。

        参数: 无。返回: 保守bytes估算。异常: 无，类型已经校验。
        """
        # 文本/tuple结构只读遍历，转换副本成本以16倍和固定余量保守覆盖。
        # 空默认新字段不增加旧金额；非空定义/角色/CAN事实在asdict复制前递归覆盖。
        return 8192 + 16 * sum(_metadata_size(getattr(self, field.name)) + 256 for field in fields(self)
            if field.name not in ('signal_bindings', 'preset_bindings', 'can_sources', 'session_ids','text_can_sources','threshold_durations','detailed_diagnostics','retain_work','input_diagnostics','trace_requested','integrity_diagnostics','frame_format_notices','analysis_outcome','aggregation_definitions')
            or getattr(self, field.name))

    def to_dict(self) -> dict:
        """返回独立JSON兼容元数据，调用侧必须先预留estimated_bytes。

        参数: 无。
        返回: 独立JSON兼容dict。detailed_diagnostics=False时仅输出运行身份、
            后端、配置版本、时间解释、运行设置及适用的边界/限制/请求诊断；
            signal_bindings、preset_bindings、can_sources等即使非空也不输出。
            detailed_diagnostics=True才展开详细模型；空的可选明细继续按分支省略。
            模型持有字段不等于默认序列化一定包含该键。
        异常: 无预期异常；调用方须在复制前承担estimated_bytes预算。
        """
        if (not self.detailed_diagnostics):
            # 从生成处只复制必要运行信息，不先展开完整绑定/来源后再隐藏。
            result = {name: getattr(self, name) for name in ('run_id', 'plan_hash', 'backend',
                'config_version', 'started_at', 'device_label', 'software_version',
                'source_time_interpretation', 'parsing_policy', 'worker_config', 'retain_work', 'detailed_diagnostics')}
            for name in ('input_identity', 'session_boundaries', 'session_ids', 'limitations', 'dependency_versions'):
                if getattr(self, name):
                    result[name] = getattr(self, name)
            if self.threshold_durations:
                result['threshold_durations']=tuple(item.to_dict() for item in self.threshold_durations)
            if self.trace_requested or self.integrity_diagnostics:
                result['diagnostics']={'trace':self.trace_requested,'integrity':self.integrity_diagnostics}
                result['input_diagnostics']=[item.to_dict() for item in self.input_diagnostics]
            if self.frame_format_notices:
                result['frame_format_notices']=[dict(source=source, **asdict(notice)) for source, notice in self.frame_format_notices]
            if self.analysis_outcome is not None:
                result['analysis_outcome']=self.analysis_outcome.to_dict()
            if self.aggregation_definitions:
                result['aggregation_definitions']=[asdict(a) for a in self.aggregation_definitions]
            return result
        result = asdict(self)
        if not self.aggregation_definitions:
            result.pop('aggregation_definitions')
        if self.analysis_outcome is None:
            result.pop('analysis_outcome')
        else:
            result['analysis_outcome']=self.analysis_outcome.to_dict()
        if self.frame_format_notices:
            result['frame_format_notices']=[dict(source=source, **asdict(notice)) for source, notice in self.frame_format_notices]
        else:
            result.pop('frame_format_notices')
        if self.input_identity is None:
            result.pop('input_identity')  # 未计算的全量输入摘要不以占位文字冒充。
        if self.threshold_durations:
            result['threshold_durations'] = tuple(item.to_dict() for item in self.threshold_durations)
        else:
            result.pop('threshold_durations')
        if not self.text_can_sources:
            result.pop('text_can_sources')
        if not self.session_ids:
            result.pop('session_ids')
        # 只有实际存在的详细事实才展开对应字段。
        if self.signal_bindings:
            for row, definition in zip(result['signal_bindings'], self.signal_bindings):
                # dtype转明确文本；无效值里的非有限诊断用既有显式标签，不输出裸NaN。
                row['dtype'] = definition.dtype.value
                row['invalid_values'] = tuple({'diagnostic_float': 'nan' if isnan(value) else
                    'inf' if value > 0 else '-inf'} if type(value) is float and not isfinite(value) else value
                    for value in definition.invalid_values)
                row['semantic_status'] = 'not_provided' if definition.semantic_id is None else 'declared'
                # 原基础策略拒绝全部非零质量位；声明名称不代表物理语义已核实。
                row['quality_policy'] = {'mode': 'reject_nonzero',
                    'forbidden_flags': tuple(flag.name for flag in QualityFlag),
                    'forbidden_mask': sum(int(flag) for flag in QualityFlag)}
        else:
            result.pop('signal_bindings')
        if not self.preset_bindings:
            result.pop('preset_bindings')
        if not self.can_sources:
            result.pop('can_sources')
        else:
            # 仅实际差异增加提示；原无差异CAN清单的键和值完全保持。
            for row, source in zip(result['can_sources'], self.can_sources):
                if not source.frame_format_notices:
                    row.pop('frame_format_notices')
                if source.input_check == 'full' and source.check_policy_version is None:
                    for key in ('input_check', 'time_scope', 'check_policy_version', 'retained_record_count',
                                'full_check_count', 'selected_first_ns', 'selected_last_ns'):
                        row.pop(key)
                if source.decode_scope == 'all':
                    # 新默认字段既不改变旧JSON，也不增加旧估算费用。
                    row.pop('decode_scope')
                    row.pop('decode_frame_ids')
                if source.decoded_values_policy == 'all_values-v1':
                    # 兼容旧all与旧requested全字段事实，默认值不改变清单键或费用。
                    row.pop('decoded_values_policy')
        return result


def _metadata_size(value) -> int:
    """统计已校验元数据树的基础对象大小，不产生转换树。

    参数: value为元数据字段。返回: 基础bytes估算。异常: 无。
    """
    # 仅遍历已验证的有限模型，不泛化为raw_config或任意dataclass序列化。
    from ..planning.aggregations import AggregationPlan
    if type(value) is AggregationPlan:
        return getsizeof(value)+sum(_metadata_size(getattr(value,key)) for key in value.__dataclass_fields__)
    if type(value) in (SignalDefinition, PresetBindingMetadata, PresetRoleMetadata,
                      CANSourceMetadata, CANUnitCheck, CANFrameFormatNotice,TextCANSourceMetadata,InputDiagnostic,
                      AnalysisOutcome, RuleOutcome):
        return getsizeof(value) + sum(_metadata_size(getattr(value, field.name)) + 32 for field in fields(value)
            if type(value) is not CANSourceMetadata or (
                (field.name != 'frame_format_notices' or value.frame_format_notices)
                and (field.name not in ('decode_scope', 'decode_frame_ids') or value.decode_scope != 'all')
                and (field.name != 'decoded_values_policy' or value.decoded_values_policy != 'all_values-v1')
                and (field.name not in ('input_check', 'time_scope', 'check_policy_version',
                    'retained_record_count', 'full_check_count', 'selected_first_ns', 'selected_last_ns')
                    or value.check_policy_version is not None or value.input_check != 'full')))

    if type(value) is tuple:
        return getsizeof(value) + sum(_metadata_size(item) + 32 for item in value)
    return getsizeof(value)


@dataclass(frozen=True)
class OutputManifest:
    """保存成功发布目录、清单和固定白名单表行数；legacy只在启用时出现。"""

    run_id: str
    output_dir: Path
    manifest_path: Path
    output_files: tuple[Path, ...]
    row_counts: tuple[tuple[str, int], ...]
    status: str = 'completed'

    def __post_init__(self) -> None:
        """校验返回清单身份，不凭构造调用证明目录已发布。

        参数: 无。返回: None。异常: TypeError/ValueError为字段错误。
        """
        require_text(self.run_id, 'run_id')
        if self.status != 'completed' or not isinstance(self.output_dir, Path) or not isinstance(self.manifest_path, Path):
            raise ValueError('OutputManifest需completed和Path')
        if type(self.output_files) is not tuple or any(not isinstance(path, Path) for path in self.output_files):
            raise TypeError('输出路径需tuple Path')
        if type(self.row_counts) is not tuple or any(type(item) is not tuple or len(item) != 2
                or item[0] not in ('events', 'segments', 'calculations', 'message_calculations', 'legacy_contributions', 'sequences','contributions','input_trace','selections','aggregations')
                or type(item[1]) is not int or item[1] < 0 for item in self.row_counts):
            raise ValueError('输出行数需固定表及非负原生int')


@dataclass(frozen=True)
class ExportManifest:
    """独立信号或原帧导出的实际输出路径；调用者无需猜测时间文件名。"""

    output_dir: Path
    manifest_path: Path
    output_files: tuple[Path, ...]

    def __post_init__(self):
        """核对实际路径类型和所属目录。参数: 无。返回: None。异常: 类型或路径错，不访问文件。"""
        if not isinstance(self.output_dir, Path) or not isinstance(self.manifest_path, Path):
            raise TypeError('导出返回目录和清单必须为Path')
        if type(self.output_files) is not tuple or any(not isinstance(p, Path) for p in self.output_files):
            raise TypeError('导出文件必须为Path tuple')
        if any(p.parent != self.output_dir for p in (self.manifest_path, *self.output_files)):
            raise ValueError('导出返回路径必须属于本次输出根')
