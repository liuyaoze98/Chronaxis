"""用手算活动、点和真实观测范围核对两个独立窗口后端。

输入为合成已完成Event与明确WindowSpec，输出为unittest断言；覆盖T15/T16、
T45/T55的片段范围、scope、请求覆盖、EOF、UNKNOWN、精确deadline和溢出。
旧writer不运行，正确性真值来自手算，不能把新片段结果当旧文件行为已修复。
所有测试只用内存，不写文件或证明完整AnalysisRunner预算。
"""

# 冻结模型变体保留旧事实，浮点覆盖只允许最后舍入差。
from dataclasses import replace
import unittest
# 合法NumPy整数容器不能在身份生成时失败或进入固定宽算术。
import numpy as np
# 窗口模型、独立扩展与归约后端。
from chronaxis.core.windows import WindowSpec, Segment
from chronaxis.core.windows_reference import build_segments_reference
from chronaxis.core.windows_numpy import build_segments_numpy
# 原始活动/点模型用明示事实构造，规则作用域保持。
from chronaxis.core.temporal import TemporalRule, make_event
from chronaxis.core.models import Interval
from chronaxis.core.types import QualityFlag as Q
from chronaxis.timebase.conversion import INT64_MIN, INT64_MAX
# 两独立原行指标入口用于额外核对event与segment统计口径。
from chronaxis.core.expression import compile_expression
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.calculations_memory_reference import compute_memory_reference
from chronaxis.core.calculations_memory_numpy import compute_memory_numpy
from test_calculations import _memory


def activity(start, end, *, status='closed', quality=Q.NONE, diagnostic=Q.NONE):
    """构造立即确认且边界已知的合成活动，不制造旧检测输出。

    参数: start/end为纳秒；status/quality/diagnostic明确结束与依赖原因。
    返回: Event，onset=confirmed，原活动边界不可变。
    异常: 模型检查错误传播。
    """
    # 同一明示合成规则，ID由真实时间事实生成。
    return make_event(TemporalRule('active', 'dataset', 'session', 'condition_duration'), start, start, end,
                      status, quality, diagnostic)


