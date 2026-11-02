"""验证CAN完整引用在内部叶子codec与历史v3中的精确往返及版本隔离。

输入是手构的冻结CANSourceRef、结果行和HistorySample，以及明确损坏的JSONL。
输出是原浮点秒、量化事实、int64大时间、UINT64值和同刻原序的独立断言。
测试调用真实编码/解码器，逐项检查v3固定引用tuple，不通过丢弃CAN附加字段获得
表面相等；基础SourceRef历史v1和CSVSourceRef历史v2继续使用原格式。模型编码不
证明BLF/DBC已读、时间映射已核或实际分析完成，不创建来源、工作目录或子进程。
"""

from configuration_fixtures import current_fixture

# 测试仅处理有限合成对象和内存JSON，所有原定位均不访问真实文件。
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.selection import SelectionRow
from chronaxis.core.temporal import Event, TemporalRule
from chronaxis.core.types import QualityFlag as Q, SignalDType as D, Truth
from chronaxis.core.windows import Segment, WindowSpec
from chronaxis.execution.history_records import HistoryProgress, HistorySample, decode_record, encode_record
from chronaxis.legacy.records import LegacyCANField, PROFILE_ID
from chronaxis.results import ResultFormatError
from chronaxis.results.codec import _pack, _unpack, _estimate
from chronaxis.sources.can_spec import CANSourceRef
from chronaxis.sources.csv_spec import CSVSourceRef


LARGE_TIME = 2**63 - 8
LARGE_SEQUENCE = 2**53 + 3
MAX_BYTES = 65536


def can_reference(*, sequence=LARGE_SEQUENCE, timestamp=1.0000000004, quantized=True):
    """建立完整原名CAN引用，不根据编码位置猜测时间或DBC字段。

    参数: sequence为原yield序号；timestamp为原生有限float秒；quantized为原bool事实。
    返回: CANSourceRef，原消息/信号名称含点号和中文。异常: 原模型校验错误传播。
    """
    locator = LegacyCANField(0, 'Signal.原值', 0x321, False, True)
    return CANSourceRef('session', 'source_can', locator.key, '合成/input.BLF', PROFILE_ID,
        0, 'Signal.原值', 0x321, False, True, sequence, timestamp, quantized)


def history_sample(reference, *, sequence=LARGE_SEQUENCE, time_ns=LARGE_TIME):
    """把明确UINT64原值与原引用放入真实历史记录，不执行归一化。

    参数: reference为typed来源；sequence/time_ns为保精度的整数事实。
    返回: HistorySample，物理值、逻辑值及原诊断均为2**64-1。
    异常: 被测历史或标量模型校验原样传播；不生成I/O或预算所有者。
    """
    return HistorySample(3, 'value', time_ns, sequence, 2**64 - 1,
        ScalarValue(2**64 - 1, D.UINT64), '1', reference, True, 2**64 - 1)


def core_values(references):
    """为同一有序引用tuple构造事件、部分片段和原值选择三种结果行。

    参数: references为非空typed来源tuple，顺序由调用者指定。
    返回: 三行tuple，窗口及数值均为明确合成事实。异常: 核心模型错误传播。
    """
    # 所有坐标处于int64内，短窗口不因端点很大而经float损失1ns。
    event = Event('event', TemporalRule('rule', 'dataset', 'session', 'condition_duration', 2),
        'activity', LARGE_TIME, LARGE_TIME + 2, LARGE_TIME + 2, 'closed', 'condition_duration',
        Q.NONE, Q.NONE, references)
    segment = Segment('segment', 'dataset', 'session', WindowSpec('window', 'rule', 'activity'),
        Interval(LARGE_TIME, LARGE_TIME + 4), Interval(LARGE_TIME, LARGE_TIME + 2), .5,
        'partial', ('event',), ('closed',), Q.NONE, references)
    selected = SelectionRow(LARGE_TIME + 1, ScalarValue(2**64 - 1, D.UINT64), Truth.TRUE,
        Q.NONE, 'binding', references, '1')
    return event, segment, selected


