"""用真实内存及CSV来源验证单次读取与同一history的首末原行关联。

所有输入现场合成于work/m2-run-tests/observed-ingestion，来源标签home。
专项覆盖两后端、批次1/2/7、空投影、全空、单点及只加一次offset，核实际文件
SHA和进度/样本计数，拒绝相等但非原request、半写历史与来源config替换。
故障只注入新scan自有预算或实际CSV读/FD，不修旧memory/history默认关闭风险。
有限夹具可物化比较，不把测试列表当作生产有界实现或真实用户日志验收。
"""

# 测试使用真实数据模型和budget，不用手造观测事实代替实际扫描。
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow, SourceSpec, TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.observed_ingestion import ObservedSourceScan, SourceScanObservation
from chronaxis.planning.models import SourcePlan
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import SignalCSVSpec
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.protocol import SourceReadError


class ObservedSourceScanTests(unittest.TestCase):
    """每例创建独立来源和history，显式调用方标记最后归还并核最终余额0。"""

    def fixture(self, *, kind='memory', backend='numpy', size=2, projection=('value',),
                times=(1, 1, 4), offset=7, declared=True, bad_csv=False):
        """创建真正原source/config及预算适配器，不预读或构造观测模型。

        参数: kind为memory或signal_csv；backend、size、projection沿真实请求；times
            为原行时间，offset只在来源应用；declared仅控制memory原边界；bad_csv造坏时间。
        返回: history、source_plan、adapter、request、budget。异常: 原模型、文件或预算错误。
        """
        # 唯一work目录保留证据，不覆盖任何用户输入或旧项目快照。
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/observed-ingestion' / uuid4().hex
        work.mkdir(parents=True)
        budget = ResourceBudget(16 * 1024 ** 2)
        self.addCleanup(self.assert_zero, budget)
        budget.reserve_ram(8192)
        self.addCleanup(budget.release_ram, 8192)
        timebase = TimebaseSpec('clock', TimeType.RELATIVE, 'observed-ingestion-home')
        definitions = (SignalDefinition('value', 'table', 'v', SignalDType.FLOAT64, '1', 20),)
        if kind == 'memory':
            # 中间同刻原行没有投影更新，但仍必须计入raw row_count。
            rows = tuple(MemoryRow(time_ns=time, sequence=index,
                         values={} if index == 1 else {'v': index + 2})
                         for index, time in enumerate(times))
            config = SourceSpec('table', timebase, rows, offset,
                0 if declared else None, max(6, times[-1]) if declared and times else 6 if declared else None)
            adapter = BudgetedMemorySourceAdapter(budget, config, 'session', definitions, backend=backend)
        else:
            path = work / 'input.csv'
            lines = ['ns,v'] + [str(time) + ',' + ('' if index == 1 else str(index + 2))
                               for index, time in enumerate(times)]
            if bad_csv:
                lines.append('not_time,5')
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            config = SignalCSVSpec('table', (path,), timebase, 'ns', 'ns', offset)
            adapter = BudgetedSignalCSVSourceAdapter(budget, config, 'session', definitions, backend=backend)
        self.addCleanup(adapter.close)
        source_plan = SourcePlan('table', kind, config, 'ns', None, 'synthetic-source-home', MappingProxyType({}))
        request = ReadRequest('session', projection, -100, 100, size)
        history = DecodedHistoryStore(budget, work / 'history', (adapter.describe(),), {'table': request})
        self.addCleanup(history.close)
        return history, source_plan, adapter, request, budget

    def assert_zero(self, budget):
        """最后核全部真实自有和借用账目已归还。参数: budget共享账本。返回: None。异常: 漏账断言失败。
        """
        self.assertEqual(budget.ram_bytes, 0)

    def scan(self, data):
        """创建本次真实扫描并登记关闭。参数: fixture结果。返回: scan。异常: 原构造错误。
        """
        history, plan, adapter, request, budget = data
        owner = ObservedSourceScan(history, plan, adapter, request)
        self.addCleanup(owner.close)
        return owner

    def cancel_once(self, actual, error, *, after=False, amount=None):
        """在一笔真实预算调用前后仅取消一次。参数: 原方法/原错/阶段/可选金额。返回: wrapper。异常: 指定原错。
        """
        reached = []

        def invoke(value):
            """转交真实账本并在指定位置注入。参数: 原bytes。返回: 原返回。异常: 指定原错误。
            """
            if not reached and (amount is None or value == amount):
                reached.append(value)
                if after:
                    actual(value)
                raise error
            return actual(value)

        return invoke

    def assert_snapshot(self, data, owner, *, first, last, rows, start, end):
        """按独立原行真值及真实文件摘要核完成快照。参数: fixture/scan/原行与范围真值。返回: None。异常: 关联错误。
        """
        history, plan, adapter, request, budget = data
        self.assertTrue(owner.finished)
        self.assertFalse(owner.failed)
        self.assertFalse(owner.closed)
        self.assertIs(owner.history, history)
        self.assertIs(owner.source_plan, plan)
        self.assertIs(owner.request, request)
        observation = owner.observation
        self.assertIsInstance(observation, SourceScanObservation)
        self.assertEqual((observation.source, observation.session_id), ('table', 'session'))
        self.assertEqual((observation.first_ns, observation.last_ns, observation.row_count,
            observation.observed_start_ns, observation.observed_end_ns, observation.source_eof),
            (first, last, rows, start, end, True))
        self.assertEqual(owner.counts, tuple(history.counts['table']))
        self.assertEqual(owner.history_sha256, sha256(history.paths['table'].read_bytes()).hexdigest())
        history.seal()
        reader = history.iter_records('table')
        self.addCleanup(reader.close)
        for record in reader:
            record = None
        self.assertTrue(reader.verified_eof)
        reader.close()

    def test_real_memory_csv_backends_and_batches_preserve_raw_rows_and_history_identity(self):
        """十二组合核同刻原行、缺字段/缺失、一次offset及真实SHA/count。参数: 无。返回: None。异常: 真值或身份错误。
        """
        for kind in ('memory', 'signal_csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        data = self.fixture(kind=kind, backend=backend, size=size)
                        owner = self.scan(data)
                        self.assertIsNone(owner.consume())
                        # memory声明0—6后加7，CSV实际原行1—4后加7，没有二次偏移。
                        self.assert_snapshot(data, owner, first=8, last=11, rows=3,
                            start=7 if kind == 'memory' else 8, end=13 if kind == 'memory' else 11)
                        self.assertEqual(owner.counts[1], 2 if kind == 'memory' else 3)
                        self.assertIsNone(owner.consume())

    def test_empty_projection_empty_source_and_single_point_are_distinct(self):
        """原行空投影仍有范围，全空保None，单点首末相等不伪造成空源。参数: 无。返回: None。异常: 范围混淆。
        """
        for kind in ('memory', 'signal_csv'):
            for times, projection in (((1, 4), ()), ((), ('value',)), ((3,), ('value',))):
                with self.subTest(kind=kind, times=times, projection=projection):
                    data = self.fixture(kind=kind, times=times, projection=projection, declared=False, offset=2)
                    owner = self.scan(data)
                    owner.consume()
                    first = times[0] + 2 if times else None
                    last = times[-1] + 2 if times else None
                    self.assert_snapshot(data, owner, first=first, last=last, rows=len(times), start=first, end=last)
                    if not projection:
                        self.assertEqual(owner.counts[1], 0)

    def test_external_completed_read_cannot_make_unconsumed_scan_a_history_proof(self):
        """相同request独立read可完成，但没有向本history写入就不能成为scan事实。参数: 无。返回: None。异常: 错认独立读取。
        """
        data = self.fixture(kind='signal_csv')
        history, plan, adapter, request, budget = data
        owner = self.scan(data)
        external = adapter.iter_batches_with_observation(request)
        self.addCleanup(external.close)
        for batch in external:
            batch = None
        self.assertTrue(external.exhausted)
        self.assertEqual(history.counts['table'], [0, 0])
        with self.assertRaises(ResultClosedError):
            _ = owner.observation
        owner.consume()
        self.assertEqual(owner.observation.row_count, 3)
        external.close()

    def test_original_request_config_budget_and_unwritten_source_are_required(self):
        """拒绝仅值相等请求、复制config、不同budget及半写history。参数: 无。返回: None。异常: 合同绕过。
        """
        data = self.fixture(kind='signal_csv', size=1)
        history, plan, adapter, request, budget = data
        baseline = budget.ram_bytes
        with self.assertRaises(ValueError):
            ObservedSourceScan(history, plan, adapter, replace(request))
        with self.assertRaises(ValueError):
            ObservedSourceScan(history, replace(plan, config=replace(plan.config)), adapter, request)
        other = BudgetedSignalCSVSourceAdapter(ResourceBudget(16 * 1024 ** 2), plan.config,
            'session', adapter.signals)
        self.addCleanup(other.close)
        with self.assertRaises(ValueError):
            ObservedSourceScan(history, plan, other, request)
        self.assertEqual(budget.ram_bytes, baseline)
        read = adapter.iter_batches(request)
        self.addCleanup(read.close)
        history.append(next(read))
        read.close()
        with self.assertRaises(ValueError):
            ObservedSourceScan(history, plan, adapter, request)

    def test_source_replacement_or_external_append_before_consume_is_rejected(self):
        """已构造scan不能接替换来源或接别人已写的批次。参数: 无。返回: None。异常: 首端证明串线。
        """
        for kind in ('memory', 'signal_csv'):
            data = self.fixture(kind=kind)
            history, plan, adapter, request, budget = data
            owner = self.scan(data)
            if kind == 'memory':
                adapter._adapter.source = replace(plan.config, offset_ns=8)
            else:
                adapter.spec = replace(plan.config, offset_ns=8)
            with self.assertRaises(ValueError):
                owner.consume()
            self.assertTrue(owner.failed)
            self.assertEqual(history.counts['table'], [0, 0])
            owner.close()
        data = self.fixture(kind='signal_csv')
        history, plan, adapter, request, budget = data
        owner = self.scan(data)
        read = adapter.iter_batches(request)
        self.addCleanup(read.close)
        history.append(next(read))
        read.close()
        before = tuple(history.counts['table'])
        with self.assertRaises(ValueError):
            owner.consume()
        self.assertEqual(tuple(history.counts['table']), before)

    def test_fixed_reserve_cancel_limit_and_unreturned_cleanup_preserve_top_scan(self):
        """新owner首笔真实预算前后取消、超限及持续清理都保原错和最高恢复。参数: 无。返回: None。异常: 漏费或盖错。
        """
        for after in (False, True):
            data = self.fixture(kind='signal_csv')
            history, plan, adapter, request, budget = data
            baseline = budget.ram_bytes
            original = KeyboardInterrupt('observed-scan-reserve')
            with patch.object(budget, 'reserve_ram', self.cancel_once(budget.reserve_ram, original, after=after)):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    self.scan(data)
            self.assertIs(caught.exception, original)
            self.assertEqual(budget.ram_bytes, baseline)
        data = self.fixture(kind='signal_csv')
        history, plan, adapter, request, budget = data
        baseline = budget.ram_bytes
        original = MemoryError('observed-scan-unreturned')
        with patch.object(budget, 'reserve_ram', self.cancel_once(budget.reserve_ram, original, after=True)), \
             patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt('persistent scan cleanup')):
            with self.assertRaises(MemoryError) as caught:
                self.scan(data)
        recovered = getattr(original, 'observed_source_scan_cleanup_owner', None)
        self.assertIsNotNone(recovered)
        self.addCleanup(recovered.close)
        recovered.close()
        self.assertEqual(budget.ram_bytes, baseline)
        limit = budget.memory_budget_bytes
        budget.memory_budget_bytes = baseline
        try:
            with self.assertRaises(BudgetExceededError):
                self.scan(data)
        finally:
            budget.memory_budget_bytes = limit
        self.assertFalse(adapter.handles)

    def test_csv_unreturned_read_and_bad_input_never_create_finished_scan(self):
        """自有CSV read未返回清理与实际坏时间均保持最高scan责任，不伪完成。参数: 无。返回: None。异常: 漏费或假事实。
        """
        data = self.fixture(kind='signal_csv')
        history, plan, adapter, request, budget = data
        baseline = budget.ram_bytes
        owner = self.scan(data)
        original = KeyboardInterrupt('observed-scan-own-csv-reserve')
        with patch.object(budget, 'reserve_ram', self.cancel_once(budget.reserve_ram, original, after=True)), \
             patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt('csv child persistent cleanup')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.consume()
        self.assertIs(caught.exception, original)
        self.assertIs(getattr(original, 'observed_source_scan_cleanup_owner', None), owner)
        self.assertIsNotNone(owner._read)
        self.assertFalse(owner.finished)
        owner.close()
        self.assertEqual(budget.ram_bytes, baseline)
        data = self.fixture(kind='signal_csv', bad_csv=True, size=1)
        owner = self.scan(data)
        with self.assertRaises(SourceReadError):
            owner.consume()
        self.assertTrue(owner.failed)
        self.assertFalse(owner.finished)
        with self.assertRaises(ResultClosedError):
            _ = owner.observation
        owner.close()
        self.assertFalse(data[2].handles)

    def test_runtime_failure_closes_only_owned_csv_fd_and_keeps_parallel_read_alive(self):
        """真实history append后取消，scan.close只关自有FD并保另一个活read。参数: 无。返回: None。异常: 关闭借用或漏FD。
        """
        data = self.fixture(kind='signal_csv', size=1)
        history, plan, adapter, request, budget = data
        external = adapter.iter_batches_with_observation(request)
        self.addCleanup(external.close)
        next(external)
        borrowed_handles = tuple(adapter.handles)
        owner = self.scan(data)
        original = KeyboardInterrupt('observed-scan-after-real-append')
        actual_append = history.append

        def append_then_cancel(batch):
            """先真实写入再取消。参数: 原batch。返回: 无。异常: 本例原取消。
            """
            actual_append(batch)
            raise original

        with patch.object(history, 'append', append_then_cancel):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.consume()
        self.assertIs(caught.exception, original)
        own_handles = tuple(handle for handle in adapter.handles if handle not in borrowed_handles)
        self.assertTrue(own_handles)
        owner.close()
        self.assertTrue(all(handle.closed for handle in own_handles))
        self.assertTrue(all(not handle.closed for handle in borrowed_handles))
        self.assertFalse(adapter.closed)
        self.assertFalse(history.closed)
        for batch in external:
            batch = None
        self.assertTrue(external.exhausted)
        external.close()

    def test_completed_snapshot_and_fixed_close_before_after_cancel_remain_separate(self):
        """完成快照与显式关闭分开，固定费前后取消可同owner重试。参数: 无。返回: None。异常: 重读、重复扣费或借用被关。
        """
        for after in (False, True):
            data = self.fixture(kind='signal_csv')
            history, plan, adapter, request, budget = data
            owner = self.scan(data)
            owner.consume()
            fixed = owner._fixed_cost
            baseline = budget.ram_bytes - fixed
            original = KeyboardInterrupt('observed-scan-close-fixed')
            with patch.object(budget, 'release_ram', self.cancel_once(budget.release_ram, original,
                    after=after, amount=fixed)):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    owner.close()
            self.assertIs(caught.exception, original)
            with self.assertRaises(ResultClosedError):
                _ = owner.observation
            owner.close()
            owner.close()
            self.assertTrue(owner.closed)
            self.assertEqual(budget.ram_bytes, baseline)
            self.assertFalse(adapter.closed)
            self.assertFalse(history.closed)
