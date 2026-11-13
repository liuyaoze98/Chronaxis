"""按平台原语不覆盖地移动一个文件或目录，不复制内容或重读分析输入。"""
from functools import lru_cache
from pathlib import Path
import ctypes
import errno
import os
import sys
from .budget import _cleanup_owner

@lru_cache(maxsize=1)
def _linux_rename():
    """取得libc的正式renameat2接口。

    参数: 无。
    返回: 已声明参数类型的C函数。
    异常: libc缺少该接口时抛NotImplementedError，不退回可覆盖的rename。
    """
    try:
        function = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as error:
        raise NotImplementedError('Linux发布需要libc renameat2，不退回覆盖式rename') from error
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    return function

def require_publication_platform():
    """确认本机提供不覆盖发布的调用接口，不创建探测文件。

    参数: 无。
    返回: None。
    异常: 未支持的平台或缺少接口时抛NotImplementedError；文件系统能力在实际移动时核验。
    """
    if os.name == 'nt':
        return
    if sys.platform.startswith('linux'):
        _linux_rename()
        return
    raise NotImplementedError('不覆盖发布目前支持Windows与提供renameat2的Linux')

class _DirectoryHandles:
    """短暂持有本次移动的两个父目录fd；遵循Linux关闭后不重试同一编号。"""

    def __init__(self):
        """初始化两个空目录fd槽。

        参数: 无。
        返回: 新的目录句柄对象。
        异常: 无主动异常。
        """
        self.source = self.target = None

    @property
    def closed(self):
        """查询两个目录fd是否都已交给Linux关闭。

        参数: 无。
        返回: bool；关闭报错仍由close方法向外报告。
        异常: 无。
        """
        return self.source is None and self.target is None

    def open(self, name, path):
        """打开并登记本次移动的一侧父目录。

        参数: name为source或target内部槽名；path为父目录Path。
        返回: 实际打开的目录fd。
        异常: 链接、父目录身份替换或IO错误；已经打开的fd仍归本对象。
        """
        before = path.stat(follow_symlinks=False)
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        setattr(self, name, descriptor)
        actual = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino):
            raise OSError('发布父目录身份已变化')
        return descriptor

    def close(self):
        """对两个实际目录fd各调用一次Linux close。

        参数: 无。
        返回: None；已关闭的槽不重复操作。
        异常: 报告首个关闭错误，其余写入notes；不重试可能已被复用的fd编号。
        """
        errors = []
        for name in ('target', 'source'):
            descriptor = getattr(self, name)
            if descriptor is None:
                continue
            # Linux close报告错误前可能已释放编号，不能保存数字供第二次关闭。
            setattr(self, name, None)
            try:
                os.close(descriptor)
            except BaseException as error:
                errors.append(error)
        if errors:
            for error in errors[1:]:
                errors[0].add_note('另一发布目录fd关闭失败: ' + type(error).__name__)
            raise errors[0]

def move_no_replace(source, target):
    """在同一文件系统中不覆盖地移动一个文件或目录。

    参数: source为来源路径；target为目标路径。
    返回: None；回滚也使用同一原语。
    异常: 已有目标、跨盘或IO错误原样失败；缺少不覆盖原语时明确拒绝。
    Linux使用已打开父目录的相对名称调用RENAME_NOREPLACE，并检查父目录身份。
    单次名称移动原子，不承诺多个文件构成事务或断电后内容持久。
    """
    require_publication_platform()
    if os.name == 'nt':
        os.rename(source, target)
        return
    source, target = (Path(source).absolute(), Path(target).absolute())
    handles = _DirectoryHandles()
    try:
        source_fd = handles.open('source', source.parent)
        target_fd = handles.open('target', target.parent)
        if _linux_rename()(source_fd, os.fsencode(source.name), target_fd, os.fsencode(target.name), 1):
            code = ctypes.get_errno()
            error = OSError(code, os.strerror(code), str(target))
            if code in (errno.ENOSYS, errno.EOPNOTSUPP):
                raise NotImplementedError('当前Linux内核或文件系统不支持不覆盖发布') from error
            if code == errno.EINVAL:
                # EINVAL也可能来自无效路径组合，不能一律说文件系统不支持，更不能覆盖重试。
                raise OSError(code, '不覆盖发布被拒绝：可能是文件系统不支持RENAME_NOREPLACE，'
                              '也可能是源/目标路径组合或调用参数无效；请检查路径和文件系统能力',
                              str(target)) from error
            raise error
        # fd仍指向原目录；路径若已被替换，拒绝把新路径当作本次结果归属。
        for path, descriptor in ((source.parent, source_fd), (target.parent, target_fd)):
            actual = os.fstat(descriptor)
            current = path.stat(follow_symlinks=False)
            if (actual.st_dev, actual.st_ino) != (current.st_dev, current.st_ino):
                raise OSError('发布期间父目录被替换，保留未知对象')
    except BaseException as error:
        _cleanup_owner(handles, error, 'publication_move_cleanup_owner', '发布目录句柄')
        raise
    else:
        handles.close()
