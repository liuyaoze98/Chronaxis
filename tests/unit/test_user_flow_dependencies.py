"""验证 CAN 安装缺项的配置和运行诊断，不把依赖失败当成信号错误。

用局部导入故障代替删除环境中的包；实际导入顺序和异常链仍经过产品入口。
不写私人文件、不访问网络，BLF 构造失败后核对资源账本清零。
"""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis.can_dependencies import CANDependencyError, import_can_dependency
from chronaxis.planning.checks import PlanValidationError
from chronaxis.planning.dbc_defaults import DBCDefaults
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.blf import BLFRead, BLFSpec


class UserFlowDependenciesTests(unittest.TestCase):
    """环境缺项带安装方案，其他解析错误不被错误归类。"""

    def test_direct_and_transitive_missing_dependency(self):
        """检查直接及间接缺项。参数: 无。返回: None。异常: 诊断不符时断言失败。"""
        for requested, missing in (('cantools', 'cantools'), ('can', 'can'),
                                   ('cantools', 'bitstruct'), ('natsort', 'natsort')):
            with self.subTest(requested=requested, missing=missing):
                error = ModuleNotFoundError('synthetic missing dependency', name=missing)
                with patch('chronaxis.can_dependencies.import_module', side_effect=error):
                    with self.assertRaises(CANDependencyError) as caught:
                        import_can_dependency(requested)
                self.assertEqual(caught.exception.code, 'dependency_missing')
                self.assertEqual(caught.exception.module_name, missing)
                self.assertIs(caught.exception.__cause__, error)
                self.assertIn('.whl"', str(caught.exception))
                self.assertNotIn('[can]', str(caught.exception))
                self.assertIn('默认会安装 CAN 依赖', str(caught.exception))
                self.assertIn('同一个 Python', str(caught.exception))

    def test_other_import_failures_are_not_reported_as_missing(self):
        """不掩盖损坏或版本不兼容。参数: 无。返回: None。异常: 原错身份变化时失败。"""
        error = ImportError('incompatible binary')
        with patch('chronaxis.can_dependencies.import_module', side_effect=error):
            with self.assertRaises(ImportError) as caught:
                import_can_dependency('cantools')
        self.assertIs(caught.exception, error)

    def test_dbc_defaults_reports_source_environment(self):
        """从信号默认推导入口获得来源级诊断。参数: 无。返回: None。异常: 断言失败。"""
        config = SimpleNamespace(dbc_path=Path('unused.dbc'), name='bus')
        field = SimpleNamespace(frame_id=256, signal='state', is_extended=False, is_fd=False)
        missing = ModuleNotFoundError('missing', name='cantools')
        with patch('chronaxis.can_dependencies.import_module', side_effect=missing):
            with self.assertRaises(PlanValidationError) as caught:
                DBCDefaults().fill({}, config, field, '$.signals[0]')
        error = caught.exception
        self.assertEqual((error.path, error.code, error.object_name),
                         ('$.sources', 'dependency_missing', '来源 bus'))
        self.assertIn('缺少 CAN', error.message)
        self.assertNotIn('无法从DBC补充信号声明', error.message)

    def test_explicit_metadata_does_not_import_can_dependency(self):
        """显式完整声明仍是静态路径。参数: 无。返回: None。异常: 意外导入时失败。"""
        raw = {'dtype': 'int64', 'unit': '1'}
        with patch('chronaxis.can_dependencies.import_module') as importer:
            self.assertEqual(DBCDefaults().fill(raw, None, None, '$.signals[0]'), raw)
        importer.assert_not_called()

    def test_blf_runtime_missing_dependency_releases_budget(self):
        """运行时导入失败先于打开文件并退款。参数: 无。返回: None。异常: 断言失败。"""
        budget = ResourceBudget()
        missing = ModuleNotFoundError('missing', name='can')
        with patch('chronaxis.can_dependencies.import_module', side_effect=missing):
            with self.assertRaises(CANDependencyError):
                BLFRead(BLFSpec(Path('not-opened.blf')), budget)
        self.assertEqual(budget.ram_bytes, 0)
