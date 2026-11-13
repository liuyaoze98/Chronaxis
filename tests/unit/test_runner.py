"""从真正公共AnalysisRunner贯通真实来源、事件、指标、片段及独立结果发布。

每例先把来源单位、整数纳秒、valid_for、规则和预算写入完整JSON并load_analysis_plan。
公共run才读取真实memory或CSV，期望来自手算值和父关联，不手造内部阶段。
专项覆盖两个后端及切批、所有九个算子、持续/边沿/start_only、多来源实际域、
空输入与真实单点、后端覆盖、单次来源扫描、可重复导出、稳定实际输入身份和失败关闭。
内部资源通过真实close及文件游标观察，返回AnalysisResult只拥有最终暂存及其费用；
所有合成产物保留在新项目work并标home，不写RefProjects，不修改旧测试或算法。
"""
from published_paths import published_file


from configuration_fixtures import current_fixture

# 公共入口是唯一运行路径；内部类型只用于观察真实读取次数和关闭责任。
from contextlib import ExitStack, contextmanager
import csv
import json
from pathlib import Path
import platform
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
import numpy as np
from chronaxis import AnalysisRunner, load_analysis_plan, AnalysisResult, AnalysisError
from chronaxis.core.models import Interval
from chronaxis.core.selection import SelectionRow
from chronaxis.core.types import QualityFlag as Q
from chronaxis.execution.csv_observation import CSVObservationRead
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter, _CSVRequest
from chronaxis.execution.record_session_calculations import RecordSessionCalculations
from chronaxis.execution.record_source_cursor import RecordSourceCursor
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.run_session import RunSession
from chronaxis.results.codec import decode_row
from chronaxis.results.errors import BudgetExceededError, ResultClosedError


