"""从普通 Runner 验证同帧直接积分，和两条显式通用路径及手算分别比较。

三种真实小文件共用同一 DBC；用结构阻断验证确实省掉数组归组和最新状态，
并检查来源尾段、跨文件同刻、默认有效期、失败清理及首帧前选择普通路径。
"""

from contextlib import ExitStack
from uuid import uuid4
import unittest
from unittest.mock import patch

from chronaxis import AnalysisRunner
from chronaxis.results.errors import AnalysisError
from chronaxis.execution.same_frame_integrals import SameFrameIntegrals
import test_record_runner as fixtures


class SameFrameRunnerTests(unittest.TestCase):
    """每个运行独享工作目录和预算；公开结果是比较对象，不比较私有实现布局。"""

    setUp = fixtures.RecordRunnerTests.setUp
    asc = fixtures.RecordRunnerTests.asc
    csv = fixtures.RecordRunnerTests.csv
    blf = fixtures.RecordRunnerTests.blf
    fixtures = fixtures.RecordRunnerTests.fixtures

    def plan(self, kind, path, edit=None):
        """只保留原样例的实际时间积分。参数: 格式、路径、配置调整。返回: 计划。异常: 原静态错误。"""
        def prepare(raw):
            """声明 auto 且不改变业务公式。参数: 配置。返回: None。异常: 调整错误。"""
            raw['calculations'] = raw['calculations'][:1]
            raw.setdefault('execution', {}).update(backend='auto', batch_rows=2)
            if edit is not None:
                edit(raw)
        return fixtures.RecordRunnerTests.plan(self, kind, path, mode='actual', edit=prepare)

    def run_rows(self, plan, backend=None, *, direct=False):
        """运行并关闭结果，同时检查直接路径省掉的对象。参数: 计划/覆盖/结构检查。返回: 行tuple。异常: 原运行错。"""
        work = self.root / uuid4().hex
        with ExitStack() as stack:
            if direct:
                for target in ('record_source_cursor.RawSignalGroups',
                               'record_session_calculations.LatestSignalState',
                               'record_session_calculations.DriverExpression'):
                    stack.enter_context(patch('chronaxis.execution.' + target,
                        side_effect=AssertionError('直接路径构造了不需要的通用状态')))
            result = AnalysisRunner(backend).run(plan, work)
            try:
                rows = tuple(result.iter_calculations())
                self.assertEqual(set(result.spool.counts), {'calculations'})
                self.assertEqual(result.metadata.backend, backend or 'reference')
                budget = result.spool._budget
            finally:
                result.close()
        self.assertEqual(budget.ram_bytes, 0)
        self.assertFalse(work.exists())
        return rows

    def compare(self, plan, expected, *, direct=True):
        """以独立手算和原显式路径双重核验。参数: 计划/预期数值。返回: 行tuple。异常: 断言。"""
        actual = self.run_rows(plan, direct=direct)
        for backend in ('reference', 'numpy'):
            self.assertEqual(actual, self.run_rows(plan, backend))
        if expected is None:
            self.assertIsNone(actual[0].value)
        else:
            self.assertAlmostEqual(actual[0].value, expected, places=2)
        return actual

    def test_three_formats_bounded_batches_units_and_default_ttl(self):
        """三格式 4000W×0.12s+4800W×0.18s=1344J；DBC默认TTL与显式TTL一致。"""
        for kind, path in self.fixtures().items():
            for rows in (1, 2, 64):
                def edit(raw):
                    """变批大小而不改时间。参数: 配置。返回: None。异常: 无。"""
                    raw['execution']['batch_rows'] = rows
                    # 覆盖显式auto和省略后端两种公共入口；业务面积相同。
                    if rows == 64:
                        raw['execution'].pop('backend')
                    raw['calculations'][0]['unit'] = 'Wh'
                    for signal in raw['signals']:
                        signal.pop('valid_for')
                with self.subTest(kind=kind, batch_rows=rows):
                    self.compare(self.plan(kind, path, edit), 1344 / 3600)

    def test_observation_tail_clipping_and_short_ttl(self):
        """无关末帧仍确定EOF，裁剪不补观测；TTL 50ms只留下200J+240J。"""
        self.fixtures()
        path = self.asc('0.00 1 100 Rx d 2 C8 0A\n0.12 1 100 Rx d 2 C8 0C\n'
                        '0.30 1 200 Rx d 1 00\n').path
        for domain, ttl, expected in ((None, '1s', 1344),
                                     ({'start':'0.06s', 'end':'0.24s'}, '1s', 816),
                                     ({'start':'0s', 'end':'1s'}, '1s', 1344),
                                     (None, '0.05s', 440)):
            def edit(raw):
                """选择范围和有效期。参数: 配置。返回: None。异常: 无。"""
                if domain is None:
                    raw['dataset'].pop('domain')
                else:
                    raw['dataset']['domain'] = domain
                for signal in raw['signals']:
                    signal['valid_for'] = ttl
            with self.subTest(domain=domain, ttl=ttl):
                self.compare(self.plan('can_asc', path, edit), expected)

    def test_empty_one_point_and_no_target(self):
        """空来源、单点和只有其他ID保持通用路径的空值原因，不能产生虚假能量。"""
        self.fixtures()
        for body in ('', '0.1 1 100 Rx d 2 C8 0A\n',
                     '0.0 1 200 Rx d 1 00\n0.3 1 200 Rx d 1 00\n'):
            def edit(raw):
                """按实际观测范围。参数: 配置。返回: None。异常: 无。"""
                raw['dataset'].pop('domain')
            self.compare(self.plan('can_asc', self.asc(body).path, edit), None)

    def test_first_target_after_observation_start(self):
        """观测前0.1秒没有功率，后0.2秒才有4000W，不把未知头部补成零或完整。"""
        self.fixtures()
        path = self.asc('0.0 1 200 Rx d 1 00\n0.1 1 100 Rx d 2 C8 0A\n'
                        '0.3 1 200 Rx d 1 00\n').path
        def edit(raw):
            """采用实际来源范围。参数: 配置。返回: None。异常: 无。"""
            raw['dataset'].pop('domain')
        rows = self.compare(self.plan('can_asc', path, edit), 800)
        self.assertEqual(rows[0].status, 'partial')

    def test_continuous_files_same_time_and_parallel_merge(self):
        """跨卷同刻按最后原序选8000W，积分1920J；并行归并不重置状态。"""
        self.fixtures()
        first = self.asc('0.00 1 100 Rx d 2 C8 0A\n0.12 1 100 Rx d 2 C8 0C\n').path
        second = self.asc('0.12 1 100 Rx d 2 C8 14\n0.30 1 100 Rx d 2 C8 14\n').path
        for processes in (1, 4):
            for merge in ('concatenate', 'time_order'):
                def edit(raw):
                    """连续文件保留一份会话。参数: 配置。返回: None。异常: 无。"""
                    raw['sources'][0].pop('path')
                    raw['sources'][0].update(paths=[str(first.absolute()), str(second.absolute())], file_merge=merge)
                    raw['execution']['process_count'] = processes
                    for signal in raw['signals']:
                        signal['same_time_policy'] = 'last_by_sequence'
                with self.subTest(processes=processes, merge=merge):
                    self.compare(self.plan('can_asc', first, edit), 1920)

    def test_decode_failure_replaces_previous_value(self):
        """未知复用编号把当前值置无效；不能继续用旧4000W累加后0.18秒。"""
        self.fixtures()
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 3 Node\n SG_ Selector M : 0|8@1+ (1,0) [0|255] "" Node\n'
            ' SG_ Voltage m1 : 8|8@1+ (2,0) [0|510] "V" Node\n'
            ' SG_ Current m1 : 16|8@1+ (1,0) [0|255] "A" Node\n', encoding='utf-8')
        path = self.asc('0.00 1 100 Rx d 3 01 C8 0A\n0.12 1 100 Rx d 3 02 C8 0C\n'
                        '0.30 1 100 Rx d 3 01 C8 14\n').path
        rows = self.compare(self.plan('can_asc', path), 480)
        self.assertEqual(rows[0].status, 'partial')

    def test_shared_frame_calculations_keep_independent_missing_quality(self):
        """复用报文只缺电流时，能量部分有效而电压积分仍完整120V*s。"""
        self.fixtures()
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 3 Node\n SG_ Selector M : 0|8@1+ (1,0) [0|255] "" Node\n'
            ' SG_ Voltage : 8|8@1+ (2,0) [0|510] "V" Node\n'
            ' SG_ Current m1 : 16|8@1+ (1,0) [0|255] "A" Node\n'
            ' SG_ Other m2 : 16|8@1+ (1,0) [0|255] "" Node\n', encoding='utf-8')
        path = self.asc('0.00 1 100 Rx d 3 01 C8 0A\n0.12 1 100 Rx d 3 02 C8 0C\n'
                        '0.30 1 100 Rx d 3 01 C8 14\n').path
        def edit(raw):
            """只增加实际需要的电压累计。参数: 配置。返回: None。异常: 无。"""
            raw['calculations'].append(dict(name='voltage_area', operation='integral', expr='voltage', unit='V*s'))
        rows = self.compare(self.plan('can_asc', path, edit), 480)
        voltage, = (row for row in rows if row.calculation_id == 'voltage_area')
        self.assertEqual((voltage.value, voltage.status, int(voltage.quality)), (120, 'complete', 0))

    def test_uncertain_binding_uses_original_cursor_before_reading(self):
        """绑定证明不足只建立普通归组，首帧前选择且不创建第二个读取游标。"""
        from chronaxis.execution import record_source_cursor as cursors
        from chronaxis.sources import text_can_decode
        path = self.fixtures()['can_asc']
        plan = self.plan('can_asc', path)
        original = cursors.RecordSourceCursor._attach_raw_groups
        cursors_seen = []
        def attach(owner, *args):
            """观测首帧前复用。参数: owner/参数。返回: 原返回。异常: 原错误。"""
            self.assertFalse(owner._reading_started)
            cursors_seen.append(owner)
            return original(owner, *args)
        with patch('chronaxis.execution.same_frame_integrals.same_frame_binding', return_value=None), \
             patch.object(cursors.RecordSourceCursor, '_attach_raw_groups', attach), \
             patch.object(text_can_decode, 'load_dbc_file', wraps=text_can_decode.load_dbc_file) as load, \
             patch.object(SameFrameIntegrals, '__init__', side_effect=AssertionError('不应构造直接owner')):
            actual = self.run_rows(plan)
        self.assertEqual(len(cursors_seen), 1)
        self.assertEqual(load.call_count, 1)
        self.assertEqual(actual, self.run_rows(plan, 'reference'))

    def test_explicit_backend_and_fixed_period_keep_general_path(self):
        """显式后端不被优化替换；固定周期依然算880J，不改成实际积分1344J。"""
        path = self.fixtures()['can_asc']
        plan = self.plan('can_asc', path)
        with patch.object(SameFrameIntegrals, '__init__', side_effect=AssertionError('越过适用边界')):
            for backend in ('reference', 'numpy'):
                self.assertAlmostEqual(self.run_rows(plan, backend)[0].value, 1344)
            def edit(raw):
                """改为固定周期。参数: 配置。返回: None。异常: 无。"""
                raw['intervals']['default'] = dict(mode='fixed', value='0.1s', driver='current')
            fixed = self.plan('can_asc', path, edit)
            work = self.root / uuid4().hex
            with AnalysisRunner().run(fixed, work) as result:
                self.assertAlmostEqual(next(result.iter_calculations()).value, 880)
                self.assertEqual(result.metadata.backend, 'numpy')

    def test_failure_cancel_and_close_restore_budget_without_retry(self):
        """消费失败与取消均保持一次扫描和预算归零，失败不交付前缀。"""
        path = self.fixtures()['can_asc']
        plan = self.plan('can_asc', path)
        original = SameFrameIntegrals.consume
        for problem in (ValueError('direct failure'), KeyboardInterrupt('direct cancel')):
            seen, budgets = [], []
            def fail(owner, update):
                """第二帧故意失败。参数: owner/更新。返回: None。异常: 注入原错。"""
                budgets.append(owner._budget)
                seen.append(update.sequence)
                if len(seen) == 2:
                    raise problem
                return original(owner, update)
            work = self.root / uuid4().hex
            with patch.object(SameFrameIntegrals, 'consume', fail):
                with self.assertRaises((AnalysisError, KeyboardInterrupt)):
                    AnalysisRunner().run(plan, work)
            self.assertEqual(len(seen), 2)
            self.assertTrue(budgets)
            self.assertEqual(budgets[0].ram_bytes, 0)
            self.assertFalse(work.exists())

    def test_persistent_direct_close_failure_keeps_highest_owner(self):
        """直接owner持续关闭失败时仍能从公共异常恢复，修复后释放全部费用。"""
        path = self.fixtures()['can_asc']
        work = (self.root / uuid4().hex).resolve()
        with patch.object(SameFrameIntegrals, 'consume', side_effect=ValueError('direct failure')), \
             patch.object(SameFrameIntegrals, 'close', side_effect=OSError('busy direct owner')):
            with self.assertRaises(AnalysisError) as caught:
                AnalysisRunner().run(self.plan('can_asc', path), work)
        owner = caught.exception.runner_cleanup_owner
        self.assertFalse(owner._closed)
        owner.close()
        self.assertEqual(owner._budget.ram_bytes, 0)
        self.assertFalse(work.exists())
