# 每个示例的实际结果与解释

> 本页使用随册合成数据，结果由实际运行产生；不能作为其他日志的预期值。

本页覆盖76份可运行YAML（含2份批量清单）和2份JSON配置。两份教学基础配置及一份公共定义不独立运行，单列在末尾。

命令以`examples`为当前目录，结果目录可复用，每次输出增加时间文件名。普通例默认中文可读CSV，时间列为精确秒、同区间指标合并，各指标分别显示状态和说明。显式csv/jsonl交换格式及原帧/信号导出仍采用各自约定；空单元格不是零。

每例的`result-summary.json`从真实运行清单摘取状态、表行数、适用的业务概况和阈值预设摘要；完整运行会另生成`run_manifest_<时间后缀>.json`。教学快照去掉命名时间，保留稳定下载名；这不代表新运行使用固定文件名。教程结果不复制其中的随机运行编号、绝对路径或资源峰值。明确请求贡献、追溯或导出的例子保留相应小文件，普通例不额外开启这些功能。

## 按文件查找

|配置|用途|实际结果|
|---|---|---|
|[activity.yaml](examples/activity.yaml)|事件、窗口与各自能量|[查看表和解释](#activity-yaml)|
|[analysis-imports.yaml](examples/analysis-imports.yaml)|能量与均值/来源读取|[查看表和解释](#analysis-imports-yaml)|
|[analysis.json](examples/analysis.json)|能量与均值/来源读取|[查看表和解释](#analysis-json)|
|[analysis.yaml](examples/analysis.yaml)|能量与均值/来源读取|[查看表和解释](#analysis-yaml)|
|[batch-extended.yaml](examples/batch-extended.yaml)|两个独立任务|[查看表和解释](#batch-extended-yaml)|
|[batch-minimal.yaml](examples/batch-minimal.yaml)|独立任务|[查看表和解释](#batch-minimal-yaml)|
|[calculation-minimal.yaml](examples/calculation-minimal.yaml)|功率积分|[查看表和解释](#calculation-minimal-yaml)|
|[calculation-operations.yaml](examples/calculation-operations.yaml)|统计、积分与筛选|[查看表和解释](#calculation-operations-yaml)|
|[can-joint-analysis.yaml](examples/can-joint-analysis.yaml)|CAN与独立电流表联合计算|[查看表和解释](#can-joint-analysis-yaml)|
|[conditional-energy.yaml](examples/conditional-energy.yaml)|连续满足条件后积分|[查看表和解释](#conditional-energy-yaml)|
|[continuous-parallel.yaml](examples/continuous-parallel.yaml)|连续分卷多进程读取|[查看表和解释](#continuous-parallel-yaml)|
|[continuous-time-order.yaml](examples/continuous-time-order.yaml)|连续分卷多进程读取|[查看表和解释](#continuous-time-order-yaml)|
|[dual-grid.yaml](examples/dual-grid.yaml)|原始CAN或网格重建导出|[查看表和解释](#dual-grid-yaml)|
|[execution-comparison.json](examples/execution-comparison.json)|观测不足时的结果|[查看表和解释](#execution-comparison-json)|
|[execution-diagnostics.yaml](examples/execution-diagnostics.yaml)|显式请求输入追溯|[查看表和解释](#execution-diagnostics-yaml)|
|[execution-report.yaml](examples/execution-report.yaml)|保留已知范围的数值|[查看表和解释](#execution-report-yaml)|
|[execution-strict.yaml](examples/execution-strict.yaml)|拒绝给出不完整数值|[查看表和解释](#execution-strict-yaml)|
|[export-can-all-windows.yaml](examples/export-can-all-windows.yaml)|按全部窗口分别导出|[查看表和解释](#export-can-all-windows-yaml)|
|[export-can-grid.yaml](examples/export-can-grid.yaml)|CAN等间隔重建|[查看表和解释](#export-can-grid-yaml)|
|[export-can-minimal.yaml](examples/export-can-minimal.yaml)|原帧导出|[查看表和解释](#export-can-minimal-yaml)|
|[export-signal-grid.yaml](examples/export-signal-grid.yaml)|信号等间隔导出|[查看表和解释](#export-signal-grid-yaml)|
|[export-signal-minimal.yaml](examples/export-signal-minimal.yaml)|导出原信号更新|[查看表和解释](#export-signal-minimal-yaml)|
|[expression-extended.yaml](examples/expression-extended.yaml)|事件内派生功率积分|[查看表和解释](#expression-extended-yaml)|
|[expression-minimal.yaml](examples/expression-minimal.yaml)|派生功率最大值|[查看表和解释](#expression-minimal-yaml)|
|[input-asc-minimal.yaml](examples/input-asc-minimal.yaml)|ASC报文与DBC解码|[查看表和解释](#input-asc-minimal-yaml)|
|[input-can-directory.yaml](examples/input-can-directory.yaml)|能量与均值/来源读取|[查看表和解释](#input-can-directory-yaml)|
|[input-csv-minimal.yaml](examples/input-csv-minimal.yaml)|CSV功率积分|[查看表和解释](#input-csv-minimal-yaml)|
|[input-csv-offset.yaml](examples/input-csv-offset.yaml)|CSV时间校准|[查看表和解释](#input-csv-offset-yaml)|
|[input-memory-minimal.yaml](examples/input-memory-minimal.yaml)|内存API输入|[查看表和解释](#input-memory-minimal-yaml)|
|[input-raw-csv-mapping.yaml](examples/input-raw-csv-mapping.yaml)|原始报文读取和DBC解码|[查看表和解释](#input-raw-csv-mapping-yaml)|
|[input-raw-csv-minimal.yaml](examples/input-raw-csv-minimal.yaml)|原始报文读取和DBC解码|[查看表和解释](#input-raw-csv-minimal-yaml)|
|[interval-actual.yaml](examples/interval-actual.yaml)|按真实时间间隔积分|[查看表和解释](#interval-actual-yaml)|
|[interval-fixed.yaml](examples/interval-fixed.yaml)|按固定周期积分|[查看表和解释](#interval-fixed-yaml)|
|[lookup-power.yaml](examples/lookup-power.yaml)|电压查表后的平均功率|[查看表和解释](#lookup-power-yaml)|
|[message-directions.yaml](examples/message-directions.yaml)|按方向分别累计消息|[查看表和解释](#message-directions-yaml)|
|[message-energy.yaml](examples/message-energy.yaml)|每条消息累计|[查看表和解释](#message-energy-yaml)|
|[message-minimal.yaml](examples/message-minimal.yaml)|每条消息累计|[查看表和解释](#message-minimal-yaml)|
|[power-statistics.yaml](examples/power-statistics.yaml)|功率波动与加载均值的P95|[查看表和解释](#power-statistics-yaml)|
|[preset-charge-energy.yaml](examples/preset-charge-energy.yaml)|充电活动与累计量|[查看表和解释](#preset-charge-energy-yaml)|
|[preset-charge-minimal.yaml](examples/preset-charge-minimal.yaml)|充电活动检测|[查看表和解释](#preset-charge-minimal-yaml)|
|[preset-command-automatic.yaml](examples/preset-command-automatic.yaml)|请求响应配对|[查看表和解释](#preset-command-automatic-yaml)|
|[preset-command-minimal.yaml](examples/preset-command-minimal.yaml)|请求响应配对|[查看表和解释](#preset-command-minimal-yaml)|
|[preset-fault-context.yaml](examples/preset-fault-context.yaml)|报警前后窗口|[查看表和解释](#preset-fault-context-yaml)|
|[preset-fault-minimal.yaml](examples/preset-fault-minimal.yaml)|报警点后的窗口|[查看表和解释](#preset-fault-minimal-yaml)|
|[preset-threshold-delay.yaml](examples/preset-threshold-delay.yaml)|确认等待后的报警|[查看表和解释](#preset-threshold-delay-yaml)|
|[preset-threshold-minimal.yaml](examples/preset-threshold-minimal.yaml)|迟滞报警时长|[查看表和解释](#preset-threshold-minimal-yaml)|
|[preset-threshold-partial.yaml](examples/preset-threshold-partial.yaml)|初始状态未知的报警|[查看表和解释](#preset-threshold-partial-yaml)|
|[quality.yaml](examples/quality.yaml)|无效码和过期|[查看表和解释](#quality-yaml)|
|[rule-condition_duration-extended.yaml](examples/rule-condition_duration-extended.yaml)|事件规则：condition_duration|[查看表和解释](#rule-condition_duration-extended-yaml)|
|[rule-condition_duration-minimal.yaml](examples/rule-condition_duration-minimal.yaml)|事件规则：condition_duration|[查看表和解释](#rule-condition_duration-minimal-yaml)|
|[rule-debounce-extended.yaml](examples/rule-debounce-extended.yaml)|事件规则：debounce|[查看表和解释](#rule-debounce-extended-yaml)|
|[rule-debounce-minimal.yaml](examples/rule-debounce-minimal.yaml)|事件规则：debounce|[查看表和解释](#rule-debounce-minimal-yaml)|
|[rule-falling_edge-extended.yaml](examples/rule-falling_edge-extended.yaml)|事件规则：falling_edge|[查看表和解释](#rule-falling_edge-extended-yaml)|
|[rule-falling_edge-minimal.yaml](examples/rule-falling_edge-minimal.yaml)|事件规则：falling_edge|[查看表和解释](#rule-falling_edge-minimal-yaml)|
|[rule-hysteresis-extended.yaml](examples/rule-hysteresis-extended.yaml)|事件规则：hysteresis|[查看表和解释](#rule-hysteresis-extended-yaml)|
|[rule-hysteresis-minimal.yaml](examples/rule-hysteresis-minimal.yaml)|事件规则：hysteresis|[查看表和解释](#rule-hysteresis-minimal-yaml)|
|[rule-rising_edge-extended.yaml](examples/rule-rising_edge-extended.yaml)|事件规则：rising_edge|[查看表和解释](#rule-rising_edge-extended-yaml)|
|[rule-rising_edge-minimal.yaml](examples/rule-rising_edge-minimal.yaml)|事件规则：rising_edge|[查看表和解释](#rule-rising_edge-minimal-yaml)|
|[rule-start_end-extended.yaml](examples/rule-start_end-extended.yaml)|事件规则：start_end|[查看表和解释](#rule-start_end-extended-yaml)|
|[rule-start_end-minimal.yaml](examples/rule-start_end-minimal.yaml)|事件规则：start_end|[查看表和解释](#rule-start_end-minimal-yaml)|
|[rule-start_only-extended.yaml](examples/rule-start_only-extended.yaml)|事件规则：start_only|[查看表和解释](#rule-start_only-extended-yaml)|
|[rule-start_only-minimal.yaml](examples/rule-start_only-minimal.yaml)|事件规则：start_only|[查看表和解释](#rule-start_only-minimal-yaml)|
|[rule-window_delta-extended.yaml](examples/rule-window_delta-extended.yaml)|事件规则：window_delta|[查看表和解释](#rule-window_delta-extended-yaml)|
|[rule-window_delta-minimal.yaml](examples/rule-window_delta-minimal.yaml)|事件规则：window_delta|[查看表和解释](#rule-window_delta-minimal-yaml)|
|[sequence-minimal.yaml](examples/sequence-minimal.yaml)|请求响应配对|[查看表和解释](#sequence-minimal-yaml)|
|[sequence-outcomes.yaml](examples/sequence-outcomes.yaml)|匹配、无响应和无法确定|[查看表和解释](#sequence-outcomes-yaml)|
|[signal-bool-minimal.yaml](examples/signal-bool-minimal.yaml)|布尔开关边沿|[查看表和解释](#signal-bool-minimal-yaml)|
|[signal-enum-minimal.yaml](examples/signal-enum-minimal.yaml)|枚举状态边沿|[查看表和解释](#signal-enum-minimal-yaml)|
|[signal-number-conversion.yaml](examples/signal-number-conversion.yaml)|电流单位换算|[查看表和解释](#signal-number-conversion-yaml)|
|[signal-number-minimal.yaml](examples/signal-number-minimal.yaml)|DBC电流最大值|[查看表和解释](#signal-number-minimal-yaml)|
|[signal-state-combined.yaml](examples/signal-state-combined.yaml)|组合状态边沿|[查看表和解释](#signal-state-combined-yaml)|
|[start-end.yaml](examples/start-end.yaml)|开始、正常结束及超时|[查看表和解释](#start-end-yaml)|
|[timing-actual.yaml](examples/timing-actual.yaml)|真实时间下的规则和配对|[查看表和解释](#timing-actual-yaml)|
|[timing-dbc.yaml](examples/timing-dbc.yaml)|DBC周期下的规则和配对|[查看表和解释](#timing-dbc-yaml)|
|[timing-fixed.yaml](examples/timing-fixed.yaml)|固定周期下的规则和配对|[查看表和解释](#timing-fixed-yaml)|
|[window-exit-delay.yaml](examples/window-exit-delay.yaml)|围绕事件选窗口|[查看表和解释](#window-exit-delay-yaml)|
|[window-merged.yaml](examples/window-merged.yaml)|围绕事件选窗口|[查看表和解释](#window-merged-yaml)|
|[window-minimal.yaml](examples/window-minimal.yaml)|围绕事件选窗口|[查看表和解释](#window-minimal-yaml)|

<a id="activity-yaml"></a>
## activity.yaml

用途：事件、窗口与各自能量。配置：[下载](examples/activity.yaml)；功能说明：[阅读指南](activity-tutorial.md)。

```powershell
chronaxis run activity.yaml --output result-activity-yaml
```

为什么得到这些结果：温度在1秒达到80℃，连续2秒后于3秒确认，6秒解除。活动[1,6)是5秒，10W×5s＝50J；窗口前后各加1秒得到[0,7)，10W×7s＝70J。

[本次状态与表清单](examples/results/activity-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/activity-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | event_energy（J） | event_energy：状态 | event_energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | hot | 1 | 3 | 6 | 正常结束 | — | 50.0 | 完整 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/activity-yaml/窗口结果.csv)（1行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 | context_energy（J） | context_energy：状态 | context_energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | hot_context | 0 | 7 | 完整 | 1 | — | 70.0 | 完整 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="analysis-imports-yaml"></a>
## analysis-imports.yaml

用途：能量与均值/来源读取。配置：[下载](examples/analysis-imports.yaml)；功能说明：[阅读指南](quickstart.md)。

```powershell
chronaxis run analysis-imports.yaml --output result-analysis-imports-yaml
```

为什么得到这些结果：功率2、4、8、10W分别持续1、2、1、2秒：2×1＋4×2＋8×1＋10×2＝38J；四个更新的均值为6W；按时间加权为38/6W。派生double_power把功率乘2，所以double_energy为76J。

[本次状态与表清单](examples/results/analysis-imports-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/analysis-imports-yaml/会话结果.csv)（1行）**

| double_energy（J） | double_energy：状态 | double_energy：说明 | energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 76.0 | 完整 | — | 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="analysis-json"></a>
## analysis.json

用途：能量与均值/来源读取。配置：[下载](examples/analysis.json)；功能说明：[阅读指南](quickstart.md)。

```powershell
chronaxis run analysis.json --output result-analysis-json
```

为什么得到这些结果：功率2、4、8、10W分别持续1、2、1、2秒：2×1＋4×2＋8×1＋10×2＝38J；四个更新的均值为6W；按时间加权为38/6W。

[本次状态与表清单](examples/results/analysis-json/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/analysis-json/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="analysis-yaml"></a>
## analysis.yaml

用途：能量与均值/来源读取。配置：[下载](examples/analysis.yaml)；功能说明：[阅读指南](quickstart.md)。

```powershell
chronaxis run analysis.yaml --output result-analysis-yaml
```

为什么得到这些结果：功率2、4、8、10W分别持续1、2、1、2秒：2×1＋4×2＋8×1＋10×2＝38J；四个更新的均值为6W；按时间加权为38/6W。

[本次状态与表清单](examples/results/analysis-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/analysis-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="batch-extended-yaml"></a>
## batch-extended.yaml

用途：两个独立任务。配置：[下载](examples/batch-extended.yaml)；功能说明：[阅读指南](batch.md)。

```powershell
chronaxis batch run batch-extended.yaml --output result-batch-extended-yaml
```

为什么得到这些结果：job_1运行主例得到38J、6W和38/6W；job_2电压积分13V·s。两任务不拼接日志或继承状态。

[批量状态摘要](examples/results/batch-extended-yaml/batch-summary.json)。以下各任务独立输出：

### job_1

[本次状态与表清单](examples/results/batch-extended-yaml/job_1/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/batch-extended-yaml/job_1/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。

### job_2

[本次状态与表清单](examples/results/batch-extended-yaml/job_2/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/batch-extended-yaml/job_2/会话结果.csv)（1行）**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="batch-minimal-yaml"></a>
## batch-minimal.yaml

用途：独立任务。配置：[下载](examples/batch-minimal.yaml)；功能说明：[阅读指南](batch.md)。

```powershell
chronaxis batch run batch-minimal.yaml --output result-batch-minimal-yaml
```

为什么得到这些结果：job_1独立执行batch/energy.yaml，得到38J、6W和38/6W；检查jobs中的completed与子任务结果。

[批量状态摘要](examples/results/batch-minimal-yaml/batch-summary.json)。以下各任务独立输出：

### job_1

[本次状态与表清单](examples/results/batch-minimal-yaml/job_1/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/batch-minimal-yaml/job_1/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="calculation-minimal-yaml"></a>
## calculation-minimal.yaml

用途：功率积分。配置：[下载](examples/calculation-minimal.yaml)；功能说明：[阅读指南](calculations.md)。

```powershell
chronaxis run calculation-minimal.yaml --output result-calculation-minimal-yaml
```

为什么得到这些结果：1到4秒功率为10W，其余为0；10W×3s=30J。本例只请求这一项积分。

[本次状态与表清单](examples/results/calculation-minimal-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/calculation-minimal-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 30.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="calculation-operations-yaml"></a>
## calculation-operations.yaml

用途：统计、积分与筛选。配置：[下载](examples/calculation-operations.yaml)；功能说明：[阅读指南](calculations.md)。

```powershell
chronaxis run calculation-operations.yaml --output result-calculation-operations-yaml
```

为什么得到这些结果：功率0W@0s、10W@1s、0W@4s，观测到5s。正功率持续3s，因此积分30J、时长3s；样本均值(0＋10＋0)/3＝10/3W，时间均值30/5＝6W。最小值0W、最大值10W；select保留三次实际更新。Wh结果为30/3600。

[本次状态与表清单](examples/results/calculation-operations-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/calculation-operations-yaml/会话结果.csv)（1行）**

| duration（s） | duration：状态 | duration：说明 | energy_Wh（Wh） | energy_Wh：状态 | energy_Wh：说明 | integral（J） | integral：状态 | integral：说明 | max_time（W） | max_time：状态 | max_time：说明 | min_time（W） | min_time：状态 | min_time：说明 | sample_maximum（W） | sample_maximum：状态 | sample_maximum：说明 | sample_mean（W） | sample_mean：状态 | sample_mean：说明 | sample_minimum（W） | sample_minimum：状态 | sample_minimum：说明 | time_weighted_mean（W） | time_weighted_mean：状态 | time_weighted_mean：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3.0 | 完整 | — | 0.008333333333333333 | 完整 | — | 30.0 | 完整 | — | 10.0 | 完整 | — | 0.0 | 完整 | — | 10.0 | 完整 | — | 3.3333333333333335 | 完整 | — | 0.0 | 完整 | — | 6.0 | 完整 | — |

**选择结果：[下载完整 选择结果.csv](examples/results/calculation-operations-yaml/选择结果.csv)（3行）**

| 计算项 | 统计范围 | 所属区间 | 时间（s） | 值 | 单位 | 数值状态 | 选择状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| select | 会话 | — | 0 | 0.0 | W | 有效 | 满足条件 | — |
| select | 会话 | — | 1 | 10.0 | W | 有效 | 满足条件 | — |
| select | 会话 | — | 4 | 0.0 | W | 有效 | 满足条件 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="can-joint-analysis-yaml"></a>
## can-joint-analysis.yaml

用途：CAN与独立电流表联合计算。配置：[下载](examples/can-joint-analysis.yaml)；功能说明：[阅读指南](examples.md#can-joint-analysis)。

```powershell
chronaxis run can-joint-analysis.yaml --output result-can-joint-analysis-yaml
```

为什么得到这些结果：CAN电压3、7、3V分别保持1秒，独立来源电流2A。同步后积分(3＋7＋3)×2＝26J；共同clock说明同步依据，来源名称本身不会自动校准时间。

[本次状态与表清单](examples/results/can-joint-analysis-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/can-joint-analysis-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 26.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="conditional-energy-yaml"></a>
## conditional-energy.yaml

用途：连续满足条件后积分。配置：[下载](examples/conditional-energy.yaml)；功能说明：[阅读指南](conditional-energy.md)。

```powershell
chronaxis run conditional-energy.yaml --output result-conditional-energy-yaml
```

为什么得到这些结果：状态为0x2且电流恰好10A，符合>=10A；[0,60)恰好60秒被严格>60s排除，[61,122)跨卷连续61秒合格。默认onset覆盖完整61秒，400V×10A×61s/3600000=0.06777777777777777kWh。

[本次状态与表清单](examples/results/conditional-energy-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/conditional-energy-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | 说明 | energy_kwh（kWh） | energy_kwh：状态 | energy_kwh：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | eligible | 61 | 122 | 正常结束 | — | 0.06777777777777777 | 完整 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="continuous-parallel-yaml"></a>
## continuous-parallel.yaml

用途：连续分卷多进程读取。配置：[下载](examples/continuous-parallel.yaml)；功能说明：[阅读指南](continuous-files.md)。

```powershell
chronaxis run continuous-parallel.yaml --output result-continuous-parallel-yaml
```

为什么得到这些结果：同一会话保持跨文件状态，2/4/8/10W分别保持1/2/1/2秒，能量38J；time_order例还产生[0,6)秒的一段活动，1秒确认。

[本次状态与表清单](examples/results/continuous-parallel-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/continuous-parallel-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="continuous-time-order-yaml"></a>
## continuous-time-order.yaml

用途：连续分卷多进程读取。配置：[下载](examples/continuous-time-order.yaml)；功能说明：[阅读指南](continuous-files.md)。

```powershell
chronaxis run continuous-time-order.yaml --output result-continuous-time-order-yaml
```

为什么得到这些结果：同一会话保持跨文件状态，2/4/8/10W分别保持1/2/1/2秒，能量38J；time_order例还产生[0,6)秒的一段活动，1秒确认。

[本次状态与表清单](examples/results/continuous-time-order-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/continuous-time-order-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | active | 0 | 1 | 6 | 观测结束，活动尚未确认结束 | 数据缺失 |

**会话结果：[下载完整 会话结果.csv](examples/results/continuous-time-order-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="dual-grid-yaml"></a>
## dual-grid.yaml

用途：原始CAN或网格重建导出。配置：[下载](examples/dual-grid.yaml)；功能说明：[阅读指南](can-exports.md)。

```powershell
chronaxis run dual-grid.yaml --output result-dual-grid-yaml
```

为什么得到这些结果：电压积分仍为3＋7＋3＝13V·s。双网格例有12个250ms信号位置，最后3点缺右端；CAN500ms网格实际生成5帧、跳过1点。导出文件与分析摘要分别读取，不用导出行数代替积分区间。

[本次状态与表清单](examples/results/dual-grid-yaml/result-summary.json)：`completed`。

[导出说明 exports/export-00000000/manifest.json](examples/results/dual-grid-yaml/exports/export-00000000/manifest.json)。

**resampled：[下载完整 exports/export-00000000/resampled.csv](examples/results/dual-grid-yaml/exports/export-00000000/resampled.csv)（12行）**

| time_ns | signal | value | unit | status | reason | quality |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | voltage | 3.0 | V | observed | — | 0 |
| 250000000 | voltage | 4.0 | V | estimated | — | 0 |
| 500000000 | voltage | 5.0 | V | estimated | — | 0 |
| 750000000 | voltage | 6.0 | V | estimated | — | 0 |
| 1000000000 | voltage | 7.0 | V | observed | — | 0 |
| 1250000000 | voltage | 6.0 | V | estimated | — | 0 |
| 1500000000 | voltage | 5.0 | V | estimated | — | 0 |
| 1750000000 | voltage | 4.0 | V | estimated | — | 0 |

表内共12行，此处显示前8行；下载文件包含全部行。

[下载 exports/export-00000001/frames.asc](examples/results/dual-grid-yaml/exports/export-00000001/frames.asc)（210字节）。

[导出说明 exports/export-00000001/manifest.json](examples/results/dual-grid-yaml/exports/export-00000001/manifest.json)：frames=5，generated=5，passthrough=0，skipped_grid_points=1。

[下载 exports.jsonl](examples/results/dual-grid-yaml/exports.jsonl)（518字节）。

**会话结果：[下载完整 会话结果.csv](examples/results/dual-grid-yaml/会话结果.csv)（1行）**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="execution-comparison-json"></a>
## execution-comparison.json

用途：观测不足时的结果。配置：[下载](examples/execution-comparison.json)；功能说明：[阅读指南](execution.md)。

```powershell
chronaxis run execution-comparison.json --output result-execution-comparison-json
```

为什么得到这些结果：请求[0,12)秒，文件只观测到8秒，功率4000W。已知部分4000×8＝32000J；report返回32000和partial，strict返回空值及indeterminate，不把后4秒补成0。联合例还分别给出两段事件各4000J和合并窗口24000J。

[本次状态与表清单](examples/results/execution-comparison-json/result-summary.json)：`completed`。

**计算：[下载完整 calculations.csv](examples/results/execution-comparison-json/calculations.csv)（4行）**

| calculation_id | operation | scope | value | unit | status | reason | quality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| event_energy | integral | event | 4000.0 | J | complete | ok | 0 |
| event_energy | integral | event | 4000.0 | J | complete | ok | 0 |
| segment_energy | integral | segment | 24000.0 | J | complete | ok | 0 |
| session_energy | integral | session | 32000.0 | J | partial | partial_coverage | 0 |

**事件：[下载完整 events.csv](examples/results/execution-comparison-json/events.csv)（2行）**

| rule_id | start_ns | confirmed_ns | end_ns | status | quality |
| --- | --- | --- | --- | --- | --- |
| working | 0 | 0 | 1000000000 | closed | 0 |
| working | 2000000000 | 2000000000 | 3000000000 | closed | 0 |

**窗口：[下载完整 segments.csv](examples/results/execution-comparison-json/segments.csv)（1行）**

| window_id | start_ns | end_ns | status |
| --- | --- | --- | --- |
| context | 0 | 6000000000 | complete |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="execution-diagnostics-yaml"></a>
## execution-diagnostics.yaml

用途：显式请求输入追溯。配置：[下载](examples/execution-diagnostics.yaml)；功能说明：[阅读指南](execution.md)。

```powershell
chronaxis run execution-diagnostics.yaml --output result-execution-diagnostics-yaml
```

为什么得到这些结果：功率10W保持3秒，仍为30J。此例显式开启diagnostics.trace，所以同时提供逐条所需输入的输入追溯.csv；普通例不产生这张表。小批次用于展示执行设置，不改变计算。

[本次状态与表清单](examples/results/execution-diagnostics-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/execution-diagnostics-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 30.0 | 完整 | — |

**输入追溯：[下载完整 输入追溯.csv](examples/results/execution-diagnostics-yaml/输入追溯.csv)（3行）**

| 来源 | 原记录序号 | 时间（s） | 记录类型 | 输入位置 | 字段值 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| source_1 | 1 | 0 | 解码报文 | can:0:256:0:0 | {"Power":0.0} | — |
| source_1 | 2 | 1 | 解码报文 | can:0:256:0:0 | {"Power":10.0} | — |
| source_1 | 3 | 4 | 解码报文 | can:0:256:0:0 | {"Power":0.0} | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="execution-report-yaml"></a>
## execution-report.yaml

用途：保留已知范围的数值。配置：[下载](examples/execution-report.yaml)；功能说明：[阅读指南](execution.md)。

```powershell
chronaxis run execution-report.yaml --output result-execution-report-yaml
```

为什么得到这些结果：请求[0,12)，实际只观测到8秒；4000W×8s＝32000J。report保留32000并标为partial，未观测的后4秒没有被补零。

[本次状态与表清单](examples/results/execution-report-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/execution-report-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 32000.0 | 部分有效 | 仅统计有效部分 |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="execution-strict-yaml"></a>
## execution-strict.yaml

用途：拒绝给出不完整数值。配置：[下载](examples/execution-strict.yaml)；功能说明：[阅读指南](execution.md)。

```powershell
chronaxis run execution-strict.yaml --output result-execution-strict-yaml
```

为什么得到这些结果：请求[0,12)，实际只观测到8秒；虽能确认已知部分为32000J，strict仍把完整请求的数值留空并标为indeterminate，避免把部分值当作全段结果。

[本次状态与表清单](examples/results/execution-strict-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/execution-strict-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| — | 无法确定 | 有效数据不足 |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="export-can-all-windows-yaml"></a>
## export-can-all-windows.yaml

用途：按全部窗口分别导出。配置：[下载](examples/export-can-all-windows.yaml)；功能说明：[阅读指南](can-exports.md)。

```powershell
chronaxis run export-can-all-windows.yaml --output result-export-can-all-windows-yaml
```

为什么得到这些结果：电压大于5V的活动为[1,2)；active窗口导出1秒的1帧，before窗口向前加1秒，在[0,2)导出0、1秒的2帧。两个窗口分别输出，不能把两份文件的帧数当作整段积分的样本数。

[本次状态与表清单](examples/results/export-can-all-windows-yaml/result-summary.json)：`completed`。

[下载 exports/export-00000000/frames.asc](examples/results/export-can-all-windows-yaml/exports/export-00000000/frames.asc)（86字节）。

[导出说明 exports/export-00000000/manifest.json](examples/results/export-can-all-windows-yaml/exports/export-00000000/manifest.json)：frames=1，generated=0，passthrough=1，skipped_grid_points=0。

[下载 exports/export-00000001/frames.asc](examples/results/export-can-all-windows-yaml/exports/export-00000001/frames.asc)（117字节）。

[导出说明 exports/export-00000001/manifest.json](examples/results/export-can-all-windows-yaml/exports/export-00000001/manifest.json)：frames=2，generated=0，passthrough=2，skipped_grid_points=0。

[下载 exports.jsonl](examples/results/export-can-all-windows-yaml/exports.jsonl)（648字节）。

**事件结果：[下载完整 事件结果.csv](examples/results/export-can-all-windows-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | high | 1 | 1 | 2 | 正常结束 | — |

**会话结果：[下载完整 会话结果.csv](examples/results/export-can-all-windows-yaml/会话结果.csv)（1行）**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/export-can-all-windows-yaml/窗口结果.csv)（2行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | active | 1 | 2 | 完整 | 1 | — |
| 2 | before | 0 | 2 | 完整 | 1 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="export-can-grid-yaml"></a>
## export-can-grid.yaml

用途：CAN等间隔重建。配置：[下载](examples/export-can-grid.yaml)；功能说明：[阅读指南](can-exports.md)。

```powershell
chronaxis run export-can-grid.yaml --output result-export-can-grid-yaml
```

为什么得到这些结果：电压积分仍为13V·s。500ms网格在0、0.5、1、1.5、2秒生成5帧；2.5秒缺少范围内右端更新而跳过，不外推。

[本次状态与表清单](examples/results/export-can-grid-yaml/result-summary.json)：`completed`。

[下载 exports/export-00000000/frames.asc](examples/results/export-can-grid-yaml/exports/export-00000000/frames.asc)（210字节）。

[导出说明 exports/export-00000000/manifest.json](examples/results/export-can-grid-yaml/exports/export-00000000/manifest.json)：frames=5，generated=5，passthrough=0，skipped_grid_points=1。

[下载 exports.jsonl](examples/results/export-can-grid-yaml/exports.jsonl)（258字节）。

**会话结果：[下载完整 会话结果.csv](examples/results/export-can-grid-yaml/会话结果.csv)（1行）**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="export-can-minimal-yaml"></a>
## export-can-minimal.yaml

用途：原帧导出。配置：[下载](examples/export-can-minimal.yaml)；功能说明：[阅读指南](can-exports.md)。

```powershell
chronaxis run export-can-minimal.yaml --output result-export-can-minimal-yaml
```

为什么得到这些结果：电压积分为3＋7＋3＝13V·s；导出[0,3)内0、1、2秒的3条原始帧，3秒排除端点不导出。没有重采样，不生成中间帧。

[本次状态与表清单](examples/results/export-can-minimal-yaml/result-summary.json)：`completed`。

[下载 exports/export-00000000/frames.asc](examples/results/export-can-minimal-yaml/exports/export-00000000/frames.asc)（148字节）。

[导出说明 exports/export-00000000/manifest.json](examples/results/export-can-minimal-yaml/exports/export-00000000/manifest.json)：frames=3，generated=0，passthrough=3，skipped_grid_points=0。

[下载 exports.jsonl](examples/results/export-can-minimal-yaml/exports.jsonl)（257字节）。

**会话结果：[下载完整 会话结果.csv](examples/results/export-can-minimal-yaml/会话结果.csv)（1行）**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="export-signal-grid-yaml"></a>
## export-signal-grid.yaml

用途：信号等间隔导出。配置：[下载](examples/export-signal-grid.yaml)；功能说明：[阅读指南](signal-exports.md)。

```powershell
chronaxis run export-signal-grid.yaml --output result-export-signal-grid-yaml
```

为什么得到这些结果：积分仍为38J；500ms网格共有12行，其中4行对应实际更新、5行由相邻更新线性估计、4.5/5/5.5秒的3行因缺右端更新记missing。

[本次状态与表清单](examples/results/export-signal-grid-yaml/result-summary.json)：`completed`。

[导出说明 exports/export-00000000/manifest.json](examples/results/export-signal-grid-yaml/exports/export-00000000/manifest.json)。

**resampled：[下载完整 exports/export-00000000/resampled.csv](examples/results/export-signal-grid-yaml/exports/export-00000000/resampled.csv)（12行）**

| time_ns | signal | value | unit | status | reason | quality |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | power | 2.0 | W | observed | — | 0 |
| 500000000 | power | 3.0 | W | estimated | — | 0 |
| 1000000000 | power | 4.0 | W | observed | — | 0 |
| 1500000000 | power | 5.0 | W | estimated | — | 0 |
| 2000000000 | power | 6.0 | W | estimated | — | 0 |
| 2500000000 | power | 7.0 | W | estimated | — | 0 |
| 3000000000 | power | 8.0 | W | observed | — | 0 |
| 3500000000 | power | 9.0 | W | estimated | — | 0 |

表内共12行，此处显示前8行；下载文件包含全部行。

[下载 exports.jsonl](examples/results/export-signal-grid-yaml/exports.jsonl)（260字节）。

**会话结果：[下载完整 会话结果.csv](examples/results/export-signal-grid-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="export-signal-minimal-yaml"></a>
## export-signal-minimal.yaml

用途：导出原信号更新。配置：[下载](examples/export-signal-minimal.yaml)；功能说明：[阅读指南](signal-exports.md)。

```powershell
chronaxis run export-signal-minimal.yaml --output result-export-signal-minimal-yaml
```

为什么得到这些结果：积分仍为38J；original.csv保存0、1、3、4秒的4条power更新。没有设置重采样，不生成中间时间点。

[本次状态与表清单](examples/results/export-signal-minimal-yaml/result-summary.json)：`completed`。

[导出说明 exports/export-00000000/manifest.json](examples/results/export-signal-minimal-yaml/exports/export-00000000/manifest.json)。

**original：[下载完整 exports/export-00000000/original.csv](examples/results/export-signal-minimal-yaml/exports/export-00000000/original.csv)（4行）**

| time_ns | signal | value | unit | quality |
| --- | --- | --- | --- | --- |
| 0 | power | 2.0 | W | 0 |
| 1000000000 | power | 4.0 | W | 0 |
| 3000000000 | power | 8.0 | W | 0 |
| 4000000000 | power | 10.0 | W | 0 |

[下载 exports.jsonl](examples/results/export-signal-minimal-yaml/exports.jsonl)（259字节）。

**会话结果：[下载完整 会话结果.csv](examples/results/export-signal-minimal-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="expression-extended-yaml"></a>
## expression-extended.yaml

用途：事件内派生功率积分。配置：[下载](examples/expression-extended.yaml)；功能说明：[阅读指南](expressions.md)。

```powershell
chronaxis run expression-extended.yaml --output result-expression-extended-yaml
```

为什么得到这些结果：由400V×10A得到4000W，在working事件选中的4秒内积分，4000×4=16000J。

[本次状态与表清单](examples/results/expression-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/expression-extended-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | 说明 | energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | working | 0 | 4 | 观测结束，活动尚未确认结束 | 数据缺失 | 16000.0 | 完整 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="expression-minimal-yaml"></a>
## expression-minimal.yaml

用途：派生功率最大值。配置：[下载](examples/expression-minimal.yaml)；功能说明：[阅读指南](expressions.md)。

```powershell
chronaxis run expression-minimal.yaml --output result-expression-minimal-yaml
```

为什么得到这些结果：先用voltage * current定义power；400V×10A=4000W。本例对派生功率取样本最大值，结果4000W。

[本次状态与表清单](examples/results/expression-minimal-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/expression-minimal-yaml/会话结果.csv)（1行）**

| maximum_power（W） | maximum_power：状态 | maximum_power：说明 |
| --- | --- | --- |
| 4000.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="input-asc-minimal-yaml"></a>
## input-asc-minimal.yaml

用途：ASC报文与DBC解码。配置：[下载](examples/input-asc-minimal.yaml)；功能说明：[阅读指南](inputs.md)。

```powershell
chronaxis run input-asc-minimal.yaml --output result-input-asc-minimal-yaml
```

为什么得到这些结果：ASC三条目标报文的原始码为1、3、1，DBC转换为3、7、3V；各保持1秒，积分3＋7＋3＝13V·s。

[本次状态与表清单](examples/results/input-asc-minimal-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/input-asc-minimal-yaml/会话结果.csv)（1行）**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="input-can-directory-yaml"></a>
## input-can-directory.yaml

用途：能量与均值/来源读取。配置：[下载](examples/input-can-directory.yaml)；功能说明：[阅读指南](quickstart.md)。

```powershell
chronaxis run input-can-directory.yaml --output result-input-can-directory-yaml
```

为什么得到这些结果：功率2、4、8、10W分别持续1、2、1、2秒：2×1＋4×2＋8×1＋10×2＝38J；四个更新的均值为6W；按时间加权为38/6W。

[本次状态与表清单](examples/results/input-can-directory-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/input-can-directory-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="input-csv-minimal-yaml"></a>
## input-csv-minimal.yaml

用途：CSV功率积分。配置：[下载](examples/input-csv-minimal.yaml)；功能说明：[阅读指南](inputs.md)。

```powershell
chronaxis run input-csv-minimal.yaml --output result-input-csv-minimal-yaml
```

为什么得到这些结果：四次功率更新2、4、8、10W分别保持1、2、1、2秒，积分38J。本例只请求积分，不输出均值。

[本次状态与表清单](examples/results/input-csv-minimal-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/input-csv-minimal-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="input-csv-offset-yaml"></a>
## input-csv-offset.yaml

用途：CSV时间校准。配置：[下载](examples/input-csv-offset.yaml)；功能说明：[阅读指南](inputs.md)。

```powershell
chronaxis run input-csv-offset.yaml --output result-input-csv-offset-yaml
```

为什么得到这些结果：给CSV时间加配置的固定偏移后与分析时钟对应；功率保持时长仍为1、2、1、2秒，积分38J。

[本次状态与表清单](examples/results/input-csv-offset-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/input-csv-offset-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="input-memory-minimal-yaml"></a>
## input-memory-minimal.yaml

用途：内存API输入。配置：[下载](examples/input-memory-minimal.yaml)；功能说明：[阅读指南](inputs.md)。

```powershell
chronaxis run input-memory-minimal.yaml --output result-input-memory-minimal-yaml
```

为什么得到这些结果：内存记录的功率先为2W、后为4W，各持续1秒，因此能量2×1＋4×1＝6J。此例专门说明内存记录，不是读取日志的默认入口。

[本次状态与表清单](examples/results/input-memory-minimal-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/input-memory-minimal-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 6.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="input-raw-csv-mapping-yaml"></a>
## input-raw-csv-mapping.yaml

用途：原始报文读取和DBC解码。配置：[下载](examples/input-raw-csv-mapping.yaml)；功能说明：[阅读指南](inputs.md)。

```powershell
chronaxis run input-raw-csv-mapping.yaml --output result-input-raw-csv-mapping-yaml
```

为什么得到这些结果：DBC将三个原始码1、3、1转换为3、7、3V，各保持1秒，面积3＋7＋3＝13V·s。原始CSV的列映射只改变怎样读取字段，不改变解码或计算。

[本次状态与表清单](examples/results/input-raw-csv-mapping-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/input-raw-csv-mapping-yaml/会话结果.csv)（1行）**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="input-raw-csv-minimal-yaml"></a>
## input-raw-csv-minimal.yaml

用途：原始报文读取和DBC解码。配置：[下载](examples/input-raw-csv-minimal.yaml)；功能说明：[阅读指南](inputs.md)。

```powershell
chronaxis run input-raw-csv-minimal.yaml --output result-input-raw-csv-minimal-yaml
```

为什么得到这些结果：DBC将三个原始码1、3、1转换为3、7、3V，各保持1秒，面积3＋7＋3＝13V·s。原始CSV的列映射只改变怎样读取字段，不改变解码或计算。

[本次状态与表清单](examples/results/input-raw-csv-minimal-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/input-raw-csv-minimal-yaml/会话结果.csv)（1行）**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="interval-actual-yaml"></a>
## interval-actual.yaml

用途：按真实时间间隔积分。配置：[下载](examples/interval-actual.yaml)；功能说明：[阅读指南](intervals.md)。

```powershell
chronaxis run interval-actual.yaml --output result-interval-actual-yaml
```

为什么得到这些结果：4000W在0、0.12、0.30秒更新，两个实际间隔为0.12和0.18秒，总计0.30秒，积分4000×0.30＝1200J。

[本次状态与表清单](examples/results/interval-actual-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/interval-actual-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 1200.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="interval-fixed-yaml"></a>
## interval-fixed.yaml

用途：按固定周期积分。配置：[下载](examples/interval-fixed.yaml)；功能说明：[阅读指南](intervals.md)。

```powershell
chronaxis run interval-fixed.yaml --output result-interval-fixed-yaml
```

为什么得到这些结果：记录仍在0、0.12、0.30秒，但两个计算间隔各使用配置的0.1秒，总计0.20秒，积分4000×0.20＝800J；原记录时间不改写。

[本次状态与表清单](examples/results/interval-fixed-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/interval-fixed-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 800.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="lookup-power-yaml"></a>
## lookup-power.yaml

用途：电压查表后的平均功率。配置：[下载](examples/lookup-power.yaml)；功能说明：[阅读指南](expressions.md)。

```powershell
chronaxis run lookup-power.yaml --output result-lookup-power-yaml
```

为什么得到这些结果：三次电压读数为3、7、3V。标定表中3V对应10W、11V对应50W，7V在线性插值后为30W。因此样本平均功率为(10＋30＋10)/3＝50/3W，约16.67W。

[本次状态与表清单](examples/results/lookup-power-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/lookup-power-yaml/会话结果.csv)（1行）**

| rated_power（W） | rated_power：状态 | rated_power：说明 |
| --- | --- | --- |
| 16.666666666666668 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="message-directions-yaml"></a>
## message-directions.yaml

用途：按方向分别累计消息。配置：[下载](examples/message-directions.yaml)；功能说明：[阅读指南](message-calculations.md)。

```powershell
chronaxis run message-directions.yaml --output result-message-directions-yaml
```

为什么得到这些结果：范围[0,3)内有三条4000W消息：0秒方向1，仅positive_energy贡献400J；1秒方向-1，仅negative_energy贡献400J；2秒方向0，两项均不累计。每条贡献=4000W×0.1s。两项各检查3条消息，contributions共6次求值：2次contributed、4次condition_false；两项各400J。3秒记录位于排除端点，不参加求值。

[本次状态与表清单](examples/results/message-directions-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/message-directions-yaml/会话结果.csv)（1行）**

| negative_energy（J） | negative_energy：状态 | negative_energy：说明 | positive_energy（J） | positive_energy：状态 | positive_energy：说明 |
| --- | --- | --- | --- | --- | --- |
| 400.0 | 完整 | — | 400.0 | 完整 | — |

**贡献明细：[下载完整 贡献明细.csv](examples/results/message-directions-yaml/贡献明细.csv)（6行）**

| 计算项 | 来源 | 原记录序号 | 求值序号 | 贡献值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| negative_energy | source_1 | 0 | 0 | — | 不满足条件，已跳过 |
| negative_energy | source_1 | 1 | 1 | 400.0 | 已计入 |
| negative_energy | source_1 | 2 | 2 | — | 不满足条件，已跳过 |
| positive_energy | source_1 | 0 | 0 | 400.0 | 已计入 |
| positive_energy | source_1 | 1 | 1 | — | 不满足条件，已跳过 |
| positive_energy | source_1 | 2 | 2 | — | 不满足条件，已跳过 |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="message-energy-yaml"></a>
## message-energy.yaml

用途：每条消息累计。配置：[下载](examples/message-energy.yaml)；功能说明：[阅读指南](message-calculations.md)。

```powershell
chronaxis run message-energy.yaml --output result-message-energy-yaml
```

为什么得到这些结果：每条完整消息按4000W×0.1s贡献400J，两条共800J，即使同一时刻也各算一次；缺失本条所需值时不沿用旧值。完整贡献例包含两条400J和一条missing_input跳过记录。

[本次状态与表清单](examples/results/message-energy-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/message-energy-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 800.0 | 部分有效 | 输入仅部分有效；数据缺失 |

**贡献明细：[下载完整 贡献明细.csv](examples/results/message-energy-yaml/贡献明细.csv)（3行）**

| 计算项 | 来源 | 原记录序号 | 求值序号 | 贡献值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| energy | source_1 | 0 | 0 | 400.0 | 已计入 |
| energy | source_1 | 1 | 1 | 400.0 | 已计入 |
| energy | source_1 | 2 | 2 | — | 缺少计算输入；数据缺失 |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="message-minimal-yaml"></a>
## message-minimal.yaml

用途：每条消息累计。配置：[下载](examples/message-minimal.yaml)；功能说明：[阅读指南](message-calculations.md)。

```powershell
chronaxis run message-minimal.yaml --output result-message-minimal-yaml
```

为什么得到这些结果：每条完整消息按4000W×0.1s贡献400J，两条共800J，即使同一时刻也各算一次；缺失本条所需值时不沿用旧值。

[本次状态与表清单](examples/results/message-minimal-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/message-minimal-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 800.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="power-statistics-yaml"></a>
## power-statistics.yaml

用途：功率波动与加载均值的P95。配置：[下载](examples/power-statistics.yaml)；功能说明：[阅读指南](calculations.md#v4-power-statistics)。

```powershell
chronaxis run power-statistics.yaml --output result-power-statistics-yaml
```

为什么得到这些结果：五条读数为0、10、0、20、0W，均值6W，离均差平方和320W²；样本方差除以4得80W²，总体标准差为8W。0、10、20W分别保持4、3、2秒，时间均方根为√(1100/9)W。读数排序后P95为18W；两段加载[1,4)、[5,7)秒的均值为10、20W，它们的P95为19.5W，候选及参与均为2。其余计数、方差和中位数的手算见统计指南。

[本次状态与表清单](examples/results/power-statistics-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/power-statistics-yaml/事件结果.csv)（4行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | load_mean（W） | load_mean：状态 | load_mean：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | load_start | 1 | 1 | — | 瞬时事件 | — | — | 无此项结果 | — |
| 2 | load_start | 5 | 5 | — | 瞬时事件 | — | — | 无此项结果 | — |
| 3 | loaded | 1 | 1 | 4 | 正常结束 | — | 10.0 | 完整 | — |
| 4 | loaded | 5 | 5 | 7 | 正常结束 | — | 20.0 | 完整 | — |

**会话结果：[下载完整 会话结果.csv](examples/results/power-statistics-yaml/会话结果.csv)（1行）**

| cycles（1） | cycles：状态 | cycles：说明 | held_rms（W） | held_rms：状态 | held_rms：说明 | held_spread（W） | held_spread：状态 | held_spread：说明 | held_variance（V^2*A^2） | held_variance：状态 | held_variance：说明 | loads（1） | loads：状态 | loads：说明 | reading_median（W） | reading_median：状态 | reading_median：说明 | reading_p95（W） | reading_p95：状态 | reading_p95：说明 | reading_rms（W） | reading_rms：状态 | reading_rms：说明 | reading_spread（W） | reading_spread：状态 | reading_spread：说明 | reading_variance（V^2*A^2） | reading_variance：状态 | reading_variance：说明 | readings（1） | readings：状态 | readings：说明 | starts（1） | starts：状态 | starts：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 完整 | — | 11.055415967851332 | 完整 | — | 7.85674201318386 | 完整 | — | 61.72839506172837 | 完整 | — | 2 | 完整 | — | 0.0 | 完整 | — | 18.0 | 完整 | — | 10.0 | 完整 | — | 8.000000000000002 | 完整 | — | 80.00000000000004 | 完整 | — | 5 | 完整 | — | 2 | 完整 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/power-statistics-yaml/窗口结果.csv)（1行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | test_cycle | 1 | 8.5 | 完整 | 3、4 | — |

**聚合结果：[下载完整 聚合结果.csv](examples/results/power-statistics-yaml/聚合结果.csv)（1行）**

| 聚合项 | 分组 | 结果 | 单位 | 状态 | 原因 | 候选数 | 参与数 | 定义排除数 | 质量排除数 | 参与的部分值 | 匹配 | 确认超时 | 观测不足 | 未决 | 已完整发现总体 | 质量说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| load_mean_p95 | {"session_id":"power_bench"} | 19.5 | W | 完整 | 正常 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 是 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-charge-energy-yaml"></a>
## preset-charge-energy.yaml

用途：充电活动与累计量。配置：[下载](examples/preset-charge-energy.yaml)；功能说明：[阅读指南](presets.md)。

```powershell
chronaxis run preset-charge-energy.yaml --output result-preset-charge-energy-yaml
```

为什么得到这些结果：充电活动[1,3)持续2秒；400V×10A×2s=8000J=8000/3600Wh，10A×2s=20As=20/3600Ah。

[本次状态与表清单](examples/results/preset-charge-energy-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/preset-charge-energy-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | 说明 | demo_preset_charge（Ah） | demo_preset_charge：状态 | demo_preset_charge：说明 | demo_preset_energy（Wh） | demo_preset_energy：状态 | demo_preset_energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1 | 3 | 正常结束 | — | 0.005555555555555556 | 完整 | — | 2.2222222222222223 | 完整 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-charge-minimal-yaml"></a>
## preset-charge-minimal.yaml

用途：充电活动检测。配置：[下载](examples/preset-charge-minimal.yaml)；功能说明：[阅读指南](presets.md)。

```powershell
chronaxis run preset-charge-minimal.yaml --output result-preset-charge-minimal-yaml
```

为什么得到这些结果：电流与模式满足配置条件，产生[1,3)秒活动。本例未请求能量或电荷量计算。

[本次状态与表清单](examples/results/preset-charge-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/preset-charge-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1 | 1 | 3 | 正常结束 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-command-automatic-yaml"></a>
## preset-command-automatic.yaml

用途：请求响应配对。配置：[下载](examples/preset-command-automatic.yaml)；功能说明：[阅读指南](sequences.md)。

```powershell
chronaxis run preset-command-automatic.yaml --output result-preset-command-automatic-yaml
```

为什么得到这些结果：开始边沿与响应边沿相差1秒，在配置允许的等待范围内，因此匹配成功且delay_ns=1000000000。本例按配置中的请求与响应规则配对，查看配对结果.csv的配对状态和延迟（s）。

[本次状态与表清单](examples/results/preset-command-automatic-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/preset-command-automatic-yaml/事件结果.csv)（2行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_request | 1 | 1 | — | 瞬时事件 | — |
| 2 | demo_preset_response | 2 | 2 | — | 瞬时事件 | — |

**配对结果：[下载完整 配对结果.csv](examples/results/preset-command-automatic-yaml/配对结果.csv)（1行）**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_pair | 1 | 2 | 2 | 1 | 已响应 | — |

本次没有窗口结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-command-minimal-yaml"></a>
## preset-command-minimal.yaml

用途：请求响应配对。配置：[下载](examples/preset-command-minimal.yaml)；功能说明：[阅读指南](sequences.md)。

```powershell
chronaxis run preset-command-minimal.yaml --output result-preset-command-minimal-yaml
```

为什么得到这些结果：开始边沿与响应边沿相差1秒，在配置允许的等待范围内，因此匹配成功且delay_ns=1000000000。本例按配置中的请求与响应规则配对，查看配对结果.csv的配对状态和延迟（s）。

[本次状态与表清单](examples/results/preset-command-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/preset-command-minimal-yaml/事件结果.csv)（2行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_request | 1 | 1 | — | 瞬时事件 | — |
| 2 | demo_preset_response | 2 | 2 | — | 瞬时事件 | — |

**配对结果：[下载完整 配对结果.csv](examples/results/preset-command-minimal-yaml/配对结果.csv)（1行）**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_pair | 1 | 2 | 2 | 1 | 已响应 | — |

本次没有窗口结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-fault-context-yaml"></a>
## preset-fault-context.yaml

用途：报警前后窗口。配置：[下载](examples/preset-fault-context.yaml)；功能说明：[阅读指南](presets.md)。

```powershell
chronaxis run preset-fault-context.yaml --output result-preset-fault-context-yaml
```

为什么得到这些结果：1秒报警上升沿产生点事件；pre=1s、post=2s得到[0,3)窗口，不是把报警活动向前后延长。

[本次状态与表清单](examples/results/preset-fault-context-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/preset-fault-context-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_alarm | 1 | 1 | — | 瞬时事件 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/preset-fault-context-yaml/窗口结果.csv)（1行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_context | 0 | 3 | 完整 | 1 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-fault-minimal-yaml"></a>
## preset-fault-minimal.yaml

用途：报警点后的窗口。配置：[下载](examples/preset-fault-minimal.yaml)；功能说明：[阅读指南](presets.md)。

```powershell
chronaxis run preset-fault-minimal.yaml --output result-preset-fault-minimal-yaml
```

为什么得到这些结果：1秒报警上升沿产生点事件，end_ns为空。pre=0s、post=1s得到[1,2)窗口；窗口长度不是报警持续时长。

[本次状态与表清单](examples/results/preset-fault-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/preset-fault-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_alarm | 1 | 1 | — | 瞬时事件 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/preset-fault-minimal-yaml/窗口结果.csv)（1行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_context | 1 | 2 | 完整 | 1 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-threshold-delay-yaml"></a>
## preset-threshold-delay.yaml

用途：确认等待后的报警。配置：[下载](examples/preset-threshold-delay.yaml)；功能说明：[阅读指南](presets.md)。

```powershell
chronaxis run preset-threshold-delay.yaml --output result-preset-threshold-delay-yaml
```

为什么得到这些结果：进入和退出均需500ms确认，活动[1.5,3.5)累计2秒；初始还在等待退出确认，整体摘要partial。

[本次状态与表清单](examples/results/preset-threshold-delay-yaml/result-summary.json)：`completed`。

阈值预设的会话摘要：

|预设|累计秒数|状态|
|---|---|---|
|demo_preset|2.0|partial|

**事件结果：[下载完整 事件结果.csv](examples/results/preset-threshold-delay-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | demo_preset_duration（s） | demo_preset_duration：状态 | demo_preset_duration：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1.5 | 1.5 | 3.5 | 正常结束 | — | 2.0 | 完整 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-threshold-minimal-yaml"></a>
## preset-threshold-minimal.yaml

用途：迟滞报警时长。配置：[下载](examples/preset-threshold-minimal.yaml)；功能说明：[阅读指南](presets.md)。

```powershell
chronaxis run preset-threshold-minimal.yaml --output result-preset-threshold-minimal-yaml
```

为什么得到这些结果：温度1秒达到80℃进入报警，3秒达到75℃退出，活动[1,3)累计2秒。

[本次状态与表清单](examples/results/preset-threshold-minimal-yaml/result-summary.json)：`completed`。

阈值预设的会话摘要：

|预设|累计秒数|状态|
|---|---|---|
|demo_preset|2.0|complete|

**事件结果：[下载完整 事件结果.csv](examples/results/preset-threshold-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | demo_preset_duration（s） | demo_preset_duration：状态 | demo_preset_duration：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1 | 1 | 3 | 正常结束 | — | 2.0 | 完整 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="preset-threshold-partial-yaml"></a>
## preset-threshold-partial.yaml

用途：初始状态未知的报警。配置：[下载](examples/preset-threshold-partial.yaml)；功能说明：[阅读指南](presets.md)。

```powershell
chronaxis run preset-threshold-partial.yaml --output result-preset-threshold-partial-yaml
```

为什么得到这些结果：最初温度位于进入和退出阈值之间，无法确定初始状态；可确认[1,3)报警2秒，整体摘要partial。

[本次状态与表清单](examples/results/preset-threshold-partial-yaml/result-summary.json)：`completed`。

阈值预设的会话摘要：

|预设|累计秒数|状态|
|---|---|---|
|demo_preset|2.0|partial|

**事件结果：[下载完整 事件结果.csv](examples/results/preset-threshold-partial-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | demo_preset_duration（s） | demo_preset_duration：状态 | demo_preset_duration：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1 | 1 | 3 | 正常结束 | — | 2.0 | 完整 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="quality-yaml"></a>
## quality.yaml

用途：无效码和过期。配置：[下载](examples/quality.yaml)；功能说明：[阅读指南](results.md)。

```powershell
chronaxis run quality.yaml --output result-quality-yaml
```

为什么得到这些结果：0秒10W，1秒命中显式无效码，2秒恢复10W，有效期1秒，4秒结束。仅[0,1)、[2,3)有效：10×1＋10×1＝20J；quality=18表示无效码OUT_OF_RANGE16与过期STALE2。partial说明20J只覆盖已知部分。

[本次状态与表清单](examples/results/quality-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/quality-yaml/会话结果.csv)（1行）**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 20.0 | 部分有效 | 仅统计有效部分；数据过期；数值超出允许范围 |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-condition_duration-extended-yaml"></a>
## rule-condition_duration-extended.yaml

用途：事件规则：condition_duration。配置：[下载](examples/rule-condition_duration-extended.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-condition_duration-extended.yaml --output result-rule-condition_duration-extended-yaml
```

为什么得到这些结果：活动仍为[1,6)，selection_origin=confirmed从3秒起计算，10W×3s=30J。

[本次状态与表清单](examples/results/rule-condition_duration-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-condition_duration-extended-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | 说明 | energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 6 | 正常结束 | — | 30.0 | 完整 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-condition_duration-minimal-yaml"></a>
## rule-condition_duration-minimal.yaml

用途：事件规则：condition_duration。配置：[下载](examples/rule-condition_duration-minimal.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-condition_duration-minimal.yaml --output result-rule-condition_duration-minimal-yaml
```

为什么得到这些结果：温度1秒达到条件，持续2秒后于3秒确认，6秒解除，活动为[1,6)。

[本次状态与表清单](examples/results/rule-condition_duration-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-condition_duration-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 3 | 6 | 正常结束 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-debounce-extended-yaml"></a>
## rule-debounce-extended.yaml

用途：事件规则：debounce。配置：[下载](examples/rule-debounce-extended.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-debounce-extended.yaml --output result-rule-debounce-extended-yaml
```

为什么得到这些结果：进入与退出均按配置等待确认，最终确认区间[3,8)；等待中不立即切换状态。

[本次状态与表清单](examples/results/rule-debounce-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-debounce-extended-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 3 | 3 | 8 | 正常结束 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-debounce-minimal-yaml"></a>
## rule-debounce-minimal.yaml

用途：事件规则：debounce。配置：[下载](examples/rule-debounce-minimal.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-debounce-minimal.yaml --output result-rule-debounce-minimal-yaml
```

为什么得到这些结果：本例稳定状态区间为[1,5)，未增加额外等待。

[本次状态与表清单](examples/results/rule-debounce-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-debounce-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | 5 | 正常结束 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-falling_edge-extended-yaml"></a>
## rule-falling_edge-extended.yaml

用途：事件规则：falling_edge。配置：[下载](examples/rule-falling_edge-extended.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-falling_edge-extended.yaml --output result-rule-falling_edge-extended-yaml
```

为什么得到这些结果：5秒下降沿后取[5,6)窗口，10W×1s=10J。

[本次状态与表清单](examples/results/rule-falling_edge-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-falling_edge-extended-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 5 | 5 | — | 瞬时事件 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/rule-falling_edge-extended-yaml/窗口结果.csv)（1行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 | energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 5 | 6 | 完整 | 1 | — | 10.0 | 完整 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-falling_edge-minimal-yaml"></a>
## rule-falling_edge-minimal.yaml

用途：事件规则：falling_edge。配置：[下载](examples/rule-falling_edge-minimal.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-falling_edge-minimal.yaml --output result-rule-falling_edge-minimal-yaml
```

为什么得到这些结果：5秒开关由真变假，产生一个下降沿点事件。

[本次状态与表清单](examples/results/rule-falling_edge-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-falling_edge-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 5 | 5 | — | 瞬时事件 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-hysteresis-extended-yaml"></a>
## rule-hysteresis-extended.yaml

用途：事件规则：hysteresis。配置：[下载](examples/rule-hysteresis-extended.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-hysteresis-extended.yaml --output result-rule-hysteresis-extended-yaml
```

为什么得到这些结果：迟滞规则增加进入和退出等待后，报警区间为[2,7)。

[本次状态与表清单](examples/results/rule-hysteresis-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-hysteresis-extended-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 2 | 2 | 7 | 正常结束 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-hysteresis-minimal-yaml"></a>
## rule-hysteresis-minimal.yaml

用途：事件规则：hysteresis。配置：[下载](examples/rule-hysteresis-minimal.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-hysteresis-minimal.yaml --output result-rule-hysteresis-minimal-yaml
```

为什么得到这些结果：进入和退出采用不同阈值，中间温度沿用已知状态，报警区间[1,6)。

[本次状态与表清单](examples/results/rule-hysteresis-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-hysteresis-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | 6 | 正常结束 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-rising_edge-extended-yaml"></a>
## rule-rising_edge-extended.yaml

用途：事件规则：rising_edge。配置：[下载](examples/rule-rising_edge-extended.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-rising_edge-extended.yaml --output result-rule-rising_edge-extended-yaml
```

为什么得到这些结果：1秒上升沿产生点事件，向后取1秒窗口[1,2)，10W×1s=10J。

[本次状态与表清单](examples/results/rule-rising_edge-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-rising_edge-extended-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | — | 瞬时事件 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/rule-rising_edge-extended-yaml/窗口结果.csv)（1行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 | energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 2 | 完整 | 1 | — | 10.0 | 完整 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-rising_edge-minimal-yaml"></a>
## rule-rising_edge-minimal.yaml

用途：事件规则：rising_edge。配置：[下载](examples/rule-rising_edge-minimal.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-rising_edge-minimal.yaml --output result-rule-rising_edge-minimal-yaml
```

为什么得到这些结果：1秒开关由假变真，产生一个上升沿点事件。

[本次状态与表清单](examples/results/rule-rising_edge-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-rising_edge-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | — | 瞬时事件 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-start_end-extended-yaml"></a>
## rule-start_end-extended.yaml

用途：事件规则：start_end。配置：[下载](examples/rule-start_end-extended.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-start_end-extended.yaml --output result-rule-start_end-extended-yaml
```

为什么得到这些结果：1秒开始后最多等待2秒，3秒因timeout结束，不等到5秒的结束条件。

[本次状态与表清单](examples/results/rule-start_end-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-start_end-extended-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | 3 | 超时结束 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-start_end-minimal-yaml"></a>
## rule-start_end-minimal.yaml

用途：事件规则：start_end。配置：[下载](examples/rule-start_end-minimal.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-start_end-minimal.yaml --output result-rule-start_end-minimal-yaml
```

为什么得到这些结果：1秒收到开始条件，5秒收到结束条件，活动为[1,5)。

[本次状态与表清单](examples/results/rule-start_end-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-start_end-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | 5 | 正常结束 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-start_only-extended-yaml"></a>
## rule-start_only-extended.yaml

用途：事件规则：start_only。配置：[下载](examples/rule-start_only-extended.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-start_only-extended.yaml --output result-rule-start_only-extended-yaml
```

为什么得到这些结果：1秒和6秒启动后各选择5秒窗口，分别为[1,6)与[6,11)。

[本次状态与表清单](examples/results/rule-start_only-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-start_only-extended-yaml/事件结果.csv)（2行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | — | 瞬时事件 | — |
| 2 | detected | 6 | 6 | — | 瞬时事件 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/rule-start_only-extended-yaml/窗口结果.csv)（2行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 6 | 完整 | 1 | — |
| 2 | context | 6 | 11 | 完整 | 2 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-start_only-minimal-yaml"></a>
## rule-start_only-minimal.yaml

用途：事件规则：start_only。配置：[下载](examples/rule-start_only-minimal.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-start_only-minimal.yaml --output result-rule-start_only-minimal-yaml
```

为什么得到这些结果：1秒和6秒各产生一次启动点，持续为真不会不断重触发。

[本次状态与表清单](examples/results/rule-start_only-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-start_only-minimal-yaml/事件结果.csv)（2行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | — | 瞬时事件 | — |
| 2 | detected | 6 | 6 | — | 瞬时事件 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-window_delta-extended-yaml"></a>
## rule-window_delta-extended.yaml

用途：事件规则：window_delta。配置：[下载](examples/rule-window_delta-extended.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-window_delta-extended.yaml --output result-rule-window_delta-extended-yaml
```

为什么得到这些结果：允许初始窗口判断，4秒和12秒各触发一次；首个触发标记为initial。

[本次状态与表清单](examples/results/rule-window_delta-extended-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-window_delta-extended-yaml/事件结果.csv)（2行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 4 | 4 | — | 瞬时事件 | — |
| 2 | detected | 12 | 12 | — | 瞬时事件 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="rule-window_delta-minimal-yaml"></a>
## rule-window_delta-minimal.yaml

用途：事件规则：window_delta。配置：[下载](examples/rule-window_delta-minimal.yaml)；功能说明：[阅读指南](rules.md)。

```powershell
chronaxis run rule-window_delta-minimal.yaml --output result-rule-window_delta-minimal-yaml
```

为什么得到这些结果：比较完整回看窗口内的变化，在12秒触发一次。

[本次状态与表清单](examples/results/rule-window_delta-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/rule-window_delta-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 12 | 12 | — | 瞬时事件 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="sequence-minimal-yaml"></a>
## sequence-minimal.yaml

用途：请求响应配对。配置：[下载](examples/sequence-minimal.yaml)；功能说明：[阅读指南](sequences.md)。

```powershell
chronaxis run sequence-minimal.yaml --output result-sequence-minimal-yaml
```

为什么得到这些结果：开始边沿与响应边沿相差1秒，在配置允许的等待范围内，因此匹配成功且delay_ns=1000000000。本例按配置中的请求与响应规则配对，查看配对结果.csv的配对状态和延迟（s）。

[本次状态与表清单](examples/results/sequence-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/sequence-minimal-yaml/事件结果.csv)（2行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 2 | response_edge | 2 | 2 | — | 瞬时事件 | — |

**配对结果：[下载完整 配对结果.csv](examples/results/sequence-minimal-yaml/配对结果.csv)（1行）**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 1 | 2 | 2 | 1 | 已响应 | — |

本次没有窗口结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="sequence-outcomes-yaml"></a>
## sequence-outcomes.yaml

用途：匹配、无响应和无法确定。配置：[下载](examples/sequence-outcomes.yaml)；功能说明：[阅读指南](sequences.md)。

```powershell
chronaxis run sequence-outcomes.yaml --output result-sequence-outcomes-yaml
```

为什么得到这些结果：三种等待分别得到matched、no_response和indeterminate：收到符合条件响应；观测完整却到时无响应；或者缺数据/观测提前结束而无法下结论。不能把最后一种当作无响应。

[本次状态与表清单](examples/results/sequence-outcomes-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/sequence-outcomes-yaml/事件结果.csv)（4行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 2 | request_edge | 3 | 3 | — | 瞬时事件 | — |
| 3 | request_edge | 6 | 6 | — | 瞬时事件 | — |
| 4 | response_edge | 2 | 2 | — | 瞬时事件 | — |

**配对结果：[下载完整 配对结果.csv](examples/results/sequence-outcomes-yaml/配对结果.csv)（3行）**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 1 | 4 | 2 | 1 | 已响应 | — |
| 2 | pair | 2 | — | 5 | — | 时限内未响应 | — |
| 3 | pair | 3 | — | 8 | — | 无法确定 | 数值超出允许范围 |

本次没有窗口结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="signal-bool-minimal-yaml"></a>
## signal-bool-minimal.yaml

用途：布尔开关边沿。配置：[下载](examples/signal-bool-minimal.yaml)；功能说明：[阅读指南](signals.md)。

```powershell
chronaxis run signal-bool-minimal.yaml --output result-signal-bool-minimal-yaml
```

为什么得到这些结果：Enabled在100ms从整数0变1，choices把它们映成false/true，产生一次上升沿。

[本次状态与表清单](examples/results/signal-bool-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/signal-bool-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | activated | 0.1 | 0.1 | — | 瞬时事件 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="signal-enum-minimal-yaml"></a>
## signal-enum-minimal.yaml

用途：枚举状态边沿。配置：[下载](examples/signal-enum-minimal.yaml)；功能说明：[阅读指南](signals.md)。

```powershell
chronaxis run signal-enum-minimal.yaml --output result-signal-enum-minimal-yaml
```

为什么得到这些结果：ModeCode在100ms从0变7，DBC枚举表给出idle/running；mode == "running"由假变真，产生上升沿。

[本次状态与表清单](examples/results/signal-enum-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/signal-enum-minimal-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | activated | 0.1 | 0.1 | — | 瞬时事件 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="signal-number-conversion-yaml"></a>
## signal-number-conversion.yaml

用途：电流单位换算。配置：[下载](examples/signal-number-conversion.yaml)；功能说明：[阅读指南](signals.md)。

```powershell
chronaxis run signal-number-conversion.yaml --output result-signal-number-conversion-yaml
```

为什么得到这些结果：DBC解码得到5000、7000、5000、5000mA，再按mA到A的单位关系自动乘0.001换为A，最大值7A；没有命中本例声明的异常码。

[本次状态与表清单](examples/results/signal-number-conversion-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/signal-number-conversion-yaml/会话结果.csv)（1行）**

| maximum_current（A） | maximum_current：状态 | maximum_current：说明 |
| --- | --- | --- |
| 7.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="signal-number-minimal-yaml"></a>
## signal-number-minimal.yaml

用途：DBC电流最大值。配置：[下载](examples/signal-number-minimal.yaml)；功能说明：[阅读指南](signals.md)。

```powershell
chronaxis run signal-number-minimal.yaml --output result-signal-number-minimal-yaml
```

为什么得到这些结果：DBC解码值5000、7000、5000、5000mA，sample_maximum取最大值，并按计算项指定的mA输出7000mA。

[本次状态与表清单](examples/results/signal-number-minimal-yaml/result-summary.json)：`completed`。

**会话结果：[下载完整 会话结果.csv](examples/results/signal-number-minimal-yaml/会话结果.csv)（1行）**

| maximum_current（mA） | maximum_current：状态 | maximum_current：说明 |
| --- | --- | --- |
| 7000.0 | 完整 | — |

本次没有事件、窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="signal-state-combined-yaml"></a>
## signal-state-combined.yaml

用途：组合状态边沿。配置：[下载](examples/signal-state-combined.yaml)；功能说明：[阅读指南](signals.md)。

```powershell
chronaxis run signal-state-combined.yaml --output result-signal-state-combined-yaml
```

为什么得到这些结果：100ms时Enabled变1且ModeCode变7，映射后开关为true且状态为running；组合条件由假变真。

[本次状态与表清单](examples/results/signal-state-combined-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/signal-state-combined-yaml/事件结果.csv)（1行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | enabled_running | 0.1 | 0.1 | — | 瞬时事件 | — |

本次没有窗口、请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="start-end-yaml"></a>
## start-end.yaml

用途：开始、正常结束及超时。配置：[下载](examples/start-end.yaml)；功能说明：[阅读指南](examples.md#start-end-case)。

```powershell
chronaxis run start-end.yaml --output result-start-end-yaml
```

为什么得到这些结果：三段活动分别是[0,2)、[4,9)、[11,14)秒，对无量纲value取时间加权均值：(10×2)/2=10、(40×2+60×3)/5=52、(110×3)/3=110，单位均为1。第二段因timeout=5s结束。默认事件结果.csv在同一行给出开始/确认/结束时间及cycle_mean，不需手工拼表；显式交换格式的关联见[结果表实例ID](results.md#用实例id关联三张结果表)。

[本次状态与表清单](examples/results/start-end-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/start-end-yaml/事件结果.csv)（3行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | cycle_mean（1） | cycle_mean：状态 | cycle_mean：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cycle | 0 | 0 | 2 | 正常结束 | — | 10.0 | 完整 | — |
| 2 | cycle | 4 | 4 | 9 | 超时结束 | — | 52.0 | 完整 | — |
| 3 | cycle | 11 | 11 | 14 | 正常结束 | — | 110.0 | 完整 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/start-end-yaml/窗口结果.csv)（3行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | cycle_window | 0 | 2 | 完整 | 1 | — |
| 2 | cycle_window | 4 | 9 | 完整 | 2 | — |
| 3 | cycle_window | 11 | 14 | 完整 | 3 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="timing-actual-yaml"></a>
## timing-actual.yaml

用途：真实时间下的规则和配对。配置：[下载](examples/timing-actual.yaml)；功能说明：[阅读指南](intervals.md)。

```powershell
chronaxis run timing-actual.yaml --output result-timing-actual-yaml
```

为什么得到这些结果：采用报文实际时刻差：请求响应延迟2秒，温度条件累计5秒。规则等待、窗口和计算均使用实际时间依据，见时间间隔指南的同组输入对照。

[本次状态与表清单](examples/results/timing-actual-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/timing-actual-yaml/事件结果.csv)（5行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | change | 4 | 4 | — | 瞬时事件 | — |
| 2 | change | 6 | 6 | — | 瞬时事件 | — |
| 3 | hot | 1 | 2.5 | 6 | 正常结束 | — |
| 4 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 5 | response_edge | 3 | 3 | — | 瞬时事件 | — |

**会话结果：[下载完整 会话结果.csv](examples/results/timing-actual-yaml/会话结果.csv)（1行）**

| hot_duration（s） | hot_duration：状态 | hot_duration：说明 |
| --- | --- | --- |
| 5.0 | 完整 | — |

**配对结果：[下载完整 配对结果.csv](examples/results/timing-actual-yaml/配对结果.csv)（1行）**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 4 | 5 | 3 | 2 | 已响应 | — |

本次没有窗口结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="timing-dbc-yaml"></a>
## timing-dbc.yaml

用途：DBC周期下的规则和配对。配置：[下载](examples/timing-dbc.yaml)；功能说明：[阅读指南](intervals.md)。

```powershell
chronaxis run timing-dbc.yaml --output result-timing-dbc-yaml
```

为什么得到这些结果：从request所属DBC报文取得1秒周期，每次驱动更新推进一次；本例请求响应延迟1秒，温度条件累计2秒。没有驱动更新时不自行追加周期。

[本次状态与表清单](examples/results/timing-dbc-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/timing-dbc-yaml/事件结果.csv)（4行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | change | 7 | 7 | — | 瞬时事件 | — |
| 2 | hot | 1 | 6 | 6 | 正常结束 | — |
| 3 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 4 | response_edge | 3 | 3 | — | 瞬时事件 | — |

**会话结果：[下载完整 会话结果.csv](examples/results/timing-dbc-yaml/会话结果.csv)（1行）**

| hot_duration（s） | hot_duration：状态 | hot_duration：说明 |
| --- | --- | --- |
| 2.0 | 完整 | — |

**配对结果：[下载完整 配对结果.csv](examples/results/timing-dbc-yaml/配对结果.csv)（1行）**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 3 | 4 | 3 | 1 | 已响应 | — |

本次没有窗口结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="timing-fixed-yaml"></a>
## timing-fixed.yaml

用途：固定周期下的规则和配对。配置：[下载](examples/timing-fixed.yaml)；功能说明：[阅读指南](intervals.md)。

```powershell
chronaxis run timing-fixed.yaml --output result-timing-fixed-yaml
```

为什么得到这些结果：request是驱动信号，每次驱动推进配置的1秒；本例请求响应延迟1秒，温度条件累计2秒。没有驱动更新时不自行追加周期。

[本次状态与表清单](examples/results/timing-fixed-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/timing-fixed-yaml/事件结果.csv)（4行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | change | 7 | 7 | — | 瞬时事件 | — |
| 2 | hot | 1 | 6 | 6 | 正常结束 | — |
| 3 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 4 | response_edge | 3 | 3 | — | 瞬时事件 | — |

**会话结果：[下载完整 会话结果.csv](examples/results/timing-fixed-yaml/会话结果.csv)（1行）**

| hot_duration（s） | hot_duration：状态 | hot_duration：说明 |
| --- | --- | --- |
| 2.0 | 完整 | — |

**配对结果：[下载完整 配对结果.csv](examples/results/timing-fixed-yaml/配对结果.csv)（1行）**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 3 | 4 | 3 | 1 | 已响应 | — |

本次没有窗口结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="window-exit-delay-yaml"></a>
## window-exit-delay.yaml

用途：围绕事件选窗口。配置：[下载](examples/window-exit-delay.yaml)；功能说明：[阅读指南](windows.md)。

```powershell
chronaxis run window-exit-delay.yaml --output result-window-exit-delay-yaml
```

为什么得到这些结果：条件产生三段真实活动[1,2)、[3,4)、[6,7)。每段结束后等待2秒：3秒的活动在首次等待截止4秒之前开始；6秒的活动恰在第二次截止6秒开始，仍合并。最后7秒结束后等到9秒关闭，片段为[1,9)。中间条件为假的时间不变成真实活动。

[本次状态与表清单](examples/results/window-exit-delay-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/window-exit-delay-yaml/事件结果.csv)（3行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | pressed | 1 | 1 | 2 | 正常结束 | — |
| 2 | pressed | 3 | 3 | 4 | 正常结束 | — |
| 3 | pressed | 6 | 6 | 7 | 正常结束 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/window-exit-delay-yaml/窗口结果.csv)（1行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 9 | 完整 | 1、2、3 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="window-merged-yaml"></a>
## window-merged.yaml

用途：围绕事件选窗口。配置：[下载](examples/window-merged.yaml)；功能说明：[阅读指南](windows.md)。

```powershell
chronaxis run window-merged.yaml --output result-window-merged-yaml
```

为什么得到这些结果：1、3、6秒的上升沿各向后扩展3秒，先得到[1,4)、[3,6)、[6,9)。merge=overlap_and_adjacent把重叠或首尾相接的区间合为[1,9)。

[本次状态与表清单](examples/results/window-merged-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/window-merged-yaml/事件结果.csv)（3行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | pressed | 1 | 1 | — | 瞬时事件 | — |
| 2 | pressed | 3 | 3 | — | 瞬时事件 | — |
| 3 | pressed | 6 | 6 | — | 瞬时事件 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/window-merged-yaml/窗口结果.csv)（1行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 9 | 完整 | 1、2、3 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


<a id="window-minimal-yaml"></a>
## window-minimal.yaml

用途：围绕事件选窗口。配置：[下载](examples/window-minimal.yaml)；功能说明：[阅读指南](windows.md)。

```powershell
chronaxis run window-minimal.yaml --output result-window-minimal-yaml
```

为什么得到这些结果：button_pressed在1、3、6秒从假变真，产生三个上升沿点事件。pre=0s、post=3s分别得到[1,4)、[3,6)、[6,9)；本例不合并窗口。

[本次状态与表清单](examples/results/window-minimal-yaml/result-summary.json)：`completed`。

**事件结果：[下载完整 事件结果.csv](examples/results/window-minimal-yaml/事件结果.csv)（3行）**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | pressed | 1 | 1 | — | 瞬时事件 | — |
| 2 | pressed | 3 | 3 | — | 瞬时事件 | — |
| 3 | pressed | 6 | 6 | — | 瞬时事件 | — |

**窗口结果：[下载完整 窗口结果.csv](examples/results/window-minimal-yaml/窗口结果.csv)（3行）**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 4 | 完整 | 1 | — |
| 2 | context | 3 | 6 | 完整 | 2 | — |
| 3 | context | 6 | 9 | 完整 | 3 | — |

本次没有请求响应结果表：只显示配置请求且实际产生的结果；未请求的表不会为教程额外生成。需要事件/窗口的其他例子请按上方索引查看。


## 不能独立运行的定义文件

|配置|为何没有独立结果|在哪里查看完整任务结果|
|---|---|---|
|[teaching-base.yaml](examples/teaching-base.yaml)|只声明教学来源和信号，没有请求事件或计算。|[持续条件完整例](#rule-condition_duration-extended-yaml)、[规则指南](rules.md)|
|[electrical-base.yaml](examples/electrical-base.yaml)|只声明电压、电流等信号，需加表达式或预设。|[表达式完整例](#expression-extended-yaml)、[充电完整例](#preset-charge-energy-yaml)|
|[shared/definitions.yaml](examples/shared/definitions.yaml)|imports公共定义，需要主配置指定要做什么。|[analysis-imports.yaml实际结果](#analysis-imports-yaml)|

这些文件未计作独立运行成功。正文里的片段也不单独声称有结果：先跟随所属章节的完整配置链接，再在本页查对应文件。

## 重新生成与核验

在源码仓库根目录，安装项目及CAN依赖后运行；工作目录须不存在。默认只在指定工作目录生成一份结果草稿，`--publish`才更新手册：

```powershell
python tools/build_example_results.py --work work/manual-results-new --publish
python tools/build_example_results.py --check
```

生成时先执行76份YAML并核对案例对应的独立数学断言，再执行2份JSON及规则、时间、窗口等已有脚本的明确预期；解释文字单独维护，不由实测倒推。`--check`核对配置解析值、输入和结果文件摘要：配置注释/缩进不影响摘要，输入和结果按实际字节检查；它只证明文件一致性，不替代重新执行。

生成来源标签可用`--device-label home`或`--device-label work`按实际设备填写；省略时读取CHRONAXIS_DEVICE_LABEL，未知则记pending。它只标注本次结果文件，不修改原教学输入的来源。
