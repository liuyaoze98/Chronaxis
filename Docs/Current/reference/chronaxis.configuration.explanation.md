# `chronaxis.configuration.explanation`

把已验证的分析声明讲成人可阅读的步骤；不加载来源、不展开运行时数据。

文本与JSON报告使用同一计划和能力报告。这里仅翻译已知术语、格式化精确时间，
并从原始声明区分显式设置与默认设置，不建立另一套配置默认值或执行规则。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`time_text`](#api-time_text)|无损显示纳秒时长。|
|[`_declared`](#api-_declared)|检查原声明是否包含字段。|
|[`_setting`](#api-_setting)|显示实际生效值及其来源。|
|[`_scope`](#api-_scope)|解释计算/输出范围。|
|[`_validation_lines`](#api-_validation_lines)|保留报告中全部错误与限制。|
|[`validation_text`](#api-validation_text)|生成简短校验说明。|
|[`_rule_lines`](#api-_rule_lines)|说明事件、窗口和请求响应的有效声明。|
|[`explanation_text`](#api-explanation_text)|按输入→信号→事件→计算→输出说明同一有效计划。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
```

</details>

<a id="api-time_text"></a>
## `time_text`

无损显示纳秒时长。

```python
time_text(nanoseconds)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`nanoseconds`|int|是|无|位置或关键字。整数纳秒时长；输出时不经浮点换算，避免大整数精度丢失。|

### 返回说明

带单位文本。

### 异常说明

无。

源码：[`src/chronaxis/configuration/explanation.py:25`](../../../src/chronaxis/configuration/explanation.py#L25)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_declared"></a>
## `_declared`

检查原声明是否包含字段。

```python
_declared(plan, *parts)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已经静态校验的分析计划；用于提取实际声明、规则和默认值，不执行分析。|
|`parts`|str 或 int 的可变参数|否|()|可变位置。从配置根开始依次给出的键或下标；用于区分显式填写与省略的字段。|

### 返回说明

bool。

### 异常说明

无；不取文件默认值。

源码：[`src/chronaxis/configuration/explanation.py:35`](../../../src/chronaxis/configuration/explanation.py#L35)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_setting"></a>
## `_setting`

显示实际生效值及其来源。

```python
_setting(plan, label, value, *parts)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已经静态校验的分析计划；用于提取实际声明、规则和默认值，不执行分析。|
|`label`|str|是|无|位置或关键字。显示给读者的设置名称，例如结果表格式；不用于读取配置键。|
|`value`|JSON原生值|是|无|位置或关键字。当前待检查或显示的单个值；诊断不会展开打印整个大容器。|
|`parts`|str 或 int 的可变参数|否|()|可变位置。从配置根开始依次给出的键或下标；用于区分显式填写与省略的字段。|

### 返回说明

文本。

### 异常说明

无。

源码：[`src/chronaxis/configuration/explanation.py:48`](../../../src/chronaxis/configuration/explanation.py#L48)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_scope"></a>
## `_scope`

解释计算/输出范围。

```python
_scope(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。session、event:规则ID或segment:窗口ID的统计范围文本，生成对应中文说明。|

### 返回说明

中文及具体ID。

### 异常说明

无。

源码：[`src/chronaxis/configuration/explanation.py:56`](../../../src/chronaxis/configuration/explanation.py#L56)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_validation_lines"></a>
## `_validation_lines`

保留报告中全部错误与限制。

```python
_validation_lines(validation)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`validation`|ValidationReport|是|无|位置或关键字。当前计划的静态检查报告，包括错误、警告及执行能力；不代表已读入真实数据。|

### 返回说明

文本行。

### 异常说明

无。

源码：[`src/chronaxis/configuration/explanation.py:64`](../../../src/chronaxis/configuration/explanation.py#L64)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-validation_text"></a>
## `validation_text`

生成简短校验说明。

```python
validation_text(plan, validation)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已经静态校验的分析计划；用于提取实际声明、规则和默认值，不执行分析。|
|`validation`|ValidationReport|是|无|位置或关键字。当前计划的静态检查报告，包括错误、警告及执行能力；不代表已读入真实数据。|

### 返回说明

多行文本。

### 异常说明

无。

源码：[`src/chronaxis/configuration/explanation.py:74`](../../../src/chronaxis/configuration/explanation.py#L74)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_rule_lines"></a>
## `_rule_lines`

说明事件、窗口和请求响应的有效声明。

```python
_rule_lines(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已经静态校验的分析计划；用于提取实际声明、规则和默认值，不执行分析。|

### 返回说明

文本行。

### 异常说明

内部模型不符。

源码：[`src/chronaxis/configuration/explanation.py:82`](../../../src/chronaxis/configuration/explanation.py#L82)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-explanation_text"></a>
## `explanation_text`

按输入→信号→事件→计算→输出说明同一有效计划。

```python
explanation_text(plan, report, *, backend_override=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已经静态校验的分析计划；用于提取实际声明、规则和默认值，不执行分析。|
|`report`|ExplainReport|是|无|位置或关键字。计划依赖、有效间隔、后端及静态检查结果，用于生成说明文字。|
|`backend_override`|str 或 None|否|None|仅关键字。本次显示采用的后端覆盖；reference或numpy，None沿用计划中的设置，不修改文件。|

### 返回说明

多行文本。

### 异常说明

内部接口不符传播，不用默认文案掩盖未实现类型；无输入I/O。

源码：[`src/chronaxis/configuration/explanation.py:121`](../../../src/chronaxis/configuration/explanation.py#L121)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
