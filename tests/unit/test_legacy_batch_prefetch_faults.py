"""验证单批预取失败时的真实交付、远端错误和资源恢复责任。

测试使用受控子进程与真实Pipe，正常传输一批后才注入下一次请求的故障。
费用检查保留另一使用者的真实借款；关闭失败不得提前释放两批费用，恢复
只能使用原owner。此文件不测性能，也不以受控消息代替旧CAN调用顺序验收。
所有输入与输出均由既有ProcessFixture放在新项目work目录。
"""

from functools import partial
from dataclasses import replace
import os
import platform
from unittest.mock import patch

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter, CANObservationRead
from chronaxis.legacy.batch_read import LegacyCANBatchRead
from chronaxis.legacy.batch_wire import encode_batch
from chronaxis.legacy.process_read import RemoteLegacyError
from chronaxis.legacy.records import (MAX_WIRE_BYTES, PROFILE_ID, LegacyCANRequest, LegacyDecodedFrame,
    decode_packet, decoded_to_dict, encode_packet)
from chronaxis.legacy.worker import VENDOR_SHA256
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.can_spec import LegacyCANSpec
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.protocol import SourceReadError
from test_legacy_can_batch import BatchConnectionFault, sample
from test_legacy_can_process import ProcessFixture, ProcessFault


def fault_batch_worker(connection, *, mode='normal'):
    """通过真实连接返回两批，或让第二批发生明确协议/退出故障。

    参数: connection为spawn传入的实际端点，mode选择受控场景。
    返回: 正常返回None。异常: bad_exit以7退出，其他未预期错误直接传播。
    """
    try:
        initial = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
        ready = {'op': 'ready', 'version': 1, 'profile': PROFILE_ID,
            'worker_pid': os.getpid(), 'fields': [{'locator': item, 'unit': 'V'} for item in initial['fields']],
            'dependency_versions': {'python': platform.python_version(), 'python-can': '4.6.1',
                'cantools': '39.4.3', 'natsort': '8.4.0'}, 'vendor_sha256': VENDOR_SHA256}
        connection.send_bytes(encode_packet(ready))
        for index in range(2):
            packet = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
            if packet['op'] != 'pull_batch' or packet['request_id'] != index:
                raise AssertionError('故障夹具需要按0、1顺序授权两批')
            # 第一批始终成功且没有EOF，让下一次许可真正进入预取路径。
            if index == 1 and mode == 'disconnect':
                return
            if index == 1 and mode in ('remote_error', 'wrong_id', 'bad_facts'):
                reply = {'op': 'error', 'request_id': index, 'phase': 'parse',
                    'error': {'module': 'builtins', 'type': 'ValueError',
                        'message': 'prefetched parse failure', 'traceback': 'controlled traceback',
                        'notes': ['controlled note']}}
                if mode == 'wrong_id':
                    reply['request_id'] = 0
                elif mode == 'bad_facts':
                    reply['error']['notes'] = [3]
                connection.send_bytes(encode_packet(reply))
                return
            data = encode_batch(index, [float(index)],
                [encode_packet(decoded_to_dict(sample(index)))], index == 1, packet['bytes'])
            connection.send_bytes(data)
            if index == 1 and mode == 'bad_exit':
                raise SystemExit(7)
    except (EOFError, BrokenPipeError, ConnectionResetError):
        # 父提前取消会真实关管道；这里结束夹具，不伪造任何EOF回应。
        return
    finally:
        connection.close()


