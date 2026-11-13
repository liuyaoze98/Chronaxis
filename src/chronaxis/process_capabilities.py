"""按实际调度需求提示 Linux 受管工作进程的能力，不执行分析。

只在调用者确认需要受管工作进程时，打开本进程的 pidfd 并用信号0检查接口。
不创建进程、不读取日志、不改变进程组，不发送真实信号；每次探测后关闭描述符。
检查结果只描述当前环境，运行时的身份握手、权限与清理检查仍须执行。
"""

import errno
import os
import signal
import sys
import warnings


def _pidfd_group_capability():
    """用本进程的描述符检查组信号标志，不依赖内核版本字符串。

    参数: 无。返回: (状态, 原因)，状态为supported/unavailable/unknown。
    异常: 关闭描述符失败或取消原样传播；普通探测OSError保留errno为提示原因。
    """
    # 缺少Python接口即可确认当前解释器不能走既有受管进程路径。
    opener = getattr(os, 'pidfd_open', None)
    sender = getattr(signal, 'pidfd_send_signal', None)
    if opener is None or sender is None:
        return 'unavailable', 'Python未提供pidfd_open或pidfd_send_signal接口'
    descriptor = None
    try:
        try:
            descriptor = opener(os.getpid(), 0)
            # 基线只检查自己，避免把名称空间或访问错误误认为组标志不受支持。
            sender(descriptor, 0, None, 0)
        except OSError as error:
            state = 'unavailable' if error.errno == errno.ENOSYS else 'unknown'
            return state, f'pidfd基础检查失败（errno={error.errno}）'
        try:
            # Linux PIDFD_SIGNAL_PROCESS_GROUP=4；信号0不向组成员投递信号。
            sender(descriptor, 0, None, 4)
        except OSError as error:
            if error.errno in (errno.EINVAL, errno.ENOSYS):
                return 'unavailable', f'基础检查通过，但进程组标志不可用（errno={error.errno}）'
            # 当前进程可能不是组长；ESRCH或权限错误不证明内核缺少该能力。
            return 'unknown', f'进程组检查未能确认（errno={error.errno}）'
        return 'supported', ''
    finally:
        if descriptor is not None:
            os.close(descriptor)


def managed_worker_warnings(required, context):
    """为实际需要受管工作进程的计划生成当前 Linux 环境提示。

    参数: required为调度器确定的需求；context为单任务或批量入口说明。
    返回: 提示字符串tuple；不需要该路径、其他平台或探测通过时为空。
    异常: 探测资源关闭失败或取消传播；不把环境提示改成配置错误。
    """
    if not required or not sys.platform.startswith('linux'):
        return ()
    state, detail = _pidfd_group_capability()
    if state == 'supported':
        return ()
    if state == 'unavailable':
        return (f'{context}需要受管工作进程，当前Linux环境无法提供所需的pidfd进程组能力：'
                f'{detail}。请检查Python接口、内核及运行环境；配置有效不表示此环境可执行该路径。',)
    return (f'{context}需要受管工作进程，当前Linux环境尚无法确认pidfd进程组能力：'
            f'{detail}。不据此判定不支持；实际启动时仍会核验工作进程组。',)


def warn_managed_worker(required, context):
    """为没有静态报告返回值的运行准备入口发出同一环境提示。

    参数: required/context同managed_worker_warnings。返回: None。
    异常: 资源关闭或取消传播；告警遵循调用者的Python warnings策略。
    """
    for message in managed_worker_warnings(required, context):
        warnings.warn(message, RuntimeWarning, stacklevel=2)
