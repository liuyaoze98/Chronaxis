"""以手构业务真值验证可读发布，不扫描真实输入或改变计算器。

暂存与输出均在临时目录；检查关联、精确时间、数值和生命周期。真实能量数值
来自用户提供的已独立对照结果，这里验证导出而非冒称再次完成真实数据分析。
"""

import csv
import json
import tempfile
import unittest
from publication_fixtures import published_path
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from chronaxis.results import AnalysisResult
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.spool import ResultSpool
from chronaxis.results.summary import (SummaryCalculationRow, SummaryEventRow, SummarySegmentRow,
    SummarySequenceRow, SummarySelectionRow, SummaryContributionRow, SummaryInputRow)
from chronaxis.core.types import QualityFlag as Q
from test_results import run_metadata
from chronaxis.results.readable_format import seconds, quality_text, explanation, outcome_messages
from chronaxis.results.analysis_outcome import AnalysisOutcome, RuleOutcome


def sample_event(sequence=0, event_id='long-full-event-identity', **changes):
    """提供实际验收边界的导出夹具。参数: 序号/ID/覆盖字段。返回: 事件。异常: 模型校验。"""
    row = SummaryEventRow(sequence, 'dataset', 'entity', 'session', 'eligible', event_id,
                          862346858000, 922346858001, 929993200000, 'closed', 'condition_duration', Q.NONE)
    return replace(row, **changes)


def sample_calculation(sequence=1, parent='long-full-event-identity', **changes):
    """提供未舍入的实际能量。参数: 序号/父ID/覆盖字段。返回: 指标。异常: 模型校验。"""
    row = SummaryCalculationRow(sequence, 'dataset', 'entity', 'session', 'energy_kwh',
        'integral', 'event', parent or 'fixture-parent', 1.1813362616030807, 'kWh', 'complete', 'ok', Q.NONE)
    return replace(row, parent_id=parent, **changes)


def make_result(root, rows, tables=('events', 'calculations'), **metadata):
    """封存合成结果供发布。参数: 根目录/行/表/元数据。返回: 结果。异常: 原预算/IO。"""
    spool = ResultSpool(ResourceBudget(8 * 1024 * 1024), root / 'spool', 2,
        requested_tables=tables, enable_sequences='sequences' in tables,
        enable_contributions='contributions' in tables, enable_trace='input_trace' in tables,
        enable_selections='selections' in tables)
    for row in rows:
        spool.append(row)
    spool.seal()
    return AnalysisResult(spool, replace(run_metadata(), device_label='home', **metadata), 'readable_csv')


def read_csv(path):
    """读取小型测试结果。参数: CSV路径。返回: 行列表。异常: IO/CSV传播。"""
    with (path if path.is_file() else published_path(path)).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


class ReadableEnergyTests(unittest.TestCase):
    """能量样板必须一行解释区间和数值，且不留下第二套旧表。"""

    def test_real_value_projection_and_manifest(self):
        """参数: 无。返回: None。异常: 断言失败；数值为用户真实结果的导出夹具。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with make_result(root, [sample_event(), sample_calculation()]) as result:
                published = result.write(root / 'output')
                rows = read_csv(root / 'output' / '事件结果.csv')
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['开始时间（s）'], '862.346858')
                self.assertEqual(rows[0]['结束时间（s）'], '929.9932')
                self.assertEqual(rows[0]['energy_kwh（kWh）'], '1.1813362616030807')
                self.assertEqual(rows[0]['energy_kwh：状态'], '完整')
                self.assertNotIn('确认时间（s）', rows[0])
                self.assertEqual(dict(published.row_counts), {'events': 1})
                self.assertEqual({p.name for p in (root / 'output').iterdir()}, {path.name for path in (*published.output_files, published.manifest_path)})
                manifest = json.loads(published.manifest_path.read_text(encoding='utf-8'))
                self.assertEqual(manifest['presentation']['common_identity']['entity_id'], 'entity')
                self.assertEqual(manifest['row_counts'], {'events': 1})
                self.assertNotIn('session_boundaries', manifest['run'])
            self.assertEqual(result.spool.budget.ram_bytes, 0)

    def test_multiple_metrics_keep_separate_statuses(self):
        """参数: 无。返回: None。异常: 断言失败；部分结果不得被完整能量遮蔽。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extra = sample_calculation(2, calculation_id='other', value=None, status='indeterminate',
                                       reason='no_observation', quality=Q.MISSING)
            with make_result(root, [sample_event(), sample_calculation(), extra]) as result:
                result.write(root / 'output')
                row = read_csv(root / 'output' / '事件结果.csv')[0]
                self.assertEqual(row['other（kWh）'], '')
                self.assertEqual(row['other：状态'], '无法确定')
                self.assertIn('没有所需观测数据', row['other：说明'])
                self.assertEqual(row['energy_kwh：状态'], '完整')


