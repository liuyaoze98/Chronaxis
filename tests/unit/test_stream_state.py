"""验证完整同刻组原子提交、声明冲突政策和最新记录的有限预算。

合成内存来源经真实reference/numpy归一化和完整同刻分组后交给状态，四切分有手算真值。
直接小型规范记录用于隔离坏绑定、枚举域、NaN、取消式构造故障与预算不足。
测试只在新项目工作目录创建夹具；不写旧快照。
本节点没有TTL/EOF查询或表达式数值核，不将控制协议测试当完整AnalysisRunner验收。
"""

# 合成输入、实际来源和局部故障替换，不复制或修改旧链。
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import MemoryRow, SourceRef, SourceSpec, TimebaseSpec
from chronaxis.core.numeric import ScalarValue, normalize_reference
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.batch_signal_groups import BatchSignalGroups
from chronaxis.execution.history_records import HistorySample
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.state import LatestSignalState, CommittedUpdates
from chronaxis.results import BudgetExceededError, ResultClosedError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest
from chronaxis.sources.csv_spec import CSVSourceRef


def make_sample(definition, time, sequence, raw, *, reference=None):
    """构造已归一化小记录，控制协议不再计算单位换算。

    参数: definition声明/time整数ns/sequence原行/raw原标量/reference可选定位。
    返回: HistorySample；ENUM物理值用当前标签下标，无效值保持掩码和原诊断。
    异常: 夹具模型错误直接传播，不隐藏未到达的被测路径。
    """
    value = normalize_reference(definition, raw)
    if value.valid:
        physical = value.labels.index(value.value) if definition.dtype is D.ENUM else value.value
    else:
        physical = 0.0 if definition.dtype is D.FLOAT64 else False if definition.dtype is D.BOOL else 0
    return HistorySample(0, definition.name, time, sequence, physical, value, definition.unit,
                         reference or SourceRef('session', definition.source, definition.field), True, raw)


