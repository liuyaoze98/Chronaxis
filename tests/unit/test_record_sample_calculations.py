"""核新版样本统计复用旧数值核；条件/TTL/裁剪保持点不能多算样本。"""

from configuration_fixtures import current_fixture
from copy import deepcopy
from itertools import product
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisPlan,AnalysisRunner
import test_record_sources as sources
import test_record_scope_calculations as scopes


class RecordSampleCalculationTests(unittest.TestCase):
    """实际值在0/3/6秒更新，半开0—6只计4和8两条，均值6。"""
    setUp=sources.RecordSourcesTests.setUp

    def config(self,*,age='10s',scope='session'):
        """构造值与条件分开更新的数据。参数: 有效期/指标范围。返回: dict。异常: 无。"""
        raw=dict(config_version=3,
            dataset=dict(name='dataset',entity='device',session='session',domain=dict(start='0s',end='6s')),
            sources=[],signals=[],calculations=[],metadata=dict(device_label='home'))
        for name,unit,dtype,times,values in (('value','W','float64',(0,3,6),(4,8,10)),
                ('gate','1','bool',(0,1,2,6),(True,False,True,True))):
            raw['sources'].append(dict(name=name,source_type='memory',time=dict(time_type='relative',unit='ns',origin='same'),
                rows=[dict(time=str(t)+'s',values={'raw':v}) for t,v in zip(times,values)]))
            raw['signals'].append(dict(name=name,source=name,field='raw',dtype=dtype,unit=unit,valid_for=age if name=='value' else '10s'))
        for operation in ('sample_minimum','sample_maximum','sample_mean'):
            raw['calculations'].append(dict(name=operation,scope=scope,operation=operation,expr='value',condition='gate',unit='W'))
        if scope.startswith('event:'):
            raw['rules']=[dict(name='active',rule_type='condition_duration',condition='gate',minimum_duration='0s')]
        return raw

    def test_session_samples_ignore_condition_updates_and_default_period(self):
        """批次大小和任务默认周期不改变样本统计；与schema1现有接口同值同状态。"""
        for backend,size in product(('reference','numpy'),(1,2,16)):
            raw=self.config();raw['execution']={'batch_rows':size}
            raw['rules']=[dict(name='active',rule_type='condition_duration',condition='gate',minimum_duration='0s')]
            raw['intervals']={'default':{'mode':'fixed','value':'0.1s','driver':'gate'}}
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                rows={r.calculation_id:r for r in result.iter_calculations()}
                self.assertEqual({k:r.value for k,r in rows.items()},dict(sample_minimum=4.,sample_maximum=8.,sample_mean=6.))
                self.assertTrue(all(r.status=='complete' for r in rows.values()))
            actual=deepcopy(raw);actual.pop('intervals')
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(actual)),self.root/uuid4().hex) as result:
                self.assertEqual({row.calculation_id:row.value for row in result.iter_calculations()},
                                 dict(sample_minimum=4.,sample_maximum=8.,sample_mean=6.))

    def test_early_value_eof_matches_existing_sample_policy(self):
        """值源先到EOF而条件仍有数据，样本值和质量政策与旧入口一致。"""
        for backend in ('reference','numpy'):
            raw=self.config();raw['sources'][0]['rows'].pop()
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                current={row.calculation_id:row for row in result.iter_calculations()}
            # 值源最后记录在3秒，0—3秒半开范围仅有0秒的4，3秒端点不计入。
            self.assertEqual({key:row.value for key,row in current.items()},
                             dict(sample_minimum=4.,sample_maximum=4.,sample_mean=4.))
            self.assertTrue(all(row.status=='partial' for row in current.values()))

    def test_expiry_and_strict_policy(self):
        """中间过期不补样本；部分政策仍得6，严格政策返回未知，覆盖门槛单独报告。"""
        for backend,policy in product(('reference','numpy'),('report','strict')):
            raw=self.config(age='2s')
            for calculation in raw['calculations']:calculation.update(partial_policy=policy,minimum_coverage=.9)
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                rows={r.calculation_id:r for r in result.iter_calculations()}
                self.assertEqual(rows['sample_mean'].value,6. if policy=='report' else None)
                self.assertTrue(all(r.status==('partial' if policy=='report' else 'indeterminate') for r in rows.values()))
                self.assertTrue(all(r.coverage_status=='indeterminate' for r in rows.values()))

    def test_event_cut_does_not_count_held_value(self):
        """第二次活动从2秒开始，2秒的保持4不能计样本，只有3秒的8。"""
        for backend in ('reference','numpy'):
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(self.config(scope='event:active'))),self.root/uuid4().hex) as result:
                events={r.event_id:r for r in result.iter_events()}
                rows=tuple(result.iter_calculations());self.assertEqual(len(rows),6)
                for row in rows:self.assertEqual(row.value,4. if events[row.parent_id].start_ns==0 else 8.)

    def test_select_session_events_and_unknown(self):
        """选择只在0/3秒输出，条件未知单独保留；事件裁剪不新增2秒的保持值。"""
        for backend,scope,unknown in product(('reference','numpy'),('session','event:active'),(False,True)):
            if scope!='session' and unknown:continue
            raw=self.config(scope=scope)
            raw['calculations']=[dict(name='selected',scope=scope,operation='select',expr='value',condition='gate',unit='W')]
            raw['execution']={'batch_rows':1,'result_buffer_rows':1}
            if unknown:raw['sources'][1]['rows'][2]['values']['raw']=None
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                self.assertEqual(tuple(result.iter_calculations()),())
                rows=tuple(result.iter_selections())
                self.assertEqual(sorted((row.time_ns,row.value) for row in rows),[(0,4.),(3000000000,8.)])
                last=next(row for row in rows if row.time_ns==3000000000)
                self.assertEqual(last.selection,'unknown' if unknown else 'true')
                if unknown:self.assertNotEqual(last.quality,0)
                output=self.root/uuid4().hex;result.write(output)
                self.assertTrue((output/'选择结果.csv').exists())
            self.assertEqual(sorted((r.time_ns,r.value,r.selection) for r in rows),
                             [(0,4.,'true'),(3000000000,8.,'unknown' if unknown else 'true')])

    def test_select_enum_and_uint64_exact(self):
        """选择保枚举文字和uint64精度；事件必要历史不转成float。"""
        for backend,kind in product(('reference','numpy'),('enum','uint64')):
            raw=self.config(scope='event:active')
            signal=raw['signals'][0];signal.update(dtype=kind,unit='1')
            if kind=='enum':signal['choices']=[[0,'off'],[1,'scope']]
            for row,value in zip(raw['sources'][0]['rows'],(1,0,1) if kind=='enum' else (2**64-1,2**64-2,2**64-3)):
                row['values']['raw']=value
            raw['calculations']=[dict(name='selected',scope='event:active',operation='select',expr='value',condition='gate',unit='1')]
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                rows=sorted(result.iter_selections(),key=lambda r:r.time_ns)
                self.assertEqual([row.value for row in rows],['scope','off'] if kind=='enum' else [2**64-1,2**64-2])

    def test_selection_cancel_after_output_releases_resources(self):
        """实际选择行写入后取消，最终暂存与必要状态都释放，不能留下成功前缀。"""
        from chronaxis.execution.record_session_calculations import RecordSessionCalculations
        original=RecordSessionCalculations._emit_selection;budgets=[]
        def cancel(owner,*args):
            """真实追加后取消。参数: owner/行。返回: 不返回。异常: KeyboardInterrupt。"""
            original(owner,*args);budgets.append(owner._budget);raise KeyboardInterrupt('select cancel')
        raw=self.config();raw['calculations']=[dict(name='selected',scope='session',operation='select',expr='value',unit='W')]
        root=self.root/uuid4().hex
        with patch.object(RecordSessionCalculations,'_emit_selection',cancel):
            with self.assertRaises(KeyboardInterrupt):AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),root)
        self.assertEqual(budgets[0].ram_bytes,0);self.assertFalse(root.exists())


