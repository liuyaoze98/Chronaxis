<a id="安装与环境"></a>
# Installation and environment

A local wheel can be installed without the source repository. Python must be >=3.12 and <3.13; the verified environment is Windows with Python 3.12.4. Use Windows for writing final result directories: the current implementation publishes a complete directory atomically without overwriting an existing target. Other operating systems have not been validated for this operation.

<a id="已取得安装包"></a>
## Install a wheel

In your Python 3.12 virtual environment, replace the filename below with the wheel you received. A normal installation includes the dependencies for signal tables, CAN logs and DBC decoding. Prepare the dependency packages in advance for offline installation.

```powershell
python -m pip install ".\chronaxis-0.1.0.dev0-py3-none-any.whl"
python -m chronaxis guide --language en
```

Open the README at the printed path directly. No export or extraction is needed. Without a Python environment, use the files included with the [offline manual](ai-guide.md). The manual ZIP contains documentation and teaching data; install the wheel separately to execute analyses. Source installation is described below.

<a id="创建独立环境"></a>
## Create an isolated environment

Run these Windows PowerShell commands from the repository root. Explicitly using the virtual environment's Python avoids relying on terminal activation or changing script execution policy.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "."
.\.venv\Scripts\python.exe -m chronaxis --help
```

`pip install -e "."` installs the current source directory and CAN dependencies, so the BLF/ASC examples can run directly. `pyproject.toml` specifies NumPy, YAML parsing and CAN dependencies; the first installation needs a package index or local dependency packages. An editable install depends on the source directory. Reinstall it after moving the repository.

<a id="can输入与导出"></a>
## CAN input and export

A normal installation includes dependencies for BLF, ASC, raw CAN CSV, DBC decoding and CAN message export. The declared and verified versions are `python-can==4.6.1`, `cantools==39.4.3` and `natsort==8.4.0`, constrained by wheel metadata. The older `chronaxis[can]` spelling remains compatible and installs the same dependencies.

Decoded CSV tasks do not need a DBC. CAN libraries are imported only when required. If an older environment lacks dependencies, reinstall the complete current wheel in that environment rather than installing an arbitrary latest cantools version.

<a id="检查安装与首次运行"></a>
## Check installation and run the first example

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m chronaxis validate Docs/Current/examples/analysis.yaml
.\.venv\Scripts\python.exe -m chronaxis run Docs/Current/examples/analysis.yaml --output first-result
```

`first-result` must not already exist. Follow the [BLF/ASC quick start](quickstart.md) to check 38 J, 6 W and 38/6 W in `会话结果.csv` (session results). Later examples abbreviate the command to `chronaxis`; without activating the environment, use `.\.venv\Scripts\python.exe -m chronaxis` instead.

You can copy the offline HTML manual's complete `examples` directory elsewhere. Run its `api_example.py` with a Python environment containing Chronaxis. Reading HTML itself requires neither Python nor Node.js.

<a id="安装失败时"></a>
## Troubleshooting installation

| Symptom | Check and action |
|---|---|
| `py` or Python 3.12 is unavailable | Install the supported Python version, or replace `py -3.12` with the full path to a known Python 3.12 executable. |
| pip cannot obtain dependencies | Check the index/network or provide local packages matching `pyproject.toml`. A failed download is not a completed installation. |
| `No module named chronaxis` | Confirm that execution uses the installation interpreter and that the editable source directory still exists. |
| `dependency_missing` or a missing CAN reader/decoder dependency | Reinstall the local `.whl` in the interpreter used for analysis; use `-e "."` only when source is available. No signal, channel or DBC change is needed. |
| Validation succeeds but results cannot be written | Read the original exception chain and platform requirements. Static validation does not publish results. |

See [troubleshooting](troubleshooting.md) for other failures. Use `pyproject.toml` as the dependency/version specification for source installation.
