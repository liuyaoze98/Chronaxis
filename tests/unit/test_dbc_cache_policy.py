"""确保DBC加载不启用第三方磁盘缓存，避免读取可被外部替换的pickle缓存。

使用包内源码与合成DBC验证调用参数和依赖默认行为，不读取业务日志。
"""
import ast
import importlib.util
import inspect
from pathlib import Path
import unittest
from unittest.mock import patch
import chronaxis


class DBCCachePolicyTests(unittest.TestCase):
    """防止新增DBC调用静默启用持久缓存。"""

    def test_product_loaders_do_not_pass_cache_options(self):
        """所有产品DBC加载只传入文件名；额外参数必须重新审查。"""
        package = Path(chronaxis.__file__).resolve().parent
        calls = []
        for path in package.rglob('*.py'):
            if 'vendor' in path.parts or '冲突副本' in path.name:
                continue
            for node in ast.walk(ast.parse(path.read_bytes().decode('utf-8-sig'))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if ast.unparse(node.func).endswith('cantools.database.load_file'):
                        calls.append(path.relative_to(package).as_posix())
                        self.assertEqual(len(node.args), 1, str(path))
                        self.assertFalse(node.keywords, str(path))
        # 按文件核对所有已审入口，既能发现新调用，也能发现已知入口改写后漏检。
        self.assertCountEqual(calls, [
            'execution/frame_capture.py', 'fast/can_io.py', 'fast/worker.py',
            'legacy/batch_worker.py', 'legacy/worker.py', 'sources/text_can_decode.py',
            'planning/dbc_defaults.py', 'planning/dbc_defaults.py',
        ])

    @unittest.skipUnless(importlib.util.find_spec('cantools'), '未安装可选CAN依赖')
    def test_default_dbc_load_never_constructs_diskcache(self):
        """真实解析合成DBC时缓存构造器不得触发；也核对默认值。"""
        import cantools.database
        self.assertIsNone(inspect.signature(cantools.database.load_file).parameters['cache_dir'].default)
        fixture = Path(__file__).resolve().parents[2]/'Docs/Current/examples/data/can/teaching.dbc'
        with patch.object(cantools.database.diskcache, 'Cache', side_effect=AssertionError('禁止启用磁盘缓存')):
            database = cantools.database.load_file(fixture)
        self.assertTrue(database.messages)


if __name__ == '__main__':
    unittest.main()
