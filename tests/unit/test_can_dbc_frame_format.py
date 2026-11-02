"""验证已授权的DBC FD声明与真实经典CAN帧之间的单向兼容。

测试现场生成独立DBC/BLF，通过真实spawn旧链和公开AnalysisRunner读取；不改Ref/vendor、
原reader/decoder或真实帧flags。仅DBC为FD而selector及实际帧为经典CAN可继续，
同时要求结果与发布清单留下固定结构化提示。相反方向、错误定位、非法READY提示
仍严格拒绝。原load/next/parse由隔离观察包装透传计数，不代替任何原调用。
小夹具只含四帧，结果游标有限耗尽；每个正常或失败路径都核真实read关闭及RAM0。
本文件只在work产生夹具与发布物，可选CAN依赖确实缺失才skip，不将skip视为通过。
"""

from configuration_fixtures import current_fixture

# 公共声明与测试工具可静态导入；CAN依赖延迟到现场夹具/子进程执行。
from dataclasses import FrozenInstanceError, replace
from functools import partial
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.legacy import process_read as process_module
from chronaxis.legacy import batch_read as batch_module
from chronaxis.legacy.records import LegacyCANField, LegacyCANRequest
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.protocol import SourceReadError


HAS_CAN = all(importlib.util.find_spec(name) is not None for name in ('can', 'cantools', 'natsort'))
WORK = Path(__file__).resolve().parents[2] / 'work/m2-real-acceptance-tests/dbc-frame-format'
BASE = 1700000000.0


def observed_worker(connection, **options):
    """透传实际批政策并观察真实vendor调用，不改输入或解码策略。

    参数: 原连接及当前worker选项。返回: 原返回。异常: 原进程或追踪错误。
    """
    from chronaxis.legacy import worker
    from chronaxis.legacy.batch_worker import batch_worker_main
    from test_legacy_can_process import observed_real_worker
    with patch.object(worker, 'worker_main', partial(batch_worker_main, **options)):
        return observed_real_worker(connection)


def invalid_notice_worker(connection, mode):
    """在真实worker已产出READY后仅破坏提示协议，用真实管道验证父校验。

    参数: connection为真实spawn端点；mode选择一个固定非法提示形状。
    返回: 原worker返回值。异常: 原worker或管道错误传播；不授额外PULL。
    """
    from chronaxis.legacy import worker
    from chronaxis.legacy.records import decode_packet, encode_packet

    class ReplyProxy:
        """只变更一次实际READY；所有其他连接行为透传同一端点。"""

        def send_bytes(self, payload):
            """注入固定坏提示。参数: payload原bytes。返回: 原发送结果。异常: 原wire错误。"""
            packet = decode_packet(payload)
            if packet.get('op') == 'ready':
                notice = {'code': 'dbc_fd_classic_selector', 'dbc_is_fd': True,
                          'requested_is_fd': False}
                if mode == 'extra':
                    notice['unexpected'] = 1
                elif mode == 'dbc_bool':
                    notice['dbc_is_fd'] = 1
                elif mode == 'selector_bool':
                    notice['requested_is_fd'] = 0
                elif mode == 'reverse':
                    notice.update(dbc_is_fd=False, requested_is_fd=True)
                elif mode == 'code':
                    notice['code'] = 'arbitrary_compatibility'
                elif mode == 'locator':
                    packet['fields'][0]['locator']['is_fd'] = True
                elif mode == 'null':
                    notice = None
                elif mode == 'missing':
                    del notice['dbc_is_fd']
                packet['fields'][0]['frame_format_compatibility'] = notice
                payload = encode_packet(packet)
            return connection.send_bytes(payload)

        def __getattr__(self, name):
            """透传真实连接。参数: name属性名。返回: 原属性。异常: 原访问错误。"""
            return getattr(connection, name)

    return worker.worker_main(ReplyProxy())


