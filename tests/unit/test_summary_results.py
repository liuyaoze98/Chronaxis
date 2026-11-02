"""验证精简指标的独立版本、按需发布和自有目录清理，旧格式单独回归。"""

from configuration_fixtures import current_fixture

import csv
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chronaxis.core.types import QualityFlag as Q
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.codec import encode_row, decode_row, estimate_row_bytes
from chronaxis.results.errors import ResultFormatError, AnalysisError, ResultClosedError
from chronaxis.results.result import AnalysisResult
from chronaxis.results.spool import ResultSpool
from chronaxis.results.summary import SummaryCalculationRow, SUMMARY_FIELDS, SummaryEventRow, SummarySequenceRow, SUMMARY_COLUMNS
from chronaxis.results.owned_directory import directory_identity, remove_owned_directory
from test_results import run_metadata


def summary(sequence=0, **changes):
    """建立明确合成精简结果。参数: 序号及字段替换。返回: 行。异常: 模型错误。"""
    row = SummaryCalculationRow(sequence, 'dataset', 'entity', 'session', 'peak', 'max_time',
                           'session', None, 2**63+17, 'W', 'complete', 'ok', Q.NONE)
    return replace(row, **changes)


class SummaryResultTests(unittest.TestCase):
    """关闭能力从生成处省略，版本与清理边界分别检查。"""

    def setUp(self):
        """建立新项目work私有测试目录。参数: 无。返回: None。异常: IO错误。"""
        temporary = TemporaryDirectory(dir='work', prefix='summary-result-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_mixed_requested_coverage_csv_has_one_optional_column(self):
        """只为请求覆盖的行增加判定，旧行和原codec仍能发布。"""
        from chronaxis.results.summary import SummaryCoverageCalculationRow,summary_fields
        spool=ResultSpool(ResourceBudget(8*1024*1024),self.root/'coverage',1,requested_tables=('calculations',))
        self.addCleanup(spool.close)
        ordinary=summary()
        fields=summary_fields(summary(1,calculation_id='covered'))
        fields['quality']=Q.NONE
        coverage=SummaryCoverageCalculationRow(**fields,coverage_status='sufficient')
        spool.append(ordinary);spool.append(coverage);spool.seal()
        metadata=run_metadata()
        result=AnalysisResult(spool,metadata,table_format='csv')
        self.addCleanup(result.close)
        output=self.root/'published-coverage'
        result.write(output)
        with (output/'calculations.csv').open(encoding='utf-8-sig',newline='') as handle:
            rows=list(csv.DictReader(handle))
        self.assertEqual(len(rows[0]),len(SUMMARY_FIELDS)+1)
        self.assertEqual({r['calculation_id']:r['coverage_status'] for r in rows},{'peak':'','covered':'sufficient'})

    def result(self, *, name='spool', table_format='csv', diagnostic=False, retain=False):
        """准备两行精简结果和明确schema2元数据。参数: 发布设置。返回: 结果。异常: 构造错误。"""
        spool = ResultSpool(ResourceBudget(8*1024*1024), self.root/name, 1,
                            requested_tables=('calculations',), failure_diagnostics=diagnostic or retain)
        self.addCleanup(spool.close)
        spool.append(summary())
        spool.append(summary(1, calculation_id='missing', value=None, status='indeterminate', reason='no_observation', quality=Q.MISSING))
        spool.seal()
        metadata = replace(run_metadata(), input_identity=None,
                           device_label='home', detailed_diagnostics=diagnostic, retain_work=retain)
        result = AnalysisResult(spool, metadata, table_format)
        self.addCleanup(result.close)
        return result

    def test_flat_codec_and_strict_version_boundary(self):
        """大整数精确保留，旧行不能仅改版本冒充精简行。参数: 无。返回: None。异常: 断言失败。"""
        row = summary()
        encoded = encode_row(row, 4096)
        self.assertLess(len(encoded), estimate_row_bytes(row))
        self.assertEqual(decode_row(encoded, 4096), row)
        packed = json.loads(encoded)
        self.assertEqual(packed['row_schema_version'], 7)
        self.assertEqual(set(packed['row']), set(SUMMARY_FIELDS))
        for changed in ({**packed, 'row_schema_version': 1},
                        {**packed, 'row': {**packed['row'], 'source_refs': []}},
                        {**packed, 'row': {**packed['row'], 'quality': -1}},
                        {**packed, 'row': {**packed['row'], 'quality': True}}):
            with self.assertRaises(ResultFormatError):
                decode_row(json.dumps(current_fixture(changed)).encode(), 4096)
        old = {'row_schema_version': 1, 'row': {'model': 'CalculationRow', 'fields': {}}}
        old['row_schema_version'] = 7
        with self.assertRaises(ResultFormatError):
            decode_row(json.dumps(current_fixture(old)).encode(), 65536)
        for changes in ({'value': float('inf')}, {'value': True}, {'scope': 'event'},
                        {'status': 'indeterminate'}, {'parent_id': 'unexpected'}):
            with self.assertRaises((ValueError, TypeError)):
                summary(**changes)

    def test_events_and_sequences_publish_flat_without_duplicate_events(self):
        """新8/9版本各自平坦发布；配对只关联ID，不重复保存事件、规则或源时间。"""
        rows=(SummaryEventRow(0,'dataset','entity','session','alarm','event-a',0,120,900,'closed','condition_duration',Q.NONE),
              SummarySequenceRow(1,'dataset','entity','session','pair','pair-a','event-a','event-b',900,200,'matched',Q.NONE))
        for row,version in zip(rows,(8,9)):
            encoded=encode_row(row,4096)
            self.assertEqual(json.loads(encoded)['row_schema_version'],version)
            self.assertEqual(decode_row(encoded,4096),row)
        budget=ResourceBudget(8*1024*1024,8*1024*1024)
        spool=ResultSpool(budget,self.root/'mixed',enable_sequences=True,requested_tables=('events','sequences'))
        self.addCleanup(spool.close)
        for row in rows:
            spool.append(row)
        spool.seal()
        metadata=replace(run_metadata(),input_identity=None,
                         device_label='home',detailed_diagnostics=False,retain_work=False)
        result=AnalysisResult(spool,metadata,'csv')
        self.addCleanup(result.close)
        out=self.root/'published'
        result.write(out)
        manifest=json.loads((out/'run_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['row_schema_versions'],dict(events=8,sequences=9))
        for table in ('events','sequences'):
            with (out/(table+'.csv')).open(encoding='utf-8-sig',newline='') as stream:
                reader=csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames),SUMMARY_COLUMNS[table])
                self.assertEqual(len(tuple(reader)),1)
        self.assertFalse((out/'quality.jsonl').exists())
        result.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_csv_has_only_requested_fields_and_can_publish_twice(self):
        """默认无JSON副本、质量文件、输出哈希扫描；关闭只删自有暂存。参数: 无。返回: None。异常: 断言失败。"""
        result = self.result()
        self.assertEqual(result.spool.tables, ('calculations',))
        self.assertIsNone(result.manifest_path)
        self.assertEqual(tuple(result.iter_calculations()), (summary(), summary(1, calculation_id='missing', value=None,
            status='indeterminate', reason='no_observation', quality=Q.MISSING))[::-1])  # 按calculation_id排序。
        for name in ('first', 'second'):
            with patch('chronaxis.results.result.hashlib.sha256', side_effect=AssertionError('未请求输出哈希')):
                result.write(self.root/name)
            self.assertEqual({p.name for p in (self.root/name).iterdir()}, {'calculations.csv', 'run_manifest.json'})
            with (self.root/name/'calculations.csv').open(encoding='utf-8', newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(set(rows[0]), set(SUMMARY_FIELDS))
            self.assertEqual(rows[1]['value'], str(2**63+17))
            manifest = json.loads((self.root/name/'run_manifest.json').read_text('utf-8'))
            self.assertNotIn('spool_files', manifest)
            self.assertNotIn('coverage', manifest)
            self.assertNotIn('input_identity', manifest['run'])
            self.assertNotIn('sha256', manifest['outputs'][0])
        path = result.spool.path
        result.close()
        self.assertFalse(path.exists())
        self.assertTrue((self.root/'first/calculations.csv').exists())
        self.assertEqual(result.spool.budget.ram_bytes, 0)
        with self.assertRaises(ResultClosedError):
            result.iter_calculations()

    def test_jsonl_and_explicit_diagnostics(self):
        """JSONL只保存一份版本化行；显式诊断才产生质量文件和哈希。参数: 无。返回: None。异常: 断言失败。"""
        for detailed in (False, True):
            name = str(detailed)
            result = self.result(name='spool'+name, table_format='jsonl', diagnostic=detailed, retain=True)
            result.write(self.root/name)
            with (self.root/name/'calculations.jsonl').open('rb') as handle:
                rows = tuple(decode_row(line, 4096) for line in handle)
            self.assertEqual(len(rows), 2)
            self.assertEqual((self.root/name/'quality.jsonl').exists(), detailed)
            result.close()
            self.assertTrue(result.spool.path.exists())

    def test_failed_publish_cleans_temporary_and_retry_works(self):
        """安装前故障不留无请求现场，结果仍可向新目录重试。参数: 无。返回: None。异常: 断言失败。"""
        result = self.result()
        with patch.object(result, '_install_directory', side_effect=OSError('安装失败')):
            with self.assertRaises(AnalysisError):
                result.write(self.root/'out')
        self.assertEqual(list(self.root.glob('.out.incomplete-*')), [])
        self.assertFalse(list(result.spool.path.glob('*failure*')))
        result.write(self.root/'out')
        before = (self.root/'out/calculations.csv').read_bytes()
        with self.assertRaises(AnalysisError):
            result.write(self.root/'out')
        self.assertEqual((self.root/'out/calculations.csv').read_bytes(), before)

    def test_delete_failure_keeps_close_retry_and_replaced_directory_is_safe(self):
        """删除失败不得假报关闭；同名被替换的目录不删除。参数: 无。返回: None。异常: 断言失败。"""
        result = self.result()
        with patch('chronaxis.results.result.remove_owned_directory', side_effect=OSError('删除失败')):
            with self.assertRaises(OSError):
                result.close()
        self.assertFalse(result._closed)
        result.close()
        self.assertTrue(result._closed)
        original = self.root/'original'
        original.mkdir()
        identity = directory_identity(original)
        saved = self.root/'saved'
        original.rename(saved)
        original.mkdir()
        marker = original/'user.txt'
        marker.write_text('保留', encoding='utf-8')
        with self.assertRaises(ValueError):
            remove_owned_directory(original, identity)
        self.assertEqual(marker.read_text('utf-8'), '保留')

    def test_failed_output_cleanup_keeps_owner_for_retry(self):
        """发布和删除同时失败时，父结果保留待清理目录，不允许开始新发布。参数: 无。返回: None。异常: 断言失败。"""
        result = self.result()
        with patch.object(result, '_install_directory', side_effect=OSError('安装失败')):
            with patch('chronaxis.results.result.remove_owned_directory', side_effect=OSError('目录暂时被占用')):
                with self.assertRaises(AnalysisError) as caught:
                    result.write(self.root/'out')
        self.assertIs(caught.exception.analysis_result_cleanup_owner, result)
        self.assertIsNotNone(result._pending_output_cleanup)
        with self.assertRaises(ResultClosedError):
            result.write(self.root/'retry')
        result.close()
        self.assertEqual(list(self.root.glob('.out.incomplete-*')), [])
        self.assertEqual(result.spool.budget.ram_bytes, 0)

    def test_retired_metadata_versions_and_omitted_tables_reject_input(self):
        """仅当前元数据可构造，未请求表不能接收额外行。参数: 无。返回: None。异常: 断言失败。"""
        for version in (1, 2):
            with self.subTest(version=version), self.assertRaises(ValueError):
                replace(run_metadata(), config_version=version)
        spool = ResultSpool(ResourceBudget(), self.root/'empty', requested_tables=(), failure_diagnostics=False)
        self.addCleanup(spool.close)
        with self.assertRaises((AnalysisError, KeyError, ValueError)):
            spool.append(summary())
        self.assertFalse((spool.path/'failure.json').exists())

    def test_diagnostics_use_each_table_actual_state_field(self):
        """选择、贡献、输入追溯没有status；诊断保各自原字段，CSV/JSONL均可发布。"""
        from chronaxis.results.summary import SummaryContributionRow, SummaryInputRow
        from test_results import summary_selection_row
        rows=(summary_selection_row(0,unknown=True),
              SummaryContributionRow(1,'dataset','entity','session','energy','bus',5,0,None,'missing_input',Q.MISSING),
              SummaryInputRow(2,'dataset','entity','session','bus',5,6,'signal_sample','synthetic:5','{"a":1}',Q.NONE))
        for fmt in ('csv','jsonl'):
            spool=ResultSpool(ResourceBudget(8*1024*1024),self.root/fmt,1,
                enable_selections=True,enable_contributions=True,enable_trace=True,
                requested_tables=('selections','contributions','input_trace'))
            self.addCleanup(spool.close)
            for row in rows:spool.append(row)
            spool.seal()
            result=AnalysisResult(spool,replace(run_metadata(),detailed_diagnostics=True),fmt)
            self.addCleanup(result.close)
            output=self.root/('diagnostics-'+fmt);result.write(output)
            quality=[json.loads(line) for line in (output/'quality.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([(r['table'],r.get('selection',r.get('reason',r.get('record_type')))) for r in quality],
                [('selections','unknown'),('contributions','missing_input'),('input_trace','signal_sample')])
            self.assertTrue(all('status' not in row for row in quality))
            manifest=json.loads((output/'run_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['coverage'],{'selections:unknown':1,'contributions:missing_input':1,'input_trace:signal_sample':1})
            result.close()
            self.assertEqual(spool.budget.ram_bytes,0)


if __name__ == '__main__':
    unittest.main()
