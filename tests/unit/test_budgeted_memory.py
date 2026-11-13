"""验证内存来源预分配预算、原适配器行为和同刻分组。

输入是手算合成SourceSpec及明确转换/类型，输出为unittest断言；
两后端四切分完整事实与原入口一致，超限必须在pack/数组创建之前失败。
Unicode定宽提升按最长原字符串×N核算，错误/关闭释放预留且原输入保持。
相关验证仅写测试专用目录，不读写旧快照；不将内存输入当流式CSV或RSS证明。
"""

# 标准库测试/替换/注入只控制局部明确失败，不改数值核。
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow, SourceSpec, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.batch_signal_groups import BatchSignalGroups
from chronaxis.results.budget import ResourceBudget
from chronaxis.results import BudgetExceededError
from chronaxis.sources import MemorySourceAdapter, ReadRequest, SourceAdapter, SourceClosedError, SourceReadError


def batch_facts(batch) -> tuple:
    """提取小型测试批次的完整事实，不将所有输出物化作为生产实现。

    参数: batch为typed SignalBatch。返回: 列事实与进度tuple。
    异常: 模型/数组错误直接传播。
    """
    columns = tuple((name, column.dtype, column.unit, tuple(column.time_ns.tolist()),
                     tuple(column.values.tolist()), tuple(column.valid.tolist()), tuple(column.quality.tolist()),
                     tuple(column.sequence.tolist()), column.labels, column.source_ref,
                     tuple(repr(value) for value in column.original_values)) for name, column in batch.series.items())
    return (batch.source, batch.session_id, columns, batch.watermark_ns, batch.source_eof, batch.observed_end_ns)


