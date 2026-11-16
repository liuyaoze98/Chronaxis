# 安装与环境

Python 支持 3.12 和 3.13（`>=3.12,<3.14`）。推荐按下文“从 PyPI 安装”；已有同版 wheel 或源码时也可以用其后的方法安装。下面的命令以 Windows PowerShell 为例；在 Linux 上使用前，请先看页末的[Linux 平台条件](#linux-platform)。

## Python 与依赖

正常安装由包元数据选择依赖，不需要分别手动安装 CAN 库。

| 依赖 | 允许范围 |
|---|---|
| NumPy，Python 3.12 | `>=1.26.3,<2.6` |
| NumPy，Python 3.13 | `>=2.1,<2.6` |
| cantools | `>=39.4.3,<46` |
| jsonschema | `>=4.25.1,<4.27` |
| ruamel.yaml / python-can / natsort | 分别为 `0.19.1` / `4.6.1` / `8.4.0` |

源码的 `requirements/` 保存 Windows x86_64 下 Python 3.12.4、3.13.17 的四个依赖环境快照，分别采用本轮最低与候选最高组合。它们用于复现已选环境；允许范围不等于所有中间版本和交叉组合都经过测试。使用 wheel 时以该 wheel 的安装元数据为准，不能把新源码说明当作旧发行包已经具备的能力。

## 从 PyPI 安装

本手册对应 `0.1.0.dev5` 开发预览版。指定版本号安装，避免使用其他版本的配置说明：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "chronaxis==0.1.0.dev5"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m chronaxis guide
.\.venv\Scripts\python.exe -m chronaxis manual
```

安装时会自动取得运行依赖。安装包附带完整的 Markdown 用户手册，包括中英文章节、公开 API 说明和全部示例：`manual` 显示手册首页路径，加 `--language en` 显示英文首页；`guide` 显示随包 AI 指南的 README 路径。两者都只显示路径，用编辑器直接打开即可阅读，不需要另外下载手册。已有同版 wheel 或需要离线安装时，使用下一节。

## 使用本地安装包

本手册对应 0.1.0.dev5。取得同版 wheel 后，在 Windows PowerShell 中创建独立环境，并把下列 wheel 路径替换为实际文件路径。普通安装包含信号表分析、CAN 日志和 DBC 解码的运行依赖；离线安装需事先备齐依赖包。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev5-py3-none-any.whl"
.\.venv\Scripts\python.exe -m chronaxis guide
.\.venv\Scripts\python.exe -m chronaxis manual
```

后续命令使用同一个虚拟环境中的 Python。

wheel 同样附带 Markdown 用户手册和 AI 指南。直接打开命令显示的路径即可阅读，无需导出或解压；没有运行环境时，可以打开[离线手册附带的指南](ai-guide.md)。手册 ZIP 是说明和教学数据，不是 Python 安装包。以下为拥有源码时的安装路径。

## 从同版源码安装

取得 0.1.0.dev5 源码后，在包含 `pyproject.toml` 的仓库根目录执行以下 Windows PowerShell 命令。显式调用虚拟环境中的 Python，无需修改脚本执行策略或依赖终端激活状态。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "."
.\.venv\Scripts\python.exe -m chronaxis --help
```

`pip install -e "."`安装当前源码目录和CAN依赖，可以直接运行本手册的BLF／ASC示例。它根据pyproject.toml安装NumPy、YAML解析及CAN依赖；首次安装需要可用的软件源或本地安装包。编辑安装仍依赖原源码目录，移动仓库后应在新位置重新安装。

## CAN输入与导出

上面的普通安装已包含BLF、ASC、原始CAN CSV、DBC解码和CAN报文导出的依赖。`python-can==4.6.1`、`cantools>=39.4.3,<46`、`natsort==8.4.0` 由 wheel 元数据统一约束；精确复现时使用与 Python 版本匹配的 constraints 文件。

普通CSV任务不需要DBC；已安装的CAN库只在实际需要时导入。若旧环境缺少依赖，使用当前完整wheel在同一环境重新安装；不要单独安装任意最新版cantools后视为已验证环境。

## 检查安装与首次运行

已从 PyPI 或 wheel 安装时，直接运行随包手册中的快速开始示例。下面第一行取得手册所在目录，后两行读取其中的配置；结果写到当前目录下的 first-result，不改动安装目录：

```powershell
$manual = Split-Path (.\.venv\Scripts\python.exe -m chronaxis manual)
.\.venv\Scripts\python.exe -m chronaxis validate "$manual\examples\analysis.yaml"
.\.venv\Scripts\python.exe -m chronaxis run "$manual\examples\analysis.yaml" --output first-result
```

<a id="find-examples"></a>

**手册中的“examples 目录”在哪里。** 手册各页说“在 examples 目录运行”时，指在下面的目录中打开终端：

| 你手里的资料 | 在哪里运行 |
|---|---|
| 从 PyPI 或 wheel 安装的程序 | 先执行 `Copy-Item -Recurse "$manual\examples" .\examples`，把随包示例复制到当前工作目录（`$manual` 用上面第一行命令取得），再进入复制出的 `examples` 目录。不要直接在安装目录里运行，否则结果会写进安装目录。 |
| 离线 HTML 手册压缩包 | 解压后根目录下的 `examples` |
| 源码仓库 | `Docs/Current/examples` |

要修改示例时，在自己的副本中修改，保持其中 data 子目录的相对位置；不要直接改安装目录里的文件。

如果使用源码仓库，则在含`pyproject.toml`的仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m chronaxis validate Docs/Current/examples/analysis.yaml
.\.venv\Scripts\python.exe -m chronaxis run Docs/Current/examples/analysis.yaml --output first-result
```

first-result可以复用，每次结果使用时间文件名。然后按[BLF／ASC快速开始](quickstart.md)核对`会话结果_<运行时间>.csv`中的38J、6W和38/6W。

<a id="run-without-activation"></a>

**手册后续命令里的 `chronaxis`。** 手册其他页面把命令简写为 `chronaxis …`，它指虚拟环境里安装的命令。有三种等价写法，任选一种：

| 写法 | 什么时候用 |
|---|---|
| `.\.venv\Scripts\chronaxis …` | 不激活虚拟环境时；在其他目录运行时，把 `.\.venv` 换成虚拟环境的完整路径 |
| `.\.venv\Scripts\python.exe -m chronaxis …` | 同上，效果相同 |
| `chronaxis …` | 已执行 `.\.venv\Scripts\Activate.ps1` 激活虚拟环境后 |

如果 PowerShell 提示“禁止运行脚本”而无法激活，直接用前两种写法即可，不需要修改执行策略。

离线HTML附带的examples目录可整体复制；使用已安装Chronaxis的Python执行其中api_example.py。HTML阅读本身不需要Python，运行分析才需要环境。

## 安装失败时

| 现象 | 检查与处理 |
|---|---|
| 找不到py或示例中的Python3.12 | 先安装Python 3.12或3.13；使用3.13时将示例改为py -3.13，或填写对应解释器的完整路径。 |
| pip无法取得依赖 | 检查软件源/网络，或准备pyproject.toml规定版本的本地安装包；不要把下载失败当作项目已安装。 |
| No module named chronaxis | 当前使用的 Python 不是安装 Chronaxis 的那个。改用虚拟环境里的 `.\.venv\Scripts\python.exe`，或按[上文](#run-without-activation)的写法运行；源码可编辑安装时，还要确认源码目录没有被移动。 |
| `dependency_missing`／缺少 CAN 读取或解码依赖 | 在运行分析的同一个 Python 环境里重新安装：PyPI 安装的执行 `pip install "chronaxis==0.1.0.dev5"`，本地 wheel 安装的重新安装该 wheel，源码安装的执行 `pip install -e "."`。这是环境缺项，无需修改信号、通道或DBC。 |
| 命令能校验但不能发布结果 | 查看原异常链和平台限制；静态校验不执行发布。 |

完整错误处理见[故障排查](troubleshooting.md)。源码安装以仓库pyproject.toml为依赖和版本依据；使用wheel时以该安装包的元数据为准。

<a id="linux-platform"></a>

## Linux 平台条件

只在 Windows 上使用的读者可以跳过本节。

实际启动受管工作进程时，Linux 的进程管理需要 Python 提供 `pidfd_open`、`pidfd_send_signal`，且内核接受 Linux 6.9 引入的 `PIDFD_SIGNAL_PROCESS_GROUP`。不覆盖发布需要 libc 提供 `renameat2`，目标文件系统实际支持 `RENAME_NOREPLACE`，且临时文件与目标位于同一文件系统。缺少这些能力时程序明确拒绝相应操作，不退回可能覆盖旧文件的发布方式。pidfd要求不适用于仅做静态validate/explain或未启动受管工作进程的内联计算；独立批量任务即使进程上限为1也可能启动工作进程。

本轮 Linux 核验环境是 x86_64 Docker 容器、WSL2 内核 `6.18.54.1-microsoft-standard-WSL2`、glibc 2.41、Python 3.12.15，测试目录位于 overlayfs。其他文件系统（包括 NFS、SMB、FUSE）、CPU 架构、原生 Linux 宿主发行版及 macOS 未由这一环境的结果覆盖。Linux 6.9 或更新内核只是所需能力的一部分，不代表所有这种系统均已验收。
