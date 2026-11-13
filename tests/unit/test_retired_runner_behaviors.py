"""F2隔离行为迁移草稿：保留旧手算真值，执行当前公开Runner；不导入旧回放夹具。"""
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from chronaxis import AnalysisPlan, AnalysisRunner

BASE = Path(__file__).resolve().parent / 'migration-runs'


def source(name, field, rows):
    """构造可含空投影观测尾的来源。参数: 名称/字段/时间值序列。返回: 字典。异常: 无。"""
    return dict(name=name,source_type='memory',time=dict(clock='f2_shared'),rows=[dict(time=f'{t}ns',values={} if field is None else {field:v}) for t,v in rows])


def signal(name, source_name, *, dtype='float64', unit='1', age=20):
    """构造明确单位和有效期的信号。参数: 名称/来源/类型/单位/纳秒有效期。返回: 字典。异常: 无。"""
    return dict(name=name,source=source_name,field=name,dtype=dtype,unit=unit,valid_for=f'{age}ns')


class MigrationBehaviorTests(unittest.TestCase):
    """只补组合入口缺口，不复制既有纯核或旧owner结构断言。"""
    def run_case(self, raw, *, backend, size):
        """运行、收集并关闭真实结果。参数: 配置/后端/批次。返回: 三类行。异常: 原产品或断言。"""
        raw=dict(raw,config_version=4,execution=dict(backend=backend,batch_rows=size,result_buffer_rows=1))
        BASE.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=BASE) as folder:
            plan=AnalysisPlan.from_dict(raw)
            with AnalysisRunner().run(plan,Path(folder)/'run') as result:
                rows=dict(calculations=tuple(result.iter_calculations()),events=tuple(result.iter_events()),selections=tuple(result.iter_selections()))
                budget=result.spool.budget
            self.assertEqual(budget.ram_bytes,0)
            self.assertFalse((Path(folder)/'run').exists())
        return rows

    def test_integral_original_order_final_unit_and_ttl_hand_truth(self):
        """保留原序抵消1000J和TTL裁剪5e-9J。参数: 无。返回: None。异常: 数值或分类断言。"""
        for backend in ('reference','numpy'):
            for size in (1,7):
                with self.subTest(backend=backend,size=size):
                    raw=dict(dataset=dict(name='sum',domain=dict(start='0s',end='3s')),
                        sources=[source('s','power',[(i*10**9,x) for i,x in enumerate((1e16,1.,-1e16,0.))])],
                        signals=[signal('power','s',unit='kW',age=4*10**9)],
                        calculations=[dict(name='energy',operation='integral',expr='power',unit='J')])
                    row,=self.run_case(raw,backend=backend,size=size)['calculations']
                    self.assertEqual((row.value,row.unit,row.status),(1000.,'J','complete'))
                    raw=dict(dataset=dict(name='ttl',domain=dict(start='2ns',end='7ns')),
                        sources=[source('s','power',[(0,1.),(5,2.),(8,0.)])],
                        signals=[signal('power','s',unit='W',age=3)],
                        calculations=[dict(name='energy',operation='integral',expr='power',unit='J')])
                    row,=self.run_case(raw,backend=backend,size=size)['calculations']
                    self.assertEqual((row.value,row.status),(5e-9,'partial'))

    def test_where_selected_updates_keep_five_samples_and_mean(self):
        """未选分支噪声不增样本；5个值8/8/30/15/8均值13.8。参数: 无。返回: None。异常: 断言。"""
        for backend in ('reference','numpy'):
            for noise in (False,True):
                with self.subTest(backend=backend,noise=noise):
                    source_rows={'gate':[(0,True),(1,True),(4,False),(5,False),(8,True)],
                                 'a':[(0,8),(2,8)],
                                 'b':[(0,50)]+([(1,None),(2,12),(3,99)] if noise else [])+[(4,30),(7,15)]}
                    sources=[]
                    for name,rows in source_rows.items():
                        item=source(name+'src',name,rows)
                        item['rows'].append(dict(time='10ns',values={}))
                        sources.append(item)
                    raw=dict(dataset=dict(name='where',domain=dict(start='0ns',end='10ns')),
                        sources=sources,signals=[signal('gate','gatesrc',dtype='bool'),signal('a','asrc',dtype='int64'),signal('b','bsrc',dtype='int64',age=2)],
                        calculations=[dict(name='average',operation='sample_mean',expr='where(gate,a,b)'),dict(name='pick',operation='select',expr='where(gate,a,b)')])
                    rows=self.run_case(raw,backend=backend,size=1)
                    self.assertEqual([(r.time_ns,r.value) for r in rows['selections']],[(0,8),(2,8),(4,30),(7,15),(8,8)])
                    row,=rows['calculations']
                    self.assertEqual(row.value,13.8)

    def test_multi_rule_deadlines_without_fabricated_updates(self):
        """同条件两门槛2ns和5ns分别准时确认、实际8ns结束。参数: 无。返回: None。异常: 断言。"""
        for backend in ('reference','numpy'):
            for size in (1,7):
                raw=dict(dataset=dict(name='rules',domain=dict(start='0ns',end='8ns')),
                    sources=[source('s','a',[(0,1.),(8,0.)])],signals=[signal('a','s')],
                    rules=[dict(name=name,rule_type='condition_duration',condition='a > 0',minimum_duration=f'{duration}ns',duration_comparison='>=') for name,duration in [('short',2),('long',5)]])
                events=self.run_case(raw,backend=backend,size=size)['events']
                self.assertEqual(sorted((e.rule_id,e.start_ns,e.confirmed_ns,e.end_ns,e.status) for e in events),[('long',0,5,8,'closed'),('short',0,2,8,'closed')])

    def test_coincident_ttl_terminal_update_and_deadline_keep_causality(self):
        """3ns同时到期/确认/EOF时，FALSE关闭、无效中断；保持TRUE截断。参数: 无。返回: None。异常: 断言。"""
        for backend in ('reference','numpy'):
            for last,status in ((0.,'closed'),(None,'interrupted'),(1.,'truncated')):
                raw=dict(dataset=dict(name='coincident',domain=dict(start='0ns',end='3ns')),
                    sources=[source('s','a',[(0,1.),(3,last)])],signals=[signal('a','s',age=3)],
                    rules=[dict(name='alarm',rule_type='condition_duration',condition='a > 0',minimum_duration='3ns',duration_comparison='>=')])
                events=self.run_case(raw,backend=backend,size=1)['events']
                self.assertEqual([(e.start_ns,e.confirmed_ns,e.end_ns,e.status) for e in events],[(0,3,3,status)])

if __name__=='__main__':unittest.main(verbosity=2)