"""[home] 配置分组只影响声明位置；实际数据与时间含义保持。

合成内存序列和ASC用于核对换算、局部周期及固定时区；临时产物独立关闭。
不修改历史目录，不用被测算法产生期望值。
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError
from chronaxis.planning.config_groups import normalize_configuration, public_configuration


def config():
    """0/1/2秒功率1/2/3W；前值保持总面积3J，输入kW换算为W后为3000J。"""
    return dict(config_version=3,dataset=dict(name='groups',domain=dict(start='0s',end='2s')),
        sources=[dict(source_type='memory',rows=[dict(time='0s',values={'p':1.}),
            dict(time='1s',values={'p':2.}),dict(time='2s',values={'p':3.})])],
        signals=[dict(name='power',field='p',dtype='float64',unit='W',valid_for='3s')],
        calculations=[dict(name='energy',operation='integral',expr='power')])


class ConfigurationGroupsTests(unittest.TestCase):
    """校验当前分组、精确覆盖和必要错误，不增加默认数据扫描。"""

    def test_conversion_and_local_interval_actual_results(self):
        """conversion将kW换为W后面积3000J；本节点固定0.1秒则为300J，另一节点仍用实际间隔。"""
        raw=config();raw['signals'][0]['conversion']={'scale':1000,'offset':0,'input_unit':'kW'}
        raw['calculations'].append(dict(name='fixed',operation='integral',expr='power',
            interval=dict(mode='fixed',value='0.1s')))
        before=deepcopy(raw);plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(raw,before)
        with TemporaryDirectory(prefix='chronaxis-groups-') as directory:
            for backend in ('reference','numpy'):
                with AnalysisRunner(backend).run(plan,work_dir=Path(directory)/backend) as result:
                    values={row.calculation_id:row.value for row in result.iter_calculations()}
                    self.assertEqual(values['energy'],3000.)
                    self.assertAlmostEqual(values['fixed'],300.)

    def test_scope_objects_and_output_roundtrip(self):
        """规则/窗口引用只变声明位置，不改内部范围；全部窗口不会撞用户窗口名all。"""
        raw=config();raw['rules']=[dict(name='high',rule_type='condition_duration',condition='power > 1',minimum_duration='0s')]
        raw['windows']=[dict(name='around',rule='high')]
        raw['calculations'][0]['scope']={'rule':'high'}
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.calculations[0].scope,'event:high')
        raw['calculations'][0]['scope']={'window':'around'}
        self.assertEqual(AnalysisPlan.from_dict(raw).calculations[0].scope,'segment:around')
        raw['outputs']={'can_frames':dict(scope={'windows':'all'}),
                        'signal_csv':dict(scope={'window':'around'})}
        converted=normalize_configuration(raw)
        self.assertEqual(converted['outputs']['can_frames']['scope'],'segments')
        self.assertEqual(public_configuration(converted),raw)

    def test_old_fields_and_bad_scope_are_rejected(self):
        """旧扁平声明不作为兼容别名；错误参数不会因为新分组存在而被掩盖。"""
        variants=[]
        raw=config();raw['signals'][0]['scale']=2;variants.append(raw)
        raw=config();raw['sources'][0]['reader_options']={};variants.append(raw)
        raw=config();raw['intervals']={'overrides':{}};variants.append(raw)
        raw=config();raw['calculations'][0]['scope']='event:high';variants.append(raw)
        raw=config();raw['calculations'][0]['scope']={'rule':'a','window':'b'};variants.append(raw)
        raw=config();raw['sources'][0]['reader']={'decode_policy':'strict'};variants.append(raw)
        raw=config();raw['signals'][0]['conversion']=None;variants.append(raw)
        for raw in variants:
            with self.subTest(raw=raw),self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(raw)

    def test_reader_and_fixed_timezone_preserve_native_contract(self):
        """ASC的+08:00统一以timezone传递；拒绝在relative数据上附加时区或旧分钟字段。"""
        raw=config();raw['sources']=[dict(source_type='can_asc',path='not-read.asc',
            dbc_by_channel={'1':'not-read.dbc'},time=dict(time_type='absolute',unit='s',timezone='+08:00'),
            reader=dict(decode_policy='partial',encoding='utf-8-sig'))]
        raw['signals'][0]['field']=dict(frame_id=256,signal='Power')
        raw['dataset']['domain']=dict(start='2026-01-01T00:00:00+08:00',end='2026-01-01T00:00:02+08:00')
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.sources[0].timezone_text,'+08:00')
        self.assertEqual(plan.sources[0].config.decode_policy,'partial')
        self.assertEqual(plan.sources[0].config.inputs[0].timezone_offset_minutes,480)
        raw['sources'][0]['time']['timezone_offset_minutes']=480
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(raw)

    def test_reader_signal_csv_and_empty_can_reader(self):
        """空reader不制造ASC/BLF不适用字段，信号CSV读取选项仍进入同一Spec。"""
        raw=config();raw['sources']=[dict(source_type='signal_csv',path='not-read.csv',time_column='time',
            time={'unit':'s'},reader=dict(encoding='utf-8',delimiter=';',missing_values=['NA']))]
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.sources[0].config.delimiter,';')
        raw['sources']=[dict(path='not-read.blf',dbc_by_channel={'1':'not-read.dbc'},reader={})]
        raw['signals'][0]['field']=dict(frame_id=256,signal='Power')
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.sources[0].source_type,'can_blf')

    def test_clock_grid_start_and_local_error_locations(self):
        """共享时间基准名称与采样网格起点不混用；局部间隔错误指回本节点。"""
        raw=config();raw['sources'][0]['time']={'clock':'recording_a'}
        plan=AnalysisPlan.from_dict(raw)
        self.assertEqual(plan.sources[0].config.timebase.origin,'recording_a')
        original=deepcopy(raw)
        raw['outputs']={'signal_csv':{'scope':'session','resampling':{'start':'0.5s'}}}
        internal=normalize_configuration(raw)
        self.assertEqual(internal['outputs']['signal_csv']['resampling']['origin'],'0.5s')
        self.assertEqual(public_configuration(internal),raw)
        raw=original;raw['calculations'][0]['interval']={'mode':'fixed','value':'0s'}
        with self.assertRaises(PlanValidationError) as caught:AnalysisPlan.from_dict(raw)
        self.assertEqual(caught.exception.path,'$.calculations[0].interval.value')
        raw=config();raw['sources'][0]['time']={'origin':'recording_a'}
        with self.assertRaises(PlanValidationError) as caught:AnalysisPlan.from_dict(raw)
        self.assertEqual(caught.exception.path,'$.sources[0].time.origin')

    def test_export_timezone_uses_same_public_spelling(self):
        """原帧导出的固定时区与来源同用timezone，内部仍传分钟，不改变实际日期。"""
        raw=config();raw['outputs']={'can_frames':{'timezone':'+08:00'}}
        converted=normalize_configuration(raw)
        self.assertEqual(converted['outputs']['can_frames']['timezone_offset_minutes'],480)
        self.assertEqual(public_configuration(converted),raw)
        raw['outputs']['can_frames']['timezone']='UTC'
        self.assertEqual(normalize_configuration(raw)['outputs']['can_frames']['timezone_offset_minutes'],0)
        raw['outputs']['can_frames']={'timezone_offset_minutes':480}
        with self.assertRaises(PlanValidationError):normalize_configuration(raw)
        raw['outputs']['can_frames']={'timezone':'+00:60'}
        with self.assertRaises(PlanValidationError):normalize_configuration(raw)

    def test_public_preset_fragment_merges_without_internal_adapter(self):
        """公开片段直接合入计划；不能要求用户再把内部event串改成scope对象。"""
        from chronaxis.presets import PresetSpec,build_preset
        raw=config();raw.pop('calculations')
        raw['signals'][0]['unit']='degC';raw['signals'][0]['name']='temperature'
        raw['sources'][0]['rows']=[dict(time='0s',values={'p':85.}),
            dict(time='1s',values={'p':77.}),dict(time='2s',values={'p':70.})]
        base=AnalysisPlan.from_dict(raw)
        spec=PresetSpec.from_dict(dict(name='heat',preset_type='threshold_excursion',
            role_bindings={'signal':'temperature'},parameters={'enter_threshold':80,'exit_threshold':75}))
        fragment=build_preset(spec,tuple(s.definition for s in base.signals)).to_dict()
        self.assertTrue(all(c['scope']=='session' or isinstance(c['scope'],dict) for c in fragment['calculations']))
        direct=deepcopy(raw);direct.update(fragment)
        configured=deepcopy(raw);configured['presets']=[dict(name='heat',preset_type='threshold_excursion',
            role_bindings={'signal':'temperature'},parameters={'enter_threshold':80,'exit_threshold':75})]
        for backend in ('reference','numpy'):
            with TemporaryDirectory(prefix='chronaxis-public-fragment-') as directory:
                for index,item in enumerate((direct,configured)):
                    with AnalysisRunner(backend).run(AnalysisPlan.from_dict(item),Path(directory)/str(index)) as result:
                        rows=list(result.iter_calculations())
                        self.assertEqual(rows[0].value,2.)
                        self.assertEqual([(e.start_ns,e.end_ns) for e in result.iter_events()],[(0,2_000_000_000)])
