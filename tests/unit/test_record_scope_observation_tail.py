"""[home] CAN无关末帧仍提供事件窗口统计的观测终点；不补固定周期。"""
import json
from itertools import product
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
from uuid import uuid4
import unittest

from chronaxis import AnalysisRunner, load_analysis_plan


class ScopeObservationTailTests(unittest.TestCase):
    """公开文件入口核对末次相关更新到真实日志结束之间的计算。"""

    def setUp(self):
        """建立独立ASC/DBC；温度1—6秒报警，功率恒10W，日志7秒结束。"""
        directory = TemporaryDirectory(prefix='scope-tail-', dir='work')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        (self.root / 'meter.dbc').write_text('''VERSION "synthetic-home"
NS_ :
BS_:
BU_: Node
BO_ 256 Reading: 2 Node
 SG_ Power : 0|8@1+ (1,0) [0|255] "W" Node
 SG_ Temperature : 8|8@1+ (1,0) [0|255] "degC" Node
''', encoding='utf8')
        (self.root / 'meter.asc').write_text('base hex timestamps absolute\n'
            '0 1 100 Rx d 2 0A 46\n1 1 100 Rx d 2 0A 50\n'
            '3 1 100 Rx d 2 0A 50\n6 1 100 Rx d 2 0A 46\n'
            '7 1 7FE Rx d 1 00\n', encoding='utf8')

    def config(self, *, age='4s', fixed=False):
        """给出当前公开配置；有效期与固定周期只用于所测试的差异。"""
        raw = dict(config_version=4, dataset=dict(name='scope_tail'),
            sources=[dict(path='meter.asc', dbc_by_channel={'1': 'meter.dbc'})],
            signals=[dict(name=name, field=dict(frame_id='0x100', signal=signal), valid_for=ttl)
                for name, signal, ttl in [('power', 'Power', age), ('temperature', 'Temperature', '4s')]],
            rules=[dict(name='hot', rule_type='condition_duration', duration_comparison='>=', condition='temperature >= 80', minimum_duration='0s')],
            windows=[dict(name='context', rule='hot', pre='1s', post='1s')],
            calculations=[dict(name='event_energy', scope={'rule': 'hot'}, operation='integral', expr='power')]
                + [dict(name=op, scope={'window': 'context'}, operation=op, expr='power')
                   for op in ('integral', 'time_weighted_mean', 'sample_mean', 'sample_maximum', 'select')])
        if fixed:
            raw['calculations'][1]['interval'] = dict(mode='fixed', value='100ms', driver='power')
        return raw

    def run_config(self, raw, backend):
        """读取实际ASC并收集结果；关闭后核预算释放，不用测试配置迁移助手。"""
        path = self.root / 'plan.json'
        path.write_text(json.dumps(raw), encoding='utf8')
        with AnalysisRunner(backend).run(load_analysis_plan(path), self.root / uuid4().hex) as result:
            rows = {row.calculation_id: row for row in result.iter_calculations()}
            selections = [(row.time_ns / 1e9, row.value) for row in result.iter_selections()]
            budget = result.spool.budget
        self.assertEqual(budget.ram_bytes, 0)
        return rows, selections

    def test_window_includes_observed_tail_without_an_extra_sample(self):
        """窗口[0,7)积分70J、4个真实样本；事件[1,6)保持50J。"""
        for backend, explicit, batch in product(('reference', 'numpy'), (False, True), (1, 64)):
            with self.subTest(backend=backend, explicit=explicit, batch=batch):
                raw = self.config()
                raw['execution'] = dict(batch_rows=batch)
                if explicit:
                    raw['dataset']['domain'] = dict(start='0s', end='7s')
                rows, selected = self.run_config(raw, backend)
                self.assertEqual(rows['event_energy'].value, 50.)
                self.assertEqual(rows['integral'].value, 70.)
                self.assertTrue(all(row.status == 'complete' for row in rows.values()))
                for op in ('time_weighted_mean', 'sample_mean', 'sample_maximum'):
                    self.assertEqual(rows[op].value, 10.)
                self.assertEqual(selected, [(0, 10), (1, 10), (3, 10), (6, 10)])

    def test_fixed_period_does_not_gain_a_synthetic_interval(self):
        """固定0.1秒仅累计真实三对，共3J；观测结束不能新增一个周期。"""
        for backend in ('reference', 'numpy'):
            rows, _ = self.run_config(self.config(fixed=True), backend)
            self.assertAlmostEqual(rows['integral'].value, 3.)

    def test_tail_is_clipped_by_validity(self):
        """每个值仅保持0.5秒，四个真实更新共有效2秒；窗口积分20J并标部分。"""
        for backend in ('reference', 'numpy'):
            rows, _ = self.run_config(self.config(age='500ms'), backend)
            self.assertEqual(rows['integral'].value, 20.)
            self.assertEqual(rows['integral'].status, 'partial')


if __name__ == '__main__':
    unittest.main()
