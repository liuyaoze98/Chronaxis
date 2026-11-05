"""有效配置展开保执行语义、默认及源路径；预设只在独立副本展开一次。"""
from dataclasses import fields,is_dataclass
from collections.abc import Mapping
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis import load_analysis_plan
from chronaxis.core.expression import StaticExpression
from chronaxis.core.declarations import DeclarationBindings
from chronaxis.core.message_binding import MessageDeclarations
from chronaxis.configuration import load_configuration,parse_configuration
from chronaxis.configuration.initialization import initialize_configuration
from chronaxis.configuration.resolution import resolved_configuration,resolve_configuration
from chronaxis.configuration.template_catalog import available_templates
import test_configuration_init as init_cases
import test_configuration_templates as template_cases


def semantic_value(value):
    """只排除声明文本指纹，仍逐字段比较执行模型。参数: typed值。返回: 可比较嵌套值。异常: 无。"""
    if is_dataclass(value):
        excluded={'input_identity'}
        if isinstance(value,(StaticExpression,DeclarationBindings,MessageDeclarations)):excluded.add('identity')
        return (type(value),tuple((f.name,semantic_value(getattr(value,f.name))) for f in fields(value) if f.name not in excluded))
    if isinstance(value,Mapping):return {k:semantic_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(semantic_value(v) for v in value)
    return value


class ConfigurationResolveTests(unittest.TestCase):
    """只比较声明与独立结果，不以身份哈希不变代替执行意义不变。"""
    setUp=init_cases.ConfigurationInitTests.setUp
    command=init_cases.ConfigurationInitTests.command
    collect=template_cases.ConfigurationTemplateTests.collect
    check_expected=template_cases.ConfigurationTemplateTests.check_expected

    def assert_semantics(self,before,after):
        """比较全部执行节点及来源typed配置，允许raw_config/身份随显式化改变。参数: 两计划。返回: None。异常: 断言。"""
        for key in ('dataset','signals','derived','rules','windows','calculations','message_calculations','sequences','execution','outputs','diagnostics'):
            self.assertEqual(semantic_value(getattr(before,key)),semantic_value(getattr(after,key)),key)
        self.assertEqual([s.config for s in before.sources],[s.config for s in after.sources])
        self.assertEqual(before.intervals.resolved,after.intervals.resolved)

    def test_all_templates_relocate_and_defaults_keep_typed_semantics(self):
        """12场景导出到不同目录，两格式及默认开关均可重新加载，原字节不动。参数: 无。返回: None。异常: 断言。"""
        for template in available_templates():
            source=initialize_configuration(template.name,self.root/template.name);before=source.read_bytes()
            for defaults in (False,True):
                for suffix in ('yaml','json'):
                    with self.subTest(scene=template.name,defaults=defaults,suffix=suffix):
                        target=self.root/(template.name+str(defaults)+'.'+suffix)
                        resolve_configuration(source,output=target,defaults=defaults)
                        if template.config_type=='analysis':
                            self.assert_semantics(load_analysis_plan(source),load_analysis_plan(target))
                            self.assertNotIn('presets',load_configuration(target).data)
                        elif template.config_type=='batch':
                            from chronaxis import load_batch_plan
                            self.assertEqual(load_batch_plan(source),load_batch_plan(target))
            self.assertEqual(source.read_bytes(),before)

    def test_defaults_inherit_and_exported_scenes_execute(self):
        """独立38J/充电/迟滞结果在展开后保持；部分政策继承实际父设置。参数: 无。返回: None。异常: 断言。"""
        for scene in ('signal-csv','charge-session','stability','can-asc'):
            source=initialize_configuration(scene,self.root/scene)
            target=self.root/(scene+'.yaml');resolve_configuration(source,output=target,defaults=True)
            folder=self.root/(scene+'-run');folder.mkdir()
            self.check_expected(scene,self.collect(load_analysis_plan(target),folder))
        raw=load_configuration(source).data;raw['execution']={'partial_policy':'strict'}
        source=source.with_suffix('.json');source.write_text(json.dumps(raw),encoding='utf-8')
        resolved=resolved_configuration(source,defaults=True)
        self.assertEqual(resolved['calculations'][0]['partial_policy'],'strict')
        self.assertEqual(resolved['execution']['backend'],'numpy')
        self.assertFalse(resolved['diagnostics']['trace'])

    def test_cli_stdout_and_export_no_business_input_reads(self):
        """终端JSON没有额外提示污染；导出静态只读配置，拒绝覆盖及格式矛盾。参数: 无。返回: None。异常: 断言。"""
        source=initialize_configuration('can-blf',self.root/'example');original=Path.open
        def guard(path,*args,**kwargs):
            """静态阶段只允许配置FD。参数: 打开参数。返回: FD。异常: 断言。"""
            self.assertEqual(path,source);return original(path,*args,**kwargs)
        with patch.object(Path,'open',guard):resolved_configuration(source,defaults=True)
        printed=self.command('config','resolve',source,'--defaults','--format','json')
        self.assertEqual(printed.returncode,0,printed.stderr)
        self.assertEqual(json.loads(printed.stdout)['execution']['backend'],'numpy')
        self.assertEqual(self.command('config','resolve',source,'--output',source).returncode,1)
        self.assertEqual(self.command('config','resolve',source,'--output',self.root/'bad.json','--format','yaml').returncode,2)
        self.assertFalse((self.root/'bad.json').exists())

    def test_existing_examples_cover_special_rules_and_interval_defaults(self):
        """原示例补窗口变化、start_end及复杂预设，不只验新模板覆盖的字段。参数: 无。返回: None。异常: 断言。"""
        root=Path(__file__).resolve().parents[2]
        for name in ('analysis_plan','command_response_plan','presets_plan','stability_plan',
                'start_end_plan','threshold_excursion_plan','window_delta_plan'):
            with self.subTest(name=name):
                source=root/'examples'/(name+'.json');output=self.root/(name+'.yaml')
                resolve_configuration(source,output=output,defaults=True)
                self.assert_semantics(load_analysis_plan(source),load_analysis_plan(output))

    def test_fixed_and_dbc_periods_remain_explicit_without_reading_dbc(self):
        """固定周期字段仍为value，DBC只展开驱动，不虚构周期。参数: 无。返回: None。异常: 断言。"""
        source=initialize_configuration('can-asc',self.root/'can')
        raw=load_configuration(source).data
        for mode in ('fixed','dbc'):
            raw['intervals']={'default':{'mode':mode}}
            if mode=='fixed':raw['intervals']['default']['value']='1s'
            input_=source.with_name(mode+'.json');input_.write_text(json.dumps(raw),encoding='utf-8')
            output=self.root/(mode+'.yaml');resolve_configuration(input_,output=output,defaults=True)
            self.assert_semantics(load_analysis_plan(input_),load_analysis_plan(output))
            selected=next(item for item in load_configuration(output).data['calculations'] if item['name']=='voltage_area')['interval']
            self.assertEqual(selected['driver'],'voltage')
            if mode=='fixed':self.assertEqual(selected['value'],'1000000000ns')
            else:self.assertNotIn('value',selected)


if __name__=='__main__':unittest.main()
