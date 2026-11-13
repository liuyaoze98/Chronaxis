"""复现多信号多计算项的声明预算，核对共享对象和独立使用的所有权。

输入是三条合成恒值CSV及当前公开配置；每项积分按2秒手算。
同时检查静态DAG、独立state/driver、DBC式新声明和构造取消后的费用。
"""

from dataclasses import dataclass, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from sys import getsizeof
import unittest
from unittest.mock import patch

from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.core.expression import ExprNode, validate_expression
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.driver_expression import DriverExpression
from chronaxis.execution.run_session import RunSession
from chronaxis.execution.state import LatestSignalState
from chronaxis.execution.static_metadata import static_metadata_bytes
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError, ResultFormatError


class StaticDeclarationBudgetTests(unittest.TestCase):
    """固定每项一个依赖，增加声明和计算数，防止共享绑定重复乘入每项费用。"""

    def plan(self, root, signals=8, calculations=8, backend='reference'):
        """创建三行恒值CSV与当前配置。参数: 目录/规模/后端。返回: 已加载计划。异常: I/O或配置错误。"""
        names = ['v' + str(index) for index in range(signals)]
        path = root / 'input.csv'
        path.write_text('time,' + ','.join(names) + '\n' + ''.join(
            str(time) + ',' + ','.join(str(index + 1) for index in range(signals)) + '\n'
            for time in range(3)), encoding='utf-8')
        config = dict(config_version=4, dataset=dict(name='shared', domain=dict(start='0s', end='2s')),
            sources=[dict(name='table', source_type='signal_csv', path=str(path), time_column='time',
                          time=dict(unit='s'))],
            signals=[dict(name=name, source='table', field=name, dtype='float64', unit='W', valid_for='3s')
                     for name in names],
            calculations=[dict(name='energy' + str(index), operation='integral', expr=names[index % signals])
                          for index in range(calculations)], execution=dict(backend=backend))
        target = root / 'plan.json'
        target.write_text(json.dumps(config), encoding='utf-8')
        return load_analysis_plan(target)

    def test_default_budget_matrix_preserves_each_integral_and_releases(self):
        """8/8至32/32在默认256MiB下完成，读完结果关闭后所有费用归零。"""
        for backend in ('reference', 'numpy'):
            for signals, calculations in ((8, 8), (16, 16), (32, 8), (8, 32), (32, 32)):
                with self.subTest(backend=backend, signals=signals, calculations=calculations):
                    with TemporaryDirectory(prefix='chronaxis-static-budget-') as folder:
                        plan = self.plan(Path(folder), signals, calculations, backend)
                        result = AnalysisRunner().run(plan)
                        budget = result.spool.budget
                        try:
                            rows = {row.calculation_id: row for row in result.iter_calculations()}
                            self.assertEqual(len(rows), calculations)
                            for index in range(calculations):
                                row = rows['energy' + str(index)]
                                self.assertEqual((row.value, row.unit, row.status),
                                                 (2.0 * (index % signals + 1), 'J', 'complete'))
                            self.assertLessEqual(budget.peak_ram_bytes, 256 * 1024 ** 2)
                        finally:
                            result.close()
                        self.assertEqual(budget.ram_bytes, 0)

    def test_plan_declarations_grow_linearly_in_fixed_dependency_fixture(self):
        """只对每项一个依赖的夹具检查翻倍，复杂表达式不受此倍数约束。"""
        costs = []
        with TemporaryDirectory(prefix='chronaxis-static-growth-') as folder:
            for size in (8, 16, 32):
                session = RunSession(self.plan(Path(folder), size, size))
                costs.append(session._held_cost)
                session.close()
                self.assertEqual(session._budget.ram_bytes, 0)
        self.assertLess(costs[1], 2.2 * costs[0])
        self.assertLess(costs[2], 2.2 * costs[1])

    def test_shared_dag_counts_objects_once_but_independent_copies_cost_more(self):
        """同对象多引用只付槽，真正复制的新节点必须增加费用，环仍拒绝。"""
        leaf = ExprNode('name', D.FLOAT64, 'W', 'verified', name='v0', aliases=('v0',))
        shared = ExprNode('add', D.FLOAT64, 'W', 'verified', args=(leaf, leaf), aliases=('v0',))
        copied = replace(shared, args=(leaf, replace(leaf)))
        self.assertGreater(static_metadata_bytes(copied), static_metadata_bytes(shared))
        object.__setattr__(shared, 'args', (shared,))
        with self.assertRaises(ResultFormatError):
            static_metadata_bytes(shared)
        mapping = {str(index): str(index + 100) for index in range(32)}
        proxy = MappingProxyType(mapping)
        self.assertGreaterEqual(static_metadata_bytes(proxy), getsizeof(proxy) + getsizeof(mapping))

        @dataclass(frozen=True, slots=True)
        class SlotDeclaration:
            """模拟不带实例字典的冻结声明；字段槽由实例本体持有。"""
            name: str

        slotted = SlotDeclaration('slot-name')
        self.assertGreaterEqual(static_metadata_bytes(slotted), getsizeof(slotted) + getsizeof(slotted.name))

    def test_one_dependency_driver_does_not_charge_unrelated_bindings(self):
        """v0表达式不因另外24个声明重复收费；表达式自身增加节点仍增加费用。"""
        costs = []
        with TemporaryDirectory(prefix='chronaxis-driver-budget-') as folder:
            for count in (8, 32):
                plan = self.plan(Path(folder), count, 1)
                budget = ResourceBudget()
                state = LatestSignalState(budget, plan.bindings.signals, plan.dataset.session_id)
                driver = expanded = None
                try:
                    driver = DriverExpression(validate_expression('v0', plan.bindings), state, None)
                    expanded = DriverExpression(validate_expression('v0 + v1 + v2', plan.bindings), state, None)
                    costs.append(driver._fixed_cost)
                    self.assertGreater(expanded._fixed_cost, driver._fixed_cost)
                finally:
                    if driver is not None:
                        driver.close()
                    if expanded is not None:
                        expanded.close()
                    state.close()
                self.assertEqual(budget.ram_bytes, 0)
        # CPython共享实例键表可随实例数收缩，允许少量浅对象差异，不允许按完整绑定增长。
        self.assertLessEqual(abs(costs[1] - costs[0]), 8192)

    def test_independent_state_owns_declarations_and_parent_run_borrows_same_objects(self):
        """独立state付实体；共享父仅借同对象；替换产生的新定义仍增加费用。"""
        with TemporaryDirectory(prefix='chronaxis-static-owner-') as folder:
            plan = self.plan(Path(folder))
            parent = RunSession(plan)
            states = []
            try:
                own = LatestSignalState(parent._budget, plan.bindings.signals, plan.dataset.session_id)
                states.append(own)
                borrowed = LatestSignalState(parent._budget, plan.bindings.signals, plan.dataset.session_id,
                                             declaration_owner=parent)
                states.append(borrowed)
                copied = LatestSignalState(parent._budget, tuple(replace(item) for item in plan.bindings.signals),
                                           plan.dataset.session_id, declaration_owner=parent)
                states.append(copied)
                self.assertGreater(own.fixed_cost, borrowed.fixed_cost)
                self.assertGreater(copied.fixed_cost, borrowed.fixed_cost)
                driver = DriverExpression(validate_expression('v0', plan.bindings), own, None)
                own.close()
                with self.assertRaises(ResultClosedError):
                    driver.evaluate()
                driver.close()
            finally:
                for state in states:
                    state.close()
                parent.close()
            self.assertEqual(parent._budget.ram_bytes, 0)

    def test_run_constructor_reserve_after_effect_cancel_refunds(self):
        """费用已入账才取消时，RunSession清理原owner，不遗留或多退费用。"""
        with TemporaryDirectory(prefix='chronaxis-static-cancel-') as folder:
            plan = self.plan(Path(folder))
            original, calls, budgets = ResourceBudget.reserve_ram, [], []
            failure = KeyboardInterrupt('after static reservation')

            def reserve(budget, amount):
                """在第二次申请实际成功后取消。参数: 账本/费用。返回: None。异常: 指定取消。"""
                original(budget, amount)
                budgets.append(budget)
                calls.append(amount)
                if len(calls) == 2:
                    raise failure

            with patch.object(ResourceBudget, 'reserve_ram', reserve):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    RunSession(plan)
            self.assertIs(caught.exception, failure)
            self.assertEqual(budgets[-1].ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
