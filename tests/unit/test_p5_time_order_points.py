"""PERF-P5-ORDER-01 C1/C2：time_order组点并行与串行time_order直接积分的逐位差分及失败、清理检查。

“串行”指把parallel_point_inputs替换为返回None后的现有路径（ParallelCANDecodeRead读取、主进程
SameFrameIntegrals积分），即本任务之前time_order直接积分的实际路径；另与显式reference普通路径对照。
期望值另按帧时刻手算。全部输入是本测试临时目录生成的小型ASC/BLF和合成DBC，不读取历史项目，不做性能计时。
"""
from contextlib import ExitStack
from copy import deepcopy
import importlib
import multiprocessing
import os
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.file_group_points import DeferredPointError, FileGroupPoints
from chronaxis.execution.file_integral_terms import SameTimeGroupSummary
from chronaxis.execution.integral_blocks import encode_points
from chronaxis.execution.parallel_point_pool import ParallelPointPool, PointSpool
from chronaxis.execution.parallel_point_session import ParallelPointSession
from chronaxis.execution.record_integral import RecordIntegral
from chronaxis.execution.same_frame_integrals import SameFrameIntegrals
from chronaxis.legacy.updates import LegacyDecodedUpdate
from chronaxis.results.budget import ResourceBudget

# 只导入模块，不把其中的TestCase类放进本模块名字空间，避免unittest重复收集并运行它们。
import test_p5_group_points as group_points
import test_p5_session_integrals as session_integrals
from test_p5_group_points import facts, number, single

POINT_SESSION = 'chronaxis.execution.parallel_point_session'


def _crash_worker(control, data):
    """测试用崩溃worker：正常回READY，收到首个next后立即以退出码3结束。

    参数: 两个端点。返回: 不返回。异常: 无（直接结束进程）。仅供spawn故障注入。
    """
    from chronaxis.execution.can_block_codec import encode_metadata
    from chronaxis.execution.parallel_can_worker import plain
    from chronaxis.sources.text_can_decode import CANTextDecodeRead
    while True:
        command = control.recv()
        if command[0] == 'close':
            return
        if command[0] == 'file':
            _, index, spec, signals, options, limit, *_ = command
            reader = CANTextDecodeRead(spec, ResourceBudget(limit), signals, **options)
            encoded = encode_metadata(plain(reader.prepare_metadata()))
            reader.close()
            control.send(('ready', index, os.getpid(), len(encoded)))
            data.send_bytes(encoded)
        elif command[0] == 'budget':
            control.maximum = command[1]
        elif command[0] == 'next':
            os._exit(3)


