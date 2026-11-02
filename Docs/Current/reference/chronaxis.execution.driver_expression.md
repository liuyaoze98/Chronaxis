# chronaxis.execution.driver_expression

从已提交的同一时刻信号状态取得所选驱动的数值或BOOL表达式，不保存输入历史。

输入是经过来源校验、归一化和同一时刻政策处理的LatestSignalState，以及静态
表达式声明；每个驱动更新最多返回一个(time, value, valid_until)计算点。
按实际更新时间判断valid_for，复用既有独立参考/NumPy算术内核；固定周期
不进入此组件。最新值归state持有，临时求值空间在共享预算中预付。
这是新按需执行的内部接点，不生成CompiledExpression或伪造EOF/绑定证据，
不改变公开表达式入口拒绝StaticExpression的契约。来源读取/同一时刻归组由调用方负责。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)、[LatestSignalState](chronaxis.execution.state.md#api-LatestSignalState)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)

## 对象导航

|对象|用途|
|---|---|
|[`DriverExpression`](#api-DriverExpression)|借用最新状态，持有已核实的表达式树与依赖；不跨组缓存计算值。|
|[`DriverExpression.__init__`](#api-DriverExpression-__init__)|核对声明与实际状态映射，预付树和依赖引用费用。|
|[`DriverExpression._require_open`](#api-DriverExpression-_require_open)|拒绝失败或关闭后的求值。|
|[`DriverExpression._context_at`](#api-DriverExpression-_context_at)|读取当前持有值在实际时刻的有效性。|
|[`DriverExpression._evaluate_values`](#api-DriverExpression-_evaluate_values)|复用选定后端的独立数值核。|
|[`DriverExpression.evaluate`](#api-DriverExpression-evaluate)|仅在最新完整组包含驱动更新时求值一次；其他组仅由state保存最新值。|
|[`DriverExpression.invalidated_at`](#api-DriverExpression-invalidated_at)|当前已消费组使数值依赖失效的实际时刻。|
|[`DriverExpression.evaluate_at`](#api-DriverExpression-evaluate_at)|在当前最新状态上查询实际边界，供规则的TTL和等待调度使用。|
|[`DriverExpression.close`](#api-DriverExpression-close)|释放自有树/费用，借用state保持原所有者负责。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..core import expression_reference, expression_numpy
from ..core.expression import StaticExpression, validate_expression
from ..core.declarations import DeclarationBindings
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D, QualityFlag as Q
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns
from .history import _metadata_bytes
from .calculation_values import scalar_from_column
from .state import LatestSignalState
```

</details>

<a id="api-DriverExpression"></a>
## `DriverExpression`

借用最新状态，持有已核实的表达式树与依赖；不跨组缓存计算值。

```python
DriverExpression(static, state, driver, *, backend='numpy', derived=(), observation_ends=None)
```


源码：[`src/chronaxis/execution/driver_expression.py:25`](../../../src/chronaxis/execution/driver_expression.py#L25)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DriverExpression-__init__"></a>
### `DriverExpression.__init__`

核对声明与实际状态映射，预付树和依赖引用费用。

```python
DriverExpression.__init__(static, state, driver, *, backend='numpy', derived=(), observation_ends=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`static`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)|是|无|位置或关键字。已经完成类型、单位和依赖检查的静态表达式声明；在当前信号状态上求值，不是完整输入历史编译对象。|
|`state`|[LatestSignalState](chronaxis.execution.state.md#api-LatestSignalState)|是|无|位置或关键字。当前会话各依赖信号的最新有效状态；过期按实际时间判断，不能跨独立任务继承。|
|`driver`|str &#124; None|是|无|位置或关键字。推进该计算的原信号别名；None按实际更新组求值，固定/DBC模式使用已解析的唯一别名。|
|`backend`|str|否|'numpy'|仅关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。按依赖顺序排列的派生信号定义，用于在当前组求值，不缓存上次任务的值。|
|`observation_ends`|Mapping[str, int]|否|None|仅关键字。已知来源EOF实际纳秒时刻；尚未结束的来源没有条目。|

#### 返回说明

新owner。

#### 异常说明

声明不一致、非数值/BOOL表达式、预算或取消错误；
    构造清理失败提供driver_expression_cleanup_owner重试句柄。

源码：[`src/chronaxis/execution/driver_expression.py:28`](../../../src/chronaxis/execution/driver_expression.py#L28)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DriverExpression-_require_open"></a>
### `DriverExpression._require_open`

拒绝失败或关闭后的求值。

```python
DriverExpression._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/driver_expression.py:89`](../../../src/chronaxis/execution/driver_expression.py#L89)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DriverExpression-_context_at"></a>
### `DriverExpression._context_at`

读取当前持有值在实际时刻的有效性。

```python
DriverExpression._context_at(time_ns, *, continuous=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|
|`continuous`|bool|否|False|仅关键字。是否按连续持有状态求值；False用于真实记录更新，不额外把边界当作新样本。|

#### 返回说明

context及未来到期点。

#### 异常说明

模型/分配错误。

源码：[`src/chronaxis/execution/driver_expression.py:94`](../../../src/chronaxis/execution/driver_expression.py#L94)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DriverExpression-_evaluate_values"></a>
### `DriverExpression._evaluate_values`

复用选定后端的独立数值核。

```python
DriverExpression._evaluate_values(context)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|Mapping[str, [ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。当前时刻各依赖别名的值与有效状态；缺失和过期必须保持无效。|

#### 返回说明

ScalarValue。

#### 异常说明

原计算/分配错误。

源码：[`src/chronaxis/execution/driver_expression.py:120`](../../../src/chronaxis/execution/driver_expression.py#L120)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DriverExpression-evaluate"></a>
### `DriverExpression.evaluate`

仅在最新完整组包含驱动更新时求值一次；其他组仅由state保存最新值。

```python
DriverExpression.evaluate()
```

参数：无显式参数。


#### 参数说明

无，读取借用state的当前完整组。

#### 返回说明

None或(time_ns, ScalarValue,
    实际有效截止)；None截止表示所有依赖在int64时间域内没有未来过期点。

#### 异常说明

跳过未消费组、预算、计算结构或取消错误；失败后不再交付结果。

#### 约束说明

必须在每次完整组提交后调用，不能用最新状态补算丢掉的历史组。

源码：[`src/chronaxis/execution/driver_expression.py:138`](../../../src/chronaxis/execution/driver_expression.py#L138)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DriverExpression-invalidated_at"></a>
### `DriverExpression.invalidated_at`

当前已消费组使数值依赖失效的实际时刻。

```python
DriverExpression.invalidated_at
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int或None。

#### 异常说明

关闭/失败。

源码：[`src/chronaxis/execution/driver_expression.py:218`](../../../src/chronaxis/execution/driver_expression.py#L218)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DriverExpression-evaluate_at"></a>
### `DriverExpression.evaluate_at`

在当前最新状态上查询实际边界，供规则的TTL和等待调度使用。

```python
DriverExpression.evaluate_at(time_ns, *, continuous=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int &#124; None|是|无|位置或关键字。指定查询信号表达式的实际时刻，传整数纳秒且不得早于已提交时间组；不接受None，不产生新驱动点。|
|`continuous`|bool|否|True|仅关键字。是否按连续持有状态求值；False用于真实记录更新，不额外把边界当作新样本。|

#### 返回说明

(ScalarValue, 下一次可能改变已知结果的实际截止或None)。不提交组、
    不改变驱动游标，不制造报文，也不保存查询轨迹。

#### 异常说明

时间/状态/预算/数值错误；失败后仅可关闭，费用释放失败仍保原责任。

源码：[`src/chronaxis/execution/driver_expression.py:223`](../../../src/chronaxis/execution/driver_expression.py#L223)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DriverExpression-close"></a>
### `DriverExpression.close`

释放自有树/费用，借用state保持原所有者负责。

```python
DriverExpression.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

释放失败可重试。

源码：[`src/chronaxis/execution/driver_expression.py:266`](../../../src/chronaxis/execution/driver_expression.py#L266)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
