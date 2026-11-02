"""用独立手算验证已求值贡献的原序累计、整批原子性与真实预算恢复。

每条LegacySumContribution已由调用者给出有限float或typed skip；本测试不执行表达式、
period/factor、CAN或旧缓存。800来自两条预先手算的400；浮点顺序哨兵严格为1，
两条4e-7保未舍入8e-7。参考与NumPy分别对手算断言，跨1/2/7批及空批保持一致，
不把NumPy当参考，也不把合成输入称为旧ChrgInfo全兼容或实际来源验证。

真实ResourceBudget保调用方借款和另一活累计器；故障仅注入实际reserve/release前后，
核原异常对象、最高legacy_sum_cleanup_owner、批状态未提交和费用恢复。持续释放前
失败至少三次后只用同owner.close恢复，释放后取消不得重复抵账。不构造假owner，
不虚构FD或整进程RSS保证；所有声明与小输入均在内存，不创建文件或读取Ref。
"""

from dataclasses import FrozenInstanceError
import gc
from types import MappingProxyType
import unittest
from unittest.mock import patch
import weakref

from chronaxis.core.models import SourceRef
from chronaxis.core.types import QualityFlag as Q
from chronaxis.legacy.updates import LegacyDecodedUpdate
from chronaxis.legacy.sum import (LegacySkipReason as R, LegacySumAccumulator,
    LegacySumContribution, LegacySumSnapshot)
from chronaxis.results import BudgetExceededError, ResourceBudget, ResultClosedError


class ForeignFloat(float):
    """模拟非原生浮点，防止贡献值通过隐式float转换绕过native合同。"""


class ForeignTuple(tuple):
    """模拟tuple子类，证明有限批入口只接受明确的精确tuple。"""


class ObservedAdd:
    """透传真实NumPy ufunc，仅为accumulate返回的实际数组保存弱引用。"""

    def __init__(self, operation, references):
        """保实际ufunc与外部弱引用列表，不持有数值输入或输出强引用。

        参数: operation为原np.add；references为本例观察列表。返回: 透传观察器。
        异常: 无；本测试不改变原运算、dtype、顺序或数值。
        """
        self.operation, self.references = operation, references

    def __call__(self, *args, **kwargs):
        """透传原加法调用。参数: 原args/kwargs。返回: 原结果。异常: 原错误不变。"""
        return self.operation(*args, **kwargs)

    def __getattr__(self, name):
        """透传未观察的ufunc属性。参数: name属性名。返回: 原属性。异常: 原属性错误。"""
        return getattr(self.operation, name)

    def accumulate(self, *args, **kwargs):
        """执行实际前缀累计并只记weakref。参数: 原args/kwargs。返回: 原数组。异常: 原错误。"""
        result = self.operation.accumulate(*args, **kwargs)
        self.references.append(weakref.ref(result))
        return result


