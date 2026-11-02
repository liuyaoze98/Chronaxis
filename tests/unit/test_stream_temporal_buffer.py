"""验证有预算检测器的独立事件语义、增量排空和结果生命周期。

输入为明确手算的ConditionTick元组和当前规则，输出为须关闭的事件批次。
两个后端分别执行自己的持续/边沿状态核；预期时间、状态和原因手写，
只比较稳定ID跨切分一致，不用被测输出生成业务真值。预算故障只注入
新分析层，所有实例分别关闭；不生成完整来源轴、不接三视图或公共AnalysisRunner。
本专项无来源文件I/O；完整运行日志写work/m2-run-tests，设备来源为work。
"""

# 复用typed证据及原定位模型，故障注入不改变独立数值内核的业务结果。
from unittest.mock import patch
import sys
import unittest
from chronaxis.core.models import SourceRef
from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.temporal_reference import ReferenceTemporalDetector
from chronaxis.core.temporal_numpy import NumpyTemporalDetector
from chronaxis.core.types import Truth as T, QualityFlag as Q
from chronaxis.execution.temporal_buffer import BudgetedTemporalDetector
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import AnalysisError, BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


def rule(kind='condition_duration', duration=0, *, initial=False, window=0):
    """建立当前合成会话的冻结规则，不保存上次检测状态。

    参数: kind类型、duration门槛ns、initial首次点策略、window抑制ns。
    返回: TemporalRule。异常: 非法参数由模型拒绝。
    """
    # 明示dataset/session及时间参数，使每个新owner独立且事件ID可复核。
    return TemporalRule('rule', 'dataset', 'session', kind, duration, initial, window)


def tick(time, state, *, quality=Q.NONE, actual=True, eof=False, terminal=False,
         point=None, point_quality=None, actual_unknown=False, diagnostic=Q.NONE):
    """按手算声明一个完整组的连续/点/实际因果证据。

    参数: time整数ns，state/point三值，quality/point_quality/diagnostic质量位，
        actual/eof/terminal/actual_unknown为真实证据标志。
    返回: ConditionTick。异常: 不一致状态或类型由模型拒绝。
    """
    # 保持三值、实际因果和来源/会话末点为独立字段，不推断未知为False。
    return ConditionTick(time, state, quality, actual, eof, terminal,
                         point, point_quality, actual_unknown, diagnostic)


class RejectRegistry(set):
    """模拟新结果登记分配失败；已有批次不会被替身修改。"""

    def add(self, item):
        """拒绝一次新句柄登记。

        参数: item待登记结果。返回: 无。异常: MemoryError为指定故障。
        """
        # 无登记副作用的普通分配故障，与下一替身的部分安装故障分开。
        raise MemoryError('模拟事件批次登记失败')


class AddThenRejectRegistry(set):
    """模拟登记已产生副作用后分配失败，要求owner撤销仅本次新句柄。"""

    def add(self, item):
        """先登记新结果再抛错，不修改已有结果。

        参数: item待登记结果。返回: 无。异常: MemoryError为登记后故障。
        """
        # 模拟已经持有句柄但add尚未向caller成功返回的部分安装窗口。
        super().add(item)
        raise MemoryError('模拟登记后分配失败')


