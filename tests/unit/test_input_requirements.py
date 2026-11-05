"""验证请求结果的输入需求，防止未用声明变成实际数据处理任务。

输入复用已有合成静态配置；每个期望均按表达式、父规则和消息选择器手写。
计划构建与需求收集在禁止输入 I/O/进程的探针内完成，不生成真实日志或运行
数值。测试覆盖普通样本/消息字段分离、派生传递关系、预设、原帧和观测范围，
以及 explain 的历史声明；不把静态通过当作运行预算、读取或解码验收。
"""

from configuration_fixtures import current_fixture

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import unittest
import test_presets as preset_fixture

from chronaxis import AnalysisPlan, PlanValidationError, explain_analysis_plan
from chronaxis.planning.input_requirements import collect_input_requirements
from test_analysis_plan import ROOT, config_fixture
from test_can_decode_scope_planning import static_only
from test_plan_message_calculations import legacy_config
from test_plan_legacy_disjunction import bucket_config


def ordinary_config():
    """保留公开样例的三个声明，清空所有结果根。

    参数: 无。返回: 每次独立配置 dict。
    异常: 原样例读取/JSON 错误直接传播；读取发生在静态计划探针之外。
    """
    config = config_fixture()
    config.update(derived={}, rules=[], windows=[], calculations=[])
    return config


