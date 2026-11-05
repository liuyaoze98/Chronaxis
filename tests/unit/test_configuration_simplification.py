"""验证简化声明与完整声明等价，同时不吞掉歧义和显式错误。

只构造内存与不存在路径的配置；静态默认检查不打开日志或DBC。
使用既有完整夹具作为对照，删除被批准省略的字段后核对实际计划。
"""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from jsonschema import Draft202012Validator

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError, validate_analysis_plan
from test_can_planning import can_config
from test_plan_message_calculations import legacy_config


class ConfigurationSimplificationTests(unittest.TestCase):
    """配置默认值只补明确含义；真实数据读取由后续集成验收覆盖。"""

    def test_can_source_and_binding_defaults(self):
        """参数: 无。返回: None。异常: 断言失败；省略来源/通道后绑定应相同。"""
        full = can_config()
        expected = AnalysisPlan.from_dict(full)
        short = deepcopy(full)
        # 路径后缀、唯一来源和唯一DBC通道足以确定这些声明。
        source = short['sources'][0]
        for key in ('source_type', 'legacy_profile'):
            source.pop(key)
        source['time'].pop('unit')
        source['time'].pop('time_type')
        short['signals'][0].pop('source')
        short['signals'][0]['field'].pop('channel')
        actual = AnalysisPlan.from_dict(short)
        # 独立Schema也必须接受同一简写，不能只有Python入口放宽。
        schema = json.loads((Path(__file__).parents[2] / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(short)
        self.assertEqual(actual.sources[0].config, expected.sources[0].config)
        self.assertEqual(actual.signals, expected.signals)
        self.assertTrue(validate_analysis_plan(actual).valid)

    def test_dataset_and_clock_defaults(self):
        """参数: 无。返回: None。异常: 断言失败；默认名称局限当前任务。"""
        config = can_config()
        config['dataset'].pop('entity')
        config['dataset'].pop('session')
        config['sources'][0].pop('name')
        config['sources'][0].pop('time')
        config['signals'][0].pop('source')
        plan = AnalysisPlan.from_dict(config)
        self.assertEqual(plan.dataset.entity, 'can_static')
        self.assertEqual(plan.dataset.session_id, 'can_static')
        self.assertEqual(plan.sources[0].name, 'source_1')
        self.assertEqual(plan.signals[0].definition.source, 'source_1')

    def test_asc_auto_format(self):
        """参数: 无。返回: None。异常: 断言失败；ASC无需填BLF专用字段。"""
        config = can_config()
        source = config['sources'][0]
        for key in ('source_type', 'legacy_profile'):
            source.pop(key)
        source['reader'].pop('decode_scope')
        source['path'] = 'missing.ASC'
        self.assertEqual(AnalysisPlan.from_dict(config).sources[0].source_type, 'can_asc')

    def test_ambiguous_source_requires_selection(self):
        """参数: 无。返回: None。异常: 断言失败；多个来源不能取第一个。"""
        config = can_config()
        other = deepcopy(config['sources'][0])
        other['name'] = 'other'
        config['sources'].append(other)
        config['signals'][0].pop('source')
        with self.assertRaisesRegex(PlanValidationError, 'source'):
            AnalysisPlan.from_dict(config)

    def test_default_clocks_are_not_shared(self):
        """参数: 无。返回: None。异常: 断言失败；省略时钟不等于跨来源同步。"""
        config = can_config()
        other = deepcopy(config['sources'][0])
        other['name'] = 'other'
        config['sources'].append(other)
        for source in config['sources']:
            source.pop('time')
        plan = AnalysisPlan.from_dict(config)
        self.assertNotEqual(plan.sources[0].config.timebase, plan.sources[1].config.timebase)

    def test_invalid_explicit_values_remain_errors(self):
        """参数: 无。返回: None。异常: 断言失败；null和未知策略不被当成省略。"""
        for key, value in (('legacy_profile', None), ('time', None), ('source_type', 'unknown'), ('name', '')):
            with self.subTest(key=key):
                config = can_config()
                config['sources'][0][key] = value
                with self.assertRaises(PlanValidationError):
                    AnalysisPlan.from_dict(config)

    def test_window_and_calculation_defaults(self):
        """参数: 无。返回: None。异常: 断言失败；可推导窗口和全任务统计保持原结果。"""
        config = can_config()
        expected = AnalysisPlan.from_dict(config)
        for key in ('anchor', 'pre', 'post'):
            config['windows'][0].pop(key)
        config['calculations'][0].pop('scope')
        actual = AnalysisPlan.from_dict(config)
        self.assertEqual(actual.windows, expected.windows)
        self.assertEqual(actual.calculations, expected.calculations)

    def test_start_only_window_inherits_duration(self):
        """参数: 无。返回: None。异常: 断言失败；固定窗口时长只需写在规则上。"""
        config = can_config()
        config['rules'] = [dict(name='active', rule_type='start_only', condition='power > 1', window_duration='2s')]
        config['windows'] = [dict(name='context', rule='active')]
        self.assertEqual(AnalysisPlan.from_dict(config).windows[0].post_ns, 2_000_000_000)

    def test_message_fixed_policies_and_source_inherit(self):
        """参数: 无。返回: None。异常: 断言失败；逐消息策略不再重复必填。"""
        config = legacy_config()
        expected = AnalysisPlan.from_dict(config)
        for item in config['message_calculations']:
            for key in ('source', 'profile', 'operation', 'message_policy'):
                item.pop(key)
            item['update_message'].pop('channel')
        actual = AnalysisPlan.from_dict(config)
        self.assertEqual(actual.message_calculations, expected.message_calculations)

    def test_minimal_memory_integral_both_backends(self):
        """参数: 无。返回: None。异常: 断言失败；两后端实际算出10W×2s=20J。"""
        config = dict(config_version=4, dataset=dict(name='energy', domain=dict(start='0s', end='2s')),
                      sources=[dict(source_type='memory', rows=[dict(time='0s', values={'power': 10}),
                                                                dict(time='2s', values={'power': 10})])],
                      signals=[dict(name='power', field='power', dtype='float64', unit='W', valid_for='3s')],
                      calculations=[dict(name='energy', operation='integral', expr='power')])
        # 暂存只位于本测试的系统临时目录；上下文退出后释放结果及文件。
        for backend in ('numpy', 'reference'):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                config['execution'] = dict(backend=backend)
                with AnalysisRunner().run(AnalysisPlan.from_dict(config), work_dir=Path(directory) / 'run') as result:
                    rows = list(result.iter_calculations())
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0].value, 20)

    def test_resolve_defaults_roundtrip(self):
        """参数: 无。返回: None。异常: 断言失败；来源省略time时仍可展开再加载。"""
        from chronaxis.configuration.resolution import resolved_configuration
        config = can_config()
        config['sources'][0].pop('time')
        config['sources'][0].pop('source_type')
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            source.write_text(json.dumps(config), encoding='utf-8')
            resolved = resolved_configuration(source, defaults=True)
            self.assertEqual(AnalysisPlan.from_dict(resolved).sources[0].source_type, 'can_blf')


if __name__ == '__main__':
    # 独立执行同样通过unittest报告失败，不改变测试发现行为。
    unittest.main()
