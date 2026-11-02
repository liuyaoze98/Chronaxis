"""通过公共计划验收滑动窗口规则、事件窗口与两数值后端。

输入为明确手算的内存信号，不读取历史项目；每次运行在E盘work中独立保存。
核对配置/schema、跨批、窗口定时推进、缺口、初始化/锁存及资源关闭。
"""

from configuration_fixtures import current_fixture

import copy
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, AnalysisRunner, validate_analysis_plan, explain_analysis_plan, PlanValidationError
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError
from chronaxis.execution.record_delta_condition import RecordDeltaCondition
from chronaxis.execution import record_delta_condition as delta_module
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.results.codec import encode_row, decode_row

ROOT = Path(__file__).resolve().parents[2]


def delta_config():
    """给出4ns窗两次上升5V的样例。参数: 无。返回: 配置字典。异常: 无。"""
    values = [(0, 0), (2, 0), (4, 5), (6, 5), (8, 0), (10, 0), (12, 5), (14, 5)]
    return dict(config_version=3,
        dataset=dict(name='sample', entity='device', session='session', domain=dict(start='0ns', end='14ns')),
        sources=[dict(name='input', source_type='memory', time=dict(time_type='relative', unit='ns', origin='clock'),
            rows=[dict(time=f'{time}ns', values={'voltage': value}) for time, value in values])],
        signals=[dict(name='voltage', source='input', field='voltage', dtype='int64', unit='V', valid_for='20ns')],
        rules=[dict(name='change', rule_type='window_delta', signal='voltage', window='4ns', direction='rise',
                    threshold=5, monotonic=True, emit_initial=True)],
        execution=dict(batch_rows=2, result_buffer_rows=1, memory_budget_bytes=256 * 1024**2),
        outputs=dict(tables='jsonl'), metadata=dict(device_label='home', data_kind='synthetic'))


