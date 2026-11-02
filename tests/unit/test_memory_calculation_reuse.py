"""验证内存示例在一次准备后按多个活动窗口计算，保留原逐窗结果。

输入为真实SignalBindings合成行，时间均为整数纳秒。先通过原单查询便利入口
独立重建旧调用方式，再比较示例的事件、指标、单位、覆盖、质量和完整身份。
真实归一化、共同轴和表达式函数仅加透传计数，不用假序列替代产品执行。
reference与NumPy分别运行，检查批长1/2/7、无活动、多活动、TTL和裁剪末点。

测试不读写文件、不运行旧CAN链或性能实验；所有prepared series仅属于当前
run。这里只证明重复准备被消除，不宣称每窗口归约有界或整个进程内存下降。
"""

# 比较完整冻结结果，仅允许沿用项目明确的浮点数值容差。
from dataclasses import replace
import unittest
# 透传实际函数以观察调用次数，不替换归一化、时间轴或数值真值。
from unittest.mock import patch
# 被修改的示例仍是实际入口，基准不调用其run_analysis。
from examples import memory_analysis as example
# 当前真实内存声明与完整编译协议，不造history或运行绑定。
from chronaxis.core import (DerivedDefinition, Interval, MemoryRow, CalculationDefinition, SessionSpec,
                            SignalBindings, SignalDefinition, SignalDType as D, SourceSpec,
                            TemporalRule, TimebaseSpec, TimeType, compile_expression)
# 分别保留原单查询桥及其独立的真实内部函数供计数。
from chronaxis.core import calculations_memory_reference as reference_bridge
from chronaxis.core import calculations_memory_numpy as numpy_bridge
# 原两条时序执行链，不重写状态机来制造预期事件。
from chronaxis.core.temporal_memory_reference import detect_memory_reference
from chronaxis.core.temporal_memory_numpy import detect_memory_numpy


SECOND = 1_000_000_000  # 合成数据的秒转整数纳秒，绝对时间不转float。


def _bindings(rows, *, start=0, end=12 * SECOND, voltage_age=20 * SECOND, current_age=20 * SECOND):
    """按原行顺序建立示例所需电压、电流及power名称声明。

    参数: rows为(time_ns,原字段dict)有限tuple；start/end为会话整数ns；
        voltage_age/current_age为对应字段的非负整数有效期，默认20秒。
    返回: SignalBindings，每个MemoryRow保留真实序号和只读原值副本。
    异常: 时间、值、字段或绑定非法时传播原模型TypeError/ValueError。
    """
    # 同一声明时钟不假设外部同步，来源首末与本次会话域明确相同。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'memory-reuse-test-v1')
    source = SourceSpec('sensor', clock,
                        tuple(MemoryRow(time, values, index) for index, (time, values) in enumerate(rows)),
                        observation_start_ns=start, observation_end_ns=end)
    # 两列独立有效期，缺值不补零，负电压保留真实有符号面积。
    signals = (SignalDefinition('voltage', 'sensor', 'raw_v', D.FLOAT64, 'V', voltage_age),
               SignalDefinition('current', 'sensor', 'raw_i', D.FLOAT64, 'A', current_age))
    return SignalBindings(SessionSpec('session', clock, start, end, (source,)), signals,
                          derived_names=('power',))


def _fixed_axis_input(activity_count):
    """在相同13个更新时间上构造一段或四段活动，隔离事件数对准备次数的影响。

    参数: activity_count为1或4，活动在偶数秒开始、下一奇数秒结束。
    返回: 当前真实SignalBindings，电压400V、电流活动内10A，域[0,12)秒。
    异常: 非法活动数主动ValueError，模型错误原样传播。
    """
    # 每种输入保留完全相同的更新时间和TTL边界，区别仅为当前电流值。
    if activity_count not in (1, 4):
        raise ValueError('本计数夹具只支持1或4个活动')
    rows = tuple((index * SECOND, {'raw_i': 10. if index % 2 == 0 and index < activity_count * 2 else 0.,
                                 **({'raw_v': 400.} if index == 0 else {})}) for index in range(13))
    return _bindings(rows)


def _input_facts(bindings):
    """复制有限原值及声明身份，用于检查调用前后实际输入未被改写。

    参数: bindings为本测试建立的真实内存绑定。
    返回: (完整identity,信号tuple,来源原行事实tuple)，值保留原类型。
    异常: 模型属性不符合实际接口时直接失败，不读取私有缓存。
    """
    # 复制每行time/sequence/items，避免只保存同一个可变对象后自证未改变。
    rows = tuple((source.name, tuple((row.time_ns, row.sequence, tuple(row.values.items()))
                                    for row in source.rows)) for source in bindings.session.sources)
    return bindings.identity, bindings.signals, rows


