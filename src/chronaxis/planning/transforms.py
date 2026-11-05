"""解析 v4 时序变换的名称图、时间网格、输入表达式及输出单位。

每个离散序列作为独立的分析来源声明，不向真实 reader 增加字段。先按表达式
引用拓扑校验所有声明（包括不用的声明），再给消费者提供同一套最终绑定。
本模块不扫描数据、不生成网格点，也不创建历史。
"""

import ast
from dataclasses import dataclass, field, replace
from hashlib import sha256
from ..core.binding import SignalDefinition
from ..core.calculations import CalculationDefinition, CalculationConversion, calculation_conversion
from ..core.declarations import DeclaredSource
from ..core.expression import StaticExpression, validate_expression
from ..core.models import Interval
from ..core.types import SignalDType as D, TimeType
from .checks import (PlanValidationError, array_at, canonical, choice_at, coordinate_at, duration_at,
                     model_at, number_at, object_at, text_at)

ROLLING = ('rolling_time_mean', 'rolling_minimum', 'rolling_maximum', 'rolling_integral')
RATES = ('adjacent_rate', 'window_rate', 'sample_fit_slope')
MAX_TRANSFORMS = 64  # 防止用户定义无界依赖链和运行回调栈。


@dataclass(frozen=True)
class TemporalTransformPlan:
    """按拓扑序保存一个已验证的离散变换，预算与运行状态在任务启动时创建。"""

    name: str
    operation: str
    expression: StaticExpression
    output: SignalDefinition
    conversion: CalculationConversion
    physical: tuple[str, ...]
    window_ns: int | None
    step_ns: int | None
    origin_ns: int
    max_gap_ns: int | None
    partial_policy: str
    minimum_coverage: float
    host_spec: object = field(default=None,repr=False,compare=False)  # 仅运行宿主注册的实际网格操作。


