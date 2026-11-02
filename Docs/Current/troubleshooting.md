# 故障排查

先确认失败发生在哪一步：安装、加载配置、读取输入、计算、读取结果或发布。保留完整异常链；CLI默认文字报告便于定位，`validate/explain --format json`用于程序读取。以下处理不会要求修改原始日志或覆盖既有结果。

<a id="api-errors"></a>
## Python调用：按失败阶段处理

PlanValidationError同时保存path、message、code。path是配置字段位置，source是文件路径；二者不可混用。只打印`$.batch_version`不够判断问题，应保留message中的实际约束及code，存在时再展示行列与hint。

```python
from chronaxis import load_analysis_plan, PlanValidationError
try:
    plan = load_analysis_plan("analysis.yaml")
except PlanValidationError as error:
    print(error.source, error.path, error.code, error.message, error.hint)
    raise  # 保留原始异常链；不要把加载失败当成空计划继续运行
```

| 阶段 | 常见错误/结果 | 调用者应做什么 |
|---|---|---|
| 加载或构造 | PlanValidationError，含unknown_field等机器code | 根据path/message修正配置；有source/location时一同定位 |
| 静态检查 | ValidationReport.errors或execution_ready=False | 处理报告；validate不代表输入文件已读取 |
| 运行 | AnalysisError，cause中可能为SourceReadError、BudgetExceededError、ValueError等 | 保留异常链，按读取/资源/表达式原因修正；不要吞成无事件 |
| 流式读结果 | ResultClosedError、ContributionsUnavailableError或暂存读取错误 | 在结果仍打开时读；缺贡献需要重新请求full运行 |
| 发布 | AnalysisError及其cause，例如目标已存在或文件写入失败 | 使用新目录并修正环境；结果未关闭时可重新发布，无需重读输入 |
| 批量 | 正常返回也可能有failed任务；基础设施异常可能带batch_report | 查jobs中的error_type/error_message/error_chain；保留已完成结果，对cleanup_pending调用close |
| 关闭 | 实际文件/资源关闭错误 | 保留结果或异常提供的清理对象，解除占用后重试close |

KeyboardInterrupt/SystemExit表示取消，不应作为成功返回。异常链上的runner_cleanup_owner或analysis_result_cleanup_owner只在失败清理未完成时出现；检查属性存在后才调用其close，不假定每个错误都有这些属性。

## 环境与配置

| 现象或错误 | 原因与检查 | 修正动作 |
|---|---|---|
| No module named chronaxis | 当前解释器未安装项目，或编辑安装目录已移动 | 使用安装时的Python，按[安装页](installation.md)重新安装当前源码目录。 |
| 找不到numpy、ruamel.yaml或CAN模块 | 依赖装在其他环境，或安装时跳过了依赖 | 在运行任务的同一Python环境重新安装chronaxis；CAN依赖随正常安装提供。 |
| PlanValidationError，路径如`$.signals[0].source` | 字段缺失、类型不符或引用名称不存在 | 按source/行列/字段路径检查；source应等于sources[].name，不填文件路径。 |
| 重复键、未知字段或旧版本错误 | 配置结构不符合当前规则 | 合并重复映射，核对大小写与拼写；config_version须为整数3。 |
| YAML锚点/别名/标签被拒绝 | 当前语法不支持这些功能 | 使用普通映射/列表；共享定义采用[imports](imports.md)。 |
| `unit: 1`被拒绝 | YAML将1解析为数字，单位要求字符串 | 无量纲写`unit: '1'`；只有确需显式指定预设版本时才写`version: '1'`，通常省略。 |
| 表达式不合法 | 使用原始列名、Python任意函数或不允许的属性路径 | 先在signals绑定name，再按[表达式](expressions.md)语法填写；YAML true与表达式True属于不同层。 |

## 文件、时间与解码

