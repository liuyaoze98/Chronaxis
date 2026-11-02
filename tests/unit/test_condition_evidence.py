"""以手算三视图验证纯条件证据装箱和两个独立计算入口。

输入为冻结Evaluation或ArrayEvaluation、精确纳秒和四类明确标志，
输出为ConditionTick元组。预期三值、实际未知因果、末点及诊断手写；
数组夹具仅转换输入模型，不以被测输出生成真值。无来源读取、状态提交、
预算或AnalysisRunner接线；专项日志在work/m2-run-tests，实际产出设备为work。
"""

# 复用typed数值模型，不调用表达式求值或保持计算生成测试预期。
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis.core.condition_evidence import condition_ticks_reference, condition_ticks_numpy
from chronaxis.core.expression_reference import Evaluation
from chronaxis.core.expression_numpy import ArrayEvaluation
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.numeric_numpy import NumericArray
from chronaxis.core.temporal import ConditionTick
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, Truth as T


def evaluation(state, quality=Q.NONE, diagnostic=Q.NONE):
    """建立一个明确BOOL结果，UNKNOWN原值为None而不是已知False。

    参数: state三值、quality结果原因、diagnostic依赖原因。
    返回: Evaluation。异常: 质量/有效性矛盾由ScalarValue拒绝。
    """
    # 质量和诊断独立，已知三值可携带被决定性逻辑遮蔽的依赖质量。
    known = state is not T.UNKNOWN
    return Evaluation(ScalarValue(state is T.TRUE if known else None, D.BOOL, known, quality), diagnostic)


def array_evaluation(rows):
    """把给定标量输入事实装入独立只读数组，禁止从输出反推输入。

    参数: rows为Evaluation tuple。返回: 形状(N,)的ArrayEvaluation。
    异常: 非法dtype/质量由数组模型拒绝。
    """
    # 无效位置False仅为物理占位；valid/quality保持原BOOL事实，单位不参与本纯接口。
    values = np.array([row.value.value if row.value.valid else False for row in rows], dtype='bool')
    valid = np.array([row.value.valid for row in rows], dtype='bool')
    quality = np.array([int(row.value.quality) for row in rows], dtype='uint16')
    diagnostic = np.array([int(row.dependency_quality) for row in rows], dtype='uint16')
    return ArrayEvaluation(NumericArray(D.BOOL, values, valid, quality), diagnostic)


def numpy_arguments(arguments):
    """仅将参考输入协议转换为同一事实的数组协议。

    参数: arguments为八项参考输入tuple。返回: 八项NumPy输入tuple。
    异常: 输入布局或定宽转换错误传播。
    """
    # 时间保持int64；三个结果与四个bool列均一维，N=0也保留准确物理类型。
    return (np.array(arguments[0], dtype='int64'),
            *(array_evaluation(rows) for rows in arguments[1:4]),
            *(np.array(flags, dtype='bool') for flags in arguments[4:]))


