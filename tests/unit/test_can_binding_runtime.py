"""核对省略帧型后的DBC选择、迟到歧义及无关帧跳过。

使用明确构造的同ID定义和帧，预期来自实际类型；不扫描真实日志，不修改DBC。
元数据测试单独证明没有周期需求时不读取cycle_time。
"""

import unittest
from types import SimpleNamespace

from chronaxis.legacy.binding import FrameBindingResolver, dbc_candidates, select_message
from chronaxis.legacy.records import LegacyCANField
from chronaxis.legacy.worker import _field_metadata
from chronaxis.sources.can_updates import CANUpdateProjection


def definition(extended=False, fd=False, signal='Voltage', cycle=100):
    """构造可区分定义。参数: 帧型、信号和毫秒周期。返回: 消息替身。异常: 无。
    """
    return SimpleNamespace(frame_id=256, is_extended_frame=extended, is_fd=fd,
                           signals=[SimpleNamespace(name=signal, unit='V')], cycle_time=cycle)


def frame(extended=False, fd=False):
    """构造数据帧身份。参数: 两个真实标志。返回: 只读用途替身。异常: 无。
    """
    return SimpleNamespace(channel=0, arbitration_id=256, is_extended_id=extended,
                           is_fd=fd, is_remote_frame=False, is_error_frame=False)


class CANBindingRuntimeTests(unittest.TestCase):
    """以手工明确的候选和原帧检查自动匹配，而非依赖ID查表覆盖顺序。"""

    def test_actual_type_selects_definition(self):
        """同ID标准扩展选择正确对象。参数: 无。返回: None。异常: 断言失败。
        """
        standard, extended = definition(), definition(True)
        database = SimpleNamespace(messages=[standard, extended])
        field = LegacyCANField(0, 'Voltage', 256)
        resolver = FrameBindingResolver(database, (field,))
        selected = resolver.fields_for(frame(True))
        self.assertEqual(selected, (field,))
        self.assertIs(resolver.message_for(frame(True), selected), extended)
        # 标准帧随后出现意味着这个未限定的绑定已不唯一，不能接着混合计算。
        with self.assertRaisesRegex(ValueError, 'is_extended'):
            resolver.fields_for(frame())

    def test_signal_name_excludes_unrelated_type(self):
        """另一类型没有目标信号时跳过。参数: 无。返回: None。异常: 断言失败。
        """
        database = SimpleNamespace(messages=[definition(), definition(True, signal='Other')])
        field = LegacyCANField(0, 'Voltage', 256)
        resolver = FrameBindingResolver(database, (field,))
        self.assertEqual(resolver.fields_for(frame(True)), ())
        self.assertEqual(resolver.fields_for(frame()), (field,))
        projection = CANUpdateProjection('bus', 'trial', (field,)).for_read(_field_metadata(database, (field,)))
        self.assertFalse(projection.accepts_frame(frame(True)))
        self.assertEqual(projection.fields_for(frame()), (field,))

    def test_explicit_flags_filter_and_fd_compatibility(self):
        """显式限制有效，DBC FD兼容实际classic。参数: 无。返回: None。异常: 断言失败。
        """
        message = definition(fd=True)
        database = SimpleNamespace(messages=[message])
        field = LegacyCANField(0, 'Voltage', 256, False, False)
        resolver = FrameBindingResolver(database, (field,))
        self.assertEqual(resolver.fields_for(frame(fd=True)), ())
        self.assertEqual(resolver.fields_for(frame()), (field,))
        self.assertIs(select_message((message,), frame()), message)
        self.assertIsNone(select_message((definition(),), frame(fd=True)))

    def test_automatic_fd_notice_and_late_conflict(self):
        """自动匹配实际classic时记录提示，后续FD要求补选。参数: 无。返回: None。异常: 断言失败。
        """
        field = LegacyCANField(0, 'Voltage', 256)
        facts = _field_metadata(SimpleNamespace(messages=[definition(fd=True)]), (field,))
        projection = CANUpdateProjection('bus', 'trial', (field,)).for_read(facts)
        projection.fields_for(frame())
        self.assertEqual(projection.compatibility_fields, {field: False})
        with self.assertRaisesRegex(ValueError, 'is_fd'):
            projection.fields_for(frame(fd=True))

    def test_message_only_trigger_is_optional(self):
        """无值公式可省略帧型且仍拒绝迟到混用。参数: 无。返回: None。异常: 断言失败。
        """
        projection = CANUpdateProjection('bus', 'trial', (), message_keys=((0, 256, None, None),))
        self.assertIsNotNone(projection.build(frame(), 0, {}, None))
        with self.assertRaisesRegex(ValueError, 'is_extended'):
            projection.build(frame(True), 1, {}, None)

    def test_metadata_only_requests_needed_cycle(self):
        """显式有效期不读取周期；默认周期按需核唯一。参数: 无。返回: None。异常: 断言失败。
        """
        field = LegacyCANField(0, 'Voltage', 256)
        database = SimpleNamespace(messages=[definition(cycle=100), definition(True, cycle=200)])
        self.assertNotIn('cycle_ns', _field_metadata(database, (field,))[0])
        with self.assertRaisesRegex(ValueError, '周期不同'):
            _field_metadata(database, (field,), cycle_fields=(field,))
        database.messages[1].cycle_time = 100
        self.assertEqual(_field_metadata(database, (field,), cycle_fields=(field,))[0]['cycle_ns'], 100_000_000)

    def test_csv_missing_flags_require_real_unique_information(self):
        """FD DBC不能证明实际FD，小ID不证明标准帧。参数: 无。返回: None。异常: 断言失败。
        """
        field = LegacyCANField(0, 'Voltage', 256)
        resolver = FrameBindingResolver(SimpleNamespace(messages=[definition(fd=True)]), (field,))
        with self.assertRaisesRegex(ValueError, 'is_fd'):
            resolver.missing_flags(0, 256, None, None)
        self.assertEqual(resolver.missing_flags(0, 256, None, False), (False, False))
        resolver = FrameBindingResolver(SimpleNamespace(messages=[definition(), definition(True)]), (field,))
        with self.assertRaisesRegex(ValueError, 'is_extended'):
            resolver.missing_flags(0, 256, None, False)

    def test_missing_id_and_signal_have_distinct_errors(self):
        """名称不存在不能误导用户补帧型。参数: 无。返回: None。异常: 断言失败。
        """
        database = SimpleNamespace(messages=[definition()])
        with self.assertRaisesRegex(ValueError, '没有报文ID'):
            dbc_candidates(database, 257, ('Voltage',))
        with self.assertRaisesRegex(ValueError, '没有唯一的所需信号'):
            dbc_candidates(database, 256, ('Missing',))

    def test_duplicate_id_decode_uses_selected_message(self):
        """实际cantools同ID表发生覆盖时，仍按标准帧定义解码。参数: 无。返回: None。异常: 断言失败。
        """
        import cantools
        from chronaxis.legacy.batch_worker import _parse_selected
        dbc = ('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
               'BO_ 256 Standard: 1 Node\n SG_ Voltage : 0|8@1+ (2,0) [0|510] "V" Node\n'
               'BO_ 2147483904 Extended: 1 Node\n SG_ Voltage : 0|8@1+ (4,0) [0|1020] "V" Node\n')
        database = cantools.database.load_string(dbc, database_format='dbc')
        actual = frame()
        actual.data = b'\x0a'
        selector = LegacyCANField(0, 'Voltage', 256)
        resolver = FrameBindingResolver(database, (selector,))
        fields = resolver.fields_for(actual)
        message = resolver.message_for(actual, fields)
        processor = SimpleNamespace(parse_frame=lambda *args: self.fail('重复ID不得走旧ID查表'))
        self.assertEqual(_parse_selected(processor, database, actual, message, {256}), {'Voltage': 20})


