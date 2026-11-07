"""通过公共计划和AnalysisRunner验收点事件配对，全部输入为明确的合成布尔信号。

覆盖同刻、截止、缺失、跨批、双后端、独立输出表和失败清理。结果与手算值
比较，不调用被测配对器来制造期望；工作数据只写仓库work（home的E盘映射）。
"""
from published_paths import published_file


from configuration_fixtures import current_fixture

import copy
import csv
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, AnalysisRunner, validate_analysis_plan, explain_analysis_plan, PlanValidationError
from chronaxis.results.codec import encode_row, decode_row
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import AnalysisError, BudgetExceededError
from chronaxis.execution.record_sequences import RecordSequences
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution import record_sequences as sequence_module


ROOT = Path(__file__).resolve().parents[2]


def config_fixture():
    """生成四次请求的手算样例：匹配、缺失、截止匹配、正常超时。

    参数: 无。返回: 独立JSON字典。异常: 无主动异常，不访问文件。
    """
    values = [(0, False, False), (1, True, False), (2, False, False), (3, False, True),
              (4, True, False), (5, False, None), (6, False, False), (7, True, False),
              (8, False, False), (9, False, True), (10, True, False), (12, False, False)]
    return dict(config_version=4,
        dataset=dict(name='sample', entity='device', session='session', domain=dict(start='0ns', end='12ns')),
        sources=[dict(name='input', source_type='memory', time=dict(time_type='relative', unit='ns', origin='clock'),
            rows=[dict(time=f'{time}ns', values={'request': a, 'response': b}) for time, a, b in values])],
        signals=[dict(name=name, source='input', field=name, dtype='bool', unit='1', valid_for='20ns')
            for name in ('request', 'response')],
        rules=[dict(name='request_edge', rule_type='rising_edge', condition='request'),
               dict(name='response_edge', rule_type='rising_edge', condition='response')],
        sequences=[dict(name='reply', start='request_edge', response='response_edge', min_delay='0ns', max_delay='2ns')],
        execution=dict(batch_rows=2, result_buffer_rows=1, memory_budget_bytes=256 * 1024**2),
        outputs=dict(tables='jsonl'), metadata=dict(device_label='home', data_kind='synthetic'))


