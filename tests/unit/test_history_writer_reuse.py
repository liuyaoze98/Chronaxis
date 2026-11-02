"""验证历史写FD复用的字节、来源隔离和可恢复关闭责任。

输入为已有真实memory夹具和空投影批，输出为独立工作目录中的历史记录。
在真实FD上注入关闭失败、取消和磁盘配额不足，验证不覆盖旧FD、不盖原错、
不抵销其他owner借用费用；不修改RefProjects或旧CAN读写解码。
"""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.history_records import HistoryProgress, HistorySample
from chronaxis.results.errors import AnalysisError, BudgetExceededError
from chronaxis.sources.models import SignalBatch
import test_history_memory_recovery as recovery


class HistoryWriterReuseTests(unittest.TestCase):
    """每例持有独立实际资源，借用预算标记必须在测试清理前保持8192字节。"""

    def fixture(self, *, multiple=False):
        """复用既有三行memory及借用账本夹具，必要时声明第二个空投影来源。

        参数: multiple选择双来源。返回: 原fixture命名空间。
        异常: 夹具/预算/目录构造原错；登记清理保证失败测试也释放资源。
        """
        helper = recovery.HistoryMemoryRecoveryTests('runTest')
        self.addCleanup(helper.doCleanups)
        data = helper.fixture(history=True)
        if multiple:
            data.history.close()
            description = data.adapter.describe()
            store = DecodedHistoryStore(data.budget, data.work / 'multiple',
                (description, replace(description, name='other', fields=())),
                {'table': data.request, 'other': replace(data.request, signal_names=())})
            data.extra.append(store)
            data.history = store
        return data

    def empty(self, source='table', *, eof=False):
        """生成无目标信号的进度批，保持真实来源身份和显式EOF边界。

        参数: source为声明来源；eof选择最终进度。返回: SignalBatch。
        异常: typed模型不合法直接传播。
        """
        return SignalBatch(source, 'session', {}, 4 if eof else None, eof, 4 if eof else None)

    def test_empty_batches_reuse_one_fd_and_replay_all_progress_and_samples(self):
        """大量非目标报文不重复open，随后真实样本/EOF完整重放且费用不随空批增长。

        参数: 无。返回: None。异常: 重复open、丢进度/样本、未关闭或预算改变令断言失败。
        """
        data = self.fixture()
        store, original_open, opened = data.history, Path.open, []

        def tracked(path, *args, **kwargs):
            """登记数据写FD，不干预真实打开参数或其他文件。

            参数: path/args/kwargs为原打开调用。返回: 原FD。异常: 原open错误传播。
            """
            handle = original_open(path, *args, **kwargs)
            if path == store.paths['table'] and args[0] == 'ab':
                opened.append(handle)
            return handle

        baseline = data.budget.ram_bytes
        with patch.object(Path, 'open', autospec=True, side_effect=tracked):
            for _ in range(200):
                store.append(self.empty())
                self.assertEqual(data.budget.ram_bytes, baseline)
            self.assertEqual(len(opened), 1)
            self.assertIs(store._write_handle, opened[0])
            self.assertFalse(opened[0].closed)
            batches = 0
            read = data.adapter.iter_batches(data.request)
            try:
                for batch in read:
                    store.append(batch)
                    batches += 1
            finally:
                read.close()
            self.assertEqual(len(opened), 1)
        # EOF成功先关写FD，再允许封存和独立重放，不能把未结束写入当完成。
        self.assertTrue(opened[0].closed)
        self.assertIsNone(store._write_handle)
        self.assertIsNone(store._write_path)
        store.seal()
        reader = store.iter_records('table')
        records = tuple(reader)
        self.assertTrue(reader.verified_eof)
        self.assertEqual(sum(isinstance(row, HistoryProgress) for row in records), 200 + batches)
        self.assertEqual([row.array_value for row in records if isinstance(row, HistorySample)], [1., 3., 5.])
        store.close()
        self.assertEqual(data.budget.ram_bytes, 8192)

    def test_interleaved_sources_close_before_switch_and_keep_separate_histories(self):
        """交替来源最多持有一个数据写FD，切回来源仍追加到原文件且各自完整EOF。

        参数: 无。返回: None。异常: 同时开两个FD、串写或重放计数不同令断言失败。
        """
        data = self.fixture(multiple=True)
        store, handles = data.history, []
        for source in ('table', 'other', 'table'):
            previous = store._write_handle
            store.append(self.empty(source))
            if previous is not None:
                self.assertTrue(previous.closed)
            handles.append(store._write_handle)
            self.assertEqual(sum(not handle.closed for handle in handles), 1)
        for source in ('table', 'other'):
            store.append(self.empty(source, eof=True))
        self.assertTrue(all(handle.closed for handle in handles))
        store.seal()
        self.assertEqual(len(tuple(store.iter_records('table'))), 3)
        self.assertEqual(len(tuple(store.iter_records('other'))), 2)

    def test_switch_close_failure_keeps_original_fd_and_does_not_open_next_source(self):
        """切换时旧FD关不掉必须保留原责任，不以新来源覆盖它。

        参数: 无。返回: None。异常: 原取消被替换、旧FD丢失或错误创建新文件令断言失败。
        """
        data = self.fixture(multiple=True)
        store = data.history
        store.append(self.empty())
        primary = KeyboardInterrupt('persistent-switch-close')
        proxy = recovery.CloseBoundary(store._write_handle, primary)
        store._write_handle = proxy
        other_path = store.paths['other']
        with self.assertRaises(KeyboardInterrupt) as caught:
            store.append(self.empty('other'))
        self.assertIs(caught.exception, primary)
        self.assertIs(caught.exception.history_cleanup_owner, store)
        self.assertIs(store._write_handle, proxy)
        self.assertFalse(other_path.exists())
        self.assertFalse(proxy.closed)
        proxy.fail = False
        store.close()
        self.assertTrue(proxy.closed)
        self.assertEqual(data.budget.ram_bytes, 8192)

    def test_eof_close_failure_preserves_error_and_actual_fd_until_recovered(self):
        """EOF关闭前后抛普通错误或取消均不能伪报成功，持续未关FD仍由原父恢复。

        参数: 无。返回: None。异常: 主错/实际closed/费用与恢复责任不符令断言失败。
        """
        for after in (False, True):
            for primary in (OSError('eof-close-original'), KeyboardInterrupt('eof-close-cancel')):
                with self.subTest(after=after, error=type(primary).__name__):
                    data = self.fixture()
                    store = data.history
                    store.append(self.empty())
                    proxy = recovery.CloseBoundary(store._write_handle, primary, after=after)
                    store._write_handle = proxy
                    expected = AnalysisError if isinstance(primary, OSError) else KeyboardInterrupt
                    with self.assertRaises(expected) as caught:
                        store.append(self.empty(eof=True))
                    self.assertIs(caught.exception.__cause__ if isinstance(primary, OSError) else caught.exception, primary)
                    self.assertNotEqual(store.state, 'sealed')
                    if not after:
                        self.assertIs(store._write_handle, proxy)
                        self.assertIs(caught.exception.history_cleanup_owner, store)
                    else:
                        self.assertIsNone(store._write_handle)
                    proxy.fail = False
                    store.close()
                    self.assertTrue(proxy.closed)
                    self.assertEqual(data.budget.ram_bytes, 8192)

    def test_cancelled_write_on_reused_fd_keeps_original_cancel_and_closes_owner(self):
        """第二批写入取消不能因复用FD而遗留句柄或盖住取消原因。

        参数: 无。返回: None。异常: 主取消被替换、FD未关或借用费用被抵销令断言失败。
        """
        data = self.fixture()
        store = data.history
        store.append(self.empty())
        handle = store._write_handle
        primary = KeyboardInterrupt('reused-write-cancel')
        with patch.object(store, '_write_bytes', side_effect=primary):
            with self.assertRaises(KeyboardInterrupt) as caught:
                store.append(self.empty())
        self.assertIs(caught.exception, primary)
        self.assertTrue(handle.closed and store.closed)
        self.assertEqual(data.budget.ram_bytes, 8192)

    def test_spool_quota_failure_closes_retained_fd_and_preserves_partial_file(self):
        """首批写入后耗尽磁盘额度，第二批拒绝仍保部分文件且关闭复用FD。

        参数: 无。返回: None。异常: 超限后继续写、部分文件丢失或费用错误令断言失败。
        """
        data = self.fixture()
        store = data.history
        store.append(self.empty())
        handle, path = store._write_handle, store.paths['table']
        before = path.read_bytes()
        data.budget.spool_quota_bytes = data.budget.spool_bytes
        with self.assertRaises(AnalysisError) as caught:
            store.append(self.empty())
        self.assertIsInstance(caught.exception.__cause__, BudgetExceededError)
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(handle.closed and store.closed)
        self.assertEqual(data.budget.ram_bytes, 8192)


if __name__ == '__main__':
    unittest.main()
