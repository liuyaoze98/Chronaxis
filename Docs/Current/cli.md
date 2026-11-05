# 命令行参考

通过终端命令加载配置、检查声明、执行分析及发布结果。分析内容写在配置文件中，输出目录和后端覆盖等选项写在对应命令后。

## 全部命令

|命令|参数|作用|
|---|---|---|
|`python -m chronaxis config init/convert/resolve/origins`|详见[配置工具](configuration-tools.md)和[公共定义](imports.md)|生成模板、转换格式、展开配置、按请求查看来源|
|`python -m chronaxis validate PLAN`|可选`--backend reference/numpy`及`--format text/json`|仅检查计划，默认易读文字；--format json供程序读取|
|`python -m chronaxis explain PLAN`|同上|列出将使用的信号、资源上限、输入检查范围和计算实现|
|`python -m chronaxis run PLAN`|必填`--output`；可选`--work-dir`和`--backend`|分析、发布、关闭后打印完成摘要|
|`python -m chronaxis batch run BATCH`|必填`--output`；可选`--process-count`|运行多个独立计划并写逐任务报告；见[批量](batch.md)|
|`python -m chronaxis fast validate PLAN`|计划路径|检查同帧计算和 DBC 绑定，输出 JSON|
|`python -m chronaxis fast explain PLAN`|计划路径|以 JSON 列出输入文件、计算定义和失败处理方式|
|`python -m chronaxis fast run PLAN`|必填 `--output`|计算单个独立 ASC/BLF 文件并发布结果|
|`python -m chronaxis fast batch BATCH`|必填 `--output`，可选 `--total`|处理独立文件；`--total` 请求同一模板中可比计算项的总量，见[fast 批量](fast-energy.md)|
|`python -m chronaxis guide`|可选 `--language zh/en`、`--output 新文件.zip`|显示现有 README 路径；指定 output 时另存双语 ZIP|

`PLAN`与`BATCH`换成文件路径。安装源码包后也可直接用`chronaxis`命令。退出码：0成功，2参数/配置错误，1文件/分析/发布/关闭失败，130取消。帮助见`python -m chronaxis --help`及各子命令`--help`。完整参数与实现见[cli](reference/chronaxis.cli.md)。

每个命令后面只能填写该命令支持的选项。例如`--process-count`属于`batch run`，不能传给单任务`run`。

fast 的进程数填写在批量配置中，命令支持的选项以上表为准。--total 是不带值的开关，默认省略；不能产生完整总量时，报告说明原因。guide 的 --language 默认 zh，en 选择英文 README；可选 ZIP 始终包含两种语言。

|参数|数据类型|何时必填|省略时的行为|取值及含义|
|---|---|---|---|---|
|PLAN|文件路径|validate、explain、run|无|分析计划YAML或JSON路径；带空格时用引号括起来。|
|BATCH|文件路径|batch run|无|[批量YAML或JSON](batch.md)的路径，不是某一个analysis.json。|
|--format|字符串|否，validate/explain|text|text为终端文字，json为检查报告对象；不改变分析结果表格式。|
|--format|字符串|否，config resolve|终端默认yaml；文件按后缀|选择展开配置的yaml/json表示；显式值须与输出文件后缀一致。|
|--format|字符串|否，config origins|text|text为可读来源列表，json为字段来源报告；不是分析结果。|
|--backend|字符串|否|使用计划中的backend|`reference`使用参考计算；`numpy`使用数组计算。适用于validate、explain、run。|
|--output|目录路径|run、batch run、fast run/batch|必填|可重复使用的结果目录；每次运行创建带时间后缀的不同文件。|
|--work-dir|目录路径|否，仅run支持|自动创建本次专用工作目录|存中间数据和暂存结果；自行指定时也必须是尚不存在的路径。|
|--process-count|整数|否，仅batch run支持|使用批量文件的process_count（省略时1）|正整数；覆盖分析工作进程数量上限，例如`--process-count 2`。不包含调度主进程和CAN读取子进程。|
|-h / --help|开关，不跟值|否|执行命令|显示当前层级的帮助并退出，不运行分析。例如`python -m chronaxis run --help`。|

初始化、格式互转和有效配置展开使用config init/convert/resolve，参数和保护规则见[配置工具](configuration-tools.md)。

## 一次查看多处配置错误

先运行`chronaxis validate plan.yaml --format json`。字段可解析时会一次列出能独立确认的错误；例如backend、batch_rows和tables同时无效，可在同次报告中分别定位。每项保留可用的source、path、line、column、code、message和hint。JSON用errors数组，单错也只有一个数组元素，不再返回单独error字段。文本模式会给各错误编号。

语法损坏时先修复对应YAML/JSON；依赖的来源或信号无效时，下游检查会列在blocked_checks中，说明尚不能检查的原因，而不是猜一个值继续。修复后重新validate才能检查这些部分。有配置错误时run不会启动分析。配置补全确实需要时可读取DBC元数据；静态检查不读取业务报文内容。

run的完成摘要返回本次manifest路径，batch run返回本次report路径；结果文件自动增加时间后缀，见[结果发布](results.md#result-publication)。

## AI指南

`chronaxis guide`显示中文README的绝对路径，`chronaxis guide --language en`显示英文入口；两者不写文件。可选`--output 新文件.zip`另存完整双语副本，父目录须存在且不能覆盖现有文件。详情见[AI指南](ai-guide.md)。
