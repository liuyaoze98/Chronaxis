"""用真实最新状态和独立手算核在线规则边界，不建历史或全量时间轴。"""

from configuration_fixtures import current_fixture

from dataclasses import replace
import unittest
from chronaxis import AnalysisPlan
from chronaxis.execution.state import LatestSignalState
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.record_rule_timeline import RecordRuleTimeline
from chronaxis.results.budget import ResourceBudget
from test_stability_runner import stable_config
from test_stream_state import make_sample


class RecordRuleTimelineTests(unittest.TestCase):
    """源结束、TTL和实际记录原子更新与等待按同一明确规则处理。"""

    def run_case(self,rule,points,*,period=None,age=1000,end=1000,observed_end=None):
        """驱动完整状态组并比较两后端。参数: 规则/点/周期/有效期/结束。返回: 事件。异常: 原错误。"""
        results=[]
        for backend in ('reference','numpy'):
            raw=stable_config()
            raw.update(config_version=4)
            raw['dataset']['domain']=dict(start='0ns',end=f'{end}ns')
            raw['signals'][0]['valid_for']=f'{age}ns'
            raw['rules']=[rule]
            raw['execution']['backend']=backend
            raw['intervals']=dict(default=dict(mode='actual') if period is None else
                dict(mode='fixed',value=f'{period}ns',driver='temperature'))
            plan=AnalysisPlan.from_dict(current_fixture(raw))
            budget=ResourceBudget()
            state=LatestSignalState(budget,tuple(s.definition for s in plan.signals),'session')
            events=[]
            ends={}
            owner=RecordRuleTimeline(plan,plan.rules[0],state,budget,period,
                None if period is None else 'temperature',ends,events.append)
            try:
                owner.begin(points[0][0])
                for index,(time,value) in enumerate(points):
                    if index==len(points)-1:
                        ends['input']=time if observed_end is None else observed_end
                    owner.before_group(time)
                    definition=state.definitions['temperature']
                    state.apply(DecodedTimeGroup(time,(make_sample(definition,time,index,value),)))
                    owner.after_group(time)
                owner.finish(points[-1][0] if observed_end is None else observed_end)
                results.append(tuple(events))
            finally:
                owner.close();state.close()
            self.assertEqual(budget.ram_bytes,0)
        self.assertEqual(*results)
        return results[0]

    def test_actual_deadline_and_record_confirmation_use_real_coordinates(self):
        """0、120、300、900；实际200确认，周期100则300确认，均900结束。"""
        rule=dict(name='alarm',rule_type='condition_duration',condition='temperature > 80',minimum_duration='200ns')
        for period,expected in ((None,200),(100,300)):
            event,=self.run_case(rule,((0,85),(120,85),(300,85),(900,70)),period=period)
            self.assertEqual((event.start_ns,event.confirmed_ns,event.end_ns,event.status),(0,expected,900,'closed'))

    def test_eof_truncates_at_actual_last_record(self):
        """请求到1000，实际300结束；固定周期不能再补第4条。"""
        rule=dict(name='alarm',rule_type='condition_duration',condition='temperature > 80',minimum_duration='200ns')
        event,=self.run_case(rule,((0,85),(120,85),(300,85)),period=100)
        self.assertEqual((event.confirmed_ns,event.end_ns,event.status),(300,300,'truncated'))
        rule['minimum_duration']='300ns'
        self.assertFalse(self.run_case(rule,((0,85),(120,85),(300,85)),period=100))

    def test_ttl_interrupts_before_next_driver(self):
        """有效期150，下一条500；中途过期不会给等待凑周期或跨缺口拼接。"""
        rule=dict(name='alarm',rule_type='condition_duration',condition='temperature > 80',minimum_duration='100ns')
        events=self.run_case(rule,((0,85),(500,85),(600,70)),age=150)
        self.assertEqual(tuple((e.start_ns,e.confirmed_ns,e.end_ns,e.status) for e in events),
                         ((0,100,150,'interrupted'),(500,600,600,'closed')))
        events=self.run_case(rule,((0,85),(500,85),(600,70)),age=150,period=100)
        self.assertEqual(tuple((e.start_ns,e.confirmed_ns,e.end_ns) for e in events),((500,600,600),))

    def test_hysteresis_keeps_alarm_across_middle_band(self):
        """85→77→77→70，跨批中间区间不清已确认报警。"""
        rule=dict(name='alarm',rule_type='hysteresis',enter_condition='temperature >= 80',exit_condition='temperature <= 75')
        event,=self.run_case(rule,((0,85),(120,77),(300,77),(900,70)),period=100)
        self.assertEqual((event.start_ns,event.end_ns,event.status),(0,900,'closed'))
