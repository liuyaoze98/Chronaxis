"""从公共AnalysisRunner验证同次CAN逐消息累计、追溯及完整资源责任。

所有BLF/DBC是本例新建的合成数据；4000W乘0.1s每条400J，两条同刻应为800J。
真实旧链在spawn子进程运行，参考与NumPy分别求值；只复用同一手算预期。
本例同时检查缺值、请求端点、最终舍入、公开表和重复发布；不把它当用户日志验收。
故障注入只包新计算流的真实边界，不修改旧解码、冻结源码或测试真值。
所有资源、配置与发布均留在work；result/恢复owner关闭后账本必须归零。
"""
from published_paths import published_file


from configuration_fixtures import current_fixture

import json
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.types import QualityFlag as Q
from chronaxis.execution.record_session_calculations import RecordSessionCalculations
from chronaxis.execution.record_source_cursor import RecordSourceCursor
from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from chronaxis.execution.run_session import RunSession
from chronaxis.results.budget import ResourceBudget


class RunMessageCalculationTests(unittest.TestCase):
    """逐例创建独立实际输入，以小夹具核对两个公开消息表及关闭事实。"""

    def fixture(self, *, backend='numpy', batch=2, frames=None, domain=('0s', '4s'),
                expression='power * period', period=0.1, calculation_count=1, tables='jsonl'):
        """生成单通道功率报文和严格公开配置，普通历史显式取同刻最后一条。

        参数: backend/batch为实际执行选项；frames是(秒,ID,bytes)tuple；None使用
            两条同刻4000、一条缺值、一条未知消息。其余参数控制请求、表达式和输出。
        返回: (work,config,plan)。异常: 原文件/配置错误；缺可选CAN依赖明确skip。
        """
        try:
            import can
        except ModuleNotFoundError as exc:
            self.skipTest('缺可选CAN依赖: ' + exc.name)
        work = Path(__file__).resolve().parents[2] / 'work/m2-legacy-tests/public-runner' / uuid4().hex
        work.mkdir(parents=True)
        dbc, blf = work / 'power.dbc', work / 'power.blf'
        dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Power: 2 Node\n SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n', encoding='utf-8')
        if frames is None:
            frames = ((0, 256, b'\xa0\x0f'), (0, 256, b'\xa0\x0f'),
                (1, 256, b''), (2, 257, b'\xff'))
        writer = can.BLFWriter(blf)
        try:
            for second, frame_id, payload in frames:
                writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                    arbitration_id=frame_id, is_extended_id=False, channel=0, data=payload))
        finally:
            writer.stop()
        config = dict(config_version=4,
            dataset=dict(name='legacy_demo', entity='synthetic', session='session',
                domain=dict(start=domain[0], end=domain[1])),
            sources=[dict(name='bus', source_type='can_blf', path=str(blf),
                legacy_profile='sclicer-functions-v1', reader_options=dict(decode_policy='legacy'), dbc_by_channel={'1': str(dbc)},
                time=dict(time_type='relative', unit='s', origin='message_clock', offset='-1700000000s'))],
            signals=[dict(name='power', source='bus', field=dict(channel=1,
                signal='Power', frame_id=256, is_extended=False, is_fd=False),
                dtype='float64', unit='W', valid_for='10s', same_time_policy='last_by_sequence')],
            rules=[], windows=[], calculations=[],
            message_calculations=[dict(name='energy'+str(index), source='bus', profile='sclicer-functions-v1',
                operation='legacy_sum', message_policy='current_message-v1',
                update_message=dict(channel=1, frame_id=256, is_extended=False, is_fd=False),
                expr=expression, unit='J', parameters=dict(period=dict(value=period, unit='s')))
                for index in range(calculation_count)],
            execution=dict(backend=backend, batch_rows=batch, result_buffer_rows=1,
                memory_budget_bytes=256*1024**2), outputs=dict(tables=tables, contributions='full'),
            diagnostics=dict(trace=True, integrity=True),
            metadata=dict(device_label='home', data_kind='synthetic'))
        (work/'plan.json').write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        return work, config, AnalysisPlan.from_dict(current_fixture(config), base_dir=work)

    def run_plan(self, work, plan, name='run'):
        """实际公开运行并登记关闭。参数: work/plan/name。返回: AnalysisResult。异常: 原运行错误。"""
        result = AnalysisRunner().run(plan, work_dir=work/name)
        self.addCleanup(result.close)
        return result

    def rows(self, result, kind):
        """耗尽并关闭实际typed游标。参数: result与两表kind。返回: tuple。异常: 原游标错误。"""
        reader = (result.iter_calculations() if kind == 'summary'
            else result.iter_contributions())
        try:
            return tuple(reader)
        finally:
            reader.close()

    def test_same_time_missing_and_full_provenance_all_backends_batches(self):
        """同刻两条各400J；缺值和原序由贡献/追溯关联核对。参数: 无。返回: None。异常: 断言。"""
        for backend in ('reference', 'numpy'):
            for batch in (1, 2, 7):
                with self.subTest(backend=backend, batch=batch):
                    work, _, plan = self.fixture(backend=backend, batch=batch)
                    result = self.run_plan(work, plan)
                    summary, = self.rows(result, 'summary')
                    rows = self.rows(result, 'contributions')
                    traces = tuple(result.iter_input_trace())
                    self.assertEqual((summary.value, summary.unit, summary.status), (800.0, 'J', 'partial'))
                    self.assertEqual(tuple(row.original_sequence for row in rows), (0, 1, 2))
                    self.assertEqual(tuple(row.evaluation_index for row in rows), (0, 1, 2))
                    self.assertEqual(tuple(row.value for row in rows), (400.0, 400.0, None))
                    self.assertEqual(rows[2].reason, 'missing_input')
                    self.assertTrue(summary.quality & Q.MISSING)
                    self.assertFalse(rows[2].quality & Q.DECODE_ERROR)
                    self.assertEqual([json.loads(row.values_json) for row in traces],
                                     [{'Power': 4000}, {'Power': 4000}, {'Power': None}])
                    self.assertEqual([row.time_ns for row in traces], [0, 0, 10**9])
                    fact, = result.metadata.input_diagnostics
                    self.assertEqual((fact.record_count, fact.source_eof), (3, True))
                    self.assertEqual(len(fact.sha256), 64)
                    self.assertEqual(len({row.sequence for row in (*rows, *traces, summary)}), 7)
                    budget = result.spool.budget
                    result.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_actual_last_point_counts_but_requested_right_endpoint_does_not(self):
        """文件末点2秒在请求内可累计，请求右端2秒消息排除；不沿普通半开观测区间漏末点。

        参数: 无。返回: None。异常: 端点筛选或手算不符即失败。
        """
        for backend in ('reference', 'numpy'):
            for end, expected in (('3s', 1200.0), ('2s', 800.0)):
                with self.subTest(backend=backend, end=end):
                    frames = tuple((second, 256, b'\xa0\x0f') for second in (0, 1, 2))
                    work, _, plan = self.fixture(backend=backend, frames=frames, domain=('0s', end))
                    result = self.run_plan(work, plan)
                    summary, = self.rows(result, 'summary')
                    self.assertEqual(summary.value, expected)
                    self.assertEqual(max(row.time_ns for row in result.iter_input_trace()), 2000000000)

    def test_no_evaluations_all_skipped_and_valid_zero_are_distinct(self):
        """无匹配、空文件、全缺值保持空汇总；真实零功率贡献返回0.0。

        参数: 无。返回: None。异常: 空与零被混合或计数错误即失败。
        """
        cases = (((), None, 'no_evaluations', 0),
            (((0, 257, b'\x00'),), None, 'no_evaluations', 0),
            (((0, 256, b''),), None, 'all_skipped', 1),
            (((0, 256, b'\x00\x00'),), 0.0, None, 1))
        for backend in ('reference', 'numpy'):
            for frames, expected, reason, count in cases:
                with self.subTest(backend=backend, frames=frames):
                    work, _, plan = self.fixture(backend=backend, frames=frames)
                    result = self.run_plan(work, plan)
                    row, = self.rows(result, 'summary')
                    self.assertEqual((row.value, row.reason, len(self.rows(result, 'contributions'))),
                        (expected, reason or 'ok', count))
                    self.assertEqual(len(self.rows(result, 'contributions')), count)

    def test_only_final_sum_is_rounded(self):
        """两次4e-7J应最终8e-7舍入为1e-6，不能逐条舍入为0。

        参数: 无。返回: None。异常: 逐条舍入、单位错误或后端差异即失败。
        """
        for backend in ('reference', 'numpy'):
            work, _, plan = self.fixture(backend=backend, period=1e-10,
                frames=((0, 256, b'\xa0\x0f'), (0, 256, b'\xa0\x0f')))
            result = self.run_plan(work, plan)
            row, = self.rows(result, 'summary')
            contributions = self.rows(result, 'contributions')
            # 乘法的相邻ULP不改变舍入门槛；绝对容差远小于任何逐条round6误差。
            self.assertAlmostEqual(sum(item.value for item in contributions), 8e-7, delta=1e-18)
            self.assertEqual(row.value, 1e-6)
            self.assertEqual(len(contributions), 2)
            for item in contributions:
                self.assertAlmostEqual(item.value, 4e-7, delta=1e-18)

    def test_calculation_ids_disambiguate_shared_source_sequence(self):
        """每条原帧先算energy0再算energy1；来源原序共用，计算ID区分各桶。

        参数: 无。返回: None。异常: 声明顺序、求值身份、累计器隔离错误即失败。
        """
        work, _, plan = self.fixture(calculation_count=2)
        result = self.run_plan(work, plan)
        # 公开贡献游标按calculation/evaluation排序；重新按全局sequence还原真实交付顺序。
        rows = sorted(self.rows(result, 'contributions'), key=lambda row: row.sequence)
        self.assertEqual(tuple((row.calculation_id, row.original_sequence, row.evaluation_index) for row in rows),
            (('energy0', 0, 0), ('energy1', 0, 0), ('energy0', 1, 1),
             ('energy1', 1, 1), ('energy0', 2, 2), ('energy1', 2, 2)))
        self.assertEqual(tuple(row.value for row in self.rows(result, 'summary')), (800.0, 800.0))

    def test_repeat_publish_does_not_recompute_and_stable_identity_omits_run_uuid(self):
        """同计划重复运行稳定输入摘要相同；两种格式重复发布均只读既有结果。

        参数: 无。返回: None。异常: 发布重算、漏表、身份不稳定或序列化错误即失败。
        """
        for tables in ('csv', 'jsonl'):
            work, _, plan = self.fixture(tables=tables)
            result = self.run_plan(work, plan)
            again = self.run_plan(work, plan, 'again')
            self.assertEqual(result.metadata.input_diagnostics, again.metadata.input_diagnostics)
            self.assertNotEqual(result.metadata.run_id, again.metadata.run_id)
            with patch.object(CurrentMessageCalculation, 'consume', side_effect=AssertionError('发布不应重算')):
                first, second = result.write(work/'published1'), result.write(work/'published2')
            self.assertEqual(first.row_counts, second.row_counts)
            for name in ('calculations', 'contributions', 'input_trace'):
                left, right = published_file(first,name+'.'+tables), published_file(second,name+'.'+tables)
                self.assertEqual(left.read_bytes(), right.read_bytes())
                self.assertGreater(left.stat().st_size, 0)

    def test_new_driver_cancellation_retains_highest_owner_until_real_release_recovers(self):
        """真实消息批累计后取消，持续释放失败保最高owner并能恢复。参数: 无。返回: None。异常: 断言。"""
        work, config, _ = self.fixture()
        config['outputs']['contributions'] = 'none'
        plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=work)
        flush, release = RecordSessionCalculations._flush_messages, ResourceBudget.release_ram
        marker = KeyboardInterrupt('current message batch cancellation')
        state = dict(active=False, calls=0)
        def loaded(owner):
            """先执行真实批，再抛原取消。参数: owner。返回: None。异常: marker。"""
            self.assertTrue(owner._message_buffer)
            flush(owner)
            state['active'] = True
            raise marker
        def interrupted_release(budget, amount):
            """故障期间不抵费。参数: 账本/费用。返回: None。异常: marker。"""
            if state['active'] and amount:
                state['calls'] += 1
                raise marker
            return release(budget, amount)
        with patch.object(RecordSessionCalculations, '_flush_messages', loaded), patch.object(ResourceBudget, 'release_ram', interrupted_release):
            with self.assertRaises(KeyboardInterrupt) as caught:
                AnalysisRunner().run(plan, work_dir=work/'run')
            self.assertIs(caught.exception, marker)
            owner = marker.runner_cleanup_owner
            self.assertIs(type(owner), RunSession)
            self.addCleanup(owner.close)
            self.assertIsNotNone(owner._record_calculations)
            self.assertGreater(owner._budget.ram_bytes, 0)
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.assertGreaterEqual(state['calls'], 3)
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(owner._budget.ram_bytes, 0)

    def test_sparse_targets_fill_real_array_batches_without_losing_missing_rows(self):
        """九个稀疏同刻目标集中为实际九条，缺值仍记跳过，两个指标按原帧次序交付。

        参数: 无。返回: None。异常: 批量未实际形成、原序/缺值/手算或预算不符令断言失败。
        每个目标前放九个无关帧；八条4000W各乘0.1s合计3200J，另一次缺值不贡献。
        """
        frames = []
        for index in range(9):
            frames.extend((0, 257, b'\x00\x00') for _ in range(9))
            frames.append((0, 256, b'' if index == 4 else b'\xa0\x0f'))
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                work, _, plan = self.fixture(backend=backend, batch=64, frames=tuple(frames), calculation_count=2)
                sizes = []
                consume = CurrentMessageCalculation.consume
                def observe(owner, updates):
                    """记录真实共同批长度。参数: owner/更新。返回: 原结果。异常: 原错误。"""
                    sizes.append(len(updates))
                    return consume(owner, updates)
                with patch.object(CurrentMessageCalculation, 'consume', observe):
                    result = self.run_plan(work, plan)
                summaries = self.rows(result, 'summary')
                published = self.rows(result, 'contributions')
                # 公开表沿既有calculation/evaluation排序；sequence保存计算流真实交付次序。
                self.assertEqual(tuple(row.calculation_id for row in published), ('energy0',) * 9 + ('energy1',) * 9)
                rows = sorted(published, key=lambda row: row.sequence)
                self.assertEqual(sizes, [1] * 18)
                self.assertEqual(tuple(row.calculation_id for row in rows), ('energy0', 'energy1') * 9)
                self.assertEqual(tuple(row.original_sequence for row in rows),
                    tuple(10 * index + 9 for index in range(9) for _ in range(2)))
                self.assertEqual(tuple(row.evaluation_index for row in rows), tuple(row.original_sequence for row in rows))
                self.assertEqual(tuple(row.time_ns for row in result.iter_input_trace()), (0,) * 9)
                self.assertTrue(all(row.reason == 'missing_input' for row in rows[8:10]))
                for summary in summaries:
                    contributions = [row for row in rows if row.calculation_id == summary.calculation_id]
                    self.assertEqual((summary.value, len(contributions), sum(row.value is not None for row in contributions)), (3200.0, 9, 8))
                self.assertEqual(result.metadata.input_diagnostics[0].record_count, 9)
                # 明细为了全局交付顺序逐条处理；只求总量时仍走真实9条批计算。
                sizes.clear()
                summary_plan = replace(plan, outputs=replace(plan.outputs, contributions='none'))
                with patch.object(CurrentMessageCalculation, 'consume', observe):
                    total = self.run_plan(work, summary_plan, 'summary-only')
                self.assertEqual(sizes, [9, 9])
                self.assertEqual(tuple(row.value for row in total.iter_calculations()), (3200.0, 3200.0))
                total.close()
                budget = result.spool.budget
                result.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_union_of_calculation_selectors_preserves_domain_and_frame_order(self):
        """同一批可装两种指标目标，按原帧交错交付，域外和右端消息不生成求值。

        参数: 无。返回: None。异常: 把选择器并集误作交集、重排指标或遗漏域边界令断言失败。
        域内各有五条4000W/2000W目标，分别累计2000J/1000J；首尾域外目标均不计。
        """
        frames = [(-1, 256, b'\xa0\x0f')]
        for index in range(10):
            frames.extend((0, 257, b'\x00\x00') for _ in range(5))
            frames.append((0, 256, b'\xa0\x0f') if index % 2 == 0 else (0, 512, b'\xd0\x07'))
        frames.append((4, 512, b'\xd0\x07'))
        expected_sequences = tuple(index for index, (second, frame_id, _) in enumerate(frames)
            if 0 <= second < 4 and frame_id in (256, 512))
        for backend in ('reference', 'numpy'):
            for batch in (1, 8):
                with self.subTest(backend=backend, batch=batch):
                    work, config, _ = self.fixture(backend=backend, batch=batch, frames=tuple(frames))
                    dbc = work / 'power.dbc'
                    dbc.write_text(dbc.read_text(encoding='utf-8')
                        + 'BO_ 512 Auxiliary: 2 Node\n SG_ Aux : 0|16@1+ (1,0) [0|65535] "W" Node\n',
                        encoding='utf-8')
                    config['signals'].append(dict(name='aux', source='bus', field=dict(channel=1,
                         signal='Aux', frame_id=512, is_extended=False, is_fd=False),
                        dtype='float64', unit='W', valid_for='10s', same_time_policy='last_by_sequence'))
                    config['message_calculations'].append(dict(config['message_calculations'][0], name='aux_energy',
                        expr='aux * period', update_message=dict(channel=1, frame_id=512,
                            is_extended=False, is_fd=False)))
                    (work / 'plan.json').write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
                    plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=work)
                    result = self.run_plan(work, plan)
                    published = self.rows(result, 'contributions')
                    self.assertEqual(tuple(row.calculation_id for row in published), ('aux_energy',) * 5 + ('energy0',) * 5)
                    # 与单选择器一致，以全局sequence核对计算流，不能改变公开表原排序。
                    rows = sorted(published, key=lambda row: row.sequence)
                    summaries = self.rows(result, 'summary')
                    self.assertEqual(tuple(row.original_sequence for row in rows), expected_sequences)
                    self.assertEqual(tuple(row.calculation_id for row in rows), ('energy0', 'aux_energy') * 5)
                    self.assertEqual(tuple(row.evaluation_index for row in rows), expected_sequences)
                    self.assertEqual({row.calculation_id: row.value for row in summaries},
                        {'energy0': 2000.0, 'aux_energy': 1000.0})
                    self.assertTrue(all(sum(row.calculation_id == summary.calculation_id for row in rows) == 5 for summary in summaries))
                    self.assertEqual(result.metadata.input_diagnostics[0].record_count, 12)
                    budget = result.spool.budget
                    result.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_no_target_still_consumes_all_history_and_verifies_real_eof(self):
        """无目标仍通过真实来源EOF，不能凭空贡献表推断完成。参数: 无。返回: None。异常: 断言。"""
        frames = ((0, 257, b'\x00\x00'),) * 33
        for backend in ('reference', 'numpy'):
            work, _, plan = self.fixture(backend=backend, batch=8, frames=frames)
            completed = []
            original = RecordSourceCursor.peek
            def observed(owner):
                """记录真实EOF及已关闭读取器。参数: owner。返回: 原组。异常: 原错。"""
                group = original(owner)
                if owner._finished:
                    completed.append((owner, owner._read is None, owner._adapter is None))
                return group
            with patch.object(RecordSourceCursor, 'peek', observed):
                result = self.run_plan(work, plan)
            summary, = self.rows(result, 'summary')
            self.assertTrue(completed)
            self.assertTrue(all(read_closed and adapter_closed for _, read_closed, adapter_closed in completed))
            self.assertEqual(self.rows(result, 'contributions'), ())
            self.assertEqual((summary.value, summary.reason, summary.status), (None, 'no_evaluations', 'indeterminate'))
            fact, = result.metadata.input_diagnostics
            self.assertEqual((fact.record_count, fact.source_eof), (0, True))
            budget = result.spool.budget
            result.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_cancellation_in_unselected_tail_closes_reader_and_releases_shared_budget(self):
        """请求右端后的目标帧仍读取；最后一条取消关闭实际来源。参数: 无。返回: None。异常: 断言。"""
        frames = ((0, 256, b'\xa0\x0f'),) + ((4, 256, b'\x00\x00'),) * 31
        work, _, plan = self.fixture(batch=8, frames=frames)
        original = RecordSessionCalculations._consume_message
        marker = KeyboardInterrupt('cancel in unselected source tail')
        state = dict(calls=0, owner=None, cursors=None)
        def interrupted(owner, update):
            """透传实际消息，在最后原序取消。参数: owner/update。返回: 原结果。异常: marker。"""
            state['calls'] += 1
            state['owner'] = owner
            state['cursors'] = tuple(owner._cursors)
            original(owner, update)
            if update.sequence == len(frames)-1:
                raise marker
        with patch.object(RecordSessionCalculations, '_consume_message', interrupted):
            with self.assertRaises(KeyboardInterrupt) as caught:
                AnalysisRunner().run(plan, work_dir=work/'run')
        self.assertIs(caught.exception, marker)
        self.assertEqual(state['calls'], len(frames))
        self.assertTrue(state['owner']._closed)
        self.assertEqual(state['owner']._budget.ram_bytes, 0)
        self.assertTrue(all(cursor._closed and cursor._read is None and cursor._adapter is None for cursor in state['cursors']))


if __name__ == '__main__':
    # spawn子进程只在显式测试入口启动，模块导入不读文件或运行测试。
    unittest.main()
