"""定位可以直接阅读的AI指南，按显式请求另存独立ZIP。

只处理公开使用说明、配置规范和合成样例，不读取用户业务输入。
默认只检查入口并返回路径，不构建、解压或复制。源码使用Docs/AI，
安装使用包内guide目录；显式导出才读取整套资料并写用户指定的新文件。
"""
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def guide_path(language="zh"):
    """定位中英文README，不写文件。

    参数: language为zh或en，默认中文。返回: README的绝对Path。
    异常: 未知语言ValueError；指南缺失FileNotFoundError。只支持普通目录安装。
    """
    if language not in ("zh", "en"):
        raise ValueError("指南语言应为zh或en")
    package = Path(__file__).resolve().parent
    installed = package / "guide"
    # 已有安装目录时不借源码补齐损坏资源；可编辑/源码布局直接使用人工入口。
    if installed.is_dir():
        root = installed
    else:
        root = package.parent.parent / "Docs/AI"
        if not (root / "inputs.lock.json").is_file():
            raise FileNotFoundError("安装包缺少用户指南，请重新安装同版本的完整wheel")
    entry = root / ("en/README.md" if language == "en" else "README.md")
    if not entry.is_file():
        raise FileNotFoundError("用户指南入口缺失：" + str(entry))
    return entry.resolve()


def _installed_archive(root):
    """按发行清单打包，忽略阅读后产生的缓存或结果。

    参数: root为包内guide目录。返回: 确定性ZIP字节。异常: 清单/资源缺失或越界。
    """
    manifest = json.loads((root / "manifest.json").read_bytes())
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in sorted({"manifest.json", *manifest["sha256"]}):
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("指南成员路径超出资料目录")
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED)
    return output.getvalue()


def export_guide(output):
    """参数: output为父目录已存在的新ZIP路径。返回: 导出路径。异常: 已有目标、缺资料或I/O失败。"""
    # 仅显式导出读取整套资源；安装目录不维护第二份ZIP副本。
    resource = Path(__file__).resolve().parent / "guide"
    if resource.is_dir():
        data = _installed_archive(resource)
    else:
        builder = Path(__file__).resolve().parents[2] / "tools/build_ai_guide.py"
        if not builder.is_file() or not (builder.parent.parent / "Docs/AI/inputs.lock.json").is_file():
            raise FileNotFoundError("安装包缺少用户指南，请重新安装同版本的完整wheel")
        data = run_path(str(builder))["build"]()
    target = Path(output)
    if any(part.casefold() == "refprojects" for part in (*target.absolute().parts, *target.resolve().parts)):
        raise ValueError("资料输出不能位于RefProjects")
    # 独占创建避免覆盖用户资料；只有自己成功创建且写入失败时才移除残件。
    stream = target.open("xb")
    try:
        with stream:
            stream.write(data)
    except BaseException as error:
        try:
            target.unlink()
        except OSError as cleanup:
            error.add_note("未能清理本次未完成的资料文件：" + str(cleanup))
        raise
    return target
