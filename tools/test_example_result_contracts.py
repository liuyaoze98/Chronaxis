"""故意损坏教学结果，证明校核能发现单位、数值和发布结构漂移。

仅使用临时目录和独立手算夹具；不修改源码、教学快照或原始日志。
产品结果由test_power_statistics_example单独运行，此处验证失败路径和源码变更失效。
"""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from example_result_contracts import (
    power_statistics_expected, runtime_fingerprint,
    verify_power_statistics_csv, verify_power_statistics_publication,
)


def write_table(folder):
    """建立与独立手算相符的最小教学会话表，供逐种损坏测试。

    参数: folder为专用临时目录。返回: CSV路径。异常: 文件写入错误传播。
    """
    path = Path(folder) / '会话结果_20261113_120000_000000.csv'
    values = power_statistics_expected()
    fields, row = [], []
    for name in sorted(values):
        value, unit = values[name]
        fields.extend((f'{name}（{unit}）', name + '：状态', name + '：说明'))
        row.extend((value, '完整', ''))
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerow(row)
    return path


class ExampleResultContractTests(unittest.TestCase):
    """独立核对确定性文本、数值容差、动态字段和源码基线四个边界。"""

    def test_old_header_and_numeric_or_status_damage_are_rejected(self):
        """原缺陷的旧单位即使数值正确也应失败；数值和状态错误不能被摘要掩盖。

        参数: 无。返回: None。异常: 校核未拒绝故障时断言失败。
        """
        with TemporaryDirectory() as folder:
            path = write_table(folder)
            original = path.read_text(encoding='utf8')
            changes = (
                original.replace('W^2', 'V^2*A^2'),
                original.replace('80,完整', '81,完整'),
                original.replace('完整', '部分有效', 1),
            )
            for damaged in changes:
                self.assertNotEqual(damaged, original)
                path.write_text(damaged, encoding='utf8')
                with self.assertRaises(AssertionError):
                    verify_power_statistics_csv(path)

    def test_rounding_within_contract_passes_but_wrong_value_does_not(self):
        """同一正确值的浮点舍入允许差异，不要求两个后端CSV逐字节相同。

        参数: 无。返回: None。异常: 数值容差或单位处理错误时断言失败。
        """
        with TemporaryDirectory() as folder:
            path = write_table(folder)
            original = path.read_text(encoding='utf8')
            rounded = original.replace('80,完整', '80.00000000000004,完整')
            self.assertNotEqual(rounded, original)
            path.write_text(rounded, encoding='utf8')
            self.assertAlmostEqual(verify_power_statistics_csv(path)['reading_variance'], 80)

    def test_dynamic_fields_validate_structure_without_freezing_run_identity(self):
        """运行编号和时间可以变化，但缺少时间偏移或输出路径越界应失败。

        参数: 无。返回: None。异常: 动态字段合同未执行时断言失败。
        """
        with TemporaryDirectory() as folder:
            table = write_table(folder)
            manifest = Path(folder) / 'run_manifest.json'
            data = {'status': 'completed', 'run': {'run_id': 'first', 'started_at': '2026-11-13T12:00:00+08:00'},
                    'ended_at': '2026-11-13T12:01:00+08:00',
                    'outputs': [{'name': table.name, 'bytes': table.stat().st_size}]}
            for identity in ('first', 'second'):
                data['run']['run_id'] = identity
                manifest.write_text(json.dumps(data), encoding='utf8')
                self.assertEqual(verify_power_statistics_publication(manifest)['readings'], 5)
            data['outputs'][0]['name'] = '../' + table.name
            manifest.write_text(json.dumps(data), encoding='utf8')
            with self.assertRaises(AssertionError):
                verify_power_statistics_publication(manifest)
            data['outputs'][0]['name'] = table.name
            data['ended_at'] = '2026-11-13T12:01:00'
            manifest.write_text(json.dumps(data), encoding='utf8')
            with self.assertRaises(AssertionError):
                verify_power_statistics_publication(manifest)

    def test_runtime_changes_invalidate_unchanged_example_inputs(self):
        """产品变化必须改变基线；换行差异和不会导入的同步冲突副本不应影响它。

        参数: 无。返回: None。异常: 摘要错误或临时文件错误传播。
        """
        with TemporaryDirectory() as folder:
            source = Path(folder) / 'units.py'
            source.write_bytes(b'UNIT = "W"\r\n')
            before = runtime_fingerprint(folder)
            source.write_bytes(b'UNIT = "W"\n')
            self.assertEqual(runtime_fingerprint(folder), before)
            (Path(folder) / 'units - conflict.py').write_text('not executable', encoding='utf8')
            self.assertEqual(runtime_fingerprint(folder), before)
            source.write_text('UNIT = "V*A"\n', encoding='utf8')
            self.assertNotEqual(runtime_fingerprint(folder), before)


if __name__ == '__main__':
    unittest.main()
