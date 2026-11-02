"""用实际计划与发布数据核对R2手册的来源、返回结构和结果解释。

运行unittest时读取随册合成材料；不改配置，不发布结果。断言失败表示文档
使用的具体行为已变化，应重新核对说明，不能只更新预期数字。
"""
import copy
import csv
from pathlib import Path
import unittest
import re
import tempfile
from ruamel.yaml import YAML
from chronaxis import AnalysisPlan, AnalysisRunner, load_analysis_plan
from chronaxis.planning.input_defaults import source_defaults

EXAMPLES = Path(__file__).resolve().parents[1] / 'Docs/Current/examples'


def rows(folder, name):
    """读取发布CSV并返回字典列表；文件不存在或协议错误直接抛异常。"""
    with (EXAMPLES / 'results' / folder / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


class ManualR2(unittest.TestCase):
    """独立核对边界与实例键，不以结果文件排序或最后总数代替过程。"""

    def test_group_source_candidates(self):
        """唯一CAN可省略；CAN加CSV必须在组级显式选择。"""
        parser = YAML(typ='safe')
        raw = parser.load((EXAMPLES / 'grouped/analysis.yaml').read_text(encoding='utf8'))
        raw['sources'][0]['name'] = 'bus'
        csv_source = parser.load((EXAMPLES / 'input-csv-minimal.yaml').read_text(encoding='utf8'))['sources'][0]
        csv_source['name'] = 'meter'
        self.assertEqual(len(AnalysisPlan.from_dict(raw, base_dir=EXAMPLES / 'grouped').signals), 2)
        multi = copy.deepcopy(raw)
        multi['sources'].append(csv_source)
        with self.assertRaisesRegex(ValueError, '请指定source'):
            AnalysisPlan.from_dict(multi, base_dir=EXAMPLES / 'grouped')
        multi['signals'][0]['source'] = 'bus'
        self.assertEqual(len(AnalysisPlan.from_dict(multi, base_dir=EXAMPLES / 'grouped').signals), 2)

    def test_format_inference(self):
        """纯ASC带偏移仍为can_asc；BLF带偏移或混合文件使用asc_or_blf。"""
        for suffixes, offsets, expected in [
            (['asc'], False, 'can_asc'), (['asc'], True, 'can_asc'),
            (['blf'], False, 'can_blf'), (['blf'], True, 'asc_or_blf'),
            (['asc', 'blf'], False, 'asc_or_blf'),
        ]:
            for explicit in (False, True):
                raw = {'paths': [f'input{i}.{suffix}' for i, suffix in enumerate(suffixes)]}
                if offsets:raw['offsets'] = ['0s'] * len(suffixes)
                if explicit:raw['source_type'] = 'asc_or_blf'
                with self.subTest(raw=raw):
                    self.assertEqual(source_defaults(raw, 0)['source_type'], expected)

    def test_preset_role_reading(self):
        """两层元组按预设顺序读取；真实属性是definition.name和resolution。"""
        plan = load_analysis_plan(EXAMPLES / 'preset-charge-minimal.yaml')
        values = [(preset.id, b.contract.role, b.definition.name, b.resolution)
                  for preset, bindings in zip(plan.presets, plan.preset_bindings) for b in bindings]
        self.assertEqual(values, [('demo_preset', 'mode', 'mode', 'explicit'),
                                  ('demo_preset', 'current', 'current', 'explicit')])

    def test_join_shuffled_event_rows(self):
        """故意逆序可读行，均值和所属区间仍在同一行；保留原纳秒真值对照。"""
        actual = {float(r['cycle_mean（1）']): (int(r['开始时间（s）'])*10**9,
                                               int(r['结束时间（s）'])*10**9)
                  for r in reversed(rows('start-end-yaml', '事件结果.csv'))}
        self.assertEqual(actual, {10: (0, 2_000_000_000), 52: (4_000_000_000, 9_000_000_000),
                                  110: (11_000_000_000, 14_000_000_000)})

    def test_direction_contributions(self):
        """三消息各评估两项；方向0不贡献，端点消息不参加求值。"""
        actual = {(r['计算项'], int(r['原记录序号'])): (r['说明'], r['贡献值'])
                  for r in rows('message-directions-yaml', '贡献明细.csv')}
        expected = {(name, i): ('已计入', '400.0') if i == selected else ('不满足条件，已跳过', '')
                    for name, selected in [('positive_energy', 0), ('negative_energy', 1)] for i in range(3)}
        self.assertEqual(actual, expected)

    def test_export_snippet_replacement(self):
        """按正文仅替换导出子项；同级另一种导出必须保留且新计划可加载。"""
        base = YAML(typ='safe').load((EXAMPLES / 'dual-grid.yaml').read_text(encoding='utf8'))
        for page, key, sibling in [('signal-exports.md', 'signal_csv', 'can_frames'),
                                   ('can-exports.md', 'can_frames', 'signal_csv')]:
            text = (EXAMPLES.parent / page).read_text(encoding='utf8')
            blocks = re.findall(r'^```yaml\s*\n(.*?)^```', text, re.M | re.S)
            for block in blocks:
                value = YAML(typ='safe').load(block)
                if set(value) != {'outputs'}:continue
                self.assertNotIn('%YAML', block)
                config = copy.deepcopy(base)
                config['outputs'][key] = value['outputs'][key]
                self.assertEqual(config['outputs'][sibling], base['outputs'][sibling])
                AnalysisPlan.from_dict(config, base_dir=EXAMPLES)

    def test_runner_source_details_are_optional(self):
        """实际读取CAN并获得38J，两个来源明细仍为空，不能据此推断没有输入。"""
        plan = load_analysis_plan(EXAMPLES / 'analysis.yaml')
        with tempfile.TemporaryDirectory(prefix='doc05-metadata-', dir=EXAMPLES.parent / '_build') as root:
            with AnalysisRunner().run(plan, work_dir=Path(root) / 'run') as result:
                self.assertEqual(result.metadata.can_sources, ())
                self.assertEqual(result.metadata.text_can_sources, ())
                self.assertNotIn('can_sources', result.metadata.to_dict())
                cursor = result.iter_calculations()
                try:values = [row.value for row in cursor]
                finally:cursor.close()
                self.assertIn(38.0, values)


if __name__ == '__main__':
    unittest.main()