class InputRequirementsTests(unittest.TestCase):
    """用手写依赖真值核对唯一需求函数，不运行或伪造来源证明。"""

    def build(self, config):
        """在禁止来源 I/O 的上下文构建原计划和需求。

        参数: config为独立合成配置。返回: (plan, requirements)。
        异常: 原计划错误或禁止动作原样传播，使本用例失败。
        """
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            requirements = collect_input_requirements(plan)
        return plan, requirements

    def test_nested_derived_and_unused_declarations(self):
        """派生链展开到原信号，但未用 BOOL 派生不增加样本需求。

        参数: 无。返回: None。异常: 依赖、声明顺序或完整计划被裁剪即失败。
        """
        config = ordinary_config()
        config['derived'] = dict(twice=dict(expr='power * 2', unit='W'),
            unused_alarm=dict(expr='not alarm', unit='1'),
            power=dict(expr='voltage * current', unit='W'))
        config['calculations'] = [dict(name='mean', scope='session', operation='sample_mean', expr='twice')]
        plan, requirements = self.build(config)
        self.assertEqual(requirements.ordinary_sample_aliases, ('current', 'voltage'))
        self.assertEqual(requirements.message_aliases, ())
        self.assertEqual(tuple(item.definition.name for item in plan.signals), ('current', 'voltage', 'alarm'))
        with static_only():
            report = explain_analysis_plan(plan)
        self.assertEqual(dict(report.history_ns), {'current': 2_000_000_000, 'voltage': 2_000_000_000})
        self.assertTrue(any('仅保留静态声明检查' in item and 'alarm' in item
            for item in report.validation.warnings))

    def test_unused_derived_is_not_a_result_root(self):
        """只有未引用派生声明时不请求任何值，也不打开无消费者来源。

        参数: 无。返回: None。异常: 不必要依赖或静态检查被跳过即失败。
        """
        config = ordinary_config()
        config['derived'] = dict(unused_power=dict(expr='voltage * current', unit='W'))
        plan, requirements = self.build(config)
        self.assertEqual(requirements.required_aliases, ())
        self.assertEqual(requirements.for_source('table').required_fields, ())
        self.assertEqual(requirements.observation_sources, ())
        self.assertFalse(requirements.for_source('table').active)
        with static_only():
            self.assertEqual(dict(explain_analysis_plan(plan).history_ns), {})
        for expression in ('missing + 1', 'unused_power'):
            invalid = deepcopy(config)
            invalid['derived']['unused_power']['expr'] = expression
            with self.subTest(expression=expression), static_only(), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(invalid), base_dir=ROOT)

    def test_standalone_rule_is_a_result_root(self):
        """没有指标的活动规则仍需要条件信号。

        参数: 无。返回: None。异常: 规则因为没有下游指标而被漏掉即失败。
        """
        config = ordinary_config()
        config['rules'] = [dict(name='active', rule_type='condition_duration', condition='current > 5', minimum_duration='1s')]
        _, requirements = self.build(config)
        self.assertEqual(requirements.ordinary_sample_aliases, ('current',))
        self.assertEqual(requirements.for_source('table').required_fields, ('raw.current',))

    def test_standalone_window_keeps_parent_and_pre_history(self):
        """独立窗口保父规则与前置历史，不额外读取未用声明。

        参数: 无。返回: None。异常: 父条件遗漏或窗口历史长度错误即失败。
        """
        config = ordinary_config()
        config['rules'] = [dict(name='edge', rule_type='rising_edge', condition='alarm', emit_initial=False)]
        config['windows'] = [dict(name='context', rule='edge', anchor='point', pre='3s', post='2s')]
        plan, requirements = self.build(config)
        self.assertEqual(requirements.ordinary_sample_aliases, ('alarm',))
        with static_only():
            self.assertEqual(dict(explain_analysis_plan(plan).history_ns), {'alarm': 3_000_000_000})

    def test_select_includes_signal_condition_and_window_parent(self):
        """选择明细同时需要所选值、筛选条件和决定范围的规则。

        参数: 无。返回: None。异常: 三条独立输入任一丢失即失败。
        """
        config = ordinary_config()
        config['rules'] = [dict(name='edge', rule_type='rising_edge', condition='alarm', emit_initial=False)]
        config['windows'] = [dict(name='context', rule='edge', anchor='point', pre='3s', post='2s')]
        config['calculations'] = [dict(name='chosen', scope='segment:context', operation='select',
            expr='current', condition='voltage > 10')]
        plan, requirements = self.build(config)
        self.assertEqual(requirements.ordinary_sample_aliases, ('current', 'voltage', 'alarm'))
        self.assertEqual(requirements.message_aliases, ())
        with static_only():
            self.assertEqual(dict(explain_analysis_plan(plan).history_ns),
                {'current': 3_000_000_000, 'voltage': 3_000_000_000, 'alarm': 3_000_000_000})

    def test_parameter_only_calculation_keeps_selector_without_samples(self):
        """纯参数没有原信号依赖，仍需每条选择器报文驱动一次计算。

        参数: 无。返回: None。异常: 参数误变信号或选择器被剪掉即失败。
        """
        config = legacy_config()
        config['signals'] = []
        config['message_calculations'][0].update(expr='period / period', unit='1')
        second = deepcopy(config['message_calculations'][0])
        second['name'] = 'second'
        second['update_message']['frame_id'] = 128
        config['message_calculations'].append(second)
        plan, requirements = self.build(config)
        source = requirements.for_source('bus')
        self.assertEqual((requirements.ordinary_sample_aliases, requirements.message_aliases), ((), ()))
        self.assertEqual((source.required_fields, source.decode_frame_ids, source.selector_ids),
            ((), (256, 128), (256, 128)))
        with static_only():
            self.assertEqual(dict(explain_analysis_plan(plan).history_ns), {})

    def test_direction_is_separate_and_unused_frame_is_omitted(self):
        """公式外的方向字段仍需读取，同源未用报文不因声明而加入。

        参数: 无。返回: None。异常: 方向遗漏、ID 过多或普通样本被误生成即失败。
        """
        config = bucket_config()
        unused = deepcopy(config['signals'][0])
        unused.update(name='unused')
        unused['field'].update(frame_id=512)
        config['signals'].insert(0, unused)
        plan, requirements = self.build(config)
        source = requirements.for_source('bus')
        self.assertEqual(plan.message_calculations[0].expr.dependencies, ('power',))
        self.assertEqual(requirements.message_aliases, ('power', 'direction'))
        self.assertEqual(requirements.ordinary_sample_aliases, ())
        self.assertEqual(source.required_aliases, ('power', 'direction'))
        self.assertEqual(source.required_fields, tuple(item.definition.field for item in plan.signals[1:]))
        self.assertEqual((source.decode_frame_ids, source.selector_ids), ((256,), (256,)))

    def test_preset_without_energy_does_not_request_voltage(self):
        """明确提供电压角色但不计算能量时，电压只保留声明检查。

        参数: 无。返回: None。异常: 全部预设角色被误当数据需求即失败。
        """
        config = preset_fixture.PresetIntegrationTests().config()
        config['presets'] = config['presets'][:1]
        config['presets'][0]['parameters'].update(compute_energy=False, compute_charge=True)
        plan, requirements = self.build(config)
        self.assertEqual(tuple(item.definition.name for item in plan.signals),
            ('mode', 'current', 'voltage', 'alarm'))
        self.assertEqual(requirements.ordinary_sample_aliases, ('mode', 'current'))
        self.assertEqual(requirements.message_aliases, ())
        self.assertEqual(requirements.for_source('sensor').required_fields, ('raw_mode', 'raw_current'))

    def test_two_alias_energy_shape_needs_only_message_fields(self):
        """用合成的电压乘电流配置核真实能量计划形状，不读取私人数据。

        参数: 无。返回: None。异常: 两个字段、方向或选择器关系不符即失败。
        """
        config = legacy_config()
        voltage = deepcopy(config['signals'][0])
        voltage.update(name='voltage', unit='V', conversion={'input_unit':'V'})
        voltage['field'].update(frame_id=428, signal='Voltage')
        current = deepcopy(voltage)
        current.update(name='current', unit='A', conversion={'input_unit':'A'})
        current['field']['signal'] = 'Current'
        config['signals'] = [voltage, current]
        calculation = config['message_calculations'][0]
        calculation.update(expr='voltage * current * period',
            split_by_sign=dict(signal='current', bucket='positive', value_policy='raw_decoded-v1'))
        calculation['update_message']['frame_id'] = 428
        plan, requirements = self.build(config)
        self.assertEqual(requirements.ordinary_sample_aliases, ())
        self.assertEqual(requirements.message_aliases, ('voltage', 'current'))
        self.assertEqual(requirements.for_source('bus').decode_frame_ids, (428,))
        with static_only():
            report = explain_analysis_plan(plan)
        self.assertEqual(dict(report.history_ns), {})
        self.assertTrue(any('不生成普通样本或TTL历史' in item for item in report.validation.warnings))

    def test_observation_raw_and_immutable_source_order(self):
        """无值依赖来源仍保观测，原帧导出单列，有限需求不能被改写。

        参数: 无。返回: None。异常: 来源顺序、原帧需求或冻结边界不符即失败。
        """
        config = legacy_config()
        other = deepcopy(config['sources'][0])
        other['name'] = 'observation_only'
        config['sources'].insert(0, other)
        config['outputs'] = dict(can_frames=dict(source='observation_only', format='blf', source_time_reference='epoch'))
        _, requirements = self.build(config)
        self.assertEqual(requirements.observation_sources, ('observation_only',))
        self.assertEqual(requirements.for_source('bus').time_scope, 'selected')
        self.assertEqual(tuple(item.source for item in requirements.sources), ('observation_only', 'bus'))
        self.assertEqual(requirements.raw_sources, ('observation_only',))
        self.assertEqual(requirements.for_source('observation_only').required_aliases, ())
        with self.assertRaises(FrozenInstanceError):
            requirements.message_aliases = ()
        with self.assertRaises(FrozenInstanceError):
            requirements.for_source('bus').required_fields = ()
        with self.assertRaises(ValueError):
            requirements.for_source('missing')
        with self.assertRaises(TypeError):
            requirements.for_source(1)

    def test_function_names_and_unknown_dependency(self):
        """函数名不成为原信号依赖，未知 typed 依赖不能被剪成空集合。

        参数: 无。返回: None。异常: 错误闭包或非法替换被接受即失败。
        """
        config = ordinary_config()
        config['derived'] = dict(unused_voltage=dict(expr='voltage', unit='V'),
            magnitude=dict(expr='abs(current)', unit='A'))
        config['calculations'] = [dict(name='mean', scope='session', operation='sample_mean', expr='magnitude')]
        plan, requirements = self.build(config)
        self.assertEqual(requirements.ordinary_sample_aliases, ('current',))
        invalid_static = replace(plan.calculations[0].signal, dependencies=('missing',))
        invalid_plan = replace(plan, calculations=(replace(plan.calculations[0], signal=invalid_static),))
        with self.assertRaises(ValueError):
            collect_input_requirements(invalid_plan)
        with self.assertRaises(TypeError):
            collect_input_requirements({})


if __name__ == '__main__':
    unittest.main()
