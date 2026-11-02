"""将批量工作进程及其CAN读取子进程纳入同一个Windows作业对象。

主进程持有唯一作业句柄；工作进程先等待派发，归属登记成功后才运行用户计划。
关闭作业会结束残余后代，避免工作进程异常退出留下读取进程。不修改旧读取器。
"""

import ctypes
from ctypes import wintypes
import os


class _BasicLimits(ctypes.Structure):
    """对应Windows基本作业限制结构；仅设置关闭句柄时结束整个作业。"""

    _fields_ = [('per_process', ctypes.c_longlong), ('per_job', ctypes.c_longlong),
                ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                ('max_ws', ctypes.c_size_t), ('active_limit', wintypes.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                ('scheduling', wintypes.DWORD)]


class _ExtendedLimits(ctypes.Structure):
    """对应Windows扩展作业限制，未使用的资源额度保持零值。"""

    _fields_ = [('basic', _BasicLimits), ('io', ctypes.c_ulonglong * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


class ProcessTree:
    """持有一个工作进程树的关闭责任；当前公开结果发布仅支持Windows。"""

    def __init__(self, pid):
        """登记实际PID。参数: pid已启动但尚未派发的进程。返回: 新对象。异常: 平台或系统错误。"""
        if os.name != 'nt':
            raise NotImplementedError('批量进程树清理目前只验收Windows')
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        api.SetInformationJobObject.restype = wintypes.BOOL
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        api.AssignProcessToJobObject.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        self._api, self._handle = api, api.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        process = None
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE；不授予后代脱离权限。
            if not api.SetInformationJobObject(self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            process = api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE，用于作业分配。
            if not process or not api.AssignProcessToJobObject(self._handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise
        finally:
            if process:
                api.CloseHandle(process)

    def close(self):
        """关闭树句柄，终止残余后代。参数: 无。返回: None。异常: 关闭失败仍保留句柄供重试。"""
        if self._handle:
            if not self._api.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None
