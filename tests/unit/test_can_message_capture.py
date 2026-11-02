"""用真实合成DBC/BLF核对同次消息捕获、完成门槛和逐层移交责任。

产物仅写work/m2-legacy-tests/can-message-capture的独占home目录。正常路径经
生产spawn进程原next/parse，原字节0/2/3/4按DBC的2*x-1得到-1/3/5/7 V；
捕获与拆别名、空投影无关，逐条原decoded对象只追加一次。测试允许物化有限
夹具作手算对照，不把这些列表当生产实现，也不声称用户实际日志或RSS已验证。

故障只包裹真实预约、消息仓writer FD、原append和父安装操作，不创建假进程、
半初始化仓或替代history。原错误和最高owner、持续三次恢复、并行read与借款
均由实际对象断言。旧worker/process/vendor及既有测试保持原样。
"""

# 可选CAN依赖只用于现场有限输入，静态开关校验仍能单独运行。
import importlib.util
from pathlib import Path
from types import MappingProxyType
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import QualityFlag as Q, SignalDType as D, TimeType
from chronaxis.execution import can_reader as module
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.observed_ingestion import ObservedSourceScan
from chronaxis.legacy.message_store import DecodedMessageStore
from chronaxis.legacy.process_read import LegacyCANProcessRead
from chronaxis.legacy.records import LegacyCANField
from chronaxis.planning.models import SourcePlan
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError
from chronaxis.sources.can_spec import LegacyCANSpec
from chronaxis.sources.models import ReadRequest


WORK = Path(__file__).resolve().parents[2] / 'work/m2-legacy-tests/can-message-capture'
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


class MessageReceiver:
    """测试调用方的实际父owner，只关闭已经移入自身槽的真实消息仓。"""

    def __init__(self, budget):
        """安装空父槽及可控安装故障。参数: budget共享账本。返回: owner。异常: 无。"""
        self._budget, self._message_store = budget, None
        self.install_error, self.after = None, False

    def __setattr__(self, name, value):
        """在父真实安装前后可抛同一取消，不替换所传仓。

        参数: name/value为原属性赋值。返回: None。异常: 原install_error。
        """
        error = getattr(self, 'install_error', None)
        target = name == '_message_store' and value is not None and error is not None
        if target and not self.after:
            raise error
        object.__setattr__(self, name, value)
        if target:
            raise error

    def close(self):
        """只关闭实际新父资源。参数: 无。返回: None。异常: 原仓关闭错误可重试。"""
        if self._message_store is not None:
            self._message_store.close()
            if self._message_store.closed:
                self._message_store = None


class ActualMessageWriter:
    """透传真实writer，仅在close前持续或真实close后一次抛指定取消。"""

    def __init__(self, actual, error, *, after=False):
        """保存实际FD。参数: actual/error/after控制故障。返回: 代理。异常: 无。"""
        self.actual, self.error, self.after = actual, error, after

    def __getattr__(self, name):
        """透传真实属性。参数: name。返回: 原属性。异常: 原属性错误。"""
        return getattr(self.actual, name)

    def close(self):
        """在真实关闭前后抛错。参数: 无。返回: 原close值。异常: 同一error或原关闭错。"""
        if self.error is not None and not self.after:
            raise self.error
        value = self.actual.close()
        if self.error is not None:
            error, self.error = self.error, None
            raise error
        return value


