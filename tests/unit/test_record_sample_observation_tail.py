"""[home] BUG-CFG-035：末条所需信号之后的真实观测边界不能漏掉样本。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest
from unittest.mock import patch

from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter


class SampleObservationTailTests(unittest.TestCase):
    """从公开文件入口读取ASC，按独立手算核样本、选择和半开边界。"""

    def setUp(self):
        """建立独立合成文件和工作目录；不读取用户DBC。"""
        directory=TemporaryDirectory(prefix='sample-observed-tail-',dir='work')
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name).resolve()
        (self.root/'meter.dbc').write_text('''VERSION "synthetic-home"
NS_ :
BS_:
BU_: Node
BO_ 256 PowerFrame: 2 Node
 SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node
BA_DEF_ BO_ "GenMsgCycleTime" INT 0 65535;
BA_DEF_DEF_ "GenMsgCycleTime" 0;
BA_ "GenMsgCycleTime" BO_ 256 1000;
''',encoding='utf-8')

    def config(self, values=((0,2),(1,4),(3,8),(4,10)), end=6, age='3s'):
        """写有限ASC；末尾无关ID仅提供该来源的实际观测结束。"""
        lines=['date Mon Jan 01 00:00:00 2024','base hex timestamps absolute','internal events logged']
        for time,value in values:
            lines.append(f'{time:.6f} 1 100 Rx d 2 {value & 255:02X} {value >> 8:02X}')
        if end is not None:lines.append(f'{end:.6f} 1 7FE Rx d 1 00')
        (self.root/'meter.asc').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        return dict(config_version=3,dataset=dict(name='tail'),
            sources=[dict(name='meter',path='meter.asc',dbc_by_channel={'1':'meter.dbc'},time=dict(clock='shared'))],
            signals=[dict(name='power',field=dict(frame_id='0x100',signal='Power'),valid_for=age)],
            calculations=[dict(name=op,operation=op,expr='power') for op in
                ('integral','sample_minimum','sample_maximum','sample_mean','select')])

    def run_config(self,config,backend):
        """序列化后走公共加载和Runner；禁止新增历史并核对原始文件只扫描一次。"""
        path=self.root/'plan.json';path.write_text(json.dumps(config),encoding='utf-8')
        plan=load_analysis_plan(path)
        original=BudgetedTextCANSourceAdapter.iter_batches;scans=[]
        def scan(owner,*args,**kwargs):
            """计实际读取器调用数，仍执行真实读取。"""
            scans.append(owner);return original(owner,*args,**kwargs)
        with patch.object(BudgetedTextCANSourceAdapter,'iter_batches',scan),patch(
                'chronaxis.execution.history.DecodedHistoryStore',side_effect=AssertionError('extra history')):
            with AnalysisRunner(backend).run(plan,self.root/uuid4().hex) as result:
                rows={row.calculation_id:row for row in result.iter_calculations()}
                selected=tuple((row.time_ns/1e9,row.value) for row in result.iter_selections())
                budget=result.spool.budget
        self.assertEqual(len(scans),1)
        self.assertEqual(budget.ram_bytes,0)
        return rows,selected

    def test_unrelated_last_frame_closes_sample_tail(self):
        """0/1/3/4秒四个样本全计入0—6秒：均值6、最大10、积分38。"""
        for backend in ('reference','numpy'):
            for explicit in (False,True):
                for batch in (1,64):
                    with self.subTest(backend=backend,explicit=explicit,batch=batch):
                        raw=self.config();raw['execution']=dict(batch_rows=batch)
                        if explicit:raw['dataset']['domain']=dict(start='0s',end='6s')
                        rows,selected=self.run_config(raw,backend)
                        self.assertEqual({key:row.value for key,row in rows.items()},
                            dict(integral=38.,sample_minimum=2.,sample_maximum=10.,sample_mean=6.))
                        self.assertTrue(all(row.status=='complete' for row in rows.values()))
                        self.assertEqual(selected,((0,2.),(1,4.),(3,8.),(4,10.)))

    def test_expired_tail_keeps_real_sample_but_reports_gap(self):
        """最后值到5秒过期，4秒的真实样本仍在，5—6秒缺测不伪造新样本。"""
        for backend in ('reference','numpy'):
            rows,selected=self.run_config(self.config(age='1s'),backend)
            self.assertEqual(rows['sample_mean'].value,6.)
            self.assertEqual(rows['sample_maximum'].value,10.)
            self.assertTrue(all(row.status=='partial' for row in rows.values()))
            self.assertEqual(selected,((0,2.),(1,4.),(3,8.),(4,10.)))

    def test_true_endpoint_and_zero_span_remain_half_open(self):
        """真实结束点不纳入；只有一条且观测跨度为零时仍没有样本统计。"""
        for backend in ('reference','numpy'):
            raw=self.config(end=None)
            rows,selected=self.run_config(raw,backend)
            self.assertEqual(rows['sample_mean'].value,14/3)
            self.assertEqual(rows['sample_maximum'].value,8.)
            self.assertEqual(selected,((0,2.),(1,4.),(3,8.)))
            raw=self.config(values=((0,2),),end=None)
            rows,selected=self.run_config(raw,backend)
            self.assertTrue(all(row.value is None for row in rows.values()))
            self.assertEqual(selected,())

    def test_condition_updates_do_not_create_samples(self):
        """条件在2/5秒独自更新不能增加功率样本；条件先结束后的覆盖仍未知。"""
        for backend in ('reference','numpy'):
            raw=self.config()
            raw['signals'][0]['source']='meter'
            raw['sources'].append(dict(name='gate_source',source_type='memory',time=dict(clock='shared'),
                rows=[dict(time=f'{t}s',values=dict(gate=True)) for t in (0,2,5)]))
            raw['signals'].append(dict(name='gate',source='gate_source',field='gate',dtype='bool',unit='1',valid_for='10s'))
            for item in raw['calculations']:item['condition']='gate'
            rows,selected=self.run_config(raw,backend)
            self.assertEqual(rows['sample_mean'].value,6.)
            self.assertEqual(rows['sample_maximum'].value,10.)
            self.assertTrue(all(row.status=='partial' for row in rows.values()))
            self.assertEqual(selected,((0,2.),(1,4.),(3,8.),(4,10.)))

    def test_earlier_value_source_eof_is_not_extended_by_condition_source(self):
        """功率源4秒结束、条件源观测到6秒；不能把4秒终点当功率范围内部样本。"""
        for backend in ('reference','numpy'):
            raw=self.config(end=None)
            raw['signals'][0]['source']='meter'
            raw['sources'].append(dict(name='gate_source',source_type='memory',time=dict(clock='shared'),
                rows=[dict(time='0s',values=dict(gate=True)),dict(time='6s',values={})]))
            raw['signals'].append(dict(name='gate',source='gate_source',field='gate',dtype='bool',unit='1',valid_for='10s'))
            for item in raw['calculations']:item['condition']='gate'
            rows,selected=self.run_config(raw,backend)
            self.assertEqual(rows['sample_mean'].value,14/3)
            self.assertEqual(rows['sample_maximum'].value,8.)
            self.assertTrue(all(row.status=='partial' for row in rows.values()))
            # select既有政策保留真实更新上的无效值行，统计则不计入该样本。
            # 以6秒真实条件更新作独立对照：该路径已有右端，无需本次EOF补点。
            raw['sources'][1]['rows'][-1]['values']={'gate':True}
            existing_rows,existing_selected=self.run_config(raw,backend)
            self.assertEqual(selected,existing_selected)
            self.assertEqual(selected,((0,2.),(1,4.),(3,8.),(4,None)))
            self.assertEqual({key:(row.value,row.status) for key,row in rows.items()},
                {key:(row.value,row.status) for key,row in existing_rows.items()})

    def test_single_sample_with_later_observation_keeps_original_value(self):
        """一个真实样本也能统计；只有观测结束边界，不补第二个样本。"""
        for backend in ('reference','numpy'):
            rows,selected=self.run_config(self.config(values=((0,2),),end=2),backend)
            self.assertEqual(rows['sample_mean'].value,2.)
            self.assertEqual(rows['sample_minimum'].value,2.)
            self.assertEqual(rows['sample_maximum'].value,2.)
            self.assertTrue(all(row.status=='complete' for row in rows.values()))
            self.assertEqual(selected,((0,2.),))


if __name__=='__main__':unittest.main()
