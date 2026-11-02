"""从公开配置验收阈值预设及已知/未知报警累计。

输入使用合成温度、两个CSV文件和不同单位映射。期望由明确时间区间手算，
覆盖初始未知、缺口、确认等待、无观测、两后端、发布和资源清理。
所有运行写work专用目录，原项目只读；不把合成参数当车辆标定。
"""

from configuration_fixtures import current_fixture

import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
import subprocess
import sys
from uuid import uuid4
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError
from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError, validate_analysis_plan, explain_analysis_plan
from chronaxis.presets import build_preset
from chronaxis.core.stability import StabilityDetector, StabilitySpec
from chronaxis.results.threshold_metadata import ThresholdDurationMetadata
from chronaxis.execution.run_session import RunSession
from chronaxis.execution import run_session as run_module
from chronaxis.results.errors import AnalysisError
from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.types import Truth
from examples.m3_combined_analysis import combined_config

ROOT = Path(__file__).resolve().parents[2]
NS = 10**9


def config():
    """给出85→77→75的显式预设。参数: 无。返回: 独立配置dict。异常: 读样例错误。"""
    raw = json.loads((ROOT / 'examples/stability_plan.json').read_text(encoding='utf-8'))
    raw.update(rules=[], windows=[], calculations=[], presets=[dict(name='hot', preset_type='threshold_excursion', version='1',
        role_bindings=dict(signal='temperature'), parameters=dict(unit='degC', enter_threshold=80, exit_threshold=75))])
    return raw


