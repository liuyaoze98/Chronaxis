# chronaxis.execution.raw_signal_groups

把三格式共用的已解码更新交给实时完整同一时刻组消费者，不写历史文件。

只归一化当前声明需要的字段；同一时刻组跨读取批/连续文件保持，看到下一个相关
时间后才交付上一组，EOF显式finish交付末组。每条待交付样本预付有限预算，
大同一时刻组超预算明确失败。跨来源调用方必须先按实际时间合并；本组件不重排
原文件、不解码DBC、不查询完整性证明，不把单个来源EOF当整个会话EOF。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)、[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`RawSignalGroups`](#api-RawSignalGroups)|保存当前同一时刻的必要更新；组交付后立即释放，消费方另行承担最新值状态。|
|[`RawSignalGroups.__init__`](#api-RawSignalGroups-__init__)|建立所需帧/信号索引和固定来源引用，不打开原始文件。|
|[`RawSignalGroups._require_open`](#api-RawSignalGroups-_require_open)|拒绝失败/关闭后的输入。|
|[`RawSignalGroups.configure_metadata`](#api-RawSignalGroups-configure_metadata)|借用同次DBC候选识别纯时钟字段，不解码或读取额外记录。|
|[`RawSignalGroups.consume`](#api-RawSignalGroups-consume)|接收一条已投影更新，仅所需帧参与时间检查与同一时刻归组。|
|[`RawSignalGroups._flush`](#api-RawSignalGroups-_flush)|同步借出完整组后释放本组，不保输出副本。|
|[`RawSignalGroups.finish`](#api-RawSignalGroups-finish)|所有输入EOF并成功关闭后交付末组，不创建末尾周期。|
|[`RawSignalGroups.close`](#api-RawSignalGroups-close)|仅退自有费用，不替调用方完成剩余组。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.models import SourceRef
from ..legacy.updates import LegacyDecodedUpdate
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from ..sources.packing import pack_message_values
from .groups import DecodedTimeGroup
from .history import _metadata_bytes
from .record_sample import RecordSample
from .calculation_values import scalar_from_column
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-RawSignalGroups"></a>
## `RawSignalGroups`

保存当前同一时刻的必要更新；组交付后立即释放，消费方另行承担最新值状态。

```python
RawSignalGroups(budget, definitions, session_id, consumer, *, backend='numpy', clock_only=())
```


源码：[`src/chronaxis/execution/raw_signal_groups.py:23`](../../../src/chronaxis/execution/raw_signal_groups.py#L23)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawSignalGroups-__init__"></a>
### `RawSignalGroups.__init__`

建立所需帧/信号索引和固定来源引用，不打开原始文件。

```python
RawSignalGroups.__init__(budget, definitions, session_id, consumer, *, backend='numpy', clock_only=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`definitions`|Mapping[str, SignalDefinition]|是|无|位置或关键字。以信号别名为键的定义，提供来源、类型、单位和有效期；不会在这里重新加载DBC。|
|`session_id`|str|是|无|位置或关键字。本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`consumer`|Callable[[[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)], None]|是|无|位置或关键字。同步接收一个完整同一时刻信号组；消费者保留组时须自行承担其内存费用。|
|`backend`|str|否|'numpy'|仅关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`clock_only`|tuple[str, ...]|否|()|仅关键字。仅作为时间驱动的信号别名集合；保留真实更新时刻，不解析或构造该信号的数值样本。|

#### 返回说明

owner。

#### 异常说明

配置、预算或取消；构造恢复句柄raw_groups_cleanup_owner。

源码：[`src/chronaxis/execution/raw_signal_groups.py:26`](../../../src/chronaxis/execution/raw_signal_groups.py#L26)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawSignalGroups-_require_open"></a>
### `RawSignalGroups._require_open`

拒绝失败/关闭后的输入。

```python
RawSignalGroups._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/raw_signal_groups.py:72`](../../../src/chronaxis/execution/raw_signal_groups.py#L72)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawSignalGroups-configure_metadata"></a>
### `RawSignalGroups.configure_metadata`

借用同次DBC候选识别纯时钟字段，不解码或读取额外记录。

```python
RawSignalGroups.configure_metadata(facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|Sequence[Mapping[str, object]]|是|无|位置或关键字。本次已加载DBC字段事实；每项含locator，存在dbc_frames时用于识别只推动时间的字段，不触发解码或额外读取。|

#### 返回说明

None。

#### 异常说明

定位结构错误。

#### 副作用说明

仅保存当前纯时钟字段的有限候选，费用包含在定义固定预算中。

源码：[`src/chronaxis/execution/raw_signal_groups.py:77`](../../../src/chronaxis/execution/raw_signal_groups.py#L77)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawSignalGroups-consume"></a>
### `RawSignalGroups.consume`

接收一条已投影更新，仅所需帧参与时间检查与同一时刻归组。

```python
RawSignalGroups.consume(update)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|位置或关键字。当前一条所需报文更新，保留原输入序号、所需字段和有效状态；同一时刻不同报文仍分别处理。|

#### 返回说明

None。

#### 异常说明

身份/时间回退、预算、归一化或消费者错误；失败后禁止finish。

源码：[`src/chronaxis/execution/raw_signal_groups.py:92`](../../../src/chronaxis/execution/raw_signal_groups.py#L92)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawSignalGroups-_flush"></a>
### `RawSignalGroups._flush`

同步借出完整组后释放本组，不保输出副本。

```python
RawSignalGroups._flush()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

消费/清理错误。

源码：[`src/chronaxis/execution/raw_signal_groups.py:156`](../../../src/chronaxis/execution/raw_signal_groups.py#L156)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawSignalGroups-finish"></a>
### `RawSignalGroups.finish`

所有输入EOF并成功关闭后交付末组，不创建末尾周期。

```python
RawSignalGroups.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

消费/清理错误。

源码：[`src/chronaxis/execution/raw_signal_groups.py:169`](../../../src/chronaxis/execution/raw_signal_groups.py#L169)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawSignalGroups-close"></a>
### `RawSignalGroups.close`

仅退自有费用，不替调用方完成剩余组。

```python
RawSignalGroups.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

释放失败可重试。

源码：[`src/chronaxis/execution/raw_signal_groups.py:181`](../../../src/chronaxis/execution/raw_signal_groups.py#L181)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
