"""用明确合成事实验证直接扫描证据的计数、身份和范围。

不读取CAN或生成已退役的v4结果包装；真实扫描和当前发布由执行层专项覆盖。"""

from dataclasses import replace
import unittest

from chronaxis.core.direct_message import DirectMessageEvidence


def evidence(**changes):
    """手写合成扫描事实。参数: 负例覆盖项。返回: 新证据。异常: 原模型校验错误。"""
    values = dict(source='bus', session_id='session', decoder_profile='sclicer-functions-v1',
        read_identity='synthetic-read', input_identity='declared-input',
        source_contract_sha256='1' * 64, description_sha256='2' * 64,
        request_sha256='3' * 64, signal_stream_sha256='4' * 64,
        projected_aliases=('power', 'direction'), progress_count=3, sample_count=4,
        observed_frame_count=3, first_time_ns=5, last_time_ns=9,
        observed_start_ns=5, observed_end_ns=9, calculation_frame_ids=(256,), source_eof=True)
    values.update(changes)
    return DirectMessageEvidence(**values)






class DirectEvidenceTests(unittest.TestCase):
    """来源证据与结果版本独立，空数据不伪造文件或消息历史身份。"""

    def test_facts_identity_includes_read_projection_selection_and_stream(self):
        """逐个事实变化必须进入身份。参数: 无。返回: None。异常: 断言失败。"""
        original = evidence()
        for changes in ({'read_identity': 'another-read'}, {'input_identity': 'other-input'},
                {'source_contract_sha256': 'a' * 64}, {'description_sha256': 'b' * 64},
                {'request_sha256': 'c' * 64}, {'signal_stream_sha256': 'd' * 64},
                {'projected_aliases': ('direction', 'power')}, {'progress_count': 4},
                {'sample_count': 3}, {'observed_frame_count': 4}, {'last_time_ns': 8},
                {'observed_start_ns': 4}, {'observed_end_ns': 10}, {'calculation_frame_ids': (256, 257)}):
            with self.subTest(changes=changes):
                self.assertNotEqual(original.identity, replace(original, **changes).identity)
        self.assertEqual(len(original.identity), 64)
        self.assertFalse(hasattr(original, 'store_sha256'))
        self.assertFalse(hasattr(original, 'history_sha256'))

    def test_empty_and_invalid_scan_facts(self):
        """空原帧必须无样本/首末，拒绝假EOF、重复选择及非规范SHA。参数: 无。返回: None。异常: 断言失败。"""
        empty = evidence(observed_frame_count=0, sample_count=0, projected_aliases=(),
            first_time_ns=None, last_time_ns=None, observed_start_ns=None, observed_end_ns=None)
        self.assertEqual(empty.observed_frame_count, 0)
        for changes in ({'source_eof': 1}, {'source_eof': False}, {'progress_count': 0},
                {'progress_count': True}, {'sample_count': -1}, {'observed_frame_count': True},
                {'signal_stream_sha256': 'A' * 64}, {'evidence_kind': 'message-store-v1'},
                {'projected_aliases': ['power']}, {'projected_aliases': ('power', 'power')},
                {'projected_aliases': ()}, {'first_time_ns': None}, {'last_time_ns': 4},
                {'first_time_ns': 2**63}, {'calculation_frame_ids': (256, 256)},
                {'calculation_frame_ids': (True,)}, {'calculation_frame_ids': (2**29,)},
                {'observed_frame_count': 0}):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError, OverflowError)):
                evidence(**changes)





if __name__ == '__main__':
    unittest.main()
