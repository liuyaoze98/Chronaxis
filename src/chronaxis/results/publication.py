"""给同次输出分配时间文件名，并在已有结果目录中不覆盖地发布。

只检查本次候选路径，不扫描旧结果。Windows rename保护竞争期间出现的文件；
临时锁仅协调使用相同时间后缀的发布者，完成清单最后移动。失败回滚本次移动，
身份发生变化的路径保留给调用者处理，不删除其他运行或外部替换的文件。
"""

from datetime import datetime
import os
from pathlib import Path


def output_root(value):
    """检查可复用结果根。参数: value路径。返回: 绝对Path。异常: 路径/平台错误。"""
    root = Path(value).absolute()
    if any(p.casefold() == 'refprojects' for p in (*root.parts, *root.resolve().parts)):
        raise ValueError('输出不能位于RefProjects')
    if os.name != 'nt':
        raise NotImplementedError('不覆盖输出发布目前只验收Windows')
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise FileExistsError('输出目标必须为目录：' + str(root))
    return root


def _identity(path):
    """取得文件身份。参数: path实际路径。返回: 设备和inode。异常: 原stat错误。"""
    value = path.lstat()
    return value.st_dev, value.st_ino


class PublicationNames:
    """独占本次时间后缀，保留有限文件映射及已移动文件身份。"""

    def __init__(self, root, names):
        """分配不冲突名称。参数: root输出根、names逻辑文件名。返回: 实例。异常: IO错。"""
        self.root = output_root(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = None
        self.moved = []
        self.completed = False
        names = tuple(names)
        if any(Path(n).name != n or n in ('.', '..') for n in names):
            raise ValueError('发布名称必须是单层文件或目录名')
        base = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S_%f')
        index = 0
        # 同刻、时钟回拨及已有输出均只影响本组候选，不遍历目录。
        while True:
            stamp = base if index == 0 else f'{base}_{index}'
            lock = self.root / ('.publishing-' + stamp)
            try:
                with lock.open('xb') as stream:
                    value = os.fstat(stream.fileno())
                    self.lock = lock
                    self.lock_identity = value.st_dev, value.st_ino
            except FileExistsError:
                index += 1
                continue
            except BaseException:
                self.close()
                raise
            try:
                self.names = {n: f'{Path(n).stem}_{stamp}{Path(n).suffix}' for n in names}
                if any(os.path.lexists(self.root / n) for n in self.names.values()):
                    self.close()
                    index += 1
                    continue
            except BaseException as error:
                try:
                    self.close()
                except BaseException as cleanup:
                    error.add_note('命名锁释放失败：' + str(cleanup))
                raise
            self.stamp = stamp
            return

    def publish(self, temporary, last, installer=None, *, only=None):
        """先移数据再移清单。参数: temporary临时目录、last完成文件、installer可选rename、only本次子集。返回: None。异常: IO/取消。"""
        move = os.rename if installer is None else installer
        # 同一报告再次写出时，既有成功移动不属于此次失败的回滚范围。
        self.moved = []
        self.completed = False
        selected = tuple(self.names) if only is None else tuple(only)
        if last not in selected or any(name not in self.names for name in selected):
            raise ValueError('发布子集必须属于本次命名并包含完成清单')
        try:
            for name in (*[n for n in selected if n != last], last):
                source, target = Path(temporary) / name, self.root / self.names[name]
                identity = _identity(source)
                # 先登记候选身份，覆盖系统调用已完成却在返回前取消的情况。
                self.moved.append((source, target, identity))
                move(source, target)
            # 释放失败也进入回滚，不能留下completed却报告本次没有发布。
            self.close()
            self.completed = True
        except BaseException as error:
            # 回滚只接管身份仍与移动前一致的对象；其他文件绝不覆盖。
            for source, target, identity in reversed(self.moved):
                try:
                    if _identity(target) == identity:
                        os.rename(target, source)
                    elif target.name == self.names[last]:
                        # 外部替换的清单可能仍引用本次数据；不能删除其依赖。
                        error.add_note('完成清单已被替换，保留已发布文件供调用者核对')
                        break
                except FileNotFoundError:
                    if target.name == self.names[last] and os.path.lexists(target):
                        self.completed = True
                        error.add_note('完成清单无法撤回，保留其全部数据文件')
                        break
                except BaseException as cleanup:
                    error.add_note('发布回滚未完成：' + str(cleanup))
                    if target.name == self.names[last]:
                        # 清单撤不回时保留它引用的全部数据，不能留下一份破损的completed。
                        self.completed = True
                        error.add_note('完成清单仍已发布，其数据文件完整保留')
                        break
            try:
                self.close()
            except BaseException as cleanup:
                error.add_note('发布锁释放失败：' + str(cleanup))
            raise

    def close(self):
        """释放本次命名锁。参数: 无。返回: None。异常: IO错，不删除其他身份的文件。"""
        if self.lock is not None:
            try:
                if _identity(self.lock) == self.lock_identity:
                    self.lock.unlink()
            except FileNotFoundError:
                pass
            self.lock = None
