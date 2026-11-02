"""用真实memory/CSV封存历史验收有限窗口表达式回读。

手算整数纳秒种子、TTL和实际末点，两个数值后端分别执行既有独立核。
测试不把保持值计为真实新样本，不改变调用方原state或重读旧报文。
每例新文件只写work，所有回读、输出和原工厂资源最终关闭并核对RAM0。
资源故障在新owner/本步/交付/关闭注入，前一个已交付帧不能被后续故障撤销。
"""

# 使用原真实工厂，模块别名避免重复收集其他专项。
from dataclasses import replace
import unittest
from unittest.mock import patch
import test_stream_boundaries as real_history
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.expression import compile_expression
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import SignalDType
from chronaxis.execution import window_replay as module
from chronaxis.execution.window_replay import HistoricalWindowReplay
from chronaxis.results.errors import BudgetExceededError, ResultClosedError, ResultFormatError
from chronaxis.timebase.conversion import INT64_MIN, INT64_MAX


class WindowReplayTests(unittest.TestCase):
    """每例真实封存新历史，回读者自有资源与借用工厂分开关闭。"""

    def fixture(self, **kwargs):
        """建立真实历史和原数值绑定。

        参数: kwargs传给原工厂，texts默认数值a。返回: 原fixture。
        异常: 构造、真实读取或最终RAM0断言失败。
        """
        factory = real_history.StreamBoundaryTests('runTest')
        factory.setUp()
        kwargs.setdefault('texts', ('a',))
        fixture = factory.prepare(**kwargs)
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        return fixture

    def cleanup_fixture(self, factory, budget):
        """关闭原调用方资源并核对账本。

        参数: factory/budget为原工厂及共享账本。返回: None。异常: 漏账断言失败。
        """
        self.assertTrue(factory.doCleanups())
        self.assertEqual(budget.ram_bytes, 0)

    def replay(self, fixture, start=0, end=8, backend='numpy', **kwargs):
        """建立独立回读者并登记关闭。

        参数: fixture原资源；start/end整数ns；backend独立数值后端；kwargs可覆盖原上下文。
        返回: HistoricalWindowReplay。异常: 原构造错误传播。
        """
        owner = HistoricalWindowReplay(fixture.history, kwargs.get('context', fixture.holds._context),
            kwargs.get('bindings', fixture.lease.bindings), kwargs.get('compiled', fixture.compiled[0]),
            Interval(start, end), backend=backend)
        self.addCleanup(owner.close)
        return owner

    def scalar(self, result, backend):
        """按真实后端取值，不以NumPy结果生成参考预期。

        参数: result为ExpressionResult；backend为查询后端。
        返回: (有效值或None, valid, actual_update)；invalid不补0。
        异常: 真实类型或关闭错误传播。
        """
        if backend == 'reference':
            value = result.rows[0].value
            return (value.value if value.valid else None, value.valid, bool(result.actual_update[0]))
        value = result.arrays.value
        valid = bool(value.valid[0])
        return (value.values[0].item() if valid else None, valid, bool(result.actual_update[0]))

    def summaries(self, owner, backend):
        """即时关闭每帧，只有合成小测试保存简单手算摘要。

        参数: owner为回读者；backend为原后端。返回: 简单tuple列表。
        异常: 真实执行、关闭或断言错误传播。
        """
        rows = []
        for frame in owner:
            try:
                point = self.scalar(frame.point_result, backend)
                continuous = None if frame.continuous_result is None else self.scalar(frame.continuous_result, backend)
                rows.append((frame.time_ns, frame.end_ns, point, continuous))
            finally:
                frame.close()
        return rows

    def cancel_once(self, original, after, target=None):
        """只在首次目标动作前或成功后取消，后续保持真实清理。

        参数: original为原方法；after为时机；target可选金额。
        返回: 故障函数。异常: 唯一KeyboardInterrupt。
        """
        used = False

        def invoke(*args):
            """执行目标动作并取消一次。

            参数: args为原参数。返回: 原结果。异常: 首次目标KeyboardInterrupt。
            """
            nonlocal used
            if not used and (target is None or args[0] == target):
                used = True
                if after:
                    original(*args)
                raise KeyboardInterrupt('window-replay-test')
            return original(*args)

        return invoke

    def test_seed_ttl_and_real_update_split_window_with_original_state_unchanged(self):
        """窗口2—7ns由0ns种子到3nsTTL、5ns真实更新，原state保持未提交。

        参数: 无。返回: None。异常: 手算、来源、绑定或借用state变化断言失败。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                with self.subTest(kind=kind, backend=backend):
                    # 显式8ns观测让memory与CSV都有相同来源范围，不能以domain代替CSV EOF。
                    fixture = self.fixture(kind=kind, rows_by_source={'table': (
                        MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1),
                        MemoryRow(8, {'raw.a': 2}, 2))})
                    self.assertEqual(fixture.history.source_completions['table'].observed_end_ns, 8)
                    baseline, revision = fixture.budget.ram_bytes, fixture.state.revision
                    owner = self.replay(fixture, 2, 7, backend)
                    first = next(owner)
                    self.assertEqual((first.time_ns, first.end_ns), (2, 3))
                    self.assertEqual(self.scalar(first.point_result, backend), (1.0, True, False))
                    self.assertEqual(self.scalar(first.continuous_result, backend), (1.0, True, False))
                    self.assertEqual(first.point_result.binding_identity, fixture.lease.bindings.identity)
                    self.assertEqual(first.point_result.samples[0].time_ns, 0)
                    self.assertEqual(first.point_result.samples[0].source_ref.field, 'raw.a')
                    first.close()
                    rows = self.summaries(owner, backend)
                    self.assertEqual(rows, [(3, 5, (None, False, False), (None, False, False)),
                                            (5, 7, (2.0, True, True), (2.0, True, True)),
                                            (7, 7, (2.0, True, False), None)])
                    self.assertEqual(fixture.state.revision, revision)
                    self.assertIsNone(fixture.state.last_time_ns)
                    owner.close()
                    self.assertEqual(fixture.budget.ram_bytes, baseline)
                    self.assertFalse(fixture.history.closed)
                    self.assertFalse(fixture.lease.closed)

    def test_actual_csv_eof_excludes_continuous_but_preserves_real_last_point(self):
        """CSV实际EOF为5ns，5ns点仍是2，5—7ns连续和7ns点必须UNKNOWN。

        参数: 无。返回: None。异常: 把domain误作来源观测范围断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(kind='csv')
            self.assertEqual(fixture.history.source_completions['table'].observed_end_ns, 5)
            owner = self.replay(fixture, 2, 7, backend)
            self.assertEqual(self.summaries(owner, backend),
                [(2, 3, (1.0, True, False), (1.0, True, False)),
                 (3, 5, (None, False, False), (None, False, False)),
                 (5, 7, (2.0, True, True), (None, False, True)), (7, 7, (None, False, False), None)])

    def test_actual_window_terminal_point_and_zero_area_are_preserved(self):
        """真实8ns末点保留9，0—8面积仍用1；零宽窗口只返回真实点。

        参数: 无。返回: None。异常: 半开面积或真实末点丢失断言失败。
        """
        for backend in ('reference', 'numpy'):
            factory = real_history.StreamBoundaryTests('runTest')
            factory.setUp()
            definition = replace(factory.a, valid_for_ns=20)
            fixture = self.fixture(definitions=(definition,), rows_by_source={
                'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(8, {'raw.a': 9}, 1))})
            owner = self.replay(fixture, 0, 8, backend)
            self.assertEqual(self.summaries(owner, backend),
                [(0, 8, (1.0, True, True), (1.0, True, True)), (8, 8, (9.0, True, True), None)])
            owner.close()
            point = self.replay(fixture, 8, 8, backend)
            self.assertEqual(self.summaries(point, backend), [(8, 8, (9.0, True, True), None)])

    def test_empty_invalid_and_constant_history_do_not_manufacture_samples(self):
        """空来源未知，常量有效却没有actual_update，无效更新不补零。

        参数: 无。返回: None。异常: 伪样本或UNKNOWN被改成零断言失败。
        """
        for backend in ('reference', 'numpy'):
            empty = self.fixture(rows_by_source={'table': ()})
            owner = self.replay(empty, 0, 8, backend)
            self.assertEqual(self.summaries(owner, backend),
                [(0, 8, (None, False, False), (None, False, False)), (8, 8, (None, False, False), None)])
            owner.close()
            constant = self.fixture(rows_by_source={'table': ()}, texts=('2.0',))
            owner = self.replay(constant, 2, 7, backend)
            self.assertEqual(self.summaries(owner, backend),
                [(2, 7, (2.0, True, False), (2.0, True, False)), (7, 7, (2.0, True, False), None)])
            owner.close()
            invalid = self.fixture(rows_by_source={'table': (MemoryRow(0, {'raw.a': None}, 0),
                                                            MemoryRow(5, {'raw.a': 2}, 1))})
            owner = self.replay(invalid, 0, 7, backend)
            rows = self.summaries(owner, backend)
            self.assertTrue(all(row[2][0] is None and not row[2][1] for row in rows if row[0] < 5))
            self.assertEqual(rows[-2], (5, 7, (2.0, True, True), (2.0, True, True)))

    def test_multisource_and_int64_extremes_use_complete_groups_and_exact_ns(self):
        """两来源交错TTL与更新不拆同刻，int64边端没有start-1或浮点损失。

        参数: 无。返回: None。异常: 手算联合值或精确纳秒断言失败。
        """
        for backend in ('reference', 'numpy'):
            factory = real_history.StreamBoundaryTests('runTest')
            factory.setUp()
            other = SignalDefinition('b', 'other', 'raw.b', SignalDType.FLOAT64, '1', 20)
            fixture = self.fixture(definitions=(factory.a, other), rows_by_source={
                'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1)),
                'other': (MemoryRow(0, {'raw.b': 10}, 0), MemoryRow(4, {'raw.b': 20}, 1))}, texts=('a + b',))
            owner = self.replay(fixture, 2, 7, backend)
            self.assertEqual(self.summaries(owner, backend),
                [(2, 3, (11.0, True, False), (11.0, True, False)),
                 (3, 4, (None, False, False), (None, False, False)),
                 (4, 5, (None, False, True), (None, False, True)),
                 (5, 7, (22.0, True, True), (22.0, True, True)), (7, 7, (22.0, True, False), None)])
            owner.close()
            for start, end in ((INT64_MIN, INT64_MIN + 6), (INT64_MAX - 6, INT64_MAX)):
                fixture = self.fixture(domain=(start, end), rows_by_source={
                    'table': (MemoryRow(start, {'raw.a': 1}, 0), MemoryRow(end, {'raw.a': 3}, 1))})
                owner = self.replay(fixture, start + 1, end, backend)
                rows = self.summaries(owner, backend)
                self.assertEqual(tuple((row[0], row[1]) for row in rows),
                                 ((start + 1, start + 3), (start + 3, end), (end, end)))
                self.assertEqual(rows[-1][2], (3.0, True, True))

    def test_wrong_domain_context_or_history_rejected_without_new_owner_resources(self):
        """域外、错误后端、不同实际历史与改变原domain均拒绝且还原本次预算。

        参数: 无。返回: None。异常: 身份借用或新资源遗留断言失败。
        """
        fixture = self.fixture()
        other = self.fixture(rows_by_source={'table': (MemoryRow(0, {'raw.a': 99}, 0),
                                                     MemoryRow(5, {'raw.a': 100}, 1))})
        baseline = fixture.budget.ram_bytes
        for start, end, backend, kwargs in ((-1, 8, 'numpy', {}), (0, 9, 'numpy', {}),
                (0, 8, 'bad', {}), (0, 8, 'numpy', {'bindings': other.lease.bindings}),
                (0, 8, 'numpy', {'context': replace(fixture.holds._context, domain=Interval(0, 9))})):
            with self.subTest(start=start, end=end, backend=backend, keys=tuple(kwargs)):
                with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('身份拒绝前打开历史')) as opened:
                    with self.assertRaises(ValueError):
                        self.replay(fixture, start, end, backend, **kwargs)
                    opened.assert_not_called()
                self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_retained_frame_keeps_old_samples_and_owner_closes_only_own_resources(self):
        """保留旧帧到5ns更新以后仍读1，回读close不关闭调用方原历史或状态。

        参数: 无。返回: None。异常: 输出随state改变、漏账或越权关闭断言失败。
        """
        fixture = self.fixture()
        baseline = fixture.budget.ram_bytes
        owner = self.replay(fixture)
        first = next(owner)
        later = tuple(owner)
        self.assertEqual(self.scalar(first.point_result, 'numpy'), (1.0, True, True))
        self.assertEqual(first.point_result.samples[0].time_ns, 0)
        self.assertEqual(fixture.state.revision, 0)
        owner.close()
        owner.close()
        self.assertTrue(first.closed and all(frame.closed for frame in later))
        self.assertEqual(fixture.budget.ram_bytes, baseline)
        for read in (lambda: first.point_result, lambda: first.time_ns, lambda: next(owner)):
            with self.assertRaises(ResultClosedError):
                read()
        self.assertFalse(fixture.history.closed)
        self.assertFalse(fixture.state.closed)
        self.assertFalse(fixture.lease.closed)

    def test_constructor_and_first_step_reserve_cancel_never_read_history(self):
        """固定及首步申请前后取消，历史未读取且本次workspace完全回收。

        参数: 无。返回: None。异常: 预算/FD漏账或取消后继续推进断言失败。
        """
        for after in (False, True):
            fixture = self.fixture()
            baseline, budget = fixture.budget.ram_bytes, fixture.budget
            with patch.object(budget, 'reserve_ram', side_effect=self.cancel_once(budget.reserve_ram, after)):
                with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('预算前读历史')) as opened:
                    with self.assertRaises(KeyboardInterrupt):
                        self.replay(fixture)
                    opened.assert_not_called()
            self.assertEqual(budget.ram_bytes, baseline)
            owner = self.replay(fixture)
            owner_baseline = budget.ram_bytes
            with patch.object(budget, 'reserve_ram', side_effect=self.cancel_once(budget.reserve_ram, after)):
                with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('首步预算前读历史')) as opened:
                    with self.assertRaises(KeyboardInterrupt):
                        next(owner)
                    opened.assert_not_called()
            self.assertEqual(budget.ram_bytes, owner_baseline)
            self.assertTrue(owner.failed)
            with self.assertRaises(ResultClosedError):
                next(owner)
            owner.close()
            self.assertEqual(budget.ram_bytes, baseline)

    def test_later_budget_or_partial_delivery_failure_keeps_previous_frame(self):
        """后步预算不足或交付前后取消，只回收当前结果，保留上一帧及金额。

        参数: 无。返回: None。异常: 前帧被撤销或失败workspace遗留断言失败。
        """
        for stage in ('budget', 'frame', 'install_before', 'install_after'):
            fixture = self.fixture()
            baseline, budget = fixture.budget.ram_bytes, fixture.budget
            owner = self.replay(fixture)
            first = next(owner)
            before = budget.ram_bytes
            if stage == 'budget':
                failure = patch.object(budget, 'reserve_ram', side_effect=BudgetExceededError('本步不足'))
                error = BudgetExceededError
            elif stage == 'frame':
                failure = patch.object(module, 'WindowReplayFrame', side_effect=MemoryError('window-frame-constructor'))
                error = MemoryError
            else:
                failure = patch.object(owner._results, 'add', side_effect=self.cancel_once(
                    owner._results.add, stage == 'install_after'))
                error = KeyboardInterrupt
            with failure:
                with self.assertRaises(error):
                    next(owner)
            self.assertTrue(owner.failed)
            self.assertEqual(budget.ram_bytes, before)
            self.assertEqual(self.scalar(first.point_result, 'numpy'), (1.0, True, True))
            self.assertEqual(len(owner._results), 1)
            owner.close()
            self.assertEqual(budget.ram_bytes, baseline)

    def test_frame_and_owner_release_cancel_follow_actual_ledger(self):
        """帧或owner固定扣账前可重试，扣账后取消不产生重复释放。

        参数: 无。返回: None。异常: 关闭金额/登记交接错误断言失败。
        """
        for stage in ('frame', 'owner'):
            for after in (False, True):
                fixture = self.fixture()
                baseline, budget = fixture.budget.ram_bytes, fixture.budget
                owner = self.replay(fixture)
                frame = next(owner)
                target = frame if stage == 'frame' else owner
                cost = frame._cost if stage == 'frame' else owner._fixed_cost
                with patch.object(budget, 'release_ram', side_effect=self.cancel_once(budget.release_ram, after, cost)):
                    with self.assertRaises(KeyboardInterrupt):
                        target.close()
                self.assertEqual(target.closed, after)
                target.close()
                target.close()
                owner.close()
                self.assertEqual(budget.ram_bytes, baseline)

    def test_child_constructor_failures_release_only_new_resources(self):
        """独立查询层构造失败，原工厂状态和预算均保持，历史尚未读取。

        参数: 无。返回: None。异常: 新构造遗留成本或越权关闭断言失败。
        """
        fixture = self.fixture()
        baseline = fixture.budget.ram_bytes
        for name in ('HoldQueries', 'ExpressionQueries', 'BoundaryQueries'):
            with self.subTest(child=name):
                with patch.object(module, name, side_effect=MemoryError('window-child-constructor')):
                    with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('构造失败前读历史')) as opened:
                        with self.assertRaises(MemoryError):
                            self.replay(fixture)
                        opened.assert_not_called()
                self.assertEqual(fixture.budget.ram_bytes, baseline)
                self.assertFalse(fixture.state.closed)
                self.assertFalse(fixture.history.closed)

    def test_query_or_history_failure_keeps_prior_frame_and_can_close(self):
        """真实推进读/查询故障禁止重试，先前输出不随已提交新状态变化。

        参数: 无。返回: None。异常: 前输出被撤销、故障后推进或资源漏账断言失败。
        """
        for stage in ('query', 'read'):
            fixture = self.fixture()
            baseline = fixture.budget.ram_bytes
            owner = self.replay(fixture)
            first = next(owner)
            if stage == 'query':
                failure = patch.object(owner, '_query', side_effect=MemoryError('window-expression-failure'))
                error = MemoryError
            else:
                # 先消费3ns的TTL帧，5ns提交以后再让真实前瞻推进失败。
                next(owner).close()
                failure = patch.object(type(owner._groups), '__next__', side_effect=ResultFormatError('window-read-failure'))
                error = ResultFormatError
            with failure:
                with self.assertRaises(error):
                    next(owner)
            self.assertTrue(owner.failed)
            self.assertEqual(self.scalar(first.point_result, 'numpy'), (1.0, True, True))
            with self.assertRaises(ResultClosedError):
                next(owner)
            owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_unsigned_large_values_and_bool_truth_keep_original_types(self):
        """窗口回读不把大uint转浮点，也不把BOOL的未知掩码解释为False。

        参数: 无。返回: None。异常: 精度、dtype或三值语义变化断言失败。
        """
        definition = SignalDefinition('a', 'table', 'raw.a', SignalDType.UINT64, '1', 20)
        large = 2 ** 63 + 1
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(definitions=(definition,), rows_by_source={'table': (
                MemoryRow(0, {'raw.a': large}, 0), MemoryRow(5, {'raw.a': large + 2}, 1))})
            owner = self.replay(fixture, 2, 7, backend)
            rows = self.summaries(owner, backend)
            self.assertEqual(rows, [(2, 5, (large, True, False), (large, True, False)),
                                    (5, 7, (large + 2, True, True), (large + 2, True, True)),
                                    (7, 7, (large + 2, True, False), None)])
            self.assertTrue(all(type(row[2][0]) is int for row in rows))
            owner.close()
            fixture = self.fixture(texts=('a > 0',))
            owner = self.replay(fixture, 2, 7, backend)
            self.assertEqual(self.summaries(owner, backend),
                [(2, 3, (True, True, False), (True, True, False)),
                 (3, 5, (None, False, False), (None, False, False)),
                 (5, 7, (True, True, True), (True, True, True)), (7, 7, (True, True, False), None)])

    def test_same_history_hash_cannot_replace_actual_eof_or_final_progress(self):
        """相同封存SHA不能允许另造EOF终点或最终批计数，入口应在读历史前拒绝。

        参数: 无。返回: None。异常: 实际完成事实被替换或本次成本未回收断言失败。
        """
        for stage in ('end', 'progress'):
            with self.subTest(stage=stage):
                fixture = self.fixture(kind='csv')
                baseline = fixture.budget.ram_bytes
                bindings = fixture.lease.bindings
                completion = fixture.holds._context.completions[0]
                if stage == 'end':
                    # CSV真实EOF5ns，SHA/描述/请求/总计数不变，只把两处宣称终点替换为7ns。
                    bindings = replace(bindings, sources=(replace(bindings.sources[0], observation_end_ns=7),))
                    completion = replace(completion, observed_end_ns=7)
                else:
                    completion = replace(completion, sample_count=completion.sample_count + 1)
                context = replace(fixture.holds._context, completions=(completion,))
                compiled = compile_expression('a', bindings)
                with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('完成事实拒绝前读取')) as opened:
                    with self.assertRaises(ValueError):
                        self.replay(fixture, 2, 7, context=context, bindings=bindings, compiled=compiled)
                    opened.assert_not_called()
                self.assertEqual(fixture.budget.ram_bytes, baseline)
