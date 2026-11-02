"""以手算时间段验证迟滞和双向防抖，不以两后端相等代替业务真值。

输入为明确纳秒条件组，覆盖中间区间、连续文件的批次切分、计时撤销、
UNKNOWN/TTL/真实末点和实例隔离。只运行新核心，不读写历史项目。
"""

import unittest
import numpy as np
from chronaxis.core.stability import StabilityDetector, StabilitySpec
from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.types import QualityFlag as Q, Truth as T


def tick(time, state, *, terminal=False, quality=Q.NONE, **kwargs):
    """生成有明确原因的测试组。参数: 时间/状态及边界参数。返回: ConditionTick。异常: 模型错误。"""
    return ConditionTick(time, state, quality, terminal=terminal, **kwargs)


class StabilityTests(unittest.TestCase):
    """每例独立创建规则，会话边界与批次边界分别验证。"""

    def detector(self, end=12, enter=0, exit=0, backend='reference', start=0):
        """建立零门槛活动包装。参数: 域/两个防抖时长/后端。返回: 检测器。异常: 配置错误。"""
        return StabilityDetector(TemporalRule('alarm', 'data', 'session', 'condition_duration'),
                                 start, end, StabilitySpec(enter, exit), backend=backend)

    def result(self, detector):
        """压缩已结束活动供手算断言。参数: detector。返回: 时间/状态列表。异常: 缺末点。"""
        return [(e.start_ns, e.confirmed_ns, e.end_ns, e.status) for e in detector.finish()]

    def test_temperature_across_batches(self):
        """85→77跨文件后77→70保持报警至75。参数: 无。返回: None。异常: 断言失败。"""
        entries = tuple(tick(t, s, terminal=t == 12) for t, s in [(0,T.TRUE),(3,T.FALSE),(6,T.FALSE),(9,T.FALSE),(12,T.FALSE)])
        exits = tuple(tick(t, s, terminal=t == 12) for t, s in [(0,T.FALSE),(3,T.FALSE),(6,T.FALSE),(9,T.TRUE),(12,T.TRUE)])
        for backend in ('reference', 'numpy'):
            for size in (1,2,10):
                detector = self.detector(backend=backend)
                for index in range(0, len(entries), size):
                    detector.push(entries[index:index+size], exits[index:index+size])
                    detector.push((), ())
                self.assertEqual(self.result(detector), [(0,0,9,'closed')])

    def test_initial_middle_remains_unknown(self):
        """第一条77不能推断已报警，后来80才能进入。参数: 无。返回: None。异常: 断言失败。"""
        detector = self.detector()
        detector.push((tick(0,T.FALSE),), (tick(0,T.FALSE),))
        self.assertIs(detector.state, T.UNKNOWN)
        detector.push((tick(2,T.TRUE),tick(12,T.FALSE,terminal=True)),
                      (tick(2,T.FALSE),tick(12,T.TRUE,terminal=True)))
        self.assertEqual(self.result(detector), [(2,2,12,'closed')])

    def test_two_debounce_delays_and_no_message_deadline(self):
        """进入等2ns退出等3ns，结束不等下条消息。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference','numpy'):
            detector = self.detector(enter=2, exit=3, backend=backend)
            detector.push((tick(0,T.TRUE),))
            self.assertEqual(detector.next_deadline_ns, 2)
            detector.push((tick(6,T.FALSE),))
            self.assertEqual(detector.next_deadline_ns, 9)
            detector.push((tick(12,T.FALSE,terminal=True),))
            self.assertEqual(self.result(detector), [(2,2,9,'closed')])

    def test_bounce_restarts_timer(self):
        """短暂进出条件撤销计时，不能累计碎片。参数: 无。返回: None。异常: 断言失败。"""
        detector = self.detector(enter=3, exit=2)
        detector.push(tuple(tick(t,s,terminal=t==12) for t,s in
            [(0,T.FALSE),(1,T.TRUE),(2,T.FALSE),(3,T.TRUE),(7,T.FALSE),(8,T.TRUE),(9,T.FALSE),(12,T.FALSE)]))
        self.assertEqual(self.result(detector), [(6,6,11,'closed')])

    def test_middle_cancels_pending_but_preserves_confirmed(self):
        """迟滞中间区间撤销未满防抖，已确认状态保持。参数: 无。返回: None。异常: 断言失败。"""
        detector = self.detector(enter=2, exit=2)
        times = (0,1,3,6,7,8,10,12)
        detector.push(tuple(tick(t,s,terminal=t==12) for t,s in zip(times,(T.TRUE,T.FALSE,T.TRUE,T.FALSE,T.FALSE,T.FALSE,T.FALSE,T.FALSE))),
                      tuple(tick(t,s,terminal=t==12) for t,s in zip(times,(T.FALSE,T.FALSE,T.FALSE,T.FALSE,T.TRUE,T.FALSE,T.TRUE,T.TRUE))))
        self.assertEqual(self.result(detector), [(5,5,12,'closed')])

    def test_unknown_breaks_and_does_not_restore_latch(self):
        """失效打断报警，恢复77保持未知，重新80才再报警。参数: 无。返回: None。异常: 断言失败。"""
        detector = self.detector()
        detector.push((tick(0,T.TRUE),tick(4,T.UNKNOWN,quality=Q.STALE),tick(5,T.FALSE),tick(8,T.TRUE),tick(12,T.TRUE,terminal=True)),
                      (tick(0,T.FALSE),tick(4,T.UNKNOWN,quality=Q.STALE),tick(5,T.FALSE),tick(8,T.FALSE),tick(12,T.FALSE,terminal=True)))
        events = detector.finish()
        self.assertEqual([(e.start_ns,e.end_ns,e.status) for e in events], [(0,4,'interrupted'),(8,12,'truncated')])
        self.assertTrue(events[0].quality & Q.STALE)

    def test_exact_threshold_and_terminal(self):
        """恰好达到进入门槛但同刻退出不造零长度报警；退出门槛到EOF仍闭合。参数: 无。返回: None。异常: 断言失败。"""
        detector = self.detector(enter=3)
        detector.push((tick(0,T.TRUE),tick(3,T.FALSE),tick(12,T.FALSE,terminal=True)))
        self.assertEqual(self.result(detector), [])
        detector = self.detector(enter=12)
        detector.push((tick(0,T.TRUE),tick(12,T.TRUE,terminal=True)))
        self.assertEqual(self.result(detector), [])
        detector = self.detector(exit=3)
        detector.push((tick(0,T.TRUE),tick(9,T.FALSE),tick(12,T.UNKNOWN,terminal=True,quality=Q.MISSING,actual_update=False)))
        self.assertEqual(self.result(detector), [(0,0,12,'closed')])

    def test_terminal_real_exit_vs_waiting(self):
        """真实末点退出0延时为closed，尚需等待则truncated。参数: 无。返回: None。异常: 断言失败。"""
        for delay, expected in ((0,'closed'),(1,'truncated')):
            detector = self.detector(exit=delay)
            detector.push((tick(0,T.TRUE),tick(12,T.UNKNOWN,terminal=True,quality=Q.MISSING,
                           point_state=T.FALSE,point_quality=Q.NONE)))
            self.assertEqual(self.result(detector), [(0,0,12,expected)])

    def test_unknown_at_terminal_and_ttl(self):
        """真实末点解码失败为interrupted；单纯EOF含TTL为truncated。参数: 无。返回: None。异常: 断言失败。"""
        for actual, status in ((True,'interrupted'),(False,'truncated')):
            detector = self.detector()
            detector.push((tick(0,T.TRUE),tick(12,T.UNKNOWN,terminal=True,quality=Q.STALE,
                           actual_update=actual,actual_unknown=actual)))
            self.assertEqual(self.result(detector), [(0,0,12,status)])

    def test_invalid_inputs_and_overlap(self):
        """配置/排序/矛盾条件明确拒绝。参数: 无。返回: None。异常: 断言失败。"""
        for value in (-1,True,1.5,2**63):
            with self.assertRaises((ValueError,TypeError,OverflowError)):
                StabilitySpec(value,0)
        with self.assertRaisesRegex(ValueError,'同时成立'):
            self.detector().push((tick(0,T.TRUE),),(tick(0,T.TRUE),))
        with self.assertRaises(ValueError):
            self.detector().push((tick(0,T.TRUE),),(tick(0,T.FALSE),tick(1,T.FALSE)))
        with self.assertRaises(ValueError):
            self.detector().finish()

    def test_integer_range_isolation_and_drain(self):
        """int64末端不回绕，实例与已取结果互不影响。参数: 无。返回: None。异常: 断言失败。"""
        start,end=2**63-8,2**63-1
        detector=self.detector(start=start,end=end,enter=10)
        detector.push((tick(np.int64(start),T.TRUE),))
        self.assertIsNone(detector.next_deadline_ns)
        detector.push((tick(np.int64(end),T.TRUE,terminal=True),))
        self.assertEqual(self.result(detector),[])
        a,b=self.detector(),self.detector()
        a.push((tick(0,T.TRUE),tick(4,T.FALSE)))
        first=a.drain_events()
        self.assertEqual(len(first),1)
        self.assertIs(b.state,T.UNKNOWN)
        a.push((tick(8,T.TRUE),tick(12,T.TRUE,terminal=True)))
        self.assertEqual(self.result(a),[(8,8,12,'truncated')])
        self.assertEqual(first[0].end_ns,4)


if __name__ == '__main__':
    unittest.main()
