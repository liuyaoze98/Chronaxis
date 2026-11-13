"""E4控制通道只传有限字节，含真实大计划与固定模型往返。"""
from collections import deque
from pathlib import Path
import struct
import unittest

from chronaxis._control_wire import ControlChannel, ControlProtocolError, CHUNK, encode_json, decode_json
from chronaxis._control_models import pack_source,restore_source,pack_signal,restore_signal,pack_options,restore_options
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import TimeType,SignalDType
from chronaxis.core.binding import SignalDefinition
from chronaxis.sources.asc import ASCSpec
from chronaxis.sources.blf import BLFSpec
from chronaxis.sources.text_can_spec import CANTextSpec
from chronaxis.legacy.records import LegacyCANField


class BytePipe:
    """只实现字节方法；若实现仍调用隐含pickle的send/recv测试立即失败。"""
    def __init__(self):
        """建立空的有限测试收发队列。

        参数: 无。
        返回: 新测试端点。
        异常: 无。
        """
        self.items=deque()
        self.closed=False
    def send_bytes(self,data):
        """保存一个实际发送字节片。

        参数: data为bytes类数据。
        返回: None，追加独立bytes。
        异常: 内存分配错误。
        """
        self.items.append(bytes(data))
    def recv_bytes(self,maximum):
        """按接收上限取下一片。

        参数: maximum为本次最大字节数。
        返回: bytes。
        异常: 空队列EOFError或超长OSError。
        """
        if not self.items:raise EOFError()
        data=self.items.popleft()
        if len(data)>maximum:raise OSError('bad message length')
        return data
    def close(self):
        """标记测试端点关闭。

        参数: 无。
        返回: None。
        异常: 无。
        """
        self.closed=True
    def poll(self,*args):
        """查询测试队列是否非空。

        参数: args沿用管道等待占位参数。
        返回: bool。
        异常: 无。
        """
        return bool(self.items)


