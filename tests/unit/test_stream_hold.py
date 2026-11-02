"""验证流式最新状态的独立参考/NumPy保持查询及查询结果资源所有权。

输入是有手算真值的合成内存来源，实际经过两种归一化、历史暂存和完整组提交；
直接构造的小记录隔离TTL、来源范围、定宽值、坏上下文及分配故障边界。
输出断言分别核对逻辑行与物理数组，不能用一个被测内核生成另一个的预期值。
测试只在work/m2-run-tests/stream-hold唯一目录写新历史，device_label为work；
不调用或修改RefProjects，不把保持子节点通过解释为AnalysisRunner/事件验收完成。
"""

# 合成数据、独立数组断言及局部构造故障，只作用于新分析层。
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import Interval, MemoryRow, SourceRef, SourceSpec, TimebaseSpec
from chronaxis.core.numeric import normalize_reference
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.history_records import HistoryProgress, HistorySample, estimate_record_bytes
from chronaxis.execution.hold import HoldContext, HoldQueries
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.state import LatestSignalState
from chronaxis.results import BudgetExceededError, ResultClosedError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest, SourceCapabilities, SourceDescription
from chronaxis.sources.csv_spec import CSVSourceRef
from chronaxis.sources.descriptions import describe_fields


def make_record(definition, time_ns, sequence, raw, reference=None):
    """构造已规范化夹具，不让保持查询重复单位或枚举转换。

    参数: definition当前声明；time_ns/sequence为原时间/序号；raw原标量；reference可选定位。
    返回: HistorySample，逻辑诊断和物理占位分别保存。
    异常: 声明/夹具错误直接传播，未执行被测内核时不称产品失败。
    """
    # 归一化仅用于制造输入；查询参考预期另用手算常量。
    value = normalize_reference(definition, raw)
    if value.valid:
        physical = value.labels.index(value.value) if definition.dtype is D.ENUM else value.value
    else:
        physical = 0.0 if definition.dtype is D.FLOAT64 else False if definition.dtype is D.BOOL else 0
    # CSV引用属于原样本事实，不能由查询换成普通SourceRef丢位置。
    source_ref = reference or SourceRef('session', definition.source, definition.field)
    return HistorySample(0, definition.name, time_ns, sequence, physical, value, definition.unit,
                         source_ref, True, raw)


def make_description(source, definitions, start, end):
    """建立不读取输入的静态声明，未知端点保持None。

    参数: source来源名；definitions本来源冻结定义；start/end分析坐标端点或None。
    返回: SourceDescription，其状态仍为declared，不冒充实际seal证据。
    异常: 描述结构或时间错误直接传播。
    """
    # 复用已校验字段元数据，使类型/单位/枚举域与当前声明一致。
    fields = describe_fields(source, definitions)
    return SourceDescription(source, fields, 'clock', start, end,
                             SourceCapabilities(True, False, False, False), metadata_status='declared')


class RejectResultRegistry(set):
    """模拟结果已构造但owner登记分配失败；不保留半成品引用。"""

    def add(self, result):
        """在集合安装前抛分配故障，验证整个查询申请抵销。

        参数: result待登记结果。返回: 无正常返回。异常: MemoryError为明确注入。
        """
        # 只阻断新层自有登记；原集合和其他活动结果不被修改。
        raise MemoryError('hold-registry-test')


