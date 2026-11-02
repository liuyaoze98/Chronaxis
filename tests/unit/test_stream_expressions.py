"""验证实际解码绑定的保持查询接两独立表达式核，及表达式结果的预算所有权。

输入为明确来源时钟/单位/有效期的合成memory和CSV，实际写入新工作目录历史；
封存后经运行绑定工厂、完整组状态、两个保持内核和两个数值核输出typed结果。
手算事实分别核对正常值、UNKNOWN与依赖诊断，不以被测后端互生成预期。
测试仅写work/m2-run-tests/stream-expressions唯一目录，实际设备来源由对应验证记录注明；
不改RefProjects，不把查询通过解释为事件deadline、窗口指标或公共AnalysisRunner已完成。
"""

# 唯一工作目录、小夹具收集及局部故障均只作用于新分析层。
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import DerivedDefinition, compile_expression, validate_expression
from chronaxis.core.models import Interval, MemoryRow, SourceSpec, TimebaseSpec, SourceRef
from chronaxis.core.numeric import normalize_reference
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.execution.bindings import bind_decoded_history
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.expressions import ExpressionQueries
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.history_records import HistorySample, estimate_record_bytes
from chronaxis.execution.hold import HoldContext, HoldQueries
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.state import LatestSignalState
from chronaxis.results import BudgetExceededError, ResultClosedError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest, SignalBatch
from chronaxis.sources.csv_spec import SignalCSVSpec, CSVSourceRef


def sample(definition,time_ns,sequence,raw,reference=None):
    """建立已经归一化的坏状态/生命周期夹具，不替代表达式真值核。

    参数: definition当前声明；time_ns/sequence原时间与序号；raw原值；reference可选定位。
    返回: HistorySample，原诊断与物理占位分开。
    异常: 夹具模型错误直接传播。
    """
    # 归一化结果保留valid和quality；无效值的0/False仅用于定宽物理存储，
    # 后续求值必须读取掩码，不能把占位解释为已知零或已知False。
    value=normalize_reference(definition,raw)
    # 有效ENUM以完整标签域中的整数位置存储，逻辑业务值仍保留在value中。
    physical=(value.labels.index(value.value) if definition.dtype is D.ENUM else value.value) if value.valid else (
        0. if definition.dtype is D.FLOAT64 else False if definition.dtype is D.BOOL else 0)
    # 记录同时带原始输入和来源定位，便于区分转换后的值、物理占位与原诊断。
    return HistorySample(0,definition.name,time_ns,sequence,physical,value,definition.unit,
                         reference or SourceRef('session',definition.source,definition.field),True,raw)


class RejectRegistry(set):
    """在表达式结果已构造但尚未登记时注入分配失败，不保存半成品。"""

    def add(self,result):
        """拒绝集合安装。参数: result新结果。返回: 无。异常: MemoryError为明确注入。"""
        # 故障发生在结果完成之后，登记函数必须处理尚未交给owner管理的对象。
        raise MemoryError('expression-registry-test')


class RejectAppend(list):
    """模拟临时保持结果列表无法继续增长，让登记方负责关闭新句柄。"""

    def append(self,result):
        """拒绝新保持结果的追加。

        参数: result已经申请预算的HoldResult。返回: 无。
        异常: MemoryError为显式分配故障；不修改列表或关闭传入结果。
        """
        # 新结果是否关闭由被测登记函数决定，注入器不能替它完成资源收尾。
        raise MemoryError('expression-held-list-test')


