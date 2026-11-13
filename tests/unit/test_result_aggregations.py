"""从已观测的活动及请求配对核验总体分类、严格政策、资源清理和实际结果发布。"""

from pathlib import Path
from workspace_fixtures import TemporaryDirectory
from contextlib import closing
from unittest.mock import patch
import unittest
from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError
from chronaxis.results import ResourceBudget, BudgetExceededError
from chronaxis.results.aggregation_row import SummaryAggregationRow
from chronaxis.results.codec import encode_row, decode_row
from chronaxis.results.summary import SummaryCalculationRow, SummarySequenceRow
from chronaxis.core.types import QualityFlag as Q
from chronaxis.execution.result_aggregations import ResultAggregations


class AggregationTests(unittest.TestCase):
    """使用独立手算期望，分别覆盖两个后端及报告、严格和空总体。"""

    def sequence_config(self):
        """创建五个请求，延迟为 100、200、300、400ms 和一次已确认超时。

        参数: 无。返回: v4 原生配置。异常: 无。
        """
        rows=[(0,False,False)]
        for i in range(1,6):
            rows.extend([(1000*i,True,False),(1000*i+1,False,False)])
            if i<5:
                rows.extend([(1000*i+i*100,False,True),(1000*i+i*100+1,False,False)])
        rows.append((6000,False,False))
        return dict(config_version=4,dataset=dict(name='response',domain=dict(start='0s',end='6s')),outputs=dict(tables='jsonl'),
            sources=[dict(name='table',source_type='memory',rows=[
                dict(time=f'{t}ms',values=dict(req=q,answer=a)) for t,q,a in rows])],
            signals=[dict(name=name,field=name,dtype='bool',unit='1',valid_for='9s') for name in ('req','answer')],
            rules=[dict(name=name+'_edge',rule_type='rising_edge',condition=name) for name in ('req','answer')],
            sequences=[dict(name='reply',start='req_edge',response='answer_edge',min_delay='0s',max_delay='500ms')],
            aggregations=[dict(name='p95',source={'sequence':'reply'},operation='quantile',q=.95,unit='ms',group_by=['entity_id']),
                          dict(name='delays_var',source={'sequence':'reply'},operation='variance',unit='ms^2'),
                          dict(name='requests',source={'rule':'req_edge'},operation='count')])

    def test_success_subset_timeout_units_and_machine_readable_output(self):
        """超时定义内排除而独立保留总体计数，P95 385ms 且方差12500ms²。

        参数: 无。返回: None。异常: 任一后端、结果表版本或机器读写不符。
        """
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend),TemporaryDirectory(dir='work',prefix='aggregate-pair-') as folder:
                plan=AnalysisPlan.from_dict(self.sequence_config())
                with AnalysisRunner(backend).run(plan,work_dir=Path(folder)/'run') as result:
                    table={r.aggregation_id:r for r in result.iter_aggregations()}
                    p=table['p95']
                    self.assertEqual((p.value,p.unit,p.status),(385.,'ms','complete'))
                    self.assertEqual((p.candidate_count,p.included_count,p.definition_excluded_count,p.quality_excluded_count),(5,4,1,0))
                    self.assertEqual((p.matched_count,p.timeout_count,p.insufficient_observation_count,p.pending_count),(4,1,0,0))
                    self.assertEqual(table['delays_var'].value,12500.)
                    self.assertEqual(table['requests'].value,5)
                    self.assertEqual(result.run_manifest['row_schema_versions']['aggregations'],15)
                    self.assertEqual(result.run_manifest['run']['aggregation_definitions'][0]['q'],.95)
                    self.assertEqual(decode_row(encode_row(p,65536),65536),p)
                    result.write(Path(folder)/'out')

    def test_early_end_rejected_as_timeout_and_readable_files(self):
        """日志只覆盖第五次请求后的1ms，不能确认500ms超时；已匹配部分单独统计。

        参数: 无。返回: None。异常: 错误填充延迟、伪造超时或可读结果丢失。
        """
        for backend in ('reference','numpy'):
            with TemporaryDirectory(dir='work',prefix='aggregate-eof-') as folder:
                raw=self.sequence_config()
                raw['sources'][0]['rows'].pop()
                raw['outputs']={'tables':'readable_csv'}
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),work_dir=Path(folder)/'run') as result:
                    p=next(row for row in result.iter_aggregations() if row.aggregation_id=='p95')
                    self.assertEqual((p.value,p.status,p.timeout_count,p.insufficient_observation_count),(385.,'partial',0,1))
                    self.assertEqual((p.definition_excluded_count,p.quality_excluded_count),(0,1))
                    output=result.write(Path(folder)/'out')
                    files=[p for p in output.output_files if p.is_file() and p.suffix=='.csv']
                    self.assertTrue(any('参与数' in p.read_text('utf-8-sig').splitlines()[0] for p in files))

    def simple_plan(self):
        """创建有限标量指标和四种不同参与政策。参数: 无。返回: 真实计划。异常: 配置错误。"""
        raw=self.sequence_config()
        raw['rules']=[];raw['sequences']=[]
        raw['calculations']=[dict(name='energy',operation='integral',expr='quantity(1,"W")',unit='J')]
        raw['aggregations']=[dict(name=n,source={'calculation':'energy'},operation='sum',**opts) for n,opts in (
            ('known',{}),('strict',{'partial_policy':'strict'}),('include',{'include_partial':True}),
            ('in_wh',{'include_partial':True,'unit':'Wh'}))]
        return AnalysisPlan.from_dict(raw)

    def test_partial_population_and_no_average_coverage(self):
        """100候选内80个完整、1个部分、19个未知；检查每个数值和独立分类。

        参数: 无。返回: None。异常: 候选守恒、严格政策、单位或资源余额错误。
        """
        plan=self.simple_plan();budget=ResourceBudget()
        with closing(ResultAggregations(plan,budget)) as owner:
            for i in range(100):
                status='complete' if i<80 else 'partial' if i==80 else 'indeterminate'
                owner.accept(SummaryCalculationRow(i,'response','entity','session','energy','integral','session',None,
                    5. if i<81 else None,'J',status,'ok' if i<80 else 'partial_input',Q.NONE if i<80 else Q.MISSING))
            table={r.aggregation_id:r for r in owner.rows((),100)}
            self.assertEqual((table['known'].value,table['known'].status,table['known'].quality_excluded_count),(400.,'partial',20))
            self.assertIsNone(table['strict'].value)
            self.assertEqual((table['include'].value,table['include'].included_partial_count,table['include'].included_count),(405.,1,81))
            self.assertAlmostEqual(table['in_wh'].value,405./3600.)
        self.assertEqual(budget.ram_bytes,0)

    def test_budget_failure_and_schema_reject_invalid_sources(self):
        """分组内存不足时构造归还全部费用，非法来源及字段编译失败。

        参数: 无。返回: None。异常: 预算泄漏或规则标量误用。
        """
        budget=ResourceBudget(memory_budget_bytes=32768)
        with self.assertRaises(BudgetExceededError):
            ResultAggregations(self.simple_plan(),budget)
        self.assertEqual(budget.ram_bytes,0)
        for source,op,extra in (({'rule':'req_edge'},'mean',{}),
                ({'sequence':'reply'},'sum',{'field':'decided_ns'}),({'window':'absent'},'count',{}),
                ({'sequence':'reply'},'median',{'q':.5})):
            raw=self.sequence_config()
            raw['aggregations']=[dict(name='bad',source=source,operation=op,**extra)]
            with self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(raw)

    def test_known_empty_count_and_unknown_observation(self):
        """充分观测全假返回0，整源空不能写成确定0。

        参数: 无。返回: None。异常: 未区分空组与无观测或分位数伪造值。
        """
        for has_data in (False,True):
            raw=self.sequence_config()
            rows=raw['sources'][0]['rows']
            raw['sources'][0]['rows']=[rows[0],rows[-1]] if has_data else []
            with TemporaryDirectory(dir='work',prefix='aggregate-empty-') as folder:
                with AnalysisRunner().run(AnalysisPlan.from_dict(raw),work_dir=Path(folder)/'run') as result:
                    table={r.aggregation_id:r for r in result.iter_aggregations()}
                    self.assertEqual(table['requests'].value,0 if has_data else None)
                    self.assertEqual(table['requests'].status,'complete' if has_data else 'indeterminate')
                    self.assertIsNone(table['p95'].value)
                    self.assertEqual(table['p95'].status,'empty' if has_data else 'indeterminate')

    def test_grouped_activity_energies_and_independent_window_count(self):
        """两个活动能量为4J/8J，按对象归约或按父事件分开，窗口对象独立计数。

        参数: 无。返回: None。异常: 父关系、输入复用、组结果或单位错误。
        """
        raw=dict(config_version=4,dataset=dict(name='activities',domain=dict(start='0s',end='7s')),
            sources=[dict(name='table',source_type='memory',rows=[
                dict(time=f'{t}s',values={'p':v}) for t,v in ((0,0.),(1,2.),(3,0.),(4,4.),(6,0.),(7,0.))])],
            signals=[dict(name='power',field='p',dtype='float64',unit='W',valid_for='10s')],
            rules=[dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='power > 0',minimum_duration='0.1s')],
            windows=[dict(name='window',rule='active',pre='1s',post='1s')],
            calculations=[dict(name='energy',operation='integral',expr='power',scope=dict(rule='active'),unit='J')],
            aggregations=[dict(name=op,source=dict(calculation='energy'),operation=op,group_by=['entity_id'])
                          for op in ('sum','mean','variance')]+[
                              dict(name='each',source=dict(calculation='energy'),operation='sum',group_by=['parent_id']),
                              dict(name='segments',source=dict(window='window'),operation='count')])
        for backend in ('reference','numpy'):
            with TemporaryDirectory(dir='work',prefix='aggregate-activities-') as folder:
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),work_dir=Path(folder)/'run') as result:
                    rows=list(result.iter_aggregations())
                    self.assertEqual({r.aggregation_id:r.value for r in rows if r.aggregation_id in ('sum','mean','variance')},
                                     dict(sum=12.,mean=6.,variance=4.))
                    values={r.group_values[0]:r.value for r in rows if r.aggregation_id=='each'}
                    self.assertEqual(values,{r.parent_id:r.value for r in result.iter_calculations()})
                    self.assertEqual(next(r.value for r in rows if r.aggregation_id=='segments'),len(list(result.iter_segments())))

    def test_cancel_during_quantile_allocation_releases_accumulated_groups(self):
        """已收集若干延迟后在全局排序预约处取消，调用方可关闭并归还全部自有额度。

        参数: 无。返回: None。异常: 吞取消、部分发布或资源泄漏。
        """
        raw=self.sequence_config(); raw['aggregations']=raw['aggregations'][:1]
        # 内部聚合器由Runner接收已选后端的计划；auto先经过相同的静态步骤。
        from chronaxis.planning.backend_selection import execution_plan
        plan=execution_plan(AnalysisPlan.from_dict(raw));budget=ResourceBudget()
        owner=ResultAggregations(plan,budget)
        try:
            for i in range(4):
                owner.accept(SummarySequenceRow(i,'response','entity','session','reply',f'r{i}',f'req{i}',
                            f'ans{i}',4+i,1+i,'matched',Q.NONE))
            with patch.object(budget,'reserve_ram',side_effect=KeyboardInterrupt('aggregation-sort')):
                with self.assertRaises(KeyboardInterrupt):
                    next(iter(owner._groups.values())).value(plan.aggregations[0],1,0)
        finally:
            owner.close()
        self.assertEqual(budget.ram_bytes,0)
