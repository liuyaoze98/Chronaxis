"""验证原始CAN CSV真正流式读帧，独立手算时间/载荷并检查故障收尾。

合成CSV只写新项目work，多段小数按用户明确的毫秒＋微秒规则手算真值，
不声称已核实原设备协议。逐项覆盖物理行、跨行引号、预算和取消，不仅检查帧数。
"""

import csv
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError
from chronaxis.sources.raw_can import CANTextError
from chronaxis.sources.raw_csv import CANCSVSpec,CANCSVRead,CSVTimeSpec,CSVClock,MAX_CSV_RECORD_BYTES
from chronaxis.sources.raw_csv_layout import CANCSVLayout,ColumnMapping


class RawCANCSVTests(unittest.TestCase):
    """每次独立文件/预算，以原文字和规范帧两方面检查结果。"""

    def setUp(self):
        """建立合成测试目录。参数: 无。返回: None。异常: 工作目录I/O失败。
        """
        self.root = Path('work/m3-input-home-20261023/csv-tests')/uuid4().hex
        self.root.mkdir(parents=True)
        self.budget = ResourceBudget()

    def layout(self, *, fd=False, extra=None, header=True):
        """声明必要列与明确固定身份。参数: fd帧型、extra覆盖字段、header开关。返回: 布局。异常: 配置错误。
        """
        fields = {'timestamp':ColumnMapping(column=1),'frame_id':ColumnMapping(column=2),
                  'data':ColumnMapping(column=3),'payload_length':ColumnMapping(column=4),
                  'channel':ColumnMapping(fixed=0),'is_rx':ColumnMapping(fixed=True),
                  'is_extended':ColumnMapping(fixed=False),'is_fd':ColumnMapping(fixed=fd),
                  'frame_kind':ColumnMapping(fixed='data')}
        fields.update(extra or {})
        return CANCSVLayout(fields,has_header=header)

    def fixture(self, rows, *, layout=None, time=None, **options):
        """用标准CSV writer写明确合成值。参数: rows列表、layout/time声明及spec覆盖。返回: CANCSVSpec。异常: I/O/配置错。
        """
        layout = layout or self.layout()
        path = self.root/(uuid4().hex+'.csv')
        with path.open('w',encoding=layout.encoding,newline='') as stream:
            writer = csv.writer(stream,delimiter=layout.delimiter)
            if layout.has_header:
                writer.writerow(['time','name','data','length'])
            writer.writerows(rows)
        return CANCSVSpec(path,layout,time or CSVTimeSpec(),**options)

    def test_numeric_milliseconds_payload_and_location(self):
        """毫秒单位显式施加，原空白/同刻/不同帧均保留。参数: 无。返回: None。异常: 断言失败。
        """
        spec = self.fixture([[' 1.5 ','0x123','01 ff','2'],['1.5','123','80','1']],time=CSVTimeSpec(unit='ms',offset_ns=10))
        with CANCSVRead(spec,self.budget) as reader:
            records = list(reader)
        self.assertEqual([(r.time_ns,r.line_number,r.sequence) for r in records],[(1500010,2,0),(1500010,3,1)])
        self.assertEqual(records[0].raw_time,' 1.5 ')
        self.assertEqual(records[0].frame.data,b'\x01\xff')
        self.assertEqual(self.budget.ram_bytes,0)

    def test_fd_dlc_code_payload_length_and_contiguous_hex(self):
        """DLC9表示12字节，显式连续hex不按整串数字处理。参数: 无。返回: None。异常: 断言失败。
        """
        layout = self.layout(fd=True,extra={'dlc_code':ColumnMapping(fixed=9),'bitrate_switch':ColumnMapping(fixed=True)})
        spec = self.fixture([['0','123',bytes(range(12)).hex(),'12']],layout=layout,payload_style='contiguous')
        record = list(CANCSVRead(spec,self.budget))[0]
        self.assertEqual((record.frame.is_fd,record.frame.bitrate_switch,record.frame.dlc,record.dlc_code), (True,True,12,9))
        self.assertEqual(record.frame.data,bytes(range(12)))

    def test_declared_decimal_id_hex_length_and_channel_origin(self):
        """进制/通道起点都取声明，低ID也可以明确为扩展帧。参数: 无。返回: None。异常: 断言失败。
        """
        layout = self.layout(extra={'channel':ColumnMapping(fixed=1),'is_extended':ColumnMapping(fixed=True)})
        spec = self.fixture([['5','291','ac ca','0x02']],layout=layout,time=CSVTimeSpec(unit='ns'),
                            id_base=10,length_base=16,channel_origin=1)
        record = list(CANCSVRead(spec,self.budget))[0]
        self.assertEqual((record.time_ns,record.frame.channel,record.frame.arbitration_id,
                          record.frame.is_extended_id,record.frame.data),(5,0,0x123,True,b'\xac\xca'))

    def test_code_only_fd_and_inconsistent_code_reject(self):
        """仅DLC列也可解析，但编码与真实字节必须一致。参数: 无。返回: None。异常: 断言失败。
        """
        fields = dict(self.layout(fd=True).fields)
        fields.pop('payload_length')
        fields['dlc_code'] = ColumnMapping(column=4)
        layout = CANCSVLayout(fields)
        spec = self.fixture([['0','123',' '.join(['ff']*12),'9']],layout=layout)
        self.assertEqual(list(CANCSVRead(spec,self.budget))[0].frame.dlc,12)
        invalid = self.fixture([['0','123',' '.join(['ff']*8),'9']],layout=layout)
        with self.assertRaisesRegex(CANTextError,'DLC'):
            list(CANCSVRead(invalid,self.budget))

    def test_remote_requested_dlc_and_error_frame(self):
        """远程请求DLC和实际空载荷分别解释。参数: 无。返回: None。异常: 断言失败。
        """
        remote = self.layout(extra={'frame_kind':ColumnMapping(fixed='remote'),'dlc_code':ColumnMapping(fixed=8)})
        spec = self.fixture([['0','123','','0']],layout=remote)
        record = list(CANCSVRead(spec,self.budget))[0]
        self.assertEqual((record.frame.is_remote_frame,record.frame.dlc,record.frame.data), (True,8,b''))
        error = self.layout(extra={'frame_kind':ColumnMapping(fixed='error')})
        record = list(CANCSVRead(self.fixture([['0','0','','0']],layout=error),self.budget))[0]
        self.assertTrue(record.frame.is_error_frame)
        self.assertIsNone(record.dlc_code)

    def test_clock_midnight_requires_explicit_threshold(self):
        """只有明确的大幅回退规则才跨午夜，小乱序仍拒绝。参数: 无。返回: None。异常: 断言失败。
        """
        clock = CSVClock(CSVTimeSpec(format='clock',rollover_min_drop_ns=12*3600*10**9))
        self.assertEqual(clock.parse('23:59:59.9')[0],86399900000000)
        self.assertEqual(clock.parse('00:00:00.1')[0],86400100000000)
        with self.assertRaisesRegex(ValueError,'回退'):
            clock.parse('00:00:00.0')
        plain = CSVClock(CSVTimeSpec(format='clock'))
        plain.parse('23:59:59')
        with self.assertRaisesRegex(ValueError,'回退'):
            plain.parse('00:00:00')

    def test_iso_timezone_and_multidot_requires_explicit_mode(self):
        """不借用电脑时区，普通clock不自动接受多段格式。参数: 无。返回: None。异常: 断言失败。
        """
        iso = CSVClock(CSVTimeSpec(format='iso8601',timezone_offset_minutes=480))
        self.assertEqual(iso.parse('1970-01-01T08:00:00.000000001')[0],1)
        with self.assertRaises(ValueError):
            CSVClock(CSVTimeSpec(format='iso8601')).parse('1970-01-01T08:00:00')
        with self.assertRaisesRegex(ValueError,'多段小数'):
            CSVClock(CSVTimeSpec(format='clock')).parse('14:05:40.151.2')

    def test_clock_ms_us_keeps_units_not_decimal_digit_concatenation(self):
        """.151.2是151ms加2us，位数不改变各段单位。参数: 无。返回: None。异常: 断言失败。
        """
        # 每个期望值由整数毫秒/微秒手算，不调用产品转换函数作参考。
        clock = CSVClock(CSVTimeSpec(format='clock-ms-us-v1',offset_ns=7))
        self.assertEqual(clock.parse('14:05:40.151.2'),(50740151002007,False))
        self.assertEqual(clock.parse('14:05:40.151.3'),(50740151003007,False))
        for text in ('00:00:00.1.2','00:00:00.001.002'):
            self.assertEqual(CSVClock(CSVTimeSpec(format='clock-ms-us-v1')).parse(text),(1002000,False))
        self.assertEqual(CSVClock(CSVTimeSpec(format='clock-ms-us-v1')).parse('00:00:00.999.999'),(999999000,False))

    def test_clock_ms_us_ranges_midnight_and_failed_state(self):
        """日内范围严格检查，只有声明阈值才跨午夜，失败不提交状态。参数: 无。返回: None。异常: 断言失败。
        """
        clock = CSVClock(CSVTimeSpec(format='clock-ms-us-v1',rollover_min_drop_ns=12*3600*10**9))
        self.assertEqual(clock.parse('23:59:59.999.999')[0],86399999999000)
        self.assertEqual(clock.parse('00:00:00.0.1')[0],86400000001000)
        # 错误输入不能把日期、最近时刻或偏移推进到一半。
        for text in ('00:00:00.1000.0','00:00:00.0.1000','24:00:00.0.0',
                     '00:60:00.0.0','00:00:60.0.0','00:00:00.151','00:00:00.-1.0'):
            with self.subTest(text=text),self.assertRaises(ValueError):
                clock.parse(text)
        self.assertEqual(clock.parse('00:00:00.0.2')[0],86400000002000)
        plain = CSVClock(CSVTimeSpec(format='clock-ms-us-v1'))
        plain.parse('23:59:59.999.999')
        with self.assertRaisesRegex(ValueError,'回退'):
            plain.parse('00:00:00.0.0')
        with self.assertRaises(ValueError):
            CSVTimeSpec(format='clock-ms-us-v1',unit='ms')

    def test_clock_ms_us_reader_retains_original_text(self):
        """原时间文字带空格仍保留，纳秒时间按显式模式解释。参数: 无。返回: None。异常: 断言失败。
        """
        spec = self.fixture([[' 14:05:40.151.2 ','123','80','1']],time=CSVTimeSpec(format='clock-ms-us-v1'))
        with CANCSVRead(spec,self.budget) as reader:
            record = next(reader)
        self.assertEqual((record.time_ns,record.raw_time,record.time_quantized),
                         (50740151002000,' 14:05:40.151.2 ',False))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_time_failure_keeps_previous_clock_state(self):
        """偏移溢出后不提交半个时间状态。参数: 无。返回: None。异常: 断言失败。
        """
        clock = CSVClock(CSVTimeSpec(format='clock',offset_ns=2**63-1))
        self.assertEqual(clock.parse('00:00:00')[0],2**63-1)
        with self.assertRaises(OverflowError):
            clock.parse('00:00:00.000000001')
        self.assertEqual(clock.parse('00:00:00')[0],2**63-1)
        for value in (True,0.1):
            with self.assertRaises(ValueError):
                CSVClock(CSVTimeSpec()).parse(value)

    def test_quoted_multiline_record_preserves_start_physical_line(self):
        """一条带引号记录跨两行，下一条位置不按记录号冒充。参数: 无。返回: None。异常: 断言失败。
        """
        spec = self.fixture([['0','123','01\nff','2'],['1','123','80','1']])
        records = list(CANCSVRead(spec,self.budget))
        self.assertEqual([(r.line_number,r.frame.data) for r in records],[(2,b'\x01\xff'),(4,b'\x80')])

    def test_bad_rows_stop_without_replay(self):
        """坏ID/载荷/长度/时间不能被跳过或补齐。参数: 无。返回: None。异常: 断言失败。
        """
        bad = [['1','0x800','','0'],['1','123','ff','2'],['1','123','fg','1'],
               ['1','123','ff ff ff ff ff ff ff ff ff','9'],['-1','123','','0'],['1','123','0x01','1']]
        for row in bad:
            with self.subTest(row=row):
                reader = CANCSVRead(self.fixture([['0','123','','0'],row]),self.budget)
                next(reader)
                with self.assertRaises(CANTextError) as caught:
                    next(reader)
                self.assertEqual((caught.exception.line_number,reader.count),(3,1))
                self.assertEqual(list(reader),[])
                self.assertEqual(self.budget.ram_bytes,0)

    def test_encoding_syntax_and_record_size_fail_with_location(self):
        """错误引号和跨行无限累积都必须有界失败。参数: 无。返回: None。异常: 断言失败。
        """
        spec = self.fixture([])
        for raw,number in ((b'time,id,data,length\n\xff\n',2),
                           (b'time,id,data,length\n"0,123,ff,1\n',2),
                           (b'time,id,data,length\n"'+b'x'*MAX_CSV_RECORD_BYTES,2)):
            with self.subTest(size=len(raw)):
                spec.path.write_bytes(raw)
                with self.assertRaises(CANTextError) as caught:
                    list(CANCSVRead(spec,self.budget))
                self.assertEqual(caught.exception.line_number,number)
                self.assertEqual(self.budget.ram_bytes,0)

    def test_eof_missing_header_and_explicit_skip_rows(self):
        """空输入与缺少声明头/跳过记录的错误分开。参数: 无。返回: None。异常: 断言失败。
        """
        empty = self.fixture([],layout=self.layout(header=False))
        self.assertEqual(list(CANCSVRead(empty,self.budget)),[])
        with self.assertRaisesRegex(CANTextError,'表头'):
            list(CANCSVRead(replace(empty,layout=self.layout()),self.budget))
        skipped = replace(empty,layout=replace(empty.layout,skip_rows=1))
        with self.assertRaisesRegex(CANTextError,'跳过'):
            list(CANCSVRead(skipped,self.budget))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_explicit_skip_and_early_close_do_not_continue_reading(self):
        """只跳过声明记录，提前关闭后不读后继。参数: 无。返回: None。异常: 断言失败。
        """
        spec = self.fixture([['0','123','','0'],['1','123','','0']])
        spec.path.write_bytes(b'banner\n'+spec.path.read_bytes())
        spec = replace(spec,layout=replace(spec.layout,skip_rows=1))
        reader = CANCSVRead(spec,self.budget)
        self.assertEqual(next(reader).line_number,3)
        reader.close(); reader.close()
        self.assertEqual(list(reader),[])
        self.assertEqual((reader.count,self.budget.ram_bytes),(1,0))

    def test_budget_cancellation_and_persistent_cleanup_owner(self):
        """预算先申请，取消原错不能被关闭错误覆盖。参数: 无。返回: None。异常: 断言失败。
        """
        spec = self.fixture([['0','123','','0']])
        with self.assertRaises(BudgetExceededError):
            CANCSVRead(spec,ResourceBudget(1024))
        failure = RuntimeError('cancel')
        reader = CANCSVRead(spec,self.budget)
        with patch.object(reader,'_check_cancel',side_effect=failure), patch.object(reader,'close',side_effect=OSError('close')):
            with self.assertRaises(RuntimeError) as caught:
                next(reader)
        self.assertIs(caught.exception,failure)
        self.assertIs(caught.exception.raw_csv_cleanup_owner,reader)
        reader.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_eof_close_failure_keeps_recoverable_owner(self):
        """EOF关闭失败不能丢失临时reader责任。参数: 无。返回: None。异常: 断言失败。
        """
        reader = CANCSVRead(self.fixture([]),self.budget)
        with patch.object(reader,'close',side_effect=OSError('close')):
            with self.assertRaises(OSError) as caught:
                next(reader)
        self.assertIs(caught.exception.raw_csv_cleanup_owner,reader)
        reader.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_open_failure_preserves_other_owners_budget(self):
        """打开失败只抵销本reader费用，不释放其他对象的17字节。参数: 无。返回: None。异常: 断言失败。
        """
        spec = self.fixture([])
        self.budget.reserve_ram(17)
        with patch.object(Path,'open',side_effect=OSError('open failure')):
            with self.assertRaisesRegex(OSError,'open failure'):
                CANCSVRead(spec,self.budget)
        self.assertEqual(self.budget.ram_bytes,17)
        self.budget.release_ram(17)

    def test_file_close_failure_and_context_error_remain_recoverable(self):
        """文件真实关闭持续失败时保留原业务错误和owner，恢复后关闭句柄。参数: 无。返回: None。异常: 断言失败。
        """
        reader = CANCSVRead(self.fixture([['0','123','','0']]),self.budget)
        stream = reader._file
        failure = RuntimeError('body failure')
        with patch.object(stream,'close',side_effect=OSError('close failure')):
            with self.assertRaises(RuntimeError) as caught:
                with reader:
                    raise failure
        self.assertIs(caught.exception,failure)
        self.assertIs(failure.raw_csv_cleanup_owner,reader)
        self.assertFalse(reader.closed)
        self.assertFalse(stream.closed)
        self.assertGreater(self.budget.ram_bytes,0)
        reader.close()
        self.assertTrue(stream.closed)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_budget_release_failure_can_retry_without_double_release(self):
        """文件已关闭但归还预算失败时，只重试尚未归还的费用。参数: 无。返回: None。异常: 断言失败。
        """
        reader = CANCSVRead(self.fixture([]),self.budget)
        stream = reader._file
        held = self.budget.ram_bytes
        with patch.object(self.budget,'release_ram',side_effect=RuntimeError('release failure')):
            with self.assertRaisesRegex(RuntimeError,'release failure'):
                reader.close()
        self.assertTrue(stream.closed)
        self.assertFalse(reader.closed)
        self.assertEqual(self.budget.ram_bytes,held)
        reader.close()
        reader.close()
        self.assertEqual(self.budget.ram_bytes,0)
