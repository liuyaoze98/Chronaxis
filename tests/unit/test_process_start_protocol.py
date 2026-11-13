"""启动握手失败与通道关闭失败同时发生时，保留原错误并阻止业务执行。"""
import unittest
from unittest.mock import Mock, patch
from chronaxis import _process_start


class StartupProtocolErrors(unittest.TestCase):
    """只替代本例的系统建组调用，避免在测试父进程中真实setsid。"""

    def test_handshake_error_survives_close_error(self):
        """错误PROBE仍是主异常，关闭错误作为注记，业务入口不执行。"""
        token=b'x'*16
        connection=Mock()
        connection.recv_bytes.return_value=b'wrong'
        connection.close.side_effect=OSError('close denied')
        target=Mock()
        with patch.object(_process_start.os,'setsid',create=True),patch.object(
                _process_start.os,'getpid',return_value=123),patch.object(
                _process_start.os,'getpgrp',return_value=123,create=True):
            with self.assertRaisesRegex(ValueError,'PROBE') as caught:
                _process_start.registered_entry(connection,token,target,())
        target.assert_not_called()
        self.assertTrue(any('关闭失败' in note and 'OSError' in note for note in caught.exception.__notes__))

    def test_successful_handshake_close_error_prevents_business(self):
        """完整GO之后若启动通道关闭失败，仍抛原关闭错误且不运行任务。"""
        token=b'x'*16
        connection=Mock()
        connection.recv_bytes.side_effect=[b'PROBE'+token,b'GO'+token]
        primary=OSError('close denied')
        connection.close.side_effect=primary
        target=Mock()
        with patch.object(_process_start.os,'setsid',create=True),patch.object(
                _process_start.os,'getpid',return_value=123),patch.object(
                _process_start.os,'getpgrp',return_value=123,create=True):
            with self.assertRaises(OSError) as caught:
                _process_start.registered_entry(connection,token,target,())
        self.assertIs(caught.exception,primary)
        target.assert_not_called()

if __name__=='__main__':unittest.main()
