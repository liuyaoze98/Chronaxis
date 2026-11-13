"""以公共AnalysisRunner验证原始BLF片段的真实生成、完整帧保留与可重复发布。

输入为八个手定原帧和一字节DBC；正活动为[0,2)、[3,4)，半开筛选应导出
原帧索引(0,1,2)/(4,5)，包括不参与信号分析的未知扩展帧和12字节FD帧。
运行前用真正BLFReader建立有限逻辑真值，生产运行只创建一个解码owner并打开一次BLF；
run完成全部原writer后，write向两个新目录只复制并核验封口BLF/索引。
空输入、无窗口、无事件、EOF零长交集、不同origin、文件篡改及复制取消分别
验证实际公开路径。测试只写work独立目录，不改变旧链、Ref或生产调用参数。
可选CAN库只在夹具中导入；缺依赖按原B2夹具明确skip，不冒称实际验收通过。
"""

from configuration_fixtures import current_fixture

# 仅标准库及静态产品类在导入期加载；B2 TestCase在方法内只借夹具，避免重复发现。
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from published_paths import published_file, export_root
import unittest
from unittest.mock import patch

from chronaxis import AnalysisError, AnalysisPlan, AnalysisRunner
from chronaxis.core.models import Interval
from chronaxis.legacy.export_write import LegacyCANProcessWrite
from chronaxis.sources.blf import BLFRead
from chronaxis.sources.text_can_decode import CANTextDecodeRead
from chronaxis.results import ResultFormatError
from chronaxis.results.artifact_exports import ArtifactExportStore


