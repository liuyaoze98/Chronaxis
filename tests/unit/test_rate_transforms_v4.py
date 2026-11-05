"""用斜坡、温度和精度边界核对三种变化率的独立标量/数组实现。

时间均显式为纳秒，周期内的位置允许Fraction。这里仅测试数值含义，
真实调度、驱动归属和观测边界由对应的Runner测试覆盖。
"""
from fractions import Fraction
import unittest
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.rate_transforms import rate_difference, rate_fit, rate_unit
from chronaxis.core.types import QualityFlag as Q, SignalDType as D


class RateKernelTests(unittest.TestCase):
    """逐后端检验不同变化率、局部时间、质量和自然单位。"""

    def test_temperature_definitions_and_cycle_axis(self):
        """确认相邻、端点和点拟合分别为2.5、2、29/14温差每秒。

        参数: 无。返回: None。异常: 混用原时间与周期或给端点补权重时失败。
        """
        values = tuple(ScalarValue(k,D.FLOAT64) for k in (20.,21.,26.))
        for backend in ('reference','numpy'):
            self.assertEqual(rate_difference(backend,*values[1:],2_000_000_000).value,2.5)
            self.assertEqual(rate_difference(backend,values[0],values[-1],3_000_000_000).value,2.)
            self.assertAlmostEqual(rate_fit(backend,(0,10**9,3*10**9),values).value,29/14)
            # 如改按每次真实报文100ms，最后两点跨一个周期，端点跨两个周期。
            self.assertEqual(rate_difference(backend,*values[1:],100_000_000).value,50.)
            self.assertEqual(rate_difference(backend,values[0],values[-1],200_000_000).value,30.)
            self.assertAlmostEqual(rate_fit(backend,(0,100_000_000,200_000_000),values).value,30.)
        for source,target in (('degC','delta_K/s'),('K','delta_K/s'),('mV','mV/s'),('1','Hz')):
            self.assertEqual(rate_unit(source),target)
        with self.assertRaises(ValueError):
            rate_unit('unregistered_voltage')

    def test_relative_integers_and_fractional_coordinates(self):
        """大整数直流背景与大纪元纳秒都先减原点，允许负的无符号输入变化率。

        参数: 无。返回: None。异常: 提前舍入、整数回绕或丢亚纳秒周期折算时失败。
        """
        values = tuple(ScalarValue(2**63+k,D.UINT64) for k in (4,3,2))
        base = 2**63-5
        for backend in ('reference','numpy'):
            self.assertEqual(rate_difference(backend,values[0],values[1],1).value,-1e9)
            self.assertAlmostEqual(rate_fit(backend,(base,base+1,base+2),values).value,-1e9)
            axis = (Fraction(base), Fraction(base)+Fraction(2,3), Fraction(base)+Fraction(4,3))
            self.assertAlmostEqual(rate_fit(backend,axis,values).value,-1.5e9)
            self.assertEqual(rate_difference(backend,values[0],values[1],Fraction(2,3)).value,-1.5e9)

    def test_numerical_quality_and_invalid_coordinates(self):
        """合并无效输入，拒绝零/负跨度、未原子化同刻、未知类型及有损整数差。

        参数: 无。返回: None。异常: 在非法坐标上产生正常斜率或质量丢失时失败。
        """
        a, b = ScalarValue(0,D.INT64), ScalarValue(2**53+1,D.INT64)
        for backend in ('reference','numpy'):
            for delta in (0,-1):
                self.assertEqual(rate_difference(backend,a,b,delta).quality,Q.DOMAIN_ERROR)
            for axis in ((0,0),(7,3)):
                self.assertEqual(rate_fit(backend,axis,(a,b)).quality,Q.DOMAIN_ERROR)
            self.assertEqual(rate_fit(backend,(1,),(a,)).quality,Q.MISSING)
            stale = ScalarValue(None,D.INT64,False,Q.STALE)
            self.assertEqual(rate_difference(backend,stale,b,10**9).quality,Q.STALE)
            self.assertEqual(rate_fit(backend,(1,2),(a,stale)).quality,Q.STALE)
            self.assertEqual(rate_difference(backend,a,b,10**9).quality,Q.PRECISION_LOSS)
            self.assertEqual(rate_fit(backend,(1,2),(a,b)).quality,Q.PRECISION_LOSS)
            # 异号差达到3.4e308，但除以2秒后的最终值有限，不能在中间提前溢出。
            extreme = (ScalarValue(-1.7e308,D.FLOAT64),ScalarValue(1.7e308,D.FLOAT64))
            self.assertEqual(rate_difference(backend,*extreme,2*10**9).value,1.7e308)
            self.assertEqual(rate_fit(backend,(0,2*10**9),extreme).value,1.7e308)
            self.assertEqual(rate_difference(backend,*extreme,1).quality,Q.NONFINITE)
