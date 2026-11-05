"""用手算滚动估值核验样本、区间、筛选及父事件向公开结果传递部分性。"""

from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from chronaxis import AnalysisPlan,AnalysisRunner
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.transform_partial import partial_in_block
from chronaxis.execution.record_value_history import RecordValueHistory
from chronaxis.results import ResourceBudget


class TransformPartialOutputsTests(unittest.TestCase):
    """前三秒输入不足与窗口输出的观测范围分别判断。"""

    def test_rate_using_estimated_right_endpoint(self):
        """前一秒为实测，右端切换为估值：report 保留 1 A/s 并标估算，strict 不给值。"""
        from test_rolling_transforms_v4 import RollingTransformsTests
        helper=RollingTransformsTests('runTest')
        raw=helper.config(((0,2.),(1,8.),(4,8.)),window='3s')
        raw['transforms'][0].update(partial_policy='report',minimum_coverage=.1)
        for operation in ('window_rate','sample_fit_slope'):
            for policy in ('report','strict'):
                name=operation+'_'+policy
                raw['transforms'].append(dict(name=name,operation=operation,window='1s',step='1s',
                    expr='where(a > 5,trend + 1,a)',partial_policy=policy))
                raw['calculations'].append(dict(name='out_'+name,operation='select',expr=name))
        for backend in ('reference','numpy'):
            rows,_,_=helper.run_case(raw,backend)
            first={r.calculation_id:r for r in rows if r.time_ns==10**9}
            for operation in ('window_rate','sample_fit_slope'):
                with self.subTest(backend=backend,operation=operation):
                    report=first['out_'+operation+'_report']
                    self.assertEqual(report.value,1.)
                    self.assertTrue(report.quality & Q.ESTIMATED)
                    strict=first.get('out_'+operation+'_strict')
                    self.assertTrue(strict is None or strict.value is None)

    def config(self):
        """构造1s为2A、2s为5A的部分输出，3s为6A完整。参数: 无。返回: 配置。异常: 无。"""
        import test_rolling_transforms_v4 as rolling
        raw=rolling.RollingTransformsTests('runTest').config(((0,2.),(1,8.),(4,8.)),window='3s')
        raw['transforms'][0].update(partial_policy='report',minimum_coverage=.1)
        raw['calculations'].extend([
            dict(name='strict_points',operation='select',expr='trend',partial_policy='strict'),
            dict(name='avg',operation='sample_mean',expr='trend'),
            dict(name='strict_avg',operation='sample_mean',expr='trend',partial_policy='strict'),
            dict(name='area',operation='integral',expr='trend'),
            dict(name='masked',operation='sample_mean',expr='where(True,a,trend)'),
            dict(name='false_area',operation='integral',expr='trend',condition='a < 0'),
            dict(name='scoped',operation='sample_mean',expr='a',scope=dict(window='around'))])
        raw['rules']=[dict(name='on',rule_type='rising_edge',condition='trend > 3')]
        raw['windows']=[dict(name='around',rule='on',pre='1s',post='1s')]
        return raw

    def test_public_selected_samples_areas_and_scope_quality(self):
        """两个后端同验窗口部分值、选中贡献和参与父区间；未选分支不污染完整统计。

        参数: 无。返回: None。异常: 时间、值、掩码、部分性或父关系错误。
        """
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend),TemporaryDirectory(dir='work',prefix='rolling-partial-') as folder:
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(self.config()),work_dir=Path(folder)/'run') as result:
                    selections={(r.calculation_id,r.time_ns//10**9):r for r in result.iter_selections()}
                    for t,expected in ((1,2.),(2,5.),(3,6.)):
                        row=selections['points',t]
                        self.assertEqual(row.value,expected)
                        self.assertEqual(bool(row.quality&Q.ESTIMATED),t<3)
                        self.assertEqual(selections['strict_points',t].value,None if t<3 else expected)
                    values={r.calculation_id:r for r in result.iter_calculations()}
                    for name in ('avg','area','scoped'):
                        self.assertEqual(values[name].status,'partial')
                        self.assertTrue(values[name].quality & Q.ESTIMATED)
                    self.assertAlmostEqual(values['avg'].value,13/3)
                    self.assertEqual(values['area'].value,13.)
                    self.assertIsNone(values['strict_avg'].value)
                    self.assertTrue(values['strict_avg'].quality & Q.ESTIMATED)
                    self.assertEqual((values['masked'].status,values['masked'].value),('complete',5.))
                    self.assertFalse(values['masked'].quality & Q.ESTIMATED)
                    self.assertEqual(values['false_area'].value,0.)
                    self.assertFalse(values['false_area'].quality & Q.ESTIMATED)
                    self.assertTrue(next(result.iter_events()).quality & Q.ESTIMATED)
                    self.assertTrue(next(result.iter_segments()).quality & Q.ESTIMATED)

    def test_half_open_clipping_held_samples_and_false_selection(self):
        """TTL 前后、非真实更新、假条件和右端部分值都不能制造部分贡献。参数: 无。返回: None。异常: 断言错误。"""
        partial=ScalarValue(1.,D.FLOAT64,partial=True)
        good=ScalarValue(2.,D.FLOAT64)
        val=[(0,partial,1,None,None,False),(3,good,None,None,None,True),(4,partial,None,None,None,True)]
        self.assertTrue(partial_in_block(val,Interval(0,4),samples=False))
        self.assertFalse(partial_in_block(val,Interval(1,4),samples=False))
        self.assertFalse(partial_in_block(val,Interval(0,4),samples=True))
        val[0]=(0,partial,None,ScalarValue(False,D.BOOL),None,True)
        self.assertFalse(partial_in_block(val,Interval(0,4),samples=False))

    def test_spooled_values_and_conditions_keep_independent_partial_bits(self):
        """按需历史暂存不改变逻辑有效性，值和条件的部分标记独立往返。参数: 无。返回: None。异常: 费用或标记错误。"""
        budget=ResourceBudget()
        with TemporaryDirectory(dir='work',prefix='partial-history-') as folder:
            with closing(RecordValueHistory(budget,Path(folder),D.FLOAT64,True,sample_updates=True)) as history:
                for i in range(3):
                    history.append((i,ScalarValue(float(i),D.FLOAT64,partial=i==1),None),
                                   (i,ScalarValue(True,D.BOOL,partial=i==0),None),actual_update=True)
                for i in range(3):
                    _,value,_,condition,_,actual=history.at(i)
                    self.assertEqual((value.partial,condition.partial,actual),(i==1,i==0,True))
                    self.assertTrue(value.valid and condition.valid)
        self.assertEqual(budget.ram_bytes,0)

    def test_window_delta_marks_only_values_used_by_its_condition(self):
        """两端完整但中间估算，只在要求单调时部分；估算移至左端时两种模式均部分。

        参数: 无。返回: None。异常: 任一后端错误扩散或清除估算标志。
        """
        from chronaxis.core.window_delta import WindowDeltaSpec
        from chronaxis.execution.record_delta_condition import RecordDeltaCondition
        for backend in ('reference','numpy'):
            for monotonic in (False,True):
                budget=ResourceBudget()
                with closing(RecordDeltaCondition(budget,WindowDeltaSpec(2,0.,monotonic=monotonic),D.FLOAT64,backend,None)) as owner:
                    for t in range(4):
                        value=ScalarValue(float(t),D.FLOAT64,partial=t==1)
                        point,right=owner.update(t,value,value,None,driver=True)
                        if t>=2:
                            self.assertTrue(point.valid and right.valid)
                            self.assertEqual((point.partial,right.partial),(monotonic or t==3,)*2)
                self.assertEqual(budget.ram_bytes,0)
