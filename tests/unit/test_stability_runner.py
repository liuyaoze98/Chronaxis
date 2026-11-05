"""从公共配置运行迟滞/防抖，验证文件边界、计时、窗口与资源收尾。

输入为明确声明的合成温度或两条件信号；所有CSV与结果写work专用目录。
对照手算活动时间和两独立数值后端，结果关闭后检查预算，不接触RefProjects。
"""
from published_paths import published_file


from configuration_fixtures import current_fixture

import copy
from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, AnalysisRunner, validate_analysis_plan, explain_analysis_plan, PlanValidationError
from chronaxis.core.stability import StabilityDetector, StabilitySpec
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, AnalysisError
from chronaxis.results.codec import encode_row, decode_row

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'work/m3-stability-home-20261022/tests'


def stable_config():
    """给出85→77跨文件后77→70的温度合成例。参数: 无。返回: dict。异常: 无。"""
    return dict(config_version=4,
        dataset=dict(name='sample', entity='device', session='session', domain=dict(start='0ns', end='12ns')),
        sources=[dict(name='input', source_type='memory', time=dict(time_type='relative', unit='ns', origin='clock'),
            rows=[dict(time=f'{t}ns', values={'temperature':v}) for t,v in [(0,85),(3,77),(6,77),(9,75),(12,70)]])],
        signals=[dict(name='temperature', source='input', field='temperature', dtype='int64', unit='degC', valid_for='20ns')],
        rules=[dict(name='alarm', rule_type='hysteresis', enter_condition='temperature >= 80', exit_condition='temperature <= 75')],
        execution=dict(batch_rows=2, result_buffer_rows=1, memory_budget_bytes=256*1024**2),
        outputs=dict(tables='jsonl'), metadata=dict(device_label='home', data_kind='synthetic'))


