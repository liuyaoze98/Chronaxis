"""验收真实结果层的RAM责任、构造恢复及关闭取消后的重试。

共享账本预先持有8192 bytes调用方费用，所有结果层操作只能归还自有金额。
既有typed合成helper实写新目录，检查有限buffer、归并、metadata、reader和writer。
申请成功后取消与释放成功后取消都按真实账本验证，不手工清零掩盖生产缺陷。
未返回构造遇持续清理失败时原异常须交出正式恢复owner；真实reader句柄关闭可重试。
Path.open只记录真实句柄，iterator代理仅包装同一个真实FD，不替换整个工厂。
不注入spool局部ExitStack任意FD关闭失败，不扩大旧reader/decoder边界。
所有合成文件与home证据仅写work，原test_results及其work历史保持。
"""

# 原模型夹具按模块别名复用；只在新专项复制运行元数据并标记实际home来源。
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_results as fixtures
from chronaxis.results import AnalysisResult, AnalysisError, ResourceBudget, ResultClosedError
from chronaxis.results.codec import estimate_row_bytes
from chronaxis.results.result import _RowIterator
from chronaxis.results.spool import ResultSpool


class CancelClosingHandle:
    """保留实际二进制FD，只在首次close前后取消；其余调用原样交给同一FD。"""

    def __init__(self, handle, after, error):
        """保存真实句柄与一次故障。参数: handle/阶段/原异常。返回: None。异常: 无。"""
        self.handle, self.after, self.error, self.fired = handle, after, error, False

    @property
    def closed(self):
        """读取真实FD状态。参数: 无。返回: bool。异常: 无。"""
        return self.handle.closed

    def readline(self, size):
        """读取同一个真实FD。参数: 最大bytes。返回: bytes。异常: 原文件错误。"""
        return self.handle.readline(size)

    def close(self):
        """一次取消后可真实重试。参数: 无。返回: None。异常: 首次原异常或实际关闭错误。"""
        if not self.fired:
            self.fired = True
            if self.after:
                self.handle.close()
            raise self.error
        self.handle.close()