class ControlCodecTests(unittest.TestCase):
    """以合成输入验证固定协议；各用例独立构造，无共享状态或真实日志。"""
    def channels(self,family,maximum=8*1024*1024):
        """为一个测试建立父子固定端点。

        参数: family为通道，maximum默认8MiB或batch的None。
        返回: BytePipe、父端、子端三元组。
        异常: 通道或额度错误。
        """
        pipe=BytePipe()
        return pipe,ControlChannel(pipe,family,parent=True,max_bytes=maximum),ControlChannel(pipe,family,parent=False,max_bytes=maximum)

    def test_source_and_signal_preserve_exact_model(self):
        """核ASC/BLF来源与信号声明精确往返。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        source=CANTextSpec('bus',(ASCSpec(Path('C:/数据.asc')),),Path('C:/DBC.dbc'),0,
                           TimebaseSpec('time',TimeType.RELATIVE,'clock'))
        self.assertEqual(restore_source(pack_source(source)),source)
        source=CANTextSpec('bus',(BLFSpec(Path('C:/数据.blf'),-99),),Path('C:/DBC.dbc'),0,source.timebase)
        self.assertEqual(restore_source(pack_source(source)),source)
        signal=SignalDefinition('voltage','bus',LegacyCANField(0,'Voltage',1,False,False).key,
            SignalDType.FLOAT64,'V',300000000,invalid_values=(None,False,1,'missing'))
        self.assertEqual(restore_signal(pack_signal(signal)),signal)

    def test_can_file_and_cycle_options(self):
        """核周期定位、所需ID及文件控制参数。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        pipe,parent,worker=self.channels('can')
        field=LegacyCANField(0,'Voltage',1,False,False)
        source=CANTextSpec('bus',(ASCSpec(Path('x.asc')),),Path('x.dbc'),0,TimebaseSpec('t',TimeType.RELATIVE,'clock'))
        options=dict(cycle_fields=(field,),metadata_fields=(field,),selected_ids=(1,),emit_frame_ids=frozenset((1,2)),integrity=False)
        parent.send(('file',source,(),options,8*1024*1024,None))
        message=worker.recv()
        self.assertEqual(message[:3],('file',source,()))
        self.assertEqual(message[3]['cycle_fields'],(field,))
        self.assertEqual(set(message[3]['emit_frame_ids']),{1,2})
        worker.send(('ready',123,55))
        self.assertEqual(parent.recv(),('ready',123,55))
        self.assertFalse(pipe.items)

    def test_no_callback_or_arbitrary_class_in_options(self):
        """拒绝回调及非固定对象进入控制编码。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        with self.assertRaises(ValueError):
            pack_options(dict(check_cancel=lambda:None))
        with self.assertRaises(TypeError):
            encode_json(object(),1024)

    def test_all_small_can_and_fast_commands(self):
        """核普通CAN与fast小命令往返。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        for family,messages in (
            ('can',[('ready',123,500),('block',50,0.,0.01,0.3),('sent',0.1),('error','Error','reason')]),
            ('fast',[('offer',1,2,3),('delivered',1,2,3),('stored',1,2,3),
                     ('eof',1,2,dict(raw=0,targets=[],valid=[],selected=[],kinds=[],compatible=[]),dict(send_seconds=0.),123),('error','Error','reason')])):
            pipe,parent,worker=self.channels(family)
            for message in messages:
                worker.send(message)
                self.assertEqual(parent.recv(),message)
            for operation in (('next','close') if family=='can' else ('next','direct','spool','close')):
                parent.send((operation,))
                self.assertEqual(worker.recv(),(operation,))

    def test_unknown_direction_version_and_command(self):
        """拒绝错方向、未知版本和未知命令。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        pipe,parent,worker=self.channels('can')
        with self.assertRaises(ControlProtocolError):parent.send(('ready',1,2))
        with self.assertRaises(ControlProtocolError):worker.send(('next',))
        for header in (struct.pack('!4sBBQ',b'CCP9',1,1,2),struct.pack('!4sBBQ',b'CCP1',1,255,2)):
            pipe.items.append(header)
            with self.assertRaises(ControlProtocolError):worker.recv()

    def test_json_duplicates_depth_and_nonfinite(self):
        """拒绝重复键、超深及非有限JSON数值。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        for body in (b'{"a":1,"a":2}',b'[NaN]',b'[1e999]',b'['*321+b'0'+b']'*321):
            with self.subTest(body=body[:40]),self.assertRaises(ValueError):
                decode_json(body)

    def test_chunk_size_truncation_and_extra_packet(self):
        """核64KiB分片上限并拒绝断片与额外尾片。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        pipe,parent,worker=self.channels('batch',None)
        parent.send(('run',{'job_id':'x','path':'a'*200000},'out','reference'))
        self.assertLessEqual(max(map(len,pipe.items)),CHUNK)
        saved=list(pipe.items)
        pipe.items=deque(saved[:-1])
        with self.assertRaises(EOFError):worker.recv()
        pipe.items=deque(saved)
        pipe.items.append(b'extra tail')
        worker.recv()
        with self.assertRaises(ControlProtocolError):worker.recv()

    def test_huge_result_header_does_not_preallocate_declared_total(self):
        """巨量声明只送一片后断开，不按总长度分配内存。

        参数: 无。
        返回: None；固定结果的64KiB分片不代表整个batch的RAM上限。
        异常: 断言失败或被测接口意外错误。
        """
        import tracemalloc
        pipe,parent,worker=self.channels('batch',None)
        # 2**63字节声明在原协议整型范围内；实际仅到达一个合法长度首片。
        pipe.items.append(struct.pack('!4sBBQ',b'CCP1',3,4,2**63)+b'x'*(CHUNK-14))
        tracemalloc.start()
        try:
            with self.assertRaises(EOFError):parent.recv()
            _,peak=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak,1024*1024)

    def test_long_result_identity_preserved_without_path_based_limit(self):
        """路径消息很短时，合法长会话名称仍完整返回。

        参数: 无。
        返回: None，不按原名称裁剪或补造摘要替代。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.batch.models import BatchJobResult
        pipe,parent,worker=self.channels('batch',None)
        parent.send(('run',{'job_id':'long','path':'plan.json'},'output',None))
        worker.recv()
        name='a'*100000
        result=BatchJobResult('long','failed',dataset_id=name,entity_id=name,session_id=name,
            error_type='ValueError',error_message='test result')
        worker.send(('result',result,False))
        self.assertGreater(worker.last_payload_bytes,4*parent.last_payload_bytes+CHUNK)
        self.assertLessEqual(max(map(len,pipe.items)),CHUNK)
        self.assertEqual(parent.recv(),('result',result,False))
        self.assertFalse(pipe.items)

    def test_received_payload_over_budget_rejected_before_body(self):
        """核已授予预算在读主体前生效。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        pipe,parent,worker=self.channels('fast',1024)
        pipe.items.append(struct.pack('!4sBBQ',b'CCP1',2,0,1025))
        with self.assertRaises(ControlProtocolError):worker.recv()

    def test_legal_large_memory_plan_exceeds_sixteen_mib(self):
        """核大于16MiB的当前合法内存计划仍能恢复相同身份。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis import AnalysisPlan
        from chronaxis.batch import BatchJob
        from chronaxis.batch.process_transport import job_packet,restore_job
        from test_start_end_runner import start_end_config
        from chronaxis.planning.config_groups import public_configuration
        raw=public_configuration(start_end_config())
        raw['metadata']['data_kind']='synthetic-'+'x'*(17*1024*1024)
        raw['execution']['memory_budget_bytes']=2*1024**3
        plan=AnalysisPlan.from_dict(raw)
        pipe,parent,worker=self.channels('batch',None)
        parent.send(('run',job_packet(BatchJob('large',plan)),'out','reference'))
        self.assertGreater(parent.last_payload_bytes,16*1024*1024)
        restored=restore_job(worker.recv()[1])
        self.assertEqual(restored.plan.identity,plan.identity)
        self.assertEqual(restored.plan.raw_config['metadata']['data_kind'],raw['metadata']['data_kind'])
        self.assertFalse(pipe.items)



