"""用公开配置、双后端和手算样本验证分位数的范围、真实更新及资源清理。

会话内四次真实观测为0、10、20、30V，活动只含第二和第三次，窗口前后各
扩展一秒又包含全部四次。测试同时覆盖q保留、空选择和低层的共享预算故障。
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.configuration.resolution import resolved_configuration
from chronaxis.core.quantiles import ExactQuantileBuffer
from chronaxis.results.errors import BudgetExceededError


def quantile_config(batch_rows=1):
    """构造覆盖四个观测的会话与一个2秒活动，末点99V不属于样本范围。

    参数: batch_rows为执行批次大小。返回: 完整v4配置。异常: 无。
    """
    return dict(config_version=4,dataset=dict(name='ranked',domain=dict(start='0s',end='4s')),
        sources=[dict(name='input',source_type='memory',rows=[
            dict(time=f'{i}s',values={'v':v}) for i,v in enumerate((0,10,20,30,99))])],
        signals=[dict(name='v',field='v',unit='V',dtype='int64',valid_for='3s')],
        rules=[dict(name='active',rule_type='condition_duration',condition='0 < v < 30',minimum_duration='0s')],
        windows=[dict(name='wide',rule='active',anchor='activity',pre='1s',post='1s')],
        calculations=[
            dict(name='p95',operation='sample_quantile',expr='v',q=.95),
            dict(name='median',operation='sample_median',expr='v',scope={'rule':'active'}),
            dict(name='window_p95',operation='sample_quantile',expr='v',q=.95,scope={'window':'wide'},unit='mV'),
            dict(name='largest',operation='sample_quantile',expr='v',q=1),
            dict(name='selected',operation='sample_median',expr='v',condition='v < 30'),
            dict(name='empty',operation='sample_median',expr='v',condition='v > 100')],
        execution=dict(batch_rows=batch_rows))


class SampleQuantileTests(unittest.TestCase):
    """验证窗口改变的是样本总体，输入时长和分批方式不改变样本权重。"""

    def test_public_scopes_and_units(self):
        """取四行会话P95=28.5V、活动P50=15V、扩展窗口P95=28500mV。

        参数: 无。返回: None。异常: 批次划分、取秩、单位或末端归属错误时失败。
        """
        for backend in ('reference','numpy'):
            for batch_rows in (1,17):
                with self.subTest(backend=backend,batch=batch_rows),TemporaryDirectory(dir='work') as folder:
                    plan = AnalysisPlan.from_dict(quantile_config(batch_rows))
                    with AnalysisRunner(backend).run(plan,Path(folder)/'run') as result:
                        rows = {row.calculation_id:row for row in result.iter_calculations()}
                        budget = result.spool.budget
                    self.assertEqual(budget.ram_bytes,0)
                    for name,value,unit in (('p95',28.5,'V'),('median',15.,'V'),
                                            ('window_p95',28500.,'mV'),('largest',30,'V'),
                                            ('selected',10,'V'),('empty',None,'V')):
                        self.assertEqual((rows[name].value,rows[name].unit,type(rows[name].value)),
                                         (value,unit,type(value)))

    def test_resolve_and_invalid_fields(self):
        """展开重载仅quantile有q；median和其他算子拒绝q及v3新操作。

        参数: 无。返回: None。异常: 错误接受参数或丢失q的实际计划值时失败。
        """
        with TemporaryDirectory(dir='work') as folder:
            path = Path(folder)/'rank.json'
            path.write_text(json.dumps(quantile_config()),encoding='utf-8')
            expanded = resolved_configuration(path,defaults=True)
            self.assertEqual(expanded['calculations'][0]['q'],.95)
            self.assertNotIn('q',expanded['calculations'][1])
            self.assertEqual(AnalysisPlan.from_dict(expanded).calculations[0].q,.95)
        for operation,options in (('sample_median',dict(q=.5)),('sample_quantile',{}),
                                  ('sample_quantile',dict(q=True)),('sample_quantile',dict(q=1.01)),
                                  ('sample_minimum',dict(q=0)),('time_quantile',dict(q=.5))):
            raw = quantile_config()
            raw['calculations'] = [dict(name='bad',expr='v',operation=operation,**options)]
            with self.subTest(operation=operation,options=options),self.assertRaises(ValueError):
                AnalysisPlan.from_dict(raw)
        old = quantile_config()
        old['config_version'] = 3
        with self.assertRaises(ValueError):
            AnalysisPlan.from_dict(old)

    def test_runner_sort_budget_failure_releases_owner(self):
        """在真实排序预约前耗尽剩余共享RAM，Runner清理后不能有样本收费遗留。

        参数: 无。返回: None。异常: 原预算超额未传播、出现近似结果或未释放费用时失败。
        """
        original = ExactQuantileBuffer._reserve
        for backend in ('reference','numpy'):
            budgets = []
            def reserve(owner, amount, slot):
                """测试注入只缩小排序当刻的剩余额度，使用真实账本拒绝超额申请。

                参数: owner为实际缓冲，amount/slot为真实预算请求。返回: None。
                异常: 保留原始BudgetExceededError，恢复预算上限供清理。
                """
                if slot != '_sort_cost':
                    return original(owner,amount,slot)
                budget = owner._budget
                budgets.append(budget)
                previous = budget.memory_budget_bytes
                budget.memory_budget_bytes = budget.ram_bytes + amount - 1
                try:
                    return original(owner,amount,slot)
                finally:
                    budget.memory_budget_bytes = previous
            with self.subTest(backend=backend),TemporaryDirectory(dir='work') as folder:
                raw = quantile_config()
                raw['calculations'] = raw['calculations'][:1]
                with patch.object(ExactQuantileBuffer,'_reserve',reserve), self.assertRaises(Exception) as raised:
                    AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),Path(folder)/'run')
                error = raised.exception
                while error is not None and not isinstance(error,BudgetExceededError):
                    error = error.__cause__
                self.assertIsInstance(error,BudgetExceededError)
                self.assertTrue(budgets)
                self.assertTrue(all(b.ram_bytes == 0 for b in budgets))

    def test_historical_joint_blocks_keep_q_on_values_only(self):
        """独立回读的BOOL块只负责选择，分位概率仅属于数值块的原请求。

        参数: 无。返回: None。异常: q泄漏到duration、跨块重复或外部借用账本被释放时失败。
        """
        from chronaxis.core import MemoryRow, SignalDefinition, SignalDType as D
        from chronaxis.core.calculations import CalculationDefinition
        from chronaxis.execution.historical_sample_calculation import HistoricalSampleCalculation
        from test_window_replay import WindowReplayTests
        for backend in ('reference','numpy'):
            factory = WindowReplayTests()
            self.addCleanup(lambda f=factory:self.assertTrue(f.doCleanups()))
            fixture = factory.fixture(domain=(0,4),backend=backend,
                definitions=(SignalDefinition('a','table','raw.a',D.INT64,'V',10,config_version=4),
                             SignalDefinition('gate','table','gate',D.BOOL,'1',10,config_version=4)),
                rows_by_source={'table':tuple(MemoryRow(i,{'raw.a':v,'gate':g},i) for i,(v,g)
                                             in enumerate(((0,False),(10,True),(20,True),(30,True),(99,True))))},
                texts=('a','gate'))
            base = fixture.history.budget.ram_bytes
            spec = CalculationDefinition('rank','sample_quantile',fixture.domain,config_version=4,q=.25)
            owner = HistoricalSampleCalculation(fixture.history,fixture.holds._context,fixture.lease.bindings,
                fixture.compiled[0],spec,fixture.compiled[1],backend=backend,batch_intervals=1)
            try:
                while owner.step():
                    pass
                self.assertEqual((owner.result.value,owner.result.valid_sample_count),(15.,3))
            finally:
                owner.close()
            self.assertEqual(fixture.history.budget.ram_bytes,base)

    def test_direct_series_precision_and_budget_cleanup(self):
        """直接内存指标也保留有效样本数，区分插值精度故障与空间不足。

        参数: 无。返回: None。异常: 失去整数低位、把失败归类为空集合或泄漏费用时失败。
        """
        from test_calculations import _series
        from chronaxis.core.calculations import CalculationDefinition
        from chronaxis.core.calculations_reference import compute_reference
        from chronaxis.core.calculations_numpy import compute_numpy
        from chronaxis.core.types import SignalDType as D, QualityFlag as Q
        from chronaxis.results.budget import ResourceBudget
        series = _series((2**63+1,2**63+3,0),times=(0,1,3),dtype=D.UINT64,unit='1')
        spec = CalculationDefinition('rank','sample_median',series.observation,config_version=4)
        for compute in (compute_reference,compute_numpy):
            budget = ResourceBudget()
            result = compute(series,spec,budget=budget)
            self.assertEqual((result.value,result.valid_sample_count,result.reason),(None,2,'calculation_failed'))
            self.assertTrue(result.quality & Q.PRECISION_LOSS)
            self.assertEqual(budget.ram_bytes,0)
            budget = ResourceBudget(600)
            with self.assertRaises(BudgetExceededError):
                compute(series,spec,budget=budget)
            self.assertEqual(budget.ram_bytes,0)
