# 架构与数据处理流程



先看使用者能看到的过程：读取ASC/BLF并用DBC取得时间、功率和状态（也可读取已解码CSV）；按条件找出工作开始/结束；对每次工作算能量；最后写成表格。下面各层只是把这些步骤分工，不需要用户自己调用每一个内部模块。

文中的“绑定”是把字段对应到表达式名称，“后端”是计算实现，“暂存”是先写入工作目录的中间文件，完整解释见[术语表](terms.md)。

## 通用分析从输入记录到计算结果

```text
Python调用 / CLI
   │ AnalysisPlan.from_dict / load_analysis_plan
   ▼
planning：检查来源、别名、单位、表达式、规则和输出；展开业务预设
   │ AnalysisRunner.validate / explain（静态检查已加载计划，不读取业务报文）
   ▼
runner.AnalysisRunner → execution.run_session.RunSession
   │ 打开需要的输入，设置资源额度，准备工作目录
   ├─ memory：配置中的时间和值
   ├─ signal_csv：逐批读取表格
   └─ can_blf / can_asc / raw_can_csv：按文件格式读原始报文 → 共用DBC解码 → 所需字段
   ▼
字段对应到名称、换算单位 → 处理同时刻更新 → 检查有效期 → 计算表达式和条件
   │                          core的reference与NumPy计算函数
   ▼
事件 → 片段 → 会话/事件/片段计算；请求点与响应点另按sequences配对
   │ 从已保存的信号历史读取，不重新解码原日志
   ▼
ResultSpool：按资源上限把结果写入工作目录并排序
   ▼
AnalysisResult：行迭代器 → write → 表格、导出文件、数据问题记录、运行清单 → 写入结果目录，文件名带本次时间后缀
```

通用入口的逐消息累计还有独立路线：匹配目标报文 → 只用当条解码值求值 → 累加贡献。纯汇总场景可直接累计，在没有其他规则或指标需要时，省去普通信号历史；此处只用当条目标报文解出的值，缺少所需值就跳过，不沿用上一条补算，也不重复乘真实时间差。模式区别见[逐消息计算](message-calculations.md)。

fast run将同一ASC/BLF来源的多个分卷作为一个会话。工作进程流式读取、解码并计算当前报文贡献，主进程按file_merge指定的顺序逐条累计；execution.process_count控制工作进程上限，1在当前进程执行。任何必需分卷读取、求值或关闭失败都会使会话失败。fast batch用于独立试验，各任务在本地累计。配置和可运行示例见[高性能积分器](fast-energy.md)。

## 每一层解决什么问题

|包/入口|输入→输出|应在什么情况下查看|
|---|---|---|
|[chronaxis](reference/chronaxis.md)、[AnalysisRunner](reference/chronaxis.runner.md)|计划→检查报告或AnalysisResult|应用程序入口；根包按需加载计划/执行组件|
|[planning](reference/chronaxis.planning.md)|YAML/JSON解析后的Python字典→不可修改的计划、所需输入和能力报告|增加配置声明、排查字段/单位/角色错误|
|[presets](reference/chronaxis.presets.md)|角色绑定和参数→普通规则/窗口/指标|理解业务预设如何复用普通规则/配对/指标|
|[sources](reference/chronaxis.sources.md)|来源声明与读取请求→原始报文或SignalBatch|接入内存、CSV和CAN文件；检查格式解析、DBC解码、批次和来源定位|
|[timebase](reference/chronaxis.timebase.md)|时间文本和单位→整数纳秒；无法精确换算时附舍入说明|排查时间单位、偏移、精度或超出可表示范围的问题|
|[core](reference/chronaxis.core.md)|已绑定信号/条件→事件、片段、数值和质量|了解数学与时间边界；不负责打开CAN文件|
|[execution](reference/chronaxis.execution.md)|分析计划和分批输入→最终结果行|查看如何接着上一批继续计算、按时间合并多来源、回读历史数据及释放资源|
|[legacy](reference/chronaxis.legacy.md)|CAN记录及行为标识→消息暂存、进程协议和BLF导出接入|核对保留的报文行为、低层读写协议及清理；读取调用sources中的共用实现，BLF写出调用results.blf_writer|
|[results](reference/chronaxis.results.md)|已算好的结果行→工作目录中的暂存文件→最终输出目录|查看结果字段、输出顺序、逐行读取，以及写文件失败时的处理|

例如[execution.record_session_calculations](reference/chronaxis.execution.record_session_calculations.md)按会话调度所需计算，[execution.record_scope_calculations](reference/chronaxis.execution.record_scope_calculations.md)处理事件/片段范围。应用程序调用AnalysisRunner即可完成这些步骤。

