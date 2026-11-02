"""对照标准JSON和手写YAML语义，核受限语法、位置、隔离及真实配置句柄生命周期。"""
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chronaxis.configuration import (ConfigurationError, ConfigurationLocation,
    field_path_text, load_configuration, parse_configuration)


class ConfigurationParserTests(unittest.TestCase):
    """解析器只转换配置，不打开声明的来源或执行字符串内容。"""

    def parse(self,text,format='yaml'):
        """指定固定显示来源。参数: 文本/格式。返回: 原文档。异常: 原解析错误。"""
        return parse_configuration(text,format=format,source='case.'+format)

    def error(self,text,code,format='yaml'):
        """核稳定错误码并返回错误事实。参数: 文本/码/格式。返回: 错误。异常: 断言失败。"""
        with self.assertRaises(ConfigurationError) as caught:
            self.parse(text,format)
        self.assertEqual(caught.exception.code,code,str(caught.exception))
        return caught.exception

    def test_json_yaml_native_values_and_precision_are_equal(self):
        """同一声明的JSON/YAML保原生类型、Unicode、大整数和负零。参数: 无。返回: None。异常: 断言。"""
        text='''# 手写配置的必要标量
name: "电流"
unit: "1"
values: [null, true, false, 18446744073709551615, -0.0, 1.25e-7, ""]
channels: {"0": "dbc/${NAME}.dbc"}
expression: "a > 0 and b < 2"
message: |-
  第一行
  第二行
'''
        expected=dict(name='电流',unit='1',values=[None,True,False,2**64-1,-0.0,1.25e-7,''],
            channels={'0':'dbc/${NAME}.dbc'},expression='a > 0 and b < 2',message='第一行\n第二行')
        documents=[self.parse(text),self.parse(json.dumps(expected,ensure_ascii=False),'json')]
        for document in documents:
            self.assertEqual(document.data,expected)
            self.assertIs(type(document.data['values'][1]),bool)
            self.assertIs(type(document.data['values'][3]),int)
            self.assertIs(type(document.data['unit']),str)
            self.assertEqual(math.copysign(1,document.data['values'][4]),-1)

    def test_yaml12_ambiguous_words_dates_and_core_numbers(self):
        """1.2不沿用1.1的真假/时间解释，日期保文本而非datetime。参数: 无。返回: None。异常: 断言。"""
        actual=self.parse('values: [yes, No, ON, off, 2026-10-25, 2026-10-25T10:20:30Z, 1:20, 012, 0o12, 0x10, 1_000, TRUE, False, ~]\n').data
        self.assertEqual(actual,dict(values=['yes','No','ON','off','2026-10-25','2026-10-25T10:20:30Z',
            '1:20',12,10,16,1000,True,False,None]))
        self.assertIsNone(self.parse('# 空文档\n').data)
        self.assertEqual(self.parse('empty: ""\nmissing:\n').data,{'empty':'','missing':None})

    def test_json_duplicate_escape_and_nested_path_positions(self):
        """重复键按解码后的键名识别，准确落到第二个嵌套键。参数: 无。返回: None。异常: 断言。"""
        error=self.error('{\n "groups": [\n  {"值": 1, "\\u503c": 2}\n ]\n}','duplicate_key','json')
        self.assertEqual(error.field_path,('groups',0,'值'))
        self.assertEqual(error.location,ConfigurationLocation(3,12))
        self.assertIn('case.json:3:12',str(error))
        self.assertEqual(self.parse('{"a":{"k":1},"b":{"k":2}}','json').data,
            {'a':{'k':1},'b':{'k':2}})

    def test_yaml_duplicate_string_keys_and_array_paths(self):
        """多层映射与流式映射均拒重复，不混淆相邻对象同名键。参数: 无。返回: None。异常: 断言。"""
        error=self.error('groups:\n  - key: 1\n    key: 2\n','duplicate_key')
        self.assertEqual(error.field_path,('groups',0,'key'))
        self.assertEqual(error.location,ConfigurationLocation(3,5))
        self.error('a: {"key": 1, key: 2}','duplicate_key')
        self.assertEqual(self.parse('a: {k: 1}\nb: {k: 2}\n').data,{'a':{'k':1},'b':{'k':2}})

    def test_non_string_yaml_keys_reject_before_coercion(self):
        """数字/真假/null/容器键不转换成字符串；明确引用的数字键可用。参数: 无。返回: None。异常: 断言。"""
        for text in ('0: a','true: a','null: a','? [a, b]\n: x'):
            with self.subTest(text=text):self.error(text,'non_string_key')
        self.assertEqual(self.parse('"0": a\n"true": b\n').data,{'0':'a','true':'b'})

    def test_yaml_features_are_rejected_without_expansion(self):
        """不能用锚点/别名/合并/标签/多文档绕过原生值合同。参数: 无。返回: None。异常: 断言。"""
        cases=[('a: &shared [1]','yaml_anchor'),('a: *missing','yaml_alias'),
            ('<<: {a: 1}','yaml_merge'),('a: !custom value','yaml_tag'),
            ('a: !!str 1','yaml_tag'),('!!map {a: 1}','yaml_tag'),
            ('---\na: 1\n---\na: 2','multiple_documents'),
            ('%YAML 1.1\n---\na: yes','yaml_version'),
            ('%TAG !e! tag:example.org,2000:\n---\na: 1','yaml_tag')]
        for text,code in cases:
            with self.subTest(text=text):self.error(text,code)
        self.assertEqual(self.parse('"<<": literal').data,{'<<':'literal'})
        self.assertEqual(self.parse('value: <<\nother: =\n').data,{'value':'<<','other':'='})

    def test_yaml_lexical_errors_and_version_directives_have_config_errors(self):
        """非法字符有实际行列，不支持的版本或损坏语法统一成配置错误。参数: 无。返回: None。异常: 断言。"""
        error=self.error('a: 1\nb: \x00','invalid_yaml')
        self.assertEqual(error.location,ConfigurationLocation(2,4))
        for text in ('a:\n\tb: 1','a: [1,','%YAML 2.0\n---\na: 1','%YAML 1.3\n---\na: 1'):
            with self.subTest(text=text):
                with self.assertRaises(ConfigurationError):self.parse(text)

    def test_overlong_decimal_has_explicit_error(self):
        """不改变Python进程整数保护配置，也不把超长数字变成文本或零。参数: 无。返回: None。异常: 断言。"""
        import sys
        if sys.get_int_max_str_digits()==0:self.skipTest('运行器未启用十进制整数长度保护')
        number='9'*(sys.get_int_max_str_digits()+1)
        for format in ('json','yaml'):
            with self.subTest(format=format):self.error(number,'invalid_number',format)

    def test_json_escaped_content_does_not_confuse_location_scan(self):
        """键/值内的括号、转义引号和控制字符不参与容器定位。参数: 无。返回: None。异常: 断言。"""
        values={'a"b':[{'[]{}:': '\b\f\n\r\t / \\ " 电流'},[],{}], 'x':123.456}
        for ascii_only in (False,True):
            document=self.parse(json.dumps(values,ensure_ascii=ascii_only,indent=2),'json')
            self.assertEqual(document.data,values)
            self.assertEqual(set(document.locations),{(),('a"b',),('a"b',0),('a"b',0,'[]{}:'),
                ('a"b',1),('a"b',2),('x',)})

    def test_nonfinite_and_overflow_numbers_locate_the_value(self):
        """两格式均拒非有限值，不静默变null/0；大整数仍精确。参数: 无。返回: None。异常: 断言。"""
        for format,tokens in (('json',('NaN','Infinity','-Infinity','1e9999')),
                              ('yaml',('.nan','.Inf','-.inf','1e9999'))):
            for token in tokens:
                with self.subTest(format=format,token=token):
                    text='{"a": ['+token+']}' if format=='json' else 'a: ['+token+']'
                    error=self.error(text,'nonfinite_number',format)
                    self.assertEqual(error.field_path,('a',0))
                    self.assertEqual(error.location.line,1)
        self.assertEqual(self.parse(str(2**2048),'json').data,2**2048)

    def test_json_grammar_stays_strict(self):
        """JSON不因为另有YAML支持而接受注释、尾逗号、单引号或其他数字写法。参数: 无。返回: None。异常: 断言。"""
        for text in ('{a:1}','{"a":1,}',"{'a':1}",'[1,]','+2','01','0x10','True',
                     '{"a": #comment\n1}','{"a":1}\n{"b":2}','"bad\ntext"',''):
            with self.subTest(text=text):
                error=self.error(text,'invalid_json','json')
                with self.assertRaises(json.JSONDecodeError) as standard:json.loads(text)
                self.assertEqual(error.location,ConfigurationLocation(standard.exception.lineno,standard.exception.colno))

    def test_value_positions_and_missing_field_fallback(self):
        """嵌套值/多行文本定位准确；缺失键指向现有父对象。参数: 无。返回: None。异常: 断言。"""
        document=self.parse('items:\n  - name: x\n    text: |-\n      内容\n    count: 5\n')
        self.assertEqual(document.location_for(('items',0,'count')),ConfigurationLocation(5,12))
        self.assertEqual(document.location_for(('items',0,'text')),ConfigurationLocation(3,11))
        self.assertEqual(document.location_for(('items',0,'missing')),ConfigurationLocation(2,5))
        json_doc=self.parse('{\n "值": [\n  {"a.b": 42}\n ]\n}','json')
        self.assertEqual(json_doc.location_for(('值',0,'a.b')),ConfigurationLocation(3,11))
        self.assertEqual(field_path_text(('值',0,'a.b')),'$.值[0]["a.b"]')
        with self.assertRaises(TypeError):document.locations[()]=ConfigurationLocation(9,9)

    def test_deep_inputs_have_explicit_bound_in_both_formats(self):
        """同一64层上限在两格式一致，错误不以Python栈崩溃报告。参数: 无。返回: None。异常: 断言。"""
        for format in ('json','yaml'):
            self.parse('['*64+'0'+']'*64,format)
            self.error('['*65+'0'+']'*65,'nesting_limit',format)

    def test_templates_and_environment_references_remain_literal(self):
        """解析不读取环境或运行表达式；模板字符串只保原文。参数: 无。返回: None。异常: 断言。"""
        text='path: "${SECRET}/file"\nexpression: "{{ dangerous() }}"\n'
        with patch.dict('os.environ',{'SECRET':'do-not-substitute'}):
            self.assertEqual(self.parse(text).data,{'path':'${SECRET}/file','expression':'{{ dangerous() }}'})

    def test_concurrent_and_failed_loads_do_not_share_yaml_state(self):
        """失败后及并发各用独立解析器，格式指令和重复键状态不能串轮。参数: 无。返回: None。异常: 断言。"""
        self.error('%YAML 1.1\n---\na: on','yaml_version')
        with ThreadPoolExecutor(max_workers=8) as pool:
            documents=list(pool.map(self.parse,['a: on\nb: 1\n']*32))
        self.assertTrue(all(item.data=={'a':'on','b':1} for item in documents))
        self.assertEqual(len({id(item.data) for item in documents}),32)

    def test_loader_formats_bom_errors_and_only_config_io(self):
        """真实文件只按后缀读取，未知后缀不打开；源路径只是文本。参数: 无。返回: None。异常: 断言。"""
        root=Path(tempfile.mkdtemp(prefix='config-parser-',dir='work'))
        for suffix,text in (('.JSON','{"path":"missing.blf"}'),('.yaml','path: missing.blf'),('.yml','path: missing.blf')):
            target=root/('plan'+suffix);target.write_text('\ufeff'+text,encoding='utf-8')
            self.assertEqual(load_configuration(target).data,{'path':'missing.blf'})
        with patch.object(Path,'open',side_effect=AssertionError('不应打开')):
            with self.assertRaises(ConfigurationError) as caught:load_configuration(root/'plan.txt')
            self.assertEqual(caught.exception.code,'unsupported_format')
        bad=root/'bad.yaml';bad.write_bytes(b'\xff\xfe')
        with self.assertRaises(ConfigurationError) as caught:load_configuration(bad)
        self.assertEqual(caught.exception.code,'load_error')
        self.assertIsInstance(caught.exception.__cause__,UnicodeError)

    def test_real_fd_is_closed_before_parse_cancel_or_error(self):
        """实际配置FD在后续解析报错/取消前已关，不吞KeyboardInterrupt。参数: 无。返回: None。异常: 断言。"""
        root=Path(tempfile.mkdtemp(prefix='config-fd-',dir='work'));path=root/'config.yaml'
        path.write_text('a: 1',encoding='utf-8');opened=[];original=Path.open
        def observe(target,*args,**kwargs):
            """登记本次真实句柄。参数: 原打开参数。返回: FD。异常: 原IO错误。"""
            handle=original(target,*args,**kwargs);opened.append(handle);return handle
        with patch.object(Path,'open',observe),patch('chronaxis.configuration.parse_configuration',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):load_configuration(path)
        self.assertEqual(len(opened),1)
        self.assertTrue(opened[0].closed)
        path.write_text('a: [',encoding='utf-8')
        with patch.object(Path,'open',observe):
            with self.assertRaises(ConfigurationError):load_configuration(path)
        self.assertTrue(all(handle.closed for handle in opened))


if __name__=='__main__':
    unittest.main()
