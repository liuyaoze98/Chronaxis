"""核对当前记录执行的实际信号投影、跨映射预设结果及显式输入诊断。

输入为合成memory/CSV两套等价A/V与mA/mV映射；充电和报警预设经真实读取
后输出平坦结果。两后端独立核手算Wh/Ah，CSV/JSONL再次发布保持原行。
实际读取定义与静态声明分开核，未使用aux不归一化；数据变化改变请求的
输入诊断摘要，不能把声明hash称为完整文件hash。默认不保存完整绑定树。
独立typed元数据测试显式请求详细输出，核冻结容器、方向及预算先于JSON复制。
所有文件只写work，设备home；没有真实业务验收或物理语义认证。
"""

from configuration_fixtures import current_fixture

# 数值手算与序列化分别验收；内部RecordSourceCursor只用于观察真实请求定义，不替换算法。
import csv
from dataclasses import FrozenInstanceError, asdict, replace
import json
from pathlib import Path
from sys import getsizeof
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis import AnalysisPlan, AnalysisResult, AnalysisRunner
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.record_source_cursor import RecordSourceCursor
from chronaxis.results import AnalysisError, BudgetExceededError, ResourceBudget, ResultSpool, RunMetadata
from chronaxis.results.binding_metadata import PresetBindingMetadata, PresetRoleMetadata
from chronaxis.results.codec import decode_row


