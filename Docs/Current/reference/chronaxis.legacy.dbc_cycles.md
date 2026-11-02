# chronaxis.legacy.dbc_cycles

核验明确请求的DBC报文周期，不读文件、不解码报文或生成逐条诊断。

周期取同次已加载DBC的message.cycle_time（毫秒），精确换算一次供运行状态复用。
缺失或非法周期直接拒绝，不用快速发送周期、信号周期或实际差作替代。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)

## 对象导航

|对象|用途|
|---|---|
|[`require_cycle_fields`](#api-require_cycle_fields)|核周期定位声明，不加载DBC。|
|[`cycle_time_ns`](#api-cycle_time_ns)|将DBC报文毫秒周期转为正整数纳秒，拒绝有损舍入。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from decimal import Decimal
from math import isfinite
from .records import LegacyCANField
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-require_cycle_fields"></a>
## `require_cycle_fields`

核周期定位声明，不加载DBC。

```python
require_cycle_fields(fields, channel=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fields`|Sequence[[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)]|是|无|位置或关键字。当前确实需要的CAN字段定位集合，包含通道、报文和信号身份。|
|`channel`|int|否|None|位置或关键字。明确的内部0基CAN通道，非负整数，不根据报文ID猜通道。配置从1开始，在进入此函数前完成转换。|

### 返回说明

原tuple。

### 异常说明

TypeError/ValueError为类型、数量、重复或通道不符。

源码：[`src/chronaxis/legacy/dbc_cycles.py:14`](../../../src/chronaxis/legacy/dbc_cycles.py#L14)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-cycle_time_ns"></a>
## `cycle_time_ns`

将DBC报文毫秒周期转为正整数纳秒，拒绝有损舍入。

```python
cycle_time_ns(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。DBC message.cycle_time给出的有限正毫秒数，只接受原生int/float；文本、bool、缺失或不能精确到纳秒时拒绝。|

### 返回说明

正int64纳秒。

### 异常说明

TypeError/ValueError/TimeOverflowError为缺失、类型、
    非正、非有限、不能精确到纳秒或越界；不为非法值选择默认周期。

源码：[`src/chronaxis/legacy/dbc_cycles.py:28`](../../../src/chronaxis/legacy/dbc_cycles.py#L28)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
