"""公开AnalysisRunner原帧导出三格式对照、窗口范围、重复发布与取消清理。"""

from configuration_fixtures import current_fixture
import json
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisRunner,validate_analysis_plan
from chronaxis.results import AnalysisError
from chronaxis.sources.asc import ASCRead,ASCSpec
from chronaxis.results.budget import ResourceBudget
import test_record_runner as raw_cases

class RecordFrameExportTests(unittest.TestCase):
    """借同一数据核实际导出内容；原文件不修改也不重复解码。"""
    setUp=raw_cases.RecordRunnerTests.setUp
    asc=raw_cases.RecordRunnerTests.asc
    csv=raw_cases.RecordRunnerTests.csv
    blf=raw_cases.RecordRunnerTests.blf
    fixtures=raw_cases.RecordRunnerTests.fixtures
    plan=raw_cases.RecordRunnerTests.plan

    def export_option(self,raw,scope='session'):
        """请求独立原帧文件。参数: 配置/范围。返回: None。异常: 无。"""
        source=raw['sources'][0]
        raw['outputs']['can_frames']=dict(source=source['name'],format='asc',scope=scope)
        if source['source_type']=='can_blf':
            # BLF为原UTC时间；导出保原时刻，这里明确移回0起点用于三格式比较。
            raw['outputs']['can_frames']['output_offset']='-1700000000s'
        if scope=='segments':
            raw['rules']=[dict(name='edge',rule_type='rising_edge',condition='current >= 12')]
            raw['windows']=[dict(name='around',rule='edge',anchor='point',pre='0.1s',post='0.1s')]
            raw['outputs']['can_frames']['window']='around'

    def test_three_formats_session_and_segment_republish(self):
        """真实0/0.12秒两帧位于半开0—0.3范围；末端帧不外扩，重复发布一致。"""
        for kind,path in self.fixtures().items():
            for scope in ('session','segments'):
                def edit(raw): self.export_option(raw,scope)
                plan=self.plan(kind,path,'fixed',edit)
                self.assertTrue(validate_analysis_plan(plan).execution_ready)
                from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
                from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
                adapter=BudgetedLegacyCANSourceAdapter if kind=='can_blf' else BudgetedTextCANSourceAdapter
                original=adapter.iter_batches;scans=[]
                def scan(owner,*args,**kwargs):
                    """只记录真实入口调用，不替换数据。参数: 原调用。返回: 原reader。异常: 原错。"""
                    scans.append(owner);return original(owner,*args,**kwargs)
                with patch.object(adapter,'iter_batches',scan):
                    result=AnalysisRunner().run(plan,self.root/uuid4().hex)
                self.assertEqual(len(scans),1)
                self.addCleanup(result.close)
                for unused in range(2):
                    destination=self.root/uuid4().hex;result.write(destination)
                    inventory=[json.loads(line) for line in (destination/'exports.jsonl').read_text(encoding='utf-8').splitlines()]
                    self.assertEqual(len(inventory),1)
                    output=destination/'exports'/inventory[0]['directory']
                    self.assertEqual({f.name for f in output.iterdir()},{'frames.asc','manifest.json'})
                    budget=ResourceBudget()
                    with ASCRead(ASCSpec(output/'frames.asc'),budget) as reader: rows=list(reader)
                    self.assertEqual([r.frame.data for r in rows],[bytes([200,10]),bytes([200,12])])
                    self.assertAlmostEqual(rows[1].time_ns/1e9,.12,places=5)
                budget=result.spool.budget;result.close();self.assertEqual(budget.ram_bytes,0)

    def test_export_only_and_empty(self):
        """没有分析消费者时仅读取原帧，不要求假指标/信号历史，空来源写空文件。"""
        fixtures=self.fixtures()
        for path in (fixtures['can_asc'],self.asc('').path):
            def edit(raw):
                self.export_option(raw);raw['calculations']=[];raw['intervals']={'default':{'mode':'actual'}}
            with AnalysisRunner().run(self.plan('can_asc',path,'actual',edit),self.root/uuid4().hex) as result:
                self.assertEqual(result.spool.tables,())
                output=self.root/uuid4().hex;result.write(output)
                self.assertTrue((output/'exports.jsonl').is_file())

    def test_cancel_after_actual_export_cleans_all(self):
        """已生成真实文件后取消也不返回成功前缀，全部owner关闭并释放。"""
        from chronaxis.execution.record_exports import RecordExports
        original=RecordExports._export;budgets=[]
        def cancel(owner,*args,**kwargs):
            budgets.append(owner._budget);original(owner,*args,**kwargs);raise KeyboardInterrupt('synthetic export cancel')
        path=self.fixtures()['can_asc']
        with patch.object(RecordExports,'_export',cancel):
            with self.assertRaises(KeyboardInterrupt):
                AnalysisRunner().run(self.plan('can_asc',path,'fixed',self.export_option),self.root/uuid4().hex)
        self.assertTrue(budgets);self.assertTrue(all(b.ram_bytes==0 for b in budgets))

    def test_rebuild_fixed_and_dbc_three_formats(self):
        """只修改电流位；0.1秒插值得11.666A，量化为12；电压位保持C8。"""
        for kind,path in self.fixtures().items():
            for backend in ('reference','numpy'):
                for period in ('0.1s',{'mode':'dbc'}):
                    def edit(raw):
                        self.export_option(raw)
                        raw['calculations']=[];raw['intervals']={'default':{'mode':'actual'}}
                        raw['outputs']['can_frames']['resampling']={'period':period,'max_gap':'1s','messages':[
                            {'channel':1,'frame_id':256,'is_extended':False,'is_fd':False,'continuous':['Current'],'protected':['Voltage']}]}
                    with self.subTest(kind=kind,backend=backend,period=period):
                        result=AnalysisRunner(backend).run(self.plan(kind,path,'actual',edit),self.root/uuid4().hex)
                        self.addCleanup(result.close)
                        out=self.root/uuid4().hex;result.write(out)
                        inventory=json.loads((out/'exports.jsonl').read_text(encoding='utf-8').strip())
                        directory=out/'exports'/inventory['directory']
                        budget=ResourceBudget()
                        with ASCRead(ASCSpec(directory/'frames.asc'),budget) as reader:rows=list(reader)
                        self.assertEqual([r.time_ns for r in rows],[0,100000000])
                        self.assertEqual([r.frame.data for r in rows],[bytes([200,10]),bytes([200,12])])
                        manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
                        self.assertEqual(manifest['skipped_grid_points'],1)
                        if type(period) is dict:
                            self.assertEqual(manifest['reconstruction']['rules'][0]['period_ns'],100000000)
                            self.assertEqual(manifest['reconstruction']['period_mode'],'dbc')
                        self.assertFalse((directory/'frames.jsonl').exists())
                        held=result.spool.budget;result.close();self.assertEqual(held.ram_bytes,0)

    def test_frame_dbc_grid_independent_message_periods(self):
        """100ms报文和200ms报文各用自身网格，不把较慢报文重复到100ms。"""
        import cantools
        from chronaxis.results.frame_rebuild import FrameSample,FrameGridSpec,FrameRebuildRead
        from chronaxis.results.frame_patch import FrameRebuildRule
        from chronaxis.results.frame_exports import as_export_frame,ExportCANFrame
        from chronaxis.core.models import Interval
        from test_frame_exports import raw
        dbc='VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
        for identifier,name in ((291,'First'),(292,'Second')):
            dbc+=f'BO_ {identifier} {name}: 8 Node\n SG_ V : 0|8@1+ (1,0) [0|255] "V" Node\n'
        dbc+='BA_DEF_ BO_ "GenMsgCycleTime" INT 0 10000;\nBA_ "GenMsgCycleTime" BO_ 291 100;\nBA_ "GenMsgCycleTime" BO_ 292 200;\n'
        database=cantools.database.load_string(dbc,database_format='dbc')
        rules=tuple((FrameRebuildRule(0,i,('V',),False,False),database.get_message_by_frame_id(i)) for i,n in ((291,'First'),(292,'Second')))
        samples=[]
        for time in (0,400000000):
            for identifier in (291,292):
                value=0 if time==0 else 40
                frame=raw(time,len(samples),data=bytes([value])+bytes.fromhex('aabbccddeeff01'),identifier=identifier)
                samples.append(FrameSample(as_export_frame(frame),(('V',value),),(),True))
        for backend in ('reference','numpy'):
            budget=ResourceBudget();owner=FrameRebuildRead(samples,FrameGridSpec(None,0,1000000000),Interval(0,400000001),rules,budget,self.root/uuid4().hex,backend=backend)
            try:
                rows=list(owner)
                self.assertTrue(all(type(r) is ExportCANFrame for r in rows))
                self.assertEqual([r.time_ns for r in rows if r.frame.arbitration_id==291],[0,100000000,200000000,300000000,400000000])
                self.assertEqual([r.time_ns for r in rows if r.frame.arbitration_id==292],[0,200000000,400000000])
                self.assertTrue(all(r.frame.data[1:]==bytes.fromhex('aabbccddeeff01') for r in rows))
            finally:owner.close()
            self.assertEqual(budget.ram_bytes,0)
        with self.assertRaisesRegex(ValueError,'未知报文'):
            FrameGridSpec(None,0,1000000000,'nearest',100000000)

    def test_dbc_missing_cycle_fails_before_reading_and_releases(self):
        """DBC周期缺失时首帧前失败，不留下未释放编码上下文。"""
        from chronaxis.execution.frame_capture import FrameDBCContext
        from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
        path=self.fixtures()['can_asc']
        self.dbc.write_text(self.dbc.read_text(encoding='utf-8').replace('BA_ "GenMsgCycleTime" BO_ 256 100;', ''),encoding='utf-8')
        def edit(raw):
            self.export_option(raw)
            raw['outputs']['can_frames']['resampling']={'period':{'mode':'dbc'},'max_gap':'1s','messages':[
                {'channel':1,'frame_id':256,'is_extended':False,'is_fd':False,'continuous':['Current']}]}
        budgets=[];original=FrameDBCContext.__init__
        def capture(owner,*args,**kwargs):
            budgets.append(args[2]);return original(owner,*args,**kwargs)
        with patch.object(FrameDBCContext,'__init__',capture), patch.object(BudgetedTextCANSourceAdapter,'iter_batches',side_effect=AssertionError('首帧前不可打开reader')):
            with self.assertRaisesRegex(AnalysisError,'周期'):
                AnalysisRunner().run(self.plan('can_asc',path,'actual',edit),self.root/uuid4().hex)
        self.assertTrue(budgets);self.assertTrue(all(b.ram_bytes==0 for b in budgets))

    def test_current_segment_export_preserves_all_windows_and_epoch(self):
        """当前全部片段导出：零/一/多窗口不改成整会话或擅自只选一个。"""
        from chronaxis import AnalysisPlan,PlanValidationError
        from copy import deepcopy
        import can
        from jsonschema import Draft202012Validator
        from pathlib import Path
        schema=json.loads(Path('Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        path=self.fixtures()['can_blf']
        for count in (0,1,2):
            configs=[]
            def edit(raw):
                raw.update(config_version=3);raw.pop('intervals',None)
                raw['calculations']=[]
                raw['rules']=[dict(name='edge',rule_type='rising_edge',condition='current >= 12')]
                raw['windows']=[dict(name=f'w{i}',rule='edge',anchor='point',pre='0.1s',post='0.1s') for i in range(count)]
                raw['outputs']['can_frames']={'source':raw['sources'][0]['name'],'format':'blf',
                    'scope':'segments','source_time_reference':'epoch'}
                configs.append(current_fixture(deepcopy(raw)))
            plan=self.plan('can_blf',path,'actual',edit)
            Draft202012Validator(schema).validate(configs[0])
            self.assertIsNone(plan.outputs.can_frames.window)
            self.assertEqual(plan.outputs.can_frames.spec.source_time_reference,'epoch')
            with AnalysisRunner().run(plan,self.root/uuid4().hex) as result:
                dest=self.root/uuid4().hex;result.write(dest)
                index=dest/'exports.jsonl'
                rows=[json.loads(line) for line in index.read_text(encoding='utf-8').splitlines()]
                self.assertEqual(len(rows),count)
                for row in rows:
                    with can.BLFReader(dest/'exports'/row['directory']/'frames.blf') as reader:frames=list(reader)
                    self.assertEqual(len(frames),1)
                    self.assertAlmostEqual(frames[0].timestamp,1700000000.12,places=5)
                    self.assertEqual(frames[0].data,bytes([200,12]))
        bad=deepcopy(configs[0]);bad['outputs']['can_frames']['window']=None
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(current_fixture(bad))

    def test_default_rebuild_does_not_compute_optional_internal_hashes(self):
        """默认三格式重采样不做排序逐行MAC、原帧仓SHA或额外DBC整文件哈希。"""
        from contextlib import ExitStack
        for kind,path in self.fixtures().items():
            def edit(raw):
                self.export_option(raw)
                raw['outputs']['can_frames']['resampling']={'period':'0.1s','max_gap':'1s','messages':[
                    {'channel':1,'frame_id':256,'is_extended':False,'is_fd':False,'continuous':['Current']}]}
            with ExitStack() as stack:
                for target in ('chronaxis.results.frame_sort.FrameSort._mac','chronaxis.legacy.raw_store.sha256',
                    'chronaxis.legacy.message_store.sha256','chronaxis.execution.frame_capture.FrameDBCContext._hash',
                    'chronaxis.sources.text_can_decode.file_digest'):
                    stack.enter_context(patch(target,side_effect=AssertionError('未请求内容完整性诊断')))
                with AnalysisRunner().run(self.plan(kind,path,'fixed',edit),self.root/uuid4().hex) as result:
                    self.assertAlmostEqual(next(result.iter_calculations()).value,880,places=3)
                    output=self.root/uuid4().hex;result.write(output)
                    self.assertTrue((output/'exports.jsonl').exists())

    def test_plain_internal_sort_still_rejects_truncated_end(self):
        """关闭MAC不关闭结构/结尾验证；完整末行缺失不能当成功EOF。"""
        from chronaxis.results.frame_sort import FrameSort
        from chronaxis.results.errors import ResultFormatError
        budget=ResourceBudget();owner=FrameSort(self.root/uuid4().hex,budget,integrity=False,buffer_rows=2)
        try:
            for value in (4,1,3,2):owner.append((value,),{'value':value})
            owner.seal()
            path=owner.path/f'{owner.level}-0.jsonl'
            rows=list(owner._read(path));self.assertEqual([r[2]['value'] for r in rows],[1,2,3,4])
            content=path.read_bytes();path.write_bytes(content.rsplit(b'\n',2)[0]+b'\n')
            with self.assertRaises(ResultFormatError):list(owner._read(path))
        finally:owner.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_default_reconstruction_does_not_build_provenance_or_quantization_report(self):
        """从生成点检查量化事实和原帧旁证确实为空，仍生成正确帧。"""
        from chronaxis.results.frame_patch import DBCFramePatch
        from chronaxis.results.frame_rebuild import FrameRebuildRead,_frame_packet
        original_patch=DBCFramePatch.patch;original_output=FrameRebuildRead._output
        seen=[]
        def encode(owner,*args,**kwargs):
            self.assertFalse(kwargs['trace'])
            result=original_patch(owner,*args,**kwargs);self.assertEqual(result[1],())
            seen.append('quantization');return result
        def output(owner,record,identity):
            if hasattr(record,'provenance'):
                self.assertEqual(record.provenance,())
                packet=_frame_packet(record)
                self.assertNotIn('provenance',packet);self.assertNotIn('timestamp',packet['frame'])
                if record.time_ns==record.output_time_ns:self.assertNotIn('output_time_ns',packet)
                seen.append('frame')
            return original_output(owner,record,identity)
        path=self.fixtures()['can_asc']
        def edit(raw):
            self.export_option(raw)
            raw['outputs']['can_frames']['resampling']={'period':'0.1s','max_gap':'1s','messages':[
                {'channel':1,'frame_id':256,'is_extended':False,'is_fd':False,'continuous':['Current']}]}
        with patch.object(DBCFramePatch,'patch',encode),patch.object(FrameRebuildRead,'_output',output):
            with AnalysisRunner().run(self.plan('can_asc',path,'fixed',edit),self.root/uuid4().hex) as result:
                result.write(self.root/uuid4().hex)
        self.assertIn('quantization',seen);self.assertIn('frame',seen)
