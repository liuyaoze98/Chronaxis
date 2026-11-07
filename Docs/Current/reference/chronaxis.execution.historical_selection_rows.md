# `chronaxis.execution.historical_selection_rows`

逐块读取历史数据，逐行返回真实更新对应的SelectionRow。条件为真或未知的行分别保留状态。返回行借用当前块的数据，只能在下一次读取或关闭之前使用；若需长期保存，应由调用方复制并管理内存。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[HistoricalCalculationBlocks](chronaxis.execution.calculation_blocks.md#api-HistoricalCalculationBlocks)、[HistoricalConditionalBlocks](chronaxis.execution.historical_conditional_blocks.md#api-HistoricalConditionalBlocks)、[HoldContext](chronaxis.execution.hold.md#api-HoldContext)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`HistoricalSelectionRows`](#api-HistoricalSelectionRows)|拥有单当前块、有限核生成器和当前行费用，失败后只可重试关闭。|
|[`HistoricalSelectionRows.__init__`](#api-HistoricalSelectionRows-__init__)|检查真实select契约，先计费固定描述，再构造自有分块者。|
|[`HistoricalSelectionRows._make_blocks`](#api-HistoricalSelectionRows-_make_blocks)|创建一次自有单值或联合回读者，借用资源不接管关闭。|
|[`HistoricalSelectionRows.closed`](#api-HistoricalSelectionRows-closed)|查看本对象负责的资源是否已经全部关闭。|
|[`HistoricalSelectionRows.failed`](#api-HistoricalSelectionRows-failed)|读取操作失败状态。|
|[`HistoricalSelectionRows.exhausted`](#api-HistoricalSelectionRows-exhausted)|查看输入是否已经正常读到末尾。|
|[`HistoricalSelectionRows.__iter__`](#api-HistoricalSelectionRows-__iter__)|返回当前行迭代器本身，继续使用当前读取位置。|
|[`HistoricalSelectionRows._reserve`](#api-HistoricalSelectionRows-_reserve)|申请固定/工作区/当前行费用，并接管预约成功后取消的真实金额。|
|[`HistoricalSelectionRows._release`](#api-HistoricalSelectionRows-_release)|抵销实际自有费用，释放前取消保留金额，释放后取消立即更新归属。|
|[`HistoricalSelectionRows._drop_row`](#api-HistoricalSelectionRows-_drop_row)|结束当前借出行生命周期，释放取消时保留真实未抵销金额。|
|[`HistoricalSelectionRows._drop_current`](#api-HistoricalSelectionRows-_drop_current)|先关闭核生成器再关当前块，全部成功后释放当前核workspace。|
|[`HistoricalSelectionRows._load_current`](#api-HistoricalSelectionRows-_load_current)|取得一个有限块，在第一次消费选择核前预约全部核及行上界元数据。|
|[`HistoricalSelectionRows._finish_exhaustion`](#api-HistoricalSelectionRows-_finish_exhaustion)|正常EOF释放当前核/行/块费用，保留固定描述至explicit close。|
|[`HistoricalSelectionRows.__next__`](#api-HistoricalSelectionRows-__next__)|借出至下一次推进/close的单SelectionRow，TRUE/UNKNOWN原样交付。|
|[`HistoricalSelectionRows.close`](#api-HistoricalSelectionRows-close)|关闭核、当前块、分块者和自有费用，借用资源保持，重复关闭安全。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition
from ..core.calculations_memory_reference import require_calculation_plan
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import HistoricalCalculationBlocks, _calculation_observation
from .historical_conditional_blocks import HistoricalConditionalBlocks
```

</details>

<a id="api-HistoricalSelectionRows"></a>
## `HistoricalSelectionRows`

拥有单当前块、有限核生成器和当前行费用，失败后只可重试关闭。

数值与筛选由所选独立核完成，strict/minimum_coverage沿原行流语义，不造伪标量。
exhausted为正常EOF，与显式closed不同；EOF释放回读、当前块、核与行，固定描述费用保留至close。
再次next仍StopIteration，不将耗尽当作显式关闭。
任何清理失败保留实际句柄及金额，半关闭后不再交付行，不关闭借用历史或原状态。

```python
HistoricalSelectionRows(history, context, bindings, compiled, spec, condition=None, *, backend='numpy', batch_intervals=64, observation=None)
```


源码：[`src/chronaxis/execution/historical_selection_rows.py:31`](../../../src/chronaxis/execution/historical_selection_rows.py#L31)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-__init__"></a>
### `HistoricalSelectionRows.__init__`

检查真实select契约，先计费固定描述，再构造自有分块者。

```python
HistoricalSelectionRows.__init__(history, context, bindings, compiled, spec, condition=None, *, backend='numpy', batch_intervals=64, observation=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。本次分析保存的解码信号历史，必须已完成写入且尚未关闭；后续统计从这里读取，不重新解码输入文件。|
|`context`|[HoldContext](chronaxis.execution.hold.md#api-HoldContext)|是|无|位置或关键字。本会话的保持设置，含会话标识和时间范围；用它判断旧值可保持多久以及何时结束。|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)|是|无|位置或关键字。本次实际读取后建立的信号对应关系，包含输入来源和单位转换；不能用另一份输入的同名信号替代。|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。已经编译并绑定到本次输入的数值表达式，用它计算指标所需的值。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。当前指标的统计范围、算子、输出单位及数据不全时的处理设置；该对象的计算种类须符合本类用途。|
|`condition`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression) &#124; None|否|None|位置或关键字。额外筛选条件，结果必须是BOOL并使用同一组绑定；None表示不增加筛选条件。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`batch_intervals`|int|否|64|仅关键字。每次交付的正长度时间区间数量上限，须大于0；改变它只改变分批大小，不改变统计范围。|
|`observation`|Interval &#124; None|否|None|仅关键字。本次计算实际有数据的时间范围，用Interval给出，并且必须位于context.domain内。传None时沿用context.domain；函数不会读取文件来推算范围，因此调用方应传入已经核实的范围。|

#### 返回说明

尚未消费历史的行owner。

#### 异常说明

类型、能力、同步、预算、构造或取消错误；
    持续清理失败时原异常附historical_selection_rows_cleanup_owner用于恢复close。

源码：[`src/chronaxis/execution/historical_selection_rows.py:40`](../../../src/chronaxis/execution/historical_selection_rows.py#L40)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-_make_blocks"></a>
### `HistoricalSelectionRows._make_blocks`

创建一次自有单值或联合回读者，借用资源不接管关闭。

```python
HistoricalSelectionRows._make_blocks()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

HistoricalCalculationBlocks或HistoricalConditionalBlocks。

#### 异常说明

原构造/身份/同步/预算错误，恢复句柄由父构造接管。

源码：[`src/chronaxis/execution/historical_selection_rows.py:96`](../../../src/chronaxis/execution/historical_selection_rows.py#L96)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-closed"></a>
### `HistoricalSelectionRows.closed`

查看本对象负责的资源是否已经全部关闭。

```python
HistoricalSelectionRows.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_selection_rows.py:112`](../../../src/chronaxis/execution/historical_selection_rows.py#L112)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-failed"></a>
### `HistoricalSelectionRows.failed`

读取操作失败状态。

```python
HistoricalSelectionRows.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_selection_rows.py:117`](../../../src/chronaxis/execution/historical_selection_rows.py#L117)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-exhausted"></a>
### `HistoricalSelectionRows.exhausted`

查看输入是否已经正常读到末尾。

```python
HistoricalSelectionRows.exhausted
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示输入或结果已正常读完；False表示尚未正常读完。发生异常不等于正常读完。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_selection_rows.py:122`](../../../src/chronaxis/execution/historical_selection_rows.py#L122)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-__iter__"></a>
### `HistoricalSelectionRows.__iter__`

返回当前行迭代器本身，继续使用当前读取位置。

```python
HistoricalSelectionRows.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_selection_rows.py:126`](../../../src/chronaxis/execution/historical_selection_rows.py#L126)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-_reserve"></a>
### `HistoricalSelectionRows._reserve`

申请固定/工作区/当前行费用，并接管预约成功后取消的真实金额。

```python
HistoricalSelectionRows._reserve(amount, *, slot=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`slot`|str &#124; None|否|None|仅关键字。保存本次预约量的属性："_workspace_cost"是工作区内存，"_row_cost"是当前结果行内存。 None只计入总预约量，不另外记入上述用途属性。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算或取消传播，未真正增加账本时不记所有权。

源码：[`src/chronaxis/execution/historical_selection_rows.py:130`](../../../src/chronaxis/execution/historical_selection_rows.py#L130)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-_release"></a>
### `HistoricalSelectionRows._release`

抵销实际自有费用，释放前取消保留金额，释放后取消立即更新归属。

```python
HistoricalSelectionRows._release(amount, *, slot=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`slot`|str &#124; None|否|None|仅关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。None表示按本方法的总额处理。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放/取消传播，恢复后close不能再次抵销已释放费用。

源码：[`src/chronaxis/execution/historical_selection_rows.py:146`](../../../src/chronaxis/execution/historical_selection_rows.py#L146)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-_drop_row"></a>
### `HistoricalSelectionRows._drop_row`

结束当前借出行生命周期，释放取消时保留真实未抵销金额。

```python
HistoricalSelectionRows._drop_row()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

行费用释放或取消传播，之后需要调用close关闭资源。

源码：[`src/chronaxis/execution/historical_selection_rows.py:161`](../../../src/chronaxis/execution/historical_selection_rows.py#L161)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-_drop_current"></a>
### `HistoricalSelectionRows._drop_current`

先关闭核生成器再关当前块，全部成功后释放当前核workspace。

```python
HistoricalSelectionRows._drop_current()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

generator/block关闭、释放或取消传播，可重试。

源码：[`src/chronaxis/execution/historical_selection_rows.py:171`](../../../src/chronaxis/execution/historical_selection_rows.py#L171)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-_load_current"></a>
### `HistoricalSelectionRows._load_current`

取得一个有限块，在第一次消费选择核前预约全部核及行上界元数据。

```python
HistoricalSelectionRows._load_current()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

EOF为StopIteration；读取、预算、核构造或取消传播。

本函数直接报告的具体错误：

- `ResultClosedError`：选择行自有分块者已关闭、失败或正在清理。

源码：[`src/chronaxis/execution/historical_selection_rows.py:187`](../../../src/chronaxis/execution/historical_selection_rows.py#L187)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-_finish_exhaustion"></a>
### `HistoricalSelectionRows._finish_exhaustion`

正常EOF释放当前核/行/块费用，保留固定描述至explicit close。

```python
HistoricalSelectionRows._finish_exhaustion()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭/释放取消传播，失败后仅可close恢复。

源码：[`src/chronaxis/execution/historical_selection_rows.py:214`](../../../src/chronaxis/execution/historical_selection_rows.py#L214)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-__next__"></a>
### `HistoricalSelectionRows.__next__`

借出至下一次推进/close的单SelectionRow，TRUE/UNKNOWN原样交付。

```python
HistoricalSelectionRows.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

一个SelectionRow；FALSE、非实际更新和半开右端由原核过滤。

#### 异常说明

正常EOF可重复StopIteration；关闭/半关闭ResultClosedError；其他操作失败后仅close。

本函数直接报告的具体错误：

- `ResultClosedError`：历史选择行已关闭或正在清理。
- `RuntimeError`：失败的历史选择行只能关闭。
- `ResultClosedError`：选择行自有输入已关闭、失败或正在清理。

源码：[`src/chronaxis/execution/historical_selection_rows.py:228`](../../../src/chronaxis/execution/historical_selection_rows.py#L228)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalSelectionRows-close"></a>
### `HistoricalSelectionRows.close`

关闭核、当前块、分块者和自有费用，借用资源保持，重复关闭安全。

```python
HistoricalSelectionRows.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

generator/block/分块者关闭或金额释放取消可重试。

源码：[`src/chronaxis/execution/historical_selection_rows.py:270`](../../../src/chronaxis/execution/historical_selection_rows.py#L270)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
