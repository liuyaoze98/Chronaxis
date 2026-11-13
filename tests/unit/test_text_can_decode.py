"""用同组真实编码的小文件核对文本CAN解码、原行引用和资源生命周期。

合成DBC的电压为raw*2+1，预期数值由手算确定；BLF对照调用既有真实适配器，
不以文本解码结果作为自身真值。所有输出写work，原快照与冻结vendor只读。
本组验低层C1；公共计划/导出配置的接线在C2单独验证。
"""

from configuration_fixtures import current_fixture

from dataclasses import replace
from pathlib import Path
import json
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.legacy.records import LegacyCANField
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.codec import _pack, _unpack
from chronaxis.results.errors import BudgetExceededError
from chronaxis.sources.asc import ASCSpec
from chronaxis.sources.can_spec import LegacyCANSpec
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.raw_can import CANTextError
from chronaxis.sources.raw_csv import CANCSVSpec, CSVTimeSpec
from chronaxis.sources.raw_csv_layout import CANCSVLayout, ColumnMapping
from chronaxis.sources.text_can_spec import CANTextSpec
from chronaxis.sources.text_can_ref import CANTextSourceRef
from chronaxis.sources.text_can_decode import CANTextDecodeRead, pack_text_records


class TextCANDecodeTests(unittest.TestCase):
    """每例独立文件与预算，不继承上次读取的DBC、时间或信号缓存。"""

    def setUp(self):
        """建立两字节合成DBC。参数: 无。返回: None。异常: 工作目录I/O或可选依赖缺失。
        """
        # 测试需要真正解码库；缺依赖不能以空桩冒充成功。
        import cantools
        self.root = Path('work/m3-input-home-20261023/text-decode-tests')/uuid4().hex
        self.root.mkdir(parents=True)
        self.dbc = self.root/'fixture.dbc'
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 2 Node\n SG_ Voltage : 0|8@1+ (2,1) [0|511] "V" Node\n'
            ' SG_ Mode : 8|8@1+ (1,0) [0|255] "" Node\n'
            'BO_ 257 Other: 1 Node\n SG_ Other : 0|8@1+ (1,0) [0|255] "" Node\n',encoding='utf-8')
        self.timebase = TimebaseSpec('clock',TimeType.RELATIVE,'synthetic')
        self.field = LegacyCANField(0,'Voltage',256,False,False)
        self.signal = SignalDefinition('voltage','bus',self.field.key,SignalDType.FLOAT64,'V',10**10,
                                       input_unit='V',same_time_policy='last_by_sequence')
        self.budget = ResourceBudget()

    def asc(self, body, **options):
        """写标准ASC帧体。参数: body文本、options解析声明。返回: ASCSpec。异常: I/O或声明错。
        """
        path = self.root/(uuid4().hex+'.asc')
        path.write_text('base hex timestamps absolute\n'+body,encoding='utf-8')
        return ASCSpec(path,**options)

    def csv(self, body):
        """写四列原始CSV。参数: body为秒/ID/载荷/长度。返回: CANCSVSpec。异常: I/O或映射错。
        """
        path = self.root/(uuid4().hex+'.csv')
        path.write_text('time,id,data,length\n'+body,encoding='utf-8')
        fields = {name:ColumnMapping(column=index) for index,name in enumerate(
            ('timestamp','frame_id','data','payload_length'),1)}
        # 其他身份固定声明，不按ID大小或文件名猜测。
        fields.update({name:ColumnMapping(fixed=value) for name,value in (
            ('channel',0),('is_rx',True),('is_extended',False),('is_fd',False),('frame_kind','data'))})
        return CANCSVSpec(path,CANCSVLayout(fields),CSVTimeSpec(),id_base=16)

    def reader(self, inputs, *, signals=None, **options):
        """构造本例解码owner。参数: inputs解析器tuple、signals可覆盖、options读取参数。返回: reader。异常: 声明/预算错。
        """
        return CANTextDecodeRead(CANTextSpec('bus',inputs,self.dbc,0,self.timebase),self.budget,
                                 (self.signal,) if signals is None else signals,**options)

    def test_construction_is_static_and_mixed_formats_rejected(self):
        """创建声明不访问任何输入，混格式连续文件预先拒绝。参数: 无。返回: None。异常: 断言失败。
        """
        asc,csv = ASCSpec(self.root/'absent.asc'),self.csv('')
        with patch.object(Path,'open',side_effect=AssertionError('不应打开')):
            reader = self.reader((asc,))
            self.assertEqual(reader.count,0)
            reader.close()
        with self.assertRaises(ValueError):
            self.reader((asc,csv))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_precise_time_scaling_trace_codec_and_both_backends(self):
        """DBC缩放一次、额外显式转换一次；纳秒/同刻帧与原行完整保存。参数: 无。返回: None。异常: 断言失败。
        """
        for parser in (self.asc('0.000000001 1 100 Rx d 2 01 05\n0.000000001 1 100 Rx d 2 03 06\n'),
                       self.csv('0.000000001,100,01 05,2\n0.000000001,100,03 06,2\n')):
            with self.reader((parser,)) as reader:
                records = tuple(reader)
                self.assertEqual(reader.decode_calls,2)
                self.assertTrue(reader.exhausted)
                self.assertFalse(reader.closed)
                self.assertEqual(reader.metadata['profile'],'can-text-v1')
                self.assertGreater(self.budget.ram_bytes,0)
                for backend in ('reference','numpy'):
                    definition = replace(self.signal,unit='mV',scale=1000)
                    series = pack_text_records(definition,records,'session',backend)
                    self.assertEqual(series.time_ns.tolist(),[1,1])
                    self.assertEqual(series.values.tolist(),[3000.0,7000.0])
                    self.assertEqual(series.original_values,(3,7))
                    self.assertEqual(series.sequence.tolist(),[0,1])
                    self.assertEqual([r.line_number for r in series.source_ref],[2,3])
                    self.assertEqual([r.raw_time for r in series.source_ref],['0.000000001']*2)
                    self.assertTrue(all(type(r) is CANTextSourceRef for r in series.source_ref))
                    self.assertEqual(_unpack(_pack(series.source_ref)),series.source_ref)
            self.assertEqual(self.budget.ram_bytes,0)

    def test_unknown_unselected_remote_preserved_and_no_extra_decode(self):
        """未知/未选/远程帧原样交付，只选中帧调用解码一次且多个别名不重复解码。参数: 无。返回: None。异常: 断言失败。
        """
        from cantools.database.can.message import Message
        parser = self.asc('0 1 777 Rx d 1 ff\n1 1 101 Rx d 2 00 00\n'
                          '2 1 100 Rx r 2\n3 1 100 Rx d 2 01 05\n')
        alias = replace(self.signal,name='second')
        original = Message.decode
        with patch.object(Message,'decode',autospec=True,side_effect=original) as decode:
            with self.reader((parser,),signals=(self.signal,alias)) as reader:
                rows = tuple(reader)
                self.assertEqual([r.status for r in rows],['unknown','unselected','non_data','decoded'])
                self.assertEqual(decode.call_count,1)
                self.assertEqual(len(rows[-1].values),1)
                self.assertEqual((reader.count,reader.first_ns,reader.last_ns),(4,0,3*10**9))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_selected_bad_length_is_located_failure(self):
        """CAN合法但不满足所选DBC长度时定位原文件物理行，不能转unknown。参数: 无。返回: None。异常: 断言失败。
        """
        parser = self.asc('0 1 100 Rx d 1 01\n')
        reader = self.reader((parser,))
        with self.assertRaisesRegex(CANTextError,'长度') as context:
            next(reader)
        self.assertIn(str(parser.path),str(context.exception))
        self.assertIn('2',str(context.exception))
        self.assertTrue(reader.closed)
        self.assertFalse(reader.exhausted)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_text_history_and_leaf_codec_preserve_reference(self):
        """原行引用穿过当前内部历史及核心叶子编码，伪造历史版本拒绝。参数: 无。返回: None。异常: 断言失败。
        """
        from test_can_history import history_sample, core_values
        from chronaxis.execution.history_records import encode_record, decode_record
        from chronaxis.results.codec import _pack, _unpack
        from chronaxis.results.errors import ResultFormatError
        parser = self.csv('0.000000001,100,01 05,2\n')
        with self.reader((parser,)) as reader:
            reference = pack_text_records(self.signal,tuple(reader),'session','numpy').source_ref[0]
        sample = history_sample(reference)
        payload = encode_record(sample,65536)
        self.assertEqual(json.loads(payload)['history_version'],4)
        self.assertEqual(decode_record(payload,65536),sample)
        for value in core_values((reference,)):
            self.assertEqual(_unpack(_pack(value)),value)
        # 同一v4字节不能仅换版本就被旧解析器作为正常历史接受。
        tree = json.loads(payload)
        for version in (1,2,3):
            tree['history_version'] = version
            with self.assertRaises(ResultFormatError):
                decode_record((json.dumps(current_fixture(tree))+'\n').encode(),65536)

    def test_mux_missing_update_and_defined_decode_failure(self):
        """合法另一复用分支产生无效更新，非法分支严格报错；两者不能沿用上次值。参数: 无。返回: None。异常: 断言失败。
        """
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 2 Node\n'
            ' SG_ Selector M : 0|8@1+ (1,0) [0|255] "" Node\n'
            ' SG_ Voltage m1 : 8|8@1+ (1,0) [0|255] "V" Node\n'
            ' SG_ Other m2 : 8|8@1+ (1,0) [0|255] "" Node\n',encoding='utf-8')
        with self.reader((self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 02 09\n'),)) as reader:
            records = tuple(reader)
            for backend in ('reference','numpy'):
                series = pack_text_records(self.signal,records,'session',backend)
                self.assertEqual(series.original_values,(5,None))
                self.assertEqual(series.valid.tolist(),[True,False])
        reader = self.reader((self.asc('0 1 100 Rx d 2 03 09\n'),))
        with self.assertRaisesRegex(CANTextError,'解码失败'):
            next(reader)
        self.assertTrue(reader.closed)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_unit_mismatch_precedes_input_open(self):
        """单位不符在打开数据前拒绝，禁止猜转换倍数。参数: 无。返回: None。异常: 断言失败。
        """
        reader = self.reader((ASCSpec(self.root/'absent.asc'),),signals=(replace(self.signal,input_unit='mV',unit='mV'),))
        with self.assertRaisesRegex(ValueError,'input_unit'):
            next(reader)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_frame_type_channel_and_declared_fd_compatibility(self):
        """完整身份区分通道/帧型；已批准FD声明配经典实帧留下兼容说明。参数: 无。返回: None。异常: 断言失败。
        """
        # 用真实DBC声明FD，不改输入帧，不替换解码函数或真实加载过程。
        with self.dbc.open('a',encoding='utf-8') as stream:
            stream.write('BA_DEF_ BO_ "VFrameFormat" ENUM "StandardCAN","StandardCAN_FD";\n'
                         'BA_ "VFrameFormat" BO_ 256 1;\n')
        parser = self.asc('0 2 100 Rx d 2 01 05\n1 1 100x Rx d 2 01 05\n'
            '2 CANFD 1 Rx 100 1 0 2 2 01 05\n3 1 100 Rx d 2 01 05\n')
        with self.reader((parser,)) as reader:
            rows = tuple(reader)
            self.assertEqual([r.status for r in rows],['unselected','unselected','unselected','decoded'])
            self.assertIn('compat',str(reader.metadata['fields']))
        definition = replace(self.signal,field=replace(self.field,is_fd=True).key)
        with self.reader((parser,),signals=(definition,)) as reader:
            rows = tuple(reader)
            self.assertEqual([r.status for r in rows],['unselected','unselected','decoded','unselected'])
            self.assertEqual(rows[2].values[0][1],3)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_continuous_files_keep_global_order_and_exact_origins(self):
        """只有显式偏移才连续，文件内序号重置而全局序号不重置。参数: 无。返回: None。异常: 断言失败。
        """
        first = self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n')
        second = self.asc('0 1 100 Rx d 2 05 07\n1 1 100 Rx d 2 07 08\n',offset_ns=2*10**9)
        with self.reader((first,second)) as reader:
            series = pack_text_records(self.signal,tuple(reader),'session','numpy')
            self.assertEqual(series.time_ns.tolist(),[0,10**9,2*10**9,3*10**9])
            self.assertEqual([(r.input_index,r.record_sequence,r.yield_sequence) for r in series.source_ref],
                             [(0,0,0),(0,1,1),(1,0,2),(1,1,3)])
        reader = self.reader((first,replace(second,offset_ns=0)))
        with self.assertRaisesRegex(CANTextError,'回退'):
            tuple(reader)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_missing_file_and_cancel_release_only_owned_budget(self):
        """打不开文件或实际取消时保留其他owner费用。参数: 无。返回: None。异常: 断言失败。
        """
        self.budget.reserve_ram(17)
        reader = self.reader((ASCSpec(self.root/'absent.asc'),))
        with self.assertRaises(FileNotFoundError):
            next(reader)
        self.assertEqual(self.budget.ram_bytes,17)
        # 取消在真正读取前触发，同样只释放自身费用。
        reader = self.reader((ASCSpec(self.root/'absent.asc'),),check_cancel=Mock(side_effect=KeyboardInterrupt('取消')))
        with self.assertRaises(KeyboardInterrupt):
            next(reader)
        self.assertEqual(self.budget.ram_bytes,17)
        self.budget.release_ram(17)

    def test_budget_failure_before_loading_dbc(self):
        """固定声明够用但DBC费用不够时不加载库对象。参数: 无。返回: None。异常: 断言失败。
        """
        self.budget = ResourceBudget(memory_budget_bytes=512*1024)
        reader = self.reader((ASCSpec(self.root/'absent.asc'),))
        with patch('cantools.database.load',side_effect=AssertionError('不应加载')):
            with self.assertRaises(BudgetExceededError):
                next(reader)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_persistent_release_failure_exposes_retryable_owner(self):
        """资源释放持续失败保原文件错误和恢复owner，恢复后可清账。参数: 无。返回: None。异常: 断言失败。
        """
        reader = self.reader((ASCSpec(self.root/'absent.asc'),))
        with patch.object(self.budget,'release_ram',side_effect=OSError('账本暂不可用')):
            with self.assertRaises(FileNotFoundError) as context:
                next(reader)
        self.assertIs(context.exception.text_can_cleanup_owner,reader)
        self.assertFalse(reader.closed)
        reader.close()
        reader.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_blf_asc_csv_same_known_frames_have_same_signal(self):
        """同组BLF/ASC/CSV经各自真实入口，值/时间/质量与手算一致。参数: 无。返回: None。异常: 断言或真实读取错。
        """
        import can
        from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
        blf = self.root/'same.blf'
        writer = can.BLFWriter(blf)
        try:
            for second,payload in ((0,b'\x01\x05'),(1,b'\x03\x06'),(1,b'\x05\x07'),(2,b'\x07\x08')):
                writer.on_message_received(can.Message(timestamp=1700000000.0+second,arbitration_id=256,
                    is_extended_id=False,channel=0,data=payload))
        finally:
            writer.stop()
        spec = LegacyCANSpec('bus',blf,self.dbc,0,self.timebase,offset_ns=-1700000000*10**9)
        # 旧路径真正spawn，不替换reader或decoder；仅比可表达的整数秒，精确纳秒另有上例。
        adapter = BudgetedLegacyCANSourceAdapter(self.budget,spec,'session',(self.signal,),
            work_dir=self.root/'old-read',retain_raw_frames=False)
        actual = []
        try:
            reader = adapter.iter_batches(ReadRequest('session',('voltage',),0,3*10**9,2))
            try:
                for batch in reader:
                    for series in batch.series.values():
                        actual.extend(zip(series.time_ns.tolist(),series.values.tolist(),series.valid.tolist()))
            finally:
                reader.close()
        finally:
            adapter.close()
        expected = [(0,3.0,True),(10**9,7.0,True),(10**9,11.0,True),(2*10**9,15.0,True)]
        self.assertEqual(actual,expected)
        for parser in (self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n1 1 100 Rx d 2 05 07\n2 1 100 Rx d 2 07 08\n'),
                       self.csv('0,100,01 05,2\n1,100,03 06,2\n1,100,05 07,2\n2,100,07 08,2\n')):
            with self.reader((parser,)) as reader:
                series = pack_text_records(self.signal,tuple(reader),'session','numpy')
                self.assertEqual(list(zip(series.time_ns.tolist(),series.values.tolist(),series.valid.tolist())),expected)
        self.assertEqual(self.budget.ram_bytes,0)
