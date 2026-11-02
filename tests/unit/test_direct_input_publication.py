"""验证显式详细CAN元数据的字段策略与有限费用。

以合成元数据核字段展开和预算，不读取BLF，不使用已退役的输入结果包装。"""

from dataclasses import replace
from sys import getsizeof
import unittest

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType
from chronaxis.legacy.records import LegacyCANField, PROFILE_ID
from chronaxis.results.can_metadata import CANSourceMetadata, CANUnitCheck
from chronaxis.results.manifest import RunMetadata, _metadata_size


OLD_CAN_FIELDS = ('source', 'session_id', 'legacy_profile', 'path', 'dbc_path', 'channel',
    'read_identity', 'worker_pid', 'frame_count', 'first_ns', 'last_ns', 'raw_store_path',
    'raw_store_sha256', 'raw_spool_bytes', 'dependency_versions', 'vendor_sha256', 'unit_checks')


def source(**changes):
    """构造明确的合成CAN事实。参数: 字段覆盖项。返回: 冻结模型。异常: 原模型校验错误。"""
    values = dict(source='bus', session_id='session', legacy_profile=PROFILE_ID,
        path='synthetic.blf', dbc_path='synthetic.dbc', channel=0, read_identity='synthetic-read',
        worker_pid=123, frame_count=3, first_ns=5, last_ns=9, raw_store_path=None,
        raw_store_sha256=None, raw_spool_bytes=0, dependency_versions=(('python', 'synthetic'),),
        vendor_sha256=(('utils.py', 'a' * 64),), unit_checks=())
    values.update(changes)
    return CANSourceMetadata(**values)


def definition(alias='power', source_name='bus', frame_id=256, channel=0):
    """给所需别名完整CAN定位。参数: 名称、来源、ID及通道。返回: 定义。异常: 原声明错误。"""
    field = LegacyCANField(channel, 'RawPower', frame_id, False, False)
    return SignalDefinition(alias, source_name, field.key, SignalDType.FLOAT64, 'W', 10, input_unit='W')


def metadata(can_sources, bindings=()):
    """关联实际所需字段与CAN事实。参数: 来源、定义及可选明细事实。返回: 清单。异常: 原校验错误。"""
    return RunMetadata('synthetic-run', 'synthetic-input', 'synthetic-plan', 'reference', 3,
        'explicit synthetic seconds', (('session', 0, 12),), '2026-10-20T22:00:00+08:00',
        device_label='home', signal_bindings=bindings, can_sources=can_sources,
        detailed_diagnostics=True)


def old_source_fee(value):
    """按新增字段策略之前的明确CAN字段计算费用，不调用新估费函数。

    参数: 合成CAN模型及其有限标量/tuple。返回: 基础对象字节。
    异常: 未登记夹具类型为TypeError；无I/O或预算变更。
    """
    if type(value) is CANSourceMetadata:
        names = OLD_CAN_FIELDS + (() if value.decode_scope == 'all' else ('decode_scope', 'decode_frame_ids'))
        return getsizeof(value) + sum(old_source_fee(getattr(value, name)) + 32 for name in names)
    if type(value) is tuple:
        return getsizeof(value) + sum(old_source_fee(item) + 32 for item in value)
    if value is None or type(value) in (str, int, float, bool):
        return getsizeof(value)
    raise TypeError('本例旧费用只使用无单位记录的明确字段')




class RequestedFieldMetadataTests(unittest.TestCase):
    """字段投影有真实非默认策略，普通/混合运行不能丢掉所需字段检查。"""

    def test_default_and_old_requested_preserve_serialization_and_exact_fee(self):
        """旧all与旧requested均不新增默认策略键或费用。参数: 无。返回: None。异常: 断言失败。"""
        for original in (source(), source(decode_scope='requested', decode_frame_ids=(256,))):
            actual = metadata((original,))
            document = actual.to_dict()['can_sources'][0]
            expected = {name: getattr(original, name) for name in OLD_CAN_FIELDS}
            if original.decode_scope == 'requested':
                expected.update(decode_scope='requested', decode_frame_ids=(256,))
            self.assertEqual(document, expected)
            self.assertNotIn('decoded_values_policy', document)
            self.assertEqual(_metadata_size(original), old_source_fee(original))
            explicit_default = replace(original, decoded_values_policy='all_values-v1')
            self.assertEqual(metadata((explicit_default,)).to_dict(), actual.to_dict())
            self.assertEqual(metadata((explicit_default,)).estimated_bytes(), actual.estimated_bytes())
        requested = source(decode_scope='requested', decode_frame_ids=(256,),
            decoded_values_policy='requested_fields-v1')
        self.assertEqual(metadata((requested,)).to_dict()['can_sources'][0]['decoded_values_policy'],
            'requested_fields-v1')
        self.assertEqual(_metadata_size(requested), old_source_fee(requested)
            + getsizeof('requested_fields-v1') + 32)

    def test_requested_supports_ordinary_full_mixed_sources_and_raw_facts(self):
        """按真实字段合同接受各运行路线，不由summary_direct猜解码合法性。参数: 无。返回: None。异常: 断言失败。"""
        checks = (CANUnitCheck('power', 'W', 'W', 'verified'),)
        actual = source(decode_scope='requested', decode_frame_ids=(256,),
            decoded_values_policy='requested_fields-v1', unit_checks=checks)
        self.assertEqual(metadata((actual,), (definition(),)).can_sources, (actual,))
        # 额外CAN来源和原帧保存不改变needed字段校验；各来源的alias、ID及通道独立核对。
        another = source(source='secondary_bus', read_identity='another-read', decode_scope='requested',
            decode_frame_ids=(257,), decoded_values_policy='requested_fields-v1',
            unit_checks=(CANUnitCheck('other_power', 'W', None, 'declared'),),
            raw_store_path='synthetic/raw.jsonl', raw_store_sha256='b' * 64, raw_spool_bytes=100)
        combined = metadata((actual, another),
            (definition(), definition('other_power', 'secondary_bus', 257)))
        self.assertEqual(combined.to_dict()['can_sources'][1]['raw_store_sha256'], 'b' * 64)

    def test_policy_types_and_actual_alias_channel_id_coverage_reject(self):
        """坏策略、缺实际字段、跨来源通道均拒绝，不按bool的整数相等放行。参数: 无。返回: None。异常: 断言失败。"""
        for value in (None, False, 1, b'all_values-v1', 'requested', 'unknown'):
            with self.subTest(policy=value), self.assertRaises((TypeError, ValueError)):
                source(decoded_values_policy=value)
        with self.assertRaisesRegex(ValueError, 'all解码'):
            source(decoded_values_policy='requested_fields-v1')
        valid = source(decode_scope='requested', decode_frame_ids=(256,),
            decoded_values_policy='requested_fields-v1', unit_checks=(CANUnitCheck('power', 'W', 'W', 'verified'),))
        for changed_source, bindings in (
                (replace(valid, decode_frame_ids=()), (definition(),)),
                (replace(valid, decode_frame_ids=(257,)), (definition(),)),
                (valid, (definition(channel=1),)),
                (replace(valid, unit_checks=()), (definition(),)),
                (valid, ()),
                (valid, (replace(definition(), field='not-a-CAN-key'),))):
            with self.subTest(source=changed_source, bindings=bindings), self.assertRaises((TypeError, ValueError)):
                metadata((changed_source,), bindings)
        with self.assertRaises((TypeError, ValueError)):
            replace(valid, decode_frame_ids=(True,))


if __name__ == '__main__':
    unittest.main()
