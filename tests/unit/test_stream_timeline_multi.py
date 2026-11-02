"""用真实来源检验多规则共享一次提交与预算输出。

不同条件先捕获旧点，共享编译对象只占一个槽，规则Detector仍独立。
真实memory/CSV与手算边界分别验证，故障只注入明确生命周期动作，不改生产成本。
所有work工厂必须清理成功/账本归零，导入模块别名不重复发现原TestCase。
"""

# 多规则关联接已经封存的真实来源工厂，不继承其用例。
import unittest
from unittest.mock import patch
from dataclasses import replace
import numpy as np
import test_stream_condition_evidence as factories
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow
from chronaxis.core.temporal import TemporalRule
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, Truth as T
from chronaxis.execution.timeline_multi import MultiRuleTimeline, TimelineRule
from chronaxis.results.errors import AnalysisError, BudgetExceededError, ResultClosedError


class MultiTimelineTests(unittest.TestCase):
    """每项独立实际上游，明确验证所有权和共享原子组。"""

    def fixture(self, *, backend='numpy', **kwargs):
        """建立真实条件owner并登记层级清理。

        参数: backend及工厂合成输入。返回: (fixture,evidence)。
        异常: 来源/绑定错误传播，清理错误或漏账断言失败。
        """
        factory = factories.StreamConditionEvidenceTests('runTest')
        fixture, evidence = factory.fixture(backend=backend, **kwargs)
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        return fixture, evidence

    def cleanup_fixture(self, factory, budget):
        """断言关闭与账本。参数: 原工厂/预算。返回: None。异常: AssertionError。"""
        self.assertTrue(factory.doCleanups(), '原真实条件工厂关闭失败')
        self.assertEqual(budget.ram_bytes, 0)

    def timeline(self, fixture, evidence, declarations):
        """从规则/条件序号明确关联并登记新游标。

        参数: 实际fixture/evidence和(rule,index) tuple。
        返回: MultiRuleTimeline。异常: 真实构造错误传播。
        """
        rules = tuple(TimelineRule(rule, fixture.compiled[index]) for rule, index in declarations)
        owner = MultiRuleTimeline(evidence, fixture.boundaries, rules)
        self.addCleanup(owner.close)
        return owner

    def consume(self, fixture, owner):
        """保留真实下一组直到消费，收集小手算夹具事件与时刻。

        参数: 有限fixture/owner。返回: (events tuple,facts tuple)。
        异常: 实际错误传播，超过10000步断言失败，当前步始终close。
        """
        groups = tuple(group for group in fixture.groups if group.time_ns >= owner._start)
        index, events, facts = 0, [], []
        for _ in range(10000):
            result = owner.step(groups[index] if index < len(groups) else None)
            if result is None:
                return tuple(events), tuple(facts)
            try:
                for batch in result.events_by_rule:
                    events.extend(batch)
                facts.append((result.time_ns, result.consumed_group, result.ticks))
                if result.consumed_group:
                    index += 1
            finally:
                result.close()
        self.fail('有限多规则夹具未终止')

    def fields(self, events):
        """提取手算稳定字段。参数: Event tuple。返回: 按规则ID排序tuple。异常: 类型错误。"""
        return tuple(sorted((event.rule.rule_id, event.start_ns, event.confirmed_ns, event.end_ns, event.status)
                            for event in events))

    def test_constructor_install_failure_closes_locally_constructed_detector(self):
        """子Detector已构造但固定槽安装失败时，局部对象也必须被关闭。

        参数: 无。返回: None。异常: 子申请漏账或部分owner关闭失败断言失败。
        """
        import chronaxis.execution.timeline_multi as module
        fixture, evidence = self.fixture()
        rule = TimelineRule(TemporalRule('rule', 'dataset', 'session', 'condition_duration', 3), fixture.compiled[0])
        original, created = module.BudgetedTemporalDetector, []
        baseline = fixture.budget.ram_bytes

        class RejectInstall(list):
            """原有已安装字段保留，只拒绝本次子结果安装。"""

            def append(self, result):
                """旧增长安装失败。参数: 新Detector。返回: 无。异常: MemoryError。"""
                raise MemoryError('multi-detector-install')

            def __setitem__(self, index, result):
                """固定槽安装失败。参数: 槽与新Detector。返回: 无。异常: MemoryError。"""
                raise MemoryError('multi-detector-install')

        class RejectingTimeline(MultiRuleTimeline):
            """字段建立时安装真实故障集合，不在参数求值后更换已绑定的方法接收者。"""

            def __setattr__(self, name, value):
                """拦截检测器登记list。参数: 字段/值。返回: None。异常: 原赋值错误传播。"""
                if name == '_detectors' and isinstance(value, list):
                    value = RejectInstall(value)
                super().__setattr__(name, value)

        owner = RejectingTimeline.__new__(RejectingTimeline)
        self.addCleanup(owner.close)

        def construct_then_reject(*args, **kwargs):
            """实际构造后替换安装位置，不替生产层关闭。

            参数: 原Detector构造参数。返回: 真实Detector。
            异常: 原构造错误传播，安装失败由新owner处理。
            """
            result = original(*args, **kwargs)
            created.append(result)
            return result

        try:
            with patch.object(module, 'BudgetedTemporalDetector', side_effect=construct_then_reject):
                with self.assertRaises(MemoryError):
                    MultiRuleTimeline.__init__(owner, evidence, fixture.boundaries, (rule,))
            self.assertEqual(fixture.budget.ram_bytes, baseline)
            self.assertTrue(all(result.closed for result in created))
        finally:
            # 原失败时只在测试最终收尾关闭已捕获对象，不能掩盖此前正式漏账断言。
            for result in created:
                result.close()

    def test_shared_condition_and_different_conditions_use_one_commit(self):
        """两条件四规则先取得全部旧点，一次提交后各自确认/边沿/无事件。

        参数: 无。返回: None。异常: 重复提交/共享槽重复预备或终点错误断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture, evidence = self.fixture(backend=backend, texts=('a > 0', 'a < 0'), domain=(0, 5),
                bounds={'table': (0, 5)}, rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(3, {'raw.a': 0}, 1))})
            declarations = ((TemporalRule('duration', 'dataset', 'session', 'condition_duration', 3), 0),
                            (TemporalRule('initial', 'dataset', 'session', 'rising_edge', emit_initial=True), 0),
                            (TemporalRule('fall', 'dataset', 'session', 'falling_edge'), 0),
                            (TemporalRule('negative', 'dataset', 'session', 'condition_duration', 1), 1))
            owner = self.timeline(fixture, evidence, declarations)
            first = owner.step(fixture.groups[0])
            self.assertEqual(first.condition_slots, (0, 1))
            self.assertEqual(tuple(tick.state for tick in first.ticks), (T.TRUE, T.FALSE))
            self.assertEqual(fixture.state.revision, 1)
            initial_events = tuple(event for batch in first.events_by_rule for event in batch)
            first.close()
            middle = owner.step(fixture.groups[1])
            self.assertEqual((middle.time_ns, middle.consumed_group, fixture.state.revision), (3, True, 2))
            ended = tuple(event for batch in middle.events_by_rule for event in batch)
            middle.close()
            terminal = owner.step()
            self.assertEqual((terminal.time_ns, fixture.state.revision), (5, 2))
            terminal.close()
            self.assertIsNone(owner.step())
            expected = (('duration', 0, 3, 3, 'closed'), ('fall', 3, 3, None, 'point'), ('initial', 0, 0, None, 'point'))
            self.assertEqual(self.fields(initial_events + ended), expected)

    def test_shared_condition_distinct_deadlines_are_global_exact_boundaries(self):
        """同一条件的2ns/5ns候选各自确认，全局时钟不等报文也不混淆状态。

        参数: 无。返回: None。异常: 丢deadline或规则共享状态断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture, evidence = self.fixture(backend=backend, domain=(0, 8), bounds={'table': (0, 8)},
                definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20),),
                rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0),)})
            owner = self.timeline(fixture, evidence, ((TemporalRule('short', 'dataset', 'session', 'condition_duration', 2), 0),
                                                    (TemporalRule('long', 'dataset', 'session', 'condition_duration', 5), 0)))
            events, facts = self.consume(fixture, owner)
            self.assertEqual(tuple(time for time, _, _ in facts), (0, 2, 5, 8))
            self.assertEqual(self.fields(events), (('long', 0, 5, 8, 'truncated'), ('short', 0, 2, 8, 'truncated')))
            self.assertEqual(fixture.state.revision, 1)

    def test_sources_end_independently_and_decisive_or_stays_true(self):
        """来源早结束只截断自身规则，联合决定性TRUE和晚来源规则继续到6ns。

        参数: 无。返回: None。异常: source_eof原因导致全会话提前结束断言失败。
        """
        a = SignalDefinition('a', 'early', 'raw.a', D.FLOAT64, '1', 20)
        b = SignalDefinition('b', 'late', 'raw.b', D.FLOAT64, '1', 20)
        for backend in ('reference', 'numpy'):
            fixture, evidence = self.fixture(backend=backend, definitions=(a, b), domain=(0, 6),
                texts=('a > 0', 'b > 0', 'a > 0 or b > 0'), bounds={'early': (0, 3), 'late': (0, 6)},
                rows_by_source={'early': (MemoryRow(0, {'raw.a': 1}, 0),), 'late': (MemoryRow(0, {'raw.b': 1}, 0),)})
            declarations = tuple((TemporalRule(name, 'dataset', 'session', 'condition_duration', 2), index)
                                 for index, name in enumerate(('early_rule', 'late_rule', 'joint')))
            owner = self.timeline(fixture, evidence, declarations)
            events, facts = self.consume(fixture, owner)
            self.assertEqual(self.fields(events), (('early_rule', 0, 2, 3, 'truncated'),
                ('joint', 0, 2, 6, 'truncated'), ('late_rule', 0, 2, 6, 'truncated')))
            self.assertEqual(tuple(time for time, _, _ in facts), (0, 2, 3, 6))
            joint = next(event for event in events if event.rule.rule_id == 'joint')
            self.assertEqual(joint.dependency_quality, Q.MISSING)
            self.assertEqual(fixture.state.revision, 1)

    def test_csv_extremes_batch_splits_and_rule_order_do_not_change_events(self):
        """真实CSV/内存、批次1/2/7、规则顺序和整数极值保持各事件身份。

        参数: 无。返回: None。异常: 重复组提交、浮点时间或顺序依赖ID断言失败。
        """
        for start in (-(2 ** 63), 2 ** 53 + 1, 2 ** 63 - 4):
            identities = set()
            definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 3),
                           SignalDefinition('b', 'table', 'raw.b', D.FLOAT64, '1', 3))
            for backend in ('reference', 'numpy'):
                for kind in ('memory', 'csv'):
                    for size in (1, 2, 7):
                        for reverse in (False, True):
                            rows = (MemoryRow(start, {'raw.a': 1, 'raw.b': 0}, 0),
                                    MemoryRow(start + 3, {'raw.a': 0, 'raw.b': 1}, 1))
                            fixture, evidence = self.fixture(backend=backend, kind=kind, size=size,
                                definitions=definitions, texts=('a > 0', 'b > 0'), domain=(start, start + 3),
                                rows_by_source={'table': rows})
                            declarations = ((TemporalRule('duration', 'dataset', 'session', 'condition_duration', 3), 0),
                                            (TemporalRule('rise', 'dataset', 'session', 'rising_edge'), 1))
                            owner = self.timeline(fixture, evidence, declarations[::-1] if reverse else declarations)
                            events, _ = self.consume(fixture, owner)
                            self.assertEqual(self.fields(events), (('duration', start, start + 3, start + 3, 'closed'),
                                                                  ('rise', start + 3, start + 3, None, 'point')))
                            self.assertEqual(fixture.state.revision, 2)
                            identities.add(tuple(sorted(event.event_id for event in events)))
                            if kind == 'csv':
                                self.assertEqual(fixture.state.get('b').source_ref.line_number, 3)
            self.assertEqual(len(identities), 1)

    def test_empty_constant_and_seed_start_keep_shared_state(self):
        """空源常量不造来源EOF，域前种子只提交一次且候选从分析起点开始。

        参数: 无。返回: None。异常: 终点点扩展或seed重复提交断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture, evidence = self.fixture(backend=backend, texts=('True', 'a > 0'), domain=(0, 5),
                                              rows_by_source={'table': ()})
            declarations = ((TemporalRule('constant', 'dataset', 'session', 'condition_duration', 2), 0),
                            (TemporalRule('initial', 'dataset', 'session', 'rising_edge', emit_initial=True), 0),
                            (TemporalRule('empty', 'dataset', 'session', 'condition_duration', 2), 1))
            owner = self.timeline(fixture, evidence, declarations)
            events, facts = self.consume(fixture, owner)
            # 无信号依赖即无实际更新；emit_initial也不能凭空造真实点，duration仍可推进。
            self.assertEqual(self.fields(events), (('constant', 0, 2, 5, 'truncated'),))
            self.assertTrue(all(not ticks[0].actual_update for _, _, ticks in facts))
            self.assertFalse(facts[-1][2][0].observation_end)
            self.assertEqual(fixture.state.revision, 0)
            definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20),
                           SignalDefinition('b', 'table', 'raw.b', D.FLOAT64, '1', 20))
            fixture, evidence = self.fixture(backend=backend, definitions=definitions, texts=('a > 0', 'b < 0'),
                domain=(2, 6), bounds={'table': (0, 6)}, rows_by_source={'table': (
                    MemoryRow(0, {'raw.a': 1, 'raw.b': 0}, 0), MemoryRow(5, {'raw.a': 0, 'raw.b': -1}, 1))})
            fixture.state.apply(fixture.groups[0])
            owner = self.timeline(fixture, evidence, ((TemporalRule('duration', 'dataset', 'session', 'condition_duration', 3), 0),
                                                    (TemporalRule('rise', 'dataset', 'session', 'rising_edge'), 1)))
            events, facts = self.consume(fixture, owner)
            self.assertEqual(self.fields(events), (('duration', 2, 5, 5, 'closed'), ('rise', 5, 5, None, 'point')))
            self.assertEqual((facts[0][0:2], fixture.state.revision), ((2, False), 2))

    def test_invalid_rule_scope_and_group_type_are_preflight_errors(self):
        """空/重复/跨dataset/非BOOL配置及非原生组时间均拒绝，不改变账本或状态。

        参数: 无。返回: None。异常: 协议错位接受或拒绝后漏账断言失败。
        """
        fixture, evidence = self.fixture(texts=('a > 0', 'a'))
        good = TimelineRule(TemporalRule('rule', 'dataset', 'session', 'condition_duration', 3), fixture.compiled[0])
        baseline = fixture.budget.ram_bytes
        with self.assertRaises(TypeError):
            MultiRuleTimeline(evidence, fixture.boundaries, ())
        with self.assertRaises(TypeError):
            TimelineRule(good.rule, fixture.compiled[1])
        for rules in ((good, good), (good, TimelineRule(TemporalRule('other', 'other_dataset', 'session', 'condition_duration'), fixture.compiled[0]))):
            with self.assertRaises(ValueError):
                MultiRuleTimeline(evidence, fixture.boundaries, rules)
            self.assertEqual(fixture.budget.ram_bytes, baseline)
        owner = MultiRuleTimeline(evidence, fixture.boundaries, (good,))
        self.addCleanup(owner.close)
        with self.assertRaises(TypeError):
            owner.step(0)
        with self.assertRaises(TypeError):
            owner.step(replace(fixture.groups[0], time_ns=np.int64(0)))
        self.assertEqual(fixture.state.revision, 0)

    def test_preflight_budget_return_cancel_is_retryable(self):
        """首workspace不足/返回取消不进入多规则步骤，恢复限额后同一前瞻可继续。

        参数: 无。返回: None。异常: 假推进、漏账或预算拒绝后错误failed断言失败。
        """
        helper = factories.StreamConditionEvidenceTests('runTest')
        for backend in ('reference', 'numpy'):
            fixture, evidence = self.fixture(backend=backend)
            owner = self.timeline(fixture, evidence, ((TemporalRule('one', 'dataset', 'session', 'condition_duration', 3), 0),
                                                    (TemporalRule('two', 'dataset', 'session', 'condition_duration', 5), 0)))
            baseline, limit = fixture.budget.ram_bytes, fixture.budget.memory_budget_bytes
            fixture.budget.memory_budget_bytes = baseline
            try:
                with self.assertRaises(BudgetExceededError):
                    owner.step(fixture.groups[0])
            finally:
                fixture.budget.memory_budget_bytes = limit
            for after in (False, True):
                with patch.object(fixture.budget, 'reserve_ram', side_effect=helper.cancel_operation(fixture.budget.reserve_ram, after)):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.step(fixture.groups[0])
                self.assertEqual(fixture.budget.ram_bytes, baseline)
                self.assertFalse(owner.failed)
                self.assertIsNone(owner.cursor_ns)
                self.assertEqual(fixture.state.revision, 0)
            result = owner.step(fixture.groups[0])
            self.assertTrue(result.consumed_group)
            result.close()

    def test_second_condition_or_rule_failure_never_rolls_back_committed_state(self):
        """中间条件/规则失败整步不交付，不假回滚，之前输出继续独立持有。

        参数: 无。返回: None。异常: 假事务恢复/重试或旧输出失效断言失败。
        """
        for backend in ('reference', 'numpy'):
            for stage in ('condition', 'rule'):
                definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 20),
                               SignalDefinition('b', 'table', 'raw.b', D.FLOAT64, '1', 20))
                fixture, evidence = self.fixture(backend=backend, definitions=definitions, texts=('a > 0', 'b > 0'),
                    rows_by_source={'table': (MemoryRow(0, {'raw.a': 1, 'raw.b': 1}, 0),
                                             MemoryRow(1, {'raw.a': 0, 'raw.b': 0}, 1))})
                owner = self.timeline(fixture, evidence, ((TemporalRule('one', 'dataset', 'session', 'condition_duration', 3), 0),
                                                        (TemporalRule('two', 'dataset', 'session', 'condition_duration', 3), 1)))
                first = owner.step(fixture.groups[0])
                self.addCleanup(first.close)
                if stage == 'condition':
                    original, calls = evidence.prepare, 0

                    def fail_second(*args):
                        """第二条件预备失败。参数: 原参数。返回: 原结果。异常: MemoryError。"""
                        nonlocal calls
                        calls += 1
                        if calls == 2:
                            raise MemoryError('multi-second-condition')
                        return original(*args)

                    context = patch.object(evidence, 'prepare', side_effect=fail_second)
                    revision = 1
                else:
                    context = patch.object(owner._detectors[1], 'push', side_effect=MemoryError('multi-second-rule'))
                    revision = 2
                with context:
                    with self.assertRaises(MemoryError):
                        owner.step(fixture.groups[1])
                self.assertTrue(owner.failed)
                self.assertEqual(fixture.state.revision, revision)
                self.assertEqual(tuple(tick.state for tick in first.ticks), (T.TRUE, T.TRUE))
                with self.assertRaises(AnalysisError):
                    owner.step(fixture.groups[1])

    def test_construct_and_partial_registration_cancel_keep_prior_step(self):
        """构造/部分链安装返回取消只撤销新步，旧输出不丢且预算回到原状态。

        参数: 无。返回: None。异常: 孤儿结果或旧步骤被撤销断言失败。
        """
        for backend in ('reference', 'numpy'):
            for install in (False, True):
                fixture, evidence = self.fixture(backend=backend)
                owner = self.timeline(fixture, evidence, ((TemporalRule('one', 'dataset', 'session', 'condition_duration', 3), 0),
                                                        (TemporalRule('two', 'dataset', 'session', 'condition_duration', 5), 0)))
                first = owner.step(fixture.groups[0])
                self.addCleanup(first.close)
                baseline = fixture.budget.ram_bytes
                target, method = (owner._results, 'add') if install else (owner, '_construct')
                original = getattr(target, method)

                def cancel_delivery(*args):
                    """原构造/安装后取消。参数: 原参数。返回: 无。异常: KeyboardInterrupt。"""
                    original(*args)
                    raise KeyboardInterrupt('multi-step-delivery')

                with patch.object(target, method, side_effect=cancel_delivery):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.step(fixture.groups[1])
                self.assertTrue(owner.failed)
                self.assertEqual(tuple(owner._results), (first,))
                self.assertEqual(first.ticks[0].state, T.TRUE)
                self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_dense_steps_release_children_and_core_events_without_growth(self):
        """256实际组×三规则逐步close后RAM固定，状态只提交一次且无结果累计。

        参数: 无。返回: None。异常: 多规则重复组提交或缓存泄漏断言失败。
        """
        rows = tuple(MemoryRow(time, {'raw.a': time % 2, 'raw.b': (time + 1) % 2}, time) for time in range(256))
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 1000),
                       SignalDefinition('b', 'table', 'raw.b', D.FLOAT64, '1', 1000))
        for backend in ('reference', 'numpy'):
            fixture, evidence = self.fixture(backend=backend, definitions=definitions, texts=('a > 0', 'b > 0'),
                domain=(0, 256), bounds={'table': (0, 256)}, rows_by_source={'table': rows})
            owner = self.timeline(fixture, evidence, ((TemporalRule('one', 'dataset', 'session', 'condition_duration'), 0),
                                                    (TemporalRule('two', 'dataset', 'session', 'condition_duration'), 1),
                                                    (TemporalRule('rise', 'dataset', 'session', 'rising_edge'), 0)))
            baseline = None
            for index, group in enumerate(fixture.groups):
                result = owner.step(group)
                self.assertTrue(result.consumed_group)
                self.assertEqual(fixture.state.revision, index + 1)
                result.close()
                retained = fixture.budget.ram_bytes - fixture.state._snapshot.retained_cost
                baseline = retained if baseline is None else baseline
                self.assertEqual(retained, baseline)
                self.assertFalse(owner._results)
                self.assertFalse(evidence._results)
                for detector in owner._detectors:
                    self.assertFalse(detector._results)
                    self.assertEqual(detector._detector.events, [])
            terminal = owner.step()
            terminal.close()
            self.assertIsNone(owner.step())
            owner.close()
            with self.assertRaises(ResultClosedError):
                owner.step()

    def test_constructor_cancel_and_later_child_failure_release_all_owned_cost(self):
        """固定申请前后取消及第二子构造失败都抵销新owner，借用查询仍打开。

        参数: 无。返回: None。异常: 部分检测器或固定成本漏账断言失败。
        """
        helper = factories.StreamConditionEvidenceTests('runTest')
        for backend in ('reference', 'numpy'):
            fixture, evidence = self.fixture(backend=backend)
            rules = tuple(TimelineRule(TemporalRule(name, 'dataset', 'session', 'condition_duration', 3),
                                      fixture.compiled[0]) for name in ('one', 'two'))
            baseline = fixture.budget.ram_bytes
            for after in (False, True):
                # 只取消首次固定申请，清理动作仍用真实账本。
                fault = helper.cancel_operation(fixture.budget.reserve_ram, after)
                with patch.object(fixture.budget, 'reserve_ram', side_effect=fault):
                    with self.assertRaises(KeyboardInterrupt):
                        MultiRuleTimeline(evidence, fixture.boundaries, rules)
                self.assertEqual(fixture.budget.ram_bytes, baseline)
            from chronaxis.execution import timeline_multi as module
            original, created = module.BudgetedTemporalDetector, []

            def fail_second(*args, **kwargs):
                """首子真实创建，第二子失败。参数: 原参数。返回: 首子。异常: MemoryError。"""
                if created:
                    raise MemoryError('multi-second-constructor')
                child = original(*args, **kwargs)
                created.append(child)
                return child

            with patch.object(module, 'BudgetedTemporalDetector', side_effect=fail_second):
                with self.assertRaises(MemoryError):
                    MultiRuleTimeline(evidence, fixture.boundaries, rules)
            self.assertTrue(created[0].closed)
            self.assertEqual(fixture.budget.ram_bytes, baseline)
            self.assertFalse(evidence.closed)
            self.assertFalse(fixture.boundaries.closed)

    def test_output_and_fixed_owner_release_cancel_can_retry_without_double_debit(self):
        """关闭仅在目标workspace/固定成本前后取消，子结果先真实关闭且重试幂等。

        参数: 无。返回: None。异常: 重复扣账、孤儿输出或误关闭借用层断言失败。
        """
        helper = factories.StreamConditionEvidenceTests('runTest')
        for backend in ('reference', 'numpy'):
            for stage in ('step', 'owner'):
                for after in (False, True):
                    fixture, evidence = self.fixture(backend=backend)
                    baseline = fixture.budget.ram_bytes
                    owner = self.timeline(fixture, evidence,
                        ((TemporalRule('one', 'dataset', 'session', 'condition_duration', 3), 0),
                         (TemporalRule('two', 'dataset', 'session', 'condition_duration', 5), 0)))
                    result = owner.step(fixture.groups[0])
                    current_state_delta = fixture.budget.ram_bytes - fixture.state._snapshot.retained_cost
                    self.assertGreater(current_state_delta, baseline)
                    result_cost, fixed = result._cost, owner._fixed_cost
                    if stage == 'owner':
                        result.close()
                    target, cost = (result, result_cost) if stage == 'step' else (owner, fixed)
                    original = fixture.budget.release_ram
                    cancellation = helper.cancel_operation(original, after)

                    def release_target(amount):
                        """只中断指定成本。参数: bytes。返回: 原结果。异常: 唯一KeyboardInterrupt。"""
                        return cancellation(amount) if amount == cost else original(amount)

                    with patch.object(fixture.budget, 'release_ram', side_effect=release_target):
                        with self.assertRaises(KeyboardInterrupt):
                            target.close()
                    self.assertEqual(target.closed, after)
                    target.close()
                    target.close()
                    if stage == 'step':
                        self.assertFalse(owner._results)
                    owner.close()
                    self.assertFalse(evidence.closed)
                    self.assertFalse(fixture.boundaries.closed)
                    # 当前样本属于借用state，新owner释放不应把它作为自身成本扣掉。
                    original_state_cost = fixture.state._fixed_cost
                    fixture.state.close()
                    self.assertEqual(fixture.budget.ram_bytes, baseline - original_state_cost)

    def test_long_csv_refs_and_rule_metadata_remain_owned_after_upstream_close(self):
        """长Unicode列/合法ASCII规则ID先计账，当前点CSV行与固定绑定位置分别保留。

        参数: 无。返回: None。异常: 元数据缩减、未计账借用或关闭后仍可读断言失败。
        """
        field, rule_id = 'raw.' + '测' * 2000, 'rule_' + 'r' * 4000
        definition = SignalDefinition('a', 'table', field, D.FLOAT64, '1', 3)
        rows = (MemoryRow(0, {field: 1}, 0), MemoryRow(3, {field: 0}, 1))
        for backend in ('reference', 'numpy'):
            fixture, evidence = self.fixture(backend=backend, kind='csv', definitions=(definition,),
                rows_by_source={'table': rows}, domain=(0, 3))
            fixed_refs = (fixture.groups[0].samples[0].source_ref,)
            rule = TemporalRule(rule_id, 'dataset', 'session', 'condition_duration', 3)
            owner = MultiRuleTimeline(evidence, fixture.boundaries,
                                      (TimelineRule(rule, fixture.compiled[0], fixed_refs),))
            self.addCleanup(owner.close)
            self.assertGreater(owner._fixed_cost, 65536 + 8192)
            owner.step(fixture.groups[0]).close()
            result = owner.step(fixture.groups[1])
            refs, ticks, events = result.source_refs, result.ticks, result.events_by_rule
            self.assertEqual(refs[0][0].line_number, 3)
            self.assertEqual(refs[0][0].field, field)
            self.assertEqual(events[0][0].source_refs, fixed_refs)
            self.assertEqual(result.rule_keys, (('dataset', 'session', rule_id),))
            # 已完成步独立持有查询结果，关闭借用表达式/保持/状态不会使旧位置失效。
            fixture.expressions.close()
            fixture.holds.close()
            fixture.state.close()
            self.assertEqual((result.source_refs, result.ticks, result.events_by_rule), (refs, ticks, events))
            result.close()
            owner.close()
            with self.assertRaises(ResultClosedError):
                _ = result.source_refs
