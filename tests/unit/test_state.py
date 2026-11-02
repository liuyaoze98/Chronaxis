"""检查查询时刻应保持哪个值，以及无效更新和过期怎样改变状态。

输入是已规范化合成样本、明确有效期、来源观测范围和查询时间轴，
输出为unittest断言。手算同刻更新、无历史、末点和过期边界，再用固定种子
独立对照参考与NumPy；参考不调用被测数组内核。无效更新必须覆盖旧值，
完整同刻组跨批时只能一次提交。还检查混合信号类型、数组所有权和会话隔离。
测试只使用内存，不写文件，不读取旧日志；数组占位值必须按有效性掩码解释。
"""

# 固定种子生成可重复边界样例，unittest报告真实失败。
import random
import unittest
from dataclasses import replace

# 数组仅用于被测后端和输出核对，参考保持使用Python整数。
import numpy as np

# 实际core入口及独立数组模块，不以mock代替状态行为。
from chronaxis.core import (AtomicUpdateBuffer, MemoryRow, QualityFlag, SessionSpec, SignalBindings,
                            SignalDefinition, SignalDType, SignalSample, SignalSeries, SourceRef,
                            SourceSpec, TimebaseSpec, TimeType, align_reference, common_timeline, iter_time_groups)
from chronaxis.core.state_numpy import SignalArray, align_numpy, build_signal_array


def _series(observations=((0, 1, True, QualityFlag.NONE),), *, age=2, end=5,
            dtype=SignalDType.INT64, same_time_policy="error", base=0, known_end=True,
            choices=()) -> SignalSeries:
    """构造含真实原行身份的已规范化合成序列。

    参数: observations为(time相对ns,value,valid,quality)tuple；age/end/base为ns；
        dtype为目标逻辑类型；known_end=False仅使用实际末行收尾。
    返回: SignalSeries，当前signal_a/source_a、domain[base,base+end]点范围。
    异常: 所有模型/定义/状态错误直接传播，负例不修补。
    """
    # 公共起点为明示合成，不当作真实同步事实。
    clock = TimebaseSpec("clock", TimeType.RELATIVE, "synthetic-state-v1")
    # 原时间和原序号稳定，来源不排序或丢掉invalid行。
    rows = tuple(MemoryRow(base + time, {"raw.value": value}, sequence)
                 for sequence, (time, value, _, _) in enumerate(observations))
    # 观测end明确或未知，未知不补周期。
    source = SourceSpec("source_a", clock, rows, observation_start_ns=base,
                        observation_end_ns=base + end if known_end else None)
    # 当前分析域首末端明确，不从其他来源延长。
    session = SessionSpec("session_a", clock, base, base + end, (source,))
    # 没有数值转换，STATE仅接已经规范化的观测。
    definition = SignalDefinition("signal_a", "source_a", "raw.value", dtype, "1", age,
                                  same_time_policy=same_time_policy, choices=choices)
    # 当前引用严格定位原行和字段。
    bindings = SignalBindings(session, (definition,))
    # 无效原值/质量原样保留，不用0补齐。
    samples = tuple(SignalSample("signal_a", base + time, value, valid, quality,
                                bindings.source_ref("signal_a"), sequence)
                    for sequence, (time, value, valid, quality) in enumerate(observations))
    # 两后端共享构造门槛，保持查询分别独立实现。
    return SignalSeries(bindings, "signal_a", samples)


