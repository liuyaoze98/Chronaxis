"""验证独立原writer进程的逻辑帧对照、单PUT许可及真实资源恢复。

标准库协议例使用真正spawn的明确受控worker，核严格READY/ACK/FINISH与异常，
不冒充旧BLF正确性。真实库例把同组原始帧交给生产LegacyCANProcessWrite，并在
另一真实spawn中直接调用直接BLFWriter作独立逻辑对照；以公开BLFReader核字段、
同刻顺序及严格小量时间容差，不以文件字节相同作承诺。另用原消息构造/写/stop
透传记录证明每PUT仅一次原调用，没有FINISH隐含帧或父重新读取原输入。

故障只包实际Connection/Process或既有预算方法，保原父KI/SystemExit及借款，
持续三次失败后恢复同一最高owner；没有手造半初始化对象或伪退出状态。
全部产物保留work/m2-can-tests独占目录，device_label=home。未安装真实可选CAN
依赖时仅真实库例跳过；生产导入不启动子进程，本文件只在根统一正式轮执行。
"""

from chronaxis.can_dependencies import runtime_dependency_versions
from configuration_fixtures import current_fixture

# spawn目标必须位于模块顶层；纯协议例不加载CAN库或写出器。
from dataclasses import replace
from functools import partial
import importlib.util
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
from threading import Event
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.legacy import export_write as module
from chronaxis.legacy.records import (LegacyRawFrame, MAX_WIRE_BYTES, PROFILE_ID,
    decode_packet, encode_packet, frame_from_dict, frame_to_dict)
from chronaxis.results import BudgetExceededError, ResourceBudget, ResultClosedError


WORK = Path(__file__).resolve().parents[2] / 'work' / 'm2-can-tests'
HAS_CAN = all(importlib.util.find_spec(name) is not None for name in ('can', 'cantools', 'natsort'))
BASE = 1700000000.0
FRAME = LegacyRawFrame(BASE, 0x123, False, False, False, 0, 2, b'\x01\x02', False, True, False, False)


def controlled_write_worker(connection, *, mode):
    """由真正spawn子返回声明的受控writer协议，不调用原CAN实现。

    参数: connection为真实端点；mode为明确故障分支名。返回: 正常协议完成时None。
    异常: 非预期控制字段错误传播；exit_after_done故意非零退出，stubborn等待真实终止。
    副作用: 仅在测试新根创建独立文本产物，不能作为BLF正确性依据。
    """
    try:
        initial = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
        if set(initial) != {'op', 'version', 'profile', 'path'} or initial['op'] != 'init':
            raise AssertionError('受控writer缺少唯一INIT')
        Path(initial['path']).write_bytes(b'controlled writer protocol fixture\n')
        ready = {'op': 'ready', 'version': 1, 'profile': PROFILE_ID, 'worker_pid': os.getpid(),
            'dependency_versions': runtime_dependency_versions()}
        if mode == 'ready_pid':
            ready['worker_pid'] += 1
        elif mode == 'ready_bool_version':
            ready['version'] = True
        elif mode == 'ready_hash':
            ready['unexpected_vendor'] = 'unsupported'
        elif mode == 'ready_dependency':
            ready['dependency_versions']['python-can'] = '0.0.0'
        connection.send_bytes(encode_packet(ready))
        count = 0
        while True:
            try:
                packet = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
            except EOFError:
                if mode == 'stubborn':
                    Event().wait()
                return
            if packet['op'] == 'finish':
                if set(packet) != {'op', 'frame_count'} or packet['frame_count'] != count:
                    raise AssertionError('受控writer没有收到同次完整帧数')
                connection.send_bytes(encode_packet({'op': 'finished', 'frame_count': count}))
                if mode == 'exit_after_done':
                    raise SystemExit(2)
                return
            if (set(packet) != {'op', 'request_id', 'frame'} or packet['op'] != 'put'
                    or type(packet['request_id']) is not int or packet['request_id'] != count):
                raise AssertionError('受控writer收到重复或叠加PUT')
            frame_from_dict(packet['frame'])
            if mode == 'bad_json':
                connection.send_bytes(b'{invalid')
            elif mode == 'overlong':
                connection.send_bytes(b'x' * (MAX_WIRE_BYTES + 1))
            elif mode == 'no_ack':
                return
            elif mode == 'remote_error':
                connection.send_bytes(encode_packet({'op': 'error', 'request_id': count, 'phase': 'write',
                    'error': {'module': 'builtins', 'type': 'OSError', 'message': 'controlled partial output failure',
                        'traceback': 'controlled write location', 'notes': ['finite remote fact']}}))
            else:
                connection.send_bytes(encode_packet({'op': 'ack', 'request_id':
                    False if mode == 'bool_id' else count + 1 if mode == 'wrong_id' else count,
                    'frame_count': True if mode == 'bool_count' else count + 1}))
            count += 1
    finally:
        connection.close()


