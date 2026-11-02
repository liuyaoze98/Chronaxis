"""用真实Scan/history/FD与共享预算验证解码绑定工厂的取消和可重试关闭。

输入为独立memory/CSV小计划，真实读取后封存历史；外部reader与调用方1MiB标记
持续存活。专项只在单笔实际reserve/release、真正历史文件read/close、reader登记
或最终DecodedBindings构造位置注入原异常，不能用手造半初始化owner代替真实资源。
工厂须保原异常/取消对象，持续清理失败交出最高decoded_binding_lease_cleanup_owner；
恢复同一对象close后回借用基线。释放后取消已经完成的交易不得再次归还费用，
释放前/FD关闭前的持续失败至少实际命中三次再恢复。正常固定金额、指纹和真实EOF
仍保持原合同；来源/scan/history/外部FD不归lease关闭。所有合成产物保存在home
work，不修改旧测试或Ref，不以本专项代表其他层持续清理风险或RSS已经解决。
"""

from configuration_fixtures import current_fixture

# 原生产资源保持真实对象；故障包装只改变本reader的文件动作，不生成历史记录。
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis import AnalysisPlan
from chronaxis.execution import bindings as module
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.history import DecodedHistoryStore, _metadata_bytes
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.observed_ingestion import ObservedSourceScan
from chronaxis.results import ResourceBudget, ResultClosedError
from chronaxis.sources import ReadRequest


class FaultHandle:
    """借真实文件对象注入本reader的read/close错误，closed始终反映实际FD。

    close_error为None即可恢复；after=True表示先真正关闭文件再抛错，不能把已关FD
    当作仍需重复执行的外部动作。外部独立reader从不使用本包装。
    """

    def __init__(self, handle, *, read_error=None, close_error=None, after=False):
        """保存真实FD和注入点。参数: 原handle/原异常/after。返回: 包装。异常: 无。"""
        self.handle, self.read_error, self.close_error, self.after = handle, read_error, close_error, after
        self.close_calls = 0

    @property
    def closed(self):
        """读取物理文件状态。参数: 无。返回: bool。异常: 无。"""
        return self.handle.closed

    def readline(self, size):
        """执行真实读或抛原主错。参数: 原限长size。返回: bytes。异常: read_error或原IO错误。"""
        if self.read_error is not None:
            raise self.read_error
        return self.handle.readline(size)

    def close(self):
        """执行真实文件关闭前/后注入。参数: 无。返回: None。异常: close_error或原IO错误。"""
        self.close_calls += 1
        if self.close_error is not None and not self.after:
            raise self.close_error
        self.handle.close()
        if self.close_error is not None:
            raise self.close_error


class RejectReaderRegistration(set):
    """保留已有外部reader，拒绝新reader.add，discard和后续清理仍是真实集合操作。"""

    def __init__(self, values, primary):
        """复制有限实际登记。参数: 当前集合/原主错。返回: 故障集合。异常: 原分配错误。"""
        super().__init__(values)
        self.primary = primary

    def add(self, value):
        """在真实新FD已打开后拒绝登记。参数: 实际reader。返回: 无。异常: primary原对象。"""
        raise self.primary


