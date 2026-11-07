"""核单会话读取进程配置、API覆盖与文件归并的静态边界。

使用不存在的输入文件及完整显式绑定；校验不应扫描输入。运行支持由专项
数据测试另行证明，本模块只验证声明、严格类型及不修改原计划的覆盖规则。
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.cli import _parser


def config():
    """提供不用读取DBC补全的完整声明。参数: 无。返回: dict。异常: 无。
    """
    return dict(config_version=4, dataset=dict(name='single_session'),
        sources=[dict(name='bus',source_type='can_blf',paths=['missing_1.blf','missing_2.blf'],
                      dbc_by_channel={'1':'missing.dbc'})],
        signals=[dict(name='power',source='bus',field=dict(channel=1,frame_id=256,signal='Power',
            is_extended=False,is_fd=False),dtype='float64',unit='W',
            conversion=dict(input_unit='W'),valid_for='1s')],
        calculations=[dict(name='energy',operation='integral',expr='power',unit='J')])


class SessionProcessConfigTests(unittest.TestCase):
    """同一配置与调用覆盖只改变执行选项，不能默默改变文件组织。
    """

    def test_defaults_and_valid_integer(self):
        """默认串行且拼接；显式八进程保原文件顺序。参数: 无。返回: None。异常: 断言。
        """
        raw=config()
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.execution.process_count,1)
        self.assertEqual(plan.sources[0].config.file_merge,'concatenate')
        raw['execution']=dict(process_count=8)
        raw['sources'][0]['file_merge']='time_order'
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.execution.process_count,8)
        self.assertEqual(plan.sources[0].config.file_merge,'time_order')

    def test_invalid_config_values(self):
        """布尔、空值、小数、文本和非正整数逐项拒绝。参数: 无。返回: None。异常: 断言。
        """
        for value in (None,True,False,0,-1,1.5,'4'):
            with self.subTest(value=value):
                raw=config();raw['execution']=dict(process_count=value)
                with self.assertRaises(ValueError):
                    AnalysisPlan.from_dict(raw)
        for value in (None,'sort',True,1):
            with self.subTest(merge=value):
                raw=config();raw['sources'][0]['file_merge']=value
                with self.assertRaises(ValueError):
                    AnalysisPlan.from_dict(raw)

    def test_api_override_preserves_plan_and_merge(self):
        """API显式覆盖优先，None沿配置，原对象和归并选择不变。参数: 无。返回: None。异常: 断言。
        """
        raw=config();raw['execution']=dict(process_count=2)
        saved=deepcopy(raw)
        plan=AnalysisPlan.from_dict(raw)
        runner=AnalysisRunner()
        self.assertEqual(runner.explain(plan).budget['process_count'],2)
        self.assertEqual(runner.explain(plan,process_count=4).budget['process_count'],4)
        facts=runner.explain(plan,process_count=4).source_execution[0]
        self.assertEqual(facts['file_count'],2)
        self.assertEqual(facts['read_process_limit'],2)
        self.assertEqual(facts['file_merge'],'concatenate')
        self.assertEqual(plan.execution.process_count,2)
        self.assertEqual(plan.sources[0].config.file_merge,'concatenate')
        self.assertEqual(raw,saved)
        # 1进程覆盖恢复原串行支持范围，不被配置中的2进程残留限制。
        self.assertTrue(runner.validate(plan,process_count=1).execution_ready)
        for value in (True,False,0,-3,2.5,'4'):
            for method in (runner.validate,runner.explain,runner.run):
                with self.subTest(method=method.__name__,value=value):
                    with self.assertRaises(ValueError):
                        method(plan,process_count=value)

    def test_cli_all_ordinary_commands_accept_override(self):
        """普通三个入口使用同名参数；独立批量保持独立。参数: 无。返回: None。异常: 断言。
        """
        for command in ('validate','explain','run'):
            arguments=[command,'missing.yaml','--process-count','4']
            if command=='run':
                arguments+=['--output','not_created']
            self.assertEqual(_parser().parse_args(arguments).process_count,4)

    def test_typed_invalid_process_is_reported(self):
        """手工替换typed声明同样不能绕过真实类型检查。参数: 无。返回: None。异常: 断言。
        """
        plan=AnalysisPlan.from_dict(config())
        bad=replace(plan,execution=replace(plan.execution,process_count=True))
        self.assertFalse(AnalysisRunner().validate(bad).execution_ready)

    def test_independent_batch_cannot_nest_reading_pool(self):
        """批量worker内在读取前拒绝第二层文件进程池。参数: 无。返回: None。异常: 断言。
        """
        raw=config();raw['execution']=dict(process_count=2)
        plan=AnalysisPlan.from_dict(raw)
        with patch('chronaxis.planning.process_execution.IN_BATCH_WORKER',True):
            report=AnalysisRunner().validate(plan)
            self.assertFalse(report.execution_ready)
            self.assertTrue(any('独立批量' in error for error in report.errors))


if __name__=='__main__':
    unittest.main()