class StreamStateTests(unittest.TestCase):
    """每项新账本/状态，完整组共享时间而原行sequence仍独立。"""

    def setUp(self):
        """建立两别名及唯一专用目录，原始政策默认error。

        参数: 无。返回: None。异常: 声明/工作目录错误直接失败。
        """
        self.work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/stream-state' / uuid4().hex
        self.work.mkdir(parents=True)
        self.a = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'A', 3)
        self.z = SignalDefinition('z', 'table', 'raw.z', D.FLOAT64, 'A', 3)

    def state(self, definitions=None, budget=None):
        """构造并登记清理，不向状态提供完整原始行。

        参数: definitions可选冻结声明/budget可选共享账本。返回: LatestSignalState。
        异常: 配置/预算错误传播。
        """
        state = LatestSignalState(budget or ResourceBudget(32 * 1024 ** 2), definitions or (self.a, self.z), 'session')
        self.addCleanup(state.close)
        return state

    def test_both_backend_batch_splits_hand_values(self):
        """两后端四切分完整组只提交一次，单位/1ns/大整数/BOOL/ENUM与无效覆盖手算成立。

        参数: 无。返回: None。异常: 分批重置/顺序选错/转换重复或质量丢失断言失败。
        """
        start = 2 ** 53
        current = replace(self.a, input_unit='mA', scale=.001, same_time_policy='last_by_sequence')
        identifier = SignalDefinition('identifier', 'table', 'raw.name', D.UINT64, '1', 3)
        enabled = SignalDefinition('enabled', 'table', 'raw.b', D.BOOL, '1', 3)
        mode = SignalDefinition('mode', 'table', 'raw.e', D.ENUM, '1', 3, choices=((1, 'scope'), (0, 'off')))
        definitions = (current, identifier, enabled, mode)
        rows = (MemoryRow(time_ns=start, sequence=0, values={'raw.a':1000, 'raw.name':2**64-1, 'raw.b':True, 'raw.e':1}),
                MemoryRow(time_ns=start, sequence=1, values={'raw.a':2000}),
                MemoryRow(time_ns=start+1, sequence=2, values={'raw.a':None, 'raw.b':False}),
                MemoryRow(time_ns=start+2, sequence=3, values={'raw.a':3000, 'raw.e':0}))
        source = SourceSpec('table', TimebaseSpec('clock', TimeType.RELATIVE, 'stream-state-synthetic'), rows,
                            observation_start_ns=start, observation_end_ns=start+3)
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7, 65536):
                budget = ResourceBudget(32 * 1024 ** 2)
                adapter = BudgetedMemorySourceAdapter(budget, source, 'session', definitions, backend=backend)
                self.addCleanup(adapter.close)
                request = ReadRequest('session', tuple(item.name for item in definitions), start, start+3, size)
                state = self.state(definitions, budget)
                results = []
                def consume(group):
                    """原子提交真实完整组。参数: group。返回: None。异常: 状态原错误。"""
                    committed = state.apply(group)
                    results.append((committed.time_ns, committed.conflict_count, state.get('a').value.value, state.get('a').value.valid))
                grouping = BatchSignalGroups(budget, definitions, 'session', consume)
                self.addCleanup(grouping.close)
                for batch in adapter.iter_batches(request):
                    grouping.consume(batch)
                grouping.finish()
                adapter.close()
                self.assertEqual(results, [(start,1,2.,True),(start+1,0,None,False),(start+2,0,3.,True)])
                self.assertEqual(state.get('identifier').value.value, 2**64-1)
                self.assertFalse(state.get('enabled').value.value)
                self.assertEqual(state.get('mode').value.value, 'off')
                self.assertEqual(state.conflict_count, 1)
                state.close()
                grouping.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_conflict_is_atomic_and_same_fact_chooses_sequence(self):
        """晚别名冲突不能提交早别名；相同事实选最大原seq而不计冲突。

        参数: 无。返回: None。异常: 部分更新/计数或时间变化断言失败。
        """
        state = self.state()
        initial = DecodedTimeGroup(0, (make_sample(self.a,0,0,1), make_sample(self.z,0,0,1)))
        state.apply(initial)
        before = (state.get('a'), state.get('z'), state.last_time_ns, state.conflict_count, state.budget.ram_bytes)
        bad = DecodedTimeGroup(1, (make_sample(self.a,1,1,2), make_sample(self.z,1,1,2), make_sample(self.z,1,2,3)))
        with self.assertRaises(ValueError):
            state.apply(bad)
        self.assertEqual((state.get('a'), state.get('z'), state.last_time_ns, state.conflict_count, state.budget.ram_bytes), before)
        same = DecodedTimeGroup(1, (make_sample(self.a,1,10,2), make_sample(self.a,1,3,2)))
        result = state.apply(same)
        self.assertEqual((result.updates[0].sequence, result.conflict_count), (10,0))

    def test_last_by_sequence_and_invalid_nan_facts(self):
        """显式最后原序号独立于遍历顺序；同原因NaN一致，无效更新覆盖旧值。

        参数: 无。返回: None。异常: 选首项/回退旧值/NaN冲突计数错误断言失败。
        """
        definition = replace(self.a, same_time_policy='last_by_sequence')
        state = self.state((definition,))
        result = state.apply(DecodedTimeGroup(0, (make_sample(definition,0,9,9), make_sample(definition,0,2,2), make_sample(definition,0,4,4))))
        self.assertEqual((result.updates[0].sequence, result.conflict_count, state.conflict_count), (9,2,2))
        missing = make_sample(definition,1,10,None)
        state.apply(DecodedTimeGroup(1,(missing,)))
        self.assertIs(state.get('a'), missing)
        self.assertFalse(state.get('a').value.valid)
        # 两个独立NaN对象是同因无效事实，不能借NaN普通不相等增加冲突。
        result = state.apply(DecodedTimeGroup(2, (make_sample(definition,2,11,float('nan')), make_sample(definition,2,12,float('nan')))))
        self.assertEqual(result.conflict_count, 0)
        self.assertFalse(state.get('a').value.valid)
        self.assertTrue(state.get('a').value.quality & Q.NONFINITE)

    def test_bad_binding_dtype_unit_and_time_leave_state(self):
        """未知别名/源/字段/会话/类型/单位、重复或回退时间都不部分提交。

        参数: 无。返回: None。异常: 坏组污染任何别名/预算或提交时间断言失败。
        """
        state = self.state()
        original = make_sample(self.a,0,0,1)
        state.apply(DecodedTimeGroup(0,(original,)))
        sample = make_sample(self.a,1,1,2)
        bad_samples = (replace(sample,name='other'), replace(sample,source_ref=SourceRef('other','table','raw.a')),
                       replace(sample,source_ref=SourceRef('session','other','raw.a')), replace(sample,source_ref=SourceRef('session','table','other')),
                       replace(sample,unit='V'), replace(sample,array_value=2,value=ScalarValue(2,D.INT64)))
        before = state.budget.ram_bytes
        for bad in bad_samples:
            with self.assertRaises(ValueError):
                state.apply(DecodedTimeGroup(1,(make_sample(self.z,1,1,3),bad)))
            self.assertIs(state.get('a'), original)
            self.assertIsNone(state.get('z'))
            self.assertEqual((state.last_time_ns,state.budget.ram_bytes),(0,before))
        for time in (0,-1):
            with self.assertRaises(ValueError):
                state.apply(DecodedTimeGroup(time,(make_sample(self.a,time,2,3),)))

    def test_enum_domain_must_match_current_definition(self):
        """物理/逻辑自洽但标签域不同的ENUM不能进入当前绑定。

        参数: 无。返回: None。异常: 未声明标签被接收或状态部分变化断言失败。
        """
        definition = SignalDefinition('mode','table','raw.e',D.ENUM,'1',3,choices=((1,'scope'),(0,'off')))
        state = self.state((definition,))
        normal = make_sample(definition,0,0,1)
        state.apply(DecodedTimeGroup(0,(normal,)))
        before = state.budget.ram_bytes
        # 外来标签、域中多一标签、域顺序变化及无效记录均不能绕过当前声明。
        for value,physical in ((ScalarValue('other',D.ENUM,True,Q.NONE,('other',)),0),
                               (ScalarValue('scope',D.ENUM,True,Q.NONE,('scope','off','other')),0),
                               (ScalarValue('scope',D.ENUM,True,Q.NONE,('off','scope')),1),
                               (ScalarValue(None,D.ENUM,False,Q.MISSING,('other',)),0)):
            forged = replace(normal,time_ns=1,sequence=1,array_value=physical,value=value)
            with self.assertRaises(ValueError):
                state.apply(DecodedTimeGroup(1,(forged,)))
            self.assertIs(state.get('mode'), normal)
            self.assertEqual(state.budget.ram_bytes,before)

    def test_budget_and_result_construction_failure_are_atomic(self):
        """预算失败在结果构造前发生；结果构造MemoryError也保留旧状态并释放临时量。

        参数: 无。返回: None。异常: 先构造/部分提交/预算泄漏断言失败。
        """
        state = self.state()
        original = make_sample(self.a,0,0,1)
        state.apply(DecodedTimeGroup(0,(original,)))
        group = DecodedTimeGroup(1,(make_sample(self.a,1,1,2),))
        baseline = state.budget.ram_bytes
        blocker = state.budget.memory_budget_bytes-baseline-1
        state.budget.reserve_ram(blocker)
        with patch('chronaxis.execution.state._committed_from_validated_fields') as constructed:
            with self.assertRaises(BudgetExceededError):
                state.apply(group)
        constructed.assert_not_called()
        state.budget.release_ram(blocker)
        with patch('chronaxis.execution.state._committed_from_validated_fields',side_effect=MemoryError('injected result')):
            with self.assertRaises(MemoryError):
                state.apply(group)
        self.assertIs(state.get('a'),original)
        self.assertEqual((state.last_time_ns,state.budget.ram_bytes),(0,baseline))

    def test_final_snapshot_and_budget_transfer_failure_preserve_entire_state(self):
        """最终快照构造或转账失败时，时间/冲突/各别名/预算全部保持旧事实。

        参数: 无。返回: None。异常: 任何部分安装或清理泄漏断言失败。
        """
        state = self.state((replace(self.a,same_time_policy='last_by_sequence'),self.z))
        original = make_sample(self.a,0,0,1)
        state.apply(DecodedTimeGroup(0,(original,)))
        group = DecodedTimeGroup(1,(make_sample(self.a,1,1,2),make_sample(self.a,1,2,3),make_sample(self.z,1,1,4)))
        baseline = (state.latest,state.last_time_ns,state.conflict_count,state.retained_cost,state.budget.ram_bytes)
        with patch('chronaxis.execution.state._StateSnapshot',side_effect=MemoryError('injected final snapshot')):
            with self.assertRaises(MemoryError):
                state.apply(group)
        self.assertEqual((state.latest,state.last_time_ns,state.conflict_count,state.retained_cost,state.budget.ram_bytes),baseline)
        release = state.budget.release_ram
        attempts = []

        def fail_first_transfer(amount):
            """模拟转账分配失败，第二次调用真实释放以验证异常收尾。

            参数: amount释放bytes。返回: None。异常: 首调用MemoryError，其余账本错误传播。
            """
            attempts.append(amount)
            if len(attempts) == 1:
                raise MemoryError('injected transfer')
            release(amount)

        with patch.object(state.budget,'release_ram',side_effect=fail_first_transfer):
            with self.assertRaises(MemoryError):
                state.apply(group)
        self.assertEqual(len(attempts),2)
        self.assertEqual((state.latest,state.last_time_ns,state.conflict_count,state.retained_cost,state.budget.ram_bytes),baseline)
        # 故障撤销后同一组可提交，累计计数和所有别名一起进入新快照。
        state.apply(group)
        self.assertEqual((state.last_time_ns,state.conflict_count,state.get('a').value.value,state.get('z').value.value),(1,1,3.,4.))

    def test_replacing_large_reference_releases_old_retained_cost(self):
        """长CSV定位被短引用替换时释放负增量，旧只读视图保留但属调用方空间。

        参数: 无。返回: None。异常: 负转账计算错误或关闭重复释放断言失败。
        """
        state = self.state((self.a,))
        reference = CSVSourceRef('session','table','raw.a','synthetic.csv',2,'0','x'*20000,False)
        original = make_sample(self.a,0,0,1,reference=reference)
        state.apply(DecodedTimeGroup(0,(original,)))
        old_view,old_cost = state.latest,state.retained_cost
        state.apply(DecodedTimeGroup(1,(make_sample(self.a,1,1,2),)))
        self.assertIs(old_view['a'],original)
        self.assertEqual(state.get('a').value.value,2.)
        self.assertLess(state.retained_cost,old_cost)
        self.assertEqual(state.budget.ram_bytes,state.fixed_cost+state.retained_cost)
        state.close()
        self.assertEqual(state.budget.ram_bytes,0)

    def test_latest_retained_budget_is_bounded_and_csv_text_counted(self):
        """32与512完整组的最新状态空间稳定；长CSV诊断文本不能越预算提交。

        参数: 无。返回: None。异常: 累积全历史、长引用漏计或失败状态变化断言失败。
        """
        peaks=[]
        for count in (32,512):
            state=self.state((self.a,))
            for time in range(count):
                state.apply(DecodedTimeGroup(time,(make_sample(self.a,time,time,1),)))
            peaks.append(state.budget.peak_ram_bytes)
            self.assertEqual(state.get('a').time_ns,count-1)
            state.close()
            self.assertEqual(state.budget.ram_bytes,0)
        self.assertLessEqual(peaks[1],peaks[0]+8192)
        state=self.state((self.a,),ResourceBudget(1024*1024))
        original=make_sample(self.a,0,0,1)
        state.apply(DecodedTimeGroup(0,(original,)))
        ref=CSVSourceRef('session','table','raw.a','synthetic.csv',2,'1','x'*100000,False)
        long_sample=make_sample(self.a,1,1,2,reference=ref)
        before=state.budget.ram_bytes
        with self.assertRaises(BudgetExceededError):
            state.apply(DecodedTimeGroup(1,(long_sample,)))
        self.assertIs(state.get('a'),original)
        self.assertEqual(state.budget.ram_bytes,before)

    def test_duplicate_definitions_initial_budget_and_close(self):
        """构造失败抵销声明预留；关闭后读取/提交明确拒绝且账本归零。

        参数: 无。返回: None。异常: 重复定义/极低预算被接收或关闭泄漏断言失败。
        """
        budget=ResourceBudget(32*1024**2)
        with self.assertRaises(ValueError):
            LatestSignalState(budget,(self.a,self.a),'session')
        self.assertEqual(budget.ram_bytes,0)
        with self.assertRaises(BudgetExceededError):
            LatestSignalState(ResourceBudget(1),(self.a,),'session')
        state=self.state()
        state.apply(DecodedTimeGroup(0,(make_sample(self.a,0,0,1),)))
        state.close()
        state.close()
        self.assertEqual(state.budget.ram_bytes,0)
        with self.assertRaises(ResultClosedError):
            state.get('a')
        with self.assertRaises(ResultClosedError):
            state.apply(DecodedTimeGroup(1,(make_sample(self.a,1,1,1),)))

    def test_committed_result_rejects_duplicate_names(self):
        """提交结果自身不能混入同名多个观测或负冲突数量。

        参数: 无。返回: None。异常: 非法结果自校验漏检断言失败。
        """
        sample=make_sample(self.a,0,0,1)
        for updates,conflicts in (((sample,make_sample(self.a,0,1,2)),0),((sample,),-1)):
            with self.assertRaises(ValueError):
                CommittedUpdates(0,updates,conflicts)

    def test_public_state_views_and_counters_are_readonly(self):
        """公开状态视图和计数不能绕过apply改写最新观测或预算所有权。

        参数: 无。返回: None。异常: 外部改写成功或状态丢失断言失败。
        """
        state=self.state()
        original=make_sample(self.a,0,0,1)
        state.apply(DecodedTimeGroup(0,(original,)))
        with self.assertRaises((TypeError,AttributeError)):
            state.latest['a']=None
        with self.assertRaises((TypeError,AttributeError)):
            state.definitions['a']=replace(self.a,same_time_policy='last_by_sequence')
        for name in ('latest','definitions','retained_cost','fixed_cost','last_time_ns','conflict_count','closed','session_id','budget'):
            with self.assertRaises(AttributeError):
                setattr(state,name,None)
        self.assertIs(state.get('a'),original)

    def test_same_alias_sequence_with_distinct_csv_locations_is_rejected(self):
        """不同CSV位置不能把相同原seq伪装成不同身份，反序也明确拒绝。

        参数: 无。返回: None。异常: 稳定序号平手依赖遍历顺序或预算泄漏断言失败。
        """
        definition=replace(self.a,same_time_policy='last_by_sequence')
        first=make_sample(definition,1,1,1,reference=CSVSourceRef('session','table','raw.a','first.csv',2,'1','1',False))
        second=make_sample(definition,1,1,2,reference=CSVSourceRef('session','table','raw.a','second.csv',2,'1','2',False))
        equal_fact=replace(second,array_value=first.array_value,value=first.value,original_value=first.original_value)
        for samples in ((first,second),(second,first),(first,equal_fact),(equal_fact,first)):
            state=self.state((definition,))
            baseline=state.budget.ram_bytes
            with self.assertRaises(ValueError):
                state.apply(DecodedTimeGroup(1,samples))
            self.assertIsNone(state.get('a'))
            self.assertEqual(state.budget.ram_bytes,baseline)
