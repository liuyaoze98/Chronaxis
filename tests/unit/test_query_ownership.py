"""验证新保持与表达式查询在取消、交付失败和关闭时的预算所有权。

复用已验收的真实memory/封存历史/运行绑定夹具，输入是完整组之后的一点查询。
输出为预算、登记及生命周期断言；正常数值由既有专项覆盖，本文件检查资源边界。
故障在共享单线程账本操作前或实际执行后注入一次，不能由注入器替生产代码清理。
测试资源逆序关闭并明确要求RAM归零，工厂清理失败不能被TestCase内部吞掉。
文件只在work/m2-run-tests创建合成数据，RefProjects和旧读写/解码保持只读。
"""

# 工厂以模块引用复用，避免unittest再次发现并重复执行其TestCase类。
import unittest
from unittest.mock import patch
import numpy as np
import test_stream_boundaries as boundary_fixtures
from chronaxis.execution.hold import HoldQueries
from chronaxis.execution.expressions import ExpressionQueries


class CancelAfterAdd(set):
    """在真实集合安装后取消，保留已安装对象以检查生产方局部清理。"""

    def add(self, result):
        """先安装再取消，不释放预算或移除对象。

        参数: result已经完成构造的查询结果。
        返回: 无。
        异常: KeyboardInterrupt为明确的部分安装故障。
        """
        # 原集合操作必须实际发生，否则不能验证部分登记造成的遗漏。
        super().add(result)
        raise KeyboardInterrupt('partial-query-install')


