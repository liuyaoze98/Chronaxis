# `chronaxis.execution.record_sample`

记录流只保一份逻辑值；枚举单独保必要整数码，公共来源定义共享引用。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SignalSample](chronaxis.core.models.md#api-SignalSample)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`RecordSample`](#api-RecordSample)|一次规范更新；没有批次副本、原文或普通值的第二份物理表示。|
|[`RecordSample.__post_init__`](#api-RecordSample-__post_init__)|检查必要样本及枚举码含义。|
|[`RecordSample.array_value`](#api-RecordSample-array_value)|按需取得数组值；无效值只返回类型占位。|
|[`RecordSample.original_present`](#api-RecordSample-original_present)|本样本不保存原文。|
|[`RecordSample.original_value`](#api-RecordSample-original_value)|本样本无额外原值。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.models import SourceRef, SignalSample
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D
```

</details>

<a id="api-RecordSample"></a>
## `RecordSample`

一次规范更新；没有批次副本、原文或普通值的第二份物理表示。

```python
class RecordSample
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|信号在当前计划中的简单别名，用于查定义和表达式依赖。|
|`time_ns`|int|是|无|保存此条归一化样本的实际时间，必须是int64范围内整数纳秒，不允许None。|
|`sequence`|int|是|无|当前记录的非负顺序号；同一时刻记录仍有独立序号，不能当作时间戳。|
|`value`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|本条信号的唯一分析值，包含dtype、有效性、质量和枚举域；不另存原值副本。|
|`unit`|str|是|无|物理量或结果单位，如W、J、s；按本接口的单位检查与换算规则使用。|
|`source_ref`|[SourceRef](chronaxis.core.models.md#api-SourceRef)|是|无|当前样本的共享来源字段引用；包含会话、来源和字段，默认不增加逐帧证明副本。|
|`enum_code`|int &#124; None|否|None|枚举的原整数码，配合共享labels恢复文字；普通数值不额外保存第二份值。|

源码：[`src/chronaxis/execution/record_sample.py:8`](../../../src/chronaxis/execution/record_sample.py#L8)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSample-__post_init__"></a>
### `RecordSample.__post_init__`

检查必要样本及枚举码含义。

```python
RecordSample.__post_init__()
```

参数：无显式参数。


#### 参数说明

字段。

#### 返回说明

None。

#### 异常说明

类型/值矛盾。

源码：[`src/chronaxis/execution/record_sample.py:18`](../../../src/chronaxis/execution/record_sample.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSample-array_value"></a>
### `RecordSample.array_value`

按需取得数组值；无效值只返回类型占位。

```python
RecordSample.array_value
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

标量。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_sample.py:32`](../../../src/chronaxis/execution/record_sample.py#L32)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSample-original_present"></a>
### `RecordSample.original_present`

本样本不保存原文。

```python
RecordSample.original_present
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

False。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_sample.py:39`](../../../src/chronaxis/execution/record_sample.py#L39)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSample-original_value"></a>
### `RecordSample.original_value`

本样本无额外原值。

```python
RecordSample.original_value
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_sample.py:44`](../../../src/chronaxis/execution/record_sample.py#L44)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