class ResultResourceLifecycleTests(unittest.TestCase):
    """每个场景使用独立真实budget/目录，自有owner逆序关闭，最后核对借用8192保持。"""

    def setUp(self):
        """建立新项目专用目录。参数: 无。返回: None。异常: 实际目录错误。"""
        self.work = Path('work/m2-run-tests/result-lifecycle') / uuid4().hex
        self.work.mkdir(parents=True, exist_ok=False)

    def budget(self):
        """保留独立调用方基线。参数: 无。返回: 64MiB真实账本。异常: 预算错误。"""
        budget = ResourceBudget(64 * 1024 * 1024)
        budget.reserve_ram(8192)
        self.addCleanup(self.cleanup_budget, budget)
        return budget

    def cleanup_budget(self, budget):
        """生产资源全关后核对借用费用。参数: 实际账本。返回: None。异常: 泄漏或错误抵销断言。"""
        # 断言先于调用方释放；禁止用全账本余额清零把生产泄漏变成通过。
        self.assertEqual(budget.ram_bytes, 8192)
        budget.release_ram(8192)

    def spool(self, budget=None, *, buffer_rows=1):
        """创建真实有限暂存并登记close。参数: 可用账本/缓冲行数。返回: ResultSpool。异常: 构造原错误。"""
        budget = self.budget() if budget is None else budget
        spool = ResultSpool(budget, self.work / uuid4().hex, buffer_rows, enable_selections=True, requested_tables=('events','segments','selections'))
        self.addCleanup(spool.close)
        return spool

    def metadata(self):
        """复制旧helper合成事实，仅新产出标home与实际时间。参数: 无。返回: RunMetadata。异常: 模型错误。"""
        return replace(fixtures.run_metadata(), device_label='home', detailed_diagnostics=True, retain_work=True,
                       started_at=datetime.now(timezone(timedelta(hours=8))).isoformat())

    def result(self):
        """真实typed行实写封口后建立结果。参数: 无。返回: AnalysisResult。异常: IO/预算/模型错误。"""
        spool = self.spool()
        spool.append(fixtures.summary_event_row(0, 10))
        spool.append(fixtures.summary_selection_row(1, unknown=True))
        spool.seal()
        result = AnalysisResult(spool, self.metadata())
        self.addCleanup(result.close)
        return result

    def cancel_once(self, original, *, amount, after=False, call=1, error):
        """仅目标金额第N笔前后取消。参数: 实际方法/金额/阶段/次数/原异常。返回: 函数。异常: 原指定异常。"""
        matched = 0

        def invoke(value):
            """保留真实金额操作。参数: bytes。返回: 原操作返回。异常: 指定的一次故障。"""
            nonlocal matched
            if value == amount:
                matched += 1
                if matched == call:
                    if after:
                        original(value)
                    raise error
            return original(value)

        return invoke

    def expect_cancel(self, action, budget, method, amount, *, after=False, call=1, persistent=False, error=None):
        """调用真实动作并核对原异常，不替换构造工厂。参数: 动作/预算/注入配置。返回: 原异常。异常: 错误身份断言。"""
        error = KeyboardInterrupt('result-lifecycle-budget') if error is None else error
        actual = getattr(budget, method)
        callback = self.cancel_once(actual, amount=amount, after=after, call=call, error=error)
        # 持续清理故障只用于reserve失败后：任何release都取消，恢复owner必须保留实际责任。
        cleanup = patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-cleanup')) if persistent else nullcontext()
        with patch.object(budget, method, callback), cleanup:
            with self.assertRaises(type(error)) as caught:
                action()
        self.assertIs(caught.exception, error)
        return error

    def tracked_open(self, handles):
        """返回只记录真实文件打开的函数。参数: 有限handles列表。返回: Path.open包装。异常: 原文件错误。"""
        original = Path.open

        def open_real(path, *args, **kwargs):
            """打开真实路径并登记句柄。参数: Path及原打开参数。返回: 实际句柄。异常: 原IO错误。"""
            handle = original(path, *args, **kwargs)
            handles.append(handle)
            return handle

        return open_real

    def test_spool_constructor_reserve_before_after_transient_cancel_reclaims_fixed(self):
        """固定描述预约前/成功后取消均保原异常并归还4096，自有对象未返回也不扣借用费用。

        参数: 无。返回: None。异常: 预约后取消泄漏或构造原错丢失。
        """
        for after in (False, True):
            with self.subTest(after=after):
                budget = self.budget()
                self.expect_cancel(lambda: ResultSpool(budget, self.work / uuid4().hex, 1),
                    budget, 'reserve_ram', 4096, after=after)
                self.assertEqual(budget.ram_bytes, 8192)

    def test_spool_constructor_persistent_cleanup_keeps_original_and_recovery_owner(self):
        """固定预约成功后MemoryError且持续release取消，原异常提供正式spool恢复owner。

        参数: 无。返回: None。异常: owner不可达、原MemoryError替换或恢复费用不符。
        """
        budget = self.budget()
        error = self.expect_cancel(lambda: ResultSpool(budget, self.work / uuid4().hex, 1), budget,
            'reserve_ram', 4096, after=True, persistent=True, error=MemoryError('spool-constructor'))
        owner = getattr(error, 'result_spool_cleanup_owner', None)
        self.assertIsInstance(owner, ResultSpool)
        self.addCleanup(owner.close)
        self.assertEqual(budget.ram_bytes, 8192 + 4096)
        owner.close()
        owner.close()
        self.assertEqual(budget.ram_bytes, 8192)

    def test_spool_fixed_close_release_before_after_retry_is_exact(self):
        """固定释放前或实际抵销后取消，第二close只归还仍持有的自有金额。

        参数: 无。返回: None。异常: closed过早封死重试或成功后重复扣账。
        """
        for after in (False, True):
            spool = self.spool()
            budget = spool.budget
            self.expect_cancel(spool.close, budget, 'release_ram', 4096, after=after)
            if budget.ram_bytes > 8192:
                self.assertFalse(spool._closed)
            spool.close()
            spool.close()
            self.assertEqual(budget.ram_bytes, 8192)

    def test_append_pending_reserve_before_after_does_not_orphan_unencoded_row(self):
        """原行编码前预约前后取消，pending费用真实接管；追加失败后close能恢复基线。

        参数: 无。返回: None。异常: 未编码费用失去责任或失败被当成正常building。
        """
        for after in (False, True):
            spool = self.spool(buffer_rows=8)
            row = fixtures.summary_event_row(0, 10)
            self.expect_cancel(lambda: spool.append(row), spool.budget, 'reserve_ram',
                               estimate_row_bytes(row), after=after)
            self.assertEqual(spool.state, 'cancelled')
            spool.close()
            self.assertEqual(spool.budget.ram_bytes, 8192)

    def test_append_pending_persistent_cleanup_preserves_original_and_existing_owner(self):
        """pending预约成功后原MemoryError及持续release取消，已有spool保留费用并可恢复close。

        参数: 无。返回: None。异常: 清理覆盖原错误或未入buffer费用被遗漏。
        """
        spool = self.spool(buffer_rows=8)
        row = fixtures.summary_event_row(0, 10)
        cost = estimate_row_bytes(row)
        self.expect_cancel(lambda: spool.append(row), spool.budget, 'reserve_ram', cost,
            after=True, persistent=True, error=MemoryError('append-pending'))
        self.assertGreaterEqual(spool.budget.ram_bytes, 8192 + cost)
        spool.close()
        self.assertEqual(spool.budget.ram_bytes, 8192)

    def test_original_business_error_survives_persistent_ram_cleanup_and_recovers_owner(self):
        """真实flush写入和结果安装的业务OSError同时遇持续RAM清理取消，原错误与恢复责任保持。

        参数: 无。返回: None。异常: 业务原错被清理KeyboardInterrupt覆盖、FD未关或恢复费用错误。
        """
        with self.subTest(stage='spool-flush'):
            spool = self.spool(buffer_rows=2)
            spool.append(fixtures.summary_event_row(0, 10))
            original = OSError('actual-flush-write-failed')
            actual_write = spool._write_bytes
            handles = []
            fired = False

            def write_then_fail(handle, payload):
                """真实写入后首度抛业务错误。参数: 实际FD/bytes。返回: None。异常: 一次原OSError。"""
                nonlocal fired
                actual_write(handle, payload)
                if not fired:
                    fired = True
                    raise original

            # 两行确实进入flush并写到真实文件；只让RAM release持续取消，文件with仍正常关闭。
            with patch.object(spool, '_write_bytes', write_then_fail), \
                 patch.object(spool.budget, 'release_ram', side_effect=KeyboardInterrupt('flush-cleanup-persistent')), \
                 patch.object(Path, 'open', self.tracked_open(handles)):
                with self.assertRaises(OSError) as caught:
                    spool.append(fixtures.summary_event_row(1, 1))
            self.assertIs(caught.exception, original)
            self.assertTrue(handles)
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertTrue(any('KeyboardInterrupt' in note for note in getattr(original, '__notes__', ())))
            recovered = getattr(original, 'result_spool_cleanup_owner', None)
            self.assertIs(recovered, spool)
            self.assertGreater(spool.budget.ram_bytes, 8192)
            recovered.close()
            self.assertEqual(spool.budget.ram_bytes, 8192)

        with self.subTest(stage='result-install'):
            result = self.result()
            destination = self.work / ('failed-install-' + uuid4().hex)
            original = OSError('actual-install-failed')
            actual_release = result.spool.budget.release_ram
            reader_cost = result.spool.reader_cost
            table_reader_costs = {result.spool.reader_cost_for(table) for table in result.spool.tables}
            self.assertNotIn(reader_cost, table_reader_costs)
            readers_released = 0
            handles = []

            def keep_writer_release_cancelled(amount):
                """三reader按真实表金额释放，其后原writer金额持续取消。参数: bytes。返回: 原结果。异常: writer清理取消。"""
                nonlocal readers_released
                if amount in table_reader_costs:
                    readers_released += 1
                if amount == reader_cost:
                    readers_released += 1
                    if readers_released > 3:
                        raise KeyboardInterrupt('writer-cleanup-persistent')
                return actual_release(amount)

            # 所有真实表/质量/清单先生成并正常关FD；只在最后安装阶段注入原OSError，不替换整个工厂。
            with patch.object(result, '_install_directory', side_effect=original), \
                 patch.object(result.spool.budget, 'release_ram', keep_writer_release_cancelled), \
                 patch.object(Path, 'open', self.tracked_open(handles)):
                with self.assertRaises(AnalysisError) as caught:
                    result.write(destination)
            self.assertIs(caught.exception.__cause__, original)
            self.assertFalse(destination.exists())
            self.assertGreaterEqual(readers_released, 4)
            self.assertTrue(handles)
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertTrue(any('KeyboardInterrupt' in note for note in getattr(caught.exception, '__notes__', ())))
            recovered = getattr(caught.exception, 'analysis_result_cleanup_owner', None)
            self.assertIs(recovered, result)
            recovered.close()
            self.assertEqual(result.spool.budget.ram_bytes, 8192)

    def test_two_buffer_entries_clear_release_before_after_removes_each_charge_once(self):
        """两个已编码缓冲项的合计费用释放前后取消，不丢未释放金额也不重复抵销。

        参数: 无。返回: None。异常: 断链丢费用或重复抵销借用8192。
        """
        for after in (False, True):
            spool = self.spool(buffer_rows=8)
            spool.append(fixtures.summary_event_row(0, 10))
            spool.append(fixtures.summary_event_row(1, 1))
            # 生产按同一owner的缓冲总额抵销；两项均已真实计费，取消目标是这笔完整金额。
            cost = spool._buffer_cost
            self.expect_cancel(spool.close, spool.budget, 'release_ram', cost, after=after)
            spool.close()
            self.assertEqual(spool.budget.ram_bytes, 8192)
            self.assertEqual(spool._buffer, [])

    def test_flush_release_after_cancel_closes_real_files_and_keeps_original(self):
        """两行触发真实flush，缓冲费用实际归还后取消；所有真实FD关闭，原取消不被二次释放覆盖。

        参数: 无。返回: None。异常: flush句柄残留、原异常替换或清理重复计账。
        """
        spool = self.spool(buffer_rows=2)
        spool.append(fixtures.summary_event_row(0, 10))
        second = fixtures.summary_event_row(1, 1)
        cost = spool._buffer_cost + estimate_row_bytes(second)
        handles = []
        with patch.object(Path, 'open', self.tracked_open(handles)):
            self.expect_cancel(lambda: spool.append(second),
                               spool.budget, 'release_ram', cost, after=True)
        self.assertTrue(handles)
        self.assertTrue(all(handle.closed for handle in handles))
        spool.close()
        self.assertEqual(spool.budget.ram_bytes, 8192)

    def test_merge_reserve_before_after_cancel_reclaims_slot_before_any_open(self):
        """两真实run归并空间预约前后取消，未打开merge输入也不会孤立两reader费用。

        参数: 无。返回: None。异常: merge预约后取消漏账或故障被吞。
        """
        for after in (False, True):
            spool = self.spool()
            spool.append(fixtures.summary_event_row(0, 10))
            spool.append(fixtures.summary_event_row(1, 1))
            handles = []
            with patch.object(Path, 'open', self.tracked_open(handles)):
                self.expect_cancel(spool.seal, spool.budget, 'reserve_ram', 2 * spool.reader_cost_for('events'), after=after)
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertEqual(spool.state, 'cancelled')
            spool.close()
            self.assertEqual(spool.budget.ram_bytes, 8192)

    def test_merge_release_before_after_cancel_closes_actual_three_files_and_recovers(self):
        """实际两路归并完成后槽位释放前后取消，三个真实归并FD关闭且剩余金额可由close恢复。

        参数: 无。返回: None。异常: FD残留或归并slot成功后取消重复扣账。
        """
        for after in (False, True):
            spool = self.spool()
            spool.append(fixtures.summary_event_row(0, 10))
            spool.append(fixtures.summary_event_row(1, 1))
            handles = []
            with patch.object(Path, 'open', self.tracked_open(handles)):
                self.expect_cancel(spool.seal, spool.budget, 'release_ram', 2 * spool.reader_cost_for('events'), after=after)
            self.assertGreaterEqual(len(handles), 3)
            self.assertTrue(all(handle.closed for handle in handles))
            spool.close()
            self.assertEqual(spool.budget.ram_bytes, 8192)

    def test_analysis_metadata_constructor_reserve_before_after_cancel_reclaims_owned_spool(self):
        """结果metadata预约前后取消，真实已封口spool已接管，构造未返回也须归还二者费用。

        参数: 无。返回: None。异常: metadata预约后孤立或spool未关闭。
        """
        for after in (False, True):
            spool = self.spool()
            spool.append(fixtures.summary_selection_row(0, unknown=True))
            spool.seal()
            metadata = self.metadata()
            self.expect_cancel(lambda: AnalysisResult(spool, metadata), spool.budget, 'reserve_ram',
                               metadata.estimated_bytes(), after=after)
            self.assertTrue(spool._closed)
            self.assertEqual(spool.budget.ram_bytes, 8192)

    def test_analysis_metadata_constructor_persistent_cleanup_exposes_top_owner(self):
        """metadata申请成功后MemoryError且持续清理取消，正式analysis恢复owner同时持有metadata与spool。

        参数: 无。返回: None。异常: 原异常身份丢失、恢复owner遗漏一层或借用费用误扣。
        """
        spool = self.spool()
        spool.seal()
        metadata = self.metadata()
        original = MemoryError('analysis-constructor')
        reserve = self.cancel_once(spool.budget.reserve_ram, amount=metadata.estimated_bytes(), after=True, error=original)
        # 非取消错误仍沿既有AnalysisError包装合同；原MemoryError必须在cause中保身份且恢复owner两处可达。
        with patch.object(spool.budget, 'reserve_ram', reserve), \
             patch.object(spool.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-cleanup')):
            with self.assertRaises(AnalysisError) as caught:
                AnalysisResult(spool, metadata)
        self.assertIs(caught.exception.__cause__, original)
        owner = getattr(original, 'analysis_result_cleanup_owner', None)
        self.assertIs(getattr(caught.exception, 'analysis_result_cleanup_owner', None), owner)
        self.assertIsInstance(owner, AnalysisResult)
        self.assertIs(owner.spool, spool)
        self.addCleanup(owner.close)
        owner.close()
        self.assertTrue(spool._closed)
        self.assertEqual(spool.budget.ram_bytes, 8192)

    def test_iterator_constructor_reserve_before_after_cancel_leaves_no_unregistered_fee(self):
        """真实reader预约前后取消，返回失败不留未登记槽位，原AnalysisResult仍可正常关闭。

        参数: 无。返回: None。异常: reader孤立或正常result被擅自关闭。
        """
        for after in (False, True):
            result = self.result()
            baseline = result.spool.budget.ram_bytes
            self.expect_cancel(result.iter_selections, result.spool.budget, 'reserve_ram',
                               result.spool.reader_cost_for('selections'), after=after)
            self.assertEqual(result.spool.budget.ram_bytes, baseline)
            self.assertFalse(result._closed)
            self.assertFalse(result._iterators)
            result.close()
            self.assertEqual(result.spool.budget.ram_bytes, 8192)

    def test_iterator_constructor_persistent_cleanup_exposes_real_reader_owner(self):
        """reader申请成功后MemoryError且持续释放取消，正式恢复owner保持原result及reader金额。

        参数: 无。返回: None。异常: 构造未返回的reader责任丢失或结果元数据被清零。
        """
        result = self.result()
        baseline = result.spool.budget.ram_bytes
        error = self.expect_cancel(result.iter_selections, result.spool.budget, 'reserve_ram',
            result.spool.reader_cost_for('selections'), after=True, persistent=True, error=MemoryError('iterator-constructor'))
        owner = getattr(error, 'row_iterator_cleanup_owner', None)
        self.assertIsInstance(owner, _RowIterator)
        self.assertIs(owner.owner, result)
        self.addCleanup(owner.close)
        owner.close()
        self.assertEqual(result.spool.budget.ram_bytes, baseline)
        self.assertFalse(result._iterators)
        result.close()
        self.assertEqual(result.spool.budget.ram_bytes, 8192)

    def test_iterator_real_handle_close_before_after_cancel_keeps_retryable_responsibility(self):
        """reader真实FD关闭前/实际关闭后取消，只有句柄与reader费用均归还才closed。

        参数: 无。返回: None。异常: 开FD丢句柄、提前退费用或已关FD重复扣账。
        """
        for after in (False, True):
            result = self.result()
            baseline = result.spool.budget.ram_bytes
            iterator = result.iter_selections()
            actual_handle = iterator.handle
            error = KeyboardInterrupt('iterator-fd-close')
            iterator.handle = CancelClosingHandle(actual_handle, after, error)
            # 仅包装已打开的同一FD；before仍打开，after实际已关闭，两种都通过真实close重试。
            with self.assertRaises(KeyboardInterrupt) as caught:
                iterator.close()
            self.assertIs(caught.exception, error)
            self.assertEqual(actual_handle.closed, after)
            if not actual_handle.closed:
                self.assertFalse(iterator.closed)
                self.assertGreater(result.spool.budget.ram_bytes, baseline)
            iterator.close()
            iterator.close()
            self.assertTrue(actual_handle.closed)
            self.assertEqual(result.spool.budget.ram_bytes, baseline)
            self.assertFalse(result._iterators)
            result.close()

    def test_iterator_reader_release_before_after_cancel_closes_fd_and_retries_exactly(self):
        """实际reader句柄先关闭，槽位释放前后取消；closed不封死尚未抵销的金额。

        参数: 无。返回: None。异常: reader成功后重复归还或释放前不能重试。
        """
        for after in (False, True):
            result = self.result()
            baseline = result.spool.budget.ram_bytes
            iterator = result.iter_selections()
            handle = iterator.handle
            self.expect_cancel(iterator.close, result.spool.budget, 'release_ram', result.spool.reader_cost_for('selections'), after=after)
            self.assertTrue(handle.closed)
            if result.spool.budget.ram_bytes > baseline:
                self.assertFalse(iterator.closed)
            iterator.close()
            iterator.close()
            self.assertEqual(result.spool.budget.ram_bytes, baseline)
            self.assertFalse(result._iterators)
            result.close()

    def test_result_metadata_close_release_before_after_also_closes_actual_reader(self):
        """active reader与metadata、spool依次真实关闭，metadata释放前后取消不丢剩余责任。

        参数: 无。返回: None。异常: closed提前封死metadata或实际FD未关闭。
        """
        for after in (False, True):
            result = self.result()
            iterator = result.iter_selections()
            handle = iterator.handle
            cost = result._metadata_cost
            self.expect_cancel(result.close, result.spool.budget, 'release_ram', cost, after=after)
            self.assertTrue(handle.closed)
            if result.spool.budget.ram_bytes > 8192:
                self.assertFalse(result._closed)
            result.close()
            result.close()
            self.assertTrue(result.spool._closed)
            self.assertEqual(result.spool.budget.ram_bytes, 8192)
            with self.assertRaises(ResultClosedError):
                result.iter_selections()

    def test_writer_reserve_and_final_release_before_after_cancel_close_all_actual_fds(self):
        """真实发布writer申请与最终释放前后取消，所有表/质量/manifest/reader FD关闭且费用可恢复。

        参数: 无。返回: None。异常: writer费用失去责任、文件句柄残留或原取消身份改变。
        """
        for method in ('reserve_ram', 'release_ram'):
            for after in (False, True):
                result = self.result()
                handles = []
                destination = self.work / ('publish-' + uuid4().hex)
                # 三表reader现用各自实长，writer仍用原全局金额；明确排除金额碰撞后只命中writer。
                self.assertTrue(all(result.spool.reader_cost_for(table) != result.spool.reader_cost
                                    for table in result.spool.tables))
                call = 1
                with patch.object(Path, 'open', self.tracked_open(handles)):
                    self.expect_cancel(lambda: result.write(destination), result.spool.budget, method,
                                       result.spool.reader_cost, after=after, call=call)
                self.assertTrue(all(handle.closed for handle in handles))
                result.close()
                self.assertEqual(result.spool.budget.ram_bytes, 8192)

    def test_normal_typed_small_buffer_order_parent_schema_and_independent_readers(self):
        """小缓冲排序与两个独立reader正常往返，UINT64/UNKNOWN/显式event父及原schema保持。

        参数: 无。返回: None。异常: 生命周期修复改了排序、typed事实、父ID或JSONL协议。
        """
        spool = self.spool(buffer_rows=1)
        event_a, event_b = fixtures.summary_event_row(0, 10), fixtures.summary_event_row(1, 1)
        calculation = fixtures.summary_selection_row(2, unknown=True)
        calculation = replace(calculation, scope='event', parent_id=event_a.event_id)
        for row in (event_a, event_b, calculation):
            spool.append(row)
        spool.seal()
        self.assertEqual(spool.peak_buffer_rows, 1)
        result = AnalysisResult(spool, self.metadata())
        self.addCleanup(result.close)
        baseline = spool.budget.ram_bytes
        first, second = result.iter_events(), result.iter_events()
        self.assertEqual(next(first), event_b)
        self.assertEqual(next(second), event_b)
        self.assertEqual(next(first), event_a)
        first.close()
        second.close()
        self.assertEqual(tuple(result.iter_selections()), (calculation,))
        self.assertEqual(spool.budget.ram_bytes, baseline)
        self.assertFalse(result._iterators)
        result.close()
        self.assertTrue(all(path.exists() for path in spool.files.values()))
        self.assertEqual(spool.budget.ram_bytes, 8192)
