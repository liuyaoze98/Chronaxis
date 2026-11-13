"""验证运行元数据在创建时取得本份软件版本，显式历史版本保持。

版本夹具只改本次临时目录中的pyproject，不修改真实发行版本或模拟热更新代码。
"""
from dataclasses import replace
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest
from unittest.mock import patch
from chronaxis import _version
from chronaxis.results.manifest import RunMetadata


class MetadataFactoryTests(unittest.TestCase):
    """通过版本函数实际读取的路径检验工厂时机，不替换被捕获函数对象。"""

    def metadata(self, **kwargs):
        """创建最小元数据。参数: 可选显式字段。返回: RunMetadata。异常: 原模型或版本错误。"""
        return RunMetadata('run', None, 'plan', 'reference', 4, 'relative', (),
                           '2026-11-11T00:00:00+08:00', **kwargs)

    def test_each_instance_reads_current_source_and_keeps_previous_instance(self):
        """先后创建使用7.2和7.3，旧对象与显式历史不变。参数: 无。返回: None。异常: 断言。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'src/chronaxis'
            package.mkdir(parents=True)
            project = root / 'pyproject.toml'
            with patch.object(_version, '__file__', str(package / '_version.py')):
                project.write_text('[project]\nname="chronaxis"\nversion="7.2.0"\n', encoding='utf8')
                first = self.metadata()
                project.write_text('[project]\nname="chronaxis"\nversion="7.3.0"\n', encoding='utf8')
                second = self.metadata()
                historical = self.metadata(software_version='0.0.1')
            for value, expected in [(first,'7.2.0'),(second,'7.3.0'),(historical,'0.0.1')]:
                self.assertEqual(value.software_version, expected)
                self.assertEqual(value.to_dict()['software_version'], expected)
                self.assertEqual(replace(value,detailed_diagnostics=True).to_dict()['software_version'], expected)

    def test_invalid_current_version_fails_only_for_requested_default(self):
        """错误版本资料不影响显式历史值。参数: 无。返回: None。异常: 预期RuntimeError或断言。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'src/chronaxis'
            package.mkdir(parents=True)
            (root / 'pyproject.toml').write_text('[project]\nname="chronaxis"\nversion=""\n',encoding='utf8')
            with patch.object(_version, '__file__', str(package / '_version.py')):
                with self.assertRaises(RuntimeError):
                    self.metadata()
                explicit = self.metadata(software_version='0.0.1')
            self.assertEqual(explicit.software_version,'0.0.1')


if __name__ == '__main__':
    unittest.main()
