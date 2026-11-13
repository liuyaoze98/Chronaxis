"""保留旧混合文件中仍属于当前Runner的单次读取与恢复断言。"""
import unittest
from unittest.mock import patch
from configuration_fixtures import current_fixture
import test_run_message_calculations as runner_fixture
import message_calculation_fixture as scan_fixtures
from chronaxis import AnalysisPlan, AnalysisRunner, AnalysisError
from chronaxis.execution.text_can_reader import TextCANObservationRead, BudgetedTextCANSourceAdapter
from chronaxis.execution import message_delivery
from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from chronaxis.legacy.message_store import DecodedMessageStore
from chronaxis.results.budget import ResourceBudget

class RecordMigrationLifecycleTests(unittest.TestCase):
    """只调用现役公共入口，故障保持真实父资源的恢复责任。"""

    def test_public_runner_two_parameter_sets_share_one_actual_read(self):
        """两个period独立得800/1600J；同次读入四帧、交付三帧，不回读旧消息仓。

        参数: 无。返回: None。异常: 重复扫描、共用错误参数、漏求值或资源不归零令断言失败。
        """
        helper = runner_fixture.RunMessageCalculationTests('runTest')
        self.addCleanup(helper.doCleanups)
        work, config, _ = helper.fixture(calculation_count=2)
        config['message_calculations'][1]['parameters']['period']['value'] = .2
        plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=work)
        original, calls = message_delivery.deliver_message, []
        snapshot, snapshots = CurrentMessageCalculation.snapshot, {}
        close, observations = TextCANObservationRead.close, []

        def delivered(reader, projection, consumer, *args, **kwargs):
            """只统计真正交给指标的投影。参数: 原交付参数。返回: 原结果。异常: 原错误。"""
            def accepted(update):
                """记录读取器身份后交付原对象。参数: update。返回: 原值。异常: 消费者原错误。"""
                calls.append(id(reader))
                return consumer(update)
            return original(reader, projection, accepted, *args, **kwargs)

        def observed(owner):
            """保存真实累计快照用于独立计数校验。参数: owner。返回: 原快照。异常: 原错误。"""
            value = snapshot(owner)
            snapshots[owner._calculation.calculation_id] = value
            return value

        def closed(reader):
            """关闭前保存真实EOF，不以交付条数冒充原帧数。参数: reader。返回: 原结果。异常: 原错误。"""
            if reader.exhausted and not reader.closed and not reader.failed:
                observations.append(reader.observation)
            return close(reader)

        with patch.object(message_delivery, 'deliver_message', delivered), \
                patch.object(CurrentMessageCalculation, 'snapshot', observed), \
                patch.object(TextCANObservationRead, 'close', closed), \
                patch.object(DecodedMessageStore, 'iter_records', side_effect=AssertionError('当前执行不回读旧消息仓')):
            result = helper.run_plan(work, plan)
        rows = helper.rows(result, 'summary')
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(set(calls)), 1)
        self.assertEqual([(fact.row_count, fact.source_eof) for fact in observations], [(4, True)])
        self.assertEqual({row.calculation_id: row.value for row in rows}, {'energy0': 800., 'energy1': 1600.})
        self.assertEqual(set(snapshots), {'energy0', 'energy1'})
        self.assertTrue(all(row.evaluation_count == 3 and row.skipped_count == 1 for row in snapshots.values()))
        self.assertEqual(len(helper.rows(result, 'contributions')), 6)
        result.close()
        self.assertEqual(result.spool.budget.ram_bytes, 0)


    def test_runner_adopts_failed_source_factory_with_persistent_release(self):
        """当前CAN来源构造已入账后失败，最高Runner保原错与可恢复责任。参数: 无。返回: None。异常: 断言。"""
        from chronaxis.execution.record_source_cursor import RecordSourceCursor
        work, plan = scan_fixtures.make_scan_fixture()
        primary = ValueError('test source factory failed')
        budgets, armed = [], [False]
        original_new = RecordSourceCursor._new
        original_reserve, original_release = ResourceBudget.reserve_ram, ResourceBudget.release_ram
        def refuse(amount):
            """持续拒绝退费直到恢复。参数: bytes。返回: 不成功。异常: OSError。"""
            raise OSError('test persistent ledger cleanup')
        def construct(owner, factory, recovery, *args, **kwargs):
            """限定实际CAN适配器构造的首次预约。参数: 原工厂参数。返回: 原owner。异常: 原错。"""
            armed[0] = factory is BudgetedTextCANSourceAdapter
            try:
                return original_new(owner, factory, recovery, *args, **kwargs)
            finally:
                armed[0] = False
        def reserve(budget, amount):
            """真实入账后注入主错，清理故障保留到断言完成。参数: 原预算/bytes。返回: None。异常: primary。"""
            original_reserve(budget, amount)
            if armed[0] and not budgets:
                budgets.append(budget)
                budget.release_ram = refuse
                raise primary
        try:
            with patch.object(RecordSourceCursor, '_new', new=construct), patch.object(ResourceBudget,'reserve_ram',new=reserve):
                with self.assertRaises(AnalysisError) as caught:
                    AnalysisRunner().run(plan, work_dir=work / 'run')
            self.assertIs(caught.exception.__cause__, primary)
            owner = caught.exception.runner_cleanup_owner
            self.assertIsNotNone(primary.record_source_cleanup_owner)
            self.assertFalse(owner.closed)
            self.assertGreater(owner._budget.ram_bytes, 0)
        finally:
            for budget in budgets:
                budget.release_ram = original_release.__get__(budget, ResourceBudget)
        owner.close()
        self.assertTrue(owner.closed)
        self.assertEqual(owner._budget.ram_bytes, 0)
