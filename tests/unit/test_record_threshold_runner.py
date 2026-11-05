"""公开阈值预设的单一时长输出；固定周期按真实有效比例分摊。"""

from configuration_fixtures import current_fixture

from pathlib import Path
from uuid import uuid4
from itertools import product
import unittest
from unittest.mock import patch
from chronaxis import AnalysisRunner,AnalysisPlan,validate_analysis_plan
from test_threshold_preset import config


class RecordThresholdRunnerTests(unittest.TestCase):
    """手算actual0.3秒/fixed0.2秒，过期部分不能计作未报警。"""

    def run_config(self,mode,backend,*,ttl='1s',rows=None,domain=None):
        """构造独立预设输入。参数: 模式/后端/有效期/可选样本。返回: 结果。异常: 原公开错误。"""
        raw=config()
        raw.update(config_version=4)
        raw['dataset']['domain']=domain or dict(start='0s',end='1s')
        raw['intervals']=dict(default=dict(mode=mode))
        if mode=='fixed':
            raw['intervals']['default'].update(value='0.1s',driver='temperature')
        raw['sources'][0]['rows']=rows if rows is not None else [
            dict(time='0s',values=dict(temperature=85)),dict(time='0.12s',values=dict(temperature=77)),
            dict(time='0.3s',values=dict(temperature=75))]
        raw['signals'][0]['valid_for']=ttl
        raw['execution']['batch_rows']=1
        plan=AnalysisPlan.from_dict(current_fixture(raw))
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        root=Path(__file__).resolve().parents[2]/'work/m3-raw-interval-home/threshold'/uuid4().hex
        result=AnalysisRunner(backend).run(plan,root)
        self.addCleanup(result.close)
        return result

    def test_complete_and_partial_original_pair_fraction(self):
        """中途0.27过期，固定累计0.1+0.1×0.15/0.18；末点不再补周期。"""
        for mode,backend,ttl in product(('actual','fixed'),('reference','numpy'),('1s','0.15s')):
            with self.subTest(mode=mode,backend=backend,ttl=ttl):
                result=self.run_config(mode,backend,ttl=ttl)
                summary,=result.metadata.threshold_durations
                expected=(.3 if ttl=='1s' else .27) if mode=='actual' else (.2 if ttl=='1s' else .1+.1*.15/.18)
                self.assertAlmostEqual(summary.value,expected,places=12)
                self.assertEqual(summary.status,'complete' if ttl=='1s' else 'partial')
                fields=result.metadata.to_dict()['threshold_durations'][0]
                self.assertEqual(set(fields),{'preset_id','rule_id','value','status','unit'})
                self.assertEqual(fields['unit'],'s')
                calculation,=tuple(result.iter_calculations())
                self.assertAlmostEqual(calculation.value,expected,places=12)
                budget=result.spool.budget
                result.close()
                self.assertEqual(budget.ram_bytes,0)

    def test_empty_single_and_initial_unknown(self):
        """无记录对为无观测；开始77度不能假定报警或未报警。"""
        for rows in ([],[dict(time='0s',values=dict(temperature=85))]):
            with self.run_config('fixed','numpy',rows=rows) as result:
                summary,=result.metadata.threshold_durations
                self.assertEqual(summary.status,'no_observation')
                self.assertIsNone(summary.value)
        rows=[dict(time=f'{time}s',values=dict(temperature=value)) for time,value in ((0,77),(.12,85),(.3,75))]
        with self.run_config('fixed','reference',rows=rows) as result:
            summary,=result.metadata.threshold_durations
            self.assertEqual(summary.status,'partial')
            self.assertAlmostEqual(summary.value,.1)

    def test_domain_clips_original_driver_pair(self):
        """请求0.06–0.12秒取原0–0.12一半周期，总累计和事件累计均0.05秒。"""
        for backend in ('reference','numpy'):
            with self.run_config('fixed',backend,domain=dict(start='0.06s',end='0.12s')) as result:
                summary,=result.metadata.threshold_durations
                self.assertAlmostEqual(summary.value,.05)
                self.assertEqual(summary.status,'complete')
                row,=tuple(result.iter_calculations())
                self.assertAlmostEqual(row.value,.05)

    def test_actual_does_not_create_driver_file_and_cancel_cleans_fixed(self):
        """actual无需驱动暂存；fixed真正写出事件时长后取消必须归零并删除运行目录。"""
        with patch('chronaxis.execution.record_time_indexes.TemporaryFile',side_effect=AssertionError('unneeded clock file')):
            with self.run_config('actual','numpy') as result:
                self.assertEqual(len(tuple(result.iter_calculations())),1)
        from chronaxis.execution.record_session_calculations import RecordSessionCalculations
        original=RecordSessionCalculations._emit_event_duration
        snapshots=[]
        def cancel(owner,request,event_id,row):
            """在真实写入后模拟用户取消。参数: owner/请求/结果。返回: 无。异常: KeyboardInterrupt。"""
            original(owner,request,event_id,row)
            snapshots.append((owner._budget,owner._path))
            raise KeyboardInterrupt('after event duration')
        with patch.object(RecordSessionCalculations,'_emit_event_duration',cancel):
            with self.assertRaises(KeyboardInterrupt):
                self.run_config('fixed','numpy')
        self.assertTrue(snapshots)
        self.assertEqual(snapshots[0][0].ram_bytes,0)
        self.assertFalse(snapshots[0][1].exists())
