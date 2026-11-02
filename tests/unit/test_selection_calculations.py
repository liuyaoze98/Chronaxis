"""核对选择行流的真实更新、UNKNOWN诊断、类型与当前来源身份。

合成完整内存来源同时含数值、BOOL、ENUM和选择条件；两个桥接独立提取、
对齐和求值后输出逐行迭代器。手算判断真实更新时间与TTL缺口，不用旧输出作真值。
测试不写文件、不读取旧日志、不宣称AnalysisRunner预算或真实数据验收完成。
"""

# 冻结请求局部变体用于半开窗口/身份错误。
from dataclasses import replace
from collections.abc import Iterator
import unittest
# 现有输入夹具与差分仅用于断言，不包含数值算法。
from test_calculations import _series
import test_calculations as fixtures
# 标准库公开行流入口与实际typed模型。
from chronaxis.core import (Interval, MemoryRow, SessionSpec, SignalBindings, SignalDefinition,
                            SourceSpec, TimebaseSpec, TimeType, compile_expression, SelectionRow,
                            select_reference, select_memory_reference)
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, Truth
# 独立数组入口及两个原行到标量指标入口。
from chronaxis.core.calculations_numpy import select_numpy
from chronaxis.core.calculations_memory_numpy import select_memory_numpy, compute_memory_numpy
from chronaxis.core.calculations_memory_reference import compute_memory_reference


def selection_bindings():
    """构造真实字段更新与TTL缺口可手算的合成内存来源。

    参数: 无。
    返回: SignalBindings，0—4秒域，目标TTL一秒，条件TTL五秒。
    异常: 输入模型或绑定检查失败直接传播。
    """
    # 条件在1秒独自变FALSE；2秒UNKNOWN；3秒TRUE与无效目标同时更新。
    data = ((0, {'raw': 2., 'selected': True, 'mode': 0, 'alarm': True}),
            (1_000_000_000, {'selected': False}),
            (2_000_000_000, {'raw': 8., 'selected': None, 'mode': 1, 'alarm': False}),
            (3_000_000_000, {'raw': None, 'selected': True, 'mode': None, 'alarm': None}),
            (4_000_000_000, {'raw': 99., 'selected': True, 'mode': 0, 'alarm': True}))
    # 同一显式合成起点，保持原行顺序和序号，不声称真实同步依据。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'selection-synthetic-v1')
    source = SourceSpec('table', clock, tuple(MemoryRow(time, value, index) for index, (time, value) in enumerate(data)),
                        observation_start_ns=0, observation_end_ns=4_000_000_000)
    # 类型、单位和标签显式声明，枚举原编码不冒充公开值。
    signals = (SignalDefinition('value', 'table', 'raw', D.FLOAT64, 'W', 1_000_000_000),
               SignalDefinition('selected', 'table', 'selected', D.BOOL, '1', 5_000_000_000),
               SignalDefinition('mode', 'table', 'mode', D.ENUM, '1', 1_000_000_000, choices=((0, 'Idle'), (1, 'Run'))),
               SignalDefinition('alarm', 'table', 'alarm', D.BOOL, '1', 1_000_000_000))
    return SignalBindings(SessionSpec('session', clock, 0, 4_000_000_000, (source,)), signals)