class WindowTests(unittest.TestCase):
    """核对原活动不变和片段关联完整；每项测试使用全新局部输入。"""

    def compare(self, events, spec, observation):
        """独立执行窗口后端，比较全部模型事实和覆盖比例。

        参数: events真实合成事件tuple；spec声明；observation真实域。
        返回: 参考Segment tuple供手算断言。
        异常: 数值、ID、质量、原关联或其他字段差异由断言报告。
        """
        reference = build_segments_reference(events, spec, observation)
        array = build_segments_numpy(events, spec, observation)
        self.assertEqual(len(reference), len(array))
        # 大int64跨度转换float的最后舍入可不同，所有整数事实/ID仍严格相同。
        for left, right in zip(reference, array):
            self.assertAlmostEqual(left.requested_coverage, right.requested_coverage, delta=1e-15)
            self.assertEqual(left, replace(right, requested_coverage=left.requested_coverage))
        return reference

    def test_t15_t16_requested_actual_and_half_open(self):
        """[10,15)前5后10请求[5,25)，实际[5,20)，覆盖0.75。

        参数: 无；单位纳秒，等比例代表设计秒级边界。
        返回: None。
        异常: 请求/裁剪或半开成员关系不符由断言报告。
        """
        event = activity(10, 15)
        segment, = self.compare((event,), WindowSpec('context', 'active', 'activity', 5, 10), Interval(0, 20))
        self.assertEqual((segment.requested, segment.actual, segment.requested_coverage, segment.status),
                         (Interval(5, 25), Interval(5, 20), .75, 'partial'))
        # 边界帧5与19在实际窗口内，20排除；不调用旧writer。
        self.assertEqual(tuple(segment.actual.contains(time) for time in (5, 19, 20)), (True, True, False))
        self.assertEqual(segment.parent_event_ids, (event.event_id,))
        self.assertEqual((event.start_ns, event.end_ns), (10, 15))

    def test_t45_events_and_segment_energy(self):
        """两段真实活动各4000J，退出延迟片段含FALSE上下文共24000J。

        参数: 无；合成恒定4000W、0—6秒观测。
        返回: None。
        异常: 活动数量、scope或独立数值差异由断言报告。
        """
        events = (activity(0, 1_000_000_000), activity(2_000_000_000, 3_000_000_000))
        spec = WindowSpec('single', 'active', 'activity', merge='exit_delay', exit_delay_ns=3_000_000_000)
        segment, = self.compare(events, spec, Interval(0, 6_000_000_000))
        self.assertEqual(segment.requested, Interval(0, 6_000_000_000))
        self.assertEqual(segment.parent_event_ids, tuple(event.event_id for event in events))
        # 指标使用不同明确scope，不能把上下文写回两个原活动。
        root = compile_expression('power', _memory(rows=((0, {'raw': 4000.}), (6_000_000_000, {'raw': 0.})),
                                                    age=10_000_000_000, end=6_000_000_000))
        for event in events:
            request = CalculationDefinition('energy', 'integral', Interval(event.start_ns, event.end_ns), scope='event')
            result = compute_memory_reference(root, request)
            self.assertEqual(result, compute_memory_numpy(root, request))
            self.assertEqual(result.value, 4000.)
        request = CalculationDefinition('energy', 'integral', segment.actual, scope='segment')
        result = compute_memory_reference(root, request)
        self.assertEqual(result, compute_memory_numpy(root, request))
        self.assertEqual(result.value, 24000.)
        self.assertEqual(tuple((event.start_ns, event.end_ns) for event in events), ((0, 1_000_000_000), (2_000_000_000, 3_000_000_000)))

    def test_t55_deadline_reentry_and_pre_only_overlap(self):
        """退出deadline相等重入合并，仅pre重叠但真实间隔超delay保持两片段。

        参数: 无；立即确认活动及三纳秒退出延迟。
        返回: None。
        异常: 错误按pre重叠扩展分组或deadline边界差异由断言报告。
        """
        spec = WindowSpec('single', 'active', 'activity', merge='exit_delay', exit_delay_ns=3)
        segments = self.compare((activity(0, 1), activity(4, 5)), spec, Interval(0, 10))
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].requested, Interval(0, 8))
        # 请求[-10,4)与[-4,10)重叠，但真实活动间隔5>3，不能合并single。
        segments = self.compare((activity(0, 1), activity(6, 7)), replace(spec, pre_ns=10), Interval(0, 10))
        self.assertEqual(len(segments), 2)
        self.assertEqual(tuple(segment.requested for segment in segments), (Interval(-10, 4), Interval(-4, 10)))
        self.assertEqual(tuple(len(segment.parent_event_ids) for segment in segments), (1, 1))

    def test_unknown_gap_and_precise_exit(self):
        """UNKNOWN中断保留两原活动及质量，退出时间精确而不等下一帧。

        参数: 无；1纳秒中断、2纳秒重入、退出delay3。
        返回: None。
        异常: 事件结束状态被合并篡改或扩展重复post由断言报告。
        """
        first = activity(0, 1, status='interrupted', quality=Q.STALE, diagnostic=Q.STALE)
        second = activity(2, 3)
        spec = WindowSpec('single', 'active', 'activity', merge='exit_delay', exit_delay_ns=3)
        segment, = self.compare((first, second), spec, Interval(0, 10))
        self.assertEqual(segment.event_statuses, ('interrupted', 'closed'))
        self.assertTrue(segment.quality & Q.STALE)
        self.assertEqual(segment.requested, Interval(0, 6))
        # LC03单段1秒退出+3秒delay应为4，不能等4.1帧或再加3。
        segment, = self.compare((activity(0, 1),), spec, Interval(0, 10))
        self.assertEqual(segment.requested.end_ns, 4)

    def test_regular_overlap_and_adjacent_policies(self):
        """普通重叠、相邻与none政策分别分组，关联顺序稳定。

        参数: 无；两个活动各扩一纳秒，请求相邻。
        返回: None。
        异常: 政策混用或身份不稳定由断言报告。
        """
        events = (activity(0, 1), activity(2, 3))
        spec = WindowSpec('context', 'active', 'activity', post_ns=1)
        for policy, count in (('none', 2), ('overlap', 2), ('overlap_and_adjacent', 1)):
            segments = self.compare(events, replace(spec, merge=policy), Interval(0, 5))
            self.assertEqual(len(segments), count)
        # 真正重叠允许链式合并，结果范围取完整并集而非最后请求。
        segment, = self.compare(events, replace(spec, post_ns=2, merge='overlap'), Interval(0, 5))
        self.assertEqual(segment.requested, Interval(0, 5))
        self.assertEqual(segment.status, 'complete')

    def test_point_terminal_empty_and_status_preservation(self):
        """末点窗口保存请求但实际零时长，空事件无伪造片段，EOF状态保留。

        参数: 无；rising末点及truncated活动。
        返回: None。
        异常: point被伪造面积或EOF状态改变由断言报告。
        """
        point = make_event(TemporalRule('edge', 'dataset', 'session', 'rising_edge'), 5, 5, None, 'point', Q.NONE, Q.NONE, trigger='rising_edge')
        spec = WindowSpec('context', 'edge', 'point', post_ns=2)
        segment, = self.compare((point,), spec, Interval(0, 5))
        self.assertEqual((segment.requested, segment.actual, segment.status, segment.requested_coverage),
                         (Interval(5, 7), Interval(5, 5), 'empty', 0.))
        self.assertEqual(self.compare((), spec, Interval(0, 5)), ())
        event = activity(0, 5, status='truncated', quality=Q.MISSING)
        segment, = self.compare((event,), WindowSpec('context', 'active', 'activity', post_ns=3), Interval(0, 5))
        self.assertEqual((segment.event_statuses, segment.status, segment.requested_coverage), (('truncated',), 'partial', 5/8))

    def test_large_absolute_nanosecond_and_stable_identity(self):
        """大绝对坐标仍保留一纳秒边界；依赖诊断不改片段时间身份。

        参数: 无；合法int64域内合成活动。
        返回: None。
        异常: 时间精度、覆盖或身份差异由断言报告。
        """
        origin = 8_000_000_000_000_000_000
        event = activity(origin+2, origin+3)
        spec = WindowSpec('context', 'active', 'activity', pre_ns=1, post_ns=1)
        observation = Interval(origin, origin+3)
        segment, = self.compare((event,), spec, observation)
        self.assertEqual((segment.requested, segment.actual, segment.requested_coverage),
                         (Interval(origin+1, origin+4), Interval(origin+1, origin+3), 2/3))
        # 相同事件时间事实保留ID，但原依赖诊断仍出现在片段质量中。
        changed, = self.compare((replace(event, dependency_quality=Q.MISSING),), spec, observation)
        self.assertEqual(segment.segment_id, changed.segment_id)
        self.assertTrue(changed.quality & Q.MISSING)

    def test_expansion_and_span_overflow(self):
        """端点和请求跨度超int64均在两个后端拒绝，不wrap。

        参数: 无；合法原事件但非法扩展。
        返回: None。
        异常: 未拒绝溢出或两后端异常类型差异由断言报告。
        """
        cases = ((activity(INT64_MIN+1, INT64_MIN+2), WindowSpec('context', 'active', 'activity', pre_ns=2), Interval(INT64_MIN+1, INT64_MIN+2)),
                 (activity(INT64_MAX-2, INT64_MAX-1), WindowSpec('context', 'active', 'activity', post_ns=2), Interval(INT64_MAX-2, INT64_MAX-1)),
                 (activity(-1, 1), WindowSpec('context', 'active', 'activity', pre_ns=INT64_MAX-2, post_ns=3), Interval(-1, 1)))
        for events, spec, observation in cases:
            for build in (build_segments_reference, build_segments_numpy):
                with self.assertRaises(OverflowError):
                    build((events,), spec, observation)

    def test_numpy_time_parameters_and_tiny_positive_coverage(self):
        """合法np.int64时间规范为原生int，极小正覆盖不能伪报成零。

        参数: 无；模型参数及1/MAX覆盖边界。
        返回: None。
        异常: 合法身份生成失败或错误覆盖未拒绝由断言报告。
        """
        spec = WindowSpec('context', 'active', 'activity', pre_ns=np.int64(1), post_ns=np.int64(2))
        self.assertIs(type(spec.pre_ns), int)
        self.assertIs(type(spec.post_ns), int)
        segment, = self.compare((activity(1, 2),), spec, Interval(0, 4))
        self.assertEqual(segment.requested_coverage, 1.)
        delay = WindowSpec('single', 'active', 'activity', merge='exit_delay', exit_delay_ns=np.int64(2))
        self.assertIs(type(delay.exit_delay_ns), int)
        self.compare((activity(1, 2),), delay, Interval(0, 4))
        # 1/MAX正常可表示为float64正数；模型相对容差不掩盖其观测事实。
        spec = WindowSpec('context', 'active', 'activity', post_ns=INT64_MAX-1)
        segment, = self.compare((activity(0, 1),), spec, Interval(0, 1))
        self.assertGreater(segment.requested_coverage, 0.)
        with self.assertRaises(ValueError):
            replace(segment, requested_coverage=0.)

    def test_window_and_input_protocol_errors(self):
        """拒绝非法政策、双重post、点零长度、错规则、回退、重复和跨会话。

        参数: 无；故意无效声明与已完成事件输入。
        返回: None。
        异常: 任何错误配置被接受时断言失败。
        """
        # 配置错误不能被结果未知状态掩盖。
        for kwargs in ({'pre_ns': -1}, {'merge': 'future'}, {'merge': 'exit_delay', 'post_ns': 1, 'exit_delay_ns': 3}, {'exit_delay_ns': 3}):
            with self.assertRaises(ValueError):
                WindowSpec('context', 'active', 'activity', **kwargs)
        with self.assertRaises(ValueError):
            WindowSpec('context', 'active', 'point')
        first, second = activity(0, 1), activity(2, 3)
        spec = WindowSpec('context', 'active', 'activity')
        for build in (build_segments_reference, build_segments_numpy):
            for events in ((second, first), (first, first), (first, activity(0, 2)),
                           (first, replace(second, rule=replace(second.rule, session_id='other')))):
                with self.assertRaises(ValueError):
                    build(events, spec, Interval(0, 5))
            with self.assertRaises(ValueError):
                build((first,), replace(spec, event_rule_id='other'), Interval(0, 5))
        # Segment不能声称错误覆盖或丢失全部原事件关联。
        segment, = self.compare((first,), spec, Interval(0, 5))
        self.assertIsInstance(segment, Segment)
        with self.assertRaises(ValueError):
            replace(segment, requested_coverage=.5)
        with self.assertRaises(ValueError):
            replace(segment, parent_event_ids=())


# 直接运行同一验收集，不产生缓存或旧目录副作用。
if __name__ == '__main__':
    unittest.main()
