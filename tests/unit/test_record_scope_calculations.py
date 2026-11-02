"""按事件范围回读只保存必要值；手算核三格式、周期比例、条件与TTL。"""
from itertools import product
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisRunner
import test_record_runner as raw_cases


class RecordScopeCalculationTests(unittest.TestCase):
    """事件指标共用一份计算值，默认会话统计不创建必要历史。"""
    setUp=raw_cases.RecordRunnerTests.setUp
    asc=raw_cases.RecordRunnerTests.asc
    csv=raw_cases.RecordRunnerTests.csv
    blf=raw_cases.RecordRunnerTests.blf
    fixtures=raw_cases.RecordRunnerTests.fixtures
    plan=raw_cases.RecordRunnerTests.plan

    @staticmethod
    def calculations(raw):
        """同一事件请求能量/均值/极值。参数: 配置。返回: None。异常: 无。"""
        raw['rules']=[dict(name='active',rule_type='condition_duration',condition='voltage > 350',minimum_duration='0.1s')]
        raw['calculations']=[dict(name='energy',scope='event:active',operation='integral',expr='power',unit='J'),
                        dict(name='mean',scope='event:active',operation='time_weighted_mean',expr='power',unit='W'),
                        dict(name='peak',scope='event:active',operation='max_time',expr='power',unit='W')]

    def test_three_formats_modes_backends_and_shared_history(self):
        """0—0.3秒：实际1344J/4480W，周期880J/4400W，峰值4800W。"""
        from chronaxis.execution.record_value_history import RecordValueHistory
        for (kind,path),mode,backend in product(self.fixtures().items(),('actual','fixed','dbc'),('reference','numpy')):
            with self.subTest(kind=kind,mode=mode,backend=backend),patch(
                    'chronaxis.execution.record_scope_calculations.RecordValueHistory',wraps=RecordValueHistory) as factory:
                result=AnalysisRunner(backend).run(self.plan(kind,path,mode,self.calculations),self.root/uuid4().hex)
                self.addCleanup(result.close)
                rows={r.calculation_id:r for r in result.iter_calculations()}
                event,=tuple(result.iter_events())
                self.assertEqual(factory.call_count,1)
                self.assertTrue(all(row.parent_id==event.event_id for row in rows.values()))
                self.assertAlmostEqual(rows['energy'].value,1344 if mode=='actual' else 880,places=3)
                self.assertAlmostEqual(rows['mean'].value,4480 if mode=='actual' else 4400,places=3)
                self.assertEqual(rows['peak'].value,4800.)
                budget=result.spool.budget
                result.close()
                self.assertEqual(budget.ram_bytes,0)

    def test_partial_pair_and_value_expiry(self):
        """请求起点截一半原对，且电流0.12更新后0.27过期；不改分母或补零。"""
        path=self.fixtures()['can_asc']
        for backend,mode in product(('reference','numpy'),('actual','fixed')):
            def edit(raw):
                """报警依赖电压，统计电流另行过期。参数: 配置。返回: None。异常: 无。"""
                self.calculations(raw)
                raw['dataset']['domain']['start']='0.06s'
                raw['signals'][1]['valid_for']='0.15s'
                raw['calculations'][0]['minimum_coverage']=.95
            with AnalysisRunner(backend).run(self.plan('can_asc',path,mode,edit),self.root/uuid4().hex) as result:
                rows={r.calculation_id:r for r in result.iter_calculations()}
                self.assertAlmostEqual(rows['energy'].value,960 if mode=='actual' else 600,places=10)
                self.assertEqual(rows['energy'].status,'partial')
                self.assertEqual(rows['energy'].coverage_status,'indeterminate')

    def test_condition_and_explicit_event_end(self):
        """0—0.12结束的活动只取第一对；TRUE/FALSE选择独立于事件条件。"""
        path=self.fixtures()['can_asc']
        for backend,mode in product(('reference','numpy'),('actual','fixed')):
            def edit(raw):
                """事件跨批结束，条件只统计正电流。参数: 配置。返回: None。异常: 无。"""
                self.calculations(raw)
                raw['rules']=[dict(name='active',rule_type='start_end',start_condition='current < 12',
                    end_condition='current >= 12',timeout='1s')]
                for calculation in raw['calculations']:
                    calculation['condition']='current > 0'
            with AnalysisRunner(backend).run(self.plan('can_asc',path,mode,edit),self.root/uuid4().hex) as result:
                rows={r.calculation_id:r for r in result.iter_calculations()}
                self.assertAlmostEqual(rows['energy'].value,480 if mode=='actual' else 400)
                self.assertEqual(rows['mean'].value,4000.)

    def test_query_cancel_releases_history_and_result(self):
        """真实事件回读后发布时取消，必要文件及所有预算释放。"""
        from chronaxis.execution.record_scope_calculations import RecordScopeCalculations
        original=RecordScopeCalculations._calculate
        budgets=[]
        def cancel(owner,*args):
            """查询已完成后中断。参数: owner/原参数。返回: 无。异常: KeyboardInterrupt。"""
            original(owner,*args)
            budgets.append(owner._budget)
            raise KeyboardInterrupt('scope query cancellation')
        path=self.fixtures()['can_asc']
        root=self.root/uuid4().hex
        with patch.object(RecordScopeCalculations,'_calculate',cancel),self.assertRaises(KeyboardInterrupt):
            AnalysisRunner().run(self.plan('can_asc',path,'fixed',self.calculations),root)
        self.assertTrue(budgets)
        self.assertEqual(budgets[0].ram_bytes,0)
        self.assertFalse(root.exists())

    def test_short_read_fails_without_prefix(self):
        """必要值文件真实短缺时必须失败，不能把缺记录当空值成功。"""
        from chronaxis.execution.record_scope_calculations import RecordScopeCalculations
        from chronaxis.results import AnalysisError
        original=RecordScopeCalculations._calculate
        budgets=[]
        def truncate(owner,*args):
            """在回读前损坏测试临时文件。参数: owner/参数。返回: 原调用。异常: 应拒绝短读。"""
            budgets.append(owner._budget)
            for stream in owner._streams.values():
                if stream[2]._file is not None:
                    stream[2]._file.truncate(0)
            return original(owner,*args)
        path=self.fixtures()['can_asc']
        root=self.root/uuid4().hex
        with patch.object(RecordScopeCalculations,'_calculate',truncate),self.assertRaises(AnalysisError):
            AnalysisRunner().run(self.plan('can_asc',path,'fixed',self.calculations),root)
        self.assertTrue(budgets)
        self.assertEqual(budgets[0].ram_bytes,0)
        self.assertFalse(root.exists())

    def test_shared_read_and_budget_fallback_keep_order_and_values(self):
        """三个指标预算充足共读一次；余量小按单项回读，发布顺序和数值相同。"""
        from chronaxis.execution.record_value_history import RecordValueHistory
        original=RecordValueHistory.rows
        path=self.fixtures()['can_asc']
        baseline=None
        for capacity,expected_reads in ((268435456,1),(67108864,3)):
            calls=[]
            def rows(owner,*args):
                calls.append(args);return original(owner,*args)
            def edit(raw):
                self.calculations(raw);raw.setdefault('execution',{}).update(memory_budget_bytes=capacity,batch_rows=64)
            with patch.object(RecordValueHistory,'rows',rows):
                with AnalysisRunner().run(self.plan('can_asc',path,'fixed',edit),self.root/uuid4().hex) as result:
                    actual=[(r.calculation_id,r.value,r.status) for r in result.iter_calculations()]
                    self.assertEqual([r[0] for r in actual],['energy','mean','peak'])
            self.assertEqual(len(calls),expected_reads)
            if baseline is None:baseline=actual
            else:self.assertEqual(actual,baseline)