def direct_old_writer(path, frames):
    """在独立child直接执行直接BLFWriter/on_message_received/stop作逻辑基线。

    参数: path为测试新BLF文本路径；frames为有限LegacyRawFrame tuple。
    返回: None。异常: 库Message/写出/stop错误，进程非零退出。
    副作用: 不经过生产writer协议，也不调用新_message helper；只在新工作根写基线。
    """
    import can
    writer=can.BLFWriter(path)
    try:
        for frame in frames:
            # 独立逐字段构造，能发现新worker漏传/改传原公开字段，不镜像其封装函数。
            message = can.Message(timestamp=frame.timestamp, arbitration_id=frame.arbitration_id,
                is_extended_id=frame.is_extended_id, is_remote_frame=frame.is_remote_frame,
                is_error_frame=frame.is_error_frame, channel=frame.channel, dlc=frame.dlc,
                data=frame.data, is_fd=frame.is_fd, is_rx=frame.is_rx,
                bitrate_switch=frame.bitrate_switch, error_state_indicator=frame.error_state_indicator)
            writer.on_message_received(message)
    finally:
        writer.stop()


def traced_old_writer(connection, *, fail_write_at=None, fail_stop=False):
    """透传真实原writer并仅记录调用事实，生产协议仍完整运行。

    参数: connection为真正spawn端点；fail_write_at可选从1起实际写入后故障位置；
        fail_stop为实际stop后故障开关。返回: 原export_worker.worker_main返回值。
    异常: 原worker错误或明确注入；trace失败也明确非零，不作为成功基线。
    副作用: 新根写小量trace，不改产品磁盘文件、实际写入参数或次数。
    """
    from chronaxis.legacy import export_worker
    initial = connection.recv_bytes(MAX_WIRE_BYTES)
    packet = decode_packet(initial)
    trace_path = Path(packet['path']).with_suffix('.trace.jsonl')
    import can
    original_build=can.BLFWriter

    def trace(event,**facts):
        """记录第三方实际动作，不替代生产writer的所有权。"""
        with trace_path.open('a',encoding='utf8') as handle:
            handle.write(json.dumps(current_fixture({'rule':event,**facts}),allow_nan=False)+'\n')

    class WriterTrace:
        """代理同一个真实python-can writer，保留每次写入及关闭行为。"""
        def __init__(self,actual):self.actual,self.count=actual,0
        def on_message_received(self,message):
            trace('on_message_received',timestamp=message.timestamp,
                arbitration_id=message.arbitration_id,data_hex=bytes(message.data).hex())
            result=self.actual.on_message_received(message);self.count+=1
            if fail_write_at is not None and self.count==fail_write_at:
                raise OSError('actual old writer failed after frame')
            return result
        def stop(self):
            trace('stop');result=self.actual.stop()
            if fail_stop:raise RuntimeError('actual old writer failed after stop')
            return result

    def build(file,*args,**kwargs):
        """观察同一独占文件句柄，真实BLF编码及最终头仍由库执行。"""
        trace('build_writer',path=str(file.name),format='blf')
        return WriterTrace(original_build(file,*args,**kwargs))

    class InitialReplay:
        """仅回放已取INIT一次，其余能力全部转给同一实际端点。"""

        def __init__(self):
            """保存初包。参数: 无。返回: 新代理。异常: 无。"""
            self.initial = initial

        def recv_bytes(self, *args, **kwargs):
            """先回放再真实接收。参数: 原参数。返回: bytes。异常: 原端点错误。"""
            if self.initial is not None:
                value, self.initial = self.initial, None
                return value
            return connection.recv_bytes(*args, **kwargs)

        def __getattr__(self, name):
            """透传真实连接能力。参数: name。返回: 原属性。异常: 原属性错误。"""
            return getattr(connection, name)

    with patch.object(can,'BLFWriter',new=build):
        return export_worker.worker_main(InitialReplay())


