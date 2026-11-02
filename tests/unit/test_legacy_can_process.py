"""验证原公开CAN函数链的逐次进程许可、真实EOF和可恢复资源责任。

真实库类现场生成四帧BLF及单信号DBC，手算值为-1/3/5/7 V；两个同刻不同
payload必须保留原序号。STATUS是无读取许可的控制屏障，不能用sleep猜测没有预取。
纯wire类用真正spawn的独立测试worker核非法包和异常退出，不把这些受控回复冒称
真实DBC输出。资源故障代理只包实际Connection/Process，在真实操作前后抛同一对象；
持续失败后同一最高owner恢复，另一个read和调用方预算借款保持，不手造半初始化资源。
全部运行产物保留在新项目work/m2-can-tests，device_label为home。文件导入不打开
BLF/DBC或启动子进程；只有真实库类在可选CAN依赖确实缺失时跳过，其余协议测试照常。
"""

from configuration_fixtures import current_fixture

# 测试worker必须定义在模块顶层，供Windows spawn按名称导入；不执行历史入口。
from functools import partial
import importlib.util
import json
import os
from pathlib import Path
import platform
from threading import Event
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.legacy import process_read as module
from chronaxis.legacy.records import (LegacyCANField, LegacyCANRequest, LegacyDecodedFrame,
    LegacyRawFrame, MAX_WIRE_BYTES, PROFILE_ID, decoded_to_dict, decode_packet, encode_packet)
from chronaxis.results import ResourceBudget, ResultClosedError
from chronaxis.sources.protocol import SourceReadError


WORK = Path(__file__).resolve().parents[2] / 'work' / 'm2-can-tests'
HAS_CAN = all(importlib.util.find_spec(name) is not None for name in ('can', 'cantools', 'natsort'))
VENDOR_SHA256 = {
    'utils.py': 'cf3737ad5ab0a399dc7576585102339e0312b9babe690a1ba8decf543a71c2fd',
    'file_processor.py': '5f37bd996ccd31eedd95bec5ed39289cd7f2fe3049110ebbe195db0cbefb1db6',
    'can_processor.py': '3c96e67a1ec47ac181657b5bf5a9cabf7e35a1d5e2709577718c22d1293878e2',
}
SYNTHETIC_DBC = '''VERSION ""
NS_ :
BS_:
BU_: Vector__XXX
BO_ 256 Demo: 1 Vector__XXX
 SG_ Sample : 0|8@1+ (2,-1) [-1|509] "V" Vector__XXX
'''
BASE_TIMESTAMP = 1700000000.0
FIXTURE_ROWS = ((BASE_TIMESTAMP, 0), (BASE_TIMESTAMP + .125, 2),
    (BASE_TIMESTAMP + .125, 3), (BASE_TIMESTAMP + .25, 4))


