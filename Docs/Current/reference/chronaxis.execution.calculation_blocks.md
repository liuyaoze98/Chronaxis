# chronaxis.execution.calculation_blocks

把一个有限窗口的历史回读装成有预算的指标输入块。

输入为封存的新解码历史、原保持上下文、实际绑定、表达式及CalculationDefinition。
支持无选择条件的时间与样本口径输入；每块最多batch_intervals个正区间。
每块的CalculationSeries可交给既有独立参考或NumPy指标核；本模块不归约整个窗口。
相邻块共享边界点，但半开区间不重叠；终点点值不增加面积或样本。
NumPy表达式仍执行原数组核，装箱循环只恢复冻结数值、质量和完整来源定位。
构造和本块空间先申请，至多保留一个回读前瞻帧；不保存完整轴或块列表。
输出块各自拥有预算，close可重试；借用历史、原state和lease不由本对象关闭。
失败后禁止推进，旧块仍独立可读。文件读取只由新历史回读执行，不读取旧报文。
可显式给出原context.domain内已核实的observation，仅裁剪计算实际域，不修改原
context、绑定或请求。默认None兼容原domain及原预算，本身不证明实际观测范围。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[D](chronaxis.core.types.md#api-SignalDType)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[HistoricalWindowReplay](chronaxis.execution.window_replay.md#api-HistoricalWindowReplay)、[HoldContext](chronaxis.execution.hold.md#api-HoldContext)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[_BatchRegistry](chronaxis.execution.temporal_buffer.md#api-_BatchRegistry)

## 对象导航

|对象|用途|
|---|---|
|[`_calculation_observation`](#api-_calculation_observation)|解析计算观测范围，只返回已有Interval引用，不改保持上下文或输入身份。|
|[`CalculationBlock`](#api-CalculationBlock)|持有独立的创建后不可修改的输入对象列及本块预算，不依赖后续回读状态。|
|[`CalculationBlock.__init__`](#api-CalculationBlock-__init__)|接收已申请空间内的不可修改的数据列，登记由创建者完成。|
|[`CalculationBlock.closed`](#api-CalculationBlock-closed)|查看当前对象是否已经关闭。|
|[`CalculationBlock.series`](#api-CalculationBlock-series)|读取有限指标列。|
|[`CalculationBlock._discard`](#api-CalculationBlock-_discard)|脱链并丢引用，不重复扣账。|
|[`CalculationBlock.close`](#api-CalculationBlock-close)|区分真实扣账前后取消，释放一次且支持重试。|
|[`HistoricalCalculationBlocks`](#api-HistoricalCalculationBlocks)|只保留一个共享边界帧，逐块交付当前窗口的指标输入。|
|[`HistoricalCalculationBlocks.__init__`](#api-HistoricalCalculationBlocks-__init__)|校验分块计算能力、预留固定空间，再创建自有回读者。|
|[`HistoricalCalculationBlocks.closed`](#api-HistoricalCalculationBlocks-closed)|查看本对象负责的资源是否已经全部关闭。|
|[`HistoricalCalculationBlocks.failed`](#api-HistoricalCalculationBlocks-failed)|读取推进失败标志。|
|[`HistoricalCalculationBlocks.__iter__`](#api-HistoricalCalculationBlocks-__iter__)|返回本分块者。|
|[`HistoricalCalculationBlocks._capture`](#api-HistoricalCalculationBlocks-_capture)|在已预留块空间中恢复一行，不承担数值计算。|
|[`HistoricalCalculationBlocks.__next__`](#api-HistoricalCalculationBlocks-__next__)|先申请当前块所需内存，再读取规定数量的时间段及末端边界；下一块会复用这个边界。|
|[`HistoricalCalculationBlocks._release_unpublished`](#api-HistoricalCalculationBlocks-_release_unpublished)|关闭未交付输出或抵销尚无输出持有的申请，真实释放后清字段。|
|[`HistoricalCalculationBlocks.close`](#api-HistoricalCalculationBlocks-close)|关闭自有块及回读者，真实释放后才记录closed。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationSeries, CalculationDefinition
from ..core.calculations_memory_reference import require_calculation_plan
from ..core.models import Interval
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q, SignalDType as D
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .temporal_buffer import _BatchRegistry
from .window_replay import HistoricalWindowReplay
```

</details>

<a id="api-_calculation_observation"></a>
## `_calculation_observation`

解析计算观测范围，只返回已有Interval引用，不改保持上下文或输入身份。

```python
_calculation_observation(context, observation)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|[HoldContext](chronaxis.execution.hold.md#api-HoldContext)|是|无|位置或关键字。本会话的保持设置，含会话标识和时间范围；用它判断旧值可保持多久以及何时结束。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|位置或关键字。本次计算实际有数据的时间范围，用Interval给出，并且必须位于context.domain内。传None时沿用context.domain；函数不会读取文件来推算范围，因此调用方应传入已经核实的范围。|

### 返回说明

显式Interval，None时返回原context.domain；实际观测证明由调用方提供。

### 异常说明

TypeError为非带有明确类型的上下文/范围；ValueError为显式范围越出原domain。

本函数直接报告的具体错误：

- `TypeError`：指标观测范围需原HoldContext。
- `TypeError`：显式指标observation需Interval。
- `ValueError`：指标observation必须位于原context.domain内。

源码：[`src/chronaxis/execution/calculation_blocks.py:30`](../../../src/chronaxis/execution/calculation_blocks.py#L30)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CalculationBlock"></a>
## `CalculationBlock`

持有独立的创建后不可修改的输入对象列及本块预算，不依赖后续回读状态。

series只有有限行；外部提前保存series引用后的存活量由外部负责。
双向登记指针随本块申请计账，关闭过程中拒绝读取半关闭输出。

```python
CalculationBlock(owner, cost, series)
```


源码：[`src/chronaxis/execution/calculation_blocks.py:49`](../../../src/chronaxis/execution/calculation_blocks.py#L49)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CalculationBlock-__init__"></a>
### `CalculationBlock.__init__`

接收已申请空间内的不可修改的数据列，登记由创建者完成。

```python
CalculationBlock.__init__(owner, cost, series)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[HistoricalCalculationBlocks](chronaxis.execution.calculation_blocks.md#api-HistoricalCalculationBlocks)|是|无|位置或关键字。创建本指标块的读取器，负责登记、关闭和归还块占用的资源。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。series为CalculationSeries。|

#### 返回说明

新块。

#### 异常说明

分配失败由外层收回本次申请。

源码：[`src/chronaxis/execution/calculation_blocks.py:56`](../../../src/chronaxis/execution/calculation_blocks.py#L56)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CalculationBlock-closed"></a>
### `CalculationBlock.closed`

查看当前对象是否已经关闭。

```python
CalculationBlock.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/calculation_blocks.py:68`](../../../src/chronaxis/execution/calculation_blocks.py#L68)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CalculationBlock-series"></a>
### `CalculationBlock.series`

读取有限指标列。

```python
CalculationBlock.series
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

CalculationSeries。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：指标输入块已关闭或正在关闭。

源码：[`src/chronaxis/execution/calculation_blocks.py:73`](../../../src/chronaxis/execution/calculation_blocks.py#L73)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CalculationBlock-_discard"></a>
### `CalculationBlock._discard`

脱链并丢引用，不重复扣账。

```python
CalculationBlock._discard()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

脱链失败传播，finally仍保存真实关闭事实。

源码：[`src/chronaxis/execution/calculation_blocks.py:80`](../../../src/chronaxis/execution/calculation_blocks.py#L80)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CalculationBlock-close"></a>
### `CalculationBlock.close`

区分真实扣账前后取消，释放一次且支持重试。

```python
CalculationBlock.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

账本/取消原样传播。

源码：[`src/chronaxis/execution/calculation_blocks.py:91`](../../../src/chronaxis/execution/calculation_blocks.py#L91)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks"></a>
## `HistoricalCalculationBlocks`

只保留一个共享边界帧，逐块交付当前窗口的指标输入。

_pending归自有回读者持有，其成本由原回读帧申请覆盖；不重复提交时间组。
每块重新复制有限不可修改的数据列，旧块不会随下一块变化，主动留存须close归还预算。
无观测交集输出空迭代；零长度交集只输出一个点块，不能推断正常积分零。

```python
HistoricalCalculationBlocks(history, context, bindings, compiled, spec, *, backend='numpy', batch_intervals=64, observation=None)
```


源码：[`src/chronaxis/execution/calculation_blocks.py:110`](../../../src/chronaxis/execution/calculation_blocks.py#L110)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks-__init__"></a>
### `HistoricalCalculationBlocks.__init__`

校验分块计算能力、预留固定空间，再创建自有回读者。

```python
HistoricalCalculationBlocks.__init__(history, context, bindings, compiled, spec, *, backend='numpy', batch_intervals=64, observation=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。本次分析保存的解码信号历史，必须已完成写入且尚未关闭；后续统计从这里读取，不重新解码输入文件。|
|`context`|[HoldContext](chronaxis.execution.hold.md#api-HoldContext)|是|无|位置或关键字。本会话的保持设置，含会话标识和时间范围；用它判断旧值可保持多久以及何时结束。|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)|是|无|位置或关键字。本次实际读取后建立的信号对应关系，包含输入来源和单位转换；不能用另一份输入的同名信号替代。|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。已经编译并绑定到本次输入的数值表达式，用它计算指标所需的值。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。当前指标的统计范围、算子、输出单位及数据不全时的处理设置；该对象的计算种类须符合本类用途。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`batch_intervals`|int|否|64|仅关键字。每次交付的正长度时间区间数量上限，须大于0；改变它只改变分批大小，不改变统计范围。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。本次计算实际有数据的时间范围，用Interval给出，并且必须位于context.domain内。传None时沿用context.domain；函数不会读取文件来推算范围，因此调用方应传入已经核实的范围。|

#### 返回说明

尚未读取历史的新分块者。

#### 异常说明

类型/能力/身份/预算或取消错误。
    原异常的calculation_blocks_cleanup_owner保留持续清理失败时的自有恢复句柄。

本函数直接报告的具体错误：

- `TypeError`：历史指标分块需要真实封存历史、上下文、绑定、表达式和CalculationDefinition。
- `ValueError`：指标分块需合法后端及正整数batch_intervals。
- `ValueError`：当前历史指标分块只支持已接线的时间、样本与select输入。
- `ValueError`：select历史输入必须保留原表达式单位。
- `ValueError`：指标表达式与当前实际绑定不同。

源码：[`src/chronaxis/execution/calculation_blocks.py:118`](../../../src/chronaxis/execution/calculation_blocks.py#L118)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks-closed"></a>
### `HistoricalCalculationBlocks.closed`

查看本对象负责的资源是否已经全部关闭。

```python
HistoricalCalculationBlocks.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/calculation_blocks.py:194`](../../../src/chronaxis/execution/calculation_blocks.py#L194)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks-failed"></a>
### `HistoricalCalculationBlocks.failed`

读取推进失败标志。

```python
HistoricalCalculationBlocks.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/calculation_blocks.py:199`](../../../src/chronaxis/execution/calculation_blocks.py#L199)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks-__iter__"></a>
### `HistoricalCalculationBlocks.__iter__`

返回本分块者。

```python
HistoricalCalculationBlocks.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/calculation_blocks.py:203`](../../../src/chronaxis/execution/calculation_blocks.py#L203)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks-_capture"></a>
### `HistoricalCalculationBlocks._capture`

在已预留块空间中恢复一行，不承担数值计算。

```python
HistoricalCalculationBlocks._capture(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|WindowReplayFrame|是|无|位置或关键字。历史回读产生的当前帧，包含点值、连续区间和来源信息。|

#### 返回说明

(ScalarValue, bool actual, Q诊断, SourceRef tuple)。

#### 异常说明

关闭/真实结构/装箱分配错误；数组输入形状(1,)，单位为原表达式单位。

#### 边界说明

valid ENUM物理整数码沿原labels映射回标签字符串；其他dtype及invalid不改口径。

源码：[`src/chronaxis/execution/calculation_blocks.py:207`](../../../src/chronaxis/execution/calculation_blocks.py#L207)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks-__next__"></a>
### `HistoricalCalculationBlocks.__next__`

先申请当前块所需内存，再读取规定数量的时间段及末端边界；下一块会复用这个边界。

```python
HistoricalCalculationBlocks.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

CalculationBlock，series最多batch_intervals+1行。

#### 异常说明

StopIteration为完成/无交集；推进错误标failed并保留旧块可读。

本函数直接报告的具体错误：

- `ResultClosedError`：历史指标分块已关闭、正在关闭或推进失败。

源码：[`src/chronaxis/execution/calculation_blocks.py:234`](../../../src/chronaxis/execution/calculation_blocks.py#L234)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks-_release_unpublished"></a>
### `HistoricalCalculationBlocks._release_unpublished`

关闭未交付输出或抵销尚无输出持有的申请，真实释放后清字段。

```python
HistoricalCalculationBlocks._release_unpublished()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，可重试。

#### 异常说明

子关闭/扣账/取消错误传播。

源码：[`src/chronaxis/execution/calculation_blocks.py:291`](../../../src/chronaxis/execution/calculation_blocks.py#L291)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalCalculationBlocks-close"></a>
### `HistoricalCalculationBlocks.close`

关闭自有块及回读者，真实释放后才记录closed。

```python
HistoricalCalculationBlocks.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，可重试。

#### 异常说明

子close/账本/取消错误传播。

源码：[`src/chronaxis/execution/calculation_blocks.py:311`](../../../src/chronaxis/execution/calculation_blocks.py#L311)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
