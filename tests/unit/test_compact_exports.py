"""精简导出只生成所需业务文件；比较实际帧/插值，不仅检查文件名。"""
import csv,json
from pathlib import Path
from published_paths import published_file
from uuid import uuid4
from unittest import TestCase
from unittest.mock import patch
from chronaxis.core.models import Interval
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType as D,QualityFlag as Q
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.signal_exports import export_signal_csv,SignalCSVExportSpec
from chronaxis.results.signal_grid import SignalGridSpec
from chronaxis.results.frame_exports import export_can_frames,FrameExportSpec
from chronaxis.sources.asc import ASCRead,ASCSpec
from test_signal_exports import sample
from test_frame_exports import raw

class CompactExportTests(TestCase):
    """新模式禁止调用追溯编码，旧接口默认仍保原合同。"""
    def setUp(self):
        """独立工作目录及共享账本。参数: 无。返回: None。异常: I/O错。"""
        self.root=Path('work/m3-raw-interval-home/compact-exports')/uuid4().hex
        self.root.mkdir(parents=True);self.budget=ResourceBudget()

    def test_original_and_grid_no_reference_encoding(self):
        """保无效原因及实点/估计状态；不编码原值、来源和左右端点副本。"""
        definition=SignalDefinition('voltage','bus','字段,"含逗号"',D.FLOAT64,'V',1000)
        for backend in ('reference','numpy'):
            for grid in (None,SignalGridSpec(('voltage',),10,0,100)):
                spec=SignalCSVExportSpec(('voltage',),grid)
                rows=[sample(0,0.),sample(20,20.,sequence=1),sample(30,None,sequence=2,quality=Q.MISSING)]
                with patch('chronaxis.results.signal_exports._pack',side_effect=AssertionError('未请求原文')),patch('chronaxis.results.signal_exports._reference_json',side_effect=AssertionError('未请求端点引用')):
                    out=export_signal_csv(rows,spec,Interval(0,41),self.root/uuid4().hex,self.budget,device_label='home',definitions=(definition,),backend=backend,compact=True)
                with (published_file(out,'resampled.csv' if grid else 'original.csv')).open(encoding='utf-8',newline='') as f:
                    parsed=list(csv.DictReader(f))
                self.assertNotIn('source_ref_json',parsed[0]);self.assertNotIn('left_time_ns',parsed[0])
                self.assertNotIn('original_value_json',parsed[0])
                if grid:
                    self.assertEqual(parsed[1]['value'],'10.0');self.assertEqual(parsed[1]['status'],'estimated')
                else:
                    self.assertEqual(parsed[-1]['value'],'');self.assertNotEqual(parsed[-1]['quality'],'0')
                self.assertEqual(self.budget.ram_bytes,0)

    def test_asc_no_frame_packet(self):
        """普通、未知、同刻FD仍原样写出，不构造逐帧JSON。"""
        rows=[raw(1,0),raw(1,1,identifier=0x777),raw(3,2,data=bytes(range(12)),is_fd=True)]
        with patch('chronaxis.results.frame_exports.frame_to_dict',side_effect=AssertionError('未请求帧副本')):
            out=export_can_frames(rows,FrameExportSpec(),Interval(0,10),self.root/'asc',self.budget,source='bus',device_label='home',compact=True)
        self.assertEqual(set(out.output_dir.iterdir()),{published_file(out,'frames.asc'),out.manifest_path})
        with ASCRead(ASCSpec(published_file(out,'frames.asc')),self.budget) as read:
            actual=list(read)
        self.assertEqual([(r.time_ns,r.frame) for r in actual],[(r.time_ns,r.frame) for r in rows])
        doc=json.loads((published_file(out,'manifest.json')).read_text(encoding='utf-8'))
        self.assertNotIn('exact_source_index',doc);self.assertNotIn('max_float_conversion_error_ns',doc)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_blf_no_float_error_probe(self):
        """使用已确认采集日期写真实BLF，数值/数据可回读但不计算对照误差。"""
        import can
        rows=[raw(0,0),raw(100000000,1,data=b'\x03\x04')]
        spec=FrameExportSpec('blf',0,'relative','2026-10-24',480)
        with patch('chronaxis.results.frame_exports.Fraction',side_effect=AssertionError('未请求误差对照')),patch('chronaxis.results.frame_exports.frame_to_dict',side_effect=AssertionError('未请求帧副本')):
            out=export_can_frames(rows,spec,Interval(0,200000000),self.root/'blf',self.budget,source='bus',device_label='home',compact=True)
        with can.BLFReader(published_file(out,'frames.blf')) as reader: actual=list(reader)
        self.assertEqual([r.data for r in actual],[b'\x01\x02',b'\x03\x04'])
        self.assertAlmostEqual(actual[1].timestamp-actual[0].timestamp,.1,places=5)
        self.assertEqual(set(out.output_dir.iterdir()),{published_file(out,'frames.blf'),out.manifest_path})
        self.assertEqual(self.budget.ram_bytes,0)
