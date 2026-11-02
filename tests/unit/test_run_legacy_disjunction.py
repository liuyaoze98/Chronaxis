"""用真实公共CAN输入核对原方向分桶、独立累计与当前追溯发布。

双后端覆盖负scale、同刻、缺值/非有限/布尔、表达式错误优先和最终舍入。
DBC不能表达的值只在真实解码后的update边界注入，不修改输入、帧或EOF事实。
平坦贡献通过来源和原序关联input_trace，真实快照独立核累计次数与未舍入总和。
"""

from configuration_fixtures import current_fixture

import json
from math import isnan
import unittest
from unittest.mock import patch
from dataclasses import replace
from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from chronaxis.execution.record_session_calculations import RecordSessionCalculations

import test_run_message_calculations as fixtures
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.types import QualityFlag as Q
from chronaxis.execution.run_session import RunSession
from chronaxis.legacy.disjunction import LegacyDisjunction
from chronaxis.legacy.sum import LegacySkipReason as S
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import AnalysisError
from chronaxis.sources.can_spec import CANSourceRef


class RunLegacyDisjunctionTests(unittest.TestCase):
    """只复用旧测试的数据生成方法，不继承或重复收集其原测试方法。"""

    def fixture(self, *, backend='numpy', batch=2, rows=((0, 4000, 2),), scale=1,
                expression='power * period', unit='J', period=0.1, tables='jsonl', other=False):
        """扩展真实三字节Power报文，显式声明两个独立桶指标。

        参数: rows为(秒,原功率,有符号方向)tuple；None功率写空帧；其余选项
            分别控制后端、切批、方向普通转换、公式/单位、输出和额外真实消息声明。
        返回: (work,config,plan)。异常: 原依赖/文件/配置错误；缺CAN依赖沿夹具skip。
        """
        work, config, _ = fixtures.RunMessageCalculationTests.fixture(self, backend=backend,
            batch=batch, frames=(), period=period, tables=tables)
        import can
        dbc = work / 'power.dbc'
        dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Power: 3 Node\n'
            ' SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n'
            ' SG_ Direction : 16|8@1- (1,0) [-128|127] "raw_direction" Node\n'
            + ('BO_ 257 Other: 1 Node\n'
               ' SG_ Direction : 0|8@1- (1,0) [-128|127] "raw_direction" Node\n'
               if other else ''), encoding='utf-8')
        writer = can.BLFWriter(work / 'power.blf')
        try:
            # 实际原writer仅写本次新文件，每个tuple保留一帧，包括同刻的不同原方向。
            for second, power, direction in rows:
                payload = b'' if power is None else power.to_bytes(2, 'little') + bytes((direction & 255,))
                writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                    arbitration_id=256, is_extended_id=False, channel=0, data=payload))
        finally:
            writer.stop()
        direction = dict(name='direction', source='bus', field=dict(channel=1,
            signal='Direction', frame_id=256, is_extended=False, is_fd=False), dtype='float64',
            unit='raw_direction', valid_for='1ns', same_time_policy='last_by_sequence', scale=scale)
        config['signals'].append(direction)
        if other:
            second = json.loads(json.dumps(current_fixture(direction)))
            second['name'], second['field']['frame_id'] = 'other', 257
            config['signals'].append(second)
        positive = config['message_calculations'][0]
        positive['name'] = 'positive'
        positive['expr'], positive['unit'] = expression, unit
        positive['split_by_sign'] = dict(signal='direction', bucket='positive', value_policy='raw_decoded-v1')
        negative = json.loads(json.dumps(current_fixture(positive)))
        negative['name'], negative['split_by_sign']['bucket'] = 'negative', 'negative'
        config['message_calculations'] = [positive, negative]
        (work / 'plan.json').write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        return work, config, AnalysisPlan.from_dict(current_fixture(config), base_dir=work)

    def run_plan(self, work, plan, name='run'):
        """观察真实累计快照后透传同一结果。参数: 原输入。返回: 结果。异常: 原运行错。"""
        snapshots = {}
        original = CurrentMessageCalculation.snapshot
        def observe(owner):
            """只调用原快照一次。参数: 实际owner。返回: 原快照。异常: 原错误。"""
            value = original(owner)
            snapshots[owner._calculation.calculation_id] = value
            return value
        with patch.object(CurrentMessageCalculation, 'snapshot', observe):
            result = fixtures.RunMessageCalculationTests.run_plan(self, work, plan, name)
        self.snapshots = snapshots
        return result

    def trace_values(self, result):
        """有限读取同次输入追溯。参数: 结果。返回: 原序对应JSON值。异常: 原游标错误。"""
        reader = result.iter_input_trace()
        try:
            return {row.original_sequence: json.loads(row.values_json) for row in reader}
        finally:
            reader.close()

    def rows(self, result, kind):
        """耗尽并关闭真实typed游标。参数: result/kind。返回: tuple。异常: 原回读错。"""
        return fixtures.RunMessageCalculationTests.rows(self, result, kind)

    def test_raw_direction_outside_expression_signed_contributions_both_backends_batches(self):
        """负scale不改变原方向；同刻正负贡献各自累计，追溯保原始字段。"""
        for backend in ('reference', 'numpy'):
            for batch in (1, 2, 7):
                with self.subTest(backend=backend, batch=batch):
                    work, _, plan = self.fixture(backend=backend, batch=batch, scale=-1,
                        rows=((0, 3000, 2), (0, 6000, -3), (1, 9000, 0)),
                        expression='(power - 4000) * period')
                    result = self.run_plan(work, plan)
                    summaries = {row.calculation_id: row for row in self.rows(result, 'summary')}
                    self.assertEqual((summaries['positive'].value, summaries['negative'].value), (-100., 200.))
                    for bucket in ('positive', 'negative'):
                        snapshot = self.snapshots[bucket]
                        self.assertEqual((snapshot.evaluation_count, snapshot.contribution_count,
                                          snapshot.skipped_count), (3, 1, 2))
                        self.assertEqual(snapshot.skip_counts[S.CONDITION_FALSE], 2)
                    rows = sorted(self.rows(result, 'contributions'), key=lambda row: row.sequence)
                    self.assertEqual(tuple(row.calculation_id for row in rows), ('positive', 'negative') * 3)
                    self.assertEqual(tuple(row.original_sequence for row in rows), (0, 0, 1, 1, 2, 2))
                    self.assertEqual(tuple(row.evaluation_index for row in rows), (0, 0, 1, 1, 2, 2))
                    self.assertEqual(tuple(row.value for row in rows), (-100., None, None, 200., None, None))
                    trace = self.trace_values(result)
                    self.assertEqual([trace[i]['Direction'] for i in range(3)], [2, -3, 0])
                    self.assertEqual([trace[i]['Power'] for i in range(3)], [3000, 6000, 9000])
                    self.assertTrue(all(row.quality == Q.NONE for row in rows))
                    budget = result.spool.budget
                    result.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_capture_dictionary_missing_nonfinite_bool_and_expression_priority(self):
        """真实解码后仅注入DBC不能表示的原值，仍走当前消费/追溯及真实EOF。"""
        variants = (True, False, None, float('nan'), float('inf'), -float('inf'), 2)
        original = RecordSessionCalculations._consume_message
        def captured(owner, update):
            """复制本条合成值。参数: 原owner/update。返回: 原返回。异常: 原执行错。"""
            values = dict(update.values)
            values['Direction'] = variants[update.sequence]
            if update.sequence == 6:
                values.pop('Power', None)
                values.pop('Direction', None)
            return original(owner, replace(update, values=values))
        for backend in ('reference', 'numpy'):
            work, _, plan = self.fixture(backend=backend, batch=2, rows=tuple((0, 4000, 1) for _ in variants))
            with patch.object(RecordSessionCalculations, '_consume_message', captured):
                result = self.run_plan(work, plan)
            positive = [row for row in self.rows(result, 'contributions') if row.calculation_id == 'positive']
            self.assertEqual(tuple(row.value for row in positive), (400., None, None, None, None, None, None))
            self.assertEqual(tuple(row.reason for row in positive), ('contributed', 'condition_false',
                'missing_input', 'nonfinite_input', 'nonfinite_input', 'nonfinite_input', 'missing_input'))
            trace = self.trace_values(result)
            self.assertIs(trace[0]['Direction'], True)
            self.assertIs(trace[1]['Direction'], False)
            self.assertIsNone(trace[2]['Direction'])
            self.assertEqual([trace[i]['Direction'] for i in (3, 4, 5)],
                             [{'nonfinite': 'nan'}, {'nonfinite': 'inf'}, {'nonfinite': '-inf'}])
            for index in range(2, 6):
                self.assertTrue(positive[index].quality & (Q.MISSING if index == 2 else Q.NONFINITE))
                self.assertFalse(positive[index].quality & Q.DECODE_ERROR)
            summaries = {row.calculation_id: row for row in self.rows(result, 'summary')}
            self.assertEqual(summaries['positive'].value, 400.)
            self.assertEqual((summaries['negative'].value, summaries['negative'].reason), (None, 'all_skipped'))
            self.assertEqual(result.metadata.input_diagnostics[0].record_count, len(variants))

    def test_expression_failure_remains_primary_when_direction_also_invalid(self):
        """除零失败原因优先；合并质量仍保留同条方向缺失或非有限事实。"""
        original = RecordSessionCalculations._consume_message
        def captured(owner, update):
            """仅修改本条合成方向。参数: 原owner/update。返回: 原返回。异常: 原执行错。"""
            values = dict(update.values)
            values['Direction'] = None if update.sequence == 0 else float('nan')
            return original(owner, replace(update, values=values))
        for backend in ('reference', 'numpy'):
            work, _, plan = self.fixture(backend=backend, rows=((0, 0, 1), (0, 0, 1)),
                expression='(power / power) * period', unit='s')
            with patch.object(RecordSessionCalculations, '_consume_message', captured):
                result = self.run_plan(work, plan)
            rows = self.rows(result, 'contributions')
            self.assertEqual(len(rows), 4)
            for row in rows:
                self.assertEqual(row.reason, 'evaluation_error')
                self.assertIsNone(row.value)
                self.assertTrue(row.quality & (Q.MISSING if row.original_sequence == 0 else Q.NONFINITE))
            self.assertTrue(all(row.reason == 'all_skipped' for row in self.rows(result, 'summary')))

    def test_no_evaluations_other_bucket_zero_and_final_round_are_distinct(self):
        """空、跳过、有效零分开；两条4e-7只在公开最终汇总舍入。"""
        for backend in ('reference', 'numpy'):
            for data, expected, reason, count in (((), None, 'no_evaluations', 0),
                    (((0, 4000, 0),), None, 'all_skipped', 1), (((0, 0, 1),), 0., 'ok', 1)):
                work, _, plan = self.fixture(backend=backend, rows=data)
                result = self.run_plan(work, plan)
                summaries = {row.calculation_id: row for row in self.rows(result, 'summary')}
                self.assertEqual((summaries['positive'].value, summaries['positive'].reason), (expected, reason))
                self.assertEqual(self.snapshots['positive'].evaluation_count, count)
                self.assertEqual(summaries['negative'].reason, 'no_evaluations' if count == 0 else 'all_skipped')
                self.assertIsNone(summaries['negative'].value)
            work, _, plan = self.fixture(backend=backend, rows=((0, 4000, 1), (0, 4000, 1)), period=1e-10)
            result = self.run_plan(work, plan)
            summary = next(row for row in self.rows(result, 'summary') if row.calculation_id == 'positive')
            self.assertAlmostEqual(self.snapshots['positive'].value, 8e-7, delta=1e-18)
            self.assertEqual(summary.value, 1e-6)
            self.assertEqual(tuple(row.value for row in self.rows(result, 'contributions')
                                  if row.calculation_id == 'negative'), (None, None))

    def test_repeat_csv_jsonl_publish_preserves_trace_without_recompute(self):
        """两格式各发布两次，汇总/贡献/原值追溯保持字节一致且不重新消费。"""
        for tables in ('csv', 'jsonl'):
            work, _, plan = self.fixture(rows=((0, 4000, 2), (0, 4000, -1)), tables=tables)
            result = self.run_plan(work, plan)
            self.assertEqual([v['Direction'] for v in self.trace_values(result).values()], [2, -1])
            with patch.object(CurrentMessageCalculation, 'consume', side_effect=AssertionError('发布重算')):
                first, second = result.write(work/'published1'), result.write(work/'published2')
            self.assertEqual(first.row_counts, second.row_counts)
            for table in ('calculations', 'contributions', 'input_trace'):
                self.assertEqual((work/'published1'/f'{table}.{tables}').read_bytes(),
                                 (work/'published2'/f'{table}.{tables}').read_bytes())
            budget = result.spool.budget
            result.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_runtime_rechecks_direction_after_static_validation(self):
        """公开静态校验之后改变typed方向，当前计算器仍拒绝另一个消息字段。"""
        work, _, plan = self.fixture(other=True)
        original = CurrentMessageCalculation.__init__
        state = {}
        def changed(owner, calculation, sources, bindings, session_id, budget, **options):
            """只改当前构造入参，退出恢复。参数: 原构造参数。返回: None。异常: 原拒绝。"""
            selection = calculation.disjunction
            state['budget'] = budget
            try:
                object.__setattr__(calculation, 'disjunction', LegacyDisjunction('other', 'positive'))
                return original(owner, calculation, sources, bindings, session_id, budget, **options)
            finally:
                object.__setattr__(calculation, 'disjunction', selection)
        with patch.object(CurrentMessageCalculation, '__init__', changed):
            with self.assertRaises(AnalysisError) as caught:
                AnalysisRunner().run(plan, work_dir=work/'run')
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertIn('update_message', str(caught.exception.__cause__))
        self.assertEqual(state['budget'].ram_bytes, 0)

    def test_trace_cancellation_retains_real_reader_and_does_not_pin_unpaid_trace(self):
        """当前贡献已写后取消且持续退款失败，同一最高owner恢复关闭，不重放贡献。"""
        work, _, plan = self.fixture(batch=1, rows=((0, 4000, 1), (1, 4000, -1)))
        original = RecordSessionCalculations._emit_contribution
        release = ResourceBudget.release_ram
        marker, state = KeyboardInterrupt('contribution cancellation'), {'active': False, 'calls': 0}
        def cancelled(owner, *args, **kwargs):
            """保留真实输出后取消。参数: 原回调参数。返回: 无。异常: marker。"""
            original(owner, *args, **kwargs)
            state['active'] = True
            raise marker
        def blocked(budget, amount):
            """只阻断故障后的真实退款。参数: 账本/费用。返回: 原返回。异常: marker。"""
            if state['active'] and amount:
                state['calls'] += 1
                raise marker
            return release(budget, amount)
        with patch.object(RecordSessionCalculations, '_emit_contribution', cancelled), \
                patch.object(ResourceBudget, 'release_ram', blocked):
            with self.assertRaises(KeyboardInterrupt) as caught:
                AnalysisRunner().run(plan, work_dir=work/'run')
            self.assertIs(caught.exception, marker)
            owner = marker.runner_cleanup_owner
            self.addCleanup(owner.close)
            self.assertIs(type(owner), RunSession)
            self.assertGreater(owner._budget.ram_bytes, 0)
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.assertGreaterEqual(state['calls'], 3)
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(owner._budget.ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