class CaptureFixture(unittest.TestCase):
    """每例独占真实预算及输入，按实际owner收尾后才抵销调用方借款。"""

    def setUp(self):
        """建立home证据根及责任列表。参数: 无。返回: None。异常: 原目录或预算错。"""
        self.root = WORK / uuid4().hex
        self.root.mkdir(parents=True)
        self.budget, self.borrowed = ResourceBudget(256 * 1024 ** 2), 8192
        self.budget.reserve_ram(self.borrowed)
        self.adapters, self.reads, self.scans, self.histories, self.receivers = [], [], [], [], []
        self.path, self.dbc = self.root / 'input.blf', self.root / 'input.dbc'
        self.field = LegacyCANField(0, 'Sample', 256, False, False)

    def tearDown(self):
        """只通过真实owner关闭本例资源，最后核借款与零余额。

        参数: 无。返回: None。异常: 原关闭或断言失败，不能吞掉泄漏后称通过。
        """
        for scan in reversed(self.scans):
            scan.close()
        for read in reversed(self.reads):
            read.close()
        for receiver in self.receivers:
            receiver.close()
        for adapter in reversed(self.adapters):
            adapter.close()
        for history in reversed(self.histories):
            history.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        self.budget.release_ram(self.borrowed)
        self.assertEqual(self.budget.ram_bytes, 0)

    def adapter(self, *, capture=False, backend='reference', aliases=1, omit=False):
        """建立真正来源定义，原V与mV多别名共享原字段但不改旧解码。

        参数: capture为显式开关；backend/aliases控制实际装箱；omit省略开关测试默认。
        返回: BudgetedLegacyCANSourceAdapter。异常: 原声明/目录/预算错误。
        """
        definitions = tuple(SignalDefinition('a' + str(index), 'bus', self.field.key,
            D.FLOAT64, 'V' if index == 0 else 'mV', 1000000000, input_unit='V',
            scale=1 if index == 0 else 1000, same_time_policy='last_by_sequence')
            for index in range(aliases))
        # 保留原逐条读取和完整decoded消息捕获合同，不把本夹具切换到默认按需批协议。
        spec = LegacyCANSpec('bus', self.path, self.dbc, 0,
            TimebaseSpec('clock', TimeType.RELATIVE, 'capture-home-clock'), offset_ns=-BASE_NS,
            decode_scope='all')
        kwargs = dict(backend=backend, work_dir=self.root / ('adapter-' + str(len(self.adapters))))
        if not omit:
            kwargs['capture_message_updates'] = capture
        adapter = module.BudgetedLegacyCANSourceAdapter(self.budget, spec, 'session', definitions, **kwargs)
        self.adapters.append(adapter)
        return adapter

    def read(self, adapter, *, size=1, projection=None):
        """创建本次独立原请求与read，不提前扫描。

        参数: adapter/size/projection；None投影表示全部已声明别名。
        返回: (原ReadRequest,实际read)。异常: 原协议或预算错误。
        """
        names = tuple(item.name for item in adapter.signals) if projection is None else projection
        request = ReadRequest('session', names, 0, 1000000000, size)
        read = adapter.iter_batches_with_observation(request)
        self.reads.append(read)
        return request, read

    def receiver(self):
        """登记实际新父。参数: 无。返回: MessageReceiver。异常: 无。"""
        receiver = MessageReceiver(self.budget)
        self.receivers.append(receiver)
        return receiver

    def history_scan(self, adapter, *, projection=()):
        """以原adapter/spec/request建立真实building历史及scan。

        参数: adapter及读取投影；不构造观测证明或替代绑定。
        返回: (history,scan,原request)。异常: 原历史/扫描构造错误。
        """
        request = ReadRequest('session', projection, 0, 1000000000, 1)
        history = DecodedHistoryStore(self.budget, self.root / ('history-' + str(len(self.histories))),
            (adapter.describe(),), {'bus': request})
        self.histories.append(history)
        source = SourcePlan('bus', 'can_blf', adapter.spec, 's', None,
            'capture-source-home', MappingProxyType({}))
        scan = ObservedSourceScan(history, source, adapter, request)
        self.scans.append(scan)
        return history, scan, request

    def write_input(self, rows=None):
        """现场生成可手算的原DBC/BLF，writer实际stop后才读取。

        参数: rows为(秒偏移,frame_id,bytes)，None为四帧0/2/3/4且中间同刻。
        返回: None。异常: 原可选依赖、写入或stop错误，不修改Ref。
        """
        import can
        actual = rows if rows is not None else ((0, 256, b'\x00'), (.125, 256, b'\x02'),
            (.125, 256, b'\x03'), (.25, 256, b'\x04'))
        self.dbc.write_text(DBC, encoding='utf-8')
        writer = can.BLFWriter(str(self.path))
        try:
            for second, frame_id, data in actual:
                writer.on_message_received(can.Message(timestamp=BASE + second,
                    arbitration_id=frame_id, is_extended_id=False, channel=0, data=data))
        finally:
            writer.stop()


