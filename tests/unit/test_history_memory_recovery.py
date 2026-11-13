"""用真实内存批次核对构造、取消和持续关闭恢复。

每例建立三行有限SourceSpec、原ReadRequest及共享借用标记。
故障只围绕一次预算操作或透明生成器close注入，不替换数值、
格式或计费公式。持续失败至少三次后恢复同一owner，验证未返回资源可达、原异常
身份/原因保留、其他读取器仍可用、关闭不重读来源以及最终RAM回借用基线/0。
测试只写新项目work并保留文件；不运行旧CAN链、不改RefProjects。device_label: home。
"""

# 测试替身只控制真实资源边界，生产批次、编码、SHA和EOF均由原模块实际生成。
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow, SourceSpec, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import AnalysisError, ResultClosedError
from chronaxis.sources.memory import MemorySourceAdapter
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.protocol import SourceClosedError


class CloseBoundary:
    """透明包装真实FD或生成器，保留actual对象并只在close边界注入。"""

    def __init__(self, actual, error, *, after=False):
        """参数: actual真实资源；error原错误；after选择真实close后抛。返回: proxy。异常: 无。"""
        self.actual, self.error, self.after, self.fail = actual, error, after, True
        self.calls = 0

    @property
    def closed(self):
        """参数: 无。返回: 实际FD.closed。异常: 非FD不应查询此属性。"""
        return self.actual.closed

    def close(self):
        """参数: 无。返回: 原close值。异常: fail时原对象，释放前后由after决定。"""
        self.calls += 1
        if self.fail and not self.after:
            raise self.error
        result = self.actual.close()
        if self.fail:
            raise self.error
        return result

    def __next__(self):
        """参数: 无。返回: 原生成器next。异常: 原读取/EOF错误传播。"""
        return next(self.actual)

    def __getattr__(self, name):
        """参数: name原成员名。返回: actual成员。异常: 原属性错误传播。"""
        return getattr(self.actual, name)


class RegistrationFailure(set):
    """保留真实read set，只在add前或后抛原登记错误。"""

    def __init__(self, values, error, *, after):
        """参数: values原登记；error原错；after选择登记之后。返回: set。异常: 原set错误。"""
        super().__init__(values)
        self.error, self.after = error, after

    def add(self, value):
        """参数: value真实新read。返回: 无。异常: 原注册错误，不伪造read或账目。"""
        if self.after:
            super().add(value)
        raise self.error


