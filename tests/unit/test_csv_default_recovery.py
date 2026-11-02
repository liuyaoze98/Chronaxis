"""用真实默认预算CSV验证取消和清理失败后费用、文件及最高恢复责任。

输入由work现场合成，不调用可选观测入口冒充默认请求；正常输出另与原非预算
CSV入口比较。默认请求实际打开文件和检查器后，在预算reserve/release动作前后
或集合登记/真实FD关闭处注入有限故障，断言原cause和取消身份不被清理错误取代。
尚未完成的资源必须保留准确自有槽，恢复后回到借用基线并最终零余额；
不以共享余额差额补账，不人工构造半初始化owner，不修改解析、批次和数值预期。
全部原输入及失败证据保留在新项目work，device_label: home。
"""

# 标准库故障替身只控制单个真实动作，不替生产层关闭或抵销任何资源。
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
import unittest
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter, _CSVResources
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.csv_spec import SignalCSVSpec
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.protocol import SourceClosedError, SourceReadError
from chronaxis.sources.signal_csv import SignalCSVSourceAdapter
from test_budgeted_memory import batch_facts


class RejectRegistration(set):
    """在真实对象加入集合前或后失败，discard仍按原集合实现用于实际恢复。"""

    def __init__(self, after):
        """保存唯一故障位置。参数: after是否先实际加入。返回: 新集合。异常: 原set构造错。"""
        super().__init__()
        self.after = after

    def add(self, value):
        """只替登记动作抛错，不替被测层关闭对象。

        参数: value真实请求、检查器或FD。返回: 无。异常: 注入MemoryError。
        """
        if self.after:
            super().add(value)
        raise MemoryError('default-csv-registration')


class ControlledFile:
    """转交真实TextIO，故障仅发生于本FD关闭，不影响其余请求。"""

    def __init__(self, handle, *, after=False, error=None):
        """接住已真实打开的文件。参数: handle原FD；after关闭后故障；error指定原错。

        返回: 文件代理。异常: 无预期异常。
        """
        self.handle, self.after = handle, after
        self.error = OSError('default-csv-fd-close') if error is None else error
        self.armed, self.calls = False, 0

    @property
    def closed(self):
        """读取原FD状态。参数: 无。返回: bool。异常: 无。"""
        return self.handle.closed

    def __getattr__(self, name):
        """转交原读取协议。参数: name属性名。返回: 原值。异常: 原属性错误传播。"""
        return getattr(self.handle, name)

    def close(self):
        """在真实close前后按开关注入同一错误。

        参数: 无。返回: 原close值。异常: armed时指定原错，否则原FD错误。
        """
        if self.armed and not self.handle.closed:
            self.calls += 1
            if self.after:
                self.handle.close()
            raise self.error
        return self.handle.close()