class CaptureStaticTests(CaptureFixture):
    """不访问CAN输入也能核默认关闭、严格bool及只读配置快照。"""

    def test_default_false_has_original_fees_and_static_capture_has_no_io(self):
        """默认与显式False金额相同，True构造/read仍不spawn或创建消息仓。

        参数: 无。返回: None。异常: 原构造错误或静态副作用/费用/readonly断言失败。
        """
        # 禁止实际子工厂被触发；普通false两种写法与true的静态状态分别核对。
        with patch.object(module, 'LegacyCANProcessRead', side_effect=AssertionError('unexpected process')):
            with patch.object(module, 'DecodedMessageStore', side_effect=AssertionError('unexpected store')):
                implicit, explicit = self.adapter(omit=True), self.adapter(capture=False)
                _, first = self.read(implicit)
                _, second = self.read(explicit)
                enabled = self.adapter(capture=True)
                _, third = self.read(enabled)
                history, scan, _ = self.history_scan(enabled)
        self.assertEqual(first._fixed_cost, second._fixed_cost)
        self.assertEqual(implicit._fixed_cost, explicit._fixed_cost)
        self.assertFalse(implicit.capture_message_updates or first.capture_message_updates)
        self.assertTrue(enabled.capture_message_updates and third.capture_message_updates and scan.capture_message_updates)
        self.assertIsNone(third._process)
        self.assertIsNone(third._message_store)
        self.assertFalse(third._work_path.exists())
        for owner in (enabled, third, scan):
            with self.assertRaises(AttributeError):
                owner.capture_message_updates = False
        # 未开始读取也只能由原父close，不从readonly flag猜已经完成或取得仓。
        with self.assertRaises(ResultClosedError):
            third.take_message_store(self.receiver())
        self.assertFalse(history.closed)

    def test_capture_switch_rejects_non_native_bool_before_new_directory(self):
        """0/1/None/文本不按truthiness打开捕获，拒绝前不创建adapter目录或付款。

        参数: 无。返回: None。异常: 错误类型、目录或真实借款保护断言失败。
        """
        # 只改变非法开关，其他来源模型真实有效，以避免被无关配置错误遮蔽。
        baseline = self.budget.ram_bytes
        for value in (0, 1, None, 'true'):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self.adapter(capture=value)
                self.assertFalse((self.root / 'adapter-0').exists())
                self.assertEqual(self.budget.ram_bytes, baseline)


