"""用真实CAN扫描核纯消息首遍证明，与原规范历史逐字节摘要及公共运行结果对照。

每例使用独占home工作目录和手写DBC/BLF，不改历史项目。负例在实际read、预算和
合同边界注入可恢复故障，核原异常、真实EOF、最高owner及借用费用。故障注入不是
性能测量；既有公开磁盘绑定、普通计划及导出回归由对应原专项继续覆盖。
"""

from configuration_fixtures import current_fixture

from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import message_calculation_fixture as fixtures
from chronaxis import AnalysisPlan, AnalysisRunner, AnalysisError
from chronaxis.execution import scanned_signal_proof as module
from chronaxis.execution.can_batch_reader import CANBatchObservationRead
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.scanned_signal_proof import ScannedCANSignals, ScannedBindingLease
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.protocol import SourceReadError


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('can', 'cantools', 'natsort')), '缺少可选CAN依赖')
class ScannedSignalProofTests(unittest.TestCase):
    """每例拥有实际输入、扫描和可选磁盘参考，清理后共享账本仅保原借款。"""

    def setUp(self):
        """初始化独立责任列表。参数: 无。返回: None。异常: 无。"""
        self.owners, self.budgets = [], []

    def tearDown(self):
        """按子到父关闭实际owner并核借款不被抵销。参数: 无。返回: None。异常: 原清理/断言失败。"""
        for owner in reversed(self.owners):
            owner.close()
        for budget in self.budgets:
            self.assertEqual(budget.ram_bytes, 12345)
            budget.release_ram(12345)

    def fixture(self, *, backend='numpy', size=2, frames=None, unused=False, empty_definitions=False, two_sources=False):
        """从既有真实夹具派生边界输入。参数: 后端/批大小/原帧/声明控制。返回: work及原计划。异常: 原IO/模型错。"""
        import can
        work, _ = fixtures.make_scan_fixture(backend=backend)
        config = json.loads((work / 'plan.json').read_text(encoding='utf-8'))
        # 本专项刻画全声明样本的原canonical流与额外诊断；默认按需流由独立运行专项核对。
        config['sources'][0]['decode_scope'] = 'all'
        # 本内部解码刻画特意含短载荷，显式选择原宽松政策。
        config['sources'][0]['reader_options'] = {'decode_policy':'legacy'}
        config['execution']['batch_rows'] = size
        if unused:
            with (work / 'input.dbc').open('a', encoding='utf-8') as handle:
                handle.write('BO_ 258 Extra: 1 Node\n SG_ Extra : 0|8@1+ (1,0) [0|255] "V" Node\n')
            config['signals'].append(dict(name='unused', source='bus', field=dict(channel=1,
                 signal='Extra', frame_id=258, is_extended=False, is_fd=False),
                dtype='float64', unit='V', valid_for='10s'))
        if empty_definitions:
            config['signals'] = []
            config['message_calculations'][0]['expr'] = 'watts * period'
            config['message_calculations'][0]['parameters']['watts'] = dict(value=4000, unit='W')
        if two_sources:
            other = dict(config['sources'][0], name='other')
            config['sources'].append(other)
        if frames is not None:
            with can.BLFWriter(work / 'input.blf') as writer:
                for second, frame_id, payload in frames:
                    writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                        arbitration_id=frame_id, is_extended_id=False, channel=0, data=payload))
        (work / 'plan.json').write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        return work, AnalysisPlan.from_dict(current_fixture(config), base_dir=work)

    def scan(self, work, plan, *, index=0, budget=None):
        """构造尚未读取的同次完整声明扫描。参数: 原工作目录/计划/来源及可共享预算。返回: 命名空间。异常: 原错。"""
        if budget is None:
            budget = ResourceBudget(plan.execution.memory_budget_bytes)
            budget.reserve_ram(12345)
            self.budgets.append(budget)
        source = plan.sources[index]
        definitions = tuple(item.definition for item in plan.signals if item.definition.source == source.name)
        ids = tuple(sorted({item.update_message.frame_id for item in plan.message_calculations if item.source == source.name}))
        adapter = BudgetedLegacyCANSourceAdapter(budget, source.config, plan.dataset.session_id,
            definitions, backend=plan.execution.backend, work_dir=work / ('scan-' + source.name),
            batch_read=True, retain_raw_frames=False, capture_message_updates=bool(ids), message_frame_ids=ids)
        self.owners.append(adapter)
        request = ReadRequest(plan.dataset.session_id, tuple(item.name for item in definitions),
            plan.dataset.domain.start_ns, plan.dataset.domain.end_ns, plan.execution.batch_rows)
        description = adapter.describe()
        scan = ScannedCANSignals(plan.bindings, source, adapter, request)
        self.owners.append(scan)
        return SimpleNamespace(work=work, plan=plan, source=source, adapter=adapter, request=request,
            description=description, scan=scan, budget=budget)

    def lease(self, case, scans=None, descriptions=None, requests=None):
        """建立真实扫描绑定供成功与缺项测试。参数: case及可替换集合。返回: lease。异常: 原合同/预算错。"""
        value = ScannedBindingLease(case.plan, (case.scan,) if scans is None else scans,
            (case.description,) if descriptions is None else descriptions,
            {case.source.name: case.request} if requests is None else requests, case.budget)
        self.owners.append(value)
        return value

    def test_canonical_bytes_match_original_history_for_all_aliases_and_batches(self):
        """两后端、同刻多列、无效值和不同切批下摘要等于原磁盘编码。参数: 无。返回: None。异常: 原测试失败。"""
        frames = ((0, 999, b'a'), (1, 256, b'\xa0\x0f'), (1, 258, b'\x07'),
            (1, 256, b'\xd0\x07'), (2, 258, b''), (4, 999, b'z'))
        original = ScannedCANSignals._accept
        for backend in ('reference', 'numpy'):
            for size in (1, 3):
                with self.subTest(backend=backend, size=size):
                    work, plan = self.fixture(backend=backend, size=size, unused=True, frames=frames)
                    case = self.scan(work, plan)
                    history = DecodedHistoryStore(case.budget, work / 'reference-history',
                        (case.description,), {'bus': case.request})
                    self.owners.append(history)
                    def compare_append(owner, batch):
                        """同一真实批交给原编码参考，不替代新校验。参数: 原owner/batch。返回: None。异常: 原错。"""
                        history.append(batch)
                        return original(owner, batch)
                    with patch.object(ScannedCANSignals, '_accept', new=compare_append):
                        case.scan.consume()
                    history.seal()
                    raw = history.paths['bus'].read_bytes()
                    facts = case.scan.facts
                    self.assertEqual(facts.stream_sha256, sha256(raw).hexdigest())
                    self.assertEqual((facts.sample_count, facts.projected_aliases), (4, ('power', 'unused')))
                    self.assertEqual((facts.observation.row_count, facts.observation.first_ns,
                        facts.observation.last_ns), (6, 0, 4000000000))
                    reader = history.iter_records('bus')
                    try:
                        records = tuple(reader)
                        self.assertTrue(reader.verified_eof)
                    finally:
                        reader.close()
                    self.assertEqual(len(records), facts.sample_count + facts.progress_count)
                    self.assertFalse(hasattr(facts, 'history_sha256'))
                    case.adapter.close()
                    bound = self.lease(case).bindings
                    self.assertTrue(bound.identity.startswith('scanned-signal-binding-v1:'))
                    self.assertIs(bound.resolve('unused'), plan.bindings.resolve('unused'))

    def test_empty_and_no_target_and_zero_declarations_keep_real_observation(self):
        """空输入不补0时刻；空投影/无目标仍全扫描，不把请求终点当事实。参数: 无。返回: None。异常: 原错。"""
        for frames, empty in (((), False), (((0, 999, b'a'), (2, 999, b'z')), False),
                (((0, 256, b'\xa0\x0f'), (2, 999, b'z')), True)):
            with self.subTest(frames=len(frames), empty_definitions=empty):
                work, plan = self.fixture(frames=frames, empty_definitions=empty)
                case = self.scan(work, plan)
                case.scan.consume()
                facts = case.scan.facts
                self.assertEqual(facts.sample_count, 0)
                self.assertEqual(facts.observation.row_count, len(frames))
                self.assertEqual(facts.observation.last_ns, 2000000000 if frames else None)
                self.assertTrue(facts.completion.source_eof)
                self.assertEqual(case.scan._message_store.count, 1 if empty else 0)
                self.lease(case)

    def test_source_without_message_consumer_still_enters_binding(self):
        """第二个没有指标和信号的CAN来源仍真扫描并进入绑定。参数: 无。返回: None。异常: 原错。"""
        work, plan = self.fixture(two_sources=True)
        first = self.scan(work, plan)
        second = self.scan(work, plan, index=1, budget=first.budget)
        first.scan.consume()
        second.scan.consume()
        self.assertIsNone(second.scan._message_store)
        binding = self.lease(first, scans=(first.scan, second.scan),
            descriptions=(first.description, second.description), requests={'bus': first.request,
            'other': second.request}).bindings
        self.assertEqual([fact.observation.row_count for fact in binding.sources], [3, 3])
        self.assertEqual([fact.sample_count for fact in binding.sources], [2, 0])

    def test_unused_unit_mismatch_is_still_real_ready_error(self):
        """指标不用的声明单位错仍在真实READY检查拒绝。参数: 无。返回: None。异常: 原断言失败。"""
        work, _ = self.fixture(unused=True)
        config = json.loads((work / 'plan.json').read_text(encoding='utf-8'))
        config['signals'][1]['unit'] = 'A'
        plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=work)
        case = self.scan(work, plan)
        with self.assertRaises(SourceReadError) as caught:
            case.scan.consume()
        self.assertIn('单位', str(caught.exception))
        self.assertFalse(case.scan.finished)
        self.assertIs(caught.exception.scanned_can_signals_cleanup_owner, case.scan)

    def test_unused_samples_change_full_scan_identity(self):
        """不参与能量表达式的样本变化仍改变首遍摘要。参数: 无。返回: None。异常: 原错。"""
        import can
        work, plan = self.fixture(unused=True)
        hashes = []
        for value in (7, 8):
            # 同路径、同计划、同原序与时刻，仅更改无人消费的一个实际值。
            with can.BLFWriter(work / 'input.blf') as writer:
                for second, frame_id, payload in ((0, 256, b'\xa0\x0f'), (1, 258, bytes([value]))):
                    writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                        arbitration_id=frame_id, is_extended_id=False, channel=0, data=payload))
            run = work / str(value)
            run.mkdir()
            case = self.scan(run, plan)
            case.scan.consume()
            hashes.append(case.scan.facts.stream_sha256)
        self.assertNotEqual(*hashes)

    def test_non_target_backward_time_is_rejected(self):
        """未保留的原帧时间倒退仍由真实read拒绝。参数: 无。返回: None。异常: 原错。"""
        work, plan = self.fixture(frames=((0, 999, b'a'), (2, 256, b'\xa0\x0f'), (1, 999, b'z')))
        case = self.scan(work, plan)
        with self.assertRaises(SourceReadError):
            case.scan.consume()
        self.assertFalse(case.scan.finished)

    def test_partial_eof_and_unconsumed_scan_cannot_bind(self):
        """最终EOF批不等于真实耗尽；完全未读的同合同scan也不能绑定。参数: 无。返回: None。异常: 原错。"""
        work, plan = self.fixture()
        case = self.scan(work, plan)
        with self.assertRaises(ValueError):
            self.lease(case)
        original = CANBatchObservationRead.__next__
        def stop_after_eof(read):
            """仅在真实EOF批后故意漏掉真实完成调用。参数: read。返回: 原批。异常: 提前StopIteration。"""
            if read._eof_delivered:
                raise StopIteration
            return original(read)
        with patch.object(CANBatchObservationRead, '__next__', new=stop_after_eof):
            with self.assertRaises((ValueError, ResultClosedError)):
                case.scan.consume()
        self.assertFalse(case.scan.finished)
        with self.assertRaises(ResultClosedError):
            case.scan.facts

    def test_batch_callback_contract_or_count_replacement_is_rejected(self):
        """真实读取回调换请求或样本计数，下一步立即拒绝。参数: 无。返回: None。异常: 原错。"""
        original = CANBatchObservationRead.__next__
        for mutation in ('request', 'counts'):
            with self.subTest(mutation=mutation):
                work, plan = self.fixture(size=1)
                case = self.scan(work, plan)
                def replace_after_read(read):
                    """真实读取后污染故障现场。参数: read。返回: 原batch。异常: 原错。"""
                    batch = original(read)
                    if mutation == 'request':
                        case.scan._request = replace(case.request)
                    else:
                        case.scan._counts = (0, 99)
                    return batch
                with patch.object(CANBatchObservationRead, '__next__', new=replace_after_read):
                    with self.assertRaises(ValueError):
                        case.scan.consume()
                self.assertFalse(case.scan.finished)

    def test_missing_description_requests_and_replaced_facts_cannot_bind(self):
        """集合缺项不能被zip静默截短，完成事实被换也不能沿用。参数: 无。返回: None。异常: 原错。"""
        work, plan = self.fixture()
        case = self.scan(work, plan)
        case.scan.consume()
        for descriptions, requests in (((), {'bus': case.request}), ((case.description,), {}),
                ((case.description,), {'bus': case.request, 'extra': case.request})):
            with self.assertRaises(TypeError):
                self.lease(case, descriptions=descriptions, requests=requests)
        case.scan._facts = replace(case.scan.facts, source_contract_sha256='0' * 64)
        with self.assertRaises(ValueError):
            self.lease(case)

    def test_persistent_read_close_failure_keeps_proof_unpublished_and_owner(self):
        """完整读取后close持续失败仍保费用与同一read，恢复才清账。参数: 无。返回: None。异常: 原错。"""
        work, plan = self.fixture()
        case = self.scan(work, plan)
        primary = OSError('test persistent read close')
        with patch.object(CANBatchObservationRead, 'close', side_effect=primary):
            with self.assertRaises(OSError) as caught:
                case.scan.consume()
            self.assertIs(caught.exception, primary)
            self.assertFalse(case.scan.finished)
            self.assertIsNotNone(case.scan._read)
            with self.assertRaises(OSError):
                case.scan.close()
            self.assertGreater(case.scan._held_cost, 0)
        case.scan.close()
        self.assertTrue(case.scan.closed)

    def test_primary_encode_error_survives_persistent_release_failure(self):
        """原编码错误后退费失败仅附注，恢复owner不抵销共享借款。参数: 无。返回: None。异常: 原错。"""
        work, plan = self.fixture()
        case = self.scan(work, plan)
        primary = ValueError('test canonical encoding error')
        def fail_encode(*args):
            """到原行编码时才开启持久释放故障。参数: 原记录/上界。返回: 不成功。异常: 同一主错。"""
            case.budget.release_ram = refuse_release
            raise primary
        def refuse_release(amount):
            """模拟实际账本尚未释放即失败。参数: amount。返回: 不成功。异常: 清理KI。"""
            raise KeyboardInterrupt('test persistent release')
        original = case.budget.release_ram
        try:
            with patch.object(module, 'encode_record', new=fail_encode):
                with self.assertRaises(ValueError) as caught:
                    case.scan.consume()
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.scanned_can_signals_cleanup_owner, case.scan)
            self.assertGreater(case.scan._record_cost, 0)
            self.assertTrue(any('清理' in note for note in primary.__notes__))
        finally:
            case.budget.release_ram = original
        case.scan.close()

    def test_scan_constructor_reserve_after_update_cancel_keeps_recovery_owner(self):
        """构造预付更新后取消且清理失败，保真实未返回owner。参数: 无。返回: None。异常: 原错。"""
        work, plan = self.fixture()
        case = self.scan(work, plan)
        case.scan.close()
        primary = KeyboardInterrupt('test reserve committed')
        reserve, release = case.budget.reserve_ram, case.budget.release_ram
        def cancel_after_reserve(amount):
            """真实入账后取消。参数: amount。返回: 不成功。异常: 原primary。"""
            reserve(amount)
            raise primary
        def fail_release(amount):
            """持续拒绝释放以验证恢复责任。参数: amount。返回: 不成功。异常: OSError。"""
            raise OSError('test cleanup blocked')
        try:
            case.budget.reserve_ram, case.budget.release_ram = cancel_after_reserve, fail_release
            with self.assertRaises(KeyboardInterrupt) as caught:
                ScannedCANSignals(plan.bindings, case.source, case.adapter, case.request)
            self.assertIs(caught.exception, primary)
            pending = primary.scanned_can_signals_cleanup_owner
            self.owners.append(pending)
            self.assertGreater(pending._fixed_cost, 0)
        finally:
            case.budget.reserve_ram, case.budget.release_ram = reserve, release
        pending.close()

    def test_runner_adopts_failed_source_factory_with_persistent_release(self):
        """当前CAN来源构造已入账后失败，最高Runner保原错与可恢复责任。参数: 无。返回: None。异常: 断言。"""
        from chronaxis.execution.record_source_cursor import RecordSourceCursor
        work, plan = self.fixture()
        primary = ValueError('test source factory failed')
        budgets, armed = [], [False]
        original_new = RecordSourceCursor._new
        original_reserve, original_release = ResourceBudget.reserve_ram, ResourceBudget.release_ram
        def refuse(amount):
            """持续拒绝退费直到恢复。参数: bytes。返回: 不成功。异常: OSError。"""
            raise OSError('test persistent ledger cleanup')
        def construct(owner, factory, recovery, *args, **kwargs):
            """限定实际CAN适配器构造的首次预约。参数: 原工厂参数。返回: 原owner。异常: 原错。"""
            armed[0] = factory is BudgetedLegacyCANSourceAdapter
            try:
                return original_new(owner, factory, recovery, *args, **kwargs)
            finally:
                armed[0] = False
        def reserve(budget, amount):
            """真实入账后注入主错，清理故障保留到断言完成。参数: 原预算/bytes。返回: None。异常: primary。"""
            original_reserve(budget, amount)
            if armed[0] and not budgets:
                budgets.append(budget)
                budget.release_ram = refuse
                raise primary
        try:
            with patch.object(RecordSourceCursor, '_new', new=construct), patch.object(ResourceBudget,'reserve_ram',new=reserve):
                with self.assertRaises(AnalysisError) as caught:
                    AnalysisRunner().run(plan, work_dir=work / 'run')
            self.assertIs(caught.exception.__cause__, primary)
            owner = caught.exception.runner_cleanup_owner
            self.assertIsNotNone(primary.record_source_cleanup_owner)
            self.assertFalse(owner.closed)
            self.assertGreater(owner._budget.ram_bytes, 0)
        finally:
            for budget in budgets:
                budget.release_ram = original_release.__get__(budget, ResourceBudget)
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(owner._budget.ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
