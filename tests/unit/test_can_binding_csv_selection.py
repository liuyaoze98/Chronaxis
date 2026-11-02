"""[home] 核验省略CSV帧型时无关ID不要求DBC，保留实际行序与清理。"""

from configuration_fixtures import current_fixture
from dataclasses import replace
from uuid import uuid4
import unittest
from chronaxis import AnalysisPlan,AnalysisRunner
from chronaxis.sources.raw_csv_layout import CANCSVLayout
from chronaxis.sources.text_can_decode import CANTextDecodeRead
from chronaxis.sources.text_can_spec import CANTextSpec
from chronaxis.sources.raw_can import CANTextError
import test_text_can_decode as fixtures
from test_current_message_calculation import config

class CANBindingCSVSelectionTests(unittest.TestCase):
    """独立CSV含DBC之外的坏时间/载荷行，按需时只读ID。"""
    setUp=fixtures.TextCANDecodeTests.setUp
    csv=fixtures.TextCANDecodeTests.csv

    def source(self,body):
        """创建省略两个帧型列的来源。参数: CSV正文。返回: spec。异常: I/O。"""
        source=self.csv(body)
        fields=dict(source.layout.fields)
        fields.pop('is_extended');fields.pop('is_fd')
        return replace(source,layout=CANCSVLayout(fields))

    def test_selected_ids_preserve_sequences_across_empty_files(self):
        """无关ID不查DBC/时间/载荷；跨空文件后全局序号仍含跳行。"""
        inputs=(self.source('bad,200,bad,bad\n0,100,01 05,2\nbad,200,bad,bad\n'),
                self.source(''),self.source('bad,200,bad,bad\n1,100,03 06,2\n'))
        reader=CANTextDecodeRead(CANTextSpec('bus',inputs,self.dbc,0,self.timebase),self.budget,
            (self.signal,),selected_ids=(256,),trace=False,retain_source_time=False)
        try:
            rows=tuple(reader)
            self.assertEqual([(r.sequence,r.raw.sequence,r.raw.line_number) for r in rows],[(1,1,3),(4,1,3)])
            self.assertEqual(reader.count,5)
            self.assertEqual(reader.decode_calls,2)
            self.assertEqual(reader.metadata['record_check_scope'],'selected_ids')
        finally:reader.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_all_unselected_and_cancel_release_budget(self):
        """全无关记录正常EOF；逐物理行取消检查不能被ID跳过绕开。"""
        from unittest.mock import Mock
        inputs=(self.source('bad,200,bad,bad\nbad,200,bad,bad\n'),)
        for cancelled in (False,True):
            callback=Mock(side_effect=RuntimeError('cancelled')) if cancelled else None
            reader=CANTextDecodeRead(CANTextSpec('bus',inputs,self.dbc,0,self.timebase),self.budget,
                (self.signal,),selected_ids=(256,),trace=False,retain_source_time=False,check_cancel=callback)
            try:
                if cancelled:
                    with self.assertRaisesRegex(RuntimeError,'cancelled'):tuple(reader)
                else:
                    self.assertEqual(tuple(reader),())
                    self.assertEqual(reader.count,2)
                    self.assertTrue(reader.exhausted)
                    self.assertIsNone(reader.first_ns)
            finally:reader.close()
            self.assertEqual(self.budget.ram_bytes,0)

    def test_midnight_progress_from_unselected_rows_is_required(self):
        """午夜仅出现无关ID也推进日期，下一目标13点属于次日。"""
        from chronaxis.sources.raw_csv import CSVTimeSpec, DAY_NS
        source=self.source('12:00:00,100,01 05,2\n23:59:59,200,bad,bad\n00:00:01,200,bad,bad\n13:00:00,100,03 06,2\n')
        source=replace(source,time=CSVTimeSpec(format='clock',rollover_min_drop_ns=12*3600*10**9))
        reader=CANTextDecodeRead(CANTextSpec('bus',(source,),self.dbc,0,self.timebase),self.budget,
            (self.signal,),selected_ids=(256,),trace=False,retain_source_time=False)
        try:
            rows=tuple(reader)
            self.assertEqual([r.raw.time_ns for r in rows],[12*3600*10**9,DAY_NS+13*3600*10**9])
            self.assertEqual([r.sequence for r in rows],[0,3])
            self.assertEqual(reader.count,4)
        finally:reader.close()
        self.assertEqual(self.budget.ram_bytes,0)
        source.path.write_text('time,id,data,length\n12:00:00,100,01 05,2\nbad,200,bad,bad\n',encoding='utf-8')
        reader=CANTextDecodeRead(CANTextSpec('bus',(source,),self.dbc,0,self.timebase),self.budget,
            (self.signal,),selected_ids=(256,),trace=False,retain_source_time=False)
        try:
            with self.assertRaisesRegex(CANTextError,'日内时间'):tuple(reader)
        finally:reader.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_full_source_still_requires_real_identity(self):
        """完整原帧读取不能为未知ID伪造帧型。"""
        reader=CANTextDecodeRead(CANTextSpec('bus',(self.source('0,200,01,1\n'),),self.dbc,0,self.timebase),
            self.budget,(self.signal,),trace=False,retain_source_time=False)
        try:
            with self.assertRaisesRegex(CANTextError,'帧型'):
                tuple(reader)
        finally:reader.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_public_message_runner_ignores_unknown_id(self):
        """公开入口仅两条4000W参与，每条0.1秒，总计800J。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 2 Node\n SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n',encoding='utf-8')
        parser=self.source('bad,200,bad,bad\n0,100,A0 0F,2\nbad,200,bad,bad\n0.1,100,A0 0F,2\n')
        raw=config('raw_can_csv')
        raw['sources'][0]['path']=str(parser.path.absolute())
        raw['sources'][0]['dbc_by_channel']={'1':str(self.dbc.absolute())}
        fields=raw['sources'][0]['reader']['layout']['fields']
        fields.pop('is_extended');fields.pop('is_fd')
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend):
                result=AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
                try:
                    rows=tuple(result.iter_calculations())
                    self.assertEqual(rows[0].value,800.)
                finally:
                    budget=result.spool._budget
                    result.close()
                self.assertEqual(budget.ram_bytes,0)
        # 全部行无关时也应正常完成，来源行数不伪装成零。
        parser.path.write_text('time,id,data,length\nbad,200,bad,bad\n',encoding='utf-8')
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
        try:self.assertIsNone(tuple(result.iter_calculations())[0].value)
        finally:result.close()

if __name__=='__main__':unittest.main()
