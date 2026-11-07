"""以合成声明验收两个v1预设角色、参数、歧义和公开片段展开。

输入仅类型化SignalDefinition/JSON参数，输出用手算节点和明确拒绝条件检查。
普通分析仍无需语义目录；显式选择不绕过转换后单位/方向/位置/质量。
使用unittest及不可变副本，不读取历史日志、不执行旧链或写入RefProjects。
后续纵向测试在同文件组合现有独立参考/NumPy算子，不把构建器当AnalysisRunner。
"""

from configuration_fixtures import current_fixture

# 只读副本用于单字段故障，不修改全局夹具。
from dataclasses import replace
from copy import deepcopy
from typing import get_type_hints
import unittest
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType as D
from chronaxis.presets import PresetSpec, PlanFragment, build_preset, resolve_preset_roles
from chronaxis.planning import PlanValidationError
from chronaxis import AnalysisPlan, validate_analysis_plan
from examples.presets_demo import run_example


def definitions():
    """建立无semantic_id也能显式满足充电/报警v1的合成信号。

    参数: 无；所有单位/方向/测量位置/10秒有效期显式给出。
    返回: 四个SignalDefinition tuple，模式为明确整数编码、报警为合成BOOL。
    异常: 模型声明错误直接传播。
    """
    # 字段与表达式别名分开；不从字段文本推断角色含义。
    return (SignalDefinition('mode', 'sensor', 'raw_mode', D.INT64, '1', 10_000_000_000),
            SignalDefinition('current', 'sensor', 'raw_current', D.FLOAT64, 'A', 10_000_000_000,
                             sign_convention='positive_is_charge', measurement_location='pack_terminal'),
            SignalDefinition('voltage', 'sensor', 'raw_voltage', D.FLOAT64, 'V', 10_000_000_000,
                             measurement_location='pack_terminal'),
            SignalDefinition('alarm', 'sensor', 'raw_alarm', D.BOOL, '1', 10_000_000_000))


def charge_spec(**parameters):
    """建立明确绑定的合成充电配置，调用方可覆盖请求指标及政策。

    参数: parameters为同测试希望修改的工程参数。
    返回: PresetSpec；1编码/5A/1s只用于本合成验收。
    异常: 非JSON参数或spec结构错误直接传播。
    """
    params = {'mode_value': 1, 'current_min': 5, 'minimum_duration': '1s', **parameters}
    return PresetSpec('charging', 'charge_session', '1', {'mode': 'mode', 'current': 'current', 'voltage': 'voltage'}, params)


