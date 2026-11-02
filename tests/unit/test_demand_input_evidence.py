"""验证按需时间证据的none/selected/source边界。

手写三帧两目标记录及空来源事实；模型成功不代表真实扫描完成，不再包装旧v6结果。"""

# 替换冻结事实和修改独立JSON树，仅用于有明确预期的协议正反例。
from dataclasses import replace
import unittest

from chronaxis.core.direct_message import DemandMessageInputEvidence
from chronaxis.results.can_metadata import CANSourceMetadata
from chronaxis.execution.observed_ingestion import SourceScanObservation
from chronaxis.legacy.records import PROFILE_ID
from test_direct_message_input_evidence import EMPTY_SHA, evidence_fields as old_fields


def evidence_fields(scope='none', **changes):
    """明确组织所需时间范围，不由生产端推测输入或填造时间。

    参数: scope为none/selected/source；changes覆盖具体负例或边界事实。
    返回: DemandMessageInputEvidence构造字段dict，默认三原帧及两目标记录。
    异常: 内存分配错误直接传播；不校验覆盖项，交由被测模型拒绝。
    """
    # 基础身份及手写计数与旧v5夹具相同，新增策略不改变原始输入声明。
    values = old_fields(evidence_kind='can-demand-input-v1', time_scope=scope, input_check='auto')
    if scope != 'source':
        # 未采集完整时间时绝不能把空流SHA当作全部时间证明。
        values.update(original_timestamps_sha256=None, observed_start_ns=None, observed_end_ns=None)
    if scope == 'none':
        values.update(first_time_ns=None, last_time_ns=None)
    values.update(changes)
    return values


def evidence(scope='none', **changes):
    """构造一次独立合成证据，不声称对应真实来源读取。

    参数: scope和changes为显式构造事实。
    返回: DemandMessageInputEvidence，字段合法时生成策略绑定身份。
    异常: 模型类型、范围、摘要或计数错误原样传播。
    """
    return DemandMessageInputEvidence(**evidence_fields(scope, **changes))


def selected_metadata(**changes):
    """建立没有目标记录的合成清单，不读取声明路径或伪造实际扫描。

    参数: changes覆盖本测试需要的字段。返回: CANSourceMetadata。
    异常: 元数据模型的类型或跨字段错误原样传播。
    """
    values = dict(source='bus', session_id='session', legacy_profile=PROFILE_ID,
        path='未读取/input.blf', dbc_path='未读取/input.dbc', channel=0,
        read_identity='synthetic-read', worker_pid=123, frame_count=3, first_ns=None,
        last_ns=None, raw_store_path=None, raw_store_sha256=None, raw_spool_bytes=0,
        dependency_versions=(('python', 'synthetic'),), vendor_sha256=(('utils.py', 'a'*64),),
        unit_checks=(), decode_scope='requested', decode_frame_ids=(),
        decoded_values_policy='requested_fields-v1', input_check='auto', time_scope='selected',
        check_policy_version='demand-check-v1', retained_record_count=0)
    values.update(changes)
    return CANSourceMetadata(**values)


