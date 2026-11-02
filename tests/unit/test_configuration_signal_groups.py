"""[home] 报文集中声明和单位省略须与完整配置产生相同计算结果。"""
from copy import deepcopy
import json
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError, load_analysis_plan
import test_configuration_dbc_defaults as dbc_tests
import test_configuration_schema as schema_tests


class ConfigurationSignalGroupsTests(unittest.TestCase):
    """使用合成ASC和DBC实读，另核对导入、展开、错误和跨信号单位关系。"""
    setUp = dbc_tests.ConfigurationDBCDefaultsTests.setUp
    write_dbc = dbc_tests.ConfigurationDBCDefaultsTests.write_dbc

    def group(self):
        """仅改变配置形式，两个原信号和报文数据保持不变。"""
        raw=deepcopy(self.raw)
        raw['signals']=[dict(frame_id='0x100',valid_for='3s',signals=[
            dict(name='voltage',signal='Voltage'),dict(name='state',signal='State')])]
        return raw

    def validate_schema(self,raw):
        """独立JSON Schema与产品解析使用同一份输入。"""
        schema_tests.ConfigurationSchemaTests.setUpClass()
        schema_tests.ConfigurationSchemaTests.validators['analysis.schema.json'].validate(raw)

    def test_group_matches_flat_and_child_override(self):
        """同一报文集中绑定不改变3Vs面积、1秒上升沿或逐信号有效期。"""
        raw=self.group();before=deepcopy(raw)
        self.validate_schema(raw)
        flat=AnalysisPlan.from_dict(self.raw);group=AnalysisPlan.from_dict(raw)
        self.assertEqual(group.signals,flat.signals)
        self.assertEqual(raw,before)
        for backend in ('reference','numpy'):
            with AnalysisRunner(backend).run(group,work_dir=self.root/('group-'+backend)) as result:
                self.assertEqual(next(result.iter_calculations()).value,3.)
                self.assertEqual([row.start_ns for row in result.iter_events()],[10**9])
        raw['signals'][0]['signals'][1]['valid_for']='4s'
        self.assertEqual([s.definition.valid_for_ns for s in AnalysisPlan.from_dict(raw).signals],[3*10**9,4*10**9])

    def test_group_period_and_invalid_fields(self):
        """共用周期仍按三倍确定默认有效期；禁止覆盖报文定位或空组。"""
        raw=self.group();group=raw['signals'][0];group.pop('valid_for');group['period']='1s'
        self.assertEqual(AnalysisPlan.from_dict(raw).signals[0].definition.valid_for_ns,3*10**9)
        for key,value in (('source','other'),('field',{}),('frame_id',257),('channel',2)):
            wrong=deepcopy(raw);wrong['signals'][0]['signals'][0][key]=value
            with self.subTest(key=key),self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(wrong)
        wrong=deepcopy(raw);wrong['signals'][0]['signals']=[]
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(wrong)
        wrong=deepcopy(raw);wrong['signals'][0]['signals'][1]['name']='voltage'
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(wrong)
        wrong=deepcopy(raw);wrong['signals'][0]['valid_for']='0s'
        for child in wrong['signals'][0]['signals']:child['valid_for']='3s'
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(wrong)
        raw['signals'][0]['same_time_policy']='last_by_sequence'
        self.assertEqual(AnalysisPlan.from_dict(raw).signals[0].definition.same_time_policy,'last_by_sequence')

    def test_resolve_preserves_group_and_materializes_defaults(self):
        """两种resolve都能重载，defaults不会把每组与单个信号错误对齐。"""
        from chronaxis.configuration.resolution import resolved_configuration
        raw=self.group();raw['derived']={'doubled':dict(expr='voltage * 2')}
        raw['signals'][0]['signals'][1]['sample_policy']='backward_hold'
        path=self.root/'plan.json';path.write_text(json.dumps(raw),encoding='utf-8')
        for defaults in (False,True):
            output=resolved_configuration(path,defaults=defaults)
            self.validate_schema(output)
            plan=AnalysisPlan.from_dict(output,base_dir=self.root)
            self.assertEqual(plan.derived_expressions[0].root.unit,'V')
            children=output['signals'][0]['signals']
            self.assertEqual('dtype' in children[0],defaults)
            if defaults:
                self.assertEqual([x['dtype'] for x in children],['float64','int64'])
                self.assertEqual(output['derived']['doubled']['unit'],'V')
        from chronaxis import explain_analysis_plan
        from chronaxis.configuration.explanation import explanation_text
        plan=AnalysisPlan.from_dict(raw)
        text=explanation_text(plan,explain_analysis_plan(plan))
        self.assertIn('doubled = voltage * 2；单位 V',text)
        state_line=next(line for line in text.splitlines() if 'state ←' in line)
        self.assertIn('（配置指定）',state_line)

    def test_import_group_origins_and_duplicate_location(self):
        """导入组保持子信号的真实文件位置；重复名称在原声明处报错。"""
        from chronaxis.configuration.origins import configuration_origins
        raw=self.group();raw['sources'][0]['name']='input'
        shared=self.root/'shared.json'
        shared.write_text(json.dumps(dict(sources=raw.pop('sources'),signals=raw.pop('signals'))),encoding='utf-8')
        raw['imports']=['shared.json']
        path=self.root/'plan.json';path.write_text(json.dumps(raw),encoding='utf-8')
        self.assertEqual(len(load_analysis_plan(path).signals),2)
        report=configuration_origins(path)
        signal=next(x for x in report['items'] if x['name']=='state')
        self.assertEqual(signal['file'],str(shared))
        self.assertIn('signals[0].signals[1]',signal['declared_path'])
        raw['signals']=[dict(name='state',source='input',field=dict(frame_id=256,signal='State'))]
        path.write_text(json.dumps(raw),encoding='utf-8')
        with self.assertRaises(PlanValidationError) as error:load_analysis_plan(path)
        self.assertEqual(error.exception.code,'duplicate_definition')
        self.assertEqual(error.exception.source,str(path))

    def test_derived_inference_chains_and_explicit_errors(self):
        """V乘A得到W再积分为J；省略单位仍检查错误、循环和未知单位组合。"""
        raw=deepcopy(self.raw)
        raw['signals'][1].update(dtype='float64',unit='A')
        raw['derived']={'power':dict(expr='voltage * state'),'twice':dict(expr='power * 2')}
        raw['calculations']=[dict(name='energy',operation='integral',expr='twice')]
        self.validate_schema(raw)
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual([e.root.unit for e in plan.derived_expressions],['W','W'])
        for backend in ('reference','numpy'):
            with AnalysisRunner(backend).run(plan,work_dir=self.root/('units-'+backend)) as result:
                energy=next(result.iter_calculations())
                self.assertEqual((energy.value,energy.unit),(4.,'J'))
        for change in ({'expr':'voltage * state','unit':'V'},{'expr':'twice * 2'},
                       {'expr':'voltage * voltage'},{'expr':'voltage','unit':None}):
            wrong=deepcopy(raw);wrong['derived']['power']=change
            with self.subTest(change=change),self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(wrong)

    def test_threshold_inherits_unit_and_explicit_mismatch_fails(self):
        """同一85→77→75温度序列，省略阈值单位与完整声明结果一致。"""
        from test_threshold_preset import config
        raw=config();raw['presets'][0]['parameters'].pop('unit')
        self.validate_schema(raw)
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.preset_bindings[0][0].contract.unit,'degC')
        for backend in ('reference','numpy'):
            snapshots=[]
            for label,data in (('short',raw),('full',config())):
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(data),work_dir=self.root/(label+backend)) as result:
                    snapshots.append(([(x.start_ns,x.end_ns) for x in result.iter_events()],
                                      [(x.value,x.status) for x in result.metadata.threshold_durations]))
            self.assertEqual(*snapshots)
        raw['presets'][0]['parameters']['unit']='V'
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(raw)
