"""用原始结果字节及故意损坏的摘要核对发行流程；不运行分析或修改教学文件。"""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from ai_resource_bytes import resource_bytes, validate_result_summaries

ROOT = Path(__file__).resolve().parents[1]
check_results = run_path(str(ROOT / 'tests/ai_release/check_bundle.py'))['check_result_summaries']


def result_fixture():
    """参数: 无。返回: 带CRLF及正确摘要的微型结果文件映射。异常: 无主动异常。"""
    data = b'value,unit\r\n1000,J\r\n'
    parent = 'examples/results/energy/'
    summary = {'files': [{'path': 'energy.csv', 'bytes': len(data), 'sha256': sha256(data).hexdigest()}]}
    return {parent + 'energy.csv': data, parent + 'result-summary.json': json.dumps(summary).encode()}


def bundle_check(files):
    """建立外层哈希全部正确的内存ZIP，独立检查内层摘要；不写磁盘。"""
    material = dict(files)
    material['manifest.json'] = json.dumps({'sha256': {name: sha256(data).hexdigest() for name, data in files.items()}}).encode()
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as z:
        for name, data in material.items():
            z.writestr(name, data)
    with ZipFile(BytesIO(stream.getvalue())) as z:
        manifest = json.loads(z.read('manifest.json'))
        assert all(sha256(z.read(name)).hexdigest() == digest for name, digest in manifest['sha256'].items())
        return check_results(z, set(z.namelist()))


class ResultBytesTests(unittest.TestCase):
    """即使外层哈希有效，内层摘要失配仍必须被拒绝。"""

    def test_resource_types_use_correct_bytes(self):
        """参数: 无。返回: None。异常: 断言失败；结果不变，普通说明跨平台规范换行。"""
        data = b'a,b\r\n1,2\r\n'
        for suffix in ('csv', 'jsonl', 'json', 'asc'):
            self.assertEqual(resource_bytes('Docs/Current/examples/results/example/table.' + suffix, data), data)
        self.assertEqual(resource_bytes('Docs/Current/examples/input.csv', data), data)
        self.assertEqual(resource_bytes('Docs/AI/README.md', data), b'a,b\n1,2\n')
        self.assertEqual(resource_bytes('Docs/Current/examples/data/input.blf', data), data)

    def test_correct_inner_summary_passes(self):
        """参数: 无。返回: None。异常: 断言失败；两种独立检查均验证一个结果。"""
        files = result_fixture()
        expected = dict(result_summaries=1, result_files=1)
        self.assertEqual(validate_result_summaries(files), expected)
        self.assertEqual(bundle_check(files), expected)

    def test_newline_change_rejected_even_with_valid_outer_manifest(self):
        """参数: 无。返回: None。异常: 断言失败；复现本次CRLF转LF但内层摘要未变。"""
        files = result_fixture()
        name = 'examples/results/energy/energy.csv'
        files[name] = files[name].replace(b'\r\n', b'\n')
        with self.assertRaisesRegex(ValueError, 'bytes'):
            validate_result_summaries(files)
        with self.assertRaisesRegex(AssertionError, 'bytes'):
            bundle_check(files)

    def test_same_size_value_change_rejected(self):
        """参数: 无。返回: None。异常: 断言失败；字节数不变的内容修改由SHA256发现。"""
        files = result_fixture()
        name = 'examples/results/energy/energy.csv'
        files[name] = files[name].replace(b'1000', b'2000')
        with self.assertRaisesRegex(ValueError, 'sha256'):
            validate_result_summaries(files)
        with self.assertRaisesRegex(AssertionError, 'sha256'):
            bundle_check(files)

    def test_missing_and_escaping_files_rejected(self):
        """参数: 无。返回: None。异常: 断言失败；缺件和越出案例目录的路径不被忽略。"""
        original = result_fixture()
        summary_name = 'examples/results/energy/result-summary.json'
        for target in ('missing.csv', '../other.csv', '/absolute.csv', 'C:/absolute.csv'):
            files = deepcopy(original)
            summary = json.loads(files[summary_name])
            summary['files'][0]['path'] = target
            files[summary_name] = json.dumps(summary).encode()
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_result_summaries(files)
            with self.subTest(target=target), self.assertRaises(AssertionError):
                bundle_check(files)

    def test_current_result_samples_match_without_recalculation(self):
        """参数: 无。返回: None。异常: 断言失败；全体现有教学结果原字节匹配其摘要。"""
        folder = ROOT / 'Docs/Current/examples/results'
        files = {'examples/results/' + path.relative_to(folder).as_posix(): path.read_bytes()
                 for path in folder.rglob('*') if path.is_file()}
        counts = validate_result_summaries(files)
        self.assertGreater(counts['result_files'], 4)
        self.assertEqual(bundle_check(files), counts)
