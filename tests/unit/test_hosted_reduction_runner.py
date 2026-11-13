"""通过公开配置核验宿主归约真实输入选择、状态范围、后端、取消和不加载插件的结果读取。"""

from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest
from chronaxis import AnalysisPlan,AnalysisRunner,PlanValidationError
from chronaxis.extensions import ExtensionRegistry,ReductionSpec,ValueSpec
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.numeric_numpy import NumericArray
from chronaxis.core.types import SignalDType as D
from chronaxis.results.codec import encode_row,decode_row
from chronaxis.results.summary import SummaryHostedCalculationRow


class ExampleReduction:
    """测试宿主记录状态生命周期，按不同后端的真实输入计算总和。"""

    def __init__(self,resources,backend,log,interrupt):
        """参数: 独立资源、后端、测试记录和可选取消。返回: 新状态。异常: 预算失败。"""
        self.resources,self.backend,self.log,self.interrupt=resources,backend,log,interrupt
        self.total=0.
        resources.reserve(256)
        log.append('open')

    def consume(self,values):
        """参数: 参考标量元组或 NumPy 已选列。返回: None。异常: 注入取消或错误后端。"""
        if self.interrupt:
            raise KeyboardInterrupt('host-stop')
        if self.backend=='reference':
            assert type(values) is tuple and all(v.valid and v.dtype is D.FLOAT64 for v in values)
            self.total+=sum(v.value for v in values)
        else:
            assert type(values) is NumericArray and values.valid.all() and values.dtype is D.FLOAT64
            self.total+=float(values.values.sum())
        self.log.append('consume')

    def finalize(self):
        """参数: 无。返回: 已声明的浮点标量。异常: 无。"""
        self.log.append('finish')
        return ScalarValue(self.total,D.FLOAT64)

    def cancel(self):
        """参数: 无。返回: None。异常: 无。"""
        self.log.append('cancel')

    def close(self):
        """参数: 无。返回: None。异常: 资源释放错误。"""
        self.resources.release(256)
        self.log.append('closed')


