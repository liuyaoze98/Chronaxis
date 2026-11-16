# Chronaxis 0.1.0.dev5

[English](release-notes-0.1.0.dev5.en.md)

> 0.1.0.dev5 开发预览版；本文说明本版变更、安装方法和已验证的支持范围。

本版主要提高常见积分和 ASC 读取的速度，并让连续分卷的积分可以在文件工作进程中计算。分析配置继续使用整数 `config_version: 4`；公开 API、配置字段和结果格式没有改变，已有配置无需修改。

## 自动选择与通用计算

| 改进 | 使用时的变化 |
|---|---|
| 自动选择计算实现 | 省略 `execution.backend`（即 `auto`）时，积分、持续条件、窗口、极值和计数等已完成对照验证的组合改为选择 `reference` 流式实现。选择在读取数据前按整份计划完成；显式 `reference` 或 `numpy` 保持原选择。`explain` 和运行清单中的 `selected_backend` 可能因此与 dev4 不同，结果按既有容差保持一致。 |
| 常见 ASC 数据行 | 符合经典 CAN 数据行格式的记录使用更快的解析方式，时间仍精确换算为整数纳秒；其他行形状和特殊情况沿用原解析。普通分析和 `chronaxis fast` 读取 ASC 时都会受益。 |
| 通用数值开销 | 减少质量位合并、表达式节点重复计算、数值对象重复校验和积分误差项推进中的固定开销。具体收益取决于所选实现和请求的计算。 |
| 同一报文的直接积分 | 使用默认 `auto`、按实际帧间隔积分同一报文中有限浮点信号的简单公式时，预先编译公式并减少临时对象。固定周期或 DBC 周期间隔不进入这条路径。 |

## 连续分卷的积分

同一来源的多个 ASC/BLF 文件按 `file_merge: concatenate` 连续读取、且 `execution.process_count` 大于 1 时，满足条件的会话积分现在可在文件工作进程中计算：工作进程计算每个文件内部的积分面积，主进程处理文件之间的衔接并按原始顺序累计。数值结果、跨文件状态、有效期和预算规则不变，不需要新增配置。

适用条件见[连续分卷](../Current/continuous-files.md)及[计算实现](../Current/execution.md#integral-path-conditions)：默认 `auto`、同一物理报文的简单会话积分、实际帧间隔和零阶保持，不带规则、窗口、条件、查表、导出或追溯。预算不足时在读取首帧前沿用原路径。单文件、单进程、`time_order`、固定或 DBC 周期、显式 `reference`/`numpy` 和 `chronaxis fast` 不使用此方式。

## 性能结果怎么看

以下数据来自同一台 Windows 电脑上相同任务、相同输入和相同结果校验的配对测量，只说明所测场景：

- ASC 固定周期单文件：通用分析约 11.22→6.16 秒，`chronaxis fast` 约 8.10→3.16 秒；按实际帧间隔积分约 11.94→5.10 秒。
- 真实单个 BLF 按实际帧间隔积分：约 8.87→7.61 秒。
- 连续分卷积分：稀疏 ASC 在 4、8 个工作进程时耗时约减少 49%，密集的六项积分在 4 个工作进程时约减少 38%。但这组数据中 1 个进程仍然最快，或与 4 个进程接近；增加进程数不保证更快。
- 用户提供的十个真实 BLF（固定周期）新旧耗时变化约在 −1.5% 至 +0.7% 之间，没有明显提升。

## 安装包附带用户手册

从 PyPI 或 wheel 安装后，安装目录中附带完整的 Markdown 用户手册：中英文章节、公开 API 说明和全部示例。运行 `python -m chronaxis manual` 显示中文首页路径，加 `--language en` 显示英文首页；命令只显示路径，不写文件。手册中的示例可以直接运行，结果写到你指定的目录。内部模块参考和源码的链接指向 GitHub 上本版本的同一文件；带导航和搜索的 HTML 手册仍以在线网站和 Release 附件提供。

## 手册与 AI 指南

修正了可运行示例的运行位置说明、文件工作进程上限与可省略字段的说明，以及表达式范围、计算实现、读取方式和积分计算位置的区别。中英文手册、API 参考和随包 AI 指南已同步。

## 平台与依赖范围

与 dev4 相同：Python `>=3.12,<3.14`；NumPy 在 Python 3.12 为 `>=1.26.3,<2.6`，在 Python 3.13 为 `>=2.1,<2.6`；cantools 为 `>=39.4.3,<46`，jsonschema 为 `>=4.25.1,<4.27`。其他依赖见[安装说明](../Current/installation.md)，精确环境快照见[约束文件说明](../../requirements/README.md)。Linux 工作进程与发布条件仍按[安装说明](../Current/installation.md)执行；本版的性能数据只在 Windows 上测得，没有测量 Linux 上的连续分卷积分性能。

## 安装本版

在新环境中从 PyPI 安装本版并核对自己的任务：

```powershell
py -3.12 -m venv .venv-dev5
.\.venv-dev5\Scripts\python.exe -m pip install "chronaxis==0.1.0.dev5"
.\.venv-dev5\Scripts\python.exe -m pip check
.\.venv-dev5\Scripts\python.exe -m chronaxis guide
.\.venv-dev5\Scripts\python.exe -m chronaxis manual
```

升级时可用 `explain` 查看自动选择的计算实现。信号有效期、持续条件比较符、积分时间依据和请求输出不会因本轮性能改进自动改变。

维护者：liuyaoze，work@liuyaoze.com。
