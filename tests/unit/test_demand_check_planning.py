"""验证按实际消费者选择CAN检查与时间范围，不读取BLF、DBC或创建进程。

输入为既有合成静态配置及独立变体；输出为schema、计划、需求和解释断言。
测试证明无时间整文件声明使用None而非伪造坐标，显式domain不能被优化忽略，
普通分析、完整诊断和原帧仍保留其时间需求。除独立省范围运行对照外，只在类初始化读取schema；静态
计划操作均禁止输入I/O。来源已读、数值正确和性能收益由运行专项另行验证。
device_label: home；M2-06/C/C14。
"""

from configuration_fixtures import current_fixture

from copy import deepcopy
from dataclasses import replace
import json
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator

from chronaxis import AnalysisPlan, PlanValidationError, AnalysisRunner, explain_analysis_plan, validate_analysis_plan
from chronaxis.core.declarations import DeclarationBindings
from chronaxis.core.models import Interval
from chronaxis.planning.input_requirements import collect_input_requirements
from chronaxis.planning.legacy_execution import require_can_decode_scope
from chronaxis.planning.export_options import CANFramesOutput
from chronaxis.results.frame_exports import FrameExportSpec
from chronaxis.results.errors import AnalysisError
from test_can_decode_scope_planning import ROOT, requested_config, static_only
from test_can_planning import can_config


def whole_file_config():
    """生成纯单CAN固定周期总计，并明确省略用户时间筛选。

    参数: 无。返回: 独立JSON配置dict，保合成路径、信号和计算公式。
    异常: 无主动异常；不接触磁盘输入或用户配置。
    """
    config = requested_config()
    config['dataset'].pop('domain')
    return config