class ThresholdPresetTests(unittest.TestCase):
    """实际AnalysisRunner运行并核对冻结结果，不能用预设实现生成期望。"""

    def setUp(self):
        """创建隔离工作目录。参数: 无。返回: None。异常: 原I/O错误。"""
        self.work = ROOT / 'work/m3-accept-home-20261023/threshold' / uuid4().hex
        self.work.mkdir(parents=True)

    def run_config(self, raw, folder='run'):
        """登记结果清理后交付。参数: raw配置及folder。返回: AnalysisResult。异常: 原运行错。"""
        result = AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)), work_dir=self.work / folder)
        self.addCleanup(result.close)
        return result

    def assert_summary(self, result, value, status):
        """用秒手算核对整数纳秒及状态。参数: result和期望。返回: 快照。异常: 断言。"""
        self.assertEqual(len(result.metadata.threshold_durations), 1)
        item = result.metadata.threshold_durations[0]
        self.assertEqual(item.value,None if status in ('no_observation','indeterminate') else value)
        self.assertEqual(item.unit,'s')
        self.assertEqual(item.status, status)
        return item

    def test_schema_static_contract_and_fragment(self):
        """严格配置和普通展开一致，单位/角色/阈值错误在读数据前拒绝。参数: 无。返回: None。异常: 断言。"""
        raw = config()
        schema = json.loads((ROOT / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(raw)
        plan = AnalysisPlan.from_dict(current_fixture(raw))
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        self.assertIn('temperature', explain_analysis_plan(plan).nodes[0].dependencies)
        fragment = build_preset(plan.presets[0], tuple(s.definition for s in plan.signals))
        direct = copy.deepcopy(raw)
        direct.pop('presets')
        direct.update(fragment.to_dict())
        a, b = self.run_config(raw, 'preset'), self.run_config(direct, 'direct')
        self.assertEqual(tuple(a.iter_events()), tuple(b.iter_events()))
        self.assertEqual(tuple(a.iter_calculations()), tuple(b.iter_calculations()))
        self.assertEqual(b.metadata.threshold_durations, ())
        self.assertNotIn('threshold_durations', b.metadata.to_dict())
        for changes in ({'unit':'V'}, {'enter_threshold':75}, {'enter_threshold':True},
                        {'exit_threshold':81}, {'enter_delay':'-1s'}, {'extra':1}):
            invalid = copy.deepcopy(raw)
            invalid['presets'][0]['parameters'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(invalid))
        for roles in ({}, {'signal':'missing'}, {'signal':'temperature','other':'temperature'}):
            invalid = copy.deepcopy(raw); invalid['presets'][0]['role_bindings'] = roles
            with self.subTest(roles=roles), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(invalid))
        invalid=copy.deepcopy(raw);invalid['presets'][0]['parameters']['unexpected']=0
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(invalid)

    def test_backends_batches_and_two_files(self):
        """跨文件77℃不退出，报警9秒，两后端和批次一致。参数: 无。返回: None。异常: 断言。"""
        (self.work/'first.csv').write_text('time,temperature\n0,85\n3,77\n',encoding='utf-8')
        (self.work/'second.csv').write_text('time,temperature\n6,77\n9,75\n12,70\n',encoding='utf-8')
        for backend, batch in (('reference',1),('numpy',2),('numpy',32)):
            raw=config();source=raw['sources'][0];source.pop('rows')
            source.update(source_type='signal_csv',paths=[str(self.work/'first.csv'),str(self.work/'second.csv')],time_column='time')
            raw['execution'].update(backend=backend,batch_rows=batch)
            result=self.run_config(raw,f'{backend}-{batch}')
            self.assert_summary(result,9,'complete')
            self.assertEqual([(r.start_ns,r.end_ns) for r in result.iter_events()],[(0,9*NS)])
            self.assertEqual([r.value for r in result.iter_calculations()],[9.0])
            budget=result.spool.budget;result.close();self.assertEqual(budget.ram_bytes,0)

    def test_missing_predecessor_and_gap_do_not_become_zero(self):
        """初始77℃及真缺口后的77℃保持未知；只累加可证明报警部分。参数: 无。返回: None。异常: 断言。"""
        cases=[([(0,77),(3,85),(6,77),(9,75),(12,70)],6,9),
               ([(0,85),(3,None),(6,77),(9,75),(12,70)],3,6),
               ([(0,77),(12,77)],0,0)]
        for index,(values,active,known) in enumerate(cases):
            for backend in ('reference','numpy'):
                raw=config();raw['execution']['backend']=backend
                raw['sources'][0]['rows']=[dict(time=f'{t}s',values=dict(temperature=v)) for t,v in values]
                result=self.run_config(raw,f'case-{index}-{backend}')
                self.assert_summary(result,active,'partial' if known else 'indeterminate')

    def test_delays_count_actual_confirmed_state(self):
        """进入等2秒、退出等2秒，报警从2到11秒；起始2秒未知。参数: 无。返回: None。异常: 断言。"""
        for backend in ('reference','numpy'):
            raw=config();raw['execution']['backend']=backend
            raw['presets'][0]['parameters'].update(enter_delay='2s',exit_delay='2s')
            result=self.run_config(raw,backend)
            self.assert_summary(result,9,'partial')
            self.assertEqual([(r.start_ns,r.end_ns) for r in result.iter_events()],[(2*NS,11*NS)])

    def test_empty_zero_and_observed_end_are_distinct(self):
        """空/单点无面积，全程低温为已知零；末点不外推到请求末端。参数: 无。返回: None。异常: 断言。"""
        cases=[([],0,0,None,'no_observation',0), ([(0,70)],0,0,None,'no_observation',0),
               ([(0,70),(12,70)],0,12,0,'complete',12), ([(0,85),(5,85)],5,5,5,'complete',5)]
        for index,(values,active,known,total,status,observed) in enumerate(cases):
            raw=config();raw['sources'][0]['rows']=[dict(time=f'{t}s',values=dict(temperature=v)) for t,v in values]
            result=self.run_config(raw,str(index))
            self.assert_summary(result,active,status)

    def test_publish_snapshot_and_repeated_write(self):
        """重复写出只用已封存累计，不再次推进状态机；无效元数据拒绝。参数: 无。返回: None。异常: 断言。"""
        result=self.run_config(config())
        expected=self.assert_summary(result,9,'complete').to_dict()
        with patch.object(StabilityDetector,'push',side_effect=AssertionError('不得重复计算')):
            for name in ('one','two'):
                published=result.write(self.work/name)
                manifest=json.loads(published.manifest_path.read_text(encoding='utf-8'))
                self.assertEqual(manifest['run']['threshold_durations'],[expected])
        with self.assertRaises(ValueError):
            replace(result.metadata,threshold_durations=(replace(result.metadata.threshold_durations[0],preset_id='other'),))
        with self.assertRaises(ValueError):
            ThresholdDurationMetadata('hot','hot_activity',0,10,11,10)
        with self.assertRaises(TypeError):
            StabilitySpec(track_duration=1)

    def test_ttl_and_known_false_waiting(self):
        """TTL缺口独立计未知；已知未报警时等待进入不制造未知。参数: 无。返回: None。异常: 断言。"""
        raw=config();raw['signals'][0]['valid_for']='2s'
        raw['sources'][0]['rows']=[dict(time=f'{t}s',values=dict(temperature=v)) for t,v in ((0,85),(12,70))]
        self.assert_summary(self.run_config(raw,'ttl'),2,'partial')
        raw=config();raw['presets'][0]['parameters'].update(enter_delay='2s',exit_delay='0s')
        raw['sources'][0]['rows']=[dict(time=f'{t}s',values=dict(temperature=v)) for t,v in ((0,70),(1,85),(5,75),(12,70))]
        self.assert_summary(self.run_config(raw,'waiting'),2,'complete')

    def test_multiple_presets_and_independent_clocks(self):
        """两独立时钟的预设分别汇总实际范围，不借用另一来源的末点。参数: 无。返回: None。异常: 断言。"""
        raw=config();source=copy.deepcopy(raw['sources'][0]);source.update(name='remote')
        source['time']['origin']='remote_clock'
        source['rows']=[dict(time=f'{t}s',values=dict(value=10)) for t in (2,5)]
        raw['sources'].append(source)
        raw['signals'].append(dict(name='value',source='remote',field='value',dtype='float64',unit='V',valid_for='20s'))
        raw['presets'].append(dict(name='voltage_high',preset_type='threshold_excursion',version='1',
            role_bindings=dict(signal='value'),parameters=dict(unit='V',enter_threshold=5,exit_threshold=3)))
        for backend in ('reference','numpy'):
            raw['execution']['backend']=backend
            result=self.run_config(raw,backend)
            first,second=result.metadata.threshold_durations
            self.assertEqual((first.value,second.value),(9,3))
            self.assertEqual((first.status, second.status), ('complete', 'complete'))
            remote_events = [row for row in result.iter_events() if row.rule_id == 'voltage_high_activity']
            self.assertEqual([(row.start_ns, row.end_ns) for row in remote_events], [(2*NS, 5*NS)])

    def test_units_types_and_generated_id_collisions(self):
        """泛用单位只接受明确同名无转换，既有单位检查和节点冲突保持。参数: 无。返回: None。异常: 断言。"""
        for changes in ({'dtype':'bool'}, {'input_unit':'unknown_scale','scale':2}, {'name':'hot_duration'}):
            raw=config();raw['signals'][0].update(changes)
            if 'name' in changes:
                raw['presets'][0]['role_bindings']['signal']=changes['name']
            with self.subTest(changes=changes),self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(raw))
        raw=config();raw['signals'][0]['dtype']='uint64'
        self.assert_summary(self.run_config(raw,'uint'),9,'complete')

    def test_summary_cancellation_and_budget_failure_release_resources(self):
        """累计转清单时取消或预算拒绝，真实会话仍关闭并归零。参数: 无。返回: None。异常: 断言。"""
        original=RunSession._run_record_calculations
        reserve=run_module._reserve_owned_ram
        owners=[]

        def observed(owner):
            """保存真实最高owner后执行。参数: owner。返回: 原结果。异常: 原错。"""
            owners.append(owner)
            return original(owner)

        def reject_summary(owner, cost, slot):
            """只拒绝新汇总固定费用，使用真实预算错误。参数: owner/cost/slot。返回: 原结果。异常: 预算拒绝。"""
            if isinstance(owner,RunSession) and cost and slot=='_metadata_cost':
                owner._budget.reserve_ram(owner._budget.memory_budget_bytes+1)
            return reserve(owner,cost,slot)

        with patch.object(RunSession,'_run_record_calculations',observed):
            with patch('chronaxis.results.threshold_metadata.SummaryThresholdDuration',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
                self.run_config(config(),'cancelled')
            with patch.object(run_module,'_reserve_owned_ram',reject_summary),self.assertRaises(AnalysisError):
                self.run_config(config(),'budget')
        self.assertEqual(len(owners),2)
        self.assertTrue(all(owner._budget.ram_bytes==0 for owner in owners))

    def test_core_accounts_deadline_between_supplied_ticks(self):
        """核心未逐点提供deadline也按确认时刻累计，不按后一个报文时刻算。参数: 无。返回: None。异常: 断言。"""
        for backend in ('reference','numpy'):
            detector=StabilityDetector(TemporalRule('alarm','data','session','condition_duration'),0,12,
                StabilitySpec(2,2,True),backend=backend)
            with self.assertRaises(ValueError):
                _=detector.duration_counts
            entries=tuple(ConditionTick(t,s,terminal=t==12) for t,s in ((0,Truth.TRUE),(6,Truth.FALSE),(12,Truth.FALSE)))
            exits=tuple(ConditionTick(t,s,terminal=t==12) for t,s in ((0,Truth.FALSE),(6,Truth.TRUE),(12,Truth.TRUE)))
            detector.push(entries,exits);detector.finish()
            self.assertEqual(detector.duration_counts,(6,10))

    def test_combined_rules_and_real_cli_summary(self):
        """请求响应缺值不污染温度累计，真实CLI保存同一结果。参数: 无。返回: None。异常: 断言。"""
        raw=combined_config()
        raw['rules']=[rule for rule in raw['rules'] if rule['name']!='alarm']
        raw['presets'].append(config()['presets'][0])
        for window in raw['windows']:
            if window['rule']=='alarm':window['rule']='hot_activity'
        for calculation in raw['calculations']:
            if calculation['scope']=={'rule':'alarm'}:calculation['scope']={'rule':'hot_activity'}
        result=self.run_config(raw)
        expected=self.assert_summary(result,9,'complete').to_dict()
        self.assertEqual(len(list(result.iter_sequences())),4)
        self.assertEqual(len(list(result.iter_calculations())),11)
        plan=self.work/'plan.json';plan.write_text(json.dumps(current_fixture(raw),ensure_ascii=False),encoding='utf-8')
        api=result.write(self.work/'api')
        cli=subprocess.run([sys.executable,'-B','-m','chronaxis','run',str(plan),'--work-dir',
            str(self.work/'cli-run'),'--output',str(self.work/'cli-output')],cwd=ROOT,env=os.environ.copy(),
            capture_output=True,text=True,encoding='utf-8',timeout=90)
        (self.work/'cli.json').write_text(json.dumps(current_fixture(dict(device_label='home',returncode=cli.returncode,
            stdout=cli.stdout,stderr=cli.stderr)),ensure_ascii=False,indent=2),encoding='utf-8')
        self.assertEqual(cli.returncode,0,cli.stderr)
        manifest=json.loads((self.work/'cli-output'/'run_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['run']['threshold_durations'],[expected])
        for table in ('events','segments','calculations','sequences'):
            self.assertEqual((api.output_dir/(table+'.csv')).read_bytes(),(self.work/'cli-output'/(table+'.csv')).read_bytes())


if __name__=='__main__':
    unittest.main()
