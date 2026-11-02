"""验证解码历史的精度、进度、有限状态、磁盘故障和关闭生命周期。

全部输入是有明确手算值的合成内存信号；临时文件位于测试专用目录。
两归一化后端和不同切分重放同样样本，不调用旧reader/DBC或改RefProjects。
测试只验历史子节点，完整AnalysisRunner/算子跨批一致性仍需后续集成。
"""

# 小型测试可收集结果作断言，生产历史迭代器每次只读一行。
from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow, SourceSpec, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.history_records import HistorySample, HistoryProgress, encode_record, decode_record
from chronaxis.results import AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import MemorySourceAdapter, ReadRequest, SignalBatch


class ShortWriter:
    """模拟有限短写/零写，缓冲仅用于小型测试，不作为生产文件实现。"""

    def __init__(self, limit: int):
        """保存每次最多可写的字节数和测试输出。

        参数: limit为非负小整数。返回: 新模拟句柄。异常: 无。
        """
        self.limit, self.payload = limit, bytearray()

    def write(self, payload) -> int:
        """写出前limit字节以验证生产循环能够处理短写。

        参数: payload为bytes视图。返回: 实际写入长度。异常: 无。
        """
        size = min(self.limit, len(payload))
        self.payload.extend(payload[:size])
        return size


