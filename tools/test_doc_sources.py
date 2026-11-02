"""验证无Git的公开文档来源必须显式选择，并拒绝源码或规范漂移。"""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from doc_sources import DocSources

ROOT = Path(__file__).resolve().parents[1]


class DocSourceTests(unittest.TestCase):
    """使用最小独立目录和真实摘要校验函数检查公开树边界。"""

    def setUp(self):
        """建立无Git的小型发行树；清理只覆盖本测试临时目录。"""
        self.area = tempfile.TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        for name in ('src/chronaxis', 'Docs/AI', 'Docs/Schema', 'tools'):
            (self.root/name).mkdir(parents=True)
        for name in ('build_ai_guide.py', 'public_docs.py'):
            shutil.copyfile(ROOT/'tools'/name, self.root/'tools'/name)
        source = b'"""Example."""\nvalue = 1\n'
        schema = b'{"type":"object"}\n'
        (self.root/'src/chronaxis/__init__.py').write_bytes(source)
        (self.root/'Docs/Schema/analysis.schema.json').write_bytes(schema)
        material = 'src/chronaxis/__init__.py\0'+sha256(source).hexdigest()+'\n'
        lock = dict(runtime_sha256=sha256(material.encode()).hexdigest(),
                    inputs={'Docs/Schema/analysis.schema.json': sha256(schema).hexdigest()})
        (self.root/'Docs/AI/inputs.lock.json').write_text(json.dumps(lock), encoding='utf8')

    @patch.dict('os.environ', {'CHRONAXIS_DOC_SOURCE_TREE': '1'})
    def test_git_free_tree_is_readable(self):
        """显式树模式使用锁定源码，保持基线身份。"""
        source = DocSources(self.root, 'release-origin', 'Current')
        self.assertEqual(source.paths(), ['src/chronaxis/__init__.py'])
        self.assertIn('value = 1', source.text(source.paths()[0]))
        self.assertEqual(source.revision(), 'release-origin')

    @patch.dict('os.environ', {'CHRONAXIS_DOC_SOURCE_TREE': '1'})
    def test_source_and_schema_drift_are_rejected(self):
        """每次篡改一种输入，恢复后才测试下一种；不能静默改锁。"""
        for name in ('src/chronaxis/__init__.py', 'Docs/Schema/analysis.schema.json'):
            with self.subTest(name=name):
                path = self.root/name
                original = path.read_bytes()
                path.write_bytes(original+b' ')
                with self.assertRaises(ValueError):
                    DocSources(self.root, 'release-origin', 'Current')
                path.write_bytes(original)

    @patch.dict('os.environ', {'CHRONAXIS_DOC_SOURCE_TREE': ''})
    def test_default_never_falls_back_to_tree(self):
        """默认模式保持Git读取；不存在基线应失败，不能混用工作区。"""
        source = DocSources(self.root, 'missing-revision', 'Current')
        with patch('doc_sources.subprocess.check_output', side_effect=RuntimeError('missing Git object')):
            with self.assertRaisesRegex(RuntimeError, 'missing Git object'):
                source.text('src/chronaxis/__init__.py')


if __name__ == '__main__':
    unittest.main()
