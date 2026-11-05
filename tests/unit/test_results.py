"""用明确合成事实验证结果编解码、有限暂存和发布生命周期。

输入为手构事件、片段和选择行；输出为unittest断言，不重复旧报文读取。
本文件后续I/O测试使用专用临时目录，不修改RefProjects或用户输出。
每种错误都保留原因；大整数和UNKNOWN不能在JSON或CSV中变成浮点或正常零。
"""

from configuration_fixtures import current_fixture

# 标准库测试及冻结替换只改变本地合成模型。
from dataclasses import replace
import csv
from enum import IntEnum
import gc
import json
import math
from pathlib import Path
from sys import getsizeof
import tempfile
import unittest
from publication_fixtures import published_path
import weakref
from typing import get_type_hints
from unittest.mock import patch
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.calculations import CalculationDefinition, CalculationResult
from chronaxis.core.selection import SelectionRow
from chronaxis.core.temporal import Event, TemporalRule
from chronaxis.core.windows import Segment, WindowSpec
from chronaxis.core.types import QualityFlag as Q, SignalDType as D, Truth
from chronaxis.results import (ResultFormatError, BudgetExceededError,
                               AnalysisResult, RunMetadata, AnalysisError, ResultClosedError)
from chronaxis.results.codec import encode_row, decode_row, estimate_row_bytes
from chronaxis.results import codec as codec_module
from chronaxis.results.rows import row_sort_key
from chronaxis.results.summary import SummarySegmentRow, SummaryCoverageCalculationRow, SummaryInputRow
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.spool import ResultSpool


def core_event(sequence=0, start=5):
    """构造带来源的内部核心事件。参数: 序号/开始ns。返回: Event。异常: 模型校验错。"""
    return Event(f'event-{sequence}', TemporalRule('rule', 'dataset', 'session', 'condition_duration', 5),
                 'activity', start, start + 5, start + 5, 'closed', 'condition_duration',
                 Q.NONE, Q.NONE, (SourceRef('session', 'source', 'raw.value'),))


def run_metadata():
    """提供合成运行的完整身份和限制，不能误认为真实CAN验收。

    参数: 无。返回: RunMetadata。异常: 元数据校验错误直接传播。
    """
    return RunMetadata('synthetic-run', 'synthetic-input', 'synthetic-plan', 'reference', 4,
                       'relative nanoseconds; origin=0', (('session', 0, 100),),
                       '2026-10-09T12:40:00+08:00', limitations=('AnalysisRunner not connected; synthetic data only',), device_label='work')



def summary_event_row(sequence=0, start=5):
    """独立当前事件真值。参数: 序号/开始ns。返回: 平坦行。异常: 模型校验错。"""
    from chronaxis.results.summary import SummaryEventRow
    return SummaryEventRow(sequence,'dataset','entity','session','rule',f'event-{sequence}',
                           start,start+5,start+5,'closed','condition_duration',Q.NONE)


def summary_selection_row(sequence=1, value=2**63+17, unknown=False):
    """独立当前选择真值，保UINT64和UNKNOWN。参数: 序号/值/未知。返回: 平坦行。异常: 模型错。"""
    from chronaxis.results.summary import SummarySelectionRow
    return SummarySelectionRow(sequence,'dataset','entity','session','selected','session',None,6,
                               value,'uint64','1',True,'unknown' if unknown else 'true',
                               Q.MISSING if unknown else Q.NONE)

def result_fixture(root, table_format='csv'):
    """把倒序事件和UINT64 UNKNOWN行写入独立专用暂存。

    参数: root为全新目录路径，table_format为csv/jsonl。返回: AnalysisResult。
    异常: IO/预算错误直接传播，测试不得修改用户目录。
    """
    spool = ResultSpool(ResourceBudget(1048576), root, 1, enable_selections=True, requested_tables=('events','segments','selections'))
    spool.append(summary_event_row(0, 10))
    spool.append(summary_event_row(1, 1))
    spool.append(summary_selection_row(2, unknown=True))
    spool.seal()
    return AnalysisResult(spool, replace(run_metadata(),detailed_diagnostics=True,retain_work=True), table_format)


