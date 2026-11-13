"""用有限手工原帧和真实文件独立核对raw store的原序、完整性及恢复责任。

不依赖CAN库/DBC/旧fixture，不把被测编码器作数值真值：手工给出三帧序号0/1/2、
分析时间5/5/9ns、未知ID及完整公开字段，独立读实际JSONL与hashlib核SHA/无values。
其余例以真实FD代理或单次预算前后故障检验部分写poison、未返回reader、持续关闭
失败三次后恢复、原错/KI优先及借用费用保持。代理仍调用真实文件方法，不造假FD。
只在work/m2-can-tests独占临时目录，执行后关闭本例owner；清理前核临时根仍在work。
这些是新分析层原始暂存专项，不证明公共CAN接线、旧reader修复、RSS或真实日志验收。
"""

from configuration_fixtures import current_fixture

# 标准库构造小真值和故障；产品负责原序存储、编码、预算与实际资源关闭。
from hashlib import sha256
import json
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest
from unittest.mock import patch
from chronaxis.legacy.raw_store import RawFrameStore
from chronaxis.legacy.records import LegacyRawFrame, LegacyDecodedFrame
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError, ResultFormatError


def frame(index=0):
    """手工声明全部公开原帧字段，含未映射ID和非文本payload。

    参数: index为本小例0/1/2，影响原秒/ID/方向。返回: LegacyRawFrame。
    异常: 模型校验错误直接传播，不调用CAN构造/解析或被测store。
    """
    return LegacyRawFrame(1.25 + index / 4, 0x1FFFFFFF - index, True, index == 1,
        index == 2, 'channel\nA', 3, b'\x00\xff\x80', True, index != 1, True, False)


def decoded(index=0):
    """附带不应写入raw store的原解码字典。

    参数: index为原yield序号。返回: LegacyDecodedFrame。异常: 原模型错误。
    """
    return LegacyDecodedFrame(index, frame(index), {'not_stored': float('nan'), 'a': index})


class ActualFile:
    """透明代理真实FileIO，只在明确写/关闭位置注入同一错误，不代替FD事实。"""

    def __init__(self, actual):
        """记录真实句柄及可切换故障。参数: actual为已打开FileIO。返回: 代理。异常: 无。"""
        self.actual = actual
        self.close_error = self.write_error = None
        self.close_after = False
        self.partial_bytes, self.close_calls = 0, 0

    def __getattr__(self, name):
        """透传未注入方法和closed事实。参数: name为属性名。返回: 原属性。异常: 原属性错误。"""
        return getattr(self.actual, name)

    def write(self, payload):
        """可先真实写有限前缀再抛原错。参数: payload为bytes。返回: 原写入量。异常: 注入原错。
        """
        if self.write_error is not None:
            if self.partial_bytes:
                self.actual.write(payload[:self.partial_bytes])
            raise self.write_error
        return self.actual.write(payload)

    def close(self):
        """在真实close前或后持续抛指定对象。参数: 无。返回: 原结果。异常: 同一注入错误。
        """
        self.close_calls += 1
        if self.close_error is not None and not self.close_after:
            raise self.close_error
        value = self.actual.close()
        if self.close_error is not None:
            raise self.close_error
        return value


class RejectingSet(set):
    """在真实reader登记前/后抛MemoryError，保留实际实例以核未返回责任。"""

    def __init__(self, error, after):
        """保存登记故障。参数: error为原对象；after决定先真实add。返回: set。异常: 无。"""
        super().__init__()
        self.error, self.after, self.actual_reader = error, after, None

    def add(self, item):
        """只拦一次真实登记位置。参数: item为实际reader。返回: 不成功。异常: 原error。
        """
        self.actual_reader = item
        if self.after:
            super().add(item)
        raise self.error


