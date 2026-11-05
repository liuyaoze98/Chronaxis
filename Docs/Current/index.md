# Chronaxis 用户手册

[English manual](en/index.md)

Chronaxis用于分析多源时序数据：将输入列或报文字段绑定为信号，识别事件及时间片段，计算积分、持续时间和统计量，再读取或导出结果。常见输入是配有DBC的BLF或ASC日志，也支持原始报文CSV、已解码信号CSV和内存记录。

本手册说明分析配置版本 4 及对应公开接口。新分析使用 `config_version: 4`；配置语法见[配置说明](configuration-language.md)。可从本地 wheel 或源码[安装](installation.md)，再检查[支持范围](status.md)。网页版提供离线导航和搜索；配套 AI 资料的修订与产品基线记录在资料包的 manifest.json。

## 配置使用者的阅读路线

让 AI 代写配置或调用代码时，从[AI 指南](ai-guide.md)选择当前持有的源码、离线手册或安装包入口，直接阅读 README 和匹配的任务示例。

如果主要通过配置运行分析，按下面顺序开始：

1. 完成[安装](installation.md)，再阅读[BLF／ASC快速开始](quickstart.md)，用附带输入运行一次并核对38J的积分结果。
2. 先看[字段路径与YAML缩进](configuration-language.md#field-paths)，再阅读[配置结构](configuration.md)及[数据来源](inputs.md)，替换为自己的日志目录、DBC、报文ID和信号名。
3. 根据任务选择[事件检测](rules.md)、[请求响应配对](sequences.md)或[计算间隔](intervals.md)，再选择计算和输出。
4. 对照[各示例的实际输出和解析](example-results.md)，再查[结果字段说明](results.md)；同时检查数值、单位、状态和原因，不能只看value。

配置校验通过说明声明可接受，不能证明文件内容、DBC或业务阈值正确。每个完整示例都应先使用随附数据跑通，再逐项替换。

## Python开发者的阅读路线

先看[Python快速开始](api-usage.md)，了解加载计划、静态检查、执行、逐行读取和关闭资源的顺序。随后按需要查[公开API参考](api.md)和[结果结构](results.md)。内部实现与公开调用分开组织，通常不需要先阅读执行器源码。

## 按任务查找

|任务|阅读入口|
|---|---|
|使用自己的BLF、ASC或CSV日志|[数据来源](inputs.md)、[CAN文本输入](text-inputs.md)|
|理解时间、有效期、未知值与部分结果|[时间与结果质量](concepts.md)、[术语表](terms.md)|
|从信号建立计算表达式|[表达式](expressions.md)、[配置结构](configuration.md)|
|多个条件连续超过指定时长，再对整个区间求能量|[两卷ASC条件积分完整例](conditional-energy.md)，含配置、实际输出与逐步解释|
|识别条件活动、边沿或配对请求响应|[事件检测规则](rules.md)、[请求响应配对](sequences.md)|
|使用预设业务组合|[业务预设](presets.md)|
|调整运行资源或批量执行独立任务|[执行配置](execution.md)、[批量任务](batch.md)|
|读取分析结果或导出信号/报文|[读取结果](results.md)、[导出](exports.md)|
|复用配置、检查字段来源|[公共定义](imports.md)、[配置工具](configuration-tools.md)|
|维护实现或构建文档|[内部架构](architecture.md)、[文档构建](maintenance.md)|
|按标定表换算数值|[一维查表与插值](expressions.md#lookup-reference)|
|计算滚动统计或变化率|[时序变换](temporal-transforms.md)|
|对事件或窗口结果再统计|[结果聚合](aggregations.md)|
|加入自己的Python算法|[自定义分析算子](host-extensions.md)|
|计算同帧逐报文能量|[高性能积分器](fast-energy.md)：公式需包含时间因子|
|查找可运行的完整配置|[示例目录](examples.md)|
