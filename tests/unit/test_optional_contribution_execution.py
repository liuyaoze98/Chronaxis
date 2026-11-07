"""验证可选贡献明细的实际执行、手算结果和普通任务保留行为。

每例在work/optional-contribution-tests的唯一目录创建合成DBC/BLF和运行结果；
不读取私人日志，不修改RefProjects或其他测试产物。公共AnalysisRunner负责真实旧链读取，
两个后端均核同刻、切批、缺值、半开范围以及明确分桶。none模式用实际构造引用
的失败守卫证明未先生成明细再丢弃；普通事件、窗口、select仍与full相同。
无CAN依赖时明确skip。手算与原完整模式对照分别保留，不能互相替代。
"""
from published_paths import published_file


from configuration_fixtures import current_fixture

from collections.abc import Mapping
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.execution import record_session_calculations as execution
from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from chronaxis.legacy.message_store import DecodedMessageStore
from chronaxis.results.codec import decode_row, encode_row
from chronaxis.results.errors import ContributionsUnavailableError


def make_can_fixture(root, *, backend='numpy', batch_rows=2, contributions='none',
                     frames=None, domain=('0s', '5s'), mixed=False, disjunction=True):
    """创建单源真实输入与公开配置，不执行分析。

    参数: root为尚不存在的本例目录；frames是(秒,ID,有符号整数或None)的tuple，
        None值表示匹配空payload；frames=None使用同刻正负、零、缺值和末尾正值。
        mixed增加事件、活动窗口和select；disjunction=False计算不分桶的两项相同总和。
    返回: (独立原生config,AnalysisPlan)。异常: 原CAN依赖、IO或公开配置错误。
    """
    import can
    root.mkdir(parents=True, exist_ok=False)
    dbc, blf = root/'power.dbc', root/'power.blf'
    dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Power: 2 Node\n'
        ' SG_ Power : 0|16@1- (1,0) [-32768|32767] "W" Node\n', encoding='utf-8')
    if frames is None:
        frames = ((0,256,4000),(0,256,-2000),(1,256,0),(2,256,None),(3,256,3000),(4,257,4))
    writer = can.BLFWriter(blf)
    primary = None
    try:
        for timestamp, identifier, value in frames:
            writer.on_message_received(can.Message(timestamp=1700000000.0+timestamp,
                arbitration_id=identifier, is_extended_id=False, channel=0,
                data=b'' if value is None else value.to_bytes(2,'little',signed=True)))
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            writer.stop()
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note('合成输入关闭附加失败: '+type(cleanup).__name__)
            primary.optional_fixture_writer_cleanup_owner = writer
    calculations = []
    for index, bucket in enumerate(('positive','negative')):
        calculation = dict(name='energy'+str(index), source='bus', profile='sclicer-functions-v1',
            operation='legacy_sum', message_policy='current_message-v1', unit='J', expr='power * period',
            parameters=dict(period=dict(value=0.1,unit='s')),
            update_message=dict(channel=1,frame_id=256,is_extended=False,is_fd=False))
        if disjunction:
            calculation['split_by_sign'] = dict(signal='power',bucket=bucket,value_policy='raw_decoded-v1')
        calculations.append(calculation)
    config = dict(config_version=4,
        dataset=dict(name='optional_detail',entity='synthetic',session='session',
            domain=dict(start=domain[0],end=domain[1])),
        sources=[dict(name='bus',source_type='can_blf',path=str(blf),legacy_profile='sclicer-functions-v1',
            reader_options=dict(decode_policy='legacy'),dbc_by_channel={'1':str(dbc)},time=dict(time_type='relative',unit='s',origin='message_clock',offset='-1700000000s'))],
        signals=[dict(name='power',source='bus',field=dict(channel=1,signal='Power',
            frame_id=256,is_extended=False,is_fd=False),dtype='float64',unit='W',valid_for='10s',
            same_time_policy='last_by_sequence')],rules=[],windows=[],calculations=[],message_calculations=calculations,
        execution=dict(backend=backend,batch_rows=batch_rows,result_buffer_rows=2,memory_budget_bytes=256*1024**2),
        outputs=dict(tables='jsonl',contributions=contributions),metadata=dict(device_label='home',data_kind='synthetic'))
    if mixed:
        config['rules'] = [dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='power > 0',minimum_duration='0s')]
        config['windows'] = [dict(name='activity',rule='active',anchor='activity',pre='0s',post='0s',merge='none')]
        config['calculations'] = [dict(name='samples',scope='session',operation='select',expr='power')]
    return config, AnalysisPlan.from_dict(current_fixture(config),base_dir=root)


