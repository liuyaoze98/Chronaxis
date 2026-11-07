# `chronaxis.execution.historical_conditional_time_calculation`

从有限历史块得到完整的条件时间极值、时间均值或BOOL TRUE时长。

输入是已封存的新解码历史、原保持上下文、实际绑定、值/BOOL条件编译表达式和原指标请求。
每次step最多消费一个有限块；时间均值先取得整窗TRUE选择内的有效总时长，再重放同一新历史。
两遍不再读取原来源，数值分别使用独立参考或NumPy核，最终只换一次单位。
observation显式限制原domain内的计算观测域，条件两路和均值两遍都传同一范围；
None兼容原domain及预算，不证明实际观测，不修改原context、绑定或请求窗口。
完整窗口事实及来源诊断动态计费，超预算明确失败，不保留全窗时间轴或数值列表。
自有分块者、当前块和结果由close释放；借用历史、上下文、绑定及账本保持。
预算为新分析层保守估算，单线程账本交接，不承诺进程RSS或旧缓冲受控。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[ConditionalTimeCalculationFacts](chronaxis.core.conditional_time_reduction.md#api-ConditionalTimeCalculationFacts)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[HistoricalConditionalBlocks](chronaxis.execution.historical_conditional_blocks.md#api-HistoricalConditionalBlocks)、[HoldContext](chronaxis.execution.hold.md#api-HoldContext)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[TimeReductionResult](chronaxis.core.time_reduction.md#api-TimeReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`_append_ranges`](#api-_append_ranges)|合并同一种未知的相邻范围，保留真实已知间隔。|
|[`HistoricalConditionalTimeCalculation`](#api-HistoricalConditionalTimeCalculation)|分块读取数值和筛选条件，在选中时间内计算时间统计。数值缺失与条件未知分别记录；全部输入处理完毕后才能读取CalculationResult。加权平均先统计有效且选中的总时长，再进行第二遍计算。|
|[`HistoricalConditionalTimeCalculation.__init__`](#api-HistoricalConditionalTimeCalculation-__init__)|校验输入，预留固定状态，再创建自有分块者与纯数值核。|
|[`HistoricalConditionalTimeCalculation._make_reducer`](#api-HistoricalConditionalTimeCalculation-_make_reducer)|创建所选实现的计算器；计算平均值时，分母使用第一遍完整读取得到的有效总时长。|
|[`HistoricalConditionalTimeCalculation._make_blocks`](#api-HistoricalConditionalTimeCalculation-_make_blocks)|重新回读同一封存新历史，不再次扫描原来源。|
|[`HistoricalConditionalTimeCalculation._reset_facts`](#api-HistoricalConditionalTimeCalculation-_reset_facts)|清空本遍计数，新空tuple不复制旧未知诊断。|
|[`HistoricalConditionalTimeCalculation.closed`](#api-HistoricalConditionalTimeCalculation-closed)|读取实际关闭状态。|
|[`HistoricalConditionalTimeCalculation.failed`](#api-HistoricalConditionalTimeCalculation-failed)|读取操作失败状态。|
|[`HistoricalConditionalTimeCalculation.finished`](#api-HistoricalConditionalTimeCalculation-finished)|读取完整分类状态。|
|[`HistoricalConditionalTimeCalculation.result`](#api-HistoricalConditionalTimeCalculation-result)|借出完整窗口结果，close后不再开放。|
|[`HistoricalConditionalTimeCalculation._require_open`](#api-HistoricalConditionalTimeCalculation-_require_open)|拒绝半关闭或已关闭操作。|
|[`HistoricalConditionalTimeCalculation._reserve`](#api-HistoricalConditionalTimeCalculation-_reserve)|为当前对象申请内存额度；即使申请刚成功就被取消，也登记这笔占用，供随后归还。|
|[`HistoricalConditionalTimeCalculation._release`](#api-HistoricalConditionalTimeCalculation-_release)|扣账后即更新自有金额，释放前取消保留重试。|
|[`HistoricalConditionalTimeCalculation._append_facts`](#api-HistoricalConditionalTimeCalculation-_append_facts)|检查新块是否连续、覆盖统计是否完整，申请所需内存后保存缺失区间和来源信息。|
|[`HistoricalConditionalTimeCalculation._facts_snapshot`](#api-HistoricalConditionalTimeCalculation-_facts_snapshot)|读完全部输入后整理本遍的覆盖统计；尚未读完时不能返回整段结果。|
|[`HistoricalConditionalTimeCalculation._finish_pass`](#api-HistoricalConditionalTimeCalculation-_finish_pass)|均值第一遍切换到第二遍，或完整分类最终结果。|
|[`HistoricalConditionalTimeCalculation.step`](#api-HistoricalConditionalTimeCalculation-step)|处理至多一个有限块；换遍继续True，最终完整分类才返回False。|
|[`HistoricalConditionalTimeCalculation.close`](#api-HistoricalConditionalTimeCalculation-close)|关闭自有当前块/分块者和金额，保留借用历史及原调用方状态。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.moments import TIME_MOMENTS
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition, calculation_conversion, make_calculation_result
from ..core.models import Interval
from ..core.time_reduction import TimeReductionResult
from ..core.conditional_time_reduction import ConditionalTimeCalculationFacts
from ..core.types import QualityFlag as Q
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import _calculation_observation
from .historical_conditional_blocks import HistoricalConditionalBlocks
```

</details>

<a id="api-_append_ranges"></a>
## `_append_ranges`

合并同一种未知的相邻范围，保留真实已知间隔。

```python
_append_ranges(existing, incoming)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`existing`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|位置或关键字。此前累计的有序区间。|
|`incoming`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|位置或关键字。本次新增的有序区间；相邻或重叠部分合并，避免重复计算时长。|

### 返回说明

冻结有序tuple。

### 异常说明

ValueError为重叠；实际分配错误传播，调用方须先预约全部候选元数据。

本函数直接报告的具体错误：

- `ValueError`：条件时间指标未知范围重叠。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:29`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L29)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation"></a>
## `HistoricalConditionalTimeCalculation`

分块读取数值和筛选条件，在选中时间内计算时间统计。数值缺失与条件未知分别记录；全部输入处理完毕后才能读取CalculationResult。加权平均先统计有效且选中的总时长，再进行第二遍计算。

```python
HistoricalConditionalTimeCalculation(history, context, bindings, compiled, spec, condition, *, backend='numpy', batch_intervals=64, partial_limit=4096, observation=None)
```


源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:47`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L47)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-__init__"></a>
### `HistoricalConditionalTimeCalculation.__init__`

校验输入，预留固定状态，再创建自有分块者与纯数值核。

```python
HistoricalConditionalTimeCalculation.__init__(history, context, bindings, compiled, spec, condition, *, backend='numpy', batch_intervals=64, partial_limit=4096, observation=None)
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
|`partial_limit`|int|否|4096|仅关键字。浮点累加过程中保留的误差补偿项数量上限，须大于0；不是可忽略的错误次数。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。本次计算实际有数据的时间范围，用Interval给出，并且必须位于context.domain内。传None时沿用context.domain；函数不会读取文件来推算范围，因此调用方应传入已经核实的范围。|

#### 返回说明

尚未消费历史的新owner。

#### 异常说明

类型、能力、预算或构造错误；持续清理失败的原异常附
    historical_conditional_time_calculation_cleanup_owner，恢复环境后可调用其close。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:54`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L54)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_make_reducer"></a>
### `HistoricalConditionalTimeCalculation._make_reducer`

创建所选实现的计算器；计算平均值时，分母使用第一遍完整读取得到的有效总时长。

```python
HistoricalConditionalTimeCalculation._make_reducer(denominator=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`denominator`|int &#124; None|否|None|位置或关键字。时间均值的总有效选中时长，单位纳秒。第一次统计传None；第二次传入已统计的总时长，以各段时长占比加权。|

#### 返回说明

对应独立TimeReduction。

#### 异常说明

配置、数值模型或分配错误传播。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:116`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L116)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_make_blocks"></a>
### `HistoricalConditionalTimeCalculation._make_blocks`

重新回读同一封存新历史，不再次扫描原来源。

```python
HistoricalConditionalTimeCalculation._make_blocks()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

新HistoricalConditionalBlocks。

#### 异常说明

原构造/身份/预算错误。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:132`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L132)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_reset_facts"></a>
### `HistoricalConditionalTimeCalculation._reset_facts`

清空本遍计数，新空tuple不复制旧未知诊断。

```python
HistoricalConditionalTimeCalculation._reset_facts()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:142`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L142)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-closed"></a>
### `HistoricalConditionalTimeCalculation.closed`

读取实际关闭状态。

```python
HistoricalConditionalTimeCalculation.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:153`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L153)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-failed"></a>
### `HistoricalConditionalTimeCalculation.failed`

读取操作失败状态。

```python
HistoricalConditionalTimeCalculation.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:158`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L158)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-finished"></a>
### `HistoricalConditionalTimeCalculation.finished`

读取完整分类状态。

```python
HistoricalConditionalTimeCalculation.finished
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示规定的处理步骤已全部完成；False表示尚未完成。完成处理和关闭资源是两个独立状态。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:163`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L163)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-result"></a>
### `HistoricalConditionalTimeCalculation.result`

借出完整窗口结果，close后不再开放。

```python
HistoricalConditionalTimeCalculation.result
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

CalculationResult。

#### 异常说明

未完成/失败/关闭时拒绝。

本函数直接报告的具体错误：

- `RuntimeError`：历史时间指标尚未成功完成。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:168`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L168)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_require_open"></a>
### `HistoricalConditionalTimeCalculation._require_open`

拒绝半关闭或已关闭操作。

```python
HistoricalConditionalTimeCalculation._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：历史时间指标已关闭或正在清理。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:178`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L178)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_reserve"></a>
### `HistoricalConditionalTimeCalculation._reserve`

为当前对象申请内存额度；即使申请刚成功就被取消，也登记这笔占用，供随后归还。

```python
HistoricalConditionalTimeCalculation._reserve(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算或取消错误。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:183`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L183)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_release"></a>
### `HistoricalConditionalTimeCalculation._release`

扣账后即更新自有金额，释放前取消保留重试。

```python
HistoricalConditionalTimeCalculation._release(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放/取消错误。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:195`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L195)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_append_facts"></a>
### `HistoricalConditionalTimeCalculation._append_facts`

检查新块是否连续、覆盖统计是否完整，申请所需内存后保存缺失区间和来源信息。

```python
HistoricalConditionalTimeCalculation._append_facts(facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|[ConditionalTimeCalculationFacts](chronaxis.core.conditional_time_reduction.md#api-ConditionalTimeCalculationFacts)|是|无|位置或关键字。facts为纯核当前有限ConditionalTimeCalculationFacts。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

结构、身份、重复范围、预算或复制失败，此后只可关闭。

本函数直接报告的具体错误：

- `ValueError`：时间指标块事实与原请求或真实表达式不同。
- `ValueError`：时间指标块缺失真实交集。
- `ValueError`：时间指标块必须按原请求真实交集连续推进。
- `ValueError`：时间指标块有效与未知未完整划分。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:207`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L207)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_facts_snapshot"></a>
### `HistoricalConditionalTimeCalculation._facts_snapshot`

读完全部输入后整理本遍的覆盖统计；尚未读完时不能返回整段结果。

```python
HistoricalConditionalTimeCalculation._facts_snapshot()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

ConditionalTimeCalculationFacts。

#### 异常说明

完整范围或覆盖矛盾。

本函数直接报告的具体错误：

- `ValueError`：时间指标尚未完整消费真实交集。
- `ValueError`：时间指标全窗覆盖划分不完整。
- `ValueError`：条件时间指标全窗条件覆盖划分不完整。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:252`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L252)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-_finish_pass"></a>
### `HistoricalConditionalTimeCalculation._finish_pass`

均值第一遍切换到第二遍，或完整分类最终结果。

```python
HistoricalConditionalTimeCalculation._finish_pass()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

True表示进入第二遍，False表示最终完成。

#### 异常说明

覆盖/数值/新分块构造/预算或取消错误传播。

本函数直接报告的具体错误：

- `ValueError`：两遍时间均值的真实覆盖或来源不同。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:271`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L271)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-step"></a>
### `HistoricalConditionalTimeCalculation.step`

处理至多一个有限块；换遍继续True，最终完整分类才返回False。

```python
HistoricalConditionalTimeCalculation.step()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool；完成后重复False。

#### 异常说明

读取/数值/预算/取消错误，随后仅close。

本函数直接报告的具体错误：

- `RuntimeError`：失败的时间指标只能关闭。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:317`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L317)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalTimeCalculation-close"></a>
### `HistoricalConditionalTimeCalculation.close`

关闭自有当前块/分块者和金额，保留借用历史及原调用方状态。

```python
HistoricalConditionalTimeCalculation.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复关闭安全。

#### 异常说明

关闭或释放取消可重试。

源码：[`src/chronaxis/execution/historical_conditional_time_calculation.py:347`](../../../src/chronaxis/execution/historical_conditional_time_calculation.py#L347)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