class CSVDefaultRecoveryTests(unittest.TestCase):
    """每例保有8192字节借用标记，生产层只能归还自己的真实费用。"""

    def fixture(self, *, backend='numpy', size=2, contents='ns,v\n1,2\n', construct=True):
        """建立真实文件、原声明与共享预算，按需创建默认预算来源。

        参数: backend独立版本；size原batch_rows；contents真实CSV文本；construct是否构造adapter。
        返回: 含spec/signals/budget/request/adapter的夹具。异常: 原文件或模型错误。
        """
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/csv-default-recovery' / uuid4().hex
        work.mkdir(parents=True)
        path = work / 'input.csv'
        path.write_text(contents, encoding='utf-8', newline='')
        budget = ResourceBudget(16 * 1024 ** 2)
        self.addCleanup(self.assert_zero, budget)
        budget.reserve_ram(8192)
        self.addCleanup(budget.release_ram, 8192)
        spec = SignalCSVSpec('table', (path,), TimebaseSpec('clock', TimeType.RELATIVE,
            'csv-default-recovery-home'), 'ns', 'ns')
        signals = (SignalDefinition('value', 'table', 'v', SignalDType.FLOAT64, '1', 20),)
        adapter = BudgetedSignalCSVSourceAdapter(budget, spec, 'session', signals, backend=backend) if construct else None
        if adapter is not None:
            self.addCleanup(adapter.close)
        return SimpleNamespace(work=work, path=path, budget=budget, spec=spec, signals=signals,
            request=ReadRequest('session', ('value',), 0, 10, size), adapter=adapter)

    def assert_zero(self, budget):
        """最后核全部费用已真正抵销。参数: budget共享账本。返回: None。异常: 非零断言失败。"""
        self.assertEqual(budget.ram_bytes, 0)

    def request(self, data):
        """只从默认iter_batches创建实际请求并登记清理。

        参数: data真实夹具。返回: 实际默认请求。异常: 原创建错误传播。
        """
        owner = data.adapter.iter_batches(data.request)
        self.addCleanup(owner.close)
        return owner

    def cancel(self, actual, error, *, after=False, amount=None, limit=None):
        """对目标真实预算动作前后注入有限或持续同一原错误。

        参数: actual原方法；error指定原错；after是否先执行；amount可限制字节；limit次数上限。
        返回: (callback,calls)，calls只记录实际注入。异常: 目标调用抛指定错误。
        """
        calls = []

        def invoke(value):
            """只修改故障时机，不自行补账。

            参数: value原bytes。返回: 未触发时原返回值。异常: 指定原错或原方法错误。
            """
            if (amount is None or value == amount) and (limit is None or len(calls) < limit):
                calls.append(value)
                if after:
                    actual(value)
                raise error
            return actual(value)

        return invoke, calls

    def open_proxy(self, data, files, *, after=False, error=None):
        """仅包装本例真实CSV的只读open，其他文件完全转交原入口。

        参数: data夹具；files保存实际代理；after/error为关闭故障设置。
        返回: Path.open回调。异常: 原open错误，不伪造未打开FD。
        """
        actual = Path.open

        def invoke(path, *args, **kwargs):
            """保存真正打开的文件再交给生产层。

            参数: path及原open参数。返回: 真文件或本例代理。异常: 原打开错误。
            """
            handle = actual(path, *args, **kwargs)
            mode = args[0] if args else kwargs.get('mode', 'r')
            if path.resolve() == data.path.resolve() and mode == 'r':
                proxy = ControlledFile(handle, after=after, error=error)
                files.append(proxy)
                return proxy
            return handle

        return invoke

    def test_normal_default_matches_original_and_keeps_actual_costs(self):
        """原解析与批次事实不变，默认自有费用等于请求槽和资源槽，关闭回借用基线。

        参数: 无。返回: None。异常: 读取顺序、数值、费用或FD责任变化断言失败。
        """
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7, 65536):
                data = self.fixture(backend=backend, size=size, contents='ns,v,note\n1,2,"one\ntwo"\n1,4,x\n3,,x\n')
                baseline = data.budget.ram_bytes
                original = SignalCSVSourceAdapter(data.spec, 'session', data.signals, backend=backend)
                self.addCleanup(original.close)
                expected = tuple(batch_facts(batch) for batch in original.iter_batches(data.request))
                owner = self.request(data)
                self.assertEqual(owner.cost, 20480)
                self.assertEqual(tuple(batch_facts(batch) for batch in owner), expected)
                self.assertTrue(owner.closed)
                self.assertEqual(data.budget.ram_bytes, baseline)
                self.assertFalse(data.adapter.active)
                self.assertFalse(data.adapter.handles)
                self.assertFalse(data.adapter._resources)
                data.adapter.close()
                self.assertEqual(data.budget.ram_bytes, 8192)

    def test_eof_release_before_after_cancel_three_failures_then_recovery(self):
        """原181120残留位置的释放前后各连续取消三次，真实付款槽仍可完整恢复。

        参数: 无。返回: None。异常: 提前closed、丢槽、多扣借用金额或原KI被替换断言失败。
        """
        for after in (False, True):
            data = self.fixture()
            baseline = data.budget.ram_bytes
            owner = self.request(data)
            self.assertTrue(next(owner).source_eof)
            resources = owner._resources
            self.assertEqual(data.budget.ram_bytes - baseline, owner.cost + resources._held_cost)
            error = KeyboardInterrupt('default-csv-eof-three')
            release, calls = self.cancel(data.budget.release_ram, error, after=after, limit=3)
            with patch.object(data.budget, 'release_ram', side_effect=release):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    next(owner)
            self.assertIs(caught.exception, error)
            self.assertEqual(len(calls), 3)
            self.assertIs(getattr(error, 'csv_request_cleanup_owner', None), owner)
            self.assertFalse(owner.closed)
            self.assertEqual(data.budget.ram_bytes - baseline, owner.cost + resources._held_cost)
            owner.close()
            owner.close()
            self.assertEqual(data.budget.ram_bytes, baseline)
            self.assertTrue(resources.closed)
            self.assertFalse(data.adapter.closed)

    def test_source_fixed_release_before_after_cancel_never_loses_ownership(self):
        """来源自身固定费用释放前后取消，closed与付款槽以实际动作结果为准。

        参数: 无。返回: None。异常: 来源错误关闭或重复抵销借用余额断言失败。
        """
        for after in (False, True):
            data = self.fixture()
            original_cost = data.adapter._input_cost
            error = KeyboardInterrupt('default-csv-source-fixed')
            release, _ = self.cancel(data.budget.release_ram, error, after=after, amount=original_cost, limit=1)
            with patch.object(data.budget, 'release_ram', side_effect=release):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    data.adapter.close()
            self.assertIs(caught.exception, error)
            self.assertEqual(data.adapter.closed, after)
            self.assertEqual(data.adapter._input_cost, 0 if after else original_cost)
            data.adapter.close()
            data.adapter.close()
            self.assertEqual(data.budget.ram_bytes, 8192)

    def test_true_eof_request_fixed_close_error_is_not_hidden_by_stop_iteration(self):
        """仅请求20480字节关闭失败不伪报正常EOF，取消和普通错误均按原身份传播。

        参数: 无。返回: None。异常: StopIteration吞掉关闭原错、付款槽错误或恢复后余额错断言失败。
        """
        for error_type in (KeyboardInterrupt, SystemExit, OSError):
            for after in (False, True):
                data = self.fixture()
                baseline = data.budget.ram_bytes
                owner = self.request(data)
                self.assertTrue(next(owner).source_eof)
                error = error_type('default-csv-eof-request-fixed')
                release, reached = self.cancel(data.budget.release_ram, error, after=after, amount=20480)
                with patch.object(data.budget, 'release_ram', side_effect=release):
                    with self.assertRaises(error_type) as caught:
                        next(owner)
                self.assertIs(caught.exception, error)
                self.assertEqual(reached, [20480])
                self.assertEqual(owner.closed, after)
                self.assertEqual(owner.cost, 0 if after else 20480)
                if not after:
                    self.assertIs(getattr(error, 'csv_request_cleanup_owner', None), owner)
                owner.close()
                owner.close()
                self.assertEqual(data.budget.ram_bytes, baseline)
                self.assertFalse(data.adapter.handles)
                self.assertFalse(data.adapter._resources)
                # 原正常已关闭EOF仍为StopIteration，不能为修取消把每次耗尽都改成异常失败。
                with self.assertRaises(StopIteration):
                    next(owner)

    def test_live_fd_close_failures_remain_reachable_without_closing_other_request(self):
        """一个实际FD持续失败不清其资源槽，也不关闭另一个独立默认请求。

        参数: 无。返回: None。异常: 真实FD丢失、其他请求误关或恢复费用错误断言失败。
        """
        data = self.fixture(size=1, contents='ns,v\n1,2\n3,4\n5,6\n')
        first, second = self.request(data), self.request(data)
        files = []
        with patch.object(Path, 'open', autospec=True, side_effect=self.open_proxy(data, files)):
            next(first)
            next(second)
        self.assertEqual(len(files), 2)
        owned = first._handle
        other = second._handle
        owned.armed = True
        for _ in range(3):
            with self.assertRaises((SourceReadError, OSError)) as caught:
                first.close()
            # 生成器内首次关闭错误按原入口加来源包装，后续直接FD重试保原OSError。
            self.assertIs(caught.exception.__cause__ if isinstance(caught.exception, SourceReadError)
                else caught.exception, owned.error)
            self.assertFalse(first.closed)
            self.assertFalse(owned.closed)
            self.assertIs(first._handle, owned)
            self.assertFalse(other.closed)
        owned.armed = False
        first.close()
        self.assertTrue(owned.closed)
        self.assertFalse(other.closed)
        second.close()
        self.assertTrue(other.closed)
        self.assertFalse(data.adapter.handles)
        self.assertEqual(data.budget.ram_bytes, 8192 + data.adapter._input_cost)

    def test_fd_close_after_cancel_reports_original_but_finalizes_actual_closed_state(self):
        """真实FD已关才取消时仍报告同一KI，不留下假活动句柄或可重复扣费用。

        参数: 无。返回: None。异常: KI被替换、重复释放或真实FD未关闭断言失败。
        """
        data = self.fixture(size=1, contents='ns,v\n1,2\n3,4\n')
        owner, files = self.request(data), []
        error = KeyboardInterrupt('default-csv-fd-after')
        with patch.object(Path, 'open', autospec=True, side_effect=self.open_proxy(data, files, after=True, error=error)):
            next(owner)
        files[0].armed = True
        with self.assertRaises(KeyboardInterrupt) as caught:
            owner.close()
        self.assertIs(caught.exception, error)
        self.assertTrue(files[0].closed)
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(data.budget.ram_bytes, 8192 + data.adapter._input_cost)

    def test_business_parse_cause_survives_persistent_fd_cleanup_error(self):
        """原值语法错误与关闭错误同时发生，SourceReadError的cause仍为原解析错误。

        参数: 无。返回: None。异常: 清理错误掩盖原cause、失去FD或恢复错误断言失败。
        """
        data = self.fixture(contents='ns,v\n1,broken\n')
        owner, files = self.request(data), []
        opened = self.open_proxy(data, files)

        def arm_open(path, *args, **kwargs):
            """真正打开后立即武装该FD关闭失败。参数: 原open参数。返回: 真代理。异常: 原open错误。"""
            handle = opened(path, *args, **kwargs)
            if isinstance(handle, ControlledFile):
                handle.armed = True
            return handle

        with patch.object(Path, 'open', autospec=True, side_effect=arm_open):
            with self.assertRaises(SourceReadError) as caught:
                next(owner)
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertIn('非法数值文本', str(caught.exception.__cause__))
        self.assertIs(getattr(caught.exception, 'csv_request_cleanup_owner', None), owner)
        self.assertFalse(files[0].closed)
        files[0].armed = False
        owner.close()
        self.assertTrue(files[0].closed)
        self.assertEqual(data.budget.ram_bytes, 8192 + data.adapter._input_cost)

    def test_unreturned_adapter_after_reserve_cancel_has_real_source_owner(self):
        """来源固定预约成功后取消且清理持续失败，未返回实际来源通过最高属性恢复。

        参数: 无。返回: None。异常: owner丢失、假半初始化对象或借用费用被抵销断言失败。
        """
        data = self.fixture(construct=False)
        error = KeyboardInterrupt('default-csv-unreturned-source')
        reserve, _ = self.cancel(data.budget.reserve_ram, error, after=True, limit=1)
        with patch.object(data.budget, 'reserve_ram', side_effect=reserve):
            with patch.object(data.budget, 'release_ram', side_effect=KeyboardInterrupt('source-cleanup-three')):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    BudgetedSignalCSVSourceAdapter(data.budget, data.spec, 'session', data.signals)
        self.assertIs(caught.exception, error)
        recovery = getattr(error, 'csv_source_cleanup_owner', None)
        self.assertIsNotNone(recovery)
        self.assertFalse(recovery.closed)
        self.assertEqual(data.budget.ram_bytes, 8192 + recovery._input_cost)
        recovery.close()
        recovery.close()
        self.assertEqual(data.budget.ram_bytes, 8192)

    def test_original_adapter_constructor_error_keeps_identity_and_fixed_balance(self):
        """原来源构造已建立字段后失败，预算包装不替换原错也不遗失固定费。

        参数: 无。返回: None。异常: 构造原错被清理掩盖或余额残留断言失败。
        """
        data = self.fixture(construct=False)
        actual = SignalCSVSourceAdapter.__init__
        error = MemoryError('default-csv-original-constructor')

        def fail_initialized(owner, *args, **kwargs):
            """先调用真实来源构造，再注入同一原错。

            参数: owner及原构造参数。返回: 无。异常: 指定MemoryError或原构造错误。
            """
            actual(owner, *args, **kwargs)
            raise error

        with patch.object(SignalCSVSourceAdapter, '__init__', autospec=True, side_effect=fail_initialized):
            with self.assertRaises(MemoryError) as caught:
                BudgetedSignalCSVSourceAdapter(data.budget, data.spec, 'session', data.signals)
        self.assertIs(caught.exception, error)
        self.assertEqual(data.budget.ram_bytes, 8192)

    def test_physical_line_release_before_after_cancel_preserves_actual_accounting(self):
        """原物理行临时大额归还前后取消，释放的金额按真实动作登记，重试不多扣。

        参数: 无。返回: None。异常: 行预算丢槽、重复抵销或KI身份改变断言失败。
        """
        for after in (False, True):
            data = self.fixture()
            baseline = data.budget.ram_bytes
            owner = self.request(data)
            actual_release, reached = data.budget.release_ram, []
            error = KeyboardInterrupt('default-csv-physical-release')

            def cancel_large(amount):
                """只在原物理行读完首次归还大额余量时取消。

                参数: amount真实bytes。返回: 其他动作原返回值。异常: 指定唯一KI。
                """
                if not reached and amount > 1024 ** 2:
                    reached.append(amount)
                    if after:
                        actual_release(amount)
                    raise error
                return actual_release(amount)

            with patch.object(data.budget, 'release_ram', side_effect=cancel_large):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    next(owner)
            self.assertIs(caught.exception, error)
            self.assertEqual(len(reached), 1)
            owner.close()
            self.assertEqual(data.budget.ram_bytes, baseline)
            self.assertFalse(data.adapter.handles)

    def test_unreturned_request_constructor_cancel_owned_once_by_source(self):
        """默认请求未返回且固定费用清理失败，来源持唯一未安装请求并给出最高恢复入口。

        参数: 无。返回: None。异常: 请求失联、父子重复领费或清理越权断言失败。
        """
        data = self.fixture()
        baseline = data.budget.ram_bytes
        error = KeyboardInterrupt('default-csv-unreturned-request')
        reserve, _ = self.cancel(data.budget.reserve_ram, error, after=True, amount=20480, limit=1)
        with patch.object(data.budget, 'reserve_ram', side_effect=reserve):
            with patch.object(data.budget, 'release_ram', side_effect=KeyboardInterrupt('request-cleanup-three')):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    data.adapter.iter_batches(data.request)
        self.assertIs(caught.exception, error)
        self.assertIs(getattr(error, 'csv_source_cleanup_owner', None), data.adapter)
        child = data.adapter._uninstalled_request
        self.assertIs(child, getattr(error, 'csv_request_cleanup_owner', None))
        self.assertEqual(child.cost, 20480)
        self.assertEqual(data.budget.ram_bytes, baseline + child.cost)
        self.assertFalse(data.adapter.active)
        data.adapter.close()
        self.assertTrue(child.closed)
        self.assertEqual(data.budget.ram_bytes, 8192)

    def test_unreturned_resources_after_reserve_preserve_cause_and_request_owner(self):
        """资源固定预约后普通错误且释放持续失败，原cause和真实未返回检查器均可达。

        参数: 无。返回: None。异常: 子检查器丢失、cause改成清理KI或漏账断言失败。
        """
        data = self.fixture()
        baseline = data.budget.ram_bytes
        owner = self.request(data)
        error = MemoryError('default-csv-unreturned-resources')
        reserve, _ = self.cancel(data.budget.reserve_ram, error, after=True, amount=65536, limit=1)
        with patch.object(data.budget, 'reserve_ram', side_effect=reserve):
            with patch.object(data.budget, 'release_ram', side_effect=KeyboardInterrupt('resources-cleanup-three')):
                with self.assertRaises(SourceReadError) as caught:
                    next(owner)
        self.assertIs(caught.exception.__cause__, error)
        self.assertIs(getattr(caught.exception, 'csv_request_cleanup_owner', None), owner)
        resources = owner._resources
        self.assertIsNotNone(resources)
        self.assertEqual(resources._held_cost, 65536)
        self.assertEqual(data.budget.ram_bytes - baseline, owner.cost + resources._held_cost)
        self.assertFalse(data.adapter.handles)
        owner.close()
        self.assertEqual(data.budget.ram_bytes, baseline)

    def test_generator_request_and_resources_registration_failures_keep_real_owners(self):
        """三个真实登记点加入前后失败均清本次对象，不影响借用来源和余额。

        参数: 无。返回: None。异常: 未返回生成器/请求/检查器丢失或登记残留断言失败。
        """
        for slot in ('active', '_requests', '_resources'):
            for after in (False, True):
                data = self.fixture()
                baseline = data.budget.ram_bytes
                setattr(data.adapter, slot, RejectRegistration(after))
                if slot == '_resources':
                    owner = self.request(data)
                    with self.assertRaises(SourceReadError) as caught:
                        next(owner)
                    self.assertIsInstance(caught.exception.__cause__, MemoryError)
                    owner.close()
                else:
                    with self.assertRaises(MemoryError):
                        data.adapter.iter_batches(data.request)
                self.assertFalse(data.adapter.active)
                self.assertFalse(data.adapter._requests)
                self.assertFalse(data.adapter._resources)
                self.assertEqual(data.budget.ram_bytes, baseline)
                self.assertFalse(data.adapter.closed)

    def test_actual_fd_registration_failure_closes_uninstalled_file(self):
        """真实文件在handles登记前后失败时，默认请求已接住该FD并负责关闭。

        参数: 无。返回: None。异常: 未登记实际FD泄漏或注册主错被覆盖断言失败。
        """
        for after in (False, True):
            data = self.fixture()
            baseline = data.budget.ram_bytes
            data.adapter.handles = RejectRegistration(after)
            owner, files = self.request(data), []
            with patch.object(Path, 'open', autospec=True, side_effect=self.open_proxy(data, files)):
                with self.assertRaises(SourceReadError) as caught:
                    next(owner)
            self.assertIsInstance(caught.exception.__cause__, MemoryError)
            self.assertTrue(files)
            self.assertTrue(all(handle.closed for handle in files))
            self.assertEqual(data.budget.ram_bytes, baseline)
            self.assertTrue(owner.closed)

    def test_unreturned_slots_reject_new_requests_without_blocking_existing_read(self):
        """未返回请求或资源保唯一槽，新默认/观测请求拒覆盖，已返回另一read仍能继续。

        参数: 无。返回: None。异常: 旧owner被覆盖、提前预约、误阻已有read或恢复非零断言失败。
        """
        for slot in ('_requests', '_resources'):
            data = self.fixture(size=1, contents='ns,v\n1,2\n3,4\n5,6\n')
            existing = self.request(data)
            first = next(existing)
            self.assertEqual(tuple(first.series['value'].time_ns), (1,))
            handle = existing._handle
            rejected = RejectRegistration(False)
            rejected.update(getattr(data.adapter, slot))
            setattr(data.adapter, slot, rejected)
            with patch.object(data.budget, 'release_ram', side_effect=KeyboardInterrupt('uninstalled-slot-cleanup')):
                with self.assertRaises(MemoryError):
                    if slot == '_requests':
                        data.adapter.iter_batches(data.request)
                    else:
                        data.adapter._read_resources(data.request)
            attribute = '_uninstalled_request' if slot == '_requests' else '_uninstalled_resources'
            original = getattr(data.adapter, attribute)
            self.assertIsNotNone(original)
            self.assertFalse(original.closed)
            before = data.budget.ram_bytes
            # 新调用必须在任何预算/原生成器创建前拒绝，最高原owner仍由同一父槽保留。
            with patch.object(data.budget, 'reserve_ram', side_effect=AssertionError('未返回槽被覆盖前又预约')) as reserve:
                with self.assertRaises(SourceClosedError):
                    data.adapter.iter_batches(data.request)
                with self.assertRaises(SourceClosedError):
                    data.adapter.iter_batches_with_observation(data.request)
                if slot == '_resources':
                    with self.assertRaises(SourceClosedError):
                        data.adapter._read_resources(data.request)
                reserve.assert_not_called()
            self.assertIs(getattr(data.adapter, attribute), original)
            self.assertEqual(data.budget.ram_bytes, before)
            self.assertFalse(data.adapter._closing)
            second = next(existing)
            self.assertEqual(tuple(second.series['value'].time_ns), (3,))
            self.assertFalse(handle.closed)
            data.adapter.close()
            data.adapter.close()
            self.assertTrue(existing.closed)
            self.assertTrue(original.closed)
            self.assertTrue(handle.closed)
            self.assertEqual(data.budget.ram_bytes, 8192)

    def test_default_and_optional_observation_keep_distinct_owners_and_same_resource_amounts(self):
        """默认和可选观测各持独立请求，正常同批资源金额与原输出完全一致。

        参数: 无。返回: None。异常: 改可选正常费用、串请求或默认读取误采集观测断言失败。
        """
        data = self.fixture()
        baseline = data.budget.ram_bytes
        default = self.request(data)
        observed = data.adapter.iter_batches_with_observation(data.request)
        self.addCleanup(observed.close)
        first, second = next(default), next(observed)
        self.assertEqual(batch_facts(first), batch_facts(second))
        self.assertIsNot(default._resources, observed._resources)
        self.assertEqual(default._resources._held_cost, observed._resources._held_cost)
        self.assertEqual(default._resources.charges, observed._resources.charges)
        with self.assertRaises(StopIteration):
            next(default)
        with self.assertRaises(StopIteration):
            next(observed)
        self.assertEqual(observed.observation.row_count, 1)
        default.close()
        observed.close()
        self.assertEqual(data.budget.ram_bytes, baseline)
        self.assertFalse(data.adapter.closed)
