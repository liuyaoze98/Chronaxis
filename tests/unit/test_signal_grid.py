"""用独立手算验证离线网格，不用被测线性函数生成预期值。

覆盖不等距权重、精确实点、缺口、跨批/文件不重置、同刻策略、两后端及有限
内存/取消。真实导出同时保留原状态表和连续量网格表，明确区分原始和估计值。
"""

import csv
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
import numpy as np

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import Interval
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.core.export_interpolation import linear_reference, linear_numpy
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.signal_grid import SignalGridSpec, SignalGrid
from chronaxis.results.signal_exports import SignalCSVExportSpec, export_signal_csv
from test_signal_exports import sample


class SignalGridTests(unittest.TestCase):
    """每次独立网格状态；真值按时间差手算，输入原记录不得移动或修改。"""

    def setUp(self):
        """建立绑定和工作目录。参数: 无。返回: None。异常: I/O/静态声明错。
        """
        self.definition=SignalDefinition('voltage','bus','字段,"含逗号"',D.FLOAT64,'V',1000)
        self.budget=ResourceBudget()
        self.root=Path('work/m3-input-home-20261023/signal-grid-tests')/uuid4().hex
        self.root.mkdir(parents=True)

    def grid(self,records,*,backend='numpy',period=10,origin=0,gap=110,domain=None,policy='error'):
        """耗尽有限样例网格。参数: records及网格/后端/策略覆盖。返回: GridRow列表。异常: 原网格错。
        """
        owner=SignalGrid(SignalGridSpec(('voltage',),period,origin,gap),
            (replace(self.definition,same_time_policy=policy),),domain or Interval(0,161),self.budget,backend=backend)
        try:
            rows=[]
            for record in records:
                rows.extend(owner.push(record))
            rows.extend(owner.finish())
            return rows
        finally:
            owner.close()

    def test_linear_non_midpoint_real_points_and_missing_sides(self):
        """10→120在100处为100，非平均65；真实点无需另一侧。参数: 无。返回: None。异常: 断言失败。
        """
        for backend in ('reference','numpy'):
            rows=self.grid([sample(10,10.0),sample(120,120.0,sequence=1)],backend=backend)
            indexed={r.time_ns:r for r in rows}
            self.assertEqual(indexed[100].value,100.0)
            self.assertEqual(indexed[100].status,'estimated')
            self.assertEqual((indexed[100].left.time_ns,indexed[100].right.time_ns),(10,120))
            self.assertEqual(indexed[0].reason,'missing_left')
            self.assertEqual(indexed[130].reason,'missing_right')
            self.assertEqual((indexed[10].status,indexed[120].status),('observed','observed'))
            self.assertEqual(self.budget.ram_bytes,0)

    def test_invalid_middle_update_blocks_both_neighbor_intervals(self):
        """不能越过60处无效更新拿10和120插值。参数: 无。返回: None。异常: 断言失败。
        """
        rows=self.grid([sample(10,10.0),sample(60,None,sequence=1,quality=Q.MISSING),sample(120,120.0,sequence=2)])
        indexed={r.time_ns:r for r in rows}
        self.assertEqual(indexed[50].reason,'invalid_neighbor')
        self.assertEqual(indexed[60].reason,'invalid_update')
        self.assertEqual(indexed[100].reason,'invalid_neighbor')
        self.assertEqual((indexed[120].value,indexed[120].status),(120.0,'observed'))

    def test_gap_limit_does_not_hide_exact_observation(self):
        """间隔超限只拒估计，精确命中仍使用实值。参数: 无。返回: None。异常: 断言失败。
        """
        indexed={r.time_ns:r for r in self.grid([sample(10,10.0),sample(120,120.0,sequence=1)],gap=109)}
        self.assertEqual(indexed[100].reason,'gap_too_large')
        self.assertEqual(indexed[10].value,10.0)
        self.assertEqual(indexed[120].value,120.0)

    def test_same_time_policy_and_same_facts(self):
        """默认冲突留明确缺值；last按原序号而非到达次序。参数: 无。返回: None。异常: 断言失败。
        """
        records=[sample(10,10.0,sequence=10),sample(10,90.0,sequence=3),sample(20,20.0,sequence=11)]
        indexed={r.time_ns:r for r in self.grid(records,period=5,domain=Interval(10,21))}
        self.assertEqual(indexed[10].reason,'same_time_conflict')
        self.assertEqual(indexed[15].reason,'same_time_conflict')
        rows=self.grid(records,period=5,domain=Interval(10,21),policy='last_by_sequence')
        self.assertEqual([r.value for r in rows],[10.0,15.0,20.0])
        same=self.grid([sample(10,10.0),sample(10,10.0,sequence=1)],domain=Interval(10,11))
        self.assertEqual((same[0].status,same[0].left.sequence),('observed',1))

    def test_global_grid_negative_times_large_times_and_half_open(self):
        """非零起点/负坐标和大整数坐标都按全局网格，范围外不借样本。参数: 无。返回: None。异常: 断言失败。
        """
        rows=self.grid([sample(-11,-11.0),sample(9,9.0,sequence=1)],origin=3,domain=Interval(-12,10))
        self.assertEqual([r.time_ns for r in rows],[-7,3])
        self.assertEqual([r.value for r in rows],[-7.0,3.0])
        base=2**53+1
        rows=self.grid([sample(base,10.0),sample(base+110,120.0,sequence=1)],origin=base,domain=Interval(base,base+111))
        self.assertEqual(rows[10].time_ns,base+100)
        self.assertEqual(rows[10].value,110.0)
        outside=self.grid([sample(0,0.0),sample(120,120.0,sequence=1)],domain=Interval(10,120))
        self.assertTrue(all(r.reason=='no_observation' for r in outside))

    def test_independent_numeric_backends_and_extreme_finite_values(self):
        """非二进制小数、大数两侧及整数值分别核数值，不发生端点相减溢出。参数: 无。返回: None。异常: 断言失败。
        """
        cases=[((1,3,7),0,10,0.1,0.7,(0.16,0.28,0.52)),
               ((1,2,3),0,4,-1.7e308,1.7e308,(-8.5e307,0.0,8.5e307)),
               ((1,2,3),0,4,1,2,(1.25,1.5,1.75))]
        for args in cases:
            for kernel in (linear_reference,linear_numpy):
                actual=kernel(*args[:-1])
                np.testing.assert_allclose(actual,args[-1],rtol=1e-14,atol=0)
                self.assertTrue(np.all(np.isfinite(actual)))

    def test_actual_csv_separates_state_rows_and_grid_with_metadata(self):
        """状态仍在5/65的原表，电压在独立网格表带两端证据。参数: 无。返回: None。异常: 断言失败。
        """
        records=[sample(5,True,name='state',dtype=D.BOOL),sample(10,10.0,sequence=1),
                 sample(65,False,name='state',dtype=D.BOOL,sequence=2),sample(120,120.0,sequence=3)]
        spec=SignalCSVExportSpec(('voltage','state'),SignalGridSpec(('voltage',),10,0,110))
        outputs=[]
        for backend in ('reference','numpy'):
            path=export_signal_csv(iter(records),spec,Interval(0,131),self.root/backend,self.budget,
                device_label='home',definitions=(self.definition,),backend=backend)
            with (path/'original.csv').open(encoding='utf-8',newline='') as stream:
                original=list(csv.DictReader(stream))
            self.assertEqual([r['time_ns'] for r in original],['5','65'])
            with (path/'resampled.csv').open(encoding='utf-8',newline='') as stream:
                grid=list(csv.DictReader(stream))
            outputs.append(grid)
            row=next(r for r in grid if r['time_ns']=='100')
            self.assertEqual((row['value'],row['status'],row['left_time_ns'],row['right_time_ns']),('100.0','estimated','10','120'))
            manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
            self.assertFalse(manifest['resampling']['causal'])
            self.assertEqual(manifest['resampled_counts'],{'estimated':10,'observed':2,'missing':2})
            self.assertEqual(self.budget.ram_bytes,0)
        self.assertEqual(outputs[0],outputs[1])

    def test_empty_grid_and_cancel_during_many_grid_points(self):
        """空输入给no_observation，不补零；大网格块间能取消且不发布。参数: 无。返回: None。异常: 断言失败。
        """
        rows=self.grid([],domain=Interval(0,20))
        self.assertEqual([r.reason for r in rows],['no_observation','no_observation'])
        cancel=Mock(side_effect=[None,KeyboardInterrupt('stop')])
        spec=SignalCSVExportSpec(('voltage',),SignalGridSpec(('voltage',),1,0,10))
        with self.assertRaises(KeyboardInterrupt):
            export_signal_csv([],spec,Interval(0,1000),self.root/'cancel',self.budget,device_label='home',
                              definitions=(self.definition,),check_cancel=cancel)
        self.assertFalse((self.root/'cancel').exists())
        self.assertEqual(self.budget.ram_bytes,0)

    def test_memory_stays_bounded_as_history_grows(self):
        """20与2000更新不累积全历史，只保相邻两组及当前块。参数: 无。返回: None。异常: 断言失败。
        """
        peaks=[]
        for count in (20,2000):
            budget=ResourceBudget()
            owner=SignalGrid(SignalGridSpec(('voltage',),1,0,10),(self.definition,),Interval(0,count),budget)
            try:
                for t in range(count):
                    for row in owner.push(sample(t,float(t),sequence=t)):
                        self.assertEqual(row.status,'observed')
                for row in owner.finish():
                    self.assertEqual(row.status,'observed')
                peaks.append(budget.snapshot()['peak_ram_estimated_bytes'])
            finally:
                owner.close()
            self.assertEqual(budget.ram_bytes,0)
        self.assertLess(peaks[1]-peaks[0],65536)

    def test_static_invalid_classification_and_order_rejected(self):
        """bool不能声明连续量，回退不能排序掩盖。参数: 无。返回: None。异常: 断言失败。
        """
        definition=SignalDefinition('state','bus','state',D.BOOL,'1',10)
        with self.assertRaises(ValueError):
            SignalGrid(SignalGridSpec(('state',),1,0,10),(definition,),Interval(0,10),self.budget)
        with self.assertRaisesRegex(ValueError,'回退'):
            self.grid([sample(20,20.0),sample(10,10.0,sequence=1)])
        self.assertEqual(self.budget.ram_bytes,0)

    def test_failed_history_closes_both_csv_handles_and_grid_state(self):
        """两张表同时打开后输入失败，所有实际句柄及样本费用仍回收。参数: 无。返回: None。异常: 断言失败。
        """
        streams=[]; original=Path.open
        def opened(path,*args,**kwargs):
            """记录真实输出句柄。参数: path及open参数。返回: 真实流。异常: 原I/O错。
            """
            stream=original(path,*args,**kwargs)
            if path.suffix=='.csv':
                streams.append(stream)
            return stream
        def records():
            """先产生两表内容再报错。参数: 无。返回: 样本迭代。异常: OSError故障注入。
            """
            yield sample(0,0.0)
            yield sample(1,True,name='state',dtype=D.BOOL,sequence=1)
            yield sample(10,10.0,sequence=2)
            yield sample(20,20.0,sequence=3)
            raise OSError('历史尾部损坏')
        spec=SignalCSVExportSpec(('voltage','state'),SignalGridSpec(('voltage',),1,0,10))
        with patch.object(Path,'open',autospec=True,side_effect=opened):
            with self.assertRaisesRegex(OSError,'历史尾部损坏'):
                export_signal_csv(records(),spec,Interval(0,30),self.root/'failed',self.budget,
                    device_label='home',definitions=(self.definition,))
        self.assertEqual(len(streams),2)
        self.assertTrue(all(stream.closed for stream in streams))
        self.assertEqual(self.budget.ram_bytes,0)
        self.assertFalse((self.root/'failed').exists())
