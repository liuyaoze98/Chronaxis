"""对照未改的公开CANSourceRef，核内部固定定位复用的字段、字节及错误边界。

全部输入由本文件构造，不读CAN/DBC/磁盘。原公开构造器是独立行为参考；测试保留
负零、Unicode/转义、超大合法原序及错误优先级，证明只省固定字段重复校验。
运行接线的实际数据/取消/预算由既有AnalysisRunner专项和真实验收另核。
"""

from configuration_fixtures import current_fixture

from dataclasses import FrozenInstanceError
import json
import math
import unittest
from unittest.mock import patch

from chronaxis.execution.can_reference_template import CANReferenceTemplate
from chronaxis.legacy.records import LegacyCANField, PROFILE_ID
from chronaxis.sources.can_spec import CANSourceRef
from chronaxis.results.codec import _pack


def constants(**changes):
    """生成一组同源固定字段。参数: 覆盖字段。返回: 关键字dict。异常: 原模型错误。"""
    field = LegacyCANField(0, '功率\\原值', 428, False, False)
    result = dict(session_id='session', source_name='bus', field=field.key, path='输入/数据.blf',
        profile=PROFILE_ID, channel=field.channel,  signal=field.signal,
        frame_id=field.frame_id, is_extended=field.is_extended, is_fd=field.is_fd)
    result.update(changes)
    return result


def outcome(function):
    """保存独立调用的拒绝类型及原文本。参数: 无参调用。返回: 二元组。异常: 未拒绝时报断言错误。"""
    try:
        function()
    except (TypeError, ValueError) as exc:
        return type(exc), str(exc)
    raise AssertionError('预期输入被拒绝')


class CANReferenceTemplateTests(unittest.TestCase):
    """模板只含常量，每条仍输出独立冻结公开引用。"""

    def test_fields_bytes_and_float_bits_match_public_constructor(self):
        """多种原时间/序号与公开模型逐字段和规范结果编码相同。参数: 无。返回: None。异常: 断言失败。"""
        fixed = constants()
        template = CANReferenceTemplate(**fixed)
        for sequence in (0, 1, 2**80):
            for timestamp in (-0.0, 0.0, -1.5, 5e-324, 1.7976931348623157e308):
                for quantized in (False, True):
                    actual = template.at(sequence, timestamp, quantized)
                    expected = CANSourceRef(**fixed, yield_sequence=sequence,
                        timestamp=timestamp, time_quantized=quantized)
                    self.assertIs(type(actual), CANSourceRef)
                    self.assertEqual(actual.__dict__, expected.__dict__)
                    self.assertEqual(actual.timestamp.hex(), expected.timestamp.hex())
                    self.assertEqual(json.dumps(current_fixture(_pack(actual)), ensure_ascii=False, sort_keys=True),
                                     json.dumps(current_fixture(_pack(expected)), ensure_ascii=False, sort_keys=True))

    def test_dynamic_errors_and_priority_match_public_constructor(self):
        """坏动态值和同时多错保公开错误类型/文本/先后。参数: 无。返回: None。异常: 断言失败。"""
        fixed = constants()
        template = CANReferenceTemplate(**fixed)
        for sequence, timestamp, quantized in ((True, math.nan, 1), (-1, math.inf, 0),
                (0, 0, True), (0, math.inf, False), (0, math.nan, True),
                (0, -math.inf, False), (0, 1.0, 0), (1.0, 0.0, False)):
            self.assertEqual(outcome(lambda: template.at(sequence, timestamp, quantized)),
                outcome(lambda: CANSourceRef(**fixed, yield_sequence=sequence,
                    timestamp=timestamp, time_quantized=quantized)))

    def test_fixed_errors_still_use_full_public_validation(self):
        """固定声明错误在模板构造时完整拒绝。参数: 无。返回: None。异常: 断言失败。"""
        for change in (dict(field='{}'), dict(field=' '+constants()['field']),
                dict(profile='wrong'), dict(channel=True), dict(frame_id=-1),
                dict(session_id='bad id'), dict(path=''), dict(signal='other'),
                dict(is_extended=1), dict(signal='')):
            fixed = constants(**change)
            self.assertEqual(outcome(lambda: CANReferenceTemplate(**fixed)),
                outcome(lambda: CANSourceRef(**fixed, yield_sequence=0,
                    timestamp=0.0, time_quantized=False)))

    def test_only_template_creation_encodes_fixed_locator(self):
        """重复at不重新编码六字段，但公开构造仍执行原检查。参数: 无。返回: None。异常: 断言失败。"""
        fixed = constants()
        template = CANReferenceTemplate(**fixed)
        with patch.object(LegacyCANField, 'key', new=property(
                lambda value: (_ for _ in ()).throw(AssertionError('重复定位编码')))):
            first = template.at(0, 0.0, False)
            second = template.at(1, 0.1, True)
            self.assertEqual(first.field, fixed['field'])
            self.assertEqual(second.yield_sequence, 1)
            with self.assertRaisesRegex(AssertionError, '重复定位编码'):
                CANSourceRef(**fixed, yield_sequence=0, timestamp=0.0, time_quantized=False)

    def test_snapshot_and_each_reference_are_independent_and_frozen(self):
        """调用者字典变更不影响模板或已交付行，冻结属性保持。参数: 无。返回: None。异常: 断言失败。"""
        fixed = constants()
        template = CANReferenceTemplate(**fixed)
        fixed['path'] = '另一个输入.blf'
        first, second = template.at(0, 0.0, False), template.at(1, 0.1, True)
        self.assertNotEqual(first.path, fixed['path'])
        self.assertIsNot(first.__dict__, second.__dict__)
        with self.assertRaises(FrozenInstanceError):
            first.path = 'wrong'
        with self.assertRaises(FrozenInstanceError):
            template._fields = {}
        with self.assertRaises(TypeError):
            template._fields['path'] = 'wrong'

    def test_dynamic_failure_traceback_does_not_keep_template(self):
        """保留原错误时不额外挂住已可释放的模板。参数: 无。返回: None。异常: 断言失败。"""
        template = CANReferenceTemplate(**constants())
        try:
            template.at(0, math.nan, False)
        except ValueError as error:
            trace = error.__traceback__
            frames = []
            while trace is not None:
                if trace.tb_frame.f_code.co_name == 'at':
                    frames.append(trace.tb_frame.f_locals)
                trace = trace.tb_next
            self.assertEqual(len(frames), 1)
            self.assertIsNone(frames[0]['self'])
        else:
            self.fail('非有限原时间必须拒绝')


if __name__ == '__main__':
    unittest.main()