class ResultCodecTests(unittest.TestCase):
    """检查固定白名单、精确关联与无损诊断，测试不需要文件访问。"""

    def test_round_trip_models_and_precision(self):
        """核对事件、片段、选择行及大整数完整往返。

        参数: 无。返回: None。异常: 断言失败表示typed事实丢失。
        """
        # 部分片段保实际范围与父ID，UINT64选择不经浮点转换。
        segment = SummarySegmentRow(2, 'dataset', 'entity', 'session', 'window', 'segment-1',
                                    5, 10, 'partial', ('event-0',), Q.NONE)
        rows = (summary_event_row(), segment, summary_selection_row(3, unknown=True))
        for row in rows:
            with self.subTest(type=type(row).__name__):
                payload = encode_row(row, 65536)
                self.assertEqual(decode_row(payload, 65536), row)
                self.assertEqual(payload, encode_row(row, 65536))
                self.assertGreater(estimate_row_bytes(row), len(payload))

    def test_scalar_calculation_preserves_coverage_and_parent(self):
        """标量结果保留明确的覆盖判定、质量和event父ID。

        参数: 无。返回: None。异常: 断言失败表示关联或覆盖丢失。
        """
        row = SummaryCoverageCalculationRow(0, 'dataset', 'entity', 'session', 'energy',
                'integral', 'event', 'event-0', 4e-9, 'J', 'partial', 'partial_input', Q.MISSING, 'indeterminate')
        self.assertEqual(decode_row(encode_row(row, 65536), 65536), row)

    def test_nonfinite_invalid_diagnostic_is_explicit(self):
        """无效NaN保留为诊断标签，不能输出非法JSON或变成正常零。

        参数: 无。返回: None。异常: 断言失败表示诊断丢失。
        """
        # 当前结果以None/质量说明无值；原NaN只在显式请求的追溯表中保存标签。
        row = replace(summary_selection_row(unknown=True), value=None, dtype='float64', valid=False,
                      quality=Q.NONFINITE | Q.MISSING)
        trace = SummaryInputRow(2, 'dataset', 'entity', 'session', 'source', 0, 6,
                               'signal_sample', 'row:2', '{"raw.value":{"nonfinite":"nan"}}', Q.NONFINITE)
        for item in (row, trace):
            payload = encode_row(item, 65536)
            self.assertEqual(decode_row(payload, 65536), item)
            self.assertNotIn(b'NaN', payload)
        self.assertIsNone(row.value)
        self.assertEqual(row.selection, 'unknown')

    def test_scope_and_sequence_reject_implicit_identity(self):
        """关联键不能以bool序号或session父ID隐式构造。

        参数: 无。返回: None。异常: 缺少预期异常表示验证遗漏。
        """
        with self.assertRaises(ValueError):
            summary_event_row(True)
        with self.assertRaises(ValueError):
            replace(summary_selection_row(), parent_id='event-0')
        with self.assertRaises((TypeError, ValueError)):
            replace(summary_selection_row(), scope='event')
        self.assertLess(row_sort_key(summary_event_row(10, 1)), row_sort_key(summary_event_row(1, 5)))

    def test_reject_versions_duplicate_keys_and_unknown_models(self):
        """版本/重复键/模型注入均明确失败，不执行任意对象加载。

        参数: 无。返回: None。异常: 缺少格式异常表示解析边界不严。
        """
        packed = json.loads(encode_row(summary_event_row(), 65536))
        cases = [b'{"row_schema_version":1,"row_schema_version":1,"row":null}',
                 b'{"row_schema_version":1,"row":NaN}', b'{"row_schema_version":1,"row":1e999}']
        packed['row_schema_version'] = True
        cases.append(json.dumps(current_fixture(packed)).encode())
        for version in range(1, 7):
            cases.append(json.dumps(current_fixture({**packed, 'row_schema_version': version})).encode())
        packed['row_schema_version'] = 8
        packed['row']['model'] = 'arbitrary.Class'
        cases.append(json.dumps(current_fixture(packed)).encode())
        for payload in cases:
            with self.assertRaises(ResultFormatError):
                decode_row(payload, 65536)
        with self.assertRaises(ResultFormatError):
            encode_row(summary_event_row(), 1)
        with self.assertRaises(ResultFormatError):
            decode_row(encode_row(summary_event_row(), 65536), 1)

    def test_generic_leaves_keep_exact_diagnostics_fees_and_depth_rejections(self):
        """通用叶子保原整数费用、诊断标签、负零及深度边界，数值子类不能冒充原生类型。

        参数: 无。返回: None。异常: 标签/费用/类型或错误优先级改变时断言失败。
        """
        class IntegerChild(int):
            """数值等于整数，但不属于协议允许的原生叶子。"""

        class ForeignDirection(IntEnum):
            """可转换为整数的未登记枚举，不能被原生整数分支接受。"""
            POSITIVE = 1

        leaves = (None, False, True, -(2**63), 2**64-1, 2**4096, -0.0,
                  '中文\n\x00🙂', float('nan'), float('inf'), -float('inf'))
        for value in leaves:
            with self.subTest(value=value):
                packed = codec_module._pack(value, 32)
                if type(value) is float and not math.isfinite(value):
                    label = 'nan' if math.isnan(value) else 'inf' if value > 0 else '-inf'
                    self.assertEqual(packed, {'diagnostic_float': label})
                else:
                    self.assertIs(packed, value)
                self.assertEqual(codec_module._estimate(value, 32), getsizeof(value)+64)
                for function in (codec_module._pack, codec_module._estimate):
                    with self.assertRaisesRegex(ResultFormatError, '^结果行嵌套超过32层$'):
                        function(value, 33)
        self.assertEqual(codec_module._pack(-0.0).hex(), '-0x0.0p+0')
        for value in (D.FLOAT64, Q.MISSING | Q.NONFINITE, Truth.UNKNOWN):
            self.assertEqual(codec_module._pack(value), {'enum': type(value).__name__, 'value': value.value})
            self.assertEqual(codec_module._estimate(value), 512)
        for value in (IntegerChild(1), ForeignDirection.POSITIVE):
            with self.assertRaisesRegex(ResultFormatError, '^结果行含未注册类型'+type(value).__name__+'$'):
                codec_module._pack(value)
            with self.assertRaisesRegex(ResultFormatError, '^不能估算未登记结果对象$'):
                codec_module._estimate(value)
            for function in (codec_module._pack, codec_module._estimate):
                with self.assertRaisesRegex(ResultFormatError, '^结果行嵌套超过32层$'):
                    function(value, 33)

    def test_unknown_source_class_payload_is_released_while_error_traceback_is_held(self):
        """内部叶子编码拒绝未知来源子类后，保留错误栈也不能额外保活该局部类的属性。

        参数: 无。返回: None。异常: 新增类型局部或模型容器保活payload时断言失败。
        """
        def reject_local_source():
            """构造真实合法来源子类并走内部叶子编码入口。参数: 无。返回: 弱引用/原错。异常: 非预期错误。
            """
            class Payload:
                """仅由未知来源类属性持有的可弱引用对象。"""

            payload = Payload()
            reference = weakref.ref(payload)

            class LocalSourceRef(SourceRef):
                """可由原来源构造器创建，但不在结果协议登记表中的子类。"""
                retained = payload

            source = LocalSourceRef('session', 'source', 'raw.value')
            row = replace(core_event(), source_refs=(source,))
            try:
                try:
                    codec_module._pack(row)
                except ResultFormatError as error:
                    return reference, error
                raise AssertionError('未知来源子类未被拒绝')
            finally:
                row = source = payload = LocalSourceRef = None

        reference, error = reject_local_source()
        try:
            self.assertEqual(str(error), '结果行含未注册类型LocalSourceRef')
            self.assertIsNotNone(error.__traceback__)
            gc.collect()
            self.assertIsNone(reference())
        finally:
            error.__traceback__ = None

    def test_native_float_cancellation_keeps_error_and_releases_borrowed_model(self):
        """叶子有限性检查取消或内存失败时保同一异常，递归编码不挂住已借入的模型。

        参数: 无。返回: None。异常: 主错身份变化或持栈时模型未释放则断言失败。
        """
        for error_type in (KeyboardInterrupt, MemoryError):
            with self.subTest(error_type=error_type.__name__):
                marker = error_type('native-leaf-cancel')
                value = ScalarValue(1.25, D.FLOAT64)
                reference = weakref.ref(value)

                def fail(argument):
                    """在实际float叶子抛原标记并清测试自身借用。参数: float。返回: 无。异常: marker。
                    """
                    try:
                        raise marker
                    finally:
                        argument = None

                try:
                    with patch.object(codec_module, 'isfinite', fail):
                        try:
                            codec_module._pack(value)
                        except BaseException as error:
                            self.assertIs(error, marker)
                        else:
                            self.fail('未命中实际原生浮点检查')
                    value = None
                    gc.collect()
                    self.assertIsNotNone(marker.__traceback__)
                    self.assertIsNone(reference())
                finally:
                    value = None
                    marker.__traceback__ = None