class ActualFault:
    """在实际Connection/Process动作前后注入，不伪造closed/pid/exitcode。"""

    def __init__(self, actual, operation, error, after=False):
        """保存真实对象与故障。参数: actual/operation/error/after。返回: 代理。异常: 无。"""
        self.actual, self.operation, self.error, self.after = actual, operation, error, after
        self.calls = 0

    def __getattr__(self, name):
        """仅目标动作包故障，其余原样透传。参数: name。返回: 原属性或透传函数。异常: 原属性错误。"""
        value = getattr(self.actual, name)
        if name != self.operation:
            return value

        def invoke(*args, **kwargs):
            """对真实动作前后注入。参数: 原args/kwargs。返回: 原值。异常: 同一原注入或实际错误。"""
            self.calls += 1
            if self.error is not None and not self.after:
                raise self.error
            result = value(*args, **kwargs)
            if self.error is not None:
                raise self.error
            return result

        return invoke


class WriteFixture(unittest.TestCase):
    """每例新工作根和真实借款，清理只经过实际writer自身close。"""

    def setUp(self):
        """建立独占根/预算。参数: 无。返回: None。异常: 原目录或预算错误。"""
        self.root = WORK / ('legacy-can-export-home-' + uuid4().hex)
        self.root.mkdir(parents=True)
        self.budget, self.borrowed, self.writers = ResourceBudget(256 * 1024 ** 2), 8192, []
        self.budget.reserve_ram(self.borrowed)

    def tearDown(self):
        """关闭实际owner并核借款。参数: 无。返回: None。异常: 原关闭或费用断言失败。"""
        for writer in reversed(self.writers):
            writer.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        self.budget.release_ram(self.borrowed)
        self.assertEqual(self.budget.ram_bytes, 0)

    def make_writer(self, name=None):
        """创建并登记未启动实际writer。参数: name可选新文件名。返回: 原owner。异常: 原构造错误。"""
        writer = module.LegacyCANProcessWrite(self.budget, self.root / (name or (uuid4().hex + '.blf')))
        self.writers.append(writer)
        return writer

    def start_controlled(self, mode='normal'):
        """只替换真实spawn目标，生产parent不变。参数: mode。返回: 已启动owner。异常: 原启动/协议错误。"""
        writer = self.make_writer()
        with patch.object(module, 'worker_main', new=partial(controlled_write_worker, mode=mode)):
            writer.start()
        return writer


