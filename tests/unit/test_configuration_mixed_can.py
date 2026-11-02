"""[home] ASC/BLF同来源跨文件计算、追溯、导出和取消；原算法与时间解释保持。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from chronaxis import AnalysisPlan,AnalysisRunner,validate_analysis_plan
from chronaxis.sources.blf import BLFSpec,BLFRead
from chronaxis.sources.asc import ASCRead,ASCSpec
from chronaxis.results.budget import ResourceBudget


class ConfigurationMixedCANTests(unittest.TestCase):
    """实际三文件0/1/2秒3/1/3V，跨格式面积仍为4Vs。"""
    def setUp(self):
        """创建ASC、BLF、ASC各一帧；BLF通过现有写库生成。"""
        import can
        self.temp=TemporaryDirectory(prefix='chronaxis-mixed-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.inputs=self.root/'inputs';self.inputs.mkdir()
        self.epoch=1700000000
        (self.inputs/'part10.asc').write_text(f'base hex timestamps absolute\n{self.epoch+2} 1 100 Rx d 2 01 00\n',encoding='utf-8')
        (self.inputs/'part1.asc').write_text(f'base hex timestamps absolute\n{self.epoch} 1 100 Rx d 2 01 00\n',encoding='utf-8')
        with can.BLFWriter(self.inputs/'part2.blf') as writer:
            writer.on_message_received(can.Message(timestamp=self.epoch+1.,channel=0,arbitration_id=256,
                is_extended_id=False,data=b'\x00\x00'))
        self.dbc=Path(__file__).parents[2]/'src/chronaxis/configuration/templates/shared/sample.dbc'
        self.raw=dict(config_version=3,dataset=dict(name='mixed',domain=dict(start='0s',end='2s')),
            metadata={'device_label':'home'},
            sources=[dict(path=str(self.inputs),time=dict(offset='-1700000000s'),dbc_by_channel={'1':str(self.dbc)})],
            signals=[dict(name='voltage',field=dict(frame_id=256,signal='Voltage'),dtype='float64',unit='V',valid_for='3s')],
            calculations=[dict(name='area',operation='integral',expr='voltage')])

    def test_mixed_folder_single_dbc_load_two_backends(self):
        """目录自然序、共用DBC，两后端跨格式连续积分。"""
        import cantools
        from test_configuration_schema import ConfigurationSchemaTests
        ConfigurationSchemaTests.setUpClass()
        ConfigurationSchemaTests.validators['analysis.schema.json'].validate(self.raw)
        for backend in ('reference','numpy'):
            plan=AnalysisPlan.from_dict(self.raw)
            self.assertEqual(plan.sources[0].source_type,'asc_or_blf')
            self.assertTrue(validate_analysis_plan(plan).execution_ready)
            self.assertEqual([i.path.name for i in plan.sources[0].config.inputs],['part1.asc','part2.blf','part10.asc'])
            with patch('cantools.database.load_file',wraps=cantools.database.load_file) as load:
                with AnalysisRunner(backend).run(plan,work_dir=self.root/backend) as result:
                    self.assertEqual([r.value for r in result.iter_calculations()],[4.0])
                self.assertEqual(load.call_count,1)

    def test_per_file_offset_and_explicit_order(self):
        """偏移跟随文件，不因混合格式改变用户列出的顺序。"""
        source=self.raw['sources'][0]
        source.pop('path');source.pop('time')
        source['paths']=[{'path':str(self.inputs/name),'offset':'-1700000000s'}
                         for name in ('part1.asc','part2.blf','part10.asc')]
        plan=AnalysisPlan.from_dict(self.raw)
        with AnalysisRunner().run(plan,work_dir=self.root/'offsets') as result:
            self.assertEqual(next(result.iter_calculations()).value,4.)
        source['paths'].reverse()
        with self.assertRaisesRegex(Exception,'回退'):
            with AnalysisRunner().run(AnalysisPlan.from_dict(self.raw),work_dir=self.root/'reverse'):pass

    def test_cross_format_hysteresis_and_fixed_interval(self):
        """BLF中的1V解除ASC中的3V报警；固定周期积分仍遵守选定0.1秒。"""
        for backend in ('reference','numpy'):
            self.raw['rules']=[dict(name='alarm',rule_type='hysteresis',
                enter_condition='voltage >= 2',exit_condition='voltage <= 1')]
            self.raw['intervals']={'default':{'mode':'fixed','value':'0.1s','driver':'voltage'}}
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(self.raw),work_dir=self.root/('rules-'+backend)) as result:
                self.assertAlmostEqual(next(result.iter_calculations()).value,.4)
                events=tuple(result.iter_events())
                self.assertTrue(any(e.start_ns==0 and e.end_ns==10**9 for e in events))

    def test_direct_trace_does_not_invent_binary_line_or_text(self):
        """显式底层追溯可往返历史编码；BLF只有文件内序号。"""
        from chronaxis.sources.text_can_decode import CANTextDecodeRead,pack_text_records
        from chronaxis.results.codec import _pack,_unpack
        plan=AnalysisPlan.from_dict(self.raw);budget=ResourceBudget()
        definition=plan.signals[0].definition
        with CANTextDecodeRead(plan.sources[0].config,budget,(definition,)) as reader:
            records=tuple(reader)
        series=pack_text_records(definition,records,plan.dataset.session_id,'reference')
        ref=series.source_ref[1]
        self.assertEqual((ref.parser_version,ref.line_number,ref.record_sequence,ref.raw_time),('blf-v1',None,0,None))
        self.assertEqual(_unpack(_pack(ref)),ref)
        self.assertEqual(budget.ram_bytes,0)

    def test_explicit_trace_and_raw_export_keep_binary_position(self):
        """请求追溯时保留BLF记录序号，不伪造物理行；原帧可经共同出口导出。"""
        self.raw['diagnostics']={'trace':True,'integrity':True}
        self.raw['outputs']={'can_frames':{'format':'asc','output_offset':'-1700000000s'}}
        with AnalysisRunner().run(AnalysisPlan.from_dict(self.raw),work_dir=self.root/'trace') as result:
            self.assertEqual(next(result.iter_calculations()).value,4.)
            rows=tuple(result.iter_input_trace())
            self.assertEqual(len(rows),3)
            result.write(self.root/'published')
        outputs=list((self.root/'published').rglob('frames.asc'))
        self.assertEqual(len(outputs),1)
        budget=ResourceBudget()
        with ASCRead(ASCSpec(outputs[0]),budget) as read:
            rows=list(read)
        self.assertEqual([r.time_ns for r in rows],[0,10**9])
        self.assertEqual(budget.ram_bytes,0)

    def test_blf_reader_cancel_bad_header_and_eof_cleanup(self):
        """直接读取只持有当前文件；缺文件、坏头、预算或取消不遗留资源。"""
        budget=ResourceBudget();spec=BLFSpec(self.inputs/'part2.blf',-self.epoch*10**9)
        read=BLFRead(spec,budget,retain_source_time=True)
        row=next(read)
        self.assertEqual((row.time_ns,row.sequence,row.line_number,row.raw_time),(10**9,0,None,None))
        self.assertEqual(row.source_time_ns,(self.epoch+1)*10**9)
        self.assertEqual(list(read),[]);self.assertTrue(read.closed)
        self.assertEqual(budget.ram_bytes,0)
        bad=self.root/'bad.blf';bad.write_bytes(b'bad')
        with self.assertRaises(Exception):BLFRead(BLFSpec(bad),budget)
        self.assertEqual(budget.ram_bytes,0)
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):BLFRead(spec,budget,check_cancel=cancel)
        self.assertEqual(budget.ram_bytes,0)
        read=BLFRead(spec,budget)
        read._check_cancel=cancel
        with self.assertRaisesRegex(RuntimeError,'cancelled'):next(read)
        self.assertTrue(read.closed);self.assertEqual(budget.ram_bytes,0)

    def test_resolved_configuration_reloads_mixed_paths(self):
        """配置工具展开默认后仍可加载混合来源，不将它误判为单一BLF。"""
        import json
        from chronaxis.configuration.resolution import resolved_configuration
        path=self.root/'plan.json';path.write_text(json.dumps(self.raw),encoding='utf-8')
        for defaults in (False,True):
            resolved=resolved_configuration(path,defaults=defaults)
            self.assertEqual(AnalysisPlan.from_dict(resolved).sources[0].source_type,'asc_or_blf')
