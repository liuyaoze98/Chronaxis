"""验证公共运行在真实构造、读取、阶段交付及最终移交失败后的恢复责任。

输入为本例独立生成的memory/CSV和完整公开计划；只以真实生产调用先执行、
再在指定边界注入原错误或取消。异常路径调用公开AnalysisRunner，捕获实际RunSession、
历史FD和原CSV关闭句柄；持续清理失败后恢复同一最高owner，不制造半初始化对象。
有限测试容器不计入产品预算；不据本例推断RSS、性能或用户日志结论。
产物全部在新项目work保留并标home，不改RefProjects、旧算法或正常预算。
"""

from configuration_fixtures import current_fixture
# 标准库故障注入只拦真实调用边界；公开入口及原预算始终执行。
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from chronaxis import AnalysisRunner, load_analysis_plan, AnalysisError
from chronaxis.execution.run_session import RunSession
from chronaxis.execution.record_source_cursor import RecordSourceCursor
from chronaxis.execution.memory_reader import _BudgetedBatches
from chronaxis.execution.csv_reader import _CSVRequest
from chronaxis.sources.signal_csv import SignalCSVSourceAdapter
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.spool import ResultSpool


class ReleaseFault:
    """保留真实预算方法；active后在释放前或后持续抛同一取消对象。"""

    def __init__(self, after=False):
        """设故障位置。参数: after是否实际扣账后取消。返回: 新控制器。异常: 无。"""
        self.active, self.after, self.calls = False, after, 0
        self.error = KeyboardInterrupt('D4 persistent release cancellation')

    @contextmanager
    def installed(self):
        """替换释放入口但保留真实底层扣账。参数: 无。返回: 上下文。异常: 原操作或注入取消。"""
        original = ResourceBudget.release_ram
        controller = self

        def release(budget, amount):
            """按指定边界注入。参数: 实际账本/本次bytes。返回: None。异常: 原错误或同一取消。"""
            if not controller.active:
                return original(budget, amount)
            controller.calls += 1
            if controller.after:
                original(budget, amount)
            raise controller.error

        with patch.object(ResourceBudget, 'release_ram', new=release):
            yield self


