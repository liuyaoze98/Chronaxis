"""独立核对文件面积块与串行积分的原序数值、同刻边界及故障顺序。"""

from dataclasses import replace
from pathlib import Path
import random
import unittest

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import validate_expression, DerivedDefinition
from chronaxis.core.models import Interval, TimebaseSpec, SourceRef
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.execution.file_integral_terms import (FileIntegralTerms, ParentIntegralTerms, FileIntegralHead,
    IntegralTermsChunk, file_terms_cost, parent_terms_cost)
from chronaxis.core.integral_sum import IntegralStateLimitError
from chronaxis.execution.record_integral import RecordIntegral
from chronaxis.execution.same_frame_integrals import SameFrameIntegrals, SameFrameBinding
from chronaxis.legacy.records import LegacyCANField, LegacyRawFrame
from chronaxis.legacy.updates import LegacyDecodedUpdate
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.raw_can import RawCANRecord
from chronaxis.sources.text_can_decode import DecodedCANRecord


class FileIntegralTermsTests(unittest.TestCase):
    """只使用内存帧；期望值由手算或现役独立串行入口提供。"""

    def task(self, *, policy='error', ttl=10**9, domain=None, size=2, dtype=D.FLOAT64, limit=4096):
        """建立一项功率积分。参数: 同刻/TTL/范围/批/类型/误差项限额。返回: 工厂所需冻结任务。"""
        clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'origin')
        field = LegacyCANField(0, 'Power', 256)
        definition = SignalDefinition('power', 'bus', field.key, dtype, 'W', ttl, same_time_policy=policy)
        bindings = DeclarationBindings('session', clock, Interval(0, 10**9),
                                      (DeclaredSource('bus', clock, 'synthetic'),), (definition,))
        expression = validate_expression('power', bindings)
        spec = CalculationDefinition('energy', 'integral', domain or Interval(0, 10**9))
        budget = ResourceBudget()
        calculation = RecordIntegral(budget, spec, expression.root.unit, expression.root.dtype, None,
                                     backend='reference', batch_intervals=size, partial_limit=limit)
        self.addCleanup(calculation.close)
        return budget, (definition,), (expression,), (spec,), calculation, SameFrameBinding('bus', 0, 256, False, None, False)

    def record(self, time, sequence, value, field, *, target=True):
        """生成真实typed投影输入，不读文件。参数: ns/序号/值/字段/是否目标。返回: 解码记录。"""
        frame = LegacyRawFrame(time / 1e9, 256 if target else 257, False, False, False, 0, 0, b'', False, True, False, False)
        raw = RawCANRecord(frame, time, Path('memory.asc'), sequence + 1, sequence, None, 'test', 0)
        return DecodedCANRecord('bus', 0, sequence, raw, ((field, value),) if target else (), 'decoded' if target else 'unselected')

    def run_split(self, files, *, observed_end, worker_size=2, **options):
        """通过真实worker/parent接口按多个文件交付。参数: 文件帧列等。返回: 结果、峰值及最大块长。"""
        budget, definitions, expressions, specs, calculation, binding = self.task(**options)
        parent = ParentIntegralTerms(budget, definitions, expressions, (calculation,), binding, 'session', domain=options.get('domain'))
        self.addCleanup(parent.close)
        offset, largest = 0, 0
        for frames in files:
            worker = FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session',
                                       domain=options.get('domain'), batch_intervals=worker_size)
            self.addCleanup(worker.close)
            parent.begin_file(offset)
            for sequence, (time, value, target) in enumerate(frames):
                for event in worker.feed(self.record(time, sequence, value, definitions[0].field, target=target)):
                    if isinstance(event, IntegralTermsChunk):
                        largest = max(largest, len(event.columns[0].areas))
                    parent.consume(event)
            for event in worker.finish():
                if isinstance(event, IntegralTermsChunk):
                    largest = max(largest, len(event.columns[0].areas))
                parent.consume(event)
            offset += len(frames)
            worker.close()
        parent.finish(observed_end)
        result, peak = calculation.finish(), budget.peak_ram_bytes
        parent.close(); calculation.close()
        self.assertEqual(budget.ram_bytes, 0)
        return result, peak, largest

    def serial(self, files, *, observed_end, **options):
        """调用未分文件的现役同帧入口。参数: 同run_split。返回: 公开数值状态。"""
        budget, definitions, expressions, specs, calculation, binding = self.task(**options)
        owner = SameFrameIntegrals(budget, definitions, expressions, (calculation,), binding, 'session', lambda: None)
        self.addCleanup(owner.close)
        sequence = 0
        for frames in files:
            for time, value, target in frames:
                if target:
                    owner.consume(LegacyDecodedUpdate(time, 'bus', 0, 256, False, False, False, False,
                        SourceRef('session', 'bus', 'power'), sequence, sequence, {'Power': value}))
                sequence += 1
        owner.finish(observed_end)
        result = calculation.finish()
        owner.close(); calculation.close()
        self.assertEqual(budget.ram_bytes, 0)
        return result

    def test_clipping_ttl_invalid_and_partition_invariance(self):
        """边界不重算乘除顺序，TTL和无效更新跨文件保持；比较值/状态/质量全字段。"""
        rng = random.Random(541)
        frames = [(index * 7_000_000, None if index % 13 == 6 else float(rng.randrange(-100, 100)), True)
                  for index in range(81)]
        frames.insert(23, (frames[22][0], frames[22][1], True))
        for size in (1, 2, 7, 64):
            for worker_size in (1, 5, 64):
                options = dict(size=size, ttl=5_000_000, domain=Interval(3_000_000, 555_000_000))
                files = [frames[:1], [], frames[1:24], frames[24:26], frames[26:]]
                actual, _, largest = self.run_split(files, observed_end=560_000_000, worker_size=worker_size, **options)
                self.assertEqual(actual, self.serial(files, observed_end=560_000_000, **options))
                self.assertLessEqual(largest, worker_size)

    def test_one_group_across_many_files_and_empty_files(self):
        """同一时刻跨100份文件只保首末摘要；原帧偏移包括无关帧。"""
        files = [[(0, float(index), True)] for index in range(100)]
        files.insert(45, [(0, 0., False)])
        files.insert(70, [])
        result, _, _ = self.run_split(files, observed_end=10_000_000, policy='last_by_sequence')
        self.assertEqual(result.value, .99)
        self.assertEqual(result, self.serial(files, observed_end=10_000_000, policy='last_by_sequence'))
        empty, _, _ = self.run_split([[], [(0, 0., False)]], observed_end=0)
        self.assertIsNone(empty.value)

    def test_float_order_integer_precision_and_nonfinite_prefix(self):
        """1ns乘法一ULP、整数精度以及跨文件正溢出都复用原核及原序求和。"""
        cases = [([[(0, .1, True)], [(1, .1, True)]], 1, {}),
                 ([[(0, 2**53 + 1, True)], [(1, 1, True)]], 1, dict(dtype=D.INT64)),
                 ([[(0, 1e308, True)], [(10**9, 1e308, True)], [(2*10**9, -1e308, True)], [(3*10**9, 0., True)]],
                  3*10**9, dict(ttl=10**10, domain=Interval(0,3*10**9)))]
        for files, end, options in cases:
            actual, _, _ = self.run_split(files, observed_end=end, **options)
            self.assertEqual(actual, self.serial(files, observed_end=end, **options))
        self.assertEqual(self.run_split(cases[0][0], observed_end=1)[0].value, .1 * (1 / 1e9))

    def test_cross_file_conflict_precedes_later_file_read_error(self):
        """首组没有下一时间时仍可排空冲突摘要，不把后面的坏行错误提前。"""
        budget, definitions, expressions, specs, calculation, binding = self.task()
        parent = ParentIntegralTerms(budget, definitions, expressions, (calculation,), binding, 'session')
        self.addCleanup(parent.close)
        for offset, value in ((0, 10.), (1, 20.)):
            worker = FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session')
            self.addCleanup(worker.close)
            parent.begin_file(offset)
            worker.feed(self.record(0, 0, value, definitions[0].field))
            if offset == 0:
                for event in worker.finish():
                    parent.consume(event)
            else:
                events = worker.drain_prefix_on_error()
                self.assertEqual(len(events), 1)
                with self.assertRaisesRegex(ValueError, '同信号同时间冲突') as raised:
                    parent.consume(events[0])
                self.assertEqual(raised.exception.sequence, 1)
            worker.close()
        parent.close(); calculation.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_worker_conflict_is_immediate_and_prefix_does_not_close_current(self):
        """本文件首组冲突立即停读并提供原位置；不把未闭组追加为积分点。"""
        budget, definitions, expressions, specs, calculation, binding = self.task()
        worker = FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session')
        self.addCleanup(worker.close)
        worker.feed(self.record(0, 0, 10., definitions[0].field))
        with self.assertRaisesRegex(ValueError, '同信号同时间冲突'):
            worker.feed(self.record(0, 1, 20., definitions[0].field))
        events = worker.drain_prefix_on_error()
        self.assertIsInstance(events[0], FileIntegralHead)
        self.assertEqual(events[0].group.first_conflicts, (1,))
        self.assertIsNone(events[0].next_time_ns)
        worker.close(); calculation.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_global_batch_waits_for_right_group_close_before_capacity_failure(self):
        """未闭右组的同刻冲突先报；右组已闭则累计容量错误先于后面的读错。"""
        for close_right in (False, True):
            budget, definitions, expressions, specs, calculation, binding = self.task(
                size=2, limit=1, ttl=10**10, domain=Interval(0, 4*10**9))
            parent = ParentIntegralTerms(budget, definitions, expressions, (calculation,), binding, 'session',
                                         domain=Interval(0, 4*10**9))
            worker = FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session', batch_intervals=64,
                                       domain=Interval(0, 4*10**9))
            self.addCleanup(parent.close); self.addCleanup(worker.close)
            parent.begin_file(0)
            rows = [(0, 1e16), (10**9, 1.), (2*10**9, 2.)]
            if close_right:
                rows.append((3*10**9, 3.))
            for sequence, (time, value) in enumerate(rows):
                for event in worker.feed(self.record(time, sequence, value, definitions[0].field)):
                    parent.consume(event)
            if close_right:
                with self.assertRaises(IntegralStateLimitError):
                    for event in worker.drain_prefix_on_error():
                        parent.consume(event)
            else:
                with self.assertRaisesRegex(ValueError, '同信号同时间冲突'):
                    worker.feed(self.record(2*10**9, 3, 4., definitions[0].field))
                # 首组出区间可确认，但第二区间的右组冲突，尚不能凑满原来的2项归约批。
                for event in worker.drain_prefix_on_error():
                    parent.consume(event)
                self.assertEqual(len(parent._areas[0]), 1)
            worker.close(); parent.close(); calculation.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_size_one_frontier_and_original_serial_fault_match(self):
        """只有一个已闭内部点时需独立frontier，不能漏掉此前已经成立的满批累计错误。"""
        options = dict(size=1, limit=1, ttl=10**10, domain=Interval(0, 4*10**9))
        files = [[(0, 1e16, True)], [(10**9, 1., True)], [(2*10**9, 2., True)], [(3*10**9, 3., True)]]
        with self.assertRaises(IntegralStateLimitError):
            self.serial(files, observed_end=3*10**9, **options)
        with self.assertRaises(IntegralStateLimitError):
            self.run_split(files, observed_end=3*10**9, worker_size=64, **options)

    def test_fixed_budget_and_retryable_cleanup(self):
        """长组不增加序号集合；释放失败保留owner可重试且不重复退款。"""
        budget, definitions, expressions, specs, calculation, binding = self.task(policy='last_by_sequence')
        worker = FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session')
        self.addCleanup(worker.close)
        initial = budget.ram_bytes
        for sequence in range(300):
            worker.feed(self.record(0, sequence, float(sequence), definitions[0].field))
        self.assertEqual(budget.ram_bytes, initial)
        original = budget.release_ram
        calls = 0
        def fail_once(amount):
            """注入首次退款前失败，保留账本可重试。"""
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError('release interrupted')
            original(amount)
        budget.release_ram = fail_once
        with self.assertRaisesRegex(RuntimeError, 'release interrupted'):
            worker.close()
        self.assertFalse(worker._closed)
        self.assertIsNone(worker._current)
        worker.close(); calculation.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_derived_integer_two_metrics_keep_values_quality_and_batch_order(self):
        """保留派生整数溢出及两个指标各自原序累计，不以相同异常代替数值验证。"""
        clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'origin')
        field = LegacyCANField(0, 'Power', 256)
        definitions = (SignalDefinition('power', 'bus', field.key, D.INT64, 'W', 10**9,
                                       same_time_policy='last_by_sequence'),)
        declarations = DeclarationBindings('session', clock, Interval(0, 10**9),
            (DeclaredSource('bus', clock, 'synthetic'),), definitions, ('twice',))
        derived = (DerivedDefinition('twice', 'power * 2'),)
        expressions = tuple(validate_expression(text, declarations, derived=derived) for text in ('power', 'twice'))
        specs = tuple(CalculationDefinition(name, 'integral', Interval(0, 40_000_000)) for name in ('one', 'two'))
        binding = SameFrameBinding('bus', 0, 256, False, None, False)
        budget = ResourceBudget()
        runs = []
        for parallel in (False, True):
            calculations = tuple(RecordIntegral(budget, spec, expr.root.unit, expr.root.dtype, None,
                                backend='reference', batch_intervals=2) for spec, expr in zip(specs, expressions))
            for calculation in calculations:
                self.addCleanup(calculation.close)
            files = [[(0, 3)], [(0, 4), (10_000_000, 2**62)], [(20_000_000, 6), (30_000_000, 7)]]
            if parallel:
                owner = ParentIntegralTerms(budget, definitions, expressions, calculations, binding, 'session',
                                            derived=derived, domain=Interval(0, 40_000_000))
            else:
                owner = SameFrameIntegrals(budget, definitions, expressions, calculations, binding, 'session',
                                           lambda: None, derived=derived)
            self.addCleanup(owner.close)
            offset = 0
            for rows in files:
                if parallel:
                    worker = FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session',
                                               derived=derived, batch_intervals=1, domain=Interval(0, 40_000_000))
                    self.addCleanup(worker.close)
                    owner.begin_file(offset)
                for sequence, (time, value) in enumerate(rows):
                    if parallel:
                        for event in worker.feed(self.record(time, sequence, value, field.key)):
                            owner.consume(event)
                    else:
                        owner.consume(LegacyDecodedUpdate(time, 'bus', 0, 256, False, False, False, False,
                            SourceRef('session', 'bus', 'power'), sequence + offset, sequence + offset, {'Power': value}))
                if parallel:
                    for event in worker.finish():
                        owner.consume(event)
                    worker.close()
                offset += len(rows)
            owner.finish(40_000_000)
            runs.append(tuple(calculation.finish() for calculation in calculations))
            owner.close()
            for calculation in calculations:
                calculation.close()
            self.assertEqual(budget.ram_bytes, 0)
        self.assertEqual(runs[0], runs[1])
        self.assertTrue(runs[1][1].quality & Q.OVERFLOW)
        self.assertEqual(runs[1][1].status, 'partial')

    def test_constructor_transfers_failed_child_and_preserves_keyboard_interrupt(self):
        """子owner入账后取消且退款持续失败时，父owner保留唯一可重试所有权。"""
        for kind in ('file', 'parent'):
            budget, definitions, expressions, specs, calculation, binding = self.task()
            borrowed = budget.ram_bytes
            reserve, release = budget.reserve_ram, budget.release_ram
            calls = 0
            primary = KeyboardInterrupt('interrupted after child reserve')
            def reserve_then_interrupt(amount):
                """第二笔费用属于子求值器，先实账再模拟取消。"""
                nonlocal calls
                calls += 1
                reserve(amount)
                if calls == 2:
                    raise primary
            def deny_release(amount):
                """构造清理暂时无法退款，不能将其误报为已关闭。"""
                raise RuntimeError('release unavailable')
            budget.reserve_ram, budget.release_ram = reserve_then_interrupt, deny_release
            try:
                if kind == 'file':
                    FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session')
                else:
                    ParentIntegralTerms(budget, definitions, expressions, (calculation,), binding, 'session')
            except KeyboardInterrupt as error:
                self.assertIs(error, primary)
                owner = getattr(error, kind + '_integral_terms_cleanup_owner')
                self.assertIs(owner._evaluator, error.same_frame_evaluator_cleanup_owner)
                self.assertFalse(owner._closed)
                self.assertGreater(budget.ram_bytes, borrowed)
            else:
                self.fail('缺少原始KeyboardInterrupt')
            finally:
                budget.reserve_ram, budget.release_ram = reserve, release
            owner.close()
            self.assertTrue(owner._closed)
            self.assertEqual(budget.ram_bytes, borrowed)
            owner.close(); calculation.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_budget_estimates_cover_actual_owner_reservations(self):
        """首帧前估算覆盖实际自有费用；Python共享属性字典缩小不误认为额外支出。"""
        budget, definitions, expressions, specs, calculation, binding = self.task(size=7)
        baseline = budget.ram_bytes
        quote = file_terms_cost(definitions, expressions, specs, batch_intervals=5)
        worker = FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session', batch_intervals=5)
        self.addCleanup(worker.close)
        self.assertLessEqual(budget.ram_bytes - baseline, quote)
        self.assertEqual(budget.ram_bytes - baseline, worker._held_cost + worker._evaluator._held_cost)
        worker.close()
        quote = parent_terms_cost(definitions, expressions, batch_intervals=7)
        parent = ParentIntegralTerms(budget, definitions, expressions, (calculation,), binding, 'session')
        self.addCleanup(parent.close)
        self.assertLessEqual(budget.ram_bytes - baseline, quote)
        self.assertEqual(budget.ram_bytes - baseline, parent._held_cost + parent._evaluator._held_cost)
        parent.close(); calculation.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_two_accumulator_failures_preserve_global_batch_and_metric_order(self):
        """跨文件覆盖首组后，先按全局批再按指标顺序报错，不先算完一整列。"""
        domain = Interval(0, 12*10**9)
        files = [[(0, 10.), (10**9, 20.)],
                 [(10**9, 30.)] + [(index*10**9, float(40 + index)) for index in range(2, 11)]]
        for later_first_failure in (False, True):
            expected_log = None
            for worker_size in (None, 1, 5, 64):
                budget, definitions, expressions, specs, first, binding = self.task(
                    policy='last_by_sequence', ttl=20*10**9, domain=domain, size=2)
                expression = validate_expression('power * 2', expressions[0].bindings)
                expressions += (expression,)
                specs += (replace(specs[0], calculation_id='double_energy'),)
                second = RecordIntegral(budget, specs[1], expression.root.unit, expression.root.dtype,
                                        None, backend='reference', batch_intervals=2)
                self.addCleanup(second.close)
                calculations = (first, second)
                calls, counts = [], [0, 0]
                errors = (RuntimeError('first metric accumulation'), RuntimeError('second metric accumulation'))
                def injection(index, original):
                    """保留正常推进，在指定全局批注入可区分的累计错误。"""
                    def push(values, valid):
                        """空列只更新事实，不冒充累计批；非空列记录真实调用先后。"""
                        if values:
                            counts[index] += 1
                            calls.append((index, counts[index], tuple(values), tuple(valid)))
                            trigger = 2 if index == 0 and later_first_failure else 1
                            if counts[index] == trigger:
                                raise errors[index]
                        return original(values, valid)
                    return push
                for index, calculation in enumerate(calculations):
                    calculation._sum.push_values = injection(index, calculation._sum.push_values)
                if worker_size is None:
                    owner = SameFrameIntegrals(budget, definitions, expressions, calculations, binding,
                                               'session', lambda: None)
                else:
                    owner = ParentIntegralTerms(budget, definitions, expressions, calculations, binding,
                                                'session', domain=domain)
                self.addCleanup(owner.close)
                worker = None
                caught = None
                try:
                    offset = 0
                    for rows in files:
                        if worker_size is not None:
                            worker = FileIntegralTerms(budget, definitions, expressions, specs, binding, 'session',
                                                       domain=domain, batch_intervals=worker_size)
                            self.addCleanup(worker.close)
                            owner.begin_file(offset)
                        for sequence, (time, value) in enumerate(rows):
                            if worker_size is None:
                                owner.consume(LegacyDecodedUpdate(time, 'bus', 0, 256, False, False, False, False,
                                    SourceRef('session', 'bus', 'power'), offset + sequence, offset + sequence,
                                    {'Power': value}))
                            else:
                                for event in worker.feed(self.record(time, sequence, value, definitions[0].field)):
                                    owner.consume(event)
                        if worker_size is not None:
                            for event in worker.finish():
                                owner.consume(event)
                            worker.close()
                        offset += len(rows)
                    owner.finish(11*10**9)
                except RuntimeError as error:
                    caught = error
                finally:
                    if worker is not None:
                        worker.close()
                    owner.close(); first.close(); second.close()
                self.assertIs(caught, errors[int(later_first_failure)])
                self.assertEqual(budget.ram_bytes, 0)
                self.assertEqual(calls[0], (0, 1, (10., 30.), (True, True)))
                self.assertEqual(counts, [1, int(later_first_failure)])
                if worker_size is None:
                    expected_log = calls
                else:
                    self.assertEqual(calls, expected_log)


if __name__ == '__main__':
    unittest.main()
