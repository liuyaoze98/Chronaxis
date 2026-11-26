"""被事件计算引用的持续条件规则必须明确写出统计起点（BUG-DEV6-003）。

同一组合成数据给出两种起点下不同的真值：功率2/4/6W依次保持1秒，活动0—3秒，minimum_duration为1秒，
因此onset积分12J、confirmed积分10J。先证明省略时配置被拒绝且说明完整，再证明未被引用的规则、预设与其他规则
不受影响，最后核对清单、结果表与两种取值的实际数值。输入在内存或本测试专用目录，不读取历史项目。
"""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError, RunMetadata


def config(**rule):
    """建立内存功率与开关的计划配置。参数: 追加到规则的字段。返回: 配置字典。异常: 无。"""
    rows = [dict(time=f'{time}s', values=dict(power=value, active=active))
            for time, value, active in ((0, 2, 1), (1, 4, 1), (2, 6, 1), (3, 99, 0))]
    return dict(config_version=4,
                dataset=dict(name='data', domain=dict(start='0s', end='3s')),
                sources=[dict(name='input', source_type='memory', time=dict(time_type='relative', unit='s'),
                              rows=rows)],
                signals=[dict(name=name, source='input', field=name, dtype='float64', unit=unit, valid_for='10s')
                         for name, unit in (('power', 'W'), ('active', '1'))],
                rules=[dict(name='activity', rule_type='condition_duration', condition='active > 0',
                            minimum_duration='1s', duration_comparison='>=', **rule)],
                calculations=[dict(name='energy', operation='integral', expr='power', unit='J',
                                   scope=dict(rule='activity'))])


