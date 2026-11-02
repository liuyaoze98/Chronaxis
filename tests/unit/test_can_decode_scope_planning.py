"""检查CAN可选解码范围的配置、静态能力与旧配置身份，不读取分析来源。

输入为既有独立静态夹具及本文件的有限变体；输出为schema、计划和报告断言。
仅类初始化读取公开schema，后续阻断输入文件和进程操作。requested为默认值，
支持普通和逐消息消费者混合；显式all保留完整解码声明。默认不回填用户配置，
typed选项独立检查。本文件不验证实际decoder调用数，运行证据由CAN专项负责。
"""

from configuration_fixtures import current_fixture

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import fields, replace
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from chronaxis import AnalysisPlan, PlanValidationError, explain_analysis_plan, validate_analysis_plan
from chronaxis.planning.checks import canonical
from chronaxis.planning.legacy_execution import require_can_decode_scope
from chronaxis.sources.can_spec import LegacyCANSpec
from test_can_planning import can_config
from test_plan_message_calculations import legacy_config


ROOT = Path(__file__).absolute().parents[2]


def requested_config():
    """创建不触碰BLF/DBC的纯逐消息配置，显式选择需求解码和无明细。

    参数: 无。返回: 独立JSON字典，沿用原静态合成来源与单位。
    异常: 无主动异常；不伪造来源存在性或运行结果。
    """
    config = legacy_config()
    config['sources'][0]['decode_scope'] = 'requested'
    config['outputs'] = {'contributions': 'none'}
    return config


def static_only():
    """阻断来源I/O和进程入口，允许计划仅按词法处理路径。

    参数: 无。返回: 可恢复ExitStack，调用方须用with关闭。
    异常: 禁止动作触发AssertionError；安装失败先恢复已经安装的探针。
    """
    stack = ExitStack()
    try:
        for name in ('open', 'read_text', 'read_bytes', 'stat', 'resolve', 'mkdir'):
            stack.enter_context(patch.object(Path, name, side_effect=AssertionError('禁止输入Path.' + name)))
        stack.enter_context(patch('builtins.open', side_effect=AssertionError('禁止输入open')))
        stack.enter_context(patch.object(multiprocessing, 'get_context', side_effect=AssertionError('禁止spawn')))
        stack.enter_context(patch.object(multiprocessing, 'Process', side_effect=AssertionError('禁止Process')))
        return stack
    except BaseException:
        stack.close()
        raise


