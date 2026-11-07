# Chronaxis 0.1.0.dev3

fast run现支持同一次记录的ASC/BLF分卷，execution.process_count控制读取、解码和同帧求值工作进程，主进程按file_merge指定的顺序逐条累计。Python fast.run及CLI支持显式进程数覆盖；独立fast batch保留逐任务累计并拒绝嵌套进程池。字段、限制和完整示例见[高性能积分器](../Current/fast-energy.md)。

普通AnalysisRunner及run/validate/explain新增process_count覆盖；execution.process_count控制一个连续会话的ASC/BLF文件读取与解码，file_merge显式选择接续或稳定时间归并。功能范围和示例见[连续记录多进程](../Current/continuous-files.md)。

[English](release-notes-0.1.0.dev3.en.md)

本版要求持续条件明确选择“达到”或“严格超过”时长阈值，并改进配置错误提示。运行环境为 Windows、Python 3.12，分析配置仍使用整数 `config_version: 4`。

## 安装配套版本

取得本地 wheel 后，在 Windows PowerShell 中创建环境，并填写实际文件路径：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev3-py3-none-any.whl"
.\.venv\Scripts\python.exe -m chronaxis guide
```

使用同版源码时，在包含 `pyproject.toml` 的源码根目录创建环境，将上述安装命令改为 `.\.venv\Scripts\python.exe -m pip install .`。依赖和离线安装方法见[安装说明](../Current/installation.md)。

## 持续条件需要明确时长比较方式

`rule_type: condition_duration` 的规则必须填写 `duration_comparison`。省略该字段会在配置校验时报告缺失，避免把“超过”自动解释为“达到”。

| 填写值 | 含义 | 阈值为 60s、条件恰好成立 60s 时 |
|---|---|---|
| `">="` | 达到最小时长，包含等于阈值的情况 | 区间合格 |
| `">"` | 严格超过最小时长 | 区间不合格 |

从 0.1.0.dev2 升级时，检查每条持续条件规则：

- 已显式填写比较符的规则保留原值。
- 以前省略比较符时，程序按 `">="` 处理；要保留该行为，补写 `duration_comparison: ">="`。
- 业务要求“超过 60 秒”等严格大于条件时，填写 `duration_comparison: ">"`，再核对临界时长的区间是否入选。不能给所有旧规则统一补同一个值。

积分算法、帧间隔选项和单位换算没有变化。比较符决定哪些区间参与计算，因此修改比较符可能改变入选事件及累计能量。完整示例见[持续条件区间积分](../Current/conditional-energy.md)。

## 其他修复

| 项目 | 修复后的行为 |
|---|---|
| 配置错误说明 | 将 JSON Schema 校验结果转换为可读的中文诊断和实际字段位置，避免直接显示校验器的英文内部表达。 |
| 计算项缺少操作类型 | 缺少 `calculations[].operation` 时先指出该字段，不再把其他计算类型需要的 `rule`、`window` 等字段一起要求补填；其他独立错误仍可一起报告。 |
| 仅标准库导入测试 | 使用隔离解释器只加载被测 Chronaxis 包，检查根导入和命令帮助不依赖 NumPy、python-can、cantools 或 jsonschema；测试可用于源码及已安装包，不再依赖外部 `PYTHONPATH`。 |

按[版本规则](versioning.md)，已上传开发预览包发生变化后递增开发版本号。本次使用 `0.1.0.dev3`，既有 `0.1.0.dev2` 安装包保持原样。

维护者：liuyaoze，work@liuyaoze.com。
