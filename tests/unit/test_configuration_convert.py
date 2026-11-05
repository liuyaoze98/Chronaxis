"""格式互转保原生类型、路径和新文件保护，不把格式转换当旧结构迁移。"""
from copy import deepcopy
import io
import json
from importlib.util import find_spec
import sys
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis.configuration import load_configuration
from chronaxis.configuration.file_tools import convert_configuration,same_native_value,serialize_configuration
from chronaxis.configuration.initialization import initialize_configuration
from chronaxis.configuration.template_catalog import available_templates
from chronaxis import load_analysis_plan
import test_configuration_init as init_cases


class ConfigurationConvertTests(unittest.TestCase):
    """使用真实模板和原生极值，不从转换输出反推预期。"""
    setUp=init_cases.ConfigurationInitTests.setUp
    command=init_cases.ConfigurationInitTests.command

    def test_all_three_entrypoints_roundtrip_and_keep_order_types_and_paths(self):
        """13场景往返均相同，路径/元数据不变，转换不打开业务输入。参数: 无。返回: None。异常: 断言。"""
        package = Path(find_spec('chronaxis').origin).parent
        schemas = {root / name for root in (package / 'schemas', package.parents[1] / 'Docs' / 'Schema')
                   for name in ('analysis.schema.json', 'batch-v1.schema.json')}
        library_schemas = Path(find_spec('jsonschema_specifications').origin).parent / 'schemas'
        import_roots = {Path(entry).absolute() for entry in sys.path if entry}
        for template in available_templates():
            source=initialize_configuration(template.name,self.root/template.name)
            before=source.read_bytes();raw=load_configuration(source).data
            intermediate=source.with_suffix('.json');last=source.with_name('roundtrip.yml')
            analysis = raw.get('analysis', raw)
            declarations = {source.parent / filename for entry in analysis.get('sources', ())
                            for filename in entry.get('dbc_by_channel', {}).values()}

            def guarded(open_file):
                """限制输入、输出与解码器的只读资源。参数: 打开函数。返回: 受检函数。异常: 越界断言。"""
                def guard(file, mode='r', *args, **kwargs):
                    """核文件、模式和发布目的地。参数: 原打开参数。返回: 文件。异常: 意外访问。"""
                    path = Path(file).absolute()
                    self.assertNotIn(path.suffix.lower(), ('.asc', '.blf', '.csv'), str(path))
                    if mode in ('r', 'rb', 'rt'):
                        metadata = (path.parent.parent in import_roots
                                    and path.parent.name.endswith(('.dist-info', '.egg-info'))
                                    and path.name in ('entry_points.txt', 'METADATA'))
                        self.assertTrue(path in (source, intermediate) or path in declarations or path in schemas
                                        or path.is_relative_to(library_schemas) or metadata, str(path))
                    else:
                        self.assertEqual(mode, 'x')
                        self.assertIn(path, (intermediate, last))
                    return open_file(file, mode, *args, **kwargs)
                return guard

            with patch('io.open', guarded(io.open)), patch('builtins.open', guarded(open)):
                convert_configuration(source,intermediate);convert_configuration(intermediate,last)
            self.assertTrue(same_native_value(raw,load_configuration(last).data))
            self.assertEqual(source.read_bytes(),before)
            if template.config_type=='analysis':self.assertEqual(load_analysis_plan(source),load_analysis_plan(last))
        values={'boolean':True,'integer':18446744073709551615,'floating':1.0,'negative_zero':-0.0,
            'tiny':5e-324,'big':1.7976931348623157e308,'none':None,'strings':['yes','no','012','2026-10-25','1e3','null','中文\n第二行']}
        for format in ('json','yaml'):
            from chronaxis.configuration import parse_configuration
            self.assertTrue(same_native_value(values,parse_configuration(serialize_configuration(values,format),format=format).data))

    def test_rejects_old_versions_unknown_fields_and_relocation_without_output(self):
        """旧版本/业务错误先拒绝；跨目录相对路径不得改变含义。参数: 无。返回: None。异常: 断言。"""
        source=initialize_configuration('signal-csv',self.root/'example');raw=load_configuration(source).data
        for key,value in (('config_version',1),('config_version',True),('unkown',1)):
            wrong=deepcopy(raw);wrong[key]=value;bad=source.with_name('bad.json');bad.write_text(json.dumps(wrong),encoding='utf-8')
            with self.assertRaises(ValueError):convert_configuration(bad,source.parent/'never.yaml')
            self.assertFalse((source.parent/'never.yaml').exists())
        with self.assertRaisesRegex(ValueError,'相对路径'):convert_configuration(source,self.root/'moved.json')
        self.assertFalse((self.root/'moved.json').exists())
        before=source.read_bytes()
        with self.assertRaises(FileExistsError):convert_configuration(source,source)
        alias=source.with_name('hardlink.json');os.link(source,alias)
        with self.assertRaises(FileExistsError):convert_configuration(source,alias)
        self.assertEqual(source.read_bytes(),before)

    def test_cli_convert_and_file_failure_exit_codes(self):
        """实际子进程输出可重新加载；输入缺失1、坏字段2、已有文件1。参数: 无。返回: None。异常: 断言。"""
        source=initialize_configuration('signal-csv',self.root/'example');output=source.with_suffix('.json')
        converted=self.command('config','convert',source,'--output',output)
        self.assertEqual(converted.returncode,0,converted.stderr)
        self.assertEqual(load_analysis_plan(source),load_analysis_plan(output))
        self.assertEqual(self.command('config','convert',source,'--output',output).returncode,1)
        self.assertEqual(self.command('config','convert',self.root/'missing.yaml','--output',output).returncode,1)
        self.assertEqual(self.command('config','convert',source,'--output',self.root/'moved.json').returncode,2)


if __name__=='__main__':unittest.main()
