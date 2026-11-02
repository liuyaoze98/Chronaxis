"""验证按需CAN历史不会丢观测、原序或同刻别名，使用独立小BLF与精确时间基准。

所有输入/暂存位于work独占目录；原CAN链真实spawn，测试不替代原reader/decoder。
数值来自手写DBC，时间使用原convert_time独立比对整数比新路径；只测本节点边界。
"""

import importlib.util
import math
import random
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.execution.can_batch_reader import _float_seconds_ns
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
from chronaxis.legacy.message_store import DecodedMessageStore
from chronaxis.legacy import message_store as message_store_module
from chronaxis.legacy.records import LegacyCANField, LegacyDecodedFrame, LegacyRawFrame
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.can_spec import LegacyCANSpec
from chronaxis.sources.models import ReadRequest
from chronaxis.timebase.conversion import convert_time


class PreciseFloatTimeTests(unittest.TestCase):
    """原十进制精确表示算法独立核新整数比算法，不用浮点乘法作真值。"""

    def test_binary_float_exact_rounding(self):
        """覆盖负数、同刻、次正规、边界邻点及固定随机位值。参数: 无。返回: None。异常: 断言失败。"""
        rng = random.Random(20261018)
        values = [0.0, -0.0, 5e-324, -5e-324, 1 / 1024, -1 / 1024, 1700000000.1234567]
        values += [rng.uniform(-9e9, 9e9) for _ in range(2000)]
        values += [math.ldexp(rng.uniform(-1, 1), exponent) for exponent in range(-1074, 34)]
        for value in values:
            expected = convert_time(value, 's')
            self.assertEqual(_float_seconds_ns(value), (expected.time_ns, expected.quantized), value)
        for value in (1e20, -1e20, math.inf, -math.inf, math.nan):
            with self.assertRaises((ValueError, OverflowError)):
                _float_seconds_ns(value)
        for value in (True, 1, '1'):
            with self.assertRaises(TypeError):
                _float_seconds_ns(value)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('can', 'cantools', 'natsort')), '缺少可选CAN依赖')
