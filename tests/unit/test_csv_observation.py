"""验证新CSV单次读取的首末原行事实、真实EOF闸门和独立资源责任。

输入为work/m2-run-tests/csv-observation中的唯一小CSV目录，时间使用整数纳秒，
同时覆盖参考和NumPy后端。新读取owner交付原SignalBatch；首末时间及行数来自
真实原时间行，不从投影样本、请求范围或watermark推断。正常完整耗尽后才读取
冻结CSVObservation；提前关闭、坏行、取消或清理失败不得形成完成事实。
所有预算和FD故障注入真实对象上的目标动作，原错误及最高恢复owner保持可达。
有限批次事实只用于小样例比较；不修改旧测试、RefProjects、schema或公共AnalysisRunner。
本专项及其独立证据来源为home，显式调用方8192字节标记最后归还，最终余额为0。
"""

# 旧测试模块只借独立事实函数，不导入其TestCase而重复发现既有专项。
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_budgeted_memory as memory_helpers
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.results import BudgetExceededError, ResultClosedError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest, SourceClosedError, SourceReadError
from chronaxis.sources.csv_spec import SignalCSVSpec


class CSVObservationTests(unittest.TestCase):
    """每个来源及read独立关闭，完成事实仅由对应真实read拥有到其close。"""

    def fixture(self, *, backend='numpy', size=2, names=('value',), offset=0,
                contents=('ns,v\n\n0,2\n2,\n', 'ns,v\n2,4\n8,0\n\n')):
        """建立真实CSV、预算和借用标记，不预扫描输入。

        参数: backend为reference/numpy；size为真实batch_rows；names为空表示空投影；
            offset为整数ns偏移；contents按给定顺序建立文件，默认四原行含同刻跨界及缺失。
        返回: adapter/request/budget/调用方标记与来源固定费用基线。
        异常: 原文件、模型、预算或最终清理错误直接令测试失败。
        """
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/csv-observation' / uuid4().hex
        work.mkdir(parents=True)
        paths = []
        for index, content in enumerate(contents):
            path = work / (str(index) + '.csv')
            path.write_text(content, encoding='utf-8', newline='')
            paths.append(path)
        spec = SignalCSVSpec('table', tuple(paths),
            TimebaseSpec('clock', TimeType.RELATIVE, 'csv-observation-home'), 'ns', 'ns', offset_ns=offset)
        signals = (SignalDefinition('value', 'table', 'v', D.FLOAT64, '1', 20),)
        budget = ResourceBudget(16 * 1024 ** 2)
        self.addCleanup(self.cleanup_zero, budget)
        budget.reserve_ram(8192)
        self.addCleanup(self.cleanup_marker, budget)
        adapter = BudgetedSignalCSVSourceAdapter(budget, spec, 'session', signals, backend=backend)
        self.addCleanup(adapter.close)
        request = ReadRequest('session', names, offset, offset + 10, size)
        return adapter, request, budget, budget.ram_bytes

    def cleanup_zero(self, budget):
        """最外层核对实际0。参数: 共享budget。返回: None。异常: 漏费或多扣断言失败。"""
        self.assertEqual(budget.ram_bytes, 0)

    def cleanup_marker(self, budget):
        """只归还调用方8192标记。参数: 共享budget。返回: None。异常: 自有/借用费用混淆。"""
        self.assertEqual(budget.ram_bytes, 8192)
        budget.release_ram(8192)

    def read(self, adapter, request):
        """建立并登记真实新读取owner。参数: 来源/原请求。返回: read。异常: 原构造错误。"""
        read = adapter.iter_batches_with_observation(request)
        self.addCleanup(read.close)
        return read

    def consume(self, read):
        """只物化有限批次事实。参数: 真实read。返回: 批次tuple。异常: 原读取错误或未终止。"""
        batches = []
        for _ in range(100):
            try:
                batches.append(next(read))
            except StopIteration:
                return tuple(batches)
        self.fail('有限CSV观测夹具超过100批仍未耗尽')

    def assert_observation(self, read, request, first, last, rows):
        """核冻结事实及真实读取身份。参数: read/原request/首末ns/原行数。返回: 事实。异常: 事实错误。"""
        from chronaxis.execution.csv_observation import CSVObservation
        observation = read.observation
        self.assertIsInstance(observation, CSVObservation)
        self.assertEqual((observation.source, observation.session_id), ('table', 'session'))
        self.assertIs(observation.request, request)
        self.assertEqual(observation.read_identity, read.identity)
        self.assertIsInstance(read.identity, str)
        self.assertTrue(read.identity)
        self.assertEqual((observation.first_ns, observation.last_ns, observation.row_count, observation.source_eof),
            (first, last, rows, True))
        self.assertIs(type(observation.row_count), int)
        self.assertIs(observation.source_eof, True)
        for value in (observation.first_ns, observation.last_ns):
            if value is not None:
                self.assertIs(type(value), int)
        self.assertTrue(read.exhausted)
        self.assertFalse(read.failed)
        self.assertFalse(read.closed)
        return observation

    def close_check(self, read, adapter, budget, baseline):
        """重复close只释放自有read。参数: read/来源/共享budget/借用基线。返回: None。异常: 所有权错误。"""
        read.close()
        read.close()
        self.assertTrue(read.closed)
        self.assertEqual(budget.ram_bytes, baseline)
        self.assertFalse(adapter.closed)
        self.assertFalse(adapter.handles)
        with self.assertRaises(ResultClosedError):
            _ = read.observation

    def cancel_once(self, actual, original, *, after=False, amount=None):
        """指定单笔真实预算前/后一次取消。参数: 原方法/原错/阶段/可选金额。返回: wrapper。异常: 原错。"""
        reached = []

        def invoke(value):
            """只在目标金额命中时取消。参数: bytes。返回: 原返回。异常: 指定原对象。"""
            if not reached and (amount is None or value == amount):
                reached.append(value)
                if after:
                    actual(value)
                raise original
            return actual(value)

        return invoke

    def test_real_multifile_batches_backends_sizes_match_old_path_and_keep_original_budget(self):
        """原批次事实及临时费用不变，额外费用仅属于新read。参数: 无。返回: None。异常: 批次/预算变化。"""
        import chronaxis.execution.csv_observation as module
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                with self.subTest(backend=backend, size=size):
                    adapter, request, budget, baseline = self.fixture(backend=backend, size=size)
                    expected, old_costs = [], []
                    # 旧入口不能实例化新采集owner，也不能为未启用的采集额外计费。
                    with patch.object(module, 'CSVObservationRead', side_effect=AssertionError('old path enabled observation')):
                        old = adapter.iter_batches(request)
                        self.addCleanup(old.close)
                        for batch in old:
                            expected.append(memory_helpers.batch_facts(batch))
                            old_costs.append(budget.ram_bytes - baseline - old.cost)
                    self.assertEqual(budget.ram_bytes, baseline)
                    read = self.read(adapter, request)
                    fixed = read._fixed_cost
                    actual, new_costs, samples = [], [], 0
                    for batch in read:
                        actual.append(memory_helpers.batch_facts(batch))
                        new_costs.append(budget.ram_bytes - baseline - fixed)
                        samples += batch.sample_count
                    self.assertEqual(actual, expected)
                    self.assertEqual(new_costs, old_costs)
                    self.assertEqual(samples, 4)
                    self.assert_observation(read, request, 0, 8, 4)
                    self.assertEqual(budget.ram_bytes, baseline + fixed)
                    self.close_check(read, adapter, budget, baseline)

    def test_empty_projection_missing_values_blank_rows_headers_and_offset_are_raw_time_facts(self):
        """首末及行数独立于投影与值有效性。参数: 无。返回: None。异常: 用样本/请求代替原时间行。"""
        cases = (((), 0, ('ns,v\n\n0,\n2,\n', 'ns,v\n2,\n8,\n\n'), (0, 8, 4)),
                 (('value',), 7, ('ns,v\n\n0,\n2,4\n', 'ns,v\n2,\n8,0\n'), (7, 15, 4)),
                 ((), 0, ('ns,v\n\n', 'ns,v\n'), (None, None, 0)))
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                for names, offset, contents, expected in cases:
                    with self.subTest(backend=backend, size=size, names=names, offset=offset, rows=expected[2]):
                        adapter, request, budget, baseline = self.fixture(backend=backend, size=size,
                            names=names, offset=offset, contents=contents)
                        read = self.read(adapter, request)
                        batches = self.consume(read)
                        self.assertEqual(sum(batch.sample_count for batch in batches), expected[2] if names else 0)
                        self.assertTrue(batches[-1].source_eof)
                        self.assertEqual(batches[-1].observed_end_ns, expected[1])
                        self.assert_observation(read, request, *expected)
                        self.close_check(read, adapter, budget, baseline)

    def test_two_reads_same_request_have_independent_identity_progress_and_immutable_facts(self):
        """同request并行读取不共享最后一次结果。参数: 无。返回: None。异常: 事实或进度串用。"""
        adapter, request, budget, baseline = self.fixture(size=1)
        first, second = self.read(adapter, request), self.read(adapter, request)
        self.assertNotEqual(first.identity, second.identity)
        next(first)
        self.consume(second)
        second_fact = self.assert_observation(second, request, 0, 8, 4)
        with self.assertRaises(ResultClosedError):
            _ = first.observation
        self.consume(first)
        first_fact = self.assert_observation(first, request, 0, 8, 4)
        self.assertNotEqual(first_fact.read_identity, second_fact.read_identity)
        self.assertIs(first.observation, first_fact)
        self.assertIs(second.observation, second_fact)
        with self.assertRaises(FrozenInstanceError):
            first_fact.row_count = 999
        first.close()
        self.assertIs(second.observation, second_fact)
        self.close_check(second, adapter, budget, baseline)

    def test_final_eof_batch_is_not_completed_observation_until_real_stopiteration(self):
        """最后batch已交付仍需真实耗尽和清理。参数: 无。返回: None。异常: EOF标志提前变完成证明。"""
        adapter, request, budget, baseline = self.fixture(size=1)
        read = self.read(adapter, request)
        with self.assertRaises(ResultClosedError):
            _ = read.observation
        while True:
            batch = next(read)
            with self.assertRaises(ResultClosedError):
                _ = read.observation
            if batch.source_eof:
                break
        self.assertFalse(read.exhausted)
        with self.assertRaises(StopIteration):
            next(read)
        self.assert_observation(read, request, 0, 8, 4)
        self.assertFalse(adapter.handles)
        self.close_check(read, adapter, budget, baseline)

    def test_early_close_adapter_abort_and_completed_fact_lifetime_are_independent(self):
        """提前中止不封事实，正常事实可越过adapter.close。参数: 无。返回: None。异常: 生命周期混淆。"""
        for started in (False, True):
            adapter, request, budget, baseline = self.fixture(size=1)
            read = self.read(adapter, request)
            if started:
                next(read)
                self.assertTrue(adapter.handles)
            self.close_check(read, adapter, budget, baseline)
            self.assertFalse(read.exhausted)
        adapter, request, budget, _ = self.fixture(size=1)
        read = self.read(adapter, request)
        next(read)
        adapter.close()
        with self.assertRaises((SourceClosedError, StopIteration, ResultClosedError)):
            next(read)
        with self.assertRaises(ResultClosedError):
            _ = read.observation
        read.close()
        self.assertFalse(read.exhausted)
        self.assertEqual(budget.ram_bytes, 8192)
        adapter, request, budget, _ = self.fixture()
        read = self.read(adapter, request)
        self.consume(read)
        observation = self.assert_observation(read, request, 0, 8, 4)
        fixed = read._fixed_cost
        adapter.close()
        self.assertIs(read.observation, observation)
        self.assertEqual(budget.ram_bytes, 8192 + fixed)
        read.close()
        self.assertEqual(budget.ram_bytes, 8192)
        with self.assertRaises(ResultClosedError):
            _ = read.observation

    def test_bad_rows_time_regression_and_empty_physical_file_never_seal_facts(self):
        """坏行和跨文件回退保原错误/位置，关闭实际FD。参数: 无。返回: None。异常: 坏输入被正常封存。"""
        for contents in (('ns,v\n0,1\n2,2\n', 'ns,v\n1,3\n'),
                         ('ns,v\n0,1\n', 'ns,v\n2,3,extra\n'),
                         ('ns,v\n0,1\n', ''), ('ns,v\n0,1\n', 'ns,v\nnot_time,3\n')):
            adapter, request, budget, baseline = self.fixture(size=1, contents=contents)
            read = self.read(adapter, request)
            with self.assertRaisesRegex(SourceReadError, 'signal_csv读取失败') as caught:
                self.consume(read)
            self.assertIsNotNone(caught.exception.__cause__)
            self.assertTrue(read.failed)
            self.assertFalse(read.exhausted)
            with self.assertRaises(ResultClosedError):
                _ = read.observation
            self.close_check(read, adapter, budget, baseline)

    def test_constructor_first_reserve_before_after_and_real_limit_precede_open(self):
        """真实首笔申请取消或超限不能打开来源。参数: 无。返回: None。异常: 计费/清理/原错不符。"""
        for after in (False, True):
            adapter, request, budget, baseline = self.fixture()
            original = KeyboardInterrupt('csv-observation-constructor-reserve')
            with patch.object(budget, 'reserve_ram', self.cancel_once(budget.reserve_ram, original, after=after)), \
                 patch.object(Path, 'open', side_effect=AssertionError('unpaid source open')) as opened:
                with self.assertRaises(KeyboardInterrupt) as caught:
                    self.read(adapter, request)
            opened.assert_not_called()
            self.assertIs(caught.exception, original)
            self.assertEqual(budget.ram_bytes, baseline)
        adapter, request, budget, baseline = self.fixture()
        old_limit = budget.memory_budget_bytes
        budget.memory_budget_bytes = baseline
        try:
            with patch.object(Path, 'open', side_effect=AssertionError('overbudget source open')) as opened:
                with self.assertRaises(BudgetExceededError):
                    self.read(adapter, request)
            opened.assert_not_called()
            self.assertEqual(budget.ram_bytes, baseline)
        finally:
            budget.memory_budget_bytes = old_limit

    def test_unreturned_constructor_persistent_cleanup_preserves_original_and_highest_owner(self):
        """构造首笔计费后错且持续清理取消，原异常提供最高owner。参数: 无。返回: None。异常: 盖错或漏费。"""
        adapter, request, budget, baseline = self.fixture()
        original = MemoryError('csv-observation-unreturned')
        with patch.object(budget, 'reserve_ram', self.cancel_once(budget.reserve_ram, original, after=True)), \
             patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt('persistent constructor cleanup')):
            with self.assertRaises(MemoryError) as caught:
                self.read(adapter, request)
        self.assertIs(caught.exception, original)
        recovered = getattr(original, 'csv_observation_read_cleanup_owner', None)
        self.assertIsNotNone(recovered)
        self.addCleanup(recovered.close)
        self.assertTrue(getattr(original, '__notes__', ()))
        self.close_check(recovered, adapter, budget, baseline)

    def test_actual_request_registration_failure_before_after_is_lazy_and_recoverable(self):
        """请求/原生成器/已计费检查器登记失败均可恢复。参数: 无。返回: None。异常: 泄漏或盖错。"""
        for category in ('_requests', 'active', '_resources'):
            for after in (False, True):
                adapter, request, budget, baseline = self.fixture()
                original = MemoryError('csv-observation-registration-' + category)

                class FailingSet(set):
                    """只在真实登记动作前后失败，不代替读取或预算实现。"""

                    def add(self, value):
                        """插入前后原错。参数: 实际登记对象。返回: 无。异常: 本例原MemoryError。"""
                        if after:
                            super().add(value)
                        raise original

                # 资源构造在首次next内发生；其余两类在尚未返回read的构造/登记内发生。
                read = self.read(adapter, request) if category == '_resources' else None
                previous = getattr(adapter, category)
                setattr(adapter, category, FailingSet(previous))
                try:
                    with patch.object(Path, 'open', side_effect=AssertionError('registration unexpectedly read')) as opened:
                        expected_error = SourceReadError if category == '_resources' else MemoryError
                        with self.assertRaises(expected_error) as caught:
                            if read is None:
                                self.read(adapter, request)
                            else:
                                next(read)
                    opened.assert_not_called()
                    # 构造登记在解析器外原样传播；运行期资源登记沿原CSV错误包装保cause。
                    if category == '_resources':
                        self.assertIs(caught.exception.__cause__, original)
                        self.assertIs(getattr(caught.exception, 'csv_observation_read_cleanup_owner', None), read)
                    else:
                        self.assertIs(caught.exception, original)
                    recovered = getattr(caught.exception, 'csv_observation_read_cleanup_owner', None)
                    if recovered is not None:
                        if read is not None:
                            self.assertIs(recovered, read)
                        recovered.close()
                    if read is not None:
                        read.close()
                    self.assertFalse(adapter._requests)
                    self.assertFalse(adapter.active)
                    self.assertFalse(adapter._resources)
                    self.assertEqual(budget.ram_bytes, baseline)
                finally:
                    setattr(adapter, category, previous)

    def test_real_open_fd_read_cancel_keeps_no_complete_fact_and_borrowed_cost(self):
        """真实文件已打开再取消下一读取，FD和费用均可恢复。参数: 无。返回: None。异常: 假EOF或漏FD。"""
        adapter, request, budget, baseline = self.fixture(size=1)
        read = self.read(adapter, request)
        next(read)
        handles = tuple(adapter.handles)
        self.assertTrue(handles)
        original = KeyboardInterrupt('csv-observation-active-read-cancel')
        # 下一原样本/批次申请仍走真实共享budget，取消不能变成成功的最终EOF。
        with patch.object(budget, 'reserve_ram', self.cancel_once(budget.reserve_ram, original)):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.consume(read)
        self.assertIs(caught.exception, original)
        self.assertTrue(read.failed)
        self.assertFalse(read.exhausted)
        with self.assertRaises(ResultClosedError):
            _ = read.observation
        self.close_check(read, adapter, budget, baseline)
        self.assertTrue(all(handle.closed for handle in handles))

    def test_close_release_before_after_is_retryable_and_does_not_seal_early_eof(self):
        """自有事实费释放取消可重试，最终batch未耗尽时close仍不封存。参数: 无。返回: None。异常: 多扣或假完成。"""
        for after in (False, True):
            adapter, request, budget, baseline = self.fixture(size=7)
            read = self.read(adapter, request)
            while not next(read).source_eof:
                pass
            original = KeyboardInterrupt('csv-observation-close-fixed')
            fixed = read._fixed_cost
            with patch.object(budget, 'release_ram', self.cancel_once(budget.release_ram, original, after=after, amount=fixed)):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    read.close()
            self.assertIs(caught.exception, original)
            self.assertFalse(read.exhausted)
            with self.assertRaises(ResultClosedError):
                _ = read.observation
            self.close_check(read, adapter, budget, baseline)

    def test_actual_resource_final_cleanup_cancel_never_makes_completed_observation(self):
        """真正耗尽时资源释放取消须拒完成事实并保最高恢复责任。参数: 无。返回: None。异常: 清理失败冒EOF。"""
        adapter, request, budget, baseline = self.fixture(size=7)
        read = self.read(adapter, request)
        while not next(read).source_eof:
            pass
        original = KeyboardInterrupt('csv-observation-eof-resource-release')
        reached = []
        actual_release = budget.release_ram

        def cancel_first_release(amount):
            """实际最终清理首笔前取消一次。参数: bytes。返回: 原返回。异常: 指定原取消。"""
            if not reached:
                reached.append(amount)
                raise original
            return actual_release(amount)

        with patch.object(budget, 'release_ram', cancel_first_release):
            with self.assertRaises(KeyboardInterrupt) as caught:
                next(read)
        self.assertTrue(reached)
        self.assertIs(caught.exception, original)
        self.assertFalse(read.exhausted)
        self.assertTrue(read.failed)
        with self.assertRaises(ResultClosedError):
            _ = read.observation
        recovered = getattr(original, 'csv_observation_read_cleanup_owner', None)
        # 瞬时取消可由正式清理立即收完；若仍有责任，原异常必须指向这个最高read。
        if not read.closed:
            self.assertIs(recovered, read)
        elif recovered is not None:
            self.assertIs(recovered, read)
        self.close_check(read, adapter, budget, baseline)

    def test_new_path_open_fd_persistent_release_before_after_recovers_without_fixing_default_path(self):
        """新可选链真实FD及持续释放取消可恢复，不声称默认旧链缺陷已修。

        参数: 无。返回: None。异常: 原取消身份改变、重试漏费、多扣或借用来源被关闭。
        边界: 只调用iter_batches_with_observation；BUG122的默认_CSVRequest/_CSVResources
            不参与此修复验收。前/后注入均在真实共享budget.release_ram执行位置发生。
        """
        for after in (False, True):
            adapter, request, budget, baseline = self.fixture(size=1)
            read = self.read(adapter, request)
            next(read)
            handles = tuple(adapter.handles)
            self.assertTrue(handles)
            original = KeyboardInterrupt('csv-observation-persistent-release-' + str(after))
            actual_release = budget.release_ram
            reached = []

            def cancel_every_release(amount):
                """每次真实释放前后均取消。参数: bytes。返回: 无。异常: 本例原KeyboardInterrupt。"""
                reached.append(amount)
                if after:
                    actual_release(amount)
                raise original

            with patch.object(budget, 'release_ram', cancel_every_release):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    read.close()
            self.assertTrue(reached)
            self.assertIs(caught.exception, original)
            self.assertFalse(read.exhausted)
            with self.assertRaises(ResultClosedError):
                _ = read.observation
            # 恢复真实释放方法后只靠同一最高read重试，不手工调整预算或关闭借用adapter。
            self.close_check(read, adapter, budget, baseline)
            self.assertTrue(all(handle.closed for handle in handles))

    def test_real_file_close_persistent_failure_retries_only_own_fd_and_preserves_parallel_read(self):
        """真实FD关闭前持续失败后只重试本read，平行read的真实FD保持可用。

        参数: 无。返回: None。异常: 原关闭错误被盖、遗失未关FD、误关平行read或漏费。
        流程: 仅给Path.open返回的真实TextIO加透明close故障包装；两read依次真实打开，
            本read关闭失败期间实际底层FD仍开。恢复close方法后只调用同一read.close，
            不遍历关闭adapter全部句柄、不手工关闭底层文件或修正预算。
        """
        adapter, request, budget, baseline = self.fixture(size=1)
        first, second = self.read(adapter, request), self.read(adapter, request)
        original = KeyboardInterrupt('csv-observation-persistent-file-close')
        actual_open = Path.open
        selected, reached = set(), []
        armed = False

        class ActualFile:
            """代理实际TextIO，仅在指定read的close执行前注入持续故障。"""

            def __init__(self, handle):
                """保留实际FD。参数: 已真实打开TextIO。返回: None。异常: 无预期异常。"""
                self.handle = handle

            def __getattr__(self, name):
                """委托原文本I/O属性。参数: 原属性名。返回: 原值。异常: 原AttributeError。"""
                return getattr(self.handle, name)

            def __iter__(self):
                """返回原文件迭代协议。参数: 无。返回: self。异常: 无。"""
                return self

            def __next__(self):
                """读取实际物理行。参数: 无。返回: str。异常: 原EOF/I/O错误。"""
                return next(self.handle)

            def close(self):
                """指定FD在真实close前持续失败。参数: 无。返回: 原返回。异常: 本例原取消。"""
                if armed and self in selected and not self.handle.closed:
                    reached.append(self)
                    raise original
                return self.handle.close()

        def open_actual(path, *args, **kwargs):
            """包装真实输入FD，不提供内存假文件。参数: 原open参数。返回: 透明包装。异常: 原I/O错误。"""
            return ActualFile(actual_open(path, *args, **kwargs))

        def disarm_cleanup():
            """断言失败时也恢复真实close。参数: 无。返回: None。异常: 无。"""
            nonlocal armed
            armed = False

        self.addCleanup(disarm_cleanup)
        with patch.object(Path, 'open', open_actual):
            next(first)
            selected.update(adapter.handles)
            self.assertTrue(selected)
            next(second)
            others = set(adapter.handles) - selected
            self.assertTrue(others)
            armed = True
            with self.assertRaises(KeyboardInterrupt) as caught:
                first.close()
            self.assertIs(caught.exception, original)
            self.assertTrue(reached)
            self.assertTrue(all(not handle.handle.closed for handle in selected))
            self.assertTrue(all(not handle.handle.closed for handle in others))
            with self.assertRaises(ResultClosedError):
                _ = first.observation
            armed = False
            first.close()
            first.close()
            self.assertTrue(first.closed)
            self.assertTrue(all(handle.handle.closed for handle in selected))
            self.assertTrue(all(not handle.handle.closed for handle in others))
            self.consume(second)
        self.assert_observation(second, request, 0, 8, 4)
        self.close_check(second, adapter, budget, baseline)
        self.assertTrue(all(handle.handle.closed for handle in others))

    def test_end_file_header_release_secondary_failure_preserves_real_parse_or_cancel_root(self):
        """真实每文件header释放双错保留原解析或取消根因，覆盖BUG124。

        参数: 无。返回: None。异常: 释放副错覆盖原根因、目标未命中、事实提前完成或漏费FD。
        流程: 坏时间由真实时间解析生成ValueError；取消在真实next已打开并取得原行后，
            从原_parse_value抛指定KeyboardInterrupt。清理副错只在当前实际检查器的
            end_file循环key为header时，于共享release_ram真实执行前/后各注入一次。
        """
        for kind in ('bad_time', 'cancel'):
            for after in (False, True):
                contents = ('ns,v\n' + ('bad,2\n' if kind == 'bad_time' else '0,2\n'),)
                adapter, request, budget, baseline = self.fixture(backend='reference', size=7, contents=contents)
                read = self.read(adapter, request)
                cancel = KeyboardInterrupt('csv-observation-original-next-cancel')
                cleanup = RuntimeError('csv-observation-different-header-cleanup')
                actual_release, actual_open = budget.release_ram, Path.open
                seen, handles = [], []

                def fail_real_header_release(amount):
                    """精确命中本检查器end_file/header。参数: bytes。返回: 原返回。异常: 指定副错。"""
                    frame = inspect.currentframe().f_back
                    target = False
                    try:
                        while frame is not None:
                            if (frame.f_code.co_name == 'end_file' and frame.f_locals.get('key') == 'header'
                                    and frame.f_locals.get('self') is read._resources):
                                target = True
                                break
                            frame = frame.f_back
                    finally:
                        # 不让测试堆栈引用延长实际reader、FD或异常的借期。
                        del frame
                    if target and not seen:
                        seen.append((sys.exception(), amount))
                        if after:
                            actual_release(amount)
                        raise cleanup
                    return actual_release(amount)

                def track_actual_open(path, *args, **kwargs):
                    """记录真正打开的TextIO。参数: 原open参数。返回: 原句柄。异常: 原I/O错误。"""
                    handle = actual_open(path, *args, **kwargs)
                    handles.append(handle)
                    return handle

                with patch.object(budget, 'release_ram', fail_real_header_release), \
                     patch.object(Path, 'open', track_actual_open):
                    if kind == 'cancel':
                        with patch.object(adapter, '_parse_value', side_effect=cancel):
                            with self.assertRaises(KeyboardInterrupt) as caught:
                                next(read)
                    else:
                        with self.assertRaises(SourceReadError) as caught:
                            next(read)
                self.assertEqual(len(seen), 1, '没有唯一命中本read的实际end_file/header释放')
                primary, amount = seen[0]
                self.assertGreater(amount, 0)
                actual = caught.exception
                if kind == 'bad_time':
                    self.assertIsInstance(primary, ValueError)
                    self.assertIs(actual.__cause__, primary)
                    self.assertIn('非法十进制时间文本', str(primary))
                else:
                    self.assertIs(primary, cancel)
                    self.assertIs(actual, cancel)
                # 包装错误可将清理说明放原cause；两者合看必须明确记录不同RuntimeError。
                notes = tuple(getattr(actual, '__notes__', ())) + tuple(getattr(primary, '__notes__', ()))
                self.assertTrue(any('RuntimeError' in note for note in notes))
                self.assertIs(getattr(actual, 'csv_observation_read_cleanup_owner', None), read)
                self.assertTrue(read.failed)
                self.assertFalse(read.exhausted)
                with self.assertRaises(ResultClosedError):
                    _ = read.observation
                self.assertTrue(handles)
                self.assertTrue(all(handle.closed for handle in handles))
                self.close_check(read, adapter, budget, baseline)
