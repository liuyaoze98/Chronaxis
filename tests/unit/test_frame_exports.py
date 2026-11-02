"""验证新原帧导出的时间、顺序、未知ID、目标格式回读及失败清理。

输入为明确合成原帧，ASC由新解析器和python-can独立回读，BLF使用实际旧封装
writer进程及python-can reader。只写work；没有DBC解码或原日志再次扫描。
"""

from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from chronaxis.core.models import Interval
from chronaxis.legacy.records import LegacyRawFrame, StoredRawFrame
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.frame_exports import FrameExportSpec, export_can_frames
from chronaxis.sources.raw_can import RawCANRecord
from chronaxis.sources.asc import ASCRead, ASCSpec


def raw(time,sequence,*,data=b'\x01\x02',identifier=0x123,**changes):
    """建立手算原帧。参数: time/sequence、data/identifier及字段覆盖。返回: RawCANRecord。异常: 模型非法。
    """
    fields=dict(timestamp=time/10**9,arbitration_id=identifier,channel=0,dlc=len(data),data=data,
        is_extended_id=False,is_remote_frame=False,is_error_frame=False,is_fd=False,
        is_rx=True,bitrate_switch=False,error_state_indicator=False)
    fields.update(changes)
    return RawCANRecord(LegacyRawFrame(**fields),time,Path('synthetic.asc'),sequence+1,sequence,
                        str(time),'synthetic-v1',None,False)


