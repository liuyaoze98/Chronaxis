"""验证封存解码历史完整时间组、五来源归并及预算/失败关闭。

合成资料包含2**53处1ns差、每来源同刻两次不同原更新、提前EOF和空来源。
两归一化后端及四种batch切分与手算组事实核对，不读取旧CAN或改快照。
测试中收集少量组供比较；生产API的返回组须即时消费，不保证调用方攒全量输出。
"""

# 标准库夹具/替换/注入只测试明确故障，不改变产品语义。
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow, SourceSpec, TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.results import AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import MemorySourceAdapter, ReadRequest


class TimeGroupTests(unittest.TestCase):
    """每测试新目录/来源/账本，互不继承完成进度与关闭状态。"""

    def setUp(self) -> None:
        """建立真实测试专用目录和精确大时间坐标。

        参数: 无。返回: None。异常: 临时目录错误直接失败。
        """
        self.temp = tempfile.TemporaryDirectory(prefix='chronaxis-groups-')
        self.addCleanup(self.temp.cleanup)
        self.root, self.start = Path(self.temp.name), 2 ** 53

    def build(self, backend='numpy', rows=1, suffix='groups', empty=False, seal=True):
        """逐源写入五个明确解码历史；可附加未知观测的空来源。

        参数: backend/rows为归一化及切分；suffix为新目录；empty/seal控制夹具。
        返回: DecodedHistoryStore。异常: 夹具/协议/预算/文件错误传播。
        """
        adapters, requests = [], {}
        for index in range(5):
            name, alias = f'src{index}', f'v{index}'
            samples = [MemoryRow(time_ns=self.start, sequence=0, values={'raw': index}),
                       MemoryRow(time_ns=self.start, sequence=1, values={'raw': index + 10})]
            if index in (1, 4):
                samples.append(MemoryRow(time_ns=self.start + (1 if index == 1 else 2), sequence=2, values={'raw': index + 20}))
            source = SourceSpec(name, TimebaseSpec('clock', TimeType.RELATIVE, 'groups-synthetic'), tuple(samples),
                                observation_start_ns=self.start, observation_end_ns=self.start + (0 if index == 0 else 3))
            definition = SignalDefinition(alias, name, 'raw', SignalDType.INT64, '1', 1)
            adapter = MemorySourceAdapter(source, 'session', (definition,), backend=backend)
            self.addCleanup(adapter.close)
            adapters.append(adapter)
            requests[name] = ReadRequest('session', (alias,), self.start, self.start + 3, rows)
        if empty:
            source = SourceSpec('empty', TimebaseSpec('clock', TimeType.RELATIVE, 'groups-synthetic'), (),
                                observation_start_ns=None, observation_end_ns=None)
            adapter = MemorySourceAdapter(source, 'session', (), backend=backend)
            self.addCleanup(adapter.close)
            adapters.append(adapter)
            requests['empty'] = ReadRequest('session', (), self.start, self.start + 3, rows)
        store = DecodedHistoryStore(ResourceBudget(4 * 1024 ** 2), self.root / suffix,
                                    tuple(adapter.describe() for adapter in adapters), requests)
        self.addCleanup(store.close)
        if seal:
            for adapter in adapters:
                for batch in adapter.iter_batches(requests[adapter.source.name]):
                    store.append(batch)
                adapter.close()
            store.seal()
        return store

    def test_atomic_five_sources_both_backends_and_four_splits(self) -> None:
        """同刻十个更新只返回一组，1ns后/2ns后各返回一组，跨来源早EOF仍正确。

        参数: 无。返回: None。异常: 手算或两后端切分事实不符断言失败。
        """
        baseline = None
        for backend in ('reference', 'numpy'):
            for rows in (1, 2, 7, 100):
                store = self.build(backend, rows, suffix=f'{backend}-{rows}')
                groups = list(store.iter_groups())
                self.assertEqual([group.time_ns for group in groups], [self.start, self.start + 1, self.start + 2])
                self.assertEqual([len(group.samples) for group in groups], [10, 1, 1])
                facts = [(group.time_ns, tuple((sample.source_ref.source_name, sample.name, sample.sequence,
                          sample.value.value, sample.value.dtype, sample.value.valid, sample.value.quality) for sample in group.samples)) for group in groups]
                if baseline is None:
                    baseline = facts
                self.assertEqual(facts, baseline)
                # 同一别名同刻的两个原更新都保留，不在分组层隐式last或error。
                self.assertEqual([sample.value.value for sample in groups[0].samples if sample.name == 'v0'], [0, 10])
                self.assertEqual(groups[1].samples[0].value.value, 21)
                self.assertEqual(groups[2].samples[0].value.value, 24)
                self.assertEqual(store.source_completions['src0'].observed_end_ns, self.start)
                self.assertEqual(store.source_completions['src4'].observed_end_ns, self.start + 3)
                self.assertEqual(store._groups, set())
                self.assertEqual(store._iterators, set())
                self.assertLessEqual(store.budget.peak_ram_bytes, store.budget.memory_budget_bytes)
                store.close()
                self.assertEqual(store.budget.ram_bytes, 0)

    def test_empty_source_unknown_end_does_not_invent_sample(self) -> None:
        """空来源EOF的未知终点保持None，不制造时间0或使其他源结束。

        参数: 无。返回: None。异常: 假样本/终点/进度修改断言失败。
        """
        store = self.build(empty=True)
        self.assertIsNone(store.source_completions['empty'].observed_end_ns)
        self.assertTrue(store.source_completions['empty'].source_eof)
        with self.assertRaises(TypeError):
            store.source_completions['empty'] = store.source_completions['src0']
        self.assertEqual(sum(len(group.samples) for group in store.iter_groups()), 12)

    def test_owner_close_releases_live_group_and_all_readers(self) -> None:
        """返回当前组后owner关闭仍释放组预留和全部分源游标。

        参数: 无。返回: None。异常: 活跃资源泄漏或关闭后继续读取断言失败。
        """
        store = self.build()
        iterator = store.iter_groups()
        readers = tuple(iterator.readers)
        self.assertEqual(len(next(iterator).samples), 10)
        self.assertGreater(iterator._group_cost, 0)
        store.close()
        self.assertTrue(iterator.closed)
        self.assertTrue(all(reader.handle.closed for reader in readers))
        self.assertEqual(store.budget.ram_bytes, 0)
        with self.assertRaises(ResultClosedError):
            next(iterator)

    def test_group_budget_failure_does_not_deliver_partial_group(self) -> None:
        """预算不足时整个组失败且游标关闭，解除其他占用后可独立重放。

        参数: 无。返回: None。异常: 部分组/泄漏或历史状态污染断言失败。
        """
        store = self.build()
        base = store.budget.ram_bytes
        iterator = store.iter_groups()
        blocker = store.budget.memory_budget_bytes - store.budget.ram_bytes - 1
        store.budget.reserve_ram(blocker)
        with self.assertRaises(BudgetExceededError):
            next(iterator)
        self.assertTrue(iterator.closed)
        self.assertEqual(store.budget.ram_bytes, base + blocker)
        self.assertEqual(store.state, 'sealed')
        store.budget.release_ram(blocker)
        self.assertEqual(len(list(store.iter_groups())), 3)

    def test_mid_open_budget_failure_closes_preceding_reader(self) -> None:
        """第二个分源游标预算申请失败时第一个句柄和组状态也释放。

        参数: 无。返回: None。异常: 原预算失败被替换或前句柄泄漏断言失败。
        """
        store = self.build()
        base = store.budget.ram_bytes
        original_reserve, original_iter = store.budget.reserve_ram, store.iter_records
        opened, calls = [], []

        def reserve(amount):
            """在组状态/首游标成功后注入第二游标预算错误。

            参数: amount为真实申请。返回: None。异常: 第三次BudgetExceededError。
            """
            calls.append(amount)
            if len(calls) == 3:
                raise BudgetExceededError('second reader')
            original_reserve(amount)

        def record_reader(source):
            """保存实际成功打开的游标供关闭断言。

            参数: source为来源名。返回: 原真实游标。异常: 原打开错误传播。
            """
            reader = original_iter(source)
            opened.append(reader)
            return reader

        with patch.object(store.budget, 'reserve_ram', side_effect=reserve), patch.object(store, 'iter_records', side_effect=record_reader):
            with self.assertRaises(BudgetExceededError):
                store.iter_groups()
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].handle.closed)
        self.assertEqual(store.budget.ram_bytes, base)
        self.assertEqual(store._iterators, set())

    def test_reader_digest_constructor_failure_releases_lease(self) -> None:
        """游标固定结构/摘要构造失败不遗留预算或已打开文件。

        参数: 无。返回: None。异常: 原失败未传播或资源泄漏断言失败。
        """
        store = self.build()
        base = store.budget.ram_bytes
        with patch('chronaxis.execution.history.sha256', side_effect=MemoryError('reader digest')):
            with self.assertRaises(MemoryError):
                store.iter_records('src0')
        self.assertEqual(store.budget.ram_bytes, base)
        self.assertEqual(store._iterators, set())

    def test_corrupt_history_aborts_group_and_closes_every_source(self) -> None:
        """同组来源尾行截断时不能返回被视为完整的部分组。

        参数: 无。返回: None。异常: 损坏未阻止组提交或句柄泄漏断言失败。
        """
        store = self.build()
        path = store.work_dir / 'src0.jsonl'
        path.write_bytes(path.read_bytes()[:-1])
        base = store.budget.ram_bytes
        iterator = store.iter_groups()
        readers = tuple(iterator.readers)
        with self.assertRaises(ResultFormatError):
            next(iterator)
        self.assertTrue(all(reader.handle.closed for reader in readers))
        self.assertEqual(store.budget.ram_bytes, base)
        self.assertEqual(store._groups, set())

    def test_unsealed_history_and_mixed_group_identity_rejected(self) -> None:
        """未确认全部EOF的历史不能离线提交组，组模型拒绝跨时刻/重复观测。

        参数: 无。返回: None。异常: 拒绝缺失断言失败。
        """
        store = self.build(seal=False)
        with self.assertRaises(AnalysisError):
            store.iter_groups()
        ready = self.build(suffix='ready')
        group = next(ready.iter_groups())
        with self.assertRaises(ValueError):
            DecodedTimeGroup(group.time_ns + 1, group.samples)
        with self.assertRaises(ValueError):
            DecodedTimeGroup(group.time_ns, (group.samples[0], group.samples[0]))
        other = replace(group.samples[0], source_ref=replace(group.samples[0].source_ref, session_id='another'))
        with self.assertRaises(ValueError):
            DecodedTimeGroup(group.time_ns, (group.samples[0], other))