class ReadableFormattingTests(unittest.TestCase):
    """精确时间及未知/零值相互独立；不用显示简化改写业务数值。"""

    def test_seconds_exact_integer_boundaries(self):
        """参数: 无。返回: None。异常: 断言失败；覆盖负时间和int64极值。"""
        cases = {0: '0', 1: '0.000000001', -1: '-0.000000001', -1000000001: '-1.000000001',
                 (1 << 63)-1: '9223372036.854775807', -(1 << 63): '-9223372036.854775808'}
        for value, expected in cases.items():
            self.assertEqual(seconds(value), expected)
        self.assertEqual(seconds(None), '')
        for value in (True, 1.5, '1'):
            with self.assertRaises(TypeError):
                seconds(value)

    def test_quality_and_unknown_do_not_discredit_valid_event(self):
        """参数: 无。返回: None。异常: 断言失败；0只表示无记录原因。"""
        self.assertEqual(quality_text(0), '')
        self.assertEqual(quality_text(Q.MISSING | Q.STALE | Q.DECODE_ERROR), '数据缺失；数据过期；解码失败')
        self.assertIn('未达到要求的覆盖率', explanation(dict(reason='ok', quality=0, coverage_status='indeterminate')))
        messages = outcome_messages(AnalysisOutcome((RuleOutcome('rule', 'events_found', 1, True),), complete=1))
        self.assertIn('已找到满足要求的事件', messages[0])
        self.assertIn('不据此否定已输出区间', messages[0])

    def test_zero_null_large_integer_and_ns_valued_metric(self):
        """参数: 无。返回: None。异常: 断言失败；数值单位不能被错当时间坐标。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [sample_calculation(0, None, scope='session', calculation_id='zero', value=0.0),
                    sample_calculation(1, None, scope='session', calculation_id='missing', value=None,
                                       status='indeterminate', reason='no_observation', quality=Q.MISSING),
                    sample_calculation(2, None, scope='session', calculation_id='large', value=2**63+17),
                    sample_calculation(3, None, scope='session', calculation_id='latency_min',
                                       operation='min_time', value=123.25, unit='ns')]
            with make_result(root, rows, ('calculations',)) as result:
                result.write(root / 'output')
                row = read_csv(root / 'output' / '会话结果.csv')[0]
                self.assertEqual(row['zero（kWh）'], '0.0')
                self.assertEqual(row['missing（kWh）'], '')
                self.assertEqual(row['large（kWh）'], str(2**63+17))
                self.assertEqual(row['latency_min（ns）'], '123.25')

    def test_event_termination_and_confirmation_are_not_invented(self):
        """参数: 无。返回: None。异常: 断言失败；事件独立使用时保留确认时间。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [sample_event(0, 'a', status='truncated'),
                    sample_event(1, 'b', status='interrupted', quality=Q.STALE),
                    sample_event(2, 'c', status='point', confirmed_ns=862346858000, end_ns=None)]
            with make_result(root, rows, ('events',)) as result:
                result.write(root / 'output')
                values = read_csv(root / 'output' / '事件结果.csv')
                self.assertEqual(values[0]['区间状态'], '观测结束，活动尚未确认结束')
                self.assertEqual(values[0]['确认时间（s）'], '922.346858001')
                self.assertEqual(values[1]['说明'], '数据过期')
                self.assertEqual(values[2]['结束时间（s）'], '')

    def test_no_events_has_reason_without_zero_row(self):
        """参数: 无。返回: None。异常: 断言失败；无事件不是能量零。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outcome = AnalysisOutcome((RuleOutcome('eligible', 'duration_not_met', 0, False),))
            with make_result(root, [], analysis_outcome=outcome) as result:
                manifest = result.write(root / 'output')
                self.assertEqual(read_csv(root / 'output' / '事件结果.csv'), [])
                self.assertNotIn('calculations', dict(manifest.row_counts))
                text = json.loads(manifest.manifest_path.read_text(encoding='utf-8'))['result_messages'][0]
                self.assertIn('持续时间不满足要求', text)


class ReadableRelationsTests(unittest.TestCase):
    """覆盖不同会话、多个父事件及流式明细；不靠截短ID或行序猜关联。"""

    def test_same_identifier_in_distinct_sessions(self):
        """参数: 无。返回: None。异常: 断言失败；相同ID不能跨会话配错。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [sample_event(), sample_event(1, session_id='second'),
                    sample_calculation(2), sample_calculation(3, session_id='second', value=9.0)]
            with make_result(root, rows) as result:
                result.write(root / 'output')
                values = {r['会话']: r for r in read_csv(root / 'output' / '事件结果.csv')}
                self.assertEqual(values['session']['energy_kwh（kWh）'], '1.1813362616030807')
                self.assertEqual(values['second']['energy_kwh（kWh）'], '9.0')
                self.assertNotIn('数据集', values['session'])

    def test_window_multiple_parents_pair_and_selections(self):
        """参数: 无。返回: None。异常: 断言失败；同一关系只保留本次编号。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [sample_event(0, 'req'), sample_event(1, 'res'),
                    SummarySegmentRow(2, 'dataset', 'entity', 'session', 'context', 'window-full-id',
                                      860000000000, 931000000000, 'partial', ('req', 'res'), Q.NONE),
                    SummarySequenceRow(3, 'dataset', 'entity', 'session', 'pair', 'pair-full-id',
                                       'req', 'res', 929993200000, 100000000, 'matched', Q.NONE),
                    sample_calculation(4, 'window-full-id', scope='segment'),
                    SummarySelectionRow(5, 'dataset', 'entity', 'session', 'samples', 'segment',
                        'window-full-id', 900000000001, 2**63+17, 'uint64', '1', True, 'unknown', Q.STALE)]
            with make_result(root, rows, ('events', 'segments', 'sequences', 'calculations', 'selections')) as result:
                manifest = result.write(root / 'output')
                window = read_csv(root / 'output' / '窗口结果.csv')[0]
                self.assertEqual(window['父事件区间'], '1、2')
                self.assertEqual(window['窗口状态'], '部分有效')
                self.assertEqual(window['energy_kwh（kWh）'], '1.1813362616030807')
                pair = read_csv(root / 'output' / '配对结果.csv')[0]
                self.assertEqual((pair['请求区间'], pair['响应区间'], pair['延迟（s）']), ('1', '2', '0.1'))
                selected = read_csv(root / 'output' / '选择结果.csv')[0]
                self.assertEqual(selected['所属区间'], '1')
                self.assertEqual(selected['值'], str(2**63+17))
                self.assertEqual(selected['选择状态'], '条件未知')
                self.assertEqual(selected['时间（s）'], '900.000000001')
                self.assertEqual(dict(manifest.row_counts), {'events': 2, 'segments': 1, 'sequences': 1, 'selections': 1})

    def test_explicit_trace_contributions_and_quality_are_streamed(self):
        """参数: 无。返回: None。异常: 断言失败；只在明确请求时出现明细。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [SummaryContributionRow(0, 'dataset', 'entity', 'session', 'energy', 'log', 3, 1,
                                           None, 'missing_input', Q.MISSING),
                    SummaryInputRow(1, 'dataset', 'entity', 'session', 'log', 3, -1, 'decoded_message',
                                    'source.asc:4', '{"Voltage":null}', Q.MISSING)]
            with make_result(root, rows, ('contributions', 'input_trace'), detailed_diagnostics=True) as result:
                published = result.write(root / 'output')
                contribution = read_csv(root / 'output' / '贡献明细.csv')[0]
                self.assertEqual(contribution['贡献值'], '')
                self.assertIn('缺少计算输入', contribution['说明'])
                self.assertNotIn('会话', contribution)
                trace = read_csv(root / 'output' / '输入追溯.csv')[0]
                self.assertEqual(trace['时间（s）'], '-0.000000001')
                self.assertEqual(trace['字段值'], '{"Voltage":null}')
                quality = published_path(root / 'output' / 'quality.jsonl').read_text(encoding='utf-8').splitlines()
                self.assertEqual(len(quality), 2)
                manifest = json.loads(published.manifest_path.read_text(encoding='utf-8'))
                self.assertEqual(manifest['coverage']['contributions:missing_input'], 1)

    def test_orphan_calculation_rejected_and_cleaned(self):
        """参数: 无。返回: None。异常: 断言失败；悬空计算不能被悄悄遗漏。"""
        from chronaxis.results import AnalysisError
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with make_result(root, [sample_calculation(0)]) as result:
                with self.assertRaises(AnalysisError):
                    result.write(root / 'output')
                self.assertFalse((root / 'output').exists())
                self.assertEqual(list(root.glob('.output.incomplete-*')), [])

    def test_empty_window_and_unmatched_response(self):
        """参数: 无。返回: None。异常: 断言失败；无结束/响应不可填0。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [sample_event(0, 'request'),
                    SummarySegmentRow(1, 'dataset', 'entity', 'session', 'context', 'empty',
                                      None, None, 'empty', ('request',), Q.NONE),
                    SummarySequenceRow(2, 'dataset', 'entity', 'session', 'pair', 'unmatched', 'request',
                                       None, 930000000000, None, 'no_response', Q.NONE)]
            with make_result(root, rows, ('events', 'segments', 'sequences')) as result:
                result.write(root / 'output')
                window = read_csv(root / 'output' / '窗口结果.csv')[0]
                pair = read_csv(root / 'output' / '配对结果.csv')[0]
                self.assertEqual((window['开始时间（s）'], window['结束时间（s）']), ('', ''))
                self.assertEqual((pair['响应区间'], pair['延迟（s）']), ('', ''))
                self.assertEqual(pair['配对状态'], '时限内未响应')


class ReadablePublicContractTests(unittest.TestCase):
    """配置默认和旧交换格式分别验收，不以改测试预期掩盖计算变化。"""

    def test_plan_default_and_explicit_formats(self):
        """参数: 无。返回: None。异常: 断言失败；省略和三种显式值都能静态构建。"""
        from test_analysis_plan import config_fixture
        from chronaxis import AnalysisPlan, validate_analysis_plan
        config = config_fixture()
        config.pop('outputs', None)
        plan = AnalysisPlan.from_dict(config)
        self.assertEqual(plan.outputs.tables, 'readable_csv')
        for format_name in ('readable_csv', 'csv', 'jsonl'):
            config['outputs'] = dict(tables=format_name)
            plan = AnalysisPlan.from_dict(config)
            self.assertEqual(plan.outputs.tables, format_name)
            self.assertTrue(validate_analysis_plan(plan).valid)

    def test_explicit_csv_jsonl_bytes_and_rows_unchanged(self):
        """参数: 无。返回: None。异常: 断言失败；旧整数纳秒及parent_id保留。"""
        for format_name in ('csv', 'jsonl'):
            with self.subTest(format=format_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with make_result(root, [sample_event(), sample_calculation()]) as result:
                    result.table_format = format_name
                    published = result.write(root / 'output')
                    self.assertEqual(dict(published.row_counts), {'events': 1, 'calculations': 1})
                    path = published_path(root / 'output' / ('events.' + format_name))
                    if format_name == 'csv':
                        row = read_csv(path)[0]
                        self.assertEqual(row['start_ns'], '862346858000')
                        self.assertFalse(path.read_bytes().startswith(b'\xef\xbb\xbf'))
                    else:
                        row = json.loads(path.read_text(encoding='utf-8'))['row']
                        self.assertEqual(row['start_ns'], 862346858000)
                    self.assertEqual(row['event_id'], 'long-full-event-identity')
                    self.assertFalse((root / 'output' / '事件结果.csv').exists())


class ReadableResourceTests(unittest.TestCase):
    """预算先付、取消与失败不可发布completed；关闭失败保留可重试owner。"""

    def test_spool_and_memory_limits_fail_before_publication(self):
        """参数: 无。返回: None。异常: 断言失败；不丢字段绕过资源限制。"""
        from chronaxis.results import AnalysisError
        for kind in ('spool', 'ram'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with make_result(root, [sample_event(), sample_calculation()]) as result:
                    budget = result.spool.budget
                    if kind == 'spool':
                        budget.spool_quota_bytes = budget.spool_bytes + 1024
                    else:
                        budget.memory_budget_bytes = budget.ram_bytes + result.spool.reader_cost + 65536
                    with self.assertRaises(AnalysisError):
                        result.write(root / 'output')
                    self.assertFalse((root / 'output').exists())
                    self.assertEqual(list(root.glob('.output.incomplete-*')), [])
                self.assertEqual(budget.ram_bytes, 0)

    def test_cancel_during_csv_write_cleans_index_and_keeps_original_rows(self):
        """参数: 无。返回: None。异常: 断言失败；取消后恢复可重新发布。"""
        from chronaxis.results.readable import ReadableWriter
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with make_result(root, [sample_event(), sample_calculation()]) as result:
                with patch.object(ReadableWriter, '_base', side_effect=KeyboardInterrupt('cancel')):
                    with self.assertRaises(KeyboardInterrupt):
                        result.write(root / 'cancelled')
                self.assertEqual(result.status, 'cancelled')
                self.assertEqual(list(root.glob('.cancelled.incomplete-*')), [])
                self.assertEqual(next(result.iter_calculations()).value, 1.1813362616030807)
                result.write(root / 'recovered')
                self.assertEqual(len(read_csv(root / 'recovered' / '事件结果.csv')), 1)

    def test_existing_directory_is_untouched(self):
        """参数: 无。返回: None。异常: 断言失败；不覆盖用户输出。"""
        from chronaxis.results import AnalysisError
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'output'
            output.mkdir()
            marker = output / 'user.txt'
            marker.write_text('keep', encoding='utf-8')
            with make_result(root, [sample_event(), sample_calculation()]) as result:
                published = result.write(output)
                self.assertTrue(published.manifest_path.is_file())
                self.assertEqual(marker.read_text(encoding='utf-8'), 'keep')

    def test_stream_only_does_not_create_sqlite(self):
        """参数: 无。返回: None。异常: 断言失败；没有关联需求不付索引成本。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            row = SummarySelectionRow(0, 'dataset', 'entity', 'session', 'samples', 'session', None,
                                      1, True, 'bool', '1', True, 'true', Q.NONE)
            with make_result(root, [row], ('selections',)) as result:
                with patch('chronaxis.results.readable.sqlite3.connect', side_effect=AssertionError('unneeded index')):
                    result.write(root / 'output')
                self.assertEqual(read_csv(root / 'output' / '选择结果.csv')[0]['值'], 'True')

    def test_repeated_close_failure_retains_owner(self):
        """参数: 无。返回: None。异常: 断言失败；不释放仍由索引持有的RAM。"""
        from chronaxis.results import AnalysisError
        from chronaxis.results.readable import ReadableWriter
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = make_result(root, [sample_event(), sample_calculation()])
            try:
                with patch.object(ReadableWriter, 'close', side_effect=OSError('persistent close failure')):
                    with self.assertRaises(AnalysisError) as caught:
                        result.write(root / 'output')
                    self.assertIs(caught.exception.analysis_result_cleanup_owner, result)
                    self.assertIsNotNone(result._readable_writer.connection)
                    self.assertGreater(result._readable_writer._held_cost, 0)
                result.close()
                self.assertEqual(result.spool.budget.ram_bytes, 0)
                self.assertFalse((root / 'output').exists())
            finally:
                result.close()