## 为什么既有历史文件又有结果暂存

有些结果要等事件结束才能知道统计区间，`pre`还可能引用触发前的数据。如果只保留最新样本，这些计算会丢掉前文。历史存储保存计算所需的解码后时间和信号值，后续从它回读；结果暂存保存已经算完的最终行，供排序、流式读取与多次发布。两者职责不同。

内存预算约束新分析层的缓冲与状态；磁盘配额约束暂存。它们不表示整个Python进程占用的物理内存绝不会超过这个数；解释器、NumPy和文件解码库等还有预算外开销，整个进程的物理内存需另行测量。预算范围见[运行设置](execution.md)。使用量超过配置允许的资源上限时会报错，不能丢数据继续生成正常结果。

## 两个计算后端怎么分工

`reference`与`numpy`按照相同规则计算，但数值代码分别实现，因此可以用同一输入比较结果。事件边界、状态和质量标志应一致；浮点值可能因运算顺序产生末位舍入差异，应按指标单位和约定的绝对/相对误差核对，不能把这种容差用于掩盖状态或诊断不一致。默认auto按整份计划选择reference或numpy，具体类别见[执行设置](execution.md)。numpy实现对内建流式表达式直接处理当前时刻的值；适合批量处理的计算仍把多条值放入数组，并标明哪些位置有效。扩展算子仍调用其登记的numpy接口。

读文件、记录活动是否已经开始、管理内存和关闭文件，仍由Python控制。`explain`会列出各个计算步骤采用的实现；选择numpy不代表整个流程的每一步都由NumPy执行。

`AnalysisRunner(backend="reference")`可以覆盖本次计算方式。本次运行清单中，run.plan_hash仍标识原配置，run.backend记录本次实际采用的计算后端；不能仅凭plan_hash相同就认为两次采用了相同后端。批次边界是内存安排，不是业务结束：一次持续活动跨过多个批次仍是同一活动。

## CAN读取、解码与写出

ASC、BLF和原始报文CSV使用项目内共用的读取与DBC解码模块，BLF写出复用共用写入器。保留的行为政策见[输入与解码](inputs.md#decode-policy)；通用核心仍独立处理计划、时序规则和计算。逐消息累计的公式与输入要求见[逐消息计算](message-calculations.md)。

按需解码与字段裁剪由计划依赖决定，实际读取和检查范围可通过explain查看。具体任务只处理所需字段，额外诊断按配置请求生成。

## 单任务与批量任务的调用关系

```text
CLI / Python API
 ├─ 单任务 AnalysisRunner
 │   ├─ planning：解析事件规则、业务预设、配对和输出选项
 │   ├─ sources：内存 / 信号CSV / ASC、BLF与原始CAN CSV
 │   ├─ execution：按时间更新信号，保留跨文件与分批的状态
 │   │   ├─ core：表达式、持续/边沿、迟滞/防抖、start_end、window_delta
 │   │   └─ sequence：等待请求、匹配响应、判断缺失与超时
 │   └─ results：事件、片段、计算和配对表，以及信号CSV和报文文件
 └─ batch：为每个独立任务分别创建AnalysisRunner、工作目录与报告
```

配置解释在读日志前进行；但某帧是否能被DBC解码、实际时间是否回退，要到run读取时才能确认。ASC和原始报文CSV先解析文本，BLF读取二进制帧；三种格式再按所选政策进行DBC解码。通用分析使用相同的信号和时间规则，核心没有车型、报文ID或DBC名称依赖。

window_delta保留计算窗口所需的过去数据；迟滞、防抖、start_end保留当前状态和截止时间；sequence保存等待配对的请求。这些状态跨batch_rows和连续文件保留，在独立任务之间隔离。把分批大小改小不会把活动从头再算。

导出所需的信号和原始报文在本次读取时保存。导出等间隔的电压、电流等数据时，可以利用前后两条记录估算中间值；这些估算值不会反过来改变已经计算的事件或积分。

信号CSV和CAN报文各自配置导出范围、取样周期和起点。内存或暂存空间不足时会报错，程序不会丢弃样本或缩短窗口后继续。

相关模块入口：[batch](reference/chronaxis.batch.md)、[text_inputs](reference/chronaxis.planning.text_inputs.md)、[record_exports](reference/chronaxis.execution.record_exports.md)、[stability](reference/chronaxis.core.stability.md)、[sequence](reference/chronaxis.core.sequence.md)。
