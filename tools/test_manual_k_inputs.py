"""核验 DOC-REVIEW-12 输入和条件示例；只加载配置及教学DBC，不读日志或写产物。

覆盖自动CAN路由、来源通道和枚举条件；可用 unittest 直接运行，失败返回非零。
"""
from copy import deepcopy
from pathlib import Path
import unittest
from chronaxis import AnalysisPlan, validate_analysis_plan
from chronaxis.planning.checks import PlanValidationError

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'Docs/Current/examples'


def configuration():
    """参数无。返回独立的CAN配置；只引用已有教学DBC。异常无。"""
    return dict(config_version=4, dataset=dict(name='route_probe'),
        sources=[dict(name='bus',source_type='asc_or_blf',paths=['data/power.blf'],
                      dbc_by_channel={'1':'data/power.dbc'})],
        signals=[dict(name='power',source='bus',field=dict(frame_id=256,signal='Power'),valid_for='1s')],
        calculations=[dict(name='energy',operation='integral',expr='power',unit='J')],
        execution=dict(process_count=1))


class ManualInputTests(unittest.TestCase):
    """使用公开配置接口验证文案里的合法与非法填写方式。"""

    def valid(self, raw):
        """参数为声明字典。返回校验报告；加载或校验失败则断言失败。"""
        report=validate_analysis_plan(AnalysisPlan.from_dict(raw,base_dir=EXAMPLES))
        self.assertTrue(report.valid,report.errors)
        return report

    def test_twelve_decode_scope_routes(self):
        """四类来源各测省略/requested/all；文本路由拒绝显式字段。"""
        for kind in ('blf','asc','mixed','offset'):
            for scope in (None,'requested','all'):
                raw=configuration();source=raw['sources'][0]
                source['paths']=['data/power.asc'] if kind=='asc' else ['data/power.blf']
                if kind=='mixed': source['paths'].append('data/power.asc')
                if kind=='offset': source['paths']=[dict(path='data/power.blf',offset='1s')]
                if scope is not None: source['reader']=dict(decode_scope=scope)
                with self.subTest(kind=kind,scope=scope):
                    if scope is None or kind=='blf': self.valid(raw)
                    else:
                        with self.assertRaises(PlanValidationError) as error:
                            AnalysisPlan.from_dict(raw,base_dir=EXAMPLES)
                        self.assertIn('decode_scope',str(error.exception))

    def test_channels_require_separate_sources(self):
        """信号channel不能救两通道来源，合法的两来源绑定可省略并行设置。"""
        for channel in (None,1):
            raw=configuration();raw['sources'][0]['dbc_by_channel']['2']='data/power.dbc'
            if channel is not None: raw['signals'][0]['field']['channel']=channel
            with self.subTest(channel=channel),self.assertRaises(PlanValidationError) as error:
                AnalysisPlan.from_dict(raw,base_dir=EXAMPLES)
            self.assertIn('dbc_by_channel',str(error.exception))
        raw=configuration();raw.pop('execution')
        other=deepcopy(raw['sources'][0]);other.update(name='bus_two',dbc_by_channel={'2':'data/power.dbc'})
        raw['sources'].append(other)
        other_signal=deepcopy(raw['signals'][0]);other_signal.update(name='power_two',source='bus_two')
        raw['signals'].append(other_signal)
        self.valid(raw)

    def test_integer_and_enum_conditions(self):
        """显式5A兼容mA电流；枚举用标签或原码，整数状态直接比较。"""
        for unit in ('A','mA'):
            for dtype,expr,valid in [('enum','mode == "running"',True),
                                      ('enum','enum_code(mode) == 7',True),
                                      ('enum','mode == 1',False),('int64','mode == 1',True)]:
                raw=dict(config_version=4,dataset=dict(name='condition_probe'),
                    sources=[dict(name='table',source_type='memory',rows=[dict(time='0s',values=dict(i=10,state=7))])],
                    signals=[dict(name='current',field='i',dtype='float64',unit=unit,valid_for='1s'),
                             dict(name='mode',field='state',dtype=dtype,unit='1',valid_for='1s')],
                    rules=[dict(name='running',rule_type='rising_edge',condition='current > quantity(5, "A") and '+expr)])
                if dtype=='enum':raw['signals'][1].update(code_dtype='uint64',choices=[[0,'idle'],[7,'running']])
                with self.subTest(unit=unit,dtype=dtype,expr=expr):
                    if valid:self.valid(raw)
                    else:
                        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(raw,base_dir=EXAMPLES)


if __name__=='__main__':
    unittest.main()
