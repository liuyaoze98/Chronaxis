"""核稀疏CAN时间映射的真实消费点、完整观测、错误顺序及资源责任。

device_label: home。受控批只隔离时间算法，不冒充真实CAN读取或EOF；完整进程链另由
test_can_batch_history运行。错误与密集原循环比对，成功值再用独立Decimal真值核对。
测试不改旧读取/解码、不写文件；共享预算借款在每个用例结束后必须完整保留。
"""

import math
import random
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis.execution import can_batch_reader as module
from chronaxis.legacy.batch_wire import LegacyDecodedBatch
from chronaxis.sources.protocol import SourceReadError
from chronaxis.sources.can_updates import CANUpdateProjection
from chronaxis.timebase.conversion import INT64_MAX
import test_can_batch_time_checks as baseline
from test_legacy_batch_validation import message, original_record


def outcome(owner):
    """保存实际异常及已提交观测，不吞取消。参数: owner。返回: 状态元组。异常: BaseException。"""
    try:
        result = ('ok', module.CANBatchObservationRead._load_batch(owner))
    except Exception as error:
        result = ('error', type(error), str(error))
    return result, (owner._first_ns, owner._last_ns, owner._row_count)


class RecordingStore:
    """明确的测试消息仓，只记录消费字段和seal次数，不代表磁盘历史。"""

    def __init__(self):
        """建立空记录。参数: 无。返回: None。异常: 无。"""
        self.rows, self.seals = [], 0

    def append(self, record, mapped, *, time_quantized):
        """保存被消费的原序号与精确时间。参数: 记录/映射/量化标志。返回: None。异常: 分配错误。"""
        self.rows.append((record.sequence, mapped, time_quantized))

    def seal(self):
        """仅标记测试调用，不认证真实EOF。参数: 无。返回: None。异常: 无。"""
        self.seals += 1