class SequenceRunnerTests(unittest.TestCase):
    """每次运行有独立目录，显式关闭结果后共享RAM必须归零。"""

    def run_config(self, config):
        """调用公开入口并登记最高结果owner清理。

        参数: config为合成配置。返回: AnalysisResult。异常: 原计划/执行错误。
        """
        path = ROOT / 'work/m3-sequence-public-home-20261022/tests' / uuid4().hex
        result = AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)), work_dir=path)
        self.addCleanup(result.close)
        return result

    def test_plan_schema_and_reports(self):
        """结构、静态能力、解释依赖一致，未配置配对不多报能力。

        参数: 无。返回: None。异常: 任一声明不符使测试失败。
        """
        config = config_fixture()
        schema = json.loads((ROOT / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(current_fixture(config))
        plan = AnalysisPlan.from_dict(current_fixture(config))
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        node = next(item for item in explain_analysis_plan(plan).nodes if item.node_id == 'reply')
        self.assertEqual(node.dependencies, ('request', 'response'))
        for changes in ({'start': 'missing'}, {'max_delay': 'bad'}, {'max_pending': True},
                        {'min_delay': '3ns'}, {'name': 'request_edge'}, {'extra': 1}):
            broken = copy.deepcopy(config)
            broken['sequences'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(broken))
        invalid = replace(plan, sequences=(replace(plan.sequences[0], start_rule='missing'),))
        self.assertFalse(validate_analysis_plan(invalid).execution_ready)
        self.assertEqual(explain_analysis_plan(invalid).nodes[-1].backend, 'unavailable')

    def test_hand_calculated_backends_and_batches(self):
        """两个后端和1/2/7行批次都得出四项手算结论。

        参数: 无。返回: None。异常: 状态、延迟、整数身份或资源差异使测试失败。
        """
        baseline = None
        for backend in ('reference', 'numpy'):
            for batch in (1, 2, 7):
                config = config_fixture()
                config['execution'].update(backend=backend, batch_rows=batch)
                result = self.run_config(config)
                events = {r.event_id:r for r in result.iter_events()}
                rows = tuple(result.iter_sequences())
                actual = [(events[r.request_id].confirmed_ns, r.status, r.decided_ns, r.delay_ns) for r in rows]
                self.assertEqual(actual, [(1, 'matched', 3, 2), (4, 'indeterminate', 6, None),
                                          (7, 'matched', 9, 2), (10, 'no_response', 12, None)])
                self.assertNotEqual(int(rows[1].quality), 0)
                self.assertEqual(int(rows[-1].quality), 0)
                values = tuple(rows)
                if baseline is None:
                    baseline = values
                self.assertEqual(values, baseline)
                for row in rows:
                    self.assertEqual(decode_row(encode_row(row, 1048576), 1048576), row)
                budget = result.spool.budget
                result.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_empty_and_early_eof(self):
        """空输入不造请求，真实观测提前结束将等待中的请求标不确定。

        参数: 无。返回: None。异常: 伪事件或伪正常超时使测试失败。
        """
        empty = config_fixture()
        empty['sources'][0]['rows'] = []
        self.assertEqual(tuple(self.run_config(empty).iter_sequences()), ())
        early = config_fixture()
        early['sources'][0]['rows'] = early['sources'][0]['rows'][:3]
        row, = self.run_config(early).iter_sequences()
        self.assertEqual((row.status, row.decided_ns), ('indeterminate', 2))

    def test_shorter_response_source_does_not_prove_timeout(self):
        """请求来源到12ns、响应只到5ns，保留长会话但后续不伪证无响应。

        参数: 无。返回: None。异常: 来源结束被TTL延续成完整观测使测试失败。
        """
        config = config_fixture()
        response = dict(name='reply_input', source_type='memory',
            time=dict(time_type='relative', unit='ns', origin='clock'),
            rows=[dict(time=f'{t}ns', values={'response': False}) for t in (0, 5)])
        config['sources'].append(response)
        config['signals'][1]['source'] = 'reply_input'
        rows = tuple(self.run_config(config).iter_sequences())
        self.assertEqual(rows[0].status, 'no_response')
        self.assertTrue(all(row.status == 'indeterminate' for row in rows[1:]))

    def test_publish_both_formats_and_old_tables(self):
        """CSV常用列和JSONL完整行都可读；旧计划仍只有原三表。

        参数: 无。返回: None。异常: 发布、行数或关联错误使测试失败。
        """
        for fmt in ('csv', 'jsonl'):
            config = config_fixture()
            config['outputs']['tables'] = fmt
            result = self.run_config(config)
            out = ROOT / 'work/m3-sequence-public-home-20261022/publish' / uuid4().hex
            manifest = result.write(out)
            self.assertEqual(dict(manifest.row_counts)['sequences'], 4)
            path = published_file(manifest,'sequences.'+fmt)
            if fmt == 'csv':
                with path.open(encoding='utf-8-sig', newline='') as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(rows[0]['delay_ns'], '2')
                self.assertEqual(rows[1]['status'], 'indeterminate')
            else:
                rows = [decode_row(line, 1048576) for line in path.read_bytes().splitlines()]
                self.assertEqual(rows[0].delay_ns, 2)
        config = config_fixture()
        del config['sequences']
        old = self.run_config(config)
        self.assertEqual(old.spool.tables, ('events',))
        self.assertEqual(tuple(old.iter_sequences()), ())

    def test_capacity_failure_and_cancellation_clear_budget(self):
        """容量和取消通过公共AnalysisRunner失败，已付候选及结果资源全部归还。

        参数: 无。返回: None。异常: 错误被吞、伪成功或RAM残留使测试失败。
        """
        config = config_fixture()
        config['sequences'][0].update(max_pending=1, max_delay='20ns', min_delay='10ns')
        budgets = []
        original = ResourceBudget.__init__
        def capture(owner, *args, **kwargs):
            """记录真实账本供失败后核对。参数: 构造实参。返回: None。异常: 原错误。"""
            original(owner, *args, **kwargs)
            budgets.append(owner)
        with patch.object(ResourceBudget, '__init__', capture):
            with self.assertRaises(BudgetExceededError):
                self.run_config(config)
        self.assertTrue(budgets)
        self.assertTrue(all(item.ram_bytes == 0 for item in budgets))
        original_observe = RecordSequences._consume
        def cancel(owner, *args):
            """先真实登记候选再取消。参数: owner/step。返回: None。异常: KeyboardInterrupt。"""
            original_observe(owner, *args)
            if owner._pending_cost:
                raise KeyboardInterrupt('synthetic cancel')
        budgets.clear()
        with patch.object(ResourceBudget, '__init__', capture), patch.object(RecordSequences, '_consume', cancel):
            with self.assertRaises(KeyboardInterrupt):
                self.run_config(config_fixture())
        self.assertTrue(all(item.ram_bytes == 0 for item in budgets))

    def test_simultaneous_fifo_minimum_falling_and_expired_capacity(self):
        """手算零延迟、FIFO、最小等待、下降沿响应及过期候选不占容量。

        参数: 无。返回: None。异常: 配对优先级或容量错误使测试失败。
        """
        config = config_fixture()
        config['sequences'][0].update(min_delay='2ns', max_delay='5ns')
        config['sources'][0]['rows'] = [dict(time=f'{t}ns', values={'request': a, 'response': b})
            for t, a, b in [(0, False, True), (1, True, True), (2, False, False),
                           (3, True, True), (4, False, False), (5, False, True), (6, False, False), (12, False, False)]]
        config['rules'][1]['rule_type'] = 'falling_edge'
        result = self.run_config(config)
        events = {r.event_id:r for r in result.iter_events()}
        rows = tuple(result.iter_sequences())
        self.assertEqual([(events[r.request_id].confirmed_ns, events[r.response_id].confirmed_ns) for r in rows], [(1, 4), (3, 6)])
        # 同一真实事件可在明确相同的两角色中作为零延迟请求/响应，不跨实体消费。
        config['sequences'][0].update(response='request_edge', min_delay='0ns', max_delay='0ns', max_pending=1)
        self.assertTrue(all(r.delay_ns == 0 for r in self.run_config(config).iter_sequences()))
        # 两次请求相隔大于截止；cap=1必须正常，旧候选在当前入队之前已经结算。
        config['sequences'][0].update(response='response_edge', min_delay='0ns', max_delay='1ns')
        rows = tuple(self.run_config(config).iter_sequences())
        self.assertEqual(len(rows), 2)

    def test_reject_activity_unsynchronized_and_typed_id_collision(self):
        """不允许把延迟交付的活动或独立相对时钟当作可实时配对点。

        参数: 无。返回: None。异常: 错误配置误通过使测试失败。
        """
        config = config_fixture()
        config['rules'][0].update(rule_type='condition_duration', duration_comparison='>=', minimum_duration='0ns')
        with self.assertRaisesRegex(PlanValidationError, '点规则'):
            AnalysisPlan.from_dict(current_fixture(config))
        config = config_fixture()
        other = copy.deepcopy(config['sources'][0])
        other.update(name='other', time=dict(time_type='relative', unit='ns', origin='independent'))
        config['sources'].append(other)
        config['signals'][1]['source'] = 'other'
        with self.assertRaisesRegex(PlanValidationError, '同步'):
            AnalysisPlan.from_dict(current_fixture(config))
        plan = AnalysisPlan.from_dict(current_fixture(config_fixture()))
        duplicate = replace(plan, sequences=(replace(plan.sequences[0], sequence_id='request_edge'),))
        self.assertFalse(validate_analysis_plan(duplicate).valid)

    def test_typed_delay_range_checked_before_run(self):
        """类型化延迟不能绕过纳秒int64范围检查。

        参数: 无。返回: None。异常: 非法typed声明或跨时钟常量被静态接受使测试失败。
        """
        plan = AnalysisPlan.from_dict(current_fixture(config_fixture()))
        with self.assertRaises((ValueError, OverflowError)):
            replace(plan.sequences[0], max_delay_ns=2**63)

    def test_constant_clock_checked_before_run(self):
        """常量规则的dataset时钟也必须参与配对同步检查。

        参数: 无。返回: None。异常: 跨时钟常量被静态接受使测试失败。
        """
        config = config_fixture()
        other = copy.deepcopy(config['sources'][0])
        other.update(name='other', time=dict(time_type='relative', unit='ns', origin='independent'))
        config['sources'].append(other)
        config['signals'][1]['source'] = 'other'
        config['rules'][0].update(condition='True', emit_initial=True)
        with self.assertRaisesRegex(PlanValidationError, '时钟'):
            AnalysisPlan.from_dict(current_fixture(config))

    def test_optional_pairing_preserves_ordinary_results_and_single_source_scan(self):
        """配对复用事件步骤，不增加来源扫描，普通事件与指标保持原值和身份，新增配对行只改变全局输出序号。

        参数: 无。返回: None。异常: 额外来源读取或旧结果改变使测试失败。
        """
        config = config_fixture()
        config['calculations'] = [dict(name='duration', scope='session', operation='duration', condition='request')]
        scans = []
        original = BudgetedMemorySourceAdapter.iter_batches
        def capture(owner, *args, **kwargs):
            """记录真实来源扫描入口。参数: adapter实参。返回: 原游标。异常: 原错误。"""
            scans.append(owner)
            return original(owner, *args, **kwargs)
        with patch.object(BudgetedMemorySourceAdapter, 'iter_batches', capture):
            paired = self.run_config(config)
        self.assertEqual(len(scans), 1)
        del config['sequences']
        plain = self.run_config(config)
        for factory in ('iter_events','iter_calculations'):
            actual=tuple(getattr(paired,factory)())
            expected=tuple(getattr(plain,factory)())
            self.assertEqual(tuple(replace(row,sequence=0) for row in actual),
                             tuple(replace(row,sequence=0) for row in expected))
        all_rows=tuple(paired.iter_events())+tuple(paired.iter_calculations())+tuple(paired.iter_sequences())
        self.assertEqual(len({row.sequence for row in all_rows}),len(all_rows))

    def test_pending_ram_transactions_and_spool_failure(self):
        """候选申请/释放取消及内部写盘失败不遗失最高owner或预算。

        参数: 无。返回: None。异常: 未传播错误或预算残留使测试失败。
        """
        for action in ('reserve_after', 'release_before', 'release_after', 'append'):
            owners, tripped = [], []
            original_observe = RecordSequences.observe
            def observe(owner, *args):
                """保留本次真实owner用于清理核对。参数: owner/step。返回: 原返回。异常: 原错误。"""
                if not owners:
                    owners.append(owner)
                return original_observe(owner, *args)
            name = '_reserve_owned_ram' if action == 'reserve_after' else '_release_owned_ram'
            original_transaction = getattr(sequence_module, name)
            def transaction(owner, amount, slot):
                """在候选事务前后取消一次。参数: 真实费用槽。返回: None。异常: KeyboardInterrupt。"""
                target = slot == '_pending_cost' and amount > 0 and not tripped
                if target and action == 'release_before':
                    tripped.append(True)
                    raise KeyboardInterrupt(action)
                original_transaction(owner, amount, slot)
                if target:
                    tripped.append(True)
                    raise KeyboardInterrupt(action)
            from chronaxis.results.spool import ResultSpool
            original_append = ResultSpool.append
            def append(owner, row):
                """真实追加配对行后模拟IO失败。参数: spool/row。返回: None。异常: OSError。"""
                original_append(owner, row)
                if type(row).__name__ == 'SummarySequenceRow' and not tripped:
                    tripped.append(True)
                    raise OSError('synthetic sequence disk failure')
            injection = patch.object(ResultSpool, 'append', append) if action == 'append' else patch.object(sequence_module, name, transaction)
            with self.subTest(action=action), patch.object(RecordSequences, 'observe', observe), injection:
                with self.assertRaises(AnalysisError if action == 'append' else KeyboardInterrupt):
                    self.run_config(config_fixture())
            self.assertTrue(tripped)
            self.assertTrue(owners[0]._closed)
            self.assertEqual(owners[0]._budget.ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
