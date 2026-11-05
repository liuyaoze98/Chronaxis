"""从公开AnalysisRunner核三格式周期统计，不从某个后端复制预期。

合成三帧4000/4800/8000W，固定或DBC的两个0.1秒周期应为880J。
默认不保历史或贡献；旧入口另由既有回归核验。
"""
from published_paths import published_file


from configuration_fixtures import current_fixture

from copy import deepcopy
from dataclasses import replace
from itertools import product
from uuid import uuid4
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner, validate_analysis_plan
from chronaxis.results import SummaryCalculationRow, AnalysisError
from test_current_message_calculation import config
import test_raw_can_continuous as files


class RecordRunnerTests(unittest.TestCase):
    """同一手算覆盖读取、DBC周期、真实时间保持、累计和精简结果。"""

    setUp = files.RawCANContinuousTests.setUp
    asc = files.RawCANContinuousTests.asc
    csv = files.RawCANContinuousTests.csv
    blf = files.RawCANContinuousTests.blf

    def plan(self, kind, path, mode='fixed', edit=None):
        """建立普通功率表达式计划。参数: 格式/路径/模式。返回: 计划。异常: 静态校验错。"""
        raw = config(kind)
        raw.pop('message_calculations')
        raw['dataset']['domain'] = dict(start='0s', end='0.3s')
        signal = raw['signals'][0]
        signal.update(name='voltage', unit='V', conversion={'input_unit':'V'}, valid_for='1s')
        signal['field']['signal'] = 'Voltage'
        current = deepcopy(signal)
        current.update(name='current', unit='A', conversion={'input_unit':'A'})
        current['field']['signal'] = 'Current'
        raw['signals'].append(current)
        raw['derived'] = dict(power=dict(expr='voltage * current', unit='W'))
        raw['calculations'] = [dict(name='energy', scope='session', operation='integral', expr='power', unit='J'),
                          dict(name='mean', scope='session', operation='time_weighted_mean', expr='power', unit='W')]
        choice = dict(mode=mode)
        if mode != 'actual':
            choice['driver'] = 'current'
        if mode == 'fixed':
            choice['value'] = '0.1s'
        raw['intervals'] = dict(default=choice)
        raw['sources'][0]['path'] = str(path.absolute())
        raw['sources'][0]['dbc_by_channel'] = {'1': str(self.dbc.absolute())}
        if edit is not None:
            edit(raw)
        plan = AnalysisPlan.from_dict(current_fixture(raw))
        if kind == 'can_blf':
            source = plan.sources[0]
            plan = replace(plan, sources=(replace(source, config=replace(source.config,
                offset_ns=-1700000000*10**9)),))
        return plan

    def fixtures(self):
        """写独立三格式与DBC。参数: 无。返回: 格式路径映射。异常: I/O错误。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 2 Node\n SG_ Voltage : 0|8@1+ (2,0) [0|510] "V" Node\n'
            ' SG_ Current : 8|8@1+ (1,0) [0|255] "A" Node\n'
            'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 100000;\n'
            'BA_ "GenMsgCycleTime" BO_ 256 100;\n', encoding='utf-8')
        return dict(can_blf=self.blf(((0., bytes([200,10])),(.12, bytes([200,12])),(.3, bytes([200,20])))),
            can_asc=self.asc('0.00 1 100 Rx d 2 C8 0A\n0.12 1 100 Rx d 2 C8 0C\n0.30 1 100 Rx d 2 C8 14\n').path,
            raw_can_csv=self.csv('0,100,C8 0A,2\n0.12,100,C8 0C,2\n0.30,100,C8 14,2\n').path)

    def test_public_three_formats_two_backends_and_modes(self):
        """全部18种组合符合各自手算，结果仅含请求指标且关闭释放预算。"""
        for (kind, path), backend, mode in product(self.fixtures().items(), ('reference','numpy'), ('actual','fixed','dbc')):
            with self.subTest(kind=kind, backend=backend, mode=mode):
                plan = self.plan(kind, path, mode)
                self.assertTrue(validate_analysis_plan(plan).execution_ready)
                root = self.root / uuid4().hex
                with patch('chronaxis.execution.history.DecodedHistoryStore', side_effect=AssertionError('unexpected history')):
                    result = AnalysisRunner(backend).run(plan, work_dir=root)
                self.addCleanup(result.close)
                rows = tuple(result.iter_calculations())
                self.assertTrue(all(type(row) is SummaryCalculationRow for row in rows))
                values = {row.calculation_id: row.value for row in rows}
                self.assertAlmostEqual(values['energy'], 1344. if mode == 'actual' else 880., places=3)
                self.assertAlmostEqual(values['mean'], 4480. if mode == 'actual' else 4400., places=3)
                self.assertEqual(set(result.spool.counts), {'calculations'})
                budget = result.spool._budget
                result.close()
                self.assertEqual(budget.ram_bytes, 0)
                self.assertFalse(root.exists())

    def test_requested_coverage_does_not_change_value_or_default_rows(self):
        """0.12秒更新后有效到0.27秒，覆盖0.27/0.3；未请求的均值不附覆盖字段。"""
        import csv,json
        from chronaxis.results.summary import SummaryCoverageCalculationRow
        from chronaxis.results.codec import encode_row,decode_row
        paths=self.fixtures()
        for backend,mode,threshold in product(('reference','numpy'),('actual','fixed'),(.8,.95)):
            def edit(raw):
                """只为能量明确覆盖门槛。参数: raw。返回: None。异常: 无。"""
                raw['signals'][0]['valid_for']='0.15s'
                raw['calculations'][0].update(minimum_coverage=threshold)
            with self.subTest(backend=backend,mode=mode,threshold=threshold):
                result=AnalysisRunner(backend).run(self.plan('can_asc',paths['can_asc'],mode,edit),self.root/uuid4().hex)
                self.addCleanup(result.close)
                rows={row.calculation_id:row for row in result.iter_calculations()}
                energy=rows['energy']
                self.assertIs(type(energy),SummaryCoverageCalculationRow)
                self.assertEqual(energy.coverage_status,'sufficient' if threshold==.8 else 'indeterminate')
                self.assertEqual(energy.value,1200. if mode=='actual' else 800.)
                self.assertEqual(energy.status,'partial')
                self.assertIs(type(rows['mean']),SummaryCalculationRow)
                self.assertEqual(decode_row(encode_row(energy,1048576),1048576),energy)
                output=self.root/uuid4().hex
                result.table_format = 'csv'  # 验收显式交换格式。
                published=result.write(output)
                manifest=json.loads((published_file(published,'run_manifest.json')).read_text(encoding='utf-8'))
                self.assertEqual(manifest['row_schema_versions']['calculations'],[7,10])

    def test_raw_clock_only_skips_value_normalization(self):
        """原始三格式中的电流只用作时钟，不生成它的数值归一化结果。"""
        from chronaxis.execution import raw_signal_groups
        original=raw_signal_groups.pack_message_values
        def needed(definition,values,backend):
            """拒绝无关数值工作。参数: 定义/值/后端。返回: 原结果。异常: 断言。"""
            self.assertNotEqual(definition.name,'current')
            return original(definition,values,backend)
        for kind,path in self.fixtures().items():
            def edit(raw):
                """只请求电压均值，驱动仍是电流报文。参数: raw。返回: None。异常: 无。"""
                raw['calculations']=[dict(name='mean',scope='session',operation='time_weighted_mean',expr='voltage',unit='V')]
            with patch.object(raw_signal_groups,'pack_message_values',needed):
                with AnalysisRunner().run(self.plan(kind,path,edit=edit),self.root/uuid4().hex) as result:
                    row,=tuple(result.iter_calculations())
                    self.assertEqual(row.value,400.)

    def test_expiry_condition_strict_and_no_observations(self):
        """真实0.15秒有效期不会被固定周期延长；report保800J，strict为空。"""
        paths = self.fixtures()
        for backend, policy in product(('reference','numpy'), ('report','strict')):
            def edit(raw):
                """明确TTL和条件。参数: 配置。返回: None。异常: 夹具错误。"""
                raw['signals'][0]['valid_for'] = '0.15s'
                raw['calculations'][0].update(partial_policy=policy, condition='current > 0')
            result = AnalysisRunner(backend).run(self.plan('can_asc', paths['can_asc'], edit=edit), self.root/uuid4().hex)
            self.addCleanup(result.close)
            row = next(row for row in result.iter_calculations() if row.calculation_id == 'energy')
            self.assertEqual(row.status, 'partial' if policy == 'report' else 'indeterminate')
            self.assertEqual(row.value, 800. if policy == 'report' else None)
            result.close()
        empty = self.asc('').path
        result = AnalysisRunner().run(self.plan('can_asc', empty), self.root/uuid4().hex)
        self.addCleanup(result.close)
        self.assertTrue(all(row.value is None for row in result.iter_calculations()))

    def test_clock_only_driver_and_unused_source(self):
        """独立时钟报文只触发，不解码其值；声明但未用的缺失文件不打开。"""
        self.fixtures()
        with self.dbc.open('a', encoding='utf-8') as handle:
            handle.write('BO_ 257 Clock: 1 Node\n SG_ Tick : 0|8@1+ (1,0) [0|255] "" Node\n')
        path = self.asc('0.00 1 100 Rx d 2 C8 0A\n0.00 1 101 Rx d 1 01\n'
                        '0.12 1 101 Rx d 1 02\n0.30 1 101 Rx d 1 03\n').path
        def edit(raw):
            """加入独立时钟与无关来源。参数: 配置。返回: None。异常: 夹具错误。"""
            clock = deepcopy(raw['signals'][0])
            clock.update(name='clock', unit='1', conversion={'input_unit':'1'})
            clock['field'].update(signal='Tick', frame_id=257)
            raw['signals'].append(clock)
            raw['intervals']['default']['driver'] = 'clock'
            unused = deepcopy(raw['sources'][0])
            unused.update(name='unused', path=str(self.root/'missing.asc'))
            raw['sources'].append(unused)
        plan = self.plan('can_asc', path, edit=edit)
        from chronaxis.planning.input_requirements import collect_input_requirements
        needed = collect_input_requirements(plan).for_source('bus')
        self.assertEqual(needed.clock_aliases, ('clock',))
        self.assertEqual(len(needed.required_fields), 2)
        import cantools
        original = cantools.database.can.message.Message.decode
        with patch.object(cantools.database.can.message.Message, 'decode', autospec=True, side_effect=original) as decode:
            result = AnalysisRunner().run(plan, self.root/uuid4().hex)
            self.addCleanup(result.close)
        self.assertEqual(decode.call_count, 1)
        self.assertEqual(next(row.value for row in result.iter_calculations() if row.calculation_id == 'energy'), 800.)

    def test_failed_read_and_cleanup_retry(self):
        """读取失败不返回前缀；目录删除故障可从最高会话重试。"""
        paths = self.fixtures()
        plan = self.plan('can_asc', paths['can_asc'])
        root = (self.root/uuid4().hex).resolve()
        with patch('chronaxis.execution.record_session_calculations.DriverExpression.evaluate', side_effect=OSError('calculation interrupted')):
            with self.assertRaises(AnalysisError):
                AnalysisRunner().run(plan, root)
        self.assertFalse(root.exists())
        with patch('chronaxis.execution.record_session_calculations.DriverExpression.evaluate', side_effect=OSError('calculation interrupted')):
            with patch('chronaxis.results.owned_directory.remove_owned_directory', side_effect=OSError('busy')):
                with self.assertRaises(AnalysisError) as caught:
                    AnalysisRunner().run(plan, root)
        owner = caught.exception.runner_cleanup_owner
        self.assertFalse(owner._closed)
        owner.close()
        self.assertFalse(root.exists())
        self.assertEqual(owner._budget.ram_bytes, 0)

    def test_publish_outside_work_and_explicit_retention(self):
        """发布文件不随close删除；临时根内部拒绝发布；显式留存保持现场。"""
        paths = self.fixtures()
        for retain in (False, True):
            def edit(raw):
                """声明独立留存开关。参数: 配置。返回: None。异常: 无。"""
                raw['diagnostics'] = dict(retain_work=retain)
            root = (self.root/uuid4().hex).resolve()
            result = AnalysisRunner().run(self.plan('can_asc', paths['can_asc'], edit=edit), root)
            self.addCleanup(result.close)
            if not retain:
                with self.assertRaises(AnalysisError):
                    result.write(root/'published')
                self.assertFalse((root/'published').exists())
            output = (self.root/uuid4().hex).resolve()
            result.table_format = 'csv'  # 验收显式交换格式。
            published=result.write(output)
            result.close()
            self.assertEqual(root.exists(), retain)
            self.assertTrue((published_file(published,'calculations.csv')).is_file())

    def test_metadata_preparation_does_not_read_input_or_reload_dbc(self):
        """文本初始化可重复且不碰缺失原始文件，第一次读取才报路径错误。"""
        from chronaxis.sources.text_can_decode import CANTextDecodeRead
        paths = self.fixtures()
        plan = self.plan('can_asc', paths['can_asc'])
        spec = plan.sources[0].config
        spec = replace(spec, inputs=(replace(spec.inputs[0], path=self.root/'missing.asc'),))
        import cantools
        with patch('cantools.database.load_file', wraps=cantools.database.load_file) as load:
            read = CANTextDecodeRead(spec, self.budget, tuple(item.definition for item in plan.signals))
            self.addCleanup(read.close)
            metadata = read.prepare_metadata()
            self.assertIs(read.prepare_metadata(), metadata)
            self.assertEqual(load.call_count, 1)
            self.assertEqual(read.count, 0)
            with self.assertRaises(FileNotFoundError):
                next(read)
        read.close()
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_explicit_actual_matches_current_default(self):
        """实际间隔与旧公开路径的值/状态一致，额外追溯不参与数值。"""
        from chronaxis.planning.checks import json_value
        paths = self.fixtures()
        def edit(raw):
            """同时请求持续时长及时间极值。参数: 配置。返回: None。异常: 无。"""
            raw['calculations'].extend((dict(name='duration', scope='session', operation='duration', condition='current > 0'),
                dict(name='minimum', scope='session', operation='min_time', expr='power'),
                dict(name='maximum', scope='session', operation='max_time', expr='power')))
            raw['signals'][0]['valid_for'] = '0.15s'
        plan = self.plan('can_asc', paths['can_asc'], mode='actual', edit=edit)
        old = json_value(plan.raw_config)
        old.update(config_version=4)
        old.pop('intervals')
        for backend in ('reference', 'numpy'):
            with AnalysisRunner(backend).run(plan, self.root/uuid4().hex) as new_result:
                new = {row.calculation_id: (row.value, row.status, row.reason) for row in new_result.iter_calculations()}
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(old)), self.root/uuid4().hex) as old_result:
                previous = {row.calculation_id: (row.value, row.status, row.reason)
                            for row in old_result.iter_calculations()}
            self.assertEqual(new, previous)

    def test_mixed_raw_and_parsed_sources_share_same_time(self):
        """ASC电压配CSV原帧或解析电流，DBC驱动仍在原帧中取；同刻收齐后880J。"""
        from chronaxis.planning.checks import json_value
        paths = self.fixtures()
        for parsed, backend, reverse in product((False,True),('reference','numpy'),(False,True)):
            raw = json_value(self.plan('can_asc', paths['can_asc'], mode='dbc').raw_config)
            if parsed:
                other = dict(name='other',source_type='memory',time=dict(time_type='relative',unit='s',origin='synthetic_origin'),
                    rows=[dict(time=t,values=dict(raw=v)) for t,v in (('0s',10),('0.12s',12),('0.3s',20))])
                raw['signals'][1]['field'] = 'raw'
                raw['intervals']['default']['driver'] = 'voltage'
            else:
                other = json_value(self.plan('raw_can_csv',paths['raw_can_csv']).raw_config)['sources'][0]
                other['name'] = 'other'
            raw['signals'][1]['source'] = 'other'
            raw['sources'].append(other)
            raw['execution'] = dict(batch_rows=1)
            if reverse:
                raw['sources'].reverse()
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                values = {row.calculation_id: row.value for row in result.iter_calculations()}
                self.assertEqual(values,dict(energy=880.,mean=4400.))


if __name__ == '__main__':
    unittest.main()
