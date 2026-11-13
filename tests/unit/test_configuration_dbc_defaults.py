"""[home] DBC默认类型/单位/枚举：真实解码值对照，不将VAL表自动改成文字。"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from chronaxis import AnalysisPlan,AnalysisRunner,PlanValidationError


class ConfigurationDBCDefaultsTests(unittest.TestCase):
    """两个信号共用一份DBC；面积手算1×1+2×1=3Vs。"""
    def setUp(self):
        """建立合成DBC和ASC，不依赖用户实际报文。"""
        self.temp=TemporaryDirectory(prefix='chronaxis-dbc-defaults-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.dbc=self.root/'test.dbc'
        self.write_dbc()
        self.asc=self.root/'input.asc'
        self.asc.write_text('base hex timestamps absolute\n0 1 100 Rx d 2 02 00\n1 1 100 Rx d 2 04 01\n2 1 100 Rx d 2 06 01\n',encoding='utf-8')
        self.raw=dict(config_version=4,dataset=dict(name='defaults',domain=dict(start='0s',end='2s')),
            sources=[dict(path=str(self.asc),dbc_by_channel={'1':str(self.dbc)})],
            signals=[dict(name='voltage',field=dict(frame_id='0x100',signal='Voltage'),valid_for='3s'),
                     dict(name='state',field=dict(frame_id=256,signal='State'),valid_for='3s')],
            rules=[dict(name='on',rule_type='rising_edge',condition='state == 1')],
            calculations=[dict(name='area',operation='integral',expr='voltage')])

    def write_dbc(self,scale='1',offset='0',choices=True,extra=''):
        """State的单位为空；可替换缩放以核对原码表与物理值域的区别。"""
        text=('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 2 Node\n'
            ' SG_ Voltage : 0|8@1+ (0.5,0) [0|127.5] "V" Node\n'
            f' SG_ State : 8|8@1+ ({scale},{offset}) [0|255] "" Node\n')
        if choices:text+='VAL_ 256 State 0 "OFF" 1 "ON";\n'
        self.dbc.write_text(text+extra,encoding='utf-8')

    def test_numeric_defaults_keep_state_codes_and_load_dbc_once(self):
        """有VAL表仍是int数值，比较state==1可用；两个字段只读一次DBC。"""
        import cantools
        from test_configuration_schema import ConfigurationSchemaTests
        ConfigurationSchemaTests.setUpClass()
        ConfigurationSchemaTests.validators['analysis.schema.json'].validate(self.raw)
        with patch('cantools.database.load',wraps=cantools.database.load) as load:
            plan=AnalysisPlan.from_dict(self.raw)
        self.assertEqual(load.call_count,1)
        voltage,state=(s.definition for s in plan.signals)
        self.assertEqual((voltage.dtype.value,voltage.unit),('float64','V'))
        self.assertEqual((state.dtype.value,state.unit,state.choices,state.unit_status),('int64','unknown',(),'unverified'))
        for backend in ('reference','numpy'):
            with AnalysisRunner(backend).run(plan,work_dir=self.root/backend) as result:
                self.assertEqual(next(result.iter_calculations()).value,3.)
                self.assertEqual([row.start_ns for row in result.iter_events()],[10**9])

    def test_enum_defaults_and_integer_scaling_not_applied_twice(self):
        """原码1在DBC缩放后为2，自动映射匹配2而不是再次乘2。"""
        self.write_dbc(scale='2')
        self.raw['signals'][1]['dtype']='enum'
        self.raw['rules'][0]['condition']='state == "ON"'
        plan=AnalysisPlan.from_dict(self.raw)
        self.assertEqual(plan.signals[1].definition.choices,((0,'OFF'),(2,'ON')))
        self.assertEqual(plan.signals[1].definition.unit,'1')
        for backend in ('reference','numpy'):
            with AnalysisRunner(backend).run(plan,work_dir=self.root/('enum-'+backend)) as result:
                self.assertEqual([row.start_ns for row in result.iter_events()],[10**9])
                self.assertEqual(next(result.iter_calculations()).value,3.)

    def test_explicit_complete_declarations_do_not_read_dbc(self):
        """显式字段与手工标签保持原值；静态完整声明不新增文件依赖。"""
        self.raw['signals'][0].update(dtype='float64',unit='V',conversion={'input_unit':'V'})
        self.raw['signals'][1].update(dtype='enum',unit='1',conversion={'input_unit':'1'},choices=[[0,'idle'],[1,'running']])
        self.raw['rules'][0]['condition']='state == "running"'
        with patch('cantools.database.load',side_effect=AssertionError('unexpected DBC load')):
            plan=AnalysisPlan.from_dict(self.raw)
        self.assertEqual(plan.signals[1].definition.choices,((0,'idle'),(1,'running')))
        self.raw['signals'][1].pop('dtype')
        with patch('cantools.database.load',side_effect=AssertionError('unexpected DBC load')):
            self.assertEqual(AnalysisPlan.from_dict(self.raw).signals[1].definition.dtype.value,'enum')

    def test_enum_missing_fractional_or_colliding_table_is_clear_error(self):
        """未定义表、浮点码和缩放碰撞均不猜标签或截断数值。"""
        self.raw['signals'][1]['dtype']='enum'
        self.raw['rules']=[]
        for kwargs,pattern in [({'choices':False},'没有'),({'scale':'0.5'},'浮点'),({'scale':'0'},'重复')]:
            self.write_dbc(**kwargs)
            with self.subTest(kwargs=kwargs),self.assertRaisesRegex(PlanValidationError,pattern):
                AnalysisPlan.from_dict(self.raw)

    def test_missing_dbc_and_explicit_bad_fields_are_not_defaulted(self):
        """推导失败给出具体位置；显式null/空串不当作省略。"""
        original=deepcopy(self.raw)
        for key,value in [('dtype',None),('unit','')]:
            raw=deepcopy(original);raw['signals'][0][key]=value
            with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(raw)
        self.dbc.unlink()
        with self.assertRaisesRegex(PlanValidationError,'DBC'):AnalysisPlan.from_dict(self.raw)

    def test_ambiguous_candidates_require_only_conflicting_metadata(self):
        """同ID标准/扩展定义单位不同时，不替用户选第一份定义。"""
        self.write_dbc(extra='BO_ 2147483904 Extended: 2 Node\n SG_ Voltage : 0|8@1+ (1,0) [0|255] "A" Node\n')
        self.raw['signals'][0]['dtype']='float64'
        with self.assertRaisesRegex(PlanValidationError,'unit不同'):AnalysisPlan.from_dict(self.raw)
        self.raw['signals'][0]['field']['is_extended']=False
        self.assertEqual(AnalysisPlan.from_dict(self.raw).signals[0].definition.unit,'V')

    def test_resolve_reuses_inference_and_expands_only_when_requested(self):
        """两种resolve各只加载一次DBC；默认展开可冻结类型、单位和枚举。"""
        import json,cantools
        from chronaxis.configuration.resolution import resolved_configuration
        self.raw['signals'][1]['dtype']='enum'
        self.raw['rules'][0]['condition']='state == "ON"'
        path=self.root/'plan.json';path.write_text(json.dumps(self.raw),encoding='utf-8')
        for defaults in (False,True):
            with patch('cantools.database.load',wraps=cantools.database.load) as load:
                resolved=resolved_configuration(path,defaults=defaults)
            self.assertEqual(load.call_count,1)
            self.assertEqual('dtype' in resolved['signals'][0],defaults)
            self.assertEqual('choices' in resolved['signals'][1],defaults)
            self.assertEqual(AnalysisPlan.from_dict(resolved).signals,AnalysisPlan.from_dict(self.raw).signals)

    def test_unsigned_64_inference_keeps_integer_type(self):
        """64位无符号范围不能先转float，也不能误选int64。"""
        self.write_dbc(extra='BO_ 257 Big: 8 Node\n SG_ Counter : 0|64@1+ (1,0) [0|18446744073709551615] "" Node\n')
        self.raw['signals'].append(dict(name='counter',field=dict(frame_id=257,signal='Counter'),valid_for='1s'))
        definition=AnalysisPlan.from_dict(self.raw).signals[-1].definition
        self.assertEqual(definition.dtype.value,'uint64')