class WriteStaticTests(WriteFixture):
    """静态路径、构造及预留交易不依赖可选CAN库。"""

    def test_constructor_is_static_and_only_new_paths(self):
        """构造不spawn/不创建产物，已有目标拒绝；客户同名目录可用且原字节保持。
        参数: 无。返回: None。异常: 原接口或路径/副作用断言失败。
        """
        with patch.object(module.multiprocessing, 'get_context', side_effect=AssertionError('constructor spawned')):
            writer = self.make_writer('static.blf')
        self.assertIsNone(writer.worker_pid)
        self.assertFalse(writer.output_path.exists())
        self.assertFalse(writer.finished or writer.closed)
        writer.close()
        existing = self.root / 'existing.blf'
        existing.write_bytes(b'caller content')
        with self.assertRaises(FileExistsError):
            module.LegacyCANProcessWrite(self.budget, existing)
        customer=self.root/'RefProjects'
        customer.mkdir()
        sentinel=customer/'user.txt'
        sentinel.write_bytes(b'keep')
        allowed=module.LegacyCANProcessWrite(self.budget, customer/'new.blf')
        self.writers.append(allowed)
        self.assertFalse(allowed.output_path.exists())
        allowed.close()
        self.assertEqual(existing.read_bytes(), b'caller content')
        self.assertEqual(sentinel.read_bytes(),b'keep')
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_constructor_after_reserve_cancel_has_highest_actual_owner(self):
        """固定费先更新后取消，持续三次释放失败保真实未返回owner及借款。
        参数: 无。返回: None。异常: 原注入或最高责任/恢复断言失败。
        """
        primary, cleanup = KeyboardInterrupt('fixed reserved then cancel'), RuntimeError('release persists')
        reserve = self.budget.reserve_ram

        def reserved(amount):
            """实际付款后取消。参数: amount。返回: 无。异常: primary或原预算错误。"""
            reserve(amount)
            raise primary

        with patch.object(self.budget, 'reserve_ram', new=reserved), \
                patch.object(self.budget, 'release_ram', side_effect=cleanup):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.make_writer()
            self.assertIs(caught.exception, primary)
            owner = primary.can_process_write_cleanup_owner
            self.writers.append(owner)
            self.assertIs(type(owner), module.LegacyCANProcessWrite)
            self.assertIsNone(owner.worker_pid)
            self.assertEqual(self.budget.ram_bytes, self.borrowed + owner._held_cost)
            for _ in range(3):
                with self.assertRaises(RuntimeError) as held:
                    owner.close()
                self.assertIs(held.exception, cleanup)
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_initial_spool_quota_rejects_before_spawn(self):
        """空BLF仍先付65536，配额小于此值时无spawn或输出，不偷增预算。
        参数: 无。返回: None。异常: 原预算错误或无副作用断言失败。
        """
        self.budget.spool_quota_bytes = 65535
        writer = self.make_writer()
        with patch.object(module.multiprocessing, 'get_context', side_effect=AssertionError('quota spawned')):
            with self.assertRaises(BudgetExceededError):
                writer.start()
        self.assertEqual(writer.spool_bytes, 0)
        self.assertFalse(writer.output_path.exists())
        self.assertTrue(writer.closed and writer.failed)

    def test_target_created_after_constructor_remains_unchanged(self):
        """构造后出现的调用方文件在start再校验时拒绝，不改原字节或启动进程。
        参数: 无。返回: None。异常: 原路径错误或覆盖/启动/费用断言失败。
        """
        writer = self.make_writer('appeared.blf')
        writer.output_path.write_bytes(b'new caller content')
        with patch.object(module.multiprocessing, 'get_context', side_effect=AssertionError('collision spawned')):
            with self.assertRaises(module.LegacyCANWriteError) as caught:
                writer.start()
        self.assertIsInstance(caught.exception.__cause__, FileExistsError)
        self.assertEqual(writer.output_path.read_bytes(), b'new caller content')
        self.assertEqual(writer.spool_bytes, 0)
        self.assertTrue(writer.closed and not writer.finished)

    def test_spool_reserve_after_cancel_keeps_direct_charge(self):
        """本次磁盘预留执行后取消仍归本writer，close不倒扣累计磁盘。
        参数: 无。返回: None。异常: 原取消或真实预留/借款断言失败。
        """
        writer, primary = self.make_writer(), SystemExit('spool reserved cancellation')
        reserve = self.budget.reserve_spool

        def reserved(amount):
            """真实磁盘记账后取消。参数: amount。返回: 无。异常: 原primary或配额错误。"""
            reserve(amount)
            raise primary

        with patch.object(self.budget, 'reserve_spool', new=reserved):
            with self.assertRaises(SystemExit) as caught:
                writer.start()
        self.assertIs(caught.exception, primary)
        self.assertEqual(writer.spool_bytes, 65536)
        self.assertEqual(self.budget.spool_bytes, 65536)
        self.assertTrue(writer.closed and not writer.finished)
        self.assertFalse(writer.output_path.exists())


