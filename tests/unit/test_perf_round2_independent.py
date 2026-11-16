"""核对 P1 自动后端与 P3 状态、质量位、活动分支及宿主调用契约。

仅使用小型合成输入；同类异常不计作数值比较通过，不提供计时结论。
"""
import copy
import dataclasses
from contextlib import closing
from enum import IntFlag
import struct
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core import expression_reference, integral_sum_numpy
from chronaxis.core.expression import ExprNode
from chronaxis.core.integral_sum import IntegralStateLimitError
from chronaxis.core.integral_sum_numpy import NumpyIntegralSum
from chronaxis.core.scalar import ScalarValue
from chronaxis.core.types import QualityFlag as Q, SignalDType as D
from chronaxis.extensions import FunctionSpec, ValueSpec
from chronaxis.planning.backend_selection import select_backend


def readonly(values):
    """生成规范只读列。参数: 有限面积列表。返回: 数值及有效位。异常: 数组分配错误。"""
    values=np.array(values,dtype=np.float64); valid=np.ones(len(values),dtype=bool)
    values.setflags(write=False);valid.setflags(write=False)
    return values,valid


def captured(function):
    """比较标准库委派的返回或异常。参数: 零参回调。返回: 类型和值/异常。异常: 无。"""
    try:
        value=function()
        return type(value),repr(value)
    except (ValueError,TypeError) as exc:
        return type(exc),str(exc)


def expression_node(operation,dtype,*args,**options):
    """建立局部冻结表达式。参数: 类型、子树与属性。返回: ExprNode。异常: 模型错误。"""
    aliases=tuple(dict.fromkeys(alias for arg in args for alias in arg.aliases))
    return ExprNode(operation,dtype,'1','verified',args=tuple(args),aliases=aliases,**options)


def named(alias,dtype):
    """建立信号叶。参数: 名称和类型。返回: ExprNode。异常: 模型错误。"""
    return ExprNode('name',dtype,'1','verified',name=alias,aliases=(alias,))


