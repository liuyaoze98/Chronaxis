"""从独立手算值核对 B4 数学函数的表达式编译及两套后端。

合成输入包括不同单位、精度边界、非有限原始值与未知样本。直接数值核
另用混合质量列验证动界倒置、整型开方和负零。全部数据只存在于内存。
"""

import math
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest
import numpy as np
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core import SignalDefinition
from chronaxis.core.expression import compile_expression
from chronaxis.core.expression_math_numpy import math_numpy
from chronaxis.core.expression_math_reference import math_reference
from chronaxis.core.expression_numpy import evaluate_memory_numpy
from chronaxis.core.expression_reference import evaluate_memory_reference
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from test_expression import _bindings, _column
from test_expression_units_v4 import bindings


class MathKernelTests(unittest.TestCase):
    """以数值内核直接核对质量并集、逐行动态边界及精度检查。"""

    def check_rows(self, name, rows, values, flags):
        """对同一批次做逐行参考与整列计算，分别核对独立期望。

        参数: name为函数名，rows为typed数值参数行，values/flags为手算结果。
        返回: NumPy结果列，供检查符号等表示。异常: 任一差异由断言报告。
        """
        result = math_numpy(name,tuple(_column(col) for col in zip(*rows)))
        scalar = [math_reference(name,row) for row in rows]
        self.assertEqual([x.value for x in scalar], values)
        self.assertEqual([x.quality for x in scalar], flags)
        self.assertEqual(result.quality.tolist(),list(map(int,flags)))
        self.assertEqual(result.values[result.valid].tolist(),[x for x in values if x is not None])
        return result

    def test_dynamic_clip_and_quality_union(self):
        """倒置边界单独报域错误，同时保留任一必要输入的无效原因。

        参数: 无。返回: None。异常: 动界位置或质量合并错误则失败。
        """
        s = lambda number: ScalarValue(number,D.INT64)
        missing = ScalarValue(None,D.INT64,False,Q.MISSING)
        stale = ScalarValue(None,D.INT64,False,Q.STALE)
        rows = [(s(5),s(1),s(3)), (s(0),s(1),s(2)), (s(6),s(8),s(8)),
                (s(5),s(3),s(2)), (missing,s(3),s(2)), (s(7),stale,missing)]
        self.check_rows('clip',rows,[3,1,8,None,None,None],
                        [Q.NONE,Q.NONE,Q.NONE,Q.DOMAIN_ERROR,Q.MISSING|Q.DOMAIN_ERROR,Q.STALE|Q.MISSING])

    def test_sqrt_precision_domain_and_signed_zero(self):
        """可精确整型开方，负值与非负大整数分别有明确原因。

        参数: 无。返回: None。异常: 隐式舍入、异常质量或符号错误时失败。
        """
        ints = [(ScalarValue(v,D.INT64),) for v in (0,16,2**60,2**53+1,-(2**53+1))]
        self.check_rows('sqrt',ints,[0.,4.,2.**30,None,None],
                        [Q.NONE,Q.NONE,Q.NONE,Q.PRECISION_LOSS,Q.DOMAIN_ERROR])
        for name in ('minimum','maximum'):
            rows = [(ScalarValue(v,D.FLOAT64),ScalarValue(-v,D.FLOAT64)) for v in (0.,-0.)]
            out = self.check_rows(name,rows,[0.,-0.],[Q.NONE,Q.NONE])
            self.assertEqual(np.signbit(out.values).tolist(),[False,True])
            self.assertEqual([math.copysign(1,math_reference(name,row).value) for row in rows],[1.,-1.])


