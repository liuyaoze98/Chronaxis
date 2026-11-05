"""核验公开当前消息计算配置的schema、typed计划和无输入I/O静态报告。

输入为本文件独立合成的单BLF声明；不创建或读取BLF/DBC。标准Draft202012
验证器检查公开JSON结构，AnalysisPlan补跨来源、帧定位、单位与精确参数语义。
测试保原定义对象和配置快照，检查新policy与旧完整cache能力分开、全局ID冲突、
typed替换诚实拒绝及未启用legacy时的旧缺省报告。不运行AnalysisRunner.run或数值核心，
也不把静态可执行、profile标签或手造typed计划当成实际捕获/旧完整兼容证明。
"""

from configuration_fixtures import current_fixture

# 独立夹具与静态副作用探针；只读取一次公开schema，不借用其他TestCase。
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import json
import multiprocessing
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from chronaxis import AnalysisPlan, PlanValidationError, AnalysisRunner, explain_analysis_plan, validate_analysis_plan
from chronaxis.planning.config_groups import public_configuration
from chronaxis.core.expression import validate_expression
from chronaxis.core.message_binding import ExpressionParameter, MessageDeclarations
from chronaxis.core.types import SignalDType
from chronaxis.legacy.records import PROFILE_ID
from chronaxis.planning.models import LegacyMessageSelector, MessageCalculationPlan


ROOT = Path(__file__).absolute().parents[2]


def legacy_config():
    """创建一份power×period×factor的独立纯JSON静态配置。

    参数: 无。返回: 每次新dict，路径指向不存在的合成BLF/DBC，不含真实车型数据。
    异常: 无主动异常；只构造配置，valid_for仅原普通信号声明，不作为消息保持策略。
    """
    field = dict(channel=1, frame_id=256, is_extended=False, is_fd=False,
                  signal='Power.raw')
    return public_configuration(dict(config_version=4,
        dataset=dict(name='legacy_static', entity='synthetic', session='session',
                     domain=dict(start='0s', end='12s')),
        sources=[dict(name='bus', source_type='can_blf', path='work/legacy-static-missing.blf',
            legacy_profile=PROFILE_ID, dbc_by_channel={'1': 'work/legacy-static-missing.dbc'},
            time=dict(time_type='relative', unit='s', origin='synthetic_origin'))],
        signals=[dict(name='power', source='bus', field=field, dtype='int64', input_unit='W', unit='W',
                      valid_for='1ns', same_time_policy='last_by_sequence')],
        message_calculations=[dict(name='energy', source='bus', profile=PROFILE_ID, operation='legacy_sum',
            update_message=dict(channel=1, frame_id=256, is_extended=False, is_fd=False),
            expr='power * period * factor', unit='J',
            parameters=dict(period=dict(value=0.1, unit='s'), factor=dict(value=1, unit='1')),
            message_policy='current_message-v1')],
        metadata=dict(device_label='home', data_kind='synthetic_static')))


def changed(config, keys, value):
    """复制配置后替换叶值，使负例不污染其他用例。

    参数: config为原JSON；keys为现有容器路径；value为新叶值。
    返回: 新dict。异常: KeyError/IndexError为本测试夹具路径错误，不隐藏失败。
    """
    result = deepcopy(config)
    current = result
    for key in keys[:-1]:
        current = current[key]
    current[keys[-1]] = value
    return result


