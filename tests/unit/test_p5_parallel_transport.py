"""核并行面积的固定模型、原序交付与自有资源清理，不做性能计时。

小型ASC和DBC在本测试临时目录生成；数值位型另用固定期望核对，不能仅靠
同一编码器往返证明业务结果。测试不创建正式结果或修改历史项目。
"""
from dataclasses import replace
from decimal import Decimal
from collections import deque
import multiprocessing
from pathlib import Path
from types import SimpleNamespace
import struct
import tempfile
from time import monotonic
import unittest
from unittest.mock import patch

from chronaxis._control_wire import ControlChannel, ControlProtocolError
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import DerivedDefinition, validate_expression
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, TimeType
from chronaxis.execution.file_integral_terms import (SameTimeGroupSummary, FileIntegralHead,
    FileIntegralTail, IntegralColumnTerms, IntegralTermsChunk, FileIntegralFrontier)
from chronaxis.execution.integral_blocks import encode_packet, decode_packet, pack_task, restore_task, IntegralBlockError, boundary_supported
from chronaxis.execution.parallel_integral_pool import ParallelIntegralPool
from chronaxis.execution.parallel_integral_worker import take_events, worker_main, _facts
from chronaxis.execution.same_frame_integrals import SameFrameBinding
from chronaxis.legacy.records import LegacyCANField
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError
from chronaxis.sources.asc import ASCSpec
from chronaxis.sources.protocol import SourceReadError
from chronaxis.sources.text_can_spec import CANTextSpec


def fixture_facts():
    """返回独立有限事实。参数: 无。返回: dict。异常: 无。"""
    return dict(count=3,first_ns=0,last_ns=2000000000,decode_calls=3,
        first_order_time=Decimal('0'),last_order_time=Decimal('2.000000000000000001'),compatibility_fields=())


class _ByteEndpoint:
    """只存固定字节的测试端点，可在发送时核资源仍被计费。"""
    def __init__(self,read,write,observe=None):
        """参数为收发队列和可选观测函数；返回端点；无主动异常。"""
        self.read,self.write,self.observe=read,write,observe
    def send_bytes(self,value):
        """参数bytes；观测后保存字节；返回None；观测错误原样传播。"""
        if self.observe is not None:self.observe(value)
        self.write.append(bytes(value))
    def recv_bytes(self,maximum):
        """参数上限；返回一片；空队列EOFError，超长ValueError。"""
        if not self.read:raise EOFError()
        value=self.read.popleft()
        if len(value)>maximum:raise ValueError('oversize')
        return value
    def poll(self,*args):
        """参数兼容管道签名；返回队列是否非空；无主动异常。"""
        return bool(self.read)
    def close(self):
        """参数无；无操作；返回None；无异常。"""



def _fault_worker(control,data,mode):
    """测试用固定故障worker。参数: 两端点及测试模式。返回: None。异常: 指定退出码。

    仅供spawn故障注入，读取本测试DBC取得合法READY，不运行用户分析代码。
    """
    from chronaxis.execution.can_block_codec import encode_metadata
    from chronaxis.execution.parallel_can_worker import plain
    from chronaxis.sources.text_can_decode import CANTextDecodeRead
    index=0;reader=None
    try:
        while True:
            command=control.recv()
            if command[0]=='close':
                if mode=='close':raise SystemExit(7)
                return
            if command[0]=='file':
                _,index,spec,signals,options,limit,_=command
                if mode=='ready' and index==1:
                    control.send(('error',index,0,'read','ValueError','后文件READY失败'))
                    continue
                reader=CANTextDecodeRead(spec,ResourceBudget(limit),signals,**options)
                encoded=encode_metadata(plain(reader.prepare_metadata()))
                import os
                control.send(('ready',index,os.getpid(),len(encoded)));data.send_bytes(encoded)
                reader.close();reader=None
            elif command[0]=='budget':control.maximum=command[1]
            elif command[0]=='configure':continue
            elif command[0]=='next':
                if mode=='compute':
                    control.send(('error',index,0,'compute','ValueError','数值结构错误'))
                    continue
                facts=dict(count=0,first_ns=None,last_ns=None,decode_calls=0,
                    first_order_time=None,last_order_time=None,compatibility_fields=())
                encoded=encode_packet(index,0,(FileIntegralTail(None,False),),True,facts)
                if mode=='pipe':encoded=b'x'*524288
                control.send(('block',index+1 if mode=='protocol' else index,0,len(encoded),0.0))
                data.send_bytes(encoded)
                if mode=='refund':control.send(('error',index,1,'cleanup','RuntimeError','workspace refund failed'))
                else:control.send(('finished',index,1))
    finally:
        if reader is not None:reader.close()
        control.close();data.close()


