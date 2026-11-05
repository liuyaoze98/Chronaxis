"""验证新间隔声明、迁移及未接线拒绝，防止配置通过被误当作运行成功。

输入是独立合成配置，真实报文/DBC路径故意不存在。schema使用本地注册
资源，不访问网络；静态入口禁止输入I/O，结果对照手写声明预期。
不伪造fixed/DBC数值已经计算，不创建性能数据或改变旧测试基线。
"""

from configuration_fixtures import current_fixture

from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError, validate_analysis_plan, explain_analysis_plan
from chronaxis.analysis_cli import explanation_json, run_static
from chronaxis.planning import IntervalChoice, IntervalPlan, DiagnosticPlan
from chronaxis.results import AnalysisError
from test_can_decode_scope_planning import static_only
from test_plan_message_calculations import legacy_config


def fixture():
    """创建单信号功率积分配置；0/0.12/0.30秒仅声明，测试不运行新模式。

    参数: 无。返回: 每次新建的schema2配置dict，真实时间与单位显式。异常: 无主动异常。副作用: 无。
    """
    return dict(config_version=4,
        dataset=dict(name='demo', entity='sensor', session='run', domain=dict(start='0s', end='0.3s')),
        sources=[dict(name='table', source_type='memory', time=dict(time_type='relative', unit='s', origin='demo'),
                      rows=[dict(time=t, values={'raw':4000}) for t in ('0s','0.12s','0.3s')])],
        signals=[dict(name='power', source='table', field='raw', dtype='float64', unit='W', valid_for='1s')],
        calculations=[dict(name='energy', scope='session', operation='integral', expr='power', unit='J')])


