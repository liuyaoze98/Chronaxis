"""核对纯来源合同提取后仍检查完整声明，且不会产生运行或磁盘完成证据。

device_label: home。输入为明确构造的typed来源、信号、描述和请求，无输入扫描或
文件产物；测试返回的全部原定义及各种独立不匹配。公共历史的实际损坏/EOF/取消
语义另由原test_decoded_bindings与test_run_empty_source_binding回归核验。
本模块只验证合同；空字段返回空定义也不代表真实扫描已经完成。
"""

from dataclasses import replace
import unittest
from unittest.mock import patch

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType
from chronaxis.execution.bindings import require_decoded_source_contract
from chronaxis.sources.descriptions import describe_fields, source_timebase_identity
from chronaxis.sources.models import ReadRequest, SourceCapabilities, SourceDescription


class DecodedSourceContractTests(unittest.TestCase):
    """仅检查同一来源的声明关系；每例使用新冻结模型，不接触共享输入或预算。"""

    def setUp(self):
        """创建两个声明，第二个代表计划未用于表达式但仍完整投影的信号。

        参数: 无。返回: None。异常: 夹具模型错误直接使测试失败。
        """
        self.clock = TimebaseSpec('clock', TimeType.RELATIVE, 'source-contract-home')
        self.source = DeclaredSource('can', self.clock, 'synthetic-input', 4)
        self.signals = (
            SignalDefinition('current', 'can', 'raw.current', D.FLOAT64, 'A', 3,
                             input_unit='mA', scale=.001, semantic_id='battery.current'),
            SignalDefinition('unused', 'can', 'raw.unused', D.FLOAT64, 'V', 7,
                             measurement_location='battery', mapping_version='home-v1'))
        self.declarations = DeclarationBindings('session', self.clock, Interval(0, 20),
                                               (self.source,), self.signals)
        fields = describe_fields('can', self.signals, {
            'source_timebase_sha256': source_timebase_identity(self.clock, 4), 'offset_ns': 4})
        self.description = SourceDescription('can', fields, 'clock', None, None,
                                             SourceCapabilities(True, False, False, False))
        self.request = ReadRequest('session', ('current', 'unused'), 0, 20, 4)

    def check(self, *, declarations=None, source=None, description=None, request=None):
        """调用真实纯合同函数，用显式变体替换所需对象。

        参数: 四个typed变体为None时使用夹具。
        返回: 真实函数的别名定义dict。异常: 原校验错误不包装、不吞掉。
        """
        return require_decoded_source_contract(
            self.declarations if declarations is None else declarations,
            self.source if source is None else source,
            self.description if description is None else description,
            self.request if request is None else request)

    def test_all_original_definitions_are_returned_without_io_or_evidence(self):
        """返回完整原定义而非依赖裁剪或伪运行证明。

        参数: 无。返回: None。异常: 任何文件打开、证据构造或断言失败均使测试失败。
        """
        with patch('pathlib.Path.open', side_effect=AssertionError('pure contract opened file')), \
                patch('chronaxis.execution.bindings.DecodedSourceEvidence',
                      side_effect=AssertionError('pure contract forged evidence')):
            result = self.check()
        self.assertEqual(tuple(result), ('current', 'unused'))
        for signal in self.signals:
            self.assertIs(result[signal.name], signal)

    def test_unused_declared_signal_has_full_normalization_checked(self):
        """完整读取请求中的未用信号仍拒绝错误转换/方向/质量/语义声明。

        参数: 无。返回: None。异常: 变体误接收或模型/断言失败直接传播。
        """
        changes = ({'valid_for_ns': 8}, {'valid_range': (0, 500)}, {'invalid_values': (-1,)},
                   {'same_time_policy': 'last_by_sequence'}, {'measurement_location': 'motor'},
                   {'mapping_version': 'home-v2'}, {'semantic_id': 'battery.voltage'},
                   {'semantic_id': 'battery.voltage', 'semantic_contract_version': '2'},
                   {'sign_convention': 'positive_discharge'}, {'input_sign_convention': 'positive_charge'},
                   {'direction_factor': -1, 'scale': -1, 'input_sign_convention': 'positive_charge',
                    'sign_convention': 'positive_discharge'})
        for change in changes:
            with self.subTest(change=change):
                signals = (self.signals[0], replace(self.signals[1], **change))
                with self.assertRaises(ValueError):
                    self.check(declarations=replace(self.declarations, signals=signals))

    def test_field_dtype_unit_and_missing_fingerprint_rejected(self):
        """实际描述不能只因别名相同而掩盖原字段、类型、单位或缺转换摘要。

        参数: 无。返回: None。异常: 错误描述误接收或断言失败直接传播。
        """
        original = self.description.fields[1]
        without_hash = dict(original.metadata)
        del without_hash['normalization_sha256']
        variants = (replace(original, field=replace(original.field, field='other')),
                    replace(original, dtype=D.INT64), replace(original, unit='A'),
                    replace(original, metadata=without_hash))
        for field in variants:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.check(description=replace(self.description, fields=(self.description.fields[0], field)))
        with self.assertRaises(ValueError):
            self.check(description=replace(self.description, fields=self.description.fields[:1]))

    def test_partial_projection_preserves_public_semantics_and_all_definitions(self):
        """原公共部分投影仍可用，但返回定义始终完整，未投影字段仍受时钟约束。

        参数: 无。返回: None。异常: 投影语义改变或断言失败直接传播。
        """
        request = replace(self.request, signal_names=('current',))
        changed = replace(self.description.fields[1], unit='A')
        description = replace(self.description, fields=(self.description.fields[0], changed))
        result = self.check(request=request, description=description)
        self.assertEqual(tuple(result), ('current', 'unused'))
        self.assertIs(result['unused'], self.signals[1])

    def test_every_described_clock_checked_for_partial_and_empty_projection(self):
        """无请求样本也不能跳过任何字段的完整时间原点和偏移校验。

        参数: 无。返回: None。异常: 时钟冲突误接收或断言失败直接传播。
        """
        field = self.description.fields[1]
        variants = ({'source_timebase_sha256': '0' * 64, 'offset_ns': 4},
                    {'source_timebase_sha256': source_timebase_identity(self.clock, 4), 'offset_ns': 5}, {})
        for projected in (('current',), ()):
            for locator in variants:
                with self.subTest(projected=projected, locator=locator):
                    changed = replace(field, field=replace(field.field, locator=locator))
                    with self.assertRaises(ValueError):
                        self.check(request=replace(self.request, signal_names=projected),
                                   description=replace(self.description, fields=(self.description.fields[0], changed)))

    def test_session_domain_timebase_and_source_identity_rejected(self):
        """会话、范围、完整来源时间和实际来源归属必须属于当前声明。

        参数: 无。返回: None。异常: 错误归属误接收或断言失败直接传播。
        """
        requests = (replace(self.request, session_id='other'), replace(self.request, domain_start_ns=1),
                    replace(self.request, domain_end_ns=21), replace(self.request, signal_names=('unknown',)))
        for request in requests:
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.check(request=request)
        with self.assertRaises(ValueError):
            self.check(description=replace(self.description, timebase_id='other_clock'))
        for source in (replace(self.source, input_identity='other-input'), replace(self.source, offset_ns=5),
                       replace(self.source, timebase=replace(self.clock, origin='other-origin'))):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.check(source=source)
        other_fields = tuple(replace(item, field=replace(item.field, source='other'))
                             for item in self.description.fields)
        with self.assertRaises(ValueError):
            self.check(description=replace(self.description, name='other', fields=other_fields))

    def test_empty_source_contract_does_not_create_evidence(self):
        """空需求可保未用声明，只返回静态定义；不生成扫描或磁盘证据。

        参数: 无。返回: None。异常: 空定义替代运行证明或断言失败直接传播。
        """
        declarations = replace(self.declarations, signals=())
        description = replace(self.description, fields=())
        request = replace(self.request, signal_names=())
        with patch('chronaxis.execution.bindings.DecodedSourceEvidence',
                   side_effect=AssertionError('empty contract forged evidence')):
            result = self.check(declarations=declarations, description=description,
                                request=request)
        self.assertEqual(result, {})
        with patch('chronaxis.execution.bindings.DecodedSourceEvidence',
                   side_effect=AssertionError('unused declaration forged evidence')):
            unused = self.check(declarations=self.declarations, description=description,
                                request=request)
        self.assertEqual(unused, {item.name: item for item in self.declarations.signals})
        # 非空实际需求仍不能以空描述通过；静态声明存在不代表列已经读取。
        for declarations in (self.declarations, declarations):
            with self.assertRaises(ValueError):
                self.check(declarations=declarations, description=description,
                           request=self.request)

    def test_strict_models(self):
        """纯入口不接无类型占位或任意真值对象。

        参数: 无。返回: None。异常: 非typed模型误接收时断言失败。
        """
        original = (self.declarations, self.source, self.description, self.request)
        for position in range(4):
            arguments = list(original)
            arguments[position] = object()
            with self.subTest(position=position), self.assertRaises(TypeError):
                require_decoded_source_contract(*arguments)
