"""核对DOC-REVIEW-10的API说明、参数类型和静态失败边界。

输入为当前产品、双语文档来源及教学配置，输出unittest结果。只读配置和DBC，
不运行报文分析、不生成结果或刷新资料。测试以公开调用及真实生成入口验证说明，
并确认runner改动仅为docstring；执行时使用-B避免生成缓存。
"""

import ast
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.extensions import ExtensionRegistry
from chronaxis.fast.batch import prepare_batch, run_batch
from chronaxis.fast.totals import FastTotals
from public_api_catalog import collect
from public_api_english import check_runner_contract, sections, synchronize_page
from public_api_notes import PARAMETER_TYPES, render_note

ROOT = Path(__file__).resolve().parents[1]
# d80218d9的runner执行AST，去除docstring后按下方稳定格式摘要；源码包无需Git历史。
RUNNER_EXECUTION_SHA256 = '02bcf156adf290f8f6f2945bd61b5d8299ff646e59531a073963c59a2ce6272b'


def execution_ast_digest(text):
    """返回不受说明文字、源码位置及空可选AST字段影响的执行摘要。

    参数: Python源码文本。返回: SHA256十六进制字符串。异常: 语法错误传播。
    Python 3.12/3.13均使用节点类型和字段名编码，不使用版本相关的ast.dump格式；
    空type_params等可选字段不参与摘要，列表中的None仍保留其位置和含义。
    """
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                if isinstance(node.body[0].value.value, str):
                    node.body.pop(0)

    def encode(node):
        """参数: AST节点、字段列表或常量。返回: JSON值。异常: 不可编码字段在json.dumps拒绝。"""
        if isinstance(node, ast.AST):
            return {'node': type(node).__name__, 'fields': {
                name: encode(value) for name, value in ast.iter_fields(node)
                if value is not None and value != []}}
        if isinstance(node, list):
            return [encode(value) for value in node]
        return node

    encoded = json.dumps(encode(tree), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return sha256(encoded.encode('utf8')).hexdigest()


class ManualAPIReview(unittest.TestCase):
    """按触发条件核对异常、生成类型与翻译，禁止进入真实任务派发。"""

    def test_runner_constructor_and_registry_identity(self):
        """参数: 无。返回: 无。异常: 构造取值或同一注册对象契约不符时断言失败。"""
        for backend in (None, 'auto', 'reference', 'numpy'):
            self.assertEqual(AnalysisRunner(backend).backend, backend)
        for value, error in ((False, TypeError), ('missing', ValueError)):
            with self.assertRaises(error):
                AnalysisRunner(value)
        with self.assertRaisesRegex(TypeError, 'extensions需要宿主建立的ExtensionRegistry'):
            AnalysisRunner(extensions=object())
        registry = ExtensionRegistry()
        plan = load_analysis_plan(ROOT/'Docs/Current/examples/calculation-minimal.yaml', extensions=registry)
        # 即使两个注册表声明相同，静态入口仍要求对象身份相同；错误发生在返回报告前。
        for other in (None, ExtensionRegistry()):
            for method in ('validate', 'explain'):
                with self.assertRaisesRegex(ValueError, '必须使用同一个宿主注册'):
                    getattr(AnalysisRunner(extensions=other), method)(plan)
        runner = AnalysisRunner(extensions=registry)
        self.assertTrue(runner.validate(plan).valid)
        self.assertEqual(runner.explain(plan).plan_identity, plan.identity)

    def test_batch_parameter_and_combination_errors_precede_output(self):
        """参数: 无。返回: 无。异常: 参数拒绝错误或进入输出创建时断言失败。"""
        path = ROOT/'Docs/Current/examples/fast/batch.yaml'
        prepared = prepare_batch(path)
        # 避免重读配置，并明确截断所有输出创建；各失败必须先发生。
        with patch('chronaxis.fast.batch.prepare_batch', return_value=prepared), patch(
                'chronaxis.batch.runner._new_root', side_effect=AssertionError('不得创建输出')):
            for keywords, kind in (({'total': 1}, TypeError), ({'process_count': 0}, ValueError),
                                   ({'process_count': True}, ValueError), ({'cancel_event': object()}, TypeError)):
                with self.subTest(keywords=keywords), self.assertRaises(kind):
                    run_batch(path, 'not-created', **keywords)
            # 同一批合法规格只更换为jobs政策，即可验证total组合检查，不启动进程。
            with patch('chronaxis.fast.batch.prepare_batch', return_value=(*prepared[:2], False)):
                with self.assertRaisesRegex(ValueError, '仅支持同一分析模板'):
                    run_batch(path, 'not-created', total=True)
        self.assertIsInstance(FastTotals.from_specs(prepared[1], template=True), FastTotals)

    def test_catalog_and_rendered_types_have_no_placeholders(self):
        """参数: 无。返回: 无。异常: 反射清单与实际维护类型不一致时断言失败。"""
        previous = json.loads((ROOT/'Docs/Current/public-api.json').read_text(encoding='utf8'))
        rows = {row['name']: row for row in collect(ROOT/'src', previous)}
        for name, types in PARAMETER_TYPES.items():
            item = rows[name]
            actual = {parameter['name']: parameter['type'] for parameter in item['parameters']}
            self.assertEqual(actual, types)
            for language in ('zh', 'en'):
                rendered = render_note(item, '', language)
                self.assertNotIn('见用途', rendered)
                self.assertNotIn('See purpose', rendered)
                for value in types.values():
                    self.assertIn(value.replace('|', '&#124;'), rendered)

    def test_missing_reviewed_type_fails_instead_of_publishing_placeholder(self):
        """参数: 无。返回: 无。异常: 已维护公开页缺类型仍成功生成时断言失败。"""
        data = json.loads((ROOT/'Docs/Current/public-api.json').read_text(encoding='utf8'))
        item = deepcopy(next(row for row in data['objects'] if row['name'] == 'fast.batch.run_batch'))
        item['parameters'][0]['type'] = ''
        with patch.dict(PARAMETER_TYPES, {'fast.batch.run_batch': {}}):
            with self.assertRaisesRegex(ValueError, '公开API参数缺少已核对类型'):
                render_note(item, '', 'en')

    def test_english_runner_diagnostics_and_returns_are_guarded(self):
        """参数: 无。返回: 无。异常: 旧后端诊断或属性返回漏auto未被拦截时失败。"""
        notes = json.loads((ROOT/'Docs/Current/annotations.json').read_text(encoding='utf8'))
        page = (ROOT/'Docs/Current/en/public-api/AnalysisRunner.md').read_text(encoding='utf8')
        targets = dict(sections(page)[1])
        original = notes['chronaxis.runner.AnalysisRunner.__init__']['异常']
        check_runner_contract('api-AnalysisRunner-__init__', original, targets['api-AnalysisRunner-__init__'])
        with self.assertRaisesRegex(ValueError, 'diagnostic is stale'):
            check_runner_contract('api-AnalysisRunner-__init__', original,
                                  targets['api-AnalysisRunner-__init__'].replace('仅支持auto、', '仅支持'))
        source = (ROOT/'Docs/Current/public-api/AnalysisRunner.md').read_text(encoding='utf8')
        member = dict(sections(source)[1])['api-AnalysisRunner-backend']
        check_runner_contract('api-AnalysisRunner-backend', member, targets['api-AnalysisRunner-backend'])
        with self.assertRaisesRegex(ValueError, 'return choices are stale'):
            check_runner_contract('api-AnalysisRunner-backend', member,
                                  targets['api-AnalysisRunner-backend'].replace('None/auto/reference/numpy', 'None/reference/numpy'))
        # 更新后重新同步须幂等，不能在重复构建时复活旧错误或丢弃人工解释。
        first = synchronize_page(source, page, 'review')
        self.assertEqual(first, synchronize_page(source, first, 'review'))

    def test_runner_changes_only_docstrings(self):
        """参数: 无。返回: 无。异常: 与任务开始基线相比存在执行AST变化时失败。"""
        current = (ROOT/'src/chronaxis/runner.py').read_text(encoding='utf8')
        self.assertEqual(execution_ast_digest(current), RUNNER_EXECUTION_SHA256)
        # 算法必须对真实允许值变化敏感，不能因没有Git而跳过或仅检查文件存在。
        changed = current.replace("('reference', 'numpy', 'auto')", "('reference', 'numpy')")
        self.assertNotEqual(changed, current)
        self.assertNotEqual(execution_ast_digest(changed), RUNNER_EXECUTION_SHA256)


if __name__ == '__main__':
    unittest.main()
