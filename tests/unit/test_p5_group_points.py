"""PERF-P5-ORDER-01 B1：核对time_order组点包P5G1、文件组点生成器和工作进程points模式。

期望值按手写帧逐项给出，不把被测编码器的往返结果当唯一依据；字节位型另用struct核对。
ASC与DBC在本测试临时目录生成，不读取历史项目、不创建正式结果、不做性能计时。
跨文件合并、求值和积分属于B2，这里不覆盖。
"""
from collections import deque
from decimal import Decimal
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from chronaxis._control_wire import ControlChannel
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import validate_expression
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q, TimeType
from chronaxis.execution.file_group_points import (DeferredPointError, FileGroupPoints, file_points_cost,
    file_points_minimum_cost)
from chronaxis.execution.file_integral_terms import SameTimeGroupSummary, IntegralTermsChunk, IntegralColumnTerms
from chronaxis.execution.integral_blocks import (IntegralBlockError, MAX_POINTS, POINT_MESSAGE_LIMIT, decode_packet,
    decode_points, decode_points_prefix, encode_packet, encode_points, pack_task, point_cost, restore_task, task_mode)
from chronaxis.execution.parallel_integral_worker import _error_text, take_events, worker_main
from chronaxis.execution.same_frame_integrals import SameFrameBinding, SameFrameEvaluator, same_frame_evaluator_cost
from chronaxis.legacy.records import LegacyCANField, LegacyRawFrame
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.asc import ASCSpec
from chronaxis.sources.raw_can import RawCANRecord
from chronaxis.sources.text_can_decode import DecodedCANRecord
from chronaxis.sources.text_can_spec import CANTextSpec

from test_p5_parallel_transport import _ByteEndpoint


def facts(identity=None, compatibility=()):
    """返回一份独立的组点事实。参数: 帧型及兼容字段tuple。返回: dict。异常: 无。"""
    return dict(count=7, first_ns=0, last_ns=2000000000, decode_calls=5, first_order_time=Decimal('0'),
                last_order_time=Decimal('2.000000000000000001'), compatibility_fields=compatibility,
                frame_identity=identity)


def single(time, values):
    """按组内位置约定构造单帧组点。参数: 时间纳秒、值tuple。返回: SameTimeGroupSummary。异常: 无。"""
    return SameTimeGroupSummary(time, 0, 0, 1, values, values, (None,) * len(values))


def number(value):
    """取得有效float64数值。参数: float。返回: ScalarValue。异常: 无。"""
    return ScalarValue(value, D.FLOAT64)


