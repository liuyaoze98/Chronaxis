"""显式刷新AI发行资料的校核清单，只选指定手册提交和已登记的产品规范。

维护者在新版本校核后运行；比较基线内容，生成供源码包使用的精确文件清单。
构建wheel时不运行本工具，因此没有Git的用户仍能从sdist生成相同资料。
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tomllib
from runpy import run_path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
resource_bytes = run_path(str(ROOT / "tools/ai_resource_bytes.py"))["resource_bytes"]


def git(*args):
    """参数: args为Git只读命令参数。返回: 原始字节。异常: Git失败。"""
    return subprocess.check_output(["git", *args], cwd=ROOT)


def lock(manual, runtime, device):
    """参数: manual为参考资料版本，runtime为审核过的安装代码版本，device为实测标签。返回: 无。异常: Git或资料错误。"""
    # 解析固定源码身份，只列提交中的公开页与合成资源，不扫描用户工作目录。
    revision = git("rev-parse", "--verify", manual + "^{commit}").decode().strip()
    meta = "Docs/Current/documentation.json"
    product = json.loads(git("show", f"{revision}:{meta}"))["baseline"]
    tasks = json.loads((ROOT / "Docs/AI/tasks.json").read_bytes())["tasks"]
    names = {meta, "Docs/Current/public-api.json", "Docs/Current/examples/shared/definitions.yaml",
             "Docs/Current/examples/preset-charge-minimal.yaml",
             "Docs/Current/examples/results/conditional-energy-yaml/事件结果.csv",
             "Docs/Current/en/public-api.json",
             "Docs/Current/en/schema-translations.json"}
    # 时序教学计划和宿主程序共享本目录的ASC/DBC；打包时保持全部相对路径。
    names.update("Docs/Current/examples/temporal/" + name for name in
                 ("analysis.yaml","rolling-actual.yaml","host-analysis.yaml","host_extensions.py","meter.asc","meter.dbc"))
    names.update("Docs/Current/examples/fast/" + name for name in
                 ("analysis.yaml","analysis-blf.yaml","batch.yaml","batch-analysis.yaml","unsupported.yaml","session.yaml","session-time-order.yaml","data/power.dbc",
                  "data/run2.asc","data/run10.asc","data/single.blf"))
    names.update("Docs/AI/en/" + name for name in ("README.md", "workflow.md", "semantics.md", "tasks.json"))
    # 任务后续阅读使用同一手册正文；方向扩展示例也随专题分发。
    names.update("Docs/Current/" + language + topic + ".md"
                 for language in ("", "en/") for topic in ("aggregations", "message-calculations", "expressions", "configuration-language",
                     "results", "examples", "example-results", "fast-energy", "calculations", "continuous-files"))
    # 结果链接提供同源实际表和解释，不能只用配置文件充当输出。
    names.update("Docs/Current/examples/results/power-statistics-yaml/" + name
                 for name in ("result-summary.json", "事件结果.csv", "会话结果.csv", "窗口结果.csv", "聚合结果.csv"))
    names.update("Docs/Current/examples/" + name for name in
                 ("continuous-time-order.yaml", "message-directions.yaml", "message-energy.yaml", "readability_examples.py",
                  "example_support.py", "execution-comparison.json", "batch/energy.yaml", "batch/voltage.yaml"))
    for task in tasks:
        # 索引可直接从Docs/AI阅读；只接受约定的Current示例目录，不隐式猜测路径。
        example = task["example"]
        if not example.startswith("../Current/examples/") or ".." in example[len("../Current/"):].split("/"):
            raise ValueError("源码任务示例必须位于Current/examples：" + example)
        names.add("Docs/Current/" + example.removeprefix("../Current/"))
    paths = git("ls-tree", "-r", "--name-only", revision, "Docs/Current/examples/data",
                "Docs/Current/public-api", "Docs/Current/en/public-api", "Docs/Schema").decode().splitlines()
    names.update(p for p in paths if p.endswith((".json",".md",".csv",".asc",".blf",".dbc"))
                 and not p.startswith("Docs/Schema/README"))
    # 普通文本统一LF，已记录摘要的结果保留字节；与构建器使用同一规则。
    inputs = {}
    for name in sorted(names):
        data = git("show", f"{revision}:{name}")
        if name.startswith("Docs/Schema/") and data != git("show", f"{product}:{name}"):
            raise ValueError("规范与产品基线不一致：" + name)
        inputs[name] = sha256(resource_bytes(name, data)).hexdigest()
    # 版本号和导出名不一定反映运行语义；一次读取已审核的产品树（含指南入口）。
    runtime_rev = git("rev-parse", "--verify", runtime + "^{commit}").decode().strip()
    material = []
    with ZipFile(BytesIO(git("archive","--format=zip",runtime_rev,"src/chronaxis"))) as archive:
        for path in sorted(n for n in archive.namelist() if not n.endswith("/")):
            data = archive.read(path)
            if not path.endswith(".blf"):
                data = data.replace(b"\r\n",b"\n")
            material.append(path + "\0" + sha256(data).hexdigest() + "\n")
    runtime_hash = sha256("".join(material).encode()).hexdigest()
    version = tomllib.loads(git("show", runtime_rev+":pyproject.toml").decode())["project"]["version"]
    result = dict(device_label=device, manual_revision=revision, product_baseline=product, package_version=version,
                  runtime_revision=runtime_rev, runtime_sha256=runtime_hash, inputs=inputs)
    (ROOT/"Docs/AI/inputs.lock.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf8",newline="\n")
    # sdist精确打包含依赖的构建文件；不夹带未登记数据或Docs内的构建产物。
    resources = ["README.md", "README.en.md", "LICENSE", "Docs/Release/versioning.md", "Docs/Release/distribution.md",
                 "Docs/Release/publishing.md", "Docs/Release/publishing.en.md", "Docs/Release/release-notes-0.1.0.dev0.md",
                 "Docs/Release/release-notes-0.1.0.dev1.md", "Docs/Release/release-notes-0.1.0.dev1.en.md",
                 "Docs/Release/release-notes-0.1.0.dev2.md", "Docs/Release/release-notes-0.1.0.dev2.en.md",
                 "Docs/Release/release-notes-0.1.0.dev3.md", "Docs/Release/release-notes-0.1.0.dev3.en.md",
                 "Docs/Release/release-notes-0.1.0.dev4.md", "Docs/Release/release-notes-0.1.0.dev4.en.md",
                 "requirements/README.md", "requirements/constraints-windows-py312-min.txt",
                 "requirements/constraints-windows-py312-max.txt", "requirements/constraints-windows-py313-min.txt",
                 "requirements/constraints-windows-py313-max.txt",
                 "Docs/Release/trusted-publishing.md", "Docs/Release/trusted-publishing.en.md",
                 "Docs/Release/third-party.md", "Docs/Release/security.md", "Docs/Release/ThirdParty/highlight.js-LICENSE.txt",
                 "Docs/Release/ThirdParty/marked-LICENSE.txt", "tools/public_docs.py",
                 "tools/build_ai_guide.py", "tools/ai_resource_bytes.py", "tools/pypi_readme.py", "tools/ai_field_views.py", "tools/english_docs.py", "Docs/AI/lookup.py",
                 "Docs/AI/semantics.md", "Docs/AI/workflow.md", "Docs/AI/README.md", "Docs/AI/tasks.json",
                 "Docs/AI/run_analysis.py","Docs/AI/inputs.lock.json"]
    manifest = "".join("include " + f + "\n" for f in sorted(set(resources) | names))
    (ROOT/"MANIFEST.in").write_text(manifest, encoding="utf8",newline="\n")


if __name__ == "__main__":
    # 版本必须明确指定，不能静默使用当前工作区作为产品基线。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manual")
    parser.add_argument("--runtime", required=True, help="审核过的产品及指南入口提交")
    parser.add_argument("--device-label", required=True, choices=("home","work"))
    args = parser.parse_args()
    lock(args.manual, args.runtime, args.device_label)
