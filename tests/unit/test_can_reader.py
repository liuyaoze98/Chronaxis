"""独立核对真实旧CAN来源的批次、缺值、完整观测和资源移交。

静态类只用冻结声明及真实预算，断言构造/describe/创建read不读BLF/DBC或spawn。
真实类现场用can.BLFWriter生成四帧与手工DBC，原字节0/2/3/4经factor2/offset-1
应为-1/3/5/7 V；两个同刻原帧不合并，多别名分片不增加旧PULL。另用目标帧零载荷
引发原parse空dict，核该次MISSING且其他ID是未更新，随后有效值正常恢复。
所有原始帧从真实RawFrameStore回读，不以信号投影推断原行首末或重复扫BLF。
故障只在真实预约、FD close、父槽安装前后注入；最高owner/借用标记/其他read/最终0
由实际对象断言，不制造半初始化Process、store或替代数组。产物只在work独占目录，
保留输入/暂存，未验证用户真实日志、BLF发布、旧reader修复或整进程RSS。
"""

# 自生成小夹具和实际资源代理，不继承其他专项TestCase或用被测核作手算参考。
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import QualityFlag as Q, SignalDType as D, TimeType
from chronaxis.execution import can_reader as module
from chronaxis.legacy.records import LegacyCANField
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError
from chronaxis.sources.can_spec import LegacyCANSpec, CANSourceRef
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.protocol import SourceClosedError, SourceReadError


WORK = Path(__file__).resolve().parents[2] / 'work' / 'm2-can-tests'
HAS_CAN = all(importlib.util.find_spec(name) is not None for name in ('can', 'cantools', 'natsort'))
BASE = 1700000000.0
BASE_NS = 1700000000000000000
DBC = '''VERSION ""
NS_ :
BS_:
BU_: Vector__XXX
BO_ 256 Demo: 1 Vector__XXX
 SG_ Sample : 0|8@1+ (2,-1) [-1|509] "V" Vector__XXX
'''


class StoreReceiver:
    """测试中的真实新父owner，只拥有实际移交store，不仿造资源或费用。"""

    def __init__(self, budget):
        """安装真实空责任槽。参数: budget为同一共享账本。返回: owner。异常: 无。"""
        self._budget, self._raw_store, self.install_error = budget, None, None

    def __setattr__(self, name, value):
        """可在真实父槽安装后取消。参数: name/value。返回: None。异常: 同一install_error。"""
        object.__setattr__(self, name, value)
        if name == '_raw_store' and value is not None and getattr(self, 'install_error', None) is not None:
            raise self.install_error

    def close(self):
        """仅关闭新父实际store。参数: 无。返回: None。异常: 原store关闭错误可重试。"""
        if self._raw_store is not None:
            self._raw_store.close()
            if self._raw_store.closed:
                self._raw_store = None


class ActualWriter:
    """透明包装真实raw writer，只在close前持续取消，closed始终来自实际FD。"""

    def __init__(self, actual):
        """保留实际FD。参数: actual为FileIO。返回: 代理。异常: 无。"""
        self.actual, self.error = actual, None

    def __getattr__(self, name):
        """透传原能力。参数: name。返回: 实际属性。异常: 原属性错误。"""
        return getattr(self.actual, name)

    def close(self):
        """实际关闭前可持续抛同一取消。参数: 无。返回: 原close值。异常: error或真实错误。"""
        if self.error is not None:
            raise self.error
        return self.actual.close()


