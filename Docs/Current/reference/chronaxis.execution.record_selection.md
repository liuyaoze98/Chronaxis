# chronaxis.execution.record_selection

把真实样本更新有界地交给原select核，并直接写最终选择表。

条件独自变化、TTL和裁剪边界不输出行。TRUE与UNKNOWN保持区别；只保存一批及
共享右端，没有完整选择历史或第二套算法。事件范围由必要历史提供相同协议。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[RecordPointBuffer](chronaxis.execution.record_point_buffer.md#api-RecordPointBuffer)

## 对象导航

|对象|用途|
|---|---|
|[`RecordSelection`](#api-RecordSelection)|拥有有限样本缓冲；结果行只在回调期间借用，不累计输出列表。|
|[`RecordSelection.__init__`](#api-RecordSelection-__init__)|预约必要缓冲。|
|[`RecordSelection._flush`](#api-RecordSelection-_flush)|消费当前正时段，留下右端供下一批。|
|[`RecordSelection.finish`](#api-RecordSelection-finish)|EOF后输出最后正范围，无末尾假样本。|
|[`RecordSelection.close`](#api-RecordSelection-close)|释放缓冲及回调，实际费用归零后关闭。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.calculations_reference import select_reference
from ..core.calculations_numpy import select_numpy
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .record_point_buffer import RecordPointBuffer
from .record_sample_series import sample_series
```

</details>

<a id="api-RecordSelection"></a>
## `RecordSelection`

拥有有限样本缓冲；结果行只在回调期间借用，不累计输出列表。

```python
RecordSelection(budget, spec, input_unit, dtype, step_ns, *, backend='numpy', batch_intervals=64, conditioned=False, consumer=None)
```

继承关系：[RecordPointBuffer](chronaxis.execution.record_point_buffer.md#api-RecordPointBuffer)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/record_selection.py:13`](../../../src/chronaxis/execution/record_selection.py#L13)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSelection-__init__"></a>
### `RecordSelection.__init__`

预约必要缓冲。

```python
RecordSelection.__init__(budget, spec, input_unit, dtype, step_ns, *, backend='numpy', batch_intervals=64, conditioned=False, consumer=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`spec`|CalculationDefinition|是|无|位置或关键字。已核对的指标声明，包含算子、实际请求范围、数据不全时的处理方式和输出单位。|
|`input_unit`|str|是|无|位置或关键字。送入数值核的原计算值单位，用于校验输出单位以及积分的单位转换。|
|`dtype`|SignalDType|是|无|位置或关键字。计算值的数据类型；决定整数范围、浮点计算或枚举处理，不得隐式转float丢失整数精度。|
|`step_ns`|int &#124; None|是|无|位置或关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`backend`|str|否|'numpy'|仅关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`batch_intervals`|int|否|64|仅关键字。本对象一次交给数值核的相邻区间上限；为正整数，并受共享内存预算约束。|
|`conditioned`|bool|否|False|仅关键字。是否同时保存和处理筛选条件；False时不创建无用条件列或条件历史。|
|`consumer`|Callable[[SelectionRow], None]|否|None|仅关键字。接收每条最终选择记录；没有被选中且不是未知的记录不会输出。|

#### 返回说明

owner。

#### 异常说明

配置或预算错。

源码：[`src/chronaxis/execution/record_selection.py:15`](../../../src/chronaxis/execution/record_selection.py#L15)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSelection-_flush"></a>
### `RecordSelection._flush`

消费当前正时段，留下右端供下一批。

```python
RecordSelection._flush()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

核或输出错误。

源码：[`src/chronaxis/execution/record_selection.py:34`](../../../src/chronaxis/execution/record_selection.py#L34)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSelection-finish"></a>
### `RecordSelection.finish`

EOF后输出最后正范围，无末尾假样本。

```python
RecordSelection.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原计算/写入错。

源码：[`src/chronaxis/execution/record_selection.py:51`](../../../src/chronaxis/execution/record_selection.py#L51)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSelection-close"></a>
### `RecordSelection.close`

释放缓冲及回调，实际费用归零后关闭。

```python
RecordSelection.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

预算释放错。

源码：[`src/chronaxis/execution/record_selection.py:56`](../../../src/chronaxis/execution/record_selection.py#L56)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
