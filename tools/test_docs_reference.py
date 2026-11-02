"""检查DOC-M3-03修复的参数提取与构造字段展示问题。

输入为本文件声明的最小Python源码与说明片段，输出为unittest检查结果。
运行python -B tools/test_docs_reference.py；只导入文档生成器，不导入产品、
读取日志或改写文档。用固定预期区分必填、默认工厂、计算字段和实例接收参数。
"""

import ast
import unittest

import build_m2_docs as docs
from doc_type_links import imports, type_cell
from doc_public_api import members, public_page


class ReferenceTables(unittest.TestCase):
    """每项检查临时使用M3生成规则，结束后恢复版本，避免影响其他检查。"""

    def setUp(self):
        """启用本项的M3规则。参数: 无。返回: None。异常: 属性错误原样传播。"""
        # 保存原值，防止单项失败后把测试进程永久留在M3模式。
        self.edition = docs.EDITION
        docs.EDITION = 'M3'

    def tearDown(self):
        """恢复原版本。参数: 无。返回: None。异常: 属性错误原样传播。"""
        docs.EDITION = self.edition

    def test_group_heading_does_not_absorb_next_parameter(self):
        """核对组合标题的边界。参数: 无。返回: None。异常: 不匹配时AssertionError。"""
        # 斜杠及顿号都可分隔同组名称，但下一组的说明不能并入前组。
        section = 'before/continuous/point: 三种视图。\nquality、diagnostic (QualityFlag): 质量组合。\nrefs: 来源引用。'
        self.assertEqual(docs.describe_parameter('point', section, {}, 'f'), ('三种视图。', False))
        self.assertEqual(docs.describe_parameter('quality', section, {}, 'f'), ('质量组合。', False))
        self.assertEqual(docs.describe_parameter('refs', section, {}, 'f'), ('来源引用。', False))

    def test_field_without_default_is_required(self):
        """区分字段工厂和必填字段。参数: 无。返回: None。异常: 解析或断言错误。"""
        # repr=False不提供默认值；默认工厂和init=False各有不同的填写要求。
        source = '@dataclass\nclass Model:\n    value: int = field(repr=False)\n    items: tuple = field(default_factory=tuple)\n    derived: int = field(init=False)\n'
        node = ast.parse(source).body[0]
        rows = docs.fields(node, source.splitlines())
        self.assertEqual(docs.documented_item(rows[0], {}, node, is_field=True), ('int', '是', '无'))
        self.assertEqual(docs.documented_item(rows[1], {}, node, is_field=True), ('tuple', '否', '()'))
        self.assertEqual(docs.documented_item(rows[2], {}, node, is_field=True), ('int', '不填写', '构造时计算'))

    def test_custom_constructor_fields_are_not_arguments(self):
        """核对自定义构造字段。参数: 无。返回: None。异常: 解析或断言错误。"""
        # dataclass没有生成构造器时，声明属性不能冒充可直接传入的同名参数。
        source = '@dataclass(init=False)\nclass Model:\n    cached: int\n'
        node = ast.parse(source).body[0]
        row = docs.fields(node, source.splitlines())[0]
        self.assertEqual(docs.documented_item(row, {}, node, is_field=True)[1], '不直接填写')

    def test_python_receiver_is_not_user_input(self):
        """核对实例接收参数和空值默认。参数: 无。返回: None。异常: 解析或断言错误。"""
        # self由Python传入；value可省略，人工补充类型不能丢失真实默认值。
        node = ast.parse('def f(self, value=None): pass').body[0]
        row = docs.parameters(node)[0]
        self.assertEqual(docs.documented_item(row, {}, node), ('当前实例', '不手动传入', 'Python自动传入'))
        override = {'parameters': {'value': {'type': 'str | None', 'description': 'None表示未设置。'}}}
        self.assertEqual(docs.documented_item(docs.parameters(node)[1], override, node), ('str | None', '否', 'None'))

    def test_call_signature_preserves_keyword_boundary(self):
        """调用签名移除接收者并保留位置/关键字边界。"""
        node = ast.parse('def run(self, plan, /, *, work_dir=None) -> int: pass').body[0]
        self.assertEqual(docs.call_signature('Runner.run', node), 'Runner.run(plan, /, *, work_dir=None) -> int')

    def test_property_is_not_rendered_as_method(self):
        """属性类型可读，但不制造函数调用。"""
        node = ast.parse('@property\ndef backend(self) -> str | None: pass').body[0]
        self.assertEqual(docs.call_signature('Runner.backend', node), 'Runner.backend: str | None')

    def test_public_class_uses_verified_constructor(self):
        """公开类使用实测构造签名；字段不能覆盖构造参数。"""
        node = ast.parse('class Runner:\n    cached: int\n').body[0]
        prior = docs.PUBLIC_SIGNATURES
        try:
            docs.PUBLIC_SIGNATURES = {'pkg.Runner': '(*, backend=None)'}
            self.assertEqual(docs.call_signature('Runner', node, 'pkg.Runner'), 'Runner(*, backend=None)')
        finally:
            docs.PUBLIC_SIGNATURES = prior

    def test_type_links_follow_import_identity(self):
        """参数: 无。返回: None。异常: 同名Event或Q别名误链时断言失败。"""
        aliases=imports('from threading import Event\nfrom ..core.types import QualityFlag as Q\n','chronaxis.batch.models')
        known={'chronaxis.core.types.QualityFlag':'quality.md#api-QualityFlag','chronaxis.core.events.Event':'wrong.md'}
        linked=type_cell('tuple[Event | Q, ...]', 'chronaxis.batch.models',aliases,known,{})
        self.assertIn('[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects)',linked)
        self.assertIn('[QualityFlag（源码别名Q）](quality.md#api-QualityFlag)',linked)
        self.assertNotIn('wrong.md',linked)

    def test_unknown_or_ambiguous_type_stays_unlinked(self):
        """参数: 无。返回: None。异常: 未导入同名类型被猜测关联时失败。"""
        aliases=imports('from a import Event\nfrom b import Event\n','pkg.module')
        self.assertEqual(type_cell('Event | None','pkg.module',aliases,{'elsewhere.Event':'wrong.md'},{}),'Event | None')

    def test_public_view_omits_private_and_nested_members(self):
        """参数: 无。返回: None。异常: 私有、嵌套或其他类混入公开页时失败。"""
        names=['Runner','Runner.__init__','Runner.run','Runner.run.nested','Runner._cleanup','Runner.__post_init__','Runner.__enter__','Other']
        record={'module':'pkg.runner','objects':[{'name':n} for n in names]}
        expected=['Runner','Runner.__init__','Runner.run','Runner.__enter__']
        self.assertEqual(members('Runner',record['objects']),expected)
        content=''.join(f'<a id="{docs.anchor(n)}"></a>\n## {n}\n\nText for {n}\n' for n in names)
        result=public_page({'name':'Runner','qualified':'Runner'},record,content,{},docs.anchor)
        for n in ('Runner._cleanup','Runner.run.nested','Runner.__post_init__','Other'):self.assertNotIn(n,result)
        for n in expected:self.assertIn(n,result)

    def test_class_overview_never_becomes_field_description(self):
        """字段缺说明必须进入审核清单；不能把类概述填入字段表。"""
        previous_language=docs.LANGUAGE
        try:
            docs.EDITION='Current';docs.LANGUAGE={'phrases':{},'terms':[]}
            source='class Example:\n    """整体用途，不是字段说明。"""\n    value: int\n'
            rendered,_,missing=docs.render_module('src/chronaxis/example.py',source,{})
            self.assertEqual(missing,['chronaxis.example.Example:value'])
            row=next(line for line in rendered.splitlines() if line.startswith('|`value`|'))
            self.assertNotIn('整体用途',row)
            self.assertIn('尚缺独立说明',row)
        finally:
            docs.LANGUAGE=previous_language


if __name__ == '__main__':
    # 仅显式运行本文件时启动检查，导入不会执行测试或修改输出文件。
    unittest.main()
