# chronaxis.RunMetadata

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.results.manifest.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [RunMetadata](#api-RunMetadata)
- [RunMetadata.estimated_bytes](#api-RunMetadata-estimated_bytes)
- [RunMetadata.to_dict](#api-RunMetadata-to_dict)

<a id="api-RunMetadata"></a>
## `RunMetadata`

保存一次运行的身份、实际计算后端、时间解释及诊断摘要。通常从仍打开的AnalysisResult.metadata读取，不需要自行构造。来源明细字段是可选模型：只有调用方提供真实读取明细时才有内容。当前AnalysisRunner没有填充can_sources和text_can_sources，两者保持空元组；这不表示没有读取CAN文件，也不表示DBC已经校验。to_dict的摘要与详细模式见下方方法说明。

```python
RunMetadata(run_id: str, input_identity: str | None, plan_hash: str, backend: str, config_version: int, source_time_interpretation: str, session_boundaries: tuple[tuple[str, int, int], ...], started_at: str, mapping_hashes: tuple[str, ...] = (), dbc_hashes: tuple[str, ...] = (), parsing_policy: str = 'decoded-results', worker_config: str = 'single-thread', dependency_versions: tuple[tuple[str, str], ...] = (), limitations: tuple[str, ...] = (), software_version: str = '0.1.0.dev0', device_label: str = 'pending', signal_bindings: tuple[chronaxis.core.binding.SignalDefinition, ...] = (), preset_bindings: tuple[chronaxis.results.binding_metadata.PresetBindingMetadata, ...] = (), can_sources: tuple[chronaxis.results.can_metadata.CANSourceMetadata, ...] = (), session_ids: tuple[str, ...] = (), text_can_sources: tuple[chronaxis.results.text_can_metadata.TextCANSourceMetadata, ...] = (), threshold_durations: tuple[chronaxis.results.threshold_metadata.SummaryThresholdDuration, ...] = (), detailed_diagnostics: bool = False, retain_work: bool = False, input_diagnostics: tuple[chronaxis.results.input_diagnostics.InputDiagnostic, ...] = (), trace_requested: bool = False, integrity_diagnostics: bool = False, frame_format_notices: tuple[tuple[str, chronaxis.results.can_metadata.CANFrameFormatNotice], ...] = (), analysis_outcome: chronaxis.results.analysis_outcome.AnalysisOutcome | None = None) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`run_id`|str|是|无|本次运行唯一标识，与发布清单及资源事实关联。|
|`input_identity`|str &#124; None|是|无|读取实际输入的追溯摘要；None表示本运行没有提供该摘要，不能据此判断输入内容已核验。|
|`plan_hash`|str|是|无|计划声明的SHA-256身份，实际后端覆盖另行记录。|
|`backend`|str|是|无|读取本次实际采用的计算后端：reference为参考实现，numpy为数组实现。由Runner的有效运行设置记录，用户通常不手工构造这个结果字段。|
|`config_version`|int|是|无|本次实际分析配置的结构版本，必须是原生整数3；不是预设version，也不是软件版本。版本1及布尔值均被拒绝。|
|`source_time_interpretation`|str|是|无|来源时间解释文本，说明坐标、单位及转换约定。|
|`session_boundaries`|tuple[tuple[str, int, int], ...]|是|无|记录实际会话边界，每项为(session_id,start_ns,end_ns)，时间为整数纳秒、范围左闭右开。由执行器取得，空元组表示未建立这些边界，不能当作已观测零时长。|
|`started_at`|str|是|无|记录本次运行开始时间，由执行器生成带时区的ISO8601文本，例如2026-10-27T19:00:00+08:00；不是数据中第一条采样时间。|
|`mapping_hashes`|tuple[str, ...]|否|()|实际映射身份摘要元组；不涉及时为空，空值不等于已验。|
|`dbc_hashes`|tuple[str, ...]|否|()|实际DBC摘要元组；不涉及时为空。|
|`parsing_policy`|str|否|'decoded-results'|本次采用的解析/接入政策名称。|
|`worker_config`|str|否|'single-thread'|本次执行worker配置说明，不将单线程标签当性能保证。|
|`dependency_versions`|tuple[tuple[str, str], ...]|否|()|实际记录的依赖(name,version)元组。|
|`limitations`|tuple[str, ...]|否|()|本次已知限制文本元组，发布时保持可见。|
|`software_version`|str|否|'0.1.0.dev0'|软件版本文本，与设计版本和配置版本分开。|
|`device_label`|str|否|'pending'|实际内容来源设备标签；不能根据文件所在路径猜home/work。|
|`signal_bindings`|tuple[[SignalDefinition](../reference/chronaxis.core.binding.md#api-SignalDefinition), ...]|否|()|本次实际完整定义，不含样本或输入行。|
|`preset_bindings`|tuple[[PresetBindingMetadata](../reference/chronaxis.results.binding_metadata.md#api-PresetBindingMetadata), ...]|否|()|原预设版本及最终角色。|
|`can_sources`|tuple[[CANSourceMetadata](../reference/chronaxis.results.can_metadata.md#api-CANSourceMetadata), ...]|否|()|保存CANSourceMetadata对象元组，每项描述sclicer-functions-v1单BLF读取的来源名、原文件与DBC路径、通道、帧数、首末时间和单位检查等。由构造RunMetadata的调用方显式传入，当前公开AnalysisRunner不填充，默认()表示未提供此类明细，不表示没有CAN输入。确有元素时可用metadata.can_sources[0].source和.frame_count读取；先检查元组非空。|
|`session_ids`|tuple[str, ...]|否|()|无时间请求仍明确会话身份，绝不伪造边界。|
|`text_can_sources`|tuple[[TextCANSourceMetadata](../reference/chronaxis.results.text_can_metadata.md#api-TextCANSourceMetadata), ...]|否|()|保存TextCANSourceMetadata对象元组，每项描述can-text-v1读取的来源、inputs中的(path, parser, offset_ns)、DBC摘要、记录数和观测时间。由调用方显式提供，当前公开AnalysisRunner不填充；默认()表示未提供此类明细。确有元素时可用metadata.text_can_sources[0].inputs和.record_count读取；不能把空元组理解为输入为空。|
|`threshold_durations`|tuple[[SummaryThresholdDuration](../reference/chronaxis.results.threshold_metadata.md#api-SummaryThresholdDuration), ...]|否|()|读取阈值预设的累计时长摘要元组；每项SummaryThresholdDuration包含preset_id、rule_id、value、unit和status。partial的value是已知部分秒数，不能当作完整总时长；无此预设时为空元组。|
|`detailed_diagnostics`|bool|否|False|记录是否在清单中序列化额外详细诊断。True包含相应明细，False使用摘要；这是结果模型字段，公开Runner返回的设置不能靠修改此字段补做分析。|
|`retain_work`|bool|否|False|显式现场留存请求，不默认保留工作文件。|
|`input_diagnostics`|tuple[[InputDiagnostic](../reference/chronaxis.results.input_diagnostics.md#api-InputDiagnostic), ...]|否|()|仅按请求记录同次所需输入范围。|
|`trace_requested`|bool|否|False|记录本次是否请求输入逐条追溯：True对应diagnostics.trace开启，False不请求；实际记录通过结果追溯迭代器读取。|
|`integrity_diagnostics`|bool|否|False|记录本次是否请求输入完整性摘要：True对应diagnostics.integrity开启，False不请求；它与逐条追溯开关独立。|
|`frame_format_notices`|tuple[tuple[str, [CANFrameFormatNotice](../reference/chronaxis.results.can_metadata.md#api-CANFrameFormatNotice)], ...]|否|()|同次已核差异始终提示，独立于可选诊断。|
|`analysis_outcome`|[AnalysisOutcome](../reference/chronaxis.results.analysis_outcome.md#api-AnalysisOutcome) &#124; None|否|None|同次执行累计的AnalysisOutcome或None：逐规则说明有事件、条件未成立、未达到时长、无观测或数据不足，并分别统计complete/partial/indeterminate指标行。None表示该路径未提供概况，不能当作无事件；completed只说明执行结束。无二次输入扫描或逐条追溯。|

源码：[`src/chronaxis/results/manifest.py:28`](../../../src/chronaxis/results/manifest.py#L28)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RunMetadata-estimated_bytes"></a>
### `RunMetadata.estimated_bytes`

在asdict/JSON复制前估算元数据与其临时对象开销。

```python
RunMetadata.estimated_bytes() -> int
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

保守bytes估算。

#### 异常说明

无，类型已经校验。

返回类型：int。

源码：[`src/chronaxis/results/manifest.py:199`](../../../src/chronaxis/results/manifest.py#L199)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RunMetadata-to_dict"></a>
### `RunMetadata.to_dict`

返回独立JSON兼容元数据，调用侧必须先预留estimated_bytes。

```python
RunMetadata.to_dict() -> dict
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

独立JSON兼容dict。默认detailed_diagnostics=False只输出运行摘要及适用的可选摘要；即使模型的signal_bindings/preset_bindings/can_sources非空，也不输出这些详细键。True时展开详细模型，空的可选明细仍按规则省略。两种模式及键示例见[运行清单](../results.md#metadata-output)。

#### 异常说明

无预期异常；调用方须在复制前承担estimated_bytes预算。

返回类型：dict。

源码：[`src/chronaxis/results/manifest.py:210`](../../../src/chronaxis/results/manifest.py#L210)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
