"""用真实封存历史检验完整时间组游标的资源交接。

输入为两个来源在0/5整数纳秒的可核实样本，实际写入新项目work目录。
故障只注入组构造的预算、子游标安装和关闭动作，正式断言检查账本及真实FD。
finally只在正式断言之后回收旧实现留下的测试资源，不能替被测代码过关。
正常路径另核对完整同刻样本和EOF摘要，不更改原解码或归并语义。
"""

# 使用原真实历史工厂及已验单来源关闭故障替身；模块别名避免重复发现旧测试。
import unittest
from unittest.mock import patch
import test_stream_boundaries as real_history
import test_history_iterator_ownership as real_cursor
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow
from chronaxis.core.types import SignalDType
from chronaxis.execution.groups import _TimeGroupIterator
from chronaxis.results.errors import ResultClosedError


class RejectReaderInstall(list):
    """在实际子游标安装前或安装后失败；None预分配槽位允许建立。"""

    def __init__(self, values, after):
        """保存已有槽位和故障时机。

        参数: values为原读者槽位；after为是否先安装再失败。
        返回: 新列表替身。异常: 原列表分配错误。
        """
        super().__init__(values)
        self.after = after

    def append(self, reader):
        """拒绝动态追加实际读者。

        参数: reader为实际子游标。返回: 无。异常: 注入MemoryError。
        """
        # 安装后失败也必须由构造者持有清理句柄，不能只靠函数成功返回。
        if self.after:
            super().append(reader)
        raise MemoryError('group-reader-append')

    def __setitem__(self, index, reader):
        """拒绝实际读者进入预分配槽位。

        参数: index为槽位；reader为子游标或清理用None。
        返回: None。异常: 实际子游标安装时注入MemoryError。
        """
        # 清理空槽允许执行，测试不应人为阻断无资源的最小收尾。
        if reader is None:
            return super().__setitem__(index, reader)
        if self.after:
            super().__setitem__(index, reader)
        raise MemoryError('group-reader-slot')


