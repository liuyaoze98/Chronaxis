# chronaxis.execution.historical_time_calculation

从有限历史块得到完整的时间极值、时间均值或BOOL TRUE时长。

输入是已封存的新解码历史、原保持上下文、实际绑定、编译表达式和原指标请求。
每次step最多消费一个有限块；时间均值先取得真实有效总时长，再重放同一新历史。
两遍不再读取原来源，数值分别使用独立参考或NumPy核，最终只换一次单位。
observation显式限制原domain内的计算观测域，均值两遍保持同一范围；None兼容
原domain及固定预算，不证明实际观测。原context、绑定和CalculationDefinition.window均保持。
完整窗口事实及来源诊断动态计费，超预算明确失败，不保留全窗时间轴或数值列表。
自有分块者、当前块和结果由close释放；借用历史、上下文、绑定及账本保持。
预算为新分析层保守估算，单线程账本交接，不承诺进程RSS或旧缓冲受控。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[HistoricalCalculationBlocks](chronaxis.execution.calculation_blocks.md#api-HistoricalCalculationBlocks)、[HoldContext](chronaxis.execution.hold.md#api-HoldContext)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[TimeCalculationFacts](chronaxis.core.time_reduction.md#api-TimeCalculationFacts)、[TimeReductionResult](chronaxis.core.time_reduction.md#api-TimeReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`HistoricalTimeCalculation`](#api-HistoricalTimeCalculation)|分块读取指定范围，计算时间最小值、最大值、加权平均或条件成立时长。处理完全部输入后才能读取CalculationResult。平均值需要两遍读取同一历史：先统计有效总时长，再按时长比例累计。|
|[`HistoricalTimeCalculation.__init__`](#api-HistoricalTimeCalculation-__init__)|校验输入，预留固定状态，再创建自有分块者与纯数值核。|
|[`HistoricalTimeCalculation._make_reducer`](#api-HistoricalTimeCalculation-_make_reducer)|创建所选实现的计算器；计算平均值时，分母使用第一遍完整读取得到的有效总时长。|
|[`HistoricalTimeCalculation._make_blocks`](#api-HistoricalTimeCalculation-_make_blocks)|重新回读同一封存新历史，不再次扫描原来源。|
|[`HistoricalTimeCalculation._reset_facts`](#api-HistoricalTimeCalculation-_reset_facts)|清空本遍计数，新空tuple不复制旧未知诊断。|
|[`HistoricalTimeCalculation.closed`](#api-HistoricalTimeCalculation-closed)|读取实际关闭状态。|
|[`HistoricalTimeCalculation.failed`](#api-HistoricalTimeCalculation-failed)|读取操作失败状态。|
|[`HistoricalTimeCalculation.finished`](#api-HistoricalTimeCalculation-finished)|读取完整分类状态。|
|[`HistoricalTimeCalculation.result`](#api-HistoricalTimeCalculation-result)|借出完整窗口结果，close后不再开放。|
|[`HistoricalTimeCalculation._require_open`](#api-HistoricalTimeCalculation-_require_open)|拒绝半关闭或已关闭操作。|
|[`HistoricalTimeCalculation._reserve`](#api-HistoricalTimeCalculation-_reserve)|为当前对象申请内存额度；即使申请刚成功就被取消，也登记这笔占用，供随后归还。|
|[`HistoricalTimeCalculation._release`](#api-HistoricalTimeCalculation-_release)|扣账后即更新自有金额，释放前取消保留重试。|
|[`HistoricalTimeCalculation._append_facts`](#api-HistoricalTimeCalculation-_append_facts)|检查新块是否连续、覆盖统计是否完整，申请所需内存后保存缺失区间和来源信息。|
|[`HistoricalTimeCalculation._facts_snapshot`](#api-HistoricalTimeCalculation-_facts_snapshot)|读完全部输入后整理本遍的覆盖统计；尚未读完时不能返回整段结果。|
|[`HistoricalTimeCalculation._finish_pass`](#api-HistoricalTimeCalculation-_finish_pass)|均值第一遍切换到第二遍，或完整分类最终结果。|
|[`HistoricalTimeCalculation.step`](#api-HistoricalTimeCalculation-step)|处理至多一个有限块；换遍继续True，最终完整分类才返回False。|
|[`HistoricalTimeCalculation.close`](#api-HistoricalTimeCalculation-close)|关闭自有当前块/分块者和金额，保留借用历史及原调用方状态。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition, calculation_unit, make_calculation_result
from ..core.models import Interval
from ..core.time_reduction import TimeCalculationFacts, TimeReductionResult
from ..core.types import QualityFlag as Q
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import HistoricalCalculationBlocks, _calculation_observation
```

</details>

<a id="api-HistoricalTimeCalculation"></a>
## `HistoricalTimeCalculation`

分块读取指定范围，计算时间最小值、最大值、加权平均或条件成立时长。处理完全部输入后才能读取CalculationResult。平均值需要两遍读取同一历史：先统计有效总时长，再按时长比例累计。

```python
HistoricalTimeCalculation(history, context, bindings, compiled, spec, *, backend='numpy', batch_intervals=64, partial_limit=4096, observation=None)
```


源码：[`src/chronaxis/execution/historical_time_calculation.py:26`](../../../src/chronaxis/execution/historical_time_calculation.py#L26)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-__init__"></a>
### `HistoricalTimeCalculation.__init__`

校验输入，预留固定状态，再创建自有分块者与纯数值核。

```python
HistoricalTimeCalculation.__init__(history, context, bindings, compiled, spec, *, backend='numpy', batch_intervals=64, partial_limit=4096, observation=None)
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
|`partial_limit`|int|否|4096|仅关键字。浮点累加过程中保留的误差补偿项数量上限，须大于0；不是可忽略的错误次数。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。本次计算实际有数据的时间范围，用Interval给出，并且必须位于context.domain内。传None时沿用context.domain；函数不会读取文件来推算范围，因此调用方应传入已经核实的范围。|

#### 返回说明

尚未消费历史的新owner。

#### 异常说明

类型、能力、预算或构造错误；持续清理失败的原异常附
    historical_time_calculation_cleanup_owner，恢复环境后可调用其close。

源码：[`src/chronaxis/execution/historical_time_calculation.py:33`](../../../src/chronaxis/execution/historical_time_calculation.py#L33)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_make_reducer"></a>
### `HistoricalTimeCalculation._make_reducer`

创建所选实现的计算器；计算平均值时，分母使用第一遍完整读取得到的有效总时长。

```python
HistoricalTimeCalculation._make_reducer(denominator=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`denominator`|int &#124; None|否|None|位置或关键字。时间均值的总有效选中时长，单位纳秒。第一次统计传None；第二次传入已统计的总时长，以各段时长占比加权。|

#### 返回说明

对应独立TimeReduction。

#### 异常说明

配置、数值模型或分配错误传播。

源码：[`src/chronaxis/execution/historical_time_calculation.py:95`](../../../src/chronaxis/execution/historical_time_calculation.py#L95)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_make_blocks"></a>
### `HistoricalTimeCalculation._make_blocks`

重新回读同一封存新历史，不再次扫描原来源。

```python
HistoricalTimeCalculation._make_blocks()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

新HistoricalCalculationBlocks。

#### 异常说明

原构造/身份/预算错误。

源码：[`src/chronaxis/execution/historical_time_calculation.py:111`](../../../src/chronaxis/execution/historical_time_calculation.py#L111)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_reset_facts"></a>
### `HistoricalTimeCalculation._reset_facts`

清空本遍计数，新空tuple不复制旧未知诊断。

```python
HistoricalTimeCalculation._reset_facts()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_time_calculation.py:121`](../../../src/chronaxis/execution/historical_time_calculation.py#L121)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-closed"></a>
### `HistoricalTimeCalculation.closed`

读取实际关闭状态。

```python
HistoricalTimeCalculation.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_time_calculation.py:131`](../../../src/chronaxis/execution/historical_time_calculation.py#L131)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-failed"></a>
### `HistoricalTimeCalculation.failed`

读取操作失败状态。

```python
HistoricalTimeCalculation.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_time_calculation.py:136`](../../../src/chronaxis/execution/historical_time_calculation.py#L136)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-finished"></a>
### `HistoricalTimeCalculation.finished`

读取完整分类状态。

```python
HistoricalTimeCalculation.finished
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示规定的处理步骤已全部完成；False表示尚未完成。完成处理和关闭资源是两个独立状态。

#### 异常说明

无。

源码：[`src/chronaxis/execution/historical_time_calculation.py:141`](../../../src/chronaxis/execution/historical_time_calculation.py#L141)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-result"></a>
### `HistoricalTimeCalculation.result`

借出完整窗口结果，close后不再开放。

```python
HistoricalTimeCalculation.result
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

源码：[`src/chronaxis/execution/historical_time_calculation.py:146`](../../../src/chronaxis/execution/historical_time_calculation.py#L146)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_require_open"></a>
### `HistoricalTimeCalculation._require_open`

拒绝半关闭或已关闭操作。

```python
HistoricalTimeCalculation._require_open()
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

源码：[`src/chronaxis/execution/historical_time_calculation.py:156`](../../../src/chronaxis/execution/historical_time_calculation.py#L156)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_reserve"></a>
### `HistoricalTimeCalculation._reserve`

为当前对象申请内存额度；即使申请刚成功就被取消，也登记这笔占用，供随后归还。

```python
HistoricalTimeCalculation._reserve(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算或取消错误。

源码：[`src/chronaxis/execution/historical_time_calculation.py:161`](../../../src/chronaxis/execution/historical_time_calculation.py#L161)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_release"></a>
### `HistoricalTimeCalculation._release`

扣账后即更新自有金额，释放前取消保留重试。

```python
HistoricalTimeCalculation._release(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放/取消错误。

源码：[`src/chronaxis/execution/historical_time_calculation.py:173`](../../../src/chronaxis/execution/historical_time_calculation.py#L173)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_append_facts"></a>
### `HistoricalTimeCalculation._append_facts`

检查新块是否连续、覆盖统计是否完整，申请所需内存后保存缺失区间和来源信息。

```python
HistoricalTimeCalculation._append_facts(facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|[TimeCalculationFacts](chronaxis.core.time_reduction.md#api-TimeCalculationFacts)|是|无|位置或关键字。facts为纯核当前有限TimeCalculationFacts。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

结构、身份、重复范围、预算或复制失败，此后只可关闭。

本函数直接报告的具体错误：

- `ValueError`：时间指标块事实与原请求或真实表达式不同。
- `ValueError`：时间指标块缺失真实交集。
- `ValueError`：时间指标块必须按原请求真实交集连续推进。
- `ValueError`：时间指标块有效与未知未完整划分。
- `ValueError`：时间指标未知范围重叠。

源码：[`src/chronaxis/execution/historical_time_calculation.py:185`](../../../src/chronaxis/execution/historical_time_calculation.py#L185)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_facts_snapshot"></a>
### `HistoricalTimeCalculation._facts_snapshot`

读完全部输入后整理本遍的覆盖统计；尚未读完时不能返回整段结果。

```python
HistoricalTimeCalculation._facts_snapshot()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

TimeCalculationFacts。

#### 异常说明

完整范围或覆盖矛盾。

本函数直接报告的具体错误：

- `ValueError`：时间指标尚未完整消费真实交集。
- `ValueError`：时间指标全窗覆盖划分不完整。

源码：[`src/chronaxis/execution/historical_time_calculation.py:232`](../../../src/chronaxis/execution/historical_time_calculation.py#L232)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-_finish_pass"></a>
### `HistoricalTimeCalculation._finish_pass`

均值第一遍切换到第二遍，或完整分类最终结果。

```python
HistoricalTimeCalculation._finish_pass()
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

源码：[`src/chronaxis/execution/historical_time_calculation.py:246`](../../../src/chronaxis/execution/historical_time_calculation.py#L246)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-step"></a>
### `HistoricalTimeCalculation.step`

处理至多一个有限块；换遍继续True，最终完整分类才返回False。

```python
HistoricalTimeCalculation.step()
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

源码：[`src/chronaxis/execution/historical_time_calculation.py:289`](../../../src/chronaxis/execution/historical_time_calculation.py#L289)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-HistoricalTimeCalculation-close"></a>
### `HistoricalTimeCalculation.close`

关闭自有当前块/分块者和金额，保留借用历史及原调用方状态。

```python
HistoricalTimeCalculation.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复关闭安全。

#### 异常说明

关闭或释放取消可重试。

源码：[`src/chronaxis/execution/historical_time_calculation.py:319`](../../../src/chronaxis/execution/historical_time_calculation.py#L319)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
