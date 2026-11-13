"""核对 fast 只准备需要的公式，保留低层文字入口的全部拒绝边界。"""

from copy import deepcopy
import unittest
from unittest.mock import patch

from chronaxis.fast import compute
from chronaxis.fast.config import compile_config
from chronaxis.fast.run import run
from chronaxis.fast.session import SessionAccumulator, run_session
import test_fast_session as session_fixtures


class FastPreparationTests(unittest.TestCase):
    """使用两份合成 ASC；四条 400 J 贡献的真值为 1600 J。"""

    def setUp(self):
        """复用既有合成文件工厂；每个测试单独拥有并清理目录。"""
        self.fixture = session_fixtures.FastSessionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_accumulator_does_not_prepare_formula(self):
        """主累计器只接收贡献；禁止创建永远不会调用的求值闭包。"""
        spec = compile_config(self.fixture.config())
        with patch.object(compute, '_syntax', side_effect=AssertionError('重新解析')), \
             patch.object(compute, '_bind', side_effect=AssertionError('无用绑定')):
            total = SessionAccumulator(spec)
            for sequence in range(4):
                total.consume((sequence, sequence, ((0, 400.0, True),)))
            total.finish_file(dict(raw=4, targets=[4], valid=[4], selected=[4], kinds=[1], compatible=[]))
            rows, warnings = total.result()
        self.assertEqual(rows[0]['value'], 1600.0)
        self.assertEqual(rows[0]['status'], 'complete')
        self.assertEqual(warnings, [])

    def test_public_run_reuses_compiled_program(self):
        """公共编译后运行两文件不再解析公式；每帧仍独立求值。"""
        path = self.fixture.config()
        spec = compile_config(path, _with_database=True)
        with patch('chronaxis.fast.config.compile_config', return_value=spec), \
             patch.object(compute, '_syntax', side_effect=AssertionError('公共编译后再次解析')):
            manifest = run(path, self.fixture.folder / 'output')
        self.assertTrue(manifest.is_file())
        import json
        report = json.loads(manifest.read_bytes())
        rows = [json.loads(line) for line in
                (manifest.parent / report['outputs'][0]['name']).read_text().splitlines()]
        self.assertEqual(rows[0]['value'], 1600.0)

    def test_public_compile_uses_common_expression_only(self):
        """公共配置直接绑定通用编译树，不经过低层文本解释器。

        参数: 无。返回: None。异常: 重复解析或独立贡献真值不符时断言失败。
        """
        with patch.object(compute, '_syntax', side_effect=AssertionError('重复文本解析')):
            spec = compile_config(self.fixture.config())
            rows, _ = run_session(spec, _programs_checked=True)
        # 两份文件四条400J贡献；同时检验从真实配置编译到最终累计的完整路径。
        self.assertEqual(rows[0]['value'], 1600.0)
        self.assertEqual(rows[0]['status'], 'complete')

    def test_low_level_session_checks_once_and_keeps_source(self):
        """直接传字典仍检查一次文本，后续文件不重复；调用者声明不变。"""
        spec = compile_config(self.fixture.config())
        before = deepcopy(spec)
        with patch.object(compute, '_syntax', wraps=compute._syntax) as syntax:
            rows, _ = run_session(spec)
        self.assertEqual(syntax.call_count, len(spec['metrics']))
        self.assertEqual(rows[0]['value'], 1600.0)
        self.assertEqual(spec, before)

    def test_config_flag_cannot_bypass_low_level_text_check(self):
        """一个字典中的标志不能把非法原公式变成已检查的内部调用。"""
        spec = compile_config(self.fixture.config())
        spec['_programs_checked'] = True
        spec['metrics'][0]['expr'] = '__import__("os")'
        spec['metrics'][0]['program'] = dict(op='const', dtype='float64', value=0.0)
        with self.assertRaises(ValueError):
            run_session(spec)

    def test_internal_program_still_checks_shape_and_numeric_types(self):
        """省去原文本解析不会省去指令、信号类型和数值界限检查。"""
        item = compile_config(self.fixture.config())['metrics'][0]
        for program in (dict(op='lookup', dtype='float64', args=[]),
                        dict(op='const', dtype='float64', value=float('inf')),
                        dict(op='const', dtype='uint64', value=-1)):
            with self.subTest(program=program), self.assertRaises(ValueError):
                compute._prepare_program_metric(dict(item, program=program))

    def test_file_override_cannot_reuse_unrelated_preparation(self):
        """低层每文件覆盖的实际公式必须核验，不能借顶层合法公式绕过检查。"""
        spec = compile_config(self.fixture.config())
        forged = dict(spec['metrics'][0], expr='power[0]',
                      program=dict(op='const', dtype='float64', value=0.0))
        spec['inputs'][0]['metrics'] = [forged]
        for checked in (False, True):
            with self.subTest(top_level_checked=checked), self.assertRaises(ValueError):
                run_session(spec, _programs_checked=checked)

    def test_low_level_limits_still_apply_with_program(self):
        """合法指令不允许超长文本或超过 512 AST 节点的原式通过。"""
        item = compile_config(self.fixture.config())['metrics'][0]
        for expression in ('power' + ' ' * 4096, '+'.join(['1'] * 180)):
            with self.subTest(length=len(expression)), self.assertRaises(ValueError):
                compute.prepare_metric(dict(item, expr=expression))
