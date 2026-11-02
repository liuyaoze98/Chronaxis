"""验证实际封存解码历史形成运行绑定，并由独立参考/NumPy表达式核计算。

输入是明确时钟、单位、转换与质量政策的合成memory/CSV；实际读取结果先写
work/m2-run-tests/decoded-bindings唯一历史目录，device_label为work，不改旧快照。
绑定须完整重放核对字节SHA、计数、EOF、投影及完整声明；静态声明不能直接执行。
小夹具收集历史仅作断言，运行工厂仍受预算约束；本节点不接保持轴或完整AnalysisRunner。
预期值由手算给出，两个被测数值核不互相生成真值或共用运算实现。
"""

from configuration_fixtures import current_fixture

# 冻结模型变体和局部故障仅用于新层，原路径不扫描或改写。
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import json
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.decoded_binding import DecodedBindings, DecodedSourceEvidence
from chronaxis.core.expression import compile_expression, validate_expression
from chronaxis.core.expression_reference import evaluate_reference, evaluate_memory_reference
from chronaxis.core.expression_numpy import evaluate_numpy, evaluate_memory_numpy
from chronaxis.core.models import Interval, MemoryRow, SourceSpec, TimebaseSpec
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.numeric_numpy import NumericArray, DTYPES
from chronaxis.core.temporal import TemporalRule
from chronaxis.core.temporal_memory_reference import require_memory_rule
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.execution.bindings import bind_decoded_history
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.history_records import HistorySample, HistoryProgress, decode_record, encode_record
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.results import AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest
from chronaxis.sources.csv_spec import SignalCSVSpec, CSVSourceRef


def column(values, definition):
    """只把已解码typed标量装箱成物理数组，不计算被测表达式。

    参数: values同声明ScalarValue tuple，允许空；definition提供dtype/枚举域。
    返回: NumericArray，valid/quality独立保存，无效占位不参与正常值判断。
    异常: 夹具列类型或模型错误直接传播。
    """
    labels = tuple(dict.fromkeys(label for _,label in definition.choices)) if definition.dtype is D.ENUM else ()
    physical = [labels.index(value.value) if labels and value.valid else value.value if value.valid else 0 for value in values]
    return NumericArray(definition.dtype,np.array(physical,dtype=DTYPES[definition.dtype]),
                        np.array([value.valid for value in values],dtype=np.bool_),
                        np.array([int(value.quality) for value in values],dtype=np.uint16),labels)


class CancelAfterOne:
    """在真实游标消费一行后取消，不自行清理，验证工厂必须关闭活动游标。"""

    def __init__(self, iterator):
        """保存真实历史游标及计数，初始仍有活跃句柄。

        参数: iterator实际历史游标。返回: 新故障游标。异常: 无。
        """
        self.iterator, self.count, self.closed = iterator, 0, False

    def __iter__(self):
        """返回当前游标。参数: 无。返回: self。异常: 无。"""
        return self

    def __next__(self):
        """首行真实读取，第二次模拟用户取消。

        参数: 无。返回: 首次HistoryRecord。异常: 后续KeyboardInterrupt为明确注入。
        """
        if self.count:
            raise KeyboardInterrupt('decoded-binding-cancel-test')
        self.count += 1
        return next(self.iterator)

    def close(self):
        """关闭底层实际句柄并记录工厂执行了清理。

        参数: 无。返回: None。异常: 底层关闭错误传播。
        """
        self.closed = True
        self.iterator.close()


class CloseAfterFinalProgress:
    """返回真实最终EOF进度后提前关闭，不执行底层文件末端完整性检查。"""

    def __init__(self,iterator):
        """保存仍打开的真实历史游标。

        参数: iterator实际文件游标。返回: 新提前关闭替身。异常: 无。
        """
        self.iterator,self.saw_final,self.closed=iterator,False,False

    def __iter__(self):
        """返回当前游标。参数: 无。返回: self。异常: 无。"""
        return self

    def __next__(self):
        """真实读取至最终进度后，下一次返回停止而不读取物理文件EOF。

        参数: 无。返回: 原HistoryRecord。异常: 最终进度之后StopIteration。
        """
        if self.saw_final:
            self.close()
            raise StopIteration
        record=next(self.iterator)
        self.saw_final=isinstance(record,HistoryProgress) and record.source_eof
        return record

    @property
    def verified_eof(self):
        """只转发底层真实EOF证明。参数: 无。返回: bool。异常: 无。"""
        return self.iterator.verified_eof

    @property
    def digest(self):
        """提供真实已读取字节摘要。参数: 无。返回: 摘要对象。异常: 无。"""
        return self.iterator.digest

    def close(self):
        """幂等关闭原游标，但不能提升verified_eof。

        参数: 无。返回: None。异常: 原关闭错误传播。
        """
        self.closed=True
        self.iterator.close()


