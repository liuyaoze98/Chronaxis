"""验证默认 requested 的真实需求证据、显式 all 诊断兼容和来源关闭责任。

合成 BLF/DBC 由既有真实夹具在独占 work 目录创建；两后端通过公共Runner共用BLF读取链
读取，不替换实际 reader/decoder。旧解码轨迹专项显式input_check=full保全部原帧
时间；默认专项真实运行auto/selected并核所需记录和新范围证据。父端观察同次
元数据和实际记录类型，不给未保存载荷或时间补值。静态例独立按旧字段列表估费。
错误例覆盖非法 typed 范围在目录/输入前拒绝、真实DBC元数据二次核对和入账后取消。
不运行私人日志、性能测量或历史项目入口；所有本例记录来源为 home。
"""

from configuration_fixtures import current_fixture

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from functools import partial
import json
from pathlib import Path
from sys import getsizeof
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis import AnalysisPlan, AnalysisRunner, explain_analysis_plan
from chronaxis.execution import can_reader
from chronaxis.execution.can_batch_reader import CANBatchObservationRead
from chronaxis.execution.run_session import RunSession
from chronaxis.legacy.batch_read import LegacyCANBatchRead
from chronaxis.legacy.records import PROFILE_ID, decoded_to_dict, encode_packet
from chronaxis.legacy.required_records import RequiredDecodedFrame, required_to_dict
from chronaxis.planning.checks import PlanValidationError
from chronaxis.planning.export_options import CANFramesOutput
from chronaxis.results.frame_exports import FrameExportSpec
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.can_metadata import CANSourceMetadata
from chronaxis.results.errors import AnalysisError
from chronaxis.results.manifest import RunMetadata, _metadata_size
from chronaxis.sources.protocol import SourceReadError
from test_optional_contribution_execution import make_can_fixture, drain, summary_values
from test_legacy_requested_decode import observed_requested_worker


OLD_CAN_FIELDS = ('source','session_id','legacy_profile','path','dbc_path','channel',
    'read_identity','worker_pid','frame_count','first_ns','last_ns','raw_store_path',
    'raw_store_sha256','raw_spool_bytes','dependency_versions','vendor_sha256','unit_checks')
OLD_RUN_FIELDS = ('run_id','input_identity','plan_hash','backend','config_version',
    'source_time_interpretation','session_boundaries','started_at','mapping_hashes','dbc_hashes',
    'parsing_policy','worker_config','dependency_versions','limitations','software_version',
    'semantic_version','device_label','can_sources')


def unknown_native_type_worker(connection, *, ids, input_check, time_scope):
    """真实读取小BLF，但声明无法识别原生消息类，触发完整检查回退。

    参数: 实际spawn端点及原固定解码/检查/时间策略。
    返回: 正式batch_worker返回值。异常: 原读写、解码或协议错误。
    副作用: 仅child测试包装改变原生类识别，原iter_frames和parse_frame原样调用；
        六条真实帧均经过worker._frame，不手填READY、批次或完成计数。
    """
    from chronaxis.legacy import batch_worker, worker
    original_load = worker._load_can_runtime

    def load_without_native_type():
        """保真实读取和解码模块，只不声明可识别的原生消息类型。

        参数: 无。返回: 不暴露原生Message类的CAN门面及真实cantools模块。
        异常: 原加载错误传播；不改写旧模块或CAN库对象。
        """
        can,cantools=original_load()
        return SimpleNamespace(Message=object),cantools

    with patch.object(worker, '_load_can_runtime', load_without_native_type):
        return batch_worker.batch_worker_main(connection, decode_frame_ids=ids,
            input_check=input_check, time_scope=time_scope)


