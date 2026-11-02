# 读取分析结果

## 默认输出：直接看区间和数值

普通配置不用填写outputs。运行后先打开中文命名的CSV：同一事件或窗口的计算结果已经放在同一行，不必手动关联ID，也不用把纳秒换算成秒。文件是UTF-8带BOM编码，方便Windows表格软件识别中文；原始数值没有为了显示而舍入。

例如[连续条件能量示例](conditional-energy.md)只产生一段合格区间：

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | energy_kwh（kWh） | energy_kwh：状态 | energy_kwh：说明 |
|---|---|---|---|---|---|---|---|
| 1 | eligible | 61 | 122 | 正常结束 | 0.06777777777777777 | 完整 | |

直接读作：第1段活动从61秒开始，到122秒结束，能量为0.06777777777777777kWh，计算完整。区间是左闭右开[61,122)。普通整事件积分不额外显示确认时刻；独立事件、窗口、配对或其他计算有此用途时才显示“确认时间（s）”。起止时间仍是实际时间，未额外计算持续时间。

| 实际请求的结果 | 默认文件 | 读法 |
|---|---|---|
| 整个会话的统计 | 会话结果.csv | 同会话多项统计合并一行；各项有自己的单位、状态和说明。 |
| 事件及事件内统计 | 事件结果.csv | 起止、规则和区间编号只出现一次，各指标横向排列。 |
| 窗口及窗口内统计 | 窗口结果.csv | “父事件区间”对应事件表编号；多个编号表示多个父事件。 |
| 请求与响应 | 配对结果.csv | 请求/响应编号对应事件表；判定时间和延迟单位都是秒。 |
| select明细 | 选择结果.csv | 每次更新的值、单位、有效性及满足/未知状态。 |
| 明确请求贡献或输入追溯 | 贡献明细.csv、输入追溯.csv | 保留所需定位和原因，普通任务不产生。 |

共同的数据集、对象和会话名称只在run_manifest.json的presentation.common_identity保存；出现多个值时，对应身份列才加入表中。区间编号只在本次输出内有效，不能用来跨次运行关联。信号CSV及ASC/BLF原帧导出保持各自的数据格式，不使用这套中文结果表结构。

时间列用精确十进制秒，例如922.346858001，不丢纳秒精度。时间保留分析原点，既不从首个结果重新归零，也不猜测日期或时区。绝对时间坐标仍按实际数值显示，不能把没有日期的信息解释成某天的钟表时间。

每项指标分别看状态：“完整”表示本项计算完整；“部分有效”只包含能计算的部分；“无法确定”表示不能给出可用数值。空单元格不等于0。“数据中断”与“观测结束，活动尚未确认结束”是不同的区间状态。说明列将缺失、过期、解码失败等质量位翻译成文字；空说明不证明输入在现实中绝对正确。

没有事件时保留空表和清单中的result_messages，例如“条件曾成立，但持续时间不满足要求”；不会补一行能量0。全局存在条件未知可以与某个已输出区间的完整计算并存。多个指标中一项缺失，不会把其他项一起标为完整或失败。

## 为程序选择交换格式

默认格式名是readable_csv，无需手填。程序若依赖原表字段，在配置根部增加以下内容；已有outputs时在原映射内增加tables，不再写第二个outputs：

```yaml
outputs:                      # 只在程序需要原交换字段时增加这段
  tables: csv                 # 保留原平坦表、字段名和整数纳秒
```

可选值只有readable_csv、csv、jsonl。csv使用events.csv、calculations.csv等原表；jsonl使用对应逐行JSON（包含row_schema_version和row）。选择一种只输出一套结果，不同时生成可读和交换副本。Python的iter_events、iter_calculations等始终返回原类型化行，不受输出格式影响；低层AnalysisResult构造器仍保留csv默认，AnalysisRunner跟随计划默认readable_csv。

可读导出只读已计算结果，不重读原始日志。事件与指标的排序不同，需要临时关联索引；该索引受内存/磁盘预算约束并在发布前删除。它会增加少量导出时间；大量结果需要以具体规模实测。只有逐条明细时直接写出，不创建关联索引。

