"""用手算与独立枚举验证FIFO响应配对、未知观测和跨批状态。

输入均为明确纳秒的合成事件/条件证据，不读取真实日志。固定真值覆盖T23/T24，
随机离散枚举只作额外对照，不调用被测配对实现计算预期。还检查时间溢出、
会话隔离、同刻顺序、容量失败、标准库导入及结果身份，不宣称真实业务验收。
"""

# 独立随机生成和冻结模型替换只用于构造可重复测试资料。
from dataclasses import replace
import random
import subprocess
import sys
import unittest
from chronaxis.core import (ConditionTick, ConditionTimeline, SequenceDetector, SequenceResult,
                            SequenceRule, SequenceTick, TemporalRule, pair_sequence)
from chronaxis.core.temporal import make_event
from chronaxis.core.types import Truth as T, QualityFlag as Q
from chronaxis.timebase.conversion import INT64_MAX


def event(time, *, response=False, name=None, session='session'):
    """构造已知边沿事件，允许同刻不同ID和跨会话错误资料。

    参数: time为ns；response选择A/B规则；name可指定同刻唯一ID；session为会话。
    返回: 合法Event；测试不读取或改变既有来源。
    异常: Event模型检查错误传播。
    """
    # 时间相同不代表同一事件，同刻多事件测试用不同的稳定名字区分。
    rule = TemporalRule('b' if response else 'a', 'dataset', session, 'rising_edge')
    result = make_event(rule, time, time, None, 'point', Q.NONE, Q.NONE, trigger='rising_edge')
    return result if name is None else replace(result, event_id=name)


def rule(minimum=0, maximum=2, *, group='default'):
    """构造标准合成配对规则，时长不隐式乘秒。

    参数: minimum/maximum为ns；group为显式分组。
    返回: SequenceRule。
    异常: 无效参数由模型拒绝。
    """
    # 合成坐标的数值单位为ns，保持所有比较精确。
    return SequenceRule('sequence', 'dataset', 'session', 'a', 'b', minimum, maximum, group)


def tick(time, *, starts=(), responses=(), quality=Q.NONE, terminal=False, point_quality=None):
    """建立同刻完整证据，区分人工EOF连续未知与真实末点。

    参数: time、starts/responses；quality为连续未知原因；terminal；point_quality可覆写末点质量。
    返回: SequenceTick；默认已知FALSE足以证明观测有效，B也可来自已知边沿。
    异常: 模型不一致时传播。
    """
    # 末点质量与连续EOF分开，不能靠EOF的MISSING伪造整段未知。
    point = quality if point_quality is None else point_quality
    state = T.UNKNOWN if terminal or quality != Q.NONE else T.FALSE
    continuous_quality = Q.MISSING if terminal else quality
    condition = ConditionTick(time, state, continuous_quality, terminal=terminal,
                              point_state=T.UNKNOWN if point != Q.NONE else T.FALSE,
                              point_quality=point)
    return SequenceTick(condition, starts, responses)


def run(ticks, specification=None, *, batch_rows=1, max_pending=65536):
    """通过真实分批入口收集结果，每批转交后不在检测器保留输出。

    参数: 完整ticks；specification可选；batch_rows和max_pending用于切批/容量测试。
    返回: 完整结果tuple及已关闭检测器。
    异常: 任何真实失败直接传播给unittest。
    """
    # 每次运行独立实例，绝不跨用例共享候选。
    detector = SequenceDetector(rule() if specification is None else specification,
                                ticks[0].condition.time_ns, ticks[-1].condition.time_ns,
                                max_pending=max_pending)
    results = []
    for offset in range(0, len(ticks), batch_rows):
        results.extend(detector.push(ticks[offset:offset+batch_rows]))
    detector.finish()
    return tuple(results), detector


