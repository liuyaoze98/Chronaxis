# 示例与模板

按目标选择完整任务。所有随附数据都是可手工复算的合成数据；换成真实日志时应重新确认单位、有效期、方向、同步与业务阈值。

[逐配置实际结果与解释](example-results.md)提供按实际清单列出的可运行YAML、JSON和批量配置的运行命令、实际结果表、手算过程及CSV下载。先选配置，再按文件名查结果。两份基础配置和shared/definitions公共定义只用于组合，不作为独立分析成功案例。

常用结果：[能量与均值](example-results.md#analysis-yaml)、[事件与窗口](example-results.md#activity-yaml)、[无效值与过期](example-results.md#quality-yaml)、[实际间隔](example-results.md#interval-actual-yaml)／[固定间隔](example-results.md#interval-fixed-yaml)、[状态映射](example-results.md#signal-state-combined-yaml)。

## 先选并行运行方式

单一ASC/BLF来源的基础配置显式设置`execution.process_count: 4`，以最多4个工作进程处理同一次记录的文件；实际进程数受文件数限制。程序省略此字段时仍默认1。选定配置后，先按下表确认文件关系，再修改路径、DBC和业务条件。

|输入关系|配置进程数的位置|完整示例与核对结果|
|---|---|---|
|同一次记录的连续ASC/BLF分卷|分析根级`execution.process_count`；跨文件保留状态|[两卷读取](examples/continuous-parallel.yaml)，积分38J；[跨卷持续条件](examples/conditional-energy.yaml)，61～122秒能量0.06777777777777777kWh|
|同一次记录的文件时间范围交叠|同上，并明确`sources[].file_merge: time_order`|[按时间归并](examples/continuous-time-order.yaml)，积分38J；各文件内部所需记录须有序|
|同帧公式逐报文累计|同样使用分析根级`execution.process_count`|[高性能积分器连续会话](examples/fast/session.yaml)，1200J；使用`chronaxis fast run`|
|多次独立试验|批量根级`process_count`；每个子任务使用1|[独立批量](examples/batch-extended.yaml)，分别保留各任务结果；使用`chronaxis batch run`|
|CSV、内存或多来源联合分析|分析内使用1；独立任务可由外层批量并行|[CAN与CSV联合任务](examples/can-joint-analysis.yaml)，26J|

单文件示例保留相同的进程上限，便于换成多文件；只有一个文件时不会拆分该文件，也不代表实际启用了4个进程。完整用法见[连续记录多进程](continuous-files.md)和[批量任务](batch.md)。

## 完整教学任务

| 任务 | 输入与完整配置 | 运行与预期 |
|---|---|---|
| 台架功率的波动及每次加载的 P95 | [配置](examples/power-statistics.yaml)、[ASC](examples/data/can/power-statistics.asc)、[DBC](examples/data/can/teaching.dbc) | 5 条读数的 P95 为 18 W，2 段加载均值的 P95 为 19.5 W。[计算过程与命令](calculations.md#v4-power-statistics) |
| ASC／BLF能量与均值 | [quickstart.asc](examples/data/can/quickstart.asc)、[DBC](examples/data/can/teaching.dbc)、[analysis.yaml](examples/analysis.yaml) | [入门教程](quickstart.md)：38J、6W、38/6W |
| 事件→窗口→能量 | [activity.asc](examples/data/can/activity.asc)、[activity.yaml](examples/activity.yaml) | [完整任务](activity-tutorial.md)：活动50J、窗口70J；confirmed时30J/70J |
| 公共来源与派生定义 | [analysis-imports.yaml](examples/analysis-imports.yaml)、[definitions.yaml](examples/shared/definitions.yaml)、quickstart.asc与teaching.dbc | [公共定义](imports.md)：38J、6W、38/6W和双倍功率76J |
| Python逐行读取 | [api_example.py](examples/api_example.py) | 默认运行同目录analysis.yaml；可传入自己的配置及--output结果目录 |
|按实际时间计算滚动平均|[时序变换](temporal-transforms.md)|最小例在0.2秒得到18A；DBC周期另有扩展示例。|
|自定义函数、统计与时序算法|[自定义分析算子](host-extensions.md)|峰值80A。|
|按标定表查值与插值|[一维查表与插值](expressions.md#lookup-reference)|按声明单位使用标定表。|
|对已有事件或窗口结果再统计|[结果聚合](aggregations.md)|指定来源计算项和统计操作。|
|高性能积分器|[同帧逐报文累计](fast-energy.md)|单文件800J；连续分卷单会话1200J；独立batch总量1200J，三者分别运行。|

## 集中绑定与周期导出

以下专题各自提供完整输入、配置和实际结果；与上方结果索引分别列出。

|任务|完整材料与说明|核对结果|
|---|---|---|
|同一报文的多个信号集中绑定|[配置](examples/grouped/analysis.yaml)、[ASC](examples/grouped/pack.asc)、[DBC](examples/grouped/pack.dbc)；[信号指南](signals.md)|[最大电压42V](examples/grouped/results/会话结果.csv)、[0.1秒边沿](examples/grouped/results/事件结果.csv)|
|按DBC周期导出两种网格|[配置](examples/dbc-grid/analysis.yaml)、[ASC](examples/dbc-grid/grid.asc)、[DBC](examples/dbc-grid/grid.dbc)；[信号导出](signal-exports.md)、[CAN导出](can-exports.md)|[信号4行](examples/dbc-grid/results/resampled.csv)、[CAN 5帧](examples/dbc-grid/results/frames.asc)|

## 按功能选择最小配置与扩展示例

下面每个文件都是完整分析配置；输入文件一并保存在data目录。最小例先展示一个目标，扩展例增加对应选项。具体预期值及原因在相应指南中，不需要从其他未给出的配置猜测引用名称。

|功能|最小完整配置|扩展及说明|
|---|---|---|
|ASC／BLF日志目录|[input-can-directory.yaml](examples/input-can-directory.yaml)|直接自然序读取两个连续日志，见[快速开始](quickstart.md)|
|CSV专用输入|[input-csv-minimal.yaml](examples/input-csv-minimal.yaml)|[时间偏移](examples/input-csv-offset.yaml)，见[数据来源](inputs.md)|
|数值信号|[signal-number-minimal.yaml](examples/signal-number-minimal.yaml)|[mA换成A](examples/signal-number-conversion.yaml)，见[信号绑定](signals.md)|
|布尔与状态|[布尔](examples/signal-bool-minimal.yaml)、[枚举状态](examples/signal-enum-minimal.yaml)|[组合条件](examples/signal-state-combined.yaml)，映射输入代码到真假或状态名称|
|表达式|[expression-minimal.yaml](examples/expression-minimal.yaml)|[expression-extended.yaml](examples/expression-extended.yaml)，见[表达式](expressions.md)|
|事件规则|[持续条件](examples/rule-condition_duration-minimal.yaml)|每种规则均有独立最小/扩展配置，全部入口见[事件规则](rules.md)|
|事件窗口|[window-minimal.yaml](examples/window-minimal.yaml)|[合并](examples/window-merged.yaml)、[退出等待](examples/window-exit-delay.yaml)，见[窗口](windows.md)|
|请求响应|[sequence-minimal.yaml](examples/sequence-minimal.yaml)|[三种处理结果](examples/sequence-outcomes.yaml)，见[配对](sequences.md)|
|记录间隔|[实际时间](examples/interval-actual.yaml)|[固定间隔](examples/interval-fixed.yaml)，见[计算间隔](intervals.md)|
|计算|[calculation-minimal.yaml](examples/calculation-minimal.yaml)|[九种操作](examples/calculation-operations.yaml)，见[统计与积分](calculations.md)|
|逐消息累计|[message-minimal.yaml](examples/message-minimal.yaml)|[方向分桶](examples/message-directions.yaml)，见[逐消息累计](message-calculations.md)|
|阈值预设|[preset-threshold-minimal.yaml](examples/preset-threshold-minimal.yaml)|[等待确认](examples/preset-threshold-delay.yaml)、[部分结果](examples/preset-threshold-partial.yaml)，其他预设见[业务预设](presets.md)|
|执行与诊断|[execution-diagnostics.yaml](examples/execution-diagnostics.yaml)|[保留部分](examples/execution-report.yaml)、[严格拒绝部分](examples/execution-strict.yaml)，见[执行配置](execution.md)|
|批量|[batch-minimal.yaml](examples/batch-minimal.yaml)|[两个独立任务](examples/batch-extended.yaml)，见[批量任务](batch.md)|
|信号导出|[原始更新](examples/export-signal-minimal.yaml)|[500ms网格](examples/export-signal-grid.yaml)，见[信号导出](signal-exports.md)|
|CAN导出|[原帧](examples/export-can-minimal.yaml)|[重建网格](examples/export-can-grid.yaml)、[全部窗口](examples/export-can-all-windows.yaml)，见[CAN导出](can-exports.md)|

BLF及混合格式可用[生成与验证脚本](examples/prepare_can_examples.py)在新目录创建同数据对照；命令与输出目录结构见[快速开始](quickstart.md)。

## 生成带输入的配置模板

模板由已安装的Chronaxis生成，优先提供ASC/BLF与DBC，以及业务规则所需的小型合成日志；CSV专用场景保留相应表格。命令中的目标目录必须尚不存在；默认带逐项注释，--style minimal生成同一配置的简洁形式。

两种style都省去无用途的默认字段，minimal仅比annotated少说明文字，计算内容相同。普通示例不填写session/entity、唯一来源引用、默认范围和策略；明确保留进程上限作为运行选择，按上表区分会话并行和批量并行。扩展示例再添加本节正在说明的设置，例如非默认策略、换算或资源限制。

随册YAML中，每个父字段解释它组织的内容，每个子字段解释它控制的行为；行里的值是本例具体选择。先阅读来源和信号定义，再看规则、窗口和计算。`imports`先列公共定义文件、`derived`先定义后引用，是便于阅读的顺序，解析器本身也允许顶层键采用其他顺序。

```powershell
chronaxis config init --list
chronaxis config init fault-window --output fault-demo
chronaxis validate fault-demo/plan.yaml
chronaxis run fault-demo/plan.yaml --output fault-result
```

| 场景名 | 用途 | 配置入口 | 应核对的结果 |
|---|---|---|---|
|can-blf|CAN BLF与DBC|plan.yaml|原始字节1/3/1经DBC的2x+1得到3/7/3V，各持续1s，积分13V·s；第4帧为无关消息。|
|can-asc|CAN ASC与DBC|plan.yaml|原始字节1/3/1经DBC的2x+1得到3/7/3V，各持续1s，积分13V·s；第4帧为无关消息。|
|signal-csv|信号CSV：积分与两种均值|plan.yaml|功率2/4/8/10W分别持续1/2/1/2秒，积分38J；样本均值6W，时间加权均值38/6W。|
|charge-session|充电活动：明确角色、单位与方向|plan.yaml|活动[0s,2s)，400V×10A×2s=8000J，输出8000/3600Wh；10A×2s=20As，输出20/3600Ah。|
|fault-window|故障事件与前后窗口|plan.yaml|2s报警由假变真；向前1s、向后2s，输出片段[1s,4s)。|
|command-response|请求响应：匹配与等待到期|plan.yaml|1s请求在2s响应，延迟1s；4s请求在6s达到2s等待上限，无响应。|
|threshold|阈值预设：进入与恢复门槛|plan.yaml|85°C在0s进入，77°C保持活动，75°C在9s退出；活动时长9s。80/75°C只是合成例子。|
|stability|迟滞与去抖对照|plan.yaml|迟滞活动[1s,4s)，均值247/3°C；进入/退出各稳定1s的去抖活动[2s,4s)，均值81°C。|
|raw-can-csv|原始CAN CSV显式布局|plan.yaml|原始字节1/3/1经DBC的2x+1得到3/7/3V，各持续1s，积分13V·s；第4帧为无关消息。|
|signal-export|信号导出与独立插值网格|plan.yaml|分析积分仍为38J。原采样与500ms线性网格分别导出；网格0到5.5s共12点，前3点为2/3/4W。|
|can-export|CAN原帧导出|plan.yaml|分析积分13V·s；请求范围内原帧按原顺序导出，不重采样。|
|batch|两个独立任务的批量清单|batch.yaml|两个任务各自读取同一合成输入，均完成且各得38J；它们不是同会话时间切片。|

普通分析模板用`chronaxis run 目录/plan.yaml --output 结果目录`；batch模板用`chronaxis batch run 目录/batch.yaml --output 结果目录`。CAN类模板所需CAN依赖随正常安装提供。导出模板中的设备标签反映[当前实现限制](exports.md)，不能当作任意设备的通用标识。



## 下载完整案例并运行

以下配置和data文件都随离线包提供。从examples目录运行；分析命令的结果目录可重复使用，文件名自动增加时间后缀。CAN案例所需CAN依赖随正常安装提供。它们使用合成输入，不代表真实设备阈值。

<a id="can-joint-analysis"></a>
### CAN电压与CSV电流联合分析

[can-joint-analysis.yaml](examples/can-joint-analysis.yaml)读取[joint.asc](examples/data/joint.asc)、[joint.dbc](examples/data/joint.dbc)及[joint-current.csv](examples/data/joint-current.csv)。两个来源以synthetic_clock声明同一计时起点；声明本身不自动校时。电压在0、1、2秒为3、7、3V，电流恒为2A；[0,3)功率6、14、6W各持续1秒，energy应为26J。

```powershell
chronaxis run can-joint-analysis.yaml --output joint-result
```

<a id="start-end-case"></a>
### start_end活动与超时

[start-end.yaml](examples/start-end.yaml)使用随附[start-end.asc](examples/data/can/start-end.asc)和教学DBC，不需要CSV。begin>0开始，done>0结束，最长5秒：[教学事件结果CSV](examples/results/start-end-yaml/事件结果.csv)有[0,2)、[4,9)、[11,14)三次活动，第二次显示“超时结束”。同一表的cycle_mean（1）分别为10、52、110；第二段为(40×2+60×3)/5=52。时间列单位是秒。自行运行时，从本次manifest的outputs读取带时间后缀的事件结果文件路径。

```powershell
chronaxis run start-end.yaml --output cycle-result
```

<a id="message-energy"></a>
### 每条CAN消息的贡献与跳过

[message-energy.yaml](examples/message-energy.yaml)读取[power.blf](examples/data/power.blf)和[power.dbc](examples/data/power.dbc)。两条同刻4000W消息各乘明确参数0.1s，合计800J；第三条目标消息没有完整数据，贡献表记录missing_input；无关ID不算尝试。从本轮清单定位贡献表，查看其中的三行，而不是在汇总行寻找不存在的尝试次数字段。这里显式选择legacy解码策略以观察不完整消息，不应据此默认放宽自己数据的检查。

```powershell
chronaxis run message-energy.yaml --output message-result
```

<a id="dual-grid"></a>
### 信号250ms与CAN500ms两个导出网格

[dual-grid.yaml](examples/dual-grid.yaml)读取与联合案例相同的joint.asc和joint.dbc，同时导出电压和重建CAN帧。signals的分析名是voltage，DBC字段名是Voltage；两处不能互换。metadata.device_label受当前独立导出实现限制，本合成案例填home，具体限制见[输出配置](exports.md)。

```powershell
chronaxis run dual-grid.yaml --output grid-result
```

分析voltage_area仍为13V·s。信号网格为0～2.75秒的12个点，起始值为3、4、5、6、7V；CAN网格请求0～2.5秒的6个位置，实际生成0～2秒的5帧，2.5秒被跳过。请求范围右端3秒不包含在可插值记录中，因此信号最后3点为missing/missing_right，CAN清单skipped_grid_points=1。时间网格不改变分析积分；CAN字段编码会按DBC量化，例如估计5V可以精确编码，估计4V位于两个码值中间，按nearest_even-v1取整。通过本轮清单的 `exports.index_file` 指向的导出索引定位两份文件，不猜目录编号。

## 仅用于组合教学片段的基础文件

[teaching-base.yaml](examples/teaching-base.yaml)和[electrical-base.yaml](examples/electrical-base.yaml)只提供来源及信号，需按对应章节补入rules或calculations等功能后运行。它们能加载为计划，但不构成独立分析任务；不要直接把它们当成上方的最小运行例。[shared/definitions.yaml](examples/shared/definitions.yaml)是imports使用的公共定义，也不单独执行。

## 自动核对脚本

[run_example.py](examples/run_example.py)核对YAML/JSON、两后端与CLI；[imports_example.py](examples/imports_example.py)核对公共定义与导出后的独立配置；[readability_examples.py](examples/readability_examples.py)核对表达式、批次和部分结果语义；[advanced_examples.py](examples/advanced_examples.py)用`--output 新目录`复核上述四个完整案例。它们是验证工具，普通用户可先按上面的教学步骤直接运行。
