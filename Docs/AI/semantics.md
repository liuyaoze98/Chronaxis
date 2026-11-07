# 先决定什么能算，再生成配置

## 同一会话的连续分卷

同一次充电的多个ASC/BLF放在同一sources来源，使用execution.process_count正整数设置文件读取/解码上限，默认1。普通run/validate/explain的--process-count及AnalysisRunner同名仅关键字参数可覆盖；主进程连续处理事件/TTL/积分。file_merge: concatenate按文件顺序接续；time_order在各文件内部所需时间有序且时钟可比较时稳定归并，不平移、不去重。不要拆成多个batch jobs再相加。当前仅一个ASC/BLF来源、requested解码；批量worker内不嵌套文件池。time_order使用本次受配额暂存；资源共用，不保证进程越多越快。参见[完整可运行指南](../Current/continuous-files.md)。

## 统计：功率波动与结果总体

先确认问题中的“一次”指报文、有效保持时长、活动、最终片段，还是已算出的一行结果。样本用真实有效更新，时间方法用条件已知为真的有效时长。样本方差或标准差可取 `ddof: 0` 或 1，时间版本只取 0，RMS 省略 `ddof`。对象计数以具名规则或窗口为准。完整且确定为空可以计 0，未观测需保留状态。分位数需要 `q`，中位数省略，内部概率的精确排序使用本次内存预算。

功率试验五条读数的 P95 是 18 W；两个活动均值 [10,20] W 的 P95 是 19.5 W。用户问“每次加载”时选择活动范围的指标，再用 `aggregations` 引用该计算的 `value`。成功响应延迟选具名 `sequence` 的 `delay_ns`。按组报告候选、参与、定义排除、质量排除、部分值及总体发现状态。默认排除部分指标，只有用户的总体定义要求纳入时才设置 `include_partial: true`。任务索引 ID 为 `POWER_STATISTICS`。[可运行的 ASC/DBC 案例](../Current/examples/power-statistics.yaml)

|任务|必须核实|判断方法|
|---|---|---|
|确定输入|BLF/ASC 的日志、DBC、通道、报文与字段；CSV 的真实表头和时间单位|若不同时间基准需要联合计算，提供共同起点、偏移或其他明确同步证据。不能将两文件都从0计时当作同步依据。|
|名称绑定|原始字段在输入中定位；name是分析名称；semantic_id是可选的语义标识|字段 BMS_I 绑定为 pack_current，语义标识 battery.current 时，表达式使用 pack_current > 5。不能把点号标识写成对象属性。候选不唯一时要求指定。|
|单位与方向|已有DBC换算、输入/目标单位；需要解释充放电时才核实方向和测点|版本4省略scale和offset时，根据输入/目标单位自动换算：DBC给出2000 mA、配置unit: A，得到2 A。显式填写任一系数时不再自动叠加换算。sign_convention只说明方向，不改变值；同单位scale=-1不能作为通用翻转。|
|状态编码|明确每个码对应的业务状态|编码2是否充电要看设备定义。用户已给编码比较时保留数值类型，直接写state == 0x2；只有需要真假或文字状态时才用布尔/枚举映射，未知映射码不按非零为真。没有资料时列出缺项，不给可投用的充电判断。|
|有效期|valid_for为正时长。显式值优先；否则取本信号period的3倍，适用时可待运行取得DBC报文周期；没有依据则不能猜。显式null不等于省略。|0秒更新、period=100ms，0.299秒可沿用，0.300秒起未知。若0.2秒已收到无效更新，则从0.2秒未知。有效期不决定采样率，不产生记录。|
|条件与统计|明确请求区间、观测范围、选择集合、partial_policy|充分观测且全程已知为假时条件积分可为0；空选择的最小/最大/均值为空。无观测或全未知不能报正常0；部分数值须连同status、reason、quality解释。|
|事件与片段|两段真实活动可合并为一个片段，间隙不因此成为活动|同一运行的segments.parent_event_ids可对应多个events.event_id。计算按scope和parent_id关联，不能按行号或只按规则名称拼接。|
|时序与输出|批大小仅影响执行分块；未知响应与可判定超时不同。实际时间积分与逐消息累计不同。|核对explain中的依赖、间隔、输出单位和实际请求范围。coverage_status仅在相应结果类型和门槛时出现，不是数值覆盖率；不要虚构coverage。|
|业务预设|例如充电的mode/current及请求能量时的voltage；电流方向、单位和位置须满足预设契约|缺项或两个合格候选不自动选第一项；显式角色绑定仍须通过契约。范例的工程阈值和编码不能套给另一车型。|