class StreamHoldTests(unittest.TestCase):
    """各项独立账本/上下文/owner，结果关闭和状态关闭的所有权分别核对。"""

    def setUp(self):
        """建立唯一新工作目录及默认浮点声明。

        参数: 无。返回: None。异常: 新目录/声明错误直接失败。
        """
        # 保留新层验证文件，既不写旧快照，也不复用其他测试的历史目录。
        self.work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/stream-hold' / uuid4().hex
        self.work.mkdir(parents=True)
        self.a = SignalDefinition('a', 'table', 'raw.a', D.FLOAT64, 'A', 3)

    def context(self, definitions=None, *, domain=(0, 10), bounds=None, session='session'):
        """建立显式来源范围与whole-source EOF原事实，不假造开始点。

        参数: definitions冻结定义；domain已请求域；bounds来源到(start,end)；session会话。
        返回: HoldContext；未知end仍为None，后续查询决定是否能使用。
        异常: 非法上下文直接传播。
        """
        definitions = definitions or (self.a,)
        # 按声明来源分组，只保留固定数量的描述和完成事实。
        sources = tuple(dict.fromkeys(item.source for item in definitions))
        selected_bounds = bounds if bounds is not None else {source: domain for source in sources}
        descriptions = tuple(make_description(source, tuple(item for item in definitions if item.source == source),
                                              *selected_bounds[source]) for source in sources)
        completions = tuple(HistoryProgress(0, source, session, 0, None, True, selected_bounds[source][1])
                            for source in sources)
        return HoldContext(session, Interval(*domain), descriptions, completions)

    def owner(self, definitions=None, *, context=None, budget=None):
        """构造状态和查询owner并登记逆序关闭。

        参数: definitions冻结声明；context可选范围；budget可选共享账本。
        返回: (state,queries)，调用方可显式检查关闭后的账本。
        异常: 配置/预算错误传播。
        """
        definitions = definitions or (self.a,)
        # owner与状态共享同一RAM账本，测试不把结果放到统计之外。
        state = LatestSignalState(budget or ResourceBudget(32 * 1024 ** 2), definitions, 'session')
        self.addCleanup(state.close)
        queries = HoldQueries(state, context or self.context(definitions))
        self.addCleanup(queries.close)
        return state, queries

    def query_pair(self, queries, name, times, *, point=False):
        """用相同精确轴调用两个独立内核，登记结果清理。

        参数: queries当前owner；name别名；times整数tuple；point端点模式。
        返回: (reference_result,numpy_result)，不把一个结果喂给另一个。
        异常: 查询错误直接传播。
        """
        reference = queries.query_reference(name, times, point=point)
        self.addCleanup(reference.close)
        # 数组轴只使用int64，没有绝对时间转float。
        numpy_result = queries.query_numpy(name, np.array(times, dtype=np.int64), point=point)
        self.addCleanup(numpy_result.close)
        return reference, numpy_result

    def assert_pair(self, pair, expected, *, sample, dtype=D.FLOAT64, labels=()):
        """逐项比较手算逻辑事实与数组掩码，未知占位不作为正常数值。

        参数: pair两结果；expected=(time,value,valid,quality,actual,has_sample)行；sample原记录。
        返回: None。异常: dtype/值/纳秒/诊断或追溯错误触发断言。
        """
        reference, numpy_result = pair
        rows, arrays = reference.rows, numpy_result.arrays
        self.assertEqual(len(rows), len(expected))
        self.assertEqual(arrays.dtype, dtype)
        self.assertEqual(arrays.labels, labels)
        # 列形状和dtype单独核对，布尔/uint64不能因合并宽表被转float。
        physical_dtype = {D.FLOAT64: np.float64, D.INT64: np.int64, D.UINT64: np.uint64,
                          D.BOOL: np.bool_, D.ENUM: np.int64}[dtype]
        self.assertEqual(arrays.values.dtype, np.dtype(physical_dtype))
        self.assertEqual(arrays.time_ns.dtype, np.dtype(np.int64))
        self.assertEqual(arrays.valid.dtype, np.dtype(np.bool_))
        self.assertEqual(arrays.quality.dtype, np.dtype(np.uint16))
        self.assertEqual(arrays.actual_update.dtype, np.dtype(np.bool_))
        self.assertEqual(arrays.has_sample.dtype, np.dtype(np.bool_))
        for column in (arrays.time_ns, arrays.values, arrays.valid, arrays.quality,
                       arrays.actual_update, arrays.has_sample):
            self.assertEqual(column.shape, (len(expected),))
        for index, (time, value, valid, quality, actual, has_sample) in enumerate(expected):
            row = rows[index]
            self.assertEqual((row.time_ns, row.value, row.valid, row.quality, row.actual_update),
                             (time, value, valid, quality, actual))
            self.assertIs(row.sample, sample if has_sample else None)
            self.assertEqual((int(arrays.time_ns[index]), bool(arrays.valid[index]), Q(int(arrays.quality[index])),
                              bool(arrays.actual_update[index]), bool(arrays.has_sample[index])),
                             (time, valid, quality, actual, has_sample))
            # 无效物理占位不参与逻辑值断言；有效枚举按显式标签域解码。
            if valid:
                logical = arrays.labels[int(arrays.values[index])] if dtype is D.ENUM else arrays.values[index].item()
                self.assertEqual(logical, value)

    def test_real_source_history_both_backends_four_splits(self):
        """实际来源→历史→完整组→状态→两查询内核跨四切分有相同手算结果。

        参数: 无。返回: None。异常: 单位重复换算/同组冲突/1ns或切分状态错误断言失败。
        """
        start = 2 ** 53
        # valid_for=2ns，第一组在TTL前/到期各查一次；后续不跨未提交实际更新查询。
        current = replace(self.a, valid_for_ns=2, input_unit='mA', scale=.001,
                          same_time_policy='last_by_sequence')
        unsigned = SignalDefinition('unsigned', 'table', 'raw.u', D.UINT64, '1', 2)
        signed = SignalDefinition('signed', 'table', 'raw.i', D.INT64, '1', 2)
        enabled = SignalDefinition('enabled', 'table', 'raw.b', D.BOOL, '1', 2)
        mode = SignalDefinition('mode', 'table', 'raw.e', D.ENUM, '1', 2, choices=((1, 'scope'), (0, 'off')))
        definitions = (current, unsigned, signed, enabled, mode)
        rows = (MemoryRow(start, {'raw.a':1000, 'raw.u':2**64-1, 'raw.i':-(2**63), 'raw.b':True, 'raw.e':1}, 0),
                MemoryRow(start, {'raw.a':2000}, 1), MemoryRow(start+3, {'raw.a':None}, 2),
                MemoryRow(start+5, {'raw.a':3000, 'raw.e':0}, 3))
        source = SourceSpec('table', TimebaseSpec('clock', TimeType.RELATIVE, 'stream-hold-synthetic'), rows,
                            observation_start_ns=start, observation_end_ns=start+5)
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7, 65536):
                with self.subTest(backend=backend, size=size):
                    budget = ResourceBudget(32 * 1024 ** 2)
                    adapter = BudgetedMemorySourceAdapter(budget, source, 'session', definitions, backend=backend)
                    self.addCleanup(adapter.close)
                    request = ReadRequest('session', tuple(item.name for item in definitions), start, start+5, size)
                    description = adapter.describe()
                    history = DecodedHistoryStore(budget, self.work / f'{backend}-{size}', (description,), {'table':request})
                    self.addCleanup(history.close)
                    for batch in adapter.iter_batches(request):
                        history.append(batch)
                    adapter.close()
                    history.seal()
                    context = HoldContext('session', Interval(start,start+5), (description,),
                                          tuple(history.source_completions.values()))
                    state, queries = self.owner(definitions, context=context, budget=budget)
                    # 每组提交后仅查询下一真实更新之前的轴，不用最新状态回答历史。
                    for group in history.iter_groups():
                        state.apply(group)
                        if group.time_ns == start:
                            sample = state.get('a')
                            pair = self.query_pair(queries, 'a', (start,start+1,start+2))
                            self.assert_pair(pair, [(start,2.,True,Q.NONE,True,True),
                                                    (start+1,2.,True,Q.NONE,False,True),
                                                    (start+2,2.,False,Q.STALE,False,True)], sample=sample)
                            # 大整数/BOOL/ENUM分别保持声明列类型和精确原值。
                            for name, value, dtype, labels in (('unsigned',2**64-1,D.UINT64,()),
                                                               ('signed',-(2**63),D.INT64,()),
                                                               ('enabled',True,D.BOOL,()),
                                                               ('mode','scope',D.ENUM,('scope','off'))):
                                self.assert_pair(self.query_pair(queries,name,(start,)),
                                                 [(start,value,True,Q.NONE,True,True)],
                                                 sample=state.get(name),dtype=dtype,labels=labels)
                        elif group.time_ns == start+3:
                            self.assert_pair(self.query_pair(queries,'a',(start+3,start+4)),
                                             [(start+3,None,False,Q.MISSING,True,True),
                                              (start+4,None,False,Q.MISSING,False,True)], sample=state.get('a'))
                        else:
                            self.assert_pair(self.query_pair(queries,'a',(start+5,),point=True),
                                             [(start+5,3.,True,Q.NONE,True,True)],sample=state.get('a'))
                            self.assert_pair(self.query_pair(queries,'a',(start+5,)),
                                             [(start+5,None,False,Q.MISSING,False,False)],sample=state.get('a'))
                            self.assert_pair(self.query_pair(queries,'mode',(start+5,),point=True),
                                             [(start+5,'off',True,Q.NONE,True,True)],sample=state.get('mode'),
                                             dtype=D.ENUM,labels=('scope','off'))
                    # 明确释放完整链，不能用测试外部收集结果掩盖生产owner漏记预算。
                    queries.close()
                    state.close()
                    history.close()
                    self.assertEqual(budget.ram_bytes,0)

    def test_ttl_without_updates_and_new_sample_at_expiry(self):
        """纯计时到期不制造actual_update；恰好同刻新样本覆盖旧TTL。

        参数: 无。返回: None。异常: TTL右端包含/新值仍STALE或伪更新断言失败。
        """
        state, queries = self.owner()
        old = make_record(self.a,0,0,1)
        state.apply(DecodedTimeGroup(0,(old,)))
        self.assert_pair(self.query_pair(queries,'a',(0,2,3,4)),
                         [(0,1.,True,Q.NONE,True,True),(2,1.,True,Q.NONE,False,True),
                          (3,1.,False,Q.STALE,False,True),(4,1.,False,Q.STALE,False,True)],sample=old)
        # 新真实更新之后取新TTL，旧查询持有的样本不能被原地修改。
        new = make_record(self.a,3,1,2)
        state.apply(DecodedTimeGroup(3,(new,)))
        self.assert_pair(self.query_pair(queries,'a',(3,5,6)),
                         [(3,2.,True,Q.NONE,True,True),(5,2.,True,Q.NONE,False,True),
                          (6,2.,False,Q.STALE,False,True)],sample=new)

    def test_invalid_overwrite_combines_ttl_and_source_reasons(self):
        """无效新观测覆盖旧有效值，输入缺失与STALE/来源MISSING同时保留。

        参数: 无。返回: None。异常: 历史回退或覆盖已有质量位断言失败。
        """
        context = self.context(bounds={'table':(0,4)})
        state, queries = self.owner(context=context)
        state.apply(DecodedTimeGroup(0,(make_record(self.a,0,0,5),)))
        missing = make_record(self.a,1,1,None)
        state.apply(DecodedTimeGroup(1,(missing,)))
        self.assert_pair(self.query_pair(queries,'a',(1,3,4,5)),
                         [(1,None,False,Q.MISSING,True,True),(3,None,False,Q.MISSING,False,True),
                          (4,None,False,Q.MISSING|Q.STALE,False,True),
                          (5,None,False,Q.MISSING|Q.STALE,False,True)],sample=missing)

    def test_each_source_end_is_local_and_point_includes_end(self):
        """联合域较长不能延长提前结束来源；point包含来源末端但仍受TTL约束。

        参数: 无。返回: None。异常: 一源EOF让他源失效或末端连续仍有效断言失败。
        """
        a = replace(self.a,valid_for_ns=10)
        b = SignalDefinition('b','other','raw.b',D.FLOAT64,'A',10)
        definitions = (a,b)
        context = self.context(definitions,bounds={'table':(0,3),'other':(0,8)})
        state, queries = self.owner(definitions,context=context)
        first, second = make_record(a,1,0,2), make_record(b,1,0,4)
        state.apply(DecodedTimeGroup(1,(first,second)))
        self.assert_pair(self.query_pair(queries,'a',(2,3,4)),
                         [(2,2.,True,Q.NONE,False,True),(3,2.,False,Q.MISSING,False,True),
                          (4,2.,False,Q.MISSING,False,True)],sample=first)
        self.assert_pair(self.query_pair(queries,'a',(3,),point=True),
                         [(3,2.,True,Q.NONE,False,True)],sample=first)
        self.assert_pair(self.query_pair(queries,'b',(3,4)),
                         [(3,4.,True,Q.NONE,False,True),(4,4.,True,Q.NONE,False,True)],sample=second)

    def test_domain_outside_discards_sample_but_source_outside_keeps_diagnostics(self):
        """会话域外只返回MISSING且无样本；域内来源范围不足保留实际样本追溯。

        参数: 无。返回: None。异常: 域外泄露值或域内丢诊断断言失败。
        """
        # 只放宽TTL以隔离范围掩码，不改变源终点或补样本周期。
        definition = replace(self.a,valid_for_ns=10)
        state, queries = self.owner((definition,),context=self.context((definition,),domain=(2,6),bounds={'table':(0,4)}))
        sample = make_record(definition,0,0,7)
        state.apply(DecodedTimeGroup(0,(sample,)))
        self.assert_pair(self.query_pair(queries,'a',(0,1,2,4,6,7)),
                         [(0,None,False,Q.MISSING,False,False),(1,None,False,Q.MISSING,False,False),
                          (2,7.,True,Q.NONE,False,True),(4,7.,False,Q.MISSING,False,True),
                          (6,None,False,Q.MISSING,False,False),(7,None,False,Q.MISSING,False,False)],sample=sample)

    def test_unknown_source_start_is_preserved_and_sample_proves_hold(self):
        """未知源首端不补请求起点，已有真实样本仍能支持后续有限保持。

        参数: 无。返回: None。异常: 虚构首端/一律UNKNOWN/源结束后延长断言失败。
        """
        context = self.context(bounds={'table':(None,5)})
        state, queries = self.owner(context=context)
        sample = make_record(self.a,2,0,8)
        state.apply(DecodedTimeGroup(2,(sample,)))
        self.assertIsNone(context.descriptions[0].observation_start_ns)
        self.assert_pair(self.query_pair(queries,'a',(2,4,5)),
                         [(2,8.,True,Q.NONE,True,True),(4,8.,True,Q.NONE,False,True),
                          (5,8.,False,Q.STALE|Q.MISSING,False,True)],sample=sample)
        self.assertIsNone(context.descriptions[0].observation_start_ns)

    def test_empty_source_unknown_end_and_nonempty_unknown_end(self):
        """空源未知范围返回MISSING；非空样本遇未知EOF终点拒绝继续保持。

        参数: 无。返回: None。异常: None当0或请求终点/编造覆盖断言失败。
        """
        context = self.context(bounds={'table':(None,None)})
        state, queries = self.owner(context=context)
        self.assert_pair(self.query_pair(queries,'a',(0,2,10),point=True),
                         [(0,None,False,Q.MISSING,False,False),(2,None,False,Q.MISSING,False,False),
                          (10,None,False,Q.MISSING,False,False)],sample=None)
        state.apply(DecodedTimeGroup(0,(make_record(self.a,0,0,1),)))
        # 同一未知事实不能因出现样本自动升级为完整EOF范围。
        before = state.budget.ram_bytes
        for backend in ('reference','numpy'):
            with self.assertRaises(ValueError):
                if backend == 'reference':
                    queries.query_reference('a',(0,1))
                else:
                    queries.query_numpy('a',np.array([0,1],dtype=np.int64))
            self.assertEqual(state.budget.ram_bytes,before)

    def test_exact_large_time_and_signed_crossing_age(self):
        """绝对大坐标相邻1ns仍精确，前置样本与域内查询差超int64不能wrap。

        参数: 无。返回: None。异常: float轴精度损失或signed差回绕断言失败。
        """
        large = 2**53+1
        definition = replace(self.a,valid_for_ns=1)
        state, queries = self.owner((definition,),context=self.context((definition,),domain=(large,large+3)))
        sample = make_record(definition,large,0,1)
        state.apply(DecodedTimeGroup(large,(sample,)))
        self.assert_pair(self.query_pair(queries,'a',(large,large+1)),
                         [(large,1.,True,Q.NONE,True,True),(large+1,1.,False,Q.STALE,False,True)],sample=sample)
        # 域跨度只有2ns，但保留的前置样本到查询差可达2**64-1。
        maximum, minimum = 2**63-1, -(2**63)
        definition = replace(self.a,valid_for_ns=maximum)
        context = self.context((definition,),domain=(maximum-2,maximum),bounds={'table':(None,maximum)})
        state, queries = self.owner((definition,),context=context)
        sample = make_record(definition,minimum,0,9)
        state.apply(DecodedTimeGroup(minimum,(sample,)))
        self.assert_pair(self.query_pair(queries,'a',(maximum-2,maximum),point=True),
                         [(maximum-2,9.,False,Q.STALE,False,True),(maximum,9.,False,Q.STALE,False,True)],sample=sample)

    def test_next_expiry_is_future_bounded_and_exact(self):
        """下一TTL只在after之后且域/来源边界以内返回，越int64或无样本返回None。

        参数: 无。返回: None。异常: 返回已到期/越界/假deadline断言失败。
        """
        state, queries = self.owner(context=self.context(domain=(0,3)))
        self.assertIsNone(queries.next_expiry('a',0))
        state.apply(DecodedTimeGroup(0,(make_record(self.a,0,0,1),)))
        self.assertEqual(queries.next_expiry('a',2),3)
        self.assertIsNone(queries.next_expiry('a',3))
        self.assertIsNone(queries.next_expiry('a',4))
        # TTL在来源之后不能延长已结束来源。
        state, queries = self.owner(context=self.context(bounds={'table':(0,2)}))
        state.apply(DecodedTimeGroup(0,(make_record(self.a,0,0,1),)))
        self.assertIsNone(queries.next_expiry('a',0))
        maximum = 2**63-1
        context = self.context(domain=(maximum-2,maximum),bounds={'table':(None,maximum)})
        state, queries = self.owner(context=context)
        state.apply(DecodedTimeGroup(maximum-1,(make_record(self.a,maximum-1,0,1),)))
        self.assertIsNone(queries.next_expiry('a',maximum-1))

    def test_context_rejects_identity_eof_duplicates_and_mutation(self):
        """上下文校验身份/whole-source EOF/唯一来源/端点，不能由可变输入冒充。

        参数: 无。返回: None。异常: 错会话/缺来源/假EOF/矛盾范围被接受断言失败。
        """
        context = self.context()
        description, completion = context.descriptions[0], context.completions[0]
        malformed = (((description,description),(completion,)),
                     ((description,),(completion,completion)),
                     ((description,),()),
                     ((description,),(replace(completion,source='other'),)),
                     ((description,),(replace(completion,session_id='other'),)),
                     ((description,),(replace(completion,source_eof=False),)),
                     ((description,),(replace(completion,observed_end_ns=9),)))
        for descriptions, completions in malformed:
            with self.assertRaises((TypeError,ValueError)):
                HoldContext('session',Interval(0,10),descriptions,completions)
        with self.assertRaises((TypeError,ValueError)):
            HoldContext('session',Interval(0,10),[description],(completion,))
        with self.assertRaises((AttributeError,FrozenInstanceError)):
            context.domain = Interval(0,5)
        # Context校验不伪称seal；另一会话的状态必须在owner边界拒绝。
        state = LatestSignalState(ResourceBudget(32*1024**2),(self.a,),'other')
        self.addCleanup(state.close)
        before = state.budget.ram_bytes
        with self.assertRaises(ValueError):
            HoldQueries(state,context)
        self.assertEqual(state.budget.ram_bytes,before)

    def test_owner_binding_and_final_labels_failure_preserve_existing_state(self):
        """合法描述与当前字段/类型/单位/枚举域冲突或最后固定映射失败均抵销申请。

        参数: 无。返回: None。异常: 初始化漏账/覆盖现有样本或失败后不可恢复断言失败。
        """
        context = self.context()
        description, field = context.descriptions[0], context.descriptions[0].fields[0]
        # 描述本身合法但不属于当前绑定，必须在owner已申请后的契约检查拒绝。
        conflicting_fields = (replace(field,field=replace(field.field,field='raw.other')),
                              replace(field,unit='V'),replace(field,dtype=D.INT64))
        cases = [(self.a,context,replace(context,descriptions=(replace(description,fields=(bad,)),)))
                 for bad in conflicting_fields]
        mode = SignalDefinition('mode','table','raw.mode',D.ENUM,'1',3,choices=((0,'off'),(1,'scope')))
        enum_context = self.context((mode,))
        enum_description, enum_field = enum_context.descriptions[0], enum_context.descriptions[0].fields[0]
        wrong_domain = replace(enum_field,metadata={**enum_field.metadata,'labels':('foreign',)})
        cases.append((mode,enum_context,replace(enum_context,descriptions=(replace(enum_description,fields=(wrong_domain,)),))))
        for definition, valid_context, bad_context in cases:
            state = LatestSignalState(ResourceBudget(32*1024**2),(definition,),'session')
            self.addCleanup(state.close)
            sample = make_record(definition,0,0,0)
            state.apply(DecodedTimeGroup(0,(sample,)))
            before = (state.budget.ram_bytes,state.last_time_ns,state.conflict_count)
            with self.assertRaises(ValueError):
                HoldQueries(state,bad_context)
            self.assertEqual((state.budget.ram_bytes,state.last_time_ns,state.conflict_count),before)
            self.assertIs(state.get(definition.name),sample)
            self.assertFalse(state.closed)
            # 同一状态随后仍能创建正确owner，错误上下文不能污染绑定或全局标签域。
            queries = HoldQueries(state,valid_context)
            self.addCleanup(queries.close)
            result = queries.query_reference(definition.name,(0,))
            self.addCleanup(result.close)
            self.assertTrue(result.rows[0].valid)
            self.assertIs(result.rows[0].sample,sample)
            queries.close()
            state.close()
            self.assertEqual(state.budget.ram_bytes,0)
        # 第三次映射安装是最后固定labels；前两次及标签计算已完成后才失败。
        state = LatestSignalState(ResourceBudget(32*1024**2),(mode,),'session')
        self.addCleanup(state.close)
        sample = make_record(mode,0,0,0)
        state.apply(DecodedTimeGroup(0,(sample,)))
        before = (state.budget.ram_bytes,state.last_time_ns,state.conflict_count)
        proxy_calls = 0

        def fail_final_proxy(mapping):
            """前两次构造真实只读映射，第三次在最后labels安装之前注入分配失败。

            参数: mapping待冻结字典。返回: 前两次的真实MappingProxyType。
            异常: 第三次MemoryError为注入；其他真实结构错误直接传播。
            """
            nonlocal proxy_calls
            proxy_calls += 1
            if proxy_calls == 3:
                raise MemoryError('hold-owner-labels-test')
            return MappingProxyType(mapping)

        with patch('chronaxis.execution.hold.MappingProxyType',side_effect=fail_final_proxy):
            with self.assertRaises(MemoryError):
                HoldQueries(state,enum_context)
        self.assertEqual(proxy_calls,3)
        self.assertEqual((state.budget.ram_bytes,state.last_time_ns,state.conflict_count),before)
        self.assertIs(state.get('mode'),sample)
        self.assertFalse(state.closed)
        queries = HoldQueries(state,enum_context)
        self.addCleanup(queries.close)
        self.assert_pair(self.query_pair(queries,'mode',(0,2)),
                         [(0,'off',True,Q.NONE,True,True),(2,'off',True,Q.NONE,False,True)],
                         sample=sample,dtype=D.ENUM,labels=('off','scope'))
        queries.close()
        state.close()
        self.assertEqual(state.budget.ram_bytes,0)

    def test_axis_validation_empty_repeated_and_past_rejected(self):
        """允许空轴及重复精确查询，拒绝错误dtype/回退及早于最新组的查询。

        参数: 无。返回: None。异常: 时间cast/排序/使用未来样本回答过去断言失败。
        """
        state, queries = self.owner()
        sample = make_record(self.a,2,0,3)
        state.apply(DecodedTimeGroup(2,(sample,)))
        self.assert_pair(self.query_pair(queries,'a',()),[],sample=sample)
        self.assert_pair(self.query_pair(queries,'a',(2,2,3)),
                         [(2,3.,True,Q.NONE,True,True),(2,3.,True,Q.NONE,True,True),
                          (3,3.,True,Q.NONE,False,True)],sample=sample)
        before = state.budget.ram_bytes
        for times in ([2],(True,),(2.,),(3,2),(1,), (2**63,)):
            with self.assertRaises((TypeError,ValueError,OverflowError)):
                queries.query_reference('a',times)
            self.assertEqual(state.budget.ram_bytes,before)
        for times in (np.array([2.]),np.array([True]),np.array([[2]],dtype=np.int64),
                      np.array([3,2],dtype=np.int64),np.array([1],dtype=np.int64)):
            with self.assertRaises((TypeError,ValueError)):
                queries.query_numpy('a',times)
            self.assertEqual(state.budget.ram_bytes,before)
        with self.assertRaises((KeyError,ValueError)):
            queries.query_reference('missing',(2,))
        with self.assertRaises(TypeError):
            queries.query_reference('a',(2,),point=1)

    def test_numpy_columns_are_readonly_copies_of_input_axis(self):
        """NumPy结果独立只读，修改输入轴不改变已发布查询。

        参数: 无。返回: None。异常: 输入共享/公开可写掩码断言失败。
        """
        state, queries = self.owner()
        state.apply(DecodedTimeGroup(0,(make_record(self.a,0,0,1),)))
        axis = np.array([0,1,2],dtype=np.int64)
        result = queries.query_numpy('a',axis)
        self.addCleanup(result.close)
        axis[:] = 8
        arrays = result.arrays
        np.testing.assert_array_equal(arrays.time_ns,np.array([0,1,2],dtype=np.int64))
        for column in (arrays.time_ns,arrays.values,arrays.valid,arrays.quality,arrays.actual_update,arrays.has_sample):
            self.assertFalse(column.flags.writeable)
            with self.assertRaises(ValueError):
                column[0] = 0

    def test_large_enum_domain_is_shared_for_empty_queries(self):
        """空状态/空轴不重复创建巨大枚举域，两个结果复用owner内已计费冻结标签。

        参数: 无。返回: None。异常: 每查询重建域/截断标签或释放漏账断言失败。
        """
        # 2048标签放大固定域成本；没有观测不能把此成本藏在sample申请里。
        choices = tuple((index,f'label_{index}') for index in range(2048))
        definition = SignalDefinition('mode','table','raw.mode',D.ENUM,'1',3,choices=choices)
        state, queries = self.owner((definition,),budget=ResourceBudget(64*1024**2))
        first = queries.query_numpy('mode',np.array([],dtype=np.int64))
        second = queries.query_numpy('mode',np.array([],dtype=np.int64))
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        self.assertEqual(first.arrays.labels,tuple(label for _,label in choices))
        self.assertIs(first.arrays.labels,second.arrays.labels)
        self.assertEqual(first.arrays.values.shape,(0,))
        self.assertIsNone(first.sample)
        # 状态先关闭仍有owner/结果所有权，最终关闭释放全部新层申请。
        state.close()
        self.assertGreater(state.budget.ram_bytes,0)
        self.assertEqual(len(second.arrays.labels),2048)
        queries.close()
        self.assertEqual(state.budget.ram_bytes,0)

    def test_preallocation_budget_and_result_constructor_failure_are_atomic(self):
        """预算不足先拒绝构造；结果构造MemoryError抵销申请，不改样本或关闭owner。

        参数: 无。返回: None。异常: 构造前未检查/账本漏释放/状态变化断言失败。
        """
        state, queries = self.owner()
        sample = make_record(self.a,0,0,1)
        state.apply(DecodedTimeGroup(0,(sample,)))
        budget = state.budget
        # 保留1byte可用余额，大小非零查询应在结果构造前失败。
        blocker = budget.memory_budget_bytes-budget.ram_bytes-1
        budget.reserve_ram(blocker)
        before = budget.ram_bytes
        with patch('chronaxis.execution.hold.HoldResult') as constructor:
            with self.assertRaises(BudgetExceededError):
                queries.query_reference('a',(0,1))
            constructor.assert_not_called()
        self.assertEqual(budget.ram_bytes,before)
        budget.release_ram(blocker)
        before = budget.ram_bytes
        for backend in ('reference','numpy'):
            with patch('chronaxis.execution.hold.HoldResult',side_effect=MemoryError('hold-result-test')):
                with self.assertRaises(MemoryError):
                    if backend == 'reference':
                        queries.query_reference('a',(0,1))
                    else:
                        queries.query_numpy('a',np.array([0,1],dtype=np.int64))
            self.assertEqual(budget.ram_bytes,before)
            self.assertIs(state.get('a'),sample)
        # 故障之后仍可正常查询，失败不能偷偷进入closed状态。
        self.assert_pair(self.query_pair(queries,'a',(0,)),[(0,1.,True,Q.NONE,True,True)],sample=sample)

    def test_array_payload_and_result_registration_failures_release_reservations(self):
        """数组载荷构造及owner登记失败均释放申请，原状态和既有结果不受影响。

        参数: 无。返回: None。异常: 后段构造/登记漏账或丢已发布结果断言失败。
        """
        state, queries = self.owner()
        sample = make_record(self.a,0,0,1)
        state.apply(DecodedTimeGroup(0,(sample,)))
        existing = queries.query_reference('a',(0,))
        self.addCleanup(existing.close)
        axis = np.array([0,1],dtype=np.int64)
        before = state.budget.ram_bytes
        with patch('chronaxis.execution.hold._HeldArrays',side_effect=MemoryError('hold-payload-test')):
            with self.assertRaises(MemoryError):
                queries.query_numpy('a',axis)
        self.assertEqual(state.budget.ram_bytes,before)
        # 持有原集合内容作小型故障替身，add失败不能遗留新的结果。
        original_registry = queries._results
        for backend in ('reference','numpy'):
            failing_registry = RejectResultRegistry(original_registry)
            with patch.object(queries,'_results',failing_registry):
                with self.assertRaises(MemoryError):
                    if backend == 'reference':
                        queries.query_reference('a',(0,1))
                    else:
                        queries.query_numpy('a',axis)
                self.assertEqual(len(failing_registry),len(original_registry))
            self.assertEqual(state.budget.ram_bytes,before)
            self.assertIs(state.get('a'),sample)
            self.assertFalse(existing.closed)
            self.assertEqual(existing.rows[0].value,1.)

    def test_query_owns_old_csv_record_after_state_replace_and_close(self):
        """旧查询持有CSV定位成本，状态更新/关闭后结果仍可读，owner负责最终释放。

        参数: 无。返回: None。异常: 旧样本丢失/引用漏计/关闭重复释放断言失败。
        """
        state, queries = self.owner()
        reference = CSVSourceRef('session','table','raw.a','synthetic.csv',2,'0','1'*20000,False)
        old = make_record(self.a,0,0,1,reference)
        state.apply(DecodedTimeGroup(0,(old,)))
        baseline = state.budget.ram_bytes
        pair = self.query_pair(queries,'a',(0,1))
        # 两个结果均保守持有原样本成本，不能假设state会永远保留旧记录。
        self.assertGreaterEqual(state.budget.ram_bytes-baseline,2*estimate_record_bytes(old))
        state.apply(DecodedTimeGroup(2,(make_record(self.a,2,1,2),)))
        self.assert_pair(pair,[(0,1.,True,Q.NONE,True,True),(1,1.,True,Q.NONE,False,True)],sample=old)
        state.close()
        self.assertGreater(state.budget.ram_bytes,0)
        self.assertIs(pair[0].sample,old)
        self.assertIs(pair[1].sample,old)
        self.assertEqual(pair[0].definition,self.a)
        self.assert_pair(pair,[(0,1.,True,Q.NONE,True,True),(1,1.,True,Q.NONE,False,True)],sample=old)
        queries.close()
        queries.close()
        self.assertEqual(state.budget.ram_bytes,0)

    def test_close_releases_results_and_rejects_future_access(self):
        """result和owner关闭幂等，关闭后所有公开结果属性及新查询明确拒绝。

        参数: 无。返回: None。异常: 关闭后仍可读/活动结果漏关/账本非零断言失败。
        """
        state, queries = self.owner()
        state.apply(DecodedTimeGroup(0,(make_record(self.a,0,0,1),)))
        before = state.budget.ram_bytes
        reference, numpy_result = self.query_pair(queries,'a',(0,1))
        reference.close()
        reference.close()
        self.assertTrue(reference.closed)
        # 每个属性在closed边界先拒绝，不能因后端种类先抛别的错误。
        for name in ('rows','arrays','sample','definition'):
            with self.assertRaises(ResultClosedError):
                getattr(reference,name)
        self.assertGreater(state.budget.ram_bytes,before)
        queries.close()
        self.assertTrue(numpy_result.closed)
        for name in ('rows','arrays','sample','definition'):
            with self.assertRaises(ResultClosedError):
                getattr(numpy_result,name)
        with self.assertRaises(ResultClosedError):
            queries.query_reference('a',(0,))
        with self.assertRaises(ResultClosedError):
            queries.query_numpy('a',np.array([0],dtype=np.int64))
        with self.assertRaises(ResultClosedError):
            queries.next_expiry('a',0)
        state.close()
        self.assertEqual(state.budget.ram_bytes,0)
