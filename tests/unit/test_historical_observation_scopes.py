"""用真实扫描写入同一历史，验证按完整时钟及真实依赖选择实际范围。

所有夹具先load计划，再由实际ObservedSourceScan将memory或CSV的原批次写入
同一DecodedHistoryStore；sealed后建立实际DecodedBindings和原HoldContext。
被测范围不接手造首末快照。整数ns手算覆盖长短来源、空投影、全空、单点、域外、
offset、独立origin和显式typed同步。原请求/绑定身份保留，stable identity另含
原行首端；文件SHA篡改、提前close及真实FD/预算取消都必须拒绝假完成或漏费。
有限输出只用于小夹具真值；证据写work/m2-run-tests，device_label为home。
不修改旧测试、RefProjects、schema、数值核或公共AnalysisRunner，也不宣称RSS性能结论。
"""

from configuration_fixtures import current_fixture

# 每例拥有独立小输入和预算；所有实际生产层均按逆序显式清理。
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis import load_analysis_plan
from chronaxis.core.binding import SynchronizationEvidence
from chronaxis.core.models import Interval
from chronaxis.execution.bindings import bind_decoded_history
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.historical_observation import HistoricalObservationScopes, ObservationScope
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.hold import HoldContext
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.observed_ingestion import ObservedSourceScan
from chronaxis.results import BudgetExceededError, ResultClosedError, ResultFormatError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest


