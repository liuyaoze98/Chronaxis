"""验证当前结果编码工作区与缓冲按真实生命周期计费。

输入使用当前手写贡献、缺值和汇总；不读真实CAN或保存旧完整结果。
输出为真实spool、排序文件、严格公共回读及资源断言。完整编码预付仍在原峰值中，
缓冲费用保留至实际清理。取消前后、持续清理失败和另一owner
的借款均实际入账；保留原异常traceback并用弱引用检查模型没有被本层挂住。
全部文件留在work合成测试目录，device_label为home；不修改历史材料或用户配置。
"""

import gc
from sys import getsizeof
import unittest
from unittest.mock import patch
import weakref

import result_test_fixture as current_fixtures
import test_results as ordinary_fixtures
from chronaxis.results import ResourceBudget, ResultFormatError
from chronaxis.results.codec import encode_row, decode_row, estimate_row_bytes
from chronaxis.results.rows import row_sort_key
from chronaxis.results import spool as spool_module
from chronaxis.results.spool import ResultSpool


class ResultBufferBudgetTests(unittest.TestCase):
    """真实共享账本保留333字节借款，各例只从实际spool归还自有费用。"""

    def setUp(self):
        """建立手写事实和独立目录。参数: 无。返回: None。异常: 原目录/模型错误。"""
        self.fixture = current_fixtures.ResultFixture()
        self.fixture.setUp()

    def tearDown(self):
        """关闭真实owner后核对借款未动。参数: 无。返回: None。异常: 漏账/关闭失败。"""
        self.fixture.tearDown()

    def spool(self, name, *, rows=512, contributions=True):
        """创建256MiB账本和固定有限行数暂存，使用实际借款及owner清单。

        参数: name为本例目录，rows为缓冲上限，contributions选择可选表。返回: ResultSpool。
        异常: 原目录/预算错误；成功交付的owner由tearDown关闭。
        """
        budget = ResourceBudget(256 * 1024**2)
        budget.reserve_ram(333)
        self.fixture.budgets.append(budget)
        spool = ResultSpool(budget, self.fixture.root / name, rows, enable_contributions=contributions)
        self.fixture.owners.append(spool)
        return spool

    def test_complete_encoding_is_prepaid_and_buffer_has_only_bytes_and_key(self):
        """编码前已付完整估算；缓冲仅持当前字节和键，不保原模型或索引。"""
        spool = self.spool('prepaid')
        row = self.fixture.contribution()
        reference, cost = weakref.ref(row), estimate_row_bytes(row)
        expected, seen = encode_row(row, spool.max_row_bytes), []
        actual_encode = spool_module.encode_row

        def checked_encode(value, maximum):
            """透明观察真实预付。参数: 行/上界。返回: bytes。异常: 原编码错。"""
            try:
                seen.append((spool._pending_cost, spool.budget.ram_bytes))
                return actual_encode(value, maximum)
            finally:
                value = None

        with patch.object(spool_module, 'encode_row', checked_encode):
            spool.append(row)
        del row
        gc.collect()
        self.assertIsNone(reference())
        self.assertEqual(seen, [(cost, 333 + 4096 + cost)])
        key, payload, retained = spool._buffer[0]
        self.assertEqual(payload, expected)
        self.assertEqual((retained, spool._buffer_cost, spool._pending_cost), (cost, cost, 0))
        self.assertEqual(spool.budget.ram_bytes, 333 + 4096 + cost + spool._identity_cost)
        self.assertFalse(tuple(spool.path.glob('*.sort')))

    def test_configured_512_current_rows_flush_at_actual_limit(self):
        """256MiB下512行配置能装到511行，满512按原阈值落盘而非提前挤空生产空间。

        参数: 无。返回: None。异常: 漏行、费用不符或配置阈值改变。
        """
        spool = self.spool('512-rows')
        for sequence in range(511):
            spool.append(self.fixture.contribution(sequence, missing=sequence % 3 == 0))
        self.assertEqual(len(spool._buffer), 511)
        self.assertEqual(spool._runs['contributions'], 0)
        self.assertLess(spool._buffer_cost, 64 * 1024**2)
        self.assertEqual(spool._buffer_cost, sum(item[2] for item in spool._buffer))
        spool.append(self.fixture.contribution(511))
        self.assertEqual(spool.peak_buffer_rows, 512)
        self.assertEqual(spool._runs['contributions'], 1)
        self.assertEqual(spool._buffer, [])
        self.assertEqual(spool.budget.ram_bytes, 333 + 4096 + spool._identity_cost)
        spool.seal()
        payloads = spool.files['contributions'].read_bytes().splitlines(keepends=True)
        self.assertEqual(len(payloads), 512)
        self.assertEqual([decode_row(payload, spool.max_row_bytes).sequence for payload in payloads], list(range(512)))

    def test_current_bytes_sort_and_quality_survive_multiple_runs(self):
        """交错贡献经真实归并，字节、原顺序及缺失原因与独立排序相同。"""
        spool = self.spool('bytes-order', rows=3)
        rows = [self.fixture.contribution(index, missing=index % 3 == 0,
                calculation_id='second' if index % 2 == 0 else 'first') for index in range(8)]
        for row in rows:
            spool.append(row)
        spool.seal()
        path = spool.files['contributions']
        expected = [encode_row(row, spool.max_row_bytes) for row in sorted(rows, key=row_sort_key)]
        self.assertEqual(path.read_bytes().splitlines(keepends=True), expected)
        with path.open('rb') as data:
            for row, payload in zip(sorted(rows, key=row_sort_key), expected):
                self.assertEqual(spool._read_entry(data, spool.row_limit('contributions')), (row_sort_key(row), payload))
            self.assertIsNone(spool._read_entry(data, spool.row_limit('contributions')))
        self.assertFalse(tuple(spool.path.glob('*.sort')))

    def test_summary_retains_current_status_quality_and_original_bytes(self):
        """汇总保质量/完成状态，缓冲费用与当前行估算相同。"""
        spool = self.spool('summary')
        row = self.fixture.summary()
        expected = encode_row(row, spool.max_row_bytes)
        spool.append(row)
        self.assertEqual(spool._buffer_cost, estimate_row_bytes(row))
        spool.seal()
        self.assertEqual(spool.files['calculations'].read_bytes(), expected)
        self.assertEqual(decode_row(expected, spool.max_row_bytes), row)

    def test_event_table_keeps_current_cost_and_no_index(self):
        """默认事件表保完整估算，只保存一个结果文件。"""
        spool = self.spool('ordinary', contributions=False)
        row = ordinary_fixtures.summary_event_row()
        spool.append(row)
        self.assertEqual(spool._buffer_cost, estimate_row_bytes(row))
        self.assertEqual(len(spool._buffer[0]), 3)
        spool.seal()
        self.assertEqual(spool.files['events'].read_bytes(), encode_row(row, spool.max_row_bytes))
        self.assertFalse(tuple(spool.path.glob('*.sort')))

    def test_full_reserve_before_after_cancellation_cleans_only_own_fees(self):
        """完整编码预付前后取消都保原异常并归还实际自有费用，不侵占333借款。

        参数: 无。返回: None。异常: 未申请也抵销、成功申请后漏账或仍保留输入行。
        """
        for after in (False, True):
            with self.subTest(after=after):
                spool = self.spool('reserve-' + str(after))
                row = self.fixture.contribution()
                reference, cost = weakref.ref(row), estimate_row_bytes(row)
                reserve, error = spool.budget.reserve_ram, KeyboardInterrupt('reserve-cancel')

                def cancel(amount):
                    """仅对完整编码申请取消。参数: 实际金额。返回: None。异常: 同一取消对象。"""
                    if amount == cost:
                        if after:
                            reserve(amount)
                        raise error
                    return reserve(amount)

                captured = None
                with patch.object(spool.budget, 'reserve_ram', cancel):
                    try:
                        spool.append(row)
                    except KeyboardInterrupt as exc:
                        captured = exc
                del row
                gc.collect()
                self.assertIs(captured, error)
                self.assertIsNone(reference())
                self.assertEqual(spool.budget.ram_bytes, 333 + 4096 + spool._identity_cost)
                spool.close()
                self.assertEqual(spool.budget.ram_bytes, 333)

    def test_buffer_release_before_after_cancel_keeps_actual_cost(self):
        """缓冲释放前后取消保真实剩费，恢复只退自有金额；原行不被异常栈保活。"""
        for after in (False, True):
            with self.subTest(after=after):
                spool = self.spool('release-' + str(after))
                row = self.fixture.contribution()
                reference, cost = weakref.ref(row), estimate_row_bytes(row)
                spool.append(row)
                del row
                release, marker = spool.budget.release_ram, KeyboardInterrupt('buffer-cancel')

                def cancel(amount):
                    """实际释放前或后取消。参数: 金额。返回: 无。异常: 同marker。"""
                    self.assertEqual(amount, cost)
                    if after:
                        release(amount)
                    raise marker

                with patch.object(spool.budget, 'release_ram', cancel):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        spool._clear_buffer()
                gc.collect()
                self.assertIs(caught.exception, marker)
                self.assertIsNone(reference())
                self.assertEqual(spool._buffer, [])
                self.assertEqual(spool._buffer_cost, 0 if after else cost)
                self.assertEqual(spool.budget.ram_bytes, 333 + 4096 + spool._buffer_cost + spool._identity_cost)
                spool.close()
                self.assertEqual(spool.budget.ram_bytes, 333)

    def test_actual_write_failure_releases_buffer_and_borrowed_row(self):
        """实际写结果后报错，释放实际缓冲费，原模型不随写失败TB残留。

        参数: 无。返回: None。异常: 抵销旧编码费影响借款或吞写入原错。
        """
        spool = self.spool('write-fail', rows=1)
        row = self.fixture.contribution()
        reference, original = weakref.ref(row), OSError('actual-index-write')
        write = spool._write_bytes

        def fail_index(handle, payload):
            """保真实写入后在sort文件抛错。参数: FD/bytes。返回: None。异常: 原OSError。"""
            try:
                write(handle, payload)
                raise original
            finally:
                handle = payload = None

        captured = None
        with patch.object(spool, '_write_bytes', fail_index):
            try:
                spool.append(row)
            except OSError as exc:
                captured = exc
        del row
        gc.collect()
        self.assertIs(captured, original)
        self.assertIsNone(reference())
        self.assertEqual(spool._buffer_cost, 0)
        self.assertEqual(spool.budget.ram_bytes, 333 + 4096 + spool._identity_cost)
        self.assertGreater(spool._run_path('contributions', 0, 0).stat().st_size, 0)