def _original_analysis(bindings, *, backend, batch_rows, duration_ns=0):
    """按修复前每窗口重新准备的真实便利入口得到完整对照结果。

    参数: bindings为真实输入；backend为reference/numpy；batch_rows为正整数；
        duration_ns为持续阈值整数ns，默认0以保留短活动。
    返回: 与示例相同的(events,session_result,(event_id,calculation)tuple)。
    异常: 原编译、检测或单窗口指标异常直接传播，不依赖修改后的示例实现。
    """
    # 使用相同公开声明与规则标识，身份差异不能用删字段消除。
    derived = (DerivedDefinition('power', 'voltage * current', 'W'),)
    power = compile_expression('power', bindings, derived=derived)
    condition = compile_expression('current > 5', bindings, derived=derived)
    rule = TemporalRule('active', 'memory_demo', bindings.session.session_id, 'condition_duration', duration_ns)
    detector = detect_memory_reference if backend == 'reference' else detect_memory_numpy
    compute = reference_bridge.compute_memory_reference if backend == 'reference' else numpy_bridge.compute_memory_numpy
    # 真实时序链与每次单查询桥保留旧调用，作为新复用途径的独立对照。
    events = detector(condition, rule, batch_rows=batch_rows)
    spec = CalculationDefinition('session_energy', 'integral',
                      Interval(bindings.session.domain_start_ns, bindings.session.domain_end_ns))
    session = compute(power, spec, condition=condition)
    calculations = tuple((event.event_id, compute(power, CalculationDefinition('event_energy', 'integral',
                    Interval(event.start_ns, event.end_ns), scope='event')))
                    for event in events if event.event_type == 'activity')
    return events, session, calculations