class CANDecodeScopePlanningTests(unittest.TestCase):
    """分别验证结构、完整计划能力与兼容身份，每例不持有外部来源资源。"""

    @classmethod
    def setUpClass(cls):
        """只读取一次公开schema，后续计划检查全部在内存进行。

        参数: 无。返回: None，保存标准验证器。异常: JSON/schema/文件错误直接失败。
        """
        schema = json.loads((ROOT / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def test_omitted_scope_defaults_to_requested_without_rewriting_config(self):
        """省略范围时typed默认为requested，原位置参数与原始配置身份公式仍有效。

        参数: 无。返回: None。异常: 默认被回填、schema与typed默认不符或静态I/O时失败。
        """
        config = can_config()
        config['sources'][0]['reader'].pop('decode_scope')
        untouched = deepcopy(config)
        source_schemas = self.validator.schema['properties']['sources']['items']['oneOf']
        can_schema = next(item for item in source_schemas
            if item['properties']['source_type'].get('const') == 'can_blf')
        self.assertEqual(can_schema['properties']['reader']['properties']['decode_scope']['default'], 'requested')
        self.assertTrue(self.validator.is_valid(current_fixture(config)))
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            spec = plan.sources[0].config
            positional = LegacyCANSpec(spec.name, spec.path, spec.dbc_path, spec.channel,
                spec.timebase, spec.unit, spec.offset_ns, spec.legacy_profile)
            self.assertEqual(positional, spec)
            self.assertEqual(spec.decode_scope, 'requested')
            self.assertEqual(tuple(item.name for item in fields(LegacyCANSpec)[8:10]),
                ('decode_scope', 'input_check'))
            self.assertEqual(tuple(item.name for item in fields(LegacyCANSpec)[10:]),('paths','decode_policy'))
            self.assertTrue(validate_analysis_plan(plan).valid)
        # 身份记录实际配置；默认策略不暗中补入raw。这里独立重建规范化公式。
        old_source = deepcopy(config['sources'][0])
        old_source['reader_options'] = old_source.pop('reader')
        old_source['time']['origin'] = old_source['time'].pop('clock')
        old_source['paths'] = [str(ROOT / old_source.pop('path'))]
        old_source['dbc_by_channel'] = {'1': str(ROOT / old_source['dbc_by_channel']['1'])}
        source_identity = canonical(old_source)
        self.assertEqual(plan.sources[0].input_identity, source_identity)
        self.assertEqual(plan.identity, sha256(canonical({'plan_version': 'config3-static-v1',
            'config': config, 'sources': [source_identity]}).encode('utf-8')).hexdigest())
        self.assertNotIn('decode_scope', plan.raw_config['sources'][0])
        self.assertEqual(config, untouched)
        # 显式all是新的配置声明，保留原字段，不擅自删除用户给出的值。
        explicit = deepcopy(config)
        explicit['sources'][0]['reader']['decode_scope'] = 'all'
        with static_only():
            declared = AnalysisPlan.from_dict(current_fixture(explicit), base_dir=ROOT)
        self.assertIs(type(declared.sources[0].config), LegacyCANSpec)
        self.assertEqual(declared.sources[0].config, replace(spec, decode_scope='all'))
        self.assertEqual(declared.raw_config['sources'][0]['reader']['decode_scope'], 'all')
        explicit_source = deepcopy(old_source)
        explicit_source['decode_scope'] = 'all'
        explicit_identity = canonical(explicit_source)
        self.assertEqual(declared.sources[0].input_identity, explicit_identity)
        self.assertEqual(declared.identity, sha256(canonical({'plan_version': 'config3-static-v1',
            'config': explicit, 'sources': [explicit_identity]}).encode('utf-8')).hexdigest())
        self.assertNotEqual(declared.identity, plan.identity)

    def test_requested_explain_and_all_declarations_need_no_source_io(self):
        """需求解码保留未使用信号和每个指标声明，说明全部帧仍读取。

        参数: 无。返回: None。异常: 静态操作访问来源或丢弃声明时失败。
        """
        config = requested_config()
        unused = deepcopy(config['signals'][0])
        unused.update(name='unused')
        unused['field'].update(frame_id=512)
        config['signals'].append(unused)
        other = deepcopy(config['message_calculations'][0])
        other.update(name='constant', expr='amount', parameters={'amount': {'value': 2, 'unit': 'J'}})
        other['update_message']['frame_id'] = 768
        config['message_calculations'].append(other)
        self.assertTrue(self.validator.is_valid(current_fixture(config)))
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            self.assertIsNone(require_can_decode_scope(plan))
            report = validate_analysis_plan(plan)
            explanation = explain_analysis_plan(plan)
        self.assertTrue(report.valid and report.execution_ready)
        self.assertEqual(plan.outputs.contributions, 'none')
        self.assertEqual(tuple(item.definition.name for item in plan.signals), ('power', 'unused'))
        self.assertEqual(len(plan.message_calculations), 2)
        self.assertEqual(explanation.validation, report)
        text = ' '.join(report.warnings)
        self.assertIn('所有报文仍按原顺序读取', text)
        self.assertIn('time_scope=selected', text)
        self.assertIn('结果实际需要的信号和逐消息选择器', text)
        self.assertTrue(any('unused' in item and '仅保留静态声明检查' in item
            for item in report.warnings))

    def test_pure_parameter_calculation_accepts_empty_signals(self):
        """没有普通信号的纯参数指标仍保留其报文选择，不误拒requested。

        参数: 无。返回: None。异常: 空信号被误判为没有解码需求时失败。
        """
        config = requested_config()
        config['signals'] = []
        config['message_calculations'][0].update(expr='amount', parameters={'amount': {'value': 2, 'unit': 'J'}})
        self.assertTrue(self.validator.is_valid(current_fixture(config)))
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            self.assertIsNone(require_can_decode_scope(plan))
            self.assertTrue(validate_analysis_plan(plan).valid)
        self.assertFalse(plan.signals)
        self.assertEqual(plan.message_calculations[0].update_message.frame_id, 256)

    def test_invalid_scope_and_non_can_fields_are_rejected(self):
        """非法值由schema与parser共同拒绝，其他来源不能携带CAN选项。

        参数: 无。返回: None。异常: 空值、类型混淆或来源种类放宽时失败。
        """
        for value in (None, True, 0, [], {}, '', 'ALL', 'needed'):
            config = requested_config()
            config['sources'][0]['decode_scope'] = value
            with self.subTest(value=value), static_only():
                self.assertFalse(self.validator.is_valid(current_fixture(config)))
                with self.assertRaises(PlanValidationError) as caught:
                    AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
                self.assertEqual(caught.exception.path, '$.sources[0].reader.decode_scope')
        for kind in ('memory', 'signal_csv'):
            config = requested_config()
            config['signals'] = []
            config['message_calculations'] = []
            source = dict(name='bus', source_type=kind, time=config['sources'][0]['time'], decode_scope='requested')
            if kind == 'memory':
                source['rows'] = []
            else:
                source.update(path='unused.csv', time_column='time')
            config['sources'] = [source]
            with self.subTest(kind=kind), static_only():
                self.assertFalse(self.validator.is_valid(current_fixture(config)))
                with self.assertRaises(PlanValidationError):
                    AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
        # 直接构造规格也不允许空值、布尔或非法文本绕过原生类型和值约束。
        with static_only():
            spec = AnalysisPlan.from_dict(current_fixture(legacy_config()), base_dir=ROOT).sources[0].config
        for value in (None, True, 'unknown'):
            with self.subTest(spec=value), self.assertRaises((TypeError, ValueError)):
                replace(spec, decode_scope=value)

    def test_requested_accepts_mixed_consumers_without_changing_execution_choice(self):
        """requested支持混合消费者，历史选择仍由明细、普通输出和来源数决定。

        参数: 无。返回: None。异常: 合法混合声明被范围门禁误拒或静默改成all时失败。
        """
        ordinary = can_config()
        cases = []
        for key in ('rules', 'calculations', 'derived'):
            config = requested_config()
            config[key] = deepcopy(ordinary[key])
            cases.append((key, config, 'summary_direct' if key == 'derived' else 'summary_history'))
        window = requested_config()
        window.update(rules=deepcopy(ordinary['rules']), windows=deepcopy(ordinary['windows']))
        cases.append(('windows', window, 'summary_history'))
        full = requested_config()
        full['outputs']['contributions'] = 'full'
        cases.append(('full', full, 'full_history'))
        raw = requested_config()
        raw['outputs']['can_frames'] = {'source': 'bus', 'format': 'blf', 'scope': 'segments', 'source_time_reference': 'epoch'}
        cases.append(('raw', raw, 'summary_history'))
        multiple = requested_config()
        second = deepcopy(multiple['sources'][0])
        second.update(name='other', decode_scope='all')
        multiple['sources'].append(second)
        cases.append(('multiple', multiple, 'summary_history'))
        ordinary_only = requested_config()
        ordinary_only.pop('message_calculations')
        cases.append(('no_message_metric', ordinary_only, 'not_applicable'))
        for name, config, execution in cases:
            with self.subTest(case=name), static_only():
                self.assertTrue(self.validator.is_valid(current_fixture(config)))
                plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
                self.assertIsNone(require_can_decode_scope(plan))
                report = validate_analysis_plan(plan)
                self.assertEqual(report.execution_ready, name != 'no_message_metric', report.errors)
                self.assertEqual(plan.sources[0].config.decode_scope, 'requested')
                self.assertEqual(plan.outputs.contributions, 'full' if name == 'full' else 'none')
                self.assertEqual(explain_analysis_plan(plan).validation, report)

    def test_typed_requested_accepts_mixed_full_and_raw_plans(self):
        """typed混合计划使用requested不依赖raw_config授予权限，仍保原执行选择。

        参数: 无。返回: None。异常: 规则、窗口、派生或导出导致范围门禁误拒时失败。
        """
        ordinary = can_config()
        for contributions, raw_export in (('none', False), ('full', False), ('none', True)):
            config = legacy_config()
            config['sources'][0]['decode_scope'] = 'all'
            config.update({key: deepcopy(ordinary[key])
                for key in ('derived', 'rules', 'windows', 'calculations')})
            config['outputs'] = {'contributions': contributions}
            if raw_export:
                config['outputs']['can_frames'] = {'source': 'bus', 'format': 'blf', 'scope': 'segments', 'source_time_reference': 'epoch'}
            with self.subTest(contributions=contributions, raw_export=raw_export), static_only():
                original = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
                source = original.sources[0]
                typed = replace(original, sources=(replace(source,
                    config=replace(source.config, decode_scope='requested')),))
                self.assertIsNone(require_can_decode_scope(typed))
                report = validate_analysis_plan(typed)
                self.assertTrue(report.valid and report.execution_ready, report.errors)
                self.assertEqual(explain_analysis_plan(typed).validation, report)
                self.assertEqual(typed.outputs.contributions, contributions)
                self.assertEqual(typed.sources[0].config.decode_scope, 'requested')
                self.assertEqual(typed.raw_config['sources'][0]['reader']['decode_scope'], 'all')


if __name__ == '__main__':
    unittest.main()
