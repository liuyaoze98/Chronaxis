"""用独立Draft 2020-12验证器检查公开schema及公共解析器边界。

输入是已跟踪schema、合成JSON例和单字段变体；输出为结构与语义断言。
标准schema检查字段结构，AnalysisPlan补跨引用、单位、同步、纳秒范围等
语义；两者不能互相替代。特别记录JSON整数允许1.0而Python公开入口只接
原生int的区别。验证不读取输入CSV/DBC，不运行AnalysisRunner或数值分析。
需安装pyproject的test可选依赖；缺包直接失败，不将验收改成skip。
"""

# 使用独立标准验证器，避免自写schema子集解析器成为共同错误来源。
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft202012Validator

# 配置输入复用公开合成例，预期结构/语义分别由固定契约指定。
from chronaxis import AnalysisPlan, PlanValidationError
from test_analysis_plan import ROOT, changed, config_fixture, csv_fixture


class AnalysisSchemaTests(unittest.TestCase):
    """保存标准schema验证器，逐组区分结构拒绝与解析器语义拒绝。

    schema只有本地结构，无需远端ref；测试不因缺验证器自动跳过。
    """

    @classmethod
    def setUpClass(cls):
        """读取公开schema并由独立标准元schema检查其合法性。

        参数: 无，使用Docs/Schema下已跟踪文件。
        返回: None，将验证器保存到当前测试类。
        异常: OSError/JSONDecodeError/SchemaError表示真实验收失败。
        """
        # schema读取属于验收输入，待分析的来源声明始终不打开。
        schema = json.loads((ROOT / 'Docs' / 'Schema' / 'analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def test_valid_configuration_matrix(self):
        """合法内存/CSV、空信号声明、枚举与固定偏移在两个入口都通过。

        参数: 无，显式合成配置矩阵，不使用真实业务参数。
        返回: None，schema和公共解析器一致接受结构合法的计划。
        异常: 任一入口误拒合法配置或读取输入使测试失败。
        """
        # 空声明只表示无数据证明，不允许报告真实覆盖或执行完成。
        empty = config_fixture()
        empty.update(signals=[], derived={}, rules=[], windows=[], calculations=[])
        empty['sources'][0]['rows'] = []
        # 明确枚举标签域，所有布尔条件同步改成域内相等比较。
        enum = config_fixture()
        enum['signals'][2].update(dtype='enum', choices=[[0, 'idle'], [1, 'active']])
        enum['rules'][1]['condition'] = 'alarm == "active"'
        enum['rules'][2]['condition'] = 'alarm == "active"'
        enum['calculations'][3]['condition'] = 'alarm == "active"'
        variants = [config_fixture(), csv_fixture(), empty, enum,
                    changed(config_fixture(), ('sources', 0, 'time', 'offset'), '-.5s'),
                    changed(config_fixture(), ('rules', 1, 'rule_type'), 'falling_edge')]
        for index, config in enumerate(variants):
            with self.subTest(index=index):
                self.assertEqual(list(self.validator.iter_errors(config)), [])
                # 两类open阻断，证明独立schema和解析器都不读取声明输入。
                with patch('builtins.open', side_effect=AssertionError('禁止输入I/O')), \
                     patch.object(Path, 'open', side_effect=AssertionError('禁止Path输入I/O')):
                    AnalysisPlan.from_dict(config, base_dir=ROOT)

    def test_invalid_structure_matrix(self):
        """未知字段、错误类型及公开未支持kind由标准schema拒绝。

        参数: 无，纯JSON结构的单字段错误。
        返回: None，两个入口都拒绝，不匹配验证器的版本相关错误文本。
        异常: 任一入口接受结构错误使测试失败。
        """
        # 数值零TTL属于语义检查，本组只放schema可以准确约束的结构。
        cases = [(('unknown',), 1), (('config_version',), True), (('config_version',), 2),
                 (('semantic_version',), '0.2'), (('dataset', 'name'), 'class'),
                 (('dataset', 'name'), 'abc\n'), (('dataset', 'domain', 'unknown'), 1),
                 (('sources', 0, 'time', 'clock'), ' '), (('sources', 0, 'source_type'), 'can_blf'),
                 (('sources', 0, 'rows', 0, 'values'), []), (('signals', 0, 'valid_for'), '-1s'),
                 (('signals', 0, 'field'), {}), (('signals', 0, 'semantic_id'), ''),
                 (('signals', 0, 'dtype'), 'int32'), (('derived', 'bad.name'), {'expr': 'current', 'unit': 'A'}),
                 (('rules', 1, 'emit_initial'), 1), (('rules', 1, 'rule_type'), 'sequence'),
                 (('windows', 1, 'anchor'), 'invalid'), (('calculations', 0, 'minimum_coverage'), True),
                 (('calculations', 0, 'operation'), 'mean'), (('execution',), {'batch_rows': False}),
                 (('outputs',), {'tables': 'parquet'}), (('presets',), [{'name': 'not_wired'}])]
        for keys, value in cases:
            config = changed(config_fixture(), keys, value)
            with self.subTest(keys=keys, value=value):
                self.assertFalse(self.validator.is_valid(config))
                with self.assertRaises(PlanValidationError):
                    AnalysisPlan.from_dict(config)

    def test_preset_v1_schema_matches_public_parser(self):
        """两个已接线预设结构由标准schema与公共解析器一致检查。

        参数: 无；来自同一合成预设配置的独立副本。
        返回: None。
        异常: schema/解析器接受范围差异或未知字段未拒绝由断言报告。
        """
        # 仅复用合成输入，实际解析/独立标准schema各自检查。
        from test_presets import PresetIntegrationTests
        config = PresetIntegrationTests().config()
        self.assertTrue(self.validator.is_valid(config))
        AnalysisPlan.from_dict(config)
        # 参数、版本、角色与简单别名不能因预设展开而放宽。
        cases = [(('presets', 0, 'parameters', 'unknown'), 1),
                 (('presets', 0, 'parameters', 'compute_energy'), 1),
                 (('presets', 0, 'parameters', 'mode_value'), True),
                 (('presets', 0, 'parameters', 'minimum_coverage'), 2),
                 (('presets', 0, 'version'), '2'),
                 (('presets', 0, 'role_bindings', 'current'), 'battery.current'),
                 (('presets', 1, 'parameters', 'pre'), '-1ns'),
                 (('presets', 1, 'role_bindings', 'voltage'), 'voltage')]
        for keys, value in cases:
            bad = changed(config, keys, value)
            self.assertFalse(self.validator.is_valid(bad))
            with self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(bad)

    def test_csv_paths_offsets_and_mode_specific_fields(self):
        """来源路径二选一和按kind限定的字段具有准确结构约束。

        参数: 无，CSV路径、offset及rule/window/calculation字段错误。
        返回: None，结构错误在两个入口均拒绝。
        异常: schema错误接受类型或kind专属字段使测试失败。
        """
        # offset只允许带单位的数值坐标，绝对日期不是固定时间偏移。
        variants = [changed(csv_fixture(), ('sources', 0, 'path'), 'duplicate.csv'),
                    changed(csv_fixture(), ('sources', 0, 'paths'), []),
                    changed(csv_fixture(), ('sources', 0, 'reader', 'delimiter'), '\n'),
                    changed(config_fixture(), ('sources', 0, 'time', 'offset'), '2026-10-08T20:00:00Z'),
                    changed(config_fixture(), ('rules', 0, 'emit_initial'), False),
                    changed(config_fixture(), ('windows', 1, 'exit_delay'), '1s'),
                    changed(config_fixture(), ('calculations', 1, 'method'), 'zoh')]
        for index, config in enumerate(variants):
            with self.subTest(index=index):
                self.assertFalse(self.validator.is_valid(config))
                with self.assertRaises(PlanValidationError):
                    AnalysisPlan.from_dict(config)

    def test_semantic_checks_remain_in_public_parser(self):
        """结构合法不能证明跨引用、单位、纳秒范围或时区语义正确。

        参数: 无，schema合法而语义错误的JSON配置。
        返回: None，schema通过后公共解析器仍明确拒绝。
        异常: 公共入口依赖schema而省略语义校验使测试失败。
        """
        # 标准JSON Schema把整数值浮点1.0视为integer，API另要求原生int。
        cases = [(('config_version',), 3.0), (('signals', 0, 'valid_for'), '0s'),
                 (('signals', 0, 'source'), 'missing'), (('derived', 'power', 'unit'), 'A'),
                 (('dataset', 'domain', 'end'), '-1s'), (('windows', 1, 'post'), '2s'),
                 (('calculations', 0, 'scope'), {'rule':'missing'}), (('calculations', 0, 'unit'), 'V'),
                 (('dataset', 'domain', 'end'), '9223372036854775808ns')]
        for keys, value in cases:
            config = changed(config_fixture(), keys, value)
            with self.subTest(keys=keys, value=value):
                self.assertTrue(self.validator.is_valid(config))
                with self.assertRaises(PlanValidationError):
                    AnalysisPlan.from_dict(config)