class StateTests(unittest.TestCase):
    """核对实际状态边界、原子组和只读数组布局。

    正常0、False与UNKNOWN分开；所有数值对齐对照使用真正独立参考函数。
    """

    def _compare(self, series, times, *, point=False):
        """逐值/掩码/原观测身份核对两个独立后端。

        参数: series为合成SignalSeries；times为tuple纳秒；point控制视图。
        返回: 参考tuple和AlignedArray，供手算断言复用。
        异常: 任一后端拒绝或结果不符由unittest报告。
        """
        # 参考内核不调用NumPy对齐，先独立算逻辑结果。
        reference = align_reference(series, times, point=point)
        # 数组存储和查询实际运行searchsorted/掩码。
        array = align_numpy(build_signal_array(series), np.array(times, dtype=np.int64), point=point)
        # 有效性和完整质量逐位置一致，不只比较正常值。
        self.assertEqual([item.valid for item in reference], array.valid.tolist())
        # 诊断保留原输入原因、过期及范围不足组合。
        self.assertEqual([int(item.quality) for item in reference], array.quality.tolist())
        # 纯定时器或EOF不伪造实际更新。
        self.assertEqual([item.actual_update for item in reference], array.actual_update.tolist())
        # 每位置的原样本身份也必须一致。
        for index, item in enumerate(reference):
            # -1表示没有历史，不能映射到最后样本。
            sample_index = int(array.sample_indices[index])
            # 没有逻辑历史时数组同样没有原引用。
            if item.sample is None:
                # 不能误用负索引。
                self.assertEqual(sample_index, -1)
            else:
                # 最新invalid同样能追溯真实原行。
                self.assertEqual(series.samples[sample_index], item.sample)
            # 仅valid位置的存储值可参加比较/统计。
            if item.valid:
                # enum数组编码显式回到相同标签域再比较逻辑值。
                value = array.history.labels[int(array.values[index])] if array.history.labels else array.values[index].item()
                # 正常0和False不能被当作无效。
                self.assertEqual(value, item.value)
        # 返回实际结果继续与手算真值核对。
        return reference, array

    def test_no_history_ttl_and_invalid_overwrite(self):
        """无历史/TTL到期/无效更新分别未知，旧值不能掩盖失效。

        参数: 无；0ns有效0，1ns无效None，4ns有效2，age=2ns。
        返回: None；两个后端与手算有效性/质量一致。
        异常: 回归失败由unittest报告。
        """
        # 最新无效更新须覆盖0ns有效值，即使旧TTL还未到期。
        series = _series(((0, 0, True, QualityFlag.NONE), (1, None, False, QualityFlag.DECODE_ERROR),
                          (4, 2, True, QualityFlag.NONE)), end=6)
        # 同时包含域外、实际更新、invalid、TTL和真实末端。
        reference, _ = self._compare(series, (-1, 0, 1, 2, 3, 4, 5, 6))
        # 正常0有效，invalid不是继续保持更早0。
        self.assertEqual([item.valid for item in reference], [False, True, False, False, False, True, True, False])
        # 最新invalid原值保留None及解码原因。
        self.assertIsNone(reference[2].value)
        # invalid自身过期后叠加STALE，不丢上游原因。
        self.assertEqual(reference[4].quality, QualityFlag.DECODE_ERROR | QualityFlag.STALE)
        # 无新报文仍在TTL=2触发失效。
        plain, _ = self._compare(_series(), (0, 1, 2, 3, 4), point=True)
        # TTL右端排除，不借point模式扩大。
        self.assertEqual([item.valid for item in plain], [True, True, False, False, False])

    def test_point_source_domain_and_actual_terminal_update(self):
        """来源/会话真实末点只在point视图使用，TTL始终排除。

        参数: 无；来源0—3ns、会话0—5ns，真实末更新3ns。
        返回: None；来源结束不随其他域延长，末点actual=True。
        异常: 手算不一致时断言失败。
        """
        # 创建明确真实末更新，age足够长。
        series = _series(((0, 1, True, QualityFlag.NONE), (3, 2, True, QualityFlag.NONE)), age=10)
        # 来源结束提前，不能借会话end=5保持到5。
        source = replace(series.source, observation_end_ns=3)
        # 当前新绑定保留更短真实观测范围。
        bindings = SignalBindings(replace(series.bindings.session, sources=(source,)), series.bindings.signals)
        # 原样本身份与时间不变，规范序列重新校验。
        series = SignalSeries(bindings, series.name, series.samples)
        # 两种视图使用同一原观测。
        continuous, _ = self._compare(series, (2, 3, 4))
        # point可用真实end观测，不增加continuous区间。
        points, _ = self._compare(series, (2, 3, 4), point=True)
        # 连续末端排除，来源之后缺失。
        self.assertEqual([item.valid for item in continuous], [True, False, False])
        # 点末端包含而来源之后仍无效。
        self.assertEqual([item.valid for item in points], [True, True, False])
        # end处实际新更新保留点事件证据。
        self.assertTrue(points[1].actual_update)
        # 与TTL恰好重合且没有新更新仍到期。
        expired, _ = self._compare(_series(age=3, end=3), (3,), point=True)
        # EOF不会自动清掉并列STALE诊断。
        self.assertEqual(expired[0].quality, QualityFlag.STALE)
        # 会话真实末点更新只影响点上下文。
        terminal = _series(((0, 1, True, QualityFlag.NONE), (5, 2, True, QualityFlag.NONE)), age=10)
        # 连续末点无输入，点上下文实际有效。
        self.assertFalse(self._compare(terminal, (5,))[0][0].valid)
        # 后续TEMP只在点视图生成边沿。
        self.assertTrue(self._compare(terminal, (5,), point=True)[0][0].valid)

    def test_unknown_end_no_fake_period_and_empty_queries(self):
        """未知source end按实际末行，不补周期；空历史/查询正常处理。

        参数: 无；仅0ns一条实际行且unknown end，已知会话end5ns。
        返回: None；continuous无区间，point仅0ns可用。
        异常: 断言失败由unittest报告。
        """
        # 来源未声明end不能用valid_for虚构观测覆盖。
        series = _series(age=10, known_end=False)
        # 单点没有可证明continuous持续时间。
        self.assertFalse(self._compare(series, (0,))[0][0].valid)
        # 真实点0仍存在，之后没有来源观测。
        self.assertEqual([item.valid for item in self._compare(series, (0, 1), point=True)[0]], [True, False])
        # 空查询不访问任何样本索引。
        self.assertEqual(self._compare(series, ())[0], ())
        # 绑定来源有原字段，但此序列无可用观测。
        empty = SignalSeries(series.bindings, series.name, ())
        # 空历史查询必须全部MISSING，不误取末元素。
        self.assertEqual([item.quality for item in self._compare(empty, (0, 1), point=True)[0]], [QualityFlag.MISSING] * 2)

    def test_same_time_conflicts_and_stable_sequence_policy(self):
        """默认不同值冲突失败，显式last_by_sequence稳定且保留计数。

        参数: 无；同一0ns两条不同原值和序号。
        返回: None；默认拒绝，显式取原序号1/值2。
        异常: 错误政策行为由unittest报告。
        """
        # 不同值是冲突，不是同时间重复帧去重授权。
        observations = ((0, 1, True, QualityFlag.NONE), (0, 2, True, QualityFlag.NONE))
        # 默认不能按遍历顺序选择。
        with self.assertRaisesRegex(ValueError, "同信号同时间冲突"):
            # 实际构造门槛拒绝。
            _series(observations)
        # 显式政策允许按稳定原序号选最后项。
        series = _series(observations, same_time_policy="last_by_sequence")
        # 两条候选只规范成一条实际观测，记录覆盖数量。
        self.assertEqual((series.samples[0].value, series.samples[0].sequence, series.conflict_count), (2, 1, 1))
        # 两后端使用同一合法原提交，不丢失选择身份。
        self._compare(series, (0, 1, 2))
        # 反转同时间候选遍历顺序仍按sequence选择。
        reversed_series = SignalSeries(series.bindings, series.name,
                                      tuple(SignalSample(series.name, 0, value, True, QualityFlag.NONE,
                                                         series.bindings.source_ref(series.name), sequence)
                                            for sequence, value in ((1, 2), (0, 1))))
        # 稳定原序号结果不依遍历顺序。
        self.assertEqual(reversed_series.samples, series.samples)

    def test_atomic_updates_cross_every_batch_split(self):
        """T04两列同时更新不会产生瞬时真值，跨batch不提前提交。

        参数: 无；0ns V400/I0，1ns V0/I10，已规范化int64列。
        返回: None；所有batch_rows返回两次完整组，组后乘积均0。
        异常: 任一切批不一致时断言失败。
        """
        # 原行两个字段同步出现，来源保留原顺序。
        clock = TimebaseSpec("clock", TimeType.RELATIVE, "atomic-v1")
        # 真实0/1ns各两列，不能在列间求值。
        rows = (MemoryRow(0, {"v": 400, "i": 0}, 0), MemoryRow(1, {"v": 0, "i": 10}, 1))
        # 来源/域end2ns明确，与真实末行区别保存。
        source = SourceSpec("sensor", clock, rows, observation_start_ns=0, observation_end_ns=2)
        # 同一会话和两别名是一个原子计划。
        session = SessionSpec("session_a", clock, 0, 2, (source,))
        # STATE只检查规范值，不执行V*A单位表达式。
        definitions = tuple(SignalDefinition(name, "sensor", name, SignalDType.INT64, "1", 10) for name in ("v", "i"))
        # 两列共享同一冻结绑定。
        bindings = SignalBindings(session, definitions)
        # 每列独立异步存储，驱动器归并形成原子组。
        series = tuple(SignalSeries(bindings, name, tuple(SignalSample(name, row.time_ns, row.values[name], True,
                           QualityFlag.NONE, bindings.source_ref(name), row.sequence) for row in rows)) for name in ("v", "i"))
        # 全部切法都保持时间组完整，结果不因批大小改变。
        baseline = tuple(iter_time_groups(series, 64))
        # 每组两列同时存在，求值两次。
        self.assertEqual([(item.time_ns, len(item.updates)) for item in baseline], [(0, 2), (1, 2)])
        # 手算组后乘积，不比较未提交中间状态。
        self.assertEqual([item.updates[0].value * item.updates[1].value for item in baseline], [0, 0])
        # 1行批必然把同时间两列拆开，仍与大批一致。
        for batch_rows in (1, 2, 3, 5, 64):
            # 实际批处理入口，不模拟最终组列表。
            self.assertEqual(tuple(iter_time_groups(series, batch_rows)), baseline)
        # 直接缓冲第一条0ns更新不得提前产出组。
        buffer = AtomicUpdateBuffer(bindings)
        # pending跨batch保留。
        self.assertEqual(buffer.push((series[0].samples[0],)), ())
        # 同时刻另一列进入仍无更大时间证明完成。
        self.assertEqual(buffer.push((series[1].samples[0],)), ())
        # 真正EOF提交这一完整同时间组。
        self.assertEqual(len(buffer.finish()[0].updates), 2)
        # finish不能作为普通batch reset后继续使用。
        with self.assertRaises(ValueError):
            # 防止跨会话继承状态。
            buffer.push(())

    def test_timeline_includes_ttl_and_local_boundaries(self):
        """无新报文时TTL仍在共同轴，附加deadline不改原更新身份。

        参数: 无；0/4ns更新、age2ns、source/domain end6ns。
        返回: None；共同轴含0/2/3/4/6且2ns不是实际更新。
        异常: 手算轴不一致时断言失败。
        """
        # 两段保持之间TTL=2必须形成边界。
        series = _series(((0, 1, True, QualityFlag.NONE), (4, 2, True, QualityFlag.NONE)), end=6)
        # 额外3ns模拟后续规则deadline，域外边界排除。
        axis = common_timeline((series,), (3, 100))
        # 预期由手算明确，不从被测对齐结果生成。
        self.assertEqual(axis, (0, 2, 3, 4, 6))
        # 2ns仅计时失效，不是真报文。
        self.assertFalse(self._compare(series, axis)[0][1].actual_update)

    def test_large_time_ns_and_int64_extreme_without_float_cast(self):
        """2**53附近1ns与int64末端保持精确，不先转绝对float秒。

        参数: 无；大绝对时间、合法短会话和超会话查询。
        返回: None；age1边界与手算一致，末端TTL不溢出或扩展。
        异常: 两后端不一致时断言失败。
        """
        # 三种绝对坐标覆盖浮点失精及有符号两端。
        for base in (2 ** 53, -(2 ** 63), 2 ** 63 - 5):
            # 域跨度4ns始终合法，TTL=1精确。
            series = _series(age=1, end=4, base=base)
            # query时间不先经float。
            reference, _ = self._compare(series, (base, base + 1, base + 4), point=True)
            # 初点有效，精确到期及之后无效。
            self.assertEqual([item.valid for item in reference], [True, False, False])
            # TTL边界进入轴，超过域end的计时不添加。
            self.assertEqual(common_timeline((series,)), (base, base + 1, base + 4))

    def test_layout_dtypes_enum_bool_and_ownership(self):
        """整数不提升float，enum/bool独立存储，列只读且原诊断保留。

        参数: 无；int64/uint64端点、False、enum标签及invalid None。
        返回: None；dtype/掩码与元数据符合声明，输入不原地改变。
        异常: 所有权或布局不符时断言失败。
        """
        # 混合类型分别存列，不能拼成统一float宽表。
        cases = ((SignalDType.INT64, 2 ** 63 - 1, (), "int64"), (SignalDType.UINT64, 2 ** 64 - 1, (), "uint64"),
                 (SignalDType.FLOAT64, 0.0, (), "float64"), (SignalDType.BOOL, False, (), "bool"),
                 (SignalDType.ENUM, "scope", ((0, "off"), (1, "scope")), "int64"))
        # 每种列独立检查实际存储和逻辑对照。
        for dtype, value, choices, storage_dtype in cases:
            # 原生dtype值已经规范化，STATE不做隐藏cast。
            series = _series(((0, value, True, QualityFlag.NONE), (1, None, False, QualityFlag.MISSING)),
                             dtype=dtype, choices=choices)
            # 两后端同输入输出值和quality一致。
            _, aligned = self._compare(series, (0, 1, 2), point=True)
            # 固定整数和enum编码不丢位。
            self.assertEqual(str(aligned.values.dtype), storage_dtype)
            # 质量列至少16位承载最高标志。
            self.assertEqual(str(aligned.quality.dtype), "uint16")
            # 原无效诊断不被数值存储0占位覆盖。
            self.assertIsNone(aligned.history.series.samples[1].value)
            # 输出所有权只读约定阻止普通原地污染。
            with self.assertRaises(ValueError):
                # 修改结果列必须显式新分配。
                aligned.values[0] = 7
        # 调用者查询轴不被原地修改，结果使用独立副本。
        axis = np.array([0, 1], dtype=np.int64)
        # 新对齐结果独立持有自己的轴。
        aligned = align_numpy(build_signal_array(_series()), axis)
        # 调用者继续编辑自己输入，不影响已得结果。
        axis[0] = -1
        # 保存原查询事实。
        self.assertEqual(aligned.times_ns.tolist(), [0, 1])
        # 原调用者数组writeable保持不变。
        self.assertTrue(axis.flags.writeable)

    def test_bad_structure_identity_and_axes_rejected(self):
        """字段/原序号/时刻伪造、时间回退和错误数组布局执行前拒绝。

        参数: 无；合法序列的各类错误替换。
        返回: None；保持严格校验，不以排序/cast修补。
        异常: 预期拒绝缺失时断言失败。
        """
        # 基线包含两个真实原行。
        series = _series(((0, 1, True, QualityFlag.NONE), (1, 2, True, QualityFlag.NONE)))
        # 负例不应被当作正常新来源观测。
        for samples in ((series.samples[1], series.samples[0]), (replace(series.samples[0], sequence=99),),
                        (replace(series.samples[0], time_ns=1),), (series.samples[0], series.samples[0]),
                        (replace(series.samples[0], source_ref=SourceRef("session_a", "source_a", "missing")),)):
            # 原序列入口证明实际原行身份。
            with self.assertRaises(ValueError):
                # 不修补负例。
                SignalSeries(series.bindings, series.name, samples)
        # 数组查询不接受float/二维/带mask/回退时间轴。
        for axis in (np.array([0.0]), np.array([[0]], dtype=np.int64), np.array([1, 0], dtype=np.int64),
                     np.ma.array([0], dtype=np.int64, mask=False)):
            # 错误结构拒绝，不隐式改变输入。
            with self.assertRaises((TypeError, ValueError)):
                # 真数组入口校验完整时间列。
                align_numpy(build_signal_array(series), axis)
        # 参考同样拒绝时间回退。
        with self.assertRaises(ValueError):
            # 不以排序掩盖时间推进错误。
            align_reference(series, (1, 0))
        # 原array的有效值不能被另一列冒充。
        history = build_signal_array(series)
        # 构造门槛关联逻辑原观测。
        with self.assertRaises(ValueError):
            # dtype正确也不能证明数值来自这个信号。
            SignalArray(series, history.times_ns, np.array([9, 9], dtype=np.int64), history.valid, history.quality)

    def test_fixed_seed_independent_differential(self):
        """固定种子100组不规则时间/invalid/TTL同输入独立对照。

        参数: 无；种子20261008，1—12样本、0—80ns域、TTL1—10ns。
        返回: None；连续和点视图逐值/质量/来源身份均一致。
        异常: 任一差异由unittest定位种子与组号。
        """
        # 固定种子只属本测试，不污染全局随机状态。
        randomizer = random.Random(20261008)
        # 规模只用于边界一致性，不声称性能测量。
        for case in range(100):
            # 唯一非递减真实原时刻，故不借排序修补来源。
            times = sorted(randomizer.sample(range(70), randomizer.randint(1, 12)))
            # 全部观测明确给出，包括invalid覆盖。
            observations = tuple((time, randomizer.randint(-7, 7), True, QualityFlag.NONE)
                                 if randomizer.choice((True, False)) else (time, None, False, QualityFlag.NONFINITE)
                                 for time in times)
            # TTL和已知观测end均声明合成参数。
            series = _series(observations, age=randomizer.randint(1, 10), end=80)
            # 域外两端和每ns查询捕捉精确边界。
            queries = tuple(range(-2, 83))
            # 两模式分别核对，不把point关闭边界套入连续。
            for point in (False, True):
                # 失败报告可复现组号及模式。
                with self.subTest(case=case, point=point):
                    # 参考内核独立，实际数组运行掩码。
                    self._compare(series, queries, point=point)


# 直接执行才启动测试，不在import时创建运行会话。
if __name__ == "__main__":
    # 标准框架报告失败，不吞异常。
    unittest.main()
