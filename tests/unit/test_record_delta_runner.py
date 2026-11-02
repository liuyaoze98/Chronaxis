"""验证新记录流滑动窗口，以手算真值核实际/记录周期及旧入口一致性。"""

from configuration_fixtures import current_fixture
from pathlib import Path
from uuid import uuid4
import unittest
from chronaxis import AnalysisPlan,AnalysisRunner,validate_analysis_plan
from test_window_delta_runner import delta_config
import test_record_runner as raw_cases

ROOT=Path(__file__).resolve().parents[2]/'work/m3-raw-interval-home/delta'

class RecordDeltaTests(unittest.TestCase):
    """真实坐标保持不变，固定周期只随驱动记录推进窗口。"""
    def run_config(self,raw,backend='reference'):
        """用独立自有目录运行并注册关闭。参数: 配置/后端。返回: 结果。异常: 原运行错。"""
        raw.update(config_version=3)
        plan=AnalysisPlan.from_dict(current_fixture(raw))
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        result=AnalysisRunner(backend).run(plan,ROOT/uuid4().hex)
        self.addCleanup(result.close)
        return result

    def test_actual_contracts_and_backends(self):
        """初始化、锁存、窗口到期、缺口、末点与原手算预期相同。"""
        cases=[({},None,[4,12]),({'emit_initial':False},None,[12]),
               ({'retrigger':'once'},None,[4]),
               ({},[(0,4),(1,0),(2,8),(14,8)],[5]),
               ({},[(0,0),(14,5)],[14]),({},[],[]),({},[(12,0),(14,5)],[]),
               ({'emit_initial':False},[(0,0),(2,0),(4,5),(6,5),(8,None),(10,0),(12,5),(14,5)],[])]
        for backend in ('reference','numpy'):
            for changes,values,expected in cases:
                with self.subTest(backend=backend,changes=changes,values=values):
                    raw=delta_config();raw['rules'][0].update(changes)
                    if values is not None:
                        raw['sources'][0]['rows']=[dict(time=f'{t}ns',values={'voltage':v}) for t,v in values]
                    result=self.run_config(raw,backend)
                    self.assertEqual([r.confirmed_ns for r in result.iter_events()],expected)
                    budget=result.spool.budget;result.close();self.assertEqual(budget.ram_bytes,0)

    def test_selected_record_window_and_segment_mean(self):
        """2个固定周期覆盖0、3、9ns；只有第三条满足完整窗，窗口取前后实际记录。"""
        for backend in ('reference','numpy'):
            raw=delta_config()
            raw['sources'][0]['rows']=[dict(time=f'{t}ns',values={'voltage':v}) for t,v in ((0,0),(3,0),(9,5),(14,5))]
            raw['intervals']=dict(default=dict(mode='fixed',value='2ns',driver='voltage'))
            raw['windows']=[dict(name='around',rule='change',anchor='point',pre='2ns',post='2ns')]
            raw['calculations']=[dict(name='mean',scope='segment:around',operation='time_weighted_mean',expr='voltage')]
            result=self.run_config(raw,backend)
            self.assertEqual([r.confirmed_ns for r in result.iter_events()],[9])
            seg,=result.iter_segments();self.assertEqual((seg.start_ns,seg.end_ns),(3,14))
            calculation,=result.iter_calculations();self.assertEqual(calculation.value,2.5)

    def test_fixed_no_eof_period_and_actual_ttl(self):
        """最后记录仍须真实到达；过期造成未知，不能仅凭固定周期较短继续使用。"""
        for backend in ('reference','numpy'):
            raw=delta_config();raw['intervals']=dict(default=dict(mode='fixed',value='2ns',driver='voltage'))
            raw['sources'][0]['rows']=[dict(time=f'{t}ns',values={'voltage':v}) for t,v in ((0,0),(9,5))]
            self.assertEqual(list(self.run_config(raw,backend).iter_events()),[])
            raw['sources'][0]['rows'].insert(1,dict(time='3ns',values={'voltage':0}))
            raw['signals'][0]['valid_for']='4ns'
            self.assertEqual(list(self.run_config(raw,backend).iter_events()),[])

    def test_bounded_window_and_failure_cleanup(self):
        """保留当前窗而非全输入；预算/取消发生在付费前后均释放真实账本。"""
        from unittest.mock import patch
        from chronaxis.execution.record_delta_condition import RecordDeltaCondition
        from chronaxis.execution import record_delta_condition as module
        from chronaxis.results.budget import ResourceBudget
        from chronaxis.results.errors import BudgetExceededError
        raw=delta_config();raw['dataset']['domain']['end']='100ns'
        raw['sources'][0]['rows']=[dict(time=f'{t}ns',values={'voltage':t%7}) for t in range(101)]
        lengths=[];original=RecordDeltaCondition.update
        def measured(owner,*args,**kwargs):
            """在真实推进后观测当前保留数。参数: 原调用。返回: 原结果。异常: 原错。"""
            result=original(owner,*args,**kwargs);lengths.append(len(owner._spans));return result
        with patch.object(RecordDeltaCondition,'update',measured):
            self.run_config(raw).close()
        self.assertLessEqual(max(lengths),5)
        init=ResourceBudget.__init__
        for name in ('_reserve_owned_ram','_release_owned_ram'):
            for after in (False,True):
                for slot in ('_span_cost','_work_cost','_clock_cost'):
                    budgets=[];triggered=[];operation=getattr(module,name)
                    def capture(owner,*args,**kwargs):
                        """保存账本用于失败后核零。参数: 原调用。返回: None。异常: 原错。"""
                        init(owner,*args,**kwargs);budgets.append(owner)
                    def fault(owner,amount,target):
                        """仅一次取消或预算失败。参数: 实际申请。返回: 原结果。异常: 注入故障。"""
                        if target==slot and amount and not triggered:
                            triggered.append(True)
                            if after: operation(owner,amount,target)
                            raise (KeyboardInterrupt if after else BudgetExceededError)('synthetic delta fault')
                        return operation(owner,amount,target)
                    raw=delta_config();raw['intervals']=dict(default=dict(mode='fixed',value='2ns',driver='voltage'))
                    with self.subTest(name=name,after=after,slot=slot),patch.object(ResourceBudget,'__init__',capture),patch.object(module,name,fault):
                        with self.assertRaises((KeyboardInterrupt,BudgetExceededError)):
                            self.run_config(raw)
                    self.assertTrue(triggered)
                    self.assertTrue(budgets)
                    self.assertTrue(all(b.ram_bytes==0 for b in budgets))

