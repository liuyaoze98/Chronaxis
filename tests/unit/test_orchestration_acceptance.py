"""D1候选的纵向验收草稿：执行入口只打开实际需要的来源。

使用手算小数据核对积分、无观测、选择、事件窗口和NumPy宿主回调；文件暂存
在项目专用工作目录。需先应用父会话D1候选再作为正式专项运行，目前未执行。
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from workspace_fixtures import TemporaryDirectory
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.numeric_numpy import _output
from chronaxis.core.scalar import ScalarValue
from chronaxis.core.types import SignalDType as D
from chronaxis.execution import record_session_calculations as sessions
from chronaxis.extensions import FunctionSpec, ReductionSpec, ValueSpec, ExtensionRegistry


def config(values=(100.,100.,100.)):
    """构造2秒分析和一个未用来源。参数: 3个功率值。返回: 独立配置。异常: 无。"""
    return dict(config_version=4,dataset=dict(name='orchestration',domain=dict(start='0s',end='2s')),
                sources=[dict(name='used',source_type='memory',rows=[dict(time=f'{i}s',values=dict(p=value)) for i,value in enumerate(values)]),
                         dict(name='unused',source_type='memory',rows=[dict(time='0s',values=dict(other=9.))])],
                signals=[dict(name='power',source='used',field='p',dtype='float64',unit='W',valid_for='3s'),
                         dict(name='noise',source='unused',field='other',dtype='float64',unit='W',valid_for='3s')],
                calculations=[dict(name='energy',operation='integral',expr='power',unit='J')])


class OrchestrationAcceptanceTests(unittest.TestCase):
    """按公开Runner核对结果和真正创建的来源，不依赖辅助方法的名称。"""

    def run_case(self, raw, registry=None, backend='numpy'):
        """执行并收集已封存业务行。参数: 配置、可选注册。返回: 四类结果。异常: 产品原错。"""
        opened=[]
        original=sessions.RecordSourceCursor
        def cursor(plan, source, *args, **kwargs):
            """记录实际来源创建。参数: 原构造参数。返回: 真实游标。异常: 无关来源被打开。"""
            if source.name != 'used':
                raise AssertionError('未用来源不能参与执行')
            opened.append(source.name)
            return original(plan,source,*args,**kwargs)
        plan=AnalysisPlan.from_dict(deepcopy(raw),extensions=registry)
        with TemporaryDirectory(dir='work',prefix='d1-orchestration-') as directory:
            with patch.object(sessions,'RecordSourceCursor',cursor):
                with AnalysisRunner(backend,extensions=registry).run(plan,Path(directory)/'run') as result:
                    values=tuple(result.iter_calculations())
                    selections=tuple(result.iter_selections())
                    events=tuple(result.iter_events())
                    segments=tuple(result.iter_segments())
                    budget=result.spool.budget
            self.assertEqual(budget.ram_bytes,0)
        self.assertEqual(opened,['used'])
        return values,selections,events,segments

    def test_integral_with_unused_source(self):
        """100W保持两秒得到200J。参数: 无。返回: 无。异常: 数值、资源或输入断言。"""
        values,selections,events,segments=self.run_case(config())
        self.assertEqual([(r.value,r.unit,r.status) for r in values],[(200.,'J','complete')])
        self.assertEqual((selections,events,segments),((),(),()))

    def test_reference_integral_uses_same_requested_input(self):
        """独立参考后端也只开必要来源，积分为200J；编排不固定到NumPy。"""
        values,selections,events,segments=self.run_case(config(),backend='reference')
        self.assertEqual([(r.value,r.unit,r.status) for r in values],[(200.,'J','complete')])
        self.assertEqual((selections,events,segments),((),(),()))

    def test_no_observation_has_no_fabricated_energy(self):
        """必要来源空时返回无观测，不能借未用来源取得时域。参数: 无。返回: 无。异常: 断言。"""
        raw=config(())
        raw['dataset'].pop('domain')
        values,selections,events,segments=self.run_case(raw)
        self.assertEqual([(r.value,r.status,r.reason) for r in values],[(None,'indeterminate','no_observation')])
        self.assertEqual((selections,events,segments),((),(),()))

    def test_select_keeps_real_samples(self):
        """半开0至2秒只选0、1秒两条。参数: 无。返回: 无。异常: 选择边界断言。"""
        raw=config((10.,20.,30.))
        raw['calculations']=[dict(name='samples',operation='select',expr='power')]
        values,selections,events,segments=self.run_case(raw)
        self.assertEqual([(r.time_ns,r.value) for r in selections],[(0,10.),(10**9,20.)])
        self.assertEqual((values,events,segments),((),(),()))

    def test_event_window_routes_to_requested_scope(self):
        """第1秒边沿选0至2秒窗口，只有后半段有100W，得到100J。参数: 无。返回: 无。异常: 断言。"""
        raw=config((0.,100.,0.))
        raw['rules']=[dict(name='edge',rule_type='rising_edge',condition='power > 0',emit_initial=False)]
        raw['windows']=[dict(name='around',rule='edge',anchor='point',pre='1s',post='1s',merge='none')]
        raw['calculations']=[dict(name='energy',operation='integral',expr='power',scope=dict(window='around'),unit='J')]
        values,selections,events,segments=self.run_case(raw)
        self.assertEqual(len(events),1)
        self.assertEqual([(r.start_ns,r.end_ns) for r in segments],[(0,2*10**9)])
        self.assertEqual([(r.value,r.parent_id) for r in values],[(100.,segments[0].segment_id)])
        self.assertEqual(selections,())

    def test_host_function_uses_selected_backend_and_required_source(self):
        """宿主将功率加倍，仍只开必要来源且积分为400J。参数: 无。返回: 无。异常: 断言。"""
        called=[]
        def reference(args,resources):
            """参数: 标量与预算。返回: 倍率2结果。异常: 无。"""
            called.append('reference')
            return ScalarValue(args[0].value*2,D.FLOAT64)
        def numpy_callback(args,resources):
            """参数: 有效列与预算。返回: 倍率2列。异常: 预算错误。"""
            resources.reserve(32)
            called.append('numpy')
            return _output(D.FLOAT64,args[0].values*2,np.zeros(len(args[0].values),dtype=np.uint16))
        port=ValueSpec(D.FLOAT64,'W')
        registry=ExtensionRegistry(functions=(FunctionSpec('twice','v1',(port,),port,reference,numpy_callback),))
        raw=config()
        raw['calculations'][0]['expr']='twice(power)'
        values,_,_,_=self.run_case(raw,registry)
        self.assertEqual([r.value for r in values],[400.])
        self.assertEqual(set(called),{'numpy'})
    def test_hosted_reduction_is_prepared_and_closed(self):
        """宿主归约映射进入算子准备阶段，真实更新1W和2W累加为3W。"""
        log=[]
        class Total:
            """只保存本次两个有效样本的和，并记录实际关闭。"""
            def __init__(self,resources,backend):
                """参数: 自有资源与后端。返回: 归约状态。异常: 预算错。"""
                self.resources,self.backend,self.total=resources,backend,0.
                resources.reserve(64);log.append(('open',backend))
            def consume(self,values):
                """参数: 当前后端已选输入。返回: None。异常: 类型/数值错误。"""
                self.total+=sum(value.value for value in values) if self.backend=='reference' else float(values.values.sum())
                log.append(('consume',self.backend))
            def finalize(self):
                """参数: 无。返回: W标量总和。异常: 无。"""
                return ScalarValue(self.total,D.FLOAT64)
            def cancel(self):
                """参数: 无。返回: None。异常: 无。"""
                log.append(('cancel',self.backend))
            def close(self):
                """参数: 无。返回: None。异常: 原资源释放错。"""
                self.resources.release(64);log.append(('closed',self.backend))
        port=ValueSpec(D.FLOAT64,'W')
        registry=ExtensionRegistry(reductions=(ReductionSpec('custom_total','v1',port,port,
            reference=lambda resources:Total(resources,'reference'),
            numpy=lambda resources:Total(resources,'numpy'),state_bytes=128),))
        raw=config((1.,2.,3.));raw['calculations']=[dict(name='total',operation='custom_total',expr='power',unit='W')]
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend):
                log.clear();values,_,_,_=self.run_case(raw,registry,backend)
                self.assertEqual([(r.value,r.unit) for r in values],[(3.,'W')])
                self.assertEqual([event for event in log if event[0]=='open'],[('open',backend)])
                self.assertEqual([event for event in log if event[0]=='closed'],[('closed',backend)])

    def test_operator_constructor_failure_reclaims_prepared_inputs(self):
        """输入已准备后算子构造失败，原异常可追溯且所有实际来源关闭、账本归零。"""
        cursors=[];original=sessions.RecordSourceCursor;failure=OSError('operator construction fault')
        def cursor(plan,source,*args,**kwargs):
            """参数: 原构造参数。返回: 实际游标。异常: 来源或构造错误。"""
            self.assertEqual(source.name,'used')
            value=original(plan,source,*args,**kwargs);cursors.append(value);return value
        with TemporaryDirectory(dir='work',prefix='d1-failure-') as directory:
            plan=AnalysisPlan.from_dict(config())
            with patch.object(sessions,'RecordSourceCursor',cursor),patch.object(sessions,'RecordIntegral',side_effect=failure):
                try:
                    AnalysisRunner('numpy').run(plan,Path(directory)/'run')
                except BaseException as error:
                    chain=[]
                    while error is not None and all(error is not item for item in chain):
                        chain.append(error);error=error.__cause__
                    self.assertTrue(any(item is failure for item in chain))
                else:
                    self.fail('预期构造故障没有发生')
            self.assertEqual(len(cursors),1)
            self.assertTrue(cursors[0]._closed)
            self.assertEqual(cursors[0]._budget.ram_bytes,0)