class CANRawRunnerTests(unittest.TestCase):
    """仅小夹具收集行作真值断言，生产资源与原输入计数由实际owner对象证明。

    每次fixture新建独立work和BLF。观察start只透传真实原方法，另外记录幂等
    入口与实际首次启动，不能把finish内部再次start当成第二个旧writer进程。
    """

    def fixture(self, *, backend='numpy', size=2, mode='normal', endpoint=False):
        """借B2夹具后重写本例专属BLF与计划，原输入真值读取发生在run之前。

        参数: backend/size选择真实后端和切分；mode为normal/empty/no_events/no_windows；
            endpoint使EOF5s出现真实start_only上升点。返回: (work,plan,truth)。
        异常: 真实文件、依赖或计划错误传播；不修改原B2测试或其他已有工件。
        """
        from test_can_runner import CANRunnerTests
        # 只借生成配置的方法；不继承或全局导入另一个TestCase，也不运行其测试方法。
        work, config, _ = CANRunnerTests.fixture(self, backend=backend, size=size, frames=())
        import can
        path = Path(config['sources'][0]['path'])
        specifications = [(0., 256, b'\x01', False, False),
            (.5, 257, b'\xaa', True, False), (1., 256, b'\x03', False, False),
            (2., 256, b'\x00', False, False), (3., 256, b'\x05', False, False),
            (3.5, 258, bytes(range(12)), False, True),
            (4., 256, b'\x00', False, False), (5., 256, b'\x01' if endpoint else b'\x00', False, False)]
        if mode not in ('normal', 'empty', 'no_events', 'no_windows'):
            raise ValueError('未知raw AnalysisRunner测试模式')
        writer = can.BLFWriter(path)
        try:
            for second, frame_id, data, extended, fd in (() if mode == 'empty' else specifications):
                if mode == 'no_events' and frame_id == 256:
                    data = b'\x00'
                writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                    arbitration_id=frame_id, is_extended_id=extended, channel=0, data=data,
                    is_fd=fd, is_rx=not fd, bitrate_switch=fd, error_state_indicator=fd))
        finally:
            writer.stop()
        config['dataset']['domain'] = dict(start='0s', end='6s')
        config['windows'] = [dict(name='activity', rule='active', anchor='activity',
            pre='0s', post='0s', merge='none')]
        if mode == 'no_windows':
            config['windows'] = []
        if endpoint:
            # 最后5s上升点可观察，窗口[5,6)与真实观测[0,5]仅接于5s。
            config['rules'] = [dict(name='active', rule_type='start_only', condition='voltage > 0',
                emit_initial=True, window_duration='1s')]
            config['windows'] = [dict(name='activity', rule='active', anchor='point',
                pre='0s', post='1s', merge='none')]
        config['outputs'] = dict(tables='jsonl' if backend == 'reference' else 'csv',
            manifest='json', can_frames=dict(source='bus', format='blf', scope='segments', source_time_reference='epoch'))
        config['diagnostics']['retain_work'] = True
        (work / 'plan.json').write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        # 真值保原浮点秒、完整公开flags/channel/dlc/data；不把此独立读取算作生产扫描。
        truth = self.logical_frames(path)
        return work, AnalysisPlan.from_dict(current_fixture(config), base_dir=work), truth

    def logical_frames(self, path):
        """读取本例有限BLF的公开逻辑帧并显式stop，保持原序而不排序或筛ID。

        参数: path为本例输入或导出BLF。返回: 包含完整原字段的tuple。
        异常: 真实BLF读取/关闭错误传播；不调用生产LegacyCANProcessRead。
        """
        import can
        reader = can.BLFReader(path)
        try:
            return tuple((frame.timestamp.hex(), frame.arbitration_id, frame.is_extended_id,
                frame.is_remote_frame, frame.is_error_frame, frame.channel, frame.dlc, bytes(frame.data),
                frame.is_fd, frame.is_rx, frame.bitrate_switch, frame.error_state_indicator) for frame in reader)
        finally:
            reader.stop()

    @contextmanager
    def process_observation(self):
        """观察实际读取owner与writer启动，不改变调用或帧处理。

        参数: 无。返回: 包含解码、文件读取和writer对象的有限dict。
        异常: 被观察原错误原样传播；补丁仅在本上下文中生效。
        """
        observed = dict(write_entries=[], reads=[], raw_reads=[], writers=[])
        decode_init = CANTextDecodeRead.__init__
        raw_init = BLFRead.__init__
        write_start = LegacyCANProcessWrite.start

        def start_decode(owner, *args, **kwargs):
            """记录真实解码owner。参数: 原构造参数。返回: None。异常: 原错误。"""
            decode_init(owner, *args, **kwargs)
            observed['reads'].append(owner)

        def start_raw(owner, *args, **kwargs):
            """记录实际文件打开。参数: 原构造参数。返回: None。异常: 原错误。"""
            raw_init(owner, *args, **kwargs)
            observed['raw_reads'].append(owner)

        def start_write(owner):
            """记录首次writer启动。参数: 原owner。返回: 原start返回。异常: 原错误。"""
            before = owner._started
            observed['write_entries'].append(owner)
            result = write_start(owner)
            if not before and owner._started:
                observed['writers'].append(owner)
            return result

        with patch.object(CANTextDecodeRead, '__init__', new=start_decode), \
                patch.object(BLFRead, '__init__', new=start_raw), \
                patch.object(LegacyCANProcessWrite, 'start', new=start_write):
            yield observed

    @contextmanager
    def forbid_original_processes(self):
        """禁止再次读取、解码或启动writer；发布仅复制已存在工件。

        参数: 无。返回: with上下文。异常: 任一构造或start被调用时AssertionError。
        """
        with patch.object(CANTextDecodeRead, '__init__', side_effect=AssertionError('发布重建解码owner')), \
                patch.object(BLFRead, '__init__', side_effect=AssertionError('发布重读BLF')), \
                patch.object(LegacyCANProcessWrite, 'start', side_effect=AssertionError('发布重启writer')):
            yield

    def run_plan(self, work, plan):
        """通过唯一公共入口实际运行，并登记最终结果清理。

        参数: work/plan为本例真实输入。返回: 活AnalysisResult。异常: 原公开运行错。
        """
        result = AnalysisRunner().run(plan, work_dir=work / 'run')
        self.addCleanup(result.close)
        return result

    def rows(self, result, table):
        """真实耗尽一个有限结果游标并关闭，不把未读后缀当作完成。

        参数: result为活结果；table为events/segments/calculations。返回: 小夹具行tuple。
        异常: 真实读取/关闭错误传播；不重跑分析。
        """
        reader = getattr(result, 'iter_' + table)()
        try:
            return tuple(reader)
        finally:
            reader.close()

    def records(self, result):
        """耗尽当前封口工件索引并确认真实FD关闭。参数: result。返回: 小夹具dict tuple。异常: 编码/IO/预算。"""
        store = result._artifact_exports
        self.assertIs(type(store), ArtifactExportStore)
        reader = store._sort._read(store._sort.path / f'{store._sort.level}-0.jsonl')
        try:
            records = tuple(record for _, _, record in reader)
            self.assertFalse(store._sort.handles)
            self.assertEqual(len(records), store.count)
            return records
        finally:
            reader.close()

    def frame_file(self, store, record):
        """定位真实BLF及其登记事实。参数: 工件仓/索引dict。返回: Path和文件dict。异常: 缺文件事实。"""
        fact = next(entry for entry in record['files'] if entry['name']=='frames.blf')
        return store.path / record['directory'] / fact['name'], fact

    def assert_processes_finished(self, observed, frames, writers):
        """核真实读取EOF、文件关闭及writer退出；计数不从业务结果反推。

        参数: observed为透传观察；frames为原帧数；writers为实际writer数。
        返回: None。异常: 文件、进程、EOF或计数不符使断言失败。
        """
        self.assertEqual(len(observed['reads']), 1)
        self.assertEqual(len(observed['raw_reads']), 1)
        reader = observed['reads'][0]
        raw = observed['raw_reads'][0]
        self.assertEqual(reader.count, frames)
        self.assertEqual(raw.count, frames)
        self.assertTrue(reader.exhausted)
        self.assertTrue(reader.closed)
        self.assertTrue(raw.closed)
        for slot in ('_raw', '_db', '_binding_resolver'):
            self.assertIsNone(getattr(reader, slot))
        for slot in ('_file', '_reader', '_iterator'):
            self.assertIsNone(getattr(raw, slot))
        self.assertEqual(len(observed['writers']), writers)
        # 操作系统允许PID复用；对象身份与真实退出/句柄事实一起证明每个writer已完成。
        self.assertEqual(len(set(observed['writers'])), writers)
        for owner in observed['writers']:
            self.assertTrue(owner.finished)
            self.assertTrue(owner.closed)
            self.assertTrue(owner._process_stopped)
            self.assertIs(type(owner.worker_pid), int)
            self.assertGreater(owner.worker_pid, 0)
            self.assertEqual(owner._exit_code, 0)
            self.assertIsNone(owner._connection)
            self.assertIsNone(owner._child_connection)
            self.assertIsNone(owner._process)

    def assert_closed_budget(self, result):
        """只通过最高result重复close，释放同次所有真实资源与RAM，保留工作文件。

        参数: result为本例结果。返回: None。异常: 关闭/重复抵销/FD残留使断言失败。
        """
        budget, store = result.spool.budget, result._artifact_exports
        result.close()
        result.close()
        self.assertEqual(budget.ram_bytes, 0)
        self.assertTrue(result._closed)
        self.assertTrue(store.closed)
        for slot in ('_input', '_output', '_index', '_cursor'):
            self.assertIsNone(getattr(store, slot))

    def assert_no_completed(self, work, destination):
        """核失败目标未安装，真实临时目录存在且没有completed标记。

        参数: work为本例新根；destination为失败发布目标。返回: None。
        异常: 已完成目标、缺失败现场或completed错误留存使断言失败。
        """
        self.assertFalse(destination.exists())
        temporary = tuple(work.glob('.' + destination.name + '.incomplete-*'))
        self.assertEqual(len(temporary), 1)
        self.assertTrue((temporary[0] / 'failure.json').exists())
        marker = temporary[0] / 'run_manifest.json'
        if marker.exists():
            self.assertNotEqual(json.loads(marker.read_text(encoding='utf-8'))['status'], 'completed')

    def test_real_two_segments_preserve_all_frames_and_repeat_publish_only_copies(self):
        """两后端及三批长保完整半开片段，重复发布只复制封口工件。参数: 无。返回: None。异常: 原帧/资源断言。"""
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                with self.subTest(backend=backend, size=size):
                    work, plan, truth = self.fixture(backend=backend, size=size)
                    self.assertEqual(len(truth), 8)
                    self.assertTrue(truth[1][2])
                    self.assertEqual((truth[5][7], truth[5][8:]), (bytes(range(12)), (True, False, True, True)))
                    with self.process_observation() as observed:
                        result = self.run_plan(work, plan)
                    self.assert_processes_finished(observed, 8, 2)
                    self.assertEqual([writer.counters['frames_written'] for writer in observed['writers']], [3, 2])
                    events, segments = self.rows(result, 'events'), self.rows(result, 'segments')
                    expected = ((0, 2_000_000_000), (3_000_000_000, 4_000_000_000))
                    self.assertEqual(tuple((row.start_ns, row.end_ns) for row in events), expected)
                    self.assertEqual(tuple((row.start_ns, row.end_ns) for row in segments), expected)
                    records = self.records(result)
                    self.assertEqual(tuple(record['index'] for record in records), (0, 1))
                    self.assertEqual(tuple(tuple(record['interval']) for record in records), expected)
                    self.assertEqual(tuple(record['segment_id'] for record in records), tuple(row.segment_id for row in segments))
                    expected_frames = (tuple(truth[index] for index in (0, 1, 2)), tuple(truth[index] for index in (4, 5)))
                    for record, frames in zip(records, expected_frames):
                        path, fact = self.frame_file(result._artifact_exports, record)
                        payload = path.read_bytes()
                        self.assertEqual((sha256(payload).hexdigest(), len(payload)), (fact['sha256'], fact['bytes']))
                        self.assertEqual(self.logical_frames(path), frames)
                        report=json.loads(path.with_name('manifest.json').read_text(encoding='utf-8'))
                        self.assertEqual((report['source'],report['frames']),('bus',len(frames)))
                    with self.forbid_original_processes():
                        for number in (1, 2):
                            output = work / ('published-' + str(number))
                            manifest = result.write(output)
                            packed = json.loads(manifest.manifest_path.read_text(encoding='utf-8'))
                            self.assertEqual((packed['status'],packed['exports']['record_count']),('completed',2))
                            public = [json.loads(line) for line in (published_file(manifest,'exports.jsonl')).read_text(encoding='utf-8').splitlines()]
                            self.assertEqual([row['segment_id'] for row in public],[row.segment_id for row in segments])
                            for record, frames in zip(public, expected_frames):
                                copied=export_root(manifest)/record['directory']/'frames.blf'
                                fact=next(f for f in record['files'] if f['name']=='frames.blf')
                                self.assertEqual(sha256(copied.read_bytes()).hexdigest(),fact['sha256'])
                                self.assertEqual(self.logical_frames(copied),frames)
                    self.assert_closed_budget(result)

    def test_empty_input_no_windows_and_no_events_publish_empty_inventory(self):
        """零片段不制造导出，当前索引保持为空。参数: 无。返回: None。异常: 假片段/额外writer/泄漏。"""
        for mode in ('empty', 'no_windows', 'no_events'):
            with self.subTest(mode=mode):
                work, plan, truth = self.fixture(mode=mode)
                with self.process_observation() as observed:
                    result = self.run_plan(work, plan)
                self.assert_processes_finished(observed, len(truth), 0)
                self.assertEqual(self.rows(result, 'segments'), ())
                self.assertEqual(self.records(result), ())
                if mode != 'no_windows':
                    self.assertEqual(self.rows(result, 'events'), ())
                self.assertEqual(result._artifact_exports.count,0)
                with self.forbid_original_processes():
                    published = result.write(work / 'published-empty')
                packed = json.loads(published.manifest_path.read_text(encoding='utf-8'))
                self.assertEqual((packed['status'],packed['exports']['record_count']),('completed',0))
                self.assertEqual((published_file(published,'exports.jsonl')).read_bytes(),b'')
                self.assert_closed_budget(result)

    def test_real_eof_start_only_point_exports_no_endpoint_frame(self):
        """EOF上升点仍有空片段，半开输出不能多写端点帧。参数: 无。返回: None。异常: 假区间/帧或泄漏。"""
        work, plan, _ = self.fixture(endpoint=True)
        with self.process_observation() as observed:
            result = self.run_plan(work, plan)
        records = self.records(result)
        self.assertEqual(len(records),3)
        segments=self.rows(result,'segments')
        last=next(row for row in segments if row.segment_id==records[-1]['segment_id'])
        self.assertEqual((last.start_ns,last.end_ns),(None,None))
        path,_=self.frame_file(result._artifact_exports,records[-1])
        self.assertEqual(self.logical_frames(path),())
        report=json.loads(path.with_name('manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(report['frames'],0)
        self.assertEqual(records[-1]['segment_id'],last.segment_id)
        self.assert_processes_finished(observed,8,3)
        self.assert_closed_budget(result)

    def test_different_parent_clock_is_rejected_before_any_writer(self):
        """相同数值坐标而origin不同的父规则不可筛另一CAN原帧，所有writer启动前拒绝。

        参数: 无。返回: None。异常: 误当同步、writer先启动或最高运行账本泄漏即失败。
        """
        work, plan, _ = self.fixture()
        config = json.loads((work / 'plan.json').read_text(encoding='utf-8'))
        config['sources'].insert(0, dict(name='gate_source', source_type='memory',
            time=dict(time_type='relative', unit='ns', origin='another_origin'), rows=[
                dict(time='0s', values={'flag': 1}), dict(time='2s', values={'flag': 0}),
                dict(time='6s', values={'flag': 0})]))
        config['signals'].append(dict(name='gate', source='gate_source', field='flag',
            dtype='float64', unit='1', valid_for='10s'))
        config['rules'][0]['condition'] = 'gate > 0'
        plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=work)
        with self.process_observation() as observed, self.assertRaises(AnalysisError) as caught:
            AnalysisRunner().run(plan, work_dir=work / 'clock-run')
        self.assertEqual(len(observed['writers']), 0)
        self.assertEqual(len(observed['write_entries']), 0)
        self.assertEqual(len(observed['reads']), 1)
        # 当前在创建输出消费者时拒绝不同时间基准；读取器真实关闭但没有消费到EOF。
        self.assertTrue(observed['reads'][0].closed)
        self.assertFalse(observed['reads'][0].exhausted)
        self.assertEqual(observed['reads'][0].count, 0)
        self.assertIsNone(observed['reads'][0]._raw)
        self.assertEqual(observed['raw_reads'], [])
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertIn('共同时间基准', str(caught.exception.__cause__))
        owner = caught.exception.runner_cleanup_owner
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(owner._budget.ram_bytes, 0)

    def test_tampered_raw_file_blocks_completed_publish_but_analysis_remains_readable(self):
        """真实BLF字节篡改命中SHA核验，发布不完成且最高result可关并保分析行。

        参数: 无。返回: None。异常: 篡改被复制当成功、分析行丢失或RAM泄漏即失败。
        """
        work, plan, _ = self.fixture()
        result = self.run_plan(work, plan)
        record = self.records(result)[0]
        path, fact = self.frame_file(result._artifact_exports,record)
        payload = path.read_bytes()
        self.assertTrue(payload)
        # 同长改变最后字节，明确测试完整SHA而非仅字节数或BLF解析格式。
        path.write_bytes(payload[:-1] + bytes((payload[-1] ^ 1,)))
        destination = work / 'tampered-publish'
        with self.forbid_original_processes(), self.assertRaises(AnalysisError) as caught:
            result.write(destination)
        self.assertIsInstance(caught.exception.__cause__, ResultFormatError)
        self.assertIn('摘要', str(caught.exception.__cause__))
        self.assertIs(caught.exception.analysis_result_cleanup_owner, result)
        self.assertEqual(result.status, 'output_failed')
        self.assert_no_completed(work, destination)
        self.assertEqual(len(self.rows(result, 'events')), 2)
        self.assertEqual(len(self.rows(result, 'segments')), 2)
        caught.exception.analysis_result_cleanup_owner.close()
        self.assert_closed_budget(result)

    def test_real_copy_then_cancel_preserves_original_interrupt_and_result_owner(self):
        """实际复制/核验首BLF后取消保原KI及最高result，恢复后可向新目标重试。

        参数: 无。返回: None。异常: 注入未命中、原取消被包装、父责任丢失或账本漏即失败。
        """
        work, plan, _ = self.fixture()
        result = self.run_plan(work, plan)
        first = self.records(result)[0]
        original_file = ArtifactExportStore._file
        marker, copied = KeyboardInterrupt('真实raw copy完成后取消'), []

        def cancel_after_copy(owner, path, destination=None, expected=None, identity=None):
            """先执行原实际FD/复制/SHA再抛原KI。参数: 原调用参数。返回: 不返回。异常: 同一marker。"""
            original_file(owner, path, destination, expected, identity)
            self.assertIs(owner, result._artifact_exports)
            self.assertIsNotNone(destination)
            copied.append(destination)
            raise marker

        destination = work / 'cancelled-publish'
        with self.forbid_original_processes(), patch.object(ArtifactExportStore, '_file', new=cancel_after_copy), \
                self.assertRaises(KeyboardInterrupt) as caught:
            result.write(destination)
        self.assertIs(caught.exception, marker)
        self.assertEqual(len(copied), 1)
        self.assertTrue(copied[0].exists())
        self.assertEqual(sha256(copied[0].read_bytes()).hexdigest(), next(f for f in first['files'] if f['name']=='frames.blf')['sha256'])
        self.assertIs(marker.analysis_result_cleanup_owner, result)
        self.assertEqual(result.status, 'cancelled')
        self.assert_no_completed(work, destination)
        self.assertEqual(len(self.rows(result, 'events')), 2)
        self.assertEqual(len(self.rows(result, 'segments')), 2)
        # 取消只结束本次发布交易，封口源仍可读；不应close整仓导致既有write重试合同失效。
        self.assertEqual(result._artifact_exports.state, 'sealed')
        self.assertFalse(result._artifact_exports.closed)
        with self.forbid_original_processes():
            retry = result.write(work / 'cancelled-retry')
        completed = json.loads(retry.manifest_path.read_text(encoding='utf-8'))
        self.assertEqual((completed['status'], completed['exports']['record_count']), ('completed', 2))
        self.assertEqual(completed['error_counts']['output'], 1)
        self.assertEqual(sha256((export_root(retry) / first['directory'] / 'frames.blf').read_bytes()).hexdigest(), next(f for f in first['files'] if f['name']=='frames.blf')['sha256'])
        marker.analysis_result_cleanup_owner.close()
        self.assert_closed_budget(result)
