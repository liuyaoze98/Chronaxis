"""独立验证Sclicer静态导入、完整拒绝与原配置追溯，不运行旧链或分析流。

输入包含两份已复制的原single夹具及明确标注的合成start_only/错误变体；
输出核真实AnalysisPlan、逐字段报告和不变原bytes。路径测试只读写临时配置，
来源/DBC均不存在且静态操作被禁止；这些断言不代表CAN运行或旧状态机等价。
"""

import ast
import copy
import hashlib
import json
import multiprocessing
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from chronaxis.migration import import_legacy_ini, load_legacy_ini

ROOT = Path(__file__).absolute().parents[2]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'legacy' / 'sclicer'


def mapping_fixture(section='TRIGGER_test'):
    """生成完整显式静态CSV计划；参数: 原段名；返回: 新dict；异常: 无。

    目的: 来源路径专门不存在，字段单位/TTL均显式，避免测试隐式工程默认。
    """
    return _current_mapping({'mapping_version': 1, 'path_base': 'mapping_directory', 'io_policy': 'explicit_mapping',
        'analysis': {'config_version': 3,
            'dataset': {'name': 'migration', 'entity': 'synthetic', 'session': 'trial',
                        'domain': {'start': '0s', 'end': '30s'}},
            'sources': [{'name': 'table', 'source_type': 'signal_csv', 'path': 'missing/input.csv',
                         'time_column': 't', 'time': {'time_type': 'relative', 'unit': 's', 'clock': 'common'}}],
            'signals': [{'name': name, 'source': 'table', 'field': field, 'dtype': 'float64',
                         'unit': '1', 'valid_for': '2s'} for name, field in (
                             ('soc', 'BMS_BatPackHiResSOC'), ('mode_value', 'OBC_OpMod'))]},
        'aliases': {'BMS_BatPackHiResSOC': 'soc', 'OBC_OpMod': 'mode_value'},
        'sections': {section: {'name': 'trigger', 'window': 'window'}}})


