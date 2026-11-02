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
|`python -m chronaxis legacy import INI`|必填`--mode`、`--mapping`、`--output`|保存原文，生成新计划或完整拒绝报告|

`PLAN`与`INI`换成文件路径。安装源码包后也可直接用`chronaxis`命令。退出码：0成功，2参数/配置错误，1文件/分析/发布/关闭失败，130取消。帮助见`python -m chronaxis --help`及各子命令`--help`。完整参数与实现见[cli](reference/chronaxis.cli.md)。

每个命令后面只能填写该命令支持的选项。例如`--process-count`属于`batch run`，不能传给单任务`run`。

|参数|数据类型|何时必填|省略时的行为|取值及含义|
|---|---|---|---|---|
|PLAN|文件路径|validate、explain、run|无|分析计划YAML或JSON路径；带空格时用引号括起来。|
|BATCH|文件路径|batch run|无|[批量YAML或JSON](batch.md)的路径，不是某一个analysis.json。|
|INI|文件路径|legacy import|无|待转换的旧INI路径；原文件不会被修改。|
|--format|字符串|否，validate/explain|text|text为终端文字，json为检查报告对象；不改变分析结果表格式。|
|--format|字符串|否，config resolve|终端默认yaml；文件按后缀|选择展开配置的yaml/json表示；显式值须与输出文件后缀一致。|
|--format|字符串|否，config origins|text|text为可读来源列表，json为字段来源报告；不是分析结果。|
|--backend|字符串|否|使用计划中的backend|`reference`使用参考计算；`numpy`使用数组计算。适用于validate、explain、run。|
|--output|路径|run、batch run、legacy import|无|前两种命令填写新的结果**目录**；legacy import填写新的计划**文件**，例如converted/analysis.json。已有目标不会被覆盖。|
|--work-dir|目录路径|否，仅run支持|自动创建本次专用工作目录|存中间数据和暂存结果；自行指定时也必须是尚不存在的路径。|
|--process-count|整数|否，仅batch run支持|使用批量文件的process_count（省略时1）|正整数；覆盖分析工作进程数量上限，例如`--process-count 2`。不包含调度主进程和CAN读取子进程。|
|--mode|字符串|legacy import|无|五个值及区别见[INI导入模式](migration.md#import-modes)：legacy_sum、sclicer_single、sclicer_start_only、sclicer_start_end、sclicer_slope。|
|--mapping|文件路径|legacy import|无|说明信号、输入和新节点名称的YAML或JSON；完整字段见[INI映射文件](migration.md#import-mapping)。|
|-h / --help|开关，不跟值|否|执行命令|显示当前层级的帮助并退出，不运行分析。例如`python -m chronaxis run --help`。|

初始化、格式互转和有效配置展开使用config init/convert/resolve，参数和保护规则见[配置工具](configuration-tools.md)。

## AI指南

`chronaxis guide`显示中文README的绝对路径，`chronaxis guide --language en`显示英文入口；两者不写文件。可选`--output 新文件.zip`另存完整双语副本，父目录须存在且不能覆盖现有文件。详情见[AI指南](ai-guide.md)。
