"""对照公开原帧模型检查原生CAN未选记录的合并校验与worker接线。

使用真实can.Message模型和明确的内存旧链/连接替身，不读取日志或DBC，不开进程。
既有原编码边界测试在原生消息上重跑，补多处同时非法字段、data转换顺序、类型回退、
异常引用及真实worker的原调用次数/STOP/失败清理；原reader与decoder不被改写。
"""

from configuration_fixtures import current_fixture

from can import Message
import json
import math
import random
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis.legacy import batch_validation, batch_worker, worker
from chronaxis.legacy.batch_wire import BATCH_MAGIC, MIN_BATCH_BYTES
from chronaxis.legacy.records import decode_packet
import test_legacy_batch_validation as baseline
import test_legacy_can_batch_worker_limits as worker_baseline

_synthetic_message = baseline.message
_original_validate = batch_validation.validate_discarded


def native_message(**changes):
    """建立真实Message并保留待测非法字段，不让构造器修正夹具。

    参数: changes覆盖原字段。返回: 原生Message。异常: 原字段赋值错误。
    """
    msg = Message()
    for name, value in vars(_synthetic_message(**changes)).items():
        setattr(msg, name, value)
    return msg


def native_validate(msg, values, sequence):
    """按worker实际调用方式传入真实Message类。参数: 原消息/值/序号。返回: None。异常: 原错误。"""
    return _original_validate(msg, values, sequence, native_message_type=Message)


def outcome(function, msg, values, sequence):
    """保留精确成功或异常类型与文本。参数: 函数和输入。返回: 元组。异常: BaseException。"""
    try:
        return ('ok', function(msg, values, sequence))
    except Exception as exc:
        return ('error', type(exc), str(exc))


class ChangedData:
    """转换时修改消息字段的合成载荷，用于验证旧快照顺序及扩张后拒绝。"""

    def __init__(self, msg, change, size):
        """保存消息、字段变化和输出字节数。参数: 三者。返回: 新夹具。异常: 无。"""
        self.msg, self.change, self.size = msg, change, size

    def __len__(self):
        """使转换前长度合法。参数: 无。返回: 0。异常: 无。"""
        return 0

    def __bytes__(self):
        """转换时修改已读或未读字段。参数: 无。返回: bytes。异常: 原字段或分配错误。"""
        for name, value in self.change.items():
            setattr(self.msg, name, value)
        return bytes(self.size)


class MessageSubclass(Message):
    """只有类型变化的消息子类，必须保留原模型检查路径。"""


class CountedDict(dict):
    """计数自定义字典的读取回调，确认候选上界不会多观察一遍非原生容器。"""

    def __init__(self):
        """建立单项字典和计数。参数: 无。返回: 新字典。异常: 分配错误。"""
        super().__init__(x=1)
        self.lengths = self.iterations = 0

    def __len__(self):
        """记录原容器长度回调。参数: 无。返回: 原长度。异常: 原错误。"""
        self.lengths += 1
        return super().__len__()

    def items(self):
        """记录完整值观察。参数: 无。返回: 原视图。异常: 原错误。"""
        self.iterations += 1
        return super().items()


class TrapName(str):
    """被原规则禁止的名称子类，其真假回调不应被新增候选检查触发。"""

    def __bool__(self):
        """暴露多余用户代码执行。参数: 无。返回: 不返回。异常: AssertionError。"""
        raise AssertionError('非法名称不应触发自定义真假回调')


class NativeOriginalChain(worker_baseline.ControlledOriginalChain):
    """明确的内存旧链替身，仅将既有计数夹具换成真实Message模型。"""

    can = SimpleNamespace(Message=Message)

    def __next__(self):
        """保留原序和真实EOF计数。参数: 无。返回: 原生消息。异常: StopIteration。"""
        sequence = self.next_calls
        self.next_calls += 1
        if sequence >= self.count:
            raise StopIteration
        return native_message(timestamp=float(sequence), arbitration_id=256)

    def parse_frame(self, msg, db):
        """每条真实消息只计一次解码。参数: 消息/db。返回: 完整原值。异常: 身份断言失败。"""
        assert db is self.db
        self.parse_calls += 1
        self.parsed_sequences.append(int(msg.timestamp))
        return self.values