class LegacySumTests(unittest.TestCase):
    """每例真实构造累计器；共享账本的其他owner不属于本次清理责任。"""

    def contribution(self, index, value=400.0, reason=None, **changes):
        """构造一条显式已求值贡献，不在夹具内调用被测数值核计算真值。

        参数: index为求值序号；value/reason为已知贡献或明确skip；changes覆盖原更新。
        返回: LegacySumContribution。异常: 原更新或贡献校验错误直接传播。
        """
        fields = dict(time_ns=0, source='bus', channel=0, frame_id=0x100,
            is_extended=False, is_fd=False, is_remote=False, is_error=False,
            source_ref=SourceRef('session', 'bus', 'Raw.Power'), sequence=index,
            evaluation_index=index, values={'Raw.Power': 4000.0, 'period': 0.1})
        fields.update(changes)
        return LegacySumContribution(LegacyDecodedUpdate(**fields), value, reason)

    def owner(self, backend='reference', *, budget=None, max_batch_rows=64):
        """用真实共享预算构造累计器并登记正常最终清理。

        参数: backend/max_batch_rows为冻结选项；budget省略时新建64MiB账本。
        返回: (budget,owner)。异常: 构造或预算原错误传播，不用__new__模拟owner。
        """
        if budget is None:
            budget = ResourceBudget(64 * 1024**2)
        owner = LegacySumAccumulator(budget, 'session', 'bus', legacy_policy='explicit-contributions-v1',
            backend=backend, max_batch_rows=max_batch_rows)
        self.addCleanup(owner.close)
        return budget, owner

    def assert_snapshot(self, owner, value, evaluations, contributions, skipped, reasons=None):
        """核固定公开快照、计数和全部原因键，返回快照供不可变或历史值比较。

        参数: owner和独立预期；reasons只列非零原因，其余四枚举原因必须为0。
        返回: 实际LegacySumSnapshot。异常: 任一身份/数值/分类/计数不符使测试失败。
        """
        snapshot = owner.snapshot()
        self.assertIs(type(snapshot), LegacySumSnapshot)
        self.assertEqual((snapshot.session_id, snapshot.source, snapshot.legacy_policy),
            ('session', 'bus', 'explicit-contributions-v1'))
        self.assertEqual((snapshot.value, snapshot.evaluation_count, snapshot.contribution_count,
            snapshot.skipped_count), (value, evaluations, contributions, skipped))
        if value is not None:
            self.assertIs(type(snapshot.value), float)
        self.assertIs(type(snapshot.skip_counts), MappingProxyType)
        self.assertEqual(tuple(snapshot.skip_counts), tuple(R))
        expected = dict.fromkeys(R, 0)
        expected.update({} if reasons is None else reasons)
        self.assertEqual(dict(snapshot.skip_counts), expected)
        reason = 'no_evaluations' if evaluations == 0 else 'all_skipped' if contributions == 0 else None
        self.assertEqual(snapshot.reason, reason)
        return snapshot

    def recovery(self, error, expected=None):
        """从原异常取得真实最高累计器，不沿私有子槽替代恢复接口。

        参数: error为注入的原错误；expected可指定已返回的同一owner。
        返回: 实际LegacySumAccumulator。异常: 无恢复owner、类型或身份不符使断言失败。
        """
        owner = getattr(error, 'legacy_sum_cleanup_owner', None)
        self.assertIs(type(owner), LegacySumAccumulator)
        if expected is not None:
            self.assertIs(owner, expected)
        self.addCleanup(owner.close)
        return owner

    def borrowed(self):
        """保留调用方777字节及另一真实活累计器，供本次owner故障隔离核对。

        参数: 无。返回: (budget,sibling,借用基线,sibling固定快照)。
        异常: 真实构造/预算错误传播；清理只在该夹具全部owner结束后归还777。
        """
        budget = ResourceBudget(64 * 1024**2)
        budget.reserve_ram(777)
        self.addCleanup(self.return_borrowed, budget)
        _, sibling = self.owner(budget=budget)
        sibling.consume((self.contribution(0, 17.0),))
        return budget, sibling, budget.ram_bytes, sibling.snapshot()

    def return_borrowed(self, budget):
        """最后只归还调用方777字节，核没有owner抵销借款或残留本层费用。

        参数: budget为该夹具共享账本。返回: None。异常: 余额不符或释放错误失败。
        """
        self.assertEqual(budget.ram_bytes, 777)
        budget.release_ram(777)
        self.assertEqual(budget.ram_bytes, 0)

    def assert_borrowed(self, budget, sibling, baseline, snapshot):
        """核另一累计器仍活且内容未变，并核真实借用费用恰回基线。

        参数: 实际预算/sibling及先前基线/快照。返回: None。异常: 误关或漏费失败。
        """
        self.assertFalse(sibling.closed)
        self.assertEqual(sibling.snapshot(), snapshot)
        self.assertEqual(budget.ram_bytes, baseline)

    def test_contribution_accepts_only_finite_native_float_or_typed_skip(self):
        """原值质量只是诊断，已有贡献不重新求值；None与正常0必须明确区分。

        参数: 无。返回: None。异常: 非finite/native值或不闭合skip形状被接受时失败。
        """
        update = self.contribution(0).update
        valid = LegacySumContribution(update, 0.0)
        self.assertIs(valid.update, update)
        self.assertEqual(valid.value, 0.0)
        self.assertIsNone(valid.skip_reason)
        for reason in R:
            skipped = LegacySumContribution(update, None, reason)
            self.assertIsNone(skipped.value)
            self.assertIs(skipped.skip_reason, reason)
        # 输入quality不授权累计器重新套TTL/掩码，提供者显式给出的有限贡献仍存在。
        diagnostic = self.contribution(1, 3.0, quality=Q.MISSING | Q.ESTIMATED,
            values={'Raw.Power': None, 'raw_nan': float('nan')})
        self.assertEqual(diagnostic.value, 3.0)
        self.assertEqual(diagnostic.update.quality, Q.MISSING | Q.ESTIMATED)
        for value in (1, True, '1', ForeignFloat(1.0)):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(TypeError):
                    LegacySumContribution(update, value)
        for value in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(nonfinite=value):
                with self.assertRaises(ValueError):
                    LegacySumContribution(update, value)
        for value, reason, error in ((None, None, ValueError), (1.0, R.MISSING_INPUT, ValueError),
                (None, 'missing_input', TypeError), (None, 0, TypeError)):
            with self.subTest(value=value, reason=reason):
                with self.assertRaises(error):
                    LegacySumContribution(update, value, reason)
        with self.assertRaises(TypeError):
            LegacySumContribution(object(), 1.0)
        with self.assertRaises(FrozenInstanceError):
            valid.value = 2.0

    def test_snapshot_distinguishes_empty_all_skip_zero_and_keeps_existing_carry(self):
        """空与全skip为None，贡献和0为0.0，后续全skip/空批不清掉已有carry。

        参数: 无。返回: None。异常: 虚构正常0、重置carry或快照可变时失败。
        """
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                budget, owner = self.owner(backend)
                empty = self.assert_snapshot(owner, None, 0, 0, 0)
                self.assertIsNone(owner.consume(()))
                self.assertEqual(owner.snapshot(), empty)
                owner.consume((self.contribution(0, None, R.MISSING_INPUT),))
                skipped = self.assert_snapshot(owner, None, 1, 0, 1, {R.MISSING_INPUT: 1})
                owner.consume((self.contribution(1, 4.0), self.contribution(2, -4.0)))
                zero = self.assert_snapshot(owner, 0.0, 3, 2, 1, {R.MISSING_INPUT: 1})
                owner.consume((self.contribution(3, None, R.CONDITION_FALSE),))
                owner.consume(())
                self.assert_snapshot(owner, 0.0, 4, 2, 2, {R.MISSING_INPUT: 1, R.CONDITION_FALSE: 1})
                self.assertIsNone(empty.value)
                self.assertIsNone(skipped.value)
                self.assertEqual(zero.evaluation_count, 3)
                with self.assertRaises(FrozenInstanceError):
                    zero.value = 9.0
                with self.assertRaises(TypeError):
                    zero.skip_counts[R.MISSING_INPUT] = 9
                owner.close()
                owner.close()
                self.assertEqual(budget.ram_bytes, 0)
                with self.assertRaises(ResultClosedError):
                    owner.snapshot()
                with self.assertRaises(ResultClosedError):
                    owner.consume(())

    def test_independent_truth_and_strict_left_fold_survive_batches_one_two_seven(self):
        """两核分别对800、左折叠1、未舍入8e-7手算断言，批间不先归约或舍入。

        参数: 无。返回: None。异常: 与手算不同、跨批数值变动或重复计数时失败。
        """
        cases = (((400.0, 400.0), 800.0), ((1e16, 1.0, -1e16, 1.0), 1.0),
            ((4e-7, 4e-7), 8e-7))
        for values, expected in cases:
            # 参考真值是明确旧顺序的独立Python左折叠，不调用任何被测数值核。
            oracle = 0.0
            for value in values:
                oracle += value
            self.assertEqual(oracle.hex(), expected.hex())
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(values=values, backend=backend, batch_rows=size):
                        budget, owner = self.owner(backend, max_batch_rows=size)
                        records = tuple(self.contribution(index, value) for index, value in enumerate(values))
                        for begin in range(0, len(records), size):
                            owner.consume(())
                            owner.consume(records[begin:begin + size])
                        snapshot = self.assert_snapshot(owner, expected, len(records), len(records), 0)
                        self.assertEqual(snapshot.value.hex(), oracle.hex())
                        owner.close()
                        self.assertEqual(budget.ram_bytes, 0)

    def test_skips_same_frame_sections_and_evaluation_gaps_preserve_order_and_counts(self):
        """skip也占求值身份，同刻多帧/同帧section及间隙在两核与切批中全部保留。

        参数: 无。返回: None。异常: skip未核顺序、同帧被去重或质量自动过滤时失败。
        """
        records = (self.contribution(0, 400.0, sequence=7, evaluation_index=11),
            self.contribution(1, None, R.MISSING_INPUT, sequence=7, evaluation_index=15),
            self.contribution(2, 400.0, sequence=8, evaluation_index=16, quality=Q.MISSING),
            self.contribution(3, None, R.CONDITION_FALSE, sequence=9, evaluation_index=20),
            self.contribution(4, None, R.EVALUATION_ERROR, sequence=10, evaluation_index=21),
            self.contribution(5, None, R.NONFINITE_INPUT, sequence=11, evaluation_index=24))
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                with self.subTest(backend=backend, batch_rows=size):
                    budget, owner = self.owner(backend, max_batch_rows=size)
                    for begin in range(0, len(records), size):
                        owner.consume(records[begin:begin + size])
                    self.assert_snapshot(owner, 800.0, 6, 2, 4, dict.fromkeys(R, 1))
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_bad_batch_suffix_rolls_back_all_counts_value_and_hidden_order(self):
        """首项合法但后缀错误仍整批拒绝，原首项随后可重新提交而不重复计数。

        参数: 无。返回: None。异常: 候选提前提交或恢复时旧身份被污染即失败。
        """
        for backend in ('reference', 'numpy'):
            for failure in ('duplicate_skip', 'time_back', 'sequence_back', 'other_source', 'not_contribution'):
                with self.subTest(backend=backend, failure=failure):
                    budget, owner = self.owner(backend)
                    owner.consume((self.contribution(0, 2.0),))
                    before = owner.snapshot()
                    first = self.contribution(1, 3.0, time_ns=10)
                    if failure == 'duplicate_skip':
                        bad = self.contribution(1, None, R.MISSING_INPUT, time_ns=10)
                    elif failure == 'time_back':
                        bad = self.contribution(2, 4.0, time_ns=9)
                    elif failure == 'sequence_back':
                        bad = self.contribution(2, 4.0, time_ns=10, sequence=0)
                    elif failure == 'other_source':
                        bad = self.contribution(2, 4.0, time_ns=10, source='other',
                            source_ref=SourceRef('session', 'other', 'P'))
                    else:
                        bad = object()
                    with self.assertRaises(TypeError if failure == 'not_contribution' else ValueError):
                        owner.consume((first, bad))
                    self.assertEqual(owner.snapshot(), before)
                    owner.consume((first, self.contribution(2, 4.0, time_ns=10)))
                    self.assert_snapshot(owner, 9.0, 3, 3, 0)
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_intermediate_overflow_rejects_even_when_later_terms_would_recover(self):
        """1e308再加1e308的中间溢出必须拒绝，不能靠末尾负项或总和掩盖。

        参数: 无。返回: None。异常: 非有限中间值被放行或失败改变carry/身份时失败。
        """
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                budget, owner = self.owner(backend)
                owner.consume((self.contribution(0, 1e308),))
                before = owner.snapshot()
                with self.assertRaises(OverflowError):
                    owner.consume((self.contribution(1, 1e308), self.contribution(2, -1e308)))
                self.assertEqual(owner.snapshot(), before)
                owner.consume((self.contribution(1, -1e308),))
                self.assert_snapshot(owner, 0.0, 2, 2, 0)
                owner.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_retained_numpy_overflow_traceback_does_not_keep_released_work_arrays(self):
        """保留真实溢出异常及traceback时，两类已抵销预算的实际NumPy临时数组均释放。

        参数: 无。返回: None。异常: 观察未命中、数组被traceback保活、原错/状态变化时失败。
        观察器只转发原empty及ufunc运算，不假造数组或数值，不清除/替换原traceback。
        """
        import numpy as np
        budget, owner = self.owner('numpy')
        owner.consume((self.contribution(0, 1e308),))
        before, baseline = owner.snapshot(), budget.ram_bytes
        chain_refs, prefix_refs = [], []
        original_empty, original_add = np.empty, np.add

        def observe_empty(*args, **kwargs):
            """调用真实数组分配只存弱引用。参数: 原args/kwargs。返回: 原数组。异常: 原分配错误。"""
            array = original_empty(*args, **kwargs)
            chain_refs.append(weakref.ref(array))
            return array

        retained_error = None
        with patch.object(np, 'empty', new=observe_empty), \
                patch.object(np, 'add', new=ObservedAdd(original_add, prefix_refs)):
            try:
                owner.consume((self.contribution(1, 1e308), self.contribution(2, -1e308)))
            except OverflowError as error:
                # assertRaises会清除异常traceback；这里手动保存真实异常，保留原资源风险条件。
                retained_error = error
        self.assertIs(type(retained_error), OverflowError)
        retained_traceback = retained_error.__traceback__
        self.assertIsNotNone(retained_traceback)
        self.assertIs(getattr(retained_error, 'legacy_sum_cleanup_owner', None), owner)
        self.assertEqual((len(chain_refs), len(prefix_refs)), (1, 1))
        self.assertEqual(owner.snapshot(), before)
        self.assertEqual(budget.ram_bytes, baseline)
        # 回收不删除仍可达的异常/traceback；若帧局部仍持数组，弱引用此时依然非空。
        gc.collect()
        for reference in chain_refs + prefix_refs:
            self.assertIsNone(reference())
        self.assertIs(retained_error.__traceback__, retained_traceback)
        owner.consume((self.contribution(1, -1e308),))
        self.assert_snapshot(owner, 0.0, 2, 2, 0)
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)
        self.assertIs(retained_error.__traceback__, retained_traceback)

    def test_exact_tuple_limit_and_real_capacity_refuse_without_commit(self):
        """容器与超批在实际申请前拒绝，容量不足保原状态且不增加账本余额。

        参数: 无。返回: None。异常: 接受无界输入、先预付超批或预算失败提交时失败。
        """
        budget, owner = self.owner(max_batch_rows=1)
        before = owner.snapshot()
        item = self.contribution(0)
        for value in ([item], ForeignTuple((item,)), iter((item,)), (item, self.contribution(1))):
            with self.subTest(batch_type=type(value).__name__):
                with patch.object(budget, 'reserve_ram', wraps=budget.reserve_ram) as reserve:
                    with self.assertRaises(ValueError if type(value) is tuple else TypeError):
                        owner.consume(value)
                reserve.assert_not_called()
                self.assertEqual(owner.snapshot(), before)
        # 从真实相同构造观察固定金额，再建不可变的小限额账本；不修改运行中的预算。
        fixed = budget.ram_bytes
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)
        limited = ResourceBudget(fixed + 1)
        _, constrained = self.owner(budget=limited, max_batch_rows=1)
        self.assertEqual(limited.ram_bytes, fixed)
        snapshot = constrained.snapshot()
        with patch.object(constrained, '_candidate', wraps=constrained._candidate) as candidate:
            with self.assertRaises(BudgetExceededError):
                constrained.consume((item,))
        candidate.assert_not_called()
        self.assertEqual(constrained.snapshot(), snapshot)
        self.assertEqual(limited.ram_bytes, fixed)
        constrained.close()
        self.assertEqual(limited.ram_bytes, 0)

    def test_shared_budget_close_preserves_borrowed_owner_and_snapshot(self):
        """本累计器正常关闭只还自身费用，777借款和另一活累计器仍可继续用。

        参数: 无。返回: None。异常: 误关/抵销其他owner或旧快照跟着变化时失败。
        """
        budget, sibling, baseline, sibling_snapshot = self.borrowed()
        _, owner = self.owner('numpy', budget=budget)
        owner.consume((self.contribution(0, 0.0),))
        own_snapshot = self.assert_snapshot(owner, 0.0, 1, 1, 0)
        owner.close()
        owner.close()
        self.assert_borrowed(budget, sibling, baseline, sibling_snapshot)
        sibling.consume((self.contribution(1, 1.0),))
        self.assert_snapshot(sibling, 18.0, 2, 2, 0)
        self.assertEqual(sibling_snapshot.value, 17.0)
        self.assertEqual(own_snapshot.value, 0.0)

    def test_constructor_reserve_cancel_before_after_cleans_real_transaction(self):
        """真实构造reserve前后取消均保原KI，实际费用清理后回借用基线。

        参数: 无。返回: None。异常: 注入未命中、取消替换或构造费用泄漏时失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                budget, sibling, baseline, snapshot = self.borrowed()
                reserve = budget.reserve_ram
                marker, calls = KeyboardInterrupt('construct reserve cancel'), []

                def fail_reserve(amount):
                    """在本次真实申请前/后取消。参数: 实际amount。返回: 无。异常: 同一marker。"""
                    calls.append(amount)
                    if after:
                        reserve(amount)
                    raise marker

                with patch.object(budget, 'reserve_ram', side_effect=fail_reserve):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        LegacySumAccumulator(budget, 'session', 'bus', legacy_policy='explicit-contributions-v1')
                self.assertIs(caught.exception, marker)
                self.assertEqual(len(calls), 1)
                self.assertGreater(calls[0], 0)
                recovery = getattr(marker, 'legacy_sum_cleanup_owner', None)
                if recovery is not None:
                    self.assertIs(type(recovery), LegacySumAccumulator)
                    recovery.close()
                    self.assertTrue(recovery.closed)
                self.assert_borrowed(budget, sibling, baseline, snapshot)

    def test_consume_reserve_cancel_before_after_is_atomic_and_retryable(self):
        """批预约取消不提交累计或顺序，临时清理成功后同一批可以显式重新提交。

        参数: 无。返回: None。异常: 取消未命中、业务状态提前变化或费用未清时失败。
        """
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                with self.subTest(backend=backend, after=after):
                    budget, owner = self.owner(backend)
                    owner.consume((self.contribution(0, 2.0),))
                    before, baseline = owner.snapshot(), budget.ram_bytes
                    reserve = budget.reserve_ram
                    marker, calls = KeyboardInterrupt('batch reserve cancel'), []

                    def fail_reserve(amount):
                        """保本笔申请原前后事实。参数: 实际amount。返回: 无。异常: 同一marker。"""
                        calls.append(amount)
                        if after:
                            reserve(amount)
                        raise marker

                    with patch.object(budget, 'reserve_ram', side_effect=fail_reserve):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            owner.consume((self.contribution(1, 3.0),))
                    self.assertIs(caught.exception, marker)
                    self.assertTrue(calls and all(amount > 0 for amount in calls))
                    self.recovery(marker, owner)
                    self.assertEqual(owner.snapshot(), before)
                    self.assertEqual(budget.ram_bytes, baseline)
                    owner.consume((self.contribution(1, 3.0),))
                    self.assert_snapshot(owner, 5.0, 2, 2, 0)
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_temporary_release_cancel_keeps_batch_atomic_and_actual_fee(self):
        """临时费释放前取消须关闭恢复，释放后取消可续批，二者都不得提交候选。

        参数: 无。返回: None。异常: 候选先提交、未清临时槽可覆盖或重复还费时失败。
        """
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                with self.subTest(backend=backend, after=after):
                    budget, sibling, borrowed, sibling_snapshot = self.borrowed()
                    _, owner = self.owner(backend, budget=budget)
                    owner.consume((self.contribution(0, 2.0),))
                    before, state, baseline = owner.snapshot(), owner._state, budget.ram_bytes
                    release = budget.release_ram
                    marker, calls = KeyboardInterrupt('batch release cancel'), []

                    def fail_release(amount):
                        """在实际临时费释放前后取消。参数: 原amount。返回: 无。异常: 同一marker。"""
                        calls.append(amount)
                        if after:
                            release(amount)
                        raise marker

                    with patch.object(budget, 'release_ram', side_effect=fail_release):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            owner.consume((self.contribution(1, 3.0),))
                    self.assertIs(caught.exception, marker)
                    self.assertTrue(calls and all(amount > 0 for amount in calls))
                    self.recovery(marker, owner)
                    self.assertIs(owner._state, state)
                    if after:
                        self.assertEqual(budget.ram_bytes, baseline)
                        self.assertEqual(owner.snapshot(), before)
                        owner.consume((self.contribution(1, 3.0),))
                        self.assert_snapshot(owner, 5.0, 2, 2, 0)
                    else:
                        self.assertEqual(budget.ram_bytes, baseline + calls[0])
                        with self.assertRaises(ResultClosedError):
                            owner.snapshot()
                        with self.assertRaises(ResultClosedError):
                            owner.consume((self.contribution(1, 3.0),))
                    owner.close()
                    owner.close()
                    self.assert_borrowed(budget, sibling, borrowed, sibling_snapshot)

    def test_close_persistent_release_before_and_cancel_after_do_not_credit_twice(self):
        """释放前持续至少三次仍由同owner负责，释放后KI则不能重还已完成交易。

        参数: 无。返回: None。异常: 假关闭、丢最高owner、覆盖原错或重复抵账时失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                budget, sibling, baseline, snapshot = self.borrowed()
                _, owner = self.owner(budget=budget)
                owner.consume((self.contribution(0, 2.0),))
                release = budget.release_ram
                marker, calls = KeyboardInterrupt('owner close release cancel'), []

                def fail_release(amount):
                    """真实固定费前持续失败或后一次取消。参数: amount。返回: 无。异常: marker原对象。"""
                    calls.append(amount)
                    if after:
                        release(amount)
                    raise marker

                with patch.object(budget, 'release_ram', side_effect=fail_release):
                    for attempt in range(1 if after else 3):
                        with self.subTest(close_attempt=attempt):
                            with self.assertRaises(KeyboardInterrupt) as caught:
                                owner.close()
                            self.assertIs(caught.exception, marker)
                            self.recovery(marker, owner)
                    if after:
                        owner.close()
                        self.assertEqual(len(calls), 1)
                    else:
                        self.assertGreaterEqual(len(calls), 3)
                        self.assertFalse(owner.closed)
                    with self.assertRaises(ResultClosedError):
                        owner.snapshot()
                    with self.assertRaises(ResultClosedError):
                        owner.consume(())
                owner.close()
                owner.close()
                self.assertTrue(owner.closed)
                self.assert_borrowed(budget, sibling, baseline, snapshot)

    def test_unreturned_constructor_owner_survives_primary_and_persistent_cleanup_error(self):
        """构造申请已成功后KI加持续清理副错，未返回owner仍可实际恢复至借用基线。

        参数: 无。返回: None。异常: 主错被替换、未返回owner丢失或借用费用被抵销时失败。
        """
        budget, sibling, baseline, snapshot = self.borrowed()
        reserve = budget.reserve_ram
        primary, secondary = KeyboardInterrupt('reserve after primary'), RuntimeError('persistent release secondary')
        reserved, released = [], []

        def reserve_after(amount):
            """真实申请后保原取消。参数: amount。返回: 无。异常: primary原对象。"""
            reserve(amount)
            reserved.append(amount)
            raise primary

        def release_before(amount):
            """持续阻止本真实费用释放。参数: amount。返回: 无。异常: secondary原对象。"""
            released.append(amount)
            raise secondary

        with patch.object(budget, 'reserve_ram', side_effect=reserve_after), \
                patch.object(budget, 'release_ram', side_effect=release_before):
            with self.assertRaises(KeyboardInterrupt) as caught:
                LegacySumAccumulator(budget, 'session', 'bus', legacy_policy='explicit-contributions-v1')
            self.assertIs(caught.exception, primary)
            owner = self.recovery(primary)
            for _ in range(3):
                with self.assertRaises(RuntimeError) as cleanup:
                    owner.close()
                self.assertIs(cleanup.exception, secondary)
                self.recovery(secondary, owner)
            self.assertEqual(len(reserved), 1)
            self.assertGreaterEqual(len(released), 3)
            self.assertTrue(all(amount == reserved[0] for amount in released))
            self.assertEqual(budget.ram_bytes, baseline + reserved[0])
            self.assertTrue(getattr(primary, '__notes__', ()))
        owner.close()
        owner.close()
        self.assertTrue(owner.closed)
        self.assert_borrowed(budget, sibling, baseline, snapshot)


if __name__ == '__main__':
    # 仅直接运行才交给unittest；正式运行、证据和完整回归由根任务统一调度。
    unittest.main()
