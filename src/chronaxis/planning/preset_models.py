"""保存预设v1的公开不可变声明、角色契约及可序列化计划片段。

输入JSON参数及类型化信号引用，输出冻结spec、角色追溯和公共节点声明。
先校验spec结构并深复制参数，再由外部构建器检查工程契约；本模块不运行I/O或分析。
声明模型独立于构建器/AnalysisPlan，两个入口共用真实类型，避免循环导入及不可解析注解。
候选语义名仅是领域预设v1本地协议；不建立核心目录，不伪造时钟/来源/工程结论。
序列化产生独立JSON副本，节点仍须由正常公共编译器检查依赖与单位。
"""

# 不可变模型及结构校验不依赖预设算法或公开计划。
from collections.abc import Mapping
from dataclasses import dataclass
from ..core.binding import SignalDefinition
from ..core.expression import DerivedDefinition
from ..core.types import SignalDType as D
from ..core.windows import WindowSpec
from .checks import (PlanValidationError, choice_at, json_value, metadata_at,
                     object_at, require_json_value, text_at)
from .sequences import SequencePlan


@dataclass(frozen=True)
class RoleContract:
    """公开本预设版本的角色类型、单位、语义候选、方向与位置要求。

    有效期必须由SignalDefinition明确提供且正；基础质量使用其固定九位禁用策略。
    semantic_id/version仅用于自动查找，显式绑定仍逐字段检查，不能只凭版本宣称符合。
    """

    role: str  # mode/current/voltage/alarm；不注册全量领域名称。
    dtypes: tuple[D, ...]  # 转换后的可接受逻辑类型。
    unit: str  # 精确目标单位，关系须verified。
    semantic_id: str  # 本模块v1候选标识，大小写敏感。
    sign_convention: str | None = None  # 需要时为明确转换后方向。
    measurement_location: str | None = None  # 需要时为明确测量位置。
    version: str = '1'  # 本公开候选契约版本。
    forbidden_quality: int = 511  # 核心已定义九位基础质量全部禁止。


# 每个角色仅声明预设实际需要的内容；无通用汽车/电池本体。
CHARGE_ROLES = (
    RoleContract('mode', (D.INT64, D.UINT64), '1', 'battery.mode'),
    RoleContract('current', (D.FLOAT64,), 'A', 'battery.current', 'positive_is_charge', 'pack_terminal'),
    RoleContract('voltage', (D.FLOAT64,), 'V', 'battery.voltage', measurement_location='pack_terminal'),
)
FAULT_ROLES = (RoleContract('alarm', (D.BOOL,), '1', 'fault.alarm'),)
COMMAND_ROLES = (RoleContract('request', (D.BOOL,), '1', 'command.request'),
                 RoleContract('response', (D.BOOL,), '1', 'command.response'))


@dataclass(frozen=True)
class PresetSpec:
    """冻结预设ID、preset_type/version、角色别名及工程参数的独立JSON快照。

    id只用简单标识；role_bindings值只引用当前计划简单别名，不能写领域属性路径。
    parameters不保留调用者可变对象，实际preset_type参数在build_preset中统一校验。
    """

    id: str  # 生成节点的明确前缀，不自动加后缀解冲突。
    preset_type: str  # charge_session、fault_context、command_response或threshold_excursion。
    version: str  # 当前仅'1'。
    role_bindings: Mapping  # 只读角色→简单别名。
    parameters: Mapping  # 深冻结JSON工程声明。

    def __post_init__(self):
        """检查公开spec结构并复制冻结，不运行数据计算。

        参数: 无；读取构造字段。
        返回: None，字段保存独立只读副本。
        异常: PlanValidationError为名称、版本、JSON结构或角色别名错误。
        """
        # 公共入口与JSON路径使用同一严格名称/版本检查。
        text_at(self.id, '$.preset.name', identifier=True)
        choice_at(self.preset_type, ('charge_session', 'fault_context', 'command_response', 'threshold_excursion'), '$.preset.preset_type')
        choice_at(self.version, ('1',), '$.preset.version')
        # Mapping只用于冻结后再构建；不接受数组或任意对象作声明。
        if not isinstance(self.role_bindings, Mapping) or not isinstance(self.parameters, Mapping):
            raise PlanValidationError('$.preset', 'role_bindings/parameters必须为对象')
        roles = dict(self.role_bindings)
        parameters = dict(self.parameters) if type(self.parameters) is dict else json_value(self.parameters)
        require_json_value(roles, '$.preset.role_bindings')
        require_json_value(parameters, '$.preset.parameters')
        for role, alias in roles.items():
            text_at(role, '$.preset.role_bindings', identifier=True)
            text_at(alias, '$.preset.role_bindings.' + role, identifier=True)
        object.__setattr__(self, 'role_bindings', metadata_at(roles, '$.preset.role_bindings'))
        object.__setattr__(self, 'parameters', metadata_at(parameters, '$.preset.parameters'))

    @classmethod
    def from_dict(cls, value):
        """从当前配置的预设对象构造公开不可变声明。

        参数: value为原生JSON对象，必填name/preset_type/parameters，可选version/role_bindings。
        返回: PresetSpec，role_bindings缺省为空。
        异常: PlanValidationError为未知键、缺项或构造协议错误。
        """
        # 自由元数据不能借预设参数绕过契约。
        raw = object_at(value, '$.preset', ('name', 'preset_type', 'parameters'), ('version', 'role_bindings'))
        return cls(raw['name'], raw['preset_type'], raw.get('version', '1'), raw.get('role_bindings', {}), raw['parameters'])


