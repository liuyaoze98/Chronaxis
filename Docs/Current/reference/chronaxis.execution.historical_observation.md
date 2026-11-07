# `chronaxis.execution.historical_observation`

核对实际读取记录，计算每个来源观察到的时间范围。时间基准可比较的来源分到同一组；没有数据或缺少同步依据时，不能从请求窗口猜出一个共同范围。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)、[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[HoldContext](chronaxis.execution.hold.md#api-HoldContext)、[Interval](chronaxis.core.models.md#api-Interval)、[ObservedSourceScan](chronaxis.execution.observed_ingestion.md#api-ObservedSourceScan)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[SourceScanObservation](chronaxis.execution.observed_ingestion.md#api-SourceScanObservation)、[TimeType](chronaxis.core.types.md#api-TimeType)

## 对象导航

|对象|用途|
|---|---|
|[`ObservationScope`](#api-ObservationScope)|保存一个可比时钟组的有限范围事实，本身不提供真实读取证明。|
|[`ObservationScope.__post_init__`](#api-ObservationScope-__post_init__)|校验冻结组和标量端点，不把完整时间范围外范围建成Interval。|
|[`_SourceScopeProof`](#api-_SourceScopeProof)|保留有限逐源证明副本，不持有原行、SourceSpec.rows或整个计划副本。|
|[`HistoricalObservationScopes`](#api-HistoricalObservationScopes)|拥有预建组、有限证明及一个历史reader，关闭不接管任何借用资源。|
|[`HistoricalObservationScopes.__init__`](#api-HistoricalObservationScopes-__init__)|核对全部真实扫描、原合同及当前文件EOF，再冻结按时钟分组的范围。|
|[`HistoricalObservationScopes._clock_key`](#api-HistoricalObservationScopes-_clock_key)|返回完整可比组键。|
|[`HistoricalObservationScopes._require_contract`](#api-HistoricalObservationScopes-_require_contract)|核原会话、domain、声明绑定及来源集合。|
|[`HistoricalObservationScopes._validate_source`](#api-HistoricalObservationScopes-_validate_source)|逐项核真实扫描、当前元数据与绑定，不访问原输入行。|
|[`HistoricalObservationScopes._verify_source`](#api-HistoricalObservationScopes-_verify_source)|用一个真实reader核当前文件完整EOF，拒绝提前close冒充耗尽。|
|[`HistoricalObservationScopes._build_scopes`](#api-HistoricalObservationScopes-_build_scopes)|按原计划来源序建立全部组及domain内交集。|
|[`HistoricalObservationScopes._adopt_cleanup`](#api-HistoricalObservationScopes-_adopt_cleanup)|接管实际未返回的历史reader。|
|[`HistoricalObservationScopes.closed`](#api-HistoricalObservationScopes-closed)|读取自有关闭状态。|
|[`HistoricalObservationScopes.assert_current`](#api-HistoricalObservationScopes-assert_current)|核调用方仍使用原四对象、活扫描和同一当前历史元数据。|
|[`HistoricalObservationScopes.identity`](#api-HistoricalObservationScopes-identity)|借读包含实际原行/分组的稳定摘要。|
|[`HistoricalObservationScopes.source_observations`](#api-HistoricalObservationScopes-source_observations)|按原计划序借读有限分源事实副本。|
|[`HistoricalObservationScopes.dataset_scope`](#api-HistoricalObservationScopes-dataset_scope)|借读无依赖的dataset时钟组。|
|[`HistoricalObservationScopes.for_dependencies`](#api-HistoricalObservationScopes-for_dependencies)|按展开后的原信号依赖借读预建范围，保留原同步及实际投影门槛。|
|[`HistoricalObservationScopes.for_source`](#api-HistoricalObservationScopes-for_source)|借读实际来源所属的已核时钟组，空信号投影也必须有同次来源证明。|
|[`HistoricalObservationScopes.close`](#api-HistoricalObservationScopes-close)|可重试关闭自有reader与有限副本，不关闭任何原扫描/history/lease。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, replace
from ..core.decoded_binding import DecodedBindings
from ..core.models import Interval
from ..core.types import TimeType
from ..core.validation import require_identifier
from ..planning.plan import AnalysisPlan
from ..results.errors import ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..timebase.conversion import require_int64_ns
from .bindings import _fingerprint
from .history import DecodedHistoryStore, _metadata_bytes
from .history_records import HistoryProgress, HistorySample
from .hold import HoldContext
from .observed_ingestion import ObservedSourceScan, SourceScanObservation
```

</details>

<a id="api-ObservationScope"></a>
## `ObservationScope`

保存一个可比时钟组的有限范围事实，本身不提供真实读取证明。

```python
class ObservationScope
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`clock_key`|tuple|是|无|完整时钟组身份；dataset、独立relative和独立UTC分开。|
|`sources`|tuple[str, ...]|是|无|同组全部来源名称，顺序为原计划来源顺序。|
|`observed_start_ns`|int &#124; None|是|无|有原行来源的组外包络首端，单位整数ns。|
|`observed_end_ns`|int &#124; None|是|无|外包络末端，逐端检查，不先计算域外跨度。|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|与原domain的交集；None为空，Interval(t,t)是真实单点。|

源码：[`src/chronaxis/execution/historical_observation.py:41`](../../../src/chronaxis/execution/historical_observation.py#L41)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ObservationScope-__post_init__"></a>
### `ObservationScope.__post_init__`

校验冻结组和标量端点，不把完整时间范围外范围建成Interval。

```python
ObservationScope.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、来源重复或端点矛盾。

本函数直接报告的具体错误：

- `TypeError`：观测范围需要冻结时钟key及来源tuple。
- `ValueError`：观测时钟组来源不能重复。
- `ValueError`：观测时钟组首末端须同时已知或同时无观测。
- `ValueError`：观测时钟组末端不能早于首端。
- `TypeError`：actual须为Interval或明确None。
- `ValueError`：实际交集不能超出已核实组端点。

源码：[`src/chronaxis/execution/historical_observation.py:50`](../../../src/chronaxis/execution/historical_observation.py#L50)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_SourceScopeProof"></a>
## `_SourceScopeProof`

保留有限逐源证明副本，不持有原行、SourceSpec.rows或整个计划副本。

```python
class _SourceScopeProof
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|原来源名。|
|`description_sha256`|str|是|无|当前实际描述完整指纹。|
|`request_sha256`|str|是|无|真正写入该history的原请求指纹。|
|`history_sha256`|str|是|无|构造中实际读到文件EOF后核实的规范历史SHA。|
|`counts`|tuple[int, int]|是|无|原进度记录数、原信号样本数。|
|`observation`|[SourceScanObservation](chronaxis.execution.observed_ingestion.md#api-SourceScanObservation)|是|无|本owner拥有的有限原行和端点事实副本。|
|`clock_key`|tuple|是|无|该来源实际进入的可比时钟组。|

源码：[`src/chronaxis/execution/historical_observation.py:79`](../../../src/chronaxis/execution/historical_observation.py#L79)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes"></a>
## `HistoricalObservationScopes`

拥有预建组、有限证明及一个历史reader，关闭不接管任何借用资源。

```python
HistoricalObservationScopes(history, context, bindings, plan, source_scans)
```


源码：[`src/chronaxis/execution/historical_observation.py:91`](../../../src/chronaxis/execution/historical_observation.py#L91)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-__init__"></a>
### `HistoricalObservationScopes.__init__`

核对全部真实扫描、原合同及当前文件EOF，再冻结按时钟分组的范围。

```python
HistoricalObservationScopes.__init__(history, context, bindings, plan, source_scans)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。本次分析保存的解码信号历史，必须已完成写入且尚未关闭；后续统计从这里读取，不重新解码输入文件。|
|`context`|[HoldContext](chronaxis.execution.hold.md#api-HoldContext)|是|无|位置或关键字。本会话的保持设置，含会话标识和时间范围；用它判断旧值可保持多久以及何时结束。|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)|是|无|位置或关键字。本次实际读取后建立的信号对应关系，包含输入来源和单位转换；不能用另一份输入的同名信号替代。|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。前四项为本次原history/context/运行bindings/plan|
|`source_scans`|tuple|是|无|位置或关键字。source_scans为全部     活且完成的ObservedSourceScan tuple，可乱序但须唯一覆盖原计划来源。|

#### 返回说明

可按真实依赖借读预建ObservationScope的owner。

#### 异常说明

类型、身份、投影、同步元数据、实际历史或预算原错；持续清理失败从
    historical_observation_scopes_cleanup_owner恢复close。

源码：[`src/chronaxis/execution/historical_observation.py:94`](../../../src/chronaxis/execution/historical_observation.py#L94)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-_clock_key"></a>
### `HistoricalObservationScopes._clock_key`

返回完整可比组键。

```python
HistoricalObservationScopes._clock_key(clock, *, dataset=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`clock`|TimebaseSpec|是|无|位置或关键字。TimebaseSpec/数据集时钟标识，用于比较是否共享同一时间基准。|
|`dataset`|TimebaseSpec|否|False|仅关键字。原TimebaseSpec/dataset标记。|

#### 返回说明

tuple。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/historical_observation.py:162`](../../../src/chronaxis/execution/historical_observation.py#L162)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-_require_contract"></a>
### `HistoricalObservationScopes._require_contract`

核原会话、domain、声明绑定及来源集合。

```python
HistoricalObservationScopes._require_contract()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

契约不一致。

本函数直接报告的具体错误：

- `ValueError`：范围须保原计划绑定、会话及请求domain。
- `ValueError`：范围计划、历史、绑定及上下文来源须完全对应。

源码：[`src/chronaxis/execution/historical_observation.py:171`](../../../src/chronaxis/execution/historical_observation.py#L171)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-_validate_source"></a>
### `HistoricalObservationScopes._validate_source`

逐项核真实扫描、当前元数据与绑定，不访问原输入行。

```python
HistoricalObservationScopes._validate_source(source, scan)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|SourcePlan|是|无|位置或关键字。原SourcePlan声明，必须与同次真实扫描和绑定一致。|
|`scan`|SourcePlan|是|无|位置或关键字。原SourcePlan/对应真实scan。|

#### 返回说明

原观测、描述SHA、请求SHA、历史SHA、计数。

#### 异常说明

生命周期、对象身份、指纹、投影、计数或EOF矛盾。

本函数直接报告的具体错误：

- `ResultClosedError`：观测扫描已关闭、失败或尚未真实完成。
- `ValueError`：范围扫描必须保同一history、原SourcePlan和实际原request。
- `ValueError`：范围扫描、实际描述/请求/历史SHA/计数/投影/EOF事实不一致。

源码：[`src/chronaxis/execution/historical_observation.py:184`](../../../src/chronaxis/execution/historical_observation.py#L184)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-_verify_source"></a>
### `HistoricalObservationScopes._verify_source`

用一个真实reader核当前文件完整EOF，拒绝提前close冒充耗尽。

```python
HistoricalObservationScopes._verify_source(source, digest, counts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|位置或关键字。计划中来源的原始别名，用于定位历史文件及扫描记录。|
|`digest`|str|是|无|位置或关键字。本次扫描记录的内容摘要，用于与历史仓保存的摘要核对。|
|`counts`|tuple[int, int]|是|无|位置或关键字。依次为原进度记录数、原信号样本数；回读至文件末尾后逐项核对，提前关闭不能算作核对完成。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原读取、预算、损坏或关闭错误，reader责任保持可恢复。

本函数直接报告的具体错误：

- `ResultFormatError`：观测范围未完成当前实际历史EOF、摘要或计数核对。

源码：[`src/chronaxis/execution/historical_observation.py:223`](../../../src/chronaxis/execution/historical_observation.py#L223)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-_build_scopes"></a>
### `HistoricalObservationScopes._build_scopes`

按原计划来源序建立全部组及domain内交集。

```python
HistoricalObservationScopes._build_scopes()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原范围模型错误。

本函数直接报告的具体错误：

- `ValueError`：非空原时间行缺少已核实的观测首末端。

源码：[`src/chronaxis/execution/historical_observation.py:247`](../../../src/chronaxis/execution/historical_observation.py#L247)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-_adopt_cleanup"></a>
### `HistoricalObservationScopes._adopt_cleanup`

接管实际未返回的历史reader。

```python
HistoricalObservationScopes._adopt_cleanup(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/historical_observation.py:276`](../../../src/chronaxis/execution/historical_observation.py#L276)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-closed"></a>
### `HistoricalObservationScopes.closed`

读取自有关闭状态。

```python
HistoricalObservationScopes.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_observation.py:283`](../../../src/chronaxis/execution/historical_observation.py#L283)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-assert_current"></a>
### `HistoricalObservationScopes.assert_current`

核调用方仍使用原四对象、活扫描和同一当前历史元数据。

```python
HistoricalObservationScopes.assert_current(history, context, bindings, plan)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。本次分析保存的解码信号历史，必须已完成写入且尚未关闭；后续统计从这里读取，不重新解码输入文件。|
|`context`|[HoldContext](chronaxis.execution.hold.md#api-HoldContext)|是|无|位置或关键字。本会话的保持设置，含会话标识和时间范围；用它判断旧值可保持多久以及何时结束。|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)|是|无|位置或关键字。本次实际读取后建立的信号对应关系，包含输入来源和单位转换；不能用另一份输入的同名信号替代。|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。创建观测范围时使用的分析计划，检查后续查询没有换成另一个计划。|

#### 返回说明

None；不重复读取历史字节。

#### 异常说明

ResultClosedError为本层/扫描/历史失效，ValueError为对象或证明已改变。

本函数直接报告的具体错误：

- `ResultClosedError`：历史观测范围已关闭、正在清理或构造失败。
- `ValueError`：观测范围必须与调用方原history/context/bindings/plan共同使用。
- `ValueError`：观测范围所借扫描或当前历史证明已改变。

源码：[`src/chronaxis/execution/historical_observation.py:287`](../../../src/chronaxis/execution/historical_observation.py#L287)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-identity"></a>
### `HistoricalObservationScopes.identity`

借读包含实际原行/分组的稳定摘要。

```python
HistoricalObservationScopes.identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

str。

#### 异常说明

当前证明或活性失效。

源码：[`src/chronaxis/execution/historical_observation.py:307`](../../../src/chronaxis/execution/historical_observation.py#L307)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-source_observations"></a>
### `HistoricalObservationScopes.source_observations`

按原计划序借读有限分源事实副本。

```python
HistoricalObservationScopes.source_observations
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple。

#### 异常说明

当前证明或活性失效。

源码：[`src/chronaxis/execution/historical_observation.py:313`](../../../src/chronaxis/execution/historical_observation.py#L313)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-dataset_scope"></a>
### `HistoricalObservationScopes.dataset_scope`

借读无依赖的dataset时钟组。

```python
HistoricalObservationScopes.dataset_scope
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ObservationScope。

#### 异常说明

证明或活性失效。

源码：[`src/chronaxis/execution/historical_observation.py:319`](../../../src/chronaxis/execution/historical_observation.py#L319)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-for_dependencies"></a>
### `HistoricalObservationScopes.for_dependencies`

按展开后的原信号依赖借读预建范围，保留原同步及实际投影门槛。

```python
HistoricalObservationScopes.for_dependencies(names)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`names`|tuple[str, ...]|是|无|位置或关键字。表达式依赖的信号别名；空元组使用数据集所属的时钟组范围。|

#### 返回说明

借用到本owner关闭的ObservationScope，同组依赖返回同一预建对象。

#### 异常说明

原未知/未投影/同步错误；跨不可比较组或本层/扫描活性失效。

本函数直接报告的具体错误：

- `ValueError`：联合依赖不属于同一可比时钟组。

源码：[`src/chronaxis/execution/historical_observation.py:323`](../../../src/chronaxis/execution/historical_observation.py#L323)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-for_source"></a>
### `HistoricalObservationScopes.for_source`

借读实际来源所属的已核时钟组，空信号投影也必须有同次来源证明。

```python
HistoricalObservationScopes.for_source(name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name为本次原来源安全名。|

#### 返回说明

借用ObservationScope，范围为所属组联合，
    不是该来源独占的观测首末。

#### 异常说明

原证明失效或ValueError为未知/非文本来源。

本函数直接报告的具体错误：

- `ValueError`：未知观测来源或来源名称类型错误。

源码：[`src/chronaxis/execution/historical_observation.py:342`](../../../src/chronaxis/execution/historical_observation.py#L342)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalObservationScopes-close"></a>
### `HistoricalObservationScopes.close`

可重试关闭自有reader与有限副本，不关闭任何原扫描/history/lease。

```python
HistoricalObservationScopes.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

原reader或预算取消，未完责任保留。

源码：[`src/chronaxis/execution/historical_observation.py:354`](../../../src/chronaxis/execution/historical_observation.py#L354)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
