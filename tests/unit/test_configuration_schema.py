"""独立标准验证器离线读取四规范，检查字段说明、引用及实际缺省行为的一致性。"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry,Resource
from chronaxis import AnalysisPlan,load_analysis_plan
from test_analysis_plan import config_fixture
from test_legacy_import_sclicer import mapping_fixture

ROOT=Path(__file__).resolve().parents[2]
SCHEMAS=ROOT/'Docs'/'Schema'


def nodes(value):
    """枚举规范对象，不读取任何引用。参数: 原生规范。返回: dict迭代器。异常: 无。"""
    if isinstance(value,dict):
        yield value
        for item in value.values():yield from nodes(item)
    elif isinstance(value,list):
        for item in value:yield from nodes(item)


class ConfigurationSchemaTests(unittest.TestCase):
    """只注册四个当前本地文件，未知引用即失败；不能靠网络或旧版本补齐。"""

    @classmethod
    def setUpClass(cls):
        """读四规范并建立离线注册表。参数: 无。返回: None。异常: 标准验证或文件错误。"""
        cls.documents={name:json.loads((SCHEMAS/name).read_text(encoding='utf-8')) for name in
            ('analysis.schema.json','batch-v1.schema.json','legacy-import-v1.schema.json','definitions.schema.json')}
        registry=Registry()
        for name,value in cls.documents.items():
            Draft202012Validator.check_schema(value)
            registry=registry.with_resource((SCHEMAS/name).as_uri(),Resource.from_contents(value))
        cls.validators={name:Draft202012Validator({'$ref':(SCHEMAS/name).as_uri()},registry=registry)
            for name in cls.documents}

    def test_all_property_enum_and_constant_declarations_are_explained(self):
        """每个实际属性与选择分支都有说明，避免只解释顶层或漏重复分支。参数: 无。返回: None。异常: 断言。"""
        count=0
        for name,document in self.documents.items():
            for node in nodes(document):
                for key,property_ in node.get('properties',{}).items():
                    self.assertGreaterEqual(len(property_.get('description','')),10,(name,key))
                    count+=1
                if 'enum' in node or 'const' in node:
                    self.assertTrue(node.get('description'),(name,node))
                if '$ref' in node:
                    self.assertFalse(node['$ref'].startswith(('urn:','http:','https:')),node['$ref'])
        # 原657项加严格持续比较、ASC及混合ASC/BLF的input_check共3项；逐项说明仍必验。
        self.assertEqual(count,660)

    def test_current_analysis_examples_and_all_three_local_references_validate(self):
        """有效分析、批量、INI映射都能离线标准校验；被引用的当前结构确实生效。参数: 无。返回: None。异常: 断言/引用错误。"""
        analysis=self.validators['analysis.schema.json']
        analysis.validate(config_fixture())
        names=('analysis_plan.json','command_response_plan.json','presets_plan.json','stability_plan.json',
            'start_end_plan.json','threshold_excursion_plan.json','window_delta_plan.json',
            'm3_text_input/asc-plan.json','m3_text_input/csv-plan.json')
        for name in names:
            with self.subTest(name=name):
                path=ROOT/'examples'/name
                analysis.validate(json.loads(path.read_text(encoding='utf-8')))
                load_analysis_plan(path)
        self.validators['batch-v1.schema.json'].validate(dict(batch_version=1,jobs=[dict(name='task',plan='analysis.yml')]))
        mapping=self.validators['legacy-import-v1.schema.json']
        raw=mapping_fixture();mapping.validate(raw)
        wrong=deepcopy(raw);wrong['analysis']['config_version']=1
        self.assertFalse(mapping.is_valid(wrong))
        wrong=deepcopy(raw);wrong['analysis']['signals'][0]['valid_for']=500
        self.assertFalse(mapping.is_valid(wrong))
        wrong=deepcopy(raw);wrong['aliases']['OBC_OpMod']='not-a-simple-name'
        self.assertFalse(mapping.is_valid(wrong))

    def test_annotations_do_not_write_defaults_and_match_actual_plan_defaults(self):
        """default是说明而非回填，核已实现的资源/输出/信号及规则缺省。参数: 无。返回: None。异常: 断言。"""
        config=config_fixture();before=deepcopy(config)
        self.validators['analysis.schema.json'].validate(config)
        self.assertEqual(config,before)
        plan=AnalysisPlan.from_dict(config)
        props=self.documents['analysis.schema.json']['properties']
        for key in ('backend','batch_rows','memory_budget_bytes','result_buffer_rows','partial_policy','spool_quota_bytes','on_budget_exceeded'):
            self.assertEqual(props['execution']['properties'][key]['default'],getattr(plan.execution,key))
        for key in ('tables','manifest','contributions','signal_csv','can_frames'):
            self.assertEqual(props['outputs']['properties'][key]['default'],getattr(plan.outputs,key))
        signal=plan.signals[0].definition
        for key in ('scale','offset','sample_policy','same_time_policy'):
            self.assertEqual((props['signals']['items']['oneOf'][0]['properties']['conversion']['properties'] if key in ('scale','offset') else props['signals']['items']['oneOf'][0]['properties'])[key]['default'],getattr(signal,key))
        by_rule={r['properties']['rule_type']['const']:r['properties'] for r in props['rules']['items']['oneOf']}
        self.assertTrue(by_rule['start_end']['emit_initial']['default'])
        self.assertFalse(by_rule['rising_edge']['emit_initial']['default'])
        self.assertNotIn('emit_initial',by_rule['condition_duration'])
        # 条件继承不能伪装成统一固定默认值；input_unit省略也不应填写null。
        self.assertNotIn('default',props['calculations']['items']['properties']['partial_policy'])
        self.assertNotIn('default',props['signals']['items']['oneOf'][0]['properties']['conversion']['properties']['input_unit'])
        for document in self.documents.values():
            for node in nodes(document):
                if 'default' in node:self.assertTrue(Draft202012Validator(node).is_valid(node['default']),node)
                for example in node.get('examples',[]):self.assertTrue(Draft202012Validator(node).is_valid(example),node)

    def test_contextual_fields_explain_different_meanings(self):
        """同名offset/window/start按所属对象说明，partial长度政策不冒充额外解码。参数: 无。返回: None。异常: 断言。"""
        props=self.documents['analysis.schema.json']['properties']
        self.assertIn('数值',props['signals']['items']['oneOf'][0]['properties']['conversion']['properties']['offset']['description'])
        clock=props['sources']['items']['oneOf'][0]['properties']['time']['oneOf'][0]
        self.assertIn('时间',clock['properties']['offset']['description'])
        rule=next(item for item in props['rules']['items']['oneOf'] if item['properties']['rule_type']['const']=='window_delta')
        self.assertIn('回看窗口长度',rule['properties']['window']['description'])
        self.assertIn('点规则',props['sequences']['items']['properties']['start']['description'])
        self.assertIn('DLC',props['sources']['items']['oneOf'][2]['properties']['reader']['properties']['decode_policy']['description'])


if __name__=='__main__':
    unittest.main()
