"""核CSV内部记录的完整定位，以及明确请求的当前输入追溯表。

历史数学使用的定位不降格；公开结果只接受当前平坦格式，不再编码旧嵌套结果。
真实暂存检查预算先于编码、单行缓冲与关闭费用，不读取RefProjects。
"""

from configuration_fixtures import current_fixture
from dataclasses import dataclass
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from chronaxis.core.models import SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.history_records import HistorySample, encode_record, decode_record
from chronaxis.sources.csv_spec import CSVSourceRef
from chronaxis.results.summary import SummaryInputRow
from chronaxis.results.codec import encode_row, decode_row, estimate_row_bytes
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultFormatError, BudgetExceededError
from chronaxis.results.spool import ResultSpool
import chronaxis.results.spool as spool_module


@dataclass(frozen=True)
class UnregisteredSourceRef(SourceRef):
    """未登记来源子类不能借已有基类进入内部序列化。"""
    extra: str = 'unregistered'


def history_sample(ref):
    """构造明确UINT64内部样本。参数: 定位。返回: HistorySample。异常: 模型错。"""
    return HistorySample(0, 'value', 2, 7, 2**64 - 1, ScalarValue(2**64 - 1, D.UINT64),
                         '1', ref, True, 2**64 - 1)


def trace_row(sequence=0, text=''):
    """独立手写用户请求的追溯行。参数: 序号/原文本。返回: 当前行。异常: 模型错。"""
    return SummaryInputRow(sequence, 'dataset', 'entity', 'session', 'table', sequence, 2,
        'signal_sample', f'synthetic.csv:{sequence + 2}', json.dumps(current_fixture({'raw': text}), ensure_ascii=False), Q.NONE)


class CSVResultCodecTests(unittest.TestCase):
    """内部CSV定位与公开平坦追溯分别验收，不用旧行包装连接两者。"""

    def test_old_result_fixture_rejected_and_base_history_keeps_explicit_facts(self):
        """旧v1固定样例只作拒绝输入；当前历史保整数、来源与原生标量。"""
        fixture = Path(__file__).resolve().parents[1] / 'fixtures/results/source_ref_v1_select.jsonl'
        with self.assertRaises(ResultFormatError):
            decode_row(fixture.read_bytes(), 1048576)
        sample = history_sample(SourceRef('session', 'table', 'raw'))
        payload = encode_record(sample, 1048576)
        self.assertEqual(decode_record(payload, 1048576), sample)
        self.assertEqual(json.loads(payload)['values']['tuple'][7],
                         {'model': 'SourceRef', 'fields': {'session_id': 'session', 'source_name': 'table', 'field': 'raw'}})

    def test_csv_fields_multiline_empty_text_and_quantization_roundtrip_exactly(self):
        """内部历史完整保路径、物理末行、空/跨行原文和量化；UINT64不经浮点。"""
        for text in ('', '4,\n"quoted"', ' bad value '):
            ref = CSVSourceRef('session', 'table', 'raw', '合成目录/数据.csv', 19, '0.0000000005', text, True)
            sample = history_sample(ref)
            restored = decode_record(encode_record(sample, 1048576), 1048576)
            self.assertEqual(restored, sample)
            self.assertIs(type(restored.source_ref), CSVSourceRef)
            self.assertEqual(restored.value.value, 2**64 - 1)

    def test_unregistered_subclass_and_csv_tuple_shape_are_rejected(self):
        """内部记录拒绝未登记子类及定位字段缺失/新增，不放宽类型协议。"""
        with self.assertRaises(ResultFormatError):
            encode_record(history_sample(UnregisteredSourceRef('session', 'table', 'raw')), 1048576)
        sample = history_sample(CSVSourceRef('session', 'table', 'raw', 'synthetic.csv', 3, '2', '', False))
        for missing in (False, True):
            tree = json.loads(encode_record(sample, 1048576))
            values = tree['values']['tuple'][7]['tuple']
            values.pop() if missing else values.append('unexpected')
            with self.assertRaises(ResultFormatError):
                decode_record((json.dumps(current_fixture(tree)) + '\n').encode(), 1048576)

    def test_requested_trace_uses_current_small_spool(self):
        """三条明确请求的追溯在单行缓冲落盘，定位和原文本精确往返。"""
        with tempfile.TemporaryDirectory(prefix='csv-current-codec-', dir='work') as directory:
            budget = ResourceBudget(4 * 1024**2)
            spool = ResultSpool(budget, Path(directory) / 'results', 1, enable_trace=True, requested_tables=('input_trace',))
            self.addCleanup(spool.close)
            for sequence in range(3):
                spool.append(trace_row(sequence))
            spool.seal()
            with spool.files['input_trace'].open('rb') as stream:
                for sequence in range(3):
                    maximum = spool.row_limit('input_trace')
                    self.assertEqual(decode_row(stream.readline(maximum + 1), maximum), trace_row(sequence))
                self.assertEqual(stream.read(1), b'')
            self.assertEqual(spool.peak_buffer_rows, 1)
            spool.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_requested_long_text_has_real_cost_and_budget_precedes_encoding(self):
        """长追溯值增加实际估费；预算不足在编码前失败，不截断文本。"""
        short, long = trace_row(), trace_row(text='x' * 100000)
        self.assertGreater(estimate_row_bytes(long), estimate_row_bytes(short) + 100000)
        with self.assertRaises(ResultFormatError):
            encode_row(long, 256)
        with tempfile.TemporaryDirectory(prefix='csv-current-limit-', dir='work') as directory:
            budget = ResourceBudget(1024**2)
            spool = ResultSpool(budget, Path(directory) / 'results', 1, enable_trace=True, requested_tables=('input_trace',))
            self.addCleanup(spool.close)
            with patch.object(spool_module, 'encode_row', side_effect=AssertionError('encode-before-budget')) as encoded:
                with self.assertRaises(BudgetExceededError):
                    spool.append(long)
                encoded.assert_not_called()
            self.assertEqual(spool.state, 'failed')
            spool.close()
            self.assertEqual(budget.ram_bytes, 0)
