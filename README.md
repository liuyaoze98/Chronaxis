# Chronaxis

**简体中文** | [English](README.en.md)

[项目仓库](https://github.com/liuyaoze98/Chronaxis) · [问题反馈](https://github.com/liuyaoze98/Chronaxis/issues)

## 为什么建立 Chronaxis

工程数据分析中，许多工作会反复出现：更换一批日志、调整一个判断条件、重新计算一段过程的指标。随着车型、试验项目和文件格式增加，零散脚本往往积累了重复的读取与计算逻辑，也让分析规则越来越难以复用和维护。

Chronaxis 希望把日志读取、条件筛选和指标计算整理成可复用的 Python 库。工程人员可以用配置描述分析任务，开发者也可以把同一套分析流程集成到已有程序中，减少因更换数据或调整规则而重复编写脚本的工作。

## 希望应用在何处

项目起源于汽车与动力电池试验中的日志分析需求，希望用于试验结果整理、故障过程定位、不同批次的对比，以及自动化测试后的指标计算。随着输入格式和分析方法的扩展，也希望将这些方法用于其他设备的测试数据分析。

## 当前可以完成什么

- 查找连续满足条件的时间段，例如电流超过指定值并持续一分钟。
- 识别报警的开始与解除、请求与响应、等待超时等过程。
- 对选中的时间段计算积分、持续时间和统计值，或比较事件前后的数值变化。
- 将连续记录的多个文件作为一段数据分析；对独立试验分别运行并汇总结果。
- 输出可读结果表，并按需要导出事件附近的原始报文片段。
- 通过 YAML／JSON 配置运行，或使用 Python API 接入其他程序。

| 输入 | 使用方式 |
|---|---|
| BLF、ASC、原始报文 CSV | 使用对应 DBC 取得信号；原始报文 CSV 还需声明列和格式 |
| 已解码信号 CSV | 按时间列与信号列配置，无需 DBC |
| 内存数据 | 将程序中已有的信号值和时间通过 Python API 传入 |

## 安装与运行环境

当前版本为 **0.1.0.dev2**，属于开发预览版。请使用 **Windows 和 Python 3.12** 安装运行。预览版的接口和配置可能调整，版本命名见[版本规则](Docs/Release/versioning.md)，从旧版升级前请阅读[本版说明](Docs/Release/release-notes-0.1.0.dev2.md)。

从 PyPI 安装：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "chronaxis==0.1.0.dev2"
.\.venv\Scripts\python.exe -m chronaxis --help
```

从源码安装时，在包含 `pyproject.toml` 的仓库根目录执行 `python -m pip install .`。若取得的是发行 wheel，将上面的安装命令替换为：

```powershell
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev2-py3-none-any.whl"
```

安装时会自动安装 CAN 读取、DBC 解码等所需依赖。离线安装请提前准备依赖包，具体方法见[安装说明](Docs/Current/installation.md)。

## 快速开始：用配置运行

下面使用仓库自带的**合成 ASC 与 DBC** 演示能量计算：先找出状态等于 `0x2` 且电流至少为 `10A`、连续超过 `60s` 的时间段，再对每段内的电流与电压乘积求积分，换算为 `kWh`。

示例所需的配置和数据均已随源码提供：

| 文件 | 用途 |
|---|---|
| [conditional-energy.yaml](Docs/Current/examples/conditional-energy.yaml) | 完整可运行配置，包含信号绑定、条件、持续门槛及积分 |
| [part-1.asc](Docs/Current/examples/data/can/conditional-energy/part-1.asc)、[part-2.asc](Docs/Current/examples/data/can/conditional-energy/part-2.asc) | 两卷连续报文 |
| [signals.dbc](Docs/Current/examples/data/can/conditional-energy/signals.dbc) | 配套信号定义 |

保留源码目录结构，在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m chronaxis validate Docs/Current/examples/conditional-energy.yaml
.\.venv\Scripts\python.exe -m chronaxis run Docs/Current/examples/conditional-energy.yaml --output result-cli
```

`result-cli` 可以重复使用，每次文件名自动增加时间后缀。命令行中的路径相对当前工作目录；配置内部的数据路径相对配置文件所在目录。

本例实际运行得到一个合格事件，`result-cli/事件结果_<timestamp>.csv` 中的关键结果为：

| 开始时间（s） | 结束时间（s） | energy_kwh（kWh） | energy_kwh：状态 |
|---|---|---|---|
| 61 | 122 | 0.06777777777777777 | 完整 |

第一段恰好持续 60 秒，不满足“超过”；第二段跨越两个文件，持续 61 秒。该段功率为 4000 W，因此能量为 `4000 × 61 ÷ 3600000` kWh。积分包括合格区间最初的 60 秒。

用于自己的日志时，请根据 DBC 和实际分析目标修改信号绑定、条件与时间设置。具体方法和输出解释见[完整教程](Docs/Current/conditional-energy.md)。

## 快速开始：调用 Python API

下面用同一份配置执行同一个任务。将代码保存为仓库根目录中的 `example_energy.py`，使用上述虚拟环境运行；`result-python` 同样可以重复使用。

```python
from contextlib import closing
from chronaxis import AnalysisRunner, load_analysis_plan

if __name__ == "__main__":
    plan = load_analysis_plan("Docs/Current/examples/conditional-energy.yaml")
    with AnalysisRunner().run(plan) as result:
        with closing(result.iter_calculations()) as rows:
            for row in rows:
                print(row.calculation_id, row.value, row.unit, row.status)
        result.write("result-python")
```

执行：

```powershell
.\.venv\Scripts\python.exe example_energy.py
```

它会打印 `energy_kwh` 的数值、单位和状态，并写出与命令行示例相同的结果。请保留 `if __name__ == "__main__":` 代码块，Windows 下启动分析需要这一写法。更多用法见[Python API 指南](Docs/Current/api-usage.md)与[公开接口参考](Docs/Current/api.md)。

## 常用命令与文档

以下命令接在 `python -m chronaxis` 后使用；具体参数可追加 `--help` 查看。

| 命令 | 用途 |
|---|---|
| `config init --list` | 查看可生成的示例场景 |
| `validate` / `explain` | 检查配置／解释分析依赖和执行安排 |
| `run` | 执行一次分析并输出结果 |
| `batch run` | 运行多个独立分析任务 |
| `config resolve` / `config origins` | 查看展开后的配置／配置定义来源 |
| `guide` | 显示可直接阅读的AI指南路径；`--language en`选择英文 |

- [在线 HTML 用户手册](https://liuyaoze98.github.io/Chronaxis/)：配置、运行与结果解读；[源码中的手册](Docs/Current/index.md)可在本地阅读。
- [配置说明](Docs/Current/configuration.md)与[完整字段参考](Docs/Current/reference/configuration-schema.md)。
- [源码 AI 指南](Docs/AI/README.md)：直接阅读，按任务查询示例、API 和字段，无需先导出。
- [独立批量任务](Docs/Current/batch.md)与[结果说明](Docs/Current/results.md)。
- [版本规则](Docs/Release/versioning.md)、[发布范围](Docs/Release/distribution.md)和[第三方说明](Docs/Release/third-party.md)。

## 问题反馈与参与开发

问题和建议可发送至 [work@liuyaoze.com](mailto:work@liuyaoze.com)，也可通过 [GitHub Issues](https://github.com/liuyaoze98/Chronaxis/issues) 反馈。报告问题时，请提供软件版本、Python 和系统版本、最小配置、复现步骤，以及预期与实际结果。

参与开发可从[公开测试命令](Docs/Release/distribution.md)和[文档维护说明](Docs/Current/maintenance.md)开始。已知依赖问题见[依赖安全说明](Docs/Release/security.md)。

## 资助致谢

Chronaxis 获得了郑州日产汽车有限公司（Zhengzhou Nissan Automobile Co., Ltd.）2025 年度创新课题的资助，谨此致谢。

## AI 工具声明

本项目使用 Codex 完成开发，并借助 Workbuddy 和 Trae CN 测试 AI 对项目文档及使用方法的理解。

## 许可证与维护者

项目采用 [MIT 许可证](LICENSE)。维护者为 **liuyaoze**，联系邮箱：[work@liuyaoze.com](mailto:work@liuyaoze.com)。第三方依赖和随附资源遵循各自的许可证。
