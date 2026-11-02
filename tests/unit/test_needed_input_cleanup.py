"""[home] 用真实构造失败核需求临时引用清理及独立预算责任。

复用独占work目录中的合成CAN计划与实际来源adapter。扫描构造失败不启动读取；
租约回归通过当前消息计算器消费真实小BLF，再在最终绑定对象构造处注入失败。
直接检查仍存活的异常traceback，不使用会清理栈帧的assertRaises。
持续退款失败须保原异常和同一恢复owner；恢复后只退本owner费用，借用来源和
预先存在的借款分别归还。测试不修改旧reader、decoder或RefProjects。
"""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from chronaxis.execution import scanned_signal_proof as scanned
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.models import ReadRequest
from test_optional_contribution_execution import make_can_fixture


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('can', 'cantools', 'natsort')),
                     '缺少可选CAN依赖')
class NeededInputCleanupTests(unittest.TestCase):
    """每个子例持有独立真实owner和账本，失败栈一直保留到责任核对完成。"""

    def setUp(self):
        """建立本例清理清单。参数: 无。返回: None。异常: 无。"""
        self.owners, self.budgets = [], []

    def tearDown(self):
        """退出注入后关闭实际owner并归还既有借款。参数: 无。返回: None。异常: 清理或串账断言。"""
        for owner in reversed(self.owners):
            owner.close()
        for budget in self.budgets:
            self.assertEqual(budget.ram_bytes, 333)
            budget.release_ram(333)
            self.assertEqual(budget.ram_bytes, 0)

    def make_inputs(self, *, message_consumer=None):
        """创建尚未读取的真实来源及独立共享账本。

        参数: 无。返回: plan、budget、adapter和空普通样本请求。
        异常: 原夹具、公开模型或预算错误；目录使用新UUID，不覆盖其他测试。
        """
        root = (Path(__file__).resolve().parents[2] /
                'work/optional-contribution-tests/needed-input-cleanup' / uuid4().hex)
        _, plan = make_can_fixture(root, backend='reference')
        budget = ResourceBudget(plan.execution.memory_budget_bytes)
        budget.reserve_ram(333)
        self.budgets.append(budget)
        source = plan.sources[0]
        definitions = tuple(item.definition for item in plan.signals
                            if item.definition.source == source.name)
        ids = tuple(sorted({calculation.update_message.frame_id for calculation in plan.message_calculations}))
        adapter = BudgetedLegacyCANSourceAdapter(budget, source.config, plan.dataset.session_id,
            definitions, backend=plan.execution.backend, work_dir=root / 'adapter',
            batch_read=True, retain_raw_frames=False, capture_message_updates=False,
            message_frame_ids=ids, message_consumer=message_consumer)
        self.owners.append(adapter)
        request = ReadRequest(plan.dataset.session_id, (), plan.dataset.domain.start_ns,
                              plan.dataset.domain.end_ns, plan.execution.batch_rows)
        return plan, budget, adapter, request

    def assert_live_trace_cleared(self, error, function, names):
        """检查尚未被测试框架清理的实际失败帧，并取回其中的真实self。

        参数: 捕获的原异常、目标函数及应清除的局部变量名。
        返回: 该帧的实际owner。异常: 帧缺失、重复或仍保留临时对象时断言失败。
        """
        trace, owner, found = error.__traceback__, None, 0
        try:
            while trace is not None:
                if trace.tb_frame.f_code is function.__code__:
                    found += 1
                    for name in names:
                        self.assertIn(name, trace.tb_frame.f_locals)
                        self.assertIsNone(trace.tb_frame.f_locals[name], name)
                    owner = trace.tb_frame.f_locals['self']
                trace = trace.tb_next
            self.assertEqual(found, 1)
            return owner
        finally:
            trace = owner = error = function = None

    def test_scan_contract_failure_clears_trace_and_preserves_recoverable_owner(self):
        """需求请求建成后失败，原异常身份和真实退款责任保持。

        参数: 无。返回: None。异常: 引用残留、主错替换、提前退款或借用来源关闭时断言失败。
        ValueError、MemoryError、KeyboardInterrupt分别覆盖正常关闭和持续退款失败。
        """
        release = scanned._release_owned_ram
        for kind in (ValueError, MemoryError, KeyboardInterrupt):
            for blocked in (False, True):
                with self.subTest(error=kind.__name__, blocked_refund=blocked):
                    plan, budget, adapter, request = self.make_inputs()
                    before, primary = budget.ram_bytes, kind('needed contract failure')
                    caught = None

                    def reject_contract(*args, **kwargs):
                        """在真实请求建立后失败。参数: 原合同参数。返回: 无。异常: 同一primary。"""
                        try:
                            raise primary
                        finally:
                            args = kwargs = None

                    def release_or_block(owner, amount, slot):
                        """仅阻止本scan固定费用退款。参数: 原费用交易。返回: 原返回。异常: 指定OSError。"""
                        if blocked and slot == '_fixed_cost' and amount:
                            raise OSError('scan refund blocked')
                        return release(owner, amount, slot)

                    with patch.object(scanned, 'require_decoded_source_contract', reject_contract), \
                            patch.object(scanned, '_release_owned_ram', release_or_block):
                        try:
                            scanned.ScannedCANSignals(plan.bindings, plan.sources[0], adapter, request)
                        except BaseException as error:
                            caught = error
                        else:
                            self.fail('构造必须到达注入的原合同错误')
                        self.assertIs(caught, primary)
                        owner = self.assert_live_trace_cleared(caught, scanned.ScannedCANSignals.__init__,
                            ('contract_request', 'source', 'description'))
                        self.owners.append(owner)
                        self.assertFalse(adapter.closed)
                        self.assertEqual(adapter._requests, set())
                        if blocked:
                            self.assertIs(caught.scanned_can_signals_cleanup_owner, owner)
                            self.assertFalse(owner.closed)
                            self.assertGreater(owner._held_cost, 0)
                            self.assertEqual(budget.ram_bytes, before + owner._held_cost)
                        else:
                            self.assertTrue(owner.closed)
                            self.assertEqual(owner._held_cost, 0)
                            self.assertEqual(budget.ram_bytes, before)
                    # 保留caught及其原traceback时关闭同一owner，不能靠丢弃异常回收对象。
                    owner.close()
                    self.assertTrue(owner.closed)
                    self.assertEqual(budget.ram_bytes, before)
                    self.assertFalse(adapter.closed)
                    adapter.close()
                    self.assertEqual(budget.ram_bytes, 333)

    def test_completed_scan_lease_failure_clears_trace_and_keeps_borrowed_scan(self):
        """实际v2输入扫描完成后租约构造失败，不关闭借用scan或退还其费用。

        参数: 无。返回: None。异常: 新增需求引用残留、原异常替换、费用串账或恢复owner丢失。
        最终绑定对象构造才注入错误，确保全部需求局部和prefix确实已被计算。
        """
        release = scanned._release_owned_ram
        for blocked in (False, True):
            with self.subTest(blocked_refund=blocked):
                plan, budget, adapter, request = self.make_inputs(
                    message_consumer=lambda update: accumulator.consume((update,)))
                accumulator = CurrentMessageCalculation(plan.message_calculations[0], plan.sources, plan.bindings,
                    plan.dataset.session_id, budget, backend=plan.execution.backend,
                    domain=plan.dataset.domain, batch_rows=plan.execution.batch_rows)
                self.owners.append(accumulator)
                scan = scanned.ScannedCANSignals(plan.bindings, plan.sources[0], adapter, request,
                                                  input_only=True)
                self.owners.append(scan)
                scan.consume()
                self.assertEqual(accumulator.snapshot().value, 700.)
                adapter._update_consumer = None
                facts = scan.facts
                self.assertIsInstance(facts, scanned.ScannedInputFacts)
                self.assertTrue(scan.finished)
                self.assertIsNone(scan._read)
                before = budget.ram_bytes
                primary = MemoryError('completed lease failure') if blocked else ValueError('completed lease failure')
                caught, called = None, []

                def reject_final_binding(declarations, sources, identity):
                    """在全部源事实和前缀生成后失败。参数: 真绑定参数。返回: 无。异常: 原primary。"""
                    try:
                        self.assertIs(declarations, plan.bindings)
                        self.assertEqual(sources, (facts,))
                        self.assertTrue(identity.startswith('scanned-input-binding-v2:'))
                        called.append(True)
                        raise primary
                    finally:
                        declarations = sources = identity = None

                def release_or_block(owner, amount, slot):
                    """只阻止本租约退款，不拦借用扫描。参数: 原费用交易。返回: 原返回。异常: 指定OSError。"""
                    if blocked and isinstance(owner, scanned.ScannedBindingLease) and amount:
                        raise OSError('lease refund blocked')
                    return release(owner, amount, slot)

                with patch.object(scanned, '_ScannedBindings', reject_final_binding), \
                        patch.object(scanned, '_release_owned_ram', release_or_block):
                    try:
                        scanned.ScannedBindingLease(plan, (scan,), (scan._description,),
                                                    {plan.sources[0].name: request}, budget)
                    except BaseException as error:
                        caught = error
                    else:
                        self.fail('租约必须到达最终绑定对象构造的失败点')
                    self.assertIs(caught, primary)
                    self.assertEqual(called, [True])
                    owner = self.assert_live_trace_cleared(caught, scanned.ScannedBindingLease.__init__,
                        ('requirements', 'needed', 'aliases', 'expected_fields', 'expected_samples',
                         'prefix', 'facts', 'identity', 'source', 'scan', 'description', 'declared'))
                    self.owners.append(owner)
                    self.assertFalse(scan.closed or adapter.closed or accumulator.closed)
                    self.assertIs(scan.facts, facts)
                    if blocked:
                        self.assertIs(caught.scanned_binding_lease_cleanup_owner, owner)
                        self.assertFalse(owner.closed)
                        self.assertGreater(owner._held_cost, 0)
                        self.assertEqual(budget.ram_bytes, before + owner._held_cost)
                    else:
                        self.assertTrue(owner.closed)
                        self.assertEqual(budget.ram_bytes, before)
                owner.close()
                self.assertTrue(owner.closed)
                self.assertEqual(budget.ram_bytes, before)
                self.assertFalse(scan.closed)
                self.assertIs(scan.facts, facts)
                scan.close()
                accumulator.close()
                adapter.close()
                self.assertEqual(budget.ram_bytes, 333)


if __name__ == '__main__':
    unittest.main()
