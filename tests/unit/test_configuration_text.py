"""真实CLI默认说明与显式机器报告；验证叙述依据及无数据读取，不用快照自证正确。"""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ruamel.yaml import YAML
from chronaxis import load_analysis_plan,AnalysisRunner
from chronaxis.analysis_cli import run_static
from chronaxis.configuration.explanation import explanation_text,time_text
from test_analysis_plan import config_fixture
from test_cli_static import static_configuration
from test_plan_message_calculations import legacy_config

ROOT=Path(__file__).resolve().parents[2]


class ConfigurationTextTests(unittest.TestCase):
    """独立work内保存配置，公开模块命令从不同cwd执行。"""

    def setUp(self):
        """保存有单位/规则/计算的合成YAML。参数: 无。返回: None。异常: IO。"""
        self.root=Path(tempfile.mkdtemp(prefix='configuration-text-',dir='work')).resolve()
        self.path=self.root/'plan.yaml'
        self.write(config_fixture())

    def write(self,data):
        """写独立YAML夹具。参数: 原生配置。返回: None。异常: 格式/IO。"""
        yaml=YAML(typ='safe',pure=True)
        with self.path.open('w',encoding='utf-8') as handle:
            yaml.dump(data,handle)

    def command(self,*arguments):
        """实际-m运行。参数: CLI参数。返回: CompletedProcess。异常: IO/超时。"""
        return subprocess.run([sys.executable,'-B','-m','chronaxis',*map(str,arguments)],cwd=self.root,
            env=os.environ.copy(),capture_output=True,text=True,encoding='utf-8',timeout=60)

    def test_default_cli_explains_inputs_semantics_defaults_and_override(self):
        """普通人读入口直接说明有效期/统计口径和未核实项。参数: 无。返回: None。异常: 断言。"""
        config=config_fixture()
        config['outputs']={'tables':'jsonl'}
        config['calculations'].append(dict(name='average',operation='sample_mean',scope='session',expr='current'))
        self.write(config)
        completed=self.command('explain',self.path,'--backend','reference')
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(completed.stderr,'')
        for text in ('current ← table.raw.current','有效期 valid_for=2s','至少持续 1s',
                     '每个事件 active','每个窗口片段 activity_context','每个有效样本权重相同',
                     '按有效持续时间加权','结果表格式=jsonl（配置指定）',
                     '执行后端=reference（命令行覆盖）','详细追溯=关闭（默认）',
                     '尚未读取日志','缺口不补零','固定间隔或DBC周期不延长信号有效期'):
            self.assertIn(text,completed.stdout)
        self.assertFalse(completed.stdout.startswith('{'))
        checked=self.command('validate',self.path)
        self.assertEqual(checked.returncode,0,checked.stderr)
        self.assertIn('静态检查通过',checked.stdout)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['plan.yaml'])

    def test_json_success_and_error_have_explicit_machine_contract(self):
        """JSON成功报告沿公共字段，错误包含来源字段/行列/修正，退出仍2或1。参数: 无。返回: None。异常: 断言。"""
        valid=self.command('validate',self.path,'--format','json')
        self.assertEqual(valid.returncode,0,valid.stderr)
        self.assertTrue(json.loads(valid.stdout)['execution_ready'])
        config=config_fixture();config['signals'][0]['valid_for']='0ns';self.write(config)
        bad=self.command('validate',self.path,'--format','json')
        self.assertEqual(bad.returncode,2,bad.stderr)
        self.assertEqual(bad.stderr,'')
        diagnostic=json.loads(bad.stdout)
        self.assertFalse(diagnostic['valid'])
        error=diagnostic['errors'][0]
        self.assertEqual((error['code'],error['path'],error['object_name']),
            ('invalid_duration','$.signals[0].valid_for','信号 current'))
        self.assertEqual(error['source'],str(self.path))
        self.assertGreater(error['line'],0);self.assertGreater(error['column'],0)
        self.assertIn('1s',error['hint'])
        human=self.command('validate',self.path)
        self.assertEqual(human.returncode,2)
        self.assertEqual(human.stdout,'');self.assertIn('信号 current',human.stderr)
        missing=self.command('explain',self.root/'missing.yml','--format','json')
        self.assertEqual(missing.returncode,1)
        self.assertEqual(json.loads(missing.stdout)['errors'][0]['code'],'load_error')

    def test_text_static_path_never_opens_declared_csv_or_creates_output(self):
        """默认文本和机器报告共同保持静态边界；实际打开只允许配置。参数: 无。返回: None。异常: 断言。"""
        self.write(static_configuration())
        original=Path.open;opened=[]
        def only_configuration(path,*args,**kwargs):
            """观察真实FD打开。参数: 路径/参数。返回: FD。异常: 非配置I/O断言。"""
            self.assertEqual(path,self.path);opened.append(path)
            return original(path,*args,**kwargs)
        for command in ('validate','explain'):
            output=io.StringIO()
            args=SimpleNamespace(plan=self.path,command=command,backend=None,format='text')
            with patch.object(Path,'open',only_configuration),redirect_stdout(output),\
                 patch.object(AnalysisRunner,'run',side_effect=AssertionError('静态不得运行')):
                self.assertEqual(run_static(args),0)
            self.assertIn('尚未读取日志',output.getvalue())
        self.assertEqual(opened,[self.path,self.path])

    def test_current_scenarios_and_message_accumulation_explain_real_fields(self):
        """九个已存在场景和逐消息计划均可说明，开始结束初始开关从真实规格读取。参数: 无。返回: None。异常: 断言。"""
        names=('analysis_plan.json','command_response_plan.json','presets_plan.json','stability_plan.json',
            'start_end_plan.json','threshold_excursion_plan.json','window_delta_plan.json',
            'm3_text_input/asc-plan.json','m3_text_input/csv-plan.json')
        for name in names:
            with self.subTest(name=name):
                plan=load_analysis_plan(ROOT/'examples'/name)
                with patch.object(Path,'open',side_effect=AssertionError('说明不能读文件')):
                    text=explanation_text(plan,AnalysisRunner().explain(plan))
                self.assertIn(plan.dataset.dataset_id,text)
                self.assertIn('静态检查通过',text)
                for source in plan.sources:self.assertIn(source.name,text)
                for rule in plan.rules:
                    if rule.start_end is not None:
                        line=next(line for line in text.splitlines() if line.startswith('  '+rule.rule_id+'：'))
                        self.assertIn('首次已知条件触发='+('开启' if rule.start_end.emit_initial else '关闭'),line)
        from chronaxis import AnalysisPlan
        plan=AnalysisPlan.from_dict(legacy_config())
        text=explanation_text(plan,AnalysisRunner().explain(plan))
        self.assertIn('逐消息累计',text)
        self.assertIn('不额外乘时间间隔',text)
        self.assertEqual(time_text(1000000001),'1000000001ns')
        self.assertEqual(time_text(-1500000),'-1500us')


if __name__=='__main__':
    unittest.main()
