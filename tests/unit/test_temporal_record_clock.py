"""独立手算记录周期等待；事件始终使用实际报文时间，不输出虚拟时间轴。"""

from dataclasses import replace
import unittest

from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.temporal_reference import ReferenceTemporalDetector
from chronaxis.core.temporal_numpy import NumpyTemporalDetector
from chronaxis.core.types import Truth as T, QualityFlag as Q


class TemporalRecordClockTests(unittest.TestCase):
    """核两独立后端的确认、实际失效、分批和不凭空增加周期。"""

    def run_ticks(self, rule, ticks, advances, size):
        """按指定批次执行两后端。参数: 规则/组/增量/批宽。返回: 一致事件。异常: 断言或核心错误。"""
        outputs=[]
        for factory in (ReferenceTemporalDetector,NumpyTemporalDetector):
            detector=factory(rule,ticks[0].time_ns,ticks[-1].time_ns,record_clock=True)
            events=[]
            for start in range(0,len(ticks),size):
                detector.push(ticks[start:start+size],advances=advances[start:start+size])
                self.assertIsNone(detector.next_deadline_ns)
                events.extend(detector.drain_events())
            self.assertFalse(detector.finish())
            outputs.append(tuple(events))
        self.assertEqual(*outputs)
        return outputs[0]

    def test_wait_confirms_at_real_third_record(self):
        """10、10.12、10.30秒每步0.1秒，满0.2秒时确认在10.30秒。"""
        ns=10**9
        ticks=(ConditionTick(10*ns,T.TRUE),ConditionTick(1012*ns//100,T.TRUE),
               ConditionTick(103*ns//10,T.TRUE),ConditionTick(11*ns,T.FALSE,terminal=True))
        rule=TemporalRule('alarm','data','session','condition_duration',ns//5)
        for size in (1,2,4):
            event,=self.run_ticks(rule,ticks,(0,ns//10,ns//10,ns//10),size)
            self.assertEqual((event.start_ns,event.confirmed_ns,event.end_ns),(10*ns,103*ns//10,11*ns))

    def test_no_timer_period_and_invalid_reset(self):
        """真实时间过去很久但无驱动不累计；失效后新候选不继承旧周期。"""
        ticks=(ConditionTick(0,T.TRUE),ConditionTick(100,T.TRUE,actual_update=False),
            ConditionTick(200,T.UNKNOWN,Q.STALE,actual_update=False),ConditionTick(300,T.TRUE),
            ConditionTick(400,T.TRUE),ConditionTick(500,T.FALSE,terminal=True))
        rule=TemporalRule('alarm','data','session','condition_duration',20)
        for size in (1,3,6):
            event,=self.run_ticks(rule,ticks,(0,0,0,10,10,10),size)
            self.assertEqual((event.start_ns,event.confirmed_ns,event.end_ns),(300,500,500))
        self.assertFalse(self.run_ticks(rule,ticks[:2]+(ConditionTick(500,T.TRUE,terminal=True),),(0,0,0),2))

    def test_start_only_suppression_counts_selected_updates(self):
        """真实时间很长仍按周期抑制；到期后只接受实际新边沿。"""
        states=(T.FALSE,T.TRUE,T.FALSE,T.TRUE,T.FALSE,T.TRUE)
        ticks=tuple(ConditionTick(i*100,state,terminal=i==5) for i,state in enumerate(states))
        rule=TemporalRule('edge','data','session','start_only',window_duration_ns=30)
        for size in (1,2,3,6):
            events=self.run_ticks(rule,ticks,(0,10,10,10,10,10),size)
            self.assertEqual(tuple(e.start_ns for e in events),(100,500))

    def test_exact_large_period_does_not_overflow(self):
        """多次int64大周期的累计保持精确，确认仍是实际第二条。"""
        ticks=(ConditionTick(0,T.TRUE),ConditionTick(1,T.TRUE),ConditionTick(2,T.TRUE),ConditionTick(3,T.FALSE,terminal=True))
        rule=TemporalRule('alarm','data','session','condition_duration',(1<<63)-1)
        for size in (1,4):
            event,=self.run_ticks(rule,ticks,(0,(1<<63)-1,(1<<63)-1,0),size)
            self.assertEqual(event.confirmed_ns,1)

    def test_modes_cannot_mix_or_fabricate_first_interval(self):
        """错误增量在推进前拒绝；实际模式保持旧协议。"""
        rule=TemporalRule('alarm','data','session','condition_duration',10)
        tick=(ConditionTick(0,T.TRUE),)
        for factory in (ReferenceTemporalDetector,NumpyTemporalDetector):
            owner=factory(rule,0,100,record_clock=True)
            for advances in (None,(1,),(True,),(-1,),((1<<63),)):
                with self.assertRaises((TypeError,ValueError)):
                    owner.push(tick,advances=advances)
                self.assertIsNone(owner.last_time)
            actual=factory(rule,0,100)
            with self.assertRaises(ValueError):
                actual.push(tick,advances=(0,))

    def test_stability_wait_and_optional_duration_share_record_clock(self):
        """进入等待200、退出等待100；实际300开始900结束，选定累计200。"""
        from chronaxis.core.stability import StabilityDetector, StabilitySpec
        ticks=tuple(ConditionTick(time,state,terminal=i==4) for i,(time,state) in enumerate(
            ((0,T.TRUE),(120,T.TRUE),(300,T.TRUE),(400,T.FALSE),(900,T.FALSE))))
        for backend in ('reference','numpy'):
            for size in (1,2,5):
                owner=StabilityDetector(TemporalRule('alarm','data','session','condition_duration'),0,900,
                    StabilitySpec(enter_ns=200,exit_ns=100,track_duration=True),backend=backend,record_clock=True)
                for start in range(0,5,size):
                    owner.push(ticks[start:start+size],advances=(0,100,100,100,100)[start:start+size])
                    self.assertIsNone(owner.next_deadline_ns)
                event,=owner.finish()
                self.assertEqual((event.start_ns,event.end_ns),(300,900))
                self.assertEqual(owner.duration_counts,(200,200))

    def test_start_end_timeout_or_endpoint_result(self):
        """固定两步才超时，结束同刻优先；无新驱动的EOF只截断不伪造超时。"""
        from chronaxis.core.start_end import StartEndDetector, StartEndSpec
        rule=TemporalRule('span','data','session','condition_duration')
        starts=tuple(ConditionTick(t,T.TRUE,terminal=i==2) for i,t in enumerate((0,120,900)))
        for backend in ('reference','numpy'):
            for final,advances,expected in ((T.FALSE,(0,100,100),'timeout'),(T.TRUE,(0,100,100),'closed'),
                                           (T.FALSE,(0,100,0),'truncated')):
                owner=StartEndDetector(rule,0,900,StartEndSpec(timeout_ns=200,emit_initial=True),
                                       backend=backend,record_clock=True)
                ends=(ConditionTick(0,T.FALSE),ConditionTick(120,T.FALSE),ConditionTick(900,final,terminal=True))
                for i in range(3):
                    owner.push(starts[i:i+1],ends[i:i+1],advances=advances[i:i+1])
                    self.assertIsNone(owner.next_deadline_ns)
                event,=owner.finish()
                self.assertEqual((event.start_ns,event.end_ns,event.status),(0,900,expected))

    def test_sequence_uses_selected_delay_and_actual_decision(self):
        """请求响应按两步200配对，实际时间仍是0到900；EOF不补足未走完周期。"""
        from chronaxis.core.sequence_reference import SequenceDetector
        from test_sequence import event, rule, tick
        specification=replace(rule(200,200),record_clock=True)
        for response,advances,status in ((True,(0,100,100),'matched'),(False,(0,100,100),'no_response'),
                                         (False,(0,100,0),'indeterminate'),(True,(0,100,200),'no_response')):
            ticks=(tick(0,starts=(event(0),)),tick(120),
                   tick(900,responses=(event(900,response=True),) if response else (),terminal=True))
            for size in (1,3):
                owner=SequenceDetector(specification,0,900)
                rows=[]
                for start in range(0,3,size):
                    rows.extend(owner.push(ticks[start:start+size],advances=advances[start:start+size]))
                owner.finish()
                row,=rows
                self.assertEqual((row.status,row.decided_ns),(status,900))
                self.assertEqual(row.delay_ns,200 if status=='matched' else None)

    def test_budget_wrapper_owns_increment_workspace(self):
        """记录增量费用随本批结果关闭归还，最终owner关闭账本归零。"""
        from chronaxis.execution.temporal_buffer import BudgetedTemporalDetector
        from chronaxis.results.budget import ResourceBudget
        # 预算构造复用现有有限数值，不启动来源。
        budget=ResourceBudget(64*1024*1024,64*1024*1024)
        owner=BudgetedTemporalDetector(budget,TemporalRule('a','d','s','condition_duration',10),0,20,record_clock=True)
        try:
            fixed=budget.ram_bytes
            batch=owner.push((ConditionTick(0,T.TRUE),ConditionTick(20,T.FALSE,terminal=True)),advances=(0,10))
            self.assertGreater(budget.ram_bytes,fixed)
            batch.close()
            self.assertEqual(budget.ram_bytes,fixed)
        finally:
            owner.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_internal_sequence_codec_preserves_record_clock(self):
        """当前内部叶子编码完整保两种时钟选择，缺字段拒绝；不提供旧结果兼容。"""
        from chronaxis.results.codec import _pack, _unpack
        from chronaxis.results.errors import ResultFormatError
        from test_sequence import rule
        for record_clock in (False, True):
            original=replace(rule(),record_clock=record_clock)
            packed=_pack(original)
            self.assertIs(packed['fields']['record_clock'],record_clock)
            self.assertEqual(_unpack(packed),original)
            del packed['fields']['record_clock']
            with self.assertRaises(ResultFormatError):
                _unpack(packed)
