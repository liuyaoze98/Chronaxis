"""核ChrgInfo静态导入、有限参数与原方向分桶，不运行旧链或分析流。

输入为合成的单BLF计划和旧INI bytes，验证单位拒绝及配置定位。
输出核真实公共AnalysisPlan及逐字段报告，不把合法声明当作DBC已核或数值运行。
所有数据/DBC路径均不存在；加载测试仅创建临时配置，故障不改RefProjects。
"""

import copy
import hashlib
import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronaxis.migration import import_legacy_ini, load_legacy_ini

ROOT = Path(__file__).absolute().parents[2]


def legacy_mapping_fixture(*, disjunction=False, section='integral_energy', backend='reference', direction='Direction.raw'):
    """生成可公开构建的J配置；参数: 分桶/段/后端/原方向名；返回: 新mapping；异常: 无。

    目的: Power W乘显式period s得到J，方向独立且完整同消息；不声明真实文件存在。
    """
    def signal(name, raw, unit):
        """生成完整CAN信号声明；参数: 别名/原名/单位；返回: dict；异常: 无。"""
        return {'name': name, 'source': 'bus', 'field': {'channel': 1,
            'signal': raw, 'frame_id': 256, 'is_extended': False, 'is_fd': False},
            'dtype': 'float64', 'unit': unit, 'valid_for': '1ns', 'same_time_policy': 'last_by_sequence'}

    signals = [signal('power', 'Power', 'W')]
    aliases = {'signal_P': 'power'}
    if disjunction:
        signals.append(signal('direction', direction, '1'))
        aliases[direction] = 'direction'
    return _current_mapping({'mapping_version': 1, 'path_base': 'mapping_directory', 'io_policy': 'explicit_mapping',
        'analysis': {'config_version': 3,
            'dataset': {'name': 'legacy_import', 'entity': 'synthetic', 'session': 'trial',
                        'domain': {'start': '0s', 'end': '3s'}},
            'sources': [{'name': 'bus', 'source_type': 'can_blf', 'path': 'missing/source.blf',
                'dbc_by_channel': {'1': 'missing/source.dbc'}, 'legacy_profile': 'sclicer-functions-v1',
                'time': {'time_type': 'relative', 'unit': 's', 'origin': 'common'}}],
            'signals': signals, 'execution': {'backend': backend}},
        'aliases': aliases, 'sections': {section: {'name': 'energy', 'source': 'bus', 'unit': 'J',
            'message_policy': 'current_message-v1',
            'update_message': {'channel': 1, 'frame_id': 256, 'is_extended': False, 'is_fd': False},
            'parameter_units': {'period': 's'}}}})


def legacy_ini(*, disjunction=False, direction='Direction.raw', section='integral_energy', expr='signal_P * period'):
    """生成真实旧语法字节；参数: 分桶/原名/段/公式；返回: bytes；异常: 无。

    原I/O保审计但由mapping替代，行尾分号是ChrgInfo配置注释，不执行旧logger。
    """
    text = ('[input]\nini_path=old.ini\ndbc_path=old.dbc\nmsg_path=old-data/\n'
            '[output]\nlog_path=old-log/log.txt\n[' + section + ']\n'
            'signal_P=Power\nperiod=0.1\nexpr=' + expr + '\n')
    if disjunction:
        text += 'disjunction=' + direction + '\n'
    return text.encode('utf-8')


