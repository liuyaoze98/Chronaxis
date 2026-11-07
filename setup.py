"""扩展标准wheel构建：填入同版用户指南和自动生成的运行版本。

仅在构建产物中增加资源，不依赖Git或产品运行环境；sdist通过显式清单携带输入。
"""
from pathlib import Path
from runpy import run_path
import shutil
from setuptools import setup
from setuptools.command.build_py import build_py


def clean_package_output(build_lib, build_base, source_root):
    """仅删除受控构建根内的旧chronaxis包；拒绝源码、符号链接和目录越界。

    参数是setuptools明确选定的输出目录、构建根和仓库根。返回None；验证失败
    抛ValueError且不删除任何路径。兄弟包、构建根中的其他文件及源码保持不变。
    """
    source = Path(source_root).resolve()
    base_path = Path(build_base).absolute()
    library_path = Path(build_lib).absolute()
    package_path = library_path / 'chronaxis'
    # resolve之前检查目录链，避免链接把表面构建路径重定向到用户或源码目录。
    for path in {*base_path.parents, base_path, *package_path.parents, package_path}:
        if path.is_symlink() or path.is_junction():
            raise ValueError('构建输出不能包含符号链接或目录联接：'+str(path))
    base, library, package = base_path.resolve(), library_path.resolve(), package_path.resolve()
    if (base == source or source.is_relative_to(base) or base.is_relative_to(source/'src')
            or not library.is_relative_to(base) or not package.is_relative_to(library)
            or package.is_relative_to(source/'src')):
        raise ValueError('只能清理build_base内且位于源码树之外的build_lib/chronaxis')
    if not package.exists():
        return
    if not package.is_dir():
        raise ValueError('构建包路径已有非目录文件，不能删除：'+str(package))
    # 全部检查完才删除；也拒绝内部链接，不跟随链接清理其他目录。
    for path in package.rglob('*'):
        if path.is_symlink() or path.is_junction():
            raise ValueError('旧构建包包含链接，需人工核对：'+str(path))
    shutil.rmtree(package)


class GuideBuild(build_py):
    """沿用标准包发现流程，在安装目录提供同版指南及构建版本。"""

    def run(self):
        """参数: 无。返回: 无。异常: 构建失败或资料漂移时传播错误。"""
        if self.editable_mode:
            # 可编辑安装直接定位Docs/AI，不在源包内复制文档。
            super().run()
            return
        root = Path(__file__).resolve().parent
        # setuptools增量复制不会删除已移除的模块；先清理本次自有输出包再重建，
        # 同时移除旧指南/规范。dry-run不进行任何实际清理或指南写入。
        if not self.dry_run:
            clean_package_output(self.build_lib, self.get_finalized_command('build').build_base, root)
        super().run()
        if self.dry_run:
            return
        builder = run_path(str(root / "tools/build_ai_guide.py"))["build_files"]
        package = Path(self.build_lib) / "chronaxis"
        # 版本来自setuptools读取的project.version；只生成到构建目录，不另维护源字符串。
        version = self.distribution.get_version()
        (package / '_build_version.py').write_text(
            '\"\"\"构建时从发行元数据生成的版本，勿手工修改。\"\"\"\n'
            + 'VERSION = ' + repr(version) + '\n', encoding='utf8')
        # Docs/Schema是唯一维护源；安装包使用同版普通JSON资源，无网络取规范。
        schemas = package / "schemas"
        schemas.mkdir(parents=True, exist_ok=True)
        for name in ('analysis.schema.json', 'batch-v1.schema.json'):
            (schemas / name).write_bytes((root / 'Docs' / 'Schema' / name).read_bytes())
        # 清除旧构建留下的单个压缩资源，避免同时安装重复指南。
        obsolete = package / "user-guide.zip"
        if obsolete.is_file():
            obsolete.unlink()
        for name, data in builder().items():
            target = package / "guide" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


# PyPI需要网页链接；源码README仍可在本地按相对路径阅读。
root = Path(__file__).resolve().parent
readme = run_path(str(root / "tools/pypi_readme.py"))["build"](root)
setup(cmdclass={"build_py": GuideBuild}, long_description=readme,
      long_description_content_type="text/markdown")
