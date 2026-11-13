"""用实际合成CSV验证分配前预算、跨行记录、原事实及历史接线。

输入写入work/m2-run-tests/budgeted-csv唯一目录，device_label为work；旧快照只读。
原入口与预算入口在reference/numpy和四种切分下完整事实相同，另有手算真值。
长行/引用多行/Unicode提升按容量计费，超限明确失败；同刻状态不漏账，清理不删除输入。
小夹具物化仅用于测试比较，不能作为生产有界实现或RSS性能证明。
"""

from configuration_fixtures import current_fixture

# 唯一新工作目录保留证据；局部mock只证明失败位置，不替换数值核。
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import json
import unittest
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec, SourceRef
from chronaxis.core.types import SignalDType as D, TimeType
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.batch_signal_groups import BatchSignalGroups
from chronaxis.execution.calculation_values import scalar_from_column
from chronaxis.execution.history_records import HistorySample
from chronaxis.results import BudgetExceededError, ResultFormatError
from chronaxis.execution.history_records import encode_record, decode_record
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest, SignalCSVSourceAdapter, SourceAdapter, SourceClosedError, SourceReadError
from chronaxis.sources.csv_spec import SignalCSVSpec, CSVSourceRef
from test_budgeted_memory import batch_facts


class BudgetedCSVTests(unittest.TestCase):
    """真实文件夹具覆盖跨文件同刻、引用换行、缺失及精确整数时间。"""

    def setUp(self):
        """建立两份有序文件，电流1000mA/2000mA手算为1A/2A。

        参数: 无。返回: None。异常: 文件/夹具错误直接失败，不假装完成验收。
        """
        self.work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/budgeted-csv' / uuid4().hex
        self.work.mkdir(parents=True)
        self.start = 2 ** 53
        a = self.write('a.csv', f'ns,v,id,mode,note\n{self.start},1000,{2 ** 64 - 1},scope,"first\nsecond"\n')
        b = self.write('b.csv', f'ns,v,id,mode,note\n{self.start},2000,1,off,x\n{self.start + 1},,2,unknown,x\n{self.start + 2},NaN,3,scope,x\n')
        self.spec = SignalCSVSpec('table', (a, b), TimebaseSpec('clock', TimeType.RELATIVE, 'budget-csv-synthetic'), 'ns', 'ns')
        self.signals = (SignalDefinition('current', 'table', 'v', D.FLOAT64, 'A', 2, input_unit='mA', scale=.001),
                        SignalDefinition('identifier', 'table', 'id', D.UINT64, '1', 2),
                        SignalDefinition('mode', 'table', 'mode', D.ENUM, '1', 2, choices=(('scope', 'active'), ('off', 'inactive'))))

    def write(self, name, content):
        """写当前唯一目录合成表，不修改旧快照或用户输入。

        参数: name文件名/content完整文本。返回: Path。异常: 原文件写入错误。
        """
        path = self.work / name
        path.write_text(content, encoding='utf-8', newline='')
        return path

    def build(self, backend='numpy', size=1, *, budget=None, spec=None, signals=None):
        """构造真实预算CSV来源并登记清理，不改变分批参数。

        参数: backend/size；可替换budget/spec/signals。返回: (adapter,request)。异常: 配置/预算错误。
        """
        selected = self.signals if signals is None else signals
        adapter = BudgetedSignalCSVSourceAdapter(budget or ResourceBudget(16 * 1024 ** 2), self.spec if spec is None else spec,
                                               'session', selected, backend=backend)
        self.addCleanup(adapter.close)
        return adapter, ReadRequest('session', tuple(item.name for item in selected), self.start, self.start + 3, size)

    def test_original_facts_and_hand_truth_both_backends_splits(self):
        """四切分与原入口完整事实一致，跨行位置/同刻/1ns/大uint/缺失有独立真值。

        参数: 无。返回: None。异常: 原接口、数值、质量、位置或进度变化断言失败。
        """
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7, 65536):
                adapter, request = self.build(backend, size)
                self.assertIsInstance(adapter, SourceAdapter)
                original = SignalCSVSourceAdapter(self.spec, 'session', self.signals, backend=backend)
                self.addCleanup(original.close)
                expected = [batch_facts(batch) for batch in original.iter_batches(request)]
                actual = list(adapter.iter_batches(request))
                self.assertEqual([batch_facts(batch) for batch in actual], expected)
                current = [(int(col.time_ns[i]), col.values[i].item(), bool(col.valid[i]), col.source_ref[i])
                           for batch in actual for name, col in batch.series.items() if name == 'current' for i in range(len(col.time_ns))]
                self.assertEqual([(t, v, valid) for t, v, valid, _ in current[:2]], [(self.start, 1., True), (self.start, 2., True)])
                self.assertEqual(current[2][0], self.start + 1)
                self.assertFalse(current[2][2])
                self.assertFalse(current[3][2])
                self.assertEqual(current[0][3].line_number, 3)
                self.assertEqual(current[1][3].line_number, 2)
                identifiers = [int(col.values[i]) for batch in actual for name, col in batch.series.items() if name == 'identifier' for i in range(len(col.time_ns))]
                self.assertEqual(identifiers, [2 ** 64 - 1, 1, 2, 3])
                self.assertEqual(sum(batch.sample_count for batch in actual), 12)
                self.assertEqual(actual[-1].observed_end_ns, self.start + 2)
                adapter.close()
                self.assertEqual(adapter.budget.ram_bytes, 0)

    def test_constructor_and_request_budget_precede_reading(self):
        """声明超限不创建原入口，请求超限不打开文件，原来源可在解除占用后复用。

        参数: 无。返回: None。异常: 预算之前发生创建/open或预留残留断言失败。
        """
        tiny = ResourceBudget(1)
        with patch('chronaxis.execution.csv_reader.SignalCSVSourceAdapter.__init__') as initialize:
            with self.assertRaises(BudgetExceededError):
                BudgetedSignalCSVSourceAdapter(tiny, self.spec, 'session', self.signals)
        initialize.assert_not_called()
        self.assertEqual(tiny.ram_bytes, 0)
        adapter, request = self.build()
        baseline = adapter.budget.ram_bytes
        blocker = adapter.budget.memory_budget_bytes - baseline - 1
        adapter.budget.reserve_ram(blocker)
        with patch('pathlib.Path.open') as opened:
            with self.assertRaises(BudgetExceededError):
                adapter.iter_batches(request)
        opened.assert_not_called()
        adapter.budget.release_ram(blocker)
        self.assertEqual(adapter.budget.ram_bytes, baseline)
        self.assertEqual(sum(batch.sample_count for batch in adapter.iter_batches(request)), 12)

    def test_long_physical_line_rejected_before_pack(self):
        """未投影的大note物理行也受资源限制，不解析截断行、不调用pack。

        参数: 无。返回: None。异常: 超限被忽略或原错误链/释放错误断言失败。
        """
        path = self.write('long.csv', 'ns,v,id,mode,note\n' + f'{self.start},1,1,scope,' + 'x' * 100000 + '\n')
        adapter, request = self.build(budget=ResourceBudget(1000000), spec=replace(self.spec, paths=(path,)))
        baseline = adapter.budget.ram_bytes
        with patch('chronaxis.sources.signal_csv.pack_decoded') as pack:
            with self.assertRaises(SourceReadError) as caught:
                next(adapter.iter_batches(request))
        pack.assert_not_called()
        self.assertIsInstance(caught.exception.__cause__, BudgetExceededError)
        self.assertEqual(adapter.budget.ram_bytes, baseline)
        self.assertFalse(adapter.handles)
        self.assertEqual(len(path.read_text(encoding='utf-8').splitlines()[-1]), len(f'{self.start},1,1,scope,') + 100000)

    def test_multiline_record_accumulates_before_pack(self):
        """各物理行很短但一个引用记录累积超限，不能用逐行释放绕过限制。

        参数: 无。返回: None。异常: 多行记录资源未累计或开始数组分配断言失败。
        """
        path = self.write('quoted.csv', f'ns,v,id,mode,note\n{self.start},1,1,scope,"' + ('x\n' * 40000) + 'end"\n')
        adapter, request = self.build(budget=ResourceBudget(1000000), spec=replace(self.spec, paths=(path,)))
        baseline = adapter.budget.ram_bytes
        with patch('chronaxis.sources.signal_csv.pack_decoded') as pack:
            with self.assertRaises(SourceReadError) as caught:
                next(adapter.iter_batches(request))
        pack.assert_not_called()
        self.assertIsInstance(caught.exception.__cause__, BudgetExceededError)
        self.assertEqual(adapter.budget.ram_bytes, baseline)
        self.assertFalse(adapter.handles)

    def test_unicode_promotion_fits_real_workspace_and_splits_when_needed(self):
        """按一份 UTF32 原列计费，8MiB 可容纳原夹具，较小预算按容量提前交批。

        参数: 无。返回: None。异常: 丢样本、错误回退、容量超限或清理残留时失败。
        """
        definition = self.signals[2]
        for budget_bytes, count in ((8 * 1024 ** 2, 64), (2 * 1024 ** 2, 1024)):
            path = self.write(f'unicode-{count}.csv', 'ns,mode\n' +
                              '\n'.join(f'{self.start + i},' + ('x' * 4096 if i == 0 else 'z')
                                        for i in range(count)) + '\n')
            spec = replace(self.spec, paths=(path,))
            for backend in ('reference', 'numpy'):
                adapter, request = self.build(backend, count, budget=ResourceBudget(budget_bytes),
                                              spec=spec, signals=(definition,))
                baseline = adapter.budget.ram_bytes
                batches = list(adapter.iter_batches(request))
                self.assertEqual(sum(batch.sample_count for batch in batches), count)
                self.assertTrue(all(not col.valid.any() for batch in batches for col in batch.series.values()))
                self.assertEqual([int(t) for batch in batches for col in batch.series.values() for t in col.time_ns],
                                 list(range(self.start, self.start + count)))
                if backend == 'numpy' and count == 1024:
                    self.assertGreater(len(batches), 1)
                self.assertEqual(adapter.budget.ram_bytes, baseline)

    def test_unstarted_and_multiple_requests_close_independently(self):
        """重复未开始close不积累登记；两个活动读取器只关闭自有请求。

        参数: 无。返回: None。异常: 登记、句柄或预算残留断言失败。
        """
        adapter, request = self.build()
        baseline = adapter.budget.ram_bytes
        for _ in range(100):
            adapter.iter_batches(request).close()
        self.assertFalse(adapter.active)
        self.assertFalse(adapter._requests)
        self.assertEqual(adapter.budget.ram_bytes, baseline)
        left, right = adapter.iter_batches(request), adapter.iter_batches(request)
        next(left)
        next(right)
        self.assertEqual(len(adapter.handles), 2)
        left.close()
        self.assertEqual(len(adapter.handles), 1)
        self.assertEqual(next(right).sample_count, 1)
        adapter.close()
        self.assertFalse(adapter.handles)
        self.assertEqual(adapter.budget.ram_bytes, 0)
        with self.assertRaises(SourceClosedError):
            next(right)

    def test_parse_error_and_cancel_preserve_causes_and_release(self):
        """原数值错误保持ValueError链；KeyboardInterrupt原样传播，资源全部回基线。

        参数: 无。返回: None。异常: 错误被覆盖/取消吞掉/预算或句柄残留断言失败。
        """
        for error_type in (ValueError, KeyboardInterrupt):
            adapter, request = self.build()
            baseline = adapter.budget.ram_bytes
            error = error_type('injected parse')
            with patch.object(adapter, '_parse_value', side_effect=error):
                with self.assertRaises(SourceReadError if error_type is ValueError else KeyboardInterrupt) as caught:
                    next(adapter.iter_batches(request))
            if error_type is ValueError:
                self.assertIs(caught.exception.__cause__, error)
            else:
                self.assertIs(caught.exception, error)
            self.assertFalse(adapter.handles)
            self.assertFalse(adapter._resources)
            self.assertEqual(adapter.budget.ram_bytes, baseline)

    def test_huge_unfinished_group_rejected_without_state_escape(self):
        """批大小1也不能使5000个未完整同刻sequence集合绕过预算。

        参数: 无。返回: None。异常: 全部数据成功或失败后清理错误断言失败。
        """
        path = self.write('same.csv', 'ns,mode\n' + (f'{self.start},scope\n' * 5000))
        adapter, request = self.build(size=1, budget=ResourceBudget(500000), spec=replace(self.spec, paths=(path,)), signals=(self.signals[2],))
        baseline = adapter.budget.ram_bytes
        consumed = 0
        with self.assertRaises(SourceReadError) as caught:
            for batch in adapter.iter_batches(request):
                consumed += batch.sample_count
        self.assertGreater(consumed, 1)
        self.assertLess(consumed, 5000)
        self.assertIsInstance(caught.exception.__cause__, BudgetExceededError)
        self.assertEqual(adapter.budget.ram_bytes, baseline)

    def test_csv_history_group_shared_budget_preserves_csv_ref(self):
        """实际CSV→历史→完整组三组手算6/3/3，位置文本与CSV引用类型须保留。

        参数: 无。返回: None。异常: CSV历史不支持、位置丢失或资源残留断言失败。
        """
        for backend in ('reference', 'numpy'):
            adapter, request = self.build(backend, 2)
            groups = []
            grouping = BatchSignalGroups(adapter.budget, self.signals, 'session', groups.append)
            self.addCleanup(grouping.close)
            first = None
            for batch in adapter.iter_batches(request):
                grouping.consume(batch)
                column = batch.series.get('current')
                if first is None and column is not None and len(column.time_ns):
                    first = HistorySample(0, 'current', int(column.time_ns[0]), int(column.sequence[0]),
                        column.values[0].item(), scalar_from_column(column, 0), column.unit,
                        column.source_ref[0], True, column.original_values[0])
            grouping.finish()
            adapter.close()
            self.assertEqual([len(group.samples) for group in groups], [6, 3, 3])
            self.assertEqual([group.time_ns for group in groups], [self.start, self.start + 1, self.start + 2])
            self.assertIsInstance(first.source_ref, CSVSourceRef)
            self.assertEqual((first.source_ref.line_number, first.source_ref.time_text, first.source_ref.value_text), (3, str(self.start), '1000'))
            self.assertEqual(first.value.value, 1.)
            # CSV新版本完整还原；基础来源旧版本字节身份/字段仍可读。
            payload = encode_record(first, 65536)
            self.assertEqual(json.loads(payload)['history_version'], 2)
            self.assertEqual(decode_record(payload, 65536), first)
            base = replace(first, source_ref=SourceRef('session', 'table', 'v'))
            self.assertEqual(json.loads(encode_record(base, 65536))['history_version'], 1)
            self.assertEqual(decode_record(encode_record(base, 65536), 65536), base)
            # v2未知tag/缺字段/非法物理行，以及改为v1，不能静默丢CSV定位。
            for fault in ('unknown', 'missing', 'negative_line', 'wrong_version'):
                packed = json.loads(payload)
                reference = packed['values']['tuple'][7]['tuple']
                if fault == 'unknown':
                    reference[0] = 'other_ref'
                elif fault == 'missing':
                    reference.pop()
                elif fault == 'negative_line':
                    reference[3] = -1
                else:
                    packed['history_version'] = 1
                damaged = (json.dumps(current_fixture(packed)) + '\n').encode('utf-8')
                with self.assertRaises(ResultFormatError):
                    decode_record(damaged, 65536)
            grouping.close()
            self.assertEqual(adapter.budget.ram_bytes, 0)

    def test_header_only_empty_projection_and_static_describe(self):
        """静态描述不开文件，只有表头的EOF未知，空投影仍报告真实终点。

        参数: 无。返回: None。异常: 假EOF/伪样本/额外静态I/O断言失败。
        """
        header = self.write('empty.csv', 'ns,v,id,mode,note\n')
        for backend in ('reference', 'numpy'):
            adapter, request = self.build(backend, spec=replace(self.spec, paths=(header,)))
            with patch('pathlib.Path.open') as opened:
                adapter.describe()
            opened.assert_not_called()
            batches = list(adapter.iter_batches(request))
            self.assertEqual(len(batches), 1)
            self.assertEqual(batches[0].sample_count, 0)
            self.assertTrue(batches[0].source_eof)
            self.assertIsNone(batches[0].observed_end_ns)
            adapter.close()
            self.assertEqual(adapter.budget.ram_bytes, 0)
            projected, original_request = self.build(backend)
            batches = list(projected.iter_batches(replace(original_request, signal_names=())))
            self.assertEqual(sum(batch.sample_count for batch in batches), 0)
            self.assertEqual(batches[-1].observed_end_ns, self.start + 2)
            projected.close()
            self.assertEqual(projected.budget.ram_bytes, 0)

    def test_physical_read_failure_preserves_error_and_closes(self):
        """物理行读取OSError经原SourceReadError保留，句柄/预算回基线。

        参数: 无。返回: None。异常: 原错误链被覆盖或资源残留断言失败。
        """
        adapter, request = self.build()
        baseline = adapter.budget.ram_bytes
        original = OSError('injected physical read')
        with patch('chronaxis.execution.csv_reader._PhysicalLines.__next__', side_effect=original):
            with self.assertRaises(SourceReadError) as caught:
                next(adapter.iter_batches(request))
        self.assertIs(caught.exception.__cause__, original)
        self.assertFalse(adapter.handles)
        self.assertFalse(adapter._resources)
        self.assertEqual(adapter.budget.ram_bytes, baseline)
