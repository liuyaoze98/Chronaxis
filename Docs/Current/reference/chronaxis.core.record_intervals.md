# chronaxis.core.record_intervals

从相邻两次相关更新取得计算间隔，不创建另一套时间坐标。

调用者先按已解析的驱动选择相关更新，再逐条调用advance，包括值无效的更新。
首条只建立前序；actual取实际时间差，固定周期每次后续更新返回同一个间隔。
本模块不依赖CAN、DBC、文件边界或信号值，不保存消息历史、累计总数或输出证明。
DBC周期由接入层初始化核实后作为step_ns传入，不能在这里猜默认周期。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)

## 对象导航

|对象|用途|
|---|---|
|[`require_record_step`](#api-require_record_step)|核实记录对周期入口，禁止把合成边界当成驱动更新。|
|[`clipped_record_seconds`](#api-clipped_record_seconds)|按实际交集折算一对记录用于积分或加权的秒数，不生成时间坐标。|
|[`RecordIntervals`](#api-RecordIntervals)|一个消费者的一份前序状态，跨文件/批次复用，独立任务使用独立实例。|
|[`RecordIntervals.__init__`](#api-RecordIntervals-__init__)|创建相邻更新状态，不读取输入或分配历史容器。|
|[`RecordIntervals.advance`](#api-RecordIntervals-advance)|接收一条相关更新，返回此前一对记录的间隔。|
|[`RecordIntervals.advance_seconds`](#api-RecordIntervals-advance_seconds)|接收相关更新并返回裁剪后的计算秒数，只保同一份前序状态。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..timebase.conversion import require_int64_ns
from .models import Interval
```

</details>

<a id="api-require_record_step"></a>
## `require_record_step`

核实记录对周期入口，禁止把合成边界当成驱动更新。

```python
require_record_step(step_ns, actual_updates)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`step_ns`|int &#124; None|是|无|位置或关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`actual_updates`|tuple[bool, ...]|是|无|位置或关键字。逐点标明是否来自真实记录更新；周期计算不能把补入的失效或窗口边界当作新周期。|

### 返回说明

None。

### 异常说明

非法周期或非真实更新报错；不读取或保存记录。

源码：[`src/chronaxis/core/record_intervals.py:13`](../../../src/chronaxis/core/record_intervals.py#L13)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-clipped_record_seconds"></a>
## `clipped_record_seconds`

按实际交集折算一对记录用于积分或加权的秒数，不生成时间坐标。

```python
clipped_record_seconds(start_ns: int, end_ns: int, window: Interval, *, step_ns: int | None=None) -> float
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_ns`|int|是|无|位置或关键字。相关记录对左端的实际整数纳秒时刻；与窗口求交后确定本对的有效部分。|
|`end_ns`|int|是|无|位置或关键字。相关记录对右端的实际整数纳秒时刻；不能早于start_ns，等于时跨度为0。|
|`window`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。window为真实请求Interval|
|`step_ns`|int &#124; None|否|None|仅关键字。step_ns=None取实际差，正整数取固定或已核实DBC周期。|

### 返回说明

float秒数。固定模式使用step_ns×实际交集/实际跨度，最后才换为秒；
    不取整到纳秒，无交集或零跨度返回0。普通连续统计的同一时刻更新由上层按
    same_time_policy归组，零跨度不形成连续面积；旧逐消息N次累计不调用本函数。

### 异常说明

类型、int64边界、倒退或非法周期错误；无状态、I/O或持久化副作用。

返回类型：float。

源码：[`src/chronaxis/core/record_intervals.py:27`](../../../src/chronaxis/core/record_intervals.py#L27)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordIntervals"></a>
## `RecordIntervals`

一个消费者的一份前序状态，跨文件/批次复用，独立任务使用独立实例。

只保存必要的上一条实际时间及可选固定周期。即使选择固定周期，也用上一条
实际时间拒绝倒退；不将累计周期伪装为实际时间，不保留第二列时间。

```python
RecordIntervals(step_ns: int | None=None)
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`__slots__`|tuple[str, ...]|类成员，不作为构造参数填写|('_step_ns', '_previous_ns')|限定实例内部可保存的属性名；这些名称是实现布局，调用者不把它们作为配置填写。|

源码：[`src/chronaxis/core/record_intervals.py:58`](../../../src/chronaxis/core/record_intervals.py#L58)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordIntervals-__init__"></a>
### `RecordIntervals.__init__`

创建相邻更新状态，不读取输入或分配历史容器。

```python
RecordIntervals.__init__(step_ns: int | None=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`step_ns`|int &#124; None|否|None|位置或关键字。step_ns=None表示实际间隔|

#### 返回说明

新状态。

#### 异常说明

TypeError、ValueError或TimeOverflowError为非法周期。

源码：[`src/chronaxis/core/record_intervals.py:67`](../../../src/chronaxis/core/record_intervals.py#L67)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordIntervals-advance"></a>
### `RecordIntervals.advance`

接收一条相关更新，返回此前一对记录的间隔。

```python
RecordIntervals.advance(time_ns: int) -> int | None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。time_ns为当前记录实际整数纳秒，已按所需驱动筛选|

#### 返回说明

首条None，随后actual为非负实际差，固定周期为正step_ns。同一时刻记录不去重。

#### 异常说明

类型、int64溢出或时间倒退；失败前不修改前序状态。

#### 边界说明

不接收文件/EOF通知，不补尾段；既有actual期限、裁剪和TTL由消费者处理。

返回类型：int &#124; None。

源码：[`src/chronaxis/core/record_intervals.py:80`](../../../src/chronaxis/core/record_intervals.py#L80)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordIntervals-advance_seconds"></a>
### `RecordIntervals.advance_seconds`

接收相关更新并返回裁剪后的计算秒数，只保同一份前序状态。

```python
RecordIntervals.advance_seconds(time_ns: int, window: Interval) -> float | None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。time_ns为当前实际时间|
|`window`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。window为当前消费者实际请求范围。|

#### 返回说明

首条None，之后为交集折算秒数；窗口外更新仍推进前序，不能跳过。

#### 异常说明

时间、窗口或裁剪错误；失败不修改前序。无文件边界重置或EOF补周期。

返回类型：float &#124; None。

源码：[`src/chronaxis/core/record_intervals.py:101`](../../../src/chronaxis/core/record_intervals.py#L101)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