class SelectionOriginRequiredTests(unittest.TestCase):
    """每项直接给出配置与应有结论，不依赖其他测试的默认夹具。"""

    def setUp(self):
        """建立本测试专用目录。参数: 无。返回: None。异常: IO失败传播。"""
        self.temporary = TemporaryDirectory(prefix='selection-origin-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def event_table(self, out):
        """读取事件结果CSV。参数: 结果目录。返回: 表头与行列表。异常: 文件缺失时StopIteration。"""
        with next(Path(out).glob('事件结果_*.csv')).open(encoding='utf-8-sig', newline='') as handle:
            return list(csv.reader(handle))

    def rejected(self, raw):
        """取得拒绝该配置的诊断列表。参数: 配置。返回: [PlanValidationError]。异常: 未被拒绝时断言失败。"""
        with self.assertRaises(PlanValidationError) as caught:
            AnalysisPlan.from_dict(raw)
        return list(caught.exception._diagnostics or (caught.exception,))

    def test_omitted_origin_is_rejected_with_rule_calculation_and_choices(self):
        """省略时报出规则路径、引用它的计算、两种可选值和修改提示。"""
        for operation, extra in (('integral', dict(expr='power')), ('duration', dict(condition='True'))):
            with self.subTest(operation=operation):
                raw = config()
                raw['calculations'] = [dict(name='energy', operation=operation, scope=dict(rule='activity'), **extra)]
                found = [item for item in self.rejected(raw) if item.path == '$.rules[0].selection_origin']
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0].code, 'missing_field')
                for part in ('activity', 'energy', 'onset', 'confirmed'):
                    self.assertIn(part, found[0].message)
                self.assertIn('selection_origin', found[0].hint)

    def test_every_omitted_rule_and_all_calculations_are_reported_together(self):
        """两个规则都省略时一次报全，每个规则列出引用它的全部计算项。"""
        raw = config()
        raw['rules'].append(dict(name='second', rule_type='condition_duration', condition='power > 3',
                                 minimum_duration='1s', duration_comparison='>='))
        raw['calculations'] += [dict(name='peak', operation='sample_maximum', expr='power', scope=dict(rule='activity')),
                                dict(name='span', operation='duration', condition='True', scope=dict(rule='second'))]
        messages = {item.path: item.message for item in self.rejected(raw) if item.path.endswith('.selection_origin')}
        self.assertEqual(set(messages), {'$.rules[0].selection_origin', '$.rules[1].selection_origin'})
        self.assertIn('energy', messages['$.rules[0].selection_origin'])
        self.assertIn('peak', messages['$.rules[0].selection_origin'])
        self.assertIn('span', messages['$.rules[1].selection_origin'])
        self.assertNotIn('span', messages['$.rules[0].selection_origin'])

    def test_rules_without_event_calculations_may_omit_origin(self):
        """只列事件、供窗口使用或作会话计算的规则不受影响，默认仍为onset。"""
        unreferenced = config()
        unreferenced['calculations'] = [dict(name='total', operation='integral', expr='power', unit='J')]
        windowed = config()
        windowed['calculations'] = []
        windowed['windows'] = [dict(name='around', rule='activity', anchor='activity', pre='0s', post='0s')]
        for raw in (unreferenced, windowed):
            plan = AnalysisPlan.from_dict(raw)
            self.assertEqual(plan.rules[0].selection_origin, 'onset')

    def test_explicit_origins_give_expected_energy_in_both_forms(self):
        """显式onset得到12J、confirmed得到10J；清单和结果表都能看出起点。"""
        for origin, energy, start in (('onset', 12.0, '0'), ('confirmed', 10.0, '1')):
            with self.subTest(origin=origin):
                plan = AnalysisPlan.from_dict(config(selection_origin=origin))
                out = self.root / uuid4().hex
                with AnalysisRunner().run(plan, self.root / uuid4().hex) as result:
                    rows = list(result.iter_calculations())
                    events = list(result.iter_events())
                    run = result.run_manifest['run']
                    result.write(out)
                self.assertEqual([row.value for row in rows], [energy])
                self.assertEqual(events[0].start_ns, 0)
                self.assertEqual(run['selection_origins'], {'activity': origin})
                header, row = self.event_table(out)[:2]
                self.assertEqual(header[-1], '统计开始（s）')
                self.assertEqual(row[-1], start)

    def test_rows_without_event_metrics_have_no_statistics_start(self):
        """同一张表中没有指标的规则行不填统计开始，避免误认为也参与了计算。"""
        raw = config(selection_origin='onset')
        raw['rules'].append(dict(name='second', rule_type='condition_duration', condition='active > 0',
                                 minimum_duration='0s', duration_comparison='>='))
        plan = AnalysisPlan.from_dict(raw)
        out = self.root / uuid4().hex
        with AnalysisRunner().run(plan, self.root / uuid4().hex) as result:
            result.write(out)
        rows = self.event_table(out)
        self.assertEqual({row[1]: row[-1] for row in rows[1:]}, {'activity': '0', 'second': ''})

    def test_manifest_omits_origins_when_no_event_calculation(self):
        """没有事件计算时清单不输出统计起点，不增加无意义字段。"""
        raw = config()
        raw['calculations'] = []
        plan = AnalysisPlan.from_dict(raw)
        with AnalysisRunner().run(plan, self.root / uuid4().hex) as result:
            self.assertNotIn('selection_origins', result.run_manifest['run'])

    def test_other_rule_types_are_not_required_and_start_at_event(self):
        """防抖规则没有统计起点选择：计算照常运行，统计开始等于事件开始。"""
        raw = config()
        raw['rules'] = [dict(name='activity', rule_type='debounce', condition='active > 0',
                             enter_delay='0s', exit_delay='0s')]
        plan = AnalysisPlan.from_dict(raw)
        self.assertIsNone(plan.rules[0].selection_origin)
        out = self.root / uuid4().hex
        with AnalysisRunner().run(plan, self.root / uuid4().hex) as result:
            events = list(result.iter_events())
            self.assertNotIn('selection_origins', result.run_manifest['run'])
            result.write(out)
        rows = self.event_table(out)
        self.assertEqual(rows[0][-1], '统计开始（s）')
        self.assertEqual(rows[1][-1], f'{events[0].start_ns / 1e9:g}')

    def test_metadata_rejects_invalid_selection_origins(self):
        """清单中的起点只接受onset/confirmed且规则不重复。"""
        base = dict(run_id='r', input_identity=None, plan_hash='p', backend='reference', config_version=4,
                    source_time_interpretation='t', session_boundaries=(), started_at='2026-11-25T00:00:00+08:00')
        RunMetadata(**base, selection_origins=(('a', 'onset'), ('b', 'confirmed')))
        for value in ((('a', 'middle'),), (('a', 'onset'), ('a', 'confirmed')), (('', 'onset'),), [('a', 'onset')],
                      (('a', 'onset', 'x'),)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    RunMetadata(**base, selection_origins=value)


if __name__ == '__main__':
    unittest.main()