class RunBindingMetadataTests(unittest.TestCase):
    """每例使用独立真实运行；清单只读快照不拥有输入，结果close后共享RAM归零。"""

    def fixture(self, *, converted=False, backend='reference', semantics=True):
        """构建两个真实预设和五个信号，转换后的手算物理量相同。

        参数: converted使用CSV/mA/mV，否则memory/A/V；backend选择真实内核；
            semantics=False让角色全部显式绑定且不声明semantic_id。
        返回: work/config/path/plan/source_path/fields命名空间。异常: 原IO或静态构建错误传播。
        副作用: 仅写独立home合成work；公共JSON不添加typed-only方向反转字段。
        """
        # 两套来源在同一合成时钟上，名称、字段和额外单位换算均明确不同。
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/run-binding-metadata' / uuid4().hex
        work.mkdir(parents=True)
        source_name = 'mapped_sensor' if converted else 'sensor'
        names = ('bus.mode', 'bus.mA', 'bus.mV', 'bus.alarm', 'bus.aux') if converted else (
            'raw.mode', 'raw.current', 'raw.voltage', 'raw.alarm', 'raw.aux')
        data = ((0, 10, 0), (1, 10, 1), (2, 0, 0), (4, 0, 1))
        values = [(time, {names[0]: 1, names[1]: current * (1000 if converted else 1),
            names[2]: 400000 if converted else 400, names[3]: alarm, names[4]: 5})
            for time, current, alarm in data]
        source = dict(name=source_name, source_type='signal_csv' if converted else 'memory',
            time=dict(time_type='relative', unit='s', origin='binding-metadata-home'))
        source_path = None
        if converted:
            # 文件只存已解码信号值；CSV后端与内存后端沿同一完整绑定契约进入AnalysisRunner。
            source_path = work / 'signals.csv'
            with source_path.open('w', encoding='utf-8', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(('s',) + names)
                for time, row in values:
                    writer.writerow((time,) + tuple(row[name] for name in names))
            source.update(path=source_path.name, time_column='s')
        else:
            source['rows'] = [dict(time=str(time)+'s', values=row) for time, row in values]
        # 未用aux仍接受静态声明检查；运行清单只记录实际投影，完整aux配置保留在plan。
        signals = [dict(name=alias, source=source_name, field=field, dtype=dtype, unit=unit,
            valid_for='9s', mapping_version='milli-v2' if converted else 'native-v1')
            for alias, field, dtype, unit in zip(('mode', 'current', 'voltage', 'alarm', 'aux'), names,
                ('int64', 'float64', 'float64', 'bool', 'float64'), ('1', 'A', 'V', '1', 'custom_unit'))]
        signals[1].update(input_unit='mA' if converted else 'A', scale=.001 if converted else 1,
            sign_convention='positive_is_charge', measurement_location='pack_terminal',
            valid_range=[-1000, 1000], invalid_values=[-999], same_time_policy='last_by_sequence')
        signals[2].update(input_unit='mV' if converted else 'V', scale=.001 if converted else 1,
            measurement_location='pack_terminal')
        signals[3]['choices'] = [[0, False], [1, True]]
        signals[4].update(scale=2, offset=3, valid_for='7s', invalid_values=[-999], valid_range=[-10000, 10000])
        if semantics:
            # mode仍明确未配置语义，另外三个声明只用于预设候选和字段契约检查。
            for index, semantic in ((1, 'battery.current'), (2, 'battery.voltage'), (3, 'fault.alarm')):
                signals[index].update(semantic_id=semantic, semantic_contract_version='1')
        role_bindings = {'mode': 'mode', 'current': 'current'}
        if not semantics:
            # 无语义时完整显式角色仍可通过，不能为可追溯性补造semantic_id。
            role_bindings['voltage'] = 'voltage'
        config = dict(config_version=3,
            dataset=dict(name='binding_demo', entity='synthetic_device', session='binding_session',
                domain=dict(start='0s', end='4s')), sources=[source], signals=signals,
            presets=[dict(name='charging', preset_type='charge_session', version='1', role_bindings=role_bindings,
                parameters=dict(mode_value=1, current_min=5, minimum_duration='1s', compute_energy=True,
                    compute_charge=True, minimum_coverage=.95)),
                dict(name='fault', preset_type='fault_context', version='1',
                    role_bindings={} if semantics else {'alarm': 'alarm'}, parameters=dict(pre='1s', post='2s'))],
            execution=dict(backend=backend, batch_rows=2, result_buffer_rows=1, memory_budget_bytes=256*1024**2),
            outputs=dict(tables='csv' if backend == 'reference' else 'jsonl', manifest='json'),
            diagnostics=dict(trace=True, integrity=True),
            metadata=dict(device_label='home', data_kind='synthetic'))
        # 公共构建器先真实展开两preset；后续不替换plan所属来源、绑定或编译树。
        path = work / 'plan.json'
        path.write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        return SimpleNamespace(work=work, config=config, path=path, source_path=source_path,
            fields=names, plan=AnalysisPlan.from_dict(current_fixture(config), base_dir=work))

    def public_run(self, data):
        """观察同次来源实际请求的定义，不制造旧历史绑定hash。

        参数: data为合成计划。返回: 结果、实际输入诊断、实际定义tuple。
        异常: 原读取错误；只观察真实构造后返回，结果登记关闭。
        """
        original, captured = RecordSourceCursor.__init__, []
        def observe(owner, plan, source, definitions, *args, **options):
            """透明调用原来源构造并观察投影。参数: 原调用。返回: None。异常: 原错误。"""
            original(owner, plan, source, definitions, *args, **options)
            self.assertEqual(tuple(item.name for item in definitions), ('mode','current','voltage','alarm'))
            for definition in definitions:
                self.assertIs(definition, data.plan.bindings.resolve(definition.name))
            captured.append(definitions)
        with patch.object(RecordSourceCursor, '__init__', observe):
            result = AnalysisRunner().run(data.plan, work_dir=data.work / ('run-'+uuid4().hex))
        self.addCleanup(result.close)
        self.assertEqual(len(captured), 1)
        self.assertTrue(result.metadata.input_diagnostics)
        self.assertTrue(all(fact.source_eof for fact in result.metadata.input_diagnostics))
        # 当前默认不保存完整绑定树；所需输入及诊断只来自这次已完成读取。
        self.assertEqual(result.metadata.signal_bindings, ())
        self.assertEqual(result.metadata.mapping_hashes, ())
        return result, result.metadata.input_diagnostics, captured[0]

    def table_rows(self, result):
        """读完三张真实结果表并关闭各游标，不重新读取来源。

        参数: result为尚活结果。返回: table到typed行tuple的有限手算样例dict。
        异常: 原读取错误传播；finally关闭真实游标，失败不留借用FD。
        """
        rows = {}
        # 同时最多持一个结果reader；样例行很少，tuple仅用于独立发布回读比对。
        for table, factory in (('events', result.iter_events), ('segments', result.iter_segments), ('calculations', result.iter_calculations)):
            reader = factory()
            try:
                rows[table] = tuple(reader)
            finally:
                reader.close()
        return rows

    def close_result(self, result):
        """释放唯一结果owner并核实际共享账本归零。

        参数: result为真实返回结果。返回: None。异常: 费用残留或重复close故障由断言报告。
        """
        budget = result.spool.budget
        result.close()
        result.close()
        self.assertEqual(budget.ram_bytes, 0)


    def declared_metadata(self):
        """建立明确的有限声明元数据，测试按请求输出及实体费用。

        参数: 无。返回: (RunMetadata,声明字段dict)。异常: 原模型格式错误传播。
        """
        # 明确夹具既含非空可选tuple，也保空默认值；不能靠只比较字段数量漏掉变化。
        expected = dict(run_id='legacy-home', input_identity='synthetic-input', plan_hash='synthetic-plan',
            backend='reference', config_version=3, source_time_interpretation='relative ns; explicit origin',
            session_boundaries=(('session', 0, 100),), started_at='2026-10-16T01:00:00+08:00',
            mapping_hashes=('declared-binding',), dbc_hashes=(), parsing_policy='decoded-results',
            worker_config='single-thread', dependency_versions=(('numpy', '1.26.3'),), limitations=('synthetic only',),
            software_version='0.1.0.dev0',  device_label='home')
        return RunMetadata(**expected), expected

    def test_real_runner_bindings_presets_and_both_published_formats_roundtrip(self):
        """两映射两后端按实际投影计算，显式诊断与平坦表均可发布回读。参数: 无。返回: None。异常: 追溯或手算不符。"""
        identities = {}
        # reference实际发布CSV，NumPy实际发布JSONL；两者分别核同一手算，不借一个内核作另一个的真值。
        for converted in (False, True):
            for backend in ('reference', 'numpy'):
                with self.subTest(converted=converted, backend=backend):
                    data = self.fixture(converted=converted, backend=backend)
                    result, identity, _ = self.public_run(data)
                    run = result.run_manifest['run']
                    self.assertNotIn('signal_bindings', run)
                    self.assertEqual(run['plan_hash'], data.plan.identity)
                    self.assertEqual(run['backend'], backend)
                    self.assertEqual(run['input_diagnostics'], [fact.to_dict() for fact in identity])
                    # 两秒10A、400V活动从onset积分，不能因1秒确认裁掉头部面积。
                    tables = self.table_rows(result)
                    self.assertEqual(len(tables['calculations']), 2)
                    self.assertEqual({row.calculation_id for row in tables['calculations']}, {'charging_energy', 'charging_charge'})
                    expected = {'charging_energy': (8000/3600, 'Wh'), 'charging_charge': (20/3600, 'Ah')}
                    # 一个真实活动只应各生成一条Wh/Ah结果，集合和值正确也不能掩盖重复行。
                    for calculation_id in expected:
                        self.assertEqual(sum(row.calculation_id == calculation_id for row in tables['calculations']), 1)
                    for row in tables['calculations']:
                        value, unit = expected[row.calculation_id]
                        self.assertAlmostEqual(row.value, value, delta=1e-12)
                        self.assertEqual(row.unit, unit)
                    # 清单和三表真正经过Windows发布关闭后，再从磁盘回读完整typed记录。
                    manifest = result.write(data.work / 'published')
                    published = json.loads(manifest.manifest_path.read_text(encoding='utf-8'))
                    self.assertEqual(published['status'], 'completed')
                    self.assertEqual(published['run'], json.loads(json.dumps(current_fixture(run))))
                    for table, expected_rows in tables.items():
                        path = manifest.output_dir / (table+'.'+data.plan.outputs.tables)
                        if data.plan.outputs.tables == 'csv':
                            with path.open(encoding='utf-8', newline='') as handle:
                                rows = tuple(csv.DictReader(handle))
                            self.assertEqual(len(rows),len(expected_rows))
                            for actual,expected_row in zip(rows,expected_rows):
                                expected_fields=asdict(expected_row)
                                self.assertEqual(set(actual),set(expected_fields))
                                for key,value in expected_fields.items():
                                    if isinstance(value,tuple):
                                        self.assertEqual(json.loads(actual[key]),list(value))
                                    else:
                                        self.assertEqual(actual[key],'' if value is None else str(int(value)) if key=='quality' else str(value))
                            continue
                        else:
                            with path.open('rb') as handle:
                                rows = tuple(decode_row(line, result.spool.max_row_bytes) for line in handle)
                        self.assertEqual(rows, expected_rows)
                    identities[converted, backend] = (data.plan.bindings.identity, identity)
                    self.close_result(result)
        # 同别名改来源/字段/转换必改变实际绑定和输入身份，防止跨任务沿旧映射缓存。
        for backend in ('reference', 'numpy'):
            self.assertNotEqual(identities[False, backend], identities[True, backend])

    def test_absent_semantics_stay_none_and_metadata_snapshots_are_immutable(self):
        """实际请求定义保None，显式角色由静态契约核验；默认清单不伪造物理证明。

        参数: 无。返回: None。异常: 隐式补语义或可变快照污染时断言失败。
        """
        data = self.fixture(semantics=False)
        result, _, definitions = self.public_run(data)
        self.assertTrue(all(item.semantic_id is None and item.semantic_contract_version is None for item in definitions))
        for roles in data.plan.preset_bindings:
            for role in roles:
                self.assertEqual(role.resolution, 'explicit')
                self.assertIn(role.definition, definitions)
        with self.assertRaises(FrozenInstanceError):
            definitions[0].field = 'other'
        with self.assertRaises(FrozenInstanceError):
            result.metadata.signal_bindings = definitions
        run = result.run_manifest['run']
        self.assertNotIn('signal_bindings', run)
        self.assertNotIn('preset_bindings', run)
        run['input_diagnostics'][0]['source'] = 'mutated'
        self.assertNotEqual(result.run_manifest['run']['input_diagnostics'][0]['source'], 'mutated')
        self.close_result(result)

    def test_actual_input_changes_requested_digest_without_replacing_declared_plan(self):
        """同一个CSV计划实际值改变应改变显式输入摘要，声明hash保持不变。参数: 无。返回: None。异常: 陈旧绑定。"""
        data = self.fixture(converted=True)
        first, first_identity, _ = self.public_run(data)
        first_run = first.metadata.to_dict()
        self.close_result(first)
        # 原plan和定位声明不变，只替当前真实文件中的电流原值，显式请求的诊断摘要必须跟着实际输入值改变。
        with data.source_path.open(encoding='utf-8', newline='') as handle:
            rows = list(csv.reader(handle))
        current_index = rows[0].index(data.fields[1])
        rows[1][current_index] = '20000'
        with data.source_path.open('w', encoding='utf-8', newline='') as handle:
            csv.writer(handle).writerows(rows)
        second, second_identity, _ = self.public_run(data)
        second_run = second.metadata.to_dict()
        self.assertEqual(first_run['plan_hash'], second_run['plan_hash'])
        self.assertEqual(first_run['plan_hash'], data.plan.identity)
        self.assertNotIn('mapping_hashes', second_run)
        self.assertNotEqual(first_identity, second_identity)
        self.assertNotEqual(first_run['input_diagnostics'], second_run['input_diagnostics'])
        self.assertEqual(first.metadata.signal_bindings, second.metadata.signal_bindings)
        self.close_result(second)

    def test_unused_aux_is_not_normalized_for_either_backend(self):
        """未用aux不生成普通样本，两后端仍实际运行预设并保原手算结果。

        参数: 无。返回: None。异常: aux进入归一化、保持或运行证据时断言失败。
        这里只观察原normalizer调用并委托原函数；不替换算法、读请求或结果。
        """
        from chronaxis.sources import packing
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                data = self.fixture(backend=backend)
                name = 'normalize_reference' if backend == 'reference' else 'normalize_numpy'
                original = getattr(packing, name)
                visited = set()

                def normalize(definition, *args, **kwargs):
                    """记录真实消费定义后委托原归一化。参数: 原调用参数。返回: 原结果。异常: 原错或aux断言。"""
                    self.assertNotEqual(definition.name, 'aux')
                    visited.add(definition.name)
                    return original(definition, *args, **kwargs)

                with patch.object(packing, name, side_effect=normalize):
                    result, _, _ = self.public_run(data)
                self.assertEqual(visited, {'mode', 'current', 'voltage', 'alarm'})
                rows = self.table_rows(result)['calculations']
                self.assertEqual({row.calculation_id for row in rows}, {'charging_energy', 'charging_charge'})
                expected = {'charging_energy': 8000 / 3600, 'charging_charge': 20 / 3600}
                for row in rows:
                    self.assertAlmostEqual(row.value, expected[row.calculation_id], delta=1e-12)
                self.close_result(result)

    def test_default_metadata_is_compact_and_owns_its_actual_fee(self):
        """默认只复制必要字段，显式已有值保留，费用覆盖仍持有的声明。

        参数: 无。返回: None。异常: 默认展开完整绑定或费用不符即失败。
        """
        metadata, declared = self.declared_metadata()
        keys=('run_id','plan_hash','backend','config_version','started_at','device_label',
              'software_version','source_time_interpretation','parsing_policy','worker_config',
              'input_identity','session_boundaries','limitations','dependency_versions')
        expected={name:declared[name] for name in keys}
        expected.update(retain_work=False,detailed_diagnostics=False)
        self.assertEqual(metadata.to_dict(),expected)
        self.assertNotIn('signal_bindings',metadata.to_dict())
        self.assertNotIn('mapping_hashes',metadata.to_dict())
        def owned_size(value):
            """独立计算当前确实保存的tuple实体费用。参数: 标量/tuple。返回: bytes。异常: 无。"""
            if type(value) is tuple:
                return getsizeof(value)+sum(owned_size(item)+32 for item in value)
            return getsizeof(value)
        self.assertEqual(metadata.estimated_bytes(),8192+16*sum(owned_size(value)+256 for value in declared.values()))

    def test_typed_direction_choices_and_contract_records_preserve_complete_declared_facts(self):
        """typed专有反转证据、枚举/None及角色状态不丢，不能伪称公共JSON支持。参数: 无。返回: None。异常: 漏字段或误称物理已验。"""
        metadata, _ = self.declared_metadata()
        # direction_factor/input_sign_convention尚非公共JSON字段，此例只验证已有typed定义追溯。
        reverse = SignalDefinition('current', 'typed_source', 'raw.mA', D.FLOAT64, 'A', 9_000_000_000,
            input_unit='mA', scale=-.001, direction_factor=-1, input_sign_convention='positive_is_discharge',
            sign_convention='positive_is_charge', measurement_location='pack_terminal',
            semantic_id='battery.current', semantic_contract_version='1', mapping_version='typed-v3',
            valid_range=(-1000, 1000), invalid_values=(-999, float('nan'), float('inf'), float('-inf')),
            same_time_policy='last_by_sequence')
        state = SignalDefinition('state', 'typed_source', 'raw.state', D.ENUM, '1', 8_000_000_000,
            choices=((0, 'idle'), (1, 'active')), invalid_values=(None,))
        role = PresetRoleMetadata('current', 'current', 'explicit', '1')
        preset = PresetBindingMetadata('charging', 'charge_session', '1', (role,))
        detailed = replace(metadata, signal_bindings=(reverse, state), preset_bindings=(preset,), detailed_diagnostics=True)
        run = json.loads(json.dumps(current_fixture(detailed.to_dict()), ensure_ascii=False, allow_nan=False))
        actual = run['signal_bindings'][0]
        self.assertEqual((actual['input_unit'], actual['unit'], actual['scale'], actual['offset']), ('mA', 'A', -.001, 0))
        self.assertEqual((actual['input_sign_convention'], actual['sign_convention'], actual['direction_factor']),
            ('positive_is_discharge', 'positive_is_charge', -1))
        self.assertEqual(actual['semantic_status'], 'declared')
        self.assertEqual(actual['unit_status'], 'verified')
        self.assertEqual(actual['invalid_values'], [-999, {'diagnostic_float': 'nan'},
            {'diagnostic_float': 'inf'}, {'diagnostic_float': '-inf'}])
        self.assertEqual(run['signal_bindings'][1]['choices'], [[0, 'idle'], [1, 'active']])
        self.assertEqual(run['signal_bindings'][1]['invalid_values'], [None])
        self.assertEqual(run['signal_bindings'][1]['semantic_status'], 'not_provided')
        self.assertEqual(run['preset_bindings'][0]['roles'][0]['contract_status'], 'checked_against_declared_metadata')
        self.assertGreater(detailed.estimated_bytes(), metadata.estimated_bytes())
        # 只读记录拒绝通过修改status或容器来暗示另有物理验证步骤。
        with self.assertRaises(FrozenInstanceError):
            role.contract_status = 'physically_verified'
        with self.assertRaises((TypeError, ValueError)):
            PresetRoleMetadata('current', 'current', 'explicit', '1', 'physically_verified')
        with self.assertRaises((TypeError, ValueError)):
            replace(metadata, signal_bindings=[reverse])
        with self.assertRaises((TypeError, ValueError)):
            PresetBindingMetadata('charging', 'charge_session', '1', [role])

    def test_large_binding_metadata_reserves_before_json_copy_and_closes_owned_spool(self):
        """真实预算先拒大绑定树，to_dict未运行且失败owner清空自有费用。参数: 无。返回: None。异常: 先分配JSON或漏账。"""
        metadata, _ = self.declared_metadata()
        # 大文本由调用方提供；结果层必须先预留新副本费用，不能先asdict/JSON再碰限额。
        signal = SignalDefinition('large', 'source', 'field', D.FLOAT64, '1', 1,
            semantic_id='synthetic.'+'x'*262144)
        detailed = replace(metadata, signal_bindings=(signal,), detailed_diagnostics=True)
        budget = ResourceBudget(1024*1024)
        self.assertGreater(detailed.estimated_bytes(), budget.memory_budget_bytes)
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/run-binding-metadata' / uuid4().hex
        spool = ResultSpool(budget, work, result_buffer_rows=1, requested_tables=('calculations',))
        self.addCleanup(spool.close)
        spool.seal()
        # 封口暂存是真实owner，接管后构造失败应由AnalysisResult关闭，不能留借用固定账。
        self.assertGreater(budget.ram_bytes, 0)
        with patch.object(RunMetadata, 'to_dict', side_effect=AssertionError('预算拒绝前已复制JSON')) as convert:
            with self.assertRaises(AnalysisError) as caught:
                AnalysisResult(spool, detailed)
        convert.assert_not_called()
        self.assertIsInstance(caught.exception.__cause__, BudgetExceededError)
        self.assertTrue(spool._closed)
        self.assertEqual(budget.ram_bytes, 0)
        self.assertFalse((work / 'analysis_manifest.json').exists())
