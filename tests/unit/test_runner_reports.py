"""验证公共AnalysisRunner与共享静态报告的能力、后端视图及无输入I/O合同。

计划用现场小memory声明或明确不存在的CSV路径构造；构造后同时阻断来源adapter、
扫描、Path读取/创建、原配置重载及旧依赖导入，再调用根公开AnalysisRunner.validate/explain。
ready只表示已接入路径，真实字段、范围、单位未核警告及预算声明必须继续保留。
typed replace负例覆盖未支持来源、规则、窗口、九算子之外的operation和backend，不能
把literal True或字典索引异常当校验结果。双向后端覆盖只改有效execution view，
原sources/bindings/raw_config/identity均按对象保留；规则节点仍为state_driver。
另用全新Python子进程阻断NumPy和运行来源导入，核基本时间根入口仍只需标准库。
本专项不运行分析或写出结果，不改旧数值预期；独立证据由根写work并标home。
"""

from configuration_fixtures import current_fixture

# 共享公开入口用于正负例；子进程只用于隔离验证惰性导入，不执行任何输入分析。
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType
import unittest
from unittest.mock import patch
from chronaxis import AnalysisPlan, AnalysisRunner, explain_analysis_plan, validate_analysis_plan
from chronaxis.core.models import SourceSpec
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.observed_ingestion import ObservedSourceScan


class NoReadRows(tuple):
    """只容许常数时间的空/非空检查，禁止静态报告遍历或取原memory行。

    实例借已构建来源的同一批行，测试只暂时替换访问描述符，不重建SourceSpec。
    """

    def __iter__(self):
        """拒绝逐行走访。参数: 无。返回: 无。异常: AssertionError说明静态层读原行。"""
        raise AssertionError('静态报告遍历memory原行')

    def __getitem__(self, index):
        """拒绝索引或切片原行。参数: 原索引。返回: 无。异常: AssertionError说明静态层取行。"""
        raise AssertionError('静态报告索引memory原行')


