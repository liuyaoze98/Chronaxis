"""验证真实回读链中尚未赋值的子构造失败仍有资源恢复入口。

输入是work内的合成CSV封存历史及两个独立后端的实际绑定。
故障发生在新owner第一次真实预算申请之后，释放可在操作前或后取消。
预期保留原异常身份、借用资源及费用，只关闭本次新构造的自有对象。
测试捕获close对象仅为回收旧实现的泄漏，不能替代生产异常上的恢复句柄。
全部工厂最终关闭后检查RAM为0，不读取旧日志、不修改RefProjects。
"""

# 模块别名防止unittest再次收集工厂中的测试类。
from contextlib import ExitStack
import unittest
from unittest.mock import patch
import test_window_replay as real_history
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.execution import state as state_module
from chronaxis.execution import hold as hold_module
from chronaxis.execution import expressions as expressions_module
from chronaxis.execution import boundaries as boundaries_module
from chronaxis.execution import window_replay as replay_module
from chronaxis.execution import calculation_blocks as blocks_module


class NestedConstructorRecoveryTests(unittest.TestCase):
    """按四个新owner逐一验证直接使用、回读父owner和分块祖先的交接。"""

    def prepare(self, backend):
        """创建真实小CSV历史及借用上游，不在故障注入期间构造工厂。

        参数: backend为reference或numpy。返回: 原真实fixture。
        异常: 原工厂读写、绑定或最终清理错误。
        """
        helper = real_history.WindowReplayTests('runTest')
        fixture = helper.fixture(backend=backend, kind='csv')
        self.addCleanup(self.cleanup_factory, helper)
        return fixture

    def cleanup_factory(self, helper):
        """关闭借用链并保留原工厂RAM零断言。

        参数: helper为已注册清理的真实工厂。返回: None。异常: 清理或预算断言失败。
        """
        self.assertTrue(helper.doCleanups())

    def layers(self):
        """列出真实类、恢复字段和窗口父owner持有它的字段。

        参数: 无。返回: 四个固定三元组。异常: 无。
        """
        return ((state_module.LatestSignalState, 'state_cleanup_owner', '_state'),
                (hold_module.HoldQueries, 'hold_queries_cleanup_owner', '_holds'),
                (expressions_module.ExpressionQueries, 'expression_queries_cleanup_owner', '_expressions'),
                (boundaries_module.BoundaryQueries, 'boundary_queries_cleanup_owner', '_boundaries'))

    def invoke(self, fixture, cls, kind, backend):
        """从直接子owner或真实回读祖先启动构造。

        参数: fixture为原借用资源，cls为故障层，kind为direct/replay/blocks，backend为实际后端。
        返回: 新owner。异常: 本测试注入的原构造异常及清理取消。
        """
        if kind == 'direct':
            if cls is state_module.LatestSignalState:
                return cls(fixture.budget, tuple(fixture.state.definitions.values()), fixture.state.session_id)
            if cls is hold_module.HoldQueries:
                return cls(fixture.state, fixture.holds._context)
            if cls is expressions_module.ExpressionQueries:
                return cls(fixture.holds, fixture.lease.bindings, fixture.compiled)
            return cls(fixture.expressions)
        args = (fixture.history, fixture.holds._context, fixture.lease.bindings, fixture.compiled[0])
        if kind == 'replay':
            return replay_module.HistoricalWindowReplay(*args, Interval(2, 7), backend=backend)
        return blocks_module.HistoricalCalculationBlocks(*args, CalculationDefinition('area', 'integral', Interval(2, 7)), backend=backend)

    def capture_close(self, original, captured):
        """记录实际close接收的owner，包装仍执行生产关闭。

        参数: original为真实方法，captured为测试回收列表。返回: 包装方法。
        异常: 原关闭或注入取消传播。
        """
        def close(owner):
            """保留真实owner后调用原关闭。

            参数: owner为实际对象。返回: None。异常: 原close错误。
            """
            if all(item is not owner for item in captured):
                captured.append(owner)
            return original(owner)
        return close

    def faulting_init(self, original, fixture, error, reserve_after=True, charge_index=1):
        """仅在目标层指定申请处失败，保证执行真实构造而非虚假替身。

        参数: original为真实构造方法；fixture为借用预算；error为原异常；reserve_after决定失败前是否记账；
            charge_index为从1开始的目标申请序号，用于累计多笔费用之后失败。
        返回: 包装构造。异常: error原对象及真实清理错误。
        """
        def initialize(owner, *args, **kwargs):
            """在当前子构造内部限定一次真实申请故障。

            参数: owner为新子对象，args/kwargs是原构造输入。返回: None。异常: 注入原异常。
            """
            reserve = fixture.budget.reserve_ram
            charges = 0
            def reserve_then_fail(amount):
                """指定申请按目标时刻失败，其余申请保留原行为。

                参数: amount为非负字节。返回: None。异常: 目标error及原预算错误。
                """
                nonlocal charges
                charges += 1
                if charges == charge_index:
                    if reserve_after:
                        reserve(amount)
                    raise error
                return reserve(amount)
            with patch.object(fixture.budget, 'reserve_ram', reserve_then_fail):
                return original(owner, *args, **kwargs)
        return initialize

    def verify_case(self, cls, recovery_name, parent_field, kind, backend, *, persistent=True,
                    release_after=False, reserve_after=True, cancel_error=False, charge_index=1):
        """运行一条实际故障链并核对原异常、恢复所有权和借用预算。

        参数: cls/recovery_name/parent_field定义故障层；kind为入口；backend为实际后端；
            persistent决定释放持续或一次取消，release_after决定是否已抵销，reserve_after决定构造已申请；
            cancel_error决定原异常为取消或MemoryError，charge_index为目标申请序号。
        返回: None。异常: 真实结构、异常身份、恢复句柄或借用资源断言失败。
        """
        fixture = self.prepare(backend)
        baseline, captured = fixture.budget.ram_bytes, []
        error = KeyboardInterrupt('original-constructor-cancel') if cancel_error else MemoryError('original-constructor-memory')
        actual_init, actual_release = cls.__init__, fixture.budget.release_ram
        releases = 0
        def release(amount):
            """按首回或每回注入释放取消，原金额不做测试侧补偿。

            参数: amount为当前owner自有字节。返回: None。异常: 指定KeyboardInterrupt。
            """
            nonlocal releases
            releases += 1
            if persistent or releases == 1:
                if release_after:
                    actual_release(amount)
                raise KeyboardInterrupt('cleanup-release-cancel')
            return actual_release(amount)
        try:
            with ExitStack() as patches:
                # 捕获所有真实层，仅用于失败基线也可最终回收，不据此判定产品恢复成功。
                for owner_class, _, _ in self.layers():
                    patches.enter_context(patch.object(owner_class, 'close',
                        self.capture_close(owner_class.close, captured)))
                for owner_class in (replay_module.HistoricalWindowReplay, blocks_module.HistoricalCalculationBlocks):
                    patches.enter_context(patch.object(owner_class, 'close',
                        self.capture_close(owner_class.close, captured)))
                patches.enter_context(patch.object(cls, '__init__',
                    self.faulting_init(actual_init, fixture, error, reserve_after, charge_index)))
                patches.enter_context(patch.object(fixture.budget, 'release_ram', release))
                # BaseException容许原基线吞掉MemoryError，以严格身份断言记录实质失败。
                with self.assertRaises(BaseException) as raised:
                    self.invoke(fixture, cls, kind, backend)
            self.assertIs(raised.exception, error, '清理取消不能替换原构造异常')
            if persistent:
                child = getattr(error, recovery_name, None)
                if not release_after and reserve_after:
                    self.assertIsNotNone(child, '未赋值子构造必须交出自身恢复句柄')
                    self.assertFalse(child.closed)
                recovery = child
                if kind != 'direct':
                    parent = getattr(error, 'window_replay_cleanup_owner', None)
                    if child is not None and not child.closed:
                        self.assertIsNotNone(parent)
                        self.assertIs(getattr(parent, parent_field), child)
                    recovery = parent
                if kind == 'blocks':
                    recovery = getattr(error, 'calculation_blocks_cleanup_owner', None)
                    if parent is not None and not parent.closed:
                        self.assertIsNotNone(recovery)
                        self.assertIs(recovery._replay, parent)
                if recovery is not None:
                    recovery.close()
                    recovery.close()
                    self.assertTrue(recovery.closed)
            # 瞬时取消直接收尾；持续失败经生产句柄恢复，所有捕获对象均已关闭。
            self.assertTrue(all(owner.closed for owner in captured))
            self.assertEqual(fixture.budget.ram_bytes, baseline)
            self.assertFalse(fixture.state.closed)
            self.assertFalse(fixture.holds.closed)
            self.assertFalse(fixture.expressions.closed)
            self.assertEqual(fixture.state.revision, 0)
            fixture.history._check('sealed')
        finally:
            # 基线缺恢复句柄时，只回收测试捕获的自有对象，不关闭原fixture资源。
            for owner in reversed(captured):
                owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_direct_layers_keep_original_and_recovery_owner(self):
        """四层直接构造在两来源后端下持续释放失败仍保留原异常和自有恢复入口。

        参数: 无。返回: None。异常: 原异常身份、恢复预算或借用状态断言失败。
        """
        for backend in ('reference', 'numpy'):
            for cls, name, field in self.layers():
                with self.subTest(backend=backend, layer=cls.__name__):
                    self.verify_case(cls, name, field, 'direct', backend)

    def test_replay_adopts_each_failed_unassigned_child(self):
        """两个真实回读后端分别接管尚未赋值的四层失败子owner。

        参数: 无。返回: None。异常: 子归属或父恢复关闭断言失败。
        """
        for backend in ('reference', 'numpy'):
            for cls, name, field in self.layers():
                with self.subTest(backend=backend, layer=cls.__name__):
                    self.verify_case(cls, name, field, 'replay', backend)

    def test_blocks_adopt_parent_and_deep_child(self):
        """分块祖先经原异常接管失败回读者，其四层资源可在外层一次恢复。

        参数: 无。返回: None。异常: 祖先/父/子指针或预算断言失败。
        """
        for backend in ('reference', 'numpy'):
            for cls, name, field in self.layers():
                with self.subTest(backend=backend, layer=cls.__name__):
                    self.verify_case(cls, name, field, 'blocks', backend)

    def test_direct_transient_and_released_cancel_close_once(self):
        """四层在释放前一次取消可重试，释放后取消不能再次抵销自有费用。

        参数: 无。返回: None。异常: 借用金额被二次抵销或原异常丢失断言失败。
        """
        for cls, name, field in self.layers():
            for after in (False, True):
                with self.subTest(layer=cls.__name__, release_after=after):
                    self.verify_case(cls, name, field, 'direct', 'numpy', persistent=False, release_after=after)

    def test_replay_transient_deep_failure_returns_original(self):
        """回读父owner处理深层一次取消，清理后仍传播最初构造失败。

        参数: 无。返回: None。异常: 原异常身份或完整清理断言失败。
        """
        for cls, name, field in self.layers():
            for after in (False, True):
                with self.subTest(layer=cls.__name__, release_after=after):
                    self.verify_case(cls, name, field, 'replay', 'reference', persistent=False, release_after=after)

    def test_constructor_cancel_before_and_after_reserve(self):
        """构造申请前后取消均保留原KeyboardInterrupt，不触碰借用账目。

        参数: 无。返回: None。异常: 原取消被替换、漏账或恢复句柄断言失败。
        """
        for cls, name, field in self.layers():
            for after in (False, True):
                with self.subTest(layer=cls.__name__, reserve_after=after):
                    self.verify_case(cls, name, field, 'direct', 'numpy', reserve_after=after, cancel_error=True)

    def test_expression_failure_after_multiple_charges_keeps_full_amount(self):
        """表达式owner累计两三笔真实元数据费用后失败，直接与祖先恢复均归还全部自有金额。

        参数: 无。返回: None。异常: 只归还末笔费用、错关借用上游或丢恢复句柄断言失败。
        """
        cls, name, field = self.layers()[2]
        for backend in ('reference', 'numpy'):
            for kind in ('direct', 'replay', 'blocks'):
                for charge in (2, 3):
                    with self.subTest(backend=backend, kind=kind, charge=charge):
                        self.verify_case(cls, name, field, kind, backend, charge_index=charge)

    def test_persistent_release_after_keeps_remaining_ancestor_resources(self):
        """每次释放已完成却返回取消时，祖先仍交出剩余资源且不重复抵销已关闭子金额。

        参数: 无。返回: None。异常: 剩余恢复归属、重复扣账或原异常身份断言失败。
        """
        for kind in ('replay', 'blocks'):
            for cls, name, field in self.layers():
                with self.subTest(kind=kind, layer=cls.__name__):
                    self.verify_case(cls, name, field, kind, 'numpy', release_after=True)


# 保留unittest直接运行入口；不生成外部来源或快照内容。
if __name__ == '__main__':
    unittest.main()