class HistoricalObservationScopesTests(unittest.TestCase):
    """每例借用真实scan/history/lease，被测owner只拥有有限范围及最多一个reader。"""

    def fixture(self, *, kind='memory', backend='numpy', size=2, names=None,
                sources=None, domain=(0, 10), synchronized=(), declared=None, plan=None):
        """加载完整小计划并由真实scan单次读入新历史，不手造完成证明。

        参数: kind为memory/csv；backend/reference或numpy；size是真实批大小；names
            为各来源投影字典，省略表示其唯一别名；sources为小配置列表，含name、rows、
            origin、offset、absolute；domain为原请求整数ns。synchronized和declared
            只在任何adapter/scan之前构造明确typed声明，不声称公共JSON支持这些扩展。
            plan非None时复用同一原计划及实际CSV路径，供空投影历史同SHA的identity对照。
        返回: 含原四对象、真实scans/adapters及借用预算基线的data。
        异常: 文件、计划、真实扫描、绑定或最终清理错误直接失败。
        """
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/historical-observation' / uuid4().hex
        work.mkdir(parents=True)
        if plan is None:
            sources = ([dict(name='table', alias='a', rows=((0, 2), (8, 0)), origin='common'),
                        dict(name='other', alias='b', rows=((0, 3), (5, 0)), origin='common')]
                       if sources is None else sources)
            source_configs, signal_configs = [], []
            for source in sources:
                absolute = source.get('absolute', False)
                clock = dict(time_type='absolute' if absolute else 'relative', unit='ISO8601' if absolute else 'ns',
                    offset=str(source.get('offset', 0)) + 'ns')
                if not absolute:
                    clock['origin'] = source.get('origin', 'common')
                config = dict(name=source['name'], source_type='memory' if kind == 'memory' else 'signal_csv', time=clock)
                field = 'raw.' + source['alias']
                if kind == 'memory':
                    config['rows'] = [dict(time=self.time_text(time, absolute), values={field: value})
                        for time, value in source['rows']]
                else:
                    path = work / (source['name'] + '.csv')
                    path.write_text('ns,' + field + '\n' + ''.join(self.time_text(time, absolute, unit=False)
                        + ',' + ('' if value is None else str(value)) + '\n' for time, value in source['rows']),
                        encoding='utf-8', newline='')
                    config.update(path=str(path), time_column='ns')
                source_configs.append(config)
                signal_configs.append(dict(name=source['alias'], source=source['name'], field=field,
                    dtype='float64', unit='1', valid_for='20ns'))
            absolute_domain = sources[0].get('absolute', False)
            config = dict(config_version=3,
                dataset=dict(name='scope_dataset', entity='scope_entity', session='scope_session',
                    domain=dict(start=self.time_text(domain[0], absolute_domain), end=self.time_text(domain[1], absolute_domain))),
                sources=source_configs, signals=signal_configs, rules=[], calculations=[],
                execution=dict(backend=backend, batch_rows=size, result_buffer_rows=1, memory_budget_bytes=256*1024**2))
            path = work / 'plan.json'
            path.write_text(json.dumps(current_fixture(config)), encoding='utf-8')
            plan = load_analysis_plan(path)
            if declared:
                # 只使用核心已存在的SourceSpec typed声明，实际adapter/scan随后借这个原config。
                modified = tuple(replace(source, config=replace(source.config,
                    observation_start_ns=declared[source.name][0], observation_end_ns=declared[source.name][1]))
                    if source.name in declared else source for source in plan.sources)
                plan = replace(plan, sources=modified)
            if synchronized:
                evidence = tuple(SynchronizationEvidence(name, plan.dataset.timebase,
                    'synthetic fixed-offset mapping explicitly supplied in typed API') for name in synchronized)
                plan = replace(plan, bindings=replace(plan.bindings, synchronization=evidence))
        budget = ResourceBudget(plan.execution.memory_budget_bytes)
        self.addCleanup(self.cleanup_zero, budget)
        budget.reserve_ram(8192)
        self.addCleanup(self.cleanup_marker, budget)
        adapters, requests = [], {}
        for source in plan.sources:
            definitions = tuple(item.definition for item in plan.signals if item.definition.source == source.name)
            adapter_type = BudgetedMemorySourceAdapter if source.source_type == 'memory' else BudgetedSignalCSVSourceAdapter
            adapter = adapter_type(budget, source.config, plan.dataset.session_id, definitions,
                backend=plan.execution.backend)
            self.addCleanup(adapter.close)
            adapters.append(adapter)
            projection = tuple(item.name for item in definitions) if names is None else names[source.name]
            requests[source.name] = ReadRequest(plan.dataset.session_id, projection,
                plan.dataset.domain.start_ns, plan.dataset.domain.end_ns, plan.execution.batch_rows)
        descriptions = tuple(adapter.describe() for adapter in adapters)
        history = DecodedHistoryStore(budget, work / 'history', descriptions, requests)
        self.addCleanup(history.close)
        scans = []
        for source, adapter in zip(plan.sources, adapters):
            scan = ObservedSourceScan(history, source, adapter, requests[source.name])
            self.addCleanup(scan.close)
            scan.consume()
            self.assertTrue(scan.finished)
            scans.append(scan)
        history.seal()
        lease = bind_decoded_history(plan.bindings, history)
        self.addCleanup(lease.close)
        context = HoldContext(plan.dataset.session_id, plan.dataset.domain, descriptions,
            tuple(history.source_completions.values()))
        return SimpleNamespace(work=work, plan=plan, budget=budget, history=history, context=context,
            lease=lease, adapters=tuple(adapters), scans=tuple(scans), requests=requests,
            baseline=budget.ram_bytes)

    def time_text(self, value, absolute, *, unit=True):
        """为小样例生成明确ns或UTC时间。参数: 整数ns/absolute/unit。返回: str。异常: 超出小日期样例范围。"""
        if absolute:
            if not 0 <= value < 1_000_000_000:
                raise ValueError('本测试绝对时间格式仅用于UTC epoch后第一秒内的小ns坐标')
            return '1970-01-01T00:00:00.' + str(value).zfill(9) + 'Z'
        return str(value) + ('ns' if unit else '')

    def cleanup_zero(self, budget):
        """核最外层实际0。参数: 共享budget。返回: None。异常: 漏费或多扣断言失败。"""
        self.assertEqual(budget.ram_bytes, 0)

    def cleanup_marker(self, budget):
        """只归还明确调用方标记。参数: budget。返回: None。异常: 借用账本错误。"""
        self.assertEqual(budget.ram_bytes, 8192)
        budget.release_ram(8192)

    def owner(self, data, **changes):
        """仅传原四对象及真实scan。参数: data/显式负例覆盖。返回: scopes。异常: 原构造错。"""
        arguments = dict(history=data.history, context=data.context, bindings=data.lease.bindings,
            plan=data.plan, source_scans=data.scans)
        arguments.update(changes)
        owner = HistoricalObservationScopes(**arguments)
        self.addCleanup(owner.close)
        return owner

    def close_check(self, owner, data, *, baseline=None):
        """两次close只抵销本范围owner。参数: owner/data/可选外部reader基线。返回: None。异常: 所有权错误。"""
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(data.budget.ram_bytes, data.baseline if baseline is None else baseline)
        self.assertFalse(data.history.closed)
        self.assertFalse(data.lease.closed)
        with self.assertRaises(ResultClosedError):
            owner.for_dependencies(())

    def cancel_once(self, actual, original, *, after=False, amount=None):
        """一笔实际预算前后取消。参数: 原方法/原错/阶段/可选金额。返回: wrapper。异常: 指定原错。"""
        reached = []

        def invoke(value):
            """只在首次目标动作取消。参数: bytes。返回: 原返回。异常: 指定原对象。"""
            if not reached and (amount is None or value == amount):
                reached.append(value)
                if after:
                    actual(value)
                raise original
            return actual(value)

        return invoke

    def test_real_scans_long_short_sources_backends_sizes_envelope_and_source_endpoints(self):
        """长8短5同钟范围保8而分源端点保5。参数: 无。返回: None。异常: 取短源交集或改原请求。"""
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        data = self.fixture(kind=kind, backend=backend, size=size)
                        old_binding_identity = data.lease.bindings.identity
                        owner = self.owner(data, source_scans=tuple(reversed(data.scans)))
                        scope = owner.for_dependencies(('a',))
                        self.assertIsInstance(scope, ObservationScope)
                        self.assertIs(scope, owner.for_dependencies(('b',)))
                        self.assertIs(scope, owner.for_dependencies(('a', 'b')))
                        self.assertIs(scope, owner.dataset_scope)
                        self.assertEqual((scope.sources, scope.observed_start_ns, scope.observed_end_ns, scope.actual),
                            (('table', 'other'), 0, 8, Interval(0, 8)))
                        self.assertEqual(tuple((item.source, item.first_ns, item.last_ns, item.row_count,
                            item.observed_end_ns) for item in owner.source_observations),
                            (('table', 0, 8, 2, 8), ('other', 0, 5, 2, 5)))
                        self.assertTrue(all(owner.source_observations[index] is not data.scans[index].observation
                            for index in range(2)))
                        self.assertEqual(data.lease.bindings.identity, old_binding_identity)
                        self.assertEqual(data.context.domain, Interval(0, 10))
                        self.assertRegex(owner.identity, '^[0-9a-f]{64}$')
                        with self.assertRaises(FrozenInstanceError):
                            scope.actual = None
                        self.close_check(owner, data)

    def test_empty_projection_and_declared_empty_sources_do_not_forge_observations(self):
        """空投影原行仍有范围，全空声明边界不能造假点。参数: 无。返回: None。异常: 把无样本等同无原行。"""
        for kind in ('memory', 'csv'):
            data = self.fixture(kind=kind, names={'table': (), 'other': ()})
            self.assertTrue(all(scan.counts[1] == 0 for scan in data.scans))
            owner = self.owner(data)
            self.assertEqual(owner.dataset_scope.actual, Interval(0, 8))
            self.assertEqual(tuple(item.row_count for item in owner.source_observations), (2, 2))
            with self.assertRaisesRegex(ValueError, '投影'):
                owner.for_dependencies(('a',))
            self.close_check(owner, data)
            empty_sources = [dict(name='table', alias='a', rows=(), origin='common'),
                dict(name='other', alias='b', rows=(), origin='common')]
            data = self.fixture(kind=kind, sources=empty_sources,
                declared={'table': (0, 8), 'other': (0, 5)} if kind == 'memory' else None)
            owner = self.owner(data)
            self.assertIsNone(owner.dataset_scope.actual)
            self.assertIsNone(owner.dataset_scope.observed_start_ns)
            self.assertIsNone(owner.dataset_scope.observed_end_ns)
            self.assertEqual(tuple(item.row_count for item in owner.source_observations), (0, 0))
            self.close_check(owner, data)

    def test_single_point_terminal_touch_domain_outside_and_offset_only_once(self):
        """真实点、仅端点相交和完全域外不同，offset不二次施加。参数: 无。返回: None。异常: 边界误判。"""
        for kind in ('memory', 'csv'):
            for rows, offset, expected in ((((3, 1),), 0, Interval(3, 3)),
                (((0, 1), (3, 0)), 0, Interval(3, 3)), (((0, 1), (2, 0)), 0, None),
                (((0, 1), (2, 0)), 5, Interval(5, 7))):
                data = self.fixture(kind=kind, domain=(3, 8),
                    sources=[dict(name='table', alias='a', rows=rows, origin='common', offset=offset)])
                owner = self.owner(data)
                self.assertEqual(owner.for_dependencies(('a',)).actual, expected)
                observation = owner.source_observations[0]
                self.assertEqual((observation.first_ns, observation.last_ns), (rows[0][0]+offset, rows[-1][0]+offset))
                self.close_check(owner, data)

    def test_csv_full_raw_int64_span_is_clipped_before_interval_allocation(self):
        """域外完整跨度超过int64仍可取请求内小交集。参数: 无。返回: None。异常: 先建原全跨度Interval溢出。"""
        minimum, maximum = -(2**63), 2**63-1
        data = self.fixture(kind='csv', sources=[dict(name='table', alias='a',
            rows=((minimum, 1), (maximum, 2)), origin='common')])
        owner = self.owner(data)
        scope = owner.for_dependencies(('a',))
        self.assertEqual((scope.observed_start_ns, scope.observed_end_ns), (minimum, maximum))
        self.assertEqual(scope.actual, Interval(0, 10))
        self.close_check(owner, data)

    def test_different_relative_origins_independent_scopes_reject_joint_and_constant_uses_dataset_only(self):
        """独立origin不相互延长，真正joint仍原拒。参数: 无。返回: None。异常: 全计划误拒或错误联合。"""
        sources = [dict(name='table', alias='a', rows=(), origin='left'),
            dict(name='other', alias='b', rows=((2, 1), (8, 0)), origin='right')]
        for kind in ('memory', 'csv'):
            data = self.fixture(kind=kind, sources=sources)
            owner = self.owner(data)
            left, right = owner.for_dependencies(('a',)), owner.for_dependencies(('b',))
            self.assertNotEqual(left.clock_key, right.clock_key)
            self.assertEqual((left.sources, right.sources), (('table',), ('other',)))
            self.assertIsNone(left.actual)
            self.assertEqual(right.actual, Interval(2, 8))
            self.assertIs(owner.for_dependencies(()), left)
            with self.assertRaisesRegex(ValueError, '同步'):
                owner.for_dependencies(('a', 'b'))
            with self.assertRaisesRegex(ValueError, '未知'):
                owner.for_dependencies(('unknown',))
            with self.assertRaises(TypeError):
                owner.for_dependencies(['a'])
            self.close_check(owner, data)

    def test_explicit_typed_sync_maps_to_dataset_and_absolute_utc_remains_comparable(self):
        """typed核实映射归dataset且不重复offset，绝对UTC保完整组。参数: 无。返回: None。异常: 组或同步变化。"""
        sources = [dict(name='table', alias='a', rows=((0, 1), (5, 0)), origin='left'),
            dict(name='other', alias='b', rows=((0, 1), (3, 0)), origin='right', offset=5)]
        data = self.fixture(sources=sources, synchronized=('other',))
        owner = self.owner(data)
        self.assertEqual(owner.for_dependencies(('a', 'b')).actual, Interval(0, 8))
        self.assertEqual(owner.source_observations[1].first_ns, 5)
        self.close_check(owner, data)
        for kind in ('memory', 'csv'):
            data = self.fixture(kind=kind, sources=[dict(name='table', alias='a', rows=((0, 1), (5, 0)), absolute=True),
                dict(name='other', alias='b', rows=((2, 1), (8, 0)), absolute=True)])
            owner = self.owner(data)
            self.assertIs(owner.for_dependencies(('a', 'b')), owner.dataset_scope)
            self.assertEqual(owner.dataset_scope.actual, Interval(0, 8))
            self.close_check(owner, data)
            # dataset为relative时，另一个absolute来源独立留在UTC组，不能给常量规则填范围。
            data = self.fixture(kind=kind, sources=[dict(name='table', alias='a', rows=(), origin='relative_only'),
                dict(name='other', alias='b', rows=((2, 1), (8, 0)), absolute=True)])
            owner = self.owner(data)
            self.assertEqual(owner.for_dependencies(('b',)).clock_key, ('utc',))
            self.assertEqual(owner.for_dependencies(('b',)).actual, Interval(2, 8))
            self.assertIsNone(owner.dataset_scope.actual)
            with self.assertRaisesRegex(ValueError, '同步'):
                owner.for_dependencies(('a', 'b'))
            self.close_check(owner, data)

    def test_stable_identity_changes_raw_start_when_empty_projection_history_sha_does_not(self):
        """空投影相同SHA/EOF/计数但不同原首端必须不同scope identity。参数: 无。返回: None。异常: 输入身份漏范围。"""
        sources = [dict(name='table', alias='a', rows=((0, 1), (2, 1), (8, 0)), origin='common')]
        data = self.fixture(kind='csv', names={'table': ()}, sources=sources)
        first = self.owner(data)
        first_identity = first.identity
        repeated = self.owner(data)
        self.assertEqual(first_identity, repeated.identity)
        self.close_check(repeated, data, baseline=data.baseline + first._held_cost)
        path = data.plan.sources[0].config.paths[0]
        path.write_text('ns,raw.a\n1,1\n2,1\n8,0\n', encoding='utf-8')
        other = self.fixture(plan=data.plan, names={'table': ()})
        second = self.owner(other)
        self.assertEqual(data.scans[0].history_sha256, other.scans[0].history_sha256)
        self.assertEqual(data.scans[0].counts, other.scans[0].counts)
        self.assertEqual(data.lease.bindings.identity, other.lease.bindings.identity)
        self.assertEqual((first.source_observations[0].first_ns, second.source_observations[0].first_ns), (0, 1))
        self.assertNotEqual(first_identity, second.identity)
        self.close_check(second, other)
        self.close_check(first, data)

    def test_original_contract_scans_liveness_and_hand_snapshot_are_not_interchangeable(self):
        """本层及消费者必须保持原对象，手造快照不能替代扫描。参数: 无。返回: None。异常: 归属绕过。"""
        data, foreign = self.fixture(), self.fixture()
        with self.assertRaises(TypeError):
            self.owner(data, source_scans=tuple(scan.observation for scan in data.scans))
        for scans in ((data.scans[0],), (data.scans[0], data.scans[0]), foreign.scans):
            with self.assertRaises((ValueError, ResultClosedError)):
                self.owner(data, source_scans=scans)
            self.assertEqual(data.budget.ram_bytes, data.baseline)
        owner = self.owner(data)
        for context, bindings, plan in ((replace(data.context), data.lease.bindings, data.plan),
                (data.context, replace(data.lease.bindings), data.plan),
                (data.context, data.lease.bindings, replace(data.plan))):
            with self.assertRaisesRegex(ValueError, '原history'):
                owner.assert_current(data.history, context, bindings, plan)
        owner.assert_current(data.history, data.context, data.lease.bindings, data.plan)
        data.scans[1].close()
        before_close = data.budget.ram_bytes - owner._held_cost
        with self.assertRaises(ResultClosedError):
            owner.for_dependencies(('a',))
        self.close_check(owner, data, baseline=before_close)

    def test_actual_sha_mutation_and_real_early_reader_close_cannot_pass_eof_proof(self):
        """当前文件SHA及真实EOF必须重新核实，旧scan字段不替代。参数: 无。返回: None。异常: 损坏或早close被接受。"""
        data = self.fixture(kind='csv')
        path = data.history.paths['table']
        original = path.read_bytes()
        lines = original.splitlines(keepends=True)
        lines[-1] = b' ' + lines[-1]
        path.write_bytes(b''.join(lines))
        try:
            with self.assertRaisesRegex(ResultFormatError, '摘要'):
                self.owner(data)
            self.assertEqual(data.budget.ram_bytes, data.baseline)
        finally:
            path.write_bytes(original)
        actual = data.history.iter_records
        readers = []

        def close_before_eof(source):
            """真实创建后提前close。参数: source。返回: 实际已关闭reader。异常: 原构造/关闭错。"""
            reader = actual(source)
            readers.append(reader)
            reader.close()
            return reader

        with patch.object(data.history, 'iter_records', close_before_eof):
            with self.assertRaisesRegex(ResultFormatError, 'EOF'):
                self.owner(data)
        self.assertTrue(readers)
        self.assertTrue(all(reader.closed and not reader.verified_eof for reader in readers))
        self.assertEqual(data.budget.ram_bytes, data.baseline)

    def test_single_actual_history_reader_at_a_time_then_no_rescan_in_getters(self):
        """构造逐源最多一reader，getter不反复全扫。参数: 无。返回: None。异常: 并持reader或查询重读。"""
        data = self.fixture()
        actual = data.history.iter_records
        readers = []

        def track_actual(source):
            """登记实际reader并核单活槽。参数: source。返回: 真reader。异常: 原构造或并持断言失败。"""
            reader = actual(source)
            readers.append(reader)
            self.assertLessEqual(sum(not item.closed for item in readers), 1)
            return reader

        with patch.object(data.history, 'iter_records', track_actual):
            owner = self.owner(data)
        self.assertEqual(len(readers), len(data.plan.sources))
        self.assertTrue(all(reader.closed and reader.verified_eof and reader.handle.closed for reader in readers))
        with patch.object(data.history, 'iter_records', side_effect=AssertionError('getter rescanned history')):
            owner.assert_current(data.history, data.context, data.lease.bindings, data.plan)
            self.assertEqual(owner.for_dependencies(('a',)).actual, Interval(0, 8))
            self.assertTrue(owner.identity)
            self.assertEqual(len(owner.source_observations), 2)
        self.close_check(owner, data)

    def test_constructor_budget_before_after_true_limit_and_persistent_cleanup_restore_top_owner(self):
        """首笔预算取消及真限额提前拒，持续清理取消保最高owner。参数: 无。返回: None。异常: 漏费/盖错。"""
        for after in (False, True):
            data = self.fixture()
            original = KeyboardInterrupt('scope-first-reserve')
            with patch.object(data.budget, 'reserve_ram', self.cancel_once(data.budget.reserve_ram, original, after=after)):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    self.owner(data)
            self.assertIs(caught.exception, original)
            self.assertEqual(data.budget.ram_bytes, data.baseline)
        data = self.fixture()
        old_limit = data.budget.memory_budget_bytes
        data.budget.memory_budget_bytes = data.baseline
        try:
            with patch.object(data.history, 'iter_records', side_effect=AssertionError('unpaid history read')):
                with self.assertRaises(BudgetExceededError):
                    self.owner(data)
            self.assertEqual(data.budget.ram_bytes, data.baseline)
        finally:
            data.budget.memory_budget_bytes = old_limit
        data = self.fixture()
        original = MemoryError('scope-unreturned-construct')
        with patch.object(data.budget, 'reserve_ram', self.cancel_once(data.budget.reserve_ram, original, after=True)), \
             patch.object(data.budget, 'release_ram', side_effect=KeyboardInterrupt('scope-persistent-cleanup')):
            with self.assertRaises(MemoryError) as caught:
                self.owner(data)
        self.assertIs(caught.exception, original)
        recovered = getattr(original, 'historical_observation_scopes_cleanup_owner', None)
        self.assertIsNotNone(recovered)
        self.addCleanup(recovered.close)
        self.close_check(recovered, data)

    def test_unreturned_real_history_reader_budget_and_close_fixed_before_after_retry(self):
        """未返回reader自有费可由最高scope接管，完成后固定费释放取消可重试。参数: 无。返回: None。异常: 错接或多扣。"""
        data = self.fixture()
        probe = data.history.iter_records('table')
        cost = probe.cost
        probe.close()
        original = MemoryError('scope-unreturned-history-reader')
        reserve, release = data.budget.reserve_ram, data.budget.release_ram
        armed = []

        def fail_reader(amount):
            """实际reader已付费后失败。参数: bytes。返回: 原返回。异常: 原MemoryError。"""
            value = reserve(amount)
            if amount == cost and not armed:
                armed.append(amount)
                raise original
            return value

        def persistent_cleanup(amount):
            """reader实际计费后持续取消清理。参数: bytes。返回: 原返回。异常: 指定清理取消。"""
            if armed:
                raise KeyboardInterrupt('scope-reader-persistent-release')
            return release(amount)

        with patch.object(data.budget, 'reserve_ram', fail_reader), patch.object(data.budget, 'release_ram', persistent_cleanup):
            with self.assertRaises(MemoryError) as caught:
                self.owner(data)
        self.assertTrue(armed)
        self.assertIs(caught.exception, original)
        recovered = getattr(original, 'historical_observation_scopes_cleanup_owner', None)
        reader = getattr(original, 'history_iterator_cleanup_owner', None)
        self.assertIsNotNone(recovered)
        self.assertIsNotNone(reader)
        self.assertIs(recovered._reader, reader)
        self.addCleanup(recovered.close)
        self.close_check(recovered, data)
        for after in (False, True):
            data = self.fixture()
            owner = self.owner(data)
            original = KeyboardInterrupt('scope-fixed-release')
            with patch.object(data.budget, 'release_ram', self.cancel_once(data.budget.release_ram,
                    original, after=after, amount=owner._fixed_cost)):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    owner.close()
            self.assertIs(caught.exception, original)
            self.close_check(owner, data)

    def test_real_history_fd_close_persistent_failure_keeps_top_owner_and_external_reader(self):
        """构造中真实history FD关闭持续失败，最高scope恢复只关自身，外部reader仍可读。

        参数: 无。返回: None。异常: 原取消身份丢失、漏真实FD、多扣或关闭借用reader。
        流程: 外部reader先真实打开；仅给本构造随后打开的真实二进制FD加透明close包装。
            在完整EOF自动close时持续失败，恢复后只调用异常中的最高scope.close。
        """
        data = self.fixture(kind='csv')
        external = data.history.iter_records('other')
        self.addCleanup(external.close)
        baseline = data.budget.ram_bytes
        original = KeyboardInterrupt('scope-real-history-fd-close')
        actual_open = Path.open
        handles, reached = [], []
        armed = True

        class ActualHistoryFile:
            """只代理实际二进制FD的close故障，其余读取沿真实文件。"""

            def __init__(self, handle):
                """保存真实FD。参数: 实际已打开文件。返回: None。异常: 无预期异常。"""
                self.handle = handle

            def __getattr__(self, name):
                """委托真实文件属性。参数: 属性名。返回: 原值。异常: 原属性或I/O错误。"""
                return getattr(self.handle, name)

            def close(self):
                """在真实close前持续取消。参数: 无。返回: 原返回。异常: 本例原KeyboardInterrupt。"""
                if armed and not self.handle.closed:
                    reached.append(self)
                    raise original
                return self.handle.close()

        def open_actual(path, *args, **kwargs):
            """包装本构造实际打开的history FD。参数: 原open参数。返回: 实际代理。异常: 原I/O错误。"""
            handle = ActualHistoryFile(actual_open(path, *args, **kwargs))
            handles.append(handle)
            return handle

        def disarm_cleanup():
            """断言失败也解除持续故障。参数: 无。返回: None。异常: 无。"""
            nonlocal armed
            armed = False

        self.addCleanup(disarm_cleanup)
        with patch.object(Path, 'open', open_actual):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.owner(data)
        self.assertIs(caught.exception, original)
        self.assertTrue(handles)
        self.assertTrue(reached)
        self.assertTrue(all(not handle.handle.closed for handle in handles))
        recovered = getattr(original, 'historical_observation_scopes_cleanup_owner', None)
        self.assertIsNotNone(recovered)
        self.addCleanup(recovered.close)
        self.assertIsNotNone(recovered._reader)
        self.assertFalse(external.handle.closed)
        armed = False
        self.close_check(recovered, data, baseline=baseline)
        self.assertTrue(all(handle.handle.closed for handle in handles))
        self.assertFalse(external.handle.closed)
        self.assertIsNotNone(next(external))
        external.close()
        self.assertEqual(data.budget.ram_bytes, data.baseline)