def exact(x):
    """保存全部结果字段及浮点位。参数: 原结果。返回: 可比结构。异常: 不支持对象沿用文本。"""
    if type(x) is float:return {'float_bits':struct.pack('>d',x).hex()}
    if isinstance(x,dict):return {k:exact(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [exact(v) for v in x]
    if isinstance(x,(str,int,bool,type(None))):return x
    return {'type':type(x).__name__,'value':str(x)}

def base():
    """建立缺值、过期、大整数和条件事件夹具。返回: 小型内存配置。异常: 无。

    参数: 无。
    """
    vals=[(0,1,1.,-273.15),(120,2,2.,-0.),(300,3,None,15.),(600,2**53+1,4.,80.),(800,2**63-1,-1.,100.),(1000,0,0.,0.)]
    return {'config_version':4,'dataset':{'name':'independent','domain':{'start':'0s','end':'1s'}},
      'sources':[{'source_type':'memory','rows':[{'time':f'{t}ms','values':{'counter':i,'power':p,'temperature':c}} for t,i,p,c in vals]}],
      'signals':[{'name':'counter','field':'counter','dtype':'int64','unit':'1','valid_for':'250ms'},
        {'name':'power','field':'power','dtype':'float64','unit':'W','valid_for':'250ms'},
        {'name':'temperature','field':'temperature','dtype':'float64','unit':'degC','valid_for':'250ms'}],
      'rules':[{'name':'on','rule_type':'condition_duration','condition':'power > 0','minimum_duration':'0s','duration_comparison':'>='},
        {'name':'up','rule_type':'rising_edge','condition':'power > 0','emit_initial':True}],
      'windows':[{'name':'around','rule':'on','anchor':'activity','pre':'10ms','post':'20ms'}],
      'calculations':[{'name':'energy','operation':'integral','expr':'power','condition':'bit_test(counter,0)'},
        {'name':'duration','operation':'duration','condition':'counter > 9007199254740992'},
        {'name':'average','operation':'time_weighted_mean','expr':'power','condition':'bit_test(counter,0)'},
        {'name':'min','operation':'min_time','expr':'power'}, {'name':'max','operation':'max_time','expr':'power'},
        {'name':'smin','operation':'sample_minimum','expr':'counter'}, {'name':'smax','operation':'sample_maximum','expr':'counter'},
        {'name':'count','operation':'sample_count','expr':'power'}, {'name':'up_count','operation':'point_event_count','rule':'up'},
        {'name':'on_count','operation':'activity_count','rule':'on'}, {'name':'seg_count','operation':'segment_count','window':'around'},
        {'name':'selected','operation':'select','expr':'where(bit_test(counter,0),to_float64(counter),power / power)'},
        {'name':'event_energy','operation':'integral','expr':'power','scope':{'rule':'on'}},
        {'name':'window_energy','operation':'integral','expr':'power','scope':{'window':'around'}}], 'execution':{'backend':'auto','batch_rows':3}}

def cases():
    """构建五类少量内存边界计划。返回: 名称到配置的映射。异常: 无。

    参数: 无。
    """
    cases={}
    cases['integer_condition_where_missing_ttl']=base()
    unit=base();unit['calculations']=[{'name':'kelvin','operation':'time_weighted_mean','expr':'to_unit(temperature,"K")','unit':'degC'}, {'name':'select_temp','operation':'select','expr':'to_unit(temperature,"K")','unit':'degC'}, {'name':'scale','operation':'integral','expr':'to_unit(power,"kW")','unit':'J'}];cases['affine_and_scaled_units']=unit
    fixed=base();fixed['calculations']=[{'name':'energy','operation':'integral','expr':'power','condition':'bit_test(counter,0)','interval':{'mode':'fixed','value':'100ms','driver':'power'}}, {'name':'avg','operation':'time_weighted_mean','expr':'power','interval':{'mode':'fixed','value':'100ms'}}];cases['fixed_interval_condition']=fixed
    lookup=base();lookup['lookups']=[{'name':'curve','input_unit':'W','unit':'W','points':[[-1.,2.],[1.,2.],[4.,10.]]}];lookup['calculations']=[{'name':'mapped','operation':'integral','expr':'lookup(power,"curve")'}, {'name':'selected','operation':'select','expr':'lookup(power,"curve")'}];cases['lookup']=lookup
    maths=base();maths['calculations']=[{'name':'norm','operation':'integral','expr':'sqrt(square(power))'}, {'name':'selection','operation':'select','expr':'clip(power,0,3)'}];cases['math_functions']=maths

    return cases

class PerfRound2IndependentTests(unittest.TestCase):
    """不依赖附件验证脚本的回归断言。"""

    def test_all_quality_pairs_and_external_operands(self):
        """512² 并集及外部类型保持标准库行为。参数/返回: 无。异常: 断言失败。"""
        for left in range(512):
            for right in range(512):
                self.assertIs(Q(left)|Q(right),IntFlag.__or__(Q(left),Q(right)))
        others=(-1024,-1,0,1,511,512,1024,True,1.,None,np.int64(-1),np.int64(0),np.int64(511),np.int64(512),np.uint64(0),np.uint64(511),np.uint64(512))
        for left in range(512):
            for other in others:
                for method in ('__or__','__ror__'):
                    self.assertEqual(captured(lambda:getattr(Q,method)(Q(left),other)),
                                     captured(lambda:getattr(IntFlag,method)(Q(left),other)))

    def test_backend_successful_results_and_exclusions(self):
        """五类合法计划两后端必须成功且完整结果逐位相同。参数/返回: 无。异常: 任何运行错误。"""
        for label,cfg in cases().items():
            with self.subTest(case=label):
                self.assertEqual(select_backend(AnalysisPlan.from_dict(copy.deepcopy(cfg))).selected,'reference')
                outputs=[]
                for backend in ('reference','numpy'):
                    chosen=copy.deepcopy(cfg);chosen['execution']['backend']=backend
                    plan=AnalysisPlan.from_dict(chosen)
                    self.assertEqual(select_backend(plan).selected,backend)
                    with AnalysisRunner().run(plan) as output:
                        tables={}
                        for method in ('iter_calculations','iter_events','iter_segments'):
                            with closing(getattr(output,method)()) as rows:
                                tables[method]=[exact(dataclasses.asdict(row)) for row in rows]
                        if any(c['operation']=='select' for c in chosen['calculations']):
                            with closing(output.iter_selections()) as rows:
                                tables['iter_selections']=[exact(dataclasses.asdict(row)) for row in rows]
                        self.assertTrue(tables['iter_calculations'])
                        outputs.append(tables)
                self.assertEqual(*outputs)
        excluded=base();excluded['calculations']=[{'name':'mean','operation':'sample_mean','expr':'power'}]
        self.assertEqual(select_backend(AnalysisPlan.from_dict(excluded)).selected,'numpy')

    def check_released(self,error):
        """只检查被测模块回溯，不清理调用方。参数: 原异常。返回: 无。异常: 引用遗留断言。"""
        seen=[];tb=error.__traceback__
        while tb:
            if tb.tb_frame.f_globals.get('__name__')=='chronaxis.core.integral_sum_numpy':
                seen.append(tb.tb_frame.f_code.co_name)
                for name,value in tb.tb_frame.f_locals.items():
                    self.assertFalse(isinstance(value,(NumpyIntegralSum,np.ndarray,list)),(name,type(value)))
            tb=tb.tb_next
        self.assertIn('push_values',seen)

    def test_allocation_and_cancel_before_install_keep_old_state(self):
        """第一次候选失败不得先计数，回溯释放输入/状态。参数/返回: 无。异常: 断言失败。"""
        for error in (MemoryError('candidate'),KeyboardInterrupt('cancel')):
            with self.subTest(error=type(error).__name__):
                state=NumpyIntegralSum();state.push_values(*readonly([5.]));readonly_before=readonly([1.,2.])
                with patch.object(integral_sum_numpy.np,'array',side_effect=error):
                    try:
                        state.push_values(*readonly_before)
                    except BaseException as actual:
                        self.assertIs(actual,error);self.check_released(actual)
                    else:self.fail('故障未传播')
                self.assertEqual(state.valid_term_count,1)
                self.assertEqual(state.finish('J').value,5.)
                self.assertFalse(state.calculation_failed)

    def test_second_allocation_preserves_only_committed_prefix(self):
        """第二条失败只保留已安装的第一条。参数/返回: 无。异常: 断言失败。"""
        state=NumpyIntegralSum();state.push_values(*readonly([5.]))
        columns=readonly([1.,2.]);allocate=np.array;calls=[];error=MemoryError('second')
        def allocate_once(*args,**kwargs):
            """参数: NumPy分配实参。返回: 首条候选。异常: 第二次注入故障。"""
            calls.append(1)
            if len(calls)==2:raise error
            return allocate(*args,**kwargs)
        with patch.object(integral_sum_numpy.np,'array',side_effect=allocate_once):
            try:state.push_values(*columns)
            except MemoryError as actual:self.assertIs(actual,error);self.check_released(actual)
            else:self.fail('第二次候选未失败')
        self.assertEqual(state.valid_term_count,2)
        self.assertEqual(state.finish('J').value,6.)

    def test_partial_limit_error_is_not_masked_by_cleanup_allocation(self):
        """超限原错误不得被finally再分配覆盖。参数/返回: 无。异常: 断言失败。"""
        state=NumpyIntegralSum(partial_limit=1);state.push_values(*readonly([1.]))
        columns=readonly([2.**-54])
        with patch.object(integral_sum_numpy.np,'array',side_effect=MemoryError('cleanup')):
            try:state.push_values(*columns)
            except IntegralStateLimitError as error:self.check_released(error)
            else:self.fail('应先报告容量超限')
        self.assertEqual(state.valid_term_count,1)
        self.assertEqual(state.finish('J').value,1.)

    def test_host_structural_reuse_and_active_names(self):
        """结构相同宿主调用每点一次，未选分支不访问。参数/返回: 无。异常: 断言失败。"""
        calls=[]
        def callback(args,resources):
            """记录有效回调。参数: 标量及资源。返回: 两倍输入。异常: 无。"""
            calls.append(args[0].value)
            return ScalarValue(args[0].value*2.,D.FLOAT64)
        spec=FunctionSpec('twice','v1',(ValueSpec(D.FLOAT64,'1'),),ValueSpec(D.FLOAT64,'1'),callback,None)
        first=expression_node('host_function',D.FLOAT64,named('x',D.FLOAT64),host_function=spec)
        second=expression_node('host_function',D.FLOAT64,named('x',D.FLOAT64),host_function=spec)
        self.assertIsNot(first,second);self.assertEqual(first,second)
        summed=expression_node('add',D.FLOAT64,first,second)
        root=expression_node('where',D.FLOAT64,named('flag',D.BOOL),summed,named('fallback',D.FLOAT64))
        cache={};value=expression_reference._evaluate(root,{'flag':ScalarValue(True,D.BOOL),'x':ScalarValue(3.,D.FLOAT64)},cache)
        self.assertEqual(value.value.value,12.);self.assertEqual(calls,[3.])
        names={node.name for node in expression_reference.visited_nodes(cache) if node.operator=='name'}
        self.assertEqual(names,{'flag','x'})
        cache={};value=expression_reference._evaluate(root,{'flag':ScalarValue(False,D.BOOL),'fallback':ScalarValue(7.,D.FLOAT64)},cache)
        self.assertEqual(value.value.value,7.);self.assertEqual(calls,[3.])
        self.assertEqual({node.name for node in expression_reference.visited_nodes(cache) if node.operator=='name'},{'flag','fallback'})
        expression_reference._evaluate(root,{'flag':ScalarValue(True,D.BOOL),'x':ScalarValue(4.,D.FLOAT64)},{})
        self.assertEqual(calls,[3.,4.])


if __name__=='__main__':
    unittest.main()