class RawRecordDeltaTests(unittest.TestCase):
    """相同帧以三种格式存储时使用同一计算入口。"""
    setUp=raw_cases.RecordRunnerTests.setUp
    asc=raw_cases.RecordRunnerTests.asc
    csv=raw_cases.RecordRunnerTests.csv
    blf=raw_cases.RecordRunnerTests.blf
    fixtures=raw_cases.RecordRunnerTests.fixtures
    plan=raw_cases.RecordRunnerTests.plan
    def test_formats_modes_backends(self):
        """0→0.12→0.30三帧电流10→12→14；两周期变化4在最后触发。"""
        for kind,path in self.fixtures().items():
            for backend in ('reference','numpy'):
                for mode in ('actual','fixed','dbc'):
                    def edit(raw):
                        """只请求变化事件。参数: raw。返回: None。异常: 无。"""
                        raw['calculations']=[]
                        raw['rules']=[dict(name='delta',rule_type='window_delta',signal='current',window='0.2s',direction='rise',threshold=4,emit_initial=True)]
                    with self.subTest(kind=kind,backend=backend,mode=mode):
                        with AnalysisRunner(backend).run(self.plan(kind,path,mode,edit),self.root/uuid4().hex) as result:
                            rows=list(result.iter_events())
                            self.assertEqual(len(rows),1)
                            self.assertAlmostEqual(rows[0].confirmed_ns/1e9,.3,places=5)
