"""验证文本CAN公共接线的真实批次、同次观测和可选原帧保存。

合成DBC沿C1夹具，预期电压3/7V来自raw*2+1手算；只写work新目录。
device_label: home。公共配置、AnalysisRunner及输出发布用例随C2接线补齐。
"""

from configuration_fixtures import current_fixture

from dataclasses import replace
from unittest.mock import patch
import unittest
import json
import csv

import test_text_can_decode as fixtures
from test_can_planning import can_config
from chronaxis import AnalysisPlan,AnalysisRunner,validate_analysis_plan,explain_analysis_plan,PlanValidationError
from pathlib import Path
from copy import deepcopy
import subprocess
import sys
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.text_can_spec import CANTextSpec
from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
from chronaxis.execution.frame_capture import FrameDBCContext
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.observed_ingestion import ObservedSourceScan
from chronaxis.results.frame_patch import FrameRebuildRule
from chronaxis.results.errors import ResultClosedError


class TextCANPublicTests(unittest.TestCase):
    """每项使用独立文件、实际解析器与共享账本，不以伪造EOF证明完成。"""

    setUp=fixtures.TextCANDecodeTests.setUp
    asc=fixtures.TextCANDecodeTests.asc
    csv=fixtures.TextCANDecodeTests.csv

    def config(self,parser):
        """生成新ASC公共声明。参数: parser真实ASC路径。返回: dict。异常: 无。
        """
        config=can_config()
        config['sources']=[dict(name='bus',source_type='can_asc',path=str(parser.path.resolve()),
            dbc_by_channel={'1':str(self.dbc.resolve())},time=dict(time_type='relative',unit='s',origin='synthetic'))]
        config['signals']=[dict(name='voltage',source='bus',field=dict(channel=1,
            signal='Voltage',frame_id=256,is_extended=False,is_fd=False),dtype='float64',unit='V',
            valid_for='10s',same_time_policy='last_by_sequence')]
        config['diagnostics']={'trace':True,'integrity':True}
        config['derived']={}; config['rules']=[]; config['windows']=[]
        config['calculations']=[dict(name='area',scope='session',operation='integral',expr='voltage',unit='V*s')]
        return config

    def test_actual_batches_and_observation_require_full_eof(self):
        """跨批同刻与空投影保留真实范围，EOF批不等同已完成。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc('0.000000001 1 100 Rx d 2 01 05\n0.000000001 1 100 Rx d 2 03 06\n2 1 777 Rx d 1 ff\n')
        spec=CANTextSpec('bus',(parser,),self.dbc,0,self.timebase)
        for projection in (('voltage','alias'),()):
            adapter=BudgetedTextCANSourceAdapter(self.budget,spec,'session',
                (self.signal,replace(self.signal,name='alias')),work_dir=self.root)
            read=adapter.iter_batches_with_observation(ReadRequest('session',projection,0,3*10**9,1))
            values={name:[] for name in projection}
            for batch in read:
                self.assertLessEqual(batch.sample_count,1)
                for name,series in batch.series.items():
                    values[name].extend(series.values.tolist())
                with self.assertRaises(ResultClosedError):
                    read.observation
            self.assertEqual((read.observation.first_ns,read.observation.last_ns,read.observation.row_count),(1,2*10**9,3))
            # 空投影没有信号消费者，保留观测范围但不解码声明中的无用值。
            self.assertEqual(read.runtime_metadata['decode_calls'],2 if projection else 0)
            for rows in values.values():
                self.assertEqual(rows,[3.0,7.0])
            adapter.close(); self.assertEqual(self.budget.ram_bytes,0)

    def test_same_scan_history_and_raw_replay_share_one_dbc_load(self):
        """新DBC上下文同次解码并保原帧，重复输出范围不重读来源。参数: 无。返回: None。异常: 断言失败。
        """
        import cantools
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 777 Rx d 1 ff\n')
        plan=AnalysisPlan.from_dict(current_fixture(self.config(parser))); source=plan.sources[0]
        rule=FrameRebuildRule(0,256,('Voltage',),False,False)
        with patch('cantools.database.load_file',wraps=cantools.database.load_file) as load:
            context=FrameDBCContext(source.config.dbc_path,(rule,),self.budget)
            adapter=BudgetedTextCANSourceAdapter(self.budget,source.config,plan.dataset.session_id,
                tuple(s.definition for s in plan.signals),work_dir=self.root,retain_raw_frames=True,database_context=context)
            request=ReadRequest(plan.dataset.session_id,('voltage',),0,4*10**9,1)
            history=DecodedHistoryStore(self.budget,self.root/'history',(adapter.describe(),),{'bus':request})
            scan=ObservedSourceScan(history,source,adapter,request)
            scan.consume(); history.seal()
            self.assertEqual(scan.observation.row_count,3)
            self.assertEqual(load.call_count,1)
            first=tuple(scan._raw_store.iter_samples()); second=tuple(scan._raw_store.iter_samples())
            self.assertEqual(first,second)
            self.assertEqual(first[0].values,(('Voltage',3),))
            self.assertEqual([s.record.sequence for s in first],[0,1,2])
            scan.close(); adapter.close(); history.close(); context.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_missing_input_releases_read_and_adapter(self):
        """真实打开失败释放读取预算且不产生完成证明。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc(''); parser.path.unlink()
        spec=CANTextSpec('bus',(parser,),self.dbc,0,self.timebase)
        adapter=BudgetedTextCANSourceAdapter(self.budget,spec,'session',(self.signal,))
        read=adapter.iter_batches(ReadRequest('session',('voltage',),0,10,1))
        with self.assertRaises(OSError):
            next(read)
        self.assertTrue(read.closed); adapter.close()
        self.assertEqual(self.budget.ram_bytes,0)

    def test_public_runner_integral_and_true_metadata(self):
        """ASC公共API得到手算10Vs且清单保真实DBC/观测。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 777 Rx d 1 ff\n')
        config=self.config(parser); config['dataset']['domain']['end']='2s'
        for backend in ('reference','numpy'):
            config['execution']['backend']=backend
            plan=AnalysisPlan.from_dict(current_fixture(config))
            self.assertTrue(validate_analysis_plan(plan).execution_ready)
            result=AnalysisRunner().run(plan,work_dir=self.root/('run-'+backend))
            try:
                rows=list(result.iter_calculations())
                self.assertEqual(len(rows),1); self.assertEqual(rows[0].value,10.0)
                # 明确请求的诊断只描述所需解码记录流，未知原帧不伪装为信号记录。
                metadata=result.metadata.input_diagnostics[0]
                self.assertEqual((metadata.record_count,metadata.source_eof),(2,True))
                self.assertEqual(metadata.aliases,('voltage',))
                self.assertEqual(metadata.digest_scope,'required-decoded-records-v1')
                self.assertEqual(len(metadata.sha256),64)
            finally:
                result.close()

    def test_actual_observed_tail_expires_but_fixed_does_not_add_a_period(self):
        """0/1秒的3/7V加2秒未知帧：actual为10Vs，500ms有效期为5Vs，fixed仍只有3Vs。

        参数: 无。返回: None。异常: 尾段丢失、TTL被延长、虚构周期或资源泄漏。
        """
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 777 Rx d 1 ff\n')
        for backend in ('reference','numpy'):
            for mode,valid_for,expected in (('actual','10s',10.),('actual','500ms',5.),('fixed','10s',3.)):
                with self.subTest(backend=backend,mode=mode,valid_for=valid_for):
                    config=self.config(parser);config['dataset']['domain']['end']='4s'
                    config['execution']['backend']=backend
                    config['signals'][0]['valid_for']=valid_for
                    if mode=='fixed':
                        config['intervals']={'default':{'mode':'fixed','value':'1s','driver':'voltage'}}
                    result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),
                        work_dir=self.root/f'tail-{backend}-{mode}-{valid_for}')
                    budget=result.spool.budget
                    try:
                        self.assertEqual(next(result.iter_calculations()).value,expected)
                        self.assertEqual(len(tuple(result.iter_input_trace())),2)
                    finally:
                        result.close()
                    self.assertEqual(budget.ram_bytes,0)

    def test_public_independent_grids_and_repeat_publication(self):
        """信号250ms与报文500ms独立导出，重发不再解码。参数: 无。返回: None。异常: 断言失败。
        """
        import cantools
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 777 Rx d 1 ff\n')
        config=self.config(parser); config['dataset']['domain']['end']='2s'
        config['outputs']={'signal_csv':{'signals':['voltage'],'resampling':{
            'continuous':['voltage'],'period':'250ms','max_gap':'2s'}},
            'can_frames':{'source':'bus','format':'asc','resampling':{'period':'500ms','max_gap':'2s',
                'messages':[dict(channel=1,frame_id=256,is_extended=False,is_fd=False,continuous=['Voltage'])]}}}
        with patch('cantools.database.load_file',wraps=cantools.database.load_file) as load:
            result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/'run-exports')
            budget=result.spool.budget
            try:
                self.assertEqual(load.call_count,1)
                for name in ('published','published-again'):
                    destination=self.root/name; result.write(destination)
                    records=[json.loads(line) for line in (destination/'exports.jsonl').read_text(encoding='utf-8').splitlines()]
                    self.assertEqual([r['export_type'] for r in records],['signal_csv','can_frames'])
                    signals=destination/'exports'/records[0]['directory']
                    frames=destination/'exports'/records[1]['directory']
                    with (signals/'resampled.csv').open(encoding='utf-8',newline='') as handle:
                        rows=list(csv.DictReader(handle))
                    self.assertEqual(len(rows),8)
                    self.assertEqual(float(rows[2]['value']),5.0)
                    frame_manifest=json.loads((frames/'manifest.json').read_text(encoding='utf-8'))
                    self.assertEqual(frame_manifest['frames'],3)
                    self.assertEqual(frame_manifest['reconstruction']['period_ns'],500000000)
                self.assertEqual(load.call_count,1)
            finally:
                result.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_raw_csv_public_runner_uses_explicit_layout_and_time(self):
        """原始CSV同帧输入经公共API得到相同10Vs，原行信息仍在清单。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.csv('0,100,01 05,2\n1,100,03 06,2\n2,777,ff,1\n')
        config=self.config(parser); config['dataset']['domain']['end']='2s'
        source=config['sources'][0]; source['source_type']='raw_can_csv'
        source['reader']={'layout':parser.layout.to_dict(),'time_format':'numeric','id_base':parser.id_base}
        plan=AnalysisPlan.from_dict(current_fixture(config))
        result=AnalysisRunner().run(plan,work_dir=self.root/'run-csv')
        try:
            self.assertEqual(list(result.iter_calculations())[0].value,10.0)
            self.assertEqual(result.metadata.input_diagnostics[0].source_type,'raw_can_csv')
        finally:
            result.close()

    def test_public_csv_clock_exports_blf_with_actual_capture_date(self):
        """日内毫秒加微秒经真实公共入口写BLF，日期时区仅用于输出。参数: 无。返回: None。异常: 断言失败。
        """
        import can
        from datetime import datetime, timezone, timedelta
        parser=self.csv('14:05:40.151.2,100,01 05,2\n14:05:41.151.2,100,03 06,2\n14:05:42.151.2,777,ff,1\n')
        config=self.config(parser)
        config['dataset']['domain']={'start':'0s','end':'2s'}
        source=config['sources'][0]; source['source_type']='raw_can_csv'
        source['time']['offset']='-50740.151002s'
        source['reader']={'layout':parser.layout.to_dict(),'time_format':'clock-ms-us-v1','id_base':parser.id_base}
        config['outputs']={'can_frames':{'source':'bus','format':'blf',
            'capture_date':'2026-10-23','timezone_offset_minutes':480}}
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/'clock-blf-run')
        budget=result.spool.budget
        try:
            self.assertEqual(list(result.iter_calculations())[0].value,10.0)
            destination=self.root/'clock-blf-published'; result.write(destination)
            record=json.loads((destination/'exports.jsonl').read_text(encoding='utf-8'))
            directory=destination/'exports'/record['directory']
            with can.BLFReader(directory/'frames.blf') as reader:
                frames=list(reader)
            self.assertEqual(len(frames),2)
            expected=datetime(2026,10,23,14,5,40,151002,tzinfo=timezone(timedelta(hours=8))).timestamp()
            for index,frame in enumerate(frames):
                self.assertAlmostEqual(frame.timestamp,expected+index,places=6)
            # 原时间由真实BLF帧证明；分析时间来自明确请求的追溯，不额外生成双时间侧表。
            self.assertEqual([row.time_ns for row in result.iter_input_trace()],[0,10**9])
        finally:
            result.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_checked_in_examples_schema_run_and_outputs(self):
        """仓库两份配置与同帧BLF等价，3/7/3V手算13Vs且报警仅[1,2)。参数: 无。返回: None。异常: 断言失败。
        """
        import jsonschema
        import can
        from chronaxis import load_analysis_plan
        from chronaxis.legacy.records import PROFILE_ID
        root=Path(__file__).resolve().parents[2]
        validator=jsonschema.Draft202012Validator(json.loads((root/'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8')))
        for name in ('asc','csv','blf'):
            path=root/f'examples/m3_text_input/{name if name!="blf" else "asc"}-plan.json'
            self.assertEqual(list(validator.iter_errors(json.loads(path.read_text(encoding='utf-8')))),[])
            plan=load_analysis_plan(path)
            if name=='blf':
                # 同样的四帧交原BLF writer，归零分析；旧读取/解码调用保持原链。
                input_path=self.root/'example.blf'
                with can.BLFWriter(input_path) as writer:
                    for time,identity,payload in ((0,256,b'\x01\x05'),(1,256,b'\x03\x06'),(2,256,b'\x01\x07'),(3,1911,b'\xff')):
                        writer.on_message_received(can.Message(timestamp=1700000000+time,arbitration_id=identity,data=payload,is_extended_id=False,channel=0))
                config=json.loads(path.read_text(encoding='utf-8')); source=config['sources'][0]
                source.update(source_type='can_blf',path=str(input_path.resolve()),legacy_profile=PROFILE_ID,decode_scope='requested')
                source.pop('reader'); source['time']['offset']='-1700000000s'
                config['outputs']['can_frames']['source_time_reference']='epoch'
                plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=path.parent)
            result=AnalysisRunner().run(plan,work_dir=self.root/f'example-{name}-run')
            budget=result.spool.budget
            try:
                self.assertEqual(list(result.iter_calculations())[0].value,13.0)
                events=list(result.iter_events())
                self.assertEqual([(row.start_ns,row.end_ns) for row in events],[(10**9,2*10**9)])
                destination=self.root/f'example-{name}-out'; result.write(destination)
                records=[json.loads(line) for line in (destination/'exports.jsonl').read_text(encoding='utf-8').splitlines()]
                self.assertEqual({row['export_type'] for row in records},{'signal_csv','can_frames'})
                signal=next(row for row in records if row['export_type']=='signal_csv')
                with (destination/'exports'/signal['directory']/'resampled.csv').open(encoding='utf-8',newline='') as stream:
                    rows=[row for row in csv.DictReader(stream) if row['status']=='observed']
                self.assertEqual([(int(r['time_ns']),float(r['value'])) for r in rows],[(0,3.),(10**9,7.),(2*10**9,3.)])
            finally:
                result.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_text_asc_offset_changes_filter_but_preserves_export_clock(self):
        """ASC归零用于分析，原帧与重建帧仍输出原100秒起点。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc('100 1 100 Rx d 2 01 05\n101 1 100 Rx d 2 03 06\n102 1 777 Rx d 1 ff\n')
        config=self.config(parser); config['dataset']['domain']['end']='2s'
        config['sources'][0]['time']['offset']='-100s'
        config['outputs']={'can_frames':{'source':'bus','format':'asc'}}
        for mode in ('original','resampled'):
            if mode=='resampled':
                config['outputs']['can_frames']['resampling']={'period':'500ms','max_gap':'2s','messages':[
                    dict(channel=1,frame_id=256,is_extended=False,is_fd=False,continuous=['Voltage'])]}
            result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/f'asc-offset-{mode}')
            try:
                self.assertEqual(list(result.iter_calculations())[0].value,10.0)
                destination=self.root/f'asc-offset-out-{mode}'; result.write(destination)
                record=json.loads((destination/'exports.jsonl').read_text(encoding='utf-8'))
                directory=destination/'exports'/record['directory']
                from chronaxis.sources.asc import ASCRead, ASCSpec
                expected=[100*10**9,101*10**9] if mode=='original' else [100*10**9,100500000000,101*10**9]
                # 读实际导出帧核原始时钟，独立核分析区间。
                with ASCRead(ASCSpec(directory/'frames.asc'),self.budget) as reader:
                    self.assertEqual([row.time_ns for row in reader],expected)
                self.assertEqual(record['interval'],[0,2*10**9])
            finally:
                result.close()

    def test_blf_same_scan_reconstruction_preserves_analysis(self):
        """BLF同次原帧与解码仓连接，公开输出3帧且积分仍为10Vs。参数: 无。返回: None。异常: 断言失败。
        """
        import can
        from chronaxis.legacy.records import PROFILE_ID
        from chronaxis.sources.asc import ASCSpec
        path=self.root/'input.blf'
        with can.BLFWriter(path) as writer:
            for time,identity,payload in ((1700000000,256,b'\x01\x05'),(1700000001,256,b'\x03\x06'),(1700000002,1911,b'\xff')):
                writer.on_message_received(can.Message(timestamp=time,arbitration_id=identity,data=payload,is_extended_id=False,channel=0))
        config=self.config(ASCSpec(path)); config['dataset']['domain']['end']='2s'
        source=config['sources'][0]; source.update(source_type='can_blf',legacy_profile=PROFILE_ID,decode_scope='requested')
        source['time']['offset']='-1700000000s'
        config['outputs']={'can_frames':{'source':'bus','format':'asc','source_time_reference':'epoch',
            'resampling':{'period':'500ms','max_gap':'2s','messages':[dict(channel=1,frame_id=256,
                is_extended=False,is_fd=False,continuous=['Voltage'])]}}}
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/'run-blf-rebuild')
        budget=result.spool.budget
        try:
            self.assertEqual(list(result.iter_calculations())[0].value,10.0)
            destination=self.root/'blf-output'; result.write(destination)
            record=json.loads((destination/'exports.jsonl').read_text(encoding='utf-8'))
            manifest=json.loads((destination/'exports'/record['directory']/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['frames'],3)
        finally:
            result.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_selected_window_exports_only_matching_actual_interval(self):
        """窗口导出只保[1,2)实际片段，不导其他范围或末端帧。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 100 Rx d 2 01 07\n3 1 777 Rx d 1 ff\n')
        config=self.config(parser)
        config['rules']=[dict(name='active',rule_type='condition_duration',condition='voltage > 5',minimum_duration='0s')]
        config['windows']=[dict(name='alarm',rule='active',anchor='activity',pre='0s',post='0s',merge='none')]
        config['outputs']={'signal_csv':{'signals':['voltage'],'scope':'segments','window':'alarm'},
            'can_frames':{'source':'bus','format':'asc','scope':'segments','window':'alarm'}}
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/'window-run')
        try:
            destination=self.root/'window-published'; result.write(destination)
            records=[json.loads(line) for line in (destination/'exports.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(records),2)
            self.assertTrue(all(r['interval']==[10**9,2*10**9] and r['segment_id'] for r in records))
            manifest=json.loads((destination/'exports'/records[1]['directory']/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['frames'],1)
        finally:
            result.close()

    def test_static_schema_explanation_and_typed_guards(self):
        """新入口schema/静态报告一致，不读输入；typed替换不能跳过引用检查。参数: 无。返回: None。异常: 断言失败。
        """
        from jsonschema import Draft202012Validator
        parser=self.asc('')
        config=self.config(parser)
        config['outputs']={'signal_csv':{'signals':['voltage']},'can_frames':{
            'source':'bus','format':'blf','capture_date':'2023-11-15','timezone_offset_minutes':480}}
        schema=json.loads(Path('Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        validator=Draft202012Validator(schema); validator.check_schema(schema); validator.validate(current_fixture(config))
        with patch.object(Path,'open',side_effect=AssertionError('静态不能打开输入')):
            plan=AnalysisPlan.from_dict(current_fixture(config))
            report=explain_analysis_plan(plan)
            self.assertTrue(validate_analysis_plan(plan).execution_ready)
        self.assertEqual({node.node_type for node in report.nodes if node.node_type.startswith('output:')},{'output:signal_csv','output:can_frames'})
        wrong=replace(plan,outputs=replace(plan.outputs,can_frames=replace(plan.outputs.can_frames,source='absent')))
        self.assertFalse(validate_analysis_plan(wrong).valid)
        for change in ('missing_date','unknown_signal','wrong_window','bad_parser'):
            value=deepcopy(config)
            if change=='missing_date':
                value['outputs']['can_frames'].pop('capture_date')
            elif change=='unknown_signal':
                value['outputs']['signal_csv']['signals']=['absent']
            elif change=='wrong_window':
                value['outputs']['signal_csv'].update(scope='segments',window='absent')
            else:
                value['sources'][0]['reader']={'guess_format':True}
            with self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(value))
        value=deepcopy(config); value['sources'][0]['dbc_by_channel']={'9'*5000:'absent.dbc'}
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(value))

    def test_real_cli_publishes_text_plan_and_exports(self):
        """同一配置经过真实命令行校验/解释/运行并发布CSV。参数: 无。返回: None。异常: 子进程或断言失败。
        """
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 777 Rx d 1 ff\n')
        config=self.config(parser); config['dataset']['domain']['end']='2s'
        config['outputs']={'signal_csv':{'signals':['voltage']}}
        path=self.root/'plan.json'; path.write_text(json.dumps(current_fixture(config)),encoding='utf-8')
        for command in ('validate','explain'):
            completed=subprocess.run([sys.executable,'-B','-m','chronaxis',command,str(path),'--format','json'],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(completed.returncode,0,completed.stderr[-2000:])
            payload=json.loads(completed.stdout)
            validation=payload if command=='validate' else payload['validation']
            self.assertTrue(validation['valid'])
            self.assertTrue(validation['execution_ready'])
            self.assertIn('implemented',validation['capability_status'].values())
        destination=self.root/'cli-published'
        completed=subprocess.run([sys.executable,'-B','-m','chronaxis','run',str(path),'--output',str(destination),
            '--work-dir',str(self.root/'cli-run')],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(completed.returncode,0,completed.stderr[-2000:])
        self.assertTrue((destination/'exports.jsonl').is_file())
        manifest=json.loads((destination/'run_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['run']['input_diagnostics'][0]['record_count'],2)

    def test_output_tampering_is_detected_and_copy_can_retry(self):
        """发布逐文件核实际内容，失败不影响原分析且恢复后可写新目录。参数: 无。返回: None。异常: 断言失败。
        """
        from chronaxis.results.errors import AnalysisError
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 777 Rx d 1 ff\n')
        config=self.config(parser); config['outputs']={'signal_csv':{'signals':['voltage']}}
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/'tamper-run')
        budget=result.spool.budget
        try:
            original=result._artifact_exports.path/'export-00000000'/'original.csv'; payload=original.read_bytes()
            original.write_bytes(payload+b'bad\n')
            with self.assertRaises(AnalysisError):
                result.write(self.root/'tampered')
            self.assertFalse((self.root/'tampered').exists())
            original.write_bytes(payload)
            result.write(self.root/'recovered')
            self.assertTrue((self.root/'recovered'/'run_manifest.json').is_file())
        finally:
            result.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_real_close_failure_retains_owner_until_recovered(self):
        """真实文件close失败保可达责任及费用，恢复后归零。参数: 无。返回: None。异常: 断言失败。
        """
        from chronaxis.results.errors import AnalysisError
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 777 Rx d 1 ff\n')
        config=self.config(parser); config['outputs']={'signal_csv':{'signals':['voltage']}}
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/'close-run'); budget=result.spool.budget
        original_open=Path.open; blocked=[True]; wrappers=[]
        class BrokenClose:
            """包装实际FD，只在明确故障开关打开时拒绝close。"""
            def __init__(self,stream):
                """接管实际文件。参数: stream。返回: owner。异常: 无。
                """
                self.stream=stream
            def read(self,size=-1):
                """读取真实字节。参数: size。返回: bytes。异常: 原IO错。
                """
                return self.stream.read(size)
            def close(self):
                """注入持续close失败，开关解除后实际关闭。参数: 无。返回: None。异常: 明确OSError。
                """
                if blocked[0]:
                    raise OSError('injected real close failure')
                self.stream.close()
        def opened(path,*args,**kwargs):
            """仅包装已生成CSV原件的真实读取FD。参数: Path/open参数。返回: FD。异常: 原打开错。
            """
            stream=original_open(path,*args,**kwargs)
            if path.name=='original.csv' and args and args[0]=='rb':
                wrapper=BrokenClose(stream); wrappers.append(wrapper); return wrapper
            return stream
        with patch.object(Path,'open',opened):
            with self.assertRaises(AnalysisError):
                result.write(self.root/'close-published')
        self.assertTrue(wrappers); self.assertFalse(wrappers[0].stream.closed)
        with self.assertRaises(OSError):
            result.close()
        self.assertGreater(budget.ram_bytes,0)
        blocked[0]=False; result.close()
        self.assertTrue(wrappers[0].stream.closed); self.assertEqual(budget.ram_bytes,0)

    def test_cancel_during_generation_closes_same_scan_resources(self):
        """生成中取消不留下活输入/索引/DBC费用，现场保留。参数: 无。返回: None。异常: 断言失败。
        """
        from chronaxis.execution.run_session import RunSession
        from chronaxis.results.artifact_exports import ArtifactExportStore
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 777 Rx d 1 ff\n')
        config=self.config(parser); config['outputs']={'signal_csv':{'signals':['voltage']}}
        session=RunSession(AnalysisPlan.from_dict(current_fixture(config)),self.root/'cancel-run')
        with patch.object(ArtifactExportStore,'append',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                session.execute()
        self.assertTrue(session.failed); session.close()
        self.assertEqual(session._budget.ram_bytes,0)

    def test_unknown_identity_uses_actual_channel_and_extended_flag(self):
        """另一通道或扩展身份不借用同数字ID的DBC定义。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc('0 2 100 Rx d 2 01 05\n1 1 100x Rx d 2 03 06\n2 1 100 Rx d 2 01 07\n')
        spec=CANTextSpec('bus',(parser,),self.dbc,0,self.timebase)
        context=FrameDBCContext(self.dbc,(),self.budget)
        adapter=BudgetedTextCANSourceAdapter(self.budget,spec,'session',(self.signal,),work_dir=self.root,retain_raw_frames=True,database_context=context)
        read=adapter.iter_batches(ReadRequest('session',('voltage',),0,3*10**9,1))
        for batch in read:
            pass
        self.assertEqual(read.runtime_metadata['decode_calls'],1)
        self.assertEqual([sample.known for sample in read._raw_store.iter_samples()],[False,False,True])
        adapter.close(); context.close(); self.assertEqual(self.budget.ram_bytes,0)

    def test_multitime_multialias_batches_keep_global_order(self):
        """多个时刻和别名不能按整列交付造成时间回退，各batch总样本数仍有界。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 100 Rx d 2 05 07\n')
        spec=CANTextSpec('bus',(parser,),self.dbc,0,self.timebase)
        for size in (1,2,3,256):
            adapter=BudgetedTextCANSourceAdapter(self.budget,spec,'session',(self.signal,replace(self.signal,name='alias')))
            values={'voltage':[],'alias':[]}; previous=None
            try:
                read=adapter.iter_batches(ReadRequest('session',('voltage','alias'),0,3*10**9,size))
                for batch in read:
                    self.assertLessEqual(batch.sample_count,size)
                    times=[int(t) for series in batch.series.values() for t in series.time_ns]
                    if times:
                        if previous is not None:
                            self.assertGreaterEqual(min(times),previous)
                        previous=max(times)
                    for name,series in batch.series.items():
                        values[name].extend(series.values.tolist())
                self.assertEqual(values,{'voltage':[3.,7.,11.],'alias':[3.,7.,11.]})
            finally:
                adapter.close()
            self.assertEqual(self.budget.ram_bytes,0)

    def test_frames_only_requests_rebuild_fields_without_signal_aliases(self):
        """仅导出报文也会请求连续字段；无需伪造普通信号消费者。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc('0 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 777 Rx d 1 ff\n')
        config=self.config(parser); config['signals']=[]; config['calculations']=[]
        config['outputs']={'can_frames':{'source':'bus','format':'asc','resampling':{'period':'500ms','max_gap':'2s',
            'messages':[dict(channel=1,frame_id=256,is_extended=False,is_fd=False,continuous=['Voltage'])]}}}
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/'frames-only-run')
        try:
            self.assertEqual(list(result.iter_calculations()),[])
            self.assertEqual(result.metadata.input_diagnostics[0].aliases,())
            destination=self.root/'frames-only'; result.write(destination)
            row=json.loads((destination/'exports.jsonl').read_text(encoding='utf-8'))
            report=json.loads((destination/'exports'/row['directory']/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(report['frames'],3)
        finally:
            result.close()

    def test_empty_input_preserves_no_observation_in_export_inventory(self):
        """空输入保空值及无观测范围，导出不补日期或信号。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc(''); config=self.config(parser)
        config['outputs']={'signal_csv':{'signals':['voltage']},'can_frames':{'source':'bus','format':'asc'}}
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)),work_dir=self.root/'empty-run')
        try:
            self.assertIsNone(list(result.iter_calculations())[0].value)
            destination=self.root/'empty-published'; result.write(destination)
            rows=[json.loads(line) for line in (destination/'exports.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(rows),2); self.assertTrue(all(row['interval'] is None for row in rows))
            reports=[json.loads((destination/'exports'/row['directory']/'manifest.json').read_text(encoding='utf-8')) for row in rows]
            self.assertEqual(reports[0]['rows'],0); self.assertEqual(reports[1]['frames'],0)
        finally:
            result.close()
