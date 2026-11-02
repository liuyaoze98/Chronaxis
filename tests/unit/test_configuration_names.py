"""[home] 配置只接受name声明及rule窗口引用，拒绝旧拼写而非并存两套名称。

使用既有合成计划核对引用对象与不变的名称值；不读取报文或修改用户配置。
"""
from copy import deepcopy
import unittest

from chronaxis import AnalysisPlan, PlanValidationError
from chronaxis.batch.models import BatchPlan
from test_analysis_plan import config_fixture


class ConfigurationNamesTests(unittest.TestCase):
    """检查单一公开拼写、错误位置和名称冲突。"""

    def test_declarations_preserve_values_and_reject_id(self):
        """改字段名不能改用户选定的对象名；旧id须在准确路径拒绝。"""
        raw=config_fixture();original=deepcopy(raw);plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.dataset.dataset_id,raw['dataset']['name'])
        self.assertEqual([r.rule_id for r in plan.rules],[r['name'] for r in raw['rules']])
        self.assertEqual(raw,original)
        for section in ('dataset','rules','windows','calculations'):
            bad=deepcopy(raw)
            target=bad[section] if section=='dataset' else bad[section][0]
            target['id']=target.pop('name')
            with self.subTest(section=section),self.assertRaises(PlanValidationError) as caught:
                AnalysisPlan.from_dict(bad)
            self.assertEqual(caught.exception.code,'unknown_field')
            self.assertTrue(caught.exception.path.endswith('.id'))

    def test_window_rule_and_duplicate_name_checks(self):
        """窗口引用实际规则；旧event和不存在的rule分别报错，重复名称仍禁止。"""
        raw=config_fixture();window=raw['windows'][0]
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.windows[0].event,window['rule'])
        window['rule']='not_declared'
        with self.assertRaises(PlanValidationError) as caught:AnalysisPlan.from_dict(raw)
        self.assertEqual(caught.exception.path,'$.windows[0].rule')
        raw=config_fixture();window=raw['windows'][0];window['event']=window.pop('rule')
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(raw)
        raw=config_fixture();raw['rules'][1]['name']=raw['rules'][0]['name']
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(raw)

    def test_batch_name_is_configuration_name_not_file_path(self):
        """任务名不改变计划路径，不要求静态加载时子计划文件存在。"""
        plan=BatchPlan.from_dict(dict(batch_version=1,jobs=[dict(name='job_a',plan='missing.json')]))
        self.assertEqual(plan.jobs[0].job_id,'job_a')
        with self.assertRaises(PlanValidationError):
            BatchPlan.from_dict(dict(batch_version=1,jobs=[dict(id='job_a',plan='missing.json')]))
