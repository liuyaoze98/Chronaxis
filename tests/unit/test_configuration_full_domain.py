"""省略范围使用同一次读取的真实首末；不预扫描、补造时间或默认保存历史。"""
from copy import deepcopy
from pathlib import Path
from published_paths import published_file, export_root
from workspace_fixtures import TemporaryDirectory
from uuid import uuid4
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner
from configuration_fixtures import current_fixture


class FullDomainConfigurationTests(unittest.TestCase):
    """用独立手算和显式实际范围对照核对两后端。"""

    def setUp(self):
        """建立独立短验证目录。参数: 无。返回: None。异常: IO错误。"""
        directory = TemporaryDirectory(prefix='cfg-domain-', dir='work')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def config(self, rows=None, batch=1):
        """建立三条功率记录：3W保持一秒、1W保持一秒，共4J。参数: 可选记录/批大小。返回: dict。"""
        return dict(config_version=4, dataset=dict(name='whole'),
            sources=[dict(name='meter', source_type='memory', time=dict(clock='clock'),
                rows=([dict(time=str(t)+'s', values=dict(power=value))
                       for t, value in ((0,3),(1,1),(2,3))] if rows is None else rows))],
            signals=[dict(name='power', source='meter', field='power', dtype='float64', unit='W', valid_for='10s')],
            calculations=[dict(name='energy', operation='integral', expr='power', unit='J')],
            execution=dict(batch_rows=batch), metadata=dict(device_label='home'))

    def run_config(self, raw, backend):
        """完成公共Runner并复制最终小表。参数: 配置/后端。返回: 三类结果tuple。异常: 原执行错误。"""
        with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw), self.root/uuid4().hex) as result:
            tables=(tuple(result.iter_calculations()), tuple(result.iter_events()), tuple(result.iter_segments()))
            budget=result.spool.budget
        self.assertEqual(budget.ram_bytes,0)
        return tables

    def test_integral_and_empty_two_backends(self):
        """两后端4J；空输入不生成恒真事件，会话值None且原因是无观测。"""
        for backend in ('reference','numpy'):
            for batch in (1,3):
                with self.subTest(backend=backend,batch=batch):
                    raw=self.config(batch=batch)
                    calculations,_,_=self.run_config(raw,backend)
                    self.assertEqual(calculations[0].value,4.)
                    raw=self.config(rows=[])
                    raw['rules']=[dict(name='always',rule_type='condition_duration', duration_comparison='>=',condition='True',minimum_duration='0s')]
                    calculations,events,_=self.run_config(raw,backend)
                    self.assertEqual(events,())
                    self.assertIsNone(calculations[0].value)
                    self.assertEqual(calculations[0].reason,'no_observation')

    def test_rule_window_matches_actual_explicit_range(self):
        """跨批待定末点不提前结束；事件及前后窗口与真实0—2秒显式范围相同。"""
        for backend in ('reference','numpy'):
            raw=self.config()
            raw['rules']=[dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='power > 2',minimum_duration='0s')]
            raw['windows']=[dict(name='around',rule='active',anchor='activity',pre='0.5s',post='1.5s')]
            raw['calculations'].extend([
                dict(name='event_energy',scope=dict(rule='active'),operation='integral',expr='power',unit='J'),
                dict(name='window_energy',scope=dict(window='around'),operation='integral',expr='power',unit='J')])
            actual=self.run_config(raw,backend)
            raw['dataset']['domain']=dict(start='0s',end='2s')
            expected=self.run_config(raw,backend)
            self.assertEqual(actual,expected)

    def test_metrics_and_selection_shifted_bounds(self):
        """零点不是默认截取边界；负/正起点、条件归约和select均等价于实际范围。"""
        for backend in ('reference','numpy'):
            for start in (-3,123):
                raw=self.config(rows=[dict(time=str(start+t)+'s',values=dict(power=v)) for t,v in ((0,3),(1,1),(2,3))])
                raw['calculations']=[dict(name=operation,operation=operation,expr='power',condition='power > 0')
                    for operation in ('integral','sample_minimum','sample_maximum','sample_mean','min_time','max_time','time_weighted_mean','select')]
                def capture(config):
                    """复制最终小表，不保留执行资源。参数: 配置。返回: 计算/选择。异常: 原错。"""
                    with AnalysisRunner(backend).run(AnalysisPlan.from_dict(config),self.root/uuid4().hex) as result:
                        return tuple(result.iter_calculations()),tuple(result.iter_selections())
                actual=capture(raw)
                raw['dataset']['domain']=dict(start=str(start)+'s',end=str(start+2)+'s')
                self.assertEqual(actual,capture(raw))
                self.assertEqual(actual[0][0].value,4.)

    def test_multisource_union_and_csv_files(self):
        """两个来源结束在2/4秒时用联合0—4秒；跨CSV文件仍连续累计4J。"""
        for backend in ('reference','numpy'):
            raw=self.config()
            other=deepcopy(raw['sources'][0]); other['name']='second'
            other['rows']=[dict(time='1s',values={}),dict(time='4s',values={})]
            raw['sources'].append(other)
            raw['calculations']=[dict(name='elapsed',operation='duration',condition='True')]
            calculations,_,_=self.run_config(raw,backend)
            self.assertEqual(calculations[0].value,4.)
            raw=self.config()
            paths=[]
            for name,content in (('one.csv','time,power\n0,3\n1,1\n'),('two.csv','time,power\n2,3\n')):
                path=self.root/name; path.write_text(content,encoding='utf-8'); paths.append(str(path))
            raw['sources']=[dict(name='meter',source_type='signal_csv',paths=paths,time_column='time',time=dict(unit='s'))]
            calculations,_,_=self.run_config(raw,backend)
            self.assertEqual(calculations[0].value,4.)

    def test_sequence_and_threshold_match_explicit_observation(self):
        """序列等待、迟滞和固定周期沿用原含义；结束时间只由实际EOF确定。"""
        from test_record_sequence_runner import RecordSequenceRunnerTests
        from test_threshold_preset import config as threshold_config
        for backend in ('reference','numpy'):
            for mode in ('actual','fixed'):
                raw=current_fixture(RecordSequenceRunnerTests().config(mode))
                raw['dataset'].pop('domain')
                raw['execution']['batch_rows']=1
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),self.root/uuid4().hex) as result:
                    actual=(tuple(result.iter_events()),tuple(result.iter_sequences()))
                raw['dataset']['domain']=dict(start='0ns',end='12ns')
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),self.root/uuid4().hex) as result:
                    expected=(tuple(result.iter_events()),tuple(result.iter_sequences()))
                self.assertEqual(actual,expected)
                raw=current_fixture(threshold_config()); raw['config_version']=4
                raw['dataset'].pop('domain')
                raw['sources'][0]['rows']=[dict(time=str(t)+'s',values=dict(temperature=v))
                    for t,v in ((0,85),(.12,77),(.3,75))]
                raw['signals'][0]['valid_for']='1s'
                raw['execution']['batch_rows']=1
                choice=dict(mode=mode)
                if mode=='fixed':choice.update(value='0.1s',driver='temperature')
                raw['intervals']=dict(default=choice)
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),self.root/uuid4().hex) as result:
                    summary,=result.metadata.threshold_durations
                    self.assertAlmostEqual(summary.value,.3 if mode=='actual' else .2)

    def test_signal_export_and_cancel_keep_one_read(self):
        """信号CSV只含半开域内两个原值，在线网格按实际范围扩展；取消不遗留预算。"""
        import csv,json
        from chronaxis.results.signal_exports import SignalCSVWriter
        for backend in ('reference','numpy'):
            for resampled in (False,True):
                raw=self.config()
                option=dict(signals=['power'])
                if resampled:option['resampling']=dict(continuous=['power'],period='0.5s',max_gap='2s')
                raw['outputs']=dict(signal_csv=option)
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),self.root/uuid4().hex) as result:
                    destination=self.root/uuid4().hex;published=result.write(destination)
                    entry=json.loads((published_file(published,'exports.jsonl')).read_text().splitlines()[0])
                    name='resampled.csv' if resampled else 'original.csv'
                    with (export_root(published)/entry['directory']/name).open(encoding='utf-8') as handle:
                        rows=list(csv.DictReader(handle))
                    self.assertEqual([r['value'] for r in rows],['3.0','2.0','1.0',''] if resampled else ['3.0','1.0'])
                    if resampled:self.assertEqual(rows[-1]['reason'],'missing_right')
        raw=self.config();raw['outputs']=dict(signal_csv=dict(signals=['power']))
        original=SignalCSVWriter.push;budgets=[]
        def cancel(owner,sample):
            """写出第一行后取消，核对正常失败清理。参数: writer/样本。返回: 不返回。异常: KeyboardInterrupt。"""
            budgets.append(owner._budget);original(owner,sample);raise KeyboardInterrupt('cancel full-domain export')
        with patch.object(SignalCSVWriter,'push',cancel),self.assertRaises(KeyboardInterrupt):
            AnalysisRunner().run(AnalysisPlan.from_dict(raw),self.root/uuid4().hex)
        self.assertTrue(budgets)
        self.assertTrue(all(b.ram_bytes==0 for b in budgets))