class IntervalPlanningTests(unittest.TestCase):
    """对照旧默认、明确驱动与静态拒绝，不启动任何实际读取器。"""

    def build(self, config):
        """在既有禁止I/O探针中构建计划；失败原样成为测试错误。

        参数: config(dict)为本例独立配置。返回: AnalysisPlan。异常: PlanValidationError或禁止I/O探针异常直接传播。副作用: 临时安装并恢复静态探针，不读写输入。
        """
        with static_only():
            return AnalysisPlan.from_dict(current_fixture(config))

    def test_current_defaults_and_no_old_migration_entry(self):
        """当前配置默认无贡献，显式选择保持；旧版本和迁移别名均拒绝。"""
        import chronaxis.planning as planning
        self.assertFalse(hasattr(planning, 'migrate_schema1'))
        for explicit in (None, 'none', 'full'):
            value = fixture()
            if explicit is not None:
                value['outputs'] = {'contributions': explicit}
            before = deepcopy(value)
            plan = self.build(value)
            self.assertEqual(value, before)
            self.assertEqual(plan.outputs.contributions, explicit or 'none')
            self.assertEqual(plan.intervals.default.mode, 'actual')
            self.assertEqual(plan.diagnostics, DiagnosticPlan())
        for version in (1, 2):
            value = fixture()
            value['config_version'] = version
            with self.assertRaises(PlanValidationError):
                self.build(value)

    def test_fixed_choice_resolves_single_driver_without_changing_input_times(self):
        """两个间隔的选择只有一份有限声明；实际0/120/300ms坐标原样保留。

        参数: 无，使用本例独立配置。返回: None。异常: AssertionError或意外配置/运行错误使测试失败。副作用: 仅内存声明及测试明确的静态探针；不读报文或DBC。
        """
        config = fixture()
        config['intervals'] = {'default':{'mode':'fixed','value':'100ms'}}
        plan = self.build(config)
        self.assertEqual(plan.intervals.resolved, (('energy', IntervalChoice('fixed',100_000_000,'power')),))
        self.assertEqual(tuple(row.time_ns for row in plan.sources[0].config.rows), (0,120_000_000,300_000_000))
        self.assertEqual(plan.diagnostics, DiagnosticPlan())

    def test_multiple_candidates_require_driver_and_overrides_select_it(self):
        """两个独立信号不能自动选第一个；指定power后保留另一路表达式依赖。

        参数: 无，使用本例独立配置。返回: None。异常: AssertionError或意外配置/运行错误使测试失败。副作用: 仅内存声明及测试明确的静态探针；不读报文或DBC。
        """
        config = fixture()
        config['signals'].append(dict(name='other',source='table',field='other',dtype='float64',unit='W',valid_for='1s'))
        for row in config['sources'][0]['rows']:
            row['values']['other'] = 1
        config['derived'] = {'combined':{'expr':'power + other','unit':'W'}}
        config['calculations'][0]['expr'] = 'combined'
        config['intervals'] = {'default':{'mode':'fixed','value':'100ms'}}
        with self.assertRaisesRegex(PlanValidationError, 'driver'):
            self.build(config)
        config['intervals']['overrides'] = {'energy':{'mode':'fixed','value':'10ms','driver':'power'}}
        plan = self.build(config)
        self.assertEqual(plan.intervals.resolved[0][1].step_ns, 10_000_000)
        self.assertEqual(set(plan.calculations[0].signal.dependencies), {'power','other'})

    def test_independent_driver_uses_existing_synchronization_contract(self):
        """独立时钟必须有同步依据；已有显式校准可以使用，不强制原起点相同。

        参数: 无，构造两个不同相对起点。返回: None。异常: 误接受无依据驱动或误拒绝已校准驱动使断言失败。
        """
        from chronaxis.core.binding import SynchronizationEvidence
        from chronaxis.planning.intervals import resolve_intervals
        config = fixture()
        clock = deepcopy(config['sources'][0])
        clock['name'] = 'clock'
        clock['time']['origin'] = 'another_origin'
        config['sources'].append(clock)
        config['signals'].append(dict(name='tick', source='clock', field='raw', dtype='float64', unit='W', valid_for='1s'))
        plan = self.build(config)
        choice = IntervalChoice('fixed', 100_000_000, 'tick')
        with self.assertRaisesRegex(PlanValidationError, '同步依据'):
            resolve_intervals(plan, choice, ())
        evidence = SynchronizationEvidence('clock', plan.bindings.timebase, 'synthetic known common origin')
        synced = replace(plan, bindings=replace(plan.bindings, synchronization=(evidence,)))
        self.assertEqual(resolve_intervals(synced, choice, ()).resolved, (('energy', choice),))

    def test_dbc_requires_raw_source_and_never_opens_database(self):
        """已解析数据拒绝DBC；BLF/ASC/原始CSV的有限声明均可接受。

        参数: 无，使用本例独立配置。返回: None。异常: AssertionError或意外配置/运行错误使测试失败。副作用: 仅内存声明及测试明确的静态探针；不读报文或DBC。
        """
        plain = fixture()
        plain['intervals'] = {'default':{'mode':'dbc'}}
        with self.assertRaisesRegex(PlanValidationError, '原始报文'):
            self.build(plain)
        config = legacy_config()
        config.update(config_version=4)
        config.pop('message_calculations')
        config['calculations'] = fixture()['calculations']
        config['intervals'] = {'default':{'mode':'dbc'}}
        plan = self.build(config)
        self.assertEqual(plan.intervals.resolved[0][1], IntervalChoice('dbc',driver='power'))
        # 三种公开配置都经真实解析；输入路径不存在，静态过程不能打开它们。
        for kind in ('can_asc','raw_can_csv'):
            text_config=deepcopy(config)
            source=text_config['sources'][0]
            source.pop('legacy_profile')
            source['source_type']=kind
            if kind=='raw_can_csv':
                from chronaxis.sources.raw_csv_layout import CANCSVLayout, ColumnMapping
                fields={name:ColumnMapping(column=name) for name in ('timestamp','frame_id','data','payload_length')}
                fields.update({name:ColumnMapping(fixed=value) for name,value in
                               dict(channel=0,is_rx=True,is_extended=False,is_fd=False,frame_kind='data').items()})
                source['parser']={'layout':CANCSVLayout(fields).to_dict(),'time_format':'numeric'}
            self.assertEqual(self.build(text_config).intervals.resolved,plan.intervals.resolved)

    def test_same_message_signals_are_one_driver_candidate(self):
        """同一原消息内两个信号不误判为两个更新源，不需要重复填写driver。

        参数: 无，使用本例独立配置。返回: None。异常: AssertionError或意外配置/运行错误使测试失败。副作用: 仅内存声明及测试明确的静态探针；不读报文或DBC。
        """
        config = legacy_config()
        config.update(config_version=4)
        config.pop('message_calculations')
        other = deepcopy(config['signals'][0])
        other['name']='other'; other['field']['signal']='Other'
        config['signals'].append(other)
        config['derived']={'combined':{'expr':'power + other','unit':'W'}}
        config['calculations']=[dict(name='energy',scope='session',operation='integral',expr='combined',unit='J')]
        config['intervals']={'default':{'mode':'fixed','value':'100ms'}}
        self.assertEqual(len(self.build(config).intervals.resolved),1)

    def test_edges_have_no_interval_work_but_parent_dependencies_are_kept(self):
        """纯边沿不生成计时选择；事件范围的父规则仍参与指标驱动歧义判断。

        参数: 无，使用功率和另一独立信号的合成配置。返回: None。
        异常: 多余计时消费者、漏掉父依赖或错误拒绝导致断言失败。副作用: 仅静态探针。
        """
        config=fixture()
        config['rules']=[dict(name='pulse',rule_type='rising_edge',condition='power > 0')]
        config['intervals']={'default':{'mode':'fixed','value':'100ms'}}
        self.assertEqual(tuple(name for name,_ in self.build(config).intervals.resolved),('energy',))
        # 将事件条件换成另一原字段，两个不同更新源必须要求明确driver。
        config['signals'].append(dict(name='other',source='table',field='other',dtype='float64',unit='W',valid_for='1s'))
        for row in config['sources'][0]['rows']:
            row['values']['other']=1
        config['rules'][0]['condition']='other > 0'
        config['calculations'][0]['scope']='event:pulse'
        with self.assertRaisesRegex(PlanValidationError,'driver'):
            self.build(config)
        config['intervals']['default']['driver']='power'
        self.assertEqual(self.build(config).intervals.resolved[0][1].driver,'power')

    def test_invalid_modes_fields_units_and_unused_overrides_fail(self):
        """拒绝非法选择与无消费者覆盖，不能把无效声明悄悄忽略。

        参数: 无，使用本例独立配置。返回: None。异常: AssertionError或意外配置/运行错误使测试失败。副作用: 仅内存声明及测试明确的静态探针；不读报文或DBC。
        """
        invalid = [None, {'default':None}, {'default':{'mode':'fixed'}},
            {'default':{'mode':'fixed','value':'0s'}}, {'default':{'mode':'fixed','value':0.1}},
            {'default':{'mode':'fixed','value':'1e99s'}}, {'default':{'mode':'dbc','value':'1s'}},
            {'default':{'mode':'actual','driver':'power'}}, {'default':{'mode':'fixed','value':'1s','driver':None}},
            {'default':{'mode':'random'}},
            {'overrides':{'missing':{'mode':'actual'}}},
            {'default':{'mode':'fixed','value':'1s','driver':'missing'}}]
        for value in invalid:
            with self.subTest(value=value):
                config=fixture();config['intervals']=value
                with self.assertRaises(PlanValidationError): self.build(config)
        # Removed root overrides is rejected even when its value is an empty array.
        config=current_fixture(fixture());config['intervals']={'overrides':[]}
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(config)

    def test_diagnostics_are_independent_and_strict(self):
        """一个开关不启用另外两个，也不改变贡献选择；数字和未知键拒绝。

        参数: 无，使用本例独立配置。返回: None。异常: AssertionError或意外配置/运行错误使测试失败。副作用: 仅内存声明及测试明确的静态探针；不读报文或DBC。
        """
        for key in ('trace','integrity','retain_work'):
            config=fixture();config['diagnostics']={key:True}
            plan=self.build(config)
            self.assertEqual(sum((plan.diagnostics.trace,plan.diagnostics.integrity,plan.diagnostics.retain_work)),1)
            self.assertEqual(plan.outputs.contributions,'none')
        for value in ({'trace':1},{'retain_work':'yes'},{'extra':False},None):
            config=fixture();config['diagnostics']=value
            with self.assertRaises(PlanValidationError): self.build(config)

    def test_only_current_version_and_no_redundant_semantic_marker(self):
        """旧结构及冗余语义版本被拒绝，不能自动迁移或隐式回退。"""
        for version in (1, 2, 3, True, 4.0, '4'):
            config = fixture()
            config['config_version'] = version
            with self.assertRaises(PlanValidationError):
                self.build(config)
        config = fixture()
        config['semantic_version'] = '0.2'
        with self.assertRaises(PlanValidationError):
            self.build(config)

    def test_implemented_execution_reports_without_static_io(self):
        """API和CLI如实报告间隔与详细追溯可用；静态解释不运行输入或创建目录。

        参数: 无，使用本例独立配置。返回: None。异常: AssertionError或意外配置/运行错误使测试失败。副作用: 仅内存声明及测试明确的静态探针；不读报文或DBC。
        """
        config=fixture();config['intervals']={'default':{'mode':'fixed','value':'100ms'}}
        # 普通周期及详细追溯已接入，静态报告可用仍不能当作输入已经运行。
        config['diagnostics']={'trace':True}
        plan=self.build(config)
        with static_only():
            report=validate_analysis_plan(plan)
            self.assertTrue(report.execution_ready)
            self.assertEqual(report.capability_status['interval_execution'],'implemented')
            self.assertEqual(report.capability_status['demand_lifecycle'],'implemented')
            explained=explanation_json(explain_analysis_plan(plan))
        self.assertEqual(explained['intervals']['energy']['driver'],'power')
        args=SimpleNamespace(plan='unused.json',backend=None,command='explain',format='json')
        sink=io.StringIO()
        with patch('chronaxis.analysis_cli.load_analysis_plan',return_value=plan),redirect_stdout(sink),static_only():
            code=run_static(args)
        self.assertEqual(code,0)
        self.assertEqual(json.loads(sink.getvalue())['intervals'],explained['intervals'])

    def test_typed_replacement_cannot_bypass_resolved_declarations(self):
        """typed解析结果与当前计划不一致时报告错误，不从旧raw_config恢复覆盖。

        参数: 无，使用本例独立配置。返回: None。异常: AssertionError或意外配置/运行错误使测试失败。副作用: 仅内存声明及测试明确的静态探针；不读报文或DBC。
        """
        plan=self.build(fixture())
        bad=replace(plan,intervals=IntervalPlan(resolved=(('energy',IntervalChoice('fixed',1,'power')),)))
        self.assertTrue(any('不一致' in value for value in validate_analysis_plan(bad).errors))
        changed=replace(plan,diagnostics=None)
        self.assertFalse(validate_analysis_plan(changed).execution_ready)

    def test_current_schema_is_self_contained_and_agrees_on_structure(self):
        """单一当前规范本地验证，不注册旧结构也不访问网络。"""
        root=Path(__file__).absolute().parents[2]/'Docs'/'Schema'
        schema=json.loads((root/'analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        validator=Draft202012Validator(schema)
        config=fixture();config['intervals']={'default':{'mode':'fixed','value':'100ms'}}
        validator.validate(current_fixture(config))
        for value in ({'mode':'fixed'},{'mode':'actual','driver':'power'},{'mode':'dbc','value':'1ms'}):
            bad=deepcopy(config);bad['intervals']['default']=value
            self.assertTrue(list(validator.iter_errors(current_fixture(bad))))
        for version in (1,2):
            old=deepcopy(config);old['config_version']=version
            self.assertTrue(list(validator.iter_errors(current_fixture(old))))


if __name__ == '__main__':
    unittest.main()
