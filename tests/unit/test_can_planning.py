"""核对固定单BLF声明、原CAN定位与公共静态报告，不打开分析输入。

输入为纯JSON合成配置、单字段非法变体和冻结typed替换；输出是独立schema、
AnalysisPlan及AnalysisRunner.validate/explain的结构、身份与能力断言。测试只读取一次
公开schema，不生成BLF/DBC、不导入旧reader、CAN依赖或执行层，不启动进程。
CAN原消息/信号名保留点号和大小写，只有安全别名进入DSL；来源存在性、实际DBC
字段、运行单位、解码质量和进程RSS仍由后续实际读取证明。本专项不发布raw片段。
"""

from configuration_fixtures import current_fixture

# 独立标准schema验证与静态副作用探针，不复用其他TestCase充当本专项断言。
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import multiprocessing
from pathlib import Path
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator

# 公开入口只加载静态声明；六字段模型本身不依赖CAN库或DBC。
from chronaxis import AnalysisPlan, PlanValidationError, AnalysisRunner, explain_analysis_plan, validate_analysis_plan
from chronaxis.planning.config_groups import public_configuration
from chronaxis.legacy.records import LegacyCANField, PROFILE_ID
from chronaxis.sources.can_spec import LegacyCANSpec, can_field_from_key


ROOT = Path(__file__).absolute().parents[2]


def can_config():
    """建立带原点号名称、显式通道和有限分析节点的单BLF静态配置。

    参数: 无。返回: 每次独立的原生JSON字典，路径明确指向合成的不存在输入。
    异常: 无；不读取文件、不查DBC、不借用旧测试夹具或真实车型信号。
    """
    # 这个中央夹具服务历史链和B02全调用对照，显式保留all；测试真正默认值时删除此键。
    # 原定位允许点号；简单别名power与原DBC名称保持不同职责。
    field = dict(channel=1,  signal='Power.value', frame_id=256,
                 is_extended=False, is_fd=False)
    return public_configuration(dict(config_version=3,
        dataset=dict(name='can_static', entity='synthetic', session='can_session',
                     domain=dict(start='0s', end='4s')),
        sources=[dict(name='bus', source_type='can_blf', path='work/can-planning-missing.BLF',
                      legacy_profile=PROFILE_ID, decode_scope='all',
                      dbc_by_channel={'1': 'work/can-planning-missing.dbc'},
                      time=dict(time_type='relative', unit='s', origin='can_static_origin'), reader_options={'decode_policy':'legacy'})],
        signals=[dict(name='power', source='bus', field=field, dtype='float64', unit='W',
                      valid_for='2s', same_time_policy='last_by_sequence')],
        derived={'twice': dict(expr='power * 2', unit='W')},
        rules=[dict(name='active', rule_type='condition_duration', condition='power > 1', minimum_duration='0s')],
        windows=[dict(name='context', rule='active', anchor='activity', pre='0s', post='0s', merge='none')],
        calculations=[dict(name='area', scope='session', operation='integral', expr='power', unit='J')],
        execution=dict(backend='numpy', memory_budget_bytes=256*1024**2, batch_rows=2),
        metadata=dict(device_label='home', data_kind='synthetic')))


def with_value(config, keys, value):
    """复制一份配置并替换指定叶值，防止负例污染后续原配置。

    参数: config为纯JSON；keys为已有容器路径；value为本例替换值。
    返回: 独立dict。异常: 路径错误会直接抛KeyError/IndexError，暴露夹具错误。
    """
    result = deepcopy(config)
    current = result
    for key in keys[:-1]:
        current = current[key]
    current[keys[-1]] = value
    return result


