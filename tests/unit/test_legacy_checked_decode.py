"""用未改公开构造器核对同次严格JSON解包的私有构建，覆盖值、错误顺序和清理。

device_label: home。输入全为有限合成JSON bytes；旧实现oracle直接重现原私有函数
调用公开LegacyDecodedFrame的流程，不调用新的checked builder。正常结果按完整
公开编码比较；错误比较原异常类型和文本；所有边界测试不计时、不启动CAN或进程。
"""

from configuration_fixtures import current_fixture

from copy import deepcopy
import gc
import itertools
import json
import math
import unittest
from unittest.mock import patch
import weakref

from chronaxis.legacy import records
from chronaxis.legacy.batch_wire import MAX_BATCH_BYTES, decode_batch, encode_batch


def packet():
    """创建字段完整的原wire字典。参数: 无。返回: 新dict。异常: 分配错误传播。"""
    return {'sequence': 7, 'frame': {
        'timestamp': -0.0, 'arbitration_id': 428, 'is_extended_id': False,
        'is_remote_frame': False, 'is_error_frame': False, 'channel': 0, 'dlc': 8,
        'data_hex': '00010203040506ab', 'is_fd': False, 'is_rx': True,
        'bitrate_switch': False, 'error_state_indicator': False}, 'values': {'x': 1}}


