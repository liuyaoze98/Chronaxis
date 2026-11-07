"""通过公共计划和AnalysisRunner验证开始/结束活动、超时、统计与清理。

合成内存/CSV输入给出手算真值，覆盖两个后端、不同批次、独立结束信号的
依赖/有效性、跨文件连续与输出发布。所有文件写入E盘work，不读取历史项目。
"""

from configuration_fixtures import current_fixture

import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, AnalysisRunner, validate_analysis_plan, PlanValidationError
from chronaxis.core.start_end import StartEndDetector
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter

ROOT=Path(__file__).absolute().parents[2]


def start_end_config():
    """构造两次正常结束和一次超时。参数: 无。返回: dict。异常: 无。"""
    points=[(0,1,0,10),(2,0,1,20),(3,0,0,30),(4,1,0,40),(6,1,0,60),
            (9,1,0,90),(10,0,0,100),(11,1,0,110),(14,0,1,140),(16,0,0,160)]
    return dict(config_version=4,
        dataset=dict(name='example',entity='device',session='session',domain=dict(start='0ns',end='16ns')),
        sources=[dict(name='input',source_type='memory',time=dict(time_type='relative',unit='ns',origin='clock'),
            rows=[dict(time=f'{t}ns',values=dict(begin=b,done=e,value=v)) for t,b,e,v in points])],
        signals=[dict(name=k,source='input',field=k,dtype='int64',unit='1',valid_for='20ns') for k in ('begin','done','value')],
        rules=[dict(name='cycle',rule_type='start_end',start_condition='begin > 0',end_condition='done > 0',timeout='5ns')],
        windows=[dict(name='window',rule='cycle',anchor='activity',pre='0ns',post='0ns')],
        calculations=[dict(name='event_average',scope='event:cycle',operation='time_weighted_mean',expr='value'),
                 dict(name='segment_average',scope='segment:window',operation='time_weighted_mean',expr='value')],
        execution=dict(batch_rows=2,result_buffer_rows=1,memory_budget_bytes=256*1024**2),
        metadata=dict(device_label='home',data_kind='synthetic'))


