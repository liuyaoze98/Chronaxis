"""用整数纳秒边界验证达到/严格超过与实际事件范围，不修改输入或阈值。

低层两后端覆盖跨批、记录周期、TTL/EOF与int64极限；公共Runner覆盖实际
积分起点及跨文件保持。真值由恒定4000W和明确区间长度手算；产物仅在临时目录。
"""
from dataclasses import replace
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.temporal_reference import ReferenceTemporalDetector
from chronaxis.core.temporal_numpy import NumpyTemporalDetector
from chronaxis.core.types import Truth as T, QualityFlag as Q


class StrictDurationTests(unittest.TestCase):
    """同一门槛只改变比较符，恰好60秒必须得到不同结果。"""

    def test_memory_timers_and_maximum_threshold(self):
        """参数: 无。返回: None。异常: 断言失败；内存公开核也安排严格比较计时器。"""
        from test_temporal import _memory
        from chronaxis.core.temporal_memory_reference import detect_memory_reference
        from chronaxis.core.temporal_memory_numpy import detect_memory_numpy
        for end, threshold, expected in ((60, 60, False), (61, 60, True), (61, (1 << 63) - 1, False)):
            expression = _memory(((0, {'x': True}), (end, {'x': False})), end=end, age=100)
            rule = TemporalRule('active', 'dataset', 'session', 'condition_duration', threshold,
                                duration_comparison='>')
            for factory in (detect_memory_reference, detect_memory_numpy):
                rows = factory(expression, rule, batch_rows=1)
                self.assertEqual(bool(rows), expected)
                if rows:
                    self.assertEqual(rows[0].confirmed_ns, 61)

    def test_threshold_end_reasons_and_batches(self):
        """参数: 无。返回: None。异常: 断言失败；结束/失效/EOF不覆盖严格比较。
        """
        threshold = 60_000_000_000
        for delta, comparison, size, factory, reason in product(
                (-1, 0, 1), ('>=', '>'), (1, 3),
                (ReferenceTemporalDetector, NumpyTemporalDetector), ('false', 'stale', 'eof')):
            end = threshold + delta
            rule = TemporalRule('active', 'data', 'session', 'condition_duration', threshold,
                                duration_comparison=comparison)
            final = (ConditionTick(end, T.FALSE, terminal=True) if reason == 'false' else
                     ConditionTick(end, T.UNKNOWN, Q.STALE, actual_update=False, terminal=False)
                     if reason == 'stale' else ConditionTick(end, T.TRUE, terminal=True))
            ticks = (ConditionTick(0, T.TRUE), ConditionTick(30_000_000_000, T.TRUE), final)
            owner = factory(rule, 0, end + (reason == 'stale'))
            for index in range(0, len(ticks), size):
                owner.push(ticks[index:index + size])
            # stale结束已经关候选，补同一时刻terminal会违反组协议；检查已产生事件即可。
            rows = tuple(owner.events)
            with self.subTest(delta=delta, comparison=comparison, backend=factory, reason=reason):
                self.assertEqual(len(rows), int(delta >= 0 if comparison == '>=' else delta > 0))
                if rows:
                    self.assertEqual((rows[0].start_ns, rows[0].confirmed_ns, rows[0].end_ns),
                                     (0, threshold + (comparison == '>'), end))

    def test_record_clock_waits_for_next_selected_record(self):
        """参数: 无。返回: None。异常: 断言失败；固定周期不在无报文时凭空确认。"""
        for factory, size in product((ReferenceTemporalDetector, NumpyTemporalDetector), (1, 4)):
            rule = TemporalRule('active', 'data', 'session', 'condition_duration', 20,
                                duration_comparison='>')
            ticks = (ConditionTick(0, T.TRUE), ConditionTick(100, T.TRUE),
                     ConditionTick(250, T.TRUE), ConditionTick(400, T.FALSE, terminal=True))
            owner = factory(rule, 0, 400, record_clock=True)
            for index in range(0, 4, size):
                owner.push(ticks[index:index + size], advances=(0, 10, 10, 10)[index:index + size])
            row, = owner.finish()
            self.assertEqual((row.start_ns, row.confirmed_ns, row.end_ns), (0, 400, 400))

    def test_int64_limit_never_wraps(self):
        """参数: 无。返回: None。异常: 断言失败；最大阈值actual不可超过，累计周期可超过。"""
        maximum = (1 << 63) - 1
        for factory in (ReferenceTemporalDetector, NumpyTemporalDetector):
            rule = TemporalRule('active', 'data', 'session', 'condition_duration', maximum,
                                duration_comparison='>')
            owner = factory(rule, 0, maximum)
            owner.push((ConditionTick(0, T.TRUE),))
            self.assertIsNone(owner.next_deadline_ns)
            owner.push((ConditionTick(maximum, T.FALSE, terminal=True),))
            self.assertEqual(owner.finish(), ())
            owner = factory(rule, 0, 2, record_clock=True)
            owner.push((ConditionTick(0, T.TRUE), ConditionTick(1, T.TRUE),
                        ConditionTick(2, T.FALSE, terminal=True)), advances=(0, maximum, maximum))
            row, = owner.finish()
            self.assertEqual(row.confirmed_ns, 2)

    def test_public_continuous_files_and_integral_origin(self):
        """参数: 无。返回: None。异常: 原I/O/运行错误；分卷不断开候选，积分保持实际范围。"""
        for backend, origin, end in product(('reference', 'numpy'), ('onset', 'confirmed'), (60, 61)):
            with TemporaryDirectory(dir='work', prefix='strict-duration-') as directory:
                root = Path(directory)
                (root / 'part1.csv').write_text('time,power,active\n0,4000,1\n30,4000,1\n', encoding='utf-8')
                (root / 'part2.csv').write_text(f'time,power,active\n{end},4000,0\n', encoding='utf-8')
                raw = dict(config_version=4, dataset=dict(name='data', domain=dict(start='0s', end=f'{end}s')),
                    sources=[dict(name='input', source_type='signal_csv',
                                  paths=['part1.csv', 'part2.csv'], time_column='time', time=dict(unit='s'))],
                    signals=[dict(name=name, field=name, dtype='float64', unit=unit, valid_for='120s')
                             for name, unit in (('power', 'W'), ('active', '1'))],
                    rules=[dict(name='activity', rule_type='condition_duration', condition='active >= 1',
                                minimum_duration='60s', duration_comparison='>', selection_origin=origin)],
                    calculations=[dict(name='energy', operation='integral', expr='power', unit='kWh',
                                       scope=dict(rule='activity'))], execution=dict(batch_rows=1))
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw, base_dir=root), root / 'work') as result:
                    events, rows = tuple(result.iter_events()), tuple(result.iter_calculations())
                    self.assertEqual(len(events), int(end > 60))
                    self.assertEqual(len(rows), int(end > 60))
                    if rows:
                        self.assertEqual(events[0].confirmed_ns, 60_000_000_001)
                        seconds = 61 if origin == 'onset' else 1 - 1e-9
                        self.assertAlmostEqual(rows[0].value, 4000 * seconds / 3_600_000)
                        self.assertEqual(rows[0].parent_id, events[0].event_id)

    def test_invalid_comparison_rejected(self):
        """参数: 无。返回: None。异常: 断言失败；不能把开关套给边沿或采用未知比较。"""
        rule = TemporalRule('active', 'data', 'session', 'condition_duration')
        for changes in (dict(duration_comparison='=='), dict(rule_type='rising_edge', duration_comparison='>')):
            with self.assertRaises(ValueError):
                replace(rule, **changes)
