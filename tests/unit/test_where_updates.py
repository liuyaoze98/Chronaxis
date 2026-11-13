"""NEXT-UX-02/B3：从真实原子提交状态验证活动分支的更新与有效期。

条件刷新、值相等的真实更新、同时切换、有间隙的恢复保留不同证据。
合成时间均为整数纳秒；两个独立数值后端分别与手算时间表比较。
"""

import unittest
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.expression import validate_expression
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.types import TimeType
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.state import LatestSignalState
from chronaxis.results.budget import ResourceBudget
from types import SimpleNamespace
from test_stream_state import make_sample
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.driver_expression import DriverExpression


class WhereUpdateTests(unittest.TestCase):
    """核对逐组驱动、历史选行以及整窗平均值；不以两个后端相等代替手算。"""

    def fixture(self, backend, *, noise=False, gate_ttl=20):
        """构造三个独立更新时钟。参数: 后端、未选分支额外更新、条件TTL。返回: 声明/状态/完整组。异常: 模型错误。"""
        declarations = (('gate', D.BOOL, gate_ttl), ('a', D.INT64, 20), ('b', D.INT64, 2))
        definitions = tuple(SignalDefinition(n, n+'src', 'raw.'+n, dtype, '1', ttl, config_version=4)
                            for n, dtype, ttl in declarations)
        signals = {'gate': ((0, True), (1, True), (4, False), (5, False), (8, True)),
                   'a': ((0, 8), (2, 8)),
                   'b': ((0, 50),) + (((1, None), (2, 12), (3, 99)) if noise else ()) + ((4, 30), (7, 15))}
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'where-update-test')
        declared = DeclarationBindings('session', clock, Interval(0, 10),
            tuple(DeclaredSource(d.source, clock, d.source) for d in definitions), definitions)
        budget = ResourceBudget()
        state = LatestSignalState(budget, definitions, 'session')
        self.addCleanup(lambda: self.assertEqual(budget.ram_bytes, 0))
        self.addCleanup(state.close)
        samples = {}
        for definition in definitions:
            for sequence, (time, value) in enumerate(signals[definition.name]):
                samples.setdefault(time, []).append(make_sample(definition, time, sequence, value))
        groups = tuple(DecodedTimeGroup(time, tuple(items)) for time, items in sorted(samples.items()))
        return SimpleNamespace(declarations=declared, state=state, groups=groups)

    def test_driver_ttl_refresh_unknown_and_unselected_eof(self):
        """未选来源不能截断输出，条件会过期。参数: 无。返回: 无。异常: 截止/恢复与手算不符。"""
        for backend in ('reference', 'numpy'):
            f = self.fixture(backend, noise=True, gate_ttl=2)
            ends = {}
            driver = DriverExpression(validate_expression('where(gate,a,b)', f.declarations),
                                      f.state, None, backend=backend, observation_ends=ends)
            self.addCleanup(driver.close)
            shared = DriverExpression(validate_expression('where(gate,a,b) + b > 0', f.declarations),
                                      f.state, None, backend=backend)
            self.addCleanup(shared.close)
            results = {}
            for group in f.groups:
                f.state.apply(group)
                t, value, deadline = driver.evaluate()
                _, shared_value, _ = shared.evaluate()
                results[t] = value.value if value.valid else None, deadline, driver.actual_update_at(t)
                if t == 1:
                    ends['bsrc'] = 1
                    self.assertFalse(driver.active_end_at(1))
                    self.assertEqual(driver.evaluate_at(1)[1], 3)
                    del ends['bsrc']
                if t == 2:
                    self.assertFalse(driver.evaluate_at(3)[0].valid)
                if t in (1, 3):
                    # b 在 where 外也是活动依赖：t=1 的无效 b 导致中断，t=3 的有效
                    # b 更新只碰巧与 gate 过期同刻，不能作为真正使规则未知的证据。
                    self.assertTrue(shared.actual_update_at(t))
                    self.assertFalse(shared_value.valid)
                    self.assertEqual(shared.actual_unknown_at(t, shared_value), t == 1)
            self.assertEqual(results, {0:(8,2,True), 1:(8,3,False), 2:(8,3,True), 3:(None,None,False),
                                       4:(30,6,True), 5:(30,6,False), 7:(None,None,False), 8:(8,10,True)})
            driver.close()

    def test_exact_ttl_refresh_is_contiguous_but_later_recovery_is_sample(self):
        """1ns 条件TTL恰在1刷新，4才恢复。参数: 无。返回: 无。异常: 真实计数或选行错误。"""
        for backend in ('reference', 'numpy'):
            f = self.fixture(backend, gate_ttl=1)
            driver = DriverExpression(validate_expression('where(gate,a,b)', f.declarations), f.state, None, backend=backend)
            self.addCleanup(driver.close)
            observed = []
            for group in f.groups:
                f.state.apply(group)
                time, value, _ = driver.evaluate()
                if driver.actual_update_at(time) and value.valid:
                    observed.append(time)
            self.assertEqual(observed, [0, 4, 8])