class MessageCalculationPlanningTests(unittest.TestCase):
    """分别核结构、跨对象语义和能力报告，静态操作不接触来源资源。

    schema由标准验证器独立检查；解析器仍须对JSON schema无法表达的原生
    整数、精确FLOAT64、跨来源/消息关系进行严格校验。
    """

    @classmethod
    def setUpClass(cls):
        """读取一次公开schema并核标准结构，随后所有计划输入只在内存。

        参数: 无。返回: None，保存独立验证器。
        异常: 文件/JSON/schema错误直接失败，不跳过验收。
        """
        schema = json.loads((ROOT / 'Docs' / 'Schema' / 'analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)
        # 内部结构规范先加载；下方禁止业务来源I/O的探针仍完整保留。
        from chronaxis.planning.diagnostic_collection import schema_validator
        schema_validator('analysis.schema.json')

    def guard_static(self):
        """阻断来源文件和运行依赖动作，返回可恢复的探针上下文。

        参数: 无。返回: ExitStack，调用方with结束恢复全部patch。
        异常: 发生禁止动作时AssertionError；安装失败也恢复，不伪造输入继续。
        """
        stack = ExitStack()
        original_import = __import__

        def deny_runtime_import(name, globals=None, locals=None, fromlist=(), level=0):
            """只允许静态依赖。参数: 原import参数。返回: 原模块。异常: 运行依赖AssertionError。"""
            forbidden = ('worker', 'export_worker', 'process_read', 'can_reader', 'run_session', 'message_bindings')
            if (name.split('.')[0] in ('can', 'cantools', 'natsort', 'RefProjects')
                    or name.rsplit('.', 1)[-1] in forbidden
                    or any(item in forbidden for item in (fromlist or ()))):
                raise AssertionError('静态legacy计划尝试导入运行组件：' + name)
            return original_import(name, globals, locals, fromlist, level)

        try:
            # 声明中的路径只可词法绝对化，不得检查其存在性、解析符号链接或创建工件。
            for name in ('open', 'read_text', 'read_bytes', 'stat', 'resolve', 'mkdir'):
                stack.enter_context(patch.object(Path, name, side_effect=AssertionError('禁止Path.' + name)))
            stack.enter_context(patch('builtins.open', side_effect=AssertionError('禁止来源open')))
            stack.enter_context(patch.object(multiprocessing, 'get_context', side_effect=AssertionError('禁止spawn')))
            stack.enter_context(patch.object(multiprocessing, 'Process', side_effect=AssertionError('禁止Process')))
            stack.enter_context(patch('builtins.__import__', deny_runtime_import))
            return stack
        except BaseException:
            stack.close()
            raise

    def assert_invalid(self, config, *, schema_reject=True, code='invalid_config', prefix='$.message_calculations'):
        """分别核schema结构边界与解析器语义，保具体错误路径和机器码。

        参数: config为独立变体；schema_reject控制标准结构预期；code/prefix为公共错误预期。
        返回: 原PlanValidationError。异常: 任一误接收、错误路径或静态副作用使测试失败。
        """
        if schema_reject:
            self.assertFalse(self.validator.is_valid(current_fixture(config)))
        else:
            self.assertTrue(self.validator.is_valid(current_fixture(config)))
        with self.guard_static(), self.assertRaises(PlanValidationError) as caught:
            AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
        self.assertEqual(caught.exception.code, code)
        self.assertTrue(caught.exception.path.startswith(prefix), caught.exception.path)
        return caught.exception

    def test_public_plan_schema_and_reports_use_original_declarations_without_io(self):
        """公开配置形成独立消息typed树及能力说明，不读BLF/DBC或运行计算。

        参数: 无。返回: None。异常: 类型、对象身份、参数或能力报告不符使测试失败。
        """
        config = legacy_config()
        self.assertEqual(list(self.validator.iter_errors(current_fixture(config))), [])
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            report, explanation = AnalysisRunner().validate(current_fixture(plan)), AnalysisRunner().explain(plan)
            self.assertEqual(report, validate_analysis_plan(plan))
            self.assertEqual(explanation, explain_analysis_plan(plan))
        calculation = plan.message_calculations[0]
        self.assertIs(type(calculation), MessageCalculationPlan)
        self.assertIs(type(calculation.update_message), LegacyMessageSelector)
        self.assertIs(type(calculation.expr.bindings), MessageDeclarations)
        self.assertIs(calculation.expr.bindings.declarations, plan.bindings)
        self.assertIs(calculation.expr.bindings.resolve('power'), plan.signals[0].definition)
        self.assertEqual(calculation.expr.dependencies, ('power',))
        self.assertEqual((calculation.expr.root.dtype, calculation.unit), (SignalDType.FLOAT64, 'J'))
        self.assertIs(calculation.parameters, calculation.expr.bindings.parameters)
        self.assertEqual([(item.name, item.value, item.unit) for item in calculation.parameters],
                         [('period', 0.1, 's'), ('factor', 1.0, '1')])
        self.assertTrue(all(type(item.value) is float for item in calculation.parameters))
        self.assertEqual(plan.calculations, ())
        self.assertTrue(report.valid)
        self.assertTrue(report.execution_ready)
        self.assertEqual(report.capability_status['legacy_sum'], 'partial')
        self.assertEqual(report.capability_status['legacy_sum_current_message'], 'implemented')
        self.assertEqual(report.capability_status['legacy_sum_profile_compat'], 'unavailable')
        self.assertTrue(any('legacy_evaluation_output=false' in warning for warning in report.warnings))
        node, = explanation.nodes
        self.assertEqual((node.node_id, node.node_type, node.dependencies, node.unit, node.backend),
                         ('energy', 'message_calculation:legacy_sum', ('power',), 'J', 'numpy'))
        with self.assertRaises(FrozenInstanceError):
            calculation.parameters[0].value = 1.0

    def test_empty_legacy_keeps_old_defaults_and_original_identity_inputs(self):
        """未请求legacy时无新能力项或节点，原配置未被补默认字段。

        参数: 无。返回: None。异常: 旧默认报告、声明身份或位置参数布局发生漂移则失败。
        """
        absent = legacy_config()
        absent.pop('message_calculations')
        explicit_empty = deepcopy(absent)
        explicit_empty['message_calculations'] = []
        with self.guard_static():
            first = AnalysisPlan.from_dict(current_fixture(absent), base_dir=ROOT)
            second = AnalysisPlan.from_dict(current_fixture(explicit_empty), base_dir=ROOT)
            report_first, report_second = validate_analysis_plan(first), validate_analysis_plan(second)
        self.assertEqual(first.message_calculations, ())
        self.assertEqual(second.message_calculations, ())
        # 当前结构移除semantic_version；实际位置构造也使用唯一当前字段。
        original_fields = ('config_version', 'dataset', 'sources', 'signals',
            'derived', 'rules', 'windows', 'calculations', 'presets', 'preset_bindings', 'execution',
            'outputs', 'bindings', 'derived_expressions', 'metadata', 'raw_config', 'base_dir',
            'identity', 'message_calculations')
        self.assertEqual(tuple(item.name for item in fields(AnalysisPlan)[:len(original_fields)]), original_fields)
        positional = AnalysisPlan(*(getattr(first, name) for name in original_fields),
            sequences=first.sequences, intervals=first.intervals, diagnostics=first.diagnostics)
        self.assertEqual(positional, first)
        self.assertEqual(positional.sequences, ())
        self.assertNotIn('message_calculations', first.raw_config)
        self.assertEqual(second.raw_config['message_calculations'], ())
        self.assertNotEqual(first.identity, second.identity)
        self.assertEqual(first.bindings.identity, second.bindings.identity)
        self.assertEqual(report_first, report_second)
        self.assertEqual(report_first.capability_status['legacy_sum'], 'unavailable')
        self.assertNotIn('legacy_sum_current_message', report_first.capability_status)
        self.assertEqual(explain_analysis_plan(first).nodes, ())

    def test_parameter_snapshot_and_identity_are_independent_of_mutable_config(self):
        """参数变更只形成新计划，原快照/声明对象不被外部字典修改。

        参数: 无。返回: None。异常: 冻结、参数精确转换或完整身份未反映变化则失败。
        """
        original = legacy_config()
        altered = changed(original, ('message_calculations', 0, 'parameters', 'period', 'value'), 0.2)
        with self.guard_static():
            first = AnalysisPlan.from_dict(current_fixture(original), base_dir=ROOT)
            second = AnalysisPlan.from_dict(current_fixture(altered), base_dir=ROOT)
        original['message_calculations'][0]['parameters']['period']['value'] = 999
        self.assertEqual(first.message_calculations[0].parameters[0].value, 0.1)
        self.assertEqual(first.raw_config['message_calculations'][0]['parameters']['period']['value'], 0.1)
        self.assertNotEqual(first.identity, second.identity)
        self.assertNotEqual(first.message_calculations[0].expr.bindings.identity,
                            second.message_calculations[0].expr.bindings.identity)
        self.assertEqual(first.sources[0].input_identity, second.sources[0].input_identity)
        self.assertEqual(first.bindings.identity, second.bindings.identity)

    def test_structure_and_native_selector_types_are_strict(self):
        """schema拒缺字段/未知键，解析器额外拒JSON整数表述中的float或bool。

        参数: 无。返回: None。异常: 结构或原生类型被放宽则失败。
        """
        config = legacy_config()
        # 只拒绝仍有业务选择的缺项；唯一来源和固定策略由新默认值专项核对。
        for key in ('name', 'update_message', 'expr', 'unit'):
            missing = deepcopy(config)
            missing['message_calculations'][0].pop(key)
            with self.subTest(missing=key):
                self.assert_invalid(missing, code='missing_field')
        for key in ('frame_id',):
            missing = deepcopy(config)
            missing['message_calculations'][0]['update_message'].pop(key)
            with self.subTest(selector_missing=key):
                self.assert_invalid(missing, code='missing_field')
        cases = [(('operation',), 'integral'), (('profile',), 'chrginfo-main-v1'),
                 (('message_policy',), 'profile'), (('unknown',), True),
                 (('update_message', 'channel'), True), (('update_message', 'channel'), -1),
                 (('update_message', 'frame_id'), True), (('update_message', 'frame_id'), 2048),
                 (('update_message', 'is_extended'), 0), (('update_message', 'is_fd'), 'false'),
                 (('update_message', 'signal'), 'Power.raw'), (('parameters', 'period', 'value'), False),
                 (('parameters', 'period', 'unit'), ''), (('parameters', 'period', 'extra'), 1)]
        for keys, value in cases:
            with self.subTest(keys=keys, value=value):
                code = ('invalid_choice' if keys in (('operation',),('profile',),('message_policy',)) else
                        'unknown_field' if keys in (('unknown',),('update_message','signal'),('parameters','period','extra')) else 'invalid_config')
                self.assert_invalid(changed(config, ('message_calculations', 0, *keys), value), code=code)
        # JSON schema把1.0视作integer；Python公开模型仍须原生int，不能截断。
        for key in ('channel', 'frame_id'):
            with self.subTest(native_integer=key):
                value = 1.0 if key == 'channel' else 256.0
                self.assert_invalid(changed(config, ('message_calculations', 0, 'update_message', key), value), schema_reject=False)

    def test_cross_reference_units_and_current_message_dependencies_are_checked(self):
        """单来源同消息定位、数值单位及B4参数名称/精度均由静态语义核实。

        参数: 无。返回: None。异常: 跨引用误接收或旧保持派生被混入则失败。
        """
        config = legacy_config()
        cases = [(('message_calculations', 0, 'source'), 'missing'),
                 (('message_calculations', 0, 'update_message', 'channel'), 2),
                 (('message_calculations', 0, 'update_message', 'frame_id'), 257),
                 (('message_calculations', 0, 'expr'), 'power + period'),
                 (('message_calculations', 0, 'expr'), 'power > 0'),
                 (('message_calculations', 0, 'unit'), 'W'),
                 (('message_calculations', 0, 'parameters', 'period', 'value'), 2**53 + 1)]
        for keys, value in cases:
            with self.subTest(keys=keys):
                self.assert_invalid(changed(config, keys, value), schema_reject=False)
        # 保护整个原名称空间；不得用参数覆盖原signal或全局derived。
        collision = deepcopy(config)
        collision['message_calculations'][0]['parameters']['power'] = dict(value=1, unit='W')
        self.assert_invalid(collision, schema_reject=False)
        global_derived = deepcopy(config)
        global_derived['derived'] = {'twice': dict(expr='power * 2', unit='W')}
        global_derived['message_calculations'][0]['expr'] = 'twice * period'
        self.assert_invalid(global_derived, schema_reject=False)
        other_message = deepcopy(config)
        other = deepcopy(other_message['signals'][0])
        other['name'] = 'other'
        other['field'].update(frame_id=257, signal='Other.raw')
        other_message['signals'].append(other)
        other_message['message_calculations'][0]['expr'] = '(power + other) * period'
        self.assert_invalid(other_message, schema_reject=False)
        # 另一来源同名字段也不能通过B4单源名称空间变成上次缓存。
        other_source = deepcopy(config)
        source = deepcopy(other_source['sources'][0])
        source['name'] = 'other_bus'
        other_source['sources'].append(source)
        other = deepcopy(other_source['signals'][0])
        other.update(name='other', source='other_bus')
        other_source['signals'].append(other)
        other_source['message_calculations'][0]['expr'] = '(power + other) * period'
        self.assert_invalid(other_source, schema_reject=False)

    def test_calculation_ids_share_existing_rules_windows_and_calculations_namespace(self):
        """新指标不能与原规则/窗口/指标或另一legacy指标复用稳定ID。

        参数: 无。返回: None。异常: 任一重复被接受或缺失具体位置则失败。
        """
        config = legacy_config()
        config['rules'] = [dict(name='active', rule_type='condition_duration', condition='power > 0', minimum_duration='0s')]
        config['windows'] = [dict(name='context', rule='active', anchor='activity', pre='0s', post='0s')]
        config['calculations'] = [dict(name='ordinary', scope='session', operation='integral', expr='power', unit='J')]
        for identifier in ('active', 'context', 'ordinary'):
            with self.subTest(identifier=identifier):
                self.assert_invalid(changed(config, ('message_calculations', 0, 'name'), identifier), schema_reject=False)
        duplicate = deepcopy(config)
        duplicate['message_calculations'].append(deepcopy(duplicate['message_calculations'][0]))
        self.assert_invalid(duplicate, schema_reject=False)

    def test_typed_models_and_reports_reject_stale_or_incompatible_replacements(self):
        """typed替换同样核选择器、原声明与来源关系，不借raw_config掩盖错误。

        参数: 无。返回: None。异常: 非法类型、过期声明或错误能力被当作可运行则失败。
        """
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(legacy_config()), base_dir=ROOT)
            stale_config = changed(legacy_config(), ('signals', 0, 'valid_for'), '2ns')
            stale = AnalysisPlan.from_dict(current_fixture(stale_config), base_dir=ROOT)
        calculation = plan.message_calculations[0]
        for changes in (dict(channel=True), dict(frame_id=256.0), dict(is_extended=0), dict(is_fd=1)):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                replace(calculation.update_message, **changes)
        with self.assertRaises(FrozenInstanceError):
            calculation.source = 'other'
        with self.assertRaises((TypeError, ValueError)):
            replace(calculation, message_policy='profile')
        with self.guard_static():
            ordinary = validate_expression('power', plan.bindings, unit='W')
        with self.assertRaises(TypeError):
            replace(calculation, expr=ordinary)
        # 这些替换仍是合法单项模型，需报告按当前完整计划关系拒绝。
        wrong_selector = replace(calculation, update_message=replace(calculation.update_message, frame_id=257))
        variants = [replace(plan, message_calculations=(wrong_selector,)),
                    replace(plan, message_calculations=stale.message_calculations),
                    replace(plan, sources=(replace(plan.sources[0], source_type='memory'),)),
                    replace(plan, sources=(replace(plan.sources[0], input_identity='stale-input'),)),
                    replace(plan, message_calculations=(calculation, calculation))]
        for index, invalid in enumerate(variants):
            with self.subTest(index=index), self.guard_static():
                report, explanation = validate_analysis_plan(invalid), explain_analysis_plan(invalid)
                self.assertFalse(report.valid)
                self.assertFalse(report.execution_ready)
                self.assertTrue(report.errors)
                if index != 4:
                    self.assertEqual(explanation.nodes[-1].backend, 'unavailable')

    def test_cache_policy_rejection_is_readable_and_does_not_relabel_profile_capability(self):
        """旧cache字段无论是否带新policy都明确unsupported，不静默解释成新模式。

        参数: 无。返回: None。异常: 未保明确原因、机器码或原profile事实则失败。
        """
        for keep_policy in (True, False):
            config = legacy_config()
            config['message_calculations'][0]['cache_policy'] = 'profile'
            if not keep_policy:
                config['message_calculations'][0].pop('message_policy')
            error = self.assert_invalid(config, code='capability_unavailable')
            self.assertTrue(error.path.endswith('.cache_policy'))
            self.assertIn('尚未接线', error.message)
            self.assertIn('current_message-v1', error.message)
        # 其他已支持来源也不能因legacy通用核心存在就冒充公共CAN消息生产者。
        memory = legacy_config()
        memory['sources'] = [dict(name='bus', source_type='memory', rows=[],
            time=dict(time_type='relative', unit='s', origin='synthetic_origin'))]
        memory['signals'] = []
        memory['message_calculations'][0].update(expr='period / period', unit='1')
        self.assert_invalid(memory, schema_reject=False, code='capability_unavailable')

    def test_parameters_only_and_exact_extended_selector_boundaries_are_supported(self):
        """无信号依赖仍显式逐匹配帧求值；参数和四selector边界不能隐式推断。

        参数: 无。返回: None。异常: 合法参数/ID边界误拒或依赖被伪造则失败。
        """
        config = legacy_config()
        config['signals'] = []
        config['message_calculations'][0].update(expr='period / period', unit='1')
        config['message_calculations'][0]['parameters']['factor']['value'] = 2**53 + 2
        for frame_id, extended in ((0, False), (2047, False), (536870911, True)):
            variant = deepcopy(config)
            variant['message_calculations'][0]['update_message'].update(frame_id=frame_id, is_extended=extended)
            self.assertTrue(self.validator.is_valid(current_fixture(variant)))
            with self.guard_static():
                plan = AnalysisPlan.from_dict(current_fixture(variant), base_dir=ROOT)
            calculation = plan.message_calculations[0]
            self.assertEqual(calculation.expr.dependencies, ())
            self.assertFalse(calculation.expr.root.constant)
            self.assertEqual(calculation.update_message.frame_id, frame_id)
            self.assertEqual(calculation.parameters[1], ExpressionParameter('factor', 2**53 + 2, '1'))


if __name__ == '__main__':
    unittest.main()