def drain(reader):
    """完整消费并关闭小输入游标。参数: 活reader。返回: tuple。异常: 原读取或关闭错误。"""
    try:
        return tuple(reader)
    finally:
        reader.close()


def no_detail(*args, **kwargs):
    """明细构造守卫。参数: 任意原参数。返回: 无。异常: AssertionError表示错误地生成明细。"""
    raise AssertionError('none模式不得构造逐消息贡献或其展示输入')


def guard_details(stack):
    """阻断执行端真正使用的明细构造引用。参数: ExitStack。返回: None。异常: patch错误。"""
    stack.enter_context(patch.object(execution,'SummaryContributionRow',new=no_detail))
    stack.enter_context(patch.object(execution.RecordSessionCalculations,'_emit_contribution',new=no_detail))


def summary_values(rows):
    """抽当前公开汇总的业务字段，序号不当作跨输出模式的业务身份。参数: 汇总行。返回: tuple。异常: 属性错。"""
    return tuple((row.calculation_id,row.value,row.unit,row.status,row.reason,row.quality)
                 for row in rows if row.operation=='legacy_sum')


def mutable_config(value):
    """复制已校验配置为原生JSON结构，仅供本例再次公开解析。参数: 冻结值。返回: 独立值。异常: 原分配错误。"""
    if isinstance(value,Mapping):
        return {key:mutable_config(item) for key,item in value.items()}
    if type(value) is tuple:
        return [mutable_config(item) for item in value]
    return value


