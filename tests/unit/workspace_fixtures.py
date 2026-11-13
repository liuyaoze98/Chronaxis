"""为测试建立自有临时目录，不依赖其他测试先创建 work。

这里只创建指定的测试父目录和随机子目录，不清空父目录。TemporaryDirectory
沿用标准库的关闭/上下文行为；test_directory把清理登记到当前TestCase，失败时
由测试日志保存定位信息，测试数据不无限堆积。没有产品代码或全局目录初始化。
"""

from pathlib import Path
from tempfile import TemporaryDirectory as _TemporaryDirectory


def TemporaryDirectory(*args, **kwargs):
    """先建立测试父目录，再独占创建可自动清理的子目录。

    参数: args/kwargs与标准库TemporaryDirectory相同；未指定dir时沿用系统临时根。
    返回: 标准库TemporaryDirectory对象，由with或cleanup管理生命周期。
    异常: 目录创建及权限错误原样传播，不降级到其他路径。
    """
    # 仅补父目录；不删除已有内容，也不依赖测试执行顺序。
    parent = kwargs.get('dir', args[2] if len(args) > 2 else None)
    if parent is not None:
        Path(parent).mkdir(parents=True, exist_ok=True)
    return _TemporaryDirectory(*args, **kwargs)


def test_directory(owner, *args, **kwargs):
    """为原本只取目录名的unittest夹具登记自动清理。

    参数: owner为当前TestCase；其余参数同TemporaryDirectory。
    返回: 本次新建目录的字符串路径，保持mkdtemp调用侧的类型。
    异常: 创建错误原样传播；清理失败由unittest报告，不能吞掉。
    """
    directory = TemporaryDirectory(*args, **kwargs)
    owner.addCleanup(directory.cleanup)
    return directory.name
