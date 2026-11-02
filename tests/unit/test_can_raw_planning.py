"""验证原始BLF片段输出的冻结声明、严格schema及纯静态能力边界。

输入复用B2公开CAN合成配置，再显式声明一个原始输出来源与blf格式；输出为
AnalysisPlan、AnalysisRunner共享报告及独立Draft202012Validator断言。静态构建不读
BLF/DBC、不启动旧writer、不创建文件或假事件。真实片段选择、旧writer行为、
空索引、预算和重复发布由公共运行与导出专项另验；本测试不把声明当作已写出。
"""

from configuration_fixtures import current_fixture

# 只按模块别名复用独立JSON夹具，不导入其他TestCase至本模块触发重复发现。
import test_can_planning as can_planning
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import multiprocessing
from pathlib import Path
from typing import get_type_hints
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator

from chronaxis import AnalysisPlan, PlanValidationError, AnalysisRunner, explain_analysis_plan, validate_analysis_plan
from chronaxis.planning.models import OutputPlan
from chronaxis.planning.export_options import CANFramesOutput
from chronaxis.results.frame_exports import FrameExportSpec


ROOT = Path(__file__).absolute().parents[2]


def raw_config():
    """在真实B2静态配置上增加唯一来源与BLF格式，不修改原夹具。

    参数: 无。返回: 独立原生JSON字典。异常: 无I/O或产品执行副作用。
    """
    config = can_planning.can_config()
    config['outputs'] = dict(tables='jsonl', manifest='json', can_frames=dict(source='bus', format='asc'))
    return config


def table_config(kind):
    """建立仍遵循字符串字段规则的memory/CSV来源，专用于兼容与误指来源负例。

    参数: kind为memory或signal_csv。返回: 没有raw请求的独立JSON配置。
    异常: 未知测试种类ValueError；不创建文件或推断CAN来源。
    """
    config = can_planning.can_config()
    source = dict(name='bus', source_type=kind, time=dict(time_type='relative', unit='ns', origin='can_static_origin'))
    if kind == 'memory':
        source['rows'] = [dict(time='0s', values={'raw.power': 2}), dict(time='4s', values={'raw.power': 0})]
    elif kind == 'signal_csv':
        source.update(path='work/raw-planning-missing.csv', time_column='ns')
    else:
        raise ValueError('仅测试memory/signal_csv')
    config['sources'] = [source]
    config['signals'][0]['field'] = 'raw.power'
    return config


