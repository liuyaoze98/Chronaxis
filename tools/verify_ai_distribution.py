"""隔离检验用户交付物：由已提交产品树及显式指南文件构建sdist，再离线构建wheel。

参数给出新的工作目录；运行依赖由调用者的Python构建环境准备。忽略工作区非本任务改动。
返回wheel和导出ZIP，失败保留暂存供定位；不改产品/历史资源或安装到用户环境。
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def run(argv, cwd, env=None):
    """参数: argv命令列表、cwd目录、env环境。返回: 无。异常: 子进程非零退出。"""
    # 全部命令用参数列表，不从文本拼接shell脚本。
    subprocess.run(argv, cwd=cwd, env=env, check=True)


def verify(directory, public_source=None):
    """参数: directory为全新工作目录。返回: 已验证wheel位置。异常: 构建、校验或路径错误。"""
    directory.mkdir(parents=True, exist_ok=False)
    stage = directory / "source"
    archive = directory / "committed.zip"
    # 仅取已提交产品代码，避免将工作区未跟踪的冲突副本及用户改动打入wheel。
    if public_source is None:
        run(["git","archive","--format=zip","-o",str(archive),"HEAD","src/chronaxis"], ROOT)
        with ZipFile(archive) as source:
            source.extractall(stage)
        inputs = ROOT
    else:
        inputs = Path(public_source).resolve()
        if any((inputs/name).exists() for name in ('.git', 'RefProjects', 'work')):
            raise ValueError('公开输入必须是无Git、历史项目和工作目录的清洁导出')
        shutil.copytree(inputs/'src', stage/'src')
    files = ["setup.py","pyproject.toml","MANIFEST.in","src/chronaxis/cli.py","src/chronaxis/user_guide.py"]
    files += [line.removeprefix("include ") for line in (inputs/"MANIFEST.in").read_text(encoding="utf8").splitlines()]
    # 只有发行清单内资料及本功能明确的两个产品文件允许覆盖冻结副本。
    for name in files:
        dest = stage / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(inputs / name, dest)
    env = os.environ.copy()
    env["PIP_NO_INDEX"] = "1"
    env["PIP_NO_CACHE_DIR"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    local_tmp = directory / "tmp"
    local_tmp.mkdir()
    env.update(TEMP=str(local_tmp), TMP=str(local_tmp), TMPDIR=str(local_tmp))
    # 从sdist构建才会暴露MANIFEST缺项；不安装到项目解释器。
    run([sys.executable,"-B","setup.py","sdist","--dist-dir",str(directory)], stage, env)
    source_dist, = directory.glob("*.tar.gz")
    run([sys.executable,"-B","-m","pip","wheel","--no-index","--no-deps","--no-build-isolation",
         "-w",str(directory),str(source_dist)], directory, env)
    wheel, = directory.glob("*.whl")
    target = directory / "installed"
    run([sys.executable,"-B","-m","pip","install","--no-index","--no-deps","--target",str(target),
         str(wheel)], directory, env)
    # 只为这次无依赖的guide命令暴露新安装包；执行目录不含源码检出。
    clean = dict(env, PYTHONPATH=str(target), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    exported = directory / "installed.zip"
    entry = Path(subprocess.check_output([sys.executable,"-B","-m","chronaxis","guide"],
                                         cwd=directory,env=clean,text=True).strip())
    if not entry.is_file() or not entry.is_relative_to(target):
        raise AssertionError("安装后默认指南路径不可直接阅读")
    run([sys.executable,"-B","-m","chronaxis","guide","--output",str(exported)], directory, clean)
    duplicate = subprocess.run([sys.executable,"-B","-m","chronaxis","guide","--output",str(exported)],
                               cwd=directory,env=clean,capture_output=True)
    if duplicate.returncode != 1:
        raise AssertionError("重复导出未拒绝")
    with ZipFile(wheel) as contents:
        if "chronaxis/user-guide.zip" in contents.namelist():
            raise AssertionError("安装包仍含重复ZIP资源")
        with ZipFile(exported) as guide:
            for name in guide.namelist():
                if contents.read("chronaxis/guide/" + name) != guide.read(name):
                    raise AssertionError("直接阅读文件与可选导出不一致：" + name)
    with ZipFile(exported) as contents:
        manifest = json.loads(contents.read("manifest.json"))
        if manifest["package_version"] not in wheel.name or contents.testzip() is not None:
            raise ValueError("安装包版本或资料校验失败")
    return wheel


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--public-source", type=Path)
    args = parser.parse_args()
    print(verify(args.directory.resolve(), args.public_source))
