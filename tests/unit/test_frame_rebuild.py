"""用手算位域、独立IEEE编码及真实磁盘排序验证离线报文重建。

DBC及报文为声明合成样例；未知位用固定非零模式检验，不能以产品回读作唯一真值。
原始ASC/BLF不会重新解析或解码，测试产物仅写新项目work目录。
"""

from dataclasses import replace
import json
from pathlib import Path
from published_paths import published_file
import struct
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultFormatError,BudgetExceededError
from chronaxis.results.frame_patch import FrameRebuildRule,DBCFramePatch
from chronaxis.results.frame_sort import FrameSort
from chronaxis.results.frame_rebuild import FrameSample,FrameGridSpec,FrameRebuildRead
from chronaxis.results.frame_exports import ExportCANFrame,SkippedCANFrame,as_export_frame,FrameExportSpec,export_can_frames
from chronaxis.core.models import Interval
from test_frame_exports import raw


class FrameRebuildTests(unittest.TestCase):
    """每例独立共享预算和新目录，结束核真实文件/资源责任。"""

    def setUp(self):
        """创建独立work和预算。参数: 无。返回: None。异常: I/O错。
        """
        self.root=Path('work/m3-input-home-20261023/frame-rebuild-tests')/uuid4().hex
        self.root.mkdir(parents=True); self.budget=ResourceBudget()

    def message(self,signals,length=8):
        """加载手算信号声明。参数: signals为DBC行、length字节。返回: Message。异常: 真解析错。
        """
        import cantools
        return cantools.database.load_string('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            +f'BO_ 291 Frame: {length} Node\n'+signals,database_format='dbc').get_message_by_frame_id(0x123)

    def patcher(self,message,names,**kwargs):
        """建立明确连续字段规则。参数: message、names及规则覆盖。返回: patcher。异常: 结构/预算错。
        """
        return DBCFramePatch(FrameRebuildRule(0,0x123,names,False,False,**kwargs),message,self.budget)

    def test_little_endian_half_even_and_unchanged_bits(self):
        """10.25V/0.5=20.5取偶20；10.75/0.5=21.5取22，其余位逐位保持。参数: 无。返回: None。异常: 断言失败。
        """
        message=self.message(' SG_ Voltage : 0|16@1+ (0.5,0) [0|1000] "V" Node\n'
            ' SG_ Counter : 16|4@1+ (1,0) [0|15] "" Node\n'
            ' SG_ Checksum : 24|8@1+ (1,0) [0|255] "" Node\n')
        owner=self.patcher(message,('Voltage',),protected=('Counter','Checksum'))
        base=raw(0,0,data=bytes.fromhex('ffffa57eccdd7788')).frame
        try:
            frame,facts=owner.patch(base,{'Voltage':10.25},())
            self.assertEqual(frame.data,bytes.fromhex('1400a57eccdd7788'))
            self.assertEqual(facts,(('Voltage',10.25,20,10.0,-0.25),))
            frame,_=owner.patch(base,{'Voltage':10.75},())
            self.assertEqual(frame.data[:2],b'\x16\x00')
            with self.assertRaisesRegex(ValueError,'物理值越界'):
                owner.patch(base,{'Voltage':1001},())
        finally:
            owner.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_motorola_signed_fields_and_negative_scale(self):
        """Motorola跨字节手算123/FFE，低半字节及非选字节保原；负倍率不改变位序。参数: 无。返回: None。异常: 断言失败。
        """
        message=self.message(' SG_ V : 7|12@0+ (1,0) [0|4095] "V" Node\n'
            ' SG_ Signed : 23|12@0- (-0.5,1) [-1022|1025] "A" Node\n')
        owner=self.patcher(message,('V','Signed'))
        try:
            frame,facts=owner.patch(raw(0,0,data=bytes.fromhex('aabbccdd12345678')).frame,{'V':0x123,'Signed':2},())
            self.assertEqual(frame.data,bytes.fromhex('123bffed12345678'))
            self.assertEqual(facts[1][2],-2)
        finally:
            owner.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_float_rounding_and_raw_width_overflow(self):
        """float32按标准struct独立核载荷与误差；整数码宽越界不截断。参数: 无。返回: None。异常: 断言失败。
        """
        import cantools
        text='VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 291 Frame: 8 Node\n SG_ V : 0|32@1+ (1,0) [-1e20|1e20] "V" Node\nSIG_VALTYPE_ 291 V : 1;\n'
        msg=cantools.database.load_string(text,database_format='dbc').get_message_by_frame_id(291)
        owner=self.patcher(msg,('V',))
        try:
            frame,facts=owner.patch(raw(0,0,data=b'abcdefgh').frame,{'V':1/3},())
            self.assertEqual(frame.data,struct.pack('<f',1/3)+b'efgh')
            self.assertNotEqual(facts[0][-1],0)
        finally:
            owner.close()
        owner=self.patcher(self.message(' SG_ V : 0|8@1+ (1,0) [0|1000] "V" Node\n'),('V',))
        try:
            with self.assertRaisesRegex(ValueError,'位宽'):
                owner.patch(raw(0,0,data=b'abcdefgh').frame,{'V':256},())
        finally:
            owner.close()

    def test_multiplexer_active_subset_and_protection(self):
        """相同载荷位置的分支只改当前字段；选择器及显式保护字段不可插值。参数: 无。返回: None。异常: 断言失败。
        """
        msg=self.message(' SG_ Mux M : 0|4@1+ (1,0) [0|15] "" Node\n'
            ' SG_ V m1 : 8|8@1+ (1,0) [0|255] "V" Node\n'
            ' SG_ T m2 : 8|8@1+ (1,0) [0|255] "C" Node\n')
        owner=self.patcher(msg,('V','T'))
        try:
            frame,_=owner.patch(raw(0,0,data=bytes.fromhex('a100cdef12345678')).frame,{'V':30},(('Mux',1),))
            self.assertEqual(frame.data,bytes.fromhex('a11ecdef12345678'))
            self.assertEqual(owner.selected((('Mux',2),)),('T',))
        finally:
            owner.close()
        with self.assertRaisesRegex(ValueError,'选择器'):
            self.patcher(msg,('Mux',))
        with self.assertRaisesRegex(ValueError,'保护'):
            FrameRebuildRule(0,291,('V',),False,False,('V',))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_bounded_sort_stability_and_full_eof(self):
        """超过单批和多层归并，等键仍按原追加顺序；结束后全部句柄/预算归零。参数: 无。返回: None。异常: 断言失败。
        """
        owner=FrameSort(self.root/'sort',self.budget,buffer_rows=3)
        try:
            for i in range(41):
                owner.append((40-i if i%3 else 10,),{'number':i})
            owner.seal(); actual=list(owner.rows())
            expected=sorted(range(41),key=lambda i:(40-i if i%3 else 10,i))
            self.assertEqual([p[2]['number'] for p in actual],expected)
            self.assertFalse(owner.handles)
        finally:
            owner.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_sort_truncation_or_content_tamper_rejected(self):
        """内容仍是合法JSON也须拒篡改；删除结束行不得假装完整EOF。参数: 无。返回: None。异常: 断言失败。
        """
        for mode in ('changed','truncated','extra'):
            owner=FrameSort(self.root/mode,self.budget)
            try:
                owner.append((0,),{'value':1}); owner.seal()
                path=owner.path/'0-0.jsonl'; data=path.read_bytes()
                if mode=='changed':
                    data=data.replace(b'"value":1',b'"value":2')
                elif mode=='truncated':
                    data=data.splitlines(keepends=True)[0]
                else:
                    data+=b'junk'
                path.write_bytes(data)
                with self.assertRaises(ResultFormatError):
                    list(owner.rows())
            finally:
                owner.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def sample(self,time,sequence,value=0,*,known=True,valid=True,layout=(),values=None,**changes):
        """创建已解码事实及带状态/未知位原帧。参数: 时间/序号/值与分类/布局/帧覆盖。返回: FrameSample。异常: 模型错。
        """
        data=changes.pop('data',bytes((value if type(value) is int and 0<=value<=255 else 0,sequence%256,0xa5,0x7e,0x12,0x34,0x56,0x78)))
        return FrameSample(as_export_frame(raw(time,sequence,data=data,**changes)),
            (('V',value),) if values is None else values,layout,known,valid)

    def rebuild(self,samples,*,grid=None,interval=None,backend='numpy',message=None,rules=None,cancel=None):
        """建立真实有界重建。参数: 样本及配置覆盖。返回: owner。异常: 原构造错。
        """
        if message is None:
            message=self.message(' SG_ V : 0|8@1+ (1,0) [0|255] "V" Node\n'
                ' SG_ State : 8|8@1+ (1,0) [0|255] "" Node\n'
                ' SG_ Counter : 16|4@1+ (1,0) [0|15] "" Node\n'
                ' SG_ Checksum : 24|8@1+ (1,0) [0|255] "" Node\n')
        if rules is None:
            rules=((FrameRebuildRule(0,291,('V',),False,False,('Counter','Checksum')),message),)
        return FrameRebuildRead(samples,grid or FrameGridSpec(10,0,110),interval or Interval(0,131),
            rules,self.budget,self.root/uuid4().hex,backend=backend,check_cancel=cancel)

    def test_non_midpoint_linear_base_left_tie_and_actual_output(self):
        """10→120在100为100，状态沿右；65等距沿左，未知位逐位保留，两后端实际ASC一致。参数: 无。返回: None。异常: 断言失败。
        """
        from chronaxis.sources.asc import ASCRead,ASCSpec
        results=[]
        for backend in ('reference','numpy'):
            samples=[self.sample(10,0,10),self.sample(120,1,120)]
            owner=self.rebuild(samples,backend=backend)
            target=export_can_frames(owner,FrameExportSpec('asc'),Interval(0,131),self.root/backend,self.budget,source='bus',device_label='home')
            with ASCRead(ASCSpec(published_file(target,'frames.asc')),self.budget) as reader:
                frames=list(reader)
            actual={r.time_ns:r.frame.data for r in frames}
            self.assertEqual(actual[100],bytes((100,1,0xa5,0x7e,0x12,0x34,0x56,0x78)))
            self.assertEqual(actual[40][1:],samples[0].record.frame.data[1:])
            self.assertEqual(actual[10],samples[0].record.frame.data)
            self.assertEqual(actual[120],samples[1].record.frame.data)
            missing=[json.loads(x) for x in (published_file(target,'skipped_frames.jsonl')).read_text(encoding='utf-8').splitlines()]
            self.assertEqual([(r['time_ns'],r['reason']) for r in missing],[(0,'missing_left'),(130,'missing_right')])
            results.append(actual)
        self.assertEqual(*results)
        owner=self.rebuild([self.sample(10,0,10),self.sample(120,1,120)],grid=FrameGridSpec(25,15,110))
        try:
            frames={r.time_ns:r for r in owner if type(r) is ExportCANFrame}
            self.assertEqual(frames[65].frame.data[:2],b'\x41\x00')
            details=json.loads(dict(frames[65].provenance)['reconstruction'])
            self.assertEqual((details['base_sequence'],details['left_sequence'],details['right_sequence']),(0,0,1))
        finally:
            owner.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_invalid_gap_same_time_and_half_open_boundaries(self):
        """无效/超间隔/同刻冲突不产生伪造帧；实点保持，范围外不借点。参数: 无。返回: None。异常: 断言失败。
        """
        cases=[([self.sample(10,0,10),self.sample(60,1,None,valid=False),self.sample(120,2,120)],FrameGridSpec(10,0,110),100,'invalid_neighbor'),
            ([self.sample(10,0,10),self.sample(120,1,120)],FrameGridSpec(10,0,109),100,'gap_too_large'),
            ([self.sample(10,0,10),self.sample(10,1,20),self.sample(120,2,120)],FrameGridSpec(10,0,110),10,'same_time_conflict')]
        for samples,grid,time,reason in cases:
            owner=self.rebuild(samples,grid=grid)
            try:
                rows=list(owner); skips={r.time_ns:r.reason for r in rows if type(r) is SkippedCANFrame}
                self.assertEqual(skips[time],reason)
                self.assertTrue(any(type(r) is ExportCANFrame and r.time_ns==120 for r in rows))
            finally:
                owner.close()
        owner=self.rebuild([self.sample(-10,0,10),self.sample(120,1,120)],interval=Interval(0,120))
        try:
            self.assertEqual(list(owner),[])
        finally:
            owner.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_last_sequence_and_layout_switch_do_not_bridge(self):
        """同刻last策略依最大原序；复用从1到2再回1不可跨中间分支插值。参数: 无。返回: None。异常: 断言失败。
        """
        message=self.message(' SG_ V : 0|8@1+ (1,0) [0|255] "V" Node\n')
        rule=FrameRebuildRule(0,291,('V',),False,False,same_time_policy='last_by_sequence')
        owner=self.rebuild([self.sample(10,0,10),self.sample(10,1,20),self.sample(120,2,130)],rules=((rule,message),))
        try:
            frames={r.time_ns:r for r in owner if type(r) is ExportCANFrame}
            self.assertEqual((frames[10].frame.data[0],frames[100].frame.data[0]),(20,110))
        finally:
            owner.close()
        message=self.message(' SG_ Mux M : 0|4@1+ (1,0) [0|15] "" Node\n'
            ' SG_ V m1 : 8|8@1+ (1,0) [0|255] "V" Node\n'
            ' SG_ T m2 : 8|8@1+ (1,0) [0|255] "C" Node\n')
        rule=FrameRebuildRule(0,291,('V','T'),False,False)
        samples=[self.sample(10,0,10,layout=(('Mux',1),),data=b'\x01\x0aabcdef'),
            self.sample(60,1,60,layout=(('Mux',2),),values=(('T',60),),data=b'\x02\x3cabcdef'),
            self.sample(120,2,120,layout=(('Mux',1),),data=b'\x01\x78abcdef')]
        owner=self.rebuild(samples,rules=((rule,message),))
        try:
            rows=list(owner)
            self.assertEqual([r.time_ns for r in rows if type(r) is ExportCANFrame],[10,60,120])
            self.assertEqual(next(r.reason for r in rows if r.time_ns==100),'layout_changed')
        finally:
            owner.close()

    def test_unknown_passthrough_nearest_distance_and_stable_mix(self):
        """未知默认透传原顺序；开启最近邻后距离有限、等距取左，混合时间始终单调。参数: 无。返回: None。异常: 断言失败。
        """
        samples=[self.sample(10,0,10),self.sample(10,1,77,known=False,identifier=0x777),
            self.sample(65,2,66,identifier=0x444),self.sample(120,3,120),
            self.sample(120,4,88,known=False,identifier=0x777)]
        owner=self.rebuild(samples)
        try:
            rows=list(owner); actual=[r for r in rows if type(r) is ExportCANFrame]
            passthrough=[r for r in actual if r.frame_origin=='passthrough']
            self.assertEqual([r.sequence for r in passthrough],[1,2,4])
            self.assertEqual([r.time_ns for r in rows],sorted(r.time_ns for r in rows))
            at10=[r for r in actual if r.time_ns==10]
            self.assertEqual([r.frame_origin for r in at10],['passthrough','generated'])
        finally:
            owner.close()
        owner=self.rebuild([samples[1],samples[4]],grid=FrameGridSpec(25,15,110,'nearest',60))
        try:
            rows={r.time_ns:r for r in owner}
            self.assertEqual(rows[65].frame.data[0],77)
            self.assertEqual(rows[90].frame.data[0],88)
        finally:
            owner.close()
        owner=self.rebuild([samples[1],samples[4]],grid=FrameGridSpec(10,0,110,'nearest',15))
        try:
            rows={r.time_ns:r for r in owner}
            self.assertEqual(rows[30].reason,'neighbor_too_far')
            self.assertEqual(rows[0].frame.data[0],77)
        finally:
            owner.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_direction_channel_identity_and_failure_cleanup(self):
        """Rx和Tx不相互插值，其他通道原样保留；坏长度/时间/取消失败无残余自有费用。参数: 无。返回: None。异常: 断言失败。
        """
        samples=[self.sample(10,0,10),self.sample(20,1,80,is_rx=False),
            self.sample(50,2,50,channel=1),self.sample(120,3,120)]
        owner=self.rebuild(samples)
        try:
            rows=list(owner)
            at100=[r for r in rows if type(r) is ExportCANFrame and r.time_ns==100]
            self.assertEqual(len(at100),1)
            self.assertTrue(at100[0].frame.is_rx)
            self.assertEqual(at100[0].frame.data[0],100)
            self.assertTrue(any(type(r) is ExportCANFrame and r.frame.channel==1 and r.frame_origin=='passthrough' for r in rows))
        finally:
            owner.close()
        self.budget.reserve_ram(4096)
        for samples in ([self.sample(10,0,10,data=b'\x01')],[self.sample(20,0,20),self.sample(10,1,10)]):
            owner=self.rebuild(samples)
            with self.assertRaises(ValueError):
                owner.prepare()
            owner.close()
            self.assertEqual(self.budget.ram_bytes,4096)
        self.budget.release_ram(4096)

    def test_decimal_half_step_not_changed_by_float_interpolation(self):
        """0.1到0.6在9/10处为0.55；分辨率0.1时5.5码恰半取偶6，两后端一致。参数: 无。返回: None。异常: 断言失败。
        """
        message=self.message(' SG_ V : 0|8@1+ (0.1,0) [0|25.5] "V" Node\n')
        for backend in ('reference','numpy'):
            owner=self.rebuild([self.sample(0,0,0.1,data=b'\x01abcdefg'),self.sample(10,1,0.6,data=b'\x06abcdefg')],
                grid=FrameGridSpec(1,0,10),interval=Interval(0,11),backend=backend,message=message,
                rules=((FrameRebuildRule(0,291,('V',),False,False),message),))
            try:
                frames={r.time_ns:r for r in owner if type(r) is ExportCANFrame}
                self.assertEqual(frames[9].frame.data[0],6)
            finally:
                owner.close()

    def test_blf_generated_fd_and_manifest(self):
        """真正FD BLF回读保12字节基础帧、BRS/方向；清单包含重建范围和量化政策。参数: 无。返回: None。异常: 断言失败。
        """
        import can
        message=self.message(' SG_ V : 0|8@1+ (1,0) [0|255] "V" Node\n',length=12)
        message.is_fd=True  # 此用例模拟真实FD定义，实际帧仍保持FD标记。
        rule=FrameRebuildRule(0,291,('V',),False,True)
        samples=[self.sample(10*10**6,0,10,data=bytes((10,))+b'abcdefghijk',is_fd=True,bitrate_switch=True,is_rx=False),
            self.sample(120*10**6,1,120,data=bytes((120,))+b'ABCDEFGHIJK',is_fd=True,bitrate_switch=True,is_rx=False)]
        owner=self.rebuild(samples,grid=FrameGridSpec(10*10**6,0,110*10**6),interval=Interval(0,130*10**6),rules=((rule,message),))
        path=export_can_frames(owner,FrameExportSpec('blf',capture_date='2023-11-15',timezone_offset_minutes=480),
            Interval(0,130*10**6),self.root/'blf',self.budget,source='bus',device_label='home')
        reader=can.BLFReader(published_file(path,'frames.blf'))
        try:
            rows=list(reader)
        finally:
            reader.stop()
        row=next(r for r in rows if r.data[0]==100)
        self.assertEqual(bytes(row.data),b'dABCDEFGHIJK')
        self.assertTrue(row.is_fd and row.bitrate_switch)
        self.assertFalse(row.is_rx)
        info=json.loads((published_file(path,'manifest.json')).read_text(encoding='utf-8'))
        self.assertEqual(info['reconstruction']['period_ns'],10*10**6)
        self.assertEqual(info['reconstruction']['quantization'],'nearest_even-v1')
        self.assertEqual(info['generated'],12)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_budget_cancel_and_full_stream_memory_bound(self):
        """小预算/磁盘限制/取消均关闭；200与2000条不会按全输入规模增加RAM估算。参数: 无。返回: None。异常: 断言失败。
        """
        self.budget=ResourceBudget(memory_budget_bytes=10*1048576)
        with self.assertRaises(BudgetExceededError):
            self.rebuild([])
        self.assertEqual(self.budget.ram_bytes,0)
        self.budget=ResourceBudget(spool_quota_bytes=1024)
        owner=self.rebuild([self.sample(10,0,10),self.sample(120,1,120)])
        with self.assertRaises(BudgetExceededError):
            owner.prepare()
        self.assertEqual(self.budget.ram_bytes,0)
        self.budget=ResourceBudget(); self.budget.reserve_ram(4096)
        count=[0]; closed=[]
        def source():
            """提供带真实finally的源游标。参数: 无。返回: 样本生成器。异常: 无。
            """
            try:
                for i in range(10):
                    yield self.sample(i,i,i)
            finally:
                closed.append(True)
        def cancel():
            """原流已开始后取消。参数: 无。返回: None。异常: KeyboardInterrupt。
            """
            count[0]+=1
            if count[0]>=5:
                raise KeyboardInterrupt('用户取消')
        owner=self.rebuild(source(),cancel=cancel)
        with self.assertRaises(KeyboardInterrupt):
            owner.prepare()
        self.assertTrue(closed); self.assertEqual(self.budget.ram_bytes,4096)
        self.budget.release_ram(4096)
        peaks=[]
        for size in (200,2000):
            self.budget=ResourceBudget()
            owner=self.rebuild((self.sample(i,i,i%256) for i in range(size)),interval=Interval(0,size),grid=FrameGridSpec(1,0,2))
            try:
                self.assertEqual(sum(type(r) is ExportCANFrame for r in owner),size)
            finally:
                owner.close()
            peaks.append(self.budget.peak_ram_bytes)
            self.assertEqual(self.budget.ram_bytes,0)
        self.assertLess(peaks[1]-peaks[0],1048576)

    def test_primary_tamper_error_survives_persistent_real_close_failure(self):
        """摘要错误加真实句柄持续关闭失败，主错不被覆盖；恢复owner后全部资源归零。参数: 无。返回: None。异常: 断言失败。
        """
        original=Path.open; fail=[True]; streams=[]
        class BrokenRead:
            """保实际文件；只注入返回行认证字节变化及close故障。"""
            def __init__(self,stream):
                """保存实际FD。参数: stream。返回: None。异常: 无。"""
                self.stream=stream; self.first=True
            def __getattr__(self,name):
                """转交真实流属性。参数: name。返回: 属性。异常: 原访问错。"""
                return getattr(self.stream,name)
            def readline(self,size):
                """首行改变一个认证字节。参数: size。返回: bytes。异常: I/O错。"""
                row=self.stream.readline(size)
                if self.first and row:
                    self.first=False; row=(b'0' if row[:1]!=b'0' else b'1')+row[1:]
                return row
            def close(self):
                """恢复前拒关闭。参数: 无。返回: None。异常: OSError/I/O错。"""
                if fail[0]:
                    raise OSError('真实FD关闭失败')
                self.stream.close()
        def opened(path,*args,**kwargs):
            """仅替换分组run的读FD。参数: path及open参数。返回: 真实或故障流。异常: I/O错。"""
            stream=original(path,*args,**kwargs)
            if 'groups' in path.parts and args==('rb',):
                stream=BrokenRead(stream); streams.append(stream)
            return stream
        owner=self.rebuild([self.sample(0,0,0),self.sample(10,1,10)])
        with patch.object(Path,'open',opened):
            with self.assertRaisesRegex(ResultFormatError,'修改') as caught:
                owner.prepare()
        self.assertIs(caught.exception.frame_rebuild_cleanup_owner,owner)
        self.assertFalse(streams[0].stream.closed)
        fail[0]=False; owner.close()
        self.assertTrue(streams[0].stream.closed)
        self.assertEqual(self.budget.ram_bytes,0)