def same_time_batch_worker(connection):
    """通过真实Pipe生成2048条同刻样本，专门积累跨批去重状态。

    参数: 真实连接。返回: 真正交付全部样本后None。异常: 非预期协议/编码错误。
    来源与DBC均由本函数控制，不读取夹具路径中的占位文件，不声称执行旧CAN链。
    """
    try:
        initial = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
        connection.send_bytes(encode_packet({'op': 'ready', 'version': 1, 'profile': PROFILE_ID,
            'worker_pid': os.getpid(), 'fields': [{'locator': item, 'unit': 'V'} for item in initial['fields']],
            'dependency_versions': {'python': platform.python_version(), 'python-can': '4.6.1',
                'cantools': '39.4.3', 'natsort': '8.4.0'}, 'vendor_sha256': VENDOR_SHA256}))
        position, total = 0, 2048
        while True:
            packet = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
            if packet['op'] != 'pull_batch' or packet['request_id'] != position:
                raise AssertionError('同刻夹具需要连续的原序许可')
            end = min(total, position + packet['rows'])
            records = [encode_packet(decoded_to_dict(LegacyDecodedFrame(index,
                replace(sample(index).frame, timestamp=0.0), {'Sample': index % 10})))
                for index in range(position, end)]
            connection.send_bytes(encode_batch(position, [0.0] * (end - position), records,
                end == total, packet['bytes']))
            position = end
            if position == total:
                return
    except (EOFError, BrokenPipeError, ConnectionResetError):
        return
    finally:
        connection.close()


class SecondSendFault(BatchConnectionFault):
    """只在第二次实际send前后取消，保留第一次同步请求及原真实端点。"""

    def send_bytes(self, *args, **kwargs):
        """在预取发送前或发送后抛同一对象。

        参数: 原send参数。返回: 实际send结果。异常: 第二次取消或原管道错误。
        """
        self.calls += 1
        if self.calls == 2 and not self.after:
            raise self.error
        result = self.real.send_bytes(*args, **kwargs)
        if self.calls == 2:
            raise self.error
        return result


