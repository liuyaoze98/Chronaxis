"""校验 v4 结果表聚合的来源、字段、分组、总体政策与输出单位。"""

from dataclasses import dataclass
from fractions import Fraction
from .checks import PlanValidationError, array_at, object_at, choice_at
from .nodes import register_id
from ..core.unit_registry import resolve_unit, output_label, conversion
from ..core.moments import moment_source_unit
from ..core.quantiles import quantile_probability


@dataclass(frozen=True)
class AggregationPlan:
    """一次已编译的归约，只消费同一分析中的一个具名结果来源。"""

    name: str
    source_kind: str
    source_id: str
    operation: str
    field: str | None
    group_by: tuple[str, ...]
    input_unit: str
    unit: str
    include_partial: bool
    partial_policy: str
    q: int | float | None
    ddof: int


def aggregation_unit(operation, source_unit, target):
    """核实已输出量的尺度，方差用平方温差，返回可复算的输出换算。

    参数: operation 为聚合操作，source_unit 为引用结果的单位，target 可省略。
    返回: 输出单位、倍率、偏移；偏移在求和时按参与数累计。异常: 单位不可比或未知变换。
    """
    if operation == 'count':
        if target not in (None,'1'):
            raise ValueError('count 的单位只能为 1')
        return '1', 1, 0
    source = resolve_unit(source_unit)
    if source is None:
        if operation != 'variance' and target in (None,source_unit):
            return source_unit, 1, 0
        raise ValueError('未知单位不能换算或求方差')
    base = moment_source_unit('sample_variance',source) if operation=='variance' else source
    # 方差保留原尺度的平方，默认输出文本必须能再次解析。
    spelling = target or (f'({source_unit})^2' if operation=='variance' else source_unit)
    if operation == 'variance' and source.temperature_role == 'absolute' and target is None:
        spelling = '(delta_degC)^2' if source.offset else '(delta_K)^2'
    dst = resolve_unit(target) if target is not None else base
    if dst is None:
        raise ValueError('聚合输出单位未登记')
    scale, shift = conversion(base,dst)
    factor = scale.factor if scale.pi_power == 0 else Fraction(scale.to_float())
    return output_label(dst,spelling), factor, shift


def parse_aggregations(raw, version, calculations, rules, windows, sequences, execution, ids):
    """把声明列表解析为不可变归约计划，拒绝选择行或任意字段访问。

    参数: raw 为数组，version/各来源目录/execution/ids 均来自同一主计划。
    返回: AggregationPlan 元组，顺序与配置一致。异常: PlanValidationError 定位错误条目。
    """
    if version != 4:
        raise PlanValidationError('$.aggregations','aggregations 仅在配置版本4中可用')
    catalogs = {'calculation':{r.calculation_id:r for r in calculations},'sequence':{r.sequence_id:r for r in sequences},
                'rule':{r.rule_id:r for r in rules},'window':{r.window_id:r for r in windows}}
    plans = []
    for i,value in enumerate(array_at(raw,'$.aggregations')):
        path = f'$.aggregations[{i}]'
        item = object_at(value,path,('name','source','operation'),
                         ('field','group_by','unit','partial_policy','include_partial','q','ddof'))
        name = register_id(item['name'],path+'.name',ids)
        source = object_at(item['source'],path+'.source',(),tuple(catalogs))
        if len(source) != 1:
            raise PlanValidationError(path+'.source','需要一个具名结果对象')
        kind,source_id = next(iter(source.items()))
        if type(source_id) is not str or source_id not in catalogs[kind]:
            raise PlanValidationError(path+'.source.'+kind,'引用的结果对象不存在')
        source_plan = catalogs[kind][source_id]
        if kind=='calculation' and source_plan.operation=='select':
            raise PlanValidationError(path+'.source','select 行不是标量结果')
        op = choice_at(item['operation'],('count','sum','mean','variance','quantile','median')
                       if kind in ('calculation','sequence') else ('count',),path+'.operation')
        field = None if op=='count' else 'delay_ns' if kind=='sequence' else 'value'
        if 'field' in item and (field is None or item['field'] != field):
            raise PlanValidationError(path+'.field','此操作不支持所选字段')
        keys = tuple(array_at(item.get('group_by',[]),path+'.group_by'))
        allowed = {'dataset_id','entity_id','session_id',kind+'_id'}
        if kind=='calculation' and source_plan.scope!='session':
            allowed.add('parent_id')
        if any(type(key) is not str or key not in allowed for key in keys) or len(set(keys))!=len(keys):
            raise PlanValidationError(path+'.group_by','分组键不适用于此来源或重复')
        include = item.get('include_partial',False)
        if type(include) is not bool or include and (kind!='calculation' or op=='count'):
            raise PlanValidationError(path+'.include_partial','仅数值指标允许纳入 partial 数值')
        policy=choice_at(item.get('partial_policy',execution.partial_policy),('report','strict'),path+'.partial_policy')
        q=item.get('q')
        if op=='quantile':
            try:
                quantile_probability('sample_quantile',q)
            except ValueError as error:
                raise PlanValidationError(path+'.q',str(error)) from error
        elif 'q' in item:
            raise PlanValidationError(path+'.q','只有 quantile 接受 q')
        ddof=item.get('ddof',0)
        if 'ddof' in item and (op!='variance' or type(ddof) is not int or ddof not in (0,1)):
            raise PlanValidationError(path+'.ddof','只有 variance 接受 ddof=0 或 1')
        input_unit = '1' if op=='count' else 'ns' if kind=='sequence' else source_plan.unit
        try:
            unit,_,_=aggregation_unit(op,input_unit,item.get('unit'))
        except (TypeError,ValueError) as error:
            raise PlanValidationError(path+'.unit',str(error)) from error
        plans.append(AggregationPlan(name,kind,source_id,op,field,keys,input_unit,unit,include,policy,q,ddof))
    return tuple(plans)
