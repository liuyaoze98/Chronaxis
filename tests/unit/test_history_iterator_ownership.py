"""用真实新历史文件复现单来源游标预算及文件关闭动作取消。

原失败正式断言先执行，finally只回收测试产生的真实文件/旧孤儿成本，不能替产品过关。
完整EOF摘要和原0/5ns数据读取另验，不触及原日志/DBC/RefProjects。
"""

# 原工厂生成真实封存历史；模块别名防止重复发现旧测试。
import unittest
from unittest.mock import patch
import test_stream_boundaries as real_history
from chronaxis.results.errors import ResultClosedError
from chronaxis.execution.history_records import HistorySample


class CloseFaultFile:
    """借用真实只读句柄，在首次close前或成功后取消，不代为回收。"""

    def __init__(self, handle, after):
        """记录原句柄。参数: handle/after。返回: 新代理。异常: 无。"""
        self.handle, self.after, self.used = handle, after, False

    @property
    def closed(self):
        """读取实际FD状态。参数: 无。返回: bool。异常: 无。"""
        return self.handle.closed

    def close(self):
        """首次关闭动作取消。参数: 无。返回: None。异常: 唯一KeyboardInterrupt。"""
        if not self.used:
            self.used = True
            if self.after:
                self.handle.close()
            raise KeyboardInterrupt('history-file-close')
        self.handle.close()

    def __getattr__(self, name):
        """其余读取走真实文件。参数: 属性名。返回: 原属性。异常: 原错误传播。"""
        return getattr(self.handle, name)


