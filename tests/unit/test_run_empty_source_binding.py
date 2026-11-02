"""验证无实际字段需求的来源只能借本history真实完成扫描补充完整时钟证明。

现场创建仅有时间列的CSV，经真实ObservedSourceScan写入同一历史并封存，再调用
bind_decoded_history的可选observed_scans。正例核两后端、空/点/多行和实际历史EOF；
负例核默认缺证明、错误完整origin/offset/input_identity、同名异history、失效或
重复scan、手造事实，以及非空需求不能以空描述进入这一补证分支。未用声明
可以保留，但不得通过实际依赖投影门禁。
真实字节摘要损坏和提前停止证明后续仍须读取物理EOF，不能只相信scan快照。
来源、scan和history由夹具拥有；绑定lease只释放自有费用，不误关借用FD。所有
有限合成产物只写work并标home，不修旧测试/默认关闭风险、不运行旧CAN链。
"""

from configuration_fixtures import current_fixture

# 负例明确替换typed声明或现场合同，不把绕过公共JSON校验的变体称为合法配置。
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis import AnalysisPlan
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType
from chronaxis.execution.bindings import bind_decoded_history
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.history_records import HistoryProgress
from chronaxis.execution.observed_ingestion import ObservedSourceScan, SourceScanObservation
from chronaxis.results import ResourceBudget, ResultClosedError, ResultFormatError
from chronaxis.sources import ReadRequest


class StopBeforeVerifiedEOF:
    """交付真实最终进度后提前终止，仍借同一个实际历史reader与FD。

    这是故障游标，不制造新记录；底层未执行物理EOF读取，verified_eof必须为False。
    """

    def __init__(self, reader):
        """保存真实reader。参数: 未耗尽历史游标。返回: 本故障包装。异常: 无。"""
        self.reader, self.saw_final = reader, False

    def __iter__(self):
        """保持本次实际位置。参数: 无。返回: self。异常: 无。"""
        return self

    def __next__(self):
        """最终进度之后故意不读物理EOF。参数: 无。返回: 原记录。异常: StopIteration/原读取错。"""
        # 标记只说明看到了source_eof声明，不能冒充文件实际EOF和完整摘要校验。
        if self.saw_final:
            self.close()
            raise StopIteration
        record = next(self.reader)
        self.saw_final = isinstance(record, HistoryProgress) and record.source_eof
        return record

    @property
    def verified_eof(self):
        """借真实核验状态。参数: 无。返回: bool。异常: 无。"""
        return self.reader.verified_eof

    def close(self):
        """仅关闭本次实际历史reader。参数: 无。返回: None。异常: 原close错误。"""
        self.reader.close()


