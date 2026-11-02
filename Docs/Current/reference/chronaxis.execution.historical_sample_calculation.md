# chronaxis.execution.historical_sample_calculation

从有限历史块得到完整的样本极值或算术均值，可附独立BOOL选择条件。

输入是已封存的新解码历史、原保持上下文、实际绑定、编译表达式和原指标请求。
每次step最多消费一个有限块；均值不建立第二遍块源，也不重新扫描原来源。
样本均值累计原序真实更新的原单位总和，完整EOF后除总样本数并换单位一次。
TTL、条件更新和裁剪保持不增加样本；完整双覆盖、未知和来源动态先预约费用。
observation显式限制原domain内的计算观测域，样本只取该域半开范围内真实更新；
None兼容原domain及原预算，不证明实际观测。原context、绑定和请求窗口不改变。
自有分块者、当前块、数值状态和结果由close释放；借用历史、上下文与绑定保持。
预算是新分析层保守估算，超限明确失败，不承诺进程RSS或旧来源缓冲受控。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[HistoricalCalculationBlocks](chronaxis.execution.calculation_blocks.md#api-HistoricalCalculationBlocks)、[HistoricalConditionalBlocks](chronaxis.execution.historical_conditional_blocks.md#api-HistoricalConditionalBlocks)、[HoldContext](chronaxis.execution.hold.md#api-HoldContext)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SampleCalculationFacts](chronaxis.core.sample_reduction.md#api-SampleCalculationFacts)

## 对象导航

|对象|用途|
|---|---|
|[`_append_ranges`](#api-_append_ranges)|合并同一种未知的相邻范围，保留真实已知间隔。|
|[`HistoricalSampleCalculation`](#api-HistoricalSampleCalculation)|分块读取真实样本，计算样本最小值、最大值或算术平均值；可再加BOOL筛选条件。全部输入处理完毕后才提供CalculationResult。一个值保持多个时间段仍只算一次真实更新。|
|[`HistoricalSampleCalculation.__init__`](#api-HistoricalSampleCalculation-__init__)|校验输入，预留固定状态，再创建自有分块者和纯样本核。|
|[`HistoricalSampleCalculation._make_reducer`](#api-HistoricalSampleCalculation-_make_reducer)|创建所选后端的独立样本核，不需要预先知道均值分母。|
|[`HistoricalSampleCalculation._make_blocks`](#api-HistoricalSampleCalculation-_make_blocks)|创建一次自有历史回读者，按可选条件选择单源或联合边界。|
|[`HistoricalSampleCalculation.closed`](#api-HistoricalSampleCalculation-closed)|读取实际关闭状态。|
|[`HistoricalSampleCalculation.failed`](#api-HistoricalSampleCalculation-failed)|读取操作失败状态。|
|[`HistoricalSampleCalculation.finished`](#api-HistoricalSampleCalculation-finished)|读取完整分类状态。|
|[`HistoricalSampleCalculation.result`](#api-HistoricalSampleCalculation-result)|借出完整窗口结果，关闭或失败后不再开放。|
|[`HistoricalSampleCalculation._require_open`](#api-HistoricalSampleCalculation-_require_open)|拒绝半关闭或已关闭操作。|
|[`HistoricalSampleCalculation._reserve`](#api-HistoricalSampleCalculation-_reserve)|为当前对象申请内存额度；即使申请刚成功就被取消，也登记这笔占用，供随后归还。|
|[`HistoricalSampleCalculation._release`](#api-HistoricalSampleCalculation-_release)|扣账后即更新自有金额，释放前取消保留重试。|
|[`HistoricalSampleCalculation._append_facts`](#api-HistoricalSampleCalculation-_append_facts)|检查新块是否连续、覆盖统计是否完整，申请内存后分别保存数值缺失、条件未知和来源信息。|
|[`HistoricalSampleCalculation._facts_snapshot`](#api-HistoricalSampleCalculation-_facts_snapshot)|读完全部输入后整理整个请求范围的覆盖统计；尚未读完时不能返回整段结果。|
|[`HistoricalSampleCalculation._finish`](#api-HistoricalSampleCalculation-_finish)|按完整事实和最终数值分类一次，原序样本和无需第二遍。|
|[`HistoricalSampleCalculation.step`](#api-HistoricalSampleCalculation-step)|处理至多一个有限块，完整EOF分类后才返回False。|
|[`HistoricalSampleCalculation.close`](#api-HistoricalSampleCalculation-close)|关闭自有当前块、分块者和金额，保留借用历史及原调用方状态。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition, make_calculation_result
from ..core.models import Interval
from ..core.sample_reduction import SampleCalculationFacts
from ..core.types import QualityFlag as Q
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import HistoricalCalculationBlocks, _calculation_observation
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

ValueError为重叠；分配错误传播，调用方须先预约全部候选元数据。

本函数直接报告的具体错误：

- `ValueError`：样本指标未知范围重叠。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:27`](../../../src/chronaxis/execution/historical_sample_calculation.py#L27)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation"></a>
## `HistoricalSampleCalculation`

分块读取真实样本，计算样本最小值、最大值或算术平均值；可再加BOOL筛选条件。全部输入处理完毕后才提供CalculationResult。一个值保持多个时间段仍只算一次真实更新。

```python
HistoricalSampleCalculation(history, context, bindings, compiled, spec, condition=None, *, backend='numpy', batch_intervals=64, partial_limit=4096, observation=None)
```


源码：[`src/chronaxis/execution/historical_sample_calculation.py:45`](../../../src/chronaxis/execution/historical_sample_calculation.py#L45)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-__init__"></a>
### `HistoricalSampleCalculation.__init__`

校验输入，预留固定状态，再创建自有分块者和纯样本核。

```python
HistoricalSampleCalculation.__init__(history, context, bindings, compiled, spec, condition=None, *, backend='numpy', batch_intervals=64, partial_limit=4096, observation=None)
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
|`partial_limit`|int|否|4096|仅关键字。浮点累加过程中保留的误差补偿项数量上限，须大于0；不是可忽略的错误次数。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。本次计算实际有数据的时间范围，用Interval给出，并且必须位于context.domain内。传None时沿用context.domain；函数不会读取文件来推算范围，因此调用方应传入已经核实的范围。|

#### 返回说明

尚未消费历史的新owner。

#### 异常说明

类型、能力、预算或构造错误；持续清理失败的原异常附
    historical_sample_calculation_cleanup_owner，恢复环境后可调用其close。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:52`](../../../src/chronaxis/execution/historical_sample_calculation.py#L52)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-_make_reducer"></a>
### `HistoricalSampleCalculation._make_reducer`

创建所选后端的独立样本核，不需要预先知道均值分母。

```python
HistoricalSampleCalculation._make_reducer()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

对应SampleReduction。

#### 异常说明

原配置、数值模型或分配错误。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:119`](../../../src/chronaxis/execution/historical_sample_calculation.py#L119)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-_make_blocks"></a>
### `HistoricalSampleCalculation._make_blocks`

创建一次自有历史回读者，按可选条件选择单源或联合边界。

```python
HistoricalSampleCalculation._make_blocks()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

HistoricalCalculationBlocks或HistoricalConditionalBlocks。

#### 异常说明

原构造、身份、条件或预算错误；持续清理入口由构造调用方接管。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:134`](../../../src/chronaxis/execution/historical_sample_calculation.py#L134)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-closed"></a>
### `HistoricalSampleCalculation.closed`

读取实际关闭状态。

```python
HistoricalSampleCalculation.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:150`](../../../src/chronaxis/execution/historical_sample_calculation.py#L150)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-failed"></a>
### `HistoricalSampleCalculation.failed`

读取操作失败状态。

```python
HistoricalSampleCalculation.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:155`](../../../src/chronaxis/execution/historical_sample_calculation.py#L155)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-finished"></a>
### `HistoricalSampleCalculation.finished`

读取完整分类状态。

```python
HistoricalSampleCalculation.finished
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示规定的处理步骤已全部完成；False表示尚未完成。完成处理和关闭资源是两个独立状态。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:160`](../../../src/chronaxis/execution/historical_sample_calculation.py#L160)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-result"></a>
### `HistoricalSampleCalculation.result`

借出完整窗口结果，关闭或失败后不再开放。

```python
HistoricalSampleCalculation.result
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

- `RuntimeError`：历史样本指标尚未成功完成。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:165`](../../../src/chronaxis/execution/historical_sample_calculation.py#L165)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-_require_open"></a>
### `HistoricalSampleCalculation._require_open`

拒绝半关闭或已关闭操作。

```python
HistoricalSampleCalculation._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：历史样本指标已关闭或正在清理。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:175`](../../../src/chronaxis/execution/historical_sample_calculation.py#L175)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-_reserve"></a>
### `HistoricalSampleCalculation._reserve`

为当前对象申请内存额度；即使申请刚成功就被取消，也登记这笔占用，供随后归还。

```python
HistoricalSampleCalculation._reserve(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算或取消错误。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:180`](../../../src/chronaxis/execution/historical_sample_calculation.py#L180)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-_release"></a>
### `HistoricalSampleCalculation._release`

扣账后即更新自有金额，释放前取消保留重试。

```python
HistoricalSampleCalculation._release(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放或取消错误。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:192`](../../../src/chronaxis/execution/historical_sample_calculation.py#L192)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-_append_facts"></a>
### `HistoricalSampleCalculation._append_facts`

检查新块是否连续、覆盖统计是否完整，申请内存后分别保存数值缺失、条件未知和来源信息。

```python
HistoricalSampleCalculation._append_facts(facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|[SampleCalculationFacts](chronaxis.core.sample_reduction.md#api-SampleCalculationFacts)|是|无|位置或关键字。facts为纯核当前有限SampleCalculationFacts。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

结构、身份、重复范围、预算或复制失败，此后只可关闭。

本函数直接报告的具体错误：

- `ValueError`：样本块事实与原请求或真实表达式不同。
- `ValueError`：样本块缺失真实交集。
- `ValueError`：样本块必须按真实交集连续推进。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:204`](../../../src/chronaxis/execution/historical_sample_calculation.py#L204)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-_facts_snapshot"></a>
### `HistoricalSampleCalculation._facts_snapshot`

读完全部输入后整理整个请求范围的覆盖统计；尚未读完时不能返回整段结果。

```python
HistoricalSampleCalculation._facts_snapshot()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SampleCalculationFacts。

#### 异常说明

完整范围或双覆盖矛盾。

本函数直接报告的具体错误：

- `ValueError`：样本指标尚未完整消费真实交集。
- `ValueError`：样本全窗值覆盖不完整。
- `ValueError`：样本全窗条件覆盖不完整。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:244`](../../../src/chronaxis/execution/historical_sample_calculation.py#L244)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-_finish"></a>
### `HistoricalSampleCalculation._finish`

按完整事实和最终数值分类一次，原序样本和无需第二遍。

```python
HistoricalSampleCalculation._finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

False表示最终完成。

#### 异常说明

覆盖、数值快照、预算或取消错误。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:263`](../../../src/chronaxis/execution/historical_sample_calculation.py#L263)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-step"></a>
### `HistoricalSampleCalculation.step`

处理至多一个有限块，完整EOF分类后才返回False。

```python
HistoricalSampleCalculation.step()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool；完成后重复False。

#### 异常说明

读取/数值/预算/取消错误，随后仅close。

本函数直接报告的具体错误：

- `RuntimeError`：失败的样本指标只能关闭。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:284`](../../../src/chronaxis/execution/historical_sample_calculation.py#L284)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalSampleCalculation-close"></a>
### `HistoricalSampleCalculation.close`

关闭自有当前块、分块者和金额，保留借用历史及原调用方状态。

```python
HistoricalSampleCalculation.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复关闭安全。

#### 异常说明

关闭或释放取消可重试。

源码：[`src/chronaxis/execution/historical_sample_calculation.py:314`](../../../src/chronaxis/execution/historical_sample_calculation.py#L314)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
