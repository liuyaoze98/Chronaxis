"""用手算边界和独立随机片段核对窗口变化量两个数值后端。

全部输入均为合成整数纳秒，不读取真实来源或历史项目；测试覆盖完整时间、
缺口、真实末点、方向/单调及定宽范围。随机对照不能代替显式手算断言。
"""

import random
import unittest
from chronaxis.core.types import QualityFlag as Q, SignalDType as D, Truth
from chronaxis.core.window_delta import DeltaSpan, WindowDeltaSpec
from chronaxis.core.window_delta_reference import window_delta_reference
from chronaxis.core.window_delta_numpy import window_delta_numpy


class WindowDeltaTests(unittest.TestCase):
    """两个后端使用同一输入；每项先检查完整结果相等，再核业务真值。"""

    def compare(self, spec, spans, time=4, dtype=D.INT64):
        """执行两个独立核。参数: 配置/片段/时刻/类型。返回: 参考结果。异常: 断言失败。"""
        reference = window_delta_reference(spec, spans, time, dtype)
        self.assertEqual(reference, window_delta_numpy(spec, spans, time, dtype))
        return reference

    def test_lc08_whole_window_monotonic(self):
        """0→10→5首尾差5但不单调。参数: 无。返回: None。异常: 断言失败。"""
        spans = (DeltaSpan(0, 2, 0), DeltaSpan(2, 4, 10), DeltaSpan(4, 5, 5))
        for monotonic, expected in ((False, Truth.TRUE), (True, Truth.FALSE)):
            result = self.compare(WindowDeltaSpec(4, 4, 'any', monotonic), spans)
            self.assertEqual((result.value, result.condition, result.monotonic), (5, expected, False))

    def test_directions_and_inclusive_threshold(self):
        """恰好阈值通过，rise/fall方向不混用。参数: 无。返回: None。异常: 断言失败。"""
        spans = (DeltaSpan(0, 4, 8), DeltaSpan(4, 5, 3))
        for direction, value, truth in (('rise', -5, Truth.FALSE), ('fall', 5, Truth.TRUE), ('any', 5, Truth.TRUE)):
            result = self.compare(WindowDeltaSpec(4, 5, direction, True), spans)
            self.assertEqual((result.value, result.condition), (value, truth))

    def test_boundary_zoh_not_first_observation(self):
        """窗口左端用保持值，不用窗内首个样本。参数: 无。返回: None。异常: 断言失败。"""
        spans = (DeltaSpan(0, 2, 1), DeltaSpan(2, 4, 5), DeltaSpan(4, 6, 8))
        result = self.compare(WindowDeltaSpec(3, 7), spans)
        self.assertEqual((result.window_start_ns, result.value, result.coverage), (1, 7, 1.0))

    def test_incomplete_window_unknown(self):
        """起始不足4ns仅覆盖3ns。参数: 无。返回: None。异常: 断言失败。"""
        result = self.compare(WindowDeltaSpec(4, 0), (DeltaSpan(1, 5, 10),))
        self.assertEqual((result.value, result.condition, result.coverage), (None, Truth.UNKNOWN, .75))

    def test_gap_and_invalid_update_unknown(self):
        """缺口与显式失效均打断完整窗。参数: 无。返回: None。异常: 断言失败。"""
        for spans in ((DeltaSpan(0, 1, 0), DeltaSpan(2, 5, 10)),
                      (DeltaSpan(0, 1, 0), DeltaSpan(1, 2, None, Q.DECODE_ERROR), DeltaSpan(2, 5, 10))):
            result = self.compare(WindowDeltaSpec(4, 5), spans)
            self.assertEqual((result.condition, result.valid_duration_ns), (Truth.UNKNOWN, 3))

    def test_ttl_expired_endpoint(self):
        """连续覆盖100%也不能忽略失效右端。参数: 无。返回: None。异常: 断言失败。"""
        result = self.compare(WindowDeltaSpec(4, 0),
                              (DeltaSpan(0, 4, 5), DeltaSpan(4, 6, None, Q.STALE)))
        self.assertEqual((result.condition, result.coverage), (Truth.UNKNOWN, 1.0))
        self.assertTrue(result.quality & Q.STALE)

    def test_actual_terminal_point(self):
        """真实EOF新值可参与端点差但不保持到以后。参数: 无。返回: None。异常: 断言失败。"""
        spans = (DeltaSpan(0, 4, 1), DeltaSpan(4, 4, 6, Q.MISSING, Q.NONE))
        result = self.compare(WindowDeltaSpec(4, 5, 'rise'), spans)
        self.assertEqual((result.value, result.condition), (5, Truth.TRUE))
        self.assertIs(self.compare(WindowDeltaSpec(4, 5), spans, 5).condition, Truth.UNKNOWN)

    def test_constant_and_repeated_values(self):
        """平台段允许非严格单调；零阈值可成立。参数: 无。返回: None。异常: 断言失败。"""
        for direction in ('rise', 'fall', 'any'):
            result = self.compare(WindowDeltaSpec(4, 0, direction, True), (DeltaSpan(0, 5, 3),))
            self.assertEqual((result.value, result.monotonic, result.condition), (0, True, Truth.TRUE))

    def test_large_integer_exactness(self):
        """超过2**53的大整数仍精确比较差值。参数: 无。返回: None。异常: 断言失败。"""
        result = self.compare(WindowDeltaSpec(4, 1),
                              (DeltaSpan(0, 4, 2**60), DeltaSpan(4, 5, 2**60 + 1)))
        self.assertEqual(result.value, 1)

    def test_integer_overflow_and_unsigned_underflow(self):
        """定宽差超限报告质量，不回绕。参数: 无。返回: None。异常: 断言失败。"""
        cases = ((D.INT64, -(2**63), 0, 'any'), (D.INT64, -(2**63), 2**63-1, 'rise'),
                 (D.UINT64, 10, 0, 'rise'), (D.UINT64, 0, 10, 'fall'))
        for dtype, first, last, direction in cases:
            result = self.compare(WindowDeltaSpec(4, 0, direction),
                                  (DeltaSpan(0, 4, first), DeltaSpan(4, 5, last)), dtype=dtype)
            self.assertEqual((result.quality, result.condition), (Q.OVERFLOW, Truth.UNKNOWN))
        result = self.compare(WindowDeltaSpec(4, 2**64-1),
                              (DeltaSpan(0, 4, 2**64-1), DeltaSpan(4, 5, 0)), dtype=D.UINT64)
        self.assertEqual((result.value, result.condition), (2**64-1, Truth.TRUE))

    def test_float_nonfinite_difference(self):
        """有限首尾的差仍可能溢出。参数: 无。返回: None。异常: 断言失败。"""
        result = self.compare(WindowDeltaSpec(4, 0),
                              (DeltaSpan(0, 4, -1e308), DeltaSpan(4, 5, 1e308)), dtype=D.FLOAT64)
        self.assertEqual(result.quality, Q.NONFINITE)

    def test_time_lower_limit_and_empty(self):
        """回看越过int64下限仍明确不足窗口。参数: 无。返回: None。异常: 断言失败。"""
        result = self.compare(WindowDeltaSpec(4, 0), (DeltaSpan(-(2**63), -(2**63)+2, 1),), -(2**63)+1)
        self.assertEqual((result.coverage, result.condition), (.25, Truth.UNKNOWN))
        self.assertEqual(self.compare(WindowDeltaSpec(4, 0), ()).coverage, 0.0)

    def test_input_contract_rejections(self):
        """拒绝重叠、bool、非法政策和数值类型。参数: 无。返回: None。异常: 断言失败。"""
        for kwargs in ({'window_ns': 0}, {'window_ns': True}, {'threshold': True},
                       {'threshold': float('nan')}, {'monotonic': 1}, {'coverage_policy': 'legacy_samples'}):
            with self.assertRaises((ValueError, TypeError)):
                WindowDeltaSpec(**({'window_ns': 4, 'threshold': 0} | kwargs))
        for spans, dtype in (((DeltaSpan(0, 5, 1), DeltaSpan(4, 6, 2)), D.INT64),
                             ((DeltaSpan(0, 5, 1.0),), D.INT64), ((DeltaSpan(0, 5, 1),), D.BOOL)):
            for kernel in (window_delta_reference, window_delta_numpy):
                with self.assertRaises((ValueError, TypeError)):
                    kernel(WindowDeltaSpec(4, 0), spans, 4, dtype)

    def test_randomized_backend_equivalence(self):
        """300组稀疏与失效片段对照三种方向。参数: 无。返回: None。异常: 断言失败。"""
        rng = random.Random(20261022)
        for _ in range(300):
            spans = tuple(DeltaSpan(i * 2, i * 2 + 2, rng.randint(-20, 20),
                                   Q.NONE if rng.random() > .1 else Q.STALE) for i in range(12))
            self.compare(WindowDeltaSpec(rng.randint(1, 15), rng.randint(0, 20),
                         rng.choice(('rise', 'fall', 'any')), rng.choice((True, False))),
                         spans, rng.randint(0, 24))


if __name__ == '__main__':
    # 单文件入口与unittest discover使用同一用例。
    unittest.main()