class DemandInputEvidenceTests(unittest.TestCase):
    """独立比较时间事实和codec版本，所有用例仅持有有限内存对象。"""

    def test_selected_metadata_without_targets_cannot_claim_any_target_bounds(self):
        """空目标清单只能有None首末，原帧非空和任意假值都不构成目标观测。

        参数: 无。返回: None。异常: 接受空目标假首末或拒绝真实目标单点则失败。
        """
        empty = selected_metadata()
        self.assertEqual((empty.selected_first_ns, empty.selected_last_ns), (None, None))
        for first, last in ((0, 0), (0, None), (None, 0), ('bad', None)):
            with self.subTest(first=first, last=last), self.assertRaises(ValueError):
                replace(empty, selected_first_ns=first, selected_last_ns=last)
        point = replace(empty, retained_record_count=1, selected_first_ns=5, selected_last_ns=5)
        self.assertEqual((point.selected_first_ns, point.selected_last_ns), (5, 5))
        for first, last in ((None, None), (None, 5), (5, None)):
            with self.subTest(first=first, last=last), self.assertRaises((TypeError, ValueError)):
                replace(point, selected_first_ns=first, selected_last_ns=last)

    def test_selected_scan_bounds_require_actual_target_records(self):
        """扫描事实也以目标数量确定首末，不拿无关原帧数作为目标时间证据。

        参数: 无。返回: None。异常: 空目标假首末、非空目标缺首末或全来源伪造未被拒绝。
        """
        empty = SourceScanObservation('bus', 'session', None, None, 3, None, None, True,
                                      'selected', 0, 0)
        for first, last in ((0, 0), (0, None), (None, 0)):
            with self.subTest(first=first, last=last), self.assertRaises(ValueError):
                replace(empty, first_ns=first, last_ns=last)
        point = replace(empty, retained_record_count=1, first_ns=5, last_ns=5)
        self.assertEqual((point.first_ns, point.last_ns), (5, 5))
        for first, last in ((None, None), (None, 5), (5, None)):
            with self.subTest(first=first, last=last), self.assertRaises(ValueError):
                replace(point, first_ns=first, last_ns=last)

    def test_scope_valid_ranges_keep_uncollected_selected_and_source_distinct(self):
        """三范围均合法但含义不同，只有source允许全原时间摘要和观测域。

        参数: 无。返回: None。异常: 范围混淆、身份不区分策略或边界丢失则失败。
        """
        none, selected, source = (evidence(scope) for scope in ('none', 'selected', 'source'))
        self.assertEqual((none.first_time_ns, none.last_time_ns, none.observed_start_ns,
            none.observed_end_ns, none.original_timestamps_sha256), (None,) * 5)
        self.assertEqual((selected.first_time_ns, selected.last_time_ns), (5, 9))
        self.assertEqual((selected.observed_start_ns, selected.observed_end_ns,
            selected.original_timestamps_sha256), (None,) * 3)
        self.assertEqual((source.first_time_ns, source.last_time_ns,
            source.observed_start_ns, source.observed_end_ns), (5, 9, 4, 10))
        self.assertEqual(source.original_timestamps_sha256, '4' * 64)
        self.assertEqual(len({item.identity for item in (none, selected, source)}), 3)
        full = replace(source, input_check='full')
        self.assertNotEqual(full.identity, source.identity)
        self.assertEqual(replace(selected, last_time_ns=5).first_time_ns, 5)
        self.assertEqual(replace(source, first_time_ns=5, last_time_ns=5,
            observed_start_ns=5, observed_end_ns=5).observed_end_ns, 5)

    def test_uncollected_time_rejects_empty_digest_and_synthetic_timestamps(self):
        """没有采集完整原时间时，空SHA、任意SHA及伪造0边界均不得通过。

        参数: 无。返回: None。异常: 未采集事实被替换成空流或0时间则失败。
        """
        for scope in ('none', 'selected'):
            for digest in (EMPTY_SHA, 'a' * 64, ''):
                with self.subTest(scope=scope, digest=digest), self.assertRaises(ValueError):
                    evidence(scope, original_timestamps_sha256=digest)
            with self.subTest(scope=scope, check='full'), self.assertRaises(ValueError):
                evidence(scope, input_check='full')
        # none连目标首末也未采集，不能为了通过后续模型而填成0。
        for name in ('first_time_ns', 'last_time_ns', 'observed_start_ns', 'observed_end_ns'):
            with self.subTest(field=name), self.assertRaises(ValueError):
                evidence(**{name: 0})
        with self.assertRaises(TypeError):
            evidence('source', original_timestamps_sha256=None)

    def test_selected_time_range_requires_targets_and_cannot_claim_source_range(self):
        """目标首末有序且必须对应目标记录，不得把它们填进全来源观测域。

        参数: 无。返回: None。异常: 目标首末缺失、倒退、超界或观测域伪造被接受则失败。
        """
        for changes in ({'first_time_ns': None}, {'last_time_ns': None},
                {'first_time_ns': 10}, {'last_time_ns': 4},
                {'observed_start_ns': 5, 'observed_end_ns': 9},
                {'first_time_ns': True}, {'last_time_ns': 2**63}):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError, OverflowError)):
                evidence('selected', **changes)
        no_target = evidence('selected', retained_record_count=0,
            retained_records_sha256=EMPTY_SHA, first_time_ns=None, last_time_ns=None)
        self.assertEqual(no_target.observed_frame_count, 3)
        with self.assertRaises(ValueError):
            replace(no_target, first_time_ns=0, last_time_ns=0)

    def test_empty_source_preserves_absent_or_ordered_declared_range_only(self):
        """真实空流需空摘要，可有有序声明域，但10到5的倒置范围必须拒绝。

        参数: 无。返回: None。异常: 空来源分支绕过范围检查或生成假首末则失败。
        """
        empty = evidence('source', observed_frame_count=0, retained_record_count=0,
            original_timestamps_sha256=EMPTY_SHA, retained_records_sha256=EMPTY_SHA,
            first_time_ns=None, last_time_ns=None, observed_start_ns=None, observed_end_ns=None)
        declared = replace(empty, observed_start_ns=-10, observed_end_ns=10)
        self.assertEqual((declared.observed_start_ns, declared.observed_end_ns), (-10, 10))
        self.assertIsNone(declared.first_time_ns)
        self.assertIsNone(declared.last_time_ns)
        for changes in ({'observed_start_ns': 10, 'observed_end_ns': 5},
                {'observed_start_ns': 0}, {'observed_end_ns': 0}, {'first_time_ns': 0},
                {'original_timestamps_sha256': '4' * 64}, {'retained_records_sha256': '5' * 64}):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                replace(empty, **changes)
        # 对none而言非空但无目标与真正空文件也不能仅凭None时间混为一类。
        no_target = evidence(retained_record_count=0, retained_records_sha256=EMPTY_SHA)
        empty_untimed = replace(no_target, observed_frame_count=0)
        self.assertNotEqual(no_target.identity, empty_untimed.identity)

    def test_source_range_counts_and_scope_values_remain_strict(self):
        """全来源范围包含首末；假EOF、错误计数和非法策略不因省检查而放宽。

        参数: 无。返回: None。异常: 任一矛盾字段被模型接受则失败。
        """
        for changes in ({'first_time_ns': None}, {'observed_start_ns': 6},
                {'observed_end_ns': 8}, {'last_time_ns': 4},
                {'observed_frame_count': True}, {'retained_record_count': 4},
                {'source_eof': 1}, {'source_eof': False}, {'time_scope': 'all'},
                {'input_check': 'optional'}, {'evidence_kind': 'can-direct-input-v2'}):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                evidence('source', **changes)





if __name__ == '__main__':
    # 导入只定义纯内存夹具，直接执行才进入unittest。
    unittest.main()
