"""用真实FileIO底层计数验证四类新暂存reader的有界缓冲及原资源协议。

现场构造真实sealed消息仓、解码history、原帧仓和原始导出索引；不读CAN/DBC、
不改旧reader/vendor，不以假文件或定时性能阈值证明优化。计数FileIO子类每次都
调用原read/readinto，Path.open观察器只按产品实际buffering参数组装同一真实FD。
测试核完整原字节/SHA/typed行、跨8192边界和长行、真正EOF、预算先于open、
关闭前后取消及持续失败恢复、活sibling和借款隔离。所有产物在本任务work新目录。
"""

from configuration_fixtures import current_fixture

# 标准库计数与故障观察不会改变磁盘内容、原payload或读取顺序。
from hashlib import sha256
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import Interval, MemoryRow, SourceSpec, TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.legacy.message_store import DecodedMessageStore
from chronaxis.legacy.raw_store import RawFrameStore
from chronaxis.legacy.records import LegacyRawFrame, LegacyDecodedFrame
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultFormatError
from chronaxis.results.raw_exports import RawExportStore, RawExportRecord
from chronaxis.sources import MemorySourceAdapter, ReadRequest


KINDS = ('message', 'history', 'raw', 'index')
WORK = Path(__file__).resolve().parents[2] / 'work/m2-real-acceptance-tests/buffered-readers'


class CountingRaw(io.FileIO):
    """真实FileIO子类，只累计底层read/readinto次数及实际字节，不保存输入副本。"""

    def __init__(self, path):
        """打开唯一真实FD。参数: path只读路径。返回: FileIO。异常: 原open错误。"""
        super().__init__(path, 'r')
        self.read_calls = self.readinto_calls = self.bytes_read = self.close_failures = 0
        self.close_error = None
        self.close_after = False

    def read(self, size=-1):
        """计实际FileIO.read。参数: size原字节上限。返回: 原bytes。异常: 原IO错误。"""
        self.read_calls += 1
        result = super().read(size)
        if result is not None:
            self.bytes_read += len(result)
        return result

    def readinto(self, buffer):
        """计实际FileIO.readinto。参数: buffer原可写缓冲。返回: 原长度。异常: 原IO错误。"""
        self.readinto_calls += 1
        count = super().readinto(buffer)
        if count is not None:
            self.bytes_read += count
        return count

    def close(self):
        """在真实raw FD关闭前/后保同一故障。参数: 无。返回: None。异常: 原故障或IO错。"""
        if self.close_error is not None:
            self.close_failures += 1
            if self.close_after:
                super().close()
            raise self.close_error
        return super().close()


