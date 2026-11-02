"""用真实小来源和手算真值验证两段式条件证据查询及预算。

输入经既有memory/CSV、封存历史、真实绑定和完整组状态，输出是一点ConditionTick。
先prepare旧点，再由测试显式提交一次完整组，最后complete；不使用被测输出生成预期。
核对TTL/真实无效/末点/来源结束、提交版本、身份和独立结果生命周期。
所有文件只在work目录；复用工厂不重复发现其测试类，逆序关闭必须成功且RAM归零。
没有生产全时间轴、检测器驱动或旧CAN改动，合成结果不能代替真实日志验收。
"""

# 复用已验真实来源工厂而不继承TestCase，数值真值与故障位置在当前测试明确给出。
from dataclasses import replace
import unittest
from unittest.mock import patch
import numpy as np
import test_stream_boundaries as boundary_fixtures
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow
from chronaxis.core.temporal import ConditionTick
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, Truth as T
from chronaxis.execution.condition_evidence import ConditionEvidenceQueries
from chronaxis.results.errors import AnalysisError, BudgetExceededError, ResultClosedError


class StreamConditionEvidenceTests(unittest.TestCase):
    """每项拥有独立work夹具与预算；复用相同事实对照两个独立后端。"""

    def fixture(self, *, backend='numpy', **kwargs):
        """创建真实绑定/表达式查询及本节点owner，登记层级清理。

        参数: backend独立数值后端；kwargs为既有工厂的明确合成输入。
        返回: (fixture, owner)，state初始为空。
        异常: 实际来源/绑定/预算错误传播，工厂关闭失败明确断言。
        """
        # 原工厂创建成功后立即登记清理，新owner随后创建，关闭顺序先子后父。
        factory = boundary_fixtures.StreamBoundaryTests('runTest')
        factory.setUp()
        fixture = factory.prepare(backend=backend, **kwargs)
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        owner = ConditionEvidenceQueries(fixture.expressions, backend=backend)
        self.addCleanup(owner.close)
        return fixture, owner

    def cleanup_fixture(self, factory, budget):
        """确认复用工厂关闭成功与整个共享账本归零。

        参数: factory原工厂；budget原共享账本。返回: None。
        异常: 内部清理错误或漏账触发当前TestCase断言，不由工厂隐藏。
        """
        self.assertTrue(factory.doCleanups(), '原资源工厂关闭失败')
        self.assertEqual(budget.ram_bytes, 0)

    def submit(self, fixture, owner, group, *, index=0):
        """按明确两段顺序处理一个实际完整组并保留待关闭输出。

        参数: fixture/owner当前层级，group完整组，index登记条件序号。
        返回: 已完成PreparedConditionEvidence。
        异常: 实际提交/求值/预算错误传播，owner仍拥有预备对象以供关闭。
        """
        result = owner.prepare(fixture.compiled[index], group.time_ns)
        self.addCleanup(result.close)
        # 单组只提交一次，不能在条件求值入口偷偷重做提交。
        fixture.state.apply(group)
        result.complete()
        return result

    def cancel_operation(self, original, after):
        """构造只在首次操作前或成功后取消的真实账本替身。

        参数: original原账本方法，after是否执行后取消。返回: 故障函数。
        异常: 唯一KeyboardInterrupt不替生产层清理；后续调用原操作。
        """
        used = False

        def invoke(amount):
            """执行一次账本调用或目标取消。

            参数: amount字节。返回: 原操作返回值。
            异常: 首次KeyboardInterrupt，其他原错误传播。
            """
            nonlocal used
            if not used:
                used = True
                if after:
                    original(amount)
                raise KeyboardInterrupt('condition-budget-boundary')
            return original(amount)

        return invoke

    def test_actual_terminal_false_survives_ttl_before_point(self):
        """真实末点FALSE覆盖旧TTL，连续域仍半开，两个后端输出同一手算证据。

        参数: 无。返回: None。异常: 点/连续/诊断或真实因果错误断言失败。
        """
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                rows = (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(3, {'raw.a': 0}, 1))
                fixture, owner = self.fixture(backend=backend, rows_by_source={'table': rows}, domain=(0, 3))
                first = self.submit(fixture, owner, fixture.groups[0])
                self.assertEqual(first.ticks, (ConditionTick(0, T.TRUE),))
                first.close()
                last = self.submit(fixture, owner, fixture.groups[1])
                # 真实连续查询在终点已MISSING，before STALE诊断不应增加到当前点FALSE。
                expected = ConditionTick(3, T.UNKNOWN, Q.MISSING, True, True, True,
                                         T.FALSE, Q.NONE, False, Q.MISSING)
                self.assertEqual(last.ticks, (expected,))
                self.assertEqual((last.binding_identity, last.compiled_identity),
                                 (fixture.lease.bindings.identity, fixture.compiled[0].identity))
                self.assertEqual(fixture.state.revision, 2)

    def test_timer_terminal_ttl_is_not_an_actual_invalid_update(self):
        """没有真实更新的TTL/EOF并列保留诊断，但actual_unknown为False。

        参数: 无。返回: None。异常: 定时器被伪造为真实结束更新断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture, owner = self.fixture(backend=backend, rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0),)},
                                          domain=(0, 3))
            self.submit(fixture, owner, fixture.groups[0]).close()
            result = owner.prepare(fixture.compiled[0], 3)
            result.complete()
            # 会话末端连续域已退出，仅MISSING；点视图仍诊断TTL，二者并入diagnostic。
            expected = ConditionTick(3, T.UNKNOWN, Q.MISSING, False, True, True,
                                     T.UNKNOWN, Q.STALE, False, Q.STALE | Q.MISSING)
            self.assertEqual(result.ticks, (expected,))
            self.assertEqual(fixture.state.revision, 1)
            result.close()

    def test_side_column_refresh_at_ttl_and_real_invalid_are_distinguished(self):
        """旁列有效刷新不能将并列TTL误算为实际未知，无效新旁列则是实际因果。

        参数: 无。返回: None。异常: 原样本valid和保持valid混淆断言失败。
        """
        a = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 3)
        b = SignalDefinition('b', 'table', 'raw.b', D.FLOAT64, '1', 10)
        for backend in ('reference', 'numpy'):
            for new_b in (1, None):
                fixture, owner = self.fixture(backend=backend, definitions=(a, b), texts=('a > 0 and b >= 0',),
                    rows_by_source={'table': (MemoryRow(0, {'raw.a': 1, 'raw.b': 0}, 0),
                                             MemoryRow(3, {'raw.b': new_b}, 1))}, domain=(0, 6))
                self.submit(fixture, owner, fixture.groups[0]).close()
                result = self.submit(fixture, owner, fixture.groups[1])
                quality = Q.STALE if new_b is not None else Q.STALE | Q.MISSING
                expected = ConditionTick(3, T.UNKNOWN, quality, True, False, False,
                                         T.UNKNOWN, quality, new_b is None, quality)
                self.assertEqual(result.ticks, (expected,))
                result.close()

    def test_new_derived_domain_quality_proves_actual_unknown_without_invalid_sample(self):
        """有效新样本引起除零，新增DOMAIN_ERROR可证明真实更新导致未知。

        参数: 无。返回: None。异常: 仅检查原样本invalid而丢失派生因果断言失败。
        """
        a = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 3)
        b = SignalDefinition('b', 'table', 'raw.b', D.FLOAT64, '1', 10)
        for backend in ('reference', 'numpy'):
            fixture, owner = self.fixture(backend=backend, definitions=(a, b), texts=('a > 0 and b / b > 0',),
                rows_by_source={'table': (MemoryRow(0, {'raw.a': 1, 'raw.b': 1}, 0),
                                         MemoryRow(3, {'raw.b': 0}, 1))}, domain=(0, 6))
            self.submit(fixture, owner, fixture.groups[0]).close()
            result = self.submit(fixture, owner, fixture.groups[1])
            self.assertTrue(fixture.state.get('b').value.valid)
            self.assertTrue(result.ticks[0].actual_unknown)
            self.assertEqual(result.ticks[0].point_quality, Q.STALE | Q.DOMAIN_ERROR)
            result.close()

    def test_early_source_end_does_not_override_decisive_true(self):
        """较早来源结束保留MISSING诊断，另一来源TRUE仍使条件已知TRUE。

        参数: 无。返回: None。异常: 来源EOF强制整条联合规则未知断言失败。
        """
        a = SignalDefinition('a', 'early', 'raw.a', D.FLOAT64, '1', 10)
        b = SignalDefinition('b', 'late', 'raw.b', D.FLOAT64, '1', 10)
        for backend in ('reference', 'numpy'):
            fixture, owner = self.fixture(backend=backend, definitions=(a, b), texts=('a > 0 or b > 0',),
                rows_by_source={'early': (MemoryRow(0, {'raw.a': 0}, 0),),
                                'late': (MemoryRow(0, {'raw.b': 1}, 0),)},
                bounds={'early': (0, 3), 'late': (0, 6)}, domain=(0, 6))
            self.submit(fixture, owner, fixture.groups[0]).close()
            result = owner.prepare(fixture.compiled[0], 3)
            result.complete()
            expected = ConditionTick(3, T.TRUE, Q.NONE, False, True, False, T.TRUE, Q.NONE, False, Q.MISSING)
            self.assertEqual(result.ticks, (expected,))
            result.close()

    def test_multiple_conditions_use_one_atomic_commit_and_constant_needs_no_source_eof(self):
        """所有条件先捕获旧点后共用一次提交，常量终点独立于来源EOF。

        参数: 无。返回: None。异常: 隐藏重复提交或常量结束条件错误断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture, owner = self.fixture(backend=backend, texts=('a > 0', 'a < 0', 'True'), domain=(0, 8))
            results = tuple(owner.prepare(compiled, 0) for compiled in fixture.compiled)
            self.assertEqual(fixture.state.revision, 0)
            fixture.state.apply(fixture.groups[0])
            for result in results:
                result.complete()
            self.assertEqual(tuple(result.ticks[0].state for result in results), (T.TRUE, T.FALSE, T.TRUE))
            self.assertEqual(fixture.state.revision, 1)
            for result in results:
                result.close()
            # 常量没有信号依赖，虽在会话终点，它的observation_end必须为False。
            constant = owner.prepare(fixture.compiled[2], 8)
            constant.complete()
            self.assertEqual(constant.ticks, (ConditionTick(8, T.UNKNOWN, Q.MISSING, False, False, True,
                                                         T.TRUE, Q.NONE),))
            self.assertEqual(constant.source_refs, ())
            constant.close()

    def test_revision_rejects_hidden_intermediate_commit_and_failed_commit_does_not_increment(self):
        """末提交时间相同也不能掩盖中间组，失败快照不会增加提交版本。

        参数: 无。返回: None。异常: 旧点来自错误状态仍被接受或版本非原子断言失败。
        """
        rows = (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(1, {'raw.a': 2}, 1), MemoryRow(3, {'raw.a': 3}, 2))
        for backend in ('reference', 'numpy'):
            fixture, owner = self.fixture(backend=backend, rows_by_source={'table': rows})
            self.submit(fixture, owner, fixture.groups[0]).close()
            result = owner.prepare(fixture.compiled[0], 3)
            fixture.state.apply(fixture.groups[1])
            fixture.state.apply(fixture.groups[2])
            with self.assertRaises(ValueError):
                result.complete()
            self.assertTrue(result.failed)
            with self.assertRaises(AnalysisError):
                result.complete()
            self.assertEqual((fixture.state.revision, fixture.state.get('a').value.value), (3, 3.))
            result.close()
            with self.assertRaises(AttributeError):
                fixture.state.revision = 0
        # 新完整组最终快照分配失败必须保持版本/时间/账本，与旧原子状态验收一致。
        fixture, owner = self.fixture(rows_by_source={'table': rows})
        fixture.state.apply(fixture.groups[0])
        baseline = (fixture.state.revision, fixture.state.last_time_ns, fixture.budget.ram_bytes)
        with patch('chronaxis.execution.state._StateSnapshot', side_effect=MemoryError('revision-final-snapshot')):
            with self.assertRaises(MemoryError):
                fixture.state.apply(fixture.groups[1])
        self.assertEqual((fixture.state.revision, fixture.state.last_time_ns, fixture.budget.ram_bytes), baseline)

    def test_real_csv_and_batch_splits_keep_precise_extreme_time_and_full_refs(self):
        """真实CSV/内存与1/2/7切分在int64边缘保留1ns精度及完整CSV位置。

        参数: 无。返回: None。异常: 浮点时间量化、切分重置或位置丢失断言失败。
        """
        for backend in ('reference', 'numpy'):
            for kind in ('memory', 'csv'):
                for size in (1, 2, 7):
                    for start in (-(2 ** 63), 2 ** 53 + 1, 2 ** 63 - 4):
                        rows = (MemoryRow(start, {'raw.a': 1}, 0), MemoryRow(start + 3, {'raw.a': 0}, 1))
                        fixture, owner = self.fixture(backend=backend, kind=kind, size=size,
                            rows_by_source={'table': rows}, domain=(start, start + 3))
                        self.submit(fixture, owner, fixture.groups[0]).close()
                        last = self.submit(fixture, owner, fixture.groups[1])
                        self.assertEqual((last.time_ns, last.ticks[0].point_state), (start + 3, T.FALSE))
                        self.assertEqual(last.source_refs, (fixture.state.get('a').source_ref,))
                        if kind == 'csv':
                            self.assertEqual(last.source_refs[0].line_number, 3)
                        last.close()

    def test_long_csv_refs_survive_upstream_close_with_own_budget(self):
        """长CSV列位置独立计账，关闭上游后完成结果仍可读到自身关闭。

        参数: 无。返回: None。异常: 来源子类被缩减或预算释放后仍借用上游断言失败。
        """
        field = 'raw.' + '测' * 2000
        definition = SignalDefinition('a', 'table', field, D.FLOAT64, '1', 3)
        rows = (MemoryRow(0, {field: 1}, 0), MemoryRow(3, {field: 0}, 1))
        for backend in ('reference', 'numpy'):
            fixture, owner = self.fixture(backend=backend, kind='csv', definitions=(definition,),
                                          rows_by_source={'table': rows}, domain=(0, 3))
            self.submit(fixture, owner, fixture.groups[0]).close()
            result = self.submit(fixture, owner, fixture.groups[1])
            refs, ticks = result.source_refs, result.ticks
            fixture.expressions.close()
            fixture.holds.close()
            fixture.state.close()
            self.assertEqual(result.source_refs, refs)
            self.assertEqual(result.source_refs[0].field, field)
            self.assertEqual(result.ticks, ticks)
            self.assertGreater(result._cost, 65536 + 1024)
            result.close()
            with self.assertRaises(ResultClosedError):
                _ = result.ticks

    def test_prepare_budget_cancel_and_registration_failure_only_remove_new_result(self):
        """预申请/构造交付/部分安装取消不漏账，不影响先前已完成结果。

        参数: 无。返回: None。异常: 槽或结果登记残留、旧输出失效触发断言。
        """
        for backend in ('reference', 'numpy'):
            fixture, owner = self.fixture(backend=backend)
            first = self.submit(fixture, owner, fixture.groups[0])
            baseline = fixture.budget.ram_bytes
            for after in (False, True):
                fault = self.cancel_operation(fixture.budget.reserve_ram, after)
                with patch.object(fixture.budget, 'reserve_ram', side_effect=fault):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.prepare(fixture.compiled[0], 1)
                self.assertEqual(fixture.budget.ram_bytes, baseline)
            for method_name in ('_construct', 'add'):
                target = owner if method_name == '_construct' else owner._results
                original = getattr(target, method_name)

                def cancel_delivery(*args):
                    """原操作后取消。参数: 原方法参数。返回: 无。异常: KeyboardInterrupt。"""
                    original(*args)
                    raise KeyboardInterrupt('condition-result-delivery')

                with patch.object(target, method_name, side_effect=cancel_delivery):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.prepare(fixture.compiled[0], 1)
                self.assertEqual(fixture.budget.ram_bytes, baseline)
                self.assertEqual(tuple(owner._results), (first,))
                self.assertFalse(first.closed)
                self.assertEqual(first.ticks[0].state, T.TRUE)
            first.close()

    def test_completion_ref_budget_failure_is_failed_without_state_rollback(self):
        """来源位置额外预算不足导致失败，目标提交不回滚且资源仍能关闭。

        参数: 无。返回: None。异常: 静默丢refs、假报完成或失败后重试触发断言。
        """
        for backend in ('reference', 'numpy'):
            fixture, owner = self.fixture(backend=backend)
            result = owner.prepare(fixture.compiled[0], 0)
            fixture.state.apply(fixture.groups[0])
            limit = fixture.budget.memory_budget_bytes
            original = result._charge_refs

            def reject_refs(amount):
                """把限额暂设为已用，执行真实refs申请。

                参数: amount真实refs估算bytes。返回: 原返回值。
                异常: BudgetExceededError来自原账本，不修改生产成本或数据预期。
                """
                fixture.budget.memory_budget_bytes = fixture.budget.ram_bytes
                return original(amount)

            try:
                with patch.object(result, '_charge_refs', side_effect=reject_refs):
                    with self.assertRaises(BudgetExceededError):
                        result.complete()
            finally:
                # 恢复测试注入前的同一限额，生产没有增大配额来绕过失败。
                fixture.budget.memory_budget_bytes = limit
            self.assertTrue(result.failed)
            self.assertFalse(result.completed)
            self.assertEqual(fixture.state.revision, 1)
            with self.assertRaises(AnalysisError):
                result.complete()
            result.close()
            self.assertEqual(len(fixture.expressions._results), 0)

    def test_close_and_constructor_cancel_cover_actual_budget_transition(self):
        """完成结果/固定owner及构造的预算取消区分操作前后，并保持上游可用。

        参数: 无。返回: None。异常: 重复扣账、字段未关闭或构造漏账断言失败。
        """
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                fixture, owner = self.fixture(backend=backend)
                base = fixture.budget.ram_bytes
                fault = self.cancel_operation(fixture.budget.reserve_ram, after)
                with patch.object(fixture.budget, 'reserve_ram', side_effect=fault):
                    with self.assertRaises(KeyboardInterrupt):
                        ConditionEvidenceQueries(fixture.expressions, backend=backend)
                self.assertEqual(fixture.budget.ram_bytes, base)
                result = self.submit(fixture, owner, fixture.groups[0])
                cost, before = result._cost, fixture.budget.ram_bytes
                fault = self.cancel_operation(fixture.budget.release_ram, after)
                with patch.object(fixture.budget, 'release_ram', side_effect=fault):
                    with self.assertRaises(KeyboardInterrupt):
                        result.close()
                self.assertEqual(result.closed, after)
                self.assertEqual(fixture.budget.ram_bytes, before - cost if after else before)
                result.close()
                fixed, before = owner._fixed_cost, fixture.budget.ram_bytes
                fault = self.cancel_operation(fixture.budget.release_ram, after)
                with patch.object(fixture.budget, 'release_ram', side_effect=fault):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.close()
                self.assertEqual(owner.closed, after)
                self.assertEqual(fixture.budget.ram_bytes, before - fixed if after else before)
                owner.close()
                self.assertFalse(fixture.expressions.closed)

    def test_strict_input_slots_and_completed_registry_do_not_keep_peak_capacity(self):
        """协议错位明确拒绝，完成结果链关到一个/零后不保留高峰容量。

        参数: 无。返回: None。异常: 非BOOL/回退/重复预备被接受或资源残留断言失败。
        """
        fixture, owner = self.fixture(texts=('a > 0', 'a'), domain=(0, 600),
            rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0),)},
            definitions=(SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 1000),))
        with self.assertRaises(TypeError):
            owner.prepare(fixture.compiled[1], 0)
        for time in (False, 0., np.int64(0)):
            with self.assertRaises(TypeError):
                owner.prepare(fixture.compiled[0], time)
        pending = owner.prepare(fixture.compiled[0], 0)
        with self.assertRaises(ValueError):
            owner.prepare(fixture.compiled[0], 1)
        fixture.state.apply(fixture.groups[0])
        pending.complete()
        pending.close()
        with self.assertRaises(ValueError):
            owner.prepare(fixture.compiled[0], 0)
        baseline = fixture.budget.ram_bytes
        results = []
        # 实际持有256份已计账完成输出，再关到1/0，未完成表达式槽始终为空。
        for time in range(1, 257):
            result = owner.prepare(fixture.compiled[0], time)
            result.complete()
            results.append(result)
        self.assertEqual(len(owner._results), 256)
        for result in results[:-1]:
            result.close()
            self.assertIsNone(result._registry)
            self.assertIsNone(result._next)
        self.assertEqual(tuple(owner._results), (results[-1],))
        results[-1].close()
        self.assertFalse(owner._results)
        self.assertEqual(fixture.budget.ram_bytes, baseline)
