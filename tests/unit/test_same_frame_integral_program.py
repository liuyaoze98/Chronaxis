"""独立验证同帧浮点程序、资源释放、超宽序号及错误顺序。

仅构造有界内存消息，使用原参考核和手算面积核对结果，不读写外部报文。
预算与弱引用检查覆盖正常关闭、构造失败及中途失败；测试清理释放所有自有owner。
"""
import dataclasses
import gc
import random
import unittest
import weakref
from unittest.mock import patch
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.expression import validate_expression, DerivedDefinition, ExprNode
from chronaxis.core.expression_reference import _evaluate
from chronaxis.core.models import Interval, TimebaseSpec, SourceRef
from chronaxis.core.numeric import normalize_reference
from chronaxis.core.scalar import _scalar_from_validated_fields
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.execution.record_integral import RecordIntegral
from chronaxis.execution import same_frame_integrals as module
from chronaxis.execution.history import _metadata_bytes
from chronaxis.legacy.records import LegacyCANField, field_to_dict
from chronaxis.legacy.updates import LegacyDecodedUpdate
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError


class FloatProgramTests(unittest.TestCase):
    """用原标量核和手算面积分别检查新增实现，不依赖附件测试。"""

    def owners(self, text='x*y', *, age=65_000_000, size=2, depth=0):
        """参数: text为公式，age为纳秒有效期，size为批容量，depth为共享派生树层数。

        返回: 同帧owner、积分器、预算及定义。异常: 模型、预算与数值构造错误。"""
        fields=tuple(LegacyCANField(0,n,256) for n in ('X','Y'))
        definitions=tuple(SignalDefinition(n,'bus',f.key,D.FLOAT64,'1',age)
                          for n,f in zip(('x','y'),fields))
        clock=TimebaseSpec('clock',TimeType.RELATIVE,'origin')
        names=tuple('d'+str(n) for n in range(depth))
        derived=tuple(DerivedDefinition(name,'x+x' if n==0 else names[n-1]+'+'+names[n-1]) for n,name in enumerate(names))
        binding=DeclarationBindings('session',clock,Interval(0,10**9),
                                    (DeclaredSource('bus',clock,'synthetic'),),definitions,names)
        expression=validate_expression(names[-1] if names else text,binding,derived=derived)
        facts=tuple(dict(locator=field_to_dict(f),dbc_frames=((False,False),)) for f in fields)
        same=module.same_frame_binding(definitions,facts)
        budget=ResourceBudget()
        integral=RecordIntegral(budget,CalculationDefinition('area','integral',Interval(20_000_000,250_000_000)),
                                expression.root.unit,expression.root.dtype,None,backend='reference',batch_intervals=size)
        self.addCleanup(integral.close)
        owner=module.SameFrameIntegrals(budget,definitions,(expression,),(integral,),same,'session',lambda:None,derived=derived)
        self.addCleanup(owner.close)
        return owner,integral,budget,definitions

    def update(self,time,sequence,x=3.,y=4.):
        """参数为ns/原序号/原值；返回冻结更新；非法参数沿模型报错。

        异常: 按上述测试场景传播或注入错误。
        """
        return LegacyDecodedUpdate(time,'bus',0,256,False,False,False,False,
            SourceRef('session','bus','message'),sequence,sequence,dict(X=x,Y=y))

    def pair(self,value):
        """参数为参考标量；返回精确有效值或无效原因二元组；不抛业务错误。

        异常: 按上述测试场景传播或注入错误。
        """
        return (value.value,None) if value.valid else (None,value.quality)

    def test_close_drops_program_and_definition_references(self):
        """关闭后预算和闭包均释放，即使调用者仍持有关闭后的owner。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        owner,integral,budget,definitions=self.owners()
        ref=weakref.ref(definitions[0]);del definitions
        owner.close();integral.close();gc.collect()
        self.assertEqual(budget.ram_bytes,0)
        self.assertIsNone(ref())
        for name in ('_programs','_normalizers','_deps','_ttl'):
            self.assertIsNone(getattr(owner,name))

    def test_constructor_failure_drops_compiled_program_locals(self):
        """编译后预算或归一化构造失败时，异常回溯和owner均不继续保留程序闭包。

        参数: 无。 返回: None。
        """
        for failure in ('reserve_before','reserve_after','normalizer'):
            owner,integral,budget,definitions=self.owners()
            expressions,binding=owner._expressions,owner._binding
            owner.close();borrowed_cost=budget.ram_bytes
            refs=[];calls=[0]
            original_compile=module._compile_float_program
            original_reserve=budget.reserve_ram
            def track(node):
                """参数为节点；返回原编译程序并记录弱引用；原编译异常保留。"""
                program=original_compile(node)
                refs.append(weakref.ref(program))
                return program
            def reserve(amount):
                """参数为费用；返回None；在第二笔编译后费用处注入RuntimeError。

                异常: 按上述测试场景传播或注入错误。
                """
                calls[0]+=1
                if failure.startswith('reserve') and calls[0]==2:
                    if failure=='reserve_after':original_reserve(amount)
                    raise RuntimeError('injected-constructor')
                original_reserve(amount)
            def normalize(definition):
                """参数为定义；无返回；注入归一化闭包分配失败。

                异常: 按上述测试场景传播或注入错误。
                """
                raise MemoryError('injected-normalizer')
            normalizer_patch=patch.object(module,'_float_normalizer',side_effect=normalize) if failure=='normalizer' else patch.object(module,'_float_normalizer',wraps=module._float_normalizer)
            with patch.object(module,'_compile_float_program',side_effect=track),patch.object(budget,'reserve_ram',side_effect=reserve),normalizer_patch:
                try:
                    module.SameFrameIntegrals(budget,definitions,expressions,(integral,),binding,'session',lambda:None)
                except (RuntimeError,MemoryError) as error:
                    frame=error.__traceback__
                    found=False
                    while frame is not None:
                        local=frame.tb_frame.f_locals
                        instance=local.get('self')
                        if frame.tb_frame.f_code.co_name=='__init__' and isinstance(instance,module.SameFrameIntegrals):
                            found=True
                            self.assertIsNone(local.get('programs'))
                            self.assertTrue(instance._closed)
                            for name in ('_programs','_normalizers','_deps','_ttl'):
                                self.assertIsNone(getattr(instance,name))
                        frame=frame.tb_next
                    self.assertTrue(found)
                else:self.fail('构造失败未传播')
            gc.collect()
            self.assertTrue(refs)
            self.assertTrue(all(ref() is None for ref in refs))
            self.assertEqual(budget.ram_bytes,borrowed_cost)
            integral.close();self.assertEqual(budget.ram_bytes,0)

    def test_wide_sequence_prepays_each_actual_slot(self):
        """首槽已预付64位容量，合法超宽序号补差；后续槽按实际大小计费。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        owner,integral,budget,_=self.owners()
        first=(1<<10000)-1;second=1<<12000
        base=budget.ram_bytes
        owner.consume(self.update(0,first))
        first_cost=512+16*_metadata_bytes(first)
        self.assertEqual(budget.ram_bytes-base,first_cost-module._SEQUENCE_SLOT_BYTES)
        owner.consume(self.update(0,second))
        self.assertEqual(budget.ram_bytes-base,first_cost-module._SEQUENCE_SLOT_BYTES+512+16*_metadata_bytes(second))
        owner.close();integral.close();self.assertEqual(budget.ram_bytes,0)

    def test_wide_sequence_budget_failure_leaves_no_unpaid_state(self):
        """超宽序号补费失败后不进入选择状态，关闭可完整清账。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        owner,integral,budget,_=self.owners();budget.memory_budget_bytes=budget.ram_bytes
        with self.assertRaises(BudgetExceededError):owner.consume(self.update(0,1<<10000))
        self.assertEqual(owner._seen,set());self.assertEqual(owner._chosen,{})
        with self.assertRaises(ResultClosedError):owner.consume(self.update(1,1))
        owner.close();integral.close();self.assertEqual(budget.ram_bytes,0)

    def test_conflict_precedes_additional_slot_budget_failure(self):
        """冲突和下一槽超预算同时存在时，保留原来的冲突错误。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        owner,_,budget,_=self.owners();owner.consume(self.update(0,0))
        budget.memory_budget_bytes=budget.ram_bytes
        with self.assertRaisesRegex(ValueError,'同信号同时间冲突'):
            owner.consume(self.update(0,1,99.,4.))

    def test_normalizer_matches_reference_for_edge_values(self):
        """检查非有限、类型、精度、业务范围和无效码，不以近似值掩盖差异。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        values=(0.,-0.,5e-324,1e-300,1e300,None,float('inf'),float('nan'),True,'3',2**53+1,2**64-1,2**64,-999.)
        for scale in (0,.5,1e-300,1e300,2**53+1):
            for offset in (0,3,2**53+1):
                for bounds in (None,(-10.,10.)):
                    for invalid in ((),(-999.,)):
                        definition=SignalDefinition('x','bus','x',D.FLOAT64,'1',1,input_unit='raw',
                            scale=scale,offset=offset,valid_range=bounds,invalid_values=invalid)
                        normalizer=module._float_normalizer(definition)
                        for raw in values:
                            expected=self.pair(normalize_reference(definition,raw))
                            actual=normalizer(raw)
                            self.assertEqual(actual,expected)
                            if actual[1] is None:self.assertEqual(actual[0].hex(),expected[0].hex())

    def test_compiled_subexpressions_preserve_all_quality_reasons(self):
        """嵌套表达式的两侧缺失、除零和非有限原因应与参考核逐位相同。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        values=(0.,-0.,1.,5e-324,1e300,None,float('inf'),True,'3',2**53+1)
        for text in ('x+y','x-y','x*y','x/y','abs(x)','-x','x*2','(x/y)+(y/x)','(x+y)/(x-y)'):
            owner,_,_,definitions=self.owners(text)
            root=owner._expressions[0].root;program=module._compile_float_program(root)
            for x in values:
                for y in values:
                    context={n:normalize_reference(d,v) for n,d,v in zip(('x','y'),definitions,(x,y))}
                    expected=self.pair(_evaluate(root,context,{}).value)
                    actual=program({n:self.pair(v) for n,v in context.items()})
                    self.assertEqual(actual,expected)
                    if actual[1] is None:self.assertEqual(actual[0].hex(),expected[0].hex())
            owner.close()

    def test_integral_matches_uncompiled_path_across_boundaries(self):
        """同一192组有效请求对照未编译路径，覆盖TTL、裁剪、批边界与无效覆盖。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        values=(0.,-0.,1.,-1.,5e-324,1e300,None,float('inf'),True,'3',2**53+1)
        rng=random.Random(140108)
        for index in range(192):
            text=('x','x+y','x-y','x*y','x/y','abs(x)','-x','x*2')[index%8]
            records=tuple(self.update(t,n,rng.choice(values),rng.choice(values)) for n,t in enumerate((0,40_000_000,100_000_000,170_000_000)))
            results=[]
            for compiled in (True,False):
                owner,integral,budget,_=self.owners(text,age=(25_000_000,65_000_000,10**9)[index%3],size=(1,2,64)[index%3])
                owner._fast=compiled
                for record in records:owner.consume(record)
                owner.finish(300_000_000);results.append(dataclasses.asdict(integral.finish()))
                owner.close();integral.close();self.assertEqual(budget.ram_bytes,0)
            self.assertEqual(results[0],results[1])
            if results[0]['value'] is not None:self.assertEqual(results[0]['value'].hex(),results[1]['value'].hex())

    def test_reserve_and_release_callbacks_before_after_failure(self):
        """费用更新前后抛错均保留原异常，解除故障后可重试关闭且不重复抵销。

        参数: 无。 返回: None。
        """
        for phase in ('reserve','release'):
            for after in (False,True):
                owner,integral,budget,_=self.owners();owner.consume(self.update(0,0))
                method=phase+'_ram';original=getattr(budget,method)
                def fail(amount):
                    """参数为费用；返回无；按注入点抛RuntimeError，必要时先登记费用。

                    异常: 按上述测试场景传播或注入错误。
                    """
                    if after:original(amount)
                    raise RuntimeError('injected-'+phase)
                with patch.object(budget,method,side_effect=fail):
                    with self.assertRaisesRegex(RuntimeError,'injected-'+phase):
                        if phase=='reserve':owner.consume(self.update(0,1))
                        else:owner.close()
                owner.close();integral.close();self.assertEqual(budget.ram_bytes,0)

    def test_shared_derived_tree_falls_back_before_compilation(self):
        """12层共享派生树不展开8191个闭包，继续原缓存求值并得到手算积分。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        with patch.object(module,'_compile_float_program',wraps=module._compile_float_program) as compile_program:
            owner,integral,budget,_=self.owners(depth=12,age=10**9)
            self.assertFalse(owner._fast)
            self.assertEqual(compile_program.call_count,0)
            self.assertIsNone(owner._programs)
        owner.consume(self.update(0,0,x=1.))
        owner.consume(self.update(300_000_000,1,x=1.))
        owner.finish(300_000_000)
        self.assertAlmostEqual(integral.finish().value,4096*.230)
        owner.close();integral.close();self.assertEqual(budget.ram_bytes,0)

    def test_shared_tree_detection_visits_unique_nodes_only(self):
        """检测24层共享结构时使用有限visited，不展开超过千万个引用位置。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        reads=[0]
        class Node:
            """给检测器提供只读args并记录访问次数。"""
            def __init__(self,args=()):
                """参数为子节点tuple；返回实例；无外部异常。"""
                self._args=args
            @property
            def args(self):
                """参数无；返回子节点并计数；无外部异常。"""
                reads[0]+=1
                return self._args
        node=Node()
        for _ in range(24):node=Node((node,node))
        self.assertTrue(module._has_shared_composite_nodes((node,)))
        self.assertLessEqual(reads[0],30)

    def test_unit_conversion_and_affine_zero_preserve_reference_quality(self):
        """mV转V的下溢与摄氏转开尔文的合法零各沿用原质量规则。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        clock=TimebaseSpec('clock',TimeType.RELATIVE,'origin')
        for source,target,values in (('mV','V',(5e-324,1.,1e300,None)),('degC','K',(-273.15,0.,1e300,None))):
            definition=SignalDefinition('x','bus','x',D.FLOAT64,source,10**9)
            bindings=DeclarationBindings('session',clock,Interval(0,10**9),(DeclaredSource('bus',clock,'synthetic'),),(definition,))
            root=validate_expression('x',bindings,unit=target).root
            program=module._compile_float_program(root)
            for raw in values:
                normalized=normalize_reference(definition,raw)
                expected=self.pair(_evaluate(root,{'x':normalized},{}).value)
                actual=program({'x':self.pair(normalized)})
                self.assertEqual(actual,expected)
                if actual[1] is None:self.assertEqual(actual[0].hex(),expected[0].hex())

    def test_hand_calculated_clipping_ttl_and_units(self):
        """常数12在裁剪范围内有效20+60+65+65ms，手算面积2.52。

        参数: 无。 返回: None。 异常: 断言失败或受测接口异常。
        """
        owner,integral,budget,_=self.owners(age=65_000_000)
        for sequence,time in enumerate((0,40_000_000,100_000_000,170_000_000)):
            owner.consume(self.update(time,sequence))
        owner.finish(300_000_000);result=integral.finish()
        # 实际无重叠有效段为20–40、40–100、100–165、170–235ms，共210ms。
        self.assertAlmostEqual(result.value,12*.210)
        self.assertEqual(result.status,'partial');self.assertTrue(result.quality & Q.STALE)
        owner.close();integral.close();self.assertEqual(budget.ram_bytes,0)


if __name__=='__main__':unittest.main()
