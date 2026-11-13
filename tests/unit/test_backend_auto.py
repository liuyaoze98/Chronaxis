"""核对自动后端的静态选择、显式覆盖及实际运行；输入和期望值独立构造。"""

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from workspace_fixtures import TemporaryDirectory
from chronaxis import AnalysisPlan, AnalysisRunner, validate_analysis_plan, explain_analysis_plan
from chronaxis.planning.backend_selection import execution_plan, select_backend
from chronaxis.configuration.explanation import explanation_text
from chronaxis.execution.run_session import RunSession


def configuration(path, *, wide=False):
    """创建普通 CSV 实际积分。参数: 路径、宽表选项。返回: 配置。异常: 无。"""
    names = ('p', 'q') if wide else ('p',)
    return dict(config_version=4, dataset=dict(name='auto_test'),
        sources=[dict(name='table', source_type='signal_csv', path=str(path),
                      time_column='time', time=dict(unit='s'))],
        signals=[dict(name=name, source='table', field=name, dtype='float64',
                      unit='W', valid_for='2s') for name in names],
        calculations=[dict(name='energy', operation='integral', expr=' + '.join(names), unit='J')],
        execution=dict(backend='auto'), outputs=dict(tables='jsonl'))


class AutoBackendTests(unittest.TestCase):
    """选择不试读、不修改原计划；运行失败不切换后端。"""

    def test_omitted_backend_runs_and_resolves_without_rewriting_input(self):
        """省略后端的CSV得到200J；导出默认配置可重新运行，原用户文件不被改写。"""
        import json
        from chronaxis import load_analysis_plan
        from chronaxis.configuration.resolution import resolve_configuration
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'work'/'perf-auto-tests') as directory:
            root = Path(directory)
            source = root/'input.csv'
            source.write_text('time,p\n0,100\n1,100\n2,100\n', encoding='ascii')
            raw = configuration(source)
            raw.pop('execution')
            config = root/'analysis.json'
            config.write_text(json.dumps(raw), encoding='utf8')
            original = config.read_bytes()
            resolved = root/'resolved.json'
            resolve_configuration(config, output=resolved, defaults=True)
            self.assertEqual(json.loads(resolved.read_text(encoding='utf8'))['execution']['backend'], 'auto')
            for path in (config, resolved):
                plan = load_analysis_plan(path)
                self.assertEqual(plan.execution.backend, 'auto')
                self.assertEqual(explain_analysis_plan(plan).selected_backend, 'reference')
                with AnalysisRunner().run(plan, root/path.stem) as result:
                    row, = result.iter_calculations()
                    self.assertEqual((row.value, row.unit, row.status), (200., 'J', 'complete'))
                    self.assertEqual(result.metadata.backend, 'reference')
            self.assertEqual(config.read_bytes(), original)

    def test_static_choice_and_overrides_without_io(self):
        """静态入口在文件不存在时仍只报告声明，显式覆盖优先。"""
        plan = AnalysisPlan.from_dict(configuration('absent-auto.csv'))
        original = (plan.identity, plan.execution, plan.raw_config, plan.bindings)
        with patch.object(Path, 'open', side_effect=AssertionError('静态入口打开文件')), \
             patch.object(RunSession, '__init__', side_effect=AssertionError('静态入口启动运行')):
            report = explain_analysis_plan(plan)
            self.assertTrue(validate_analysis_plan(plan).valid)
            self.assertEqual((report.requested_backend, report.selected_backend), ('auto', 'reference'))
            self.assertEqual(report.nodes[0].backend, 'reference')
            self.assertIn('本次选择=reference', explanation_text(plan, report))
            from chronaxis.analysis_cli import explanation_json
            payload = explanation_json(report)
            self.assertEqual((payload['requested_backend'], payload['selected_backend']), ('auto', 'reference'))
            self.assertEqual(payload['backend_reason'], report.backend_reason)
            for backend in ('reference', 'numpy'):
                report = AnalysisRunner(backend).explain(plan)
                self.assertEqual((report.requested_backend, report.selected_backend), (backend, backend))
            view = execution_plan(plan)
            self.assertEqual(view.execution.backend, 'reference')
            self.assertIs(view.raw_config, plan.raw_config)
            self.assertIs(view.bindings, plan.bindings)
        self.assertEqual((plan.identity, plan.execution, plan.raw_config, plan.bindings), original)

    def test_unknown_categories_remain_numpy_and_invalid_choice_is_diagnostic(self):
        """宽表和未测统计保持 NumPy，未知 typed 后端不能借 auto 通过。"""
        wide = AnalysisPlan.from_dict(configuration('wide-auto.csv', wide=True))
        self.assertEqual(select_backend(wide).selected, 'numpy')
        raw = configuration('statistics-auto.csv')
        raw['calculations'].append(dict(name='spread', operation='sample_variance', expr='p'))
        self.assertEqual(select_backend(AnalysisPlan.from_dict(raw)).selected, 'numpy')
        bad = replace(wide, execution=replace(wide.execution, backend='typo'))
        self.assertFalse(validate_analysis_plan(bad).valid)
        self.assertEqual(explain_analysis_plan(bad).selected_backend, 'unavailable')

    def test_public_run_metadata_numbers_and_failure_no_retry(self):
        """三条100W记录积分200J，实际后端进入清单；失败只运行一次。"""
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'work'/'perf-auto-tests') as directory:
            root = Path(directory)
            source = root/'input.csv'
            source.write_text('time,p\n0,100\n1,100\n2,100\n', encoding='ascii')
            plan = AnalysisPlan.from_dict(configuration(source))
            for requested, selected in ((None, 'reference'), ('numpy', 'numpy'), ('reference', 'reference')):
                with AnalysisRunner(requested).run(plan, work_dir=root/str(requested)) as result:
                    row, = result.iter_calculations()
                    self.assertEqual((row.value, row.unit, row.status, int(row.quality)), (200., 'J', 'complete', 0))
                    self.assertEqual(result.metadata.backend, selected)
            with patch.object(RunSession, 'execute', side_effect=RuntimeError('single failure')) as execute:
                with self.assertRaisesRegex(Exception, 'single failure'):
                    AnalysisRunner().run(plan, work_dir=root/'failed')
                self.assertEqual(execute.call_count, 1)
            self.assertEqual(plan.execution.backend, 'auto')

    def test_host_reference_only_is_not_silently_selected(self):
        """宿主只有 reference 时，auto 的保守 NumPy 选择如实报不支持。"""
        from test_host_extensions_v4 import config, point_spec
        from chronaxis.extensions import ExtensionRegistry
        registry = ExtensionRegistry(functions=(point_spec([], array=False),))
        raw = config()
        raw['execution'] = dict(backend='auto')
        plan = AnalysisPlan.from_dict(raw, extensions=registry)
        report = AnalysisRunner(extensions=registry).validate(plan)
        self.assertFalse(report.valid)
        self.assertTrue(report.errors)
        self.assertTrue(AnalysisRunner('reference', extensions=registry).validate(plan).valid)

    def test_can_declarations_and_batch_override(self):
        """同帧 CAN 声明选 reference；批量 auto 沿用到每个独立任务。"""
        from chronaxis.batch.models import BatchPlan
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'work'/'perf-auto-tests') as directory:
            root = Path(directory)
            dbc, asc = root/'simple.dbc', root/'input.asc'
            dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 4 Node\n'
                           ' SG_ Voltage : 0|16@1+ (1,0) [0|65535] "V" Node\n'
                           ' SG_ Current : 16|16@1+ (1,0) [0|65535] "A" Node\n', encoding='ascii')
            asc.write_text('base hex timestamps absolute\n', encoding='ascii')
            raw = configuration(root/'unused.csv')
            raw['sources'] = [dict(name='bus', paths=[str(asc)], dbc_by_channel={'1':str(dbc)})]
            raw['signals'] = [dict(name=alias, source='bus', field=dict(channel=1, frame_id='0x100', signal=signal),
                dtype='float64', unit=unit, valid_for='1s')
                for alias, signal, unit in (('v', 'Voltage', 'V'), ('i', 'Current', 'A'))]
            raw['calculations'][0]['expr'] = 'v * i'
            plan = AnalysisPlan.from_dict(raw)
            with patch.object(Path, 'open', side_effect=AssertionError('选择读取输入')):
                self.assertEqual(select_backend(plan).selected, 'reference')
                self.assertTrue(AnalysisRunner().validate(plan).valid)
            batch = BatchPlan.from_dict(dict(batch_version=1, backend='auto',
                jobs=[dict(name='job', plan='future.json')]), base_dir=root)
            self.assertEqual(batch.backend, 'auto')
