"""独立核CAN运行清单的结构化事实、单位原声明及当前简明默认清单。

输入为明确合成CANUnitCheck/CANSourceMetadata与SignalDefinition，不创建真实read、
DBC或暂存文件；输出为JSON兼容结构及类型/归属/预算基线断言。构造校验不能证明
来源已读取，None/空DBC单位仍保declared，不借模型制造真实CAN/DBC哈希证明。
详细模型需显式开启；嵌套文本仍进入保守大小估算，不作为公开Runner默认来源事实。
全部测试无I/O和进程副作用，不复用其他TestCase夹具，也不运行reader/旧库。
"""

from configuration_fixtures import current_fixture

# 标准库只验证冻结、有限JSON与静态副作用，不建立输入或输出目录。
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
from sys import getsizeof
import unittest
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType
from chronaxis.legacy.records import LegacyCANField, PROFILE_ID
from chronaxis.results.can_metadata import CANSourceMetadata, CANUnitCheck
from chronaxis.results.manifest import RunMetadata


class CANRunMetadataTests(unittest.TestCase):
    """只检查给定事实的模型合同，不伪称本测试完成真实报文验收。"""

    def signal(self, *, alias='power', source='bus', input_unit='W', unit='W', scale=1):
        """声明完整原定位和显式单位转换，便于查清输入单位与结果单位的区别。

        参数: alias/source为安全名；input_unit/unit/scale为明确转换声明。
        返回: SignalDefinition。异常: 原绑定校验失败；不加载DBC或样本。
        """
        field = LegacyCANField(0, 'RawPower', 0x321, False, False)
        return SignalDefinition(alias, source, field.key, SignalDType.FLOAT64, unit, 10,
            input_unit=input_unit, scale=scale)

    def source(self, **changes):
        """给出有限合成read事实，摘要为测试文本而非本测试读取文件所得。

        参数: changes为本例静态字段差异。返回: CANSourceMetadata。
        异常: 被测内部一致性校验原错误；不打开声明路径。
        """
        values = {'source': 'bus', 'session_id': 'session', 'legacy_profile': PROFILE_ID,
            'path': '未读取/drive.blf', 'dbc_path': '未读取/drive.dbc', 'channel': 0,
            'read_identity': 'synthetic-read', 'worker_pid': 1234, 'frame_count': 4,
            'first_ns': 0, 'last_ns': 8, 'raw_store_path': '未读取/raw_frames.jsonl',
            'raw_store_sha256': 'a' * 64, 'raw_spool_bytes': 2048,
            'dependency_versions': (('python', 'synthetic-parent-version'), ('python-can', '4.6.1')),
            'vendor_sha256': (('utils.py', 'b' * 64),),
            'unit_checks': (CANUnitCheck('power', 'W', 'W', 'verified'),)}
        values.update(changes)
        return CANSourceMetadata(**values)

    def metadata(self, **changes):
        """把同一来源事实关联到原会话和原绑定，不省略运行侧二次核对。

        参数: changes为本例RunMetadata覆盖。返回: RunMetadata。
        异常: 被测清单校验原错误；不会执行来源。
        """
        values = {'run_id': 'synthetic-run', 'input_identity': 'synthetic-input', 'plan_hash': 'synthetic-plan',
            'backend': 'reference', 'config_version': 3, 'source_time_interpretation': 'explicit synthetic seconds',
            'session_boundaries': (('session', 0, 12),), 'started_at': '2026-10-16T08:18:50+08:00',
            'device_label': 'home', 'detailed_diagnostics': True, 'signal_bindings': (self.signal(),), 'can_sources': (self.source(),)}
        values.update(changes)
        return RunMetadata(**values)

    def test_no_can_default_is_current_compact_dictionary(self):
        """默认只输出当前运行字段，未请求详细诊断不展开来源模型。

        参数: 无。返回: None。异常: 新空字段泄漏、旧字段变化或默认费用增加断言失败。
        """
        run = RunMetadata('synthetic-run', 'synthetic-input', 'synthetic-plan', 'reference', 3,
            'explicit synthetic seconds', (('session', 0, 12),), '2026-10-16T08:18:50+08:00', device_label='home')
        self.assertEqual(run.can_sources, ())
        document = run.to_dict()
        expected_keys = {'run_id', 'input_identity', 'plan_hash', 'backend', 'config_version',
            'source_time_interpretation', 'session_boundaries', 'started_at',
            'parsing_policy', 'worker_config', 'software_version',
            'retain_work', 'detailed_diagnostics', 'device_label'}
        self.assertEqual(set(document), expected_keys)
        self.assertNotIn('can_sources', document)
        self.assertNotIn('semantic_version', document)
        self.assertFalse(document['retain_work'])
        self.assertFalse(document['detailed_diagnostics'])
        self.assertGreater(run.estimated_bytes(), 0)
        self.assertEqual(replace(run).estimated_bytes(), run.estimated_bytes())

    def test_structured_can_json_preserves_actual_fields_without_io_and_freezes(self):
        """结构化字段原样进入JSON，构造与导出不访问声明路径或替代成自由JSON字符串。

        参数: 无。返回: None。异常: 产生I/O、字段丢失/变型或允许修改冻结事实断言失败。
        """
        with patch('builtins.open', side_effect=AssertionError('元数据打开文件')) as opened, \
                patch.object(Path, 'stat', side_effect=AssertionError('元数据stat')) as stat, \
                patch.object(Path, 'resolve', side_effect=AssertionError('元数据resolve')) as resolve:
            run = self.metadata()
            document = json.loads(json.dumps(current_fixture(run.to_dict()), ensure_ascii=False, allow_nan=False))
        source = document['can_sources'][0]
        self.assertIs(type(source), dict)
        self.assertEqual((source['source'], source['session_id'], source['legacy_profile']), ('bus', 'session', PROFILE_ID))
        self.assertEqual((source['read_identity'], source['worker_pid'], source['frame_count'], source['first_ns'], source['last_ns']),
            ('synthetic-read', 1234, 4, 0, 8))
        self.assertEqual(source['raw_store_sha256'], 'a' * 64)
        self.assertEqual(source['raw_spool_bytes'], 2048)
        self.assertEqual(source['unit_checks'], [{'alias': 'power', 'input_unit': 'W', 'dbc_unit': 'W', 'status': 'verified'}])
        self.assertEqual(document['dbc_hashes'], [])
        for method in (opened, stat, resolve):
            method.assert_not_called()
        for owner, name, value in ((run, 'can_sources', ()), (run.can_sources[0], 'frame_count', 0),
                (run.can_sources[0].unit_checks[0], 'status', 'declared')):
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(owner, name, value)

    def test_unit_check_requires_matching_nonempty_dbc_or_preserved_missing(self):
        """verified只比较真实非空原单位，None/空字符串不丢失且不能伪装已核实。

        参数: 无。返回: None。异常: 声明升级、单位自动裁剪/换算或非法状态通过断言失败。
        """
        for missing in (None, ''):
            check = CANUnitCheck('power', 'W', missing, 'declared')
            self.assertIs(check.dbc_unit, missing)
            run = self.metadata(can_sources=(self.source(unit_checks=(check,)),))
            self.assertEqual(run.to_dict()['can_sources'][0]['unit_checks'][0]['dbc_unit'], missing)
        bad = (('bad.alias', 'W', 'W', 'verified'), ('power', '', None, 'declared'),
            ('power', None, None, 'declared'), ('power', 'W', 1, 'verified'),
            ('power', 'W', None, 'verified'), ('power', 'W', '', 'verified'), ('power', 'W', 'kW', 'verified'),
            ('power', 'W', 'W', 'declared'), ('power', 'W', ' ', 'declared'), ('power', 'W', None, 'unknown'))
        for values in bad:
            with self.subTest(values=values), self.assertRaises((TypeError, ValueError)):
                CANUnitCheck(*values)

    def test_source_counts_timestamps_and_native_integer_boundaries(self):
        """0帧必须无首末，真实单点合法；非空坐标int64有序且所有整数拒绝bool。

        参数: 无。返回: None。异常: 伪造观测、溢出/乱序或非原生整数通过断言失败。
        """
        empty = self.source(frame_count=0, first_ns=None, last_ns=None, raw_spool_bytes=0)
        point = self.source(frame_count=1, first_ns=-1, last_ns=-1)
        self.assertEqual((empty.first_ns, empty.last_ns), (None, None))
        self.assertEqual((point.first_ns, point.last_ns), (-1, -1))
        self.source(first_ns=-(1 << 63), last_ns=(1 << 63) - 1)
        bad = ({'frame_count': 0}, {'frame_count': True}, {'frame_count': -1}, {'worker_pid': 0},
            {'worker_pid': True}, {'worker_pid': 1.0}, {'channel': False}, {'channel': -1},
            {'raw_spool_bytes': True}, {'raw_spool_bytes': -1}, {'first_ns': None}, {'last_ns': None},
            {'first_ns': True}, {'last_ns': 8.0}, {'first_ns': 9, 'last_ns': 8},
            {'first_ns': -(1 << 63) - 1}, {'last_ns': 1 << 63})
        for change in bad:
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError, OverflowError)):
                self.source(**change)

    def test_source_rejects_bad_hashes_pairs_alias_duplicates_and_structure(self):
        """摘要只校64hex，冻结键值与单位别名必须唯一，不能接自由dict或假模型。

        参数: 无。返回: None。异常: 非法事实结构通过断言失败；不以格式合法证明真实文件SHA。
        """
        check = CANUnitCheck('power', 'W', 'W', 'verified')
        bad = ({'source': 'bus.bad'}, {'session_id': 'bad.session'}, {'legacy_profile': 'other'},
            {'path': ''}, {'dbc_path': None}, {'raw_store_path': ' '}, {'read_identity': ''},
            {'raw_store_sha256': 'a' * 63}, {'raw_store_sha256': 'g' * 64}, {'raw_store_sha256': None},
            {'dependency_versions': {'python': 'x'}}, {'dependency_versions': (('python', 'x'), ('python', 'x'))},
            {'dependency_versions': (('python', ''),)}, {'dependency_versions': (('python', True),)},
            {'vendor_sha256': (('utils.py', 'bad'),)}, {'vendor_sha256': (('utils.py', 'a' * 64), ('utils.py', 'b' * 64))},
            {'unit_checks': [check]}, {'unit_checks': ({'alias': 'power'},)}, {'unit_checks': (check, check)})
        for change in bad:
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                self.source(**change)
        # hex大小写原文合法，不在模型里改写为另一个声明。
        self.assertEqual(self.source(raw_store_sha256='AF' * 32).raw_store_sha256, 'AF' * 32)

    def test_no_raw_store_is_explicit_and_keeps_all_frame_observations(self):
        """未导出原帧只省原帧仓，仍保留全部输入的帧数、首末和真实读取身份。

        参数: 无。返回: None。异常: 不一致的空仓声明未拒绝或清单丢事实时断言失败。
        """
        source = self.source(raw_store_path=None, raw_store_sha256=None, raw_spool_bytes=0)
        actual = self.metadata(can_sources=(source,)).to_dict()['can_sources'][0]
        self.assertIsNone(actual['raw_store_path'])
        self.assertIsNone(actual['raw_store_sha256'])
        self.assertEqual(actual['raw_spool_bytes'], 0)
        self.assertEqual((actual['frame_count'], actual['first_ns'], actual['last_ns']),
                         (source.frame_count, 0, 8))
        self.assertEqual(actual['read_identity'], source.read_identity)
        # 只有完整的None/None/0组合合法；单独删路径或摘要仍表示证据矛盾。
        for change in ({'raw_store_path': None},
                {'raw_store_path': None, 'raw_store_sha256': None},
                {'raw_store_path': None, 'raw_spool_bytes': 0},
                {'raw_store_sha256': None, 'raw_spool_bytes': 0}):
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                self.source(**change)

    def test_run_checks_source_session_alias_and_original_input_unit(self):
        """CAN事实须关联本次原绑定，不与输出单位或另一个会话的同名alias混用。

        参数: 无。返回: None。异常: 错会话/来源/alias/input_unit或自由模型通过断言失败。
        """
        can = self.source()
        wrong = ((),)
        for value in ([can], (object(),), ({'source': 'bus'},), (can, can), wrong):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                self.metadata(can_sources=value)
        for source in (replace(can, session_id='other'), replace(can, source='other'),
                self.source(unit_checks=(CANUnitCheck('missing', 'W', 'W', 'verified'),)),
                self.source(unit_checks=(CANUnitCheck('power', 'kW', 'kW', 'verified'),))):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.metadata(can_sources=(source,))
        definition = self.signal(input_unit='kW', unit='W', scale=1000)
        actual = self.source(unit_checks=(CANUnitCheck('power', 'kW', 'kW', 'verified'),))
        run = self.metadata(signal_bindings=(definition,), can_sources=(actual,))
        self.assertEqual(run.signal_bindings[0].unit, 'W')
        self.assertEqual(run.can_sources[0].unit_checks[0].input_unit, 'kW')
        with self.assertRaises(ValueError):
            self.metadata(signal_bindings=(definition,), can_sources=(can,))

    def test_budget_recurses_source_and_unit_check_leaves(self):
        """新两类冻结模型逐字段估算，深层文本变化不能只计顶层dataclass大小。

        参数: 无。返回: None。异常: 任一新模型缺递归、预算低估或None/空值被改写断言失败。
        """
        source = self.source()
        before = self.metadata(can_sources=(source,))
        longer = replace(source, read_identity='r' * 4096)
        after = self.metadata(can_sources=(longer,))
        self.assertEqual(after.estimated_bytes() - before.estimated_bytes(),
            16 * (getsizeof(longer.read_identity) - getsizeof(source.read_identity)))
        none_unit = replace(source, unit_checks=(CANUnitCheck('power', 'W', None, 'declared'),))
        empty_unit = replace(source, unit_checks=(CANUnitCheck('power', 'W', '', 'declared'),))
        self.assertEqual(self.metadata(can_sources=(empty_unit,)).estimated_bytes() - self.metadata(can_sources=(none_unit,)).estimated_bytes(),
            16 * (getsizeof('') - getsizeof(None)))

    def test_unit_checks_exactly_cover_can_aliases_and_do_not_require_non_can_sources(self):
        """同CAN来源不能漏核别名；空投影可空，其他来源不被推断为必须具备CAN事实。

        参数: 无。返回: None。异常: 遗漏检查被接受或对无关来源强加CAN记录时断言失败。
        """
        source = self.source()
        with self.assertRaises(ValueError):
            self.metadata(can_sources=(replace(source, unit_checks=()),))
        definitions = (self.signal(), self.signal(alias='extra_power'))
        with self.assertRaises(ValueError):
            self.metadata(signal_bindings=definitions, can_sources=(source,))
        complete = replace(source, unit_checks=source.unit_checks + (CANUnitCheck('extra_power', 'W', 'W', 'verified'),))
        self.assertEqual(len(self.metadata(signal_bindings=definitions, can_sources=(complete,)).can_sources[0].unit_checks), 2)
        other = self.signal(source='csv_source')
        self.assertEqual(self.metadata(signal_bindings=(other,), can_sources=()).can_sources, ())
        raw_only = replace(source, unit_checks=())
        self.assertEqual(self.metadata(signal_bindings=(other,), can_sources=(raw_only,)).can_sources[0].unit_checks, ())
