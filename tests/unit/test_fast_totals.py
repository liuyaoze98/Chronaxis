"""按手算结果校验 fast 模板逐项总量、缺失与固定累计顺序。"""
from copy import deepcopy
from pathlib import Path
import unittest

from chronaxis.configuration import load_configuration
from chronaxis.fast.config import compile_template_plan
from chronaxis.fast.totals import FastTotals
from chronaxis.planning.checks import PlanValidationError
from chronaxis.planning.plan import AnalysisPlan


def plans():
    """两份由同一模板展开的独立文件；两桶同单位但方向不同。"""
    result = {}
    for job in ('A','B'):
        metrics = [dict(name=name, unit='J', frame_id=0x100, expr='power * period',
                        parameters={'period':.1}, direction={'signal':'current','bucket':bucket},
                        signals={'power':{'signal':'Power', 'dtype':'float64'}})
                   for name,bucket in [('discharge','positive'), ('charge','negative')]]
        result[job] = dict(path=job+'.asc',dbc='meter.dbc',metrics=metrics,channel=1)
    return result


def rows(p, n):
    """用 None 表示该项无观测；有效零与空值分别编码。"""
    return [dict(name=name,unit='J',value=value,status='complete' if value is not None else 'indeterminate')
            for name,value in [('discharge',p),('charge',n)]]


class FixedTotalsTests(unittest.TestCase):
    """预期指标即使单位和名称相同，也须证明来自相同绑定及方向。"""

    def test_only_missing_item_is_null(self):
        """B 文件缺充电读数只影响充电总量，抵消或无入选贡献的零保留。"""
        total=FastTotals.from_specs(plans(),template=True)
        out=total.finish({'B':rows(150,None),'A':rows(100,200)})
        self.assertEqual([(x['value'],x['status']) for x in out],[(250.,'complete'),(None,'indeterminate')])
        out=total.finish({'A':rows(100,0),'B':rows(-100,0)})
        self.assertEqual([x['value'] for x in out],[0.,0.])

    def test_failure_and_invalid_packets(self):
        """失败成员明确占位，协议缺项和非有限结果不能补零。"""
        total=FastTotals.from_specs(plans(),template=True)
        result=total.finish({'A':None,'B':rows(50,1)})
        self.assertEqual({v['reason'] for v in result},{'member_not_completed'})
        for invalid in ({'A':rows(2,3)}, {'A':[],'B':rows(2,1)},
                        {'A':rows(1,float('nan')), 'B':None}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                total.finish(invalid)

    def test_order_does_not_follow_worker_arrival(self):
        """用浮点舍入可区分的三个加数核实始终使用 A、B、C 顺序。"""
        specs=plans()
        specs['C']=dict(specs['A'],path='C.asc')
        total=FastTotals.from_specs(specs,template=True)
        result=total.finish({'C':rows(-1e16,0),'A':rows(1e16,0),'B':rows(1,0)})
        self.assertEqual(result[0]['value'],0.)

    def test_total_overflow_is_not_complete(self):
        """两个有限文件结果的和超限时给批量调用方明确错误。"""
        total=FastTotals.from_specs(plans(),template=True)
        with self.assertRaises(OverflowError):
            total.finish({'A':rows(1e308,1),'B':rows(1e308,1)})

    def test_ambiguous_or_mixed_inputs_rejected(self):
        """逐一替换公式参数、绑定或来源，禁止误把同名同单位的不同指标相加。"""
        with self.assertRaises(ValueError):
            FastTotals.from_specs(plans(),template=False)
        for changed in (dict(direction={'signal':'current','bucket':'negative'}),dict(unit='Wh'),
                        dict(parameters={'period':1}),dict(frame_id=0x101)):
            with self.subTest(changed=changed):
                specs=plans()
                specs['B']['metrics'][0].update(changed)
                with self.assertRaises(ValueError):
                    FastTotals.from_specs(specs,template=True)
        for changed in (dict(path='A.asc'),dict(channel=2),dict(dbc='other.dbc'),dict(domain_ns=[0,9])):
            specs=plans()
            specs['B'].update(changed)
            with self.assertRaises(ValueError):
                FastTotals.from_specs(specs,template=True)

    def test_template_preserves_explicit_backend_and_file(self):
        """通用执行器的默认值不冲突，显式 backend 冲突保留模板和输入定位。"""
        root=Path(__file__).resolve().parents[2]/'Docs/Current/examples'
        path=root/'message-minimal.yaml'
        raw=load_configuration(path).data
        plan=AnalysisPlan.from_dict(raw,base_dir=root)
        result=compile_template_plan(plan,template_path=path)
        self.assertEqual(result['metrics'][0]['unit'],'J')
        bad=deepcopy(raw)
        bad['execution']={'backend':'reference'}
        plan=AnalysisPlan.from_dict(bad,base_dir=root)
        with self.assertRaises(PlanValidationError) as caught:
            compile_template_plan(plan,template_path=path)
        self.assertEqual(caught.exception.path,'$.execution.backend')
        self.assertEqual(caught.exception.source,str(path))
        self.assertIn('message-clean.asc',str(caught.exception.hint))