以下字段说明用于显式csv/jsonl与类型化API；普通可读表用上面的中文列。

想先看输出长什么样，请打开[示例运行结果与解析](example-results.md)：每个完整配置都能找到运行命令、实际结果表和数值解释。本页用于查字段含义，配置文件和运行后的结果文件是两种不同结构。



普通计算的一行直接包含calculation_id、operation、scope、value、unit、status、reason和quality，以及数据集、实体、会话、父事件/片段和序号。可直接通过row.value等属性读取，完整字段见下表关联的结果模型。

本页未另行说明的秒数例子采用默认actual。配置intervals为fixed或dbc时，持续确认、等待到期、变化窗口和配对delay_ns使用所选周期依据；原时间坐标和信号到期仍按实际记录时间。先看[三种时间依据对照](intervals.md#timing-basis)。

| 表/API | 每行回答的问题 |
|---|---|
| calculations / iter_calculations | 某个计算项在会话、事件或片段内的值、单位、覆盖和质量如何 |
| events / iter_events | 哪条规则在何时开始、确认和结束；状态和触发原因是什么 |
| segments / iter_segments | 哪个窗口得到什么起止范围，与哪些事件有关 |
| sequences / iter_sequences | 哪个请求匹配了哪个响应，何时作出决定，延迟多少 |
| selections / iter_selections | select明确选择的样本时刻、值、类型、单位和有效状态 |
| input_trace / iter_input_trace | 明确请求详细追溯时的输入位置和记录种类 |
| contributions / iter_contributions | outputs.contributions=full时的逐消息贡献与跳过原因 |

计算行按实际操作返回SummaryCalculationRow或带coverage_status的SummaryCoverageCalculationRow；普通信号计算integral、duration、min_time、max_time、time_weighted_mean、sample_minimum、sample_maximum和sample_mean在minimum_coverage大于0时返回coverage_status。sufficient表示所需的观测、值有效性和条件已知范围均达到门槛；indeterminate表示不足或无法确定。这个字段不是数值覆盖率，也不会把样本统计改成时间加权统计。select明细和逐消息累计不属于这组标量结果。显式填0与省略不会因此增加coverage_status。各类完整字段均列在[摘要行模型](reference/chronaxis.results.summary.md)。公开表的相同字段在CSV和JSONL中表示同一事实。

显式csv输出原CSV结果表和run_manifest.json；jsonl每行包含版本与row字段对象。清单记录本次运行和实际写出的表；可读模式的row_counts按合并后的文件行数计数。配置标识不是输入文件内容的哈希，不能据此认定两次数据相同。

<a id="result-publication"></a>

## 结果怎样发布

程序先在目标目录旁创建临时目录，写完全部结果表、请求的导出文件和运行清单，并确认文件已关闭，再把整个临时目录改名为目标目录。发布前失败不会把半套结果作为正式完成结果交付；已有目标目录不会被覆盖。当前目录发布只验收Windows。这里的一次发布指整个结果目录，不是逐个文件分别提交。

## 缺失不是零

value为空时要结合status、reason和quality看原因。无效更新覆盖前值，过期产生未知，程序不会把缺口补成0。minimum_coverage只判断是否达到所需覆盖；partial_policy=report保留可以说明的部分结果，strict按现有规则拒绝不足覆盖的数值，不能把未观测的时段当成已知。

### 用实际输出理解partial

在[入门配置](examples/analysis.yaml)中，为power显式设置valid_for: 1s，覆盖DBC周期1s所推导的默认有效期3s，并在energy计算项设置partial_policy。其他输入和[0,6)秒分析范围保持相同。[2,3)和[5,6)内旧功率已到期，又没有新值，因此只有4秒能计算能量：2W×1s＋4W×1s＋8W×1s＋10W×1s＝24J。

| energy的partial_policy | value | status | reason | 如何使用结果 |
|---|---|---|---|---|
| report | 24.0 | partial | partial_coverage | 24J仅代表已知4秒的能量，不能当作完整6秒的总能量。 |
| strict | 空值 | indeterminate | insufficient_coverage | 数据不足，无法按完整范围给出数值；不能把空值换成0。 |

本例两行的quality均包含STALE，表示有效期已过。应按真实采集规律核对valid_for、数据时间和遗漏记录，不能仅为消除partial就调大有效期。完整数据可以得到complete；partial表示已有可用的部分值，indeterminate表示当前策略或证据不足以给出数值。具体原因仍以相应计算项的reason为准。

## 事件与配对

事件的start_ns是活动起点，confirmed_ns是达到确认门槛的时刻，end_ns是结束时刻或空值。所有_ns字段使用整数纳秒，不代表“秒数的浮点值”。

配对行直接提供request_id、response_id、decided_ns、delay_ns和status。matched表示找到响应；no_response表示完整等待期间可判断但没有响应；indeterminate表示缺数据或观测提前结束，不能下无响应结论。没有请求就没有配对行。

<a id="quality-flags"></a>
## quality：把数字还原为质量原因

CSV/JSONL的quality是整数位标记，可以同时包含多个原因，不是严重程度分数，也不是单个错误编号。0表示没有记录这些原因，仍须看status、reason或valid；例如缺少插值右端时可以是quality=0、status=missing、reason=missing_right。

| 数值 | 名称 | 意思与排查方向 |
|---|---|---|
| 1 | MISSING | 缺少需要的观测或值；核对输入列和缺失标记。 |
| 2 | STALE | 最近值超过valid_for；核对真实更新间隔和漏帧。 |
| 4 | DECODE_ERROR | 来源解码错误；核对DBC与报文结构。 |
| 8 | NONFINITE | NaN或无穷；核对输入值。 |
| 16 | OUT_OF_RANGE | 超出允许范围或编码映射；核对范围及编码表。 |
| 32 | ESTIMATED | 估计值标志；基础信号质量策略不把它当实际有效观测。 |
| 64 | OVERFLOW | 运算超出数值范围；检查数量级和表达式。 |
| 128 | PRECISION_LOSS | 转换无法精确表示；检查整数大小和目标类型。 |
| 256 | DOMAIN_ERROR | 除零等数学值域错误；检查公式。 |

例如3=1+2，表示MISSING与STALE都出现过。不能写`quality == 1`来判断是否含缺失，否则会漏掉3；应检查`quality & 1`。Python可直接使用枚举：

```python
from chronaxis.core.types import QualityFlag
quality = QualityFlag(3)  # CSV文字须先int转换；未知位或负数会报ValueError
names = [flag.name for flag in QualityFlag if quality & flag]
print(names)             # ['MISSING', 'STALE']
```

可运行对照：[quality.yaml](examples/quality.yaml)读取合成[quality.asc](examples/data/can/quality.asc)与[teaching.dbc](examples/data/can/teaching.dbc)。0秒Power为10W，1秒解码值为-1e100，2秒恢复为10W，4秒收到不含Power的报文并结束观测。配置明确将-1e100列入invalid_values，并选择valid_for: 1s。

只有[0,1)及[2,3)有有效功率，因此energy=20J、status=partial、reason=partial_coverage。当前CAN例的quality=18，即OUT_OF_RANGE（16）加STALE（2）：[1,2)命中无效码，替换此前有效值；[3,4)功率已过期。程序没有补0或继续沿用无效值。运行`chronaxis run quality.yaml --output quality-result`核对。

本例1秒时出现显式无效码，产生OUT_OF_RANGE（16）；2秒恢复的10W在3秒到期，产生STALE（2）。只有[0,1)和[2,3)可积分，共20J，status为partial，quality=16+2=18。上面的quality=3是质量位读法示意，不是本例输出。

<a id="result-status"></a>
## 各种结果的状态字段

不同表的字段集合不同，不要统一索引status/reason；先确认正在读哪种结果。下面的入口链接到实际行模型，包含完整参数与约束。

| 结果 | 判断字段与含义 | 模型 |
|---|---|---|
| 普通/逐消息汇总计算 | status=complete/partial/indeterminate：完整、部分可用、无法确定；reason说明原因 | [SummaryCalculationRow](reference/chronaxis.results.summary.md#api-SummaryCalculationRow) |
| 有覆盖门槛的计算 | 还含coverage_status=sufficient/indeterminate，表示门槛判定；不是数值覆盖率 | [SummaryCoverageCalculationRow](reference/chronaxis.results.summary.md#api-SummaryCoverageCalculationRow) |
| 事件 | status=point为点事件；closed正常结束；interrupted因未知中断；truncated观测结束；timeout超时。trigger是触发类型，事件没有reason列 | [SummaryEventRow](reference/chronaxis.results.summary.md#api-SummaryEventRow) |
| 窗口片段 | status=complete/partial/empty；empty没有实际起止范围；没有reason列 | [SummarySegmentRow](reference/chronaxis.results.summary.md#api-SummarySegmentRow) |
| 请求响应 | status=matched/no_response/indeterminate；没有reason列，结合quality及关联事件 | [SummarySequenceRow](reference/chronaxis.results.summary.md#api-SummarySequenceRow) |
| 样本选择 | valid说明值是否有效；selection=true/unknown说明选择条件；没有status/reason列 | [SummarySelectionRow](reference/chronaxis.results.summary.md#api-SummarySelectionRow) |
| 消息贡献 | reason=contributed表示计入；missing_input缺值；condition_false方向条件不满足；evaluation_error表达式失败；nonfinite_input输入非有限；没有status列 | [SummaryContributionRow](reference/chronaxis.results.summary.md#api-SummaryContributionRow) |
| 信号插值导出 | status=observed/estimated/missing；reason如missing_right说明没有可用的右端记录 | [信号导出](signal-exports.md) |

普通时间计算的reason按下表处理，不应把所有空值都叫“缺数据”：

| reason | 含义 | 处理 |
|---|---|---|
| ok | 计算满足当前要求 | 连同单位、范围和quality读取 |
| partial_coverage | report保留已有部分 | 核对缺失范围，不能当全程总量 |
| insufficient_coverage | strict不接受不足覆盖 | 补数据或重新确认业务接受标准 |
| zero_length_window | 计算窗口长度为0 | 核对窗口起止和事件 |
| no_observation | 没有观测 | 核对输入与请求时间范围 |
| calculation_failed | 数值计算失败 | 解读quality，检查公式和数值范围 |
| empty_selection | 条件可判断但未选中数据 | 积分/时长可为0；均值等不伪造0 |
| unknown_selection | 无法判断选择条件 | 检查条件信号缺失或过期 |
| no_samples / no_valid_selected_data | 没有可参与所需运算的样本/有效数据 | 核对样本选择、类型和质量 |

<a id="result-relationships"></a>
## 用实例ID关联三张结果表

同一个hot规则可能产生很多次事件，因此rule_id=hot只是配置定义名称，不能唯一定位某次活动。关联时使用同一运行目录中的event_id/segment_id；不要按表的行顺序拼接，也不要只按sequence跨表拼接。

以下来自[activity.yaml](examples/activity.yaml)的一次真实运行。为了表格可读，E1、S1仅是这里的显示缩写，实际字段保存下列完整字符串；使用时读取自己这次输出中的ID，不硬编码本例字符串。

- E1（event_id）：`3d7375484e46c0da41755d73629db92c3f87b98da58891b2c238c5a6517b848f`
- S1（segment_id）：`127695a43e932e2ceeb70f0319294829572ba84c9af8fb793e9b41eb40013de9`

| 表 | 配置定义名称 | 本次实例/父引用 | 业务值 |
|---|---|---|---|
| events | rule_id=hot | event_id=E1 | start=1秒，confirmed=3秒，end=6秒 |
| segments | window_id=hot_context | segment_id=S1；parent_event_ids=[E1] | [0,7)秒 |
| calculations | calculation_id=event_energy | scope=event；parent_id=E1 | 50J |
| calculations | calculation_id=context_energy | scope=segment；parent_id=S1 | 70J |

合并窗口可能对应多个事件，因此parent_event_ids是列表，不是一个事件ID。session范围的计算parent_id为None；CSV中是空单元格，JSONL中是null。Python使用如下关联步骤；放在仍然打开的AnalysisResult上下文内，仅适用于能装入内存的小型结果，完整关闭示例见[复核脚本](examples/activity_relationships.py)。

```python
events = {row.event_id: row for row in result.iter_events()}
segments = {row.segment_id: row for row in result.iter_segments()}
for row in result.iter_calculations():
    if row.scope == "event":
        event = events[row.parent_id]
        print(event.rule_id, event.start_ns, row.value, row.unit)
    elif row.scope == "segment":
        segment = segments[row.parent_id]
        parent_events = [events[event_id] for event_id in segment.parent_event_ids]
        print(segment.window_id, len(parent_events), row.value, row.unit)
    else:
        print("session", row.value, row.unit)
```

大结果应将三表按完整ID导入数据库或分批索引；不要为了关联把整份数据都list化。跨多次运行汇总时还需保留运行目录/运行身份，防止将不同运行的实例混在一起。

## 独立导出

信号CSV与CAN报文导出由outputs单独请求，文件索引位于exports.jsonl，目录在exports/下。原值和插值后的估计值有各自文件；CAN原帧与重建帧不混称原始输入。导出网格不改变分析积分间隔，见[导出](exports.md)。

<a id="metadata-output"></a>
## 运行清单的摘要与详细字段

RunMetadata保存运行信息，to_dict()决定哪些字段写入JSON。默认detailed_diagnostics=False输出run_id、plan_hash、backend、config_version、started_at、device_label、software_version、source_time_interpretation、parsing_policy、worker_config、retain_work和detailed_diagnostics；输入身份、会话边界、限制等仅在满足对应条件时补充。开启trace/integrity还会输出相应诊断信息。

| 模型状态 | 默认摘要模式 | detailed_diagnostics=True |
|---|---|---|
| signal_bindings含一条信号定义 | 字典中没有signal_bindings键 | 字典展开该信号定义 |
| 存有preset_bindings或CAN来源详情 | 不因非空自动输出 | 按详细序列化分支输出，空可选项仍可能省略 |

因此不能用某个详细键缺失推断模型从未持有该信息。普通读取清单时先确认输出模式，再查看键是否存在；不要为读取不存在的明细盲目索引字典。当前AnalysisRunner生成摘要模式元数据；配置diagnostics只接受trace、integrity、retain_work，不存在detailed或detailed_diagnostics配置开关。上表说明RunMetadata模型的序列化分支，不代表公开运行会填充所有模型字段。可用诊断设置见[执行设置](execution.md)。

当前公开Runner的metadata.can_sources和metadata.text_can_sources均为空元组。这两个字段用于接收调用方明确提供的来源明细，不能根据字段名假定运行后一定有值。需要核对实际输入诊断时，使用当前支持的diagnostics配置和对应结果，见[运行参数](execution.md)；仅将元数据转换为详细模式不会补出缺失明细。

## 为什么运行成功却没有事件

命令完成只表示任务没有执行错误。CLI 的 `analysis_outcome` 和运行清单的
`run.analysis_outcome` 说明业务结果；Python 可读
`result.metadata.analysis_outcome.to_dict()`。这些信息随原有计算累计，不另扫输入。

| 规则状态 | 含义与检查方向 |
|---|---|
| `no_observation` | 没有规则所需观测；检查输入、通道、ID和信号，`unobserved_signals`列出未见到的信号 |
| `insufficient_data` | 有数据，但未知或失效区间妨碍判断；检查缺值、无效码和有效期 |
| `condition_not_met` | 有可判断的数据，条件没有成立 |
| `duration_not_met` | 条件曾成立，但没有达到所选的持续时间要求 |
| `events_found` | 已生成事件；仍需查看计算结果的状态，不能据此认为全部数据完整 |
| `no_event` | 其他规则没有形成事件，例如没有出现所需边沿 |

`event_count` 是实际事件数；`has_unknown` 表示规则处理过程中出现过未知，
它可以与已有事件并存。`calculations` 中的 `complete`、`partial`、`indeterminate`
分别计数已写出的计算行，`no_observation` 是其中无观测行的数量，不是第四类互斥状态。
概况用于定位问题，不替代各行的 `reason` 和 `quality`。

事件起止与能量通过本页前述 `event_id` / `parent_id` 关联；不在每行计算结果中
重复保存事件时间。可直接运行的例子见[条件持续超过60秒后积分](conditional-energy.md)。