## 从报告定位错误

不要仅凭退出码1或2猜测错误类型。普通命令缺少配置文件通常返回1；fast validate/explain/run在准备配置、DBC或输入清单时失败返回2。fast batch有独立分类，最终批量报告写出失败也可能返回2。应同时读取stderr及已生成的任务报告，并按所用CLI命令的阶段说明判断；非零退出不表示既有结果已撤销。

先记录用户要保留的信号、条件、范围和输出。用 validate 请求 JSON。已构建计划用 valid、execution_ready、errors、warnings、capability_status；加载失败时遍历 errors 数组，每项读取 code/source/path/line/column/message/hint 等实际提供值；blocked_checks说明被无效依赖阻断的检查。单错也使用数组，不再返回单独error。explain 的同一报告在 validation 下，依赖在 nodes 和 input_requirements 下。环境、I/O 或参数错误可能只有非零退出码和 stderr；没有 JSON 不能判断为通过。

例如，把分析配置的 config_version 写成字符串 "4" 会被拒绝：只改成整数4，保留原计算，再重新检查。不要删筛选、调大有效期、忽略未知或把负号反过来“修复”诊断。修正两轮仍失败时交付真实错误和剩余事实，不伪造可运行输出。

```text
python -m chronaxis config origins ../Current/examples/analysis-imports.yaml --fields --format json
python -m chronaxis config resolve ../Current/examples/analysis-imports.yaml --defaults --format json
python -m chronaxis validate ../Current/examples/input-csv-minimal.yaml --format json
python -m chronaxis explain ../Current/examples/input-csv-minimal.yaml --format json
```

origins回答字段来自哪个声明；resolve展示展开后的配置和当前可确定的默认值。待DBC读取的周期不是在此处虚构的固定值。load_analysis_plan按定义所在文件解释路径；AnalysisPlan.from_dict只接收已展开的字典。校验不能证明实际观测、真实单位或结果正确。交付时写明使用的版本、输入、关键假设、实际执行的检查和未验条件。

## 持续门槛与积分起点

`condition_duration`必须填写`duration_comparison`，没有默认比较方式。配合`minimum_duration: 60s`，用户要求“达到/至少60秒”时填`">="`，要求“超过60秒”时填`">"`，不改成60.1秒。未说明是否包含恰好60秒且会影响结果时，先向用户确认；不能擅自选择。`selection_origin`默认`onset`，整个合格区间参与积分；只有用户要求从持续确认之后计算才选择`confirmed`。恰好60秒的活动：`>=`有事件，`>`无事件。时间精度为1ns；实际模式最早在门槛后1ns确认，固定/DBC模式等下一条使累计严格超过门槛的驱动报文。

## 资源不足时保留原任务

样本最小值、最大值和均值会在现有共享内存预算内分块归约，结果与批次大小无关；没有要求统计时不要为了调试自动加入它们。出现预算错误先核对报错的计算项、工作区或读取缓冲，不能直接把所有问题归结为机器内存不足。样本统计的最小块仍放不下时会明确失败；减少读取批量只改变执行分批，不应改变条件、有效期或丢弃输入。调大预算须有实际资源依据，预算估算与进程RSS不是同一数值。

## CAN通道、连续文件与检查范围

配置中的 DBC 映射键、显式信号通道、逐报文选择器和原帧重采样通道统一从 `1` 开始。DBC 通道键使用无前导零的正整数文本，第一路写字符串 `"1"`；普通通道字段填写整数 `1`，不要手动减一。单一来源通道的信号或选择器可以省略 `channel`，程序会采用该来源的唯一通道。原始日志中的通道值保持原样。对于原始 CSV，`reader.channel_origin` 仍用于说明输入文件的通道列从 `0` 还是从 `1` 编号。

配置路径相对于该字段所在配置/公共定义文件；字典API以base_dir为基准（省略为当前工作目录）。`chronaxis explain PLAN --format json`显示计划信息；`chronaxis config resolve PLAN --format json`可查看展开后的配置。一个来源内多文件按给定顺序连续处理，候选状态跨文件保持；目录匹配按自然序。同一文件夹不自动证明是同会话，独立试验用批量入口，不为拼接擅加时间偏移。

ASC默认仅对本任务所需通道/ID检查时间先后；来源范围仍在同次读取中取所有帧的最早/最晚时间。目标回退仍报错，完整检查或原帧导出仍要求全来源有序。不要运行额外全文件检查再自动清洗；微秒差小也不能作为修改输入的理由。

## 默认可读结果