class WindowDeltaRunnerTests(unittest.TestCase):
    """公共运行逐次关闭，合成真值不从被测核计算。"""

    def run_config(self, config):
        """运行独立输出并登记关闭。参数: config。返回: AnalysisResult。异常: 原执行错误。"""
        path = ROOT / 'work/m3-window-delta-home-20261022/tests' / uuid4().hex
        result = AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(config)), work_dir=path)
        self.addCleanup(result.close)
        return result

    def test_schema_static_and_invalid(self):
        """结构/schema与静态计划一致。参数: 无。返回: None。异常: 断言失败。"""
        raw = delta_config()
        schema = json.loads((ROOT / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(current_fixture(raw))
        plan = AnalysisPlan.from_dict(current_fixture(raw))
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        self.assertEqual(explain_analysis_plan(plan).nodes[0].dependencies, ('voltage',))
        for changes in ({'signal': 'voltage > 1'}, {'window': '0ns'}, {'threshold': -1},
                        {'monotonic': 'yes'}, {'coverage_policy': 'legacy_samples'},
                        {'retrigger': 'guess'}, {'condition': 'True'}):
            broken = copy.deepcopy(raw)
            broken['rules'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(broken))
        with self.assertRaises(TypeError):
            replace(plan.rules[0], window_delta=None)

    def test_backends_and_input_batches(self):
        """4ns与12ns触发，输入批次不改变事件身份。参数: 无。返回: None。异常: 断言失败。"""
        expected = None
        for backend, batch in (('reference', 1), ('numpy', 2), ('numpy', 16)):
            raw = delta_config()
            raw['execution'].update(backend=backend, batch_rows=batch)
            result = self.run_config(raw)
            rows = list(result.iter_events())
            self.assertEqual([row.confirmed_ns for row in rows], [4, 12])
            events = [row for row in rows]
            if expected is None:
                expected = events
            self.assertEqual(events, expected)
            budget = result.spool.budget
            result.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_initialization_and_once(self):
        """默认不把UNKNOWN→TRUE当边沿；once仅保留首次。参数: 无。返回: None。异常: 断言失败。"""
        for initial, mode, expected in ((False, 'edge', [12]), (True, 'once', [4])):
            raw = delta_config()
            raw['rules'][0].update(emit_initial=initial, retrigger=mode)
            self.assertEqual([row.confirmed_ns for row in self.run_config(raw).iter_events()], expected)

    def test_window_boundary_timer(self):
        """旧下降段移出窗口时恢复单调，无新报文也触发。参数: 无。返回: None。异常: 断言失败。"""
        raw = delta_config()
        raw['sources'][0]['rows'] = [dict(time=f'{time}ns', values={'voltage': value})
                                    for time, value in ((0, 4), (1, 0), (2, 8), (14, 8))]
        # 4ns窗口首次完整时非单调，5ns左端移到1ns后成为0→8。
        for backend in ('reference', 'numpy'):
            raw['execution']['backend'] = backend
            rows = list(self.run_config(raw).iter_events())
            self.assertEqual([row.confirmed_ns for row in rows], [5])

    def test_gap_does_not_create_edge(self):
        """缺口前后不伪造False→True。参数: 无。返回: None。异常: 断言失败。"""
        raw = delta_config()
        raw['rules'][0]['emit_initial'] = False
        raw['sources'][0]['rows'][4]['values']['voltage'] = None
        self.assertEqual(list(self.run_config(raw).iter_events()), [])

    def test_point_windows_and_calculations(self):
        """变化事件交给既有窗口与片段均值。参数: 无。返回: None。异常: 断言失败。"""
        raw = delta_config()
        raw['windows'] = [dict(name='around', rule='change', anchor='point', pre='1ns', post='1ns')]
        raw['calculations'] = [dict(name='average', scope='segment:around', operation='time_weighted_mean', expr='voltage')]
        result = self.run_config(raw)
        self.assertEqual(len(list(result.iter_segments())), 2)
        calculations = list(result.iter_calculations())
        self.assertEqual(len(calculations), 2)
        self.assertEqual([row.value for row in calculations], [2.5, 2.5])

    def test_terminal_empty_and_short_observation(self):
        """真实末点能触发；空输入和短于完整窗口不能触发。参数: 无。返回: None。异常: 断言失败。"""
        for rows, expected in (([(0, 0), (14, 5)], [14]), ([], []), ([(12, 0), (14, 5)], [])):
            raw = delta_config()
            raw['sources'][0]['rows'] = [dict(time=f'{time}ns', values={'voltage': value}) for time, value in rows]
            self.assertEqual([row.confirmed_ns for row in self.run_config(raw).iter_events()], expected)

    def test_float_derived_and_mixed_rules(self):
        """派生数值与普通规则并存，来源只扫描一次。参数: 无。返回: None。异常: 断言失败。"""
        raw = delta_config()
        raw['signals'][0]['dtype'] = 'float64'
        raw['derived'] = dict(twice=dict(expr='voltage * 2', unit='V'))
        raw['rules'][0].update(signal='twice', threshold=10)
        raw['rules'].append(dict(name='ordinary', rule_type='rising_edge', condition='voltage > 0'))
        scans = []
        original = BudgetedMemorySourceAdapter.iter_batches
        def capture(owner, *args, **kwargs):
            """记录真实来源扫描。参数: 实际调用参数。返回: 原游标。异常: 原错误。"""
            scans.append(owner)
            return original(owner, *args, **kwargs)
        with patch.object(BudgetedMemorySourceAdapter, 'iter_batches', capture):
            rows = list(self.run_config(raw).iter_events())
        self.assertEqual(len(scans), 1)
        self.assertEqual([(row.rule_id, row.confirmed_ns) for row in rows],
                         [('change', 4), ('change', 12), ('ordinary', 4), ('ordinary', 12)])

    def test_output_roundtrip_and_publish(self):
        """事件沿用原编码和三表发布契约。参数: 无。返回: None。异常: 断言失败。"""
        for tables in ('csv', 'jsonl'):
            raw = delta_config()
            raw['outputs']['tables'] = tables
            result = self.run_config(raw)
            for row in result.iter_events():
                self.assertEqual(decode_row(encode_row(row, max_bytes=2**20), max_bytes=2**20), row)
            output = ROOT / 'work/m3-window-delta-home-20261022/published' / uuid4().hex
            manifest = result.write(output)
            self.assertTrue(Path(manifest.output_dir).is_dir())

    def test_buffer_budget_and_cancel_cleanup(self):
        """窗口申请/释放前后取消和预算失败都归还资源。参数: 无。返回: None。异常: 断言失败。"""
        original_init = ResourceBudget.__init__
        for operation, after, exception in (('reserve', False, BudgetExceededError),
                                             ('reserve', True, KeyboardInterrupt),
                                             ('release', False, KeyboardInterrupt),
                                             ('release', True, KeyboardInterrupt)):
            budgets, triggered = [], []
            def capture(owner, *args, **kwargs):
                """保存真实账本供核零。参数: 原构造参数。返回: None。异常: 原错误。"""
                original_init(owner, *args, **kwargs)
                budgets.append(owner)
            name = '_reserve_owned_ram' if operation == 'reserve' else '_release_owned_ram'
            original = getattr(delta_module, name)
            def inject(owner, amount, slot):
                """只在窗口缓冲费用模拟一次失败。参数: owner/字节/槽。返回: None。异常: 指定故障。"""
                if slot == '_span_cost' and amount and not triggered:
                    triggered.append(True)
                    if after:
                        original(owner, amount, slot)
                    raise exception('synthetic window fault')
                return original(owner, amount, slot)
            with self.subTest(operation=operation, after=after), patch.object(ResourceBudget, '__init__', capture), patch.object(delta_module, name, inject):
                with self.assertRaises(exception):
                    self.run_config(delta_config())
            self.assertTrue(triggered)
            self.assertTrue(budgets)
            self.assertTrue(all(budget.ram_bytes == 0 for budget in budgets))

    def test_rolling_storage_and_actual_budget_limit(self):
        """长输入只留4ns窗口；真实账本超限停止并清理。参数: 无。返回: None。异常: 断言失败。"""
        raw = delta_config()
        raw['dataset']['domain']['end'] = '100ns'
        raw['sources'][0]['rows'] = [dict(time=f'{time}ns', values={'voltage': time % 7}) for time in range(101)]
        lengths, owners = [], []
        original = RecordDeltaCondition.update
        def measure(owner, *args, **kwargs):
            """保存每次真实计算后的窗口长度。参数: owner。返回: 原事件。异常: 原错误。"""
            event = original(owner, *args, **kwargs)
            lengths.append(len(owner._spans))
            return event
        with patch.object(RecordDeltaCondition, 'update', measure):
            self.run_config(raw).close()
        self.assertLessEqual(max(lengths), 5)
        def limit(owner, *args, **kwargs):
            """缩小真实预算剩余额度来触发工作区申请拒绝。参数: owner。返回: 原结果。异常: BudgetExceededError。"""
            owners.append(owner)
            owner._budget.memory_budget_bytes = owner._budget.ram_bytes + 100
            return original(owner, *args, **kwargs)
        with patch.object(RecordDeltaCondition, 'update', limit):
            with self.assertRaises(BudgetExceededError):
                self.run_config(delta_config())
        self.assertTrue(owners[0]._closed)
        self.assertEqual(owners[0]._budget.ram_bytes, 0)

    def test_coexists_with_pairing_and_event_calculation(self):
        """普通配对与窗口变化共存，事件指标引用不误要求数值根为BOOL。参数: 无。返回: None。异常: 断言失败。"""
        raw = delta_config()
        raw['rules'].append(dict(name='ordinary', rule_type='rising_edge', condition='voltage > 0'))
        raw['sequences'] = [dict(name='same', start='ordinary', response='ordinary', min_delay='0ns', max_delay='0ns')]
        raw['calculations'] = [dict(name='at_event', scope='event:change', operation='sample_maximum', expr='voltage')]
        result = self.run_config(raw)
        self.assertEqual(len(list(result.iter_sequences())), 2)
        calculations = list(result.iter_calculations())
        # 点事件没有持续长度，沿既有契约返回空值；要统计其附近需显式窗口。
        self.assertEqual([row.value for row in calculations], [None, None])
        self.assertTrue(all(row.reason == 'zero_length_window' for row in calculations))
        events={row.event_id:row for row in result.iter_events()}
        self.assertTrue(all(events[row.parent_id].start_ns == events[row.parent_id].confirmed_ns and events[row.parent_id].end_ns is None for row in calculations))

    def test_csv_and_requested_start(self):
        """CSV沿同样窗口规则；请求10ns起最早14ns完整。参数: 无。返回: None。异常: 断言失败。"""
        raw = delta_config()
        path = ROOT / 'work/m3-window-delta-home-20261022/csv' / (uuid4().hex + '.csv')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('ns,voltage\n' + ''.join(row['time'][:-2] + ',' + str(row['values']['voltage']) + '\n'
                        for row in raw['sources'][0]['rows']), encoding='utf-8')
        raw['sources'][0].pop('rows')
        raw['sources'][0].update(source_type='signal_csv', path=str(path), time_column='ns')
        self.assertEqual([row.confirmed_ns for row in self.run_config(raw).iter_events()], [4, 12])
        raw['dataset']['domain']['start'] = '10ns'
        self.assertEqual([row.confirmed_ns for row in self.run_config(raw).iter_events()], [14])

    def test_short_source_and_independent_clock(self):
        """长来源不能延长短来源有效值，独立时钟的规则各用本组观测。参数: 无。返回: None。异常: 断言失败。"""
        for origin in ('clock', 'separate'):
            raw = delta_config()
            raw['sources'][0]['rows'] = raw['sources'][0]['rows'][:4]
            raw['sources'].append(dict(name='other', source_type='memory',
                time=dict(time_type='relative', unit='ns', origin=origin),
                rows=[dict(time='0ns', values={'clock_signal': 0}), dict(time='14ns', values={'clock_signal': 1})]))
            raw['signals'].append(dict(name='clock_signal', source='other', field='clock_signal',
                                      dtype='int64', unit='1', valid_for='20ns'))
            raw['rules'].append(dict(name='clock_rule', rule_type='window_delta', signal='clock_signal',
                window='4ns', direction='rise', threshold=1, emit_initial=True))
            rows = list(self.run_config(raw).iter_events())
            self.assertEqual([(row.rule_id, row.confirmed_ns) for row in rows],
                             [('change', 4), ('clock_rule', 14)])


if __name__ == '__main__':
    # 单文件入口与统一测试发现共享用例。
    unittest.main()