class MemoryCalculationReuseTests(unittest.TestCase):
    """核对真实准备次数、完整结果和跨运行隔离，不凭运行速度判定优化成功。"""

    def _assert_calculation_equal(self, expected, actual):
        """严格比较完整指标，仅浮点value允许项目已有的明确容差。

        参数: expected来自原逐窗桥；actual来自复用序列，两者均为CalculationResult。
        返回: None。异常: 数值、请求、质量、覆盖、计数、来源或身份差异使断言失败。
        """
        # 不放宽None/整数或任何追溯事实，也不用默认小数位吞掉ns级数值。
        if type(expected.value) is float and type(actual.value) is float:
            self.assertAlmostEqual(expected.value, actual.value,
                                   delta=max(1e-18, abs(expected.value) * 1e-12))
            self.assertEqual(expected, replace(actual, value=expected.value))
        else:
            self.assertEqual(expected, actual)

    def _assert_analysis_equal(self, expected, actual):
        """核对事件及每个指标的基数、ID、顺序和完整结果。

        参数: expected/actual为两个完整分析返回tuple。
        返回: None。异常: 事件或指标事实差异导致unittest失败。
        """
        # zip之前必须核基数，防重复或漏行被截断掩盖。
        self.assertEqual(expected[0], actual[0])
        self._assert_calculation_equal(expected[1], actual[1])
        self.assertEqual(len(expected[2]), len(actual[2]))
        for (expected_id, expected_calculation), (actual_id, actual_calculation) in zip(expected[2], actual[2]):
            self.assertEqual(expected_id, actual_id)
            self._assert_calculation_equal(expected_calculation, actual_calculation)

    def _observe(self, bindings, backend, *, batch_rows=1, duration_ns=0):
        """在指标桥真实函数外加透传计数，时序检测内部不纳入指标准备计数。

        参数: bindings/backend为当前输入与独立实现；batch_rows默认1；duration_ns默认0。
        返回: (真实示例结果,次数dict)，包含归一化/建轴/表达式/完整准备次数，
            condition_flags逐次记录是否明确传入会话条件。
        异常: 真实函数或分析错误原样传播，patch退出后恢复原引用。
        """
        # patch指标模块已导入的引用，不替换原函数返回值或全局数值内核。
        bridge = reference_bridge if backend == 'reference' else numpy_bridge
        normalize_name = 'memory_series_reference' if backend == 'reference' else 'memory_series_numpy'
        evaluate_name = 'evaluate_reference' if backend == 'reference' else 'evaluate_numpy'
        prepare_name = 'build_calculation_series_reference' if backend == 'reference' else 'build_calculation_series_numpy'
        with patch.object(bridge, normalize_name, wraps=getattr(bridge, normalize_name)) as normalize, \
                patch.object(bridge, 'common_timeline', wraps=bridge.common_timeline) as timeline, \
                patch.object(bridge, evaluate_name, wraps=getattr(bridge, evaluate_name)) as evaluate, \
                patch.object(example, prepare_name, wraps=getattr(example, prepare_name)) as prepare:
            actual = example.run_analysis(bindings, backend=backend, batch_rows=batch_rows, duration_ns=duration_ns)
            counts = {'normalize': normalize.call_count, 'timeline': timeline.call_count,
                      'evaluate': evaluate.call_count, 'prepare': prepare.call_count,
                      'condition_flags': tuple(call.kwargs.get('condition') is not None
                                               for call in prepare.call_args_list)}
        return actual, counts

    def test_default_example_matches_original_and_hand_truth_for_all_batches(self):
        """两段8000/16000J与会话24000J在两后端及批长1/2/7保持完整事实。

        参数: 无。返回: None。异常: 手算、原逐窗对照或原输入保护失败即失败。
        """
        # 同一个冻结输入反复运行，不靠每次重建输入隐藏修改或缓存污染。
        bindings = example.build_bindings()
        before = _input_facts(bindings)
        for backend in ('reference', 'numpy'):
            for batch in (1, 2, 7):
                with self.subTest(backend=backend, batch=batch):
                    expected = _original_analysis(bindings, backend=backend, batch_rows=batch,
                                                  duration_ns=SECOND)
                    actual = example.run_analysis(bindings, backend=backend, batch_rows=batch)
                    self._assert_analysis_equal(expected, actual)
                    self.assertEqual([calculation.value for _, calculation in actual[2]], [8000., 16000.])
                    self.assertEqual(actual[1].value, 24000.)
                    self.assertEqual(_input_facts(bindings), before)

    def test_no_activity_prepares_only_conditional_session(self):
        """全FALSE没有活动时只准备会话条件序列，不产生无用event历史。

        参数: 无。返回: None。异常: 活动、指标或真实准备次数多出即失败。
        """
        # 原行仍含真实两列，零能量来自已知FALSE，不来自缺值填零。
        bindings = _bindings(((0, {'raw_v': 400., 'raw_i': 0.}),
                              (12 * SECOND, {'raw_i': 0.})))
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                actual, counts = self._observe(bindings, backend)
                self._assert_analysis_equal(_original_analysis(bindings, backend=backend, batch_rows=1), actual)
                self.assertEqual(actual[2], ())
                self.assertEqual(actual[1].value, 0.)
                self.assertEqual((counts['normalize'], counts['timeline'], counts['prepare']), (2, 1, 1))
                self.assertEqual(counts['condition_flags'], (True,))

    def test_real_preparation_counts_do_not_grow_with_activity_count(self):
        """同13点轴的一段/四段活动都只逐列归一化四次、建轴两次，不重做指标表达式。

        参数: 无。返回: None。异常: 真实包装函数未被调用或次数随活动增多即失败。
        """
        # 同行数/更新时间隔离活动数，参考逐时求值和数组整列求值分别核实。
        for backend in ('reference', 'numpy'):
            observed = []
            for activity_count in (1, 4):
                with self.subTest(backend=backend, activities=activity_count):
                    bindings = _fixed_axis_input(activity_count)
                    actual, counts = self._observe(bindings, backend)
                    self.assertEqual(len(actual[2]), activity_count)
                    self.assertEqual((counts['normalize'], counts['timeline'], counts['prepare']), (4, 2, 2))
                    self.assertEqual(counts['evaluate'], 39 if backend == 'reference' else 3)
                    self.assertEqual(counts['condition_flags'], (True, False))
                    observed.append(counts)
            self.assertEqual(observed[0], observed[1])

    def test_each_run_prepares_again_and_changed_input_has_own_identity(self):
        """重复调用不继承prepared列；相同名字但不同真实输入重新绑定并返回不同能量。

        参数: 无。返回: None。异常: 复用上轮缓存、修改输入或跨绑定身份混用即失败。
        """
        first = _fixed_axis_input(1)
        second = _fixed_axis_input(4)
        first_facts, second_facts = _input_facts(first), _input_facts(second)
        self.assertNotEqual(first.identity, second.identity)
        for backend in ('reference', 'numpy'):
            # 首轮/改值/再首轮都经过真实准备；相同输入的完整结果必须可重复。
            left, left_counts = self._observe(first, backend)
            middle, middle_counts = self._observe(second, backend)
            right, right_counts = self._observe(first, backend)
            self._assert_analysis_equal(left, right)
            self.assertEqual((left_counts, middle_counts, right_counts), (left_counts,) * 3)
            self.assertEqual((left[1].value, middle[1].value), (4000., 16000.))
            self.assertNotEqual(left[1].binding_identity, middle[1].binding_identity)
            self.assertEqual((_input_facts(first), _input_facts(second)), (first_facts, second_facts))

    def test_ttl_gaps_negative_power_and_confirmation_between_updates(self):
        """保留TTL缺失、负面积和更新之间的确认时刻，活动积分不偷偷继承条件。

        参数: 无。返回: None。异常: 覆盖、未知区间、事件确认或负能量差异即失败。
        """
        # 第二活动电压仅保持0.7秒，后0.8秒为未知；不能因当前活动TRUE延长它。
        bindings = _bindings(((0, {'raw_v': 400., 'raw_i': 10.}),
                              (SECOND // 2, {'raw_i': 0.}),
                              (SECOND, {'raw_v': -400., 'raw_i': 20.}),
                              (5 * SECOND // 2, {'raw_i': 0.}),
                              (3 * SECOND, {'raw_v': 400.})), end=3 * SECOND,
                             voltage_age=700_000_000, current_age=4 * SECOND)
        for backend in ('reference', 'numpy'):
            for batch in (1, 2, 7):
                with self.subTest(backend=backend, batch=batch):
                    expected = _original_analysis(bindings, backend=backend, batch_rows=batch,
                                                  duration_ns=SECOND // 10)
                    actual = example.run_analysis(bindings, backend=backend, batch_rows=batch,
                                                  duration_ns=SECOND // 10)
                    self._assert_analysis_equal(expected, actual)
                    self.assertEqual(len(actual[2]), 2)
                    self.assertEqual(actual[0][0].confirmed_ns, SECOND // 10)
                    self.assertEqual(actual[2][0][1].value, 2000.)
                    self.assertAlmostEqual(actual[2][1][1].value, -5600., delta=1e-9)
                    self.assertEqual(actual[2][1][1].value_unknown_ranges,
                                     (Interval(1_700_000_000, 2_500_000_000),))

    def test_prepared_series_clips_between_samples_and_at_int64_end(self):
        """现有typed归约自己裁剪边界，复用全域轴仍与逐窗插入边界的原桥一致。

        参数: 无。返回: None。异常: 小间隔、大绝对ns或零长窗口事实变化即失败。
        """
        # 使用12ns短域而非float秒，并在INT64上界附近复用相同形状的原输入。
        for base in (0, 2 ** 63 - 13):
            bindings = _bindings(((base, {'raw_v': 400., 'raw_i': 10.}),
                                  (base + 3, {'raw_i': 20.}), (base + 9, {'raw_i': 0.}),
                                  (base + 12, {})), start=base, end=base + 12)
            derived = (DerivedDefinition('power', 'voltage * current', 'W'),)
            power = compile_expression('power', bindings, derived=derived)
            for backend in ('reference', 'numpy'):
                bridge = reference_bridge if backend == 'reference' else numpy_bridge
                prepare = bridge.build_calculation_series_reference if backend == 'reference' else bridge.build_calculation_series_numpy
                single = bridge.compute_memory_reference if backend == 'reference' else bridge.compute_memory_numpy
                compute = example.compute_reference if backend == 'reference' else example.compute_numpy
                full = CalculationDefinition('prepared', 'integral', Interval(base, base + 12))
                series = prepare(power, full)
                for start, end in ((1, 2), (2, 8), (8, 11), (0, 12), (3, 3), (12, 12)):
                    with self.subTest(base=base, backend=backend, window=(start, end)):
                        spec = CalculationDefinition('window', 'integral', Interval(base + start, base + end), scope='event')
                        self._assert_calculation_equal(single(power, spec), compute(series, spec))

    def test_condition_only_updates_and_synthetic_boundaries_are_not_samples(self):
        """只变条件和窗口裁剪点不新增数值样本，完整prepared序列仍保原单查询事实。

        参数: 无。返回: None。异常: 样本计数、条件诊断或半开右端行为变化即失败。
        """
        # 直接用同一typed复用协议核电压表达式；电流仅作条件，便于分清两种更新。
        bindings = _bindings(((0, {'raw_v': 400., 'raw_i': 10.}),
                              (2 * SECOND, {'raw_i': 0.}), (3 * SECOND, {'raw_i': 20.}),
                              (5 * SECOND, {'raw_v': 500.}), (6 * SECOND, {'raw_i': 0.})),
                             end=6 * SECOND)
        # 绑定已登记power，编译任何根时仍须交齐同一组派生声明，不能跳过静态合同。
        derived = (DerivedDefinition('power', 'voltage * current', 'W'),)
        voltage = compile_expression('voltage', bindings, derived=derived)
        condition = compile_expression('current > 5', bindings, derived=derived)
        for backend in ('reference', 'numpy'):
            bridge = reference_bridge if backend == 'reference' else numpy_bridge
            prepare = bridge.build_calculation_series_reference if backend == 'reference' else bridge.build_calculation_series_numpy
            single = bridge.compute_memory_reference if backend == 'reference' else bridge.compute_memory_numpy
            compute = example.compute_reference if backend == 'reference' else example.compute_numpy
            spec = CalculationDefinition('voltage_time', 'integral', Interval(0, 6 * SECOND))
            series = prepare(voltage, spec, condition=condition)
            # [0.5,5)排除0秒真实样本，5秒为右端；内部条件变动不能增加样本。
            clipped = replace(spec, window=Interval(SECOND // 2, 5 * SECOND))
            actual = compute(series, clipped)
            self._assert_calculation_equal(single(voltage, clipped, condition=condition), actual)
            self.assertEqual(actual.valid_sample_count, 0)
            self.assertEqual(actual.value, 1400.)

    def test_zero_domain_preserves_original_result_without_activity_preparation(self):
        """真实单点零域保原零长政策，未确认活动不建立无条件序列或增加面积。

        参数: 无。返回: None。异常: 事件/指标或准备次数和原桥不同即失败。
        """
        bindings = _bindings(((8, {'raw_v': 400., 'raw_i': 10.}),), start=8, end=8)
        before = _input_facts(bindings)
        for backend in ('reference', 'numpy'):
            actual, counts = self._observe(bindings, backend, duration_ns=SECOND)
            expected = _original_analysis(bindings, backend=backend, batch_rows=1, duration_ns=SECOND)
            self._assert_analysis_equal(expected, actual)
            self.assertEqual(actual[2], ())
            self.assertEqual(counts['prepare'], 1)
            self.assertEqual(actual[1].window_duration_ns, 0)
            self.assertEqual(_input_facts(bindings), before)

    def test_errors_and_cancellation_keep_original_exception_and_input(self):
        """真实准备后取消原对象向上传播，退出patch后下一次运行仍重新准备并成功。

        参数: 无。返回: None。异常: 取消被包装/吞掉、原输入变动或错误配置被接受即失败。
        """
        bindings = example.build_bindings()
        before = _input_facts(bindings)
        for backend in ('reference', 'numpy'):
            name = 'build_calculation_series_reference' if backend == 'reference' else 'build_calculation_series_numpy'
            original = getattr(example, name)
            for error in (OSError('home preparation failure'), KeyboardInterrupt('home cancellation')):
                def prepare_then_fail(compiled, spec, *, condition=None):
                    """透传真实准备，在第一个活动序列已建成后抛原异常。

                    参数: compiled/spec/condition与真实builder相同。
                    返回: 条件会话的真实CalculationSeries；无条件活动不返回。
                    异常: 本子例同一error对象；其余真实准备异常原样传播。
                    """
                    # 失败不是假模型注入：原准备确实执行，且会话路径已先完成。
                    series = original(compiled, spec, condition=condition)
                    if condition is None:
                        raise error
                    return series
                with self.subTest(backend=backend, error=type(error).__name__):
                    with patch.object(example, name, side_effect=prepare_then_fail):
                        with self.assertRaises(type(error)) as captured:
                            example.run_analysis(bindings, backend=backend)
                    self.assertIs(captured.exception, error)
                    self.assertEqual(_input_facts(bindings), before)
            # 失败不在模块留下prepared缓存，同输入恢复运行仍与原桥完整相同。
            actual = example.run_analysis(bindings, backend=backend)
            self._assert_analysis_equal(_original_analysis(bindings, backend=backend, batch_rows=65536,
                                                          duration_ns=SECOND), actual)
        # 原检测器仍负责整数/持续时间校验，优化不提前创建列绕过错误。
        for kwargs, error_type in (({'backend': 'other'}, ValueError),
                                   ({'batch_rows': 0}, TypeError), ({'duration_ns': -1}, ValueError)):
            with self.subTest(invalid=kwargs):
                with self.assertRaises(error_type):
                    example.run_analysis(bindings, **kwargs)


# 直接执行仅运行本专项；导入不会启动实验、读写文件或运行旧程序。
if __name__ == '__main__':
    unittest.main()
