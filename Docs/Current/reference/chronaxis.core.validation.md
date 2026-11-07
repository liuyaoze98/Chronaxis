# `chronaxis.core.validation`

检查核心模型的文本、简单名称、来源序号和不可变标量。

输入为已经解析的Python对象；文本检查返回原文，序号检查返回精确Python整数，
标量检查只判断类型。原字段可以含点号；标识符须符合ASCII简单名称规则，
不得占用Python关键字或已注册的表达式函数名。本模块不裁剪或改名，不把bool
当整数，不检查样本质量。仅依赖标准库，没有数据读取、日志或会话状态。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`require_text`](#api-require_text)|检查非空来源文本并保留原文本身份，不自动strip或改名。|
|[`require_identifier`](#api-require_identifier)|校验设计9.2的简单标识符，不接受属性路径或隐藏替换。|
|[`require_sequence`](#api-require_sequence)|校验来源内非负精确序号，不设置未经设计要求的64位上限。|
|[`require_scalar`](#api-require_scalar)|限制逻辑样本的值类型，允许保留尚未检查质量的原始值。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from numbers import Integral
```

</details>

<a id="api-require_text"></a>
## `require_text`

检查非空来源文本并保留原文本身份，不自动strip或改名。

```python
require_text(value: str, field: str) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。value (str)为来源名或原字段文本|
|`field`|str|是|无|位置或关键字。field (str)用于错误定位。|

### 返回说明

str；原文本，点号及两端非全空白不被改写。

### 异常说明

TypeError为非文本；ValueError为空或全空白。

返回类型：str。

源码：[`src/chronaxis/core/validation.py:23`](../../../src/chronaxis/core/validation.py#L23)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_identifier"></a>
## `require_identifier`

校验设计9.2的简单标识符，不接受属性路径或隐藏替换。

```python
require_identifier(value: str, field: str) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。value (str)为标识符、来源名或表达式别名|
|`field`|str|是|无|位置或关键字。field (str)用于错误定位。|

### 返回说明

str；原合法标识，大小写保留。

### 异常说明

TypeError为非文本；ValueError为语法、关键字或保留名冲突。

返回类型：str。

源码：[`src/chronaxis/core/validation.py:42`](../../../src/chronaxis/core/validation.py#L42)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_sequence"></a>
## `require_sequence`

校验来源内非负精确序号，不设置未经设计要求的64位上限。

```python
require_sequence(value: int) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。value (Integral)为原来源稳定序号|

### 返回说明

int；精确序号，不使用float或取模。

### 异常说明

TypeError为非整数或bool；ValueError为负序号。

本函数直接报告的具体错误：

- `TypeError`：sequence必须为非布尔整数。
- `ValueError`：sequence必须非负。

返回类型：int。

源码：[`src/chronaxis/core/validation.py:59`](../../../src/chronaxis/core/validation.py#L59)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_scalar"></a>
## `require_scalar`

限制逻辑样本的值类型，允许保留尚未检查质量的原始值。

```python
require_scalar(value: int | float | bool | str | None) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|位置或关键字。原生int、float、bool、str或None；不接受数组、容器和自定义对象。|

### 返回说明

None: 只验证值属于允许的不可变标量类型。有效性、数值范围和声明类型
    由后续模型及数值层检查，None和非有限浮点可以保留为诊断值。

### 异常说明

TypeError: 输入不是允许的原生标量类型。

本函数直接报告的具体错误：

- `TypeError`：逻辑值仅接受原生int/float/bool/str/None。

返回类型：None。

源码：[`src/chronaxis/core/validation.py:80`](../../../src/chronaxis/core/validation.py#L80)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