class WriteProtocolTests(WriteFixture):
    """明确受控子协议仅验证parent门槛，不作为原BLF行为证据。"""

    def test_single_put_ack_and_true_finish_are_separate(self):
        """READY无帧许可；每PUT一ACK，真正正常退出及费用归零后才finished。
        参数: 无。返回: None。异常: 原进程或计数/完成/幂等断言失败。
        """
        writer = self.start_controlled()
        self.assertEqual(writer.counters, {'puts_issued': 0, 'acks_received': 0, 'frames_written': 0})
        self.assertEqual(writer.metadata['worker_pid'], writer.worker_pid)
        self.assertIs(writer.start(), writer)
        for _ in range(2):
            writer.write(FRAME)
        self.assertFalse(writer.finished or writer.closed)
        self.assertEqual(writer.counters, {'puts_issued': 2, 'acks_received': 2, 'frames_written': 2})
        writer.finish()
        self.assertTrue(writer.finished and writer.closed)
        self.assertIsNone(writer._connection)
        self.assertIsNone(writer._process)
        self.assertEqual(writer._exit_code, 0)
        self.assertEqual(writer.spool_bytes, 65536 + 2 * 4096)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        self.assertIs(writer.finish(), writer)
        with self.assertRaises(ResultClosedError):
            writer.write(FRAME)

    def test_bad_ready_strict_types_pid_dependencies_and_hash(self):
        """真子进程的坏PID/bool版本/依赖/额外字段均拒，不能凭READY字样声称初始化。
        参数: 无。返回: None。异常: 原进程或严格身份/关闭断言失败。
        """
        for mode in ('ready_pid', 'ready_bool_version', 'ready_hash', 'ready_dependency'):
            with self.subTest(mode=mode):
                with self.assertRaises(module.LegacyCANWriteError):
                    self.start_controlled(mode)
                writer = self.writers[-1]
                self.assertFalse(writer.finished)
                self.assertTrue(writer.closed and writer.failed)
                self.assertEqual(writer.counters['puts_issued'], 0)

    def test_invalid_ack_and_wire_never_confirm_frame(self):
        """坏JSON/超长/错误序号/bool计数/缺ACK不能增加父确认帧数。
        参数: 无。返回: None。异常: 原进程或计数/诊断断言失败。
        """
        for mode in ('bad_json', 'overlong', 'wrong_id', 'bool_id', 'bool_count', 'no_ack'):
            with self.subTest(mode=mode):
                writer = self.start_controlled(mode)
                with self.assertRaises(module.LegacyCANWriteError):
                    writer.write(FRAME)
                self.assertEqual(writer.counters, {'puts_issued': 1, 'acks_received': 0, 'frames_written': 0})
                self.assertTrue(writer.failed and writer.closed)
                self.assertFalse(writer.finished)

    def test_remote_partial_failure_preserves_explicit_facts(self):
        """远端写入错误保原有限事实cause，不能伪称跨进程同一异常或完整导出。
        参数: 无。返回: None。异常: 原协议错误或远端cause/失败产物断言失败。
        """
        writer = self.start_controlled('remote_error')
        with self.assertRaises(module.LegacyCANWriteError) as caught:
            writer.write(FRAME)
        self.assertIsInstance(caught.exception.__cause__, module.RemoteLegacyError)
        self.assertEqual(caught.exception.__cause__.facts['message'], 'controlled partial output failure')
        self.assertEqual(caught.exception.__cause__.phase, 'write')
        self.assertTrue(writer.output_path.exists())
        self.assertFalse(writer.finished)

    def test_finish_candidate_requires_real_zero_exit(self):
        """完成候选后子进程非零退出仍失败，不只检查收到FINISHED。
        参数: 无。返回: None。异常: 原进程或候选/实际退出断言失败。
        """
        writer = self.start_controlled('exit_after_done')
        writer.write(FRAME)
        with self.assertRaises(module.LegacyCANWriteError):
            writer.finish()
        self.assertTrue(writer._finish_received)
        self.assertEqual(writer._exit_code, 2)
        self.assertTrue(writer.closed and writer.failed)
        self.assertFalse(writer.finished)

    def test_each_frame_spool_quota_precedes_put(self):
        """第二帧无4096配额时拒绝，不发第二PUT或把首帧记作完整文件。
        参数: 无。返回: None。异常: 原配额错误或许可前缀/预留断言失败。
        """
        self.budget.spool_quota_bytes = 65536 + 4096
        writer = self.start_controlled()
        writer.write(FRAME)
        with self.assertRaises(BudgetExceededError):
            writer.write(FRAME)
        self.assertEqual(writer.counters, {'puts_issued': 1, 'acks_received': 1, 'frames_written': 1})
        self.assertEqual(writer.spool_bytes, 65536 + 4096)
        self.assertFalse(writer.finished)

    def test_frame_ram_limit_refuses_before_put_without_rescan(self):
        """真实READY后剩余RAM不足本帧预约即拒，不授权PUT或用磁盘预留代替RAM。
        参数: 无。返回: None。异常: 原预算或零PUT/费用归属断言失败。
        """
        writer = self.start_controlled()
        self.budget.memory_budget_bytes = self.budget.ram_bytes + 4259840 - 1
        with self.assertRaises(BudgetExceededError):
            writer.write(FRAME)
        self.assertEqual(writer.counters, {'puts_issued': 0, 'acks_received': 0, 'frames_written': 0})
        self.assertEqual(writer.spool_bytes, 65536)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        self.assertTrue(writer.closed and not writer.finished)