class HostedReductionRunnerTests(unittest.TestCase):
    """宿主负责 A→A 的归约语义，配置根按 mV→V 输入、A→mA 结果分别换算。"""

    def registry(self,log,interrupt=False):
        """建立仅本次宿主可用的注册。参数: 状态日志与故障。返回: 不可变注册。异常: 接口错误。"""
        spec=ReductionSpec('custom_total','1.2',ValueSpec(D.FLOAT64,'V'),ValueSpec(D.FLOAT64,'A'),
            reference=lambda r:ExampleReduction(r,'reference',log,interrupt),
            numpy=lambda r:ExampleReduction(r,'numpy',log,interrupt),state_bytes=512)
        return ExtensionRegistry(reductions=(spec,))

    def config(self):
        """三类父范围读取真实更新，只有状态为真的 2、3、5V 参与。参数: 无。返回: 原生配置。异常: 无。"""
        rows=[dict(time=f'{i}s',values={'p':value*1000.,'g':gate}) for i,(value,gate) in
              enumerate(((1,False),(2,True),(3,True),(4,False),(5,True),(6,False),(7,False)))]
        rows.insert(2,dict(time='1.5s',values={'g':True}))
        return dict(config_version=4,dataset=dict(name='host_sum',domain=dict(start='0s',end='6s')),
            sources=[dict(name='table',source_type='memory',rows=rows)],
            signals=[dict(name='power',field='p',unit='mV',dtype='float64',valid_for='3s'),
                     dict(name='gate',field='g',unit='1',dtype='bool',valid_for='3s')],
            rules=[dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='gate',minimum_duration='0.1s')],
            windows=[dict(name='parts',rule='active')],
            calculations=[dict(name=n,scope=s,operation='custom_total',expr='power',condition='gate',unit='mA') for n,s in
                          (('all','session'),('each',{'rule':'active'}),('window_sum',{'window':'parts'}))],
            outputs=dict(tables='jsonl'))

    def test_real_scopes_and_version_16(self):
        """各后端只消费所选真实点；两个事件与两个片段分别归约并可离线解码。参数: 无。返回: None。异常: 数值、版本或资源错误。"""
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend),TemporaryDirectory(dir='work',prefix='host-reduce-') as folder:
                log=[]
                plan=AnalysisPlan.from_dict(self.config(),extensions=self.registry(log))
                self.assertFalse(log)
                with AnalysisRunner(backend,extensions=plan.extensions).run(plan,work_dir=Path(folder)/'run') as result:
                    rows=tuple(result.iter_calculations())
                    self.assertEqual([(r.value,r.unit) for r in rows if r.calculation_id=='all'],[(10000.,'mA')])
                    self.assertEqual(sorted(r.value for r in rows if r.calculation_id=='each'),[5000.,5000.])
                    self.assertEqual(sorted(r.value for r in rows if r.calculation_id=='window_sum'),[5000.,5000.])
                    self.assertTrue(all(type(r) is SummaryHostedCalculationRow and r.extension_version=='1.2' for r in rows))
                    payload=encode_row(rows[0],65536)
                    self.assertEqual(decode_row(payload,65536),rows[0])
                    self.assertEqual(result.run_manifest['row_schema_versions']['calculations'],16)
                    result.write(Path(folder)/'published')
                self.assertEqual(log.count('open'),log.count('closed'))
                self.assertNotIn('cancel',log)

    def test_cancel_and_unused_registered_factory(self):
        """未请求不建状态，真实拒绝后端或取消时不输出前缀结果。参数: 无。返回: None。异常: 故障未传播或清理失败。"""
        raw=self.config(); log=[];registry=self.registry(log,interrupt=True)
        with TemporaryDirectory(dir='work',prefix='host-stop-') as folder:
            plan=AnalysisPlan.from_dict(raw,extensions=registry)
            with self.assertRaises(KeyboardInterrupt):
                AnalysisRunner('reference',extensions=registry).run(plan,work_dir=Path(folder)/'fail')
            self.assertEqual(log.count('cancel'),log.count('open'))
            self.assertEqual(log.count('closed'),log.count('open'))
            raw['calculations']=[]
            log.clear()
            with AnalysisRunner(extensions=registry).run(AnalysisPlan.from_dict(raw,extensions=registry),work_dir=Path(folder)/'unused'):
                pass
            self.assertFalse(log)
        raw=self.config()
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(raw)

    def test_known_empty_missing_and_mixed_csv_versions(self):
        """没有选中真实样本时不调用finalize，缺值按report/strict传递；旧行和宿主版本可混合发布。

        参数: 无。返回: None。异常: 伪零、伪完整、重复回调、CSV字段错误或版本不准确。
        """
        raw=self.config();raw['outputs']={'tables':'csv'}
        raw['calculations']=[dict(name='empty',operation='custom_total',expr='power',condition='False'),
            dict(name='known',operation='custom_total',expr='power',condition='gate'),
            dict(name='strict',operation='custom_total',expr='power',condition='gate',partial_policy='strict'),
            dict(name='plain',operation='sample_mean',expr='power'),
            dict(name='threshold',operation='time_weighted_mean',expr='power',minimum_coverage=.1)]
        raw['sources'][0]['rows'][3]['values']['p']=None
        for backend in ('reference','numpy'):
            with TemporaryDirectory(dir='work',prefix='host-mixed-') as folder:
                log=[];registry=self.registry(log)
                plan=AnalysisPlan.from_dict(raw,extensions=registry)
                with AnalysisRunner(backend,extensions=registry).run(plan,work_dir=Path(folder)/'run') as result:
                    rows={r.calculation_id:r for r in result.iter_calculations()}
                    self.assertIsNone(rows['empty'].value)
                    self.assertIsNone(rows['strict'].value)
                    self.assertEqual((rows['known'].status,rows['known'].value),('partial',7.))
                    self.assertEqual(result.run_manifest['row_schema_versions']['calculations'],[7,10,16])
                    result.write(Path(folder)/'out')
                self.assertEqual((log.count('open'),log.count('finish'),log.count('closed')),(3,2,3))

    def test_reject_unsupported_params_incompatible_port_and_missing_backend(self):
        """注册输入和参数在读来源前核实，缺后端不能回退。参数: 无。返回: None。异常: 错误请求未拒绝。"""
        from chronaxis import validate_analysis_plan
        log=[]
        for extra in ({'q':.5},{'ddof':1},{'method':'zoh'},{'unit':'s'},{'expr':'gate'}):
            raw=self.config()
            raw['calculations'][0].update(extra)
            with self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(raw,extensions=self.registry(log))
        spec=ReductionSpec('custom_total','v1',ValueSpec(D.FLOAT64,'V'),ValueSpec(D.FLOAT64,'A'),
                           reference=lambda r:ExampleReduction(r,'reference',log,False))
        registry=ExtensionRegistry(reductions=(spec,))
        plan=AnalysisPlan.from_dict(self.config(),extensions=registry)
        self.assertFalse(validate_analysis_plan(plan).execution_ready)
        self.assertFalse(log)
