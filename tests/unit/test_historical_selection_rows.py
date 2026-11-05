"""用真实封存历史验收逐行选择、原类型、来源定位及有限资源生命周期。

memory/CSV工厂只读取原来源一次；两个后端按1/2/7个区间回读新历史。
真实值更新产生TRUE或UNKNOWN行，FALSE、TTL边界、条件更新与右末点不造行。
手算与既有完整内存选择器互相核对；BOOL、ENUM、大整数不经过浮点转换。
workspace、当前行及调用方暂存包装分别计费，异常保留原身份和可恢复句柄。
ResultSpool小缓冲实写实读typed行与完整CSV定位；不声称公共AnalysisRunner已接线。
所有合成文件和home验证证据仅写新项目work，原history/state最终由工厂关闭。
"""

# 模块别名复用真实工厂与故障助手，避免发现重复的旧测试类。
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_historical_conditional_blocks as real_history
import test_historical_conditional_integral as integral_tests
from chronaxis.core import (SignalBindings, SignalDefinition, SessionSpec, SourceSpec,
                            TimebaseSpec, TimeType, compile_expression)
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.calculations_memory_reference import select_memory_reference
from chronaxis.core.calculations_memory_numpy import select_memory_numpy
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, Truth
from chronaxis.execution.historical_selection_rows import HistoricalSelectionRows
from chronaxis.execution.history import _metadata_bytes
from chronaxis.execution.calculation_blocks import CalculationBlock
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.results.summary import SummarySelectionRow
from chronaxis.results.spool import ResultSpool
from chronaxis.results.codec import decode_row
from chronaxis.sources.csv_spec import CSVSourceRef


