# chronaxis.execution.current_message_calculation

用三格式共用的消息计算一项逐报文累计，不建立消息历史或原帧副本。

输入是CAN读取进程投影后的有限LegacyDecodedUpdate批，公式使用本条值，不保持上一条。
复用既有归一化、参考/NumPy表达式、正负分桶及原序求和；period已经在公式
中时不再乘dt。结果是累计快照；来源是否完整读完由拥有读取器的调用方确认。
此组件由当前记录执行器调用，不创建旧绑定证明或额外核验扫描。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)、[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason)、[LegacySumAccumulator](chronaxis.legacy.sum.md#api-LegacySumAccumulator)、[LegacySumContribution](chronaxis.legacy.sum.md#api-LegacySumContribution)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`CurrentMessageCalculation`](#api-CurrentMessageCalculation)|持有一项公式与固定累计状态；输入批及明细回调都只在consume期间借用。|
|[`CurrentMessageCalculation.__init__`](#api-CurrentMessageCalculation-__init__)|先核有限声明，再预约公式和累计状态，不读输入或DBC。|
|[`CurrentMessageCalculation._require_open`](#api-CurrentMessageCalculation-_require_open)|阻止失败后继续交付结果。|
|[`CurrentMessageCalculation._matches`](#api-CurrentMessageCalculation-_matches)|核真实消息来源后选择本指标帧。|
|[`CurrentMessageCalculation.consume`](#api-CurrentMessageCalculation-consume)|按原序计算有限批；默认只累计，明细仅交给显式回调，不保存历史。|
|[`CurrentMessageCalculation.snapshot`](#api-CurrentMessageCalculation-snapshot)|读取当前累计，不冒充文件EOF。|
|[`CurrentMessageCalculation.quality`](#api-CurrentMessageCalculation-quality)|读取实际参与计算的质量汇总，不构造逐条诊断。|
|[`CurrentMessageCalculation.closed`](#api-CurrentMessageCalculation-closed)|读取释放完成状态。|
|[`CurrentMessageCalculation.close`](#api-CurrentMessageCalculation-close)|仅关闭自有累计与费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core import expression_reference, expression_numpy
from ..core.expression import validate_expression
from ..core.models import Interval
from ..core.numeric import to_float_reference
from ..core.numeric_numpy import to_float_numpy
from ..core.types import QualityFlag as Q
from ..legacy.sum import LegacySumAccumulator, LegacySumContribution, LegacySkipReason
from ..legacy.updates import LegacyDecodedUpdate
from ..planning.message_calculations import require_message_calculation
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from ..sources.packing import pack_message_values
from .calculation_values import scalar_from_column, direction_bucket_state, direction_skip_reason
from .history import _metadata_bytes
```

</details>

<a id="api-CurrentMessageCalculation"></a>
## `CurrentMessageCalculation`

持有一项公式与固定累计状态；输入批及明细回调都只在consume期间借用。

```python
CurrentMessageCalculation(calculation, sources, bindings, session_id, budget, *, backend='numpy', batch_rows=64, domain=None, contribution_consumer=None)
```


源码：[`src/chronaxis/execution/current_message_calculation.py:26`](../../../src/chronaxis/execution/current_message_calculation.py#L26)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CurrentMessageCalculation-__init__"></a>
### `CurrentMessageCalculation.__init__`

先核有限声明，再预约公式和累计状态，不读输入或DBC。

```python
CurrentMessageCalculation.__init__(calculation, sources, bindings, session_id, budget, *, backend='numpy', batch_rows=64, domain=None, contribution_consumer=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`calculation`|MessageCalculationPlan|是|无|位置或关键字。一个逐消息计算请求，包含匹配报文、公式、参数及充放电分桶条件。|
|`sources`|Sequence[SourcePlan]|是|无|位置或关键字。当前计划的来源定义，用于检查绑定来源类型及原始报文定位；不在此函数打开输入。|
|`bindings`|tuple[tuple[str, str], ...]|是|无|位置或关键字。每个所需别名及其实际原字段的对应关系，公共来源说明只保存一次。|
|`session_id`|str|是|无|位置或关键字。本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`backend`|str|否|'numpy'|仅关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`batch_rows`|int|否|64|仅关键字。每次交给计算器的最大目标记录数；限制临时数组大小，不是整文件记录数。|
|`domain`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。明确的实际统计范围，左闭右开；None表示不额外限制文件记录范围。|
|`contribution_consumer`|Callable[[[LegacySumContribution](chronaxis.legacy.sum.md#api-LegacySumContribution)], None] &#124; None|否|None|仅关键字。逐次贡献接收函数；None不构造或交付逐次贡献。|

#### 返回说明

新累计组件。

#### 异常说明

声明/预算/取消错误；失败构造携带可重试清理句柄。

源码：[`src/chronaxis/execution/current_message_calculation.py:29`](../../../src/chronaxis/execution/current_message_calculation.py#L29)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CurrentMessageCalculation-_require_open"></a>
### `CurrentMessageCalculation._require_open`

阻止失败后继续交付结果。

```python
CurrentMessageCalculation._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/current_message_calculation.py:89`](../../../src/chronaxis/execution/current_message_calculation.py#L89)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CurrentMessageCalculation-_matches"></a>
### `CurrentMessageCalculation._matches`

核真实消息来源后选择本指标帧。

```python
CurrentMessageCalculation._matches(update)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|位置或关键字。当前一条所需报文更新，保留原输入序号、所需字段和有效状态；同一时刻不同报文仍分别处理。|

#### 返回说明

bool。

#### 异常说明

类型/身份错。

源码：[`src/chronaxis/execution/current_message_calculation.py:94`](../../../src/chronaxis/execution/current_message_calculation.py#L94)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CurrentMessageCalculation-consume"></a>
### `CurrentMessageCalculation.consume`

按原序计算有限批；默认只累计，明细仅交给显式回调，不保存历史。

```python
CurrentMessageCalculation.consume(updates)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`updates`|Sequence[[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)]|是|无|位置或关键字。按原始顺序排列的一批所需报文更新；不会按时间去重。|

#### 返回说明

None。

#### 异常说明

输入/数值/预算/回调/取消错误原样传播；失败后只能close。

源码：[`src/chronaxis/execution/current_message_calculation.py:125`](../../../src/chronaxis/execution/current_message_calculation.py#L125)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CurrentMessageCalculation-snapshot"></a>
### `CurrentMessageCalculation.snapshot`

读取当前累计，不冒充文件EOF。

```python
CurrentMessageCalculation.snapshot()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

LegacySumSnapshot。

#### 异常说明

状态错。

源码：[`src/chronaxis/execution/current_message_calculation.py:198`](../../../src/chronaxis/execution/current_message_calculation.py#L198)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CurrentMessageCalculation-quality"></a>
### `CurrentMessageCalculation.quality`

读取实际参与计算的质量汇总，不构造逐条诊断。

```python
CurrentMessageCalculation.quality
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

QualityFlag。

#### 异常说明

状态错。

源码：[`src/chronaxis/execution/current_message_calculation.py:204`](../../../src/chronaxis/execution/current_message_calculation.py#L204)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CurrentMessageCalculation-closed"></a>
### `CurrentMessageCalculation.closed`

读取释放完成状态。

```python
CurrentMessageCalculation.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/current_message_calculation.py:210`](../../../src/chronaxis/execution/current_message_calculation.py#L210)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CurrentMessageCalculation-close"></a>
### `CurrentMessageCalculation.close`

仅关闭自有累计与费用。

```python
CurrentMessageCalculation.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

释放失败保留句柄供重试。

源码：[`src/chronaxis/execution/current_message_calculation.py:214`](../../../src/chronaxis/execution/current_message_calculation.py#L214)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
