# chronaxis.execution.expressions

在有预算的保持快照上调用两个既有独立表达式数值核。

输入为调用方的HoldQueries、实际解码证据绑定和预先编译的固定表达式tuple；
输出须关闭的ExpressionResult，保存同轴结果、实际依赖更新和原样本引用。
owner先申请固定空间，再有预算地遍历元数据及各表达式DAG；查询先按节点、
边、依赖、轴长和ENUM域申请暂存上界，再建立保持/context并求值。
参考逐点调用独立标量核，NumPy调用整列数组核，没有标量回退或重新归一化。
临时HoldResult始终关闭，返回结果独立计持有原样本及输出，不随state更新改变。
本模块不编译任意文本、不读文件、不调度事件/deadline、不关闭调用方资源。
来源关联核对配置及实际描述证据；state样本由调用方从绑定历史推进，本层模型
没有历史SHA字段，不能把这种契约检查声称为逐条样本的防伪认证。
预算是新分析层保守估算，不代表整个进程RSS或恶意修改私有字段的防护。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)、[ExprNode](chronaxis.core.expression.md#api-ExprNode)、[HoldQueries](chronaxis.execution.hold.md#api-HoldQueries)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`ExpressionResult`](#api-ExpressionResult)|持有独立输出和样本预算；关闭后拒绝读取，owner关闭全部自有结果。|
|[`ExpressionResult.__init__`](#api-ExpressionResult-__init__)|保存一次表达式查询的完整输出及其内存申请。|
|[`ExpressionResult._ensure_open`](#api-ExpressionResult-_ensure_open)|拒绝关闭后读取。|
|[`ExpressionResult.closed`](#api-ExpressionResult-closed)|读取关闭状态。|
|[`ExpressionResult.times_ns`](#api-ExpressionResult-times_ns)|读取自有整数ns轴。|
|[`ExpressionResult.rows`](#api-ExpressionResult-rows)|读取参考输出。|
|[`ExpressionResult.arrays`](#api-ExpressionResult-arrays)|读取NumPy输出。|
|[`ExpressionResult.actual_update`](#api-ExpressionResult-actual_update)|读取实际依赖更新OR。|
|[`ExpressionResult.samples`](#api-ExpressionResult-samples)|读取非None原样本，保留dependencies顺序。|
|[`ExpressionResult.binding_identity`](#api-ExpressionResult-binding_identity)|读取实际绑定身份。|
|[`ExpressionResult.compiled_identity`](#api-ExpressionResult-compiled_identity)|读取登记表达式身份。|
|[`ExpressionResult.close`](#api-ExpressionResult-close)|释放本结果的申请及引用，保留调用方的保持查询对象。|
|[`ExpressionResult._discard`](#api-ExpressionResult-_discard)|移除当前结果并丢引用，预算抵销责任留给调用者。|
|[`ExpressionQueries`](#api-ExpressionQueries)|登记固定可执行表达式，按当前保持状态产生独立预算快照。|
|[`ExpressionQueries.__init__`](#api-ExpressionQueries-__init__)|登记一组已编译表达式，并为固定元数据先申请空间。|
|[`ExpressionQueries._charge`](#api-ExpressionQueries-_charge)|逐步申请固定空间。|
|[`ExpressionQueries._walk_metadata`](#api-ExpressionQueries-_walk_metadata)|按对象身份遍历固定元数据，先计账再扩展遍历容器。|
|[`ExpressionQueries._check_contract`](#api-ExpressionQueries-_check_contract)|核对保持上下文与实际证据、投影内完整定义及会话domain，禁止同名借用。|
|[`ExpressionQueries._node_counts`](#api-ExpressionQueries-_node_counts)|记录表达式的唯一节点、全部参数边及枚举域暂存成本。|
|[`ExpressionQueries.closed`](#api-ExpressionQueries-closed)|查看当前对象是否已经关闭。|
|[`ExpressionQueries._ensure_open`](#api-ExpressionQueries-_ensure_open)|拒绝owner/调用方保持/state关闭后新查询。|
|[`ExpressionQueries._prepare`](#api-ExpressionQueries-_prepare)|检查表达式登记关系，并预留本次输出、缓存及原样本的空间。|
|[`ExpressionQueries._check_axis`](#api-ExpressionQueries-_check_axis)|检查规范整数轴非回退及最新状态限制，纯常量同样执行。|
|[`ExpressionQueries._register`](#api-ExpressionQueries-_register)|在完整申请中只构造结果，外层取得对象后负责登记。|
|[`ExpressionQueries._keep_hold`](#api-ExpressionQueries-_keep_hold)|登记临时保持结果，列表增长失败也关闭刚取得的申请。|
|[`ExpressionQueries.query_reference`](#api-ExpressionQueries-query_reference)|在当前状态上逐点执行独立参考保持和标量表达式计算。|
|[`ExpressionQueries.query_numpy`](#api-ExpressionQueries-query_numpy)|在当前状态上执行独立数组保持与整轴表达式计算。|
|[`ExpressionQueries.close`](#api-ExpressionQueries-close)|关闭全部自有查询结果，再释放固定元数据申请。|
|[`ExpressionQueries._finish_close`](#api-ExpressionQueries-_finish_close)|丢弃已释放固定申请的owner引用，不再关闭上游或操作账本。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof
from types import MappingProxyType
from ..core.binding import _identity
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression, ExprNode
from ..core.expression_reference import Evaluation, evaluate_reference
from ..core.expression_numpy import ArrayEvaluation, evaluate_numpy
from ..core.numeric import ScalarValue
from ..core.numeric_numpy import NumericArray
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns
from .bindings import _fingerprint
from .history import _metadata_bytes
from .history_records import estimate_record_bytes
from .hold import HoldQueries
```

</details>

<a id="api-ExpressionResult"></a>
## `ExpressionResult`

持有独立输出和样本预算；关闭后拒绝读取，owner关闭全部自有结果。

数组按普通只读约定提供；外部另存已取得的rows/arrays/samples超过关闭时刻，
须自行负责这些引用的内存，不把释放申请解释为强制销毁外部对象。

```python
ExpressionResult(owner, cost, times, payload, actual, samples, compiled)
```


源码：[`src/chronaxis/execution/expressions.py:37`](../../../src/chronaxis/execution/expressions.py#L37)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-__init__"></a>
### `ExpressionResult.__init__`

保存一次表达式查询的完整输出及其内存申请。

```python
ExpressionResult.__init__(owner, cost, times, payload, actual, samples, compiled)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[ExpressionQueries](chronaxis.execution.expressions.md#api-ExpressionQueries)|是|无|位置或关键字。创建本结果的ExpressionQueries，负责登记和统一关闭。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`times`|tuple[int, ...] &#124; numpy.ndarray[int64]|是|无|位置或关键字。求值使用的纳秒时间轴，与结果及实际更新标记等长。|
|`payload`|tuple[[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation), ...] &#124; [ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)|是|无|位置或关键字。表达式求值结果；参考实现为逐点Evaluation，数组实现为ArrayEvaluation。|
|`actual`|tuple[bool, ...] &#124; numpy.ndarray[bool]|是|无|位置或关键字。各时刻是否确有依赖信号更新；False表示时间点来自有效期等边界，不是新增观测。|
|`samples`|tuple[HistorySample, ...]|是|无|位置或关键字。本次求值保留的原始信号样本，用于说明结果来自哪些输入记录。|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。本查询对象已经登记的编译表达式；结果记录它以保持输入绑定与表达式一致。|

#### 返回说明

新结果；不复制样本，不重新计算表达式。

#### 异常说明

构造失败由调用方释放本次预算，不向owner安装半成品。

源码：[`src/chronaxis/execution/expressions.py:44`](../../../src/chronaxis/execution/expressions.py#L44)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-_ensure_open"></a>
### `ExpressionResult._ensure_open`

拒绝关闭后读取。

```python
ExpressionResult._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：表达式查询结果已关闭。

源码：[`src/chronaxis/execution/expressions.py:65`](../../../src/chronaxis/execution/expressions.py#L65)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-closed"></a>
### `ExpressionResult.closed`

读取关闭状态。

```python
ExpressionResult.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/expressions.py:72`](../../../src/chronaxis/execution/expressions.py#L72)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-times_ns"></a>
### `ExpressionResult.times_ns`

读取自有整数ns轴。

```python
ExpressionResult.times_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple或只读int64列。

#### 异常说明

对象处于下列状态时抛ResultClosedError：表达式查询结果已关闭。

源码：[`src/chronaxis/execution/expressions.py:77`](../../../src/chronaxis/execution/expressions.py#L77)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-rows"></a>
### `ExpressionResult.rows`

读取参考输出。

```python
ExpressionResult.rows: tuple[Evaluation, ...]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Evaluation tuple。

#### 异常说明

关闭或后端类型错误。

本函数直接报告的具体错误：

- `TypeError`：NumPy表达式查询请读取arrays。

返回类型：tuple[[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation), ...]。

源码：[`src/chronaxis/execution/expressions.py:83`](../../../src/chronaxis/execution/expressions.py#L83)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-arrays"></a>
### `ExpressionResult.arrays`

读取NumPy输出。

```python
ExpressionResult.arrays: ArrayEvaluation
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ArrayEvaluation。

#### 异常说明

关闭或后端类型错误。

本函数直接报告的具体错误：

- `TypeError`：参考表达式查询请读取rows。

返回类型：[ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)。

源码：[`src/chronaxis/execution/expressions.py:92`](../../../src/chronaxis/execution/expressions.py#L92)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-actual_update"></a>
### `ExpressionResult.actual_update`

读取实际依赖更新OR。

```python
ExpressionResult.actual_update
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

同轴bool tuple或只读列。

#### 异常说明

关闭。

源码：[`src/chronaxis/execution/expressions.py:101`](../../../src/chronaxis/execution/expressions.py#L101)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-samples"></a>
### `ExpressionResult.samples`

读取非None原样本，保留dependencies顺序。

```python
ExpressionResult.samples
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple。

#### 异常说明

关闭。

源码：[`src/chronaxis/execution/expressions.py:107`](../../../src/chronaxis/execution/expressions.py#L107)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-binding_identity"></a>
### `ExpressionResult.binding_identity`

读取实际绑定身份。

```python
ExpressionResult.binding_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SHA文本。

#### 异常说明

对象处于下列状态时抛ResultClosedError：表达式查询结果已关闭。

源码：[`src/chronaxis/execution/expressions.py:113`](../../../src/chronaxis/execution/expressions.py#L113)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-compiled_identity"></a>
### `ExpressionResult.compiled_identity`

读取登记表达式身份。

```python
ExpressionResult.compiled_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SHA文本。

#### 异常说明

对象处于下列状态时抛ResultClosedError：表达式查询结果已关闭。

源码：[`src/chronaxis/execution/expressions.py:119`](../../../src/chronaxis/execution/expressions.py#L119)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-close"></a>
### `ExpressionResult.close`

释放本结果的申请及引用，保留调用方的保持查询对象。

```python
ExpressionResult.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；重复关闭不会重复抵销申请。

#### 异常说明

预算账本不一致时传播内部错误。

#### 副作用说明

从owner登记表移除自身，丢弃时间轴、输出和原样本引用。
    外部提前取得的数组或行对象仍由外部调用方负责其生命周期。

源码：[`src/chronaxis/execution/expressions.py:124`](../../../src/chronaxis/execution/expressions.py#L124)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionResult-_discard"></a>
### `ExpressionResult._discard`

移除当前结果并丢引用，预算抵销责任留给调用者。

```python
ExpressionResult._discard()
```

参数：无显式参数。


#### 参数说明

无；仅用于已释放结果或尚由查询持有申请的失败结果。

#### 返回说明

None，标记关闭。

#### 异常说明

登记移除错误传播，finally仍关闭避免重复扣账。

源码：[`src/chronaxis/execution/expressions.py:151`](../../../src/chronaxis/execution/expressions.py#L151)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries"></a>
## `ExpressionQueries`

登记固定可执行表达式，按当前保持状态产生独立预算快照。

不持有全量样本；绑定、声明、文本、DAG和ENUM域在固定申请中独立计账。
查询仅接受登记的对象本身，不根据同名或同SHA接收另一个编译对象。
调用方关闭holds/state后拒绝新查询，已返回结果仍可读至自身/本owner关闭。

```python
ExpressionQueries(holds: HoldQueries, bindings: DecodedBindings, expressions: tuple[CompiledExpression, ...])
```


源码：[`src/chronaxis/execution/expressions.py:166`](../../../src/chronaxis/execution/expressions.py#L166)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-__init__"></a>
### `ExpressionQueries.__init__`

登记一组已编译表达式，并为固定元数据先申请空间。

```python
ExpressionQueries.__init__(holds: HoldQueries, bindings: DecodedBindings, expressions: tuple[CompiledExpression, ...])
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`holds`|[HoldQueries](chronaxis.execution.hold.md#api-HoldQueries)|是|无|位置或关键字。调用方的HoldQueries，包含当前状态及已核对的来源范围。|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)|是|无|位置或关键字。DecodedBindings，来自实际历史校核，静态声明不能代替。|
|`expressions`|tuple[[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression), ...]|是|无|位置或关键字。CompiledExpression元组；只接受这些对象本身的后续查询。|

#### 返回说明

新ExpressionQueries；不持有全部历史样本，也不关闭调用方资源。

#### 异常说明

TypeError: 输入类型或元数据类型不符合已定义协议。
    ValueError: 来源、转换、范围或表达式绑定不匹配。
    BudgetExceededError: 固定元数据超预算；关闭本次部分构造并抵销申请。
    原构造异常不被清理失败替换；持续失败时从expression_queries_cleanup_owner恢复close。

#### 处理流程说明

先预留容器，再按对象身份遍历绑定、表达式及标签域，逐步增加申请。
    核对来源证据和同步条件，最后记录每个表达式的节点、边及枚举域成本。

源码：[`src/chronaxis/execution/expressions.py:174`](../../../src/chronaxis/execution/expressions.py#L174)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_charge"></a>
### `ExpressionQueries._charge`

逐步申请固定空间。

```python
ExpressionQueries._charge(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算超限。

先申请再增加本owner计数，失败不改原申请，不启动后续容器增长。

源码：[`src/chronaxis/execution/expressions.py:239`](../../../src/chronaxis/execution/expressions.py#L239)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_walk_metadata"></a>
### `ExpressionQueries._walk_metadata`

按对象身份遍历固定元数据，先计账再扩展遍历容器。

```python
ExpressionQueries._walk_metadata(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。已冻结的表达式、绑定或来源元数据树；递归检查其中保留的描述和标签，不包含信号历史数组。|

#### 返回说明

None；每个不同对象只计一次，DAG共享节点不反复展开。

#### 异常说明

TypeError: 遇到协议之外的类型。
    BudgetExceededError: 本次对象或容器的预留不足。

本函数直接报告的具体错误：

- `TypeError`：表达式查询元数据含未支持类型。

#### 边界说明

表达式树不套用历史JSON的32层限制；不扩大表达式允许的语法。
    预算包含对象浅大小、遍历集合、栈以及后续指纹计算的保守暂存。

源码：[`src/chronaxis/execution/expressions.py:252`](../../../src/chronaxis/execution/expressions.py#L252)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_check_contract"></a>
### `ExpressionQueries._check_contract`

核对保持上下文与实际证据、投影内完整定义及会话domain，禁止同名借用。

```python
ExpressionQueries._check_contract()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为来源/指纹/端点/定义不符。
不重读历史；调用方仍负责从绑定历史推进当前state。

本函数直接报告的具体错误：

- `ValueError`：保持会话/domain与解码运行绑定不同。
- `ValueError`：保持来源/信号集合与解码运行绑定不同。
- `ValueError`：保持完整信号转换与解码运行绑定不同。
- `ValueError`：保持实际描述/范围/EOF与运行证据不同。

源码：[`src/chronaxis/execution/expressions.py:296`](../../../src/chronaxis/execution/expressions.py#L296)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_node_counts"></a>
### `ExpressionQueries._node_counts`

记录表达式的唯一节点、全部参数边及枚举域暂存成本。

```python
ExpressionQueries._node_counts(compiled)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前登记的CompiledExpression对象。|

#### 返回说明

三项元组：唯一节点数、参数边数、枚举相关的暂存字节估算。

#### 异常说明

TypeError: 节点不是ExprNode。
    BudgetExceededError: 遍历节点及容器增长的固定申请不足。

本函数直接报告的具体错误：

- `TypeError`：登记表达式需要带有明确类型的 ExprNode树。

#### 边界说明

用对象身份去重，不对递归节点作结构哈希；不同对象保守分别计账。
    即使查询轴为空，枚举标签构造和验证仍可能需要空间。

源码：[`src/chronaxis/execution/expressions.py:329`](../../../src/chronaxis/execution/expressions.py#L329)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-closed"></a>
### `ExpressionQueries.closed`

查看当前对象是否已经关闭。

```python
ExpressionQueries.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/expressions.py:363`](../../../src/chronaxis/execution/expressions.py#L363)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_ensure_open"></a>
### `ExpressionQueries._ensure_open`

拒绝owner/调用方保持/state关闭后新查询。

```python
ExpressionQueries._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭。

本函数直接报告的具体错误：

- `ResultClosedError`：表达式查询owner已关闭。

源码：[`src/chronaxis/execution/expressions.py:367`](../../../src/chronaxis/execution/expressions.py#L367)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_prepare"></a>
### `ExpressionQueries._prepare`

检查表达式登记关系，并预留本次输出、缓存及原样本的空间。

```python
ExpressionQueries._prepare(compiled, count, point)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。已经编译的表达式，包含运算树、结果类型、单位和依赖信号；须属于本次绑定。|
|`count`|int|是|无|位置或关键字。本次查询轴的点数，必须非负；空查询轴为0，据此预留结果内存。|
|`point`|bool|是|无|位置或关键字。原生bool，是否按点视图解释真实末端。|

#### 返回说明

本次成功申请的字节数；调用方负责将其交给结果或在失败时释放。

#### 异常说明

ResultClosedError: owner、保持对象或状态已关闭。
    TypeError: point不是bool。
    ValueError: 编译对象未登记。
    BudgetExceededError: 无法预留本次查询空间。

#### 边界说明

成本随节点、边、依赖和轴长增长，也覆盖空轴对象头及固定枚举临时量。
    原样本引用单独计账；这里不创建保持列，也不执行数值运算。

源码：[`src/chronaxis/execution/expressions.py:374`](../../../src/chronaxis/execution/expressions.py#L374)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_check_axis"></a>
### `ExpressionQueries._check_axis`

检查规范整数轴非回退及最新状态限制，纯常量同样执行。

```python
ExpressionQueries._check_axis(times)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|np.ndarray|是|无|位置或关键字。times已规范tuple或精确int64列。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为回退。
此处共享时间协议，不共享两个保持/表达式数值核。

本函数直接报告的具体错误：

- `ValueError`：表达式查询轴回退。
- `ValueError`：最新状态不能回溯已经提交的过去。

源码：[`src/chronaxis/execution/expressions.py:408`](../../../src/chronaxis/execution/expressions.py#L408)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_register"></a>
### `ExpressionQueries._register`

在完整申请中只构造结果，外层取得对象后负责登记。

```python
ExpressionQueries._register(cost, times, payload, actual, samples, compiled)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。为这个结果已经申请的内存额度，单位字节；结果关闭时由所属查询对象释放。|
|`times`|tuple[int, ...] &#124; numpy.ndarray[int64]|是|无|位置或关键字。求值使用的纳秒时间轴，与结果及实际更新标记等长。|
|`payload`|tuple[[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation), ...] &#124; [ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)|是|无|位置或关键字。表达式求值结果；参考实现为逐点Evaluation，数组实现为ArrayEvaluation。|
|`actual`|tuple[bool, ...] &#124; numpy.ndarray[bool]|是|无|位置或关键字。各时刻是否确有依赖信号更新；False表示时间点来自有效期等边界，不是新增观测。|
|`samples`|tuple[HistorySample, ...]|是|无|位置或关键字。本次求值保留的原始信号样本，用于说明结果来自哪些输入记录。|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。本查询对象已经登记的编译表达式；结果记录它以保持输入绑定与表达式一致。|

#### 返回说明

ExpressionResult。

#### 异常说明

构造错误由查询抵销，返回取消不遗留登记。

源码：[`src/chronaxis/execution/expressions.py:424`](../../../src/chronaxis/execution/expressions.py#L424)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_keep_hold"></a>
### `ExpressionQueries._keep_hold`

登记临时保持结果，列表增长失败也关闭刚取得的申请。

```python
ExpressionQueries._keep_hold(held, result)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`held`|list[HoldResult]|是|无|位置或关键字。本次查询已经取得的保持结果列表，负责在查询结束或失败时统一关闭。|
|`result`|HoldResult|是|无|位置或关键字。刚取得的保持结果；成功登记后交由held列表管理。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

列表分配错误传播；新结果关闭，之前结果仍由查询finally处理。

源码：[`src/chronaxis/execution/expressions.py:433`](../../../src/chronaxis/execution/expressions.py#L433)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-query_reference"></a>
### `ExpressionQueries.query_reference`

在当前状态上逐点执行独立参考保持和标量表达式计算。

```python
ExpressionQueries.query_reference(compiled, times_ns: tuple[int, ...], *, point=False) -> ExpressionResult
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前owner登记的编译对象。|
|`times_ns`|tuple[int, ...]|是|无|位置或关键字。非递减整数纳秒tuple；不能回溯到已提交状态之前。|
|`point`|bool|否|False|仅关键字。默认False；True按点视图检查真实末端，仍排除有效期右端。|

#### 返回说明

须关闭的ExpressionResult；rows为Evaluation元组，空轴得到空元组。
    actual_update记录真实依赖更新，samples保留原样本及其定位。

#### 异常说明

类型、登记、时间轴、预算或数值错误原样传播；取消也释放本次申请。

本函数直接报告的具体错误：

- `TypeError`：参考表达式轴需要tuple。

#### 处理流程说明

先预留并检查轴，建立各依赖的独立保持结果，再逐点准备输入并求值。
    输出独立持有原样本预算；所有临时保持结果在finally关闭。

返回类型：[ExpressionResult](chronaxis.execution.expressions.md#api-ExpressionResult)。

源码：[`src/chronaxis/execution/expressions.py:446`](../../../src/chronaxis/execution/expressions.py#L446)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-query_numpy"></a>
### `ExpressionQueries.query_numpy`

在当前状态上执行独立数组保持与整轴表达式计算。

```python
ExpressionQueries.query_numpy(compiled, times_ns: np.ndarray, *, point=False) -> ExpressionResult
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前owner登记的编译对象。|
|`times_ns`|np.ndarray|是|无|位置或关键字。一维形状(N,)的INT64 ndarray，时间为整数纳秒且非递减。|
|`point`|bool|否|False|仅关键字。默认False；必须为原生bool，True检查真实末端点视图。|

#### 返回说明

须关闭的ExpressionResult；arrays为ArrayEvaluation，轴及更新掩码只读。
    N=0合法；常量表达式仍显式使用N作为结果长度。

#### 异常说明

数组布局、登记、时间轴、预算、数值或取消错误原样传播。

本函数直接报告的具体错误：

- `TypeError`：NumPy表达式轴需要一维完整int64 ndarray。

#### 处理流程说明

先申请空间，再复制轴、取得各依赖保持列并调用现有独立数组求值核。
    不逐点调用标量数值核；临时保持始终关闭，失败抵销本次申请。

返回类型：[ExpressionResult](chronaxis.execution.expressions.md#api-ExpressionResult)。

源码：[`src/chronaxis/execution/expressions.py:513`](../../../src/chronaxis/execution/expressions.py#L513)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-close"></a>
### `ExpressionQueries.close`

关闭全部自有查询结果，再释放固定元数据申请。

```python
ExpressionQueries.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；重复关闭幂等，部分初始化失败也可调用。

#### 异常说明

预算账本不一致时传播内部错误。

#### 副作用说明

丢弃本owner持有的绑定、表达式、标签及登记引用。
    调用方的holds、state、history和运行绑定lease不由这里关闭。

源码：[`src/chronaxis/execution/expressions.py:579`](../../../src/chronaxis/execution/expressions.py#L579)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExpressionQueries-_finish_close"></a>
### `ExpressionQueries._finish_close`

丢弃已释放固定申请的owner引用，不再关闭上游或操作账本。

```python
ExpressionQueries._finish_close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，owner关闭。

#### 异常说明

无主动异常；只在已释放固定空间的收尾调用。

源码：[`src/chronaxis/execution/expressions.py:610`](../../../src/chronaxis/execution/expressions.py#L610)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
