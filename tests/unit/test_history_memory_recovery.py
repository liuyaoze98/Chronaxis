"""用真实内存批次和历史FD核BUG121的构造、取消和持续关闭恢复。

每例建立三行有限SourceSpec、原ReadRequest及共享借用标记；历史由真实来源逐批
写到EOF。故障只围绕一次预算操作或透明真实文件/生成器close注入，不替换数值、
格式或计费公式。持续失败至少三次后恢复同一owner，验证未返回资源可达、原异常
身份/原因保留、其他read/历史仍可用、关闭不重读来源以及最终RAM回借用基线/0。
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
from chronaxis.execution.history import DecodedHistoryStore
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

    def fixture(self, *, budgeted=False, history=False, sealed=False, backend='reference'):
        """建立三行真实memory及可选历史，并登记严格逆序清理。

        参数: budgeted选择预算来源；history建立building存储；sealed实际写到EOF；
            backend为真实归一化后端。返回: 有限fixture。异常: 原读取/构造错误传播。
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
            request=ReadRequest('session', ('a',), 0, 4, 1), history=None, extra=[])
        self.addCleanup(self.cleanup_fixture, data)
        if history or sealed:
            data.history = self.make_history(data, 'history', sealed=sealed)
        return data

    def make_history(self, data, name, *, sealed):
        """用原来源批次建立独立历史，不复制其他store的内存状态。

        参数: data真实fixture；name新目录；sealed是否读到实际EOF。返回: store。
        异常: 原构造/写入/EOF错误传播。
        """
        store = DecodedHistoryStore(data.budget, data.work/name, (data.adapter.describe(),), {'table': data.request})
        data.extra.append(store)
        if sealed:
            read = data.adapter.iter_batches(data.request)
            try:
                for batch in read:
                    store.append(batch)
            finally:
                read.close()
            store.seal()
        return store

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

    def test_history_parent_close_real_fd_persistent_before_and_after_is_retriable(self):
        """父历史只在真实FD及子费用全闭后closed，平行独立历史FD保持打开。

        参数: 无。返回: None。异常: 提前closed、FD丢失或误关其他store断言失败。
        """
        for after in (False, True):
            data = self.fixture(sealed=True)
            other = self.make_history(data, 'other-history', sealed=True)
            first, second = data.history.iter_records('table'), other.iter_records('table')
            next(first)
            next(second)
            error = KeyboardInterrupt('real-history-fd-close')
            proxy = CloseBoundary(first.handle, error, after=after)
            first.handle = proxy
            with self.assertRaises(KeyboardInterrupt) as caught:
                data.history.close()
            self.assertIs(caught.exception, error)
            self.assertIs(caught.exception.history_cleanup_owner, data.history)
            self.assertFalse(data.history.closed)
            if not after:
                for _ in range(2):
                    with self.assertRaises(KeyboardInterrupt):
                        data.history.close()
                self.assertFalse(proxy.closed)
                self.assertGreater(first.cost, 0)
            self.assertFalse(second.handle.closed)
            self.assertFalse(other.closed)
            proxy.fail = False
            with patch.object(data.history, 'iter_records', side_effect=AssertionError('close重开历史')):
                data.history.close()
            self.assertTrue(data.history.closed)
            self.assertTrue(proxy.closed)
            self.assertTrue(first.closed)
            self.assertTrue(second.handle.readable())
            self.assertGreater(len(tuple(second)), 0)

    def test_history_close_own_release_before_after_preserves_borrowed_marker(self):
        """history固定费释放前后取消按实际槽恢复，closed不抢在释放之前成立。

        参数: 无。返回: None。异常: 释放重做或抵销借用标记断言失败。
        """
        for after in (False, True):
            data = self.fixture(history=True)
            error = SystemExit('history-release')
            with self.fault(data.budget, 'release_ram', error, after=after):
                with self.assertRaises(SystemExit) as caught:
                    data.history.close()
                self.assertIs(caught.exception.history_cleanup_owner, data.history)
                if not after:
                    for _ in range(2):
                        with self.assertRaises(SystemExit):
                            data.history.close()
                    self.assertGreater(data.history._state_cost, 0)
                else:
                    self.assertEqual(data.history._state_cost, 0)
            data.history.close()
            self.assertTrue(data.history.closed)
            self.assertEqual(data.budget.ram_bytes, 8192)

    def test_history_constructor_reserve_after_and_mkdir_original_survive_persistent_cleanup(self):
        """入账后取消与实际mkdir失败均保原错和真实未返回history，不重复state抵销。

        参数: 无。返回: None。异常: 盖根因、费用无owner或恢复写入旧目录断言失败。
        """
        for position in ('reserve', 'mkdir'):
            data = self.fixture()
            path = data.work/'unreturned-history'
            error = KeyboardInterrupt('history-reserve-after') if position == 'reserve' else OSError('mkdir-original')
            cleanup = RuntimeError('history-constructor-cleanup')
            reserve = self.fault(data.budget, 'reserve_ram', error, after=True) if position == 'reserve' else patch.object(
                Path, 'mkdir', side_effect=error)
            with reserve, self.fault(data.budget, 'release_ram', cleanup):
                with self.assertRaises(type(error)) as caught:
                    DecodedHistoryStore(data.budget, path, (data.adapter.describe(),), {'table': data.request})
                self.assertIs(caught.exception, error)
                owner = caught.exception.history_cleanup_owner
                data.extra.append(owner)
                self.assertFalse(owner.closed)
                self.assertGreater(owner._state_cost, 0)
                with self.assertRaises(RuntimeError):
                    owner.close()
            owner.close()
            self.assertEqual(data.budget.ram_bytes, 8192)
            self.assertFalse(path.exists())

    def test_history_existing_directory_never_written_or_charged(self):
        """已有目录拒绝时保原文件且无失败诊断，不把目录当本次资源。

        参数: 无。返回: None。异常: 旧目录改写、错误包装或金额改变断言失败。
        """
        data = self.fixture()
        path = data.work/'existing'
        path.mkdir()
        marker = path/'user.txt'
        marker.write_text('keep', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            DecodedHistoryStore(data.budget, path, (data.adapter.describe(),), {'table': data.request})
        self.assertEqual(tuple(path.iterdir()), (marker,))
        self.assertEqual(marker.read_text(encoding='utf-8'), 'keep')
        self.assertEqual(data.budget.ram_bytes, 8192)

    def test_history_append_and_record_reserve_after_cancellation_recover_all_owned_slots(self):
        """真实首batch的临时lease或首行编码申请返回后取消，不遗失自有费用。

        参数: 无。返回: None。异常: 伪写成功、根因替换或append/record残账断言失败。
        """
        for target in (1, 2):
            data = self.fixture(history=True)
            read = data.adapter.iter_batches(data.request)
            batch = next(read)
            original = data.budget.reserve_ram
            calls = [0]
            error = KeyboardInterrupt('append-owned-reserve-after')
            def reserve(amount):
                """参数: amount实际申请。返回: 原结果。异常: 目标笔真实入账后原取消。"""
                value = original(amount)
                calls[0] += 1
                if calls[0] == target:
                    raise error
                return value
            with patch.object(data.budget, 'reserve_ram', side_effect=reserve):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    data.history.append(batch)
            self.assertIs(caught.exception, error)
            data.history.close()
            read.close()
            self.assertEqual(data.history._held_cost, 0)
            self.assertEqual(data.budget.ram_bytes, 8192)
            self.assertEqual(data.history.state, 'cancelled')
            self.assertTrue((data.history.work_dir/'failure.txt').exists())

    def test_history_append_release_and_failure_diagnostic_never_cover_original_error(self):
        """实际写入OSError遇诊断申请/释放取消仍保cause，所有单行和临时费可恢复。

        参数: 无。返回: None。异常: 清理盖根因或diagnostic费用遗失断言失败。
        """
        for method, after in (('reserve_ram', True), ('release_ram', False), ('release_ram', True)):
            data = self.fixture(history=True)
            read = data.adapter.iter_batches(data.request)
            batch = next(read)
            error, cleanup = OSError('actual-history-write-original'), KeyboardInterrupt('diagnostic-budget')
            with patch.object(data.history, '_write_bytes', side_effect=error), self.fault(data.budget,
                    method, cleanup, after=after, match=lambda amount: amount == 8192):
                with self.assertRaises(AnalysisError) as caught:
                    data.history.append(batch)
                self.assertIs(caught.exception.__cause__, error)
            data.history.close()
            read.close()
            self.assertEqual(data.budget.ram_bytes, 8192)
            self.assertEqual(data.history._held_cost, 0)

    def test_history_closing_rejects_new_and_existing_read_until_recovery(self):
        """父关闭未完时不允许继续已有read或新建reader，恢复只做close不重放。

        参数: 无。返回: None。异常: 半关闭还能读取或新建游标断言失败。
        """
        data = self.fixture(sealed=True)
        reader = data.history.iter_records('table')
        next(reader)
        proxy = CloseBoundary(reader.handle, KeyboardInterrupt('hold-history-closing'))
        reader.handle = proxy
        with self.assertRaises(KeyboardInterrupt):
            data.history.close()
        with self.assertRaises(ResultClosedError):
            next(reader)
        with self.assertRaises(ResultClosedError):
            data.history.iter_records('table')
        proxy.fail = False
        data.history.close()
        self.assertTrue(reader.closed and reader.handle.closed)

    def test_history_write_and_diagnostic_real_fds_keep_main_error_until_parent_recovery(self):
        """数据/诊断真实FD持续close前取消不盖普通或取消主错，最高父能恢复全部费用。

        参数: 无。返回: None。异常: 局部with丢FD、提前closed、盖主错或借用标记改变断言失败。
        """
        for slot in ('_write_handle', '_diagnostic_handle'):
            for primary in (OSError('write-main-original'), KeyboardInterrupt('write-main-cancel')):
                with self.subTest(slot=slot, primary=type(primary).__name__):
                    data = self.fixture(history=True)
                    read = data.adapter.iter_batches(data.request)
                    batch = next(read)
                    original_open, original_write = Path.open, data.history._write_bytes
                    target = data.history.paths['table'] if slot == '_write_handle' else data.history.work_dir/'failure.txt'
                    cleanup = KeyboardInterrupt('persistent-real-writer-close')
                    handles, calls = [], [0]
                    def opened(path, *args, **kwargs):
                        """参数: path原Path/打开参数。返回: 原FD或透明proxy。异常: 原打开错误。"""
                        handle = original_open(path, *args, **kwargs)
                        if path == target:
                            proxy = CloseBoundary(handle, cleanup)
                            handles.append(proxy)
                            return proxy
                        return handle
                    def write(handle, payload):
                        """参数: 原FD/bytes。返回: 第二笔后原写入。异常: 首笔原普通或取消主错。"""
                        calls[0] += 1
                        if calls[0] == 1:
                            raise primary
                        return original_write(handle, payload)
                    with patch.object(Path, 'open', autospec=True, side_effect=opened), patch.object(
                            data.history, '_write_bytes', side_effect=write):
                        expected = AnalysisError if isinstance(primary, OSError) else KeyboardInterrupt
                        with self.assertRaises(expected) as caught:
                            data.history.append(batch)
                        if isinstance(primary, OSError):
                            self.assertIs(caught.exception.__cause__, primary)
                        else:
                            self.assertIs(caught.exception, primary)
                        self.assertIs(caught.exception.history_cleanup_owner, data.history)
                        self.assertEqual(len(handles), 1)
                        handle = handles[0]
                        self.assertIs(getattr(data.history, slot), handle)
                        self.assertFalse(handle.actual.closed)
                        self.assertFalse(data.history.closed)
                        if slot == '_diagnostic_handle':
                            self.assertEqual(data.history._diagnostic_cost, 8192)
                        for _ in range(3):
                            with self.assertRaises(KeyboardInterrupt) as retry:
                                data.history.close()
                            self.assertIs(retry.exception, cleanup)
                            self.assertFalse(handle.actual.closed)
                    handle.fail = False
                    data.history.close()
                    read.close()
                    self.assertTrue(handle.actual.closed and data.history.closed)
                    self.assertIsNone(getattr(data.history, slot))
                    self.assertEqual(data.history._held_cost, 0)
                    self.assertEqual(data.budget.ram_bytes, 8192)

    def test_normal_memory_and_history_keep_original_batches_and_total_costs(self):
        """两后端正常路径保原批次值/进度和历史实际EOF，关闭不改变借用标记。

        参数: 无。返回: None。异常: 归一化、批次或费用公式被修复改变断言失败。
        """
        for backend in ('reference', 'numpy'):
            data = self.fixture(budgeted=True, backend=backend)
            source_cost = data.adapter._input_cost
            read = data.adapter.iter_batches(data.request)
            expected_request_cost = data.adapter._request_cost(data.request)
            self.assertEqual(read.cost, expected_request_cost)
            self.assertEqual(data.budget.ram_bytes, 8192+source_cost+read.cost)
            batches = tuple(read)
            self.assertEqual(tuple(batch.sample_count for batch in batches), (1, 1, 1))
            self.assertEqual(tuple(batch.source_eof for batch in batches), (False, False, True))
            self.assertEqual(tuple(column.values[0].item() for batch in batches for column in batch.series.values()), (1., 3., 5.))
            store = DecodedHistoryStore(data.budget, data.work/'normal-history', (data.adapter.describe(),), {'table': data.request})
            data.extra.append(store)
            for batch in batches:
                store.append(batch)
            store.seal()
            reader = store.iter_records('table')
            self.assertEqual(len(tuple(reader)), 6)
            self.assertTrue(reader.verified_eof and reader.handle.closed)
            store.close()
            self.assertEqual(data.budget.ram_bytes, 8192+source_cost)
