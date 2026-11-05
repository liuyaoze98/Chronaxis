"""当前配置工具不宣传或接收旧INI包装，同时保留分析与批量各自的版本。

真实CLI帮助及旧输入拒绝路径用于防止当前说明与执行入口再次分离。
当前配置的转换、展开和来源追踪语义由对应专项测试继续覆盖。
"""
import json
import unittest

from chronaxis.configuration.file_tools import convert_configuration
from chronaxis.configuration.origins import configuration_origins
from chronaxis.configuration.resolution import resolve_configuration
from chronaxis.planning.checks import PlanValidationError
import test_configuration_init as init_cases


class CurrentConfigurationToolTests(unittest.TestCase):
    """用真实帮助和非法根配置检查公开入口，不依赖内部死分支的文本形状。"""

    setUp = init_cases.ConfigurationInitTests.setUp
    command = init_cases.ConfigurationInitTests.command

    def test_cli_help_advertises_only_current_analysis_and_batch(self):
        """三份实际CLI帮助只介绍当前两种入口。参数：无。返回：无。异常：断言。"""
        for name in ('convert', 'resolve', 'origins'):
            with self.subTest(command=name):
                result = self.command('config', name, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('当前分析或批量配置', result.stdout)
                self.assertNotIn('INI', result.stdout)

    def test_unsupported_roots_fail_before_imports_or_output(self):
        """旧包装、旧版本及混合版本在加载不存在的导入或发布文件前拒绝。"""
        for index, raw in enumerate((
            {'mapping_version': 1, 'analysis': {'config_version': 4, 'imports': ['missing.json']}},
            {'config_version': 3, 'imports': ['missing.json']},
            {'config_version': 4, 'batch_version': 1},
        )):
            source = self.root / f'unsupported-{index}.json'
            source.write_text(json.dumps(raw), encoding='utf8')
            before = source.read_bytes()
            target = self.root / f'never-{index}.yaml'
            operations = (
                lambda: convert_configuration(source, target),
                lambda: resolve_configuration(source, output=target),
                lambda: configuration_origins(source),
                lambda: configuration_origins(source, fields=True),
            )
            for operation in operations:
                with self.subTest(input=index, operation=operation):
                    with self.assertRaises(PlanValidationError) as error:
                        operation()
                    self.assertEqual(error.exception.code, 'invalid_version')
                    self.assertFalse(target.exists())
                    self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
