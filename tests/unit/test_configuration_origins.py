"""验证跨文件错误位置、按请求来源报告以及配置搬移/独立导出。

使用work内合成CSV/CAN/映射/批量文件；独立预期为CSV半开积分6J，
CAN电压积分13Vs。保存路径、行列、原文件不覆盖及公开运行证据，不冒充真实业务。
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from chronaxis import AnalysisRunner, load_analysis_plan, load_batch_plan, run_batch, PlanValidationError
from chronaxis.configuration import load_configuration
from chronaxis.configuration.initialization import initialize_configuration
from chronaxis.configuration.origins import configuration_origins
from chronaxis.configuration.resolution import resolve_configuration, resolved_configuration
from chronaxis.migration import load_legacy_ini
import test_configuration_imports as import_cases
import test_configuration_resolve as resolve_cases
from test_legacy_import_sclicer import mapping_fixture


class ConfigurationOriginsTests(unittest.TestCase):
    """原字段位置由手写行列或未合并原文核对；运行结果由独立小数值核对。"""
    setUp=import_cases.ConfigurationImportsTests.setUp
    write=import_cases.ConfigurationImportsTests.write
    command=import_cases.ConfigurationImportsTests.command
    split=import_cases.ConfigurationImportsTests.split
    assert_semantics=resolve_cases.ConfigurationResolveTests.assert_semantics

    def test_imported_yaml_error_has_exact_original_field_line_and_column(self):
        """第7行有效期错误必须指向公共文件，不是主文件索引。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split();fragment=self.folder/'shared/signals.json'
        fragment=fragment.with_suffix('.yaml')
        fragment.write_text('signals:\n  - name: power\n    source: input\n    field: p\n'
                            '    dtype: float64\n    unit: W\n    valid_for: 0s\n',encoding='utf-8')
        raw['imports'][1]='shared/signals.yaml';path=self.write('plan.yaml',raw)
        with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(path)
        error=caught.exception
        self.assertEqual((error.source,error.path,error.location.line,error.location.column),
                         (str(fragment),'$.signals[0].valid_for',7,16))
        self.assertEqual(error.object_name,'信号 power')
        self.assertEqual(error.value_preview,'"0s"')
        command=self.command('validate',path,'--format','json')
        self.assertEqual(command.returncode,2)
        self.assertIn(str(fragment),json.dumps(json.loads(command.stdout),ensure_ascii=False).replace('\\\\','\\'))

    def test_appended_main_definition_keeps_its_original_index(self):
        """导入后本地信号位于索引1，错误仍回指主文件原索引0。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split()
        raw['signals']=[dict(self.config['signals'][0],name='local',valid_for='0s')]
        path=self.write('plan.json',raw)
        original=load_configuration(path)
        with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(path)
        error=caught.exception
        self.assertEqual(error.path,'$.signals[0].valid_for')
        self.assertEqual(error.source,str(path))
        self.assertEqual(error.location,original.location_for(('signals',0,'valid_for')))
        self.assertEqual(error.object_name,'信号 local')

    def test_missing_imported_field_and_bad_derived_point_to_real_declaration(self):
        """缺字段回指所属对象，派生表达式错误保原名称路径。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split();signal=deepcopy(self.config['signals'][0]);signal.pop('dtype')
        fragment=self.write('shared/signals.json',{'signals':[signal]})
        with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(path)
        self.assertEqual(caught.exception.source,str(fragment))
        self.assertEqual(caught.exception.path,'$.signals[0].dtype')
        self.assertEqual(caught.exception.value_preview,'未提供')
        self.write('shared/signals.json',{'signals':self.config['signals'],
                   'derived':{'broken':{'expr':'power + missing','unit':'W'}}})
        with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(path)
        self.assertEqual(caught.exception.source,str(fragment))
        self.assertIn('derived',caught.exception.path)

    def test_syntax_error_in_imported_json_names_that_file(self):
        """重复JSON键在真实公共文件中拒绝，错误不被主文件替换。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split();fragment=self.folder/'shared/signals.json'
        fragment.write_text('{\n"signals": [],\n"signals": []\n}\n',encoding='utf-8')
        with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(path)
        self.assertEqual(caught.exception.code,'duplicate_key')
        self.assertEqual(caught.exception.source,str(fragment))
        self.assertEqual(caught.exception.location.line,3)

    def test_whole_bundle_can_be_copied_to_another_directory(self):
        """公共定义和数据一起换目录后只使用新目录，保持6J。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split();new=self.root/'relocated';shutil.copytree(self.folder,new)
        plan=load_analysis_plan(new/path.name)
        self.assertIn(str(new),str(plan.sources[0].config.paths[0]))
        with AnalysisRunner().run(plan,self.root/'relocated-run') as result:
            self.assertEqual(next(result.iter_calculations()).value,6.)

    def test_standalone_exports_both_formats_defaults_and_actual_results(self):
        """四种独立导出删除公共文件后仍执行6J，不含imports。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split();outputs=[];before=load_analysis_plan(path)
        for extension in ('json','yaml'):
            for defaults in (False,True):
                output=self.root/f'effective-{defaults}.{extension}'
                resolve_configuration(path,output=output,defaults=defaults);outputs.append(output)
        for relative in raw['imports']:(self.folder/relative).unlink()
        for index,output in enumerate(outputs):
            after=load_analysis_plan(output)
            self.assertNotIn('imports',load_configuration(output).data)
            # --defaults改变原声明及其身份；执行模型和实际结果仍须逐项相等。
            self.assert_semantics(before,after)
            with AnalysisRunner().run(after,self.root/f'export-run-{index}') as result:
                self.assertEqual(next(result.iter_calculations()).value,6.)

    def test_can_paths_array_dbc_and_metadata_have_distinct_handling(self):
        """paths和DBC都按公共文件定位，metadata文字不改；运行保持13Vs。参数: 无。返回: None。异常: 断言。"""
        original=initialize_configuration('can-asc',self.root/'can')
        raw=load_configuration(original).data
        source=raw['sources'][0];source['paths']=[source.pop('path')]
        # 公共定义需要稳定名称，引用明确指向该来源；普通单来源模板可以省略。
        source['name']='can_input'
        for signal in raw['signals']:signal['source']='can_input'
        source['metadata']={'path':'this/is/not/a/file'}
        definitions=original.parent/'definitions.yaml'
        definitions.write_text(json.dumps({key:raw.pop(key) for key in ('sources','signals')}),encoding='utf-8')
        # JSON是YAML 1.2子集；声明仍用.yaml后缀由共同解析器读取。
        raw['imports']=['definitions.yaml'];original.write_text(json.dumps(raw),encoding='utf-8')
        target=self.root/'can-effective.json';resolve_configuration(original,output=target)
        data=load_configuration(target).data;source=data['sources'][0]
        self.assertTrue(Path(source['paths'][0]).is_absolute())
        self.assertTrue(Path(source['dbc_by_channel']['1']).is_absolute())
        self.assertEqual(source['metadata']['path'],'this/is/not/a/file')
        definitions.unlink()
        with AnalysisRunner().run(load_analysis_plan(target),self.root/'can-export-run') as result:
            self.assertEqual(next(result.iter_calculations()).value,13.)

    def test_origins_is_requested_only_and_has_no_configuration_values(self):
        """来源报告只按请求生成，定义与叶字段均保原文件/索引且不抄配置值。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split()
        with patch('chronaxis.configuration.origins.configuration_origins',side_effect=AssertionError('unrequested')):
            plan=load_analysis_plan(path)
            self.assertFalse(hasattr(plan,'origins'))
        report=configuration_origins(path)
        self.assertEqual([item['name'] for item in report['items']],['input','power'])
        self.assertEqual([Path(item['file']).name for item in report['items']],['sources.yaml','signals.json'])
        self.assertTrue(Path(report['items'][0]['resolved_paths'][0]).is_absolute())
        detailed=configuration_origins(path,fields=True)
        field=next(item for item in detailed['items'] if item['effective_path']=='$.signals[0].valid_for')
        self.assertEqual(field['declared_path'],'$.signals[0].valid_for')
        self.assertEqual(Path(field['file']).name,'signals.json')
        self.assertTrue(all('value' not in item for item in detailed['items']))
        self.assertFalse(any(item['effective_path'].startswith('$.imports') for item in detailed['items']))
        for arguments in ((),('--fields','--format','json')):
            command=self.command('config','origins',path,*arguments)
            self.assertEqual(command.returncode,0,command.stderr)
            self.assertIn('signals.json',command.stdout)

    def test_mapping_origin_and_standalone_export(self):
        """映射中的导入错误与独立导出仍回到原文件，INI内容不动。参数: 无。返回: None。异常: 断言。"""
        mapping=mapping_fixture();analysis=mapping['analysis']
        fragment={key:analysis.pop(key) for key in ('sources','signals')}
        definition=self.write('definitions.json',fragment);analysis['imports']=['definitions.json']
        path=self.write('mapping.yaml',mapping)
        ini=self.folder/'source.ini';content=b'[TRIGGER_test]\nmode=single\nexpr=BMS_BatPackHiResSOC > 1\npre_sec=0\npost_sec=0\n';ini.write_bytes(content)
        target=self.root/'mapping-effective.yaml';resolve_configuration(path,output=target)
        definition.unlink()
        self.assertEqual(load_legacy_ini(ini,target,mode='sclicer_single').report.status,'success')
        self.assertEqual(ini.read_bytes(),content)
        fragment['signals'][0]['valid_for']='0s';self.write('definitions.json',fragment)
        result=load_legacy_ini(ini,path,mode='sclicer_single')
        self.assertEqual(result.report.status,'failed')
        issue=next(issue for issue in result.report.issues if 'valid_for' in issue.path)
        self.assertIn(str(definition),issue.message)
        self.assertEqual(issue.path,'$.signals[0].valid_for')

    def test_batch_child_imports_and_origins_do_not_preload_children(self):
        """批量按原隔离规则加载子计划，origins仅列子路径。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split()
        batch=self.write('batch.yaml',dict(batch_version=1,process_count=1,
                         jobs=[dict(name='good',plan=path.name)]))
        with patch('chronaxis.batch.runner.load_analysis_plan',side_effect=AssertionError('eager child')):
            report=configuration_origins(batch)
            self.assertEqual(report['items'][0]['name'],'good')
            plan=load_batch_plan(batch)
        result=run_batch(plan,self.root/'batch-output',device_label='home')
        try:self.assertEqual(result.status,'completed')
        finally:result.close()

    def test_failed_or_cancelled_import_does_not_publish_output(self):
        """坏导入或取消不会创建独立配置，也不修改原配置。参数: 无。返回: None。异常: 断言。"""
        raw,path=self.split();original=path.read_bytes();output=self.root/'not-created.yaml'
        with patch('chronaxis.configuration.imports.load_configuration',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):resolve_configuration(path,output=output)
        self.assertFalse(output.exists());self.assertEqual(path.read_bytes(),original)
        self.write('shared/signals.json',{'imports':['unexpected.yaml']})
        with self.assertRaises(PlanValidationError):resolve_configuration(path,output=output)
        self.assertFalse(output.exists());self.assertEqual(path.read_bytes(),original)


if __name__=='__main__':
    unittest.main()
