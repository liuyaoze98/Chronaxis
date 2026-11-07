"""公开Runner核对三种原始报文格式的严格周期门槛，不改报文实际时间。

复用CAN周期夹具，独立手算两个100ms周期为880J、三个为1680J。
每次运行同时声明达到/严格超过两条规则，24次覆盖双后端和fixed/DBC；
批次固定为1以验证跨批状态，避免重复扩大已有核心边界测试。
"""

from itertools import product
from uuid import uuid4
import unittest

from chronaxis import AnalysisRunner
import test_record_runner as fixtures


class StrictDurationCANTests(unittest.TestCase):
    """周期决定累计门槛，原始时间决定事件端点，完整合格区间参与积分。"""

    setUp = fixtures.RecordRunnerTests.setUp
    asc = fixtures.RecordRunnerTests.asc
    csv = fixtures.RecordRunnerTests.csv
    blf = fixtures.RecordRunnerTests.blf
    plan = fixtures.RecordRunnerTests.plan
    fixtures = fixtures.RecordRunnerTests.fixtures

    def test_public_three_formats_fixed_and_dbc_strict_threshold(self):
        """参数: 无。返回: None。异常: 原读取错误或断言失败；不依赖真实业务日志。"""
        self.fixtures()
        for end in (0.25, 0.5):
            # 这些时间能由二进制浮点精确表示，BLF写库不会引入无关舍入差异。
            rows = ((0., bytes([200, 10])), (.125, bytes([200, 12])), (.25, bytes([200, 20])))
            if end == .5:
                rows += ((.5, bytes([200, 0])),)
            asc = ''.join(f'{time} 1 100 Rx d 2 {data[0]:02X} {data[1]:02X}\n'
                          for time, data in rows)
            csv = ''.join(f'{time},100,{data[0]:02X} {data[1]:02X},2\n'
                          for time, data in rows)
            paths = dict(can_asc=self.asc(asc).path, raw_can_csv=self.csv(csv).path,
                         can_blf=self.blf(rows))

            def edit(raw):
                """参数: raw计划字典。返回: None。异常: 无；只声明本测试的规则与积分。"""
                raw['dataset']['domain']['end'] = f'{end}s'
                reached = dict(name='reached', rule_type='condition_duration', duration_comparison='>=',
                               condition='current > 0', minimum_duration='0.2s')
                raw['rules'] = [reached, dict(reached, name='strict', duration_comparison='>')]
                raw['calculations'] = [dict(name='energy_' + name, scope=dict(rule=name),
                    operation='integral', expr='power', unit='J') for name in ('reached', 'strict')]
                raw['execution'] = dict(batch_rows=1)

            for (kind, path), backend, mode in product(paths.items(), ('reference', 'numpy'), ('fixed', 'dbc')):
                with self.subTest(kind=kind, backend=backend, mode=mode, end=end):
                    plan = self.plan(kind, path, mode, edit)
                    directory = self.root / uuid4().hex
                    with AnalysisRunner(backend).run(plan, directory) as result:
                        events = {row.rule_id: row for row in result.iter_events()}
                        values = {row.calculation_id: row for row in result.iter_calculations()}
                        expected_names = {'reached'} if end == .25 else {'reached', 'strict'}
                        self.assertEqual(set(events), expected_names)
                        self.assertEqual(set(values), {'energy_' + name for name in expected_names})
                        for name, event in events.items():
                            self.assertEqual(event.start_ns, 0)
                            self.assertEqual(event.end_ns, int(end * 1e9))
                            self.assertEqual(event.confirmed_ns,
                                             250_000_000 if name == 'reached' else 500_000_000)
                            calculation = values['energy_' + name]
                            self.assertEqual(calculation.parent_id, event.event_id)
                            self.assertAlmostEqual(calculation.value, 880. if end == .25 else 1680.)
                        budget = result.spool._budget
                    self.assertEqual(budget.ram_bytes, 0)
                    self.assertFalse(directory.exists())
