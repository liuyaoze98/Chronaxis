"""用真实JSON/YAML文件验证公共定义的一层展开、重复拒绝及既有执行入口。

合成CSV按0秒2W、1秒4W、2秒100W，在[0,2)积分为6J；文件分拆不改结果。
全部文件写work；静态检查只允许配置I/O，业务输入在实际运行测试中才打开。
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner, load_analysis_plan, PlanValidationError
from chronaxis.configuration import load_configuration, parse_configuration
from chronaxis.configuration.imports import expand_document_imports
from chronaxis.configuration.file_tools import convert_configuration, validate_document
from chronaxis.configuration.resolution import resolved_configuration
import test_configuration_entrypoints as entrypoints


class ConfigurationImportsTests(unittest.TestCase):
    """检查展开后的完整执行模型，不能只看imports字段被删除。"""
    setUp=entrypoints.ConfigurationEntrypointTests.setUp
    write=entrypoints.ConfigurationEntrypointTests.write
    command=entrypoints.ConfigurationEntrypointTests.command

    def split(self):
        """来源与信号分别放子目录两个文件。参数: 无。返回: 主配置字典/路径。异常: IO。"""
        (self.folder/'shared').mkdir(exist_ok=True)
        raw=deepcopy(self.config)
        sources=raw.pop('sources');sources[0]['path']='../input.csv'
        self.write('shared/sources.yaml',{'sources':sources})
        self.write('shared/signals.json',{'signals':raw.pop('signals')})
        raw['imports']=['shared/sources.yaml','shared/signals.json']
        return raw,self.write('plan.yaml',raw)

    def test_split_json_yaml_public_run_and_cli(self):
        """两种格式从不同cwd加载且两后端保持6J。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split()
        alternate=self.write('plan.json',raw)
        first=load_analysis_plan(path)
        self.assertEqual(first,load_analysis_plan(alternate))
        for backend in ('reference','numpy'):
            with AnalysisRunner(backend).run(first,self.root/backend) as result:
                self.assertEqual(next(result.iter_calculations()).value,6.)
        for action in ('validate','explain'):
            command=self.command(action,path,'--format','json')
            self.assertEqual(command.returncode,0,command.stderr)
            report=json.loads(command.stdout)
            self.assertTrue((report if action=='validate' else report['validation'])['execution_ready'])

    def test_declaration_order_and_cross_file_derived_reference(self):
        """导入顺序在前，本地在后，表达式仍可跨文件引用。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split()
        first={'signals':[dict(self.config['signals'][0],name='aux')],
               'derived':{'double_power':{'expr':'power * 2','unit':'W'}}}
        self.write('shared/more.yaml',first)
        raw['imports'].append('shared/more.yaml')
        raw['signals']=[dict(self.config['signals'][0],name='local')]
        raw['derived']={'triple_power':{'expr':'double_power + power','unit':'W'}}
        path=self.write('plan.yaml',raw)
        expanded=expand_document_imports(load_configuration(path))
        self.assertEqual([s['name'] for s in expanded.data['signals']],['power','aux','local'])
        self.assertEqual(list(expanded.data['derived']),['double_power','triple_power'])
        self.assertNotIn('imports',expanded.data)
        load_analysis_plan(path)

    def test_duplicate_definitions_never_override(self):
        """来源重名和信号/派生共名都拒绝，不以文件先后来覆盖。参数: 无。返回: None。异常: 断言。"""
        for section,value in (('sources',self.config['sources'][0]),('signals',self.config['signals'][0]),
                              ('derived',dict(name='power',expr='1'))):
            with self.subTest(section=section):
                raw,path=self.split()
                raw[section]={'power':'1'} if section=='derived' else [value]
                with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(self.write('plan.yaml',raw))
                self.assertEqual(caught.exception.code,'duplicate_definition')
                self.assertIn('首次声明',caught.exception.hint)
        raw,path=self.split();raw['imports'].append(raw['imports'][0])
        with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(self.write('plan.yaml',raw))
        self.assertEqual(caught.exception.code,'duplicate_definition')

    def test_fragment_shape_and_nested_import_are_rejected(self):
        """公共文件不能声明规则、版本或第二层导入。参数: 无。返回: None。异常: 断言。"""
        for fragment in ({},[],{'imports':['not-opened.yaml']},{'config_version':4},{'rules':[]},
                         {'signals':None},{'sources':[None]},{'signals':[{'name':False}]}):
            with self.subTest(fragment=fragment):
                raw,path=self.split();self.write('shared/signals.json',fragment)
                with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(path)
                self.assertEqual(Path(caught.exception.source).name,'signals.json')
                self.assertIsNotNone(caught.exception.location)

    def test_invalid_import_paths_and_missing_file_report(self):
        """URL、通配符、空值/非数组拒绝；缺文件报告真实缺失路径。参数: 无。返回: None。异常: 断言。"""
        for imports in (None,'x.yaml',[None],[''],['https://example.test/x.yaml'],['*.json']):
            with self.subTest(imports=imports):
                raw=deepcopy(self.config);raw['imports']=imports
                with self.assertRaises(PlanValidationError):load_analysis_plan(self.write('invalid.yaml',raw))
        raw=deepcopy(self.config);raw['imports']=['absent.json']
        with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(self.write('missing.yaml',raw))
        self.assertEqual(caught.exception.code,'load_error')
        self.assertEqual(Path(caught.exception.source),self.folder/'absent.json')

    def test_static_loading_opens_only_explicit_configuration_files(self):
        """无CSV/DBC/目录扫描，只读主文件和两个公共文件。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split();original=Path.open;opened=[]
        allowed={path,self.folder/'shared/sources.yaml',self.folder/'shared/signals.json'}
        def observed(target,*args,**kwargs):
            """拒绝业务文件I/O。参数: Path及open选项。返回: 句柄。异常: 非白名单断言。"""
            self.assertIn(target,allowed);opened.append(target)
            return original(target,*args,**kwargs)
        with patch.object(Path,'open',observed):load_analysis_plan(path)
        self.assertEqual(opened,[path,self.folder/'shared/sources.yaml',self.folder/'shared/signals.json'])

    def test_in_memory_api_never_reads_imports_and_no_import_fast_path(self):
        """纯字典明确拒绝未展开导入，无导入文档不复制。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split()
        document=parse_configuration(json.dumps(self.config),format='json')
        with patch.object(Path,'open',side_effect=AssertionError('unexpected IO')):
            self.assertIs(expand_document_imports(document),document)
            with self.assertRaises(PlanValidationError) as caught:AnalysisPlan.from_dict(raw)
        self.assertEqual(caught.exception.code,'unresolved_imports')
        self.assertIn('load_analysis_plan',caught.exception.hint)

    def test_convert_preserves_import_list_and_output_location(self):
        """互转保留导入声明，跨目录仍拒绝。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split()
        converted=convert_configuration(path,self.folder/'converted.json')
        self.assertEqual(json.loads(converted.read_text(encoding='utf-8')),raw)
        self.assertEqual(load_analysis_plan(path),load_analysis_plan(converted))
        with self.assertRaises(ValueError):convert_configuration(path,self.root/'bad.json')
        self.assertFalse((self.root/'bad.json').exists())

    def test_resolve_removes_imports_and_reloads_without_definitions(self):
        """独立配置不再读取公共文件且保持执行计划。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split();before=load_analysis_plan(path)
        flattened=resolved_configuration(path)
        self.assertNotIn('imports',flattened)
        output=self.root/'standalone.json';output.write_text(json.dumps(flattened),encoding='utf-8')
        (self.folder/'shared/signals.json').unlink()
        # 目的目录改变base_dir属预期，所有已固定路径、身份和执行字段仍须严格相等。
        self.assertEqual(before,replace(load_analysis_plan(output),base_dir=before.base_dir))

    def test_definition_schema_resolves_local_fields_and_rejects_other_shapes(self):
        """编辑器规范真实引用当前声明，derived仍为名称到对象。参数: 无。返回: None。异常: 验证/断言。"""
        from jsonschema import Draft202012Validator
        from referencing import Registry,Resource
        folder=Path(__file__).resolve().parents[2]/'Docs/Schema'
        registry=Registry()
        for name in ('analysis.schema.json','definitions.schema.json'):
            schema=json.loads((folder/name).read_text(encoding='utf-8'))
            Draft202012Validator.check_schema(schema)
            registry=registry.with_resource((folder/name).as_uri(),Resource.from_contents(schema))
        validator=Draft202012Validator({'$ref':(folder/'definitions.schema.json').as_uri()},registry=registry)
        fragment={'sources':self.config['sources'],'signals':self.config['signals'],
                  'derived':{'double_power':{'expr':'power * 2','unit':'W'}}}
        validator.validate(fragment)
        for invalid in ({},{'imports':[]},{'derived':[]},{'signals':{}},{'sources':[{}]}):
            self.assertFalse(validator.is_valid(invalid),invalid)


if __name__=='__main__':
    unittest.main()