def controlled_worker(connection, *, mode):
    """用真实子进程发送明确受控的协议回复，不调用CAN或假冒真实值基线。

    参数: connection为spawn传入的真实端点；mode为父测试显式指定的私有场景。
    返回: None；正常空流发送EOF后退出，其他场景按说明失败或等待真实终止。
    异常: 非预期管道错误传播；故意坏包不使用生产编码器绕过其校验。
    """
    try:
        initial = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
        if initial.get('op') != 'init':
            raise AssertionError('受控worker未先收到INIT')
        ready = {'op': 'ready', 'version': 1, 'profile': PROFILE_ID,
            'worker_pid': os.getpid(), 'fields': [{'locator': locator, 'unit': 'V'}
                for locator in initial['fields']],
            'dependency_versions': {'python': platform.python_version(), 'python-can': '4.6.1',
                'cantools': '39.4.3', 'natsort': '8.4.0'}, 'vendor_sha256': dict(VENDOR_SHA256)}
        if mode == 'ready_missing':
            del ready['dependency_versions']
        elif mode == 'ready_hash':
            ready['vendor_sha256']['can_processor.py'] = '0' * 64
        elif mode == 'ready_version':
            ready['dependency_versions']['python-can'] = '0.0.0'
        elif mode == 'ready_unit':
            ready['fields'][0]['unit'] = 1
        elif mode == 'ready_channel_bool':
            ready['fields'][0]['locator']['channel'] = False
        elif mode == 'ready_extended_int':
            ready['fields'][0]['locator']['is_extended'] = 0
        connection.send_bytes(encode_packet(ready))
        while True:
            try:
                packet = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
            except EOFError:
                if mode == 'stubborn':
                    # 真正存活的worker只由父owner终止；不靠sleep制造存活时间窗口。
                    Event().wait()
                return
            if packet['op'] == 'status':
                connection.send_bytes(encode_packet({'op': 'status', 'pulls_received': 0,
                    'frames_returned': 0, 'parse_calls': 0}))
                continue
            if packet['op'] == 'ack':
                connection.send_bytes(encode_packet({'op': 'ack'}))
                continue
            if packet['op'] != 'pull':
                raise AssertionError('受控worker收到未声明控制消息')
            request_id = packet['request_id']
            if mode == 'bad_json':
                connection.send_bytes(b'{broken-json')
            elif mode == 'overlong':
                connection.send_bytes(b'x' * (MAX_WIRE_BYTES + 1))
            elif mode in ('wrong_id', 'bool_id'):
                frame = LegacyRawFrame(BASE_TIMESTAMP, 0x100, False, False, False,
                    0, 1, b'\x00', False, True, False, False)
                connection.send_bytes(encode_packet({'op': 'item',
                    'request_id': False if mode == 'bool_id' else request_id + 1,
                    'record': decoded_to_dict(LegacyDecodedFrame(0, frame, {'Sample': -1}))}))
            elif mode == 'remote_error':
                connection.send_bytes(encode_packet({'op': 'error', 'request_id': request_id,
                    'phase': 'pull', 'error': {'module': 'builtins', 'type': 'ValueError',
                        'message': 'controlled original worker failure', 'traceback': 'controlled traceback',
                        'notes': ['controlled worker note']}}))
            elif mode == 'no_eof':
                return
            elif mode == 'bad_exit':
                connection.send_bytes(encode_packet({'op': 'eof', 'request_id': request_id, 'frame_count': 0}))
                raise SystemExit(7)
            elif mode == 'bool_eof':
                connection.send_bytes(encode_packet({'op': 'eof', 'request_id': request_id, 'frame_count': False}))
            elif mode == 'eof_alive':
                connection.send_bytes(encode_packet({'op': 'eof', 'request_id': request_id, 'frame_count': 0}))
                Event().wait()
            else:
                connection.send_bytes(encode_packet({'op': 'eof', 'request_id': request_id, 'frame_count': 0}))
            return
    finally:
        connection.close()


def observed_real_worker(connection):
    """只在隔离测试child透传计数真实vendor公开函数，不改任何源码字节。

    参数: connection为真实spawn端点。返回: 原worker返回值。
    异常: 原worker错误传播；trace写失败也直接失败，不能假报没有后继调用。
    流程: 暂存第一份INIT字节并原样回放；原loader返回后包装其公开函数，
    记录load_file/next/parse真实入口，再完整调用生产worker_main。
    """
    from chronaxis.legacy import worker
    initial = connection.recv_bytes(MAX_WIRE_BYTES)
    request = decode_packet(initial)
    trace_path = Path(request['path']).with_name('process-trace.jsonl')
    original_loader = worker._load_vendor

    def trace(event, **facts):
        """立即保存一条真实入口事实。参数: event/facts。返回: None。异常: 原IO错误。"""
        with trace_path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(current_fixture({'rule': event, **facts}), allow_nan=False) + '\n')

    def load():
        """取得原模块后只透传其公开函数。参数: 无。返回: 原loader三元组。异常: 原错误。"""
        files, processor, hashes = original_loader()
        original_frames, original_parse = files.iter_frames, processor.parse_frame
        original_database = processor.cantools.database.load_file

        def frames(path):
            """逐次请求原generator，不提前取下一项。参数: 原path。返回: 原msg流。异常: 原错误。"""
            iterator = original_frames(path)
            try:
                while True:
                    trace('next')
                    try:
                        message = next(iterator)
                    except StopIteration:
                        return
                    yield message
            finally:
                iterator.close()

        def parse(message, database):
            """每个真实parse只转发一次。参数: 原msg/db。返回: 原dict。异常: 原函数政策。"""
            trace('parse', timestamp=message.timestamp, arbitration_id=message.arbitration_id,
                data_hex=bytes(message.data).hex())
            return original_parse(message, database)

        def database(*args, **kwargs):
            """记录并执行唯一原load_file。参数: 原args/kwargs。返回: 原db。异常: 原加载错误。"""
            trace('load_file', args=list(args), kwargs=kwargs)
            return original_database(*args, **kwargs)

        files.iter_frames, processor.parse_frame = frames, parse
        processor.cantools.database.load_file = database
        return files, processor, hashes

    class InitialReplay:
        """仅原样回放已取得INIT，其后所有管道能力都转交同一真实端点。"""

        def __init__(self):
            """登记唯一未回放字节。参数: 无。返回: 新代理。异常: 无。"""
            self.first = initial

        def recv_bytes(self, *args, **kwargs):
            """先回放再真实接收。参数: 原参数。返回: 原bytes。异常: 原管道错误。"""
            if self.first is not None:
                value, self.first = self.first, None
                return value
            return connection.recv_bytes(*args, **kwargs)

        def __getattr__(self, name):
            """透传真实管道状态/动作。参数: name。返回: 原属性。异常: 原错误。"""
            return getattr(connection, name)

    with patch.object(worker, '_load_vendor', new=load):
        return worker.worker_main(InitialReplay())


