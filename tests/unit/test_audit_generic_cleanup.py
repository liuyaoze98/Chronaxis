"""核对计算失败与预算释放失败同时发生时的主异常、真实费用和重试关闭。

故障只包装真实账本调用，分别覆盖退款前失败和退款生效后的取消；
此前已交付的事件仍可读，调用方独立费用始终保留。本专项不读业务日志。
"""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan
from chronaxis.core.quantiles import ExactQuantileBuffer
from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, Truth as T
from chronaxis.execution.temporal_buffer import BudgetedTemporalDetector
from chronaxis.execution.transform_stream import TransformStage
from chronaxis.planning.intervals import IntervalChoice
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import AnalysisError, ResultClosedError


class AfterEffect:
    """先执行真实操作，首次成功后抛指定异常；不修改其他所有者的费用。"""

    def __init__(self, operation, error):
        """保存已绑定操作和同一个异常对象。参数: 原操作、错误。返回: 新故障包装。"""
        self.operation, self.error, self.used = operation, error, False

    def __call__(self, amount):
        """执行一笔真实账本交易再取消。参数: 字节数。返回: 原返回值。异常: 首次指定错误。"""
        result = self.operation(amount)
        if not self.used:
            self.used = True
            raise self.error
        return result


class GenericCleanupTests(unittest.TestCase):
    """使用小型真实owner和共享账本，不以伪造释放或放宽断言消除失败。"""

    EXTERNAL = 4096

    def budget(self):
        """为调用方保留独立费用。参数: 无。返回: 真实预算。异常: 真实预算拒绝。"""
        budget = ResourceBudget(64 * 1024**2)
        budget.reserve_ram(self.EXTERNAL)
        return budget

    def quantile(self, backend):
        """建两个数值样本的真实分位数缓冲。参数: 后端。返回: owner和账本。"""
        budget = self.budget()
        owner = ExactQuantileBuffer('sample_median', None, D.INT64, backend, budget)
        self.addCleanup(owner.close)
        if backend == 'reference':
            owner.append((10, 30))
        else:
            import numpy as np
            owner.append(np.array([10, 30], dtype=np.int64), np.array([True, True]))
        return owner, budget

    def transform(self, backend='reference'):
        """通过真实配置生成一层网格变换，游标只提供明确观测边界，不运行来源。"""
        raw = dict(config_version=4, dataset=dict(name='demo', domain=dict(start='0s', end='3s')),
            sources=[dict(name='meter', source_type='memory', rows=[
                dict(time='0s', values={'raw': 10.}), dict(time='3s', values={'raw': 20.})])],
            signals=[dict(name='a', field='raw', dtype='float64', unit='A', valid_for='30s')],
            transforms=[dict(name='trend', operation='rolling_time_mean', expr='a',
                             window='1s', step='1s', origin='0s')],
            calculations=[dict(name='points', operation='select', expr='trend')],
            execution=dict(backend=backend))
        plan = AnalysisPlan.from_dict(raw)
        budget, delivered = self.budget(), []
        cursors = {'meter': SimpleNamespace(observed_start=0, observed_end=3_000_000_000, _finished=True)}
        owner = TransformStage(plan, plan.transforms[0], tuple(s.definition for s in plan.signals),
            IntervalChoice(), None, {'meter': 3_000_000_000}, cursors, budget, delivered.append)
        self.addCleanup(owner.close)
        return owner, budget, delivered

    @staticmethod
    def tick(time, truth, terminal=False):
        """创建明确实际输入或真正末点。参数: 纳秒/三值/末点。返回: ConditionTick。"""
        return ConditionTick(time, truth, Q.MISSING if truth is T.UNKNOWN else Q.NONE,
                             not terminal, False, terminal)

    def temporal(self, backend, method):
        """保留一个已交付事件，准备下一push或finish。参数: 后端、方法。返回: 四元组。"""
        budget = self.budget()
        rule = TemporalRule('edge', 'data', 'session', 'rising_edge', 0, False, 0)
        owner = BudgetedTemporalDetector(budget, rule, 0, 4, backend=backend)
        self.addCleanup(owner.close)
        prior = owner.push((self.tick(0, T.FALSE), self.tick(1, T.TRUE)))
        self.assertEqual(len(prior.events), 1)
        if method == 'finish':
            terminal = owner.push((self.tick(4, T.UNKNOWN, True),))
            terminal.close()
            call = owner.finish
        else:
            call = lambda: owner.push((self.tick(2, T.FALSE), self.tick(3, T.TRUE)))
        return owner, budget, prior, call

    def test_quantile_primary_error_survives_refund_before_and_after_effect(self):
        """排序错误始终为主；退款未生效保留真实槽，生效后取消不重复退款。"""
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                with self.subTest(backend=backend, after=after):
                    owner, budget = self.quantile(backend)
                    primary, cleanup = MemoryError('排序失败'), KeyboardInterrupt('退款取消')
                    refund = AfterEffect(budget.release_ram, cleanup) if after else None
                    target = 'chronaxis.core.quantile_' + backend + '.ordered_' + backend
                    with patch(target, side_effect=primary), patch.object(budget, 'release_ram',
                            side_effect=refund if after else cleanup):
                        with self.assertRaises(MemoryError) as caught:
                            owner.finish()
                    self.assertIs(caught.exception, primary)
                    self.assertIs(primary.quantile_cleanup_owner, owner)
                    self.assertTrue(any('释放失败' in n for n in primary.__notes__))
                    self.assertEqual(owner._sort_cost == 0, after)
                    self.assertEqual(budget.ram_bytes, self.EXTERNAL + owner._held_cost)
                    owner.close(); owner.close()
                    self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_quantile_success_refund_after_effect_cancel_never_returns_value(self):
        """数值核成功但退款返回取消时，不交付成功快照也不双退排序费用。"""
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                owner, budget = self.quantile(backend)
                cancel = KeyboardInterrupt('排序空间已释放后取消')
                with patch.object(budget, 'release_ram', side_effect=AfterEffect(budget.release_ram, cancel)):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        owner.finish()
                self.assertIs(caught.exception, cancel)
                self.assertIs(cancel.quantile_cleanup_owner, owner)
                self.assertEqual(owner._sort_cost, 0)
                with self.assertRaises(ResultClosedError):
                    owner.finish()
                owner.close()
                self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_quantile_reserve_after_effect_cancel_survives_refund_failure(self):
        """排序费已预约后的取消是主错，退款失败不遗失缓冲最高owner。"""
        owner, budget = self.quantile('reference')
        cancel = KeyboardInterrupt('排序预约后取消')
        with patch.object(budget, 'reserve_ram', side_effect=AfterEffect(budget.reserve_ram, cancel)), \
             patch.object(budget, 'release_ram', side_effect=OSError('退款失败')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.finish()
        self.assertIs(caught.exception, cancel)
        self.assertIs(cancel.quantile_cleanup_owner, owner)
        self.assertGreater(owner._sort_cost, 0)
        owner.close()
        self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_transform_primary_error_survives_refund_before_and_after_effect(self):
        """求值失败且退款失败时不交付网格，阶段不能再次推进该未完成时刻。"""
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                with self.subTest(backend=backend, after=after):
                    owner, budget, delivered = self.transform(backend)
                    primary, cleanup = ValueError('网格求值失败'), KeyboardInterrupt('退款取消')
                    refund = AfterEffect(budget.release_ram, cleanup) if after else cleanup
                    with patch.object(owner, '_at_grid', side_effect=primary), \
                         patch.object(budget, 'release_ram', side_effect=refund):
                        with self.assertRaises(ValueError) as caught:
                            owner._drain(None, through=0)
                    self.assertIs(caught.exception, primary)
                    self.assertIs(primary.transform_cleanup_owner, owner)
                    self.assertEqual(delivered, [])
                    self.assertEqual(owner.next_grid, 0)
                    self.assertEqual(owner._work_cost == 0, after)
                    with self.assertRaises(ResultClosedError):
                        owner.finish()
                    owner.close(); owner.close()
                    self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_transform_success_refund_after_effect_cancel_does_not_deliver(self):
        """真实空窗口求值完成后退款取消，仍保留取消并停止后续网格。"""
        owner, budget, delivered = self.transform()
        cancel = KeyboardInterrupt('网格退款后取消')
        with patch.object(budget, 'release_ram', side_effect=AfterEffect(budget.release_ram, cancel)):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner._drain(None, through=0)
        self.assertIs(caught.exception, cancel)
        self.assertEqual(owner._work_cost, 0)
        self.assertEqual(delivered, [])
        with self.assertRaises(ResultClosedError):
            owner.finish()
        owner.close()
        self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_transform_reserve_after_effect_cancel_survives_refund_failure(self):
        """网格预约已生效后取消，失败工作区仍由阶段close回收。"""
        owner, budget, delivered = self.transform()
        cancel = KeyboardInterrupt('网格预约后取消')
        with patch.object(budget, 'reserve_ram', side_effect=AfterEffect(budget.reserve_ram, cancel)), \
             patch.object(budget, 'release_ram', side_effect=OSError('退款失败')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner._drain(None, through=0)
        self.assertIs(caught.exception, cancel)
        self.assertIs(cancel.transform_cleanup_owner, owner)
        self.assertGreater(owner._work_cost, 0)
        self.assertEqual(delivered, [])
        owner.close()
        self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_temporal_primary_error_survives_refund_and_preserves_prior_batch(self):
        """core错误后只接管本批未交付费用，旧结果与外部费用不受影响。"""
        for backend in ('reference', 'numpy'):
            for method in ('push', 'finish'):
                for after in (False, True):
                    with self.subTest(backend=backend, method=method, after=after):
                        owner, budget, prior, call = self.temporal(backend, method)
                        baseline, old_events = budget.ram_bytes, prior.events
                        primary, cleanup = ValueError('时序核失败'), KeyboardInterrupt('退款取消')
                        refund = AfterEffect(budget.release_ram, cleanup) if after else cleanup
                        with patch.object(type(owner._detector), method, side_effect=primary), \
                             patch.object(budget, 'release_ram', side_effect=refund):
                            with self.assertRaises(ValueError) as caught:
                                call()
                        self.assertIs(caught.exception, primary)
                        self.assertIs(primary.temporal_detector_cleanup_owner, owner)
                        self.assertTrue(owner.failed)
                        self.assertEqual(tuple(owner._results), (prior,))
                        self.assertEqual(prior.events, old_events)
                        self.assertFalse(prior.closed)
                        self.assertEqual(owner._failed_workspace_cost == 0, after)
                        self.assertEqual(budget.ram_bytes, baseline + owner._failed_workspace_cost)
                        with self.assertRaises(AnalysisError):
                            owner.push(())
                        owner.close(); owner.close()
                        self.assertTrue(prior.closed)
                        self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_temporal_preflight_cancel_refund_failure_is_recoverable_owner(self):
        """core前取消保留业务状态，但未退费用未解决时不能累加第二笔工作区。"""
        for method in ('push', 'finish'):
            with self.subTest(method=method):
                owner, budget, prior, call = self.temporal('reference', method)
                core, last = owner._detector, owner._detector.last_time
                cancel = KeyboardInterrupt('时序预约后取消')
                with patch.object(budget, 'reserve_ram', side_effect=AfterEffect(budget.reserve_ram, cancel)), \
                     patch.object(budget, 'release_ram', side_effect=OSError('退款失败')):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        call()
                self.assertIs(caught.exception, cancel)
                self.assertIs(cancel.temporal_detector_cleanup_owner, owner)
                self.assertFalse(owner.failed)
                self.assertIs(owner._detector, core)
                self.assertEqual(core.last_time, last)
                self.assertGreater(owner._failed_workspace_cost, 0)
                self.assertFalse(prior.closed)
                with self.assertRaises(AnalysisError):
                    owner.push(())
                owner.close()
                self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_temporal_preflight_two_cancels_keep_original_and_allow_retry(self):
        """预约与退款都已生效后取消时保首个取消，无残留费用且core仍可重试。"""
        for method in ('push', 'finish'):
            with self.subTest(method=method):
                owner, budget, prior, call = self.temporal('reference', method)
                baseline = budget.ram_bytes
                primary, cleanup = KeyboardInterrupt('预约取消'), KeyboardInterrupt('退款取消')
                with patch.object(budget, 'reserve_ram', side_effect=AfterEffect(budget.reserve_ram, primary)), \
                     patch.object(budget, 'release_ram', side_effect=AfterEffect(budget.release_ram, cleanup)):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        call()
                self.assertIs(caught.exception, primary)
                self.assertFalse(owner.failed)
                self.assertEqual(owner._failed_workspace_cost, 0)
                self.assertEqual(budget.ram_bytes, baseline)
                fresh = call()
                fresh.close()
                owner.close()
                self.assertEqual(budget.ram_bytes, self.EXTERNAL)

    def test_temporal_pending_refund_after_effect_cancel_is_not_double_released(self):
        """close先退失败批后取消，重试只释放仍持有的旧批与固定费用。"""
        owner, budget, prior, call = self.temporal('reference', 'push')
        baseline = budget.ram_bytes
        primary = ValueError('时序核失败')
        with patch.object(type(owner._detector), 'push', side_effect=primary), \
             patch.object(budget, 'release_ram', side_effect=OSError('首次退款失败')):
            with self.assertRaises(ValueError) as caught:
                call()
        self.assertIs(caught.exception, primary)
        cancel = KeyboardInterrupt('关闭工作区已退款后取消')
        with patch.object(budget, 'release_ram', side_effect=AfterEffect(budget.release_ram, cancel)):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.close()
        self.assertIs(caught.exception, cancel)
        self.assertEqual(owner._failed_workspace_cost, 0)
        self.assertEqual(budget.ram_bytes, baseline)
        self.assertFalse(prior.closed)
        owner.close(); owner.close()
        self.assertEqual(budget.ram_bytes, self.EXTERNAL)


    def test_persistent_close_failure_retains_only_owned_cost_until_recovery(self):
        """连续两次关闭都不能退款时，三个真实owner均保留费用，恢复后只退自身费用。"""
        for kind in ('quantile', 'transform', 'temporal'):
            for backend in ('reference', 'numpy'):
                with self.subTest(kind=kind, backend=backend):
                    prior = None
                    if kind == 'quantile':
                        owner, budget = self.quantile(backend)
                    elif kind == 'transform':
                        owner, budget, delivered = self.transform(backend)
                    else:
                        owner, budget, prior, call = self.temporal(backend, 'push')
                    held = budget.ram_bytes
                    self.assertGreater(held, self.EXTERNAL)
                    cleanup = OSError('预算退款仍不可用')
                    with patch.object(budget, 'release_ram', side_effect=cleanup):
                        for _ in range(2):
                            with self.assertRaises(OSError) as caught:
                                owner.close()
                            self.assertIs(caught.exception, cleanup)
                            self.assertEqual(budget.ram_bytes, held)
                            if prior is not None:
                                self.assertFalse(prior.closed)
                                self.assertEqual(len(prior.events), 1)
                    owner.close(); owner.close()
                    self.assertEqual(budget.ram_bytes, self.EXTERNAL)
                    if prior is not None:
                        self.assertTrue(prior.closed)