class LegacyImportSclicerTests(unittest.TestCase):
    """核合同规定的配置语义、静态边界与定位，不复用其它TestCase。"""

    def convert(self, content, mapping=None, mode='sclicer_single'):
        """调用真实字节API；参数: bytes及可选mapping/mode；返回: 结果；异常: API原错传播。"""
        return import_legacy_ini(content, mapping_fixture() if mapping is None else mapping,
            mode=mode, base_dir=ROOT / 'work' / 'm2-import-tests', device_label='home')

    def assert_rejected(self, content, code, mapping=None, mode='sclicer_single'):
        """强制整份失败；参数: 输入/目标机器码；返回: 匹配问题；异常: AssertionError。"""
        result = self.convert(content, mapping, mode)
        self.assertIsNone(result.plan)
        self.assertIs(result.original_ini, content)
        self.assertEqual(result.report.status, 'failed')
        self.assertIsNone(result.report.plan_identity)
        matches = [item for item in result.report.issues if item.code == code and item.level == 'error']
        self.assertTrue(matches, result.report.to_dict())
        return matches[0]

    def test_two_original_single_fixtures_keep_bytes_and_exit_delay(self):
        """核两原夹具实际默认/显式映射和完整字段去向。

        参数: 无；返回: None；异常: AssertionError或夹具读取错误。
        目的: 原post只进exit_delay，活动和窗口分离，UTC不偷偷改变时钟。
        """
        for filename, section, post, alias in (
                ('single-soc.ini', 'TRIGGER_soc=92', 3, 'soc'),
                ('single-mode.ini', 'TRIGGER_ChrgMod=CC', 6, 'mode_value')):
            with self.subTest(filename=filename):
                content = (FIXTURES / filename).read_bytes()
                mapping = mapping_fixture(section)
                before = copy.deepcopy(mapping)
                result = self.convert(content, mapping)
                self.assertIsNotNone(result.plan, result.report.to_dict())
                rule, window = result.plan.rules[0], result.plan.windows[0]
                self.assertEqual((rule.rule_type, rule.minimum_duration_ns, rule.selection_origin), ('condition_duration', 0, 'onset'))
                self.assertEqual(rule.condition.dependencies, (alias,))
                self.assertEqual((window.anchor, window.pre_ns, window.post_ns, window.merge,
                                  window.exit_delay_ns), ('activity', 3_000_000_000, 0, 'exit_delay', post * 10**9))
                self.assertEqual(result.plan.sources[0].config.timebase.origin, 'common')
                self.assertIs(result.original_ini, content)
                self.assertEqual(result.report.source_sha256, hashlib.sha256(content).hexdigest())
                self.assertEqual(result.report.plan_identity, result.plan.identity)
                self.assertEqual(result.report.status, 'success')
                self.assertEqual(len(result.report.fields), 11)
                self.assertTrue(all(item.status in ('mapped', 'replaced') for item in result.report.fields))
                self.assertIn('single_deadline_difference', {item.code for item in result.report.issues})
                self.assertIn('unknown_ttl_difference', {item.code for item in result.report.issues})
                warnings = {item.code: item for item in result.report.issues}
                rounding = warnings['comparison_rounding_difference']
                self.assertEqual(rounding.level, 'warning')
                self.assertIn('round(v,10)', rounding.message)
                self.assertIn('原值', rounding.message)
                duplicate = warnings['raw_trigger_duplicate_difference']
                self.assertEqual(duplicate.level, 'warning')
                self.assertIn('LC02', duplicate.message)
                self.assertIn('不修改旧writer', duplicate.message)
                self.assertIn('不宣称', duplicate.message)
                self.assertEqual(mapping, before)

    def test_start_only_uses_duration_and_preserves_ignored_post(self):
        """核默认10秒及显式固定时长；参数: 无；返回: None；异常: AssertionError。

        目的: 原post不叠加，初始TRUE策略和point窗口必须真实反映计划。
        """
        for duration, expected in (('', 10), ('duration_sec=4\n', 4)):
            with self.subTest(duration=duration):
                content = ('[TRIGGER_test]\nmode=start_only\nstart_expr=OBC_OpMod==2\n'
                           'post_sec=99\n' + duration).encode()
                result = self.convert(content, mode='sclicer_start_only')
                self.assertIsNotNone(result.plan, result.report.to_dict())
                rule, window = result.plan.rules[0], result.plan.windows[0]
                self.assertEqual((rule.rule_type, rule.window_duration_ns, rule.emit_initial), ('start_only', expected * 10**9, True))
                self.assertEqual((window.anchor, window.pre_ns, window.post_ns, window.merge), ('point', 5 * 10**9, expected * 10**9, 'none'))
                post = next(item for item in result.report.fields if item.path.endswith('.post_sec'))
                self.assertEqual((post.status, post.target, post.value), ('replaced', None, '99'))
                issue = next(item for item in result.report.issues if item.code == 'start_only_edge_difference')
                self.assertIn('last_ts', issue.message)

    def test_alias_replacement_changes_names_not_substrings_or_literals(self):
        """核AST精确替换；参数: 无；返回: None；异常: AssertionError。

        原名称有前缀关系且枚举literal等于原Name，字符串不能被全局替换。
        """
        mapping = mapping_fixture()
        mapping['aliases'] = {'Old': 'soc', 'OldLong': 'mode_value', 'State': 'state'}
        mapping['analysis']['signals'].append({'name': 'state', 'source': 'table', 'field': 'state',
            'dtype': 'enum', 'unit': '1', 'valid_for': '1s', 'choices': [[0, 'Old'], [1, 'Other']]})
        result = self.convert(b'[TRIGGER_test]\nmode=single\nexpr=Old==1 and OldLong==2 and State=="Old"\n', mapping)
        self.assertIsNotNone(result.plan, result.report.to_dict())
        tree = ast.parse(result.plan.rules[0].condition.text, mode='eval')
        self.assertEqual({node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}, {'soc', 'mode_value', 'state'})
        self.assertIn('Old', [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)])
        # 两个不同旧键同指同一新信号是明确用户选择，不等于JSON重复键覆盖。
        mapping['aliases']['OldLong'] = 'soc'
        result = self.convert(b'[TRIGGER_test]\nmode=single\nexpr=Old==1 and OldLong<3\n', mapping)
        self.assertIsNotNone(result.plan, result.report.to_dict())
        self.assertEqual(result.plan.rules[0].condition.dependencies, ('soc',))
        mapping['aliases']['Old'] = 'unknown_target'
        self.assert_rejected(b'[TRIGGER_test]\nmode=single\nexpr=Old==1\n', 'invalid_alias', mapping)

    def test_old_option_case_and_single_defaults_are_explicit(self):
        """核旧option小写及5/3默认；参数: 无；返回: None；异常: AssertionError。"""
        result = self.convert(b'[TRIGGER_test]\nMODE=single\nEXPR=OBC_OpMod==2\n')
        self.assertIsNotNone(result.plan, result.report.to_dict())
        window = result.plan.windows[0]
        self.assertEqual((window.pre_ns, window.exit_delay_ns), (5 * 10**9, 3 * 10**9))
        self.assertEqual({item.path for item in result.report.fields}, {'[TRIGGER_test].mode', '[TRIGGER_test].expr'})

    def test_static_can_mapping_never_opens_data_dbc_or_spawns(self):
        """用不存在BLF/DBC核静态无I/O；参数: 无；返回: None；异常: AssertionError。

        目的: 真公开计划包含完整CAN定位，禁止Path探测、打开及进程创建。
        """
        mapping = mapping_fixture()
        mapping['analysis']['sources'] = [{'name': 'table', 'source_type': 'can_blf', 'path': 'absent/input.blf',
            'legacy_profile': 'sclicer-functions-v1', 'dbc_by_channel': {'1': 'absent/input.dbc'},
            'time': {'time_type': 'relative', 'unit': 's', 'clock': 'common'}}]
        for definition in mapping['analysis']['signals']:
            definition['field'] = {'channel': 1,  'signal': definition['field'],
                                   'frame_id': 256, 'is_extended': False, 'is_fd': False}
        content = b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n'
        with patch.object(Path, 'open', side_effect=AssertionError('input open')), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('input read')), \
                patch.object(Path, 'read_text', side_effect=AssertionError('input text')), \
                patch.object(Path, 'stat', side_effect=AssertionError('input stat')), \
                patch.object(Path, 'resolve', side_effect=AssertionError('input resolve')), \
                patch.object(multiprocessing, 'get_context', side_effect=AssertionError('spawn')), \
                patch('builtins.open', side_effect=AssertionError('input builtin open')):
            result = self.convert(content, mapping)
        self.assertIsNotNone(result.plan, result.report.to_dict())
        source = result.plan.raw_config['sources'][0]
        self.assertTrue(Path(source['path']).is_absolute())
        self.assertTrue(Path(source['dbc_by_channel']['1']).is_absolute())

    def test_mapping_requires_metadata_and_empty_generated_nodes(self):
        """缺工程参数不得猜；参数: 无；返回: None；异常: AssertionError。

        缺少周期依据仍整份失败；显式period可以生成三倍有效期，不覆盖预置rule。
        """
        content = b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n'
        for key in ('dtype', 'unit'):
            with self.subTest(key=key):
                mapping = mapping_fixture()
                del mapping['analysis']['signals'][0][key]
                issue = self.assert_rejected(content, 'missing_field', mapping)
                self.assertEqual(issue.path, '$.signals[0].' + key)
        mapping = mapping_fixture()
        del mapping['analysis']['signals'][0]['valid_for']
        issue = self.assert_rejected(content, 'invalid_config', mapping)
        self.assertEqual(issue.path, '$.signals[0].valid_for')
        self.assertIn('period', issue.message)
        mapping['analysis']['signals'][0]['period'] = '500ms'
        converted = self.convert(content, mapping)
        self.assertIsNotNone(converted.plan, converted.report.to_dict())
        self.assertEqual(converted.plan.signals[0].definition.valid_for_ns, 1_500_000_000)
        mapping = mapping_fixture()
        mapping['analysis']['rules'] = [{'name': 'injected'}]
        self.assert_rejected(content, 'nonempty_generated_nodes', mapping)
        mapping = mapping_fixture()
        mapping['unexpected'] = 1
        self.assert_rejected(content, 'invalid_mapping_shape', mapping)
        mapping = mapping_fixture()
        mapping['sections']['extra'] = {'name': 'other', 'window': 'other_window'}
        self.assert_rejected(content, 'section_mapping_mismatch', mapping)

    def test_unsupported_ini_shapes_and_unknown_fields_reject_with_lines(self):
        """逐项核安全语法边界；参数: 无；返回: None；异常: AssertionError。"""
        base = '[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n'
        cases = ((base + 'unknown=1\n', 'unknown_option', 4),
                 (base + '[OTHER]\na=1\n', 'unsupported_section', 4),
                 ('[DEFAULT]\nmode=single\n' + base, 'unsupported_default', 1),
                 (base.replace('OBC_OpMod==2', '%(condition)s'), 'unsupported_interpolation', 3),
                 (base + '   and OBC_OpMod==1\n', 'unsupported_multiline', 4),
                 (base + 'EXPR=OBC_OpMod==1\n', 'duplicate_option', 4),
                 (base + '[TRIGGER_test]\n', 'duplicate_section', 4))
        for text, code, line in cases:
            with self.subTest(code=code):
                issue = self.assert_rejected(text.encode(), code)
                self.assertEqual((issue.origin, issue.line), ('ini', line))
                self.assertGreaterEqual(issue.column, 1)

    def test_mixed_modes_slope_and_disabled_slicing_are_not_partial_success(self):
        """核不支持项整拒；参数: 无；返回: None；异常: AssertionError。"""
        base = '[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n'
        for text, code in ((base.replace('mode=single', 'mode=start_end'), 'unsupported_mode'),
                           (base.replace('OBC_OpMod==2', '_slope_rise_10s_A_4_unused'), 'unsupported_slope'),
                           (base + '[OUTPUT]\nmerge=true\n', 'unsupported_merge'),
                           (base + '[OUTPUT]\nslice=false\n', 'unsupported_slice_disabled')):
            with self.subTest(code=code):
                self.assert_rejected(text.encode(), code)
        mapping = mapping_fixture()
        mapping['sections']['TRIGGER_second'] = {'name': 'second', 'window': 'second_window'}
        self.assert_rejected((base + '[TRIGGER_second]\nmode=start_only\nstart_expr=OBC_OpMod==2\n').encode(),
                             'unsupported_mode', mapping)

    def test_missing_required_fields_use_original_section_header_location(self):
        """缺mode/条件仍有真实定位；参数: 无；返回: None；异常: AssertionError。

        段头前保留空行及注释，强断言实际第三行，不能写None或随意使用首字段行。
        """
        prefix = b'; original comment\n\n[TRIGGER_test]\n'
        for body, field, mode in (
                (b'expr=OBC_OpMod==2\n', 'mode', 'sclicer_single'),
                (b'mode=single\n', 'expr', 'sclicer_single'),
                (b'mode=start_only\n', 'start_expr', 'sclicer_start_only')):
            with self.subTest(field=field):
                issue = self.assert_rejected(prefix + body, 'missing_option', mode=mode)
                self.assertEqual((issue.origin, issue.path, issue.line, issue.column),
                                 ('ini', '[TRIGGER_test].' + field, 3, 1))

    def test_unsafe_expressions_and_missing_aliases_never_execute(self):
        """禁止任意调用/属性/下标；参数: 无；返回: None；异常: AssertionError。

        目的: 注入文本只能作为配置拒绝，不能经旧eval或名称猜测执行。
        """
        for expression in ('__import__("os").system("x")', 'OBC_OpMod.value==2', 'OBC_OpMod[0]==2'):
            with self.subTest(expression=expression), patch('builtins.eval', side_effect=AssertionError('eval')):
                self.assert_rejected(('[TRIGGER_test]\nmode=single\nexpr=' + expression + '\n').encode(), 'unsafe_expression')
        issue = self.assert_rejected(b'[TRIGGER_test]\nmode=single\nexpr=Unmapped==1\n', 'missing_alias')
        self.assertEqual((issue.path, issue.line), ('[TRIGGER_test].expr', 3))

    def test_public_plan_type_unit_id_and_duration_errors_remain_localized(self):
        """用真公开构建器核类型/单位/名称；参数: 无；返回: None；异常: AssertionError。"""
        content = b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n'
        mapping = mapping_fixture()
        mapping['sections']['TRIGGER_test']['window'] = 'trigger'
        result = self.convert(content, mapping)
        self.assertIsNone(result.plan)
        self.assertTrue(any(item.level == 'error' for item in result.report.issues))
        self.assert_rejected(content.replace(b'mode=single', b'mode=single\npre_sec=nan'), 'invalid_duration')
        self.assert_rejected(content.replace(b'mode=single', b'mode=single\npost_sec=-1'), 'invalid_duration')
        # 合法AST但数值根不是布尔，必须由真实条件编译器拒绝并回指原expr。
        result = self.convert(content.replace(b'OBC_OpMod==2', b'OBC_OpMod+2'))
        self.assertIsNone(result.plan)
        self.assertEqual(result.report.issues[-1].origin, 'ini')
        self.assertEqual((result.report.issues[-1].path, result.report.issues[-1].line), ('[TRIGGER_test].expr', 3))

    def test_load_reads_only_config_pair_and_freezes_absolute_paths(self):
        """真实读取两配置并固定路径；参数: 无；返回: None；异常: 原配置I/O或AssertionError。

        新计划搬到另一个输出目录后来源仍定位mapping父目录，不读来源验证此事实。
        """
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            ini, mapping_path = base / 'source.ini', base / 'mapping.json'
            content = b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n'
            ini.write_bytes(content)
            mapping_path.write_text(json.dumps(mapping_fixture()), encoding='utf-8')
            actual_open, reads = Path.open, []

            def read_pair(path, *args, **kwargs):
                """透传真实配置打开；参数: Path/原参数；返回: 文件句柄；异常: 非指定文件AssertionError。"""
                self.assertIn(path, (ini, mapping_path))
                reads.append(path)
                return actual_open(path, *args, **kwargs)

            with patch.object(Path, 'open', read_pair), patch.object(Path, 'stat', side_effect=AssertionError('stat')), \
                    patch.object(Path, 'resolve', side_effect=AssertionError('resolve')):
                result = load_legacy_ini(ini, mapping_path, mode='sclicer_single', device_label='home')
            self.assertIsNotNone(result.plan, result.report.to_dict())
            self.assertEqual(reads, [ini, mapping_path])
            self.assertEqual(result.plan.raw_config['sources'][0]['path'], str((base / 'missing/input.csv').absolute()))
            moved = base / 'another' / 'migrated.json'
            self.assertNotEqual(Path(result.plan.raw_config['sources'][0]['path']).parent, moved.parent)
            self.assertEqual(result.original_ini, content)

    def test_report_immutability_json_failures_and_native_errors_are_distinct(self):
        """核冻结报告、非法JSON及原错误分类；参数: 无；返回: None；异常: AssertionError。"""
        content = b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n'
        result = self.convert(content)
        with self.assertRaises(FrozenInstanceError):
            result.report.status = 'failed'
        exported = result.report.to_dict()
        exported['fields'].clear()
        self.assertTrue(result.report.fields)
        with self.assertRaises(TypeError):
            self.convert(bytearray(content))
        with self.assertRaises(ValueError):
            self.convert(content, mode='unknown')
        self.assert_rejected(b'\xff', 'invalid_ini_encoding')
        self.assert_rejected(content, 'unsupported_section', mode='legacy_sum')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            ini, mapping = base / 'source.ini', base / 'mapping.json'
            ini.write_bytes(content)
            for text, code in (('{"a":1,"a":2}', 'duplicate_mapping_key'), ('{', 'invalid_mapping_json')):
                mapping.write_text(text, encoding='utf-8')
                issue = load_legacy_ini(ini, mapping, mode='sclicer_single').report.issues[-1]
                self.assertEqual((issue.origin, issue.code), ('mapping', code))
            marker = PermissionError('真实配置读取被拒绝')
            with patch.object(Path, 'read_bytes', side_effect=marker):
                with self.assertRaises(PermissionError) as caught:
                    load_legacy_ini(ini, mapping, mode='sclicer_single')
            self.assertIs(caught.exception, marker)
        # 资源失败和取消不能被通用配置报告吞掉，且保同一个原异常对象。
        for marker in (MemoryError('真实静态构造资源失败'), KeyboardInterrupt('真实取消')):
            with self.subTest(error=type(marker).__name__), \
                    patch('chronaxis.migration.api.AnalysisPlan.from_dict', side_effect=marker):
                with self.assertRaises(type(marker)) as caught:
                    self.convert(content)
                self.assertIs(caught.exception, marker)


if __name__ == '__main__':
    unittest.main()


def _current_mapping(mapping):
    """把共享旧夹具声明转换为当前公开结构；不改变原INI、数值或业务断言。"""
    from chronaxis.planning.config_groups import public_configuration
    mapping['analysis']=public_configuration(mapping['analysis'])
    return mapping
