"""用同一ASC数据核充电预设与普通条件积分的等价范围。

输入为仓库已声明的合成CAN数据，模式1在[1,3)秒成立，电流10A、电压400V。
两后端分别运行公开AnalysisRunner，手算总能量8000J；不改预设含义或用户输入。
"""
from pathlib import Path
import unittest

from ruamel.yaml import YAML
from chronaxis import AnalysisPlan, AnalysisRunner


class ChargePresetApplicabilityTests(unittest.TestCase):
    """只比较明确等价的条件与单位；边界差异单独给独立预期。"""

    def config(self, *, preset=True, comparison='>', unit='Wh', current_min=5):
        """参数: 是否预设、普通比较符/单位、门槛。返回: 计划。异常: 公开配置错误。"""
        path=Path(__file__).resolve().parents[2]/'Docs/Current/examples/preset-charge-energy.yaml'
        raw=YAML(typ='safe').load(path.read_text(encoding='utf-8'))
        raw['presets'][0]['parameters']['current_min']=current_min
        if not preset:
            raw.pop('presets')
            # 普通数值积分不需要给电流附加充电方向或电池包测点来套用预设契约。
            for signal in raw['signals']:
                signal.pop('measurement_location',None)
                signal.pop('sign_convention',None)
            raw['derived']={'demo_preset_power':{'expr':'voltage * current','unit':'W'}}
            raw['rules']=[{'name':'demo_preset_activity','rule_type':'condition_duration',
                'condition':f'mode == 1 and current {comparison} {current_min}','minimum_duration':'0s'}]
            raw['calculations']=[
                {'name':'demo_preset_energy','operation':'integral','expr':'demo_preset_power',
                    'scope':{'rule':'demo_preset_activity'},'unit':unit},
                {'name':'demo_preset_charge','operation':'integral','expr':'current',
                    'scope':{'rule':'demo_preset_activity'},'unit':'Ah'}]
        return AnalysisPlan.from_dict(raw,base_dir=path.parent)

    def run_plan(self, plan, backend):
        """参数: 计划/后端。返回: 活动边界和指标数值单位。异常: 原运行错误。"""
        with AnalysisRunner(backend=backend).run(plan) as result:
            events=[(row.start_ns,row.end_ns) for row in result.iter_events()]
            values={row.calculation_id:(row.value,row.unit) for row in result.iter_calculations()}
        return events,values

    def test_equivalent_plain_conditions_match_preset_on_both_backends(self):
        """参数: 无。返回: None。异常: 断言失败；相同>5A及Wh/Ah结果完全一致。"""
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend):
                preset=self.run_plan(self.config(),backend)
                ordinary=self.run_plan(self.config(preset=False),backend)
                self.assertEqual(preset,ordinary)
                self.assertEqual(preset[0],[(10**9,3*10**9)])
                self.assertAlmostEqual(preset[1]['demo_preset_energy'][0],8000/3600)
                self.assertAlmostEqual(preset[1]['demo_preset_charge'][0],20/3600)

    def test_inclusive_current_threshold_and_kwh_require_plain_combination(self):
        """参数: 无。返回: None。异常: 断言失败；10A本身被>10排除、被>=10保留。"""
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend):
                events,_=self.run_plan(self.config(current_min=10),backend)
                self.assertEqual(events,[])
                events,values=self.run_plan(self.config(preset=False,comparison='>=',unit='kWh',current_min=10),backend)
                self.assertEqual(events,[(10**9,3*10**9)])
                self.assertEqual(values['demo_preset_energy'][1],'kWh')
                self.assertAlmostEqual(values['demo_preset_energy'][0],8000/3600000)
