"""通过公开Runner核对真实样本与点事件、活动、最终片段的计数。

合成规则产生两段分开的活动，同一批活动供两种窗口定义使用。手算计数和
真实结果行分别核对；完全空、未观测、部分发现与严格策略使用独立样例。
"""

from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import json
import unittest
from chronaxis import AnalysisPlan, AnalysisRunner


def counter_config(values=(0.,1.,1.,0.,1.,0.,0.)):
    """构造起止均有观测的6秒会话，保留原样本与窗口归属。

    参数: values为逐秒原值，None代表观测值缺失。返回: v4配置。
    异常: 无，实际解析时单独验证声明。
    """
    return dict(config_version=4,dataset=dict(name='counted',domain=dict(start='0s',end='6s')),
        sources=[dict(name='input',source_type='memory',rows=[
            dict(time=f'{n}s',values={'v':v}) for n,v in enumerate(values)])],
        signals=[dict(name='v',field='v',dtype='float64',unit='V',valid_for='5s')],
        rules=[dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='v > 0',minimum_duration='0s'),
               dict(name='rise',rule_type='rising_edge',condition='v > 0')],
        windows=[dict(name=name,rule='active',anchor='activity',pre='0s',post='0s',
                      merge='exit_delay',exit_delay='2s') for name in ('joined','second')],
        calculations=[dict(name='points',operation='point_event_count',rule='rise'),
                      dict(name='activities',operation='activity_count',rule='active'),
                      dict(name='strict_activities',operation='activity_count',rule='active',partial_policy='strict'),
                      dict(name='segments',operation='segment_count',window='joined'),
                      dict(name='samples',operation='sample_count',expr='v',condition='v>0'),
                      dict(name='by_event',operation='sample_count',expr='v',scope={'rule':'active'}),
                      dict(name='by_window',operation='sample_count',expr='v',scope={'window':'joined'})],
        execution=dict(batch_rows=1))


