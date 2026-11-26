"""运行清单按事实记录文件工作进程数（BUG-DEV6-002）。

用小型ASC真实运行：清单的process_count是本次生效上限，worker_process_count是实际启动数；
同一计划覆盖进程数不改变计划身份，所以必须由清单自己说明。分别覆盖主进程读取、连续分卷读取解码、
文件内面积并行、time_order组点并行、time_order上限1，以及CSV来源（上限不代表启动了进程）。
输入都是本测试专用目录中的合成文件；不做性能计时。
"""
from collections.abc import Mapping
from uuid import uuid4
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner, RunMetadata
import test_session_process_runtime as session_cases


def native(value):
    """把只读配置副本还原为普通字典与列表。参数: 任意JSON形值。返回: 原生容器。异常: 无。"""
    if isinstance(value, Mapping):
        return {key: native(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [native(item) for item in value]
    return value


class RunProcessManifestTests(unittest.TestCase):
    """每项都从真实运行的结果取清单，不手工构造实际启动数。"""

    setUp = session_cases.SessionProcessRuntimeTests.setUp
    file = session_cases.SessionProcessRuntimeTests.file
    plan = session_cases.SessionProcessRuntimeTests.plan

    def manifest(self, plan, count=None):
        """运行一次并返回清单run部分。参数: 计划、可选进程上限覆盖。返回: dict。异常: 运行错误传播。"""
        with AnalysisRunner().run(plan, self.root / uuid4().hex, process_count=count) as result:
            return result.run_manifest['run']

    def direct_plan(self, parts, merge):
        """无条件会话积分的计划，满足直接积分与并行积分条件。参数: 分卷、归并方式。返回: AnalysisPlan。"""
        files = [self.file(rows, 'asc') for rows in parts]
        raw = dict(config_version=4, dataset=dict(name='direct'),
                   sources=[dict(name='bus', paths=[str(p) for p in files], file_merge=merge,
                                 dbc_by_channel={'1': str(self.dbc)})],
                   signals=[dict(name='power', field=dict(frame_id=256, signal='Power'), dtype='float64',
                                 unit='W', valid_for='2s')],
                   calculations=[dict(name='energy', operation='integral', expr='power', unit='J')],
                   outputs=dict(tables='jsonl'))
        return AnalysisPlan.from_dict(raw)

    def test_single_process_reports_no_worker(self):
        """上限1时全部在主进程内完成：实际启动数为0，没有worker_config键。"""
        run = self.manifest(self.plan([[(0, 10), (1, 20)], [(2, 30), (3, 40)]], 'asc'))
        self.assertEqual((run['process_count'], run['worker_process_count']), (1, 0))
        self.assertNotIn('worker_config', run)

    def test_parallel_reading_reports_started_workers_within_limit(self):
        """上限4、两个文件：实际启动2个；上限等于文件数时数值相同，计划身份不变。"""
        plan = self.plan([[(0, 10), (1, 20)], [(2, 30), (3, 40)]], 'asc')
        wide, exact = self.manifest(plan, 4), self.manifest(plan, 2)
        self.assertEqual((wide['process_count'], wide['worker_process_count']), (4, 2))
        self.assertEqual((exact['process_count'], exact['worker_process_count']), (2, 2))
        self.assertEqual(wide['plan_hash'], exact['plan_hash'])
        self.assertEqual(wide['plan_hash'], self.manifest(plan, 1)['plan_hash'])

    def test_override_wins_over_configuration(self):
        """配置写2时，运行时覆盖为1：清单记录覆盖后的1，不启动工作进程。"""
        raw = native(self.plan([[(0, 10), (1, 20)], [(2, 30), (3, 40)]], 'asc').raw_config)
        raw['execution'] = dict(process_count=2)
        plan = AnalysisPlan.from_dict(raw)
        self.assertEqual(self.manifest(plan)['process_count'], 2)
        run = self.manifest(plan, 1)
        self.assertEqual((run['process_count'], run['worker_process_count']), (1, 0))

    def test_parallel_integral_and_point_paths_report_started_workers(self):
        """连续分卷面积并行与time_order组点并行都报告实际启动数。"""
        disjoint = [[(0, 10), (1, 20), (2, 10)], [(3, 30), (4, 40), (5, 10)]]
        overlap = [[(0, 10), (2, 20), (4, 10)], [(1, 30), (3, 40), (5, 10)]]
        for merge, parts in (('concatenate', disjoint), ('time_order', overlap)):
            with self.subTest(merge=merge):
                run = self.manifest(self.direct_plan(parts, merge), 4)
                self.assertEqual((run['process_count'], run['worker_process_count']), (4, 2))

    def test_time_order_with_limit_one_still_uses_one_worker(self):
        """time_order在上限1时也使用文件工作进程，清单如实写1。"""
        plan = self.plan([[(0, 10), (2, 20)], [(1, 30), (3, 40)]], 'asc', merge='time_order')
        run = self.manifest(plan, 1)
        self.assertEqual((run['process_count'], run['worker_process_count']), (1, 1))

    def test_csv_source_never_reports_started_workers(self):
        """CSV在主进程读取：清单实际启动数为0（并行上限大于1的CSV计划在校验时即被拒绝）。"""
        path = self.root / (uuid4().hex + '.csv')
        path.write_text('time,power\n0,10\n1,20\n2,10\n', encoding='utf-8')
        raw = dict(config_version=4, dataset=dict(name='table', domain=dict(start='0s', end='2s')),
                   sources=[dict(name='table', source_type='signal_csv', path=str(path), time_column='time',
                                 time=dict(time_type='relative', unit='s'))],
                   signals=[dict(name='power', source='table', field='power', dtype='float64', unit='W', valid_for='5s')],
                   calculations=[dict(name='energy', operation='integral', expr='power', unit='J')],
                   outputs=dict(tables='jsonl'))
        run = self.manifest(AnalysisPlan.from_dict(raw))
        self.assertEqual((run['process_count'], run['worker_process_count']), (1, 0))

    def test_metadata_rejects_impossible_process_counts(self):
        """实际启动数不能超过上限，数值必须是原生整数。"""
        base = dict(run_id='r', input_identity=None, plan_hash='p', backend='reference', config_version=4,
                    source_time_interpretation='t', session_boundaries=(), started_at='2026-11-25T00:00:00+08:00')
        RunMetadata(**base, process_count=4, worker_process_count=2)
        for count, started in ((0, 0), (True, 0), (4, 5), (4, -1), (4, True), ('4', 0)):
            with self.subTest(process_count=count, worker_process_count=started):
                with self.assertRaises(ValueError):
                    RunMetadata(**base, process_count=count, worker_process_count=started)


if __name__ == '__main__':
    unittest.main()
