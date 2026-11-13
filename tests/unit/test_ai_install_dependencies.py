"""核对离线安装验收使用实际依赖目录，并精确检查复制后的版本。

最小发行元数据只用于测试读取规则，不冒充安装兼容性验收；不联网、不创建venv。
目标检查直接执行工具传给隔离解释器的原脚本，最低与较新合法组合均须能通过。
"""
from contextlib import redirect_stdout
from importlib import metadata
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from check_ai_install import CAN_VERSION_CHECK, check, dependency_can_versions


class ReachedGuideLookup(RuntimeError):
    """测试专用停止点：路径隔离已通过，尚未开始任何任务查询或分析。"""


def installation_path_probe(root, *, outside=False, wrong_english=False):
    """在真实临时目录运行安装检查的路径分支，安装子进程由受控结果代替。

    参数: 临时根目录及两种越界场景。返回: 无；通过路径检查后抛ReachedGuideLookup。
    使用含..的实际可访问别名模拟短名与真实目录拼写不同，适用于Windows及其他平台。
    异常: 保留生产检查的AssertionError，不把隔离失败转换成成功。
    """
    root = root.resolve()
    area = root/'installation'
    area.mkdir()
    (root/'alias-segment').mkdir()
    alias = root/'alias-segment'/'..'/'installation'
    site = area/'runtime/Lib/site-packages'
    site.mkdir(parents=True)
    guide = (root/'outside' if outside else site)/'chronaxis/guide'
    (guide/'en').mkdir(parents=True)
    (guide/'README.md').write_text('guide', encoding='utf-8')
    (guide/'en/README.md').write_text('English guide', encoding='utf-8')
    (guide/'manifest.json').write_text('{"package_version":"0.1.0.dev4"}', encoding='utf-8')
    wheel, archive, report = root/'candidate.whl', root/'guide.zip', root/'report.json'
    wheel.write_bytes(b'wheel fixture')
    archive.write_bytes(b'guide fixture')
    versions = {'python-can':'4.6.1', 'cantools':'45.1.2', 'natsort':'8.4.0'}

    def command(argv, **kwargs):
        """返回安装步骤的受控结果，仅真实执行被测工具的目录和文件检查。

        参数: 子进程命令及调用选项。返回: 退出码、标准输出及错误输出的替代结果。
        异常: ReachedGuideLookup标记路径检查已通过；临时文件I/O错误原样传播。
        """
        argv = list(map(str, argv))
        output = ''
        if '-c' in argv:
            code = argv[argv.index('-c')+1]
            if "sysconfig.get_path('purelib')" in code:
                output = str(alias/'runtime/Lib/site-packages')
            elif code == CAN_VERSION_CHECK:
                output = json.dumps(versions)
            elif 'import chronaxis,pathlib,sys' in code:
                output = str(site/'chronaxis/__init__.py')
            elif 'RunMetadata' in code:
                output = '0.1.0.dev4'
        elif 'guide' in argv:
            if '--output' in argv:
                Path(argv[argv.index('--output')+1]).write_bytes(archive.read_bytes())
            else:
                english = '--language' in argv and not wrong_english
                output = str(guide/('en/README.md' if english else 'README.md'))
        elif any(value.endswith('lookup.py') for value in argv):
            raise ReachedGuideLookup('安装目录隔离和双语入口检查均已通过')
        return SimpleNamespace(returncode=0, stdout=output, stderr='')

    with patch('check_ai_install.tempfile.mkdtemp', return_value=str(alias)), \
            patch('check_ai_install.dependency_can_versions', return_value=versions), \
            patch('check_ai_install.shutil.copytree'), \
            patch('check_ai_install.subprocess.run', side_effect=command):
        check(wheel, archive, root, report, 'ci')


def distribution(directory, folder, name, version):
    """写最小测试元数据。参数: 父目录、元数据目录名、发行名及版本。返回: 无。异常: I/O错误。"""
    target = directory/folder
    target.mkdir()
    text = f'Metadata-Version: 2.1\nName: {name}\n'
    if version is not None:
        text += f'Version: {version}\n'
    (target/'METADATA').write_text(text, encoding='utf-8')


def target_versions(expected, actual):
    """执行实际隔离检查脚本，替代元数据查询以模拟指定目标环境。

    参数: 来源与目标版本映射。返回: 脚本JSON输出。异常: 保留不一致或缺包错误。
    """
    output = StringIO()
    with patch.object(sys, 'argv', ['-c', json.dumps(expected)]), \
            patch.object(metadata, 'version', side_effect=actual.__getitem__), redirect_stdout(output):
        exec(compile(CAN_VERSION_CHECK, '<can-versions>', 'exec'), {})
    return json.loads(output.getvalue())


