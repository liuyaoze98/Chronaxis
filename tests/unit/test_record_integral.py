"""核对周期积分的有界输入、失败清理和真实三格式入口；不代替公共AnalysisRunner验收。"""

from configuration_fixtures import current_fixture

from dataclasses import replace
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.record_integral import RecordIntegral
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError, BudgetExceededError
from chronaxis.sources.models import ReadRequest
import test_raw_can_continuous as files
from test_current_message_calculation import config


def point(time, value):
    """构造一个驱动点，缺值明确无效。参数: 时间和值。返回: tuple。异常: 模型错误。"""
    return (time, ScalarValue(value, D.FLOAT64) if value is not None else
            ScalarValue(None, D.FLOAT64, False, Q.MISSING))


class RecordIntegralTests(unittest.TestCase):
    """用手算预期检查两后端，无效值、窗口和批次不能改变计算含义。"""

    def owner(self, *, backend='numpy', size=2, window=None, policy='report', unit=None):
        """创建独立预算及被测对象。参数: 计算设置。返回: owner,budget。异常: 构造失败。"""
        budget = ResourceBudget()
        spec = CalculationDefinition('energy', 'integral', window or Interval(0, 300_000_000),
                          partial_policy=policy, output_unit=unit)
        owner = RecordIntegral(budget, spec, 'W', D.FLOAT64, 100_000_000,
                               backend=backend, batch_intervals=size)
        self.addCleanup(owner.close)
        return owner, budget

    def test_half_period_and_batches(self):
        """半周期200J加整周期400J；末点不加，分批只保留一个共享端点。"""
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 64):
                owner, budget = self.owner(backend=backend, size=size,
                    window=Interval(60_000_000, 300_000_000), unit='Wh')
                for time in (0, 120_000_000, 300_000_000):
                    owner.consume((point(time, 4000.),))
                result = owner.finish()
                self.assertAlmostEqual(result.value, 600. / 3600)
                self.assertEqual(result.status, 'complete')
                self.assertIs(owner.finish(), result)
                self.assertEqual(len(owner._rows), 1)
                self.assertEqual(budget.spool_bytes, 0)
                with self.assertRaises(ResultClosedError):
                    owner.consume(())
                owner.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_missing_does_not_bridge_and_strict_is_null(self):
        """中间缺值覆盖原值；首半周期200J保留或按strict置空。"""
        for backend in ('reference', 'numpy'):
            for policy in ('report', 'strict'):
                owner, _ = self.owner(backend=backend, size=1, policy=policy,
                                      window=Interval(60_000_000, 300_000_000))
                for time, value in ((0, 4000.), (120_000_000, None), (300_000_000, 9000.)):
                    owner.consume((point(time, value),))
                result = owner.finish()
                self.assertEqual(result.value, 200. if policy == 'report' else None)
                self.assertNotEqual(result.status, 'complete')
                self.assertTrue(result.quality & Q.MISSING)

    def test_empty_single_unknown_zero_and_zero_window(self):
        """无观测/全无效不冒充有效零，单点不制造末尾周期。"""
        for backend in ('reference', 'numpy'):
            for values, expected in (((), None), ((4000.,), None), ((None, 4000.), None), ((0., 4000.), 0.)):
                owner, _ = self.owner(backend=backend, window=Interval(0, 120_000_000))
                owner.consume(tuple(point(i * 120_000_000, value) for i, value in enumerate(values)))
                self.assertEqual(owner.finish().value, expected)
            owner, _ = self.owner(backend=backend, window=Interval(0, 0))
            owner.consume((point(0, 4000.), point(120_000_000, 4000.)))
            self.assertIsNone(owner.finish().value)

    def test_failure_does_not_publish_prefix(self):
        """时间回退和超预算后拒绝finish，释放仅抵销本对象费用。"""
        owner, budget = self.owner(size=1)
        owner.consume((point(0, 4000.), point(120_000_000, 4000.)))
        with self.assertRaises(ValueError):
            owner.consume((point(100, 4000.),))
        with self.assertRaises(ResultClosedError):
            owner.finish()
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)
        owner, budget = self.owner(size=1)
        budget.memory_budget_bytes = budget.ram_bytes
        with self.assertRaises(BudgetExceededError):
            owner.consume((point(0, 1.), point(1, 1.)))
        with self.assertRaises(ResultClosedError):
            owner.finish()
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_budget_callback_cancel_and_release_retry(self):
        """费用入账后取消也要归还；释放前取消不能把对象误标为已关闭。"""
        owner, budget = self.owner(size=1)
        reserve = budget.reserve_ram
        def cancelled(amount):
            """模拟预约成功后取消。参数: bytes。返回: 无。异常: KeyboardInterrupt。"""
            reserve(amount)
            raise KeyboardInterrupt()
        with patch.object(budget, 'reserve_ram', side_effect=cancelled):
            with self.assertRaises(KeyboardInterrupt):
                owner.consume((point(0, 1.), point(1, 1.)))
        with patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                owner.close()
        self.assertFalse(owner.closed)
        owner.close()
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_no_unknown_range_details_requested(self):
        """默认摘要把未知范围构造显式关掉，质量和有效时长仍用于结果分类。"""
        owner, _ = self.owner(size=1)
        with patch.object(owner, '_compute', wraps=owner._compute) as compute:
            owner.consume((point(0, None), point(120_000_000, 1.)))
        self.assertIs(compute.call_args.kwargs['retain_unknown_ranges'], False)
        self.assertTrue(owner.finish().quality & Q.MISSING)

    def test_long_stream_keeps_same_memory_bound(self):
        """记录总数增长不增加缓冲峰值；同一手算结果不受分批改变。"""
        peaks = []
        for count in (65, 513):
            owner, budget = self.owner(size=8, window=Interval(0, count - 1))
            for time in range(count):
                owner.consume((point(time, 10.),))
            self.assertEqual(owner.finish().value, float(count - 1))
            peaks.append(budget.peak_ram_bytes)
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)
        self.assertEqual(peaks[0], peaks[1])

    def test_expiry_gap_and_recovery_across_batches(self):
        """真实0.15秒过期不被固定周期延长；保前段、不填缺口，恢复后从新值算。"""
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 64):
                for policy in ('report', 'strict'):
                    owner, budget = self.owner(backend=backend, size=size, policy=policy,
                                              window=Interval(0, 540_000_000))
                    for time, value, deadline in ((0, 4000., 150_000_000),
                        (180_000_000, 4000., 150_000_000), (360_000_000, 2000., 510_000_000),
                        (540_000_000, 2000., 510_000_000)):
                        owner.consume((point(time, value) + (deadline,),))
                    result = owner.finish()
                    if policy == 'report':
                        self.assertAlmostEqual(result.value, 500.)
                        self.assertEqual(result.status, 'partial')
                    else:
                        self.assertIsNone(result.value)
                        self.assertEqual(result.reason, 'insufficient_coverage')
                    self.assertTrue(result.quality & Q.STALE)
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_numeric_failure_and_large_integer_time(self):
        """输出单位溢出不能发布正常值，数组整数时间先规范成Python整数。"""
        import numpy as np
        for backend in ('reference', 'numpy'):
            owner, _ = self.owner(backend=backend, window=Interval(0, 1))
            owner.consume((point(np.int64(0), 4000.), point(np.int64(1), 4000.)))
            self.assertEqual(owner.finish().value, 400.)
            spec = CalculationDefinition('energy', 'integral', Interval(0, 1))
            budget = ResourceBudget()
            owner = RecordIntegral(budget, spec, 'kW', D.FLOAT64, 10**9, backend=backend)
            self.addCleanup(owner.close)
            owner.consume((point(0, 1e308), point(1, 1e308)))
            result = owner.finish()
            self.assertIsNone(result.value)
            self.assertEqual(result.reason, 'calculation_failed')
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)


