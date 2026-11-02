"""[home] 全输入、独立批量模板和受限公共覆盖，均用实际小输入验证。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from chronaxis import AnalysisPlan, AnalysisRunner, load_analysis_plan, PlanValidationError
from chronaxis.batch.models import BatchPlan


class ConfigurationReuseTests(unittest.TestCase):
    """验证省略配置不会合并任务或推断不存在的数据。"""
    def setUp(self):
        """建立临时表；输入0/1/2秒功率3/1/3W，面积4J。"""
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.raw=dict(config_version=3,dataset=dict(name='test',domain=dict(start='0s',end='2s')),
            sources=[dict(source_type='signal_csv',path='input.csv',time_column='t',time=dict(unit='s'))],
            signals=[dict(name='p',field='p',dtype='float64',unit='W',valid_for='5s')],
            calculations=[dict(name='energy',operation='integral',expr='p')])
        self.write('input.csv','t,p\n0,3\n1,1\n2,3\n')

    def write(self,name,value):
        """写隔离的配置或表，返回路径；不改产品或历史资源。"""
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(value if type(value) is str else json.dumps(value),encoding='utf-8');return p

    def test_full_input_and_empty_observation(self):
        """无domain按实际观测结算，空表不制造0值。"""
        self.raw['dataset'].pop('domain')
        for backend in ('reference','numpy'):
            plan=AnalysisPlan.from_dict(self.raw,base_dir=self.root)
            with AnalysisRunner(backend).run(plan,work_dir=self.root/backend) as result:
                self.assertEqual(next(result.iter_calculations()).value,4.)
        self.write('input.csv','t,p\n')
        with AnalysisRunner().run(AnalysisPlan.from_dict(self.raw,base_dir=self.root),work_dir=self.root/'empty') as result:
            self.assertIsNone(next(result.iter_calculations()).value)

    def test_template_natural_order_independent_files(self):
        """目录中的file2先于file10；每文件独立编译、计算，不按连续时间合并。"""
        self.write('inputs/file10.csv','t,p\n0,9\n1,9\n')
        self.write('inputs/file2.csv','t,p\n0,3\n1,3\n')
        self.raw['dataset']['domain']['end']='1s'
        template=self.write('template.json',self.raw)
        plan=BatchPlan.from_dict(dict(batch_version=1,template=str(template),inputs='inputs'),base_dir=self.root)
        self.assertEqual([j.job_id for j in plan.jobs],['job_1','job_2'])
        values=[]
        for job in plan.jobs:
            with AnalysisRunner().run(job.plan,work_dir=self.root/job.job_id) as result:values.append(next(result.iter_calculations()).value)
        self.assertEqual(values,[3.,9.])
        from chronaxis.batch import BatchRunner
        report=BatchRunner(2).run(plan.jobs,self.root/'parallel',device_label='home')
        self.assertEqual(report.status,'completed')
        self.assertEqual(len({job.run_id for job in report.jobs}),2)
        explicit=BatchPlan.from_dict(dict(batch_version=1,jobs=[dict(plan='a.json'),dict(plan='b.json')]))
        self.assertEqual([j.job_id for j in explicit.jobs],['job_1','job_2'])

    def test_import_override_and_origin(self):
        """仅明确覆盖既有字段；缺目标、改名和自由metadata均拒绝。"""
        from chronaxis.configuration.origins import configuration_origins
        sources=self.raw.pop('sources');sources[0]['name']='input'
        signals=self.raw.pop('signals')
        self.write('shared.json',dict(sources=sources,signals=signals))
        self.raw.update(imports=['shared.json'],overrides=dict(signals=dict(p=dict(valid_for='3s'))))
        path=self.write('plan.json',self.raw)
        self.assertEqual(load_analysis_plan(path).signals[0].definition.valid_for_ns,3*10**9)
        report=configuration_origins(path,fields=True)
        self.assertTrue(any(x['declared_path']=='$.overrides.signals.p.valid_for' for x in report['items']))
        for changes in (dict(missing=dict(unit='V')),dict(p=dict(name='q')),dict(p=dict(metadata={'x':1}))):
            self.raw['overrides']['signals']=changes;self.write('plan.json',self.raw)
            with self.assertRaises(PlanValidationError):load_analysis_plan(path)

    def test_ini_infers_unique_aliases_and_sclicer_section_names(self):
        """同名原列唯一匹配时不重复写aliases，段名自动产生独立规则/窗口名。"""
        from test_legacy_import_sclicer import mapping_fixture,FIXTURES,ROOT
        from chronaxis.migration.api import import_legacy_ini
        mapping=mapping_fixture();mapping.pop('aliases');mapping.pop('sections')
        from chronaxis.planning.config_groups import public_configuration
        mapping['analysis']=public_configuration(mapping['analysis'])
        result=import_legacy_ini((FIXTURES/'single-soc.ini').read_bytes(),mapping,
            mode='sclicer_single',base_dir=ROOT/'work/m2-import-tests',device_label='home')
        self.assertIsNotNone(result.plan,result.report.to_dict())
        self.assertEqual(result.plan.rules[0].rule_id,'trigger_1')

    def test_grouped_ini_signal_defaults_and_ambiguous_alias(self):
        """INI映射复用DBC元数据，不重复要求信号类型/单位；重名原字段不自动挑选。"""
        from chronaxis.migration.api import _prepare_mapping
        dbc=Path(__file__).parents[2]/'src/chronaxis/configuration/templates/shared/sample.dbc'
        raw=dict(mapping_version=1,analysis=dict(config_version=3,dataset=dict(name='can',domain=dict(start='0s',end='1s')),
            sources=[dict(path='missing.asc',dbc_by_channel={'1':str(dbc)})],
            signals=[dict(frame_id=256,valid_for='1s',signals=[dict(name='voltage',signal='Voltage')])]))
        prepared,_=_prepare_mapping(raw,self.root)
        signal=prepared['analysis']['signals'][0]
        self.assertEqual((signal['unit'],signal['source'],signal['field']['channel']),('V','source_1',1))
        self.assertEqual(prepared['aliases'],{'Voltage':'voltage'})
        raw['analysis']['signals'][0]['signals'].append(dict(name='other',signal='Voltage'))
        prepared,_=_prepare_mapping(raw,self.root)
        self.assertNotIn('Voltage',prepared['aliases'])

    def test_override_paths_use_main_directory_and_remove_old_origins(self):
        """替换输入按主文件解释，替换time整对象后不输出已删除clock的来源。"""
        from chronaxis.configuration.origins import configuration_origins
        source=self.raw.pop('sources')[0]
        source.update(name='input',path='../input.csv',time=dict(unit='s',clock='old'))
        signals=self.raw.pop('signals')
        self.write('shared/defs.json',dict(sources=[source],signals=signals))
        self.write('replacement.csv','t,p\n0,3\n1,1\n2,3\n')
        self.raw.update(imports=['shared/defs.json'],overrides=dict(sources=dict(input=dict(path='replacement.csv',time=dict(unit='s')))))
        path=self.write('plan.json',self.raw)
        plan=load_analysis_plan(path)
        self.assertEqual(plan.raw_config['sources'][0]['path'],str(self.root/'replacement.csv'))
        rows=configuration_origins(path,fields=True)['items']
        self.assertFalse(any(item['effective_path']=='$.sources[0].time.clock' for item in rows))
        self.assertTrue(any(item['declared_path']=='$.overrides.sources.input.path' for item in rows))

    def test_template_requires_unambiguous_source_and_rejects_jobs_mixing(self):
        """多来源必须指定替换哪一路；模板与显式jobs不能混用。"""
        self.raw['sources'][0]['name']='one'
        self.raw['sources'].append(dict(self.raw['sources'][0],name='two'))
        template=self.write('template.json',self.raw)
        for raw in (dict(template=str(template),inputs='input.csv'),
                    dict(template=str(template),inputs='input.csv',jobs=[])):
            with self.assertRaises(PlanValidationError):BatchPlan.from_dict(dict(batch_version=1,**raw),base_dir=self.root)
        self.raw['sources']=['invalid']
        self.write('template.json',self.raw)
        with self.assertRaises(PlanValidationError):
            BatchPlan.from_dict(dict(batch_version=1,template=str(template),inputs='input.csv'),base_dir=self.root)
