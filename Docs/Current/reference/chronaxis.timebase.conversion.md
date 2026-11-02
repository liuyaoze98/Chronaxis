# chronaxis.timebase.conversion

把明确单位的时间数值或完整日期转换为整数纳秒，并保存转换诊断。

数值入口接收声明为s、ms、us或ns的整数、十进制文本、Decimal或已有float；
日期入口接收完整ISO日期。输出为int64纳秒及输入表示、舍入和时区信息。
换算通过十进制系数和指数完成，只在最终纳秒处舍入；恰好半值时取最近偶数，
不受Decimal全局精度影响，也不经过浮点UTC秒数。
日期中的明确时区偏移优先；无偏移时须传入tzinfo，重复或不存在的本地时刻
会被拒绝。已有浮点的上游精度无法恢复。单值最多4096位有效数字，极大指数
先判断溢出或舍零，不分配无界的10次幂。
参考加减先用Python整数计算再检查范围，独立于NumPy实现。本模块仅依赖
标准库，不读取文件、不使用机器默认时区，也不持有会话或日志状态。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`TimeOverflowError`](#api-TimeOverflowError)|时间坐标、偏移后坐标或非负跨度超出int64时拒绝运算。|
|[`TimeConversion`](#api-TimeConversion)|保存规范时间及来源精度，避免跨任务修改转换诊断。|
|[`require_int64_ns`](#api-require_int64_ns)|校验整数纳秒协议，明确拒绝布尔、浮点和越界。|
|[`_decimal_input`](#api-_decimal_input)|取得精确的输入表示，不受全局Decimal计算精度影响。|
|[`convert_time`](#api-convert_time)|按明确单位换算纳秒，并在最终结果处取最近偶数舍入。|
|[`parse_duration`](#api-parse_duration)|解析带单位的非负持续参数，允许显式零长度。|
|[`parse_datetime_ns`](#api-parse_datetime_ns)|将ISO完整日期转换为UTC整数纳秒，保留亚微秒分数。|
|[`checked_add_ns`](#api-checked_add_ns)|为一个纳秒坐标添加固定偏移，并检查结果是否仍在int64范围内。|
|[`shift_times_reference`](#api-shift_times_reference)|逐项独立计算固定偏移，作为数组内核的整数真值参考。|
|[`time_deltas_reference`](#api-time_deltas_reference)|计算非递减整数时间的相邻跨度，允许同时间不同样本。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, replace
from datetime import datetime, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from numbers import Integral
from typing import Sequence
```

</details>

<a id="api-TimeOverflowError"></a>
## `TimeOverflowError`

时间坐标、偏移后坐标或非负跨度超出int64时拒绝运算。

异常不携带可被误用的回绕结果；失败由调用者记录为任务校验错误。
本类型没有可变状态，不打开资源或把失败当正常零时长。

```python
class TimeOverflowError(OverflowError)
```

继承关系：OverflowError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/timebase/conversion.py:38`](../../../src/chronaxis/timebase/conversion.py#L38)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-TimeConversion"></a>
## `TimeConversion`

保存规范时间及来源精度，避免跨任务修改转换诊断。

time_ns经入口校验为int64；quantized表示实际纳秒舍入发生，浮点限制
与量化分别记录。input_text保留转换所见表示，不证明上游原始精度。
source_timezone仅记录日期采用的时区，不替代多源同步依据。

```python
TimeConversion(time_ns: int, input_representation: str, input_unit: str, input_text: str, quantized: bool, precision_limited: bool = False, rounding: str = 'round_half_even', source_timezone: str | None = None) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|核心坐标或时长，单位纳秒，有符号64位范围。|
|`input_representation`|str|是|无|integer/decimal_text/decimal/binary_float/ISO8601等实际来源。|
|`input_unit`|str|是|无|明确声明的s/ms/us/ns，日期入口使用ISO8601。|
|`input_text`|str|是|无|当前入口所见文本；不记录用户日志或假设更高源精度。|
|`quantized`|bool|是|无|原精确表示不能整纳秒表示时为True，包括舍为0。|
|`precision_limited`|bool|否|False|标记输入是否为已有二进制float：True表示不能恢复转为float之前的精度；1.0也为True，即使quantized=False。整数/十进制文本/Decimal为False；False不表示多个时钟已同步。|
|`rounding`|str|否|'round_half_even'|最终纳秒固定采用最近偶数舍入。|
|`source_timezone`|str &#124; None|否|None|日期实际采用的tzinfo说明，纯数值不猜。|

源码：[`src/chronaxis/timebase/conversion.py:47`](../../../src/chronaxis/timebase/conversion.py#L47)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-require_int64_ns"></a>
## `require_int64_ns`

校验整数纳秒协议，明确拒绝布尔、浮点和越界。

```python
require_int64_ns(value: int, field: str='time_ns') -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。时间整数，允许NumPy整数标量，不允许bool。|
|`field`|str|否|'time_ns'|位置或关键字。错误定位字段，默认time_ns。|

### 返回说明

int: 独立Python整数，保留原精确值。

### 异常说明

TypeError: 非整数或bool，不能靠隐式截断转换。
    TimeOverflowError: 超出有符号64位纳秒范围。

返回类型：int。

源码：[`src/chronaxis/timebase/conversion.py:65`](../../../src/chronaxis/timebase/conversion.py#L65)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_decimal_input"></a>
## `_decimal_input`

取得精确的输入表示，不受全局Decimal计算精度影响。

```python
_decimal_input(value: int | float | str | Decimal) -> tuple[Decimal, str, str]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; str &#124; Decimal|是|无|位置或关键字。整数、十进制文本、Decimal或当前已有的float。|

### 返回说明

tuple: 精确Decimal、表示类型、原入口文本。

### 异常说明

TypeError: 布尔或未支持的类型。
    ValueError: 空文本或非法文本、非有限值或超过4096位有效数字。

本函数直接报告的具体错误：

- `TypeError`：布尔值不能表示时间。
- `ValueError`：时间必须为有限数值。
- `ValueError`：时间超过4096位有效数字限制。
- `ValueError`：非法十进制时间文本。
- `TypeError`：时间仅接受整数、十进制文本、Decimal或float。

返回类型：tuple[Decimal, str, str]。

源码：[`src/chronaxis/timebase/conversion.py:91`](../../../src/chronaxis/timebase/conversion.py#L91)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-convert_time"></a>
## `convert_time`

按明确单位换算纳秒，并在最终结果处取最近偶数舍入。

```python
convert_time(value: int | float | str | Decimal, unit: str) -> TimeConversion
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; str &#124; Decimal|是|无|位置或关键字。有限整数、十进制文本、Decimal或已有float，允许负时间坐标。|
|`unit`|str|是|无|位置或关键字。大小写敏感的s、ms、us或ns；没有默认单位。|

### 返回说明

TimeConversion: 整数纳秒、输入表示与单位，以及是否发生纳秒舍入和
    是否受已有浮点精度限制的诊断。

### 异常说明

TypeError或ValueError: 输入类型、文本语法、有效数字长度或单位不合法。
    TimeOverflowError: 舍入后的结果超出int64范围。

### 处理流程说明

分离符号、系数和指数，在整数域缩放或求商余数，再舍入到整纳秒。
    极大正指数提前拒绝；极大负指数直接判定舍为0，避免无界分配。

### 副作用说明

无，不修改输入、Decimal上下文或时间基准。

返回类型：[TimeConversion](chronaxis.timebase.conversion.md#api-TimeConversion)。

源码：[`src/chronaxis/timebase/conversion.py:143`](../../../src/chronaxis/timebase/conversion.py#L143)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-parse_duration"></a>
## `parse_duration`

解析带单位的非负持续参数，允许显式零长度。

```python
parse_duration(text: str) -> TimeConversion
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。完整数值后缀，如500ms、3s、0ns。|

### 返回说明

TimeConversion: 纳秒持续时间，原带单位文本保留。

### 异常说明

TypeError: 非文本。
    ValueError: 缺单位、非法语法或原数值为负，即使负小值会舍为0。
    TimeOverflowError: 换算/舍入超int64。

返回类型：[TimeConversion](chronaxis.timebase.conversion.md#api-TimeConversion)。

源码：[`src/chronaxis/timebase/conversion.py:204`](../../../src/chronaxis/timebase/conversion.py#L204)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-parse_datetime_ns"></a>
## `parse_datetime_ns`

将ISO完整日期转换为UTC整数纳秒，保留亚微秒分数。

```python
parse_datetime_ns(text: str, source_timezone: tzinfo | None=None) -> TimeConversion
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。YYYY-MM-DDTHH:MM:SS[.fraction][Z/±HH:MM]，也允许空格分隔。|
|`source_timezone`|tzinfo &#124; None|否|None|位置或关键字。为没有时区偏移的日期指定时区对象；如from datetime import timezone后传timezone.utc，或timezone(timedelta(hours=8))。必须是tzinfo实例，不能传YAML用的字符串。日期已有偏移时以日期为准；None且日期无偏移会报错。|

### 返回说明

TimeConversion: UTC epoch纳秒、量化与实际采用时区，非机器默认。

### 异常说明

TypeError/ValueError: 文本/时区非法、naive缺时区、本地时刻模糊或不存在。
    TimeOverflowError: int64时间超界。
    OverflowError: 转到UTC时超出datetime历法边界。

### 副作用说明

无；不调用系统本地时区，不加载IANA名称或访问文件。

返回类型：[TimeConversion](chronaxis.timebase.conversion.md#api-TimeConversion)。

源码：[`src/chronaxis/timebase/conversion.py:236`](../../../src/chronaxis/timebase/conversion.py#L236)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-checked_add_ns"></a>
## `checked_add_ns`

为一个纳秒坐标添加固定偏移，并检查结果是否仍在int64范围内。

```python
checked_add_ns(time_ns: int, offset_ns: int) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。已满足int64范围的原时间坐标，单位为纳秒。|
|`offset_ns`|int|是|无|位置或关键字。已满足int64范围的固定偏移，单位为纳秒。|

### 返回说明

int: 精确的新坐标；成功相加不表示不同来源已经同步。

### 异常说明

TypeError: 任一输入不是非布尔整数。
    TimeOverflowError: 任一输入或相加结果超出int64范围。

返回类型：int。

源码：[`src/chronaxis/timebase/conversion.py:301`](../../../src/chronaxis/timebase/conversion.py#L301)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-shift_times_reference"></a>
## `shift_times_reference`

逐项独立计算固定偏移，作为数组内核的整数真值参考。

```python
shift_times_reference(times: Sequence[int], offset_ns: int) -> tuple[int, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|Sequence[int]|是|无|位置或关键字。已声明纳秒坐标，不要求排序。|
|`offset_ns`|int|是|无|位置或关键字。合法int64固定偏移。|

### 返回说明

tuple[int,...]: 新整数序列，空输入返回空tuple。

### 异常说明

TypeError/TimeOverflowError: 参数类型或任一坐标/结果超界。

### 副作用说明

无；不导入或调用NumPy实现，不修改输入。

返回类型：tuple[int, ...]。

源码：[`src/chronaxis/timebase/conversion.py:319`](../../../src/chronaxis/timebase/conversion.py#L319)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-time_deltas_reference"></a>
## `time_deltas_reference`

计算非递减整数时间的相邻跨度，允许同时间不同样本。

```python
time_deltas_reference(times: Sequence[int]) -> tuple[int, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|Sequence[int]|是|无|位置或关键字。来源顺序的int64纳秒，允许重复坐标。|

### 返回说明

tuple[int,...]: 长度max(N-1,0)的非负int64跨度。

### 异常说明

TypeError/ValueError: 非整数或来源内时间回退。
    TimeOverflowError: 输入或跨度超界，即使两端各自合法。

本函数直接报告的具体错误：

- `ValueError`：时间序列必须非递减。

### 副作用说明

无；Python整数参考不调用NumPy内核，也不排序或去重。

返回类型：tuple[int, ...]。

源码：[`src/chronaxis/timebase/conversion.py:338`](../../../src/chronaxis/timebase/conversion.py#L338)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
