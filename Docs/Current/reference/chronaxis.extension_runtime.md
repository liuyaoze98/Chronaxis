# `chronaxis.extension_runtime`

托管可信回调的后端调用、有限资源、返回形状及取消和关闭责任。

逐点调用只拥有本次工作区；样本归约和时序状态分别活到当前统计范围或
会话结束。共享ResourceBudget只为请求的实现付费，回调可在分配额外内存前
预约并归还自己的金额。宿主代码必须遵守该协议，这不是Python代码沙箱。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[FunctionSpec](chronaxis.extensions.md#api-FunctionSpec)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[ReductionSpec](chronaxis.extensions.md#api-ReductionSpec)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[TransformSpec](chronaxis.extensions.md#api-TransformSpec)

## 对象导航

|对象|用途|
|---|---|
|[`ExtensionResources`](#api-ExtensionResources)|一次调用或状态所有的预算视图；动态费用与固定状态费用分开登记。|
|[`ExtensionResources.__init__`](#api-ExtensionResources-__init__)||
|[`ExtensionResources.reserve`](#api-ExtensionResources-reserve)||
|[`ExtensionResources.release`](#api-ExtensionResources-release)||
|[`ExtensionResources.close`](#api-ExtensionResources-close)|退回全部自有费用。|
|[`_check_scalar`](#api-_check_scalar)|验证回调输出模型。|
|[`_check_values`](#api-_check_values)|验证已选样本的布局和类型。|
|[`point_call`](#api-point_call)|按声明后端运行有限逐点函数，任何退出路径都清理本次工作区。|
|[`_HostedState`](#api-_HostedState)|持有一个工厂状态及其独立资源用量记录；失败后仅接受取消和关闭。|
|[`_HostedState.__init__`](#api-_HostedState-__init__)||
|[`_HostedState._require_open`](#api-_HostedState-_require_open)||
|[`_HostedState.close`](#api-_HostedState-close)|通知取消、关闭状态、归还费用。|
|[`HostedReduction`](#api-HostedReduction)|每个统计范围独享一次样本归约，已结束的状态不会再次消费。|
|[`HostedReduction.__init__`](#api-HostedReduction-__init__)||
|[`HostedReduction.consume`](#api-HostedReduction-consume)||
|[`HostedReduction.merge`](#api-HostedReduction-merge)||
|[`HostedReduction.finalize`](#api-HostedReduction-finalize)||
|[`HostedTransform`](#api-HostedTransform)|只持有此时序请求的状态，按原时基的实际网格递增推进。|
|[`HostedTransform.__init__`](#api-HostedTransform-__init__)||
|[`HostedTransform.advance`](#api-HostedTransform-advance)||
|[`advance_grid`](#api-advance_grid)|将已覆盖区间按正序交给宿主，并保留实际或所选周期的纳秒权重。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .extensions import _BUDGET, FunctionSpec, ReductionSpec, TransformSpec
from .core.numeric import ScalarValue
from .results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .results.errors import ResultClosedError
```

</details>

<a id="api-ExtensionResources"></a>
## `ExtensionResources`

一次调用或状态所有的预算视图；动态费用与固定状态费用分开登记。

```python
ExtensionResources(budget, fixed=0)
```


源码：[`src/chronaxis/extension_runtime.py:14`](../../../src/chronaxis/extension_runtime.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ExtensionResources-__init__"></a>
### `ExtensionResources.__init__`



```python
ExtensionResources.__init__(budget, fixed=0)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget) &#124; None|是|无|位置或关键字。共享RAM账本；未显式提供时使用当前宿主执行上下文，独立调用使用默认配额。|
|`fixed`|int|否|0|位置或关键字。本状态在调用工厂前必须占用的非负字节数，和回调后续动态申请分开记账。|

#### 返回说明

资源所有者。

#### 异常说明

预约失败可清理。

源码：[`src/chronaxis/extension_runtime.py:17`](../../../src/chronaxis/extension_runtime.py#L17)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ExtensionResources-reserve"></a>
### `ExtensionResources.reserve`



```python
ExtensionResources.reserve(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。即将分配的非负字节数，先通过共享额度检查才可分配。|

#### 返回说明

None。

#### 异常说明

预算超额、取消或已关闭。

源码：[`src/chronaxis/extension_runtime.py:31`](../../../src/chronaxis/extension_runtime.py#L31)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ExtensionResources-release"></a>
### `ExtensionResources.release`



```python
ExtensionResources.release(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本回调已付且可以退回的动态字节数，不得动用固定状态费或他人余额。|

#### 返回说明

None。

#### 异常说明

不允许退其他所有者或固定额度。

源码：[`src/chronaxis/extension_runtime.py:37`](../../../src/chronaxis/extension_runtime.py#L37)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ExtensionResources-close"></a>
### `ExtensionResources.close`

退回全部自有费用。

```python
ExtensionResources.close(cancelled=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cancelled`|bool|否|False|位置或关键字。是否因上游取消而进入清理；账本在两种退出下均退还本实例费用。|

#### 返回说明

None。

#### 异常说明

账本异常后可重试。

源码：[`src/chronaxis/extension_runtime.py:45`](../../../src/chronaxis/extension_runtime.py#L45)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_check_scalar"></a>
## `_check_scalar`

验证回调输出模型。

```python
_check_scalar(value, port)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。宿主交回或送入单个参考端口的带有明确类型的标量及有效性。|
|`port`|ValueSpec|是|无|位置或关键字。需要匹配的固定端口约定，特别是该数值的逻辑dtype。|

### 返回说明

原ScalarValue。

### 异常说明

类型错误。

源码：[`src/chronaxis/extension_runtime.py:57`](../../../src/chronaxis/extension_runtime.py#L57)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_check_values"></a>
## `_check_values`

验证已选样本的布局和类型。

```python
_check_values(values, port, backend)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|tuple[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue), ...] &#124; [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。按本次后端打包的已选有效值，标量元组或一维同型数值列。|
|`port`|ValueSpec|是|无|位置或关键字。宿主已声明的输入端口，所有值必须匹配其dtype。|
|`backend`|str|是|无|位置或关键字。实际使用的reference或numpy后端；只能调用该实现，不能静默改用另一后端。|

### 返回说明

个数。

### 异常说明

布局或质量异常。

源码：[`src/chronaxis/extension_runtime.py:64`](../../../src/chronaxis/extension_runtime.py#L64)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-point_call"></a>
## `point_call`

按声明后端运行有限逐点函数，任何退出路径都清理本次工作区。

```python
point_call(spec, backend, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[FunctionSpec](chronaxis.extensions.md#api-FunctionSpec)|是|无|位置或关键字。本次表达式已经绑定的宿主逐点函数描述。|
|`backend`|str|是|无|位置或关键字。实际使用的reference或numpy后端；只能调用该实现，不能静默改用另一后端。|
|`args`|tuple[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue), ...] &#124; tuple[[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray), ...]|是|无|位置或关键字。按固定参数顺序排列的标量或同长数组，任一必需输入未知时传播原因。|

### 返回说明

ScalarValue或NumericArray。

### 异常说明

能力、结构、回调、取消或额度错误原样传播。

源码：[`src/chronaxis/extension_runtime.py:76`](../../../src/chronaxis/extension_runtime.py#L76)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_HostedState"></a>
## `_HostedState`

持有一个工厂状态及其独立资源用量记录；失败后仅接受取消和关闭。

```python
_HostedState(spec, backend, budget, methods)
```


源码：[`src/chronaxis/extension_runtime.py:124`](../../../src/chronaxis/extension_runtime.py#L124)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_HostedState-__init__"></a>
### `_HostedState.__init__`



```python
_HostedState.__init__(spec, backend, budget, methods)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[ReductionSpec](chronaxis.extensions.md#api-ReductionSpec) &#124; [TransformSpec](chronaxis.extensions.md#api-TransformSpec)|是|无|位置或关键字。被消费的宿主状态协议，规定初始状态费用和实际后端工厂。|
|`backend`|str|是|无|位置或关键字。实际使用的reference或numpy后端；只能调用该实现，不能静默改用另一后端。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget) &#124; None|是|无|位置或关键字。共享RAM账本；未显式提供时使用当前宿主执行上下文，独立调用使用默认配额。|
|`methods`|tuple[str, ...]|是|无|位置或关键字。本类状态必须实现的方法名称，工厂返回时逐个核对。|

#### 返回说明

owner。

#### 异常说明

工厂或协议错误。

源码：[`src/chronaxis/extension_runtime.py:127`](../../../src/chronaxis/extension_runtime.py#L127)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_HostedState-_require_open"></a>
### `_HostedState._require_open`



```python
_HostedState._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

拒绝使用已失败或已关闭状态。

源码：[`src/chronaxis/extension_runtime.py:146`](../../../src/chronaxis/extension_runtime.py#L146)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_HostedState-close"></a>
### `_HostedState.close`

通知取消、关闭状态、归还费用。

```python
_HostedState.close(cancelled=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cancelled`|bool|否|False|位置或关键字。上游是否取消；需要时先调用宿主cancel，再关闭状态和自有资源。|

#### 返回说明

None。

#### 异常说明

原清理错误可重试。

源码：[`src/chronaxis/extension_runtime.py:151`](../../../src/chronaxis/extension_runtime.py#L151)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedReduction"></a>
## `HostedReduction`

每个统计范围独享一次样本归约，已结束的状态不会再次消费。

```python
HostedReduction(spec, backend, budget)
```

继承关系：[_HostedState](chronaxis.extension_runtime.md#api-_HostedState)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/extension_runtime.py:168`](../../../src/chronaxis/extension_runtime.py#L168)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedReduction-__init__"></a>
### `HostedReduction.__init__`



```python
HostedReduction.__init__(spec, backend, budget)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[ReductionSpec](chronaxis.extensions.md#api-ReductionSpec)|是|无|位置或关键字。当前样本范围的归约协议，描述端口、可选合并方法和后端工厂。|
|`backend`|str|是|无|位置或关键字。实际使用的reference或numpy后端；只能调用该实现，不能静默改用另一后端。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget) &#124; None|是|无|位置或关键字。共享RAM账本；未显式提供时使用当前宿主执行上下文，独立调用使用默认配额。|

#### 返回说明

owner。

#### 异常说明

工厂、预算或能力错。

源码：[`src/chronaxis/extension_runtime.py:171`](../../../src/chronaxis/extension_runtime.py#L171)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedReduction-consume"></a>
### `HostedReduction.consume`



```python
HostedReduction.consume(values)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|tuple[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue), ...] &#124; [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。按本次后端打包的已选有效值，标量元组或一维同型数值列。|

#### 返回说明

None。

#### 异常说明

错类型、已结束或回调/预算失败。

源码：[`src/chronaxis/extension_runtime.py:178`](../../../src/chronaxis/extension_runtime.py#L178)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedReduction-merge"></a>
### `HostedReduction.merge`



```python
HostedReduction.merge(other)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`other`|[HostedReduction](chronaxis.extension_runtime.md#api-HostedReduction)|是|无|位置或关键字。能够与自身合并的另一个未结算状态，须为同一注册对象和同一后端。|

#### 返回说明

None。

#### 异常说明

不可合并或回调失败。

源码：[`src/chronaxis/extension_runtime.py:190`](../../../src/chronaxis/extension_runtime.py#L190)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedReduction-finalize"></a>
### `HostedReduction.finalize`



```python
HostedReduction.finalize()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

静态声明dtype的最终ScalarValue。

#### 异常说明

错误输出或回调失败。

源码：[`src/chronaxis/extension_runtime.py:205`](../../../src/chronaxis/extension_runtime.py#L205)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedTransform"></a>
## `HostedTransform`

只持有此时序请求的状态，按原时基的实际网格递增推进。

```python
HostedTransform(spec, backend, budget)
```

继承关系：[_HostedState](chronaxis.extension_runtime.md#api-_HostedState)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/extension_runtime.py:217`](../../../src/chronaxis/extension_runtime.py#L217)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedTransform-__init__"></a>
### `HostedTransform.__init__`



```python
HostedTransform.__init__(spec, backend, budget)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[TransformSpec](chronaxis.extensions.md#api-TransformSpec)|是|无|位置或关键字。当前会话的宿主时序协议，含后端工厂、状态费用及允许的历史宽度。|
|`backend`|str|是|无|位置或关键字。实际使用的reference或numpy后端；只能调用该实现，不能静默改用另一后端。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget) &#124; None|是|无|位置或关键字。共享RAM账本；未显式提供时使用当前宿主执行上下文，独立调用使用默认配额。|

#### 返回说明

owner。

#### 异常说明

工厂、预算或能力错。

源码：[`src/chronaxis/extension_runtime.py:220`](../../../src/chronaxis/extension_runtime.py#L220)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedTransform-advance"></a>
### `HostedTransform.advance`



```python
HostedTransform.advance(time_ns, window_ns, values, weights_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。正在推进的实际网格时间戳，单位纳秒，必须比已交付的上一格晚。|
|`window_ns`|int|是|无|位置或关键字。本次网格请求的正窗口宽度，不能超过宿主声明的最大历史宽度。|
|`values`|tuple[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue), ...] &#124; [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。按本次后端打包的已选有效值，标量元组或一维同型数值列。|
|`weights_ns`|tuple[int &#124; Fraction, ...] &#124; numpy.ndarray|是|无|位置或关键字。与每段有效数值对应的正纳秒权重；实际间隔用整数，折算周期可包含分数。|

#### 返回说明

ScalarValue。

#### 异常说明

协议或回调失败。

源码：[`src/chronaxis/extension_runtime.py:227`](../../../src/chronaxis/extension_runtime.py#L227)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-advance_grid"></a>
## `advance_grid`

将已覆盖区间按正序交给宿主，并保留实际或所选周期的纳秒权重。

```python
advance_grid(host, time_ns, window_ns, latest_first, weights, conversion)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`host`|[HostedTransform](chronaxis.extension_runtime.md#api-HostedTransform)|是|无|位置或关键字。当前执行阶段已经创建的宿主时序状态，拥有本会话的预算责任。|
|`time_ns`|int|是|无|位置或关键字。正在推进的实际网格时间戳，单位纳秒，必须比已交付的上一格晚。|
|`window_ns`|int|是|无|位置或关键字。本次网格请求的正窗口宽度，不能超过宿主声明的最大历史宽度。|
|`latest_first`|Sequence[int &#124; float]|是|无|位置或关键字。从窗口右向左读取到的有效原值；交给宿主前恢复为正序。|
|`weights`|Sequence[int &#124; Fraction]|是|无|位置或关键字。与倒序值逐项对应的实际或周期折算纳秒权重。|
|`conversion`|CalculationConversion|是|无|位置或关键字。将宿主本格的自然单位结果换到用户指定输出单位的转换。|

### 返回说明

ScalarValue，保留宿主自身失败质量或部分状态。

### 异常说明

权重/回调或协议异常。

源码：[`src/chronaxis/extension_runtime.py:254`](../../../src/chronaxis/extension_runtime.py#L254)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
