"""核对状态信号首次缺样本和无效更新的实际驱动求值。

三种声明共用小型真实 LatestSignalState，两个数值后端独立执行。
只保留必要最新状态，测试结束核对预算归零；不读取私人日志或写文件。
"""
import unittest

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import validate_expression
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.execution.driver_expression import DriverExpression
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.state import LatestSignalState
from chronaxis.results.budget import ResourceBudget
from test_stream_state import make_sample


class UserFlowSignalTypesTests(unittest.TestCase):
    """缺样本必须未知；未知映射码不能沿用旧真假值或崩溃。"""

    def test_missing_invalid_unknown_and_recovery_on_both_backends(self):
        """逐组检查 int/bool/enum 的缺样本、编码、失效和恢复。

        参数: 无。返回: None。异常: 结果、质量或资源责任不符时断言失败。
        """
        cases = (
            (D.INT64, (), 'state == 0x2', False),
            (D.BOOL, ((0, False), (2, True)), 'state', None),
            (D.ENUM, ((0, 'off'), (2, 'active')), "state == 'active'", None),
        )
        for backend in ('reference', 'numpy'):
            for dtype, choices, expression, unknown_result in cases:
                with self.subTest(backend=backend, dtype=dtype):
                    clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'origin')
                    signal = SignalDefinition('state', 'bus', 'raw.state', dtype,
                        '1', 100, choices=choices, invalid_values=(7,))
                    bindings = DeclarationBindings('session', clock, Interval(0, 1000),
                        (DeclaredSource('bus', clock, 'synthetic'),), (signal,))
                    budget = ResourceBudget()
                    state = LatestSignalState(budget, (signal,), 'session')
                    driver = None
                    try:
                        driver = DriverExpression(validate_expression(expression, bindings),
                            state, None, backend=backend)
                        # 尚无任何样本时返回未知，绝不凭 choices 推断状态。
                        value, _ = driver.evaluate_at(0)
                        self.assertFalse(value.valid)
                        self.assertTrue(value.quality & Q.MISSING)
                        # 2 为真；7 显式无效；3 只在整数声明中是合法假值。
                        # 之后恢复到 2，再测试实际有效期端点。
                        for time, raw, expected in ((1, 2, True), (2, 7, None),
                                                    (3, 3, unknown_result), (4, 2, True)):
                            state.apply(DecodedTimeGroup(time,
                                (make_sample(signal, time, time, raw),)))
                            value, _ = driver.evaluate_at(time)
                            self.assertEqual(value.valid, expected is not None)
                            if expected is not None:
                                self.assertEqual(value.value, expected)
                            else:
                                self.assertTrue(value.quality & Q.OUT_OF_RANGE)
                        value, _ = driver.evaluate_at(104)
                        self.assertFalse(value.valid)
                        self.assertTrue(value.quality & Q.STALE)
                    finally:
                        # 与生产路径一样关闭自有对象，构造失败也清理真实状态。
                        if driver is not None:
                            driver.close()
                        state.close()
                    self.assertEqual(budget.ram_bytes, 0)
