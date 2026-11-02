"""同组小文件核对原序接续、解码失效及新旧政策；不读取历史项目。"""

from configuration_fixtures import current_fixture

from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
from copy import deepcopy
import json
from types import SimpleNamespace

from chronaxis.legacy.records import LegacyCANRequest
from chronaxis.legacy.batch_read import LegacyCANBatchRead
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
from chronaxis.sources.can_spec import LegacyCANSpec
from chronaxis.sources.text_can_spec import CANTextSpec
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.protocol import SourceReadError
from chronaxis.sources.raw_can import CANTextError
from chronaxis.results.errors import BudgetExceededError
import test_text_can_decode as fixtures


class RawCANContinuousTests(unittest.TestCase):
    """保留前序真实更新；既不跨文件清状态，也不把缺失更新跳过。"""

    setUp = fixtures.TextCANDecodeTests.setUp
    asc = fixtures.TextCANDecodeTests.asc
    csv = fixtures.TextCANDecodeTests.csv

    def blf(self, rows):
        """写独立BLF。参数: rows为(秒,载荷)序列。返回: Path。异常: 原写库错误。"""
        import can
        path=self.root/(uuid4().hex+'.blf')
        writer=can.BLFWriter(path)
        try:
            for second,data in rows:
                writer.on_message_received(can.Message(timestamp=1700000000.+second,
                    arbitration_id=256,is_extended_id=False,channel=0,data=data))
        finally:
            writer.stop()
        return path

    def multiplex(self):
        """建立手写复用DBC。参数: 无。返回: None。异常: I/O错误。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 2 Node\n SG_ Selector M : 0|8@1+ (1,0) [0|255] "" Node\n'
            ' SG_ Voltage m1 : 8|8@1+ (2,1) [0|511] "V" Node\n',encoding='utf-8')

    def consume(self, adapter, names=()):
        """消费一次并关闭。参数: adapter/names。返回: 每条样本引用。异常: 原读取错误。"""
        refs=[]
        try:
            read=adapter.iter_batches(ReadRequest('session',names,0,4*10**9,2))
            try:
                for batch in read:
                    for series in batch.series.values():
                        refs.extend(series.source_ref)
            finally:
                read.close()
        finally:
            adapter.close()
        return refs

    def adapter(self, paths, collect, **kwargs):
        """建立有序来源。参数: 路径、消费者、覆盖声明。返回: adapter。异常: 配置/预算。"""
        spec=LegacyCANSpec('bus',paths[0],self.dbc,0,self.timebase,
            offset_ns=-1700000000*10**9,paths=tuple(paths),decode_policy='strict',**kwargs)
        return BudgetedLegacyCANSourceAdapter(self.budget,spec,'session',(self.signal,),
            work_dir=self.root/uuid4().hex,retain_raw_frames=False,message_consumer=collect)

    def test_blf_empty_files_global_sequence_and_one_dbc_session(self):
        """跨空文件继续，原序连续，真正最后EOF才结束。参数: 无。返回: None。异常: 断言失败。"""
        paths=(self.blf([]),self.blf([(0,b'\x01\x05'),(1,b'\x03\x06')]),
               self.blf([]),self.blf([(1,b'\x05\x07'),(2,b'\x07\x08')]),self.blf([]))
        request=LegacyCANRequest(paths[0],self.dbc,(self.field,))
        read=LegacyCANBatchRead(request,self.budget,input_paths=paths,decode_policy='strict',
            decode_scope='requested',decode_frame_ids=(256,),prefetch=True,batch_rows=1)
        records=[]; indices=[]
        try:
            read.start()
            self.assertEqual(read.metadata['version'],5)
            for batch in read:
                indices.append(batch.input_index)
                records.extend((r.sequence,r.values['Voltage']) for r in batch.records)
            self.assertTrue(read.finished)
        finally:
            read.close()
        self.assertEqual(records,[(0,3),(1,7),(2,11),(3,15)])
        self.assertEqual(indices,sorted(indices))
        self.assertEqual(indices[-1],4)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_three_formats_decode_failure_is_current_invalid_update(self):
        """复用编号1/2/1产生11/None/15，不缓存前值；跨文件保持序号。参数: 无。返回: None。异常: 断言失败。"""
        self.multiplex()
        paths=(self.blf([(0,b'\x01\x05')]),self.blf([(1,b'\x02\x06'),(2,b'\x01\x07')]))
        parsers=((self.asc('0 1 100 Rx d 2 01 05\n'),self.asc('1 1 100 Rx d 2 02 06\n2 1 100 Rx d 2 01 07\n')),
                 (self.csv('0,100,01 05,2\n'),self.csv('1,100,02 06,2\n2,100,01 07,2\n')))
        for inputs in (None,*parsers):
            rows=[]
            def collect(update):
                """只保存对照标量。参数: update。返回: None。异常: 缺字段错误。"""
                rows.append((update.sequence,update.time_ns,update.values['Voltage']))
            adapter=self.adapter(paths,collect) if inputs is None else BudgetedTextCANSourceAdapter(
                self.budget,CANTextSpec('bus',inputs,self.dbc,0,self.timebase,'strict'),
                'session',(self.signal,),message_consumer=collect)
            self.consume(adapter)
            self.assertEqual(rows,[(0,0,11),(1,10**9,None),(2,2*10**9,15)])
            self.assertEqual(self.budget.ram_bytes,0)

    def test_blf_sample_references_keep_actual_file_and_backward_time_fails(self):
        """样本定位实际文件，文件切换不能掩盖回退。参数: 无。返回: None。异常: 断言失败。"""
        paths=(self.blf([(0,b'\x01\x05')]),self.blf([(1,b'\x03\x06')]))
        refs=self.consume(self.adapter(paths,None),('voltage',))
        self.assertEqual([r.path for r in refs],[str(p) for p in paths])
        self.assertEqual([r.yield_sequence for r in refs],[0,1])
        self.assertEqual(self.budget.ram_bytes,0)
        with self.assertRaisesRegex(SourceReadError,'回退'):
            self.consume(self.adapter(tuple(reversed(paths)),None),('voltage',))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_three_formats_strict_length_stops_and_partial_is_explicit(self):
        """短于DBC的完整帧仅partial可读；strict报错且退款。参数: 无。返回: None。异常: 断言失败。"""
        self.multiplex()
        blf=self.blf([(0,b'\x01')])
        parsers=(self.asc('0 1 100 Rx d 1 01\n'),self.csv('0,100,01,1\n'))
        for policy in ('strict','partial'):
            for parser in (None,*parsers):
                rows=[]
                collect=lambda update:rows.append(update.values['Voltage'])
                if parser is None:
                    spec=LegacyCANSpec('bus',blf,self.dbc,0,self.timebase,
                        offset_ns=-1700000000*10**9,decode_policy=policy)
                    adapter=BudgetedLegacyCANSourceAdapter(self.budget,spec,'session',(self.signal,),
                        work_dir=self.root/uuid4().hex,retain_raw_frames=False,message_consumer=collect)
                else:
                    adapter=BudgetedTextCANSourceAdapter(self.budget,
                        CANTextSpec('bus',(parser,),self.dbc,0,self.timebase,policy),
                        'session',(self.signal,),message_consumer=collect)
                if policy=='strict':
                    with self.assertRaisesRegex((CANTextError,SourceReadError),'长度'):
                        self.consume(adapter)
                else:
                    self.consume(adapter)
                    self.assertEqual(rows,[None])
                self.assertEqual(self.budget.ram_bytes,0)

    def test_consumer_cancel_and_missing_next_file_release_resources(self):
        """跨文件失败和消费者取消保原错误、关闭进程、退还所有费用。参数: 无。返回: None。异常: 断言失败。"""
        first=self.blf([(0,b'\x01\x05')])
        second=self.blf([(1,b'\x03\x06')])
        def cancel(update):
            """模拟消费者取消。参数: update。返回: 不返回。异常: KeyboardInterrupt。"""
            raise KeyboardInterrupt('consumer cancelled')
        with self.assertRaisesRegex(KeyboardInterrupt,'consumer cancelled'):
            self.consume(self.adapter((first,second),cancel))
        self.assertEqual(self.budget.ram_bytes,0)
        with self.assertRaises(SourceReadError):
            self.consume(self.adapter((first,self.root/'missing.blf'),None))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_current_static_paths_policy_and_rejected_old_versions(self):
        """当前结构支持有序多文件；默认strict，legacy/partial显式选择。参数: 无。返回: None。异常: 断言。"""
        from chronaxis import AnalysisPlan, PlanValidationError
        from test_plan_message_calculations import legacy_config
        from jsonschema import Draft202012Validator
        config = legacy_config()
        source = config['sources'][0]
        source.pop('reader_options', None)
        first = source.pop('path', None)
        if first is None:
            first = source.pop('paths')[0]
        source['paths'] = [first, str(Path(first).with_name('next.blf'))]
        current = AnalysisPlan.from_dict(current_fixture(config))
        self.assertEqual(tuple(path.name for path in current.sources[0].config.input_paths),
                         (Path(first).name, 'next.blf'))
        self.assertEqual(current.sources[0].config.decode_policy, 'strict')
        validator = Draft202012Validator(json.loads(Path('Docs/Schema/analysis.schema.json').read_text(encoding='utf-8')))
        validator.validate(current_fixture(config))
        for version in (1, 2):
            old = deepcopy(config)
            old['config_version'] = version
            self.assertFalse(validator.is_valid(current_fixture(old)))
            with self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(old))
        for policy in ('legacy', 'partial'):
            source['reader_options'] = {'decode_policy': policy}
            validator.validate(current_fixture(config))
            self.assertEqual(AnalysisPlan.from_dict(current_fixture(config)).sources[0].config.decode_policy, policy)
        source['paths'][1] = 'wrong.asc'
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(config))

    def test_strict_policy_does_not_swallow_structural_or_unexpected_errors(self):
        """DLC错误在partial也拒绝；预算和取消不变成缺值。参数: 无。返回: None。异常: 断言失败。"""
        from chronaxis.legacy.decode_policy import check_decode_length
        frame=SimpleNamespace(dlc=2,data=b'\x01')
        for policy in ('strict','partial'):
            with self.assertRaisesRegex(ValueError,'长度'):check_decode_length(frame,2,policy)
        from chronaxis.sources.text_can_decode import CANTextDecodeRead
        parser=self.asc('0 1 100 Rx d 2 01 05\n')
        for error in (KeyboardInterrupt('cancel'),BudgetExceededError('budget')):
            read=CANTextDecodeRead(CANTextSpec('bus',(parser,),self.dbc,0,self.timebase,'strict'),
                self.budget,(self.signal,))
            try:
                read._start()
                message = read._db.messages[0]
                with patch.object(message,'decode',side_effect=error) as decode:
                    with self.assertRaises(type(error)):next(read)
                    decode.assert_called_once_with(b'\x01\x05',
                        decode_choices=False, allow_truncated=True)
            finally:read.close()
            self.assertEqual(self.budget.ram_bytes,0)

    def test_old_text_decode_failure_still_reports_error(self):
        """显式legacy不静默改变原文本失败行为。参数: 无。返回: None。异常: 断言失败。"""
        self.multiplex()
        parser=self.asc('0 1 100 Rx d 2 02 05\n')
        adapter=BudgetedTextCANSourceAdapter(self.budget,
            CANTextSpec('bus',(parser,),self.dbc,0,self.timebase,'legacy'),'session',(self.signal,))
        with self.assertRaisesRegex(CANTextError,'解码失败'):self.consume(adapter,('voltage',))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_continuous_protocol_rejects_wrong_file_and_early_eof(self):
        """边界包不能伪造文件、退序或提前EOF；关闭退还费用。参数: 无。返回: None。异常: 断言失败。"""
        from chronaxis.legacy.batch_wire import FILE_HEADER,FILE_MAGIC,MAX_BATCH_BYTES,encode_batch
        from chronaxis.results.budget import _reserve_owned_ram
        paths=(self.root/'a.blf',self.root/'b.blf')
        request=LegacyCANRequest(paths[0],self.dbc,())
        inner=encode_batch(0,[],[],True,MAX_BATCH_BYTES-FILE_HEADER.size)
        for envelope,pattern in ((inner,'缺少文件'),
                (FILE_HEADER.pack(FILE_MAGIC,2)+inner,'越界'),
                (FILE_HEADER.pack(FILE_MAGIC,0)+inner,'最后文件前')):
            read=LegacyCANBatchRead(request,self.budget,input_paths=paths)
            try:
                read._batch_limit=MAX_BATCH_BYTES
                _reserve_owned_ram(read,MAX_BATCH_BYTES*128,'_current_cost')
                read._connection=SimpleNamespace(recv_bytes=lambda limit:envelope)
                with self.assertRaisesRegex(SourceReadError,pattern):read._receive_reply()
            finally:
                read._connection=None
                read.close()
            self.assertEqual(self.budget.ram_bytes,0)

    def test_continuous_auto_and_all_modes_keep_sequence(self):
        """新文件外壳兼容三种时间范围及all旧基础协议。参数: 无。返回: None。异常: 断言失败。"""
        paths=(self.blf([(0,b'\x01\x05')]),self.blf([(1,b'\x03\x06')]))
        for scope in ('source','selected','none','all'):
            options={} if scope=='all' else dict(decode_scope='requested',decode_frame_ids=(256,),
                input_check='auto',time_scope=scope)
            read=LegacyCANBatchRead(LegacyCANRequest(paths[0],self.dbc,(self.field,)),
                self.budget,input_paths=paths,decode_policy='strict',**options)
            rows=[]
            try:
                for batch in read:
                    rows.extend((r.sequence,r.values['Voltage']) for r in batch.records)
                    if scope=='none':self.assertEqual(batch.timestamps,())
            finally:read.close()
            self.assertEqual(rows,[(0,3),(1,7)])
            self.assertEqual(self.budget.ram_bytes,0)

    def test_optional_input_fingerprint_uses_inner_payload_only(self):
        """显式旧诊断只摘要实际时间/记录，文件包头不混入内容。参数: 无。返回: None。异常: 断言失败。"""
        import hashlib,struct
        from chronaxis.legacy.records import encode_packet,decoded_to_dict
        from chronaxis.legacy.batch_wire import LENGTH
        paths=(self.blf([(0,b'\x01\x05')]),self.blf([(1,b'\x03\x06')]))
        records=[]
        adapter=self.adapter(paths,lambda update: None)
        read=adapter.iter_batches(ReadRequest('session',(),0,2*10**9,2))
        original=read._deliver_message
        def observe(record,mapped):
            """独立编码后继续原交付。参数: 原记录/时间。返回: 原返回。异常: 原编码或交付错误。"""
            records.append(encode_packet(decoded_to_dict(record)))
            return original(record,mapped)
        read._deliver_message=observe
        try:
            list(read)
            expected=(hashlib.sha256(struct.pack('>2d',1700000000.,1700000001.)).hexdigest(),
                hashlib.sha256(b''.join(LENGTH.pack(len(r))+r for r in records)).hexdigest(),2,2)
            self.assertEqual(read.input_fingerprints,expected)
        finally:
            read.close();adapter.close()
        self.assertEqual(self.budget.ram_bytes,0)


if __name__=='__main__':
    unittest.main()