class GroupIteratorOwnershipTests(unittest.TestCase):
    """每例独立真实双来源与共享账本，关闭重试不能丢失自有资源。"""

    def fixture(self, *, kind='memory'):
        """建立两个来源的实际历史与原工厂清理。

        参数: kind为memory或csv。返回: 含history/budget的原fixture。
        异常: 真实构造、封存或最终RAM归零断言失败。
        """
        factory = real_history.StreamBoundaryTests('runTest')
        factory.setUp()
        other = SignalDefinition('b', 'other', 'raw.b', SignalDType.FLOAT64, '1', 3)
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1)),
                'other': (MemoryRow(0, {'raw.b': 3}, 0), MemoryRow(5, {'raw.b': 4}, 1))}
        fixture = factory.prepare(definitions=(factory.a, other), rows_by_source=rows, kind=kind, size=1)
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        return fixture

    def cleanup_fixture(self, factory, budget):
        """关闭所有原工厂资源后核对实际账本。

        参数: factory为真实工厂，budget为账本。返回: None。异常: 收尾断言失败。
        """
        self.assertTrue(factory.doCleanups())
        self.assertEqual(budget.ram_bytes, 0)

    def recover_test_resources(self, history, baseline, group=None):
        """正式断言结束后回收原失败造成的测试资源。

        参数: history为当前历史；baseline为未打开游标时RAM；group可选实际组。
        返回: None。异常: 真实关闭或账本不一致传播。
        """
        # 使用父历史登记找到旧实现可能遗失的子句柄；不在任何验收断言前调用。
        for reader in tuple(history._iterators):
            reader.handle.close()
            reader.close()
        if group is not None:
            group.close()
        # 原实现构造后取消没有交付对象，或提前closed后漏账；仅为测试隔离回收。
        if history.budget.ram_bytes > baseline:
            history.budget.release_ram(history.budget.ram_bytes - baseline)

    def cancel_once(self, original, after, target=None):
        """只在目标预算动作首次执行前或成功后取消。

        参数: original为原预算方法；after为取消时机；target可选组自有金额。
        返回: 故障函数。异常: 首次目标调用抛KeyboardInterrupt。
        """
        used = False

        def invoke(amount):
            """执行可选目标动作并注入一次取消。

            参数: amount为字节数。返回: 原方法结果。异常: 唯一KeyboardInterrupt。
            """
            nonlocal used
            if not used and (target is None or amount == target):
                used = True
                if after:
                    original(amount)
                raise KeyboardInterrupt('group-budget')
            return original(amount)

        return invoke

    def test_constructor_cancel_never_opens_child_or_leaks_state(self):
        """构造申请前后取消均不得打开子游标或泄漏组固定预算。

        参数: 无。返回: None。异常: 原reserve成功后取消的漏账断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                fixture = self.fixture()
                budget, history = fixture.budget, fixture.history
                baseline = budget.ram_bytes
                try:
                    with patch.object(budget, 'reserve_ram', side_effect=self.cancel_once(budget.reserve_ram, after)):
                        with patch.object(history, 'iter_records', side_effect=AssertionError('申请前打开子游标')) as opened:
                            with self.assertRaises(KeyboardInterrupt):
                                history.iter_groups()
                            opened.assert_not_called()
                    self.assertEqual(budget.ram_bytes, baseline)
                    self.assertFalse(history._groups)
                    self.assertFalse(history._iterators)
                finally:
                    self.recover_test_resources(history, baseline)

    def test_child_install_failure_closes_uninstalled_actual_reader(self):
        """子游标安装前后分配失败，构造者仍须关闭新打开的真实子句柄。

        参数: 无。返回: None。异常: 子游标或预算遗留断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                fixture = self.fixture()
                baseline, history = fixture.budget.ram_bytes, fixture.history

                class RejectInstallation(_TimeGroupIterator):
                    """在字段创建时装入列表替身，不在callee求值途中换列表。"""

                    def __setattr__(self, name, value):
                        """仅包装读者槽位字段，保留所有实际组行为。

                        参数: name/value为原赋值。返回: None。异常: 原安装错误传播。
                        """
                        if name == 'readers':
                            value = RejectReaderInstall(value, after)
                        super().__setattr__(name, value)

                try:
                    with self.assertRaises(MemoryError):
                        RejectInstallation(history)
                    self.assertFalse(history._iterators)
                    self.assertFalse(history._groups)
                    self.assertEqual(fixture.budget.ram_bytes, baseline)
                finally:
                    self.recover_test_resources(history, baseline)

    def test_group_budget_close_cancel_retains_retry_or_finishes_once(self):
        """空游标及持有完整组时，组扣账前取消可重试，扣账后只最小关闭。

        参数: 无。返回: None。异常: 提前closed、登记丢失或重复扣账断言失败。
        """
        for retained in (False, True):
            for after in (False, True):
                with self.subTest(retained=retained, after=after):
                    fixture = self.fixture()
                    budget, history = fixture.budget, fixture.history
                    baseline = budget.ram_bytes
                    group = history.iter_groups()
                    if retained:
                        self.assertEqual(next(group).time_ns, 0)
                    cost = group._state_cost + group._group_cost
                    try:
                        with patch.object(budget, 'release_ram', side_effect=self.cancel_once(budget.release_ram, after, cost)):
                            with self.assertRaises(KeyboardInterrupt):
                                group.close()
                        self.assertEqual(group.closed, after)
                        if after:
                            self.assertEqual(group._state_cost + group._group_cost, 0)
                        else:
                            self.assertIn(group, history._groups)
                            self.assertGreater(budget.ram_bytes, baseline)
                            with self.assertRaises(ResultClosedError):
                                next(group)
                        group.close()
                        group.close()
                        self.assertFalse(history._groups)
                        self.assertFalse(history._iterators)
                        self.assertEqual(budget.ram_bytes, baseline)
                    finally:
                        self.recover_test_resources(history, baseline, group)

    def test_child_file_close_cancel_keeps_group_ownership_until_actual_close(self):
        """真实子FD关闭前取消保留组及子资源，关闭后取消完成组最小收尾。

        参数: 无。返回: None。异常: 丢失真实句柄、组登记或预算断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                fixture = self.fixture()
                budget, history = fixture.budget, fixture.history
                baseline = budget.ram_bytes
                group = history.iter_groups()
                readers = tuple(group.readers)
                handle = readers[0].handle
                readers[0].handle = real_cursor.CloseFaultFile(handle, after)
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        group.close()
                    self.assertEqual(handle.closed, after)
                    self.assertTrue(readers[1].closed)
                    self.assertEqual(group.closed, after)
                    if not after:
                        self.assertIn(group, history._groups)
                        self.assertIn(readers[0], group.readers)
                        with self.assertRaises(ResultClosedError):
                            next(group)
                    group.close()
                    group.close()
                    self.assertTrue(all(reader.handle.closed for reader in readers))
                    self.assertFalse(history._groups)
                    self.assertFalse(history._iterators)
                    self.assertEqual(budget.ram_bytes, baseline)
                finally:
                    self.recover_test_resources(history, baseline, group)

    def test_normal_multisource_groups_keep_actual_eof_and_digest(self):
        """两真实来源跨批同刻组保留0/5纳秒与原来源/序号/最终摘要。

        参数: 无。返回: None。异常: 样本归并、摘要或资源变化断言失败。
        """
        for kind in ('memory', 'csv'):
            with self.subTest(kind=kind):
                fixture = self.fixture(kind=kind)
                history, budget = fixture.history, fixture.budget
                baseline = budget.ram_bytes
                group = history.iter_groups()
                readers = tuple(group.readers)
                result = tuple(group)
                self.assertEqual(tuple(item.time_ns for item in result), (0, 5))
                self.assertTrue(all(s.value.valid for item in result for s in item.samples))
                self.assertEqual(tuple(tuple((s.name, s.sequence, s.value.value) for s in item.samples) for item in result),
                                 ((('b', 0, 3.0), ('a', 0, 1.0)), (('b', 1, 4.0), ('a', 1, 2.0))))
                self.assertTrue(all(reader.verified_eof and reader.closed for reader in readers))
                self.assertEqual(tuple(reader.digest.hexdigest() for reader in readers),
                                 tuple(history.hashes[reader.source].hexdigest() for reader in readers))
                self.assertTrue(group.closed)
                self.assertFalse(history._groups)
                self.assertFalse(history._iterators)
                self.assertEqual(budget.ram_bytes, baseline)
