# 依赖环境快照 / Dependency environment snapshots

这四份文件保存 Windows x86_64 环境的完整 `pip freeze --all`，用于复现依赖选择。它们包含构建与安装工具；`pyproject.toml` 决定正常安装的运行依赖。快照不包含 Chronaxis 自身、编辑安装或机器绝对路径。

These files preserve complete `pip freeze --all` output from four Windows x86_64 environments, including build and installation tools. Normal runtime dependencies are declared in `pyproject.toml`. No project self-pin, editable install or local path is included.

| 文件 / File | Python | NumPy | cantools | jsonschema |
|---|---|---|---|---|
| [constraints-windows-py312-min.txt](constraints-windows-py312-min.txt) | 3.12.4 | 1.26.3 | 39.4.3 | 4.25.1 |
| [constraints-windows-py312-max.txt](constraints-windows-py312-max.txt) | 3.12.4 | 2.5.4 | 45.1.2 | 4.26.0 |
| [constraints-windows-py313-min.txt](constraints-windows-py313-min.txt) | 3.13.17 | 2.1.0 | 39.4.3 | 4.25.1 |
| [constraints-windows-py313-max.txt](constraints-windows-py313-max.txt) | 3.13.17 | 2.5.4 | 45.1.2 | 4.26.0 |

最低／最高表示本轮选取的依赖组合，不是所有包在整个允许区间的数学最小值或最大值。端点组合通过测试，也不能据此宣称所有中间版本、所有交叉组合或其他平台都已测试。快照本身是环境记录，不是测试通过证明。

Minimum/maximum identify the endpoint combinations selected for this review. They do not denote every package's global minimum/maximum. Testing these combinations does not test every intermediate release, cross-combination or operating system. A snapshot records an environment, not a test result.

在包含 `pyproject.toml` 的源码根目录，可按对应 Python 解释器安装一个固定组合。例如：

From the source root containing `pyproject.toml`, select the matching Python and constraint file:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements/constraints-windows-py312-min.txt .
.\.venv\Scripts\python.exe -m pip check
```

`-c` 固定本次安装涉及包的版本，不主动安装快照中的全部工具。要复建完整工具环境，另用 `-r` 安装该文件；项目本身仍从匹配源码或 wheel 安装。Python 解释器版本、操作系统和二进制轮子来源不由 constraints 文件安装或锁定。这些文件没有发行文件哈希，不是供应链完整性锁。

`-c` constrains dependencies involved in the install; it does not install every tool in the snapshot. Use `-r` separately if reproducing the full tool environment, then install the matching project source or wheel. Constraints do not install or lock Python, the operating system or binary wheel provenance, and contain no artifact hashes.

安装范围与平台条件见[中文安装说明](../Docs/Current/installation.md) / [Installation](../Docs/Current/en/installation.md)。许可和缓存说明见[第三方依赖](../Docs/Release/third-party.md)与[安全说明](../Docs/Release/security.md)。

维护者 / Maintainer: liuyaoze.