def old_metadata_size(value):
    """按新选项出现前的明确字段估费，不调用新估费函数。

    参数: 本例无绑定/无notice的有限旧元数据。返回: 原基础字节数。
    异常: 不支持的测试对象以TypeError拒绝，避免意外扩大预期模型。
    """
    if type(value) is CANSourceMetadata:
        return getsizeof(value)+sum(old_metadata_size(getattr(value,name))+32 for name in OLD_CAN_FIELDS)
    if type(value) is tuple:
        return getsizeof(value)+sum(old_metadata_size(item)+32 for item in value)
    if value is None or type(value) in (str,int,float,bool):
        return getsizeof(value)
    raise TypeError('旧费用预期只支持本例的明确模型')


def static_source(**changes):
    """创建仅用于模型检查的有限事实，不假称实际来源扫描完成。

    参数: 本例字段覆盖。返回: CANSourceMetadata。异常: 被测模型原检查错误。
    """
    values=dict(source='bus',session_id='session',legacy_profile=PROFILE_ID,path='synthetic.blf',
        dbc_path='synthetic.dbc',channel=0,read_identity='synthetic-read',worker_pid=123,
        frame_count=0,first_ns=None,last_ns=None,raw_store_path=None,raw_store_sha256=None,
        raw_spool_bytes=0,dependency_versions=(('python','synthetic'),),
        vendor_sha256=(('utils.py','a'*64),),unit_checks=())
    values.update(changes)
    return CANSourceMetadata(**values)


