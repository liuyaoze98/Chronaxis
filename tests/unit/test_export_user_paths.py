"""通过公开计划和执行入口验证客户目录、设备标签及三类实际导出。

所有 RefProjects 同名目录均位于合成测试根内，不写仓库历史资料。
"""
import csv
import json
from uuid import uuid4
import unittest

from chronaxis import AnalysisRunner, PlanValidationError, validate_analysis_plan
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.asc import ASCRead, ASCSpec
from published_paths import export_root, published_file
import test_record_runner as raw_cases


class CustomerExportTests(unittest.TestCase):
    """验证用户标签不影响计算/导出，未填标签保持 pending 而非猜测设备。"""

    setUp = raw_cases.RecordRunnerTests.setUp
    asc = raw_cases.RecordRunnerTests.asc
    csv = raw_cases.RecordRunnerTests.csv
    blf = raw_cases.RecordRunnerTests.blf
    fixtures = raw_cases.RecordRunnerTests.fixtures
    plan = raw_cases.RecordRunnerTests.plan

    def test_omitted_and_customer_labels_export_signals_and_both_frame_formats(self):
        """省略、英文和中文标签均可校验、计算及导出 CSV/ASC/BLF，保留用户旧文件。"""
        import can
        path = self.fixtures()['can_asc']
        for label in (None, 'lab-pc', '试验台一号'):
            for format in ('asc', 'blf'):
                with self.subTest(label=label, format=format):
                    def edit(raw):
                        """只选择用户标签和所需导出，保留同一组手算输入。"""
                        raw['metadata'] = {} if label is None else dict(device_label=label)
                        raw['outputs']['signal_csv'] = dict(signals=['current'])
                        raw['outputs']['can_frames'] = dict(source=raw['sources'][0]['name'], format=format)
                        if format == 'blf':
                            raw['outputs']['can_frames'].update(capture_date='2026-11-11', timezone='+08:00')
                    plan = self.plan('can_asc', path, 'fixed', edit)
                    self.assertTrue(validate_analysis_plan(plan).execution_ready)
                    customer = self.root / uuid4().hex / 'RefProjects'
                    output = customer / 'output'
                    output.mkdir(parents=True)
                    sentinel = output / 'user.txt'
                    sentinel.write_bytes(b'keep')
                    with AnalysisRunner().run(plan, customer / 'work') as result:
                        expected_label = 'pending' if label is None else label
                        self.assertEqual(result.metadata.device_label, expected_label)
                        values = {row.calculation_id: row.value for row in result.iter_calculations()}
                        self.assertAlmostEqual(values['energy'], 880.0)
                        published = result.write(output)
                        manifest = json.loads(published.manifest_path.read_text(encoding='utf-8'))
                        self.assertEqual(manifest['run']['device_label'], expected_label)
                        inventory = [json.loads(line) for line in published_file(published, 'exports.jsonl').read_text(encoding='utf-8').splitlines()]
                        directories = {item['export_type']: export_root(published) / item['directory'] for item in inventory}
                        with (directories['signal_csv'] / 'original.csv').open(encoding='utf-8', newline='') as stream:
                            signals = list(csv.DictReader(stream))
                        self.assertEqual([row['value'] for row in signals], ['10.0', '12.0'])
                        for directory in directories.values():
                            details = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
                            self.assertEqual(details['device_label'], expected_label)
                        frames_path = directories['can_frames'] / ('frames.' + format)
                        if format == 'asc':
                            with ASCRead(ASCSpec(frames_path), ResourceBudget()) as reader:
                                frames = [record.frame.data for record in reader]
                        else:
                            with can.BLFReader(frames_path) as reader:
                                frames = [bytes(record.data) for record in reader]
                        self.assertEqual(frames, [bytes([200, 10]), bytes([200, 12])])
                    self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_invalid_customer_label_is_reported_before_running(self):
        """错误标签在配置阶段定位，不能先通过校验再在导出时失败。"""
        path = self.fixtures()['can_asc']
        for label in ('', '   ', None, 42, True):
            with self.subTest(label=label):
                def edit(raw):
                    """显式设置非法标签，与省略 metadata.device_label 区分。"""
                    raw['metadata'] = dict(device_label=label)
                    raw['outputs']['signal_csv'] = dict(signals=['current'])
                with self.assertRaises(PlanValidationError) as caught:
                    self.plan('can_asc', path, 'fixed', edit)
                self.assertIn('$.metadata.device_label', {item.path for item in caught.exception.diagnostics})