@unittest.skipUnless(HAS_CAN, '可选CAN依赖can/cantools/natsort确实未全部安装')
class CANDBCFrameFormatTests(unittest.TestCase):
    """固定小输入证明单向兼容、实际帧严格匹配及可发布的真实提示。"""

    def fixture(self, *, dbc_fd=True, actual_fd=False, selector_fd=False,
                backend='reference', size=2, locator_changes=None, source_type='can_blf'):
        """生成八字节标准帧DBC/BLF及实际公共计划，不复制真实用户输入。

        参数: 三个fd参数分别控制DBC元数据、原帧和显式selector；backend/size为真实执行参数；
            locator_changes只用于原定位严格拒绝负例。返回: (work,plan)。
        异常: 夹具IO、DBC模型或公开计划错误直接传播；不修改原始资料。
        """
        import can
        work = WORK / uuid4().hex
        work.mkdir(parents=True)
        dbc, blf = work / 'synthetic.dbc', work / 'synthetic.blf'
        dbc_text = ('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 8 Node\n SG_ Voltage : 0|16@1+ (1,0) [0|65535] "V" Node\n')
        if dbc_fd:
            # 标准FD在Vector公开VFrameFormat枚举中为14；不伪造原BLF消息的is_fd。
            dbc_text += ('BA_DEF_ BO_ "VFrameFormat" ENUM "StandardCAN","ExtendedCAN",'
                '"reserved","J1939PG","reserved","reserved","reserved","reserved",'
                '"reserved","reserved","reserved","reserved","reserved","reserved",'
                '"StandardCAN_FD","ExtendedCAN_FD";\n'
                'BA_DEF_DEF_ "VFrameFormat" "StandardCAN";\n'
                'BA_ "VFrameFormat" BO_ 256 14;\n')
        dbc.write_text(dbc_text, encoding='utf-8')
        writer = can.BLFWriter(blf)
        try:
            # 未知ID也照原链parse一次；实际目标数据按手算1/3/5V，不重施DBC缩放。
            for second, frame_id, value in ((0, 256, 1), (.5, 257, 9), (1, 256, 3), (2, 256, 5)):
                writer.on_message_received(can.Message(timestamp=BASE + second,
                    arbitration_id=frame_id, is_extended_id=False, channel=0,
                    is_fd=actual_fd, data=value.to_bytes(2, 'little') + b'\0' * 6))
        finally:
            writer.stop()
        locator = dict(channel=1,  signal='Voltage', frame_id=256,
                       is_extended=False, is_fd=selector_fd)
        locator.update(locator_changes or {})
        # 全量解码仍由当前strict长度政策执行，观察器透传真实v5协议。
        config = dict(config_version=3,
            dataset=dict(name='can_format', entity='synthetic', session='session',
                         domain=dict(start='0s', end='3s')),
            sources=[dict(name='bus', source_type='can_blf', path=str(blf),
                legacy_profile='sclicer-functions-v1', decode_scope='all',
                dbc_by_channel={'1': str(dbc)},
                time=dict(time_type='relative', unit='s', origin='synthetic_clock', offset='-1700000000s'))],
            signals=[dict(name='voltage', source='bus', field=locator,
                          dtype='float64', unit='V', valid_for='10s')],
            rules=[], windows=[], calculations=[dict(name='samples', scope='session', operation='select', expr='voltage')],
            outputs=dict(tables='jsonl' if backend == 'reference' else 'csv', manifest='json'),
            execution=dict(backend=backend, batch_rows=size, memory_budget_bytes=256 * 1024**2),
            metadata=dict(device_label='home', data_kind='synthetic'))
        if source_type != 'can_blf':
            source = config['sources'][0]
            source.pop('legacy_profile')
            source.pop('decode_scope')
            source.update(source_type=source_type, time=dict(time_type='relative', unit='s', origin='synthetic_clock'))
            rows = ((0, 256, 1), (.5, 257, 9), (1, 256, 3), (2, 256, 5))
            if source_type == 'can_asc':
                path = work / 'synthetic.asc'
                path.write_text('date Tue Nov 14 22:13:20 2023\nbase hex timestamps absolute\n'
                    + ''.join(f'{time} 1 {frame_id:X} Rx d 8 {value:02X} 00 00 00 00 00 00 00\n'
                              for time, frame_id, value in rows), encoding='utf-8')
            else:
                path = work / 'synthetic.csv'
                path.write_text('time,id,data,length\n' + ''.join(f'{time},{frame_id:X},{value:02X} 00 00 00 00 00 00 00,8\n'
                                       for time, frame_id, value in rows), encoding='utf-8')
                fields = {name: {'column': index} for index, name in enumerate(
                    ('timestamp', 'frame_id', 'data', 'payload_length'), 1)}
                fields.update({name: {'fixed': value} for name, value in (
                    ('channel', 0), ('is_rx', True), ('is_extended', False), ('is_fd', False), ('frame_kind', 'data'))})
                source['parser'] = dict(time_format='numeric', id_base=16, layout=dict(fields=fields))
            source['path'] = str(path)
        return work, AnalysisPlan.from_dict(current_fixture(config), base_dir=work)

    def run_observed(self, plan, work, children):
        """只替换私有测试缝的spawn目标为透传观察器，保原构造和执行。

        参数: plan/work为真输入；children收集实际read。返回: 公开AnalysisResult。
        异常: 原AnalysisRunner错误传播，已创建read仍可在children检查真实关闭事实。
        """
        original = process_module.LegacyCANProcessRead.__init__

        def initialize(read, *args, **kwargs):
            """记录真实read并调用原构造。参数: 原args/kwargs。返回: None。异常: 原构造错。"""
            original(read, *args, **kwargs)
            children.append(read)

        with patch.object(process_module.LegacyCANProcessRead, '__init__', new=initialize), \
                patch.object(batch_module, 'batch_worker_main', new=observed_worker):
            return AnalysisRunner().run(plan, work_dir=work / 'run')

    def rows(self, result):
        """有限耗尽并关闭真实指标游标。参数: result。返回: tuple。异常: 原读取/关闭错误。"""
        reader = result.iter_selections()
        try:
            return tuple(reader)
        finally:
            reader.close()

    def assert_trace(self, work, *, next_count, parse_count):
        """检查真实旧入口计数，不把方法构造次数当实际扫描。

        参数: work为夹具根；两个count是手算许可/原帧数量。返回: None。异常: 原IO/断言。
        """
        path = work / 'process-trace.jsonl'
        with path.open(encoding='utf-8') as handle:
            facts = [json.loads(line) for line in handle]
        self.assertEqual(sum(row['rule'] == 'load_file' for row in facts), 1)
        self.assertEqual(sum(row['rule'] == 'next' for row in facts), next_count)
        self.assertEqual(sum(row['rule'] == 'parse' for row in facts), parse_count)
        # 不用批次数替代旧调用证据：每条原帧仍须next后紧接一次parse，末尾仅多一次EOF。
        self.assertEqual([row['rule'] for row in facts],
                         ['load_file'] + ['next', 'parse'] * parse_count
                         + ['next'] * (next_count - parse_count))
        parsed = [row for row in facts if row['rule'] == 'parse']
        expected = ((0, 256, 1), (.5, 257, 9), (1, 256, 3), (2, 256, 5))[:parse_count]
        self.assertEqual([(row['timestamp'], row['arbitration_id'], row['data_hex']) for row in parsed],
                         [(BASE + second, frame_id, (value.to_bytes(2, 'little') + b'\0' * 6).hex())
                          for second, frame_id, value in expected])

    def assert_closed_reads(self, children):
        """每例核实际进程/连接已清、共享账归零。参数: children。返回: None。异常: 断言。"""
        self.assertEqual(len(children), 1)
        for read in children:
            self.assertTrue(read.closed)
            self.assertIsNone(read._process)
            self.assertIsNone(read._connection)
            self.assertEqual(read._budget.ram_bytes, 0)

    def test_fd_dbc_classic_frames_publish_structured_notice(self):
        """真实经典四帧经FD声明DBC读一次，手算值、出处、提示与两种发布均保留。

        参数: 无。返回: None。异常: 兼容、真实帧或发布/资源/原调用计数任何差异即失败。
        """
        for backend, size in (('reference', 1), ('numpy', 7)):
            with self.subTest(backend=backend, size=size):
                work, plan = self.fixture(backend=backend, size=size)
                children = []
                result = self.run_observed(plan, work, children)
                try:
                    rows = self.rows(result)
                    self.assertEqual(tuple((row.time_ns, row.value) for row in rows),
                                     ((0, 1.0), (1000000000, 3.0)))
                    self.assertEqual(len(result.metadata.frame_format_notices), 1)
                    source, notice = result.metadata.frame_format_notices[0]
                    self.assertEqual(source, 'bus')
                    self.assertEqual((notice.alias, notice.channel, notice.signal,
                        notice.frame_id, notice.is_extended, notice.dbc_is_fd, notice.requested_is_fd,
                        notice.code), ('voltage', 0, 'Voltage', 256, False, True, False,
                                       'dbc_fd_classic_selector'))
                    with self.assertRaises(FrozenInstanceError):
                        notice.dbc_is_fd = False
                    # 两种表格式仅复制已完成结果；同次read不因发布增加load/parse。
                    for number in (1, 2):
                        published = result.write(work / ('published-' + str(number)))
                        manifest = json.loads(published.manifest_path.read_text(encoding='utf-8'))
                        self.assertEqual(manifest['run']['frame_format_notices'],
                                         [dict(source='bus', alias='voltage', channel=0,  signal='Voltage',
                                               frame_id=256, is_extended=False, dbc_is_fd=True,
                                               requested_is_fd=False, code='dbc_fd_classic_selector')])
                        self.assertTrue(any('DBC声明CAN FD' in text and '原帧未转换' in text
                                            for text in manifest['run']['limitations']))
                    self.assertEqual(children[0].counters,
                        {'pulls_issued': 1, 'items_returned': 4, 'items_accepted': 4,
                         'frames_authorized': 4096, 'records_returned': 3})
                    self.assert_trace(work, next_count=5, parse_count=4)
                finally:
                    result.close()
                self.assert_closed_reads(children)

    def test_equal_frame_formats_have_no_notice(self):
        """普通经典及普通FD均不产生提示，当前READY与简明清单仍一致。

        参数: 无。返回: None。异常: 无差异路径错误、额外字段或资源泄漏即失败。
        """
        original = batch_module.LegacyCANBatchRead._check_ready
        for fd in (False, True):
            with self.subTest(fd=fd):
                work, plan = self.fixture(dbc_fd=fd, actual_fd=fd, selector_fd=fd)
                packets, children = [], []

                def check(read, packet):
                    """观察真实READY后调用原核查。参数: read/packet。返回: 原结果。异常: 原协议错。"""
                    packets.append(packet)
                    return original(read, packet)

                with patch.object(batch_module.LegacyCANBatchRead, '_check_ready', new=check):
                    result = self.run_observed(plan, work, children)
                try:
                    self.assertEqual(len(self.rows(result)), 2)
                    self.assertEqual(len(packets), 1)
                    self.assertEqual(set(packets[0]), {'op', 'version', 'profile', 'worker_pid',
                        'fields', 'dependency_versions', 'vendor_sha256', 'base_version', 'input_paths', 'decode_policy'})
                    self.assertEqual(set(packets[0]['fields'][0]), {'locator', 'unit'})
                    self.assertEqual(packets[0]['decode_policy'], 'strict')
                    self.assertEqual(result.metadata.frame_format_notices, ())
                    self.assertNotIn('frame_format_notices', result.metadata.to_dict())
                    self.assertNotIn('can_sources', result.metadata.to_dict())
                    self.assertFalse(any('DBC声明CAN FD' in text for text in result.metadata.limitations))
                    self.assert_trace(work, next_count=5, parse_count=4)
                finally:
                    result.close()
                self.assert_closed_reads(children)

    def test_text_formats_publish_same_notice_without_diagnostics(self):
        """ASC和原始CSV同次核DBC提示，默认不要求trace或完整性摘要。

        参数: 无。返回: None。异常: 手算选择、真实提示或关闭账本错误即失败。
        """
        for source_type in ('can_asc', 'raw_can_csv'):
            for backend in ('reference', 'numpy'):
                with self.subTest(source_type=source_type, backend=backend):
                    work, plan = self.fixture(source_type=source_type, backend=backend)
                    result = AnalysisRunner().run(plan, work_dir=work / 'run')
                    budget = result.spool.budget
                    try:
                        self.assertEqual([(row.time_ns, row.value) for row in self.rows(result)],
                                         [(0, 1.), (1000000000, 3.)])
                        published = result.write(work / 'published')
                        run = json.loads(published.manifest_path.read_text(encoding='utf-8'))['run']
                        self.assertNotIn('diagnostics', run)
                        self.assertEqual(len(run['frame_format_notices']), 1)
                        notice = run['frame_format_notices'][0]
                        self.assertEqual((notice['source'], notice['alias'], notice['dbc_is_fd'],
                                          notice['requested_is_fd']), ('bus', 'voltage', True, False))
                    finally:
                        result.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_notice_retention_cancellation_preserves_error_and_closes(self):
        """真实EOF提示复制前后取消均保原对象和退款，不发布成功前缀。

        参数: 无。返回: None。异常: 真实读取/原错身份/关闭责任断言失败。
        """
        from chronaxis.execution.record_source_cursor import RecordSourceCursor
        original = RecordSourceCursor._retain_frame_notices
        for after in (False, True):
            work, plan = self.fixture()
            marker = KeyboardInterrupt('notice retention cancellation')
            children, cursors = [], []

            def cancel(cursor):
                """仅在真实EOF处取消。参数: 实际cursor。返回: 无。异常: marker原对象。"""
                cursors.append(cursor)
                if after:
                    original(cursor)
                    self.assertEqual(len(cursor.frame_format_notices), 1)
                raise marker

            with patch.object(RecordSourceCursor, '_retain_frame_notices', cancel), \
                    self.assertRaises(KeyboardInterrupt) as caught:
                self.run_observed(plan, work, children)
            self.assertIs(caught.exception, marker)
            self.assertEqual(len(cursors), 1)
            self.assertTrue(cursors[0]._closed)
            self.assertEqual(cursors[0]._held_cost, 0)
            self.assert_trace(work, next_count=5, parse_count=4)
            self.assert_closed_reads(children)

    def test_explicit_flags_filter_actual_frames_and_reject_reverse_dbc(self):
        """显式帧型过滤不匹配原帧；DBC反向兼容仍在INIT拒绝。

        参数: 无。返回: None。异常: 错误帧型被接受、调用次数改变或失败漏清理即失败。
        """
        for dbc_fd, actual_fd, selector_fd, pulls in ((True, True, False, 1),
                (True, False, True, 1), (False, True, True, 0)):
            with self.subTest(dbc_fd=dbc_fd, actual_fd=actual_fd, selector_fd=selector_fd):
                work, plan = self.fixture(dbc_fd=dbc_fd, actual_fd=actual_fd, selector_fd=selector_fd)
                children = []
                if pulls:
                    result = self.run_observed(plan, work, children)
                    try:
                        self.assertEqual(self.rows(result), ())
                    finally:
                        result.close()
                else:
                    with self.assertRaisesRegex(Exception, 'FD'):
                        self.run_observed(plan, work, children)
                self.assertEqual(children[0].counters['pulls_issued'], pulls)
                # 新批协议已获准在取消/拒绝前有一批读出；四帧夹具恰好在首批内。
                # 原错误仍在首个目标值交付前拒绝，不伪造只读取一条的旧计数。
                returned = 4 if pulls else 0
                self.assertEqual(children[0].counters['items_returned'], returned)
                self.assertEqual(children[0].counters['items_accepted'], returned)
                self.assertEqual(children[0].counters['records_returned'], 3 if pulls else 0)
                self.assertEqual(children[0].counters['frames_authorized'], 4096 if pulls else 0)
                self.assert_trace(work, next_count=5 if pulls else 0, parse_count=returned)
                self.assert_closed_reads(children)

    def test_original_message_signal_id_and_extended_checks_stay_strict(self):
        """单向FD兼容不能掩盖原message/signal/ID/标准扩展任何错误。

        参数: 无。返回: None。异常: 错定位被接受、读取发生于元数据拒绝之后或漏账即失败。
        """
        # 已删除参数在静态配置层报错，不再读取DBC验证一个冗余名称。
        with self.assertRaisesRegex(Exception, 'message'):
            self.fixture(locator_changes={'message': 'Other'})
        for changes in ({'signal': 'Missing'}, {'frame_id': 258},
                        {'is_extended': True}):
            with self.subTest(changes=changes):
                work, plan = self.fixture(locator_changes=changes)
                children = []
                with self.assertRaises(Exception) as caught:
                    self.run_observed(plan, work, children)
                self.assertIn('旧CAN子进程metadata失败', str(caught.exception))
                self.assertEqual(children[0].counters['pulls_issued'], 0)
                self.assert_trace(work, next_count=0, parse_count=0)
                self.assert_closed_reads(children)

    def test_ready_compatibility_rejects_extra_missing_and_non_native_bool(self):
        """真实READY的额外/缺失/反向/0或1冒bool/错误code及错locator全部拒绝。

        参数: 无。返回: None。异常: 任一伪提示通过或破坏借款基线/真实进程清理即失败。
        """
        work, plan = self.fixture()
        spec = plan.sources[0].config
        field = LegacyCANField(0, 'Voltage', 256, False, False)
        for mode in ('extra', 'missing', 'dbc_bool', 'selector_bool', 'reverse', 'code', 'locator', 'null'):
            with self.subTest(mode=mode):
                budget = ResourceBudget(16 * 1024**2)
                budget.reserve_ram(777)
                read = process_module.LegacyCANProcessRead(LegacyCANRequest(spec.path, spec.dbc_path, (field,)),
                    budget, _worker_target=partial(invalid_notice_worker, mode=mode))
                try:
                    with self.assertRaises(SourceReadError):
                        read.start()
                    self.assertFalse(read.finished)
                    self.assertTrue(read.closed)
                    self.assertEqual(read.counters['pulls_issued'], 0)
                    self.assertIsNone(read._process)
                    self.assertIsNone(read._connection)
                    self.assertEqual(budget.ram_bytes, 777)
                finally:
                    read.close()
                    budget.release_ram(777)
                self.assertEqual(budget.ram_bytes, 0)

    def test_notice_model_freezing_and_original_binding_link(self):
        """真实提示不可变、原生类型严格且不能借同别名伪造另一个信号定位。

        参数: 无。返回: None。异常: 错误结构/重复别名/原绑定不符被接受或估费未覆盖即失败。
        """
        work, plan = self.fixture()
        children = []
        result = self.run_observed(plan, work, children)
        try:
            source, notice = result.metadata.frame_format_notices[0]
            field = plan.signals[0].definition.field
            self.assertEqual(LegacyCANField(notice.channel, notice.signal,
                notice.frame_id, notice.is_extended, notice.requested_is_fd).key, field)
            for changes in ({'dbc_is_fd': 1}, {'requested_is_fd': 0}, {'is_extended': 0},
                            {'channel': False}, {'dbc_is_fd': False}, {'code': 'other'}):
                with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                    replace(notice, **changes)
            for notices in ([('bus', notice)], (('bus', notice), ('bus', notice)),
                            (('bad.source', notice),), (('bus', {}),)):
                with self.subTest(notices=notices), self.assertRaises((TypeError, ValueError)):
                    replace(result.metadata, frame_format_notices=notices)
            plain = replace(result.metadata, frame_format_notices=())
            self.assertGreater(result.metadata.estimated_bytes(), plain.estimated_bytes())
            self.assertNotIn('frame_format_notices', plain.to_dict())
        finally:
            result.close()
        self.assert_closed_reads(children)

    def test_compatibility_ready_reserve_cancel_keeps_original_and_closes_owner(self):
        """真实兼容READY复制预约前后取消都保原对象，尚未PULL且最高链清至RAM0。

        参数: 无。返回: None。异常: 取消未命中、原对象被换、原帧超读或实际责任未释放即失败。
        """
        original_check = batch_module.LegacyCANBatchRead._check_ready
        original_reserve = ResourceBudget.reserve_ram
        for after in (False, True):
            with self.subTest(after=after):
                work, plan = self.fixture()
                marker = KeyboardInterrupt('compatibility metadata reserve cancellation')
                state = {'amount': None, 'hits': 0}
                children = []

                def check(read, packet):
                    """核实际READY后定位下一真实复制预约。参数: 原参数。返回: None。异常: 原校验错。"""
                    original_check(read, packet)
                    self.assertIn('frame_format_compatibility', packet['fields'][0])
                    state['amount'] = 4096 + 16 * process_module._wire_metadata_bytes(packet)

                def reserve(budget, amount):
                    """只在已核READY真实预约处前/后取消。参数: 原budget/amount。返回: None。异常: marker。"""
                    if state['amount'] is not None and amount == state['amount'] and state['hits'] == 0:
                        state['hits'] += 1
                        if after:
                            original_reserve(budget, amount)
                        raise marker
                    return original_reserve(budget, amount)

                with patch.object(batch_module.LegacyCANBatchRead, '_check_ready', new=check), \
                        patch.object(ResourceBudget, 'reserve_ram', new=reserve), \
                        self.assertRaises(KeyboardInterrupt) as caught:
                    self.run_observed(plan, work, children)
                self.assertIs(caught.exception, marker)
                self.assertEqual(state['hits'], 1)
                self.assertEqual(children[0].counters['pulls_issued'], 0)
                self.assert_trace(work, next_count=0, parse_count=0)
                self.assert_closed_reads(children)


if __name__ == '__main__':
    # spawn导入测试模块不运行suite；根统一使用unittest正式命令。
    unittest.main()