普通配置省略outputs.tables时，输出readable_csv：中文文件名/列名、精确秒、一个事件或窗口的指标在同一行。读取CLI返回的manifest或API返回的manifest_path，再从清单outputs确定本次实际文件，不能硬编码events.csv/calculations.csv。显式outputs.tables: csv或jsonl继续使用原程序交换格式和整数纳秒；只生成选中的一套表。

可读表保留计算名称和单位；空单元格不是0，各指标独立显示完整、部分有效或无法确定及原因。事件区间状态与指标状态分别看。全局has_unknown不否定已有区间内完整的计算；无事件说明见清单result_messages，不生成虚假能量0。时间保留原分析坐标，不能擅自补日期或从零平移；不重复保存ns和秒。Python iter_events/iter_calculations等仍返回原类型化行。

## 独立批量的进程数

批量文件根级process_count控制分析工作进程上限，正整数，默认1，不含调度主进程及CAN读取子进程。run_batch(plan, output, process_count=4)和CLI --process-count 4可覆盖计划；None仅在API表示沿用计划。配置不接受null或布尔值。Python脚本需在if __name__ == "__main__":保护内调用。普通AnalysisRunner另有读取/解码进程上限，配置为execution.process_count；同一会话连续paths保持一个分析状态，不拆成独立任务。

每任务独立预算和输出，取消只阻止未启动任务。在途任务完成关闭；report.close()可重试远程清理。不要把未启动项或进程崩溃当成成功。旧workers/max_workers/--workers不再接受。

## 数值与后端核对

两个后端应按相同规则给出事件边界、状态和诊断；浮点数值按该指标的单位和约定误差比较，不要求二进制逐位相等，也不能用舍入误差解释事件或质量标志不一致。

普通标量计算（含样本统计）在minimum_coverage>0时可返回coverage_status；它是门槛判定，不是比例，也不改变样本均值的等权算法。初始边沿emit_initial看的是第一次已知状态，不是分析中任意第一次True。用户请求的末端只有实际观测且满足规则时才能产生点事件。

## 版本4表达式怎么选

带单位常量写 `quantity(500,'mV')`，等于 0.5 V。按条件二选一用 `where`，未选分支缺值不作废当前结果。查标定曲线用 `lookup(voltage,'curve')`；先确认输入、输出单位和点对。编码 7 和 9 可有相同状态名，只有确实要区分两者时用 `enum_code(mode)`。查表例中 3、7、3 V 对应 10、30、10 W，样本平均约 16.67 W。分析配置仅接受整数版本4。

版本4的信号`unit`是目标单位。原始报文的输入单位可从DBC取得；已解码表需要用`conversion.input_unit`说明不同的输入单位。例如输入为mA、目标为A，省略`conversion.scale`和`conversion.offset`即可自动换算。若显式填写一个系数，另一个采用原有恒等默认值，并校验整套换算；不会再自动乘一次DBC系数。仅改结果单位文字、而不执行对应换算，不是有效转换。任务`UNITS`演示输入单位与目标单位之间的换算；无需重复填写可推导的倍率。


## 时序变换与宿主扩展

先核对实际时基、TTL、输出网格和间隔口径。固定/DBC的网格点在两真实驱动帧中间时，等后帧计算周期重叠比例，保留原网格时刻。adjacent_rate使用真实数值更新，max_gap按实际时间判断；window_rate取两个边界值，sample_fit_slope只对真实样本等权拟合。默认strict预热不足为未知，下游保留partial质量。配置引用宿主操作时索取真实Python程序、固定端口、版本与后端；加载和运行都传同一个注册。YAML没有模块导入入口。

## 选择连续分析的运行方式

同一次记录的多个 ASC／BLF 分卷先按 `CONTINUOUS_FILES` 组织：一份分析配置、同一个来源，保留跨文件信号状态、事件和积分。需要持续条件、跨帧取值、事件/窗口或按实际时间积分时，使用普通分析入口；例如持续条件能量任务使用 `CONDITION_ENERGY`，不会因输入分成多个文件而改用 fast。

只有公式的全部信号输入都来自当前报文、每条报文独立产生可累计贡献，且不需要上述能力时，才选择 `FAST_CONTINUOUS_SESSION`。此时 `execution.process_count` 控制读取、解码及同帧求值的工作进程上限，`file_merge` 控制文件组织顺序；主进程按规定顺序累计，不能用每文件部分和替代。多个独立试验按各自分析能力选择普通 batch 或 fast 的 `FAST_TEMPLATE_TOTAL`，不拆开连续会话。

`fast.run` 取消时抛出 `InterruptedError`。受管理预算不是整个进程树的物理内存上限。
