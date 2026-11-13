"""验证公共计划的配置语义、冻结边界、文件加载和静态报告。

输入使用examples/analysis_plan.json中的合成内存声明及其独立变体，
输出为公共API断言；预期时间由秒到纳秒手算，依赖由显式表达式确定。
每项只验证静态计划，不运行AnalysisRunner或把声明范围当作实际覆盖证明。
文件加载用work专用临时目录；I/O阻断用例证明CSV/DBC不被静态入口打开。
依赖标准库unittest和已实现的chronaxis，不需要schema验证器。
"""

from workspace_fixtures import TemporaryDirectory as workspace_temporary_directory

# 文件加载与错误用例只写项目专用临时目录，保留异常原链。
import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

# 根公共入口与底层不可执行声明类型使用相同验收接口。
from chronaxis import AnalysisPlan, PlanValidationError, explain_analysis_plan, load_analysis_plan, validate_analysis_plan
from chronaxis.core.expression import compile_expression
from chronaxis.core.types import SignalDType

# 仓库定位仅用于已跟踪的合成配置，不扫描历史目录。
ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / 'examples' / 'analysis_plan.json'
WORK = ROOT / 'work' / 'm2-plan-tests'


def config_fixture():
    """读取独立的合成配置副本，不共享上个测试的可变输入。

    参数: 无，使用已跟踪的公开JSON样例。
    返回: dict，包含两种单位、布尔映射、活动/点规则和多种指标。
    异常: OSError或JSONDecodeError表示夹具缺失或损坏，直接失败。
    """
    # 每次重新读取，调用方可修改本测试副本，原样例保持不变。
    return json.loads(EXAMPLE.read_text(encoding='utf-8'))


def changed(config, keys, value):
    """建立仅一个指定字段变化的配置，用于准确定位拒绝条件。

    参数: config为原配置；keys为字段/数组下标tuple；value为新原生值。
    返回: dict，深复制后替换目标字段，原配置不变。
    异常: KeyError或IndexError表示测试路径错误，直接失败。
    """
    # 深复制保证不同变体之间没有字段或列表污染。
    result = deepcopy(config)
    target = result
    # 只沿显式路径导航，不用表达式求值或反射。
    for key in keys[:-1]:
        target = target[key]
    # 最后一级允许替换或新增字段，便于测试未知键拒绝。
    target[keys[-1]] = value
    return result


def csv_fixture():
    """把合成来源换为不存在的CSV声明，保留信号和计算契约。

    参数: 无，来源路径专门不存在，不读取真实日志。
    返回: dict，连续文件顺序为second.csv、first.csv，禁止静态重排。
    异常: 公开样例读取错误传播。
    """
    # 删除内存行后显式声明CSV时间列；路径不能被读取或按名字排序。
    config = config_fixture()
    config['sources'][0] = {
        'name': 'table', 'source_type': 'signal_csv', 'time_column': 'time',
        'time': {'time_type': 'relative', 'unit': 's', 'clock': 'synthetic_common_clock'},
        'paths': ['second.csv', 'first.csv'], 'reader': {},
    }
    from chronaxis.planning.config_groups import public_configuration
    return public_configuration(config)


