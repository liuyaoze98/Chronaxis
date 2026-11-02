"""核旧 slope 字符串到可执行完整窗口计划的明确迁移。

合成INI覆盖带下划线名称、数字边界和旧解析缺陷；手算输入验证实际两后端，
并通过真实CLI保存原配置、报告和计算结果。所有运行产物放在专用work目录，
不运行或修改历史项目。旧样本口径与真实业务数据不在本测试中冒充已验。
"""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis import AnalysisRunner
from chronaxis.migration import import_legacy_ini
from test_legacy_import_sclicer import mapping_fixture

ROOT = Path(__file__).absolute().parents[2]


def slope_mapping():
    """给出完整窗口及初始化/重触发的明确选择。参数: 无。返回: dict。异常: 无。"""
    mapping = mapping_fixture()
    mapping['sections']['TRIGGER_test'].update(coverage_policy='full', emit_initial=True, retrigger='edge')
    mapping['analysis']['signals'] = [dict(name='soc', source='table', field='SOC_raw',
        dtype='int64', unit='1', valid_for='20s')]
    mapping['aliases'] = {'BMS_SOC_raw': 'soc'}
    mapping['analysis']['dataset']['domain']['end'] = '14s'
    mapping['analysis']['sources'] = [dict(name='table', source_type='memory',
        time=dict(time_type='relative', unit='s', origin='common'), rows=[
            dict(time=f'{time}s', values={'SOC_raw': value})
            for time, value in ((0, 0), (2, 0), (4, 5), (6, 5), (8, 0), (10, 0), (12, 5), (14, 5))])]
    mapping['analysis']['execution'] = dict(batch_rows=2, memory_budget_bytes=256 * 1024**2)
    return _current_mapping(mapping)


def slope_ini(expression='_slope_rise_4s_BMS_SOC_raw_5'):
    """生成single段内的旧slope表达式。参数: expression。返回: bytes。异常: 编码错误。"""
    return ('[TRIGGER_test]\nmode=single\nexpr=' + expression + '\npre_sec=1\npost_sec=1\n').encode()


