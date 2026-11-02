"""检查条件持续多久才确认活动，以及真实更新、末点和切批怎样影响事件。

输入为手算区间或明确原行、有效期及来源范围；输出为unittest断言。
参考与NumPy从同一输入独立执行，逐字段比较Event和ConditionTick，再
用手算核对开始、确认、结束及原因。持续活动和边沿点事件分开，真实末点
仍参加点判断；批次切分不能丢候选状态，会话切换不能把两段时长拼接。
对应T05—T12、T46—T48及因果、隔离、定宽时间边界；不读取真实业务日志。
"""

# 当前合成冻结声明的局部变更，不修改已有输入。
from dataclasses import replace
# 可重复生成额外边界序列，真值仍有手算基线。
import random
# 实际验收失败不会被吞掉。
import unittest
# NumPy仅用于被测数组后端/明确int64查询。
import numpy as np
# 原字段/会话/类型模型，不依赖具体业务。
from chronaxis.core import (MemoryRow, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType as D, SourceSpec, TimebaseSpec, TimeType)
# 真实受限编译，不用eval或伪条件替代实际接线。
from chronaxis.core.expression import compile_expression
# 参考/数组分别归一化实际原行。
from chronaxis.core.numeric import memory_series_reference
# 参考保持负责更新前点的独立真值。
from chronaxis.core.state import align_reference
# 数组布局与独立保持，不借标量输出作输入。
from chronaxis.core.state_numpy import build_signal_array, align_numpy
# 当前typed规则/证据，明确EOF不是FALSE。
from chronaxis.core.temporal import (ConditionSpan, ConditionTick, ConditionTimeline,
                                     TemporalRule, timeline_from_spans)
# 两个独立检测内核与跨批状态对象。
from chronaxis.core.temporal_reference import ReferenceTemporalDetector, detect_reference
# 实际NumPy run与edge计算。
from chronaxis.core.temporal_numpy import NumpyTemporalDetector, detect_numpy
# 从原行到事件的完整参考链，不调用NumPy。
from chronaxis.core.temporal_memory_reference import build_timeline_reference, detect_memory_reference
# 从原行到事件的完整实际数组链。
from chronaxis.core.temporal_memory_numpy import build_timeline_numpy, detect_memory_numpy
# UNKNOWN与False及所有原因严格区分。
from chronaxis.core.types import QualityFlag as Q, Truth as T


def _rule(kind='condition_duration', duration=0, *, initial=False):
    """建立单会话规则，不在各后端共享可变状态。

    参数: kind支持duration/rising/falling；duration ns；initial明确bool。
    返回: 冻结TemporalRule，scope完整可追溯。
    异常: 当前规则校验错误传播。
    """
    # 不用秒数文件名或全局变量充当身份。
    return TemporalRule('rule', 'dataset', 'session', kind, duration, initial)


def _memory(rows, *, end=5, age=10, second_age=10, expression='x'):
    """构造明确范围/时钟的原行布尔信号及实际编译计划。

    参数: rows为(time_ns, 原字典)序列；end/age/second_age明确ns；expression合法DSL。
    返回: CompiledExpression，空原行仍保留明示来源域。
    异常: 模型/绑定/语法错误传播，不补假值或周期。
    """
    # 相对起点为明确合成身份，不能外推真实同步。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'temporal-synthetic-v1')
    # sequence来自原顺序，不重新排序。
    source = SourceSpec('sensor', clock, tuple(MemoryRow(time, values, index) for index, (time, values) in enumerate(rows)),
                        observation_start_ns=0, observation_end_ns=end)
    # 全部范围明确，EOF包含真实末点但不增加面积。
    session = SessionSpec('session', clock, 0, end, (source,))
    # 只声明实际原字段，不能编造不存在y的绑定。
    fields = {name for _, values in rows for name in values}
    # 普通信号不需领域语义，类型/TTL明确，不放宽产品字段检查。
    signals = tuple(SignalDefinition(name, 'sensor', name, D.BOOL, '1', ttl)
                    for name, ttl in (('x', age), ('y', second_age)) if name in fields)
    # 编译真正受限表达式与当前绑定身份。
    return compile_expression(expression, SignalBindings(session, signals))


