"""NEXT-UX-02/B6 的一维标定表验收。合成轴同时检查端点、内部、越界和无效输入。

比较两种独立实现与手算结果，另经公共配置和 Runner 验证电压换单位后查额定功率。
临时结果只写项目工作目录；低层精度测试不读取文件。
"""

from dataclasses import replace
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.lookup import LookupTablePlan, PreparedLookup, MAX_POINTS
from chronaxis.core.lookup_numpy import lookup_numpy
from chronaxis.core.lookup_reference import lookup_reference
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.numeric_numpy import NumericArray, DTYPES
from chronaxis.core.types import SignalDType as D, QualityFlag as Q


class LookupTests(unittest.TestCase):
    """分别用声明、内核和公开执行入口验证同一物理标定曲线。"""

    def table(self, points=((1, 10), (2, 40), (4, 60))):
        """构造典型V→W标定。参数: 冻结点对。返回: 声明。异常: 原校验错误。"""
        return LookupTablePlan('curve', points, 'V', 'W')

    def compare(self, table, mode, bounds, inputs, dtype, expected):
        """按独立答案验证两后端。参数: 表、模式、输入和答案。返回: 无。异常: 数值/质量不符。"""
        prepared = table.prepare(mode, bounds)
        physical = np.array([v if v is not None else 0 for v in inputs], dtype=DTYPES[dtype])
        valid = np.array([v is not None for v in inputs], dtype=bool)
        column = NumericArray(dtype, physical, valid, (~valid).astype('uint16') * int(Q.MISSING))
        batch = lookup_numpy(prepared, column)
        for index, raw in enumerate(inputs):
            value = ScalarValue(raw, dtype) if raw is not None else ScalarValue(None, dtype, False, Q.MISSING)
            scalar = lookup_reference(prepared, value)
            answer = expected[index]
            if isinstance(answer, Q):
                self.assertEqual((scalar.valid, scalar.quality), (False, answer))
                self.assertEqual((batch.valid[index], int(batch.quality[index])), (False, int(answer)))
            else:
                self.assertTrue(scalar.valid and batch.valid[index])
                self.assertEqual((scalar.value, batch.values[index].item()), (answer, answer))
        self.assertIs(batch.dtype, prepared.dtype)

    def test_endpoints_interpolation_and_both_step_directions(self):
        """精确节点均取本身。参数: 无。返回: 无。异常: 内部、越界或缺失错误。"""
        query = (0., 1., 1.5, 2., 3., 4., 5., None)
        for mode, mid in (('linear', (25.,50.)), ('previous', (10,40)), ('next', (40,60))):
            for bounds, outer in (('invalid',(Q.OUT_OF_RANGE, Q.OUT_OF_RANGE)), ('clamp',(10,60))):
                self.compare(self.table(), mode, bounds, query, D.FLOAT64,
                             (outer[0], 10, mid[0], 40, mid[1], 60, outer[1], Q.MISSING))

    def test_int64_uint64_and_float_precision_failures(self):
        """阶梯大整数无损，线性转换和整数轴显式校验。参数: 无。返回: 无。异常: 精度断言。"""
        high = (1 << 64) - 1
        table = self.table(((0, high), (2, high - 1)))
        self.assertIs(table.dtype, D.UINT64)
        self.compare(table, 'previous', 'clamp', (0,1,2,(1<<53)+1), D.UINT64,
                     (high,high,high-1,Q.PRECISION_LOSS))
        with self.assertRaises(ValueError):
            table.prepare('linear', 'invalid')
        for points in ((((1<<53)+1, 0),(1<<54, 1)), ((0,1.),(1,high)), ((0,-1),(1,high)),
                       ((0,0),(0,1)), ((1,0),(0,1)), ((0,True),(1,2)), ((0,1),)):
            with self.subTest(points=points), self.assertRaises((TypeError, ValueError)):
                self.table(points)
        limit = float.fromhex('0x1.fffffffffffffp+1023')
        self.compare(self.table(((-limit,-1.),(limit,1.))), 'linear','invalid',
                     (-limit,0.,limit), D.FLOAT64, (-1.,Q.NONFINITE,1.))
        self.compare(self.table(((0.,-limit),(2.,limit))), 'linear','invalid', (1.,), D.FLOAT64, (0.,))

    def config(self, backend):
        """生成额定功率配置。参数: 后端。返回: 可运行原字典。异常: 无。"""
        return dict(config_version=4, dataset=dict(name='demo',domain=dict(start='0s',end='3s')),
            sources=[dict(name='table',source_type='memory',rows=[
                dict(time=f'{i}s',values=dict(mv=v)) for i,v in enumerate((1000,1500,4000,1000))])],
            signals=[dict(name='voltage',field='mv',dtype='int64',unit='mV',valid_for='2s')],
            lookups=[dict(name='curve',input_unit='V',unit='W',points=[[1,10],[2,40],[4,60]])],
            calculations=[dict(name='rated_power',operation='sample_mean',expr="lookup(voltage,'curve')",unit='W')],
            execution=dict(backend=backend,batch_rows=1))

    def test_public_runner_units_identity_and_version(self):
        """公共入口1000/1500/4000mV映射10/25/60W。参数: 无。返回: 无。异常: 运行或身份错误。"""
        for backend in ('reference','numpy'):
            raw = self.config(backend)
            plan = AnalysisPlan.from_dict(raw)
            with TemporaryDirectory(dir='work', prefix='lookup-v4-') as directory:
                with AnalysisRunner().run(plan, work_dir=Path(directory)/'run') as result:
                    row, = result.iter_calculations()
                    self.assertAlmostEqual(row.value, 95 / 3)
                    self.assertEqual(row.unit, 'W')
            raw['lookups'][0]['points'][1][1] = 50
            changed = AnalysisPlan.from_dict(raw)
            self.assertNotEqual(changed.bindings.identity, plan.bindings.identity)
            self.assertNotEqual(changed.calculations[0].signal.identity, plan.calculations[0].signal.identity)
        raw = self.config('numpy')
        raw.update(config_version=3, lookups=[], calculations=[])
        with self.assertRaises(ValueError):
            AnalysisPlan.from_dict(raw)

    def test_unused_tables_schema_and_compiler_rejections(self):
        """未引用表无数值列，坏签名/轴在执行前拒绝。参数: 无。返回: 无。异常: 非法配置被接受。"""
        raw = self.config('numpy')
        raw['calculations'][0].update(expr='voltage', unit='mV')
        with patch.object(LookupTablePlan, 'prepare', side_effect=AssertionError('不应为未使用表打包')):
            AnalysisPlan.from_dict(raw)
        # 未请求的派生公式也必须编译检查，但不会为其生成执行数组。
        raw['derived'] = dict(unused_curve=dict(expr="lookup(voltage,'curve')", unit='W'))
        with patch.object(PreparedLookup, 'packed', side_effect=AssertionError('未请求派生不应生成数值列')):
            plan = AnalysisPlan.from_dict(raw)
            with TemporaryDirectory(dir='work', prefix='lookup-unused-') as directory:
                with AnalysisRunner().run(plan, work_dir=Path(directory)/'run') as result:
                    row, = result.iter_calculations()
                    self.assertAlmostEqual(row.value, 6500/3)
        del raw['derived']
        for expr in ("lookup(voltage,'absent')", 'lookup(voltage,voltage)', "lookup(True,'curve')",
                     "lookup(voltage,'curve',mode='spline')", "lookup(voltage,'curve','linear')",
                     "lookup(quantity(1,'A'),'curve')", "lookup(voltage,'curve',other='hi')"):
            raw['calculations'][0].update(expr=expr, unit='W')
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                AnalysisPlan.from_dict(raw)
        with self.assertRaises(ValueError):
            self.table(tuple((i,i) for i in range(MAX_POINTS + 1)))

    def test_table_content_counts_against_driver_budget(self):
        """大表静态持有的预算在重编译前申请。参数: 无。返回: 无。异常: 超预算继续或失败后漏账。"""
        from chronaxis.core.expression import validate_expression
        from chronaxis.execution.driver_expression import DriverExpression
        from chronaxis.execution.state import LatestSignalState
        from chronaxis.results.budget import ResourceBudget
        from chronaxis.results.errors import BudgetExceededError

        raw = self.config('reference')
        plan = AnalysisPlan.from_dict(raw)
        budget = ResourceBudget(64 * 1024 ** 2)
        state = LatestSignalState(budget, plan.bindings.signals, plan.dataset.session_id)
        self.addCleanup(state.close)
        baseline = budget.ram_bytes
        small = DriverExpression(plan.calculations[0].signal, state, None)
        self.addCleanup(small.close)
        limit = budget.ram_bytes
        small.close()
        # 同样的源、表达式及行数，只增加标定轴长度。失败不能占有调用方的状态费用。
        large = self.table(tuple((i, i) for i in range(512)))
        declared = replace(plan.bindings, lookups=(large,))
        static = validate_expression("lookup(voltage,'curve')", declared)
        budget.memory_budget_bytes = limit
        with self.assertRaises(BudgetExceededError):
            DriverExpression(static, state, None)
        self.assertEqual(budget.ram_bytes, baseline)

    def test_current_message_uses_same_lookup_with_own_period_parameter(self):
        """实际两条CAN帧分别标定再乘周期。参数: 无。返回: 无。异常: 消息域绑定或累计差异。"""
        from test_run_message_calculations import RunMessageCalculationTests
        from configuration_fixtures import current_fixture
        factory = RunMessageCalculationTests()
        for backend in ('reference', 'numpy'):
            work, original, _ = factory.fixture(backend=backend, frames=((0,256,b'\xa0\x0f'),(0,256,b'\xa0\x0f')))
            raw = current_fixture(original)
            raw.update(config_version=4, lookups=[dict(name='cal',input_unit='kW',unit='W',points=[[0,0],[8,4000]])])
            raw['message_calculations'][0]['expr'] = "lookup(power,'cal') * period"
            plan = AnalysisPlan.from_dict(raw, base_dir=work)
            with AnalysisRunner().run(plan, work_dir=work/'lookup') as result:
                row, = result.iter_calculations()
                self.assertEqual((row.value, row.unit), (400., 'J'))
