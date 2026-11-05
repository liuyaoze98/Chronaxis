"""用真实BLF核按需时间检查、无时间累计及当前平坦输出。

手算两桶结果；额外追溯由测试明确请求，原帧数量只从实际read完成时观察。
不把所需记录摘要当成全输入内容证明，不保留旧版本结果入口。
"""
from published_paths import published_file


from configuration_fixtures import current_fixture

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest
from uuid import uuid4

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.execution.can_reader import CANObservationRead
from chronaxis.results.codec import encode_row, decode_row
from test_optional_contribution_execution import make_can_fixture, drain, summary_values


class DemandCheckExecutionTests(unittest.TestCase):
    """每次真实读取、发布和关闭，区分未采集时间、无匹配和无有效贡献。"""

    def fixture(self, **options):
        """创建独占输入并显式请求诊断。参数: 夹具选项。返回: root/config。异常: 原IO/依赖错。"""
        root=Path(__file__).resolve().parents[2]/'work/demand-check-tests'/uuid4().hex
        config,_=make_can_fixture(root,**options)
        config['diagnostics']={'trace':True,'integrity':True}
        return root,config

    def run_case(self, root, config, name):
        """在实际read关闭前观察EOF，不增加输入扫描。参数: 根/配置/名称。返回: 汇总/元数据。异常: 原错。"""
        plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
        original=CANObservationRead.close
        observations=[]
        def close(read):
            """借读实际完成事实后执行原close。参数: 原read。返回: None。异常: 原关闭错。"""
            if read.finished and not read.closed and not read._closing:
                observations.append(read.observation)
            return original(read)
        with patch.object(CANObservationRead,'close',new=close):
            result=AnalysisRunner().run(plan,work_dir=root/(name+'-run'))
        budget=result.spool.budget
        try:
            rows=drain(result.iter_calculations())
            for row in rows:
                self.assertEqual(decode_row(encode_row(row,1<<20),1<<20),row)
            self.published=result.write(root/(name+'-output'))
            metadata=result.metadata
        finally:
            result.close()
        self.assertEqual(budget.ram_bytes,0)
        self.assertEqual(len(observations),1)
        self.observation=observations[0]
        return rows,metadata

    def test_whole_file_untimed_matches_complete_check_both_backends(self):
        """全文件两桶700/-200J；none不制造时间，full记录来源检查范围。参数: 无。返回: None。异常: 断言。"""
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend):
                root,config=self.fixture(backend=backend)
                del config['dataset']['domain']
                rows,metadata=self.run_case(root,config,'none')
                observation=self.observation
                full=deepcopy(config);full['sources'][0]['input_check']='full'
                baseline,complete=self.run_case(root,full,'full')
                self.assertEqual(summary_values(rows),summary_values(baseline))
                self.assertEqual(tuple(row.value for row in rows),(700.,-200.))
                self.assertEqual(metadata.session_boundaries,())
                self.assertEqual(metadata.session_ids,('session',))
                fact=metadata.input_diagnostics[0]
                self.assertEqual((observation.row_count,fact.record_count),(6,5))
                self.assertEqual((observation.first_ns,observation.last_ns,fact.time_scope),(None,None,'none'))
                self.assertEqual(complete.input_diagnostics[0].time_scope,'source')
                self.assertEqual(fact.digest_scope,'required-decoded-records-v1')
                self.assertTrue(fact.source_eof)

    def test_explicit_domain_uses_only_target_time_and_keeps_half_open_filter(self):
        """[0,3)排除3秒目标，检查所需时间不冒充全文件范围。参数: 无。返回: None。异常: 断言。"""
        root,config=self.fixture(domain=('0s','3s'))
        rows,metadata=self.run_case(root,config,'selected')
        self.assertEqual(tuple(row.value for row in rows),(400.,-200.))
        self.assertEqual(metadata.input_diagnostics[0].time_scope,'selected')
        self.assertEqual((self.observation.first_ns,self.observation.last_ns),(0,3_000_000_000))

    def test_empty_file_and_no_matching_file_keep_distinct_counts(self):
        """空/无匹配均无求值，原帧数以真实读取事实区分。参数: 无。返回: None。异常: 断言。"""
        for frames,expected in (((),0),(((0,257,1),(1,257,2)),2)):
            with self.subTest(raw_count=expected):
                root,config=self.fixture(frames=frames);del config['dataset']['domain']
                rows,metadata=self.run_case(root,config,'empty')
                self.assertEqual(self.observation.row_count,expected)
                self.assertEqual(metadata.input_diagnostics[0].record_count,0)
                self.assertEqual([(row.value,row.reason) for row in rows],[(None,'no_evaluations')]*2)

    def test_target_count_is_not_valid_contribution_count(self):
        """缺值和零方向仍产生两目标记录，两个桶均无有效值。参数: 无。返回: None。异常: 断言。"""
        root,config=self.fixture(frames=((0,256,None),(1,256,0)))
        del config['dataset']['domain']
        rows,metadata=self.run_case(root,config,'skipped')
        self.assertEqual(metadata.input_diagnostics[0].record_count,2)
        self.assertEqual([(row.value,row.reason) for row in rows],[(None,'all_skipped')]*2)

    def test_current_csv_keeps_input_scope_in_requested_manifest(self):
        """计算CSV保存结果，输入检查范围只在请求的来源清单保存一次。参数: 无。返回: None。异常: 断言。"""
        import csv
        root,config=self.fixture();del config['dataset']['domain']
        config['outputs']['tables']='csv'
        self.run_case(root,config,'csv')
        with (published_file(self.published,'calculations.csv')).open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual([float(row['value']) for row in rows],[700.,-200.])
        self.assertTrue(all('time_scope' not in row and 'row_json' not in row for row in rows))
        document=json.loads((self.published.manifest_path).read_text(encoding='utf-8'))
        fact=document['run']['input_diagnostics'][0]
        self.assertEqual((fact['time_scope'],fact['input_check']),('none','auto'))


if __name__=='__main__':
    unittest.main()
