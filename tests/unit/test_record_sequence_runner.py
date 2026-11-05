"""公开schema2配对的独立手算：同刻、实际/周期、TTL/EOF与取消。"""

from configuration_fixtures import current_fixture

from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisRunner,AnalysisPlan,validate_analysis_plan
from test_sequence_runner import config_fixture


class RecordSequenceRunnerTests(unittest.TestCase):
    """不借旧AnalysisRunner生成真值，输出只保单一延迟和事件ID。"""

    def config(self,mode='actual'):
        """转为新合同并明确周期驱动。参数: 模式。返回: 配置。异常: 无。"""
        raw=config_fixture()
        raw.update(config_version=4)
        raw['intervals']={'default':{'mode':mode}}
        if mode=='fixed':
            raw['intervals']['default'].update(value='1ns',driver='request')
        return raw

    def run_config(self,raw):
        """使用真实公开入口。参数: 配置。返回: 可关闭结果。异常: 原运行错。"""
        plan=AnalysisPlan.from_dict(current_fixture(raw))
        self.assertTrue(validate_analysis_plan(plan).execution_ready)
        path=Path(__file__).resolve().parents[2]/'work/m3-raw-interval-home/sequence'/uuid4().hex
        result=AnalysisRunner().run(plan,path)
        self.addCleanup(result.close)
        return result

    def test_hand_values_backends_batches(self):
        """末次10→12只有一次驱动：actual超时，fixed等待未满而结束。"""
        for mode in ('actual','fixed'):
            for backend in ('reference','numpy'):
                for batch in (1,7):
                    with self.subTest(mode=mode,backend=backend,batch=batch):
                        raw=self.config(mode)
                        raw['execution'].update(backend=backend,batch_rows=batch)
                        result=self.run_config(raw)
                        events={row.event_id:row for row in result.iter_events()}
                        actual=[(events[r.request_id].confirmed_ns,r.status,r.decided_ns,r.delay_ns)
                                for r in result.iter_sequences()]
                        self.assertEqual(actual,[(1,'matched',3,2),(4,'indeterminate',6,None),
                            (7,'matched',9,2),(10,'no_response' if mode=='actual' else 'indeterminate',12,None)])
                        budget=result.spool.budget
                        result.close()
                        self.assertEqual(budget.ram_bytes,0)

    def test_simultaneous_and_empty(self):
        """同刻请求与响应只能提交一次；空来源不造配对。"""
        for empty in (False,True):
            raw=self.config('fixed')
            raw['sources'][0]['rows']=[] if empty else [
                dict(time='0ns',values=dict(request=False,response=False)),
                dict(time='1ns',values=dict(request=True,response=True))]
            result=self.run_config(raw)
            rows=tuple(result.iter_sequences())
            self.assertEqual(len(rows),0 if empty else 1)
            if rows:
                self.assertEqual((rows[0].status,rows[0].delay_ns,rows[0].decided_ns),('matched',0,1))

    def test_cancel_after_pair(self):
        """真正写出一条结果后取消，不发布前缀，费用清零。"""
        from chronaxis.execution.record_session_calculations import RecordSessionCalculations
        original=RecordSessionCalculations._emit_sequence
        budgets=[]
        def cancel(owner,row):
            """模拟取消。参数: owner/row。返回: 无。异常: KeyboardInterrupt。"""
            original(owner,row)
            budgets.append(owner._budget)
            raise KeyboardInterrupt('after pair')
        with patch.object(RecordSessionCalculations,'_emit_sequence',cancel):
            with self.assertRaises(KeyboardInterrupt):
                self.run_config(self.config())
        self.assertEqual(budgets[0].ram_bytes,0)

    def test_shorter_and_empty_response_source(self):
        """响应来源结束后不能证明无响应；空响应来源也须按真实请求EOF结束。"""
        for empty in (False,True):
            raw=self.config()
            raw['sources'].append(dict(name='reply_input',source_type='memory',
                time=dict(time_type='relative',unit='ns',origin='clock'),
                rows=[] if empty else [dict(time=f'{t}ns',values={'response':False}) for t in (0,5)]))
            raw['signals'][1]['source']='reply_input'
            result=self.run_config(raw)
            rows=tuple(result.iter_sequences())
            self.assertEqual(len(rows),4)
            self.assertEqual(rows[0].status,'indeterminate' if empty else 'no_response')
            self.assertTrue(all(row.status=='indeterminate' for row in rows[1:]))

    def test_capacity_failure_releases_pending_requests(self):
        """请求超容量必须失败，不能漏掉请求后继续成功。"""
        from chronaxis.execution.record_sequences import RecordSequences
        from chronaxis.results.errors import BudgetExceededError
        raw=self.config('fixed')
        raw['sequences'][0].update(max_pending=1,max_delay='100ns')
        raw['sources'][0]['rows']=[dict(time=f'{t}ns',values=dict(request=bool(t%2),response=False)) for t in range(5)]
        original=RecordSequences.close
        budgets=[]
        def close(owner):
            """记录真实账本用于最终断言。参数: owner。返回: None。异常: 原关闭错。"""
            budgets.append(owner._budget)
            original(owner)
        with patch.object(RecordSequences,'close',close):
            with self.assertRaises(BudgetExceededError):
                self.run_config(raw)
        self.assertTrue(budgets)
        self.assertEqual(budgets[-1].ram_bytes,0)
