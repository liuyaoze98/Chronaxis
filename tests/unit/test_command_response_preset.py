"""验证command_response预设只展开公共节点，角色映射与显式计划结果等价。

所有信号为合成布尔值；检查参数、单位/类型、角色歧义、ID冲突及来源追溯。
实际AnalysisRunner使用work下独立目录，不访问RefProjects或真实业务日志。
"""

from configuration_fixtures import current_fixture

import copy
import json
import unittest
from pathlib import Path
from typing import get_type_hints
from uuid import uuid4
from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError, PresetSpec, build_preset
from chronaxis.planning.preset_models import PlanFragment
from chronaxis.planning.sequences import SequencePlan
from test_sequence_runner import config_fixture, ROOT


def preset_config():
    """用两个显式角色替换普通规则，仍使用同一组合成输入。

    参数: 无。返回: 独立配置dict。异常: 无主动异常。
    """
    config = config_fixture()
    config['rules'], config['sequences'] = [], []
    config['presets'] = [dict(name='command', preset_type='command_response', version='1',
        role_bindings=dict(request='request', response='response'),
        parameters=dict(min_delay='0ns', max_delay='2ns'))]
    return config


class CommandResponsePresetTests(unittest.TestCase):
    """预设与显式展开使用相同公开AnalysisRunner，每次完整关闭结果。"""

    def run_plan(self, plan):
        """获取实际输出与清单的角色追溯，关闭后核预算归零。

        参数: plan为公开AnalysisPlan。返回: 配对结果tuple与角色元数据tuple。
        异常: 原运行、模型、清理或预算断言错误。
        """
        work = ROOT / 'work/m3-sequence-public-home-20261022/presets' / uuid4().hex
        result = AnalysisRunner().run(plan, work_dir=work)
        try:
            rows = tuple(row for row in result.iter_sequences())
            bindings = plan.presets
            events = {row.event_id:row for row in result.iter_events()}
            budget = result.spool.budget
        finally:
            result.close()
        self.assertEqual(budget.ram_bytes, 0)
        return rows, events, bindings

    def test_schema_typed_fragment_and_explicit_equivalence_two_mappings(self):
        """两套字段/别名映射、两后端均与预设公开展开相同。

        参数: 无。返回: None。异常: schema、绑定追溯或业务输出差异使测试失败。
        """
        schema = json.loads((ROOT / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        validator = Draft202012Validator(schema)
        self.assertEqual(get_type_hints(PlanFragment)['sequences'], tuple[SequencePlan, ...])
        semantic = None
        for renamed in (False, True):
            config = preset_config()
            if renamed:
                for signal, alias in zip(config['signals'], ('command_bit', 'reply_bit')):
                    signal['name'] = alias
                config['presets'][0]['role_bindings'] = dict(request='command_bit', response='reply_bit')
            validator.validate(current_fixture(config))
            for backend in ('reference', 'numpy'):
                config['execution']['backend'] = backend
                plan = AnalysisPlan.from_dict(current_fixture(config))
                fragment = build_preset(plan.presets[0], tuple(item.definition for item in plan.signals))
                explicit = copy.deepcopy(config)
                explicit.pop('presets')
                explicit.update(fragment.to_dict())
                direct = AnalysisPlan.from_dict(current_fixture(explicit))
                rows, events, metadata = self.run_plan(plan)
                direct_rows, _, _ = self.run_plan(direct)
                self.assertEqual(rows, direct_rows)
                self.assertEqual(metadata[0].preset_type, 'command_response')
                summary = tuple((events[row.request_id].confirmed_ns, row.status, row.delay_ns) for row in rows)
                if semantic is None:
                    semantic = summary
                self.assertEqual(summary, semantic)
                self.assertEqual(tuple(item.definition.name for item in plan.preset_bindings[0]),
                                 ('command_bit', 'reply_bit') if renamed else ('request', 'response'))

    def test_roles_parameters_conflicts_and_semantic_resolution(self):
        """未知参数、非法延迟、错误角色契约及冲突均在读取输入前拒绝。

        参数: 无。返回: None。异常: 错误声明误通过使测试失败。
        """
        for change in ({'min_delay': '3ns'}, {'max_pending': 0}, {'emit_initial': 'true'}, {'guessed': 1}):
            config = preset_config()
            config['presets'][0]['parameters'].update(change)
            with self.subTest(change=change), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(config))
        for field, value in (('dtype', 'float64'), ('unit', 'V'), ('valid_for', '0ns')):
            config = preset_config()
            config['signals'][0][field] = value
            with self.subTest(field=field), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(config))
        config = preset_config()
        config['rules'] = [dict(name='command_pair', rule_type='rising_edge', condition='request')]
        with self.assertRaisesRegex(PlanValidationError, '冲突'):
            AnalysisPlan.from_dict(current_fixture(config))
        config = preset_config()
        config['presets'][0]['role_bindings'] = {}
        for signal in config['signals']:
            signal.update(semantic_id='command.' + signal['name'], semantic_contract_version='1')
        plan = AnalysisPlan.from_dict(current_fixture(config))
        self.assertTrue(all(item.resolution == 'semantic_unique' for item in plan.preset_bindings[0]))
        duplicate = copy.deepcopy(config['signals'][0])
        duplicate['name'] = 'second_request'
        config['signals'].append(duplicate)
        with self.assertRaisesRegex(PlanValidationError, '歧义'):
            AnalysisPlan.from_dict(current_fixture(config))


if __name__ == '__main__':
    unittest.main()
