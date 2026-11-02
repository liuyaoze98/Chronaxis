"""用真实小文件和禁止构造探针核schema2需求裁剪；不计未运行的能力。"""

from configuration_fixtures import current_fixture
from copy import deepcopy
from contextlib import ExitStack
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisPlan,AnalysisRunner,explain_analysis_plan
from dataclasses import replace
from chronaxis.analysis_cli import explanation_json
from chronaxis.planning.input_requirements import collect_input_requirements
import test_record_runner as raw_cases

class RecordDemandTests(unittest.TestCase):
    """未用来源即使路径不存在也不打开；必要计算结果保持。"""
    setUp=raw_cases.RecordRunnerTests.setUp
    asc=raw_cases.RecordRunnerTests.asc
    csv=raw_cases.RecordRunnerTests.csv
    blf=raw_cases.RecordRunnerTests.blf
    fixtures=raw_cases.RecordRunnerTests.fixtures
    plan=raw_cases.RecordRunnerTests.plan

    def test_unused_source_and_consumers_are_not_constructed(self):
        """三格式同一积分结果880J，不建规则/窗口/历史/导出阶段。"""
        from chronaxis.execution.record_source_cursor import RecordSourceCursor
        original=RecordSourceCursor.__init__
        for kind,path in self.fixtures().items():
            configs=[]
            def edit(raw):
                unused=deepcopy(raw['sources'][0]);unused['name']='unused'
                unused['path']=str(self.root/('not-present-input'+path.suffix));unused['dbc_by_channel']={'1':str(self.root/'not-present-dbc')}
                raw['sources'].append(unused)
                alias=deepcopy(raw['signals'][0]);alias.update(name='unused_value',source='unused');raw['signals'].append(alias)
                raw['derived']['unused_expression']={'expr':'unused_value * 2','unit':'V'}
                raw['calculations']=raw['calculations'][:1]
                configs.append(deepcopy(raw))
            plan=self.plan(kind,path,'fixed',edit)
            if kind=='can_blf':
                all_sources=AnalysisPlan.from_dict(current_fixture(configs[0])).sources
                plan=replace(plan,sources=(plan.sources[0],*all_sources[1:]))
            needed=collect_input_requirements(plan)
            self.assertFalse(needed.for_source('unused').active)
            self.assertEqual(needed.for_source('unused').time_scope,'none')
            explanation=explanation_json(explain_analysis_plan(plan))
            self.assertFalse(next(x for x in explanation['input_requirements'] if x['source']=='unused')['active'])
            seen=[]
            def inspect(owner,*args,**kwargs):
                seen.append((args[1].name,kwargs['requirements']))
                return original(owner,*args,**kwargs)
            with ExitStack() as stack:
                stack.enter_context(patch.object(RecordSourceCursor,'__init__',inspect))
                for name in ('RecordRuleTimeline','RecordSequences','RecordTimeIndexes','RecordWindows','RecordScopeCalculations','RecordExports','RecordEventDurations'):
                    stack.enter_context(patch('chronaxis.execution.record_session_calculations.'+name,side_effect=AssertionError('无消费者却构造'+name)))
                with AnalysisRunner().run(plan,self.root/uuid4().hex) as result:
                    self.assertAlmostEqual(next(result.iter_calculations()).value,880,places=3)
            self.assertEqual([name for name,_ in seen],[plan.sources[0].name])
            self.assertEqual(seen[0][1],needed.sources[0])

    def test_empty_events_do_not_open_window_replay(self):
        """规则未命中时，不为窗口读取空事件文件。"""
        from chronaxis.results.spool import ResultSpool
        path=self.fixtures()['can_asc']
        def edit(raw):
            raw['calculations']=[]
            raw['rules']=[dict(name='edge',rule_type='rising_edge',condition='current > 100')]
            raw['windows']=[dict(name='around',rule='edge',anchor='point',pre='0.1s',post='0.1s')]
        from chronaxis.execution.record_windows import RecordWindows
        original=RecordWindows.finish
        def finish(owner,*args):
            with patch.object(ResultSpool,'_seal_table',side_effect=AssertionError('空事件不需要打开回放')):
                return original(owner,*args)
        with patch.object(RecordWindows,'finish',finish):
            with AnalysisRunner().run(self.plan('can_asc',path,'actual',edit),self.root/uuid4().hex) as result:
                self.assertEqual(result.spool.counts['events'],0)
                self.assertEqual(result.spool.counts['segments'],0)

    def test_default_samples_have_one_value_and_no_original_text(self):
        """在生成点检查普通值没有物理副本，文本计算不保原时间和导出坐标。"""
        from chronaxis.execution.record_source_cursor import RecordSourceCursor
        from chronaxis.execution.record_sample import RecordSample
        from chronaxis.sources.text_can_decode import CANTextDecodeRead
        enqueue=RecordSourceCursor._enqueue;decode=CANTextDecodeRead._decode
        seen=[];text_rows=[]
        def inspect(owner,group):
            for sample in group.samples:
                self.assertIs(type(sample),RecordSample)
                self.assertNotIn('array_value',sample.__dataclass_fields__)
                self.assertIs(sample.array_value,sample.value.value)
                self.assertFalse(sample.original_present)
                seen.append(sample.name)
            return enqueue(owner,group)
        def no_text(owner,raw):
            self.assertIsNone(raw.raw_time);self.assertIsNone(raw.source_time_ns)
            text_rows.append(raw.sequence);return decode(owner,raw)
        for kind,path in self.fixtures().items():
            with patch.object(RecordSourceCursor,'_enqueue',inspect),patch.object(CANTextDecodeRead,'_decode',no_text):
                with AnalysisRunner().run(self.plan(kind,path,'fixed'),self.root/uuid4().hex) as result:
                    self.assertAlmostEqual(next(result.iter_calculations()).value,880,places=3)
        self.assertTrue(seen);self.assertEqual(len(text_rows),6)