class RawFrameStoreTests(unittest.TestCase):
    """每例借用固定RAM标记，显式核恢复基线和真实FD，不靠tearDown断言冒充及时关闭。"""

    def setUp(self):
        """建立work内独占根。参数: 无。返回: None。异常: 原目录/设备IO错误。"""
        self.work = Path(__file__).resolve().parents[2] / 'work' / 'm2-can-tests'
        self.work.mkdir(parents=True, exist_ok=True)
        self.temp = TemporaryDirectory(prefix='raw-store-', dir=self.work)
        self.root, self.owners, self.budgets = Path(self.temp.name), [], []

    def tearDown(self):
        """回收测试自有对象和借用标记，删除前核目录边界。

        参数: 无。返回: None。异常: 未恢复资源/越界/清理错误直接暴露，不吞失败。
        """
        for owner in self.owners:
            owner.close()
        for budget in self.budgets:
            self.assertEqual(budget.ram_bytes, 4096)
            budget.release_ram(4096)
        self.assertTrue(self.root.resolve().is_relative_to(self.work.resolve()))
        self.temp.cleanup()

    def budget(self, *, quota=None):
        """建立实际共享账本及外部借用费用。参数: quota为可选磁盘配额。返回: budget。
        异常: 原预算错误；store不得抵销4096字节借用标记。
        """
        budget = ResourceBudget(32 * 1024 ** 2, quota)
        budget.reserve_ram(4096)
        self.budgets.append(budget)
        return budget

    def store(self, name='case', *, budget=None, max_row_bytes=65536):
        """只登记真实成功返回的store。参数: name/budget/行限额。返回: store。异常: 原构造错误。
        """
        owner = RawFrameStore(self.budget() if budget is None else budget, self.root / name,
            'raw_source', max_row_bytes=max_row_bytes)
        self.owners.append(owner)
        return owner

    def populated(self, name='case'):
        """写手算三帧并真实seal。参数: name为新子目录。返回: 原store。异常: 原写入/关闭错误。
        """
        owner = self.store(name)
        for index, time_ns in enumerate((5, 5, 9)):
            owner.append(decoded(index), time_ns)
        owner.seal()
        return owner

    def test_original_fields_order_same_time_and_flow_sha(self):
        """手算三帧无筛选且5/5/9ns同刻原序保留，独立核真实文件及流SHA。

        参数: 无。返回: None。异常: 原操作或字段/身份/费用/完整EOF断言失败。
        """
        owner = self.populated()
        payload = owner.file_path.read_bytes()
        self.assertEqual(owner.count, 3)
        self.assertEqual(owner.sha256, sha256(payload).hexdigest())
        self.assertEqual(owner.spool_bytes, len(payload))
        self.assertIsNone(owner._writer)
        packets = [json.loads(line) for line in payload.splitlines()]
        self.assertEqual([item['sequence'] for item in packets], [0, 1, 2])
        self.assertEqual([item['time_ns'] for item in packets], [5, 5, 9])
        self.assertTrue(all(set(item) == {'sequence', 'time_ns', 'frame'} for item in packets))
        self.assertNotIn(b'not_stored', payload)
        self.assertEqual(packets[1]['frame']['data_hex'], '00ff80')
        reader = owner.iter_frames()
        rows = list(reader)
        self.assertTrue(reader.closed and reader.verified_eof and reader.handle.closed)
        self.assertEqual([(row.sequence, row.time_ns) for row in rows], [(0, 5), (1, 5), (2, 9)])
        self.assertEqual([row.frame.arbitration_id for row in rows], [0x1FFFFFFF, 0x1FFFFFFE, 0x1FFFFFFD])
        self.assertEqual(rows[1].frame, LegacyRawFrame(1.5, 0x1FFFFFFE, True, True, False,
            'channel\nA', 3, b'\x00\xff\x80', True, False, True, False))
        owner.close()
        self.assertEqual(owner.budget.ram_bytes, 4096)
        self.assertEqual(owner.budget.spool_bytes, len(payload))
        self.assertTrue(owner.file_path.is_file())

    def test_independent_readers_final_row_and_early_close_are_not_eof(self):
        """两个真实文件位置独立；交付末行/提前close均不能伪造完整EOF。

        参数: 无。返回: None。异常: 原读取或位置/EOF/借用费用断言失败。
        """
        owner = self.populated()
        baseline = owner.budget.ram_bytes
        first, second = owner.iter_frames(), owner.iter_frames()
        self.assertIsNot(first.handle, second.handle)
        self.assertEqual(next(first).sequence, 0)
        self.assertEqual(next(second).sequence, 0)
        self.assertEqual(next(first).sequence, 1)
        self.assertEqual(next(first).sequence, 2)
        self.assertFalse(first.verified_eof)
        second.close()
        self.assertFalse(second.verified_eof)
        with self.assertRaises(StopIteration):
            next(first)
        self.assertTrue(first.verified_eof)
        self.assertEqual(owner.budget.ram_bytes, baseline)
        owner.close()
        self.assertTrue(first.handle.closed and second.handle.closed)

    def test_empty_source_seals_but_building_and_closed_cannot_read(self):
        """空文件可有真实完整EOF；未seal和已close明确拒读，不能混作空输入。

        参数: 无。返回: None。异常: 原操作或状态断言失败。
        """
        owner = self.store()
        with self.assertRaises(RuntimeError):
            owner.iter_frames()
        owner.seal()
        self.assertEqual(owner.count, 0)
        self.assertEqual(owner.sha256, sha256(b'').hexdigest())
        reader = owner.iter_frames()
        self.assertEqual(list(reader), [])
        self.assertTrue(reader.verified_eof)
        owner.close()
        with self.assertRaises(ResultClosedError):
            owner.iter_frames()

    def test_sequence_time_and_int64_violations_poison(self):
        """拒绝序号跳跃、同序重复、时间回退及int64越界，不重排补帧。

        参数: 无。返回: None。异常: 原拒绝或poison/费用断言失败。
        """
        cases = ((1, 5, False), (0, 4, True), (1, 4, True), (0, 1 << 63, False))
        for index, (sequence, time_ns, seed) in enumerate(cases):
            with self.subTest(index=index):
                owner = self.store(str(index))
                if seed:
                    owner.append(decoded(0), 5)
                with self.assertRaises((ValueError, OverflowError)):
                    owner.append(decoded(sequence), time_ns)
                self.assertEqual(owner.state, 'failed')
                self.assertTrue(owner.closed)
                self.assertEqual(owner.budget.ram_bytes, 4096)
                with self.assertRaises(ResultClosedError):
                    owner.seal()

    def test_existing_directory_rejected_and_customer_named_directory_allowed(self):
        """已有目录保哨兵；测试根内名为RefProjects的客户目录可用。

        参数: 无。返回: None。异常: 原拒绝或写入边界/借用费用断言失败。
        """
        existing = self.root / 'existing'
        existing.mkdir()
        sentinel = existing / 'keep.bin'
        sentinel.write_bytes(b'keep')
        budget = self.budget()
        with self.assertRaises(FileExistsError):
            RawFrameStore(budget, existing, 'raw_source')
        self.assertEqual(sentinel.read_bytes(), b'keep')
        self.assertEqual(tuple(existing.iterdir()), (sentinel,))
        allowed = self.root / 'RefProjects' / 'new'
        allowed.parent.mkdir()
        marker=allowed.parent/'user.txt'
        marker.write_bytes(b'keep')
        owner=RawFrameStore(budget, allowed, 'raw_source')
        self.assertTrue(allowed.is_dir())
        owner.close()
        self.assertEqual(marker.read_bytes(),b'keep')
        self.assertEqual(budget.ram_bytes, 4096)

    def test_constructor_reserve_after_cancel_and_mkdir_original_error_recover(self):
        """构造首笔reserve成功后取消或mkdir失败均有实际owner，不能抵销借用费用。

        参数: 无。返回: None。异常: 原故障或未返回owner/账本断言失败。
        """
        budget, marker = self.budget(), KeyboardInterrupt('constructor reserve after')
        original = budget.reserve_ram

        def reserve(amount):
            """真实预约后抛同一取消。参数: amount。返回: 不成功。异常: marker。"""
            original(amount)
            raise marker

        with patch.object(budget, 'reserve_ram', new=reserve):
            with self.assertRaises(KeyboardInterrupt) as caught:
                RawFrameStore(budget, self.root / 'reserve', 'raw_source')
        self.assertIs(caught.exception, marker)
        owner = caught.exception.raw_frame_store_cleanup_owner
        self.assertTrue(owner.closed)
        self.assertEqual(budget.ram_bytes, 4096)
        failure = OSError('actual mkdir rejection')
        with patch.object(Path, 'mkdir', side_effect=failure):
            with self.assertRaises(OSError) as caught:
                RawFrameStore(budget, self.root / 'mkdir', 'raw_source')
        self.assertIs(caught.exception, failure)
        self.assertTrue(caught.exception.raw_frame_store_cleanup_owner.closed)
        self.assertEqual(budget.ram_bytes, 4096)

    def test_append_reserve_after_cancel_closes_real_writer(self):
        """append本笔预约后取消仍登记实际槽并保同一父取消，真实writer关闭。

        参数: 无。返回: None。异常: 原取消或资源/费用断言失败。
        """
        owner, marker = self.store(), KeyboardInterrupt('append reserve after')
        handle, original = owner._writer, owner.budget.reserve_ram

        def reserve(amount):
            """真实预约后取消。参数: amount。返回: 不成功。异常: marker。"""
            original(amount)
            raise marker

        with patch.object(owner.budget, 'reserve_ram', new=reserve):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.append(decoded(), 5)
        self.assertIs(caught.exception, marker)
        self.assertIs(marker.raw_frame_store_cleanup_owner, owner)
        self.assertTrue(handle.closed and owner.closed)
        self.assertEqual(owner.count, 0)
        self.assertEqual(owner.file_path.read_bytes(), b'')
        self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_row_limit_and_spool_quota_reject_before_write(self):
        """行上限/磁盘配额在真实write前拒绝，不把零写入前缀封口。

        参数: 无。返回: None。异常: 原拒绝或计数/文件/费用断言失败。
        """
        for index, limit in enumerate((1, 65536)):
            budget = self.budget(quota=1 if limit == 65536 else None)
            owner = self.store(str(index), budget=budget, max_row_bytes=limit)
            with self.assertRaises(ValueError if limit == 1 else BudgetExceededError):
                owner.append(decoded(), 5)
            self.assertEqual(owner.file_path.read_bytes(), b'')
            self.assertEqual(owner.count, 0)
            self.assertTrue(owner.closed)
            self.assertEqual(budget.ram_bytes, 4096)
            self.assertEqual(budget.spool_bytes, 0)

    def test_spool_reservation_after_cancel_is_retained_not_deducted(self):
        """累计磁盘申请后取消保原预留，即便尚未write也不冒充已归还。

        参数: 无。返回: None。异常: 原取消或累计账本/零写入断言失败。
        """
        owner, marker = self.store(), KeyboardInterrupt('spool reserve after')
        original = owner.budget.reserve_spool

        def reserve(amount):
            """先真实预留磁盘再取消。参数: amount。返回: 不成功。异常: marker。"""
            original(amount)
            raise marker

        with patch.object(owner.budget, 'reserve_spool', new=reserve):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.append(decoded(), 5)
        self.assertIs(caught.exception, marker)
        self.assertGreater(owner.spool_bytes, 0)
        self.assertEqual(owner.spool_bytes, owner.budget.spool_bytes)
        self.assertEqual(owner.file_path.read_bytes(), b'')
        self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_partial_write_preserves_primary_under_persistent_cleanup_failure(self):
        """真实写五字节后普通错/父取消，持续close副取消不能盖主错或丢FD。

        参数: 无。返回: None。异常: 原主错或最高owner/poison/恢复断言失败。
        """
        for index, primary in enumerate((RuntimeError('write primary'), KeyboardInterrupt('write primary'))):
            actual_open, handles = Path.open, []

            def opened(path, *args, **kwargs):
                """透传真实open，只包装本例writer。参数: path及原参数。返回: 真实FD代理。异常: 原IO。
                """
                actual = actual_open(path, *args, **kwargs)
                if args and args[0] == 'xb':
                    wrapped = ActualFile(actual)
                    wrapped.write_error, wrapped.partial_bytes = primary, 5
                    wrapped.close_error = KeyboardInterrupt('cleanup secondary')
                    handles.append(wrapped)
                    return wrapped
                return actual

            with patch.object(Path, 'open', new=opened):
                owner = self.store(str(index))
                with self.assertRaises(type(primary)) as caught:
                    owner.append(decoded(), 5)
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.raw_frame_store_cleanup_owner, owner)
            self.assertFalse(owner.closed or handles[0].actual.closed)
            self.assertEqual(owner.count, 0)
            self.assertIsNone(owner.sha256)
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
                self.assertFalse(owner.closed)
            handles[0].close_error = None
            owner.close()
            self.assertTrue(handles[0].actual.closed and owner.closed)
            self.assertEqual(owner.file_path.stat().st_size, 5)
            self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_seal_writer_close_failure_never_exposes_complete_sha(self):
        """seal真实writer持续close前取消，条数存在但SHA/可读完成事实不能提前开放。

        参数: 无。返回: None。异常: 原取消或真实FD/状态/恢复断言失败。
        """
        actual_open, handles = Path.open, []
        marker = KeyboardInterrupt('seal close before')

        def opened(path, *args, **kwargs):
            """包装真实writer。参数: path及open参数。返回: 原FD或代理。异常: 原IO。
            """
            actual = actual_open(path, *args, **kwargs)
            if args and args[0] == 'xb':
                wrapped = ActualFile(actual)
                handles.append(wrapped)
                return wrapped
            return actual

        with patch.object(Path, 'open', new=opened):
            owner = self.store()
        owner.append(decoded(), 5)
        handles[0].close_error = marker
        with self.assertRaises(KeyboardInterrupt) as caught:
            owner.seal()
        self.assertIs(caught.exception, marker)
        self.assertFalse(owner.closed or handles[0].actual.closed)
        self.assertEqual(owner.state, 'cancelled')
        self.assertIsNone(owner.sha256)
        with self.assertRaises(ResultClosedError):
            owner.iter_frames()
        handles[0].close_error = None
        owner.close()
        self.assertTrue(handles[0].actual.closed)
        self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_reader_registration_before_after_failure_keeps_unreturned_actual_fd(self):
        """登记前/后MemoryError且真实FD持续关失败，最高父保未返回reader并可恢复。

        参数: 无。返回: None。异常: 原登记错或责任/FD/借用费用断言失败。
        """
        for index, after in enumerate((False, True)):
            owner = self.populated(str(index))
            marker = MemoryError('registration primary')
            registry = RejectingSet(marker, after)
            owner._readers = registry
            actual_open, handles = Path.open, []

            def opened(path, *args, **kwargs):
                """包装同次真实reader的close。参数: 原open参数。返回: FD代理。异常: 原IO。
                """
                actual = actual_open(path, *args, **kwargs)
                if args and args[0] == 'rb':
                    wrapped = ActualFile(actual)
                    wrapped.close_error = KeyboardInterrupt('reader cleanup')
                    handles.append(wrapped)
                    return wrapped
                return actual

            with patch.object(Path, 'open', new=opened):
                with self.assertRaises(MemoryError) as caught:
                    owner.iter_frames()
            self.assertIs(caught.exception, marker)
            self.assertIs(marker.raw_frame_store_cleanup_owner, owner)
            self.assertIs(owner._pending_reader, registry.actual_reader)
            self.assertFalse(handles[0].actual.closed or owner.closed)
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            handles[0].close_error = None
            owner.close()
            self.assertTrue(handles[0].actual.closed and registry.actual_reader.closed)
            self.assertIsNone(owner._pending_reader)
            self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_reader_close_before_after_cancel_preserves_other_live_reader(self):
        """reader的真实close前/后取消可重试，不能关同store另一独立FD。

        参数: 无。返回: None。异常: 原取消或隔离/费用/真实EOF断言失败。
        """
        for index, after in enumerate((False, True)):
            owner = self.populated(str(index))
            actual_open, handles = Path.open, []
            marker = KeyboardInterrupt('reader close boundary')

            def opened(path, *args, **kwargs):
                """只包装本例新reader。参数: 原open参数。返回: 真实FD代理。异常: 原IO。
                """
                actual = actual_open(path, *args, **kwargs)
                wrapped = ActualFile(actual)
                handles.append(wrapped)
                return wrapped

            with patch.object(Path, 'open', new=opened):
                first, second = owner.iter_frames(), owner.iter_frames()
            self.assertEqual(next(first).sequence, 0)
            handles[0].close_error, handles[0].close_after = marker, after
            for _ in range(1 if after else 3):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    first.close()
                self.assertIs(caught.exception, marker)
                self.assertFalse(first.closed or handles[1].actual.closed)
            self.assertEqual(handles[0].actual.closed, after)
            handles[0].close_error = None
            first.close()
            self.assertEqual([row.sequence for row in second], [0, 1, 2])
            self.assertTrue(second.verified_eof)
            owner.close()
            self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_reader_constructor_reserve_after_cancel_has_highest_parent(self):
        """未返回reader在首笔预约后取消仍已安装父槽，恢复不遗失任何真实费用。

        参数: 无。返回: None。异常: 原取消或owner/借用费用断言失败。
        """
        owner = self.populated()
        original, marker = owner.budget.reserve_ram, KeyboardInterrupt('reader reserve after')

        def reserve(amount):
            """真实预约后抛原取消。参数: amount。返回: 不成功。异常: marker。"""
            original(amount)
            raise marker

        with patch.object(owner.budget, 'reserve_ram', new=reserve):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.iter_frames()
        self.assertIs(caught.exception, marker)
        self.assertIs(marker.raw_frame_store_cleanup_owner, owner)
        self.assertTrue(owner.closed)
        self.assertIsNone(owner._pending_reader)
        self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_release_before_three_failures_and_after_cancel_are_idempotent(self):
        """自有费用抵销前持续三次失败保槽；抵销后取消不重复扣借用4096标记。

        参数: 无。返回: None。异常: 原取消或真实账本/关闭时点断言失败。
        """
        for index, after in enumerate((False, True)):
            owner = self.store(str(index))
            handle, original = owner._writer, owner.budget.release_ram
            marker = KeyboardInterrupt('release boundary')

            def release(amount):
                """只在本笔真实抵销前/后取消。参数: amount。返回: 不成功。异常: marker。"""
                if after:
                    original(amount)
                raise marker

            with patch.object(owner.budget, 'release_ram', new=release):
                for _ in range(1 if after else 3):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        owner.close()
                    self.assertIs(caught.exception, marker)
                    self.assertEqual(owner.closed, after)
                    self.assertTrue(handle.closed)
            owner.close()
            owner.close()
            self.assertTrue(owner.closed)
            self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_valid_reencoded_tamper_is_detected_by_full_stream_sha(self):
        """字段仍合法且序号/条数相同的载荷篡改，只有真实完整SHA可拒绝。

        参数: 无。返回: None。异常: 原完整性拒绝或未验证EOF/费用断言失败。
        """
        owner = self.populated()
        original_hash = owner.sha256
        lines = owner.file_path.read_bytes().splitlines(keepends=True)
        packet = json.loads(lines[0])
        packet['frame']['data_hex'] = '010203'
        lines[0] = json.dumps(current_fixture(packet), sort_keys=True, separators=(',', ':')).encode() + b'\n'
        owner.file_path.write_bytes(b''.join(lines))
        reader = owner.iter_frames()
        self.assertEqual(next(reader).frame.data, b'\x01\x02\x03')
        self.assertEqual(next(reader).sequence, 1)
        self.assertEqual(next(reader).sequence, 2)
        with self.assertRaisesRegex(ResultFormatError, 'SHA'):
            next(reader)
        self.assertFalse(reader.verified_eof)
        self.assertTrue(reader.handle.closed and owner.closed)
        self.assertEqual(owner.sha256, original_hash)
        self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_count_suffix_and_missing_newline_corruption_are_rejected(self):
        """少一条、额外后缀及末行缺换行均不能把已交付前缀当完整EOF。

        参数: 无。返回: None。异常: 原格式拒绝或真实FD/poison断言失败。
        """
        for index, kind in enumerate(('missing', 'suffix', 'unterminated')):
            owner = self.populated(str(index))
            lines = owner.file_path.read_bytes().splitlines(keepends=True)
            payload = b''.join(lines[:-1]) if kind == 'missing' else b''.join(lines)
            if kind == 'suffix':
                payload += lines[0]
            if kind == 'unterminated':
                payload = payload[:-1]
            owner.file_path.write_bytes(payload)
            reader = owner.iter_frames()
            with self.assertRaises(ResultFormatError):
                list(reader)
            self.assertTrue(owner.closed and reader.handle.closed)
            self.assertFalse(reader.verified_eof)
            self.assertEqual(owner.budget.ram_bytes, 4096)


# 仅测试运行器显式调用才执行；导入不会创建临时文件或启动CAN进程。
if __name__ == '__main__':
    unittest.main()
