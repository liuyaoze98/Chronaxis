"""用固定原语失败核对不覆盖发布诊断；不要求Windows具备Linux目录fd。

模拟的移动不触碰文件，真实路径只用于错误定位；同时确认句柄关闭和原errno保留。
"""
import ctypes
import errno
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from chronaxis.results import platform_files


class PublicationDiagnosticTests(unittest.TestCase):
    """只注入操作系统返回值，不改变发布的目标保护和资源责任。"""

    def test_invalid_argument_keeps_errno_cause_and_closes_handles(self):
        """EINVAL说明多种可能原因，原始异常链及目标路径完整保留。

        参数: 无。返回: None。异常: 诊断或关闭行为不符时断言失败。
        """
        owner = Mock()
        owner.open.side_effect = [101, 102]
        fake_os = SimpleNamespace(name='posix', fsencode=os.fsencode, strerror=os.strerror)
        target = Path('test-publication-target').absolute()

        def fail_rename(*args):
            """模拟内核拒绝移动。参数: 原语参数。返回: -1。异常: 无。"""
            ctypes.set_errno(errno.EINVAL)
            return -1

        with patch.object(platform_files, 'os', fake_os), \
                patch.object(platform_files, 'require_publication_platform'), \
                patch.object(platform_files, '_DirectoryHandles', return_value=owner), \
                patch.object(platform_files, '_linux_rename', return_value=fail_rename):
            with self.assertRaises(OSError) as caught:
                platform_files.move_no_replace('test-publication-source', target)
        error = caught.exception
        self.assertEqual((error.errno, error.filename), (errno.EINVAL, str(target)))
        self.assertIsInstance(error.__cause__, OSError)
        self.assertEqual(error.__cause__.errno, errno.EINVAL)
        self.assertIn('可能', str(error))
        self.assertIn('路径组合', str(error))
        owner.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
