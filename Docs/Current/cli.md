# 命令行参考

通过终端命令加载配置、检查声明、执行分析及发布结果。分析内容写在配置文件中，输出目录和后端覆盖等选项写在对应命令后。

## 按基础并行配置运行

下载手册的完整 `examples` 目录，在该目录打开终端。下面三步使用连续分卷示例中明确设置的 `execution.process_count: 4`：

```text
python -m chronaxis validate continuous-parallel.yaml
python -m chronaxis explain continuous-parallel.yaml --format json
python -m chronaxis run continuous-parallel.yaml --output result-continuous
```

`validate`检查配置，`explain`解释执行设置，`run`才读取日志并计算。示例有两个输入文件，解释结果的 `source_execution[].file_count` 和 `read_process_limit` 均为2；配置中的4只是上限。运行后从完成摘要的 `manifest` 找本次清单和实际结果文件，积分为38J，详见[结果示例](example-results.md#continuous-parallel-yaml)。

普通 `explain` 的 `read_process_limit` 是按配置和来源推导的读取子进程上限，不是运行时已启动的数量。例如单个 ASC 按默认 `concatenate` 直接读取时可以不创建子进程，即使这个静态上限为1。fast 的 `worker_process_limit` 另按实际调度方式说明：在当前进程内执行时为0。

临时改变进程数可在命令后加 `--process-count 2`，不会改写配置文件。单个CSV、内存或多来源计划使用1；独立任务使用批量根级进程数，详见[执行配置](execution.md)。

## 全部命令

|命令|参数|作用|
|---|---|---|
|`python -m chronaxis config init/convert/resolve/origins`|详见[配置工具](configuration-tools.md)和[公共定义](imports.md)|生成模板、转换格式、展开配置、按请求查看来源|
|`python -m chronaxis validate PLAN`|可选`--backend reference/numpy`、`--process-count 正整数`及`--format text/json`|仅检查计划，默认易读文字；--format json供程序读取|
|`python -m chronaxis explain PLAN`|同上|列出将使用的信号、资源上限、输入检查范围和计算实现|
|`python -m chronaxis run PLAN`|必填`--output`；可选`--work-dir`、`--backend`和`--process-count`|分析、发布、关闭后打印完成摘要|
|`python -m chronaxis batch run BATCH`|必填`--output`；可选`--process-count`|运行多个独立计划并写逐任务报告；见[批量](batch.md)|
|`python -m chronaxis fast validate PLAN`|计划路径，可选 `--process-count`|检查同帧计算和 DBC 绑定，输出 JSON|
|`python -m chronaxis fast explain PLAN`|计划路径，可选 `--process-count`|以 JSON 列出输入文件、计算定义和失败处理方式|
|`python -m chronaxis fast run PLAN`|必填 `--output`，可选 `--process-count`|将同一来源的ASC/BLF分卷作为一个会话计算并发布汇总|
|`python -m chronaxis fast batch BATCH`|必填 `--output`，可选 `--total`、`--process-count`|处理独立文件；`--total` 请求同一模板中可比计算项的总量，见[fast 批量](fast-energy.md)|
|`python -m chronaxis guide`|可选 `--language zh/en`、`--output 新文件.zip`|显示现有 README 路径；指定 output 时另存双语 ZIP|

`PLAN`与`BATCH`换成文件路径。安装源码包后也可直接用`chronaxis`命令。成功返回0，取消返回130；失败时的1和2按下面的[退出码与错误位置](#退出码与错误位置)区分，不能仅凭“文件错误”判断。帮助见`python -m chronaxis --help`及各子命令`--help`。完整参数与实现见[cli](reference/chronaxis.cli.md)。

普通run、validate、explain支持`--process-count`，覆盖本次文件读取/解码进程上限；batch run的同名参数控制独立分析任务数。连续分卷用法见[连续多进程读取](continuous-files.md)。

fast run的进程数来自分析配置execution.process_count；fast batch来自批量根级process_count。两者及fast validate/explain均支持--process-count覆盖；覆盖只影响本次调用。--total 是不带值的开关，默认省略；不能产生完整总量时，报告说明原因。guide 的 --language 默认 zh，en 选择英文 README；可选 ZIP 始终包含两种语言。

|参数|数据类型|何时必填|省略时的行为|取值及含义|
|---|---|---|---|---|
|PLAN|文件路径|validate、explain、run|无|分析计划YAML或JSON路径；带空格时用引号括起来。|
|BATCH|文件路径|batch run|无|[批量YAML或JSON](batch.md)的路径，不是某一个analysis.json。|
|--format|字符串|否，validate/explain|text|text为终端文字，json为检查报告对象；不改变分析结果表格式。|
|--format|字符串|否，config resolve|终端默认yaml；文件按后缀|选择展开配置的yaml/json表示；显式值须与输出文件后缀一致。|
|--format|字符串|否，config origins|text|text为可读来源列表，json为字段来源报告；不是分析结果。|
|--backend|字符串|否|使用计划中的backend|`reference`使用参考计算；`numpy`使用数组计算。适用于validate、explain、run。|
|--output|目录路径|run、batch run、fast run/batch|必填|可重复使用的结果目录；每次运行创建带时间后缀的不同文件。|
|--work-dir|目录路径|否，仅普通run支持|自动创建本次专用工作目录|存中间数据和暂存结果；自行指定时也必须是尚不存在的路径。|
|--process-count|整数|否，run/validate/explain/batch run及fast对应命令|普通分析沿用execution.process_count；批量沿用根级process_count，默认均1|正整数。普通分析限制读取/解码，fast单会话还在工作进程求单帧贡献；均不含主进程；独立批量限制分析任务进程数，不含各任务的旧CAN子进程。|
|-h / --help|开关，不跟值|否|执行命令|显示当前层级的帮助并退出，不运行分析。例如`python -m chronaxis run --help`。|

初始化、格式互转和有效配置展开使用config init/convert/resolve，参数和保护规则见[配置工具](configuration-tools.md)。

## 退出码与错误位置

退出码用于判断命令是否成功；诊断内容和批量报告说明具体原因。同一种文件问题在不同入口可能返回不同的码，编写批处理脚本时须先确定所调用的命令。

|命令|返回2的常见情况|返回1的常见情况|
|---|---|---|
|普通 `validate`、`explain`、`run`|参数或配置内容错误、来源目录为空、通配符无匹配|配置或DBC文件无法读取；`run`读取日志、分析、发布或关闭失败|
|普通 `batch run`|批量配置或参数不合法；`template`／`inputs`在加载时展开或构建子计划时出现配置内容错误|批量配置或模板文件无法读取；`jobs`子配置在任务启动后校验失败，或其他已开始的子任务失败；输出、批量报告或清理失败|
|`fast validate`、`fast explain`、`fast run`|准备配置、DBC或输入清单失败，包括这些阶段的文件错误|仅 `fast run`：开始执行后的日志读取、计算或结果发布失败|
|`fast batch`|批量预检查失败、输出目录无法建立；最终批量报告写出失败且没有随异常返回可恢复报告|任务报告标记失败；或执行故障已经携带当次批量报告|

例如：

- 配置文件不存在，普通 `validate` 返回1，`fast validate` 返回2。缺少DBC也是这一区别。
- 配置明确写出一个不存在的 `missing.asc`，静态 `validate`／`explain` 不读取该文件，可以返回0；实际 `run` 才读取并返回1。返回0不能证明日志可以读取。
- 普通批量采用 **`jobs`** 引用分析文件时，子配置在工作进程启动后才加载。子配置引用空目录或无匹配通配符时，该任务记为失败，整批返回1，并有批量任务报告。
- 普通批量采用 **`template`／`inputs`** 时，在加载批量配置时就展开模板并构建每份子计划。例如合法模板有 `primary`、`auxiliary` 两个CSV来源，`source: primary` 指定只用 `inputs` 替换 `primary`；如果保留的 `auxiliary` 引用空目录或无匹配通配符，加载就返回2，尚未启动任务，也没有任务报告。这不限于批量 `inputs` 自身展开失败；具体加载行为见 [`load_batch_plan`](public-api/load_batch_plan.md)。
- **`fast batch`** 会在启动前检查它支持的CAN子配置；上述空目录、无匹配通配符等准备错误返回2，不启动任务、不生成任务报告。它不能采用上面的双CSV模板。
- 输出路径已经是普通文件，普通 `run`、普通 `batch run` 和 `fast run` 返回1，`fast batch` 返回2。若各子任务已经成功、最后的fast批量报告写入发生文件错误，也可能返回2，已完成任务的结果仍保留。

处理非零退出时，同时保存标准错误输出并查看已生成的任务报告。非零退出不表示已经发布的结果全部撤销；批量取消或失败也不能把未完成任务当成成功。

## 一次查看多处配置错误

先运行`chronaxis validate plan.yaml --format json`。字段可解析时会一次列出能独立确认的错误；例如backend、batch_rows和tables同时无效，可在同次报告中分别定位。每项保留可用的source、path、line、column、code、message和hint。JSON用errors数组，单错也只有一个数组元素，不再返回单独error字段。文本模式会给各错误编号。

语法损坏时先修复对应YAML/JSON；依赖的来源或信号无效时，下游检查会列在blocked_checks中，说明尚不能检查的原因，而不是猜一个值继续。修复后重新validate才能检查这些部分。有配置错误时run不会启动分析。配置补全确实需要时可读取DBC元数据；静态检查不读取业务报文内容。

run的完成摘要返回本次manifest路径，batch run返回本次report路径；结果文件自动增加时间后缀，见[结果发布](results.md#result-publication)。

## AI指南

`chronaxis guide`显示中文README的绝对路径，`chronaxis guide --language en`显示英文入口；两者不写文件。可选`--output 新文件.zip`另存完整双语副本，父目录须存在且不能覆盖现有文件。详情见[AI指南](ai-guide.md)。
