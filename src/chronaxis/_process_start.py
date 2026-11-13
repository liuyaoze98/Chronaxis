"""Linux工作进程在业务入口前登记进程组；此模块只依赖标准库。

独立限长bytes管道只用于启动握手，GO后立即关闭；业务通信仍使用原协议。
"""
import os
import secrets
import signal
import sys
from multiprocessing.connection import wait

def registered_entry(connection, token, target, args):
    """建立独立进程组，在父进程确认身份后调用原业务入口。

    参数: connection为启动管道；token为本次随机标记；target及args为原入口与参数。
    返回: 原业务入口的返回值。
    异常: 握手、管道或原入口错误；未收到GO时不执行业务。
    """
    primary = None
    try:
        os.setsid()
        pid = os.getpid()
        connection.send_bytes(b'READY' + token + pid.to_bytes(8, 'big') + os.getpgrp().to_bytes(8, 'big'))
        if connection.recv_bytes(64) != b'PROBE' + token:
            raise ValueError('进程组登记PROBE不匹配')
        connection.send_bytes(b'ACK' + token)
        if connection.recv_bytes(64) != b'GO' + token:
            raise ValueError('进程组登记GO不匹配')
    except BaseException as error:
        primary = error
        raise
    finally:
        # GO之后立即关闭启动通道；业务通信继续使用独立控制端点。
        try:
            connection.close()
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note('启动管道关闭失败: ' + type(cleanup).__name__)
    return target(*args)

class StartupGate:
    """仅拥有启动管道；父工作槽在分配完成后立即登记本对象。"""

    def __init__(self, context):
        """创建并拥有本次启动管道。

        参数: context为multiprocessing的spawn上下文。
        返回: 新的启动资源对象。
        异常: 创建错误原样传播；未关闭端点通过process_start_cleanup_owner保留。
        """
        self.parent = self.child = None
        self.token = secrets.token_bytes(16)
        try:
            self.parent, self.child = context.Pipe()
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup:
                error.add_note('启动管道清理失败: ' + type(cleanup).__name__)
                error.process_start_cleanup_owner = self
            raise

    @property
    def closed(self):
        """查询启动管道是否全部关闭。

        参数: 无。
        返回: bool；True只表示本对象不再持有端点，不表示业务进程退出。
        异常: 无。
        """
        return self.parent is None and self.child is None

    def receive(self, process, timeout=5.0):
        """限时等待本次进程的一条有限启动消息。

        参数: process为本次Process；timeout为等待秒数。
        返回: 最多64字节的bytes。
        异常: 超时、提前退出、消息过长或断管时失败。
        """
        ready = wait((self.parent, process.sentinel), timeout=timeout)
        if self.parent in ready:
            return self.parent.recv_bytes(64)
        if process.sentinel in ready:
            raise ChildProcessError('工作进程在启动登记期间退出')
        raise TimeoutError('等待工作进程登记超时')

    def close_child(self):
        """关闭父进程持有的启动子端副本。

        参数: 无。
        返回: None。
        异常: 真实关闭错误；尚未关闭的端点仍由本对象持有。
        """
        if self.child is not None:
            try:
                self.child.close()
            finally:
                if self.child.closed:
                    self.child = None

    def close(self):
        """关闭本对象持有的两个端点。

        参数: 无。
        返回: None；重复关闭安全。
        异常: 报告首个关闭错误，其余写入notes；未关闭端点保留供恢复。
        """
        errors = []
        for name in ('child', 'parent'):
            connection = getattr(self, name)
            if connection is None:
                continue
            try:
                connection.close()
            except BaseException as error:
                errors.append(error)
            finally:
                if connection.closed:
                    setattr(self, name, None)
        if errors:
            for error in errors[1:]:
                errors[0].add_note('另一启动端点关闭失败: ' + type(error).__name__)
            raise errors[0]

def spawn_entry(context, target, args):
    """为当前平台准备原业务入口，不启动进程。

    参数: context为spawn上下文；target及args为原入口与参数。
    返回: (入口函数, 参数元组, 启动owner)；Windows原样返回入口，owner为None。
    异常: 平台或pidfd接口不支持时明确拒绝；创建启动管道失败时传播原错。
    """
    if os.name == 'nt':
        return (target, args, None)
    if not sys.platform.startswith('linux') or not hasattr(os, 'pidfd_open') or (not hasattr(signal, 'pidfd_send_signal')):
        raise NotImplementedError('进程树管理需要Windows或支持pidfd组信号的Linux 6.9及以上')
    gate = StartupGate(context)
    return (registered_entry, (gate.child, gate.token, target, args), gate)