class SelectionCalculationTests(unittest.TestCase):
    """核对完整行协议和真实更新边界；实例没有跨测试信号或流状态。"""

    def test_direct_rows_preserve_unknown_and_original_values(self):
        """TRUE与UNKNOWN保留，FALSE排除，invalid原值不被填成正常零。

        参数: 无；直接typed合成序列。
        返回: None。
        异常: 行协议或双后端差异由断言报告。
        """
        # 0秒TRUE有效2；1秒UNKNOWN无效；3秒末点不输出。
        series = _series((2., None, 99.), conditions=(True, None, True))
        spec = CalculationDefinition('rows', 'select', series.observation)
        rows = tuple(select_reference(series, spec))
        self.assertEqual(rows, tuple(select_numpy(series, spec)))
        self.assertEqual(tuple(row.time_ns for row in rows), (0, 1_000_000_000))
        self.assertEqual(tuple(row.selection for row in rows), (Truth.TRUE, Truth.UNKNOWN))
        self.assertIs(rows[1].value, series.values[1])
        self.assertTrue(rows[1].quality & Q.MISSING)
        # FALSE行过滤；真实更新标志为False的保持位置不能新增行。
        series = replace(series, conditions=_series((0., 0., 0.), conditions=(False, True, True)).conditions,
                         actual_value_updates=(True, False, True))
        self.assertEqual(tuple(select_reference(series, spec)), ())
        self.assertEqual(tuple(select_numpy(series, spec)), ())

    def test_memory_ttl_clipping_condition_only_and_identity(self):
        """裁剪与TTL不产生行，条件独自更新不伪造目标更新，身份保留。

        参数: 无；真实原字段合成输入。
        返回: None。
        异常: 两独立完整链或手算行不符产生断言失败。
        """
        bindings = selection_bindings()
        root = compile_expression('value', bindings)
        condition = compile_expression('selected', bindings)
        spec = CalculationDefinition('rows', 'select', Interval(500_000_000, 4_000_000_000))
        reference = select_memory_reference(root, spec, condition=condition)
        array = select_memory_numpy(root, spec, condition=condition)
        # 接口是迭代器；输出消费时逐行产生，不返回预先累计的list。
        self.assertIsInstance(reference, Iterator)
        self.assertIsInstance(array, Iterator)
        rows = tuple(reference)
        self.assertEqual(rows, tuple(array))
        # .5保持/1秒TTL+条件更新/EOF均不产生目标行，仅2和3秒。
        self.assertEqual(tuple(row.time_ns for row in rows), (2_000_000_000, 3_000_000_000))
        self.assertEqual(tuple(row.selection for row in rows), (Truth.UNKNOWN, Truth.TRUE))
        self.assertEqual(rows[0].value.value, 8.)
        self.assertEqual(rows[0].unit, 'W')
        self.assertFalse(rows[1].value.valid)
        self.assertEqual(rows[0].binding_identity, root.identity + ':' + condition.identity)
        self.assertEqual(rows[0].source_refs, (bindings.source_ref('value'), bindings.source_ref('selected')))
        # 裁剪右端半开；零窗口不能靠保持值产生新行。
        empty = replace(spec, window=Interval(2_000_000_000, 2_000_000_000))
        self.assertEqual(tuple(select_memory_reference(root, empty, condition=condition)), ())
        self.assertEqual(tuple(select_memory_numpy(root, empty, condition=condition)), ())

    def test_enum_and_bool_memory_rows(self):
        """BOOL保留真假，ENUM公开标签域与invalid质量，不泄露数组整数码。

        参数: 无；同一个实际合成来源。
        返回: None。
        异常: 类型/标签或两个后端差异由断言报告。
        """
        bindings = selection_bindings()
        condition = compile_expression('selected', bindings)
        spec = CalculationDefinition('rows', 'select', Interval(500_000_000, 4_000_000_000))
        for name, dtype, expected in (('mode', D.ENUM, 'Run'), ('alarm', D.BOOL, False)):
            root = compile_expression(name, bindings)
            rows = tuple(select_memory_reference(root, spec, condition=condition))
            self.assertEqual(rows, tuple(select_memory_numpy(root, spec, condition=condition)))
            self.assertEqual((rows[0].value.dtype, rows[0].value.value, rows[1].value.valid), (dtype, expected, False))
            # 枚举未知也保留域，避免同码不同标签混淆。
            if dtype is D.ENUM:
                self.assertEqual(rows[0].value.labels, ('Idle', 'Run'))
                self.assertEqual(rows[1].value.labels, ('Idle', 'Run'))

    def test_time_and_duration_memory_chain(self):
        """两个原行桥接独立核对TTL平均与BOOL时长的手算结果。

        参数: 无；2W首秒、8W第三秒，其余未知。
        返回: None。
        异常: 完整结果或手算差异由断言报告。
        """
        bindings = selection_bindings()
        # 两个有效区间各一秒，均值(2+8)/2=5W，值覆盖1/2。
        root = compile_expression('value', bindings)
        spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 4_000_000_000))
        result = compute_memory_reference(root, spec)
        self.assertEqual(result, compute_memory_numpy(root, spec))
        self.assertEqual((result.value, result.value_coverage, result.status), (5., .5, 'partial'))
        # alarm首秒TRUE、第三秒FALSE，其他未知，TRUE时长1秒而非2秒。
        root = compile_expression('alarm', bindings)
        spec = replace(spec, operation='duration')
        result = compute_memory_reference(root, spec)
        self.assertEqual(result, compute_memory_numpy(root, spec))
        self.assertEqual((result.value, result.value_coverage, result.status), (1., .5, 'partial'))

    def test_same_time_group_and_large_integer_rows(self):
        """显式last_by_sequence的同刻组只输出最终状态一次；大整数不转float。

        参数: 无；显式同刻原行与uint64边界。
        返回: None。
        异常: 去重/类型或独立链差异由断言报告。
        """
        # 原同刻不同值默认拒绝；显式last_by_sequence才在组完成后取最终值。
        bindings = fixtures._memory(rows=((0, {'raw': 2.}), (1_000_000_000, {'raw': 8.}),
                                         (1_000_000_000, {'raw': 9.}), (3_000_000_000, {'raw': 0.})))
        spec = CalculationDefinition('rows', 'select', Interval(0, 3_000_000_000))
        for select in (select_memory_reference, select_memory_numpy):
            with self.assertRaises(ValueError):
                select(compile_expression('power', bindings), spec)
        # 只修改测试的显式政策，不改变产品既定冲突拒绝默认。
        bindings = SignalBindings(bindings.session, (replace(bindings.resolve('power'), same_time_policy='last_by_sequence'),))
        root = compile_expression('power', bindings)
        rows = tuple(select_memory_reference(root, spec))
        self.assertEqual(rows, tuple(select_memory_numpy(root, spec)))
        self.assertEqual(tuple(row.value.value for row in rows), (2., 9.))
        # 选择原生大整数，不经过float64归一化造成精度损失。
        series = _series((2**64-1, 2**53+1, 0), dtype=D.UINT64)
        rows = tuple(select_reference(series, spec))
        self.assertEqual(rows, tuple(select_numpy(series, spec)))
        self.assertEqual(tuple(row.value.value for row in rows), (2**64-1, 2**53+1))

    def test_selection_contract_errors(self):
        """拒绝标量算子、隐式单位换算、错绑定和FALSE输出协议。

        参数: 无；故意错误的声明。
        返回: None。
        异常: 未拒绝错误请求时产生断言失败。
        """
        series = _series((2., 8., 0.))
        spec = CalculationDefinition('rows', 'select', series.observation)
        for select in (select_reference, select_numpy):
            with self.assertRaises(ValueError):
                tuple(select(series, replace(spec, operation='time_weighted_mean')))
            with self.assertRaises(ValueError):
                tuple(select(series, replace(spec, output_unit='kW')))
        # 输出行只能TRUE或UNKNOWN，不能偷偷把FALSE输出给消费者。
        with self.assertRaises(TypeError):
            SelectionRow(0, ScalarValue(2., D.FLOAT64), Truth.FALSE, Q.NONE, 'binding', (), 'W')
        # 不能构造丢失UNKNOWN或无效值原因的行。
        with self.assertRaises(ValueError):
            SelectionRow(0, ScalarValue(2., D.FLOAT64), Truth.UNKNOWN, Q.NONE, 'binding', (), 'W')
        with self.assertRaises(ValueError):
            SelectionRow(0, ScalarValue(None, D.FLOAT64, False, Q.MISSING), Truth.TRUE, Q.NONE, 'binding', (), 'W')
        # 同名条件但实际输入不同，不能重用前一任务绑定。
        bindings = selection_bindings()
        root = compile_expression('value', bindings)
        condition = compile_expression('selected', fixtures._memory(rows=((0, {'raw': 2., 'selected': True}),)))
        for select in (select_memory_reference, select_memory_numpy):
            with self.assertRaises(ValueError):
                select(root, spec, condition=condition)


# 独立运行同一验收集，不产生文件或旧路径副作用。
if __name__ == '__main__':
    unittest.main()
