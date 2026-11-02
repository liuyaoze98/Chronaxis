# chronaxis.execution.condition_evidence

在同一时刻的全部更新处理前后，分别计算条件状态，供事件检测器判断持续成立、边沿和未知中断。计算前先从资源限额中申请所需内存；返回对象负责归还自己占用的额度。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[ExpressionQueries](chronaxis.execution.expressions.md#api-ExpressionQueries)、[Interval](chronaxis.core.models.md#api-Interval)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[_BatchRegistry](chronaxis.execution.temporal_buffer.md#api-_BatchRegistry)

## 对象导航

|对象|用途|
|---|---|
|[`PreparedConditionEvidence`](#api-PreparedConditionEvidence)|保存一个条件的旧点和输出，生命周期为预备→完成/失败→关闭。|
|[`PreparedConditionEvidence.__init__`](#api-PreparedConditionEvidence-__init__)|接收已申请workspace和旧点，不复制数组或编译树。|
|[`PreparedConditionEvidence._ensure_open`](#api-PreparedConditionEvidence-_ensure_open)|拒绝释放后使用。|
|[`PreparedConditionEvidence.closed`](#api-PreparedConditionEvidence-closed)|读取关闭状态。|
|[`PreparedConditionEvidence.failed`](#api-PreparedConditionEvidence-failed)|读取完成失败状态。|
|[`PreparedConditionEvidence.completed`](#api-PreparedConditionEvidence-completed)|读取完成状态。|
|[`PreparedConditionEvidence.time_ns`](#api-PreparedConditionEvidence-time_ns)|读取目标时间。|
|[`PreparedConditionEvidence.ticks`](#api-PreparedConditionEvidence-ticks)|读取一点证据。|
|[`PreparedConditionEvidence.source_refs`](#api-PreparedConditionEvidence-source_refs)|读取当前点位置。|
|[`PreparedConditionEvidence.binding_identity`](#api-PreparedConditionEvidence-binding_identity)|读取实际绑定身份。|
|[`PreparedConditionEvidence.compiled_identity`](#api-PreparedConditionEvidence-compiled_identity)|读取编译身份。|
|[`PreparedConditionEvidence._close_views`](#api-PreparedConditionEvidence-_close_views)|关闭三快照，失败句柄留在字段供close重试。|
|[`PreparedConditionEvidence._charge_refs`](#api-PreparedConditionEvidence-_charge_refs)|保存完整来源位置前增加独立持有量。|
|[`PreparedConditionEvidence.complete`](#api-PreparedConditionEvidence-complete)|核对唯一目标提交后求值并形成真实三视图证据。|
|[`PreparedConditionEvidence._discard`](#api-PreparedConditionEvidence-_discard)|移除链成员与预备槽，丢弃已释放的自有引用。|
|[`PreparedConditionEvidence.close`](#api-PreparedConditionEvidence-close)|释放三查询与workspace/refs，保留上游。|
|[`ConditionEvidenceQueries`](#api-ConditionEvidenceQueries)|借用真实表达式查询，固定槽和链式结果拥有独立预算。|
|[`ConditionEvidenceQueries.__init__`](#api-ConditionEvidenceQueries-__init__)|先申请固定槽/游标空间，再取得上游登记序号。|
|[`ConditionEvidenceQueries.closed`](#api-ConditionEvidenceQueries-closed)|读取关闭状态。|
|[`ConditionEvidenceQueries._ensure_open`](#api-ConditionEvidenceQueries-_ensure_open)|检查自身及上游。|
|[`ConditionEvidenceQueries._construct`](#api-ConditionEvidenceQueries-_construct)|仅构造局部结果，不安装槽或结果链。|
|[`ConditionEvidenceQueries.prepare`](#api-ConditionEvidenceQueries-prepare)|在目标组提交前捕获同一时刻旧点并返回有预算预备结果。|
|[`ConditionEvidenceQueries.close`](#api-ConditionEvidenceQueries-close)|关闭自有预备/完成结果与固定槽，保留调用方上游。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.condition_evidence import condition_ticks_reference, condition_ticks_numpy
from ..core.expression import CompiledExpression
from ..core.models import Interval
from ..core.types import SignalDType
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner
from ..timebase.conversion import require_int64_ns
from .expressions import ExpressionQueries
from .history import _metadata_bytes
from .temporal_buffer import _BatchRegistry
```

</details>

<a id="api-PreparedConditionEvidence"></a>
## `PreparedConditionEvidence`

保存一个条件的旧点和输出，生命周期为预备→完成/失败→关闭。

每表达式至多一个预备槽；完成后释放槽，输出仍保有独立预算。
complete失败不回滚state且禁止再次完成；close始终负责自有资源。
私有链指针由登记器维护，公开状态/输出只读。

```python
PreparedConditionEvidence(owner, cost, slot, time_ns, revision, before, axis)
```


源码：[`src/chronaxis/execution/condition_evidence.py:29`](../../../src/chronaxis/execution/condition_evidence.py#L29)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-__init__"></a>
### `PreparedConditionEvidence.__init__`

接收已申请workspace和旧点，不复制数组或编译树。

```python
PreparedConditionEvidence.__init__(owner, cost, slot, time_ns, revision, before, axis)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[ConditionEvidenceQueries](chronaxis.execution.condition_evidence.md#api-ConditionEvidenceQueries)|是|无|位置或关键字。创建预备条件结果的查询管理器，负责后续提交或关闭该结果。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`slot`|int|是|无|位置或关键字。条件表达式在本查询对象登记表中的非负序号。|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`revision`|int|是|无|位置或关键字。准备条件证据时的状态版本；完成时用来检查中途是否发生了不应出现的状态更新。|
|`before`|ExpressionResult|是|无|位置或关键字。准备更新前取得的条件结果；先用它结束前一段时间，再处理当前更新。|
|`axis`|tuple[int, ...] &#124; numpy.ndarray[int64]|是|无|位置或关键字。只含当前时刻的一项纳秒时间轴，参考实现为tuple，数组实现为int64数组；它不是文件句柄。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

分配失败由prepare清理。

源码：[`src/chronaxis/execution/condition_evidence.py:37`](../../../src/chronaxis/execution/condition_evidence.py#L37)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-_ensure_open"></a>
### `PreparedConditionEvidence._ensure_open`

拒绝释放后使用。

```python
PreparedConditionEvidence._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：预备条件证据已关闭。

源码：[`src/chronaxis/execution/condition_evidence.py:53`](../../../src/chronaxis/execution/condition_evidence.py#L53)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-closed"></a>
### `PreparedConditionEvidence.closed`

读取关闭状态。

```python
PreparedConditionEvidence.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/condition_evidence.py:59`](../../../src/chronaxis/execution/condition_evidence.py#L59)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-failed"></a>
### `PreparedConditionEvidence.failed`

读取完成失败状态。

```python
PreparedConditionEvidence.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/condition_evidence.py:64`](../../../src/chronaxis/execution/condition_evidence.py#L64)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-completed"></a>
### `PreparedConditionEvidence.completed`

读取完成状态。

```python
PreparedConditionEvidence.completed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示条件结果已经计算完成；False表示尚未完成。

#### 异常说明

无。

源码：[`src/chronaxis/execution/condition_evidence.py:69`](../../../src/chronaxis/execution/condition_evidence.py#L69)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-time_ns"></a>
### `PreparedConditionEvidence.time_ns`

读取目标时间。

```python
PreparedConditionEvidence.time_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int ns。

#### 异常说明

对象处于下列状态时抛ResultClosedError：预备条件证据已关闭。

源码：[`src/chronaxis/execution/condition_evidence.py:74`](../../../src/chronaxis/execution/condition_evidence.py#L74)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-ticks"></a>
### `PreparedConditionEvidence.ticks`

读取一点证据。

```python
PreparedConditionEvidence.ticks
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ConditionTick tuple。

#### 异常说明

关闭/未完成。

本函数直接报告的具体错误：

- `AnalysisError`：条件证据尚未完成。

源码：[`src/chronaxis/execution/condition_evidence.py:80`](../../../src/chronaxis/execution/condition_evidence.py#L80)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-source_refs"></a>
### `PreparedConditionEvidence.source_refs`

读取当前点位置。

```python
PreparedConditionEvidence.source_refs
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SourceRef tuple。

#### 异常说明

关闭/未完成。

本函数直接报告的具体错误：

- `AnalysisError`：条件证据尚未完成。

源码：[`src/chronaxis/execution/condition_evidence.py:89`](../../../src/chronaxis/execution/condition_evidence.py#L89)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-binding_identity"></a>
### `PreparedConditionEvidence.binding_identity`

读取实际绑定身份。

```python
PreparedConditionEvidence.binding_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SHA文本。

#### 异常说明

对象处于下列状态时抛ResultClosedError：预备条件证据已关闭。

源码：[`src/chronaxis/execution/condition_evidence.py:97`](../../../src/chronaxis/execution/condition_evidence.py#L97)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-compiled_identity"></a>
### `PreparedConditionEvidence.compiled_identity`

读取编译身份。

```python
PreparedConditionEvidence.compiled_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SHA文本。

#### 异常说明

对象处于下列状态时抛ResultClosedError：预备条件证据已关闭。

源码：[`src/chronaxis/execution/condition_evidence.py:103`](../../../src/chronaxis/execution/condition_evidence.py#L103)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-_close_views"></a>
### `PreparedConditionEvidence._close_views`

关闭三快照，失败句柄留在字段供close重试。

```python
PreparedConditionEvidence._close_views()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，成功字段清空。

#### 异常说明

查询关闭错误原样传播。

源码：[`src/chronaxis/execution/condition_evidence.py:108`](../../../src/chronaxis/execution/condition_evidence.py#L108)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-_charge_refs"></a>
### `PreparedConditionEvidence._charge_refs`

保存完整来源位置前增加独立持有量。

```python
PreparedConditionEvidence._charge_refs(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

None，成功金额计入_cost。

#### 异常说明

预算拒绝/取消传播；已记账的返回取消仍保有申请直到close。

源码：[`src/chronaxis/execution/condition_evidence.py:120`](../../../src/chronaxis/execution/condition_evidence.py#L120)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-complete"></a>
### `PreparedConditionEvidence.complete`

核对唯一目标提交后求值并形成真实三视图证据。

```python
PreparedConditionEvidence.complete()
```

参数：无显式参数。


#### 参数说明

无；调用方可已提交一次同一时刻完整组，定时器可不提交。

#### 返回说明

None，之后通过ticks/source_refs读取快照。

#### 异常说明

版本/预算/求值/取消错误传播，转failed并禁止再完成；不回滚state，仍须close。

本函数直接报告的具体错误：

- `AnalysisError`：条件证据不能重复完成或从失败恢复。
- `ValueError`：预备条件两段之间只能提交一次目标完整组。

源码：[`src/chronaxis/execution/condition_evidence.py:137`](../../../src/chronaxis/execution/condition_evidence.py#L137)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-_discard"></a>
### `PreparedConditionEvidence._discard`

移除链成员与预备槽，丢弃已释放的自有引用。

```python
PreparedConditionEvidence._discard()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，结果关闭。

#### 异常说明

脱链错误传播，finally仍关闭；owner重试可清理残留链。

源码：[`src/chronaxis/execution/condition_evidence.py:189`](../../../src/chronaxis/execution/condition_evidence.py#L189)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PreparedConditionEvidence-close"></a>
### `PreparedConditionEvidence.close`

释放三查询与workspace/refs，保留上游。

```python
PreparedConditionEvidence.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

查询/预算关闭错误传播，未扣账可重试，已扣账取消最小收尾。

源码：[`src/chronaxis/execution/condition_evidence.py:206`](../../../src/chronaxis/execution/condition_evidence.py#L206)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ConditionEvidenceQueries"></a>
## `ConditionEvidenceQueries`

借用真实表达式查询，固定槽和链式结果拥有独立预算。

每表达式至多一个未完成结果，已完成输出按自身成本可保留到close。
编译树由上游拥有，本层只保存整数登记序号，不延长已释放编译元数据寿命。

```python
ConditionEvidenceQueries(expressions: ExpressionQueries, *, backend='numpy', observation=None)
```


源码：[`src/chronaxis/execution/condition_evidence.py:225`](../../../src/chronaxis/execution/condition_evidence.py#L225)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ConditionEvidenceQueries-__init__"></a>
### `ConditionEvidenceQueries.__init__`

先申请固定槽/游标空间，再取得上游登记序号。

```python
ConditionEvidenceQueries.__init__(expressions: ExpressionQueries, *, backend='numpy', observation=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`expressions`|[ExpressionQueries](chronaxis.execution.expressions.md#api-ExpressionQueries)|是|无|位置或关键字。expressions打开的真实ExpressionQueries|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。observation为原请求范围内的实际Interval，None沿用原HoldContext.domain。|

#### 返回说明

新owner，不关闭上游或提交state。

#### 异常说明

类型/关闭/预算/取消原错误传播；部分构造关闭自有申请，持续清理失败
    从原异常的condition_evidence_queries_cleanup_owner恢复close，不关闭上游。

源码：[`src/chronaxis/execution/condition_evidence.py:232`](../../../src/chronaxis/execution/condition_evidence.py#L232)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ConditionEvidenceQueries-closed"></a>
### `ConditionEvidenceQueries.closed`

读取关闭状态。

```python
ConditionEvidenceQueries.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/condition_evidence.py:279`](../../../src/chronaxis/execution/condition_evidence.py#L279)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ConditionEvidenceQueries-_ensure_open"></a>
### `ConditionEvidenceQueries._ensure_open`

检查自身及上游。

```python
ConditionEvidenceQueries._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：条件证据查询已关闭。

源码：[`src/chronaxis/execution/condition_evidence.py:283`](../../../src/chronaxis/execution/condition_evidence.py#L283)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ConditionEvidenceQueries-_construct"></a>
### `ConditionEvidenceQueries._construct`

仅构造局部结果，不安装槽或结果链。

```python
ConditionEvidenceQueries._construct(cost, slot, time_ns, revision, before, axis)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`revision`|int|是|无|位置或关键字。prepare时取得的状态版本号；结算时必须仍是同一版本，防止用过期准备结果更新状态。|
|`before`|ExpressionResult|是|无|位置或关键字。prepare取得的更新前条件结果，交给新结果对象保存。|
|`axis`|tuple[int, ...] &#124; numpy.ndarray[int64]|是|无|位置或关键字。含本次时刻的一项纳秒轴；与before的计算时刻一致。|

#### 返回说明

PreparedConditionEvidence。

#### 异常说明

构造/返回取消由prepare清理。

源码：[`src/chronaxis/execution/condition_evidence.py:289`](../../../src/chronaxis/execution/condition_evidence.py#L289)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ConditionEvidenceQueries-prepare"></a>
### `ConditionEvidenceQueries.prepare`

在目标组提交前捕获同一时刻旧点并返回有预算预备结果。

```python
ConditionEvidenceQueries.prepare(compiled, time_ns: int) -> PreparedConditionEvidence
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。compiled为登记BOOL对象|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|

#### 返回说明

须complete/close对象；可先为所有条件prepare再统一state.apply。

#### 异常说明

未登记/非BOOL/时间回退/槽占用/预算/取消传播，失败不改变state或旧结果。

本函数直接报告的具体错误：

- `TypeError`：条件证据只接受已编译BOOL条件。
- `ValueError`：条件不属于当前登记对象。
- `TypeError`：条件证据时间需要原生int纳秒。
- `ValueError`：证据时间须域内且晚于已提交组和已完成点。
- `ValueError`：当前条件已有未完成预备结果。

返回类型：[PreparedConditionEvidence](chronaxis.execution.condition_evidence.md#api-PreparedConditionEvidence)。

源码：[`src/chronaxis/execution/condition_evidence.py:297`](../../../src/chronaxis/execution/condition_evidence.py#L297)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ConditionEvidenceQueries-close"></a>
### `ConditionEvidenceQueries.close`

关闭自有预备/完成结果与固定槽，保留调用方上游。

```python
ConditionEvidenceQueries.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子结果/预算关闭错误传播，已释放固定空间的取消最小收尾。

源码：[`src/chronaxis/execution/condition_evidence.py:350`](../../../src/chronaxis/execution/condition_evidence.py#L350)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
