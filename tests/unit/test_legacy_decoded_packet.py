"""验证专用decoded包正证明与原严格公共模型的字节、错误及引用责任等价。

device_label: home。用完整手写包、固定字段变体与原公开构造器作独立真值；
覆盖复杂回退、64KiB/ITEM/深度、JSON先于模型错误、可变解析树隔离与取消清理。
只使用有界合成输入，不运行CAN/进程或性能计时，不依赖work目录中的原型和数据。
"""

from copy import deepcopy
import gc
import itertools
import json
import unittest
from unittest.mock import patch
import weakref

from chronaxis.legacy import records, batch_wire, message_store
import test_legacy_checked_decode as baseline
from test_legacy_checked_decode import original_checked_builder, packet, wire

ORIGINAL_PARSE = records.decode_packet


def original_decode(payload):
    """用未改公共解析与原公开构造流程作独立真值。参数: bytes。返回: 原记录。异常: 原错误。"""
    return original_checked_builder(ORIGINAL_PARSE(payload))


def encoded(record):
    """按完整公开格式编码以比较全部字段。参数: 原记录。返回: bytes。异常: 原编码错误。"""
    return records.encode_packet(records.decoded_to_dict(record))


def outcome(operation, payload):
    """保精确错误类型和文本或完整字节。参数: 函数/bytes。返回: 对照tuple。异常: 取消不捕获。"""
    try:
        return ('bytes', encoded(operation(payload)))
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        return ('error', type(error), str(error))