class SequenceTests(unittest.TestCase):
    """核对设计13.4的每个决定边界及无全局状态约束。

测试方法只使用局部合成资料；随机对照在独立列表枚举中计算预期。
    """

    def test_t23_inclusive_maximum_and_batch_invariance(self):
        """请求1、响应3、最大2，恰好截止仍匹配。

        参数: 无。返回: None。异常: 断言失败表示T23或切批身份不一致。
        """
        # 手算延迟2；批长1/2/整轴不能改变任何结果字段或ID。
        ticks = (tick(0), tick(1, starts=(event(1),)), tick(3, responses=(event(3, response=True),)), tick(5, terminal=True))
        expected, _ = run(ticks)
        self.assertEqual([(x.status, x.delay_ns, x.decided_ns) for x in expected], [('matched', 2, 3)])
        for size in (2, 20):
            self.assertEqual(run(ticks, batch_rows=size)[0], expected)

    def test_t24_unknown_is_not_no_response(self):
        """等待中曾缺响应观测，即使后来恢复也只能判断不确定。

        参数: 无。返回: None。异常: 错把UNKNOWN当False时断言失败。
        """
        # 1到2缺观测，截止3时已恢复，历史未知仍不能被抹掉。
        ticks = (tick(0), tick(1, starts=(event(1),), quality=Q.DECODE_ERROR), tick(2), tick(4, terminal=True))
        result = run(ticks)[0][0]
        self.assertEqual((result.status, result.decided_ns, result.observation_quality), ('indeterminate', 3, Q.DECODE_ERROR))

    def test_fifo_and_response_used_once(self):
        """两个等待请求只收到一个响应，最早的配对，另一个超时。

        参数: 无。返回: None。异常: 复用B或倒序配对时断言失败。
        """
        # deadline分别4和5，响应3只能给最早的请求1。
        ticks = (tick(0), tick(1, starts=(event(1),)), tick(2, starts=(event(2),)),
                 tick(3, responses=(event(3, response=True),)), tick(6, terminal=True))
        results, detector = run(ticks, rule(maximum=3))
        self.assertEqual([(x.request.confirmed_ns, x.status, x.decided_ns) for x in results], [(1, 'matched', 3), (2, 'no_response', 5)])
        self.assertEqual(detector.pending_count, 0)

    def test_minimum_inclusive_and_early_b_discarded(self):
        """太早的响应不能保存到稍后冒充合格响应，最小延迟端点包含。

        参数: 无。返回: None。异常: 提前B被挪时间使用时失败。
        """
        ticks = (tick(0, starts=(event(0),)), tick(1, responses=(event(1, response=True),)),
                 tick(2, responses=(event(2, response=True),)), tick(4, terminal=True))
        result = run(ticks, rule(2, 3))[0][0]
        self.assertEqual((result.response.confirmed_ns, result.delay_ns), (2, 2))
        without_later = (ticks[0], ticks[1], tick(4, terminal=True))
        self.assertEqual(run(without_later, rule(2, 3))[0][0].status, 'no_response')

    def test_simultaneous_permutation_and_zero_delay(self):
        """同刻A/B整组处理，tuple顺序不影响一对一关系或ID。

        参数: 无。返回: None。异常: 遍历顺序改变事实时失败。
        """
        starts = (event(1, name='a2'), event(1, name='a1'))
        responses = (event(1, response=True, name='b2'), event(1, response=True, name='b1'))
        first = run((tick(0), tick(1, starts=starts, responses=responses), tick(2, terminal=True)), rule(0, 0))[0]
        second = run((tick(0), tick(1, starts=starts[::-1], responses=responses[::-1]), tick(2, terminal=True)), rule(0, 0))[0]
        self.assertEqual(first, second)
        self.assertEqual([(x.request.event_id, x.response.event_id) for x in first], [('a1', 'b1'), ('a2', 'b2')])

    def test_same_deadline_b_then_remaining_timeout(self):
        """截止点的B先用掉最老请求，同刻剩余请求才判超时。

        参数: 无。返回: None。异常: 先超时丢失B时失败。
        """
        ticks = (tick(0, starts=(event(0, name='a1'), event(0, name='a2'))),
                 tick(2, responses=(event(2, response=True),), terminal=True))
        self.assertEqual([(x.request.event_id, x.status) for x in run(ticks)[0]], [('a1', 'matched'), ('a2', 'no_response')])

    def test_sparse_deadline_and_late_unknown_do_not_contaminate(self):
        """没有新记录也精确到期，之后才缺失的数据不污染已完成等待。

        参数: 无。返回: None。异常: 用下一条消息时刻代替deadline时失败。
        """
        ticks = (tick(0), tick(1, starts=(event(1),)), tick(9, terminal=True, point_quality=Q.MISSING))
        result = run(ticks)[0][0]
        self.assertEqual((result.status, result.decided_ns, result.observation_quality), ('no_response', 3, Q.NONE))

    def test_eof_before_deadline(self):
        """日志在等待完成前结束，不得缩短deadline后宣布未响应。

        参数: 无。返回: None。异常: 提前EOF被当正常超时时失败。
        """
        result = run((tick(0), tick(1, starts=(event(1),)), tick(2, terminal=True)))[0][0]
        self.assertEqual((result.status, result.decided_ns, result.observation_quality), ('indeterminate', 2, Q.MISSING))

    def test_actual_terminal_response_and_zero_domain(self):
        """真实末点B可配对，零长度会话也可承载同刻真实点。

        参数: 无。返回: None。异常: 把终点点证据抹掉时失败。
        """
        ticks = (tick(0, starts=(event(0),), responses=(event(0, response=True),), terminal=True),)
        self.assertEqual(run(ticks, rule(0, 0))[0][0].status, 'matched')
        self.assertEqual(run((tick(0, terminal=True, point_quality=Q.MISSING),))[0], ())

    def test_endpoint_unknown_and_zero_delay_unknown(self):
        """截止点真实无效和零延迟未知点均不能证明未响应。

        参数: 无。返回: None。异常: 只看正长度区间忽略关键点时失败。
        """
        cases = ((tick(0, starts=(event(0),)), tick(2, terminal=True, point_quality=Q.STALE)),
                 (tick(0, starts=(event(0),), terminal=True, point_quality=Q.MISSING),))
        for ticks, maximum in zip(cases, (2, 0)):
            self.assertEqual(run(ticks, rule(maximum=maximum))[0][0].status, 'indeterminate')

    def test_unknown_before_request_not_inherited(self):
        """请求发出之前的缺失不污染之后完整的等待区间。

        参数: 无。返回: None。异常: 全会话质量OR误用于每个请求时失败。
        """
        ticks = (tick(0, quality=Q.MISSING), tick(1, starts=(event(1),)), tick(4, terminal=True))
        self.assertEqual(run(ticks)[0][0].observation_quality, Q.NONE)

    def test_matched_preserves_unknown_evidence(self):
        """最后观察到B仍匹配，但不隐瞒等待中不同的未知原因。

        参数: 无。返回: None。异常: 丢失中间诊断时失败。
        """
        ticks = (tick(0, starts=(event(0),), quality=Q.STALE), tick(1, quality=Q.DECODE_ERROR),
                 tick(2, responses=(event(2, response=True),), terminal=True))
        result = run(ticks)[0][0]
        self.assertEqual((result.status, result.observation_quality), ('matched', Q.STALE | Q.DECODE_ERROR))

    def test_multiple_deadlines_and_later_request_quality(self):
        """多个请求的质量起点和deadline独立，不在一次大步推进时混淆。

        参数: 无。返回: None。异常: 早晚请求共享错误质量时失败。
        """
        ticks = (tick(0, starts=(event(0),), quality=Q.MISSING), tick(1, starts=(event(1),)), tick(6, terminal=True))
        results = run(ticks, rule(maximum=3))[0]
        self.assertEqual([(x.decided_ns, x.status) for x in results], [(3, 'indeterminate'), (4, 'no_response')])

    def test_group_identity_and_instance_isolation(self):
        """相同时间和事件在不同组产生不同身份，各实例没有共享候选。

        参数: 无。返回: None。异常: 跨组复用状态或ID时失败。
        """
        ticks = (tick(0, starts=(event(0),)), tick(2, terminal=True))
        first = run(ticks, rule(group='vehicle-a'))[0]
        second = run(ticks, rule(group='vehicle-b'))[0]
        self.assertNotEqual(first[0].result_id, second[0].result_id)
        self.assertEqual(run((tick(0), tick(2, terminal=True)), rule(group='vehicle-a'))[0], ())

    def test_foreign_session_and_wrong_rule_rejected(self):
        """同名事件来自另一会话或不匹配规则时拒绝整批。

        参数: 无。返回: None。异常: 不应发生的跨范围配对由断言发现。
        """
        for wrong in (event(0, session='other'), event(0, response=True)):
            detector = SequenceDetector(rule(), 0, 2)
            with self.assertRaises(ValueError):
                detector.push((tick(0, starts=(wrong,)),))
            self.assertEqual(detector.pending_count, 0)
            with self.assertRaises(ValueError):
                detector.push(())

    def test_capacity_failure_clears_and_closes(self):
        """候选超过限制时明确失败并释放队列，不悄悄丢掉请求。

        参数: 无。返回: None。异常: 容量失守或失败后继续运行时失败。
        """
        detector = SequenceDetector(rule(maximum=5), 0, 10, max_pending=1)
        self.assertEqual(detector.push((tick(0, starts=(event(0),)),)), ())
        with self.assertRaises(MemoryError):
            detector.push((tick(1, starts=(event(1),)),))
        self.assertEqual(detector.pending_count, 0)
        with self.assertRaises(ValueError):
            detector.finish()

    def test_capacity_released_at_deadline(self):
        """前一请求已到期释放后可容纳下一请求，容量不累计整段历史。

        参数: 无。返回: None。异常: 已决定请求仍占候选额度时失败。
        """
        ticks = (tick(0, starts=(event(0),)), tick(3, starts=(event(3),)), tick(6, terminal=True))
        self.assertEqual(len(run(ticks, max_pending=1)[0]), 2)

    def test_bad_order_missing_start_and_lifecycle(self):
        """缺会话首组、重复时间组和缺EOF都不能静默修补。

        参数: 无。返回: None。异常: 生命周期或时间协议未被拒绝时失败。
        """
        for bad in ((tick(1),), (tick(0), tick(0))):
            with self.assertRaises(ValueError):
                SequenceDetector(rule(), 0, 2).push(bad)
        detector = SequenceDetector(rule(), 0, 2)
        self.assertEqual(detector.push(()), ())
        detector.push((tick(0),))
        with self.assertRaises(ValueError):
            detector.finish()
        detector.push((tick(2, terminal=True),))
        detector.finish()
        with self.assertRaises(ValueError):
            detector.finish()
        with self.assertRaises(ValueError):
            detector.push(())

    def test_deadline_overflow(self):
        """绝对纳秒接近int64上限时，deadline不能回绕或静默裁剪。

        参数: 无。返回: None。异常: 未拒绝溢出时失败。
        """
        detector = SequenceDetector(rule(), INT64_MAX-1, INT64_MAX)
        with self.assertRaises(OverflowError):
            detector.push((tick(INT64_MAX-1, starts=(event(INT64_MAX-1),)),))
        self.assertEqual(detector.pending_count, 0)

    def test_rule_validation(self):
        """拒绝伪整数、负延迟、倒置范围、空分组和非法规则名称。

        参数: 无。返回: None。异常: 非法规则被接受时失败。
        """
        for changes in ({'min_delay_ns': True}, {'max_delay_ns': 1.5}, {'min_delay_ns': -1},
                        {'min_delay_ns': 3}, {'group_id': ' '}, {'rule_id': 'a.b'}):
            with self.assertRaises((TypeError, ValueError)):
                replace(rule(), **changes)

    def test_numpy_integer_times_match_python_identity(self):
        """公共整数协议允许NumPy整数，结果身份和延迟仍须与Python整数一致。

        参数: 无。返回: None。异常: 已合法时间在身份编码时失败或精度变化时断言失败。
        """
        # 只在测试构造数组整数，不给标准库产品模块增加NumPy依赖。
        import numpy as np
        normal = (tick(0), tick(1, starts=(event(1),)), tick(3, responses=(event(3, response=True),), terminal=True))
        wrapped = tuple(SequenceTick(replace(item.condition, time_ns=np.int64(item.condition.time_ns)),
                                     tuple(replace(e, confirmed_ns=np.int64(e.confirmed_ns)) for e in item.starts),
                                     tuple(replace(e, confirmed_ns=np.int64(e.confirmed_ns)) for e in item.responses))
                        for item in normal)
        expected = run(normal)[0][0]
        actual = run(wrapped, rule(np.int64(0), np.int64(2)))[0][0]
        self.assertEqual(actual, expected)
        self.assertIs(type(actual.decided_ns), int)
        self.assertIs(type(actual.delay_ns), int)

    def test_tick_validation(self):
        """同刻重复ID、时间不符和未知条件下的B均拒绝。

        参数: 无。返回: None。异常: 非完整证据被接受时失败。
        """
        with self.assertRaises(ValueError):
            tick(0, starts=(event(0), event(0)))
        with self.assertRaises(ValueError):
            tick(0, starts=(event(1),))
        with self.assertRaises(ValueError):
            tick(0, responses=(event(0, response=True),), quality=Q.MISSING)
        with self.assertRaises(TypeError):
            SequenceTick(tick(0).condition, [event(0)])

    def test_result_validation(self):
        """公共结果模型不能手工组装成缺观测却正常超时的矛盾结果。

        参数: 无。返回: None。异常: 非法状态/字段组合被接受时失败。
        """
        result = run((tick(0, starts=(event(0),)), tick(2, terminal=True)))[0][0]
        for changes in ({'observation_quality': Q.MISSING}, {'decided_ns': 1}, {'delay_ns': 0},
                        {'status': 'indeterminate'}, {'status': 'anything'}, {'response': event(2, response=True)}):
            with self.assertRaises(ValueError):
                replace(result, **changes)
        self.assertIsInstance(result, SequenceResult)

    def test_memory_adapter_and_permuted_inputs(self):
        """完整内存入口接收原Event和条件轴，输出与分批入口完全相同。

        参数: 无。返回: None。异常: 便利接口与实际状态机不一致时失败。
        """
        ticks = (tick(0), tick(1, starts=(event(1),)), tick(3, responses=(event(3, response=True),)), tick(5, terminal=True))
        timeline = ConditionTimeline(0, 5, tuple(item.condition for item in ticks))
        for size in (1, 3, 100):
            self.assertEqual(pair_sequence(rule(), (event(1),), (event(3, response=True),), timeline, batch_rows=size), run(ticks)[0])
        with self.assertRaises(ValueError):
            pair_sequence(rule(), (event(2),), (), timeline)
        with self.assertRaises(ValueError):
            pair_sequence(rule(), (event(1), event(1)), (), timeline)

    def test_activity_uses_confirmation_not_onset(self):
        """持续活动作为A时用确认时刻配对，不把尚未成立的起点当请求。

        参数: 无。返回: None。异常: onset与confirmed混淆时失败。
        """
        source_rule = TemporalRule('a', 'dataset', 'session', 'condition_duration', 2)
        request = make_event(source_rule, 0, 2, 4, 'closed', Q.NONE, Q.NONE)
        ticks = (tick(0), tick(2, starts=(request,)), tick(3, responses=(event(3, response=True),)), tick(5, terminal=True))
        self.assertEqual(run(ticks)[0][0].delay_ns, 1)

    def test_random_discrete_oracle(self):
        """独立逐请求枚举与FIFO状态机对照，包含随机未知区间和端点。

        参数: 无。返回: None。异常: 任何结果、决定时刻或质量差异都失败。
        """
        rng = random.Random(20261022)
        for _ in range(200):
            # 离散完整观测轴每ns一组，随机A/B只在已知B点生成。
            maximum = rng.randrange(1, 6)
            minimum = rng.randrange(maximum+1)
            qualities = [Q.MISSING if rng.randrange(4) == 0 else Q.NONE for _ in range(12)]
            starts = [event(t) for t in range(10) if rng.randrange(3) == 0]
            responses = [event(t, response=True) for t in range(12) if qualities[t] == Q.NONE and rng.randrange(3) == 0]
            # Oracle用未使用请求列表枚举，不调用被测队列、计数器或结果构造。
            chosen = {}
            for response in responses:
                eligible = [request for request in starts if request.event_id not in chosen
                            and minimum <= response.confirmed_ns-request.confirmed_ns <= maximum]
                if eligible:
                    chosen[eligible[0].event_id] = response
            expected = {}
            for request in starts:
                response = chosen.get(request.event_id)
                deadline = request.confirmed_ns+maximum
                end = response.confirmed_ns if response else min(11, deadline)
                unknown = any(quality != Q.NONE for quality in qualities[request.confirmed_ns:end+1]) or response is None and deadline > 11
                status = 'matched' if response else 'indeterminate' if unknown else 'no_response'
                expected[request.event_id] = (status, end, Q.MISSING if unknown else Q.NONE)
            ticks = tuple(tick(t, starts=tuple(a for a in starts if a.confirmed_ns == t),
                               responses=tuple(b for b in responses if b.confirmed_ns == t),
                               quality=qualities[t], terminal=t == 11) for t in range(12))
            results = run(ticks, rule(minimum, maximum), batch_rows=rng.randrange(1, 9))[0]
            self.assertEqual({x.request.event_id: (x.status, x.decided_ns, x.observation_quality) for x in results}, expected)

    def test_core_import_without_numpy(self):
        """标准库core入口不得因为新增顺序能力隐式加载NumPy或CAN。

        参数: 无。返回: None。异常: 独立子进程导入失败或加载重依赖时失败。
        """
        # 新解释器防止本测试进程已导入依赖导致误判。
        code = 'import sys; from chronaxis.core import SequenceDetector; assert "numpy" not in sys.modules; assert "can" not in sys.modules'
        result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    # 直接执行同样只运行合成专项，不触碰历史快照。
    unittest.main()
