"""通过真实子进程检查最小legacy import命令及三个文件的公开发布合同。

输入为本测试在work新建的INI原bytes和显式mapping文件；Sclicer映射复用既有
mapping_fixture函数，不继承其TestCase。子进程使用当前正式Python、继承项目
PYTHONPATH并加-B，cwd固定仓库根；这里不安装包、不读数据/DBC、不运行分析流。

成功断言实际计划可由load_analysis_plan回读、来源仍按mapping目录定位、原bytes和报告
匹配摘要。失败区分参数/配置与I/O，检查整份失败不发布计划、既有目标和Ref
均不被改写。每次命令的stdout/stderr/退出码保存在独立work证据目录，不删除
失败材料。脚本入口只核pyproject声明，不假称已安装console script或跨平台验收。
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest
from uuid import uuid4

import test_legacy_import_sclicer as fixtures
from chronaxis import load_analysis_plan


ROOT = Path(__file__).absolute().parents[2]


class LegacyImportCLITests(unittest.TestCase):
    """使用实际CLI和真实配置文件，所有产物留在当前测试的专用work目录。"""

    def setUp(self):
        """建立独立输入、输出与命令日志目录，不创建任何真实来源数据。

        参数: 无。返回: None。异常: 原文件系统错误；不吞掉准备失败。
        """
        self.work = ROOT / 'work' / 'm2-import-tests' / 'cli' / uuid4().hex
        self.inputs = self.work / 'mapping-directory'
        self.inputs.mkdir(parents=True)
        self.ini, self.mapping = self.inputs / 'original.ini', self.inputs / 'mapping.json'
        self.output = self.work / 'different-output-directory' / 'migrated.json'
        self.log_index = 0

    def prepare(self, content, *, mapping=None):
        """写两个实际输入配置，保留给子进程与后续bytes核对。

        参数: content为原INI bytes；mapping为可选完整原生字典。
        返回: (INI原bytes, mapping文件原bytes)。异常: 原编码/写入错误。
        """
        self.ini.write_bytes(content)
        encoded = json.dumps(fixtures.mapping_fixture() if mapping is None else mapping,
            ensure_ascii=False).encode('utf-8')
        self.mapping.write_bytes(encoded)
        return content, encoded

    def invoke(self, arguments, *, device_label='home', script=None):
        """真正执行python -B -m chronaxis，并保存本次有限命令结果。

        参数: arguments为CLI参数序列；device_label为子环境显式标签，None表示删除；
            script仅供取消例调用真实main并包实际文件读取，其余一律-m公开入口。
        返回: CompletedProcess，包含原stdout/stderr/退出码。
        异常: 真实启动/超时/UTF8错误原样传播，不把非零退出自动当测试成功。
        """
        environment = os.environ.copy()
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        environment['PYTHONIOENCODING'] = 'utf-8'
        # 继承根正式PYTHONPATH，不把测试环境的依赖伪装成全局安装；设备来自显式env。
        if device_label is None:
            environment.pop('CHRONAXIS_DEVICE_LABEL', None)
        else:
            environment['CHRONAXIS_DEVICE_LABEL'] = device_label
        command = [sys.executable, '-B']
        command += ['-m', 'chronaxis'] if script is None else ['-c', script]
        command += list(map(str, arguments))
        completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
            text=True, encoding='utf-8', errors='strict', timeout=60)
        self.log_index += 1
        (self.work / ('command-' + str(self.log_index) + '.json')).write_text(json.dumps({
            'device_label': 'home', 'cwd': str(ROOT), 'command': command,
            'requested_device_label': device_label, 'returncode': completed.returncode,
            'stdout': completed.stdout, 'stderr': completed.stderr}, ensure_ascii=False, indent=2), encoding='utf-8')
        return completed

    def import_command(self, *, mode='sclicer_single', output=None, ini=None, mapping=None):
        """构造公开import实参而不调用产品。参数: 可选mode/路径。返回: list。异常: 无。"""
        return ['legacy', 'import', self.ini if ini is None else ini, '--mode', mode,
            '--mapping', self.mapping if mapping is None else mapping,
            '--output', self.output if output is None else output]

    def published_paths(self, output=None):
        """按公开命名计算三个目标。参数: 可选.json路径。返回: 三Path tuple。异常: 无。"""
        plan = self.output if output is None else output
        return plan, plan.with_suffix('.original.ini'), plan.with_suffix('.migration-report.json')

    def summary(self, completed, *, status, original, device_label='home'):
        """核实际stdout有限摘要与原/报告文件一致，不仅检查退出码。

        参数: completed为真实命令结果；status为预期状态；original为原INI bytes；
            device_label为显式输入标签。返回: (摘要dict, 回读报告dict)。
        异常: AssertionError/JSON或文件错误；缺失产物不能用空默认值掩盖。
        """
        self.assertEqual(len(completed.stdout.strip().splitlines()), 1, completed.stdout)
        value = json.loads(completed.stdout)
        self.assertEqual(set(value), {'status', 'plan', 'original', 'report', 'device_label',
            'issue_count', 'error_count', 'warning_count'})
        self.assertEqual((value['status'], value['device_label']), (status, device_label))
        plan, preserved, report = self.published_paths()
        self.assertEqual((value['original'], value['report']), (str(preserved), str(report)))
        self.assertTrue(Path(value['original']).is_absolute())
        self.assertTrue(Path(value['report']).is_absolute())
        self.assertEqual(preserved.read_bytes(), original)
        payload = json.loads(report.read_text(encoding='utf-8'))
        self.assertEqual((payload['status'], payload['device_label']), (status, device_label))
        self.assertEqual(payload['source_sha256'], hashlib.sha256(original).hexdigest())
        levels = tuple(item['level'] for item in payload['issues'])
        self.assertEqual(value['issue_count'], len(levels))
        self.assertEqual(value['error_count'], levels.count('error'))
        self.assertEqual(value['warning_count'], levels.count('warning'))
        self.assertTrue(all(type(value[key]) is int for key in ('issue_count', 'error_count', 'warning_count')))
        # 摘要只给路径/计数；完整fields/issues应在已实际发布的报告中。
        self.assertNotIn('fields', value)
        self.assertNotIn('issues', value)
        if status == 'success':
            self.assertEqual(value['plan'], str(plan))
            self.assertTrue(Path(value['plan']).is_absolute())
            self.assertTrue(plan.is_file())
        else:
            self.assertIsNone(value['plan'])
            self.assertIsNone(payload['plan_identity'])
            self.assertFalse(plan.exists())
        return value, payload

    def test_single_bom_crlf_preserves_original_and_mapping_base_after_relocation(self):
        """BOM/CRLF原字节不改，输出目录改变后计划来源仍按原mapping目录绝对定位。

        参数: 无。返回: None。异常: CLI状态、路径、真实计划/报告或输入bytes不符即失败。
        """
        original, encoded = self.prepare(b'\xef\xbb\xbf; CLI synthetic original\r\n[TRIGGER_test]\r\n'
            b'mode=single\r\nexpr=OBC_OpMod==2\r\npre_sec=2\r\npost_sec=4\r\n')
        completed = self.invoke(self.import_command())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, '')
        value, report = self.summary(completed, status='success', original=original)
        actual = load_analysis_plan(value['plan'])
        self.assertEqual(actual.identity, report['plan_identity'])
        self.assertEqual(actual.sources[0].config.paths, (self.inputs / 'missing' / 'input.csv',))
        self.assertTrue(actual.sources[0].config.paths[0].is_absolute())
        self.assertFalse(actual.sources[0].config.paths[0].exists())
        self.assertEqual((actual.rules[0].rule_type, actual.windows[0].pre_ns, actual.windows[0].exit_delay_ns),
            ('condition_duration', 2_000_000_000, 4_000_000_000))
        self.assertEqual((self.ini.read_bytes(), self.mapping.read_bytes()), (original, encoded))

    def test_start_only_ascii_uses_explicit_duration_and_pending_when_label_absent(self):
        """ASCII start_only可直接load_analysis_plan；未设置设备env时保持pending，不从当前机器猜标签。

        参数: 无。返回: None。异常: 真实计划默认/显式字段或设备来源不符即失败。
        """
        original, _ = self.prepare(b'[TRIGGER_test]\nmode=start_only\nstart_expr=OBC_OpMod==2\n'
            b'duration_sec=4\npost_sec=99\n')
        completed = self.invoke(self.import_command(mode='sclicer_start_only'), device_label=None)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value, report = self.summary(completed, status='success', original=original, device_label='pending')
        actual = load_analysis_plan(value['plan'])
        self.assertEqual((actual.rules[0].rule_type, actual.rules[0].window_duration_ns,
            actual.rules[0].emit_initial, actual.windows[0].post_ns), ('start_only', 4_000_000_000, True, 4_000_000_000))
        self.assertEqual(actual.identity, report['plan_identity'])

    def test_legacy_sum_disjunction_creates_two_typed_calculations_without_data_io(self):
        """B2冻结助手提供真实配置，CLI生成正负两指标并保原点号方向字段，不读取BLF/DBC。

        参数: 无。返回: None。异常: 两指标ID/策略/单位/原绑定或迁移计划回读不符即失败。
        边界: 本例只验证公开转换与发布，实际手算运行由C2另验，不把静态成功当数值通过。
        """
        import test_legacy_import_sum as legacy_fixtures
        mapping = legacy_fixtures.legacy_mapping_fixture(disjunction=True)
        original, _ = self.prepare(legacy_fixtures.legacy_ini(disjunction=True), mapping=mapping)
        completed = self.invoke(self.import_command(mode='legacy_sum'))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value, report = self.summary(completed, status='success', original=original)
        actual = load_analysis_plan(value['plan'])
        prefix = mapping['sections']['integral_energy']['name']
        self.assertEqual(tuple(item.calculation_id for item in actual.message_calculations),
            (prefix + '_positive', prefix + '_negative'))
        self.assertEqual(tuple(item.disjunction.bucket for item in actual.message_calculations), ('positive', 'negative'))
        for calculation in actual.message_calculations:
            self.assertEqual((calculation.message_policy, calculation.disjunction.signal, calculation.disjunction.value_policy),
                ('current_message-v1', 'direction', 'raw_decoded-v1'))
            self.assertEqual(calculation.unit, 'J')
            self.assertEqual(next(item.value for item in calculation.parameters if item.name == 'period'), 0.1)
        definition = actual.bindings.resolve('direction')
        self.assertEqual(json.loads(definition.field)['signal'], 'Direction.raw')
        self.assertEqual(actual.sources[0].source_type, 'can_blf')
        original_path = Path(mapping['analysis']['sources'][0]['path'])
        expected_path = original_path if original_path.is_absolute() else self.inputs / original_path
        self.assertEqual(actual.sources[0].config.path, expected_path)
        self.assertFalse(actual.sources[0].config.path.exists())
        self.assertEqual(actual.identity, report['plan_identity'])

    def test_conversion_failure_publishes_original_and_report_without_partial_plan(self):
        """一个合法段加一个不支持字段必须整份失败，只保原文及定位报告，不能产部分计划。

        参数: 无。返回: None。异常: 退出码、文件集合或首条错误诊断不符即失败。
        """
        original, _ = self.prepare(b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\nunsupported=1\n')
        completed = self.invoke(self.import_command())
        self.assertEqual(completed.returncode, 2)
        value, report = self.summary(completed, status='failed', original=original)
        errors = tuple(item for item in report['issues'] if item['level'] == 'error')
        self.assertGreater(value['error_count'], 0)
        self.assertEqual((errors[0]['code'], errors[0]['line']), ('unknown_option', 4))
        self.assertTrue(completed.stderr.strip())
        self.assertLess(len(completed.stderr), 8192)
        self.assertEqual(set(self.output.parent.iterdir()), set(self.published_paths()[1:]))

    def test_invalid_mapping_json_has_diagnostic_sidecars_and_no_plan(self):
        """JSON配置损坏是整份配置失败；真实原INI和报告仍可读，退出2且计划不存在。

        参数: 无。返回: None。异常: 非零分类、诊断或原bytes丢失即失败。
        """
        original, _ = self.prepare(b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n')
        self.mapping.write_bytes(b'{"mapping_version": 1, invalid}')
        completed = self.invoke(self.import_command())
        self.assertEqual(completed.returncode, 2)
        _, report = self.summary(completed, status='failed', original=original)
        self.assertIn('invalid_mapping_json', {item['code'] for item in report['issues']})
        self.assertTrue(completed.stderr.strip())

    def test_existing_any_target_is_preserved_without_new_sidecars(self):
        """plan/原文/报告任一目标已存在均整拒，不覆盖sentinel或偷写另外两个产物。

        参数: 无。返回: None。异常: 保留文件、真实错误类别或目录内容改变即失败。
        """
        self.prepare(b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n')
        for index in range(3):
            with self.subTest(target=index):
                output = self.work / ('existing-' + str(index)) / 'migrated.json'
                output.parent.mkdir()
                targets = self.published_paths(output)
                sentinel = b'preexisting bytes must stay unchanged\x00\r\n'
                targets[index].write_bytes(sentinel)
                completed = self.invoke(self.import_command(output=output))
                self.assertEqual(completed.returncode, 1)
                self.assertTrue(completed.stderr.strip())
                self.assertEqual(targets[index].read_bytes(), sentinel)
                self.assertEqual(set(output.parent.iterdir()), {targets[index]})

    def test_help_unknown_commands_modes_and_missing_arguments_are_argparse_only(self):
        """帮助退出0，未知命令/mode或缺必需参数退出2；不存在的输入不得被先读取。

        参数: 无。返回: None。异常: 退出码/usage不符或产生输出即失败。
        """
        for arguments in (['--help'], ['legacy', '--help'], ['legacy', 'import', '--help']):
            with self.subTest(arguments=arguments):
                completed = self.invoke(arguments)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn('usage:', completed.stdout.lower())
                self.assertEqual(completed.stderr, '')
        complete = self.import_command()
        cases = (['unknown-command'], ['legacy', 'unknown-command'],
            ['legacy', 'import', self.ini],
            [*complete[:3], '--mode', 'unsupported', '--mapping', self.mapping, '--output', self.output],
            [*complete[:5], '--output', self.output], [*complete[:7]], [*complete, '--unknown-option'])
        for arguments in cases:
            with self.subTest(arguments=arguments):
                completed = self.invoke(arguments)
                self.assertEqual(completed.returncode, 2)
                self.assertIn('usage:', completed.stderr.lower())
                self.assertEqual(completed.stdout, '')
        self.assertFalse(self.output.parent.exists())
        self.assertFalse(self.ini.exists())
        self.assertFalse(self.mapping.exists())

    def test_missing_input_or_mapping_is_io_error_without_publication(self):
        """真实缺文件返回1并保短路径错误，不生成原文/报告或伪成功计划。

        参数: 无。返回: None。异常: I/O分类、路径诊断或意外产物即失败。
        """
        self.prepare(b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n')
        for field in ('ini', 'mapping'):
            with self.subTest(field=field):
                missing = self.inputs / ('missing-' + field + '.json')
                completed = self.invoke(self.import_command(**{field: missing}))
                self.assertEqual(completed.returncode, 1)
                self.assertIn(missing.name, completed.stderr)
                self.assertLess(len(completed.stderr), 8192)
                self.assertEqual(completed.stdout, '')
                self.assertTrue(all(not path.exists() for path in self.published_paths()))

    def test_non_json_output_and_ref_directory_are_rejected_before_creation(self):
        """非法扩展和合成Ref子路径先拒绝；不依赖仓库历史资料。

        参数: 无。返回: None。异常: 路径防护、目录不变或错误分类不符即失败。
        """
        self.prepare(b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n')
        bad = self.work / 'invalid-suffix' / 'migrated.txt'
        completed = self.invoke(self.import_command(output=bad))
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(completed.stderr.strip())
        self.assertFalse(bad.parent.exists())
        # 在本测试工作目录模拟受保护名称，不读写仓库真实历史目录。
        ref = self.work / 'RefProjects'
        ref.mkdir()
        rejected_root = ref / ('chronaxis-cli-rejected-' + uuid4().hex)
        self.assertFalse(rejected_root.exists())
        before = ref.stat().st_mtime_ns
        completed = self.invoke(self.import_command(output=rejected_root / 'migrated.json'))
        self.assertEqual(completed.returncode, 2)
        self.assertIn('RefProjects', completed.stderr)
        self.assertFalse(rejected_root.exists())
        self.assertEqual(ref.stat().st_mtime_ns, before)

    def test_cancel_after_actual_ini_read_returns_130_without_publication(self):
        """真实main读完原INI后遇取消，子进程退出130且不留下计划或sidecar。

        参数: 无。返回: None。异常: 取消分类、原文件读到事实或未发布边界不符即失败。
        边界: 仅包新入口的实际Path.read_bytes；不模拟writer恢复或宣称测试了旧CAN取消。
        """
        original, _ = self.prepare(b'[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n')
        script = '''"""在真实INI读取完成且FD已关闭后取消，调用公开CLI main核退出分类。"""
from pathlib import Path
import sys
from unittest.mock import patch
from chronaxis.cli import main

target = Path(sys.argv[1]).absolute()
read = Path.read_bytes

def interrupted(path):
    """参数: 实际Path；返回: 原bytes；异常: 目标真实读完后KeyboardInterrupt。"""
    payload = None
    try:
        payload = read(path)
        if path.absolute() == target:
            # 标记证明取消在原真实read之后；FD已由原read_bytes上下文结束。
            print('actual_ini_read_then_cancel', file=sys.stderr)
            raise KeyboardInterrupt('controlled CLI read cancellation')
        return payload
    finally:
        payload = None

with patch.object(Path, 'read_bytes', new=interrupted):
    raise SystemExit(main(sys.argv[2:]))
'''
        completed = self.invoke([self.ini, *self.import_command()], script=script)
        self.assertEqual(completed.returncode, 130)
        self.assertIn('actual_ini_read_then_cancel', completed.stderr)
        self.assertIn('取消', completed.stderr)
        self.assertEqual(completed.stdout, '')
        self.assertTrue(all(not path.exists() for path in self.published_paths()))
        self.assertEqual(self.ini.read_bytes(), original)

    def test_pyproject_declares_public_console_entry_without_installing(self):
        """静态核console script指向同一main，不安装包或声称全局命令已可用。

        参数: 无。返回: None。异常: TOML读取或公开entry声明不符即失败。
        """
        configuration = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        self.assertEqual(configuration['project']['scripts']['chronaxis'], 'chronaxis.cli:main')


if __name__ == '__main__':
    # 本文件导入只声明测试；实际CLI子进程由根统一显式unittest执行。
    unittest.main()
