"""从宿主注册到公开Runner核对逐点函数、网格状态、后端能力与资源责任。

所有回调都在测试的宿主进程显式创建，配置只引用名字。小型参考/NumPy实现
分别跑自己的内核。故障时核对取消、关闭和共享预算，不把异常当作有效缺省值。
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.numeric_numpy import NumericArray, _output
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.extensions import (ValueSpec, FunctionSpec, ReductionSpec, TransformSpec, ExtensionRegistry,
                                  builtin_function_specs,using_extension_budget)
from chronaxis.extension_runtime import HostedReduction
from chronaxis.results.budget import ResourceBudget


PORT = ValueSpec(D.FLOAT64,'V')


def point_spec(log,version='v1',*,array=True):
    """创建显式定标公式 y=2x。参数: 调用记录、版本和数组能力。返回: FunctionSpec。异常: 声明错误。"""
    def reference(args, resources):
        """参数: 当前标量tuple与预算。返回: 倍率2的电压。异常: 预算超额。"""
        resources.reserve(32)
        log.append('ref')
        return ScalarValue(args[0].value*2.,D.FLOAT64)
    def numpy(args, resources):
        """参数: 有效样本数组tuple与预算。返回: 完整数组列。异常: 预算或形状错误。"""
        resources.reserve(32*len(args[0].values))
        log.append('array')
        return _output(D.FLOAT64,np.multiply(args[0].values,2.),np.zeros(len(args[0].values),dtype=np.uint16))
    return FunctionSpec('calibrate','%s'%version,(PORT,),PORT,reference,numpy if array else None)


def config():
    """建立半开2秒会话，真实样本1000/2000mV。参数: 无。返回: v4配置。异常: 无。"""
    return dict(config_version=4,dataset=dict(name='plugins',domain=dict(start='0s',end='2s')),
                sources=[dict(name='s',source_type='memory',rows=[dict(time=f'{i}s',values={'v':float(i+1)*1000})
                                                                   for i in range(3)])],
                signals=[dict(name='v',field='v',dtype='float64',unit='mV',valid_for='3s')],
                calculations=[dict(name='reading',operation='select',expr='calibrate(v)')])


class GridState:
    """每次运行维护独立网格计数，用状态和窗口有效电压共同形成输出。"""
    def __init__(self,resources,log,fail):
        """参数: 本次预算、外部测试日志及故障标志。返回: 状态。异常: 首次存储预约失败。"""
        self.resources,self.log,self.fail,self.n = resources,log,fail,0
        resources.reserve(80)
        log.append(('new',resources._budget))

    def advance(self,time_ns,window_ns,values,weights_ns):
        """参数: 真实网格、窗口和从早到晚的有效区间。返回: 加当前网格序号的电压。异常: 可注入取消。"""
        self.n += 1
        self.log.append(('advance',time_ns,window_ns))
        if self.fail:
            raise KeyboardInterrupt('test grid cancellation')
        if isinstance(values,NumericArray):
            value = np.average(values.values,weights=weights_ns).item()
        else:
            value = sum(v.value*w for v,w in zip(values,weights_ns))/sum(weights_ns)
        return ScalarValue(value+self.n,D.FLOAT64)

    def cancel(self):
        """参数: 无。返回: None。异常: 无。"""
        self.log.append(('cancel',))

    def close(self):
        """参数: 无。返回: None。异常: 借用资源协议错误。"""
        self.resources.release(80)
        self.log.append(('close',))


class HostExtensionTests(unittest.TestCase):
    """核对受信任宿主调用边界与版本隔离，不对Python宿主声称沙箱。"""

    def test_plan_uses_name_capability_identity_and_no_static_callback(self):
        """构建、校验只读注册；版本改变身份，错注册及不支持后端提前拒绝。

        参数: 无。返回: None。异常: 越权加载、未检查身份或错误后端回退则失败。
        """
        log = []
        registry = ExtensionRegistry(functions=(point_spec(log),))
        alternative = ExtensionRegistry(functions=(point_spec(log,'v2'),))
        raw = config()
        # 不可把纯字面量实参的宿主回调当内置clip静态边界运行。
        raw['calculations'].append(dict(name='bounds',operation='sample_mean',expr='clip(v,calibrate(0.),quantity(5.,"V"))'))
        first = AnalysisPlan.from_dict(raw,extensions=registry)
        other = AnalysisPlan.from_dict(raw,extensions=alternative)
        self.assertNotEqual(first.calculations[0].signal.identity,other.calculations[0].signal.identity)
        self.assertEqual(log,[])
        with self.assertRaises(ValueError):
            AnalysisPlan.from_dict(raw)
        with self.assertRaises((TypeError,ValueError,RuntimeError)):
            AnalysisRunner(extensions=alternative).validate(first)
        # 只有参考实现时，不接受NumPy运行；未注册的配置字段不能声明导入路径。
        reference_only = ExtensionRegistry(functions=(point_spec(log,array=False),))
        raw['execution'] = dict(backend='numpy')
        with self.assertRaises((ValueError,RuntimeError)):
            plan = AnalysisPlan.from_dict(raw,extensions=reference_only)
            AnalysisRunner('numpy',extensions=reference_only).run(plan)
        raw['extensions'] = {'module':'untrusted_module'}
        with self.assertRaises(ValueError):
            AnalysisPlan.from_dict(raw,extensions=registry)

    def test_point_function_both_backends_and_units(self):
        """1000和2000mV送入V端口后分别输出2和4V，两后端不得互相回退。

        参数: 无。返回: None。异常: 误用输入尺度、回调后端或残留RAM时失败。
        """
        for backend in ('reference','numpy'):
            log = []
            registry = ExtensionRegistry(functions=(point_spec(log),))
            with self.subTest(backend=backend),TemporaryDirectory(dir='work') as folder:
                raw = config()
                raw['execution'] = dict(backend=backend)
                plan = AnalysisPlan.from_dict(raw,extensions=registry)
                self.assertFalse(log)
                with AnalysisRunner(backend,extensions=registry).run(plan,Path(folder)/'run') as result:
                    rows = list(result.iter_selections())
                    self.assertEqual([(r.value,r.unit) for r in rows],[(2.,'V'),(4.,'V')])
                    budget = result.spool.budget
                self.assertEqual(budget.ram_bytes,0)
                self.assertEqual(set(log),{'ref' if backend=='reference' else 'array'})

    def test_point_failure_quality_and_stable_builtin_contracts(self):
        """无效行不运行回调，异常返回时清理其动态费用；各版本能列出实际内置能力。

        参数: 无。返回: None。异常: 漏报无效原因、隐藏回调错误或语法目录扩权时失败。
        """
        from chronaxis.extension_runtime import point_call
        catalog = builtin_function_specs()
        with self.assertRaises(ValueError):
            builtin_function_specs(3)
        self.assertEqual((catalog['where'].history_ns,catalog['where'].backends),(0,('reference','numpy')))
        self.assertIn('切换',catalog['where'].updates)
        self.assertEqual(catalog['bit_test'].signature,'bit_test(x,bit)')
        with self.assertRaises((ValueError,TypeError)):
            point_spec([],version='')
        def invalid(args,resources):
            """参数: 有效值与账本。返回: 故意错误dtype。异常: 来自调用端的显式类型拒绝。"""
            resources.reserve(64)
            return ScalarValue(True,D.BOOL)
        spec = FunctionSpec('mistyped','1',(PORT,),PORT,invalid,invalid)
        budget = ResourceBudget(1024)
        budget.reserve_ram(32)
        with using_extension_budget(budget):
            self.assertEqual(point_call(spec,'reference',(ScalarValue(None,D.FLOAT64,False,Q.STALE),)).quality,Q.STALE)
            with self.assertRaises(TypeError):
                point_call(spec,'reference',(ScalarValue(2.,D.FLOAT64),))
            with self.assertRaises(TypeError):
                point_call(spec,'numpy',(_output(D.FLOAT64,np.array([2.]),np.zeros(1,dtype=np.uint16)),))
        self.assertEqual(budget.ram_bytes,32)

    def test_stateful_grid_is_only_created_on_request_and_closed_on_cancel(self):
        """声明但无消费时不建状态；窗口请求按版本推进，取消后关闭并退净费用。

        参数: 无。返回: None。异常: 状态时钟错误、取消吞掉或预算未释放则失败。
        """
        for backend in ('reference','numpy'):
            for scenario in ('unused','normal','cancel'):
                log = []
                def factory(resources):
                    """参数: 本次状态资源。返回: 测试用网格对象。异常: 资源预约失败。"""
                    return GridState(resources,log,scenario=='cancel')
                spec = TransformSpec('grid_counter','1',PORT,PORT,factory,factory,state_bytes=256,history_ns=10**9)
                registry = ExtensionRegistry(transforms=(spec,))
                raw = config()
                raw['transforms'] = [dict(name='grid',operation='grid_counter',expr='v',window='1s',step='1s')]
                raw['calculations'][0]['expr'] = 'v' if scenario=='unused' else 'grid'
                raw['execution'] = dict(backend=backend)
                with self.subTest(backend=backend,scenario=scenario),TemporaryDirectory(dir='work') as folder:
                    plan = AnalysisPlan.from_dict(raw,extensions=registry)
                    runner = AnalysisRunner(backend,extensions=registry)
                    self.assertFalse(log)
                    if scenario == 'cancel':
                        with self.assertRaises(KeyboardInterrupt):
                            runner.run(plan,Path(folder)/'run')
                        self.assertEqual([e[0] for e in log][-2:],['cancel','close'])
                        self.assertEqual(log[0][1].ram_bytes,0)
                    else:
                        with runner.run(plan,Path(folder)/'run') as result:
                            rows = list(result.iter_selections())
                            budget = result.spool.budget
                        if scenario == 'unused':
                            self.assertFalse(log)
                        else:
                            self.assertEqual(log[-1],('close',))
                            self.assertEqual([r.value for r in rows if r.valid],[2.])
                        self.assertEqual(budget.ram_bytes,0)

    def test_scalar_reduction_merge_contract_and_ledger(self):
        """归约的consume、merge和finalize分别接收已选值、兼容状态和一次结算。

        参数: 无。返回: None。异常: 未声明的合并、类型或生命周期失约时失败。
        """
        class Sum:
            """仅为本测试持有一个标量。"""
            def __init__(self,res):
                """参数: 宿主预算。返回: 归约对象。异常: 无。"""
                self.n = 0.
            def consume(self,values):
                """参数: 一批已选值。返回: None。异常: 类型不符。"""
                self.n += sum(v.value for v in values)
            def merge(self,other):
                """参数: 同型对象。返回: None。异常: 无。"""
                self.n += other.n
            def finalize(self):
                """参数: 无。返回: 标量和。异常: 无。"""
                return ScalarValue(self.n,D.FLOAT64)
            def close(self):
                """参数: 无。返回: None。异常: 无。"""
            def cancel(self):
                """参数: 无。返回: None。异常: 无。"""
        spec = ReductionSpec('acme_sum','1',PORT,PORT,Sum,state_bytes=128,mergeable=True)
        budget = ResourceBudget(1024)
        a,b = (HostedReduction(spec,'reference',budget) for _ in range(2))
        try:
            a.consume((ScalarValue(3.,D.FLOAT64),))
            b.consume((ScalarValue(7.,D.FLOAT64),))
            a.merge(b)
            self.assertEqual(a.finalize().value,10.)
            self.assertEqual(b.finalize().value,7.)
        finally:
            a.close()
            b.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_grid_extension_receives_actual_or_prorated_dbc_weight(self):
        """同一宿主均值在0.20秒按真实时长得18，按固定或DBC的100ms周期得130/9。

        参数: 无。返回: None。异常: 时间轴改写、权重取整或能力范围失约即失败。
        """
        from test_record_sample_observation_tail import SampleObservationTailTests
        files = SampleObservationTailTests()
        files.setUp()
        self.addCleanup(files.doCleanups)
        dbc = files.root/'meter.dbc'
        dbc.write_text(dbc.read_text(encoding='utf-8').replace('BO_ 256 1000;', 'BO_ 256 100;'),encoding='utf-8')
        w = ValueSpec(D.FLOAT64,'W')
        class Weighted:
            """向两种真实后端分别应用本格的已折算权重。"""
            def __init__(self,res):
                """参数: 宿主资源。返回: 状态。异常: 无。"""
            def advance(self,t,window,values,weights):
                """参数: 网格、窗口、数据和所选纳秒权重。返回: 加权平均。异常: 空输入。"""
                mean = (np.average(values.values,weights=weights).item() if isinstance(values,NumericArray)
                        else sum(v.value * w for v,w in zip(values,weights))/sum(weights))
                return ScalarValue(mean,D.FLOAT64)
            def close(self):
                """参数: 无。返回: None。异常: 无。"""
            def cancel(self):
                """参数: 无。返回: None。异常: 无。"""
        spec = TransformSpec('weighted','1',w,w,Weighted,Weighted,history_ns=10**8)
        registry = ExtensionRegistry(transforms=(spec,))
        for backend in ('reference','numpy'):
            for mode in ('actual','fixed','dbc'):
                raw = files.config(values=((0,10),(.12,20),(.30,40),(.42,5)),end=.6,age='1s')
                raw['config_version'] = 4
                raw['signals'][0]['dtype'] = 'float64'
                clock = {'mode':mode}
                if mode != 'actual':
                    clock['driver'] = 'power'
                if mode == 'fixed':
                    clock['value'] = '0.1s'
                raw['transforms'] = [dict(name='series',operation='weighted',expr='power',window='0.1s',
                                          step='0.1s',interval=clock)]
                raw['calculations'] = [dict(name='out',operation='select',expr='series')]
                raw['execution'] = {'backend':backend}
                with self.subTest(backend=backend,mode=mode),TemporaryDirectory(dir=files.root) as folder:
                    plan = AnalysisPlan.from_dict(raw,base_dir=files.root,extensions=registry)
                    with AnalysisRunner(backend,extensions=registry).run(plan,Path(folder)/'run') as result:
                        row, = (r for r in result.iter_selections() if r.time_ns==200_000_000)
                        self.assertAlmostEqual(row.value,18. if mode=='actual' else 130/9)
                if mode == 'fixed':
                    restricted = ExtensionRegistry(transforms=(TransformSpec('weighted','2',w,w,Weighted,Weighted,
                        history_ns=10**8,interval_modes=('actual',)),))
                    with self.assertRaisesRegex(ValueError,'不支持'):
                        AnalysisPlan.from_dict(raw,base_dir=files.root,extensions=restricted)
