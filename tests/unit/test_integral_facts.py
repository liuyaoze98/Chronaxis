"""用手算覆盖与真实历史验证整窗积分事实累计及资源清理。

输入为明确声明的块事实或真实 memory/CSV 历史，两面积核分别生成事实。
不把另一个后端当真值：覆盖、样本和未知范围用纳秒手算验证。
长流逐块消费，检查相邻诊断合并及彼此分开的未知范围超限，不保留面积或全时间轴。
故障在申请、候选构造和释放前后注入；共享账本已有金额必须原样保留。
文件副作用只来自现有真实夹具的 work 目录，夹具最终核对 RAM 为零。
"""

# 原测试模块仅作为真实夹具工厂使用，避免重复收集其测试类。
from dataclasses import replace
import unittest
from unittest.mock import patch
import test_calculation_blocks as real_history
from chronaxis.core.integral_terms import IntegralFacts
from chronaxis.core.integral_terms_reference import compute_integral_terms_reference
from chronaxis.core.integral_terms_numpy import compute_integral_terms_numpy
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, MemoryRow, SourceRef
from chronaxis.core.types import QualityFlag as Q
from chronaxis.execution import integral_facts as module
from chronaxis.execution.integral_facts import IntegralFactsAccumulator
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


class IntegralFactsTests(unittest.TestCase):
    """每个 owner 独立关闭；手算、实际历史和故障场景各自提供证据。"""

    def owner(self, spec=None, observation=None, budget=None, refs=()):
        """创建累计者并登记最终关闭。

        参数: spec/observation 默认 0—9ns；budget 可含调用方已有申请；refs 保留完整类型。
        返回: IntegralFactsAccumulator。异常: 真实构造错误传播。
        """
        # 默认只描述明确的小型观测；借用账本不会在夹具关闭时整体清空。
        spec = CalculationDefinition('area', 'integral', Interval(0, 9)) if spec is None else spec
        observation = spec.window if observation is None else observation
        budget = ResourceBudget() if budget is None else budget
        owner = IntegralFactsAccumulator(budget, spec, observation, 'W', 'explicit-facts', refs)
        self.addCleanup(owner.close)
        return owner

    def block(self, spec, start, end, valid=None, count=0, unknown=(), quality=Q.NONE, refs=()):
        """建立可单独核实的事实，不创建面积或伪造 CalculationSeries。

        参数: spec 原请求；start/end/valid 为整数 ns；其余为明确计数/诊断/来源。
        返回: IntegralFacts。异常: 原冻结模型校验错误。
        """
        # 默认全块有效；未知情况必须由测试显式给出时长及区间。
        valid = end - start if valid is None else valid
        return IntegralFacts(spec, Interval(start, end), valid, count, unknown, quality,
                             'W', 'explicit-facts', refs)

    def cancel_once(self, original, after):
        """在首次预算动作之前或成功之后取消，后续执行真实清理。

        参数: original 为账本原方法；after 为取消时机。返回: 故障函数。
        异常: 返回函数首次调用抛 KeyboardInterrupt。
        """
        # 故障仅发生一次，后续真实清理才能检验是否重试或重复扣账。
        used = False

        def invoke(amount):
            """注入一次取消。参数: amount 为 bytes。返回: 原结果。异常: 首次取消。"""
            # 标志先置位，再按时机执行真实动作，保证异常后重试不会再被本故障拦住。
            nonlocal used
            if not used:
                used = True
                if after:
                    original(amount)
                raise KeyboardInterrupt('integral-facts-test')
            return original(amount)

        return invoke

    def test_hand_coverage_merges_adjacent_unknown_and_preserves_full_source_refs(self):
        """三个块覆盖 9ns，有效 4ns/样本3，未知 1—6ns，CSV细节不丢失。

        参数: 无。返回: None。异常: 覆盖、质量或完整来源不符断言失败。
        """
        # 明确同一基础来源的两个 CSV 行；完整子类字段决定是否可以去重。
        spec = CalculationDefinition('area', 'integral', Interval(0, 9), output_unit='J')
        base = SourceRef('session', 'table', 'raw.a')
        first = CSVSourceRef('session', 'table', 'raw.a', 'input.csv', 2, '0', '1.0', False)
        second = replace(first, line_number=3, time_text='3', value_text='bad')
        owner = self.owner(spec, refs=(base, base))
        # 未知1—3ns与后块3—6ns相邻；其余共4ns有效且真实样本计3次。
        owner.push(self.block(spec, 0, 3, 1, 1, (Interval(1, 3),), Q.STALE, (first, first)))
        owner.push(self.block(spec, 3, 6, 0, 0, (Interval(3, 4), Interval(4, 6)), Q.MISSING, (first, second)))
        owner.push(self.block(spec, 6, 9, 3, 2, refs=(second, base)))
        # 完整性门槛必须显式 finish；读取后按手算核对来源、质量和原请求。
        with self.assertRaises(RuntimeError):
            _ = owner.facts
        owner.finish()
        facts = owner.facts
        self.assertEqual((facts.actual_window, facts.value_valid_duration_ns, facts.valid_sample_count),
                         (Interval(0, 9), 4, 3))
        self.assertEqual(facts.value_unknown_ranges, (Interval(1, 6),))
        self.assertEqual(facts.quality, Q.STALE | Q.MISSING)
        self.assertEqual(facts.source_refs, (base, first, second))
        self.assertIs(facts.source_refs[1], first)
        self.assertIs(facts.spec, spec)
        self.assertEqual(facts.input_unit, 'W')  # 尚无面积或输出单位数值转换。
        # 重复完成无副作用，完成后追加和关闭后读取必须拒绝。
        owner.finish()
        with self.assertRaises(RuntimeError):
            owner.push(self.block(spec, 9, 9))
        owner.close()
        with self.assertRaises(ResultClosedError):
            _ = owner.facts
        self.assertEqual(owner._budget.ram_bytes, 0)

    def test_real_memory_csv_history_two_backends_all_splits_match_hand_truth(self):
        """真实 0/5/8ns 更新在 2—7ns 得有效3ns、样本1、未知3—5ns。

        参数: 无。返回: None。异常: 分块/后端改变事实或借用状态断言失败。
        """
        # 同一真实更新序列跨来源/后端/切分复用，预期始终来自独立手算。
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1), MemoryRow(8, {'raw.a': 2}, 2))}
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for count in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, intervals=count):
                        helper = real_history.CalculationBlocksTests('runTest')
                        try:
                            # 在创建新 owner 前记录借用基线，结束时逐一关闭自有资源。
                            fixture = helper.fixture(kind=kind, backend=backend, rows_by_source=rows, size=count)
                            spec = CalculationDefinition('area', 'integral', Interval(2, 7))
                            before = fixture.budget.ram_bytes
                            blocks = helper.owner(fixture, spec, backend=backend, batch_intervals=count)
                            owner = IntegralFactsAccumulator(fixture.budget, spec, fixture.holds._context.domain,
                                                             '1', fixture.compiled[0].identity)
                            try:
                                # 即时消费原块事实，每次 finally 都关闭该块，不收集全轴/面积。
                                compute = compute_integral_terms_reference if backend == 'reference' else compute_integral_terms_numpy
                                for block in blocks:
                                    try:
                                        owner.push(compute(block.series, spec).facts)
                                    finally:
                                        block.close()
                                # 整窗覆盖与完整 CSV 定位均需核对，原调用方 state 不应提交。
                                owner.finish()
                                facts = owner.facts
                                self.assertEqual((facts.actual_window, facts.value_valid_duration_ns, facts.valid_sample_count),
                                                 (Interval(2, 7), 3, 1))
                                self.assertEqual(facts.value_unknown_ranges, (Interval(3, 5),))
                                self.assertTrue(facts.quality & Q.STALE)
                                self.assertEqual(facts.binding_identity, fixture.compiled[0].identity)
                                self.assertTrue(facts.source_refs)
                                if kind == 'csv':
                                    self.assertTrue(all(isinstance(ref, CSVSourceRef) and ref.path and ref.line_number >= 2
                                                        for ref in facts.source_refs))
                                self.assertEqual(fixture.state.revision, 0)
                            finally:
                                owner.close()
                            # EOF 不等于关闭：回读缓存仍属分块者，显式关闭后才回到借用基线。
                            blocks.close()
                            self.assertEqual(fixture.budget.ram_bytes, before)
                        finally:
                            # 即使断言失败，真实工厂仍须释放全部资源并核对 RAM0。
                            self.assertTrue(helper.doCleanups())

    def test_no_intersection_finishes_without_inventing_observation(self):
        """请求与真实观测分离，空完成保持 actual None 和零覆盖计数。

        参数: 无。返回: None。异常: 捏造观测或面积正常零断言失败。
        """
        # 没有观测交集只保留 None；零覆盖计数不表示数值积分正常为零。
        owner = self.owner(observation=Interval(20, 30))
        owner.finish()
        self.assertIsNone(owner.facts.actual_window)
        self.assertEqual((owner.facts.value_valid_duration_ns, owner.facts.valid_sample_count), (0, 0))

    def test_zero_and_touching_windows_require_one_real_point(self):
        """原请求零长度或观测仅与请求端点相接，都需要一个真实点块。

        参数: 无。返回: None。异常: 点交集混同无交集或重复点被接收断言失败。
        """
        # 同时覆盖原请求为点，以及请求末端与观测起点相接两种情况。
        for window, observation in ((Interval(3, 3), Interval(0, 9)), (Interval(0, 9), Interval(9, 12))):
            spec = CalculationDefinition('area', 'integral', window)
            point = max(window.start_ns, observation.start_ns)
            owner = self.owner(spec, observation)
            owner.push(self.block(spec, point, point))
            owner.finish()
            self.assertEqual(owner.facts.actual_window, Interval(point, point))
            # 另建 owner 注入重复点，不能破坏前一个已完成的点事实。
            duplicate = self.owner(spec, observation)
            duplicate.push(self.block(spec, point, point))
            with self.assertRaises(ValueError):
                duplicate.push(self.block(spec, point, point))
            self.assertTrue(duplicate.failed)

    def test_partial_observation_uses_original_request_without_guessing_eof(self):
        """只观测 2—7ns，完整接收该交集后仍保留原 0—9ns 请求。

        参数: 无。返回: None。异常: 交集或原请求被改写断言失败。
        """
        # 请求与观测不同，finish 只检查真实交集，原 strict 政策留给结果封装。
        spec = CalculationDefinition('area', 'integral', Interval(0, 9), partial_policy='strict')
        owner = self.owner(spec, Interval(2, 7))
        owner.push(self.block(spec, 2, 4))
        owner.push(self.block(spec, 4, 7))
        owner.finish()
        self.assertIs(owner.facts.spec, spec)
        self.assertEqual(owner.facts.actual_window, Interval(2, 7))
        self.assertEqual(owner.facts.value_valid_duration_ns, 5)

    def test_incomplete_finish_and_unobserved_point_are_rejected(self):
        """接收前缀不是 EOF，未收到点事实也不能直接完成点窗口。

        参数: 无。返回: None。异常: 未完整覆盖仍开放 facts 断言失败。
        """
        # 两个不足场景各自验证，读取不能把前缀或未观测点变成最终结果。
        owner = self.owner()
        owner.push(self.block(CalculationDefinition('area', 'integral', Interval(0, 9)), 0, 3))
        point = self.owner(CalculationDefinition('area', 'integral', Interval(3, 3)))
        for item in (owner, point):
            with self.assertRaises(ValueError):
                item.finish()
            with self.assertRaises(RuntimeError):
                _ = item.facts
            self.assertTrue(item.failed)

    def test_gap_overlap_reversed_or_nonadvancing_blocks_fail_closed(self):
        """缺口、重叠、倒序、越界及正域零块出错后只允许关闭。

        参数: 无。返回: None。异常: 错块被接收或失败后继续推进断言失败。
        """
        # 先接收同一合法前缀，再逐个注入不同时间错误；错误后合法块也不再接收。
        spec = CalculationDefinition('area', 'integral', Interval(0, 9))
        for start, end in ((4, 6), (2, 5), (0, 2), (3, 10), (3, 3)):
            with self.subTest(start=start, end=end):
                owner = self.owner(spec)
                owner.push(self.block(spec, 0, 3))
                with self.assertRaises(ValueError):
                    owner.push(self.block(spec, start, end))
                with self.assertRaises(RuntimeError):
                    owner.push(self.block(spec, 3, 9))

    def test_wrong_request_unit_identity_and_missing_actual_are_rejected(self):
        """原请求、输入单位、表达式身份或实际观测不一致不能拼接。

        参数: 无。返回: None。异常: 静默重绑定或改写请求断言失败。
        """
        spec = CalculationDefinition('area', 'integral', Interval(0, 9))
        # 每次只更改一项原事实，以免另一校验先报错遮住待检查字段。
        good = self.block(spec, 0, 9)
        cases = (replace(good, spec=replace(spec, calculation_id='other')),
                 replace(good, input_unit='kW'), replace(good, binding_identity='other'),
                 replace(good, actual_window=None, value_valid_duration_ns=0))
        for facts in cases:
            owner = self.owner(spec)
            with self.assertRaises(ValueError):
                owner.push(facts)

    def test_unknown_overlap_order_incomplete_partition_and_impossible_count_rejected(self):
        """模型允许但消费者协议不允许的重复未知、空缺及过多样本被拒绝。

        参数: 无。返回: None。异常: 仅靠总时长抵消错误范围断言失败。
        """
        spec = CalculationDefinition('area', 'integral', Interval(0, 9))
        # 重叠例的总未知时长看似正确，仍必须按区间顺序检查，而非只比总长。
        cases = (self.block(spec, 0, 9, 4, unknown=(Interval(0, 3), Interval(2, 4))),
                 self.block(spec, 0, 9, 5, unknown=(Interval(6, 8), Interval(0, 2))),
                 self.block(spec, 0, 9, 7, unknown=(Interval(0, 1),)),
                 self.block(spec, 0, 9, count=10))
        for facts in cases:
            owner = self.owner(spec)
            with self.assertRaises(ValueError):
                owner.push(facts)

    def test_long_valid_stream_retains_no_axis_or_area_and_constant_ram(self):
        """1000 个有效块只保留计数，稳定来源去重后 RAM 不随块数增长。

        参数: 无。返回: None。异常: 全轴/面积或重复来源累计增长断言失败。
        """
        # 来源预先加入后不再增长；逐块关闭由纯事实消费代替，无面积数组留存。
        spec = CalculationDefinition('area', 'integral', Interval(0, 1000))
        ref = SourceRef('session', 'table', 'raw.a')
        budget = ResourceBudget(2_000_000)
        owner = self.owner(spec, budget=budget, refs=(ref,))
        retained = budget.ram_bytes
        for time in range(1000):
            owner.push(self.block(spec, time, time + 1, count=1, refs=(ref, ref)))
            self.assertEqual(budget.ram_bytes, retained)
        # 全部块处理完才开放结果；计数与去重来源以手算核对。
        owner.finish()
        self.assertEqual((owner.facts.value_valid_duration_ns, owner.facts.valid_sample_count), (1000, 1000))
        self.assertEqual(owner.facts.source_refs, (ref,))
        self.assertEqual(owner.facts.value_unknown_ranges, ())

    def test_long_adjacent_unknown_stream_is_one_budgeted_range(self):
        """600 个相邻未知块合成一个正区间，保留预算在首块后稳定。

        参数: 无。返回: None。异常: 每个旧未知片段都永久保留断言失败。
        """
        # 首个未知段需要预算，之后只延长该段端点，不累计600份旧诊断。
        spec = CalculationDefinition('area', 'integral', Interval(0, 600))
        budget = ResourceBudget(400_000)
        owner = self.owner(spec, budget=budget)
        retained = None
        for time in range(600):
            owner.push(self.block(spec, time, time + 1, 0, unknown=(Interval(time, time + 1),), quality=Q.STALE))
            retained = budget.ram_bytes if retained is None else retained
            self.assertEqual(budget.ram_bytes, retained)
        # 全未知须完整保留诊断，不能按无有效值删去整窗范围。
        owner.finish()
        self.assertEqual(owner.facts.value_unknown_ranges, (Interval(0, 600),))
        self.assertEqual(owner.facts.value_valid_duration_ns, 0)

    def test_disjoint_unknown_growth_stops_at_budget_without_truncation(self):
        """交替有效/未知区间无法压成一段，达到预算时失败而非删除旧诊断。

        参数: 无。返回: None。异常: 超限不失败、可读残缺结果或关闭漏账断言失败。
        """
        # 有效间隔阻止未知合并；小预算下检查可预计的明确失败。
        spec = CalculationDefinition('area', 'integral', Interval(0, 1000))
        budget = ResourceBudget(500_000)
        budget.reserve_ram(1234)
        owner = self.owner(spec, budget=budget)
        stopped = False
        for time in range(0, 1000, 2):
            try:
                owner.push(self.block(spec, time, time + 2, 1, unknown=(Interval(time + 1, time + 2),)))
            except BudgetExceededError:
                stopped = True
                break
        # 未完成或超限事实不能读取；close 仅归还自己的金额，借用1234仍保留。
        self.assertTrue(stopped)
        self.assertTrue(owner.failed)
        self.assertLessEqual(budget.ram_bytes, budget.memory_budget_bytes)
        with self.assertRaises(RuntimeError):
            _ = owner.facts
        owner.close()
        self.assertEqual(budget.ram_bytes, 1234)
        budget.release_ram(1234)

    def test_unique_csv_source_growth_alone_stops_at_budget(self):
        """所有区间有效且无未知范围，独立来源增长仍必须受预算限制。

        参数: 无。返回: None。异常: 来源未计费、丢失CSV细节或关闭漏账断言失败。
        """
        # 长原文本来自调用方；新 owner 保留每个完整行定位前仍需申请预算。
        spec = CalculationDefinition('area', 'integral', Interval(0, 200))
        budget = ResourceBudget(500_000)
        budget.reserve_ram(1234)
        owner = self.owner(spec, budget=budget)
        stopped = False
        accepted = 0
        for time in range(200):
            ref = CSVSourceRef('session', 'table', 'raw.a', 'input.csv', time + 2,
                               str(time), '1' * 1000, False)
            try:
                owner.push(self.block(spec, time, time + 1, refs=(ref,)))
                accepted += 1
            except BudgetExceededError:
                stopped = True
                break
        # 未知为空仍超限，不能把唯一行丢掉或只保留三个基础字段来继续。
        self.assertTrue(stopped)
        self.assertGreater(accepted, 0)
        self.assertTrue(owner.failed)
        self.assertLessEqual(budget.ram_bytes, budget.memory_budget_bytes)
        with self.assertRaises(RuntimeError):
            owner.finish()
        owner.close()
        self.assertEqual(budget.ram_bytes, 1234)
        budget.release_ram(1234)

    def test_candidate_is_not_allocated_before_budget_and_failure_closes(self):
        """不足候选预算时不构造合并容器；真实分配失败后仍归还全部持有量。

        参数: 无。返回: None。异常: 分配先于申请或清理漏账断言失败。
        """
        # 分别测试申请拒绝和申请后分配失败，合并函数调用次数证明顺序。
        for allocation_error in (False, True):
            budget = ResourceBudget()
            owner = self.owner(budget=budget)
            if not allocation_error:
                budget.memory_budget_bytes = budget.ram_bytes
            with patch.object(module, '_join_unknown', side_effect=MemoryError('candidate')) as build:
                with self.assertRaises(MemoryError if allocation_error else BudgetExceededError):
                    owner.push(self.block(CalculationDefinition('area', 'integral', Interval(0, 9)), 0, 9))
                self.assertEqual(build.call_count, int(allocation_error))
            # 不论故障发生在哪里，仍有已交付 owner 可以精确清理。
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_constructor_reserve_cancellation_before_after_preserves_borrowed_ram(self):
        """初始申请前/成功后取消都不会漏账或扣掉调用方既有 RAM。

        参数: 无。返回: None。异常: 构造失败后账本不回到基线断言失败。
        """
        # 构造不交付对象，必须由构造异常路径归还真实成功的申请。
        spec = CalculationDefinition('area', 'integral', Interval(0, 9))
        for after in (False, True):
            budget = ResourceBudget()
            budget.reserve_ram(1234)
            with patch.object(budget, 'reserve_ram', side_effect=self.cancel_once(budget.reserve_ram, after)):
                with self.assertRaises(KeyboardInterrupt):
                    IntegralFactsAccumulator(budget, spec, spec.window, 'W', 'explicit-facts')
            self.assertEqual(budget.ram_bytes, 1234)
            budget.release_ram(1234)

    def test_constructor_double_cancellation_retries_cleanup_and_keeps_original_exception(self):
        """初次申请成功后取消，首次清理又取消，最小重试归还 RAM 且保留原异常。

        参数: 无。返回: None。异常: 原原因被覆盖或没有清理第二次取消断言失败。
        """
        spec = CalculationDefinition('area', 'integral', Interval(0, 9))
        budget = ResourceBudget()
        budget.reserve_ram(1234)
        # 两次独立取消：先让申请成功，随后阻断首次清理，第二次清理应成功。
        reserve_fault = self.cancel_once(budget.reserve_ram, True)
        release_fault = self.cancel_once(budget.release_ram, False)
        with patch.object(budget, 'reserve_ram', side_effect=reserve_fault), patch.object(budget, 'release_ram', side_effect=release_fault) as release:
            with self.assertRaises(KeyboardInterrupt) as caught:
                IntegralFactsAccumulator(budget, spec, spec.window, 'W', 'identity')
            self.assertEqual(str(caught.exception), 'integral-facts-test')
            self.assertEqual(release.call_count, 2)
            self.assertTrue(caught.exception.__notes__)
        # 对象未交付也不遗留金额，借用账本金额最后由本测试释放。
        self.assertEqual(budget.ram_bytes, 1234)
        budget.release_ram(1234)

    def test_constructor_persistent_cleanup_failure_exposes_recovery_owner(self):
        """持续拒绝释放时原异常仍给出可访问 owner，恢复账本后可显式关闭。

        参数: 无。返回: None。异常: 无界重试、恢复入口丢失或最终漏账断言失败。
        """
        spec = CalculationDefinition('area', 'integral', Interval(0, 9))
        budget = ResourceBudget()
        budget.reserve_ram(1234)
        # 持续释放错误不能无限重试；原异常须保留 self 作为恢复时可操作的 owner。
        with patch.object(budget, 'reserve_ram', side_effect=self.cancel_once(budget.reserve_ram, True)), patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-cleanup')) as release:
            with self.assertRaises(KeyboardInterrupt) as caught:
                IntegralFactsAccumulator(budget, spec, spec.window, 'W', 'identity')
            self.assertEqual(str(caught.exception), 'integral-facts-test')
            self.assertEqual(release.call_count, 2)
            recovery = caught.exception.integral_facts_cleanup_owner
            self.addCleanup(recovery.close)
            self.assertFalse(recovery.closed)
            self.assertGreater(budget.ram_bytes, 1234)
        # 故障作用域结束后实际重试，检查原异常恢复入口能归还全部自有 RAM。
        recovery.close()
        self.assertEqual(budget.ram_bytes, 1234)
        budget.release_ram(1234)

    def test_push_reserve_and_release_cancellation_before_after_keeps_closable_owner(self):
        """候选申请及余量释放的四种取消时机均只允许随后关闭，最终精确归还。

        参数: 无。返回: None。异常: 取消后继续读取/推进或最终漏账断言失败。
        """
        spec = CalculationDefinition('area', 'integral', Interval(0, 9))
        # 交叉覆盖两个账本动作的前后取消，当前 owner 不能再 finish 或继续追加。
        for method in ('reserve_ram', 'release_ram'):
            for after in (False, True):
                with self.subTest(method=method, after=after):
                    budget = ResourceBudget()
                    budget.reserve_ram(1234)
                    owner = self.owner(spec, budget=budget)
                    original = getattr(budget, method)
                    with patch.object(budget, method, side_effect=self.cancel_once(original, after)):
                        with self.assertRaises(KeyboardInterrupt):
                            owner.push(self.block(spec, 0, 9))
                    # 故障恢复后关闭现有句柄，不能把已归还金额再扣一次。
                    self.assertTrue(owner.failed)
                    with self.assertRaises(RuntimeError):
                        owner.finish()
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 1234)
                    budget.release_ram(1234)

    def test_close_release_cancellation_before_after_is_retryable_and_never_double_charges(self):
        """关闭前取消保留状态供重试，成功后取消已结束；重复关闭不多扣账。

        参数: 无。返回: None。异常: 状态与实际释放不符或重复扣账断言失败。
        """
        # 关闭的前后取消有不同状态，检查实际扣账再重试而非只看是否抛异常。
        for after in (False, True):
            budget = ResourceBudget()
            budget.reserve_ram(1234)
            owner = self.owner(budget=budget)
            with patch.object(budget, 'release_ram', side_effect=self.cancel_once(budget.release_ram, after)):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
                self.assertEqual(owner.closed, after)
                with self.assertRaises(ResultClosedError):
                    _ = owner.facts
                owner.close()
            owner.close()
            self.assertEqual(budget.ram_bytes, 1234)
            budget.release_ram(1234)

    def test_invalid_constructor_and_initial_allocation_failure_leave_no_ram(self):
        """静态非法输入、初始预算不足或去重分配失败都没有可交付半成品。

        参数: 无。返回: None。异常: 非法输入被接收或构造留账断言失败。
        """
        # 静态输入先拒绝，预算和分配失败另测，不用一个错误遮盖另一个。
        spec = CalculationDefinition('area', 'integral', Interval(0, 9))
        budget = ResourceBudget()
        for bad in (None, 'observation'):
            with self.assertRaises(TypeError):
                IntegralFactsAccumulator(budget, spec, bad, 'W', 'identity')
        with self.assertRaises(TypeError):
            IntegralFactsAccumulator(budget, replace(spec, operation='duration'), spec.window, 'W', 'identity')
        with self.assertRaises(ValueError):
            IntegralFactsAccumulator(budget, replace(spec, output_unit='Ah'), spec.window, 'W', 'identity')
        # 初始去重发生在申请之后；构造实际分配失败须归还刚申请的金额。
        with patch.object(module, '_unique_refs', side_effect=MemoryError('initial')):
            with self.assertRaises(MemoryError):
                IntegralFactsAccumulator(budget, spec, spec.window, 'W', 'identity')
        self.assertEqual(budget.ram_bytes, 0)
        # 连固定状态都装不下时，申请本身不应改变预算账本。
        small = ResourceBudget(1)
        with self.assertRaises(BudgetExceededError):
            IntegralFactsAccumulator(small, spec, spec.window, 'W', 'identity')
        self.assertEqual(small.ram_bytes, 0)
