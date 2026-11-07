# 分析配置结构

手写以YAML为主，程序交换可用JSON，两种格式使用同一套字段。当前配置使用整数 `config_version: 4`。缺少版本或填写其他版本时会报错。逐项用途、类型、条件、范围和默认值从[字段参考](configuration-reference.md)查询。Schema是供软件读取的“配置结构规范”：列明允许字段、类型和必填条件，供编辑器或校验器使用，不是另一种业务配置格式。这里说明填写顺序和各段负责什么。初次使用先读[字段、缩进和列表](configuration-language.md#先认识字段映射和列表)。下表的“段”都是文件根级字段，彼此并列；不要因表格顺序把后一段缩进到前一段中。

| 段 | 是否必填 | 用途 |
|---|---|---|
| config_version | 是 | 声明这份分析文件按哪一版字段结构解释；填写整数4。不是日志日期或预设版本 |
| dataset | 是 | [数据集与分析范围](dataset.md)：name命名本任务，entity/session默认沿用name；domain可省略，按实际观测范围分析 |
| sources | 展开后必须有至少一项，可由imports提供 | 按顺序列出输入；默认识别ASC/BLF，CSV和内存须明确source_type；读取参数集中在reader |
| signals | 展开后必须有数组，可由imports提供 | 给原始列或报文字段一个表达式使用的名称；CAN类型与单位默认由DBC推导，CSV/内存才需明确声明；valid_for可省略，默认规则见[信号](signals.md) |
| imports | 否，缺省不导入 | 按顺序读取本地一层公共sources/signals/derived；重名默认拒绝；需要局部替换时显式用overrides，见[公共定义](imports.md) |
| overrides | 否，缺省不覆盖 | 对导入后的来源、信号或派生定义按名称明确覆盖允许字段；不创建新对象 |
| lookups | 否 | 用标定点把输入值换成输出值，见[一维查表与插值字段参考](expressions.md#lookup-reference)及[电压查表示例](examples/lookup-power.yaml) |
| derived | 否，缺省为空 | 由信号表达式计算的新信号，键是新名称，expr是表达式；unit可按表达式推导，明确填写时仍检查一致性 |
| transforms | 否 | 将信号变为滚动均值、变化率等新序列，见[时序变换](temporal-transforms.md) |
| aggregations | 否 | 汇总本次分析的会话、事件或片段标量计算结果、请求响应延迟，或统计事件及最终片段数量；例如求每段平均功率的P95，见[结果聚合](aggregations.md) |
| rules | 否，缺省为空 | 事件规则；rule_type明确说明是哪种时间判断 |
| presets | 否，缺省为空 | 常用规则组合；preset_type选择充电、故障、请求响应或阈值方案 |
| windows | 否，缺省为空 | 从事件生成需要分析或导出的片段 |
| sequences | 否，缺省为空 | 在指定延迟范围内配对请求和响应点 |
| calculations | 否，缺省为空 | 声明要算出哪些结果；每项用operation选算法，用scope选会话、事件或片段范围，用expr/condition选输入 |
| message_calculations | 否，缺省为空 | 按原消息累计一次表达式贡献，与普通时间积分分开 |
| intervals | 否，默认actual | intervals.default提供统一间隔；节点自己的interval就地覆盖，不另写overrides名称表 |
| outputs | 否 | 默认中文可读CSV与JSON运行清单；需要原交换字段时显式tables: csv或jsonl；贡献明细、信号导出和CAN导出默认关闭 |
| execution | 否 | 控制文件读取进程数、计算实现、资源使用及数据不全时的处理。单一ASC/BLF来源示例显式选择process_count: 4；省略时进程数仍为1，计算实现默认numpy。见[执行设置](execution.md) |
| diagnostics | 否，全为false | 选择是否额外记录逐项定位信息、完整性校验以及保留临时文件；按排错需求启用，详见[诊断](execution.md#diagnostics) |
| metadata | 否，空对象 | 保存附加信息；device_label控制运行清单来源标签，普通分析缺省pending。具体入口限制见[运行说明](execution.md)，其他备注不改变计算 |

字段名称区分大小写，未知字段会报错并可能给拼写提示，但不会自动接受建议值。同一配置不能重复一个键；同名来源、信号或冲突节点也会拒绝。原日志列名和DBC信号名保持原文，用signals中的name给它们取简单可读的表达式名称。

## 常用字段怎样简写

普通BLF/ASC任务从[最小入门配置](quickstart.md)开始，只加当前任务需要的内容。不要按字段表逐项补齐：session/entity沿用dataset.name；格式、默认时间、唯一来源/通道、DBC已有类型/单位/周期、默认scope与输出均可省略。多个候选或缺少信息时，程序会指出需要补充的位置。

基础示例保留一个明确的运行选择：单一ASC/BLF来源使用最多4个文件读取工作进程。下面是根级片段，加入自己的完整配置；已有`execution`时只在其中设置`process_count`，保留其他设置，不重复创建父键。

```yaml
execution:          # 控制本次分析的运行方式
  process_count: 4  # 最多4个文件读取工作进程；实际不超过文件数
```

这是手册推荐的显式配置，程序默认仍为1。只有一个文件时不会拆分该文件；多个文件仍组成同一次连续分析。CSV、内存和多来源联合分析使用1；独立任务在批量配置根级设置`process_count`，各子任务保持1。使用条件与覆盖顺序见[执行设置](execution.md)。

用户给来源、信号、规则、窗口、计算项和批量任务起的名称统一用`name`；引用使用`source`、`rule`、`window`。CAN报文编号使用`frame_id`，DBC信号名仍为`field.signal`。普通计算的输入统一写`expr`。

下面以 [analysis.yaml](examples/analysis.yaml) 为基础，替换其整个 `calculations` 段；`power` 已在同一文件的 `signals` 中定义。普通会话积分只需要：

```yaml
calculations:            # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: energy         # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: integral  # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    expr: power          # 指定参与计算的数值或信号表达式；引用前面已定义的信号
```

其他段保持原样，不要再追加第二个 `calculations:`。需要事件/窗口范围时再加 `scope`，需要覆盖计算间隔时再加 `interval`，见[计算](calculations.md)和[间隔](intervals.md)。

本页的 `field.signal`、`time.clock` 等点号写法表示父子位置，不是字面键名；实际文件须展开为对应缩进，见[完整对照](configuration-language.md#field-paths)。

来源的读取参数放在`reader`；信号额外换算放在`conversion`；相对时间共同起点叫`time.clock`，重采样网格起点叫`resampling.start`。同一份含义只填写一处。省略字段采用已列明的默认值；显式null是否允许以具体字段说明为准，不能普遍代替省略。例如execution.spool_quota_bytes允许null，表示不另设暂存磁盘配额。类型或取值不合法时报错。

分析默认只解析、检查和保留本次计算需要的内容。完整信号检查、逐条贡献与追溯、原帧副本和额外导出均按请求启用；不为了之后可能排错而默认构造、扫描或保存这些数据。

## 配置语言

完整语法和当前字段见[配置文件语法](configuration-language.md)。

支持一个文档、字符串键、映射、列表、注释、多行文本，以及JSON原生的字符串、有限数字、布尔和空值。true/false是布尔值，yes/no是普通字符串。时长写成500ms或2s这样的字符串，原始数据中的整数、浮点和文本类型保持区分。

拒绝重复键、非字符串键、多文档、自定义标签、锚点、别名、合并键、非有限数字和超过64层的嵌套。不替换环境变量，也不执行模板。声明了YAML版本时只接受1.2。限制的目的是让一份配置中的值、类型和来源明确，而不是让配置变成另一门程序语言。

## 时间与统计术语

valid_for表示一个有效样本在最后更新时间之后最多保持多久；到期即未知。timeout只表示等待或活动的上限；minimum_duration表示条件必须持续多久才确认。它们不能互换。

sample_mean是按样本个数平均；time_weighted_mean按每个值实际占用的时间平均。在快速开始的同一组数据上，前者为6W，后者为38/6W，见[时间与计算](concepts.md)。

## 功能与字段参考

窗口配置见[事件窗口与片段](windows.md)，计算方式见[统计与积分](calculations.md)，逐模块字段入口见[配置字段参考](configuration-reference.md)。

## 配置错误定位

校验消息包含可获得的文件、行列、原字段路径、对象名、错误代码、短值和修正提示。缺少字段时定位到最近父对象，不虚构不存在的行号。validate默认易读文字；加--format json获取结构化错误。编辑器可使用[编辑器字段提示](schema-editor.md)关联YAML，不要向业务配置中添加未支持的$schema字段。