class NeededCANHistoryTests(unittest.TestCase):
    """拥有独占真实文件与预算，结束必须归还全部owner费用。"""

    def setUp(self):
        """写手工DBC/BLF夹具。参数: 无。返回: None。异常: 原文件/依赖错误。"""
        import can
        self.root = Path('work/c12-needed-history-home-20261018') / uuid4().hex
        self.root.mkdir(parents=True)
        self.budget = ResourceBudget(256 * 1024 ** 2)
        self.owners = []
        self.dbc, self.blf = self.root / 'input.dbc', self.root / 'input.blf'
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Vector__XXX\nBO_ 256 Demo: 1 Vector__XXX\n SG_ Sample : 0|8@1+ (2,-1) [-1|509] "V" Vector__XXX\n', encoding='utf-8')
        # 非目标帧同时占真实观测首末，两个目标同刻保独立sequence。
        with can.BLFWriter(self.blf) as writer:
            for stamp, frame_id, data in ((0, 999, b'a'), (1, 256, b'\x02'),
                    (1, 256, b'\x03'), (2, 999, b'b'), (3, 256, b''), (4, 999, b'c')):
                writer.on_message_received(can.Message(timestamp=1700000000.0 + stamp,
                    arbitration_id=frame_id, data=data, is_extended_id=False, channel=0))

    def tearDown(self):
        """关闭真实owner核零余额，保留所有文件证据。参数: 无。返回: None。异常: 原关闭/断言失败。"""
        for owner in reversed(self.owners):
            owner.close()
        self.assertEqual(self.budget.ram_bytes, 0)

    def read(self, *, raw=False, aliases=2, message_ids=(256,), size=3):
        """建立显式批来源并保完整观测。参数: raw/aliases/message_ids/size控制边界。返回: read。异常: 原错误。"""
        field = LegacyCANField(0, 'Sample', 256, False, False)
        definitions = tuple(SignalDefinition('a' + str(index), 'bus', field.key,
            SignalDType.FLOAT64, 'V', 1000000000, input_unit='V') for index in range(aliases))
        spec = LegacyCANSpec('bus', self.blf, self.dbc, 0,
            TimebaseSpec('clock', TimeType.RELATIVE, 'synthetic'), offset_ns=-1700000000000000000)
        adapter = BudgetedLegacyCANSourceAdapter(self.budget, spec, 'session', definitions,
            work_dir=self.root / 'adapter', batch_read=True, retain_raw_frames=raw,
            capture_message_updates=True, message_frame_ids=message_ids)
        self.owners.append(adapter)
        request = ReadRequest('session', tuple(item.name for item in definitions), 0, 5000000000, size)
        read = adapter.iter_batches(request)
        self.owners.append(read)
        return read

    def test_sparse_history_full_observation_and_same_time(self):
        """无raw保存3个目标，6帧观测完整，同刻与缺值别名不丢失。参数: 无。返回: None。异常: 断言失败。"""
        read = self.read()
        batches = list(read)
        self.assertTrue(read.finished)
        self.assertEqual((read.observation.row_count, read.observation.first_ns, read.observation.last_ns),
            (6, 0, 4000000000))
        self.assertIsNone(read._raw_store)
        self.assertEqual([batch.sample_count for batch in batches], [3, 3, 0])
        for alias in ('a0', 'a1'):
            columns = [batch.series[alias] for batch in batches if alias in batch.series]
            self.assertEqual([int(seq) for column in columns for seq in column.sequence], [1, 2, 4])
            self.assertEqual([bool(value) for column in columns for value in column.valid], [True, True, False])
            self.assertEqual([float(value) for column in columns for value in column.values][:2], [3, 5])
        store = read._message_store
        rows = list(store.iter_records())
        self.assertEqual(store.count, 3)
        self.assertEqual(store.line_limit, max(len(line) for line in store.file_path.read_bytes().splitlines(keepends=True)))
        with self.assertRaises(AttributeError):
            store.line_limit = 1000000
        self.assertEqual([row.decoded.sequence for row in rows], [1, 2, 4])
        self.assertEqual([dict(row.decoded.values) for row in rows], [{'Sample': 3}, {'Sample': 5}, {}])
        self.assertFalse(any(self.root.rglob('raw_frames.jsonl')))

    def test_real_sparse_batch_keeps_all_frames_and_exact_target_times(self):
        """真实spawn交付64原帧的稀疏批，所有目标时间及量化标志对独立旧转换核验。

        参数: 无。返回: None。异常: 原帧观测遗漏、目标映射失真或稀疏分支未真实使用。
        """
        import can
        from chronaxis.execution import can_batch_reader as batch_module
        positions = (9, 33, 54)
        with can.BLFWriter(self.blf) as writer:
            for index in range(64):
                writer.on_message_received(can.Message(timestamp=1700000000.0+index/1024,
                    arbitration_id=256 if index in positions else 999,
                    data=b'\x02', is_extended_id=False, channel=0))
        read = self.read(aliases=1, size=2)
        with patch.object(batch_module, '_sparse_batch_times', wraps=batch_module._sparse_batch_times) as sparse:
            batches = list(read)
        self.assertGreater(sparse.call_count, 0)
        self.assertTrue(read.finished)
        self.assertEqual(read.observation.row_count, 64)
        self.assertEqual(sum(batch.sample_count for batch in batches), len(positions))
        rows = list(read._message_store.iter_records())
        self.assertEqual([row.decoded.sequence for row in rows], list(positions))
        for row in rows:
            expected = convert_time(row.decoded.frame.timestamp, 's')
            self.assertEqual(row.time_ns, expected.time_ns-1700000000000000000)
            self.assertEqual(row.time_quantized, expected.quantized)
        self.assertEqual(read.observation.first_ns, 0)
        last = convert_time(1700000000.0+63/1024, 's')
        self.assertEqual(read.observation.last_ns, last.time_ns-1700000000000000000)
        self.assertIsNone(read._raw_store)

    def test_constant_message_selector_without_signals(self):
        """纯常量选择器没有任何signal仍保存选择ID及全观测。参数: 无。返回: None。异常: 断言失败。"""
        self.budget = ResourceBudget(32 * 1024 ** 2)
        read = self.read(aliases=0, size=4096)
        batches = list(read)
        self.assertEqual(len(batches), 1)
        self.assertTrue(batches[0].source_eof)
        self.assertEqual(read.observation.row_count, 6)
        self.assertEqual([row.decoded.sequence for row in read._message_store.iter_records()], [1, 2, 4])

    def test_raw_export_retains_all_original_frames(self):
        """raw开启保存全部原帧，消息仓仍只含目标原记录。参数: 无。返回: None。异常: 断言失败。"""
        read = self.read(raw=True)
        list(read)
        self.assertEqual(read._raw_store.count, 6)
        self.assertEqual(read._message_store.count, 3)
        rows = list(read._raw_store.iter_frames())
        self.assertEqual(len(rows), 6)

    def test_empty_message_selection_keeps_observation_and_empty_line_limit(self):
        """无目标时空消息仓不虚构原范围，完整六帧观测仍保留。参数: 无。返回: None。异常: 断言失败。"""
        read = self.read(aliases=0, message_ids=(257,))
        batches = list(read)
        self.assertEqual(len(batches), 1)
        self.assertEqual(read._message_store.count, 0)
        self.assertEqual(read._message_store.line_limit, 1)
        self.assertEqual(tuple(read._message_store.iter_records()), ())
        self.assertEqual(read.observation.row_count, 6)

    def test_small_budget_shrinks_transport_and_keeps_consumption_space(self):
        """32MiB不足默认大包，但可供单目标样本及完整消息暂存，必须缩包成功。

        参数: 无。返回: None。异常: 预算误拒、样本遗漏或最终费用泄漏使测试失败。
        """
        self.budget = ResourceBudget(32 * 1024 ** 2)
        read = self.read(aliases=1, size=1)
        batches = list(read)
        self.assertEqual(sum(batch.sample_count for batch in batches), 3)
        self.assertEqual(read._message_store.count, 3)
        self.assertEqual(read.observation.row_count, 6)

    def test_non_target_timestamp_regression_is_rejected(self):
        """无目标记录也核每个原时间，不能因稀疏保存漏掉原输入回退。

        参数: 无。返回: None。异常: 未拒绝倒退或资源泄漏使断言失败。
        """
        import can
        with can.BLFWriter(self.blf) as writer:
            for stamp in (0, 2, 1):
                writer.on_message_received(can.Message(timestamp=1700000000.0 + stamp,
                    arbitration_id=999, data=b'x', is_extended_id=False, channel=0))
        read = self.read(aliases=0)
        with self.assertRaisesRegex(Exception, '时间回退'):
            list(read)
        self.assertFalse(read.finished)
        self.assertTrue(read.failed)

    def test_cancel_during_sparse_append_closes_actual_batch_resources(self):
        """真实批次已收到后消息仓取消，保原异常并关闭进程及本批费用。

        参数: 无。返回: None。异常: 假完成、错误替换或责任泄漏使断言失败。
        """
        read = self.read()
        primary = KeyboardInterrupt('append cancelled')
        with patch.object(DecodedMessageStore, 'append', side_effect=primary):
            with self.assertRaises(KeyboardInterrupt) as caught:
                next(read)
        self.assertIs(caught.exception, primary)
        self.assertIs(primary.can_observation_read_cleanup_owner, read)
        self.assertTrue(read.closed)
        self.assertFalse(read.finished)
        self.assertIsNone(read._incoming)

    def test_sealed_line_limit_rejects_larger_tamper_before_decode(self):
        """封口后加长行须在解码前拒绝，避免较小缓存预算持有未付费大行。

        参数: 无。返回: None。异常: 越过实测行长仍解码或上界被外部文件提高使测试失败。
        """
        read = self.read()
        list(read)
        store = read._message_store
        original_limit = store.line_limit
        lines = store.file_path.read_bytes().splitlines(keepends=True)
        lines[0] = lines[0][:-1] + b' ' * original_limit + b'\n'
        store.file_path.write_bytes(b''.join(lines))
        with patch.object(message_store_module, '_decode_row', wraps=message_store_module._decode_row) as decode:
            with self.assertRaisesRegex(Exception, '封口实测上限'):
                next(store.iter_records())
            decode.assert_not_called()
        self.assertEqual(store.line_limit, original_limit)

    def test_sparse_store_rejects_duplicate_and_reversed_sequence(self):
        """原序间隔允许但重复/倒退仍拒绝，默认连续模式不放宽。参数: 无。返回: None。异常: 断言失败。"""
        frame = LegacyRawFrame(1.0, 256, False, False, False, 0, 1, b'x', False, False, True, False)
        for suffix, sparse, second in (('duplicate', True, 3), ('reverse', True, 2), ('dense', False, 3)):
            store = DecodedMessageStore(self.budget, self.root / suffix, 'bus', 'session',
                decoder_profile='test', read_identity=suffix, sparse_sequences=sparse)
            self.owners.append(store)
            if sparse:
                store.append(LegacyDecodedFrame(3, frame, {}), 100, time_quantized=False)
            before = store.line_limit
            with self.assertRaises(ValueError):
                store.append(LegacyDecodedFrame(second, frame, {}), 100, time_quantized=False)
            self.assertEqual(store.line_limit, before)


if __name__ == '__main__':
    unittest.main()
