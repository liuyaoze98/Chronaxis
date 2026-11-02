"""验证时间统计owner的有限内存、必要均值暂存及失败清理，不替代公共AnalysisRunner验收。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.record_time_calculation import RecordTimeCalculation
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError


class RecordTimeCalculationTests(unittest.TestCase):
    """用手算真值分别检查两后端及不同批次，临时文件只位于新项目work。"""

    def setUp(self):
        """建立专用可删除目录。参数: 无。返回: None。异常: IO错误。"""
        self.directory = TemporaryDirectory(dir='work', prefix='time-calculation-')
        self.addCleanup(self.directory.cleanup)

    def owner(self, operation='time_weighted_mean', *, backend='numpy', size=2, conditioned=False,
              policy='report', dtype=D.FLOAT64, window=None, unit='W', step=100_000_000):
        """创建独立预算及owner。参数: 统计设置。返回: owner,budget。异常: 构造失败。"""
        budget = ResourceBudget()
        spec = CalculationDefinition('time', operation, window or Interval(60_000_000, 300_000_000), partial_policy=policy)
        owner = RecordTimeCalculation(budget, spec, unit, dtype, step,
            backend=backend, batch_intervals=size, conditioned=conditioned, work_dir=self.directory.name)
        self.addCleanup(owner.close)
        return owner, budget

    @staticmethod
    def row(time, value, deadline=None, dtype=D.FLOAT64):
        """缺值明确无效。参数: 时间/值/实际截止/类型。返回: 点tuple。异常: 模型错误。"""
        return (time, ScalarValue(None, dtype, False, Q.MISSING) if value is None else ScalarValue(value, dtype), deadline)

    def test_two_pass_mean_deadline_and_cleanup(self):
        """有效权重0.025和0.05，均值2000；仅32字节必要暂存。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 64):
                owner, budget = self.owner(backend=backend, size=size)
                for row in ((0, 4000., 90_000_000), (120_000_000, 1000., 210_000_000), (300_000_000, 999., None)):
                    owner.consume((self.row(*row),))
                result = owner.finish()
                self.assertAlmostEqual(result.value, 2000.)
                self.assertEqual(result.status, 'partial')
                self.assertEqual(budget.spool_bytes, 32)
                self.assertIs(owner.finish(), result)
                self.assertEqual(list(Path(self.directory.name).iterdir()), [])
                owner.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_actual_large_nanosecond_weights_keep_reference_formula(self):
        """超2^53纳秒仍按原整数比例参与参考均值，分批与整批相同。"""
        from math import fsum
        weights = (2**53+1, 7, 19)
        values = (1.1, 1e15, -1e15)
        total = sum(weights)
        expected = fsum(value*(weight/total) for value, weight in zip(values, weights))
        for size in (1, 3):
            owner, budget = self.owner(backend='reference', size=size, step=None, window=Interval(0,total))
            time = 0
            for value, weight in zip(values, weights):
                owner.consume((self.row(time, value),))
                time += weight
            owner.consume((self.row(time, 0.),))
            self.assertEqual(owner.finish().value, expected)
            self.assertEqual(budget.spool_bytes, 48)
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_no_file_for_other_ops_or_empty_mean(self):
        """极值/时长单遍，均值无有效选中项不创建文件。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for operation in ('min_time', 'max_time', 'duration', 'time_weighted_mean'):
                dtype, unit = (D.BOOL, '1') if operation == 'duration' else (D.UINT64, 'W')
                owner, budget = self.owner(operation, backend=backend, dtype=dtype, unit=unit, window=Interval(0, 200))
                values = (None, None, None) if operation == 'time_weighted_mean' else ((False, True, False) if operation == 'duration' else (2**63+1, 2**63+2, 0))
                with patch('chronaxis.execution.record_time_calculation.TemporaryFile', side_effect=AssertionError('不应创建文件')):
                    for time, value in zip((0, 100, 200), values):
                        owner.consume((self.row(time, value, dtype=dtype),))
                    result = owner.finish()
                expected = {'min_time': 2**63+1, 'max_time': 2**63+2, 'duration': 0.1, 'time_weighted_mean': None}[operation]
                self.assertEqual(result.value, expected)
                self.assertEqual(budget.spool_bytes, 0)
                owner.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_condition_false_unknown_and_intermediate_expiry(self):
        """外FALSE不写均值项；非驱动失效切开有效期而不补新周期。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for policy in ('report', 'strict'):
                owner, budget = self.owner(backend=backend, size=1, conditioned=True, policy=policy, window=Interval(0, 300))
                true = (ScalarValue(True, D.BOOL),)
                owner.consume((self.row(0, 100.),), conditions=true)
                owner.expire_at(50, condition=True)
                owner.consume((self.row(100, 200.),), conditions=(ScalarValue(False, D.BOOL),))
                owner.consume((self.row(200, 300.),), conditions=true)
                owner.consume((self.row(300, 999.),), conditions=true)
                result = owner.finish()
                if policy == 'report':
                    self.assertAlmostEqual(result.value, 700/3)
                    self.assertEqual(result.status, 'partial')
                else:
                    self.assertIsNone(result.value)
                self.assertEqual(budget.spool_bytes, 32)

    def test_large_mean_avoids_area_overflow(self):
        """有效数值1e308按先归一化权重保持有限。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            owner, _ = self.owner(backend=backend, size=1, window=Interval(0, 3))
            for time in range(4):
                owner.consume((self.row(time, 1e308),))
            self.assertEqual(owner.finish().value, 1e308)

    def test_spool_quota_and_cleanup_retry(self):
        """超配额或清理取消都不发布前缀，关闭可重试。参数: 无。返回: None。异常: 断言失败。"""
        owner, budget = self.owner(size=1, window=Interval(0, 2))
        budget.spool_quota_bytes = 15
        with self.assertRaises(BudgetExceededError):
            owner.consume((self.row(0, 1.), self.row(1, 2.)))
        with self.assertRaises(ResultClosedError):
            owner.finish()
        with patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                owner.close()
        self.assertFalse(owner.closed)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_short_read_and_cancel_cannot_return_result(self):
        """必要回读被截短或预算预约后取消时拒绝交付。参数: 无。返回: None。异常: 断言失败。"""
        owner, budget = self.owner(size=1, window=Interval(0, 2))
        owner.consume((self.row(0, 1.), self.row(1, 2.)))
        owner._file.truncate(5)
        with self.assertRaisesRegex(ValueError, '不完整'):
            owner.finish()
        with self.assertRaises(ResultClosedError):
            owner.finish()
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)
        owner, budget = self.owner(size=1)
        reserve = budget.reserve_ram
        def cancel(amount):
            """在实际预约后取消。参数: bytes。返回: 无。异常: KeyboardInterrupt。"""
            reserve(amount)
            raise KeyboardInterrupt()
        with patch.object(budget, 'reserve_ram', side_effect=cancel):
            with self.assertRaises(KeyboardInterrupt):
                owner.consume((self.row(0, 1.), self.row(120_000_000, 2.)))
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_long_stream_has_fixed_peak_ram(self):
        """文件按实际必要项增长，RAM不随整窗记录数增长。参数: 无。返回: None。异常: 断言失败。"""
        peaks = []
        for count in (65, 257):
            owner, budget = self.owner(size=8, window=Interval(0, count-1))
            for time in range(count):
                owner.consume((self.row(time, 10.),))
            self.assertAlmostEqual(owner.finish().value, 10.)
            self.assertEqual(budget.spool_bytes, 16*(count-1))
            peaks.append(budget.peak_ram_bytes)
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)
        self.assertEqual(peaks[0], peaks[1])

    def test_constructor_and_file_close_failures_are_recoverable(self):
        """构造预算失败不泄漏，文件关闭失败不把结果当完成。参数: 无。返回: None。异常: 断言失败。"""
        budget = ResourceBudget(1)
        with self.assertRaises(BudgetExceededError):
            RecordTimeCalculation(budget, CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 2)),
                'W', D.FLOAT64, 100, work_dir=self.directory.name)
        self.assertEqual(budget.ram_bytes, 0)
        owner, budget = self.owner(size=1, window=Interval(0, 1))
        owner.consume((self.row(0, 1.), self.row(1, 2.)))
        file = owner._file
        with patch.object(file, 'close', side_effect=OSError('关闭失败')):
            with self.assertRaisesRegex(OSError, '关闭失败'):
                owner.finish()
            with self.assertRaises(ResultClosedError):
                owner.finish()
        owner.close()
        self.assertTrue(file.closed)
        self.assertEqual(budget.ram_bytes, 0)

    def test_corrupt_nonfinite_weight_or_trailing_record_fails(self):
        """必要回读的非法权重和多出内容不能生成看似有效的均值。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for weight in (float('nan'), -1., 0.):
                owner, budget = self.owner(backend=backend, size=1, window=Interval(0, 1))
                owner.consume((self.row(0, 1.), self.row(1, 2.)))
                owner._file.seek(0)
                owner._file.write(owner._codec.pack(1., weight))
                with self.assertRaisesRegex(ValueError, '有限数值和正权重'):
                    owner.finish()
                owner.close()
                self.assertEqual(budget.ram_bytes, 0)
            owner, _ = self.owner(backend=backend, size=1, window=Interval(0, 1))
            owner.consume((self.row(0, 1.), self.row(1, 2.)))
            owner._file.write(b'x')
            with self.assertRaisesRegex(ValueError, '未登记数据'):
                owner.finish()


if __name__ == '__main__':
    unittest.main()
