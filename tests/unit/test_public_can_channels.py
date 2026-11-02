"""验证用户1基通道到内部0基模型的唯一转换，以及原始文件布局保持原约定。

通过公共计划、配置展开和INI入口检查，合成文件只写临时目录，不读取私人日志。
静态配置夹具保留完整类型，避免为通道验证额外加载DBC。
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from chronaxis import AnalysisPlan, PlanValidationError
from chronaxis.configuration.resolution import resolved_configuration
from chronaxis.legacy.records import field_from_dict
from chronaxis.sources.can_spec import can_field_from_key
from test_can_planning import can_config
from test_plan_message_calculations import legacy_config


class PublicCANChannelTests(unittest.TestCase):
    """所有配置入口使用同一正整数规则，类型化API继续使用内部编号。"""

    def test_channels_in_each_raw_format_and_omitted_signal(self):
        """参数: 无。返回: None。异常: 断言失败；各格式及省略继承只转换一次。"""
        for source_type, suffix in (('can_blf', '.blf'), ('can_asc', '.asc'), ('asc_or_blf', '.asc'), ('raw_can_csv', '.csv')):
            for channel in (1, 2):
                for explicit in (False, True):
                    with self.subTest(source_type=source_type, channel=channel, explicit=explicit):
                        raw = can_config()
                        source = raw['sources'][0]
                        source.update(source_type=source_type, path='not-read'+suffix,
                                      dbc_by_channel={str(channel): 'not-read.dbc'})
                        if source_type != 'can_blf':
                            source.pop('legacy_profile', None)
                            source.pop('reader', None)
                        if source_type == 'raw_can_csv':
                            source['reader'] = dict(time_format='numeric', layout=dict(fields={
                                'timestamp': 'time', 'frame_id': 'id', 'data': 'data'}))
                        field = raw['signals'][0]['field']
                        field.pop('channel')
                        if explicit:
                            field['channel'] = channel
                        original = deepcopy(raw)
                        plan = AnalysisPlan.from_dict(raw)
                        self.assertEqual(plan.sources[0].config.channel, channel-1)
                        self.assertEqual(can_field_from_key(plan.signals[0].definition.field).channel, channel-1)
                        self.assertEqual(raw, original)

    def test_zero_and_noncanonical_values_rejected(self):
        """参数: 无。返回: None。异常: 断言失败；旧0不自动猜成第一路。"""
        for key in ('0', '00', '01', '-1', '+1', ' 1', '1\n', '0x1', True, 1):
            raw = can_config()
            raw['sources'][0]['dbc_by_channel'] = {key: 'not-read.dbc'}
            with self.subTest(key=key), self.assertRaises(PlanValidationError):
                AnalysisPlan.from_dict(raw)
        for value in (0, -1, True, 1.0, '1', None):
            raw = can_config()
            raw['signals'][0]['field']['channel'] = value
            with self.subTest(value=value), self.assertRaisesRegex(PlanValidationError, '从1开始'):
                AnalysisPlan.from_dict(raw)

    def test_group_and_message_selector_share_public_number(self):
        """参数: 无。返回: None。异常: 断言失败；集中信号与逐报文使用公共2。"""
        raw = legacy_config()
        raw['sources'][0]['dbc_by_channel'] = {'2': 'not-read.dbc'}
        for signal in raw['signals']:
            signal['field']['channel'] = 2
        for calculation in raw['message_calculations']:
            calculation['update_message']['channel'] = 2
        plan = AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.message_calculations[0].update_message.channel, 1)
        signal = raw['signals'][0]
        field = signal.pop('field')
        signal.pop('source', None)
        signal['signal'] = field.pop('signal')
        raw['signals'] = [dict(field, source='bus', signals=[signal]), *raw['signals'][1:]]
        plan = AnalysisPlan.from_dict(raw)
        self.assertEqual(can_field_from_key(plan.signals[0].definition.field).channel, 1)
        raw['signals'][0]['channel'] = 0
        with self.assertRaisesRegex(PlanValidationError, '从1开始'):
            AnalysisPlan.from_dict(raw)

    def test_resolve_roundtrip_keeps_public_channels(self):
        """参数: 无。返回: None。异常: I/O或断言失败；两次resolve后通道不漂移。"""
        with TemporaryDirectory(prefix='chronaxis-channel-') as directory:
            path = Path(directory)/'analysis.json'
            raw = can_config()
            for defaults in (False, True):
                path.write_text(json.dumps(raw), encoding='utf-8')
                first = resolved_configuration(path, defaults=defaults)
                path.write_text(json.dumps(first), encoding='utf-8')
                second = resolved_configuration(path, defaults=defaults)
                self.assertEqual(first, second)
                self.assertEqual(tuple(second['sources'][0]['dbc_by_channel']), ('1',))
                self.assertEqual(second['signals'][0]['field']['channel'], 1)
                self.assertEqual(AnalysisPlan.from_dict(second).sources[0].config.channel, 0)

    def test_human_explanation_uses_public_channel_and_both_id_forms(self):
        """参数: 无。返回: None。异常: 断言失败；解释不暴露内部0基键误导用户。"""
        from chronaxis import explain_analysis_plan
        from chronaxis.configuration.explanation import explanation_text
        plan=AnalysisPlan.from_dict(can_config())
        text=explanation_text(plan,explain_analysis_plan(plan))
        self.assertIn('通道 1',text)
        self.assertNotIn('通道 0',text)
        self.assertNotIn('"channel":0',text)
        self.assertIn('0x100（256）',text)
        self.assertIn('Power.value',text)

    def test_typed_field_api_still_accepts_zero(self):
        """参数: 无。返回: None。异常: 断言失败；低层API不是公共配置入口。"""
        field = field_from_dict(dict(channel=0, signal='value', frame_id=256, is_extended=False, is_fd=False))
        self.assertEqual(field.channel, 0)