class ResultSpoolTests(unittest.TestCase):
    """使用独立临时目录验证有限缓冲、双路排序、配额与关闭句柄。"""

    def test_many_runs_stable_order_and_finite_buffer(self):
        """40行超过两行缓冲，输出按起点与稳定序号排列。

        参数: 无。返回: None。异常: 断言失败表示漏行、错序或资源越界。
        """
        with tempfile.TemporaryDirectory() as root:
            budget = ResourceBudget(1048576)
            spool = ResultSpool(budget, Path(root) / 'spool', 2)
            # 起点故意倒序且重复，不能用到达顺序冒充业务排序。
            rows = [summary_event_row(index, 20 - index // 2) for index in range(40)]
            for row in rows:
                spool.append(row)
            spool.seal()
            with spool.files['events'].open('rb') as handle:
                actual = [decode_row(line, spool.max_row_bytes) for line in handle]
            self.assertEqual(actual, sorted(rows, key=row_sort_key))
            self.assertEqual(spool.state, 'analysis_complete')
            self.assertEqual(spool.peak_buffer_rows, 2)
            self.assertLessEqual(budget.peak_ram_bytes, budget.memory_budget_bytes)
            self.assertGreater(budget.spool_bytes, sum(len(encode_row(row, 65536)) for row in rows))
            # 外部归并文件保留，成功写入的累计账本等于所有run实际大小。
            self.assertEqual(budget.spool_bytes, sum(path.stat().st_size for path in spool.path.glob('*.jsonl')))
            spool.close()
            spool.close()
            self.assertEqual(budget.ram_bytes, 0)
            self.assertTrue(spool.files['events'].exists())


class ResultLifecycleTests(unittest.TestCase):
    """验证独立行流、关闭资源和原子发布的成功/失败路径。"""

    def test_iterators_are_independent_and_close_preserves_files(self):
        """交替消费两个事件流，close后读/写拒绝且原文件仍在。

        参数: 无。返回: None。异常: 断言失败表示共享游标或资源泄漏。
        """
        with tempfile.TemporaryDirectory() as root:
            result = result_fixture(Path(root) / 'spool')
            a, b = result.iter_events(), result.iter_events()
            self.assertEqual(next(a).start_ns, 1)
            self.assertEqual(next(a).start_ns, 10)
            self.assertEqual(next(b).start_ns, 1)
            result.close()
            result.close()
            self.assertTrue(a.handle.closed and b.handle.closed)
            self.assertEqual(result.spool.budget.ram_bytes, 0)
            self.assertTrue(result.spool.files['events'].exists())
            for method in (result.iter_events, result.iter_segments, result.iter_calculations):
                with self.assertRaises(ResultClosedError):
                    method()
            with self.assertRaises(ResultClosedError):
                next(b)
            with self.assertRaises(ResultClosedError):
                result.write(Path(root) / 'output')

    def test_csv_publish_and_repeat_to_new_directory(self):
        """CSV与质量/清单完整发布，二次导出只读同一暂存。

        参数: 无。返回: None。异常: 断言失败表示精度、顺序或完成状态错误。
        """
        with tempfile.TemporaryDirectory() as root:
            with result_fixture(Path(root) / 'spool') as result:
                internal = json.loads(result.manifest_path.read_text('utf-8'))
                self.assertEqual(internal['status'], 'analysis_complete')
                manifest = result.write(Path(root) / 'output')
                completed = json.loads(manifest.manifest_path.read_text('utf-8'))
                self.assertEqual(completed['status'], 'completed')
                self.assertEqual(completed['row_counts'], {'events': 2, 'segments': 0, 'selections': 1})
                self.assertEqual(completed['run']['device_label'], 'work')
                with published_path(manifest.output_dir / 'selections.csv').open(encoding='utf-8', newline='') as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(rows[0]['value'], str(2**63+17))
                self.assertEqual(rows[0]['selection'], 'unknown')
                self.assertNotIn('row_json', rows[0])
                self.assertEqual(int(rows[0]['quality']), int(Q.MISSING))
                self.assertTrue(published_path(manifest.output_dir / 'quality.jsonl').exists())
                second = result.write(Path(root) / 'second')
                self.assertEqual(published_path(manifest.output_dir / 'events.csv').read_bytes(), published_path(second.output_dir / 'events.csv').read_bytes())
                self.assertFalse(tuple(Path(root).glob('.*.incomplete-*')))
            self.assertTrue(manifest.manifest_path.exists())

    def test_jsonl_publish_is_replayable(self):
        """JSONL输出可恢复原typed行，空片段表仍明确存在。

        参数: 无。返回: None。异常: 断言失败表示输出格式不完整。
        """
        with tempfile.TemporaryDirectory() as root:
            with result_fixture(Path(root) / 'spool', 'jsonl') as result:
                manifest = result.write(Path(root) / 'output')
                with published_path(manifest.output_dir / 'events.jsonl').open('rb') as handle:
                    rows = [decode_row(line, 4096) for line in handle]
                self.assertEqual([row.sequence for row in rows], [1, 0])
                self.assertEqual(published_path(manifest.output_dir / 'segments.jsonl').stat().st_size, 0)

    def test_existing_target_is_preserved_and_result_can_retry(self):
        """复用已有目录时保留用户文件，并支持再次发布到其他目录。

        参数: 无。返回: None。异常: 断言失败表示已有数据受损或状态不准确。
        """
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / 'existing'
            destination.mkdir()
            marker = destination / 'user.txt'
            marker.write_text('user data', encoding='utf-8')
            with result_fixture(Path(root) / 'spool') as result:
                published = result.write(destination)
                self.assertEqual(published.status, 'completed')
                self.assertEqual(result.status, 'analysis_complete')
                self.assertEqual(marker.read_text('utf-8'), 'user data')
                self.assertTrue(published.manifest_path.is_file())
                self.assertEqual(result.write(Path(root) / 'new').status, 'completed')

    def test_writer_and_install_failure_publish_no_completed(self):
        """中途写入或最后安装失败，所有句柄关闭且无已发布完成目录。

        参数: 无。返回: None。异常: 缺少失败或资源未关闭表示缺陷。
        """
        for failure in ('write', 'install'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                with result_fixture(Path(root) / 'spool') as result:
                    target = Path(root) / 'output'
                    method = '_write_table' if failure == 'write' else '_install_directory'
                    with patch.object(AnalysisResult, method, side_effect=OSError('injected failure')):
                        with self.assertRaises(AnalysisError):
                            result.write(target)
                    self.assertFalse(tuple(target.iterdir()) if target.exists() else ())
                    self.assertFalse(result._iterators)
                    self.assertEqual(result.status, 'output_failed')
                    temporary = next(Path(root).glob('.output.incomplete-*'))
                    self.assertEqual(json.loads((temporary / 'failure.json').read_text('utf-8'))['status'], 'output_failed')
                    if (temporary / 'run_manifest.json').exists():
                        self.assertEqual(json.loads((temporary / 'run_manifest.json').read_text('utf-8'))['status'], 'output_failed')

    def test_corrupt_spool_fails_and_closes_iterator(self):
        """损坏行不能少写后仍completed，读失败立即释放句柄。

        参数: 无。返回: None。异常: 缺少格式错误表示损坏被吞掉。
        """
        with tempfile.TemporaryDirectory() as root:
            with result_fixture(Path(root) / 'spool') as result:
                result.spool.files['events'].write_bytes(b'invalid\n')
                iterator = result.iter_events()
                with self.assertRaises(ResultFormatError):
                    next(iterator)
                self.assertTrue(iterator.handle.closed)
                with self.assertRaises(AnalysisError):
                    result.write(Path(root) / 'output')
                self.assertFalse((Path(root) / 'output').exists())

    def test_context_cancellation_preserves_original_exception(self):
        """取消发布保留KeyboardInterrupt，释放发布资源且不假报完成。

        参数: 无。返回: None。异常: 原取消异常须被测试捕获。
        """
        with tempfile.TemporaryDirectory() as root:
            with result_fixture(Path(root) / 'spool') as result:
                baseline = result.spool.budget.ram_bytes
                with patch.object(AnalysisResult, '_write_table', side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        result.write(Path(root) / 'output')
                self.assertEqual(result.status, 'cancelled')
                self.assertEqual(result.spool.budget.ram_bytes, baseline)

    def test_invalid_metadata_rejects_inferred_time_and_bool(self):
        """时间无时区或版本为bool不能成为可追溯清单。

        参数: 无。返回: None。异常: 缺少元数据校验异常表示错误。
        """
        with self.assertRaises(ValueError):
            replace(run_metadata(), started_at='2026-10-09T12:00:00')
        with self.assertRaises(ValueError):
            replace(run_metadata(), config_version=True)

    def test_public_entry_types_are_resolvable(self):
        """公开行流/写出/上下文注解能直接解析为真实实现类型。

        参数: 无。返回: None。异常: NameError或断言失败表示注解占位。
        """
        from chronaxis import AnalysisResult as PublicResult, OutputManifest as PublicManifest
        from chronaxis.results import SummaryCalculationRow
        from chronaxis.results.summary import SummaryEventRow, SummarySegmentRow
        self.assertIs(PublicResult, AnalysisResult)
        self.assertIs(get_type_hints(AnalysisResult.write)['return'], PublicManifest)
        self.assertIs(get_type_hints(AnalysisResult.__enter__)['return'], AnalysisResult)
        for method, row_type in ((AnalysisResult.iter_events, SummaryEventRow), (AnalysisResult.iter_segments, SummarySegmentRow),
                                 (AnalysisResult.iter_calculations, SummaryCalculationRow)):
            self.assertEqual(get_type_hints(method)['return'].__args__, (row_type,))

    def test_mid_csv_failure_closes_every_real_handle(self):
        """实际写过一行后注入CSV错误，输入和所有输出句柄均关闭。

        参数: 无。返回: None。异常: 缺少失败或句柄未关闭表示资源泄漏。
        """
        with tempfile.TemporaryDirectory() as root:
            with result_fixture(Path(root) / 'spool') as result:
                handles = []
                original_open, original_row = Path.open, csv.DictWriter.writerow
                calls = 0

                def tracked_open(path, *args, **kwargs):
                    """记录发布期间真实句柄，保留原文件操作。

                    参数: path/args/kwargs为open输入。返回: 文件对象。异常: IO错误。
                    """
                    handle = original_open(path, *args, **kwargs)
                    handles.append(handle)
                    return handle

                def failing_row(writer, row):
                    """表头和首行成功后失败，确保覆盖中途写入。

                    参数: writer为DictWriter，row为当前字段。返回: 原写入结果。
                    异常: 第三次调用抛OSError。
                    """
                    nonlocal calls
                    calls += 1
                    if calls == 3:
                        raise OSError('mid csv failure')
                    return original_row(writer, row)

                baseline = result.spool.budget.ram_bytes
                with patch.object(Path, 'open', tracked_open), patch.object(csv.DictWriter, 'writerow', failing_row):
                    with self.assertRaises(AnalysisError):
                        result.write(Path(root) / 'output')
                self.assertGreaterEqual(calls, 3)
                self.assertTrue(all(handle.closed for handle in handles))
                self.assertEqual(result.spool.budget.ram_bytes, baseline)
                self.assertFalse((Path(root) / 'output').exists())

    def test_target_created_during_install_is_never_overwritten(self):
        """在rename调用时创建竞争目录，Windows安装必须拒绝覆盖。

        参数: 无。返回: None。异常: 缺少发布失败表示竞争保护遗漏。
        """
        with tempfile.TemporaryDirectory() as root:
            with result_fixture(Path(root) / 'spool') as result:
                target = Path(root) / 'output'
                original_rename = __import__('os').rename

                def competing_rename(source, destination):
                    """模拟目标在最后存在检查之后被另一调用者创建。

                    参数: source/destination为安装路径。返回: 原rename结果。
                    异常: 原rename对已存在目标的拒绝。
                    """
                    Path(destination).mkdir()
                    return original_rename(source, destination)

                with patch('chronaxis.results.result.os.rename', competing_rename):
                    with self.assertRaises(AnalysisError):
                        result.write(target)
                self.assertTrue(target.is_dir())
                self.assertFalse((target / 'run_manifest.json').exists())

    def test_internal_manifest_quota_failure_closes_spool(self):
        """分析行成功但内部清单超配额，不能返回完整结果且RAM释放。

        参数: 无。返回: None。异常: 缺少AnalysisError表示构造失败未隔离。
        """
        with tempfile.TemporaryDirectory() as root:
            row = summary_event_row()
            budget = ResourceBudget(1048576, len(encode_row(row, 4096)))
            spool = ResultSpool(budget, Path(root) / 'spool', 1, requested_tables=('events',))
            spool.append(row)
            spool.seal()
            with self.assertRaises(AnalysisError) as raised:
                AnalysisResult(spool, replace(run_metadata(),detailed_diagnostics=True,retain_work=True))
            self.assertIsInstance(raised.exception.__cause__, BudgetExceededError)
            self.assertEqual(spool.state, 'failed')
            self.assertEqual(budget.ram_bytes, 0)


class ResultFailureTests(unittest.TestCase):
    """隔离检查预算、目录和磁盘错误；不把成功输出误算为失败修复。"""

    def test_external_merge_spool_quota_exceeded(self):
        """初始run可写而归并副本超配额，封口明确失败。

        参数: 无。返回: None。异常: 缺少预算错误表示归并未计入spool。
        """
        with tempfile.TemporaryDirectory() as root:
            rows = (summary_event_row(0, 10), summary_event_row(1, 1))
            quota = sum(len(encode_row(row, 4096)) for row in rows) + 20
            budget = ResourceBudget(1048576, quota)
            spool = ResultSpool(budget, Path(root) / 'spool', 1)
            for row in rows:
                spool.append(row)
            with self.assertRaises(BudgetExceededError):
                spool.seal()
            self.assertEqual(spool.state, 'failed')
            self.assertEqual(budget.ram_bytes, 4096)
            spool.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_ram_and_spool_exceed_fail_without_dropping(self):
        """RAM或磁盘配额超限明确失败，不能缩减数据或标完成。

        参数: 无。返回: None。异常: 缺少预算错误或失败状态表示缺陷。
        """
        for memory, quota in ((8192, None), (1048576, 10)):
            with self.subTest(memory=memory, quota=quota), tempfile.TemporaryDirectory() as root:
                budget = ResourceBudget(memory, quota)
                spool = ResultSpool(budget, Path(root) / 'spool', 1)
                with self.assertRaises(BudgetExceededError):
                    spool.append(summary_event_row())
                self.assertEqual(spool.state, 'failed')
                self.assertFalse((spool.path / 'run_manifest.json').exists())
                self.assertEqual(budget.ram_bytes, 4096)
                spool.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_merge_uses_shared_budget(self):
        """调用侧其他状态占用也参与归并申请，不能移出统计。

        参数: 无。返回: None。异常: 缺少预算失败表示未共享账本。
        """
        with tempfile.TemporaryDirectory() as root:
            budget = ResourceBudget(1048576)
            spool = ResultSpool(budget, Path(root) / 'spool', 1)
            spool.append(summary_event_row(0, 10))
            spool.append(summary_event_row(1, 1))
            # 按实际两路行长精确占满余量再多1B；原600000在动态小行下已可合法归并。
            merge_cost = 2 * spool.reader_cost_for('events')
            borrowed = budget.memory_budget_bytes - budget.ram_bytes - merge_cost + 1
            self.assertGreater(borrowed, 0)
            self.assertEqual(budget.ram_bytes + borrowed + merge_cost, budget.memory_budget_bytes + 1)
            budget.reserve_ram(borrowed)
            with self.assertRaises(BudgetExceededError):
                spool.seal()
            self.assertEqual(spool.state, 'failed')
            budget.release_ram(borrowed)
            spool.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_disk_full_closes_open_handles(self):
        """注入写入错误，句柄必须关闭且原磁盘错误仍可追溯。

        参数: 无。返回: None。异常: 断言失败表示句柄泄漏或失败被吞掉。
        """
        with tempfile.TemporaryDirectory() as root:
            spool = ResultSpool(ResourceBudget(1048576), Path(root) / 'spool', 1)
            handles = []
            original_open = Path.open

            def tracked_open(path, *args, **kwargs):
                """记录本测试打开的文件，执行仍使用真实文件句柄。

                参数: path/args/kwargs为Path.open输入。返回: 文件对象。
                异常: 原I/O异常传播。
                """
                handle = original_open(path, *args, **kwargs)
                handles.append(handle)
                return handle

            with patch.object(Path, 'open', tracked_open), patch.object(ResultSpool, '_write_bytes', side_effect=OSError('disk full')):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    spool.append(summary_event_row())
            self.assertTrue(handles)
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertEqual(spool.state, 'failed')
            spool.close()

    def test_budget_validation_and_existing_work_dir(self):
        """金额和目录必须明确；拒绝已有目录且退还固定状态申请。

        参数: 无。返回: None。异常: 缺少异常表示验证遗漏。
        """
        with self.assertRaises(ValueError):
            ResourceBudget(True)
        budget = ResourceBudget(1048576)
        with self.assertRaises(ValueError):
            budget.release_ram(1)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(FileExistsError):
                ResultSpool(budget, root)
            self.assertEqual(budget.ram_bytes, 0)
