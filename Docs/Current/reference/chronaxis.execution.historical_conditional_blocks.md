# chronaxis.execution.historical_conditional_blocks

从已保存的信号历史中分别读取数值表达式和筛选条件，再把双方按时间对齐，逐块返回共同的指标输入。每块都有独立的内存占用记录，用完后需关闭。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationBlock](chronaxis.execution.calculation_blocks.md#api-CalculationBlock)、[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[HistoricalCalculationBlocks](chronaxis.execution.calculation_blocks.md#api-HistoricalCalculationBlocks)、[HoldContext](chronaxis.execution.hold.md#api-HoldContext)、[Interval](chronaxis.core.models.md#api-Interval)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[_BatchRegistry](chronaxis.execution.temporal_buffer.md#api-_BatchRegistry)

## 对象导航

|对象|用途|
|---|---|
|[`HistoricalConditionalBlocks`](#api-HistoricalConditionalBlocks)|持有两路有限输入与独立输出登记，按共同窗口单向推进。|
|[`HistoricalConditionalBlocks.__init__`](#api-HistoricalConditionalBlocks-__init__)|核对联合依赖，预约固定金额，再创建两路自有分块者。|
|[`HistoricalConditionalBlocks.closed`](#api-HistoricalConditionalBlocks-closed)|查看本对象负责的资源是否已经全部关闭。|
|[`HistoricalConditionalBlocks.failed`](#api-HistoricalConditionalBlocks-failed)|读取不可继续推进的失败标志。|
|[`HistoricalConditionalBlocks.__iter__`](#api-HistoricalConditionalBlocks-__iter__)|返回当前迭代器本身，继续使用当前读取位置。|
|[`HistoricalConditionalBlocks._reserve`](#api-HistoricalConditionalBlocks-_reserve)|即使预约返回途中取消，也及时记录真正取得的自有金额。|
|[`HistoricalConditionalBlocks._load`](#api-HistoricalConditionalBlocks-_load)|只在本路当前块到达游标时关闭并取得下一块。|
|[`HistoricalConditionalBlocks.__next__`](#api-HistoricalConditionalBlocks-__next__)|产生一个有独立预算的联合块，保留尚未交付的两路剩余区间。|
|[`HistoricalConditionalBlocks._release_unpublished`](#api-HistoricalConditionalBlocks-_release_unpublished)|关闭尚未返回给调用方的数据块，或归还其已经申请的内存额度；中途取消后可以重试。|
|[`HistoricalConditionalBlocks.close`](#api-HistoricalConditionalBlocks-close)|依次关闭自有输出、当前块、两回读者和固定金额，保留借用资源。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition
from ..core.calculations_memory_reference import require_calculation_plan
from ..core.calculation_series_join import join_calculation_series, _joint_times
from ..core.models import Interval
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import HistoricalCalculationBlocks, CalculationBlock, _calculation_observation
from .temporal_buffer import _BatchRegistry
```

</details>

<a id="api-HistoricalConditionalBlocks"></a>
## `HistoricalConditionalBlocks`

持有两路有限输入与独立输出登记，按共同窗口单向推进。

_cursor是尚未交付的半开区间左端；每路_current覆盖该点，过右端才换块。
点窗口只交付一次。已登记输出费用归各CalculationBlock，固定/未交付金额归父。
_failed或_closing后仅允许关闭，历史/原状态和绑定均由调用方管理。

```python
HistoricalConditionalBlocks(history, context, bindings, compiled, spec, condition, *, backend='numpy', batch_intervals=64, observation=None)
```


源码：[`src/chronaxis/execution/historical_conditional_blocks.py:33`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L33)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-__init__"></a>
### `HistoricalConditionalBlocks.__init__`

核对联合依赖，预约固定金额，再创建两路自有分块者。

```python
HistoricalConditionalBlocks.__init__(history, context, bindings, compiled, spec, condition, *, backend='numpy', batch_intervals=64, observation=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。本次分析保存的解码信号历史，必须已完成写入且尚未关闭；后续统计从这里读取，不重新解码输入文件。|
|`context`|[HoldContext](chronaxis.execution.hold.md#api-HoldContext)|是|无|位置或关键字。本会话的保持设置，含会话标识和时间范围；用它判断旧值可保持多久以及何时结束。|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)|是|无|位置或关键字。本次实际读取后建立的信号对应关系，包含输入来源和单位转换；不能用另一份输入的同名信号替代。|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。已经编译并绑定到本次输入的数值表达式，用它计算指标所需的值。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。当前指标的统计范围、算子、输出单位及数据不全时的处理设置；该对象的计算种类须符合本类用途。|
|`condition`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression) &#124; None|是|无|位置或关键字。额外筛选条件，结果必须是BOOL并使用同一组绑定；None表示不增加筛选条件。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`batch_intervals`|int|否|64|仅关键字。每次交付的正长度时间区间数量上限，须大于0；改变它只改变分批大小，不改变统计范围。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。本次计算实际有数据的时间范围，用Interval给出，并且必须位于context.domain内。传None时沿用context.domain；函数不会读取文件来推算范围，因此调用方应传入已经核实的范围。|

#### 返回说明

新有限联合owner。

#### 异常说明

类型/能力/同步/预算/取消错误原样传播；
    持续清理失败时原异常的conditional_blocks_cleanup_owner可再次close。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:41`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L41)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-closed"></a>
### `HistoricalConditionalBlocks.closed`

查看本对象负责的资源是否已经全部关闭。

```python
HistoricalConditionalBlocks.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:117`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L117)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-failed"></a>
### `HistoricalConditionalBlocks.failed`

读取不可继续推进的失败标志。

```python
HistoricalConditionalBlocks.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:122`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L122)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-__iter__"></a>
### `HistoricalConditionalBlocks.__iter__`

返回当前迭代器本身，继续使用当前读取位置。

```python
HistoricalConditionalBlocks.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:126`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L126)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-_reserve"></a>
### `HistoricalConditionalBlocks._reserve`

即使预约返回途中取消，也及时记录真正取得的自有金额。

```python
HistoricalConditionalBlocks._reserve(cost, *, fixed=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`fixed`|bool|否|False|仅关键字。fixed区分构造和当前未交付输出。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

超预算/取消原样传播，不靠发布后的总余额推断所有权。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:130`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L130)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-_load"></a>
### `HistoricalConditionalBlocks._load`

只在本路当前块到达游标时关闭并取得下一块。

```python
HistoricalConditionalBlocks._load(side)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`side`|int|是|无|位置或关键字。0读取主数值侧，1读取条件侧；两侧按时间边界合并后计算条件指标。|

#### 返回说明

覆盖游标的有限CalculationSeries。

#### 异常说明

回读/关闭失败，或输入提前结束/范围错位；不能将意外EOF当正常完成。

本函数直接报告的具体错误：

- `ValueError`：条件历史两路当前块没有覆盖同一实际游标。
- `ValueError`：条件历史输入在完整窗口交付前意外结束。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:147`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L147)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-__next__"></a>
### `HistoricalConditionalBlocks.__next__`

产生一个有独立预算的联合块，保留尚未交付的两路剩余区间。

```python
HistoricalConditionalBlocks.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

CalculationBlock，最多batch_intervals+1行。

#### 异常说明

StopIteration仅表示正常完整结束/无交集；其余失败后需要调用close关闭资源。

本函数直接报告的具体错误：

- `ResultClosedError`：条件历史分块已关闭、正在关闭或推进失败。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:170`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L170)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-_release_unpublished"></a>
### `HistoricalConditionalBlocks._release_unpublished`

关闭尚未返回给调用方的数据块，或归还其已经申请的内存额度；中途取消后可以重试。

```python
HistoricalConditionalBlocks._release_unpublished()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

块关闭/扣账/取消错误原样传播。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:212`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L212)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalConditionalBlocks-close"></a>
### `HistoricalConditionalBlocks.close`

依次关闭自有输出、当前块、两回读者和固定金额，保留借用资源。

```python
HistoricalConditionalBlocks.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复关闭安全。

#### 异常说明

关闭/释放取消可重试。

源码：[`src/chronaxis/execution/historical_conditional_blocks.py:230`](../../../src/chronaxis/execution/historical_conditional_blocks.py#L230)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