class RunnerTests(unittest.TestCase):
    """各计划和运行目录互相独立，公共结果显式close后共享RAM必须归零。"""

    def fixture(self, *, kind='memory', backend='numpy', size=2, table_format='csv',
                rows=((0, 2), (1, 4), (3, 0), (5, 6), (8, 0)),
                other_rows=((0, 10), (5, 10)), rules=None, windows=None, calculations=None,
                signals=True, budget=256 * 1024 ** 2, domain=(0, 12), diagnostics=None):
        """先保存完整声明，公共run之前不创建adapter或人工运行绑定。

        参数: kind为memory/csv；backend原声明后端；size真实批次，None省略以采用公共默认；table_format为csv/jsonl；
            rows/other_rows原时间和值，None不声明第二来源；rules/windows/calculations可覆盖；
            signals=False保留原行但空投影；budget为RAM bytes；domain为原请求ns。
        返回: work/config/path/plan命名空间。异常: 原文件或公共load_analysis_plan校验错误传播。
        """
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/public-runner' / uuid4().hex
        work.mkdir(parents=True)
        config = {'config_version': 4,
            'dataset': {'name': 'runner_dataset', 'entity': 'runner_device', 'session': 'runner_session',
                'domain': {'start': str(domain[0]) + 'ns', 'end': str(domain[1]) + 'ns'}},
            'sources': [], 'signals': [], 'derived': {'twice': {'expr': 'a * 2', 'unit': '1'}} if signals else {},
            'rules': ([dict(name='z_duration', rule_type='condition_duration', duration_comparison='>=', condition='a > 0', minimum_duration='0ns'),
                      dict(name='a_rising', rule_type='rising_edge', condition='a > 0', emit_initial=True),
                      dict(name='m_start', rule_type='start_only', condition='a > 0', emit_initial=True, window_duration='4ns')]
                if rules is None else rules),
            'windows': ([dict(name='z_context', rule='z_duration', anchor='activity', pre='0ns', post='0ns',
                            merge='exit_delay', exit_delay='2ns'),
                        dict(name='a_context', rule='a_rising', anchor='point', pre='0ns', post='1ns'),
                        dict(name='m_context', rule='m_start', anchor='point', pre='0ns', post='4ns')]
                if windows is None else windows),
            'calculations': ([dict(name='z_integral', scope='session', operation='integral', expr='a'),
                         dict(name='y_min_samples', scope='session', operation='sample_minimum', expr='a'),
                         dict(name='x_max_samples', scope='session', operation='sample_maximum', expr='a'),
                         dict(name='w_mean_samples', scope='session', operation='sample_mean', expr='a'),
                         dict(name='v_min_time', scope='session', operation='min_time', expr='a'),
                         dict(name='u_max_time', scope='session', operation='max_time', expr='a'),
                         dict(name='t_mean_time', scope='session', operation='time_weighted_mean', expr='a'),
                         dict(name='s_duration', scope='session', operation='duration', condition='a > 0'),
                         dict(name='r_select', scope='session', operation='select', expr='twice', condition='a >= 4'),
                         dict(name='q_event_integral', scope='event:z_duration', operation='integral', expr='a'),
                         dict(name='p_segment_integral', scope='segment:z_context', operation='integral', expr='a'),
                         dict(name='o_short_integral', scope='session', operation='integral', expr='b')]
                if calculations is None else calculations),
            'execution': {'backend': backend, 'batch_rows': size, 'result_buffer_rows': 1,
                'memory_budget_bytes': budget}, 'outputs': {'tables': table_format, 'manifest': 'json'},
            'metadata': {'device_label': 'home', 'data_kind': 'synthetic'}}
        if diagnostics is not None:
            config['diagnostics'] = diagnostics
        # 省略配置项才是真正默认batch_rows，不能手填一个相同数字冒充默认加载路径。
        if size is None:
            del config['execution']['batch_rows']
        sources = [('table', 'a', 'raw.a', rows)]
        if other_rows is not None:
            sources.append(('other', 'b', 'raw.b', other_rows))
        for name, alias, field, raw in sources:
            source = dict(name=name, source_type='memory' if kind == 'memory' else 'signal_csv',
                time=dict(time_type='relative', unit='ns', origin='runner_home_clock'))
            if kind == 'memory':
                source['rows'] = [dict(time=str(time) + 'ns', values={field: value}) for time, value in raw]
            else:
                path = work / (name + '.csv')
                path.write_text('ns,' + field + '\n' + ''.join(str(time) + ',' +
                    ('' if value is None else str(value)) + '\n' for time, value in raw), encoding='utf-8', newline='')
                source.update(path=path.name, time_column='ns')
            config['sources'].append(source)
            if signals:
                config['signals'].append(dict(name=alias, source=name, field=field,
                    dtype='float64', unit='1', valid_for='20ns'))
        path = work / 'plan.json'
        path.write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        return SimpleNamespace(work=work, config=config, path=path, plan=load_analysis_plan(path))

    def public_run(self, data, *, runner=None, work_dir=None):
        """只调用公共AnalysisRunner并登记独立结果清理，不主动发布。

        参数: data真实计划；runner可提供后端覆盖；work_dir可显式新目录或None。
        返回: 原AnalysisResult。异常: 公共run原错误传播，未交付结果由生产owner清理。
        """
        result = (AnalysisRunner() if runner is None else runner).run(data.plan, work_dir=work_dir)
        self.addCleanup(result.close)
        self.assertIs(type(result), AnalysisResult)
        self.assertEqual(result.status, 'analysis_complete')
        self.assertEqual(result.run_manifest['status'], 'analysis_complete')
        self.assertEqual(result.metadata.plan_hash, data.plan.identity)
        return result

    def rows(self, result):
        """有限手算夹具读取三张真实结果表，各游标耗尽后显式幂等关闭。

        参数: result活AnalysisResult。返回: events/segments/calculations命名空间tuple。
        异常: 真实读取、格式或关闭错误传播，不重新运行来源。
        """
        values = {}
        for name, factory in (('events', result.iter_events), ('segments', result.iter_segments), ('calculations', result.iter_calculations), ('selections',result.iter_selections)):
            reader = factory()
            try:
                values[name] = tuple(reader)
            finally:
                reader.close()
        return SimpleNamespace(**values)

    def close_result(self, result):
        """结果最后释放后检查真实共享费用为零、文件保留且不可继续读取。

        参数: result公共返回结果。返回: None。异常: 重复释放、文件丢失或账目错误断言失败。
        """
        budget, files = result.spool.budget, tuple(result.spool.files.values())
        result.close()
        result.close()
        self.assertEqual(budget.ram_bytes, 0)
        self.assertTrue(all(path.exists() == result.metadata.retain_work for path in files))
        with self.assertRaises(ResultClosedError):
            result.iter_events()

    @contextmanager
    def observe(self):
        """观察当前实际来源、游标和资源关闭，不构造已退役历史阶段。"""
        evidence=SimpleNamespace(closed={},sessions=[],effective_plans=[],readers=[],source_handles=[],reads=[],scans=[])
        classes=(RecordSessionCalculations,RecordSourceCursor,BudgetedMemorySourceAdapter,BudgetedSignalCSVSourceAdapter,AnalysisResult)
        def close_wrapper(original,name):
            """记录真实owner及已确认来源端点，再调用原close。"""
            def invoke(owner):
                owners=evidence.closed.setdefault(name,[])
                if not any(item is owner for item in owners):
                    owners.append(owner)
                    if isinstance(owner,RecordSourceCursor):
                        evidence.scans.append((owner.source_name,owner.observed_start,owner.observed_end,owner._finished))
                return original(owner)
            return invoke
        def read_wrapper(original,kind):
            """记录真实批读取对象；不收集或替换输入数据。"""
            def invoke(owner,request,**kwargs):
                evidence.reads.append((kind,owner,request))
                reader=original(owner,request,**kwargs)
                evidence.readers.append(reader)
                return reader
            return invoke
        init=RunSession.__init__
        def session_init(owner,plan,work_dir=None):
            """记录真实会话及有效计划，保留原构造。"""
            evidence.sessions.append(owner);evidence.effective_plans.append(plan)
            return init(owner,plan,work_dir=work_dir)
        close_handle=BudgetedSignalCSVSourceAdapter._close_handle
        def closed_handle(owner,handle,primary):
            """观察同一真实CSV句柄的关闭，不代替产品清理。"""
            evidence.source_handles.append(handle)
            return close_handle(owner,handle,primary)
        with ExitStack() as stack:
            for cls in classes:
                stack.enter_context(patch.object(cls,'close',new=close_wrapper(cls.close,cls.__name__)))
            stack.enter_context(patch.object(RunSession,'__init__',new=session_init))
            stack.enter_context(patch.object(BudgetedSignalCSVSourceAdapter,'_close_handle',new=closed_handle))
            stack.enter_context(patch.object(BudgetedMemorySourceAdapter,'iter_batches',new=read_wrapper(BudgetedMemorySourceAdapter.iter_batches,'memory')))
            stack.enter_context(patch.object(BudgetedSignalCSVSourceAdapter,'iter_batches',new=read_wrapper(BudgetedSignalCSVSourceAdapter.iter_batches,'csv')))
            yield evidence

    def test_public_memory_csv_backends_splits_nine_operators_and_real_parents(self):
        """十二种真实运行核九算子、三种规则和父关联，业务排序不能重编全局生成序号。

        参数: 无。返回: None。异常: 数值、批次一致性、源缺失或父关系错误断言失败。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        data = self.fixture(kind=kind, backend=backend, size=size)
                        result = self.public_run(data, work_dir=data.work / 'run')
                        tables = self.rows(result)
                        self.assertEqual(result.metadata.backend, backend)
                        events = tables.events
                        self.assertEqual(len(events), 6)
                        duration = tuple(row for row in events if row.rule_id == 'z_duration')
                        self.assertEqual(tuple((row.start_ns, row.end_ns) for row in duration), ((0, 3), (5, 8)))
                        for rule in ('a_rising', 'm_start'):
                            self.assertEqual(tuple(row.start_ns for row in events if row.rule_id == rule), (0, 5))
                        # 先核真实行数再建索引，防止字典覆盖重复行或后续zip截断多余结果。
                        session_rows = tuple(row for row in tables.calculations if row.scope == 'session')
                        scalar_rows = session_rows
                        self.assertEqual(len(tables.calculations), 12)
                        self.assertEqual(len(session_rows), 9)
                        self.assertEqual(len(scalar_rows), 9)
                        scalars = {row.calculation_id: row for row in scalar_rows}
                        expected = {'z_integral': 28e-9, 'y_min_samples': 0, 'x_max_samples': 6, 'w_mean_samples': 3,
                            'v_min_time': 0, 'u_max_time': 6, 't_mean_time': 3.5, 's_duration': 6e-9, 'o_short_integral': 50e-9}
                        self.assertEqual(set(scalars), set(expected))
                        for identifier, value in expected.items():
                            # 这些秒单位积分/时长来自整数纳秒，绝对容差须远小于1ns，防止0被当作正确小量。
                            if identifier in ('z_integral', 's_duration', 'o_short_integral'):
                                self.assertAlmostEqual(scalars[identifier].value, value, delta=1e-18)
                            else:
                                self.assertAlmostEqual(scalars[identifier].value, value)
                        self.assertEqual(scalars['o_short_integral'].status,'partial')
                        selected = tuple(row for row in tables.selections if row.calculation_id == 'r_select')
                        self.assertEqual(tuple((row.time_ns, row.value) for row in selected), ((1, 8), (5, 12)))
                        segment = next(row for row in tables.segments if row.window_id == 'z_context')
                        self.assertEqual((segment.start_ns, segment.end_ns), (0, 8))
                        self.assertEqual(set(segment.parent_event_ids), {row.event_id for row in duration})
                        event_calculations = tuple(row for row in tables.calculations if row.scope == 'event')
                        self.assertEqual(len(event_calculations), 2)
                        self.assertEqual({row.parent_id for row in event_calculations}, {row.event_id for row in duration})
                        for actual, expected_value in zip(sorted(row.value for row in event_calculations), (10e-9, 18e-9)):
                            self.assertAlmostEqual(actual, expected_value, delta=1e-18)
                        segment_calculations = tuple(row for row in tables.calculations if row.scope == 'segment')
                        self.assertEqual(len(segment_calculations), 1)
                        segment_calculation = segment_calculations[0]
                        self.assertEqual(segment_calculation.parent_id, segment.segment_id)
                        self.assertAlmostEqual(segment_calculation.value, 28e-9, delta=1e-18)
                        all_rows = tables.events + tables.segments + tables.calculations + tables.selections
                        self.assertEqual(sorted(row.sequence for row in all_rows), list(range(len(all_rows))))
                        self.assertNotEqual(tuple(row.sequence for row in events), tuple(range(len(events))))
                        # 初始点先交付，duration要到3ns才结束；不得按最后事件业务顺序重新编号。
                        self.assertEqual(next(row.sequence for row in events if row.rule_id == 'a_rising'
                            and row.start_ns == 0), 0)
                        self.assertGreater(next(row.sequence for row in duration if row.start_ns == 0),
                            next(row.sequence for row in events if row.rule_id == 'a_rising' and row.start_ns == 0))
                        self.assertLessEqual(result.spool.peak_buffer_rows, 1)
                        self.close_result(result)

    def test_backend_override_changes_actual_metadata_and_explain_without_mutating_plan(self):
        """双向后端覆盖只改变执行选择，原计划身份、声明和来源对象保持。

        参数: 无。返回: None。异常: 静默fallback、explain与运行不符或原计划被改断言失败。
        """
        for declared, actual in (('numpy', 'reference'), ('reference', 'numpy')):
            data = self.fixture(backend=declared)
            original = (data.plan.identity, data.plan.execution, data.plan.raw_config, data.plan.bindings,
                tuple(source.config for source in data.plan.sources))
            runner = AnalysisRunner(backend=actual)
            with self.observe() as evidence:
                report = runner.explain(data.plan)
                self.assertEqual(evidence.reads, [])
                result = self.public_run(data, runner=runner, work_dir=data.work / 'override')
            self.assertEqual(result.metadata.backend, actual)
            self.assertEqual(report.plan_identity, original[0])
            self.assertTrue(report.validation.execution_ready)
            self.assertEqual(report.validation.capability_status['runner'], 'implemented')
            for node in report.nodes:
                self.assertEqual(node.backend, 'state_driver' if node.node_type.startswith('rule:') else actual)
            self.assertEqual(data.plan.execution.backend, declared)
            self.assertIs(data.plan.execution, original[1])
            self.assertIs(data.plan.raw_config, original[2])
            self.assertIs(data.plan.bindings, original[3])
            self.assertTrue(all(source.config is prior for source, prior in zip(data.plan.sources, original[4])))
            self.assertEqual(result.metadata.backend,actual)
            self.assertIs(evidence.effective_plans[0].bindings, data.plan.bindings)
            self.assertEqual(evidence.effective_plans[0].identity, data.plan.identity)
            self.close_result(result)

    def test_default_source_batch_size_runs_small_real_plan_with_declared_budget(self):
        """不写batch_rows的真实小计划在原256MiB预算内完成，来源默认不被内部调度改写。

        参数: 无。返回: None。异常: 默认计划不可执行、预算被提高或原配置被改断言失败。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                data = self.fixture(kind=kind, backend=backend, size=None, other_rows=None,
                    rows=((0, 2), (1, 4), (3, 0)), domain=(0, 4),
                    rules=[dict(name='active', rule_type='condition_duration', duration_comparison='>=', condition='a > 0', minimum_duration='0ns')],
                    windows=[dict(name='whole', rule='active', anchor='activity', pre='0ns', post='1ns')],
                    calculations=[dict(name='area', scope='session', operation='integral', expr='a')])
                self.assertNotIn('batch_rows', data.config['execution'])
                source_batch_rows = data.plan.execution.batch_rows
                with self.observe() as evidence:
                    result = self.public_run(data, work_dir=data.work / 'default-batch-run')
                    rows = self.rows(result)
                    self.assertEqual(len(rows.events), 1)
                    self.assertAlmostEqual(rows.calculations[0].value, 10e-9, delta=1e-18)
                    self.assertEqual(len(evidence.reads), 1)
                    self.assertEqual(evidence.reads[0][2].batch_rows, source_batch_rows)
                self.assertEqual(data.plan.execution.batch_rows, source_batch_rows)
                self.assertEqual(result.spool.budget.memory_budget_bytes, 256 * 1024 ** 2)
                self.close_result(result)

    def test_single_scan_internal_resources_closed_before_return_and_no_reads_on_export(self):
        """公共run返回前关闭所有输入及四阶段，回读和两次写出只读取最终暂存。

        参数: 无。返回: None。异常: 重扫来源、内部FD未关或转移结果费用错误断言失败。
        """
        for kind in ('memory', 'csv'):
            data = self.fixture(kind=kind)
            with self.observe() as evidence:
                result = self.public_run(data, work_dir=data.work / 'owned-run')
                self.assertEqual(len(evidence.reads), 2)
                self.assertEqual(len({id(item[1]) for item in evidence.reads}), 2)
                self.assertEqual(len(evidence.sessions), 1)
                self.assertTrue(evidence.sessions[0].closed)
                for cls in (RecordSessionCalculations,RecordSourceCursor):
                    self.assertTrue(evidence.closed.get(cls.__name__), cls.__name__)
                    self.assertTrue(all(owner._closed for owner in evidence.closed[cls.__name__]))
                adapter_name = BudgetedMemorySourceAdapter.__name__ if kind == 'memory' else BudgetedSignalCSVSourceAdapter.__name__
                self.assertEqual(len(evidence.closed[adapter_name]), 2)
                self.assertTrue(all(owner.closed for owner in evidence.closed[adapter_name]))
                self.assertTrue(evidence.readers)
                self.assertTrue(all(reader.closed for reader in evidence.readers))
                self.assertTrue(all(handle.closed for handle in evidence.source_handles))
                self.assertTrue(all(owner._closed for owner in evidence.closed.get(AnalysisResult.__name__,[]) if owner is not result))
                self.assertEqual(result.spool.budget.ram_bytes, result._held_cost + result.spool._held_cost)
                tables = self.rows(result)
                first = result.write(data.work / 'export-first')
                second = result.write(data.work / 'export-second')
                self.assertEqual(first.status, 'completed')
                self.assertEqual(first.row_counts, second.row_counts)
                self.assertEqual(self.rows(result).events, tables.events)
                self.assertEqual(len(evidence.reads), 2)
                self.assertEqual((published_file(first,'events.csv')).read_bytes(), (published_file(second,'events.csv')).read_bytes())
                self.close_result(result)

    def test_csv_and_jsonl_manifest_describe_real_run_and_roundtrip_typed_rows(self):
        """当前双格式保精确数值与父关联；清单不伪造未请求的输入身份或旧语义版本。"""
        from chronaxis.results.summary import summary_fields
        for fmt in ('csv','jsonl'):
            data=self.fixture(kind='csv',table_format=fmt)
            result=self.public_run(data,work_dir=data.work/'publish-run')
            rows=self.rows(result);manifest=result.write(data.work/'published')
            document=json.loads(manifest.manifest_path.read_text(encoding='utf-8'))
            self.assertEqual(document['status'],'completed')
            self.assertEqual(document['run']['backend'],data.plan.execution.backend)
            self.assertEqual(document['run']['plan_hash'],data.plan.identity)
            self.assertEqual(document['run']['config_version'],4)
            self.assertEqual(document['run']['device_label'],'home')
            self.assertNotIn('semantic_version',document['run'])
            self.assertNotIn('input_identity',document['run'])
            self.assertEqual(document['resources']['memory_budget_bytes'],data.plan.execution.memory_budget_bytes)
            self.assertLessEqual(document['resources']['peak_ram_estimated_bytes'],data.plan.execution.memory_budget_bytes)
            self.assertEqual(document['resources']['whole_process_rss'],'not_measured')
            self.assertEqual(document['row_counts'],{name:len(getattr(rows,name)) for name in ('events','segments','calculations','selections')})
            for table in ('events','segments','calculations','selections'):
                expected=getattr(rows,table);path=published_file(manifest,table+'.'+fmt)
                if fmt=='jsonl':
                    self.assertEqual(tuple(decode_row(line,result.spool.max_row_bytes) for line in path.read_bytes().splitlines(keepends=True)),expected)
                else:
                    with path.open(encoding='utf-8',newline='') as handle:actual=list(csv.DictReader(handle))
                    self.assertEqual(len(actual),len(expected))
                    for packed,row in zip(actual,expected):
                        fields=summary_fields(row)
                        self.assertEqual(set(packed),set(fields))
                        for key,value in fields.items():
                            if key=='parent_event_ids':
                                self.assertEqual(json.loads(packed[key]),list(value))
                            else:
                                self.assertEqual(packed[key],'' if value is None else str(value))
                        self.assertNotIn('row_json',packed)
            self.close_result(result)

    def test_default_work_directories_are_unique_and_repeated_runs_are_independent(self):
        """同一个AnalysisRunner两次默认目录各自独立，同计划事实身份稳定且互不关闭结果。

        参数: 无。返回: None。异常: 复用暂存、UUID污染输入身份或跨结果关闭断言失败。
        """
        data = self.fixture()
        runner = AnalysisRunner()
        first, second = self.public_run(data, runner=runner), self.public_run(data, runner=runner)
        self.assertNotEqual(first.spool.path, second.spool.path)
        self.assertNotEqual(first.metadata.run_id, second.metadata.run_id)
        self.assertEqual(first.metadata.input_identity, second.metadata.input_identity)
        self.assertEqual(self.rows(first).events, self.rows(second).events)
        self.close_result(first)
        self.assertTrue(self.rows(second).events)
        self.close_result(second)

    def test_existing_work_path_rejected_and_customer_named_path_is_allowed(self):
        """已有工作目录原内容保留，测试根内的客户同名目录可正常分析。

        参数: 无。返回: None。异常: 覆盖已有内容或尝试向历史快照写目录断言失败。
        """
        data = self.fixture()
        existing = data.work / 'existing'
        existing.mkdir()
        marker = existing / 'user.txt'
        marker.write_text('keep this original file', encoding='utf-8')
        with self.assertRaises(AnalysisError) as existing_error:
            AnalysisRunner().run(data.plan, work_dir=existing)
        self.assertIsInstance(existing_error.exception.__cause__, FileExistsError)
        self.assertEqual(tuple(existing.iterdir()), (marker,))
        self.assertEqual(marker.read_text(encoding='utf-8'), 'keep this original file')
        customer=data.work/'RefProjects'
        customer.mkdir()
        sentinel=customer/'user.txt'
        sentinel.write_bytes(b'keep')
        result=AnalysisRunner().run(data.plan,work_dir=customer/'analysis')
        try:
            self.assertTrue(self.rows(result).events)
        finally:
            self.close_result(result)
        self.assertEqual(sentinel.read_bytes(),b'keep')

    def test_validate_and_explain_do_not_read_sources_or_hide_unknown_backend(self):
        """静态公共检查不读来源、不建RunSession，非法后端及plan类型明确拒绝。

        参数: 无。返回: None。异常: 静态入口提前I/O、隐式fallback或接受错误对象断言失败。
        """
        data = self.fixture(kind='csv')
        runner = AnalysisRunner()
        self.assertIsNone(runner.backend)
        with patch.object(RunSession, '__init__', side_effect=AssertionError('静态检查创建运行会话')):
            with patch.object(Path, 'open', side_effect=AssertionError('静态检查读取输入文件')):
                validation = runner.validate(data.plan)
                report = runner.explain(data.plan)
                self.assertTrue(validation.valid)
                self.assertTrue(validation.execution_ready)
                self.assertEqual(report.validation, validation)
            with self.assertRaises(TypeError):
                runner.run(data.config)
        with self.assertRaises(ValueError):
            AnalysisRunner(backend='gpu')
        with self.assertRaises(TypeError):
            AnalysisRunner(backend=True)

    def test_empty_true_input_has_no_events_segments_or_selection_and_exact_null_stats(self):
        """空输入无活动、片段或选择；标量返回明确未知，不能伪造零值。"""
        for kind in ('memory','csv'):
            for backend in ('reference','numpy'):
                data=self.fixture(kind=kind,backend=backend,rows=(),other_rows=None,
                    rules=[dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='True',minimum_duration='0ns')],
                    windows=[dict(name='whole',rule='active',anchor='activity',pre='0ns',post='1ns')],
                    calculations=[dict(name='area',scope='session',operation='integral',expr='a'),
                        dict(name='duration',scope='session',operation='duration',condition='True'),
                        dict(name='selected',scope='session',operation='select',expr='a'),
                        dict(name='segment_area',scope='segment:whole',operation='integral',expr='a')])
                result=self.public_run(data,work_dir=data.work/'empty-run');rows=self.rows(result)
                self.assertEqual(rows.events+rows.segments+rows.selections,())
                self.assertEqual({r.calculation_id for r in rows.calculations},{'area','duration'})
                for row in rows.calculations:
                    self.assertEqual((row.value,row.reason,row.status),(None,'no_observation','indeterminate'))
                    self.assertEqual(row.scope,'session');self.assertIsNone(row.parent_id)
                self.close_result(result)

    def test_real_single_point_preserves_initial_event_and_actual_point(self):
        """真实单点按显式initial产出点事件；N−1间隔为空，片段明确标empty。

        参数: 无。返回: None。异常: 单点误当全空、额外持续或默认rising被初始化断言失败。
        """
        rules = [dict(name='active', rule_type='rising_edge', condition='a > 0', emit_initial=True),
                 dict(name='default_rising', rule_type='rising_edge', condition='a > 0'),
                 dict(name='duration', rule_type='condition_duration', duration_comparison='>=', condition='True', minimum_duration='0ns')]
        windows = [dict(name='whole', rule='active', anchor='point', pre='1ns', post='1ns')]
        calculations = [dict(name='area', scope='session', operation='integral', expr='a')]
        for kind in ('memory', 'csv'):
            data = self.fixture(kind=kind, rows=((8, 4),), other_rows=None, rules=rules, windows=windows, calculations=calculations)
            result = self.public_run(data, work_dir=data.work / 'point-run')
            rows = self.rows(result)
            self.assertEqual(len(rows.events), 1)
            event = rows.events[0]
            self.assertEqual((event.start_ns, event.confirmed_ns, event.end_ns, event.trigger), (8, 8, None, 'initial'))
            self.assertEqual((rows.segments[0].start_ns,rows.segments[0].end_ns,rows.segments[0].status),(None,None,'empty'))
            self.assertIsNone(rows.calculations[0].value)
            self.assertEqual(rows.calculations[0].status,'indeterminate')
            self.close_result(result)

    def test_requested_input_integrity_tracks_raw_start_with_same_plan_path(self):
        """同一路径同配置的所需输入摘要稳定；实际首端变化后摘要必须变化。"""
        data=self.fixture(kind='csv',rows=((1,2),(5,3)),other_rows=None,signals=True,rules=[],windows=[],
                          calculations=[dict(name='area',scope='session',operation='integral',expr='a')],
                          diagnostics={'integrity':True})
        first=self.public_run(data,work_dir=data.work/'first-facts')
        repeated=self.public_run(data,work_dir=data.work/'same-facts')
        self.assertEqual(first.metadata.input_diagnostics,repeated.metadata.input_diagnostics)
        initial,=first.metadata.input_diagnostics
        self.assertTrue(initial.source_eof)
        self.assertEqual(initial.record_count,2)
        self.assertIsNotNone(initial.sha256)
        (data.work/'table.csv').write_text('ns,raw.a\n2,2\n5,3\n',encoding='utf-8',newline='')
        changed=self.public_run(data,work_dir=data.work/'changed-facts')
        final,=changed.metadata.input_diagnostics
        self.assertEqual(final.record_count,2)
        self.assertNotEqual(initial.sha256,final.sha256)
        self.assertEqual(first.metadata.plan_hash,changed.metadata.plan_hash)
        for result in (first,repeated,changed):self.close_result(result)

    def test_raw_rows_without_declared_fields_still_define_constant_activity_and_duration(self):
        """无声明字段仍保真实1–5ns原行范围，常量规则和会话时长不按全空处理。

        参数: 无。返回: None。异常: 没字段就丢原行观测、借请求起点或补时长断言失败。
        """
        rules = [dict(name='active', rule_type='condition_duration', duration_comparison='>=', condition='True', minimum_duration='2ns')]
        windows = [dict(name='whole', rule='active', anchor='activity', pre='0ns', post='1ns')]
        calculations = [dict(name='session_duration', scope='session', operation='duration', condition='True'),
                   dict(name='event_duration', scope='event:active', operation='duration', condition='True'),
                   dict(name='segment_duration', scope='segment:whole', operation='duration', condition='True')]
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                with self.subTest(kind=kind, backend=backend):
                    data = self.fixture(kind=kind, backend=backend, rows=((1, 2), (5, 3)), other_rows=None,
                        signals=False, rules=rules, windows=windows, calculations=calculations)
                    self.assertEqual(data.plan.signals, ())
                    with self.observe() as evidence:
                        result = self.public_run(data, work_dir=data.work / 'raw-without-fields')
                        rows = self.rows(result)
                    self.assertEqual(len(evidence.reads), 1)
                    self.assertEqual(evidence.reads[0][2].signal_names, ())
                    self.assertEqual(evidence.scans[0][1:], (1, 5, True))
                    self.assertEqual(len(rows.events), 1)
                    event = rows.events[0]
                    self.assertEqual((event.start_ns, event.confirmed_ns, event.end_ns, event.status), (1, 3, 5, 'truncated'))
                    self.assertEqual(len(rows.segments), 1)
                    segment = rows.segments[0]
                    self.assertEqual((segment.start_ns,segment.end_ns),(1,5))
                    self.assertEqual(segment.parent_event_ids, (event.event_id,))
                    values = {row.calculation_id: row for row in rows.calculations}
                    self.assertEqual(set(values), {'session_duration', 'event_duration', 'segment_duration'})
                    for row in values.values():
                        self.assertAlmostEqual(row.value, 4e-9, delta=1e-18)
                    self.assertEqual(values['event_duration'].parent_id, event.event_id)
                    self.assertEqual(values['segment_duration'].parent_id, segment.segment_id)
                    self.close_result(result)

    def test_budget_failure_has_highest_owner_and_does_not_return_partial_result(self):
        """真实限额不足拒绝公共运行，保最高恢复owner且不交付部分AnalysisResult。

        参数: 无。返回: None。异常: 越限继续、隐藏错误或恢复后费用非零断言失败。
        """
        data = self.fixture(budget=1)
        with self.observe() as evidence:
            with self.assertRaises(BudgetExceededError) as caught:
                AnalysisRunner().run(data.plan, work_dir=data.work / 'too-small')
        recovery = getattr(caught.exception, 'runner_cleanup_owner', None)
        self.assertIsNotNone(recovery)
        recovery.close()
        self.assertTrue(recovery.closed)
        self.assertEqual(recovery._budget.ram_bytes, 0)
        self.assertTrue(evidence.sessions)

    def test_read_error_and_cancellation_keep_original_error_and_close_actual_resources(self):
        """实际CSV已产生首batch后出错或取消，保留原因及关闭FD和所有自有费用。

        参数: 无。返回: None。异常: 原错被替换、继续交付结果或关闭责任遗失断言失败。
        """
        for error in (OSError('public-runner-read-failure'), KeyboardInterrupt('public-runner-cancel')):
            data = self.fixture(kind='csv', size=1)
            actual_next = _CSVRequest.__next__

            def fail_after_batch(owner):
                """真实读取首batch使FD及预算确已存在，再注入当前原错误。

                参数: owner真实CSVObservationRead。返回: 无正常返回。
                异常: 指定原OSError或KeyboardInterrupt；实际读取本身错误原样传播。
                """
                actual_next(owner)
                raise error

            with self.observe() as evidence:
                with patch.object(_CSVRequest, '__next__', autospec=True, side_effect=fail_after_batch):
                    expected_error = AnalysisError if isinstance(error, OSError) else KeyboardInterrupt
                    with self.assertRaises(expected_error) as caught:
                        AnalysisRunner().run(data.plan, work_dir=data.work / 'failed-read')
            # 公共入口把普通运行错误包装为AnalysisError，取消原样；两者都不能丢最高恢复入口。
            if isinstance(error, OSError):
                self.assertIs(caught.exception.__cause__, error)
            else:
                self.assertIs(caught.exception, error)
            recovery = getattr(caught.exception, 'runner_cleanup_owner', None)
            self.assertIsNotNone(recovery)
            recovery.close()
            self.assertTrue(recovery.closed)
            self.assertEqual(recovery._budget.ram_bytes, 0)
            self.assertTrue(evidence.sessions)
            self.assertTrue(all(reader.closed for reader in evidence.readers))
            self.assertTrue(evidence.source_handles)
            self.assertTrue(all(handle.closed for handle in evidence.source_handles))
