"""验证当前解码状态的下一时间边界选择和独立结果预算。

输入为少量真实memory或CSV来源，经历史封存、实际运行绑定、完整组状态和
表达式登记后交给BoundaryQueries。时间均为整数纳秒，预期来自显式TTL、
规则截止、更新、来源结束和分析域的手算，不用选择器生成自身预期。
本文件仅写work/m2-run-tests/stream-boundaries唯一目录；设备来源登记在验证记录。
各层分别关闭各自资源，故障只注入新分析层；不改RefProjects，不实现Detector
推进或事件结束分类，也不把原因排序解释为真实同刻状态的消费顺序。
"""

# 使用真实小来源和现有模型；故障替身不替产品执行资源收尾。
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import compile_expression, validate_expression
from chronaxis.core.models import Interval, MemoryRow, SourceSpec, TimebaseSpec
from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.temporal_reference import ReferenceTemporalDetector
from chronaxis.core.temporal_numpy import NumpyTemporalDetector
from chronaxis.core.types import SignalDType as D, TimeType, Truth
from chronaxis.execution.bindings import bind_decoded_history
from chronaxis.execution.boundaries import BoundaryQueries, RuleDeadline
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.expressions import ExpressionQueries
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.hold import HoldContext, HoldQueries
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.state import LatestSignalState
from chronaxis.results import BudgetExceededError, ResultClosedError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest
from chronaxis.sources.csv_spec import SignalCSVSpec


class RejectBoundaryRegistry(set):
    """拒绝已经完成的边界结果登记，保留原集合中的活动结果。"""

    def add(self, result):
        """注入集合分配失败，验证查询负责抵销尚未登记结果的预算。

        参数: result新BoundaryResult。返回: 无正常返回。
        异常: MemoryError为明确注入；不自行关闭result或修改原集合。
        """
        # 被测查询必须处理未登记对象，故障替身不能掩盖它的清理缺口。
        raise MemoryError('boundary-registry-test')