def wire(value):
    """只用标准库编码合成输入，允许以JSON转义表达坏Unicode。

    参数: value为原生JSON树。返回: bytes，大小不由被测代码决定。
    异常: 标准库编码或分配错误；非有限值须由夹具显式使用原diagnostic标签。
    """
    return json.dumps(current_fixture(value), ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf-8')


def original_checked_builder(value):
    """保持修改前私有函数的形状检查和公开构造路径，充当独立行为oracle。

    参数: value为同次decode_packet返回的原生dict。返回: 原LegacyDecodedFrame。
    异常: 原形状/frame/值/序号/ITEM上限错误按旧顺序传播；不调用私有新构建函数。
    """
    records._shape(value, ('sequence', 'frame', 'values'), 'decoded frame')
    if type(value['values']) is not dict:
        raise TypeError('decoded values需要dict')
    return records.LegacyDecodedFrame(value['sequence'], records.frame_from_dict(value['frame']),
        {name: records._value_from_wire(item) for name, item in value['values'].items()})


class ChangingMapping(records.Mapping):
    """首次迭代合法、第二次变成坏值，证明公开构造器仍防御调用方可变Mapping。"""

    def __init__(self):
        """初始化遍历计数。参数: 无。返回: 新对象。异常: 无。"""
        self.visits = 0

    def __getitem__(self, key):
        """读取有限测试值。参数: key为原键。返回: 1。异常: 非x键抛KeyError。"""
        if key != 'x':
            raise KeyError(key)
        return 1

    def __iter__(self):
        """返回唯一原键。参数: 无。返回: iterator。异常: 无。"""
        return iter(('x',))

    def __len__(self):
        """保持单项容器。参数: 无。返回: 1。异常: 无。"""
        return 1

    def items(self):
        """在两次检查间更改值。参数: 无。返回: 一项tuple。异常: 无。"""
        self.visits += 1
        return (('x', 1 if self.visits == 1 else 'changed'),)


class LegacyCheckedDecodeTests(unittest.TestCase):
    """对照相同严格入口后两个独立构建路径，原公开模型是业务校验基线。"""

    def assert_equivalent(self, payload):
        """比较原结果完整字节或原异常的准确类型及文本。

        参数: payload为有限合法/非法wire bytes。返回: 新模型或None。
        异常: 接受/拒绝、错误优先级或完整输出变化时断言失败。
        """
        try:
            expected = original_checked_builder(records.decode_packet(payload))
        except (TypeError, ValueError, OverflowError) as error:
            with self.assertRaises(type(error)) as caught:
                records._decoded_from_checked_dict(records.decode_packet(payload))
            self.assertEqual(str(caught.exception), str(error))
            return None
        actual = records._decoded_from_checked_dict(records.decode_packet(payload))
        self.assertIs(type(actual), records.LegacyDecodedFrame)
        self.assertEqual(records.encode_packet(records.decoded_to_dict(actual)),
                         records.encode_packet(records.decoded_to_dict(expected)))
        return actual

    def test_full_values_and_all_boolean_combinations(self):
        """完整值、Unicode、负零、非有限标签和128种帧标志与旧构造完全一致。

        参数: 无。返回: None。异常: 丢值、改字段或编码不一致使断言失败。
        """
        names = ('is_extended_id', 'is_remote_frame', 'is_error_frame', 'is_fd',
                 'is_rx', 'bitrate_switch', 'error_state_indicator')
        for flags in itertools.product((False, True), repeat=7):
            value = packet()
            value['frame'].update(zip(names, flags))
            value['frame']['channel'] = '电\n"\\😀'
            value['frame']['data_hex'] = value['frame']['data_hex'].upper()
            value['values'] = {'零': 0, 'false': False, 'true': True, 'n': -0.0,
                'large': 2**2048, 'nan': {'diagnostic_float': 'nan'},
                'inf': {'diagnostic_float': 'inf'}, '-inf': {'diagnostic_float': '-inf'}}
            with self.subTest(flags=flags):
                actual = self.assert_equivalent(wire(value))
                self.assertTrue(math.isnan(actual.values['nan']))
                self.assertEqual(actual.frame.timestamp.hex(), '-0x0.0p+0')

    def test_multiple_invalid_fields_preserve_original_error_priority(self):
        """单错和双错组合按原优先级拒绝，不因合并循环先报另一字段。

        参数: 无。返回: None。异常: 异常类型/文本变化或坏记录通过使断言失败。
        """
        changes = ((('sequence',), False), (('sequence',), -1),
            (('frame', 'timestamp'), 1), (('frame', 'arbitration_id'), False),
            (('frame', 'dlc'), 65), (('frame', 'channel'), False),
            (('frame', 'data_hex'), 'xz'), (('frame', 'is_fd'), 0),
            (('values',), []), (('values',), {'x': 'invalid'}),
            (('values',), {'': 1}), (('values',), {'x': {'diagnostic_float': 'bad'}}),
            (('values',), {'x': {'diagnostic_float': 'nan', 'extra': 1}}))
        for length in (1, 2):
            for variants in itertools.combinations(changes, length):
                value = packet()
                for path, replacement in variants:
                    target = value if len(path) == 1 else value[path[0]]
                    target[path[-1]] = deepcopy(replacement)
                with self.subTest(variants=variants):
                    self.assertIsNone(self.assert_equivalent(wire(value)))

    def test_strict_wire_errors_remain_before_typed_builder(self):
        """UTF8、重复键、裸非有限数、深度及根结构仍由真正严格JSON入口拒绝。

        参数: 无。返回: None。异常: wire错误被构建路径绕过时断言失败。
        """
        value = packet()
        value['values'] = {'\ud800': 0}
        nested = {'x': 0}
        for _ in range(18):
            nested = {'x': nested}
        payloads = (b'\xff', b'{"x":1,"x":2}', b'{"x":NaN}', b'[]',
                    wire(nested), wire(value), b'{"x":"' + b'a'*65536 + b'"}')
        for payload in payloads:
            with self.subTest(prefix=payload[:32]):
                self.assertIsNone(self.assert_equivalent(payload))

    def test_item_envelope_exact_64kib_boundary_and_error_order(self):
        """record包合法仍必须包含ITEM外壳计长，65535/65536通过、65537拒绝。

        参数: 无。返回: None。异常: 漏掉外壳或改变先遇到的坏名称错误时断言失败。
        """
        for prefix in ('x', '电😀', '"\\\n'):
            value = packet()
            value['values'] = {prefix: 0}
            envelope = {'op': 'item', 'request_id': 7, 'record': value}
            base = len(json.dumps(current_fixture(envelope), ensure_ascii=False, allow_nan=False,
                                 sort_keys=True, separators=(',', ':')).encode('utf-8'))
            for delta in (-1, 0, 1):
                changed = deepcopy(value)
                changed['values'] = {prefix + 'a'*(65536-base+delta): 0}
                # 此处使用原UTF8格式；ASCII转义会扩大Unicode，改变要验证的精确字节边界。
                payload = json.dumps(current_fixture(changed), ensure_ascii=False, allow_nan=False,
                                     separators=(',', ':')).encode('utf-8')
                self.assertLessEqual(len(payload), records.MAX_WIRE_BYTES)
                with self.subTest(prefix=prefix, delta=delta):
                    actual = self.assert_equivalent(payload)
                    self.assertEqual(actual is None, delta > 0)
            # 边界附近同时放坏名称，继续按原逐项检查先后而非提前只看整个包长度。
            changed['values'] = {'': 0, **changed['values']}
            self.assertIsNone(self.assert_equivalent(json.dumps(current_fixture(changed), ensure_ascii=False,
                allow_nan=False, separators=(',', ':')).encode('utf-8')))

    def test_frozen_values_and_frame_do_not_borrow_mutable_parsed_tree(self):
        """新返回模型不借原parsed树的容器，调用方后续改树不能改已校验记录。

        参数: 无。返回: None。异常: 变更传播或values可写使断言失败。
        """
        source = records.decode_packet(wire(packet()))
        result = records._decoded_from_checked_dict(source)
        before = records.encode_packet(records.decoded_to_dict(result))
        source['values']['x'] = 999
        source['frame']['data_hex'] = 'ff'
        source['frame']['timestamp'] = 1.0
        self.assertEqual(records.encode_packet(records.decoded_to_dict(result)), before)
        with self.assertRaises(TypeError):
            result.values['x'] = 2

    def test_public_constructor_still_checks_changing_mapping_twice(self):
        """外部可变Mapping仍须两遍完整检查，私有优化不能削弱公开防御。

        参数: 无。返回: None。异常: 公开构造器接受第二遍坏值时断言失败。
        """
        values = ChangingMapping()
        with self.assertRaisesRegex(TypeError, '解码wire值仅支持数值或bool'):
            records.LegacyDecodedFrame(7, records.frame_from_dict(packet()['frame']), values)
        self.assertEqual(values.visits, 2)

    def test_batch_checks_one_strict_tree_and_one_private_values_pass(self):
        """含非有限诊断的复杂记录仍严格解包一次，再精确核值；公开oracle核值两遍。

        参数: 无。返回: None。异常: 原JSON或值检查被跳过/仍重复、批次内容变化则失败。
        """
        value = packet()
        value['values'] = {'x': 0, 'flag': False, 'invalid': {'diagnostic_float': 'nan'}}
        original_tree, original_entry = records._wire_tree, records._decoded_entry_size
        counts = {'strict_trees': 0, 'entries': 0}

        def observed_tree(item, depth=0, remaining=records.MAX_WIRE_BYTES):
            """透明记录完整decoded树检查。参数: 原树/深度/余额。返回: 原长度。异常: 原错。"""
            if depth == 0 and type(item) is dict and set(item) == {'sequence', 'frame', 'values'}:
                counts['strict_trees'] += 1
            return original_tree(item, depth, remaining)

        def observed_entry(name, item, remaining):
            """透明记录每项原值边界。参数: 原名称/数值/余额。返回: 原长度。异常: 原错。"""
            counts['entries'] += 1
            return original_entry(name, item, remaining)

        payload = encode_batch(7, [-0.0], [wire(value)], False, MAX_BATCH_BYTES)
        with patch.object(records, '_wire_tree', new=observed_tree), \
                patch.object(records, '_decoded_entry_size', new=observed_entry):
            batch, eof = decode_batch(payload, expected_start=7, row_limit=1,
                                      byte_limit=MAX_BATCH_BYTES, frame_ids=None)
        self.assertFalse(eof)
        self.assertEqual(counts, {'strict_trees': 1, 'entries': 3})
        counts.update(strict_trees=0, entries=0)
        with patch.object(records, '_wire_tree', new=observed_tree), \
                patch.object(records, '_decoded_entry_size', new=observed_entry):
            expected = original_checked_builder(records.decode_packet(wire(value)))
        self.assertEqual(counts, {'strict_trees': 1, 'entries': 6})
        self.assertEqual(records.encode_packet(records.decoded_to_dict(batch.records[0])),
                         records.encode_packet(records.decoded_to_dict(expected)))

    def test_cancellation_does_not_retain_new_frame_in_builder_traceback(self):
        """正证明、精确回退或冻结失败，保存原异常也不能额外挂住本次新原帧。

        参数: 无。返回: None。异常: 取消被包装、帧仍保活或公开输入被改时断言失败。
        """
        original = records.frame_from_dict
        for checkpoint in ('_small_item_fits', '_decoded_values_size', 'MappingProxyType'):
            for failure_type in (KeyboardInterrupt, MemoryError):
                frames = []
                marker = failure_type('checked-builder-cancel-home')
                source = packet()
                if checkpoint == '_decoded_values_size':
                    source['values'] = {'复杂键': 1}

                def capture(value):
                    """仅记录新帧弱引用。参数: 原frame字典。返回: 原typed帧。异常: 原构造错。"""
                    frame = original(value)
                    frames.append(weakref.ref(frame))
                    return frame

                with self.subTest(checkpoint=checkpoint, failure=failure_type.__name__), \
                        patch.object(records, 'frame_from_dict', capture), \
                        patch.object(records, checkpoint, side_effect=marker):
                    try:
                        records._decoded_from_checked_dict(records.decode_packet(wire(source)))
                    except (KeyboardInterrupt, MemoryError) as error:
                        self.assertIs(error, marker)
                    else:
                        self.fail('预检或冻结失败未传播')
                gc.collect()
                self.assertEqual(len(frames), 1)
                self.assertIsNone(frames[0]())

    def test_small_items_preserve_values_without_exact_size_walks(self):
        """正证明覆盖常见完整值及边界序号，省精确计长仍保公开模型的完整输出。

        参数: 无。返回: None。异常: 多做精确遍历或输出变化时断言失败。
        """
        for sequence in (0, 2**64 - 1):
            for channel in (None, 0, -(2**64 - 1), 2**64 - 1, 'x\n\\"'):
                source = packet()
                source['sequence'], source['frame']['channel'] = sequence, channel
                source['values'] = {'i': -(2**64 - 1), 'p': 2**64 - 1,
                    'f': 1.7976931348623157e308, 'z': -0.0, 's': 5e-324, 'b': False}
                parsed = records.decode_packet(wire(source))
                expected = original_checked_builder(parsed)
                with patch.object(records, '_wire_tree', side_effect=AssertionError('额外ITEM树')), \
                        patch.object(records, '_decoded_values_size', side_effect=AssertionError('额外值计长')):
                    actual = records._decoded_from_checked_dict(parsed)
                self.assertEqual(records.encode_packet(records.decoded_to_dict(actual)),
                                 records.encode_packet(records.decoded_to_dict(expected)))

    def test_complex_items_fall_back_to_original_exact_size_check(self):
        """不能正证明时保留原精确校验；Unicode、大整数或保守界不足都不能直接拒绝。

        参数: 无。返回: None。异常: 未执行完整回退或公开输出改变时断言失败。
        """
        cases = []
        for values in ({'中文': 1}, {'x': {'diagnostic_float': 'nan'}}, {'x': 2**65},
                       {'x' * 11000: 1}, {str(index): index for index in range(1800)}):
            source = packet()
            source['values'] = values
            cases.append(source)
        for channel in ('通道', 2**65):
            source = packet()
            source['frame']['channel'] = channel
            cases.append(source)
        source = packet()
        source['sequence'] = 2**65
        cases.append(source)
        for source in cases:
            parsed = records.decode_packet(wire(source))
            expected = original_checked_builder(parsed)
            with patch.object(records, '_decoded_values_size', wraps=records._decoded_values_size) as exact:
                actual = records._decoded_from_checked_dict(parsed)
                self.assertEqual(exact.call_count, 1)
            self.assertEqual(records.encode_packet(records.decoded_to_dict(actual)),
                             records.encode_packet(records.decoded_to_dict(expected)))

    def test_frame_and_sequence_errors_precede_positive_proof(self):
        """坏frame或负序号仍在正证明之前拒绝，不因快路改变原错误位置。

        参数: 无。返回: None。异常: 证明被提前调用或错误改变时断言失败。
        """
        invalid_frame, invalid_sequence = packet(), packet()
        invalid_frame['frame']['timestamp'] = 'bad'
        invalid_sequence['sequence'] = -1
        for source in (invalid_frame, invalid_sequence):
            parsed = records.decode_packet(wire(source))
            with patch.object(records, '_small_item_fits', side_effect=AssertionError('提前证明')):
                with self.assertRaises(ValueError):
                    records._decoded_from_checked_dict(parsed)


if __name__ == '__main__':
    unittest.main()