def json_line(tree):
    """生成有限JSONL负例的原生bytes，不调用被测编码器修正损坏结构。

    参数: tree为测试自行变异的JSON树。返回: 带单个换行的UTF8 bytes。
    异常: JSON或UTF8编码错误原样传播，不接受裸非有限数。
    """
    return (json.dumps(current_fixture(tree), ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')


def changed_line(tree, keys, value):
    """只变更指定wire叶值，保持其他合法字段以命中对应拒绝分支。

    参数: tree为合法原JSON树；keys为已有容器路径；value为替换叶值。
    返回: 独立JSONL bytes。异常: 错误路径直接抛出，避免负例因夹具错误假通过。
    """
    copy = deepcopy(tree)
    current = copy
    for key in keys[:-1]:
        current = current[key]
    current[keys[-1]] = value
    return json_line(copy)


class CANHistoryTests(unittest.TestCase):
    """真实编解码不得改原引用；坏版本和类型必须失败，不降级成基础定位。

    全部数据量有限、没有外部资源；负例修改合法wire的一个明确位置，结果只检查
    FormatError合同，不依赖实现的异常措辞或把手造记录当作来源完成证明。
    """

    def test_internal_value_codec_preserves_full_can_refs_in_core_models(self):
        """三类结果完整保两个原序引用、原float和量化标志，容器仍冻结。

        参数: 无。返回: None。异常: 字段丢失、序号取整或任何文件访问使测试失败。
        """
        references = (can_reference(), can_reference(sequence=LARGE_SEQUENCE + 1, timestamp=-0.0, quantized=False))
        # 显式阻断文件动作；结果模型和codec不能为恢复来源再次读BLF/DBC。
        with patch('builtins.open', side_effect=AssertionError('codec不得打开输入')), \
                patch.object(Path, 'open', side_effect=AssertionError('codec不得打开路径')):
            for row in core_values(references):
                with self.subTest(row=type(row).__name__):
                    payload = json_line(_pack(row))
                    decoded = _unpack(json.loads(payload))
                    self.assertEqual(decoded, row)
                    self.assertEqual(json_line(_pack(decoded)), payload)
                    self.assertGreater(16 * _estimate(row) + 8192, len(payload))
                    body = decoded
                    actual = body.source_refs
                    self.assertEqual(type(actual), tuple)
                    self.assertEqual(tuple(type(ref) for ref in actual), (CANSourceRef, CANSourceRef))
                    self.assertEqual([ref.yield_sequence for ref in actual], [2**53 + 3, 2**53 + 4])
                    self.assertEqual((actual[0].signal, actual[0].frame_id), ('Signal.原值', 0x321))
                    self.assertEqual((actual[0].path, actual[0].profile, actual[0].channel), ('合成/input.BLF', PROFILE_ID, 0))
                    self.assertEqual((actual[0].is_extended, actual[0].is_fd), (False, True))
                    self.assertIs(type(actual[0].timestamp), float)
                    self.assertEqual(actual[0].timestamp.hex(), (1.0000000004).hex())
                    self.assertEqual(math.copysign(1., actual[1].timestamp), -1.)
                    self.assertEqual([ref.time_quantized for ref in actual], [True, False])
                    with self.assertRaises(FrozenInstanceError):
                        actual[0].path = 'changed.BLF'
        # 大端点、部分覆盖、选择UINT64均用手给事实另核，不能只有自往返相等。
        event, segment, selected = (_unpack(_pack(row)) for row in core_values(references))
        self.assertEqual((event.start_ns, event.end_ns), (2**63 - 8, 2**63 - 6))
        self.assertEqual(segment.requested, Interval(2**63 - 8, 2**63 - 4))
        self.assertEqual(segment.actual, Interval(2**63 - 8, 2**63 - 6))
        self.assertEqual((segment.requested_coverage, segment.parent_event_ids), (.5, ('event',)))
        self.assertEqual((selected.time_ns, selected.value.value), (2**63 - 7, 2**64 - 1))

    def test_history_v3_uses_fixed_tuple_and_preserves_same_time_original_order(self):
        """当前v3保存12项必要定位，同刻两原序与大时间均无float转换。

        参数: 无。返回: None。异常: 版本、wire形状、精度或顺序不符则失败。
        """
        references = (can_reference(), can_reference(sequence=LARGE_SEQUENCE + 1, timestamp=-0.0, quantized=False))
        samples = tuple(history_sample(ref, sequence=ref.yield_sequence) for ref in references)
        decoded = []
        for index, sample in enumerate(samples):
            payload = encode_record(sample, MAX_BYTES)
            packed = json.loads(payload)
            self.assertEqual(set(packed), {'history_version', 'record_type', 'values'})
            self.assertEqual((packed['history_version'], packed['record_type']), (3, 'sample'))
            self.assertEqual(set(packed['values']), {'tuple'})
            values = packed['values']['tuple']
            self.assertEqual(len(values), 10)
            self.assertEqual((values[0], values[1], values[2], values[3], values[4]),
                             (3, 'value', 2**63 - 8, 2**53 + 3 + index, 2**64 - 1))
            self.assertEqual(set(values[7]), {'tuple'})
            raw = values[7]['tuple']
            self.assertEqual(len(raw), 12)
            self.assertEqual(raw[:2], ['can_source_ref', {'model': 'SourceRef', 'fields':
                {'session_id': 'session', 'source_name': 'source_can', 'field': references[index].field}}])
            self.assertEqual(raw[2:10], ['合成/input.BLF', PROFILE_ID, 0,
                'Signal.原值', 0x321, False, True, 2**53 + 3 + index])
            self.assertIs(type(raw[10]), float)
            self.assertIs(type(raw[11]), bool)
            restored = decode_record(payload, MAX_BYTES)
            self.assertEqual(restored, sample)
            self.assertIs(type(restored.source_ref), CANSourceRef)
            self.assertEqual(encode_record(restored, MAX_BYTES), payload)
            decoded.append(restored)
        self.assertEqual([row.time_ns for row in decoded], [2**63 - 8, 2**63 - 8])
        self.assertEqual([row.sequence for row in decoded], [2**53 + 3, 2**53 + 4])
        self.assertEqual(decoded[0].source_ref.timestamp.hex(), (1.0000000004).hex())
        self.assertEqual(math.copysign(1., decoded[1].source_ref.timestamp), -1.)
        self.assertEqual([row.source_ref.time_quantized for row in decoded], [True, False])

    def test_basic_v1_csv_v2_and_progress_formats_remain_compatible(self):
        """CAN新增登记不改变基础v1、CSV v2和进度v1的原字段及结果格式。

        参数: 无。返回: None。异常: 版本升级外溢或附加定位丢失使测试失败。
        """
        base = SourceRef('session', 'source_can', 'raw.value')
        csv = CSVSourceRef('session', 'table', 'raw.value', '合成/input.csv', 7,
                           '9007199254740993', '18446744073709551615', True)
        for reference, version in ((base, 1), (csv, 2)):
            with self.subTest(reference=type(reference).__name__):
                sample = history_sample(reference)
                payload = encode_record(sample, MAX_BYTES)
                packed = json.loads(payload)
                self.assertEqual(packed['history_version'], version)
                self.assertEqual(decode_record(payload, MAX_BYTES), sample)
                raw = packed['values']['tuple'][7]
                if version == 1:
                    self.assertEqual(raw, {'model': 'SourceRef', 'fields':
                        {'session_id': 'session', 'source_name': 'source_can', 'field': 'raw.value'}})
                else:
                    self.assertEqual(len(raw['tuple']), 7)
                    self.assertEqual(raw['tuple'][0], 'csv_source_ref')
                    self.assertEqual(raw['tuple'][2:], ['合成/input.csv', 7,
                        '9007199254740993', '18446744073709551615', True])
                row = core_values((reference,))[2]
                self.assertEqual(_unpack(_pack(row)), row)
        progress = HistoryProgress(3, 'source_can', 'session', 0, LARGE_TIME, True, LARGE_TIME)
        payload = encode_record(progress, MAX_BYTES)
        self.assertEqual(json.loads(payload)['history_version'], 1)
        self.assertEqual(decode_record(payload, MAX_BYTES), progress)

    def test_internal_registry_rejects_unregistered_same_name_and_invalid_can_wire(self):
        """内部值登记按真实类型封闭，CAN模型的错误标签/形状/native类型不能加载。

        参数: 无。返回: None。异常: 任意伪类、坏版本或错误定位被接受则失败。
        """
        reference = can_reference()
        packed = _pack(core_values((reference,))[0])
        ref_path = ('fields', 'source_refs', 'tuple', 0)
        field_path = ref_path + ('fields',)
        cases = [(ref_path + ('model',), 'ArbitraryModel'), (field_path + ('channel',), False),
            (field_path + ('frame_id',), True), (field_path + ('is_extended',), 0),
            (field_path + ('is_fd',), 1), (field_path + ('yield_sequence',), True),
            (field_path + ('yield_sequence',), float(2**53)), (field_path + ('timestamp',), 1),
            (field_path + ('timestamp',), {'diagnostic_float': 'inf'}),
            (field_path + ('time_quantized',), 1), (field_path + ('profile',), 'other-profile'),
            (field_path + ('signal',), 'different-from-key'), (field_path + ('extra',), 0)]
        for keys, value in cases:
            with self.subTest(keys=keys, value=value), self.assertRaises((ResultFormatError, TypeError, ValueError)):
                _unpack(json.loads(changed_line(packed, keys, value)))
        missing = deepcopy(packed)
        del missing['fields']['source_refs']['tuple'][0]['fields']['path']
        with self.assertRaises((ResultFormatError, TypeError, ValueError)):
            _unpack(missing)

        class UnregisteredCANRef(CANSourceRef):
            """仅测试同名伪类不能借白名单登记；不增加字段或文件副作用。"""

        # 名称与字段均可相同，但真实class不是登记原对象，不能开放反射反序列化。
        UnregisteredCANRef.__name__ = 'CANSourceRef'
        fake = UnregisteredCANRef(**vars(reference))
        row = core_values((fake,))[0]
        for operation in (_pack, _estimate):
            with self.subTest(operation=operation), self.assertRaises((ResultFormatError, TypeError, ValueError)):
                operation(row)
        with self.assertRaises((ResultFormatError, TypeError, ValueError)):
            encode_record(history_sample(fake), MAX_BYTES)

    def test_history_v3_rejects_damage_native_type_errors_and_v1_direct_can_bypass(self):
        """损坏记录明确失败，v1不能利用结果模型CAN登记绕过v3固定引用格式。

        参数: 无。返回: None。异常: 错误版本/固定shape/类型或不完整数据被接受则失败。
        """
        reference = can_reference()
        payload = encode_record(history_sample(reference), MAX_BYTES)
        packed = json.loads(payload)
        ref_path = ('values', 'tuple', 7, 'tuple')
        cases = [(('history_version',), version) for version in (0, 4, True, 3.0)]
        cases += [(('record_type',), 'progress'), (('record_type',), 'unknown'), (('extra',), 0),
            (ref_path + (0,), 'csv_source_ref'), (ref_path + (0,), 'unknown_ref'),
            (ref_path + (4,), False), (ref_path + (6,), True), (ref_path + (7,), 0),
            (ref_path + (8,), 1), (ref_path + (9,), True), (ref_path + (9,), 1.0),
            (ref_path + (10,), 1), (ref_path + (10,), True),
            (ref_path + (10,), {'diagnostic_float': 'nan'}), (ref_path + (11,), 1),
            (('values', 'tuple', 0), False), (('values', 'tuple', 2), 2**63),
            (('values', 'tuple', 8), 1)]
        for keys, value in cases:
            with self.subTest(keys=keys, value=value), self.assertRaises(ResultFormatError):
                decode_record(changed_line(packed, keys, value), MAX_BYTES)
        for size_change in (-1, 1):
            tree = deepcopy(packed)
            raw = tree['values']['tuple'][7]['tuple']
            raw.pop() if size_change < 0 else raw.append('extra')
            with self.subTest(size_change=size_change), self.assertRaises(ResultFormatError):
                decode_record(json_line(tree), MAX_BYTES)
        for version in (1, 2):
            with self.subTest(version=version), self.assertRaises(ResultFormatError):
                decode_record(changed_line(packed, ('history_version',), version), MAX_BYTES)
        # 内部通用codec产生的真实CAN model不适用于历史固定外壳；放到历史v1也必须被明确拒绝。
        result_wire = _pack(core_values((reference,))[0])
        direct = result_wire['fields']['source_refs']['tuple'][0]
        # v3内部基础身份也要求精确SourceRef，不能以其CAN子类替代固定外壳。
        with self.assertRaises(ResultFormatError):
            decode_record(changed_line(packed, ref_path + (1,), direct), MAX_BYTES)
        bypass = deepcopy(packed)
        bypass['history_version'] = 1
        bypass['values']['tuple'][7] = direct
        with self.assertRaises(ResultFormatError):
            decode_record(json_line(bypass), MAX_BYTES)
        # 真正的外层/JSON损坏不可以当空批或终点未知忽略。
        for damaged in (payload[:-1], payload[:-8] + b'\n', b'\xff\n',
                b'{"history_version":3,"history_version":3,"record_type":"sample","values":null}\n',
                b'{"history_version":3,"record_type":"sample","values":NaN}\n'):
            with self.subTest(damaged=damaged[:48]), self.assertRaises(ResultFormatError):
                decode_record(damaged, MAX_BYTES)
        with self.assertRaises(ResultFormatError):
            decode_record(payload, len(payload) - 1)
