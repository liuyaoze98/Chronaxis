"""只删除本次明确新建的私有目录，拒绝路径被重定向或目录被替换。"""

from pathlib import Path
import shutil


def directory_identity(path):
    """登记刚创建目录的实际位置和文件系统身份，不枚举内容。

    参数: 新建私有Path。返回: (resolved_path, device, inode)。异常: IO或链接根拒绝。
    """
    path = Path(path)
    if path.is_symlink() or path.is_junction() or not path.is_dir():
        raise ValueError('清理登记只允许实际新建的普通目录')
    stat = path.stat(follow_symlinks=False)
    return path.resolve(), stat.st_dev, stat.st_ino


def remove_owned_directory(path, identity):
    """核对原实际路径和身份后删除自有目录；不存在时幂等，失败可重试。

    参数: 原路径及创建时登记identity。返回: None。异常: 重定向/替换或IO错误。
    shutil只删除目录内链接自身，不沿子目录链接删除外部内容；不接收未登记目录。
    """
    path = Path(path)
    if path.is_symlink() or path.is_junction():
        raise ValueError('自有目录变成链接，拒绝清理')
    if not path.exists():
        return
    if identity is None or directory_identity(path) != identity:
        raise ValueError('自有目录实际位置或身份已变化，拒绝清理')
    shutil.rmtree(path)
