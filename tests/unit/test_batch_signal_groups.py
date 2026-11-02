"""核在线同刻归组的预算、watermark和关闭；不构造全历史。"""

from configuration_fixtures import current_fixture
import unittest
from chronaxis import AnalysisPlan
from chronaxis.execution.batch_signal_groups import BatchSignalGroups
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.models import ReadRequest
from test_interval_planning import fixture


class BatchSignalGroupsTests(unittest.TestCase):
    """只在来源承诺完整且后续组到来后输出，最后组由finish提交。"""

    def setup_stream(self, consume):
        """构造实际内存reader与归组。参数: consumer。返回: budget,groups,read。异常: 构造原错。"""
        plan = AnalysisPlan.from_dict(current_fixture(fixture()))
        budget = ResourceBudget()
        definitions = tuple(item.definition for item in plan.signals)
        groups = BatchSignalGroups(budget,definitions,plan.dataset.session_id,consume)
        self.addCleanup(groups.close)
        adapter = BudgetedMemorySourceAdapter(budget,plan.sources[0].config,plan.dataset.session_id,definitions)
        self.addCleanup(adapter.close)
        read = adapter.iter_batches(ReadRequest(plan.dataset.session_id,('power',),0,300000000,1))
        self.addCleanup(read.close)
        return budget,groups,read,adapter

    def test_last_group_requires_finish_and_no_original_trace(self):
        """完整末组在finish前保留，来源字段引用共享且不保原值副本。"""
        output=[]
        budget,groups,read,adapter=self.setup_stream(output.append)
        for batch in read:
            groups.consume(batch)
        self.assertEqual([group.time_ns for group in output],[0,120000000])
        read.close(); adapter.close()
        groups.finish()
        self.assertEqual([group.time_ns for group in output],[0,120000000,300000000])
        self.assertTrue(all(not sample.original_present and sample.source_ref is output[0].samples[0].source_ref
                            for group in output for sample in group.samples))
        output.clear(); groups.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_early_close_never_flushes_and_budget_failure_is_terminal(self):
        """提前关闭不冒充EOF；未完成组超预算不拆组继续。"""
        output=[]
        budget,groups,read,adapter=self.setup_stream(output.append)
        batch=next(read)
        budget.memory_budget_bytes=budget.ram_bytes+1
        with self.assertRaises(BudgetExceededError):
            groups.consume(batch)
        with self.assertRaises(ResultClosedError):
            groups.finish()
        groups.close();read.close();adapter.close()
        self.assertEqual(output,[])
        self.assertEqual(budget.ram_bytes,0)

    def test_consumer_error_keeps_root_cause_and_refunds(self):
        """交付异常不提供成功finish，所有真实费用仍由本owner释放。"""
        error=OSError('consumer')
        def fail(group):
            """注入消费故障。参数: group。返回: 无。异常: 指定OSError。"""
            raise error
        budget,groups,read,adapter=self.setup_stream(fail)
        with self.assertRaises(OSError) as caught:
            for batch in read:
                groups.consume(batch)
        self.assertIs(caught.exception,error)
        groups.close(); read.close(); adapter.close()
        self.assertEqual(budget.ram_bytes,0)
