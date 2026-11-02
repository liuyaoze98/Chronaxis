"""用手算窗口和真实多规则事件验预算查询，数值仍走两个独立内核。

专项验证请求/实际/父关联、完整定位预算、申请/交付/释放取消及无累计登记。
小完整Event tuple只是已声明夹具，不宣称跨批片段分组或整个AnalysisRunner流式完成。
"""

# 合成真实活动事实复用既有测试函数，导入模块别名不重复发现旧TestCase。
import unittest
from unittest.mock import patch
from dataclasses import replace
import test_windows as window_facts
import test_stream_condition_evidence as real_queries
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.temporal import TemporalRule, make_event
from chronaxis.core.windows import WindowSpec
from chronaxis.core.types import QualityFlag as Q, SignalDType
from chronaxis.execution.windows import WindowQueries
from chronaxis.execution.timeline_multi import MultiRuleTimeline, TimelineRule
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef
from chronaxis.timebase.conversion import INT64_MIN, INT64_MAX, TimeOverflowError


class WindowQueryTests(unittest.TestCase):
    """每测试独立预算，所有新owner/批关闭且最终RAM归零。"""

    def setUp(self):
        """建立账本。参数: 无。返回: None。异常: 预算配置错误传播。"""
        self.budget = ResourceBudget()
        self.addCleanup(self.assert_budget_empty)

    def assert_budget_empty(self):
        """核对最后清理。参数: 无。返回: None。异常: 漏账AssertionError。"""
        self.assertEqual(self.budget.ram_bytes, 0)

    def owner(self, backend):
        """建立查询。参数: backend。返回: WindowQueries。异常: 构造错误传播。"""
        owner = WindowQueries(self.budget, backend=backend)
        self.addCleanup(owner.close)
        return owner

    def cancel_once(self, original, after):
        """只在首次真实操作前或返回后取消，之后保持真实清理。

        参数: original预算/登记函数、after是否执行成功后取消。返回: 故障函数。
        异常: 目标首次KeyboardInterrupt；不吞其他原错误。
        """
        used = False

        def invoke(*args):
            """注入唯一取消。参数: 原参数。返回: 原结果。异常: 首次KeyboardInterrupt。"""
            nonlocal used
            if not used:
                used = True
                if after:
                    original(*args)
                raise KeyboardInterrupt('window-query-lifecycle')
            return original(*args)

        return invoke

    def test_requested_actual_and_four_merge_policies_match_hand_truth(self):
        """扩展/裁剪和四政策保留父活动，真实间隔相等优先重入，pre不扩大single。

        参数: 无，合成纳秒活动。返回: None。异常: 手算或双后端不符断言失败。
        """
        event = window_facts.activity(10, 15)
        pairs = (window_facts.activity(1, 2), window_facts.activity(2, 3))
        references = []
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend)
            result = owner.build((event,), WindowSpec('context', 'active', 'activity', 5, 10), Interval(0, 20))
            segment, = result.segments
            self.assertEqual((segment.requested, segment.actual, segment.requested_coverage, segment.status),
                             (Interval(5, 25), Interval(5, 20), .75, 'partial'))
            references.append(segment)
            result.close()
            for merge, ranges in (('none', ((1, 2), (2, 3))), ('overlap', ((1, 2), (2, 3))),
                                  ('overlap_and_adjacent', ((1, 3),)), ('exit_delay', ((1, 5),))):
                spec = WindowSpec('merge', 'active', 'activity', merge=merge,
                                  exit_delay_ns=2 if merge == 'exit_delay' else None)
                result = owner.build(pairs, spec, Interval(0, 10))
                self.assertEqual(tuple((s.requested.start_ns, s.requested.end_ns) for s in result.segments), ranges)
                self.assertEqual(tuple(parent for s in result.segments for parent in s.parent_event_ids),
                                 tuple(event.event_id for event in pairs))
                result.close()
            # 6ns重入晚于前段2+2ns，尽管pre造成请求重叠仍保持两个single片段。
            separate = (pairs[0], window_facts.activity(6, 7))
            result = owner.build(separate, WindowSpec('single', 'active', 'activity', 10,
                merge='exit_delay', exit_delay_ns=2), Interval(0, 10))
            self.assertEqual(len(result.segments), 2)
            result.close()
        self.assertEqual(references[0], references[1])
        self.assertEqual((event.start_ns, event.end_ns), (10, 15))

    def test_unknown_eof_parents_and_start_only_point_keep_scope(self):
        """未知和EOF原状态不因片段合并消失，固定点窗口只裁剪真实观测。

        参数: 无。返回: None。异常: 活动被改写或虚构观测断言失败。
        """
        parents = (window_facts.activity(5, 6, status='interrupted', quality=Q.STALE, diagnostic=Q.MISSING),
                   window_facts.activity(8, 9, status='truncated', quality=Q.MISSING))
        rule = TemporalRule('point', 'dataset', 'session', 'start_only', window_duration_ns=3)
        point = make_event(rule, 5, 5, None, 'point', Q.NONE, Q.NONE, trigger='start_only')
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend)
            result = owner.build(parents, WindowSpec('single', 'active', 'activity', merge='exit_delay',
                                 exit_delay_ns=2), Interval(0, 10))
            segment, = result.segments
            self.assertEqual((segment.requested, segment.actual), (Interval(5, 11), Interval(5, 10)))
            self.assertEqual(segment.event_statuses, ('interrupted', 'truncated'))
            self.assertEqual(segment.quality, Q.STALE | Q.MISSING)
            result.close()
            result = owner.build((point,), WindowSpec('fixed', 'point', 'point', 1, 3), Interval(0, 6))
            segment, = result.segments
            self.assertEqual((segment.requested, segment.actual, segment.requested_coverage),
                             (Interval(4, 8), Interval(4, 6), .5))
            result.close()

    def test_empty_extreme_times_and_overflow_are_exact_and_old_output_survives(self):
        """空批、三整数极值1ns与扩展溢出不走float时间，失败不撤销旧输出。

        参数: 无。返回: None。异常: 精度/资源/旧输出失效断言失败。
        """
        spec = WindowSpec('exact', 'active', 'activity')
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend)
            empty = owner.build((), spec, Interval(0, 1))
            self.assertEqual(empty.segments, ())
            empty.close()
            for start in (INT64_MIN, 2 ** 53 + 1, INT64_MAX - 2):
                event = window_facts.activity(start, start + 1)
                result = owner.build((event,), spec, Interval(start, start + 2))
                self.assertEqual(result.segments[0].requested, Interval(start, start + 1))
                self.assertEqual(result.segments[0].requested_coverage, 1)
                result.close()
            old = owner.build((window_facts.activity(1, 2),), spec, Interval(0, 5))
            before = self.budget.ram_bytes
            with self.assertRaises(TimeOverflowError):
                owner.build((window_facts.activity(INT64_MIN, INT64_MIN + 1),),
                    WindowSpec('overflow', 'active', 'activity', 1), Interval(INT64_MIN, INT64_MIN + 2))
            self.assertEqual(self.budget.ram_bytes, before)
            self.assertEqual(old.segments[0].requested, Interval(1, 2))
            old.close()

    def test_invalid_input_and_budget_refusal_precede_core_allocation(self):
        """错类型/协议/重复/回退失败清理，限额不足连数值内核也不调用。

        参数: 无。返回: None。异常: 静默排序/接受错误或超限后分配断言失败。
        """
        event, spec, observation = window_facts.activity(1, 2), WindowSpec('check', 'active', 'activity'), Interval(0, 10)
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend)
            baseline = self.budget.ram_bytes
            for events in ([event], ('invalid',)):
                with self.assertRaises(TypeError):
                    owner.build(events, spec, observation)
            for events in ((event, event), (window_facts.activity(5, 6), event)):
                with self.assertRaises(ValueError):
                    owner.build(events, spec, observation)
                self.assertEqual(self.budget.ram_bytes, baseline)
            limit = self.budget.memory_budget_bytes
            self.budget.memory_budget_bytes = baseline + 1
            try:
                with patch.object(owner, '_build', wraps=owner._build) as core:
                    with self.assertRaises(BudgetExceededError):
                        owner.build((event,), spec, observation)
                    core.assert_not_called()
            finally:
                self.budget.memory_budget_bytes = limit
            owner.build((event,), spec, observation).close()

    def test_constructor_and_query_reserve_cancel_leave_existing_result_readable(self):
        """固定/查询申请前后取消抵销一次，旧输出继续可读且查询可重试。

        参数: 无。返回: None。异常: 新成本漏账或错误撤销旧结果断言失败。
        """
        events, spec, observation = (window_facts.activity(1, 2),), WindowSpec('query', 'active', 'activity'), Interval(0, 3)
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                baseline = self.budget.ram_bytes
                with patch.object(self.budget, 'reserve_ram', side_effect=self.cancel_once(self.budget.reserve_ram, after)):
                    with self.assertRaises(KeyboardInterrupt):
                        WindowQueries(self.budget, backend=backend)
                self.assertEqual(self.budget.ram_bytes, baseline)
                owner = self.owner(backend)
                old = owner.build(events, spec, observation)
                baseline = self.budget.ram_bytes
                with patch.object(self.budget, 'reserve_ram', side_effect=self.cancel_once(self.budget.reserve_ram, after)):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.build(events, spec, observation)
                self.assertEqual(self.budget.ram_bytes, baseline)
                self.assertEqual(old.segments[0].requested, Interval(1, 2))
                owner.build(events, spec, observation).close()
                old.close()

    def test_core_construct_and_partial_registration_failure_cleanup_only_new_batch(self):
        """内核/构造/部分链安装失败只清理新批，原输出及原账本不受影响。

        参数: 无。返回: None。异常: 本次孤儿成本/旧输出丢失断言失败。
        """
        events, spec, observation = (window_facts.activity(1, 2),), WindowSpec('query', 'active', 'activity'), Interval(0, 3)
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend)
            old = owner.build(events, spec, observation)
            baseline = self.budget.ram_bytes
            for target, name in ((owner, '_build'), (owner, '_construct'), (owner._results, 'add')):
                fault = MemoryError('window-core') if name == '_build' else self.cancel_once(getattr(target, name), True)
                with patch.object(target, name, side_effect=fault):
                    with self.assertRaises((MemoryError, KeyboardInterrupt)):
                        owner.build(events, spec, observation)
                self.assertEqual(self.budget.ram_bytes, baseline)
                self.assertEqual(tuple(owner._results), (old,))
                self.assertEqual(old.segments[0].actual, Interval(1, 2))
            old.close()

    def test_release_and_discard_cancel_retry_without_double_debit(self):
        """输出/固定owner扣账及脱链动作前后取消支持重试，closed孤儿最终清理。

        参数: 无。返回: None。异常: 重复释放或登记残留断言失败。
        """
        spec, events = WindowSpec('query', 'active', 'activity'), (window_facts.activity(1, 2),)
        for backend in ('reference', 'numpy'):
            for stage in ('batch', 'owner', 'discard'):
                for after in (False, True):
                    baseline = self.budget.ram_bytes
                    owner = self.owner(backend)
                    result = owner.build(events, spec, Interval(0, 3))
                    if stage == 'owner':
                        result.close()
                    target = owner if stage == 'owner' else result
                    fault_target, name = (owner._results, 'discard') if stage == 'discard' else (self.budget, 'release_ram')
                    with patch.object(fault_target, name, side_effect=self.cancel_once(getattr(fault_target, name), after)):
                        with self.assertRaises(KeyboardInterrupt):
                            target.close()
                    self.assertEqual(target.closed, after or stage == 'discard')
                    target.close()
                    owner.close()
                    owner.close()
                    self.assertEqual(self.budget.ram_bytes, baseline)
                    with self.assertRaises(ResultClosedError):
                        _ = result.segments

    def test_long_full_csv_metadata_and_dense_queries_do_not_grow(self):
        """完整长CSV物理位置由输出成本持有；256查询及时close后账本/链不累计。

        参数: 无。返回: None。异常: 缩减位置或未计账输出引用断言失败。
        """
        # 此项人工声明定位模型；真正CSV读取链在下一测试单独运行。
        ref = CSVSourceRef('session', 'table', 'raw.' + '测' * 2000, 'source.csv', 314, '1', '1', False)
        event = replace(window_facts.activity(1, 2), source_refs=(ref,))
        spec = WindowSpec('metadata', 'active', 'activity')
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend)
            baseline = self.budget.ram_bytes
            result = owner.build((event,), spec, Interval(0, 3))
            self.assertGreater(result._cost, 65536 + 8192)
            self.assertEqual(result.segments[0].source_refs, (ref,))
            self.assertEqual(result.segments[0].source_refs[0].line_number, 314)
            result.close()
            for _ in range(256):
                owner.build((event,), spec, Interval(0, 3)).close()
                self.assertEqual(self.budget.ram_bytes, baseline)
                self.assertFalse(owner._results)

    def test_real_multi_timeline_events_enter_bounded_window_queries(self):
        """真实来源→多规则驱动→活动窗口，关闭查询/状态后片段仍保留父关联。

        参数: 无。返回: None。异常: 只验伪事件或真实层级关闭漏账断言失败。
        """
        for backend, ttl, point_count in (('reference', 3, 1), ('reference', 20, 1),
                                         ('numpy', 3, 1), ('numpy', 20, 1)):
            factory = real_queries.StreamConditionEvidenceTests('runTest')
            # 3ns真实FALSE先与上一完成点的TRUE判断边沿，再安装连续态；并列TTL不抹掉falling。
            # 20ns有效期同样产生一个真实边沿，提前TTL无真实更新的情形不在本次输入内。
            fixture, evidence = factory.fixture(backend=backend, kind='csv', domain=(0, 3),
                definitions=(SignalDefinition('a', 'table', 'raw.a', SignalDType.FLOAT64, '1', ttl),),
                rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(3, {'raw.a': 0}, 1))})
            self.assertEqual(tuple(group.time_ns for group in fixture.groups), (0, 3))
            timeline = MultiRuleTimeline(evidence, fixture.boundaries,
                (TimelineRule(TemporalRule('active', 'dataset', 'session', 'condition_duration', 3), fixture.compiled[0]),
                 TimelineRule(TemporalRule('fall', 'dataset', 'session', 'falling_edge'), fixture.compiled[0])))
            owner = WindowQueries(fixture.budget, backend=backend)
            try:
                timeline.step(fixture.groups[0]).close()
                step = timeline.step(fixture.groups[1])
                activities, points = step.events_by_rule
                self.assertEqual(len(activities), 1)
                self.assertEqual(len(points), point_count)
                self.assertEqual(fixture.state.revision, 2)
                result = owner.build(activities, WindowSpec('context', 'active', 'activity', 1, 2), Interval(0, 3))
                step.close()
                timeline.close()
                # 原工厂整体清理会断言共享RAM0，此时窗口仍合法持有成本，不能提前验它。
                evidence.close()
                fixture.boundaries.close()
                fixture.expressions.close()
                fixture.holds.close()
                fixture.state.close()
                segment, = result.segments
                self.assertEqual((segment.requested, segment.actual, segment.requested_coverage),
                                 (Interval(-1, 5), Interval(0, 3), .5))
                self.assertEqual(segment.parent_event_ids, (activities[0].event_id,))
                result.close()
            finally:
                owner.close()
                timeline.close()
                self.assertTrue(factory.doCleanups())
                self.assertEqual(fixture.budget.ram_bytes, 0)