class LegacyImportSumTests(unittest.TestCase):
    """验证完整导入/整份拒绝及原字节定位，不继承其它TestCase。"""

    def convert(self, content, mapping=None):
        """调用公开导入；参数: bytes/可选mapping；返回: 结果；异常: API原错传播。"""
        return import_legacy_ini(content, legacy_mapping_fixture() if mapping is None else mapping,
            mode='legacy_sum', base_dir=ROOT / 'work' / 'm2-import-tests', device_label='home')

    def rejected(self, content, code, mapping=None):
        """核整份失败及原bytes；参数: 原输入/机器码；返回: 问题；异常: AssertionError。"""
        result = self.convert(content, mapping)
        self.assertIsNone(result.plan)
        self.assertIs(result.original_ini, content)
        self.assertEqual(result.report.status, 'failed')
        self.assertIsNone(result.report.plan_identity)
        matches = [item for item in result.report.issues if item.code == code and item.level == 'error']
        self.assertTrue(matches, result.report.to_dict())
        return matches[0]

    def test_plain_and_bucket_j_plans_build_for_both_backends(self):
        """用公开构造核两后端声明及一拆二；参数: 无；返回: None；异常: AssertionError。

        本方法不执行数值核，真400/800和分桶数值另由B3及根集成验证。
        """
        for backend in ('reference', 'numpy'):
            for bucketed in (False, True):
                with self.subTest(backend=backend, bucketed=bucketed):
                    mapping = legacy_mapping_fixture(disjunction=bucketed, backend=backend)
                    before = copy.deepcopy(mapping)
                    content = legacy_ini(disjunction=bucketed)
                    result = self.convert(content, mapping)
                    self.assertIsNotNone(result.plan, result.report.to_dict())
                    calculations = result.plan.message_calculations
                    self.assertEqual(len(calculations), 2 if bucketed else 1)
                    self.assertEqual([item.calculation_id for item in calculations],
                                     ['energy_positive', 'energy_negative'] if bucketed else ['energy'])
                    for calculation in calculations:
                        self.assertEqual((calculation.expr.text, calculation.unit, calculation.message_policy),
                                         ('power * period', 'J', 'current_message-v1'))
                        self.assertEqual([(item.name, item.value.hex(), item.unit) for item in calculation.parameters],
                                         [('period', float(0.1).hex(), 's')])
                    if bucketed:
                        self.assertEqual([item.disjunction.bucket for item in calculations], ['positive', 'negative'])
                        self.assertTrue(all(item.disjunction.signal == 'direction' for item in calculations))
                        self.assertTrue(all(item.disjunction.value_policy == 'raw_decoded-v1' for item in calculations))
                    else:
                        self.assertIsNone(calculations[0].disjunction)
                    self.assertEqual(result.plan.execution.backend, backend)
                    self.assertEqual(result.report.source_sha256, hashlib.sha256(content).hexdigest())
                    self.assertEqual(result.report.plan_identity, result.plan.identity)
                    self.assertEqual(mapping, before)
                    self.assertTrue(all(item.status in ('mapped', 'replaced') for item in result.report.fields))

    def test_dot_direction_is_independent_of_expr_and_reports_both_targets(self):
        """保方向原点号名与两个输出映射；参数: 无；返回: None；异常: AssertionError。"""
        content = legacy_ini(disjunction=True)
        result = self.convert(content, legacy_mapping_fixture(disjunction=True))
        self.assertIsNotNone(result.plan, result.report.to_dict())
        self.assertTrue(all(item.expr.dependencies == ('power',) for item in result.plan.message_calculations))
        mappings = [item for item in result.report.fields if item.path == '[integral_energy].disjunction']
        self.assertEqual({item.target for item in mappings}, {
            '$.message_calculations[0].split_by_sign.signal', '$.message_calculations[1].split_by_sign.signal'})
        self.assertEqual({item.line for item in mappings}, {11})
        self.assertEqual({item.value for item in mappings}, {'Direction.raw'})
        outputs = [item.message for item in result.report.issues if item.code == 'disjunction_output_mapping']
        self.assertEqual(outputs, ['energy+ → energy_positive', 'energy- → energy_negative'])
        warnings = {item.code: item.message for item in result.report.issues}
        self.assertIn('NONFINITE_INPUT', warnings['disjunction_quality_difference'])
        self.assertIn('MISSING_INPUT', warnings['disjunction_quality_difference'])
        self.assertIn('None', warnings['empty_sum_difference'])
        self.assertIn('每次AnalysisRunner会话独立', warnings['current_message_difference'])
        # 同一个Power既作公式值又作原方向，两个不同旧键可显式指向同一别名。
        mapping = legacy_mapping_fixture()
        mapping['aliases']['Power'] = 'power'
        same = self.convert(legacy_ini(disjunction=True, direction='Power'), mapping)
        self.assertIsNotNone(same.plan, same.report.to_dict())
        self.assertTrue(all(item.disjunction.signal == 'power' for item in same.plan.message_calculations))

    def test_original_direction_name_source_and_full_message_must_match(self):
        """拒别名指错原字段和跨消息；参数: 无；返回: None；异常: AssertionError。"""
        content = legacy_ini(disjunction=True)
        mapping = legacy_mapping_fixture(disjunction=True)
        mapping['analysis']['signals'][1]['field']['signal'] = 'Other.raw'
        issue = self.rejected(content, 'direction_field_mismatch', mapping)
        self.assertEqual((issue.path, issue.line), ('[integral_energy].disjunction', 11))
        mapping = legacy_mapping_fixture(disjunction=True)
        del mapping['aliases']['Direction.raw']
        inferred = self.convert(content, mapping)
        self.assertIsNotNone(inferred.plan, inferred.report.to_dict())
        self.assertTrue(all(item.disjunction.signal == 'direction' for item in inferred.plan.message_calculations))
        duplicate = dict(mapping['analysis']['signals'][1], name='other_direction')
        mapping['analysis']['signals'].append(duplicate)
        self.rejected(content, 'missing_direction_alias', mapping)
        for key, value in (('message', 'OtherMessage'), ('frame_id', 257), ('is_fd', True)):
            with self.subTest(key=key):
                mapping = legacy_mapping_fixture(disjunction=True)
                mapping['analysis']['signals'][1]['field'][key] = value
                result = self.convert(content, mapping)
                self.assertIsNone(result.plan)
                self.assertNotIn('unsupported_disjunction', {item.code for item in result.report.issues})

    def test_case_semicolon_comments_and_safe_fraction_parameters(self):
        """核大小写、分号及1/3600原序值；参数: 无；返回: None；异常: AssertionError。"""
        content = legacy_ini(expr='signal_P * period * gain * GAIN * factor1')
        content = content.replace(b'[integral_energy]', b'[global]\ngain=1/3600 ; %(not_interpolation)s\nGAIN=2\n[integral_energy]')
        content = content.replace(b'period=0.1', b'period=0.1 ; original float seconds\nfactor1=3 ; kept factor')
        mapping = legacy_mapping_fixture()
        mapping['sections']['integral_energy']['parameter_units'].update({'gain': '1', 'GAIN': '1', 'factor1': '1'})
        with patch('builtins.eval', side_effect=AssertionError('eval不可执行')):
            result = self.convert(content, mapping)
        self.assertIsNotNone(result.plan, result.report.to_dict())
        parameters = result.plan.message_calculations[0].parameters
        self.assertEqual([item.name for item in parameters], ['period', 'factor1', 'gain', 'GAIN'])
        self.assertEqual([item.value.hex() for item in parameters], [float(0.1).hex(), float(3).hex(), float(1/3600).hex(), float(2).hex()])
        global_rows = [item for item in result.report.fields if item.path == '[global].gain']
        self.assertEqual(global_rows[0].value, '1/3600')
        self.assertEqual(result.plan.message_calculations[0].expr.text, 'power * period * gain * GAIN * factor1')
        self.rejected(b'# not a ChrgInfo comment\n' + legacy_ini(), 'invalid_ini')

    def test_invalid_constant_calls_nonfinite_precision_and_operator_are_rejected(self):
        """有限纯常量不能执行调用；参数: 无；返回: None；异常: AssertionError。

        不用NumPy或被测数值核算期望；零除/超宽整数/幂均是明确配置拒绝。
        """
        for value in ('__import__("os").system("x")', '1/0', '1e999', '2+3', '0x10',
                      '2**3', 'True', 'other_name', '"0.1"'):
            with self.subTest(value=value), patch('builtins.eval', side_effect=AssertionError('eval')):
                content = legacy_ini().replace(b'period=0.1', ('period=' + value).encode())
                issue = self.rejected(content, 'invalid_constant')
                self.assertEqual((issue.origin, issue.path, issue.line), ('ini', '[integral_energy].period', 9))
        # global才允许四则，但原生int计算结果不能有损转FLOAT64参数。
        content = b'[global]\ngain=9007199254740993 + 0\n' + legacy_ini()
        self.rejected(content, 'invalid_constant')

    def test_factor_float_syntax_and_each_signal_raw_source_mapping_are_strict(self):
        """旧factor非法值不变成新算术，alias不能换原字段；参数: 无；返回: None；异常: AssertionError。"""
        for value in ('2+3', '0x10', '__import__("os")'):
            with self.subTest(factor=value):
                content = legacy_ini() + ('factor1=' + value + '\n').encode()
                issue = self.rejected(content, 'invalid_factor')
                self.assertEqual((issue.path, issue.line), ('[integral_energy].factor1', 11))
                self.assertIn('fallback=1.0', issue.message)
        mapping = legacy_mapping_fixture()
        mapping['analysis']['signals'][0]['field']['signal'] = 'AnotherPower'
        issue = self.rejected(legacy_ini(), 'signal_field_mismatch', mapping)
        self.assertEqual((issue.path, issue.line), ('[integral_energy].signal_P', 8))
        mapping = legacy_mapping_fixture()
        other = copy.deepcopy(mapping['analysis']['sources'][0])
        other['name'] = 'other_bus'
        mapping['analysis']['sources'].append(other)
        mapping['analysis']['signals'][0]['source'] = 'other_bus'
        self.rejected(legacy_ini(), 'signal_field_mismatch', mapping)
        mapping = legacy_mapping_fixture()
        second = copy.deepcopy(mapping['analysis']['signals'][0])
        second.update(name='other_power')
        second['field']['signal'] = 'OtherPower'
        mapping['analysis']['signals'].append(second)
        mapping['aliases'].update(signal_P='other_power', signal_Q='power')
        content = legacy_ini(expr='(signal_P + signal_Q) * period') + b'signal_Q=OtherPower\n'
        self.rejected(content, 'signal_field_mismatch', mapping)

    def test_float_text_and_parenthesized_integer_ast_keep_distinct_precision_rules(self):
        """区分旧float文本与AST原生int；参数: 无；返回: None；异常: AssertionError。

        原大整数文本在旧float阶段已舍入，保该实际float及原文；括号触发global
        AST回退后仍是精确int，不能借此绕过ExpressionParameter精确转换合同。
        """
        literal = '9007199254740993'
        content = legacy_ini().replace(b'period=0.1', ('period=' + literal).encode())
        result = self.convert(content)
        self.assertIsNotNone(result.plan, result.report.to_dict())
        self.assertEqual(result.plan.message_calculations[0].parameters[0].value.hex(), float(literal).hex())
        self.assertEqual(next(item.value for item in result.report.fields if item.path.endswith('.period')), literal)
        mapping = legacy_mapping_fixture()
        mapping['sections']['integral_energy']['parameter_units']['gain'] = '1'
        content = ('[global]\ngain=' + literal + '\n').encode() + legacy_ini(expr='signal_P * period * gain')
        result = self.convert(content, mapping)
        self.assertIsNotNone(result.plan, result.report.to_dict())
        self.assertEqual(result.plan.message_calculations[0].parameters[1].value.hex(), float(literal).hex())
        self.rejected(content.replace(('gain=' + literal).encode(), ('gain=(' + literal + ')').encode()),
                      'invalid_constant', mapping)

    def test_override_and_unused_signal_gate_are_not_silently_rewritten(self):
        """旧覆盖及未用signal仍有门控，不能丢失；参数: 无；返回: None；异常: AssertionError。"""
        for key in ('period', 'signal_P', 'factor1'):
            with self.subTest(key=key):
                content = legacy_ini().replace(b'[integral_energy]', ('[global]\n' + key + '=2\n[integral_energy]').encode())
                if key == 'factor1':
                    content += b'factor1=3\n'
                self.rejected(content, 'variable_override')
        content = legacy_ini() + b'signal_D=Direction.raw\n'
        mapping = legacy_mapping_fixture(disjunction=True)
        mapping['aliases']['signal_D'] = 'direction'
        issue = self.rejected(content, 'unused_signal_gate', mapping)
        self.assertIn('signal_D', issue.message)

    def test_every_parameter_unit_is_explicit_and_known_mismatch_points_to_expr(self):
        """核参数单位缺失/冗余及真实J/kWh诊断；参数: 无；返回: None；异常: AssertionError。"""
        mapping = legacy_mapping_fixture()
        mapping['sections']['integral_energy']['parameter_units'] = {}
        issue = self.rejected(legacy_ini(), 'parameter_units_mismatch', mapping)
        self.assertIn('period', issue.message)
        mapping = legacy_mapping_fixture()
        mapping['sections']['integral_energy']['parameter_units']['unused'] = '1'
        self.rejected(legacy_ini(), 'parameter_units_mismatch', mapping)
        mapping = legacy_mapping_fixture()
        mapping['sections']['integral_energy']['unit'] = 'kWh'
        result = self.convert(legacy_ini(), mapping)
        self.assertIsNone(result.plan)
        issue = result.report.issues[-1]
        self.assertEqual((issue.origin, issue.path, issue.line), ('ini', '[integral_energy].expr', 10))
        self.assertIn('J', issue.message)
        self.assertIn('kWh', issue.message)

    def test_disjunction_reaches_specific_unit_error_not_disjunction_rejection(self):
        """合成分桶公式触发单位拒绝；参数: 无；返回: None；异常: AssertionError。"""
        content = (b'[input]\nini_path=old.ini\ndbc_path=old.dbc\nmsg_path=old-data/\n'
                   b'[output]\nlog_path=old-log/log.txt\n[global]\nWh_to_kWh=1/1000\nsec_to_hour=1/3600\n[integral_bms1]\n'
                   b'signal_V=BMS_BatPackActVol\nsignal_I=BMS_BatPackActCur\n'
                   b'period=0.1\n'
                   b'expr=signal_V * signal_I * period * Wh_to_kWh * sec_to_hour\n'
                   b'disjunction=BMS_BatPackActCur\n')
        mapping = legacy_mapping_fixture(disjunction=True, section='integral_bms1', direction='BMS_BatPackActCur')
        voltage, current = mapping['analysis']['signals']
        voltage.update(name='voltage', unit='V')
        voltage['field']['signal'] = 'BMS_BatPackActVol'
        current.update(name='current', unit='A')
        current['field']['signal'] = 'BMS_BatPackActCur'
        mapping['aliases'] = {'signal_V': 'voltage', 'signal_I': 'current', 'BMS_BatPackActCur': 'current'}
        settings = mapping['sections']['integral_bms1']
        settings['unit'] = 'kWh'
        settings['parameter_units'] = {'period': 's', 'Wh_to_kWh': '1', 'sec_to_hour': '1'}
        result = self.convert(content, mapping)
        self.assertIsNone(result.plan)
        self.assertIs(result.original_ini, content)
        issue = result.report.issues[-1]
        self.assertEqual((issue.origin, issue.path, issue.line), ('ini', '[integral_bms1].expr', 14))
        self.assertIn('J', issue.message)
        self.assertIn('kWh', issue.message)
        self.assertNotIn('unsupported_disjunction', {item.code for item in result.report.issues})

    def test_missing_fields_unknown_sections_and_unsafe_formula_have_locations(self):
        """核整份拒绝和缺项段头回退；参数: 无；返回: None；异常: AssertionError。"""
        content = legacy_ini()
        for key, line in (('period', 9), ('expr', 10)):
            with self.subTest(key=key):
                body = b'\n'.join(part for part in content.split(b'\n') if not part.startswith(key.encode() + b'='))
                issue = self.rejected(body, 'missing_option')
                self.assertEqual((issue.path, issue.line, issue.column), ('[integral_energy].' + key, 7, 1))
        issue = self.rejected(content + b'[tragger]\ntragger=True\n', 'unsupported_section')
        self.assertEqual((issue.path, issue.line), ('[tragger]', 11))
        for tail in (b'raw_msg_ts=timestamp\n', b'cache_policy=profile\n', b'unknown=1\n'):
            self.rejected(content + tail, 'unknown_option')
        self.rejected(content.replace(b'expr=signal_P * period', b'expr=Power.raw * period'), 'unsafe_expression')
        self.rejected(content.replace(b'expr=signal_P * period', b'expr=abs(signal_P) * period'), 'unsafe_expression')

    def test_global_fields_map_to_each_section_and_duplicate_ids_fail_whole_file(self):
        """保多section参数去向，不复用局部状态；参数: 无；返回: None；异常: AssertionError。"""
        content = b'[global]\ngain=2\n' + legacy_ini(expr='signal_P * period * gain')
        content += b'[integral_second]\nsignal_P=Power\nperiod=0.2\nexpr=signal_P * period * gain\n'
        mapping = legacy_mapping_fixture()
        settings = mapping['sections']['integral_energy']
        settings['parameter_units']['gain'] = '1'
        mapping['sections']['integral_second'] = copy.deepcopy(settings)
        mapping['sections']['integral_second']['name'] = 'second'
        result = self.convert(content, mapping)
        self.assertIsNotNone(result.plan, result.report.to_dict())
        self.assertEqual([item.parameters[0].value for item in result.plan.message_calculations], [0.1, 0.2])
        targets = [item.target for item in result.report.fields if item.path == '[global].gain']
        self.assertEqual(set(targets), {'$.message_calculations[0].parameters.gain.value', '$.message_calculations[1].parameters.gain.value'})
        mapping['sections']['integral_second']['name'] = 'energy'
        result = self.convert(content, mapping)
        self.assertIsNone(result.plan)
        self.assertEqual(result.report.status, 'failed')

    def test_static_import_and_load_open_only_explicit_config_pair(self):
        """禁止静态数据/DBC/进程I/O并核两配置加载；参数: 无；返回: None；异常: AssertionError。

        Path观察器透传实际配置读取，声明路径仍写成mapping父下绝对定位。
        """
        content, mapping = legacy_ini(disjunction=True), legacy_mapping_fixture(disjunction=True)
        with patch.object(Path, 'open', side_effect=AssertionError('静态open')), \
                patch.object(Path, 'stat', side_effect=AssertionError('静态stat')), \
                patch.object(Path, 'resolve', side_effect=AssertionError('静态resolve')), \
                patch.object(multiprocessing, 'get_context', side_effect=AssertionError('静态spawn')), \
                patch('builtins.open', side_effect=AssertionError('静态DBC/数据open')):
            result = self.convert(content, mapping)
        self.assertIsNotNone(result.plan, result.report.to_dict())
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            ini, mapping_path = base / 'source.ini', base / 'mapping.json'
            ini.write_bytes(content)
            mapping_path.write_text(json.dumps(mapping), encoding='utf-8')
            original_open, reads = Path.open, []

            def read_pair(path,*args,**kwargs):
                """只打开两个真实配置。参数: Path和打开参数。返回: FD。异常: 非配置路径断言。"""
                self.assertIn(path, (ini, mapping_path))
                reads.append(path)
                return original_open(path,*args,**kwargs)

            with patch.object(Path, 'open', read_pair):
                result = load_legacy_ini(ini, mapping_path, mode='legacy_sum', device_label='home')
            self.assertIsNotNone(result.plan, result.report.to_dict())
            self.assertEqual(reads, [ini, mapping_path])
            source = result.plan.raw_config['sources'][0]
            self.assertEqual(source['path'], str((base / 'missing/source.blf').absolute()))
            self.assertEqual(source['dbc_by_channel']['1'], str((base / 'missing/source.dbc').absolute()))

    def test_case_sensitive_duplicates_interpolation_and_wrong_profile_reject(self):
        """保旧大小写与安全边界；参数: 无；返回: None；异常: AssertionError。"""
        content = legacy_ini()
        issue = self.rejected(content + b'period=0.2\n', 'duplicate_option')
        self.assertEqual(issue.line, 11)
        self.rejected(content.replace(b'period=0.1', b'Period=0.1'), 'unknown_option')
        self.rejected(content.replace(b'period=0.1', b'period=%(value)s'), 'unsupported_interpolation')
        self.rejected(b'[DEFAULT]\nperiod=0.1\n' + content, 'unsupported_default')
        mapping = legacy_mapping_fixture()
        mapping['analysis']['sources'][0]['legacy_profile'] = 'chrginfo-main-v1'
        self.rejected(content, 'invalid_legacy_source', mapping)


if __name__ == '__main__':
    unittest.main()


def _current_mapping(mapping):
    """把共享旧夹具声明转换为当前公开结构；不改变原INI、数值或业务断言。"""
    from chronaxis.planning.config_groups import public_configuration
    mapping['analysis']=public_configuration(mapping['analysis'])
    return mapping