class StartEndRunnerTests(unittest.TestCase):
    """真实入口结果与手算对照，逐次关闭资源，不引用被测核生成预期。"""

    def run_config(self,raw):
        """运行唯一工作目录并登记关闭。参数: raw配置。返回: AnalysisResult。异常: 原执行错误。"""
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),work_dir=ROOT/'work/m3-migrate-home-20261022/public'/uuid4().hex)
        self.addCleanup(result.close)
        return result

    def intervals(self,result):
        """提取可读时间/状态。参数: result。返回: list。异常: 原读取错误。"""
        return [(r.start_ns,r.end_ns,r.status) for r in result.iter_events()]

    def test_schema_and_static_contract(self):
        """公开schema和静态计划都接收新规则与双依赖。参数: 无。返回: None。异常: 断言失败。"""
        raw=start_end_config()
        schema=json.loads((ROOT/'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(current_fixture(raw))),[])
        plan=AnalysisPlan.from_dict(current_fixture(raw))
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        self.assertEqual(plan.rules[0].dependencies,('begin','done'))
        self.assertEqual(plan.rules[0].start_end.timeout_ns,5)
        self.assertTrue(plan.rules[0].start_end.emit_initial)
        for change in (dict(timeout='0ns'),dict(timeout=-1),dict(emit_initial=1),dict(end_condition='value'),
                       dict(condition='True'),dict(enter_delay='1ns')):
            bad=copy.deepcopy(raw);bad['rules'][0].update(change)
            with self.subTest(change=change),self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(bad))

    def test_backends_batches_windows_and_calculations(self):
        """0–2/4–9/11–14及均值10/52/110，跨批一致。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference','numpy'):
            for batch in (1,2,32):
                raw=start_end_config();raw['execution'].update(backend=backend,batch_rows=batch)
                result=self.run_config(raw)
                self.assertEqual(self.intervals(result),[(0,2,'closed'),(4,9,'timeout'),(11,14,'closed')])
                segments=list(result.iter_segments())
                events={row.event_id:row for row in result.iter_events()}
                self.assertEqual([tuple(events[parent].status for parent in r.parent_event_ids) for r in segments],[('closed',),('timeout',),('closed',)])
                self.assertEqual(sorted(r.value for r in result.iter_calculations()),[10,10,52,52,110,110])
                result.close();self.assertEqual(result.spool.budget.ram_bytes,0)

    def test_deadline_without_input_and_same_time_end(self):
        """无5ns采样仍在5超时，同刻end优先关闭。参数: 无。返回: None。异常: 断言失败。"""
        raw=start_end_config();raw['sources'][0]['rows']=[dict(time='0ns',values=dict(begin=1,done=0,value=10)),
            dict(time='16ns',values=dict(begin=1,done=0,value=10))]
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,5,'timeout')])
        raw['sources'][0]['rows'].insert(1,dict(time='5ns',values=dict(begin=0,done=1,value=10)))
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,5,'closed')])

    def test_end_only_dependency_and_unknown(self):
        """结束条件引用独立字段，缺失不能漏过或变成超时。参数: 无。返回: None。异常: 断言失败。"""
        raw=start_end_config();raw['sources'][0]['rows'][4]['values']['done']=None
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,2,'closed'),(4,6,'interrupted'),(11,14,'closed')])
        raw=start_end_config();raw['sources'][0]['rows'][1]['values']['begin']=None
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,2,'closed'),(4,9,'timeout'),(11,14,'closed')])

    def test_independent_end_source_and_clock_validation(self):
        """第二来源确实参与判断和同步校验，EOF不伪造超时。参数: 无。返回: None。异常: 断言失败。"""
        raw=start_end_config()
        second=copy.deepcopy(raw['sources'][0]);second['name']='ending'
        raw['sources'].append(second);raw['signals'][1]['source']='ending'
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,2,'closed'),(4,9,'timeout'),(11,14,'closed')])
        second['rows']=second['rows'][:5]
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,2,'closed'),(4,6,'truncated')])
        second['time']['origin']='different_clock'
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(raw))

    def test_csv_file_boundary_keeps_active_state(self):
        """第一个CSV结束时仍活动，第二个继续到超时。参数: 无。返回: None。异常: 文件/断言错误。"""
        raw=start_end_config();work=ROOT/'work/m3-migrate-home-20261022/csv'/uuid4().hex;work.mkdir(parents=True)
        rows=raw['sources'][0]['rows'];paths=[]
        for index,part in enumerate((rows[:5],rows[5:])):
            path=work/f'part{index}.csv'
            path.write_text('t,begin,done,value\n'+''.join(f"{r['time'][:-2]},{r['values']['begin']},{r['values']['done']},{r['values']['value']}\n" for r in part),encoding='utf-8')
            paths.append(str(path))
        raw['sources']=[dict(name='input',source_type='signal_csv',paths=paths,time_column='t',time=dict(time_type='relative',unit='ns',origin='clock'))]
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,2,'closed'),(4,9,'timeout'),(11,14,'closed')])

    def test_initial_and_unlimited_empty_terminal(self):
        """显式关闭首次触发、不限时、空数据和末点有独立语义。参数: 无。返回: None。异常: 断言失败。"""
        raw=start_end_config();raw['rules'][0]['emit_initial']=False
        self.assertEqual(self.intervals(self.run_config(raw)),[(4,9,'timeout'),(11,14,'closed')])
        raw=start_end_config();raw['rules'][0]['timeout']=None
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,2,'closed'),(4,14,'closed')])
        raw=start_end_config();raw['sources'][0]['rows']=[]
        self.assertEqual(self.intervals(self.run_config(raw)),[])
        raw=start_end_config();raw['sources'][0]['rows']=[raw['sources'][0]['rows'][0]]
        self.assertEqual(self.intervals(self.run_config(raw)),[])

    def test_constant_conditions_use_real_observation(self):
        """始终开始/从不结束可按实际观测计时，空文件不生成。参数: 无。返回: None。异常: 断言失败。"""
        raw=start_end_config();raw['rules'][0].update(start_condition='True',end_condition='False')
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,5,'timeout')])
        raw['sources'][0]['rows']=[]
        self.assertEqual(self.intervals(self.run_config(raw)),[])

    def test_cancel_and_budget_failure_release_ram(self):
        """实际状态推进取消和预算不足均清理资源。参数: 无。返回: None。异常: 断言失败。"""
        budgets=[];original=ResourceBudget.reserve_ram
        def reserve(owner,amount):
            """记录真实账本。参数: owner/amount。返回: 原结果。异常: 原异常。"""
            if owner not in budgets:
                budgets.append(owner)
            return original(owner,amount)
        with patch.object(ResourceBudget,'reserve_ram',reserve),patch.object(StartEndDetector,'_advance',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
            self.run_config(start_end_config())
        self.assertTrue(budgets);self.assertTrue(all(b.ram_bytes==0 for b in budgets))
        raw=start_end_config();raw['execution']['memory_budget_bytes']=64
        with self.assertRaises(BudgetExceededError):
            self.run_config(raw)

    def test_one_scan_publication_and_old_rules_coexist(self):
        """双条件共用一次来源扫描，发布保timeout且旧规则可并用。参数: 无。返回: None。异常: 断言失败。"""
        raw=start_end_config();raw['rules'].append(dict(name='old',rule_type='condition_duration', duration_comparison='>=',condition='begin > 0',minimum_duration='0ns'))
        scans=[];original=BudgetedMemorySourceAdapter.iter_batches
        def batches(owner,*args,**kwargs):
            """捕获扫描而不替换数据。参数: 原调用参数。返回: 原游标。异常: 原异常。"""
            scans.append(owner);return original(owner,*args,**kwargs)
        with patch.object(BudgetedMemorySourceAdapter,'iter_batches',batches):
            result=self.run_config(raw)
        self.assertEqual(len(scans),1)
        self.assertEqual({r.rule_id for r in result.iter_events()},{'cycle','old'})
        output=ROOT/'work/m3-migrate-home-20261022/published'/uuid4().hex
        publication = result.write(output)
        events = next(path for path in publication.output_files if path.name.startswith('事件结果_'))
        self.assertIn('超时结束', events.read_text(encoding='utf-8'))
        events = {row.event_id: row for row in result.iter_events()}
        self.assertTrue(any(events[parent].status == 'timeout'
                            for row in result.iter_segments() for parent in row.parent_event_ids))

    def test_activity_rejected_as_point_sequence(self):
        """活动不能伪装点窗口或FIFO点请求。参数: 无。返回: None。异常: 断言失败。"""
        raw=start_end_config();raw['windows'][0].update(anchor='point',pre='1ns')
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(raw))

    def test_sequence_coexistence_and_activity_rejection(self):
        """双条件槽不干扰FIFO配对，活动不能作为点请求。参数: 无。返回: None。异常: 断言失败。"""
        from test_sequence_runner import config_fixture
        raw=config_fixture();expected=[r for r in self.run_config(raw).iter_sequences()]
        raw['rules'].append(dict(name='bounded_request',rule_type='start_end',start_condition='request',end_condition='not request',timeout='5ns'))
        actual = list(self.run_config(raw).iter_sequences())
        self.assertEqual([replace(row, sequence=0) for row in actual],
                         [replace(row, sequence=0) for row in expected])
        raw['sequences'][0]['start']='bounded_request'
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(raw))

    def test_end_ttl_and_actual_terminal_deadline(self):
        """结束字段过期中断；截止末点有真实值时仍能判正常或超时。参数: 无。返回: None。异常: 断言失败。"""
        for value,status in ((0,'timeout'),(1,'closed')):
            raw=start_end_config();raw['sources'][0]['rows']=[dict(time='0ns',values=dict(begin=1,done=0,value=10)),
                dict(time='5ns',values=dict(begin=0,done=value,value=10))]
            self.assertEqual(self.intervals(self.run_config(raw)),[(0,5,status)])
        raw=start_end_config();raw['signals'][1]['valid_for']='2ns'
        raw['sources'][0]['rows']=[dict(time='0ns',values=dict(begin=1,done=0,value=10)),
            dict(time='16ns',values=dict(begin=1,done=0,value=10))]
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,2,'interrupted')])