class LegacyBatchPrefetchFaultTests(ProcessFixture):
    """独立覆盖预取故障，不重复主专项中的正常旧链和小预算同步回退。"""

    def prefetch_read(self, *, mode='normal'):
        """建立并登记真实预取owner。

        参数: mode为第二批场景。返回: 尚未启动read。异常: 原构造错误。
        """
        read = LegacyCANBatchRead(
            LegacyCANRequest(self.input_path, self.dbc_path, (self.field,)), self.budget,
            frame_ids=(256,), batch_rows=2, prefetch=True,
            _worker_target=partial(fault_batch_worker, mode=mode))
        self.reads.append(read)
        return read

    def assert_released(self, read):
        """同时检查实际资源、费用及失败状态，而非只核账本总额。

        参数: 已关闭read。返回: None。异常: 测试断言失败。
        """
        self.assertTrue(read.closed)
        self.assertFalse(read.finished)
        self.assertIsNone(read._process)
        self.assertIsNone(read._connection)
        self.assertIsNone(read._child_connection)
        self.assertIsNone(read._current)
        self.assertIsNone(read._prefetch_packet)
        self.assertFalse(read._waiting)
        self.assertEqual((read._current_cost, read._prefetch_cost, read._held_cost), (0, 0, 0))
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_process_close_failure_keeps_both_fees_and_same_recovery_owner(self):
        """实际join/close前后失败均保两槽，恢复不重复释放借款。

        参数: 无。返回: None。异常: 断言或未预期实际资源错误。
        """
        for operation, after in (('join', False), ('close', False), ('close', True)):
            with self.subTest(operation=operation, after=after):
                read = self.prefetch_read()
                next(read)
                costs = (read._current_cost, read._prefetch_cost, read._held_cost)
                self.assertGreater(costs[0], 0)
                self.assertGreater(costs[1], 0)
                before = self.budget.ram_bytes
                failure = OSError('persistent actual process ' + operation)
                proxy = ProcessFault(read._process, operation, failure, after)
                read._process = proxy
                try:
                    for _ in range(2):
                        with self.assertRaises(OSError) as caught:
                            read.close()
                        self.assertIs(caught.exception, failure)
                        self.assertIs(failure.can_process_read_cleanup_owner, read)
                        self.assertIs(read._process, proxy)
                        self.assertFalse(read.closed)
                        self.assertEqual((read._current_cost, read._prefetch_cost, read._held_cost), costs)
                        self.assertEqual(self.budget.ram_bytes, before)
                finally:
                    proxy.error = None
                    read.close()
                self.assert_released(read)

    def test_constructor_reserve_cancel_uses_initialized_child_slots(self):
        """基类构造预约前后取消时，动态清理钩子可安全访问子类预取槽。

        参数: 无。返回: None。异常: 断言或未预期构造错误。
        """
        for after in (False, True):
            with self.subTest(after=after):
                # 测试保留尚未返回的实际对象，方便同时核关闭标志和零费用。
                read = LegacyCANBatchRead.__new__(LegacyCANBatchRead)
                self.reads.append(read)
                reserve = self.budget.reserve_ram
                failure = KeyboardInterrupt('batch constructor reservation')

                def cancel_reserve(amount):
                    """在首笔固定费更新前后取消。参数: amount。返回: 不成功。异常: 原KI。"""
                    if after:
                        reserve(amount)
                    raise failure

                with patch.object(self.budget, 'reserve_ram', cancel_reserve):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        read.__init__(LegacyCANRequest(self.input_path, self.dbc_path, (self.field,)),
                            self.budget, prefetch=True, _worker_target=fault_batch_worker)
                self.assertIs(caught.exception, failure)
                self.assert_released(read)

    def test_reserve_cancel_before_or_after_payment_never_delivers_current_batch(self):
        """预取预约前后取消不重发，真实关闭后才归还实际已付金额。

        参数: 无。返回: None。异常: 断言或未预期原错误。
        """
        for after in (False, True):
            with self.subTest(after=after):
                read = self.prefetch_read().start()
                reserve, release = self.budget.reserve_ram, self.budget.release_ram
                failure = KeyboardInterrupt('prefetch reserve cancellation')
                hits, delivered = [], []

                def cancel_reserve(amount):
                    """仅当前批已解码后的下一笔预约取消。

                    参数: 实际费用。返回: None。异常: 同一取消对象或原预算错误。
                    """
                    if read._current is not None:
                        hits.append(amount)
                        if after:
                            reserve(amount)
                        raise failure
                    reserve(amount)

                def observe_release(amount):
                    """预约取消收尾必须先关闭真实IPC和子进程。

                    参数: 退费金额。返回: 原返回。异常: 断言或原退费错误。
                    """
                    if hits:
                        self.assertIsNone(read._process)
                        self.assertIsNone(read._connection)
                    return release(amount)

                with patch.object(self.budget, 'reserve_ram', cancel_reserve), \
                        patch.object(self.budget, 'release_ram', observe_release):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        delivered.append(next(read))
                self.assertIs(caught.exception, failure)
                self.assertEqual(delivered, [])
                self.assertEqual(len(hits), 1)
                self.assertEqual(read.counters['pulls_issued'], 1)
                self.assertEqual(read.counters['items_accepted'], 1)
                self.assertEqual(read.counters['items_returned'], 0)
                self.assertEqual(read.counters['records_returned'], 0)
                self.assert_released(read)

    def test_prefetch_send_cancel_before_or_after_send_keeps_current_undelivered(self):
        """下一批发包前后取消都不重试，也不交付先前已解码当前批。

        参数: 无。返回: None。异常: 断言或未预期管道错误。
        """
        for after in (False, True):
            with self.subTest(after=after):
                read = self.prefetch_read().start()
                failure = KeyboardInterrupt('prefetch send cancellation')
                proxy = SecondSendFault(read._connection, operation='send_bytes', error=failure, after=after)
                read._connection = proxy
                delivered = []
                with self.assertRaises(KeyboardInterrupt) as caught:
                    delivered.append(next(read))
                self.assertIs(caught.exception, failure)
                self.assertEqual(delivered, [])
                self.assertEqual(proxy.calls, 2)
                self.assertTrue(proxy.closed)
                self.assertEqual(read.counters['pulls_issued'], 2)
                self.assertEqual(read.counters['items_accepted'], 1)
                self.assertEqual(read.counters['items_returned'], 0)
                self.assertEqual(read.counters['records_returned'], 0)
                self.assert_released(read)

    def test_prefetched_receive_cancel_reclaims_transferred_slot(self):
        """下一次接包前后取消时，已转移到current的费用仍完整回收。

        参数: 无。返回: None。异常: 断言或未预期实际接收错误。
        """
        for after in (False, True):
            with self.subTest(after=after):
                read = self.prefetch_read()
                first = next(read)
                self.assertEqual(first.start_sequence, 0)
                self.assertGreater(read._prefetch_cost, 0)
                failure = KeyboardInterrupt('prefetched receive cancellation')
                read._connection = BatchConnectionFault(read._connection,
                    operation='recv_bytes', error=failure, after=after)
                with self.assertRaises(KeyboardInterrupt) as caught:
                    next(read)
                self.assertIs(caught.exception, failure)
                self.assertEqual(read.counters['items_accepted'], 1)
                self.assert_released(read)

    def test_release_failure_after_real_close_keeps_exact_unpaid_slots(self):
        """实际资源已关闭而退费持续失败时，同一owner保费用供后续恢复。

        参数: 无。返回: None。异常: 断言或未预期关闭错误。
        """
        read = self.prefetch_read()
        next(read)
        costs = (read._current_cost, read._prefetch_cost, read._held_cost)
        before = self.budget.ram_bytes
        failure = OSError('persistent budget release')

        def refuse_release(amount):
            """在实际账本更新前拒绝退费。参数: amount。返回: 不成功。异常: 同一错误。"""
            raise failure

        with patch.object(self.budget, 'release_ram', refuse_release):
            for _ in range(2):
                with self.assertRaises(OSError) as caught:
                    read.close()
                self.assertIs(caught.exception, failure)
                self.assertIs(failure.can_process_read_cleanup_owner, read)
                self.assertIsNone(read._process)
                self.assertIsNone(read._connection)
                self.assertFalse(read.closed)
                self.assertEqual((read._current_cost, read._prefetch_cost, read._held_cost), costs)
                self.assertEqual(self.budget.ram_bytes, before)
        read.close()
        self.assert_released(read)

    def test_prefetched_remote_error_keeps_strict_facts_and_request_identity(self):
        """正确远端错误保cause，错序号和坏事实被协议层拒绝。

        参数: 无。返回: None。异常: 断言或未预期子进程错误。
        """
        for mode in ('remote_error', 'wrong_id', 'bad_facts'):
            with self.subTest(mode=mode):
                read = self.prefetch_read(mode=mode)
                next(read)
                with self.assertRaises(SourceReadError) as caught:
                    next(read)
                cause = caught.exception.__cause__
                if mode == 'remote_error':
                    self.assertIs(type(cause), RemoteLegacyError)
                    self.assertEqual(cause.request_id, 1)
                    self.assertEqual(cause.phase, 'parse')
                    self.assertIn('prefetched parse failure', str(cause))
                else:
                    self.assertNotIsInstance(cause, RemoteLegacyError)
                self.assert_released(read)

    def test_prefetched_disconnect_is_not_successful_eof(self):
        """未收到第二批完整回应时，子正常退出也不能补造EOF。

        参数: 无。返回: None。异常: 断言或未预期协议错误。
        """
        read = self.prefetch_read(mode='disconnect')
        next(read)
        with self.assertRaises(SourceReadError):
            next(read)
        self.assertEqual(read.counters['items_accepted'], 1)
        self.assert_released(read)

    def test_prefetched_eof_data_precedes_nonzero_exit_rejection(self):
        """EOF数据可先交付，下一次next必须拒绝子进程非零退出。

        参数: 无。返回: None。异常: 断言或未预期实际关闭错误。
        """
        read = self.prefetch_read(mode='bad_exit')
        self.assertEqual(next(read).start_sequence, 0)
        self.assertEqual(next(read).start_sequence, 1)
        self.assertFalse(read.finished)
        self.assertEqual(read.counters['pulls_issued'], 2)
        with self.assertRaises(SourceReadError):
            next(read)
        self.assertEqual(read._exit_code, 7)
        self.assert_released(read)

    def test_same_time_pending_growth_preserves_synchronous_budget_success(self):
        """同64MiB下同步和预取都完成2048个同刻样本，不靠关预取或加预算通过。

        参数: 无。返回: None。异常: 预算回归、输出差异或清理断言失败。
        旧固定headroom曾让同步成功而预取在约千条后失败；本例保每输出批1条、
        每原批32条，真实触发pending跨批增长，逐项比较全部样本而非只比数量。
        """
        # 只为本例建立相同64MiB账本，原借款仍逐笔归还并重新登记。
        self.budget.release_ram(self.borrowed)
        self.budget = ResourceBudget(64 * 1024 ** 2)
        self.budget.reserve_ram(self.borrowed)
        self.input_path.write_bytes(b'controlled source, not a real BLF')
        self.dbc_path.write_text('controlled metadata, not a real DBC', encoding='utf-8')
        definition = SignalDefinition('a', 'bus', self.field.key,
            SignalDType.FLOAT64, 'V', 1000000000, input_unit='V')
        spec = LegacyCANSpec('bus', self.input_path, self.dbc_path, 0,
            TimebaseSpec('clock', TimeType.RELATIVE, 'controlled'), decode_scope='all')
        original_accept = CANObservationRead._accept
        outputs = []
        for prefetch in (False, True):
            with self.subTest(prefetch=prefetch):
                adapter = BudgetedLegacyCANSourceAdapter(self.budget, spec, 'session', (definition,),
                    work_dir=self.root / ('signal-adapter-' + str(prefetch)), batch_read=True,
                    retain_raw_frames=False, capture_message_updates=False, message_frame_ids=(256,))
                self.reads.append(adapter)
                read = adapter.iter_batches(ReadRequest('session', ('a',), 0, 1000000000, 1))
                self.reads.append(read)
                rows, prefetch_costs = [], []

                def construct(*args, **kwargs):
                    """仅选开关、32原帧上限及受控子进程，不改产品计费。

                    参数: 原构造参数。返回: 实际批owner。异常: 原构造错误。
                    """
                    kwargs.update(prefetch=prefetch, batch_rows=32, _worker_target=same_time_batch_worker)
                    return LegacyCANBatchRead(*args, **kwargs)

                def observe_accept(owner, batch):
                    """检查真实预取仍被使用，再执行原接收校验。

                    参数: 原owner/批。返回: 原批。异常: 原验证或预算错误。
                    """
                    prefetch_costs.append(owner._process._prefetch_cost)
                    return original_accept(owner, batch)

                try:
                    with patch('chronaxis.legacy.batch_read.LegacyCANBatchRead', construct), \
                            patch.object(CANObservationRead, '_accept', observe_accept):
                        for batch in read:
                            if 'a' in batch.series:
                                column = batch.series['a']
                                rows.extend((int(sequence), int(time), float(value), bool(valid))
                                    for sequence, time, value, valid in zip(column.sequence,
                                        column.time_ns, column.values, column.valid))
                    self.assertTrue(read.finished)
                    self.assertEqual(read.observation.row_count, 2048)
                    self.assertEqual((read.observation.first_ns, read.observation.last_ns), (0, 0))
                    self.assertEqual(any(prefetch_costs), prefetch)
                    self.assertEqual(rows, [(index, 0, float(index % 10), True) for index in range(2048)])
                    outputs.append(rows)
                finally:
                    read.close()
                    adapter.close()
                self.assertEqual(self.budget.ram_bytes, self.borrowed)
        self.assertEqual(outputs[0], outputs[1])
