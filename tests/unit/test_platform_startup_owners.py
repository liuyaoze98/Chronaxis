"""Linux三个真实调用方在GO前取消时，应关闭启动管道、已启动进程和本次费用。"""
import multiprocessing
import signal
import sys
import unittest
from unittest.mock import patch
from chronaxis._process_start import StartupGate


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux启动登记生命周期专项')
class StartupOwnerTests(unittest.TestCase):
    """注入发生在真实ACK收到之后，业务入口尚未获得GO。"""

    def test_cancel_after_ack_releases_all_three_callers(self):
        """batch、fast和连续CAN均保留原取消异常且回收实际自有资源。"""
        for kind in ('batch', 'fast', 'can'):
            with self.subTest(kind=kind):
                before={process.pid for process in multiprocessing.active_children()}
                budget=None
                if kind=='batch':
                    from chronaxis.batch.process_transport import ProcessWorker
                    action=ProcessWorker
                elif kind=='fast':
                    from test_fast_resource_transactions import FastResourceTransactionsTests
                    fixture=FastResourceTransactionsTests('test_pool_start_after_reserve_cancel_can_close_owned_fee')
                    fixture.setUp()
                    self.addCleanup(fixture.doCleanups)
                    owner=fixture.pool()
                    self.addCleanup(owner.close)
                    budget=owner.budget
                    action=lambda: owner.start(1)
                else:
                    from test_session_process_runtime import SessionProcessRuntimeTests
                    fixture=SessionProcessRuntimeTests('test_cancel_with_unconsumed_blocks_closes_only_owned_workers')
                    fixture.setUp()
                    self.addCleanup(fixture.doCleanups)
                    owner,budget=fixture.decoder([[(0,10)],[(1,20)]])
                    action=owner.prepare_metadata
                primary=KeyboardInterrupt('cancel before GO')
                observed=[]
                receive=StartupGate.receive

                def stop_after_ack(gate, process, timeout=5.):
                    """先收到真实ACK再抛同一取消对象；记录实际gate供关闭状态核对。"""
                    if gate not in observed:
                        observed.append(gate)
                    message=receive(gate,process,timeout)
                    if message.startswith(b'ACK'):
                        raise primary
                    return message

                with patch.object(StartupGate,'receive',stop_after_ack):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        action()
                self.assertIs(caught.exception,primary)
                self.assertTrue(observed)
                self.assertTrue(all(gate.closed for gate in observed))
                self.assertEqual({process.pid for process in multiprocessing.active_children()},before)
                if budget is not None:
                    self.assertEqual(budget.ram_bytes,0)

    def test_failed_group_close_keeps_actual_caller_owner(self):
        """三个已注册实际池在组关闭受阻时保留pidfd和费用，恢复后可关闭归零。"""
        from chronaxis.batch import process_tree
        for kind in ('batch', 'fast', 'can'):
            with self.subTest(kind=kind):
                before={process.pid for process in multiprocessing.active_children()}
                budget=None
                if kind=='batch':
                    from chronaxis.batch.process_transport import ProcessWorker
                    owner=ProcessWorker()
                    trees=[owner.tree]
                elif kind=='fast':
                    from test_fast_resource_transactions import FastResourceTransactionsTests
                    fixture=FastResourceTransactionsTests('test_pool_start_after_reserve_cancel_can_close_owned_fee')
                    fixture.setUp()
                    self.addCleanup(fixture.doCleanups)
                    owner=fixture.pool()
                    owner.start(1)
                    budget=owner.budget
                    trees=[slot['tree'] for slot in owner.slots]
                else:
                    from test_session_process_runtime import SessionProcessRuntimeTests
                    fixture=SessionProcessRuntimeTests('test_cancel_with_unconsumed_blocks_closes_only_owned_workers')
                    fixture.setUp()
                    self.addCleanup(fixture.doCleanups)
                    owner,budget=fixture.decoder([[(0,10)],[(1,20)]])
                    owner.prepare_metadata()
                    trees=[slot['tree'] for slot in owner._slots]
                self.addCleanup(owner.close)
                descriptors=[tree._fd for tree in trees]
                primary=PermissionError('group close denied')
                original=signal.pidfd_send_signal

                def deny_kill(descriptor, sig, info, flags):
                    """仅拒绝实际组的SIGKILL，能力探测与组消失检查仍走原接口。"""
                    if sig==signal.SIGKILL:
                        raise primary
                    return original(descriptor,sig,info,flags)

                with patch.object(process_tree.signal,'pidfd_send_signal',deny_kill):
                    with self.assertRaises(RuntimeError if kind=='fast' else PermissionError) as caught:
                        owner.close()
                original_error=caught.exception.__cause__ if kind=='fast' else caught.exception
                self.assertIs(original_error,primary)
                self.assertEqual([tree._fd for tree in trees],descriptors)
                self.assertTrue(all(not tree._closed for tree in trees))
                if budget is not None:
                    self.assertGreater(budget.ram_bytes,0)
                owner.close()
                self.assertTrue(all(tree._closed and tree._fd is None for tree in trees))
                self.assertEqual({process.pid for process in multiprocessing.active_children()},before)
                if budget is not None:
                    self.assertEqual(budget.ram_bytes,0)

if __name__=='__main__':unittest.main()
