"""确保DBC加载不启用第三方磁盘缓存，避免读取可被外部替换的pickle缓存。

使用包内源码与合成DBC验证调用参数和依赖默认行为，不读取业务日志。
"""
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
import chronaxis
from chronaxis.dbc_loading import load_dbc_file
from dbc_cache_policy_check import cache_policy_errors


class DBCCachePolicyTests(unittest.TestCase):
    """防止新增DBC调用静默启用持久缓存。"""

    def test_product_loaders_use_shared_gateway(self):
        """扫描所有现役模块，新增合规调用不需要维护文件数量清单。

        参数: 无。返回: None。异常: 校验不符或实际加载失败时测试失败。
        """
        package = Path(chronaxis.__file__).resolve().parent
        gateway = package / 'dbc_loading.py'
        self.assertTrue(gateway.is_file())
        for path in package.rglob('*.py'):
            if 'vendor' in path.parts or '冲突副本' in path.name:
                continue
            with self.subTest(path=path.relative_to(package).as_posix()):
                errors = cache_policy_errors(path.read_text(encoding='utf-8-sig'), gateway=path == gateway)
                self.assertEqual(errors, [])

    def test_new_compliant_call_is_not_a_fixed_inventory_failure(self):
        """新增调用及入口别名可直接通过，不要求固定的文件数量。

        参数: 无。返回: None。异常: 校验不符或实际加载失败时测试失败。
        """
        for source in ('from chronaxis.dbc_loading import load_dbc_file\nload_dbc_file(path, cantools)',
                       'from chronaxis.dbc_loading import load_dbc_file as read\nread(path, processor.cantools)'):
            with self.subTest(source=source):
                self.assertEqual(cache_policy_errors(source), [])

    def test_bypass_aliases_are_rejected(self):
        """直接、导入、赋值、显式动态别名及其他解析入口均不能绕过共用入口。

        参数: 无。返回: None。异常: 校验不符或实际加载失败时测试失败。
        """
        sources = (
            'cantools.database.load_file(path)',
            'processor.cantools.database.load_file(path)',
            'import cantools as ct\nct.database.load_file(path)',
            'import cantools.database as db\ndb.load_file(path)',
            'from cantools import database as db\ndb.load_file(path)',
            'from cantools.database import load_file as read\nread(path)',
            'import cantools as ct\nfirst=ct.database\nread=first.load_file\nread(path)',
            'ct=import_can_dependency("cantools")\nct.database.load_file(path)',
            'getattr(cantools.database, "load_file")(path)',
            'cantools.database.load(stream)',
            'cantools.database.load_string(text)',
        )
        for source in sources:
            with self.subTest(source=source):
                self.assertTrue(cache_policy_errors(source))

    def test_gateway_cache_options_and_extra_parses_are_rejected(self):
        """入口只允许官方load的一次固定参数调用。参数: 无。返回: None。异常: 断言失败。"""
        allowed = ('cantools.database.load(stream, database_format=database_format, '
                   'frame_id_mask=None, prune_choices=False, strict=True)')
        forbidden = (
            'cantools.database.load_file(path)',
            'cantools.database.load_string(text)',
            'cantools.database.load(stream)',
            allowed.replace('strict=True', 'strict=False'),
            allowed.replace('prune_choices=False', 'prune_choices=0'),
            allowed.replace('stream,', '*args,'),
            allowed.replace('database_format=database_format', '**options'),
            allowed[:-1] + ', cache_dir="cache")',
            allowed + '\n' + allowed,
        )
        for call in forbidden:
            with self.subTest(call=call):
                self.assertTrue(cache_policy_errors(call, gateway=True))
        self.assertEqual(cache_policy_errors(allowed, gateway=True), [])

    def test_gateway_preserves_loader_path_result_and_exception(self):
        """原路径只打开一次，解析结果或异常保持。参数: 无。返回: None。异常: 断言失败。"""
        path, database = Path('未读取/示例.DBC'), object()
        loader = Mock(return_value=database)
        module = SimpleNamespace(database=SimpleNamespace(load=loader))
        handle = MagicMock()
        stream = handle.__enter__.return_value
        with patch('builtins.open', return_value=handle) as opened:
            self.assertIs(load_dbc_file(path, module), database)
        opened.assert_called_once_with(path, encoding='cp1252', errors='replace')
        loader.assert_called_once_with(stream, database_format='dbc', frame_id_mask=None,
                                       prune_choices=False, strict=True)
        handle.__exit__.assert_called_once_with(None, None, None)
        error = OSError('合成解析失败')
        loader.reset_mock()
        loader.side_effect = error
        handle.reset_mock()
        with patch('builtins.open', return_value=handle) as opened:
            with self.assertRaises(OSError) as raised:
                load_dbc_file(path, module)
        self.assertIs(raised.exception, error)
        opened.assert_called_once_with(path, encoding='cp1252', errors='replace')
        loader.assert_called_once_with(stream, database_format='dbc', frame_id_mask=None,
                                       prune_choices=False, strict=True)
        self.assertIs(handle.__exit__.call_args.args[1], error)

    @unittest.skipUnless(importlib.util.find_spec('cantools'), '未安装CAN依赖')
    def test_default_dbc_load_never_constructs_diskcache(self):
        """实际DBC解析只走load，保留官方排序默认。参数: 无。返回: None。异常: 断言失败。"""
        import cantools.database
        load_parameters = inspect.signature(cantools.database.load).parameters
        file_parameters = inspect.signature(cantools.database.load_file).parameters
        for name in ('frame_id_mask', 'prune_choices', 'strict', 'sort_signals'):
            self.assertIs(load_parameters[name].default, file_parameters[name].default)
        fixture = Path(__file__).resolve().parents[2]/'Docs/Current/examples/data/can/teaching.dbc'
        forbidden = Mock(side_effect=AssertionError('禁止启用磁盘缓存'))
        with patch.object(cantools.database, 'diskcache', SimpleNamespace(Cache=forbidden), create=True), \
                patch.object(cantools.database, 'load_file', side_effect=AssertionError('禁止文件缓存入口')):
            database = load_dbc_file(fixture, cantools)
        self.assertTrue(database.messages)
        forbidden.assert_not_called()


if __name__ == '__main__':
    unittest.main()
