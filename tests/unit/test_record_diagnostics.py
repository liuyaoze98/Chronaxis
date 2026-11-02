"""核新版可选输入追溯与摘要独立、单次输入、同值及取消清理，不使用摘要替代数值真值。"""

from configuration_fixtures import current_fixture
import hashlib
import json
from itertools import product
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisPlan,AnalysisRunner
import test_record_legacy_runner as legacy
import test_record_sources as parsed


class RecordDiagnosticsTests(unittest.TestCase):
    """固定三条消息正桶800J/负桶-200J，诊断选项不能改变结果或隐含开启贡献。"""
    setUp=legacy.RecordLegacyRunnerTests.setUp
    asc=legacy.RecordLegacyRunnerTests.asc
    csv=legacy.RecordLegacyRunnerTests.csv
    blf=legacy.RecordLegacyRunnerTests.blf
    fixtures=legacy.RecordLegacyRunnerTests.fixtures
    plan=legacy.RecordLegacyRunnerTests.plan

    def test_raw_formats_independent_options_and_input_hash(self):
        """有trace可独立重算记录摘要；仅integrity不建追溯，trace不默认附摘要/原帧。"""
        for (kind,path),(trace,integrity) in product(self.fixtures().items(),((True,False),(False,True),(True,True))):
            with self.subTest(kind=kind,trace=trace,integrity=integrity):
                raw=self.plan(kind,path,False)
                raw['diagnostics']=dict(trace=trace,integrity=integrity)
                raw['execution']={'result_buffer_rows':1}
                result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
                self.addCleanup(result.close)
                self.assertEqual({r.calculation_id:r.value for r in result.iter_calculations()},dict(positive=800.,negative=-200.))
                self.assertNotIn('contributions',result.spool.tables)
                facts=result.run_manifest['run']['input_diagnostics']
                self.assertEqual(len(facts),1)
                self.assertEqual(facts[0]['record_count'],3)
                self.assertTrue(facts[0]['source_eof'])
                self.assertEqual(facts[0]['record_scope'],'required-decoded-records-v1')
                self.assertEqual('sha256' in facts[0],integrity)
                if trace:
                    rows=tuple(result.iter_input_trace())
                    self.assertEqual(len(rows),3)
                    self.assertEqual([json.loads(row.values_json)['Power'] for row in rows],[4000,4000,-2000])
                    if integrity:
                        digest=hashlib.sha256()
                        for row in rows:
                            payload=json.dumps(current_fixture((row.original_sequence,row.time_ns,row.record_type,row.locator,int(row.quality),row.values_json)),
                                ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
                            digest.update(len(payload).to_bytes(8,'big'));digest.update(payload)
                        self.assertEqual(facts[0]['sha256'],digest.hexdigest())
                else:self.assertNotIn('input_trace',result.spool.tables)
                output=self.root/uuid4().hex
                result.write(output)
                self.assertEqual((output/'输入追溯.csv').exists(),trace)
                self.assertFalse((output/'quality.jsonl').exists())
                budget=result.spool.budget;result.close()
                self.assertEqual(budget.ram_bytes,0)

    def test_default_never_constructs_diagnostics(self):
        """默认直接跳过诊断owner，不先收集再隐藏。"""
        path=self.fixtures()['can_asc']
        with patch('chronaxis.execution.record_session_calculations.RecordDiagnostics',side_effect=AssertionError('unused')):
            result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(self.plan('can_asc',path))),self.root/uuid4().hex)
        self.addCleanup(result.close)
        self.assertNotIn('input_diagnostics',result.run_manifest['run'])
        result.close()

    def test_unrelated_messages_not_in_trace_and_empty_source_is_explicit(self):
        """仅所需ID进入诊断；空来源确实EOF、零记录，不能写成完整文件内容核验。"""
        self.fixtures()
        for text,count in (('0.0 1 101 Rx d 1 09\n0.1 1 100 Rx d 1 04\n',1),('',0)):
            raw=self.plan('can_asc',self.asc(text).path,False)
            raw['diagnostics']={'trace':True,'integrity':True}
            result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
            self.addCleanup(result.close)
            self.assertEqual(len(tuple(result.iter_input_trace())),count)
            self.assertEqual(result.metadata.input_diagnostics[0].record_count,count)
            self.assertTrue(result.metadata.input_diagnostics[0].source_eof)
            result.close()

    def test_cancel_after_trace_releases_every_owner(self):
        """真实追溯写入后取消，不留下成功前缀和持费owner。"""
        from chronaxis.execution.record_diagnostics import RecordDiagnostics
        original=RecordDiagnostics.consume;budgets=[]
        def cancel(owner,*args):
            """实际写后取消。参数: owner/输入。返回: 不返回。异常: KeyboardInterrupt。"""
            original(owner,*args);budgets.append(owner._budget);raise KeyboardInterrupt('diagnostic cancel')
        raw=self.plan('can_asc',self.fixtures()['can_asc']);raw['diagnostics']={'trace':True,'integrity':True}
        root=self.root/uuid4().hex
        with patch.object(RecordDiagnostics,'consume',cancel):
            with self.assertRaises(KeyboardInterrupt):AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),root)
        self.assertEqual(budgets[0].ram_bytes,0);self.assertFalse(root.exists())


class ParsedDiagnosticsTests(unittest.TestCase):
    """解析表和内存走相同真实样本诊断，不伪造DBC或原帧。"""
    setUp=parsed.RecordSourcesTests.setUp
    config=parsed.RecordSourcesTests.config

    def test_memory_and_csv(self):
        """两来源各三条，固定周期能量1000J；摘要/追溯都覆盖真实样本。"""
        for kind in ('memory','signal_csv'):
            raw=self.config(kind);raw['diagnostics']={'trace':True,'integrity':True}
            result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
            self.addCleanup(result.close)
            self.assertEqual(next(r.value for r in result.iter_calculations() if r.calculation_id=='energy'),1000.)
            rows=tuple(result.iter_input_trace());self.assertEqual(len(rows),6)
            self.assertTrue(all(row.record_type=='signal_sample' for row in rows))
            self.assertEqual([item.record_count for item in result.metadata.input_diagnostics],[3,3])
            budget=result.spool.budget;result.close();self.assertEqual(budget.ram_bytes,0)
