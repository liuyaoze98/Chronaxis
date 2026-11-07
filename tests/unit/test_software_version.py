"""核对软件版本来自本份源码或构建包，以及既有运行元数据序列化。

临时目录模拟源码、已安装包和环境中的旧发行元数据；隔离子解释器仅读取这些
明确输入。不修改真实版本、历史结果或Python安装，失败保留标准unittest诊断。
"""

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
import unittest

from chronaxis._version import software_version
from chronaxis.results.manifest import RunMetadata


ROOT = Path(__file__).resolve().parents[2]
VERSION_SOURCE = ROOT / 'src/chronaxis/_version.py'


class SoftwareVersionTests(unittest.TestCase):
    """独立进程避免模块缓存掩盖源码、安装和缺失资料的来源选择。"""

    def package(self, directory: Path, *, source: bool) -> Path:
        """在临时目录复制被测模块和空根包，返回可加入sys.path的目录。"""
        parent = directory / ('src' if source else 'site-packages')
        package = parent / 'chronaxis'
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('', encoding='utf8')
        shutil.copyfile(VERSION_SOURCE, package / '_version.py')
        return parent

    def probe(self, parent: Path, cwd: Path, *, failure: bool = False) -> dict:
        """从隔离且禁用site的解释器导入被测包；返回JSON，非预期退出使测试失败。"""
        code = '''
import importlib.metadata, json, sys
sys.path.insert(0, sys.argv[1])
from chronaxis._version import software_version
try:
    value = software_version()
except RuntimeError as error:
    print(json.dumps({'error': str(error)}))
    sys.exit(2)
print(json.dumps({'version': value, 'module': sys.modules['chronaxis._version'].__file__}))
'''
        process = subprocess.run([sys.executable, '-X', 'utf8', '-I', '-S', '-B', '-c',
                                  code, str(parent)], cwd=cwd, capture_output=True, text=True,
                                 encoding='utf8')
        self.assertEqual(process.returncode, 2 if failure else 0, process.stderr)
        return json.loads(process.stdout)

    def test_source_and_metadata_use_current_project_version(self):
        """源码默认及两种清单序列化都跟随pyproject，显式历史版本仍被保留。"""
        expected = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf8'))['project']['version']
        self.assertEqual(software_version(), expected)
        metadata = RunMetadata('version-check', None, 'plan-check', 'reference', 4,
                               'relative', (), '2026-11-07T00:00:00+08:00')
        for value in (metadata, replace(metadata, detailed_diagnostics=True)):
            self.assertEqual(value.software_version, expected)
            self.assertEqual(value.to_dict()['software_version'], expected)
        historical = replace(metadata, software_version='0.0.1')
        self.assertEqual(historical.to_dict()['software_version'], '0.0.1')

    def test_source_ignores_environment_distribution_and_stale_build_file(self):
        """本源码项目优先于旧安装元数据及误留的构建文件，不从当前工作目录猜版本。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.package(root / 'checkout', source=True)
            project = parent.parent / 'pyproject.toml'
            project.write_text('[project]\nname="chronaxis"\nversion="7.2.0.dev9"\n', encoding='utf8')
            (parent / 'chronaxis/_build_version.py').write_text('VERSION="0.0.1"\n', encoding='utf8')
            old = parent / 'chronaxis-0.0.1.dist-info'
            old.mkdir()
            (old / 'METADATA').write_text('Metadata-Version: 2.1\nName: chronaxis\nVersion: 0.0.1\n', encoding='utf8')
            self.assertEqual(self.probe(parent, root)['version'], '7.2.0.dev9')

    def test_installed_copy_uses_built_version_without_repository(self):
        """安装包不含pyproject，仍使用自身构建信息；外部同名项目不影响结果。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.package(root / 'environment', source=False)
            (parent / 'chronaxis/_build_version.py').write_text('VERSION="6.4.0.dev8"\n', encoding='utf8')
            (root / 'pyproject.toml').write_text('[project]\nname="chronaxis"\nversion="0.0.2"\n', encoding='utf8')
            self.assertEqual(self.probe(parent, root)['version'], '6.4.0.dev8')

    def test_source_missing_wrong_or_empty_version_is_not_guessed(self):
        """源码资料缺失、项目错误或版本无效时明确失败，不猜测默认版本。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.package(root, source=True)
            self.assertIn('error', self.probe(parent, root, failure=True))
            project = root / 'pyproject.toml'
            for text in ('[project]\nname="other"\nversion="1"\n',
                         '[project]\nname="chronaxis"\nversion=""\n',
                         '[project]\nname="chronaxis"\nversion=1\n'):
                with self.subTest(project=text):
                    project.write_text(text, encoding='utf8')
                    self.assertIn('error', self.probe(parent, root, failure=True))

    def test_unbuilt_package_copy_cannot_borrow_another_installed_version(self):
        """缺构建信息的复制品必须失败，环境中的同名发行元数据不能代替本包事实。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.package(root, source=False)
            old = parent / 'chronaxis-0.0.1.dist-info'
            old.mkdir()
            (old / 'METADATA').write_text('Metadata-Version: 2.1\nName: chronaxis\nVersion: 0.0.1\n', encoding='utf8')
            self.assertIn('构建版本', self.probe(parent, root, failure=True)['error'])

    def test_installed_target_named_src_does_not_require_repository(self):
        """安装目标恰好名为src时，包内生成版本仍有效，不要求额外项目根文件。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.package(root, source=True)
            (parent / 'chronaxis/_build_version.py').write_text('VERSION="6.4.0"\n', encoding='utf8')
            self.assertEqual(self.probe(parent, root)['version'], '6.4.0')


if __name__ == '__main__':
    unittest.main()