class PointPacketTests(unittest.TestCase):
    """P5G1编码与解码：位型、事实位置、错误包和费用上界。"""

    def test_roundtrip_keeps_bits_positions_and_facts(self):
        """负零、uint64最大值、无效值、多帧冲突位置和延迟错误原文都无损恢复；单帧组点比多帧短。"""
        values = (ScalarValue(-0., D.FLOAT64), ScalarValue(2**64 - 1, D.UINT64), ScalarValue(None, D.INT64, False, Q.MISSING))
        later = (number(float.fromhex('0x1.0000000000001p+0')), ScalarValue(1, D.UINT64), ScalarValue(-3, D.INT64))
        multi = SameTimeGroupSummary(10, 0, 2, 3, values, later, (None, 2, 1))
        deferred = DeferredPointError(11, ValueError, '同一报文绑定匹配多种实际帧，请补充 is_fd')
        events = (single(5, values), multi, deferred)
        for identity in (None, (False, True)):
            with self.subTest(identity=identity):
                packet = encode_points(3, 4, events, True, facts(identity, (('{"k":1}', False),)))
                self.assertEqual(packet[:4], b'P5G1')
                self.assertIn(struct.pack('!d', float.fromhex('0x1.0000000000001p+0')), packet)
                restored = decode_points(packet)
                self.assertEqual((restored.file_index, restored.number, restored.eof), (3, 4, True))
                self.assertEqual(restored.events, events)
                self.assertEqual(restored.facts, facts(identity, (('{"k":1}', False),)))
                self.assertEqual(struct.pack('!d', restored.events[0].first_values[0].value), struct.pack('!d', -0.))
                self.assertIs(restored.events[2].kind, ValueError)
        one = encode_points(0, 0, (single(5, values),), False, facts())
        two = encode_points(0, 0, (SameTimeGroupSummary(5, 0, 1, 2, values, values, (None,) * 3),), False, facts())
        self.assertLess(len(one), len(two))

    def test_prefix_reads_facts_without_decoding_events(self):
        """事件区被破坏时完整解码失败，但收包用的前缀解码仍得到文件号、块号、EOF和事实。"""
        empty = encode_points(2, 9, (), False, facts((False, False)))
        packet = bytearray(encode_points(2, 9, (single(5, (number(1.),)),), False, facts((False, False))))
        packet[len(empty)] = 9  # 事件区紧接在事件数之后；把首个事件的标记改成未知值。
        packet = bytes(packet)
        with self.assertRaisesRegex(IntegralBlockError, '标记'):
            decode_points(packet)
        self.assertEqual(decode_points_prefix(packet), (2, 9, False, facts((False, False))))

    def test_malformed_packets_and_unsupported_events_are_rejected(self):
        """两种包互不接受；截断、尾随、超量、非法位置、子类、超长原文和非法帧型都拒绝。"""
        packet = encode_points(0, 0, (single(5, (number(1.),)),), False, facts())
        area = encode_packet(0, 0, (IntegralTermsChunk(0, 1, (IntegralColumnTerms((1.,), (True,), 1, 1, Q.NONE),)),),
                             False, facts())
        for broken in (packet[:-1], packet + b'x', area):
            with self.subTest(broken=broken[:8]):
                with self.assertRaises(IntegralBlockError):
                    decode_points(broken)
        with self.assertRaises(IntegralBlockError):
            decode_packet(packet)
        with self.assertRaisesRegex(IntegralBlockError, '2048'):
            encode_points(0, 0, (single(5, (number(1.),)),) * (MAX_POINTS + 1), False, facts())

        class LocalError(ValueError):
            """ValueError的子类；延迟错误只接受四种内建类型本身。"""

        bad = (SameTimeGroupSummary(5, 0, 1, 2, (number(1.),), (number(2.),), (0,)),
               SameTimeGroupSummary(5, 3, 3, 1, (number(1.),), (number(1.),), (None,)),
               SameTimeGroupSummary(5, 0, 0, 1, (number(1.),), (number(2.),), (None,)),
               DeferredPointError(5, LocalError, 'x'), DeferredPointError(5, RuntimeError, 'x'),
               DeferredPointError(5, ValueError, 'x' * (POINT_MESSAGE_LIMIT + 1)), DeferredPointError(None, ValueError, 'x'))
        for event in bad:
            with self.subTest(event=type(event).__name__):
                with self.assertRaises(IntegralBlockError):
                    encode_points(0, 0, (event,), False, facts())
        with self.assertRaisesRegex(IntegralBlockError, '帧型'):
            encode_points(0, 0, (), False, facts((False, 1)))
        empty = encode_points(0, 0, (), False, facts())
        packet = bytearray(encode_points(0, 0, (DeferredPointError(5, ValueError, 'x'),), False, facts()))
        packet[len(empty) + 4] = 7  # 事件标记1字节+时间整数3字节之后是错误类型序号。
        with self.assertRaisesRegex(IntegralBlockError, '错误类型'):
            decode_points(bytes(packet))

    def test_point_cost_covers_actual_encoding(self):
        """每个事件实际增加的字节数不超过point_cost的编码上界。"""
        values = tuple(ScalarValue(-(2**63), D.INT64) for _ in range(5))
        empty = len(encode_points(0, 0, (), False, facts()))
        for event in (single(-(2**63), values), SameTimeGroupSummary(2**63 - 1, 0, 9, 10, values, values, (9,) * 5),
                      DeferredPointError(2**63 - 1, OverflowError, '溢出' * 100)):
            with self.subTest(event=type(event).__name__):
                grown = len(encode_points(0, 0, (event,), False, facts())) - empty
                self.assertLessEqual(grown, point_cost(event)[0])

    def test_task_mode_is_required_and_checked(self):
        """模式随任务传输；默认terms；未知值和缺字段在重建前拒绝。"""
        case = FileGroupPointsTests('test_budget_matches_estimate_and_close_is_idempotent')
        budget, definitions, expressions, specs, binding = case.task()
        task = pack_task(definitions, expressions, specs, binding, 'session')
        self.assertEqual(task_mode(task), 'terms')
        self.assertEqual(task_mode(pack_task(definitions, expressions, specs, binding, 'session', mode='points')), 'points')
        self.assertNotIn('mode', restore_task(task))
        for bad in ('area', None, 1):
            with self.subTest(mode=bad):
                with self.assertRaisesRegex(ValueError, '模式'):
                    task_mode(dict(task, mode=bad))
        missing = dict(task)
        missing.pop('mode')
        with self.assertRaises(ValueError):
            restore_task(missing)

    def test_error_text_without_notes_keeps_only_message(self):
        """组点模式只发送str(错误)，与现有time_order读取的错误格式一致。"""
        error = ValueError('原错误')
        error.add_note('清理说明')
        self.assertEqual(_error_text(error, False), '原错误')
        self.assertIn('清理说明', _error_text(error))