class QueryOwnershipTests(unittest.TestCase):
    """每种故障使用独立真实夹具和账本；不修改业务真值或预算公式。"""

    def fixture(self):
        """建立原工厂并将其清理结果纳入本TestCase断言。

        参数: 无。
        返回: 已提交首个完整组的各层资源。
        异常: 来源/历史/绑定/状态错误传播，清理漏账由本测试失败报告。
        """
        # 使用组合而不继承测试类，全部原用例仍只由其原模块执行一次。
        factory = boundary_fixtures.StreamBoundaryTests('runTest')
        factory.setUp()
        fixture = factory.prepare()
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        fixture.state.apply(fixture.groups[0])
        return fixture

    def cleanup_fixture(self, factory, budget):
        """逆序清理真实夹具并检查工厂失败状态与共享RAM。

        参数: factory拥有原层级关闭函数，budget为同一账本。
        返回: None。
        异常: 原工厂清理失败或最终漏账触发断言。
        """
        # doCleanups内部会记录异常，必须检查返回值，不能仅调用后宣称通过。
        self.assertTrue(factory.doCleanups(), '原工厂层级关闭失败')
        self.assertEqual(budget.ram_bytes, 0, '真实夹具关闭后预算应归零')

    def query(self, fixture, layer, backend):
        """按指定层和后端实际申请一个查询结果。

        参数: fixture真实资源；layer为hold/expression；backend为reference/numpy。
        返回: HoldResult或ExpressionResult，调用方负责close。
        异常: 当前查询实际异常传播，不使用伪造结果代替资源申请。
        """
        # 两个数值后端接同一事实的一点轴；选择只控制真实接口，不生成测试答案。
        owner = fixture.holds if layer == 'hold' else fixture.expressions
        argument = 'a' if layer == 'hold' else fixture.compiled[0]
        axis = (0,) if backend == 'reference' else np.array([0], dtype='int64')
        return getattr(owner, 'query_' + backend)(argument, axis)

    def cancellation(self, original, after, call_index=1):
        """构造在第N次实际账本操作前或后只取消一次的注入器。

        参数: original原操作；after是否先执行；call_index正整数目标次数。
        返回: 可调用的故障函数，不替生产代码释放或抵销金额。
        异常: 当前原操作异常原样传播；目标时刻抛KeyboardInterrupt。
        """
        # 闭包只保存小整数，后续重试继续调用真实原操作，不反复阻止必要清理。
        calls = 0

        def invoke(amount):
            """执行一次指定账本操作或取消。

            参数: amount申请或释放字节。
            返回: 原操作返回值。
            异常: KeyboardInterrupt为唯一目标故障，其他异常原样传播。
            """
            nonlocal calls
            # 故障前后与调用次数分别明确，不能把扣账未发生当成已扣账。
            calls += 1
            if calls == call_index:
                if after:
                    original(amount)
                raise KeyboardInterrupt('query-budget-boundary')
            return original(amount)

        return invoke

    def test_result_close_before_or_after_release_cancel(self):
        """未释放的关闭保持可重试，已释放的取消完成关闭且不再扣账。

        参数: 无。返回: None。
        异常: 预算低估、登记遗漏或重复释放触发断言。
        """
        for layer in ('hold', 'expression'):
            for backend in ('reference', 'numpy'):
                for after in (False, True):
                    with self.subTest(layer=layer, backend=backend, after=after):
                        fixture = self.fixture()
                        owner = fixture.holds if layer == 'hold' else fixture.expressions
                        base = fixture.budget.ram_bytes
                        result = self.query(fixture, layer, backend)
                        cost = result._cost
                        fault = self.cancellation(fixture.budget.release_ram, after)
                        with patch.object(fixture.budget, 'release_ram', side_effect=fault):
                            with self.assertRaises(KeyboardInterrupt):
                                result.close()
                        # 查询自身申请是唯一变量，旧state和其他层的账目不能被抵销。
                        self.assertEqual(result.closed, after)
                        self.assertEqual(result in owner._results, not after)
                        self.assertEqual(fixture.budget.ram_bytes, base if after else base + cost)
                        result.close()
                        result.close()
                        self.assertEqual(fixture.budget.ram_bytes, base)

    def test_query_reserve_before_or_after_return_cancel(self):
        """预申请取消没有输出登记和漏账，原owner可再次执行真实查询。

        参数: 无。返回: None。
        异常: 失败后状态或预算改变、正常重试失败触发断言。
        """
        for layer in ('hold', 'expression'):
            for backend in ('reference', 'numpy'):
                for after in (False, True):
                    with self.subTest(layer=layer, backend=backend, after=after):
                        fixture = self.fixture()
                        base = fixture.budget.ram_bytes
                        fault = self.cancellation(fixture.budget.reserve_ram, after)
                        with patch.object(fixture.budget, 'reserve_ram', side_effect=fault):
                            with self.assertRaises(KeyboardInterrupt):
                                self.query(fixture, layer, backend)
                        # 没有数值输出交付，两类登记应保持空；当前样本仍为原1。
                        self.assertEqual(fixture.budget.ram_bytes, base)
                        self.assertEqual(len(fixture.holds._results), 0)
                        self.assertEqual(len(fixture.expressions._results), 0)
                        self.assertEqual(fixture.state.get('a').value.value, 1.)
                        self.query(fixture, layer, backend).close()
                        self.assertEqual(fixture.budget.ram_bytes, base)

    def test_partial_install_and_register_delivery_cancel(self):
        """半安装与构造返回取消不留下孤儿结果，也不影响原owner重试。

        参数: 无。返回: None。
        异常: 登记不空、预算漏账或重试失败触发断言。
        """
        for layer in ('hold', 'expression'):
            for backend in ('reference', 'numpy'):
                for partial_install in (False, True):
                    with self.subTest(layer=layer, backend=backend, partial_install=partial_install):
                        fixture = self.fixture()
                        owner = fixture.holds if layer == 'hold' else fixture.expressions
                        base = fixture.budget.ram_bytes
                        if partial_install:
                            # 集合仍执行真实add，取消后应由当前查询撤销自己的局部结果。
                            old = owner._results
                            owner._results = CancelAfterAdd()
                            with self.assertRaises(KeyboardInterrupt):
                                self.query(fixture, layer, backend)
                            self.assertEqual(len(owner._results), 0)
                            owner._results = old
                        else:
                            original = owner._register

                            def cancel_delivery(*args):
                                """构造返回后取消。参数: 原_register参数。返回: 无。异常: KeyboardInterrupt。"""
                                # 原操作正常完成才取消；新的未登记对象必须由外层预算边界覆盖。
                                original(*args)
                                raise KeyboardInterrupt('query-register-delivery')

                            with patch.object(owner, '_register', side_effect=cancel_delivery):
                                with self.assertRaises(KeyboardInterrupt):
                                    self.query(fixture, layer, backend)
                            self.assertEqual(len(owner._results), 0)
                        self.assertEqual(fixture.budget.ram_bytes, base)
                        self.query(fixture, layer, backend).close()
                        self.assertEqual(fixture.budget.ram_bytes, base)

    def test_temporary_hold_close_cancel_never_delivers_orphan_expression(self):
        """临时保持关闭取消时表达式结果不能已经对外遗留登记。

        参数: 无。返回: None。
        异常: 任一临时或输出结果遗漏/漏账触发断言。
        """
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                with self.subTest(backend=backend, after=after):
                    fixture = self.fixture()
                    base = fixture.budget.ram_bytes
                    fault = self.cancellation(fixture.budget.release_ram, after)
                    with patch.object(fixture.budget, 'release_ram', side_effect=fault):
                        with self.assertRaises(KeyboardInterrupt):
                            self.query(fixture, 'expression', backend)
                    # 单依赖的首次release来自临时保持，取消不应交付表达式或遗留自有申请。
                    self.assertEqual(len(fixture.holds._results), 0)
                    self.assertEqual(len(fixture.expressions._results), 0)
                    self.assertEqual(fixture.budget.ram_bytes, base)

    def test_owner_fixed_close_before_or_after_release_cancel(self):
        """空owner固定空间未释放可重试，已释放的取消不再释放固定预算。

        参数: 无。返回: None。
        异常: owner生命周期、保留字段或预算不一致触发断言。
        """
        for layer in ('hold', 'expression'):
            for after in (False, True):
                with self.subTest(layer=layer, after=after):
                    fixture = self.fixture()
                    owner = fixture.holds if layer == 'hold' else fixture.expressions
                    base, fixed = fixture.budget.ram_bytes, owner._fixed_cost
                    fault = self.cancellation(fixture.budget.release_ram, after)
                    with patch.object(fixture.budget, 'release_ram', side_effect=fault):
                        with self.assertRaises(KeyboardInterrupt):
                            owner.close()
                    self.assertEqual(owner.closed, after)
                    self.assertEqual(fixture.budget.ram_bytes, base - fixed if after else base)
                    owner.close()
                    self.assertEqual(fixture.budget.ram_bytes, base - fixed)

    def test_constructor_first_and_later_reserve_return_cancel(self):
        """构造初次与后续元数据申请返回取消只撤销本次新owner申请。

        参数: 无。返回: None。
        异常: 原层预算或对象被错误关闭、构造漏账触发断言。
        """
        for layer in ('hold', 'expression'):
            for call_index in ((1,) if layer == 'hold' else (1, 2)):
                for after in (False, True):
                    with self.subTest(layer=layer, call_index=call_index, after=after):
                        fixture = self.fixture()
                        base = fixture.budget.ram_bytes
                        fault = self.cancellation(fixture.budget.reserve_ram, after, call_index)
                        with patch.object(fixture.budget, 'reserve_ram', side_effect=fault):
                            with self.assertRaises(KeyboardInterrupt):
                                if layer == 'hold':
                                    HoldQueries(fixture.state, fixture.holds._context)
                                else:
                                    ExpressionQueries(fixture.holds, fixture.lease.bindings, fixture.compiled)
                        # 借用的旧查询和最新state仍打开，失败不抵销其他owner的固定空间。
                        self.assertEqual(fixture.budget.ram_bytes, base)
                        self.assertFalse(fixture.holds.closed)
                        self.assertFalse(fixture.expressions.closed)
                        self.assertFalse(fixture.state.closed)

    def test_failed_new_query_preserves_previously_delivered_result(self):
        """新结果部分安装失败仅撤销新对象，先前结果及其持有预算保持可读。

        参数: 无。返回: None。
        异常: 旧结果被关闭、业务值改变或预算抵销过量触发断言。
        """
        for layer in ('hold', 'expression'):
            for backend in ('reference', 'numpy'):
                with self.subTest(layer=layer, backend=backend):
                    fixture = self.fixture()
                    owner = fixture.holds if layer == 'hold' else fixture.expressions
                    first = self.query(fixture, layer, backend)
                    base = fixture.budget.ram_bytes
                    original = owner._results
                    owner._results = CancelAfterAdd(original)
                    with self.assertRaises(KeyboardInterrupt):
                        self.query(fixture, layer, backend)
                    # 原结果仍登记/可读，只有新add对象被清理；不得把全owner清空当作回滚。
                    self.assertEqual(tuple(owner._results), (first,))
                    self.assertFalse(first.closed)
                    self.assertEqual(fixture.budget.ram_bytes, base)
                    if backend == 'reference':
                        self.assertTrue(first.rows[0].valid if layer == 'hold' else first.rows[0].value.valid)
                    else:
                        self.assertTrue(first.arrays.valid[0] if layer == 'hold' else first.arrays.value.valid[0])
                    first.close()
                    owner._results = original
                    original.discard(first)

    def test_discard_cancel_marks_closed_and_owner_retry_prunes_registration(self):
        """扣账后脱离登记取消不允许再次释放，owner重试能清除关闭对象。

        参数: 无。返回: None。
        异常: 重复扣账、关闭对象残留导致死循环或预算错误触发断言。
        """
        for layer in ('hold', 'expression'):
            for after in (False, True):
                with self.subTest(layer=layer, after=after):
                    fixture = self.fixture()
                    owner = fixture.holds if layer == 'hold' else fixture.expressions
                    base, fixed = fixture.budget.ram_bytes, owner._fixed_cost
                    result = self.query(fixture, layer, 'reference')

                    class CancelDiscard(set):
                        """只在第一次移除前/后取消，保留真实后续移除供owner重试。"""

                        def discard(self, item):
                            """执行真实移除或唯一取消。

                            参数: item待脱离结果。返回: None。
                            异常: 首次KeyboardInterrupt，不修改任何预算。
                            """
                            # 先切换一次性故障状态，重试必须能执行原set操作而非一直拒绝。
                            if self.cancel:
                                self.cancel = False
                                if after:
                                    super().discard(item)
                                raise KeyboardInterrupt('query-discard-boundary')
                            super().discard(item)

                    # 集合构造不执行add，原结果保持唯一成员；只注入登记移除边界。
                    owner._results = CancelDiscard(owner._results)
                    owner._results.cancel = True
                    with self.assertRaises(KeyboardInterrupt):
                        result.close()
                    self.assertTrue(result.closed)
                    self.assertEqual(result in owner._results, not after)
                    self.assertEqual(fixture.budget.ram_bytes, base)
                    result.close()
                    owner.close()
                    self.assertEqual(fixture.budget.ram_bytes, base - fixed)