class NativeBatchValidationTests(baseline.LegacyBatchValidationTests):
    """在真实Message上重复原模型/编码真值，另核合并校验专有边界。"""

    def setUp(self):
        """只替换既有测试的消息构建和待测入口，保留原模型真值。

        参数: 无。返回: None。异常: patch初始化错误；已建立patch由addCleanup恢复。
        """
        for target, name, value in ((baseline, 'message', native_message),
                (baseline, 'validate_discarded', native_validate)):
            handle = patch.object(target, name, new=value)
            handle.start()
            self.addCleanup(handle.stop)

    def test_multiple_bad_fields_preserve_exact_exception_priority(self):
        """多个字段、序号和values同时非法时仍报告原路径的首个错误。

        参数: 无。返回: None。异常: 类型、文本或接受边界变化令断言失败。
        """
        changes = ({}, {'is_rx': None}, {'timestamp': 1}, {'timestamp': float('nan')}, {'arbitration_id': False},
            {'arbitration_id': 0x20000000}, {'dlc': -1}, {'data': bytes(65)}, {'data': None},
            {'channel': False}, {'channel': '\ud800'}, {'channel': 'a' * 65537},
            *({name: 0} for name in baseline._BOOL_FIELDS))
        for first in changes:
            for second in changes:
                for sequence in (0, -1, False):
                    for values in ({}, None, {'': 0}, {'x': []}):
                        combined = dict(first, **second)
                        expected = outcome(_original_validate, native_message(**combined), values, sequence)
                        actual = outcome(native_validate, native_message(**combined), values, sequence)
                        self.assertEqual(actual, expected)

    def test_bytes_conversion_preserves_snapshot_order_and_size_check(self):
        """data转换对字段的副作用仍按原快照顺序观察，转换后超64字节也拒绝。

        参数: 无。返回: None。异常: 提前校验、漏复制或观察时机改变令断言失败。
        """
        for change in ({'timestamp': 1}, {'channel': False}, {'is_rx': 0}, {'dlc': 65},
                {'is_extended_id': 0}):
            for size in (0, 65):
                old_msg, new_msg = native_message(), native_message()
                old_msg.data = ChangedData(old_msg, change, size)
                new_msg.data = ChangedData(new_msg, change, size)
                self.assertEqual(outcome(native_validate, new_msg, {}, 0),
                                 outcome(_original_validate, old_msg, {}, 0))

    def test_only_exact_message_type_skips_the_original_frame_model(self):
        """精确类型才省模型；替身、子类及默认入口仍调用原_frame。

        参数: 无。返回: None。异常: 类型回退、完整值遍历或路径次数不符。
        """
        subclass = MessageSubclass()
        for name, value in vars(_synthetic_message()).items():
            setattr(subclass, name, value)
        with patch.object(batch_validation, '_frame', wraps=worker._frame) as original_frame:
            native_validate(native_message(), {'x': 0}, 0)
            self.assertEqual(original_frame.call_count, 0)
            native_validate(subclass, {'x': 0}, 0)
            native_validate(_synthetic_message(), {'x': 0}, 0)
            _original_validate(native_message(), {'x': 0}, 0)
            self.assertEqual(original_frame.call_count, 3)

    def test_failed_native_validation_drops_frame_and_value_references(self):
        """保留异常后，新辅助帧不继续持有原消息、完整值或payload快照。

        参数: 无。返回: None。异常: 新辅助函数traceback中残留大对象令断言失败。
        """
        try:
            native_validate(native_message(), {'x': []}, 0)
        except TypeError as exc:
            trace = exc.__traceback__
            visited = False
            while trace is not None:
                if trace.tb_frame.f_code.co_name == '_validate_native_frame':
                    visited = True
                    for name in ('msg', 'values', 'data', 'channel', 'name', 'value'):
                        self.assertIsNone(trace.tb_frame.f_locals[name])
                trace = trace.tb_next
            self.assertTrue(visited)
        else:
            self.fail('非法解码值必须失败')

    def test_positive_bound_covers_ascii_and_all_finite_float_exponents(self):
        """安全上界的正结论用原模型和真实JSON验证，覆盖最坏转义与全部有限指数。

        参数: 无。返回: None。异常: 上界接受坏输入、漏数值或实际ITEM超64KiB时失败。
        """
        generator = random.Random(20261018)
        channels = (None, 0, -(2**64-1), 2**64-1, '', '\n"\\\x00', '\x00' * 10000)
        for exponent in range(2047):
            bits = (generator.getrandbits(1) << 63) | (exponent << 52) | generator.getrandbits(52)
            value = struct.unpack('>d', bits.to_bytes(8, 'big'))[0]
            self.assertTrue(math.isfinite(value))
            # 期望来自独立JSON编码；不使用被测公式计算预期字节数。
            self.assertLessEqual(len(json.dumps(current_fixture(value), allow_nan=False)), 32)
            values = {chr(exponent % 128) + 'x': value, 'min': -(2**64-1),
                      'max': 2**64-1, 'false': False, 'zero': 0}
            sequence = (0, 2**64-1)[exponent % 2]
            channel = channels[exponent % len(channels)]
            msg = native_message(timestamp=value, channel=channel, arbitration_id=0x1fffffff,
                dlc=64, data=bytes(64), **dict.fromkeys(baseline._BOOL_FIELDS, False))
            self.assertTrue(batch_validation._small_item_fits(values, sequence, channel))
            payload = baseline.records.encode_packet(baseline.item_packet(msg, values, sequence))
            self.assertLessEqual(len(payload), 65536)
            native_validate(msg, values, sequence)

    def test_small_native_values_need_no_exact_scalar_or_value_sizing(self):
        """完整上界已证明时不编码或再遍历值；0与False也必须实际检查。

        参数: 无。返回: None。异常: 原精确路径被调用或合法常见值未接受。
        """
        with patch.object(batch_validation, '_scalar_size', side_effect=AssertionError('多余标量计长')), \
                patch.object(batch_validation, '_decoded_values_size', side_effect=AssertionError('多余值计长')):
            for values in ({}, {'x': 0}, {'x': False}, {'x': 1.25}, {'\n"\\\x00': -(2**64-1)}):
                native_validate(native_message(), values, 0)

    def test_unsupported_bound_keeps_original_errors_and_mapping_callbacks(self):
        """Unicode、非有限、大整数、近限额及坏值仍按原精确规则处理。

        参数: 无。返回: None。异常: 将门禁失败误当拒绝、改错误或增加自定义回调。
        """
        samples = ({'电压': 1}, {'x': float('nan')}, {'x': float('inf')}, {'x': 1 << 65},
            {'x': []}, {'': 1}, {'\ud800': 1}, {'x' * 65500: 0}, {1: 0}, {TrapName('x'): 1})
        for values in samples:
            self.assertFalse(batch_validation._small_item_fits(values, 0, 0))
            self.assertEqual(outcome(native_validate, native_message(), values, 0),
                             outcome(_original_validate, native_message(), values, 0))
        for sequence, channel in ((1 << 65, 0), (0, '电'), (0, '\ud800'), (0, 1 << 65)):
            self.assertFalse(batch_validation._small_item_fits({}, sequence, channel))
            self.assertEqual(outcome(native_validate, native_message(channel=channel), {}, sequence),
                             outcome(_original_validate, native_message(channel=channel), {}, sequence))
        custom = CountedDict()
        native_validate(native_message(), custom, 0)
        self.assertEqual((custom.lengths, custom.iterations), (1, 1))

    def test_cancel_and_memory_error_keep_original_exception_and_clear_new_locals(self):
        """在正证明内部或精确回退取消/分配失败，不吞错，也不在新栈帧挂住输入。

        参数: 无。返回: None。异常: 原异常被替换、清理未做或新大引用保留时失败。
        """
        for failure_type in (KeyboardInterrupt, MemoryError):
            for checkpoint in ('bound', 'fallback'):
                marker = failure_type('native-bound-failure-home')
                calls = 0

                def finite_or_fail(value):
                    """在共享上界的首次值检查中失败。参数: float。返回: 原有限性。异常: 指定原异常。"""
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        raise marker
                    return math.isfinite(value)

                target_module = baseline.records if checkpoint == 'bound' else batch_validation
                target = 'isfinite' if checkpoint == 'bound' else '_decoded_values_size'
                replacement = finite_or_fail if checkpoint == 'bound' else marker
                values = {'x': 1.25} if checkpoint == 'bound' else {'电压': 1.25}
                with self.subTest(failure=failure_type.__name__, checkpoint=checkpoint), \
                        patch.object(target_module, target, side_effect=replacement):
                    try:
                        native_validate(native_message(), values, 0)
                    except BaseException as error:
                        self.assertIs(error, marker)
                        trace = error.__traceback__
                        visited = set()
                        while trace is not None:
                            name = trace.tb_frame.f_code.co_name
                            if name in ('_small_item_fits', '_validate_native_frame'):
                                visited.add(name)
                                for local in ('values', 'channel', 'name', 'value'):
                                    self.assertIsNone(trace.tb_frame.f_locals[local])
                            trace = trace.tb_next
                        self.assertIn('_validate_native_frame', visited)
                        if checkpoint == 'bound':
                            self.assertIn('_small_item_fits', visited)
                    else:
                        self.fail('原异常被吞掉')


