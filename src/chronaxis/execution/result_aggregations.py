"""在最终结果行产生时按具名引用分组。只保存归约状态和精确分位数所需的样本。"""

from fractions import Fraction
from math import isfinite
from ..core.quantiles import ExactQuantileBuffer
from ..core.types import SignalDType as D, QualityFlag as Q
from ..planning.aggregations import aggregation_unit
from ..results.aggregation_row import SummaryAggregationRow
from ..results.summary import SummaryCalculationRow, SummaryEventRow, SummarySegmentRow, SummarySequenceRow
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner


def discovery_rules(plan, spec):
    """定位总体发现所依赖的原规则。参数: 主计划与聚合。返回: 规则ID元组。异常: 引用未校验。"""
    if spec.source_kind=='rule':
        return (spec.source_id,)
    if spec.source_kind=='sequence':
        pair=next(item for item in plan.sequences if item.sequence_id==spec.source_id)
        return tuple(dict.fromkeys((pair.start_rule,pair.response_rule)))
    if spec.source_kind=='calculation':
        calc=next(item for item in plan.calculations if item.calculation_id==spec.source_id)
        if calc.scope=='session':
            return ()
        scope,parent=calc.scope.split(':')
        if scope=='event':
            return (parent,)
    else:
        parent=spec.source_id
    window=next(w for w in plan.windows if w.window_id==parent)
    return (window.event,)


class _Group:
    """一个实际键的有限状态。二阶和在精确有理数域累计，输出边界检查数值范围。"""

    def __init__(self):
        """创建空候选和零计数。参数: 无。返回: 新组。异常: 分配错误传播。"""
        self.total=self.used=self.excluded=self.bad=self.partials=0
        self.matched=self.timeout=self.insufficient=0
        self.sum=self.squares=Fraction(0)
        self.quality=Q.NONE
        self.quantile=None
        self.integer=True

    def accept(self,spec,row,budget,backend,dtype,needs_coverage):
        """从一条源行提取候选、分类及实际数值。参数: 计划、行、预算、后端、原dtype。返回: None。异常: 预算或模型错误。"""
        self.total+=1
        if spec.source_kind=='sequence':
            self.matched+=row.status=='matched'
            self.timeout+=row.status=='no_response'
            self.insufficient+=row.status=='indeterminate'
        if spec.operation=='count':
            # 计已观测对象身份。已确认请求的响应未知不使该请求本身消失。
            self.used+=1
            return
        if spec.source_kind=='sequence':
            if row.status=='no_response':
                self.excluded+=1
                return
            if row.status=='indeterminate':
                self.bad+=1
                self.quality|=row.quality
                return
            if row.quality & Q.ESTIMATED:
                self.bad+=1
                self.quality|=row.quality
                return
            value=row.delay_ns
        else:
            if row.unit!=spec.input_unit:
                raise ValueError('指标结果行单位与同一来源计划不符')
            if row.status=='complete' and row.value is None and row.reason=='empty_selection':
                self.excluded+=1
                return
            if (row.value is None or row.status=='indeterminate' or getattr(row,'coverage_status',None)=='indeterminate'
                    or needs_coverage and not hasattr(row,'coverage_status')
                    or row.status=='partial' and not spec.include_partial):
                self.bad+=1
                self.quality|=row.quality or Q.MISSING
                return
            self.partials+=row.status=='partial'
            value=row.value
        self.quality|=row.quality
        self.used+=1
        self.integer &= type(value) is int
        if spec.operation in ('quantile','median'):
            if self.quantile is None:
                self.quantile=ExactQuantileBuffer('sample_'+spec.operation,spec.q,dtype,backend,budget)
            if dtype is D.FLOAT64 and type(value) is int and int(float(value))!=value:
                self.quality|=Q.PRECISION_LOSS
                self.bad+=1
                self.used-=1
                self.partials-=getattr(row,'status','')=='partial'
                return
            if backend=='numpy':
                import numpy as np
                from ..core.numeric_numpy import DTYPES
                self.quantile.append(np.asarray([value],dtype=DTYPES[dtype]),np.ones(1,dtype=bool))
            else:
                self.quantile.append((value,))
        else:
            exact=Fraction(value)
            self.sum+=exact
            if spec.operation=='variance':
                self.squares+=exact*exact

    def value(self,spec,factor,shift):
        """最终一次换算，不平均行覆盖率或块分位数。参数: 计划及已核单位系数。返回: 数值、原因、质量。异常: 原预算/排序错误。"""
        if spec.operation=='count':
            return self.used,'ok',Q.NONE
        if not self.used:
            return None,'empty_population',Q.NONE
        if spec.operation=='variance' and self.used<=spec.ddof:
            return None,'insufficient_count',Q.NONE
        if spec.operation in ('median','quantile'):
            value,quality=self.quantile.finish()
            if value is None:
                return None,'numeric_error',quality
            number=Fraction(value)*factor+shift
            integral=type(value) is int
        elif spec.operation=='variance':
            number=(self.squares-self.sum*self.sum/self.used)/(self.used-spec.ddof)*factor
            integral=False
        elif spec.operation=='mean':
            number=self.sum/self.used*factor+shift
            integral=False
        else:
            number=self.sum*factor+shift*self.used
            integral=self.integer
        if integral and isinstance(number,Fraction) and number.denominator==1:
            if -(1<<63)<=number.numerator<1<<64:
                return number.numerator,'ok',Q.NONE
            return None,'numeric_error',Q.OVERFLOW
        try:
            result=float(number)
        except OverflowError:
            return None,'numeric_error',Q.OVERFLOW
        if (not isfinite(result) or result==0 and number
                or self.integer and abs(number)>=1<<53 and Fraction(result)!=number):
            return None,'numeric_error',Q.PRECISION_LOSS
        return result,'ok',Q.NONE


