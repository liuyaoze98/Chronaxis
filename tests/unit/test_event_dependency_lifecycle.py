"""验收事件阶段依赖的真实历史及三类动态owner构造恢复。

memory/CSV合成来源经既有工厂封存；完整历史/绑定/查询属于调用方，不被新owner关闭。
独立8192 bytes调用方标记与原层费用共同作基线，不手工清总账让故障通过。
真实未返回reader/group/evidence/detector/multi在直接预约成功后失败并持续清理取消，
原异常须保身份、notes和正式最高恢复owner；未安装子对象交给父唯一关闭。
旧组费用释放前后和新组预约前后取消，实际账本只计算一次，真实FD与registry同步收尾。
normal路径核对同刻完整组、CSV定位、批次/计数/完整EOF及摘要，未修改原I/O或核心数值。
所有生成文件与home验证证据只写work；现有测试和RefProjects不修改。
"""

# 复用真实来源工厂而非继承旧测试类；异常只注入单笔预算或登记增长。
import unittest
from unittest.mock import patch
import test_stream_boundaries as factories
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow
from chronaxis.core.temporal import TemporalRule
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.condition_evidence import ConditionEvidenceQueries
from chronaxis.execution.groups import _TimeGroupIterator
from chronaxis.execution.history import _HistoryIterator
from chronaxis.execution.history_records import HistorySample, estimate_record_bytes
from chronaxis.execution.temporal_buffer import BudgetedTemporalDetector
from chronaxis.execution.timeline_multi import MultiRuleTimeline, TimelineRule
from chronaxis.results.errors import AnalysisError
from chronaxis.sources.csv_spec import CSVSourceRef