class CANPlanningTests(unittest.TestCase):
    """用独立schema和公共计划入口验证声明边界，静态查询始终不拥有外部资源。

    schema在类初始化读取一次；每个静态操作单独借用探针，退出即恢复。非法typed
    替换只检验报告是否诚实，不把手造声明当作已读CAN或实际绑定证明。
    """

    @classmethod
    def setUpClass(cls):
        """读取公开schema并验证标准结构，供后续纯内存配置检查。

        参数: 无。返回: None，保存独立Draft202012Validator。
        异常: OSError/JSONDecodeError/SchemaError均是真实专项失败，不自动skip。
        """
        schema = json.loads((ROOT / 'Docs' / 'Schema' / 'analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def guard_static(self):
        """阻断输入文件、旧依赖和子进程动作，返回可恢复的上下文栈。

        参数: 无。返回: ExitStack，在调用者with结束或安装失败时恢复所有探针。
        异常: 任一被禁止动作实际发生时AssertionError，不用伪造读取结果继续。
        """
        stack = ExitStack()
        original_import = __import__

        def deny_runtime_import(name, globals=None, locals=None, fromlist=(), level=0):
            """阻断CAN依赖及真实执行组件。参数: 原import参数。返回: 原模块。异常: 禁止目标AssertionError。"""
            # 同时覆盖绝对名称与相对导入的fromlist，避免只改import写法就绕过边界。
            forbidden = ('can', 'cantools', 'natsort', 'worker', 'process_read', 'can_reader', 'run_session')
            if name.split('.')[0] in ('can', 'cantools', 'natsort', 'RefProjects') or \
                    name.rsplit('.', 1)[-1] in forbidden or any(item in forbidden for item in (fromlist or ())):
                raise AssertionError('静态CAN规划尝试导入运行依赖：' + name)
            return original_import(name, globals, locals, fromlist, level)

        try:
            # stat/resolve也禁用，保证不存在的相对路径只做词法绝对化。
            for name in ('open', 'read_text', 'read_bytes', 'stat', 'resolve', 'mkdir'):
                stack.enter_context(patch.object(Path, name, side_effect=AssertionError('静态CAN规划触发Path.'+name)))
            stack.enter_context(patch('builtins.open', side_effect=AssertionError('静态CAN规划触发open')))
            stack.enter_context(patch.object(multiprocessing, 'get_context', side_effect=AssertionError('静态CAN规划创建spawn上下文')))
            stack.enter_context(patch.object(multiprocessing, 'Process', side_effect=AssertionError('静态CAN规划创建进程')))
            stack.enter_context(patch('builtins.__import__', deny_runtime_import))
            return stack
        except BaseException:
            # 探针安装中断也不能污染其他测试或掩盖原错误。
            stack.close()
            raise

    def assert_invalid(self, config, *, schema_reject=True, path_prefix='$', code='invalid_config'):
        """核非法配置按指定层拒绝，保留独立schema与Python跨引用的职责区别。

        参数: config为单一变体；schema_reject说明标准schema是否能表达此拒绝；
            path_prefix为公共错误应指向的位置。返回: 捕获的PlanValidationError。
        异常: 任何误接收、错误机器码、路径丢失或静态副作用都会使断言失败。
        """
        if schema_reject:
            self.assertFalse(self.validator.is_valid(current_fixture(config)))
        with self.guard_static(), self.assertRaises(PlanValidationError) as caught:
            AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
        self.assertEqual(caught.exception.code, code)
        self.assertTrue(caught.exception.path.startswith(path_prefix), caught.exception.path)
        return caught.exception

    def test_public_static_can_plan_keeps_original_locator_and_reports_limited_profile(self):
        """纯静态构建和共享报告可用，原定位、语义缺省与未验限制不变。

        参数: 无。返回: None。异常: I/O、旧依赖、身份或能力说明不符合合同则失败。
        """
        config = can_config()
        self.assertEqual(list(self.validator.iter_errors(config)), [])
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            report = AnalysisRunner().validate(plan)
            explanation = AnalysisRunner().explain(plan)
            self.assertEqual(report, validate_analysis_plan(plan))
            self.assertEqual(explanation, explain_analysis_plan(plan))
        spec, definition = plan.sources[0].config, plan.signals[0].definition
        locator = LegacyCANField(**dict(config['signals'][0]['field'], channel=0))
        self.assertIsInstance(spec, LegacyCANSpec)
        self.assertEqual(spec.path, ROOT / config['sources'][0]['path'])
        self.assertEqual(spec.dbc_path, ROOT / config['sources'][0]['dbc_by_channel']['1'])
        self.assertEqual((spec.channel, spec.unit, spec.offset_ns, spec.legacy_profile), (0, 's', 0, PROFILE_ID))
        self.assertEqual(definition.field, locator.key)
        self.assertEqual(can_field_from_key(definition.field), locator)
        self.assertEqual(locator.signal, 'Power.value')
        self.assertEqual(definition.name, 'power')
        self.assertIsNone(definition.semantic_id)
        self.assertIsNone(definition.semantic_contract_version)
        self.assertTrue(report.valid and report.execution_ready)
        self.assertEqual(report.errors, ())
        for key in ('can_blf', 'can_asc', 'raw_can_csv', PROFILE_ID, 'runner', 'memory', 'signal_csv', 'window_segments'):
            self.assertEqual(report.capability_status[key], 'implemented')
        self.assertEqual(report.capability_status['legacy_profiles'], 'partial')
        self.assertEqual(report.capability_status['interval_execution'], 'implemented')
        for key in ('legacy_sum',):
            self.assertEqual(report.capability_status[key], 'unavailable')
        for text in ('metadata_status=declared', '运行单位核对deferred', '空字典无法区分',
                     'None/MISSING', '不猜DECODE_ERROR', '不保证关闭所有内部文件句柄', '进程RSS', '实际RAM峰值'):
            self.assertTrue(any(text in warning for warning in report.warnings), text)
        self.assertEqual(explanation.plan_identity, plan.identity)
        self.assertEqual(explanation.source_names, ('bus',))
        self.assertEqual(tuple(node.dependencies for node in explanation.nodes),
                         (('power',), ('power',), ('power',), ('power',)))
        with self.assertRaises(TypeError):
            report.capability_status['legacy_profiles'] = 'implemented'
        with self.assertRaises(FrozenInstanceError):
            spec.channel = 1

    def test_path_normalization_binding_identity_and_explicit_declarations(self):
        """单路径等价形式共享来源身份，定位/DBC/转换变更使声明绑定身份改变。

        参数: 无。返回: None。异常: 隐式semantic、名称改写、路径探测或身份未更新则失败。
        """
        original = can_config()
        singleton = deepcopy(original)
        singleton['sources'][0]['paths'] = [singleton['sources'][0].pop('path')]
        explicit = deepcopy(original)
        explicit['sources'][0]['path'] = str(ROOT / original['sources'][0]['path'])
        explicit['sources'][0]['dbc_by_channel']['1'] = str(ROOT / original['sources'][0]['dbc_by_channel']['1'])
        self.assertTrue(self.validator.is_valid(current_fixture(singleton)))
        with self.guard_static():
            base, array, absolute = (AnalysisPlan.from_dict(current_fixture(item), base_dir=ROOT) for item in (original, singleton, explicit))
        self.assertEqual(base.sources[0].input_identity, array.sources[0].input_identity)
        self.assertEqual(base.sources[0].input_identity, absolute.sources[0].input_identity)
        self.assertEqual(base.bindings.identity, array.bindings.identity)
        self.assertEqual(base.bindings.identity, absolute.bindings.identity)
        # 绝对CAN仍用原秒时间；domain提供显式UTC，不借timezone或relative origin。
        utc = deepcopy(original)
        utc['sources'][0]['time'] = dict(time_type='absolute', unit='s', offset='-.5s')
        utc['dataset']['domain'] = dict(start='1970-01-01T00:00:00Z', end='1970-01-01T00:00:04Z')
        self.assertTrue(self.validator.is_valid(current_fixture(utc)))
        with self.guard_static():
            utc_plan = AnalysisPlan.from_dict(current_fixture(utc), base_dir=ROOT)
        self.assertEqual(utc_plan.sources[0].config.timebase.time_type.value, 'absolute')
        self.assertIsNone(utc_plan.sources[0].config.timebase.origin)
        self.assertEqual(utc_plan.sources[0].config.offset_ns, -500_000_000)
        # 配置identity仍可区别用户原表示；绑定身份只记录规范来源定位与原信号契约。
        variants = [with_value(original, ('sources', 0, 'dbc_by_channel', '1'), 'work/another.dbc'),
                    with_value(original, ('signals', 0, 'field', 'signal'), 'Power.other'),
                    with_value(original, ('signals', 0, 'valid_for'), '3s'),
                    with_value(original, ('sources', 0, 'time', 'offset'), '-1s')]
        # 使用合法kW→W转换检查绑定身份；W→W倍率2本身不属于有效声明。
        conversion = deepcopy(original)
        conversion['signals'][0].update(input_unit='kW', scale=1000)
        variants.append(conversion)
        channel = deepcopy(original)
        channel['sources'][0]['dbc_by_channel'] = {'2': 'work/can-planning-missing.dbc'}
        channel['signals'][0]['field']['channel'] = 2
        variants.append(channel)
        for index, config in enumerate(variants):
            with self.subTest(index=index), self.guard_static():
                plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
                self.assertNotEqual(plan.bindings.identity, base.bindings.identity)
        # 已声明semantic只是可追溯文本，不把原DBC字段名或点号注册为表达式变量。
        semantic = with_value(original, ('signals', 0, 'semantic_id'), 'physical.pack.power')
        semantic['signals'][0]['semantic_contract_version'] = 'declared-v1'
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(semantic), base_dir=ROOT)
        self.assertEqual(plan.signals[0].definition.semantic_id, 'physical.pack.power')
        self.assertEqual(plan.signals[0].definition.field, base.signals[0].definition.field)
        self.assertIsNone(base.signals[0].definition.semantic_id)

    def test_source_profile_path_channel_time_and_unknown_keys_are_strict(self):
        """公开CAN来源严格拒绝非法路径、别名通道、自由选项、错误时间及未知字段。

        参数: 无。返回: None。异常: 任一非法结构获接受、错误被误报可用性或发生I/O则失败。
        """
        original = can_config()
        cases = [(['legacy_profile'], 'other-profile'), (['dbc_by_channel'], {}),
                 (['dbc_by_channel'], {'1': 'a.dbc', '2': 'b.dbc'}),
                 (['dbc_by_channel'], {'1': 'a.dbc', '00': 'b.dbc'}),
                 (['dbc_by_channel'], {'00': 'a.dbc'}), (['dbc_by_channel'], {'-1': 'a.dbc'}),
                 (['dbc_by_channel'], {' 0': 'a.dbc'}), (['dbc_by_channel'], {'0\n': 'a.dbc'}),
                 (['dbc_by_channel'], {'1': ''}), (['path'], 'input.asc'),
                 (['path'], ''), (['reader_options'], {'filter': True}),
                 (['reader'], []), (['time', 'unit'], 'ms'),
                 (['time', 'unit'], 'ISO8601'), (['time', 'timezone'], 'invalid-zone'),
                 (['unknown_reader_option'], 1)]
        for keys, value in cases:
            with self.subTest(keys=keys, value=value):
                code = ('invalid_choice' if keys in (['legacy_profile'],['time','unit']) else
                        'unknown_field' if keys==['unknown_reader_option'] or keys==['reader_options'] and type(value) is dict else
                        'invalid_type' if keys in (['reader_options'],['reader']) else 'invalid_config')
                # 路径Schema同时允许目录，扩展名与显式来源类型的关系由模型检查。
                self.assert_invalid(with_value(original, ('sources', 0, *keys), value),
                                    schema_reject=keys!=['path'], path_prefix='$.sources[0]', code=code)
        for removed in ('dbc_by_channel', 'path'):
            config = deepcopy(original)
            del config['sources'][0][removed]
            with self.subTest(removed=removed):
                self.assert_invalid(config, path_prefix='$.sources[0]', code='missing_field' if removed!='path' else 'invalid_config')
        relative = deepcopy(original)
        del relative['sources'][0]['time']['clock']
        # 单来源可使用自动时间基准；显式空origin仍不是省略。
        self.validator.validate(current_fixture(relative))
        self.assertEqual(AnalysisPlan.from_dict(current_fixture(relative)).sources[0].config.timebase.origin, '__source_bus')
        self.assert_invalid(with_value(relative, ('sources', 0, 'time', 'clock'), None), path_prefix='$.sources[0].time')
        self.assert_invalid(with_value(original, ('sources', 0, 'time', 'time_type'), 'absolute'),
                            path_prefix='$.sources[0].time.clock')
        utc = deepcopy(original)
        utc['sources'][0]['time'] = dict(time_type='absolute', unit='s', timezone='UTC')
        self.assert_invalid(utc, path_prefix='$.sources[0].time.timezone')
        for paths in ([], ['input.csv']):
            config = deepcopy(original)
            config['sources'][0]['paths'] = paths
            del config['sources'][0]['path']
            with self.subTest(paths=paths):
                self.assert_invalid(config, schema_reject=not paths, path_prefix='$.sources[0]')
        both = with_value(original, ('sources', 0, 'paths'), ['other.blf'])
        self.assert_invalid(both, path_prefix='$.sources[0]')
        # 原生对象键与版本由入口先拒；JSON Schema的integer可接1.0，Python明确不接。
        self.assert_invalid(with_value(original, ('sources', 0, 'dbc_by_channel'), {False: 'a.dbc'}),
                            schema_reject=False, path_prefix='$.sources[0]')
        self.assert_invalid(with_value(original, ('config_version',), True), path_prefix='$.config_version', code='invalid_choice')
        self.assert_invalid(with_value(original, ('config_version',), 1), path_prefix='$.config_version', code='invalid_choice')
        # 旧配置版本均拒绝，不通过语义版本字段补偿。
        self.assert_invalid(with_value(original, ('config_version',), 2), path_prefix='$.config_version', code='invalid_choice')
        self.assert_invalid(with_value(original, ('config_version',), 3.0), schema_reject=False,
                            path_prefix='$.config_version', code='invalid_choice')
        # 原始CSV使用新的raw_can_csv显式布局；旧转换器名称继续拒绝。
        # can_asc已有独立公共入口，不能拿BLF专用profile冒充其配置。
        self.assert_invalid(with_value(original, ('sources', 0, 'source_type'), 'can_asc'),
                            path_prefix='$.sources[0]', code='unknown_field')
        for kind in ('legacy_raw_csv',):
            config = with_value(original, ('sources', 0, 'source_type'), kind)
            self.assertFalse(self.validator.is_valid(current_fixture(config)))
            with self.guard_static(), self.assertRaises(PlanValidationError) as caught:
                AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
            self.assertEqual(caught.exception.code, 'capability_unavailable')

    def test_exact_can_field_native_types_and_source_channel_are_required(self):
        """必填定位及原生开关类型严格，省略类型合法，实际来源通道必须一致。

        参数: 无。返回: None。异常: 定位被猜测、规范化修正或跨来源套用则失败。
        """
        original = can_config()
        cases = [('channel', False), ('channel', -1), ('frame_id', True), ('frame_id', -1),
                 ('frame_id', 0x20000000), ('is_extended', 0), ('is_fd', 1),
                 ('message', ''), ('signal', ''), ('extra', 'ignored')]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.assert_invalid(with_value(original, ('signals', 0, 'field', key), value), path_prefix='$.signals[0].field')
        for field in ('Power.value', {}, {key: value for key, value in original['signals'][0]['field'].items() if key != 'signal'}):
            with self.subTest(field=field):
                self.assert_invalid(with_value(original, ('signals', 0, 'field'), field), path_prefix='$.signals[0].field')
        automatic = deepcopy(original)
        automatic['signals'][0]['field'].pop('is_fd')
        self.validator.validate(current_fixture(automatic))
        self.assertIsNone(can_field_from_key(AnalysisPlan.from_dict(current_fixture(automatic), base_dir=ROOT).signals[0].definition.field).is_fd)
        # Schema只约束native JSON结构；任意source名称到通道值的联合关系由Python再核。
        self.assert_invalid(with_value(original, ('signals', 0, 'field', 'channel'), 2), schema_reject=False,
                            path_prefix='$.signals[0].field.channel')
        self.assert_invalid(with_value(original, ('signals', 0, 'field', 'channel'), 1.0), schema_reject=False,
                            path_prefix='$.signals[0].field')
        # 单字段未超过模型文本上限仍可能使整个规范键超64KiB，错误必须留在配置边界。
        self.assert_invalid(with_value(original, ('signals', 0, 'field', 'message'), 'm'*65536),
                            schema_reject=False, path_prefix='$.signals[0].field')

    def test_memory_csv_field_rules_and_simple_alias_dsl_remain_separate(self):
        """旧来源仍需原字段文本，CAN原名和semantic不能打开点号属性表达式。

        参数: 无。返回: None。异常: 跨来源字段形状或DSL Attribute被接受则失败。
        """
        original = can_config()
        for kind in ('memory', 'signal_csv'):
            config = deepcopy(original)
            source = dict(name='bus', source_type=kind, time=dict(time_type='relative', unit='ns', origin='can_static_origin'))
            if kind == 'memory':
                source['rows'] = [dict(time='0s', values={'Power.value': 2}), dict(time='4s', values={'Power.value': 0})]
            else:
                source.update(path='work/can-planning-missing.csv', time_column='ns')
            config['sources'] = [source]
            # CAN对象不能在单一memory/CSV计划中绕过原字符串字段schema及解析器。
            with self.subTest(kind=kind):
                self.assert_invalid(config, path_prefix='$.signals[0].field')
                config['signals'][0]['field'] = 'Power.value'
                self.assertTrue(self.validator.is_valid(current_fixture(config)))
                with self.guard_static():
                    plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
                    report = AnalysisRunner().validate(plan)
                self.assertTrue(report.execution_ready)
                self.assertEqual(plan.signals[0].definition.field, 'Power.value')
                self.assertEqual(report.capability_status['legacy_profiles'], 'unavailable')
        for expression in ('Power.value * 2', 'physical.pack.power * 2', 'power.real * 2'):
            config = with_value(original, ('derived', 'twice', 'expr'), expression)
            config['signals'][0]['semantic_id'] = 'physical.pack.power'
            config['signals'][0]['semantic_contract_version'] = 'declared-v1'
            with self.subTest(expression=expression):
                self.assert_invalid(config, schema_reject=False, path_prefix='$.derived.twice.expr')
        # 混合来源的动态名称关系超出标准schema表达能力，Python仍拒为CSV配CAN对象。
        mixed = deepcopy(original)
        mixed['sources'].append(dict(name='table', source_type='signal_csv', path='missing.csv', time_column='ns',
                                     time=dict(time_type='relative', unit='ns', origin='can_static_origin')))
        mixed['signals'][0]['source'] = 'table'
        self.assert_invalid(mixed, schema_reject=False, path_prefix='$.signals[0].field')

    def test_typed_report_rejects_unavailable_views_and_backend_override_keeps_plan(self):
        """报告检查typed真实声明，后端覆盖保原对象，raw必须为冻结结构化请求。

        参数: 无。返回: None。异常: 原raw_config掩盖typed错误、报告副作用或覆盖改原计划则失败。
        """
        with self.guard_static():
            plan = AnalysisPlan.from_dict(current_fixture(can_config()), base_dir=ROOT)
        source, signal = plan.sources[0], plan.signals[0]
        bad_field = replace(signal, definition=replace(signal.definition, field='Power.value'))
        wrong_channel = LegacyCANField(1, 'Power.value', 256, False, False).key
        cases = [replace(plan, sources=(replace(source, source_type='can_asc'),)),
                 replace(plan, sources=(replace(source, source_type='memory'),)),
                 replace(plan, sources=(replace(source, time_unit='ms'),)),
                 replace(plan, sources=(replace(source, timezone_text='UTC'),)),
                 replace(plan, sources=(replace(source, name='other'),)),
                 replace(plan, signals=(bad_field,)),
                 replace(plan, signals=(replace(signal, definition=replace(signal.definition, field=wrong_channel)),)),
                 replace(plan, execution=replace(plan.execution, backend='unknown')),
                 replace(plan, calculations=(replace(plan.calculations[0], operation='legacy_sum'),)),
                 replace(plan, outputs=replace(plan.outputs, can_frames='blf'))]
        for index, typed in enumerate(cases):
            with self.subTest(index=index), self.guard_static():
                report = validate_analysis_plan(typed)
                self.assertFalse(report.valid)
                self.assertFalse(report.execution_ready)
                self.assertTrue(report.errors)
                self.assertEqual(explain_analysis_plan(typed).validation, report)
        self.assertTrue(any('can_frames' in error for error in validate_analysis_plan(cases[-1]).errors))
        # 捕获公共AnalysisRunner交给共享报告的有效对象，明确backend变更未重构源/绑定/配置。
        import chronaxis.runner as module
        original_explain, views = module.explain_analysis_plan, []

        def capture(effective):
            """记录真实报告收到的view。参数: effective计划。返回: 真报告。异常: 原报告错误。"""
            views.append(effective)
            return original_explain(effective)

        for declared, selected in (('numpy', 'reference'), ('reference', 'numpy')):
            base = replace(plan, execution=replace(plan.execution, backend=declared))
            with self.guard_static(), patch.object(module, 'explain_analysis_plan', side_effect=capture):
                explanation = AnalysisRunner(backend=selected).explain(base)
            effective = views[-1]
            self.assertEqual(effective.execution.backend, selected)
            self.assertEqual(base.execution.backend, declared)
            self.assertIs(effective.sources, base.sources)
            self.assertIs(effective.bindings, base.bindings)
            self.assertIs(effective.raw_config, base.raw_config)
            self.assertEqual(effective.identity, base.identity)
            self.assertEqual(explanation.plan_identity, base.identity)
            for node in explanation.nodes:
                self.assertEqual(node.backend, 'state_driver' if node.node_type.startswith('rule:') else selected)
        for entry in (validate_analysis_plan, explain_analysis_plan, AnalysisRunner().validate, AnalysisRunner().explain):
            with self.subTest(entry=entry), self.assertRaises(TypeError):
                entry({})
