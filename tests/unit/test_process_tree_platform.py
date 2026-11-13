"""Linux真实pidfd注册与进程树清理；只观察本例创建并获知PID的子孙。"""
import errno
import multiprocessing as mp
import os
import signal
import sys
import time
import unittest
from unittest.mock import patch
from chronaxis._process_start import spawn_entry,StartupGate
from chronaxis.batch.process_tree import ProcessTree


def idle():
    """测试自己的持续运行进程。参数无；无正常返回，等待本例关闭。"""
    while True:time.sleep(.05)


def descendants(pipe,root_exit):
    """创建本组子孙并报告PID。参数: 私有端点与根退出开关；不接收用户数据。"""
    child=os.fork()
    if child==0:
        grandchild=os.fork()
        if grandchild==0:
            pipe.send(("grandchild",os.getpid()));pipe.close();signal.signal(signal.SIGTERM,signal.SIG_IGN);idle()
        pipe.send(("child",os.getpid()));pipe.close();signal.signal(signal.SIGTERM,signal.SIG_IGN);idle()
    pipe.send(("root",os.getpid()));pipe.close()
    if not root_exit:idle()


def broken_registration(pipe,token,mode):
    """只测试本例握手早退/损坏，绝不运行业务。参数含测试模式；返回None或原管道错误。"""
    try:
        if mode!="false_group":os.setsid()
        if mode=="before_ready":return
        pid=os.getpid();pipe.send_bytes(b"READY"+token+pid.to_bytes(8,"big")+pid.to_bytes(8,"big"))
        if mode=="after_ready":return
        if pipe.recv_bytes(64)!=b"PROBE"+token:return
        if mode=="timeout":idle()
        pipe.send_bytes(b"ACK"+(b"x"*16 if mode=="bad_ack" else token))
        if mode=="after_ack":return
        try:pipe.recv_bytes(64)
        except EOFError:pass
    finally:pipe.close()


def alive(pid):
    """检查本例明确得到的PID，僵尸不算仍执行。返回bool；仅缺路径视为已退出。"""
    try:
        with open(f"/proc/{pid}/stat") as stream:return stream.read().split(") ",1)[1].split()[0]!="Z"
    except FileNotFoundError:return False


