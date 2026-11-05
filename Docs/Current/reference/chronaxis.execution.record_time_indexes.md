# `chronaxis.execution.record_time_indexes`

只为周期选窗/事件时长保存一份所需驱动时刻，按索引定位。

每条只写一个实际整数时间；偏移只在单次查询中按记录索引计算，不保存改写时间轴。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`RecordTimeIndexes`](#api-RecordTimeIndexes)|拥有各必要驱动的一份定长时间文件，所有消费者借用。|
|[`RecordTimeIndexes.__init__`](#api-RecordTimeIndexes-__init__)|预付有限索引状态。|
|[`RecordTimeIndexes.observe_group`](#api-RecordTimeIndexes-observe_group)|每驱动每实际同一时刻组只写一次。|
|[`RecordTimeIndexes.count`](#api-RecordTimeIndexes-count)|读取已写条数。|
|[`RecordTimeIndexes.last`](#api-RecordTimeIndexes-last)|读取已写末时刻。|
|[`RecordTimeIndexes.at`](#api-RecordTimeIndexes-at)|只读取一个时间整数。|
|[`RecordTimeIndexes.lower`](#api-RecordTimeIndexes-lower)|二分首个不早于time_ns的时刻。|
|[`RecordTimeIndexes.position`](#api-RecordTimeIndexes-position)|单次查询实际时刻位于哪对记录及其比例，不保存转换时间轴。|
|[`RecordTimeIndexes.shift`](#api-RecordTimeIndexes-shift)|按所选周期偏移记录位置，返回实际时刻及首尾裁剪标识。|
|[`RecordTimeIndexes.closed`](#api-RecordTimeIndexes-closed)|返回关闭状态。|
|[`RecordTimeIndexes.close`](#api-RecordTimeIndexes-close)|只关闭本次必要文件，失败可重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from struct import Struct
from tempfile import TemporaryFile
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
```

</details>

<a id="api-RecordTimeIndexes"></a>
## `RecordTimeIndexes`

拥有各必要驱动的一份定长时间文件，所有消费者借用。

```python
RecordTimeIndexes(budget, path, drivers)
```


源码：[`src/chronaxis/execution/record_time_indexes.py:12`](../../../src/chronaxis/execution/record_time_indexes.py#L12)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-__init__"></a>
### `RecordTimeIndexes.__init__`

预付有限索引状态。

```python
RecordTimeIndexes.__init__(budget, path, drivers)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`path`|str &#124; Path|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|
|`drivers`|Iterable[str]|是|无|位置或关键字。需要建立记录位置索引的驱动别名；无窗口或回看需求时不建立无用索引。|

#### 返回说明

owner。

#### 异常说明

原构造错。

源码：[`src/chronaxis/execution/record_time_indexes.py:15`](../../../src/chronaxis/execution/record_time_indexes.py#L15)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-observe_group"></a>
### `RecordTimeIndexes.observe_group`

每驱动每实际同一时刻组只写一次。

```python
RecordTimeIndexes.observe_group(group)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|DecodedTimeGroup|是|无|位置或关键字。同一实际时刻收齐的所需信号更新；本组全部到齐后再求值，避免来源遍历顺序影响结果。|

#### 返回说明

None。

#### 异常说明

顺序/IO/预算错误。

源码：[`src/chronaxis/execution/record_time_indexes.py:32`](../../../src/chronaxis/execution/record_time_indexes.py#L32)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-count"></a>
### `RecordTimeIndexes.count`

读取已写条数。

```python
RecordTimeIndexes.count(driver)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`driver`|str|是|无|位置或关键字。需要查询的原信号驱动别名，必须已在本索引登记。|

#### 返回说明

int。

#### 异常说明

未声明驱动。

源码：[`src/chronaxis/execution/record_time_indexes.py:52`](../../../src/chronaxis/execution/record_time_indexes.py#L52)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-last"></a>
### `RecordTimeIndexes.last`

读取已写末时刻。

```python
RecordTimeIndexes.last(driver)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`driver`|str|是|无|位置或关键字。需要查询的原信号驱动别名，必须已在本索引登记。|

#### 返回说明

int或None。

#### 异常说明

未声明驱动。

源码：[`src/chronaxis/execution/record_time_indexes.py:56`](../../../src/chronaxis/execution/record_time_indexes.py#L56)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-at"></a>
### `RecordTimeIndexes.at`

只读取一个时间整数。

```python
RecordTimeIndexes.at(driver, index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`driver`|str|是|无|位置或关键字。需要查询的原信号驱动别名，必须已在本索引登记。|
|`index`|int|是|无|位置或关键字。当前内部序列的记录索引；读取时检查范围，不把越界当作空输入。|

#### 返回说明

int。

#### 异常说明

越界/短读。

源码：[`src/chronaxis/execution/record_time_indexes.py:60`](../../../src/chronaxis/execution/record_time_indexes.py#L60)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-lower"></a>
### `RecordTimeIndexes.lower`

二分首个不早于time_ns的时刻。

```python
RecordTimeIndexes.lower(driver, time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`driver`|str|是|无|位置或关键字。需要查询的原信号驱动别名，必须已在本索引登记。|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

索引。

#### 异常说明

原读取错。

源码：[`src/chronaxis/execution/record_time_indexes.py:73`](../../../src/chronaxis/execution/record_time_indexes.py#L73)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-position"></a>
### `RecordTimeIndexes.position`

单次查询实际时刻位于哪对记录及其比例，不保存转换时间轴。

```python
RecordTimeIndexes.position(driver, time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`driver`|str|是|无|位置或关键字。需要查询的原信号驱动别名，必须已在本索引登记。|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

(Fraction记录位置,是否超出观测)。

#### 异常说明

空索引或读取错。

源码：[`src/chronaxis/execution/record_time_indexes.py:84`](../../../src/chronaxis/execution/record_time_indexes.py#L84)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-shift"></a>
### `RecordTimeIndexes.shift`

按所选周期偏移记录位置，返回实际时刻及首尾裁剪标识。

```python
RecordTimeIndexes.shift(driver, time_ns, offset_ns, step_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`driver`|str|是|无|位置或关键字。需要查询的原信号驱动别名，必须已在本索引登记。|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|
|`offset_ns`|int|是|无|位置或关键字。相对于事件锚点的有符号时长纳秒数；负数向前取记录，正数向后取记录。|
|`step_ns`|int &#124; None|是|无|位置或关键字。已经解析的正纳秒周期；None使用实际相邻记录时间差，不虚构末尾周期。|

#### 返回说明

(实际ns,是否裁剪)。
非整周期按原实际间隔比例定位，最终纳秒沿既有最近偶数舍入；不补观测之外的记录。

#### 异常说明

空索引/非法周期/实际读取错。

源码：[`src/chronaxis/execution/record_time_indexes.py:108`](../../../src/chronaxis/execution/record_time_indexes.py#L108)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-closed"></a>
### `RecordTimeIndexes.closed`

返回关闭状态。

```python
RecordTimeIndexes.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_time_indexes.py:131`](../../../src/chronaxis/execution/record_time_indexes.py#L131)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordTimeIndexes-close"></a>
### `RecordTimeIndexes.close`

只关闭本次必要文件，失败可重试。

```python
RecordTimeIndexes.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错。

源码：[`src/chronaxis/execution/record_time_indexes.py:135`](../../../src/chronaxis/execution/record_time_indexes.py#L135)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
