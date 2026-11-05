"""核对目录、通配符、显式顺序及逐文件偏移，并运行连续ASC分析。

所有输入均为系统临时目录中的合成文件，不写历史项目或用户日志。
目录选择仅枚举名称；实际读取、自然顺序与跨文件结果由公开Runner验证。
"""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError
from chronaxis.planning.input_paths import expand_input_paths, expand_source_files
from chronaxis.configuration.resolution import resolved_configuration
from test_can_planning import can_config


class ConfigurationPathsTests(unittest.TestCase):
    """输入列表的顺序是业务事实，目录发现只排序自己产生的集合。"""

    def setUp(self):
        """参数: 无。返回: None。异常: 临时目录不可写；清理由unittest登记。"""
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # 三个编号刻意按非自然顺序创建，另加无关格式和子目录。
        for name in ('part10.ASC', 'part2.asc', 'part1.asc', 'ignore.txt'):
            (self.root / name).write_text('', encoding='utf-8')
        (self.root / 'nested').mkdir()
        (self.root / 'nested' / 'extra.asc').write_text('', encoding='utf-8')

    def test_directory_natural_order_filter_and_no_recursion(self):
        """参数: 无。返回: None。异常: 断言失败；只取目录内ASC，数字按1/2/10。"""
        paths = expand_input_paths(dict(paths=str(self.root), source_type='can_asc'), self.root, '$.sources[0]')
        self.assertEqual([item.name for item in paths], ['part1.asc', 'part2.asc', 'part10.ASC'])

    def test_explicit_order_and_file_no_io(self):
        """参数: 无。返回: None。异常: 断言失败；列表原序保留，不stat明确文件。"""
        with patch.object(Path, 'stat', side_effect=AssertionError('明确文件不访问磁盘')):
            paths = expand_input_paths(dict(paths=['part10.ASC', 'part2.asc']), self.root, '$.sources[0]')
            self.assertEqual([item.name for item in paths], ['part10.ASC', 'part2.asc'])
            self.assertEqual(len(expand_input_paths(dict(paths='missing.blf'), self.root, '$.sources[0]')), 1)
            self.assertEqual(expand_input_paths(dict(paths='record[1].blf'), self.root, '$.sources[0]')[0].name,
                             'record[1].blf')

    def test_glob_and_explicit_recursion(self):
        """参数: 无。返回: None。异常: 断言失败；递归只有**声明时启用。"""
        paths = expand_input_paths(dict(paths='**/*.asc', source_type='can_asc'), self.root, '$.sources[0]')
        self.assertEqual({item.name for item in paths}, {'part1.asc', 'part2.asc', 'part10.ASC', 'extra.asc'})

    def test_empty_unknown_and_ambiguous_declarations(self):
        """参数: 无。返回: None。异常: 断言失败；错误目录/空匹配/两种路径并填都拒绝。"""
        for raw in (dict(paths=[]), dict(paths='*.blf'), dict(paths='missing-folder'),
                    dict(path='x.asc', paths=['x.asc']), dict(paths=[{'path': 'part1.asc', 'unknown': 0}])):
            with self.subTest(raw=raw), self.assertRaises(PlanValidationError):
                expand_input_paths(raw, self.root, '$.sources[0]')

    def test_offsets_follow_file_objects(self):
        """参数: 无。返回: None。异常: 断言失败；文件变序时自己的偏移跟随文件。"""
        raw = dict(paths=[dict(path='part10.ASC', offset='2s'), 'part2.asc'], source_type='can_asc')
        paths, shifts = expand_source_files(raw, self.root, '$.sources[0]')
        self.assertEqual([item.name for item in paths], ['part10.ASC', 'part2.asc'])
        self.assertEqual(shifts, ('2s', '0s'))
        raw['offsets'] = ['0s', '0s']
        with self.assertRaises(PlanValidationError):
            expand_source_files(raw, self.root, '$.sources[0]')

    def test_directory_limit_reports_instead_of_truncating(self):
        """参数: 无。返回: None。异常: 断言失败；超限必须停止而非只取前几项。"""
        with patch('chronaxis.planning.input_paths.MAX_INPUT_FILES', 2):
            with self.assertRaisesRegex(PlanValidationError, '超过'):
                expand_input_paths(dict(paths=str(self.root), source_type='can_asc'), self.root, '$.sources[0]')

    def test_public_auto_source_directory_and_resolve(self):
        """参数: 无。返回: None。异常: 断言失败；公开解析和导出工具支持相同目录简写。"""
        config = can_config()
        source = config['sources'][0]
        for key in ('source_type', 'legacy_profile', 'path'):
            source.pop(key)
        source['reader'].pop('decode_scope')
        source['paths'] = str(self.root)
        plan = AnalysisPlan.from_dict(config)
        self.assertEqual(plan.sources[0].source_type, 'can_asc')
        self.assertEqual([item.path.name for item in plan.sources[0].config.inputs],
                         ['part1.asc', 'part2.asc', 'part10.ASC'])
        saved = self.root / 'analysis.json'
        saved.write_text(json.dumps(config), encoding='utf-8')
        for defaults in (False, True):
            resolved = resolved_configuration(saved, defaults=defaults)
            self.assertEqual(AnalysisPlan.from_dict(resolved).sources[0].config.inputs,
                             plan.sources[0].config.inputs)

    def test_public_file_offsets_and_input_not_mutated(self):
        """参数: 无。返回: None。异常: 断言失败；公共来源合并总偏移且不改原字典。"""
        config = can_config()
        source = config['sources'][0]
        for key in ('legacy_profile', 'path'):
            source.pop(key)
        source['reader'].pop('decode_scope')
        source.update(source_type='can_asc', paths=[{'path': 'part1.asc', 'offset': '1s'}, 'part2.asc'])
        original = deepcopy(config)
        plan = AnalysisPlan.from_dict(config, base_dir=self.root)
        self.assertEqual([item.offset_ns for item in plan.sources[0].config.inputs], [10**9, 0])
        self.assertEqual(config, original)

    def test_directory_analysis_continues_across_files(self):
        """参数: 无。返回: None。异常: 断言失败；自然序读取使三帧跨文件积分为4Vs。"""
        shared = Path(__file__).parents[2] / 'src/chronaxis/configuration/templates/shared'
        # 原始字节01解出3V，00解出1V；在0/1/2秒更新，积分3×1+1×1=4Vs。
        for name, seconds, byte in (('part1.asc', 0, '01'), ('part2.asc', 1, '00'), ('part10.ASC', 2, '01')):
            (self.root / name).write_text(f'base hex timestamps absolute\n{seconds} 1 100 Rx d 2 {byte} 00\n', encoding='utf-8')
        config = dict(config_version=4, dataset=dict(name='folder', domain=dict(start='0s', end='2s')),
                      sources=[dict(paths=str(self.root), dbc_by_channel={'1': str(shared / 'sample.dbc')})],
                      signals=[dict(name='voltage', field=dict(frame_id='0x100', signal='Voltage'),
                                    dtype='float64', unit='V', valid_for='3s')],
                      calculations=[dict(name='area', operation='integral', expr='voltage')])
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                config['execution'] = dict(backend=backend)
                with AnalysisRunner().run(AnalysisPlan.from_dict(config), work_dir=self.root / backend) as result:
                    self.assertEqual([row.value for row in result.iter_calculations()], [4.0])


if __name__ == '__main__':
    # 与测试发现使用同一组断言。
    unittest.main()