class StreamBoundaryTests(unittest.TestCase):
    """每例独立历史和预算，各owner借用调用方资源而只关闭自有申请。"""

    def setUp(self):
        """建立专用工作目录、共同可核实的相对时钟和3ns有效期声明。

        参数: 无。返回: None。异常: 目录或模型构造错误直接失败。
        """
        # 真实夹具保存在新项目唯一目录，同名来源不能复用另一例的历史证据。
        self.work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/stream-boundaries' / uuid4().hex
        self.work.mkdir(parents=True)
        self.clock = TimebaseSpec('clock', TimeType.RELATIVE, 'boundary-synthetic')
        self.a = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, '1', 3)

    def prepare(self, *, definitions=None, rows_by_source=None, bounds=None, domain=(0, 8),
                texts=('a > 0',), kind='memory', backend='numpy', size=2):
        """从真实读取与EOF证据建立边界owner，保留小组供测试显式提交。

        参数: definitions冻结声明；rows_by_source原始MemoryRow tuple映射；bounds可选
            来源(start,end)纳秒；domain分析范围；texts注册表达式；kind为memory或csv；
            backend归一化后端；size真实读取批次行数。
        返回: SimpleNamespace保存各层、编译对象和有限合成时间组。
        异常: 读取、封存、绑定或编译错误直接传播，创建成功的资源逆序清理。
        """
        # 普通小夹具共享64MiB账本；每层创建后立即登记自己的关闭函数。
        definitions = (self.a,) if definitions is None else definitions
        rows_by_source = {'table': (MemoryRow(0, {'raw.a': 1}, 0),
                                    MemoryRow(5, {'raw.a': 2}, 1))} if rows_by_source is None else rows_by_source
        budget = ResourceBudget(64 * 1024 ** 2)
        interval = Interval(*domain)
        names = tuple(dict.fromkeys(item.source for item in definitions))
        directory = self.work / uuid4().hex
        adapters, requests = [], {}
        for name in names:
            # 每来源只请求其已声明列；全部来源使用同一完整时基，联合表达式没有隐式同步推断。
            selected = tuple(item for item in definitions if item.source == name)
            rows = rows_by_source[name]
            if kind == 'memory':
                # 空来源保留未知观测端点，不能为了排空而制造一个source_eof时间。
                start, end = bounds[name] if bounds is not None else domain if rows else (None, None)
                source = SourceSpec(name, self.clock, rows, observation_start_ns=start, observation_end_ns=end)
                adapter = BudgetedMemorySourceAdapter(budget, source, 'session', selected, backend=backend)
            else:
                # CSV真正写入整数时间和原单元格；实际最后观测点由reader的EOF完成事实提供。
                path = directory / name / 'signals.csv'
                path.parent.mkdir(parents=True)
                fields = tuple(item.field for item in selected)
                lines = ['ns,' + ','.join(fields)]
                for row in rows:
                    values = [str(row.time_ns)] + ['' if row.values.get(field) is None else str(row.values[field])
                                                   for field in fields]
                    lines.append(','.join(values))
                path.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='')
                adapter = BudgetedSignalCSVSourceAdapter(budget, SignalCSVSpec(name, (path,), self.clock, 'ns', 'ns'),
                                                         'session', selected, backend=backend)
            self.addCleanup(adapter.close)
            adapters.append(adapter)
            requests[name] = ReadRequest('session', tuple(item.name for item in selected), *domain, size)
        # 历史先完整消费所有来源至EOF，随后关闭读句柄并封存；静态声明尚不能执行。
        descriptions = tuple(adapter.describe() for adapter in adapters)
        history = DecodedHistoryStore(budget, directory / 'history', descriptions, requests)
        self.addCleanup(history.close)
        for name, adapter in zip(names, adapters):
            for batch in adapter.iter_batches(requests[name]):
                history.append(batch)
            adapter.close()
        history.seal()
        declarations = DeclarationBindings('session', self.clock, interval,
                                            tuple(DeclaredSource(name, self.clock, 'boundary-synthetic') for name in names),
                                            definitions)
        lease = bind_decoded_history(declarations, history)
        self.addCleanup(lease.close)
        # state最初没有样本；测试按完整组提交后，保持查询才有当前TTL证据。
        state = LatestSignalState(budget, definitions, 'session')
        self.addCleanup(state.close)
        holds = HoldQueries(state, HoldContext('session', interval, descriptions,
                                              tuple(history.source_completions.values())))
        self.addCleanup(holds.close)
        compiled = tuple(compile_expression(text, lease.bindings) for text in texts)
        expressions = ExpressionQueries(holds, lease.bindings, compiled)
        self.addCleanup(expressions.close)
        # 边界owner只借用表达式及其上游；完整组仅在有限小测试中物化，不是生产缓冲方案。
        boundaries = BoundaryQueries(expressions)
        self.addCleanup(boundaries.close)
        groups = tuple(history.iter_groups())
        return SimpleNamespace(budget=budget, history=history, lease=lease, state=state, holds=holds,
                               expressions=expressions, boundaries=boundaries, compiled=compiled,
                               groups=groups, declarations=declarations, domain=interval)

    def query(self, fixture, *, index=0, after_ns=0, next_group_ns=None, duration_deadlines=()):
        """调用真实选择器并登记独立结果关闭，不收集生产时间轴。

        参数: fixture各层；index登记编译对象序号；其余与query_next的整数纳秒契约相同。
        返回: BoundaryResult或None。异常: 真实输入、预算或选择错误传播。
        """
        # None没有结果申请；非空结果由测试负责关闭，owner关闭也必须能处理它。
        result = fixture.boundaries.query_next(fixture.compiled[index], after_ns=after_ns,
                                               next_group_ns=next_group_ns, duration_deadlines=duration_deadlines)
        if result is not None:
            self.addCleanup(result.close)
        return result

    def assert_boundary(self, result, fixture, time_ns, reasons, *, index=0):
        """比较独立手算时刻、完整有序原因及已登记运行身份。

        参数: result实际结果；fixture当前链；time_ns手算整数纳秒；reasons(kind,target) tuple。
        返回: None。异常: 时间、顺序、身份或错误关闭断言失败。
        """
        # 原因必须完整冻结；身份直接来自已编译对象，不重复选择器的扫描或哈希计算。
        self.assertIsNotNone(result)
        self.assertIs(type(result.time_ns), int)
        self.assertEqual(result.time_ns, time_ns)
        self.assertIs(type(result.reasons), tuple)
        self.assertEqual(tuple((reason.reason_type, reason.target) for reason in result.reasons), reasons)
        self.assertEqual(result.binding_identity, fixture.lease.bindings.identity)
        self.assertEqual(result.compiled_identity, fixture.compiled[index].identity)
        self.assertFalse(result.closed)

    def close_fixture(self, fixture):
        """按借用关系逆序关闭各层并确认新分析RAM归零。

        参数: fixture本例各资源。返回: None。异常: 关闭或账本残留断言失败。
        """
        # 边界与表达式owner先关闭自有结果；调用方保持、状态、lease、历史分别释放。
        fixture.boundaries.close()
        fixture.expressions.close()
        fixture.holds.close()
        fixture.state.close()
        fixture.lease.close()
        fixture.history.close()
        self.assertEqual(fixture.budget.ram_bytes, 0)

    def test_deadline_three_precedes_update_five_across_real_sources_and_splits(self):
        """真实memory/CSV和两归一化后端不同切批，规则3ns先于下一更新5ns。

        参数: 无。返回: None。异常: 等到下一样本、切批重置或错误原因断言失败。
        """
        # age为10ns，TTL在域外；CSV末点5ns、memory末点8ns均晚于规则截止3ns。
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        fixture = self.prepare(definitions=(replace(self.a, valid_for_ns=10),),
                                               kind=kind, backend=backend, size=size)
                        fixture.state.apply(fixture.groups[0])
                        result = self.query(fixture, next_group_ns=5, duration_deadlines=(RuleDeadline('rule', 3),))
                        self.assert_boundary(result, fixture, 3, (('duration', 'rule'),))
                        self.close_fixture(fixture)

    def test_same_time_causes_merge_and_sort_without_end_classification(self):
        """TTL、规则、真实更新、EOF同3ns只返回一个结果，原因完整且确定排序。

        参数: 无。返回: None。异常: 同刻原因遗漏、重复来源或顺序依赖输入断言失败。
        """
        # 两依赖都在0ns更新且age=3，CSV实际末组在3ns；规则输入故意逆字典序。
        definitions = (self.a, SignalDefinition('b', 'table', 'raw.b', D.FLOAT64, '1', 3))
        rows = {'table': (MemoryRow(0, {'raw.a': 1, 'raw.b': 2}, 0),
                          MemoryRow(3, {'raw.a': 2, 'raw.b': 3}, 1))}
        fixture = self.prepare(definitions=definitions, rows_by_source=rows, texts=('a + b > 0',), kind='csv')
        fixture.state.apply(fixture.groups[0])
        result = self.query(fixture, next_group_ns=3,
                            duration_deadlines=(RuleDeadline('z_rule', 3), RuleDeadline('a_rule', 3)))
        self.assert_boundary(result, fixture, 3, (('ttl', 'a'), ('ttl', 'b'), ('duration', 'a_rule'),
                                                 ('duration', 'z_rule'), ('update', ''), ('source_eof', 'table')))
        # 单有这些原因不决定closed/interrupted/truncated，选择器必须保留原state不推进。
        self.assertEqual(fixture.state.last_time_ns, 0)
        self.close_fixture(fixture)

    def test_domain_end_keeps_equal_ttl_deadline_update_and_eof_reasons(self):
        """域末同3ns的全部候选均保留，已到域末后不再生成边界。

        参数: 无。返回: None。异常: 域末提前丢并列原因或重复定时器断言失败。
        """
        # 当前样本0ns、age3、已核实来源末3ns；caller声明下一完整组也在域末3ns。
        fixture = self.prepare(domain=(0, 3), rows_by_source={'table': (MemoryRow(0, {'raw.a': 1}, 0),)})
        fixture.state.apply(fixture.groups[0])
        result = self.query(fixture, next_group_ns=3, duration_deadlines=(RuleDeadline('rule', 3),))
        self.assert_boundary(result, fixture, 3, (('ttl', 'a'), ('duration', 'rule'), ('update', ''),
                                                 ('source_eof', 'table'), ('domain_end', '')))
        self.assertIsNone(self.query(fixture, after_ns=3))
        self.close_fixture(fixture)

    def test_new_sample_at_two_replaces_old_expiry_three(self):
        """先选2ns真实更新，提交后重新扫描得到TTL5ns，不能复用旧TTL3ns。

        参数: 无。返回: None。异常: 陈旧timer未淘汰、扫描修改状态或回溯断言失败。
        """
        # 初始TTL为0+3=3；下一样本在2，更新后TTL为2+3=5，后续实际组在7。
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(2, {'raw.a': 2}, 1),
                          MemoryRow(7, {'raw.a': 3}, 2))}
        fixture = self.prepare(rows_by_source=rows)
        fixture.state.apply(fixture.groups[0])
        self.assert_boundary(self.query(fixture, next_group_ns=2), fixture, 2, (('update', ''),))
        fixture.state.apply(fixture.groups[1])
        current = fixture.state.get('a')
        self.assert_boundary(self.query(fixture, after_ns=2, next_group_ns=7), fixture, 5, (('ttl', 'a'),))
        # 已处理5ns后TTL不重复；扫描本身不提交、重置或替换当前原样本。
        self.assert_boundary(self.query(fixture, after_ns=5, next_group_ns=7), fixture, 7, (('update', ''),))
        self.assertIs(fixture.state.get('a'), current)
        self.assertEqual(fixture.state.last_time_ns, 2)
        self.close_fixture(fixture)

    def test_dependency_sources_are_deduplicated_and_other_eof_is_ignored(self):
        """同来源两依赖只产生一次EOF，非依赖来源提前结束不影响本表达式。

        参数: 无。返回: None。异常: 全局EOF污染、重复来源或同步身份错误断言失败。
        """
        # zeta上两列共同结束于4，alpha上非依赖列结束于2；age10均超过各来源范围。
        definitions = (SignalDefinition('a', 'zeta', 'raw.a', D.FLOAT64, '1', 10),
                       SignalDefinition('b', 'zeta', 'raw.b', D.FLOAT64, '1', 10),
                       SignalDefinition('c', 'alpha', 'raw.c', D.FLOAT64, '1', 10))
        rows = {'zeta': (MemoryRow(0, {'raw.a': 1, 'raw.b': 2}, 0),),
                'alpha': (MemoryRow(0, {'raw.c': 3}, 0),)}
        fixture = self.prepare(definitions=definitions, rows_by_source=rows,
                               bounds={'zeta': (0, 4), 'alpha': (0, 2)}, texts=('a + b > 0', 'c > 0'))
        fixture.state.apply(fixture.groups[0])
        self.assert_boundary(self.query(fixture), fixture, 4, (('source_eof', 'zeta'),))
        self.assert_boundary(self.query(fixture, index=1), fixture, 2, (('source_eof', 'alpha'),), index=1)
        self.close_fixture(fixture)

    def test_constants_and_empty_source_choose_only_domain_end(self):
        """纯常量及有效分析域内的空来源都到域末，未知端点不造EOF时间。

        参数: 无。返回: None。异常: 空源猜周期、虚构TTL/EOF或常量猜依赖断言失败。
        """
        # 空来源observed_end为None；常量无依赖，a也没有当前样本，两者都只有域末8ns。
        fixture = self.prepare(rows_by_source={'table': ()}, texts=('True', 'a > 0'))
        for index in (0, 1):
            self.assert_boundary(self.query(fixture, index=index), fixture, 8, (('domain_end', ''),), index=index)
            self.assertIsNone(self.query(fixture, index=index, after_ns=8))
        self.close_fixture(fixture)

    def test_native_int64_min_and_large_adjacent_nanoseconds_remain_exact(self):
        """INT64_MIN起点及大于float精度范围的相邻1ns均直接选择整数边界。

        参数: 无。返回: None。异常: 起点减1、float舍入或符号溢出断言失败。
        """
        # 两个起点都用原生整数；当前样本age1，下一TTL严格是start+1，无需start-1哨兵。
        for start in (-(2 ** 63), 2 ** 53 + 1):
            with self.subTest(start=start):
                fixture = self.prepare(domain=(start, start + 6), definitions=(replace(self.a, valid_for_ns=1),),
                                       rows_by_source={'table': (MemoryRow(start, {'raw.a': 1}, 0),)})
                fixture.state.apply(fixture.groups[0])
                self.assert_boundary(self.query(fixture, after_ns=start), fixture, start + 1, (('ttl', 'a'),))
                self.close_fixture(fixture)

    def test_overflow_is_rejected_and_out_of_domain_future_is_ignored(self):
        """越界原生时间明确拒绝，合法但超过域末的未来截止不阻止域末排空。

        参数: 无。返回: None。异常: wrap、钳制或越域timer被错误选中断言失败。
        """
        # 输入端点越过int64必须失败；当前样本+age超MAX由既有保持协议忽略，不能wrap成过去。
        maximum = 2 ** 63 - 1
        for time in (maximum + 1, -(2 ** 63) - 1, True, 3.0, np.int64(3)):
            with self.assertRaises((TypeError, ValueError, OverflowError)):
                RuleDeadline('rule', time)
        fixture = self.prepare(domain=(maximum - 1, maximum),
                               rows_by_source={'table': (MemoryRow(maximum - 1, {'raw.a': 1}, 0),)})
        fixture.state.apply(fixture.groups[0])
        self.assert_boundary(self.query(fixture, after_ns=maximum - 1), fixture, maximum,
                             (('source_eof', 'table'), ('domain_end', '')))
        with self.assertRaises((TypeError, ValueError, OverflowError)):
            self.query(fixture, after_ns=maximum - 1, next_group_ns=maximum + 1)
        self.close_fixture(fixture)
        # 20ns/21ns本身合法，但超过当前域末8ns；它们不替代或延长观测域。
        future = self.prepare(rows_by_source={'table': ()}, texts=('True',))
        self.assert_boundary(self.query(future, next_group_ns=20, duration_deadlines=(RuleDeadline('rule', 21),)),
                             future, 8, (('domain_end', ''),))
        self.close_fixture(future)

    def test_invalid_cursors_deadlines_and_duplicate_rules_leave_state_and_budget(self):
        """错误时间、冻结结构、重复规则和非未来截止被拒绝，不改变原账本及状态。

        参数: 无。返回: None。异常: 隐式转换、重复合并或拒绝失败漏账断言失败。
        """
        # 0ns组已处理；所有next/deadline必须严格晚于after，重复ID不能靠不同时间消歧。
        fixture = self.prepare()
        fixture.state.apply(fixture.groups[0])
        original = fixture.state.get('a')
        before = fixture.budget.ram_bytes
        cases = ({'after_ns': True}, {'after_ns': 0.0}, {'after_ns': np.int64(0)},
                 {'after_ns': -1}, {'after_ns': 9}, {'next_group_ns': 0}, {'next_group_ns': -1},
                 {'next_group_ns': True}, {'next_group_ns': 1.0},
                 {'duration_deadlines': [RuleDeadline('rule', 3)]}, {'duration_deadlines': ('rule',)},
                 {'duration_deadlines': (RuleDeadline('rule', 0),)},
                 {'duration_deadlines': (RuleDeadline('rule', 3), RuleDeadline('rule', 4))},
                 {'after_ns': 8, 'next_group_ns': 8})
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises((TypeError, ValueError, OverflowError)):
                    self.query(fixture, **arguments)
                self.assertEqual(fixture.budget.ram_bytes, before)
                self.assertIs(fixture.state.get('a'), original)
        # after位于域内也不能早于最后提交组；该限制来自最新状态，不能重放过去。
        fixture.state.apply(fixture.groups[1])
        before = fixture.budget.ram_bytes
        with self.assertRaises(ValueError):
            self.query(fixture, after_ns=4)
        self.assertEqual(fixture.budget.ram_bytes, before)
        self.close_fixture(fixture)

    def test_only_current_registered_compiled_object_is_accepted(self):
        """静态、未登记和另一实际绑定的同名表达式都不能进入边界扫描。

        参数: 无。返回: None。异常: 文本或名称绕过登记身份、漏预算断言失败。
        """
        # 另一链把原值由1改为2，改变真实历史绑定；不能凭同一a别名复用原计划。
        fixture = self.prepare()
        fixture.state.apply(fixture.groups[0])
        other = self.prepare(rows_by_source={'table': (MemoryRow(0, {'raw.a': 2}, 0),)})
        invalid = (compile_expression('a >= 0', fixture.lease.bindings),
                   validate_expression('a > 0', fixture.declarations), other.compiled[0], None)
        before = fixture.budget.ram_bytes
        for compiled in invalid:
            with self.assertRaises((TypeError, ValueError)):
                fixture.boundaries.query_next(compiled, after_ns=0)
            self.assertEqual(fixture.budget.ram_bytes, before)
        self.close_fixture(other)
        self.close_fixture(fixture)

    def test_budget_rejection_precedes_ttl_scan_and_result_construction(self):
        """仅余1字节时先拒绝固定构造和新查询，不调用TTL扫描或结果构造。

        参数: 无。返回: None。异常: 申请前扫描/构造或失败漏账断言失败。
        """
        # 固定资源已创建；测试占位仅留1字节，并保存带占位的账本以检查失败抵销。
        fixture = self.prepare()
        fixture.state.apply(fixture.groups[0])
        blocker = fixture.budget.memory_budget_bytes - fixture.budget.ram_bytes - 1
        fixture.budget.reserve_ram(blocker)
        before = fixture.budget.ram_bytes
        try:
            with patch.object(fixture.holds, 'next_expiry') as scan, \
                    patch('chronaxis.execution.boundaries.BoundaryResult') as construct:
                with self.assertRaises(BudgetExceededError):
                    BoundaryQueries(fixture.expressions)
                with self.assertRaises(BudgetExceededError):
                    self.query(fixture)
                scan.assert_not_called()
                construct.assert_not_called()
            self.assertEqual(fixture.budget.ram_bytes, before)
        finally:
            # 占位成本属于测试，无论断言结果如何都要单独释放，不能混作产品申请。
            fixture.budget.release_ram(blocker)
        self.close_fixture(fixture)

    def test_scan_constructor_registration_and_cancellation_release_only_new_cost(self):
        """扫描、结果构造、登记和取消原样传播，释放本次成本且保留旧结果和原state。

        参数: 无。返回: None。异常: 取消被吞、旧结果误关、句柄或账本残留断言失败。
        """
        # 保存一个已完成的TTL3ns结果；后续失败不得撤销它或替换原0ns样本。
        fixture = self.prepare()
        fixture.state.apply(fixture.groups[0])
        original = fixture.state.get('a')
        existing = self.query(fixture)
        before = fixture.budget.ram_bytes
        registry = set(fixture.boundaries._results)
        failures = (('scan', MemoryError('boundary-scan-test')),
                    ('scan', KeyboardInterrupt('boundary-scan-cancel-test')),
                    ('construct', MemoryError('boundary-result-test')),
                    ('construct', KeyboardInterrupt('boundary-result-cancel-test')))
        for stage, error in failures:
            with self.subTest(stage=stage, error=type(error).__name__):
                # 故障分别在已申请查询成本之后的扫描和结果构造处，覆盖BaseException取消。
                injection = patch.object(fixture.holds, 'next_expiry', side_effect=error) if stage == 'scan' else \
                    patch('chronaxis.execution.boundaries.BoundaryResult', side_effect=error)
                with injection:
                    with self.assertRaises(type(error)):
                        self.query(fixture)
                self.assertEqual(fixture.budget.ram_bytes, before)
                self.assertEqual(fixture.boundaries._results, registry)
                self.assertIs(fixture.state.get('a'), original)
                self.assertEqual(fixture.state.last_time_ns, 0)
        # 结果已完整构造后登记集合仍可能失败，本次抵销不能顺手关闭原有活动结果。
        with patch.object(fixture.boundaries, '_results', RejectBoundaryRegistry(registry)):
            with self.assertRaisesRegex(MemoryError, 'boundary-registry-test'):
                self.query(fixture)
        self.assertEqual(fixture.budget.ram_bytes, before)
        self.assertEqual(fixture.boundaries._results, registry)
        self.assertIs(fixture.state.get('a'), original)
        self.assert_boundary(existing, fixture, 3, (('ttl', 'a'),))
        self.close_fixture(fixture)

    def test_upstream_close_preserves_old_result_but_rejects_new_queries(self):
        """调用方任一查询层或state关闭后旧边界快照可读，新边界查询拒绝且不增加账本。

        参数: 无。返回: None。异常: 旧快照依赖已释放上游或新查询漏账断言失败。
        """
        # 结果只持有时刻、原因和身份；表达式、保持、state的关闭都不得让旧结果失效。
        for caller in ('expressions', 'holds', 'state'):
            with self.subTest(caller=caller):
                fixture = self.prepare()
                fixture.state.apply(fixture.groups[0])
                result = self.query(fixture)
                getattr(fixture, caller).close()
                before = fixture.budget.ram_bytes
                self.assert_boundary(result, fixture, 3, (('ttl', 'a'),))
                with self.assertRaises(ResultClosedError):
                    self.query(fixture)
                self.assertEqual(fixture.budget.ram_bytes, before)
                self.close_fixture(fixture)

    def test_owner_close_is_idempotent_and_only_closes_owned_results(self):
        """边界owner幂等关闭自有结果，表达式、保持、state、历史和lease仍属于caller。

        参数: 无。返回: None。异常: 属性越权可读、caller被关闭或最终RAM残留断言失败。
        """
        # 一结果先自行重复关闭，另一结果留给owner重复关闭，覆盖两种合法所有权收尾。
        fixture = self.prepare()
        fixture.state.apply(fixture.groups[0])
        first, second = self.query(fixture), self.query(fixture)
        first.close()
        first.close()
        fixture.boundaries.close()
        fixture.boundaries.close()
        for result in (first, second):
            self.assertTrue(result.closed)
            for attribute in ('time_ns', 'reasons', 'binding_identity', 'compiled_identity'):
                with self.assertRaises(ResultClosedError):
                    getattr(result, attribute)
        with self.assertRaises(ResultClosedError):
            self.query(fixture)
        # 上游保持开放且表达式仍可真实求值；边界owner不能关闭调用方的任何一层。
        for caller in ('expressions', 'holds', 'state', 'history', 'lease'):
            self.assertFalse(getattr(fixture, caller).closed)
        expression = fixture.expressions.query_reference(fixture.compiled[0], (0,))
        self.addCleanup(expression.close)
        self.assertTrue(expression.rows[0].value.valid)
        self.assertTrue(expression.rows[0].value.value)
        expression.close()
        self.close_fixture(fixture)

    def test_existing_detector_zero_and_positive_deadline_protocol(self):
        """真实两Detector的duration0不留同刻timer，正门槛提供严格未来截止。

        参数: 无。返回: None。异常: duration0重复定时器或正门槛误等到更新断言失败。
        """
        # 同一TRUE@0分别交给两现有Detector；本测试只核对公开截止协议，不实现新推进器。
        fixture = self.prepare(definitions=(replace(self.a, valid_for_ns=10),))
        fixture.state.apply(fixture.groups[0])
        for detector_type in (ReferenceTemporalDetector, NumpyTemporalDetector):
            with self.subTest(detector=detector_type.__name__):
                zero = detector_type(TemporalRule('zero', 'dataset', 'session', 'condition_duration', 0), 0, 8)
                zero.push((ConditionTick(0, Truth.TRUE),))
                # 公开确认时刻必须已经是0ns；没有未来timer本身不能替代立即确认的证据。
                self.assertEqual(zero.confirmed, 0)
                self.assertIsNone(zero.next_deadline_ns)
                positive = detector_type(TemporalRule('positive', 'dataset', 'session', 'condition_duration', 3), 0, 8)
                positive.push((ConditionTick(0, Truth.TRUE),))
                self.assertEqual(positive.next_deadline_ns, 3)
                # duration3提供的真实截止在下一组5ns之前，因此边界选择应只返回duration原因。
                result = self.query(fixture, next_group_ns=5,
                                    duration_deadlines=(RuleDeadline('positive', positive.next_deadline_ns),))
                self.assert_boundary(result, fixture, 3, (('duration', 'positive'),))
        self.close_fixture(fixture)
