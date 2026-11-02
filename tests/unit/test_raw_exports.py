"""独立核原始导出索引、有限复制和真实资源失败恢复，不调用CAN旧链。

输入是本专项在work独占目录生成的有限不透明文件字节及手工范围/摘要，输出为
冻结记录、真实JSONL/副本、完整EOF与预算/FD责任断言。文件只用于本层字节复制
验证，不冒充合法BLF或旧writer验收；真正CAN生成/回读由独立writer与AnalysisRunner专项
完成。每例借用一笔预算，所有真实owner关闭后应恰好回到借款，最后抵销为0。
故障注入只包装真实FD及实际reserve/release，不制造半初始化owner或补余额差；
持续关闭失败、释放前后取消、未返回reader与EOF关闭取消均保原异常及恢复对象。
产物保留在work并标home；不修改原日志、DBC、RefProjects或调用旧解码/写出路径。
"""

from configuration_fixtures import current_fixture

# 只自建小字节样本、独立手算SHA和公开冻结模型，不复用其他TestCase夹具。
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis.core.models import Interval
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError, ResultFormatError
from chronaxis.results.raw_exports import RawExportRecord, RawExportStore


WORK = Path(__file__).resolve().parents[2] / 'work' / 'm2-can-tests'


class ActualFile:
    """透明包住实际FD，可在真实close前后失败或保长度损坏写入字节。"""

    def __init__(self, actual):
        """保存真实FD及故障开关。参数: actual实际FileIO。返回: 代理。异常: 无。"""
        self.actual, self.close_error, self.write_error = actual, None, None
        self.after_close = self.corrupt = False

    def __getattr__(self, name):
        """透传真实属性。参数: name属性名。返回: 原属性。异常: 原属性错误。"""
        return getattr(self.actual, name)

    def write(self, payload):
        """在实际FD写有限原字节或等长损坏，亦可抛原取消。

        参数: payload有限bytes/view。返回: 实际写入数。异常: write_error或原IO错误。
        """
        if self.write_error is not None:
            raise self.write_error
        if self.corrupt and payload:
            payload = bytes((payload[0] ^ 1,)) + bytes(payload[1:])
        return self.actual.write(payload)

    def close(self):
        """真实关闭前或后抛同一故障，closed始终来自实际FD。

        参数: 无。返回: 实际close值。异常: close_error或原close错误，可解除后重试。
        """
        if self.close_error is not None and not self.after_close:
            raise self.close_error
        result = self.actual.close()
        if self.close_error is not None:
            raise self.close_error
        return result


class FailingSet(set):
    """只在实际登记后失败，验证未返回reader从父pending槽仍可恢复。"""

    def add(self, item):
        """先加入真实集合再取消。参数: item真实reader。返回: 不成功。异常: 原marker。"""
        super().add(item)
        raise self.marker


