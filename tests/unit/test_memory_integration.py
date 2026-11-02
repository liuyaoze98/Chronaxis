"""把绑定、功率计算、持续条件和积分串起来，检查整条内存分析流程。

输入是同一组明确合成原行，各后端独立转换和计算；输出为unittest断言。
两段活动及能量使用手算真值；跨字段映射和单位转换后应保持物理结果。
同一时刻的样本被任意切批或插入空批时，必须收齐后提交；会话切换不能
继承前一会话状态。积分窗口分块后不得重复结算，也不能把未知面积补零。
当前指标使用完整内存历史；这些检查不证明M2生产内存预算、连续文件或CAN接入。
"""

# 冻结输入变体保留旧对象不改写。
from dataclasses import replace
# 真实回归断言，不靠计数或输出文件数量验收。
import unittest
# 测试查询严格一维int64，数组执行是真实被测后端。
import numpy as np
# 可运行完整M1示例也是验收入口，不额外建空AnalysisRunner。
from examples.memory_analysis import build_bindings, run_analysis
# 真实typed原行/原子组/表达式/指标协议。
from chronaxis.core import (AtomicUpdateBuffer, DerivedDefinition, Interval, MemoryRow, CalculationDefinition,
                            SignalSeries, compile_expression, memory_series_reference, compute_memory_reference)
# 独立实际数组原行归一化及指标链。
from chronaxis.core.normalize_numpy import memory_series_numpy
# NumPy完整输入到结果，不调用标量面积。
from chronaxis.core.calculations_memory_numpy import compute_memory_numpy
# 未知诊断区间合并只是输出协议，不共享积分数值。
from chronaxis.core.calculations import merge_ranges
# 独立三值表达式执行。
from chronaxis.core.expression_reference import evaluate_memory_reference
# 真正数组保持/解释。
from chronaxis.core.expression_numpy import evaluate_memory_numpy
# 完整质量及dtype仍严格区分。
from chronaxis.core.types import QualityFlag as Q, SignalDType as D