class LegacyDecodedPacketTests(unittest.TestCase):
    """核单次解析正证明、精确回退、外壳错误先后及生命周期。"""

    def assert_same(self, payload):
        """比较未改公开模型oracle与专用入口。参数: payload。返回: None。异常: 差异断言。"""
        self.assertEqual(outcome(original_decode, payload), outcome(records._decoded_from_packet, payload))

    def assert_equivalent(self, payload):
        """让共享旧边界夹具比较新入口与独立公开oracle。参数: bytes。返回: 合法记录或None。异常: 差异。"""
        self.assert_same(payload)
        if outcome(original_decode, payload)[0] == 'error':
            return None
        return records._decoded_from_packet(payload)

    def test_original_complete_values_and_boolean_combinations(self):
        """复用原完整字段和128标志输入而不调用私有builder作真值。参数: 无。返回: None。异常: 断言。"""
        baseline.LegacyCheckedDecodeTests.test_full_values_and_all_boolean_combinations(self)

    def test_original_multiple_error_priority(self):
        """原单错/双错组合仍沿公开入口次序拒绝。参数: 无。返回: None。异常: 断言。"""
        baseline.LegacyCheckedDecodeTests.test_multiple_invalid_fields_preserve_original_error_priority(self)

    def test_original_wire_before_model_errors(self):
        """原UTF8、重复键、深度及裸非有限错误仍优先。参数: 无。返回: None。异常: 断言。"""
        baseline.LegacyCheckedDecodeTests.test_strict_wire_errors_remain_before_typed_builder(self)

    def test_original_exact_item_limit(self):
        """保ITEM外壳65535/65536接受与65537拒绝及原错误。参数: 无。返回: None。异常: 断言。"""
        baseline.LegacyCheckedDecodeTests.test_item_envelope_exact_64kib_boundary_and_error_order(self)

    def test_fallback_discards_first_frame_before_original_parser(self):
        """正证明False或普通错误后，进入原解析前第一份frame必须已经释放。

        参数: 无。返回: None。异常: 重复持有临时frame、非原错误或输出变化令断言失败。
        spy只保存弱引用，不依赖gc收集或结束整个调用后才观察释放事实。
        """
        for kind in ('unproved', 'ordinary_error'):
            source = packet()
            if kind == 'unproved':
                source['values'] = {'电流': 3.0}
            else:
                source['sequence'] = -1
            payload = wire(source)
            expected = outcome(original_decode, payload)
            references, fallback_calls = [], []
            original_frame = records.frame_from_dict

            def observed_frame(value):
                """保模型弱引用以核峰值责任。参数: 原树。返回: 原frame。异常: 原模型错误。"""
                frame = original_frame(value)
                references.append(weakref.ref(frame))
                return frame

            def fallback(value):
                """在第二次解析开始前核第一份frame已死。参数: bytes。返回: 原树。异常: 原解析错误。"""
                self.assertEqual(len(references), 1)
                self.assertIsNone(references[0]())
                fallback_calls.append(1)
                return ORIGINAL_PARSE(value)

            with self.subTest(kind=kind), patch.object(records, 'frame_from_dict', observed_frame), \
                    patch.object(records, 'decode_packet', fallback):
                self.assertEqual(outcome(records._decoded_from_packet, payload), expected)
            self.assertEqual(fallback_calls, [1])

    def test_batch_and_message_paths_use_same_complete_decoder(self):
        """实际批包与磁盘行接线均使用专用入口，全部字段与公共oracle相等。

        参数: 无。返回: None。异常: 接线未调用、完整字段变化或多解析令断言失败。
        """
        source = packet()
        inner = wire(source)
        expected = encoded(original_decode(inner))
        batch = batch_wire.encode_batch(7, [-0.0], [inner], False, batch_wire.MAX_BATCH_BYTES)
        header = records.encode_packet({'store_version': 1, 'time_ns': 19, 'time_quantized': True})
        stored = header[:-1] + b',"decoded":' + inner + b'}\n'
        with patch.object(batch_wire, '_decoded_from_packet', wraps=records._decoded_from_packet) as batched, \
                patch.object(message_store, '_decoded_from_packet', wraps=records._decoded_from_packet) as disk, \
                patch.object(records, 'decode_packet', side_effect=AssertionError('unexpected fallback')):
            decoded, eof = batch_wire.decode_batch(batch, expected_start=7, row_limit=4096,
                byte_limit=batch_wire.MAX_BATCH_BYTES, frame_ids=(428,))
            row = message_store._decode_row(stored)
        self.assertEqual((batched.call_count, disk.call_count), (1, 1))
        self.assertFalse(eof)
        self.assertEqual((row.time_ns, row.time_quantized), (19, True))
        self.assertEqual(encoded(decoded.records[0]), expected)
        self.assertEqual(encoded(row.decoded), expected)

    def test_positive_record_uses_one_parse_and_one_frame_without_wire_walk(self):
        """128种原标志及完整有限值省树遍历，保持一次解析和一次原帧构造。

        参数: 无。返回: None。异常: 字节、调用次数或正证明覆盖失败。
        """
        flags = ('is_extended_id', 'is_remote_frame', 'is_error_frame', 'is_fd', 'is_rx',
                 'bitrate_switch', 'error_state_indicator')
        for bits in itertools.product((False, True), repeat=7):
            source = packet()
            source['frame'].update(zip(flags, bits))
            source['frame']['data_hex'] = 'ABCDEF00'
            source['values'] = {'f': -0.0, 'i': -(2**64 - 1), 'positive': 2**64 - 1,
                                'bool': False, 'small': 5e-324, 'large': 1.7976931348623157e308}
            payload = wire(source)
            expected = encoded(original_decode(payload))
            with patch.object(records.json, 'loads', wraps=json.loads) as parsed, \
                    patch.object(records, 'frame_from_dict', wraps=records.frame_from_dict) as frames, \
                    patch.object(records, 'decode_packet', side_effect=AssertionError('unexpected fallback')), \
                    patch.object(records, '_wire_tree', side_effect=AssertionError('extra tree')):
                actual = records._decoded_from_packet(payload)
                self.assertEqual((parsed.call_count, frames.call_count), (1, 1))
            self.assertEqual(encoded(actual), expected)

    def test_all_root_and_frame_fields_mutated_preserve_behavior(self):
        """逐个根和frame字段替换或删改，不凭格式猜测遗漏字段。

        参数: 无。返回: None。异常: 接受/错误文本或优先级变化时失败。
        """
        source = packet()
        paths = [(name,) for name in source] + [('frame', name) for name in source['frame']]
        variants = (None, False, 0, -1, 1.25, 'text', [], {}, {'diagnostic_float': 'nan'})
        for path in paths:
            for replacement in variants:
                current = deepcopy(source)
                target = current if len(path) == 1 else current[path[0]]
                target[path[-1]] = deepcopy(replacement)
                with self.subTest(path=path, value_type=type(replacement).__name__):
                    self.assert_same(wire(current))
            current = deepcopy(source)
            del (current if len(path) == 1 else current[path[0]])[path[-1]]
            self.assert_same(wire(current))
        for path in ((), ('frame',)):
            current = deepcopy(source)
            (current if not path else current[path[0]])['extra'] = 1
            self.assert_same(wire(current))

    def test_complex_values_reparse_through_original_entry(self):
        """Unicode、诊断和大整数不能用有限小包证明，须回原入口。

        参数: 无。返回: None。异常: 未回退或最终完整字节不同。
        """
        for values in ({'电流': 3.0}, {'x': 2**80}, {'x': {'diagnostic_float': 'nan'}},
                       {'x': {'diagnostic_float': 'inf'}}, {'x' * 11000: 1}):
            source = packet()
            source['values'] = values
            payload = wire(source)
            expected = encoded(original_decode(payload))
            with patch.object(records, 'decode_packet', wraps=ORIGINAL_PARSE) as fallback:
                actual = records._decoded_from_packet(payload)
                self.assertEqual(fallback.call_count, 1)
            self.assertEqual(encoded(actual), expected)

    def test_wire_errors_keep_priority_over_earlier_typed_frame_errors(self):
        """深度、孤立surrogate、未标记非有限及规范尺寸错误仍先于frame类型错误。

        参数: 无。返回: None。异常: 专用入口提前暴露模型错误或错误优先级变化。
        """
        nested = 0
        for _ in range(20):
            nested = {'n': nested}
        for values in ({'\ud800': 1}, {'x': nested}):
            source = packet()
            source['frame']['timestamp'] = 'bad'
            source['values'] = values
            self.assert_same(wire(source))
        source = packet()
        source['frame']['timestamp'] = 'bad'
        raw = wire(source).replace(b'"x":1', b'"x":1e999')
        self.assert_same(raw)
        # 5000个短指数输入仍在bytes界内，但规范float文本会显著增长；不得只看原bytes。
        raw_values = b','.join(('"k%d":1e9' % index).encode('ascii') for index in range(5000))
        raw = wire(packet()).replace(b'"x":1', raw_values)
        self.assertLessEqual(len(raw), records.MAX_WIRE_BYTES)
        self.assert_same(raw)
        self.assertEqual(outcome(original_decode, raw)[0], 'error')

    def test_actual_bytes_limits_and_parser_failures_preserve_original_errors(self):
        """bytes边界、重复键、裸常量、UTF8、超长整数和尾随内容均沿原拒绝。

        参数: 无。返回: None。异常: 原错误变化或越界数据绕过入口。
        """
        valid = wire(packet())
        padded = valid + b' ' * (records.MAX_WIRE_BYTES - len(valid))
        for payload in (None, bytearray(valid), b'', b'\xff', b'[]', b'null',
                        b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
                        b'{"sequence":' + b'1' * 5001 + b'}', valid + b'{}', padded, padded + b' '):
            with self.subTest(kind=type(payload).__name__, prefix=str(payload)[:20]):
                self.assert_same(payload)

    def test_result_does_not_borrow_any_captured_parse_dictionary(self):
        """即使诊断工具保留parsed树，事后更改也不能影响输出模型。

        参数: 无。返回: None。异常: 可变树别名影响结果或冻结失效。
        """
        loads, captured = json.loads, []

        def observe(*args, **kwargs):
            """仅保解析结果以检查别名。参数: 原loads参数。返回: 原dict。异常: 原解析错。"""
            parsed = loads(*args, **kwargs)
            captured.append(parsed)
            return parsed

        with patch.object(records.json, 'loads', observe):
            result = records._decoded_from_packet(wire(packet()))
        before = encoded(result)
        captured[0]['values']['x'] = 900
        captured[0]['frame']['timestamp'] = 2.0
        captured[0]['frame']['data_hex'] = 'ff'
        self.assertEqual(encoded(result), before)
        with self.assertRaises(TypeError):
            result.values['x'] = 5

    def test_cancel_and_memory_failure_do_not_reparse_or_retain_new_frame(self):
        """解析、正证明与冻结阶段失败不fallback，原异常和已释临时引用均保真。

        参数: 无。返回: None。异常: 吞取消、二次解析或持TB保活新模型时失败。
        """
        for location in ('parse', 'proof', 'freeze'):
            for exception_type in (KeyboardInterrupt, SystemExit, MemoryError):
                marker = exception_type('packet-proof-failure-home')
                captured = []
                original_frame = records.frame_from_dict

                def frame_copy(value):
                    """保存真实frame弱引用。参数: 原字典。返回: 原frame。异常: 原模型错误。"""
                    frame = original_frame(value)
                    captured.append(weakref.ref(frame))
                    return frame

                owner, attribute = ((records.json, 'loads') if location == 'parse' else
                    (records, '_small_item_fits') if location == 'proof' else (records, 'MappingProxyType'))
                caught = None
                with patch.object(owner, attribute, side_effect=marker), \
                        patch.object(records, 'frame_from_dict', frame_copy), \
                        patch.object(records, 'decode_packet', side_effect=AssertionError('unexpected fallback')):
                    try:
                        records._decoded_from_packet(wire(packet()))
                    except BaseException as error:
                        caught = error
                self.assertIs(caught, marker)
                gc.collect()
                self.assertTrue(all(reference() is None for reference in captured))
                trace = marker.__traceback__
                while trace is not None:
                    if trace.tb_frame.f_globals.get('__name__') == records.__name__:
                        for name in ('payload', 'parsed', 'raw_values', 'values', 'frame', 'result'):
                            self.assertIsNone(trace.tb_frame.f_locals.get(name), name)
                    trace = trace.tb_next
