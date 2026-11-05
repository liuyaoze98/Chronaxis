"""公开入口核解析表和多来源实时合并，独立手算不使用历史执行结果作真值。"""

from configuration_fixtures import current_fixture

from pathlib import Path
from tempfile import TemporaryDirectory
from itertools import product
from uuid import uuid4
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.results import AnalysisError


class RecordSourcesTests(unittest.TestCase):
    """在同刻跨来源/跨批更新后才求值，不依赖来源声明顺序。"""

    def setUp(self):
        """建立本次私有夹具。参数: 无。返回: None。异常: IO错误。"""
        self.directory = TemporaryDirectory(dir='work', prefix='record-sources-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()

    def config(self, kind='memory', mode='fixed', size=1, reverse=False, missing=False):
        """建立同步电压/电流两来源。参数: 来源形式/间隔/批大小/顺序/缺值。返回: dict。异常: IO错。"""
        raw = dict(config_version=4,
            dataset=dict(name='dataset', entity='device', session='session', domain=dict(start='0s',end='0.3s')),
            sources=[], signals=[], derived=dict(power=dict(expr='voltage * current', unit='W')),
            calculations=[dict(name='energy', scope='session', operation='integral', expr='power', unit='J'),
                     dict(name='mean', scope='session', operation='time_weighted_mean', expr='power', unit='W')],
            execution=dict(batch_rows=size), metadata=dict(device_label='home'))
        choice = dict(mode=mode)
        if mode == 'fixed':
            choice.update(value='0.1s',driver='current')
        raw['intervals'] = dict(default=choice)
        for alias, unit, values in (('voltage','V',(400,None if missing else 500,600)),('current','A',(10,12,20))):
            source = dict(name=alias, source_type=kind, time=dict(time_type='relative',unit='ns',origin='same_clock'))
            if kind == 'memory':
                source['rows'] = [dict(time=str(t)+'ns',values=dict(raw=value)) for t,value in zip((0,120000000,300000000),values)]
            else:
                path = self.root/(alias+uuid4().hex+'.csv')
                path.write_text('time,raw\n'+''.join(str(t)+','+('' if v is None else str(v))+'\n'
                    for t,v in zip((0,120000000,300000000),values)),encoding='utf-8')
                source.update(path=str(path),time_column='time')
            raw['sources'].append(source)
            raw['signals'].append(dict(name=alias,source=alias,field='raw',dtype='float64',unit=unit,valid_for='1s'))
        if reverse:
            raw['sources'].reverse()
        return raw

    def test_two_sources_formats_modes_backends_and_batches(self):
        """同刻400V/10A、500V/12A：周期1000J，实际1560J；排序与分批不影响。"""
        for kind, mode, backend, size in product(('memory','signal_csv'),('actual','fixed'),('reference','numpy'),(1,3)):
            with self.subTest(kind=kind,mode=mode,backend=backend,size=size):
                raw = self.config(kind,mode,size,reverse=size==3)
                with patch('chronaxis.execution.history.DecodedHistoryStore.__init__', side_effect=AssertionError('unrequested history')):
                    result = AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
                self.addCleanup(result.close)
                values = {row.calculation_id:row.value for row in result.iter_calculations()}
                self.assertEqual(values['energy'],1560. if mode=='actual' else 1000.)
                self.assertAlmostEqual(values['mean'],5200. if mode=='actual' else 5000.)
                budget = result.spool.budget
                result.close()
                self.assertEqual(budget.ram_bytes,0)

    def test_independent_clock_ignores_unused_values_and_original_copies(self):
        """电流只提供更新时间，坏电流文本不解析；按它推进电压均值为450V。"""
        from chronaxis.sources import packing
        from chronaxis.execution.batch_signal_groups import BatchSignalGroups
        original=packing._pack_numeric_columns
        consume=BatchSignalGroups.consume
        def compact(owner,batch):
            """验证从来源生成处就无原值副本。参数: owner/batch。返回: 原处理。异常: 断言或原错。"""
            self.assertTrue(all(column.original_values is None for column in batch.series.values()))
            return consume(owner,batch)
        def required_only(definition,values,backend):
            """确认纯时钟完全跳过归一化。参数: 定义/原值/后端。返回: 原结果。异常: 无关调用失败。"""
            self.assertNotEqual(definition.name,'current')
            return original(definition,values,backend)
        for kind,backend in product(('memory','signal_csv'),('reference','numpy')):
            raw=self.config(kind)
            raw['derived']={}
            raw['calculations']=[dict(name='mean',scope='session',operation='time_weighted_mean',expr='voltage',unit='V')]
            if kind=='memory':
                for row in raw['sources'][1]['rows']:
                    row['values']['raw']='not-a-number'
            else:
                Path(raw['sources'][1]['path']).write_text('time,raw\n0,not-a-number\n120000000,x\n300000000,y\n',encoding='utf-8')
            with self.subTest(kind=kind,backend=backend),patch.object(BatchSignalGroups,'consume',compact),patch.object(packing,'_pack_numeric_columns',required_only),patch(
                    'chronaxis.sources.signal_csv.CSVSourceRef',side_effect=AssertionError('unrequested detailed source')):
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                    row,=tuple(result.iter_calculations())
                    self.assertEqual(row.value,450.)
                    self.assertEqual(row.status,'complete')

    def test_ended_source_does_not_extend_to_other_source_end(self):
        """电压记录到0.12秒，电流到0.3秒；后半段不能继续使用末条电压。"""
        for mode,backend in product(('actual','fixed'),('reference','numpy')):
            raw=self.config(mode=mode,size=1)
            raw['sources'][0]['rows'].pop()
            result=AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
            self.addCleanup(result.close)
            rows={row.calculation_id:row for row in result.iter_calculations()}
            self.assertEqual(rows['energy'].value,480. if mode=='actual' else 400.)
            self.assertEqual(rows['energy'].status,'partial')
            self.assertEqual(rows['mean'].value,4000.)
            result.close()

    def test_non_driver_end_clips_original_pair_proportion(self):
        """0到0.3秒驱动对中电压在0.12秒结束：实际480J，固定周期按40%算160J。"""
        for mode,backend in product(('actual','fixed'),('reference','numpy')):
            raw=self.config(mode=mode,size=1)
            raw['sources'][0]['rows'].pop()
            raw['sources'][1]['rows'].pop(1)
            raw['sources'][1]['rows'].append(dict(time='500000000ns',values=dict(raw=20)))
            raw['dataset']['domain']['end']='0.5s'
            result=AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
            self.addCleanup(result.close)
            row=next(row for row in result.iter_calculations() if row.calculation_id=='energy')
            self.assertAlmostEqual(row.value,480. if mode=='actual' else 160.,places=12)
            self.assertEqual(row.status,'partial')
            result.close()

    def test_source_end_preserves_boolean_short_circuit(self):
        """已结束电压不会延长AND；电流仍真时OR不能被误判未知。"""
        for backend in ('reference','numpy'):
            raw=self.config(mode='actual',size=1)
            raw['sources'][0]['rows'].pop()
            raw['calculations']=[dict(name='both',scope='session',operation='duration',condition='voltage > 0 and current > 0'),
                            dict(name='either',scope='session',operation='duration',condition='voltage > 0 or current > 0')]
            result=AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
            self.addCleanup(result.close)
            values={row.calculation_id:row.value for row in result.iter_calculations()}
            self.assertAlmostEqual(values['both'],.12)
            self.assertAlmostEqual(values['either'],.3)
            result.close()

    def test_missing_update_replaces_old_value_and_source_fail_is_atomic(self):
        """第二组缺电压不可沿用400V，另一来源失败时不返回前缀。"""
        for kind in ('memory','signal_csv'):
            raw = self.config(kind,missing=True)
            with AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                energy = next(row for row in result.iter_calculations() if row.calculation_id=='energy')
                self.assertEqual((energy.value,energy.status),(400.,'partial'))
        raw = self.config('signal_csv')
        Path(raw['sources'][1]['path']).write_text('time,raw\n0,10\n120000000,12\nbad,20\n',encoding='utf-8')
        path = self.root/uuid4().hex
        with self.assertRaises(AnalysisError):
            AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),path)
        self.assertFalse(path.exists())

    def test_split_columns_same_time_group(self):
        """单宽表一批一列时，必须收齐电压电流再算，同刻重复沿原策略。"""
        raw = self.config('memory',size=1)
        raw['sources'] = [dict(name='table',source_type='memory',time=dict(time_type='relative',unit='ns',origin='same_clock'),
            rows=[dict(time=str(t)+'ns',values=dict(v=v,i=i)) for t,v,i in
                  ((0,400,10),(0,500,10),(120000000,600,12),(300000000,700,20))])]
        for signal, field in zip(raw['signals'], ('v','i')):
            signal.update(source='table',field=field,same_time_policy='last_by_sequence')
        with AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
            self.assertEqual(next(row.value for row in result.iter_calculations() if row.calculation_id=='energy'),1220.)

    def test_queue_delivery_cancellation_keeps_real_owner(self):
        """实际组已入队后取消，最高会话仍关闭队列/来源并归零，不返前缀。"""
        from chronaxis.execution.run_session import RunSession
        from chronaxis.execution.record_source_cursor import RecordSourceCursor
        error = KeyboardInterrupt('after enqueue')
        original = RecordSourceCursor._enqueue
        def interrupt(owner, group):
            """在真实入队后取消。参数: owner/group。返回: 无。异常: 原KeyboardInterrupt。"""
            original(owner, group)
            raise error
        path = self.root/uuid4().hex
        session = RunSession(AnalysisPlan.from_dict(current_fixture(self.config())),path)
        self.addCleanup(session.close)
        with patch.object(RecordSourceCursor,'_enqueue',interrupt):
            with self.assertRaises(KeyboardInterrupt) as caught:
                session.execute()
        self.assertIs(caught.exception,error)
        session.close()
        self.assertEqual(session._budget.ram_bytes,0)
        self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