class CountOperationTests(unittest.TestCase):
    """从实际输出和单独的空域/未知样例核对计数及资源释放。"""

    def run_rows(self, raw, backend):
        """运行并按指标收集有限测试结果；关闭后公共预算应归零。

        参数: raw为公开配置，backend为运行后端。返回: 指标行映射。
        异常: 配置、执行、资源或数量差异触发失败。
        """
        with TemporaryDirectory(dir='work',prefix='counts-v4-') as directory:
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),Path(directory)/'run') as result:
                rows = {}
                for row in result.iter_calculations():
                    rows.setdefault(row.calculation_id,[]).append(row)
                budget = result.spool.budget
            self.assertEqual(budget.ram_bytes,0)
        return rows

    def test_two_activities_one_segment_and_scope_samples(self):
        """同一活动被多个窗口引用也只计一次，真实末点不加进半开样本。

        参数: 无。返回: None。异常: 计错对象、父范围或单位即失败。
        """
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend):
                rows = self.run_rows(counter_config(),backend)
                for name, expected in (('points',2),('activities',2),('strict_activities',2),('segments',1),('samples',3)):
                    row, = rows[name]
                    self.assertEqual((row.value,type(row.value),row.unit,row.status),(expected,int,'1','complete'))
                self.assertEqual([r.value for r in rows['by_event']],[2,1])
                self.assertEqual([r.value for r in rows['by_window']],[5])

    def test_complete_zero_partial_and_no_observation(self):
        """全FALSE完整返回0，已知活动后遇缺值分report/strict，无观测返回None。

        参数: 无。返回: None。异常: 混淆未知与完整空集时失败。
        """
        for backend in ('reference','numpy'):
            for mode in ('empty','partial','outside','unknown'):
                raw = counter_config((0.,)*7 if mode in ('empty','outside') else
                                     (None,)*7 if mode=='unknown' else (0.,1.,0.,None,None,0.,0.))
                if mode=='outside':
                    raw['dataset']['domain'] = dict(start='10s',end='12s')
                with self.subTest(backend=backend,mode=mode):
                    rows = self.run_rows(raw,backend)
                    activity = rows['activities'][0]
                    strict = rows['strict_activities'][0]
                    samples = rows['samples'][0]
                    if mode == 'empty':
                        self.assertEqual([(r.value,r.status) for r in (activity,strict,samples)],[(0,'complete')]*3)
                    elif mode == 'partial':
                        self.assertEqual((activity.value,activity.status),(1,'partial'))
                        self.assertEqual((strict.value,strict.status),(None,'indeterminate'))
                    else:
                        self.assertEqual([(r.value,r.status) for r in (activity,strict,samples)],[(None,'indeterminate')]*3)

    def test_invalid_scopes_and_v3(self):
        """拒绝错类规则、未知引用、无意义expr或模糊的对象范围，并隔离旧配置。

        参数: 无。返回: None。异常: 允许非法配置时断言失败。
        """
        for item in (dict(operation='point_event_count',rule='active'),dict(operation='activity_count',rule='rise'),
                     dict(operation='segment_count',window='missing'),dict(operation='sample_count'),
                     dict(operation='activity_count',rule='active',expr='v'),
                     dict(operation='point_event_count',rule='rise',condition='True'),
                     dict(operation='segment_count',window='joined',minimum_coverage=.5),
                     dict(operation='activity_count',rule='active',window='joined'),
                     dict(operation='segment_count',window='joined',scope={'rule':'active'})):
            raw = counter_config()
            raw['calculations'] = [dict(name='bad',**item)]
            with self.subTest(item=item), self.assertRaises(ValueError):
                AnalysisPlan.from_dict(raw)
        raw = counter_config()
        raw['config_version'] = 3
        with self.assertRaises(ValueError):
            AnalysisPlan.from_dict(raw)

    def test_where_counts_only_selected_real_updates(self):
        """where的未选分支更新及同值条件刷新不增加真实样本数。

        参数: 无。返回: None。异常: 分支采样、半开范围或后端语义不符时失败。
        """
        from test_where_acceptance import SIGNALS, EXPR
        sources, signals = [], []
        for name,dtype,unit,records in SIGNALS:
            sources.append(dict(name=name,source_type='memory',time={'clock':'same'},rows=[
                dict(time=f'{t}s',values={'raw':v}) for t,v in records]))
            signals.append(dict(name=name,source=name,field='raw',dtype=dtype.value,unit=unit,valid_for='20s'))
        raw = dict(config_version=4,dataset=dict(name='sampled',domain=dict(start='0s',end='6s')),
                   sources=sources,signals=signals,calculations=[dict(name='updates',operation='sample_count',expr=EXPR),
                                                              dict(name='constant',operation='sample_count',expr='1')])
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend):
                rows = self.run_rows(raw,backend)
                row, = rows['updates']
                self.assertEqual((row.value,row.status),(5,'complete'))
                constant, = rows['constant']
                self.assertEqual((constant.value,constant.status),(0,'complete'))

    def test_core_held_value_without_real_updates_counts_zero(self):
        """窗口内全程有确定保持值但无任何真实更新时，两条核心路径都计0。

        参数: 无。返回: None。异常: 把保持边界当样本或按输入单位输出则失败。
        """
        from test_calculations import _series
        from chronaxis.core.calculations import CalculationDefinition
        from chronaxis.core.models import Interval
        from chronaxis.core.calculations_reference import compute_reference
        from chronaxis.core.calculations_numpy import compute_numpy
        series = _series((3.,3.,3.),times=(0,1,3),actual=(True,False,False),unit='V')
        spec = CalculationDefinition('held','sample_count',Interval(1,3),config_version=4)
        for compute in (compute_reference,compute_numpy):
            with self.subTest(compute=compute.__name__):
                result = compute(series,spec)
                self.assertEqual((result.value,result.status,result.unit,result.valid_sample_count),(0,'complete','1',0))

    def test_resolve_reload_count_targets(self):
        """展开默认值后重载计数引用，避免向对象计数填入不适用的覆盖或表达式。

        参数: 无。返回: None。异常: 引用错配、配置变为无效或结果语义改变时失败。
        """
        from chronaxis.configuration.resolution import resolved_configuration
        raw = counter_config()
        with TemporaryDirectory(dir='work',prefix='count-config-v4-') as folder:
            path = Path(folder)/'counts.json'
            path.write_text(json.dumps(raw),encoding='utf-8')
            expanded = resolved_configuration(path,defaults=True)
            restored = AnalysisPlan.from_dict(expanded)
            before = AnalysisPlan.from_dict(raw)
            self.assertEqual([(r.operation,r.count_target,r.scope,r.partial_policy) for r in restored.calculations],
                             [(r.operation,r.count_target,r.scope,r.partial_policy) for r in before.calculations])
            for item in expanded['calculations'][:4]:
                self.assertFalse({'expr','condition','minimum_coverage','method'}.intersection(item))