@dataclass(frozen=True)
class RoleBinding:
    """保存已通过字段契约的角色及其原信号定义，供调用者追溯转换与来源。

    自动/显式查找方式不同，但definition保留完整来源、单位、方向转换和质量身份。
    不保存样本值，也不伪称元数据的物理事实已由系统测量核实。
    """

    contract: RoleContract  # 本次实际校验的v1角色。
    definition: SignalDefinition  # 原不可变完整绑定，包含转换证据。
    resolution: str  # explicit或semantic_unique。


@dataclass(frozen=True)
class PresetRule:
    """保存生成的持续、rising_edge或迟滞声明，尚未绑定来源时钟或执行状态。

    condition是由合法简单别名/原生有限常量生成的受限DSL；正常计划编译仍检查类型和依赖。
    selection_origin仅持续规则为onset，point没有持续选择；实例不产生事件。
    """

    id: str  # 生成节点ID。
    rule_type: str  # condition_duration、rising_edge或hysteresis。
    condition: str | None  # 公共DSL；迟滞改用两个明确条件。
    minimum_duration_ns: int | None = None  # condition_duration门槛，单位ns。
    selection_origin: str | None = None  # condition_duration为onset。
    emit_initial: bool = False  # rising_edge首次初始化政策。
    enter_condition: str | None = None  # 迟滞进入条件，普通规则不使用。
    exit_condition: str | None = None  # 迟滞退出条件。
    enter_delay_ns: int = 0  # 进入确认等待，纳秒。
    exit_delay_ns: int = 0  # 退出确认等待，纳秒。


@dataclass(frozen=True)
class PresetCalculation:
    """保存按原活动范围计算的积分或时长声明及独立覆盖/部分结果政策。

    积分signal是公共信号或派生别名，unit为Wh/Ah；condition_duration用明确BOOL条件和秒。
    partial_policy=None表示继承execution，不是默认强制strict；覆盖质量由既有CalculationDefinition判断。
    """

    id: str  # 生成指标ID。
    scope: str  # event:生成活动ID。
    signal: str | None  # 简单别名；condition-only duration不提供。
    unit: str  # 明确积分输出单位。
    minimum_coverage: int | float = 0  # 0—1，只影响覆盖质量判断。
    partial_policy: str | None = None  # 未提供则由完整计划执行选项继承。
    operation: str = 'integral'  # integral或按实际事件区间计算duration。
    condition: str | None = None  # duration可用恒真条件计整个已知活动区间。


@dataclass(frozen=True)
class PlanFragment:
    """保存预设生成的公共节点，不含来源、执行器或真实样本。

    derived/rules/windows/calculations/sequences为类型化不可变tuple；序列化只是声明副本。
    ID不隐式改变，合入完整计划时继续检查用户节点及其他预设冲突。
    """

    derived: tuple[DerivedDefinition, ...] = ()
    rules: tuple[PresetRule, ...] = ()
    windows: tuple[WindowSpec, ...] = ()
    calculations: tuple[PresetCalculation, ...] = ()
    sequences: tuple[SequencePlan, ...] = ()  # 可选点事件配对声明；空值不输出sequences键。

    def to_dict(self):
        """将类型化片段序列化为当前配置节点副本；没有配对时省略空sequences键。

        参数: 无；读取生成的不可变声明。
        返回: dict，可合入AnalysisPlan.from_dict；不含伪造来源或执行结果。
        异常: 无主动异常；实例由build_preset构造。
        """
        # 派生元数据不伪造领域意义，公共名称与表达式保持。
        derived = {item.name: {'expr': item.expr, 'unit': item.unit} for item in self.derived}
        rules, windows, calculations = [], [], []
        for item in self.rules:
            row = {'name': item.id, 'rule_type': item.rule_type}
            if item.rule_type == 'hysteresis':
                row.update(enter_condition=item.enter_condition, exit_condition=item.exit_condition,
                    enter_delay=f'{item.enter_delay_ns}ns', exit_delay=f'{item.exit_delay_ns}ns')
                rules.append(row)
                continue
            row['condition'] = item.condition
            if item.rule_type == 'condition_duration':
                row.update(minimum_duration=f'{item.minimum_duration_ns}ns', duration_comparison='>=',
                           selection_origin=item.selection_origin)
            else:
                row['emit_initial'] = item.emit_initial
            rules.append(row)
        for item in self.windows:
            windows.append({'name': item.window_id, 'rule': item.event_rule_id, 'anchor': item.anchor,
                            'pre': f'{item.pre_ns}ns', 'post': f'{item.post_ns}ns', 'merge': item.merge})
        for item in self.calculations:
            row = {'name': item.id, 'scope': item.scope, 'operation': item.operation, 'unit': item.unit,
                   'minimum_coverage': item.minimum_coverage}
            if item.signal is not None:
                row['expr'] = item.signal
            if item.condition is not None:
                row['condition'] = item.condition
            if item.operation == 'integral':
                row['method'] = 'zoh'
            if item.partial_policy is not None:
                row['partial_policy'] = item.partial_policy
            calculations.append(row)
        result = {'derived': derived, 'rules': rules, 'windows': windows, 'calculations': calculations}
        if self.sequences:
            result['sequences'] = [dict(name=item.sequence_id, start=item.start_rule, response=item.response_rule,
                min_delay=f'{item.min_delay_ns}ns', max_delay=f'{item.max_delay_ns}ns', max_pending=item.max_pending)
                for item in self.sequences]
        from .config_groups import public_configuration
        return public_configuration(result)