@unittest.skipUnless(HAS_CAN, '需要固定可选CAN依赖，skip不能作为真实捕获验收')
class CaptureActualTests(CaptureFixture):
    """生产spawn读取真实BLF，在实际封存、FD和父槽边界验证数据与恢复。"""

    def test_same_record_once_for_two_backends_and_alias_batch_sizes(self):
        """两后端×1/2/7拆批仍四原帧与五PULL，captured参数就是原B1返回对象。

        参数: 无。返回: None。异常: 原生产错或手算/身份/次数/封口断言失败。
        """
        # 有限测试保留原record供is对照；观察包装始终只委托一次真实next/append。
        self.write_input()
        actual_next, actual_append = LegacyCANProcessRead.__next__, DecodedMessageStore.append
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                with self.subTest(backend=backend, size=size):
                    returned, appended = [], []

                    def original_next(process):
                        """观察原调用返回。参数: 真实process。返回: 原record。异常: 原EOF/读取错。"""
                        record = actual_next(process)
                        returned.append(record)
                        return record

                    def original_append(store, record, time_ns, *, time_quantized):
                        """只观察同次实际追加。参数: 原store/record/time/量化。返回: 原结果。异常: 原错。"""
                        self.assertIs(record, returned[-1])
                        appended.append((store, record, time_ns, time_quantized))
                        return actual_append(store, record, time_ns, time_quantized=time_quantized)

                    adapter = self.adapter(capture=True, backend=backend, aliases=2)
                    request, read = self.read(adapter, size=size)
                    with patch.object(LegacyCANProcessRead, '__next__', original_next):
                        with patch.object(DecodedMessageStore, 'append', original_append):
                            first = next(read)
                            process, store = read._process, read._message_store
                            batches = (first, *tuple(read))
                    # 真值来自一字节DBC手算，进程计数和封口仓另证未随别名/批次重复读取。
                    self.assertEqual(len(returned), 4)
                    self.assertEqual(len(appended), 4)
                    self.assertTrue(all(item[0] is store for item in appended))
                    self.assertEqual(process.counters, {'pulls_issued': 5, 'items_returned': 4, 'items_accepted': 4})
                    self.assertTrue(process.closed and process.finished and read.finished)
                    self.assertIs(read.observation.request, request)
                    self.assertEqual(store.decoder_profile, read.runtime_metadata['profile'])
                    self.assertEqual(store.read_identity, read.identity)
                    self.assertEqual((store.source_name, store.session_id, store.count), ('bus', 'session', 4))
                    self.assertTrue(all(batch.sample_count <= size for batch in batches))
                    self.assertEqual([float(batch.series['a0'].values[0]) for batch in batches if 'a0' in batch.series], [-1, 3, 5, 7])
                    receiver = self.receiver()
                    self.assertIs(read.take_message_store(receiver), store)
                    reader = store.iter_records()
                    rows = tuple(reader)
                    self.assertTrue(reader.verified_eof and reader.closed)
                    self.assertEqual([row.time_ns for row in rows], [0, 125000000, 125000000, 250000000])
                    self.assertEqual([row.decoded for row in rows], returned)
                    self.assertEqual([row.time_quantized for row in rows], [item[3] for item in appended])
                    # 移交后输入父关闭不能销毁输出仓，只有真实接收父负责最终费用。
                    read.close()
                    adapter.close()
                    self.assertFalse(store.closed)
                    receiver.close()

    def test_empty_projection_captures_unknown_and_missing_and_waits_for_stop(self):
        """空投影仍全捕获未知ID/空dict，EOF批交付尚不能移交，真Stop后才可取仓。

        参数: 无。返回: None。异常: 原生产错或全源/缺key/完成门槛断言失败。
        """
        # 原未知帧与原空dict都是实际yield；零投影不得使它们从消息仓消失。
        self.write_input(((0, 256, b'\x00'), (.125, 257, b'\x01'),
            (.25, 256, b''), (.375, 256, b'\x04')))
        adapter = self.adapter(capture=True)
        _, read = self.read(adapter, projection=())
        receiver, batches = self.receiver(), []
        while True:
            batch = next(read)
            batches.append(batch)
            if batch.source_eof:
                break
        process, store = read._process, read._message_store
        self.assertEqual(len(batches), 5)
        self.assertTrue(all(batch.sample_count == 0 for batch in batches))
        self.assertEqual(store.state, 'sealed')
        self.assertFalse(read.finished)
        # EOF批仅交付进度，仍必须再next让输入完成收尾后才能移交。
        with self.assertRaises(ResultClosedError):
            read.take_message_store(receiver)
        with self.assertRaises(StopIteration):
            next(read)
        self.assertTrue(process.closed and process.finished and read.finished)
        self.assertIs(read.take_message_store(receiver), store)
        rows = tuple(store.iter_records())
        self.assertEqual([row.decoded.frame.arbitration_id for row in rows], [256, 257, 256, 256])
        self.assertEqual(dict(rows[1].decoded.values), {})
        self.assertEqual(dict(rows[2].decoded.values), {})
        self.assertEqual(rows[-1].decoded.values['Sample'], 7)
        self.assertEqual(read.observation.row_count, 4)

    def test_default_real_read_never_creates_message_directory_or_store(self):
        """默认正常原信号仍-1/3/5/7，消息构造零次且没有可取的隐藏仓。

        参数: 无。返回: None。异常: 原生产错或默认路径被扩大断言失败。
        """
        # 真正常规读取仍执行；只有新消息工厂被设为一旦调用即失败，核默认off。
        self.write_input()
        adapter = self.adapter(omit=True)
        _, read = self.read(adapter)
        with patch.object(module, 'DecodedMessageStore', side_effect=AssertionError('default capture')):
            batches = tuple(read)
        self.assertEqual([float(batch.series['a0'].values[0]) for batch in batches if batch.sample_count], [-1, 3, 5, 7])
        self.assertIsNone(read._message_store)
        self.assertFalse((read._work_path / 'messages').exists())
        with self.assertRaises(ResultClosedError):
            read.take_message_store(self.receiver())

    def test_capture_keeps_missing_key_without_changing_signal_invalid_update(self):
        """捕获保原空dict，目标缺key仍MISSING而非旧值，其他ID没有信号更新。

        参数: 无。返回: None。异常: 原生产错或原字段/缺值/原序断言失败。
        """
        # 同时核信号层更新及仓内原dict，不能以捕获存在就推断MISSING处理未变。
        self.write_input(((0, 256, b'\x00'), (.125, 257, b'\x01'),
            (.25, 256, b''), (.375, 256, b'\x04')))
        adapter = self.adapter(capture=True)
        _, read = self.read(adapter)
        batches = tuple(read)
        columns = [batch.series['a0'] for batch in batches if 'a0' in batch.series]
        self.assertEqual([int(column.sequence[0]) for column in columns], [0, 2, 3])
        self.assertEqual([bool(column.valid[0]) for column in columns], [True, False, True])
        self.assertEqual(columns[1].original_values, (None,))
        self.assertEqual(int(columns[1].quality[0]), int(Q.MISSING))
        store = read.take_message_store(self.receiver())
        rows = tuple(store.iter_records())
        self.assertEqual(dict(rows[2].decoded.values), {})
        self.assertNotIn('Sample', rows[2].decoded.values)
        self.assertEqual(rows[-1].decoded.values['Sample'], 7)

    def test_empty_and_single_message_stores_have_distinct_complete_endpoints(self):
        """开启捕获时空仓和单点均真EOF封口，0条None与1条0ns不能混同。

        参数: 无。返回: None。异常: 原生产错或封口/全流EOF/端点断言失败。
        """
        # 两种输入都经过同一真实完整协议，空仓不是提前close制造的零行结果。
        for rows in ((), ((0, 256, b'\x02'),)):
            with self.subTest(rows=rows):
                self.write_input(rows)
                adapter = self.adapter(capture=True)
                _, read = self.read(adapter, projection=())
                tuple(read)
                store = read.take_message_store(self.receiver())
                self.assertEqual(store.state, 'sealed')
                reader = store.iter_records()
                captured = tuple(reader)
                self.assertTrue(reader.verified_eof and reader.closed)
                self.assertEqual(len(captured), len(rows))
                self.assertEqual((read.observation.first_ns, read.observation.last_ns),
                    (0, 0) if rows else (None, None))
                read.close()
                adapter.close()

    def test_scan_transfers_actual_store_before_closing_read_and_borrowed_input(self):
        """实际空投影scan写同一history，原消息仓经scan移交后独立存活。

        参数: 无。返回: None。异常: 原生产错或原对象/READY/EOF/费用归属断言失败。
        """
        # 原工厂返回对象只被观察，不用手造仓、相等readid或外部read替代扫描。
        self.write_input()
        adapter = self.adapter(capture=True)
        history, scan, request = self.history_scan(adapter)
        captured = []

        def create_actual(*args, **kwargs):
            """观察真实构造返回。参数: 原仓构造参数。返回: 实际仓。异常: 原构造错。"""
            store = DecodedMessageStore(*args, **kwargs)
            captured.append(store)
            return store

        with patch.object(module, 'DecodedMessageStore', side_effect=create_actual):
            scan.consume()
        self.assertEqual(len(captured), 1)
        store = captured[0]
        self.assertTrue(scan.finished and scan.capture_message_updates)
        self.assertIs(scan._message_store, store)
        self.assertIsNone(scan._read)
        self.assertIs(scan.request, request)
        self.assertEqual(scan.counts, (5, 0))
        self.assertEqual(scan.observation.row_count, store.count)
        self.assertEqual(store.read_identity, scan.read_identity)
        self.assertEqual(store.decoder_profile, scan.runtime_metadata['profile'])
        # 再次移交后逐个关闭原父与借用输入，账本只能剩新父的真实仓费。
        receiver = self.receiver()
        self.assertIs(scan.take_message_store(receiver), store)
        self.assertIsNone(scan._message_store)
        scan.close()
        self.assertTrue(scan.closed)
        self.assertFalse(adapter.closed or history.closed or store.closed)
        adapter.close()
        history.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed + store._held_cost)
        self.assertEqual(len(tuple(store.iter_records())), 4)

    def test_read_receiver_cancel_before_after_keeps_one_actual_parent(self):
        """父安装前仍归read，安装后即归新父；同一KI不丢仓且重复移交拒绝。

        参数: 无。返回: None。异常: 原生产错或同一异常/责任/借款断言失败。
        """
        # setter前后分别证明责任归属，不以异常是否发生猜测父是否实际安装。
        self.write_input()
        for after in (False, True):
            with self.subTest(after=after):
                adapter = self.adapter(capture=True)
                _, read = self.read(adapter)
                tuple(read)
                receiver, store = self.receiver(), read._message_store
                marker = KeyboardInterrupt('message receiver')
                receiver.install_error, receiver.after = marker, after
                try:
                    with self.assertRaises(KeyboardInterrupt) as raised:
                        read.take_message_store(receiver)
                    self.assertIs(raised.exception, marker)
                    self.assertIs(marker.can_observation_read_cleanup_owner, read)
                    self.assertIs(receiver._message_store if after else read._message_store, store)
                    self.assertIsNone(read._message_store if after else receiver._message_store)
                finally:
                    receiver.install_error = None
                if not after:
                    self.assertIs(read.take_message_store(receiver), store)
                with self.assertRaises(ResultClosedError):
                    read.take_message_store(receiver)
                read.close()
                adapter.close()
                self.assertFalse(store.closed)
                receiver.close()

    def test_scan_receiver_cancel_before_after_retains_actual_scan_or_parent(self):
        """scan完成后父安装前后取消均有真实槽，关闭scan不越权关闭已移交仓。

        参数: 无。返回: None。异常: 原生产错或最高scan/父槽/关闭断言失败。
        """
        # 使用真实finished scan覆盖第二级移交，不能只测read一级后推结论。
        self.write_input()
        for after in (False, True):
            with self.subTest(after=after):
                adapter = self.adapter(capture=True)
                _, scan, _ = self.history_scan(adapter)
                scan.consume()
                receiver, store = self.receiver(), scan._message_store
                marker = KeyboardInterrupt('scan receiver')
                receiver.install_error, receiver.after = marker, after
                try:
                    with self.assertRaises(KeyboardInterrupt) as raised:
                        scan.take_message_store(receiver)
                    self.assertIs(raised.exception, marker)
                    self.assertIs(marker.observed_source_scan_cleanup_owner, scan)
                    self.assertIs(receiver._message_store if after else scan._message_store, store)
                finally:
                    receiver.install_error = None
                if not after:
                    self.assertIs(scan.take_message_store(receiver), store)
                with self.assertRaises(ValueError):
                    scan.take_message_store(receiver)
                scan.close()
                self.assertFalse(store.closed)

    def test_message_constructor_reserve_cancel_has_actual_unreturned_store_owner(self):
        """首PULL前消息仓固定费前后取消，实际未返回子由最高read持有恢复。

        参数: 无。返回: None。异常: 原生产错或实际账目/owner/零PULL断言失败。
        """
        # 在原raw已经返回后才选择消息首笔预约，以真实金额识别持续清理目标。
        self.write_input()
        for after in (False, True):
            with self.subTest(after=after):
                adapter = self.adapter(capture=True)
                _, read = self.read(adapter)
                actual_reserve, actual_release = self.budget.reserve_ram, self.budget.release_ram
                marker, cleanup = KeyboardInterrupt('message reserve'), KeyboardInterrupt('message release')
                selected, releases = [], []
                process_seen = []

                def reserve(amount):
                    """只命中原raw已安装后的第一笔仓费。参数: amount。返回: 原值。异常: 原marker。"""
                    if read._raw_store is not None and read._message_store is None and not selected:
                        selected.append(amount)
                        process_seen.append(read._process)
                        if after:
                            actual_reserve(amount)
                        raise marker
                    return actual_reserve(amount)

                def release(amount):
                    """后取消场景持续拒绝同笔实际消息费。参数: amount。返回: 原值。异常: cleanup。"""
                    if after and selected and amount == selected[0]:
                        releases.append(amount)
                        raise cleanup
                    return actual_release(amount)

                with patch.object(self.budget, 'reserve_ram', side_effect=reserve):
                    with patch.object(self.budget, 'release_ram', side_effect=release):
                        with self.assertRaises(KeyboardInterrupt) as raised:
                            next(read)
                self.assertIs(raised.exception, marker)
                self.assertIs(marker.can_observation_read_cleanup_owner, read)
                child = marker.decoded_message_store_cleanup_owner
                self.assertEqual(process_seen[0].counters['pulls_issued'], 0)
                self.assertTrue(process_seen[0].closed)
                if after:
                    self.assertGreaterEqual(len(releases), 3)
                    self.assertIs(read._message_store, child)
                    self.assertFalse(child.closed or read.closed)
                    self.assertEqual(child._held_cost, selected[0])
                read.close()
                self.assertTrue(child.closed and read.closed)
                adapter.close()

    def test_capture_append_cancel_preserves_primary_and_clears_own_record_locals(self):
        """真实追加后取消不再PULL或生成finished，原TB只核本层record/conversion已断。

        参数: 无。返回: None。异常: 原生产错或原错误/次数/TB/恢复断言失败。
        """
        # 保留真实原TB而不用assertRaises清理它，检验本层finally实际断开大局部。
        self.write_input()
        adapter = self.adapter(capture=True)
        _, read = self.read(adapter)
        marker, actual = KeyboardInterrupt('message append after'), DecodedMessageStore.append
        processes, stores = [], []

        def append(store, record, time_ns, *, time_quantized):
            """先执行真实追加再抛同一取消。参数: 原追加参数。返回: 不返回。异常: marker。"""
            actual(store, record, time_ns, time_quantized=time_quantized)
            stores.append(store)
            processes.append(read._process)
            raise marker

        caught = None
        with patch.object(DecodedMessageStore, 'append', append):
            try:
                next(read)
            except KeyboardInterrupt as exc:
                caught = exc
        self.assertIs(caught, marker)
        self.assertIs(caught.can_observation_read_cleanup_owner, read)
        self.assertEqual(processes[0].counters, {'pulls_issued': 1, 'items_returned': 1, 'items_accepted': 1})
        self.assertTrue(processes[0].closed and stores[0].closed and read.closed)
        self.assertTrue(read.failed)
        self.assertFalse(read.finished)
        found, current = False, caught.__traceback__
        while current is not None:
            if current.tb_frame.f_code.co_name == '_new_record':
                found = True
                self.assertIsNone(current.tb_frame.f_locals['record'])
                self.assertIsNone(current.tb_frame.f_locals['conversion'])
            current = current.tb_next
        self.assertTrue(found)

    def test_message_writer_close_cancel_is_retryable_and_parallel_read_isolated(self):
        """真实消息writer关闭前持续至少三次/关闭后取消，不伪完成且另一read可继续。

        参数: 无。返回: None。异常: 原生产错或真实FD/owner/原取消/借用隔离断言失败。
        """
        # 两read先各持有真实独立FD；只给first的消息writer装关闭故障代理。
        self.write_input()
        for after in (False, True):
            with self.subTest(after=after):
                adapter = self.adapter(capture=True)
                _, first = self.read(adapter)
                _, second = self.read(adapter)
                next(first)
                next(second)
                store, other = first._message_store, second._message_store
                marker = KeyboardInterrupt('message writer close')
                wrapper = ActualMessageWriter(store._writer, marker, after=after)
                store._writer = wrapper
                try:
                    with self.assertRaises(KeyboardInterrupt) as raised:
                        tuple(first)
                    self.assertIs(raised.exception, marker)
                    self.assertIs(marker.can_observation_read_cleanup_owner, first)
                    self.assertIs(marker.decoded_message_store_cleanup_owner, store)
                    self.assertTrue(first.failed)
                    self.assertFalse(first.finished)
                    if not after:
                        for _ in range(3):
                            with self.assertRaises(KeyboardInterrupt) as repeated:
                                first.close()
                            self.assertIs(repeated.exception, marker)
                            self.assertFalse(wrapper.actual.closed or store.closed or first.closed)
                    self.assertFalse(second.closed or other._writer.closed)
                finally:
                    wrapper.error = None
                first.close()
                self.assertTrue(wrapper.actual.closed and store.closed and first.closed)
                self.assertFalse(other._writer.closed)
                tuple(second)
                self.assertTrue(second.finished)
