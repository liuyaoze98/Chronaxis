"""用独立手算核实逐帧累计、类型检查与方向的先后关系。"""

import ast
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from chronaxis.fast.compute import prepare_metric, encode_program


def metric(expression='p * period', dtype='float64', **extra):
    """构造以当前帧 Power 为唯一源的低层固定口径指标。"""
    return prepare_metric(dict(name='energy', unit='J', expr=expression,
        signals={'p': dict(signal='Power', dtype=dtype)}, parameters={'period': .1}, **extra))


class FastComputeTests(unittest.TestCase):
    """每个输入 dict 是独立一条已匹配报文，不依赖帧时间进行去重。"""

    def test_same_time_state_and_order(self):
        """文件重复运行应各得800J；改变加法顺序会改变抵消后的结果。"""
        for unused in range(2):
            energy = metric()
            self.assertIsNone(energy.result()['value'])
            with patch.object(ast, 'parse', side_effect=AssertionError('逐帧重新解析')):
                for frame in ({'Power':4000}, {'Power':4000}):
                    energy.consume(frame)
            self.assertEqual(energy.result()['value'], 800.)
        energy = metric('p')
        for power in (1e16, 1., -1e16):
            energy.consume({'Power':power})
        self.assertEqual((energy.result()['value'],energy.result()['reason']), (0.,None))

    def test_fail_before_direction_and_do_not_bucket_engineering_value(self):
        """反向帧公式先算；方向使用未应用用户翻转的物理值。"""
        direction = dict(signal='Power', bucket='positive')
        divide = metric('1 / (p + 1)', direction=direction)
        with self.assertRaises(ZeroDivisionError):
            divide.consume({'Power':-1})
        energy = prepare_metric(dict(name='x',unit='A',expr='p',
            signals={'p':dict(signal='Power',dtype='float64',scale=-1)},
            direction=direction))
        for power in (-1, 0):
            energy.consume({'Power':power})
        self.assertEqual((energy.result()['value'],energy.result()['reason']), (0.,'no_selected_direction'))
        energy.consume({'Power':12})
        self.assertEqual(energy.result()['value'], -12.)

    def test_unit_conversion_inside_expression_and_business_factor(self):
        """4kW+500W，乘0.1s并应用独立效率0.95。"""
        def node(op, *children, value=None, name=None):
            return SimpleNamespace(operator=op, dtype=SimpleNamespace(value='float64'), args=children,
                                   value=value, name=name)
        first=node('unit_convert',node('name',name='kw'), value=(1000,0))
        add=node('add',first,node('name',name='w'))
        program=encode_program(node('mul',node('mul',add,node('const',value=.1)),node('const',value=.95)))
        energy=prepare_metric(dict(name='e',unit='J',expr='(kw + w) * .1 * .95',
            signals={k:dict(signal=k,dtype='float64') for k in ('kw','w')},program=program))
        energy.consume({'kw':4,'w':500})
        self.assertEqual(energy.result()['value'],427.5)

    def test_numerical_failures(self):
        """中间整数超限、转浮点失真、累计溢出、坏解码值不能变为零。"""
        for expr,val,dtype in [('(p+1)-1',2**63-1,'int64'),('abs(p)',-2**63,'int64'),
                               ('p',2**53+1,'int64'),('-p',1,'uint64'),('p',True,'float64'),
                               ('p',float('nan'),'float64'),('p',None,'float64')]:
            with self.subTest(expr=expr, value=val), self.assertRaises(ValueError):
                metric(expr,dtype).consume({'Power':val})
        large = metric('p')
        large.consume({'Power':1e308})
        with self.assertRaises(ValueError):
            large.consume({'Power':1e308})
        with self.assertRaises(KeyError):
            metric().consume({})

    def test_unsupported_source_and_program(self):
        """即使提供编译指令，用户算式的禁用语法仍在开始前拒绝。"""
        for expr in ('p > 0', 'p and p', 'p[0]', 'object.method()', 'abs(p,p)', 'True', 'p**2',
                     '(lambda: 1)()', 'unknown', '__import__("os")'):
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                metric(expr,program={'op':'const','dtype':'float64','value':0.})
        with self.assertRaises(ValueError):
            metric(program={'op':'lookup','dtype':'float64','args':[]})