class OptionalContributionExecutionTests(unittest.TestCase):
    """在真实公共执行链检验选项，所有本例目录独占且无需清理其他会话文件。"""

    def root(self):
        """产生尚不存在的唯一测试路径。参数: 无。返回: Path。异常: 无主动异常。"""
        return Path(__file__).resolve().parents[2]/'work/optional-contribution-tests'/uuid4().hex

    def fixture(self, **kwargs):
        """提供明确CAN依赖skip和实际夹具。参数: 原夹具选项。返回: 根/config/plan。异常: 原错误。"""
        try:
            import can
        except ModuleNotFoundError as exc:
            self.skipTest('缺可选CAN依赖: '+exc.name)
        root = self.root()
        config,plan = make_can_fixture(root,**kwargs)
        return root,config,plan

    def run_result(self, plan, root, *, forbid=False, direct=False):
        """完整run期间保持实际构造守卫，结果交调用者关闭。参数: 计划/路径/明细及直接路径门禁。返回: AnalysisResult。异常: 原运行错。"""
        snapshots = []
        snapshot = CurrentMessageCalculation.snapshot
        def observed(owner):
            """观察实际结束快照，不触发额外计算。参数: 当前累计器。返回: 原快照。异常: 原错。"""
            value = snapshot(owner)
            snapshots.append(value)
            return value
        with ExitStack() as stack:
            stack.enter_context(patch.object(CurrentMessageCalculation,'snapshot',new=observed))
            if forbid:
                guard_details(stack)
            if direct:
                for name in ('__init__','append','iter_records'):
                    stack.enter_context(patch.object(DecodedMessageStore,name,new=no_detail))
            result = AnalysisRunner().run(plan,work_dir=root)
        self.addCleanup(result.close)
        self.snapshots = getattr(self,'snapshots',{})
        self.snapshots[result.metadata.run_id] = tuple(snapshots)
        if direct:
            self.assertFalse(tuple(root.rglob('decoded_messages.jsonl')))
        return result

    def close_result(self, result):
        """核真实公共结果关闭与RAM归零。参数: 活result。返回: None。异常: 原关闭或断言错误。"""
        budget = result.spool.budget
        result.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_none_preserves_hand_calculated_two_buckets_all_backends(self):
        """同刻两消息分别计算、缺值跳过，跨批总计700/-200。参数: 无。返回: None。异常: 断言失败。"""
        for backend,batch in (('reference',1),('numpy',3)):
            with self.subTest(backend=backend,batch=batch):
                root,config,plan = self.fixture(backend=backend,batch_rows=batch)
                result = self.run_result(plan,root/'none',forbid=True,direct=True)
                rows = drain(result.iter_calculations())
                self.assertEqual(tuple(row.value for row in rows),(700.,-200.))
                self.assertEqual(tuple((row.evaluation_count,row.contribution_count,
                    row.skipped_count) for row in self.snapshots[result.metadata.run_id]),((5,2,3),(5,1,4)))
                self.assertEqual(tuple(dict((reason.value,count) for reason,count in row.skip_counts.items())
                    for row in self.snapshots[result.metadata.run_id]),(dict(missing_input=1,condition_false=2,evaluation_error=0,nonfinite_input=0),
                                      dict(missing_input=1,condition_false=3,evaluation_error=0,nonfinite_input=0)))
                self.assertFalse(result.contributions_available)
                with self.assertRaises(ContributionsUnavailableError):
                    result.iter_contributions()
                output_manifest=result.write(root/'none-published')
                published=json.loads((output_manifest.manifest_path).read_text(encoding='utf-8'))
                self.assertEqual(published['status'],'completed')
                self.assertNotIn('contributions',published['row_counts'])
                self.assertFalse(any(p.name.startswith('contributions_') for p in output_manifest.output_files))
                with (published_file(output_manifest,'calculations.jsonl')).open('rb') as stream:
                    decoded=tuple(decode_row(line,1048576) for line in stream)
                self.assertEqual(summary_values(decoded),summary_values(rows))
                self.assertFalse(any(p.name.startswith('quality_') for p in output_manifest.output_files))
                config['outputs']['contributions']='full'
                full = self.run_result(AnalysisPlan.from_dict(current_fixture(config),base_dir=root),root/'full')
                self.assertEqual(summary_values(rows),summary_values(drain(full.iter_calculations())))
                self.assertEqual(len(drain(full.iter_contributions())),10)
                self.close_result(result)
                self.close_result(full)

    def test_none_preserves_half_open_domain_empty_skipped_and_zero(self):
        """空输入、全跳过与有效零不混淆，右端点排除。参数: 无。返回: None。异常: 断言失败。"""
        cases=(('domain',None,('0s','3s'),True,(400.,-200.),(4,4),(1,1),None),
            ('empty',(),('0s','5s'),True,(None,None),(0,0),(0,0),'no_evaluations'),
            ('skipped',((0,256,0),(1,256,None),(2,257,0)),('0s','5s'),True,
                (None,None),(2,2),(0,0),'all_skipped'),
            ('zero',((0,256,4000),(0,256,-4000),(1,257,0)),('0s','5s'),False,
                (0.,0.),(2,2),(2,2),None))
        for name,frames,domain,disjunction,values,evaluations,counts,reason in cases:
            with self.subTest(case=name):
                root,_,plan=self.fixture(frames=frames,domain=domain,disjunction=disjunction,batch_rows=1)
                result=self.run_result(plan,root/'run',forbid=True,direct=True)
                rows=drain(result.iter_calculations())
                self.assertEqual(tuple(row.value for row in rows),values)
                self.assertEqual(tuple(row.evaluation_count for row in self.snapshots[result.metadata.run_id]),evaluations)
                self.assertEqual(tuple(row.contribution_count for row in self.snapshots[result.metadata.run_id]),counts)
                self.assertEqual(tuple(row.reason for row in self.snapshots[result.metadata.run_id]),(reason,reason))
                self.close_result(result)

    def test_mixed_none_preserves_events_windows_select_and_source(self):
        """混合任务保留普通结果，none不构造明细或消息历史。参数: 无。返回: None。异常: 断言失败。"""
        root,config,plan=self.fixture(mixed=True)
        self.assertEqual(plan.outputs.contributions,'none')
        none=self.run_result(plan,root/'none',forbid=True)
        config['outputs']['contributions']='full'
        full=self.run_result(AnalysisPlan.from_dict(current_fixture(config),base_dir=root),root/'full')
        for method in ('iter_events','iter_segments','iter_selections'):
            left=drain(getattr(none,method)());right=drain(getattr(full,method)())
            self.assertTrue(left,method)
            self.assertEqual(tuple(encode_row(replace(row,sequence=0),1048576) for row in left),tuple(encode_row(replace(row,sequence=0),1048576) for row in right))
        self.assertEqual(summary_values(drain(none.iter_calculations())),summary_values(drain(full.iter_calculations())))
        self.assertFalse(tuple((root/'none').rglob('decoded_messages.jsonl')))
        self.assertEqual(none.metadata.input_diagnostics,())
        self.close_result(none)
        self.close_result(full)

    def test_ordinary_plan_none_keeps_normal_results_and_empty_contribution_api(self):
        """无逐消息任务时none不改变原普通表或空贡献游标。参数: 无。返回: None。异常: 断言失败。"""
        root,config,_=self.fixture(mixed=True)
        config['message_calculations']=[]
        plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
        self.assertEqual(plan.message_calculations,())
        none=self.run_result(plan,root/'none',forbid=True)
        config['outputs']['contributions']='full'
        full=self.run_result(AnalysisPlan.from_dict(current_fixture(config),base_dir=root),root/'full')
        for method in ('iter_events','iter_segments','iter_selections'):
            left=drain(getattr(none,method)());right=drain(getattr(full,method)())
            self.assertTrue(left,method)
            self.assertEqual(tuple(encode_row(replace(row,sequence=0),1048576) for row in left),tuple(encode_row(replace(row,sequence=0),1048576) for row in right))
        for result in (none,full):
            self.assertFalse(result.contributions_available)
            with self.assertRaises(ContributionsUnavailableError):
                result.iter_contributions()
        self.close_result(none)
        self.close_result(full)

    def test_parser_default_invalid_values_and_strategy_have_no_source_io(self):
        """选项在读源前严格校验，省略为none且不调用旧策略选择器。参数: 无。返回: None。异常: 断言失败。"""
        root,config,_=self.fixture()
        try:
            from jsonschema import Draft202012Validator
        except ModuleNotFoundError as exc:
            self.skipTest('缺schema验证依赖: '+exc.name)
        schema=Path(__file__).resolve().parents[2]/'Docs/Schema/analysis.schema.json'
        validator=Draft202012Validator(json.loads(schema.read_text(encoding='utf-8')))
        self.assertFalse(list(validator.iter_errors(current_fixture(config))))
        with patch.object(Path,'open',side_effect=AssertionError('静态解析不得打开来源')):
            default=deepcopy(config);default['outputs'].pop('contributions')
            parsed=AnalysisPlan.from_dict(current_fixture(default),base_dir=root)
            self.assertEqual(parsed.outputs.contributions,'none')
            self.assertEqual(AnalysisPlan.from_dict(current_fixture(config),base_dir=root).outputs.contributions,'none')
            for invalid in (None,True,0,'summary','NONE',[],{}):
                with self.subTest(value=repr(invalid)):
                    changed=deepcopy(config);changed['outputs']['contributions']=invalid
                    self.assertTrue(list(validator.iter_errors(current_fixture(changed))))
                    with self.assertRaises((TypeError,ValueError)):
                        AnalysisPlan.from_dict(current_fixture(changed),base_dir=root)

    def test_current_none_preserves_nonfinite_signed_zero_and_raw_bool_direction(self):
        """直接投影手写解码值，核整数DBC不能表达的非有限/布尔/带符号零。参数: 无。返回: None。异常: 数值/费用断言。"""
        from message_calculation_fixture import synthetic_message_plan,synthetic_message_records
        from chronaxis.sources.can_updates import CANUpdateProjection
        from chronaxis.sources.can_spec import can_field_from_key
        from chronaxis.results.budget import ResourceBudget
        for backend in ('reference','numpy'):
            for constant in (False,True):
                with self.subTest(backend=backend,constant=constant):
                    plan,signal=synthetic_message_plan(self.root(),backend=backend,disjunction=True,constant=constant,
                        unicode_text=False,batch_rows=3)
                    inputs=synthetic_message_records(signal)
                    if not constant:
                        decoded,time,quantized=inputs[8]
                        inputs=inputs[:8]+((replace(decoded,values={signal:-0.0}),time,quantized),)
                    projection=CANUpdateProjection('bus','session',
                        tuple(can_field_from_key(item.definition.field) for item in plan.signals))
                    updates=tuple(projection.build(row.frame,row.sequence,row.values,time)
                                  for row,time,_ in inputs)
                    results=[]
                    for mode in ('full','none'):
                        budget=ResourceBudget();details=[];states=[]
                        for request in plan.message_calculations:
                            owner=CurrentMessageCalculation(request,plan.sources,plan.bindings,'session',budget,
                                backend=backend,batch_rows=3,
                                contribution_consumer=(lambda contribution, quality: details.append(contribution)) if mode=='full' else None)
                            try:
                                for start in range(0,len(updates),3):
                                    owner.consume(updates[start:start+3])
                                state=owner.snapshot();states.append(state)
                                counts={reason.value:count for reason,count in state.skip_counts.items()}
                                self.assertEqual(counts['missing_input'],1)
                                self.assertEqual(counts['nonfinite_input'],3)
                            finally:
                                owner.close()
                        expected=(5.0,1.25) if constant else (3.0,-.5)
                        self.assertEqual(tuple(state.value for state in states),expected)
                        self.assertEqual(len(details),len(inputs)*2 if mode=='full' else 0)
                        results.append(tuple((v.value,v.evaluation_count,v.contribution_count,v.skip_counts) for v in states))
                        self.assertEqual(budget.ram_bytes,0)
                    self.assertEqual(results[0],results[1])


if __name__=='__main__':
    unittest.main()