class FileGroupPointsTests(unittest.TestCase):
    """只用内存帧；期望组点按手写帧逐项给出。"""

    def task(self, *, policies=('error', 'error'), dbc_fd=False):
        """建立两信号同帧任务。参数: 两个信号的同刻政策和DBC FD属性；字段未限定FD，绑定fd同为None。
        返回: (预算, 定义, 表达式, 计算项, 绑定)。异常: 声明构造原错误。
        """
        clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'origin')
        fields = (LegacyCANField(0, 'Voltage', 256), LegacyCANField(0, 'Current', 256))
        definitions = tuple(SignalDefinition(name, 'bus', field.key, D.FLOAT64, unit, 10**9, same_time_policy=policy)
                            for name, field, unit, policy in zip(('voltage', 'current'), fields, ('V', 'A'), policies))
        bindings = DeclarationBindings('session', clock, Interval(0, 10**9),
                                       (DeclaredSource('bus', clock, 'synthetic'),), definitions)
        expression = validate_expression('voltage * current', bindings)
        spec = CalculationDefinition('energy', 'integral', Interval(0, 10**9))
        binding = SameFrameBinding('bus', 0, 256, False, None, dbc_fd)
        return ResourceBudget(), definitions, (expression,), (spec,), binding

    def owner(self, **options):
        """构造组点生成器并登记关闭。参数: 同task。返回: (owner, 预算, 定义)。异常: 构造原错误。"""
        budget, definitions, expressions, specs, binding = self.task(**options)
        owner = FileGroupPoints(budget, definitions, expressions, specs, binding, 'session')
        self.addCleanup(owner.close)
        return owner, budget, definitions

    def record(self, time, sequence, voltage, current, definitions, *, target=True, fd=False):
        """生成真实typed投影输入，不读文件。参数: 纳秒、局部序号、两信号原值、定义、是否目标帧、是否FD帧。
        返回: DecodedCANRecord。异常: 模型构造原错误。
        """
        frame = LegacyRawFrame(time / 1e9, 256 if target else 257, False, False, False, 0, 0, b'', fd, True, False, False)
        raw = RawCANRecord(frame, time, Path('memory.asc'), sequence + 1, sequence, None, 'test', 0)
        values = ((definitions[0].field, voltage), (definitions[1].field, current)) if target else ()
        return DecodedCANRecord('bus', 0, sequence, raw, values, 'decoded' if target else 'unselected')

    def feed_all(self, owner, definitions, rows):
        """依次交付帧并收集事件。参数: owner、定义、(时间, 电压, 电流[, 选项])行。返回: 事件list。异常: 原错误。"""
        events = []
        for sequence, row in enumerate(rows):
            time, voltage, current, *rest = row
            events.extend(owner.feed(self.record(time, sequence, voltage, current, definitions, **(rest[0] if rest else {}))))
        events.extend(owner.finish())
        return events

    def values(self, group, which='last'):
        """取组点首值或末值的浮点数。参数: 组点、'first'或'last'。返回: tuple[float]。异常: 无。"""
        return tuple(item.value for item in (group.last_values if which == 'last' else group.first_values))

    def test_groups_by_time_with_local_positions_and_last_values(self):
        """同一时刻两帧合成一个多帧组点，末值取后一帧；无关帧不进入组点；时间严格递增。"""
        owner, _, definitions = self.owner(policies=('last_by_sequence', 'last_by_sequence'))
        events = self.feed_all(owner, definitions, ((0, 10., 1.), (0, 20., 2.), (5, 30., 3.),
            (6, 0., 0., dict(target=False)), (7, 40., 4.)))
        self.assertEqual([event.time_ns for event in events], [0, 5, 7])
        first = events[0]
        self.assertEqual((first.first_sequence, first.last_sequence, first.count), (0, 1, 2))
        self.assertEqual(self.values(first, 'first'), (10., 1.))
        self.assertEqual(self.values(first), (20., 2.))
        self.assertEqual(first.first_conflicts, (None, None))
        self.assertEqual([event.count for event in events[1:]], [1, 1])
        self.assertIs(events[1].first_values, events[1].last_values)
        self.assertEqual(owner.frame_identity, (False, False))

    def test_conflict_positions_follow_policy_and_stop_the_file(self):
        """error政策信号与首帧不同时记组内位置；冲突组立即交付，之后不再交付组点。"""
        owner, _, definitions = self.owner(policies=('last_by_sequence', 'error'))
        events = []
        for sequence, (time, voltage, current) in enumerate(((0, 1., 2.), (0, 9., 2.), (0, 9., 3.), (5, 1., 1.))):
            events.append(owner.feed(self.record(time, sequence, voltage, current, definitions)))
        self.assertEqual(events[:2], [(), ()])
        conflict, = events[2]
        self.assertEqual((conflict.time_ns, conflict.count, conflict.first_conflicts), (0, 3, (None, 2)))
        self.assertEqual(events[3], ())
        self.assertTrue(owner.stopped)
        self.assertEqual(owner.finish(), ())
        owner, _, definitions = self.owner()
        group, = self.feed_all(owner, definitions, ((0, 1., 2.), (0, 1., 2.), (0, 5., 6.)))
        self.assertEqual(group.first_conflicts, (2, 2))

    def test_projection_error_is_deferred_with_prefix_and_original_text(self):
        """DBC标FD且未限定FD时，同文件内先经典后FD由投影报错；它作为延迟错误交付，前面的帧先成组。"""
        owner, _, definitions = self.owner(dbc_fd=True)
        events = self.feed_all(owner, definitions, ((0, 1., 2.), (0, 1., 2.), (5, 1., 2., dict(fd=True)), (7, 1., 2.)))
        group, error = events
        self.assertEqual((group.time_ns, group.count), (0, 2))
        self.assertEqual(error, DeferredPointError(5, ValueError, '同一报文绑定匹配多种实际帧，请补充 is_fd'))
        self.assertTrue(owner.stopped)
        self.assertEqual(owner.frame_identity, (False, False))
        owner, _, definitions = self.owner(dbc_fd=True)
        prefix, error = self.feed_all(owner, definitions, ((0, 1., 2.), (0, 1., 2., dict(fd=True))))
        self.assertEqual((prefix.time_ns, prefix.count, error.time_ns), (0, 1, 0))

    def test_only_exact_builtin_errors_are_deferred(self):
        """子类、其他类型及超长原文不延迟，原样抛出并使owner失败；四种内建类型都可延迟。"""
        class LocalError(ValueError):
            """ValueError的子类，不能按内建ValueError重建。"""

        for raised, deferred in ((ValueError('v'), True), (TypeError('t'), True), (OverflowError('o'), True),
                                 (ZeroDivisionError('z'), True), (LocalError('l'), False), (RuntimeError('r'), False),
                                 (ValueError('x' * (POINT_MESSAGE_LIMIT + 1)), False)):
            with self.subTest(error=type(raised).__name__, size=len(str(raised))):
                owner, _, definitions = self.owner()
                with patch.object(owner._evaluator, 'normalize', side_effect=raised):
                    if deferred:
                        event, = owner.feed(self.record(3, 0, 1., 2., definitions))
                        self.assertEqual(event, DeferredPointError(3, type(raised), str(raised)))
                    else:
                        with self.assertRaises(type(raised)):
                            owner.feed(self.record(3, 0, 1., 2., definitions))
                        with self.assertRaises(Exception):
                            owner.finish()

    def test_compatibility_and_identity_before_and_after_frames(self):
        """DBC为FD、实际经典帧时记录兼容提示；首帧前帧型为None。"""
        owner, _, definitions = self.owner(dbc_fd=True)
        self.assertIsNone(owner.frame_identity)
        owner.feed(self.record(0, 0, 1., 2., definitions))
        self.assertEqual(owner.frame_identity, (False, False))
        self.assertEqual(set(owner.compatibility_fields.values()), {False})
        self.assertEqual({field.signal for field in owner.compatibility_fields}, {'Voltage', 'Current'})

    def test_budget_matches_estimate_and_close_is_idempotent(self):
        """构造前的报价覆盖实际预约，实际预约等于本owner与求值器登记之和；下界不高于实际；关闭两次后账本为0。

        与面积生成器的同类测试相同，报价在构造前取得：声明对象的属性字典大小可能在首次使用后变化。
        """
        budget, definitions, expressions, specs, binding = self.task()
        quote = file_points_cost(definitions, expressions)
        owner = FileGroupPoints(budget, definitions, expressions, specs, binding, 'session')
        self.assertLessEqual(budget.ram_bytes, quote)
        self.assertEqual(budget.ram_bytes, owner._held_cost + owner._evaluator._held_cost)
        self.assertLessEqual(file_points_minimum_cost(len(definitions)), budget.ram_bytes)
        self.assertGreater(quote, same_frame_evaluator_cost(definitions, expressions))
        owner.close(); owner.close()
        self.assertEqual(budget.ram_bytes, 0)