class HistoryMemoryRecoveryTests(unittest.TestCase):
    """每例独立实际资源，借用标记只由测试最终释放，不得被生产误抵销。"""

    def fixture(self, *, budgeted=False, backend='reference'):
        """建立三行真实内存输入，并登记严格逆序清理。

        参数: budgeted选择预算来源；backend为真实归一化后端。返回: 有限fixture。异常: 原读取/构造错误传播。
        """
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/history-memory-recovery' / uuid4().hex
        work.mkdir(parents=True)
        budget = ResourceBudget(16*1024**2)
        budget.reserve_ram(8192)
        source = SourceSpec('table', TimebaseSpec('clock', TimeType.RELATIVE, 'recovery-home'),
            tuple(MemoryRow(time_ns=t, values={'raw': t+1}, sequence=i) for i, t in enumerate((0, 2, 4))))
        signals = (SignalDefinition('a', 'table', 'raw', D.FLOAT64, '1', 10),)
        adapter = (BudgetedMemorySourceAdapter(budget, source, 'session', signals, backend=backend)
            if budgeted else MemorySourceAdapter(source, 'session', signals, backend=backend))
        data = SimpleNamespace(work=work, budget=budget, source=source, signals=signals, adapter=adapter,
            request=ReadRequest('session', ('a',), 0, 4, 1), extra=[])
        self.addCleanup(self.cleanup_fixture, data)
        return data


    def cleanup_fixture(self, data):
        """在注入撤销后关实际owner，确认借用标记保留，再由测试释放。

        参数: data当前fixture。返回: None。异常: 任一关闭或账目残留令专项失败。
        """
        for owner in reversed(data.extra):
            owner.close()
        data.adapter.close()
        self.assertEqual(data.budget.ram_bytes, 8192)
        data.budget.release_ram(8192)
        self.assertEqual(data.budget.ram_bytes, 0)

    def fault(self, budget, method, error, *, after=False, match=None):
        """创建只围绕直接预算操作的前/后注入，未命中仍执行真实账本。

        参数: budget真实账本；method申请/释放方法；error原错；after真实变化后抛；
            match为可选金额谓词。返回: patch上下文。异常: 原预算或指定错误传播。
        """
        original = getattr(budget, method)
        def invoke(amount):
            """参数: amount原金额。返回: 原方法返回值。异常: 命中时指定原错。"""
            if match is not None and not match(amount):
                return original(amount)
            if after:
                original(amount)
            raise error
        return patch.object(budget, method, side_effect=invoke)

    def test_memory_read_close_before_after_release_preserves_parallel_read_and_marker(self):
        """read单次费用释放前后取消可重试，平行真实请求仍能耗尽且不重开来源。

        参数: 无。返回: None。异常: 重复扣账、误关平行read或原取消丢失断言失败。
        """
        for after in (False, True):
            for error_type in (KeyboardInterrupt, SystemExit, RuntimeError):
                with self.subTest(after=after, error_type=error_type):
                    data = self.fixture(budgeted=True)
                    first = data.adapter.iter_batches(data.request)
                    second = data.adapter.iter_batches(data.request)
                    next(first)
                    next(second)
                    baseline = data.budget.ram_bytes-first.cost
                    error = error_type('read-release-boundary')
                    with self.fault(data.budget, 'release_ram', error, after=after):
                        with self.assertRaises(error_type) as caught:
                            first.close()
                        self.assertIs(caught.exception, error)
                        if not after:
                            for _ in range(2):
                                with self.assertRaises(error_type):
                                    first.close()
                            self.assertFalse(first.closed)
                            self.assertGreater(first.cost, 0)
                        else:
                            self.assertEqual(first.cost, 0)
                    with patch.object(data.adapter._adapter, 'iter_batches', side_effect=AssertionError('close重读来源')):
                        first.close()
                        first.close()
                    self.assertTrue(first.closed)
                    self.assertFalse(data.adapter.closed)
                    self.assertEqual(data.budget.ram_bytes, baseline)
                    self.assertGreater(sum(batch.sample_count for batch in second), 0)
                    self.assertTrue(second.closed)

    def test_memory_real_generator_close_persistent_failure_retains_exact_read(self):
        """真实生成器关闭前三次持续取消，当前read保费保句柄，其他read仍独立。

        参数: 无。返回: None。异常: 丢原生成器、提前closed或跨请求影响断言失败。
        """
        data = self.fixture(budgeted=True)
        read = data.adapter.iter_batches(data.request)
        other = data.adapter.iter_batches(data.request)
        next(read)
        next(other)
        original, original_cost = read.iterator, read.cost
        error = KeyboardInterrupt('real-generator-close')
        proxy = CloseBoundary(original, error)
        read.iterator = proxy
        for _ in range(3):
            with self.assertRaises(KeyboardInterrupt) as caught:
                read.close()
            self.assertIs(caught.exception, error)
            self.assertIs(caught.exception.memory_read_cleanup_owner, read)
            self.assertFalse(read.closed)
            self.assertIs(read.iterator, proxy)
            self.assertEqual(read.cost, original_cost)
        proxy.fail = False
        read.close()
        self.assertIsNone(original.gi_frame)
        self.assertGreater(sum(batch.sample_count for batch in other), 0)

    def test_memory_source_close_persistent_release_before_after_keeps_owned_fee(self):
        """来源固定费释放前后取消不提前closed，恢复后同一source归还原申请。

        参数: 无。返回: None。异常: 自有金额重复抵销或恢复owner遗失断言失败。
        """
        for after in (False, True):
            data = self.fixture(budgeted=True)
            error = KeyboardInterrupt('source-release-boundary')
            with self.fault(data.budget, 'release_ram', error, after=after):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    data.adapter.close()
                self.assertIs(caught.exception.memory_source_cleanup_owner, data.adapter)
                if not after:
                    for _ in range(2):
                        with self.assertRaises(KeyboardInterrupt):
                            data.adapter.close()
                    self.assertGreater(data.adapter._input_cost, 0)
                else:
                    self.assertEqual(data.adapter._input_cost, 0)
            data.adapter.close()
            self.assertTrue(data.adapter.closed)
            self.assertEqual(data.budget.ram_bytes, 8192)

    def test_memory_source_constructor_reserve_after_keeps_unreturned_owner_and_original(self):
        """首次实际入账后取消且释放持续失败，原source构造owner可恢复而不猜费用。

        参数: 无。返回: None。异常: 原取消被清理盖掉、source丢失或漏账断言失败。
        """
        data = self.fixture()
        error, cleanup = KeyboardInterrupt('source-reserve-after'), RuntimeError('persistent-cleanup')
        with self.fault(data.budget, 'reserve_ram', error, after=True), self.fault(data.budget, 'release_ram', cleanup):
            with self.assertRaises(KeyboardInterrupt) as caught:
                BudgetedMemorySourceAdapter(data.budget, data.source, 'session', data.signals, backend='reference')
            self.assertIs(caught.exception, error)
            owner = caught.exception.memory_source_cleanup_owner
            data.extra.append(owner)
            with self.assertRaises(RuntimeError):
                owner.close()
            self.assertFalse(owner.closed)
            self.assertEqual(owner._input_cost, owner._held_cost)
        owner.close()
        self.assertEqual(data.budget.ram_bytes, 8192)

    def test_memory_unreturned_read_constructor_and_registration_keep_highest_actual_owner(self):
        """read构造或add前后失败时来源保未安装槽，原错及read恢复属性同时可达。

        参数: 无。返回: None。异常: 回调后费用遗失、覆盖原错或误关借用adapter断言失败。
        """
        for position in ('reserve', 'add-before', 'add-after'):
            with self.subTest(position=position):
                data = self.fixture(budgeted=True)
                baseline = data.budget.ram_bytes
                error = KeyboardInterrupt('request-reserve') if position == 'reserve' else MemoryError('register-original')
                cleanup = RuntimeError('request-persistent-release')
                if position != 'reserve':
                    data.adapter.active = RegistrationFailure(data.adapter.active, error, after=position == 'add-after')
                reserve = self.fault(data.budget, 'reserve_ram', error, after=True) if position == 'reserve' else patch.object(
                    data.budget, 'reserve_ram', wraps=data.budget.reserve_ram)
                with reserve, self.fault(data.budget, 'release_ram', cleanup):
                    with self.assertRaises(type(error)) as caught:
                        data.adapter.iter_batches(data.request)
                    self.assertIs(caught.exception, error)
                    read = caught.exception.memory_read_cleanup_owner
                    self.assertIs(data.adapter._uninstalled_read, read)
                    self.assertFalse(read.closed)
                    with self.assertRaises(RuntimeError):
                        read.close()
                read.close()
                self.assertTrue(read.closed)
                self.assertIsNone(data.adapter._uninstalled_read)
                self.assertFalse(data.adapter.closed)
                self.assertEqual(data.budget.ram_bytes, baseline)

    def test_memory_true_eof_release_failure_cannot_be_stop_iteration(self):
        """末EOF批已交付后的真实耗尽清理失败传播取消，不能被StopIteration吞掉。

        参数: 无。返回: None。异常: 伪正常EOF或原取消丢失断言失败。
        """
        data = self.fixture(budgeted=True)
        read = data.adapter.iter_batches(data.request)
        while not next(read).source_eof:
            pass
        error = KeyboardInterrupt('eof-release')
        with self.fault(data.budget, 'release_ram', error):
            with self.assertRaises(KeyboardInterrupt) as caught:
                next(read)
            self.assertIs(caught.exception, error)
            self.assertIs(caught.exception.memory_read_cleanup_owner, read)
        read.close()
        self.assertTrue(read.closed)
