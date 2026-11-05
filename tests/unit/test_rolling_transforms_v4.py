"""D2 通过真实公共 Runner 校核滚动输出、事件、条件、真实周期、EOF及前史。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.planning.input_requirements import collect_input_requirements


class RollingTransformsTests(unittest.TestCase):
    """以原样本、独立手算输出和事件纳秒坐标验收离散模型。"""

    def config(self, rows, *, op='rolling_time_mean', window='10s', step='1s', origin='0s'):
        """参数: 原始行、操作和网格。返回: v4完整配置。异常: 由实际解析器报告。"""
        return dict(config_version=4,dataset=dict(name='demo',domain=dict(start=f'{rows[0][0]}s',end=f'{rows[-1][0]}s')),
            sources=[dict(name='meter',source_type='memory',rows=[
                dict(time=f'{t}s',values={'raw':v}) for t,v in rows])],
            signals=[dict(name='a',field='raw',dtype='float64',unit='A',valid_for='30s')],
            transforms=[dict(name='trend',operation=op,expr='a',window=window,step=step,origin=origin)],
            calculations=[dict(name='points',operation='select',expr='trend')],
            execution=dict(batch_rows=1))

    def run_case(self,raw,backend):
        """参数: 公共配置及后端。返回: 选择行、汇总行和事件。异常: 运行/关闭失败。"""
        plan=AnalysisPlan.from_dict(raw)
        with TemporaryDirectory(dir='work',prefix='rolling-v4-') as directory:
            with AnalysisRunner(backend).run(plan,work_dir=Path(directory)/'run') as result:
                return tuple(result.iter_selections()),tuple(result.iter_calculations()),tuple(result.iter_events())

    def test_step_response_and_duration_on_real_grid(self):
        """参数: 无。返回: 无。异常: 阶跃真实网格、样本或持续确认时间错误。"""
        raw=self.config(((-10,0.),(0,10.),(12,10.)))
        raw['rules']=[dict(name='active',rule_type='condition_duration',condition='trend >= 5',
                           minimum_duration='3s')]
        raw['windows']=[dict(name='around',rule='active',anchor='activity',pre='0s',post='0s',merge='none')]
        raw['calculations'].extend([dict(name='event_avg',operation='sample_mean',expr='trend',scope={'rule':'active'}),
            dict(name='window_avg',operation='sample_mean',expr='trend',scope={'window':'around'})])
        for backend in ('reference','numpy'):
            for step,onset in ((1,5),(3,6)):
                raw['transforms'][0]['step']=f'{step}s'
                selected,summaries,events=self.run_case(raw,backend)
                valid={s.time_ns//10**9:s.value for s in selected if s.value is not None}
                for t in range(0,12,step):
                    self.assertAlmostEqual(valid[t],min(10.,float(t)))
                event,=events
                self.assertEqual((event.start_ns,event.confirmed_ns),(onset*10**9,(onset+3)*10**9))
                for summary in summaries:
                    self.assertAlmostEqual(summary.value,55/7 if step==1 else 7.5)

    def test_fixed_between_frames_delays_calculation_but_keeps_grid_timestamp(self):
        """参数: 无。返回: 无。异常: 未确认原周期被外推、网格错位或等权分摊。"""
        raw=self.config(((10,10.),(10.12,20.),(10.3,30.)),window='0.1s',step='0.1s',origin='10s')
        raw['transforms'][0]['interval']=dict(mode='fixed',value='0.1s',driver='a')
        for backend in ('reference','numpy'):
            rows,_,_=self.run_case(raw,backend)
            by_time={r.time_ns:r.value for r in rows}
            self.assertAlmostEqual(by_time[10_200_000_000],130/9)
            self.assertEqual(sorted(by_time),[10_000_000_000,10_100_000_000,10_200_000_000])

    def test_extrema_integral_missing_window_and_cascaded_dependencies(self):
        """参数: 无。返回: 无。异常: 二级依赖、TTL、端点或面积单位错误。"""
        for op,answer in (('rolling_minimum',2.),('rolling_maximum',8.),('rolling_integral',18.)):
            raw=self.config(((0,2.),(1,8.),(3,4.),(4,4.)),op=op,window='3s')
            for backend in ('reference','numpy'):
                rows,_,_=self.run_case(raw,backend)
                by_time={r.time_ns:r.value for r in rows}
                self.assertIsNone(by_time[2*10**9])
                self.assertAlmostEqual(by_time[3*10**9],answer)
        raw=self.config(((0,2.),(1,8.),(3,4.),(4,4.)),window='1s')
        raw['transforms'].insert(0,dict(name='twice',operation='rolling_maximum',expr='adjusted',window='1s',step='1s'))
        raw['derived']={'adjusted':{'expr':'trend*2'}}
        raw['calculations'][0]['expr']='twice'
        plan=AnalysisPlan.from_dict(raw)
        needed=collect_input_requirements(plan)
        self.assertEqual((needed.ordinary_sample_aliases,needed.transform_names),(('a',),('trend','twice')))
        rows,_,_=self.run_case(raw,'numpy')
        self.assertEqual({r.time_ns:r.value for r in rows}[3*10**9],16.)
        raw['transforms'][1]['expr']='twice'
        with self.assertRaisesRegex(ValueError,'循环'):
            AnalysisPlan.from_dict(raw)

    def test_async_can_clock_and_dbc_preserve_input_positions_and_scope(self):
        """参数: 无。返回: 无。异常: 只读计时帧才取测量值或固定周期被实际秒数替代。"""
        from test_record_runner import RecordRunnerTests
        from configuration_fixtures import current_fixture
        from chronaxis.configuration.resolution import resolved_configuration
        factory=RecordRunnerTests()
        factory.setUp()
        self.addCleanup(factory.doCleanups)
        factory.fixtures()
        # 0/.12/.30 为100ms计时帧，测量在.03和.09（各在第一帧对的1/4和3/4）。
        with factory.dbc.open('a',encoding='utf-8') as out:
            out.write('BO_ 257 Sensor: 1 Node\n SG_ Measured : 0|8@1+ (1,0) [0|255] "A" Node\n')
        path=factory.asc('0.00 1 100 Rx d 2 C8 0A\n0.03 1 101 Rx d 1 01\n0.09 1 101 Rx d 1 07\n'
                         '0.12 1 100 Rx d 2 C8 0C\n0.30 1 100 Rx d 2 C8 14\n').path
        for mode in ('fixed','dbc'):
            def edit(raw):
                """参数: 原夹具配置。返回: 无。异常: 原字段转换不合法。"""
                measured=dict(raw['signals'][1])
                measured.update(name='observed',field=dict(measured['field'],frame_id=257,signal='Measured'))
                raw['signals'].append(measured)
                raw['calculations']=[dict(name='picked',operation='select',expr='curve')]
                public=current_fixture(raw)
                raw.clear()
                raw.update(public,config_version=4,transforms=[dict(name='curve',operation='rolling_time_mean',
                    expr='observed',window='0.05s',step='0.03s')])
            plan=factory.plan('can_asc',path,mode,edit)
            for backend in ('reference','numpy'):
                with TemporaryDirectory(dir='work',prefix='rolling-clock-') as folder:
                    with AnalysisRunner(backend).run(plan,work_dir=Path(folder)/'run') as result:
                        points={r.time_ns:r.value for r in result.iter_selections()}
                    # 在.12，回看50ms计量纳秒对应[.06,.12)：1与7各占一半。
                    self.assertAlmostEqual(points[120000000],4.)
            # 通过文件展开默认值后，节点局部间隔与全局选择仍指向真实时钟current。
            config_file=factory.root/f'resolve-{mode}.json'
            config_file.write_text(json.dumps(dict(plan.raw_config),default=lambda x:dict(x)),encoding='utf-8')
            resolved=AnalysisPlan.from_dict(resolved_configuration(config_file,defaults=True))
            self.assertEqual(dict(resolved.intervals.resolved)['curve'],dict(plan.intervals.resolved)['curve'])

    def test_unrequested_transform_is_not_allocated_and_cancel_releases_owned_state(self):
        """参数: 无。返回: 无。异常: 未消费变换分配状态，或密集网格取消后未释放预算。"""
        from chronaxis.execution.transform_stream import TransformStage
        raw=self.config(((0,1.),(1,2.),(2,3.)),window='1s')
        raw['transforms'].append(dict(name='unused',operation='rolling_maximum',expr='a',window='1s',step='1ns'))
        self.assertEqual(collect_input_requirements(AnalysisPlan.from_dict(raw)).transform_names,('trend',))
        raw['calculations'][0]['expr']='a'
        with patch.object(TransformStage,'__init__',side_effect=AssertionError('未请求变换不应分配')):
            self.run_case(raw,'numpy')
        raw['calculations'][0]['expr']='unused'
        budgets=[]
        def cancel(stage,*args):
            """选定网格点中断。参数: 运行层和时刻。返回: 无。异常: KeyboardInterrupt。"""
            budgets.append(stage._budget)
            raise KeyboardInterrupt
        with patch.object(TransformStage,'_at_grid',cancel), self.assertRaises(KeyboardInterrupt):
            self.run_case(raw,'numpy')
        self.assertEqual(budgets[0].ram_bytes,0)

    def test_subnormal_constant_mean_remains_representable(self):
        """参数: 无。返回: 无。异常: 可表示的均值因单项乘小权重丢失。"""
        tiny=float.fromhex('0x0.0000000000001p-1022')
        raw=self.config(((0,tiny),(1,tiny),(2,tiny),(3,tiny),(4,0.)),window='3s')
        for backend in ('reference','numpy'):
            selected,_,_=self.run_case(raw,backend)
            self.assertEqual({row.time_ns:row.value for row in selected}[3*10**9],tiny)
