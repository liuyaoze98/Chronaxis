"""用真实封存历史验收有限数值与BOOL条件的联合回读。

memory/CSV合成原行经既有工厂读取一次，随后只回读新解码历史。
手算4W与TRUE/FALSE/UNKNOWN区间、TTL、同刻更新和EOF；两独立核分别计算。
输出块按半开边界消费，条件单独更新不制造数值样本，原状态和完整来源保持。
故障只注入新owner、登记和账本；保留初始失败证据，持续清理失败须交出恢复句柄。
本文件只写新项目work，所有原工厂资源最后分别关闭并检查RAM0。
"""

# 真实工厂用模块别名复用，避免重复发现原测试类；数值真值来自明确手算。
from dataclasses import replace
import unittest
from unittest.mock import patch
import test_window_replay as real_history
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution import historical_conditional_blocks as module
from chronaxis.execution import calculation_blocks as child_module
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


class HistoricalConditionalBlocksTests(unittest.TestCase):
    """联合owner自有两回读和输出，借用历史及原state不由其关闭。"""

    def fixture(self, **kwargs):
        """建立真实同步数值与条件来源并登记原工厂清理。

        参数: kwargs可替换原行、声明、domain、kind或后端。
        返回: 实际fixture。异常: 真实工厂或最终RAM0检查错误传播。
        """
        factory = real_history.WindowReplayTests('runTest')
        end = 4_000_000_000
        kwargs.setdefault('definitions', (
            SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', 10_000_000_000),
            SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 10_000_000_000)))
        kwargs.setdefault('rows_by_source', {
            'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(end, {'raw.a': 999}, 1)),
            'other': tuple(MemoryRow(index * 1_000_000_000, {'raw.b': value}, index)
                           for index, value in enumerate((1, 0, None, 1, 0)))})
        kwargs.setdefault('domain', (0, end))
        kwargs.setdefault('texts', ('a', 'b > 0'))
        fixture = factory.fixture(**kwargs)
        self.addCleanup(self.close_factory, factory)
        return fixture

    def close_factory(self, factory):
        """执行原真实清理及RAM0断言。参数: 原工厂。返回: None。异常: 清理断言失败。"""
        self.assertTrue(factory.doCleanups())

    def owner(self, fixture, spec=None, **kwargs):
        """构造联合回读并及时登记自己的关闭入口。

        参数: fixture实际输入；spec默认积分全4秒；kwargs可覆盖真实构造配置。
        返回: HistoricalConditionalBlocks。异常: 原构造错误或注入故障传播。
        """
        spec = CalculationDefinition('area', 'integral', fixture.domain) if spec is None else spec
        owner = module.HistoricalConditionalBlocks(fixture.history,
            kwargs.pop('context', fixture.holds._context), kwargs.pop('bindings', fixture.lease.bindings),
            kwargs.pop('compiled', fixture.compiled[0]), spec, kwargs.pop('condition', fixture.compiled[1]), **kwargs)
        self.addCleanup(owner.close)
        return owner

    def summarize(self, owner, spec, backend):
        """即时独立计算并关闭有限块，仅测试保存小型手算摘要。

        参数: owner/原spec/后端。返回: (有限series,CalculationResult)列表。
        异常: 原数值或关闭错误传播；生产预算不依据本测试的摘要留存。
        """
        compute = compute_reference if backend == 'reference' else compute_numpy
        result = []
        for block in owner:
            try:
                result.append((block.series, compute(block.series, spec)))
            finally:
                block.close()
        return result

    def test_real_sources_both_backends_and_all_splits_hand_truth(self):
        """4W×T/F/U/T各1秒为8J、条件覆盖3/4、真实值样本1。

        参数: 无。返回: None。异常: 来源/后端/读取与输出切分改变手算结果。
        """
        end = 4_000_000_000
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        fixture = self.fixture(kind=kind, backend=backend, size=size)
                        baseline = fixture.budget.ram_bytes
                        spec = CalculationDefinition('area', 'integral', fixture.domain)
                        # 封存后两个原adapter的读取入口均禁用，联合owner只能回读新历史。
                        with patch.object(BudgetedMemorySourceAdapter, 'iter_batches', side_effect=AssertionError('memory-rescan')) as memory_scan:
                            with patch.object(BudgetedSignalCSVSourceAdapter, 'iter_batches', side_effect=AssertionError('csv-rescan')) as csv_scan:
                                owner = self.owner(fixture, spec, backend=backend, batch_intervals=size)
                                result = self.summarize(owner, spec, backend)
                                memory_scan.assert_not_called()
                                csv_scan.assert_not_called()
                        self.assertEqual(sum(value.value for _, value in result if value.value is not None), 8.)
                        self.assertEqual(sum(value.condition_known_duration_ns for _, value in result) / end, .75)
                        self.assertEqual(sum(value.value_valid_duration_ns for _, value in result), end)
                        self.assertEqual(sum(value.selected_duration_ns for _, value in result), 2_000_000_000)
                        self.assertEqual(sum(value.valid_sample_count for _, value in result), 1)
                        self.assertEqual(tuple(item for _, value in result for item in value.condition_unknown_ranges), (Interval(2_000_000_000, 3_000_000_000),))
                        self.assertEqual(result[0][0].times_ns[0], 0)
                        self.assertEqual(result[-1][0].times_ns[-1], end)
                        for index, (series, _) in enumerate(result):
                            self.assertLessEqual(len(series.times_ns), size + 1)
                            if index:
                                self.assertEqual(result[index - 1][0].times_ns[-1], series.times_ns[0])
                            self.assertEqual(series.binding_identity, fixture.compiled[0].identity)
                            self.assertEqual({ref.field for ref in series.source_refs}, {'raw.a', 'raw.b'})
                            if kind == 'csv':
                                self.assertTrue(all(type(ref) is CSVSourceRef for ref in series.source_refs))
                                self.assertTrue(all(ref.path and ref.line_number > 0 for ref in series.source_refs))
                        if kind == 'csv':
                            # 完整原单元格和定位不能只由字段名字重新构造，缺失条件也须有原证据。
                            refs = tuple(ref for series, _ in result for ref in series.source_refs)
                            self.assertTrue(any(ref.field == 'raw.a' and ref.time_text == '0'
                                                and ref.value_text == '4' and ref.line_number == 2 for ref in refs))
                            self.assertTrue(any(ref.field == 'raw.b' and ref.time_text == '2000000000'
                                                and ref.value_text == '' and ref.line_number == 4 for ref in refs))
                            self.assertTrue(all(ref.time_quantized is False for ref in refs))
                        owner.close()
                        self.assertFalse(fixture.history.closed)
                        self.assertEqual((fixture.state.revision, fixture.budget.ram_bytes), (0, baseline))

    def test_condition_ttl_and_atomic_simultaneous_value_update(self):
        """条件TTL到期为UNKNOWN，2秒同刻新样本覆盖TTL且数值8W只更新一次。

        参数: 无。返回: None。异常: 条件到期伪FALSE、同刻重复或假样本。
        """
        end = 4_000_000_000
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', end + 1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 1_000_000_000))
        rows = {'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(2_000_000_000, {'raw.a': 8}, 1), MemoryRow(end, {'raw.a': 99}, 2)),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(2_000_000_000, {'raw.b': 1}, 1), MemoryRow(end, {'raw.b': 0}, 2))}
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                fixture = self.fixture(kind=kind, backend=backend, definitions=definitions, rows_by_source=rows)
                spec = CalculationDefinition('area', 'integral', fixture.domain)
                result = self.summarize(self.owner(fixture, spec, backend=backend, batch_intervals=1), spec, backend)
                self.assertEqual(sum(value.value for _, value in result if value.value is not None), 12.)
                self.assertEqual(sum(value.condition_known_duration_ns for _, value in result), 2_000_000_000)
                self.assertEqual(sum(value.valid_sample_count for _, value in result), 2)
                self.assertEqual(tuple(interval for _, value in result for interval in value.condition_unknown_ranges),
                                 (Interval(1_000_000_000, 2_000_000_000), Interval(3_000_000_000, end)))

    def test_source_eof_point_and_no_intersection(self):
        """条件来源2秒EOF不延长，4秒点保留实际更新，无交集不读取历史。

        参数: 无。返回: None。异常: EOF补FALSE、点造面积或无交集打开历史。
        """
        end = 4_000_000_000
        rows = {'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(end, {'raw.a': 99}, 1)),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(2_000_000_000, {'raw.b': 0}, 1))}
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                fixture = self.fixture(kind=kind, backend=backend, rows_by_source=rows,
                    bounds={'table': (0, end), 'other': (0, 2_000_000_000)})
                spec = CalculationDefinition('area', 'integral', fixture.domain)
                result = self.summarize(self.owner(fixture, spec, backend=backend, batch_intervals=1), spec, backend)
                self.assertEqual(sum(value.value for _, value in result if value.value is not None), 8.)
                self.assertEqual(sum(value.condition_known_duration_ns for _, value in result), 2_000_000_000)
                point = self.owner(fixture, replace(spec, window=Interval(end, end)), backend=backend, batch_intervals=1)
                block = next(point)
                self.assertEqual((block.series.times_ns, block.series.values[0].value), ((end,), 99.))
                self.assertFalse(block.series.conditions[0].valid)
                block.close()
                outside = self.owner(fixture, replace(spec, window=Interval(end + 1, end + 2)), backend=backend, batch_intervals=1)
                with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('no-observation-read')) as opened:
                    self.assertEqual(list(outside), [])
                    opened.assert_not_called()

    def test_other_time_ops_keep_joint_conditions_and_dtype(self):
        """既有时间极值/均值/BOOL时长能接收联合块，样本仍只来自原值更新。

        参数: 无。返回: None。异常: 算子不支持、条件丢失或BOOL数值混淆。
        """
        for backend in ('reference', 'numpy'):
            for operation in ('min_time', 'max_time', 'time_weighted_mean', 'duration'):
                fixture = self.fixture(backend=backend, texts=('a > 0', 'b > 0') if operation == 'duration' else ('a', 'b > 0'))
                spec = CalculationDefinition('value', operation, fixture.domain)
                result = self.summarize(self.owner(fixture, spec, backend=backend, batch_intervals=1), spec, backend)
                usable = [value.value for _, value in result if value.value is not None]
                self.assertEqual(sum(usable) if operation == 'duration' else max(usable), 2. if operation == 'duration' else 4.)
                self.assertEqual(sum(value.valid_sample_count for _, value in result), 1)
                self.assertTrue(all(series.conditions is not None for series, _ in result))

    def test_bad_capability_joint_identity_and_sync_reject_before_read(self):
        """拒绝select输出单位转换、非BOOL、旧绑定及缺同步，不先打开历史。

        参数: 无。返回: None。异常: 错误计划误支持、漏账或过早读取。
        """
        fixture = self.fixture()
        other = self.fixture(rows_by_source={
            'table': (MemoryRow(0, {'raw.a': 7}, 0), MemoryRow(4_000_000_000, {'raw.a': 8}, 1)),
            'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(4_000_000_000, {'raw.b': 1}, 1))})
        baseline = fixture.budget.ram_bytes
        with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('invalid-plan-read')) as opened:
            for operation in ('select',):
                with self.assertRaises((TypeError, ValueError)):
                    self.owner(fixture, CalculationDefinition('bad', operation, fixture.domain, output_unit='kW'))
            with self.assertRaises((TypeError, ValueError)):
                self.owner(fixture, condition=fixture.compiled[0])
            with self.assertRaises((TypeError, ValueError)):
                self.owner(fixture, condition=other.compiled[1])
            # 同一实测binding的联合同步门槛必须被调用；不以两个单源表达式各自可读代替。
            with patch.object(type(fixture.lease.bindings), 'require_synchronized', side_effect=ValueError('joint-sync-missing')):
                with self.assertRaises(ValueError):
                    self.owner(fixture)
            for size in (0, True, 1.5):
                with self.assertRaises((TypeError, ValueError)):
                    self.owner(fixture, batch_intervals=size)
            opened.assert_not_called()
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_constructor_and_first_step_budget_cancellation(self):
        """构造和首步申请前后取消或超预算均能回收自有账本，不读原adapter。

        参数: 无。返回: None。异常: 取消漏账、超预算后推进或借用资源改变。
        """
        helper = real_history.WindowReplayTests('runTest')
        for stage in ('constructor-before', 'constructor-after', 'step-before', 'step-after', 'step-limit'):
            fixture = self.fixture()
            baseline, budget = fixture.budget.ram_bytes, fixture.budget
            owner = None if stage.startswith('constructor') else self.owner(fixture, batch_intervals=1)
            before = budget.ram_bytes
            if stage == 'step-limit':
                budget.memory_budget_bytes = before
                with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('over-budget-read')):
                    with self.assertRaises(BudgetExceededError):
                        next(owner)
            else:
                with patch.object(budget, 'reserve_ram', helper.cancel_once(budget.reserve_ram, stage.endswith('after'))):
                    with self.assertRaises(KeyboardInterrupt):
                        self.owner(fixture, batch_intervals=1) if owner is None else next(owner)
            if owner is not None:
                self.assertTrue(owner.failed)
                with self.assertRaises(ResultClosedError):
                    next(owner)
                owner.close()
            self.assertEqual(budget.ram_bytes, baseline)
            self.assertFalse(fixture.history.closed)

    def test_output_registry_failure_keeps_old_block_and_cleans_new_cost(self):
        """输出登记前后失败不能撤销旧块，未发布申请始终有close入口。

        参数: 无。返回: None。异常: 旧列改写、失败后可推进或关闭漏账。
        """
        for after in (False, True):
            fixture = self.fixture()
            baseline = fixture.budget.ram_bytes
            owner = self.owner(fixture, batch_intervals=1)
            first = next(owner)
            saved = first.series
            original = owner._results.add

            def reject(block):
                """在登记动作前或后注入失败。

                参数: 当前新块。返回: 无。异常: 明确MemoryError，不替生产释放预算。
                """
                if after:
                    original(block)
                raise MemoryError('joint-registry-failure')

            with patch.object(owner._results, 'add', reject):
                with self.assertRaises(MemoryError):
                    next(owner)
            self.assertTrue(owner.failed)
            self.assertIs(first.series, saved)
            self.assertEqual(saved.values[0].value, 4.)
            owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_close_release_cancellation_before_and_after_is_retryable(self):
        """输出或父固定金额释放前后取消均保持真实关闭事实，重试不重复扣账。

        参数: 无。返回: None。异常: 释放后重复、释放前丢句柄或借用资源被关。
        """
        helper = real_history.WindowReplayTests('runTest')
        for target in ('block', 'owner'):
            for after in (False, True):
                fixture = self.fixture()
                baseline = fixture.budget.ram_bytes
                owner = self.owner(fixture, batch_intervals=1)
                block = next(owner)
                object_ = block if target == 'block' else owner
                # 先关子资源以隔离父固定金额；这些资源本就归联合父所有。
                if target == 'owner':
                    block.close()
                    for child in owner._blocks:
                        child.close()
                    cost = owner._fixed_cost
                else:
                    cost = block._cost
                with patch.object(fixture.budget, 'release_ram', helper.cancel_once(fixture.budget.release_ram, after, cost)):
                    with self.assertRaises(KeyboardInterrupt):
                        object_.close()
                self.assertEqual(object_.closed, after)
                object_.close()
                owner.close()
                self.assertEqual(fixture.budget.ram_bytes, baseline)
                self.assertFalse(fixture.history.closed)

    def test_join_failure_keeps_original_error_when_inflight_cleanup_persistently_cancels(self):
        """联合列构造失败且未交付金额持续释放取消，原MemoryError仍保持身份。

        参数: 无。返回: None。异常: 清理取消覆盖原错、failed遗漏或恢复后账本残留。
        """
        fixture = self.fixture()
        baseline = fixture.budget.ram_bytes
        owner = self.owner(fixture, batch_intervals=1)
        # 先真实取得两路当前块，把故障明确放在输出构造及其金额清理，避免打断输入回读。
        owner._load(0)
        owner._load(1)
        original = MemoryError('real-joint-output-construction')
        with patch.object(module, 'join_calculation_series', side_effect=original):
            with patch.object(fixture.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-inflight-release')):
                with self.assertRaises(MemoryError) as raised:
                    next(owner)
        self.assertIs(raised.exception, original)
        self.assertTrue(owner.failed)
        self.assertGreater(owner._inflight_cost, 0)
        self.assertEqual(owner._inflight_cost, owner._step_cost)
        self.assertIsNone(owner._unpublished_block)
        self.assertTrue(any('KeyboardInterrupt' in note for note in original.__notes__))
        with self.assertRaises(ResultClosedError):
            next(owner)
        # 持续故障解除后只用真实父close恢复，不能由测试手工抵销失去归属的金额。
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(fixture.budget.ram_bytes, baseline)
        self.assertFalse(fixture.history.closed)
        self.assertEqual(fixture.state.revision, 0)

    def test_released_output_with_cancelled_unlink_is_recovered_by_parent(self):
        """输出已真实抵销金额但脱链取消，父关闭补齐登记，不无限循环或重复扣账。

        参数: 无。返回: None。异常: 关闭事实错误、悬挂登记无法恢复或借用预算受损。
        """
        fixture = self.fixture()
        baseline = fixture.budget.ram_bytes
        owner = self.owner(fixture, batch_intervals=1)
        block = next(owner)
        cost, before = block._cost, fixture.budget.ram_bytes
        with patch.object(owner._results, 'discard', side_effect=KeyboardInterrupt('after-release-unlink')):
            with self.assertRaises(KeyboardInterrupt):
                block.close()
        # 抵销已完成，finally记录closed，但原链节点仍存在；这不是尚未释放的输出。
        self.assertTrue(block.closed)
        self.assertEqual(block._cost, 0)
        self.assertEqual(fixture.budget.ram_bytes, before - cost)
        self.assertIs(block._registry, owner._results)
        self.assertEqual(len(owner._results), 1)
        block.close()
        self.assertEqual(fixture.budget.ram_bytes, before - cost)
        # 真实父close负责识别closed且仍登记的块并补脱链，随后正常关闭两路资源。
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertIsNone(block._registry)
        self.assertEqual(fixture.budget.ram_bytes, baseline)
        self.assertFalse(fixture.history.closed)

    def test_second_child_constructor_recovery_is_owned_by_parent(self):
        """第二个真实子构造失败且持续释放取消，父接管失败子句柄并保留原异常。

        参数: 无。返回: None。异常: 原异常/恢复owner丢失或最终账本残留。
        """
        fixture = self.fixture()
        baseline, children, parents = fixture.budget.ram_bytes, [], []
        child_cls, parent_cls = child_module.HistoricalCalculationBlocks, module.HistoricalConditionalBlocks
        child_close, parent_close = child_cls.close, parent_cls.close
        original = MemoryError('second-real-child-constructor')
        calls = 0

        def capture_child(owner):
            """保存真实关闭对象供失败测试最终回收。

            参数: 真实子owner。返回: 原关闭结果。异常: 原错误传播，不代替生产清理。
            """
            if all(item is not owner for item in children):
                children.append(owner)
            return child_close(owner)

        def capture_parent(owner):
            """保存正在清理的真实父owner。

            参数: 真实父owner。返回: 原关闭结果。异常: 原错误传播。
            """
            if all(item is not owner for item in parents):
                parents.append(owner)
            return parent_close(owner)

        def construct_child(*args, **kwargs):
            """只在第二子构造的真实回读入口注入失败。

            参数: 原构造参数。返回: 第一子实际owner。异常: 第二子原MemoryError。
            """
            nonlocal calls
            calls += 1
            if calls == 2:
                with patch.object(child_module, 'HistoricalWindowReplay', side_effect=original):
                    return child_cls(*args, **kwargs)
            return child_cls(*args, **kwargs)

        try:
            with patch.object(module, 'HistoricalCalculationBlocks', construct_child), patch.object(child_cls, 'close', capture_child), patch.object(parent_cls, 'close', capture_parent):
                with patch.object(fixture.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-joint-cleanup')):
                    with self.assertRaises(MemoryError) as raised:
                        self.owner(fixture, batch_intervals=1)
            self.assertIs(raised.exception, original)
            recovery = getattr(original, 'conditional_blocks_cleanup_owner', None)
            self.assertIsNotNone(recovery)
            self.assertIs(recovery._blocks[1], original.calculation_blocks_cleanup_owner)
            self.assertFalse(recovery.closed)
            self.assertGreater(fixture.budget.ram_bytes, baseline)
            recovery.close()
            recovery.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)
            self.assertFalse(fixture.history.closed)
        finally:
            # 捕获仅为失败断言后回收，不能作为生产恢复句柄成功的依据。
            for owner in reversed(parents + children):
                owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_long_stream_has_only_two_front_blocks_and_bounded_live_state(self):
        """129ns交错来源逐块关闭，实时账本不随已经交付的块数增长。

        参数: 无。返回: None。异常: 全轴留存、多余前瞻或输出登记不能归零。
        """
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', 2),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 2))
        rows = {'table': tuple(MemoryRow(index, {'raw.a': 4}, index) for index in range(0, 129, 2)),
                'other': tuple(MemoryRow(index, {'raw.b': 1}, index) for index in range(129))}
        fixture = self.fixture(definitions=definitions, rows_by_source=rows, domain=(0, 128))
        baseline = fixture.budget.ram_bytes
        owner = self.owner(fixture, batch_intervals=1)
        steady, count = None, 0
        for block in owner:
            self.assertEqual(len(block.series.times_ns), 2)
            self.assertEqual(len(owner._results), 1)
            self.assertLessEqual(sum(current is not None for current in owner._current), 2)
            block.close()
            self.assertEqual(len(owner._results), 0)
            if count > 3:
                live = fixture.budget.ram_bytes
                steady = live if steady is None else steady
                self.assertLess(live - steady, 4096)
            count += 1
        self.assertEqual(count, 128)
        owner.close()
        self.assertEqual(fixture.budget.ram_bytes, baseline)


if __name__ == '__main__':
    # 直接运行本专项只验证本联合历史节点，完整回归由根统一执行。
    unittest.main()
