"""按需从同次DBC取得报文周期；手写100ms真值，不重解码或回退周期。"""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,PropertyMock
import unittest

from chronaxis.legacy.dbc_cycles import cycle_time_ns,require_cycle_fields
from chronaxis.legacy.worker import _field_metadata
from chronaxis.legacy.records import LegacyCANRequest,LegacyCANField
from chronaxis.legacy.batch_read import LegacyCANBatchRead
from chronaxis.core.record_intervals import RecordIntervals
from chronaxis.sources.text_can_spec import CANTextSpec
from chronaxis.sources.text_can_decode import CANTextDecodeRead
from chronaxis.sources.protocol import SourceReadError
from chronaxis.results.budget import ResourceBudget
from chronaxis.timebase.conversion import TimeOverflowError
import test_raw_can_continuous as fixtures


class DBCCycleTests(unittest.TestCase):
    """只检查显式请求的报文周期；普通读取不要求DBC含周期。"""

    setUp=fixtures.RawCANContinuousTests.setUp
    asc=fixtures.RawCANContinuousTests.asc
    csv=fixtures.RawCANContinuousTests.csv
    blf=fixtures.RawCANContinuousTests.blf

    def with_cycle(self,value=100):
        """添加报文周期属性。参数: value毫秒。返回: None。异常: I/O错误。"""
        with self.dbc.open('a',encoding='utf-8') as stream:
            stream.write('BA_DEF_ BO_ "GenMsgCycleTime" INT 0 100000;\n'
                f'BA_ "GenMsgCycleTime" BO_ 256 {value};\n')

    def test_numeric_conversion_is_exact_and_rejects_invalid(self):
        """毫秒准确转ns，不将零/缺失/浮点误差变默认值。参数: 无。返回: None。异常: 断言失败。"""
        for value,expected in ((100,100_000_000),(0.1,100_000),(0.000001,1)):
            self.assertEqual(cycle_time_ns(value),expected)
        for value in (None,0,-1,float('inf'),float('nan'),0.0000001):
            with self.assertRaises(ValueError):cycle_time_ns(value)
        for value in (True,'100',[],{}):
            with self.assertRaises(TypeError):cycle_time_ns(value)
        with self.assertRaises(TimeOverflowError):cycle_time_ns(10**20)

    def test_one_message_cycle_is_read_once_and_only_on_request(self):
        """同帧两字段只取一次周期；普通元数据不访问周期属性。参数: 无。返回: None。异常: 断言失败。"""
        signal1=SimpleNamespace(name='Voltage',unit='V')
        signal2=SimpleNamespace(name='Mode',unit='')
        class Message:
            """有限DBC替身，仅周期属性有访问计数。"""
            frame_id=256;name='Frame';is_extended_frame=False;is_fd=False
            signals=(signal1,signal2)
        db=SimpleNamespace(messages=[Message()])
        second=replace(self.field,signal='Mode')
        with patch.object(Message,'cycle_time',new_callable=PropertyMock,create=True,return_value=100) as period:
            plain=_field_metadata(db,(self.field,second))
            self.assertEqual(period.call_count,0)
            self.assertTrue(all('cycle_ns' not in x for x in plain))
            facts=_field_metadata(db,(self.field,second),cycle_fields=(self.field,second))
            self.assertEqual(period.call_count,1)
            self.assertEqual([f['cycle_ns'] for f in facts],[100_000_000,100_000_000])
        db.messages.append(Message())
        with self.assertRaisesRegex(ValueError,'不唯一'):
            _field_metadata(db,(self.field,),cycle_fields=(self.field,))

    def test_three_formats_read_same_cycle_without_extra_value_decode(self):
        """BLF/ASC/CSV同一DBC得到100ms，纯周期请求不增加所需值。参数: 无。返回: None。异常: 断言失败。"""
        self.with_cycle()
        blf=self.blf([(0,b'\x01\x05'),(1,b'\x03\x06')])
        read=LegacyCANBatchRead(LegacyCANRequest(blf,self.dbc,()),self.budget,
            decode_scope='requested',decode_frame_ids=(256,),cycle_fields=(self.field,),batch_rows=1)
        try:
            read.start()
            self.assertEqual(read.metadata['fields'][0]['cycle_ns'],100_000_000)
            clock=RecordIntervals(read.metadata['fields'][0]['cycle_ns'])
            steps=[]
            for batch in read:
                if batch.start_sequence == 0:
                    self.assertEqual(read._exchange({'op':'status'})['parse_calls'],0)
                for record in batch.records:
                    self.assertEqual(dict(record.values),{})
                    steps.append(clock.advance(round(record.frame.timestamp*10**9)))
            self.assertEqual(steps,[None,100_000_000])
        finally:read.close()
        self.assertEqual(self.budget.ram_bytes,0)
        for parser in (self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n'),
                       self.csv('0,100,01 05,2\n1,100,03 06,2\n')):
            read=CANTextDecodeRead(CANTextSpec('bus',(parser,),self.dbc,0,self.timebase,'strict'),
                self.budget,(),cycle_fields=(self.field,))
            try:
                read._start()
                self.assertEqual(read.metadata['fields'][0]['cycle_ns'],100_000_000)
                with patch.object(type(read._db.get_message_by_frame_id(256)),'cycle_time',new_callable=PropertyMock,
                        side_effect=AssertionError('初始化后不得逐帧查询周期')):
                    list(read)
                self.assertEqual(read.decode_calls,0)
            finally:read.close()
            self.assertEqual(self.budget.ram_bytes,0)

    def test_missing_cycle_fails_before_first_frame_and_does_not_affect_default(self):
        """未选DBC周期仍可读；选择缺失周期则不开始PULL并关闭资源。参数: 无。返回: None。异常: 断言失败。"""
        blf=self.blf([(0,b'\x01\x05')])
        request=LegacyCANRequest(blf,self.dbc,(self.field,))
        for cycles in ((),(self.field,)):
            read=LegacyCANBatchRead(request,self.budget,cycle_fields=cycles)
            try:
                if cycles:
                    with self.assertRaisesRegex(SourceReadError,'cycle_time'):read.start()
                    self.assertEqual(read.counters['pulls_issued'],0)
                else:
                    read.start();self.assertNotIn('cycle_ns',read.metadata['fields'][0]);list(read)
            finally:read.close()
            self.assertEqual(self.budget.ram_bytes,0)
        parser=self.asc('0 1 100 Rx d 2 01 05\n')
        read=CANTextDecodeRead(CANTextSpec('bus',(parser,),self.dbc,0,self.timebase),
            self.budget,(self.signal,),cycle_fields=(self.field,))
        try:
            with self.assertRaisesRegex(ValueError,'cycle_time'):next(read)
            self.assertEqual(read.count,0)
        finally:read.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_cycle_identity_and_channel_are_not_guessed(self):
        """DBC身份不符、重复和错误通道拒绝，不取第一个候选。参数: 无。返回: None。异常: 断言失败。"""
        for fields in ((self.field,self.field),(replace(self.field,channel=1),)):
            with self.assertRaises(ValueError):require_cycle_fields(fields,0)
        with self.assertRaises(TypeError):require_cycle_fields([self.field])
        self.with_cycle()
        import cantools
        db=cantools.database.load_file(str(self.dbc))
        wrong=replace(self.field,signal='Wrong')
        with self.assertRaisesRegex(ValueError,'信号'):_field_metadata(db,(wrong,),cycle_fields=(wrong,))
        other=LegacyCANField(0,'Other',257,False,False)
        with self.assertRaisesRegex(ValueError,'cycle_time'):_field_metadata(db,(other,),cycle_fields=(other,))

    def test_adapters_forward_only_requested_cycle_metadata(self):
        """实际适配器交付同次周期，默认路径仍不带周期。参数: 无。返回: None。异常: 断言失败。"""
        from uuid import uuid4
        from chronaxis.sources.can_spec import LegacyCANSpec
        from chronaxis.sources.models import ReadRequest
        from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
        from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
        self.with_cycle()
        blf=self.blf([(0,b'\x01\x05')])
        parsers=(self.asc('0 1 100 Rx d 2 01 05\n'),self.csv('0,100,01 05,2\n'))
        for parser in (None,*parsers):
            if parser is None:
                spec=LegacyCANSpec('bus',blf,self.dbc,0,self.timebase,offset_ns=-1700000000*10**9)
                adapter=BudgetedLegacyCANSourceAdapter(self.budget,spec,'session',(self.signal,),
                    work_dir=self.root/uuid4().hex,retain_raw_frames=False,cycle_fields=(self.field,))
            else:
                adapter=BudgetedTextCANSourceAdapter(self.budget,
                    CANTextSpec('bus',(parser,),self.dbc,0,self.timebase),'session',(self.signal,),
                    cycle_fields=(self.field,))
            read=adapter.iter_batches(ReadRequest('session',(),0,2*10**9,2))
            try:
                list(read)
                self.assertEqual(read.runtime_metadata['fields'][0]['cycle_ns'],100_000_000)
            finally:read.close();adapter.close()
            self.assertEqual(self.budget.ram_bytes,0)

    def test_ready_rejects_missing_unrequested_and_invalid_cycle_metadata(self):
        """新READY必须与周期请求一致，不能凭空接受或忽略周期字段。参数: 无。返回: None。异常: 断言失败。"""
        from chronaxis.planning.checks import json_value
        self.with_cycle()
        blf=self.blf([(0,b'\x01\x05')])
        read=LegacyCANBatchRead(LegacyCANRequest(blf,self.dbc,(self.field,)),self.budget,
            cycle_fields=(self.field,))
        try:
            read.start()
            for bad in (None,0,-1,True,100.0,2**63):
                packet=json_value(read.metadata)
                if bad is None:packet['fields'][0].pop('cycle_ns')
                else:packet['fields'][0]['cycle_ns']=bad
                with self.assertRaisesRegex(SourceReadError,'周期'):read._check_ready(packet)
            packet=json_value(read.metadata);packet['cycle_fields']=[]
            with self.assertRaisesRegex(SourceReadError,'周期请求'):read._check_ready(packet)
        finally:read.close()
        self.assertEqual(self.budget.ram_bytes,0)


if __name__=='__main__':unittest.main()
