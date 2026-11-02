"""核新CAN批时间快路径与原Decimal换算、公开int64加法的严格等价。

device_label: home。随机输入来自固定种子的原始float64位模式，期望值使用独立
Decimal精确展开和最近偶数舍入。批入口使用明确的受控测试owner，仅隔离时间
算法和实际预算事务，不冒充完整来源、真实EOF或性能验收；真实CAN生命周期另跑
既有test_can_batch_history。无文件、旧模块或外部资源副作用。
"""

from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import math
import random
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from chronaxis.execution import can_batch_reader as module
from chronaxis.execution.can_batch_reader import CANBatchObservationRead, _float_seconds_ns
from chronaxis.legacy.batch_wire import LegacyDecodedBatch
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.protocol import SourceReadError
from chronaxis.timebase.conversion import (INT64_MIN, INT64_MAX, TimeOverflowError,
    checked_add_ns, convert_time, require_int64_ns)


def decimal_reference(value):
    """用独立Decimal算法复现原float入口的结果和错误。参数: 原float。返回: ns/量化。异常: 原类别和文本。"""
    if type(value) is not float:
        raise TypeError('原CAN时间需要float')
    if not math.isfinite(value):
        raise ValueError('原CAN时间必须有限')
    # float64的精确十进制展开最多1074位量级，1200位可覆盖乘十亿的全部有效位。
    with localcontext() as context:
        context.prec = 1200
        raw = Decimal.from_float(value) * Decimal(1000000000)
        rounded = raw.to_integral_value(rounding=ROUND_HALF_EVEN)
    return require_int64_ns(int(rounded)), raw != rounded


class ControlledProcess:
    """明确的测试批迭代器，只记录next次数，不代表真实CAN进程或EOF证明。"""

    def __init__(self, batches):
        """保存有限测试批。参数: batches。返回: 测试迭代器。异常: 无。"""
        self.batches, self.calls, self.finished = iter(batches), 0, False

    def __next__(self):
        """交付下一测试批并计调用，不伪造finished。参数: 无。返回: 批。异常: 原StopIteration。"""
        self.calls += 1
        return next(self.batches)


