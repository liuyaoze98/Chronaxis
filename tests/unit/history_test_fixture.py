"""独立历史数学测试的真实来源/历史/绑定夹具；不构造已删除的旧阶段编排器。

保留原测试工厂的真实读取、封口和预算清理。活动父由调用测试明确提供，
公共记录流如何生成活动另由record_rule_runner与record_scope_calculations验证。
"""

from configuration_fixtures import current_fixture
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import unittest
from chronaxis import load_analysis_plan
from chronaxis.execution.bindings import bind_decoded_history
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.hold import HoldContext
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.results import RunMetadata
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest


class HistoricalMathFixture(unittest.TestCase):
    """只提供fixture与清理方法，不注册额外测试或拥有事件输出阶段。"""

    def fixture(self, *, kind='memory', backend='numpy', size=2, buffer=2,
                rows=((0, 1), (3, 0), (5, 1), (8, 0)), domain=(0, 8), valid_for=20,
                rules=None, derived=None, other_rows=None):
        """从实际计划建立真实来源、封存历史和运行绑定，不复用旧夹具时钟。

        参数: kind为memory/CSV；backend为reference/NumPy；size和buffer为实际切批/结果缓冲；
            rows为有限(time_ns, raw.a)tuple，None保留无效；domain为整数ns半开域；
            valid_for为有效期ns；rules/derived为独立配置，可用空rules测试空阶段；
            other_rows非None时声明同计划第二来源other及别名b，验证联合条件。
        返回: SimpleNamespace含plan/history/context/lease/budget/metadata/work/baseline/adapters。
        异常: 文件、计划、读取和绑定原错误直接失败；cleanup核对调用方最终RAM为0。
        """
        # 每例目录唯一且只属于新项目；配置中的原来源定位不随owner回读改变。
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/historical-events' / uuid4().hex
        work.mkdir(parents=True)
        source = {'name': 'table', 'source_type': kind if kind == 'memory' else 'signal_csv',
                  'time': {'time_type': 'relative', 'unit': 'ns', 'origin': 'home_event_plan_clock'}}
        if kind == 'memory':
            source['rows'] = [{'time': str(time) + 'ns', 'values': {'raw.a': value}} for time, value in rows]
        else:
            # CSV的空单元格表达缺失，真实最后行提供EOF端点；不补周期或假终点。
            path = work / 'source.csv'
            path.write_text('ns,raw.a\n' + ''.join(str(time) + ',' + ('' if value is None else str(value)) + '\n'
                                                  for time, value in rows), encoding='utf-8', newline='')
            source.update(path='source.csv', time_column='ns')
        config = {'config_version': 4,
                  'dataset': {'name': 'event_dataset', 'entity': 'event_device', 'session': 'event_session',
                              'domain': {'start': str(domain[0]) + 'ns', 'end': str(domain[1]) + 'ns'}},
                  'sources': [source], 'signals': [{'name': 'a', 'source': 'table', 'field': 'raw.a',
                      'dtype': 'float64', 'unit': '1', 'valid_for': str(valid_for) + 'ns'}],
                  'rules': [{'name': 'active', 'rule_type': 'condition_duration', 'duration_comparison': '>=', 'condition': 'a > 0', 'minimum_duration': '2ns'}]
                           if rules is None else rules,
                  'derived': {} if derived is None else derived,
                  'execution': {'backend': backend, 'batch_rows': size, 'result_buffer_rows': buffer,
                                'memory_budget_bytes': 64 * 1024 ** 2},
                  'metadata': {'device_label': 'home', 'data_kind': 'synthetic'}}
        if other_rows is not None:
            # 两源仍独立读取和封存，但共用同一已声明origin；不借另一个fixture的运行绑定。
            second = {'name': 'other', 'source_type': source['source_type'], 'time': dict(source['time'])}
            if kind == 'memory':
                second['rows'] = [{'time': str(time) + 'ns', 'values': {'raw.b': value}}
                                  for time, value in other_rows]
            else:
                (work / 'other.csv').write_text('ns,raw.b\n' + ''.join(str(time) + ',' +
                    ('' if value is None else str(value)) + '\n' for time, value in other_rows),
                    encoding='utf-8', newline='')
                second.update(path='other.csv', time_column='ns')
            config['sources'].append(second)
            config['signals'].append({'name': 'b', 'source': 'other', 'field': 'raw.b',
                                       'dtype': 'float64', 'unit': '1', 'valid_for': str(valid_for) + 'ns'})
        config_path = work / 'plan.json'
        config_path.write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        plan = load_analysis_plan(config_path)
        budget = ResourceBudget(plan.execution.memory_budget_bytes, plan.execution.spool_quota_bytes)
        # 此cleanup最先登记、最后执行；适配器、lease和历史都已归还后必须确实为0。
        self.addCleanup(self.cleanup_zero, budget)
        adapters, requests = [], {}
        for declaration in plan.sources:
            # 实际adapter直接消费typed计划；时基、字段、session和投影都来自同一个load_analysis_plan结果。
            definitions = tuple(item.definition for item in plan.signals if item.definition.source == declaration.name)
            adapter_type = BudgetedMemorySourceAdapter if declaration.source_type == 'memory' else BudgetedSignalCSVSourceAdapter
            adapter = adapter_type(budget, declaration.config, plan.dataset.session_id, definitions, backend=backend)
            self.addCleanup(adapter.close)
            adapters.append(adapter)
            requests[declaration.name] = ReadRequest(plan.dataset.session_id, tuple(item.name for item in definitions),
                plan.dataset.domain.start_ns, plan.dataset.domain.end_ns, plan.execution.batch_rows)
            self.assertEqual(declaration.config.timebase, plan.dataset.timebase)
        descriptions = tuple(adapter.describe() for adapter in adapters)
        history = DecodedHistoryStore(budget, work / 'history', descriptions, requests)
        self.addCleanup(history.close)
        for declaration, adapter in zip(plan.sources, adapters):
            for batch in adapter.iter_batches(requests[declaration.name]):
                history.append(batch)
            adapter.close()
        history.seal()
        lease = bind_decoded_history(plan.bindings, history)
        self.addCleanup(lease.close)
        context = HoldContext(plan.dataset.session_id, plan.dataset.domain, descriptions,
                              tuple(history.source_completions.values()))
        metadata = RunMetadata('event_run', lease.bindings.identity, plan.identity, backend, plan.config_version,
            'relative integer nanoseconds; origin=home_event_plan_clock',
            ((plan.dataset.session_id, domain[0], domain[1]),),
            datetime.now(timezone(timedelta(hours=8))).isoformat(),
            limitations=('synthetic data; actual logs unverified',),
            device_label='home')
        # 明确调用方标记防止自有账本失误抵销借用层；本节点不修bootstrap工厂。
        budget.reserve_ram(8192)
        baseline = budget.ram_bytes
        self.addCleanup(self.cleanup_marker, budget, baseline)
        return SimpleNamespace(plan=plan, history=history, context=context, lease=lease, budget=budget,
                               metadata=metadata, work=work, baseline=baseline, adapters=tuple(adapters))

    def cleanup_zero(self, budget):
        """调用方全部层关闭后核对最终零余额，不手工修正任何生产费用。

        参数: 实际共享budget。返回: None。异常: 留存费用或借用抵销断言失败。
        """
        self.assertEqual(budget.ram_bytes, 0)

    def cleanup_marker(self, budget, baseline):
        """仅归还调用方明确8192标记，泄漏或多扣借用层直接失败。

        参数: 共享budget及建owner前baseline。返回: None。异常: 账本断言或原budget错误。
        """
        self.assertEqual(budget.ram_bytes, baseline)
        budget.release_ram(8192)