class CANRawPlanningTests(unittest.TestCase):
    """原始导出只接受明确typed BLF声明，报告计划能力同时保运行期限制。

    所有分析输入路径都为合成定位；schema只读一次，之后静态操作借用阻断探针。
    source名称到实际来源种类/profile的关联由Python核，标准schema只核对象形状。
    """

    @classmethod
    def setUpClass(cls):
        """读取本地公开schema并由独立元schema校验其结构。

        参数: 无。返回: None，保存验证器。异常: 真实读取、JSON或SchemaError传播，不skip。
        """
        schema = json.loads((ROOT / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def guard_static(self):
        """阻断源/DBC/writer I/O与进程，让合法和非法静态路径均不得产生副作用。

        参数: 无。返回: 安装完毕的ExitStack。异常: 禁止动作AssertionError；安装中断也恢复探针。
        """
        stack, original_import = ExitStack(), __import__

        def deny_runtime_import(name, globals=None, locals=None, fromlist=(), level=0):
            """拒运行与旧CAN组件导入。参数: 原import参数。返回: 原模块。异常: 禁止目标AssertionError。"""
            forbidden = ('can', 'cantools', 'natsort', 'worker', 'process_read', 'can_reader',
                         'run_session', 'export_worker', 'export_write', 'raw_exports')
            if name.split('.')[0] in ('can', 'cantools', 'natsort', 'RefProjects') or \
                    name.rsplit('.', 1)[-1] in forbidden or any(item in forbidden for item in (fromlist or ())):
                raise AssertionError('静态raw规划导入运行组件：' + name)
            return original_import(name, globals, locals, fromlist, level)

        try:
            for method in ('open', 'read_text', 'read_bytes', 'stat', 'resolve', 'mkdir'):
                stack.enter_context(patch.object(Path, method, side_effect=AssertionError('静态raw规划触发Path.'+method)))
            stack.enter_context(patch('builtins.open', side_effect=AssertionError('静态raw规划触发open')))
            stack.enter_context(patch.object(multiprocessing, 'get_context', side_effect=AssertionError('静态raw规划创建spawn上下文')))
            stack.enter_context(patch.object(multiprocessing, 'Process', side_effect=AssertionError('静态raw规划创建Process')))
            stack.enter_context(patch('builtins.__import__', deny_runtime_import))
            return stack
        except BaseException:
            stack.close()
            raise


    def test_frozen_frame_declaration_shared_reports_and_no_io(self):
        """帧声明冻结且无I/O，修改原字典不影响计划；报告复用同一typed计划。"""
        config = raw_config()
        self.assertTrue(self.validator.is_valid(current_fixture(config)))
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            with patch.object(AnalysisPlan, 'from_dict', side_effect=AssertionError('报告不得重构计划')):
                report = AnalysisRunner().validate(plan)
                explanation = AnalysisRunner().explain(plan)
                self.assertEqual(report, validate_analysis_plan(plan))
                self.assertEqual(explanation, explain_analysis_plan(plan))
        option = plan.outputs.can_frames
        self.assertIs(type(option), CANFramesOutput)
        self.assertEqual((option.source, option.spec.format, option.scope), ('bus', 'asc', 'session'))
        self.assertEqual(get_type_hints(OutputPlan)['can_frames'], CANFramesOutput | None)
        with self.assertRaises(FrozenInstanceError):
            option.source = 'changed'
        config['outputs']['can_frames']['source'] = 'changed'
        self.assertEqual(option.source, 'bus')
        self.assertEqual(plan.raw_config['outputs']['can_frames']['source'], 'bus')
        self.assertTrue(report.valid and report.execution_ready, report.errors)
        self.assertEqual(explanation.plan_identity, plan.identity)
        self.assertEqual(explanation.source_names, ('bus',))
        self.assertTrue(any(node.node_id == 'outputs.can_frames' for node in explanation.nodes))

    def test_frame_only_analysis_needs_no_fake_events(self):
        """session报文导出无需窗口或计算，声明本身不创建任何输出文件。"""
        config = raw_config()
        config.update(signals=[], derived={}, rules=[], windows=[], calculations=[])
        self.assertTrue(self.validator.is_valid(current_fixture(config)))
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            report = validate_analysis_plan(plan)
        self.assertEqual((plan.rules, plan.windows, plan.calculations), ((), (), ()))
        self.assertEqual(plan.outputs.can_frames.scope, 'session')
        self.assertTrue(report.execution_ready, report.errors)

    def test_shape_format_and_source_association(self):
        """非法结构由schema和解析器拒绝；动态来源关联由解析器独立校验。"""
        # 唯一CAN来源不再要求重复引用；Schema和计划均应与完整声明相同。
        short = raw_config()
        expected = AnalysisPlan.from_dict(current_fixture(short)).outputs.can_frames
        short['outputs']['can_frames'].pop('source')
        self.validator.validate(current_fixture(short))
        self.assertEqual(AnalysisPlan.from_dict(current_fixture(short)).outputs.can_frames, expected)
        variants = [[], 'blf', True, {}, {'source': 'bus'},
            {'source': 'bus', 'format': 'blf', 'unknown': 1},
            {'source': False, 'format': 'blf'}, {'source': '', 'format': 'blf'},
            {'source': 'bus', 'format': 'csv'}, {'source': 'bus', 'format': 'BLF'},
            {'source': 'bus', 'format': None}, {'source': 'bus', 'format': True}]
        for value in variants:
            config = raw_config()
            config['outputs']['can_frames'] = value
            with self.subTest(value=value):
                self.assertFalse(self.validator.is_valid(current_fixture(config)))
                with self.guard_static(), self.assertRaises(PlanValidationError) as caught:
                    AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
                self.assertTrue(caught.exception.path.startswith('$.outputs.can_frames'))
        unknown = raw_config()
        unknown['outputs']['can_frames']['source'] = 'unknown'
        configs = [unknown]
        for kind in ('memory', 'signal_csv'):
            config = table_config(kind)
            config['outputs'] = {'can_frames': {'source': 'bus', 'format': 'blf'}}
            configs.append(config)
        for config in configs:
            self.assertTrue(self.validator.is_valid(current_fixture(config)))
            with self.guard_static(), self.assertRaises(PlanValidationError) as caught:
                AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            self.assertEqual(caught.exception.path, '$.outputs.can_frames.source')

    def test_typed_output_and_source_replacement_are_revalidated(self):
        """合法raw_config不能替代typed输出、来源、窗口及格式的真实校验。"""
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(raw_config()), base_dir=ROOT)
        option = plan.outputs.can_frames
        cases = [replace(plan, outputs=replace(plan.outputs, can_frames=value))
                 for value in (object(), 'blf', {}, ('bus', 'blf'),
                               replace(option, source='unknown'),
                               replace(option, scope='segments', window='unknown'))]
        source = plan.sources[0]
        cases += [replace(plan, sources=()), replace(plan, sources=(replace(source, name='renamed'),)),
                  replace(plan, sources=(source, source))]
        for typed in cases:
            with self.guard_static():
                report = validate_analysis_plan(typed)
                explanation = explain_analysis_plan(typed)
            self.assertFalse(report.valid)
            self.assertFalse(report.execution_ready)
            self.assertTrue(report.errors)
            self.assertEqual(explanation.validation, report)
        for format in ('csv', True, None):
            with self.assertRaises((TypeError, ValueError)):
                FrameExportSpec(format)

    def test_omitted_null_and_formats_preserve_binding_identity(self):
        """省略/null均关闭报文导出；CSV与JSONL只改变表格式，不能改变信号绑定。"""
        for original in (can_planning.can_config(), table_config('memory'), table_config('signal_csv')):
            for table_format in ('csv', 'jsonl'):
                omitted = deepcopy(original)
                omitted['outputs'] = dict(tables=table_format, manifest='json')
                null = deepcopy(omitted)
                null['outputs']['can_frames'] = None
                self.assertTrue(self.validator.is_valid(current_fixture(omitted)))
                self.assertTrue(self.validator.is_valid(current_fixture(null)))
                with self.guard_static():
                    first = AnalysisPlan.from_dict(current_fixture(omitted), base_dir=ROOT)
                    second = AnalysisPlan.from_dict(current_fixture(null), base_dir=ROOT)
                self.assertIsNone(first.outputs.can_frames)
                self.assertIsNone(second.outputs.can_frames)
                self.assertEqual(second.outputs.tables, table_format)
                self.assertEqual(first.bindings.identity, second.bindings.identity)
        with self.guard_static():
            base = AnalysisPlan.from_dict(current_fixture(can_planning.can_config()), base_dir=ROOT)
            raw = AnalysisPlan.from_dict(current_fixture(raw_config()), base_dir=ROOT)
        self.assertNotEqual(base.identity, raw.identity)
        self.assertEqual(base.bindings.identity, raw.bindings.identity)

    def test_retired_raw_segments_rejected_and_window_selection_explicit(self):
        """旧输出入口无兼容别名；segments支持明确窗口或全部窗口，错误引用拒绝。"""
        retired = can_planning.can_config()
        retired['outputs'] = {'raw_segments': {'source': 'bus', 'format': 'blf'}}
        self.assertFalse(self.validator.is_valid(current_fixture(retired)))
        with self.guard_static(), self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(retired), base_dir=ROOT)
        current = raw_config()
        current['outputs']['can_frames'].update(scope='segments', window='context')
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(current), base_dir=ROOT)
        self.assertEqual((plan.outputs.can_frames.scope, plan.outputs.can_frames.window), ('segments', 'context'))
        current['outputs']['can_frames']['window'] = 'unknown'
        with self.guard_static(), self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(current), base_dir=ROOT)
