"""核对缺失判别字段只报告根因，合法操作仍执行原有字段组合校验。

使用合成内存配置，不读取报文；结果来自明确的字段依赖和公开计划构建接口。
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, PlanValidationError
from chronaxis.core.types import SignalDType
from chronaxis.extensions import ExtensionRegistry, ReductionSpec, TransformSpec, ValueSpec
from chronaxis.planning.diagnostic_collection import DiagnosticCollection, schema_validator


def configuration():
    """返回独立的三条电压样本配置；无文件输入和自动默认比较符。

    参数: 无。返回: 原生配置字典。异常: 无。
    """
    return dict(config_version=4, dataset=dict(name='diagnostics', domain=dict(start='0s', end='2s')),
                sources=[dict(name='table', source_type='memory', rows=[
                    dict(time=f'{index}s', values=dict(voltage=float(index))) for index in range(3)])],
                signals=[dict(name='voltage', field='voltage', dtype='float64', unit='V', valid_for='3s')],
                calculations=[dict(name='mean', operation='sample_mean', expr='voltage', unit='V')])


def forbidden_factory(resources):
    """校验阶段不得创建宿主状态；若调用，立即让测试失败。

    参数: 本次资源对象。返回: 不返回。异常: AssertionError。
    """
    raise AssertionError('配置校验不得执行宿主回调')


class RootDiagnosticTests(unittest.TestCase):
    """检查根因定位、独立错误保留及合法内置和宿主操作。"""

    def diagnostics(self, config, **kwargs):
        """构建失败时返回结构化诊断；意外通过直接失败。

        参数: 配置及构建选项。返回: 诊断元组。异常: 意外通过时断言失败。
        """
        with self.assertRaises(PlanValidationError) as caught:
            AnalysisPlan.from_dict(config, **kwargs)
        return caught.exception.diagnostics

    def test_missing_operation_removes_original_five_and_six_error_cascades(self):
        """缺操作时，expr、rule、window、q和结果单位不被错分支误判。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        for include_unit in (False, True):
            value = configuration()
            del value['calculations'][0]['operation']
            if not include_unit:
                del value['calculations'][0]['unit']
            before = deepcopy(value)
            with self.subTest(unit=include_unit):
                errors = self.diagnostics(value)
                self.assertEqual([(item.path, item.code) for item in errors],
                                 [('$.calculations[0].operation', 'missing_field')])
                self.assertEqual(value, before)

    def test_missing_operation_skips_entire_conditional_including_else(self):
        """补齐if的required不能让else误禁method、q、ddof等尚无法判断的字段。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        value = configuration()
        item = value['calculations'][0]
        del item['operation']
        item.update(method='zoh', q=.5, ddof=1, rule='alarm', window='span')
        errors = self.diagnostics(value)
        self.assertEqual([item.path for item in errors], ['$.calculations[0].operation'])

    def test_invalid_operation_has_only_its_own_choice_error(self):
        """非法操作名不能触发其他内置操作的必填项或互斥项。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        for operation in ('unknown_operation', None, 8, []):
            value = configuration()
            value['calculations'][0].update(operation=operation, method='zoh', q=.5, rule='alarm')
            with self.subTest(operation=operation):
                errors = self.diagnostics(value)
                self.assertEqual([(item.path, item.code) for item in errors],
                                 [('$.calculations[0].operation', 'invalid_choice')])

    def test_root_precedes_independent_errors_without_hiding_them(self):
        """操作根因先显示，同一对象坏expr及另一执行选项仍一次列出。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        value = configuration()
        value['calculations'][0] = dict(name='mean', expr=42, unit='V')
        value['execution'] = dict(backend='gpu')
        errors = self.diagnostics(value)
        self.assertEqual(errors[0].path, '$.calculations[0].operation')
        self.assertEqual({item.path for item in errors},
                         {'$.calculations[0].operation', '$.calculations[0].expr', '$.execution.backend'})

    def test_typo_recommendation_still_precedes_its_missing_field(self):
        """operation拼错时先指出原键和修正建议，不覆盖原字典。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        value = configuration()
        item = value['calculations'][0]
        item['operaton'] = item.pop('operation')
        errors = self.diagnostics(value)
        self.assertEqual(errors[0].path, '$.calculations[0].operaton')
        self.assertIn('operation', errors[0].hint)
        self.assertEqual(errors[1].path, '$.calculations[0].operation')

    def test_aggregation_discriminators_do_not_invent_dependent_errors(self):
        """聚合操作或来源缺失/非法时不伪报q、field或分组限制。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        for operation in (None, 'unknown_operation'):
            value = configuration()
            item = dict(name='summary', source={'calculation': 'mean'}, field='value', unit='V', q=.5, ddof=1)
            if operation is not None:
                item['operation'] = operation
            value['aggregations'] = [item]
            with self.subTest(operation=operation):
                self.assertEqual([error.path for error in self.diagnostics(value)], ['$.aggregations[0].operation'])
        for source in (None, {}, {'unknown': 'mean'}):
            value = configuration()
            item = dict(name='summary', operation='sum', field='value', group_by=['calculation_id'])
            if source is not None:
                item['source'] = source
            value['aggregations'] = [item]
            with self.subTest(source=source):
                self.assertTrue(all(error.path.startswith('$.aggregations[0].source')
                                    for error in self.diagnostics(value)))

    def test_transforms_keep_independent_fields_without_operation(self):
        """缺操作不触发相邻变化率分支；无关坏步长仍定位自身。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        value = configuration()
        value['transforms'] = [dict(name='rolling', expr='voltage', window='1s', step='bad')]
        self.assertEqual({error.path for error in self.diagnostics(value)},
                         {'$.transforms[0].operation', '$.transforms[0].step'})

    def test_valid_builtin_counts_quantiles_and_aggregations(self):
        """有效判别字段仍支持样本/事件/片段计数、分位和结果聚合。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        value = configuration()
        value['rules'] = [dict(name='active', rule_type='condition_duration', condition='voltage > 0',
                               minimum_duration='0.1s', duration_comparison='>='),
                          dict(name='rise', rule_type='rising_edge', condition='voltage > 0')]
        value['windows'] = [dict(name='span', rule='active')]
        value['calculations'] += [dict(name='samples', operation='sample_count', expr='voltage'),
                                  dict(name='points', operation='point_event_count', rule='rise'),
                                  dict(name='activities', operation='activity_count', rule='active'),
                                  dict(name='segments', operation='segment_count', window='span'),
                                  dict(name='p95', operation='sample_quantile', expr='voltage', q=.95)]
        value['aggregations'] = [dict(name='total', operation='sum', source={'calculation': 'mean'}),
                                 dict(name='p50', operation='quantile', source={'calculation': 'mean'}, q=.5)]
        plan = AnalysisPlan.from_dict(value)
        self.assertEqual(len(plan.calculations), 6)
        self.assertEqual(len(plan.aggregations), 2)

    def test_true_illegal_combinations_still_fail_with_chinese_messages(self):
        """已知操作的不适用字段必须拒绝；not约束不泄漏底层英文。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        for update, suffix in ((dict(q=.5), '.q'), (dict(method='zoh'), '.method'),
                               (dict(operation='point_event_count', rule='rise'), '.expr')):
            value = configuration()
            value['calculations'][0].update(update)
            errors = self.diagnostics(value)
            with self.subTest(update=update):
                match = next(error for error in errors if error.path.endswith(suffix))
                self.assertIn('不能填写', match.message)
                self.assertNotIn('should not', match.message)
        value = configuration()
        value['calculations'][0]['operation'] = 'sample_quantile'
        self.assertEqual(self.diagnostics(value)[0].path, '$.calculations[0].q')

    def test_host_operations_use_guarded_schema_without_changing_shared_validator(self):
        """自定义操作从当前注册读取合法名称，并保留表达式等公共约束。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        port = ValueSpec(SignalDType.FLOAT64, 'V')
        registry = ExtensionRegistry(
            reductions=(ReductionSpec('host_sum', 'v1', port, port, forbidden_factory, forbidden_factory),),
            transforms=(TransformSpec('host_grid', 'v1', port, port, forbidden_factory,
                                      forbidden_factory, history_ns=10**9),))
        value = configuration()
        value['calculations'][0]['operation'] = 'host_sum'
        value['transforms'] = [dict(name='grid', operation='host_grid', expr='voltage', window='1s', step='1s')]
        AnalysisPlan.from_dict(value, extensions=registry)
        value['calculations'][0]['q'] = .5
        errors = self.diagnostics(value, extensions=registry)
        self.assertEqual([error.path for error in errors], ['$.calculations[0].q'])
        del value['calculations'][0]['q']
        del value['calculations'][0]['expr']
        self.assertEqual(self.diagnostics(value, extensions=registry)[0].path, '$.calculations[0].expr')
        self.assertNotIn('host_sum', schema_validator('analysis.schema.json').schema[
            'properties']['calculations']['items']['properties']['operation']['enum'])

    def test_unhandled_schema_keyword_uses_safe_project_message(self):
        """通用兜底不输出jsonschema的英文，即使遇到新的约束类型。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        validator = Draft202012Validator({'type': 'object', 'minProperties': 2})
        with patch('chronaxis.planning.diagnostic_collection.schema_validator', return_value=validator):
            errors = DiagnosticCollection({}).errors
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].message, '值或字段组合不符合当前配置要求')
        self.assertNotIn('properties', errors[0].message)

    def test_duration_comparison_is_required_only_for_duration_rule(self):
        """持续门槛明确选择达到/超过；边沿不凭空要求比较符。

        参数: 无。返回: None。异常: 行为不符合预期时断言失败。
        """
        value = configuration()
        value['rules'] = [dict(name='active', rule_type='condition_duration', condition='voltage > 0',
                              minimum_duration='1s')]
        self.assertEqual(self.diagnostics(value)[0].path, '$.rules[0].duration_comparison')
        for comparison in ('>=', '>'):
            value['rules'][0]['duration_comparison'] = comparison
            AnalysisPlan.from_dict(value)
        value['rules'] = [dict(name='rise', rule_type='rising_edge', condition='voltage > 0')]
        AnalysisPlan.from_dict(value)


if __name__ == '__main__':
    unittest.main()
