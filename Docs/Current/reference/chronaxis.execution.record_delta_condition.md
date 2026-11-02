# chronaxis.execution.record_delta_condition

在当前窗口内保留必要数值片段，输出窗口变化量的三值条件。

实际模式在旧边界移出窗口时继续求值；固定/DBC只在选定驱动到达时移动窗口，
其他更新只处理失效。原实际坐标和TTL不改变，变化量仍交原独立两后端核计算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[DeltaSpan](chronaxis.core.window_delta.md#api-DeltaSpan)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[T](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`RecordDeltaCondition`](#api-RecordDeltaCondition)|拥有当前窗口片段和有限驱动时刻；不创建整段历史或对照时间轴。|
|[`RecordDeltaCondition.__init__`](#api-RecordDeltaCondition-__init__)|预付有限状态，动态窗口按实际容量收费。|
|[`RecordDeltaCondition._condition`](#api-RecordDeltaCondition-_condition)|转换既有数值核的三值结果，不把未知变False。|
|[`RecordDeltaCondition._append`](#api-RecordDeltaCondition-_append)|只保存值或质量真正变化的边界，查询末点临时构造。|
|[`RecordDeltaCondition._left`](#api-RecordDeltaCondition-_left)|只根据当前窗口需要的驱动记录确定左端。|
|[`RecordDeltaCondition.update`](#api-RecordDeltaCondition-update)|推进真实值和当前窗口，返回点/右侧条件；不输出变化值副本。|
|[`RecordDeltaCondition.closed`](#api-RecordDeltaCondition-closed)|返回资源关闭状态。|
|[`RecordDeltaCondition.close`](#api-RecordDeltaCondition-close)|释放有界片段与驱动记录，不写文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections import deque
from dataclasses import replace
from fractions import Fraction
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D, QualityFlag as Q, Truth as T
from ..core.window_delta import DeltaSpan
from ..core.window_delta_reference import window_delta_reference
from ..core.window_delta_numpy import window_delta_numpy
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
```

</details>

<a id="api-RecordDeltaCondition"></a>
## `RecordDeltaCondition`

拥有当前窗口片段和有限驱动时刻；不创建整段历史或对照时间轴。

```python
RecordDeltaCondition(budget, spec, dtype, backend, step_ns)
```


源码：[`src/chronaxis/execution/record_delta_condition.py:18`](../../../src/chronaxis/execution/record_delta_condition.py#L18)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDeltaCondition-__init__"></a>
### `RecordDeltaCondition.__init__`

预付有限状态，动态窗口按实际容量收费。

```python
RecordDeltaCondition.__init__(budget, spec, dtype, backend, step_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`spec`|WindowDeltaSpec|是|无|位置或关键字。窗口变化量声明，规定回看长度、首尾取值及变化阈值。|
|`dtype`|SignalDType|是|无|位置或关键字。计算值的数据类型；决定整数范围、浮点计算或枚举处理，不得隐式转float丢失整数精度。|
|`backend`|str|是|无|位置或关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`step_ns`|int &#124; None|是|无|位置或关键字。已经解析的正纳秒周期；None使用实际相邻记录时间差，不虚构末尾周期。|

#### 返回说明

owner。

#### 异常说明

原构造错。

源码：[`src/chronaxis/execution/record_delta_condition.py:21`](../../../src/chronaxis/execution/record_delta_condition.py#L21)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDeltaCondition-_condition"></a>
### `RecordDeltaCondition._condition`

转换既有数值核的三值结果，不把未知变False。

```python
RecordDeltaCondition._condition(result)
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|WindowDeltaResult|是|无|位置或关键字。窗口变化量内核结果；依据变化数值和有效状态形成当前条件。|

#### 返回说明

ScalarValue。

#### 异常说明

原类型错。

源码：[`src/chronaxis/execution/record_delta_condition.py:40`](../../../src/chronaxis/execution/record_delta_condition.py#L40)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDeltaCondition-_append"></a>
### `RecordDeltaCondition._append`

只保存值或质量真正变化的边界，查询末点临时构造。

```python
RecordDeltaCondition._append(time_ns, point, right)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|
|`point`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。当前表达式值及其类型、有效性和质量；无效值不会用0代替。|
|`right`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。当前右端条件值；用于窗口变化量的条件组合，不代表另一个实际时间轴。|

#### 返回说明

None。

#### 异常说明

预算/时间回退。

源码：[`src/chronaxis/execution/record_delta_condition.py:45`](../../../src/chronaxis/execution/record_delta_condition.py#L45)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDeltaCondition-_left"></a>
### `RecordDeltaCondition._left`

只根据当前窗口需要的驱动记录确定左端。

```python
RecordDeltaCondition._left(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

左端或不足时None。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_delta_condition.py:64`](../../../src/chronaxis/execution/record_delta_condition.py#L64)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDeltaCondition-update"></a>
### `RecordDeltaCondition.update`

推进真实值和当前窗口，返回点/右侧条件；不输出变化值副本。

```python
RecordDeltaCondition.update(time_ns, point, right, expires_at_ns, *, driver=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|
|`point`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。当前表达式值及其类型、有效性和质量；无效值不会用0代替。|
|`right`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。当前右端条件值；用于窗口变化量的条件组合，不代表另一个实际时间轴。|
|`expires_at_ns`|int &#124; None|是|无|位置或关键字。当前值按实际时间计算的有效截止纳秒时刻；None表示没有额外截止。|
|`driver`|bool|否|False|仅关键字。当前点是否来自所选驱动；False仅更新条件/失效边界，不增加固定周期。|

#### 返回说明

两个BOOL ScalarValue。

#### 异常说明

倒序、预算或原数值错误；失败只能清理。

源码：[`src/chronaxis/execution/record_delta_condition.py:78`](../../../src/chronaxis/execution/record_delta_condition.py#L78)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDeltaCondition-closed"></a>
### `RecordDeltaCondition.closed`

返回资源关闭状态。

```python
RecordDeltaCondition.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_delta_condition.py:155`](../../../src/chronaxis/execution/record_delta_condition.py#L155)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDeltaCondition-close"></a>
### `RecordDeltaCondition.close`

释放有界片段与驱动记录，不写文件。

```python
RecordDeltaCondition.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原预算关闭错，可重试。

源码：[`src/chronaxis/execution/record_delta_condition.py:159`](../../../src/chronaxis/execution/record_delta_condition.py#L159)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
