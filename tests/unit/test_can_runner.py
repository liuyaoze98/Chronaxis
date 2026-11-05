"""从公共AnalysisRunner读取真实合成BLF，验证CAN接线、缺值、范围与结果出处。

每例生成独立BLF/DBC和计划，时间与值由简单一字节信号手算。旧链在真实spawn
子进程执行；两后端及1/2/7切批比较相同公开结果。暂存、结果及配置只写work，
不写RefProjects。测试可读取小夹具结果作断言，生产流仍逐批处理。
可选CAN依赖缺失时明确skip；本机正式验收提供固定依赖，不以skip声称通过。
"""

from configuration_fixtures import current_fixture

# CAN依赖延迟到夹具，不令普通静态计划依赖旧I/O库。
import json
from pathlib import Path
import unittest
from uuid import uuid4
from chronaxis import AnalysisPlan, AnalysisRunner, AnalysisError
from chronaxis.core.types import QualityFlag as Q


class CANRunnerTests(unittest.TestCase):
    """独立真实输入经完整公共执行，最终close后共享RAM须归零。"""

    def fixture(self, *, backend='numpy', size=2, frames=((0, b'\x01'), (1, b'\x03'),
            (1, b'\x05'), (2, b'\x07')), policy='last_by_sequence', signals=True, unit='V', decode_policy='strict'):
        """生成单通道一字节DBC/BLF及完整声明，首帧基准映到0ns。

        参数: backend/size真实后端与批长；frames为秒偏移及原payload；policy为同刻策略；
            signals=False保留来源空投影；unit为声明输入/输出单位。
        返回: (work, config, plan)。异常: 文件、DBC或配置错误直接传播，缺可选依赖skip。
        """
        try:
            import can
        except ModuleNotFoundError as exc:
            self.skipTest('缺可选CAN依赖: ' + exc.name)
        work = Path(__file__).resolve().parents[2] / 'work/m2-can-tests/public-runner' / uuid4().hex
        work.mkdir(parents=True)
        dbc, blf = work / 'synthetic.dbc', work / 'synthetic.blf'
        dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 1 Node\n SG_ Voltage : 0|8@1+ (1,0) [0|255] "V" Node\n', encoding='utf-8')
        writer = can.BLFWriter(blf)
        try:
            for second, payload in frames:
                writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                    arbitration_id=256, is_extended_id=False, channel=0, data=payload))
        finally:
            writer.stop()
        config = dict(config_version=4,
            dataset=dict(name='can_real', entity='synthetic', session='session',
                domain=dict(start='0s', end='4s')),
            sources=[dict(name='bus', source_type='can_blf', path=str(blf),
                legacy_profile='sclicer-functions-v1', reader_options=dict(decode_policy=decode_policy), dbc_by_channel={'1': str(dbc)},
                time=dict(time_type='relative', unit='s', origin='synthetic_clock',
                    offset='-1700000000s'))],
            signals=[dict(name='voltage', source='bus', field=dict(channel=1,
                signal='Voltage', frame_id=256, is_extended=False, is_fd=False),
                dtype='float64', input_unit=unit, unit=unit, valid_for='10s', same_time_policy=policy)] if signals else [],
            rules=[dict(name='active', rule_type='condition_duration', condition='voltage > 0' if signals else 'True',
                minimum_duration='0s')],
            windows=[], calculations=[dict(name='samples', scope='session', operation='select', expr='voltage')]
                if signals else [dict(name='known', scope='session', operation='duration', condition='True')],
            execution=dict(backend=backend, batch_rows=size, memory_budget_bytes=256*1024**2),
            diagnostics=dict(trace=True, integrity=True),
            metadata=dict(device_label='home', data_kind='synthetic'))
        # 保存便于故障重现；from_dict以此目录解释路径，读取发生在run中。
        (work / 'plan.json').write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        return work, current_fixture(config), AnalysisPlan.from_dict(current_fixture(config), base_dir=work)

    def run_plan(self, plan, work):
        """公共运行并登记结果关闭。参数: plan/work实际输入。返回: AnalysisResult。异常: 原运行错。
        """
        result = AnalysisRunner().run(plan, work_dir=work / 'run')
        self.addCleanup(result.close)
        return result

    def rows(self, result):
        """耗尽真实指标游标后关闭。参数: 活result。返回: 小夹具tuple。异常: 原读取/关闭错。
        """
        reader = result.iter_selections()
        try:
            return tuple(reader)
        finally:
            reader.close()

    def test_two_backends_batches_preserve_same_time_and_can_provenance(self):
        """同刻按显式last策略选5，半开范围内原序0/2及全部四帧元数据保留。

        参数: 无。返回: None。异常: 数值、出处、一次观测范围或关闭账本不符即失败。
        """
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                with self.subTest(backend=backend, size=size):
                    work, _, plan = self.fixture(backend=backend, size=size)
                    result = self.run_plan(plan, work)
                    rows = self.rows(result)
                    self.assertEqual(tuple((row.time_ns, row.value) for row in rows),
                        ((0, 1.0), (1000000000, 5.0)))
                    traces = tuple(result.iter_input_trace())
                    self.assertEqual(tuple(row.original_sequence for row in traces), (0, 1, 2, 3))
                    self.assertEqual(tuple(row.time_ns for row in traces), (0, 10**9, 10**9, 2*10**9))
                    self.assertEqual([json.loads(row.values_json)['Voltage'] for row in traces], [1, 3, 5, 7])
                    self.assertTrue(all(row.source == 'bus' and row.record_type == 'decoded_message' for row in traces))
                    fact, = result.metadata.input_diagnostics
                    self.assertEqual((fact.record_count, fact.source_eof), (4, True))
                    self.assertEqual(fact.aliases, ('voltage',))
                    self.assertTrue(dict(fact.bindings)['voltage'])
                    self.assertEqual(len(fact.sha256), 64)
                    self.assertFalse(tuple(work.rglob('raw_frames.jsonl')))
                    budget = result.spool.budget
                    result.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_matching_empty_decode_invalidates_previous_value(self):
        """350V情形以可手算3V代替：同类空payload使后续1–2秒为UNKNOWN，不沿用3V。

        参数: 无。返回: None。异常: 旧allow_truncated空解码被跳过或虚构DECODE_ERROR即失败。
        """
        for backend in ('reference', 'numpy'):
            work, _, plan = self.fixture(backend=backend, frames=((0, b'\x03'), (1, b''), (2, b'\x07')), decode_policy='legacy')
            result = self.run_plan(plan, work)
            rows = self.rows(result)
            # select保留无效更新；事件边界也须在1秒结束，不能延用前值。
            events = result.iter_events()
            try:
                actual = tuple(events)
            finally:
                events.close()
            self.assertEqual(len(actual), 1)
            self.assertEqual((actual[0].start_ns, actual[0].end_ns,
                actual[0].status), (0, 1000000000, 'interrupted'))
            self.assertEqual(result.metadata.input_diagnostics[0].record_count, 3)
            invalid = tuple(row for row in rows if not row.valid)
            self.assertEqual(len(invalid), 1)
            self.assertTrue(all(row.quality & Q.MISSING for row in invalid))
            self.assertTrue(all(not row.quality & Q.DECODE_ERROR for row in invalid))

    def test_default_same_time_error_is_preserved(self):
        """默认error不得因CAN接线而静默去重。参数: 无。返回: None。异常: 同刻被接受则失败。
        """
        work, _, plan = self.fixture(policy='error')
        with self.assertRaises(AnalysisError) as caught:
            self.run_plan(plan, work)
        self.assertIs(type(caught.exception.__cause__), ValueError)
        self.assertIn('同信号同时间冲突', str(caught.exception.__cause__))

    def test_dbc_nonempty_unit_mismatch_is_rejected(self):
        """DBC写V而声明A须停止，不重复换算。参数: 无。返回: None。异常: 被接受即失败。
        """
        work, _, plan = self.fixture(unit='A')
        with self.assertRaises(Exception) as caught:
            self.run_plan(plan, work)
        self.assertIn('input_unit', str(caught.exception))

    def test_empty_projection_keeps_real_clock_without_claiming_decoded_records(self):
        """空投影仍按真实时钟生成2秒活动，不将时钟数冒充解码数。参数: 无。返回: None。异常: 断言。"""
        work, _, plan = self.fixture(signals=False)
        result = self.run_plan(plan, work)
        events = tuple(result.iter_events())
        self.assertEqual([(row.start_ns, row.end_ns) for row in events], [(0, 2*10**9)])
        self.assertEqual(tuple(row.value for row in result.iter_calculations()), (2.0,))
        fact, = result.metadata.input_diagnostics
        self.assertEqual((fact.record_count, fact.aliases, fact.source_eof), (0, (), True))

    def test_empty_blf_has_no_events_and_no_observation(self):
        """零帧不因True生成事件，保空首末。参数: 无。返回: None。异常: 假零点或事件即失败。
        """
        work, _, plan = self.fixture(frames=(), signals=False)
        result = self.run_plan(plan, work)
        events = result.iter_events()
        try:
            self.assertEqual(tuple(events), ())
        finally:
            events.close()
        fact, = result.metadata.input_diagnostics
        self.assertEqual((fact.record_count, fact.source_eof), (0, True))
        self.assertEqual([(row.value, row.status) for row in result.iter_calculations()], [(None, 'indeterminate')])


if __name__ == '__main__':
    # 真实spawn子进程不可在模块导入时重入测试主程序。
    unittest.main()