@unittest.skipUnless(sys.platform.startswith("linux"),"Linux pidfd组接口专项")
class LinuxProcessTreeTests(unittest.TestCase):
    """验证原组身份、后代退出和失败责任；兄弟进程不得被误杀。"""

    def test_running_and_reaped_root_close_descendants(self):
        """活组长或已回收组长的子孙均关闭；同父另一个组仍存活。"""
        context=mp.get_context("spawn")
        for root_exit in (False,True):
            with self.subTest(root_exit=root_exit):
                sibling=context.Process(target=idle);sibling.start();parent,child=context.Pipe()
                target,args,gate=spawn_entry(context,descendants,(child,root_exit));process=context.Process(target=target,args=args);tree=None
                try:
                    process.start();child.close();tree=ProcessTree(process.pid,registration=gate,process=process);gate.close()
                    pids={}
                    for _ in range(3):
                        self.assertTrue(parent.poll(5));kind,pid=parent.recv();pids[kind]=pid
                    if root_exit:process.join(5);self.assertEqual(process.exitcode,0)
                    tree.close();self.assertTrue(tree._closed);self.assertFalse(any(alive(pid) for pid in pids.values()))
                    self.assertTrue(sibling.is_alive());tree.close()
                finally:
                    gate.close()
                    if tree is not None:tree.close()
                    if process.is_alive():process.kill()
                    process.join(5);process.close();parent.close()
                    sibling.terminate();sibling.join(5);sibling.close()

    def test_early_exit_and_invalid_ack_never_signal_unconfirmed_fd(self):
        """READY前后退出及错误ACK不允许向未确认fd发组信号。"""
        context=mp.get_context("spawn")
        for mode in ("before_ready","after_ready","bad_ack","timeout","false_group"):
            with self.subTest(mode=mode):
                gate=StartupGate(context);process=context.Process(target=broken_registration,args=(gate.child,gate.token,mode));tree=None;calls=[]
                original=signal.pidfd_send_signal;receive=gate.receive
                def observed(*args,**kwargs):
                    """记录本例真实系统信号调用，不替代内核行为。返回原调用结果；错误原样传播。"""
                    calls.append(args);return original(*args,**kwargs)
                ready=[False]
                def bounded(process,timeout=5.):
                    """READY仍限5秒，后续未响应例限0.1秒。返回原消息；原超时传播。"""
                    result=receive(process,.1 if ready[0] else timeout);ready[0]=True;return result
                try:
                    process.start()
                    with patch.object(signal,"pidfd_send_signal",observed),patch.object(gate,"receive",bounded):
                        with self.assertRaises((ChildProcessError,EOFError,OSError,ValueError,TimeoutError)) as caught:
                            tree=ProcessTree(process.pid,registration=gate,process=process)
                    tree=getattr(caught.exception,"process_tree_cleanup_owner",None)
                    self.assertEqual(calls,[])
                finally:
                    gate.close()
                    if tree is not None:tree.close()
                    if process.is_alive():process.kill()
                    process.join(5);process.close()

    def test_failed_group_signal_keeps_owned_descriptor_for_retry(self):
        """强制关闭被拒时不能退掉树责任；同一pidfd恢复后关闭原组。"""
        context=mp.get_context("spawn");target,args,gate=spawn_entry(context,idle,());process=context.Process(target=target,args=args);tree=None
        try:
            process.start();tree=ProcessTree(process.pid,registration=gate,process=process);gate.close();descriptor=tree._fd
            with patch.object(signal,"pidfd_send_signal",side_effect=PermissionError("injected")):
                with self.assertRaises(PermissionError):tree.close()
            self.assertFalse(tree._closed);self.assertEqual(tree._fd,descriptor);self.assertTrue(process.is_alive())
            tree.close();self.assertTrue(tree._closed);self.assertFalse(process.is_alive())
        finally:
            gate.close()
            if tree is not None:tree.close()
            if process.is_alive():process.kill()
            process.join(5);process.close()

    def test_released_pidfd_error_never_retries_reused_number(self):
        """真实pidfd关闭后即使报告错误，也不能再次关闭已复用的文件编号。"""
        from chronaxis.batch import process_tree
        tree = object.__new__(ProcessTree)
        tree._linux = True
        tree._fd = os.pidfd_open(os.getpid())
        tree._confirmed = False
        tree._closed = False
        tree._process = None
        close = os.close
        reused = []

        def close_then_error(descriptor):
            """真实close后用/dev/null复用该编号并报错；不向任何进程发送信号。"""
            close(descriptor)
            replacement = os.open(os.devnull, os.O_RDONLY)
            if replacement != descriptor:
                os.dup2(replacement, descriptor)
                close(replacement)
            reused.append(descriptor)
            raise OSError("pidfd close failed after release")

        try:
            with patch.object(process_tree.os, "close", close_then_error):
                with self.assertRaisesRegex(OSError, "after release"):
                    tree.close()
            self.assertTrue(tree._closed)
            self.assertIsNone(tree._fd)
            tree.close()
            os.fstat(reused[0])
        finally:
            if reused:
                close(reused[0])
            elif tree._fd is not None:
                close(tree._fd)

    def test_unsupported_group_flag_does_not_dispatch_business(self):
        """内核拒绝组标志时明确失败；不退回裸PID杀组或执行业务入口。"""
        context = mp.get_context("spawn")
        target, args, gate = spawn_entry(context, idle, ())
        process = context.Process(target=target, args=args)
        calls = []

        def unsupported(descriptor, sig, info, flags):
            """仅能力探测返回EINVAL，并保存实际请求；其他信号调用会使断言失败。"""
            calls.append((sig, flags))
            raise OSError(errno.EINVAL, "group flag unavailable")

        try:
            process.start()
            with patch.object(signal, "pidfd_send_signal", unsupported):
                with self.assertRaisesRegex(NotImplementedError, "Linux 6.9") as caught:
                    ProcessTree(process.pid, registration=gate, process=process)
            self.assertEqual(calls, [(0, 4)])
            self.assertFalse(hasattr(caught.exception, "process_tree_cleanup_owner"))
            gate.close()
            process.join(5)
            self.assertFalse(process.is_alive())
            self.assertNotEqual(process.exitcode, 0)
        finally:
            gate.close()
            if process.is_alive():
                process.kill()
            process.join(5)
            process.close()

if __name__=="__main__":unittest.main()