class EventDependencyLifecycleTests(unittest.TestCase):
    """每例保持真实借用层，最高恢复owner逆序关闭，调用方标记最终才释放。"""

    def fixture(self, *, kind='csv', backend='numpy', size=1):
        """建立两源真实封存历史及借用8192标记。参数: 来源/后端/批次。返回: fixture与基线。异常: 原工厂错误。"""
        factory = factories.StreamBoundaryTests('runTest')
        factory.setUp()
        self.addCleanup(self.cleanup_factory, factory)
        definitions = (SignalDefinition('a', 'alpha', 'raw.a', D.FLOAT64, '1', 10),
                       SignalDefinition('b', 'beta', 'raw.b', D.FLOAT64, '1', 10))
        rows = {'alpha': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1)),
                'beta': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(5, {'raw.b': 2}, 1))}
        data = factory.prepare(kind=kind, backend=backend, size=size, definitions=definitions,
                               rows_by_source=rows, texts=('a > 0', 'b > 0'), domain=(0, 5))
        data.budget.reserve_ram(8192)
        baseline = data.budget.ram_bytes
        # 新资源cleanup在此标记之后登记，先由真实owner恢复基线，再由调用方归还自己的标记。
        self.addCleanup(self.cleanup_marker, data, baseline)
        return data, baseline

    def cleanup_factory(self, factory):
        """核对原层最终清理。参数: 原工厂。返回: None。异常: 清理断言失败。"""
        self.assertTrue(factory.doCleanups())

    def cleanup_marker(self, data, baseline):
        """不清生产总账，只抵销明确8192标记。参数: fixture/基线。返回: None。异常: 泄漏或借用损失断言。"""
        self.assertEqual(data.budget.ram_bytes, baseline)
        data.budget.release_ram(8192)

    def cancel_once(self, actual, error, *, amount=None, call=1, after=False):
        """目标单笔操作前后取消。参数: 实际方法/原错/金额/次数/阶段。返回: 函数。异常: 指定原错。"""
        matched = 0

        def invoke(value):
            """调用真实预算并一次取消。参数: bytes。返回: 原返回。异常: 目标时原异常。"""
            nonlocal matched
            if amount is None or value == amount:
                matched += 1
                if matched == call:
                    if after:
                        actual(value)
                    raise error
            return actual(value)

        return invoke

    def close_check(self, owner, data, baseline):
        """两次close仅归还自有费用。参数: 实际owner/fixture/基线。返回: None。异常: 所有权或费用断言。"""
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(data.budget.ram_bytes, baseline)
        self.assertFalse(data.history.closed)
        self.assertFalse(data.expressions.closed)
        self.assertEqual(data.state.revision, 0)

    def persistent_constructor(self, action, data, *, call=1):
        """实际构造预约成功后原MemoryError，清理持续取消。参数: 动作/fixture/目标次。返回: 原错。异常: 身份断言。"""
        original = MemoryError('actual-event-dependency-constructor')
        reserve = self.cancel_once(data.budget.reserve_ram, original, call=call, after=True)
        with patch.object(data.budget, 'reserve_ram', reserve), \
             patch.object(data.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-constructor-cleanup')):
            with self.assertRaises(MemoryError) as caught:
                action()
        self.assertIs(caught.exception, original)
        self.assertTrue(any('KeyboardInterrupt' in note for note in getattr(original, '__notes__', ())))
        return original

    def dynamic(self, category, data, backend):
        """准备真实动态构造参数，不替换factory。参数: 类别/fixture/后端。返回: 类/args/kwargs/属性/目标次/基线。异常: 原错误。"""
        rule = TemporalRule('short', 'dataset', 'session', 'condition_duration', 1)
        # DecodedBindings没有SignalBindings.source_ref快捷接口；从已核对真实组取依赖的typed来源引用。
        refs = tuple(sample.source_ref for sample in data.groups[0].samples if sample.name in data.compiled[0].dependencies)
        if category == 'evidence':
            return (ConditionEvidenceQueries, (data.expressions,), {'backend': backend},
                    'condition_evidence_queries_cleanup_owner', 1, data.budget.ram_bytes)
        if category == 'detector':
            return (BudgetedTemporalDetector, (data.budget, rule, 0, 5), {'source_refs': refs, 'backend': backend},
                    'temporal_detector_cleanup_owner', 1, data.budget.ram_bytes)
        evidence = ConditionEvidenceQueries(data.expressions, backend=backend)
        self.addCleanup(evidence.close)
        rules = (TimelineRule(rule, data.compiled[0], refs),
                 TimelineRule(TemporalRule('long', 'dataset', 'session', 'condition_duration', 3), data.compiled[0], refs))
        # 第1笔multi固定费、第2笔首Detector、第3笔第二Detector；第二子真实构造尚未安装。
        return (MultiRuleTimeline, (evidence, data.boundaries, rules), {},
                'multi_rule_timeline_cleanup_owner', 3, data.budget.ram_bytes)

    def test_history_constructor_reserve_before_after_transient_preserves_original(self):
        """真实reader未返回时预约前/成功后一次取消，原MemoryError不被清理覆盖且无孤立费用。

        参数: 无。返回: None。异常: 原错丢失或借用基线改变。
        """
        for kind in ('memory', 'csv'):
            for after in (False, True):
                data, baseline = self.fixture(kind=kind)
                cost = data.history.line_limits['alpha'] * 64 + 8192 + 16384
                original = MemoryError('reader-transient')
                reserve = self.cancel_once(data.budget.reserve_ram, original, amount=cost, after=after)
                with patch.object(data.budget, 'reserve_ram', reserve):
                    with self.assertRaises(MemoryError) as caught:
                        data.history.iter_records('alpha')
                self.assertIs(caught.exception, original)
                self.assertEqual(data.budget.ram_bytes, baseline)
                self.assertFalse(data.history._iterators)

    def test_history_constructor_persistent_release_has_formal_owner_and_exact_cost(self):
        """probe单reader预约后原MemoryError及持续清理取消，正式恢复句柄负责真实reader费用。

        参数: 无。返回: None。异常: 原异常替换、traceback救援替代API或费用重复。
        """
        for kind in ('memory', 'csv'):
            data, baseline = self.fixture(kind=kind)
            original = self.persistent_constructor(lambda: data.history.iter_records('alpha'), data)
            recovered = getattr(original, 'history_iterator_cleanup_owner', None)
            self.assertIsInstance(recovered, _HistoryIterator)
            self.addCleanup(recovered.close)
            self.assertEqual(data.budget.ram_bytes, baseline + recovered.cost)
            self.assertEqual(recovered._held_cost, recovered.cost)
            self.assertIsNone(recovered.handle)
            self.close_check(recovered, data, baseline)

    def test_group_constructor_second_actual_reader_is_adopted_by_highest_owner(self):
        """第一reader已开FD，第二构造未返回且持续释放取消；group接管未安装子，原错不丢。

        参数: 无。返回: None。异常: 父只恢复自身、丢第二子或关闭借用history。
        """
        for kind in ('memory', 'csv'):
            data, baseline = self.fixture(kind=kind)
            original = self.persistent_constructor(data.history.iter_groups, data, call=3)
            recovered = getattr(original, 'time_group_iterator_cleanup_owner', None)
            child = getattr(original, 'history_iterator_cleanup_owner', None)
            self.assertIsInstance(recovered, _TimeGroupIterator)
            self.assertIsInstance(child, _HistoryIterator)
            self.assertIs(recovered._uninstalled_reader, child)
            self.addCleanup(recovered.close)  # 只登记最高group责任，不把它已拥有的child再单独关闭。
            handle = recovered.readers[0].handle
            self.assertIsNotNone(handle)
            self.assertTrue(handle.closed)
            self.assertFalse(recovered.closed)
            self.close_check(recovered, data, baseline)
            self.assertTrue(child.closed)
            self.assertFalse(data.history._iterators)
            self.assertFalse(data.history._groups)

    def test_old_group_release_before_after_cancel_never_debits_borrowed_balance(self):
        """已交付组释放前/实际释放后取消，group槽位按真实金额记录，随后close不再扣调用方费用。

        参数: 无。返回: None。异常: probe旧组成功释放后被重复抵销。
        """
        for after in (False, True):
            data, baseline = self.fixture()
            iterator = data.history.iter_groups()
            self.addCleanup(iterator.close)
            first = next(iterator)
            self.assertEqual((first.time_ns, len(first.samples)), (0, 2))
            del first
            cost = iterator._group_cost
            original = KeyboardInterrupt('old-group-release')
            release = self.cancel_once(data.budget.release_ram, original, amount=cost, after=after)
            with patch.object(data.budget, 'release_ram', release):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    next(iterator)
            self.assertIs(caught.exception, original)
            self.assertEqual(iterator._group_cost, 0 if after else cost)
            self.assertEqual(iterator._held_cost, iterator._state_cost + iterator._group_cost)
            self.close_check(iterator, data, baseline)

    def test_new_group_reserve_before_after_cancel_tracks_successful_record(self):
        """新组首record预约前/成功后MemoryError保持既有AnalysisError cause，费用由真实owner收尾。

        参数: 无。返回: None。异常: 成功预约遗漏、closed费用残留或原cause改变。
        """
        for after in (False, True):
            data, baseline = self.fixture()
            iterator = data.history.iter_groups()
            self.addCleanup(iterator.close)
            cost = estimate_record_bytes(iterator.heap[0][2])
            original = MemoryError('new-group-reserve')
            reserve = self.cancel_once(data.budget.reserve_ram, original, amount=cost, after=after)
            with patch.object(data.budget, 'reserve_ram', reserve):
                with self.assertRaises(AnalysisError) as caught:
                    next(iterator)
            self.assertIs(caught.exception.__cause__, original)
            self.assertTrue(iterator.closed)
            self.assertEqual((iterator._group_cost, iterator._held_cost), (0, 0))
            self.close_check(iterator, data, baseline)

    def test_new_group_persistent_cleanup_exposes_same_top_owner_on_wrapper_and_cause(self):
        """成功预约的record遇持续释放取消，外AnalysisError与原MemoryError均交出同一最高group。

        参数: 无。返回: None。异常: wrapper丢恢复句柄、原错覆盖或借用金额损坏。
        """
        data, baseline = self.fixture()
        iterator = data.history.iter_groups()
        self.addCleanup(iterator.close)
        cost = estimate_record_bytes(iterator.heap[0][2])
        original = MemoryError('new-group-persistent')
        reserve = self.cancel_once(data.budget.reserve_ram, original, amount=cost, after=True)
        with patch.object(data.budget, 'reserve_ram', reserve), \
             patch.object(data.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-group-step-cleanup')):
            with self.assertRaises(AnalysisError) as caught:
                next(iterator)
        self.assertIs(caught.exception.__cause__, original)
        self.assertIs(getattr(original, 'time_group_iterator_cleanup_owner', None), iterator)
        self.assertIs(getattr(caught.exception, 'time_group_iterator_cleanup_owner', None), iterator)
        self.assertEqual(iterator._group_cost, cost)
        self.assertEqual(iterator._held_cost, iterator._state_cost + cost)
        self.assertTrue(all(reader.handle.closed for reader in iterator.readers))
        self.close_check(iterator, data, baseline)

    def test_registry_growth_failure_after_real_construction_keeps_original_and_owner(self):
        """真实reader/group已构造但登记失败，同时清理持续取消，注册原MemoryError与实际owner保持。

        参数: 无。返回: None。异常: 注册失败清理替换原错或未登记对象丢失。
        """
        for field, action_name, attribute, owner_type in (
                ('_iterators', 'reader', 'history_iterator_cleanup_owner', _HistoryIterator),
                ('_groups', 'groups', 'time_group_iterator_cleanup_owner', _TimeGroupIterator)):
            for after in (False, True):
                with self.subTest(registry=field, after=after):
                    data, baseline = self.fixture()
                    original = MemoryError('registry-growth')

                    class RejectGrowth(set):
                        """保留原registry，只在add前或实际add成功后失败，不替换构造或真实FD。"""

                        def add(self, value):
                            """登记前后抛原错。参数: 实际owner。返回: 无。异常: 指定MemoryError。"""
                            if after:
                                super().add(value)
                            raise original

                    registry = getattr(data.history, field)
                    actual_registry = RejectGrowth(registry)
                    setattr(data.history, field, actual_registry)
                    try:
                        with patch.object(data.budget, 'release_ram', side_effect=KeyboardInterrupt('registry-cleanup-persistent')):
                            with self.assertRaises(MemoryError) as caught:
                                if action_name == 'reader':
                                    data.history.iter_records('alpha')
                                else:
                                    data.history.iter_groups()
                        self.assertIs(caught.exception, original)
                        recovered = getattr(original, attribute, None)
                        self.assertIsInstance(recovered, owner_type)
                        self.assertEqual(recovered in actual_registry, after)
                        self.addCleanup(recovered.close)
                        # 保留实际登记集合直到正式owner.close完成；成功add后的孤儿也须真实脱链，不能先丢集合绕过。
                        self.close_check(recovered, data, baseline)
                        self.assertNotIn(recovered, actual_registry)
                    finally:
                        setattr(data.history, field, registry)

    def test_dynamic_constructor_before_after_transient_keeps_existing_borrowed_queries(self):
        """两后端三类真实动态owner的首/深子预约前后取消，不推进或关闭原查询、history及state。

        参数: 无。返回: None。异常: 共享查询误关闭或未返回owner费用遗留。
        """
        for backend in ('reference', 'numpy'):
            for category in ('evidence', 'detector', 'multi'):
                for after in (False, True):
                    with self.subTest(backend=backend, category=category, after=after):
                        data, _ = self.fixture(kind='memory', backend=backend)
                        cls, args, kwargs, attribute, call, baseline = self.dynamic(category, data, backend)
                        original = MemoryError('dynamic-transient')
                        reserve = self.cancel_once(data.budget.reserve_ram, original, call=call, after=after)
                        with patch.object(data.budget, 'reserve_ram', reserve):
                            with self.assertRaises(MemoryError) as caught:
                                cls(*args, **kwargs)
                        self.assertIs(caught.exception, original)
                        self.assertEqual(data.budget.ram_bytes, baseline)
                        self.assertFalse(data.expressions.closed)
                        self.assertEqual(data.state.revision, 0)

    def test_dynamic_constructor_six_probe_cases_recover_highest_actual_owner(self):
        """原六动态probe按reference/NumPy×evidence/detector/multi真实复现，持续清理保原错与最高owner。

        参数: 无。返回: None。异常: 只恢复内部子、scope金额损失或正式恢复属性不可达。
        """
        for backend in ('reference', 'numpy'):
            for category in ('evidence', 'detector', 'multi'):
                with self.subTest(backend=backend, category=category):
                    data, _ = self.fixture(kind='memory', backend=backend)
                    cls, args, kwargs, attribute, call, baseline = self.dynamic(category, data, backend)
                    original = self.persistent_constructor(lambda: cls(*args, **kwargs), data, call=call)
                    recovered = getattr(original, attribute, None)
                    self.assertIsInstance(recovered, cls)
                    self.addCleanup(recovered.close)
                    if category == 'multi':
                        child = getattr(original, 'temporal_detector_cleanup_owner', None)
                        self.assertIsInstance(child, BudgetedTemporalDetector)
                        self.assertIs(recovered._uninstalled_detector, child)
                    self.close_check(recovered, data, baseline)

    def test_reader_and_group_close_release_before_after_restore_exact_borrowed_balance(self):
        """已返回真实reader/group自有最终费用释放前后取消，第二close只抵销剩余金额。

        参数: 无。返回: None。异常: 实际FD未关、已释放金额重复扣账或caller状态改变。
        """
        for category in ('reader', 'group'):
            for after in (False, True):
                data, baseline = self.fixture()
                owner = data.history.iter_records('alpha') if category == 'reader' else data.history.iter_groups()
                self.addCleanup(owner.close)
                if category == 'group':
                    next(owner)
                    cost = owner._state_cost + owner._group_cost
                    handles = [reader.handle for reader in owner.readers]
                else:
                    cost = owner.cost
                    handles = [owner.handle]
                original = KeyboardInterrupt('dependency-close-ledger')
                release = self.cancel_once(data.budget.release_ram, original, amount=cost, after=after)
                with patch.object(data.budget, 'release_ram', release):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        owner.close()
                self.assertIs(caught.exception, original)
                self.assertTrue(all(handle.closed for handle in handles))
                if data.budget.ram_bytes > baseline:
                    self.assertFalse(owner.closed)
                self.close_check(owner, data, baseline)

    def test_normal_backends_sources_batches_preserve_whole_eof_hash_count_and_groups(self):
        """正常两源同刻0/5ns完整组、CSV行定位、批次进度及完整EOF摘要跨后端/批次保持原算法。

        参数: 无。返回: None。异常: 解析/计数/whole EOF、排序或费用被生命周期修复改变。
        """
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        data, baseline = self.fixture(kind=kind, backend=backend, size=size)
                        reader = data.history.iter_records('alpha')
                        self.addCleanup(reader.close)
                        handle = reader.handle
                        samples = [record for record in reader if isinstance(record, HistorySample)]
                        self.assertEqual([(record.time_ns, record.sequence, record.value.value) for record in samples],
                                         [(0, 0, 1.), (5, 1, 2.)])
                        self.assertTrue(reader.verified_eof)
                        self.assertTrue(handle.closed)
                        self.assertEqual(reader.digest.digest(), data.history.hashes['alpha'].digest())
                        self.close_check(reader, data, baseline)
                        iterator = data.history.iter_groups()
                        self.addCleanup(iterator.close)
                        summary = []
                        for group in iterator:
                            summary.append((group.time_ns, tuple(record.name for record in group.samples)))
                            if kind == 'csv':
                                self.assertTrue(all(isinstance(record.source_ref, CSVSourceRef) for record in group.samples))
                                self.assertTrue(all(record.source_ref.line_number == (2 if group.time_ns == 0 else 3)
                                                    for record in group.samples))
                        self.assertEqual(summary, [(0, ('a', 'b')), (5, ('a', 'b'))])
                        self.close_check(iterator, data, baseline)