class AIInstallDependenciesTests(unittest.TestCase):
    """精确复制检查独立于版本允许范围，不把范围符合当成复制一致。"""

    def test_reads_requested_directory_for_minimum_and_newer_cantools(self):
        """参数: 无。返回: None。异常: 指定目录被当前解释器安装状态替代时失败。"""
        for cantools in ('39.4.3', '45.1.2'):
            with self.subTest(cantools=cantools), TemporaryDirectory() as temporary:
                root = Path(temporary)
                expected = {'python-can': '4.6.1', 'cantools': cantools, 'natsort': '8.4.0'}
                for name, version in expected.items():
                    distribution(root, name.replace('-', '_')+'-'+version+'.dist-info', name, version)
                with patch.object(metadata, 'version', side_effect=AssertionError('不应查询当前解释器')):
                    self.assertEqual(dependency_can_versions(root), expected)

    def test_normalizes_distribution_names_without_using_directory_names(self):
        """参数: 无。返回: None。异常: 合法发行名称大小写或下划线形式无法识别时失败。"""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for folder, name, version in (('first.dist-info', 'Python_CAN', '4.6.1'),
                                          ('second.dist-info', 'CanTools', '45.1.2'),
                                          ('third.dist-info', 'natsort', '8.4.0')):
                distribution(root, folder, name, version)
            self.assertEqual(dependency_can_versions(root),
                             {'python-can': '4.6.1', 'cantools': '45.1.2', 'natsort': '8.4.0'})

    def test_missing_directory_or_distribution_is_explicit(self):
        """参数: 无。返回: None。异常: 缺失依赖未报告具体对象时失败。"""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, '依赖目录不存在或不是目录'):
                dependency_can_versions(root/'absent')
            distribution(root, 'cantools.dist-info', 'cantools', '45.1.2')
            with self.assertRaisesRegex(ValueError, 'python-can, natsort'):
                dependency_can_versions(root)

    def test_duplicate_or_missing_version_is_rejected(self):
        """参数: 无。返回: None。异常: 重复发行或空版本被任意选取时失败。"""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            distribution(root, 'a.dist-info', 'python-can', '4.6.1')
            distribution(root, 'b.dist-info', 'Python_CAN', '4.6.1')
            with self.assertRaisesRegex(ValueError, '重复.*python-can'):
                dependency_can_versions(root)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            distribution(root, 'cantools.dist-info', 'cantools', None)
            with self.assertRaisesRegex(ValueError, '缺少版本.*cantools'):
                dependency_can_versions(root)

    def test_target_must_match_exact_selected_versions(self):
        """参数: 无。返回: None。异常: 新合法版本被拒绝或两合法版本的混用未拒绝时失败。"""
        for cantools in ('39.4.3', '45.1.2'):
            expected = {'python-can': '4.6.1', 'cantools': cantools, 'natsort': '8.4.0'}
            self.assertEqual(target_versions(expected, expected), expected)
        expected = {'python-can': '4.6.1', 'cantools': '45.1.2', 'natsort': '8.4.0'}
        with self.assertRaisesRegex(RuntimeError, '来源目录版本不一致'):
            target_versions(expected, dict(expected, cantools='39.4.3'))
        with self.assertRaises(KeyError):
            target_versions(expected, {'python-can': '4.6.1', 'natsort': '8.4.0'})

    def test_invalid_source_is_rejected_before_creating_an_environment(self):
        """参数: 无。返回: None。异常: 缺失源元数据仍创建临时环境时失败。"""
        with TemporaryDirectory() as temporary, patch('check_ai_install.tempfile.mkdtemp') as create:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, '缺少所需发行元数据'):
                check(root/'candidate.whl', root/'guide.zip', root, root/'report.json', 'ci')
            create.assert_not_called()

    def test_equivalent_path_spelling_reaches_guide_lookup(self):
        """参数: 无。返回: None。异常: 同一真实目录因路径拼写差异而误拒绝时失败。"""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ReachedGuideLookup):
                installation_path_probe(root)
            report = json.loads((root/'report.json').read_bytes())
            self.assertEqual(report['directory'], str((root/'installation').resolve()))

    def test_guide_outside_installed_directory_remains_rejected(self):
        """参数: 无。返回: None。异常: 规范路径后把外部指南当安装资源时失败。"""
        with TemporaryDirectory() as temporary:
            with self.assertRaises(AssertionError):
                installation_path_probe(Path(temporary), outside=True)

    def test_wrong_english_entry_remains_rejected(self):
        """参数: 无。返回: None。异常: 中文入口被当作英文README接受时失败。"""
        with TemporaryDirectory() as temporary:
            with self.assertRaises(AssertionError):
                installation_path_probe(Path(temporary), wrong_english=True)


if __name__ == '__main__':
    unittest.main()