class StreamTemporalBufferTests(unittest.TestCase):
    """逐项核对手算业务事实、预留时机、失败状态及所有权。"""

    def owner(self, selected_rule, start, end, *, backend='numpy', refs=(), budget=None):
        """创建并登记清理当前独立owner，调用方可另行关闭以验证账本。

        参数: selected_rule规则、start/end整数ns、backend独立核、refs来源、budget账本。
        返回: (BudgetedTemporalDetector,ResourceBudget)。异常: 构造错误原样传播。
        """
        # 小夹具使用64MiB共享估算；注册清理保证断言失败也不遗留owner申请。
        budget = ResourceBudget(64 * 1024 ** 2) if budget is None else budget
        owner = BudgetedTemporalDetector(budget, selected_rule, start, end, refs, backend=backend)
        self.addCleanup(owner.close)
        return owner, budget

    def batch(self, owner, ticks):
        """推送当前有限批次并登记异常路径的最终清理。

        参数: owner当前检测器，ticks完整组tuple。返回: TemporalEventBatch。
        异常: 推进或预算错误传播，不吞失败。
        """
        # 只登记本次真实返回句柄，失败时不会把缺失结果伪装为空批。
        result = owner.push(ticks)
        self.addCleanup(result.close)
        return result

    def facts(self, events):
        """取可与手算直接比较的事件边界和主状态。

        参数: events已产出的Event tuple。返回: 四字段tuple列表。
        异常: 非Event输入属性错误传播。
        """
        # 直接抽取既定时间事实，排除可选诊断字段对手算边界比较的干扰。
        return [(event.start_ns, event.confirmed_ns, event.end_ns, event.status) for event in events]

    def consume(self, owner, ticks, size, *, empty=True):
        """按有限切分消费小手算夹具，每批立即关闭，返回仅测试持有的事实。

        参数: owner当前实例、ticks小tuple、size正批长、empty是否插空批。
        返回: 事件tuple；仅本专项小夹具用于对照，不作为产品累计输出流程。
        异常: 推进/finish错误及断言失败传播。
        """
        # 本helper只用于少量切分真值对照；产品有界性由增量大批测试另验。
        events = []
        for offset in range(0, len(ticks), size):
            if empty:
                # 空批不能重置候选/边沿或重发已经取出的事件。
                gap = self.batch(owner, ())
                self.assertEqual(gap.events, ())
                gap.close()
            result = self.batch(owner, ticks[offset:offset + size])
            # 将本测试的小事件副本保留用于比较，产品句柄则当批释放。
            events.extend(result.events)
            result.close()
        # finish仅封闭真正terminal之后的状态，不补造/重发先前事件。
        final = owner.finish()
        self.addCleanup(final.close)
        # 最终空批依然是有所有权的句柄，核对后关闭，不漏计其工作申请。
        self.assertEqual(final.events, ())
        final.close()
        return tuple(events)

    def test_duration_exact_deadline_end_classification_and_diagnostics(self):
        """门槛恰等FALSE/invalid/TTL/EOF时先确认，并保留真实结束优先级。

        参数: 无。返回: None。异常: 边界、主状态、质量或排空差异断言失败。
        """
        cases = (
            # 真实FALSE即便同EOF也closed，旧TTL诊断不改主状态。
            ('false', tick(3, T.UNKNOWN, quality=Q.MISSING, eof=True, terminal=True,
                           point=T.FALSE, point_quality=Q.NONE, diagnostic=Q.STALE),
             'closed', Q.NONE, Q.STALE | Q.MISSING),
            # 真实无效证据优先interrupted，不能由EOF覆盖。
            ('invalid', tick(3, T.UNKNOWN, quality=Q.MISSING, eof=True, terminal=True,
                             actual_unknown=True, diagnostic=Q.MISSING),
             'interrupted', Q.MISSING, Q.MISSING),
            # 无实际更新且TTL早于EOF，连续性在到期时中断。
            ('ttl', tick(3, T.UNKNOWN, quality=Q.STALE, actual=False, diagnostic=Q.STALE),
             'interrupted', Q.STALE, Q.STALE),
            # 纯EOF无真实结束更新，点仍可保持TRUE而连续区间必须结束。
            ('eof', tick(3, T.UNKNOWN, quality=Q.MISSING, actual=False, eof=True, terminal=True,
                         point=T.TRUE, point_quality=Q.NONE, diagnostic=Q.MISSING),
             'truncated', Q.MISSING, Q.MISSING),
            # TTL==EOF以truncated为主，STALE在完整原因中保留。
            ('ttl_eof', tick(3, T.UNKNOWN, quality=Q.STALE | Q.MISSING, actual=False,
                             eof=True, terminal=True, diagnostic=Q.STALE | Q.MISSING),
             'truncated', Q.STALE | Q.MISSING, Q.STALE | Q.MISSING),
        )
        # 每种结束原因分别运行两个独立core，不共享前一案例的候选状态。
        for backend in ('reference', 'numpy'):
            for name, ending, status, quality, diagnostic in cases:
                with self.subTest(backend=backend, case=name):
                    # TTL早于真正E的案例补一个后续terminal，其余同刻在3收尾。
                    end = 5 if name == 'ttl' else 3
                    owner, budget = self.owner(rule(duration=3), 0, end, backend=backend)
                    first = self.batch(owner, (tick(0, T.TRUE),))
                    self.assertEqual(first.events, ())
                    first.close()
                    self.assertEqual(owner.next_deadline_ns, 3)
                    # 精确确认、主结束原因和完整诊断独立核对，禁止靠数量代替事实。
                    result = self.batch(owner, (ending,))
                    self.assertEqual(self.facts(result.events), [(0, 3, 3, status)])
                    self.assertEqual(result.events[0].quality, quality)
                    self.assertEqual(result.events[0].dependency_quality, diagnostic)
                    result.close()
                    self.assertIsNone(owner.next_deadline_ns)
                    if name == 'ttl':
                        # 候选已在TTL结束，后续真正EOF不得再次输出同一活动。
                        tail = self.batch(owner, (tick(5, T.UNKNOWN, quality=Q.MISSING,
                                                      actual=False, eof=True, terminal=True),))
                        self.assertEqual(tail.events, ())
                        tail.close()
                    # 所有末点消费后finish无剩余事件，各层关闭最终回到零申请。
                    final = owner.finish()
                    self.assertEqual(final.events, ())
                    final.close()
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_terminal_true_is_point_only_and_zero_duration_has_no_activity(self):
        """真实终点F→T可产生rising，duration0不能建立终点活动。

        参数: 无。返回: None。异常: point/连续半开语义混淆断言失败。
        """
        # 连续半开域在E为UNKNOWN，但真实点更新TRUE保持独立有效。
        ticks = (tick(0, T.FALSE), tick(3, T.UNKNOWN, quality=Q.MISSING,
                                      eof=True, terminal=True, point=T.TRUE, point_quality=Q.NONE))
        for backend in ('reference', 'numpy'):
            # 同一明确证据分别用于边沿与零门槛持续，不能以零长度activity替代point。
            for kind, expected in (('rising_edge', [(3, 3, None, 'point')]), ('condition_duration', [])):
                with self.subTest(backend=backend, kind=kind):
                    owner, budget = self.owner(rule(kind), 0, 3, backend=backend)
                    events = self.consume(owner, ticks, 1)
                    self.assertEqual(self.facts(events), expected)
                    # 切分helper已关闭所有批次，owner最后释放固定配置预算。
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_start_only_suppression_expiry_unknown_and_real_reentry(self):
        """抑制区间右端允许真实边沿，UNKNOWN恢复和定时器均不伪造重触发。

        参数: 无。返回: None。异常: 跨批抑制、恢复或半开边界断言失败。
        """
        # 1触发后[1,5)抑制3；5和9均为真正F→T且恰在旧抑制右端。
        ticks = (tick(0, T.FALSE), tick(1, T.TRUE), tick(2, T.FALSE), tick(3, T.TRUE),
                 tick(4, T.FALSE), tick(5, T.TRUE), tick(6, T.UNKNOWN, quality=Q.MISSING,
                                                          actual_unknown=True),
                 tick(7, T.TRUE), tick(8, T.FALSE), tick(9, T.TRUE),
                 tick(10, T.UNKNOWN, quality=Q.MISSING, actual=False, eof=True, terminal=True,
                      point=T.TRUE, point_quality=Q.NONE))
        # 两核分别逐组跨批保持blocked_until，不把被抑制边沿排队补发。
        for backend in ('reference', 'numpy'):
            owner, budget = self.owner(rule('start_only', window=4), 0, 10, backend=backend)
            events = self.consume(owner, ticks, 1)
            self.assertEqual(self.facts(events), [(1, 1, None, 'point'), (5, 5, None, 'point'),
                                                  (9, 9, None, 'point')])
            self.assertEqual(tuple(event.trigger_kind for event in events), ('start_only',) * 3)
            # 输出边沿均为真实start_only，关闭后不保留抑制状态或申请。
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_workspace_rejection_precedes_core_and_allows_exact_retry(self):
        """共享账本仅余1字节时不进入core，不改候选，解除占用后同批可重试。

        参数: 无。返回: None。异常: 超预算后误推进或不能恢复断言失败。
        """
        # 外部占用只留1字节，令本次workspace必然在core状态改变前拒绝。
        for backend in ('reference', 'numpy'):
            owner, budget = self.owner(rule(duration=2), 0, 3, backend=backend)
            core = owner._detector
            before = (core.last_time, core.candidate_start, core.confirmed, tuple(core.events))
            occupied = budget.memory_budget_bytes - budget.ram_bytes - 1
            budget.reserve_ram(occupied)
            baseline = budget.ram_bytes
            try:
                # 若实现先调用core，则替身立即失败，不能靠最终状态偶然一致蒙混。
                with patch.object(type(core), 'push', side_effect=AssertionError('不应进入core')) as called:
                    with self.assertRaises(BudgetExceededError):
                        owner.push((tick(0, T.TRUE),))
                    called.assert_not_called()
                # 账本、失败标志和候选指针均保持旧值，保证同批合法重试。
                self.assertEqual(budget.ram_bytes, baseline)
                self.assertFalse(owner.failed)
                self.assertIs(owner._detector, core)
                self.assertEqual((core.last_time, core.candidate_start, core.confirmed,
                                  tuple(core.events)), before)
            finally:
                # 只解除夹具外部占用，不释放owner自己的固定申请。
                budget.release_ram(occupied)
            # 解除占用后重新推送原首组，准确deadline仍从真正onset0开始。
            first = self.batch(owner, (tick(0, T.TRUE),))
            first.close()
            self.assertEqual(owner.next_deadline_ns, 2)
            result = self.batch(owner, (tick(2, T.FALSE),))
            self.assertEqual(self.facts(result.events), [(0, 2, 2, 'closed')])
            # 合法末点后finish同样先申请；超限不得提前封闭core，解除后可重试。
            result.close()
            terminal = self.batch(owner, (tick(3, T.UNKNOWN, quality=Q.MISSING,
                                              actual=False, terminal=True),))
            terminal.close()
            occupied = budget.memory_budget_bytes - budget.ram_bytes - 1
            budget.reserve_ram(occupied)
            try:
                with patch.object(type(core), 'finish', side_effect=AssertionError('不应提前finish')) as called:
                    with self.assertRaises(BudgetExceededError):
                        owner.finish()
                    called.assert_not_called()
                self.assertFalse(owner.failed)
                self.assertFalse(core.finished)
            finally:
                budget.release_ram(occupied)
            final = owner.finish()
            self.assertEqual(final.events, ())
            final.close()
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_reservation_cancellation_keeps_prior_budget_and_core_retryable(self):
        """构造/push/finish的预申请入口或返回取消抵销新申请，core尚未推进。

        参数: 无。返回: None。异常: 新申请漏计、core误推进或不能重试断言失败。
        """
        # 各阶段均有外部4096字节；返回取消已经加账但仍必须还原此原值。
        for backend in ('reference', 'numpy'):
            for stage in ('constructor', 'push', 'finish'):
                for phase in ('call', 'return'):
                    with self.subTest(backend=backend, stage=stage, phase=phase):
                        budget = ResourceBudget(64 * 1024 ** 2)
                        budget.reserve_ram(4096)
                        detector = prior = core = before_state = None
                        if stage != 'constructor':
                            detector, _ = self.owner(rule('rising_edge'), 0, 4, backend=backend, budget=budget)
                            ticks = (tick(0, T.FALSE), tick(1, T.TRUE))
                            if stage == 'finish':
                                ticks += (tick(4, T.UNKNOWN, quality=Q.MISSING,
                                               actual=False, terminal=True),)
                            prior = self.batch(detector, ticks)
                            core = detector._detector
                            before_state = dict(vars(core), events=tuple(core.events))
                        before = budget.ram_bytes
                        reserve_code = budget.reserve_ram.__func__.__code__
                        caller_code = (BudgetedTemporalDetector.__init__.__code__ if stage == 'constructor'
                                       else getattr(detector, stage).__func__.__code__)
                        previous_trace, fired = sys.gettrace(), False

                        def cancel_reservation(frame, event, argument):
                            """仅取消指定owner阶段的本次账本预申请，不拦截清理抵销。

                            参数: frame运行帧、event追踪事件、argument追踪参数。
                            返回: 当前追踪函数。异常: KeyboardInterrupt为指定申请取消。
                            """
                            # 精确调用方code与budget实例，constructor无外部owner指针也能定位。
                            nonlocal fired
                            caller = frame.f_back
                            matches = (frame.f_code is reserve_code and frame.f_locals.get('self') is budget
                                       and event == phase and caller is not None
                                       and caller.f_code is caller_code)
                            if not fired and matches:
                                fired = True
                                raise KeyboardInterrupt('模拟预申请边界取消')
                            return cancel_reservation

                        try:
                            sys.settrace(cancel_reservation)
                            with self.assertRaises(KeyboardInterrupt):
                                if stage == 'constructor':
                                    BudgetedTemporalDetector(budget, rule('rising_edge'), 0, 4, backend=backend)
                                elif stage == 'push':
                                    detector.push((tick(2, T.FALSE), tick(3, T.TRUE)))
                                else:
                                    detector.finish()
                        finally:
                            # 构造失败或其他断言失败均恢复原trace，不污染重试和最终清理。
                            sys.settrace(previous_trace)
                        self.assertTrue(fired)
                        self.assertEqual(budget.ram_bytes, before)
                        if stage == 'constructor':
                            # 未返回半成品；合法同构造重试仍使用原账本、最终只留外部占用。
                            retry, _ = self.owner(rule('rising_edge'), 0, 4, backend=backend, budget=budget)
                            retry.close()
                        else:
                            # core状态、此前批和failed标志都保持原值，不能把core前取消fail-stop。
                            self.assertIs(detector._detector, core)
                            self.assertEqual(dict(vars(core), events=tuple(core.events)), before_state)
                            self.assertFalse(detector.failed)
                            self.assertFalse(prior.closed)
                            self.assertEqual(tuple(detector._results), (prior,))
                            self.assertEqual(self.facts(prior.events), [(1, 1, None, 'point')])
                            if stage == 'push':
                                result = self.batch(detector, (tick(2, T.FALSE), tick(3, T.TRUE)))
                                self.assertEqual(self.facts(result.events), [(3, 3, None, 'point')])
                            else:
                                result = detector.finish()
                                self.addCleanup(result.close)
                                self.assertEqual(result.events, ())
                            result.close()
                            detector.close()
                        # owner关闭只能释放自有内容，外部4096字节最后由夹具解除。
                        self.assertEqual(budget.ram_bytes, 4096)
                        budget.release_ram(4096)
                        self.assertEqual(budget.ram_bytes, 0)

    def test_constructor_invalid_metadata_and_core_failure_restore_prior_budget(self):
        """非法配置和固定申请后的core构造失败抵销本owner成本。

        参数: 无。返回: None。异常: 配置误接受或既有账本被清除断言失败。
        """
        # 模拟账本已有无关工作，失败只允许抵销新owner的预留。
        budget = ResourceBudget(64 * 1024 ** 2)
        budget.reserve_ram(4096)
        # 外部既有申请是无关工作，任何失败不能代替调用方释放。
        variants = ((rule(), 0, 3, (), 'fast'), ('rule', 0, 3, (), 'numpy'),
                    (rule(), 3, 0, (), 'numpy'),
                    (rule(), 0, 3, (SourceRef('other', 'sensor', 'raw.x'),), 'numpy'))
        for selected_rule, start, end, refs, backend in variants:
            # 配置语义、范围和会话归属各自拒绝，不能静默换后端或清空来源。
            with self.subTest(backend=backend, start=start, end=end):
                with self.assertRaises((TypeError, ValueError)):
                    BudgetedTemporalDetector(budget, selected_rule, start, end, refs, backend=backend)
                self.assertEqual(budget.ram_bytes, 4096)
        # 后端实例真正创建时分配失败，固定预留也须恢复到外部原值。
        for name in ('ReferenceTemporalDetector', 'NumpyTemporalDetector'):
            backend = 'reference' if name.startswith('Reference') else 'numpy'
            with patch('chronaxis.execution.temporal_buffer.' + name, side_effect=MemoryError('构造失败')):
                with self.assertRaises(MemoryError):
                    BudgetedTemporalDetector(budget, rule(), 0, 3, backend=backend)
            self.assertEqual(budget.ram_bytes, 4096)
        # 固定预算不足时也必须先拒绝，不能先建立未计账的core再清理。
        empty_budget = ResourceBudget(1)
        with patch('chronaxis.execution.temporal_buffer.ReferenceTemporalDetector') as reference_core:
            with patch('chronaxis.execution.temporal_buffer.NumpyTemporalDetector') as numpy_core:
                with self.assertRaises(BudgetExceededError):
                    BudgetedTemporalDetector(empty_budget, rule(), 0, 3)
                reference_core.assert_not_called()
                numpy_core.assert_not_called()
        self.assertEqual(empty_budget.ram_bytes, 0)
        # 只有夹具外部占用由本测试解除，最后确认未留下构造失败账目。
        budget.release_ram(4096)
        self.assertEqual(budget.ram_bytes, 0)

    def assert_failed_owner_preserves_prior(self, owner, budget, prior, baseline):
        """检查推进后故障必须fail-stop，但已有结果仍独立有效且清理可抵销。

        参数: owner失败实例、budget账本、prior旧批、baseline失败前RAM。
        返回: None。异常: 生命周期或预算错误断言失败。
        """
        # fail-stop丢弃不可安全重试的core，但不关闭owner已有结果或固定诊断。
        self.assertTrue(owner.failed)
        self.assertFalse(owner.closed)
        self.assertIsNone(owner._detector)
        self.assertEqual(budget.ram_bytes, baseline)
        self.assertEqual(tuple(owner._results), (prior,))
        self.assertFalse(prior.closed)
        self.assertEqual(self.facts(prior.events), [(1, 1, None, 'point')])
        # 禁止重试的精确异常是AnalysisError，不把生命周期错误吞成空输出。
        for method in ('push', 'finish'):
            # 失败后不允许接着原状态重试，关闭不重发旧事实。
            with self.assertRaises(AnalysisError):
                if method == 'push':
                    owner.push(())
                else:
                    owner.finish()
        # 旧批和固定申请分别释放一次，部分安装新批不得造成重复抵销。
        prior.close()
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_core_push_drain_finish_and_cancellation_fail_stop_keep_prior_results(self):
        """core开始后的推进/排空/finish错误与取消清理新申请且保留旧批。

        参数: 无。返回: None。异常: 未fail-stop、旧批失效或泄漏断言失败。
        """
        # 每个后端、推进阶段和异常类型使用独立owner，不共享失败状态。
        for backend in ('reference', 'numpy'):
            for method in ('push', 'drain_events', 'finish'):
                for failure in (MemoryError, KeyboardInterrupt):
                    with self.subTest(backend=backend, method=method, failure=failure.__name__):
                        owner, budget = self.owner(rule('rising_edge'), 0, 4, backend=backend)
                        prior = self.batch(owner, (tick(0, T.FALSE), tick(1, T.TRUE)))
                        if method == 'finish':
                            # 先合法消费terminal，使故障来自指定finish阶段而非缺末点。
                            terminal = self.batch(owner, (tick(4, T.UNKNOWN, quality=Q.MISSING,
                                                              actual=False, terminal=True),))
                            terminal.close()
                        baseline = budget.ram_bytes
                        core_type = type(owner._detector)
                        # patch指定core方法，取消和分配失败都不得留半推进实例供重试。
                        with patch.object(core_type, method, side_effect=failure('模拟core故障')):
                            with self.assertRaises(failure):
                                if method == 'finish':
                                    owner.finish()
                                else:
                                    owner.push((tick(2, T.FALSE), tick(3, T.TRUE)))
                        # 统一核对failed、旧批与账本清理，不放宽业务或预算断言。
                        self.assert_failed_owner_preserves_prior(owner, budget, prior, baseline)

    def test_two_backends_and_splits_keep_hand_facts_and_stable_ids(self):
        """两段活动跨1/2/7与空批不合并，不改确认时刻或稳定事件身份。

        参数: 无。返回: None。异常: 事件事实、切分身份或状态继承断言失败。
        """
        # 两段TRUE之间存在真实FALSE，不允许按批次或片段策略合并原始活动。
        ticks = (tick(0, T.TRUE), tick(1, T.TRUE, actual=False), tick(2, T.FALSE),
                 tick(3, T.TRUE), tick(4, T.TRUE, actual=False), tick(5, T.FALSE),
                 tick(6, T.UNKNOWN, quality=Q.MISSING, actual=False, eof=True, terminal=True,
                      point=T.FALSE, point_quality=Q.NONE))
        # 身份只作跨切分一致性核对；所有时间和主状态均有独立手算预期。
        identities = None
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                with self.subTest(backend=backend, size=size):
                    owner, budget = self.owner(rule(duration=1), 0, 6, backend=backend)
                    events = self.consume(owner, ticks, size)
                    self.assertEqual(self.facts(events), [(0, 1, 2, 'closed'), (3, 4, 5, 'closed')])
                    # 不同真实活动有不同稳定ID，两核和任何切分不再生成新身份。
                    current = tuple(event.event_id for event in events)
                    self.assertEqual(len(set(current)), 2)
                    identities = current if identities is None else identities
                    self.assertEqual(current, identities)
                    # 消费helper已释放每批，owner关闭抵销剩余固定预算。
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_adjacent_nanoseconds_and_deadlines_near_integer_extremes(self):
        """极值和2**53附近相邻1ns坐标精确，不用浮点或减一哨兵。

        参数: 无。返回: None。异常: int64边界或deadline损失精度断言失败。
        """
        # 采用合法短跨度，分别覆盖负极值、浮点精度阈值和正极值附近。
        for backend in ('reference', 'numpy'):
            for start in (-(2 ** 63), 2 ** 53 + 1, 2 ** 63 - 4):
                with self.subTest(backend=backend, start=start):
                    owner, budget = self.owner(rule(duration=1), start, start + 3, backend=backend)
                    first = self.batch(owner, (tick(start, T.TRUE),))
                    first.close()
                    # 精确1ns门槛必须保留原生整数；无实际timer只确认不输出未结束活动。
                    self.assertEqual(owner.next_deadline_ns, start + 1)
                    timer = self.batch(owner, (tick(start + 1, T.TRUE, actual=False),))
                    self.assertEqual(timer.events, ())
                    timer.close()
                    self.assertIsNone(owner.next_deadline_ns)
                    # 后续真实FALSE给活动独立end，确认不能改写为该更新时间。
                    ending = self.batch(owner, (tick(start + 2, T.FALSE),))
                    self.assertEqual(self.facts(ending.events), [(start, start + 1, start + 2, 'closed')])
                    ending.close()
                    # 合法末点封闭当前实例，各批独立关闭后最终账本归零。
                    terminal = self.batch(owner, (tick(start + 3, T.UNKNOWN, quality=Q.MISSING,
                                                        actual=False, terminal=True),))
                    terminal.close()
                    final = owner.finish()
                    final.close()
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_large_source_and_csv_metadata_are_owned_by_fixed_and_result_budgets(self):
        """长来源/CSV定位增加固定和批次独立成本，原字段与诊断文本完整保留。

        参数: 无。返回: None。异常: 只按事件数量计账或定位截断断言失败。
        """
        # 比较相同规则/点数下的短引用和巨大原字段/CSV诊断，不访问该合成路径。
        sizes = []
        for refs in ((SourceRef('session', 'sensor', 'raw.x'),),
                     (SourceRef('session', 'sensor', 'raw.' + 'x' * 32768),
                      CSVSourceRef('session', 'table', 'raw.x', 'work/' + 'p' * 32768 + '.csv',
                                   91, '1', '诊断文本' * 8192, False))):
            owner, budget = self.owner(rule('rising_edge'), 0, 2, refs=refs)
            fixed = budget.ram_bytes
            # 批次独立持有完整原定位，固定成本与结果持有成本分别记录。
            result = self.batch(owner, (tick(0, T.FALSE), tick(1, T.TRUE)))
            self.assertEqual(self.facts(result.events), [(1, 1, None, 'point')])
            self.assertEqual(result.events[0].source_refs, refs)
            retained = budget.ram_bytes - fixed
            self.assertGreater(retained, 0)
            sizes.append((fixed, retained))
            # 批次先释放应回到固定值，owner再释放，不代替外部释放引用。
            result.close()
            self.assertEqual(budget.ram_bytes, fixed)
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)
        # 长文本独立结果申请不能仅借固定owner计账，避免owner释放后漏计。
        self.assertGreater(sizes[1][0], sizes[0][0] + 32768)
        self.assertGreater(sizes[1][1], sizes[0][1] + 32768)

    def test_many_incremental_batches_release_events_and_keep_ram_bounded(self):
        """大量分批边沿即刻关闭，每批后固定RAM不随累计事件增长。

        参数: 无。返回: None。异常: 内部累计事件或未释放批次成本断言失败。
        """
        # 只保留当前7行输入与事件计数，大量稳定点不会增加owner累计结果列表。
        for backend in ('reference', 'numpy'):
            owner, budget = self.owner(rule('rising_edge'), 0, 1024, backend=backend)
            fixed, count = budget.ram_bytes, 0
            # 输入逐批新建，不建立全量axis；每7个tick最多4个point。
            for start in range(0, 1024, 7):
                current = tuple(tick(time, T.TRUE if time % 2 else T.FALSE)
                                for time in range(start, min(start + 7, 1024)))
                result = self.batch(owner, current)
                # 内部必须正式排空且每批close后回到固定RAM，不只检查返回数量。
                count += len(result.events)
                self.assertEqual(owner._detector.events, [])
                result.close()
                self.assertEqual(budget.ram_bytes, fixed)
            # 真正terminal与finish不得重发此前512个稳定rising点。
            terminal = self.batch(owner, (tick(1024, T.UNKNOWN, quality=Q.MISSING,
                                              actual=False, eof=True, terminal=True),))
            self.assertEqual(terminal.events, ())
            terminal.close()
            final = owner.finish()
            self.assertEqual(final.events, ())
            final.close()
            self.assertEqual(count, 512)
            self.assertEqual(budget.ram_bytes, fixed)
            # 完成实例关闭后释放固定申请；此断言不代表整进程RSS测量。
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)
            # 突发同时持有5000空批，再关到1/0；明确256MiB容纳全部合法工作预留。
            burst, burst_budget = self.owner(rule(duration=2), 0, 3, backend=backend,
                                             budget=ResourceBudget(256 * 1024 ** 2))
            first = burst.push((tick(0, T.TRUE),))
            first.close()
            fixed = burst_budget.ram_bytes
            core = burst._detector
            before = (core.last_time, core.candidate_start, core.confirmed)
            batches = [burst.push(()) for _ in range(5000)]
            self.assertEqual(len(tuple(burst._results)), 5000)
            self.assertGreater(burst_budget.ram_bytes, fixed)
            for result in batches[:-1]:
                result.close()
            # 此getsizeof仅核对固定登记容器；活节点须由剩余batch的workspace覆盖。
            self.assertEqual(tuple(burst._results), (batches[-1],))
            self.assertLessEqual(sys.getsizeof(burst._results), burst_budget.ram_bytes)
            self.assertGreater(burst_budget.ram_bytes, fixed)
            self.assertFalse(batches[-1].closed)
            self.assertEqual(batches[-1].events, ())
            # 已关闭节点清空双向链接，剩余单节点不再持有任何已关闭邻居。
            self.assertTrue(all(result._previous is None and result._next is None
                                and result._registry is None for result in batches[:-1]))
            self.assertIsNone(batches[-1]._previous)
            self.assertIsNone(batches[-1]._next)
            self.assertEqual((core.last_time, core.candidate_start, core.confirmed), before)
            self.assertEqual(burst.next_deadline_ns, 2)
            batches[-1].close()
            self.assertIsNone(batches[-1]._registry)
            # 全部批释放后不能留峰值槽位；无活节点仍只持有原固定账目。
            self.assertEqual(tuple(burst._results), ())
            self.assertEqual(burst_budget.ram_bytes, fixed)
            self.assertLessEqual(sys.getsizeof(burst._results), fixed)
            burst.close()
            self.assertEqual(burst_budget.ram_bytes, 0)

    def test_result_constructor_and_registration_failure_preserve_prior_batch(self):
        """已推进后新批次构造/登记失败进入failed，旧批仍按自己的申请持有。

        参数: 无。返回: None。异常: 旧批失效、申请未抵销或错误重试断言失败。
        """
        # 构造、普通登记、部分安装和最终交付都是本次结果的独立失败阶段。
        for backend in ('reference', 'numpy'):
            for stage, failure in (('constructor', MemoryError), ('constructor', KeyboardInterrupt),
                                   ('registration', MemoryError), ('after_registration', MemoryError),
                                   ('handoff', KeyboardInterrupt)):
                with self.subTest(backend=backend, stage=stage, failure=failure.__name__):
                    owner, budget = self.owner(rule('rising_edge'), 0, 4, backend=backend)
                    prior = self.batch(owner, (tick(0, T.FALSE), tick(1, T.TRUE)))
                    baseline = budget.ram_bytes
                    if stage == 'constructor':
                        # 构造尚未登记；MemoryError和取消均必须保留prior并抵销新申请。
                        with patch('chronaxis.execution.temporal_buffer.TemporalEventBatch',
                                   side_effect=failure('模拟结果构造失败')):
                            with self.assertRaises(failure):
                                owner.push((tick(2, T.FALSE), tick(3, T.TRUE)))
                    elif stage in ('registration', 'after_registration'):
                        # 替身保留所有已有句柄，新增add失败不会吞掉prior的所有权。
                        registry = RejectRegistry if stage == 'registration' else AddThenRejectRegistry
                        owner._results = registry(owner._results)
                        with self.assertRaises(MemoryError):
                            owner.push((tick(2, T.FALSE), tick(3, T.TRUE)))
                    else:
                        # 在构造helper返回到owner的交付窗口取消，外部trace必须最终恢复。
                        # 修正后helper只构造；原第二轮日志的旧helper在此处已完成登记。
                        previous_trace = sys.gettrace()
                        register_code = owner._register.__code__
                        fired = False

                        def cancel_handoff(frame, event, argument):
                            """仅取消一次本owner的结果构造helper返回，不干扰其他帧或清理。

                            参数: frame运行帧、event追踪事件、argument追踪参数。
                            返回: 当前追踪函数。异常: KeyboardInterrupt为指定交付取消。
                            """
                            # 精确比较code对象，只在第一次_register返回边界取消。
                            nonlocal fired
                            if not fired and frame.f_code is register_code and event == 'return':
                                fired = True
                                raise KeyboardInterrupt('模拟构造helper返回时取消')
                            # 其他帧继续沿用当前trace，不消费或修改任何业务状态。
                            return cancel_handoff

                        try:
                            sys.settrace(cancel_handoff)
                            with self.assertRaises(KeyboardInterrupt):
                                owner.push((tick(2, T.FALSE), tick(3, T.TRUE)))
                        finally:
                            # 任何断言或产品异常都恢复调用方原trace，避免影响后续专项。
                            sys.settrace(previous_trace)
                        self.assertTrue(fired)
                    # 本次新句柄不可残留登记，否则close会再次释放已抵销成本。
                    self.assert_failed_owner_preserves_prior(owner, budget, prior, baseline)

    def test_finish_requires_terminal_and_does_not_repeat_drained_output(self):
        """缺terminal不能finish，正常finish只封闭并拒绝后续输入、不重发旧事件。

        参数: 无。返回: None。异常: 缺末点误收尾或最终重复输出断言失败。
        """
        # 两后端先独立检查缺末点路径，再使用全新owner检查正常封闭。
        for backend in ('reference', 'numpy'):
            premature, early_budget = self.owner(rule(), 0, 3, backend=backend)
            with self.assertRaises(ValueError):
                premature.finish()
            # core已进入finish校验，失败后不能伪造末点并重试。
            self.assertTrue(premature.failed)
            premature.close()
            self.assertEqual(early_budget.ram_bytes, 0)
            # 真正terminal之后旧point批仍可读，正常finish只产生空增量。
            owner, budget = self.owner(rule('rising_edge'), 0, 3, backend=backend)
            result = self.batch(owner, (tick(0, T.FALSE), tick(1, T.TRUE),
                                       tick(3, T.UNKNOWN, quality=Q.MISSING,
                                            actual=False, terminal=True)))
            self.assertEqual(self.facts(result.events), [(1, 1, None, 'point')])
            final = owner.finish()
            self.addCleanup(final.close)
            self.assertEqual(final.events, ())
            self.assertFalse(result.closed)
            self.assertEqual(self.facts(result.events), [(1, 1, None, 'point')])
            for method, expected in (('push', ValueError), ('finish', AnalysisError)):
                # 第一次非法推进已进入core并fail-stop，后续调用由AnalysisError拒绝。
                with self.assertRaises(expected):
                    if method == 'push':
                        owner.push(())
                    else:
                        owner.finish()
            # 即便随后非法调用进入failed，先前已交付的两批仍由各自close清理。
            final.close()
            result.close()
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_batch_and_owner_properties_are_readonly_and_close_is_owned(self):
        """冻结配置/输出只读，批次幂等关闭，取消后释放与登记所有权一致。

        参数: 无。返回: None。异常: 属性可改、关闭取消/访问或预算误释放断言失败。
        """
        # 外部4096字节代表其他工作，owner关闭不能抵销这笔无关占用。
        budget = ResourceBudget(64 * 1024 ** 2)
        budget.reserve_ram(4096)
        selected = rule('rising_edge')
        owner, _ = self.owner(selected, 0, 3, budget=budget)
        self.assertIs(owner.rule, selected)
        self.assertEqual((owner.start_ns, owner.end_ns), (0, 3))
        self.assertIsNone(owner.next_deadline_ns)
        # 配置和生命周期只读，赋值不得绕过core协议或预算所有权。
        for name, value in (('rule', rule()), ('start_ns', 2), ('end_ns', 4),
                            ('next_deadline_ns', 1), ('closed', True), ('failed', True)):
            with self.assertRaises(AttributeError):
                setattr(owner, name, value)
        # 两批分别存活，先关闭第一批不能误关闭第二批或重复抵销第一批成本。
        first = self.batch(owner, (tick(0, T.FALSE), tick(1, T.TRUE)))
        second = self.batch(owner, (tick(2, T.FALSE),))
        self.assertIs(type(first.events), tuple)
        with self.assertRaises(AttributeError):
            first.events = ()
        with self.assertRaises(AttributeError):
            first.closed = True
        first.close()
        after_first_close = budget.ram_bytes
        first.close()
        self.assertEqual(budget.ram_bytes, after_first_close)
        with self.assertRaises(ResultClosedError):
            _ = first.events
        self.assertFalse(second.closed)
        # owner负责关闭当前自有结果与固定申请，重复关闭不再修改账本。
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertTrue(second.closed)
        with self.assertRaises(ResultClosedError):
            _ = second.events
        # 关闭后不允许再推进或finish，原外部账目留给调用方最后释放。
        for method in ('push', 'finish'):
            with self.assertRaises(ResultClosedError):
                if method == 'push':
                    owner.push(())
                else:
                    owner.finish()
        self.assertEqual(budget.ram_bytes, 4096)
        budget.release_ram(4096)
        self.assertEqual(budget.ram_bytes, 0)
        # 四窗口采用默认登记器与真实账本；精确实例/code防止误拦其他批的清理。
        for backend in ('reference', 'numpy'):
            for method in ('discard', 'release_ram'):
                for phase in ('call', 'return'):
                    with self.subTest(backend=backend, method=method, phase=phase):
                        detector, current_budget = self.owner(rule('rising_edge'), 0, 4, backend=backend)
                        prior = self.batch(detector, (tick(0, T.FALSE), tick(1, T.TRUE)))
                        current = self.batch(detector, (tick(2, T.FALSE), tick(3, T.TRUE)))
                        before, cost, prior_cost = current_budget.ram_bytes, current._cost, prior._cost
                        instance = detector._results if method == 'discard' else current_budget
                        target = getattr(instance, method).__func__.__code__
                        previous_trace, fired = sys.gettrace(), False

                        def cancel_close(frame, event, argument):
                            """仅在当前批脱链/抵销的指定入口或返回边界取消一次。

                            参数: frame运行帧、event追踪事件、argument追踪参数。
                            返回: 当前追踪函数。异常: KeyboardInterrupt为指定关闭取消。
                            """
                            # 同code还须同实例及本批参数，保证prior和无关工作不受影响。
                            nonlocal fired
                            matches = (frame.f_code is target and frame.f_locals.get('self') is instance
                                       and event == phase)
                            selected = (frame.f_locals.get('result') is current if method == 'discard'
                                        else frame.f_locals.get('amount') == cost)
                            if not fired and matches and selected:
                                fired = True
                                raise KeyboardInterrupt('模拟事件批关闭边界取消')
                            return cancel_close

                        try:
                            sys.settrace(cancel_close)
                            with self.assertRaises(KeyboardInterrupt):
                                current.close()
                        finally:
                            # 抛错后仍恢复原trace，后续retry与owner.close不再注入取消。
                            sys.settrace(previous_trace)
                        self.assertTrue(fired)
                        self.assertFalse(detector.failed)
                        self.assertFalse(prior.closed)
                        self.assertEqual(prior._cost, prior_cost)
                        self.assertEqual(self.facts(prior.events), [(1, 1, None, 'point')])
                        if method == 'release_ram' and phase == 'call':
                            # 未进入抵销体，结果保持开放且仍由owner登记，可重试同一close。
                            self.assertEqual(current_budget.ram_bytes, before)
                            self.assertFalse(current.closed)
                            self.assertEqual(current._cost, cost)
                            self.assertEqual(set(detector._results), {prior, current})
                            self.assertEqual(self.facts(current.events), [(3, 3, None, 'point')])
                            current.close()
                        else:
                            # 已抵销时最小收尾必须完成，不能留下非零cost等待第二次释放。
                            self.assertEqual(current_budget.ram_bytes, before - cost)
                            self.assertTrue(current.closed)
                            self.assertEqual(current._cost, 0)
                            self.assertEqual(tuple(detector._results), (prior,))
                            self.assertIsNone(current._previous)
                            self.assertIsNone(current._next)
                            self.assertIsNone(current._registry)
                            with self.assertRaises(ResultClosedError):
                                _ = current.events
                        # 已释放和重试成功两路径都只能扣一次，owner最后安全关闭prior。
                        self.assertEqual(current_budget.ram_bytes, before - cost)
                        current.close()
                        self.assertEqual(current_budget.ram_bytes, before - cost)
                        detector.close()
                        self.assertTrue(prior.closed)
                        self.assertEqual(current_budget.ram_bytes, 0)
        # owner固定抵销只拦截直接来自该owner.close的调用，排除内部batch.close。
        for backend in ('reference', 'numpy'):
            for phase in ('call', 'return'):
                with self.subTest(backend=backend, fixed_release=phase):
                    fixed_budget = ResourceBudget(64 * 1024 ** 2)
                    fixed_budget.reserve_ram(4096)
                    detector, _ = self.owner(rule('rising_edge'), 0, 4, backend=backend, budget=fixed_budget)
                    prior = self.batch(detector, (tick(0, T.FALSE), tick(1, T.TRUE)))
                    fixed = detector._fixed_cost
                    release_code = fixed_budget.release_ram.__func__.__code__
                    close_code = detector.close.__func__.__code__
                    previous_trace, fired = sys.gettrace(), False

                    def cancel_fixed_release(frame, event, argument):
                        """仅取消当前owner固定申请的直接抵销，不取消其活动批关闭。

                        参数: frame运行帧、event追踪事件、argument追踪参数。
                        返回: 当前追踪函数。异常: KeyboardInterrupt为固定抵销取消。
                        """
                        # 使用精确f_back owner实例/code，即便批次金额相同也不会误拦。
                        nonlocal fired
                        caller = frame.f_back
                        matches = (frame.f_code is release_code and frame.f_locals.get('self') is fixed_budget
                                   and event == phase and caller is not None and caller.f_code is close_code
                                   and caller.f_locals.get('self') is detector)
                        if not fired and matches:
                            fired = True
                            raise KeyboardInterrupt('模拟owner固定抵销取消')
                        return cancel_fixed_release

                    try:
                        sys.settrace(cancel_fixed_release)
                        with self.assertRaises(KeyboardInterrupt):
                            detector.close()
                    finally:
                        # 取消后的最小收尾和下一次close都使用恢复后的正常追踪环境。
                        sys.settrace(previous_trace)
                    self.assertTrue(fired)
                    self.assertTrue(prior.closed)
                    self.assertFalse(detector.failed)
                    if phase == 'call':
                        # 自有批已正常释放，固定申请尚未扣除，owner仍开放可close重试。
                        self.assertFalse(detector.closed)
                        self.assertEqual(detector._fixed_cost, fixed)
                        self.assertEqual(fixed_budget.ram_bytes, 4096 + fixed)
                    else:
                        # 固定抵销完成后的取消须完成关闭，不再持有可重复释放的金额。
                        self.assertTrue(detector.closed)
                        self.assertEqual(detector._fixed_cost, 0)
                        self.assertEqual(fixed_budget.ram_bytes, 4096)
                    detector.close()
                    detector.close()
                    self.assertEqual(fixed_budget.ram_bytes, 4096)
                    fixed_budget.release_ram(4096)
                    self.assertEqual(fixed_budget.ram_bytes, 0)

    def test_formal_core_drain_transfers_output_without_resetting_open_candidate(self):
        """两个core正式排空接口仅转交输出，不重置deadline/确认/跨批活动。

        参数: 无。返回: None。异常: 排空重发、候选重置或finish重复输出断言失败。
        """
        # 正式排空行为分别在两个原core执行，不用wrapper替代此接口验收。
        for core_type in (ReferenceTemporalDetector, NumpyTemporalDetector):
            core = core_type(rule(duration=1), 0, 5)
            core.push((tick(0, T.TRUE),))
            self.assertEqual(core.next_deadline_ns, 1)
            self.assertEqual(core.drain_events(), ())
            self.assertEqual(core.next_deadline_ns, 1)
            # 第一活动结束后排空一次，既有push增量与正式转交事件一致且无重复。
            new = core.push((tick(1, T.TRUE, actual=False), tick(2, T.FALSE)))
            drained = core.drain_events()
            self.assertEqual(self.facts(drained), [(0, 1, 2, 'closed')])
            self.assertEqual(drained, new)
            self.assertEqual(core.events, [])
            self.assertEqual(core.drain_events(), ())
            # 第二开放活动的onset/confirmed在空排空后保留，不能当作重新开始。
            core.push((tick(3, T.TRUE), tick(4, T.TRUE, actual=False)))
            self.assertEqual(core.drain_events(), ())
            self.assertEqual((core.candidate_start, core.confirmed), (3, 4))
            # 真正EOF仅结束第二活动，已排空的第一活动不会在finish中重发。
            core.push((tick(5, T.UNKNOWN, quality=Q.MISSING, actual=False,
                            eof=True, terminal=True),))
            self.assertEqual(self.facts(core.drain_events()), [(3, 4, 5, 'truncated')])
            self.assertEqual(core.finish(), ())
            # 未使用drain的原便捷路径仍保存其全部事件，兼容语义不改变。
            legacy = core_type(rule('rising_edge'), 0, 2)
            legacy.push((tick(0, T.FALSE), tick(1, T.TRUE),
                         tick(2, T.UNKNOWN, quality=Q.MISSING, actual=False, terminal=True)))
            self.assertEqual(self.facts(legacy.finish()), [(1, 1, None, 'point')])