class RequestedDecodeRuntimeTests(unittest.TestCase):
    """使用实际来源及最高会话 owner，所有运行目录独占且关闭后核账本归零。"""

    def root(self):
        """取得尚不存在的本例路径。参数: 无。返回: Path。异常: 无主动异常。"""
        return Path(__file__).resolve().parents[2]/'work/can-requested-tests'/uuid4().hex

    def fixture(self, **kwargs):
        """生成真实小输入并明确处理可选依赖缺失。参数: 原夹具选项。返回: root/config/plan。异常: 原错误。"""
        try:
            import can
        except ModuleNotFoundError as exc:
            self.skipTest('缺可选CAN依赖: '+exc.name)
        root=self.root()
        config,_=make_can_fixture(root,**kwargs)
        config['diagnostics']={'trace':True,'integrity':True}
        return root,config,AnalysisPlan.from_dict(current_fixture(config),base_dir=root)

    def execute(self,plan,path,*,trace=False,ordinary=False):
        """观察公共Runner实际共用读取链，保留原手算结果、需求范围和关闭断言。"""
        import can
        from chronaxis.execution import text_can_reader
        from chronaxis.sources.text_can_decode import CANTextDecodeRead
        from chronaxis.sources.can_spec import can_field_from_key
        observed=dict(ready=[],records=[],adapters=[],processes=[],completed=[],calls=[],delivered_ids=[])
        read_type=text_can_reader.TextCANObservationRead
        original_init=read_type.__init__;original_prepare=read_type.prepare_metadata;original_close=read_type.close
        original_next=CANTextDecodeRead.__next__;original_decode=CANTextDecodeRead._decode
        original_frames=can.BLFReader.__iter__
        prepared=set()
        def initialize(read,owner,request):
            """记录实际适配器需求。参数: read、owner、request。返回: None。异常: 原构造错误。"""
            original_init(read,owner,request)
            ids={can_field_from_key(item.field).frame_id for item in owner.signals}
            ids.update(key[1] for key in owner._update_projection._groups) if owner._update_projection is not None else None
            observed['adapters'].append((owner._serial_blf_policy,tuple(sorted(ids))))
            observed['processes'].append(read)
        def prepare(read):
            """每个读取器只摘取一次元数据。参数: read。返回: 原事实。异常: 原初始化错误。"""
            facts=original_prepare(read)
            if id(read) not in prepared:
                prepared.add(id(read));observed['ready'].append(dict(facts))
            return facts
        def advance(read):
            """记录真实交付顺序与载荷。参数: read。返回: 原记录。异常: EOF或原读取错误。"""
            record=original_next(read)
            observed['delivered_ids'].append(record.raw.frame.arbitration_id)
            if record.raw.frame.arbitration_id in {256}:
                observed['records'].append((record.sequence,record.raw.frame.timestamp,
                    record.raw.frame.arbitration_id,record.raw.frame.data.hex(),record.values))
            return record
        def decode(read,raw):
            """按真实计数增量记录调用。参数: read及raw。返回: 原解码结果。异常: 原解码错误。"""
            before=read.decode_calls;result=original_decode(read,raw)
            observed['calls'].extend(dict(rule='parse') for _ in range(read.decode_calls-before))
            return result
        def frames(reader):
            """透传真实BLF迭代并记录EOF调用。参数: reader。返回: 帧生成器。异常: 原读取/关闭错误。"""
            iterator=original_frames(reader)
            try:
                while True:
                    observed['calls'].append(dict(rule='next'))
                    try:value=next(iterator)
                    except StopIteration:return
                    yield value
            finally:iterator.close()
        def close(read):
            """关闭前保留已完成观测。参数: read。返回: 原关闭结果。异常: 原关闭错误。"""
            if read.exhausted and not read.closed and read._observation is not None:
                observed['completed'].append(read.observation)
            return original_close(read)
        with ExitStack() as stack:
            stack.enter_context(patch.object(read_type,'__init__',initialize))
            stack.enter_context(patch.object(read_type,'prepare_metadata',prepare))
            stack.enter_context(patch.object(read_type,'close',close))
            stack.enter_context(patch.object(CANTextDecodeRead,'__next__',advance))
            stack.enter_context(patch.object(CANTextDecodeRead,'_decode',decode))
            if trace:stack.enter_context(patch.object(can.BLFReader,'__iter__',frames))
            result=AnalysisRunner().run(plan,work_dir=path)
        budget=result.spool.budget
        try:
            rows=tuple(row for row in drain(result.iter_calculations()) if row.operation=='legacy_sum')
            metadata=result.metadata
            if ordinary:observed['ordinary']=tuple(drain(getattr(result,name)())
                for name in ('iter_events','iter_segments','iter_selections'))
        finally:result.close()
        self.assertEqual(budget.ram_bytes,0)
        self.assertTrue(all(read.closed for read in observed['processes']))
        return rows,metadata,observed

    def test_current_manifest_omits_unrequested_full_can_model(self):
        """当前必要清单不默认展开完整CAN模型，all内部模型计费保持。参数: 无。返回: None。异常: 断言。"""
        source=static_source()
        explicit=static_source(decode_scope='all',decode_frame_ids=())
        run=RunMetadata('run','input','plan','reference',4,'synthetic seconds',
            (('session',0,1),),'2026-10-19T00:00:00+08:00',device_label='home',can_sources=(source,))
        actual=run.to_dict()
        self.assertNotIn('can_sources',actual)
        self.assertNotIn('semantic_version',actual)
        self.assertNotIn('input_diagnostics',actual)
        self.assertEqual(actual['config_version'],4)
        self.assertEqual(actual,replace(run,can_sources=(explicit,)).to_dict())
        self.assertEqual(_metadata_size(source),old_metadata_size(source))
        self.assertEqual(run.estimated_bytes(),replace(run,can_sources=(explicit,)).estimated_bytes())

    def test_requested_metadata_rejects_types_duplicates_and_noncanonical_ids(self):
        """元数据拒绝 bool ID、类型替代和重复/乱序，all 不接受有限 ID 冒充全解码。

        参数: 无。返回: None。异常: 原模型未拒绝错误输入时断言失败。
        """
        class Scope(str):
            """仅检验原生str边界的测试子类，不作为合法策略。"""
        class Identifier(int):
            """仅检验原生int边界的测试子类，不作为合法ID。"""
        for scope in (False,None,1,'needed',Scope('requested')):
            with self.subTest(scope=scope),self.assertRaises((TypeError,ValueError)):
                static_source(decode_scope=scope)
        for ids in (None,[],[256],(False,),(True,),(Identifier(256),),(256.,),(-1,),
                    (0x20000000,),(256,256),(257,256)):
            with self.subTest(ids=ids),self.assertRaises((TypeError,ValueError)):
                static_source(decode_scope='requested',decode_frame_ids=ids)
        with self.assertRaises((TypeError,ValueError)):
            static_source(decode_scope='all',decode_frame_ids=(256,))
        self.assertEqual(static_source(decode_scope='requested',decode_frame_ids=()).decode_frame_ids,())
        source=static_source(decode_scope='requested',decode_frame_ids=(0,256,0x1fffffff))
        self.assertGreater(_metadata_size(source),old_metadata_size(source))

    def test_explicit_all_contract_description_and_adapter_fee_keep_old_shape(self):
        """显式all保原来源合同与描述，adapter仍按原明确公式付款。

        参数: 无。返回: None。异常: 默认合同或费用改变时断言失败。
        """
        root,config,_=self.fixture()
        config['sources'][0]['decode_scope']='all'
        plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
        source=plan.sources[0];spec=source.config
        expected=(source.name,source.source_type,source.input_identity,source.time_unit,source.timezone_text,
            spec.name,str(spec.path),str(spec.dbc_path),spec.channel,spec.legacy_profile,
            spec.timebase,spec.unit,spec.offset_ns)
        definitions=tuple(item.definition for item in plan.signals)
        descriptions=[];costs=[]
        for index,selected_spec in enumerate((spec,replace(spec,decode_scope='all'))):
            budget=ResourceBudget(256*1024**2,None);work=root/('adapter'+str(index))
            old_cost=65536+32*can_reader._metadata_bytes((selected_spec.name,str(selected_spec.path),
                str(selected_spec.dbc_path),selected_spec.channel,selected_spec.timebase,selected_spec.unit,
                selected_spec.offset_ns,plan.dataset.session_id,definitions,str(work)))
            adapter=can_reader.BudgetedLegacyCANSourceAdapter(budget,selected_spec,plan.dataset.session_id,
                definitions,work_dir=work,batch_read=True,retain_raw_frames=False,message_frame_ids=(256,))
            try:
                descriptions.append(adapter.describe());costs.append(adapter._fixed_cost)
                self.assertEqual(adapter._fixed_cost,old_cost)
                self.assertEqual((adapter.decode_scope,adapter.decode_frame_ids),('all',()))
            finally:
                adapter.close()
            self.assertEqual(budget.ram_bytes,0)
        self.assertEqual(descriptions[0],descriptions[1]);self.assertEqual(costs[0],costs[1])
        locator=descriptions[0].fields[0].field.locator
        self.assertEqual(set(locator),{'path','dbc_path','channel','legacy_profile','time_unit',
                                      'offset_ns','source_timebase_sha256'})

    def test_omitted_scope_runs_requested_with_actual_input_evidence(self):
        """真正省略选项时使用requested/auto/selected，真实READY4及新证明记录范围。

        参数: 无。返回: None。异常: 默认范围、实际READY、手算值或真实关闭不符时失败。
        """
        root,config,_=self.fixture()
        config['sources'][0].pop('decode_scope',None)
        plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
        self.assertNotIn('decode_scope',plan.raw_config['sources'][0])
        self.assertNotIn('input_check',plan.raw_config['sources'][0])
        self.assertEqual(plan.sources[0].config.decode_scope,'requested')
        self.assertEqual(plan.sources[0].config.input_check,'auto')
        rows,metadata,facts=self.execute(plan,root/'default')
        self.assertEqual(tuple(row.value for row in rows),(700.,-200.))
        self.assertEqual(facts['adapters'],[('requested',(256,))])
        self.assertEqual(facts['ready'][0]['decode_scope'],'requested')
        self.assertEqual(facts['ready'][0]['time_order_check_scope'],'selected_ids')
        self.assertEqual(metadata.input_diagnostics[0].aliases,('power',))
        self.assertEqual(metadata.input_diagnostics[0].time_scope,'selected')
        observed=facts['completed'][0]
        self.assertEqual((observed.row_count,observed.retained_record_count,observed.full_check_count),(6,5,0))
        self.assertEqual((observed.first_ns,observed.last_ns),(0,3_000_000_000))
        self.assertEqual(metadata.input_diagnostics[0].digest_scope,'required-decoded-records-v1')

    def test_real_runner_requested_union_preserves_both_backend_summaries(self):
        """requested只解所需帧，all实际解全部帧；两后端700/-200J不变。参数: 无。返回: None。异常: 断言。"""
        for backend in ('reference','numpy'):
            root,config,_=self.fixture(backend=backend)
            config['sources'][0]['input_check']='full'
            with Path(config['sources'][0]['dbc_by_channel']['1']).open('a',encoding='utf-8') as stream:
                stream.write('BO_ 257 Extra: 2 Node\n SG_ Extra : 0|16@1- (1,0) [-32768|32767] "W" Node\n')
            extra=deepcopy(config['signals'][0]);extra['name']='extra'
            extra['field'].update(signal='Extra',frame_id=257)
            config['signals'].append(extra)
            results=[];observations=[]
            for scope in ('all','requested'):
                selected=deepcopy(config);selected['sources'][0]['decode_scope']=scope
                plan=AnalysisPlan.from_dict(current_fixture(selected),base_dir=root)
                rows,metadata,facts=self.execute(plan,root/scope,trace=True)
                results.append(rows);observations.append(facts)
                self.assertEqual(tuple(row.value for row in rows),(700.,-200.))
                self.assertEqual(metadata.input_diagnostics[0].aliases,('power',))
                self.assertEqual(facts['completed'][0].row_count,6)
                self.assertEqual(sum(item['rule']=='next' for item in facts['calls']),7)
                self.assertEqual(sum(item['rule']=='parse' for item in facts['calls']),6 if scope=='all' else 5)
                self.assertEqual(tuple(record[2] for record in facts['records']),(256,)*5)
                self.assertEqual(tuple(facts['delivered_ids']),(256,)*5)
            self.assertEqual(summary_values(results[0]),summary_values(results[1]))
            self.assertEqual(observations[1]['adapters'],[('requested',(256,))])
            ready=observations[1]['ready'][0]
            self.assertEqual(ready['decode_scope'],'requested')
            self.assertEqual(observations[0]['ready'][0]['decode_scope'],'all')
            # 未用声明仍静态保存，错误单位不应强制读取该值或冒称已核实。
            selected['signals'][1]['unit']='A'
            selected['signals'][1]['conversion']={'input_unit':'A'}
            rows,metadata,_=self.execute(AnalysisPlan.from_dict(current_fixture(selected),base_dir=root),root/'unused-unit')
            self.assertEqual(tuple(row.value for row in rows),(700.,-200.))
            self.assertEqual(metadata.input_diagnostics[0].aliases,('power',))

    def test_no_signal_constant_calculations_still_identify_requested_scope(self):
        """纯参数requested不调用parse，all仍实际解码，当前结果不复制旧证明。参数: 无。返回: None。异常: 断言。"""
        root,config,_=self.fixture(disjunction=False)
        config['sources'][0]['input_check']='full';config['signals']=[]
        for calculation in config['message_calculations']:
            calculation['expr']='amount';calculation['parameters']={'amount':{'value':2,'unit':'J'}}
        results=[];identities=[]
        for scope in ('all','requested'):
            selected=deepcopy(config);selected['sources'][0]['decode_scope']=scope
            rows,metadata,facts=self.execute(AnalysisPlan.from_dict(current_fixture(selected),base_dir=root),root/scope,trace=True)
            results.append(rows);identities.append(metadata.plan_hash)
            self.assertEqual(tuple(row.value for row in rows),(10.,10.))
            self.assertEqual(facts['ready'][0]['fields'],())
            self.assertEqual((facts['completed'][0].row_count,facts['completed'][0].retained_record_count),(6,5))
            self.assertEqual(sum(item['rule']=='next' for item in facts['calls']),7)
            self.assertEqual(sum(item['rule']=='parse' for item in facts['calls']),6 if scope=='all' else 0)
            self.assertEqual(tuple(record[2] for record in facts['records']),(256,)*5)
            self.assertEqual(tuple(facts['delivered_ids']),(256,)*5)
            self.assertEqual(metadata.input_diagnostics[0].aliases,())
            self.assertTrue(metadata.input_diagnostics[0].source_eof)
            self.assertIsNone(metadata.input_identity)
        self.assertNotEqual(*identities)
        self.assertEqual(summary_values(results[0]),summary_values(results[1]))

    def test_typed_mixed_requested_runs_real_dependencies(self):
        """typed混合规则、窗口和select可按需运行，full及raw不被scope误拒。

        参数: 无。返回: None。异常: 手算、普通结果、实际需求或关闭错误时失败。
        """
        root,config,_=self.fixture(mixed=True)
        config['sources'][0]['decode_scope']='all'
        base=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
        requested=replace(base.sources[0],config=replace(base.sources[0].config,decode_scope='requested'))
        mixed=replace(base,sources=(requested,))
        cases=(mixed,replace(mixed,outputs=replace(mixed.outputs,contributions='full')),
            replace(mixed,outputs=replace(mixed.outputs,can_frames=CANFramesOutput('bus', FrameExportSpec('asc')))))
        for index,plan in enumerate(cases):
            with self.subTest(case=index):
                rows,metadata,facts=self.execute(plan,root/('mixed'+str(index)),ordinary=True)
                self.assertEqual(tuple(row.value for row in rows),(700.,-200.))
                self.assertEqual(facts['adapters'],[('requested',(256,))])
                self.assertEqual(metadata.input_diagnostics[0].aliases,('power',))
                self.assertTrue(all(facts['ordinary']))
                source=facts['completed'][0]
                self.assertEqual((source.time_scope,source.row_count),('source',6))
                self.assertEqual(source.retained_record_count,6 if index==2 else 5)
                self.assertEqual(source.full_check_count,0)
                self.assertEqual(plan.raw_config['sources'][0]['reader']['decode_scope'],'all')

    def test_mixed_metadata_keeps_real_complete_check_fallback_counts(self):
        """普通历史扫描将真实read回退计数移交清单，不在重建观测时重置为零。

        参数: 无。返回: None；六原帧/五目标/六完整检查回退按夹具手写。
        异常: 旧函数、实际握手/数值、透传计数或关闭责任错误使测试失败。
        """
        root,_,plan=self.fixture(mixed=True)
        from chronaxis.sources.blf import BLFRead
        original_init=BLFRead.__init__
        def force_fallback(read,*args,**kwargs):
            """强制完整字段回退。参数: read及原参数。返回: None。异常: 原初始化错误。"""
            original_init(read,*args,**kwargs)
            read._native_message_type=object
        with patch.object(BLFRead,'__init__',force_fallback):
            rows,metadata,facts=self.execute(plan,root/'mixed-fallback',ordinary=True)
        self.assertEqual(tuple(row.value for row in rows),(700.,-200.))
        self.assertTrue(all(facts['ordinary']))
        source=facts['completed'][0]
        self.assertEqual((metadata.input_diagnostics[0].input_check,source.time_scope),('auto','source'))
        self.assertEqual((source.row_count,source.retained_record_count,source.full_check_count),(6,5,6))
        self.assertEqual((source.first_ns,source.last_ns),(0,4_000_000_000))

    def test_invalid_typed_scope_is_rejected_before_mkdir_and_input(self):
        """受控损坏typed范围仍在来源和目录创建前拒绝，不把非法值当默认requested。

        参数: 无。返回: None。异常: 错误入口越过静态门禁时断言失败。
        """
        root,_,base=self.fixture(mixed=True)
        cases=[]
        for value in ('unknown',None,True):
            invalid=replace(base.sources[0].config)
            object.__setattr__(invalid,'decode_scope',value)
            cases.append(replace(base,sources=(replace(base.sources[0],config=invalid),)))
        for index,plan in enumerate(cases):
            for constructor in ('runner','session'):
                # 公共AnalysisRunner先给出统一AnalysisError；内部构造保原静态PlanValidationError。
                expected=AnalysisError if constructor=='runner' else PlanValidationError
                with self.subTest(case=index,entry=constructor),\
                        patch.object(Path,'mkdir',side_effect=AssertionError('门禁前创建目录')) as mkdir,\
                        patch.object(LegacyCANBatchRead,'start',side_effect=AssertionError('门禁前读取来源')) as start,\
                        self.assertRaises(expected) as caught:
                    if constructor=='runner':AnalysisRunner().run(plan,work_dir=root/('bad'+str(index)))
                    else:RunSession(plan,root/('bad'+str(index)))
                self.assertIn('decode_scope',str(caught.exception))
                mkdir.assert_not_called();start.assert_not_called()

    def test_pure_message_unused_derived_does_not_create_ordinary_stages(self):
        """纯消息full/none允许未引用派生，完整静态声明不成为普通历史运行根。

        参数: 无。返回: None。异常: 无用阶段被创建、目标投影或手算结果改变时失败。
        """
        for mode in ('full','none'):
            with self.subTest(contributions=mode):
                root,config,_=self.fixture(contributions=mode)
                unused=deepcopy(config['signals'][0])
                unused.update(name='unused',unit='V',conversion={'input_unit':'V'})
                unused['field'].update(signal='Unused',frame_id=258)
                config['signals'].append(unused)
                config['derived']={'unused_twice':{'expr':'unused * 2','unit':'V'}}
                plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
                with ExitStack() as stack:
                    for name in ('LatestSignalState','RecordRuleTimeline','RecordWindows','RecordScopeCalculations'):
                        stack.enter_context(patch('chronaxis.execution.record_session_calculations.'+name,
                            side_effect=AssertionError('unused派生不能创建普通计算状态')))
                    rows,metadata,facts=self.execute(plan,root/'unused-derived')
                self.assertEqual(tuple(row.value for row in rows),(700.,-200.))
                self.assertEqual(facts['adapters'],[('requested',(256,))])
                self.assertEqual(metadata.input_diagnostics[0].aliases,('power',))
                self.assertEqual(tuple(item.definition.name for item in plan.signals),('power','unused'))
                self.assertEqual(len(plan.derived_expressions),1)

    def test_unused_derived_typed_changes_still_fail_and_close(self):
        """未用派生的合法改式、未知引用和循环仍拒绝，已付协调费用正常关闭。

        参数: 无。返回: None。异常: typed静态不匹配被放行、错误丢失或资源未释放时失败。
        """
        for mode in ('full','none'):
            root,config,_=self.fixture(contributions=mode)
            config['derived']={'unused_power':{'expr':'power * 2','unit':'W'}}
            base=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
            for index,(text,message) in enumerate((('power * 3','原完整静态表达式不一致'),
                    ('missing_power * 2','未知'),('unused_power','循环'))):
                changed=replace(base.derived[0],definition=replace(base.derived[0].definition,expr=text))
                plan=replace(base,derived=(changed,))
                with self.subTest(contributions=mode,expression=text),self.assertRaises(AnalysisError) as caught:
                    AnalysisRunner().run(plan,work_dir=root/('invalid-derived'+str(index)))
                self.assertIn(message,str(caught.exception))
                owner=caught.exception.runner_cleanup_owner
                owner.close()
                self.assertTrue(owner.closed)
                self.assertEqual(owner._budget.ram_bytes,0)
                self.assertIsNone(owner._path)

    def test_empty_results_still_validate_derived_before_input(self):
        """空任务缺少消费者时执行前拒绝，内部会话仍在输入前复核非法派生。

        参数: 无。返回: None。异常: typed错误越过需求/目录/输入门禁或合法空任务失败。
        """
        root,config,_=self.fixture()
        # 空任务不构造观测；内部协调器的静态复核仍独立验证。
        config['sources'][0]['input_check']='full'
        config.update(message_calculations=[],rules=[],windows=[],calculations=[],
            derived={'unused_power':{'expr':'power * 2','unit':'W'}})
        base=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
        with patch.object(LegacyCANBatchRead,'start',side_effect=AssertionError('空任务不读取输入')),self.assertRaises(AnalysisError):
            AnalysisRunner().run(base,work_dir=root/'empty-results')
        self.assertFalse((root/'empty-results').exists())
        for index,(text,message) in enumerate((('power * 3','原完整静态表达式不一致'),
                ('missing_power * 2','未知'),('unused_power','循环'))):
            definition=replace(base.derived[0].definition,expr=text)
            plan=replace(base,derived=(replace(base.derived[0],definition=definition),))
            with self.subTest(expression=text),\
                    patch('chronaxis.execution.run_session.collect_input_requirements',
                        side_effect=AssertionError('派生复核前收集需求')) as requirements,\
                    patch.object(Path,'mkdir',side_effect=AssertionError('派生复核前创建目录')) as mkdir,\
                    patch.object(LegacyCANBatchRead,'start',
                        side_effect=AssertionError('派生复核前读取来源')) as start,\
                    self.assertRaises(ValueError) as caught:
                RunSession(plan,root/('invalid-empty'+str(index)))
            self.assertIn(message,str(caught.exception))
            requirements.assert_not_called()
            mkdir.assert_not_called()
            start.assert_not_called()
            owner=caught.exception.runner_cleanup_owner
            owner.close()
            self.assertTrue(owner.closed)
            self.assertIsNone(owner._path)
            self.assertEqual(owner._budget.ram_bytes,0)

    def test_actual_dbc_metadata_failure_and_charge_cancellation_are_owned(self):
        """实际DBC绑定失败和元数据入账后取消，都保原错及同一最高资源owner。"""
        from chronaxis.sources import text_can_decode
        root,config,_=self.fixture()
        plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
        original=text_can_decode.load_dbc_file
        opened=[]
        def wrong_unit(*args,**kwargs):
            """真实载入后制造DBC单位矛盾。参数: 原加载参数。返回: 数据库。异常: 原加载错误。"""
            database=original(*args,**kwargs)
            database.messages[0].signals[0].unit='A'
            return database
        session=RunSession(plan,root/'bad-dbc');self.addCleanup(session.close)
        with patch.object(text_can_decode,'load_dbc_file',wrong_unit):
            with self.assertRaisesRegex(ValueError,'单位') as caught:session.execute()
        self.assertIs(caught.exception.runner_cleanup_owner,session)
        session.close();self.assertEqual(session._budget.ram_bytes,0)
        session=RunSession(plan,root/'cancel');self.addCleanup(session.close)
        original_reserve=text_can_decode._reserve_owned_ram
        cancellation=KeyboardInterrupt('requested运行元数据入账后取消')
        def reserve(owner,amount,slot):
            """实际入账后取消。参数: owner、amount、slot。返回: None。异常: 原费用错误或同一取消。"""
            original_reserve(owner,amount,slot)
            if slot=='_metadata_cost':opened.append(owner);raise cancellation
        with patch.object(text_can_decode,'_reserve_owned_ram',reserve):
            with self.assertRaises(KeyboardInterrupt) as caught:session.execute()
        self.assertIs(caught.exception,cancellation)
        self.assertIs(cancellation.runner_cleanup_owner,session)
        session.close();self.assertEqual(session._budget.ram_bytes,0)
        self.assertTrue(opened and all(read.closed for read in opened))