class StreamExpressionTests(unittest.TestCase):
    """每项真实来源与新账本独立，caller资源和表达式owner分别清理。"""

    def setUp(self):
        """建立大整数坐标、五种声明和唯一新工作目录。

        参数: 无。返回: None。异常: 工作目录/声明错误直接失败。
        """
        # 每例使用独立目录，真实CSV和历史暂存均写入新项目work，避免夹具互相覆盖。
        self.work=Path(__file__).resolve().parents[2]/'work/m2-run-tests/stream-expressions'/uuid4().hex
        self.work.mkdir(parents=True)
        # 2**53+1不能由float64精确表示；相邻1ns查询要求时间始终保持整数纳秒。
        self.start=2**53+1
        self.clock=TimebaseSpec('clock',TimeType.RELATIVE,'expression-stream-synthetic')
        # 五种类型分别验证mA→A、uint64最大值、int64最小值、BOOL和ENUM域。
        # 每列valid_for均为2ns：start和start+1有效，达到start+2即因TTL等号失效。
        self.definitions=(SignalDefinition('current','table','raw.a',D.FLOAT64,'A',2,input_unit='mA',scale=.001),
                          SignalDefinition('unsigned','table','raw.u',D.UINT64,'1',2),
                          SignalDefinition('signed','table','raw.i',D.INT64,'1',2),
                          SignalDefinition('enabled','table','raw.b',D.BOOL,'1',2),
                          SignalDefinition('mode','table','raw.e',D.ENUM,'1',2,choices=((0,'off'),(1,'scope'))))
        # 首组建立完整有效状态；3ns后的缺失更新必须覆盖旧电流；4ns后新值恢复有效。
        # UINT64/INT64端点只在首组出现，不能因类型转换或后续批次缺列丢失其精度。
        self.rows=(MemoryRow(self.start,{'raw.a':1000,'raw.u':2**64-1,'raw.i':-(2**63),'raw.b':True,'raw.e':0},0),
                   MemoryRow(self.start+3,{'raw.a':None,'raw.b':False},1),
                   MemoryRow(self.start+4,{'raw.a':3000,'raw.b':True,'raw.e':1},2))

    def prepare(self,texts=('current',),*,backend='numpy',size=2,kind='memory',definitions=None,rows=None,
                derived=(),empty_progress=False,budget=None):
        """建立完整实际链，编译只使用工厂生成绑定，保留组供测试逐次提交。

        参数: texts注册表达式；backend/size/kind真实来源模式；其余为显式合成变体。
        返回: SimpleNamespace各层资源及冻结compiled/groups，生产实现不收集全组。
        异常: 实际读取/封存/绑定/编译错误传播。
        """
        # 调用方可显式替换声明、原始行和预算；普通小夹具使用64MiB统一新账本。
        # 所有层共享该账本，各层创建成功后立即登记清理，异常时按逆序释放各自资源。
        definitions=self.definitions if definitions is None else definitions
        rows=self.rows if rows is None else rows
        budget=budget or ResourceBudget(64*1024**2)
        directory=self.work/uuid4().hex
        # memory使用明确观测范围；CSV真实读写同一组关键值，末端范围由来源协议报告。
        if kind=='memory':
            source=SourceSpec('table',self.clock,rows,observation_start_ns=self.start if rows else None,
                              observation_end_ns=self.start+6 if rows else None)
            adapter=BudgetedMemorySourceAdapter(budget,source,'session',definitions,backend=backend)
        else:
            # 原始CSV保留整数端点和空电流单元格，不能先替它归一化或补零。
            directory.mkdir()
            path=directory/'signals.csv'
            path.write_text('ns,raw.a,raw.u,raw.i,raw.b,raw.e\n'
                            f'{self.start},1000,{2**64-1},{-(2**63)},true,off\n'
                            f'{self.start+3},,1,-1,false,scope\n{self.start+4},3000,2,-2,true,scope\n',
                            encoding='utf-8',newline='')
            # CSV枚举原值为文本，显式替换该来源的choices键，其他声明和单位政策不变。
            definitions=tuple(replace(item,choices=(('off','off'),('scope','scope'))) if item.dtype is D.ENUM else item
                              for item in definitions)
            adapter=BudgetedSignalCSVSourceAdapter(budget,SignalCSVSpec('table',(path,),self.clock,'ns','ns'),
                                                  'session',definitions,backend=backend)
        self.addCleanup(adapter.close)
        # 先建立静态声明和精确读取请求；description提供实际来源定位和观测证据。
        # 此处声明仍不能执行，必须读至EOF并封存历史后才能取得实际运行绑定。
        domain=Interval(self.start,self.start+6)
        declarations=DeclarationBindings('session',self.clock,domain,(DeclaredSource('table',self.clock,'stream-synthetic'),),
                                         definitions,derived_names=tuple(item.name for item in derived))
        request=ReadRequest('session',tuple(item.name for item in definitions),domain.start_ns,domain.end_ns,size)
        description=adapter.describe()
        history=DecodedHistoryStore(budget,directory/'history',(description,),{'table':request})
        self.addCleanup(history.close)
        if empty_progress:
            # 合法空非EOF批次不产生实际更新，也不能改变表达式值或边沿证据。
            history.append(SignalBatch('table','session',{},None,False,None))
        # 完整消费真实适配器批次并记录EOF；关闭读句柄后封存，禁止继续追加历史。
        for batch in adapter.iter_batches(request):
            history.append(batch)
        adapter.close()
        history.seal()
        # 实际绑定lease独立持有历史证据和完整转换身份，编译不得借用静态声明执行。
        lease=bind_decoded_history(declarations,history)
        self.addCleanup(lease.close)
        # state初始为空，测试稍后按完整同刻组提交；holds借用state并核对实际来源完成信息。
        # 两者各自拥有固定成本，表达式查询关闭时不能代替调用方关闭它们。
        state=LatestSignalState(budget,definitions,'session')
        self.addCleanup(state.close)
        holds=HoldQueries(state,HoldContext('session',domain,(description,),tuple(history.source_completions.values())))
        self.addCleanup(holds.close)
        # 编译并登记同一实际绑定的对象；queries只拥有自身固定申请和返回的表达式结果。
        compiled=tuple(compile_expression(text,lease.bindings,derived=derived) for text in texts)
        queries=ExpressionQueries(holds,lease.bindings,compiled)
        self.addCleanup(queries.close)
        # 仅小型测试物化，实际生产仍逐完整组消费并有独立历史预算。
        groups=tuple(history.iter_groups())
        # 各测试显式获得层级资源和原组，用独立手算预期验证逐组提交后的查询结果。
        return SimpleNamespace(budget=budget,history=history,lease=lease,state=state,holds=holds,compiled=compiled,
                               queries=queries,groups=groups,declarations=declarations,definitions=definitions,domain=domain)

    def close_fixture(self,fixture):
        """明确按所有权关闭完整链并核对RAM归零。

        参数: fixture本测试各层资源。返回: None。异常: 关闭失败或漏账断言失败。
        """
        # 先释放表达式快照，再依次关闭调用方保持、状态、绑定和历史；重复清理须幂等。
        fixture.queries.close()
        fixture.holds.close()
        fixture.state.close()
        fixture.lease.close()
        fixture.history.close()
        self.assertEqual(fixture.budget.ram_bytes,0)

    def pair(self,fixture,index,times,*,point=False):
        """用相同精确轴调用两保持/数值查询，结果清理独立登记。

        参数: fixture链；index已登记compiled序号；times整数tuple；point端点模式。
        返回: (reference_result,numpy_result)。异常: 实际查询错误传播。
        """
        # 两后端使用同一登记对象与整数轴，各结果分别登记关闭，避免由另一后端代为释放。
        compiled=fixture.compiled[index]
        reference=fixture.queries.query_reference(compiled,times,point=point)
        self.addCleanup(reference.close)
        numpy_result=fixture.queries.query_numpy(compiled,np.array(times,dtype=np.int64),point=point)
        self.addCleanup(numpy_result.close)
        return reference,numpy_result

    def assert_facts(self,pair,times,expected,actual,*,dtype,samples=()):
        """独立手算结果核对逻辑值、结果质量、依赖诊断、真实更新和原样本。

        参数: pair两结果；times轴；expected=(value,valid,quality,dependency_quality)；actual实际更新。
        返回: None。异常: 数值/掩码/身份或来源追溯错误断言失败。
        """
        # 先核对两结果各自与预期的轴、真实更新和原样本，防止数值相同掩盖来源丢失。
        reference,numpy_result=pair
        self.assertEqual(tuple(reference.times_ns),times)
        np.testing.assert_array_equal(numpy_result.times_ns,np.array(times,dtype=np.int64))
        self.assertEqual(tuple(reference.actual_update),tuple(actual))
        self.assertEqual(numpy_result.actual_update.tolist(),list(actual))
        self.assertEqual(reference.samples,samples)
        self.assertEqual(numpy_result.samples,samples)
        self.assertEqual(reference.binding_identity,numpy_result.binding_identity)
        self.assertEqual(reference.compiled_identity,numpy_result.compiled_identity)
        # 再核对长度与声明类型，数组后端不能通过广播或隐式升型凑出相同数值。
        self.assertEqual(len(reference.rows),len(expected))
        self.assertEqual(numpy_result.arrays.value.dtype,dtype)
        for index,(value,valid,quality,diagnostic) in enumerate(expected):
            # UNKNOWN按逻辑无值None比较，并分别检查valid、结果质量和全部依赖诊断；
            # 无效行的物理占位可以是0/False，断言不能误把该占位当作可用业务值。
            row=reference.rows[index]
            self.assertEqual((row.value.value if row.value.valid else None,row.value.valid,row.value.quality,row.dependency_quality),
                             (value,valid,quality,diagnostic))
            arrays=numpy_result.arrays
            self.assertEqual((bool(arrays.value.valid[index]),Q(int(arrays.value.quality[index])),Q(int(arrays.dependency_quality[index]))),
                             (valid,quality,diagnostic))
            if valid:
                # 有效ENUM数组存的是域内整数编码，须还原标签后与独立手算业务值比较；
                # 其余类型用item保留Python整数/布尔语义，不把uint64端点转为float。
                logical=arrays.value.labels[int(arrays.value.values[index])] if arrays.value.labels else arrays.value.values[index].item()
                self.assertEqual(logical,value)

    def test_real_memory_csv_backends_splits_and_empty_progress(self):
        """实际memory/CSV两归一化后端三切分，空进度不改变保持/三值诊断与更新。

        参数: 无。返回: None。异常: 切分重置/TTL等号/UNKNOWN当False或诊断丢失断言失败。
        """
        # 覆盖两种真实来源、两种归一化后端和三种切分，空进度不能新增样本或重置状态。
        for kind in ('memory','csv'):
            for backend in ('reference','numpy'):
                for size in (1,2,7):
                    with self.subTest(kind=kind,backend=backend,size=size):
                        # 1000mA转换为1A，1>1为False；enabled=True，所以首刻及1ns后均为False。
                        # 2ns恰好达到valid_for，两依赖都STALE，UNKNOWN and UNKNOWN仍为UNKNOWN。
                        fixture=self.prepare(('(current > 1) and enabled',),kind=kind,backend=backend,size=size,empty_progress=True)
                        fixture.state.apply(fixture.groups[0])
                        compiled=fixture.compiled[0]
                        held=tuple(fixture.state.get(name) for name in compiled.dependencies)
                        times=(self.start,self.start+1,self.start+2)
                        self.assert_facts(self.pair(fixture,0,times),times,
                                          [(False,True,Q.NONE,Q.NONE),(False,True,Q.NONE,Q.NONE),
                                           (None,False,Q.STALE,Q.STALE)],[True,False,False],dtype=D.BOOL,samples=held)
                        # 3ns更新的电流缺失为UNKNOWN，enabled=False；FALSE AND UNKNOWN可决断为False，
                        # 结果quality为NONE，但dependency_quality仍须保留原电流的MISSING。
                        fixture.state.apply(fixture.groups[1])
                        held=tuple(fixture.state.get(name) for name in compiled.dependencies)
                        self.assert_facts(self.pair(fixture,0,(self.start+3,)),(self.start+3,),
                                          [(False,True,Q.NONE,Q.MISSING)],[True],dtype=D.BOOL,samples=held)
                        # 4ns新电流为3A且enabled=True，结果为True；真实末点使用point模式允许取值。
                        fixture.state.apply(fixture.groups[2])
                        held=tuple(fixture.state.get(name) for name in compiled.dependencies)
                        self.assert_facts(self.pair(fixture,0,(self.start+4,),point=True),(self.start+4,),
                                          [(True,True,Q.NONE,Q.NONE)],[True],dtype=D.BOOL,samples=held)
                        self.close_fixture(fixture)

    def test_five_dtypes_exact_large_values_and_one_ns_axis(self):
        """五种dtype查询保持定宽精确值，大坐标相邻1ns没有float转换。

        参数: 无。返回: None。异常: uint/有符号端点/BOOL/枚举被提升或轴丢精度断言失败。
        """
        # 首组每列独立查询；手算值直接来自原始端点、明确缩放和枚举域，不借另一后端生成。
        fixture=self.prepare(tuple(item.name for item in self.definitions))
        fixture.state.apply(fixture.groups[0])
        for index,(value,dtype) in enumerate(((1.,D.FLOAT64),(2**64-1,D.UINT64),(-(2**63),D.INT64),(True,D.BOOL),('off',D.ENUM))):
            held=(fixture.state.get(fixture.compiled[index].dependencies[0]),)
            times=(self.start,self.start+1)
            self.assert_facts(self.pair(fixture,index,times),times,
                              [(value,True,Q.NONE,Q.NONE)]*2,[True,False],dtype=dtype,samples=held)
        self.close_fixture(fixture)

    def test_budget_is_reserved_before_hold_and_numeric_computation(self):
        """超预算在保持和数值调用前失败，两后端均不安装结果或改变状态。

        参数: 无。返回: None。异常: 申请前执行保持/数值或预算残留断言失败。
        """
        # 已提交的状态和固定成本不变；测试占位使账本仅余1字节，无法容纳任何新查询。
        fixture=self.prepare()
        fixture.state.apply(fixture.groups[0])
        budget=fixture.budget
        blocker=budget.memory_budget_bytes-budget.ram_bytes-1
        budget.reserve_ram(blocker)
        before=budget.ram_bytes
        axis=np.array([self.start],dtype=np.int64)
        # 两后端必须先拒绝预算再返回：保持查询和数值核均替换为可检查的探针，
        # assert_not_called证明没有提前取得样本、分配保持结果或开始计算。
        for backend in ('reference','numpy'):
            with patch.object(fixture.holds,'query_'+backend) as hold,patch('chronaxis.execution.expressions.evaluate_'+backend) as numeric:
                with self.assertRaises(BudgetExceededError):
                    if backend=='reference':
                        fixture.queries.query_reference(fixture.compiled[0],(self.start,))
                    else:
                        fixture.queries.query_numpy(fixture.compiled[0],axis)
                hold.assert_not_called()
                numeric.assert_not_called()
            self.assertEqual(budget.ram_bytes,before)
        # 失败后RAM仍为原账本；只释放测试自身占位，再按各层所有权检查最终归零。
        budget.release_ram(blocker)
        self.close_fixture(fixture)

    def test_complex_tree_reserves_more_query_space_than_simple_tree(self):
        """相同依赖/轴下复杂树比简单树申请更多空间，不能只按最终列nbytes计账。

        参数: 无。返回: None。异常: 节点缓存/中间列被移出预算断言失败。
        """
        # 两树只依赖同一current，使用完全相同的8点整数轴；差别仅是复杂树增加四个加法。
        # 最终数组形状一致，所以仅查看最终nbytes不能证明中间节点已纳入计账。
        fixture=self.prepare(('current','(((current+1)+2)+3)+4'))
        fixture.state.apply(fixture.groups[0])
        totals=[]
        times=tuple(self.start for _ in range(8))
        for compiled in fixture.compiled:
            # 保留真实reserve行为，同时累加本次全部申请，包括查询缓存和临时保持；
            # 此数值是申请总量，不冒充同时存活RAM或进程峰值。
            with patch.object(fixture.budget,'reserve_ram',wraps=fixture.budget.reserve_ram) as reservations:
                result=fixture.queries.query_numpy(compiled,np.array(times,dtype=np.int64))
                self.addCleanup(result.close)
                totals.append(sum(call.args[0] for call in reservations.call_args_list))
            # 每次比较前关闭前一结果，避免其存活状态影响下一树的可用容量。
            result.close()
        # 静态节点更多时总申请必须增长，不能把所有查询都简化成仅最终一列的成本。
        self.assertGreater(totals[1],totals[0])
        self.close_fixture(fixture)

    def test_kernel_result_constructor_and_registration_failures_release_all(self):
        """计算/结果构造/owner登记故障与取消关闭临时保持，抵销本次预算并保留状态。

        参数: 无。返回: None。异常: 保持句柄/查询申请漏释放或取消被吞断言失败。
        """
        # 先保存真实current样本对象及账本；各注入失败都只能撤销本次查询，不能重置原状态。
        fixture=self.prepare()
        fixture.state.apply(fixture.groups[0])
        original=fixture.state.get('current')
        before=fixture.budget.ram_bytes
        # 两后端分别在数值核、结果构造处注入MemoryError，再在数值核注入KeyboardInterrupt。
        # 取消不是普通Exception，仍须原样传播并执行临时保持的finally关闭。
        for backend in ('reference','numpy'):
            for target,error in (('evaluate_'+backend,MemoryError('expression-kernel-test')),
                                 ('ExpressionResult',MemoryError('expression-result-test')),
                                 ('evaluate_'+backend,KeyboardInterrupt('expression-cancel-test'))):
                with patch('chronaxis.execution.expressions.'+target,side_effect=error):
                    with self.assertRaises(type(error)):
                        if backend=='reference':
                            fixture.queries.query_reference(fixture.compiled[0],(self.start,))
                        else:
                            fixture.queries.query_numpy(fixture.compiled[0],np.array([self.start],dtype=np.int64))
                # 逐次比较原账本、保持登记集合及原样本身份，识别漏账、漏句柄或状态被替换。
                self.assertEqual(fixture.budget.ram_bytes,before)
                self.assertFalse(fixture.holds._results)
                self.assertIs(fixture.state.get('current'),original)
            # 结果已构造后的owner集合登记也可能分配失败；此阶段同样不得留住临时保持或申请。
            original_registry=fixture.queries._results
            with patch.object(fixture.queries,'_results',RejectRegistry(original_registry)):
                with self.assertRaises(MemoryError):
                    if backend=='reference':
                        fixture.queries.query_reference(fixture.compiled[0],(self.start,))
                    else:
                        fixture.queries.query_numpy(fixture.compiled[0],np.array([self.start],dtype=np.int64))
            self.assertEqual(fixture.budget.ram_bytes,before)
            self.assertFalse(fixture.holds._results)
        # 所有故障移除后，两真实查询仍应得到1000mA转换后的1A及原样本，确认状态可继续使用。
        self.assert_facts(self.pair(fixture,0,(self.start,)),(self.start,),[(1.,True,Q.NONE,Q.NONE)],
                          [True],dtype=D.FLOAT64,samples=(original,))
        self.close_fixture(fixture)

    def test_old_csv_samples_keep_independent_budget_after_state_update(self):
        """表达式结果独立持有原CSV样本/定位，更新或state关闭后仍能读取旧结果。

        参数: 无。返回: None。异常: 旧结果引用变成新值/定位丢失或引用漏计断言失败。
        """
        # 两查询各自持有首刻CSV原样本，新增RAM至少覆盖两份完整原记录引用成本。
        # 此处只核对成本下界，不要求实际数组和缓存恰好等于该下界。
        fixture=self.prepare(kind='csv')
        fixture.state.apply(fixture.groups[0])
        original=fixture.state.get('current')
        self.assertIsInstance(original.source_ref,CSVSourceRef)
        before=fixture.budget.ram_bytes
        pair=self.pair(fixture,0,(self.start,))
        self.assertGreaterEqual(fixture.budget.ram_bytes-before,2*estimate_record_bytes(original))
        # 提交缺失组及新3A组后关闭state；旧查询必须仍持有独立的首刻1A和原CSV定位。
        fixture.state.apply(fixture.groups[1])
        fixture.state.apply(fixture.groups[2])
        fixture.state.close()
        # caller关闭状态后旧快照仍可读，但两个后端都不能再借该状态产生新结果。
        after_close=fixture.budget.ram_bytes
        with self.assertRaises(ResultClosedError):
            fixture.queries.query_reference(fixture.compiled[0],(self.start+4,))
        with self.assertRaises(ResultClosedError):
            fixture.queries.query_numpy(fixture.compiled[0],np.array([self.start+4],dtype=np.int64))
        self.assertEqual(fixture.budget.ram_bytes,after_close)
        # 原始单元格文本1000和旧逻辑1A均保持，不能借用更新后的3000或已关闭的state。
        self.assert_facts(pair,(self.start,),[(1.,True,Q.NONE,Q.NONE)],[True],dtype=D.FLOAT64,samples=(original,))
        self.assertEqual(pair[0].samples[0].source_ref.value_text,'1000')
        self.assertFalse(pair[0].closed)
        self.close_fixture(fixture)

    def test_partial_owner_construction_releases_only_new_fixed_reservations(self):
        """owner构造中的超限、分配故障和取消抵销新申请，不关闭已有查询快照。

        参数: 无。返回: None。
        异常: 固定申请漏账、错误关闭caller或已有结果被关闭时断言失败。
        先把剩余容量限定为同一登记树固定成本减1字节，确保在已有多次申请后失败；
        再在完整元数据遍历后注入分配故障和取消，验证构造异常的统一收尾。
        """
        # 既有owner和两后端结果必须持续可用，失败构造只拥有本次新增申请。
        fixture=self.prepare()
        fixture.state.apply(fixture.groups[0])
        original=fixture.state.get('current')
        pair=self.pair(fixture,0,(self.start,))
        before=fixture.budget.ram_bytes
        registered=set(fixture.queries._results)
        # 将可用容量限定为同一登记树固定成本少1字节；占位属于测试，必须与产品申请分开释放。
        remaining=fixture.queries._fixed_cost-1
        blocker=fixture.budget.memory_budget_bytes-before-remaining
        fixture.budget.reserve_ram(blocker)
        limited=fixture.budget.ram_bytes
        try:
            # 允许初始化前几次固定申请，最后因总容量少1字节拒绝并恢复原账本。
            with patch.object(fixture.budget,'reserve_ram',wraps=fixture.budget.reserve_ram) as reservations:
                with self.assertRaises(BudgetExceededError):
                    ExpressionQueries(fixture.holds,fixture.lease.bindings,fixture.compiled)
            self.assertGreater(reservations.call_count,2)
            self.assertEqual(fixture.budget.ram_bytes,limited)
        finally:
            # 即使断言失败也释放测试占位，防止把注入器自身的成本混作产品漏账。
            fixture.budget.release_ram(blocker)
        # 解除容量限制后，分别模拟遍历结束的分配故障及取消，覆盖超限以外的构造失败路径。
        for error in (MemoryError('expression-owner-test'),KeyboardInterrupt('expression-owner-cancel-test')):
            with self.subTest(error=type(error).__name__):
                # 此时完整metadata已申请；后续字典分配失败或取消应抵销全部新固定成本。
                with patch.object(ExpressionQueries,'_check_contract',side_effect=error):
                    with self.assertRaises(type(error)):
                        ExpressionQueries(fixture.holds,fixture.lease.bindings,fixture.compiled)
                self.assertEqual(fixture.budget.ram_bytes,before)
                self.assertEqual(fixture.queries._results,registered)
                self.assertIs(fixture.state.get('current'),original)
                self.assertFalse(fixture.holds.closed)
        # 旧结果的手算真值为1000mA转换后的1A，失败构造不能影响其值或来源样本。
        self.assert_facts(pair,(self.start,),[(1.,True,Q.NONE,Q.NONE)],[True],
                          dtype=D.FLOAT64,samples=(original,))
        self.close_fixture(fixture)

    def test_second_hold_list_allocation_failure_closes_new_and_previous_handles(self):
        """第二依赖登记失败时关闭新句柄和已登记句柄，两后端原状态和预算不变。

        参数: 无。返回: None。
        异常: 首个临时结果或未登记的新结果漏关闭、异常被吞或状态改变时断言失败。
        两个依赖分别是真实current和enabled，故障发生在保持结果已构造且已有前一结果时。
        """
        # 两列都已经提交；当前值1A大于1为False，与True相与的手算结果为False。
        fixture=self.prepare(('(current > 1) and enabled',))
        fixture.state.apply(fixture.groups[0])
        compiled=fixture.compiled[0]
        originals=tuple(fixture.state.get(name) for name in compiled.dependencies)
        before=fixture.budget.ram_bytes
        register_hold=fixture.queries._keep_hold

        def reject_second(held,result):
            """首个保持结果正常安装，第二个交给拒绝增长的列表。

            参数: held本次已登记列表；result新HoldResult。返回: None。
            异常: 第二次由RejectAppend抛MemoryError，真实_keep_hold负责关闭新结果。
            """
            # 注入点只替换第二次追加的容器，仍执行真实登记函数的异常收尾。
            if held:
                register_hold(RejectAppend(),result)
            else:
                register_hold(held,result)

        # 两后端独立执行同一第二次追加故障，不能以一个后端的清理结果代替另一个。
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend):
                with patch.object(fixture.queries,'_keep_hold',side_effect=reject_second) as registration:
                    with self.assertRaisesRegex(MemoryError,'expression-held-list-test'):
                        if backend=='reference':
                            fixture.queries.query_reference(compiled,(self.start,))
                        else:
                            fixture.queries.query_numpy(compiled,np.array([self.start],dtype=np.int64))
                # 第二次追加确实已被尝试，两临时句柄均已关闭且没有半成品结果。
                self.assertEqual(registration.call_count,2)
                self.assertEqual(fixture.budget.ram_bytes,before)
                self.assertFalse(fixture.holds._results)
                self.assertFalse(fixture.queries._results)
                for name,original in zip(compiled.dependencies,originals):
                    self.assertIs(fixture.state.get(name),original)
        # 移除故障后真实查询仍返回手算False，说明本次失败没有损坏后续可用状态。
        self.assert_facts(self.pair(fixture,0,(self.start,)),(self.start,),
                          [(False,True,Q.NONE,Q.NONE)],[True],dtype=D.BOOL,samples=originals)
        self.close_fixture(fixture)

    def test_large_enum_domain_empty_axis_is_fixed_budgeted(self):
        """巨大枚举域在无当前样本/空轴时仍完整且有固定申请，关闭全部层后归零。

        参数: 无。返回: None。异常: 标签截断/空轴不计域空间/错误样本证据断言失败。
        """
        # 2048个标签同时被历史、绑定、当前状态、保持和表达式owner持有。
        # 本夹具固定申请实测约73MiB，两空轴结果同时存活约166MiB；显式256MiB
        # 容纳完整域及查询临时量，其他夹具仍用64MiB，不修改产品计账上界。
        choices=tuple((index,f'label_{index}') for index in range(2048))
        definition=SignalDefinition('mode','table','raw.e',D.ENUM,'1',2,choices=choices)
        fixture=self.prepare(('mode',),definitions=(definition,),budget=ResourceBudget(256*1024**2))
        # 空轴没有样本或物理数值，却仍须保存全部标签并由owner负责释放预算。
        pair=self.pair(fixture,0,())
        self.assertEqual(pair[0].rows,())
        self.assertEqual(pair[1].arrays.value.labels,tuple(label for _,label in choices))
        self.assertEqual(pair[1].arrays.value.values.shape,(0,))
        self.assertEqual(pair[1].samples,())
        self.assertGreater(fixture.budget.ram_bytes,0)
        self.close_fixture(fixture)

    def test_owner_close_releases_only_owned_results_and_rejects_access(self):
        """表达式owner关闭自有结果，caller保持/状态/历史/lease仍可用且由各自关闭。

        参数: 无。返回: None。异常: 越权关闭caller或结果属性仍可读断言失败。
        """
        # 先重复关闭reference结果，随后重复关闭owner；幂等收尾还须关闭仍存活的NumPy结果。
        fixture=self.prepare()
        fixture.state.apply(fixture.groups[0])
        reference,numpy_result=self.pair(fixture,0,(self.start,))
        reference.close()
        reference.close()
        self.assertTrue(reference.closed)
        fixture.queries.close()
        fixture.queries.close()
        self.assertTrue(numpy_result.closed)
        # 关闭后所有读取属性和新查询都必须拒绝，避免借由残存字段访问已经释放计账的数据。
        for result in (reference,numpy_result):
            for name in ('times_ns','rows','arrays','actual_update','samples','binding_identity','compiled_identity'):
                with self.assertRaises(ResultClosedError):
                    getattr(result,name)
        with self.assertRaises(ResultClosedError):
            fixture.queries.query_reference(fixture.compiled[0],(self.start,))
        # caller保持、状态、历史和lease不属于表达式owner；它们仍开放且可产生有效保持结果。
        self.assertFalse(fixture.holds.closed)
        self.assertFalse(fixture.state.closed)
        self.assertFalse(fixture.history.closed)
        self.assertFalse(fixture.lease.closed)
        held=fixture.holds.query_reference('current',(self.start,))
        self.addCleanup(held.close)
        self.assertTrue(held.rows[0].valid)
        # caller资源最后由测试各自关闭，检查释放范围正确且全链RAM归零。
        held.close()
        self.close_fixture(fixture)

    def test_invalid_overwrite_unknown_and_known_true_diagnostics(self):
        """无效更新不回退旧值；TRUE or UNKNOWN可决断且保留缺失诊断。

        参数: 无。返回: None。异常: 缺失被填0/当False或决断丢诊断断言失败。
        """
        # 把3ns处的enabled改为True，同时保留电流缺失；缺失更新必须覆盖原1A，不能回退旧值。
        rows=(self.rows[0],replace(self.rows[1],values={'raw.a':None,'raw.b':True}),self.rows[2])
        fixture=self.prepare(('current > 1','(current > 1) or enabled'),rows=rows)
        # 首组后提交缺失组：单独比较是UNKNOWN，TRUE OR UNKNOWN可决断为True。
        # OR结果本身有效且quality为NONE，但两个表达式都保留依赖电流的MISSING诊断。
        fixture.state.apply(fixture.groups[0])
        fixture.state.apply(fixture.groups[1])
        for index,expected in ((0,(None,False,Q.MISSING,Q.MISSING)),(1,(True,True,Q.NONE,Q.MISSING))):
            compiled=fixture.compiled[index]
            held=tuple(fixture.state.get(name) for name in compiled.dependencies)
            self.assert_facts(self.pair(fixture,index,(self.start+3,)),(self.start+3,),
                              [expected],[True],dtype=D.BOOL,samples=held)
        self.close_fixture(fixture)

    def test_source_eof_point_and_domain_masks_do_not_extend_hold(self):
        """真实来源末点仅point可用，域外缺失不保留旧TTL或伪造更新。

        参数: 无。返回: None。异常: 来源/域末端闭合为持续保持或丢actual更新断言失败。
        """
        # 完整提交真实CSV三组后，最后观测时间为start+4ns，当前电流为3000mA即3A。
        # 来源EOF限定连续保持的右开端点，不能因2ns TTL尚未到期而把它延至start+6。
        fixture=self.prepare(kind='csv')
        for group in fixture.groups:
            fixture.state.apply(group)
        held=(fixture.state.get('current'),)
        time=self.start+4
        # 真实末点的point查询包含观测终点，值为3A且actual_update=True。
        self.assert_facts(self.pair(fixture,0,(time,),point=True),(time,),
                          [(3.,True,Q.NONE,Q.NONE)],[True],dtype=D.FLOAT64,samples=held)
        # 同刻连续查询位于来源半开区间外，为MISSING；但该时刻确实更新，actual_update仍为True。
        self.assert_facts(self.pair(fixture,0,(time,)),(time,),
                          [(None,False,Q.MISSING,Q.MISSING)],[True],dtype=D.FLOAT64,samples=held)
        # domain为[start,start+6)，终点及其后1ns均为MISSING，且没有在这两刻发生真实更新。
        # 域外缺失优先于TTL，不得把STALE或旧值当作仍在观测范围内的结果。
        end=self.start+6
        self.assert_facts(self.pair(fixture,0,(end,end+1)),(end,end+1),
                          [(None,False,Q.MISSING,Q.MISSING)]*2,[False,False],dtype=D.FLOAT64,samples=held)
        self.close_fixture(fixture)

    def test_constants_empty_axis_and_no_dependency_updates(self):
        """常量与空轴有明确结果长度，不能凭纯计算制造真实更新。

        参数: 无。返回: None。异常: 无依赖猜样本/空轴shape或结果dtype错误断言失败。
        """
        # 空来源不提供任何样本；两纯常量分别手算为INT64的3和BOOL的True，无需猜依赖。
        fixture=self.prepare(('1+2','True'),rows=())
        for index,dtype in ((0,D.INT64),(1,D.BOOL)):
            # 空轴的行数、更新掩码和样本均为空，但结果类型仍必须正确。
            pair=self.pair(fixture,index,())
            self.assert_facts(pair,(),[],[],dtype=dtype)
            # 非空轴每点都返回同一常量；纯计算没有实际信号更新，actual_update始终False。
            value=3 if index==0 else True
            times=(self.start,self.start+1)
            self.assert_facts(self.pair(fixture,index,times),times,
                              [(value,True,Q.NONE,Q.NONE)]*2,[False,False],dtype=dtype)
        self.close_fixture(fixture)

    def test_only_registered_compiled_and_same_binding_can_be_queried(self):
        """静态树、未登记表达式与另一实际绑定的compiled都拒绝执行且不申请残留。

        参数: 无。返回: None。异常: 名称/文本相同绕过登记和实际输入身份断言失败。
        """
        # 三种非法输入分别是同绑定未登记的新表达式、仅验证的静态树、同名而实际数据不同的绑定。
        # 修改原电流为2000mA会改变运行证据身份，不能凭表达式文本current继承旧绑定。
        fixture=self.prepare()
        fixture.state.apply(fixture.groups[0])
        unregistered=compile_expression('current+1',fixture.lease.bindings)
        static=validate_expression('current',fixture.declarations)
        other=self.prepare(rows=(replace(self.rows[0],values={**self.rows[0].values,'raw.a':2000}),*self.rows[1:]))
        before=fixture.budget.ram_bytes
        # 两后端均拒绝这些对象，每次失败后的账本必须保持原值。
        for compiled in (unregistered,static,other.compiled[0]):
            with self.assertRaises((TypeError,ValueError)):
                fixture.queries.query_reference(compiled,(self.start,))
            with self.assertRaises((TypeError,ValueError)):
                fixture.queries.query_numpy(compiled,np.array([self.start],dtype=np.int64))
            self.assertEqual(fixture.budget.ram_bytes,before)
        # owner构造也须拒绝静态声明及另一实际绑定，构造期间申请的固定成本不能残留。
        with self.assertRaises((TypeError,ValueError)):
            ExpressionQueries(fixture.holds,fixture.declarations,fixture.compiled)
        with self.assertRaises(ValueError):
            ExpressionQueries(fixture.holds,other.lease.bindings,fixture.compiled)
        self.assertEqual(fixture.budget.ram_bytes,before)
        self.close_fixture(other)
        self.close_fixture(fixture)

    def test_shared_derived_nodes_keep_hand_value_and_original_dependencies(self):
        """派生公共子树复用不改变手算结果，samples仅保留展开后原依赖。

        参数: 无。返回: None。异常: 派生重复换算或作为虚构原样本断言失败。
        """
        # current先从1000mA转换为1A，twice为2A，twice+twice手算为4A；共享子树不重复缩放。
        # 展开的原始依赖只有current，派生名称twice不能变成虚构HistorySample。
        derived=(DerivedDefinition('twice','current*2','A'),)
        fixture=self.prepare(('twice+twice',),derived=derived)
        fixture.state.apply(fixture.groups[0])
        self.assertEqual(fixture.compiled[0].dependencies,('current',))
        # 相邻1ns都在TTL内，值为4A；仅首刻存在真实更新，两后端保留同一个原始current样本。
        times=(self.start,self.start+1)
        self.assert_facts(self.pair(fixture,0,times),times,[(4.,True,Q.NONE,Q.NONE)]*2,
                          [True,False],dtype=D.FLOAT64,samples=(fixture.state.get('current'),))
        self.close_fixture(fixture)

    def test_axis_validation_repeated_exact_times_and_readonly_arrays(self):
        """允许重复精确轴，拒绝回溯/错误dtype；输出轴/数值/更新均独立只读。

        参数: 无。返回: None。异常: 偷排序/cast或输入共享及可写结果断言失败。
        """
        # 保存查询前账本，所有轴拒绝路径都必须抵销本次申请，不能修改已提交的状态。
        fixture=self.prepare()
        fixture.state.apply(fixture.groups[0])
        compiled=fixture.compiled[0]
        before=fixture.budget.ram_bytes
        # 参考轴拒绝list、bool、float、回退顺序及早于当前state的时间，不能偷偷转换或排序。
        for times in ([self.start],(True,),(float(self.start),),(self.start+1,self.start),(self.start-1,)):
            with self.assertRaises((TypeError,ValueError)):
                fixture.queries.query_reference(compiled,times)
            self.assertEqual(fixture.budget.ram_bytes,before)
        # 数组轴必须是一维int64且非递减；浮点、二维和回退输入都在结果安装前失败。
        for axis in (np.array([self.start],dtype=float),np.array([[self.start]],dtype=np.int64),
                     np.array([self.start+1,self.start],dtype=np.int64)):
            with self.assertRaises((TypeError,ValueError)):
                fixture.queries.query_numpy(compiled,axis)
            self.assertEqual(fixture.budget.ram_bytes,before)
        # 重复同刻合法；结果须复制精确轴，调用方后来改动输入不得改变已返回的时间快照。
        axis=np.array([self.start,self.start,self.start+1],dtype=np.int64)
        result=fixture.queries.query_numpy(compiled,axis)
        self.addCleanup(result.close)
        axis[:]=self.start+5
        np.testing.assert_array_equal(result.times_ns,np.array([self.start,self.start,self.start+1],dtype=np.int64))
        # 时间、实际更新、物理值、有效掩码及两种质量列均只读，防止绕过预算快照的不可变契约。
        for values in (result.times_ns,result.actual_update,result.arrays.value.values,result.arrays.value.valid,
                       result.arrays.value.quality,result.arrays.dependency_quality):
            self.assertFalse(values.flags.writeable)
            with self.assertRaises(ValueError):
                values[0]=0
        self.close_fixture(fixture)