| 现象 | 检查步骤 | 修正动作 |
|---|---|---|
| 配置校验通过但run提示文件/列不存在 | 静态检查没有读取业务文件；相对路径以声明文件目录为起点 | 用config origins查看声明位置；核对path、time_column、field的实际拼写。 |
| 连续文件时间回退 | 后一个文件从0重新计时，或paths顺序错误 | 只有连续试验才放在同一来源；根据已知起点明确offset/offsets，不能任意增加时间掩盖回退。 |
| 两来源不能联合计算 | time.type/time.clock/单位或偏移不能证明同一时刻 | 使用真实同步依据设置共同时间基准，见[时间同步](inputs.md)。 |
| CAN报文不能解码 | 通道、标准/扩展帧、FD标志、ID或DBC定义不相符 | 核对field中的channel、frame_id、signal和DBC映射；帧型通常自动识别，提示歧义时才补充is_extended或is_fd。再检查实际帧长度。 |
| ASC或原始CSV格式错误 | reader.version、列映射、分隔符或时间格式与文件不一致 | 对照[文本CAN输入](text-inputs.md)；结构错误不能靠partial解码策略跳过。 |

## 结果为空或不完整

| 结果 | 如何解释与检查 | 后续动作 |
|---|---|---|
| value为空 | 查看operation、scope、status、reason、quality；没有样本、零长度、全未知和strict拒绝均可能为空 | 先确认请求范围与观测范围，再检查信号valid_for、无效值、条件。不要改成0掩盖原因。 |
| status=partial | 只算出所需范围内可确认的部分 | 对照[部分结果](execution.md)判断是否接受；调整policy不会补回原始观测。 |
| 没有事件 | 条件未持续够久、没有已知边沿、有效期不足或阈值/单位错误 | 检查规则类型和minimum_duration/emit_initial；用小段可手算数据复现。 |
| 请求配对indeterminate | 等待期间条件未知，或观测提前结束 | 核对响应来源覆盖与valid_for，不能直接报告设备无响应。 |
| 覆盖字段缺失 | minimum_coverage省略或为0，或操作不属于相关时间统计 | 查看实际行模型；公开摘要不提供三个数值覆盖率。 |
| ContributionsUnavailableError | 运行时未保存逐消息贡献 | 确有需要时设outputs.contributions: full并重新运行。 |
| iter_input_trace报AnalysisError | 未开启输入追溯 | 设diagnostics.trace: true后重新运行；它不等于全日志备份。 |
| ResultClosedError | 结果或游标已关闭/正在关闭 | 在AnalysisResult的with范围内完成读取；游标用try/finally显式close，不支持直接对游标使用with。 |

## 资源与发布

| 错误 | 原因与处理 |
|---|---|
| BudgetExceededError | 按异常资源项区分内存、结果缓冲或暂存磁盘；可减小batch_rows/result_buffer_rows，或在确认资源足够后调整对应配额。状态本身需要的内存未必随批次减小。 |
| 输出目标已存在 | 使用另一个新目录。程序不覆盖已有结果，空目录也不能当新目标。 |
| 发布目录位于自有工作目录内 | 默认close会清理该工作目录；把正式输出放在工作目录外。 |
| 非Windows发布失败 | 当前安全发布路径尚未在该平台验收；按[支持范围](status.md)选择环境。 |
| 独立信号/CAN导出标签失败 | 当前实现限制metadata.device_label为home/work，见[输出限制](exports.md)；普通分析可不请求这些导出。 |
| 暂存格式损坏或读取OSError | 停止使用该结果，保留异常及必要现场，检查文件访问和磁盘；不要吞掉异常当作空表。 |
| 批量返回报告但部分任务失败 | 查看batch_report.json中每个任务的状态、错误与输出路径；修正失败项后独立重跑，避免覆盖已完成目录。 |

需要保留现场时，在下一次复现配置中设置`diagnostics.retain_work: true`；需要输入位置时再单独开启trace。记录配置、命令、错误链、运行清单和可共享的最小合成输入，以便重现。
