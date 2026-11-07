# `chronaxis.execution.record_alarm_duration`

仅在请求报警累计时，按实际有效区间折算所选周期。

状态变化可能发生在两个驱动报文之间，例如温度在中途过期。每对报文只保
实际已知/报警长度，收到右端后按该对完整跨度折算，不保存逐点轨迹。没有
右端的末段不补固定周期；实际模式则累计已经确认存在的连续观测区间。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[NumpyIntegralSum](chronaxis.core.integral_sum_numpy.md#api-NumpyIntegralSum)、[ReferenceIntegralSum](chronaxis.core.integral_sum_reference.md#api-ReferenceIntegralSum)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[T](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`RecordAlarmDuration`](#api-RecordAlarmDuration)|拥有一个待完成记录对和有限求和状态，不读取来源或构造明细。|
|[`RecordAlarmDuration.__init__`](#api-RecordAlarmDuration-__init__)|预付统计费用。|
|[`RecordAlarmDuration.consume`](#api-RecordAlarmDuration-consume)|先结算前态，再记当前态；中途未知只裁剪本对有效部分。|
|[`RecordAlarmDuration.driver`](#api-RecordAlarmDuration-driver)|接收原始驱动端点，包括请求域两侧用于比例的点。|
|[`RecordAlarmDuration.finish`](#api-RecordAlarmDuration-finish)|返回单一秒数及完整性；不结算没有右端的周期。|
|[`RecordAlarmDuration.closed`](#api-RecordAlarmDuration-closed)|返回关闭状态。|
|[`RecordAlarmDuration.close`](#api-RecordAlarmDuration-close)|丢弃统计状态并归还自己的费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.types import Truth as T
from ..core.integral_sum_reference import ReferenceIntegralSum
from ..core.integral_sum_numpy import NumpyIntegralSum
from ..results.errors import ResultClosedError, AnalysisError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
```

</details>

<a id="api-RecordAlarmDuration"></a>
## `RecordAlarmDuration`

拥有一个待完成记录对和有限求和状态，不读取来源或构造明细。

```python
RecordAlarmDuration(budget, step_ns, backend, window)
```


源码：[`src/chronaxis/execution/record_alarm_duration.py:15`](../../../src/chronaxis/execution/record_alarm_duration.py#L15)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordAlarmDuration-__init__"></a>
### `RecordAlarmDuration.__init__`

预付统计费用。

```python
RecordAlarmDuration.__init__(budget, step_ns, backend, window)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`step_ns`|int &#124; None|是|无|位置或关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`backend`|str|是|无|位置或关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`window`|Interval|是|无|位置或关键字。当前要计算的实际半开时间范围，起点计入、终点不增加新区间。|

#### 返回说明

owner。

#### 异常说明

构造原错附owner。

源码：[`src/chronaxis/execution/record_alarm_duration.py:18`](../../../src/chronaxis/execution/record_alarm_duration.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordAlarmDuration-consume"></a>
### `RecordAlarmDuration.consume`

先结算前态，再记当前态；中途未知只裁剪本对有效部分。

```python
RecordAlarmDuration.consume(time_ns, state, driver=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|
|`state`|Truth|是|无|位置或关键字。当前报警条件的TRUE、FALSE或UNKNOWN状态；UNKNOWN不累计为已知报警时长。|
|`driver`|bool|否|False|位置或关键字。当前点是否由所选驱动真实更新产生；只有True且已有前序驱动才增加周期。|

#### 返回说明

None。

#### 异常说明

顺序/数值/关闭错误。

源码：[`src/chronaxis/execution/record_alarm_duration.py:39`](../../../src/chronaxis/execution/record_alarm_duration.py#L39)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordAlarmDuration-driver"></a>
### `RecordAlarmDuration.driver`

接收原始驱动端点，包括请求域两侧用于比例的点。

```python
RecordAlarmDuration.driver(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

None。

#### 异常说明

顺序错误。

源码：[`src/chronaxis/execution/record_alarm_duration.py:78`](../../../src/chronaxis/execution/record_alarm_duration.py#L78)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordAlarmDuration-finish"></a>
### `RecordAlarmDuration.finish`

返回单一秒数及完整性；不结算没有右端的周期。

```python
RecordAlarmDuration.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

(可核实报警秒数或None,状态)。

#### 异常说明

求和失败/关闭错误。

源码：[`src/chronaxis/execution/record_alarm_duration.py:84`](../../../src/chronaxis/execution/record_alarm_duration.py#L84)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordAlarmDuration-closed"></a>
### `RecordAlarmDuration.closed`

返回关闭状态。

```python
RecordAlarmDuration.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_alarm_duration.py:104`](../../../src/chronaxis/execution/record_alarm_duration.py#L104)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordAlarmDuration-close"></a>
### `RecordAlarmDuration.close`

丢弃统计状态并归还自己的费用。

```python
RecordAlarmDuration.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

释放原错可重试。

源码：[`src/chronaxis/execution/record_alarm_duration.py:108`](../../../src/chronaxis/execution/record_alarm_duration.py#L108)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