class CANFixture(unittest.TestCase):
    """每例独占work根与真实借款，关闭本例所有实际owner后才归还借款。"""

    def setUp(self):
        """建立本例根和共享预算。参数: 无。返回: None。异常: 原目录/预约错误。"""
        self.root = WORK / ('can-reader-home-' + uuid4().hex)
        self.root.mkdir(parents=True)
        self.budget, self.borrowed = ResourceBudget(256 * 1024 ** 2), 8192
        self.budget.reserve_ram(self.borrowed)
        self.adapters, self.reads, self.receivers = [], [], []
        self.path, self.dbc = self.root / 'input.blf', self.root / 'input.dbc'
        self.field = LegacyCANField(0, 'Sample', 0x100, False, False)

    def tearDown(self):
        """只经真实owner close恢复，不删除输入/暂存证据。

        参数: 无。返回: None。异常: 关闭或借用费用断言失败，不吞资源遗失。
        """
        for read in reversed(self.reads):
            read.close()
        for owner in self.receivers:
            owner.close()
        for adapter in reversed(self.adapters):
            adapter.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        self.budget.release_ram(self.borrowed)
        self.assertEqual(self.budget.ram_bytes, 0)

    def definitions(self, aliases=1, unit='V'):
        """声明同定位V与mV别名。参数: aliases数和原unit。返回: tuple。异常: 原模型错误。"""
        # 第二别名使用真实V→mV关系；不能把同一V单位配倍率2伪装为合法转换。
        return tuple(SignalDefinition('a' + str(index), 'can', self.field.key, D.FLOAT64,
            unit if index == 0 else 'mV', 1000000000, input_unit=unit,
            scale=1 if index == 0 else 1000) for index in range(aliases))

    def adapter(self, *, aliases=1, backend='numpy', signals=None):
        """创建真实静态来源，不启动。参数: 别名/后端/可选定义。返回: adapter。异常: 原构造错误。"""
        # 本夹具核旧逐条ProcessRead/B02全调用及费用；默认按需批协议由独立专项覆盖。
        spec = LegacyCANSpec('can', self.path, self.dbc, 0,
            TimebaseSpec('clock', TimeType.RELATIVE, 'synthetic_epoch'), offset_ns=-BASE_NS,
            decode_scope='all')
        adapter = module.BudgetedLegacyCANSourceAdapter(self.budget, spec, 'session',
            self.definitions(aliases) if signals is None else signals, backend=backend,
            work_dir=self.root / ('adapter-' + str(len(self.adapters))))
        self.adapters.append(adapter)
        return adapter

    def read(self, adapter, *, names=None, size=1):
        """创建同会话原请求及独立read。参数: adapter/投影/批次。返回: (原request, read)。异常: 原错误。"""
        request = ReadRequest('session', tuple(item.name for item in adapter.signals) if names is None else names,
            0, 1000000000, size)
        read = adapter.iter_batches_with_observation(request)
        self.reads.append(read)
        return request, read

    def receiver(self):
        """登记真实新父。参数: 无。返回: StoreReceiver。异常: 无主动异常。"""
        owner = StoreReceiver(self.budget)
        self.receivers.append(owner)
        return owner