class MemoryIntegrationTests(unittest.TestCase):
    """逐字段比较完整任务，手算验证独立后端共同语义。

    每次运行都创建新的状态，batch只改变完整组消费边界。
    """

    def test_t42_mapping_reuse_and_changed_ttl_full_task(self):
        """规则跨字段/单位映射保持物理事实并追溯，TTL变化重算事件与指标。

        参数: 无；原A字段映射到实际mA字段及明确valid_for变化。
        返回: None。
        异常: 物理事实/身份/来源/缓存隔离失败由unittest报告。
        """
        # 当前基础任务的实际输入身份和可核实物理事实。
        base = build_bindings()
        # 新映射来自新的原字段mA，不借旧字段数值或factor缓存。
        source = base.session.sources[0]
        # 仅复制新任务原行；旧输入模型保持不变。
        rows = tuple(replace(row, values={('raw_milliamps' if name == 'raw_i' else name): value*1000 if name == 'raw_i' else value for name, value in row.values.items()}) for row in source.rows)
        # 新定义显式mA→A一次转换，mapping版本和field变更都可追溯。
        current = replace(base.signals[1], field='raw_milliamps', input_unit='mA', scale=.001, mapping_version='mapping-v2')
        # 重新构造当前真实绑定，不从上次任务继承来源。
        mapped = replace(base, session=replace(base.session, sources=(replace(source, rows=rows),)), signals=(base.signals[0], current, base.signals[2]))
        # 同一声明式规则在两种实际mapping分别执行。
        original = run_analysis(base, backend='reference', batch_rows=1)
        # 实际数组新输入从原行归一化/保持开始，不能共享旧值。
        observed = run_analysis(mapped, backend='numpy', batch_rows=2)
        # 物理事实相同，稳定内容event_id不由原字段命名决定。
        self.assertEqual([event.event_id for event in original[0]], [event.event_id for event in observed[0]])
        # 面积数学值相同，输入来源和完整执行身份必须不同。
        self.assertEqual(original[1].value, observed[1].value)
        # 名称文本相同不能当绑定证明。
        self.assertNotEqual(original[1].binding_identity, observed[1].binding_identity)
        # 新真实原字段在事件中可追溯，不能仍指向raw_i。
        self.assertEqual(observed[0][0].source_refs[0].field, 'raw_milliamps')
        # 单独改变TTL1秒，未知缺口中断两段活动，不复用旧计划结果。
        limited = replace(mapped, signals=(mapped.signals[0], replace(current, valid_for_ns=1_000_000_000), mapped.signals[2]))
        # 新reference/NumPy实际源绑定都重算完整任务。
        reference = run_analysis(limited, backend='reference', batch_rows=1)
        # 完整原因/事件/指标对象相同，不只面积。
        self.assertEqual(reference, run_analysis(limited, backend='numpy', batch_rows=7))
        # 两段各只有1秒有效：4000+8000=12000J，不沿用旧24000。
        self.assertEqual((reference[1].value, reference[1].status), (12000., 'partial'))
        # TTL恰门槛先确认，再interrupted；事件均不跨未知。
        self.assertEqual([event.status for event in reference[0]], ['interrupted', 'interrupted'])

    def test_full_task_events_calculations_and_backend_batches(self):
        """两活动/分scope能量与会话选择积分保持手算事实。

        参数: 无；memory-analysis-v1明确合成输入。
        返回: None。
        异常: 完整事实或手算能量差异由unittest报告。
        """
        # 同一当前绑定，两个后端创建各自执行状态。
        bindings = build_bindings()
        # 参考完整任务包含真实source/binding/quality对象。
        expected = run_analysis(bindings, backend='reference')
        # 在deadline/活动中间及EOF处改变完整组batch大小。
        for size in (1, 2, 7, 65536):
            # 同一完整任务不以batch编号重写event_id。
            self.assertEqual(expected, run_analysis(bindings, backend='reference', batch_rows=size))
            # 真正数组后端包括内存接线/指标，不只换函数名。
            self.assertEqual(expected, run_analysis(bindings, backend='numpy', batch_rows=size))
        # 独立手算两段真实活动，不跨中间FALSE合并。
        self.assertEqual([(event.start_ns, event.confirmed_ns, event.end_ns) for event in expected[0]],
                         [(0, 1_000_000_000, 2_000_000_000), (3_000_000_000, 4_000_000_000, 5_000_000_000)])
        # 400V*10A*2s=8000J，400V*20A*2s=16000J。
        self.assertEqual([calculation.value for _, calculation in expected[2]], [8000., 16000.])
        # 会话选择面积等于两真实活动，FALSE已知不计缺失。
        self.assertEqual((expected[1].value, expected[1].condition_coverage), (24000., 1.))
        # event统计区间标记与session明确分开。
        self.assertTrue(all(calculation.spec.scope == 'event' for _, calculation in expected[2]))
        # 当前原字段定位/执行身份不是只有名称声明。
        self.assertTrue(expected[1].binding_identity and expected[1].source_refs)
        # 大标识仍原生整数，没有为了组合列转换float。
        reference = memory_series_reference(bindings, 'identifier')
        # NumPy归一化也保留同INT64精确值。
        array = memory_series_numpy(bindings, 'identifier')
        # T33完整任务中的整数身份未失真。
        self.assertEqual(reference.samples, array.samples)
        # 精确大奇数不是近似float。
        self.assertEqual(reference.samples[0].value, 2 ** 53+1)

    def test_atomic_group_arbitrary_sample_splits_and_empty_batches(self):
        """同刻依赖跨任意原样本batch收齐，空批不能提前提交或reset。

        参数: 无；当前输入全部规范化SignalSample，明确合法原顺序。
        返回: None。
        异常: 分组/来源/真实状态差异由unittest报告。
        """
        # 两归一化后端从相同原行产生输入样本，buffer只处理时间协议。
        bindings = build_bindings()
        # 当前定义布局固定，不靠名字排序改变组内容。
        histories = tuple(memory_series_reference(bindings, definition.name) for definition in bindings.signals)
        # 已排序合成样本流只在测试中合并分析输出，不改原读写顺序。
        samples = tuple(sorted((sample for history in histories for sample in history.samples), key=lambda sample: sample.time_ns))
        # 先获得单批完整原子组基线。
        full = AtomicUpdateBuffer(bindings)
        # 只有真正EOF才提交最后pending。
        expected = full.push(samples) + full.finish()
        # 一条一批必然将0秒的多列原子组拆开。
        for size in (1, 2, 7):
            # 新buffer独立，不沿用之前会话pending。
            buffer, groups = AtomicUpdateBuffer(bindings), []
            # 推进原始规范化样本批，不在batch尾finish。
            for offset in range(0, len(samples), size):
                # 空batch没有隐式收尾。
                self.assertEqual(buffer.push(()), ())
                # 尚未收齐同时间末组保留在buffer。
                groups.extend(buffer.push(samples[offset:offset+size]))
            # 真正完整输入EOF一次完成pending。
            groups.extend(buffer.finish())
            # 全部updates/quality/source及冲突数一致。
            self.assertEqual(tuple(groups), expected)
            # 重建每列仅用于证明没有丢掉/重复样本，不能绕过归属校验。
            for history in histories:
                # 完整组中的各列原样本顺序保持。
                restored = tuple(sample for group in groups for sample in group.updates if sample.name == history.name)
                # 当前模型再次核实当前绑定/原sequence/field一致。
                self.assertEqual(SignalSeries(bindings, history.name, restored), history)

    def test_integral_window_blocks_no_double_settlement_with_unknown(self):
        """在门槛/TTL/面积中间裁剪分块，和为完整已核实面积且未知不补零。

        参数: 无；正常及实际invalid变体，保留完整内存历史供因果窗口查询。
        返回: None。
        异常: 面积/覆盖/未知范围或重复结算失败由unittest报告。
        边界: 这是M1内存窗口分块验证，不是M2流式暂存验收。
        """
        # 正常任务与1秒真实invalid两变体，各输入身份不同。
        bindings = build_bindings()
        # 保持原sequence/字段来源，替换新输入而不改原对象。
        source = bindings.session.sources[0]
        # 1秒invalid覆盖旧有效电流，未知持续到3秒真实恢复。
        rows = (source.rows[0], MemoryRow(1_000_000_000, {'raw_i': None}, 1), *source.rows[2:])
        # 当前会话/来源模型重新校验真实范围与原顺序。
        invalid = replace(bindings, session=replace(bindings.session, sources=(replace(source, rows=rows),)))
        # 切点包含deadline前后、未知中间与正常积分区间中间。
        cuts = (0, 250_000_000, 1_000_000_000, 2_500_000_000, 3_250_000_000, 4_500_000_000, 6_000_000_000)
        # 两后端独立原行保持与完整指标，不向数组提供参考结果。
        for current in (bindings, invalid):
            # 完整派生定义在每个表达式中校验，名称空间隔离。
            derived = (DerivedDefinition('power', 'voltage * current', 'W'),)
            # 数值和条件都来自当前完整绑定。
            power = compile_expression('power', current, derived=derived)
            # 条件选择三值未知不能自动FALSE。
            condition = compile_expression('current > 5', current, derived=derived)
            # 全部窗口覆盖同一域，半开不重叠。
            spec = CalculationDefinition('energy', 'integral', Interval(cuts[0], cuts[-1]))
            # 正常与invalid全域手算分别24000J/20000J。
            expected_value = 24000. if current is bindings else 20000.
            # 对两独立执行链分别验证面积及覆盖可分解。
            for compute in (compute_memory_reference, compute_memory_numpy):
                # 全域结果保留全部coverage/UNKNOWN范围。
                whole = compute(power, spec, condition=condition)
                # 每块当前左边保持需要已有前置历史，不重新从空状态开始。
                blocks = tuple(compute(power, replace(spec, window=Interval(left, right)), condition=condition) for left, right in zip(cuts, cuts[1:]))
                # 未知块null没有正常0，将有核实面积的块求和。
                self.assertAlmostEqual(sum(block.value for block in blocks if block.value is not None), expected_value)
                # 全域真值同时独立检查。
                self.assertEqual(whole.value, expected_value)
                # 时长精确整数相加，无重复边界周期。
                self.assertEqual(sum(block.value_valid_duration_ns for block in blocks), whole.value_valid_duration_ns)
                # 条件已知与选中覆盖也各结算一次。
                self.assertEqual(sum(block.selected_duration_ns for block in blocks), whole.selected_duration_ns)
                # 当前未知范围合并只压缩相邻输出，不填平known缺口。
                self.assertEqual(merge_ranges(tuple(interval for block in blocks for interval in block.condition_unknown_ranges)), whole.condition_unknown_ranges)

    def test_new_sessions_do_not_join_and_async_quality(self):
        """两个TRUE2秒会话不拼成4秒；异步TTL/除零诊断独立一致。

        参数: 无；新session短域与两个列不同TTL。
        返回: None。
        异常: 状态继承、质量或当前绑定差异由unittest报告。
        """
        # 每个session只有2秒，duration3不够，不能跨session确认。
        base = build_bindings()
        # 同源短输入保留真实字段/序号，末样本提供domain边界。
        source = replace(base.session.sources[0], rows=base.session.sources[0].rows[:2], observation_end_ns=2_000_000_000)
        # 两个独立新session使用相同别名，不同身份。
        for name in ('first', 'second'):
            # 冻结当前会话与绑定，不共享上次candidate。
            bindings = replace(base, session=replace(base.session, session_id=name, domain_end_ns=2_000_000_000, sources=(source,)))
            # 每后端都独立初始化，而非累计4秒。
            for backend in ('reference', 'numpy'):
                # batch1穿过2秒真实终点FALSE。
                events, _, _ = run_analysis(bindings, backend=backend, batch_rows=1, duration_ns=3_000_000_000)
                # T28没有确认事实。
                self.assertEqual(events, ())
        # Voltage TTL.5s/current TTL1s，异步更新使质量来源不同。
        signals = (replace(base.signals[0], valid_for_ns=500_000_000), replace(base.signals[1], valid_for_ns=1_000_000_000), base.signals[2])
        # 完整绑定身份改变，旧执行引用不能复用。
        bindings = replace(base, signals=signals)
        # 当前派生语法/单位仍独立校验。
        derived = (DerivedDefinition('power', 'voltage * current', 'W'),)
        # 根表达式包括正常/过期/合法配置除零两种数值能力。
        for text in ('power', 'current / current'):
            # 每次当前绑定编译，不继承旧列缓存。
            compiled = compile_expression(text, bindings, derived=derived)
            # 查询在TTL前后和真实零值更新后，时间不浮点化。
            times = (0, 750_000_000, 1_500_000_000, 2_000_000_000, 3_000_000_000)
            # 标量参考独立保持/表达式。
            reference = evaluate_memory_reference(compiled, times)
            # 数组实际独立归一化/保持/表达式。
            array = evaluate_memory_numpy(compiled, np.array(times, dtype=np.int64))
            # 不压缩STALE/DOMAIN原因或用正常0替代未知。
            self.assertEqual([int(result.value.quality) for result in reference], array.value.quality.tolist())
            # 所有可用值mask完整一致。
            self.assertEqual([result.value.valid for result in reference], array.value.valid.tolist())
            # 合法除零属于运行数值失效，不是配置语法错误。
            if text == 'current / current':
                # 2秒真实current0时明确DOMAIN_ERROR。
                self.assertTrue(reference[3].value.quality & Q.DOMAIN_ERROR)
        # 后端不能无声回退到参考，否则能力声明不真实。
        with self.assertRaises(ValueError):
            # 明确拒绝未知后端。
            run_analysis(base, backend='unregistered')
