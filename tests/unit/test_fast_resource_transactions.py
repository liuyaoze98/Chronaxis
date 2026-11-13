"""核对 fast 构造、进程和关闭异常的真实所有权与主异常保留。

两份合成 ASC 各一帧；测试真实 worker 和共享账本，不作性能测量。
文件进入 tests/unit 后再运行，当前 D2 草稿尚未接入产品。
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from workspace_fixtures import TemporaryDirectory
from chronaxis.results.budget import ResourceBudget

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'Docs/Current/examples'


class AfterEffectOnce:
    """只在首次真实操作已经成功后抛错，后续调用继续使用原方法。"""

    def __init__(self, original, error):
        """保存实际调用和异常对象。参数: 原方法/异常。返回: 新注入器。异常: 无。"""
        self.original, self.error, self.fired = original, error, False

    def __call__(self, *args, **kwargs):
        """先产生真实效果再取消。参数: 原参数。返回: 原返回。异常: 首次指定异常。"""
        result = self.original(*args, **kwargs)
        if not self.fired:
            self.fired = True
            raise self.error
        return result


@contextmanager
def observed_budgets():
    """记录真正创建的账本，不替换限额、申请和释放实现。

    参数: 无。返回: 本次实际 ResourceBudget 列表。异常: 原构造及调用错误传播。
    """
    created = []
    original = ResourceBudget.__init__

    def observed(owner, *args, **kwargs):
        """完成真实初始化后登记。参数: 原构造参数。返回: None。异常: 原构造错误。"""
        original(owner, *args, **kwargs)
        created.append(owner)

    with patch.object(ResourceBudget, '__init__', new=observed):
        yield created


def close_test_workers(slots):
    """测试断言结束后兜底关闭捕获的真实资源，不能作为产品清理通过的依据。

    参数: 启动后观察到的槽快照。返回: None。异常: 真实进程或句柄清理失败传播。
    这个快照只用于防止一个失败用例影响下一个；所有产品责任断言先于本函数。
    """
    for slot in slots:
        process = slot.get('process')
        if process is not None and not getattr(process, '_closed', False):
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(5)
                if process.is_alive():
                    raise RuntimeError('测试自有 worker 未能结束')
            process.close()
        for key in ('control', 'data', 'child_control', 'child_data'):
            connection = slot.get(key)
            if connection is not None:
                connection.close()
        tree = slot.get('tree')
        if tree is not None:
            tree.close()


class FastResourceTransactionsTests(unittest.TestCase):
    """检查 fast 真实构造、worker 及主异常责任，数据量仅为两文件各一帧。"""

    def setUp(self):
        """生成隔离合成输入及编译配置。参数: 无。返回: None。异常: IO/配置错误。"""
        from chronaxis.configuration import load_configuration
        from chronaxis.fast.config import compile_config
        self.temporary = TemporaryDirectory(prefix='resource-transactions-', dir=ROOT/'work/audit-fix-02')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        header = 'date Mon Jan 01 00:00:00.000 2024\nbase hex timestamps absolute\ninternal events logged\n'
        paths = []
        for number in range(2):
            path = self.folder / f'part-{number}.asc'
            path.write_text(header + f'{number:.9f} 1 100 Rx d 2 A0 0F\n', encoding='ascii')
            paths.append(str(path))
        raw = load_configuration(EXAMPLES/'message-minimal.yaml').data
        raw['dataset'] = dict(name='resource_transactions')
        raw['sources'][0]['paths'] = paths
        raw['sources'][0]['dbc_by_channel']['1'] = str(EXAMPLES/'data/power.dbc')
        raw['execution'] = dict(process_count=1)
        path = self.folder/'analysis.json'
        path.write_text(json.dumps(raw), encoding='utf-8')
        self.spec = compile_config(path)
        from chronaxis import AnalysisPlan
        self.plan = AnalysisPlan.from_dict(raw, base_dir=self.folder)

    def pool(self):
        """真实构造尚未启动的工作池。参数: 无。返回: FilePool。异常: 原初始化错误。"""
        from chronaxis.fast.session import FilePool, file_specs
        pool = FilePool(file_specs(self.spec), ResourceBudget(), self.folder, None, dict(worker_pids=[]))
        return pool

    def start_pool(self, pool):
        """启动一个真实 worker 并登记测试兜底，不模拟管道或进程对象。

        参数: 实际工作池。返回: 启动时槽快照。异常: 原启动错误。
        """
        try:
            pool.start(1)
        finally:
            slots = tuple(pool.slots)
            self.addCleanup(close_test_workers, slots)
        self.assertEqual(len(slots), 1)
        self.assertIsNotNone(slots[0]['process'].pid)
        return slots

    def assert_zero_budgets(self, budgets):
        """断言真实所有者已退费。参数: 本次观察的账本。返回: None。异常: 断言失败。"""
        self.assertTrue(budgets)
        self.assertEqual([budget.ram_bytes for budget in budgets], [0] * len(budgets))

    def test_pool_start_after_reserve_cancel_can_close_owned_fee(self):
        """工作槽申请成功后取消，即使尚未启动进程，费用仍须由池恢复。"""
        pool = self.pool()
        error = KeyboardInterrupt('pool reserve already recorded')
        fault = AfterEffectOnce(pool.budget.reserve_ram, error)
        with patch.object(pool.budget, 'reserve_ram', new=fault):
            with self.assertRaises(KeyboardInterrupt) as caught:
                pool.start(1)
        self.assertIs(caught.exception, error)
        self.assertTrue(fault.fired)
        self.assertFalse(pool.slots)
        pool.close()
        pool.close()
        self.assertEqual(pool.budget.ram_bytes, 0)

    @unittest.skipUnless(os.name == 'nt', '该用例核对 Windows 实际进程树句柄；跨平台适配另验收')
    def test_pool_failed_tree_close_keeps_real_handle_for_retry(self):
        """真实 worker 已停止但作业句柄首次关闭失败，池仍须持有并重试该句柄。"""
        pool = self.pool()
        slots = self.start_pool(pool)
        tree = slots[0]['tree']
        self.assertIsNotNone(tree)
        self.assertIsNotNone(tree._handle)
        original, calls = tree.close, []
        error = OSError('real job handle first close failed')

        def fail_once():
            """首次保留真实句柄并失败。参数: 无。返回: None。异常: 首次 OSError。"""
            calls.append(True)
            if len(calls) == 1:
                raise error
            return original()

        with patch.object(tree, 'close', new=fail_once):
            with self.assertRaises((OSError, RuntimeError)) as caught:
                pool.close()
        self.assertTrue(caught.exception is error or caught.exception.__cause__ is error)
        self.assertIsNotNone(tree._handle)
        self.assertTrue(any(slot.get('tree') is tree for slot in pool.slots))
        pool.close()
        self.assertIsNone(tree._handle)
        self.assertEqual(pool.budget.ram_bytes, 0)
        pool.close()

    def test_pool_close_after_release_cancel_does_not_release_twice(self):
        """实际 worker 和费用已释放后取消，再次 close 不得重复抵销费用。"""
        pool = self.pool()
        slots = self.start_pool(pool)
        connections = tuple(slot[key] for slot in slots for key in ('control', 'data'))
        processes = tuple(slot['process'] for slot in slots)
        error = KeyboardInterrupt('pool release already recorded')
        fault = AfterEffectOnce(pool.budget.release_ram, error)
        with patch.object(pool.budget, 'release_ram', new=fault):
            with self.assertRaises(KeyboardInterrupt) as caught:
                pool.close()
        self.assertIs(caught.exception, error)
        self.assertTrue(fault.fired)
        self.assertEqual(pool.budget.ram_bytes, 0)
        self.assertTrue(all(connection.closed for connection in connections))
        self.assertTrue(all(getattr(process, '_closed', False) for process in processes))
        pool.close()
        self.assertEqual(pool.budget.ram_bytes, 0)

    def test_fast_initial_reserve_after_cancel_returns_budget(self):
        """会话首笔费用实际入账后取消，未返回的会话也必须恢复为零。"""
        from chronaxis.fast.session import run_session
        error = KeyboardInterrupt('fast initial reserve already recorded')
        fault = AfterEffectOnce(ResourceBudget.reserve_ram, error)

        def fail_after_reserve(budget, amount):
            """保留类方法的实例绑定。参数: 实际账本/bytes。返回: None。异常: 首次入账后取消。"""
            return fault(budget, amount)

        with observed_budgets() as budgets, patch.object(ResourceBudget, 'reserve_ram', new=fail_after_reserve):
            with self.assertRaises(KeyboardInterrupt) as caught:
                run_session(self.spec, work_dir=self.folder)
        self.assertIs(caught.exception, error)
        self.assertTrue(fault.fired)
        self.assert_zero_budgets(budgets)

    def test_fast_accumulator_constructor_failure_returns_budget(self):
        """累计器真实构造后失败仍在会话构造保护区内，不能遗留固定费用。"""
        from chronaxis.fast.session import run_session, SessionAccumulator
        error = MemoryError('accumulator constructed then failed')
        original, constructed = SessionAccumulator.__init__, []

        def fail_after_construct(owner, spec):
            """先真实构造再故障。参数: 实例/编译配置。返回: 无。异常: 指定 MemoryError。"""
            original(owner, spec)
            constructed.append(owner)
            raise error

        with observed_budgets() as budgets, patch.object(SessionAccumulator, '__init__', new=fail_after_construct):
            with self.assertRaises(MemoryError) as caught:
                run_session(self.spec, work_dir=self.folder)
        self.assertIs(caught.exception, error)
        self.assertEqual(len(constructed), 1)
        self.assert_zero_budgets(budgets)

    def test_fast_read_error_survives_reader_close_error(self):
        """读取到真实贡献后失败，后续实际关闭附加报错不能替换原读取异常。"""
        from chronaxis.fast.session import run_session
        from chronaxis.fast.stream import FileContributions
        primary, cleanup = OSError('contribution read failed'), OSError('reader close additionally failed')
        original_next, original_close = FileContributions.__next__, FileContributions.close
        readers, close_faults = [], []

        def fail_after_read(reader):
            """确认真实读取后再失败。参数: 读取器。返回: 无。异常: 原始测试故障。"""
            original_next(reader)
            readers.append(reader)
            raise primary

        def fail_after_close(reader):
            """先关闭真实句柄再报一次错。参数: 读取器。返回: None。异常: 一次清理副错。"""
            was_closed = reader.closed
            original_close(reader)
            if not was_closed and not close_faults:
                close_faults.append(True)
                raise cleanup

        with observed_budgets() as budgets, patch.object(FileContributions, '__next__', new=fail_after_read), patch.object(
                FileContributions, 'close', new=fail_after_close):
            with self.assertRaises(OSError) as caught:
                run_session(self.spec, work_dir=self.folder)
        self.assertTrue(readers and close_faults)
        self.assertTrue(all(reader.closed for reader in readers))
        self.assertIs(caught.exception, primary)
        self.assert_zero_budgets(budgets)

    def test_fast_compute_error_survives_final_release_after_cancel(self):
        """已消费实际贡献后的主错，与最后退款已完成后取消同时发生时保留主错。"""
        from chronaxis.fast.session import run_session, SessionAccumulator
        primary, cleanup = ArithmeticError('actual contribution then calculation failed'), KeyboardInterrupt('final release done')
        consume, release = SessionAccumulator.consume, ResourceBudget.release_ram
        consumed, refunded = [], []

        def fail_after_consume(owner, record):
            """先运行实际累计再故障。参数: 累计器/记录。返回: 无。异常: 主错。"""
            consume(owner, record)
            consumed.append(record)
            raise primary

        def fail_after_final_release(budget, amount):
            """最后退款真实归零后取消。参数: 账本/金额。返回: None。异常: 一次取消。"""
            release(budget, amount)
            if budget.ram_bytes == 0 and not refunded:
                refunded.append(True)
                raise cleanup

        with observed_budgets() as budgets, patch.object(SessionAccumulator, 'consume', new=fail_after_consume), patch.object(
                ResourceBudget, 'release_ram', new=fail_after_final_release):
            with self.assertRaises(ArithmeticError) as caught:
                run_session(self.spec, work_dir=self.folder)
        self.assertTrue(consumed and refunded)
        self.assertIs(caught.exception, primary)
        self.assert_zero_budgets(budgets)

    def test_fast_task_error_survives_real_pool_close_error(self):
        """实际双 worker 完成消费后主任务失败，池关闭副错不改变向外传播的主错。"""
        from chronaxis.fast.session import FilePool, run_session
        primary, cleanup = OSError('completed consumption then task failed'), OSError('pool closed additionally failed')
        concatenate, close = FilePool.concatenate, FilePool.close
        consumed, close_faults = [], []

        def fail_after_concatenate(pool, accumulator):
            """实际消费全部贡献后失败。参数: 池/累计器。返回: 无。异常: 主错。"""
            self.addCleanup(close_test_workers, tuple(pool.slots))
            concatenate(pool, accumulator)
            consumed.append(pool)
            raise primary

        def fail_after_close(pool, success=False):
            """执行真实池清理再附加一次故障。参数: 池/完成标志。返回: None。异常: 副错。"""
            close(pool, success)
            if not close_faults:
                close_faults.append(True)
                raise cleanup

        with observed_budgets() as budgets, patch.object(FilePool, 'concatenate', new=fail_after_concatenate), patch.object(
                FilePool, 'close', new=fail_after_close):
            with self.assertRaises(OSError) as caught:
                run_session(dict(self.spec, process_count=2), work_dir=self.folder)
        self.assertTrue(consumed and close_faults)
        self.assertIs(caught.exception, primary)
        self.assert_zero_budgets(budgets)


    def test_live_workers_and_owned_directory_survive_persistent_close_failure(self):
        """关闭持续失败时实际worker仍活动，目录和预算必须随原异常owner保留。"""
        from chronaxis.fast.session import FilePool, run_session
        primary, cleanup = OSError('task stopped before consumption'), OSError('pool close still unavailable')
        observed = []

        def stop_before_consumption(pool, accumulator):
            """取得真实活动worker后模拟主任务失败；不伪造进程或任何关闭结果。"""
            slots = tuple(dict(slot) for slot in pool.slots)
            self.addCleanup(close_test_workers, slots)
            observed.append((pool, slots))
            self.assertTrue(any(slot['process'].is_alive() for slot in slots))
            raise primary

        def fail_close(pool, success=False):
            """在关闭前持续失败，保持真实进程和费用。参数: 池/成功标记。异常: 清理错误。"""
            raise cleanup

        with observed_budgets() as budgets, patch.object(FilePool, 'concatenate', new=stop_before_consumption), patch.object(
                FilePool, 'close', new=fail_close):
            with self.assertRaises(OSError) as caught:
                run_session(dict(self.spec, process_count=2), work_dir=self.folder)
            self.assertIs(caught.exception, primary)
            owner = caught.exception.fast_session_cleanup_owner
            self.addCleanup(owner.close)
            pool, slots = observed[0]
            self.assertIs(owner.pool, pool)
            directory = owner.directory
            self.assertTrue(directory.is_dir())
            self.assertTrue(any(slot['process'].is_alive() for slot in slots))
            held = pool.budget.ram_bytes
            self.assertGreater(held, 0)
            for _ in range(2):
                with self.assertRaises(OSError) as repeated:
                    owner.close()
                self.assertIs(repeated.exception, cleanup)
                self.assertTrue(directory.is_dir())
                self.assertEqual(pool.budget.ram_bytes, held)
        owner.close()
        self.assertFalse(directory.exists())
        self.assertTrue(all(getattr(slot['process'], '_closed', False) for slot in slots))
        self.assert_zero_budgets(budgets)
        owner.close()

    def test_opened_asc_constructor_failure_retains_reader_until_close_recovers(self):
        """ASC真实文件已打开后，取得迭代器失败且关闭持续失败，最高owner仍可恢复。"""
        from chronaxis.fast.session import run_session
        from chronaxis.sources.asc import ASCRead
        primary, cleanup = MemoryError('iterator allocation failed'), OSError('ASC close still unavailable')
        original_close, opened = ASCRead.close, []

        def fail_iterator(reader):
            """故障点在ASC构造已完成之后；保存真实文件作资源断言。"""
            self.assertFalse(reader._file.closed)
            opened.append((reader, reader._file))
            self.addCleanup(original_close, reader)
            raise primary

        def fail_close(reader):
            """持续拒绝关闭实际打开文件，不改closed状态或预算。"""
            raise cleanup

        with observed_budgets() as budgets, patch.object(ASCRead, '__iter__', new=fail_iterator), patch.object(
                ASCRead, 'close', new=fail_close):
            with self.assertRaises(MemoryError) as caught:
                run_session(self.spec, work_dir=self.folder)
            self.assertIs(caught.exception, primary)
            owner = caught.exception.fast_session_cleanup_owner
            self.addCleanup(owner.close)
            reader, handle = opened[0]
            self.assertIs(owner.reader.reader, reader)
            self.assertFalse(handle.closed)
            held = owner._budget.ram_bytes
            self.assertGreater(held, 0)
            for _ in range(2):
                with self.assertRaises(OSError):
                    owner.close()
                self.assertFalse(handle.closed)
                self.assertFalse(reader.closed)
                self.assertEqual(owner._budget.ram_bytes, held)
        owner.close()
        self.assertTrue(handle.closed)
        self.assertTrue(reader.closed)
        self.assert_zero_budgets(budgets)
        owner.close()

    @unittest.skipUnless(os.name == 'nt', '核对Windows实际作业对象和失败构造恢复')
    def test_process_tree_constructor_failure_preserves_real_job_owner(self):
        """作业对象真实创建后构造失败；关闭正常或持续失败均不替换主异常。"""
        from chronaxis.batch import process_tree
        ProcessTree = process_tree.ProcessTree
        original_close = ProcessTree.close
        for persistent in (False, True):
            with self.subTest(persistent=persistent):
                pool = self.pool()
                self.addCleanup(pool.close)
                primary = MemoryError('job limits allocation failed')
                cleanup = OSError('job handle close still unavailable')
                trees = []

                def observe_close(tree):
                    """观察真实作业句柄，按本子例保留或实际关闭。"""
                    if not trees:
                        trees.append((tree, tree._handle))
                        self.addCleanup(original_close, tree)
                    if persistent:
                        raise cleanup
                    original_close(tree)

                try:
                    with patch.object(process_tree, '_ExtendedLimits', side_effect=primary), patch.object(
                            ProcessTree, 'close', new=observe_close):
                        with self.assertRaises(MemoryError) as caught:
                            pool.start(1)
                        self.assertIs(caught.exception, primary)
                        self.assertTrue(trees and trees[0][1])
                        tree, handle = trees[0]
                        if persistent:
                            self.assertIs(caught.exception.process_tree_cleanup_owner, tree)
                            self.assertIs(caught.exception.fast_pool_cleanup_owner, pool)
                            self.assertTrue(any(slot.get('tree') is tree for slot in pool.slots))
                            self.assertFalse(tree._closed)
                            self.assertEqual(tree._handle, handle)
                            self.assertGreater(pool.budget.ram_bytes, 0)
                        else:
                            self.assertTrue(tree._closed)
                            self.assertEqual(pool.budget.ram_bytes, 0)
                finally:
                    self.addCleanup(close_test_workers, tuple(dict(slot) for slot in pool.slots))
                pool.close()
                self.assertTrue(tree._closed)
                self.assertIsNone(tree._handle)
                self.assertEqual(pool.budget.ram_bytes, 0)

    @unittest.skipUnless(os.name == 'nt', '核对Windows实际OpenProcess句柄的独立责任')
    def test_process_tree_process_handle_failure_is_not_lost_after_job_closes(self):
        """作业已关闭但登记用进程句柄仍未关闭时，池不能因_handle为空丢掉owner。"""
        from chronaxis.batch.process_tree import ProcessTree
        original_release, original_close = ProcessTree._close_process_handle, ProcessTree.close
        primary, cleanup = OSError('registration process handle close failed'), OSError('process handle still blocked')
        pool = self.pool()
        self.addCleanup(pool.close)
        trees, calls = [], []

        def fail_release(tree):
            """仅阻止真实OpenProcess句柄关闭；作业句柄仍走真实CloseHandle。"""
            if tree._process_handle:
                if not trees:
                    trees.append((tree, tree._process_handle))
                    self.addCleanup(original_close, tree)
                calls.append(True)
                raise primary if len(calls) == 1 else cleanup
            return original_release(tree)

        try:
            with patch.object(ProcessTree, '_close_process_handle', new=fail_release):
                with self.assertRaises(OSError) as caught:
                    pool.start(1)
                self.assertIs(caught.exception, primary)
                tree, process_handle = trees[0]
                self.assertIs(caught.exception.process_tree_cleanup_owner, tree)
                self.assertIs(caught.exception.fast_pool_cleanup_owner, pool)
                self.assertIsNone(tree._handle)
                self.assertEqual(tree._process_handle, process_handle)
                self.assertFalse(tree._closed)
                self.assertTrue(any(slot.get('tree') is tree for slot in pool.slots))
                self.assertGreater(pool.budget.ram_bytes, 0)
        finally:
            self.addCleanup(close_test_workers, tuple(dict(slot) for slot in pool.slots))
        pool.close()
        self.assertTrue(tree._closed)
        self.assertIsNone(tree._process_handle)
        self.assertEqual(pool.budget.ram_bytes, 0)
        pool.close()


    @unittest.skipUnless(os.name == 'nt', '核对Windows共享批量调用的真实进程树构造失败')
    def test_batch_worker_constructor_adopts_unclosed_tree(self):
        """批量入口未返回worker时，持续失败的树句柄及实际进程仍有最高owner。"""
        from chronaxis.batch import process_tree
        from chronaxis.batch.process_transport import ProcessWorker
        primary, cleanup = MemoryError('batch tree limits failed'), OSError('batch tree close blocked')
        original_close = process_tree.ProcessTree.close
        trees = []

        def fail_close(tree):
            """只阻止真实作业关闭并保留对象，故障撤销后由原方法关闭。"""
            if not trees:
                trees.append(tree)
                self.addCleanup(original_close, tree)
            raise cleanup

        with patch.object(process_tree, '_ExtendedLimits', side_effect=primary), patch.object(
                process_tree.ProcessTree, 'close', new=fail_close):
            with self.assertRaises(MemoryError) as caught:
                ProcessWorker()
            self.assertIs(caught.exception, primary)
            owner = caught.exception.batch_worker_cleanup_owner
            self.addCleanup(owner.close)
            self.assertIs(owner.tree, trees[0])
            self.assertIs(caught.exception.process_tree_cleanup_owner, owner.tree)
            self.assertTrue(owner.process.is_alive())
            handles = (owner.connection, owner._child)
            self.assertTrue(all(not handle.closed for handle in handles))
            for _ in range(2):
                with self.assertRaises(OSError):
                    owner.close()
                self.assertFalse(owner.closed)
                self.assertTrue(owner.process.is_alive())
        owner.close()
        self.assertTrue(owner.closed)
        self.assertTrue(all(handle.closed for handle in handles))
        self.assertTrue(getattr(owner.process, '_closed', False))
        self.assertTrue(trees[0]._closed)
        owner.close()

    @unittest.skipUnless(os.name == 'nt', '核对Windows普通并行CAN调用的真实进程树构造失败')
    def test_parallel_can_constructor_adopts_unclosed_tree(self):
        """普通CAN工作槽保留未返回的树和真实费用，重复关闭失败不丢槽或借用费用。"""
        from chronaxis.batch import process_tree
        from chronaxis.execution.parallel_can_decode import ParallelCANDecodeRead
        primary, cleanup = MemoryError('CAN tree limits failed'), OSError('CAN tree close blocked')
        original_close = process_tree.ProcessTree.close
        budget = ResourceBudget()
        budget.reserve_ram(4096)
        owner = ParallelCANDecodeRead(self.plan.sources[0].config, budget,
            tuple(item.definition for item in self.plan.signals), process_count=2,
            work_dir=self.folder/'parallel', emit_frame_ids=(256,), time_frame_ids=(256,))
        self.addCleanup(owner.close)
        trees = []

        def fail_close(tree):
            """作业确已创建，仅阻止它的关闭。参数: 实际树。异常: 持续清理错误。"""
            if not trees:
                trees.append(tree)
                self.addCleanup(original_close, tree)
            raise cleanup

        try:
            with patch.object(process_tree, '_ExtendedLimits', side_effect=primary), patch.object(
                    process_tree.ProcessTree, 'close', new=fail_close):
                with self.assertRaises(MemoryError) as caught:
                    owner.prepare_metadata()
                self.assertIs(caught.exception, primary)
                self.assertIs(caught.exception.text_can_cleanup_owner, owner)
                self.assertIs(caught.exception.process_tree_cleanup_owner, trees[0])
                self.assertTrue(any(slot.get('tree') is trees[0] for slot in owner._slots))
                held = budget.ram_bytes
                self.assertGreater(held, 4096)
                for _ in range(2):
                    with self.assertRaises(OSError):
                        owner.close()
                    self.assertEqual(budget.ram_bytes, held)
                    self.assertFalse(owner.closed)
        finally:
            self.addCleanup(close_test_workers, tuple(dict(slot) for slot in owner._slots))
        owner.close()
        self.assertTrue(owner.closed)
        self.assertTrue(trees[0]._closed)
        self.assertFalse(owner._slots)
        self.assertEqual(budget.ram_bytes, 4096)
        owner.close()


    @unittest.skipUnless(os.name == 'nt', '核对批量调度的真实Windows构造取消与恢复责任')
    def test_batch_cancel_keeps_pending_owner_but_clean_cancel_returns_report(self):
        """已清理Ctrl+C仍返回取消报告，未关闭真实句柄时必须保留原取消及恢复owner。"""
        from chronaxis.batch import BatchJob, BatchRunner, process_tree
        original_close = process_tree.ProcessTree.close
        for persistent in (False, True):
            with self.subTest(persistent=persistent):
                primary = KeyboardInterrupt('batch construction cancelled')
                cleanup = OSError('batch cancellation cleanup blocked')
                trees = []

                def observe_close(tree):
                    """按子例执行真实关闭或保留真实句柄，不能把两种取消混为一谈。"""
                    if not trees:
                        trees.append(tree)
                        self.addCleanup(original_close, tree)
                    if persistent:
                        raise cleanup
                    return original_close(tree)

                with patch.object(process_tree, '_ExtendedLimits', side_effect=primary), patch.object(
                        process_tree.ProcessTree, 'close', new=observe_close):
                    runner = BatchRunner(process_count=2)
                    output = self.folder / ('batch-cancel-blocked' if persistent else 'batch-cancel-clean')
                    jobs = (BatchJob('first', self.plan),)
                    if persistent:
                        returned = None
                        try:
                            with self.assertRaises(KeyboardInterrupt) as caught:
                                returned = runner.run(jobs, output, device_label='home')
                        finally:
                            # 旧调度可能吞掉取消，测试失败也必须登记真实owner兜底，不能留下worker。
                            pending = getattr(primary, 'batch_worker_cleanup_owner', None)
                            if pending is not None:
                                self.addCleanup(pending.close)
                            if returned is not None:
                                self.addCleanup(returned.close)
                        self.assertIs(caught.exception, primary)
                        owner = caught.exception.batch_worker_cleanup_owner
                        self.addCleanup(owner.close)
                        report = caught.exception.batch_report
                        self.addCleanup(report.close)
                        self.assertIs(owner.tree, trees[0])
                        self.assertFalse(owner.closed)
                        self.assertTrue(owner.process.is_alive())
                    else:
                        report = runner.run(jobs, output, device_label='home')
                        self.addCleanup(report.close)
                        self.assertEqual(report.status, 'cancelled')
                        self.assertTrue(report.cancel_requested)
                        self.assertTrue(trees[0]._closed)
                if persistent:
                    owner.close()
                    self.assertTrue(owner.closed)
                    self.assertTrue(trees[0]._closed)
                report.close()