import test_record_runner as raw_cases


class FullDomainRawTests(unittest.TestCase):
    """三种原始报文格式继续共用一次读取和实际终点。"""
    setUp=raw_cases.RecordRunnerTests.setUp
    asc=raw_cases.RecordRunnerTests.asc
    csv=raw_cases.RecordRunnerTests.csv
    blf=raw_cases.RecordRunnerTests.blf
    fixtures=raw_cases.RecordRunnerTests.fixtures
    plan=raw_cases.RecordRunnerTests.plan

    def test_three_formats_full_range_and_requested_exports(self):
        """两后端actual1344J/fixed880J；原帧和信号导出可与省略范围联合运行。"""
        from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
        for kind,path in self.fixtures().items():
            for backend in ('reference','numpy'):
                for mode in ('actual','fixed','dbc'):
                    def edit(raw):
                        """显式请求输出但省略范围。参数: 配置。返回: None。异常: 无。"""
                        raw['dataset'].pop('domain')
                        raw['outputs']['signal_csv']=dict(signals=['current'])
                        raw['outputs']['can_frames']=dict(source=raw['sources'][0]['name'],format='asc')
                        raw.setdefault('execution',{})['batch_rows']=1
                    plan=self.plan(kind,path,mode,edit)
                    adapter=BudgetedTextCANSourceAdapter
                    original=adapter.iter_batches;scans=[]
                    def scan(owner,*args,**kwargs):
                        """核对只读一次。参数: 原调用参数。返回: 原读取器。异常: 原错。"""
                        scans.append(owner);return original(owner,*args,**kwargs)
                    with self.subTest(kind=kind,backend=backend,mode=mode),patch.object(adapter,'iter_batches',scan):
                        with AnalysisRunner(backend).run(plan,self.root/uuid4().hex) as result:
                            rows={r.calculation_id:r.value for r in result.iter_calculations()}
                            self.assertAlmostEqual(rows['energy'],1344 if mode=='actual' else 880,places=3)
                            destination=self.root/uuid4().hex;published=result.write(destination)
                            self.assertTrue((published_file(published,'exports.jsonl')).is_file())
                            budget=result.spool.budget
                        self.assertEqual(budget.ram_bytes,0)
                        self.assertEqual(len(scans),1)


if __name__=='__main__':
    unittest.main()