class RunEmptySourceBindingTests(unittest.TestCase):
    """每例拥有真实输入/scan/history，独立绑定成功或失败都返回借用预算基线。"""

    def fixture(self, *, backend='reference', times=(1, 3), name='table', spare=False):
        """创建无字段CSV计划，并真实扫描到同一封存history。

        参数: backend为参考/NumPy；times为原整数ns行；name为来源名；spare=True
            在首次consume前再构造一个真实但不消费的scan，供未完成证明负例。
        返回: 真实plan/source/adapter/request/history/scan/budget/work命名空间。
        异常: 原IO、计划、扫描或封存错误传播。副作用: 仅写独立home合成work。
        """
        # 只有时间列，description.fields真的为空；不能用有字段的空投影代替本分支。
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/empty-source-binding' / uuid4().hex
        work.mkdir(parents=True)
        path = work / 'times.csv'
        path.write_text('ns\n'+''.join(str(time)+'\n' for time in times), encoding='utf-8', newline='')
        config = dict(config_version=3,
            dataset=dict(name='empty_binding', entity='synthetic', session='session', domain=dict(start='0ns', end='20ns')),
            sources=[dict(name=name, source_type='signal_csv', path=path.name, time_column='ns',
                time=dict(time_type='relative', unit='ns', origin='empty-source-home', offset='4ns'))],
            signals=[], execution=dict(backend=backend, batch_rows=2, memory_budget_bytes=256*1024**2),
            metadata=dict(device_label='home', data_kind='synthetic'))
        plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=work)
        source = plan.sources[0]
        budget = ResourceBudget(plan.execution.memory_budget_bytes)
        self.addCleanup(self.assert_zero, budget)
        # 调用方独立标记使重复扣款或误归还借用费用不会被最终0掩盖。
        budget.reserve_ram(8192)
        self.addCleanup(self.return_marker, budget)
        adapter = BudgetedSignalCSVSourceAdapter(budget, source.config, plan.dataset.session_id, (), backend=backend)
        self.addCleanup(adapter.close)
        request = ReadRequest(plan.dataset.session_id, (), 0, 20, 2)
        description = adapter.describe()
        self.assertEqual(description.fields, ())
        history = DecodedHistoryStore(budget, work / 'history', (description,), {name: request})
        self.addCleanup(history.close)
        extra = ObservedSourceScan(history, source, adapter, request) if spare else None
        if extra is not None:
            self.addCleanup(extra.close)
        scan = ObservedSourceScan(history, source, adapter, request)
        self.addCleanup(scan.close)
        scan.consume()
        history.seal()
        self.assertTrue(scan.finished)
        self.assertIs(scan.history, history)
        self.assertIs(scan.request, request)
        return SimpleNamespace(work=work, plan=plan, source=source, budget=budget, adapter=adapter,
            request=request, history=history, scan=scan, spare=extra, baseline=budget.ram_bytes, name=name)

    def assert_zero(self, budget):
        """核所有夹具最终费用为0。参数: 真实共享预算。返回: None。异常: 漏费由断言报告。"""
        self.assertEqual(budget.ram_bytes, 0)

    def return_marker(self, budget):
        """只归还调用方固定标记。参数: 真实共享预算。返回: None。异常: 借用费用不符时断言失败。"""
        self.assertEqual(budget.ram_bytes, 8192)
        budget.release_ram(8192)

    def reject(self, data, *, declarations=None, scans=None, error=ValueError, message=None):
        """核失败不修改借用层，也不漏工厂费用。

        参数: data真实夹具；declarations/scans为明确负例覆盖；error/message核异常分类。
        返回: 原捕获异常。异常: 接受无效证明、误关借用或费用变化时断言失败。
        """
        baseline = data.budget.ram_bytes
        expected = self.assertRaises(error) if message is None else self.assertRaisesRegex(error, message)
        with expected as caught:
            bind_decoded_history(data.plan.bindings if declarations is None else declarations, data.history,
                observed_scans=(data.scan,) if scans is None else scans)
        # 工厂不拥有来源、scan、history或调用方的实际reader；失败仅归还本次费用。
        self.assertEqual(data.budget.ram_bytes, baseline)
        self.assertFalse(data.history.closed)
        data.adapter.describe()
        self.assertFalse(data.history._iterators)
        return caught.exception

    def test_default_without_scan_rejects_and_true_scan_replays_actual_eof_for_empty_point_and_rows(self):
        """默认仍拒缺证明，真Scan空/点/多行逐源核物理EOF。参数: 无。返回: None。异常: 假完成或借用误关。"""
        for backend in ('reference', 'numpy'):
            for times in ((), (2,), (1, 3)):
                with self.subTest(backend=backend, times=times):
                    data = self.fixture(backend=backend, times=times)
                    self.reject(data, scans=(), message='唯一真实扫描')
                    readers = []
                    original = data.history.iter_records

                    def observe(source):
                        """交付真reader并记录其最终EOF/FD。参数: 来源名。返回: 原reader。异常: 原工厂错误。"""
                        reader = original(source)
                        readers.append(reader)
                        return reader

                    # 绑定必须仍调用真实历史回放；静态scan.hash等式不能代替实际读取。
                    with patch.object(data.history, 'iter_records', side_effect=observe):
                        lease = bind_decoded_history(data.plan.bindings, data.history, observed_scans=(data.scan,))
                    self.addCleanup(lease.close)
                    self.assertEqual(len(readers), 1)
                    self.assertTrue(readers[0].verified_eof)
                    self.assertTrue(readers[0].handle.closed)
                    evidence = lease.bindings.sources[0]
                    self.assertEqual((evidence.source, evidence.projected_aliases, evidence.sample_count), (data.name, (), 0))
                    self.assertEqual(evidence.history_sha256, data.scan.history_sha256)
                    self.assertEqual(evidence.progress_count, data.scan.counts[0])
                    self.assertTrue(evidence.source_eof)
                    self.assertEqual(data.scan.observation.row_count, len(times))
                    self.assertEqual(data.scan.observation.first_ns, times[0]+4 if times else None)
                    self.assertEqual(evidence.observation_end_ns, times[-1]+4 if times else None)
                    lease.close()
                    lease.close()
                    self.assertEqual(data.budget.ram_bytes, data.baseline)
                    self.assertFalse(data.scan.closed)
                    self.assertFalse(data.history.closed)

    def test_same_id_wrong_full_origin_offset_input_identity_and_replaced_request_reject(self):
        """同timebase_id不掩盖来源差异，值相等request也须是原对象。参数: 无。返回: None。异常: 错合同被接受。"""
        data = self.fixture()
        source = data.plan.bindings.sources[0]
        # 均为明确typed负例；原CSV、scan与history不改，只有被请求绑定的声明不同。
        alternatives = (replace(source, timebase=replace(source.timebase, origin='foreign-origin')),
            replace(source, offset_ns=source.offset_ns+1), replace(source, input_identity=source.input_identity+'-other'))
        for altered in alternatives:
            with self.subTest(altered=altered):
                declarations = replace(data.plan.bindings, sources=(altered,))
                self.reject(data, declarations=declarations, message='真实扫描.*不符')
        # 请求内容相等仍不能换成另一个对象，再借此前真实scan冒充同一次历史合同。
        copied_request = replace(data.request)
        self.assertEqual(copied_request, data.request)
        self.assertIsNot(copied_request, data.request)
        with patch.object(data.history.validators[data.name], 'request', copied_request):
            self.reject(data, message='真实扫描.*不符')

    def test_same_name_scan_from_other_history_and_unknown_source_reject(self):
        """真实同名不同history或未知来源Scan均不能借来证明本次扫描。参数: 无。返回: None。异常: 外来证明被接受。"""
        data = self.fixture()
        foreign = self.fixture()
        unknown = self.fixture(name='other')
        # 两个都真实耗尽且SHA可能相同；history对象及原request对应关系仍必须同一次。
        self.assertEqual(foreign.scan.history_sha256, data.scan.history_sha256)
        self.reject(data, scans=(foreign.scan,), message='真实扫描.*不符')
        self.reject(data, scans=(data.scan, unknown.scan), message='当前历史之外')
        self.assertFalse(foreign.scan.closed)
        self.assertFalse(unknown.scan.closed)

    def test_closed_unfinished_and_duplicate_real_scans_reject_without_closing_borrowed_owners(self):
        """模型真实也须活、完成且唯一，未consume或重复不能补证明。参数: 无。返回: None。异常: 失效Scan被接受。"""
        data = self.fixture(spare=True)
        self.assertFalse(data.spare.finished)
        self.reject(data, scans=(data.spare,), message='真实完成')
        self.assertFalse(data.spare.closed)
        self.reject(data, scans=(data.scan, data.scan), message='唯一真实扫描')
        data.scan.close()
        self.assertTrue(data.scan.finished)
        self.assertTrue(data.scan.closed)
        self.reject(data, scans=(data.scan,), message='真实完成')

    def test_handmade_observation_dict_and_mutable_container_are_not_scan_proof(self):
        """相同端点的typed事实或字典不是本history数据流证明。参数: 无。返回: None。异常: duck typing被接受。"""
        data = self.fixture()
        fact = replace(data.scan.observation)
        self.assertIs(type(fact), SourceScanObservation)
        self.assertEqual(fact, data.scan.observation)
        self.assertIsNot(fact, data.scan.observation)
        # 精确Scan类型和冻结tuple都不可省略；这些不是合法替代API。
        for scans in ((fact,), ({'observation': fact, 'finished': True},), [data.scan], (object(),)):
            with self.subTest(scans=scans):
                self.reject(data, scans=scans, error=TypeError, message='实际ObservedSourceScan tuple')

    def test_unused_declaration_needs_real_scan_and_nonempty_request_still_rejects(self):
        """未用声明可保留，但不得伪装成已读取的列。参数: 无。返回: None。异常: 缺证明/缺字段被绕过。"""
        data = self.fixture()
        signal = SignalDefinition('value', data.name, 'not_in_csv', SignalDType.FLOAT64, '1', 10)
        declarations = replace(data.plan.bindings, signals=(signal,))
        # 未用声明不强迫读取不存在的列，但仍须真scan与历史物理EOF。
        self.reject(data, declarations=declarations, scans=(), message='唯一真实扫描')
        baseline = data.budget.ram_bytes
        lease = bind_decoded_history(declarations, data.history, observed_scans=(data.scan,))
        self.addCleanup(lease.close)
        try:
            self.assertEqual(lease.bindings.sources[0].projected_aliases, ())
            self.assertTrue(lease.bindings.sources[0].source_eof)
            self.assertIs(lease.bindings.resolve('value'), signal)
            with self.assertRaisesRegex(ValueError, '未在实际解码投影'):
                lease.bindings.require_synchronized(('value',))
        finally:
            lease.close()
        self.assertEqual(data.budget.ram_bytes, baseline)
        changed = replace(data.request, signal_names=('value',))
        validator = data.history.validators[data.name]
        # 非空request是现场合同损坏负例，不伪称原空描述能合法创建这样的扫描。
        with patch.object(validator, 'request', changed):
            self.reject(data, message='读取投影必须为空')

    def test_completed_scan_does_not_replace_actual_history_sha_or_physical_eof(self):
        """scan快照相同仍须检查实际字节SHA及真实EOF，提前close不证明完成。参数: 无。返回: None。异常: 快照替代实际回放。"""
        data = self.fixture()
        path = data.history.paths[data.name]
        original_bytes = path.read_bytes()
        # 仅颠倒第一行JSON键序，保持内容与字节长度，避免误碰实际行长上限而漏核SHA。
        first, *remaining = original_bytes.splitlines(keepends=True)
        packed = json.loads(first)
        changed = (json.dumps(current_fixture(dict(reversed(tuple(packed.items())))), ensure_ascii=False,
            separators=(',', ':'))+'\n').encode('utf-8')+b''.join(remaining)
        self.assertEqual(len(changed), len(original_bytes))
        self.assertNotEqual(changed, original_bytes)
        path.write_bytes(changed)
        self.reject(data, error=ResultFormatError, message='摘要')
        path.write_bytes(original_bytes)
        readers = []
        original = data.history.iter_records

        def stop_before_eof(source):
            """返回读过真实最终进度但不核物理EOF的包装。参数: 来源名。返回: 故障游标。异常: 原工厂错误。"""
            reader = StopBeforeVerifiedEOF(original(source))
            readers.append(reader)
            return reader

        with patch.object(data.history, 'iter_records', side_effect=stop_before_eof):
            self.reject(data, error=ResultFormatError, message='实际EOF')
        self.assertEqual(len(readers), 1)
        self.assertTrue(readers[0].saw_final)
        self.assertFalse(readers[0].verified_eof)
        self.assertTrue(readers[0].reader.handle.closed)

    def test_lease_close_preserves_external_reader_actual_fd_scan_and_history(self):
        """成功lease只归还自有固定费，独立真实FD与借用层保持可用。参数: 无。返回: None。异常: 越界关闭或预算不符。"""
        data = self.fixture()
        reader = data.history.iter_records(data.name)
        self.addCleanup(reader.close)
        baseline = data.budget.ram_bytes
        lease = bind_decoded_history(data.plan.bindings, data.history, observed_scans=(data.scan,))
        self.addCleanup(lease.close)
        lease.close()
        lease.close()
        self.assertEqual(data.budget.ram_bytes, baseline)
        self.assertFalse(reader.handle.closed)
        self.assertIsInstance(next(reader), HistoryProgress)
        self.assertFalse(data.scan.closed)
        self.assertFalse(data.history.closed)
        self.assertEqual(data.scan.observation.row_count, 2)
        data.adapter.describe()
        reader.close()
        self.assertEqual(data.budget.ram_bytes, data.baseline)
        with self.assertRaises(ResultClosedError):
            lease.bindings
