"""验收真实历史上的整窗样本极值与均值，以及单遍有限资源生命周期。

memory/CSV真实行只由原工厂读取一次；新分析逐块回读封存历史，不保存全窗值列。
原数值更新、有效性与TRUE选择共同决定样本；TTL、条件更新和裁剪保持不增加样本。
不等样本数的有限块用手算总和/总数核对整窗均值，两个独立后端均执行实际入口。
完整覆盖、UNKNOWN与CSV定位动态计费；预算、构造、分配和取消故障保留清理入口。
新owner只关闭自有块源/当前块/结果；原history/state由工厂最后关闭并核对RAM0。
所有合成历史及验证输出只写新项目work，不修改历史快照。
"""

# 工厂与账本注入助手以模块别名复用，避免重复发现已有测试类。
import unittest
from unittest.mock import patch
import test_historical_conditional_blocks as real_history
import test_historical_conditional_integral as integral_tests
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution import historical_sample_calculation as module
from chronaxis.execution.historical_sample_calculation import HistoricalSampleCalculation
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.calculation_blocks import CalculationBlock
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


class HistoricalSampleCalculationTests(unittest.TestCase):
    """每个新owner独立清理，原state不因历史回读推进，原账本金额保持。"""

    def prepare(self, *, operation='sample_mean', joint=False, spec=None, backend='numpy', kind='memory', size=1, **kwargs):
        """建立真实历史，先登记原工厂清理，再创建自有分析层。

        参数: operation/joint/spec指定样本请求；backend/kind/size实际配置；kwargs传原工厂。
        返回: fixture,owner,baseline。异常: 原来源/构造错误传播。
        """
        factory = real_history.HistoricalConditionalBlocksTests('runTest')
        self.addCleanup(self.cleanup_factory, factory)
        fixture = factory.fixture(backend=backend, kind=kind, size=size, **kwargs)
        # 记录原history/state等借用金额，新分析不得用总账清零替代自己的责任。
        baseline = fixture.budget.ram_bytes
        spec = CalculationDefinition('samples', operation, fixture.domain) if spec is None else spec
        owner = self.make_owner(fixture, spec, joint, backend, size)
        return fixture, owner, baseline

    def make_owner(self, fixture, spec, joint=False, backend='numpy', size=1):
        """创建实际整窗样本owner并注册自己的close。

        参数: fixture真实输入；spec/joint/backend/size原配置。返回: 新owner。异常: 原构造故障。
        """
        owner = HistoricalSampleCalculation(fixture.history, fixture.holds._context, fixture.lease.bindings,
            fixture.compiled[0], spec, fixture.compiled[1] if joint else None,
            backend=backend, batch_intervals=size)
        self.addCleanup(owner.close)
        return owner

    def cleanup_factory(self, factory):
        """核对原工厂RAM0。参数: 工厂。返回: None。异常: 最终清理断言失败。"""
        self.assertTrue(factory.doCleanups())

    def consume(self, owner):
        """逐次消费有限块，不累计测试自己的值数组或块均值。

        参数: 实际owner。返回: 完整CalculationResult。异常: 原推进错误。
        """
        while owner.step():
            pass  # EOF核对、整窗归约和分类由生产单遍完成。
        self.assertTrue(owner.finished)
        self.assertFalse(owner.step())
        return owner.result

    def close_and_check(self, fixture, owner, baseline):
        """归还全部自有状态，重复关闭安全且原历史保持开放。

        参数: 实际资源和分析前金额。返回: None。异常: 所有权或金额不符。
        """
        # 两次成功关闭验证只归还自有金额一次；借用history/state仍开放，账本恢复分析前基线。
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertFalse(fixture.history.closed)
        self.assertEqual(fixture.state.revision, 0)
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def cancel_at(self, original, **kwargs):
        """复用实际账本前后一次取消助手，实际费用仍由owner登记。

        参数: 原方法及call/after/exception配置。返回: 注入函数。异常: 原助手错误。
        """
        return integral_tests.HistoricalConditionalIntegralTests('runTest').cancel_at(original, **kwargs)

    def values_fixture(self, values, *, operation='sample_mean', unit='W', dtype=D.FLOAT64, output=None, **kwargs):
        """每秒真实更新一个值，末点重复值只提供右EOF边界。

        参数: values手算样本；operation/unit/dtype/output声明分析；kwargs为真实配置。
        返回: prepare三元组。异常: 工厂或模型错误传播。
        """
        end = len(values) * 1_000_000_000
        rows = {'table': tuple(MemoryRow(index * 1_000_000_000, {'raw.a': value}, index)
                for index, value in enumerate(tuple(values) + (values[-1],))),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(end, {'raw.b': 0}, 1))}
        definitions = (SignalDefinition('a', 'table', 'raw.a', dtype, unit, end+1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', end+1))
        return self.prepare(operation=operation, spec=CalculationDefinition('samples', operation, Interval(0, end), output_unit=output),
                            domain=(0, end), definitions=definitions, rows_by_source=rows, **kwargs)

    def test_real_sources_backends_splits_use_total_sample_count_without_rescan(self):
        """样本2/4/6/8/30共五个，min2/max30/mean10；2/2/1块样本数不能取块均值平均。

        参数: 无。返回: None。异常: 整窗计数/数值错误或重新扫描原adapter。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    for operation, expected in (('sample_minimum', 2.), ('sample_maximum', 30.), ('sample_mean', 10.)):
                        fixture, owner, baseline = self.values_fixture((2, 4, 6, 8, 30), operation=operation, kind=kind, backend=backend, size=size)
                        # 封存后禁用原adapter；新样本均值不需第二次建块源或重新读取原CSV。
                        with patch.object(owner, '_make_blocks', side_effect=AssertionError('sample-second-pass')) as rebuild, patch.object(BudgetedMemorySourceAdapter, 'iter_batches', side_effect=AssertionError('memory-rescan')) as memory_scan:
                            with patch.object(BudgetedSignalCSVSourceAdapter, 'iter_batches', side_effect=AssertionError('csv-rescan')) as csv_scan:
                                result = self.consume(owner)
                                rebuild.assert_not_called()
                                memory_scan.assert_not_called()
                                csv_scan.assert_not_called()
                        self.assertEqual((result.value, result.valid_sample_count, result.status), (expected, 5, 'complete'))
                        self.assertEqual(result.binding_identity, fixture.compiled[0].identity)
                        self.assertEqual(result.value_coverage, 1.)
                        self.close_and_check(fixture, owner, baseline)

    def test_condition_updates_and_true_false_unknown_keep_one_actual_selected_sample(self):
        """4W保持窗内仅0秒真实更新，T/F/U/T边界不会制造样本，三个样本算子均得4。

        参数: 无。返回: None。异常: 条件/块边界增样本或条件事实丢失。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    for operation in ('sample_minimum', 'sample_maximum', 'sample_mean'):
                        fixture, owner, baseline = self.prepare(operation=operation, joint=True, kind=kind, backend=backend, size=size)
                        result = self.consume(owner)
                        self.assertEqual((result.value, result.valid_sample_count, result.status), (4., 1, 'partial'))
                        self.assertEqual((result.value_valid_duration_ns, result.condition_known_duration_ns,
                                          result.selected_duration_ns), (4_000_000_000, 3_000_000_000, 2_000_000_000))
                        self.assertEqual(result.condition_unknown_ranges, (Interval(2_000_000_000, 3_000_000_000),))
                        self.close_and_check(fixture, owner, baseline)

    def test_condition_ttl_and_simultaneous_updates_only_count_real_value_samples(self):
        """条件TTL产生T/U/T/U，0/2秒真实更新4/8各选一次，样本均值6而非时间边界均值。

        参数: 无。返回: None。异常: 条件TTL/同刻更新改变选中样本或未知。
        """
        end = 4_000_000_000
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', end+1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 1_000_000_000))
        rows = {'table': (MemoryRow(0, {'raw.a': 4}, 0), MemoryRow(2_000_000_000, {'raw.a': 8}, 1), MemoryRow(end, {'raw.a': 99}, 2)),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(2_000_000_000, {'raw.b': 1}, 1), MemoryRow(end, {'raw.b': 0}, 2))}
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                fixture, owner, baseline = self.prepare(joint=True, backend=backend, size=size, definitions=definitions, rows_by_source=rows)
                result = self.consume(owner)
                self.assertEqual((result.value, result.valid_sample_count, result.selected_duration_ns), (6., 2, 2_000_000_000))
                self.assertEqual(result.condition_unknown_ranges, (Interval(1_000_000_000, 2_000_000_000), Interval(3_000_000_000, end)))
                self.close_and_check(fixture, owner, baseline)

    def test_clipped_left_hold_right_eof_point_and_outside_keep_half_open_samples(self):
        """左裁剪保持无真实更新，右EOF更新排除；点和域外都不能借空和返回0。

        参数: 无。返回: None。异常: 窗口边界或末点被当有效样本。
        """
        end = 4_000_000_000
        cases = ((Interval(500_000_000, 2_500_000_000), None, 0, 'no_samples'),
                 (Interval(0, end), 4., 1, 'ok'), (Interval(0, 0), None, 0, 'zero_length_window'),
                 (Interval(end+1, end+2), None, 0, 'no_observation'))
        for backend in ('reference', 'numpy'):
            for window, value, samples, reason in cases:
                fixture, owner, baseline = self.prepare(backend=backend, spec=CalculationDefinition('samples', 'sample_mean', window))
                result = self.consume(owner)
                self.assertEqual((result.value, result.valid_sample_count, result.reason), (value, samples, reason))
                self.close_and_check(fixture, owner, baseline)

    def test_full_false_unknown_and_true_invalid_keep_distinct_empty_reasons(self):
        """全FALSE样本为空None，UNKNOWN无法判断，TRUE值无效也不填0；真实诊断仍保留。

        参数: 无。返回: None。异常: 三种证据混同或UNKNOWN被当FALSE。
        """
        end = 4_000_000_000
        for backend in ('reference', 'numpy'):
            for value, condition, reason in ((None, 0, 'empty_selection'), (4, None, 'unknown_selection'), (None, 1, 'no_valid_selected_data')):
                rows = {'table': (MemoryRow(0, {'raw.a': value}, 0), MemoryRow(end, {'raw.a': value}, 1)),
                        'other': (MemoryRow(0, {'raw.b': condition}, 0), MemoryRow(end, {'raw.b': condition}, 1))}
                fixture, owner, baseline = self.prepare(joint=True, backend=backend, rows_by_source=rows)
                result = self.consume(owner)
                self.assertIsNone(result.value)
                self.assertEqual((result.reason, result.valid_sample_count), (reason, 0))
                self.assertEqual(result.status, 'complete' if condition == 0 else 'indeterminate')
                self.close_and_check(fixture, owner, baseline)

    def test_strict_and_minimum_coverage_preserve_original_sample_facts(self):
        """条件覆盖3/4时report保留4W，strict删值；最低门槛不改样本计数或请求。

        参数: 无。返回: None。异常: 政策和实际样本事实混同。
        """
        for backend in ('reference', 'numpy'):
            for policy in ('report', 'strict'):
                spec = CalculationDefinition('samples', 'sample_mean', Interval(0, 4_000_000_000), policy, minimum_coverage=.9, scope='event')
                fixture, owner, baseline = self.prepare(joint=True, backend=backend, spec=spec)
                result = self.consume(owner)
                self.assertIs(result.spec, spec)
                self.assertEqual(result.value, 4. if policy == 'report' else None)
                self.assertEqual((result.valid_sample_count, result.condition_coverage, result.coverage_status), (1, .75, 'indeterminate'))
                self.close_and_check(fixture, owner, baseline)

    def test_raw_sample_sum_overflow_is_permanent_even_after_later_cancellation(self):
        """样本原序和1e308+1e308先溢出，后续-1e308不能恢复；输入覆盖和样本3保留。

        参数: 无。返回: None。异常: 改成规范时间权重避开既定样本和或丢失事实。
        """
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                fixture, owner, baseline = self.values_fixture((1e308, 1e308, -1e308), backend=backend, size=size)
                result = self.consume(owner)
                self.assertEqual((result.value, result.reason, result.valid_sample_count, result.value_coverage), (None, 'calculation_failed', 3, 1.))
                self.assertTrue(result.quality & Q.NONFINITE)
                self.close_and_check(fixture, owner, baseline)

    def test_large_integer_extrema_mean_precision_and_final_unit_failure_preserve_contract(self):
        """uint64极值保留原整数、均值精度损失为未知；最终V转mV溢出仅使数值失败。

        参数: 无。返回: None。异常: 偷转float或换算失败改写输入覆盖。
        """
        for backend in ('reference', 'numpy'):
            for operation, expected in (('sample_minimum', 2**64-3), ('sample_maximum', 2**64-1), ('sample_mean', None)):
                fixture, owner, baseline = self.values_fixture((2**64-1, 2**64-3), operation=operation, dtype=D.UINT64, unit='1', backend=backend)
                result = self.consume(owner)
                self.assertEqual(result.value, expected)
                if operation == 'sample_mean':
                    self.assertEqual((result.value_valid_duration_ns, result.valid_sample_count), (0, 0))
                    self.assertTrue(result.quality & Q.PRECISION_LOSS)
                else:
                    self.assertIs(type(result.value), int)
                self.close_and_check(fixture, owner, baseline)
            fixture, owner, baseline = self.values_fixture((1e308,), unit='V', output='mV', backend=backend)
            result = self.consume(owner)
            self.assertEqual((result.value, result.reason, result.value_coverage, result.valid_sample_count), (None, 'calculation_failed', 1., 1))
            self.close_and_check(fixture, owner, baseline)

    def test_all_unknown_ranges_and_csv_refs_grow_final_metadata_reservation(self):
        """100个值TTL未知与CSV定位完整保留，样本均值4W/100样本，最后预约随诊断增长。

        参数: 无。返回: None。异常: 诊断截断、来源退化或快照无预算。
        """
        # 数值每2ns真实更新一次、TTL1ns：0—200ns有100个有效样本及交替的100个未知1ns段，末点不计样本。
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', 1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 201))
        rows = {'table': tuple(MemoryRow(time, {'raw.a': 4}, index) for index, time in enumerate(range(0, 201, 2))),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(200, {'raw.b': 0}, 1))}
        fixture, owner, baseline = self.prepare(kind='csv', size=7, domain=(0, 200), definitions=definitions, rows_by_source=rows)
        # 正向完整诊断明确给128MiB，预算拒绝另测；停在末块之后、冻结最终事实之前。
        fixture.budget.memory_budget_bytes = 128*1024*1024
        while owner._cursor != owner._actual.end_ns:
            owner.step()
        before = fixture.budget.ram_bytes
        self.assertFalse(owner.step())
        self.assertGreater(fixture.budget.ram_bytes-before, 65536+4096*100)
        result = owner.result
        self.assertEqual((result.value, result.valid_sample_count, result.value_valid_duration_ns), (4., 100, 100))
        self.assertEqual(len(result.value_unknown_ranges), 100)
        # 来源保留CSV子类的路径、行号、原时间和原值；不能只保留通用字段或截断100行定位。
        refs = [ref for ref in result.source_refs if isinstance(ref, CSVSourceRef)]
        self.assertGreaterEqual(len(refs), 100)
        self.assertTrue(all(ref.path and ref.line_number >= 2 and ref.time_text and ref.value_text == '4' for ref in refs))
        self.close_and_check(fixture, owner, baseline)

    def test_workspace_and_final_snapshot_budget_precede_kernel_and_result_allocation(self):
        """先取得有限块再预约核空间；完整末块后先预约快照，预算不足各自不调用分配入口。

        参数: 无。返回: None。异常: 越预算执行核、快照或交付失败前缀。
        """
        fixture, owner, baseline = self.prepare()
        # 本owner第一次_reserve为next成功后的核workspace，不依赖易变化的具体费用公式。
        with patch.object(owner, '_reserve', side_effect=BudgetExceededError('sample-workspace')), patch.object(owner._reducer, 'push') as push:
            with self.assertRaises(BudgetExceededError):
                owner.step()
            push.assert_not_called()
        self.close_and_check(fixture, owner, baseline)
        fixture, owner, baseline = self.prepare()
        while owner._cursor != owner._actual.end_ns:
            owner.step()
        # 已消费完整窗口仍未分类，最终预约先于冻结快照；预算设置不影响已完成的读取。
        fixture.budget.memory_budget_bytes = fixture.budget.ram_bytes
        with patch.object(owner, '_facts_snapshot') as snapshot:
            with self.assertRaises(BudgetExceededError):
                owner.step()
            snapshot.assert_not_called()
        with self.assertRaises(RuntimeError):
            _ = owner.result
        self.close_and_check(fixture, owner, baseline)

    def test_real_single_and_joint_child_constructor_cleanup_preserve_original_recovery(self):
        """单值/联合子构造申请成功后失败且持续清理取消，原异常保留父恢复owner。

        参数: 无。返回: None。异常: 原异常替换或未赋值子句柄丢失。
        """
        for joint in (False, True):
            fixture, existing, baseline = self.prepare(joint=joint)
            existing.close()  # 原fixture仍开放，构造故障完成后必须回到此借用基线。
            original = MemoryError('sample-constructor-original')
            # 父固定申请为第1笔，新子固定申请为第2笔；后者成功后失败，父子释放均持续取消。
            with patch.object(fixture.budget, 'reserve_ram', self.cancel_at(fixture.budget.reserve_ram,
                    call=2, after=True, exception=original)), patch.object(fixture.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-cleanup')):
                with self.assertRaises(MemoryError) as caught:
                    self.make_owner(fixture, CalculationDefinition('samples', 'sample_mean', fixture.domain), joint)
            self.assertIs(caught.exception, original)
            recovery = original.historical_sample_calculation_cleanup_owner
            self.addCleanup(recovery.close)
            self.close_and_check(fixture, recovery, baseline)

    def test_array_failure_hides_prefix_and_retains_current_owned_block(self):
        """核分配失败在取得块及预约后传播原异常，当前块仍可由owner显式关闭。

        参数: 无。返回: None。异常: 原异常替换、前缀开放或资源失去句柄。
        """
        fixture, owner, baseline = self.prepare(joint=True)
        original = MemoryError('sample-array')
        with patch.object(owner._reducer, 'push', side_effect=original):
            with self.assertRaises(MemoryError) as caught:
                owner.step()
        self.assertIs(caught.exception, original)
        self.assertIsNotNone(owner._current)
        self.assertTrue(owner.failed)
        with self.assertRaises(RuntimeError):
            _ = owner.result
        self.close_and_check(fixture, owner, baseline)

    def test_workspace_reserve_release_cancel_before_after_recover_actual_budget(self):
        """首块workspace申请/释放前后取消封闭前缀，重试close按实际金额归还自有资源。

        参数: 无。返回: None。异常: 已释放费用被重复扣账或借用历史关闭。
        """
        for method in ('_reserve', '_release'):
            for after in (False, True):
                fixture, owner, baseline = self.prepare(joint=True)
                actual = getattr(owner, method)
                cancel = self.cancel_at(actual, after=after)

                def cancel_positive(amount):
                    """跳过初块空事实释放。参数: bytes。返回: 原结果。异常: 正workspace一次取消。"""
                    # 首块没有旧facts费用，零金额释放要真实执行但不触发故障；首笔正释放才是workspace归还。
                    return cancel(amount) if amount > 0 else actual(amount)

                # 首笔正申请就是workspace；事实旧费用为0，首笔正释放才是workspace归还。
                with patch.object(owner, method, cancel_positive):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.step()
                self.assertTrue(owner.failed)
                self.close_and_check(fixture, owner, baseline)

    def test_current_block_and_final_owner_close_cancel_before_after_are_retryable(self):
        """当前块关闭和完整结果owner关闭分开注入，实际释放前后重试均不扣借用资源。

        参数: 无。返回: None。异常: 当前句柄丢失、重复扣账或关闭后结果开放。
        """
        for after in (False, True):
            fixture, owner, baseline = self.prepare()
            actual = CalculationBlock.close

            def cancel_close(block):
                """取消当前块关闭。参数: 实际块。返回: None。异常: 指定时机关闭取消。"""
                # after=True先完成实际块关闭再取消，金额已经归还；False则保留未释放的当前句柄。
                if after:
                    actual(block)
                raise KeyboardInterrupt('sample-current-close')

            # 推进失败后由owner收尾当前块和自有子源；两种时机均不重复扣借用history的费用。
            with patch.object(CalculationBlock, 'close', cancel_close):
                with self.assertRaises(KeyboardInterrupt):
                    owner.step()
            self.close_and_check(fixture, owner, baseline)
            # 第二个owner先完成整窗；关闭所有自有子后，仅针对父剩余金额动作取消。
            fixture, owner, baseline = self.prepare(joint=True)
            self.consume(owner)
            with patch.object(fixture.budget, 'release_ram', self.cancel_at(fixture.budget.release_ram,
                    target=owner._held_cost, after=after)):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.close_and_check(fixture, owner, baseline)
            with self.assertRaises(ResultClosedError):
                _ = owner.result