class AnalysisPlanTests(unittest.TestCase):
    """按T37—T39、T42及T58公共配置范围验证实际入口。

    每个用例持有独立计划；无全局绑定或可执行输入缓存。
    不评价数值、窗口执行、旧调用链或真实日志是否完成。
    """

    def assert_invalid(self, config, path, code='invalid_config'):
        """要求公共解析器返回指定位置和机器错误码。

        参数: config为错误变体；path为JSON路径；code默认配置错误。
        返回: PlanValidationError，供需要原因或异常链的用例继续断言。
        异常: 未拒绝或错误位置/码变化导致AssertionError。
        """
        # 只接受公开异常，不能由任意TypeError掩盖配置诊断缺失。
        with self.assertRaises(PlanValidationError) as caught:
            AnalysisPlan.from_dict(config, base_dir=ROOT)
        # 同一失败原因必须能被API调用者定位，而不是依赖文本猜测。
        self.assertEqual((caught.exception.path, caught.exception.code), (path, code))
        return caught.exception

    def test_defaults_and_typed_nodes(self):
        """完整合成配置解析为确定时间、单位、依赖和默认预算。

        参数: 无，公开样例。
        返回: None，固定契约与手算纳秒一致。
        异常: 任何解析或类型/默认值偏差使测试失败。
        """
        # 4s=4000000000ns，原字段含点号不改变合法current别名。
        plan = AnalysisPlan.from_dict(config_fixture(), base_dir=ROOT)
        self.assertEqual((plan.dataset.domain.start_ns, plan.dataset.domain.end_ns), (0, 4_000_000_000))
        self.assertEqual(plan.signals[0].definition.field, 'raw.current')
        self.assertEqual(plan.signals[0].definition.dtype, SignalDType.FLOAT64)
        # 表达式V*A推导W，积分W*s转换Wh；不预先计算任何数值。
        self.assertEqual(plan.derived_expressions[0].dependencies, ('current', 'voltage'))
        self.assertEqual(plan.calculations[0].unit, 'Wh')
        self.assertEqual(plan.rules[0].minimum_duration_ns, 1_000_000_000)
        # 省略后端由auto按计划选择；其余默认预算保持已发布的数值。
        self.assertEqual((plan.execution.backend, plan.execution.batch_rows, plan.execution.memory_budget_bytes,
                          plan.execution.result_buffer_rows, plan.execution.spool_quota_bytes),
                         ('auto', 65536, 268435456, 4096, None))
        self.assertEqual((plan.outputs.tables, plan.outputs.manifest), ('readable_csv', 'json'))

    def test_deep_freeze_and_input_isolation(self):
        """原字典后续修改不能改变计划，嵌套快照和模型均只读。

        参数: 无，对当前用例独立副本修改。
        返回: None，typed行、配置和元数据保持原身份。
        异常: 对计划写入应抛TypeError/FrozenInstanceError。
        """
        # 构建前保留原值，构建后同时改变样本、策略和嵌套自由元数据。
        config = config_fixture()
        plan = AnalysisPlan.from_dict(config)
        original_identity = plan.identity
        config['sources'][0]['rows'][0]['values']['raw.current'] = 900
        config['signals'][0]['valid_for'] = '9s'
        config['metadata']['notes']['units'].append('changed')
        # 行值和TTL快照独立，不能继承外部修改。
        self.assertEqual(plan.sources[0].config.rows[0].values['raw.current'], 6)
        self.assertEqual(plan.signals[0].definition.valid_for_ns, 2_000_000_000)
        self.assertEqual(plan.metadata['notes']['units'], ('A', 'V'))
        self.assertEqual(plan.identity, original_identity)
        # 嵌套映射和dataclass均明确拒绝原地修改。
        with self.assertRaises(TypeError):
            plan.raw_config['metadata']['notes']['units'][0] = 'x'
        with self.assertRaises(FrozenInstanceError):
            plan.identity = 'changed'

    def test_unknown_keys_at_each_layer(self):
        """拼写错误不能在任何配置层被静默忽略，自由metadata除外。

        参数: 无，各对象新增unknown字段。
        返回: None，错误定位到所属对象。
        异常: 未拒绝未知字段或诊断位置失真使测试失败。
        """
        # 分别覆盖根、来源时钟、行、绑定、派生、节点及预算输出对象。
        cases = [((), '$'), (('dataset',), '$.dataset'), (('dataset', 'domain'), '$.dataset.domain'),
                 (('sources', 0), '$.sources[0]'), (('sources', 0, 'time'), '$.sources[0].time'),
                 (('sources', 0, 'rows', 0), '$.sources[0].rows[0]'), (('signals', 0), '$.signals[0]'),
                 (('derived', 'power'), '$.derived.power'), (('rules', 0), '$.rules[0]'),
                 (('windows', 0), '$.windows[0]'), (('calculations', 0), '$.calculations[0]'),
                 (('execution',), '$.execution'), (('outputs',), '$.outputs')]
        # 为可省略的对象显式建空字典，未知字段仍应拒绝。
        base = config_fixture()
        base.update(execution={}, outputs={})
        for keys, path in cases:
            with self.subTest(path=path):
                self.assert_invalid(changed(base, keys + ('unknown',), 1), path + '.unknown', 'unknown_field')

    def test_versions_and_missing_required_fields(self):
        """版本不隐式转换，缺少必填声明不能通过默认值补造。

        参数: 无，根版本及缺项变体。
        返回: None，所有错误位于版本字段或根对象。
        异常: bool/float版本被当1，或缺项未拒绝使测试失败。
        """
        # 3/4各自保留规则；bool、float、旧结构和尚未支持的5仍明确拒绝。
        for version in (True, 3.0, 1, 2, 5, '3'):
            with self.subTest(version=version):
                self.assert_invalid(changed(config_fixture(), ('config_version',), version), '$.config_version', 'invalid_choice')
        # 不再允许用户额外指定独立语义版本。
        self.assert_invalid(changed(config_fixture(), ('semantic_version',), '0.2'), '$.semantic_version', 'unknown_field')
        # 根必填项逐项删除，以明确证据覆盖入口完整性。
        for key in ('config_version', 'dataset', 'sources', 'signals'):
            config = config_fixture()
            del config[key]
            with self.subTest(missing=key):
                self.assert_invalid(config, '$.' + key, 'missing_field')

    def test_names_fields_units_and_dsl(self):
        """原字段/语义名可含点号，DSL只使用安全别名并检查单位。

        参数: 无，绑定和表达式变体。
        返回: None，合法元数据通过，名称冲突与属性访问拒绝。
        异常: 放宽DSL或混淆原字段与别名使测试失败。
        """
        # 可选点号语义标识只增加声明，不改变直接表达式依赖。
        config = changed(config_fixture(), ('signals', 0, 'semantic_id'), 'battery.current')
        plan = AnalysisPlan.from_dict(config)
        self.assertEqual(plan.rules[0].condition.dependencies, ('current',))
        # 信号源及原字段错误必须在读取执行之前出现。
        self.assert_invalid(changed(config, ('signals', 0, 'source'), 'missing'), '$.signals[0].source', 'invalid_reference')
        self.assert_invalid(changed(config, ('signals', 0, 'field'), 'missing'), '$.signals[0].field')
        for name in ('class', 'abs', 'battery.current', 'voltage'):
            with self.subTest(name=name):
                self.assert_invalid(changed(config, ('signals', 0, 'name'), name),
                                    '$.signals/derived' if name == 'voltage' else '$.signals[0].name')
        # 单位与禁用语法走已有静态编译器，不改测试期望或开放eval。
        for text in ('battery.current > 5', 'signal("battery.current")', 'current[0]', 'current ** 2', 'missing > 5'):
            with self.subTest(text=text):
                error = self.assert_invalid(changed(config, ('rules', 0, 'condition'), text), '$.rules[0].condition')
                self.assertIn('行1列', error.message)
        self.assert_invalid(changed(config, ('derived', 'power', 'unit'), 'A'), '$.derived.power.expr')

    def test_duplicate_ids_and_unused_derived_cycle(self):
        """对象重复和未使用派生环也必须在计划构建时被拒绝。

        参数: 无，明确的重复来源/ID与两节点环。
        返回: None，不自动加后缀或忽略未引用声明。
        异常: 循环或重复ID被接受使测试失败。
        """
        # 来源重复无需读输入即可发现，保留冲突索引。
        config = config_fixture()
        config['sources'].append(deepcopy(config['sources'][0]))
        self.assert_invalid(config, '$.sources[1].name')
        # 规则/窗口/指标使用统一节点ID注册，不能覆盖已有规则。
        self.assert_invalid(changed(config_fixture(), ('windows', 0, 'name'), 'active'), '$.windows[0].name')
        self.assert_invalid(changed(config_fixture(), ('calculations', 0, 'name'), 'active'), '$.calculations[0].name')
        # 两个额外派生未被规则引用，仍不能保留依赖环。
        config = config_fixture()
        config['derived'].update(first={'expr': 'second', 'unit': 'A'}, second={'expr': 'first', 'unit': 'A'})
        self.assert_invalid(config, '$.derived.first.expr')

    def test_time_ranges_ttl_offsets_and_row_order(self):
        """时间单位必须显式，倒序、负时长及越界时间不能静默修正。

        参数: 无，合成坐标和边界变体。
        返回: None，合法负offset保留，错误定位明确。
        异常: 时间截断、重新排序或缺单位通过使测试失败。
        """
        # 同步offset允许负数，不是非负duration；样本本身仍保持原顺序。
        plan = AnalysisPlan.from_dict(changed(config_fixture(), ('sources', 0, 'time', 'offset'), '-500ms'))
        self.assertEqual(plan.sources[0].config.offset_ns, -500_000_000)
        # 错误时间涵盖缺单位、倒置范围和严格大于零的有效期。
        cases = [(('dataset', 'domain', 'start'), '0', '$.dataset.domain.start'),
                 (('dataset', 'domain', 'end'), '-1s', '$.dataset.domain'),
                 (('signals', 0, 'valid_for'), '0ns', '$.signals[0].valid_for'),
                 (('rules', 0, 'minimum_duration'), '-1ns', '$.rules[0].minimum_duration'),
                 (('sources', 0, 'rows', 1, 'time'), '-1s', '$.sources[0]'),
                 (('dataset', 'domain', 'end'), '9223372036854775808ns', '$.dataset.domain.end')]
        for keys, value, path in cases:
            with self.subTest(path=path, value=value):
                self.assert_invalid(changed(config_fixture(), keys, value), path,
                    'invalid_duration' if keys[-1] in ('valid_for','minimum_duration') else 'invalid_config')

    def test_absolute_timezone_and_relative_clock_rules(self):
        """绝对时间需时区，共同相对起点必须声明而非由首点猜测。

        参数: 无，固定+08:00时区及非法相对声明。
        返回: None，绝对时间跨度仍为手算4s。
        异常: 无时区日期应拒绝；relative缺origin采用来源专属基准。
        """
        # 使用固定时区避免依赖本机IANA时区数据库和本地时区猜测。
        config = config_fixture()
        config['sources'][0]['time'] = {'time_type': 'absolute', 'unit': 'ISO8601', 'timezone': '+08:00'}
        config['dataset']['domain'] = {'start': '2026-10-08T20:00:00', 'end': '2026-10-08T20:00:04'}
        for row, seconds in zip(config['sources'][0]['rows'], (0, 1, 4)):
            row['time'] = f'2026-10-08T20:00:0{seconds}'
        plan = AnalysisPlan.from_dict(config)
        self.assertEqual(plan.dataset.domain.end_ns - plan.dataset.domain.start_ns, 4_000_000_000)
        # 来源未声明时区时，无offset的日期不能按系统地区自动解释。
        del config['sources'][0]['time']['timezone']
        self.assert_invalid(config, '$.sources[0].rows[0].time')
        config = config_fixture()
        del config['sources'][0]['time']['clock']
        # 单来源默认基准不根据首点猜测，多来源同步仍需用户声明。
        self.assertTrue(AnalysisPlan.from_dict(config).sources[0].config.timebase.origin.startswith('__source_'))

    def test_rule_window_and_calculation_contracts(self):
        """节点引用、布尔条件、锚点和指标口径使用设计契约校验。

        参数: 无，单字段错误变体。
        返回: None，错误定位且不把声明当实际执行。
        异常: 错误引用或未支持口径被接受使测试失败。
        """
        # 各变体只触发一个明确约束，避免前置错误掩盖目标行为。
        cases = [(('rules', 0, 'condition'), 'current', '$.rules[0].condition'),
                 (('rules', 1, 'rule_type'), 'sequence', '$.rules[1].rule_type'),
                 (('windows', 0, 'rule'), 'missing', '$.windows[0].rule'),
                 (('windows', 0, 'anchor'), 'point', '$.windows[0].anchor'),
                 (('windows', 0, 'post'), '1ns', '$.windows[0].merge'),
                 (('windows', 1, 'post'), '2s', '$.windows[1].post'),
                 (('calculations', 0, 'scope'), {'window': 'missing'}, '$.calculations[0].scope'),
                 (('calculations', 0, 'method'), 'linear', '$.calculations[0].method'),
                 (('calculations', 0, 'operation'), 'mean', '$.calculations[0].operation'),
                 (('calculations', 0, 'minimum_coverage'), True, '$.calculations[0].minimum_coverage'),
                 (('calculations', 0, 'minimum_coverage'), 1.01, '$.calculations[0].minimum_coverage'),
                 (('calculations', 3, 'condition'), 'current', '$.calculations[3].condition')]
        for keys, value, path in cases:
            with self.subTest(path=path):
                code = ('invalid_choice' if keys[-1] in ('rule_type','method','operation') else
                        'invalid_reference' if keys[-1] in ('rule','scope') else
                        ('invalid_type' if value is True else 'out_of_range') if keys[-1]=='minimum_coverage' else 'invalid_config')
                self.assert_invalid(changed(config_fixture(), keys, value), path, code)

    def test_execution_limits_and_unavailable_capabilities(self):
        """预算类型严格检查，尚未接线能力返回明确unavailable错误。

        参数: 无，预算与未来能力声明。
        返回: None，所有拒绝具有机器码和位置。
        异常: bool预算、未知后端或未接线旧能力被接受使测试失败。
        """
        # 资源限额必须正原生整数，声明本身不能证明实际内存受限。
        for key in ('batch_rows', 'memory_budget_bytes', 'result_buffer_rows', 'spool_quota_bytes'):
            for value in (True, 0, -1, 1.5):
                config = changed(config_fixture(), ('execution',), {key: value})
                with self.subTest(key=key, value=value):
                    self.assert_invalid(config, '$.execution.' + key, 'invalid_type' if type(value) is not int else 'out_of_range')
        self.assert_invalid(changed(config_fixture(), ('execution',), {'backend': 'unknown'}), '$.execution.backend', 'invalid_choice')
        # 预设、单BLF和显式逐消息计算已接线；缺必填字段仍是结构错误。
        self.assert_invalid(changed(config_fixture(), ('presets',), [{'name': 'future'}]), '$.presets[0].parameters', 'missing_field')
        self.assert_invalid(changed(config_fixture(), ('message_calculations',), [{'name': 'future'}]), '$.message_calculations[0].expr', 'missing_field')
        for kind in ('legacy_raw_csv',):
            self.assert_invalid(changed(config_fixture(), ('sources', 0, 'source_type'), kind), '$.sources[0].source_type', 'capability_unavailable')
        # 原始BLF导出已接线；列表仍是结构错误，不能再把它写成能力未实现。
        self.assert_invalid(changed(config_fixture(), ('outputs',), {'raw_segments': []}), '$.outputs.raw_segments', 'unknown_field')

    def test_csv_paths_no_io_and_reports(self):
        """静态解析/报告只保存路径和声明，公共AnalysisRunner已接线仍不读取来源。

        参数: 无，不存在的连续CSV声明。
        返回: None，预算/依赖/历史范围手算一致，无输入打开。
        异常: 静态入口打开输入文件、遗漏实际能力或把声明当实测使测试失败。
        """
        # 夹具读取放在阻断之前；API、报告禁止打开输入CSV或DBC。
        config = csv_fixture()
        with patch('builtins.open', side_effect=AssertionError('不允许输入I/O')), \
             patch.object(Path, 'open', side_effect=AssertionError('不允许Path输入I/O')):
            plan = AnalysisPlan.from_dict(config, base_dir=ROOT)
            validation = validate_analysis_plan(plan)
            explanation = explain_analysis_plan(plan)
        # 路径按原顺序相对于显式base解释，不能排序或默认读取。
        self.assertEqual(plan.sources[0].config.paths, (ROOT / 'second.csv', ROOT / 'first.csv'))
        self.assertTrue(validation.valid)
        self.assertTrue(validation.execution_ready)
        self.assertEqual(validation.capability_status['runner'], 'implemented')
        # 公共执行和结果发布均已有路径；静态ready不代表输入已读或实际RAM测量通过。
        self.assertEqual(validation.capability_status['bounded_result_publish'], 'implemented')
        # 已接线的时间算法和选择行流沿当前公共执行路径使用。
        self.assertEqual(validation.capability_status['time_calculations'], 'implemented')
        self.assertEqual(validation.capability_status['selection_rows'], 'implemented')
        # 窗口和固定抑制规则已由公共AnalysisRunner调用，不借静态报告执行数值运算。
        self.assertEqual(validation.capability_status['window_segments'], 'implemented')
        self.assertEqual(validation.capability_status['start_only'], 'implemented')
        self.assertTrue(any('metadata_status=declared' in item for item in validation.warnings))
        # 3s的pre超过2s TTL，规则和片段指标全部原依赖保留3s历史声明。
        self.assertEqual(dict(explanation.history_ns), {'current': 3_000_000_000, 'voltage': 3_000_000_000, 'alarm': 2_000_000_000})
        self.assertEqual(explanation.budget['memory_budget_bytes'], 268435456)
        self.assertEqual(next(node for node in explanation.nodes if node.node_id == 'context_mean').dependencies, ('current', 'voltage'))
        # 静态表达式仍不能通过真正执行编译门槛。
        with self.assertRaises(TypeError):
            compile_expression('current', plan.bindings)

    def test_csv_path_shape_and_format(self):
        """文件路径必须二选一，CSV格式错误静态拒绝而不猜测。

        参数: 无，不存在路径和错误格式参数。
        返回: None，拒绝位置明确；路径顺序由上一用例验证。
        异常: 文件格式或路径结构被静默修复使测试失败。
        """
        # 同时path/paths及空paths都不能形成可读取的声明。
        error = self.assert_invalid(changed(csv_fixture(), ('sources', 0, 'path'), 'third.csv'), '$.sources[0].path')
        self.assertEqual(error.message, '当前操作或配置下不能填写字段：path')
        self.assert_invalid(changed(csv_fixture(), ('sources', 0, 'paths'), []), '$.sources[0].paths')
        for key, value in (('delimiter', '\n'), ('encoding', 'nonexistent-codec'), ('missing_values', ['', ''])):
            with self.subTest(key=key):
                self.assert_invalid(changed(csv_fixture(), ('sources', 0, 'reader', key), value),
                                    '$.sources[0]' if key == 'encoding' else '$.sources[0].reader.' + key)

    def test_identity_changes_without_binding_leaks(self):
        """同表达式的路径、字段、TTL、转换和策略变化区分计划身份。

        参数: 无，CSV声明的合法单字段变体。
        返回: None，所有新身份与基线不同，重复配置身份稳定。
        异常: 跨任务绑定复用或身份忽略策略使测试失败。
        """
        # 原样重建稳定；只读计划不使用上次调用的绑定对象。
        config = csv_fixture()
        baseline = AnalysisPlan.from_dict(config, base_dir=ROOT)
        repeated = AnalysisPlan.from_dict(config, base_dir=ROOT)
        self.assertEqual(baseline.identity, repeated.identity)
        self.assertIsNot(baseline.bindings, repeated.bindings)
        # mA到A的转换必须显式正确，不用非法A到A系数伪造变化。
        variants = [changed(config, ('sources', 0, 'paths'), ['other.csv', 'first.csv']),
                    changed(config, ('signals', 0, 'field'), 'other_current'),
                    changed(config, ('signals', 0, 'valid_for'), '3s'),
                    changed(config, ('signals', 0, 'same_time_policy'), 'last_by_sequence')]
        converted = deepcopy(config)
        converted['signals'][0].setdefault('conversion', {})['input_unit'] = 'mA'
        converted['signals'][0].setdefault('conversion',{})['scale'] = 0.001
        variants.append(converted)
        for variant in variants:
            plan = AnalysisPlan.from_dict(variant, base_dir=ROOT)
            self.assertNotEqual(plan.identity, baseline.identity)
            self.assertNotEqual(plan.bindings.identity, baseline.bindings.identity)
        # 新计划解析不改变基线的原字段与来源路径。
        self.assertEqual(baseline.bindings.resolve('current').field, 'raw.current')

    def test_load_plan_bom_relative_paths_and_read_only_config(self):
        """加载只打开指定JSON，BOM合法且来源路径按配置目录解释。

        参数: 无，work内临时配置，不存在CSV文件。
        返回: None，文件句柄关闭且原配置字节不改写。
        异常: 打开输入、目录基准错误或句柄未关闭使测试失败。
        """
        # 所有临时输出限制在新项目work目录，退出自动清理本用例目录。
        WORK.mkdir(parents=True, exist_ok=True)
        with workspace_temporary_directory(dir=WORK) as directory:
            target = Path(directory) / 'analysis.json'
            target.write_text(json.dumps(csv_fixture()), encoding='utf-8-sig')
            original = target.read_bytes()
            opened = []
            original_open = Path.open

            def config_only(path, *args, **kwargs):
                """只允许指定配置文件打开并记录真实句柄。

                参数: path为待打开Path；args/kwargs为原open选项。
                返回: 真实文本句柄，由load_analysis_plan的with关闭。
                异常: AssertionError表示企图读取声明的输入；I/O错误传播。
                """
                # 目标CSV不存在，仍显式阻断，防止读取被吞异常掩盖。
                self.assertEqual(path, target)
                handle = original_open(path, *args, **kwargs)
                opened.append(handle)
                return handle

            # 只包装Path.open；配置解析完后输入读取次数必须仍为零。
            with patch.object(Path, 'open', config_only):
                plan = load_analysis_plan(target)
            self.assertEqual(plan.sources[0].config.paths[0], target.parent / 'second.csv')
            self.assertEqual(len(opened), 1)
            self.assertTrue(opened[0].closed)
            self.assertEqual(target.read_bytes(), original)

    def test_load_plan_errors_and_original_exception(self):
        """重复键、坏编码、坏JSON和非有限常量不能成为成功计划。

        参数: 无，work中各最小损坏配置字节。
        返回: None，文件定位、错误码与原异常链保留。
        异常: 解析器吞错误或覆盖重复键使测试失败。
        """
        # 重复根键/嵌套键及JSON扩展常量在模型构建前即拒绝。
        cases = [(b'{"x":1,"x":2}', 'duplicate_key'),
                 (b'{"metadata":{"x":1,"x":2}}', 'duplicate_key'),
                 (b'{"x":NaN}', 'nonfinite_number'), (b'{"x":Infinity}', 'nonfinite_number'),
                 (b'{', 'invalid_json'), (b'\xff', 'load_error')]
        WORK.mkdir(parents=True, exist_ok=True)
        with workspace_temporary_directory(dir=WORK) as directory:
            target = Path(directory) / 'bad.json'
            for content, code in cases:
                target.write_bytes(content)
                with self.subTest(content=content), self.assertRaises(PlanValidationError) as caught:
                    load_analysis_plan(target)
                self.assertEqual((caught.exception.source, caught.exception.code), (str(target), code))
                self.assertTrue(caught.exception.path.startswith('$'))
                self.assertIsNotNone(caught.exception.__cause__)
            # 文件不存在与参数类型错误也通过公开异常返回。
            with self.assertRaises(PlanValidationError) as caught:
                load_analysis_plan(Path(directory) / 'absent.json')
            self.assertEqual(caught.exception.code, 'load_error')
        with self.assertRaises(PlanValidationError):
            load_analysis_plan(123)

    def test_json_containers_checked_before_freezing(self):
        """非JSON容器不能在冻结阶段被偷偷转换成合法配置数组。

        参数: 无，tuple信号列表及循环字典，均无法来自合法JSON。
        返回: None，原生容器错误定位明确，不产生RecursionError泄漏。
        异常: 接受非JSON容器或无限递归使测试失败。
        """
        # 公共from_dict声明与load_analysis_plan遵循同一JSON结构，不容许冻结改变类型。
        config = config_fixture()
        self.assert_invalid(changed(config, ('signals',), tuple(config['signals'])), '$.signals')
        # 循环对象不是合法JSON，自引用位置需转换为公开配置诊断。
        config = config_fixture()
        config['metadata']['cycle'] = config['metadata']
        self.assert_invalid(config, '$.metadata.cycle')
        # 两个字段共享同一列表但没有自引用，属于合法JSON树的可复制输入。
        config = config_fixture()
        shared = ['A']
        config['metadata'].update(first=shared, second=shared)
        plan = AnalysisPlan.from_dict(config)
        self.assertEqual((plan.metadata['first'], plan.metadata['second']), (('A',), ('A',)))
        # 自由元数据字段不限制名称，仍须拒绝JSON无法表示的非有限值。
        for value in (float('nan'), float('inf')):
            self.assert_invalid(changed(config_fixture(), ('metadata', 'bad_float'), value), '$.metadata.bad_float')

    def test_multisource_synchronization_uses_actual_dependencies(self):
        """不同起点的独立规则可静态存在，联合指标必须有公共同步依据。

        参数: 无，两个相对时钟的来源及segment联合依赖。
        返回: None，不从首样本相同猜测同步，不越过指标事件依赖。
        异常: 误接受联合分析或误拒绝独立来源使测试失败。
        """
        # 电压单独来源与电流有不同起点，移除联合power后独立指标可检查。
        config = config_fixture()
        second = deepcopy(config['sources'][0])
        second['name'] = 'other'
        second['time']['clock'] = 'other_clock'
        config['sources'].append(second)
        config['signals'][1]['source'] = 'other'
        config['derived'] = {}
        config['calculations'] = [{'name': 'voltage_peak', 'scope': 'session', 'operation': 'sample_maximum', 'expr': 'voltage'}]
        AnalysisPlan.from_dict(config)
        # 一旦指标范围来自电流活动，就成为跨来源依赖，执行前拒绝。
        config['calculations'][0]['scope'] = {'window':'activity_context'}
        self.assert_invalid(config, '$.calculations[0]')
        # 用户明确提供同一公共起点才可通过，不自动制造SynchronizationEvidence。
        config['sources'][1]['time']['clock'] = config['sources'][0]['time']['clock']
        AnalysisPlan.from_dict(config)