class CANBatchTimeCheckTests(unittest.TestCase):
    """单行失败和批次部分推进均保原异常及账本责任，结束核共享借款未被抵销。"""

    def owner(self, values, offset=0, *, next_values=None):
        """建立无外部资源的明确测试owner。参数: 时间/偏移/可选下一批。返回: owner。异常: 夹具错误。"""
        budget = ResourceBudget(16 * 1024 ** 2)
        budget.reserve_ram(12345)
        batches = [LegacyDecodedBatch(0, tuple(values), ())]
        if next_values is not None:
            batches.append(LegacyDecodedBatch(len(values), tuple(next_values), ()))
        value = SimpleNamespace(_record=None, _incoming=None, _mapped_times=None, _record_cost=0,
            _held_cost=0, _budget=budget, _process=ControlledProcess(batches), _spec=SimpleNamespace(offset_ns=offset),
            _row_count=0, _first_ns=None, _last_ns=None, _raw_store=None, _message_store=None,
            _input_ended=False, _incoming_index=0, _owner=SimpleNamespace(time_scope='source'),
            _retained_record_count=0, _full_check_count=0)
        self.addCleanup(self.release, value)
        return value

    def release(self, owner):
        """仅释放受控owner实际费用并核借款。参数: owner。返回: None。异常: 重复抵销/漏账断言失败。"""
        module._release_owned_ram(owner, owner._record_cost, '_record_cost')
        self.assertEqual(owner._held_cost, 0)
        self.assertEqual(owner._budget.ram_bytes, 12345)
        owner._budget.release_ram(12345)

    def assert_float_matches(self, value):
        """将实际结果或严格错误与Decimal独立结果比对。参数: value。返回: None。异常: 断言失败。"""
        try:
            expected = decimal_reference(value)
        except (ValueError, TypeError, TimeOverflowError) as expected_error:
            with self.assertRaises(type(expected_error)) as actual:
                _float_seconds_ns(value)
            self.assertEqual(str(actual.exception), str(expected_error))
        else:
            actual = _float_seconds_ns(value)
            self.assertEqual(actual, expected)
            self.assertIs(type(actual[0]), int)
            original = convert_time(value, 's')
            self.assertEqual(actual, (original.time_ns, original.quantized))

    def test_all_exponents_random_bits_and_int64_neighbors(self):
        """覆盖全部float64指数、随机符号尾数、次正规和int64边界邻点。参数: 无。返回: None。异常: 断言失败。"""
        rng = random.Random(20261018)
        values = [0.0, -0.0, 5e-324, -5e-324, math.inf, -math.inf, math.nan,
            1 / 1024, -1 / 1024, 3 / 1024, -3 / 1024]
        for edge in (INT64_MIN / 1e9, INT64_MAX / 1e9):
            values.extend((edge, math.nextafter(edge, math.inf), math.nextafter(edge, -math.inf)))
        for exponent in range(2048):
            bits = (rng.getrandbits(1) << 63) | (exponent << 52) | rng.getrandbits(52)
            values.append(struct.unpack('>d', struct.pack('>Q', bits))[0])
        values.extend(struct.unpack('>d', struct.pack('>Q', rng.getrandbits(64)))[0] for _ in range(2048))
        for value in values:
            self.assert_float_matches(value)

    def test_strict_float_type_and_half_even_rounding(self):
        """原生float限制保持，精确半纳秒值对称取偶。参数: 无。返回: None。异常: 断言失败。"""
        for value in (True, False, 1, '1', Decimal('1'), np.float64(1), None):
            self.assert_float_matches(value)
        # 1/1024秒乘十亿恰为976562.5ns，3/1024对应2929687.5ns。
        for value, expected in ((1/1024, 976562), (3/1024, 2929688),
                (-1/1024, -976562), (-3/1024, -2929688)):
            self.assertEqual(_float_seconds_ns(value), (expected, True))

    def test_offset_types_boundaries_and_error_priority_match_public_add(self):
        """直接批入口拒绝坏偏移，原时间溢出不得由偏移抵消，报错先后与原链一致。参数: 无。返回: None。异常: 断言失败。"""
        offsets = (0, 1, -1, INT64_MIN, INT64_MAX, np.int64(-7), np.uint64(8),
            True, 0.0, '0', None, INT64_MAX + 1, INT64_MIN - 1, np.uint64(2**64 - 1))
        for timestamp in (0.0, 1.0, -1.0, 1e20, -1e20, math.nan, 1):
            for offset in offsets:
                owner = self.owner((timestamp,), offset)
                try:
                    ns, quantized = decimal_reference(timestamp)
                    expected = checked_add_ns(ns, offset)
                except (ValueError, TypeError, TimeOverflowError) as expected_error:
                    with self.assertRaises(type(expected_error)) as actual:
                        CANBatchObservationRead._load_batch(owner)
                    self.assertEqual(str(actual.exception), str(expected_error))
                    self.assertEqual(owner._row_count, 0)
                else:
                    self.assertTrue(CANBatchObservationRead._load_batch(owner))
                    self.assertEqual(owner._mapped_times, ((expected, quantized),))
                    self.assertIs(type(owner._last_ns), int)

    def test_once_per_batch_offset_validation_and_empty_batch_behavior(self):
        """非空批只核一次偏移，跨批重新核；空批保持原来不读取偏移的行为。参数: 无。返回: None。异常: 断言失败。"""
        values = (-0.0, 0.0, 1/1024, 3/1024, 1.0)
        owner = self.owner(values, np.int64(7), next_values=(2.0, 2.0))
        with patch.object(module, 'require_int64_ns', wraps=require_int64_ns) as validate:
            CANBatchObservationRead._load_batch(owner)
            self.assertEqual(validate.call_count, 1)
            self.assertEqual(owner._mapped_times,
                tuple((checked_add_ns(decimal_reference(value)[0], 7), decimal_reference(value)[1]) for value in values))
            CANBatchObservationRead._load_batch(owner)
            self.assertEqual(validate.call_count, 2)
        empty = self.owner((), object())
        with patch.object(module, 'require_int64_ns', side_effect=AssertionError('empty checked offset')):
            self.assertTrue(CANBatchObservationRead._load_batch(empty))
        self.assertEqual((empty._row_count, empty._mapped_times, empty._first_ns), (0, (), None))

    def test_quantized_same_time_and_cross_batch_backward_order(self):
        """原float略回退但量化同刻仍允许，映射后倒退跨批仍拒绝。参数: 无。返回: None。异常: 断言失败。"""
        first, second = 0.00000000049, 0.00000000048
        owner = self.owner((first, second), 11, next_values=(-1.0,))
        CANBatchObservationRead._load_batch(owner)
        self.assertEqual(owner._mapped_times, ((11, True), (11, True)))
        with self.assertRaisesRegex(SourceReadError, 'CAN原yield时间回退，禁止重排'):
            CANBatchObservationRead._load_batch(owner)
        self.assertEqual((owner._first_ns, owner._last_ns, owner._row_count), (11, 11, 2))

    def test_cancellation_after_reserve_and_during_conversion_keep_actual_fees(self):
        """预算更新后及第二帧换算取消保同一异常、已完成计数和实际费用。参数: 无。返回: None。异常: 断言失败。"""
        owner = self.owner((0.0, 1.0))
        primary = KeyboardInterrupt('test reserve after commit')
        original_reserve = owner._budget.reserve_ram
        def cancel_reserve(amount):
            """真实预付后取消。参数: amount。返回: 不成功。异常: 同一primary。"""
            original_reserve(amount)
            raise primary
        with patch.object(owner._budget, 'reserve_ram', new=cancel_reserve):
            with self.assertRaises(KeyboardInterrupt) as caught:
                CANBatchObservationRead._load_batch(owner)
        self.assertIs(caught.exception, primary)
        self.assertEqual(owner._process.calls, 0)
        self.assertGreater(owner._record_cost, 0)
        other = self.owner((0.0, 1.0))
        primary = KeyboardInterrupt('test second time conversion')
        def cancel_second(value):
            """第一帧真实转换、第二帧取消。参数: float。返回: 原结果。异常: primary。"""
            if value == 1.0:
                raise primary
            return _float_seconds_ns(value)
        with patch.object(module, '_float_seconds_ns', new=cancel_second):
            with self.assertRaises(KeyboardInterrupt) as caught:
                CANBatchObservationRead._load_batch(other)
        self.assertIs(caught.exception, primary)
        self.assertEqual((other._row_count, other._last_ns), (1, 0))
        self.assertGreater(other._record_cost, 0)


if __name__ == '__main__':
    unittest.main()
