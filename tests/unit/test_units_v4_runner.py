"""从公开计划和Runner验证新单位在读取、计算和发布之间没有遗漏。

输入是本测试生成的内存值及小型CAN夹具；输出包括统计、选择行、贡献和清单。
两个后端对照手算结果，临时工作仅放在项目work映射，退出后释放结果资源。
这里验证合成数据接线，不代表用户真实日志、性能或整项DSL扩展已经验收。
"""

# 测试隔离目录只持有本次结果，原日志与旧项目保持只读。
import json
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest
from chronaxis import AnalysisPlan, AnalysisRunner
from published_paths import published_file


class UnitsV4RunnerTests(unittest.TestCase):
    """按公开配置运行新单位，分别检查数值、单位及版本声明。"""

    def config(self, backend):
        """构造两秒功率和温度保持数据，目标结果可直接手算。

        参数: backend为reference或numpy。
        返回: 完整版本4配置dict。
        异常: 无；本函数不加载计划或创建文件。
        """
        # 功率1/3/5kW、温度0/20/40℃；半开范围[0,2s)不含末点样本。
        return dict(config_version=4, dataset=dict(name='unit_run', domain=dict(start='0s',end='2s')),
            sources=[dict(name='table', source_type='memory', rows=[
                dict(time=f'{i}s',values={'p':float(p),'t':float(t)})
                for i,p,t in ((0,1,0),(1,3,20),(2,5,40))])],
            signals=[dict(name='power',field='p',dtype='float64',unit='kW',valid_for='3s'),
                     dict(name='temperature',field='t',dtype='float64',unit='degC',valid_for='3s')],
            calculations=[
                dict(name='energy',operation='integral',expr='power',unit='Wh'),
                dict(name='mean',operation='sample_mean',expr='power',unit='kW'),
                dict(name='temp_mean',operation='time_weighted_mean',expr='temperature',unit='degC'),
                dict(name='temp_min',operation='sample_minimum',expr='temperature',unit='degC'),
                dict(name='values',operation='select',expr='power',unit='kW')],
            execution=dict(backend=backend,batch_rows=1),outputs=dict(tables='jsonl'))

    def test_public_statistics_selection_and_manifest_version(self):
        """同一运行同时覆盖积分、偏移均值/极值、选取和清单版本。

        参数: 无。
        返回: None；能量4000J=10/9Wh，范围内样本均值2kW，时间温度均值10℃。
        异常: 计划/执行失败或结果差异使测试失败。
        """
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend), TemporaryDirectory(dir='work',prefix='units-v4-') as folder:
                plan=AnalysisPlan.from_dict(self.config(backend))
                with AnalysisRunner().run(plan,work_dir=Path(folder)/'run') as result:
                    rows={row.calculation_id:row for row in result.iter_calculations()}
                    self.assertAlmostEqual(rows['energy'].value,10/9)
                    self.assertEqual(rows['energy'].unit,'Wh')
                    self.assertAlmostEqual(rows['mean'].value,2.)
                    self.assertEqual(rows['mean'].unit,'kW')
                    self.assertAlmostEqual(rows['temp_mean'].value,10.)
                    self.assertAlmostEqual(rows['temp_min'].value,0.)
                    selected=list(result.iter_selections())
                    self.assertEqual([row.value for row in selected],[1.,3.])
                    self.assertTrue(all(row.unit=='kW' for row in selected))
                    published=result.write(Path(folder)/'output')
                    manifest=json.loads(published_file(published,'run_manifest.json').read_text(encoding='utf-8'))
                    self.assertEqual(manifest['run']['config_version'],4)

    def test_public_current_message_target_and_contribution_modes(self):
        """同刻两条4000W报文分别贡献400J，总量转换为2/9Wh。

        参数: 无。
        返回: None；full/none及两个后端总值按原合同取六位小数0.222222，明细同为Wh。
        异常: 版本、单位或合计不一致时断言失败；依赖缺失按原夹具跳过。
        """
        # 复用已有真实CAN夹具构造，不复用其计算答案或数值执行。
        from test_run_message_calculations import RunMessageCalculationTests
        from configuration_fixtures import current_fixture
        fixture=RunMessageCalculationTests()
        for backend in ('reference','numpy'):
            work, config, _=fixture.fixture(backend=backend,frames=((0,256,b'\xa0\x0f'),(0,256,b'\xa0\x0f')))
            config=current_fixture(config)
            config['config_version']=4
            # DBC给出W，绑定改为kW且不手填倍率，验证解码后只转换一次。
            config['signals'][0]['unit']='kW'
            config['message_calculations'][0]['unit']='Wh'
            for mode in ('full','none'):
                config['outputs']['contributions']=mode
                plan=AnalysisPlan.from_dict(config,base_dir=work)
                with AnalysisRunner().run(plan,work_dir=work/('v4-'+mode)) as result:
                    rows=list(result.iter_calculations())
                    self.assertEqual(len(rows),1)
                    # current_message-v1保留原最终六位舍入，贡献明细仍为原未舍入贡献。
                    self.assertEqual(rows[0].value,0.222222)
                    self.assertEqual(rows[0].unit,'Wh')
                    if mode=='full':
                        contributions=list(result.iter_contributions())
                        self.assertEqual(len(contributions),2)
                        # 明细按calculation_id引用该计算的Wh单位，不重复保存每行单位。
                        self.assertTrue(all(row.calculation_id==rows[0].calculation_id for row in contributions))
                        self.assertAlmostEqual(sum(row.value for row in contributions),2/9)


# 可独立运行两个公开入口测试；输出在项目已有work目录中。
if __name__=='__main__':
    unittest.main()