class CANStaticTests(CANFixture):
    """不依赖可选CAN库的静态无IO与未返回责任专项。"""

    def test_static_describe_and_read_creation_do_not_touch_input_or_spawn(self):
        """未知输入仍可静态描述，字段时钟/单位仅declared；创建read不start。

        参数: 无。返回: None。异常: 不应发生的输入open/start或描述断言失败。
        """
        with patch.object(module.LegacyCANProcessRead, 'start', side_effect=AssertionError('no start')), \
                patch.object(Path, 'open', side_effect=AssertionError('no input open')):
            adapter = self.adapter()
            description = adapter.describe()
            request, read = self.read(adapter)
            self.assertIs(read.request, request)
            self.assertFalse(read.finished)
            self.assertIsNone(read._process)
            self.assertEqual(description.metadata_status, 'declared')
            self.assertIsNone(description.observation_start_ns)
            self.assertIsNone(description.observation_end_ns)
            self.assertEqual(description.fields[0].field.field, self.field.key)
            self.assertEqual(description.fields[0].metadata['input_unit'], 'V')
            with self.assertRaises(ResultClosedError):
                _ = read.observation
            with self.assertRaises(ResultClosedError):
                _ = read.runtime_metadata
        read.close()
        adapter.close()
        with self.assertRaises(SourceClosedError):
            adapter.describe()

    def test_unreturned_read_after_reserve_cancel_keeps_actual_parent_slot(self):
        """read首笔预约后取消且持续抵销失败，来源保实际未返回read，恢复不抵销借款。

        参数: 无。返回: None。异常: 原KI/关闭副错或实际责任/费用断言失败。
        """
        adapter = self.adapter()
        original, primary, secondary = self.budget.reserve_ram, KeyboardInterrupt('request reserve'), RuntimeError('release')

        def reserve(amount):
            """先真实预约后取消。参数: amount。返回: 不成功。异常: primary。"""
            original(amount)
            raise primary

        with patch.object(self.budget, 'reserve_ram', new=reserve), patch.object(self.budget, 'release_ram', side_effect=secondary):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.read(adapter)
            self.assertIs(caught.exception, primary)
            read = primary.can_observation_read_cleanup_owner
            self.reads.append(read)
            self.assertIs(adapter._uninstalled_request, read)
            self.assertIsNone(read._process)
            self.assertFalse(read.closed)
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    read.close()
        read.close()
        self.assertIsNone(adapter._uninstalled_request)
        self.assertEqual(self.budget.ram_bytes, self.borrowed + adapter._held_cost)

    def test_adapter_constructor_cancel_has_actual_highest_owner(self):
        """来源首笔预约后KI与持续抵销失败保真实constructor owner，未创建输入/子进程。

        参数: 无。返回: None。异常: 原KI或最高owner/借款断言失败。
        """
        original, primary = self.budget.reserve_ram, KeyboardInterrupt('source reserve')

        def reserve(amount):
            """真实预约后原KI。参数: amount。返回: 不成功。异常: primary。"""
            original(amount)
            raise primary

        with patch.object(self.budget, 'reserve_ram', new=reserve), \
                patch.object(self.budget, 'release_ram', side_effect=RuntimeError('release held')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.adapter()
            self.assertIs(caught.exception, primary)
            adapter = primary.can_source_cleanup_owner
            self.adapters.append(adapter)
            self.assertIsNone(adapter.work_dir)
            self.assertFalse(adapter.closed)
        adapter.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)