class ResultAggregations:
    """订阅同一次运行的必要源行，分组先预约，异常由拥有者统一关闭。"""

    def __init__(self,plan,budget):
        """预留有限声明、已知空组和结果元数据。参数: 已校验计划和共享账本。返回: owner。异常: 配置/预算错误含清理句柄。"""
        self._plan,self._budget=plan,budget
        self._held_cost=self._group_cost=0
        self._groups={}
        self._subscribers={}
        self._types={}
        self._scales={}
        self._coverage=set()
        self._seen=set()
        self._closed=False
        try:
            _reserve_owned_ram(self,8192+8192*len(plan.aggregations),'_group_cost')
            for spec in plan.aggregations:
                self._subscribers.setdefault((spec.source_kind,spec.source_id),[]).append(spec)
                self._scales[spec]=aggregation_unit(spec.operation,spec.input_unit,spec.unit)[1:]
                self._types[spec]=self._input_dtype(spec)
                if spec.source_kind=='calculation' and any(c.calculation_id==spec.source_id and
                        c.minimum_coverage>0 for c in plan.calculations):
                    self._coverage.add(spec)
        except BaseException as exc:
            _cleanup_owner(self,exc,'aggregation_cleanup_owner','结果聚合')
            raise

    def _input_dtype(self,spec):
        """确定分位数排序列的原类型。参数: 已校验聚合。返回: dtype。异常: 引用不符。"""
        if spec.source_kind=='sequence':
            return D.INT64
        if spec.source_kind!='calculation' or spec.operation not in ('median','quantile'):
            return D.FLOAT64
        calc=next(c for c in self._plan.calculations if c.calculation_id==spec.source_id)
        if self._plan.extensions is not None and calc.operation in self._plan.extensions.reductions:
            from ..core.calculations import CalculationDefinition,calculation_conversion
            from ..core.models import Interval
            value=self._plan.extensions.reductions[calc.operation].output
            unit=CalculationDefinition('stat','sample_minimum',Interval(0,0),output_unit=calc.unit,config_version=4)
            return calculation_conversion(unit,value.unit).dtype(value.dtype)
        if calc.operation.endswith('_count'):
            return D.UINT64
        if calc.operation in ('sample_minimum','sample_maximum','min_time','max_time'):
            from ..core.calculations import CalculationDefinition,calculation_conversion
            from ..core.models import Interval
            unit=CalculationDefinition('stat',calc.operation,Interval(0,0),output_unit=calc.unit,config_version=4)
            return calculation_conversion(unit,calc.signal.root.unit).dtype(calc.signal.root.dtype)
        return D.FLOAT64

    def _group(self,spec,row):
        """按稳定字段取得或创建组。参数: 计划、实际源行或已知固定空组。返回: 状态。异常: 预算或键不合法。"""
        dataset=self._plan.dataset
        values={'dataset_id':row.dataset_id if row is not None else dataset.dataset_id,
                'session_id':row.session_id if row is not None else dataset.session_id,
                'entity_id':row.entity_id if row is not None else dataset.entity,
                spec.source_kind+'_id':spec.source_id}
        if 'parent_id' in spec.group_by:
            values['parent_id']=row.parent_id
        key=tuple(values[k] for k in spec.group_by)
        identity=(spec,key)
        if identity not in self._groups:
            _reserve_owned_ram(self,32768+16*sum(len(k) for k in key),'_group_cost')
            self._groups[identity]=_Group()
        return self._groups[identity]

    def accept(self,row):
        """只分派实际受订阅的结果行。参数: 本次产出的行。返回: None。异常: 预算/输入矛盾。"""
        if isinstance(row,SummaryCalculationRow):
            key=('calculation',row.calculation_id)
        elif isinstance(row,SummarySequenceRow):
            key=('sequence',row.rule_id)
        elif isinstance(row,SummaryEventRow):
            key=('rule',row.rule_id)
        elif isinstance(row,SummarySegmentRow):
            key=('window',row.window_id)
        else:
            return
        for spec in self._subscribers.get(key,()):
            self._seen.add(spec)
            self._group(spec,row).accept(spec,row,self._budget,self._plan.execution.backend,self._types[spec],spec in self._coverage)

    def rows(self,rules,sequence):
        """在原规则完成后交付总体判定及组结果。参数: 原规则owner、首序号。返回: 逐组行。异常: 未完成或预算错误。"""
        by_id={owner._request.rule_id:owner for owner in rules}
        ds=self._plan.dataset
        for spec in self._plan.aggregations:
            if spec not in self._seen and 'parent_id' not in spec.group_by:
                self._group(spec,None)
        for (spec,key),group in self._groups.items():
            evidence=[by_id[name].count_evidence(ds.domain) for name in discovery_rules(self._plan,spec)]
            complete=all(e[2] for e in evidence)
            observed=all(e[0] for e in evidence)
            determinate=all(e[1] for e in evidence)
            quality=group.quality
            for _,_,_,flags in evidence:
                quality|=flags
            partial=not complete or group.bad>0 or group.partials>0
            number,reason,flag=group.value(spec,*self._scales[spec])
            quality|=flag
            if not group.used and (not observed or not determinate or group.bad):
                number,status,reason=None,'indeterminate','no_observation' if not observed else 'insufficient_data'
            elif reason=='numeric_error' or reason=='insufficient_count':
                status='indeterminate'
            elif partial:
                status,reason='partial','partial_population'
                if spec.partial_policy=='strict':
                    number=None
            else:
                status='empty' if number is None else 'complete'
            identity=dict(zip(spec.group_by,key))
            yield SummaryAggregationRow(sequence,identity.get('dataset_id',ds.dataset_id),identity.get('entity_id',ds.entity),
                identity.get('session_id',ds.session_id),spec.name,spec.source_kind,
                spec.source_id,spec.operation,spec.group_by,key,number,spec.unit,status,reason,group.total,
                group.used,group.excluded,group.bad,group.partials,group.matched,group.timeout,group.insufficient,
                0,complete,quality)
            sequence+=1

    def close(self):
        """释放精确分位数和自己的分组费用，可重试。参数: 无。返回: None。异常: 原账本错误传播。"""
        if self._closed:
            return
        for group in self._groups.values():
            if group.quantile is not None:
                group.quantile.close()
        self._groups.clear()
        _release_owned_ram(self,self._group_cost,'_group_cost')
        self._closed=True