class RecordIntegralFormatsTests(unittest.TestCase):
    """真实格式解码后供给同一个积分器；暂不覆盖表达式/TTL与公开计划接线。"""

    setUp = files.RawCANContinuousTests.setUp
    asc = files.RawCANContinuousTests.asc
    csv = files.RawCANContinuousTests.csv
    blf = files.RawCANContinuousTests.blf

    def test_three_formats_same_record_pairs(self):
        """三条4000W形成两个0.1s周期，窗口剪掉首半段后为600J。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 2 Node\n SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n', encoding='utf-8')
        paths = {'can_blf': self.blf(((0., bytes([160, 15])), (.12, bytes([160, 15])), (.3, bytes([160, 15])))),
                 'can_asc': self.asc('0.00 1 100 Rx d 2 A0 0F\n0.12 1 100 Rx d 2 A0 0F\n0.30 1 100 Rx d 2 A0 0F\n').path,
                 'raw_can_csv': self.csv('0,100,A0 0F,2\n0.12,100,A0 0F,2\n0.30,100,A0 0F,2\n').path}
        for kind, path in paths.items():
            raw = config(kind)
            raw['sources'][0]['path'] = str(path.absolute())
            raw['sources'][0]['dbc_by_channel'] = {'1': str(self.dbc.absolute())}
            plan = AnalysisPlan.from_dict(current_fixture(raw))
            source_config = plan.sources[0].config
            if kind == 'can_blf':
                # BLF夹具使用明确绝对起点；与文本的相对0秒对齐后再应用同一窗口。
                source_config = replace(source_config, offset_ns=-1700000000 * 10**9)
            owner = RecordIntegral(self.budget, CalculationDefinition('energy', 'integral',
                Interval(60_000_000, 300_000_000)), 'W', D.FLOAT64, 100_000_000, batch_intervals=1)
            self.addCleanup(owner.close)
            factory = BudgetedLegacyCANSourceAdapter if kind == 'can_blf' else BudgetedTextCANSourceAdapter
            adapter = factory(self.budget, source_config, 'session',
                tuple(item.definition for item in plan.signals), work_dir=self.root / ('integral-' + kind),
                message_consumer=lambda row: owner.consume((point(row.time_ns, float(row.values['Power'])),)),
                **({'batch_read': True} if kind == 'can_blf' else {}))
            try:
                read = adapter.iter_batches(ReadRequest('session', (), 0, 12 * 10**9, 2))
                try:
                    for batch in read:
                        self.assertFalse(batch.series)
                finally:
                    read.close()
            finally:
                adapter.close()
            # 读取及关闭成功后才取得结果；本条不把解析入口测试冒充公开AnalysisRunner。
            self.assertAlmostEqual(owner.finish().value, 600., places=3)
            owner.close()
            self.assertEqual(self.budget.ram_bytes, 0)
