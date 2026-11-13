"""[home] 核固定按需解码、v3字段投影和真实关闭，显式all仍保完整解码检查。

内存旧链替身逐次记录next/parse，独立检查默认READY/批字节、固定集合与原帧保留、
未选原帧错误。真实BLF/DBC和spawn验证原时间、完整选中值、调用次数、预取与EOF。
独立账本故障覆盖策略预约及退款前后取消和持续Process.close失败，借款不得误还。
文件导入不打开来源；真实夹具只写新work目录，不改产品源码或RefProjects。
"""

from chronaxis.can_dependencies import runtime_dependency_versions
from functools import partial
from collections.abc import Mapping
import math
import os
from pathlib import Path
import platform
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis.legacy import batch_worker, worker
from chronaxis.legacy.batch_read import LegacyCANBatchRead
from chronaxis.legacy.batch_wire import BATCH_MAGIC, MAX_BATCH_BYTES, MAX_BATCH_ROWS, decode_batch
from chronaxis.legacy.records import (LegacyCANField, LegacyCANRequest, MAX_WIRE_BYTES, PROFILE_ID,
                                     decode_packet, encode_packet, field_to_dict)
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError
from chronaxis.sources.protocol import SourceReadError
from test_legacy_can_batch_worker_limits import ControlledOriginalChain, ScriptedBytesConnection, pull
from test_legacy_can_process import (ProcessFixture, ProcessFault, HAS_CAN, SYNTHETIC_DBC,
                                     BASE_TIMESTAMP, observed_real_worker)


class AlternatingChain(ControlledOriginalChain):
    """每条使用明确交替ID，允许在一次实际读取后注入原字段错误。"""

    def __init__(self, *, values=None, fault=None):
        """保存四帧输入。参数: 原解码值/字段故障名。返回: None。异常: 原构造错误。"""
        super().__init__(4, {'zero': -0.0, 'flag': False, '数值': 3} if values is None else values)
        self.fault = fault

    def __next__(self):
        """沿原替身next计数并设ID，首条未选帧可带坏DLC/时间。

        参数: 无。返回: 当条消息。异常: 真EOF或原读取错误；不调用parse。
        """
        message = super().__next__()
        message.arbitration_id = 257 if message.synthetic_sequence % 2 == 0 else 256
        if message.synthetic_sequence == 0:
            if self.fault == 'dlc':
                message.dlc = 65
            elif self.fault == 'time':
                message.timestamp = float('nan')
        return message


def observed_requested_worker(connection, *, ids):
    """让既有真实读取/解码追踪器调用同一个正式批worker，不改任何旧文件。

    参数: 实际spawn端点和固定ID，None代表原all。返回: 原返回。异常: 原worker错误。
    """
    with patch.object(worker, 'worker_main', partial(batch_worker.batch_worker_main, decode_frame_ids=ids)):
        observed_real_worker(connection)


def ready_for(read, *, scope='requested'):
    """建立独立READY测试值，不发送、不假称有真实进程。

    参数: 已构造read及预期策略。返回: 原生JSON树。异常: 原访问/分配错误。
    """
    from chronaxis.legacy.records import field_to_dict
    packet = {'op': 'ready', 'version': 1, 'profile': PROFILE_ID,
        'worker_pid': read._worker_pid,
        'fields': [{'locator': field_to_dict(value), 'unit': 'V'} for value in read._request.fields],
        'dependency_versions': runtime_dependency_versions()}
    if scope == 'requested':
        packet.update(version=3, decode_scope='requested', decode_frame_ids=list(read._decode_frame_ids),
                      decoded_values_policy='requested_fields-v1')
    return packet