class BudgetedMemoryTests(unittest.TestCase):
    """每项使用新预算/来源，既有完整内存输入只作合成夹具。"""

    def setUp(self) -> None:
        """声明精确大时间、大整数、同刻多更新和无效原值。

        参数: 无。返回: None。异常: 夹具错误直接失败。
        """
        self.start = 2 ** 53
        rows = (MemoryRow(time_ns=self.start, sequence=0, values={'raw.v': 1000, 'raw.name': 2 ** 64 - 1, 'raw.mode': 1}),
                MemoryRow(time_ns=self.start, sequence=1, values={'raw.v': 2000}),
                MemoryRow(time_ns=self.start + 1, sequence=2, values={'raw.v': None, 'raw.mode': 99}),
                MemoryRow(time_ns=self.start + 2, sequence=3, values={}),
                MemoryRow(time_ns=self.start + 3, sequence=4, values={'raw.v': float('nan'), 'raw.name': 1}))
        self.source = SourceSpec('table', TimebaseSpec('clock', TimeType.RELATIVE, 'budget-memory-synthetic'), rows,
                                 observation_start_ns=self.start, observation_end_ns=self.start + 4)
        self.definitions = (SignalDefinition('current', 'table', 'raw.v', D.FLOAT64, 'A', 2, input_unit='mA', scale=.001),
                            SignalDefinition('identifier', 'table', 'raw.name', D.UINT64, '1', 2),
                            SignalDefinition('mode', 'table', 'raw.mode', D.ENUM, '1', 2, choices=((1, 'scope'), (0, 'off'))))

    def build(self, backend='numpy', rows=1, budget=None):
        """创建新预算内存来源和原参数请求，不自动缩小批次。

        参数: backend/rows与原入口一致；budget为可选共享账本。
        返回: (adapter,request)。异常: 配置/预算错误传播。
        """
        adapter = BudgetedMemorySourceAdapter(budget or ResourceBudget(16 * 1024 ** 2), self.source,
                                             'session', self.definitions, backend=backend)
        self.addCleanup(adapter.close)
        request = ReadRequest('session', tuple(item.name for item in self.definitions), self.start, self.start + 4, rows)
        return adapter, request

    def test_original_adapter_facts_both_backends_and_splits(self) -> None:
        """保留原入口全部列/进度及手算值，两后端四切分均实际运行。

        参数: 无。返回: None。异常: 数值/质量/原身份/分批改变断言失败。
        """
        for backend in ('reference', 'numpy'):
            for rows in (1, 2, 7, 65536):
                adapter, request = self.build(backend, rows)
                self.assertIsInstance(adapter, SourceAdapter)
                original = MemorySourceAdapter(self.source, 'session', self.definitions, backend=backend)
                self.addCleanup(original.close)
                expected = [batch_facts(batch) for batch in original.iter_batches(request)]
                batches = list(adapter.iter_batches(request))
                self.assertEqual([batch_facts(batch) for batch in batches], expected)
                current = [(int(column.time_ns[index]), column.values[index].item(), bool(column.valid[index]))
                           for batch in batches for name, column in batch.series.items() if name == 'current'
                           for index in range(len(column.time_ns))]
                self.assertEqual(current[:2], [(self.start, 1., True), (self.start, 2., True)])
                self.assertEqual(current[2][0], self.start + 1)
                self.assertFalse(current[2][2])
                identifier = [column.values[index].item() for batch in batches for name, column in batch.series.items()
                              if name == 'identifier' for index in range(len(column.time_ns))]
                self.assertEqual(identifier, [2 ** 64 - 1, 1])
                self.assertEqual(sum(batch.sample_count for batch in batches), 8)
                self.assertLessEqual(adapter.budget.peak_ram_bytes, adapter.budget.memory_budget_bytes)
                adapter.close()
                self.assertEqual(adapter.budget.ram_bytes, 0)

    def test_input_budget_failure_precedes_adapter_construction(self) -> None:
        """完整既有输入超限时不创建原适配器或任何批次数组。

        参数: 无。返回: None。异常: 超限后仍调用原入口或预留污染断言失败。
        """
        budget = ResourceBudget(1)
        with patch('chronaxis.execution.memory_reader.MemorySourceAdapter') as original:
            with self.assertRaises(BudgetExceededError):
                BudgetedMemorySourceAdapter(budget, self.source, 'session', self.definitions)
        original.assert_not_called()
        self.assertEqual(budget.ram_bytes, 0)
        self.assertEqual(self.source.rows[0].values['raw.name'], 2 ** 64 - 1)

    def test_request_budget_failure_precedes_pack_and_keeps_source_open(self) -> None:
        """请求缓冲不足时不调用pack；解除其他占用后原来源可正常读。

        参数: 无。返回: None。异常: 归一化先分配/源状态污染断言失败。
        """
        adapter, request = self.build()
        base = adapter.budget.ram_bytes
        blocker = adapter.budget.memory_budget_bytes - base - 1
        adapter.budget.reserve_ram(blocker)
        with patch('chronaxis.sources.memory.pack_decoded') as pack:
            with self.assertRaises(BudgetExceededError):
                adapter.iter_batches(request)
        pack.assert_not_called()
        self.assertEqual(adapter.active, set())
        self.assertEqual(adapter.budget.ram_bytes, base + blocker)
        adapter.budget.release_ram(blocker)
        self.assertEqual(sum(batch.sample_count for batch in adapter.iter_batches(request)), 8)

    def test_numpy_unicode_width_promotion_preflight_and_reference_path(self) -> None:
        """原文本总长很小仍可能提升整列宽度，NumPy在创建raw数组前拒绝。

        参数: 无。返回: None。异常: Unicode最坏估算遗漏或隐式后端回退断言失败。
        """
        rows = tuple(MemoryRow(time_ns=self.start + index, sequence=index,
                     values={'raw.v': 'x' * (4096 if index == 0 else 1)}) for index in range(64))
        source = replace(self.source, rows=rows, observation_end_ns=self.start + 64)
        request = ReadRequest('session', ('current',), self.start, self.start + 64, 64)
        budget = ResourceBudget(8 * 1024 ** 2)
        numpy = BudgetedMemorySourceAdapter(budget, source, 'session', (self.definitions[0],), backend='numpy')
        self.addCleanup(numpy.close)
        with patch('chronaxis.sources.memory.pack_decoded') as pack:
            with self.assertRaises(BudgetExceededError):
                numpy.iter_batches(request)
        pack.assert_not_called()
        # 参考实现未生成宽Unicode原数组，仍以自己独立预算/数值核处理无效文本。
        reference = BudgetedMemorySourceAdapter(ResourceBudget(8 * 1024 ** 2), source, 'session', (self.definitions[0],), backend='reference')
        self.addCleanup(reference.close)
        batches = list(reference.iter_batches(request))
        self.assertEqual(sum(batch.sample_count for batch in batches), 64)
        self.assertTrue(all(not bool(valid) for batch in batches for valid in batch.series['current'].valid))

    def test_independent_requests_and_owner_close_release_leases(self) -> None:
        """各请求有独立进度/预留，关闭owner抵销全部且保留原输入。

        参数: 无。返回: None。异常: 请求污染或资源泄漏断言失败。
        """
        adapter, request = self.build()
        base = adapter.budget.ram_bytes
        first, second = adapter.iter_batches(request), adapter.iter_batches(request)
        self.assertEqual(batch_facts(next(first)), batch_facts(next(second)))
        second_cost = second.cost
        first.close()
        self.assertEqual(adapter.budget.ram_bytes, base + second_cost)
        adapter.close()
        adapter.close()
        self.assertTrue(second.closed)
        self.assertEqual(adapter.budget.ram_bytes, 0)
        self.assertEqual(self.source.rows[1].values['raw.v'], 2000)
        with self.assertRaises(SourceClosedError):
            next(second)
        with self.assertRaises(SourceClosedError):
            adapter.describe()

    def test_normalization_failure_keeps_original_chain_and_releases_request(self) -> None:
        """pack失败仍保留原适配器SourceReadError链，请求最坏预留释放。

        参数: 无。返回: None。异常: 吞异常/泄漏/原链变更断言失败。
        """
        adapter, request = self.build()
        base = adapter.budget.ram_bytes
        failure = OSError('synthetic pack failure')
        iterator = adapter.iter_batches(request)
        with patch('chronaxis.sources.memory.pack_decoded', side_effect=failure):
            with self.assertRaises(SourceReadError) as caught:
                next(iterator)
        self.assertIs(caught.exception.__cause__, failure)
        self.assertEqual(adapter.budget.ram_bytes, base)
        self.assertEqual(adapter.active, set())

    def test_constructor_contract_failure_releases_input_reservation(self) -> None:
        """原契约校验失败抵销已核算输入，不把错误来源包装为有效。

        参数: 无。返回: None。异常: 原ValueError缺失或预留泄漏断言失败。
        """
        budget = ResourceBudget(16 * 1024 ** 2)
        wrong = replace(self.definitions[0], source='other')
        with self.assertRaises(ValueError):
            BudgetedMemorySourceAdapter(budget, self.source, 'session', (wrong,))
        self.assertEqual(budget.ram_bytes, 0)

    def test_request_domain_keeps_original_lookback_and_observation(self) -> None:
        """窄请求不会在包装层丢前置保持或真实域外末点。

        参数: 无。返回: None。异常: 隐式读取裁剪或观测终点改写断言失败。
        """
        adapter, request = self.build()
        request = replace(request, domain_start_ns=self.start + 1, domain_end_ns=self.start + 2)
        batches = list(adapter.iter_batches(request))
        self.assertEqual(min(int(time) for batch in batches for column in batch.series.values() for time in column.time_ns), self.start)
        self.assertEqual(max(int(time) for batch in batches for column in batch.series.values() for time in column.time_ns), self.start + 3)
        self.assertEqual(batches[-1].observed_end_ns, self.start + 4)

    def test_shared_budget_source_groups_and_closed_inputs(self) -> None:
        """同一账本实际接通内存批次和完整同刻组，消费后输入已关闭。

        参数: 无。返回: None。异常: 接线/数量/质量/释放或文件事实改变断言失败。
        """
        with tempfile.TemporaryDirectory(prefix='chronaxis-budget-memory-') as temporary:
            budget = ResourceBudget(16 * 1024 ** 2)
            adapter, request = self.build(budget=budget)
            groups = []
            grouping = BatchSignalGroups(budget, self.definitions, 'session', groups.append)
            self.addCleanup(grouping.close)
            last = None
            for batch in adapter.iter_batches(request):
                grouping.consume(batch)
                last = batch
            grouping.finish()
            adapter.close()
            self.assertTrue(adapter.closed)
            self.assertEqual([len(group.samples) for group in groups], [4, 2, 2])
            self.assertEqual(groups[0].samples[0].time_ns, self.start)
            self.assertTrue(any(not sample.value.valid for group in groups for sample in group.samples))
            self.assertTrue(last.source_eof)
            self.assertEqual(last.observed_end_ns, self.start + 4)
            grouping.close()
            self.assertEqual(budget.ram_bytes, 0)
            self.assertLessEqual(budget.peak_ram_bytes, budget.memory_budget_bytes)

    def test_unstarted_requests_close_without_original_registration_leak(self) -> None:
        """未执行next便关闭的请求不能在原适配器中累积失效生成器。

        参数: 无。返回: None。异常: 原活动登记或预算泄漏断言失败。
        """
        adapter, request = self.build()
        base = adapter.budget.ram_bytes
        for _ in range(100):
            iterator = adapter.iter_batches(request)
            iterator.close()
        self.assertEqual(adapter.active, set())
        self.assertEqual(adapter._adapter.active, set())
        self.assertEqual(adapter.budget.ram_bytes, base)

    def test_cancelled_request_preserves_interrupt_and_releases(self) -> None:
        """取消保留原KeyboardInterrupt，释放请求后源仍可显式关闭。

        参数: 无。返回: None。异常: 取消被包装/吞掉或账本泄漏断言失败。
        """
        adapter, request = self.build()
        base = adapter.budget.ram_bytes
        iterator = adapter.iter_batches(request)
        interrupt = KeyboardInterrupt('synthetic cancel')
        with patch('chronaxis.sources.memory.pack_decoded', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt) as caught:
                next(iterator)
        self.assertIs(caught.exception, interrupt)
        self.assertEqual(adapter.budget.ram_bytes, base)
        self.assertEqual(adapter.active, set())
        self.assertEqual(adapter._adapter.active, set())
        adapter.close()
        self.assertEqual(adapter.budget.ram_bytes, 0)
