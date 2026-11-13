"""来源包惰性导出保持公开名单和对象身份，BLF worker 不加载无关数组代码。"""
import json
import subprocess
import sys
import unittest


class SourceExportsTests(unittest.TestCase):
    """独立解释器证明冷导入，当前解释器证明所有原公开对象仍可获取。"""

    def test_cold_package_and_unknown_attribute_do_not_import_numpy(self):
        """只导入来源包和不存在属性，不加载 NumPy/规划/CSV 输入实现。"""
        source="""import sys
import chronaxis.sources as sources
try:sources.not_a_public_source
except AttributeError:pass
else:raise AssertionError('unknown attribute accepted')
assert not {'numpy','chronaxis.planning','chronaxis.sources.signal_csv'} & sys.modules.keys()
print('ok')
"""
        result=subprocess.run([sys.executable,'-X','utf8','-B','-c',source],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'ok')

    def test_all_names_and_original_class_identity_are_preserved(self):
        """原公开名单/顺序及每个类对象保持，按需访问可重复且不是包装类型。"""
        import importlib
        import chronaxis.sources as sources
        expected=['MemorySourceAdapter','SignalCSVSpec','CSVSourceRef','SignalCSVSourceAdapter',
            'FieldDescription','FieldLocation','ReadRequest','SignalBatch','SignalSeries',
            'SourceCapabilities','SourceDescription','BatchValidator','SourceAdapter','SourceClosedError','SourceReadError']
        self.assertEqual(sources.__all__,expected)
        for name in expected:
            original=getattr(importlib.import_module('chronaxis.sources.'+sources._EXPORTS[name]),name)
            self.assertIs(getattr(sources,name),original)
            self.assertIs(getattr(sources,name),original)
        with self.assertRaises(AttributeError):getattr(sources,'not_public')

    def test_from_import_remains_supported(self):
        """显式 from import 与星号导入继续得到相同公开对象。"""
        from chronaxis.sources import MemorySourceAdapter,SignalCSVSpec,SourceReadError
        import chronaxis.sources as sources
        self.assertIs(MemorySourceAdapter,sources.MemorySourceAdapter)
        self.assertIs(SignalCSVSpec,sources.SignalCSVSpec)
        self.assertIs(SourceReadError,sources.SourceReadError)
        namespace={}
        exec('from chronaxis.sources import *',namespace)
        self.assertEqual(set(namespace)-{'__builtins__'},set(sources.__all__))
        for name in sources.__all__:self.assertIs(namespace[name],getattr(sources,name))


if __name__=='__main__':unittest.main()