class RunnerRecoveryTests(unittest.TestCase):
    """逐个公共run观察真实owner，恢复后账本归零且实际句柄全部关闭。"""

    def fixture(self, kind='signal_csv', backend='numpy'):
        """创建独立真实三行计划。参数: 来源种类/后端。返回: plan/work。异常: 原写入/解析错误。"""
        work = Path(__file__).resolve().parents[2] / 'work/m2-run-tests/runner-recovery' / uuid4().hex
        work.mkdir(parents=True)
        source = dict(name='table', source_type=kind, time=dict(time_type='relative', unit='ns', origin='runner-home'))
        if kind == 'memory':
            source['rows'] = [dict(time=str(t)+'ns', values={'v':v}) for t,v in ((0,2),(2,3),(8,4))]
        else:
            (work/'source.csv').write_text('ns,v\n0,2\n2,3\n8,4\n', encoding='utf-8')
            source.update(path='source.csv', time_column='ns')
        config = dict(config_version=4,
            dataset=dict(name='recovery', entity='synthetic', session='session', domain=dict(start='0ns',end='12ns')),
            sources=[source], signals=[dict(name='v',source='table',field='v',dtype='float64',unit='1',valid_for='20ns')],
            rules=[dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='v > 0',minimum_duration='0ns')],
            windows=[dict(name='window',rule='active',anchor='activity',pre='0ns',post='0ns',merge='none')],
            calculations=[dict(name='whole',scope='session',operation='integral',expr='v'),
                     dict(name='event',scope='event:active',operation='integral',expr='v'),
                     dict(name='window_value',scope='segment:window',operation='integral',expr='v')],
            execution=dict(backend=backend,batch_rows=1,result_buffer_rows=1,memory_budget_bytes=256*1024**2),
            metadata=dict(device_label='home',data_kind='synthetic'))
        path=work/'plan.json'
        path.write_text(json.dumps(current_fixture(config)),encoding='utf-8')
        return SimpleNamespace(plan=load_analysis_plan(path),work=work)

    @contextmanager
    def observe(self):
        """记录真正构造的session与文件对象。参数: 无。返回: 观察容器。异常: 原构造/关闭错误。"""
        facts = SimpleNamespace(sessions=[], handles=[])
        session_init = RunSession.__init__
        close_handle = SignalCSVSourceAdapter._close_handle
        path_open = Path.open

        def session_created(owner,*args,**kwargs):
            """保留实际self而非手造对象。参数: 原构造参数。返回: None。异常: 原初始化错误。"""
            facts.sessions.append(owner)
            # 断言意外失败时，unittest在故障patch退出后仍重试同一真实owner，避免影响后例。
            self.addCleanup(owner.close)
            session_init(owner,*args,**kwargs)

        def source_handle_closed(owner,handle,primary):
            """在原关闭前记真实CSV文件。参数: 来源/原FD/主错。返回: None。异常: 原关闭错误。"""
            facts.handles.append(handle)
            return close_handle(owner,handle,primary)

        def input_opened(path,*args,**kwargs):
            """记录实际源文件，仍返回原TextIO。参数: 原Path/打开参数。返回: 真FD。异常: 原打开错误。"""
            handle=path_open(path,*args,**kwargs)
            if path.name=='source.csv':
                facts.handles.append(handle)
            return handle

        with ExitStack() as stack:
            stack.enter_context(patch.object(RunSession,'__init__',new=session_created))
            stack.enter_context(patch.object(SignalCSVSourceAdapter,'_close_handle',new=source_handle_closed))
            stack.enter_context(patch.object(Path,'open',new=input_opened))
            yield facts

    def recover(self,data,facts,fault,primary):
        """运行并恢复最高真实owner。参数: 真计划/观察/释放控制/主错。返回: session。异常: 不符断言。"""
        try:
            AnalysisRunner().run(data.plan,work_dir=data.work/'run')
        except BaseException as error:
            # 业务IO保cause，取消对象不被清理副错替换；两者都携实际最高恢复owner。
            if isinstance(primary,(KeyboardInterrupt,SystemExit,AnalysisError)):
                self.assertIs(error,primary)
            else:
                self.assertIsInstance(error,AnalysisError)
                self.assertIs(error.__cause__,primary)
            self.assertEqual(len(facts.sessions),1)
            owner=facts.sessions[0]
            self.assertIs(error.runner_cleanup_owner,owner)
            self.assertTrue(owner.failed)
            # 持续“释放前”故障必须可重复重试，after模式允许费用已真实释放而完成关闭。
            if not owner.closed and not fault.after:
                for _ in range(3):
                    with self.assertRaises(KeyboardInterrupt) as retry:
                        owner.close()
                    self.assertIs(retry.exception,fault.error)
                self.assertGreaterEqual(fault.calls,3)
            fault.active=False
            owner.close()
            owner.close()
            self.assertTrue(owner.closed)
            self.assertEqual(owner._budget.ram_bytes,0)
            self.assertTrue(all(handle.closed for handle in facts.handles))
            self.assertTrue((data.work/'source.csv').exists() if data.plan.sources[0].source_type=='signal_csv' else
                            (data.work/'plan.json').exists())
            if owner.work_dir is not None:
                self.assertFalse(owner.work_dir.exists())
            return owner
        else:
            self.fail('故障没有到达公共run，不应返回成功结果')

    def test_session_initial_reserve_after_cancel_preserves_original_and_zero_balance(self):
        """首次真实申请后取消仍有已初始化责任槽。参数: 无。返回: None。异常: 主错/费用不符。"""
        original=ResourceBudget.reserve_ram
        for error in (KeyboardInterrupt('session reserve'),SystemExit('session reserve')):
            with self.subTest(error=type(error).__name__):
                data=self.fixture(); fired=False
                def reserve(budget,amount):
                    """首笔实际入账后取消。参数: 实际账本/bytes。返回: None。异常: 原取消对象。"""
                    nonlocal fired
                    original(budget,amount)
                    if not fired:
                        fired=True
                        raise error
                with self.observe() as facts, ReleaseFault().installed() as fault, patch.object(
                        ResourceBudget,'reserve_ram',new=reserve):
                    self.recover(data,facts,fault,error)
                self.assertTrue(fired)

    def test_unreturned_source_spool_and_record_factory_owners_survive_cancel(self):
        """当前来源、最终暂存、记录会话真实申请后取消，持续清理失败仍能恢复最高父。"""
        original_construct,original_new=RunSession._construct,RecordSourceCursor._new
        original_reserve=ResourceBudget.reserve_ram
        for kind in ('memory','signal_csv'):
            for slot in ('_spool','_record_calculations','_source'):
                for after in (False,True):
                    with self.subTest(kind=kind,slot=slot,after=after):
                        data=self.fixture(kind);primary=KeyboardInterrupt('factory '+slot)
                        state=dict(armed=False,fired=False)
                        with self.observe() as facts,ReleaseFault(after).installed() as fault:
                            def construct(owner,name,factory,*args,**kwargs):
                                """围绕原会话工厂设置一次注入范围，不制造子对象。"""
                                state['armed']=name==slot and not state['fired']
                                try:return original_construct(owner,name,factory,*args,**kwargs)
                                finally:state['armed']=False
                            def source_new(owner,factory,recovery,*args,**kwargs):
                                """定位当前实际来源适配器工厂的第一次预约。"""
                                armed=state['armed']
                                if slot=='_source' and factory.__name__ in ('BudgetedMemorySourceAdapter','BudgetedSignalCSVSourceAdapter'):
                                    state['armed']=not state['fired']
                                try:return original_new(owner,factory,recovery,*args,**kwargs)
                                finally:state['armed']=armed
                            def reserve(budget,amount):
                                """先入账再取消；释放故障保持到正式恢复。"""
                                original_reserve(budget,amount)
                                if state['armed'] and not state['fired']:
                                    state['fired']=True;fault.active=True;raise primary
                            with patch.object(RunSession,'_construct',new=construct),patch.object(RecordSourceCursor,'_new',new=source_new),patch.object(ResourceBudget,'reserve_ram',new=reserve):
                                self.recover(data,facts,fault,primary)
                            self.assertTrue(state['fired'])

    def test_real_read_error_and_cancellation_keep_scan_parent_and_files(self):
        """真实首批已生成后的IO或取消保原对象，恢复scan/来源及账本。参数: 无。返回: None。异常: 根因或FD不符。"""
        for kind,read_type in (('memory',_BudgetedBatches),('signal_csv',_CSVRequest)):
            for backend in ('reference','numpy'):
                for cancelled in (False,True):
                    with self.subTest(kind=kind,backend=backend,cancelled=cancelled):
                        data=self.fixture(kind,backend)
                        primary=KeyboardInterrupt('actual read') if cancelled else OSError('actual read')
                        original=read_type.__next__; fired=False
                        with self.observe() as facts, ReleaseFault().installed() as fault:
                            def read(owner):
                                """先走实际读取再让本批交付失败。参数: 真read。返回: 真批次。异常: 原主错。"""
                                nonlocal fired
                                batch=original(owner)
                                if not fired:
                                    fired=True;fault.active=True
                                    raise primary
                                return batch
                            with patch.object(read_type,'__next__',new=read):
                                self.recover(data,facts,fault,primary)
                            self.assertTrue(fired)

    def test_each_current_output_partial_delivery_preserves_primary_and_recoverable_spool(self):
        """当前事件、会话/事件/片段计算及片段的真实首行入仓后失败，不能交付前缀。"""
        original=ResultSpool.append
        for target in ('events','segments','session','event','segment'):
            for backend in ('reference','numpy'):
                with self.subTest(target=target,backend=backend):
                    data=self.fixture(backend=backend);primary=OSError(28,'current output disk full');seen=[]
                    with self.observe() as facts,ReleaseFault().installed() as fault:
                        def append(spool,row):
                            """先真实写入选中业务行，再抛主错误和持续清理副错。"""
                            value=original(spool,row)
                            kind=type(row).__name__
                            selected=(kind=='SummaryEventRow' and target=='events' or
                                      kind=='SummarySegmentRow' and target=='segments' or
                                      kind=='SummaryCalculationRow' and row.scope==target)
                            if selected and not seen:
                                seen.append((kind,row.sequence));fault.active=True;raise primary
                            return value
                        with patch.object(ResultSpool,'append',new=append):
                            self.recover(data,facts,fault,primary)
                        self.assertEqual(len(seen),1)
                        self.assertFalse((data.work/'run').exists())

    def test_final_result_before_transfer_release_cancel_still_owns_real_result(self):
        """真实结果已构造但尚未移交时取消，session仍关闭最高结果。参数: 无。返回: None。异常: 孤儿结果/重复释放。"""
        original=RunSession._release_costs
        for backend in ('reference','numpy'):
            for after in (False,True):
                with self.subTest(backend=backend,after=after):
                    data=self.fixture(backend=backend);captured=[]
                    with self.observe() as facts, ReleaseFault(after).installed() as fault:
                        def release(owner):
                            """只在首次成功移交前启用故障。参数: 真session。返回: None。异常: 真释放取消。"""
                            if owner._result is not None and not captured:
                                captured.append(owner._result)
                                fault.active=True
                            return original(owner)
                        with patch.object(RunSession,'_release_costs',new=release):
                            self.recover(data,facts,fault,fault.error)
                        self.assertEqual(len(captured),1)
                        self.assertTrue(captured[0]._closed)
                        self.assertEqual(captured[0].status,'cancelled')

    def test_final_spool_write_error_without_cleanup_fault_returns_zero_and_keeps_files(self):
        """真实最终暂存写完首行再报IO错，无清理故障仍保原cause且归零。参数: 无。返回: None。异常: 假成功或清理残留。"""
        data=self.fixture(); primary=OSError(28,'final spool append')
        original=ResultSpool.append; fired=False
        with self.observe() as facts, ReleaseFault().installed() as fault:
            def append(spool,row):
                """先执行原append，只在本次最终spool注入。参数: 真暂存/行。返回: 原结果。异常: 主IO错。"""
                nonlocal fired
                value=original(spool,row)
                if not fired and facts.sessions and spool is facts.sessions[0]._spool:
                    fired=True
                    raise primary
                return value
            with patch.object(ResultSpool,'append',new=append):
                self.recover(data,facts,fault,primary)
            self.assertTrue(fired)


# 手动执行本文件时使用同一unittest入口，导入不运行或写数据。
if __name__=='__main__':
    unittest.main()