class HistoricalSelectionRowsTests(unittest.TestCase):
    """每个选择owner只持有当前块/核/行；原借用状态及金额由工厂保护。"""

    def definitions_and_rows(self):
        """声明手算更新、TTL与三值选择。参数: 无。返回: 定义/来源行。异常: 模型错误。"""
        # 1秒只有条件和TTL边界；4秒只定EOF。2秒UNKNOWN与3秒无效值仍须输出。
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', 1_000_000_000),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 5_000_000_000))
        rows = {'table': tuple(MemoryRow(time * 1_000_000_000, {'raw.a': value}, index)
                              for index, (time, value) in enumerate(((0, 2), (2, 8), (3, None), (4, 99)))),
                'other': tuple(MemoryRow(index * 1_000_000_000, {'raw.b': value}, index)
                               for index, value in enumerate((1, 0, None, 1, 1)))}
        return definitions, rows

    def prepare(self, *, joint=True, kind='memory', backend='numpy', size=1, spec=None, **kwargs):
        """建立真实历史后登记自有选择层。参数: 联合/来源/后端/块数及夹具覆盖。返回: 三元组。异常: 原错误。"""
        factory = real_history.HistoricalConditionalBlocksTests('runTest')
        self.addCleanup(self.cleanup_factory, factory)
        definitions, rows = self.definitions_and_rows()
        kwargs.setdefault('definitions', definitions)
        kwargs.setdefault('rows_by_source', rows)
        fixture = factory.fixture(kind=kind, backend=backend, size=size, **kwargs)
        # 基线仅属于原history/state/保持等借用层，选择层不能全账本清零。
        baseline = fixture.budget.ram_bytes
        spec = CalculationDefinition('rows', 'select', fixture.domain) if spec is None else spec
        owner = self.make_owner(fixture, spec, joint=joint, backend=backend, size=size)
        return fixture, owner, baseline

    def make_owner(self, fixture, spec, *, joint=True, backend='numpy', size=1, **kwargs):
        """注册真实选择owner关闭。参数: 实际fixture及请求配置。返回: owner。异常: 原构造错误。"""
        owner = HistoricalSelectionRows(fixture.history, fixture.holds._context, fixture.lease.bindings,
            kwargs.pop('compiled', fixture.compiled[0]), spec,
            kwargs.pop('condition', fixture.compiled[1] if joint else None),
            backend=backend, batch_intervals=size, **kwargs)
        self.addCleanup(owner.close)
        return owner

    def cleanup_factory(self, factory):
        """检查借用层最终RAM0。参数: 原工厂。返回: None。异常: 清理断言错误。"""
        self.assertTrue(factory.doCleanups())

    def close_and_check(self, fixture, owner, baseline):
        """核对自有金额仅归还一次。参数: 实际资源及基线。返回: None。异常: 所有权断言错误。"""
        # 成功后再次close不扣账；原历史保持开放且原state没有因回读推进。
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assertFalse(fixture.history.closed)
        self.assertEqual(fixture.state.revision, 0)
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def summary(self, row):
        """取固定小型手算字段。参数: 一行。返回: 时间/typed值/选择/质量。异常: 错误模型传播。"""
        return row.time_ns, row.value, row.selection, row.quality, row.unit

    def consume(self, owner):
        """即时消费，只保存本测试至多三行摘要。参数: owner。返回: 摘要tuple。异常: 原推进错误。"""
        result = []
        for row in owner:
            result.append(self.summary(row))
        self.assertTrue(owner.exhausted)
        return tuple(result)

    def memory_truth(self, spec):
        """独立构造完整内存桥接输入。参数: 原请求。返回: 两内存入口摘要。异常: 绑定或核错误。"""
        definitions, rows = self.definitions_and_rows()
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'selection-synthetic-v1')
        sources = tuple(SourceSpec(name, clock, data, observation_start_ns=0, observation_end_ns=4_000_000_000)
                        for name, data in rows.items())
        bindings = SignalBindings(SessionSpec('session', clock, 0, 4_000_000_000, sources), definitions)
        value, condition = compile_expression('a', bindings), compile_expression('b > 0', bindings)
        # 身份与CSV定位属于实际历史，数值/选择字段可与独立完整内存桥接比较。
        reference = tuple(self.summary(row) for row in select_memory_reference(value, spec, condition=condition))
        self.assertEqual(reference, tuple(self.summary(row) for row in select_memory_numpy(value, spec, condition=condition)))
        return reference

    def cancel_at(self, original, **kwargs):
        """复用账本前后一次取消。参数: 实际方法及注入配置。返回: 注入函数。异常: 原指定异常。"""
        return integral_tests.HistoricalConditionalIntegralTests('runTest').cancel_at(original, **kwargs)

    def test_real_sources_backends_splits_match_hand_and_memory_without_rescan(self):
        """手算0秒2W TRUE、2秒8W UNKNOWN、3秒无效TRUE；条件/TTL/EOF不增加行。

        参数: 无。返回: None。异常: 数值、质量、身份或来源被切分/后端改变。
        """
        spec = CalculationDefinition('rows', 'select', Interval(0, 4_000_000_000))
        expected = self.memory_truth(spec)
        self.assertEqual(tuple(item[0] for item in expected), (0, 2_000_000_000, 3_000_000_000))
        self.assertEqual(tuple(item[2] for item in expected), (Truth.TRUE, Truth.UNKNOWN, Truth.TRUE))
        self.assertEqual(tuple(item[1].valid for item in expected), (True, True, False))
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        fixture, owner, baseline = self.prepare(kind=kind, backend=backend, size=size)
                        # 封存后禁止重新打开原来源；联合身份由两实际compiled组成。
                        with patch.object(BudgetedMemorySourceAdapter, 'iter_batches', side_effect=AssertionError('rescan')), \
                             patch.object(BudgetedSignalCSVSourceAdapter, 'iter_batches', side_effect=AssertionError('rescan')):
                            rows = []
                            for row in owner:
                                self.assertEqual(row.binding_identity, fixture.compiled[0].identity + ':' + fixture.compiled[1].identity)
                                self.assertTrue(row.source_refs)
                                if kind == 'csv':
                                    self.assertTrue(all(isinstance(ref, CSVSourceRef) for ref in row.source_refs))
                                rows.append(self.summary(row))
                        self.assertEqual(tuple(rows), expected)
                        self.close_and_check(fixture, owner, baseline)

    def test_historical_voltage_selection_respects_version_and_converts_once(self):
        """从真实封存历史回读1000mV，v4单路与条件选择均交付1V。

        参数: 无。返回: None。异常: 目标单位、数值、类型、版本门槛或归还预算错误。
        """
        window = Interval(0, 4_000_000_000)
        rows = {'table': (MemoryRow(0, {'raw.a': 1000}, 0), MemoryRow(window.end_ns, {'raw.a': 999}, 1)),
                'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(window.end_ns, {'raw.b': 1}, 1))}
        for version in (4,):
            definitions = (SignalDefinition('a', 'table', 'raw.a', D.INT64, 'mV', window.end_ns, config_version=version),
                           SignalDefinition('b', 'other', 'raw.b', D.INT64, '1', window.end_ns, config_version=version))
            for backend in ('reference', 'numpy'):
                for joint in (False, True):
                    with self.subTest(version=version, backend=backend, joint=joint):
                        spec = CalculationDefinition('rows', 'select', window, config_version=version,
                                                     output_unit='V')
                        fixture, owner, baseline = self.prepare(backend=backend, joint=joint, spec=spec,
                                                               definitions=definitions, rows_by_source=rows)
                        row, = tuple(owner)
                        expected = (1.0, D.FLOAT64, 'V')
                        self.assertEqual((row.value.value, row.value.dtype, row.unit), expected)
                        self.close_and_check(fixture, owner, baseline)

    def test_bool_enum_and_uint64_preserve_original_typed_value_and_labels(self):
        """BOOL与ENUM编码按声明解码，uint64最大值精确保留；select不做浮点数值归约。

        参数: 无。返回: None。异常: CSV/数组装箱丢失标签、整数精度或真实类型。
        """
        for dtype, raw, expected, choices in ((D.BOOL, 1, True, ((0, False), (1, True))),
                (D.ENUM, 1, 'Run', ((0, 'Idle'), (1, 'Run'))), (D.UINT64, 2**64-1, 2**64-1, ())):
            for kind in ('memory', 'csv'):
                for backend in ('reference', 'numpy'):
                    definitions = (SignalDefinition('a', 'table', 'raw.a', dtype, '1', 5_000_000_000, choices=choices),
                                   SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', 5_000_000_000))
                    rows = {'table': (MemoryRow(0, {'raw.a': raw}, 0), MemoryRow(4_000_000_000, {'raw.a': raw}, 1)),
                            'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(4_000_000_000, {'raw.b': 1}, 1))}
                    fixture, owner, baseline = self.prepare(kind=kind, backend=backend, size=2,
                                                            definitions=definitions, rows_by_source=rows)
                    row = next(owner)
                    self.assertEqual((row.value.dtype, row.value.valid, row.value.value, row.unit), (dtype, True, expected, '1'))
                    if dtype == D.ENUM:
                        self.assertEqual(row.value.labels, ('Idle', 'Run'))
                    if dtype == D.UINT64:
                        self.assertIs(type(row.value.value), int)
                    self.assertEqual(self.consume(owner), ())
                    self.close_and_check(fixture, owner, baseline)

    def test_clipped_hold_right_eof_point_and_outside_never_create_samples(self):
        """左侧保持不造行，半开右端排除真实更新；点及域外请求无行。

        参数: 无。返回: None。异常: 裁剪保持/右末点误当样本或空请求资源泄漏。
        """
        for window, expected in ((Interval(500_000_000, 4_000_000_000), (2_000_000_000, 3_000_000_000)),
                (Interval(2_000_000_000, 3_000_000_000), (2_000_000_000,)),
                (Interval(2_000_000_000, 2_000_000_000), ()), (Interval(5_000_000_000, 6_000_000_000), ())):
            for backend in ('reference', 'numpy'):
                fixture, owner, baseline = self.prepare(spec=CalculationDefinition('rows', 'select', window), backend=backend, size=1)
                self.assertEqual(tuple(item[0] for item in self.consume(owner)), expected)
                self.close_and_check(fixture, owner, baseline)

    def test_unconditional_invalid_false_filter_and_unknown_are_distinct(self):
        """无条件的无效原值仍TRUE；全FALSE无行；全UNKNOWN输出未知行且不把无效值填零。

        参数: 无。返回: None。异常: 三值选择或原质量被改变。
        """
        fixture, owner, baseline = self.prepare(joint=False)
        rows = self.consume(owner)
        self.assertEqual(tuple(item[2] for item in rows), (Truth.TRUE,) * 3)
        self.assertFalse(rows[-1][1].valid)
        self.assertIsNone(rows[-1][1].value)
        self.close_and_check(fixture, owner, baseline)
        for condition in (0, None):
            definitions, sources = self.definitions_and_rows()
            sources['other'] = (MemoryRow(0, {'raw.b': condition}, 0), MemoryRow(4_000_000_000, {'raw.b': condition}, 1))
            fixture, owner, baseline = self.prepare(rows_by_source=sources)
            rows = self.consume(owner)
            self.assertEqual(tuple(item[2] for item in rows), () if condition == 0 else (Truth.UNKNOWN,) * 3)
            if condition is None:
                self.assertTrue(all(item[3] & Q.MISSING for item in rows))
            self.close_and_check(fixture, owner, baseline)

    def test_invalid_plan_identity_sync_and_output_unit_reject_before_read_or_budget(self):
        """单位转换、非BOOL、异绑定及缺同步先拒绝，不消费历史也不新增金额。

        参数: 无。返回: None。异常: 无效计划进入生产或拒绝漏账。
        """
        fixture, first, baseline = self.prepare()
        self.close_and_check(fixture, first, baseline)
        # 第二份真实数据必须不同；相同原数据的稳定身份相同，不能作为异绑定负面输入。
        other, second, other_baseline = self.prepare(rows_by_source={
            'table': (MemoryRow(0, {'raw.a': 7}, 0), MemoryRow(4_000_000_000, {'raw.a': 8}, 1)),
            'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(4_000_000_000, {'raw.b': 1}, 1))})
        self.close_and_check(other, second, other_baseline)
        with patch.object(fixture.history, 'iter_groups', side_effect=AssertionError('invalid-read')) as opened:
            for kwargs in ({'spec': CalculationDefinition('bad', 'select', fixture.domain, output_unit='V')},
                    {'spec': CalculationDefinition('bad', 'time_weighted_mean', fixture.domain)}, {'condition': fixture.compiled[0]},
                    {'condition': other.compiled[1]}, {'size': True}, {'size': 0}, {'backend': 'bad'}):
                spec = kwargs.pop('spec', CalculationDefinition('rows', 'select', fixture.domain))
                with self.assertRaises((TypeError, ValueError)):
                    self.make_owner(fixture, spec, **kwargs)
            with patch.object(type(fixture.lease.bindings), 'require_synchronized', side_effect=ValueError('sync')):
                with self.assertRaises(ValueError):
                    self.make_owner(fixture, CalculationDefinition('rows', 'select', fixture.domain))
            opened.assert_not_called()
        self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_generator_close_cancel_before_after_keeps_workspace_until_retry(self):
        """生成器关闭前后取消保留frame句柄与核费用，重试完成后才能归还自有金额。

        参数: 无。返回: None。异常: 生成器尚持数组时workspace过早释放或关闭不可重试。
        """
        for after in (False, True):
            fixture, owner, baseline = self.prepare(size=7)
            next(owner)
            original = owner._rows

            class CancelClosingRows:
                """包装一个实际核生成器，只在首个close前后取消，不替换选择算法。"""

                def __init__(self):
                    """保留一次注入状态。参数: 无。返回: None。异常: 无。"""
                    self.fired = False

                def close(self):
                    """关闭实际核或首度取消。参数: 无。返回: None。异常: 一次KeyboardInterrupt。"""
                    if not self.fired:
                        self.fired = True
                        if after:
                            original.close()
                        raise KeyboardInterrupt('selection-generator-close')
                    original.close()

            # 原生成器不提前丢弃；after=False仍持frame，after=True已关但父等重试成功返回才删句柄。
            owner._rows = CancelClosingRows()
            held, workspace = owner._held_cost, owner._workspace_cost
            with self.assertRaises(KeyboardInterrupt):
                owner.close()
            self.assertIsNotNone(owner._rows)
            self.assertEqual((owner._held_cost, owner._workspace_cost), (held, workspace))
            self.close_and_check(fixture, owner, baseline)

    def test_workspace_budget_rejects_before_selector_generator_creation(self):
        """实际有限块取得后核workspace不足，选择器尚未创建，原块可恢复清理。

        参数: 无。返回: None。异常: 预算门槛晚于核分配或清理漏账。
        """
        fixture, owner, baseline = self.prepare()
        actual = owner._reserve

        def reject_workspace(amount, *, slot=None):
            """只拒核空间。参数: 金额/费用槽。返回: 原预约。异常: 指定BudgetExceededError。"""
            if slot == '_workspace_cost':
                raise BudgetExceededError('selection-workspace')
            return actual(amount, slot=slot)

        # patch实际局部import定义点；生成器创建本身也必须在workspace预约之后。
        with patch.object(owner, '_reserve', reject_workspace), patch('chronaxis.core.calculations_numpy.select_numpy') as kernel:
            with self.assertRaises(BudgetExceededError):
                next(owner)
            kernel.assert_not_called()
        self.assertTrue(owner.failed)
        self.assertIsNotNone(owner._current)
        self.close_and_check(fixture, owner, baseline)

    def test_current_row_budget_rejects_before_generator_first_allocation(self):
        """核已创建但当前行预约失败时禁止首次next，不执行数组或行装箱。

        参数: 无。返回: None。异常: 行元数据先分配或核费用遗漏。
        """
        fixture, owner, baseline = self.prepare()
        actual = owner._reserve
        visited = []

        def probe(series, spec):
            """生成器首次推进记标记。参数: 有限series/spec。返回: 空迭代器。异常: 无。"""
            visited.append('allocated')
            yield from ()

        def reject_row(amount, *, slot=None):
            """仅拒当前行费用。参数: bytes/槽。返回: 原预约。异常: 指定预算错误。"""
            if slot == '_row_cost':
                raise BudgetExceededError('selection-row')
            return actual(amount, slot=slot)

        with patch('chronaxis.core.calculations_numpy.select_numpy', probe), patch.object(owner, '_reserve', reject_row):
            with self.assertRaises(BudgetExceededError):
                next(owner)
        self.assertEqual(visited, [])
        self.assertGreater(owner._workspace_cost, 0)
        self.close_and_check(fixture, owner, baseline)

    def test_array_failure_keeps_original_exception_and_current_cleanup_owner(self):
        """首次数组分配失败保留原MemoryError及当前块/费用，不交付开放前缀。

        参数: 无。返回: None。异常: 原异常身份丢失或失败后继续出行。
        """
        fixture, owner, baseline = self.prepare()
        original = MemoryError('selection-array')

        def fail_array(series, spec):
            """模拟核首次推进失败。参数: 有限series/spec。返回: 生成器。异常: 原MemoryError。"""
            raise original
            yield  # 保持惰性核，失败发生于next而非创建阶段。

        with patch('chronaxis.core.calculations_numpy.select_numpy', fail_array):
            with self.assertRaises(MemoryError) as caught:
                next(owner)
        self.assertIs(caught.exception, original)
        self.assertTrue(owner.failed)
        self.assertIsNotNone(owner._current)
        with self.assertRaises(RuntimeError):
            next(owner)
        self.close_and_check(fixture, owner, baseline)

    def test_real_single_and_joint_constructor_persistent_cleanup_preserves_recovery(self):
        """真实子owner申请成功后失败且持续清理取消，父接管未赋值子并保留原异常。

        参数: 无。返回: None。异常: 恢复句柄丢失、借用金额清空或原MemoryError被替换。
        """
        for joint in (False, True):
            fixture, first, baseline = self.prepare(joint=joint)
            self.close_and_check(fixture, first, baseline)
            original = MemoryError('selection-child-constructor')
            budget = fixture.budget
            # 第1申请是父固定描述，第2是实际单/联合子构造；账本先成功，再抛原错误。
            reserve = self.cancel_at(budget.reserve_ram, after=True, call=2, exception=original)
            with patch.object(budget, 'reserve_ram', reserve), \
                 patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-cleanup')):
                with self.assertRaises(MemoryError) as caught:
                    self.make_owner(fixture, CalculationDefinition('rows', 'select', fixture.domain), joint=joint)
            self.assertIs(caught.exception, original)
            recovered = getattr(original, 'historical_selection_rows_cleanup_owner', None)
            self.assertIsNotNone(recovered)
            self.addCleanup(recovered.close)
            self.assertIsNotNone(recovered._blocks)
            self.close_and_check(fixture, recovered, baseline)

    def test_row_reserve_release_cancel_before_after_follow_actual_ledger(self):
        """当前行申请/归还前后取消均按实际持有金额收尾，不重复扣账。

        参数: 无。返回: None。异常: 申请成功未接管或释放成功重复抵销。
        """
        for method in ('_reserve', '_release'):
            for after in (False, True):
                fixture, owner, baseline = self.prepare(size=7)
                if method == '_release':
                    next(owner)  # 下一次推进先归还当前借出行，故此时注入行释放。
                actual = getattr(owner, method)
                fired = False

                def cancel_row(amount, *, slot=None):
                    """针对首个行槽动作取消。参数: bytes/槽。返回: 原结果。异常: 一次KeyboardInterrupt。"""
                    nonlocal fired
                    if slot == '_row_cost' and not fired:
                        fired = True
                        if after:
                            actual(amount, slot=slot)
                        raise KeyboardInterrupt('selection-row-ledger')
                    return actual(amount, slot=slot)

                # after=True由生产实际方法先更新held与行槽；close重试只归还剩余金额。
                with patch.object(owner, method, cancel_row):
                    with self.assertRaises(KeyboardInterrupt):
                        next(owner)
                self.assertTrue(owner.failed)
                self.close_and_check(fixture, owner, baseline)

    def test_current_block_and_owner_close_cancel_before_after_are_retryable(self):
        """当前块关闭与父最终费用释放分别取消，前后两种阶段都保留可重试责任。

        参数: 无。返回: None。异常: 已关块重复扣账、当前句柄丢失或借用历史被关闭。
        """
        for after in (False, True):
            fixture, owner, baseline = self.prepare(size=7)
            next(owner)
            actual = CalculationBlock.close

            def cancel_current(block):
                """取消实际当前块关闭。参数: block。返回: None。异常: 关闭前或成功后取消。"""
                if after:
                    actual(block)
                raise KeyboardInterrupt('selection-current-close')

            # generator先正常关闭；当前块未成功返回则父保留其句柄，不放弃workspace责任。
            with patch.object(CalculationBlock, 'close', cancel_current):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.assertFalse(owner.closed)
            self.close_and_check(fixture, owner, baseline)
            fixture, owner, baseline = self.prepare()
            self.consume(owner)  # EOF已释放所有子，仅固定描述费用仍归父owner持有。
            with patch.object(fixture.budget, 'release_ram', self.cancel_at(fixture.budget.release_ram,
                    target=owner._held_cost, after=after)):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.close_and_check(fixture, owner, baseline)

    def test_full_csv_refs_increase_current_row_budget_without_retaining_window(self):
        """同一CSV完整定位越长行元数据费用越大，生产始终只保留一个块和当前行。

        参数: 无。返回: None。异常: 截短CSV来源、动态费用未增长或全窗行累积。
        """
        costs = []
        end = 40_000_000_000
        sources = {'table': tuple(MemoryRow(index * 1_000_000_000, {'raw.a': index}, index) for index in range(41)),
                   'other': (MemoryRow(0, {'raw.b': 1}, 0), MemoryRow(end, {'raw.b': 1}, 1))}
        definitions = (SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'W', end+1),
                       SignalDefinition('b', 'other', 'raw.b', D.FLOAT64, '1', end+1))
        for size in (1, 40):
            fixture, owner, baseline = self.prepare(kind='csv', size=size, domain=(0, end),
                                                    rows_by_source=sources, definitions=definitions)
            # 显式提升合成压力预算，正向验证完整来源保留，未改变生产预约策略。
            fixture.budget.memory_budget_bytes = 256 * 1024 * 1024
            row = next(owner)
            costs.append((owner._row_cost, len(row.source_refs)))
            self.assertTrue(all(isinstance(ref, CSVSourceRef) for ref in row.source_refs))
            count = 1
            for row in owner:
                count += 1
                self.assertIs(owner._row, row)
                self.assertIsNotNone(owner._current)
            self.assertEqual(count, 40)
            self.close_and_check(fixture, owner, baseline)
        self.assertGreater(costs[1][0], costs[0][0])
        self.assertGreater(costs[1][1], costs[0][1])

    def test_small_spool_projects_memory_and_csv_into_current_selection_rows(self):
        """逐行计费包装后实写小缓冲并回读，当前UNKNOWN/无效值、类型及父关联不变。

        参数: 无。返回: None。异常: 暂存编解码、显式父身份或来源往返改变。
        """
        for kind in ('memory', 'csv'):
            spec = CalculationDefinition('rows', 'select', Interval(0, 4_000_000_000), scope='event')
            fixture, owner, baseline = self.prepare(kind=kind, size=2, spec=spec)
            directory = Path('work/m2-run-tests/selection-spool') / uuid4().hex
            spool = ResultSpool(fixture.budget, work_dir=directory, result_buffer_rows=1,
                                enable_selections=True, requested_tables=('selections',))
            self.addCleanup(spool.close)
            expected = []
            for sequence, row in enumerate(owner):
                # 调用方先为保留行引用与当前选择包装预约；append编码/缓冲另由spool自有预算承担。
                wrapper_cost = 65536 + 16 * _metadata_bytes((row, spec, 'dataset', 'entity', 'session', 'event-1', sequence))
                fixture.budget.reserve_ram(wrapper_cost)
                try:
                    wrapped = SummarySelectionRow(sequence, 'dataset', 'entity', 'session', spec.calculation_id,
                        'event', 'event-1', row.time_ns, row.value.value if row.value.valid else None,
                        row.value.dtype.value, row.unit, row.value.valid, row.selection.name.lower(), row.quality)
                    spool.append(wrapped)
                    expected.append((sequence, row.time_ns, row.value.value if row.value.valid else None,
                        row.value.valid, row.selection.name.lower(), row.quality))
                finally:
                    del wrapped
                    fixture.budget.release_ram(wrapper_cost)
            owner.close()
            self.assertLessEqual(spool.peak_buffer_rows, 1)
            spool.seal()
            actual = []
            # 小缓冲数学行按编码上限回读，保持父身份、业务值和状态，不重复原来源全文。
            with spool.files['selections'].open('rb') as stream:
                for payload in iter(lambda: stream.readline(spool.row_limit('selections') + 1), b''):
                    wrapped = decode_row(payload, spool.row_limit('selections'))
                    self.assertEqual((wrapped.sequence, wrapped.scope, wrapped.parent_id), (len(actual), 'event', 'event-1'))
                    actual.append((wrapped.sequence, wrapped.time_ns, wrapped.value, wrapped.valid,
                                   wrapped.selection, wrapped.quality))
            self.assertEqual(actual, expected)
            spool.close()
            self.close_and_check(fixture, owner, baseline)

    def test_exhaustion_releases_live_rows_but_external_retention_needs_own_budget(self):
        """EOF只保留固定描述，外部跨next保留行须自己计费；显式close后原行仍冻结。

        参数: 无。返回: None。异常: EOF伪称closed、残留核费用或生产扣掉外部金额。
        """
        fixture, owner, baseline = self.prepare(size=7)
        row = next(owner)
        external_cost = 4096 + 16 * _metadata_bytes(row)
        fixture.budget.reserve_ram(external_cost)
        before = self.summary(row)
        try:
            # 这里只保留一个已计费的外部行；其余即时消费不保存全窗列表。
            for current in owner:
                self.assertIs(owner._row, current)
            self.assertTrue(owner.exhausted)
            self.assertFalse(owner.closed)
            self.assertEqual((owner._blocks, owner._current, owner._rows, owner._row), (None,) * 4)
            self.assertEqual((owner._workspace_cost, owner._row_cost), (0, 0))
            self.assertGreater(owner._held_cost, 0)
            with self.assertRaises(StopIteration):
                next(owner)
            owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline + external_cost)
            self.assertEqual(self.summary(row), before)
            with self.assertRaises(ResultClosedError):
                next(owner)
        finally:
            fixture.budget.release_ram(external_cost)
        self.close_and_check(fixture, owner, baseline)
