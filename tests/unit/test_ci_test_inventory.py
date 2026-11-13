"""检查公开CI测试分组不会遗漏新文件，并随公开源码发布真正可用的验收入口。

只在自动清理的合成目录枚举空测试文件，不运行产品或联网。正式工作流的环境、
运行分组和独立安装验收分别核对；内部性能测试排除沿用公开导出已有清单。
"""

from pathlib import Path
from runpy import run_path
import sys
import unittest
from unittest.mock import patch

from ruamel.yaml import YAML
from workspace_fixtures import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
with patch.object(sys, 'path', [str(ROOT / 'tools'), *sys.path]):
    HELPERS = run_path(str(ROOT / 'tools/run_ci_tests.py'))


class CITestInventoryTests(unittest.TestCase):
    """用独立目录覆盖新增、嵌套和内部测试，防止手工分组导致假绿。"""

    def test_every_public_module_is_assigned_once_including_new_names(self):
        """参数: 无。返回: None。异常: 断言失败；未知新测试自动进入core且不丢嵌套模块。"""
        with TemporaryDirectory(prefix='ci-inventory-') as directory:
            root = Path(directory)
            files = ('tests/unit/test_new_feature.py', 'tests/unit/nested/test_new_operator.py',
                     'tests/unit/test_signal_csv.py', 'tests/unit/test_manual_behavior.py',
                     'tests/unit/test_software_version.py', 'tests/unit/test_asc_repository.py',
                     'tools/test_current_html.py', 'tools/test_not_public.py')
            for name in files:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('', encoding='utf-8')
            groups, excluded = HELPERS['inventory'](root)
            self.assertEqual(groups['core'], ['nested.test_new_operator', 'test_new_feature'])
            self.assertEqual(groups['input'], ['test_signal_csv'])
            self.assertEqual(groups['docs'], ['test_manual_behavior', 'test_current_html'])
            self.assertEqual(groups['install'], ['test_software_version'])
            self.assertEqual(excluded, ['tests/unit/test_asc_repository.py'])

    def test_real_public_unit_inventory_is_complete(self):
        """参数: 无。返回: None。异常: 断言失败；真实所有公开unit各有唯一执行位置。"""
        groups, excluded = HELPERS['inventory'](ROOT)
        assigned = [name for names in groups.values() for name in names]
        expected = {'.'.join(path.relative_to(ROOT / 'tests/unit').with_suffix('').parts)
                    for path in (ROOT / 'tests/unit').rglob('test_*.py')
                    if path.name not in HELPERS['EXCLUDED_TESTS']}
        self.assertTrue(expected <= set(assigned))
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual({Path(path).name for path in excluded},
                         {path.name for path in (ROOT / 'tests/unit').rglob('test_*.py')
                          if path.name in HELPERS['EXCLUDED_TESTS']})

    def test_public_source_includes_ci_and_keeps_internal_exclusions(self):
        """参数: 无。返回: None。异常: 断言失败；公开源码要携带CI脚本，不能泄露私有性能输入。"""
        included = HELPERS['included']
        for path in ('.github/workflows/verify.yml', 'tools/run_ci_tests.py',
                     'tools/check_ai_install.py', 'tests/unit/workspace_fixtures.py'):
            self.assertTrue(included(path), path)
        for name in HELPERS['EXCLUDED_TESTS']:
            self.assertFalse(included('tests/unit/' + name), name)

    def test_workflow_runs_all_groups_and_keeps_documentation_checks_strict(self):
        """参数: 无。返回: None。异常: 断言失败；分组、工具版本和安装验收均有实际执行命令。"""
        source = (ROOT / '.github/workflows/verify.yml').read_text(encoding='utf-8')
        workflow = YAML(typ='safe').load(source)
        self.assertTrue({'push', 'pull_request'} <= set(workflow['on']))
        self.assertEqual(workflow['env']['CHRONAXIS_DOC_SOURCE_TREE'], '1')
        self.assertEqual(workflow['env']['CHRONAXIS_DEVICE_LABEL'], 'ci')
        self.assertEqual(workflow['jobs']['unit']['strategy']['matrix']['group'], ['core', 'input'])
        for group in ('docs', 'install'):
            self.assertIn('--group ' + group, source)
        for job in workflow['jobs'].values():
            self.assertEqual(job['runs-on'], 'windows-2022')
        for required in ('marked@17.0.5', 'highlight.js@11.11.1', 'pip install -e ".[test]"',
                         'check_ai_install.py', 'build --sdist', '--no-build-isolation'):
            self.assertIn(required, source)
        self.assertNotIn('verify_runtime=False', source)


if __name__ == '__main__':
    unittest.main()
