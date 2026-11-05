"""用手算和活动行探针核对 v4 where 的编译、分支求值与诊断。

构造普通内存绑定并提供同一组标量/数组输入；不依赖具体车型或日志。
探针记录除法内核收到的行数，防止两条分支全量计算后才掩蔽质量。
"""

import unittest
from unittest.mock import patch
import numpy as np

from chronaxis.core import SignalDefinition, SignalDType as D, QualityFlag as Q
from chronaxis.core import expression_numpy as arr, expression_reference as ref
from chronaxis.core.expression import compile_expression
from chronaxis.core.numeric import ScalarValue
from test_expression import _bindings, _column


def where_bindings():
    """建立布尔条件及带单位数值输入的真实绑定。

    参数: 无。返回: v4内存绑定。异常: 模型或类型错误原样传播。
    """
    # 求值用显式context；原行仅建立来源和字段身份。
    specs = (('c',D.BOOL,'1'), ('x',D.FLOAT64,'mV'), ('y',D.FLOAT64,'V'),
             ('d',D.FLOAT64,'1'), ('i',D.INT64,'V'), ('ms',D.INT64,'mV'))
    definitions = tuple(SignalDefinition(k,'sensor',k,t,u,4,config_version=4) for k,t,u in specs)
    return _bindings(rows=({k:1 for k,_,_ in specs},), definitions=definitions)


