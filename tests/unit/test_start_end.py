"""用明确手算时间验证开始、结束、超时和缺失观测的不同结果。

合成输入使用整数纳秒，验证跨批连续、同刻结束优先、实例隔离及事件编码。
参考/NumPy入口共享有序状态协议，真值直接列在断言中，不以相等替代正确性。
本文件不读写来源或历史项目，不宣称已接通公共配置和旧INI导入。
"""

from dataclasses import replace
import unittest
import numpy as np
from chronaxis.core import StartEndSpec, StartEndDetector
from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.types import QualityFlag as Q, Truth as T
from chronaxis.core.models import Interval
from chronaxis.core.windows import WindowSpec
from chronaxis.core.windows_reference import build_segments_reference
from chronaxis.core.windows_numpy import build_segments_numpy
from chronaxis.results.summary import SummaryEventRow, SummarySegmentRow
from chronaxis.results.codec import encode_row, decode_row


def tick(time, state, **kwargs):
    """构造有明确未知原因的组。参数: 时间/Truth及边界。返回: ConditionTick。异常: 模型错误。"""
    return ConditionTick(time, state, Q.MISSING if state is T.UNKNOWN else Q.NONE, **kwargs)


class StartEndTests(unittest.TestCase):
    """以新开始/结束契约核验正长度活动，旧两阶段含义只作差异依据。"""

    def detector(self, end=12, timeout=5, initial=True, backend='reference', start=0):
        """构造独立实例。参数: 域、时限、初始化、后端。返回: 检测器。异常: 配置错误。"""
        return StartEndDetector(TemporalRule('measure', 'data', 'session', 'condition_duration'),
            start, end, StartEndSpec(timeout, initial), backend=backend)

    def run_points(self, points, *, timeout=5, initial=True, size=1, backend='reference'):
        """按指定批次喂同刻条件。参数: (time,start,end)及配置。返回: Event tuple。异常: 执行错误。"""
        finish = points[-1][0]
        starts = tuple(tick(time, start, terminal=time == finish) for time, start, end in points)
        ends = tuple(tick(time, end, terminal=time == finish) for time, start, end in points)
        detector = self.detector(finish, timeout, initial, backend)
        for index in range(0, len(points), size):
            detector.push(starts[index:index+size], ends[index:index+size])
            detector.push((), ())
        return detector.finish()

    def times(self, events):
        """提取手算比较字段。参数: events。返回: tuple列表。异常: 无。"""
        return [(e.start_ns, e.end_ns, e.status) for e in events]

    def test_user_example_and_exact_timeout(self):
        """0开始2结束，或没有结束时5超时。参数: 无。返回: None。异常: 断言失败。"""
        cases = [([(0,T.TRUE,T.FALSE),(2,T.FALSE,T.TRUE),(12,T.FALSE,T.FALSE)], [(0,2,'closed')]),
                 ([(0,T.TRUE,T.FALSE),(12,T.TRUE,T.FALSE)], [(0,5,'timeout')]),
                 ([(0,T.TRUE,T.FALSE),(5,T.FALSE,T.TRUE),(12,T.FALSE,T.FALSE)], [(0,5,'closed')])]
        for points, expected in cases:
            for backend in ('reference', 'numpy'):
                for size in (1,2,10):
                    self.assertEqual(self.times(self.run_points(points, backend=backend, size=size)), expected)

    def test_explicit_deadline_and_no_periodic_restart(self):
        """定时器本身不重开持续TRUE，drain不清业务状态。参数: 无。返回: None。异常: 断言失败。"""
        detector = self.detector()
        detector.push((tick(0,T.TRUE),), (tick(0,T.FALSE),))
        self.assertEqual(detector.next_deadline_ns, 5)
        detector.push((tick(5,T.TRUE,actual_update=False),), (tick(5,T.FALSE,actual_update=False),))
        self.assertEqual(self.times(detector.drain_events()), [(0,5,'timeout')])
        self.assertIsNone(detector.next_deadline_ns)
        detector.push((tick(12,T.TRUE,terminal=True),), (tick(12,T.FALSE,terminal=True),))
        self.assertEqual(detector.finish(), ())
        with self.assertRaises(ValueError):
            detector.finish()

    def test_new_edge_after_end_and_repeated_start_ignored(self):
        """活动中不排队，结束后只有新边沿重开。参数: 无。返回: None。异常: 断言失败。"""
        points=[(0,T.TRUE,T.FALSE),(1,T.FALSE,T.FALSE),(2,T.TRUE,T.FALSE),(3,T.TRUE,T.TRUE),
                (4,T.TRUE,T.FALSE),(5,T.FALSE,T.FALSE),(6,T.TRUE,T.FALSE),(8,T.FALSE,T.TRUE),(12,T.FALSE,T.FALSE)]
        self.assertEqual(self.times(self.run_points(points)), [(0,3,'closed'),(6,8,'closed')])

    def test_initial_policy_and_unknown_recovery(self):
        """初始TRUE可禁用，缺口恢复不伪造上升。参数: 无。返回: None。异常: 断言失败。"""
        points=[(0,T.TRUE,T.FALSE),(1,T.UNKNOWN,T.FALSE),(2,T.TRUE,T.FALSE),
                (3,T.FALSE,T.FALSE),(4,T.TRUE,T.FALSE),(6,T.FALSE,T.TRUE),(12,T.FALSE,T.FALSE)]
        self.assertEqual(self.times(self.run_points(points, initial=False)), [(4,6,'closed')])
        points=[(0,T.UNKNOWN,T.FALSE),(2,T.TRUE,T.FALSE),(4,T.FALSE,T.TRUE),(12,T.FALSE,T.FALSE)]
        self.assertEqual(self.times(self.run_points(points)), [(2,4,'closed')])

    def test_start_signal_loss_does_not_erase_recorded_start(self):
        """已开始后只需知道end，start失效保诊断但不截断。参数: 无。返回: None。异常: 断言失败。"""
        events=self.run_points([(0,T.TRUE,T.FALSE),(1,T.UNKNOWN,T.FALSE),(2,T.UNKNOWN,T.TRUE),(12,T.FALSE,T.FALSE)])
        self.assertEqual(self.times(events), [(0,2,'closed')])
        self.assertTrue(events[0].dependency_quality & Q.MISSING)
        self.assertEqual(events[0].quality, Q.NONE)

    def test_end_unknown_is_not_timeout_and_requires_new_start(self):
        """end缺失中断，恢复不能接回原活动。参数: 无。返回: None。异常: 断言失败。"""
        events=self.run_points([(0,T.TRUE,T.FALSE),(2,T.TRUE,T.UNKNOWN),(3,T.TRUE,T.FALSE),
                               (5,T.TRUE,T.FALSE),(12,T.TRUE,T.FALSE)])
        self.assertEqual(self.times(events), [(0,2,'interrupted')])
        self.assertEqual(events[0].quality, Q.MISSING)

    def test_same_deadline_unknown_and_real_end(self):
        """截止点未知不能证明没结束；同刻真实end可正常关闭。参数: 无。返回: None。异常: 断言失败。"""
        for terminal, actual, expected in ((False,False,'interrupted'),(True,False,'truncated'),(True,True,'interrupted')):
            detector=self.detector(end=5 if terminal else 12)
            detector.push((tick(0,T.TRUE),),(tick(0,T.FALSE),))
            detector.push((tick(5,T.TRUE,terminal=terminal),),
                (tick(5,T.UNKNOWN,terminal=terminal,actual_update=actual,actual_unknown=actual),))
            self.assertEqual(self.times(detector.drain_events()),[(0,5,expected)])
        self.assertEqual(self.times(self.run_points([(0,T.TRUE,T.FALSE),(5,T.FALSE,T.TRUE)])),[(0,5,'closed')])
        self.assertEqual(self.times(self.run_points([(0,T.TRUE,T.FALSE),(5,T.FALSE,T.FALSE)])),[(0,5,'timeout')])

    def test_unlimited_and_early_source_eof(self):
        """不限时等实际结束；提前结束观测保截断原因。参数: 无。返回: None。异常: 断言失败。"""
        self.assertEqual(self.times(self.run_points([(0,T.TRUE,T.FALSE),(8,T.FALSE,T.TRUE),(12,T.FALSE,T.FALSE)],
                                                  timeout=None)),[(0,8,'closed')])
        self.assertEqual(self.times(self.run_points([(0,T.TRUE,T.FALSE),(3,T.FALSE,T.FALSE)])),[(0,3,'truncated')])
        detector=self.detector()
        detector.push((tick(0,T.TRUE),),(tick(0,T.FALSE),))
        detector.push((tick(3,T.FALSE),),(tick(3,T.UNKNOWN,observation_end=True,actual_update=False),))
        self.assertEqual(self.times(detector.drain_events()),[(0,3,'truncated')])

    def test_simultaneous_zero_length_and_empty_observation(self):
        """开始同刻已结束、真实末点或全未知不伪造活动。参数: 无。返回: None。异常: 断言失败。"""
        for points in ([(0,T.TRUE,T.TRUE),(12,T.TRUE,T.FALSE)],
                       [(0,T.FALSE,T.FALSE),(12,T.TRUE,T.FALSE)],
                       [(0,T.UNKNOWN,T.UNKNOWN),(12,T.UNKNOWN,T.UNKNOWN)],[(0,T.TRUE,T.FALSE)]):
            self.assertEqual(self.run_points(points), ())

    def test_instance_and_int64_boundary(self):
        """实例隔离且域外时限不回绕。参数: 无。返回: None。异常: 断言失败。"""
        detector=self.detector()
        detector.push((tick(0,T.TRUE),),(tick(0,T.FALSE),))
        other=self.detector()
        self.assertIsNone(other.active_start)
        end=2**63-1; beginning=end-3
        detector=self.detector(start=beginning,end=end,timeout=10)
        detector.push((tick(beginning,T.TRUE),),(tick(beginning,T.FALSE),))
        self.assertIsNone(detector.next_deadline_ns)
        detector.push((tick(end,T.FALSE,terminal=True),),(tick(end,T.FALSE,terminal=True),))
        self.assertEqual(self.times(detector.finish()),[(beginning,end,'truncated')])

    def test_invalid_spec_and_pair_protocol(self):
        """非法时限、错组、缺末点明确拒绝。参数: 无。返回: None。异常: 断言失败。"""
        for value in (0,-1,True,1.5,2**63):
            with self.assertRaises((ValueError,TypeError,OverflowError)):
                StartEndSpec(value)
        self.assertEqual(StartEndSpec(np.int64(5)).timeout_ns,5)
        with self.assertRaises(TypeError):
            StartEndSpec(5,1)
        with self.assertRaises(ValueError):
            self.detector().push((tick(0,T.TRUE),),())
        with self.assertRaises(ValueError):
            self.detector().finish()
        detector=self.detector()
        detector.push((tick(0,T.TRUE),),(tick(0,T.FALSE),))
        with self.assertRaises(ValueError):
            detector.push((tick(0,T.FALSE),),(tick(0,T.FALSE),))

    def test_timeout_survives_windows_and_wire(self):
        """timeout原样进入片段和结果编码，不伪装closed。参数: 无。返回: None。异常: 断言失败。"""
        events=self.run_points([(0,T.TRUE,T.FALSE),(12,T.TRUE,T.FALSE)])
        event=events[0]
        row=SummaryEventRow(0,event.rule.dataset_id,'entity',event.rule.session_id,event.rule.rule_id,
            event.event_id,event.start_ns,event.confirmed_ns,event.end_ns,event.status,event.trigger_kind,event.quality)
        self.assertEqual(decode_row(encode_row(row,max_bytes=65536),max_bytes=65536),row)
        for build in (build_segments_reference,build_segments_numpy):
            segments=build(events,WindowSpec('window','measure','activity'),Interval(0,12))
            self.assertEqual(segments[0].event_statuses,('timeout',))
            segment=segments[0]
            row=SummarySegmentRow(0,segment.dataset_id,'entity',segment.session_id,segment.window.window_id,
                segment.segment_id,segment.actual.start_ns,segment.actual.end_ns,segment.status,segment.parent_event_ids,segment.quality)
            self.assertEqual(decode_row(encode_row(row,max_bytes=65536),max_bytes=65536),row)
        # 点事件不能借新增状态伪装超时活动。
        with self.assertRaises(ValueError):
            replace(event,event_type='point',end_ns=None)
        with self.assertRaises(ValueError):
            replace(event,quality=Q.MISSING)

    def test_continuous_end_boundary_does_not_wait_next_point(self):
        """右侧结束条件已真时按当前边界关闭。参数: 无。返回: None。异常: 断言失败。"""
        detector=self.detector()
        detector.push((tick(0,T.TRUE),),(tick(0,T.FALSE),))
        detector.push((tick(2,T.FALSE),),(tick(2,T.TRUE,point_state=T.FALSE),))
        self.assertEqual(self.times(detector.drain_events()),[(0,2,'closed')])

    def test_initial_constant_has_no_signal_update(self):
        """常量已有已知证据即可按首次策略启动，末点仍不新建活动。参数: 无。返回: None。异常: 断言失败。"""
        detector=self.detector()
        detector.push((tick(0,T.TRUE,actual_update=False),),(tick(0,T.FALSE,actual_update=False),))
        detector.push((tick(12,T.TRUE,actual_update=False,terminal=True),),
                      (tick(12,T.FALSE,actual_update=False,terminal=True),))
        self.assertEqual(self.times(detector.finish()),[(0,5,'timeout')])