def _names(text, path):
    """提取引用边。参数: 表达式文本及位置。返回: 名称集合。异常: 带位置的语法错误。"""
    try:
        tree = ast.parse(text, mode='eval')
    except (SyntaxError, TypeError) as error:
        raise PlanValidationError(path, '变换输入须为合法表达式') from error
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def build_transforms(raw, bindings, derived, *, timezone=None):
    """解析全图。参数: 配置项、物理声明、派生定义及时间区。返回: 最终声明和变换元组。异常: 配置错误。"""
    if bindings.config_version != 4:
        raise PlanValidationError('$.transforms', 'transforms需要config_version=4')
    rows, edges, plans = {}, {}, {}
    original = {s.name for s in bindings.signals}
    formulas = {d.name: d for d in derived}
    for d in derived:
        edges[d.name] = _names(d.expr, '$.derived.'+d.name)
    entries=array_at(raw,'$.transforms')
    if len(entries)>MAX_TRANSFORMS:
        raise PlanValidationError('$.transforms',f'最多支持{MAX_TRANSFORMS}个时序变换')
    for i, item in enumerate(entries):
        path = f'$.transforms[{i}]'
        base = object_at(item, path, ('name','operation','expr'), ('window','step','origin','max_gap','unit',
                         'minimum_coverage','partial_policy'))
        name = text_at(base['name'], path+'.name', identifier=True)
        if name in original or name in formulas or name in rows:
            raise PlanValidationError(path+'.name', '时序、派生与原信号名称必须唯一')
        registry = getattr(bindings,'extensions',None)
        registered = registry.transforms if registry is not None else {}
        op = choice_at(base['operation'], ROLLING+RATES+tuple(registered), path+'.operation')
        params = ('max_gap',) if op == 'adjacent_rate' else ('window','step')
        extra = ('unit',) if op == 'adjacent_rate' else ('unit','origin','minimum_coverage','partial_policy')
        item = object_at(base,path,('name','operation','expr',*params),extra)
        rows[name] = path,item
        edges[name] = _names(text_at(item['expr'],path+'.expr'),path+'.expr')

    ordered, done, visiting = [], set(), set()
    def visit(name):
        """按依赖先后检查循环。参数: 原简单名称。返回: 无。异常: 包括派生/变换混合环。"""
        if name in visiting:
            raise PlanValidationError('$.transforms', '派生或时序变换循环依赖：'+name)
        if name in done or name not in edges:
            return
        visiting.add(name)
        for dep in sorted(edges[name]):
            visit(dep)
        visiting.remove(name)
        done.add(name)
        ordered.append(name)

    for name in edges:
        visit(name)
    available = []
    source_names = {s.name for s in bindings.sources}
    for name in ordered:
        if name in formulas:
            available.append(formulas[name])
            continue
        path, item = rows[name]
        op = item['operation']
        local = replace(bindings,derived_names=tuple(d.name for d in available))
        host_spec = registered.get(op)
        expr = model_at(validate_expression,path+'.expr',item['expr'],local,derived=tuple(available),
                        unit=host_spec.input.unit if host_spec is not None else None)
        if host_spec is not None and expr.root.dtype is not host_spec.input.dtype:
            raise PlanValidationError(path+'.expr','宿主时序变换需要与声明端口一致的输入dtype')
        if expr.root.dtype not in (D.FLOAT64,D.INT64,D.UINT64):
            raise PlanValidationError(path+'.expr','时序数值变换需要数值输入')
        physical = tuple(dict.fromkeys(alias for dep in expr.dependencies
                    for alias in (plans[dep].physical if dep in plans else (dep,))))
        model_at(bindings.require_synchronized,path+'.expr',physical)
        grid = op != 'adjacent_rate'
        window = duration_at(item['window'],path+'.window',positive=True) if grid else None
        if host_spec is not None and window > host_spec.history_ns:
            raise PlanValidationError(path+'.window','时序窗口超过宿主注册的history_ns')
        step = duration_at(item['step'],path+'.step',positive=True) if grid else None
        gap = None if grid else duration_at(item['max_gap'],path+'.max_gap',positive=True)
        origin = coordinate_at(item['origin'],path+'.origin',absolute=bindings.timebase.time_type is TimeType.ABSOLUTE,
                               tz=timezone) if 'origin' in item else 0
        policy = choice_at(item.get('partial_policy','strict'),('strict','report'),path+'.partial_policy')
        coverage = number_at(item.get('minimum_coverage',0),path+'.minimum_coverage',minimum=0,maximum=1)
        unit = host_spec.output.unit if host_spec is not None else expr.root.unit
        if op in RATES:
            from ..core.rate_transforms import rate_unit
            unit = model_at(rate_unit,path+'.unit',unit)
        # 平均值/极值保留输入尺度，积分从规范输入推导面积；最后统一兼容目标。
        calculation = 'integral' if op=='rolling_integral' else 'sample_minimum'
        target = item.get('unit', None if calculation=='integral' else unit)
        if calculation == 'integral':
            from ..core.unit_registry import resolve_unit
            child = expr.root
            while child.operator=='unit_convert' and not child.unit_explicit:
                child = child.args[0]
            original_unit = resolve_unit(child.unit)
            if original_unit is not None and original_unit.offset:
                raise PlanValidationError(path+'.expr','绝对摄氏度滚动积分须先显式转换到K')
        spec = CalculationDefinition(name,calculation,Interval(0,0),output_unit=target,config_version=4)
        conversion = model_at(calculation_conversion,path+'.unit',spec,unit)
        dtype = conversion.dtype(expr.root.dtype) if op in ('rolling_minimum','rolling_maximum') else D.FLOAT64
        if host_spec is not None:
            dtype = conversion.dtype(host_spec.output.dtype)
        source = '_temporal_'+name
        while source in source_names:
            source = '_'+source
        source_names.add(source)
        identity = sha256(canonical((item,registry.identity) if host_spec is not None else item).encode('utf-8')).hexdigest()
        declared = DeclaredSource(source,bindings.timebase,'temporal:'+identity)
        output = SignalDefinition(name,source,'temporal.'+name,dtype,conversion.unit,step or gap,config_version=4)
        bindings = replace(bindings,sources=bindings.sources+(declared,),signals=bindings.signals+(output,),
                           temporal_inputs=bindings.temporal_inputs+((name,physical),))
        plans[name] = TemporalTransformPlan(name,op,expr,output,conversion,physical,window,step,origin,gap,policy,coverage,host_spec)
    # 重编译到最终绑定；执行时按原声明复核，不把临时拓扑身份交给 reader。
    return bindings, tuple(replace(p,expression=model_at(validate_expression,rows[p.name][0]+'.expr',
                p.expression.text,bindings,derived=derived,unit=p.host_spec.input.unit if p.host_spec is not None else None))
                           for p in plans.values())


def active_transforms(plan, aliases):
    """从消费者逆向收集必要变换。参数: 计划、输出别名集合。返回: 拓扑序元组。异常: 已建计划错误。"""
    needed = set(aliases)
    selected = []
    for item in reversed(plan.transforms):
        if item.name in needed:
            selected.append(item)
            needed.update(item.expression.dependencies)
    return tuple(reversed(selected))


def physical_dependencies(plan, aliases):
    """展开原采集依赖。参数: 计划和表达式输入别名。返回: 保序去重原别名。异常: 已建计划错误。"""
    transforms = {p.name:p.physical for p in plan.transforms}
    return tuple(dict.fromkeys(n for a in aliases for n in transforms.get(a,(a,))))
