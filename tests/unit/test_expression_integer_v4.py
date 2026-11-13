"""验证v4精确cast、取余与位选择的公开语义及两套独立数值实现。

输入覆盖64位上下限、零除、跨符号转换与mV尺度选择。所有期望均直接
由整数/物理量定义给出，参考与NumPy独立对照。数据不依赖日志或DBC。
"""

from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest
import numpy as np
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core import SignalDefinition
from chronaxis.core.expression import compile_expression
from chronaxis.core.expression_numpy import evaluate_numpy
from chronaxis.core.expression_reference import evaluate_reference
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from test_expression import _bindings, _column


def word_bindings():
    """建立有符号、无符号、纯浮点和带物理单位的真实内存绑定。

    参数: 无。返回: 带版本4的SignalBindings。异常: 来源模型校验错误直接传播。
    """
    specs = (('i',D.INT64,'1'),('j',D.INT64,'1'),('u',D.UINT64,'1'),
             ('f',D.FLOAT64,'1'),('v',D.INT64,'mV'),('percent',D.INT64,'%'))
    definitions = tuple(SignalDefinition(k,'sensor',k,d,u,2,config_version=4) for k,d,u in specs)
    return _bindings(rows=({k:1 for k,_,_ in specs},),definitions=definitions)


class IntegerExpressionTests(unittest.TestCase):
    """逐行核对每个边界的值/质量/单位/目标类型，并从计划验证流式执行。"""

    def check(self, text, data, expected, flags, dtype, unit='1'):
        """将指定列作为同一输入交给两个后端，分开核对手算结果。

        参数: text为DSL；data按别名给出同长原值或显式无效ScalarValue列；
            expected/flags/dtype/unit为期望，None表示无效。
        返回: None。异常: 编译、结果或原因偏差由断言报告。
        """
        bindings = word_bindings()
        expr = compile_expression(text,bindings)
        self.assertEqual((expr.root.dtype,expr.root.unit),(dtype,unit))
        context = {name:[value if isinstance(value,ScalarValue) else ScalarValue(value,bindings.resolve(name).dtype)
                         for value in data[name]] for name in expr.dependencies}
        refs = [evaluate_reference(expr,{k:v[n] for k,v in context.items()},bindings) for n in range(len(expected))]
        arr = evaluate_numpy(expr,{k:_column(v) for k,v in context.items()},bindings,size=len(expected))
        self.assertEqual([v.value.value if v.value.valid else None for v in refs],expected)
        self.assertEqual([v.value.quality for v in refs],flags)
        self.assertEqual([v.dependency_quality for v in refs],flags)
        self.assertEqual(arr.value.quality.tolist(),list(map(int,flags)))
        self.assertEqual(arr.dependency_quality.tolist(),list(map(int,flags)))
        self.assertEqual(arr.value.values[arr.value.valid].tolist(),[v for v in expected if v is not None])

    def test_remainder_sign_zero_minimum_and_unknown(self):
        """余数随除数符号，最小负数模负一为零，0除和未知各有原因。

        参数: 无。返回: None。异常: 质量/值不符或依赖硬件整数除法溢出时失败。
        """
        missing = ScalarValue(None,D.INT64,False,Q.MISSING)
        self.check('mod(i,j)',{'i':[-5,5,-5,-(2**63),1,missing], 'j':[3,-3,-3,-1,0,0]},
                   [1,-1,-2,0,None,None],[Q.NONE]*4+[Q.DOMAIN_ERROR,Q.MISSING],D.INT64)
        self.check('mod(u,3)',{'u':[2**64-1,2**63+1]},[0,0],[Q.NONE]*2,D.UINT64)
        self.check('mod(to_uint64(i),u)',{'i':[7,-1], 'u':[4,3]},[3,None],[Q.NONE,Q.OVERFLOW],D.UINT64)

    def test_bits_are_exact_twos_complement(self):
        """覆盖符号位、最低位、取全64位及编译期宽度表达式。

        参数: 无。返回: None。异常: 符号右移、隐式浮点或错位掩码改变结果则失败。
        """
        data = {'i':[-(2**63),-1,1]}
        self.check('bit_test(i,63)',data,[True,True,False],[Q.NONE]*3,D.BOOL)
        self.check('bit_extract(i,0,64)',data,[2**63,2**64-1,1],[Q.NONE]*3,D.UINT64)
        self.check('bit_extract(i,60,2+2)',data,[8,15,0],[Q.NONE]*3,D.UINT64)
        self.check('bit_test(u,0)',{'u':[2**63+1,2**63]},[True,False],[Q.NONE]*2,D.BOOL)

    def test_float_edges_and_exact_casts(self):
        """比较float64可精确表示的开区间端点，检查分数和跨符号范围。

        参数: 无。返回: None。异常: 截断小数、负数wrap或放行上界即失败。
        """
        max_float_signed = float(np.nextafter(2.**63,0.))
        max_float_unsigned = float(np.nextafter(2.**64,0.))
        self.check('to_int64(f)',{'f':[-2.**63,max_float_signed,2.**63,-.5]},
                   [-(2**63),int(max_float_signed),None,None],[Q.NONE,Q.NONE,Q.OVERFLOW,Q.PRECISION_LOSS],D.INT64)
        self.check('to_uint64(f)',{'f':[max_float_unsigned,2.**64,-1.,-0.]},
                   [int(max_float_unsigned),None,None,0],[Q.NONE,Q.OVERFLOW,Q.OVERFLOW,Q.NONE],D.UINT64)
        self.check('to_int64(u)',{'u':[2**63-1,2**63]},[2**63-1,None],[Q.NONE,Q.OVERFLOW],D.INT64)
        self.check('to_float64(u)',{'u':[2**53+1,2**63,2**64-1]},[None,2.**63,None],
                   [Q.PRECISION_LOSS,Q.NONE,Q.PRECISION_LOSS],D.FLOAT64)

    def test_explicit_units_and_static_rejections(self):
        """默认转规范尺度，显式选mV时保留1500mV；错位/单位/定宽静态拒绝。

        参数: 无。返回: None。异常: 换算顺序、版本隔离或拒绝范围不符则失败。
        """
        self.check('to_int64(v)',{'v':[1500,2000]},[None,2],[Q.PRECISION_LOSS,Q.NONE],D.INT64,'V')
        self.check('to_int64(to_unit(v,"mV"))',{'v':[1500,2000]},[1500,2000],[Q.NONE]*2,D.INT64,'mV')
        for text in ('mod(i,u)','mod(u,-1)','mod(i,f)','mod(v,3)','mod(percent,2)',
                     'bit_test(i,-1)','bit_test(i,64)','bit_test(i,j)','bit_test(v,0)',
                     'bit_extract(i,0,0)','bit_extract(i,63,2)','bit_extract(i,0,64.)',
                     'to_float64(True)','to_int64(18446744073709551616)','to_int64(f,a=2)'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                compile_expression(text,word_bindings())
        # 未显式填写版本的绑定也使用当前整数能力。
        current = compile_expression('bit_test(counter,0)',_bindings())
        self.assertIs(current.root.dtype, D.BOOL)

    def test_public_cast_and_word_operations(self):
        """从公开配置输出真实选择行，串联cast、跨符号、取余及位提取。

        参数: 无。返回: None。异常: API静态编译或执行阶段遗漏任一函数时失败。
        """
        from test_units_v4_runner import UnitsV4RunnerTests
        for backend in ('reference','numpy'):
            config = UnitsV4RunnerTests().config(backend)
            config['signals'][0].update(name='counter',dtype='int64',unit='1')
            # 原数据输入为1/3/5，半开会话只选择首两行。mod(counter,3)依次为1、0。
            for row in config['sources'][0]['rows']:
                row['values']['p'] = int(row['values']['p'])
            config['calculations'] = [dict(name='bits',operation='select',
                expr='to_float64(bit_extract(to_uint64(mod(counter,3)),0,2))')]
            with self.subTest(backend=backend), TemporaryDirectory(dir='work',prefix='word-v4-') as folder:
                with AnalysisRunner().run(AnalysisPlan.from_dict(config),work_dir=Path(folder)/'run') as result:
                    self.assertEqual([row.value for row in result.iter_selections()],[1.,0.])
