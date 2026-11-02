"""用真实结果run验证多路归并的全字节顺序、当前行顺序和共享预算责任。

输入来自当前手写活动/贡献夹具，包含缺值、大整数和交错键；
期望以原严格编码器及独立sorted生成。测试实际损坏行、注入原取消和预算
回调前后故障，检查所有实际FD关闭、原文件保留、同一owner可清理且借款不被归还。
所有文件仅写新项目work目录；不读取CAN、旧快照或执行性能测量。
"""

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

import test_results as fixtures
import result_test_fixture as current_fixtures
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.codec import encode_row
from chronaxis.results.errors import AnalysisError, BudgetExceededError, ResultFormatError
import chronaxis.results.merge_runs as merge_module
from chronaxis.results.merge_runs import merge_runs
from chronaxis.results.rows import row_sort_key
from chronaxis.results.spool import ResultSpool


class ClosingFaultHandle:
    """只包装同一个真实FD，在真实关闭前或后抛指定错误，其他操作全部透传。"""

    def __init__(self, handle, error, *, after=False):
        """保存实际FD和故障。参数: handle/error/after。返回: 代理。异常: 无。"""
        self.handle, self.error, self.after = handle, error, after
        self.calls = 0

    def __getattr__(self, name):
        """透传真实文件状态和读写。参数: name。返回: 原属性。异常: 原属性错误。"""
        return getattr(self.handle, name)

    def close(self):
        """持续关闭前故障保真实FD，关闭后故障保实际closed事实。

        参数: 无。返回: 原close返回。异常: 同一指定错误或原IO错误。
        """
        self.calls += 1
        if self.error is not None and not self.after:
            raise self.error
        result = self.handle.close()
        if self.error is not None:
            raise self.error
        return result


