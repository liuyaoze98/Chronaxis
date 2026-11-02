"""验证显式实际观测域驱动查询，以及完整时间组的来源子集。

输入为真实内存或CSV来源，经封存历史、实际绑定和原HoldContext建立查询。
测试用手算的8/12纳秒范围、域前种子、真实末点和int64端点核对事件；
两查询必须保留原表达式owner，类型/范围或不同实际域在新增预算之前拒绝。
来源子集只归并指定来源，真实源游标仍检查计数和SHA；不能以子集EOF冒充全历史。
文件只写新项目work目录，测试逐层关闭并断言共享RAM归零，不改历史CAN路径。
device_label: home。
"""

from configuration_fixtures import current_fixture

# 使用模块别名复用真实工厂，避免把既有TestCase重复加入发现列表。
import json
import unittest
from unittest.mock import patch
import test_stream_boundaries as real_queries
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.temporal import TemporalRule
from chronaxis.core.types import SignalDType as D, Truth as T
from chronaxis.execution.boundaries import BoundaryQueries, RuleDeadline
from chronaxis.execution.condition_evidence import ConditionEvidenceQueries
from chronaxis.execution.timeline import TemporalTimeline
from chronaxis.execution.timeline_multi import MultiRuleTimeline, TimelineRule
from chronaxis.results.errors import AnalysisError, BudgetExceededError


