# 先决定什么能算，再生成配置

|任务|必须核实|判断方法|
|---|---|---|
|确定输入|BLF/ASC 的日志、DBC、通道、报文与字段；CSV 的真实表头和时间单位|若不同时间基准需要联合计算，提供共同起点、偏移或其他明确同步证据。不能将两文件都从0计时当作同步依据。|
|名称绑定|原始字段在输入中定位；name是分析名称；semantic_id是可选的语义标识|字段 BMS_I 绑定为 pack_current，语义标识 battery.current 时，表达式使用 pack_current > 5。不能把点号标识写成对象属性。候选不唯一时要求指定。|
|单位与方向|已有DBC换算、物理单位、正向含义及测点|已解码2000 mA→2 A，只需额外的单位变换。单位标签、sign_convention都不会改变数值；公开配置没有 direction_factor，不能把同单位 scale=-1 当通用翻转。|
|状态编码|明确每个码对应的业务状态|编码2是否充电要看设备定义。用户已给编码比较时保留数值类型，直接写state == 0x2；只有需要真假或文字状态时才用布尔/枚举映射，未知映射码不按非零为真。没有资料时列出缺项，不给可投用的充电判断。|
|有效期|valid_for为正时长。显式值优先；否则取本信号period的3倍，适用时可待运行取得DBC报文周期；没有依据则不能猜。显式null不等于省略。|0秒更新、period=100ms，0.299秒可沿用，0.300秒起未知。若0.2秒已收到无效更新，则从0.2秒未知。有效期不决定采样率，不产生记录。|
|条件与统计|明确请求区间、观测范围、选择集合、partial_policy|充分观测且全程已知为假时条件积分可为0；空选择的最小/最大/均值为空。无观测或全未知不能报正常0；部分数值须连同status、reason、quality解释。|
|事件与片段|两段真实活动可合并为一个片段，间隙不因此成为活动|同一运行的segments.parent_event_ids可对应多个events.event_id。计算按scope和parent_id关联，不能按行号或只按规则名称拼接。|
|时序与输出|批大小仅影响执行分块；未知响应与可判定超时不同。实际时间积分与逐消息累计不同。|核对explain中的依赖、间隔、输出单位和实际请求范围。coverage_status仅在相应结果类型和门槛时出现，不是数值覆盖率；不要虚构coverage。|
|业务预设|例如充电的mode/current及请求能量时的voltage；电流方向、单位和位置须满足预设契约|缺项或两个合格候选不自动选第一项；显式角色绑定仍须通过契约。范例的工程阈值和编码不能套给另一车型。|

## 从报告定位错误

先记录用户要保留的信号、条件、范围和输出。用 validate 请求 JSON。已构建计划用 valid、execution_ready、errors、warnings、capability_status；加载失败时读单个 error 的 code/source/path/line/column/message/hint 等实际提供值。explain 的同一报告在 validation 下，依赖在 nodes 和 input_requirements 下。环境、I/O 或参数错误可能只有非零退出码和 stderr；没有 JSON 不能判断为通过。

例如，把分析配置的 config_version 写成字符串 "3" 会被拒绝：只改成整数3，保留原计算，再重新检查。不要删筛选、调大有效期、忽略未知或把负号反过来“修复”诊断。修正两轮仍失败时交付真实错误和剩余事实，不伪造可运行输出。

```text
python -m chronaxis config origins ../Current/examples/analysis-imports.yaml --fields --format json
python -m chronaxis config resolve ../Current/examples/analysis-imports.yaml --defaults --format json
python -m chronaxis validate ../Current/examples/input-csv-minimal.yaml --format json
python -m chronaxis explain ../Current/examples/input-csv-minimal.yaml --format json
```

origins回答字段来自哪个声明；resolve展示展开后的配置和当前可确定的默认值。待DBC读取的周期不是在此处虚构的固定值。load_analysis_plan按定义所在文件解释路径；AnalysisPlan.from_dict只接收已展开的字典。校验不能证明实际观测、真实单位或结果正确。交付时写明使用的版本、输入、关键假设、实际执行的检查和未验条件。

## 持续门槛与积分起点