class WriteRecoveryTests(WriteFixture):
    """只在实际已启动子进程/管道及逐笔预算上注入，另一writer保持独立。"""

    def test_connection_close_before_after_persistent_retry_isolated(self):
        """真实端点close前/后持续三次取消，恢复同一owner且不影响另一个writer。
        参数: 无。返回: None。异常: 原进程或实际端点/原取消/借款断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                writer, other = self.start_controlled(), self.start_controlled()
                primary = KeyboardInterrupt('actual pipe close cancellation')
                fault = ActualFault(writer._connection, 'close', primary, after)
                writer._connection = fault
                try:
                    # after分支真实端点已关，后两次close应继续恢复而非重关已撤槽。
                    attempts = 1 if after else 3
                    for _ in range(attempts):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            writer.close()
                        self.assertIs(caught.exception, primary)
                        self.assertIs(primary.can_process_write_cleanup_owner, writer)
                        self.assertFalse(writer.closed or writer.finished)
                    self.assertEqual(fault.actual.closed, after)
                    other.write(FRAME)
                    self.assertEqual(other.counters['frames_written'], 1)
                finally:
                    fault.error = None
                    writer.close()
                self.assertTrue(writer.closed and writer._process_stopped)
                self.assertIsNone(writer._connection)
                self.assertEqual(self.budget.ram_bytes, self.borrowed + other._held_cost)
                other.finish()

    def test_real_process_join_and_close_persist_then_recover(self):
        """实际Process.join/close前三次失败，恢复只关本进程且不伪造退出证明。
        参数: 无。返回: None。异常: 原进程或实际owner/同对象恢复断言失败。
        """
        for operation, after in (('join', False), ('close', False), ('close', True)):
            with self.subTest(operation=operation, after=after):
                writer = self.start_controlled('stubborn')
                primary = RuntimeError('persistent actual Process.' + operation)
                fault = ActualFault(writer._process, operation, primary, after)
                writer._process = fault
                try:
                    for _ in range(3):
                        with self.assertRaises(RuntimeError) as caught:
                            writer.close()
                        self.assertIs(caught.exception, primary)
                        self.assertIs(primary.can_process_write_cleanup_owner, writer)
                        self.assertIs(writer._process, fault)
                        self.assertFalse(writer.closed or writer.finished)
                    if operation == 'close':
                        self.assertTrue(writer._process_stopped)
                finally:
                    fault.error = None
                    writer.close()
                self.assertTrue(writer.closed)
                self.assertIsNone(writer._process)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_parent_receive_cancel_not_replaced_by_cleanup_failure(self):
        """PUT发出后父KI保原对象，持续join副错只附note并保最高writer。
        参数: 无。返回: None。异常: 原进程或父取消/原前缀/实际恢复断言失败。
        """
        writer = self.start_controlled()
        primary, cleanup = KeyboardInterrupt('PUT receive cancelled'), RuntimeError('join remains blocked')
        connection = ActualFault(writer._connection, 'recv_bytes', primary)
        process = ActualFault(writer._process, 'join', cleanup)
        writer._connection, writer._process = connection, process
        try:
            with self.assertRaises(KeyboardInterrupt) as caught:
                writer.write(FRAME)
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.can_process_write_cleanup_owner, writer)
            self.assertTrue(any('RuntimeError' in note for note in primary.__notes__))
            self.assertEqual(writer.counters, {'puts_issued': 1, 'acks_received': 0, 'frames_written': 0})
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    writer.close()
        finally:
            connection.error = process.error = None
            writer.close()
        self.assertTrue(writer.closed and not writer.finished)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_ram_release_before_after_cancel_is_owned_not_borrowed(self):
        """固定费释放前三次失败及释放后一次KI，重试不二次抵销调用方8192借款。
        参数: 无。返回: None。异常: 原预算或自有槽/借款/原取消断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                writer = self.make_writer()
                primary, release = KeyboardInterrupt('owned fixed fee cancellation'), self.budget.release_ram

                def cancelled(amount):
                    """只执行指定前后动作。参数: amount。返回: 无。异常: primary或原预算错误。"""
                    if after:
                        release(amount)
                    raise primary

                with patch.object(self.budget, 'release_ram', new=cancelled):
                    for _ in range(1 if after else 3):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            writer.close()
                        self.assertIs(caught.exception, primary)
                        self.assertEqual(self.budget.ram_bytes, self.borrowed + writer._held_cost)
                    self.assertEqual(writer._fixed_cost == 0, after)
                writer.close()
                writer.close()
                self.assertEqual(self.budget.ram_bytes, self.borrowed)