class ObservationDomainQueryTests(unittest.TestCase):
    """每例拥有真实来源工厂及其逆序清理，新查询只关闭自身资源。"""

    def fixture(self, **kwargs):
        """建立保持原请求域的真实查询工厂并登记最终RAM检查。

        参数: kwargs为旧工厂的来源、批次、表达式和domain设置。
        返回: 含history/state/holds/expressions等真实对象的夹具。
        异常: 读取、绑定、编译或预算错误原样传播。
        """
        # 先登记工厂清理，后建的独立查询和游标会在借用资源之前关闭。
        factory = real_queries.StreamBoundaryTests('runTest')
        factory.setUp()
        fixture = factory.prepare(**kwargs)
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        return fixture

    def cleanup_fixture(self, factory, budget):
        """关闭原工厂全部资源并证明没有借用或自有预算遗留。

        参数: factory真实工厂；budget共享账本。返回: None。
        异常: 关闭错误或RAM非零触发AssertionError。
        """
        # 原工厂的内部清理异常不能被本测试的成功结果掩盖。
        self.assertTrue(factory.doCleanups(), '实际范围夹具关闭失败')
        self.assertEqual(budget.ram_bytes, 0)

    def owners(self, fixture, *, backend='numpy', observation=None):
        """在原表达式对象上建立同一实际域的两查询。

        参数: fixture真实夹具；backend独立后端；observation为Interval或None。
        返回: (evidence,boundaries)，均已登记清理。
        异常: 输入、上游生命周期或预算错误传播。
        """
        # 两查询各拥有固定预算，但不复制context、bindings或表达式登记树。
        evidence = ConditionEvidenceQueries(fixture.expressions, backend=backend, observation=observation)
        self.addCleanup(evidence.close)
        boundaries = BoundaryQueries(fixture.expressions, observation=observation)
        self.addCleanup(boundaries.close)
        return evidence, boundaries

    def consume(self, fixture, evidence, boundaries, rule, *, multi=False):
        """用同一真实前瞻推进单或多规则游标，收集有限手算夹具结果。

        参数: fixture与两查询；rule冻结规则；multi选择共同入口的多规则调用。
        返回: (events,facts) tuple；facts为(整数时刻,是否消费组,条件tick)。
        异常: 实际推进错误传播；有限输入超过100步触发AssertionError。
        """
        # 域前组已经由调用方提交为种子，不再交给新时间线重复提交。
        groups = tuple(group for group in fixture.groups if group.time_ns >= evidence._start)
        timeline = (MultiRuleTimeline(evidence, boundaries, (TimelineRule(rule, fixture.compiled[0]),))
                    if multi else TemporalTimeline(evidence, boundaries, fixture.compiled[0], rule))
        self.addCleanup(timeline.close)
        index, events, facts = 0, [], []
        for _ in range(100):
            step = timeline.step(groups[index] if index < len(groups) else None)
            if step is None:
                return tuple(events), tuple(facts)
            try:
                # 多规则只有一个槽，读取其原输出，不改变被测检测器推进顺序。
                tick = step.ticks[0] if multi else step.tick
                events.extend(step.events_by_rule[0] if multi else step.events)
                facts.append((step.time_ns, step.consumed_group, tick))
                if step.consumed_group:
                    index += 1
            finally:
                step.close()
        self.fail('有限实际范围未在100步内结束')

    def event_fields(self, events):
        """提取手算所需事件边界，排除与本契约无关的展示字段。

        参数: events有限Event tuple。返回: 稳定边界字段tuple。
        异常: 输入结构错误传播。
        """
        return tuple((event.start_ns, event.confirmed_ns, event.end_ns, event.status) for event in events)

    def test_explicit_end_closes_constant_and_decisive_true_at_eight(self):
        """请求到12ns而实际到8ns，常量和决定性TRUE都只累计到8ns。

        参数: 无。返回: None。异常: 沿请求域延长、改变绑定或末点标志错误断言失败。
        """
        # 两个表达式分别覆盖零信号依赖与仍持有信号依赖的决定性TRUE，旧请求域不变。
        definition = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20)
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(8, {'raw.a': 0}, 1))}
        for backend in ('reference', 'numpy'):
            for kind in ('memory', 'csv'):
                for text in ('True', '(a > 0) or True'):
                    for multi in (False, True):
                        with self.subTest(backend=backend, kind=kind, text=text, multi=multi):
                            fixture = self.fixture(definitions=(definition,), domain=(0, 12),
                                bounds={'table': (0, 8)}, rows_by_source=rows, texts=(text,), kind=kind, backend=backend)
                            original = fixture.holds._context
                            actual = Interval(0, 8)
                            evidence, boundaries = self.owners(fixture, backend=backend, observation=actual)
                            rule = TemporalRule('rule', 'dataset', 'session', 'condition_duration', 3)
                            events, facts = self.consume(fixture, evidence, boundaries, rule, multi=multi)
                            self.assertEqual(self.event_fields(events), ((0, 3, 8, 'truncated'),))
                            self.assertEqual(facts[-1][0], 8)
                            self.assertTrue(facts[-1][2].terminal)
                            self.assertIs(fixture.holds._context, original)
                            self.assertEqual((original.domain.start_ns, original.domain.end_ns), (0, 12))
                            self.assertIs(boundaries._domain, actual)
                            self.assertIs(boundaries._expressions, evidence._queries)

    def test_none_preserves_original_domain_and_default_costs(self):
        """未给实际域仍沿原12ns结束，固定申请与原有接口一致。

        参数: 无。返回: None。异常: 默认语义或两笔固定预算改变断言失败。
        """
        fixture = self.fixture(domain=(0, 12), texts=('True',),
            rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0),)})
        baseline = fixture.budget.ram_bytes
        evidence, boundaries = self.owners(fixture)
        self.assertEqual(fixture.budget.ram_bytes - baseline, 65536 + 512 + 32768)
        self.assertIs(boundaries._domain, fixture.holds._context.domain)
        events, facts = self.consume(fixture, evidence, boundaries,
            TemporalRule('rule', 'dataset', 'session', 'condition_duration', 3))
        self.assertEqual(self.event_fields(events), ((0, 3, 12, 'truncated'),))
        self.assertEqual(facts[-1][0], 12)

    def test_range_validation_happens_before_own_budget(self):
        """非Interval和原请求外范围直接拒绝，不先预留再回滚。

        参数: 无。返回: None。异常: 类型、范围错误或提前预算申请断言失败。
        """
        fixture = self.fixture(domain=(0, 12))
        # 预算替身只记录禁止调用；原表达式及状态已在替身安装前准备好。
        for value, error in (((0, 8), TypeError), (False, TypeError),
                             (Interval(-1, 8), ValueError), (Interval(0, 13), ValueError)):
            for query in (ConditionEvidenceQueries, BoundaryQueries):
                with self.subTest(value=value, query=query.__name__):
                    with patch.object(fixture.budget, 'reserve_ram', side_effect=AssertionError('错误域先申请预算')) as reserve:
                        with self.assertRaises(error):
                            query(fixture.expressions, observation=value)
                        reserve.assert_not_called()

    def test_mismatched_actual_domains_rejected_before_single_or_multi_detector(self):
        """同一表达式owner的不同实际起点或终点不能组合成时间线。

        参数: 无。返回: None。异常: 不匹配仍创建Detector或产生预算动作断言失败。
        """
        fixture = self.fixture(domain=(0, 12))
        evidence = ConditionEvidenceQueries(fixture.expressions, observation=Interval(0, 8))
        self.addCleanup(evidence.close)
        rule = TemporalRule('rule', 'dataset', 'session', 'condition_duration', 3)
        for interval in (Interval(0, 12), Interval(1, 8)):
            boundaries = BoundaryQueries(fixture.expressions, observation=interval)
            self.addCleanup(boundaries.close)
            with patch.object(fixture.budget, 'reserve_ram', side_effect=AssertionError('域错配先创建Detector')) as reserve:
                with self.assertRaisesRegex(ValueError, '实际观测范围'):
                    TemporalTimeline(evidence, boundaries, fixture.compiled[0], rule)
                with self.assertRaisesRegex(ValueError, '实际观测范围'):
                    MultiRuleTimeline(evidence, boundaries, (TimelineRule(rule, fixture.compiled[0]),))
                reserve.assert_not_called()
        self.assertEqual(fixture.state.revision, 0)

    def test_candidate_filtering_and_actual_after_bounds(self):
        """原context内但实际域外的TTL/更新/截止不延长实际终点。

        参数: 无。返回: None。异常: 域外候选越过实际终点或after未受限断言失败。
        """
        definition = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 10)
        fixture = self.fixture(domain=(0, 12), definitions=(definition,), bounds={'table': (0, 12)},
            rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0),)})
        _, boundaries = self.owners(fixture, observation=Interval(0, 8))
        fixture.state.apply(fixture.groups[0])
        result = boundaries.query_next(fixture.compiled[0], after_ns=0, next_group_ns=11,
            duration_deadlines=(RuleDeadline('rule', 9),))
        try:
            self.assertEqual(result.time_ns, 8)
            self.assertEqual(tuple((reason.reason_type, reason.target) for reason in result.reasons), (('domain_end', ''),))
        finally:
            result.close()
        self.assertIsNone(boundaries.query_next(fixture.compiled[0], after_ns=8))
        with self.assertRaises(ValueError):
            boundaries.query_next(fixture.compiled[0], after_ns=9)

    def test_pre_domain_seed_and_true_terminal_point_at_int64_edges(self):
        """真实域前种子不重复提交，末点边沿包含且没有start-1或加周期溢出。

        参数: 无。返回: None。异常: 种子丢失、末点扩展持续时间或整数精度错误断言失败。
        """
        # 三个起点涵盖INT64_MIN、超过浮点精度边界及INT64_MAX附近。
        for start in (-(2 ** 63), 2 ** 53 + 1, 2 ** 63 - 13):
            for backend in ('reference', 'numpy'):
                definition = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20)
                rows = {'table': (MemoryRow(start, {'raw.a': 0}, 0), MemoryRow(start + 8, {'raw.a': 1}, 1))}
                fixture = self.fixture(domain=(start, start + 12), bounds={'table': (start, start + 8)},
                    definitions=(definition,), rows_by_source=rows, backend=backend)
                evidence, boundaries = self.owners(fixture, backend=backend, observation=Interval(start + 2, start + 8))
                fixture.state.apply(fixture.groups[0])
                events, facts = self.consume(fixture, evidence, boundaries,
                    TemporalRule('rule', 'dataset', 'session', 'rising_edge'))
                self.assertEqual(self.event_fields(events), ((start + 8, start + 8, None, 'point'),))
                self.assertEqual(facts[0][:2], (start + 2, False))
                self.assertEqual(fixture.state.revision, 2)
                self.assertTrue(facts[-1][2].actual_update)
                self.assertTrue(facts[-1][2].terminal)

    def test_real_zero_length_domain_preserves_point_without_new_activity(self):
        """真实单点保留点证据，首次TRUE只在显式初始化策略下生成点事件。

        参数: 无。返回: None。异常: 把单点跳过、把UNKNOWN当FALSE或增加持续时间断言失败。
        """
        for backend in ('reference', 'numpy'):
            for kind, emit_initial in (('condition_duration', False), ('rising_edge', False), ('rising_edge', True)):
                fixture = self.fixture(domain=(0, 12), texts=('a > 0',), backend=backend,
                    rows_by_source={'table': (MemoryRow(8, {'raw.a': 1}, 0),)}, bounds={'table': (8, 8)})
                evidence, boundaries = self.owners(fixture, backend=backend, observation=Interval(8, 8))
                events, facts = self.consume(fixture, evidence, boundaries,
                    TemporalRule('rule', 'dataset', 'session', kind, emit_initial=emit_initial))
                # T11要求默认UNKNOWN→TRUE没有rising；显式初始化点不能冒称已知边沿。
                expected = ((8, 8, None, 'point'),) if emit_initial else ()
                self.assertEqual(self.event_fields(events), expected)
                if emit_initial:
                    self.assertEqual(events[0].trigger_kind, 'initial')
                self.assertEqual(len(facts), 1)
                self.assertEqual(facts[0][2].state, T.UNKNOWN)
                self.assertEqual(facts[0][2].point_state, T.TRUE)

    def source_fixture(self, *, kind='memory'):
        """建立两个有同刻记录且结束时间不同的真实来源。

        参数: kind为memory或csv。返回: 原真实夹具。
        异常: 来源读取、封存和绑定错误传播。
        """
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 20))
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(8, {'raw.a': 2}, 1)),
                'other': (MemoryRow(0, {'raw.b': 3}, 0), MemoryRow(5, {'raw.b': 4}, 1))}
        return self.fixture(definitions=definitions, rows_by_source=rows, domain=(0, 12), kind=kind,
            bounds={'table': (0, 8), 'other': (0, 5)})

    def test_sources_subset_excludes_other_same_time_and_preserves_default(self):
        """子集只开所选真实FD，同刻外来源不并入组；默认仍归并全部来源。

        参数: 无。返回: None。异常: 额外开源、样本混入或EOF/关闭预算错误断言失败。
        """
        for kind in ('memory', 'csv'):
            fixture = self.source_fixture(kind=kind)
            history, budget = fixture.history, fixture.budget
            baseline = budget.ram_bytes
            original = history.iter_records
            with patch.object(history, 'iter_records', wraps=original) as opened:
                iterator = history.iter_groups(sources=('table',))
                readers = tuple(iterator.readers)
                groups = tuple(iterator)
                self.assertEqual([call.args[0] for call in opened.call_args_list], ['table'])
            self.assertEqual(tuple(group.time_ns for group in groups), (0, 8))
            self.assertEqual(tuple(sample.source_ref.source_name for group in groups for sample in group.samples), ('table', 'table'))
            self.assertTrue(all(reader.closed and reader.verified_eof and reader.handle.closed for reader in readers))
            self.assertEqual(budget.ram_bytes, baseline)
            default = tuple(history.iter_groups())
            self.assertEqual(tuple(group.time_ns for group in default), (0, 5, 8))
            self.assertEqual(len(default[0].samples), 2)
            self.assertFalse(history.closed)
            self.assertEqual(budget.ram_bytes, baseline)

    def test_subset_validation_before_budget_and_empty_subset_opens_nothing(self):
        """子集类型、重复和未知名先拒绝，显式空子集合法且不打开任何源。

        参数: 无。返回: None。异常: 参数错误后仍申请/打开或空集混入来源断言失败。
        """
        fixture = self.source_fixture()
        history, budget = fixture.history, fixture.budget
        for sources, error in (('table', TypeError), (['table'], TypeError), ((1,), TypeError),
                               (('table', 'table'), ValueError), (('unknown',), ValueError)):
            with patch.object(budget, 'reserve_ram', side_effect=AssertionError('非法子集先预约')) as reserve:
                with patch.object(history, 'iter_records', side_effect=AssertionError('非法子集先开源')) as opened:
                    with self.assertRaises(error):
                        history.iter_groups(sources=sources)
                    reserve.assert_not_called()
                    opened.assert_not_called()
        baseline = budget.ram_bytes
        with patch.object(history, 'iter_records', side_effect=AssertionError('空集先开源')) as opened:
            self.assertEqual(tuple(history.iter_groups(sources=())), ())
            opened.assert_not_called()
        self.assertEqual(budget.ram_bytes, baseline)

    def test_selected_source_sha_is_checked_without_claiming_full_history(self):
        """所选来源读到真实EOF才验证SHA，未选来源损坏仍由全来源重放发现。

        参数: 无。返回: None。异常: 子集跳过自己的摘要或替全历史背书断言失败。
        """
        fixture = self.source_fixture()
        history, budget = fixture.history, fixture.budget
        path = history.paths['other']
        original = path.read_bytes()
        first, remaining = original.split(b'\n', 1)
        # 仅逆转合法JSON对象键顺序，值和行字节长度不变，使计数通过而SHA不同。
        decoded = json.loads(first)
        changed = json.dumps(current_fixture(dict(reversed(tuple(decoded.items())))), ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')
        self.assertEqual(len(changed), len(first))
        self.assertNotEqual(changed, first)
        path.write_bytes(changed + b'\n' + remaining)
        self.addCleanup(path.write_bytes, original)
        baseline = budget.ram_bytes
        self.assertEqual(tuple(group.time_ns for group in history.iter_groups(sources=('table',))), (0, 8))
        with self.assertRaisesRegex(AnalysisError, '摘要'):
            tuple(history.iter_groups(sources=('other',)))
        self.assertEqual(budget.ram_bytes, baseline)
        with self.assertRaisesRegex(AnalysisError, '摘要'):
            tuple(history.iter_groups())
        self.assertFalse(history._iterators)
        self.assertFalse(history._groups)
        self.assertEqual(budget.ram_bytes, baseline)

    def test_subset_fixed_cost_and_failure_cleanup_preserve_borrowed_budget(self):
        """子集状态随实际源数计费，构造预约后取消及读组拒绝均关闭真实句柄。

        参数: 无。返回: None。异常: 多计无关源、漏账或子句柄遗留断言失败。
        """
        fixture = self.source_fixture()
        history, budget = fixture.history, fixture.budget
        baseline = budget.ram_bytes
        subset = history.iter_groups(sources=('table',))
        subset_cost = subset._state_cost
        subset.close()
        all_sources = history.iter_groups()
        self.assertLess(subset_cost, all_sources._state_cost)
        all_sources.close()
        original = budget.reserve_ram
        used = False

        def cancel_after_reserve(amount):
            """只在本组固定费用已实际登记后取消一次。

            参数: amount本次bytes。返回: 原reserve返回值。
            异常: 首次成功预约后抛KeyboardInterrupt，之后调用原方法。
            """
            nonlocal used
            original(amount)
            if not used:
                used = True
                raise KeyboardInterrupt('subset-fixed-after-reserve')

        # 固定预约取消时尚未开源；只抵销本组已经实际记账的一笔费用。
        with patch.object(budget, 'reserve_ram', side_effect=cancel_after_reserve):
            with self.assertRaises(KeyboardInterrupt):
                history.iter_groups(sources=('table',))
        self.assertEqual(budget.ram_bytes, baseline)
        iterator = history.iter_groups(sources=('table',))
        readers = tuple(iterator.readers)
        limit = budget.memory_budget_bytes
        budget.memory_budget_bytes = budget.ram_bytes
        try:
            with self.assertRaises(BudgetExceededError):
                next(iterator)
        finally:
            budget.memory_budget_bytes = limit
        self.assertTrue(iterator.closed)
        self.assertTrue(all(reader.handle.closed for reader in readers))
        self.assertEqual(budget.ram_bytes, baseline)
        self.assertFalse(history._groups)
        self.assertFalse(history._iterators)
