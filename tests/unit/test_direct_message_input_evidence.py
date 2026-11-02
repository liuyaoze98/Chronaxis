"""验证按需输入证据的身份、范围、空输入及取消传播。

手写事实和独立摘要核对核心证据模型，不读取来源，不生成旧v5结果。"""

from dataclasses import replace
from hashlib import sha256
import unittest
from unittest.mock import patch

from chronaxis.core import direct_message
from chronaxis.core.direct_message import DirectMessageInputEvidence


EMPTY_SHA = sha256(b'').hexdigest()


def evidence_fields(**changes):
    """给出独立手写的实际输入事实，不调用编码器推导预期。

    参数: changes为单项负例或有效边界覆盖。返回: 新字段dict。
    异常: 无主动异常，内存错误原样传播；不读取文件或生产端状态。
    """
    values = dict(source='bus', session_id='session', decoder_profile='sclicer-functions-v1',
        read_identity='synthetic-read', input_identity='declared-input',
        source_contract_sha256='1' * 64, description_sha256='2' * 64, request_sha256='3' * 64,
        original_timestamps_sha256='4' * 64, retained_records_sha256='5' * 64,
        required_aliases=('power', 'direction'), observed_frame_count=3, retained_record_count=2,
        first_time_ns=5, last_time_ns=9, observed_start_ns=4, observed_end_ns=10,
        calculation_frame_ids=(256,), source_eof=True, evidence_kind='can-direct-input-v2')
    values.update(changes)
    return values


def evidence(**changes):
    """构造待测新模型。参数: 字段覆盖项。返回: 新证据。异常: 模型校验或取消错误。"""
    return DirectMessageInputEvidence(**evidence_fields(**changes))