`condition_duration`的`minimum_duration: 60s`默认表示达到60秒。用户要求“超过60秒”时增加`duration_comparison: ">"`，不改成60.1秒。`selection_origin`默认`onset`，整个合格区间参与积分；只有用户要求从持续确认之后计算才选择`confirmed`。恰好60秒的活动：默认有事件，严格模式无事件。时间精度为1ns；实际模式最早在门槛后1ns确认，固定/DBC模式等下一条使累计严格超过门槛的驱动报文。

## 资源不足时保留原任务

样本最小值、最大值和均值会在现有共享内存预算内分块归约，结果与批次大小无关；没有要求统计时不要为了调试自动加入它们。出现预算错误先核对报错的计算项、工作区或读取缓冲，不能直接把所有问题归结为机器内存不足。样本统计的最小块仍放不下时会明确失败；减少读取批量只改变执行分批，不应改变条件、有效期或丢弃输入。调大预算须有实际资源依据，预算估算与进程RSS不是同一数值。

## CAN通道、连续文件与检查范围

配置中的DBC映射键、显式信号通道、逐报文选择器和原帧重采样通道统一从1开始。ASC文件第一路写1，配置也写1；不要手动减1。单一来源通道的信号/选择器可以省略channel。内部0基编号由程序转换，原始CSV的reader.channel_origin仍说明文件列原来从0还是1编号。旧配置0需迁移，不能通过修改原始日志来匹配。

配置路径相对于该字段所在配置/公共定义文件；字典API以base_dir为基准（省略为当前工作目录）。`chronaxis explain PLAN --format json`显示计划信息；`chronaxis config resolve PLAN --format json`可查看展开后的配置。一个来源内多文件按给定顺序连续处理，候选状态跨文件保持；目录匹配按自然序。同一文件夹不自动证明是同会话，独立试验用批量入口，不为拼接擅加时间偏移。

ASC默认仅对本任务所需通道/ID检查时间先后；来源范围仍在同次读取中取所有帧的最早/最晚时间。目标回退仍报错，完整检查或原帧导出仍要求全来源有序。不要运行额外全文件检查再自动清洗；微秒差小也不能作为修改输入的理由。

## 默认可读结果

普通配置省略outputs.tables时，输出readable_csv：中文文件名/列名、精确秒、一个事件或窗口的指标在同一行。读取run_manifest.json.outputs确定实际文件，不能硬编码events.csv/calculations.csv。显式outputs.tables: csv或jsonl继续使用原程序交换格式和整数纳秒；只生成选中的一套表。

可读表保留计算名称和单位；空单元格不是0，各指标独立显示完整、部分有效或无法确定及原因。事件区间状态与指标状态分别看。全局has_unknown不否定已有区间内完整的计算；无事件说明见清单result_messages，不生成虚假能量0。时间保留原分析坐标，不能擅自补日期或从零平移；不重复保存ns和秒。Python iter_events/iter_calculations等仍返回原类型化行。

## 独立批量的进程数

批量文件根级process_count控制分析工作进程上限，正整数，默认1，不含调度主进程及CAN读取子进程。run_batch(plan, output, process_count=4)和CLI --process-count 4可覆盖计划；None仅在API表示沿用计划。配置不接受null或布尔值。Python脚本需在if __name__ == "__main__":保护内调用。普通AnalysisRunner没有此参数，同一会话连续paths不拆分到独立进程。

每任务独立预算和输出，取消只阻止未启动任务。在途任务完成关闭；report.close()可重试远程清理。不要把未启动项或进程崩溃当成成功。旧workers/max_workers/--workers不再接受。

## 迁移数值与后端核对

旧INI中的秒数允许科学计数法；导入保留紧凑表示并检查可表示的时长，不能为了展示展开巨大指数。拒绝报告不代表成功生成分析计划。两个后端应按相同规则给出事件边界、状态和诊断；浮点数值按该指标的单位和约定误差比较，不要求二进制逐位相等，也不能用舍入误差解释事件或质量标志不一致。

普通标量计算（含样本统计）在minimum_coverage>0时可返回coverage_status；它是门槛判定，不是比例，也不改变样本均值的等权算法。初始边沿emit_initial看的是第一次已知状态，不是分析中任意第一次True。用户请求的末端只有实际观测且满足规则时才能产生点事件。
