"""用实体实量、真实结果文件和小CSV验收139费用分离及实际读界。

输入为明确的冻结事实及四行合成CSV；不执行3000/512规模或性能实验。
实体估费与sys.getsizeof的实例/字典/字段实量对照；候选取消保原异常和TB，
完整refs按原对象保留。所有表按真实已编码行长预付，损坏先限长再解码；
空表读槽保单文件固定空间。持续关闭失败保真实FD/owner，借用4096不能被抵销。
文件仅写work/m2-bugfix-tests新uuid；旧reader/decoder与冻结codec算法不替换。
"""

from configuration_fixtures import current_fixture

from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from sys import getsizeof
import unittest
from unittest.mock import patch
from uuid import uuid4
import weakref
import test_results as rows_fixture
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.models import Interval
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.integral_terms import IntegralFacts
from chronaxis.core.conditional_integral_terms import ConditionalIntegralFacts
from chronaxis.core.types import QualityFlag as Q
from chronaxis.execution import integral_facts as plain
from chronaxis.execution import conditional_integral_facts as selected
from chronaxis.execution.retained_metadata import retained_metadata_bytes
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.results import AnalysisResult, ResultFormatError, ResourceBudget
from chronaxis.results.codec import encode_row
from chronaxis.results import result as result_module
from chronaxis.results import codec as codec_module
from chronaxis.results import spool as spool_module
from chronaxis.results import rows as row_module
from chronaxis.results.spool import ResultSpool
from chronaxis.sources.csv_spec import CSVSourceRef


class WeakDictionary(dict):
    """只为有限测试观察JSON树死亡提供弱引用能力，键值和JSON行为仍为dict。"""


