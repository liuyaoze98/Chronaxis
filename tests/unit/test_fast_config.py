"""核对 fast 的静态能力、信号单位转换、原始位置及配置边界。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis.configuration import load_configuration
from chronaxis.fast.config import compile_config
from chronaxis.fast.compute import prepare_metric
from chronaxis.planning.checks import PlanValidationError


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / 'Docs/Current/examples/message-minimal.yaml'


class FastConfigurationTests(unittest.TestCase):
    """所有改写只放在专用工作区，不要求存在测试日志。"""

    def setUp(self):
        """复制配置的业务声明并固定 DBC 路径。"""
        self.temp = TemporaryDirectory(dir=ROOT/'work')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.raw = load_configuration(SAMPLE).data
        src = self.raw['sources'][0]
        src['paths'] = str(self.folder/'absent.asc')
        src['dbc_by_channel']['1'] = str(SAMPLE.parent/'data/power.dbc')

    def compile(self):
        """传入 JSON 文件，走实际配置入口。"""
        path = self.folder / 'input.json'
        path.write_text(json.dumps(self.raw),encoding='utf8')
        return compile_config(path)

    def test_shipped_example_and_import_without_recording(self):
        """教学配置语义、导入位置与相对路径保持，缺 ASC 仍能完成静态校验。"""
        standard = compile_config(SAMPLE)
        self.assertEqual(standard['domain_ns'],[0,10**9])
        self.assertEqual(standard['channel'],1)
        self.assertEqual(standard['metrics'][0]['frame_id'],0x100)
        self.assertEqual(standard['table_format'],'readable_csv')
        self.assertEqual(standard, json.loads(json.dumps(standard)))
        module = self.folder / 'defs'
        module.mkdir()
        src = self.raw.pop('sources')[0]
        src['name'] = 'meter'
        src['paths'] = 'absent.asc'
        (module/'source.json').write_text(json.dumps({'sources':[src],'signals':self.raw.pop('signals')}), encoding='utf8')
        self.raw['imports']=['defs/source.json']
        spec=self.compile()
        self.assertEqual(Path(spec['path']), module/'absent.asc')

    def test_v4_internal_watt_and_kilowatt(self):
        """同帧 4kW 与 500W 相加再乘 0.1s，得到 450J，不能只在最终汇总时换算。"""
        dbc = self.folder/'units.dbc'
        dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: E\nBO_ 256 Frame: 4 E\n'
                       ' SG_ High : 0|16@1+ (1,0) [0|65535] "kW" E\n'
                       ' SG_ Low : 16|16@1+ (1,0) [0|65535] "W" E\n', encoding='ascii')
        self.raw['config_version']=4
        self.raw['sources'][0]['dbc_by_channel']['1']=str(dbc)
        self.raw['signals']=[dict(name=k.lower(),field={'frame_id':'0x100','signal':k},
                                 dtype='float64',period='100ms') for k in ('High','Low')]
        self.raw['message_calculations'][0]['expr']='(high + low) * period'
        spec=self.compile()
        item=prepare_metric(spec['metrics'][0])
        self.assertEqual(item.evaluate({'High':4,'Low':500}),450.)

    def test_mark_separate_conflicts(self):
        """一份配置同时锁定旧读取器、后端与明细时，列出所有显式冲突。"""
        self.raw['sources'][0]['legacy_profile']='sclicer-functions-v1'
        self.raw['execution']={'backend':'numpy','memory_budget_bytes':268435456}
        self.raw['outputs']={'contributions':'full'}
        with self.assertRaises(PlanValidationError) as raised:
            self.compile()
        errors=raised.exception.diagnostics
        self.assertEqual({e.path for e in errors}, {'$.sources[0].legacy_profile','$.execution.backend',
                                                     '$.outputs.contributions'})
        self.assertTrue(all(e.source==str(self.folder/'input.json') for e in errors))

    def test_rejects_bad_dbc_or_cross_frame_before_opening_log(self):
        """显式完整的单位声明也须核对 DBC，不能等运行后才发现绑定错误。"""
        sig=self.raw['signals'][0]
        sig['field']['signal']='Undefined'
        sig['unit']='W'
        with self.assertRaisesRegex(PlanValidationError,'DBC'):
            self.compile()
        sig['field']['signal']='Power'
        sig['field']['frame_id']=0x101
        with self.assertRaises(PlanValidationError):
            self.compile()

    def test_rejects_v4_features_and_continuous_paths(self):
        """连续分卷静态接入，但越过fast表达式白名单仍拒绝。"""
        self.raw['sources'][0]['paths']=[str(self.folder/'first.asc'),str(self.folder/'next.asc')]
        self.assertEqual(len(self.compile()['inputs']), 2)
        self.raw['sources'][0]['paths']=str(self.folder/'first.asc')
        self.raw['config_version']=4
        self.raw['message_calculations'][0]['expr']='where(True,power,power) * period'
        with self.assertRaises(PlanValidationError):
            self.compile()