class FrameExportTests(unittest.TestCase):
    """真实写出后逐帧比较可表达字段；不能表达的错误帧标志必须留索引与清单。"""

    def setUp(self):
        """创建新测试根和共享预算。参数: 无。返回: None。异常: I/O错。
        """
        self.root=Path('work/m3-input-home-20261023/frame-export-tests')/uuid4().hex
        self.root.mkdir(parents=True)
        self.budget=ResourceBudget()

    def export(self,records,*,format='asc',interval=None,offset=0,target='out',cancel=None,reference='relative',date=None,zone=None):
        """调用实际导出。参数: records和格式/范围/偏移/目录/取消覆盖。返回: Path。异常: 原导出错。
        """
        return export_can_frames(records,FrameExportSpec(format,offset,reference,date,zone),interval or Interval(0,1000),
            self.root/target,self.budget,source='bus',device_label='home',check_cancel=cancel)

    def test_asc_precise_ns_all_frames_and_identity(self):
        """1ns、同刻未知ID/扩展/FD/远程都保留，完整原序不去重。参数: 无。返回: None。异常: 断言失败。
        """
        records=[raw(1,0),raw(1,1,identifier=0x777),raw(2,2,identifier=0x321,is_extended_id=True,is_rx=False),
                 raw(3,3,data=bytes(range(12)),is_fd=True,bitrate_switch=True,error_state_indicator=True),
                 raw(4,4,data=b'',dlc=8,is_remote_frame=True)]
        path=self.export(iter(records))
        with ASCRead(ASCSpec(path/'frames.asc'),self.budget) as reader:
            actual=tuple(reader)
        self.assertEqual([r.time_ns for r in actual],[r.time_ns for r in records])
        self.assertEqual([r.frame for r in actual],[r.frame for r in records])
        index=[json.loads(line) for line in (path/'frames.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual([r['sequence'] for r in index],[0,1,2,3,4])
        self.assertEqual(index[1]['frame']['arbitration_id'],0x777)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_asc_independent_reader_and_error_limit_index(self):
        """独立python-can核普通帧；错误帧无法表达的Tx在索引保留并注明。参数: 无。返回: None。异常: 断言失败。
        """
        import can
        records=[raw(10**9,0),raw(2*10**9,1,data=b'',identifier=0,is_error_frame=True,is_rx=False)]
        path=self.export(records,interval=Interval(0,3*10**9))
        reader=can.ASCReader(path/'frames.asc')
        try:
            rows=list(reader)
        finally:
            reader.stop()
        self.assertEqual((len(rows),rows[0].timestamp,rows[0].data),(2,1.0,b'\x01\x02'))
        self.assertTrue(rows[1].is_error_frame)
        index=[json.loads(line) for line in (path/'frames.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertFalse(index[1]['frame']['is_rx'])
        self.assertIn('is_rx',index[1]['format_limits'])
        self.assertEqual(json.loads((path/'manifest.json').read_text(encoding='utf-8'))['format_limited_frames'],1)

    def test_half_open_overlapping_and_empty_ranges(self):
        """每个片段内原帧只写一次，重叠片段各自保记录。参数: 无。返回: None。异常: 断言失败。
        """
        records=[raw(t,t) for t in (0,1,2,3)]
        for start,end,expected in ((0,2,[0,1]),(1,3,[1,2]),(2,2,[]),(5,7,[])):
            path=self.export(iter(records),interval=Interval(start,end),target=f'{start}-{end}')
            rows=[json.loads(line) for line in (path/'frames.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([r['sequence'] for r in rows],expected)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_blf_original_epoch_separate_from_analysis_offset(self):
        """旧暂存筛选分析0/1秒，输出仍为原2023绝对时间，不施加分析offset两次。参数: 无。返回: None。异常: 断言失败。
        """
        import can
        base=1700000000*10**9
        source=[StoredRawFrame(i,i*10**9,raw(base+i*10**9,i,identifier=0x100+i).frame) for i in range(3)]
        path=self.export(source,format='blf',interval=Interval(0,2*10**9),reference='epoch')
        reader=can.BLFReader(path/'frames.blf')
        try:
            rows=list(reader)
        finally:
            reader.stop()
        self.assertEqual([r.timestamp for r in rows],[1700000000.0,1700000001.0])
        self.assertEqual([r.arbitration_id for r in rows],[0x100,0x101])
        self.assertEqual([bytes(r.data) for r in rows],[b'\x01\x02']*2)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_blf_fd_same_time_and_precision_recorded(self):
        """FD/同刻保载荷和标志，float秒损失有清单且精确索引不丢ns。参数: 无。返回: None。异常: 断言失败。
        """
        import can
        base=1700000000*10**9+123
        records=[raw(base,0,data=bytes(range(12)),is_fd=True,bitrate_switch=True,is_rx=False),
                 raw(base,1,identifier=0x777)]
        path=self.export(records,format='blf',interval=Interval(base,base+1),reference='epoch')
        reader=can.BLFReader(path/'frames.blf')
        try:
            rows=list(reader)
        finally:
            reader.stop()
        self.assertEqual(len(rows),2)
        self.assertTrue(rows[0].is_fd and rows[0].bitrate_switch)
        self.assertFalse(rows[0].is_rx)
        self.assertEqual(bytes(rows[0].data),bytes(range(12)))
        manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
        self.assertGreater(manifest['max_float_conversion_error_ns'],0)
        self.assertLessEqual(abs(round(rows[0].timestamp*10**9)-base),1000)
        index=[json.loads(line) for line in (path/'frames.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual([r['output_time_ns'] for r in index],[base,base])

    def test_empty_blf_and_missing_date_do_not_fabricate_epoch(self):
        """有时间声明可导空BLF；无日期先拒配置，不因输入为空或大数字伪造日期。参数: 无。返回: None。异常: 断言失败。
        """
        import can
        path=self.export([],format='blf',target='empty',reference='epoch')
        reader=can.BLFReader(path/'frames.blf')
        try:
            self.assertEqual(list(reader),[])
        finally:
            reader.stop()
        with self.assertRaisesRegex(ValueError,'日期'):
            self.export([raw(10,0)],format='blf')
        with self.assertRaisesRegex(ValueError,'日期'):
            self.export([],format='blf',offset=1700000000*10**9)
        self.assertFalse((self.root/'out').exists())
        self.assertEqual(self.budget.ram_bytes,0)

    def test_explicit_time_shift_changes_output_not_range(self):
        """明确平移只改输出时间，范围筛选仍按原分析坐标。参数: 无。返回: None。异常: 断言失败。
        """
        path=self.export([raw(-1,0),raw(0,1),raw(1,2)],interval=Interval(-1,1),offset=10)
        with ASCRead(ASCSpec(path/'frames.asc'),self.budget) as reader:
            self.assertEqual([r.time_ns for r in reader],[9,10])
        self.assertEqual(self.budget.ram_bytes,0)

    def test_late_rollback_and_cancel_never_publish_partial_files(self):
        """先写前缀再遇回退或取消，整个导出不安装。参数: 无。返回: None。异常: 断言失败。
        """
        with self.assertRaisesRegex(ValueError,'回退'):
            self.export([raw(2,0),raw(1,1)])
        with self.assertRaises(KeyboardInterrupt):
            self.export([raw(1,0)],cancel=Mock(side_effect=KeyboardInterrupt('cancel')))
        self.assertFalse((self.root/'out').exists())
        self.assertEqual(self.budget.ram_bytes,0)

    def test_blf_real_worker_failure_closes_owner(self):
        """真正writer已启动写首帧后，后续错误触发关闭且不发布。参数: 无。返回: None。异常: 断言失败。
        """
        from chronaxis.legacy.export_write import LegacyCANProcessWrite
        original=LegacyCANProcessWrite.write; owners=[]
        def failed(owner,frame):
            """真实写一次后抛注入错。参数: owner/frame。返回: 无。异常: OSError。
            """
            owners.append(owner); original(owner,frame); raise OSError('写出后故障')
        base=1700000000*10**9
        with patch.object(LegacyCANProcessWrite,'write',autospec=True,side_effect=failed):
            with self.assertRaisesRegex(OSError,'写出后故障'):
                self.export([raw(base,0)],format='blf',interval=Interval(base,base+1),reference='epoch')
        self.assertTrue(owners[0].closed)
        self.assertEqual(self.budget.ram_bytes,0)
        self.assertFalse((self.root/'out').exists())

    def test_real_date_timezone_mapping_and_validation(self):
        """明确2023-11-15东八区午夜，加日内秒得到独立已知epoch；拒重复/非法日期。参数: 无。返回: None。异常: 断言失败。
        """
        import can
        time=(6*3600+13*60+20)*10**9+123
        path=self.export([raw(time,0)],format='blf',interval=Interval(time,time+1),date='2023-11-15',zone=480)
        reader=can.BLFReader(path/'frames.blf')
        try:
            rows=list(reader)
        finally:
            reader.stop()
        self.assertLessEqual(abs(rows[0].timestamp-1700000000.000000123),1e-6)
        info=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((info['capture_date'],info['timezone_offset_minutes']),('2023-11-15',480))
        packet=json.loads((path/'frames.jsonl').read_text(encoding='utf-8'))
        self.assertEqual((packet['source_time_ns'],packet['output_time_ns']),(time,1700000000*10**9+123))
        for date,zone,reference in (('2023-02-29',0,'relative'),('2023-11-15',None,'relative'),
                ('2023-11-15',1440,'relative'),('2023-11-15',0,'epoch')):
            with self.assertRaises(ValueError):
                FrameExportSpec('blf',0,reference,date,zone)
        with self.assertRaisesRegex(ValueError,'1990'):
            self.export([raw(1,0)],format='blf',target='early',reference='epoch')
        self.assertEqual(self.budget.ram_bytes,0)

    def test_blf_channel_rejection_and_verifier_close_recovery(self):
        """拒BLF隐式改通道；真实摘要句柄持续关闭失败时保owner，恢复后RAM归零。参数: 无。返回: None。异常: 断言失败。
        """
        from chronaxis.results.export_files import ExportFiles
        base=1700000000*10**9
        with self.assertRaisesRegex(ValueError,'通道'):
            self.export([raw(base,0,channel=None)],format='blf',reference='epoch',interval=Interval(base,base+1))
        original=Path.open; failures=[True]; wrappers=[]
        class HeldFile:
            """持有真实读句柄，外部恢复开关只控制close故障。"""
            def __init__(self,stream):
                """保存真实流。参数: stream。返回: None。异常: 无。"""
                self.stream=stream
            def read(self,size):
                """读取真实文件。参数: size。返回: bytes。异常: I/O错。"""
                return self.stream.read(size)
            def close(self):
                """按开关注入关闭错。参数: 无。返回: None。异常: OSError或I/O错。"""
                if failures[0]:
                    raise OSError('摘要关闭故障')
                self.stream.close()
        def opened(path,*args,**kwargs):
            """仅替换新文件摘要读流。参数: path及open参数。返回: 原或故障流。异常: I/O错。"""
            stream=original(path,*args,**kwargs)
            if path.name=='frames.blf' and args==('rb',):
                stream=HeldFile(stream); wrappers.append(stream)
            return stream
        with patch.object(Path,'open',opened):
            with self.assertRaisesRegex(OSError,'摘要关闭故障') as caught:
                self.export([],format='blf',reference='epoch',target='close')
        owner=caught.exception.export_cleanup_owner
        self.assertIsInstance(owner,ExportFiles)
        self.assertFalse(wrappers[0].stream.closed)
        failures[0]=False; owner.close()
        self.assertTrue(wrappers[0].stream.closed)
        self.assertEqual(self.budget.ram_bytes,0)
        self.assertFalse((self.root/'close').exists())
