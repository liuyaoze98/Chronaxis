# `chronaxis.execution.same_frame_integrals`

把同一物理报文的简单数值表达式直接交给现役实际时间积分器。

本对象只保存一个待完成同一时刻组；不构造信号数组、历史或通用最新状态。
读取、DBC投影、范围推进、积分器及结果发布仍由原会话负责。只有首帧前
证明绑定一致的内部调用方使用本入口，运行错误不切换路径或重读输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[D](chronaxis.core.types.md#api-SignalDType)、[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[RecordIntegral](chronaxis.execution.record_integral.md#api-RecordIntegral)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)

## 对象导航

|对象|用途|
|---|---|
|[`direct_integral_inputs`](#api-direct_integral_inputs)|检查直接积分的完整静态边界，不读取DBC或数据。|
|[`SameFrameBinding`](#api-SameFrameBinding)|保存同次DBC证明的共同定位；fd可为None，真实歧义继续由原投影器检查。|
|[`SameFrameBinding.matches`](#api-SameFrameBinding-matches)|匹配已投影更新。|
|[`same_frame_binding`](#api-same_frame_binding)|复用同次DBC字段事实证明唯一共同绑定，不加载文件。|
|[`_NotCompilable`](#api-_NotCompilable)|静态表达式或信号声明不在浮点快速子集内；调用方保留原通用求值。|
|[`_has_shared_composite_nodes`](#api-_has_shared_composite_nodes)|检查闭包递归是否会重复展开同一个复合节点。|
|[`_compile_float_program`](#api-_compile_float_program)|把全FLOAT64的简单表达式编译为闭包，逐项复刻参考核的数值与质量规则。|
|[`_compile_float_program.binary`](#api-_compile_float_program-binary)|计算两侧并合并质量。|
|[`_compile_float_program.unary`](#api-_compile_float_program-unary)|取负值或绝对值。|
|[`_compile_float_program.affine`](#api-_compile_float_program-affine)|执行已编译单位换算。|
|[`_float_normalizer`](#api-_float_normalizer)|FLOAT64信号的快速归一化：普通有限数直接按原顺序计算value*scale+offset。|
|[`_float_normalizer.slow`](#api-_float_normalizer-slow)|复用参考归一化。|
|[`_float_normalizer.normalize`](#api-_float_normalizer-normalize)|直接换算有限原数值，其他输入交参考核。|
|[`_same_value`](#api-_same_value)|沿用同一时刻事实比较。|
|[`_reference_group_values`](#api-_reference_group_values)|共用标量表达式及真实TTL求值，既有单进程与文件工作进程使用相同算法。|
|[`same_frame_evaluator_cost`](#api-same_frame_evaluator_cost)|计算求值器实际预约费用，供首帧前预算选择与构造共用。|
|[`SameFrameEvaluator`](#api-SameFrameEvaluator)|共享归一化、表达式和TTL的有限求值器，不归组、不累计面积。|
|[`SameFrameEvaluator.__init__`](#api-SameFrameEvaluator-__init__)|验证实际定义与已冻结表达式并预约静态及求值空间。|
|[`SameFrameEvaluator.normalize`](#api-SameFrameEvaluator-normalize)|归一化一条已投影报文，保留原质量规则。|
|[`SameFrameEvaluator.evaluate`](#api-SameFrameEvaluator-evaluate)|对一个已解决同一时刻选择的组求值。|
|[`SameFrameEvaluator.close`](#api-SameFrameEvaluator-close)|先解除闭包和声明引用再退款。|
|[`SameFrameIntegrals`](#api-SameFrameIntegrals)|拥有同一时刻选择和表达式上下文；借用积分器，关闭时不代替父会话关闭它们。|
|[`SameFrameIntegrals.__init__`](#api-SameFrameIntegrals-__init__)|检查静态表达式与实定义，预付有界状态，不读取输入。|
|[`SameFrameIntegrals._require_open`](#api-SameFrameIntegrals-_require_open)|失败后仅允许关闭。|
|[`SameFrameIntegrals.consume`](#api-SameFrameIntegrals-consume)|接收一条已投影报文，完整同一时刻组才推进积分。|
|[`SameFrameIntegrals._consume_fast`](#api-SameFrameIntegrals-_consume_fast)|浮点快速路径逐帧接收；检查、同一时刻选择和冲突规则与consume相同。|
|[`SameFrameIntegrals._flush_fast`](#api-SameFrameIntegrals-_flush_fast)|提交完整同一时刻组，取最早有效截止并追加到借用积分器。|
|[`SameFrameIntegrals._flush`](#api-SameFrameIntegrals-_flush)|按已选求值路径提交完整同一时刻值并复用积分器。|
|[`SameFrameIntegrals.finish`](#api-SameFrameIntegrals-finish)|在原读取器确认EOF并关闭后，补算到来源真实末端的保持尾段。|
|[`SameFrameIntegrals.close`](#api-SameFrameIntegrals-close)|释放自有上下文及费用，借用积分器由父会话关闭。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from __future__ import annotations
from dataclasses import dataclass, replace
from math import isfinite, isnan
from typing import Callable, Mapping, Sequence, TYPE_CHECKING
from ..core.binding import SignalDefinition
from ..core.expression import validate_expression
from ..core.expression_reference import _evaluate
from ..core.numeric import _exact_float, normalize_reference, ScalarValue
from ..core.scalar import _scalar_from_validated_fields
from ..core.types import QualityFlag as Q, SignalDType as D
from ..legacy.records import field_from_dict
from ..legacy.updates import LegacyDecodedUpdate
from ..planning.backend_selection import simple_numeric_expression
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from .history import _metadata_bytes
from .static_metadata import static_metadata_bytes
```

</details>

<a id="api-direct_integral_inputs"></a>
## `direct_integral_inputs`

检查直接积分的完整静态边界，不读取DBC或数据。

```python
direct_integral_inputs(plan: AnalysisPlan) -> tuple[SignalDefinition, ...] | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。已经完成静态后端选择的计划；检查直接积分全部条件，不读取DBC或报文。|

### 返回说明

本次必要定义tuple；不适用为None。

### 异常说明

非法带有明确类型的结构，不把运行错误当成选择其他路径的理由。

返回类型：tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...] &#124; None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:37`](../../../src/chronaxis/execution/same_frame_integrals.py#L37)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameBinding"></a>
## `SameFrameBinding`

保存同次DBC证明的共同定位；fd可为None，真实歧义继续由原投影器检查。

```python
class SameFrameBinding
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|当前计划中的来源名称。|
|`channel`|int|是|无|已转换为内部零起序号的通道。|
|`frame_id`|int|是|无|DBC和原配置共同定位的报文编号。|
|`extended`|bool|是|无|同次DBC字段事实已经确定的标准/扩展标记。|
|`fd`|bool &#124; None|是|无|原配置的CAN/FD约束；None保留原投影器的自动识别。|
|`dbc_fd`|bool|是|无|DBC声明的FD属性，沿用经典CAN兼容规则。|

源码：[`src/chronaxis/execution/same_frame_integrals.py:72`](../../../src/chronaxis/execution/same_frame_integrals.py#L72)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameBinding-matches"></a>
### `SameFrameBinding.matches`

匹配已投影更新。

```python
SameFrameBinding.matches(update: LegacyDecodedUpdate) -> bool
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|位置或关键字。原读取器和投影器已经验证的本条解码更新；无效新值也必须交付。|

#### 返回说明

bool。

#### 异常说明

非法内部对象属性错误。

返回类型：bool。

源码：[`src/chronaxis/execution/same_frame_integrals.py:82`](../../../src/chronaxis/execution/same_frame_integrals.py#L82)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-same_frame_binding"></a>
## `same_frame_binding`

复用同次DBC字段事实证明唯一共同绑定，不加载文件。

```python
same_frame_binding(definitions: tuple[SignalDefinition, ...], facts: Sequence[Mapping]) -> SameFrameBinding | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。表达式实际依赖的定义，所有字段应证明属于同一消息。|
|`facts`|Sequence[Mapping[str, object]]|是|无|位置或关键字。同次来源初始化得到的metadata.fields；包含已核定位和DBC帧型，不再次加载文件。|

### 返回说明

共同定位或None（交回普通路径）。

### 异常说明

已有元数据结构损坏；不能将损坏当不支持而吞错。

返回类型：[SameFrameBinding](chronaxis.execution.same_frame_integrals.md#api-SameFrameBinding) &#124; None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:91`](../../../src/chronaxis/execution/same_frame_integrals.py#L91)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_NotCompilable"></a>
## `_NotCompilable`

静态表达式或信号声明不在浮点快速子集内；调用方保留原通用求值。

```python
class _NotCompilable(Exception)
```

继承关系：Exception。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/same_frame_integrals.py:129`](../../../src/chronaxis/execution/same_frame_integrals.py#L129)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_has_shared_composite_nodes"></a>
## `_has_shared_composite_nodes`

检查闭包递归是否会重复展开同一个复合节点。

```python
_has_shared_composite_nodes(roots)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`roots`|Iterable[ExprNode]|是|无|位置或关键字。已校验表达式根节点的可迭代对象。按节点对象身份判断多个表达式是否共享含子节点的复合节点；共享时保留原求值核的结果缓存。|

### 返回说明

存在共享复合子树时为True，否则False。

### 异常说明

非法内部树的属性错误；不改变合法表达式或求值规则。
只遍历一次实际节点；共享派生树继续使用原求值核的单次结果缓存。

源码：[`src/chronaxis/execution/same_frame_integrals.py:138`](../../../src/chronaxis/execution/same_frame_integrals.py#L138)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_compile_float_program"></a>
## `_compile_float_program`

把全FLOAT64的简单表达式编译为闭包，逐项复刻参考核的数值与质量规则。

```python
_compile_float_program(node)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。已校验的表达式根节点或子节点。数值常量须能无损表示为float；其余节点须为FLOAT64且属于支持的简单运算，否则抛出_NotCompilable。|

### 返回说明

callable(context)->(value, quality)。

### 异常说明

_NotCompilable为非FLOAT64节点、非简单算子或编译期常量/系数不能精确表示为float。
规则来源: binary_reference（两侧原因并集、除零DOMAIN_ERROR、非有限NONFINITE）、
    unary_reference、to_float_reference、affine_reference（含纯倍率下溢PRECISION_LOSS）。

源码：[`src/chronaxis/execution/same_frame_integrals.py:158`](../../../src/chronaxis/execution/same_frame_integrals.py#L158)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_compile_float_program-binary"></a>
### `_compile_float_program.binary`

计算两侧并合并质量。

```python
_compile_float_program.binary(context, left=left, right=right, op=op)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|Mapping[str, tuple[float &#124; None, QualityFlag &#124; None]]|是|无|位置或关键字。本次同一时刻组的归一化值映射：键为信号别名，值为(value, quality)；有效值使用有限float和None，无效值使用None及原因标志。|
|`left`|Callable[[Mapping[str, tuple[float &#124; None, QualityFlag &#124; None]]], tuple[float &#124; None, QualityFlag &#124; None]]|否|left|位置或关键字。编译时捕获的左侧子程序；接收同一context，返回数值与质量二元组。通常由闭包默认值传入。|
|`right`|Callable[[Mapping[str, tuple[float &#124; None, QualityFlag &#124; None]]], tuple[float &#124; None, QualityFlag &#124; None]]|否|right|位置或关键字。编译时捕获的右侧子程序；接收同一context，返回数值与质量二元组。通常由闭包默认值传入。|
|`op`|str|否|op|位置或关键字。编译时捕获的二元运算名称：add、sub、mul或div；用于选择计算并保留左右原因合并和除零处理。|

#### 返回说明

有限float与None，或None与原因并集。

#### 异常说明

内部上下文缺键KeyError。

源码：[`src/chronaxis/execution/same_frame_integrals.py:183`](../../../src/chronaxis/execution/same_frame_integrals.py#L183)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_compile_float_program-unary"></a>
### `_compile_float_program.unary`

取负值或绝对值。

```python
_compile_float_program.unary(context, child=child, negate=negate)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|Mapping[str, tuple[float &#124; None, QualityFlag &#124; None]]|是|无|位置或关键字。本次同一时刻组的信号别名到(value, quality)映射；无效输入的原因由子程序原样返回。|
|`child`|Callable[[Mapping[str, tuple[float &#124; None, QualityFlag &#124; None]]], tuple[float &#124; None, QualityFlag &#124; None]]|否|child|位置或关键字。编译时捕获的单个子程序；使用同一context求得待处理的有限float或无效原因。通常不用另传。|
|`negate`|bool|否|negate|位置或关键字。编译时捕获的布尔选择：True执行取负值，False取绝对值；不是用户配置项。|

#### 返回说明

数值质量二元组。

#### 异常说明

内部上下文缺键KeyError。

源码：[`src/chronaxis/execution/same_frame_integrals.py:212`](../../../src/chronaxis/execution/same_frame_integrals.py#L212)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_compile_float_program-affine"></a>
### `_compile_float_program.affine`

执行已编译单位换算。

```python
_compile_float_program.affine(context, child=child, factor=factor, shift=shift)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|Mapping[str, tuple[float &#124; None, QualityFlag &#124; None]]|是|无|位置或关键字。本次同一时刻组的信号别名到(value, quality)映射；先由子程序取值，无效值不参与换算。|
|`child`|Callable[[Mapping[str, tuple[float &#124; None, QualityFlag &#124; None]]], tuple[float &#124; None, QualityFlag &#124; None]]|否|child|位置或关键字。编译时捕获的待换算子程序；接收context，返回数值与质量二元组。通常不用另传。|
|`factor`|float|否|factor|位置或关键字。从单位换算节点取得且已证明可精确转为float的倍率；按number * factor + shift的顺序计算。|
|`shift`|float|否|shift|位置或关键字。从单位换算节点取得且已证明可精确转为float的加法偏移；为0时还检查纯倍率换算是否下溢为0。|

#### 返回说明

数值质量二元组。

#### 异常说明

内部上下文缺键KeyError；数值失败作为质量返回。

源码：[`src/chronaxis/execution/same_frame_integrals.py:230`](../../../src/chronaxis/execution/same_frame_integrals.py#L230)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_float_normalizer"></a>
## `_float_normalizer`

FLOAT64信号的快速归一化：普通有限数直接按原顺序计算value*scale+offset。

```python
_float_normalizer(definition)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。已解析的FLOAT64信号定义；使用其scale、offset、invalid_values和valid_range。普通有限数按原换算顺序处理，其余情况交给参考归一化函数。|

### 返回说明

callable(raw)->(value, quality)。
其余情况（缺失、非有限、超宽整数、整数转float丢精度、显式无效值、结果非有限或超范围、
非数值原值）全部交normalize_reference，结果与原路径相同。

### 异常说明

内部定义结构不合法时保留原TypeError或ValueError。

源码：[`src/chronaxis/execution/same_frame_integrals.py:248`](../../../src/chronaxis/execution/same_frame_integrals.py#L248)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_float_normalizer-slow"></a>
### `_float_normalizer.slow`

复用参考归一化。

```python
_float_normalizer.slow(raw)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|int &#124; float &#124; bool &#124; str &#124; None|是|无|位置或关键字。当前报文该信号的原始解码值；可以是缺失、非有限或显式无效值，由normalize_reference按信号定义判断数值和质量。|

#### 返回说明

数值质量二元组。

#### 异常说明

原值不符合标量协议时保留参考核TypeError。

源码：[`src/chronaxis/execution/same_frame_integrals.py:261`](../../../src/chronaxis/execution/same_frame_integrals.py#L261)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_float_normalizer-normalize"></a>
### `_float_normalizer.normalize`

直接换算有限原数值，其他输入交参考核。

```python
_float_normalizer.normalize(raw)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|int &#124; float &#124; bool &#124; str &#124; None|是|无|位置或关键字。当前报文该信号的原始解码值。有限float及范围内、转float不丢精度的int可直接换算；其他类型、异常值或换算结果交参考归一化处理。|

#### 返回说明

数值质量二元组。

#### 异常说明

不支持的原值结构沿参考核报TypeError。

源码：[`src/chronaxis/execution/same_frame_integrals.py:272`](../../../src/chronaxis/execution/same_frame_integrals.py#L272)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_same_value"></a>
## `_same_value`

沿用同一时刻事实比较。

```python
_same_value(left: ScalarValue, right: ScalarValue) -> bool
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。已归一化的同一时刻左值。|
|`right`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。已归一化的同一时刻右值；按类型、有效性、质量、码和值比较。|

### 返回说明

bool。

### 异常说明

无外部输入转换。

返回类型：bool。

源码：[`src/chronaxis/execution/same_frame_integrals.py:295`](../../../src/chronaxis/execution/same_frame_integrals.py#L295)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_reference_group_values"></a>
## `_reference_group_values`

共用标量表达式及真实TTL求值，既有单进程与文件工作进程使用相同算法。

```python
_reference_group_values(expressions, definitions, time, context)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`expressions`|tuple[[StaticExpression](chronaxis.core.expression.md#api-StaticExpression), ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`definitions`|Mapping[str, [SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)]|是|无|位置或关键字。信号名到实际定义的映射，包含已解析的真实有效期。|
|`time`|int|是|无|位置或关键字。当前同一时刻组的实际纳秒，用于计算有效截止，不使用固定周期改写时间。|
|`context`|Mapping[str, [ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。当前组各依赖信号的规范值，包含有效性与质量；无效新值覆盖旧值。|

### 返回说明

生成器，按计算项顺序产生(ScalarValue, int | None)；第二项是有效截止纳秒，
    没有可表示的有限截止时为None，全部表达式完成后自然结束。

### 异常说明

原表达式求值异常继续传播，不用空值代替错误。

源码：[`src/chronaxis/execution/same_frame_integrals.py:302`](../../../src/chronaxis/execution/same_frame_integrals.py#L302)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-same_frame_evaluator_cost"></a>
## `same_frame_evaluator_cost`

计算求值器实际预约费用，供首帧前预算选择与构造共用。

```python
same_frame_evaluator_cost(definitions, expressions, derived=())
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[[StaticExpression](chronaxis.core.expression.md#api-StaticExpression), ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|位置或关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|

### 返回说明

int，非负的保守预约字节数。

### 异常说明

非法静态模型的原类型或属性错误。

源码：[`src/chronaxis/execution/same_frame_integrals.py:322`](../../../src/chronaxis/execution/same_frame_integrals.py#L322)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameEvaluator"></a>
## `SameFrameEvaluator`

共享归一化、表达式和TTL的有限求值器，不归组、不累计面积。

```python
SameFrameEvaluator(budget, definitions, expressions, binding, session_id, *, derived=())
```


源码：[`src/chronaxis/execution/same_frame_integrals.py:333`](../../../src/chronaxis/execution/same_frame_integrals.py#L333)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameEvaluator-__init__"></a>
### `SameFrameEvaluator.__init__`

验证实际定义与已冻结表达式并预约静态及求值空间。

```python
SameFrameEvaluator.__init__(budget, definitions, expressions, binding, session_id, *, derived=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。与父会话共享的受管理预算；本对象只预约和归还自身持有的费用。|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[[StaticExpression](chronaxis.core.expression.md#api-StaticExpression), ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`binding`|[SameFrameBinding](chronaxis.execution.same_frame_integrals.md#api-SameFrameBinding)|是|无|位置或关键字。首帧前由同次DBC元数据证明的唯一共同报文定位。|
|`session_id`|str|是|无|位置或关键字。本次连续分析的会话名称，文件切换时保持不变。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|

#### 返回说明

None，构造新的有限求值owner。

#### 异常说明

参数类型错误时TypeError；定义、绑定或表达式不一致时ValueError；
    预算不足时BudgetExceededError，清理失败附same_frame_evaluator_cleanup_owner。

源码：[`src/chronaxis/execution/same_frame_integrals.py:336`](../../../src/chronaxis/execution/same_frame_integrals.py#L336)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameEvaluator-normalize"></a>
### `SameFrameEvaluator.normalize`

归一化一条已投影报文，保留原质量规则。

```python
SameFrameEvaluator.normalize(values)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|Mapping[str, object]|是|无|位置或关键字。DBC信号名到本条解码值的映射，必须包含已证明的全部字段；缺值或无效值不沿用上一条。|

#### 返回说明

tuple[ScalarValue, ...]，与definitions的声明顺序一致。

#### 异常说明

已关闭时ResultClosedError，缺少已证明字段时ValueError；原归一化异常继续传播。

源码：[`src/chronaxis/execution/same_frame_integrals.py:396`](../../../src/chronaxis/execution/same_frame_integrals.py#L396)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameEvaluator-evaluate"></a>
### `SameFrameEvaluator.evaluate`

对一个已解决同一时刻选择的组求值。

```python
SameFrameEvaluator.evaluate(time, values)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time`|int|是|无|位置或关键字。已解决同一时刻选择的当前组实际纳秒。|
|`values`|tuple[[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), ...]|是|无|位置或关键字。按definitions顺序排列的归一化信号值，与本组时间对应。|

#### 返回说明

tuple[tuple[ScalarValue, int | None], ...]，与计算项同序；第二项为有效截止纳秒，
    没有可表示的有限截止时为None。

#### 异常说明

已关闭时ResultClosedError；原表达式求值异常继续传播。

源码：[`src/chronaxis/execution/same_frame_integrals.py:420`](../../../src/chronaxis/execution/same_frame_integrals.py#L420)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameEvaluator-close"></a>
### `SameFrameEvaluator.close`

先解除闭包和声明引用再退款。

```python
SameFrameEvaluator.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

预算退款失败可重试。

源码：[`src/chronaxis/execution/same_frame_integrals.py:445`](../../../src/chronaxis/execution/same_frame_integrals.py#L445)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals"></a>
## `SameFrameIntegrals`

拥有同一时刻选择和表达式上下文；借用积分器，关闭时不代替父会话关闭它们。

```python
SameFrameIntegrals(budget: ResourceBudget, definitions: tuple[SignalDefinition, ...], expressions: tuple[StaticExpression, ...], calculations: tuple[RecordIntegral, ...], binding: SameFrameBinding, session_id: str, before_group: Callable[[], None], *, derived: tuple=()) -> None
```


源码：[`src/chronaxis/execution/same_frame_integrals.py:455`](../../../src/chronaxis/execution/same_frame_integrals.py#L455)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals-__init__"></a>
### `SameFrameIntegrals.__init__`

检查静态表达式与实定义，预付有界状态，不读取输入。

```python
SameFrameIntegrals.__init__(budget: ResourceBudget, definitions: tuple[SignalDefinition, ...], expressions: tuple[StaticExpression, ...], calculations: tuple[RecordIntegral, ...], binding: SameFrameBinding, session_id: str, before_group: Callable[[], None], *, derived: tuple=()) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。与父会话共享的受管理预算；构造时预付自有状态。|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。已由来源补齐实际有效期的必要信号定义。|
|`expressions`|tuple[[StaticExpression](chronaxis.core.expression.md#api-StaticExpression), ...]|是|无|位置或关键字。已编译的简单数值表达式，逐项对应calculations。|
|`calculations`|tuple[[RecordIntegral](chronaxis.execution.record_integral.md#api-RecordIntegral), ...]|是|无|位置或关键字。父会话拥有的现役积分器；本对象只交付值，不替代父对象关闭它们。|
|`binding`|[SameFrameBinding](chronaxis.execution.same_frame_integrals.md#api-SameFrameBinding)|是|无|位置或关键字。首帧前已由同次DBC事实证明的共同消息定位。|
|`session_id`|str|是|无|位置或关键字。当前分析会话身份，分卷不重置。|
|`before_group`|Callable[[], None]|是|无|位置或关键字。积分缓冲即将结算时同步刷新真实观测范围；无参数且返回None，发生异常时直接交给调用者处理。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。本计划原有派生声明，供静态校核使用；不额外计算未请求的输出。|

#### 返回说明

None。构造器预付并安装自有状态；调用SameFrameIntegrals(...)取得实例。

#### 异常说明

声明/预算/取消；未返回时附same_frame_cleanup_owner。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:458`](../../../src/chronaxis/execution/same_frame_integrals.py#L458)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals-_require_open"></a>
### `SameFrameIntegrals._require_open`

失败后仅允许关闭。

```python
SameFrameIntegrals._require_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:547`](../../../src/chronaxis/execution/same_frame_integrals.py#L547)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals-consume"></a>
### `SameFrameIntegrals.consume`

接收一条已投影报文，完整同一时刻组才推进积分。

```python
SameFrameIntegrals.consume(update: LegacyDecodedUpdate) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|位置或关键字。原读取器和投影器已经验证的本条解码更新；无效新值也必须交付。|

#### 返回说明

None。

#### 异常说明

身份、同一时刻冲突、预算、计算原错。
无效字段覆盖本次值，不沿用前条。未选择的帧只由原读取器维护观测范围。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:552`](../../../src/chronaxis/execution/same_frame_integrals.py#L552)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals-_consume_fast"></a>
### `SameFrameIntegrals._consume_fast`

浮点快速路径逐帧接收；检查、同一时刻选择和冲突规则与consume相同。

普通有限值使用数值/质量对，特殊输入沿用参考归一化。

```python
SameFrameIntegrals._consume_fast(update: LegacyDecodedUpdate) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|位置或关键字。当前会话的一条LegacyDecodedUpdate。其来源、通道及帧身份用于匹配，time_ns用于实际时间顺序，sequence用于同一时刻选择，values提供全部已证明的同帧字段。|

#### 返回说明

None。

#### 异常说明

身份、同一时刻冲突、预算、计算原错。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:606`](../../../src/chronaxis/execution/same_frame_integrals.py#L606)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals-_flush_fast"></a>
### `SameFrameIntegrals._flush_fast`

提交完整同一时刻组，取最早有效截止并追加到借用积分器。

```python
SameFrameIntegrals._flush_fast() -> None
```

参数：无显式参数。


#### 参数说明

无；读取当前组和已编译程序。

#### 返回说明

None。

#### 异常说明

保留范围回调、积分器和预算原错误，外层_flush统一标记失败。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:658`](../../../src/chronaxis/execution/same_frame_integrals.py#L658)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals-_flush"></a>
### `SameFrameIntegrals._flush`

按已选求值路径提交完整同一时刻值并复用积分器。

```python
SameFrameIntegrals._flush() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原计算/预算错误。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:689`](../../../src/chronaxis/execution/same_frame_integrals.py#L689)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals-finish"></a>
### `SameFrameIntegrals.finish`

在原读取器确认EOF并关闭后，补算到来源真实末端的保持尾段。

```python
SameFrameIntegrals.finish(observed_end: int | None) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`observed_end`|int &#124; None|是|无|位置或关键字。原游标确认EOF后的实际末端纳秒；无观测为None，不用配置终点补造数据。|

#### 返回说明

None。

#### 异常说明

原数值、预算或取消错误。
不替代EOF证明，不把domain.end当采集终点，不虚构固定周期。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:728`](../../../src/chronaxis/execution/same_frame_integrals.py#L728)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-SameFrameIntegrals-close"></a>
### `SameFrameIntegrals.close`

释放自有上下文及费用，借用积分器由父会话关闭。

```python
SameFrameIntegrals.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

释放失败可重试。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:752`](../../../src/chronaxis/execution/same_frame_integrals.py#L752)（行号对应 Chronaxis 0.1.0.dev5 源码）。

## 内部匿名回调


<a id="lambda-174"></a>
### 第174行匿名函数

```python
lambda context: pair
```

|参数|含义|返回/异常|
|---|---|---|
|`context`|参数按上方签名传入；具体调用语义尚待补充。|返回值由上方表达式决定；具体用途和异常尚待核对，不据模板推断。|

<a id="lambda-179"></a>
### 第179行匿名函数

```python
lambda context: context[name]
```

|参数|含义|返回/异常|
|---|---|---|
|`context`|参数按上方签名传入；具体调用语义尚待补充。|返回值由上方表达式决定；具体用途和异常尚待核对，不据模板推断。|