class RequestedWorkerTests(unittest.TestCase):
    """实际执行生产worker循环，用明确替身观察逐帧调用和独立协议字节。"""

    def configure_db(self, chain, fields):
        """提供候选索引所需的合成DBC声明，解码值仍由原计数替身返回。

        参数: chain为旧链替身、fields为请求字段。返回: None。异常: 构造失败。
        声明中允许有本条未解出的信号，以继续验证缺失键不会被补造。
        """
        chain.db.messages = tuple(SimpleNamespace(frame_id=frame_id, length=8,
            is_extended_frame=False, is_fd=False,
            signals=tuple(SimpleNamespace(name=field.signal) for field in fields
                          if field.frame_id == frame_id))
            for frame_id in dict.fromkeys(field.frame_id for field in fields))

    def execute(self, *, ids=None, projection=(256,), values=None, fault=None, error=False,
                omit_scope=False, names=(), field_ids=(256,)):
        """执行一批四帧及真EOF，失败时仍核原生成器/连接关闭。

        参数: 固定ID、PULL投影、原值、故障、所需字段名和字段所在ID。
        返回: chain/connection。异常: 非预期退出或断言。
        """
        chain = AlternatingChain(values=values, fault=fault)
        connection = ScriptedBytesConnection(chain, [(pull(0,
            ids=None if projection is None else list(projection)), 0, 0)])
        fields = tuple(LegacyCANField(0, name, frame_id, False, False)
                       for frame_id in field_ids for name in names)
        request = LegacyCANRequest(Path('synthetic.blf'), Path('synthetic.dbc'), fields)
        self.configure_db(chain, fields)
        metadata_fields = [{'locator': field_to_dict(field), 'unit': None} for field in fields]
        processor = SimpleNamespace(parse_frame=chain.parse_frame,
            cantools=SimpleNamespace(database=SimpleNamespace()))
        with patch.object(worker, '_request', return_value=request), \
                patch.object(batch_worker, 'load_dbc_file', side_effect=lambda path,module: chain.load_file(path)), \
                patch.object(worker, '_load_can_runtime', return_value=(getattr(chain,'can',None),processor.cantools)), \
                patch.object(worker, '_iter_blf', side_effect=chain.iter_frames), \
                patch.object(batch_worker, '_parse_selected', side_effect=lambda db,frame,message,duplicates: processor.parse_frame(frame,db)), \
                patch.object(worker, '_field_metadata', return_value=metadata_fields), \
                patch.object(batch_worker.metadata, 'version', return_value='controlled'):
            kwargs = {} if omit_scope else {'decode_frame_ids': ids}
            if error:
                with self.assertRaises(SystemExit) as caught:
                    batch_worker.batch_worker_main(connection, **kwargs)
                self.assertEqual(caught.exception.code, 1)
            else:
                batch_worker.batch_worker_main(connection, **kwargs)
        self.assertEqual((chain.load_calls, chain.iter_calls, chain.close_calls), (1, 1, 1))
        self.assertTrue(connection.closed)
        return chain, connection

    def test_default_and_explicit_none_keep_v1_and_exact_bytes(self):
        """默认与显式None全解码协议逐字节相同。参数: 无。返回: None。异常: 断言。"""
        first, a = self.execute(omit_scope=True)
        second, b = self.execute(ids=None)
        self.assertEqual(a.sent, b.sent)
        self.assertEqual((first.next_calls, first.parse_calls), (5, 4))
        self.assertEqual((second.next_calls, second.parse_calls), (5, 4))
        header = decode_packet(a.sent[0][0])
        self.assertEqual(set(header), {'op', 'version', 'profile', 'worker_pid', 'fields',
                                     'dependency_versions'})
        self.assertEqual(header['version'], 1)

    def test_requested_reads_all_and_keeps_complete_selected_bytes(self):
        """全部目标字段均被请求时，原时间/原序和目标完整字节同all。参数: 无。返回: None。异常: 断言。"""
        _, baseline = self.execute()
        chain, selected = self.execute(ids=(256,), names=('zero', 'flag', '数值'))
        self.assertEqual((chain.next_calls, chain.parse_calls), (5, 2))
        self.assertEqual(chain.parsed_sequences, [1, 3])
        self.assertEqual(baseline.sent[1][0], selected.sent[1][0])
        ready = decode_packet(selected.sent[0][0])
        self.assertEqual((ready['version'], ready['decode_scope'], ready['decode_frame_ids']),
                         (3, 'requested', [256]))
        self.assertEqual(ready['decoded_values_policy'], 'requested_fields-v1')
        batch, eof = decode_batch(selected.sent[1][0], expected_start=0, row_limit=MAX_BATCH_ROWS,
                                  byte_limit=MAX_BATCH_BYTES, frame_ids=(256,))
        self.assertEqual(batch.timestamps, (0.0, 0.0, 0.0, 0.0))
        self.assertEqual([row.sequence for row in batch.records], [1, 3])
        self.assertTrue(eof)

    def test_fixed_scope_does_not_shrink_with_pull_projection(self):
        """PULL小投影不改变启动固定解码范围，空集合也保全时间。

        参数: 无。返回: None。异常: 调用范围/EOF断言。
        """
        for fixed, projection, expected in (((256, 257), (256,), 4), ((256,), (), 2), ((), (), 0)):
            with self.subTest(fixed=fixed, projection=projection):
                chain, connection = self.execute(ids=fixed, projection=projection,
                                                 names=('zero',), field_ids=fixed)
                self.assertEqual((chain.next_calls, chain.parse_calls), (5, expected))
                batch, eof = decode_batch(connection.sent[1][0], expected_start=0,
                    row_limit=MAX_BATCH_ROWS, byte_limit=MAX_BATCH_BYTES, frame_ids=projection)
                self.assertEqual(len(batch.timestamps), 4)
                self.assertTrue(eof)

    def test_raw_projection_can_retain_other_ids_without_expanding_decode(self):
        """PULL可保留全部原帧，但不会扩大解码集合。参数: 无。返回: None。异常: 断言。"""
        for projection in (None, (257,), (256, 257)):
            with self.subTest(projection=projection):
                chain, connection = self.execute(ids=(256,), projection=projection, names=('zero',))
                self.assertEqual((chain.next_calls, chain.parse_calls), (5, 2))
                batch, eof = decode_batch(connection.sent[1][0], expected_start=0,
                    row_limit=MAX_BATCH_ROWS, byte_limit=MAX_BATCH_BYTES, frame_ids=projection)
                self.assertTrue(eof)
                self.assertEqual(len(batch.timestamps), 4)
                expected = [index for index in range(4)
                            if projection is None or (257 if index % 2 == 0 else 256) in projection]
                self.assertEqual([row.sequence for row in batch.records], expected)
                for row in batch.records:
                    self.assertEqual(dict(row.values), {'zero': -0.0} if row.sequence % 2 else {})

    def test_unselected_raw_errors_remain_but_no_decoded_values_exist(self):
        """按需仍拒绝未选坏原帧；无解码值时不伪称核过其值。参数: 无。返回: None。异常: 断言。"""
        for fault in ('dlc', 'time'):
            chain, connection = self.execute(ids=(256,), fault=fault, error=True)
            self.assertEqual((chain.next_calls, chain.parse_calls), (1, 0))
            self.assertFalse(any(item[0].startswith(BATCH_MAGIC) for item in connection.sent))
        chain, _ = self.execute(ids=(), projection=(), values={'bad': 'not-numeric'})
        self.assertEqual(chain.parse_calls, 0)
        chain, _ = self.execute(ids=None, projection=(), values={'bad': 'not-numeric'}, error=True)
        self.assertEqual((chain.next_calls, chain.parse_calls), (1, 1))
        chain, _ = self.execute(ids=(256,), values={'bad': 'not-numeric'}, names=('bad',), error=True)
        self.assertEqual((chain.next_calls, chain.parse_calls), (2, 1))

    def test_requested_omits_bad_unused_values_and_keeps_absent_keys_absent(self):
        """无关坏值不进入校验，所需缺失键不补零；常量触发无需遍历返回值。

        参数: 无。返回: None。异常: 多读无关值、补键或所需值变化时断言失败。
        """
        values = {'zero': -0.0, 'flag': False, 'unused': 'x' * (MAX_WIRE_BYTES + 1),
                  'surrogate\ud800': object()}
        chain, connection = self.execute(ids=(256,), names=('zero', 'flag', 'absent'), values=values)
        self.assertEqual(chain.parse_calls, 2)
        batch, _ = decode_batch(connection.sent[1][0], expected_start=0,
            row_limit=MAX_BATCH_ROWS, byte_limit=MAX_BATCH_BYTES, frame_ids=(256,))
        for row in batch.records:
            self.assertEqual(set(row.values), {'zero', 'flag'})
            self.assertEqual(row.values['zero'].hex(), '-0x0.0p+0')
            self.assertIs(row.values['flag'], False)
        # 没有字段需求时，即使原返回对象不能作为Mapping，也不处理其内容。
        constant_chain, constant = self.execute(ids=(256,), values=object())
        self.assertEqual((constant_chain.next_calls, constant_chain.parse_calls), (5, 0))
        empty, _ = decode_batch(constant.sent[1][0], expected_start=0,
            row_limit=MAX_BATCH_ROWS, byte_limit=MAX_BATCH_BYTES, frame_ids=(256,))
        self.assertEqual([dict(row.values) for row in empty.records], [{}, {}])
        self.execute(values=values, error=True)

    def test_required_diagnostics_unicode_and_item_size_still_use_original_model(self):
        """所需诊断值、Unicode与64KiB仍按原模型和编码器处理。

        参数: 无。返回: None。异常: 字节、诊断类型或超限拒绝断言失败。
        """
        values = {'数值😀': float('nan'), '正': float('inf'), '负': float('-inf'), 'big': 2 ** 100}
        _, baseline = self.execute(values=values)
        _, requested = self.execute(ids=(256,), values=values, names=tuple(values))
        self.assertEqual(baseline.sent[1][0], requested.sent[1][0])
        batch, _ = decode_batch(requested.sent[1][0], expected_start=0,
            row_limit=MAX_BATCH_ROWS, byte_limit=MAX_BATCH_BYTES, frame_ids=(256,))
        self.assertTrue(math.isnan(batch.records[0].values['数值😀']))
        self.assertEqual(batch.records[0].values['big'], 2 ** 100)
        # INIT本身合法的小字段集，在合成低记录上限下仍必须于模型预检拒绝。
        with patch('chronaxis.legacy.records.MAX_WIRE_BYTES', 1024):
            _, failed = self.execute(ids=(256,), values={'needed': 2 ** 5000},
                                     names=('needed',), error=True)
        failure = decode_packet(failed.sent[-1][0])
        self.assertEqual(failure['op'], 'error')
        self.assertFalse(any(item[0].startswith(BATCH_MAGIC) for item in failed.sent))

    def test_requested_omits_unused_long_field_across_4096_frames(self):
        """实际worker跨5000合成帧仅保所需字段，包在4096边界连续且没有多解码。

        参数: 无。返回: None。异常: 裁剪、逐帧顺序、真实EOF或关闭计数不符时断言失败。
        只替换旧输入链，不打开真实BLF；完整spawn与大记录预算由其他专项负责。
        """
        class SparseChain(ControlledOriginalChain):
            """每160条有一条目标，足以在同一正常包中覆盖4096原帧。"""

            def __next__(self):
                """保原计数并设当前ID。参数: 无。返回: 消息。异常: 原StopIteration。"""
                message = super().__next__()
                message.arbitration_id = 256 if message.synthetic_sequence % 160 == 0 else 257
                return message

        chain = SparseChain(5000, {'needed': 3, 'Unused' + 'x' * 60000: 4})
        connection = ScriptedBytesConnection(chain, [
            (pull(0, ids=[256]), 0, 0),
            (pull(4096, ids=[256]), 4096, 26)])
        field = LegacyCANField(0, 'needed', 256, False, False)
        request = LegacyCANRequest(Path('synthetic.blf'), Path('synthetic.dbc'), (field,))
        self.configure_db(chain, (field,))
        processor = SimpleNamespace(parse_frame=chain.parse_frame,
            cantools=SimpleNamespace(database=SimpleNamespace()))
        with patch.object(worker, '_request', return_value=request), \
                patch.object(batch_worker, 'load_dbc_file', side_effect=lambda path,module: chain.load_file(path)), \
                patch.object(worker, '_load_can_runtime', return_value=(getattr(chain,'can',None),processor.cantools)), \
                patch.object(worker, '_iter_blf', side_effect=chain.iter_frames), \
                patch.object(batch_worker, '_parse_selected', side_effect=lambda db,frame,message,duplicates: processor.parse_frame(frame,db)), \
                patch.object(worker, '_field_metadata',
                    return_value=[{'locator': field_to_dict(field), 'unit': None}]), \
                patch.object(batch_worker.metadata, 'version', return_value='controlled'):
            batch_worker.batch_worker_main(connection, decode_frame_ids=(256,))
        batches, next_start, sequences = [], 0, []
        for payload, _, _ in connection.sent:
            if not payload.startswith(BATCH_MAGIC):
                continue
            batch, eof = decode_batch(payload, expected_start=next_start, row_limit=MAX_BATCH_ROWS,
                byte_limit=MAX_BATCH_BYTES, frame_ids=(256,))
            batches.append((batch.start_sequence, len(batch.timestamps), eof))
            next_start += len(batch.timestamps)
            for row in batch.records:
                self.assertEqual(dict(row.values), {'needed': 3})
                sequences.append(row.sequence)
        self.assertEqual(batches, [(0, 4096, False), (4096, 904, True)])
        self.assertEqual(sequences, list(range(0, 5000, 160)))
        self.assertEqual((chain.next_calls, chain.parse_calls, chain.close_calls), (5001, 32, 1))
        self.assertTrue(connection.closed)
        self.assertFalse(connection.commands)

    def test_projection_reads_only_required_keys_and_clears_cancelled_references(self):
        """投影不枚举Mapping，所需键取消原样传播且清本层traceback。

        参数: 无。返回: None。异常: 意外遍历/错误替换/引用残留时断言失败。
        """
        class RequiredOnly(Mapping):
            """只允许访问wanted，其他入口一律失败，便于观察真正访问范围。"""

            def __init__(self, failure=None):
                """保存可选失败。参数: 原异常或None。返回: None。异常: 无。"""
                self.failure = failure
                self.calls = []

            def __getitem__(self, name):
                """记录需求键访问。参数: 字段名。返回: -0.0。异常: 注入错误或KeyError。"""
                self.calls.append(name)
                if name == 'absent':
                    raise KeyError(name)
                if name != 'wanted':
                    raise AssertionError('读取了无关字段')
                if self.failure is not None:
                    raise self.failure
                return -0.0

            def __iter__(self):
                """禁止枚举。参数: 无。返回: 无。异常: AssertionError。"""
                raise AssertionError('不应遍历原values')

            def __len__(self):
                """禁止计数。参数: 无。返回: 无。异常: AssertionError。"""
                raise AssertionError('不应检查原values大小')

        source = RequiredOnly()
        result = batch_worker._project_values(source, {'wanted': None, 'absent': None})
        self.assertEqual(source.calls, ['wanted', 'absent'])
        self.assertEqual(result['wanted'].hex(), '-0x0.0p+0')
        self.assertNotIn('absent', result)
        for failure in (KeyboardInterrupt('projection cancel'), MemoryError('projection allocation')):
            source = RequiredOnly(failure)
            try:
                batch_worker._project_values(source, {'wanted': None})
            except BaseException as caught:
                self.assertIs(caught, failure)
                trace, found = caught.__traceback__, False
                while trace is not None:
                    if trace.tb_frame.f_code is batch_worker._project_values.__code__:
                        found = True
                        for name in ('values', 'names', 'projected', 'name', 'value'):
                            self.assertIsNone(trace.tb_frame.f_locals[name])
                    trace = trace.tb_next
                self.assertTrue(found)
            else:
                self.fail('投影必须传播原取消')