class WhereValueTests(unittest.TestCase):
    """分别核对两个独立内核，含混合分支、未知与未选错误。"""

    def test_masked_arithmetic_and_diagnostics(self):
        """未选/未知行不执行除法；选择有错分支时保留具体原因。

        参数: 无。返回: None。异常: 收到的行数、结果或质量不符即断言失败。
        """
        bindings = where_bindings()
        expr = compile_expression('where(c, x, y / d)', bindings)
        self.assertEqual((expr.root.unit,expr.dependencies), ('V',('c','d','x','y')))
        # 共五行：选正常毫伏、条件过期、选零分母、选1V、选缺失毫伏。
        c = (True,None,False,False,True)
        context = {'c':[ScalarValue(v,D.BOOL) if v is not None else ScalarValue(None,D.BOOL,False,Q.STALE) for v in c],
                   'd':[ScalarValue(v,D.FLOAT64) for v in (0.,0.,0.,2.,0.)],
                   'x':[ScalarValue(500.,D.FLOAT64)]*4+[ScalarValue(None,D.FLOAT64,False,Q.MISSING)],
                   'y':[ScalarValue(2.,D.FLOAT64)]*5}
        # 探针包裹既有内核，不替换数值逻辑；两行真正进入除法。
        with patch.object(ref,'binary_reference',wraps=ref.binary_reference) as scalar_div:
            rows = [ref.evaluate_reference(expr,{k:v[n] for k,v in context.items()},bindings) for n in range(len(c))]
        with patch.object(arr,'binary_numpy',wraps=arr.binary_numpy) as array_div:
            columns = arr.evaluate_numpy(expr,{k:_column(v) for k,v in context.items()},bindings)
        self.assertEqual(scalar_div.call_count, 2)
        self.assertEqual(array_div.call_count, 1)
        self.assertEqual(len(array_div.call_args.args[1].values), 2)
        # 盲检手算输出，不用reference产生NumPy的期望。
        expected = [Q.NONE,Q.STALE,Q.DOMAIN_ERROR,Q.NONE,Q.MISSING]
        self.assertEqual([r.value.quality for r in rows], expected)
        self.assertEqual([r.dependency_quality for r in rows], expected)
        self.assertEqual(columns.value.quality.tolist(), list(map(int,expected)))
        self.assertEqual(columns.dependency_quality.tolist(), list(map(int,expected)))
        self.assertEqual([r.value.value for r in rows if r.value.valid], [0.5,1.])
        self.assertEqual(columns.value.values[columns.value.valid].tolist(), [0.5,1.])

    def test_branch_units_precision_and_nesting(self):
        """分支尺度对称，裸数按另一分支单位，精度只在活动路径检查。

        参数: 无。返回: None。异常: 单位、数值或质量改变时断言失败。
        """
        bindings = where_bindings()
        for expr_text, condition, expected, unit in (
                ('where(c, x, 500)',False,0.5,'V'), ('where(c, 500, x)',True,0.5,'V'),
                ('where(c, 1, 0)',True,1,'1'), ('where(c, ms, i)',True,0.005,'V'),
                ('where(c, ms, i)',False,None,'V'),
                ('where(c, x, where(c, x, 500.))',False,0.5,'V')):
            # 整数2^53+1进入float64会损失精度；选到其他分支时仍正常。
            expr = compile_expression(expr_text, bindings)
            values = {'c':ScalarValue(condition,D.BOOL), 'x':ScalarValue(1.,D.FLOAT64),
                      'i':ScalarValue(2**53+1,D.INT64), 'ms':ScalarValue(5,D.INT64)}
            ctx = {name:values[name] for name in expr.dependencies}
            with self.subTest(expr=expr_text,condition=condition):
                r = ref.evaluate_reference(expr,ctx,bindings)
                a = arr.evaluate_numpy(expr,{k:_column([v]) for k,v in ctx.items()},bindings)
                self.assertEqual(expr.root.unit,unit)
                quality = Q.PRECISION_LOSS if expected is None else Q.NONE
                self.assertEqual((r.value.quality,a.value.quality.tolist()),(quality,[quality]))
                if expected is not None:
                    self.assertEqual((r.value.value,a.value.values.tolist()),(expected,[expected]))

    def test_static_checks_even_when_constant_false_and_version_isolation(self):
        """未选分支仍检查类型、单位、名称、安全与整数边界；当前函数保留名不能被业务别名占用。

        参数: 无。返回: None。异常: 允许非法分支或破坏旧别名时断言失败。
        """
        bindings = where_bindings()
        for text in ('where(False, z, 1)', 'where(False, x.real, x)', 'where(x,1,2)',
                     'where(False, c, 2)', 'where(False, x, d)', 'where(c, i, y)',
                     'where(c, 1, y=2)', 'where(c,i)', 'where(False,18446744073709551616,1)',
                     'where(False, abs(18446744073709551616), y)',
                     'where(c, quantity(25,"degC"), quantity(2,"delta_K"))'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                compile_expression(text,bindings)
        # 当前where是保留函数名；不能再作为业务信号声明。
        with self.assertRaisesRegex(ValueError, 'where'):
            compile_expression('where', _bindings(definitions=(SignalDefinition('where','sensor','raw_i',D.FLOAT64,'A',2),)))

    def test_nested_subbatch_coordinates_and_known_condition_diagnostics(self):
        """嵌套条件在活动子批独立选行；已知逻辑可保留诊断而不损害覆盖。

        参数: 无。返回: None。异常: 子批次错位、重复合并质量或近似舍入时失败。
        """
        bindings = where_bindings()
        # 第三行c未知但d为正，三值or仍确定为真；第四行c为真但d未知。
        inputs = {'c':[ScalarValue(v,D.BOOL) if v is not None else ScalarValue(None,D.BOOL,False,Q.STALE)
                       for v in (True,False,None,True,False)],
                  'd':[ScalarValue(v,D.FLOAT64) if v is not None else ScalarValue(None,D.FLOAT64,False,Q.MISSING)
                       for v in (-1.,1.,1.,None,-1.)],
                  'x':[ScalarValue(500.,D.FLOAT64)]*5, 'y':[ScalarValue(2.,D.FLOAT64)]*5}
        expr = compile_expression('where(c or d>0, where(d>0, x, y), x)', bindings)
        rows = [ref.evaluate_reference(expr,{k:v[n] for k,v in inputs.items()},bindings) for n in range(5)]
        data = arr.evaluate_numpy(expr,{k:_column(v) for k,v in inputs.items()},bindings)
        expected = [2.,0.5,0.5,None,0.5]
        diagnostics = [Q.NONE,Q.NONE,Q.STALE,Q.MISSING,Q.NONE]
        self.assertEqual([r.value.value for r in rows],expected)
        self.assertEqual([r.dependency_quality for r in rows],diagnostics)
        self.assertEqual(data.value.values[data.value.valid].tolist(), [v for v in expected if v is not None])
        self.assertEqual(data.value.quality.tolist(),[0,0,0,int(Q.MISSING),0])
        self.assertEqual(data.dependency_quality.tolist(),list(map(int,diagnostics)))

    def test_empty_batch(self):
        """空数组和常量条件不强制对空分支求值。

        参数: 无。返回: None。异常: 误进入除法或输出非空则失败。
        """
        bindings = where_bindings()
        expr = compile_expression('where(False, 1/0, 1.)',bindings)
        with patch.object(arr,'binary_numpy', side_effect=AssertionError('未选除法不应执行')):
            for size in (0,3):
                result = arr.evaluate_numpy(expr,{},bindings,size=size)
                np.testing.assert_array_equal(result.value.values, np.ones(size))
