# Chronaxis 0.1.0

[English](release-notes-0.1.0.en.md)

> 0.1.0 是 Chronaxis 在 0.x 阶段的首个正式版本，此前发布的是 0.1.0.dev0—0.1.0.dev6 开发预览版。本文说明与 0.1.0.dev6 相比的变化、升级时需要修改的地方、安装方法和已验证的支持范围。

本版修正了 0.1.0.dev6 中的三处问题，其中两处是不兼容变化：从 dev6 或更早版本升级前，请先按下一节检查配置和读取运行清单的程序。分析配置继续使用整数 `config_version: 4`。0.x 阶段接口和配置仍可能调整，不兼容变化会在发行说明中列出迁移方法，见[版本规则](versioning.md)。

## 升级前需要修改的地方

| 变化 | 影响 | 怎么改 |
|---|---|---|
| 被计算引用的持续条件规则必须写 `selection_origin` | `condition_duration` 规则被 `calculations` 的 `scope: {rule: 名称}` 引用、却没有写 `selection_origin` 时，dev6 静默按 `onset` 计算，校验和结果都不提示；本版在校验时报错，并列出规则、引用它的计算和两个可选值。两种取值的结果可能相差很大：条件能量示例按 `onset` 为 0.06777777777777777 kWh，按 `confirmed` 为 0.00111111111 kWh。 | 要保持 dev6 的结果，在该规则中补一行 `selection_origin: onset`；需要从持续确认的时刻开始统计时写 `confirmed`。没有被计算引用的规则仍可省略。 |
| 运行清单删除 `worker_config` | dev6 清单中的 `run.worker_config` 总是 `single-thread`，与实际并行无关。本版删除该键，改为 `run.process_count`（本次生效的文件工作进程上限，已计入命令行或 Python 调用的覆盖）和 `run.worker_process_count`（实际启动并完成工作的进程数，0 表示全部在主进程内完成）。公开类 `RunMetadata` 同时删除 `worker_config` 字段，按位置传参的代码会错位。 | 读取清单的程序改读这两个新键；构造 `RunMetadata` 时使用关键字参数。 |

## 其他变化

- 事件结果表在指标列之后新增“统计开始（s）”列，写明每个事件的指标从哪个时刻开始统计；没有事件指标的行留空。持续条件规则被事件计算引用时，运行清单另记 `selection_origins`。
- 改正 AI 指南中进程数参数的写法：参数写在 `AnalysisRunner().run(plan, process_count=4)` 等方法上，`AnalysisRunner(...)` 构造函数不接受它。文档检查新增“可照抄调用与实际公开签名一致”的核对。
- 中英文手册、AI 指南与示例同步：受影响的示例显式写 `selection_origin: onset`，数值不变；排错页补充缺少统计起点时的处理。

除新增的一列外，随包 78 个示例的计算结果与 0.1.0.dev6 逐格相同。本版没有改动读取、解码和积分的执行路径，没有重新测量性能，dev5、dev6 发行说明中的性能数字仍适用于各自所测场景。

## 平台与依赖范围

与 0.1.0.dev6 相同：Python `>=3.12,<3.14`；NumPy 在 Python 3.12 为 `>=1.26.3,<2.6`，在 Python 3.13 为 `>=2.1,<2.6`；cantools 为 `>=39.4.3,<46`，jsonschema 为 `>=4.25.1,<4.27`。其他依赖见[安装说明](../Current/installation.md)，精确环境快照见[约束文件说明](../../requirements/README.md)。Linux 工作进程与发布条件仍按[安装说明](../Current/installation.md)执行；本版实际核验环境为 Windows 与 Python 3.12。

## 安装本版

在新环境中从 PyPI 安装本版并核对自己的任务：

```powershell
py -3.12 -m venv .venv-010
.\.venv-010\Scripts\python.exe -m pip install "chronaxis==0.1.0"
.\.venv-010\Scripts\python.exe -m pip check
.\.venv-010\Scripts\python.exe -m chronaxis guide
.\.venv-010\Scripts\python.exe -m chronaxis manual
```

升级后先对自己的配置运行 `python -m chronaxis validate 配置文件`：若报告缺少 `selection_origin`，按上表补写后再运行分析。

维护者：liuyaoze，work@liuyaoze.com。