class ConditionEvidenceTests(unittest.TestCase):
    """验证手算因果、诊断、分批及严格输入协议，无跨任务共享状态。"""

    def cases(self):
        """给出独立手算矩阵，每行保存三个结果、四标志及预期actual_unknown。

        参数: 无。返回: 小tuple矩阵。异常: 非法夹具模型错误传播。
        """
        # 前五行分别为旁列刷新、known揭示未知、实际invalid、质量新增和质量移除。
        unknown = evaluation(T.UNKNOWN, Q.STALE, Q.MISSING)
        missing = evaluation(T.UNKNOWN, Q.MISSING)
        both = evaluation(T.UNKNOWN, Q.STALE | Q.MISSING)
        known = evaluation(T.TRUE)
        return ((unknown, unknown, unknown, True, False, False, False, False),
                (known, missing, missing, True, False, False, False, True),
                (missing, missing, missing, True, True, False, False, True),
                (unknown, both, both, True, False, False, False, True),
                (both, unknown, unknown, True, False, False, False, False),
                # 没有真实更新，即使before已知，也不能宣称实际更新导致未知。
                (known, missing, missing, False, False, False, False, False),
                # 决定性TRUE/FALSE结果仍known，不因依赖未知或invalid标志强制结束。
                (unknown, evaluation(T.TRUE, diagnostic=Q.MISSING),
                 evaluation(T.TRUE, diagnostic=Q.STALE), True, True, True, False, False),
                (known, evaluation(T.FALSE, diagnostic=Q.STALE),
                 evaluation(T.FALSE, diagnostic=Q.MISSING), True, True, False, False, False))

    def arguments(self, cases, *, start=0):
        """从小手算矩阵建立八项参考输入，不计算产品证据。

        参数: cases当前矩阵、start精确整数起点。返回: 八项tuple输入。
        异常: 非法矩阵索引或时间由调用方验证。
        """
        # 仅重排输入字段；严格递增时间可用于极值附近的1ns对照。
        return (tuple(start + index for index in range(len(cases))),
                *(tuple(case[index] for case in cases) for index in range(7)))

    def expected(self, cases, *, start=0):
        """按矩阵中手写因果答案建立预期typed结果，不调用被测函数。

        参数: cases手算矩阵、start整数ns。返回: ConditionTick tuple。
        异常: 夹具质量冲突由模型拒绝。
        """
        # state来自输入明确真值；诊断只OR实际continuous/point，不含before反事实。
        states = (T.UNKNOWN, T.UNKNOWN, T.UNKNOWN, T.UNKNOWN, T.UNKNOWN, T.UNKNOWN, T.TRUE, T.FALSE)
        return tuple(ConditionTick(start + index, states[index], case[1].value.quality,
                                   case[3], case[5], case[6], states[index], case[2].value.quality,
                                   case[7], case[1].dependency_quality | case[2].dependency_quality)
                     for index, case in enumerate(cases))

    def test_hand_causal_matrix_known_logic_and_actual_diagnostics(self):
        """手算因果矩阵区分TTL与真实更新，决定性逻辑不被依赖诊断强制未知。

        参数: 无。返回: None。异常: 因果、三值或诊断与手算不符断言失败。
        """
        # 同一明确输入事实分别进入两个独立入口，期望不来自任何被测输出。
        cases = self.cases()
        arguments = self.arguments(cases)
        expected = self.expected(cases)
        self.assertEqual(condition_ticks_reference(*arguments), expected)
        self.assertEqual(condition_ticks_numpy(*numpy_arguments(arguments)), expected)

    def test_terminal_forces_continuous_missing_preserves_known_point_and_ignores_before_diagnostic(self):
        """末点连续UNKNOWN/MISSING、真实点TRUE/FALSE原样保留且before诊断不泄漏。

        参数: 无。返回: None。异常: 半开连续或反事实诊断混淆断言失败。
        """
        for state in (T.TRUE, T.FALSE):
            # before有独立STALE，实际两个视图diagnostic均NONE，不能把STALE附入tick。
            arguments = ((3,), (evaluation(T.UNKNOWN, Q.STALE, Q.STALE),),
                         (evaluation(state),), (evaluation(state),), (True,), (False,), (True,), (True,))
            expected = (ConditionTick(3, T.UNKNOWN, Q.MISSING, True, True, True,
                                      state, Q.NONE, False, Q.NONE),)
            self.assertEqual(condition_ticks_reference(*arguments), expected)
            self.assertEqual(condition_ticks_numpy(*numpy_arguments(arguments)), expected)

    def test_empty_splits_and_adjacent_integer_extremes_match_hand_answers(self):
        """空批/1/2/7切分没有共享状态，极值附近相邻ns保持精确。

        参数: 无。返回: None。异常: 切分重置、dtype或时间量化断言失败。
        """
        empty = ((),) * 8
        self.assertEqual(condition_ticks_reference(*empty), ())
        self.assertEqual(condition_ticks_numpy(*numpy_arguments(empty)), ())
        # 只用合法8ns短轴，避开int64溢出；完整输出独立对照手算矩阵。
        for start in (-(2 ** 63), 2 ** 53 + 1, 2 ** 63 - 8):
            cases = self.cases()
            arguments, expected = self.arguments(cases, start=start), self.expected(cases, start=start)
            for size in (1, 2, 7):
                reference, numpy = [], []
                for offset in range(0, len(cases), size):
                    current = tuple(column[offset:offset + size] for column in arguments)
                    reference.extend(condition_ticks_reference(*current))
                    numpy.extend(condition_ticks_numpy(*numpy_arguments(current)))
                self.assertEqual(tuple(reference), expected)
                self.assertEqual(tuple(numpy), expected)

    def test_terminal_ttl_and_early_source_end_keep_point_causality_separate(self):
        """TTL与EOF并列不伪造真实无效更新，来源末点仍独立于连续视图。

        参数: 无。
        返回: None。
        异常: 因果、连续质量或点证据与手算不符时断言失败。
        """
        # 旁列真实刷新恰遇TTL，更新前点已经STALE，因此没有新增实际未知原因。
        stale = evaluation(T.UNKNOWN, Q.STALE, Q.STALE)
        missing = evaluation(T.UNKNOWN, Q.MISSING, Q.MISSING)
        arguments = ((3,), (stale,), (stale,), (stale,),
                     (True,), (False,), (True,), (True,))
        expected = (ConditionTick(3, T.UNKNOWN, Q.STALE | Q.MISSING, True, True, True,
                                  T.UNKNOWN, Q.STALE, False, Q.STALE),)
        self.assertEqual(condition_ticks_reference(*arguments), expected)
        self.assertEqual(condition_ticks_numpy(*numpy_arguments(arguments)), expected)
        # 来源提前结束但会话继续：连续值未知，真实末点TRUE仍known，不因MISSING变未知。
        arguments = ((4,), (evaluation(T.TRUE),), (missing,),
                     (evaluation(T.TRUE),), (True,), (False,), (True,), (False,))
        expected = (ConditionTick(4, T.UNKNOWN, Q.MISSING, True, True, False,
                                  T.TRUE, Q.NONE, False, Q.MISSING),)
        self.assertEqual(condition_ticks_reference(*arguments), expected)
        self.assertEqual(condition_ticks_numpy(*numpy_arguments(arguments)), expected)
        # 常量条件的会话终点可以没有来源EOF或实际更新，不建立虚构的来源结束证据。
        known = (evaluation(T.TRUE),)
        arguments = ((5,), known, known, known, (False,), (False,), (False,), (True,))
        expected = (ConditionTick(5, T.UNKNOWN, Q.MISSING, False, False, True,
                                  T.TRUE, Q.NONE, False, Q.NONE),)
        self.assertEqual(condition_ticks_reference(*arguments), expected)
        self.assertEqual(condition_ticks_numpy(*numpy_arguments(arguments)), expected)

    def test_full_int64_jump_is_accepted_without_difference_overflow(self):
        """合法的int64最小到最大坐标跳跃不因差分溢出而被误判为回退。

        参数: 无。
        返回: None。
        异常: 时间量化、回绕或正常点证据丢失时断言失败。
        """
        # 时间比较无需计算相减；该合法间隔大于有符号int64的最大可存储差值。
        times = (-(2 ** 63), 2 ** 63 - 1)
        known = (evaluation(T.TRUE), evaluation(T.FALSE))
        arguments = (times, known, known, known, (True, True),
                     (False, False), (False, False), (False, False))
        expected = (ConditionTick(times[0], T.TRUE), ConditionTick(times[1], T.FALSE))
        self.assertEqual(condition_ticks_reference(*arguments), expected)
        self.assertEqual(condition_ticks_numpy(*numpy_arguments(arguments)), expected)

    def test_reference_rejects_types_lengths_time_order_terminal_and_flag_conflicts(self):
        """参考接口拒绝非BOOL/非原生tuple、时间回退及实际因果/终点结构错误。

        参数: 无。返回: None。异常: 不合法输入被接受断言失败。
        """
        arguments = self.arguments(self.cases()[:2])
        # 每个错误只改变一个输入维度，拒绝不能依赖隐式truthiness或截断对齐。
        malformed = ((0, [0, 1]), (0, (False, 1)), (0, (0.0, 1)), (0, (np.int64(0), 1)),
                     (1, list(arguments[1])), (1, (object(), object())),
                     (1, (Evaluation(ScalarValue(1, D.INT64), Q.NONE),) * 2),
                     (1, (Evaluation(object(), Q.NONE),) * 2),
                     (1, (Evaluation(evaluation(T.TRUE).value, 0),) * 2),
                     (4, (1, True)), (4, [True, True]))
        for index, replacement in malformed:
            current = list(arguments)
            current[index] = replacement
            with self.assertRaises(TypeError):
                condition_ticks_reference(*current)
        # 相同/回退坐标、非末/重复terminal和invalid缺actual均属语义结构矛盾。
        malformed = ((0, (0, 0)), (0, (1, 0)), (2, arguments[2][:1]),
                     (7, (True, False)), (7, (True, True)), (4, (False, False)))
        for index, replacement in malformed:
            current = list(arguments)
            current[index] = replacement
            if index == 4:
                current[5] = (True, False)
            with self.assertRaises(ValueError):
                condition_ticks_reference(*current)
        # 参考坐标明确拒绝两个int64边界外的整数，不把无界Python int当合法时间。
        for times in ((-(2 ** 63) - 1, 1), (0, 2 ** 63)):
            with self.assertRaises(OverflowError):
                condition_ticks_reference(times, *arguments[1:])

    def test_numpy_rejects_dtypes_shapes_non_bool_time_order_and_flag_conflicts(self):
        """数组接口拒绝隐式cast/broadcast、非BOOL结果及时间/因果/终点矛盾。

        参数: 无。返回: None。异常: 错误数组协议被接受断言失败。
        """
        arguments = numpy_arguments(self.arguments(self.cases()[:2]))
        numeric = ArrayEvaluation(NumericArray(D.INT64, np.array([1, 2], dtype='int64'),
                                              np.ones(2, dtype='bool'), np.zeros(2, dtype='uint16')),
                                  np.zeros(2, dtype='uint16'))
        # 物理类型与形状必须显式满足协议，函数不能悄悄astype或flatten。
        malformed = ((0, np.array([0, 1], dtype='float64')), (0, np.array([[0, 1]], dtype='int64')),
                     (1, numeric), (1, object()), (4, np.array([1, 1], dtype='uint8')),
                     (4, np.array([[True, True]], dtype='bool')), (4, (True, True)))
        for index, replacement in malformed:
            current = list(arguments)
            current[index] = replacement
            with self.assertRaises(TypeError):
                condition_ticks_numpy(*current)
        # 长度错位不得广播；整列重复/回退、终点及invalid标志独立拒绝。
        malformed = ((0, np.array([0, 0], dtype='int64')), (0, np.array([1, 0], dtype='int64')),
                     (1, array_evaluation(self.cases()[0][:1])),
                     (4, np.array([True], dtype='bool')), (7, np.array([True, False], dtype='bool')),
                     (7, np.array([True, True], dtype='bool')), (4, np.array([False, False], dtype='bool')))
        for index, replacement in malformed:
            current = list(arguments)
            current[index] = replacement
            if index == 4 and len(replacement) == 2:
                current[5] = np.array([True, False], dtype='bool')
            with self.assertRaises(ValueError):
                condition_ticks_numpy(*current)

    def test_independent_entries_do_not_modify_input_arrays_or_call_other_kernel(self):
        """两个入口不互调，数组输入包括四标志保持原值和只读约定。

        参数: 无。返回: None。异常: 互调数值核或原地修改输入断言失败。
        """
        arguments = self.arguments(self.cases())
        arrays = numpy_arguments(arguments)
        # 逐列保存输入快照，标志也设置只读，排除原地修改mask的实现。
        columns = (arrays[0], *(column for result in arrays[1:4] for column in
                               (result.value.values, result.value.valid, result.value.quality,
                                result.dependency_quality)), *arrays[4:])
        copies = tuple(column.copy() for column in columns)
        for column in columns:
            column.flags.writeable = False
        with patch('chronaxis.core.condition_evidence.condition_ticks_reference',
                   side_effect=AssertionError('数组入口不得调用参考核')):
            self.assertEqual(condition_ticks_numpy(*arrays), self.expected(self.cases()))
        with patch('chronaxis.core.condition_evidence.condition_ticks_numpy',
                   side_effect=AssertionError('参考入口不得调用数组核')):
            self.assertEqual(condition_ticks_reference(*arguments), self.expected(self.cases()))
        for column, copy in zip(columns, copies):
            np.testing.assert_array_equal(column, copy)
            self.assertFalse(column.flags.writeable)