class DemandCheckPlanningTests(unittest.TestCase):
    """用需求矩阵检查静态分支，每例配置独立，不持有来源或运行资源。"""

    @classmethod
    def setUpClass(cls):
        """读取一次公开schema，独立核标准语法。

        参数: 无。返回: None，保存标准验证器。异常: 文件、JSON或schema错误直接失败。
        """
        schema = json.loads((ROOT / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def test_omitted_domain_has_no_fake_time_and_explicit_scope_reason(self):
        """纯整文件任务省去时间，None不冒充空区间或来源观测。

        参数: 无。返回: None。异常: 伪造端点、需求错误、配置改写或静态I/O使断言失败。
        """
        config = whole_file_config()
        original = deepcopy(config)
        self.assertTrue(self.validator.is_valid(current_fixture(config)))
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            requirements = collect_input_requirements(plan)
            explanation = explain_analysis_plan(plan)
        self.assertIsNone(plan.dataset.domain)
        self.assertIsNone(plan.bindings.domain)
        self.assertFalse(plan.dataset.domain_explicit)
        self.assertEqual(config, original)
        self.assertEqual(requirements.observation_sources, ())
        source = requirements.for_source('bus')
        self.assertEqual((source.time_scope, source.input_check), ('none', 'auto'))
        self.assertEqual(source.decode_frame_ids, (256,))
        self.assertTrue(source.reasons)
        self.assertEqual(explanation.input_requirements, requirements)
        text = ' '.join(explanation.validation.warnings)
        self.assertIn('time_scope=none', text)
        self.assertIn('未采集报文时间', text)
        self.assertIn('不施时间筛选', text)

    def test_explicit_domain_keeps_selected_time_and_old_binding_identity(self):
        """显式范围仅省无关时间，用户半开时间筛选及旧声明v1身份保持。

        参数: 无。返回: None。异常: domain被忽略或旧Interval身份变化使断言失败。
        """
        config = requested_config()
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            source = collect_input_requirements(plan).for_source('bus')
            old = DeclarationBindings(plan.bindings.session_id, plan.bindings.timebase,
                plan.bindings.domain, plan.bindings.sources, plan.bindings.signals,
                plan.bindings.derived_names, plan.bindings.synchronization)
            whole = AnalysisPlan.from_dict(current_fixture(whole_file_config()), base_dir=ROOT)
        self.assertEqual(source.time_scope, 'selected')
        self.assertTrue(plan.dataset.domain_explicit)
        self.assertEqual((plan.dataset.domain.start_ns, plan.dataset.domain.end_ns), (0, 12_000_000_000))
        self.assertEqual(old.identity, plan.bindings.identity)
        self.assertNotEqual(whole.bindings.identity, old.identity)

    def test_full_check_keeps_source_time_without_forcing_full_decode(self):
        """显式full可整文件诊断时间，但解码仍requested且不伪造筛选范围。

        参数: 无。返回: None。异常: 两种开关耦合或完整来源观测丢失即失败。
        """
        config = whole_file_config()
        config['sources'][0]['input_check'] = 'full'
        self.assertTrue(self.validator.is_valid(current_fixture(config)))
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            requirements = collect_input_requirements(plan)
        self.assertEqual(plan.sources[0].config.decode_scope, 'requested')
        self.assertEqual(requirements.for_source('bus').time_scope, 'source')
        self.assertEqual(requirements.for_source('bus').input_check, 'full')
        self.assertEqual(requirements.observation_sources, ('bus',))
        self.assertIsNone(plan.dataset.domain)

    def test_all_decode_keeps_explicit_domain_and_full_time_diagnostic(self):
        """all保完整时间检查；纯逐消息计划仍可不声明筛选范围。

        参数: 无。返回: None。异常: all静默省时间或无筛选声明被补造范围即失败。
        """
        config = requested_config()
        config['sources'][0]['decode_scope'] = 'all'
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            source = collect_input_requirements(plan).for_source('bus')
        self.assertEqual(source.time_scope, 'source')
        self.assertEqual(source.input_check, 'full')
        self.assertEqual(plan.sources[0].config.input_check, 'auto')
        missing = deepcopy(config)
        missing['dataset'].pop('domain')
        self.assertTrue(self.validator.is_valid(current_fixture(missing)))
        with static_only():
            self.assertIsNone(AnalysisPlan.from_dict(current_fixture(missing), base_dir=ROOT).dataset.domain)

    def test_time_consumers_keep_full_source_with_optional_domain(self):
        """普通消费者省略范围后仍读取必要时间；逐消息与无消费者来源继续省略时间工作。

        参数: 无。返回: None。异常: 来源需求丢失或省略范围生成假端点即失败。
        """
        ordinary = can_config()
        cases = []
        for key in ('rules', 'calculations'):
            config = requested_config()
            config[key] = deepcopy(ordinary[key])
            cases.append((key, config))
        windows = requested_config()
        windows.update(rules=deepcopy(ordinary['rules']), windows=deepcopy(ordinary['windows']))
        cases.append(('windows', windows))
        full = requested_config()
        full['outputs']['contributions'] = 'full'
        cases.append(('contributions', full))
        raw = requested_config()
        raw['outputs']['can_frames'] = dict(source='bus', format='asc')
        cases.append(('raw', raw))
        multiple = requested_config()
        other = deepcopy(multiple['sources'][0])
        other['name'] = 'other'
        multiple['sources'].append(other)
        cases.append(('multiple', multiple))
        no_calculation = requested_config()
        no_calculation['message_calculations'] = []
        cases.append(('no_calculation', no_calculation))
        for name, config in cases:
            with self.subTest(case=name), static_only():
                plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
                requirements = collect_input_requirements(plan)
                expected = {'contributions': ('selected',), 'multiple': ('selected', 'none'),
                            'no_calculation': ('none',)}.get(name, ('source',))
                self.assertEqual(tuple(item.time_scope for item in requirements.sources), expected)
                missing = deepcopy(config)
                missing['dataset'].pop('domain')
                self.assertTrue(self.validator.is_valid(current_fixture(missing)))
                full_input = AnalysisPlan.from_dict(current_fixture(missing), base_dir=ROOT)
                self.assertIsNone(full_input.dataset.domain)
                self.assertIsNone(full_input.bindings.domain)
                full_requirements = collect_input_requirements(full_input)
                full_expected = {'contributions': ('none',), 'multiple': ('none', 'none'),
                                 'no_calculation': ('none',)}.get(name, ('source',))
                self.assertEqual(tuple(item.time_scope for item in full_requirements.sources),full_expected)
                self.assertEqual(tuple(item.required_fields for item in full_requirements.sources),
                                 tuple(item.required_fields for item in requirements.sources))

    def test_input_check_default_and_invalid_values_have_no_input_io(self):
        """默认auto不回填用户配置；未知值、空值及非原生类型在静态边界拒绝。

        参数: 无。返回: None。异常: 非法值被转换或配置身份材料改写即失败。
        """
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(requested_config()), base_dir=ROOT)
        self.assertEqual(plan.sources[0].config.input_check, 'auto')
        self.assertNotIn('input_check', plan.raw_config['sources'][0])
        for value in (None, True, 1, [], {}, '', 'FULL', 'requested'):
            config = requested_config()
            config['sources'][0]['input_check'] = value
            with self.subTest(value=value), static_only():
                self.assertFalse(self.validator.is_valid(current_fixture(config)))
                with self.assertRaises(PlanValidationError) as caught:
                    AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
                self.assertEqual(caught.exception.path, '$.sources[0].reader.input_check')
                with self.assertRaises((TypeError, ValueError)):
                    replace(plan.sources[0].config, input_check=value)

    def test_typed_domain_presence_cannot_bypass_consumer_guard(self):
        """typed替换不能把不存在的domain标记为显式；消费者可以使用完整输入。

        参数: 无。返回: None。异常: reports接受不一致声明或漏掉消费者即失败。
        """
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(whole_file_config()), base_dir=ROOT)
            bad = replace(plan, dataset=replace(plan.dataset, domain_explicit=True))
            self.assertFalse(validate_analysis_plan(bad).valid)
            full = replace(plan, outputs=replace(plan.outputs, contributions='full'))
            self.assertTrue(validate_analysis_plan(full).valid)

    def test_typed_time_request_and_consumers_fail_before_session_creation(self):
        """旧绑定和矛盾时间声明仍拒绝；完整输入可增加已正确编译的普通消费者。

        参数: 无。返回: None；非法时间声明在创建RunSession前拒绝，合法消费者保持有效。
        异常: 漏检、误报运行阶段失败、触碰输入或创建资源使本用例失败。
        """
        with static_only():
            whole = AnalysisPlan.from_dict(current_fixture(whole_file_config()), base_dir=ROOT)
            explicit = AnalysisPlan.from_dict(current_fixture(requested_config()), base_dir=ROOT)
            mixed_config = whole_file_config()
            mixed_config['calculations'] = can_config()['calculations']
            mixed = AnalysisPlan.from_dict(current_fixture(mixed_config), base_dir=ROOT)
        # 跨计划只借有限静态节点制造typed负例，不用raw_config补回缺失时间。
        source = whole.sources[0]
        other = replace(source, name='other', config=replace(source.config, name='other'))
        cases = [
            ('none_marked_explicit', replace(whole, dataset=replace(whole.dataset, domain_explicit=True))),
            ('domain_marked_implicit', replace(explicit, dataset=replace(explicit.dataset, domain_explicit=False))),
            ('removed_domain_old_binding', replace(explicit,
                dataset=replace(explicit.dataset, domain=None, domain_explicit=False))),
            ('added_domain_old_binding', replace(whole,
                dataset=replace(whole.dataset, domain=Interval(0, 1), domain_explicit=True))),
            ('foreign_domain', replace(whole, dataset=replace(whole.dataset, domain='not_an_interval', domain_explicit=True))),
            ('non_boolean_presence', replace(whole, dataset=replace(whole.dataset, domain_explicit=0))),
            ('mixed', replace(whole, calculations=mixed.calculations, intervals=mixed.intervals)),
            ('full_contributions', replace(whole, outputs=replace(whole.outputs, contributions='full'))),
            ('can_frames', replace(whole, outputs=replace(whole.outputs,
                can_frames=CANFramesOutput('bus', FrameExportSpec('asc'))))),
            ('multiple_sources', replace(whole, sources=whole.sources + (other,))),
            ('all_decode', replace(whole, sources=(replace(source,
                config=replace(source.config, decode_scope='all')),))),
        ]
        # 若run未先拒绝，伪模块工厂会留下调用证据，避免把运行期失败误当门禁通过。
        fake_module = ModuleType('chronaxis.execution.run_session')
        fake_module.RunSession = Mock(side_effect=AssertionError('禁止构造RunSession'))
        runner = AnalysisRunner()
        for name, bad in cases:
            with self.subTest(case=name), static_only(), \
                    patch.dict('sys.modules', {'chronaxis.execution.run_session': fake_module}):
                if name in ('full_contributions', 'multiple_sources', 'all_decode', 'can_frames', 'mixed'):
                    self.assertTrue(runner.validate(bad).valid)
                    self.assertIsNone(require_can_decode_scope(bad))
                    fake_module.RunSession.assert_not_called()
                    continue
                self.assertFalse(runner.validate(bad).valid)
                with self.assertRaises(PlanValidationError):
                    require_can_decode_scope(bad)
                with self.assertRaises(AnalysisError) as caught:
                    runner.run(bad, work_dir='work/forbidden-typed-domain')
                self.assertIn('计划尚不能执行', str(caught.exception))
                fake_module.RunSession.assert_not_called()

    def test_unbounded_ordinary_plan_matches_actual_explicit_domain(self):
        """两后端真实运行三条记录：3/1/3W两秒4J，省略域与显式实际域结果完全一致。"""
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from uuid import uuid4
        config=dict(config_version=4,dataset=dict(name='observed'),
            sources=[dict(name='meter',source_type='memory',rows=[
                dict(time=str(t)+'s',values=dict(power=v)) for t,v in ((0,3),(1,1),(2,3))])],
            signals=[dict(name='power',source='meter',field='power',dtype='float64',unit='W',valid_for='3s')],
            calculations=[dict(name='energy',operation='integral',expr='power',unit='J')],
            execution=dict(batch_rows=1))
        with TemporaryDirectory(dir='work',prefix='demand-full-domain-') as directory:
            for backend in ('reference','numpy'):
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(config),Path(directory)/uuid4().hex) as result:
                    implicit=tuple(result.iter_calculations())
                explicit=deepcopy(config);explicit['dataset']['domain']=dict(start='0s',end='2s')
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(explicit),Path(directory)/uuid4().hex) as result:
                    self.assertEqual(implicit,tuple(result.iter_calculations()))
                self.assertEqual(implicit[0].value,4.)
