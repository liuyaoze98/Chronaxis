# `chronaxis.results.manifest`

定义运行清单和输出清单。运行清单记录配置、实际输入、时间解释、使用的实现及资源统计；输出清单记录发布后的文件和状态。未取得的信息保留为空，不把空值解释为检查通过。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AggregationPlan](chronaxis.planning.aggregations.md#api-AggregationPlan)、[AnalysisOutcome](chronaxis.results.analysis_outcome.md#api-AnalysisOutcome)、[CANFrameFormatNotice](chronaxis.results.can_metadata.md#api-CANFrameFormatNotice)、[CANSourceMetadata](chronaxis.results.can_metadata.md#api-CANSourceMetadata)、[CANUnitCheck](chronaxis.results.can_metadata.md#api-CANUnitCheck)、[InputDiagnostic](chronaxis.results.input_diagnostics.md#api-InputDiagnostic)、[Interval](chronaxis.core.models.md#api-Interval)、[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PresetBindingMetadata](chronaxis.results.binding_metadata.md#api-PresetBindingMetadata)、[PresetRoleMetadata](chronaxis.results.binding_metadata.md#api-PresetRoleMetadata)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[RuleOutcome](chronaxis.results.analysis_outcome.md#api-RuleOutcome)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SummaryThresholdDuration](chronaxis.results.threshold_metadata.md#api-SummaryThresholdDuration)、[TextCANSourceMetadata](chronaxis.results.text_can_metadata.md#api-TextCANSourceMetadata)、[ThresholdDurationMetadata](chronaxis.results.threshold_metadata.md#api-ThresholdDurationMetadata)

## 对象导航

|对象|用途|
|---|---|
|[`RunMetadata`](#api-RunMetadata)|保存一次运行的身份、实际计算后端、时间解释及诊断摘要。通常从仍打开的AnalysisResult.metadata读取，不需要自行构造。来源明细字段是可选模型：只有调用方提供真实读取明细时才有内容。当前AnalysisRunner没有填充can_sources和text_can_sources，两者保持空元组；这不表示没有读取CAN文件，也不表示DBC已经校验。to_dict的摘要与详细模式见下方方法说明。|
|[`RunMetadata.__post_init__`](#api-RunMetadata-__post_init__)|验证清单文本与明确会话范围，不访问外部输入。|
|[`RunMetadata.estimated_bytes`](#api-RunMetadata-estimated_bytes)|在asdict/JSON复制前估算元数据与其临时对象开销。|
|[`RunMetadata.to_dict`](#api-RunMetadata-to_dict)|返回独立JSON兼容元数据，调用侧必须先预留estimated_bytes。|
|[`_metadata_size`](#api-_metadata_size)|统计已校验元数据树的基础对象大小，不产生转换树。|
|[`OutputManifest`](#api-OutputManifest)|保存成功发布目录、清单和固定白名单表行数；legacy只在启用时出现。|
|[`OutputManifest.__post_init__`](#api-OutputManifest-__post_init__)|校验返回清单身份，不凭构造调用证明目录已发布。|
|[`ExportManifest`](#api-ExportManifest)|独立信号或原帧导出的实际输出路径；调用者无需猜测时间文件名。|
|[`ExportManifest.__post_init__`](#api-ExportManifest-__post_init__)|核对实际路径类型和所属目录。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, asdict, field, fields
from datetime import datetime
from math import isfinite, isnan
from pathlib import Path
from sys import getsizeof
from .._version import software_version
from ..core.validation import require_text, require_identifier
from ..core.models import Interval
from ..core.binding import SignalDefinition
from ..core.types import QualityFlag
from .binding_metadata import PresetBindingMetadata, PresetRoleMetadata
from .can_metadata import CANSourceMetadata, CANUnitCheck, CANFrameFormatNotice
from .text_can_metadata import TextCANSourceMetadata
from .threshold_metadata import ThresholdDurationMetadata, SummaryThresholdDuration
from .input_diagnostics import InputDiagnostic
from .analysis_outcome import AnalysisOutcome, RuleOutcome
from ..legacy.records import LegacyCANField
```

</details>

<a id="api-RunMetadata"></a>
## `RunMetadata`

保存一次运行的身份、实际计算后端、时间解释及诊断摘要。通常从仍打开的AnalysisResult.metadata读取，不需要自行构造。来源明细字段是可选模型：只有调用方提供真实读取明细时才有内容。当前AnalysisRunner没有填充can_sources和text_can_sources，两者保持空元组；这不表示没有读取CAN文件，也不表示DBC已经校验。to_dict的摘要与详细模式见下方方法说明。

```python
RunMetadata(run_id: str, input_identity: str | None, plan_hash: str, backend: str, config_version: int, source_time_interpretation: str, session_boundaries: tuple[tuple[str, int, int], ...], started_at: str, mapping_hashes: tuple[str, ...] = (), dbc_hashes: tuple[str, ...] = (), parsing_policy: str = 'decoded-results', worker_config: str = 'single-thread', dependency_versions: tuple[tuple[str, str], ...] = (), limitations: tuple[str, ...] = (), software_version: str = <factory>, device_label: str = 'pending', signal_bindings: tuple[chronaxis.core.binding.SignalDefinition, ...] = (), preset_bindings: tuple[chronaxis.results.binding_metadata.PresetBindingMetadata, ...] = (), can_sources: tuple[chronaxis.results.can_metadata.CANSourceMetadata, ...] = (), session_ids: tuple[str, ...] = (), text_can_sources: tuple[chronaxis.results.text_can_metadata.TextCANSourceMetadata, ...] = (), threshold_durations: tuple[chronaxis.results.threshold_metadata.SummaryThresholdDuration, ...] = (), detailed_diagnostics: bool = False, retain_work: bool = False, input_diagnostics: tuple[chronaxis.results.input_diagnostics.InputDiagnostic, ...] = (), trace_requested: bool = False, integrity_diagnostics: bool = False, frame_format_notices: tuple[tuple[str, chronaxis.results.can_metadata.CANFrameFormatNotice], ...] = (), analysis_outcome: chronaxis.results.analysis_outcome.AnalysisOutcome | None = None, aggregation_definitions: tuple = ()) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`run_id`|str|是|无|本次运行唯一标识，与发布清单及资源事实关联。|
|`input_identity`|str &#124; None|是|无|读取实际输入的追溯摘要；None表示本运行没有提供该摘要，不能据此判断输入内容已核验。|
|`plan_hash`|str|是|无|计划声明的SHA-256身份，实际后端覆盖另行记录。|
|`backend`|str|是|无|本次实际采用的数值实现reference或numpy；auto计划也记录选择后的值，不改变历史结果。|
|`config_version`|int|是|无|本次实际分析配置的结构版本，仅接受原生整数4；不是预设version，也不是软件版本。版本1及布尔值均被拒绝。|
|`source_time_interpretation`|str|是|无|来源时间解释文本，说明坐标、单位及转换约定。|
|`session_boundaries`|tuple[tuple[str, int, int], ...]|是|无|记录实际会话边界，每项为(session_id,start_ns,end_ns)，时间为整数纳秒、范围左闭右开。由执行器取得，空元组表示未建立这些边界，不能当作已观测零时长。|
|`started_at`|str|是|无|记录本次运行开始时间，由执行器生成带时区的ISO8601文本，例如2026-10-27T19:00:00+08:00；不是数据中第一条采样时间。|
|`mapping_hashes`|tuple[str, ...]|否|()|实际映射身份摘要元组；不涉及时为空，空值不等于已验。|
|`dbc_hashes`|tuple[str, ...]|否|()|实际DBC摘要元组；不涉及时为空。|
|`parsing_policy`|str|否|'decoded-results'|本次采用的解析/接入政策名称。|
|`worker_config`|str|否|'single-thread'|本次执行worker配置说明，不将单线程标签当性能保证。|
|`dependency_versions`|tuple[tuple[str, str], ...]|否|()|实际记录的依赖(name,version)元组。|
|`limitations`|tuple[str, ...]|否|()|本次已知限制文本元组，发布时保持可见。|
|`software_version`|str|否|调用 software_version() 生成|软件发行版本文本；省略时在每次构造RunMetadata时读取当前这份源码或安装包的版本，已构造对象不改写。与设计版本、配置版本分开；显式传入的历史版本保持原值。|
|`device_label`|str|否|'pending'|实际内容来源设备标签，使用用户提供的非空文本；不根据文件所在路径猜测。|
|`signal_bindings`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|否|()|本次实际完整定义，不含样本或输入行。|
|`preset_bindings`|tuple[[PresetBindingMetadata](chronaxis.results.binding_metadata.md#api-PresetBindingMetadata), ...]|否|()|原预设版本及最终角色。|
|`can_sources`|tuple[[CANSourceMetadata](chronaxis.results.can_metadata.md#api-CANSourceMetadata), ...]|否|()|保存CANSourceMetadata对象元组，每项描述sclicer-functions-v1单BLF读取的来源名、原文件与DBC路径、通道、帧数、首末时间和单位检查等。由构造RunMetadata的调用方显式传入，当前公开AnalysisRunner不填充，默认()表示未提供此类明细，不表示没有CAN输入。确有元素时可用metadata.can_sources[0].source和.frame_count读取；先检查元组非空。|
|`session_ids`|tuple[str, ...]|否|()|无时间请求仍明确会话身份，绝不伪造边界。|
|`text_can_sources`|tuple[[TextCANSourceMetadata](chronaxis.results.text_can_metadata.md#api-TextCANSourceMetadata), ...]|否|()|保存TextCANSourceMetadata对象元组，每项描述can-text-v1读取的来源、inputs中的(path, parser, offset_ns)、DBC摘要、记录数和观测时间。由调用方显式提供，当前公开AnalysisRunner不填充；默认()表示未提供此类明细。确有元素时可用metadata.text_can_sources[0].inputs和.record_count读取；不能把空元组理解为输入为空。|
|`threshold_durations`|tuple[[SummaryThresholdDuration](chronaxis.results.threshold_metadata.md#api-SummaryThresholdDuration), ...]|否|()|读取阈值预设的累计时长摘要元组；每项SummaryThresholdDuration包含preset_id、rule_id、value、unit和status。partial的value是已知部分秒数，不能当作完整总时长；无此预设时为空元组。|
|`detailed_diagnostics`|bool|否|False|记录是否在清单中序列化额外详细诊断。True包含相应明细，False使用摘要；这是结果模型字段，公开Runner返回的设置不能靠修改此字段补做分析。|
|`retain_work`|bool|否|False|显式现场留存请求，不默认保留工作文件。|
|`input_diagnostics`|tuple[[InputDiagnostic](chronaxis.results.input_diagnostics.md#api-InputDiagnostic), ...]|否|()|仅按请求记录同次所需输入范围。|
|`trace_requested`|bool|否|False|记录本次是否请求输入逐条追溯：True对应diagnostics.trace开启，False不请求；实际记录通过结果追溯迭代器读取。|
|`integrity_diagnostics`|bool|否|False|记录本次是否请求输入完整性摘要：True对应diagnostics.integrity开启，False不请求；它与逐条追溯开关独立。|
|`frame_format_notices`|tuple[tuple[str, [CANFrameFormatNotice](chronaxis.results.can_metadata.md#api-CANFrameFormatNotice)], ...]|否|()|同次已核差异始终提示，独立于可选诊断。|
|`analysis_outcome`|[AnalysisOutcome](chronaxis.results.analysis_outcome.md#api-AnalysisOutcome) &#124; None|否|None|同次执行累计的AnalysisOutcome或None：逐规则说明有事件、条件未成立、未达到时长、无观测或数据不足，并分别统计complete/partial/indeterminate指标行。None表示该路径未提供概况，不能当作无事件；completed只说明执行结束。无二次输入扫描或逐条追溯。|
|`aggregation_definitions`|tuple[[AggregationPlan](chronaxis.planning.aggregations.md#api-AggregationPlan), ...]|否|()|本次运行使用的聚合定义及总体政策。非空时随清单序列化，省略时不增加该字段。|

源码：[`src/chronaxis/results/manifest.py:29`](../../../src/chronaxis/results/manifest.py#L29)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunMetadata-__post_init__"></a>
### `RunMetadata.__post_init__`

验证清单文本与明确会话范围，不访问外部输入。

```python
RunMetadata.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为结构或事实格式错误。

本函数直接报告的具体错误：

- `ValueError`：结果清单需实际reference/numpy及配置版本1。
- `ValueError`：started_at必须带时区。
- `TypeError`：session_boundaries需tuple。
- `TypeError`：依赖版本需(name,version)tuple。
- `TypeError`：贡献输出清单需要ContributionOutputMetadata或None。
- `TypeError`：运行绑定清单需SignalDefinition及PresetBindingMetadata tuple。
- `ValueError`：运行绑定清单不能重复别名。
- `ValueError`：运行绑定清单不能重复预设ID。
- `ValueError`：预设最终角色必须引用本清单实际信号别名。
- `TypeError`：阈值汇总需ThresholdDurationMetadata tuple。
- `ValueError`：阈值汇总必须对应本次预设及生成规则，不能重复。
- `TypeError`：独立会话身份需要无重复tuple。
- `TypeError`：文本CAN清单需要TextCANSourceMetadata tuple。
- `ValueError`：文本CAN清单来源重复。
- `TypeError`：CAN运行清单需要CANSourceMetadata tuple。
- `ValueError`：CAN运行清单来源重复。
- `TypeError`：会话边界需(session_id,start,end)。
- `TypeError`：清单会话边界需原生int纳秒。
- `TypeError`：清单映射/限制需要非空文本tuple。
- `ValueError`：文本CAN清单会话错误。
- `ValueError`：文本CAN单位清单必须覆盖实际绑定。
- `ValueError`：CAN运行清单会话不属于本次session_boundaries。
- `ValueError`：CAN单位清单必须恰好覆盖同来源本次实际绑定别名。
- `ValueError`：CAN单位核对别名/来源/input_unit与本次原声明不同。
- `ValueError`：CAN帧型提示必须对应本次原信号完整定位。
- `ValueError`：requested固定解码集合须覆盖本次实际绑定字段及同来源通道。

返回类型：None。

源码：[`src/chronaxis/results/manifest.py:73`](../../../src/chronaxis/results/manifest.py#L73)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

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

源码：[`src/chronaxis/results/manifest.py:205`](../../../src/chronaxis/results/manifest.py#L205)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

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

源码：[`src/chronaxis/results/manifest.py:216`](../../../src/chronaxis/results/manifest.py#L216)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_metadata_size"></a>
## `_metadata_size`

统计已校验元数据树的基础对象大小，不产生转换树。

```python
_metadata_size(value) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。结果清单中的元数据字段或嵌套结构，用于估算其占用内存。|

### 返回说明

基础bytes估算。

### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/results/manifest.py:306`](../../../src/chronaxis/results/manifest.py#L306)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-OutputManifest"></a>
## `OutputManifest`

保存成功发布目录、清单和固定白名单表行数；legacy只在启用时出现。

```python
OutputManifest(run_id: str, output_dir: pathlib.Path, manifest_path: pathlib.Path, output_files: tuple[pathlib.Path, ...], row_counts: tuple[tuple[str, int], ...], status: str = 'completed') -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`run_id`|str|是|无|本次运行唯一标识，与发布清单及资源事实关联。|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|已经成功发布的结果目录绝对Path。|
|`manifest_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|本次实际运行清单的绝对Path，文件名含时间后缀；读取它而不是拼固定文件名。|
|`output_files`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|是|无|本次实际发布的文件路径元组。|
|`row_counts`|tuple[tuple[str, int], ...]|是|无|各固定结果表的实际行数记录。|
|`status`|str|否|'completed'|本次发布结果状态，成功为completed。|

源码：[`src/chronaxis/results/manifest.py:333`](../../../src/chronaxis/results/manifest.py#L333)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-OutputManifest-__post_init__"></a>
### `OutputManifest.__post_init__`

校验返回清单身份，不凭构造调用证明目录已发布。

```python
OutputManifest.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为字段错误。

本函数直接报告的具体错误：

- `ValueError`：OutputManifest需completed和Path。
- `TypeError`：输出路径需tuple Path。
- `ValueError`：输出行数需固定表及非负原生int。

返回类型：None。

源码：[`src/chronaxis/results/manifest.py:343`](../../../src/chronaxis/results/manifest.py#L343)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportManifest"></a>
## `ExportManifest`

独立信号或原帧导出的实际输出路径；调用者无需猜测时间文件名。

```python
ExportManifest(output_dir: pathlib.Path, manifest_path: pathlib.Path, output_files: tuple[pathlib.Path, ...]) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|本次导出所在目录，可以含有旧结果。|
|`manifest_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|本次带时间后缀的完成清单Path，直接使用实际返回路径。|
|`output_files`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|是|无|本次导出的数据文件Path元组，不含由manifest_path单独提供的完成清单。|

源码：[`src/chronaxis/results/manifest.py:360`](../../../src/chronaxis/results/manifest.py#L360)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportManifest-__post_init__"></a>
### `ExportManifest.__post_init__`

核对实际路径类型和所属目录。

```python
ExportManifest.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

类型或路径错，不访问文件。

源码：[`src/chronaxis/results/manifest.py:367`](../../../src/chronaxis/results/manifest.py#L367)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
