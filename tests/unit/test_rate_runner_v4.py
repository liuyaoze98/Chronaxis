"""通过公开变换配置验证三种变化率的调度、真实时间门槛及输出单位。

0/1/3秒的温度真值是20/21/26℃。等权拟合使用三个真实点，点差和窗口
端点的分母独立检查。另用小型ASC/DBC运行真实的驱动周期查询。
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from chronaxis import AnalysisPlan, AnalysisRunner


def rate_config(*, batch=1, age='4s', gap='3s', interval=None):
    """构造能覆盖3秒输出的真实源，最后两条只用于恢复和声明观测尾。

    参数: batch为批次大小，age为实际TTL，gap为实际最大相邻间隔，interval可改周期。
    返回: v4配置。异常: 无，签名与单位的实际检查由公共编译完成。
    """
    transforms = [dict(name='adj',operation='adjacent_rate',expr='temperature',max_gap=gap),
                  dict(name='ends',operation='window_rate',expr='temperature',window='3s',step='1s'),
                  dict(name='fitted',operation='sample_fit_slope',expr='temperature',window='3s',step='1s')]
    if interval is not None:
        for item in transforms:
            item['interval'] = interval
            if item['operation'] != 'adjacent_rate':
                item['window'] = '0.2s'
    return dict(config_version=4,dataset=dict(name='rates',domain=dict(start='0s',end='5s')),
        sources=[dict(name='readings',source_type='memory',rows=[
            dict(time=f'{t}s',values={'t':v}) for t,v in ((0,20.),(1,21.),(3,26.),(4,27.),(5,28.))])],
        signals=[dict(name='temperature',field='t',dtype='float64',unit='degC',valid_for=age)],
        transforms=transforms,calculations=[dict(name='out_'+v['name'],operation='select',expr=v['name'])
                                             for v in transforms],execution=dict(batch_rows=batch))


class RateRunnerTests(unittest.TestCase):
    """从选择结果的真实时刻和单位校验离散输出，结束后核共享RAM归零。"""

    def outputs(self, raw, backend, directory):
        """运行一次配置并按公开输出列与实际纳秒时刻读取结果。

        参数: raw/后端/现有私有目录，目录也作为相对来源路径的基准。
        返回: {输出名:{实际纳秒:选择行}}。异常: 执行失败或费用泄漏直接失败。
        """
        plan = AnalysisPlan.from_dict(raw,base_dir=directory)
        with TemporaryDirectory(dir=directory,prefix='rate-run-') as folder:
            with AnalysisRunner(backend).run(plan,Path(folder)/'run') as result:
                rows = {}
                for row in result.iter_selections():
                    by_time = rows.setdefault(row.calculation_id,{})
                    self.assertNotIn(row.time_ns,by_time)
                    by_time[row.time_ns] = row
                budget = result.spool.budget
            self.assertEqual(budget.ram_bytes,0)
        return rows

    def test_actual_and_fixed_temperature_rates(self):
        """不等实际间隔与等序号周期分别验证端点同刻采用新值且拟合含右端。

        参数: 无。返回: None。异常: 混用采样范围、时间单位或温度偏移时失败。
        """
        for backend in ('reference','numpy'):
            for fixed in (False,True):
                for batch in (1,16):
                    config = rate_config(batch=batch,interval=dict(mode='fixed',driver='temperature',value='0.1s')
                                         if fixed else None)
                    with self.subTest(backend=backend,fixed=fixed,batch=batch), TemporaryDirectory(dir='work') as folder:
                        rows = self.outputs(config,backend,Path(folder))
                        expected = (50.,30.,30.) if fixed else (2.5,2.,29/14)
                        for name,value in zip(('out_adj','out_ends','out_fitted'),expected):
                            point = rows[name][3_000_000_000]
                            self.assertAlmostEqual(point.value,value)
                            self.assertEqual(point.unit,'delta_K/s')

    def test_actual_gap_ttl_and_atomic_refresh(self):
        """TTL到点同时刷新可继续相邻差分，过期区间或实际max_gap均会断链。

        参数: 无。返回: None。异常: 跨未知保留旧斜率或多计同刻真实输出时失败。
        """
        for backend in ('reference','numpy'):
            for age,gap,fixed in (('1s','3s',False),('5s','1s',False),('1s','3s',True),('5s','1s',True)):
                raw = rate_config(age=age,gap=gap,interval=dict(mode='fixed',driver='temperature',value='0.1s')
                                  if fixed else None)
                raw['transforms'] = raw['transforms'][:1]
                raw['calculations'] = raw['calculations'][:1]
                # 4秒先报错误候选5℃再报最终27℃，该组只应推进一次。
                raw['signals'][0]['same_time_policy'] = 'last_by_sequence'
                raw['sources'][0]['rows'].insert(3,dict(time='4s',values={'t':5.}))
                with self.subTest(backend=backend,age=age,gap=gap,fixed=fixed),TemporaryDirectory(dir='work') as folder:
                    rows = self.outputs(raw,backend,Path(folder))['out_adj']
                    self.assertEqual(rows[10**9].value,10. if fixed else 1.)
                    self.assertIsNone(rows[3*10**9].value)
                    self.assertEqual(rows[4*10**9].value,10. if fixed else 1.)

    def test_dbc_drives_selected_period_without_changing_actual_times(self):
        """合成ASC的真实驱动记录相隔2秒，但按DBC的1秒周期得到5W/s。

        参数: 无。返回: None。异常: DBC周期遗漏、样本时刻被改写或预算未回收时失败。
        """
        from test_record_sample_observation_tail import SampleObservationTailTests
        files = SampleObservationTailTests()
        files.setUp()
        self.addCleanup(files.doCleanups)
        for backend in ('reference','numpy'):
            raw = files.config(values=((0,20),(1,21),(3,26),(4,27)),end=5,age='4s')
            raw['config_version'] = 4
            choice = dict(mode='dbc',driver='power')
            raw['transforms'] = [dict(name='r',operation='adjacent_rate',expr='power',max_gap='3s',interval=choice),
                                 dict(name='w',operation='window_rate',expr='power',window='2s',step='1s',interval=choice),
                                 dict(name='f',operation='sample_fit_slope',expr='power',window='2s',step='1s',interval=choice)]
            raw['calculations'] = [dict(name='out_'+n,operation='select',expr=n) for n in ('r','w','f')]
            with self.subTest(backend=backend):
                rows = self.outputs(raw,backend,files.root)
                for name,value in (('out_r',5.),('out_w',3.),('out_f',3.)):
                    point = rows[name][3*10**9]
                    self.assertAlmostEqual(point.value,value)
                    # 项目单位目录将W/s规范显示为V*A/s，数值倍率仍为1。
                    self.assertEqual(point.unit,'V*A/s')

    def test_independent_driver_preserves_both_actual_value_updates(self):
        """在两驱动帧之间保留两次电流实测，等后一帧确定间距后回填0.09秒。

        参数: 无。返回: None。异常: 抽成一个驱动样本、除以0.06实际秒或改变输出时间则失败。
        """
        sources,signals = [],[]
        for name,unit,observations in (('clockword','1',((0,0),(.12,1),(.30,2))),
                                      ('amperes','A',((.03,1),(.09,7),(.30,7)))):
            sources.append(dict(name=name,source_type='memory',time={'clock':'same'},rows=[
                dict(time=f'{t}s',values={'v':n}) for t,n in observations]))
            signals.append(dict(name=name,source=name,field='v',dtype='int64',unit=unit,valid_for='1s'))
        raw = dict(config_version=4,dataset={'name':'async_rate'},sources=sources,signals=signals,
                   transforms=[dict(name='dv',operation='adjacent_rate',expr='amperes',max_gap='1s',
                                    interval=dict(mode='fixed',driver='clockword',value='0.1s'))],
                   calculations=[dict(name='out',operation='select',expr='dv')],execution=dict(batch_rows=1))
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend),TemporaryDirectory(dir='work') as folder:
                rows = self.outputs(raw,backend,Path(folder))['out']
                self.assertEqual(rows[90_000_000].value,120.)
                self.assertNotIn(120_000_000,rows)
