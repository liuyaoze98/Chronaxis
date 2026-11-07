"""取得当前这份软件的发行版本，不查询其他安装副本或业务输入。

源码检出从自身项目的pyproject.toml读取；构建包使用构建时自动生成的版本模块。
只依赖标准库且不写文件，缺失或损坏的版本资料明确报错，不回退为另一版本。
"""

from pathlib import Path
import tomllib


def software_version() -> str:
    """返回当前源码或安装包版本；版本资料缺失、项目不符或版本为空时抛RuntimeError。

    参数: 无。返回: 非空版本字符串。读取最多一份本地项目文件或本包生成模块；
    不读取全局distribution元数据，不依赖调用者工作目录，不修改任何文件。
    """
    package = Path(__file__).resolve().parent
    root = package.parent.parent
    # 只有本文件确在该项目的src/chronaxis下，才把其pyproject视为源码版本来源。
    project_file = root / 'pyproject.toml'
    if package == root / 'src' / 'chronaxis' and project_file.is_file():
        try:
            with project_file.open('rb') as handle:
                project = tomllib.load(handle)['project']
            if project['name'] != 'chronaxis':
                raise ValueError('项目名称不是chronaxis')
            version = project['version']
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError('无法从当前Chronaxis源码的pyproject.toml读取版本') from error
    else:
        # 构建器写入的模块随wheel安装；不向仓库路径或其他已安装包寻找备用版本。
        try:
            from ._build_version import VERSION
        except ImportError as error:
            raise RuntimeError('当前Chronaxis缺少对应项目版本或构建版本信息，请使用完整源码或安装包') from error
        version = VERSION
    if type(version) is not str or not version or version != version.strip():
        raise RuntimeError('当前Chronaxis版本信息必须是非空且无首尾空白的文本')
    return version