class ConnectionFault:
    """只代理一个真实Pipe端点，closed始终来自实际句柄而非注入状态。"""

    def __init__(self, connection, *, operation='close', error=None, after=False):
        """保存实际端点和故障。参数: connection/operation/error/after。返回: 代理。异常: 无。"""
        self.real, self.operation, self.error, self.after = connection, operation, error, after
        self.calls = 0

    @property
    def closed(self):
        """读取真实端点状态。参数: 无。返回: bool。异常: 原属性错误。"""
        return self.real.closed

    def __getattr__(self, name):
        """透传未注入能力。参数: name。返回: 原属性。异常: 原AttributeError。"""
        return getattr(self.real, name)

    def close(self):
        """在本端真实close前后注入。参数: 无。返回: 原返回值。异常: 原对象或实际关闭错误。"""
        return self._invoke('close')

    def recv_bytes(self, *args, **kwargs):
        """在本端真实接收前后注入。参数: 原接收参数。返回: bytes。异常: 原对象或实际管道错误。"""
        return self._invoke('recv_bytes', *args, **kwargs)

    def _invoke(self, name, *args, **kwargs):
        """只计目标真实动作。参数: name及原参数。返回: 原返回值。异常: 目标原对象或原错误。"""
        if name == self.operation:
            self.calls += 1
            if self.error is not None and not self.after:
                raise self.error
        value = getattr(self.real, name)(*args, **kwargs)
        if name == self.operation and self.error is not None:
            raise self.error
        return value


class ProcessFault:
    """为真实已启动Process的单项join/terminate/close注入，不伪造pid或退出状态。"""

    def __init__(self, process, operation, error, after):
        """保存同一真实进程。参数: process/operation/error/after。返回: 代理。异常: 无。"""
        self.real, self.operation, self.error, self.after = process, operation, error, after
        self.calls = 0

    def __getattr__(self, name):
        """透传真实pid/is_alive/exitcode。参数: name。返回: 原属性。异常: 原错误。"""
        return getattr(self.real, name)

    def join(self, *args, **kwargs):
        """代理实际等待。参数: 原参数。返回: 原返回值。异常: 目标原对象或真实错误。"""
        return self._invoke('join', *args, **kwargs)

    def terminate(self):
        """代理实际终止。参数: 无。返回: 原返回值。异常: 目标原对象或真实错误。"""
        return self._invoke('terminate')

    def close(self):
        """代理实际进程句柄关闭。参数: 无。返回: 原返回值。异常: 目标原对象或真实错误。"""
        return self._invoke('close')

    def _invoke(self, name, *args, **kwargs):
        """保实际副作用一次语义。参数: name及原参数。返回: 原值。异常: 注入原对象或原错误。"""
        if name == self.operation:
            self.calls += 1
            if self.error is not None and not self.after:
                raise self.error
        value = getattr(self.real, name)(*args, **kwargs)
        if name == self.operation and self.error is not None:
            raise self.error
        return value


