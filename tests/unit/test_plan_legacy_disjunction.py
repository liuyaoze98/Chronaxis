"""静态核对可选正负分桶声明，不读取BLF/DBC或运行旧代码。

输入为当前消息计划的独立JSON变体，输出为冻结选择器或具体配置错误。
方向可不在公式中，仍必须有同来源/同消息的完整定位。标准schema和typed
替换分别检验结构与跨对象合同；这些结果不证明真实CAN运行已经通过。
"""

from configuration_fixtures import current_fixture

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, PlanValidationError, validate_analysis_plan, explain_analysis_plan
from chronaxis.legacy.disjunction import LegacyDisjunction
from test_plan_message_calculations import legacy_config


def bucket_config():
    """生成公式只用power、方向另用direction的声明。

    参数: 无。返回: 独立JSON字典。异常: 原测试夹具构造错误直接传播。
    """
    config = legacy_config()
    direction = deepcopy(config['signals'][0])
    direction.update(name='direction', dtype='float64', unit='1', conversion={'input_unit':'1'})
    direction['field']['signal'] = 'Direction.raw'
    config['signals'].append(direction)
    config['message_calculations'][0]['split_by_sign'] = dict(
        signal='direction', bucket='positive', value_policy='raw_decoded-v1')
    return config


class LegacyDisjunctionPlanningTests(unittest.TestCase):
    """将JSON结构、原始绑定、typed防绕过与静态无I/O分别核验。"""

    @classmethod
    def setUpClass(cls):
        """加载一次公开schema。参数: 无。返回: None。异常: 原文件/schema错误使测试失败。"""
        path = Path(__file__).absolute().parents[2] / 'Docs/Schema/analysis.schema.json'
        cls.validator = Draft202012Validator(json.loads(path.read_text(encoding='utf-8')))

    def test_separate_direction_static_reports_and_frozen_snapshot(self):
        """方向独立于expr，explain仍显示它，构建/报告不读取来源。

        参数: 无。返回: None。异常: 结构、依赖、冻结或静态I/O合同不符即失败。
        """
        config = bucket_config()
        self.assertTrue(self.validator.is_valid(config))
        with patch.object(Path, 'open', side_effect=AssertionError('不得读取输入')):
            plan = AnalysisPlan.from_dict(current_fixture(config))
            report, explanation = validate_analysis_plan(plan), explain_analysis_plan(plan)
        self.assertTrue(report.valid and report.execution_ready)
        self.assertEqual(report.capability_status['legacy_sum_disjunction'], 'implemented')
        self.assertEqual(plan.message_calculations[0].expr.dependencies, ('power',))
        self.assertEqual(explanation.nodes[0].dependencies, ('direction', 'power'))
        selection = plan.message_calculations[0].disjunction
        self.assertEqual(selection, LegacyDisjunction('direction', 'positive'))
        config['message_calculations'][0]['split_by_sign']['bucket'] = 'negative'
        self.assertEqual(selection.bucket, 'positive')
        with self.assertRaises(FrozenInstanceError):
            selection.bucket = 'negative'

    def test_exact_shape_policy_and_unknown_signal_rejected(self):
        """缺字段、自由条件、隐式null及未知别名均不能冒充分桶。

        参数: 无。返回: None。异常: 错误配置被接收或错误位置丢失即失败。
        """
        # 原值分桶只有一种策略，省略后必须与原完整声明相同。
        short = bucket_config()
        expected = AnalysisPlan.from_dict(current_fixture(short)).message_calculations[0].disjunction
        short['message_calculations'][0]['split_by_sign'].pop('value_policy')
        self.validator.validate(short)
        self.assertEqual(AnalysisPlan.from_dict(current_fixture(short)).message_calculations[0].disjunction, expected)
        for value in (None, {},
                {'signal':'direction','bucket':'zero','value_policy':'raw_decoded-v1'},
                {'signal':'direction','bucket':'positive','value_policy':'normalized'},
                {'signal':'direction','bucket':'positive','value_policy':'raw_decoded-v1','extra':1}):
            config = bucket_config()
            config['message_calculations'][0]['split_by_sign'] = value
            with self.subTest(value=value):
                self.assertFalse(self.validator.is_valid(config))
                with self.assertRaises(PlanValidationError) as caught:
                    AnalysisPlan.from_dict(current_fixture(config))
                self.assertIn('split_by_sign', caught.exception.path)
        config = bucket_config()
        config['message_calculations'][0]['split_by_sign']['signal'] = 'missing'
        with self.assertRaises(PlanValidationError) as caught:
            AnalysisPlan.from_dict(current_fixture(config))
        self.assertIn('split_by_sign.signal', caught.exception.path)

    def test_direction_full_message_locator_rejects_cross_message(self):
        """方向虽不在expr，仍拒跨来源、通道、ID、标志及同ID不同message。

        参数: 无。返回: None。异常: 单字段绕过完整定位校验即失败。
        """
        for key, value in (('channel',2), ('frame_id',257), ('is_extended',True),
                ('is_fd',True), ('message','OtherMessage')):
            config = bucket_config()
            config['signals'][1]['field'][key] = value
            with self.subTest(field=key), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(current_fixture(config))
        config = bucket_config()
        other = deepcopy(config['sources'][0])
        other['name'] = 'other'
        config['sources'].append(other)
        config['signals'][1]['source'] = 'other'
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(config))

    def test_raw_policy_allows_declared_transform_but_does_not_rewrite_it(self):
        """原值政策不删除用户普通信号转换，负倍率仍完整保存在普通声明中。

        参数: 无。返回: None。异常: 转换/原定位/分桶政策被隐式替换即失败。
        """
        config = bucket_config()
        config['signals'][1].update(scale=-1, unit='raw_direction')
        plan = AnalysisPlan.from_dict(current_fixture(config))
        self.assertEqual(plan.signals[1].definition.scale, -1)
        self.assertEqual(plan.message_calculations[0].disjunction.value_policy, 'raw_decoded-v1')

    def test_typed_replacement_cannot_bypass_direction_relationship(self):
        """替换typed选择器后validate重核定位，不仅信任原raw_config。

        参数: 无。返回: None。异常: 错误typed关系被报告可执行即失败。
        """
        config = bucket_config()
        extra = deepcopy(config['signals'][1])
        extra['name'] = 'other_direction'
        extra['field']['frame_id'] = 257
        config['signals'].append(extra)
        plan = AnalysisPlan.from_dict(current_fixture(config))
        bad_calculation = replace(plan.message_calculations[0],
            disjunction=LegacyDisjunction('other_direction', 'negative'))
        report = validate_analysis_plan(replace(plan, message_calculations=(bad_calculation,)))
        self.assertFalse(report.valid)
        self.assertFalse(report.execution_ready)

    def test_absent_disjunction_preserves_default_model_and_reports(self):
        """不启用分桶时不增加新能力项或依赖，旧默认仍为None。

        参数: 无。返回: None。异常: 未请求功能改变旧静态报告即失败。
        """
        plan = AnalysisPlan.from_dict(current_fixture(legacy_config()))
        self.assertIsNone(plan.message_calculations[0].disjunction)
        self.assertNotIn('legacy_sum_disjunction', validate_analysis_plan(plan).capability_status)
        self.assertEqual(explain_analysis_plan(plan).nodes[0].dependencies, ('power',))

    def test_boolean_direction_allowed_but_enum_direction_rejected(self):
        """bool沿原正负比较合同，enum标签不能冒充原数值方向。

        参数: 无。返回: None。异常: dtype范围被意外收紧或放宽即失败。
        """
        config = bucket_config()
        config['signals'][1]['dtype'] = 'bool'
        self.assertTrue(validate_analysis_plan(AnalysisPlan.from_dict(current_fixture(config))).valid)
        config['signals'][1].update(dtype='enum', choices=[[0,'off'],[1,'scope']])
        with self.assertRaises(PlanValidationError):
            AnalysisPlan.from_dict(current_fixture(config))