def _facts(events):
    """投影可独立手算的活动或点边界。

    参数: events实际Event序列。
    返回: (start,confirmed,end,status)列表，ns不转float。
    异常: 无主动异常，不作为完整差分比较替代。
    """
    # 完整ID/原因/来源由其他断言比较，手算只关注事实。
    return [(event.start_ns, event.confirmed_ns, event.end_ns, event.status) for event in events]


class TemporalTests(unittest.TestCase):
    """以固定真值与独立双链对照验证时间契约。

    无会话间共享候选；真实terminal/空batch/同刻原子组分别验证。
    """

    def _compare(self, rule, timeline):
        """检查合法不同完整组切批的全部Event完全相同。

        参数: rule当前规则，timeline完整ConditionTimeline。
        返回: 参考完整Event tuple，供额外手算检查。
        异常: 不同ID/原因/来源/边界由unittest报告。
        """
        # 一次完整独立参考为稳定切批比较对象。
        expected = detect_reference(rule, timeline)
        # 小批穿过每个pending/active/EOF边界，普通尾不收尾。
        for size in (1, 2, 7, 65536):
            # 两内核各自执行完整数据，不复用结果。
            self.assertEqual(expected, detect_reference(rule, timeline, batch_rows=size))
            # NumPy检测数值使用实际run/edge掩码。
            self.assertEqual(expected, detect_numpy(rule, timeline, batch_rows=size))
        # 未确认候选不会变最终事件。
        return expected

    def _memory_compare(self, compiled, rule):
        """从实际原行独立构造两个轴并检测完整事件。

        参数: compiled当前原行绑定的BOOL计划，rule匹配当前会话。
        返回: 参考timeline及Event tuple，供手算/因果字段检查。
        异常: 任一证据/结果差异由unittest报告。
        """
        # 原行归一化、保持、表达式、deadline都独立计算。
        reference = build_timeline_reference(compiled, rule)
        # 比较全部point/continuous/actual_unknown/来源，而非仅事件数。
        self.assertEqual(reference, build_timeline_numpy(compiled, rule))
        # 两detector与切批完整事实一致。
        events = self._compare(rule, reference)
        # 全链入口不能只有模型声明或调用参考作NumPy后端。
        self.assertEqual(events, detect_memory_reference(compiled, rule, batch_rows=2))
        # 独立数组从原行重新执行，不喂参考输出。
        self.assertEqual(events, detect_memory_numpy(compiled, rule, batch_rows=1))
        # 保留证据供进一步手算断言。
        return reference, events

    def test_t05_t07_t10_duration_hand_truth(self):
        """恰等门槛先确认，未知打断候选，EOF截断已确认活动。

        参数: 无；设计T05—T07/T10明确半开区间。
        返回: None。
        异常: 完整差分或手算事实失败由unittest报告。
        """
        # 同组FALSE不能抹掉之前恰好3ns的已观测时长。
        cases = [((ConditionSpan(0, 3, T.TRUE), ConditionSpan(3, 4, T.FALSE)), [(0, 3, 3, 'closed')]),
                 ((ConditionSpan(0, 2, T.TRUE), ConditionSpan(2, 4, T.UNKNOWN, Q.MISSING)), []),
                 ((ConditionSpan(0, 2, T.TRUE), ConditionSpan(2, 3, T.UNKNOWN, Q.MISSING), ConditionSpan(3, 6, T.TRUE), ConditionSpan(6, 7, T.FALSE)), [(3, 6, 6, 'closed')]),
                 ((ConditionSpan(0, 5, T.TRUE),), [(0, 3, 5, 'truncated')])]
        # 每输入包含独立预期，不能只双后端互相确认。
        for spans, expected in cases:
            # typed区间真实边界不填平UNKNOWN。
            events = self._compare(_rule(duration=3), timeline_from_spans(spans))
            # onset/confirm/end分别手算。
            self.assertEqual(_facts(events), expected)

    def test_t08_t09_t47_ttl_and_eof(self):
        """真实TTL定时失效与EOF同刻优先级按设计处理。

        参数: 无；t0 TRUE，真实域与TTL明确，无后续新样本。
        返回: None。
        异常: UNKNOWN/状态/诊断/门槛差异由unittest报告。
        """
        # TTL2早于EOF5，门槛3不够，门槛2恰等必须确认并中断。
        compiled = _memory(((0, {'x': True}),), age=2)
        # 超门槛不把失效区间当FALSE或TRUE累计。
        _, events = self._memory_compare(compiled, _rule(duration=3))
        # T08没有确认事实。
        self.assertEqual(events, ())

        # T09先结算2ns，之后TTL中断。
        _, events = self._memory_compare(compiled, _rule(duration=2))
        # 确认和结束同刻仍为正长度真实活动。
        self.assertEqual(_facts(events), [(0, 2, 2, 'interrupted')])
        # 原因保持STALE，不用默认MISSING掩盖。
        self.assertTrue(events[0].quality & Q.STALE)
        # TTL恰同EOF，无实际结束，truncated并保留STALE。
        _, events = self._memory_compare(_memory(((0, {'x': True}),), end=3, age=3), _rule(duration=3))
        # T47精确状态优先级。
        self.assertEqual(_facts(events), [(0, 3, 3, 'truncated')])
        # 同刻TTL仍可审计。
        self.assertTrue(events[0].dependency_quality & Q.STALE)
        # 同EOF真实invalid更新优先interrupted。
        timeline, events = self._memory_compare(_memory(((0, {'x': True}), (3, {'x': None})), end=3, age=3), _rule(duration=3))
        # 真实原因与纯TTL不混为一类。
        self.assertEqual(events[0].status, 'interrupted')
        # 显式实际未知证据，而非根据任意更新猜因果。
        self.assertTrue(timeline.ticks[-1].actual_unknown)

    def test_source_eof_isolation_and_two_activities(self):
        """来源提前结束仅影响依赖规则，FALSE/UNKNOWN缺口保留真实活动。

        参数: 无；两个相同明示时钟来源及两个真实TRUE区间。
        返回: None。
        异常: 来源范围或活动事实合并错误由unittest报告。
        """
        # 相同明确原点是合成同步依据，不凭offset猜同步。
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'temporal-source-v1')
        # a仅观测到2，不能借b更长范围延长a。
        a = SourceSpec('a', clock, (MemoryRow(0, {'raw': True}, 0),), observation_start_ns=0, observation_end_ns=2)
        # b观测到5，另一个独立规则继续。
        b = SourceSpec('b', clock, (MemoryRow(0, {'raw': True}, 0),), observation_start_ns=0, observation_end_ns=5)
        # 会话域完整，但每信号仍受来源范围约束。
        session = SessionSpec('session', clock, 0, 5, (a, b))
        # 两别名相同BOOL政策，来源域各自独立。
        bindings = SignalBindings(session, (SignalDefinition('x', 'a', 'raw', D.BOOL, '1', 10), SignalDefinition('y', 'b', 'raw', D.BOOL, '1', 10)))
        # 同时检查提前截断、长源继续、逻辑独立决定。
        for expression, end in (('x', 2), ('y', 5), ('x or y', 5)):
            # 真正编译当前别名绑定。
            _, events = self._memory_compare(compile_expression(expression, bindings), _rule(duration=1))
            # source EOF不影响能由y独立决定的TRUE逻辑。
            self.assertEqual(_facts(events), [(0, 1, end, 'truncated')])
        # D19两段TRUE必须保留两Event，片段合并留M2。
        spans = (ConditionSpan(0, 2, T.TRUE), ConditionSpan(2, 3, T.FALSE), ConditionSpan(3, 5, T.TRUE), ConditionSpan(5, 6, T.FALSE))
        # 完整分段真值，不能改中间FALSE为TRUE。
        events = self._compare(_rule(duration=1), timeline_from_spans(spans))
        # 两个真实活动边界和确认分别保留。
        self.assertEqual(_facts(events), [(0, 1, 2, 'closed'), (3, 4, 5, 'closed')])
        # UNKNOWN缺口也不得跨越累积/合并。
        unknown = (spans[0], replace(spans[1], state=T.UNKNOWN, quality=Q.MISSING), spans[2], spans[3])
        # UNKNOWN只改变第一段结束原因，不合并数量。
        events = self._compare(_rule(duration=1), timeline_from_spans(unknown))
        # 第二段完全新候选。
        self.assertEqual(_facts(events), [(0, 1, 2, 'interrupted'), (3, 4, 5, 'closed')])

    def test_batch_lifecycle_deadline_and_identity(self):
        """空批无reset，未EOF不能finish；候选/身份按会话隔离。

        参数: 无；有额外TRUE时刻证据的完整[0,5]轴。
        返回: None。
        异常: 生命周期负例由assertRaises检查，差分由unittest报告。
        """
        # 固定合成TRUE轴穿过deadline，EOF连续UNKNOWN/点TRUE。
        timeline = ConditionTimeline(0, 5, (ConditionTick(0, T.TRUE), ConditionTick(1, T.TRUE, actual_update=False),
                                           ConditionTick(3, T.TRUE, actual_update=False),
                                           ConditionTick(5, T.UNKNOWN, Q.MISSING, False, True, True, T.TRUE, Q.NONE)))
        # 两个真实状态实现独立创建和验证。
        for detector_type in (ReferenceTemporalDetector, NumpyTemporalDetector):
            # 单会话候选保持跨批，禁止全局缓存。
            detector = detector_type(_rule(duration=3), 0, 5)
            # 未真正terminal不能收尾。
            with self.assertRaises(ValueError):
                # 普通batch尾不能变EOF。
                detector.finish()
            # 首个TRUE还只是pending。
            self.assertEqual(detector.push(timeline.ticks[:1]), ())
            # next_deadline是真3ns，非下一条样本1ns。
            self.assertEqual(detector.next_deadline_ns, 3)
            # 空批不得丢候选或锁存。
            self.assertEqual(detector.push(()), ())
            # 普通TRUE更新不重设onset。
            detector.push(timeline.ticks[1:3])
            # 精确timer确认后不重复安排确认。
            self.assertEqual(detector.confirmed, 3)
            # 已确认无需新duration deadline。
            self.assertIsNone(detector.next_deadline_ns)
            # 真实terminal后才完成final事件。
            detector.push(timeline.ticks[3:])
            # 与完整独立参考包括ID完全相同。
            self.assertEqual(detector.finish(), detect_reference(_rule(duration=3), timeline))
            # finish后不能复用新session。
            with self.assertRaises(ValueError):
                # 即便空批也不能继续已关闭实例。
                detector.push(())
        # 稳定ID不包含切批行数或metadata声明。
        baseline = self._compare(_rule(duration=3), timeline)
        # rule/session/dataset是可检查身份组成，不仅秒数。
        for changed in (replace(_rule(duration=3), rule_id='other'), replace(_rule(duration=3), session_id='other'), replace(_rule(duration=3), dataset_id='other')):
            # 新规则独立状态且ID明确隔离。
            self.assertNotEqual(baseline[0].event_id, self._compare(changed, timeline)[0].event_id)
        # 相同物理输入可选semantic_id不改变事件事实ID。
        compiled = _memory(((0, {'x': True}),))
        # 当前来源/别名不改变，只增加optional领域声明。
        bindings = replace(compiled.bindings, signals=(replace(compiled.bindings.signals[0], semantic_id='custom.flag'),))
        # 名称声明不是新的物理事件。
        self.assertEqual(detect_memory_reference(compiled, _rule(duration=1)), detect_memory_numpy(compile_expression('x', bindings), _rule(duration=1)))

    def test_strict_before_and_int64_boundaries(self):
        """更新前点不减1ns，极值时间与超域deadline不wrap。

        参数: 无；int64最小/最大附近真实时间点，跨度均可表示。
        返回: None。
        异常: 溢出/错误输入负例或手算事实失败由unittest报告。
        """
        # 最小int64上不能通过t-1实现更新前点。
        start = -(2 ** 63)
        # 只构造合法短域，避免跨全int64跨度。
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'temporal-extreme-v1')
        # 起点真实TRUE和起点+1真实FALSE。
        source = SourceSpec('sensor', clock, (MemoryRow(start, {'x': True}, 0), MemoryRow(start+1, {'x': False}, 1)),
                            observation_start_ns=start, observation_end_ns=start+3)
        # 定宽坐标与短跨度均已证明。
        bindings = SignalBindings(SessionSpec('session', clock, start, start+3, (source,)), (SignalDefinition('x', 'sensor', 'x', D.BOOL, '1', 2),))
        # 参考原行规范化仍精确保持极值ns。
        series = memory_series_reference(bindings, 'x')
        # strict_before在当前t检查TTL，cursor严格小于t。
        ref = align_reference(series, (start, start+1), point=True, strict_before=True)
        # 数组searchsorted左侧，不计算t-1。
        out = align_numpy(build_signal_array(series), np.array([start, start+1], dtype=np.int64), point=True, strict_before=True)
        # 首点无历史，第二点旧TRUE而非新FALSE。
        self.assertEqual([(x.valid, x.value if x.valid else None) for x in ref], [(False, None), (True, True)])
        # 两后端均无actual，旧样本不是当前真实更新。
        self.assertEqual(out.valid.tolist(), [False, True])
        # 同步检查原因完整对应。
        self.assertEqual(out.quality.tolist(), [int(x.quality) for x in ref])
        # 极值起点完整duration1闭合，不浮点混淆相邻ns。
        _, events = self._memory_compare(compile_expression('x', bindings), _rule(duration=1))
        # 确认/结束完全精确。
        self.assertEqual(_facts(events), [(start, start+1, start+1, 'closed')])
        # 正极值靠近末端仍精确，门槛超域不能wrap确认。
        start = 2 ** 63 - 5
        # Explicit span是手算证据，不依赖真实来源。
        timeline = timeline_from_spans((ConditionSpan(start, start+4, T.TRUE),))
        # 超域门槛绝不产生错误的负时间活动。
        self.assertEqual(self._compare(_rule(duration=2 ** 63-1), timeline), ())
        # 可达门槛仍在真正正极值附近确认。
        events = self._compare(_rule(duration=3), timeline)
        # 绝对坐标不经float转换。
        self.assertEqual(_facts(events), [(start, start+3, start+4, 'truncated')])
        # strict_before输入也要真bool，不以1代替声明。
        with self.assertRaises(TypeError):
            # 两视图协议参数保持严格。
            align_reference(series, (), strict_before=1)

    def test_random_complete_truth_and_batch_consistency(self):
        """固定种子三值区间、末点实际更新在两独立内核与切批下一致。

        参数: 无；64组短可检查合成轴，三规则/初始化/门槛边界。
        返回: None。
        异常: 全字段差分由unittest报告；手算真值在前述用例独立覆盖。
        """
        # 固定随机身份便于复现，不把随机差分当唯一真值。
        rng = random.Random(104607)
        # 覆盖多run/UNKNOWN与终点真实更新组合，不凑重复样本数量。
        for index in range(64):
            # 同组单调正区间明确，长度1至4ns。
            spans, time = [], 0
            # 不同batch可能切在pending、deadline前后或EOF。
            for _ in range(rng.randint(1, 12)):
                # 真/假/未知随机，但quality严格对应。
                truth = rng.choice((T.TRUE, T.FALSE, T.UNKNOWN))
                # 完整覆盖域，缺口用明确UNKNOWN表达。
                end = time + rng.randint(1, 4)
                # 原质量原因不同组合仍须完整差分。
                spans.append(ConditionSpan(time, end, truth, rng.choice((Q.MISSING, Q.STALE, Q.DECODE_ERROR)) if truth is T.UNKNOWN else Q.NONE))
                # 下一span紧接，禁止未观测空隙。
                time = end
            # 半数真实末点更新，其他只是EOF历史point。
            actual = bool(index % 2)
            # 真实末点可knownFalse/knownTrue/invalid。
            point = rng.choice((T.TRUE, T.FALSE, T.UNKNOWN)) if actual else None
            # 真实invalid有明确MISSING原因。
            timeline = timeline_from_spans(tuple(spans), terminal_state=point, terminal_quality=Q.MISSING if point is T.UNKNOWN else Q.NONE, terminal_actual=actual)
            # 三种检测都有独立数组实现与稳定批次身份。
            for rule in (_rule(duration=rng.randint(0, 8)), _rule('rising_edge', initial=bool(index % 3)), _rule('falling_edge')):
                # 同一输入完整比较ID/质量/事实，不只数量。
                self._compare(rule, timeline)

    def test_invalid_models_zero_domain_and_scope(self):
        """不完整域/回退/错误scope拒绝，零域仅真实点不持续。

        参数: 无；typed负例及零长度会话末点。
        返回: None。
        异常: 预期配置失败由assertRaises核对。
        """
        # UNKNOWN无原因不能进入核心。
        with self.assertRaises(ValueError):
            # 非零quality与UNKNOWN必须对应。
            ConditionTick(0, T.UNKNOWN)
        # bool不是Truth模型。
        with self.assertRaises(TypeError):
            # 不允许隐式bool替代三值。
            ConditionSpan(0, 1, True)
        # terminal必须真实域end，不允许普通batch尾。
        with self.assertRaises(ValueError):
            # 漏terminal的完整轴不合法。
            ConditionTimeline(0, 1, (ConditionTick(0, T.TRUE), ConditionTick(1, T.TRUE)))
        # 明确零domain只保留真实point证据，无活动。
        timeline = ConditionTimeline(0, 0, (ConditionTick(0, T.UNKNOWN, Q.MISSING, True, True, True, T.TRUE, Q.NONE),))
        # duration0也不能建立零长度activity。
        self.assertEqual(self._compare(_rule(duration=0), timeline), ())
        # 显式initial允许真实零域末点TRUE。
        self.assertEqual(_facts(self._compare(_rule('rising_edge', initial=True), timeline)), [(0, 0, None, 'point')])
        # 规则不能继承其他会话绑定。
        with self.assertRaises(ValueError):
            # 当前真实输入不是跨会话共享全局context。
            build_timeline_reference(_memory(((0, {'x': True}),)), replace(_rule(), session_id='other'))
        # 完整时间组重复/回退不能被sort修正。
        for kind in (ReferenceTemporalDetector, NumpyTemporalDetector):
            # 独立会话状态，用相同非法输入验证协议。
            detector = kind(_rule(), 0, 2)
            # 首组真实TRUE合法。
            detector.push((ConditionTick(0, T.TRUE),))
            # 同刻重复完整组必须拒绝。
            with self.assertRaises(ValueError):
                # 同时间原字段由上游AtomicUpdateBuffer统一处理。
                detector.push((ConditionTick(0, T.FALSE),))

    def test_t46_t48_terminal_points(self):
        """真实末点FALSE闭合与falling；末点TRUE仅rising不新建活动。

        参数: 无；domain E=3的真实原行更新。
        返回: None。
        异常: duration/point事实或连续边界错误由unittest报告。
        """
        # T46实际FALSE发生在E，同刻deadline先确认。
        compiled = _memory(((0, {'x': True}), (3, {'x': False})), end=3)
        # 真实closed优先EOF。
        _, events = self._memory_compare(compiled, _rule(duration=3))
        # onset不改为确认，活动仍完整[0,3)。
        self.assertEqual(_facts(events), [(0, 3, 3, 'closed')])
        # 终点真实falling必须保留point。
        _, events = self._memory_compare(compiled, _rule('falling_edge'))
        # point无end，不制造零长度区间或增加面积。
        self.assertEqual(_facts(events), [(3, 3, None, 'point')])
        # T48最后TRUE真实可观察，但domain后不能有活动。
        compiled = _memory(((0, {'x': False}), (3, {'x': True})), end=3)
        # 已知FALSE→TRUE真实末点产生rising。
        timeline, events = self._memory_compare(compiled, _rule('rising_edge'))
        # 独立point事实。
        self.assertEqual(_facts(events), [(3, 3, None, 'point')])
        # 连续与点必须分开，不修改半开范围。
        self.assertEqual((timeline.ticks[-1].state, timeline.ticks[-1].point_state), (T.UNKNOWN, T.TRUE))
        # 即便d0，terminal TRUE也不能新建activity。
        _, events = self._memory_compare(compiled, _rule(duration=0))
        # 非终点一直FALSE，选择持续活动为空。
        self.assertEqual(events, ())

    def test_t11_t12_edges_unknown_initial_and_timers(self):
        """初始化显式开启，UNKNOWN恢复非默认rising且不伪造falling。

        参数: 无；真实原行未知/真/假与无报文timer。
        返回: None。
        异常: 边沿与初始化策略错误由unittest报告。
        """
        # 第一次known TRUE只在明确初始化策略下输出。
        compiled = _memory(((0, {'x': None}), (1, {'x': True}), (2, {'x': None}), (3, {'x': True})))
        # 普通U→T不构成rising。
        _, events = self._memory_compare(compiled, _rule('rising_edge'))
        # 无已知FALSE之前不能凭空rising。
        self.assertEqual(events, ())
        # 显式初始化只第一次known TRUE，后续恢复不重复initial。
        _, events = self._memory_compare(compiled, _rule('rising_edge', initial=True))
        # 1ns初始化点，3ns不是第二初始化。
        self.assertEqual(_facts(events), [(1, 1, None, 'point')])
        # 输出初始化类型可追溯。
        self.assertEqual(events[0].trigger_kind, 'initial')
        # 已知F→T真实rising；T→U/U→F均非已知falling。
        compiled = _memory(((0, {'x': False}), (1, {'x': True}), (2, {'x': None}), (3, {'x': False})))
        # 第一次真正rising保留。
        _, events = self._memory_compare(compiled, _rule('rising_edge'))
        # 无未知恢复假rising。
        self.assertEqual(_facts(events), [(1, 1, None, 'point')])
        # UNKNOWN不能普遍当False制造falling。
        _, events = self._memory_compare(compiled, _rule('falling_edge'))
        # 无已知T→F。
        self.assertEqual(events, ())
        # TTL只使未知，不是实际FALSE更新。
        _, events = self._memory_compare(_memory(((0, {'x': True}),), age=2), _rule('falling_edge'))
        # 纯TTL/EOF都不得有边沿。
        self.assertEqual(events, ())

    def test_deadline_without_update_and_refresh_at_ttl(self):
        """无新报文精确deadline入轴，同TTL新样本覆盖旧到期。

        参数: 无；真实[0,5]域/TTL与更新时刻。
        返回: None。
        异常: timer/更新因果或边界错误由unittest报告。
        """
        # 无实际3ns样本，也必须在3ns确认。
        timeline, events = self._memory_compare(_memory(((0, {'x': True}),)), _rule(duration=3))
        # axis必须真实包含deadline，不等下一消息5ns。
        self.assertEqual([tick.time_ns for tick in timeline.ticks], [0, 3, 5])
        # timer不能声称真实信号更新。
        self.assertFalse(timeline.ticks[1].actual_update)
        # hand真值与完整来源身份。
        self.assertEqual(_facts(events), [(0, 3, 5, 'truncated')])
        # 新TRUE在旧TTL2恰到期时实际覆盖旧TTL。
        timeline, events = self._memory_compare(_memory(((0, {'x': True}), (2, {'x': True}), (4, {'x': False})), age=2), _rule(duration=3))
        # 没有假未知缺口或重置onset。
        self.assertEqual(_facts(events), [(0, 3, 4, 'closed')])
        # 更新2ns确为连续TRUE而非STALE旧样本。
        self.assertEqual(next(tick.state for tick in timeline.ticks if tick.time_ns == 2), T.TRUE)

    def test_actual_causality_and_atomic_group(self):
        """旁列更新不能误判同EOF TTL；决定性更新揭示未知则中断。

        参数: 无；两个真实布尔依赖，共同时间完整组。
        返回: None。
        异常: 因果、三值或瞬态假边沿由unittest报告。
        """
        # x在EOF3到期，y仅刷新TRUE，before/after均UNKNOWN。
        compiled = _memory(((0, {'x': True, 'y': True}), (3, {'y': True})), end=3, age=3, expression='x and y')
        # 真实任意更新不等于真实结束更新。
        timeline, events = self._memory_compare(compiled, _rule(duration=3))
        # 同EOF TTL为truncated而非interrupted。
        self.assertEqual(events[0].status, 'truncated')
        # 实际更新存在，但不是结束因果。
        self.assertTrue(timeline.ticks[-1].actual_update)
        # 必须保留actual_unknown为False。
        self.assertFalse(timeline.ticks[-1].actual_unknown)
        # y原来TRUE决定逻辑；EOF实际FALSE使过期x被揭示，确为actual未知。
        compiled = _memory(((0, {'x': True, 'y': True}), (3, {'y': False})), end=3, age=3, expression='x or y')
        # before已知TRUE，afterUNKNOWN，实际因果必须识别。
        timeline, events = self._memory_compare(compiled, _rule(duration=3))
        # 不能一律按EOF截断掩盖实际未知。
        self.assertEqual(events[0].status, 'interrupted')
        # 明确保存因果证据。
        self.assertTrue(timeline.ticks[-1].actual_unknown)
        # 同刻x/y互换，两完整组条件x and y都FALSE，无中间瞬态TRUE。
        compiled = _memory(((0, {'x': True, 'y': False}), (1, {'x': False}), (1, {'y': True})), expression='x and y')
        # 不能逐字段更新产生假rising。
        _, events = self._memory_compare(compiled, _rule('rising_edge'))
        # 真正原子组无边沿。
        self.assertEqual(events, ())
