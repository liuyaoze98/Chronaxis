"""核对真实start_only边沿、固定窗口抑制、UNKNOWN与跨批隔离。

输入是明示布尔原行、有效期和会话范围；两个原行到事件链独立运行，
输出完整Event和Segment的unittest断言。手算触发时刻覆盖T55与LC06的状态部分。
到期不制造边沿，被抑制触发不排队，真实末点只产生point而不增加持续时长。
测试不读取旧日志，不证明旧入口修复、生产有界历史或整个AnalysisRunner接线。
"""

# 冻结模型变体用于明确策略/窗口错误，不修改输入。
from dataclasses import replace
import unittest
# 合法数值容器输入需要规范为Python精确整数后参与宽域deadline比较。
import numpy as np
# 明示合成原行夹具不包含被测检测算法。
from test_temporal import _memory
from chronaxis.core.temporal import TemporalRule
from chronaxis.core.temporal_memory_reference import detect_memory_reference
from chronaxis.core.temporal_memory_numpy import detect_memory_numpy
from chronaxis.core.windows import WindowSpec
from chronaxis.core.windows_reference import build_segments_reference
from chronaxis.core.windows_numpy import build_segments_numpy
from chronaxis.core.models import Interval
from chronaxis.core.types import QualityFlag as Q
from chronaxis.timebase.conversion import INT64_MAX