@unittest.skipUnless(HAS_CAN, '真实CAN依赖未安装，不能伪造原writer行为')
class WriteRealLibraryTests(WriteFixture):
    """现场原库写出/回读与隔离旧基线比较，不能由受控协议替代。"""

    def read_fields(self, path):
        """显式关闭真正BLFReader并取本小夹具字段。参数: path。返回: dict tuple。异常: 原读取/关闭错误。"""
        import can
        reader = can.BLFReader(str(path))
        try:
            return tuple({'timestamp': msg.timestamp, 'arbitration_id': msg.arbitration_id,
                'is_extended_id': msg.is_extended_id, 'is_remote_frame': msg.is_remote_frame,
                'is_error_frame': msg.is_error_frame, 'channel': msg.channel, 'dlc': msg.dlc,
                'data': bytes(msg.data), 'is_fd': msg.is_fd, 'is_rx': msg.is_rx,
                'bitrate_switch': msg.bitrate_switch, 'error_state_indicator': msg.error_state_indicator}
                for msg in reader)
        finally:
            reader.stop()

    def test_real_original_logic_fields_same_time_and_old_baseline(self):
        """经典/扩展/FD原公开字段与独立python-can参考一致，同刻未知ID原序保留且时间误差严格受限。
        参数: 无。返回: None。异常: 原库/进程或手算字段/时间/原对照断言失败。
        """
        frames = (FRAME, replace(FRAME, timestamp=BASE + .125, arbitration_id=0x1ABCDE,
                is_extended_id=True, data=b'\x10\x20', is_rx=False),
            replace(FRAME, timestamp=BASE + .125, arbitration_id=0x456, is_fd=True, dlc=12,
                data=bytes(range(12)), bitrate_switch=True, error_state_indicator=True),
            replace(FRAME, timestamp=BASE + .25, arbitration_id=0x321, data=b'\x07\x08'))
        writer = self.make_writer('production.blf').start()
        ready = writer.metadata
        self.assertEqual(ready['worker_pid'], writer.worker_pid)
        self.assertNotIn('vendor_sha256', ready)
        for frame in frames:
            writer.write(frame)
        writer.finish()
        # 独立python-can参考写入位于另一个真实进程，避免父sys.modules污染或调用被测worker作参考。
        reference = self.root / 'direct-old.blf'
        process = multiprocessing.get_context('spawn').Process(target=direct_old_writer,
            args=(str(reference), frames))
        try:
            process.start()
            process.join(timeout=15)
            self.assertIsNotNone(process.exitcode, '原基线必须真实退出')
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.pid is not None and process.exitcode is None:
                process.kill()
                process.join(timeout=5)
            process.close()
        actual, baseline = self.read_fields(writer.output_path), self.read_fields(reference)
        self.assertEqual(actual, baseline)
        self.assertEqual(len(actual), 4)
        self.assertEqual(tuple(row['arbitration_id'] for row in actual), (0x123, 0x1ABCDE, 0x456, 0x321))
        for row, original in zip(actual, frames):
            expected = frame_to_dict(original)
            expected['data'] = original.data
            del expected['data_hex']
            for name, value in expected.items():
                if name != 'timestamp':
                    self.assertEqual(row[name], value, name)
            self.assertTrue(math.isclose(row['timestamp'] - BASE, original.timestamp - BASE,
                rel_tol=0, abs_tol=1e-6), '原BLF纳秒相对坐标不得被默认7位小数吞掉')
        self.assertTrue(writer.finished and writer.closed)
        self.assertLessEqual(writer.output_path.stat().st_size, writer.spool_bytes)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_real_empty_blf_and_no_frame_permission(self):
        """零PUT仍经BLFWriter/stop生成可读空BLF，完成计数为0而非假缺文件。
        参数: 无。返回: None。异常: 原库或空产物/预留/完成断言失败。
        """
        writer = self.make_writer('empty.blf')
        writer.finish()
        self.assertEqual(self.read_fields(writer.output_path), ())
        self.assertEqual(writer.counters, {'puts_issued': 0, 'acks_received': 0, 'frames_written': 0})
        self.assertEqual(writer.spool_bytes, 65536)
        self.assertGreater(writer.output_path.stat().st_size, 0)
        self.assertTrue(writer.finished)

    def test_real_calls_build_once_write_once_each_stop_once(self):
        """透传真实旧函数的trace证明READY不写帧、PUT原顺序一次、FINISH只stop。
        参数: 无。返回: None。异常: 原库或真实调用次数/参数/顺序断言失败。
        """
        writer = self.make_writer('trace.blf')
        with patch.object(module, 'worker_main', new=traced_old_writer):
            writer.start()
        trace_path = writer.output_path.with_suffix('.trace.jsonl')
        start = tuple(json.loads(line) for line in trace_path.read_text(encoding='utf-8').splitlines())
        self.assertEqual(tuple(row['rule'] for row in start), ('build_writer',))
        self.assertEqual(start[0]['path'], str(writer.output_path))
        self.assertEqual(start[0]['format'], 'blf')
        for frame in (FRAME, replace(FRAME, data=b'\x03\x04')):
            writer.write(frame)
        before = tuple(json.loads(line) for line in trace_path.read_text(encoding='utf-8').splitlines())
        self.assertEqual(tuple(row['rule'] for row in before),
            ('build_writer', 'on_message_received', 'on_message_received'))
        writer.finish()
        final = tuple(json.loads(line) for line in trace_path.read_text(encoding='utf-8').splitlines())
        self.assertEqual(tuple(row['rule'] for row in final),
            ('build_writer', 'on_message_received', 'on_message_received', 'stop'))
        self.assertEqual(tuple(row['data_hex'] for row in final if row['rule'] == 'on_message_received'),
            ('0102', '0304'))

    def test_real_open_writer_parent_cancel_keeps_file_and_closes_actual_process(self):
        """真实原writer已接首帧，第二PUT接收取消保原对象与部分文件且不伪finished。
        参数: 无。返回: None。异常: 原库或真实PID/取消/关闭/借款断言失败。
        """
        writer = self.make_writer('cancelled.blf').start()
        writer.write(FRAME)
        primary = SystemExit('actual writer receive cancellation')
        fault = ActualFault(writer._connection, 'recv_bytes', primary)
        writer._connection = fault
        with self.assertRaises(SystemExit) as caught:
            writer.write(replace(FRAME, timestamp=BASE + .125))
        self.assertIs(caught.exception, primary)
        self.assertTrue(writer.closed and writer.failed)
        self.assertFalse(writer.finished)
        self.assertIsNotNone(writer._exit_code)
        self.assertIsNone(writer._process)
        self.assertTrue(writer.output_path.exists())
        self.assertEqual(writer.counters['puts_issued'], 2)
        self.assertEqual(writer.counters['frames_written'], 1)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_real_write_after_failure_keeps_prefix_and_actual_partial_file(self):
        """第二次原on_message_received已实际执行后失败，父只确认首帧且部分BLF保留。
        参数: 无。返回: None。异常: 原库或真实次数/原故障事实/部分文件/费用断言失败。
        """
        writer = self.make_writer('partial-old.blf')
        with patch.object(module, 'worker_main', new=partial(traced_old_writer, fail_write_at=2)):
            writer.start()
        writer.write(FRAME)
        with self.assertRaises(module.LegacyCANWriteError) as caught:
            writer.write(replace(FRAME, timestamp=BASE + .125))
        self.assertIsInstance(caught.exception.__cause__, module.RemoteLegacyError)
        self.assertEqual(caught.exception.__cause__.facts['type'], 'OSError')
        self.assertEqual(caught.exception.__cause__.facts['message'], 'actual old writer failed after frame')
        self.assertEqual(writer.counters, {'puts_issued': 2, 'acks_received': 1, 'frames_written': 1})
        self.assertTrue(writer.closed and writer.failed and not writer.finished)
        trace = tuple(json.loads(line) for line in writer.output_path.with_suffix('.trace.jsonl')
            .read_text(encoding='utf-8').splitlines())
        self.assertEqual(tuple(row['rule'] for row in trace),
            ('build_writer', 'on_message_received', 'on_message_received', 'stop'))
        self.assertEqual(len(self.read_fields(writer.output_path)), 2, '原stop保留实际已进入旧writer的两帧')
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_real_stop_after_failure_is_not_finished_or_retried(self):
        """原stop已成功执行后故障仍非完成，不重复stop或把完整文件等同成功事实。
        参数: 无。返回: None。异常: 原库或实际stop次数/远端cause/关闭断言失败。
        """
        writer = self.make_writer('stop-old.blf')
        with patch.object(module, 'worker_main', new=partial(traced_old_writer, fail_stop=True)):
            writer.start()
        writer.write(FRAME)
        with self.assertRaises(module.LegacyCANWriteError) as caught:
            writer.finish()
        self.assertEqual(caught.exception.__cause__.phase, 'stop')
        self.assertEqual(caught.exception.__cause__.facts['type'], 'RuntimeError')
        trace = tuple(json.loads(line) for line in writer.output_path.with_suffix('.trace.jsonl')
            .read_text(encoding='utf-8').splitlines())
        self.assertEqual(tuple(row['rule'] for row in trace), ('build_writer', 'on_message_received', 'stop'))
        self.assertTrue(writer.closed and writer.failed and not writer.finished)
        self.assertFalse(writer._finish_received)
        self.assertEqual(len(self.read_fields(writer.output_path)), 1)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