class MathExpressionTests(unittest.TestCase):
    """逐层核对公开编译入口、原始数值归一化、单位、结果类型与质量。"""

    def check(self, expr, data, expected, unit, dtype, quality=Q.NONE):
        """让相同原输入分别经公开reference和NumPy内存求值。

        参数: expr/data为源表达式与绑定，其他参数为显式手算验收值。
        返回: None。异常: 编译、dtype、单位、结果或诊断偏差触发失败。
        """
        tree = compile_expression(expr,data)
        self.assertEqual((tree.root.unit,tree.root.dtype),(unit,dtype))
        ref = evaluate_memory_reference(tree,(0,))[0]
        arr = evaluate_memory_numpy(tree,np.array([0],dtype=np.int64))
        self.assertEqual((ref.value.quality,ref.dependency_quality),(quality,quality))
        self.assertEqual((arr.value.quality.tolist(),arr.dependency_quality.tolist()),([int(quality)],[int(quality)]))
        self.assertEqual(ref.value.value,expected)
        if expected is not None:
            self.assertEqual(arr.value.values.tolist(),[expected])

    def test_common_units_literals_temperature_and_unknowns(self):
        """兼容输入换算、裸常量锚点、缺失及绝对温度按同一物理量比较。

        参数: 无。返回: None。异常: 任一物理量/样本质量与手算不符则失败。
        """
        data = bindings(('a','V',1.),('b','mV',500.),('c','V',2.),('bad','V',float('nan')))
        for text,expected in (('minimum(a,b,c)',.5), ('maximum(b,a,c)',2.),
                              ('minimum(b,250)',.25), ('clip(b,0,250)',.25),
                              ('clip(a,quantity(800,"mV"),quantity(2,"V"))',1.),
                              ('maximum(b,a,quantity(250,"mV"))',1.)):
            with self.subTest(text=text):
                self.check(text,data,expected,'V',D.FLOAT64)
        self.check('minimum(a,b,bad)',data,None,'V',D.FLOAT64,Q.NONFINITE)
        temp = bindings(('c','degC',25.),('k','K',280.))
        self.check('minimum(c,k)',temp,280.,'K',D.FLOAT64)
        self.check('clip(c,0,20)',temp,293.15,'K',D.FLOAT64)

    def test_power_units_and_boundaries(self):
        """开方以规范尺度计算；平方复用定宽溢出及非有限质量。

        参数: 无。返回: None。异常: 忽略倍率、偏移或转换精度时失败。
        """
        data = bindings(('mixed','mA*A',9000.),('ma','mA',2000),
                        ('neg','A^2',-1),('huge','1',2**53+1),('lo','1',-(2**63)),('large','1',1e300))
        for text,value,unit,dtype,flag in (
                ('sqrt(mixed)',3.,'A',D.FLOAT64,Q.NONE),
                ('square(ma)',4.,'A^2',D.FLOAT64,Q.NONE),
                ('sqrt(square(ma))',2.,'A',D.FLOAT64,Q.NONE),
                ('sqrt(neg)',None,'A',D.FLOAT64,Q.DOMAIN_ERROR),
                ('sqrt(huge)',None,'1',D.FLOAT64,Q.PRECISION_LOSS),
                ('square(lo)',None,'1',D.INT64,Q.OVERFLOW),
                ('abs(lo)',None,'1',D.INT64,Q.OVERFLOW),
                ('square(large)',None,'1',D.FLOAT64,Q.NONFINITE)):
            with self.subTest(text=text):
                self.check(text,data,value,unit,dtype,flag)
        # UINT64平方仍使用无符号上限，极值也不能先转float丢掉低位。
        unsigned = _bindings(rows=({'raw':2**32},),
                             definitions=(SignalDefinition('u','sensor','raw',D.UINT64,'1',2,config_version=4),))
        self.check('square(u)',unsigned,None,'1',D.UINT64,Q.OVERFLOW)
        self.check('maximum(u,18446744073709551615)',unsigned,2**64-1,'1',D.UINT64)

    def test_static_rejections_and_legacy(self):
        """静态拒绝错签名、裸数歧义、越界、不可开方单位和已知倒置。

        参数: 无。返回: None。异常: 未拒绝非法输入、错误地接受旧版新函数则失败。
        """
        data = bindings(('a','V',1.),('b','mV',500.),('t','degC',10.),('i','V',2))
        for text in ('minimum(a)', 'maximum(a,b,b=2)', 'clip(a,2,1)',
                     'clip(a,maximum(1,2),1)', 'clip(a,quantity(1001,"mV"),quantity(1,"V"))',
                     'minimum(a,b,3.2)', 'minimum(3.2,b,a)', 'clip(b,0,a)',
                     'minimum(a,i,1.)', 'clip(True,0,2)', 'minimum(t,a)', 'square(t)',
                     'sqrt(t)', 'sqrt(a)', 'square(18446744073709551616)', 'sqrt(abs(18446744073709551616))'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                compile_expression(text,data)
        # 当前函数名不可作为信号别名；旧配置版本在入口明确拒绝。
        with self.assertRaisesRegex(ValueError,'clip'):
            compile_expression('1',bindings(('clip','A',3.)))

    def test_public_mean_and_selection(self):
        """运行公开配置，以同一功率列验证逐点函数、样本均值和选择行。

        参数: 无。返回: None。异常: 两个后端的范围、单位或结果不符则失败。
        """
        from test_units_v4_runner import UnitsV4RunnerTests
        for backend in ('reference','numpy'):
            config = UnitsV4RunnerTests().config(backend)
            # 复用半开范围内的1、3kW数据；截到[1250,2000]W得均值1.625kW。
            config['calculations'] = [
                dict(name='mean',operation='sample_mean',unit='kW',
                     expr='minimum(maximum(sqrt(square(power)),quantity(1250,"W")),quantity(2000,"W"))'),
                dict(name='rows',operation='select',unit='kW',expr='clip(power,1.25,2)')]
            with self.subTest(backend=backend), TemporaryDirectory(dir='work',prefix='math-v4-') as folder:
                plan = AnalysisPlan.from_dict(config)
                with AnalysisRunner().run(plan,work_dir=Path(folder)/'run') as result:
                    mean = next(r for r in result.iter_calculations() if r.calculation_id == 'mean')
                    self.assertEqual((mean.value,mean.unit),(1.625,'kW'))
                    self.assertEqual([(r.value,r.unit) for r in result.iter_selections()],
                                     [(1.25,'kW'),(2.,'kW')])
