<a id="安装与环境"></a>
# Installation and environment

Python 3.12 and 3.13 are supported (`>=3.12,<3.14`). A local wheel does not require the source repository. The commands below use Windows; process cleanup and result publication on Linux also require the system capabilities listed on this page. Python compatibility and the wheel `any` tag alone do not establish platform support.

## Python, dependencies and platform requirements

Package metadata selects the normal runtime dependencies; you do not need to install the CAN libraries individually.

| Dependency | Allowed range |
|---|---|
| NumPy on Python 3.12 | `>=1.26.3,<2.6` |
| NumPy on Python 3.13 | `>=2.1,<2.6` |
| cantools | `>=39.4.3,<46` |
| jsonschema | `>=4.25.1,<4.27` |
| ruamel.yaml / python-can / natsort | `0.19.1` / `4.6.1` / `8.4.0`, respectively |

The source tree's `requirements/` directory records four Windows x86_64 dependency snapshots using Python 3.12.4 and 3.13.17, each with the selected lower or candidate upper dependency combination. These reproduce selected environments; an allowed range does not mean every intermediate version or cross-combination has been tested. For a wheel, follow that wheel's installation metadata. New source documentation does not add capabilities to an older published package.

When managed workers are actually started, Linux process management needs Python's `pidfd_open` and `pidfd_send_signal`, and a kernel that accepts `PIDFD_SIGNAL_PROCESS_GROUP`, introduced in Linux 6.9. Publication without overwrite needs libc's `renameat2`, actual `RENAME_NOREPLACE` support in the destination filesystem, and temporary and final files on the same filesystem. Missing capabilities cause the relevant operation to fail explicitly rather than falling back to publication that could overwrite existing files. The pidfd requirement does not apply to static validate/explain or inline calculation without managed workers; an independent batch may start a worker even with a process limit of one.

The Linux review environment is an x86_64 Docker container on WSL2 kernel `6.18.54.1-microsoft-standard-WSL2`, glibc 2.41 and Python 3.12.15, with tests on overlayfs. This environment does not cover other filesystems (including NFS, SMB and FUSE), CPU architectures, native Linux hosts or macOS. A Linux 6.9-or-newer kernel is one prerequisite, not evidence that every such system has been validated.

<a id="从-pypi-安装"></a>
## Install from PyPI

This manual covers development preview `0.1.0.dev4`. Select the version explicitly so that its configuration instructions match the installed package:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "chronaxis==0.1.0.dev4"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m chronaxis guide --language en
```

Installation obtains the runtime dependencies automatically. `guide` displays the bundled README path, which you can open directly. If you have the matching wheel or need an offline installation, use the next section.

<a id="使用本地安装包"></a>
## Install a local wheel

This manual covers 0.1.0.dev4. Obtain the matching wheel, create an isolated environment in Windows PowerShell, and substitute its actual path below. Installation includes dependencies for signal tables, CAN logs and DBC decoding. Prepare dependency packages in advance for offline installation.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev4-py3-none-any.whl"
.\.venv\Scripts\python.exe -m chronaxis guide --language en
```

Use the Python executable from this environment for subsequent commands.

Open the README at the printed path directly. No export or extraction is needed. Without a Python environment, use the files included with the [offline manual](ai-guide.md). The manual ZIP contains documentation and teaching data; install the wheel separately to execute analyses. Source installation is described below.

<a id="创建独立环境"></a>
## Install from the matching source tree

Obtain the 0.1.0.dev4 source tree, then run these Windows PowerShell commands from its root containing `pyproject.toml`. Explicitly using the virtual environment's Python avoids relying on terminal activation or changing script execution policy.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "."
.\.venv\Scripts\python.exe -m chronaxis --help
```

`pip install -e "."` installs the current source directory and CAN dependencies, so the BLF/ASC examples can run directly. `pyproject.toml` specifies NumPy, YAML parsing and CAN dependencies; the first installation needs a package index or local dependency packages. An editable install depends on the source directory. Reinstall it after moving the repository.

<a id="can输入与导出"></a>
## CAN input and export

A normal installation includes dependencies for BLF, ASC, raw CAN CSV, DBC decoding and CAN message export. Wheel metadata requires `python-can==4.6.1`, `cantools>=39.4.3,<46` and `natsort==8.4.0`. To reproduce an exact environment, choose the constraints file matching your Python version.

Decoded CSV tasks do not need a DBC. CAN libraries are imported only when required. If an older environment lacks dependencies, reinstall the complete current wheel in that environment rather than installing an arbitrary latest cantools version.

<a id="检查安装与首次运行"></a>
## Check installation and run the first example

With a wheel and the offline manual, first activate the environment containing Chronaxis, then run from the manual extraction root, which directly contains `examples`:

```powershell
python -m chronaxis validate examples/analysis.yaml
python -m chronaxis run examples/analysis.yaml --output first-result
```

With a source checkout, run from its root containing `pyproject.toml`:

```powershell
.\.venv\Scripts\python.exe -m chronaxis validate Docs/Current/examples/analysis.yaml
.\.venv\Scripts\python.exe -m chronaxis run Docs/Current/examples/analysis.yaml --output first-result
```

`first-result` can be reused; result filenames receive a timestamp suffix. Follow the [BLF/ASC quick start](quickstart.md) to check 38 J, 6 W and 38/6 W in `会话结果_<run timestamp>.csv` (session results). Later examples abbreviate the command to `chronaxis`; without activating the environment, use `.\.venv\Scripts\python.exe -m chronaxis` instead.

You can copy the offline HTML manual's complete `examples` directory elsewhere. Run its `api_example.py` with a Python environment containing Chronaxis. Reading HTML itself requires neither Python nor Node.js.

<a id="安装失败时"></a>
## Troubleshooting installation

| Symptom | Check and action |
|---|---|
| `py` or the example Python 3.12 is unavailable | Install Python 3.12 or 3.13. For 3.13 use `py -3.13`, or specify that interpreter by its full path. |
| pip cannot obtain dependencies | Check the index/network or provide local packages matching `pyproject.toml`. A failed download is not a completed installation. |
| `No module named chronaxis` | Confirm that execution uses the installation interpreter and that the editable source directory still exists. |
| `dependency_missing` or a missing CAN reader/decoder dependency | Reinstall the local `.whl` in the interpreter used for analysis; use `-e "."` only when source is available. No signal, channel or DBC change is needed. |
| Validation succeeds but results cannot be written | Read the original exception chain and platform requirements. Static validation does not publish results. |

See [troubleshooting](troubleshooting.md) for other failures. Use `pyproject.toml` as the dependency/version specification for source installation.