class RunnerReportTests(unittest.TestCase):
    """静态报告只借原声明，测试不创建运行owner或依赖输入文件存在。"""

    def fixture(self, *, kind='memory', backend='numpy'):
        """创建含九算子、派生、活动及start_only的小计划，CSV路径故意不存在。

        参数: kind为memory/csv；backend为原计划执行后端。返回: 真AnalysisPlan。
        异常: 公共静态构建或样例声明错误直接失败；本函数不读写输入文件。
        """
        # 两种来源保持同一时钟和信号契约，区别只在已接入的读取路径。
        source = dict(name='table', source_type='memory' if kind == 'memory' else 'signal_csv',
            time=dict(time_type='relative', unit='ns', origin='runner-reports-home'))
        if kind == 'memory':
            source['rows'] = [dict(time=str(time)+'ns', values={'raw.a': value, 'raw.b': condition, 'raw.c': 1})
                for time, value, condition in ((0, 2, 1), (4, 4, 0), (10, 0, 0))]
        else:
            source.update(path='work/runner-reports-missing-source.csv', time_column='ns')
        # 八个信号口径加一个BOOL持续口径覆盖九operation，再加入真正事件/片段依赖。
        calculations = [dict(name='op_'+operation, scope='session', operation=operation, expr='a') for operation in
            ('sample_minimum', 'sample_maximum', 'sample_mean', 'min_time', 'max_time', 'time_weighted_mean', 'integral', 'select')]
        calculations += [dict(name='op_duration', scope='session', operation='duration', condition='b > 0'),
            dict(name='segment_area', scope='segment:context', operation='integral', expr='a', condition='b > 0'),
            dict(name='event_mean', scope='event:active', operation='time_weighted_mean', expr='a')]
        # pre=3ns大于TTL=2ns，手算a/b历史需求应为3；未用c无运行历史需求，仍保单位未核实。
        config = dict(config_version=4,
            dataset=dict(name='reports_dataset', entity='reports_entity', session='reports_session',
                domain=dict(start='0ns', end='10ns')), sources=[source],
            signals=[dict(name=name, source='table', field='raw.'+name, dtype='float64',
                unit=unit, valid_for='2ns') for name, unit in (('a', 'W'), ('b', '1'), ('c', 'custom_unit'))],
            derived={'twice': dict(expr='a * 2', unit='W')},
            rules=[dict(name='active', rule_type='condition_duration', condition='b > 0', minimum_duration='1ns'),
                dict(name='start', rule_type='start_only', condition='b > 0', emit_initial=True, window_duration='3ns')],
            windows=[dict(name='context', rule='active', anchor='activity', pre='3ns', post='0ns',
                merge='exit_delay', exit_delay='2ns'),
                dict(name='fixed', rule='start', anchor='point', pre='0ns', post='3ns', merge='none')],
            calculations=calculations, execution=dict(backend=backend, batch_rows=2, result_buffer_rows=1,
                memory_budget_bytes=256*1024**2), metadata={'device_label': 'home', 'data_kind': 'synthetic'})
        # 静态构建在阻断之前完成，之后不能再重放原配置或原rows来换掉typed声明。
        return AnalysisPlan.from_dict(current_fixture(config), base_dir=Path(__file__).resolve().parents[2])

    def guard_static(self):
        """阻断静态入口不得执行的文件、来源、重构或旧模块动作。

        参数: 无。返回: 调用方with使用的ExitStack。异常: 目标动作被执行时AssertionError。
        副作用: 仅with借期替换探针，退出即恢复，不创建目录或运行扫描。
        """
        # 每个调用方独立借一套探针，失败也必须恢复patch，不影响后续计划构造。
        stack = ExitStack()
        original_import = __import__

        def deny_runtime_import(name, globals=None, locals=None, fromlist=(), level=0):
            """拒绝执行层/旧reader依赖探测。参数: 原import参数。返回: 原模块。异常: 禁止目标AssertionError。"""
            # 绝对和相对import都覆盖，避免仅改import写法便绕过静态/运行边界。
            if (name in ('can', 'cantools', 'pandas', 'file_processor', 'dbc')
                    or name.startswith('RefProjects') or name.rsplit('.', 1)[-1] == 'run_session'
                    or 'run_session' in (fromlist or ())):
                raise AssertionError('静态报告尝试导入运行或旧reader模块：' + name)
            return original_import(name, globals, locals, fromlist, level)

        try:
            # 即使CSV路径不存在，报告也不得借文件探测或mkdir先产生副作用。
            for method in ('open', 'read_text', 'read_bytes', 'mkdir'):
                stack.enter_context(patch.object(Path, method, side_effect=AssertionError('静态报告触发Path.'+method)))
            stack.enter_context(patch('builtins.open', side_effect=AssertionError('静态报告触发open')))
            stack.enter_context(patch('builtins.__import__', deny_runtime_import))
            # 禁止创建真正来源/scan，以及通过重建计划/SourceSpec访问原始memory数据。
            for target in (BudgetedMemorySourceAdapter, BudgetedSignalCSVSourceAdapter, ObservedSourceScan):
                stack.enter_context(patch.object(target, '__init__', side_effect=AssertionError('静态报告创建来源或扫描')))
            stack.enter_context(patch.object(AnalysisPlan, 'from_dict', side_effect=AssertionError('静态报告重建原配置')))
            stack.enter_context(patch.object(SourceSpec, '__post_init__', side_effect=AssertionError('静态报告重构memory原行')))
            return stack
        except BaseException:
            # 安装中途失败仍撤销此前所有patch，原异常原样传播。
            stack.close()
            raise

    def test_public_validate_explain_share_real_capabilities_and_never_open_or_scan_inputs(self):
        """公共与直接静态入口同报告，合法计划ready仍保输入未核警告。参数: 无。返回: None。异常: 能力或I/O不符。"""
        # 四种组合都经过公开AnalysisRunner与共享函数，不能只有某个默认后端得到新能力状态。
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                plan = self.fixture(kind=kind, backend=backend)
                with self.guard_static():
                    direct = validate_analysis_plan(plan)
                    runner = AnalysisRunner()
                    validation = runner.validate(plan)
                    explanation = runner.explain(plan)
                    self.assertEqual(validation, direct)
                    self.assertEqual(explanation, explain_analysis_plan(plan))
                # ready表示路径存在；旧profile/legacy_sum仍明确不可用。
                self.assertTrue(validation.valid)
                self.assertEqual(validation.errors, ())
                self.assertTrue(validation.execution_ready)
                for key in ('configuration_static', 'memory', 'signal_csv', 'runner', 'bounded_result_publish',
                            'preset_expansion', 'time_calculations', 'selection_rows', 'window_segments', 'start_only'):
                    self.assertEqual(validation.capability_status[key], 'implemented')
                for key in ('legacy_profiles', 'legacy_sum'):
                    self.assertEqual(validation.capability_status[key], 'unavailable')
                # 已有来源/单位未验警告和预算声明必须保留，不把ready当实测证明。
                self.assertTrue(any('请求domain不证明实际观测范围' in warning for warning in validation.warnings))
                self.assertTrue(any('c：单位关系unverified' in warning for warning in validation.warnings))
                self.assertTrue(any('实际RAM峰值' in warning for warning in validation.warnings))
                self.assertFalse(any('完整AnalysisRunner及输入历史预算尚未接线' in warning for warning in validation.warnings))
                if kind == 'csv':
                    self.assertTrue(any('metadata_status=declared' in warning for warning in validation.warnings))
                self.assertEqual(explanation.plan_identity, plan.identity)
                self.assertEqual(explanation.source_names, ('table',))
                self.assertEqual(dict(explanation.history_ns), {'a': 3, 'b': 3})
                self.assertEqual(explanation.budget['memory_budget_bytes'], 256*1024**2)

    def test_static_reports_do_not_walk_or_index_original_memory_rows(self):
        """原memory行即使拒绝迭代和索引仍可解释。参数: 无。返回: None。异常: 原行被读取或来源被重构。"""
        plan = self.fixture()
        rows = NoReadRows(plan.sources[0].config.rows)

        def borrow_rows(source):
            """借只允许非空判断的原行tuple。参数: 原来源。返回: 原行受限视图。异常: 无。"""
            return rows

        # property临时遮住实例字段，不修改来源对象；len/bool仍是tuple的O(1)状态。
        with patch.object(SourceSpec, 'rows', new=property(borrow_rows), create=True), self.guard_static():
            self.assertTrue(AnalysisRunner().validate(plan).execution_ready)
            self.assertEqual(AnalysisRunner().explain(plan).plan_identity, plan.identity)

    def test_bidirectional_backend_override_preserves_original_objects_and_reports_actual_nodes(self):
        """双向覆盖只改有效execution，原声明身份和源绑定不变。参数: 无。返回: None。异常: 重构或后端标记不符。"""
        # 捕获AnalysisRunner实际传给共享报告的view，检查对象关系而非只看一段输出文本。
        import chronaxis.runner as module
        original_explain = module.explain_analysis_plan
        for declared, selected in (('numpy', 'reference'), ('reference', 'numpy')):
            plan = self.fixture(backend=declared)
            views = []

            def capture_view(effective):
                """记录共享报告实际收到的有效view。参数: plan view。返回: 真报告。异常: 原报告错误。"""
                # 原报告仍真正运行，不用伪造报告隐藏错误后端或身份。
                views.append(effective)
                return original_explain(effective)

            with self.guard_static(), patch.object(module, 'explain_analysis_plan', side_effect=capture_view):
                explanation = AnalysisRunner(backend=selected).explain(plan)
            # 声明身份不随执行选项改变，来源、绑定和原配置必须继续借原对象。
            self.assertEqual(len(views), 1)
            view = views[0]
            self.assertIsNot(view, plan)
            self.assertEqual(view.execution.backend, selected)
            self.assertEqual(plan.execution.backend, declared)
            self.assertEqual(view.identity, plan.identity)
            self.assertIs(view.raw_config, plan.raw_config)
            self.assertIs(view.sources, plan.sources)
            self.assertIs(view.bindings, plan.bindings)
            self.assertTrue(all(view.sources[index].config is source.config for index, source in enumerate(plan.sources)))
            self.assertEqual(explanation.plan_identity, plan.identity)
            # 规则保持状态驱动，其余真实数组/参考节点沿本次有效后端。
            for node in explanation.nodes:
                self.assertEqual(node.backend, 'state_driver' if node.node_type.startswith('rule:') else selected)
            self.assertTrue(explanation.validation.execution_ready)
        # None覆盖借原plan本体，不为一次静态查询生成输入或另一个声明身份。
        plan, views = self.fixture(), []

        def capture_original(effective):
            """观察无覆盖时原对象。参数: plan。返回: 真报告。异常: 原报告错误。"""
            # 默认选择不应无端构造另一个有效view。
            views.append(effective)
            return original_explain(effective)

        with self.guard_static(), patch.object(module, 'explain_analysis_plan', side_effect=capture_original):
            AnalysisRunner().explain(plan)
        self.assertIs(views[0], plan)

    def test_unsupported_typed_kind_operator_backend_and_scope_report_errors_without_keyerror(self):
        """typed替换未支持声明不能因原raw_config合法而误报ready。参数: 无。返回: None。异常: literal真或KeyError。"""
        # 原解析器拒绝这些声明；这里明确用typed replace检验报告不只返回literal真。
        original = self.fixture()
        cases = [replace(original, sources=(replace(original.sources[0], source_type='legacy_profile'),)),
            replace(original, sources=(replace(original.sources[0], source_type='frame_csv'),)),
            replace(original, execution=replace(original.execution, backend='cuda')),
            replace(original, rules=(replace(original.rules[0], rule_type='sequence'),) + original.rules[1:]),
            replace(original, calculations=(replace(original.calculations[0], operation='legacy_sum'),) + original.calculations[1:]),
            replace(original, windows=(replace(original.windows[0], merge='future_merge'),) + original.windows[1:]),
            replace(original, windows=(replace(original.windows[0], event='missing'),) + original.windows[1:]),
            replace(original, calculations=(replace(original.calculations[0], scope='event:missing'),) + original.calculations[1:]),
            replace(original, calculations=(replace(original.calculations[0], scope='segment:missing'),) + original.calculations[1:]),
            replace(original, outputs=replace(original.outputs, tables='xlsx')),
            replace(original, outputs=replace(original.outputs, can_frames=('unavailable',))),
            ]
        with self.assertRaises(ValueError):
            replace(original, config_version=2)
        # 每种替换都保原raw_config；重解析原配置会丢掉负例并被I/O/重构探针拒绝。
        for plan in cases:
            with self.subTest(errors_for=(plan.sources[0].source_type, plan.execution.backend, plan.rules[0].rule_type,
                    plan.calculations[0].operation, plan.calculations[0].scope, plan.windows[0].event, plan.outputs.tables)):
                with self.guard_static():
                    validation = AnalysisRunner().validate(plan)
                    explanation = AnalysisRunner().explain(plan)
                    self.assertEqual(validation, validate_analysis_plan(plan))
                self.assertFalse(validation.valid)
                self.assertFalse(validation.execution_ready)
                self.assertTrue(validation.errors)
                self.assertEqual(explanation.validation, validation)
                # 有错误仍保原声明身份和只读报告，不绕回raw_config重构来丢弃typed替换。
                self.assertEqual(explanation.plan_identity, original.identity)
                self.assertIs(plan.raw_config, original.raw_config)
        # 非法数值口径/后端必须在节点层也明确不可用，规则独立保留状态驱动事实。
        unknown_op = cases[4]
        with self.guard_static():
            explanation = AnalysisRunner().explain(unknown_op)
            unknown_backend = AnalysisRunner().explain(cases[2])
        self.assertEqual(next(node.backend for node in explanation.nodes
            if node.node_id == original.calculations[0].calculation_id), 'unavailable')
        self.assertTrue(all(node.backend == 'state_driver' if node.node_type.startswith('rule:')
            else node.backend == 'unavailable' for node in unknown_backend.nodes))

    def test_report_containers_and_dataclasses_are_immutable_without_claiming_measured_budget(self):
        """保持冻结模型/tuple/MappingProxy，预算仍是声明值。参数: 无。返回: None。异常: 可变结果或改输入。"""
        # 旧报告的只读形状是公共合同，能力变化不能变成可变结果容器。
        plan = self.fixture()
        with self.guard_static():
            validation = AnalysisRunner().validate(plan)
            explanation = AnalysisRunner().explain(plan)
        self.assertIs(type(validation.errors), tuple)
        self.assertIs(type(validation.warnings), tuple)
        self.assertIs(type(explanation.nodes), tuple)
        self.assertIs(type(explanation.source_names), tuple)
        for mapping in (validation.capability_status, explanation.history_ns, explanation.budget):
            self.assertIsInstance(mapping, MappingProxyType)
            with self.assertRaises(TypeError):
                mapping['mutated'] = 'bad'
        with self.assertRaises(FrozenInstanceError):
            validation.execution_ready = False
        with self.assertRaises(FrozenInstanceError):
            explanation.plan_identity = 'changed'
        # 数值逐字段等于原声明，没有预测或伪造实际执行峰值。
        self.assertEqual(dict(explanation.budget), dict(memory_budget_bytes=plan.execution.memory_budget_bytes,
            batch_rows=plan.execution.batch_rows, result_buffer_rows=plan.execution.result_buffer_rows,
            spool_quota_bytes=plan.execution.spool_quota_bytes))

    def test_public_static_type_errors_and_explicit_backend_validation_remain_clear(self):
        """类型错误保持TypeError，未知显式覆盖不静默回退。参数: 无。返回: None。异常: 错类型被吞或启动运行。"""
        # 错误调用不应借自动构建、默认NumPy或启动输入来掩盖用户拼写/类型问题。
        with self.guard_static():
            for value in (None, {}, object(), True):
                for function in (validate_analysis_plan, explain_analysis_plan, AnalysisRunner().validate, AnalysisRunner().explain):
                    with self.assertRaises(TypeError):
                        function(value)
            for backend in (1, True, object()):
                with self.assertRaises(TypeError):
                    AnalysisRunner(backend=backend)
            for backend in ('gpu', '', 'NumPy'):
                with self.assertRaises(ValueError):
                    AnalysisRunner(backend=backend)
        self.assertIsNone(AnalysisRunner().backend)

    def test_fresh_public_time_import_needs_no_numpy_or_runner_source_modules(self):
        """新进程阻断NumPy和运行来源仍可用根时间入口。参数: 无。返回: None。异常: 惰性导入回归或子进程失败。"""
        # 主测试模块已使用AnalysisRunner，只有全新解释器才能证明普通根时间导入没有运行依赖。
        script = '''import json
import sys
attempted = []
class RejectRuntime:
    """禁止基础时间导入探测NumPy、AnalysisRunner或执行来源。"""
    def find_spec(self, fullname, path=None, target=None):
        """拒绝运行依赖。参数: 原import查找参数。返回: None。异常: 禁止目标ImportError。"""
        if (fullname == 'numpy' or fullname.startswith('numpy.')
                or fullname == 'chronaxis.runner' or fullname.startswith('chronaxis.execution')
                or fullname in ('chronaxis.sources.memory', 'chronaxis.sources.signal_csv')):
            attempted.append(fullname)
            raise ImportError('basic time import attempted runtime dependency: '+fullname)
        return None
sys.meta_path.insert(0, RejectRuntime())
import chronaxis
from chronaxis import convert_time, parse_duration
assert convert_time('1', 'ns').time_ns == 1
assert parse_duration('2ns').time_ns == 2
assert not attempted, attempted
assert 'numpy' not in sys.modules
assert 'chronaxis.runner' not in sys.modules
assert 'chronaxis.execution.run_session' not in sys.modules
print(json.dumps({'device_label':'home','attempted':attempted,'time_ns':1,'runner_loaded':False}))
'''
        # 子进程继承同一真实包路径并禁pyc，断言stdout只有受控事实且无隐藏告警。
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf8')
        completed = subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[2],
            env=environment, capture_output=True, text=True, timeout=30, check=True)
        result = json.loads(completed.stdout)
        self.assertEqual(result, dict(device_label='home', attempted=[], time_ns=1, runner_loaded=False))
        self.assertEqual(completed.stderr, '')
