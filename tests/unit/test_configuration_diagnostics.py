"""从真实文件验证错误能定位并指导修改；静态检查不得读数据，建议不替用户改值。"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ruamel.yaml import YAML
from chronaxis import load_analysis_plan, load_batch_plan, PlanValidationError
from chronaxis.configuration.diagnostics import field_path_parts
from chronaxis.configuration.models import field_path_text
from test_analysis_plan import config_fixture


class ConfigurationDiagnosticTests(unittest.TestCase):
    """每例独立work目录，诊断位置通过原文字行核对。"""

    def setUp(self):
        """准备独立目录。参数: 无。返回: None。异常: 实际IO错误。"""
        self.root=Path(tempfile.mkdtemp(prefix='configuration-diagnostics-',dir='work')).resolve()

    def write(self,data,suffix='yaml'):
        """保存标准输出的原生配置。参数: 值/后缀。返回: 文件。异常: IO或格式错误。"""
        path=self.root/('plan.'+suffix)
        if suffix=='json':
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        else:
            writer=YAML(typ='safe',pure=True)
            writer.default_flow_style=False
            with path.open('w',encoding='utf-8') as stream:
                writer.dump(data,stream)
        return path

    def failure(self,path,loader=load_analysis_plan):
        """只允许实际配置I/O并捕获拒绝。参数: 路径/入口。返回: 异常。异常: 断言。"""
        original=Path.open
        def selected(target,*args,**kwargs):
            """阻止意外数据/DBC读取。参数: 路径/参数。返回: FD。异常: 非选定文件断言。"""
            schemas = Path(__file__).resolve().parents[2] / 'Docs' / 'Schema'
            self.assertIn(target, (path, schemas/'analysis.schema.json', schemas/'batch-v1.schema.json'))
            return original(target,*args,**kwargs)
        with patch.object(Path,'open',selected),self.assertRaises(PlanValidationError) as caught:
            loader(path)
        error=caught.exception
        self.assertEqual(error.source,str(path))
        self.assertIsNotNone(error.location)
        self.assertIn(str(path),str(error))
        return error

    def test_duration_has_source_field_object_value_constraint_and_example(self):
        """有效期0ns在两格式都拒绝，指出实际信号及带单位修正例。参数: 无。返回: None。异常: 断言。"""
        config=config_fixture();config['signals'][0]['valid_for']='0ns'
        for suffix in ('json','yaml'):
            path=self.write(config,suffix);error=self.failure(path)
            self.assertEqual((error.path,error.code),('$.signals[0].valid_for','invalid_duration'))
            self.assertEqual(error.object_name,'信号 current')
            self.assertEqual(error.value_preview,'"0ns"')
            self.assertIn('大于0',error.message)
            self.assertIn('"1s"',error.hint)
            lines=path.read_text(encoding='utf-8').splitlines()
            index=next(i for i,line in enumerate(lines) if '0ns' in line)
            self.assertEqual(error.location.line,index+1)
            token='"0ns"' if suffix=='json' else '0ns'
            self.assertEqual(error.location.column,lines[index].index(token)+1)
            self.assertEqual(error.to_dict()['line'],index+1)
            self.assertFalse(any(key in vars(error) for key in ('document','locations','data')))

    def test_unknown_field_suggests_without_accepting_or_changing_input(self):
        """拼写建议指原错误键，且原始文件/字典保持。参数: 无。返回: None。异常: 断言。"""
        config=config_fixture();config['signals'][0]['valid_fro']='2s';before=deepcopy(config)
        path=self.write(config);content=path.read_bytes();error=self.failure(path)
        self.assertEqual((error.path,error.code),('$.signals[0].valid_fro','unknown_field'))
        self.assertIn('valid_for',error.hint)
        self.assertEqual(path.read_bytes(),content);self.assertEqual(config,before)
        config['signals'][0]['wrong.key[0]']=False;del config['signals'][0]['valid_fro']
        error=self.failure(self.write(config,'json'))
        self.assertEqual(error.path,'$.signals[0]["wrong.key[0]"]')
        self.assertEqual(error.value_preview,'false')

    def test_missing_field_points_to_owner_and_does_not_invent_a_value(self):
        """缺项明确未提供并定位对象起点，不捏造缺项所在行。参数: 无。返回: None。异常: 断言。"""
        config=config_fixture();del config['signals'][0]['unit']
        path=self.write(config);error=self.failure(path)
        self.assertEqual((error.path,error.code),('$.signals[0].unit','missing_field'))
        self.assertEqual(error.value_preview,'未提供')
        self.assertEqual(error.object_name,'信号 current')
        text=path.read_text(encoding='utf-8').splitlines()[error.location.line-1]
        self.assertTrue(text.lstrip().startswith('- '),text)

    def test_enum_reference_and_expression_keep_exact_original_fields(self):
        """枚举给允许值，引用给已声明名，表达式保内部语法原因。参数: 无。返回: None。异常: 断言。"""
        cases=(('signals',0,'source','missing','invalid_reference','table'),
               ('calculations',0,'operation','mean','invalid_choice','sample_mean'),
               ('rules',0,'condition','current ** 2','invalid_config','行1列'))
        for group,index,key,value,code,evidence in cases:
            config=config_fixture();config[group][index][key]=value
            error=self.failure(self.write(config))
            self.assertEqual((error.path,error.code),(f'$.{group}[{index}].{key}',code))
            self.assertIn(evidence,str(error))
            self.assertEqual(error.value_preview,json.dumps(value,ensure_ascii=False))

    def test_batch_workers_and_duplicate_jobs_are_located_without_child_io(self):
        """批量限制落到实际字段，重复id指第二个任务。参数: 无。返回: None。异常: 断言。"""
        data=dict(batch_version=1,jobs=[dict(name='one',plan='missing.yml')],process_count=0)
        error=self.failure(self.write(data),load_batch_plan)
        self.assertEqual((error.path,error.code),('$.process_count','out_of_range'))
        data['process_count']=1;data['jobs'].append(dict(name='ONE',plan='missing.json'))
        error=self.failure(self.write(data),load_batch_plan)
        self.assertEqual((error.path,error.code),('$.jobs[1].name','duplicate_id'))
        self.assertEqual(error.object_name,'任务 ONE')


    def test_quoted_paths_round_trip_and_compound_paths_are_not_falsely_located(self):
        """含点号/引号键可逆，不将组合错误假装成一个源码字段。参数: 无。返回: None。异常: 断言。"""
        parts=('signals',0,'引号".[]')
        self.assertEqual(field_path_parts(field_path_text(parts)),parts)
        self.assertIsNone(field_path_parts('$.signals/derived'))


if __name__=='__main__':
    unittest.main()