@unittest.skipUnless(HAS_CAN, '可选CAN依赖未全部安装')
class CANActualTests(CANFixture):
    """使用真实BLF/DBC和生产B1进程，不用控制worker替代正常路径。"""

    def write_input(self, rows=None, *, unit='V'):
        """现场生成有限真实输入。参数: rows为(offset秒,id,data,channel,extended,fd)；unit为DBC单位。
        返回: None。异常: 原CAN写入/stop或文件错误；不读取DBC/BLF补真值。
        """
        import can
        actual = rows if rows is not None else ((0, 0x100, b'\x00', 0, False, False),
            (.125, 0x100, b'\x02', 0, False, False), (.125, 0x100, b'\x03', 0, False, False),
            (.25, 0x100, b'\x04', 0, False, False))
        self.dbc.write_text(DBC.replace('"V"', '"' + unit + '"'), encoding='utf-8')
        writer = can.BLFWriter(str(self.path))
        try:
            for offset, frame_id, data, channel, extended, fd in actual:
                writer.on_message_received(can.Message(timestamp=BASE + offset, arbitration_id=frame_id,
                    is_extended_id=extended, channel=channel, data=data, is_fd=fd))
        finally:
            writer.stop()

    def test_real_four_frames_two_backends_alias_split_and_raw_store_once(self):
        """手算-1/3/5/7V及对应mV；拆为单样本批但原PULL仍5含EOF。

        参数: 无。返回: None。异常: 原生产错误或数值/引用/原序/完成/费用断言失败。
        """
        self.write_input()
        for backend in ('reference', 'numpy'):
            adapter = self.adapter(aliases=2, backend=backend)
            request, read = self.read(adapter, size=1)
            first = next(read)
            process = read._process
            batches = (first, *tuple(read))
            self.assertEqual(len(batches), 9)
            self.assertTrue(batches[-1].source_eof and batches[-1].sample_count == 0)
            self.assertTrue(all(batch.sample_count <= 1 for batch in batches))
            for index, expected in enumerate(((-1, 3, 5, 7), (-1000, 3000, 5000, 7000))):
                columns = [batch.series['a' + str(index)] for batch in batches if 'a' + str(index) in batch.series]
                self.assertEqual(tuple(column.values[0] for column in columns), expected)
                self.assertTrue(all(column.valid[0] and column.quality[0] == 0 for column in columns))
                self.assertEqual(tuple(int(column.sequence[0]) for column in columns), (0, 1, 2, 3))
                self.assertEqual(tuple(int(column.time_ns[0]) for column in columns), (0, 125000000, 125000000, 250000000))
                self.assertTrue(all(type(column.source_ref[0]) is CANSourceRef for column in columns))
                self.assertEqual(tuple(column.source_ref[0].yield_sequence for column in columns), (0, 1, 2, 3))
            self.assertEqual(process.counters, {'pulls_issued': 5, 'items_returned': 4, 'items_accepted': 4})
            self.assertTrue(process.closed and process.finished and read.finished)
            fact = read.observation
            self.assertIs(fact.request, request)
            self.assertEqual((fact.first_ns, fact.last_ns, fact.row_count), (0, 250000000, 4))
            self.assertEqual(read.runtime_metadata['fields'][0]['unit'], 'V')
            parent = self.receiver()
            raw = read.take_raw_store(parent)
            self.assertIs(parent._raw_store, raw)
            self.assertEqual([(row.sequence, row.time_ns, row.frame.data) for row in raw.iter_frames()],
                [(0, 0, b'\x00'), (1, 125000000, b'\x02'), (2, 125000000, b'\x03'), (3, 250000000, b'\x04')])
            read.close()
            adapter.close()
            self.assertFalse(raw.closed)
            self.assertEqual(self.budget.ram_bytes, self.borrowed + raw._held_cost)
            parent.close()

    def test_matching_missing_key_is_missing_update_other_id_is_not_update(self):
        """原parse空dict的目标帧发None/MISSING，非目标帧无列；后继有效观测恢复。

        参数: 无。返回: None。异常: 原输入错误或缺值口径/全部原帧断言失败。
        """
        self.write_input(((0, 0x100, b'\x00', 0, False, False), (.125, 0x101, b'\x01', 0, False, False),
            (.25, 0x100, b'', 0, False, False), (.375, 0x100, b'\x04', 0, False, False)))
        adapter = self.adapter()
        _, read = self.read(adapter)
        batches = tuple(read)
        columns = [batch.series['a0'] for batch in batches if 'a0' in batch.series]
        self.assertEqual(tuple(int(column.sequence[0]) for column in columns), (0, 2, 3))
        self.assertEqual(tuple(bool(column.valid[0]) for column in columns), (True, False, True))
        self.assertEqual(columns[1].original_values, (None,))
        self.assertEqual(int(columns[1].quality[0]), int(Q.MISSING))
        self.assertEqual(float(columns[-1].values[0]), 7)
        self.assertEqual(read.observation.row_count, 4)
        parent = self.receiver()
        raw = read.take_raw_store(parent)
        self.assertEqual([row.frame.arbitration_id for row in raw.iter_frames()], [0x100, 0x101, 0x100, 0x100])

    def test_empty_projection_still_scans_all_frames_and_final_eof_is_not_finish(self):
        """零投影仍全原序暂存；空EOF批交付后尚未StopIteration，不可借事实/移交。

        参数: 无。返回: None。异常: 原进程错误或全源/完成门槛断言失败。
        """
        self.write_input()
        adapter = self.adapter()
        request, read = self.read(adapter, names=())
        parent = self.receiver()
        batches = []
        while True:
            batch = next(read)
            batches.append(batch)
            if batch.source_eof:
                break
        self.assertEqual(len(batches), 5)
        self.assertTrue(all(batch.sample_count == 0 for batch in batches))
        self.assertFalse(read.finished)
        with self.assertRaises(ResultClosedError):
            _ = read.observation
        with self.assertRaises(ResultClosedError):
            read.take_raw_store(parent)
        with self.assertRaises(StopIteration):
            next(read)
        self.assertIs(read.observation.request, request)
        self.assertEqual(read.observation.row_count, 4)
        raw = read.take_raw_store(parent)
        self.assertEqual(raw.count, 4)

    def test_empty_and_single_point_raw_observations_are_distinct(self):
        """真实空BLF无可猜首末，单点是first=last=0且row_count1，均真实完整EOF。

        参数: 无。返回: None。异常: 原生成/读取或端点/计数断言失败。
        """
        for index, rows in enumerate(((), ((0, 0x100, b'\x02', 0, False, False),))):
            self.write_input(rows)
            adapter = self.adapter(signals=())
            _, read = self.read(adapter)
            self.assertTrue(tuple(read)[-1].source_eof)
            fact = read.observation
            self.assertEqual((fact.first_ns, fact.last_ns, fact.row_count),
                (None, None, 0) if index == 0 else (0, 0, 1))
            read.close()
            adapter.close()

    def test_same_request_two_reads_identity_and_completed_facts_survive_adapter_close(self):
        """同一请求并发两read身份独立，adapter.close关活read但不销毁已完成read事实。

        参数: 无。返回: None。异常: 原读取/关闭或所有权/事实断言失败。
        """
        self.write_input()
        adapter = self.adapter()
        request, first = self.read(adapter)
        second = adapter.iter_batches(request)
        self.reads.append(second)
        self.assertNotEqual(first.identity, second.identity)
        self.assertIs(first.request, second.request)
        tuple(first)
        next(second)
        second_process = second._process
        adapter.close()
        self.assertTrue(second.closed and second_process.closed)
        self.assertFalse(first.closed)
        self.assertIs(first.observation.request, request)
        self.assertEqual(first.runtime_metadata['fields'][0]['unit'], 'V')
        first.close()
        with self.assertRaises(ResultClosedError):
            _ = first.observation

    def test_runtime_unit_mismatch_rejects_before_pull_and_unknown_unit_stays_unverified(self):
        """非空DBC单位不等input_unit在PULL前拒绝；空单位原事实保留，不能升级verified。

        参数: 无。返回: None。异常: 原单位拒绝或同次元数据/零许可断言失败。
        """
        self.write_input()
        adapter = self.adapter(signals=self.definitions(unit='A'))
        _, read = self.read(adapter)
        captured, original = [], module.LegacyCANProcessRead.start

        def start(owner):
            """透传真实INIT并记录原owner。参数: owner。返回: 原self。异常: 原启动错误。"""
            captured.append(owner)
            return original(owner)

        with patch.object(module.LegacyCANProcessRead, 'start', new=start):
            with self.assertRaises(SourceReadError):
                next(read)
        self.assertEqual(captured[0].counters['pulls_issued'], 0)
        self.assertTrue(captured[0].closed and read.closed)
        self.write_input(unit='')
        adapter = self.adapter()
        _, read = self.read(adapter)
        next(read)
        self.assertIn(read.runtime_metadata['fields'][0]['unit'], (None, ''))
        with self.assertRaises(TypeError):
            read.runtime_metadata['fields'][0]['unit'] = 'V'
        tuple(read)

    def test_raw_store_handoff_installs_parent_before_post_assignment_cancel(self):
        """真实sealed store先装新父，安装后同一KI仍有父槽，read.close不关借用store。

        参数: 无。返回: None。异常: 原KI或最高真实父/独立生命周期/费用断言失败。
        """
        self.write_input()
        adapter = self.adapter()
        _, read = self.read(adapter)
        tuple(read)
        parent, primary = self.receiver(), KeyboardInterrupt('after parent installation')
        parent.install_error = primary
        with self.assertRaises(KeyboardInterrupt) as caught:
            read.take_raw_store(parent)
        self.assertIs(caught.exception, primary)
        raw = parent._raw_store
        self.assertIsNotNone(raw)
        self.assertEqual(raw.state, 'sealed')
        self.assertIsNone(read._raw_store)
        read.close()
        adapter.close()
        self.assertFalse(raw.closed)
        self.assertEqual(len(tuple(raw.iter_frames())), 4)
        self.assertEqual(self.budget.ram_bytes, self.borrowed + raw._held_cost)
        with self.assertRaises(ResultClosedError):
            read.take_raw_store(parent)
        parent.install_error = None
        parent.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_raw_writer_persistent_close_retains_owner_and_other_read(self):
        """实际raw FD连续三次关前KI保同一read/费用，另一read仍能交付原下一帧。

        参数: 无。返回: None。异常: 原KI或实际FD/隔离/恢复断言失败。
        """
        self.write_input()
        adapter = self.adapter()
        _, first = self.read(adapter)
        _, other = self.read(adapter)
        actual_open, handles = Path.open, []

        def opened(path, *args, **kwargs):
            """只包装真实raw writer。参数: 原open参数。返回: 原FD/代理。异常: 原IO。
            """
            actual = actual_open(path, *args, **kwargs)
            if path.name == 'raw_frames.jsonl' and args and args[0] == 'xb':
                wrapped = ActualWriter(actual)
                handles.append(wrapped)
                return wrapped
            return actual

        with patch.object(Path, 'open', new=opened):
            next(first)
        next(other)
        marker = KeyboardInterrupt('raw close before')
        handles[0].error = marker
        try:
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    first.close()
                self.assertIs(caught.exception, marker)
                self.assertIs(marker.can_observation_read_cleanup_owner, first)
                self.assertFalse(handles[0].actual.closed or first.closed)
            batch = next(other)
            self.assertEqual(int(batch.series['a0'].sequence[0]), 1)
        finally:
            handles[0].error = None
            first.close()
        self.assertTrue(handles[0].actual.closed)
        self.assertFalse(other.closed)
        tuple(other)

    def test_read_release_after_cancel_never_deducts_borrowed_fees_twice(self):
        """真实read固定费抵销后KI，完成资源关闭且槽0；重试不能多扣来源或借款。

        参数: 无。返回: None。异常: 原KI或实际账本/幂等断言失败。
        """
        self.write_input()
        adapter = self.adapter()
        _, read = self.read(adapter)
        next(read)
        original, target, primary, hits = self.budget.release_ram, read._fixed_cost, KeyboardInterrupt('after read release'), []

        def release(amount):
            """真实抵销目标本笔后取消。参数: amount。返回: 原值。异常: primary或原release错误。"""
            value = original(amount)
            if amount == target and not hits:
                hits.append(amount)
                raise primary
            return value

        with patch.object(self.budget, 'release_ram', new=release):
            with self.assertRaises(KeyboardInterrupt) as caught:
                read.close()
        self.assertIs(caught.exception, primary)
        self.assertEqual(read._fixed_cost, 0)
        self.assertTrue(read.closed)
        read.close()
        self.assertEqual(hits, [target])
        self.assertEqual(self.budget.ram_bytes, self.borrowed + adapter._held_cost)

    def test_explicit_target_channel_and_flags_filter_other_frames(self):
        """显式选择器跳过同ID其他通道或帧型，不混合或产生无效更新。

        参数: 无。返回: None。异常: 原明确拒绝或失败完成/所有权断言失败。
        """
        for channel, extended, fd in ((1, False, False), (0, True, False), (0, False, True)):
            self.write_input(((0, 0x100, b'\x02', channel, extended, fd),))
            adapter = self.adapter()
            _, read = self.read(adapter)
            batches = tuple(read)
            self.assertTrue(all(batch.sample_count == 0 for batch in batches))
            self.assertFalse(read.failed)
            self.assertTrue(read.finished)
            self.assertEqual(read.observation.row_count, 1)
            read.close()
            adapter.close()

    def test_original_time_regression_rejects_without_reordering_or_extra_pull(self):
        """真实原流0/.25/.125秒回退明确失败，不排序补救或授予第四次PULL。

        参数: 无。返回: None。异常: 原时间错误或原序/许可/关闭断言失败。
        """
        self.write_input(((0, 0x100, b'\x00', 0, False, False), (.25, 0x100, b'\x02', 0, False, False),
            (.125, 0x100, b'\x03', 0, False, False)))
        adapter = self.adapter()
        _, read = self.read(adapter)
        self.assertEqual(int(next(read).series['a0'].sequence[0]), 0)
        process = read._process
        self.assertEqual(int(next(read).series['a0'].sequence[0]), 1)
        with self.assertRaises(SourceReadError):
            next(read)
        self.assertTrue(read.closed and process.closed and read.failed)
        self.assertFalse(read.finished)
        self.assertEqual(process.counters, {'pulls_issued': 3, 'items_returned': 3, 'items_accepted': 3})


# 导入不启动进程；root统一实际unit运行时才生成真实合成BLF/DBC和暂存。
if __name__ == '__main__':
    unittest.main()
