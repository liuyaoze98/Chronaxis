"""检查说明重写保留编辑器指令、显式null及不同上下文字段含义。

运行本文件执行unittest；只处理合成字符串，不写用户文件或运行分析。
"""
import unittest
from pathlib import Path
import re
from ruamel.yaml import YAML
from annotate_manual_examples import render
from manual_example_comments import comment, example_comment


class ExampleComments(unittest.TestCase):
    """用独立预期防止注释工具删除有行为含义的指令或串用字段。"""

    def test_editor_directive_and_null(self):
        """保留编辑器关联并显示null；失败时抛断言错误。"""
        result=render('# yaml-language-server: $schema=schemas/analysis.schema.json\noutputs:\n  signal_csv: null\n')
        self.assertIn('# yaml-language-server: $schema=schemas/analysis.schema.json',result)
        self.assertIn('signal_csv: null',result)

    def test_context_specific_names(self):
        """同名字段按完整上下文解释；未知字段必须报错。"""
        self.assertIn('activity',comment('windows[0].anchor'))
        self.assertNotEqual(comment('signals[0].source'),comment('outputs.can_frames.source'))
        with self.assertRaises(KeyError):comment('new_section.source')

    def test_current_structure(self):
        """当前分组与字段迁移不能退回旧公开写法。"""
        self.assertIn('数值',comment('calculations[0].expr'))
        self.assertIn('DBC信号名称',comment('signals[0].signals[1].signal'))
        self.assertIn('固定',comment('sources[0].reader.layout.fields.channel.fixed'))
        self.assertNotIn('event:',comment('calculations[0].scope'))

    def test_inline_mapping_keeps_teaching_syntax(self):
        """内联写法与多行值等价，但必须保留花括号；父行同时解释子字段。"""
        text='dataset:\n  name: energy\n  domain: {start: 2s, end: 5s}\n'
        result=render(text)
        self.assertIn('domain: {start: 2s, end: 5s}',result)
        self.assertIn('start：设置分析起点',result)
        self.assertIn('end：设置分析终点',result)
        self.assertEqual(render(result),result)

    def test_value_and_format_specific_explanations(self):
        """算法和日期说明依本例取值生成，不依赖下载物中不存在的相邻说明。"""
        self.assertIn('false变为true',example_comment('rules[0].rule_type','rising_edge',{}))
        self.assertIn('等权',example_comment('calculations[0].operation','sample_mean',{}))
        self.assertIn('持续时长加权',example_comment('calculations[0].operation','time_weighted_mean',{}))
        blf=example_comment('outputs.can_frames.capture_date','2026-10-23',{'format':'blf'})
        self.assertIn('日历时间',blf)
        self.assertNotIn('ASC',blf)
        with self.assertRaises(KeyError):example_comment('rules[0].rule_type','unknown',{})

    def test_local_parameters_precede_expression(self):
        """只重排真实引用的局部参数；值保持且第二次生成不继续改变输出。"""
        text='message_calculations:\n  - expr: power * period\n    parameters:\n      period:\n        value: 0.1\n        unit: s\n    name: energy\n'
        result=render(text)
        self.assertLess(result.index('parameters:'),result.index('expr:'))
        self.assertEqual(YAML(typ='safe').load(text),YAML(typ='safe').load(result))
        self.assertEqual(render(result),result)

    def test_r3_download_context_survives_regeneration(self):
        """单BLF说明可再生成且不套给ASC；未填等待与明确等待使用不同注释。"""
        root=Path(__file__).resolve().parents[1]/'Docs/Current/examples'
        text=(root/'message-energy.yaml').read_text(encoding='utf8')
        result=render(text,'message-energy.yaml')
        self.assertIn('../inputs.html#解码失败时各读取路径的处理',result)
        self.assertIn('不增加这项DBC长度预检查',result)
        self.assertNotIn('按路径表',result)
        self.assertEqual(render(result,'message-energy.yaml'),result)
        self.assertEqual(YAML(typ='safe').load(text),YAML(typ='safe').load(result))
        with self.assertRaises(AssertionError):render(text.replace('data/power.blf','data/power.asc'),'message-energy.yaml')
        self.assertIn('默认均为0s',example_comment('rules[0].rule_type','debounce',{}))
        self.assertNotIn('默认均为0s',example_comment('rules[0].rule_type','debounce',{'enter_delay':'1s'}))

    def test_all_downloads_and_default_templates_have_field_comments(self):
        """逐键检查实际交付文件，包括父容器和动态键；文件头不能抵充注释。"""
        root=Path(__file__).resolve().parents[1]
        paths=list((root/'Docs/Current/examples').rglob('*.yaml'))
        paths+=list((root/'src/chronaxis/configuration/templates').rglob('annotated.yaml'))
        def check(node,where,parent_comment=''):
            """递归验证注释与已审写字段职责，未知路径继续由render拒绝。"""
            if isinstance(node,dict):
                for key,value in node.items():
                    if node.fa.flow_style():
                        self.assertIn(str(key)+'：',parent_comment,f'{where}.{key}缺少行内用途说明')
                    else:
                        self.assertTrue(node.ca.items.get(key),f'{where}.{key}缺少用途注释')
                    check(value,f'{where}.{key}',str(node.ca.items.get(key)))
            elif isinstance(node,list):
                for index,value in enumerate(node):check(value,f'{where}[{index}]')
        for path in paths:
            text=path.read_text(encoding='utf-8');check(YAML().load(text),str(path))
            self.assertEqual(YAML(typ='safe').load(text),YAML(typ='safe').load(render(text)))
        # 同样检查页面中的业务配置，不把下载文件通过当成网页通过。
        for path in (root/'Docs/Current').glob('*.md'):
            for block in re.findall(r'^[~`]{3}ya?ml\s*\n(.*?)^[~`]{3}',path.read_text(encoding='utf-8'),re.M|re.S):
                check(YAML().load(block),str(path))


if __name__=='__main__':unittest.main()
