"""从当前公开入口验证活动起点、确认起点及原事件/合并片段的独立范围。

预期直接由2/4/6W时间线计算；同时覆盖实际记录与固定周期、两后端及真实CSV。
不调用旧历史窗口包装器，以免独立旧实现通过掩盖当前执行器漏接配置。
"""

from configuration_fixtures import current_fixture
from itertools import product
from uuid import uuid4
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner
import test_record_sources as source_cases


class EventCalculationOriginTests(unittest.TestCase):
    """九个计算操作和时长快捷路径都必须遵守同一活动规则的选择起点。"""

    setUp = source_cases.RecordSourcesTests.setUp

    def config(self, source_type, origin, mode, size, minimum_duration='1s'):
        """建立0—3秒活动，功率依次2/4/6W，3秒关闭。

        参数: 来源、选择起点、间隔、批次和确认时长。返回: 当前配置字典。
        异常: 测试CSV写入失败直接传播；所有产物在本测试专用目录。
        """
        source = dict(name='input', source_type=source_type,
                      time=dict(time_type='relative', unit='s', origin='clock'))
        if source_type == 'memory':
            source['rows'] = [dict(time=f'{time}s', values=dict(power=value, active=active))
                              for time, value, active in ((0, 2, 1), (1, 4, 1), (2, 6, 1), (3, 99, 0))]
        else:
            path = self.root / (uuid4().hex + '.csv')
            path.write_text('time,power,active\n0,2,1\n1,4,1\n2,6,1\n3,99,0\n', encoding='utf-8')
            source.update(path=str(path), time_column='time')
        calculations = [dict(name=operation, scope='event:activity', operation=operation, expr='power')
                        for operation in ('integral', 'sample_minimum', 'sample_maximum', 'sample_mean',
                                          'min_time', 'max_time', 'time_weighted_mean', 'select')]
        # 无条件时长走快捷路径；条件时长走必要值历史，两者都须接入origin。
        calculations += [dict(name='duration', scope='event:activity', operation='duration', condition='True'),
                         dict(name='conditioned_duration', scope='event:activity', operation='duration',
                              condition='active > 0')]
        choice = dict(mode=mode)
        if mode == 'fixed':
            choice.update(value='1s', driver='power')
        return dict(config_version=3,
                    dataset=dict(name='data', entity='device', session='session',
                                 domain=dict(start='0s', end='3s')),
                    sources=[source], signals=[dict(name=name, source='input', field=name,
                        dtype='float64', unit=unit, valid_for='10s') for name, unit in (('power', 'W'), ('active', '1'))],
                    rules=[dict(name='activity', rule_type='condition_duration', condition='active > 0',
                                minimum_duration=minimum_duration, selection_origin=origin)],
                    calculations=calculations, intervals=dict(default=choice),
                    execution=dict(batch_rows=size, result_buffer_rows=1))

    def test_all_operations_use_selected_start_and_keep_real_activity(self):
        """原活动总为[0,3)；onset面积12J，confirmed面积10J，样本右端均排除。"""
        for kind, mode, backend, size, origin in product(('memory', 'signal_csv'), ('actual', 'fixed'),
                ('reference', 'numpy'), (1, 7), ('onset', 'confirmed')):
            with self.subTest(kind=kind, mode=mode, backend=backend, size=size, origin=origin):
                raw = self.config(kind, origin, mode, size)
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)), self.root / uuid4().hex) as result:
                    event, = tuple(result.iter_events())
                    self.assertEqual((event.start_ns, event.confirmed_ns, event.end_ns), (0, 10**9, 3 * 10**9))
                    rows = {row.calculation_id: row for row in result.iter_calculations()}
                    first, mean, area, duration = (2., 4., 12., 3.) if origin == 'onset' else (4., 5., 10., 2.)
                    expected = dict(integral=area, sample_minimum=first, sample_maximum=6., sample_mean=mean,
                                    min_time=first, max_time=6., time_weighted_mean=mean, duration=duration,
                                    conditioned_duration=duration)
                    self.assertEqual({name: row.value for name, row in rows.items()}, expected)
                    self.assertTrue(all(row.parent_id == event.event_id for row in rows.values()))
                    selections = tuple(result.iter_selections())
                    expected_points = [(0, 2.), (10**9, 4.), (2 * 10**9, 6.)]
                    self.assertEqual([(row.time_ns, row.value) for row in selections],
                                     expected_points if origin == 'onset' else expected_points[1:])
                    self.assertTrue(all(row.parent_id == event.event_id for row in selections))
                    budget = result.spool.budget
                self.assertEqual(budget.ram_bytes, 0)

    def test_confirmation_at_end_is_empty_without_changing_original_event(self):
        """3秒才确认时统计[3,3)，九个标量均无值，select不返回EOF样本。"""
        for kind, mode, backend in product(('memory', 'signal_csv'), ('actual', 'fixed'), ('reference', 'numpy')):
            raw = self.config(kind, 'confirmed', mode, 1, minimum_duration='3s')
            with self.subTest(kind=kind, mode=mode, backend=backend):
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)), self.root / uuid4().hex) as result:
                    event, = tuple(result.iter_events())
                    self.assertEqual((event.start_ns, event.confirmed_ns, event.end_ns), (0, 3 * 10**9, 3 * 10**9))
                    rows = tuple(result.iter_calculations())
                    self.assertEqual(len(rows), 9)
                    self.assertTrue(all(row.value is None and row.reason == 'zero_length_window' for row in rows))
                    self.assertFalse(tuple(result.iter_selections()))
                    budget = result.spool.budget
                self.assertEqual(budget.ram_bytes, 0)

    def test_t45_events_keep_separate_energy_when_context_windows_merge(self):
        """两活动各4000J；扩展后的合并片段为24000J，并保留两个原父事件。"""
        for kind, backend in product(('memory', 'signal_csv'), ('reference', 'numpy')):
            raw = self.config(kind, 'onset', 'actual', 1, minimum_duration='0s')
            raw['dataset']['domain']['end'] = '6s'
            points = [(time, 4000, int(time in (0, 2))) for time in range(7)]
            source = raw['sources'][0]
            if kind == 'memory':
                source['rows'] = [dict(time=f'{time}s', values=dict(power=value, active=active))
                                  for time, value, active in points]
            else:
                from pathlib import Path
                Path(source['path']).write_text('time,power,active\n' + ''.join(
                    f'{time},{value},{active}\n' for time, value, active in points), encoding='utf-8')
            raw['windows'] = [dict(name='context', rule='activity', anchor='activity', pre='0s',
                                   post='3s', merge='overlap_and_adjacent')]
            raw['calculations'] = [dict(name=name, scope=scope, operation='integral', expr='power', unit='J')
                                   for name, scope in (('each_event', 'event:activity'), ('context_energy', 'segment:context'))]
            with self.subTest(kind=kind, backend=backend):
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)), self.root / uuid4().hex) as result:
                    events = tuple(result.iter_events())
                    segment, = tuple(result.iter_segments())
                    self.assertEqual([(row.start_ns, row.end_ns) for row in events],
                                     [(0, 10**9), (2 * 10**9, 3 * 10**9)])
                    self.assertEqual((segment.start_ns, segment.end_ns), (0, 6 * 10**9))
                    self.assertEqual(segment.parent_event_ids, tuple(row.event_id for row in events))
                    rows = tuple(result.iter_calculations())
                    self.assertEqual({row.parent_id: row.value for row in rows},
                                     {events[0].event_id: 4000., events[1].event_id: 4000., segment.segment_id: 24000.})
                    budget = result.spool.budget
                self.assertEqual(budget.ram_bytes, 0)