class WorkerPointsModeTests(unittest.TestCase):
    """在本进程内运行真实worker_main与CANTextDecodeRead，核points模式的包、事实和错误次序。"""

    def setUp(self):
        """参数无；建立临时目录、DBC和单信号任务；写入失败原样传播。"""
        self.temporary = tempfile.TemporaryDirectory(prefix='chronaxis-p5-points-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.dbc = self.root / 'signals.dbc'
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Power: 1 Node\n'
                            ' SG_ Power : 0|8@1+ (1,0) [0|255] "W" Node\n', encoding='utf-8')
        self.timebase = TimebaseSpec('clock', TimeType.RELATIVE, 'origin')
        self.definition = SignalDefinition('power', 'bus', LegacyCANField(0, 'Power', 256, False, False).key,
                                           D.FLOAT64, 'W', 3000000000)
        self.domain = Interval(0, 4000000000)
        bindings = DeclarationBindings('session', self.timebase, self.domain,
                                       (DeclaredSource('bus', self.timebase, 'synthetic-points'),), (self.definition,))
        self.expression = validate_expression('power', bindings)
        self.specification = CalculationDefinition('energy', 'integral', self.domain, output_unit='J')
        self.binding = SameFrameBinding('bus', 0, 256, False, False, False)

    def asc(self, name, count, *, bad=False):
        """写一个ASC。参数: 文件名、目标帧数（每帧间隔1ms，值依次0—9循环）、是否在末尾加坏行。
        返回: ASCSpec。异常: 写入错误。
        """
        path = self.root / name
        lines = ''.join(f'{i / 1000:.9f} 1 100 Rx d 1 {i % 10:02X}\n' for i in range(count))
        path.write_text('base hex timestamps absolute\n' + lines + ('broken data record\n' if bad else ''),
                        encoding='utf-8')
        return ASCSpec(path)

    def run_worker(self, spec, grants, *, evaluator=None):
        """用字节端点运行worker_main。参数: ASC、next许可数、可替换的求值器类。
        返回: (控制消息list, 解码后的组点包list, 预算实例)。异常: 原worker错误。
        """
        class BudgetProbe(ResourceBudget):
            """记录worker内实际账本，供结束后核对为0。"""
            instance = None

            def __init__(self, *args):
                """参数转交预算；保存实例；返回None；原错传播。"""
                super().__init__(*args)
                type(self).instance = self

        incoming, outgoing, sent = deque(), deque(), deque()
        parent = ControlChannel(_ByteEndpoint(outgoing, incoming), 'integral', parent=True, max_bytes=64 * 1048576)
        child = ControlChannel(_ByteEndpoint(incoming, outgoing), 'integral', parent=False, max_bytes=64 * 1048576)
        data = _ByteEndpoint(deque(), sent)
        source = CANTextSpec('bus', (spec,), self.dbc, 0, self.timebase, 'strict')
        task = pack_task((self.definition,), (self.expression,), (self.specification,), self.binding, 'session',
                         domain=self.domain, mode='points')
        parent.send(('file', 0, source, (self.definition,), dict(integrity=False, trace=False), 64 * 1048576, None))
        parent.send(('configure', 0, task, 64 * 1048576))
        for _ in range(grants):
            parent.send(('next',))
        parent.send(('close',))
        patches = [patch('chronaxis.execution.parallel_integral_worker.ResourceBudget', BudgetProbe),
                   patch('chronaxis.execution.parallel_integral_worker.signal.signal')]
        if evaluator is not None:
            patches.append(patch('chronaxis.execution.file_group_points.SameFrameEvaluator', evaluator))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        worker_main(child, data)
        messages = []
        while parent.poll():
            messages.append(parent.recv())
        parent.close()
        packets = [decode_points(packet) for packet in sent if packet[:4] == b'P5G1']
        return messages, packets, BudgetProbe.instance

    def failing_evaluator(self, at):
        """返回第at次归一化抛ValueError的求值器类。参数: 从1起的调用序号。返回: 类。异常: 无。"""
        class FailingEvaluator(SameFrameEvaluator):
            """第at次normalize抛出内建ValueError，其余调用原实现。"""
            calls = 0

            def normalize(self, values):
                """参数为解码值；按序号抛错或原样归一化；返回原结果；异常: 注入ValueError。"""
                type(self).calls += 1
                if type(self).calls == at:
                    raise ValueError('注入的归一化错误')
                return super().normalize(values)
        return FailingEvaluator

    def test_points_packets_limits_facts_and_finish(self):
        """3000个不同时刻的目标帧分成2048和952两包组点，块号连续，末包为EOF并带最终事实，随后确认释放。"""
        messages, packets, budget = self.run_worker(self.asc('many.asc', 3000), 2)
        self.assertEqual([len(packet.events) for packet in packets], [2048, 952])
        self.assertEqual([packet.number for packet in packets], [0, 1])
        self.assertEqual([packet.eof for packet in packets], [False, True])
        events = [event for packet in packets for event in packet.events]
        self.assertEqual([event.time_ns for event in events], [i * 1000000 for i in range(3000)])
        self.assertEqual([event.first_values[0].value for event in events[:12]], [float(i % 10) for i in range(12)])
        final = packets[-1].facts
        self.assertEqual((final['count'], final['frame_identity'], final['first_ns'], final['last_ns']),
                         (3000, (False, False), 0, 2999000000))
        self.assertEqual([message[0] for message in messages], ['ready', 'block', 'block', 'finished'])
        self.assertEqual(budget.ram_bytes, 0)

    def test_deferred_error_keeps_reading_to_eof(self):
        """第2帧延迟错误后不再交付组点，但读取器读完全部20帧；末包含延迟错误并正常确认释放。"""
        messages, packets, budget = self.run_worker(self.asc('deferred.asc', 20), 1, evaluator=self.failing_evaluator(2))
        events = [event for packet in packets for event in packet.events]
        self.assertEqual(events[0].time_ns, 0)
        self.assertEqual(events[1], DeferredPointError(1000000, ValueError, '注入的归一化错误'))
        self.assertEqual(len(events), 2)
        self.assertEqual(packets[-1].facts['count'], 20)
        self.assertTrue(packets[-1].eof)
        self.assertEqual(messages[-1][0], 'finished')
        self.assertEqual(budget.ram_bytes, 0)

    def test_later_bad_line_after_deferred_error_is_reported_without_notes(self):
        """延迟错误之后同一文件的坏行仍作为读取错误报出，文本只含str(错误)。"""
        messages, packets, budget = self.run_worker(self.asc('bad.asc', 20, bad=True), 2,
                                                    evaluator=self.failing_evaluator(2))
        self.assertTrue(any(type(event) is DeferredPointError for packet in packets for event in packet.events))
        self.assertEqual([message[0] for message in messages], ['ready', 'block', 'error'])
        error = messages[-1]
        self.assertEqual(error[3:5], ('read', 'CANTextError'))
        # 坏行在第22行（表头1行+20帧之后）；文本只含原错误，不附加说明。
        self.assertTrue(error[5].endswith('bad.asc:22: ASC时间需要非负十进制秒'))
        self.assertNotIn('\n', error[5])
        self.assertEqual(budget.ram_bytes, 0)

    def test_take_events_points_uses_point_limit(self):
        """points封包按2048个事件切分，面积模式的128上限不影响组点。"""
        items = tuple((single(i, (number(1.),)), facts()) for i in range(MAX_POINTS + 5))
        events, remaining, _ = take_events(items, facts(), points=True)
        self.assertEqual((len(events), len(remaining)), (MAX_POINTS, 5))
        self.assertIs(events[0], items[0][0])


if __name__ == '__main__':
    unittest.main()