class ResultMergeRunsTests(unittest.TestCase):
    """每例真实共享账本保留8192调用方借款，所有暂存只释放自己的费用。"""

    def setUp(self):
        """准备独立work夹具和账本。参数: 无。返回: None。异常: 原创建错误。"""
        self.fixture = current_fixtures.ResultFixture()
        self.fixture.setUp()
        self.budget = ResourceBudget(64 * 1024**2)
        self.borrowed = 8192
        self.budget.reserve_ram(self.borrowed)
        self.owners = []

    def tearDown(self):
        """关闭实际owners后核调用方借款。参数: 无。返回: None。异常: 泄漏/错误退费断言。"""
        for owner in reversed(self.owners):
            owner.close()
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        self.budget.release_ram(self.borrowed)
        self.fixture.tearDown()

    def spool(self, name, *, rows=2):
        """建立启用当前贡献的真实暂存。参数: name/rows为目录和缓冲。返回: owner。异常: 原错误。"""
        owner = ResultSpool(self.budget, self.fixture.root / name, rows, enable_contributions=True)
        self.owners.append(owner)
        return owner

    def make_runs(self, owner, table, count, *, rows=2):
        """生成交错键的原始run。参数: owner/table/count/rows。返回: (paths,所有行)。异常: 原错误。"""
        result = []
        for sequence in range(count * rows):
            if table == 'contributions':
                row = self.fixture.contribution(sequence, missing=sequence % 3 == 0,
                    calculation_id='second' if sequence % 2 else 'first')
            else:
                row = fixtures.summary_event_row(sequence, start=(sequence * 7) % 13)
            result.append(row)
            owner.append(row)
        owner._flush()
        paths = tuple(owner._run_path(table, 0, index) for index in range(owner._runs[table]))
        self.assertEqual(len(paths), count)
        return paths, result

    def tracked_open(self, handles):
        """生成只记录真实FD的open包装。参数: handles为登记列表。返回: 函数。异常: 原IO错误。"""
        original = Path.open

        def opened(path, *args, **kwargs):
            """保实际文件及错误。参数: 原open参数。返回: 实际FD。异常: 原open错误。"""
            handle = original(path, *args, **kwargs)
            handles.append(handle)
            return handle

        return opened

    def test_multiple_routes_keep_current_bytes_order_and_disk_cost(self):
        """五路交错贡献逐字节等于独立全排序，磁盘费用等于实际JSONL输出。

        参数: 无。返回: None。异常: 丢行、排序、字节、费用或FD断言失败。
        """
        owner = self.spool('legacy-order')
        paths, rows = self.make_runs(owner, 'contributions', 5)
        originals = {path: path.read_bytes() for path in paths}
        destination = owner.path / 'merged.jsonl'
        baseline, disk_before, handles = self.budget.ram_bytes, self.budget.spool_bytes, []
        with patch.object(Path, 'open', self.tracked_open(handles)):
            merge_runs(owner, paths, destination, table='contributions')
        expected = b''.join(encode_row(row, owner.max_row_bytes) for row in sorted(rows, key=row_sort_key))
        self.assertEqual(destination.read_bytes(), expected)
        with destination.open('rb') as data:
            actual_keys = []
            while (entry := owner._read_entry(data, owner.row_limit('contributions'))) is not None:
                actual_keys.append(entry[0])
        self.assertEqual(actual_keys, [row_sort_key(row) for row in sorted(rows, key=row_sort_key)])
        self.assertTrue(handles and all(handle.closed for handle in handles))
        self.assertEqual(self.budget.ram_bytes, baseline)
        self.assertEqual(self.budget.spool_bytes - disk_before,
                         destination.stat().st_size)
        self.assertEqual({path: path.read_bytes() for path in paths}, originals)
        self.assertFalse(tuple(owner.path.glob('*.sort')))

    def test_sixty_four_routes_and_equal_keys_are_stable_by_input_route(self):
        """64路上限保完整字节；相等键不按payload内容重排，而按输入路序稳定输出。

        参数: 无。返回: None。异常: 上限被误拒或相等键重排导致断言失败。
        """
        owner = self.spool('stable-64', rows=1)
        paths, _ = self.make_runs(owner, 'events', 64, rows=1)
        expected = []
        # 保合法且同长的完整行，但使用逆字典序触发文本，区别稳定路序和payload字节序。
        for index, path in enumerate(paths):
            row = replace(fixtures.summary_event_row(0, 5), trigger=f'route{63-index:02d}')
            payload = encode_row(row, owner.max_row_bytes)
            self.assertLessEqual(len(payload), owner.row_limit('events'))
            path.write_bytes(payload)
            expected.append(payload)
        destination = owner.path / 'stable.jsonl'
        merge_runs(owner, paths, destination, table='events')
        self.assertEqual(destination.read_bytes(), b''.join(expected))
        self.assertFalse(destination.with_suffix('.sort').exists())

    def test_corruption_and_reversed_keys_in_any_route_are_rejected(self):
        """任一路类型/字段/完整换行损坏及行键倒序必须拒绝，不宣称检测合法值篡改。

        参数: 无。返回: None。异常: 损坏未拒、实际FD泄漏或费用被错误清零。
        """
        for kind in ('invalid_json', 'missing_newline', 'unknown_field', 'reversed_rows'):
            with self.subTest(kind=kind):
                owner = self.spool('bad-' + kind)
                paths, _ = self.make_runs(owner, 'contributions', 3)
                bad = paths[-1]
                original = bad.read_bytes()
                if kind == 'invalid_json':
                    bad.write_bytes(original.replace(b'400.0', b'false'))
                elif kind == 'missing_newline':
                    bad.write_bytes(original.rstrip(b'\n'))
                elif kind == 'unknown_field':
                    bad.write_bytes(original.replace(b'"quality"', b'"qualitx"'))
                else:
                    bad.write_bytes(b''.join(reversed(original.splitlines(keepends=True))))
                baseline, handles = self.budget.ram_bytes, []
                with patch.object(Path, 'open', self.tracked_open(handles)):
                    with self.assertRaises(ResultFormatError):
                        merge_runs(owner, paths, owner.path / 'failed.jsonl', table='contributions')
                self.assertEqual(owner._merge_cost, 0)
                self.assertEqual(self.budget.ram_bytes, baseline)
                self.assertTrue(all(handle.closed for handle in handles))
                self.assertTrue(all(path.exists() for path in paths))

    def test_empty_runs_read_eof_and_write_one_empty_file(self):
        """全空输入仍打开每个真实run，最终创建一个空JSONL。

        参数: 无。返回: None。异常: 空表流程失败或未创建空输出。
        """
        owner = self.spool('empty')
        paths = tuple(owner.path / f'empty-{index}.jsonl' for index in range(3))
        for path in paths:
            path.touch()
        destination = owner.path / 'empty-merged.jsonl'
        merge_runs(owner, paths, destination, table='contributions')
        self.assertEqual(destination.read_bytes(), b'')
        self.assertFalse(destination.with_suffix('.sort').exists())

    def test_budget_rejection_happens_before_files_open_or_destination_creation(self):
        """不足完整多路费用时不打开任何run，也不借用另一owner的余额。

        参数: 无。返回: None。异常: 未预付分配、残留输出或共享预算断言失败。
        """
        owner, other = self.spool('budget'), self.spool('other')
        paths, _ = self.make_runs(owner, 'events', 3)
        cost = len(paths) * owner.reader_cost_for('events') + 65536 + 1024 * len(paths)
        loan = self.budget.memory_budget_bytes - self.budget.ram_bytes - cost + 1
        self.budget.reserve_ram(loan)
        baseline, handles = self.budget.ram_bytes, []
        destination = owner.path / 'not-created.jsonl'
        try:
            with patch.object(Path, 'open', self.tracked_open(handles)):
                with self.assertRaises(BudgetExceededError):
                    merge_runs(owner, paths, destination, table='events')
            self.assertFalse(handles)
            self.assertFalse(destination.exists())
            self.assertEqual(self.budget.ram_bytes, baseline)
            self.assertFalse(other._closed)
        finally:
            self.budget.release_ram(loan)

    def test_write_after_cancel_keeps_same_error_and_closes_every_actual_file(self):
        """真实写入后取消保原KI对象，清费用/FD但保所有输入和部分输出。

        参数: 无。返回: None。异常: 原错误被替换、FD泄漏或错误退共享费用。
        """
        owner = self.spool('write-cancel')
        paths, _ = self.make_runs(owner, 'contributions', 3)
        baseline, handles = self.budget.ram_bytes, []
        primary = KeyboardInterrupt('after actual merge index write')
        original = owner._write_bytes

        def cancelled(handle, payload):
            """实际写结果后抛同一取消。参数: 原handle/payload。返回: None。异常: 同primary。"""
            original(handle, payload)
            raise primary

        destination = owner.path / 'partial.jsonl'
        with patch.object(Path, 'open', self.tracked_open(handles)), patch.object(owner, '_write_bytes', cancelled):
            with self.assertRaises(KeyboardInterrupt) as caught:
                merge_runs(owner, paths, destination, table='contributions')
        self.assertIs(caught.exception, primary)
        self.assertTrue(destination.exists())
        self.assertTrue(all(path.exists() for path in paths))
        self.assertTrue(handles and all(handle.closed for handle in handles))
        self.assertEqual(self.budget.ram_bytes, baseline)
        self.assertEqual(owner._merge_cost, 0)

    def test_reserve_and_release_after_cancel_preserve_actual_ownership(self):
        """预算回调实际更新后抛KI仍只退本次费用，不重复抵销借款和其他owner。

        参数: 无。返回: None。异常: 原取消身份或实际费用记录不符。
        """
        for method in ('reserve_ram', 'release_ram'):
            with self.subTest(method=method):
                owner = self.spool('cancel-' + method)
                paths, _ = self.make_runs(owner, 'events', 3)
                baseline = self.budget.ram_bytes
                primary = KeyboardInterrupt(method + ' after actual ledger update')
                original = getattr(self.budget, method)
                fired = []

                def cancelled(amount):
                    """先更新真实账本再抛一次取消。参数: bytes。返回: 原返回。异常: 同primary。"""
                    result = original(amount)
                    if not fired:
                        fired.append(amount)
                        raise primary
                    return result

                with patch.object(self.budget, method, cancelled):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        merge_runs(owner, paths, owner.path / 'output.jsonl', table='events')
                self.assertIs(caught.exception, primary)
                self.assertEqual(owner._merge_cost, 0)
                self.assertEqual(self.budget.ram_bytes, baseline)

    def test_primary_io_error_survives_persistent_release_failure_until_owner_close(self):
        """业务错误优先，持续退费失败保同一owner实际金额，恢复后close只释放自有费用。

        参数: 无。返回: None。异常: 主错被替换、提前清槽或错误退借款。
        """
        owner, other = self.spool('persistent'), self.spool('persistent-other')
        paths, _ = self.make_runs(owner, 'events', 3)
        baseline = self.budget.ram_bytes
        primary, cleanup = OSError('controlled merge write failure'), KeyboardInterrupt('persistent release')
        with patch.object(owner, '_write_bytes', side_effect=primary), \
                patch.object(self.budget, 'release_ram', side_effect=cleanup):
            with self.assertRaises(OSError) as caught:
                merge_runs(owner, paths, owner.path / 'failed.jsonl', table='events')
        self.assertIs(caught.exception, primary)
        self.assertGreater(owner._merge_cost, 0)
        self.assertEqual(self.budget.ram_bytes, baseline + owner._merge_cost)
        self.assertTrue(any('清理' in note for note in primary.__notes__))
        with self.assertRaises(AnalysisError):
            merge_runs(owner, paths, owner.path / 'forbidden.jsonl', table='events')
        own_fixed = owner._fixed_cost + owner._identity_cost
        owner.close()
        self.assertEqual(self.budget.ram_bytes, baseline - own_fixed)
        self.assertFalse(other._closed)

    def test_persistent_actual_file_close_keeps_resources_and_fee_until_same_owner_recovers(self):
        """输入或输出持续关不掉时保实际FD/费用，恢复后同一spool.close关闭且不误退借款。

        参数: 无。返回: None。异常: FD被丢、费用提前归还、同owner无法恢复或原错误被替换。
        """
        for location in ('input', 'output'):
            with self.subTest(location=location):
                owner, other = self.spool('close-' + location), self.spool('other-' + location)
                paths, _ = self.make_runs(owner, 'contributions', 3)
                destination, baseline = owner.path / 'output.jsonl', self.budget.ram_bytes
                target = {'input': paths[1], 'output': destination}[location]
                primary, wrappers = KeyboardInterrupt('persistent actual close ' + location), []
                original = Path.open

                def opened(path, *args, **kwargs):
                    """只在目标真实FD注入持续close故障。参数: 原open参数。返回: FD/代理。异常: 原IO。"""
                    handle = original(path, *args, **kwargs)
                    if path == target:
                        handle = ClosingFaultHandle(handle, primary)
                        wrappers.append(handle)
                    return handle

                with patch.object(Path, 'open', opened):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        merge_runs(owner, paths, destination, table='contributions')
                self.assertIs(caught.exception, primary)
                resources = primary.result_merge_cleanup_owner
                self.assertIs(resources, owner._merge_run_resources)
                self.assertGreater(owner._merge_cost, 0)
                self.assertEqual(self.budget.ram_bytes, baseline + owner._merge_cost)
                self.assertFalse(wrappers[0].closed)
                for _ in range(2):
                    with self.assertRaises(KeyboardInterrupt) as repeated:
                        owner.close()
                    self.assertIs(repeated.exception, primary)
                    self.assertFalse(owner._closed)
                    self.assertIs(owner._merge_run_resources, resources)
                # 只解除故障，仍由实际owner完成关闭，不手动清零账本或另造恢复对象。
                wrappers[0].error = None
                own_fixed = owner._fixed_cost + owner._identity_cost
                owner.close()
                self.assertTrue(wrappers[0].closed and resources.closed and owner._closed)
                self.assertIsNone(owner._merge_run_resources)
                self.assertEqual(self.budget.ram_bytes, baseline - own_fixed)
                self.assertFalse(other._closed)

    def test_primary_write_error_survives_close_failure_and_close_after_cancel_is_not_double_charged(self):
        """写失败不被后续关文件失败替换；实际关闭后取消仍能清完费用且不重复抵销。

        参数: 无。返回: None。异常: 原错身份、实际句柄或预算责任不符。
        """
        for after in (False, True):
            with self.subTest(after=after):
                owner = self.spool('combined-' + str(after))
                paths, _ = self.make_runs(owner, 'events', 3)
                baseline, destination, wrappers = self.budget.ram_bytes, owner.path / 'failed.jsonl', []
                primary, cleanup = OSError('primary actual workflow failure'), KeyboardInterrupt('close failure')
                original = Path.open

                def opened(path, *args, **kwargs):
                    """透传真实FD并包装一个输入。参数: 原open参数。返回: FD/代理。异常: 原IO。"""
                    handle = original(path, *args, **kwargs)
                    if path == paths[0]:
                        handle = ClosingFaultHandle(handle, cleanup, after=after)
                        wrappers.append(handle)
                    return handle

                with patch.object(Path, 'open', opened), patch.object(owner, '_write_bytes', side_effect=primary):
                    with self.assertRaises(OSError) as caught:
                        merge_runs(owner, paths, destination, table='events')
                self.assertIs(caught.exception, primary)
                self.assertTrue(any('资源清理' in note for note in primary.__notes__))
                if after:
                    self.assertTrue(wrappers[0].closed)
                    self.assertEqual(owner._merge_cost, 0)
                    self.assertIsNone(owner._merge_run_resources)
                    self.assertEqual(self.budget.ram_bytes, baseline)
                else:
                    self.assertIs(primary.result_merge_cleanup_owner, owner._merge_run_resources)
                    self.assertIs(primary.result_spool_cleanup_owner, owner)
                    self.assertFalse(wrappers[0].closed)
                    wrappers[0].error = None
                    owner._merge_run_resources.close()
                    self.assertEqual(self.budget.ram_bytes, baseline)

    def test_single_and_two_routes_preserve_explicit_fee(self):
        """单路复制/双路入口保已验证费用，table=None继续严格读完整普通行。

        参数: 无。返回: None。异常: 输出、预算金额或已有文件被改变。
        """
        for count, table in ((1, None), (2, 'events')):
            with self.subTest(count=count, table=table):
                owner = self.spool('compat-' + str(count))
                paths, rows = self.make_runs(owner, 'events', count)
                costs, original = [], self.budget.reserve_ram

                def reserve(amount):
                    """记录真实申请金额。参数: bytes。返回: 原返回。异常: 原预算错误。"""
                    costs.append(amount)
                    return original(amount)

                with patch.object(self.budget, 'reserve_ram', reserve):
                    merge_runs(owner, paths, owner.path / 'output.jsonl', table=table)
                self.assertEqual(costs, [2 * (owner.reader_cost if table is None else owner.reader_cost_for(table))])
                self.assertEqual((owner.path / 'output.jsonl').read_bytes(),
                    b''.join(encode_row(row, owner.max_row_bytes) for row in sorted(rows, key=row_sort_key)))

    def test_registration_cancel_before_and_after_callback_keeps_actual_open_file(self):
        """真实FD已打开但ExitStack登记前后取消，责任槽仍能找回并关闭该FD。

        参数: 无。返回: None。异常: 登记缝隙导致FD丢失、原KI身份或预算不符。
        """
        for after in (False, True):
            with self.subTest(after=after):
                owner = self.spool('register-' + str(after))
                paths, _ = self.make_runs(owner, 'events', 3)
                baseline, handles = self.budget.ram_bytes, []
                primary = KeyboardInterrupt('actual FD callback registration')
                original = merge_module.ExitStack.callback

                def cancelled(stack, *args, **kwargs):
                    """在真实登记前后抛取消。参数: stack及原callback参数。返回: 无。异常: 同primary。"""
                    if after:
                        original(stack, *args, **kwargs)
                    raise primary

                with patch.object(Path, 'open', self.tracked_open(handles)), \
                        patch.object(merge_module.ExitStack, 'callback', cancelled):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        merge_runs(owner, paths, owner.path / 'unused.jsonl', table='events')
                self.assertIs(caught.exception, primary)
                self.assertEqual(len(handles), 1)
                self.assertTrue(handles[0].closed)
                self.assertIsNone(owner._merge_run_resources)
                self.assertEqual(self.budget.ram_bytes, baseline)

    def test_public_seal_failure_retains_highest_spool_owner_during_persistent_close(self):
        """公共seal遇多路输出持续关不掉，_fail不能误退费用，原异常提供同一最高spool。

        参数: 无。返回: None。异常: 错误状态、恢复owner或真实句柄/预算责任不符。
        """
        owner = self.spool('seal-close')
        self.make_runs(owner, 'contributions', 3)
        primary, wrappers, original = KeyboardInterrupt('persistent seal output close'), [], Path.open

        def opened(path, *args, **kwargs):
            """仅包装本次第一层贡献输出。参数: 原open参数。返回: 实际FD/代理。异常: 原IO。"""
            handle = original(path, *args, **kwargs)
            if path.name == 'contributions-L1-000000000000.jsonl':
                handle = ClosingFaultHandle(handle, primary)
                wrappers.append(handle)
            return handle

        with patch.object(Path, 'open', opened):
            with self.assertRaises(KeyboardInterrupt) as caught:
                owner.seal()
        self.assertIs(caught.exception, primary)
        self.assertIs(primary.result_spool_cleanup_owner, owner)
        self.assertEqual(owner.state, 'cancelled')
        self.assertGreater(owner._merge_cost, 0)
        self.assertTrue(wrappers and not wrappers[0].closed)
        wrappers[0].error = None
        owner.close()
        self.assertTrue(owner._closed and wrappers[0].closed)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_invalid_routes_and_existing_destination_never_overwrite_input(self):
        """限定路数/类型/唯一性，已有目标保原字节，失败不遗留归并费用。

        参数: 无。返回: None。异常: 非法配置被接受或输入/目标被覆盖。
        """
        owner = self.spool('invalid')
        paths, _ = self.make_runs(owner, 'events', 3)
        baseline, destination = self.budget.ram_bytes, owner.path / 'existing.jsonl'
        destination.write_bytes(b'keep-existing')
        for routes in (list(paths), (), paths * 22, (paths[0], paths[0])):
            with self.subTest(route_count=len(routes)):
                with self.assertRaises(ValueError):
                    merge_runs(owner, routes, owner.path / 'unused.jsonl', table='events')
                self.assertEqual(self.budget.ram_bytes, baseline)
        with self.assertRaises(FileExistsError):
            merge_runs(owner, paths, destination, table='events')
        self.assertEqual(destination.read_bytes(), b'keep-existing')
        self.assertEqual(self.budget.ram_bytes, baseline)


if __name__ == '__main__':
    unittest.main()