class RequestedReadBoundaryTests(ProcessFixture):
    """以真实预算/owner核构造与READY边界，无来源时不启动进程。"""

    def make_requested(self, **kwargs):
        """构造并登记按需read。参数: 可覆盖构造项。返回: read。异常: 原构造错误。"""
        options = dict(frame_ids=(256,), decode_scope='requested', decode_frame_ids=(256,))
        options.update(kwargs)
        fields = options.pop('fields', (self.field,))
        read = LegacyCANBatchRead(LegacyCANRequest(self.input_path, self.dbc_path, fields),
                                 self.budget, **options)
        self.reads.append(read)
        return read

    def test_all_fee_target_and_constructor_policy_validation(self):
        """all不新增费用/partial，非法策略拒绝且归还自有费。参数: 无。返回: None。异常: 断言。"""
        original = self.make_requested(decode_scope='all', decode_frame_ids=None)
        self.assertIs(original._worker_target, batch_worker.batch_worker_main)
        self.assertEqual((original._fixed_cost, original._decode_policy_cost), (1048576, 0))
        original.close()
        cases = [dict(decode_scope='unknown'), dict(decode_scope=True),
                 dict(decode_scope='all'), dict(decode_frame_ids=None), dict(decode_frame_ids=[]),
                 dict(decode_frame_ids=(True,)), dict(decode_frame_ids=(256, 256)),
                 dict(decode_frame_ids=(-1,)), dict(decode_frame_ids=(0x20000000,)),
                 dict(decode_frame_ids=())]
        for options in cases:
            with self.subTest(options=options):
                with self.assertRaises(SourceReadError):
                    self.make_requested(**options)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)
        empty = self.make_requested(fields=(), frame_ids=(), decode_frame_ids=())
        self.assertEqual(empty._decode_policy_cost, 8192)
        empty.close()

    def test_strict_ready_rejects_wrong_policy_ids_types_and_shared_metadata(self):
        """v3每项都核，含bool/int、字段定位、依赖与旧v1/v2降级。

        参数: 无。返回: None。异常: 协议断言或非预期校验错误。
        """
        read = self.make_requested()
        read._worker_pid = os.getpid()  # 独立头部校验，没有实际spawn，不当进程事实。
        read._check_ready(ready_for(read))
        mutations = [dict(version=1), dict(version=2), dict(version=True), dict(decode_scope='all'),
                     dict(decode_frame_ids=[True]), dict(decode_frame_ids=[257]),
                     dict(decode_frame_ids=(256,)), dict(decode_frame_ids=[256, 256]),
                     dict(extra=1), dict(worker_pid=True), dict(profile='wrong'),
                     dict(fields=[]), dict(dependency_versions={}), dict(vendor_sha256={}),
                     dict(decoded_values_policy='full'), dict(decoded_values_policy=True)]
        for changes in mutations:
            packet = ready_for(read)
            packet.update(changes)
            with self.subTest(changes=changes), self.assertRaises(SourceReadError):
                read._check_ready(packet)
        with self.assertRaises(SourceReadError):
            read._check_ready(ready_for(read, scope='all'))
        legacy_v2 = ready_for(read)
        legacy_v2['version'] = 2
        del legacy_v2['decoded_values_policy']
        with self.assertRaises(SourceReadError):
            read._check_ready(legacy_v2)
        all_read = self.make_requested(decode_scope='all', decode_frame_ids=None)
        all_read._worker_pid = read._worker_pid
        with self.assertRaises(SourceReadError):
            all_read._check_ready(ready_for(read))

    def test_policy_reserve_before_after_cancel_preserves_same_owner(self):
        """策略预约前后取消与持续退款失败保同owner及借款。

        参数: 无。返回: None。异常: 取消身份、实际费用或恢复断言。
        """
        request = LegacyCANRequest(self.input_path, self.dbc_path, (self.field,))
        amount = 8192 + 256 + 1024
        reserve = self.budget.reserve_ram
        for after in (False, True):
            primary = KeyboardInterrupt('decode policy reserve')
            secondary = OSError('policy release blocked')

            def fault_reserve(value):
                """只针对策略一笔预约注入。参数: 金额。返回: None。异常: 同primary。"""
                if value != amount:
                    return reserve(value)
                if after:
                    reserve(value)
                raise primary

            with patch.object(self.budget, 'reserve_ram', new=fault_reserve), \
                    patch.object(self.budget, 'release_ram', side_effect=secondary):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    LegacyCANBatchRead(request, self.budget, frame_ids=(256,),
                        decode_scope='requested', decode_frame_ids=(256,))
                self.assertIs(caught.exception, primary)
                owner = primary.can_process_read_cleanup_owner
                self.reads.append(owner)
                self.assertEqual(owner._decode_policy_cost, amount if after else 0)
                self.assertIsNone(owner._process)
                self.assertEqual(self.budget.ram_bytes, self.borrowed + owner._held_cost)
                with self.assertRaises(OSError):
                    owner.close()
            owner.close()
            self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_policy_low_budget_and_release_after_cancel_do_not_double_refund(self):
        """策略独立费用不足不启动；退款后取消不重复抵销。参数: 无。返回: None。异常: 断言。"""
        budget = ResourceBudget(1048576 + 8192 + 255)
        with self.assertRaises(BudgetExceededError):
            LegacyCANBatchRead(LegacyCANRequest(self.input_path, self.dbc_path, ()), budget,
                frame_ids=(256,), decode_scope='requested', decode_frame_ids=(256,))
        self.assertEqual(budget.ram_bytes, 0)
        read = self.make_requested()
        target = read._decode_policy_cost
        original, primary, hits = self.budget.release_ram, KeyboardInterrupt('policy released'), []

        def release(amount):
            """策略真实退款后仅取消一次。参数: 金额。返回: 原值。异常: 同primary。"""
            value = original(amount)
            if amount == target and not hits:
                hits.append(amount)
                raise primary
            return value

        with patch.object(self.budget, 'release_ram', new=release):
            with self.assertRaises(KeyboardInterrupt) as caught:
                read.close()
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.can_process_read_cleanup_owner, read)
            self.assertEqual(read._decode_policy_cost, 0)
        read.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_invalid_batch_never_reaches_private_packet_consumer(self):
        """整包解码失败时不通知观察者，关闭时清掉回调。

        参数: 无。返回: None。异常: 意外调用、吞包错误或费用残留时断言失败。
        """
        calls = []
        read = self.make_requested()

        def observe(owner, payload, batch):
            """记录不应发生的调用。参数: 借入三对象。返回: None。异常: 无。"""
            calls.append(owner)

        class BrokenPacketConnection:
            """提供含正确magic但被截断的单包，不创建真实管道。"""

            def recv_bytes(self, maximum):
                """交付坏包。参数: 许可字节。返回: bytes。异常: 无。"""
                return BATCH_MAGIC

        read._validated_packet_consumer = observe
        # 只为直接调用接包边界准备一笔真实自有费；没有伪造started或已关闭进程。
        from chronaxis.results.budget import _reserve_owned_ram
        _reserve_owned_ram(read, 64, '_current_cost')
        with patch.object(read, '_connection', BrokenPacketConnection()):
            with self.assertRaises(ValueError):
                read._receive_reply()
        self.assertEqual(calls, [])
        read.close()
        self.assertIsNone(read._validated_packet_consumer)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)


