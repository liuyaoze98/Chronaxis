"""从公开运行器核验连续文件积分，独立手算边界，不进行性能计时。

全部输入由小型ASC/BLF和合成DBC生成，不读取历史项目。单进程结果用于完整行
对照，面积预期另按给定帧时刻手算；结构测试只监测P5入口类，不依赖传输私有属性。
"""

from copy import deepcopy
from pathlib import Path
import importlib
import json
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.types import QualityFlag
from chronaxis.results.errors import AnalysisError


class P5SessionIntegralTests(unittest.TestCase):
    """同一连续会话在1/4进程下应保留面积、状态、质量和原错误顺序。"""

    def setUp(self):
        """参数无；建立自有临时目录与DBC；依赖或写入失败原样传播。"""
        self.temporary = tempfile.TemporaryDirectory(prefix='chronaxis-p5-session-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.dbc = self.root / 'signals.dbc'
        self.dbc.write_text(
            'VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 PowerFrame: 2 Node\n'
            ' SG_ Voltage : 0|8@1+ (2,0) [0|510] "V" Node\n'
            ' SG_ Current : 8|8@1+ (1,0) [0|255] "A" Node\n'
            'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 100000;\n'
            'BA_ "GenMsgCycleTime" BO_ 256 125;\n', encoding='utf-8')

    def source_file(self, kind, rows, *, name=None, trailing=''):
        """参数为格式及(秒,ID,字节)记录；返回公开paths项；写入错误直接传播。

        BLF使用真实绝对日期并通过显式文件偏移映射到本例相对秒，不手工替换typed计划。
        """
        path = self.root / ((name or uuid4().hex) + '.' + kind)
        if kind == 'asc':
            body = ''.join(f'{second:.12f} 1 {identifier:X} Rx d {len(data)} '
                           + ' '.join(f'{byte:02X}' for byte in data) + '\n'
                           for second, identifier, data in rows)
            path.write_text('base hex timestamps absolute\n' + body + trailing, encoding='utf-8')
            return str(path)
        if kind != 'blf':
            raise ValueError('测试仅生成ASC或BLF')
        import can
        writer = can.BLFWriter(path)
        try:
            for second, identifier, data in rows:
                writer.on_message_received(can.Message(timestamp=1700000000. + second,
                    arbitration_id=identifier, is_extended_id=False, channel=0, data=data))
        finally:
            writer.stop()
        return dict(path=str(path), offset='-1700000000s')

    def config(self, paths, *, processes=1, policy='error', ttl='1s', domain=None,
               mode='actual', merge='concatenate'):
        """参数控制连续输入/进程/有效期等公开字段；返回新配置；不读取数据文件。"""
        dataset = dict(name='p5_continuous')
        if domain is not None:
            dataset['domain'] = domain
        interval = dict(mode=mode)
        if mode != 'actual':
            interval['driver'] = 'current'
        if mode == 'fixed':
            interval['value'] = '0.125s'
        return dict(config_version=4, dataset=dataset,
            sources=[dict(name='bus', paths=deepcopy(paths), file_merge=merge,
                          dbc_by_channel={'1': str(self.dbc)})],
            signals=[dict(name=name, source='bus', dtype='float64', valid_for=ttl,
                          same_time_policy=policy, field=dict(frame_id='0x100', signal=signal))
                     for name, signal in (('voltage', 'Voltage'), ('current', 'Current'))],
            calculations=[dict(name='energy', operation='integral', expr='voltage * current',
                               unit='J', scope='session')],
            intervals=dict(default=interval),
            execution=dict(backend='auto', process_count=processes), outputs=dict(tables='jsonl'))

    def run_rows(self, raw, *, backend=None, notices=False):
        """参数为配置、后端及提示开关；返回完整行或(行,帧型提示)；清理失败或原错传播。"""
        work = self.root / ('work-' + uuid4().hex)
        result = AnalysisRunner(backend).run(AnalysisPlan.from_dict(deepcopy(raw)), work_dir=work)
        try:
            rows = tuple(result.iter_calculations())
            frame_notices = result.metadata.frame_format_notices
            self.assertEqual(set(result.spool.counts), {'calculations'})
            budget = result.spool.budget
        finally:
            result.close()
        self.assertEqual(budget.ram_bytes, 0)
        self.assertFalse(work.exists())
        return (rows, frame_notices) if notices else rows

    def compare(self, raw, expected, *, status=None, quality=None):
        """参数为同会话配置和手算值；对照1/4进程完整行；返回并行行，差异抛断言。"""
        rows = []
        for count in (1, 4):
            changed = deepcopy(raw)
            changed['execution']['process_count'] = count
            rows.append(self.run_rows(changed))
        self.assertEqual(rows[0], rows[1])
        energy, = rows[1]
        if expected is None:
            self.assertIsNone(energy.value)
        else:
            self.assertEqual(energy.value, expected)
        if status is not None:
            self.assertEqual(energy.status, status)
        if quality is not None:
            self.assertTrue(energy.quality & quality)
        return rows[1]

    def paths_used(self):
        """返回(补丁上下文, 计数dict)；统计直接同帧积分构造次数和并行积分成功执行次数。

        只包住原构造/执行并原样返回结果；prepare后回退到普通路径的并行会话不计为执行。
        """
        from contextlib import ExitStack
        session = importlib.import_module('chronaxis.execution.parallel_integral_session').ParallelIntegralSession
        direct = importlib.import_module('chronaxis.execution.same_frame_integrals').SameFrameIntegrals
        counts = dict(direct=0, parallel=0)
        original_init, original_execute = direct.__init__, session.execute
        def construct(owner, *args, **kwargs):
            """记录一次直接同帧积分构造，再调用原实现。"""
            counts['direct'] += 1
            return original_init(owner, *args, **kwargs)
        def execute(owner, *args, **kwargs):
            """原execute成功返回后才记录并行执行。"""
            result = original_execute(owner, *args, **kwargs)
            counts['parallel'] += 1
            return result
        stack = ExitStack()
        stack.enter_context(patch.object(direct, '__init__', construct))
        stack.enter_context(patch.object(session, 'execute', execute))
        return stack, counts

    def compare_general(self, raw, expected, *, status=None, quality=None, paths=(1, 1)):
        """1/4进程完整行须与显式reference普通路径逐行一致，并确认实际走过的路径。

        参数: 配置、手算值或None、可选状态/质量；paths为(直接同帧积分构造次数,
            并行积分成功执行次数)，默认(1,1)即1进程走直接路径、4进程走并行路径。
        返回: 并行行。异常: 断言失败。
        """
        stack, counts = self.paths_used()
        with stack:
            rows = self.compare(raw, expected, status=status, quality=quality)
            used = dict(counts)
            general = self.run_rows(raw, backend='reference')
        self.assertEqual(rows, general)
        self.assertEqual(used, dict(direct=paths[0], parallel=paths[1]))
        return rows

    def failure(self, raw, backend=None):
        """参数为错误配置及可选后端；返回真实异常链文本；若错误未发生或暂存残留则断言失败。"""
        work = self.root / ('failed-' + uuid4().hex)
        with self.assertRaises(AnalysisError) as caught:
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(deepcopy(raw)), work_dir=work):
                self.fail('失败输入被发布为成功结果')
        parts, seen = [], set()
        error = caught.exception
        while error is not None and id(error) not in seen:
            seen.add(id(error))
            parts.append(type(error).__name__ + ': ' + str(error))
            error = error.__cause__
        self.assertFalse(work.exists())
        return '\n'.join(parts)

    def standard_files(self, kind='asc'):
        """参数为ASC/BLF；返回两连续分卷；4000×.125+4800×.25+8000×.125=2700J。"""
        return [self.source_file(kind, ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'))),
                self.source_file(kind, ((.375, 256, b'\xc8\x14'), (.5, 512, b'\x00')))]

    def pure_blf_config(self, paths, *, policy='strict', processes=1):
        """参数为BLF路径项、解码政策和进程上限；返回纯can_blf公开配置；不更改typed计划。"""
        raw = self.config([entry['path'] for entry in paths], processes=processes)
        raw['sources'][0].update(source_type='can_blf',
            time=dict(time_type='relative', unit='s', clock='p5_fixture', offset='-1700000000s'),
            reader=dict(decode_policy=policy))
        return raw

    def test_actual_zoh_asc_blf_and_mixed_files(self):
        """两格式和混合来源均在文件边界延续上一功率，手算2700J。"""
        for kinds in (('asc', 'asc'), ('blf', 'blf'), ('asc', 'blf')):
            paths = [self.source_file(kinds[0], ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'))),
                     self.source_file(kinds[1], ((.375, 256, b'\xc8\x14'), (.5, 512, b'\x00')))]
            with self.subTest(kinds=kinds):
                self.compare(self.config(paths), 2700., status='complete')

    def test_cross_file_ttl_domain_empty_and_no_target(self):
        """空文件和无目标文件不切断保持；TTL及domain仍按实际时刻裁剪。"""
        for kind in ('asc', 'blf'):
            paths = [self.source_file(kind, ((0., 256, b'\xc8\x0a'),)),
                     self.source_file(kind, ()),
                     self.source_file(kind, ((.125, 512, b'\x00'),)),
                     self.source_file(kind, ((.25, 256, b'\xc8\x0c'),)),
                     self.source_file(kind, ((.5, 512, b'\x00'),))]
            for ttl, domain, value, status in (
                    ('1s', None, 2200., 'complete'),
                    ('0.1875s', None, 1650., 'partial'),
                    ('0.1875s', {'start': '0.0625s', 'end': '0.4375s'}, 1400., 'partial')):
                with self.subTest(kind=kind, ttl=ttl, domain=domain):
                    self.compare(self.config(paths, ttl=ttl, domain=domain), value, status=status)

    def test_all_empty_no_target_and_observed_tail(self):
        """空观测不造零值，单点不造面积；无关末帧仍给出真实EOF。"""
        empty = self.source_file('asc', ())
        no_target = self.source_file('asc', ((0., 512, b'\x00'), (.5, 512, b'\x00')))
        single = self.source_file('asc', ((0., 256, b'\xc8\x0a'),))
        tail = self.source_file('asc', ((.5, 512, b'\x00'),))
        for paths in ([empty, empty], [empty, no_target], [single, empty]):
            with self.subTest(paths=paths):
                self.compare(self.config(paths), None)
        self.compare(self.config([single, empty, tail], domain={'start': '0s', 'end': '1s'}), 2000.)

    def test_first_target_after_observation_is_partial(self):
        """前125ms无功率，之后375ms×4000W=1500J，不能把未知头部补成完整。"""
        paths = [self.source_file('asc', ((0., 512, b'\x00'),)),
                 self.source_file('asc', ((.125, 256, b'\xc8\x0a'), (.5, 512, b'\x00')))]
        rows = self.compare(self.config(paths), 1500., status='partial')
        # 起点前未知由覆盖状态表示；未见无效样本，不额外构造MISSING质量标记。
        self.assertEqual(rows[0].quality, QualityFlag.NONE)

    def test_cross_file_same_time_last_uses_global_original_sequence(self):
        """前文件含无关原帧，后文件本地序号0仍应覆盖前文件末组，面积4500J。"""
        for kind in ('asc', 'blf'):
            first = self.source_file(kind, ((0., 256, b'\xc8\x0a'), (.03125, 512, b'\x00'),
                (.0625, 512, b'\x00'), (.09375, 512, b'\x00'), (.125, 256, b'\xc8\x0c')))
            second = self.source_file(kind, ((.125, 256, b'\xc8\x14'),
                (.25, 256, b'\xc8\x1e'), (.5, 512, b'\x00')))
            with self.subTest(kind=kind):
                self.compare(self.config([first, second], policy='last_by_sequence'), 4500., status='complete')

    def test_cross_file_same_time_error_preserves_signal_order(self):
        """跨文件两信号均冲突时，按信号声明顺序首先报告voltage。"""
        paths = [self.source_file('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'))),
                 self.source_file('asc', ((.125, 256, b'\xc9\x14'), (.5, 512, b'\x00')))]
        for count in (1, 4):
            with self.subTest(processes=count):
                message = self.failure(self.config(paths, processes=count))
                self.assertIn('同信号同时间冲突', message)
                self.assertIn('voltage', message)

    def test_equal_cross_file_same_time_is_not_an_extra_interval(self):
        """完全相同的文件边界记录只形成一个时点，不能重复累计边界面积。"""
        first = self.source_file('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c')))
        second = self.source_file('asc', ((.125, 256, b'\xc8\x0c'), (.5, 512, b'\x00')))
        self.compare(self.config([first, second]), 2300., status='complete')

    def test_earlier_file_error_precedes_ready_later_file_error(self):
        """后文件较早可返回错误，也必须先交付前文件的原数据错误。"""
        first = self.source_file('asc', tuple((i/128, 256, b'\xc8\x0a') for i in range(16)),
            name='earlier', trailing='0.125 1 100 Rx d 2 C8 ZZ\n')
        second = self.source_file('asc', (), name='later', trailing='0.250 1 100 Rx d 2 GG 0A\n')
        for count in (1, 4):
            with self.subTest(processes=count):
                message = self.failure(self.config([first, second], processes=count))
                self.assertIn('earlier.asc', message)
                self.assertNotIn('later.asc', message)

    def test_boundary_conflict_precedes_later_data_error(self):
        """后文件首组先与前文件冲突，不能被其后坏行提前覆盖。"""
        first = self.source_file('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c')))
        second = self.source_file('asc', ((.125, 256, b'\xc9\x14'),),
            trailing='0.250 1 100 Rx d 2 GG 0A\n')
        for count in (1, 4):
            with self.subTest(processes=count):
                message = self.failure(self.config([first, second], processes=count))
                self.assertIn('同信号同时间冲突', message)
                self.assertIn('voltage', message)

    def test_subnanosecond_cross_file_regression_is_not_hidden_by_rounding(self):
        """两时刻舍入后同为125ms，精确来源时间回退仍须报错。"""
        first = self.source_file('asc', (), trailing='0.1250000004 1 100 Rx d 2 C8 0A\n')
        second = self.source_file('asc', (), trailing='0.1250000003 1 100 Rx d 2 C8 0A\n')
        for count in (1, 4):
            with self.subTest(processes=count):
                message = self.failure(self.config([first, second], processes=count))
                self.assertIn('时间回退', message)

    def test_time_order_keeps_existing_results(self):
        """时间归并不进入连续面积并行，结果不变。PERF-P5-ORDER-01起1/4进程都由组点并行会话完成，
        其主进程仍构造同一个直接同帧积分owner，所以计数为(2, 0)；组点路径的选择与差分见test_p5_time_order_points。"""
        paths = self.standard_files()
        self.compare_general(self.config(paths, merge='time_order'), 2700., paths=(2, 0))

    def test_fixed_and_dbc_match_general_path_across_formats(self):
        """固定125ms与DBC周期（测试DBC声明GenMsgCycleTime=125ms）：4000W与4800W两段各计一个周期得1100J；
        末条驱动后不补尾段，故覆盖不全。"""
        for mode in ('fixed', 'dbc'):
            for kinds in (('asc', 'asc'), ('blf', 'blf'), ('asc', 'blf')):
                paths = [self.source_file(kinds[0], ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'))),
                         self.source_file(kinds[1], ((.375, 256, b'\xc8\x14'), (.5, 512, b'\x00')))]
                with self.subTest(mode=mode, kinds=kinds):
                    self.compare_general(self.config(paths, mode=mode), 1100., status='partial')

    def test_fixed_and_dbc_cross_file_ttl_domain_same_time_and_invalid(self):
        """固定间隔与DBC周期下跨文件保持、有效期、domain、同刻覆盖和单点均与普通路径一致。

        功率记录0s=4000W、0.25s=4800W（中间隔空文件和无关帧），间隔125ms（DBC周期同为125ms）：
        有效期1s得4000×0.125=500J；有效期0.1875s截去该对后1/4，得375J；
        再加domain 0.0625—0.4375s只剩0.0625—0.1875s，得4000×0.125×0.125/0.25=250J。
        """
        for kind in ('asc', 'blf'):
            paths = [self.source_file(kind, ((0., 256, b'\xc8\x0a'),)),
                     self.source_file(kind, ()),
                     self.source_file(kind, ((.125, 512, b'\x00'),)),
                     self.source_file(kind, ((.25, 256, b'\xc8\x0c'),)),
                     self.source_file(kind, ((.5, 512, b'\x00'),))]
            for mode in ('fixed', 'dbc'):
                for ttl, domain, value in (('1s', None, 500.), ('0.1875s', None, 375.),
                                           ('0.1875s', {'start': '0.0625s', 'end': '0.4375s'}, 250.)):
                    with self.subTest(mode=mode, kind=kind, ttl=ttl, domain=domain):
                        self.compare_general(self.config(paths, ttl=ttl, domain=domain, mode=mode), value,
                                             status='partial')
            # 0.125s的前后文件同刻组按last_by_sequence取后文件8000W：4000×0.125+8000×0.125=1500J。
            first = self.source_file(kind, ((0., 256, b'\xc8\x0a'), (.0625, 512, b'\x00'),
                                            (.125, 256, b'\xc8\x0c')))
            second = self.source_file(kind, ((.125, 256, b'\xc8\x14'), (.25, 256, b'\xc8\x1e'),
                                             (.5, 512, b'\x00')))
            for mode in ('fixed', 'dbc'):
                with self.subTest(mode=mode, kind=kind, case='same_time'):
                    self.compare_general(self.config([first, second], policy='last_by_sequence', mode=mode), 1500.)
        # 单条功率记录不构成驱动对，固定间隔与DBC周期都不造面积，也不补到观测末端。
        paths = [self.source_file('asc', ((0., 512, b'\x00'),)),
                 self.source_file('asc', ((.125, 256, b'\xc8\x0a'), (.5, 512, b'\x00')))]
        for mode in ('fixed', 'dbc'):
            with self.subTest(mode=mode, case='single'):
                self.compare_general(self.config(paths, mode=mode), None)

    def test_fixed_and_dbc_multiplex_invalid_frame_is_a_driver_update(self):
        """无效子类型帧同样投影驱动字段并使当段无效：只计0—0.125s的500J，结果partial且含MISSING。

        DBC另声明125ms周期，使DBC周期与固定125ms得到同一手算值。
        """
        self.dbc.write_text(
            'VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 PowerFrame: 3 Node\n'
            ' SG_ Mux M : 0|8@1+ (1,0) [0|255] "" Node\n'
            ' SG_ Voltage m1 : 8|8@1+ (2,0) [0|510] "V" Node\n'
            ' SG_ Current m1 : 16|8@1+ (1,0) [0|255] "A" Node\n'
            'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 100000;\n'
            'BA_ "GenMsgCycleTime" BO_ 256 125;\n', encoding='utf-8')
        paths = [self.source_file('asc', ((0., 256, b'\x01\xc8\x0a'),)),
                 self.source_file('asc', ((.125, 256, b'\x02\xc8\x0a'),
                                          (.25, 256, b'\x01\xc8\x0c'), (.375, 512, b'\x00')))]
        for mode in ('fixed', 'dbc'):
            raw = self.config(paths, mode=mode)
            raw['sources'][0]['reader'] = dict(decode_policy='partial')
            with self.subTest(mode=mode):
                self.compare_general(raw, 500., status='partial', quality=QualityFlag.MISSING)

    def test_dbc_missing_cycle_reports_same_error_on_every_path(self):
        """DBC未声明报文周期时，各路径都在读取前报告同一缺周期错误，不猜周期。

        同一进程数下，auto（1进程直接积分、4进程并行积分）与显式reference普通路径的完整错误链相同；
        多进程读取在原因前附文件路径，这是普通多进程读取原有的包装，与新路径无关。
        """
        self.dbc.write_text(
            'VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 PowerFrame: 2 Node\n'
            ' SG_ Voltage : 0|8@1+ (2,0) [0|510] "V" Node\n'
            ' SG_ Current : 8|8@1+ (1,0) [0|255] "A" Node\n', encoding='utf-8')
        paths = self.standard_files()
        for count in (1, 4):
            with self.subTest(processes=count):
                selected = self.failure(self.config(paths, processes=count, mode='dbc'))
                general = self.failure(self.config(paths, processes=count, mode='dbc'), 'reference')
                self.assertIn('缺少cycle_time周期', selected)
                self.assertEqual(selected, general)

    def test_parallel_source_requests_dbc_driver_cycle_like_general_cursor(self):
        """并行读取的周期请求与普通游标相同：先列DBC驱动字段，再列未填有效期的字段；无DBC间隔时不加驱动。"""
        from chronaxis.execution.parallel_integral_session import parallel_integral_source
        from chronaxis.planning.input_requirements import collect_input_requirements
        from chronaxis.sources.can_spec import can_field_from_key
        raw = self.config(self.standard_files(), processes=4, mode='dbc')
        # voltage不填有效期，需要DBC周期补齐；current是DBC驱动。
        raw['signals'][0].pop('valid_for')
        plan = AnalysisPlan.from_dict(deepcopy(raw))
        definitions = tuple(item.definition for item in plan.signals)
        fields = {item.name: can_field_from_key(item.field) for item in definitions}
        requirement = collect_input_requirements(plan).for_source('bus')
        _, options = parallel_integral_source(plan.sources[0], definitions, requirement, plan.intervals.resolved)
        self.assertEqual(options['cycle_fields'], (fields['current'], fields['voltage']))
        _, options = parallel_integral_source(plan.sources[0], definitions, requirement)
        self.assertEqual(options['cycle_fields'], (fields['voltage'],))

    def test_dbc_driver_cycle_and_interval_helpers(self):
        """只在全部驱动都有同一DBC周期事实时给出纳秒；缺事实或周期不一致返回None，交由普通路径。"""
        from chronaxis.execution.same_frame_integrals import dbc_driver_cycle, direct_integral_interval
        from chronaxis.legacy.records import field_to_dict
        from chronaxis.sources.can_spec import can_field_from_key
        raw = self.config(self.standard_files(), mode='dbc')
        raw['calculations'].append(dict(raw['calculations'][0], name='energy_b',
                                        interval={'mode': 'dbc', 'driver': 'voltage'}))
        plan = AnalysisPlan.from_dict(deepcopy(raw))
        self.assertEqual(direct_integral_interval(plan), ('dbc', None))
        signals = {item.definition.name: item.definition for item in plan.signals}
        def fact(name, cycle=None):
            """参数为信号名和可选周期；返回与读取器相同形状的字段事实。"""
            item = dict(locator=field_to_dict(can_field_from_key(signals[name].field)))
            if cycle is not None:
                item['cycle_ns'] = cycle
            return item
        self.assertEqual(dbc_driver_cycle(plan, (fact('voltage', 125_000_000), fact('current', 125_000_000))),
                         125_000_000)
        self.assertIsNone(dbc_driver_cycle(plan, (fact('voltage', 125_000_000), fact('current'))))
        self.assertIsNone(dbc_driver_cycle(plan, (fact('voltage', 125_000_000), fact('current', 100_000_000))))
        # 两项都用DBC周期才共用一种间隔；改一项为实际间隔后不再进入直接积分，间隔查询也拒绝。
        mixed = deepcopy(raw)
        mixed['calculations'][1]['interval'] = {'mode': 'actual'}
        mixed_plan = AnalysisPlan.from_dict(mixed)
        with self.assertRaisesRegex(ValueError, '共用'):
            direct_integral_interval(mixed_plan)

    def test_fixed_non_applicable_intervals_keep_general_path(self):
        """混用实际/固定、两个不同固定值、驱动来自另一报文都不进入新路径，结果仍等于普通路径。"""
        self.dbc.write_text(self.dbc.read_text(encoding='utf-8')
                            + 'BO_ 512 OtherFrame: 1 Node\n SG_ Count : 0|8@1+ (1,0) [0|255] "" Node\n'
                            + 'BA_ "GenMsgCycleTime" BO_ 512 125;\n', encoding='utf-8')
        paths = self.standard_files()
        mixed = self.config(paths, mode='fixed')
        mixed['calculations'].append(dict(mixed['calculations'][0], name='energy_b', interval={'mode': 'actual'}))
        steps = deepcopy(mixed)
        steps['calculations'][1]['interval'] = {'mode': 'fixed', 'value': '0.25s', 'driver': 'current'}
        other = self.config(paths, mode='fixed')
        other['signals'].append(dict(name='count', source='bus', dtype='float64', valid_for='1s',
                                     field=dict(frame_id='0x200', signal='Count')))
        other['intervals']['default']['driver'] = 'count'
        # DBC周期与实际间隔、与等值固定间隔混用，或以另一报文信号作DBC驱动，同样不进入新路径。
        dbc_actual = deepcopy(mixed)
        dbc_actual['intervals']['default'] = {'mode': 'dbc', 'driver': 'current'}
        dbc_fixed = deepcopy(dbc_actual)
        dbc_fixed['calculations'][1]['interval'] = {'mode': 'fixed', 'value': '0.125s', 'driver': 'current'}
        dbc_other = deepcopy(other)
        dbc_other['intervals']['default'] = {'mode': 'dbc', 'driver': 'count'}
        for name, raw in (('mixed', mixed), ('steps', steps), ('other_driver', other), ('dbc_actual', dbc_actual),
                          ('dbc_fixed', dbc_fixed), ('dbc_other_driver', dbc_other)):
            with self.subTest(case=name):
                stack, counts = self.paths_used()
                with stack:
                    rows = [self.run_rows(dict(raw, execution=dict(raw['execution'], process_count=count)))
                            for count in (1, 4)]
                    general = self.run_rows(raw, backend='reference')
                self.assertEqual(counts, dict(direct=0, parallel=0))
                self.assertEqual(rows[0], general)
                self.assertEqual(rows[1], general)
        # 混用时两项各按自己的间隔：固定125ms为1100J，实际2700J；固定250ms为4000×0.25+4800×0.25=2200J；
        # 另一报文驱动只有一次更新，没有面积。
        self.assertEqual([row.value for row in self.run_rows(mixed)], [1100., 2700.])
        self.assertEqual([row.value for row in self.run_rows(steps)], [1100., 2200.])
        self.assertEqual([row.value for row in self.run_rows(other)], [None])
        self.assertEqual([row.value for row in self.run_rows(dbc_actual)], [1100., 2700.])
        self.assertEqual([row.value for row in self.run_rows(dbc_fixed)], [1100., 1100.])
        self.assertEqual([row.value for row in self.run_rows(dbc_other)], [None])

    def test_p5_selection_and_public_nonapplicable_controls(self):
        """成功例必须完成P5执行；静态不适用例连P5构造都不进入。"""
        module = importlib.import_module('chronaxis.execution.parallel_integral_session')
        cls = module.ParallelIntegralSession
        original = cls.__init__
        original_execute = cls.execute
        calls = []
        completed = []
        def construct(owner, *args, **kwargs):
            """参数为原构造参数；记录一次后调用原实现；返回和异常保持。"""
            calls.append(True)
            return original(owner, *args, **kwargs)
        def execute(owner, *args, **kwargs):
            """原execute成功返回才登记，prepare回退不能冒充P5执行。"""
            result = original_execute(owner, *args, **kwargs)
            completed.append(True)
            return result
        paths = self.standard_files()
        with patch.object(cls, '__init__', construct), patch.object(cls, 'execute', execute):
            # 实际间隔、固定间隔和DBC周期都应真正执行并行积分。
            for mode in ('actual', 'fixed', 'dbc'):
                self.run_rows(self.config(paths, processes=4, mode=mode))
            self.assertEqual(len(calls), 3)
            self.assertEqual(len(completed), 3)
            for raw, backend in ((self.config(paths, processes=1), None),
                    (self.config(paths[:1], processes=4), None),
                    (self.config(paths, processes=4), 'reference'),
                    (self.config(paths, processes=4), 'numpy'),
                    (self.config(paths, processes=4, mode='fixed'), 'reference'),
                    (self.config(paths, processes=4, mode='dbc'), 'reference'),
                    (self.config(paths, processes=4, merge='time_order'), None)):
                self.run_rows(raw, backend=backend)
                self.assertEqual(len(calls), 3)
                self.assertEqual(len(completed), 3)

    def test_fast_keeps_its_own_fixed_message_path(self):
        """fast逐报文累计三条贡献为2100J，不能构造普通P5会话积分器。"""
        module = importlib.import_module('chronaxis.execution.parallel_integral_session')
        from chronaxis.fast import run
        raw = self.config(self.standard_files(), processes=4)
        raw.pop('calculations')
        raw.pop('intervals')
        raw['execution'].pop('backend')
        raw['message_calculations'] = [dict(name='energy', update_message=dict(frame_id='0x100'),
            expr='voltage * current * period', unit='J', parameters=dict(period=dict(value=.125, unit='s')))]
        config = self.root/'fast.json'
        config.write_text(json.dumps(raw), encoding='utf-8')
        with patch.object(module.ParallelIntegralSession, '__init__', side_effect=AssertionError('fast误选P5')):
            manifest = run(config, self.root/'fast-output', work_dir=self.root/'fast-work')
        contents = json.loads(Path(manifest).read_text(encoding='utf-8'))
        names = [entry['name'] for entry in contents['outputs'] if entry['name'].startswith('results_') and entry['name'].endswith('.jsonl')]
        self.assertEqual(len(names), 1)
        rows = [json.loads(line) for line in (Path(manifest).parent/names[0]).read_text(encoding='utf-8').splitlines()]
        self.assertEqual([(row['name'], row['value'], row['unit'], row['status']) for row in rows],
                         [('energy', 2100., 'J', 'complete')])

    def test_pure_blf_legacy_and_strict_keep_length_policy(self):
        """纯BLF两政策的正常积分相同；legacy允许额外字节，strict仍报长度不符。"""
        paths = self.standard_files('blf')
        for policy in ('legacy', 'strict'):
            with self.subTest(policy=policy, payload='exact'):
                self.compare(self.pure_blf_config(paths, policy=policy), 2700., status='complete')
        padded = [self.source_file('blf', ((0., 256, b'\xc8\x0a\x00'),)),
                  self.source_file('blf', ((.125, 256, b'\xc8\x0c'), (.25, 512, b'\x00')))]
        self.compare(self.pure_blf_config(padded, policy='legacy'), 1100., status='complete')
        for count in (1, 4):
            with self.subTest(policy='strict', payload='extra', processes=count):
                message = self.failure(self.pure_blf_config(padded, processes=count))
                self.assertIn('载荷长度不一致', message)

    def test_cross_file_frame_identity_matches_general_path(self):
        """BUG-P5-005：DBC标FD且未写is_fd时，前后文件分别为FD帧与经典帧（及反向），
        4进程并行积分须报出与4进程原路径相同的错误，不能给出混合两种帧型的数值。"""
        import can
        with self.dbc.open('a', encoding='utf-8') as stream:
            stream.write('BA_DEF_ BO_ "VFrameFormat" ENUM "StandardCAN","ExtendedCAN",'
                '"reserved","J1939PG","reserved","reserved","reserved","reserved",'
                '"reserved","reserved","reserved","reserved","reserved","reserved",'
                '"StandardCAN_FD","ExtendedCAN_FD";\n'
                'BA_DEF_DEF_ "VFrameFormat" "StandardCAN";\nBA_ "VFrameFormat" BO_ 256 14;\n')

        def blf(name, rows):
            """写BLF。参数: 文件名、(秒, 字节, FD)行。返回: 路径项。异常: 写入错误。"""
            path = self.root / (name + '.blf')
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
        general = patch('chronaxis.execution.parallel_integral_session.parallel_integral_inputs', lambda plan: None)
        for label, first, second in (('fd_classic', fd, classic),
                                     ('classic_fd', tuple((t - .375, d, False) for t, d, _ in classic),
                                      tuple((t + .375, d, True) for t, d, _ in fd))):
            paths = [blf(label + '-a', first), blf(label + '-b', second)]
            for pure in (True, False):
                raw = self.pure_blf_config(paths, processes=4) if pure else self.config(paths, processes=4)
                with self.subTest(label=label, pure=pure):
                    message = self.failure(raw)
                    with general:
                        expected = self.failure(raw)
                    self.assertEqual(message, expected)
                    self.assertIn('同一报文绑定匹配多种实际帧，请补充 is_fd', message)

    def test_dbc_fd_classic_automatic_and_explicit_notices(self):
        """DBC标FD而原帧为经典CAN时，显式/自动绑定均保留两条真实兼容提示。"""
        with self.dbc.open('a', encoding='utf-8') as stream:
            stream.write('BA_DEF_ BO_ "VFrameFormat" ENUM "StandardCAN","ExtendedCAN",'
                '"reserved","J1939PG","reserved","reserved","reserved","reserved",'
                '"reserved","reserved","reserved","reserved","reserved","reserved",'
                '"StandardCAN_FD","ExtendedCAN_FD";\n'
                'BA_DEF_DEF_ "VFrameFormat" "StandardCAN";\n'
                'BA_ "VFrameFormat" BO_ 256 14;\n')
        paths = self.standard_files('blf')
        for explicit in (False, True):
            results = []
            for count in (1, 4):
                raw = self.pure_blf_config(paths, processes=count)
                if explicit:
                    for signal in raw['signals']:
                        signal['field'].update(is_fd=False, is_extended=False)
                with self.subTest(explicit=explicit, processes=count):
                    rows, notices = self.run_rows(raw, notices=True)
                    self.assertEqual(rows[0].value, 2700.)
                    self.assertEqual(rows[0].status, 'complete')
                    facts = tuple((source, notice.alias, notice.channel, notice.frame_id,
                        notice.signal, notice.is_extended, notice.dbc_is_fd,
                        notice.requested_is_fd, notice.code) for source, notice in notices)
                    self.assertEqual(facts, (
                        ('bus', 'voltage', 0, 256, 'Voltage', False, True, False, 'dbc_fd_classic_selector'),
                        ('bus', 'current', 0, 256, 'Current', False, True, False, 'dbc_fd_classic_selector')))
                    results.append((rows, notices))
            self.assertEqual(results[0], results[1])

    def test_derived_two_integrals_respect_small_and_large_batches(self):
        """300条同帧更新跨两个文件，批大小1/256及进程1/4均累计150000J和300000J。"""
        paths = [self.source_file('asc', tuple((i / 8, 256, b'\xc8\x0a') for i in range(150))),
                 self.source_file('asc', tuple((i / 8, 256, b'\xc8\x0a') for i in range(150, 300))
                                  + ((37.5, 512, b'\x00'),))]
        module = importlib.import_module('chronaxis.execution.parallel_integral_session')
        original = module.ParallelIntegralSession.execute
        selected = []
        def execute(owner, *args, **kwargs):
            """记录成功完成的P5执行，准备后的回退不会被计入。"""
            result = original(owner, *args, **kwargs)
            selected.append(True)
            return result
        observations = []
        for size in (1, 256):
            for count in (1, 4):
                raw = self.config(paths, processes=count)
                raw['execution']['batch_rows'] = size
                raw['derived'] = dict(power=dict(expr='voltage * current', unit='W'),
                                      twice_power=dict(expr='power * 2', unit='W'))
                raw['calculations'] = [dict(name='energy', operation='integral', expr='power', unit='J'),
                                       dict(name='double_energy', operation='integral', expr='twice_power', unit='J')]
                with self.subTest(batch_rows=size, processes=count):
                    before = len(selected)
                    with patch.object(module.ParallelIntegralSession, 'execute', execute):
                        rows = self.run_rows(raw)
                    self.assertEqual(len(selected) - before, int(count > 1))
                    self.assertEqual(tuple((row.calculation_id, row.value, row.unit, row.status) for row in rows),
                                     (('double_energy', 300000., 'J', 'complete'),
                                      ('energy', 150000., 'J', 'complete')))
                    observations.append(rows)
        self.assertTrue(all(rows == observations[0] for rows in observations))

    def test_full_input_check_rejects_unselected_time_regression(self):
        """auto只核所需帧顺序；full仍拒绝无关原帧在文件交界处回退。"""
        paths = [self.source_file('asc', ((0., 256, b'\xc8\x0a'), (.125, 256, b'\xc8\x0c'))),
                 self.source_file('asc', ((.0625, 512, b'\x00'), (.375, 256, b'\xc8\x14'),
                                          (.5, 512, b'\x00')))]
        self.compare(self.config(paths), 2700., status='complete')
        for count in (1, 4):
            raw = self.config(paths, processes=count)
            raw['sources'][0]['reader'] = dict(input_check='full')
            with self.subTest(processes=count):
                self.assertIn('时间回退', self.failure(raw))

    def test_session_fixed_cost_rejects_before_owner_construction(self):
        """只提高P5声明估算，公共预算仍供旧路径运行；会话owner不得创建且结果仍为2700J。"""
        from chronaxis.execution.parallel_integral_session import ParallelIntegralSession
        paths = self.standard_files()
        expected = self.run_rows(self.config(paths))
        with patch.object(ParallelIntegralSession, 'fixed_cost', return_value=2**62) as estimate, \
                patch.object(ParallelIntegralSession, '__init__',
                             side_effect=AssertionError('超预算仍创建P5会话')) as construct:
            actual = self.run_rows(self.config(paths, processes=4))
        estimate.assert_called_once()
        construct.assert_not_called()
        self.assertEqual(actual, expected)
        self.assertEqual(actual[0].value, 2700.)

    def test_pool_startup_cost_rejects_before_pool_or_read(self):
        """P5启动估算不足时不创建pool、不安装数值任务，原路径仍正常累计并退款。"""
        from chronaxis.execution.parallel_integral_pool import ParallelIntegralPool
        paths = self.standard_files()
        expected = self.run_rows(self.config(paths))
        with patch.object(ParallelIntegralPool, 'startup_cost', return_value=2**62) as estimate, \
                patch.object(ParallelIntegralPool, '__init__',
                             side_effect=AssertionError('超预算仍创建积分池')) as construct, \
                patch.object(ParallelIntegralPool, 'configure',
                             side_effect=AssertionError('超预算仍安装数值任务')) as configure:
            actual = self.run_rows(self.config(paths, processes=4))
        estimate.assert_called_once()
        construct.assert_not_called()
        configure.assert_not_called()
        self.assertEqual(actual, expected)
        self.assertEqual(actual[0].value, 2700.)

    def test_configuration_budget_falls_back_before_first_read_request(self):
        """真实READY后判数值费用不足；禁止next读取许可，关闭已启动资源后原路径算2700J。"""
        from chronaxis._control_wire import ControlChannel
        from chronaxis.execution.parallel_integral_pool import ParallelIntegralPool
        paths = self.standard_files()
        expected = self.run_rows(self.config(paths))
        owners, commands = [], []
        original = ControlChannel.send
        def record_send(channel, message):
            """参数为真实通道及消息；记录P5许可后原样发送；返回及异常不变。"""
            if channel.family == 'integral':
                commands.append(message[0])
                self.assertNotEqual(message[0], 'next', '预算未通过却授予首帧读取许可')
            return original(channel, message)
        def over_budget(owner, *args, **kwargs):
            """参数为已取得元数据的pool及声明；核未读状态后返回超额费用；异常为断言失败。"""
            self.assertEqual(owner.count, 0)
            self.assertFalse(owner._configured)
            self.assertIsNotNone(owner.metadata)
            owners.append(owner)
            return 2**62
        with patch.object(ControlChannel, 'send', record_send), \
                patch.object(ParallelIntegralPool, 'configuration_cost', over_budget), \
                patch.object(ParallelIntegralPool, 'configure',
                             side_effect=AssertionError('数值费用未通过却安装任务')) as configure:
            actual = self.run_rows(self.config(paths, processes=4))
        self.assertEqual(actual, expected)
        self.assertEqual(actual[0].value, 2700.)
        configure.assert_not_called()
        self.assertEqual(len(owners), 1)
        self.assertIn('file', commands)
        self.assertIn('close', commands)
        self.assertNotIn('next', commands)
        self.assertNotIn('configure', commands)
        self.assertTrue(owners[0].closed)
        self.assertEqual(owners[0]._held_cost, 0)
        self.assertEqual(owners[0]._budget.ram_bytes, 0)

    def test_six_integrals_eight_workers_default_budget_rejects_before_pool(self):
        """十文件六积分默认256MiB/批上限下，八进程P5必需费用超限，不创建池且原路线仍算4500J。"""
        from chronaxis.execution.parallel_integral_pool import ParallelIntegralPool
        paths = [self.source_file('asc', ((index / 8, 256, b'\xc8\x0a'),)) for index in range(10)]
        raw = self.config(paths, processes=8)
        raw['calculations'] = [dict(name=f'energy_{index}', operation='integral',
                                    expr='voltage * current', unit='J', scope='session')
                               for index in range(6)]
        plan = AnalysisPlan.from_dict(deepcopy(raw))
        self.assertEqual(plan.execution.memory_budget_bytes, 256 * 1048576)
        self.assertEqual(plan.execution.batch_rows, 65536)
        with patch.object(ParallelIntegralPool, '__init__',
                          side_effect=AssertionError('确定预算不足却创建P5池')) as construct, \
                patch.object(ParallelIntegralPool, 'prepare_metadata',
                             side_effect=AssertionError('确定预算不足却启动元数据进程')) as metadata:
            rows = self.run_rows(raw)
        construct.assert_not_called()
        metadata.assert_not_called()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row.value == 4500. and row.unit == 'J' and row.status == 'complete' for row in rows))


    def test_multiplex_decode_invalid_at_file_boundary_replaces_previous_values(self):
        """合法长度但未定义子类型令当帧无效；跨文件不沿用旧功率，手算1100J。"""
        self.dbc.write_text(
            'VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 PowerFrame: 3 Node\n'
            ' SG_ Mux M : 0|8@1+ (1,0) [0|255] "" Node\n'
            ' SG_ Voltage m1 : 8|8@1+ (2,0) [0|510] "V" Node\n'
            ' SG_ Current m1 : 16|8@1+ (1,0) [0|255] "A" Node\n', encoding='utf-8')
        module = importlib.import_module('chronaxis.execution.parallel_integral_session')
        original = module.ParallelIntegralSession.execute
        selected = []
        def execute(owner, *args, **kwargs):
            """记录成功完成的P5执行，防止把准备后回退计作并行通过。"""
            result = original(owner, *args, **kwargs)
            selected.append(True)
            return result
        for kind in ('asc', 'blf'):
            paths = [self.source_file(kind, ((0., 256, b'\x01\xc8\x0a'),)),
                     self.source_file(kind, ((.125, 256, b'\x02\xc8\x0a'),
                                             (.25, 256, b'\x01\xc8\x0c'), (.375, 512, b'\x00')))]
            raw = self.pure_blf_config(paths, policy='partial') if kind == 'blf' else self.config(paths)
            raw['sources'][0]['reader'] = dict(decode_policy='partial')
            with self.subTest(kind=kind), patch.object(module.ParallelIntegralSession, 'execute', execute):
                before = len(selected)
                rows = self.compare(raw, 1100., status='partial', quality=QualityFlag.MISSING)
                self.assertEqual(len(selected) - before, 1)
                self.assertEqual(rows[0].reason, 'partial_coverage')


if __name__ == '__main__':
    unittest.main()