class TimeOrderPointsPublicTests(unittest.TestCase):
    """从公开AnalysisRunner核对新路径与串行路径的完整结果行、错误和资源清理。"""

    def setUp(self):
        """参数无；复用连续积分测试的DBC与ASC/BLF生成辅助；记录已有子进程。"""
        self.h = session_integrals.P5SessionIntegralTests('test_actual_zoh_asc_blf_and_mixed_files')
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.children = {process.pid for process in multiprocessing.active_children()}

    def tearDown(self):
        """参数无；断言没有遗留本测试启动的子进程。"""
        self.assertEqual({process.pid for process in multiprocessing.active_children()} - self.children, set())

    def config(self, paths, **options):
        """生成time_order公开配置。参数: 路径与config选项。返回: dict。异常: 无。"""
        return self.h.config(paths, merge='time_order', **options)

    def counted(self):
        """返回(补丁上下文, 计数)；统计组点会话与连续面积会话的成功执行次数。"""
        points = importlib.import_module(POINT_SESSION).ParallelPointSession
        terms = importlib.import_module('chronaxis.execution.parallel_integral_session').ParallelIntegralSession
        counts = dict(points=0, terms=0)
        stack = ExitStack()
        for name, owner in (('points', points), ('terms', terms)):
            original = owner.execute
            def execute(session, *args, _original=original, _name=name, **kwargs):
                """原execute成功返回后计数。"""
                result = _original(session, *args, **kwargs)
                counts[_name] += 1
                return result
            stack.enter_context(patch.object(owner, 'execute', execute))
        return stack, counts

    def serial_patch(self):
        """返回使组点路径不适用的补丁，运行即走本任务之前的串行time_order直接积分。"""
        return patch(POINT_SESSION + '.parallel_point_inputs', lambda plan: None)

    def compare(self, raw, *, processes=(1, 4), expected=None):
        """新路径与同进程数串行路径、显式reference普通路径完整行逐位相同，且确实走了新路径。

        参数: raw为time_order配置；processes为要对照的进程上限；expected为手算值或None（不核数值）。
        返回: 最后一个进程数的新路径结果行。异常: 断言失败。
        """
        rows = None
        reference = self.h.run_rows(raw, backend='reference')
        for count in processes:
            changed = deepcopy(raw)
            changed['execution']['process_count'] = count
            stack, counts = self.counted()
            with stack:
                rows = self.h.run_rows(changed)
            self.assertEqual(counts, dict(points=1, terms=0), count)
            with self.serial_patch():
                serial = self.h.run_rows(changed)
            self.assertEqual(rows, serial, count)
            self.assertEqual(rows, reference, count)
        if expected is not None:
            self.assertEqual(rows[0].value, expected)
        return rows

    def compare_failure(self, raw, *, processes=(1, 4), serial_processes=None):
        """新路径的完整异常链文本与串行路径相同。

        参数: raw为会失败的配置；processes为新路径进程上限；serial_processes为串行对照的进程上限，
            None表示与新路径相同（多文件读取错误按文件序号报告时用1进程串行作对照）。
        返回: 最后一次失败文本。异常: 断言失败。
        """
        message = None
        for count in processes:
            changed = deepcopy(raw)
            changed['execution']['process_count'] = count
            message = self.h.failure(changed)
            serial = deepcopy(raw)
            serial['execution']['process_count'] = count if serial_processes is None else serial_processes
            with self.serial_patch():
                expected = self.h.failure(serial)
            self.assertEqual(message, expected, count)
        return message

    def test_overlap_shapes_match_serial_reference_and_hand_values(self):
        """小重叠、完全包含、后文件整体更早、三文件同一时刻和无重叠，在实际间隔下逐位相同。

        三文件同刻：0.25s三个文件各一帧，last_by_sequence取第三个文件的400V×30A；
        手算(4000×.25)+(12000×.25)=4000J。无重叠时还应等于concatenate并行结果。
        """
        f = self.h.source_file
        shapes = dict(
            small=[f('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'), (.5, 256, b'\xc8\x10'))),
                   f('asc', ((.375, 256, b'\xc8\x14'), (.5, 256, b'\xc8\x16'), (.75, 512, b'\x00')))],
            contained=[f('asc', tuple((i / 8, 256, bytes((200, 10 + i))) for i in range(9))),
                       f('asc', ((.25, 256, b'\xc8\x30'), (.3125, 256, b'\xc8\x31'), (.5, 256, b'\xc8\x32')))],
            earlier=[f('asc', ((.5, 256, b'\xc8\x0a'), (.625, 256, b'\xc8\x0c'), (.75, 512, b'\x00'))),
                     f('asc', ((0., 256, b'\xc8\x14'), (.125, 256, b'\xc8\x16'), (.25, 256, b'\xc8\x18')))],
            three=[f('asc', ((0., 256, b'\xc8\x0a'), (.25, 256, b'\xc8\x0b'))),
                   f('asc', ((.25, 256, b'\xc8\x0c'),)),
                   f('asc', ((.25, 256, b'\xc8\x1e'), (.5, 512, b'\x00')))],
            disjoint=self.h.standard_files())
        for name, paths in shapes.items():
            with self.subTest(shape=name):
                raw = self.config(paths, policy='last_by_sequence')
                rows = self.compare(raw, processes=(1, 2, 4) if name == 'three' else (1, 4),
                                    expected=4000. if name == 'three' else None)
                if name == 'disjoint':
                    concatenated = self.h.config(paths, processes=4, policy='last_by_sequence')
                    self.assertEqual(rows, self.h.run_rows(concatenated))
                    self.assertEqual(rows[0].value, 2700.)

    def test_fixed_dbc_and_formats_match_serial(self):
        """固定125ms与DBC周期（GenMsgCycleTime=125ms）在ASC、BLF与混合格式的重叠输入上逐位相同。"""
        for kinds in (('asc', 'asc'), ('blf', 'blf'), ('asc', 'blf')):
            paths = [self.h.source_file(kinds[0], ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'), (.5, 256, b'\xc8\x10'))),
                     self.h.source_file(kinds[1], ((.375, 256, b'\xc8\x14'), (.5, 256, b'\xc8\x16'), (.75, 512, b'\x00')))]
            for mode in ('actual', 'fixed', 'dbc'):
                with self.subTest(kinds=kinds, mode=mode):
                    self.compare(self.config(paths, mode=mode, policy='last_by_sequence'),
                                 processes=(1, 4) if kinds == ('asc', 'asc') else (4,))

    def test_cross_file_same_time_last_uses_merge_order(self):
        """前文件含无关原帧、后文件局部序号0与前文件末组同刻：取后文件值，手算4500J（A1-4）。"""
        for kind in ('asc', 'blf'):
            first = self.h.source_file(kind, ((0., 256, b'\xc8\x0a'), (.03125, 512, b'\x00'),
                (.0625, 512, b'\x00'), (.09375, 512, b'\x00'), (.125, 256, b'\xc8\x0c')))
            second = self.h.source_file(kind, ((.125, 256, b'\xc8\x14'), (.25, 256, b'\xc8\x1e'), (.5, 512, b'\x00')))
            with self.subTest(kind=kind):
                self.compare(self.config([first, second], policy='last_by_sequence'), expected=4500.)

    def test_same_time_error_policy_conflicts_match_serial(self):
        """跨文件冲突、文件内冲突、两信号同时冲突（报先声明的voltage）及第三个文件冲突，错误链与串行相同。"""
        f = self.h.source_file
        cases = dict(
            cross=[f('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'))),
                   f('asc', ((.125, 256, b'\xc8\x0d'), (.5, 512, b'\x00')))],
            inside=[f('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'), (.125, 256, b'\xc8\x0e'))),
                    f('asc', ((.25, 256, b'\xc8\x0c'),))],
            both=[f('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'))),
                  f('asc', ((.125, 256, b'\xc9\x14'), (.5, 512, b'\x00')))],
            third=[f('asc', ((0., 256, b'\xc8\x0a'), (.25, 256, b'\xc8\x0b'))),
                   f('asc', ((.25, 256, b'\xc8\x0b'),)),
                   f('asc', ((.25, 256, b'\xc8\x1e'),))])
        for name, paths in cases.items():
            with self.subTest(case=name):
                message = self.compare_failure(self.config(paths))
                self.assertIn('同信号同时间冲突', message)
                self.assertIn('voltage' if name == 'both' else 'current', message)

    def test_ttl_domain_invalid_empty_and_no_target_match_serial(self):
        """空文件、无目标文件、TTL截止、domain裁剪、全空观测与单组文件，在新路径上与串行逐位相同。"""
        f = self.h.source_file
        paths = [f('asc', ((0., 256, b'\xc8\x0a'),)), f('asc', ()), f('asc', ((.125, 512, b'\x00'),)),
                 f('asc', ((.25, 256, b'\xc8\x0c'),)), f('asc', ((.5, 512, b'\x00'),))]
        for ttl, domain, value in (('1s', None, 2200.), ('0.1875s', None, 1650.),
                                   ('0.1875s', {'start': '0.0625s', 'end': '0.4375s'}, 1400.)):
            with self.subTest(ttl=ttl, domain=domain):
                self.compare(self.config(paths, ttl=ttl, domain=domain), expected=value)
        empty, no_target = f('asc', ()), f('asc', ((0., 512, b'\x00'), (.5, 512, b'\x00')))
        single_group = f('asc', ((0., 256, b'\xc8\x0a'),))
        for group in ([empty, empty], [empty, no_target], [single_group, empty]):
            with self.subTest(paths=len(group)):
                rows = self.compare(self.config(group))
                self.assertIsNone(rows[0].value)

    def test_frame_identity_errors_and_notices_match_serial(self):
        """DBC标FD且未写is_fd：跨文件FD与经典帧混用报同一错误（A1-6）；显式经典帧的兼容提示与串行相同。"""
        import can
        with self.h.dbc.open('a', encoding='utf-8') as stream:
            stream.write('BA_DEF_ BO_ "VFrameFormat" ENUM "StandardCAN","ExtendedCAN",'
                '"reserved","J1939PG","reserved","reserved","reserved","reserved",'
                '"reserved","reserved","reserved","reserved","reserved","reserved",'
                '"StandardCAN_FD","ExtendedCAN_FD";\n'
                'BA_DEF_DEF_ "VFrameFormat" "StandardCAN";\nBA_ "VFrameFormat" BO_ 256 14;\n')

        def blf(name, rows):
            """写BLF。参数: 文件名、(秒, 字节, FD)行。返回: 路径项。异常: 写入错误。"""
            path = self.h.root / (name + '.blf')
            writer = can.BLFWriter(path)
            try:
                for second, data, fd in rows:
                    writer.on_message_received(can.Message(timestamp=1700000000. + second, arbitration_id=256,
                        is_extended_id=False, is_fd=fd, channel=0, data=data))
            finally:
                writer.stop()
            return dict(path=str(path), offset='-1700000000s')
        fd = ((0., b'\xc8\x0a', True), (.125, b'\xc8\x0c', True))
        classic = ((.375, b'\xc8\x14', False), (.5, b'\xc8\x14', False))
        for label, first, second in (('fd_classic', fd, classic),
                                     ('classic_fd', tuple((t - .375, d, False) for t, d, _ in classic),
                                      tuple((t + .375, d, True) for t, d, _ in fd))):
            paths = [blf(label + '-a', first), blf(label + '-b', second)]
            for pure in (True, False):
                with self.subTest(label=label, pure=pure):
                    raw = self.h.pure_blf_config(paths) if pure else self.config(paths)
                    raw['sources'][0]['file_merge'] = 'time_order'
                    message = self.compare_failure(raw)
                    self.assertIn('同一报文绑定匹配多种实际帧，请补充 is_fd', message)
        paths = self.h.standard_files('blf')
        for count in (1, 4):
            raw = self.h.pure_blf_config(paths, processes=count)
            raw['sources'][0]['file_merge'] = 'time_order'
            for signal in raw['signals']:
                signal['field'].update(is_fd=False, is_extended=False)
            with self.subTest(processes=count):
                stack, counts = self.counted()
                with stack:
                    actual = self.h.run_rows(raw, notices=True)
                self.assertEqual(counts['points'], 1)
                with self.serial_patch():
                    self.assertEqual(actual, self.h.run_rows(raw, notices=True))
                self.assertEqual(len(actual[1]), 2)

    def test_selection_conditions(self):
        """time_order多文件1/4进程走组点路径；concatenate仍走面积路径；单文件、显式reference和带条件积分都不走。"""
        paths = self.h.standard_files()
        for merge, count, expected in (('time_order', 1, dict(points=1, terms=0)),
                                       ('time_order', 4, dict(points=1, terms=0)),
                                       ('concatenate', 4, dict(points=0, terms=1)),
                                       ('concatenate', 1, dict(points=0, terms=0))):
            with self.subTest(merge=merge, processes=count):
                stack, counts = self.counted()
                with stack:
                    self.h.run_rows(self.h.config(paths, processes=count, merge=merge))
                self.assertEqual(counts, expected)
        others = [self.config(paths[:1], processes=4)]
        conditioned = self.config(paths, processes=4)
        conditioned['calculations'][0]['condition'] = 'current > 0'
        others.append(conditioned)
        for raw, backend in ((others[0], None), (self.config(paths, processes=4), 'reference'), (others[1], None)):
            with self.subTest(backend=backend, condition='condition' in raw['calculations'][0]):
                stack, counts = self.counted()
                with stack:
                    self.h.run_rows(raw, backend=backend)
                self.assertEqual(counts, dict(points=0, terms=0))

    def test_read_phase_errors_precede_merge_phase_and_report_smallest_file(self):
        """前文件同刻冲突+后文件坏行报坏行（E3）；两文件都坏时报序号小的文件（E2，以1进程串行为准）；
        文件内时间回退按读取错误报出。"""
        f = self.h.source_file
        conflict = f('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'), (.125, 256, b'\xc9\x0c')),
                     name='conflict-first')
        bad = f('asc', ((.1875, 256, b'\xc8\x0a'),), name='bad-second', trailing='0.250 1 100 Rx d 2 GG 0A\n')
        message = self.compare_failure(self.config([conflict, bad]))
        self.assertIn('bad-second.asc', message)
        earlier = f('asc', tuple((i / 1024, 256, b'\xc8\x0a') for i in range(3000)), name='earlier',
                    trailing='3.000 1 100 Rx d 2 C8 ZZ\n')
        later = f('asc', (), name='later', trailing='0.250 1 100 Rx d 2 GG 0A\n')
        message = self.compare_failure(self.config([earlier, later]), processes=(1, 4), serial_processes=1)
        self.assertIn('earlier.asc', message)
        self.assertNotIn('later.asc', message)
        backwards = f('asc', (), name='backwards', trailing='0.500 1 100 Rx d 2 C8 0A\n0.250 1 100 Rx d 2 C8 0A\n')
        message = self.compare_failure(self.config([self.h.standard_files()[0], backwards]))
        self.assertIn('backwards.asc', message)

    def test_spool_quota_fails_without_leftovers(self):
        """暂存配额不足时新路径失败，不发布结果、不残留工作目录；串行路径同样因配额失败。"""
        raw = self.config(self.h.standard_files(), processes=4)
        raw['execution']['spool_quota_bytes'] = 64
        message = self.h.failure(raw)
        self.assertIn('spool_quota_bytes', message)
        with self.serial_patch():
            self.assertIn('spool_quota_bytes', self.h.failure(raw))

    def test_budget_fallbacks_happen_before_first_read_grant(self):
        """启动前下界或READY后报价超预算时沿用串行路径：不发next许可，结果与串行相同。"""
        from chronaxis._control_wire import ControlChannel
        raw = self.config(self.h.standard_files(), processes=4)
        with self.serial_patch():
            expected = self.h.run_rows(raw)
        commands = []
        original = ControlChannel.send

        def record_send(channel, message):
            """记录积分族命令后原样发送；首帧许可出现即断言失败。"""
            if channel.family == 'integral':
                commands.append(message[0])
                self.assertNotEqual(message[0], 'next', '预算未通过却授予读取许可')
            return original(channel, message)
        for target, value in (('points_minimum_cost', 2**62), ('configuration_cost', 2**62)):
            commands.clear()
            with self.subTest(target=target):
                with patch.object(ControlChannel, 'send', record_send), \
                        patch.object(ParallelPointPool, target, lambda *args, **kwargs: value):
                    stack, counts = self.counted()
                    with stack:
                        actual = self.h.run_rows(raw)
                self.assertEqual(actual, expected)
                self.assertEqual(counts['points'], 0)
                self.assertNotIn('configure', commands)
                if target == 'points_minimum_cost':
                    self.assertNotIn('file', commands)

    def test_cancel_and_worker_exit_clean_up(self):
        """暂存写入时取消与工作进程意外退出：都失败、不残留子进程和工作目录。"""
        raw = self.config(self.h.standard_files(), processes=4)
        work = self.h.root / 'cancel-work'
        with patch.object(PointSpool, 'append', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                from chronaxis import AnalysisPlan, AnalysisRunner
                with AnalysisRunner().run(AnalysisPlan.from_dict(deepcopy(raw)), work_dir=work):
                    self.fail('取消后不应发布结果')
        self.assertFalse(work.exists())
        with patch('chronaxis.execution.parallel_integral_pool.worker_main', _crash_worker):
            message = self.h.failure(raw)
        self.assertIn('积分工作进程意外退出', message)
        self.assertIn('退出码3', message)


class PointMergeTests(unittest.TestCase):
    """直接调用归并段，核对合并、帧型与延迟错误的先后，以及与串行同帧积分逐位相同。"""

    def setUp(self):
        """参数无；建立临时工作目录与两信号任务。"""
        self.temporary = tempfile.TemporaryDirectory(prefix='chronaxis-p5-merge-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.helper = group_points.FileGroupPointsTests('test_budget_matches_estimate_and_close_is_idempotent')

    def integrals(self, budget, definitions, expressions, binding, *, step=None, size=4):
        """建立RecordIntegral与SameFrameIntegrals。参数: 预算、声明、绑定、间隔、批上限。返回: (owner, 积分器)。"""
        spec = CalculationDefinition('energy', 'integral', Interval(0, 10**9))
        calculation = RecordIntegral(budget, spec, expressions[0].root.unit, expressions[0].root.dtype, step,
                                     backend='reference', batch_intervals=size)
        self.addCleanup(calculation.close)
        owner = SameFrameIntegrals(budget, definitions, expressions, (calculation,), binding, 'session', lambda: None)
        self.addCleanup(owner.close)
        return owner, calculation

    def merge(self, files, identities=None, *, policies=('last_by_sequence', 'last_by_sequence'), step=None, end=None):
        """把每个文件的帧经FileGroupPoints、P5G1包和暂存交给_merge，再完成积分。

        参数: files为每个文件的(时间, 电压, 电流)行list；identities为各文件实际帧型，None表示全为经典帧；
            policies为两信号同刻政策；step为固定间隔纳秒或None；end为观测末端。
        返回: RecordIntegralResult。异常: 归并段的原错误。
        """
        budget, definitions, expressions, specs, binding = self.helper.task(policies=policies)
        owner, calculation = self.integrals(budget, definitions, expressions, binding, step=step)
        spool = PointSpool(budget, self.root, len(files))
        self.addCleanup(spool.close)
        for index, rows in enumerate(files):
            worker = FileGroupPoints(budget, definitions, expressions, specs, binding, 'session')
            events = self.helper.feed_all(worker, definitions, rows)
            worker.close()
            spool.append(index, encode_points(index, 0, tuple(events), True, facts((False, False))))
        spool.open_readers()
        session = SimpleNamespace(_definitions=definitions, _spool=spool, _owner=owner, timings=dict(groups=0))
        ParallelPointSession._merge(session, identities or ((False, False),) * len(files))
        owner.finish(end)
        return calculation.finish()

    def serial(self, files, *, policies=('last_by_sequence', 'last_by_sequence'), step=None, end=None):
        """把同样的帧按串行time_order顺序（时间、文件位置、文件内原序号）逐帧交给SameFrameIntegrals。

        参数: 同merge。返回: RecordIntegralResult。异常: 原错误。
        """
        budget, definitions, expressions, _, binding = self.helper.task(policies=policies)
        owner, calculation = self.integrals(budget, definitions, expressions, binding, step=step)
        merged = sorted((time, index, local, voltage, current) for index, rows in enumerate(files)
                        for local, (time, voltage, current) in enumerate(rows))
        for sequence, (time, _, _, voltage, current) in enumerate(merged):
            owner.consume(LegacyDecodedUpdate(time, 'bus', 0, 256, False, False, False, False,
                SourceRef('session', 'bus', 'voltage'), sequence, sequence, {'Voltage': voltage, 'Current': current}))
        owner.finish(end)
        return calculation.finish()

    def test_random_overlapping_files_match_serial_bitwise(self):
        """随机3—4个文件、时间大量重叠且有同刻帧，实际间隔与固定间隔下结果逐位相同（批上限4，跨多批）。

        电压可取None（归一化为MISSING无效值），覆盖无效值在同刻选择和积分中的处理。
        """
        generator = random.Random(20261121)
        for trial in range(40):
            files = []
            for _ in range(generator.randint(3, 4)):
                times = sorted(generator.randrange(0, 60) * 7 for _ in range(generator.randint(0, 25)))
                files.append([(time, generator.choice((1.5, 2.25, -3., None, float.fromhex('0x1.0000000000001p+0'))),
                               generator.choice((10., .1, 7.))) for time in times])
            end = max((row[0] for rows in files for row in rows), default=0) + 11
            for step in (None, 5):
                with self.subTest(trial=trial, step=step):
                    self.assertEqual(self.merge(files, step=step, end=end), self.serial(files, step=step, end=end))

    def test_deferred_error_and_identity_order(self):
        """延迟错误以原类型在归并位置报出；之前已合并部分的冲突先报；首事件先核跨文件帧型。"""
        budget, definitions, expressions, specs, binding = self.helper.task()
        values = (number(1.), number(2.))
        other = (number(1.), number(3.))

        def run(events_by_file, identities):
            """把手写事件写入暂存并归并。参数: 每文件事件tuple、帧型。返回: None。异常: 归并原错误。"""
            owner, _ = self.integrals(budget, definitions, expressions, binding)
            spool = PointSpool(budget, self.root, len(events_by_file))
            self.addCleanup(spool.close)
            for index, events in enumerate(events_by_file):
                spool.append(index, encode_points(index, 0, events, True, facts(identities[index])))
            spool.open_readers()
            session = SimpleNamespace(_definitions=definitions, _spool=spool, _owner=owner, timings=dict(groups=0))
            try:
                ParallelPointSession._merge(session, identities)
            finally:
                spool.close()
        classic, fd = (False, False), (False, True)
        with self.assertRaises(TypeError) as raised:
            run(((single(0, values), single(5, values)), (DeferredPointError(5, TypeError, '原文'),)), (classic, classic))
        self.assertEqual(str(raised.exception), '原文')
        conflicted = SameTimeGroupSummary(5, 0, 1, 2, values, other, (None, 1))
        with self.assertRaisesRegex(ValueError, '同信号同时间冲突：current@5ns'):
            run(((conflicted,), (DeferredPointError(5, ValueError, '后到'),)), (classic, classic))
        with self.assertRaisesRegex(ValueError, '同一报文绑定匹配多种实际帧，请补充 is_fd'):
            run(((single(0, values), single(3, values)), (single(3, values),)), (classic, fd))
        with self.assertRaisesRegex(ValueError, '同信号同时间冲突'):
            run(((single(0, values), conflicted), (single(5, values),)), (classic, fd))

    def test_spool_cleanup_keeps_foreign_files(self):
        """只删除登记的暂存文件；目录中有外来文件时rmdir失败并保留外来文件，删掉后可重试关闭。"""
        budget = ResourceBudget()
        spool = PointSpool(budget, self.root, 1)
        spool.append(0, encode_points(0, 0, (single(0, (number(1.),)),), True, facts()))
        root = spool._root
        foreign = root / 'foreign.txt'
        foreign.write_text('keep', encoding='utf-8')
        with self.assertRaises(OSError):
            spool.close()
        self.assertTrue(foreign.exists())
        self.assertFalse((root / '0.points').exists())
        foreign.unlink()
        spool.close()
        self.assertFalse(root.exists())
        self.assertEqual(budget.ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