class ProcessFixture(unittest.TestCase):
    """每例独立work目录、真实借款与read登记，清理只经每个read自身close。"""

    def setUp(self):
        """建立独占输入路径与预算。参数: 无。返回: None。异常: 原目录或预算错误。"""
        self.root = WORK / ('legacy-can-process-home-' + uuid4().hex)
        self.root.mkdir(parents=True)
        self.budget, self.borrowed, self.reads = ResourceBudget(256 * 1024 ** 2), 1_048_576, []
        self.budget.reserve_ram(self.borrowed)
        self.input_path, self.dbc_path = self.root / 'synthetic.blf', self.root / 'synthetic.dbc'
        self.field = LegacyCANField(0, 'Sample', 0x100, False, False)

    def tearDown(self):
        """重试本例实际read并核借款未误还。参数: 无。返回: None。异常: 实际关闭或漏账断言。"""
        for read in reversed(self.reads):
            read.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed, '每个read只能释放自己的实际费用')
        self.budget.release_ram(self.borrowed)
        self.assertEqual(self.budget.ram_bytes, 0)

    def make_read(self, *, mode='empty', request=None):
        """构造真实read而不启动。参数: mode和可选原request。返回: 已登记read。异常: 原构造错误。"""
        actual = request or LegacyCANRequest(self.input_path, self.dbc_path, (self.field,))
        read = module.LegacyCANProcessRead(actual, self.budget,
            _worker_target=partial(controlled_worker, mode=mode))
        self.reads.append(read)
        return read

    def assert_no_completion(self, read):
        """拒把失败/提前关闭当EOF。参数: read。返回: None。异常: 断言失败。"""
        self.assertFalse(read.finished)

    def assert_status(self, read, expected):
        """用真实无credit屏障确认子端计数。参数: read和三元组。返回: None。异常: 原wire或断言。"""
        reply = read._exchange({'op': 'status'})
        self.assertEqual(reply, {'op': 'status', 'pulls_received': expected[0],
            'frames_returned': expected[1], 'parse_calls': expected[2]})

    def read_trace(self):
        """逐行读取本例有限公开调用trace。参数: 无。返回: dict列表。异常: 原IO/JSON错误。"""
        with self.input_path.with_name('process-trace.jsonl').open(encoding='utf-8') as handle:
            return [json.loads(line) for line in handle]


