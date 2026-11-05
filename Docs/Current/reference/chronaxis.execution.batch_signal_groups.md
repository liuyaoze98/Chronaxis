# `chronaxis.execution.batch_signal_groups`

将已校验的解析信号批按watermark归为同一时刻组，不创建磁盘历史。

来源适配器负责原输入及跨批合同。本层只保尚未完整的组，最大时间组等到
后续时间或真实EOF才交付；超出预算直接失败，不拆散同一时刻更新。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`BatchSignalGroups`](#api-BatchSignalGroups)|借用已验证批，拥有未完成样本与有限排序状态。|
|[`BatchSignalGroups.__init__`](#api-BatchSignalGroups-__init__)|预付状态。|
|[`BatchSignalGroups.consume`](#api-BatchSignalGroups-consume)|保必要规范值，按完成进度交付组；丢弃原值/详细来源副本。|
|[`BatchSignalGroups._flush`](#api-BatchSignalGroups-_flush)|只交付完整组，费用在consumer返回后释放。|
|[`BatchSignalGroups.finish`](#api-BatchSignalGroups-finish)|调用方确认真实EOF及关闭后交最后组。|
|[`BatchSignalGroups.close`](#api-BatchSignalGroups-close)|丢待处理组并退款，不把提前close当EOF。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.models import SourceRef
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .groups import DecodedTimeGroup
from .record_sample import RecordSample
from ..core.types import SignalDType as D
from .calculation_values import scalar_from_column
from .history import _metadata_bytes
```

</details>

<a id="api-BatchSignalGroups"></a>
## `BatchSignalGroups`

借用已验证批，拥有未完成样本与有限排序状态。

```python
BatchSignalGroups(budget, definitions, session_id, consumer)
```


源码：[`src/chronaxis/execution/batch_signal_groups.py:18`](../../../src/chronaxis/execution/batch_signal_groups.py#L18)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BatchSignalGroups-__init__"></a>
### `BatchSignalGroups.__init__`

预付状态。

```python
BatchSignalGroups.__init__(budget, definitions, session_id, consumer)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`definitions`|Mapping[str, SignalDefinition]|是|无|位置或关键字。以信号别名为键的定义，提供来源、类型、单位和有效期；不会在这里重新加载DBC。|
|`session_id`|str|是|无|位置或关键字。本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`consumer`|Callable[[[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)], None]|是|无|位置或关键字。同步接收一个完整同一时刻信号组；消费者保留组时须自行承担其内存费用。|

#### 返回说明

owner。

#### 异常说明

预算/取消原错。

源码：[`src/chronaxis/execution/batch_signal_groups.py:21`](../../../src/chronaxis/execution/batch_signal_groups.py#L21)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BatchSignalGroups-consume"></a>
### `BatchSignalGroups.consume`

保必要规范值，按完成进度交付组；丢弃原值/详细来源副本。

```python
BatchSignalGroups.consume(batch)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|SignalBatch|是|无|位置或关键字。当前有限信号批；结束水位用于保证同一时刻更新作为一组交付。|

#### 返回说明

None。

#### 异常说明

预算/模型/回退，失败后只清理。

源码：[`src/chronaxis/execution/batch_signal_groups.py:38`](../../../src/chronaxis/execution/batch_signal_groups.py#L38)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BatchSignalGroups-_flush"></a>
### `BatchSignalGroups._flush`

只交付完整组，费用在consumer返回后释放。

```python
BatchSignalGroups._flush(watermark, *, keep_last)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`watermark`|int &#124; None|是|无|位置或关键字。本批之后不会再出现更早记录的纳秒边界；None表示没有额外水位。|
|`keep_last`|bool|是|无|仅关键字。是否暂留最后一个同一时刻组，等下一批确认没有同一时刻记录后再交付。|

#### 返回说明

None。

#### 异常说明

原错。

源码：[`src/chronaxis/execution/batch_signal_groups.py:68`](../../../src/chronaxis/execution/batch_signal_groups.py#L68)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BatchSignalGroups-finish"></a>
### `BatchSignalGroups.finish`

调用方确认真实EOF及关闭后交最后组。

```python
BatchSignalGroups.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

失败拒绝完成。

源码：[`src/chronaxis/execution/batch_signal_groups.py:101`](../../../src/chronaxis/execution/batch_signal_groups.py#L101)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BatchSignalGroups-close"></a>
### `BatchSignalGroups.close`

丢待处理组并退款，不把提前close当EOF。

```python
BatchSignalGroups.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

退款失败可重试。

源码：[`src/chronaxis/execution/batch_signal_groups.py:114`](../../../src/chronaxis/execution/batch_signal_groups.py#L114)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
