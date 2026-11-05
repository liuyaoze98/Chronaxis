"""验证多错误诊断、依赖隔离和单次DBC补全。

全部使用合成配置，文件放新项目work；不读真实日志，不改用户输入。
期望来自独立坏字段、明确缺失引用及原型的错误位置，不以错误总数代替语义检查。
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chronaxis.cli import main
from chronaxis.planning.plan import AnalysisPlan, load_analysis_plan
from chronaxis.planning.checks import PlanValidationError
from chronaxis.batch.models import BatchPlan


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'work' / 'next-ux-development-01' / 'diagnostic-tests'


def config():
    """读取已有小型内存教学配置。参数: 无。返回: 原生dict。异常: 测试资源缺失。"""
    return json.loads((ROOT / 'examples/analysis_plan.json').read_text(encoding='utf-8'))


class MultiDiagnosticTests(unittest.TestCase):
    """独立字段应同时报告，已知无效依赖只能阻断其消费者。"""

    def error(self, value):
        """捕获配置异常。参数: 配置。返回: PlanValidationError。异常: 误通过时断言失败。"""
        with self.assertRaises(PlanValidationError) as caught:
            AnalysisPlan.from_dict(value)
        return caught.exception

    def test_multiple_fields_in_same_and_separate_objects(self):
        """同一execution内四错及outputs两错全部出现，原字典保持。参数: 无。返回: None。异常: 断言失败。"""
        value = config()
        value['execution'] = {'backend':'gpu','batch_rows':0,'result_buffer_rows':False,'memory_budget_bytes':-1}
        value['outputs'] = {'tables':'xlsx','manifest':'yaml'}
        original = deepcopy(value)
        error = self.error(value)
        self.assertEqual({item.path for item in error.diagnostics}, {
            '$.execution.backend','$.execution.batch_rows','$.execution.result_buffer_rows',
            '$.execution.memory_budget_bytes','$.outputs.tables','$.outputs.manifest'})
        self.assertEqual(value, original)

    def test_bad_signal_blocks_only_consumers_and_retains_unrelated_rule_error(self):
        """坏电流不让报警信号产生假错，另一条未知引用仍被发现。参数: 无。返回: None。异常: 断言失败。"""
        value = config()
        value['signals'][0]['valid_for'] = '-1s'
        value['rules'].append({'name':'independent_bad','rule_type':'condition_duration',
                              'condition':'missing > 0','minimum_duration':'1s'})
        error = self.error(value)
        self.assertEqual({item.path for item in error.diagnostics},
                         {'$.signals[0].valid_for','$.rules[3].condition'})
        self.assertTrue(any(item['path']=='$.rules[0].condition' for item in error.blocked_checks))
        self.assertFalse(any(item['path'].startswith('$.rules[1]') for item in error.blocked_checks))

    def test_independent_semantic_errors(self):
        """两个合法结构的规则分别引用未知信号，均有原数组位置。参数: 无。返回: None。异常: 断言失败。"""
        value = config()
        value['rules'][0]['condition'] = 'not_here > 1'
        value['rules'][1]['condition'] = 'absent == 1'
        error = self.error(value)
        self.assertIn('$.rules[0].condition', [item.path for item in error.diagnostics])
        self.assertIn('$.rules[1].condition', [item.path for item in error.diagnostics])

    def test_cli_json_and_source_locations(self):
        """CLI只输出errors数组，逐项带不同真实行列，有错时不启动计算。参数: 无。返回: None。异常: 断言失败。"""
        WORK.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            path = Path(folder) / 'bad.yaml'
            from ruamel.yaml import YAML
            value = config(); value['execution'] = {'backend':'gpu','batch_rows':0}
            value['outputs'] = {'tables':'xlsx'}
            with path.open('w',encoding='utf-8') as handle:
                YAML().dump(value,handle)
            stdout = io.StringIO()
            with patch('chronaxis.runner.AnalysisRunner.run', side_effect=AssertionError('不得分析')), redirect_stdout(stdout):
                status = main(['validate',str(path),'--format','json'])
            payload = json.loads(stdout.getvalue())
            self.assertEqual(status,2)
            self.assertNotIn('error',payload)
            self.assertEqual(len(payload['errors']),3)
            self.assertEqual(len({item['line'] for item in payload['errors']}),3)
            self.assertTrue(all(item['source']==str(path) for item in payload['errors']))

    def test_syntax_failure_is_one_diagnostic(self):
        """无法解析的YAML保留语法位置，不补猜配置。参数: 无。返回: None。异常: 断言失败。"""
        WORK.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            path=Path(folder)/'syntax.yaml';path.write_text('dataset: "unterminated',encoding='utf-8')
            with self.assertRaises(PlanValidationError) as caught:
                load_analysis_plan(path)
            self.assertEqual(len(caught.exception.diagnostics),1)
            self.assertEqual(caught.exception.code,'invalid_yaml')

    def test_batch_own_fields_accumulate_without_loading_jobs(self):
        """错误批量设置一次列出，显式子计划路径仍保持延迟加载。参数: 无。返回: None。异常: 断言失败。"""
        with self.assertRaises(PlanValidationError) as caught:
            BatchPlan.from_dict({'batch_version':1,'jobs':[{'plan':'does-not-exist.yaml'}],
                                 'process_count':0,'backend':'gpu','fail_fast':'yes'})
        self.assertEqual({item.path for item in caught.exception.diagnostics},
                         {'$.process_count','$.backend','$.fail_fast'})

    def test_valid_plan_and_context_cleanup(self):
        """错误后的合法构建不继承旧诊断或失败名称，值与默认值保持。参数: 无。返回: None。异常: 断言失败。"""
        bad=config();bad['execution']={'backend':'gpu'};self.error(bad)
        plan=AnalysisPlan.from_dict(config())
        self.assertEqual(plan.execution.backend,'numpy')
        self.assertEqual(len(plan.signals),3)
        self.assertEqual(plan.derived_expressions[0].root.unit,'W')

    def test_dbc_dependency_failure_and_unrelated_fields(self):
        """同一DBC只尝试加载一次，缺失与无关输出错误一起报告，其余信号标阻断。参数: 无。返回: None。异常: 断言失败。"""
        from ruamel.yaml import YAML
        example=ROOT/'Docs/Current/examples/conditional-energy.yaml'
        value=YAML(typ='safe',pure=True).load(example.read_text(encoding='utf-8'))
        value['outputs']={'tables':'xlsx'}
        with patch('cantools.database.load_file',side_effect=FileNotFoundError('missing.dbc')) as loader:
            with self.assertRaises(PlanValidationError) as caught:
                AnalysisPlan.from_dict(value,base_dir=example.parent)
        self.assertEqual(loader.call_count,1)
        self.assertEqual({item.path for item in caught.exception.diagnostics},
                         {'$.outputs.tables','$.signals[0]'})
        self.assertTrue(any(item['path']=='$.signals[1]' for item in caught.exception.blocked_checks))

    def test_imported_definition_keeps_original_file_location(self):
        """主文件和导入信号文件的独立错误各指向自己的文件，未改写配置。参数: 无。返回: None。异常: 断言失败。"""
        from ruamel.yaml import YAML
        WORK.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            root=Path(folder);shared=root/'signals.yaml';path=root/'plan.yaml'
            value=config();definitions={'signals':value.pop('signals')}
            definitions['signals'][0]['valid_for']='-1s'
            value['imports']=['signals.yaml'];value['execution']={'backend':'gpu'}
            for target,content in ((shared,definitions),(path,value)):
                with target.open('w',encoding='utf-8') as handle:YAML().dump(content,handle)
            with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(path)
            sources={item.source for item in caught.exception.diagnostics}
            self.assertEqual(sources,{str(path),str(shared)})

    def test_rule_name_does_not_hide_signal_in_other_namespace(self):
        """规则名可与信号名相同，坏规则不能阻断另一合法信号表达式。参数: 无。返回: None。异常: 断言失败。"""
        value=config()
        value['rules'][0]['name']='current'
        value['rules'][0]['condition']='absent > 1'
        value['rules'][1]['condition']='current > 1'
        error=self.error(value)
        self.assertIn('$.rules[0].condition',[item.path for item in error.diagnostics])
        self.assertFalse(any(item['path'].startswith('$.rules[1]') for item in error.blocked_checks))
        self.assertFalse(any(item.path.startswith('$.rules[1]') for item in error.diagnostics))

    def test_duplicate_jobs_and_bad_scheduler_both_reported(self):
        """重复任务名不被无关调度设置错误遮蔽；不读取不存在的子计划。参数: 无。返回: None。异常: 断言失败。"""
        with self.assertRaises(PlanValidationError) as caught:
            BatchPlan.from_dict({'batch_version':1,'process_count':0,'jobs':[
                {'name':'same','plan':'missing.json'},{'name':'SAME','plan':'other.json'}]})
        self.assertEqual({item.path for item in caught.exception.diagnostics},
                         {'$.process_count','$.jobs[1].name'})


if __name__ == '__main__':
    unittest.main()