@unittest.skipUnless(HAS_CAN, '可选CAN依赖can/cantools/natsort确实未全部安装')
class RealLegacyCANProcessTests(ProcessFixture):
    """使用真实BLF/DBC及生产worker，隔离trace只观察原公开调用。"""

    def setUp(self):
        """现场生成四帧真夹具。参数: 无。返回: None。异常: 原can writer或文件错误。"""
        super().setUp()
        import can
        self.dbc_path.write_text(SYNTHETIC_DBC, encoding='utf-8')
        writer = can.BLFWriter(str(self.input_path))
        try:
            for timestamp, payload in FIXTURE_ROWS:
                writer.on_message_received(can.Message(timestamp=timestamp, arbitration_id=0x100,
                    is_extended_id=False, channel=0, data=[payload]))
        finally:
            writer.stop()

    def real_read(self, *, observed=False, input_path=None):
        """建立真旧链read，不读取。

        参数: observed是否隔离透传trace，input_path为本例可选夹具。返回: 已登记read。
        异常: 原请求或构造错误传播，不伪造metadata。
        """
        request = LegacyCANRequest(input_path or self.input_path, self.dbc_path, (self.field,))
        kwargs = {'_worker_target': observed_real_worker} if observed else {}
        read = module.LegacyCANProcessRead(request, self.budget, **kwargs)
        self.reads.append(read)
        return read

    def test_real_four_frames_metadata_idle_ack_and_true_eof(self):
        """核真实值/同刻原序、INIT零读取及ACK不授权，额外PULL确认EOF后才完成。

        参数: 无。返回: None。异常: 原产品错误或精确值/资源/许可断言失败。
        """
        read = self.real_read(observed=True)
        self.assertIsNone(read.worker_pid, '构造不得spawn')
        with self.assertRaises(RuntimeError):
            _ = read.metadata
        self.assertIs(iter(read), read)
        self.assertIs(read.start(), read)
        pid = read.worker_pid
        self.assertIs(type(pid), int)
        self.assertGreater(pid, 0)
        self.assert_status(read, (0, 0, 0))
        self.assertIs(read.start(), read)
        self.assertEqual(read.worker_pid, pid, '重复start不得重载DBC或换进程')
        metadata = read.metadata
        self.assertEqual(metadata['profile'], PROFILE_ID)
        self.assertEqual(metadata['vendor_sha256'], VENDOR_SHA256)
        self.assertEqual(metadata['fields'][0]['unit'], 'V')
        self.assertEqual(dict(metadata['fields'][0]['locator']), {
            'channel': 0,  'signal': 'Sample', 'frame_id': 256,
            'is_extended': False, 'is_fd': False})
        with self.assertRaises(TypeError):
            metadata['fields'][0]['unit'] = 'W'
        first = next(read)
        self.assert_status(read, (1, 1, 1))
        self.assertEqual(read._exchange({'op': 'ack', 'request_id': 0}), {'op': 'ack', 'request_id': 0})
        self.assert_status(read, (1, 1, 1))
        rows = (first, *tuple(read))
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(type(row) is LegacyDecodedFrame for row in rows))
        self.assertEqual(tuple(row.sequence for row in rows), (0, 1, 2, 3))
        self.assertEqual(tuple(row.values['Sample'] for row in rows), (-1, 3, 5, 7),
            '真实DBC factor2/offset-1只能施加一次')
        self.assertEqual(tuple(row.frame.timestamp for row in rows), tuple(item[0] for item in FIXTURE_ROWS))
        self.assertEqual(tuple(row.frame.data for row in rows), tuple(bytes([item[1]]) for item in FIXTURE_ROWS))
        self.assertTrue(all(row.frame.arbitration_id == 256 and row.frame.channel == 0
            and row.frame.dlc == 1 and not row.frame.is_extended_id and not row.frame.is_fd for row in rows))
        self.assertEqual(read.counters, {'pulls_issued': 5, 'items_returned': 4, 'items_accepted': 4})
        self.assertTrue(read.finished and read.closed and read._process_stopped)
        self.assertIsNone(read._process)
        self.assertIsNone(read._connection)
        self.assertEqual(read._exit_code, 0)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        with self.assertRaises(StopIteration):
            next(read)
        with self.assertRaises(ResultClosedError):
            _ = read.metadata
        trace = self.read_trace()
        self.assertEqual([item['rule'] for item in trace].count('load_file'), 1)
        self.assertEqual([item['rule'] for item in trace].count('next'), 5)
        self.assertEqual([item['rule'] for item in trace].count('parse'), 4)
        self.assertEqual(trace[0], {'rule': 'load_file', 'args': [str(self.dbc_path)], 'kwargs': {}})

    def test_two_pulls_close_has_no_third_original_call(self):
        """在真实STATUS屏障后关闭，子退出trace只能为原链两帧前缀。

        参数: 无。返回: None。异常: 原读取/关闭或前缀断言失败。
        """
        read = self.real_read(observed=True).start()
        self.assertEqual((next(read).sequence, next(read).sequence), (0, 1))
        self.assert_status(read, (2, 2, 2))
        read.close()
        read.close()
        self.assertTrue(read.closed and read._process_stopped)
        self.assert_no_completion(read)
        self.assertEqual(read.counters, {'pulls_issued': 2, 'items_returned': 2, 'items_accepted': 2})
        with self.assertRaises(ResultClosedError):
            next(read)
        trace = self.read_trace()
        self.assertEqual([item['rule'] for item in trace].count('next'), 2)
        self.assertEqual([item['rule'] for item in trace].count('parse'), 2)
        self.assertEqual([item['data_hex'] for item in trace if item['rule'] == 'parse'], ['00', '02'])

    def test_parent_cancel_before_third_credit_keeps_same_owner(self):
        """第二帧费用释放前持续取消，原KI和同owner恢复且不授第三PULL。

        参数: 无。返回: None。异常: 原生产错误或取消/计账/前缀断言失败。
        """
        read = self.real_read(observed=True).start()
        next(read)
        next(read)
        self.assert_status(read, (2, 2, 2))
        current_cost, primary, hits = read._current_cost, KeyboardInterrupt('before third PULL'), []
        self.assertGreater(current_cost, 0, '故障必须命中真实当前记录的已付槽')
        original = self.budget.release_ram

        def release(amount):
            """只拒当前真实槽。参数: amount。返回: 原值。异常: 同primary或原release错误。"""
            if amount == current_cost:
                hits.append(amount)
                raise primary
            return original(amount)

        with patch.object(self.budget, 'release_ram', new=release):
            with self.assertRaises(KeyboardInterrupt) as caught:
                next(read)
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.can_process_read_cleanup_owner, read)
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt) as again:
                    read.close()
                self.assertIs(again.exception, primary)
        self.assertGreaterEqual(len(hits), 4, '持续故障必须实际重复命中本槽')
        self.assertEqual(read.counters['pulls_issued'], 2)
        read.close()
        self.assertTrue(read.closed and read._process_stopped)
        self.assert_no_completion(read)
        trace = self.read_trace()
        self.assertEqual([item['rule'] for item in trace].count('next'), 2)
        self.assertEqual([item['rule'] for item in trace].count('parse'), 2)

    def test_unknown_id_keeps_original_empty_dict_without_filtering(self):
        """原parse未知ID返回空dict也交付原帧，不能为列投影少解码一次。

        参数: 无。返回: None。异常: 原can或产品错误、原帧/许可断言失败。
        """
        import can
        path = self.root / 'unknown.blf'
        writer = can.BLFWriter(str(path))
        try:
            for sequence, frame_id in enumerate((0x101, 0x100)):
                writer.on_message_received(can.Message(timestamp=BASE_TIMESTAMP + sequence * .125,
                    arbitration_id=frame_id, is_extended_id=False, channel=0, data=[2]))
        finally:
            writer.stop()
        read = self.real_read(observed=True, input_path=path).start()
        first, second = next(read), next(read)
        self.assertEqual((first.sequence, first.frame.arbitration_id, dict(first.values)), (0, 0x101, {}))
        self.assertEqual((second.sequence, second.frame.arbitration_id, dict(second.values)),
            (1, 0x100, {'Sample': 3}))
        self.assert_status(read, (2, 2, 2))
        with self.assertRaises(StopIteration):
            next(read)
        self.assertTrue(read.finished)