def _ready_failure(control,data):
    """后文件初始化失败入口。参数: 控制/数据端点。返回: None。异常: 原管道错误。"""
    _fault_worker(control,data,'ready')


def _close_failure(control,data):
    """收到close后异常退出。参数: 控制/数据端点。返回: 无。异常: SystemExit(7)。"""
    _fault_worker(control,data,'close')


def _full_pipe(control,data):
    """发送整512KiB包以覆盖取消。参数: 控制/数据端点。返回: None。异常: 父取消。"""
    _fault_worker(control,data,'pipe')


def _bad_protocol(control,data):
    """发送错误文件编号。参数: 控制/数据端点。返回: None。异常: 父关闭。"""
    _fault_worker(control,data,'protocol')


def _compute_failure(control,data):
    """计算阶段ValueError入口。参数: 两端点。返回: None。异常: 原管道错误。"""
    _fault_worker(control,data,'compute')


def _refund_failure(control,data):
    """末包送达后退款失败。参数: 两端点。返回: None。异常: 原管道错误。"""
    _fault_worker(control,data,'refund')


class P5ParallelTransportTests(unittest.TestCase):
    """每项独占临时来源，正常/失败/取消之后均核父预算与子进程。"""
    def setUp(self):
        """参数无；建立ASC/DBC和冻结数值任务；返回None；写入错误原样传播。"""
        self.directory=tempfile.TemporaryDirectory(prefix='p5-transport-')
        self.addCleanup(self.directory.cleanup);self.root=Path(self.directory.name)
        self.dbc=self.root/'power.dbc'
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Power: 1 Node\n'
            ' SG_ Power : 0|8@1+ (1,0) [0|255] "W" Node\n',encoding='utf-8')
        self.timebase=TimebaseSpec('clock',TimeType.RELATIVE,'origin')
        self.definition=SignalDefinition('power','bus',LegacyCANField(0,'Power',256,False,False).key,D.FLOAT64,'W',3000000000)
        self.domain=Interval(0,4000000000)
        self.bindings=DeclarationBindings('session',self.timebase,self.domain,
            (DeclaredSource('bus',self.timebase,'synthetic-transport'),),(self.definition,))
        self.expression=validate_expression('power',self.bindings)
        self.specification=CalculationDefinition('energy','integral',self.domain,output_unit='J')
        self.binding=SameFrameBinding('bus',0,256,False,False,False)
        self.children={process.pid for process in multiprocessing.active_children()}

    def file(self,name,start=0,*,bad=False):
        """参数为文件名、起秒及错误标志；返回ASCSpec；写入错误直接传播。"""
        path=self.root/name
        path.write_text('base hex timestamps absolute\n'+''.join(
            f'{start+i:.9f} 1 100 Rx d 1 0A\n' for i in range(3))+
            ('broken data record\n' if bad else ''),encoding='utf-8')
        return ASCSpec(path)

    def pool(self,files,*,count=2,budget=None):
        """参数为文件列表/上限/预算；返回池和账本；构造原错传播。"""
        budget=budget or ResourceBudget()
        source=CANTextSpec('bus',tuple(files),self.dbc,0,self.timebase,'strict')
        owner=ParallelIntegralPool(source,budget,(self.definition,),process_count=count,
            classify_unselected=False,integrity=False,trace=False,retain_source_time=False)
        self.addCleanup(owner.close)
        return owner,budget

    def configure(self,pool):
        """参数为已准备池；安装现有表达式；返回None；配置错误原样传播。"""
        pool.configure((self.definition,),(self.expression,),(self.specification,),self.binding,'session',domain=self.domain)

    def assert_clean(self,pool,budget):
        """参数为池及账本；断言幂等清理与无新增子进程；返回None；失败抛断言。"""
        pool.close();pool.close();self.assertEqual(budget.ram_bytes,0)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}-self.children,set())

    def test_task_roundtrip_preserves_declaration_and_derived(self):
        """实际TTL与原声明分别传输，派生表达式仍保留原绑定身份。"""
        original=replace(self.definition,valid_for_ns=None)
        bindings=replace(self.bindings,signals=(original,),derived_names=('scaled',))
        derived=(DerivedDefinition('scaled','power * 2'),)
        expression=validate_expression('scaled',bindings,derived=derived)
        task=pack_task((self.definition,),(expression,),(self.specification,),self.binding,'session',derived=derived)
        result=restore_task(task)
        self.assertEqual(result['expressions'],(expression,));self.assertEqual(result['definitions'],(self.definition,))
        self.assertEqual(result['derived'],derived);self.assertIsNone(result['domain'])
        task['bindings']['identity']='bad'
        with self.assertRaisesRegex(ValueError,'身份不符'):restore_task(task)

    def test_admission_cost_matches_actual_reservation_without_reading(self):
        """首帧前查询费用与实际配置增量一致，用户大批上限不放大传输块。"""
        files=(self.file('a.asc'),self.file('b.asc',3));pool,budget=self.pool(files)
        startup=pool.startup_cost(pool.spec,(self.definition,),process_count=2,**pool._options)
        pool.prepare_metadata()
        self.assertEqual(budget.ram_bytes,startup+pool._metadata_cost)
        before=budget.ram_bytes
        cost=pool.configuration_cost((self.definition,),(self.expression,),(self.specification,),
                                    self.binding,'session',domain=self.domain,batch_intervals=4096)
        self.assertEqual(budget.ram_bytes,before);self.assertEqual(pool.count,0)
        pool.configure((self.definition,),(self.expression,),(self.specification,),
                       self.binding,'session',domain=self.domain,batch_intervals=4096)
        self.assertEqual(budget.ram_bytes-before,cost)
        self.assertEqual(pool._task['batch_intervals'],64)
        self.assert_clean(pool,budget)

    def test_binary_values_and_exact_time_are_not_rounded(self):
        """负零/最大uint64/浮点相邻值及精确Decimal均无损，面积字节另按struct核对。"""
        values=(ScalarValue(-0.,D.FLOAT64),ScalarValue(2**64-1,D.UINT64),ScalarValue(None,D.INT64,False,Q.MISSING))
        group=SameTimeGroupSummary(0,0,2,3,values,values,(None,None,None))
        area=float.fromhex('0x1.0000000000001p+0')
        events=(FileIntegralHead(group,1),IntegralTermsChunk(1,2,(IntegralColumnTerms((area,-0.),(True,False),1,1,Q.NONE),)),FileIntegralTail(group,False))
        encoded=encode_packet(3,4,events,True,fixture_facts())
        self.assertIn(struct.pack('!d',area),encoded)
        restored=decode_packet(encoded)
        self.assertEqual(restored.events,events);self.assertEqual(restored.facts,fixture_facts())
        self.assertEqual(struct.pack('!d',restored.events[0].group.first_values[0].value),struct.pack('!d',-0.))
        frontier=FileIntegralFrontier(2)
        self.assertEqual(decode_packet(encode_packet(0,0,(frontier,),False,fixture_facts())).events,(frontier,))
        opened=replace(events[1],right_closed=False)
        self.assertFalse(decode_packet(encode_packet(0,0,(opened,),False,fixture_facts())).events[0].right_closed)

    def test_block_rejects_truncation_trailing_and_nonfinite_area(self):
        """错误包不能绕过长度与有限数检查，也不加载Python对象。"""
        event=IntegralTermsChunk(0,1,(IntegralColumnTerms((1.,),(True,),1,1,Q.NONE),))
        packet=encode_packet(0,0,(event,),False,fixture_facts())
        for broken in (packet[:-1],packet+b'x',b'BAD!'+packet[4:]):
            with self.subTest(broken=broken[:8]):
                with self.assertRaises(IntegralBlockError):decode_packet(broken)
        event=IntegralTermsChunk(0,1,(IntegralColumnTerms((float('inf'),),(True,),1,1,Q.NONE),))
        with self.assertRaisesRegex(IntegralBlockError,'有限'):decode_packet(encode_packet(0,0,(event,),False,fixture_facts()))

    def test_control_channel_preserves_integral_identity_and_direction(self):
        """真实字节管道传文件级错误的序号，父端不能伪装worker发送结果。"""
        first,second=multiprocessing.Pipe()
        parent=ControlChannel(first,'integral',parent=True,max_bytes=1048576)
        worker=ControlChannel(second,'integral',parent=False,max_bytes=1048576)
        try:
            worker.send(('error',2,3,'read','ValueError','坏输入'))
            self.assertEqual(parent.recv(),('error',2,3,'read','ValueError','坏输入'))
            worker.send(('finished',2,3))
            self.assertEqual(parent.recv(),('finished',2,3))
            with self.assertRaises(ControlProtocolError):parent.send(('ready',0,123,42))
            with self.assertRaises(ControlProtocolError):parent.send(('finished',2,3))
        finally:parent.close();worker.close()

    def test_prepare_only_does_not_open_missing_input(self):
        """首帧前只读DBC；实际输入不存在时prepare仍可完成，关闭没有读取错误。"""
        pool,budget=self.pool((ASCSpec(self.root/'missing.asc'),))
        metadata=pool.prepare_metadata()
        self.assertEqual(metadata['profile'],'can-text-v1');self.assertEqual(pool.count,0)
        self.assertFalse(pool.file_facts);self.assert_clean(pool,budget)

    def test_file_order_and_eof_facts(self):
        """后文件可提前准备，但事件/事实只在按序消费后交付，槽可复用。"""
        files=tuple(self.file(f'{i}.asc',i*3) for i in range(3))
        pool,budget=self.pool(files);pool.prepare_metadata();self.configure(pool)
        for index in range(3):
            events=tuple(pool.iter_file(index))
            self.assertIsInstance(events[0],FileIntegralHead);self.assertIsInstance(events[-1],FileIntegralTail)
            self.assertEqual(pool.file_facts[index]['count'],3)
            self.assertEqual(set(pool.file_facts),set(range(index+1)))
        self.assertEqual(pool.count,9);self.assertEqual(pool.last_ns,8000000000)
        self.assertLessEqual(len(pool.timings['worker_pids']),2);self.assert_clean(pool,budget)

    def test_later_file_error_waits_for_earlier_complete_file(self):
        """后文件缺失不会抢在前文件有效首尾事件之前抛出。"""
        pool,budget=self.pool((self.file('first.asc'),ASCSpec(self.root/'later-missing.asc')))
        pool.prepare_metadata();self.configure(pool)
        events=tuple(pool.iter_file(0));self.assertIsInstance(events[-1],FileIntegralTail)
        with self.assertRaisesRegex(SourceReadError,'later-missing.asc'):tuple(pool.iter_file(1))
        self.assert_clean(pool,budget)

    def test_out_of_order_request_does_not_consume_a_file(self):
        """调用者不能跳过前文件；拒绝后仍可取消并完整清理。"""
        pool,budget=self.pool((self.file('a.asc'),self.file('b.asc',3)))
        pool.prepare_metadata();self.configure(pool)
        with self.assertRaisesRegex(ValueError,'按原序'):tuple(pool.iter_file(1))
        self.assertEqual(pool.count,0);self.assert_clean(pool,budget)

    def test_close_with_unconsumed_prefetch_releases_resources(self):
        """工作进程可能停在块发送/等待许可，取消不要求消费所有文件。"""
        pool,budget=self.pool((self.file('a.asc'),self.file('b.asc',3)))
        pool.prepare_metadata();self.configure(pool);self.assert_clean(pool,budget)

    def test_low_budget_constructor_leaves_ledger_unchanged(self):
        """固定空间预付失败发生在创建进程之前，不能遗留部分费用。"""
        budget=ResourceBudget(1024)
        with self.assertRaises(BudgetExceededError):self.pool((self.file('a.asc'),),budget=budget)
        self.assertEqual(budget.ram_bytes,0)

    def test_later_ready_failure_is_deferred(self):
        """后文件在READY之前失败，也必须等前文件完成再向外抛出。"""
        pool,budget=self.pool((self.file('first.asc'),self.file('later.asc',3)))
        with patch('chronaxis.execution.parallel_integral_pool.worker_main',_ready_failure):
            pool.prepare_metadata();self.configure(pool)
            self.assertEqual(tuple(pool.iter_file(0)),(FileIntegralTail(None,False),))
            with self.assertRaisesRegex(SourceReadError,'后文件READY失败'):tuple(pool.iter_file(1))
        self.assert_clean(pool,budget)

    def test_partial_process_start_cleans_first_process_and_unstarted_pipes(self):
        """第二槽构造失败时，第一槽和第二槽已建立端点均由原owner关闭。"""
        pool,budget=self.pool((self.file('first.asc'),self.file('second.asc',3)))
        context=multiprocessing.get_context('spawn')
        class FailSecond:
            """仅第二次Process构造失败的真实spawn代理。"""
            def __init__(self):
                """参数无；初始化计数；返回None；无主动异常。"""
                self.count=0
            def __getattr__(self,name):
                """参数为属性名；返回原上下文属性；异常按原对象。"""
                return getattr(context,name)
            def Process(self,*args,**kwargs):
                """第二次抛OSError。参数为真实Process参数；返回Process；异常为指定构造失败。"""
                self.count+=1
                if self.count==2:raise OSError('second slot failed')
                return context.Process(*args,**kwargs)
        with patch('chronaxis.execution.parallel_integral_pool.multiprocessing.get_context',return_value=FailSecond()):
            with self.assertRaisesRegex(OSError,'second slot'):pool.prepare_metadata()
        self.assert_clean(pool,budget)

    def test_worker_close_failure_is_not_success(self):
        """数据EOF之后工作进程退出码异常，关闭仍失败且清理账本和句柄。"""
        pool,budget=self.pool((self.file('file.asc'),))
        with patch('chronaxis.execution.parallel_integral_pool.worker_main',_close_failure):
            pool.prepare_metadata();self.configure(pool);tuple(pool.iter_file(0))
            with self.assertRaisesRegex(SourceReadError,'退出码'):pool.close()
        self.assert_clean(pool,budget)

    def test_cancel_while_full_data_packet_is_waiting(self):
        """已收到大块通知而尚未接收数据时取消，不要求排空管道。"""
        pool,budget=self.pool((self.file('file.asc'),))
        with patch('chronaxis.execution.parallel_integral_pool.worker_main',_full_pipe):
            pool.prepare_metadata();self.configure(pool)
            self.assertTrue(pool._slots[0]['control'].poll(5),'worker未发出块通知')
            self.assert_clean(pool,budget)

    def test_wrong_file_protocol_closes_all_workers(self):
        """坏包文件号不能进入数值累计，失败后没有残留进程和预算。"""
        pool,budget=self.pool((self.file('file.asc'),))
        with patch('chronaxis.execution.parallel_integral_pool.worker_main',_bad_protocol):
            pool.prepare_metadata();self.configure(pool)
            with self.assertRaisesRegex(ControlProtocolError,'序号'):tuple(pool.iter_file(0))
        self.assert_clean(pool,budget)

    def test_cancel_after_successful_reservation_refunds_exact_amount(self):
        """预算已实际增加后取消，事务helper登记并在关闭时精确退回。"""
        class CancelBudget(ResourceBudget):
            """在指定次成功预付后抛取消，用于覆盖所有权登记窗口。"""
            fail=False
            def reserve_ram(self,amount):
                """参数为bytes；先真实预付再按标志取消；返回None；异常KeyboardInterrupt。"""
                super().reserve_ram(amount)
                if self.fail:self.fail=False;raise KeyboardInterrupt()
        budget=CancelBudget();pool,_=self.pool((self.file('file.asc'),),budget=budget)
        pool.prepare_metadata();budget.fail=True
        with self.assertRaises(KeyboardInterrupt):self.configure(pool)
        self.assert_clean(pool,budget)

    def test_compute_error_retains_its_known_type(self):
        """工作进程数值ValueError不会变成读取错误，原类型由有限白名单恢复。"""
        pool,budget=self.pool((self.file('file.asc'),))
        with patch('chronaxis.execution.parallel_integral_pool.worker_main',_compute_failure):
            pool.prepare_metadata();self.configure(pool)
            with self.assertRaisesRegex(ValueError,'数值结构错误') as caught:tuple(pool.iter_file(0))
            self.assertIs(type(caught.exception),ValueError)
        self.assert_clean(pool,budget)

    def test_configuration_minimum_is_below_exact_quote(self):
        """前置下界与实际任务共用批限制，宽计算项或大用户批不能使下界高于完整报价。"""
        from chronaxis.execution.file_integral_terms import file_terms_cost, file_terms_minimum_cost, parent_terms_cost, parent_terms_minimum_cost
        for count in (1,6):
            definitions=(self.definition,)
            expressions=(self.expression,)*count
            specifications=(self.specification,)*count
            for batch in (1,64,4096):
                with self.subTest(calculations=count,batch=batch):
                    pool,budget=self.pool((self.file('first.asc'),self.file('second.asc',3)))
                    try:
                        minimum=pool.configuration_minimum_cost(count,process_count=2,file_count=2,batch_intervals=batch)
                        exact=pool.configuration_cost(definitions,expressions,specifications,self.binding,'session',
                                                      domain=self.domain,batch_intervals=batch)
                        self.assertLess(minimum,exact)
                        self.assertLess(file_terms_minimum_cost(count,batch_intervals=batch),
                            file_terms_cost(definitions,expressions,specifications,batch_intervals=batch))
                        self.assertLess(parent_terms_minimum_cost(count,batch_intervals=batch),
                            parent_terms_cost(definitions,expressions,batch_intervals=batch))
                        self.assertFalse(pool._started)
                    finally:self.assert_clean(pool,budget)

    def test_unknown_remote_error_type_never_imports_a_class(self):
        """未知远端类型只展示为SourceReadError文字，不动态查找或执行构造器。"""
        pool,budget=self.pool((self.file('file.asc'),))
        with self.assertRaisesRegex(SourceReadError,'malicious.module.Custom'):
            pool._raise_file(dict(file=0,error=('compute','malicious.module.Custom','message')))
        self.assert_clean(pool,budget)

    def test_future_file_first_credit_computes_a_real_batch(self):
        """未轮到的文件也在一次许可内处理4096帧，不能只计算首Head就停。"""
        files=[]
        for index in range(2):
            path=self.root/f'dense-{index}.asc'
            path.write_text('base hex timestamps absolute\n'+''.join(
                f'{index*10+i/1000:.9f} 1 100 Rx d 1 0A\n' for i in range(6000)),encoding='utf-8')
            files.append(ASCSpec(path))
        pool,budget=self.pool(files);pool.prepare_metadata();self.configure(pool)
        until=monotonic()+15
        while any(slot.get('packet') is None for slot in pool._slots) and monotonic()<until:
            if not pool._poll_controls():pool._slots[0]['control'].poll(.05)
        future=pool._file_slots[1]
        self.assertIsNotNone(future['packet'],'后文件没有完成首批')
        packet=decode_packet(future['packet'])
        self.assertEqual(packet.facts['count'],4096)
        self.assertGreaterEqual(len(packet.events),60)
        self.assertTrue(any(type(event) is IntegralTermsChunk for event in packet.events))
        self.assertFalse(packet.eof);self.assertFalse(pool.file_facts)
        self.assert_clean(pool,budget)

    def test_wide_multiple_columns_split_without_advancing_facts(self):
        """千计算项按真实列宽分包，先包使用自身末事件事实而不是后续文件末事实。"""
        column=IntegralColumnTerms((1.,)*14,(True,)*14,14,14,Q.NONE)
        items=[]
        for index in range(5):
            facts=fixture_facts();facts.update(count=index+1,decode_calls=index+1)
            items.append((IntegralTermsChunk(index*14,(index+1)*14,(column,)*1000),facts))
        events,remaining,facts=take_events(tuple(items),items[-1][1])
        self.assertEqual(len(events),2);self.assertEqual(len(remaining),3);self.assertEqual(facts['count'],2)
        packet=encode_packet(0,0,events,False,facts)
        self.assertLessEqual(len(packet),524288)
        self.assertEqual(decode_packet(packet).events,events)

    def test_boundary_admission_and_compatibility_snapshots_are_bounded(self):
        """极宽边界在读取前排除，未变化兼容图在多事件快照间共享，不重复建128份。"""
        self.assertTrue(boundary_supported((self.definition,)))
        self.assertFalse(boundary_supported((self.definition,)*4096))
        self.assertFalse(boundary_supported((SimpleNamespace(field='宽'*200000),)))
        field=LegacyCANField(0,'Power',256,False,True)
        terms=SimpleNamespace(compatibility_fields={field:False})
        reader=SimpleNamespace(count=1,first_ns=0,last_ns=0,decode_calls=1,
            first_order_time=Decimal('0'),_last_selected_time=Decimal('0'))
        cache={};first=_facts(reader,terms,cache)
        for _ in range(128):self.assertIs(_facts(reader,terms,cache)['compatibility_fields'],first['compatibility_fields'])

    def test_wide_facts_are_included_in_packet_limit(self):
        """兼容提示超过旧64KiB余量时按实际图宽分包，保持完整字段和前缀事实。"""
        facts=fixture_facts()
        facts['compatibility_fields']=tuple(('signal'+str(index)+'界'*200,False) for index in range(500))
        column=IntegralColumnTerms((1.,)*14,(True,)*14,14,14,Q.NONE)
        event=IntegralTermsChunk(0,14,(column,)*1000)
        events,remaining,current=take_events(((event,facts),(event,facts)),facts)
        self.assertEqual(len(events),1);self.assertEqual(len(remaining),1)
        packet=encode_packet(0,0,events,False,current)
        self.assertEqual(decode_packet(packet).facts['compatibility_fields'],facts['compatibility_fields'])

    def test_primary_read_error_survives_workspace_refund_failure(self):
        """已有读取主错后BLOCK_RAM退款再失败，返回仍是原读取错误且附清理说明。"""
        from chronaxis.execution.integral_blocks import BLOCK_RAM
        from chronaxis.sources.text_can_decode import CANTextDecodeRead
        incoming,outgoing=deque(),deque()
        class Endpoint:
            """固定内存字节端点；测试不启进程、不使用pickle。"""
            def __init__(self,read,write):
                """参数为两个队列；返回端点；无主动异常。"""
                self.read,self.write=read,write;self.closed=False
            def send_bytes(self,value):
                """参数bytes；保存副本；返回None；内存错误直接传播。"""
                self.write.append(bytes(value))
            def recv_bytes(self,maximum):
                """参数上限；返回一片；空队列EOFError，超长ValueError。"""
                if not self.read:raise EOFError()
                value=self.read.popleft()
                if len(value)>maximum:raise ValueError('oversize')
                return value
            def poll(self,*args):
                """参数沿管道等待签名；返回是否有片；无主动异常。"""
                return bool(self.read)
            def close(self):
                """参数无；标记关闭；返回None；无主动异常。"""
                self.closed=True
        class FailingReader:
            """真实DBC元数据配一次读错，资源仍交真实读取器管理。"""
            def __init__(self,*args,**kwargs):
                """参数转交真实读取器；返回wrapper；构造原错传播。"""
                self.reader=CANTextDecodeRead(*args,**kwargs)
            def __getattr__(self,name):
                """参数属性名；返回真实属性；原属性错误传播。"""
                return getattr(self.reader,name)
            def __next__(self):
                """参数无；不返回；固定原读取错误。"""
                raise SourceReadError('original read failure')
        class RefundBudget(ResourceBudget):
            """只在首次块workspace退款时注入失败。"""
            instance=None
            def __init__(self,*args):
                """参数转交预算；记录测试实例；返回None；原错传播。"""
                super().__init__(*args);self.failed=False;type(self).instance=self
            def release_ram(self,amount):
                """参数bytes；首次workspace退款失败，否则真实退款；返回None；RuntimeError。"""
                if amount==BLOCK_RAM and not self.failed:
                    self.failed=True;raise RuntimeError('workspace refund failed')
                super().release_ram(amount)
        parent=ControlChannel(Endpoint(outgoing,incoming),'integral',parent=True,max_bytes=64*1048576)
        child=ControlChannel(Endpoint(incoming,outgoing),'integral',parent=False,max_bytes=64*1048576)
        data=Endpoint(deque(),deque())
        source=CANTextSpec('bus',(self.file('fixture.asc'),),self.dbc,0,self.timebase,'strict')
        task=pack_task((self.definition,),(self.expression,),(self.specification,),self.binding,'session',domain=self.domain)
        parent.send(('file',0,source,(self.definition,),dict(integrity=False,trace=False),64*1048576,None))
        parent.send(('configure',0,task,64*1048576));parent.send(('next',));parent.send(('next',));parent.send(('close',))
        with patch('chronaxis.execution.parallel_integral_worker.CANTextDecodeRead',FailingReader), \
             patch('chronaxis.execution.parallel_integral_worker.ResourceBudget',RefundBudget), \
             patch('chronaxis.execution.parallel_integral_worker.signal.signal'):
            worker_main(child,data)
        messages=[]
        while parent.poll():messages.append(parent.recv())
        errors=[message for message in messages if message[0]=='error']
        self.assertEqual(len(errors),1);self.assertEqual(errors[0][3:5],('read','SourceReadError'))
        self.assertIn('original read failure',errors[0][5]);self.assertIn('RuntimeError',errors[0][5])
        self.assertEqual(RefundBudget.instance.ram_bytes,0)
        parent.close()

    def test_workspace_held_until_eof_payload_sent_and_finished(self):
        """成功末包发送时仍有块费用，释放后才发送finished；退款失败不能确认成功。"""
        from chronaxis.execution.integral_blocks import BLOCK_RAM
        for fail_refund in (False,True):
            with self.subTest(fail_refund=fail_refund):
                class BudgetProbe(ResourceBudget):
                    """记录实例并可只失败一次块退款。"""
                    instance=None
                    def __init__(self,*args):
                        """参数转交预算；保存实例；返回None；原错传播。"""
                        super().__init__(*args);self.failed=False;type(self).instance=self
                    def release_ram(self,amount):
                        """参数费用；按测试注入或退款；返回None；注入RuntimeError。"""
                        if fail_refund and amount==BLOCK_RAM and not self.failed:
                            self.failed=True;raise RuntimeError('late refund failure')
                        return super().release_ram(amount)
                incoming,outgoing=deque(),deque();observed=[]
                def observe(value):
                    """参数为发送数据；记录积分包发送时费用；返回None；无主动异常。"""
                    if value[:4]==b'P5I1':observed.append((decode_packet(value).eof,BudgetProbe.instance.ram_bytes))
                parent=ControlChannel(_ByteEndpoint(outgoing,incoming),'integral',parent=True,max_bytes=64*1048576)
                child=ControlChannel(_ByteEndpoint(incoming,outgoing),'integral',parent=False,max_bytes=64*1048576)
                data=_ByteEndpoint(deque(),deque(),observe)
                source=CANTextSpec('bus',(self.file('final.asc'),),self.dbc,0,self.timebase,'strict')
                task=pack_task((self.definition,),(self.expression,),(self.specification,),self.binding,'session',domain=self.domain)
                parent.send(('file',0,source,(self.definition,),dict(integrity=False,trace=False),64*1048576,None))
                parent.send(('configure',0,task,64*1048576));parent.send(('next',));parent.send(('close',))
                with patch('chronaxis.execution.parallel_integral_worker.ResourceBudget',BudgetProbe), \
                     patch('chronaxis.execution.parallel_integral_worker.signal.signal'):
                    worker_main(child,data)
                messages=[]
                while parent.poll():messages.append(parent.recv())
                self.assertTrue(observed);self.assertTrue(observed[-1][0])
                self.assertTrue(all(amount>=BLOCK_RAM for _,amount in observed))
                self.assertEqual(BudgetProbe.instance.ram_bytes,0)
                self.assertEqual(any(item[0]=='finished' for item in messages),not fail_refund)
                self.assertEqual(any(item[0]=='error' for item in messages),fail_refund)
                if fail_refund:self.assertEqual(messages[-1][3],'cleanup')
                parent.close()

    def test_eof_without_successful_refund_does_not_finish_file(self):
        """收到EOF数据后退款失败，父进程不完成文件、不复用槽，且清理全部费用。"""
        with patch('chronaxis.execution.parallel_integral_pool.worker_main',_refund_failure):
            pool,budget=self.pool((self.file('first.asc'),self.file('second.asc')))
            pool.prepare_metadata()
            self.configure(pool)
            with self.assertRaisesRegex(SourceReadError,'workspace refund failed'):list(pool.iter_file(0))
            self.assertEqual(pool._current,0);self.assert_clean(pool,budget)


if __name__=='__main__':unittest.main()
