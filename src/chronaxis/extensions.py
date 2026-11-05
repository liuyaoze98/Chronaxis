"""由宿主Python程序显式声明可信扩展，纯配置只引用其已注册名称。

逐点函数声明固定输入输出端口；样本归约与网格变换分别使用具有生命周期
的工厂。注册表冻结名称、版本、类型、单位和后端能力，以稳定摘要标识协议。
本模块不发现模块、不读取配置中的文件或导入路径，也不在注册时创建运行状态。
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType

from .core.types import SignalDType as D
from .core.unit_registry import resolve_unit
from .core.validation import require_identifier, require_text
from .core.function_contracts import builtin_function_specs


_BUDGET = ContextVar('chronaxis_host_extension_budget',default=None)
_BUILTINS = frozenset(builtin_function_specs()) | frozenset("""
duration integral select legacy_sum sample_mean
sample_minimum sample_maximum min_time max_time time_weighted_mean sample_count point_event_count
activity_count segment_count sample_variance sample_stddev sample_rms sample_median sample_quantile
time_variance time_stddev time_rms rolling_time_mean rolling_minimum rolling_maximum rolling_integral
adjacent_rate window_rate sample_fit_slope
condition_duration rising_edge falling_edge start_only window_delta debounce hysteresis start_end
""".split())


@dataclass(frozen=True)
class ValueSpec:
    """一个固定类型与数值尺度的端口。BOOL使用单位1，枚举代码需在DSL中显式取出。"""

    dtype: D
    unit: str

    def __post_init__(self):
        """核对宿主声明的类型与尺度。参数: 无。返回: None。异常: ValueError为非法端口。"""
        if not isinstance(self.dtype,D) or self.dtype is D.ENUM or resolve_unit(self.unit) is None:
            raise ValueError('扩展端口须声明数值或BOOL类型及已登记单位')
        if self.dtype is D.BOOL and self.unit != '1':
            raise ValueError('扩展BOOL端口的单位必须为1')


class _BackendSpec:
    """三类协议共享名称/版本与显式能力验证，不共享数值或状态回调。"""

    def require_backend(self, backend):
        """取得请求后端自身的实现。参数: backend为reference或numpy。返回: 回调。异常: 缺实现报ValueError。"""
        if backend not in ('reference','numpy'):
            raise ValueError('扩展后端须为reference或numpy')
        implementation = self.reference if backend == 'reference' else self.numpy
        if implementation is None:
            raise ValueError(f'扩展 {self.name} {self.version} 不支持后端 {backend}')
        return implementation

    def _check(self, inputs):
        """校验名称、版本、端口与声明的具体后端。参数: 固定输入tuple。返回: None。异常: 非法描述报错。"""
        require_identifier(self.name,'extension.name')
        require_text(self.version,'extension.version')
        if self.name in _BUILTINS:
            raise ValueError(f'扩展名称与内置能力冲突：{self.name}')
        if type(inputs) is not tuple or not inputs or any(type(p) is not ValueSpec for p in (*inputs,self.output)):
            raise TypeError('扩展需要非空固定输入及明确的ValueSpec输出')
        if self.reference is None and self.numpy is None or any(
                f is not None and not callable(f) for f in (self.reference,self.numpy)):
            raise ValueError('扩展至少需要一个可调用的后端实现')


@dataclass(frozen=True)
class FunctionSpec(_BackendSpec):
    """纯逐点函数，impl(args,resources)返回同一形状的ScalarValue或NumericArray。

    固定位置参数逐一按端口单位及dtype编译，任何必要输入无效都传递到结果；
    无历史，真实输入更新沿用普通表达式政策。
    """
    name: str
    version: str
    inputs: tuple[ValueSpec,...]
    output: ValueSpec
    reference: object = None
    numpy: object = None

    def __post_init__(self):
        """参数: 无。返回: None。异常: 声明或实现不合法时拒绝注册。"""
        self._check(self.inputs)


@dataclass(frozen=True)
class ReductionSpec(_BackendSpec):
    """标量样本归约协议；factory(resources)建立每范围独立的状态。

    consume接收已选真实样本，finalize返回ScalarValue，close退还外部资源；
    mergeable=True时还必须提供merge(other)。cancel和close均为必需方法，分别处理取消及资源释放。
    """
    name: str
    version: str
    input: ValueSpec
    output: ValueSpec
    reference: object = None
    numpy: object = None
    state_bytes: int = 0
    mergeable: bool = False

    def __post_init__(self):
        """参数: 无。返回: None。异常: 资源/合并能力或端口不合规时拒绝。"""
        self._check((self.input,))
        if type(self.state_bytes) is not int or self.state_bytes < 0 or type(self.mergeable) is not bool:
            raise ValueError('归约需要非负state_bytes和布尔mergeable')
        if self.input.dtype is D.BOOL or self.output.dtype is D.BOOL:
            raise ValueError('标量样本归约需要数值输入和输出')


@dataclass(frozen=True)
class TransformSpec(_BackendSpec):
    """有状态网格变换；factory(resources)为本次会话创建状态。

    advance(time_ns,window_ns,values,weights_ns)仅接收本窗口有效的ZOH区间，
    返回实际网格时刻的ScalarValue。history_ns限制回看窗口的实际或周期
    计量宽度，interval_modes声明该实现能正确使用的时间权重。
    """
    name: str
    version: str
    input: ValueSpec
    output: ValueSpec
    reference: object = None
    numpy: object = None
    state_bytes: int = 0
    history_ns: int = 0
    interval_modes: tuple[str,...] = ('actual','fixed','dbc')

    def __post_init__(self):
        """参数: 无。返回: None。异常: 非数值端口、非正历史或非法资源费时拒绝。"""
        self._check((self.input,))
        if (type(self.state_bytes) is not int or self.state_bytes < 0 or type(self.history_ns) is not int
                or not 0 < self.history_ns < 1 << 63 or self.input.dtype is D.BOOL or self.output.dtype is D.BOOL):
            raise ValueError('网格扩展需要数值端口、非负state_bytes及正int64历史时长')
        if (type(self.interval_modes) is not tuple or not self.interval_modes
                or any(m not in ('actual','fixed','dbc') for m in self.interval_modes)
                or len(set(self.interval_modes)) != len(self.interval_modes)):
            raise ValueError('时序扩展的interval_modes须明确列出互不重复的actual、fixed或dbc')


@dataclass(frozen=True,eq=False,init=False)
class ExtensionRegistry:
    """不可变的宿主能力集合；同次运行必须提供与编译时相同的注册对象。"""
    functions: object
    reductions: object
    transforms: object
    identity: str

    def __init__(self,functions=(),reductions=(),transforms=()):
        """登记三种互斥的typed描述。参数: 三类描述符tuple。返回: 新注册表。异常: 重名或模型错误。"""
        records, names = [], set()
        for kind,entries,typ in (('functions',functions,FunctionSpec),('reductions',reductions,ReductionSpec),
                                 ('transforms',transforms,TransformSpec)):
            if type(entries) is not tuple or any(type(spec) is not typ for spec in entries):
                raise TypeError(f'{kind}需要对应描述符的tuple')
            by_name = {}
            for spec in entries:
                if spec.name in names:
                    raise ValueError(f'重复的扩展名称：{spec.name}')
                by_name[spec.name] = spec
                names.add(spec.name)
                ports = spec.inputs if kind == 'functions' else (spec.input,)
                records.append((kind,spec.name,spec.version,[(p.dtype.value,p.unit) for p in ports],
                                (spec.output.dtype.value,spec.output.unit),spec.reference is not None,
                                spec.numpy is not None,getattr(spec,'state_bytes',0),getattr(spec,'mergeable',False),
                                getattr(spec,'history_ns',0),sorted(getattr(spec,'interval_modes',()))))
            object.__setattr__(self,kind,MappingProxyType(by_name))
        # 身份取声明和实现版本，跨进程不使用函数地址；换实现的宿主须递增版本。
        payload = json.dumps(['chronaxis-host-v1',sorted(records)],ensure_ascii=False,separators=(',',':'))
        object.__setattr__(self,'identity',sha256(payload.encode('utf-8')).hexdigest())


@contextmanager
def using_extension_budget(budget):
    """让当前调用栈的逐点扩展使用实际运行账本，嵌套及异常后恢复原上下文。

    参数: budget为本次ResourceBudget。返回: 上下文管理器。异常: 回调/执行异常原样传播。
    """
    token = _BUDGET.set(budget)
    try:
        yield
    finally:
        _BUDGET.reset(token)