class ControlFixedShapeTests(unittest.TestCase):
    """以合成输入验证固定协议；各用例独立构造，无共享状态或真实日志。"""
    def test_raw_csv_layout_roundtrip(self):
        """核原始CSV列映射和进制声明往返。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.sources.raw_csv import CANCSVSpec,CSVTimeSpec
        from chronaxis.sources.raw_csv_layout import CANCSVLayout,ColumnMapping
        fields={'timestamp':ColumnMapping(column=1),'frame_id':ColumnMapping(column=2),
            'data':ColumnMapping(column=3),'payload_length':ColumnMapping(column=4),
            'channel':ColumnMapping(fixed=0),'is_rx':ColumnMapping(column='direction',value_map={'R':True,'T':False}),
            'is_extended':ColumnMapping(fixed=False),'is_fd':ColumnMapping(fixed=False),
            'frame_kind':ColumnMapping(fixed='data')}
        item=CANCSVSpec(Path('raw.csv'),CANCSVLayout(fields),CSVTimeSpec(),id_base='auto')
        source=CANTextSpec('bus',(item,),Path('x.dbc'),0,TimebaseSpec('clock',TimeType.RELATIVE,'clock'))
        self.assertEqual(restore_source(pack_source(source)),source)

    def test_rebuild_context_roundtrip(self):
        """核帧重建规则及两个开关保持原义。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis._control_models import pack_frame_context,restore_frame_context
        from chronaxis.results.frame_patch import FrameRebuildRule
        value=((FrameRebuildRule(0,0x100,('Voltage',),False,False,('Counter',),'last_by_sequence'),),True,False)
        self.assertEqual(restore_frame_context(pack_frame_context(value)),value)

    def test_unknown_model_fields_and_object_tags_rejected(self):
        """核模型未知字段拒绝且普通文字标签不恢复对象。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis._control_models import restore_source,check_fast_spec
        source=CANTextSpec('bus',(ASCSpec(Path('x.asc')),),Path('x.dbc'),0,TimebaseSpec('clock',TimeType.RELATIVE,'clock'))
        packet=pack_source(source)
        packet['__class__']='os.system'
        with self.assertRaises(ValueError):restore_source(packet)
        with self.assertRaises(ValueError):check_fast_spec({'__class__':'os.system'})
        # 未知对象标签仅可成为普通配置文字；没有任何恢复代码会调用其内容。
        self.assertEqual(decode_json(b'{"__class__":"os.system"}'),{'__class__':'os.system'})

    def test_long_chinese_diagnostics_stay_bounded(self):
        """核长中文错误的JSON转义不会突破小消息额度。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        pipe,parent,worker=ControlCodecTests().channels('can')
        worker.send(('error','ValueError','错误'*200000))
        reply=parent.recv()
        self.assertEqual(reply[0],'error')
        self.assertIn('诊断已截断',reply[2])
        self.assertLess(worker.last_payload_bytes,CHUNK)
        pipe,parent,worker=ControlCodecTests().channels('batch',None)
        worker.send(('cleanup_failed',tuple('关闭失败'*10000 for _ in range(20))))
        message=parent.recv()
        self.assertEqual(len(message[1]),16)
        self.assertLess(worker.last_payload_bytes,CHUNK)



class ControlFrameCountTests(unittest.TestCase):
    """以合成输入验证固定协议；各用例独立构造，无共享状态或真实日志。"""
    def test_fast_batch_rows_are_fixed_models(self):
        """可选总量行只接受已有固定字段，不恢复任意树或对象标签。

        参数: 无。
        返回: None，合法结果的数值和空值原样返回。
        异常: 断言失败或被测接口意外错误。
        """
        pipe,parent,worker=ControlCodecTests().channels('batch',None)
        outcome=dict(job_id='file',status='failed',error_type='test',error_message='test')
        rows=[dict(name='charge',unit='J',value=100.0,status='complete',reason=None),
              dict(name='discharge',unit='J',value=None,status='indeterminate',reason='no_target_frames')]
        worker.send(('fast_result',outcome,False,rows))
        self.assertEqual(parent.recv()[3],rows)
        for bad in ({'__class__':'arbitrary'},[dict(rows[0],extra=1)],
                    [dict(rows[0],value=True)],[dict(rows[0],reason='made_up')]):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                worker.send(('fast_result',outcome,False,bad))

    def test_small_control_is_one_bounded_pipe_write(self):
        """核小控制通知只产生一次有界管道写入。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        pipe,parent,worker=ControlCodecTests().channels('can')
        parent.send(('next',))
        self.assertEqual(len(pipe.items),1)
        self.assertLessEqual(len(pipe.items[0]),CHUNK)
        self.assertEqual(worker.recv(),('next',))