class NativeBatchWorkerTests(unittest.TestCase):
    """执行实际worker循环，核原生快路、未选坏值、STOP和错误清理。"""

    def run_worker(self, count, values, commands, *, error=False):
        """复用已审计的有限连接夹具，仅把原消息类型换成真实Message。

        参数: 原条数/原值/许可脚本和预期错误。返回: 链、连接及快路次数。异常: 验证失败。
        """
        with patch.object(worker_baseline, 'ControlledOriginalChain', NativeOriginalChain), \
                patch.object(batch_validation, '_validate_native_frame',
                    wraps=batch_validation._validate_native_frame) as validate:
            chain, connection = worker_baseline.LegacyBatchWorkerLimitTests().run_worker(
                count, values, commands, error=error)
        return chain, connection, validate.call_count

    def test_worker_selects_native_validation_only_for_unselected_frames(self):
        """真实worker在parse之后按投影选择快路，保留记录仍走原模型。

        参数: 无。返回: None。异常: 路径或原next/parse次数不符。
        """
        for selected, expected_fast in (([], 3), (None, 0), ([256], 0)):
            commands = [(worker_baseline.pull(0, ids=selected), 0, 0)]
            chain, connection, calls = self.run_worker(3, {'x': 0}, commands)
            self.assertEqual(calls, expected_fast)
            self.assertEqual((chain.next_calls, chain.parse_calls), (4, 3))
            self.assertEqual(chain.parsed_sequences, [0, 1, 2])
            self.assertTrue(any(payload.startswith(BATCH_MAGIC) for payload, _, _ in connection.sent))

    def test_worker_reports_unselected_invalid_values_and_closes_resources(self):
        """真实快路遇到坏值或超长记录仍失败发送错误，不读取后续帧且完成收尾。

        参数: 无。返回: None。异常: 错误、原调用数或关闭事实不符。
        """
        for values, error_type in (({'x': []}, 'TypeError'), ({'x' * 65536: 0}, 'ValueError')):
            chain, connection, calls = self.run_worker(2, values,
                [(worker_baseline.pull(0, ids=[]), 0, 0)], error=True)
            self.assertEqual(calls, 1)
            self.assertEqual((chain.next_calls, chain.parse_calls, chain.close_calls), (1, 1, 1))
            self.assertTrue(connection.closed)
            self.assertFalse(any(payload.startswith(BATCH_MAGIC) for payload, _, _ in connection.sent))
            packet = decode_packet(connection.sent[-1][0])
            self.assertEqual((packet['phase'], packet['error']['type']), ('batch', error_type))

    def test_stop_after_native_batch_does_not_read_or_parse_ahead(self):
        """一批许可结束后STOP只关闭已有链，未选记录也不会后台继续读。

        参数: 无。返回: None。异常: STOP时多next/parse或关闭错误。
        """
        command = worker_baseline.pull(0, size=MIN_BATCH_BYTES, ids=[])
        command['rows'] = 1
        chain, connection, calls = self.run_worker(2, {'x': 0},
            [(command, 0, 0), ({'op': 'stop'}, 1, 1)])
        self.assertEqual((calls, chain.next_calls, chain.parse_calls, chain.close_calls), (1, 1, 1, 1))
        self.assertTrue(connection.closed)

    def test_worker_cancel_and_memory_failure_close_without_reading_ahead(self):
        """正证明期间取消或分配失败，实际worker报告原类型并关闭，不再推进原链。

        参数: 无。返回: None。异常: 原错误类型、next/parse次数或收尾事实不符。
        """
        for failure_type in (KeyboardInterrupt, MemoryError):
            with self.subTest(failure=failure_type.__name__), \
                    patch.object(batch_validation, '_small_item_fits',
                        side_effect=failure_type('native-worker-bound-home')):
                chain, connection, calls = self.run_worker(2, {'x': 1.25},
                    [(worker_baseline.pull(0, ids=[]), 0, 0)], error=True)
            self.assertEqual((calls, chain.next_calls, chain.parse_calls, chain.close_calls), (1, 1, 1, 1))
            self.assertTrue(connection.closed)
            self.assertFalse(any(payload.startswith(BATCH_MAGIC) for payload, _, _ in connection.sent))
            packet = decode_packet(connection.sent[-1][0])
            self.assertEqual((packet['phase'], packet['error']['type']), ('batch', failure_type.__name__))


if __name__ == '__main__':
    unittest.main()
