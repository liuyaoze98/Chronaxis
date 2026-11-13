"""工作进程退出和已送达业务错误同时可见时，原业务错误不能被退出状态覆盖。"""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from chronaxis.fast.session import FilePool


class WorkerErrorPriorityTests(unittest.TestCase):
    """确定性排列管道与退出状态，无需依赖进程调度或sleep。"""

    def pool(self, message):
        """构造只有一个退出槽的最小pump夹具。参数: 待收消息；返回池与槽。"""
        pool=object.__new__(FilePool)
        control=Mock()
        control.recv.return_value=message
        slot=dict(control=control,data=Mock(),phase='computing',file=0,
                  process=SimpleNamespace(pid=123,exitcode=0))
        pool.slots=[slot]
        pool.specs=[dict(path='sample.asc')]
        pool.stats=dict(main_wait_seconds=0.)
        pool.check_cancel=Mock()
        pool.grant=Mock()
        return pool,slot

    def test_ready_error_precedes_exit_status(self):
        """完整error包已就绪且子进程退出时，仍报告所选文件的原错误内容。"""
        pool,slot=self.pool(('error','ValueError','时间回退'))
        with patch('chronaxis.fast.session.wait',return_value=[slot['control']]):
            with self.assertRaisesRegex(RuntimeError,'sample.asc：ValueError：时间回退'):
                pool.pump(False)
        slot['control'].recv.assert_called_once_with()

    def test_nonerror_packet_does_not_turn_exit_into_success(self):
        """即使已有EOF包，意外退出仍失败，不把半完成任务算为成功。"""
        pool,slot=self.pool(('eof',0,0,{}, {},123))
        pool.message=Mock()
        with patch('chronaxis.fast.session.wait',return_value=[slot['control']]):
            with self.assertRaisesRegex(RuntimeError,'意外退出'):
                pool.pump(False)
        pool.message.assert_not_called()

    def test_closed_pipe_preserves_exit_failure(self):
        """没有完整消息的断管仍按工作进程退出失败处理。"""
        pool,slot=self.pool(None)
        slot['control'].recv.side_effect=EOFError('closed')
        with patch('chronaxis.fast.session.wait',return_value=[slot['control']]):
            with self.assertRaisesRegex(RuntimeError,'意外退出'):
                pool.pump(False)

if __name__=='__main__':unittest.main()