class DecodedBindingTests(unittest.TestCase):
    """每项真实历史/账本/lease独立，模型拒绝与资源清理均有实际证据。"""

    def setUp(self):
        """建立唯一工作目录、五dtype声明和四个明确更新点。

        参数: 无。返回: None。异常: 目录/模型夹具错误直接失败。
        """
        self.work = Path(__file__).resolve().parents[2]/'work/m2-run-tests/decoded-bindings'/uuid4().hex
        self.work.mkdir(parents=True)
        self.clock = TimebaseSpec('clock',TimeType.RELATIVE,'decoded-binding-synthetic')
        self.domain = Interval(0,5)
        self.definitions = (SignalDefinition('current','table','raw.a',D.FLOAT64,'A',3,input_unit='mA',scale=.001),
                            SignalDefinition('unsigned','table','raw.u',D.UINT64,'1',3),
                            SignalDefinition('signed','table','raw.i',D.INT64,'1',3),
                            SignalDefinition('enabled','table','raw.b',D.BOOL,'1',3),
                            SignalDefinition('mode','table','raw.e',D.ENUM,'1',3,choices=((0,'off'),(1,'scope'))))
        self.rows = (MemoryRow(0,{'raw.a':1000,'raw.u':2**64-1,'raw.i':-(2**63),'raw.b':True,'raw.e':0},0),
                     MemoryRow(1,{'raw.a':None,'raw.b':False},1),
                     MemoryRow(2,{'raw.a':3000,'raw.b':True,'raw.e':1},2),
                     MemoryRow(3,{'raw.a':None,'raw.b':True},3))

    def declarations(self, definitions=None, *, session='session',domain=None,clock=None,input_identity='synthetic-memory'):
        """建立配置声明，不用虚拟内存行充当文件存在证明。

        参数: definitions/session/domain/clock显式变体；input_identity配置定位身份。
        返回: DeclarationBindings，仅声明关系。
        异常: 结构/单位/名称或同步模型错误直接传播。
        """
        clock = self.clock if clock is None else clock
        return DeclarationBindings(session,clock,domain or self.domain,(DeclaredSource('table',clock,input_identity),),
                                   self.definitions if definitions is None else definitions)

    def build(self, *, backend='numpy',size=2,rows=None,definitions=None,projected=None,kind='memory',
              description=None,seal=True,budget=None):
        """实际读取一个新来源并写历史，保留原描述和请求供绑定工厂核验。

        参数: backend/size选择归一化/切分；其余限定合成输入、投影、描述或seal。
        返回: (declarations,history,description,request)，adapter已关闭。
        异常: 真正输入/历史写入错误传播，不把夹具失败称作工厂拒绝。
        """
        budget = budget or ResourceBudget(64*1024**2)
        definitions = self.definitions if definitions is None else definitions
        rows = self.rows if rows is None else rows
        directory = self.work/uuid4().hex
        # memory缺字段表示未更新；CSV每列每行均有实际观测，两类事实分别验证。
        if kind == 'memory':
            source = SourceSpec('table',self.clock,rows,observation_start_ns=0 if rows else None,
                                observation_end_ns=4 if rows else None)
            adapter = BudgetedMemorySourceAdapter(budget,source,'session',definitions,backend=backend)
            declarations = self.declarations(definitions)
        else:
            directory.mkdir()
            csv_path = directory/'signals.csv'
            csv_path.write_text('ns,raw.a,raw.u,raw.i,raw.b,raw.e\n'
                                f'0,1000,{2**64-1},{-(2**63)},true,off\n'
                                '1,,1,-1,false,scope\n2,3000,2,-2,true,off\n3,,3,-3,true,scope\n',
                                encoding='utf-8',newline='')
            definitions = tuple(replace(item,choices=(('off','off'),('scope','scope'))) if item.dtype is D.ENUM else item
                                for item in definitions)
            spec = SignalCSVSpec('table',(csv_path,),self.clock,'ns','ns')
            adapter = BudgetedSignalCSVSourceAdapter(budget,spec,'session',definitions,backend=backend)
            declarations = self.declarations(definitions,input_identity=str(csv_path))
        self.addCleanup(adapter.close)
        names = tuple(item.name for item in definitions) if projected is None else projected
        request = ReadRequest('session',names,self.domain.start_ns,self.domain.end_ns,size)
        description = adapter.describe() if description is None else description
        history = DecodedHistoryStore(budget,directory/'history',(description,),{'table':request})
        self.addCleanup(history.close)
        for batch in adapter.iter_batches(request):
            history.append(batch)
        adapter.close()
        if seal:
            history.seal()
        return declarations,history,description,request

    def bind(self,declarations,history):
        """构造实际运行lease并登记关闭，不保存工厂临时游标。

        参数: declarations当前声明/history真实封存历史。返回: DecodedBindingLease。
        异常: 工厂实际验证错误传播。
        """
        lease = bind_decoded_history(declarations,history)
        self.addCleanup(lease.close)
        return lease

    def records(self,history):
        """完整读取小型历史作测试输入，必须消费到EOF使摘要检查实际执行。

        参数: history已封存小夹具。返回: tuple typed记录。
        异常: 实际历史读取/完整性错误传播。
        """
        return tuple(history.iter_records('table'))

    def assert_truth(self,bindings,records):
        """从原解码值装箱后独立求值，核对五dtype及三值诊断手算真值。

        参数: bindings真实运行绑定/records实际历史记录。返回: 独立结果事实摘要。
        异常: 任一后端值、质量、dtype或追溯错误触发断言。
        """
        samples = tuple(item for item in records if isinstance(item,HistorySample))
        first = {item.name:item.value for item in samples if item.time_ns==0}
        # 第一行精确整数/布尔/枚举不能在表达式context里隐式转float。
        for name,expected in (('current',1.),('unsigned',2**64-1),('signed',-(2**63)),('enabled',True),('mode','off')):
            compiled = compile_expression(name,bindings)
            scalar = evaluate_reference(compiled,{name:first[name]},bindings)
            array = evaluate_numpy(compiled,{name:column((first[name],),bindings.resolve(name))},bindings)
            self.assertEqual((scalar.value.value,scalar.value.valid,scalar.value.quality),(expected,True,Q.NONE))
            self.assertEqual(array.value.dtype,bindings.resolve(name).dtype)
            actual = array.value.labels[int(array.value.values[0])] if array.value.labels else array.value.values[0].item()
            self.assertEqual(actual,expected)
        # FALSE可遮蔽未知但不能丢依赖MISSING；UNKNOWN不是False。
        compiled = compile_expression('(current > 1) and enabled',bindings)
        scalar_results,values_by_name = [],{name:[] for name in compiled.dependencies}
        for time in (0,1,2,3):
            context = {item.name:item.value for item in samples if item.time_ns==time and item.name in compiled.dependencies}
            scalar_results.append(evaluate_reference(compiled,context,bindings))
            for name in compiled.dependencies:
                values_by_name[name].append(context[name])
        array = evaluate_numpy(compiled,{name:column(tuple(values),bindings.resolve(name))
                                        for name,values in values_by_name.items()},bindings)
        expected = [(False,True,Q.NONE,Q.NONE),(False,True,Q.NONE,Q.MISSING),
                    (True,True,Q.NONE,Q.NONE),(None,False,Q.MISSING,Q.MISSING)]
        facts = [(item.value.value if item.value.valid else None,item.value.valid,item.value.quality,item.dependency_quality)
                 for item in scalar_results]
        self.assertEqual(facts,expected)
        self.assertEqual(array.value.valid.tolist(),[True,True,True,False])
        self.assertEqual(array.value.quality.tolist(),[0,0,0,int(Q.MISSING)])
        self.assertEqual(array.dependency_quality.tolist(),[0,int(Q.MISSING),0,int(Q.MISSING)])
        self.assertEqual(array.value.values[:3].tolist(),[False,False,True])
        return facts

    def test_memory_both_backends_four_cuts_evidence_and_hand_truth(self):
        """真实memory两后端四切分实际绑定后五dtype及三值结果与手算一致。

        参数: 无。返回: None。异常: 假声明执行/切分丢状态/哈希计数或数值错误断言失败。
        """
        all_facts=[]
        for backend in ('reference','numpy'):
            for size in (1,2,7,65536):
                with self.subTest(backend=backend,size=size):
                    declarations,history,_,request=self.build(backend=backend,size=size)
                    records=self.records(history)
                    lease=self.bind(declarations,history)
                    bindings=lease.bindings
                    self.assertIsInstance(bindings,DecodedBindings)
                    evidence=bindings.sources[0]
                    self.assertIsInstance(evidence,DecodedSourceEvidence)
                    self.assertEqual((evidence.source,evidence.session_id,evidence.projected_aliases),
                                     ('table','session',request.signal_names))
                    self.assertEqual(evidence.sample_count,sum(isinstance(item,HistorySample) for item in records))
                    self.assertEqual(evidence.progress_count,sum(isinstance(item,HistoryProgress) for item in records))
                    self.assertEqual(evidence.history_sha256,sha256(history.paths['table'].read_bytes()).hexdigest())
                    self.assertTrue(evidence.source_eof)
                    self.assertEqual((evidence.observation_start_ns,evidence.observation_end_ns),(0,4))
                    self.assertRegex(evidence.description_sha256,'^[0-9a-f]{64}$')
                    self.assertRegex(evidence.request_sha256,'^[0-9a-f]{64}$')
                    self.assertNotEqual(bindings.identity,declarations.identity)
                    all_facts.append(self.assert_truth(bindings,records))
                    lease.close()
                    history.close()
                    self.assertEqual(history.budget.ram_bytes,0)
        # 历史字节身份可随batch分区变化；只要求实际数值事实切分不变。
        self.assertTrue(all(facts==all_facts[0] for facts in all_facts))

    def test_csv_both_backends_four_cuts_keep_actual_file_refs(self):
        """真实CSV不能伪造SourceSpec.rows，完整定位与手算表达式两后端均可执行。

        参数: 无。返回: None。异常: CSV身份/原定位丢失或重复换算断言失败。
        """
        for backend in ('reference','numpy'):
            for size in (1,2,7,65536):
                with self.subTest(backend=backend,size=size):
                    declarations,history,description,_=self.build(backend=backend,size=size,kind='csv')
                    records=self.records(history)
                    self.assertIsNone(description.observation_start_ns)
                    samples=[item for item in records if isinstance(item,HistorySample)]
                    self.assertEqual(len(samples),20)
                    self.assertTrue(all(isinstance(item.source_ref,CSVSourceRef) for item in samples))
                    lease=self.bind(declarations,history)
                    self.assertIsNone(lease.bindings.sources[0].observation_start_ns)
                    self.assertEqual(lease.bindings.sources[0].observation_end_ns,3)
                    self.assert_truth(lease.bindings,records)
                    lease.close()
                    history.close()
                    self.assertEqual(history.budget.ram_bytes,0)

    def test_actual_data_identity_isolated_and_exact_context_required(self):
        """同声明不同真实值形成不同绑定/编译身份，旧compiled不能套用新数据。

        参数: 无。返回: None。异常: 数据身份串用或缺列/多列被隐式补齐断言失败。
        """
        declarations,first,_,_=self.build(size=7)
        changed_rows=(replace(self.rows[0],values={**self.rows[0].values,'raw.a':2000}),*self.rows[1:])
        other_declarations,second,_,_=self.build(size=7,rows=changed_rows)
        self.assertEqual(declarations.identity,other_declarations.identity)
        left,right=self.bind(declarations,first),self.bind(other_declarations,second)
        self.assertNotEqual(left.bindings.identity,right.bindings.identity)
        compiled=compile_expression('current',left.bindings)
        self.assertNotEqual(compiled.identity,compile_expression('current',right.bindings).identity)
        scalar=ScalarValue(1.,D.FLOAT64)
        for context in ({},{'current':scalar,'extra':scalar}):
            with self.assertRaises(ValueError):
                evaluate_reference(compiled,context,left.bindings)
        with self.assertRaises(ValueError):
            evaluate_reference(compiled,{'current':scalar},right.bindings)
        with self.assertRaises(ValueError):
            evaluate_numpy(compiled,{'current':column((scalar,),self.definitions[0])},right.bindings)
        with self.assertRaises(TypeError):
            evaluate_reference(compiled,{'current':ScalarValue(1,D.INT64)},left.bindings)

    def test_full_normalization_identity_and_source_clock_changes_reject_reuse(self):
        """旧描述不能复用变化的转换/原码/质量政策/语义或来源时钟偏移声明。

        参数: 无。返回: None。异常: 只比labels/scale摘要而漏完整声明断言失败。
        """
        declarations,history,_,_=self.build()
        current,mode=self.definitions[0],self.definitions[-1]
        # 已知单位变体也必须先合法：A→A倍率1，mA→A反向倍率-.001与方向声明一致。
        changed_current=(replace(current,input_unit='A',scale=1),
                         replace(current,scale=-.001,direction_factor=-1,
                                 input_sign_convention='positive_sensor_direction',sign_convention='opposite_sensor_direction'),
                         replace(current,valid_range=(0.,10.)),replace(current,invalid_values=(999,)),
                         replace(current,valid_for_ns=4),replace(current,semantic_id='sensor.current'),
                         replace(current,field='different'))
        variants=[replace(declarations,signals=(definition,*self.definitions[1:])) for definition in changed_current]
        # 标签域顺序相同而原编码不同，先前旧metadata可相同，完整identity必须区分。
        variants.append(replace(declarations,signals=(*self.definitions[:-1],replace(mode,choices=((10,'off'),(11,'scope'))))))
        variants.extend((replace(declarations,session_id='other'),replace(declarations,domain=Interval(0,6)),
                         replace(declarations,sources=(replace(declarations.sources[0],offset_ns=1),)),
                         replace(declarations,sources=(replace(declarations.sources[0],timebase=replace(self.clock,origin='other-origin')),))))
        before=history.budget.ram_bytes
        for variant in variants:
            with self.subTest(identity=variant.identity),self.assertRaises(ValueError):
                bind_decoded_history(variant,history)
            self.assertEqual(history.budget.ram_bytes,before)
            self.assertFalse(history._iterators)

    def test_incomplete_or_inconsistent_description_fingerprints_rejected(self):
        """缺完整转换指纹或来源时钟/偏移描述不符，真实历史也不能升级为可执行绑定。

        参数: 无。返回: None。异常: 从旧metadata猜转换或忽略完整时钟身份断言失败。
        """
        _,baseline,description,_=self.build()
        fields=description.fields
        # 保留输出dtype/unit/labels但移除新完整指纹，刻画旧描述不足的事实。
        old_fields=tuple(replace(field,metadata={key:value for key,value in field.metadata.items()
                                                if key!='normalization_sha256'}) for field in fields)
        bad_clock_fields=tuple(replace(field,field=replace(field.field,locator={**field.field.locator,
                                  'source_timebase_sha256':'0'*64})) for field in fields)
        bad_offset_fields=tuple(replace(field,field=replace(field.field,locator={**field.field.locator,
                                   'offset_ns':1})) for field in fields)
        bad_descriptions=(replace(description,fields=old_fields),replace(description,fields=bad_clock_fields),
                          replace(description,fields=bad_offset_fields),replace(description,timebase_id='other_clock'))
        for bad_description in bad_descriptions:
            declarations,history,_,_=self.build(description=bad_description)
            before=history.budget.ram_bytes
            with self.assertRaises(ValueError):
                bind_decoded_history(declarations,history)
            self.assertEqual(history.budget.ram_bytes,before)
            self.assertFalse(history._iterators)
        baseline.close()

    def test_empty_source_and_empty_projection_are_truthful_and_dependencies_guarded(self):
        """空源/空投影仍有真实EOF，未读取依赖拒绝编译，已投影空数据可以表达UNKNOWN。

        参数: 无。返回: None。异常: 空源伪样本/未投影列被隐式视为已读断言失败。
        """
        declarations,history,_,_=self.build(rows=())
        lease=self.bind(declarations,history)
        evidence=lease.bindings.sources[0]
        self.assertEqual((evidence.sample_count,evidence.progress_count,evidence.source_eof),(0,1,True))
        self.assertIsNone(evidence.observation_start_ns)
        self.assertIsNone(evidence.observation_end_ns)
        compiled=compile_expression('current > 1',lease.bindings)
        missing=ScalarValue(None,D.FLOAT64,False,Q.MISSING)
        result=evaluate_reference(compiled,{'current':missing},lease.bindings)
        self.assertFalse(result.value.valid)
        self.assertEqual(result.value.quality,Q.MISSING)
        empty=evaluate_numpy(compiled,{'current':column((),self.definitions[0])},lease.bindings)
        self.assertEqual(empty.value.values.shape,(0,))
        # 空投影与空源不同：原数据确实存在，但没有任何信号列的读取证明。
        declarations,unprojected,_,_=self.build(projected=())
        lease=self.bind(declarations,unprojected)
        self.assertEqual(lease.bindings.sources[0].projected_aliases,())
        self.assertEqual(lease.bindings.sources[0].sample_count,0)
        self.assertEqual(lease.bindings.sources[0].observation_end_ns,4)
        with self.assertRaises(ValueError):
            compile_expression('current',lease.bindings)
        constant=compile_expression('1+2',lease.bindings)
        self.assertEqual(evaluate_reference(constant,{},lease.bindings).value.value,3)
        np.testing.assert_array_equal(evaluate_numpy(constant,{},lease.bindings,size=2).value.values,np.array([3,3],dtype=np.int64))
        self.assertEqual(evaluate_numpy(constant,{},lease.bindings,size=0).value.values.shape,(0,))
        # 部分投影只授权该列，即使描述列出其他合法字段也不能执行未读取依赖。
        declarations,partial,_,_=self.build(projected=('current',))
        lease=self.bind(declarations,partial)
        compile_expression('current',lease.bindings)
        with self.assertRaises(ValueError):
            compile_expression('enabled',lease.bindings)

    def test_empty_projection_still_requires_actual_source_clock_evidence(self):
        """空投影也不能借用同ID不同起点/偏移来源，字段全空时明确缺时基证据。

        参数: 无。返回: None。异常: 将未读列与未核对来源时钟混为一谈断言失败。
        """
        declarations,history,description,_=self.build(projected=())
        # 原观测范围属于整个来源；纯常量不授权替换其实际时钟声明。
        variants=(replace(declarations,sources=(replace(declarations.sources[0],offset_ns=1),)),
                  replace(declarations,sources=(replace(declarations.sources[0],timebase=replace(self.clock,origin='other-origin')),)))
        before=history.budget.ram_bytes
        for variant in variants:
            with self.subTest(identity=variant.identity),self.assertRaises(ValueError):
                # 若错误地成功返回也立即关闭，后续账本断言不被测试自己持有的lease干扰。
                self.bind(variant,history).close()
            self.assertEqual(history.budget.ram_bytes,before)
            self.assertFalse(history._iterators)
        # 现有SourceDescription没有独立自由元数据；没有字段定位就没有完整时基证明。
        declarations,without_fields,_,_=self.build(projected=(),description=replace(description,fields=()))
        before=without_fields.budget.ram_bytes
        with self.assertRaises(ValueError):
            self.bind(declarations,without_fields)
        self.assertEqual(without_fields.budget.ram_bytes,before)
        self.assertFalse(without_fields._iterators)

    def test_static_and_memory_convenience_cannot_execute_decoded_bindings(self):
        """执行编译拒绝声明，数值核拒绝静态树，memory快捷入口拒绝decoded含纯常量。

        参数: 无。返回: None。异常: 类型守卫放宽或decoded偷读虚构rows断言失败。
        """
        declarations,history,_,_=self.build()
        lease=self.bind(declarations,history)
        static=validate_expression('current',declarations)
        with self.assertRaises(TypeError):
            compile_expression('current',declarations)
        with self.assertRaises(TypeError):
            evaluate_reference(static,{'current':ScalarValue(1.,D.FLOAT64)},declarations)
        with self.assertRaises(TypeError):
            evaluate_numpy(static,{'current':column((ScalarValue(1.,D.FLOAT64),),self.definitions[0])},declarations)
        for text in ('current','1+2'):
            compiled=compile_expression(text,lease.bindings)
            with self.assertRaises(TypeError):
                evaluate_memory_reference(compiled,(0,))
            with self.assertRaises(TypeError):
                evaluate_memory_numpy(compiled,np.array([0],dtype=np.int64))
        # 时序memory入口共享的守卫也须显式拒绝decoded，而非访问不存在session抛AttributeError。
        compiled=compile_expression('enabled',lease.bindings)
        with self.assertRaises(TypeError):
            require_memory_rule(compiled,TemporalRule('rule','dataset','session','rising_edge'))

    def test_evidence_schema_identity_eof_and_frozen_model_guards(self):
        """轻量证据模型校验摘要/计数/EOF/投影归属，冻结对象不能被改写。

        参数: 无。返回: None。异常: 不合法证据或声明来源/会话被接受断言失败。
        """
        declarations,history,_,_=self.build()
        lease=self.bind(declarations,history)
        bindings,evidence=lease.bindings,lease.bindings.sources[0]
        bad_fields=({'history_sha256':'bad'},{'description_sha256':'g'*64},{'request_sha256':None},
                    {'sample_count':-1},{'sample_count':True},{'progress_count':0},{'source_eof':False},
                    {'projected_aliases':('current','current')},{'projected_aliases':['current']},
                    {'observation_start_ns':5,'observation_end_ns':4})
        for changes in bad_fields:
            with self.subTest(changes=changes),self.assertRaises((TypeError,ValueError)):
                replace(evidence,**changes)
        for sources in ((),(evidence,evidence),(replace(evidence,source='other'),),
                        (replace(evidence,session_id='other'),),(replace(evidence,projected_aliases=('unknown',)),)):
            with self.assertRaises((TypeError,ValueError)):
                DecodedBindings(declarations,sources)
        with self.assertRaises(TypeError):
            DecodedBindings(declarations,[evidence])
        with self.assertRaises((AttributeError,FrozenInstanceError)):
            bindings.sources=()
        with self.assertRaises((AttributeError,FrozenInstanceError)):
            evidence.sample_count=0
        with self.assertRaises(AttributeError):
            lease.bindings=bindings
        self.assertIs(lease.bindings,bindings)

    def test_unsealed_closed_and_wrong_source_history_rejected(self):
        """工厂只能绑定尚打开sealed历史，来源集合也不能按同名字段猜对应关系。

        参数: 无。返回: None。异常: 非sealed/closed或不同来源被升级断言失败。
        """
        declarations,history,_,_=self.build(seal=False)
        before=history.budget.ram_bytes
        with self.assertRaises(AnalysisError):
            bind_decoded_history(declarations,history)
        self.assertEqual(history.budget.ram_bytes,before)
        history.seal()
        different=replace(declarations,sources=(replace(declarations.sources[0],name='other'),),
                          signals=tuple(replace(item,source='other') for item in declarations.signals))
        with self.assertRaises(ValueError):
            bind_decoded_history(different,history)
        self.assertEqual(history.budget.ram_bytes,before)
        history.close()
        with self.assertRaises(ResultClosedError):
            bind_decoded_history(declarations,history)
        self.assertEqual(history.budget.ram_bytes,0)

    def test_history_tamper_truncation_schema_and_missing_eof_rejected(self):
        """工厂必须读到真实文件末端校验SHA/计数/EOF，合法值篡改也不能重用旧身份。

        参数: 无。返回: None。异常: 仅相信内存completion或提前结束重放断言失败。
        """
        for mutation in ('value','truncated','schema','missing_eof'):
            declarations,history,_,_=self.build(size=7)
            path=history.paths['table']
            payload=path.read_bytes()
            lines=payload.splitlines(keepends=True)
            if mutation=='value':
                original=decode_record(lines[0],history.max_line_bytes)
                changed=replace(original,array_value=9.,value=ScalarValue(9.,D.FLOAT64))
                lines[0]=encode_record(changed,history.max_line_bytes)
                changed_payload=b''.join(lines)
            elif mutation=='truncated':
                changed_payload=payload[:-1]
            elif mutation=='schema':
                packed=json.loads(lines[0])
                packed['history_version']=999
                lines[0]=(json.dumps(current_fixture(packed),separators=(',',':'),sort_keys=True)+'\n').encode('utf-8')
                changed_payload=b''.join(lines)
            else:
                changed_payload=b''.join(lines[:-1])
            path.write_bytes(changed_payload)
            before=history.budget.ram_bytes
            with self.subTest(mutation=mutation),self.assertRaises((ResultFormatError,AnalysisError,ValueError)):
                bind_decoded_history(declarations,history)
            self.assertEqual(history.budget.ram_bytes,before)
            self.assertFalse(history._iterators)
            history.close()
            self.assertEqual(history.budget.ram_bytes,0)

    def test_binding_lease_outlives_history_and_close_releases_owned_budget(self):
        """绑定没有借用历史句柄，history先关闭后lease仍可编译，最终释放自有预算。

        参数: 无。返回: None。异常: 借用关闭对象/句柄残留/重复释放断言失败。
        """
        declarations,history,_,_=self.build()
        lease=self.bind(declarations,history)
        bindings=lease.bindings
        self.assertFalse(history._iterators)
        history.close()
        self.assertGreater(history.budget.ram_bytes,0)
        compiled=compile_expression('1+2',lease.bindings)
        self.assertEqual(evaluate_reference(compiled,{},lease.bindings).value.value,3)
        self.assertIs(lease.bindings,bindings)
        lease.close()
        lease.close()
        self.assertTrue(lease.closed)
        with self.assertRaises(ResultClosedError):
            lease.bindings
        self.assertEqual(history.budget.ram_bytes,0)

    def test_final_progress_without_physical_verified_eof_is_rejected(self):
        """全部记录含最终EOF进度不足以证明文件完整，提前close不能生成运行绑定。

        参数: 无。返回: None。异常: 将closed或进度EOF误作实际末端验收断言失败。
        """
        declarations,history,_,_=self.build()
        original=history.iter_records
        wrappers=[]
        before=history.budget.ram_bytes

        def prematurely_closed_iterator(source):
            """建立真实游标并包最终progress后的提前关闭行为。

            参数: source真实来源名。返回: CloseAfterFinalProgress。
            异常: 原游标打开/构造错误传播。
            """
            wrapper=CloseAfterFinalProgress(original(source))
            wrappers.append(wrapper)
            return wrapper

        with patch.object(history,'iter_records',side_effect=prematurely_closed_iterator):
            with self.assertRaises(ResultFormatError):
                bind_decoded_history(declarations,history)
        self.assertEqual(len(wrappers),1)
        self.assertTrue(wrappers[0].saw_final)
        self.assertTrue(wrappers[0].closed)
        self.assertFalse(wrappers[0].verified_eof)
        self.assertFalse(history._iterators)
        self.assertEqual(history.budget.ram_bytes,before)
        # 用原完整游标恢复后同一历史可正常验证，失败不改原样本或文件。
        lease=self.bind(declarations,history)
        lease.close()
        history.close()
        self.assertEqual(history.budget.ram_bytes,0)

    def test_budget_precedes_replay_and_binding_lease_construction_failure(self):
        """预算不足先拒绝读历史，后段model/lease构造失败抵销申请且历史仍可使用。

        参数: 无。返回: None。异常: 分配前未检查/后段漏账/状态破坏断言失败。
        """
        declarations,history,_,_=self.build()
        budget=history.budget
        blocker=budget.memory_budget_bytes-budget.ram_bytes-1
        budget.reserve_ram(blocker)
        before=budget.ram_bytes
        with patch.object(history,'iter_records') as replay:
            with self.assertRaises(BudgetExceededError):
                bind_decoded_history(declarations,history)
            replay.assert_not_called()
        self.assertEqual(budget.ram_bytes,before)
        budget.release_ram(blocker)
        before=budget.ram_bytes
        for target in ('DecodedBindings','DecodedBindingLease'):
            with patch('chronaxis.execution.bindings.'+target,side_effect=MemoryError('decoded-bind-construction-test')):
                with self.assertRaises(MemoryError):
                    bind_decoded_history(declarations,history)
            self.assertEqual(budget.ram_bytes,before)
            self.assertFalse(history._iterators)
            self.assertEqual(history.state,'sealed')
        lease=self.bind(declarations,history)
        self.assert_truth(lease.bindings,self.records(history))
        lease.close()
        history.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_cancel_during_actual_replay_closes_file_and_preserves_history(self):
        """真实游标读首行后取消，工厂关闭句柄并释放申请，不覆盖历史或吞取消。

        参数: 无。返回: None。异常: KeyboardInterrupt被包装/资源漏释放断言失败。
        """
        declarations,history,_,_=self.build()
        original=history.iter_records
        wrappers=[]
        before=history.budget.ram_bytes

        def cancelling_iterator(source):
            """创建真实文件游标，再包一个不会自动关闭的取消测试对象。

            参数: source当前来源名。返回: CancelAfterOne。
            异常: 原游标打开错误直接传播。
            """
            wrapper=CancelAfterOne(original(source))
            wrappers.append(wrapper)
            return wrapper

        with patch.object(history,'iter_records',side_effect=cancelling_iterator):
            with self.assertRaises(KeyboardInterrupt):
                bind_decoded_history(declarations,history)
        self.assertEqual(len(wrappers),1)
        self.assertTrue(wrappers[0].closed)
        self.assertTrue(wrappers[0].iterator.handle.closed)
        self.assertFalse(history._iterators)
        self.assertEqual(history.budget.ram_bytes,before)
        self.assertEqual(history.state,'sealed')
        lease=self.bind(declarations,history)
        lease.close()
        history.close()
        self.assertEqual(history.budget.ram_bytes,0)
