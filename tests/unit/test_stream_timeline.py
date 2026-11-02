"""用真实来源和手算事件验证单规则准确时间游标及资源。

复用已验memory/CSV→封存历史→绑定→状态→真实条件查询工厂，外部保存下一组直到消费。
事件预期使用固定起点/确认/终点/status，不从参考或NumPy输出推算另一版本真值。
验证无新数据deadline、并列FALSE/TTL/EOF、域前种子/常量、边沿与start_only、切分极值，
以及失败/关闭预算。文件仅写work，原工厂清理成功且共享RAM必须归零，无旧CAN副作用。
"""

# 模块别名复用工厂而不重复发现其TestCase；两个独立后端共用原始输入。
import unittest
from unittest.mock import patch
import test_stream_condition_evidence as factories
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow, SourceRef
from chronaxis.core.temporal import TemporalRule
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, Truth as T
from chronaxis.execution.timeline import TemporalTimeline
from chronaxis.results.errors import AnalysisError, BudgetExceededError, ResultClosedError


class StreamTimelineTests(unittest.TestCase):
    """单规则游标与各借用owner逆序关闭，每个合成来源独立目录和预算。"""

    def fixture(self, *, backend='numpy', rule=None, seed=False, **kwargs):
        """建立真实查询与新游标并登记所有清理。

        参数: backend独立版本，rule默认duration3，seed是否先提交域前组，其余为工厂输入。
        返回: (fixture,timeline)，小原始完整组仅供测试保留前瞻。
        异常: 实际读取/编译/预算错误传播，工厂清理失败明确断言。
        """
        factory = factories.StreamConditionEvidenceTests('runTest')
        fixture, evidence = factory.fixture(backend=backend, **kwargs)
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        if seed:
            # 域前种子在游标建立前提交，实际组仍留在测试输入但演示循环会跳过。
            for group in fixture.groups:
                if group.time_ns < evidence._start:
                    fixture.state.apply(group)
        rule = TemporalRule('rule', 'dataset', 'session', 'condition_duration', 3) if rule is None else rule
        timeline = TemporalTimeline(evidence, fixture.boundaries, fixture.compiled[0], rule)
        self.addCleanup(timeline.close)
        return fixture, timeline

    def cleanup_fixture(self, factory, budget):
        """核对真实工厂清理。参数: 工厂/账本。返回: None。异常: AssertionError。"""
        self.assertTrue(factory.doCleanups(), '真实条件工厂关闭失败')
        self.assertEqual(budget.ram_bytes, 0)

    def consume(self, fixture, timeline):
        """外部保留前瞻直到消费，收集有限手算夹具的事件与事实。

        参数: 小fixture/单规则timeline。返回: (events tuple,facts tuple)。
        异常: 超10000步判无限循环，实际步骤错误传播并关闭当前步。
        """
        groups = tuple(group for group in fixture.groups if group.time_ns >= timeline._start)
        index, events, facts = 0, [], []
        for _ in range(10000):
            group = groups[index] if index < len(groups) else None
            result = timeline.step(group)
            if result is None:
                return tuple(events), tuple(facts)
            try:
                events.extend(result.events)
                facts.append((result.time_ns, result.consumed_group, result.tick))
                if result.consumed_group:
                    index += 1
            finally:
                result.close()
        self.fail('有限夹具的准确时间游标未终止')

    def event_fields(self, events):
        """只提取手算边界。参数: Event tuple。返回: 稳定字段tuple。异常: 类型错误传播。"""
        return tuple((event.start_ns, event.confirmed_ns, event.end_ns, event.status) for event in events)

    def test_no_update_still_confirms_exact_deadline(self):
        """没有下一报文也在3ns确认，8ns实际EOF截断。

        参数: 无。返回: None。异常: 等待报文或把batch尾当EOF断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture, timeline = self.fixture(backend=backend, domain=(0, 8), bounds={'table': (0, 8)},
                definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20),),
                rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0),)})
            events, facts = self.consume(fixture, timeline)
            self.assertEqual(self.event_fields(events), ((0, 3, 8, 'truncated'),))
            self.assertEqual(tuple((time, consumed) for time, consumed, _ in facts), ((0, True), (3, False), (8, False)))
            self.assertEqual(fixture.state.revision, 1)

    def test_deadline_false_ttl_and_eof_same_time_closes_actual_end(self):
        """TRUE[0,3)先准确确认，再应用末点FALSE，以closed结束。

        参数: 无。返回: None。异常: 丢失确认或TTL/EOF覆盖实际FALSE断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture, timeline = self.fixture(backend=backend, domain=(0, 3),
                rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(3, {'raw.a': 0}, 1))})
            events, facts = self.consume(fixture, timeline)
            self.assertEqual(self.event_fields(events), ((0, 3, 3, 'closed'),))
            self.assertEqual(events[0].quality, Q.NONE)
            self.assertEqual(facts[-1][2].point_state, T.FALSE)
            self.assertEqual(fixture.state.revision, 2)

    def test_ttl_before_eof_and_ttl_equals_eof_keep_different_status(self):
        """TTL早于EOF中断，并列EOF则截断；真实无效并列仍中断。

        参数: 无。返回: None。异常: 结束优先级或并列诊断丢失断言失败。
        """
        # Event结束质量保留两视图并集，truncated优先级不意味着删除并列STALE。
        cases = ((8, False, 'interrupted', Q.STALE), (3, False, 'truncated', Q.MISSING | Q.STALE),
                 (3, True, 'interrupted', Q.MISSING))
        for backend in ('reference', 'numpy'):
            for end, invalid, status, quality in cases:
                rows = (MemoryRow(0, {'raw.a': 1}, 0),)
                if invalid:
                    rows += (MemoryRow(3, {'raw.a': None}, 1),)
                fixture, timeline = self.fixture(backend=backend, domain=(0, end), bounds={'table': (0, end)},
                                                  rows_by_source={'table': rows})
                events, facts = self.consume(fixture, timeline)
                self.assertEqual(self.event_fields(events), ((0, 3, 3, status),))
                self.assertEqual(events[0].quality, quality)
                if end == 3 and not invalid:
                    self.assertEqual(events[0].dependency_quality, Q.STALE | Q.MISSING)

    def test_decisive_joint_source_constant_empty_and_domain_seed(self):
        """较早来源EOF不压倒决定性TRUE；常量空源与域前种子按实际分析起点推进。

        参数: 无。返回: None。异常: 伪造source末点或用start-1处理下界断言失败。
        """
        a = SignalDefinition('a', 'early', 'raw.a', D.FLOAT64, '1', 20)
        b = SignalDefinition('b', 'late', 'raw.b', D.FLOAT64, '1', 20)
        for backend in ('reference', 'numpy'):
            fixture, timeline = self.fixture(backend=backend, definitions=(a, b), domain=(0, 6),
                texts=('a > 0 or b > 0',), bounds={'early': (0, 3), 'late': (0, 6)},
                rows_by_source={'early': (MemoryRow(0, {'raw.a': 0}, 0),), 'late': (MemoryRow(0, {'raw.b': 1}, 0),)})
            events, facts = self.consume(fixture, timeline)
            self.assertEqual(self.event_fields(events), ((0, 3, 6, 'truncated'),))
            self.assertEqual(tuple(time for time, _, _ in facts), (0, 3, 6))
            fixture, timeline = self.fixture(backend=backend, texts=('True',), domain=(0, 5),
                                             rows_by_source={'table': ()})
            events, facts = self.consume(fixture, timeline)
            self.assertEqual(self.event_fields(events), ((0, 3, 5, 'truncated'),))
            self.assertFalse(facts[-1][2].observation_end)
            fixture, timeline = self.fixture(backend=backend, seed=True, domain=(2, 6), bounds={'table': (0, 6)},
                definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20),),
                rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 0}, 1))})
            events, facts = self.consume(fixture, timeline)
            self.assertEqual(self.event_fields(events), ((2, 5, 5, 'closed'),))
            self.assertEqual(facts[0][0:2], (2, False))

    def test_terminal_true_edge_and_start_only_reentry(self):
        """末点TRUE可产生rising而不能新建活动，start_only抑制需要真实重入边沿。

        参数: 无。返回: None。异常: 末点扩展连续区间或抑制重置错误断言失败。
        """
        terminal_rows = (MemoryRow(0, {'raw.a': 0}, 0), MemoryRow(3, {'raw.a': 1}, 1))
        for backend in ('reference', 'numpy'):
            for kind in ('rising_edge', 'condition_duration'):
                rule = TemporalRule('rule', 'dataset', 'session', kind)
                fixture, timeline = self.fixture(backend=backend, rule=rule, domain=(0, 3), rows_by_source={'table': terminal_rows})
                events, _ = self.consume(fixture, timeline)
                self.assertEqual(self.event_fields(events), ((3, 3, None, 'point'),) if kind == 'rising_edge' else ())
            rule = TemporalRule('rule', 'dataset', 'session', 'start_only', window_duration_ns=3)
            rows = tuple(MemoryRow(time, {'raw.a': value}, time) for time, value in enumerate((0, 1, 0, 1, 0, 1)))
            fixture, timeline = self.fixture(backend=backend, rule=rule, domain=(0, 8), bounds={'table': (0, 8)},
                definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20),), rows_by_source={'table': rows})
            events, _ = self.consume(fixture, timeline)
            self.assertEqual(self.event_fields(events), ((1, 1, None, 'point'), (5, 5, None, 'point')))

    def test_csv_splits_and_extreme_int64_keep_event_identity(self):
        """真实CSV/内存和批次1/2/7在极值保留准确确认，两个后端事件ID稳定。

        参数: 无。返回: None。异常: 时间浮点化、切组或ID随批次变化断言失败。
        """
        for start in (-(2 ** 63), 2 ** 53 + 1, 2 ** 63 - 4):
            identities = set()
            for backend in ('reference', 'numpy'):
                for kind in ('memory', 'csv'):
                    for size in (1, 2, 7):
                        rows = (MemoryRow(start, {'raw.a': 1}, 0), MemoryRow(start + 3, {'raw.a': 0}, 1))
                        fixture, timeline = self.fixture(backend=backend, kind=kind, size=size,
                            domain=(start, start + 3), rows_by_source={'table': rows})
                        events, facts = self.consume(fixture, timeline)
                        self.assertEqual(self.event_fields(events), ((start, start + 3, start + 3, 'closed'),))
                        identities.add(events[0].event_id)
                        if kind == 'csv':
                            self.assertEqual(fixture.state.get('a').source_ref.line_number, 3)
            self.assertEqual(len(identities), 1)

    def test_preflight_budget_and_external_revision_errors_do_not_fake_progress(self):
        """workspace拒绝可重试，外部提交与回退前瞻在推进前拒绝。

        参数: 无。返回: None。异常: 静默回滚/前置失败假标推进断言失败。
        """
        fixture, timeline = self.fixture()
        original_limit = fixture.budget.memory_budget_bytes
        fixture.budget.memory_budget_bytes = fixture.budget.ram_bytes
        try:
            with self.assertRaises(BudgetExceededError):
                timeline.step(fixture.groups[0])
        finally:
            fixture.budget.memory_budget_bytes = original_limit
        self.assertFalse(timeline.failed)
        self.assertIsNone(timeline.cursor_ns)
        self.assertEqual(fixture.state.revision, 0)
        first = timeline.step(fixture.groups[0])
        self.addCleanup(first.close)
        with self.assertRaises(ValueError):
            timeline.step(fixture.groups[0])
        fixture.state.apply(fixture.groups[1])
        with self.assertRaises(ValueError):
            timeline.step()
        self.assertEqual(first.tick.state, T.TRUE)

    def test_stage_failure_preserves_old_output_and_rejects_retry(self):
        """步骤开始后的求值/构造交付故障标failed，原输出保持可读直到close。

        参数: 无。返回: None。异常: 假事务恢复或旧输出被撤销断言失败。
        """
        for method in ('push', '_construct'):
            fixture, timeline = self.fixture()
            first = timeline.step(fixture.groups[0])
            self.addCleanup(first.close)
            baseline = fixture.budget.ram_bytes
            target = timeline._detector if method == 'push' else timeline
            with patch.object(target, method, side_effect=MemoryError('timeline-stage')):
                with self.assertRaises(MemoryError):
                    timeline.step(fixture.groups[1])
            self.assertTrue(timeline.failed)
            with self.assertRaises(AnalysisError):
                timeline.step(fixture.groups[1])
            self.assertEqual(fixture.budget.ram_bytes, baseline)
            self.assertEqual(first.tick.state, T.TRUE)
            self.assertEqual(timeline.cursor_ns, 0)

    def test_step_close_and_constructor_budget_cancel_are_accounted_once(self):
        """constructor固定申请和step workspace释放返回取消均唯一抵销。

        参数: 无。返回: None。异常: 重复抵销或漏账断言失败。
        """
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                factory = factories.StreamConditionEvidenceTests('runTest')
                fixture, evidence = factory.fixture(backend=backend)
                self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
                rule = TemporalRule('rule', 'dataset', 'session', 'condition_duration', 3)
                baseline = fixture.budget.ram_bytes
                fault = factory.cancel_operation(fixture.budget.reserve_ram, after)
                with patch.object(fixture.budget, 'reserve_ram', side_effect=fault):
                    with self.assertRaises(KeyboardInterrupt):
                        TemporalTimeline(evidence, fixture.boundaries, fixture.compiled[0], rule)
                self.assertEqual(fixture.budget.ram_bytes, baseline)
                timeline = TemporalTimeline(evidence, fixture.boundaries, fixture.compiled[0], rule)
                self.addCleanup(timeline.close)
                result = timeline.step(fixture.groups[0])
                original_release, used = fixture.budget.release_ram, False

                def cancel_workspace(amount):
                    """仅workspace释放取消。参数: amount bytes。返回: 原结果。异常: KeyboardInterrupt。"""
                    nonlocal used
                    if amount == 65536 and not used:
                        used = True
                        if after:
                            original_release(amount)
                        raise KeyboardInterrupt('timeline-workspace-release')
                    return original_release(amount)

                with patch.object(fixture.budget, 'release_ram', side_effect=cancel_workspace):
                    with self.assertRaises(KeyboardInterrupt):
                        result.close()
                self.assertEqual(result.closed, after)
                result.close()

    def test_many_actual_steps_close_without_accumulating_results(self):
        """256实际组关闭后除当前state保留量外RAM固定，检测器不累计最终事件。

        参数: 无。返回: None。异常: 游标/查询/检测器登记或账本随批累积断言失败。
        """
        rows = tuple(MemoryRow(time, {'raw.a': time % 2}, time) for time in range(256))
        rule = TemporalRule('rule', 'dataset', 'session', 'condition_duration')
        fixture, timeline = self.fixture(rule=rule, domain=(0, 256), bounds={'table': (0, 256)},
            definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 1000),),
            rows_by_source={'table': rows})
        baseline = None
        for group in fixture.groups:
            result = timeline.step(group)
            self.assertTrue(result.consumed_group)
            result.close()
            # 差额扣除当前latest真实保留量，避免把数据自身大小变化伪装为缓存泄漏。
            retained = fixture.budget.ram_bytes - fixture.state._snapshot.retained_cost
            baseline = retained if baseline is None else baseline
            self.assertEqual(retained, baseline)
            self.assertFalse(timeline._results)
            self.assertFalse(timeline._evidence._results)
            self.assertFalse(timeline._detector._results)
            self.assertEqual(timeline._detector._detector.events, [])
        terminal = timeline.step()
        self.assertEqual(terminal.time_ns, 256)
        terminal.close()
        self.assertIsNone(timeline.step())
        timeline.close()
        with self.assertRaises(ResultClosedError):
            timeline.step()

    def test_entry_protocol_rejects_wrong_type_owner_session_and_seed_timing(self):
        """查询owner必须共用实际上游，非组/跨会话/已提交域内起点均拒绝。

        参数: 无。返回: None。异常: 入口协议错位接受或拒绝后资源改变断言失败。
        """
        fixture, timeline = self.fixture()
        other, second = self.fixture()
        rule = TemporalRule('rule', 'dataset', 'session', 'condition_duration', 3)
        baseline = fixture.budget.ram_bytes
        with self.assertRaises(TypeError):
            timeline.step(0)
        with self.assertRaises(ValueError):
            TemporalTimeline(timeline._evidence, other.boundaries, fixture.compiled[0], rule)
        wrong_session = TemporalRule('rule', 'dataset', 'other_session', 'condition_duration', 3)
        with self.assertRaises(ValueError):
            TemporalTimeline(timeline._evidence, fixture.boundaries, fixture.compiled[0], wrong_session)
        with self.assertRaises(ValueError):
            TemporalTimeline(timeline._evidence, fixture.boundaries, fixture.compiled[0], rule,
                             source_refs=(SourceRef('other_session', 'table', 'raw.a'),))
        self.assertEqual(fixture.budget.ram_bytes, baseline)
        fixture.state.apply(fixture.groups[0])
        with self.assertRaises(ValueError):
            TemporalTimeline(timeline._evidence, fixture.boundaries, fixture.compiled[0], rule)

    def test_step_reserve_return_cancel_leaves_unstarted_cursor_retryable(self):
        """首workspace申请前/返回后取消不进入步骤，之后可按同一真实前瞻重试。

        参数: 无。返回: None。异常: 假推进/漏账/不可重试断言失败。
        """
        helper = factories.StreamConditionEvidenceTests('runTest')
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                fixture, timeline = self.fixture(backend=backend)
                baseline = fixture.budget.ram_bytes
                fault = helper.cancel_operation(fixture.budget.reserve_ram, after)
                with patch.object(fixture.budget, 'reserve_ram', side_effect=fault):
                    with self.assertRaises(KeyboardInterrupt):
                        timeline.step(fixture.groups[0])
                self.assertFalse(timeline.failed)
                self.assertIsNone(timeline.cursor_ns)
                self.assertEqual(fixture.state.revision, 0)
                self.assertEqual(fixture.budget.ram_bytes, baseline)
                result = timeline.step(fixture.groups[0])
                self.assertTrue(result.consumed_group)
                result.close()

    def test_construct_delivery_and_partial_install_cancel_leave_only_prior_step(self):
        """构造交付/链部分安装取消不留下未交付步，旧条件和事件仍独立持有。

        参数: 无。返回: None。异常: 新登记残留/旧输出失效或重复扣账断言失败。
        """
        for backend in ('reference', 'numpy'):
            for install in (False, True):
                fixture, timeline = self.fixture(backend=backend)
                first = timeline.step(fixture.groups[0])
                self.addCleanup(first.close)
                baseline = fixture.budget.ram_bytes
                target = timeline._results if install else timeline
                method = 'add' if install else '_construct'
                original = getattr(target, method)

                def cancel_delivery(*args):
                    """原操作后取消。参数: 原参数。返回: 无。异常: KeyboardInterrupt。"""
                    original(*args)
                    raise KeyboardInterrupt('timeline-result-delivery')

                with patch.object(target, method, side_effect=cancel_delivery):
                    with self.assertRaises(KeyboardInterrupt):
                        timeline.step(fixture.groups[1])
                self.assertTrue(timeline.failed)
                self.assertEqual(tuple(timeline._results), (first,))
                self.assertEqual(first.tick.state, T.TRUE)
                self.assertEqual(first.events, ())
                self.assertEqual(fixture.budget.ram_bytes, baseline)