class PresetContractTests(unittest.TestCase):
    """用独立声明副本验收T40/T41和参数/生成ID边界，无跨测试状态。"""

    def test_explicit_without_semantics_and_optional_outputs(self):
        """显式完整绑定无需semantic_id，没有请求的指标不生成。

        参数: 无；合成模式/电流和可选电压。
        返回: None。
        异常: 生成节点或角色检查差异由断言报告。
        """
        fragment = build_preset(charge_spec(), definitions())
        self.assertIsInstance(fragment, PlanFragment)
        self.assertEqual((fragment.derived, fragment.calculations, fragment.windows), ((), (), ()))
        self.assertEqual(fragment.rules[0].condition, 'mode == 1 and current > 5')
        self.assertEqual((fragment.rules[0].minimum_duration_ns, fragment.rules[0].selection_origin), (1_000_000_000, 'onset'))
        self.assertEqual(fragment.to_dict()['rules'][0]['duration_comparison'], '>=')
        # 请求Wh/Ah才生成相应功率与积分，部分政策缺省保留继承。
        fragment = build_preset(charge_spec(compute_energy=True, compute_charge=True, minimum_coverage=.95), definitions())
        self.assertEqual(fragment.derived[0].expr, 'voltage * current')
        self.assertEqual(tuple(item.unit for item in fragment.calculations), ('Wh', 'Ah'))
        self.assertEqual(tuple(item.partial_policy for item in fragment.calculations), (None, None))
        self.assertNotIn('partial_policy', fragment.to_dict()['calculations'][0])

    def test_missing_ambiguous_and_explicit_priority(self):
        """T40缺项/歧义拒绝，显式合格选择优先于自动候选。

        参数: 无；当前局部信号列表，不模拟全局注册表。
        返回: None。
        异常: 错误接受、候选诊断缺失由断言报告。
        """
        mode, current, voltage, alarm = definitions()
        spec = PresetSpec('charging', 'charge_session', '1', {'mode': 'mode'}, {'mode_value': 1, 'current_min': 5, 'minimum_duration': '1s'})
        with self.assertRaisesRegex(PlanValidationError, 'current.*缺少'):
            build_preset(spec, definitions())
        first = replace(current, semantic_id='battery.current', semantic_contract_version='1')
        second = replace(first, name='other')
        with self.assertRaisesRegex(PlanValidationError, '歧义.*current.*other'):
            build_preset(spec, (mode, first, second))
        explicit = replace(spec, role_bindings={'mode': 'mode', 'current': 'other'})
        roles = resolve_preset_roles(explicit, (mode, first, second))
        self.assertEqual(roles[1].definition.name, 'other')
        self.assertEqual(roles[1].resolution, 'explicit')
        self.assertEqual(resolve_preset_roles(spec, (mode, first))[1].resolution, 'semantic_unique')
        # 字符串大小写及版本不是模糊匹配；不取不满足候选当唯一。
        for candidate in (replace(first, semantic_id='Battery.current'), replace(first, semantic_contract_version='2')):
            with self.assertRaisesRegex(PlanValidationError, '缺少'):
                build_preset(spec, (mode, candidate))

    def test_explicit_cannot_bypass_contract(self):
        """T41显式别名仍拒绝错误dtype/方向/位置/单位关系或基础质量。

        参数: 无；每次仅破坏一个合法角色字段。
        返回: None。
        异常: 不合格契约被接受时断言失败。
        """
        mode, current, voltage, alarm = definitions()
        for bad in (replace(current, sign_convention=None), replace(current, sign_convention='positive_is_discharge'),
                    replace(current, measurement_location='branch'), replace(current, dtype=D.INT64),
                    replace(current, unit='mA', input_unit='mA')):
            with self.assertRaises(PlanValidationError):
                build_preset(charge_spec(), (mode, bad, voltage, alarm))
        # 已知输入模型不允许自由质量策略；预设检查实际identity中的固定禁止掩码。
        class BadQuality(SignalDefinition):
            """仅用于故障夹具：伪造质量身份，其他字段保持合法。"""
            def identity(self):
                """返回故意放宽的身份供契约拒绝测试。

                参数: 无。
                返回: 原tuple末项被改为0。
                异常: 无主动异常。
                """
                return super().identity()[:-1] + (0,)
        bad = BadQuality(**{key: value for key, value in current.__dict__.items() if key != 'unit_status'})
        with self.assertRaisesRegex(PlanValidationError, '质量'):
            build_preset(charge_spec(), (mode, bad, voltage))

    def test_voltage_only_required_for_energy(self):
        """只算活动/电量不强制电压，能量请求才必须完整电压契约。

        参数: 无；局部只保留mode/current。
        返回: None。
        异常: 依赖范围或缺项不符合时断言失败。
        """
        spec = replace(charge_spec(compute_charge=True), role_bindings={'mode': 'mode', 'current': 'current'})
        fragment = build_preset(spec, definitions()[:2])
        self.assertEqual(tuple(item.unit for item in fragment.calculations), ('Ah',))
        with self.assertRaisesRegex(PlanValidationError, 'voltage'):
            build_preset(replace(spec, parameters={**dict(spec.parameters), 'compute_energy': True}), definitions()[:2])

    def test_fault_has_only_alarm_contract_and_point_window(self):
        """报警只需BOOL/1角色和显式pre/post，不要求电池元数据。

        参数: 无；合成TRUE的含义为演示报警谓词成立，不代表真实故障。
        返回: None。
        异常: 参数、节点或无关契约检查差异由断言报告。
        """
        spec = PresetSpec('fault', 'fault_context', '1', {'alarm': 'alarm'}, {'pre': '1s', 'post': '2s', 'emit_initial': True})
        fragment = build_preset(spec, (definitions()[-1],))
        self.assertEqual((fragment.rules[0].rule_type, fragment.rules[0].condition, fragment.rules[0].emit_initial), ('rising_edge', 'alarm', True))
        window = fragment.windows[0]
        self.assertEqual((window.anchor, window.merge, window.pre_ns, window.post_ns), ('point', 'none', 1_000_000_000, 2_000_000_000))
        self.assertEqual((fragment.derived, fragment.calculations), ((), ()))

    def test_parameter_errors_are_rejected(self):
        """未知参数/角色/版本、伪bool数值、负时间/覆盖与模式编码错误明确拒绝。

        参数: 无；独立参数变体。
        返回: None。
        异常: 错误配置被接受时断言失败。
        """
        for params in ({'current_min': True}, {'duration': '-1ns'}, {'minimum_coverage': 2},
                       {'compute_energy': 1}, {'unknown': 1}, {'mode_value': 2**64}, {'partial_policy': 'ignore'}):
            with self.assertRaises(PlanValidationError):
                build_preset(charge_spec(**params), definitions())
        for spec in (replace(charge_spec(), role_bindings={'unknown': 'current'}),
                     replace(charge_spec(), role_bindings={'mode': 'missing', 'current': 'current'})):
            with self.assertRaises(PlanValidationError):
                build_preset(spec, definitions())
        with self.assertRaises(PlanValidationError):
            PresetSpec('charging', 'charge_session', '2', {}, {})
        with self.assertRaises(PlanValidationError):
            PresetSpec('charging', 'charge_session', '1', {'current': 'battery.current'}, {})
        for params in ({'pre': '0s', 'post': '0s'}, {'pre': '-1ns', 'post': '1s'}, {'pre': '1s', 'post': '1s', 'emit_initial': 1}):
            with self.assertRaises(PlanValidationError):
                build_preset(PresetSpec('fault', 'fault_context', '1', {'alarm': 'alarm'}, params), definitions())

    def test_generated_ids_and_duplicate_signals(self):
        """生成ID与信号冲突或信号别名重复均拒绝，不隐藏加后缀。

        参数: 无；仅改原定义别名。
        返回: None。
        异常: 冲突被接受时断言失败。
        """
        signals = definitions()
        with self.assertRaisesRegex(PlanValidationError, '生成ID冲突'):
            build_preset(charge_spec(compute_energy=True), signals + (replace(signals[1], name='charging_power'),))
        with self.assertRaisesRegex(PlanValidationError, '重复'):
            build_preset(charge_spec(), signals + (signals[1],))

    def test_spec_and_serialization_are_independent(self):
        """构造后原JSON修改无效，片段序列化每次返回独立声明副本。

        参数: 无；原可变spec配置。
        返回: None。
        异常: 输入或序列化状态泄漏由断言报告。
        """
        raw = {'name': 'fault', 'preset_type': 'fault_context', 'version': '1', 'role_bindings': {'alarm': 'alarm'}, 'parameters': {'pre': '1s', 'post': '2s'}}
        spec = PresetSpec.from_dict(raw)
        raw['parameters']['pre'] = '0s'
        raw['role_bindings']['alarm'] = 'missing'
        fragment = build_preset(spec, definitions())
        one = fragment.to_dict()
        one['rules'][0]['condition'] = 'False'
        self.assertEqual(fragment.to_dict()['rules'][0]['condition'], 'alarm')
        self.assertEqual(fragment.windows[0].pre_ns, 1_000_000_000)