class SparseCANTimeTests(unittest.TestCase):
    """所有稀疏批至少16原帧，覆盖首末证明、跨批状态和真实消费索引。"""

    def owner(self, values, offset=0):
        """复用原测试真实预算夹具。参数: 原时间/偏移。返回: owner。异常: 夹具或预算错误。"""
        return baseline.CANBatchTimeCheckTests.owner(self, values, offset)

    def release(self, owner):
        """复用原清账断言，确保不抵销共享借款。参数: owner。返回: None。异常: 余额断言失败。"""
        baseline.CANBatchTimeCheckTests.release(self, owner)

    def batch(self, values, positions=(), *, start=0):
        """建立完整原记录及全部原时间。参数: 时间/相对目标索引/原起点。返回: 批。异常: 模型错误。"""
        timestamps = tuple(values)
        records = tuple(original_record(message(timestamp=timestamps[index]), {}, start+index)
                        for index in positions)
        return LegacyDecodedBatch(start, timestamps, records)

    def with_records(self, values, positions=(), offset=0):
        """安装完整目标记录的可控进程。参数: 时间/索引/偏移。返回: owner。异常: 夹具错误。"""
        owner = self.owner(values, offset)
        owner._process = baseline.ControlledProcess([self.batch(values, positions)])
        return owner

    def dense_owner(self, values, offset=0):
        """仅对_load_batch强制原密集时间循环，不消费占位记录。参数: 时间/偏移。返回: owner。异常: 夹具错误。"""
        owner = self.owner(values, offset)
        # 这里没有记录消费；占位只选择原密集循环，使坏时间也可与原错误顺序比对。
        owner._process = baseline.ControlledProcess([LegacyDecodedBatch(0, tuple(values), (None,)*len(values))])
        return owner

    def test_sparse_4096_keeps_all_observations_and_consumed_quantization(self):
        """4096原帧只换算首末和80目标，所有实际消费值与原循环及独立真值一致。

        参数: 无。返回: None。异常: 计数、量化标志、原索引或预算差异使断言失败。
        """
        values = tuple(float(index)/123 for index in range(4096))
        positions = tuple(range(17, len(values), 51))
        old, new = self.dense_owner(values), self.with_records(values, positions)
        expected = outcome(old)
        with patch.object(module, '_float_seconds_ns', wraps=module._float_seconds_ns) as calls:
            self.assertEqual(outcome(new), expected)
        keep = {0, len(values)-1, *positions}
        self.assertEqual(calls.call_count, len(keep))
        self.assertEqual(len(new._mapped_times), len(values))
        for index, mapped in enumerate(new._mapped_times):
            self.assertEqual(mapped, old._mapped_times[index] if index in keep else None)
            if index in keep:
                self.assertEqual(mapped, baseline.decimal_reference(values[index]))
        self.assertEqual((old._process.calls, new._process.calls), (1, 1))
        self.assertEqual(old._record_cost, new._record_cost)

    def test_dense_and_short_batches_do_not_enter_sparse_helper(self):
        """密集、短批继续原循环，不增加每帧稀疏处理。参数: 无。返回: None。异常: 误入稀疏路径。"""
        for count, positions in ((128, tuple(range(128))), (15, ())):
            values = tuple(index/1024 for index in range(count))
            owner = self.with_records(values, positions)
            with patch.object(module, '_sparse_batch_times', side_effect=AssertionError('unexpected sparse path')):
                self.assertTrue(module.CANBatchObservationRead._load_batch(owner))
            self.assertEqual(owner._mapped_times, tuple(baseline.decimal_reference(value) for value in values))

    def test_business_errors_preserve_exact_error_and_original_prefix(self):
        """末点试算不抢报错，坏类型/非有限/倒退/偏移仍保原错误及实际前缀。

        参数: 无。返回: None。异常: 类别、文本或首末/计数不同使断言失败。
        """
        normal = [float(index) for index in range(32)]
        cases = [(tuple(normal[:-1]+[1e20]), INT64_MAX),
                 (tuple(normal[:-1]+[1e20]), 0),
                 (tuple(normal), INT64_MAX-2000000000),
                 (tuple(normal), True), (tuple(normal), None)]
        for invalid in (1, None, math.nan, math.inf, -math.inf, -1.0):
            values = normal.copy()
            values[11] = invalid
            cases.append((tuple(values), 0))
        for values, offset in cases:
            old, new = self.dense_owner(values, offset), self.owner(values, offset)
            self.assertEqual(outcome(new), outcome(old))
            self.assertEqual((old._process.calls, new._process.calls), (1, 1))
            self.assertIsNone(new._mapped_times)

    def test_tiny_float_regression_falls_back_and_accepts_same_nanosecond(self):
        """float略回退而量化同刻仍允许，不将证明门禁变成业务拒绝。参数: 无。返回: None。异常: 错误拒绝。"""
        values = tuple([.49e-9]*16+[.48e-9]*16)
        old, new = self.dense_owner(values, 11), self.owner(values, 11)
        self.assertEqual(outcome(new), outcome(old))
        self.assertEqual(new._mapped_times, old._mapped_times)
        self.assertTrue(all(value == (11, True) for value in new._mapped_times))

    def test_random_sorted_batches_match_decimal_at_every_retained_point(self):
        """固定随机正负/次正规/近int64边界的保留点对独立Decimal逐值核验。

        参数: 无。返回: None。异常: 单调证明、最近偶数舍入或量化标志错误。
        """
        generator = random.Random(611)
        seeds = [-1e-300, -5e-324, -0.0, 0.0, 5e-324, 1e-300, -1/1024, 1/1024]
        for _ in range(24):
            values = tuple(sorted(seeds+[generator.uniform(-9e9, 9e9) for _ in range(120)]))
            positions = (1, 25, 61, 100)
            offset = generator.randrange(-1000000000, 1000000000)
            old, new = self.dense_owner(values, offset), self.with_records(values, positions, offset)
            self.assertEqual(outcome(new), outcome(old))
            for index in (0, len(values)-1, *positions):
                ns, quantized = baseline.decimal_reference(values[index])
                self.assertEqual(new._mapped_times[index], (ns+offset, quantized))
                self.assertEqual(new._mapped_times[index], old._mapped_times[index])

    def test_sparse_cross_batch_equal_time_and_target_indices(self):
        """两个真正稀疏批跨界同刻，绝对原序号仍映射至各自正确位置。

        参数: 无。返回: None。异常: 跨批等时误拒、原计数/首末或目标映射变化。
        """
        first = tuple(index/1024 for index in range(32))
        second = tuple((31+index)/1024 for index in range(32))
        owner = self.owner(first, 9)
        owner._process = baseline.ControlledProcess([self.batch(first, (4, 31)),
            self.batch(second, (0, 19), start=32)])
        with patch.object(module, '_sparse_batch_times', wraps=module._sparse_batch_times) as calls:
            self.assertTrue(module.CANBatchObservationRead._load_batch(owner))
            first_last = owner._last_ns
            self.assertTrue(module.CANBatchObservationRead._load_batch(owner))
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(owner._mapped_times[0][0], first_last)
        for index in (0, 19, 31):
            ns, quantized = baseline.decimal_reference(second[index])
            self.assertEqual(owner._mapped_times[index], (ns+9, quantized))
        self.assertEqual((owner._first_ns, owner._last_ns, owner._row_count),
                         (9, baseline.decimal_reference(second[-1])[0]+9, 64))

    def test_sparse_cross_batch_backward_time_preserves_previous_observation(self):
        """跨批首条倒退在任何新计数前拒绝，前批观测完整保留。参数: 无。返回: None。异常: 误改前缀。"""
        first = tuple(float(index) for index in range(32))
        second = tuple(float(30+index) for index in range(32))
        owner = self.owner(first)
        owner._process = baseline.ControlledProcess([self.batch(first), self.batch(second, (8,), start=32)])
        self.assertTrue(module.CANBatchObservationRead._load_batch(owner))
        with self.assertRaisesRegex(SourceReadError, 'CAN原yield时间回退，禁止重排'):
            module.CANBatchObservationRead._load_batch(owner)
        self.assertEqual((owner._first_ns, owner._last_ns, owner._row_count), (0, 31000000000, 32))
        self.assertIsNone(owner._mapped_times)

    def test_empty_projection_to_target_consumes_exact_times_and_waits_for_true_eof(self):
        """前批无目标仍计观测，后批目标由真实_advance_record使用稀疏槽，真EOF才seal。

        参数: 无。返回: None。异常: 漏原帧、错目标位置、提前seal或未归还费用。
        """
        first = tuple(index/1024 for index in range(32))
        second = tuple((31+index)/1024 for index in range(32))
        owner = self.owner(first, 11)
        owner._process = baseline.ControlledProcess([self.batch(first), self.batch(second, (8, 19), start=32)])
        owner._load_batch = MethodType(module.CANBatchObservationRead._load_batch, owner)
        owner._deliver_message = MethodType(module.CANBatchObservationRead._deliver_message, owner)
        # 原fixture显式声明新接入层默认无直接消费者，原时间/序号/EOF断言保持。
        owner._owner = SimpleNamespace(message_frame_ids=None, _definitions=(),
                                       time_scope='source',_update_consumer=None,_frame_observer=None)
        owner._binding_projection = CANUpdateProjection('bus', 'session', ())
        owner._progress_ns = None
        store = owner._message_store = RecordingStore()
        for index in (8, 19):
            self.assertTrue(module.CANBatchObservationRead._advance_record(owner))
            ns, quantized = baseline.decimal_reference(second[index])
            self.assertEqual((owner._record.sequence, owner._mapped, owner._conversion), (32+index, ns+11, quantized))
        self.assertEqual(store.seals, 0)
        self.assertFalse(owner._input_ended)
        self.assertEqual(owner._row_count, 64)
        owner._process.finished = True
        self.assertFalse(module.CANBatchObservationRead._advance_record(owner))
        self.assertEqual((owner._process.calls, store.seals, owner._record_cost), (3, 1, 0))
        self.assertEqual(owner._budget.ram_bytes, 12345)
        self.assertEqual([row[0] for row in store.rows], [40, 51])

    def test_unfinished_process_cannot_seal_after_sparse_data(self):
        """批次数据已消费也不能将未完成进程的StopIteration当EOF。参数: 无。返回: None。异常: 虚假封口。"""
        owner = self.owner(tuple(float(index) for index in range(32)))
        store = owner._message_store = RecordingStore()
        self.assertTrue(module.CANBatchObservationRead._load_batch(owner))
        with self.assertRaisesRegex(SourceReadError, '未完成真实EOF'):
            module.CANBatchObservationRead._load_batch(owner)
        self.assertEqual(store.seals, 0)
        self.assertFalse(owner._input_ended)
        self.assertEqual(owner._row_count, 32)

    def test_noncanonical_retained_shape_falls_back_to_complete_mapping(self):
        """非典型保留对象不获稀疏证明，时间层沿原路径输出完整映射。参数: 无。返回: None。异常: 意外提前拒绝。"""
        values = tuple(float(index) for index in range(32))
        owner = self.owner(values)
        owner._process = baseline.ControlledProcess([LegacyDecodedBatch(0, values, (object(),))])
        self.assertTrue(module.CANBatchObservationRead._load_batch(owner))
        self.assertEqual(owner._mapped_times, tuple(baseline.decimal_reference(value) for value in values))

    def test_cancel_and_memory_failure_keep_original_exception_and_truthful_prefix(self):
        """预检或目标换算取消时保同一异常/首条前缀/实际费用，清除新辅助函数大引用。

        参数: 无。返回: None。异常: 吞异常、提交未完成批或退掉尚归owner承担的费用。
        """
        for error_type in (KeyboardInterrupt, MemoryError):
            for checkpoint in ('finite_scan', 'retained_conversion'):
                values = tuple(float(index) for index in range(32))
                owner = self.with_records(values, (8,))
                marker = error_type('sparse-time-home')
                original = module.isfinite if checkpoint == 'finite_scan' else module._float_seconds_ns

                def fail_at_eight(value):
                    """在确实执行的校验处触发原异常。参数: 原float。返回: 原结果。异常: marker。"""
                    if value == 8.0:
                        raise marker
                    return original(value)

                target = 'isfinite' if checkpoint == 'finite_scan' else '_float_seconds_ns'
                with patch.object(module, target, new=fail_at_eight):
                    with self.assertRaises(error_type) as caught:
                        module.CANBatchObservationRead._load_batch(owner)
                self.assertIs(caught.exception, marker)
                self.assertEqual((owner._first_ns, owner._last_ns, owner._row_count), (0, 0, 1))
                self.assertEqual(owner._process.calls, 1)
                self.assertFalse(owner._input_ended)
                self.assertIsNone(owner._mapped_times)
                self.assertGreater(owner._record_cost, 0)
                traceback = marker.__traceback__
                while traceback is not None:
                    if traceback.tb_frame.f_code.co_name == '_sparse_batch_times':
                        for name in ('owner', 'batch', 'timestamps', 'mapped_times', 'indices', 'sparse', 'result'):
                            self.assertIsNone(traceback.tb_frame.f_locals[name])
                    traceback = traceback.tb_next

    def test_reserve_committed_then_cancel_does_not_pull_sparse_input(self):
        """原预付回调实际记账后取消，仍由本owner清理且不先取原批。参数: 无。返回: None。异常: 费用/读取变化。"""
        owner = self.owner(tuple(float(index) for index in range(32)))
        marker = KeyboardInterrupt('sparse reserve after payment')
        reserve = owner._budget.reserve_ram

        def reserve_then_cancel(amount):
            """实际付款后触发指定取消。参数: 金额。返回: 不成功。异常: marker。"""
            reserve(amount)
            raise marker

        with patch.object(owner._budget, 'reserve_ram', new=reserve_then_cancel):
            with self.assertRaises(KeyboardInterrupt) as caught:
                module.CANBatchObservationRead._load_batch(owner)
        self.assertIs(caught.exception, marker)
        self.assertEqual((owner._process.calls, owner._row_count), (0, 0))
        self.assertGreater(owner._record_cost, 0)


if __name__ == '__main__':
    unittest.main()