class CANBindingRunnerTests(unittest.TestCase):
    """通过公开分析入口验证省略字段，而非只检查匹配辅助函数。"""

    from test_record_runner import RecordRunnerTests as _Fixture
    setUp = _Fixture.setUp
    asc = _Fixture.asc
    csv = _Fixture.csv
    blf = _Fixture.blf
    plan = _Fixture.plan
    fixtures = _Fixture.fixtures

    def test_automatic_three_formats_and_missing_csv_flags(self):
        """三格式自动绑定得同一1344J，CSV省略源帧型也通过。参数: 无。返回: None。异常: 断言失败。
        """
        from chronaxis import AnalysisRunner
        from uuid import uuid4
        for kind, path in self.fixtures().items():
            def edit(raw):
                """仅删可推定字段。参数: 合成配置。返回: None。异常: 键错误。
                """
                for signal in raw['signals']:
                    signal['field'].pop('message', None)
                    signal['field'].pop('is_extended')
                    signal['field'].pop('is_fd')
                    signal['field']['frame_id'] = '0x100'
                if kind == 'raw_can_csv':
                    fields = raw['sources'][0]['reader']['layout']['fields']
                    fields.pop('is_extended')
                    fields.pop('is_fd')
            with self.subTest(kind=kind):
                plan = self.plan(kind, path, 'actual', edit)
                with AnalysisRunner().run(plan, work_dir=self.root / uuid4().hex) as result:
                    energy = next(row.value for row in result.iter_calculations() if row.calculation_id == 'energy')
                    self.assertAlmostEqual(energy, 1344.0, places=3)


if __name__ == '__main__':
    unittest.main()