class RawSampleCalculationTests(unittest.TestCase):
    """三原始格式复用样本核与事件必要历史。"""
    setUp=scopes.RecordScopeCalculationTests.setUp
    asc=scopes.RecordScopeCalculationTests.asc
    csv=scopes.RecordScopeCalculationTests.csv
    blf=scopes.RecordScopeCalculationTests.blf
    fixtures=scopes.RecordScopeCalculationTests.fixtures
    plan=scopes.RecordScopeCalculationTests.plan

    def test_three_formats_sample_mean(self):
        """0与0.12秒各一个真实功率样本，均值4400W，不按时长加权。"""
        for (kind,path),backend in product(self.fixtures().items(),('reference','numpy')):
            def edit(raw):
                """替换为样本均值。参数: 配置。返回: None。异常: 无。"""
                raw['calculations']=[dict(name='mean',scope='session',operation='sample_mean',expr='power',unit='W')]
            with AnalysisRunner(backend).run(self.plan(kind,path,'actual',edit),self.root/uuid4().hex) as result:
                self.assertEqual(next(result.iter_calculations()).value,4400.)

    def test_window_samples_and_selection_use_actual_update_positions(self):
        """actual窗0.02—0.22只有一条，固定/DBC窗0—0.3有两条；不输出窗口起点保持值。"""
        for (kind,path),mode in product(self.fixtures().items(),('actual','fixed','dbc')):
            def edit(raw):
                """同一片段请求样本均值及选择行。参数: 配置。返回: None。异常: 无。"""
                raw['rules']=[dict(name='edge',rule_type='rising_edge',condition='current >= 12')]
                raw['windows']=[dict(name='around',rule='edge',anchor='point',pre='0.1s',post='0.1s')]
                raw['calculations']=[dict(name='mean',scope='segment:around',operation='sample_mean',expr='power',unit='W'),
                    dict(name='selected',scope='segment:around',operation='select',expr='power',unit='W')]
                raw['outputs']={'tables':'jsonl'}
            with AnalysisRunner().run(self.plan(kind,path,mode,edit),self.root/uuid4().hex) as result:
                self.assertEqual(next(result.iter_calculations()).value,4800. if mode=='actual' else 4400.)
                rows=tuple(result.iter_selections());self.assertEqual(len(rows),1 if mode=='actual' else 2)
                segment,=tuple(result.iter_segments());self.assertTrue(all(row.parent_id==segment.segment_id for row in rows))
                output=self.root/uuid4().hex;result.write(output)
                self.assertTrue((output/'selections.jsonl').exists())