class LegacyCANProtocolTests(ProcessFixture):
    """不依赖CAN extra，用真正spawn与64KiB wire核客户端生命周期和失败分类。"""

    def test_constructor_and_iter_do_not_spawn_and_close_rejects_metadata(self):
        """构造只预约，未知路径不读；ready门槛及提前关闭不能当EOF。

        参数: 无。返回: None。异常: 原构造/关闭错误或无IO门槛断言失败。
        """
        with patch.object(module.multiprocessing, 'get_context', side_effect=AssertionError('构造不准spawn')):
            read = self.make_read()
            self.assertIs(iter(read), read)
            self.assertIsNone(read.worker_pid)
            self.assertEqual(read.counters, {'pulls_issued': 0, 'items_returned': 0, 'items_accepted': 0})
            with self.assertRaises(RuntimeError):
                _ = read.metadata
            read.close()
        self.assertTrue(read.closed)
        self.assert_no_completion(read)
        with self.assertRaises(ResultClosedError):
            _ = read.metadata
        with self.assertRaises(ResultClosedError):
            next(read)

    def test_bad_json_overlong_and_wrong_credit_never_finish(self):
        """真实Pipe上坏JSON/超64KiB/错id均失败并关资源，不吞错当EOF。

        参数: 无。返回: None。异常: 原子进程错误或失败/资源断言。
        """
        for mode in ('bad_json', 'overlong', 'wrong_id', 'bool_id', 'bool_eof'):
            with self.subTest(mode=mode):
                read = self.make_read(mode=mode).start()
                with self.assertRaises(SourceReadError):
                    next(read)
                self.assert_no_completion(read)
                read.close()
                self.assertTrue(read.closed and read._process_stopped)
                self.assertEqual(read.counters['items_accepted'], 0)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_ready_missing_dependency_wrong_hash_version_or_unit_rejected(self):
        """READY必须证明声明的同次元数据，不能只核locator就接受缺项/错版本。

        参数: 无。返回: None。异常: 原子进程错误或错误metadata接受/漏账断言。
        """
        for mode in ('ready_missing', 'ready_hash', 'ready_version', 'ready_unit',
                'ready_channel_bool', 'ready_extended_int'):
            with self.subTest(mode=mode):
                read = self.make_read(mode=mode)
                with self.assertRaises(SourceReadError):
                    read.start()
                self.assert_no_completion(read)
                self.assertEqual(read.counters['pulls_issued'], 0)
                read.close()
                self.assertTrue(read.closed and read._process_stopped)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_remote_error_has_explicit_facts_cause(self):
        """远端原错仅作事实cause，不假装本进程拿到原对象。

        参数: 无。返回: None。异常: 原wire或事实/不可变/关闭断言失败。
        """
        read = self.make_read(mode='remote_error').start()
        with self.assertRaises(SourceReadError) as caught:
            next(read)
        remote = caught.exception.__cause__
        self.assertIs(type(remote), module.RemoteLegacyError)
        self.assertEqual((remote.phase, remote.request_id), ('pull', 0))
        self.assertEqual(remote.facts['type'], 'ValueError')
        self.assertEqual(remote.facts['message'], 'controlled original worker failure')
        self.assertEqual(remote.facts['notes'], ('controlled worker note',))
        with self.assertRaises(TypeError):
            remote.facts['message'] = 'changed'
        self.assert_no_completion(read)
        self.assertTrue(read.closed and read._process_stopped)

    def test_exit_without_eof_or_after_bad_exit_is_not_completion(self):
        """exit0无EOF、发EOF后exit7、EOF后仍活都不能封存正常完成。

        参数: 无。返回: None。异常: 原wire/进程错误或错误完成断言。
        """
        for mode in ('no_eof', 'bad_exit', 'eof_alive'):
            with self.subTest(mode=mode):
                read = self.make_read(mode=mode).start()
                with self.assertRaises(SourceReadError):
                    next(read)
                self.assert_no_completion(read)
                read.close()
                self.assertTrue(read.closed and read._process_stopped)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)


