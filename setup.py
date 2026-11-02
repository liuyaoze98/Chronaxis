"""扩展标准wheel构建：从与离线手册相同的资料生成器填入用户指南。

仅在构建产物中增加资源，不依赖Git或产品运行环境；sdist通过显式清单携带输入。
"""
from pathlib import Path
from runpy import run_path
from setuptools import setup
from setuptools.command.build_py import build_py


class GuideBuild(build_py):
    """沿用标准包发现流程，在安装目录提供可直接打开的同版指南文件。"""

    def run(self):
        """参数: 无。返回: 无。异常: 构建失败或资料漂移时传播错误。"""
        # 先复制包，再写入普通文档；不要求读者先生成或解压资源。
        super().run()
        if self.editable_mode:
            # 可编辑安装直接定位Docs/AI，不在源包内复制文档。
            return
        root = Path(__file__).resolve().parent
        builder = run_path(str(root / "tools/build_ai_guide.py"))["build_files"]
        package = Path(self.build_lib) / "chronaxis"
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