class StabilityRunnerTests(unittest.TestCase):
    """每个运行使用独立目录，断言基于手算真值而非重新调用被测实现。"""

    def run_config(self, config):
        """运行独立计划并登记关闭。参数: config字典。返回: AnalysisResult。异常: 原执行错误。"""
        result = AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)), work_dir=WORK/uuid4().hex)
        self.addCleanup(result.close)
        return result

    def intervals(self, result):
        """取报警时间及结束原因。参数: result。返回: tuple列表。异常: 结果读取错误。"""
        return [(r.start_ns,r.end_ns,r.status) for r in result.iter_events()]

    def test_schema_and_typed_validation(self):
        """两个公开kind/schema严格拒绝误填字段。参数: 无。返回: None。异常: 断言失败。"""
        schema=json.loads((ROOT/'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        raw=stable_config()
        Draft202012Validator(schema).validate(current_fixture(raw))
        plan=AnalysisPlan.from_dict(current_fixture(raw))
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        self.assertEqual(explain_analysis_plan(plan).nodes[0].dependencies, ('temperature',))
        for changes in ({'exit_condition':'temperature'}, {'enter_delay':'-1s'}, {'duration':'2ns'},
                        {'emit_initial':True}, {'unknown_policy':'false'}):
            invalid=copy.deepcopy(raw);invalid['rules'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(invalid))
        with self.assertRaises(TypeError):
            replace(plan.rules[0],exit_condition=None)
        with self.assertRaises(ValueError):
            replace(plan.rules[0],rule_type='condition_duration',minimum_duration_ns=0)
        raw['rules']=[dict(name='alarm',rule_type='debounce',condition='temperature >= 80',enter_delay='1ns',exit_delay='2ns')]
        Draft202012Validator(schema).validate(current_fixture(raw))
        self.assertTrue(validate_analysis_plan(AnalysisPlan.from_dict(current_fixture(raw))).execution_ready)

    def test_backends_and_batches(self):
        """活动0—9不在77处解除，双后端/不同批次事件完整相同。参数: 无。返回: None。异常: 断言失败。"""
        expected=None
        for backend,batch in (('reference',1),('numpy',2),('numpy',32)):
            raw=stable_config();raw['execution'].update(backend=backend,batch_rows=batch)
            result=self.run_config(raw)
            self.assertEqual(self.intervals(result),[(0,9,'closed')])
            events=[r for r in result.iter_events()]
            if expected is None:
                expected=events
            self.assertEqual(events,expected)
            budget=result.spool.budget;result.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_two_actual_csv_files_keep_state(self):
        """真实两个CSV依次读入仍是一段报警，文件/计算批不重置。参数: 无。返回: None。异常: I/O或断言。"""
        folder=WORK/uuid4().hex;folder.mkdir(parents=True)
        (folder/'first.csv').write_text('time,temperature\n0,85\n3,77\n',encoding='utf-8')
        (folder/'second.csv').write_text('time,temperature\n6,77\n9,75\n12,70\n',encoding='utf-8')
        for backend in ('reference','numpy'):
            raw=stable_config();source=raw['sources'][0];source.pop('rows')
            source.update(source_type='signal_csv',paths=[str(folder/'first.csv'),str(folder/'second.csv')],time_column='time')
            raw['execution'].update(backend=backend,batch_rows=1)
            self.assertEqual(self.intervals(self.run_config(raw)),[(0,9,'closed')])

    def test_enter_and_exit_deadlines_without_records(self):
        """2ns进入，9ns开始退出等2ns，11ns无需报文即可解除。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config();raw['rules'][0].update(enter_delay='2ns',exit_delay='2ns')
        self.assertEqual(self.intervals(self.run_config(raw)),[(2,11,'closed')])
        raw['rules']=[dict(name='alarm',rule_type='debounce',condition='temperature >= 80',enter_delay='2ns',exit_delay='2ns')]
        self.assertEqual(self.intervals(self.run_config(raw)),[(2,5,'closed')])

    def test_initial_unknown_and_true_data_gap(self):
        """第一条77不报警；TTL失效后的77不能恢复旧报警。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config();raw['sources'][0]['rows'][0]['values']['temperature']=77
        self.assertEqual(self.intervals(self.run_config(raw)),[])
        raw=stable_config();raw['signals'][0]['valid_for']='2ns'
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,2,'interrupted')])

    def test_exit_signal_is_projected_and_traced(self):
        """退出条件独有信号也读取并追溯；同刻原子更新不看半组。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config()
        for row in raw['sources'][0]['rows']:
            row['values']['reset']=row['time']=='9ns'
        raw['signals'].append(dict(name='reset',source='input',field='reset',dtype='bool',unit='1',valid_for='20ns'))
        raw['rules'][0]['exit_condition']='reset'
        raw['diagnostics']={'trace':True}
        plan=AnalysisPlan.from_dict(current_fixture(raw))
        self.assertEqual(set(plan.rules[0].dependencies),{'temperature','reset'})
        self.assertEqual(set(explain_analysis_plan(plan).nodes[0].dependencies),{'temperature','reset'})
        result=self.run_config(raw)
        self.assertEqual(self.intervals(result),[(0,9,'closed')])
        diagnostic,=result.metadata.input_diagnostics
        self.assertEqual(dict(diagnostic.bindings),{'temperature':'temperature','reset':'reset'})
        trace=tuple(result.iter_input_trace())
        self.assertEqual({name for row in trace for name in json.loads(row.values_json)},{'temperature','reset'})

    def test_second_source_and_clock_check(self):
        """退出来源使用实际范围与同步依据，不漏掉独立时钟。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config();raw['sources'].append(dict(name='reset_source',source_type='memory',
            time=dict(time_type='relative',unit='ns',origin='clock'),
            rows=[dict(time=f'{t}ns',values={'reset':v}) for t,v in [(0,False),(9,True),(12,True)]]))
        raw['signals'].append(dict(name='reset',source='reset_source',field='reset',dtype='bool',unit='1',valid_for='20ns'))
        raw['rules'][0]['exit_condition']='reset'
        raw['calculations']=[dict(name='mean',scope='event:alarm',operation='time_weighted_mean',expr='temperature',unit='degC')]
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,9,'closed')])
        raw['sources'][1]['time']['origin']='other_clock'
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(raw))

    def test_event_window_calculations_and_publication(self):
        """报警0—9平均(85+77+77)/3，片段同范围；结果可发布及往返解码。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config()
        raw['windows']=[dict(name='window',rule='alarm',anchor='activity',pre='0ns',post='0ns')]
        raw['calculations']=[dict(name='event_mean',scope='event:alarm',operation='time_weighted_mean',expr='temperature',unit='degC'),
                        dict(name='segment_mean',scope='segment:window',operation='time_weighted_mean',expr='temperature',unit='degC')]
        for backend in ('reference','numpy'):
            raw['execution']['backend']=backend;result=self.run_config(raw)
            values=[row.value for row in result.iter_calculations()]
            self.assertEqual(len(values),2)
            for value in values:
                self.assertAlmostEqual(value,239/3)
            self.assertEqual(len(list(result.iter_segments())),1)
            for row in result.iter_events():
                self.assertEqual(decode_row(encode_row(row, max_bytes=2**20), max_bytes=2**20),row)
            target=WORK/uuid4().hex
            published=result.write(target)
            self.assertTrue((published_file(published,'run_manifest.json')).exists())

    def test_overlap_fails_and_closes_budget(self):
        """进出条件同真时明确失败，不猜优先级，也不泄漏RAM。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config();raw['rules'][0]['exit_condition']='temperature >= 75'
        budgets=[];original=ResourceBudget.reserve_ram
        def reserve(owner,amount):
            """记录实际账本后照常申请。参数: owner/amount。返回: 原结果。异常: 原预算异常。"""
            if owner not in budgets:
                budgets.append(owner)
            return original(owner,amount)
        with patch.object(ResourceBudget,'reserve_ram',reserve),self.assertRaisesRegex(AnalysisError,'同时成立'):
            self.run_config(raw)
        self.assertTrue(budgets)
        self.assertTrue(all(b.ram_bytes==0 for b in budgets))

    def test_cancel_closes_owned_resources(self):
        """状态推进取消后关闭实际资源，不伪装完成。参数: 无。返回: None。异常: 断言失败。"""
        budgets=[];original=ResourceBudget.reserve_ram
        def reserve(owner,amount):
            """捕获真实预算。参数: owner/amount。返回: 原结果。异常: 原异常。"""
            if owner not in budgets:
                budgets.append(owner)
            return original(owner,amount)
        with patch.object(ResourceBudget,'reserve_ram',reserve),patch.object(StabilityDetector,'_continuous',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
            self.run_config(stable_config())
        self.assertTrue(budgets)
        self.assertTrue(all(b.ram_bytes==0 for b in budgets))

    def test_empty_short_and_terminal_observation(self):
        """无数据不报警；等待超过观测不确认；真实末点可解除。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config();raw['sources'][0]['rows']=[]
        self.assertEqual(self.intervals(self.run_config(raw)),[])
        raw=stable_config();raw['rules'][0]['enter_delay']='20ns'
        self.assertEqual(self.intervals(self.run_config(raw)),[])
        raw=stable_config();raw['sources'][0]['rows']=[dict(time='0ns',values={'temperature':85}),dict(time='12ns',values={'temperature':75})]
        self.assertEqual(self.intervals(self.run_config(raw)),[(0,12,'closed')])

    def test_budget_failure_and_old_rule_compatibility(self):
        """不足预算失败；普通规则与迟滞并用仍有原事件。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config();raw['execution']['memory_budget_bytes']=64
        with self.assertRaises(BudgetExceededError):
            self.run_config(raw)
        raw=stable_config();raw['rules'].append(dict(name='simple',rule_type='condition_duration',condition='temperature >= 80',minimum_duration='0ns'))
        rows=list(self.run_config(raw).iter_events())
        self.assertEqual({r.rule_id:(r.start_ns,r.end_ns) for r in rows},{'alarm':(0,9),'simple':(0,3)})

    def test_exit_deadline_coincides_with_ttl(self):
        """退出已满足2ns，同刻TTL不能改写为未知中断。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference','numpy'):
            raw=stable_config();raw['execution']['backend']=backend
            raw['signals'][0]['valid_for']='2ns';raw['rules'][0]['exit_delay']='2ns'
            raw['sources'][0]['rows']=[dict(time=f'{t}ns',values={'temperature':v}) for t,v in [(0,85),(2,85),(4,75),(8,70),(12,70)]]
            self.assertEqual(self.intervals(self.run_config(raw)),[(0,6,'closed')])

    def test_zero_observation_and_activity_anchor_validation(self):
        """单末点没有持续报警；公开窗口要求activity。参数: 无。返回: None。异常: 断言失败。"""
        raw=stable_config();raw['sources'][0]['rows']=raw['sources'][0]['rows'][:1]
        self.assertEqual(self.intervals(self.run_config(raw)),[])
        raw=stable_config();raw['windows']=[dict(name='bad',rule='alarm',anchor='point',pre='0ns',post='0ns')]
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(raw))

    def test_sequence_can_coexist_but_cannot_reference_activity(self):
        """新增退出查询槽不扰乱既有配对；活动不能冒充点事件。参数: 无。返回: None。异常: 断言失败。"""
        from test_sequence_runner import config_fixture
        raw=config_fixture()
        original=[row for row in self.run_config(raw).iter_sequences()]
        raw['rules'].append(dict(name='stable_request',rule_type='hysteresis',
                                 enter_condition='request',exit_condition='not request'))
        actual=[row for row in self.run_config(raw).iter_sequences()]
        self.assertEqual([replace(row, sequence=0) for row in actual],
                         [replace(row, sequence=0) for row in original])
        raw['sequences'][0]['start']='stable_request'
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(raw))


if __name__ == '__main__':
    unittest.main()