class TemporaryReaderBufferingTests(unittest.TestCase):
    """四个实际产品owner共享同类黑盒断言，不构造假owner或模拟数值真值。"""

    def setUp(self):
        """建立独占work根与真实资源清单。参数: 无。返回: None。异常: 原目录错误。"""
        self.root = WORK / uuid4().hex
        self.root.mkdir(parents=True)
        self.owners, self.budgets, self.raw_handles = [], [], []

    def tearDown(self):
        """停故障后由原owner关闭，最后核每份borrowed777而非主动替产品抵账。

        参数: 无。返回: None。异常: 原关闭或泄漏断言失败，产物留在work。
        """
        for raw in self.raw_handles:
            raw.close_error = None
        for owner in reversed(self.owners):
            owner.close()
        for raw in self.raw_handles:
            self.assertTrue(raw.closed)
        for budget in self.budgets:
            self.assertEqual(budget.ram_bytes, 777)
            budget.release_ram(777)
            self.assertEqual(budget.ram_bytes, 0)

    def fixture(self, kind):
        """构造真实封存输入，消息/history/index包含大于8192字节的合法单行。

        参数: kind为四固定仓类别。返回: owner/path/open/budget/count小描述。
        异常: 原模型、预算或文件错误传播；原帧64字节上限保持，靠多行跨buffer。
        """
        budget = ResourceBudget(128 * 1024**2)
        budget.reserve_ram(777)
        self.budgets.append(budget)
        path = self.root / (kind + '-' + uuid4().hex)
        if kind == 'history':
            field = 'raw.' + 'x' * 9000
            source = SourceSpec('bus', TimebaseSpec('clock', TimeType.RELATIVE, 'buffer-test'),
                tuple(MemoryRow(time_ns=index, sequence=index, values={field: index}) for index in range(4)),
                observation_start_ns=0, observation_end_ns=4)
            definition = SignalDefinition('value', 'bus', field, SignalDType.FLOAT64, '1', 10)
            adapter = MemorySourceAdapter(source, 'session', (definition,), backend='reference')
            request = ReadRequest('session', ('value',), 0, 4, 1)
            owner = DecodedHistoryStore(budget, path, (adapter.describe(),), {'bus': request})
            self.owners.append(owner)
            try:
                for batch in adapter.iter_batches(request):
                    owner.append(batch)
            finally:
                adapter.close()
            owner.seal()
            return SimpleNamespace(kind=kind, owner=owner, path=owner.paths['bus'],
                open=lambda: owner.iter_records('bus'), budget=budget, expected_count=None)
        if kind == 'index':
            owner = RawExportStore(budget, path, 'bus', 'session', 'home')
            self.owners.append(owner)
            for index in range(4):
                owner.append(RawExportRecord(index, 'bus', 'session', 'segment:' + str(index),
                    'window_' + 'x' * 9000, Interval(0, 10), Interval(5, 5), 0,
                    None, None, 0, 'empty_range', 'home'))
            owner.seal()
            return SimpleNamespace(kind=kind, owner=owner, path=owner.inventory_path,
                open=owner.iter_records, budget=budget, expected_count=4)
        owner = (DecodedMessageStore(budget, path, 'bus', 'session',
                    decoder_profile='explicit-decoded-v1', read_identity='real-buffer-read')
                 if kind == 'message' else RawFrameStore(budget, path, 'bus'))
        self.owners.append(owner)
        count = 4 if kind == 'message' else 48
        for index in range(count):
            frame = LegacyRawFrame(1.0 + index, 256, False, False, False, 0, 64,
                bytes(range(64)), True, True, False, False)
            values = {('signal_' + str(i) + '_' + 'x' * 80): float(i) for i in range(120)}
            record = LegacyDecodedFrame(index, frame, values if kind == 'message' else {})
            if kind == 'message':
                owner.append(record, index, time_quantized=False)
            else:
                owner.append(record, index)
        owner.seal()
        return SimpleNamespace(kind=kind, owner=owner, path=owner.file_path,
            open=owner.iter_records if kind == 'message' else owner.iter_frames,
            budget=budget, expected_count=count)

    def observe_open(self, fixture, handles):
        """只按产品请求的buffering包装真实FileIO，便于准确计底层调用。

        参数: fixture为目标实际文件；handles接收原FileIO。返回: Path.open替换函数。
        异常: 原FileIO/BufferedReader构造错误；其他文件完全走原Path.open。
        """
        original = Path.open

        def opened(path, mode='r', *args, **kwargs):
            """透传真实open参数。参数: 原path/mode/args/kwargs。返回: 真句柄。异常: 原IO错。"""
            if path == fixture.path and mode == 'rb':
                raw = CountingRaw(path)
                handles.append(raw)
                self.raw_handles.append(raw)
                buffering = kwargs.get('buffering', args[0] if args else -1)
                return raw if buffering == 0 else io.BufferedReader(raw, buffer_size=buffering)
            return original(path, mode, *args, **kwargs)

        return opened

    def test_all_four_readers_use_block_reads_and_preserve_exact_eof(self):
        """四仓真实底层调用接近块数而非字节数，完整typed内容与SHA保持且末条仍未EOF。

        参数: 无。返回: None。异常: 原读错、字节/行/EOF/费用或分块断言失败。
        """
        evidence = []
        for kind in KINDS:
            with self.subTest(kind=kind):
                fixture = self.fixture(kind)
                before = fixture.path.read_bytes()
                self.assertGreater(len(before), 8192)
                if kind != 'raw':
                    self.assertGreater(max(map(len, before.splitlines())), 8192)
                baseline = fixture.budget.ram_bytes
                handles = []
                actual = []
                with patch.object(Path, 'open', new=self.observe_open(fixture, handles)):
                    reader = fixture.open()
                try:
                    count = 0
                    # 预先知道物理行数，确保末条交付仍不被预读伪装成verified EOF。
                    for _ in before.splitlines():
                        actual.append(next(reader))
                        count += 1
                    self.assertFalse(reader.verified_eof)
                    with self.assertRaises(StopIteration):
                        next(reader)
                    self.assertTrue(reader.verified_eof and reader.closed)
                    self.assertTrue(handles[0].closed)
                    self.assertEqual(handles[0].bytes_read, len(before))
                    evidence.append(dict(kind=kind, bytes=len(before), records=count,
                        read_calls=handles[0].read_calls, readinto_calls=handles[0].readinto_calls,
                        maximum_block_calls=math.ceil(len(before) / 8192) + 2,
                        raw_closed=handles[0].closed, verified_eof=reader.verified_eof))
                    self.assertLessEqual(handles[0].read_calls + handles[0].readinto_calls,
                                         math.ceil(len(before) / 8192) + 2)
                    self.assertIs(type(reader.handle), io.BufferedReader)
                    if fixture.expected_count is not None:
                        self.assertEqual(count, fixture.expected_count)
                    # 手写原值检查与磁盘SHA分开，避免只证明重复使用同一codec。
                    if kind == 'message':
                        self.assertEqual(tuple(row.decoded.sequence for row in actual), tuple(range(4)))
                        self.assertTrue(all(len(row.decoded.values) == 120 and row.decoded.frame.data == bytes(range(64))
                            and row.decoded.values['signal_0_' + 'x' * 80] == 0.0 for row in actual))
                    elif kind == 'raw':
                        self.assertEqual(tuple(row.sequence for row in actual), tuple(range(48)))
                        self.assertTrue(all(row.frame.data == bytes(range(64)) and row.frame.is_fd for row in actual))
                    elif kind == 'index':
                        self.assertEqual(tuple(row.index for row in actual), tuple(range(4)))
                        self.assertTrue(all(row.status == 'empty_range' and row.actual == Interval(5, 5) for row in actual))
                    else:
                        samples = [row for row in actual if hasattr(row, 'value')]
                        self.assertEqual(tuple(row.value.value for row in samples), (0.0, 1.0, 2.0, 3.0))
                    self.assertEqual(fixture.path.read_bytes(), before)
                    digest = fixture.owner.hashes['bus'].hexdigest() if kind == 'history' else fixture.owner.sha256
                    self.assertEqual(sha256(before).hexdigest(), digest)
                    self.assertEqual(fixture.budget.ram_bytes, baseline)
                finally:
                    reader.close()
        # 留实际测量数而非仅布尔结论；工件属于本例有限work证据，不混入性能计时。
        (self.root / 'block-read-counts.json').write_text(
            json.dumps(current_fixture(dict(device_label='home', facts=evidence)), indent=2) + '\n', encoding='utf-8')

    def test_prefetch_early_close_and_corrupt_or_overlong_rows_do_not_prove_completion(self):
        """缓冲确有有限预读但提前close不设verified，追加及超限损坏仍严格拒绝。

        参数: 无。返回: None。异常: 预读被误当消费、损坏未拒或真实句柄未关即失败。
        """
        for kind in KINDS:
            with self.subTest(kind=kind, stage='early'):
                fixture, handles = self.fixture(kind), []
                with patch.object(Path, 'open', new=self.observe_open(fixture, handles)):
                    reader = fixture.open()
                next(reader)
                self.assertGreater(handles[0].bytes_read, 0)
                self.assertFalse(reader.verified_eof)
                reader.close()
                self.assertFalse(reader.verified_eof)
                self.assertTrue(reader.handle.closed and handles[0].closed)
            for corruption in ('suffix', 'overlong'):
                with self.subTest(kind=kind, corruption=corruption):
                    fixture, handles = self.fixture(kind), []
                    limit = (fixture.owner.line_limits['bus'] if kind == 'history'
                             else fixture.owner.max_row_bytes if kind in ('message', 'raw') else 65536)
                    if corruption == 'suffix':
                        with fixture.path.open('ab') as handle:
                            handle.write(b'{}\n')
                    else:
                        fixture.path.write_bytes(b'x' * (limit + 2) + b'\n')
                    with patch.object(Path, 'open', new=self.observe_open(fixture, handles)):
                        reader = fixture.open()
                    try:
                        with self.assertRaises(ResultFormatError):
                            tuple(reader)
                        self.assertFalse(reader.verified_eof)
                        self.assertTrue(handles[0].closed)
                    finally:
                        reader.close()

    def test_buffer_fee_is_prepaid_and_reserve_cancel_does_not_open_a_file(self):
        """真实reader费比原公式多16384，预约前后KI及实际容量不足都先于open。

        参数: 无。返回: None。异常: 新buffer未付费、故障不命中、原错被换或借款损失即失败。
        """
        original_open = Path.open
        for kind in KINDS:
            fixture = self.fixture(kind)
            baseline = fixture.budget.ram_bytes
            reader = fixture.open()
            amount = fixture.budget.ram_bytes - baseline
            original_cost = (fixture.owner.line_limits['bus'] * 64 + 8192 if kind == 'history'
                else 65536 + 64 * (fixture.owner.max_row_bytes if kind in ('message', 'raw') else 65536))
            self.assertEqual(amount, original_cost + 16384)
            reader.close()
            for after in (False, True):
                with self.subTest(kind=kind, after=after):
                    item = self.fixture(kind)
                    marker, calls = KeyboardInterrupt('buffer reserve boundary'), []
                    reserve = item.budget.reserve_ram

                    def fail(size):
                        """原预约前/后只取消一次。参数: size。返回: 原结果。异常: marker原对象。"""
                        calls.append(size)
                        if after:
                            reserve(size)
                        raise marker

                    def unopened(path, mode='r', *args, **kwargs):
                        """拒目标read open但允许原诊断写。参数: 原参数。返回: 原句柄。异常: 提前open断言。"""
                        if path == item.path and mode == 'rb':
                            self.fail('reader buffer尚未完成预约便打开文件')
                        return original_open(path, mode, *args, **kwargs)

                    with patch.object(item.budget, 'reserve_ram', side_effect=fail), \
                            patch.object(Path, 'open', new=unopened), self.assertRaises(KeyboardInterrupt) as caught:
                        item.open()
                    self.assertIs(caught.exception, marker)
                    self.assertEqual(len(calls), 1)
                    item.owner.close()
                    self.assertEqual(item.budget.ram_bytes, 777)
            with self.subTest(kind=kind, stage='capacity'):
                item = self.fixture(kind)
                held = item.budget.memory_budget_bytes - item.budget.ram_bytes - amount + 1
                item.budget.reserve_ram(held)
                try:
                    with self.assertRaises(BudgetExceededError):
                        item.open()
                finally:
                    item.owner.close()
                    item.budget.release_ram(held)
                self.assertEqual(item.budget.ram_bytes, 777)

    def test_real_buffer_raw_close_failure_recovers_without_closing_sibling(self):
        """真实raw FD关闭前持续三次失败及关闭后KI均保同一buffer/原错，活兄弟不受影响。

        参数: 无。返回: None。异常: FD责任丢失、原对象被换、兄弟误关或预算重复释放即失败。
        """
        for kind in KINDS:
            for after in (False, True):
                with self.subTest(kind=kind, after=after):
                    fixture, handles = self.fixture(kind), []
                    baseline = fixture.budget.ram_bytes
                    with patch.object(Path, 'open', new=self.observe_open(fixture, handles)):
                        reader, sibling = fixture.open(), fixture.open()
                    buffer, raw = reader.handle, handles[0]
                    self.assertIs(buffer.raw, raw)
                    marker = KeyboardInterrupt('actual buffer raw close')
                    raw.close_error, raw.close_after = marker, after
                    for _ in range(1 if after else 3):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            reader.close()
                        self.assertIs(caught.exception, marker)
                        self.assertIs(reader.handle, buffer)
                        if kind != 'history':
                            name = {'message': 'decoded_message_store_cleanup_owner',
                                    'raw': 'raw_frame_store_cleanup_owner',
                                    'index': 'raw_export_store_cleanup_owner'}[kind]
                            self.assertIs(getattr(marker, name), fixture.owner)
                        self.assertFalse(sibling.closed or sibling.handle.closed or handles[1].closed)
                    self.assertEqual(raw.close_failures, 1 if after else 3)
                    self.assertEqual(raw.closed, after)
                    raw.close_error = None
                    reader.close()
                    self.assertTrue(reader.closed and buffer.closed and raw.closed)
                    self.assertIsNotNone(next(sibling))
                    sibling.close()
                    self.assertTrue(handles[1].closed)
                    self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_buffer_fee_release_cancel_preserves_borrowed_credit_and_actual_closed_fd(self):
        """含buffer的整笔费释放前持续三次或已释放后KI，可由同reader恢复且不抵兄弟费用。

        参数: 无。返回: None。异常: 原错/费用槽丢失、FD未真关或重复抵销即失败。
        """
        for kind in KINDS:
            for after in (False, True):
                with self.subTest(kind=kind, after=after):
                    fixture = self.fixture(kind)
                    baseline = fixture.budget.ram_bytes
                    reader = fixture.open()
                    amount = fixture.budget.ram_bytes - baseline
                    sibling = fixture.open()
                    marker, hits = KeyboardInterrupt('buffer fee release'), []
                    release = fixture.budget.release_ram

                    def fail(size):
                        """只拦该整笔reader费。参数: size。返回: 原结果。异常: 同一marker。"""
                        if size == amount:
                            hits.append(size)
                            if after:
                                release(size)
                            raise marker
                        return release(size)

                    with patch.object(fixture.budget, 'release_ram', side_effect=fail):
                        for _ in range(1 if after else 3):
                            with self.assertRaises(KeyboardInterrupt) as caught:
                                reader.close()
                            self.assertIs(caught.exception, marker)
                    self.assertEqual(len(hits), 1 if after else 3)
                    self.assertTrue(reader.handle.closed and reader.handle.raw.closed)
                    self.assertFalse(sibling.closed or sibling.handle.closed)
                    reader.close()
                    self.assertIsNotNone(next(sibling))
                    sibling.close()
                    self.assertEqual(fixture.budget.ram_bytes, baseline)


if __name__ == '__main__':
    # 直接入口只运行本专项；普通导入不创建文件或读取输入。
    unittest.main()