@unittest.skipUnless(HAS_CAN, '实际CAN依赖未全部安装')
class RequestedRealReadTests(ProcessFixture):
    """现场真实四帧BLF，保全部观察时间，按需只解码Demo两帧，验证实际进程资源。"""

    def setUp(self):
        """生成唯一新夹具目录中的DBC/BLF。参数: 无。返回: None。异常: 原写文件错误。"""
        super().setUp()
        import can
        self.dbc_path.write_text(SYNTHETIC_DBC, encoding='utf-8')
        writer = can.BLFWriter(str(self.input_path))
        try:
            for index in range(4):
                writer.on_message_received(can.Message(timestamp=BASE_TIMESTAMP + index * .125,
                    arbitration_id=256 if index % 2 else 257, is_extended_id=False,
                    channel=0, data=[index]))
        finally:
            writer.stop()

    def actual_read(self, *, ids=(256,), prefetch=False, observed=True, target=None):
        """建立真实来源read并登记关闭责任。参数: 范围/预取/trace。返回: read。异常: 原错误。"""
        fields = () if ids == () else (self.field,)
        read = LegacyCANBatchRead(LegacyCANRequest(self.input_path, self.dbc_path, fields),
            self.budget, frame_ids=(256,) if ids is None else ids, batch_rows=2,
            prefetch=prefetch, decode_scope='all' if ids is None else 'requested', decode_frame_ids=ids,
            _worker_target=target or (partial(observed_requested_worker, ids=ids) if observed else None))
        self.reads.append(read)
        return read

    def test_actual_calls_complete_bytes_prefetch_and_empty_scope(self):
        """默认/按需/空范围均真EOF，预取不改成功序号和值。

        参数: 无。返回: None。异常: 真实旧调用、报文内容或费用断言。
        """
        baseline = None
        trace_path = self.input_path.with_name('process-trace.jsonl')
        for ids, prefetch, expected in ((None, False, 4), ((256,), True, 2), ((), False, 0)):
            with self.subTest(ids=ids, prefetch=prefetch):
                before = len(self.read_trace()) if trace_path.exists() else 0
                read = self.actual_read(ids=ids, prefetch=prefetch)
                read.start()
                self.assertEqual(read.metadata['version'], 1 if ids is None else 3)
                records, times = [], []
                for batch in read:
                    records.extend(batch.records)
                    times.extend(batch.timestamps)
                calls = self.read_trace()[before:]
                self.assertEqual(sum(item['rule'] == 'next' for item in calls), 5)
                self.assertEqual(sum(item['rule'] == 'parse' for item in calls), expected)
                self.assertEqual(sum(item['rule'] == 'load_file' for item in calls), 1)
                self.assertEqual(len(times), 4)
                if ids is None:
                    baseline = (records, times)
                elif ids:
                    self.assertEqual((records, times), baseline)
                else:
                    self.assertEqual(records, [])
                    self.assertEqual(times, baseline[1])
                self.assertTrue(read.finished and read.closed)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)
        # 实际默认target也须传固定策略，不能只靠显式观测wrapper通过。
        direct = self.actual_read(observed=False)
        self.assertEqual(sum(len(batch.records) for batch in direct), 2)
        self.assertTrue(direct.finished)

    def test_raw_all_keeps_other_frames_without_decoding_their_values(self):
        """实际spawn保全部原帧并仅解码所需ID，严格v3直到真EOF。

        参数: 无。返回: None。异常: 原帧、调用范围、来源事实或清理断言失败。
        """
        read = LegacyCANBatchRead(LegacyCANRequest(self.input_path, self.dbc_path, (self.field,)),
            self.budget, frame_ids=None, batch_rows=2, prefetch=True,
            decode_scope='requested', decode_frame_ids=(256,),
            _worker_target=partial(observed_requested_worker, ids=(256,)))
        self.reads.append(read)
        rows = [row for batch in read for row in batch.records]
        self.assertEqual([row.sequence for row in rows], [0, 1, 2, 3])
        self.assertEqual([dict(row.values) for row in rows],
                         [{}, {'Sample': 1}, {}, {'Sample': 5}])
        calls = self.read_trace()
        self.assertEqual(sum(item['rule'] == 'next' for item in calls), 5)
        self.assertEqual(sum(item['rule'] == 'parse' for item in calls), 2)
        self.assertTrue(read.closed and read.finished)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_packet_consumer_observes_original_payload_once_in_order(self):
        """观察者只借严格核过的原包，按批原序调用并在实际关闭后解除。

        参数: 无。返回: None。异常: 重编码/重复调用/借用错误或清理断言失败。
        """
        calls = []
        read = self.actual_read(prefetch=True, observed=False)

        def observe(owner, payload, batch):
            """仅保留小计数不保活借入大包。参数: 同read/bytes/batch。返回: None。异常: 断言。"""
            self.assertIs(owner, read)
            self.assertIs(payload, read._pending_reply)
            verified, eof = decode_batch(payload, expected_start=batch.start_sequence,
                row_limit=2, byte_limit=read._batch_limit, frame_ids=(256,))
            self.assertEqual(batch, verified)
            calls.append((batch.start_sequence, len(batch.timestamps), eof))

        read._validated_packet_consumer = observe
        delivered = [(batch.start_sequence, len(batch.timestamps)) for batch in read]
        self.assertEqual(delivered, [(0, 2), (2, 2), (4, 0)])
        self.assertEqual(calls, [(0, 2, False), (2, 2, False), (4, 0, True)])
        self.assertIsNone(read._validated_packet_consumer)
        self.assertTrue(read.finished and read.closed)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_packet_consumer_cancel_poison_read_and_preserve_recovery_owner(self):
        """观察失败不交付该批，沿原错误包装规则保留恢复责任。

        参数: 无。返回: None。异常: KI身份、MemoryError原因、恢复owner或费用不符时断言失败。
        """
        for failure in (KeyboardInterrupt('packet observation'), MemoryError('packet observation')):
            with self.subTest(kind=type(failure).__name__):
                read, calls = self.actual_read(observed=False), []
                read.start()
                close_error = OSError('actual process close blocked')
                proxy = ProcessFault(read._process, 'close', close_error, False)
                read._process = proxy

                def observe(owner, payload, batch):
                    """在严格包后取消。参数: 当前借用对象。返回: 无。异常: 原failure。"""
                    try:
                        calls.append(batch.start_sequence)
                        raise failure
                    finally:
                        owner = payload = batch = None

                read._validated_packet_consumer = observe
                try:
                    expected = (SourceReadError if isinstance(failure, MemoryError)
                                else type(failure))
                    with self.assertRaises(expected) as caught:
                        next(read)
                    if isinstance(failure, MemoryError):
                        self.assertIs(caught.exception.__cause__, failure)
                    else:
                        self.assertIs(caught.exception, failure)
                    self.assertIs(caught.exception.can_process_read_cleanup_owner, read)
                    self.assertEqual(calls, [0])
                    self.assertEqual(read.counters['items_returned'], 0)
                    self.assertFalse(read.finished or read.closed)
                    with self.assertRaises(OSError):
                        read.close()
                finally:
                    read._process = proxy.real
                    read.close()
                self.assertIsNone(read._validated_packet_consumer)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_override_worker_must_acknowledge_requested_policy(self):
        """显式故障target回v1也被拒绝，INIT不扩大读取许可。参数: 无。返回: None。异常: 断言。"""
        read = self.actual_read(target=partial(observed_requested_worker, ids=None))
        with self.assertRaises(SourceReadError):
            read.start()
        self.assertFalse(read.finished)
        self.assertTrue(read.closed)
        self.assertEqual(read.counters['pulls_issued'], 0)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_close_failure_keeps_policy_fee_until_real_process_closed(self):
        """真实进程close持续失败时保策略费和同owner，恢复后才退款。

        参数: 无。返回: None。异常: 实际资源/费用或异常身份断言。
        """
        read = self.actual_read(prefetch=True, observed=False)
        next(read)
        cost, held = read._decode_policy_cost, read._held_cost
        primary = OSError('actual process close blocked')
        proxy = ProcessFault(read._process, 'close', primary, False)
        read._process = proxy
        try:
            for _ in range(2):
                with self.assertRaises(OSError) as caught:
                    read.close()
                self.assertIs(caught.exception, primary)
                self.assertIs(primary.can_process_read_cleanup_owner, read)
                self.assertEqual((read._decode_policy_cost, read._held_cost), (cost, held))
                self.assertIs(read._process, proxy)
        finally:
            read._process = proxy.real
        read.close()
        self.assertEqual(read._decode_policy_cost, 0)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)


if __name__ == '__main__':
    unittest.main()