class RawExportTests(unittest.TestCase):
    """每例独占home工作根、共享真实账本和真实store列表，退出核借款不被多扣。"""

    def setUp(self):
        """建立工作根和借用预算。参数: 无。返回: None。异常: 原目录/预算错误。"""
        # work可能是跨盘链接，故障注入与copy实际使用同一物理绝对路径。
        self.root = (WORK / ('raw-exports-home-' + uuid4().hex)).resolve()
        self.root.mkdir(parents=True)
        self.budget, self.borrowed, self.stores = ResourceBudget(64 * 1024 ** 2), 8192, []
        self.budget.reserve_ram(self.borrowed)

    def tearDown(self):
        """通过所有实际owner关FD/费用，保磁盘并最终回0。

        参数: 无。返回: None。异常: 真实关闭错误或借款/预算断言失败，不吞资源故障。
        """
        for store in reversed(self.stores):
            store.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        self.budget.release_ram(self.borrowed)
        self.assertEqual(self.budget.ram_bytes, 0)

    def store(self, *, budget=None, label='home'):
        """创建并登记实际仓。参数: budget可选独立账本；label原设备标签。返回: store。
        异常: 原构造/目录/预算错误；成功实例才加入正常清理列表。
        """
        owner = RawExportStore(self.budget if budget is None else budget,
            self.root / ('store-' + str(len(self.stores))), 'bus', 'session', label)
        self.stores.append(owner)
        return owner

    def record(self, owner, *, status='exported', payload=b'opaque-BLF-bytes\x00\xff', frames=3):
        """独立生成当前号事实；不透明文件由夹具模拟原writer先预留磁盘。

        参数: owner实际仓；status三态；payload有限字节；frames帧数。返回: RawExportRecord。
        异常: 原文件/预算/模型错误；此helper不解析字节或把它称为合法BLF。
        """
        index = owner.record_count
        requested = Interval(-2, 12)
        if status == 'exported':
            path = owner.next_path()
            owner.budget.reserve_spool(len(payload))
            path.write_bytes(payload)
            actual, file_name, digest, size = Interval(0, 8), f'raw_segments/{index:012d}.blf', sha256(payload).hexdigest(), len(payload)
        else:
            actual = Interval(5, 5) if status == 'empty_range' else None
            file_name = digest = None
            frames = size = 0
        return RawExportRecord(index, owner.source, owner.session_id, 'segment:' + str(index), 'window_main',
            requested, actual, frames, file_name, digest, size, status, owner.device_label)

    def sealed(self, *, payload=b'finite-original', frames=3):
        """建立一条实际文件/索引并封口。参数: payload/frames原事实。返回: (store,record)。
        异常: 原构建/封口错误；不重扫来源或调用CAN库。
        """
        owner = self.store()
        record = self.record(owner, payload=payload, frames=frames)
        owner.append(record)
        owner.seal()
        return owner, record

    def test_three_record_states_preserve_original_intervals_and_freeze(self):
        """正长零帧文件、原actual点、无观测各自保值，来源/设备及原范围冻结。

        参数: 无。返回: None。异常: 误合并三态、复制范围或冻结失效则失败。
        """
        owner = self.store(label='custom-home')
        expected = []
        for status in ('exported', 'empty_range', 'no_observation'):
            record = self.record(owner, status=status, payload=b'', frames=0)
            requested, actual = record.requested, record.actual
            owner.append(record)
            self.assertIs(record.requested, requested)
            self.assertIs(record.actual, actual)
            expected.append(record)
        owner.seal()
        self.assertEqual(tuple(owner.iter_records()), tuple(expected))
        self.assertEqual((owner.record_count, owner.file_count, owner.format), (3, 1, 'blf'))
        packed = [json.loads(line) for line in owner.inventory_path.read_bytes().splitlines()]
        self.assertEqual(packed[1]['actual'], {'start_ns': 5, 'end_ns': 5})
        self.assertIsNone(packed[2]['actual'])
        self.assertEqual(packed[0]['device_label'], 'custom-home')
        with self.assertRaises(FrozenInstanceError):
            expected[0].frame_count = 1
        facts = (owner.path, owner.inventory_path, owner.source, owner.session_id, owner.device_label,
                 owner.format, owner.record_count, owner.file_count, owner.sha256, owner.inventory_bytes)
        owner.close()
        self.assertEqual(facts, (owner.path, owner.inventory_path, owner.source, owner.session_id, owner.device_label,
                 owner.format, owner.record_count, owner.file_count, owner.sha256, owner.inventory_bytes))
        self.assertTrue(owner.inventory_path.exists())

    def test_models_reject_unsafe_types_ranges_paths_hashes_and_statuses(self):
        """严格拒bool数量、越界、越请求actual、路径穿越和三态文件矛盾，不做I/O。

        参数: 无。返回: None。异常: 任一坏事实被接收或构造尝试打开文件则失败。
        """
        owner = self.store()
        record = self.record(owner)
        cases = dict(index=[True, -1, 10 ** 12], frame_count=[False, -1, 1 << 63],
            byte_count=[True, -1, 1 << 63], source=['bad.source', '', 1], session_id=['x y', ''],
            segment_id=['', '\x00bad', 'a\nb'], window_id=[''], device_label=['', '\x7f'],
            requested=[(0, 12), None], actual=[Interval(-3, 1), Interval(0, 13), Interval(0, 0), None],
            file_name=['../outside.blf', '/raw_segments/000000000000.blf', 'raw_segments/000000000001.blf'],
            sha256=['a' * 63, 'z' * 64, None], status=['no_observation', 'empty_range', 'other', True])
        with patch.object(Path, 'open', side_effect=AssertionError('model must not open')):
            for field, values in cases.items():
                for value in values:
                    with self.subTest(field=field, value=value), self.assertRaises((TypeError, ValueError, OverflowError)):
                        replace(record, **{field: value})
            with self.assertRaises(ValueError):
                replace(record, segment_id='a' * 65536)
            upper = replace(record, sha256=record.sha256.upper())
            self.assertEqual(upper.sha256, record.sha256.upper())
            end = (1 << 63) - 1
            boundary = replace(record, requested=Interval(end - 1, end), actual=Interval(end - 1, end))
            self.assertEqual(boundary.actual.end_ns, end)

    def test_empty_store_next_path_is_noncreating_and_rejects_existing_or_ref_root(self):
        """计算路径不创建BLF，空仓可封口/复制，已有目录或Ref路径保持原状。

        参数: 无。返回: None。异常: 错误创建文件、覆盖既有路径或误计BLF费用则失败。
        """
        owner = self.store()
        path = owner.next_path()
        self.assertEqual(path.relative_to(owner.path).as_posix(), 'raw_segments/000000000000.blf')
        self.assertFalse(path.exists())
        owner.seal()
        reader = owner.iter_records()
        self.assertEqual(tuple(reader), ())
        self.assertTrue(reader.closed and reader.verified_eof)
        self.assertEqual((owner.record_count, owner.file_count, owner.inventory_bytes, owner.spool_bytes), (0, 0, 0, 0))
        self.assertEqual(owner.sha256, sha256(b'').hexdigest())
        destination = self.root / 'published-empty'
        self.assertEqual(owner.copy_to(destination).read_bytes(), b'')
        before = self.budget.ram_bytes
        with self.assertRaises(FileExistsError):
            RawExportStore(self.budget, owner.path, 'bus', 'session', 'home')
        self.assertEqual(self.budget.ram_bytes, before)
        forbidden = self.root / 'RefProjects' / 'new-raw'
        with self.assertRaises(ValueError):
            RawExportStore(self.budget, forbidden, 'bus', 'session', 'home')
        self.assertFalse(forbidden.exists())
        self.assertEqual(self.budget.ram_bytes, before)

    def test_index_spool_is_additive_without_double_counting_original_files(self):
        """连续四条可有无文件空洞，索引只新增本行spool，原文件费用保持一次。

        参数: 无。返回: None。异常: 重复计算原BLF、错误编号或流摘要/条数不符则失败。
        """
        owner = self.store()
        expected, original_bytes = [], 0
        for status in ('exported', 'no_observation', 'empty_range', 'exported'):
            record = self.record(owner, status=status)
            original_bytes += record.byte_count
            expected.append(record)
            owner.append(record)
        owner.seal()
        self.assertEqual(tuple(owner.iter_records()), tuple(expected))
        self.assertEqual((owner.record_count, owner.file_count), (4, 2))
        self.assertEqual(owner.spool_bytes, owner.inventory_bytes)
        self.assertEqual(self.budget.spool_bytes, original_bytes + owner.spool_bytes)
        self.assertEqual(owner.sha256, sha256(owner.inventory_path.read_bytes()).hexdigest())
        self.assertTrue((owner.path / 'raw_segments/000000000003.blf').exists())
        self.assertFalse((owner.path / 'raw_segments/000000000001.blf').exists())

    def test_append_rejects_wrong_owner_or_index_before_writing_prefix(self):
        """索引/来源/会话/设备不匹配不能写入有效前缀，失败仍完整释放自有费用。

        参数: 无。返回: None。异常: 错误事实获接收、计数推进或借款被释放则失败。
        """
        for changes in (dict(index=1, file_name='raw_segments/000000000001.blf'), dict(source='other'),
                        dict(session_id='another'), dict(device_label='work')):
            owner = self.store()
            record = self.record(owner)
            with self.subTest(changes=changes), self.assertRaises(ValueError) as caught:
                owner.append(replace(record, **changes))
            self.assertIs(caught.exception.raw_export_store_cleanup_owner, owner)
            self.assertTrue(owner.closed)
            self.assertEqual((owner.state, owner.record_count, owner.inventory_path.read_bytes()), ('failed', 0, b''))

    def test_append_validates_actual_file_byte_count_and_sha(self):
        """原文件缺失、截断、额外字节或同长改值均明确失败，不信任声明摘要。

        参数: 无。返回: None。异常: 任一损坏漏检或错误索引写出则失败。
        """
        for damaged in (None, b'', b'finite-original+', b'Finite-original'):
            owner = self.store()
            record = self.record(owner, payload=b'finite-original')
            path = owner.path / record.file_name
            if damaged is None:
                path.unlink()
            else:
                path.write_bytes(damaged)
            with self.subTest(damaged=damaged), self.assertRaises((FileNotFoundError, ResultFormatError)):
                owner.append(record)
            self.assertEqual((owner.state, owner.record_count), ('failed', 0))
            self.assertEqual(owner.inventory_path.read_bytes(), b'')
            self.assertTrue(owner.closed)

    def test_independent_readers_only_complete_eof_proves_full_index(self):
        """提前关reader不证明EOF，独立reader保各自位置，store关闭真实收回活FD。

        参数: 无。返回: None。异常: 错误共享位置、提前verified或活FD遗失则失败。
        """
        owner, record = self.sealed()
        first, second = owner.iter_records(), owner.iter_records()
        self.assertEqual(next(first), record)
        self.assertFalse(first.verified_eof)
        first.close()
        self.assertTrue(first.closed)
        self.assertFalse(first.verified_eof)
        self.assertEqual(tuple(second), (record,))
        self.assertTrue(second.verified_eof and second.handle.closed)
        live = owner.iter_records()
        owner.close()
        self.assertTrue(live.closed and live.handle.closed)
        self.assertFalse(live.verified_eof)
        with self.assertRaises(ResultClosedError):
            owner.iter_records()

    def test_index_corruption_suffix_hash_and_count_are_not_silently_accepted(self):
        """完整EOF前核有界JSON/归属，EOF核摘要和条数，真实文件后缀也不能忽略。

        参数: 无。返回: None。异常: 任一破坏被当作完整有效索引或reader未关则失败。
        """
        for kind in ('truncate', 'same_length', 'suffix', 'unknown', 'owner', 'count', 'oversized', 'duplicate'):
            owner, _ = self.sealed()
            original = owner.inventory_path.read_bytes()
            if kind == 'truncate':
                content = original[:-1]
            elif kind == 'same_length':
                content = original.replace(b'segment:0', b'segment:1')
            elif kind == 'suffix':
                content = original + original
            elif kind == 'unknown':
                item = json.loads(original)
                item['extra'] = True
                content = json.dumps(current_fixture(item)).encode() + b'\n'
            elif kind == 'owner':
                item = json.loads(original)
                item['source'] = 'other'
                content = json.dumps(current_fixture(item)).encode() + b'\n'
            elif kind == 'oversized':
                content = b' ' * 65537 + b'\n'
            elif kind == 'duplicate':
                content = b'{"index":0,"index":0}\n'
            else:
                content = b''
            owner.inventory_path.write_bytes(content)
            reader = owner.iter_records()
            with self.subTest(kind=kind), self.assertRaises(ResultFormatError):
                tuple(reader)
            self.assertTrue(owner.closed and reader.closed)
            self.assertFalse(reader.verified_eof)

    def test_repeated_copy_verifies_real_bytes_without_new_spool_or_source_changes(self):
        """两个新发布根仅复制已存字节/索引，真实SHA相同，不增分析spool或留FD。

        参数: 无。返回: None。异常: 复制重写原件、无界读或摘要/预算错误则失败。
        """
        payload = bytes(range(256)) * 513
        owner, record = self.sealed(payload=payload)
        source_index, baseline, spool = owner.inventory_path.read_bytes(), self.budget.ram_bytes, self.budget.spool_bytes
        for name in ('published-a', 'published-b'):
            destination = self.root / name
            destination.mkdir()
            (destination / 'events.csv').write_bytes(b'header\n')
            inventory = owner.copy_to(destination)
            self.assertEqual(inventory, destination / 'raw_segments.jsonl')
            self.assertEqual(inventory.read_bytes(), source_index)
            copied = destination / record.file_name
            self.assertEqual(copied.read_bytes(), payload)
            self.assertEqual(sha256(copied.read_bytes()).hexdigest(), record.sha256)
            self.assertEqual((destination / 'events.csv').read_bytes(), b'header\n')
            self.assertEqual((self.budget.ram_bytes, self.budget.spool_bytes), (baseline, spool))
        self.assertEqual((owner.path / record.file_name).read_bytes(), payload)
        self.assertEqual(owner.inventory_path.read_bytes(), source_index)
        self.assertEqual(tuple(owner.iter_records()), (record,))

    def test_copy_preflight_refuses_existing_artifacts_and_ref_directory(self):
        """已有原始索引或目录不得覆盖，Ref发布路径在创建前拒绝且不毒化已封口仓。

        参数: 无。返回: None。异常: 覆盖/创建受保护路径或拒绝后不能正常回读则失败。
        """
        owner, record = self.sealed()
        for name in ('raw_segments', 'raw_segments.jsonl'):
            destination = self.root / ('existing-' + name.replace('.', '-'))
            destination.mkdir()
            artifact = destination / name
            if name.endswith('.jsonl'):
                artifact.write_bytes(b'user-data')
            else:
                artifact.mkdir()
            with self.assertRaises(FileExistsError):
                owner.copy_to(destination)
            if artifact.is_file():
                self.assertEqual(artifact.read_bytes(), b'user-data')
        forbidden = self.root / 'RefProjects' / 'publication'
        with self.assertRaises(ValueError):
            owner.copy_to(forbidden)
        self.assertFalse(forbidden.exists())
        self.assertEqual(tuple(owner.iter_records()), (record,))

    def test_constructor_and_unreturned_reader_reserve_after_cancel_keep_real_owner(self):
        """首笔真实预约后取消且持续释放失败，未返回构造/reader仍由最高store恢复。

        参数: 无。返回: None。异常: 原KI身份、真实pending或借款断言失败。
        """
        reserve = self.budget.reserve_ram
        primary, secondary = KeyboardInterrupt('reserve after'), RuntimeError('release held')

        def reserved(amount):
            """真实预约后取消。参数: amount原金额。返回: 不成功。异常: 同一primary。"""
            reserve(amount)
            raise primary

        with patch.object(self.budget, 'reserve_ram', new=reserved), patch.object(self.budget, 'release_ram', side_effect=secondary):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.store()
            owner = caught.exception.raw_export_store_cleanup_owner
            self.stores.append(owner)
            self.assertIs(caught.exception, primary)
            self.assertFalse(owner.closed)
            self.assertIsNone(owner._writer)
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    owner.close()
        owner.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        owner, _ = self.sealed()
        primary = KeyboardInterrupt('reader reserve after')
        with patch.object(self.budget, 'reserve_ram', new=reserved), patch.object(self.budget, 'release_ram', side_effect=secondary):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.iter_records()
            self.assertIs(caught.exception, primary)
            reader = owner._pending_reader
            self.assertIsNotNone(reader)
            self.assertFalse(reader.closed or owner.closed)
            self.assertIsNone(reader.handle)
        owner.close()
        self.assertTrue(reader.closed)

    def test_reader_registration_and_real_fd_persistent_failure_keep_pending_slot(self):
        """add实际登记后取消且reader真FD持续关前失败，pending不被新构造覆盖。

        参数: 无。返回: None。异常: 原KI身份、实际FD/登记/恢复断言失败。
        """
        owner, _ = self.sealed()
        primary, secondary = KeyboardInterrupt('registered after'), RuntimeError('reader close')
        registry, handles, actual_open = FailingSet(), [], Path.open
        registry.marker = primary
        owner._readers = registry

        def opened(path, *args, **kwargs):
            """只包装真实索引reader。参数: 原open参数。返回: 实际FD/代理。异常: 原IO。"""
            result = actual_open(path, *args, **kwargs)
            if path == owner.inventory_path and args and args[0] == 'rb':
                result = ActualFile(result)
                result.close_error = secondary
                handles.append(result)
            return result

        try:
            with patch.object(Path, 'open', new=opened), self.assertRaises(KeyboardInterrupt) as caught:
                owner.iter_records()
            self.assertIs(caught.exception, primary)
            pending = owner._pending_reader
            self.assertIsNotNone(pending)
            self.assertIn(pending, owner._readers)
            self.assertFalse(handles[0].actual.closed or owner.closed)
            with self.assertRaises(ResultClosedError):
                owner.iter_records()
            self.assertIs(owner._pending_reader, pending)
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    owner.close()
        finally:
            for handle in handles:
                handle.close_error = None
            owner.close()
        self.assertTrue(pending.closed and handles[0].actual.closed)

    def test_eof_close_cancel_propagates_original_instead_of_stop_iteration(self):
        """最后记录后EOF真实close仍可KI，不能吞成StopIteration或提前verified。

        参数: 无。返回: None。异常: 原KI身份、FD/完成门槛或恢复断言失败。
        """
        owner, record = self.sealed()
        reader = owner.iter_records()
        self.assertEqual(next(reader), record)
        handle = ActualFile(reader.handle)
        reader.handle = handle
        primary = KeyboardInterrupt('EOF FD close')
        handle.close_error = primary
        try:
            with self.assertRaises(KeyboardInterrupt) as caught:
                next(reader)
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.raw_export_store_cleanup_owner, owner)
            self.assertFalse(reader.closed or reader.verified_eof or handle.actual.closed or owner.closed)
        finally:
            handle.close_error = None
            owner.close()
        self.assertTrue(reader.closed and handle.actual.closed)
        self.assertFalse(reader.verified_eof)

    def test_copy_write_cancel_and_persistent_target_close_preserve_primary_and_fds(self):
        """复制原KI和持续目标FD副错保handle，恢复/新目录重试不关sealed输入或其他reader。

        参数: 无。返回: None。异常: 主错被替换、FD丢失或自有费用/借款被误抵销则失败。
        """
        owner, record = self.sealed()
        independent = owner.iter_records()
        destination, handles, actual_open = self.root / 'copy-failed', [], Path.open
        primary, secondary = KeyboardInterrupt('copy write'), RuntimeError('target close')

        def opened(path, *args, **kwargs):
            """只包装实际目标BLF writer。参数: 原open参数。返回: 真实FD/代理。异常: 原IO。"""
            result = actual_open(path, *args, **kwargs)
            if path == destination / record.file_name and args and args[0] == 'xb':
                result = ActualFile(result)
                result.write_error, result.close_error = primary, secondary
                handles.append(result)
            return result

        try:
            with patch.object(Path, 'open', new=opened), self.assertRaises(KeyboardInterrupt) as caught:
                owner.copy_to(destination)
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.raw_export_store_cleanup_owner, owner)
            self.assertIs(owner._output_fd, handles[0])
            self.assertFalse(handles[0].actual.closed or owner.closed)
            self.assertIsNone(owner._input_fd)
            self.assertGreater(owner._held_cost, 0)
            self.assertEqual(owner.state, 'sealed')
            self.assertFalse(independent.closed)
            self.assertEqual(next(independent), record)
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    owner.recover_copy()
                self.assertIs(owner._output_fd, handles[0])
                self.assertFalse(owner.closed or independent.closed)
            blocked = self.root / 'must-not-replace-pending-copy'
            with self.assertRaises(RuntimeError):
                owner.copy_to(blocked)
            self.assertFalse(blocked.exists())
        finally:
            for handle in handles:
                handle.close_error = None
            owner.recover_copy()
        self.assertTrue(handles[0].actual.closed)
        self.assertFalse(owner.closed or independent.closed)
        retry = self.root / 'copy-after-recovery'
        self.assertEqual(owner.copy_to(retry).read_bytes(), owner.inventory_path.read_bytes())
        self.assertEqual((retry / record.file_name).read_bytes(), (owner.path / record.file_name).read_bytes())
        self.assertEqual(tuple(independent), ())
        self.assertTrue(independent.verified_eof)
        self.assertEqual(self.budget.ram_bytes, self.borrowed + owner._fixed_cost)

    def test_destination_corruption_is_detected_by_real_copy_roundtrip(self):
        """BLF或索引真write返回正确长度但改值时，副本回读SHA仍须失败，原件保持。

        参数: 无。返回: None。异常: 仅信write长度、未核副本或原件被改写则失败。
        """
        for target_kind in ('blf', 'index'):
            owner, record = self.sealed()
            destination, actual_open = self.root / ('copy-corrupt-' + target_kind), Path.open
            target = destination / (record.file_name if target_kind == 'blf' else 'raw_segments.jsonl')
            original = (owner.path / record.file_name).read_bytes()

            def opened(path, *args, **kwargs):
                """只破坏真实目标写入。参数: 原open参数。返回: 实际FD/代理。异常: 原IO。"""
                result = actual_open(path, *args, **kwargs)
                if path == target and args and args[0] == 'xb':
                    result = ActualFile(result)
                    result.corrupt = True
                return result

            with patch.object(Path, 'open', new=opened), self.assertRaises(ResultFormatError):
                owner.copy_to(destination)
            self.assertEqual((owner.path / record.file_name).read_bytes(), original)
            self.assertFalse(owner.closed)
            self.assertEqual(owner.state, 'sealed')
            retry = self.root / ('copy-after-corrupt-output-' + target_kind)
            self.assertEqual(owner.copy_to(retry).read_bytes(), owner.inventory_path.read_bytes())
            self.assertEqual((retry / record.file_name).read_bytes(), original)

    def test_output_error_or_cancel_can_retry_new_directory_and_other_reader_survives(self):
        """真实目标write的普通错/KI/SystemExit只清本copy，固定输入费与独立reader保持。

        参数: 无。返回: None。异常: 主错身份改变、输入关闭、费用误扣或重试字节错误则失败。
        """
        for primary in (OSError('actual output write'), KeyboardInterrupt('actual output cancel'), SystemExit('actual output exit')):
            owner, record = self.sealed()
            independent = owner.iter_records()
            baseline, original_spool = self.budget.ram_bytes, self.budget.spool_bytes
            destination, actual_open = self.root / ('output-error-' + str(len(self.stores))), Path.open

            def opened(path, *args, **kwargs):
                """仅目标真writer写失败。参数: 原open参数。返回: 真FD/代理。异常: 原IO。"""
                result = actual_open(path, *args, **kwargs)
                if path == destination / record.file_name and args and args[0] == 'xb':
                    result = ActualFile(result)
                    result.write_error = primary
                return result

            with patch.object(Path, 'open', new=opened), self.assertRaises(type(primary)) as caught:
                owner.copy_to(destination)
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.raw_export_store_cleanup_owner, owner)
            self.assertEqual(owner.state, 'sealed')
            self.assertFalse(owner.closed or independent.closed)
            self.assertEqual((owner._copy_cost, owner._io_cost), (0, 0))
            self.assertEqual(self.budget.ram_bytes, baseline)
            self.assertEqual(self.budget.spool_bytes, original_spool)
            self.assertEqual(next(independent), record)
            retry = self.root / ('output-retry-' + str(len(self.stores)))
            self.assertEqual(owner.copy_to(retry).read_bytes(), owner.inventory_path.read_bytes())
            self.assertEqual((retry / record.file_name).read_bytes(), (owner.path / record.file_name).read_bytes())
            self.assertEqual(tuple(independent), ())
            owner.close()
            self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_copy_input_index_or_blf_corruption_still_poisons_sealed_store(self):
        """源索引/BLF损坏或实际删除仍poison全部输入，不能误当可重试输出故障。

        参数: 无。返回: None。异常: 输入破坏可成功发布、仍称sealed或实际reader遗失则失败。
        """
        for kind in ('index', 'blf', 'index_missing', 'blf_missing'):
            owner, record = self.sealed()
            independent = owner.iter_records()
            if kind == 'index':
                owner.inventory_path.write_bytes(b'')
            elif kind == 'blf':
                (owner.path / record.file_name).write_bytes(b'Finite-original')
            else:
                missing = owner.inventory_path if kind == 'index_missing' else owner.path / record.file_name
                if kind == 'index_missing':
                    # Windows不允许删除尚有普通读FD的文件；先真实关闭本独立reader再删源。
                    independent.close()
                missing.unlink()
            expected = FileNotFoundError if kind.endswith('_missing') else ResultFormatError
            with self.subTest(kind=kind), self.assertRaises(expected) as caught:
                owner.copy_to(self.root / ('bad-input-' + kind))
            self.assertIs(caught.exception.raw_export_store_cleanup_owner, owner)
            if kind.endswith('_missing'):
                self.assertIsNone(caught.exception.__cause__)
                self.assertEqual(Path(caught.exception.filename), missing)
            self.assertEqual(owner.state, 'failed')
            self.assertTrue(owner.closed and independent.closed and independent.handle.closed)
            self.assertEqual(self.budget.ram_bytes, self.borrowed)
            with self.assertRaises(ResultClosedError):
                owner.copy_to(self.root / ('bad-input-retry-' + kind))

    def test_copy_reader_reserve_cancel_before_after_preserves_input_and_allows_retry(self):
        """未返回copy reader预约前/后KI只收回临时责任，原仓和其他reader仍可完整回读。

        参数: 无。返回: None。异常: 原KI身份、真实费用槽、reader隔离或新目录重试断言失败。
        """
        for after in (False, True):
            owner, record = self.sealed()
            independent = owner.iter_records()
            baseline, reserve, hits = self.budget.ram_bytes, self.budget.reserve_ram, []
            primary = KeyboardInterrupt('copy reader reserve ' + str(after))

            def reserved(amount):
                """仅临时reader真实笔前/后取消。参数: amount金额。返回: 原值。异常: primary。"""
                if amount == 65536 + 64 * 65536 + 16384 and not hits:
                    hits.append(amount)
                    if after:
                        reserve(amount)
                    raise primary
                return reserve(amount)

            destination = self.root / ('copy-reader-reserve-failed-' + str(after))
            with patch.object(self.budget, 'reserve_ram', new=reserved), self.assertRaises(KeyboardInterrupt) as caught:
                owner.copy_to(destination)
            self.assertIs(caught.exception, primary)
            self.assertEqual(len(hits), 1)
            self.assertEqual(owner.state, 'sealed')
            self.assertFalse(owner.closed or independent.closed)
            self.assertIsNone(owner._copy_reader)
            self.assertEqual(self.budget.ram_bytes, baseline)
            retry = self.root / ('copy-reader-reserve-retry-' + str(after))
            self.assertEqual(owner.copy_to(retry).read_bytes(), owner.inventory_path.read_bytes())
            self.assertEqual(tuple(independent), (record,))
            owner.close()
            self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_copy_reader_eof_close_persistent_cancel_can_recover_without_poisoning_input(self):
        """临时copy reader在真EOF关FD持续KI仍保其实际槽，不影响其他reader或新目录重试。

        参数: 无。返回: None。异常: 原取消被吞、输入poison、FD/费用遗失或重试断言失败。
        """
        owner, record = self.sealed()
        independent = owner.iter_records()
        actual_open, handles = Path.open, []
        primary = KeyboardInterrupt('copy reader EOF close')

        def opened(path, *args, **kwargs):
            """只包装本次copy的真实原索引FD。参数: 原open参数。返回: 真FD/代理。异常: 原IO。"""
            result = actual_open(path, *args, **kwargs)
            if path == owner.inventory_path and args and args[0] == 'rb':
                result = ActualFile(result)
                result.close_error = primary
                handles.append(result)
            return result

        try:
            with patch.object(Path, 'open', new=opened), self.assertRaises(KeyboardInterrupt) as caught:
                owner.copy_to(self.root / 'copy-reader-close-failed')
            self.assertIs(caught.exception, primary)
            pending = owner._copy_reader
            self.assertIsNotNone(pending)
            self.assertIs(pending.handle, handles[0])
            self.assertFalse(pending.closed or pending.verified_eof or handles[0].actual.closed)
            self.assertEqual(owner.state, 'sealed')
            self.assertFalse(owner.closed or independent.closed)
            self.assertEqual(next(independent), record)
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt) as held:
                    owner.recover_copy()
                self.assertIs(held.exception, primary)
                self.assertIs(owner._copy_reader, pending)
        finally:
            for handle in handles:
                handle.close_error = None
            owner.recover_copy()
        self.assertTrue(pending.closed and handles[0].actual.closed)
        self.assertFalse(pending.verified_eof or owner.closed or independent.closed)
        retry = self.root / 'copy-reader-close-retry'
        self.assertEqual(owner.copy_to(retry).read_bytes(), owner.inventory_path.read_bytes())
        self.assertEqual(tuple(independent), ())
        self.assertEqual(self.budget.ram_bytes, self.borrowed + owner._fixed_cost)

    def test_index_budget_and_release_before_after_cancellation_are_real_transactions(self):
        """索引配额失败保原文件，关闭费用释放前/后取消均不多扣借款且可恢复。

        参数: 无。返回: None。异常: 原预算/KI身份、spool或真实槽金额断言失败。
        """
        limited = ResourceBudget(16 * 1024 ** 2, spool_quota_bytes=1)
        owner = self.store(budget=limited)
        record = self.record(owner, status='no_observation')
        with self.assertRaises(BudgetExceededError):
            owner.append(record)
        self.assertTrue(owner.closed)
        self.assertEqual((limited.ram_bytes, limited.spool_bytes), (0, 0))
        for after in (False, True):
            owner, _ = self.sealed()
            release, target, hits = self.budget.release_ram, owner._fixed_cost, []
            primary = KeyboardInterrupt('release ' + str(after))

            def released(amount):
                """目标笔释放前/后原KI。参数: amount金额。返回: 原值。异常: 同一primary。"""
                if amount == target and not hits:
                    hits.append(amount)
                    if after:
                        release(amount)
                    raise primary
                return release(amount)

            with patch.object(self.budget, 'release_ram', new=released), self.assertRaises(KeyboardInterrupt) as caught:
                owner.close()
            self.assertIs(caught.exception, primary)
            self.assertEqual(owner._fixed_cost, 0 if after else target)
            self.assertEqual(owner.closed, after)
            owner.close()
            self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_index_writer_close_before_after_cancel_and_spool_after_cancel_preserve_truth(self):
        """索引真FD关闭前/后KI不伪造sealed；spool已预约后取消仍记本笔且保原主错。

        参数: 无。返回: None。异常: 原KI身份、真实FD/费用槽/累计spool或状态断言失败。
        """
        for after in (False, True):
            owner = self.store()
            owner.append(self.record(owner, status='no_observation'))
            writer, primary = ActualFile(owner._writer), KeyboardInterrupt('index close ' + str(after))
            owner._writer = writer
            writer.close_error, writer.after_close = primary, after
            try:
                with self.assertRaises(KeyboardInterrupt) as caught:
                    owner.seal()
                self.assertIs(caught.exception, primary)
                self.assertEqual(owner.state, 'failed')
                self.assertIsNone(owner.sha256)
                self.assertEqual(writer.actual.closed, after)
                self.assertEqual(owner.closed, after)
                if not after:
                    self.assertIs(owner._writer, writer)
                    for _ in range(3):
                        with self.assertRaises(KeyboardInterrupt):
                            owner.close()
            finally:
                writer.close_error = None
                owner.close()
            self.assertTrue(writer.actual.closed)
            self.assertEqual(self.budget.ram_bytes, self.borrowed)
        owner = self.store()
        record = self.record(owner, status='no_observation')
        reserve, before = self.budget.reserve_spool, self.budget.spool_bytes
        primary = KeyboardInterrupt('spool reserve after')

        def reserved(amount):
            """真实索引spool预约后取消。参数: amount原金额。返回: 不成功。异常: primary。"""
            reserve(amount)
            raise primary

        with patch.object(self.budget, 'reserve_spool', new=reserved), self.assertRaises(KeyboardInterrupt) as caught:
            owner.append(record)
        self.assertIs(caught.exception, primary)
        self.assertTrue(owner.closed)
        self.assertEqual(owner.inventory_path.read_bytes(), b'')
        self.assertGreater(owner.spool_bytes, 0)
        self.assertEqual(self.budget.spool_bytes - before, owner.spool_bytes)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)


if __name__ == '__main__':
    unittest.main()
