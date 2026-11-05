# 输出配置与结果发布



根级`outputs`选择结果文件格式、逐消息贡献及额外数据导出。`AnalysisRunner.run()`先执行分析并准备暂存，`result.write(结果目录)`发布文件；CLI run会完成这两步。

分析表回答“发生了什么、算出多少”；信号CSV保存时间和值；ASC/BLF保存CAN报文字节。三者用途不同，可以一起输出。输入是ASC也可以输出BLF，不要求输入、输出格式相同。

**重采样**表示按你指定的等间隔时间重新取值。例如原电压在10ms为10V、120ms为120V，要求每100ms一行，程序可在100ms用两点之间的直线估计为100V。这个值标为estimated，表示这是估算值，而非100ms处的真实采样。它使用了后面的120ms数据，适合离线整理；规则与积分仍按原数据计算，不使用这些估计值。

## 当前导出环境限制

当前信号CSV和CAN报文导出路径会检查根级`metadata.device_label`，仅接受`home`或`work`。这是现有实现的开发设备标签限制，标签不参与时间或数值计算。导出示例的`home`记录样例产生环境，不表示任意用户的设备都应填写home。普通CSV分析无需此字段；批处理的报告标签允许非空自定义文本，不能将批处理标签规则套用于独立导出路径。

缺少所需标签或填写其他值时，当前导出会失败。该限制不影响不请求这些导出的普通分析。

## outputs的全部字段

outputs是配置顶层的可选对象。例如YAML写法`outputs: {tables: jsonl}`。下表字段相对于outputs，例如tables的完整路径为`outputs.tables`。表格格式不会改变计算结果，两个额外导出可以分别开启。

|字段|数据类型|必填|默认值|可填写的值与含义|
|---|---|---|---|---|
|tables|字符串|否|`"readable_csv"`|选择普通分析结果表的保存格式。`"readable_csv"`输出方便直接阅读的表格；`"csv"`保留稳定机器字段；`"jsonl"`每行保存一个对应摘要行的JSON对象，适合逐行读取。|
|manifest|字符串|否|`"json"`|选择运行清单的格式，用于查询本次输入、设置和输出表。运行清单格式，当前填json或省略。|
|contributions|字符串|否|`"none"`|控制是否保存逐消息的每次求值与跳过明细；需要逐条排查时选full。`"full"`保留每条目标消息的计算明细；`"none"`只累计汇总，不额外保留逐次明细计数。普通计算不使用逐消息贡献开关。|
|signal_csv|对象或null|否|`null`，关闭|控制额外导出哪些信号及是否重采样；填写下级配置启用。导出所选原信号，全部字段见[信号导出](signal-exports.md)。|
|can_frames|对象或null|否|`null`，关闭|控制额外导出哪个CAN来源及格式/重建；填写下级配置启用。导出一个CAN来源的报文，全部字段见[CAN导出](can-exports.md)。|

BLF、ASC和原始报文CSV的报文导出均配置在`outputs.can_frames`中，使用下文的来源、格式和范围字段。

<a id="export-scope"></a>
### 导出范围

| scope写法 | 作用 | 适用导出 |
|---|---|---|
| 省略或`session` | 导出本次会话范围 | 信号CSV、CAN报文 |
| `{window: context}` | 导出名为context的窗口产生的片段 | 信号CSV、CAN报文 |
| `{windows: all}` | 导出所有窗口产生的片段 | 仅CAN报文 |

窗口名来自`windows[].name`。范围写在`outputs.signal_csv.scope`或`outputs.can_frames.scope`字段中，可以是session字符串或表中对象，不再另填window字段。空值不是有效scope；信号导出需明确一个窗口，不能使用windows: all。

两类导出各自选择scope，互不影响。范围包含起点、不包含终点，例如1～2秒的片段含1秒、不含2秒；插值不会从范围外借样本补端点。

## 选择导出类型

- [信号CSV与重采样](signal-exports.md)：导出物理量更新，或生成等间隔数值。
- [CAN报文与重采样](can-exports.md)：导出ASC/BLF原帧，或重建指定字段。

## 输出文件位置

直接调用Python的export_signal_csv或export_can_frames时，返回ExportManifest，包含output_dir、manifest_path和output_files。目录可复用，实际文件带时间后缀；使用返回属性，不再把返回对象当Path。普通配置导出由运行清单的exports记录定位。

调用run时先在工作目录准备导出文件；调用 `result.write()` 后，它们才与分析表一起出现在指定的最终输出目录。

从本次运行清单的exports.index_file找到带时间后缀的导出索引，可以找到每次导出的时间范围、数据来源和文件路径。实际文件放在 `exports_<时间后缀>/export-XXXXXXXX/` 子目录；仅在`diagnostics.integrity: true`时保存文件内容摘要；默认检查必要文件身份和大小。

同一个result再次write到同一或另一个结果目录，会检查并复制已经生成的文件，不再读取或解码原日志。

配套例子把3、7、3V分别保持1秒，积分仍为13V·s；大于5V的活动为`[1,2)`。同时请求250ms信号网格和500ms报文网格，不改变这两个分析结果。运行方式见[示例](examples.md)。所有导出类、函数和参数见[signal_exports](reference/chronaxis.results.signal_exports.md)、[signal_grid](reference/chronaxis.results.signal_grid.md)、[frame_exports](reference/chronaxis.results.frame_exports.md)、[frame_rebuild](reference/chronaxis.results.frame_rebuild.md)。

信号250ms与CAN500ms同时导出的完整输入、命令与核对见[双网格案例](examples.md#dual-grid)。