class HistoryIteratorOwnershipTests(unittest.TestCase):
    """每项真实新历史和账本，原失败回收仅在正式断言之后。"""

    def fixture(self, **kwargs):
        """建立真实历史。参数: 原工厂输入。返回: fixture。异常: 原错误传播。"""
        factory = real_history.StreamBoundaryTests('runTest')
        factory.setUp()
        fixture = factory.prepare(**kwargs)
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        return fixture

    def cleanup_fixture(self, factory, budget):
        """核对全部原工厂关闭。参数: 工厂/预算。返回: None。异常: 漏账断言失败。"""
        self.assertTrue(factory.doCleanups())
        self.assertEqual(budget.ram_bytes, 0)

    def cancel_once(self, original, after):
        """首次预算动作前或成功后取消。参数: 原方法/after。返回: 故障函数。异常: 首次取消。"""
        used = False

        def invoke(amount):
            """执行一次目标动作。参数: bytes。返回: 原结果。异常: KeyboardInterrupt。"""
            nonlocal used
            if not used:
                used = True
                if after:
                    original(amount)
                raise KeyboardInterrupt('history-budget')
            return original(amount)

        return invoke

    def test_constructor_reserve_cancel_releases_cost_before_any_open(self):
        """申请前后取消均不打开文件，原构造孤儿成本在正式断言后才回收。

        参数: 无。返回: None。异常: 固定申请漏账或提前打开断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                fixture = self.fixture()
                budget, history = fixture.budget, fixture.history
                baseline = budget.ram_bytes
                try:
                    with patch.object(budget, 'reserve_ram', side_effect=self.cancel_once(budget.reserve_ram, after)):
                        with patch.object(type(history.paths['table']), 'open', side_effect=AssertionError('早于预算打开')) as opened:
                            with self.assertRaises(KeyboardInterrupt):
                                history.iter_records('table')
                            opened.assert_not_called()
                    self.assertEqual(budget.ram_bytes, baseline)
                    self.assertFalse(history._iterators)
                finally:
                    # 构造旧失败没有返回owner/没有FD，仅回收确已证明的孤儿账本便于工厂退出。
                    if budget.ram_bytes > baseline:
                        budget.release_ram(budget.ram_bytes - baseline)

    def check_close_cancel(self, stage):
        """检验真实FD与预算两种关闭动作的前后交接。

        参数: stage为file或ram。返回: None。
        异常: 提前closed/丢句柄/重复扣账断言失败，finally只作测试环境回收。
        """
        for after in (False, True):
            with self.subTest(stage=stage, after=after):
                fixture = self.fixture()
                budget, history = fixture.budget, fixture.history
                baseline = budget.ram_bytes
                reader = history.iter_records('table')
                handle = reader.handle
                try:
                    if stage == 'file':
                        reader.handle = CloseFaultFile(handle, after)
                        with self.assertRaises(KeyboardInterrupt):
                            reader.close()
                    else:
                        with patch.object(budget, 'release_ram', side_effect=self.cancel_once(budget.release_ram, after)):
                            with self.assertRaises(KeyboardInterrupt):
                                reader.close()
                    self.assertEqual(reader.closed, after)
                    self.assertEqual(handle.closed, after or stage == 'ram')
                    if not after:
                        self.assertGreater(budget.ram_bytes, baseline)
                        self.assertIn(reader, history._iterators)
                        with self.assertRaises(ResultClosedError):
                            next(reader)
                    reader.close()
                    reader.close()
                    self.assertTrue(handle.closed)
                    self.assertFalse(reader.verified_eof)
                    self.assertFalse(history._iterators)
                    self.assertEqual(budget.ram_bytes, baseline)
                finally:
                    # 原失败可能标closed却FD仍开/账本仍占，正式断言后保住真实测试资源。
                    handle.close()
                    reader.close()
                    if budget.ram_bytes > baseline:
                        budget.release_ram(budget.ram_bytes - baseline)

    def test_file_close_cancel_keeps_real_handle_or_finishes_once(self):
        """文件close前可重试、成功后取消完成最小释放。参数: 无。返回: None。异常: 断言失败。"""
        self.check_close_cancel('file')

    def test_budget_release_cancel_keeps_registered_retryable_cursor(self):
        """真实FD关闭后预算未抵销仍登记可重试。参数: 无。返回: None。异常: 断言失败。"""
        self.check_close_cancel('ram')

    def test_digest_open_and_partial_registration_failure_leave_no_cursor(self):
        """构造摘要/打开和部分登记失败释放新FD/申请，不改现有历史。

        参数: 无。返回: None。异常: 构造或安装孤儿成本断言失败。
        """
        from chronaxis.execution import history as module
        fixture = self.fixture()
        baseline, history = fixture.budget.ram_bytes, fixture.history
        for target, name, error in ((module, 'sha256', MemoryError('history-digest')),
                                   (type(history.paths['table']), 'open', OSError('history-open'))):
            with patch.object(target, name, side_effect=error):
                with self.assertRaises(type(error)):
                    history.iter_records('table')
            self.assertEqual(fixture.budget.ram_bytes, baseline)

        class RejectDelivery(set):
            """真实登记后取消，不替生产close资源。"""

            def add(self, reader):
                """部分安装后取消。参数: reader。返回: 无。异常: KeyboardInterrupt。"""
                super().add(reader)
                raise KeyboardInterrupt('history-register')

        original = history._iterators
        history._iterators = RejectDelivery()
        try:
            with self.assertRaises(KeyboardInterrupt):
                history.iter_records('table')
            self.assertFalse(history._iterators)
            self.assertEqual(fixture.budget.ram_bytes, baseline)
        finally:
            history._iterators = original

    def test_full_actual_eof_sequence_and_digest_stay_verified(self):
        """真实memory/CSV历史完整读到文件EOF，0/5ns顺序与原摘要证明保持。

        参数: 无。返回: None。异常: 数据读取变更或提前close伪EOF断言失败。
        """
        for kind in ('memory', 'csv'):
            fixture = self.fixture(kind=kind)
            baseline = fixture.budget.ram_bytes
            reader = fixture.history.iter_records('table')
            records = tuple(reader)
            self.assertEqual(tuple(record.time_ns for record in records if isinstance(record, HistorySample)), (0, 5))
            self.assertTrue(reader.verified_eof)
            self.assertTrue(reader.closed)
            self.assertEqual(reader.digest.hexdigest(), fixture.history.hashes['table'].hexdigest())
            self.assertFalse(fixture.history._iterators)
            self.assertEqual(fixture.budget.ram_bytes, baseline)