class LegacyImportSlopeTests(unittest.TestCase):
    """以独立手算时间和真实入口检查迁移结果，失败不得留下部分计划。"""

    def convert(self, expression=None, mapping=None, content=None):
        """调用字节API。参数: 可选原表达式/映射/原文。返回: 导入结果。异常: 原API错误。"""
        return import_legacy_ini(content if content is not None else slope_ini() if expression is None else slope_ini(expression),
            slope_mapping() if mapping is None else mapping, mode='sclicer_slope', base_dir=ROOT, device_label='home')

    def test_parse_underscores_and_keep_original(self):
        """完整匹配名称而非拆开下划线。参数: 无。返回: None。异常: 断言失败。"""
        mapping = slope_mapping()
        before, content = copy.deepcopy(mapping), slope_ini()
        with patch.object(Path, 'open', side_effect=AssertionError('静态转换不得读取文件')):
            result = self.convert(mapping=mapping, content=content)
        self.assertEqual(result.report.status, 'success', result.report.to_dict())
        self.assertIs(result.original_ini, content)
        self.assertEqual(mapping, before)
        rule, window = result.plan.rules[0], result.plan.windows[0]
        self.assertEqual(rule.rule_type, 'window_delta')
        self.assertEqual(rule.condition.dependencies, ('soc',))
        self.assertTrue(rule.window_delta.monotonic)
        self.assertEqual((window.anchor, window.pre_ns, window.post_ns), ('point', 10**9, 10**9))
        self.assertTrue(all(field.status == 'mapped' for field in result.report.fields))
        self.assertIn('slope_semantic_differences', {item.code for item in result.report.issues})

    def test_two_backends_real_events_and_segments(self):
        """4秒与12秒各上升5，得到两点和两段。参数: 无。返回: None。异常: 断言/执行错误。"""
        plan = self.convert().plan
        self.assertIsNotNone(plan)
        for backend in ('reference', 'numpy'):
            result = AnalysisRunner(backend).run(plan, work_dir=ROOT / 'work/m3-migrate-home-20261022/tests' / uuid4().hex)
            try:
                self.assertEqual([row.confirmed_ns for row in result.iter_events()], [4 * 10**9, 12 * 10**9])
                self.assertEqual(len(list(result.iter_segments())), 2)
            finally:
                result.close()
            self.assertEqual(result.spool.budget.ram_bytes, 0)

    def test_slope2_any_is_not_monotonic(self):
        """0→10→5只符合非单调变化量。参数: 无。返回: None。异常: 断言/执行错误。"""
        for prefix, expected in (('slope', []), ('slope2', [4 * 10**9])):
            mapping = slope_mapping()
            mapping['analysis']['dataset']['domain']['end'] = '4s'
            mapping['analysis']['sources'][0]['rows'] = [dict(time=f'{time}s', values={'SOC_raw': value})
                for time, value in ((0, 0), (2, 10), (4, 5))]
            plan = self.convert(f'_{prefix}_any_4s_BMS_SOC_raw_4', mapping).plan
            self.assertIsNotNone(plan)
            for backend in ('reference', 'numpy'):
                result = AnalysisRunner(backend).run(plan, work_dir=ROOT / 'work/m3-migrate-home-20261022/tests' / uuid4().hex)
                try:
                    self.assertEqual([row.confirmed_ns for row in result.iter_events()], expected)
                finally:
                    result.close()

    def test_direction_and_decimal_threshold(self):
        """阈值保留信号单位且支持小数，不计算每秒速率。参数: 无。返回: None。异常: 断言失败。"""
        for direction in ('rise', 'fall', 'any'):
            result = self.convert(f'_slope2_{direction}_2.5s_BMS_SOC_raw_1.25')
            self.assertIsNotNone(result.plan, result.report.to_dict())
            spec = result.plan.rules[0].window_delta
            self.assertEqual((spec.direction, spec.window_ns, spec.threshold), (direction, 2500000000, 1.25))

    def test_bad_syntax_values_and_padding_are_located(self):
        """未知名/额外尾段及坏数字整份拒绝并定位expr行。参数: 无。返回: None。异常: 断言失败。"""
        variants = (
            ('_slope_up_4s_BMS_SOC_raw_5', 'invalid_slope_syntax'),
            ('_slope_rise_4s_unknown_5', 'missing_slope_alias'),
            ('_slope_rise_4s_BMS_SOC_raw_5_unused', 'missing_slope_alias'),
            ('_slope_rise_0s_BMS_SOC_raw_5', 'invalid_slope_window'),
            ('_slope_rise_4ms_BMS_SOC_raw_5', 'invalid_slope_window'),
            ('_slope_rise_999999999999s_BMS_SOC_raw_5', 'invalid_slope_window'))
        variants += tuple((f'_slope_rise_4s_BMS_SOC_raw_{value}', 'invalid_slope_threshold')
                          for value in ('-1', 'NaN', 'inf', '1e99999', '1e-99999', 'x'))
        for expression, code in variants:
            with self.subTest(expression=expression):
                result = self.convert(expression)
                self.assertIsNone(result.plan)
                issue = result.report.issues[-1]
                self.assertEqual((issue.code, issue.origin, issue.line), (code, 'ini', 3))
                self.assertIsNone(result.report.plan_identity)

    def test_incomplete_window_gap_and_explicit_once(self):
        """两点不足整窗或窗内缺值不得触发；once只输出首次。参数: 无。返回: None。异常: 断言失败。"""
        for rows in (((0, 0), (2, 10)), ((0, 0), (2, None), (4, 10))):
            mapping = slope_mapping()
            mapping['analysis']['sources'][0]['rows'] = [dict(time=f'{time}s', values={'SOC_raw': value})
                for time, value in rows]
            result = AnalysisRunner().run(self.convert(mapping=mapping).plan,
                work_dir=ROOT / 'work/m3-migrate-home-20261022/tests' / uuid4().hex)
            try:
                self.assertEqual(list(result.iter_events()), [])
            finally:
                result.close()
        mapping = slope_mapping()
        mapping['sections']['TRIGGER_test']['retrigger'] = 'once'
        result = AnalysisRunner().run(self.convert(mapping=mapping).plan,
            work_dir=ROOT / 'work/m3-migrate-home-20261022/tests' / uuid4().hex)
        try:
            self.assertEqual([row.confirmed_ns for row in result.iter_events()], [4 * 10**9])
        finally:
            result.close()

    def test_mixed_file_has_no_partial_plan(self):
        """前段成功也不能跳过后段非法表达式。参数: 无。返回: None。异常: 断言失败。"""
        mapping = slope_mapping()
        mapping['sections']['TRIGGER_other'] = dict(mapping['sections']['TRIGGER_test'], name='other', window='other_window')
        content = slope_ini() + b'\n[TRIGGER_other]\nmode=single\nexpr=BMS_SOC_raw > 0\n'
        result = self.convert(mapping=mapping, content=content)
        self.assertIsNone(result.plan)
        self.assertEqual(result.report.issues[-1].path, '[TRIGGER_other].expr')
        self.assertIsNone(result.report.plan_identity)

    def test_explicit_policies_and_mapping_shape(self):
        """缺少选择时不能猜旧锁存或覆盖口径。参数: 无。返回: None。异常: 断言失败。"""
        for key, value, code in (('coverage_policy', 'legacy_samples', 'unsupported_slope_coverage'),
                ('emit_initial', 1, 'invalid_slope_initial'), ('retrigger', 'auto', 'invalid_slope_retrigger')):
            mapping = slope_mapping()
            mapping['sections']['TRIGGER_test'][key] = value
            result = self.convert(mapping=mapping)
            self.assertIsNone(result.plan)
            self.assertEqual(result.report.issues[-1].code, code)
        mapping = slope_mapping()
        del mapping['sections']['TRIGGER_test']['emit_initial']
        self.assertEqual(self.convert(mapping=mapping).report.issues[-1].code, 'invalid_section_mapping')

    def test_missing_expr_mixed_and_old_mode_remain_rejected(self):
        """新模式不顺手接受普通条件或混合start_end。参数: 无。返回: None。异常: 断言失败。"""
        for content, code in ((b'[TRIGGER_test]\nmode=single\n', 'missing_option'),
                (slope_ini('BMS_SOC_raw > 0'), 'invalid_slope_syntax'),
                (slope_ini().replace(b'mode=single', b'mode=start_end'), 'unsupported_mode')):
            result = self.convert(content=content)
            self.assertIsNone(result.plan)
            self.assertEqual(result.report.issues[-1].code, code)
        old = mapping_fixture()
        old['aliases'] = {'BMS_SOC_raw': 'soc'}
        result = import_legacy_ini(slope_ini(), old, mode='sclicer_single', base_dir=ROOT)
        self.assertEqual(result.report.issues[-1].code, 'unsupported_slope')

    def test_cli_import_validate_and_run(self):
        """真实CLI保原文和报告，再运行生成计划。参数: 无。返回: None。异常: 断言/子进程错误。"""
        work = ROOT / 'work/m3-migrate-home-20261022/tests' / uuid4().hex
        work.mkdir(parents=True)
        original, mapping, plan = work / 'old.ini', work / 'mapping.json', work / 'plan.json'
        original.write_bytes(slope_ini())
        mapping.write_text(json.dumps(slope_mapping()), encoding='utf-8')
        environment = dict(os.environ, CHRONAXIS_DEVICE_LABEL='home', PYTHONDONTWRITEBYTECODE='1')
        commands = [('legacy', 'import', str(original), '--mapping', str(mapping), '--mode', 'sclicer_slope', '--output', str(plan)),
                    ('validate', str(plan)), ('run', str(plan), '--output', str(work / 'result'), '--work-dir', str(work / 'run'))]
        for index, arguments in enumerate(commands):
            completed = subprocess.run([sys.executable, '-B', '-m', 'chronaxis', *arguments], cwd=ROOT,
                env=environment, capture_output=True, text=True, encoding='utf-8', timeout=60)
            (work / f'command-{index}.json').write_text(json.dumps(dict(device_label='home',
                returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr), ensure_ascii=False), encoding='utf-8')
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertEqual((work / 'plan.original.ini').read_bytes(), original.read_bytes())
        report = json.loads((work / 'plan.migration-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['device_label'], 'home')
        self.assertEqual(report['status'], 'success')


def _current_mapping(mapping):
    """把共享旧夹具声明转换为当前公开结构；不改变原INI、数值或业务断言。"""
    from chronaxis.planning.config_groups import public_configuration
    mapping['analysis']=public_configuration(mapping['analysis'])
    return mapping