class DecodedBindingRecoveryTests(unittest.TestCase):
    """每例独立资源树；最高lease只清本次固定费和真实child，不关闭借用输入。"""

    def fixture(self, *, kind='memory', backend='reference'):
        """建立完整真实Scan/history并保持一个外部reader活跃。

        参数: kind为memory/csv；backend为reference/numpy。返回: 实际资源/基线命名空间。
        异常: 真计划、IO或扫描错误传播。副作用: 只写独立home合成work，注册最终清理。
        """
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/decoded-binding-recovery' / uuid4().hex
        work.mkdir(parents=True)
        source = dict(name='table', source_type='memory' if kind == 'memory' else 'signal_csv',
            time=dict(time_type='relative', unit='ns', origin='binding-recovery-home'))
        if kind == 'memory':
            source['rows'] = [dict(time=str(time)+'ns', values={'v': value}) for time, value in ((0, 2), (5, 4))]
        else:
            path = work / 'input.csv'
            path.write_text('ns,v\n0,2\n5,4\n', encoding='utf-8', newline='')
            source.update(path=path.name, time_column='ns')
        plan = AnalysisPlan.from_dict(current_fixture(dict(config_version=3,
            dataset=dict(name='recovery', entity='synthetic', session='session', domain=dict(start='0ns', end='8ns')),
            sources=[source], signals=[dict(name='value', source='table', field='v', dtype='float64', unit='1', valid_for='10ns')],
            metadata=dict(device_label='home', data_kind='synthetic'))), base_dir=work)
        budget = ResourceBudget(64*1024**2)
        self.addCleanup(self.assert_zero, budget)
        budget.reserve_ram(1024*1024)
        self.addCleanup(self.return_marker, budget)
        adapter_type = BudgetedMemorySourceAdapter if kind == 'memory' else BudgetedSignalCSVSourceAdapter
        adapter = adapter_type(budget, plan.sources[0].config, 'session',
            tuple(item.definition for item in plan.signals), backend=backend)
        self.addCleanup(adapter.close)
        request = ReadRequest('session', ('value',), 0, 8, 2)
        history = DecodedHistoryStore(budget, work/'history', (adapter.describe(),), {'table': request})
        self.addCleanup(history.close)
        scan = ObservedSourceScan(history, plan.sources[0], adapter, request)
        self.addCleanup(scan.close)
        scan.consume()
        history.seal()
        external = history.iter_records('table')
        self.addCleanup(external.close)
        # 金额完全沿原固定公式，不能把reader费用合入父_cost或用余额差替孩子抵账。
        fee = 32768 + len(plan.bindings.sources)*8192 + len(plan.bindings.signals)*2048 + 16*_metadata_bytes(
            (plan.bindings, tuple((item.description, item.request) for item in history.validators.values())))
        reader_fee = history.line_limits['table']*64+8192+16384
        return SimpleNamespace(work=work, plan=plan, budget=budget, adapter=adapter, history=history,
            scan=scan, external=external, baseline=budget.ram_bytes, fee=fee, reader_fee=reader_fee)

    def assert_zero(self, budget):
        """核夹具最外层归零。参数: 共享预算。返回: None。异常: 漏费或多扣断言失败。"""
        self.assertEqual(budget.ram_bytes, 0)

    def return_marker(self, budget):
        """仅归还调用方1MiB标记。参数: 共享预算。返回: None。异常: 借用账目错误由断言报告。"""
        self.assertEqual(budget.ram_bytes, 1024*1024)
        budget.release_ram(1024*1024)

    def bind(self, data):
        """调用唯一真实工厂并登记lease清理。参数: data。返回: 真lease。异常: 原工厂错误。"""
        owner = module.bind_decoded_history(data.plan.bindings, data.history)
        self.addCleanup(owner.close)
        return owner

    def assert_borrowed(self, data, baseline=None):
        """核借用history、scan、adapter与外部真实FD可用，当前费用准确。

        参数: data及可选应有RAM。返回: None。异常: 误关或费用变化断言失败。
        """
        self.assertFalse(data.history.closed)
        self.assertFalse(data.scan.closed)
        self.assertFalse(data.external.closed)
        self.assertFalse(data.external.handle.closed)
        self.assertTrue(data.scan.finished)
        data.adapter.describe()
        self.assertEqual(data.budget.ram_bytes, data.baseline if baseline is None else baseline)

    def recovery(self, error):
        """取得原异常交出的最高实际lease。参数: 原异常。返回: 可恢复真实owner。异常: 缺失/假owner断言失败。"""
        owner = getattr(error, 'decoded_binding_lease_cleanup_owner', None)
        self.assertIs(type(owner), module.DecodedBindingLease)
        self.addCleanup(owner.close)
        self.assertFalse(owner.closed)
        # 关闭已经开始，单行引用须先于reader费用结束，不能在子关闭取消后孤立存活。
        self.assertIsNone(owner._current)
        with self.assertRaises(ResultClosedError):
            owner.bindings
        return owner

    def release_failure(self, data, amount, error, calls, *, after=False):
        """只向一笔目标金额安装持续失败，其他原交易照常执行。

        参数: data/amount/原error/calls命中列表/after。返回: 真实release包装。
        异常: 目标error原对象；不修改其他owner的账目。
        """
        actual = data.budget.release_ram

        def invoke(value):
            """记录并执行单笔目标交易前后错误。参数: bytes。返回: 原返回。异常: 指定原对象。"""
            if value == amount:
                calls.append(value)
                if after:
                    actual(value)
                raise error
            return actual(value)

        return invoke

    def test_normal_cost_identity_and_real_eof_remain_unchanged_across_sources_and_backends(self):
        """正常费用与真实EOF/SHA不随恢复接线改变。参数: 无。返回: None。异常: 正常金额/来源身份不符。"""
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                with self.subTest(kind=kind, backend=backend):
                    data = self.fixture(kind=kind, backend=backend)
                    owner = self.bind(data)
                    self.assertEqual((owner._cost, owner._held_cost), (data.fee, data.fee))
                    self.assertIsNone(owner._reader)
                    self.assertIsNone(owner._current)
                    self.assertIsNone(owner._evidence)
                    evidence = owner.bindings.sources[0]
                    self.assertEqual(evidence.history_sha256, data.scan.history_sha256)
                    self.assertEqual((evidence.progress_count, evidence.sample_count), data.scan.counts)
                    self.assertTrue(evidence.source_eof)
                    self.assertIs(owner.bindings.declarations, data.plan.bindings)
                    self.assert_borrowed(data, data.baseline+data.fee)
                    owner.close()
                    owner.close()
                    self.assertEqual((owner._cost, owner._held_cost), (0, 0))
                    self.assert_borrowed(data)

    def test_factory_reserve_before_and_after_cancel_preserves_original_and_cleans_actual_fee(self):
        """首次预约前后原取消/分配错误都保对象并回基线。参数: 无。返回: None。异常: try外漏费或主错被盖。"""
        for after in (False, True):
            for error_type in (KeyboardInterrupt, SystemExit, MemoryError):
                with self.subTest(after=after, error_type=error_type):
                    data = self.fixture()
                    primary = error_type('factory-reserve-home')
                    actual = data.budget.reserve_ram
                    reached = []

                    def reserve(value):
                        """仅命中本工厂首次固定费。参数: bytes。返回: 原返回。异常: primary原对象。"""
                        if value == data.fee and not reached:
                            reached.append(value)
                            if after:
                                actual(value)
                            raise primary
                        return actual(value)

                    with patch.object(data.budget, 'reserve_ram', side_effect=reserve):
                        with self.assertRaises(error_type) as caught:
                            self.bind(data)
                    self.assertIs(caught.exception, primary)
                    self.assertEqual(reached, [data.fee])
                    self.assert_borrowed(data)

    def test_factory_reserve_after_cancel_and_three_release_failures_hands_off_same_owner(self):
        """未返回工厂已付款时持续释放失败保最高真实owner。参数: 无。返回: None。异常: 漏owner或借用多扣。"""
        data = self.fixture()
        primary, secondary = KeyboardInterrupt('reserve-after-home'), RuntimeError('release-before-home')
        actual = data.budget.reserve_ram
        reached, calls = [], []

        def reserve(value):
            """先真正入账再原取消。参数: bytes。返回: 原返回。异常: primary。"""
            actual(value)
            reached.append(value)
            raise primary

        with patch.object(data.budget, 'reserve_ram', side_effect=reserve), patch.object(data.budget, 'release_ram',
                side_effect=self.release_failure(data, data.fee, secondary, calls)):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.bind(data)
            self.assertIs(caught.exception, primary)
            owner = self.recovery(primary)
            with self.assertRaises(RuntimeError) as retry:
                owner.close()
            self.assertIs(retry.exception, secondary)
            self.assertGreaterEqual(len(calls), 3)
            self.assertEqual(reached, [data.fee])
            self.assertEqual((owner._cost, owner._held_cost), (data.fee, data.fee))
            self.assert_borrowed(data, data.baseline+data.fee)
        owner.close()
        owner.close()
        self.assert_borrowed(data)

    def test_lease_close_before_and_after_errors_retry_without_repeating_completed_credit(self):
        """释放前持续三次可重试，释放后错误已完成一次交易不得再扣。参数: 无。返回: None。异常: double credit。"""
        for after in (False, True):
            for error_type in (KeyboardInterrupt, SystemExit, RuntimeError):
                with self.subTest(after=after, error_type=error_type):
                    data = self.fixture()
                    owner = self.bind(data)
                    primary, calls = error_type('lease-release-home'), []
                    with patch.object(data.budget, 'release_ram',
                            side_effect=self.release_failure(data, data.fee, primary, calls, after=after)):
                        with self.assertRaises(error_type) as caught:
                            owner.close()
                        self.assertIs(caught.exception, primary)
                        with self.assertRaises(ResultClosedError):
                            owner.bindings
                        if after:
                            # 槽已按真实交易清0；随后close不调用仍持续抛错的外部release。
                            self.assertEqual((owner._cost, owner._held_cost), (0, 0))
                            owner.close()
                            owner.close()
                            self.assertEqual(calls, [data.fee])
                            self.assert_borrowed(data)
                        else:
                            for _ in range(2):
                                with self.assertRaises(error_type) as retry:
                                    owner.close()
                                self.assertIs(retry.exception, primary)
                            self.assertEqual(calls, [data.fee]*3)
                            self.assertFalse(owner.closed)
                            self.assert_borrowed(data, data.baseline+data.fee)
                    owner.close()
                    self.assertTrue(owner.closed)
                    self.assert_borrowed(data)

    def test_real_reader_primary_and_persistent_child_fee_failure_preserve_highest_owner(self):
        """真实FD读取主错遇子费用持续失败仍保原对象和唯一最高lease。参数: 无。返回: None。异常: 清理副错覆盖主错。"""
        for error_type in (ValueError, KeyboardInterrupt, SystemExit):
            with self.subTest(error_type=error_type):
                data = self.fixture()
                primary, secondary, calls, readers = error_type('reader-primary-home'), RuntimeError('child-release-home'), [], []
                original = data.history.iter_records

                def records(name):
                    """在实际已打开reader上装读错FD。参数: 来源名。返回: 真reader。异常: 原构造错误。"""
                    reader = original(name)
                    reader.handle = FaultHandle(reader.handle, read_error=primary)
                    readers.append(reader)
                    return reader

                with patch.object(data.history, 'iter_records', side_effect=records), patch.object(data.budget, 'release_ram',
                        side_effect=self.release_failure(data, data.reader_fee, secondary, calls)):
                    with self.assertRaises(error_type) as caught:
                        self.bind(data)
                    self.assertIs(caught.exception, primary)
                    owner = self.recovery(primary)
                    self.assertIs(owner._reader, readers[0])
                    self.assertTrue(readers[0].handle.closed)
                    self.assertGreaterEqual(len(calls), 3)
                    self.assertTrue(any('RuntimeError' in note for note in primary.__notes__))
                    self.assert_borrowed(data, data.baseline+data.fee+data.reader_fee)
                owner.close()
                self.assertTrue(readers[0].closed)
                self.assert_borrowed(data)

    def test_real_file_close_before_persistent_failure_recovers_only_own_fd(self):
        """真实文件close前持续三次失败保留FD到同owner恢复。参数: 无。返回: None。异常: FD丢失或误关外部reader。"""
        data = self.fixture()
        primary, secondary, readers = ValueError('read-before-close-home'), RuntimeError('fd-close-before-home'), []
        original = data.history.iter_records

        def records(name):
            """保真实handle并装持续关闭前失败。参数: 来源名。返回: 真reader。异常: 原构造错误。"""
            reader = original(name)
            reader.handle = FaultHandle(reader.handle, read_error=primary, close_error=secondary)
            readers.append(reader)
            return reader

        with patch.object(data.history, 'iter_records', side_effect=records):
            with self.assertRaises(ValueError) as caught:
                self.bind(data)
        self.assertIs(caught.exception, primary)
        owner = self.recovery(primary)
        handle = readers[0].handle
        self.assertGreaterEqual(handle.close_calls, 3)
        self.assertFalse(handle.closed)
        self.assertIs(owner._reader, readers[0])
        self.assert_borrowed(data, data.baseline+data.fee+data.reader_fee)
        handle.close_error = None
        owner.close()
        self.assertTrue(handle.closed)
        self.assertTrue(owner.closed)
        self.assert_borrowed(data)

    def test_unreturned_reader_reserve_after_cancel_is_adopted_as_actual_child(self):
        """真实reader构造未返回的费用由最高lease接管，不造半初始化owner。参数: 无。返回: None。异常: 孤儿费用。"""
        data = self.fixture()
        primary, secondary = KeyboardInterrupt('child-reserve-after-home'), RuntimeError('child-release-before-home')
        actual = data.budget.reserve_ram
        reached, calls = [], []

        def reserve(value):
            """仅在实际child申请更新后取消。参数: bytes。返回: 原返回。异常: primary原对象。"""
            actual(value)
            if value == data.reader_fee:
                reached.append(value)
                raise primary

        with patch.object(data.budget, 'reserve_ram', side_effect=reserve), patch.object(data.budget, 'release_ram',
                side_effect=self.release_failure(data, data.reader_fee, secondary, calls)):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.bind(data)
            self.assertIs(caught.exception, primary)
            owner = self.recovery(primary)
            self.assertIs(owner._reader.owner, data.history)
            self.assertIsNone(owner._reader.handle)
            self.assertEqual(owner._reader.cost, data.reader_fee)
            self.assertEqual(reached, [data.reader_fee])
            self.assertGreaterEqual(len(calls), 3)
            self.assert_borrowed(data, data.baseline+data.fee+data.reader_fee)
        owner.close()
        self.assert_borrowed(data)

    def test_final_binding_model_failure_keeps_primary_when_fixed_cleanup_persists(self):
        """真EOF之后模型构造错误也保原错和固定费owner。参数: 无。返回: None。异常: 尾端构造漏费。"""
        data = self.fixture()
        primary, secondary, calls = MemoryError('binding-model-home'), SystemExit('fixed-release-home'), []
        with patch.object(module, 'DecodedBindings', side_effect=primary), patch.object(data.budget, 'release_ram',
                side_effect=self.release_failure(data, data.fee, secondary, calls)):
            with self.assertRaises(MemoryError) as caught:
                self.bind(data)
            self.assertIs(caught.exception, primary)
            owner = self.recovery(primary)
            self.assertIsNone(owner._reader)
            with self.assertRaises(SystemExit):
                owner.close()
            self.assertGreaterEqual(len(calls), 3)
            self.assert_borrowed(data, data.baseline+data.fee)
        owner.close()
        self.assert_borrowed(data)

    def test_real_file_close_after_error_keeps_read_primary_and_does_not_repeat_fd_or_credit(self):
        """真实FD已关闭后副错不能盖读主错或造成第二次费用归还。参数: 无。返回: None。异常: 主错被换或double credit。"""
        data = self.fixture()
        primary, secondary, handles = ValueError('read-primary-after-home'), KeyboardInterrupt('fd-close-after-home'), []
        original = data.history.iter_records

        def records(name):
            """让唯一真实FD先关闭再抛副错。参数: 来源名。返回: 真reader。异常: 原构造错误。"""
            reader = original(name)
            reader.handle = FaultHandle(reader.handle, read_error=primary, close_error=secondary, after=True)
            handles.append(reader.handle)
            return reader

        with patch.object(data.history, 'iter_records', side_effect=records):
            with self.assertRaises(ValueError) as caught:
                self.bind(data)
        self.assertIs(caught.exception, primary)
        self.assertEqual(len(handles), 1)
        self.assertTrue(handles[0].closed)
        self.assertEqual(handles[0].close_calls, 1)
        self.assertTrue(any('KeyboardInterrupt' in note for note in primary.__notes__))
        self.assert_borrowed(data)

    def test_real_reader_registration_failure_and_persistent_cleanup_adopts_unreturned_fd(self):
        """实际FD打开后登记失败仍从原异常接真实child，恢复不动外部reader。参数: 无。返回: None。异常: 未返回FD漏费。"""
        data = self.fixture()
        primary, secondary, calls = MemoryError('reader-registration-home'), RuntimeError('registered-child-release-home'), []
        data.history._iterators = RejectReaderRegistration(data.history._iterators, primary)
        with patch.object(data.budget, 'release_ram', side_effect=self.release_failure(data, data.reader_fee, secondary, calls)):
            with self.assertRaises(MemoryError) as caught:
                self.bind(data)
            self.assertIs(caught.exception, primary)
            owner = self.recovery(primary)
            self.assertIs(owner._reader.owner, data.history)
            self.assertTrue(owner._reader.handle.closed)
            self.assertNotIn(owner._reader, data.history._iterators)
            self.assertGreaterEqual(len(calls), 3)
            self.assert_borrowed(data, data.baseline+data.fee+data.reader_fee)
        owner.close()
        self.assert_borrowed(data)