class SignalHistoryTests(unittest.TestCase):
    """每项使用新工作目录/适配器/账本，不共享协议或关闭状态。"""

    def setUp(self) -> None:
        """构造大整数、五类型、同组重复更新和无效诊断。

        参数: 无。返回: None。异常: 夹具或临时目录错误直接失败。
        """
        self.temp = tempfile.TemporaryDirectory(prefix='chronaxis-history-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.start = 2 ** 53
        # UINT64端点不能经过float，电流单位仅归一化一次；同刻两个不同原序号保留。
        rows = (MemoryRow(time_ns=self.start, sequence=0, values={'raw.u': 2 ** 64 - 1, 'raw.i': -3, 'raw.f': 1000, 'raw.b': True, 'raw.e': 1}),
                MemoryRow(time_ns=self.start, sequence=1, values={'raw.f': 2000}),
                MemoryRow(time_ns=self.start + 1, sequence=2, values={'raw.f': float('nan'), 'raw.e': 99}),
                MemoryRow(time_ns=self.start + 2, sequence=3, values={}),
                MemoryRow(time_ns=self.start + 3, sequence=4, values={'raw.f': float('inf')}),
                MemoryRow(time_ns=self.start + 4, sequence=5, values={'raw.f': 0, 'raw.b': False, 'raw.e': 0}))
        self.source = SourceSpec('table', TimebaseSpec('clock', TimeType.RELATIVE, 'history-synthetic'), rows,
                                 observation_start_ns=self.start, observation_end_ns=self.start + 5)
        self.definitions = (SignalDefinition('unsigned', 'table', 'raw.u', D.UINT64, '1', 3),
                            SignalDefinition('signed', 'table', 'raw.i', D.INT64, '1', 3),
                            SignalDefinition('current', 'table', 'raw.f', D.FLOAT64, 'A', 3, input_unit='mA', scale=.001),
                            SignalDefinition('enabled', 'table', 'raw.b', D.BOOL, '1', 3),
                            SignalDefinition('mode', 'table', 'raw.e', D.ENUM, '1', 3, choices=((1, 'scope'), (0, 'off'))))

    def build(self, backend: str = 'numpy', rows: int = 2, budget: ResourceBudget | None = None, suffix: str = 'history'):
        """建立适配器及尚未写入的历史，关闭交由测试清理。

        参数: backend/rows选择归一化和切分；budget可共享；suffix为本测试新目录。
        返回: (adapter,request,store)。异常: 配置/目录/预算错误传播。
        """
        adapter = MemorySourceAdapter(self.source, 'session', self.definitions, backend=backend)
        self.addCleanup(adapter.close)
        request = ReadRequest('session', tuple(item.name for item in self.definitions), self.start, self.start + 5, rows)
        store = DecodedHistoryStore(budget or ResourceBudget(4 * 1024 ** 2), self.root / suffix,
                                    (adapter.describe(),), {'table': request})
        self.addCleanup(store.close)
        return adapter, request, store

    def fill(self, adapter, request, store) -> None:
        """逐批写入并封存，不在测试辅助函数中攒批次数组。

        参数: adapter/request/store为当前任务组件。返回: None。
        异常: 实际被测写入/协议错误传播。
        """
        for batch in adapter.iter_batches(request):
            store.append(batch)
        adapter.close()
        store.seal()

    def test_five_types_precision_diagnostics_and_split_equivalence(self) -> None:
        """手算核对五类型、单位、1ns及两后端四切分样本事实。

        参数: 无。返回: None。异常: 任何事实偏离均断言失败。
        """
        baseline = None
        for backend in ('reference', 'numpy'):
            for rows in (1, 2, 7, 100):
                adapter, request, store = self.build(backend, rows, suffix=f'{backend}-{rows}')
                self.fill(adapter, request, store)
                records = list(store.iter_records('table'))
                samples = [record for record in records if isinstance(record, HistorySample)]
                # 跨列同刻的传输顺序会随切分改变，业务事实按原身份比较；每列原更新全部保留。
                facts = sorted([(record.name, record.time_ns, record.sequence, record.array_value,
                          record.value.dtype, record.value.valid, record.value.quality,
                          repr(record.original_value), record.source_ref) for record in samples],
                          key=lambda item: (item[1], item[2], item[0]))
                if baseline is None:
                    baseline = facts
                self.assertEqual(facts, baseline)
                self.assertEqual(len(samples), 12)
                self.assertEqual(next(item for item in samples if item.name == 'unsigned').array_value, 2 ** 64 - 1)
                current = [item for item in samples if item.name == 'current']
                self.assertEqual([item.value.value for item in current[:2]], [1., 2.])
                self.assertEqual(current[2].time_ns, self.start + 1)
                self.assertFalse(current[2].value.valid)
                self.assertTrue(math.isnan(current[2].original_value))
                self.assertTrue(math.isinf(current[3].original_value))
                mode = [item for item in samples if item.name == 'mode']
                self.assertEqual(mode[0].value.value, 'scope')
                self.assertFalse(mode[1].value.valid)
                self.assertEqual(mode[1].original_value, 99)
                self.assertEqual(mode[2].value.value, 'off')
                self.assertTrue(records[-1].source_eof)
                self.assertLessEqual(store.budget.peak_ram_bytes, store.budget.memory_budget_bytes)
                store.close()
                self.assertEqual(store.budget.ram_bytes, 0)

    def test_empty_batch_and_unknown_observation_are_preserved(self) -> None:
        """空投影的未知终点保留None，EOF不被解释为周期或无限有效。

        参数: 无。返回: None。异常: 事实重建错误断言失败。
        """
        adapter, request, original = self.build()
        original.close()
        description = replace(adapter.describe(), observation_end_ns=None)
        request = replace(request, signal_names=())
        budget = ResourceBudget(1024 ** 2)
        store = DecodedHistoryStore(budget, self.root / 'empty', (description,), {'table': request})
        self.addCleanup(store.close)
        store.append(SignalBatch('table', 'session', {}, None, False, None))
        with self.assertRaises(AnalysisError):
            store.seal()
        store.append(SignalBatch('table', 'session', {}, self.start, True, None))
        store.seal()
        records = list(store.iter_records('table'))
        self.assertEqual([item.sample_count for item in records], [0, 0])
        self.assertIsNone(records[0].watermark_ns)
        self.assertIsNone(records[-1].observed_end_ns)

    def test_independent_iterators_close_and_files_survive(self) -> None:
        """两个游标各自从首行开始，关闭所有活跃句柄并保留历史文件。

        参数: 无。返回: None。异常: 生命周期或资源泄漏断言失败。
        """
        adapter, request, store = self.build()
        self.fill(adapter, request, store)
        first, second = store.iter_records('table'), store.iter_records('table')
        self.assertEqual(next(first), next(second))
        next(first)
        path = store.work_dir / 'table.jsonl'
        store.close()
        store.close()
        self.assertTrue(first.handle.closed and second.handle.closed)
        self.assertTrue(path.exists())
        self.assertEqual(store.budget.ram_bytes, 0)
        with self.assertRaises(ResultClosedError):
            next(first)
        with self.assertRaises(ResultClosedError):
            store.iter_records('table')

    def test_existing_directory_and_mixed_session_rejected(self) -> None:
        """历史不覆盖既有用户目录，也不把不同会话合并为一次运行。

        参数: 无。返回: None。异常: 拒绝缺失断言失败。
        """
        adapter, request, store = self.build()
        marker = store.work_dir / 'user.txt'
        marker.write_text('keep', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            DecodedHistoryStore(ResourceBudget(), store.work_dir, (adapter.describe(),), {'table': request})
        self.assertEqual(marker.read_text(encoding='utf-8'), 'keep')
        other = replace(adapter.describe(), name='other', fields=())
        with self.assertRaises(ValueError):
            DecodedHistoryStore(ResourceBudget(), self.root / 'mixed', (adapter.describe(), other),
                                {'table': request, 'other': replace(request, session_id='another', signal_names=())})
        self.assertFalse((self.root / 'mixed').exists())

    def test_ram_failure_before_protocol_or_write(self) -> None:
        """预算不足不继续分配协议集合/编码；共享账本其他使用者仍保留。

        参数: 无。返回: None。异常: 错误类型/计数/文件偏离断言失败。
        """
        budget = ResourceBudget(1024 ** 2)
        adapter, request, store = self.build(budget=budget)
        blocker = budget.memory_budget_bytes - budget.ram_bytes - 1
        budget.reserve_ram(blocker)
        batch = next(adapter.iter_batches(request))
        with self.assertRaises(AnalysisError) as caught:
            store.append(batch)
        self.assertIsInstance(caught.exception.__cause__, BudgetExceededError)
        self.assertEqual(store.state, 'failed')
        self.assertEqual(budget.ram_bytes, blocker)
        self.assertFalse((store.work_dir / 'table.jsonl').exists())
        budget.release_ram(blocker)

    def test_spool_quota_failure_closes_and_cannot_seal(self) -> None:
        """磁盘配额超限立即失败，不丢行继续或标为完整。

        参数: 无。返回: None。异常: 预算/清理/生命周期断言失败。
        """
        budget = ResourceBudget(1024 ** 2, 1)
        adapter, request, store = self.build(budget=budget)
        with self.assertRaises(AnalysisError) as caught:
            store.append(next(adapter.iter_batches(request)))
        self.assertIsInstance(caught.exception.__cause__, BudgetExceededError)
        self.assertTrue(store.closed)
        self.assertEqual(budget.ram_bytes, 0)
        with self.assertRaises(ResultClosedError):
            store.seal()

    def test_disk_error_and_cancellation_keep_original_failure(self) -> None:
        """实际写入故障/取消关闭句柄，原原因不被诊断失败替换。

        参数: 无。返回: None。异常: 原异常链或取消身份不一致断言失败。
        """
        for failure in (OSError('disk full'), KeyboardInterrupt('cancel')):
            adapter, request, store = self.build(suffix=type(failure).__name__)
            batch = next(adapter.iter_batches(request))
            with patch.object(store, '_write_bytes', side_effect=failure):
                with self.assertRaises(type(failure) if isinstance(failure, KeyboardInterrupt) else AnalysisError) as caught:
                    store.append(batch)
            self.assertTrue(store.closed)
            self.assertEqual(store.budget.ram_bytes, 0)
            self.assertEqual(store.state, 'cancelled' if isinstance(failure, KeyboardInterrupt) else 'failed')
            if isinstance(failure, OSError):
                self.assertIs(caught.exception.__cause__, failure)

    def test_duplicate_same_group_cross_batch_rejected(self) -> None:
        """尚未完整同组的重复原序号失败，不重复计入面积/事件。

        参数: 无。返回: None。异常: 重复接受或资源泄漏断言失败。
        """
        adapter, request, store = self.build(rows=1)
        batch = next(adapter.iter_batches(request))
        self.assertIsNone(batch.watermark_ns)
        store.append(batch)
        with self.assertRaises(AnalysisError) as caught:
            store.append(batch)
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertEqual(store.budget.ram_bytes, 0)

    def test_corrupt_truncated_or_same_length_changed_file_fails(self) -> None:
        """不完整尾行及合法JSON内同长度篡改均不能通过完整重放。

        参数: 无。返回: None。异常: 损坏未发现/句柄泄漏断言失败。
        """
        for truncated in (True, False):
            adapter, request, store = self.build(suffix=f'corrupt-{truncated}')
            self.fill(adapter, request, store)
            path = store.work_dir / 'table.jsonl'
            payload = path.read_bytes()
            changed = payload[:-2] if truncated else payload.replace(b'18446744073709551615', b'18446744073709551614')
            self.assertNotEqual(changed, payload)
            path.write_bytes(changed)
            iterator = store.iter_records('table')
            with self.assertRaises(ResultFormatError):
                list(iterator)
            self.assertTrue(iterator.handle.closed)
            self.assertEqual(len(store._iterators), 0)

    def test_strict_record_format_and_original_column_presence(self) -> None:
        """严格版本/重复键/额外字段拒绝，原诊断None不等于无原列。

        参数: 无。返回: None。异常: 非法格式未拒绝断言失败。
        """
        adapter, request, store = self.build()
        self.fill(adapter, request, store)
        record = next(store.iter_records('table'))
        absent = replace(record, original_present=False, original_value=None)
        self.assertFalse(decode_record(encode_record(absent, 8192), 8192).original_present)
        self.assertTrue(decode_record(encode_record(replace(absent, original_present=True), 8192), 8192).original_present)
        for payload in (b'{"history_version":1,"history_version":1}\n',
                        b'{"history_version":true,"record_type":"progress","values":{"tuple":[]}}\n',
                        b'{"history_version":1,"record_type":"progress","values":{"tuple":[]},"extra":0}\n'):
            with self.assertRaises(ResultFormatError):
                decode_record(payload, 8192)

    def test_many_completed_groups_do_not_retain_history_ram(self) -> None:
        """输入规模增长只增加磁盘历史，已完整时间组释放去重状态。

        参数: 无。返回: None。异常: 峰值随历史线性增长或记录丢失断言失败。
        """
        peaks = []
        for count in (32, 512):
            # 全量内存SourceSpec是测试输入，组件仅声明对收到的批次/历史预算负责。
            source = replace(self.source, rows=tuple(MemoryRow(time_ns=self.start + index, sequence=index,
                             values={'raw.f': 1000}) for index in range(count)), observation_end_ns=self.start + count)
            adapter = MemorySourceAdapter(source, 'session', (self.definitions[2],))
            self.addCleanup(adapter.close)
            request = ReadRequest('session', ('current',), self.start, self.start + count, 1)
            budget = ResourceBudget(1024 ** 2)
            store = DecodedHistoryStore(budget, self.root / f'many-{count}', (adapter.describe(),), {'table': request})
            self.addCleanup(store.close)
            self.fill(adapter, request, store)
            self.assertEqual(sum(isinstance(record, HistorySample) for record in store.iter_records('table')), count)
            self.assertEqual(store.validators['table'].pending, {})
            peaks.append(budget.peak_ram_bytes)
            store.close()
            self.assertEqual(budget.ram_bytes, 0)
        # 固定预算覆盖单批/读行，规模16倍不允许保留全量样本对象。
        self.assertLessEqual(peaks[1], peaks[0] + 8192)

    def test_unfinished_group_identity_state_is_budgeted(self) -> None:
        """超大同刻组不能无界积累去重集合，超限失败且不丢样本继续。

        参数: 无。返回: None。异常: 未触发预算、错误原因或账本泄漏断言失败。
        """
        source = replace(self.source, rows=tuple(MemoryRow(time_ns=self.start, sequence=index,
                         values={'raw.f': 1000}) for index in range(5000)), observation_end_ns=self.start + 1)
        adapter = MemorySourceAdapter(source, 'session', (self.definitions[2],))
        self.addCleanup(adapter.close)
        request = ReadRequest('session', ('current',), self.start, self.start + 1, 1)
        budget = ResourceBudget(1024 ** 2)
        store = DecodedHistoryStore(budget, self.root / 'huge-group', (adapter.describe(),), {'table': request})
        self.addCleanup(store.close)
        written = 0
        with self.assertRaises(AnalysisError) as caught:
            for batch in adapter.iter_batches(request):
                store.append(batch)
                written += batch.sample_count
        self.assertIsInstance(caught.exception.__cause__, BudgetExceededError)
        self.assertGreater(written, 0)
        self.assertLess(written, 5000)
        self.assertLessEqual(budget.peak_ram_bytes, budget.memory_budget_bytes)
        self.assertEqual(budget.ram_bytes, 0)
        self.assertEqual(store.state, 'failed')

    def test_all_configured_sources_must_finish_before_seal(self) -> None:
        """一个来源先EOF不能提前封存仍活动的其他来源。

        参数: 无。返回: None。异常: 提前封存或跨来源事实混合断言失败。
        """
        adapter, request, original = self.build()
        original.close()
        second = replace(adapter.describe(), name='other', fields=())
        store = DecodedHistoryStore(ResourceBudget(2 * 1024 ** 2), self.root / 'two-sources',
                                    (adapter.describe(), second),
                                    {'table': request, 'other': replace(request, signal_names=())})
        self.addCleanup(store.close)
        for batch in adapter.iter_batches(request):
            store.append(batch)
        with self.assertRaises(AnalysisError):
            store.seal()
        store.append(SignalBatch('other', 'session', {}, self.start + 4, True, self.start + 5))
        store.seal()
        self.assertEqual(len(list(store.iter_records('other'))), 1)
        self.assertEqual(sum(isinstance(item, HistorySample) for item in store.iter_records('table')), 12)

    def test_short_write_progress_and_zero_write_rejection(self) -> None:
        """合法短写完成原字节，零写明确失败，累计配额不隐式抵销。

        参数: 无。返回: None。异常: 写出内容或配额不符断言失败。
        """
        adapter, request, store = self.build()
        writer = ShortWriter(2)
        store._write_bytes(writer, b'abcdefg')
        self.assertEqual(bytes(writer.payload), b'abcdefg')
        self.assertEqual(store.budget.spool_bytes, 7)
        with self.assertRaises(OSError):
            store._write_bytes(ShortWriter(0), b'xyz')
        self.assertEqual(store.budget.spool_bytes, 10)

    def test_reader_budget_failure_preserves_sealed_store(self) -> None:
        """游标RAM不足时不打开新句柄，解除占用后历史仍可完整读。

        参数: 无。返回: None。异常: 失败后账本或生命周期污染断言失败。
        """
        adapter, request, store = self.build()
        self.fill(adapter, request, store)
        base = store.budget.ram_bytes
        blocker = store.budget.memory_budget_bytes - base - 1
        store.budget.reserve_ram(blocker)
        with self.assertRaises(BudgetExceededError):
            store.iter_records('table')
        self.assertEqual(store.budget.ram_bytes, base + blocker)
        self.assertEqual(store._iterators, set())
        self.assertEqual(store.state, 'sealed')
        store.budget.release_ram(blocker)
        self.assertTrue(list(store.iter_records('table'))[-1].source_eof)

    def test_constructor_late_failure_releases_reserved_state(self) -> None:
        """固定结构初始化后段失败也释放账本，尚未产生工作目录。

        参数: 无。返回: None。异常: 初始化错误被隐藏或预留泄漏断言失败。
        """
        adapter, request, original = self.build()
        original.close()
        budget = ResourceBudget(1024 ** 2)
        path = self.root / 'failed-init'
        with patch('chronaxis.execution.history.sha256', side_effect=MemoryError('digest init')):
            with self.assertRaises(MemoryError):
                DecodedHistoryStore(budget, path, (adapter.describe(),), {'table': request})
        self.assertEqual(budget.ram_bytes, 0)
        self.assertFalse(path.exists())
