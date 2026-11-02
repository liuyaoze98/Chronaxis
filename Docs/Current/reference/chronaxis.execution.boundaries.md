# chronaxis.execution.boundaries

从当前保持状态选择下一分析边界，合并同一时刻原因而不推进事件状态。

输入为已经登记实际解码表达式的ExpressionQueries、已处理的整数纳秒游标、
下一完整更新组时刻和当前未确认duration的冻结截止快照。输出须关闭的
BoundaryResult，只保存一个时刻、全部并列原因以及绑定和表达式身份。
查询先预留依赖、规则、来源及字符串空间，再扫描当前TTL、依赖来源EOF与
domain结束；每次重新计算，不积累过期timer，也不保存样本或完整更新组。
原因按固定顺序展示，该顺序不代表消费顺序；本模块不求值表达式、不提交
state、不推进Detector，不据EOF原因决定事件的closed/interrupted/truncated。
调用方负责先处理domain起点；这里不以start-1初始化，因此INT64_MIN可用。
owner只关闭自有结果和固定申请，上游关闭后已有结果仍独立可读。RAM为新
分析层保守计账，不代表整个进程RSS或外部另存引用的强制回收。device_label: home。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[ExpressionQueries](chronaxis.execution.expressions.md#api-ExpressionQueries)、[Interval](chronaxis.core.models.md#api-Interval)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`_require_native_ns`](#api-_require_native_ns)|要求原生int的精确有符号64位纳秒，拒绝隐式类型转换。|
|[`RuleDeadline`](#api-RuleDeadline)|保存调用方当前未确认duration的一份截止快照，不持有Detector。|
|[`RuleDeadline.__post_init__`](#api-RuleDeadline-__post_init__)|校验冻结规则标识和整数截止，不读取候选状态。|
|[`BoundaryReason`](#api-BoundaryReason)|描述选中时刻的一项事实原因，不能直接解释为事件结束状态。|
|[`BoundaryReason.__post_init__`](#api-BoundaryReason-__post_init__)|校验原因种类及对应目标格式，不推断数据有效性。|
|[`_reason_key`](#api-_reason_key)|生成边界原因的显示排序键；这个顺序不改变实际的时间处理顺序。|
|[`BoundaryResult`](#api-BoundaryResult)|持有单一边界的独立预算快照，关闭后拒绝读取内容。|
|[`BoundaryResult.__init__`](#api-BoundaryResult-__init__)|使用已经申请的空间保存当前边界时间及原因，不复制信号样本或重新检查有效期。|
|[`BoundaryResult._ensure_open`](#api-BoundaryResult-_ensure_open)|拒绝关闭后读取，已有结果不再检查上游生命周期。|
|[`BoundaryResult.closed`](#api-BoundaryResult-closed)|读取本结果是否关闭。|
|[`BoundaryResult.time_ns`](#api-BoundaryResult-time_ns)|读取选中的精确纳秒时刻。|
|[`BoundaryResult.reasons`](#api-BoundaryResult-reasons)|读取同一时刻全部并列原因。|
|[`BoundaryResult.binding_identity`](#api-BoundaryResult-binding_identity)|读取查询时实际解码绑定身份。|
|[`BoundaryResult.compiled_identity`](#api-BoundaryResult-compiled_identity)|读取本次登记表达式的完整身份。|
|[`BoundaryResult.close`](#api-BoundaryResult-close)|归还本次查询占用的内存额度，并从创建者的登记中移除本结果；上游资源仍由上游对象管理。|
|[`BoundaryResult._discard`](#api-BoundaryResult-_discard)|无扣账地移除登记并关闭字段，供查询撤销或释放后最小收尾。|
|[`BoundaryQueries`](#api-BoundaryQueries)|借用表达式owner选择下一边界，所有存活结果各自计账。|
|[`BoundaryQueries.__init__`](#api-BoundaryQueries-__init__)|先申请保存查询状态的内存，再关联仍处于打开状态的表达式查询对象。|
|[`BoundaryQueries.closed`](#api-BoundaryQueries-closed)|查看边界查询对象是否已经关闭。|
|[`BoundaryQueries._ensure_open`](#api-BoundaryQueries-_ensure_open)|检查本对象及它借用的上游对象是否仍可用于查询。|
|[`BoundaryQueries._query_cost`](#api-BoundaryQueries-_query_cost)|只读取固定元数据大小，估算扫描、排序和结果独立持有空间。|
|[`BoundaryQueries._register`](#api-BoundaryQueries-_register)|仅构造完整结果，查询外层拿到对象后再登记。|
|[`BoundaryQueries.query_next`](#api-BoundaryQueries-query_next)|选择严格晚于已处理游标的下一边界，保留该时刻全部并列原因。|
|[`BoundaryQueries.close`](#api-BoundaryQueries-close)|关闭全部自有结果与固定申请，保留caller表达式、保持、状态和历史。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from sys import getsizeof
from types import MappingProxyType
from ..core.expression import CompiledExpression
from ..core.models import Interval
from ..core.validation import require_identifier
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns
from .expressions import ExpressionQueries
```

</details>

<a id="api-_require_native_ns"></a>
## `_require_native_ns`

要求原生int的精确有符号64位纳秒，拒绝隐式类型转换。

```python
_require_native_ns(value, field)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。纳秒时间坐标，必须是Python原生整数；bool和NumPy整数标量不作为合法坐标。|
|`field`|str|是|无|位置或关键字。错误定位字段名称。|

### 返回说明

原int坐标，单位为纳秒，不舍入或取模。

### 异常说明

TypeError: 输入不是原生int。
    TimeOverflowError: 坐标超出有符号64位范围。

### 副作用说明

无，不读取状态或申请查询预算。

源码：[`src/chronaxis/execution/boundaries.py:34`](../../../src/chronaxis/execution/boundaries.py#L34)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RuleDeadline"></a>
## `RuleDeadline`

保存调用方当前未确认duration的一份截止快照，不持有Detector。

rule_id是当前规则的简单标识，time_ns是原生int64纳秒的精确截止时刻。
快照不证明某个候选仍存在；调用方须在每次规则或信号更新后重新取得快照。
本模型不相加duration，不生成零门槛timer，也不改变规则配置或检测状态。

```python
class RuleDeadline
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule_id`|str|是|无|当前duration规则标识，不能用表达式文本替代身份。|
|`time_ns`|int|是|无|已检查的原生int64纳秒；查询再检查必须严格晚于游标。|

源码：[`src/chronaxis/execution/boundaries.py:56`](../../../src/chronaxis/execution/boundaries.py#L56)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RuleDeadline-__post_init__"></a>
### `RuleDeadline.__post_init__`

校验冻结规则标识和整数截止，不读取候选状态。

```python
RuleDeadline.__post_init__()
```

参数：无显式参数。


#### 参数说明

无显式参数，读取rule_id与time_ns。

#### 返回说明

None，字段保持原值，不隐式改名或转换时间类型。

#### 异常说明

TypeError: 标识不是原生str或时间不是原生int。
    ValueError: 标识为空、含点号、关键字或保留名称。
    TimeOverflowError: 时间超出int64。

#### 副作用说明

无，不注册timer或打开资源。

源码：[`src/chronaxis/execution/boundaries.py:67`](../../../src/chronaxis/execution/boundaries.py#L67)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryReason"></a>
## `BoundaryReason`

描述选中时刻的一项事实原因，不能直接解释为事件结束状态。

ttl的target为信号别名，duration为规则标识，source_eof为来源标识；
update与domain_end的target固定为空串，不保存更新组或会话对象。
所有字段冻结；相同reason_type的多个目标可同时出现，同来源EOF只输出一次。

```python
class BoundaryReason
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reason_type`|str|是|无|ttl/duration/update/source_eof/domain_end中的一种。|
|`target`|str|是|无|目标简单标识，update与domain_end固定为空串。|

源码：[`src/chronaxis/execution/boundaries.py:90`](../../../src/chronaxis/execution/boundaries.py#L90)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryReason-__post_init__"></a>
### `BoundaryReason.__post_init__`

校验原因种类及对应目标格式，不推断数据有效性。

```python
BoundaryReason.__post_init__()
```

参数：无显式参数。


#### 参数说明

无显式参数，读取reason_type与target。

#### 返回说明

None，保留固定协议中的字符串。

#### 异常说明

TypeError: kind或target不是原生str。
    ValueError: 原因未注册、标识不合法或无目标原因携带非空target。

本函数直接报告的具体错误：

- `TypeError`：边界原因kind/target需要原生str。
- `ValueError`：边界原因kind未注册。
- `ValueError`：update/domain_end的target必须为空串。

#### 副作用说明

无，不求值条件或改变来源状态。

源码：[`src/chronaxis/execution/boundaries.py:101`](../../../src/chronaxis/execution/boundaries.py#L101)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_reason_key"></a>
## `_reason_key`

生成边界原因的显示排序键；这个顺序不改变实际的时间处理顺序。

```python
_reason_key(reason)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reason`|[BoundaryReason](chronaxis.execution.boundaries.md#api-BoundaryReason)|是|无|位置或关键字。已校验BoundaryReason。|

### 返回说明

(种类序号, target)，同种类按保留大小写的目标字典序排列。

### 异常说明

KeyError: 内部原因种类与固定协议不一致。

### 副作用说明

无，只作为当前查询中已预留排序空间的key函数。

源码：[`src/chronaxis/execution/boundaries.py:127`](../../../src/chronaxis/execution/boundaries.py#L127)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult"></a>
## `BoundaryResult`

持有单一边界的独立预算快照，关闭后拒绝读取内容。

time、原因tuple和两个身份不借用上游可变状态；上游资源关闭不清除此结果。
owner登记全部存活结果并负责最终关闭。调用方若另存已取得的原因或身份引用，
须自行负责关闭以后仍保留的外部引用，不把释放预算解释为强制销毁对象。

```python
BoundaryResult(owner, cost, time_ns, reasons, binding_identity, compiled_identity)
```


源码：[`src/chronaxis/execution/boundaries.py:143`](../../../src/chronaxis/execution/boundaries.py#L143)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-__init__"></a>
### `BoundaryResult.__init__`

使用已经申请的空间保存当前边界时间及原因，不复制信号样本或重新检查有效期。

```python
BoundaryResult.__init__(owner, cost, time_ns, reasons, binding_identity, compiled_identity)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BoundaryQueries](chronaxis.execution.boundaries.md#api-BoundaryQueries)|是|无|位置或关键字。产生该边界结果的查询对象，负责登记结果和关闭时归还资源额度。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`reasons`|tuple[[BoundaryReason](chronaxis.execution.boundaries.md#api-BoundaryReason), ...]|是|无|位置或关键字。已校验、已排序的BoundaryReason tuple。 binding_identity、compiled_identity: 当前实际绑定与登记表达式的身份字符串。|
|`binding_identity`|str|是|无|位置或关键字。当前实际信号绑定的身份摘要，用于核对结果仍属于同次绑定。|
|`compiled_identity`|str|是|无|位置或关键字。当前已编译表达式的身份摘要，用于核对结果来自原表达式。|

#### 返回说明

新BoundaryResult，待owner登记后交给调用方。

#### 异常说明

MemoryError: 构造分配失败，由查询完整抵销申请。

#### 副作用说明

只建立结果自有字段；不追加owner登记或改动caller资源。

源码：[`src/chronaxis/execution/boundaries.py:151`](../../../src/chronaxis/execution/boundaries.py#L151)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-_ensure_open"></a>
### `BoundaryResult._ensure_open`

拒绝关闭后读取，已有结果不再检查上游生命周期。

```python
BoundaryResult._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，打开结果可继续读取独立快照。

#### 异常说明

ResultClosedError: 本结果已关闭。

本函数直接报告的具体错误：

- `ResultClosedError`：下一边界结果已关闭。

源码：[`src/chronaxis/execution/boundaries.py:172`](../../../src/chronaxis/execution/boundaries.py#L172)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-closed"></a>
### `BoundaryResult.closed`

读取本结果是否关闭。

```python
BoundaryResult.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool；关闭后仍可检查此状态。

#### 异常说明

无。

源码：[`src/chronaxis/execution/boundaries.py:187`](../../../src/chronaxis/execution/boundaries.py#L187)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-time_ns"></a>
### `BoundaryResult.time_ns`

读取选中的精确纳秒时刻。

```python
BoundaryResult.time_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int，严格晚于查询游标且不超过domain_end。

#### 异常说明

ResultClosedError: 结果已关闭。

源码：[`src/chronaxis/execution/boundaries.py:201`](../../../src/chronaxis/execution/boundaries.py#L201)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-reasons"></a>
### `BoundaryResult.reasons`

读取同一时刻全部并列原因。

```python
BoundaryResult.reasons
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

BoundaryReason tuple，固定种类顺序及target字典序；不表示消费优先级。

#### 异常说明

ResultClosedError: 结果已关闭。

源码：[`src/chronaxis/execution/boundaries.py:216`](../../../src/chronaxis/execution/boundaries.py#L216)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-binding_identity"></a>
### `BoundaryResult.binding_identity`

读取查询时实际解码绑定身份。

```python
BoundaryResult.binding_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SHA字符串，与当前登记表达式所属绑定一致。

#### 异常说明

ResultClosedError: 结果已关闭。

源码：[`src/chronaxis/execution/boundaries.py:231`](../../../src/chronaxis/execution/boundaries.py#L231)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-compiled_identity"></a>
### `BoundaryResult.compiled_identity`

读取本次登记表达式的完整身份。

```python
BoundaryResult.compiled_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SHA字符串，不以同名表达式或同文本替代登记关系。

#### 异常说明

ResultClosedError: 结果已关闭。

源码：[`src/chronaxis/execution/boundaries.py:246`](../../../src/chronaxis/execution/boundaries.py#L246)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-close"></a>
### `BoundaryResult.close`

归还本次查询占用的内存额度，并从创建者的登记中移除本结果；上游资源仍由上游对象管理。

```python
BoundaryResult.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；重复关闭安全。

#### 异常说明

ValueError: 内部预算账本不一致，不能吞掉重复释放或漏计错误。
    KeyboardInterrupt: 未释放资源额度可重试；已释放时最小关闭后传播取消。

#### 副作用说明

清除本结果持有的原因、身份及owner引用。

源码：[`src/chronaxis/execution/boundaries.py:260`](../../../src/chronaxis/execution/boundaries.py#L260)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryResult-_discard"></a>
### `BoundaryResult._discard`

无扣账地移除登记并关闭字段，供查询撤销或释放后最小收尾。

```python
BoundaryResult._discard()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；本方法不再次释放申请。

#### 异常说明

脱离取消传播，finally仍关闭，owner随后只移除残留登记。

源码：[`src/chronaxis/execution/boundaries.py:286`](../../../src/chronaxis/execution/boundaries.py#L286)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryQueries"></a>
## `BoundaryQueries`

借用表达式owner选择下一边界，所有存活结果各自计账。

固定申请只持本owner和登记容器；不复制表达式树、绑定、描述或ENUM域。
表达式owner继续拥有这些元数据，其关闭会丢弃内部引用并拒绝后续查询。
每次查询重新取得当前TTL，来源EOF仅按实际依赖去重；不持累积timer heap。
after必须已处理domain起点且不早于state最后提交时刻，caller负责该前提。

```python
BoundaryQueries(expressions: ExpressionQueries, *, observation=None)
```


源码：[`src/chronaxis/execution/boundaries.py:300`](../../../src/chronaxis/execution/boundaries.py#L300)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryQueries-__init__"></a>
### `BoundaryQueries.__init__`

先申请保存查询状态的内存，再关联仍处于打开状态的表达式查询对象。

```python
BoundaryQueries.__init__(expressions: ExpressionQueries, *, observation=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`expressions`|[ExpressionQueries](chronaxis.execution.expressions.md#api-ExpressionQueries)|是|无|位置或关键字。当前实际解码绑定的ExpressionQueries，不能为空或关闭。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。原请求范围内的实际Interval，None保持原HoldContext.domain。|

#### 返回说明

新BoundaryQueries，未创建查询结果。

#### 异常说明

TypeError: 参数不是ExpressionQueries。
    ResultClosedError: 表达式owner、保持owner或state已关闭。
    BudgetExceededError、MemoryError: 固定申请或容器构造失败，抵销本次申请。
    原异常身份保留；持续清理失败时从boundary_queries_cleanup_owner恢复close。

#### 副作用说明

只拥有固定预算及自有结果登记；不关闭、复制或推进caller资源。

源码：[`src/chronaxis/execution/boundaries.py:309`](../../../src/chronaxis/execution/boundaries.py#L309)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryQueries-closed"></a>
### `BoundaryQueries.closed`

查看边界查询对象是否已经关闭。

```python
BoundaryQueries.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool，独立于caller是否已经关闭。

#### 异常说明

无。

源码：[`src/chronaxis/execution/boundaries.py:368`](../../../src/chronaxis/execution/boundaries.py#L368)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryQueries-_ensure_open"></a>
### `BoundaryQueries._ensure_open`

检查本对象及它借用的上游对象是否仍可用于查询。

```python
BoundaryQueries._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError: 本owner、表达式owner、保持owner或state已关闭。

本函数直接报告的具体错误：

- `ResultClosedError`：下一边界owner已关闭。

源码：[`src/chronaxis/execution/boundaries.py:381`](../../../src/chronaxis/execution/boundaries.py#L381)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryQueries-_query_cost"></a>
### `BoundaryQueries._query_cost`

只读取固定元数据大小，估算扫描、排序和结果独立持有空间。

```python
BoundaryQueries._query_cost(compiled, deadlines)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。本查询已登记的编译表达式；根据其依赖数量估算查询所需内存。|
|`deadlines`|tuple[[RuleDeadline](chronaxis.execution.boundaries.md#api-RuleDeadline), ...]|是|无|位置或关键字。已检查元素类型的RuleDeadline tuple，可含很长的rule_id。|

#### 返回说明

原生int字节数，随依赖、规则、来源上界和字符串长度增长。

#### 异常说明

KeyError: 内部实际绑定不能解析已登记依赖。

#### 边界说明

本步骤不访问当前样本、不调用next_expiry、不创建依赖或来源集合。

源码：[`src/chronaxis/execution/boundaries.py:397`](../../../src/chronaxis/execution/boundaries.py#L397)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryQueries-_register"></a>
### `BoundaryQueries._register`

仅构造完整结果，查询外层拿到对象后再登记。

```python
BoundaryQueries._register(cost, time_ns, reasons, compiled)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`time_ns`|int &#124; None|是|无|位置或关键字。已选出的下一个处理边界的纳秒时刻；没有边界时为None。|
|`reasons`|tuple[[BoundaryReason](chronaxis.execution.boundaries.md#api-BoundaryReason), ...]|是|无|位置或关键字。产生该时刻的全部原因，例如输入更新、有效期到期或持续条件达到门槛；同一时刻原因一起保存。|
|`compiled`|str|是|无|位置或关键字。当前owner登记对象，用于取得两个身份字符串。|

#### 返回说明

BoundaryResult，尚未登记，外层保有局部清理句柄。

#### 异常说明

MemoryError、KeyboardInterrupt: 构造或登记失败/取消，查询清理原申请。

#### 副作用说明

不建立登记归属；不改变caller状态。

源码：[`src/chronaxis/execution/boundaries.py:419`](../../../src/chronaxis/execution/boundaries.py#L419)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryQueries-query_next"></a>
### `BoundaryQueries.query_next`

选择严格晚于已处理游标的下一边界，保留该时刻全部并列原因。

```python
BoundaryQueries.query_next(compiled, *, after_ns: int, next_group_ns: int | None=None, duration_deadlines: tuple[RuleDeadline, ...]=()) -> BoundaryResult | None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前表达式owner登记的CompiledExpression原对象。|
|`after_ns`|int|是|无|仅关键字。原生int64纳秒，位于闭区间domain内且不早于state最后提交时刻。|
|`next_group_ns`|int &#124; None|否|None|仅关键字。下一完整更新组的原生int64时刻或None，必须严格晚于after。|
|`duration_deadlines`|tuple[[RuleDeadline](chronaxis.execution.boundaries.md#api-RuleDeadline), ...]|否|()|仅关键字。RuleDeadline tuple；rule_id唯一，每个截止严格晚于after。|

#### 返回说明

须close的BoundaryResult；after等于domain_end时返回None。
    合法未来更新或截止超过domain_end时忽略，domain_end自身仍为候选。

#### 异常说明

TypeError、TimeOverflowError: 计划、tuple、快照或时间类型/范围错误。
    ValueError: 未登记对象、域外或回溯游标、过期截止、重复rule_id。
    ResultClosedError: 本owner或借用上游关闭。
    BudgetExceededError、MemoryError、KeyboardInterrupt: 预留、扫描、构造或取消错误。

#### 副作用说明

只登记本次结果；失败或取消抵销申请，不提交state或推进Detector。

#### 边界说明

起点初始化由caller完成，不使用start-1；原因排序不决定结束分类。
    after到域末时仍完整校验入参，不用结束状态掩盖错误截止或重复规则。

返回类型：[BoundaryResult](chronaxis.execution.boundaries.md#api-BoundaryResult) &#124; None。

源码：[`src/chronaxis/execution/boundaries.py:436`](../../../src/chronaxis/execution/boundaries.py#L436)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BoundaryQueries-close"></a>
### `BoundaryQueries.close`

关闭全部自有结果与固定申请，保留caller表达式、保持、状态和历史。

```python
BoundaryQueries.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；重复关闭安全，也允许构造中途失败时收尾。

#### 异常说明

ValueError: 内部账本金额不一致，不能静默绕过。
    KeyboardInterrupt: 子结果/固定申请未释放可重试，已释放不会再次扣账。

#### 副作用说明

逐项关闭自有结果并丢弃caller引用，不打开或删除文件。

源码：[`src/chronaxis/execution/boundaries.py:538`](../../../src/chronaxis/execution/boundaries.py#L538)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