class RefMetadataBudgetTests(unittest.TestCase):
    """每个真实owner独立关闭；保留调用方费用，不从共享余额推断归属。"""

    def setUp(self):
        """创建专用新根。参数: 无。返回: None。异常: 原目录创建错误。"""
        # 每次新uuid，保留上轮失败证据，不触Ref或既有发布。
        self.root = Path('work/m2-bugfix-tests/ref-metadata') / uuid4().hex
        self.root.mkdir(parents=True, exist_ok=False)

    def budget(self):
        """建立固定256MiB并留独立借款。参数: 无。返回: 实际预算。异常: 预算错误。"""
        budget = ResourceBudget(268435456)
        budget.reserve_ram(4096)
        self.addCleanup(self.finish_budget, budget)
        return budget

    def finish_budget(self, budget):
        """先核借款再自行释放。参数: 原账本。返回: None。异常: 泄费或误抵断言。"""
        self.assertEqual(budget.ram_bytes, 4096)
        budget.release_ram(4096)

    def refs(self, count, *, long=False):
        """构造完整不同物理行定位。参数: 个数及长文本标志。返回: tuple。异常: 原模型错误。"""
        # 长文本是已存在的caller输入，累计者仍必须为继续持有完整实体付款。
        path = 'source-' + ('测' * 4096 if long else '') + '.csv'
        return tuple(CSVSourceRef('session', 'table', 'raw.a', path, index + 2,
            str(index), '2', False) for index in range(count))

    def owner(self, *, condition=False, refs=(), budget=None):
        """创建两套真实事实owner。参数: 条件分支/初始定位/借预算。返回: owner。异常: 原构造错误。"""
        budget = self.budget() if budget is None else budget
        spec = CalculationDefinition('area', 'integral', Interval(0, 2), output_unit='J')
        cls = selected.ConditionalIntegralFactsAccumulator if condition else plain.IntegralFactsAccumulator
        owner = cls(budget, spec, spec.window, 'W', 'explicit-facts', refs)
        self.addCleanup(owner.close)
        return owner

    def block(self, owner, *, condition=False, refs=(), start=0):
        """明确一纳秒全有效事实。参数: 原owner/分支/定位/起点。返回: typed事实。异常: 原模型检查。"""
        common = dict(spec=owner._spec, actual_window=Interval(start, start + 1),
            value_valid_duration_ns=1, valid_sample_count=1, value_unknown_ranges=(),
            quality=Q.NONE, input_unit='W', binding_identity='explicit-facts', source_refs=refs)
        if condition:
            return ConditionalIntegralFacts(**common, condition_known_duration_ns=1,
                selected_duration_ns=1, selected_value_unknown_duration_ns=0,
                false_duration_ns=0, condition_unknown_ranges=())
        return IntegralFacts(**common)

    def spool(self, *, contributions=False, current=False):
        """建立真实小缓冲。参数: contributions启用当前贡献表，current只请求事件。返回: spool。异常: 预算/IO原错。"""
        spool = ResultSpool(self.budget(), self.root / uuid4().hex, 1, enable_contributions=contributions,
                            requested_tables=('events',) if current else None)
        self.addCleanup(spool.close)
        return spool

    def result(self, spool):
        """封存并接真实结果父。参数: 本测试spool。返回: result。异常: 原封存/metadata错误。"""
        spool.seal()
        result = AnalysisResult(spool, replace(rows_fixture.run_metadata(), device_label='home'), 'jsonl')
        self.addCleanup(result.close)
        return result

    def test_entity_estimate_covers_instance_dictionary_container_and_long_unicode(self):
        """实体费覆盖实际对象/字典/字段，长Unicode按真实字符存储增长。

        参数: 无。返回: None。异常: 实体漏计或长文本被固定常数替代时断言失败。
        """
        short, long = self.refs(1)[0], self.refs(1, long=True)[0]
        for ref in (short, long):
            # 直接核这一个真实实例的实体尺寸，不用被测递归算法生成真值。
            actual = getsizeof(ref) + getsizeof(vars(ref)) + sum(getsizeof(item) for item in vars(ref).values())
            self.assertGreaterEqual(retained_metadata_bytes(ref), actual)
            self.assertGreaterEqual(retained_metadata_bytes((ref, ref)), getsizeof((ref, ref)) + 2 * actual)
        self.assertGreaterEqual(retained_metadata_bytes(long) - retained_metadata_bytes(short),
                                getsizeof(long.path) - getsizeof(short.path))

    def test_candidate_keeps_original_refs_and_prepays_pointer_not_old_payload_copy(self):
        """旧长定位继续原对象持有，新候选预约不再重付整个旧payload。

        参数: 无。返回: None。异常: refs截断/深复制或候选未预付断言失败。
        """
        for condition in (False, True):
            with self.subTest(condition=condition):
                old_refs, incoming = self.refs(12, long=True), self.refs(1)
                owner = self.owner(condition=condition, refs=old_refs)
                reserve, charges = owner._budget.reserve_ram, []

                def observe(amount):
                    """透传真实预付。参数: bytes。返回: 原结果。异常: 原预算错误。"""
                    charges.append(amount)
                    return reserve(amount)

                with patch.object(owner._budget, 'reserve_ram', observe):
                    owner.push(self.block(owner, condition=condition, refs=incoming))
                module = selected if condition else plain
                self.assertEqual(len(charges), 1)
                self.assertLess(charges[0], module._refs_cost(old_refs))
                self.assertEqual(owner._state.source_refs, (*old_refs, *incoming))
                self.assertTrue(all(one is two for one, two in zip(owner._state.source_refs, (*old_refs, *incoming))))
                owner.close()

    def test_push_reserve_before_after_cancel_exposes_same_owner_and_preserves_borrowed(self):
        """候选预付前/后取消都保原错及最高真实事实owner。

        参数: 无。返回: None。异常: 漏登记、原错被改或误抵借款断言失败。
        """
        for condition in (False, True):
            for after in (False, True):
                with self.subTest(condition=condition, after=after):
                    owner = self.owner(condition=condition)
                    actual, calls = owner._budget.reserve_ram, []
                    marker = KeyboardInterrupt('actual-candidate-reserve')

                    def cancel(amount):
                        """命中实际唯一申请。参数: bytes。返回: 不返回。异常: 同一取消。"""
                        calls.append(amount)
                        if after:
                            actual(amount)
                        raise marker

                    with patch.object(owner._budget, 'reserve_ram', cancel):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            owner.push(self.block(owner, condition=condition, refs=self.refs(1)))
                    self.assertIs(caught.exception, marker)
                    self.assertEqual(len(calls), 1)
                    attribute = 'conditional_integral_facts_cleanup_owner' if condition else 'integral_facts_cleanup_owner'
                    self.assertIs(getattr(marker, attribute), owner)
                    owner.close()
                    self.assertEqual(owner._budget.ram_bytes, 4096)

    def test_release_before_after_cancel_preserved_tb_does_not_pin_old_snapshot(self):
        """候选缩账前后取消保原TB，旧本层前缀在close后真正失去引用。

        参数: 无。返回: None。异常: 已抵费用仍钉住旧候选、或借款不保断言失败。
        """
        for condition in (False, True):
            for after in (False, True):
                owner = self.owner(condition=condition, refs=self.refs(2))
                old = weakref.ref(owner._state)
                actual, hits = owner._budget.release_ram, []
                marker, saved = KeyboardInterrupt('actual-candidate-shrink'), None

                def cancel(amount):
                    """命中真实缩账。参数: bytes。返回: 不返回。异常: 同一取消。"""
                    hits.append(amount)
                    if after:
                        actual(amount)
                    raise marker

                try:
                    with patch.object(owner._budget, 'release_ram', cancel):
                        owner.push(self.block(owner, condition=condition, refs=self.refs(1)))
                except KeyboardInterrupt as error:
                    saved = error
                self.assertIs(saved, marker)
                self.assertIsNotNone(saved.__traceback__)
                self.assertEqual(len(hits), 1)
                owner.close()
                self.assertIsNone(old())
                self.assertEqual(owner._budget.ram_bytes, 4096)

    def test_unreturned_constructor_persistent_cleanup_recovers_actual_owned_fee(self):
        """构造预约后取消且三次持续释放失败，最高未返回owner不丢实际费用。

        参数: 无。返回: None。异常: 未返回责任丢失、原错变更或抵借款断言失败。
        """
        for condition in (False, True):
            budget, marker = self.budget(), KeyboardInterrupt('constructor-owned-reserve')
            reserve, releases = budget.reserve_ram, []

            def cancel_reserve(amount):
                """真实入账后取消。参数: bytes。返回: 不返回。异常: 同一主错。"""
                reserve(amount)
                raise marker

            def cancel_release(amount):
                """持续阻止真实释放。参数: bytes。返回: 不返回。异常: 同一主错。"""
                releases.append(amount)
                raise marker

            cls = selected.ConditionalIntegralFactsAccumulator if condition else plain.IntegralFactsAccumulator
            spec = CalculationDefinition('area', 'integral', Interval(0, 2))
            with patch.object(budget, 'reserve_ram', cancel_reserve), patch.object(budget, 'release_ram', cancel_release):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    cls(budget, spec, spec.window, 'W', 'explicit-facts', self.refs(1))
                self.assertIs(caught.exception, marker)
                name = 'conditional_integral_facts_cleanup_owner' if condition else 'integral_facts_cleanup_owner'
                owner = getattr(marker, name)
                self.addCleanup(owner.close)
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.assertGreaterEqual(len(releases), 3)
            self.assertFalse(owner.closed)
            owner.close()
            owner.close()
            self.assertEqual(budget.ram_bytes, 4096)

    def test_dynamic_max_uses_actual_bytes_and_empty_table_keeps_one_file_space(self):
        """普通表实长与真实文件逐字一致；空贡献表预付一份文件缓冲及固定状态。

        参数: 无。返回: None。异常: 行字节/上界或实际固定文件空间漏账时断言失败。
        """
        spool = self.spool(contributions=True)
        row = rows_fixture.summary_event_row()
        payload = encode_row(row, spool.max_row_bytes)
        spool.append(row)
        self.assertEqual(spool.row_limit('events'), len(payload))
        self.assertEqual(spool.reader_cost_for('events'), len(payload) * 64 + 8192)
        self.assertEqual(spool.row_limit('calculations'), 1)
        self.assertEqual(spool.row_limit('contributions'), 1)
        self.assertEqual(spool.reader_cost_for('contributions'), 16384)
        # 现行空表与有数据表均只用一个JSONL；公开结果继续核真实读槽费用。
        spool.seal()
        self.assertEqual(spool.files['events'].read_bytes(), payload)
        spool = self.spool(current=True)
        row = rows_fixture.summary_event_row()
        spool.append(row)
        result = self.result(spool)
        baseline = spool.budget.ram_bytes
        reader = result.iter_events()
        self.assertEqual(spool.budget.ram_bytes - baseline, spool.reader_cost_for('events'))
        self.assertEqual(next(reader), row)
        reader.close()
        self.assertEqual(spool.budget.ram_bytes, baseline)
        result.close()

    def test_table_oversize_or_missing_newline_rejects_before_decode_and_closes_fd(self):
        """损坏文件不能按stat扩读界；超实长或缺换行在解码前明确拒绝。

        参数: 无。返回: None。异常: 读界绕过、decode被调用或FD/费用残留断言失败。
        """
        for oversize in (False, True):
            spool = self.spool(current=True)
            spool.append(rows_fixture.summary_event_row())
            result = self.result(spool)
            payload = spool.files['events'].read_bytes()
            spool.files['events'].write_bytes(payload[:-1] + (b'  \n' if oversize else b''))
            baseline = spool.budget.ram_bytes
            reader = result.iter_events()
            handle = reader.handle
            with patch.object(result_module, 'decode_row', wraps=result_module.decode_row) as decoder:
                with self.assertRaises(ResultFormatError):
                    next(reader)
                decoder.assert_not_called()
            self.assertTrue(handle.closed)
            self.assertTrue(reader.closed)
            self.assertEqual(spool.budget.ram_bytes, baseline)
            result.close()

    def test_empty_table_reader_fixed_header_covers_actual_fd_and_instance(self):
        """空表读界仍为1，固定头必须覆盖真实缓冲FD及reader实例字典。

        参数: 无。返回: None。异常: 缓冲/句柄实体漏计或EOF未关闭断言失败。
        """
        spool = self.spool(current=True)
        result = self.result(spool)
        reader = result.iter_events()
        # 只计reader真正拥有的实体，不把借用owner/spool递归算进本读槽。
        actual = (getsizeof(reader) + getsizeof(vars(reader)) + getsizeof(reader.handle)
                  + getsizeof(reader.handle.raw))
        self.assertEqual(reader.max_row_bytes, 1)
        self.assertGreaterEqual(reader._reader_cost, actual)
        self.assertEqual(reader._reader_cost, 16384)
        with self.assertRaises(StopIteration):
            next(reader)
        self.assertTrue(reader.handle.closed)
        result.close()

    def test_actual_reader_reserve_before_after_cancel_no_fd_or_unregistered_fee(self):
        """新实长读槽申请前后取消均不打开FD，真实父仍活且借款不变。

        参数: 无。返回: None。异常: 故障未hit、槽孤立或父被擅自关闭断言失败。
        """
        for after in (False, True):
            spool = self.spool(current=True)
            spool.append(rows_fixture.summary_event_row())
            result = self.result(spool)
            baseline, actual = spool.budget.ram_bytes, spool.budget.reserve_ram
            cost, hits = spool.reader_cost_for('events'), []
            marker = KeyboardInterrupt('actual-table-reader-reserve')

            def cancel(amount):
                """只截实际表读槽。参数: bytes。返回: 原结果或抛错。异常: 同一取消。"""
                if amount == cost:
                    hits.append(amount)
                    if after:
                        actual(amount)
                    raise marker
                return actual(amount)

            with patch.object(spool.budget, 'reserve_ram', cancel), patch.object(Path, 'open', wraps=Path.open) as opened:
                with self.assertRaises(KeyboardInterrupt) as caught:
                    result.iter_events()
                opened.assert_not_called()
            self.assertIs(caught.exception, marker)
            self.assertEqual(hits, [cost])
            self.assertFalse(result._iterators)
            self.assertEqual(spool.budget.ram_bytes, baseline)
            result.close()

    def test_actual_reader_persistent_release_keeps_highest_result_and_other_fd(self):
        """一个新读槽持续三次释放失败保最高结果；另一真实reader不被单reader关闭。

        参数: 无。返回: None。异常: 费用失责、提前closed或并行FD被误关断言失败。
        """
        spool = self.spool(current=True)
        spool.append(rows_fixture.summary_event_row())
        result = self.result(spool)
        first, second = result.iter_events(), result.iter_events()
        cost, actual, hits = first._reader_cost, spool.budget.release_ram, []
        marker = KeyboardInterrupt('actual-table-reader-release')

        def cancel(amount):
            """持续拦截同表真实金额。参数: bytes。返回: 原结果或抛错。异常: 同一取消。"""
            if amount == cost:
                hits.append(amount)
                raise marker
            return actual(amount)

        with patch.object(spool.budget, 'release_ram', cancel):
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    first.close()
                self.assertIs(caught.exception, marker)
                self.assertFalse(first.closed)
                self.assertFalse(second.handle.closed)
            with self.assertRaises(KeyboardInterrupt):
                result.close()
        self.assertGreaterEqual(len(hits), 3)
        self.assertIs(marker.analysis_result_cleanup_owner, result)
        self.assertTrue(first.handle.closed)
        result.close()
        self.assertTrue(second.handle.closed)
        self.assertEqual(spool.budget.ram_bytes, 4096)

    def test_tiny_real_csv_three_scopes_both_backends_trace_and_close_zero(self):
        """四行真CSV、两核和1/2/7切批保持手算12J及同次四条输入追溯。

        参数: 无。返回: None。异常: 真读取/父关联/数值/完整refs或最终RAM断言失败。
        """
        path = (self.root / 'source.csv').absolute()
        path.write_text('ns,a\n0,2\n1000000000,2\n2000000000,2\n3000000000,2\n', encoding='utf-8')
        for backend in ('reference', 'numpy'):
            for batch in (1, 2, 7):
                # 全配置只使用公开模型；无CAN/DBC或额外数据扫描。
                config = dict(config_version=3,
                    dataset=dict(name='d', entity='entity', session='session', domain=dict(start='0s', end='4s')),
                    sources=[dict(name='table', source_type='signal_csv', path=str(path), time_column='ns',
                        time=dict(time_type='relative', unit='ns', origin='explicit'))],
                    signals=[dict(name='a', source='table', field='a', dtype='float64', unit='W',
                        valid_for='10s', same_time_policy='last_by_sequence')],
                    derived={'b': dict(expr='a * 2', unit='W')},
                    rules=[dict(name='active', rule_type='condition_duration', condition='b > 0', minimum_duration='0s')],
                    windows=[dict(name='whole', rule='active', anchor='activity', pre='0s', post='0s', merge='none')],
                    calculations=[dict(name=calculation_id, scope=scope, operation='integral', expr='b', unit='J')
                        for calculation_id, scope in (('session', 'session'), ('event', 'event:active'), ('segment', 'segment:whole'))],
                    execution=dict(backend=backend, batch_rows=batch, result_buffer_rows=1,
                        memory_budget_bytes=268435456), outputs=dict(tables='jsonl'), diagnostics=dict(trace=True), metadata=dict(device_label='home'))
                actual_read, reads = BudgetedSignalCSVSourceAdapter.iter_batches, []

                def observe_read(adapter, request, **options):
                    """观察新层实际read一次。参数: 原adapter/request。返回: 原read。异常: 原构造错误。"""
                    read = actual_read(adapter, request, **options)
                    reads.append(read)
                    return read

                with patch.object(BudgetedSignalCSVSourceAdapter, 'iter_batches', observe_read):
                    result = AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)), work_dir=self.root / uuid4().hex)
                budget = result.spool.budget
                try:
                    self.assertEqual(len(reads), 1)
                    self.assertTrue(reads[0].closed)
                    reader = result.iter_calculations()
                    try:
                        rows = tuple(reader)
                    finally:
                        reader.close()
                    self.assertEqual(len(rows), 3)
                    for row in rows:
                        self.assertTrue(math.isclose(row.value, 12.0, rel_tol=1e-12, abs_tol=1e-18))
                        self.assertEqual(row.parent_id is None, row.scope == 'session')
                    traces = tuple(result.iter_input_trace())
                    self.assertEqual(len(traces), 4)
                    self.assertEqual([row.original_sequence for row in traces], [0, 1, 2, 3])
                    self.assertTrue(all(row.source == 'table' and json.loads(row.values_json) == {'a': 2.0} for row in traces))
                    self.assertEqual([row.time_ns for row in traces], [0, 10**9, 2*10**9, 3*10**9])
                    result.write(self.root / ('published-' + uuid4().hex))
                finally:
                    result.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_current_codec_matches_independent_literal_bytes(self):
        """当前平坦事件与手写JSON逐字节相同；不再承诺旧版本字节和费用。"""
        payload = (b'{"row":{"confirmed_ns":10,"dataset_id":"dataset","end_ns":10,"entity_id":"entity",'
                   b'"event_id":"event-0","quality":0,"rule_id":"rule","sequence":0,"session_id":"session",'
                   b'"start_ns":5,"status":"closed","trigger":"condition_duration"},"row_schema_version":8}\n')
        row = rows_fixture.summary_event_row()
        self.assertEqual(codec_module.encode_row(row, 1048576), payload)
        self.assertEqual(codec_module.decode_row(payload, 1048576), row)
        self.assertGreater(codec_module.estimate_row_bytes(row), len(payload))

    def test_codec_encode_same_error_tb_drops_actual_tree_but_not_user_guard(self):
        """真实平坦字段树经JSON后取消，保同一异常/TB而本层树弱引用全部释放。

        参数: 无。返回: None。异常: encode局部/递归迭代器保树或外部帧被清断言失败。
        """
        pack, dumps = codec_module.summary_fields, codec_module.json.dumps
        refs, errors = [], []
        marker = KeyboardInterrupt('codec-real-dumps-after')
        user_guard = object()

        def observe_pack(value):
            """透传真实pack后加透明弱引用壳。参数: 原值/深度。返回: 原JSON语义树。异常: 原错。"""
            tree = None
            try:
                tree = pack(value)
                if type(tree) is dict:
                    tree = WeakDictionary(tree)
                    refs.append(weakref.ref(tree))
                return tree
            finally:
                tree = value = None

        def cancel_dumps(value, *args, **kwargs):
            """实际JSON完成后取消。参数: 原树与原选项。返回: 不返回。异常: 同一marker。"""
            guard = user_guard
            text = None
            try:
                text = dumps(value, *args, **kwargs)
                raise marker
            finally:
                # 仅清测试自身借入参数；guard保留用于核生产没有清外部帧。
                text = value = args = kwargs = None

        with patch.object(codec_module, 'summary_fields', observe_pack), patch.object(codec_module.json, 'dumps', cancel_dumps):
            try:
                codec_module.encode_row(rows_fixture.summary_event_row(), 1048576)
            except KeyboardInterrupt as error:
                errors.append(error)
        self.assertEqual(len(errors), 1)
        self.assertIs(errors[0], marker)
        saved_tb = marker.__traceback__
        self.assertTrue(refs)
        self.assertTrue(all(ref() is None for ref in refs))
        tb, guard_seen = saved_tb, False
        while tb is not None:
            if tb.tb_frame.f_code is cancel_dumps.__code__:
                self.assertIs(tb.tb_frame.f_locals['guard'], user_guard)
                guard_seen = True
            if tb.tb_frame.f_code is codec_module.encode_row.__code__:
                self.assertIsNone(tb.tb_frame.f_locals['packed'])
                self.assertIsNone(tb.tb_frame.f_locals['row'])
            tb = tb.tb_next
        self.assertTrue(guard_seen)
        self.assertIs(marker.__traceback__, saved_tb)

    def test_codec_nested_decode_failure_clears_own_containers_without_external_frame_clear(self):
        """嵌套定位非法触发真实解包错误；codec自身参数/容器清空，调用者输入保留。

        参数: 无。返回: None。异常: 自有生成器/kwargs/解析树留在TB或输入被改断言失败。
        """
        raw = codec_module._pack(rows_fixture.core_event())
        raw['fields']['source_refs']['tuple'][0]['fields']['session_id'] = {'invalid-tag': True}
        saved = None
        try:
            codec_module._unpack(raw)
        except ResultFormatError as error:
            saved = error
        self.assertIsNotNone(saved)
        self.assertIsNotNone(saved.__traceback__)
        self.assertEqual(raw['fields']['source_refs']['tuple'][0]['fields']['session_id'],
                         {'invalid-tag': True})
        count, tb = 0, saved.__traceback__
        while tb is not None:
            frame = tb.tb_frame
            if frame.f_globals.get('__name__') == codec_module.__name__:
                count += 1
                self.assertNotIn(frame.f_code.co_name, ('<dictcomp>', '<genexpr>', '<listcomp>'))
                for key in ('packed', 'payload', 'value', 'row', 'items', 'kwargs', 'item'):
                    if key in frame.f_locals:
                        self.assertIsNone(frame.f_locals[key], (frame.f_code.co_name, key))
            tb = tb.tb_next
        self.assertGreater(count, 3)

    def test_closed_actual_fileio_write_keeps_error_and_releases_local_memoryview(self):
        """真实已关闭FileIO写入失败，原错/TB保留而本层memoryview不继续存活。

        参数: 无。返回: None。异常: 写错误改型、临时view保活或累计磁盘抵销断言失败。
        """
        spool = self.spool()
        path, payload = self.root / 'actual-closed.bin', b'actual-fileio-payload'
        handle = path.open('xb', buffering=0)
        handle.close()
        views, seen, saved = [], [], None
        before = spool.budget.spool_bytes
        user_guard = object()

        def observe_view(data):
            """记录真正memoryview的弱引用。参数: 原bytes。返回: 原view。异常: 原分配错误。"""
            view = memoryview(data)
            views.append(weakref.ref(view))
            return view

        def invoke():
            """透传真实写错并留外部guard。参数: 无。返回: 不返回。异常: 同一ValueError。"""
            guard = user_guard
            try:
                spool._write_bytes(handle, payload)
            except ValueError as error:
                seen.append(error)
                raise

        with patch.object(spool_module, 'memoryview', observe_view, create=True):
            try:
                invoke()
            except ValueError as error:
                saved = error
        self.assertIsNotNone(saved)
        self.assertIs(saved, seen[0])
        self.assertIsNone(saved.__cause__)
        self.assertEqual(len(views), 1)
        self.assertIsNone(views[0]())
        self.assertEqual(spool.budget.spool_bytes - before, len(payload))
        tb, own_seen = saved.__traceback__, False
        while tb is not None:
            if tb.tb_frame.f_code is spool._write_bytes.__code__:
                own_seen = True
                for key in ('self', 'handle', 'payload', 'view'):
                    self.assertIsNone(tb.tb_frame.f_locals[key])
            if tb.tb_frame.f_code is invoke.__code__:
                self.assertIs(tb.tb_frame.f_locals['guard'], user_guard)
            tb = tb.tb_next
        self.assertTrue(own_seen)
        self.assertTrue(handle.closed)
        self.assertEqual(payload, b'actual-fileio-payload')

        # 同一真实FileIO错误再经实际flush路径发生，局部sort-key也须在抵buffer费前断开。
        flush_spool = self.spool()
        write_bytes, saved = flush_spool._write_bytes, None

        def close_before_write(handle, data):
            """关闭实际新FD再透传写入。参数: 原句柄/bytes。返回: 不返回。异常: 原ValueError。"""
            try:
                handle.close()
                write_bytes(handle, data)
            finally:
                handle = data = None

        with patch.object(flush_spool, '_write_bytes', close_before_write):
            try:
                flush_spool.append(rows_fixture.summary_event_row())
            except ValueError as error:
                saved = error
        self.assertIsNotNone(saved)
        tb, flush_seen = saved.__traceback__, False
        while tb is not None:
            if tb.tb_frame.f_code is flush_spool._flush.__code__:
                flush_seen = True
                self.assertIsNone(tb.tb_frame.f_locals['key'])
                self.assertIsNone(tb.tb_frame.f_locals['payload'])
            tb = tb.tb_next
        self.assertTrue(flush_seen)
        self.assertEqual(flush_spool._buffer_cost, 0)

    def test_enum_fields_cancel_keeps_original_tb_and_clears_local_label(self):
        """真实ENUM字段已取出后取消，清本层长标签而不清调用者原行和guard。

        参数: 无。返回: None。异常: 不是同一原取消、未命中取值窗口或TB仍留标签时断言失败。
        """
        label = '实际枚举标签' * 2048
        row = replace(rows_fixture.summary_selection_row(), value=label, dtype='enum')
        self.assertIs(result_module._row_fields(row)['value'], label)
        marker, saved, hit = KeyboardInterrupt('enum-after-label'), None, []
        previous, user_guard = sys.gettrace(), object()

        def trace_label(frame, event, argument):
            """在原函数已提取标签后的下一行取消。参数: 真实trace事件。返回: hook。异常: 原marker。"""
            try:
                if (frame.f_code is result_module._row_fields.__code__ and event == 'line'
                        and frame.f_locals.get('result', {}).get('value') is label):
                    hit.append(True)
                    raise marker
                return trace_label
            finally:
                frame = argument = None

        def invoke():
            """调用真实字段展开并保外部guard。参数: 无。返回: dict。异常: 原取消。"""
            guard = user_guard
            return result_module._row_fields(row)

        try:
            sys.settrace(trace_label)
            invoke()
        except KeyboardInterrupt as error:
            saved = error
        finally:
            sys.settrace(previous)
        self.assertIs(saved, marker)
        self.assertEqual(hit, [True])
        saved_tb, tb, own_seen, guard_seen = saved.__traceback__, saved.__traceback__, False, False
        while tb is not None:
            if tb.tb_frame.f_code is result_module._row_fields.__code__:
                own_seen = True
                for name in ('row', 'result'):
                    self.assertIsNone(tb.tb_frame.f_locals[name])
            if tb.tb_frame.f_code is invoke.__code__:
                guard_seen = True
                self.assertIs(tb.tb_frame.f_locals['guard'], user_guard)
            tb = tb.tb_next
        self.assertTrue(own_seen and guard_seen)
        self.assertIs(saved.__traceback__, saved_tb)
        self.assertIs(row.value, label)

    def test_sort_helpers_internal_cancel_clear_only_own_borrowed_row(self):
        """真实排序函数内部完成前置工作后取消，保helper自身TB但不再钉住借入行。

        参数: 无。返回: None。异常: 未命中真实内部行、原错/TB或普通排序key改变时断言失败。
        """
        row, user_guard = rows_fixture.summary_event_row(), object()
        self.assertEqual(row_module.row_table(row), 'events')
        self.assertEqual(row_module.row_sort_key(row), ('session', 'rule', 5, 0, 'dataset', 'entity'))
        # sort分支必须已执行row_table且取出实际事件时间；不是在callee返回后才由caller抛错。
        for function in (row_module.row_table, row_module.row_sort_key):
            with self.subTest(function=function.__name__):
                marker, saved, hit = KeyboardInterrupt('helper-inside-' + function.__name__), None, []
                previous = sys.gettrace()
                import inspect
                source_lines, first_line = inspect.getsourcelines(function)
                cancel_line = first_line + next(index for index, line in enumerate(source_lines)
                    if 'if type(row) in SUMMARY_MODELS' in line)

                def trace_inside(frame, event, argument):
                    """只在目标原函数内部已建局部后取消。参数: trace事件。返回: hook。异常: 原marker。"""
                    try:
                        ready = (frame.f_lineno == cancel_line if function is row_module.row_table
                                 else 'time' in frame.f_locals)
                        if frame.f_code is function.__code__ and event == 'line' and ready:
                            hit.append(True)
                            raise marker
                        return trace_inside
                    finally:
                        frame = argument = None

                def invoke():
                    """透传真实helper并保外部guard。参数: 无。返回: 原返回值。异常: 原取消。"""
                    guard = user_guard
                    return function(row)

                try:
                    sys.settrace(trace_inside)
                    invoke()
                except KeyboardInterrupt as error:
                    saved = error
                finally:
                    sys.settrace(previous)
                self.assertIs(saved, marker)
                self.assertEqual(hit, [True])
                saved_tb, tb, own_seen, guard_seen = saved.__traceback__, saved.__traceback__, False, False
                while tb is not None:
                    if tb.tb_frame.f_code is function.__code__:
                        own_seen = True
                        for name in ('row', 'event', 'segment', 'start'):
                            if name in tb.tb_frame.f_locals:
                                self.assertIsNone(tb.tb_frame.f_locals[name])
                    if tb.tb_frame.f_code is invoke.__code__:
                        guard_seen = True
                        self.assertIs(tb.tb_frame.f_locals['guard'], user_guard)
                    tb = tb.tb_next
                self.assertTrue(own_seen and guard_seen)
                self.assertIs(saved.__traceback__, saved_tb)
                self.assertEqual(row.event_id, 'event-0')


if __name__ == '__main__':
    unittest.main()