class DirectInputEvidenceTests(unittest.TestCase):
    """新输入证据有独立身份、费用与解码域；旧证据的公开格式不受改写。"""

    def test_identity_matches_independent_length_prefix_hash_and_every_field(self):
        """所有可变事实及版本进入身份。参数: 无。返回: None。异常: 断言失败。"""
        actual = evidence()
        # 独立写出顺序与tuple边界，不调用模型使用的_hash_parts。
        parts = ('can-direct-input-v2', 'bus', 'session', 'sclicer-functions-v1',
            'synthetic-read', 'declared-input', '1' * 64, '2' * 64, '3' * 64,
            '4' * 64, '5' * 64, '2', 'power', 'direction', '3', '2',
            '5', '9', '4', '10', '1', '256', 'true')
        digest = sha256()
        for part in parts:
            raw = part.encode('utf-8')
            digest.update(str(len(raw)).encode('ascii') + b':' + raw)
        self.assertEqual(actual.identity, digest.hexdigest())
        variations = dict(source='other_bus', session_id='other_session', decoder_profile='other-profile',
            read_identity='other-read', input_identity='原输入', source_contract_sha256='a' * 64,
            description_sha256='b' * 64, request_sha256='c' * 64, original_timestamps_sha256='d' * 64,
            retained_records_sha256='e' * 64, required_aliases=('direction', 'power'),
            observed_frame_count=4, retained_record_count=1, first_time_ns=6, last_time_ns=8,
            observed_start_ns=3, observed_end_ns=11, calculation_frame_ids=(256, 257))
        for name, value in variations.items():
            with self.subTest(field=name):
                self.assertNotEqual(actual.identity, replace(actual, **{name: value}).identity)
        for absent in ('signal_stream_sha256', 'sample_count', 'progress_count',
                'store_sha256', 'history_sha256'):
            self.assertFalse(hasattr(actual, absent))

    def test_empty_source_and_no_matching_records_are_distinct(self):
        """零记录不等于零原帧，常量指标不要求别名。参数: 无。返回: None。异常: 断言失败。"""
        no_target = evidence(required_aliases=(), retained_record_count=0,
            retained_records_sha256=EMPTY_SHA)
        empty = evidence(required_aliases=(), observed_frame_count=0, retained_record_count=0,
            original_timestamps_sha256=EMPTY_SHA, retained_records_sha256=EMPTY_SHA,
            first_time_ns=None, last_time_ns=None, observed_start_ns=None, observed_end_ns=None)
        self.assertNotEqual(no_target.identity, empty.identity)
        declared_range = replace(empty, observed_start_ns=-10, observed_end_ns=10)
        self.assertIsNone(declared_range.first_time_ns)
        self.assertEqual(evidence(required_aliases=()).retained_record_count, 2)
    def test_malformed_facts_reject_counts_types_ranges_and_empty_digest(self):
        """拒绝假EOF、混合版本、计数和范围矛盾。参数: 无。返回: None。异常: 断言失败。"""
        cases = (
            {'source_eof': 1}, {'source_eof': False}, {'evidence_kind': 'can-direct-scan-v1'},
            {'observed_frame_count': True}, {'observed_frame_count': -1},
            {'retained_record_count': False}, {'retained_record_count': -1}, {'retained_record_count': 4},
            {'required_aliases': ['power']}, {'required_aliases': ('power', 'power')},
            {'required_aliases': ('power.bad',)}, {'required_aliases': (False,)},
            {'source_contract_sha256': 'A' * 64}, {'description_sha256': '2' * 63},
            {'request_sha256': b'3' * 64}, {'original_timestamps_sha256': 'not-sha'},
            {'retained_records_sha256': '5' * 65}, {'retained_record_count': 0},
            {'calculation_frame_ids': []}, {'calculation_frame_ids': ()}, {'calculation_frame_ids': (False,)},
            {'calculation_frame_ids': (256, 256)}, {'calculation_frame_ids': (257, 256)},
            {'calculation_frame_ids': (-1,)}, {'calculation_frame_ids': (2**29,)},
            {'first_time_ns': None}, {'last_time_ns': 4}, {'first_time_ns': 2**63},
            {'last_time_ns': -(2**63) - 1}, {'first_time_ns': True},
            {'observed_start_ns': None}, {'observed_end_ns': 8}, {'observed_start_ns': 11})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError, OverflowError)):
                evidence(**changes)
        # 空流有唯一已知摘要；它不允许虚构原帧首末或只有一端的观测范围。
        empty = dict(observed_frame_count=0, retained_record_count=0,
            original_timestamps_sha256=EMPTY_SHA, retained_records_sha256=EMPTY_SHA,
            first_time_ns=None, last_time_ns=None, observed_start_ns=None, observed_end_ns=None)
        for changes in ({'original_timestamps_sha256': '4' * 64}, {'first_time_ns': 0},
                {'observed_end_ns': 0}, {'retained_record_count': 1}):
            with self.subTest(empty_changes=changes), self.assertRaises((TypeError, ValueError)):
                evidence(**(empty | changes))






    def test_identity_cancel_propagates_once_and_releases_new_parts(self):
        """身份计算取消不重试，新增tuple不滞留构造器帧。参数: 无。返回: None。异常: 断言失败。"""
        for error_type in (KeyboardInterrupt, SystemExit, MemoryError):
            failure = error_type('synthetic identity fault')
            with patch.object(direct_message, '_hash_parts', side_effect=failure) as calculate:
                try:
                    evidence()
                except BaseException as caught:
                    self.assertIs(caught, failure)
                    calculate.assert_called_once()
                    trace = caught.__traceback__
                    found = False
                    while trace is not None:
                        frame = trace.tb_frame
                        if (frame.f_code.co_name == '__post_init__'
                                and frame.f_code.co_filename == direct_message.__file__):
                            self.assertIsNone(frame.f_locals.get('parts'))
                            found = True
                        trace = trace.tb_next
                    self.assertTrue(found)
                else:
                    self.fail('身份计算取消未传播')


if __name__ == '__main__':
    unittest.main()
