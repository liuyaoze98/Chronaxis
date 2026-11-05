# `chronaxis.planning.sequences`

检查请求/响应点事件配对的公开声明，不读取信号或执行配对。

输入是JSON节点或冻结SequencePlan；输出为已验证的计划和联合依赖。
只引用同计划的点规则，拒绝活动、跨时钟、重名和非法延迟。观测条件直接
采用响应规则的条件，用户不需要重复配置另一份观测表达式。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[TimeType](chronaxis.core.types.md#api-TimeType)

## 对象导航

|对象|用途|
|---|---|
|[`SequencePlan`](#api-SequencePlan)|保存一个FIFO配对声明；延迟包含两端，max_pending限制同时等待的请求数。|
|[`SequencePlan.__post_init__`](#api-SequencePlan-__post_init__)|检查独立字段，不读取其他规则。|
|[`sequence_dependencies`](#api-sequence_dependencies)|检查两端引用和时钟，返回两规则实际原信号依赖。|
|[`parse_sequences`](#api-parse_sequences)|解析独立sequences数组，节点ID与规则/窗口/指标共用名称空间。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from .diagnostic_collection import usable_node, collect_node_error
from .checks import PlanValidationError
from .checks import array_at, duration_at, model_at, number_at, object_at, text_at
from .nodes import register_id
from ..core.validation import require_identifier
from ..core.types import TimeType
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-SequencePlan"></a>
## `SequencePlan`

保存一个FIFO配对声明；延迟包含两端，max_pending限制同时等待的请求数。

```python
class SequencePlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence_id`|str|是|无|本组配对的唯一ID，对应JSON的id。|
|`start_rule`|str|是|无|请求点规则ID，对应JSON的start。|
|`response_rule`|str|是|无|响应点规则ID，对应JSON的response。|
|`min_delay_ns`|int|是|无|非负整数纳秒最小延迟，边界包含。|
|`max_delay_ns`|int|是|无|不小于min_delay_ns的整数纳秒最大延迟，边界包含。|
|`max_pending`|int|否|65536|限制本配对规则同时等待响应的请求数量；按可接受的并发请求上限选正整数，默认65536。它不是总请求数或等待时长。|

源码：[`src/chronaxis/planning/sequences.py:19`](../../../src/chronaxis/planning/sequences.py#L19)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SequencePlan-__post_init__"></a>
### `SequencePlan.__post_init__`

检查独立字段，不读取其他规则。

```python
SequencePlan.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为名称或整数边界错误。

本函数直接报告的具体错误：

- `TypeError`：sequence延迟和容量须为原生整数。
- `ValueError`：sequence需要0<=min_delay<=max_delay及正max_pending。

源码：[`src/chronaxis/planning/sequences.py:29`](../../../src/chronaxis/planning/sequences.py#L29)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-sequence_dependencies"></a>
## `sequence_dependencies`

检查两端引用和时钟，返回两规则实际原信号依赖。

```python
sequence_dependencies(item, rules, bindings)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`item`|[SequencePlan](chronaxis.planning.sequences.md#api-SequencePlan)|是|无|位置或关键字。已经解析的请求响应配对配置，包含所引用的请求和响应规则ID。|
|`rules`|tuple[RulePlan, ...]|是|无|位置或关键字。当前计划的规则，按ID查找配对依赖的表达式和信号。|
|`bindings`|DeclarationBindings &#124; DecodedBindings|是|无|位置或关键字。静态声明绑定或运行时实际绑定，用于解析这些信号所属的来源。|

### 返回说明

去重且稳定排序的别名tuple。

### 异常说明

TypeError/ValueError为不支持的引用或时钟。

本函数直接报告的具体错误：

- `TypeError`：sequences需要SequencePlan。

源码：[`src/chronaxis/planning/sequences.py:44`](../../../src/chronaxis/planning/sequences.py#L44)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-parse_sequences"></a>
## `parse_sequences`

解析独立sequences数组，节点ID与规则/窗口/指标共用名称空间。

```python
parse_sequences(value, rules, bindings, ids)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list[dict]|是|无|位置或关键字。请求响应配对配置数组；每项字段和例子见[配对](../sequences.md)。|
|`rules`|tuple[RulePlan, ...]|是|无|位置或关键字。当前计划已经解析的规则，用于核对request和response引用的ID。|
|`bindings`|DeclarationBindings|是|无|位置或关键字。静态信号声明绑定，用于核对配对依赖，不在解析阶段装入样本。|
|`ids`|set[str]|是|无|位置或关键字。本计划已经使用的节点名字集合；解析成功后把新名字加入，遇到重复名字报错。它是本次解析的可变工作集合，不是原始信号值。|

### 返回说明

SequencePlan tuple。

### 异常说明

PlanValidationError保留非法字段或引用的位置。

源码：[`src/chronaxis/planning/sequences.py:75`](../../../src/chronaxis/planning/sequences.py#L75)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
