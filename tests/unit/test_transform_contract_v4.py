"""D1 验证离散网格与物理时间的关系、拓扑顺序、预算和原更新投影。"""
from fractions import Fraction
import unittest
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.transform_window import TransformSpan, TransformWindow, first_grid
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError


class TransformContractTests(unittest.TestCase):
    """手算覆盖两个原周期内的窗口，确保网格没有成为第三条驱动记录。"""

    def test_fixed_grid_between_two_records_uses_exact_overlap(self):
        """参数: 无。返回: 无。异常: 锚点、分摊或退款错误。"""
        budget=ResourceBudget()
        window=TransformWindow(budget,100,100)
        self.addCleanup(window.close)
        for left,right,x in ((10000,10120,10.),(10120,10300,20.)):
            value=ScalarValue(x,D.FLOAT64)
            window.append(TransformSpan(left,right,value,None,True,value))
        parts=[(s.value.value,(right-left)*ratio) for s,left,right,ratio in window.slices(10200)]
        self.assertEqual(parts,[(20.,Fraction(400,9)),(10.,Fraction(500,9))])
        self.assertEqual(first_grid(-11,0,5),-10)
        self.assertEqual(first_grid(10121,10000,100),10200)
        window.trim()
        self.assertEqual(len(window.spans),1)
        window.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_dense_history_fails_before_retaining_extra_span(self):
        """参数: 无。返回: 无。异常: 超预算部分安装或关闭后留账。"""
        budget=ResourceBudget(2048)
        window=TransformWindow(budget,10,None)
        self.addCleanup(window.close)
        value=ScalarValue(2.,D.FLOAT64)
        with self.assertRaises(BudgetExceededError):
            for t in range(3):
                window.append(TransformSpan(t,t+1,value,None,True,value))
        self.assertEqual(len(window.spans),2)
        window.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_planned_transforms_are_bounded_and_unrequested_series_do_not_open(self):
        """参数: 无。返回: 无。异常: 配置容量、静态依赖图或按需投影错误。"""
        from chronaxis import AnalysisPlan
        from chronaxis.planning.input_requirements import collect_input_requirements
        raw=dict(config_version=4,dataset=dict(name='grid'),sources=[dict(name='table',source_type='memory',
            rows=[dict(time='0s',values={'v':1.})])],signals=[dict(name='v',field='v',unit='V',
            dtype='float64',valid_for='2s')],calculations=[dict(name='plain',operation='sample_count',expr='v')])
        for size in (0,64,65):
            raw['transforms']=[dict(name=f'grid{i}',operation='rolling_minimum',expr='v',step='1s',window='1s')
                               for i in range(size)]
            if size<=64:
                plan=AnalysisPlan.from_dict(raw)
                self.assertEqual(len(plan.transforms),size)
                self.assertEqual(collect_input_requirements(plan).transform_names,())
            else:
                with self.assertRaises(ValueError):
                    AnalysisPlan.from_dict(raw)
