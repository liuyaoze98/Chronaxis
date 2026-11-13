"""验证AI重锁生成的源码清单保留本版说明和精确依赖快照，不收集旁路文件。"""
from io import BytesIO
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]


class ReleaseResources(unittest.TestCase):
    """以极小的受控Git响应运行真实清单生成函数，不读取私有历史。"""

    def test_relocking_keeps_only_reviewed_constraints_and_current_release_notes(self):
        """重锁不会丢失约束快照，也不会扩大为整个目录的分发。

        参数: 无。返回: None。异常: 清单缺项、重复项或额外私有文件使断言失败。
        """
        spec = importlib.util.spec_from_file_location('release_resource_lock', ROOT/'tools/lock_ai_inputs.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        version = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
        archive = BytesIO()
        with ZipFile(archive, 'w') as stream:
            stream.writestr('src/chronaxis/__init__.py', '"""测试用冻结运行树。"""\n')

        def frozen_git(*args):
            """提供真实lock流程所需的最小Git事实。参数: Git命令。返回: bytes。异常: 未列命令失败。"""
            if args[0] == 'rev-parse':
                return b'1111111111111111111111111111111111111111\n'
            if args[0] == 'ls-tree':
                return b''
            if args[0] == 'archive':
                return archive.getvalue()
            if args[0] == 'show':
                path = args[1].partition(':')[2]
                if path == 'Docs/Current/documentation.json':
                    return b'{"baseline":"2222222222222222222222222222222222222222"}'
                if path == 'pyproject.toml':
                    return ('[project]\nversion = '+json.dumps(version)+'\n').encode()
                return b'{}'
            raise AssertionError(args)

        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target/'Docs/AI').mkdir(parents=True)
            (target/'Docs/AI/tasks.json').write_text('{"tasks":[]}', encoding='utf-8')
            (target/'requirements').mkdir()
            (target/'requirements/private.txt').write_text('not for distribution', encoding='utf-8')
            (target/'MANIFEST.in').write_text('include requirements/private.txt\n', encoding='utf-8')
            with patch.object(module, 'ROOT', target), patch.object(module, 'git', side_effect=frozen_git):
                module.lock('manual', 'runtime', 'home')
            lines = (target/'MANIFEST.in').read_text(encoding='utf-8').splitlines()
            self.assertEqual(len(lines), len(set(lines)))
            actual = {line.removeprefix('include ') for line in lines if line.startswith('include requirements/')}
            self.assertEqual(actual, {'requirements/README.md',
                'requirements/constraints-windows-py312-min.txt', 'requirements/constraints-windows-py312-max.txt',
                'requirements/constraints-windows-py313-min.txt', 'requirements/constraints-windows-py313-max.txt'})
            for suffix in ('.md', '.en.md'):
                self.assertIn('include Docs/Release/release-notes-'+version+suffix, lines)
            installed_lock = json.loads((target/'Docs/AI/inputs.lock.json').read_text(encoding='utf-8'))
            self.assertEqual(installed_lock['package_version'], version)


if __name__ == '__main__':
    unittest.main()
