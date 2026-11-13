"""管理本次工作进程树；Windows使用作业对象，Linux使用已确认身份的pidfd进程组。

父进程持有本次任务的作业句柄或pidfd；工作进程完成登记后才运行用户计划。
关闭时回收本任务的剩余后代，不扫描或接管其他任务的进程。
"""

import ctypes
from ctypes import wintypes
import os
import signal
import sys
from time import monotonic, sleep

from ..results.budget import _cleanup_owner


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
    """持有一个工作进程树的关闭责任；Linux在GO前完成双向身份核验。"""

    def __init__(self, pid, *, registration=None, process=None):
        """登记实际PID。Windows沿原pid接口；Linux另需registration和借用process。返回新对象；平台、握手或系统错误保原异常。"""
        self._linux = sys.platform.startswith('linux')
        if self._linux:
            self._register_linux(pid, registration, process)
            return
        if os.name != 'nt':
            raise NotImplementedError('进程树管理需要Windows或Linux 6.9及以上')
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
        # 两个实际句柄先登记；构造尚未返回也必须能从原异常恢复关闭。
        self._api, self._handle, self._process_handle = api, None, None
        self._closed = False
        try:
            self._handle = api.CreateJobObjectW(None, None)
            if not self._handle:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE；不授予后代脱离权限。
            if not api.SetInformationJobObject(self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._process_handle = api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE。
            if not self._process_handle or not api.AssignProcessToJobObject(self._handle, self._process_handle):
                raise ctypes.WinError(ctypes.get_last_error())
            # 登记成功后只关本次借助的进程句柄，保留作业句柄直到工作池结束。
            self._close_process_handle()
        except BaseException as error:
            _cleanup_owner(self, error, 'process_tree_cleanup_owner', 'Windows进程树构造')
            raise

    def _register_linux(self, pid, registration, process):
        """通过本次进程的双向握手登记pidfd。

        参数: pid为实际PID；registration拥有启动通道；process为借用的Process。
        返回: None；能力与身份核验完成后才发GO。
        异常: 无效身份、握手或系统错误原样传播；未确认fd只关闭，不发送组信号。
        """
        self._fd = None
        self._confirmed = False
        self._closed = False
        self._process = process
        try:
            if registration is None or process is None or type(pid) is not int or (pid != process.pid) or (pid <= 0):
                raise ValueError('Linux进程树只能登记本次启动握手对应的Process')
            registration.close_child()
            expected = b'READY' + registration.token + pid.to_bytes(8, 'big') + pid.to_bytes(8, 'big')
            if registration.receive(process) != expected or pid == os.getpgrp():
                raise ValueError('工作进程组READY身份不匹配')
            # 只打开临时fd；收到打开之后的ACK以前不能向该fd发送组信号。
            self._fd = os.pidfd_open(pid)
            registration.parent.send_bytes(b'PROBE' + registration.token)
            if registration.receive(process) != b'ACK' + registration.token:
                raise ValueError('工作进程组ACK身份不匹配')
            if os.getpgid(pid) != pid or pid == os.getpgrp():
                raise ValueError('实际工作进程未建立独立进程组')
            try:
                signal.pidfd_send_signal(self._fd, 0, None, 4)
            except OSError as error:
                if error.errno in (22, 38):
                    raise NotImplementedError('并行任务需要Linux 6.9及以上的pidfd进程组信号') from error
                raise
            # ACK证明原worker仍活着，实际组身份和内核能力通过后才授予业务执行。
            self._confirmed = True
            registration.parent.send_bytes(b'GO' + registration.token)
        except BaseException as error:
            _cleanup_owner(self, error, 'process_tree_cleanup_owner', 'Linux进程树登记')
            raise

    def _close_linux(self):
        """关闭已确认的进程组并核对实际消失。

        参数: 无。
        返回: None；未确认fd仅关闭。
        异常: 组未消失或信号失败时保留责任；Linux close本身报错也不重试已释放编号。
        """
        if self._fd is None:
            self._process = None
            self._closed = True
            return
        if self._confirmed:
            try:
                signal.pidfd_send_signal(self._fd, signal.SIGKILL, None, 4)
            except ProcessLookupError:
                pass
            # 回收本次组长僵尸；不接管或扫描其他进程。
            process = self._process
            if process is not None and (not getattr(process, '_closed', False)):
                process.join(timeout=5)
                if process.is_alive():
                    raise TimeoutError('进程树组长尚未退出')
            deadline = monotonic() + 5
            while True:
                try:
                    signal.pidfd_send_signal(self._fd, 0, None, 4)
                except ProcessLookupError:
                    break
                if monotonic() >= deadline:
                    raise TimeoutError('进程组尚未全部退出，保留清理责任')
                sleep(0.01)
        # 组已不存在；Linux close可能先释放编号再报错，因此只调用一次。
        descriptor = self._fd
        self._fd = None
        self._process = None
        self._closed = True
        os.close(descriptor)

    def _close_process_handle(self):
        """关闭登记期间真实打开的进程句柄。参数: 无。返回: None。异常: 失败仍保留句柄。"""
        if self._process_handle:
            if not self._api.CloseHandle(self._process_handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._process_handle = None

    def close(self):
        """关闭本次平台资源；Windows失败保留实际句柄，Linux只重试尚未结束的组。

        参数: 无。返回: None；重复关闭安全。异常: 第一个关闭错误，其余写入notes。
        Windows作业关闭后结束残余后代；登记句柄失败仍尝试结束作业。
        Linux组确认消失后只close一次pidfd；错误向上传播，不重试已释放编号。
        """
        if self._closed:
            return
        if getattr(self, '_linux', False) is True:
            self._close_linux()
            return
        errors = []
        try:
            self._close_process_handle()
        except BaseException as error:
            errors.append(error)
        if self._handle:
            try:
                if not self._api.CloseHandle(self._handle):
                    raise ctypes.WinError(ctypes.get_last_error())
                self._handle = None
            except BaseException as error:
                errors.append(error)
        self._closed = not self._handle and not self._process_handle
        if errors:
            for error in errors[1:]:
                errors[0].add_note('Windows进程树另有句柄关闭失败: ' + type(error).__name__)
            raise errors[0]