class LegacyCANProcessRecoveryTests(ProcessFixture):
    """真实进程/端点配合逐笔费用故障，核持续恢复和其他read的借用边界。"""

    def test_connection_close_before_and_after_cancel_preserves_other_read(self):
        """本端close前持续三次、真实close后取消分别恢复，另一个read继续活着。

        参数: 无。返回: None。异常: 原资源错误或恢复/隔离/费用断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                read, other = self.make_read(mode='stubborn').start(), self.make_read().start()
                expected = self.borrowed + other._held_cost
                real = read._connection
                primary = KeyboardInterrupt('actual parent Pipe.close')
                fault = ConnectionFault(real, error=primary, after=after)
                read._connection = fault
                try:
                    for _ in range(1 if after else 3):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            read.close()
                        self.assertIs(caught.exception, primary)
                        self.assertFalse(read.closed)
                        self.assert_no_completion(read)
                    self.assertEqual(fault.calls, 1 if after else 3,
                        '执行后已关端点不能为重复命中而再次关闭')
                    self.assertEqual(real.closed, after)
                    self.assert_status(other, (0, 0, 0))
                finally:
                    fault.error = None
                    read.close()
                self.assertTrue(real.closed and read.closed and read._process_stopped)
                self.assertEqual(self.budget.ram_bytes, expected)
                self.assert_status(other, (0, 0, 0))
                other.close()
                self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def _process_fault_case(self, operation, after):
        """在真实Process动作前后失败并恢复同一owner，不假造终止或已退状态。

        参数: operation为join/terminate/close；after指定先执行真实动作。
        返回: None。异常: 原资源错误或目标命中/恢复断言失败。
        """
        read, other = self.make_read(mode='stubborn').start(), self.make_read().start()
        expected, real = self.borrowed + other._held_cost, read._process
        primary = KeyboardInterrupt('actual Process.' + operation)
        fault = ProcessFault(real, operation, primary, after)
        read._process = fault
        try:
            for _ in range(1 if after else 3):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    read.close()
                self.assertIs(caught.exception, primary)
                self.assertFalse(read.closed)
                self.assertIs(read._process, fault)
                self.assert_no_completion(read)
            self.assertGreaterEqual(fault.calls, 1 if after else 3, '故障必须命中所指定真实动作')
            if operation == 'close':
                self.assertTrue(read._process_stopped, '真实进程已退后才允许关闭其进程句柄')
            self.assert_status(other, (0, 0, 0))
        finally:
            fault.error = None
            read.close()
        self.assertTrue(read.closed and read._process_stopped)
        self.assertIsNone(read._process)
        self.assertIsNone(read._connection)
        self.assertEqual(self.budget.ram_bytes, expected)
        self.assert_status(other, (0, 0, 0))
        other.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_process_join_terminate_close_before_and_after_recover(self):
        """三种实际进程动作前持续失败及执行后取消，不丢真实进程责任。

        参数: 无。返回: None。异常: 原操作错误或各目标/隔离/恢复断言失败。
        """
        for operation in ('join', 'terminate', 'close'):
            for after in (False, True):
                with self.subTest(operation=operation, after=after):
                    self._process_fault_case(operation, after)

    def test_parent_receive_cancel_keeps_primary_and_highest_real_owner(self):
        """PULL已授权后接收取消，持续join副错只附note且恢复同一真实owner。

        参数: 无。返回: None。异常: 原进程错误或取消身份/最高责任/借款断言。
        """
        read, other = self.make_read().start(), self.make_read().start()
        expected = self.borrowed + other._held_cost
        primary, secondary = KeyboardInterrupt('parent recv cancellation'), RuntimeError('persistent join cleanup')
        connection = ConnectionFault(read._connection, operation='recv_bytes', error=primary)
        process = ProcessFault(read._process, 'join', secondary, False)
        read._connection, read._process = connection, process
        try:
            with self.assertRaises(KeyboardInterrupt) as caught:
                next(read)
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.can_process_read_cleanup_owner, read)
            self.assertTrue(any('RuntimeError' in note and '旧CAN进程read' in note
                for note in getattr(primary, '__notes__', ())), '清理副错以真实类型和责任标签附note')
            for _ in range(3):
                with self.assertRaises(RuntimeError) as cleanup:
                    read.close()
                self.assertIs(cleanup.exception, secondary)
            self.assertGreaterEqual(process.calls, 4)
            self.assertEqual(connection.calls, 1)
            self.assertEqual(read.counters, {'pulls_issued': 1, 'items_returned': 0, 'items_accepted': 0})
            self.assert_no_completion(read)
            self.assert_status(other, (0, 0, 0))
        finally:
            connection.error = process.error = None
            read.close()
        self.assertTrue(read.closed and read._process_stopped)
        self.assertEqual(self.budget.ram_bytes, expected)
        other.close()

    def test_constructor_reserve_before_after_cancel_with_real_fee_recovery(self):
        """构造首次reserve执行前取消不漏账，执行后取消加持续release失败有真实owner。

        参数: 无。返回: None。异常: 原构造错误或原取消/真实费用恢复断言。
        """
        primary, secondary = KeyboardInterrupt('fixed reserve cancellation'), RuntimeError('fixed release blocked')
        request = LegacyCANRequest(self.input_path, self.dbc_path, (self.field,))
        original_reserve = self.budget.reserve_ram
        with patch.object(self.budget, 'reserve_ram', side_effect=primary):
            with self.assertRaises(KeyboardInterrupt) as before:
                module.LegacyCANProcessRead(request, self.budget)
        self.assertIs(before.exception, primary)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

        def reserve(amount):
            """先付真实费用再取消。参数: amount。返回: 无。异常: primary或原reserve错误。"""
            original_reserve(amount)
            raise primary

        with patch.object(self.budget, 'reserve_ram', new=reserve), \
                patch.object(self.budget, 'release_ram', side_effect=secondary) as released:
            with self.assertRaises(KeyboardInterrupt) as after:
                module.LegacyCANProcessRead(request, self.budget)
            self.assertIs(after.exception, primary)
            owner = primary.can_process_read_cleanup_owner
            self.assertIs(type(owner), module.LegacyCANProcessRead)
            self.reads.append(owner)
            self.assertIsNone(owner.worker_pid)
            self.assertEqual(owner._held_cost, owner._fixed_cost)
            self.assertGreater(owner._fixed_cost, 0)
            self.assertEqual(self.budget.ram_bytes, self.borrowed + owner._held_cost)
            for _ in range(3):
                with self.assertRaises(RuntimeError) as cleanup:
                    owner.close()
                self.assertIs(cleanup.exception, secondary)
            self.assertGreaterEqual(released.call_count, 4)
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_release_after_cancel_never_credits_borrowed_budget_twice(self):
        """真实fee释放后取消，槽已归零；同owner重试不得抵销调用方借款。

        参数: 无。返回: None。异常: 原清理错误或真实交易/幂等断言。
        """
        read = self.make_read().start()
        target, primary, hits = read._metadata_cost, KeyboardInterrupt('after metadata release'), []
        self.assertGreater(target, 0)
        original = self.budget.release_ram

        def release(amount):
            """只在真实目标释放后首次取消。参数: amount。返回: 原值。异常: 原primary或release错误。"""
            value = original(amount)
            if amount == target and not hits:
                hits.append(amount)
                raise primary
            return value

        with patch.object(self.budget, 'release_ram', new=release):
            with self.assertRaises(KeyboardInterrupt) as caught:
                read.close()
            self.assertIs(caught.exception, primary)
            self.assertEqual(read._metadata_cost, 0)
            self.assertEqual(self.budget.ram_bytes, self.borrowed + read._held_cost)
            self.assertFalse(read.closed)
        self.assertEqual(hits, [target])
        read.close()
        read.close()
        self.assertTrue(read.closed and read._process_stopped)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