class StartOnlyTests(unittest.TestCase):
    """逐字段比较独立链与手算触发；状态只属于一次检测实例。"""

    def compare(self, rows, rule, *, end=10, age=100):
        """在多种完整时间组切批下核对两个独立原行链。

        参数: rows原纳秒/布尔字段序列；rule当前声明；end/age明确纳秒。
        返回: 参考Event tuple，所有切批结果已严格核对。
        异常: 边界、质量、ID或跨批不一致由断言报告。
        """
        # 原信号仅依赖x，另一列更新不会伪造x的实际边沿。
        root = _memory(rows, end=end, age=age)
        expected = None
        for batch in (1, 2, 3, 5, 100):
            reference = detect_memory_reference(root, rule, batch_rows=batch)
            array = detect_memory_numpy(root, rule, batch_rows=batch)
            self.assertEqual(reference, array)
            if expected is None:
                expected = reference
            else:
                self.assertEqual(reference, expected)
        return expected

    def test_t55_initial_suppression_no_queue_and_new_edge(self):
        """初始触发0，窗口内2/6边沿丢弃，到期7不重触发，之后9新边沿触发。

        参数: 无；固定窗口三纳秒、原布尔更新0—10。
        返回: None。
        异常: 手算或切批/独立后端不符由断言报告。
        """
        values = (True, False, True, False, True, False, True, True, False, True, False)
        rows = tuple((time, {'x': value}) for time, value in enumerate(values))
        rule = TemporalRule('rule', 'dataset', 'session', 'start_only', emit_initial=True, window_duration_ns=3)
        events = self.compare(rows, rule)
        self.assertEqual(tuple(event.start_ns for event in events), (0, 4, 9))
        self.assertEqual(tuple(event.trigger_kind for event in events), ('initial', 'start_only', 'start_only'))
        self.assertTrue(all(event.end_ns is None and event.status == 'point' for event in events))
        # 请求范围从触发时刻固定结束，pre只扩前文，不增加抑制时长或合并。
        window = WindowSpec('context', 'rule', 'point', pre_ns=1, post_ns=3)
        segments = build_segments_reference(events, window, Interval(0, 10))
        self.assertEqual(segments, build_segments_numpy(events, window, Interval(0, 10)))
        self.assertEqual(tuple(segment.requested for segment in segments), (Interval(-1, 3), Interval(3, 7), Interval(8, 12)))
        self.assertEqual(segments[-1].requested_coverage, .5)
        # 省略初始策略后首次TRUE不触发，已知FALSE→TRUE在2/6/9触发。
        events = self.compare(rows, replace(rule, emit_initial=False))
        self.assertEqual(tuple(event.start_ns for event in events), (2, 6, 9))

    def test_right_endpoint_real_rising_and_continuous_true(self):
        """抑制右端3恰好真实rising可触发，持续TRUE跨到期不周期触发。

        参数: 无；初始TRUE与固定三纳秒窗口。
        返回: None。
        异常: 半开抑制边界或自动重触发错误由断言报告。
        """
        rule = TemporalRule('rule', 'dataset', 'session', 'start_only', emit_initial=True, window_duration_ns=3)
        events = self.compare(((0, {'x': True}), (1, {'x': False}), (3, {'x': True}), (10, {'x': True})), rule)
        self.assertEqual(tuple(event.start_ns for event in events), (0, 3))
        events = self.compare(((0, {'x': True}), (3, {'x': True}), (6, {'x': True}), (10, {'x': True})), rule)
        self.assertEqual(tuple(event.start_ns for event in events), (0,))

    def test_unknown_ttl_recovery_and_condition_only_updates(self):
        """TTL未知恢复不构成rising，其他列独自更新不影响实际x边沿。

        参数: 无；x一纳秒有效期，1秒等比例表示纳秒边界。
        返回: None。
        异常: UNKNOWN被当FALSE或初始策略重复由断言报告。
        """
        rule = TemporalRule('rule', 'dataset', 'session', 'start_only', emit_initial=True, window_duration_ns=3)
        rows = ((0, {'x': True, 'y': False}), (1, {'y': True}), (2, {'x': True}),
                (3, {'x': False}), (4, {'x': True}), (10, {'x': False}))
        # age=1时3秒FALSE到4秒恰好过期，更新前旧连续FALSE仍提供真实边沿证据。
        events = self.compare(rows, rule, age=1)
        self.assertEqual(tuple(event.start_ns for event in events), (0, 4))
        self.assertTrue(all(event.quality == Q.NONE for event in events))

    def test_terminal_point_and_new_session_state(self):
        """真实EOF rising可以触发点，实际窗口零时长；新实例不继承抑制状态。

        参数: 无；五纳秒真实域、固定两纳秒窗口。
        返回: None。
        异常: 末点或会话隔离错误由断言报告。
        """
        rule = TemporalRule('rule', 'dataset', 'session', 'start_only', window_duration_ns=2)
        rows = ((0, {'x': False}), (1, {'x': True}), (4, {'x': False}), (5, {'x': True}))
        events = self.compare(rows, rule, end=5)
        self.assertEqual(tuple(event.start_ns for event in events), (1, 5))
        spec = WindowSpec('context', 'rule', 'point', post_ns=2)
        segments = build_segments_reference(events, spec, Interval(0, 5))
        self.assertEqual(segments, build_segments_numpy(events, spec, Interval(0, 5)))
        self.assertEqual((segments[-1].actual, segments[-1].requested_coverage, segments[-1].status), (Interval(5, 5), 0., 'empty'))
        # 同一声明重复完整分析使用新检测器，结果和ID一致，不继承blocked_until。
        self.assertEqual(events, self.compare(rows, rule, end=5))

    def test_numpy_duration_normalization_and_wide_deadline(self):
        """np.int64(MAX)固定抑制时间保留精确值，域外deadline不回绕或序列化失败。

        参数: 无；100纳秒触发后102再次rising，但固定窗口远大于观测域。
        返回: None。
        异常: 身份失败、回绕导致重复触发或双后端差异由断言报告。
        """
        rule = TemporalRule('rule', 'dataset', 'session', 'start_only', window_duration_ns=np.int64(INT64_MAX))
        self.assertIs(type(rule.window_duration_ns), int)
        rows = ((0, {'x': False}), (100, {'x': True}), (101, {'x': False}), (102, {'x': True}), (105, {'x': False}))
        events = self.compare(rows, rule, end=105, age=1000)
        self.assertEqual(tuple(event.start_ns for event in events), (100,))
        # 原生整数同一声明得到相同时间事实和ID。
        self.assertEqual(events, self.compare(rows, replace(rule, window_duration_ns=INT64_MAX), end=105, age=1000))

    def test_rule_window_and_new_identity_validation(self):
        """固定时长必须正且只属于start_only，窗口须保持该时长与none政策。

        参数: 无；故意错误配置以及同触发不同固定时长。
        返回: None。
        异常: 错误配置被接受或新模式身份未隔离由断言报告。
        """
        for duration in (0, -1):
            with self.assertRaises(ValueError):
                TemporalRule('rule', 'dataset', 'session', 'start_only', window_duration_ns=duration)
        with self.assertRaises(TypeError):
            TemporalRule('rule', 'dataset', 'session', 'start_only', window_duration_ns=True)
        with self.assertRaises(ValueError):
            TemporalRule('rule', 'dataset', 'session', 'rising_edge', window_duration_ns=3)
        rule = TemporalRule('rule', 'dataset', 'session', 'start_only', emit_initial=True, window_duration_ns=3)
        rows = ((0, {'x': True}), (10, {'x': True}))
        events = self.compare(rows, rule)
        changed = self.compare(rows, replace(rule, window_duration_ns=4))
        self.assertNotEqual(events[0].event_id, changed[0].event_id)
        # 新模式不能伪装为falling或在未声明初始化时构造initial点。
        with self.assertRaises(ValueError):
            replace(events[0], trigger_kind='falling_edge')
        with self.assertRaises(ValueError):
            replace(events[0], rule=replace(rule, emit_initial=False))
        for build in (build_segments_reference, build_segments_numpy):
            with self.assertRaises(ValueError):
                build(events, WindowSpec('context', 'rule', 'point', post_ns=4), Interval(0, 10))
            with self.assertRaises(ValueError):
                build(events, WindowSpec('context', 'rule', 'point', post_ns=3, merge='overlap'), Interval(0, 10))


# 直接运行同一验收集，不创建文件或跨任务状态。
if __name__ == '__main__':
    unittest.main()