class PresetIntegrationTests(unittest.TestCase):
    """从公共JSON展开及直接双后端组合验收T41/T42/T58，来源隔离。"""

    def config(self):
        """建立完全合成的公共schema1输入，显式绑定四角色。

        参数: 无。
        返回: 新dict，模式编码1与报警TRUE只用于演示谓词。
        异常: 无主动异常。
        """
        rows = [{'time': '0s', 'values': {'raw_mode': 1, 'raw_current': 10., 'raw_voltage': 400., 'raw_alarm': False}},
                {'time': '2s', 'values': {'raw_current': 0., 'raw_alarm': True}},
                {'time': '4s', 'values': {'raw_current': 0., 'raw_alarm': False}}]
        signals = [{'name': item.name, 'source': item.source, 'field': item.field, 'dtype': item.dtype.value,
                    'unit': item.unit, 'valid_for': '10s'} for item in definitions()]
        signals[1].update(sign_convention='positive_is_charge', measurement_location='pack_terminal')
        signals[2]['measurement_location'] = 'pack_terminal'
        return current_fixture({'config_version': 4,
                'dataset': {'name': 'demo', 'entity': 'synthetic', 'session': 'session', 'domain': {'start': '0s', 'end': '4s'}},
                'sources': [{'name': 'sensor', 'source_type': 'memory', 'time': {'time_type': 'relative', 'unit': 's', 'origin': 'synthetic'}, 'rows': rows}],
                'signals': signals, 'execution': {'partial_policy': 'strict'},
                'presets': [{'name': 'charging', 'preset_type': 'charge_session', 'version': '1',
                             'role_bindings': {'mode': 'mode', 'current': 'current', 'voltage': 'voltage'},
                             'parameters': {'mode_value': 1, 'current_min': 5, 'minimum_duration': '1s', 'compute_energy': True, 'compute_charge': True}},
                            {'name': 'fault', 'preset_type': 'fault_context', 'version': '1', 'role_bindings': {'alarm': 'alarm'},
                             'parameters': {'pre': '1s', 'post': '2s'}}]})

    def test_json_matches_direct_public_combination(self):
        """预设展开与直接四类公共节点的编译相同，部分政策正常继承execution。

        参数: 无；同一当前配置副本。
        返回: None。
        异常: 展开/编译/身份或继承错误由断言报告。
        """
        config = self.config()
        plan = AnalysisPlan.from_dict(current_fixture(config))
        # 公开字段必须解析为实际模型类型，不能以未定义的前向文本假报类型接口完成。
        self.assertEqual(get_type_hints(AnalysisPlan)['presets'], tuple[PresetSpec, ...])
        manual = deepcopy(config)
        specs = manual.pop('presets')
        for raw in specs:
            fragment = build_preset(PresetSpec.from_dict(raw), definitions()).to_dict()
            manual.setdefault('derived', {}).update(fragment['derived'])
            for key in ('rules', 'windows', 'calculations'):
                manual.setdefault(key, []).extend(fragment[key])
        direct = AnalysisPlan.from_dict(current_fixture(manual))
        self.assertEqual((plan.derived, plan.rules, plan.windows, plan.calculations),
                         (direct.derived, direct.rules, direct.windows, direct.calculations))
        self.assertEqual(tuple(item.partial_policy for item in plan.calculations), ('strict', 'strict'))
        self.assertEqual(len(plan.presets), 2)
        self.assertEqual(plan.preset_bindings[0][1].definition.field, 'raw_current')
        self.assertEqual(plan.raw_config, AnalysisPlan.from_dict(current_fixture(config)).raw_config)
        self.assertNotIn('derived', plan.raw_config)
        self.assertEqual(validate_analysis_plan(plan).capability_status['preset_expansion'], 'implemented')
        # 公共AnalysisRunner已接通预设展开后的四阶段；静态ready仍不表示实际来源或工程含义已验。
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        config['presets'][0]['parameters']['current_min'] = 99
        self.assertEqual(plan.presets[0].parameters['current_min'], 5)

    def test_user_other_preset_and_duplicate_id_collisions(self):
        """生成ID与用户派生/规则/窗口/指标或其他预设冲突拒绝，用户配置不变。

        参数: 无；每次一个独立冲突配置。
        返回: None。
        异常: 自动覆盖/加后缀或输入变化由断言报告。
        """
        variants = [
            {'derived': {'charging_power': {'expr': 'voltage * current', 'unit': 'W'}}},
            {'rules': [{'name': 'charging_activity', 'rule_type': 'rising_edge', 'condition': 'alarm'}]},
            {'windows': [{'name': 'fault_context'}]}, {'calculations': [{'name': 'charging_energy'}]}]
        for addition in variants:
            config = self.config()
            config.update(addition)
            before = deepcopy(config)
            with self.assertRaisesRegex(PlanValidationError, '生成ID冲突'):
                AnalysisPlan.from_dict(current_fixture(config))
            self.assertEqual(config, before)
        config = self.config()
        config['presets'].append(deepcopy(config['presets'][0]))
        with self.assertRaisesRegex(PlanValidationError, 'preset id重复'):
            AnalysisPlan.from_dict(current_fixture(config))

    def test_two_mappings_backend_results_and_provenance(self):
        """T41/T42同物理含义的V/A与mV/反向mA映射双后端等价，原来源身份不同。

        参数: 无；合成绑定及batch1/3。
        返回: None。
        异常: 手算值、范围、单位、来源或跨任务泄漏由断言报告。
        """
        native = run_example(False, 'reference', 1)
        converted = run_example(True, 'reference', 3)
        for mapped, reference in ((False, native), (True, converted)):
            self.assertEqual(reference[2:], run_example(mapped, 'numpy', 2)[2:])
            self.assertEqual(tuple((event.start_ns, event.end_ns) for event in reference[2]),
                             ((0, 2_000_000_000), (3_000_000_000, 5_000_000_000)))
            for row, expected in zip(reference[3], (8000/3600, 20/3600, 16000/3600, 40/3600)):
                self.assertAlmostEqual(row.value, expected, delta=1e-12)
                self.assertEqual(row.coverage_status, 'sufficient')
            self.assertEqual(tuple(event.start_ns for event in reference[4]), (1_000_000_000, 4_000_000_000, 6_000_000_000))
            self.assertEqual(reference[5][-1].requested_coverage, 1/3)
        self.assertNotEqual(native[0].identity, converted[0].identity)
        self.assertNotEqual(native[3][0].binding_identity, converted[3][0].binding_identity)
        self.assertEqual(native[3][0].source_refs[0].source_name, 'sensor')
        self.assertEqual(converted[3][0].source_refs[0].source_name, 'mapped_sensor')
        self.assertEqual(tuple((row.value, row.unit) for row in native[3]), tuple((row.value, row.unit) for row in converted[3]))
        # 再执行native仍返回native来源；构建器不缓存上一映射的引用。
        self.assertEqual(native[2:], run_example(False, 'reference', 2)[2:])


# 直接运行同一契约/纵向集，无文件副作用。
if __name__ == '__main__':
    unittest.main()
