# chronaxis.migration.legacy_sum

静态迁移ChrgInfo当前消息公式，保原参数顺序、缺值门控和分桶定位。

输入为已按旧大小写/分号口径解析的INI及显式mapping；输出仅追加独立分析
字典的message_calculations与有限报告。period/factor沿旧float文本解析；只有global
在float文本失败后通过受限AST原序计算。公式只替换Name；
不执行eval、旧ConfigManager、DBC、reader或数据扫描。旧完整触发/缓存不支持。
正负分桶复用已接入raw_decoded-v1，不改贡献符号、周期、单位或普通数值核。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ExpressionParameter](chronaxis.core.message_binding.md#api-ExpressionParameter)、[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)

## 对象导航

|对象|用途|
|---|---|
|[`_reject`](#api-_reject)|拒绝原字段并保真实位置；|
|[`_targets`](#api-_targets)|为一原字段保每个真实目标，不把多路径拼成无法解析的字符串。|
|[`_constant`](#api-_constant)|保旧float优先口径，只有global允许有界纯数字AST回退。|
|[`_constant.evaluate`](#api-_constant-evaluate)|按原树逐节点算数；|
|[`_formula`](#api-_formula)|保数值公式顺序并精确替换signal Name，参数不改名。|
|[`_io_fields`](#api-_io_fields)|保旧I/O及完整替代政策；|
|[`convert_legacy_sum`](#api-convert_legacy_sum)|整份生成普通或正负legacy指标，保字段、参数及输出标签的逐项关系。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from math import isfinite
from ..core.message_binding import ExpressionParameter
from ..legacy.records import PROFILE_ID, field_from_dict
from .ini import field_path, locate, mark, problem
from .models import LegacyImportIssue
```

</details>

<a id="api-_reject"></a>
## `_reject`

拒绝原字段并保真实位置；

```python
_reject(fields, headers, section, key, code, message)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`headers`|dict[str, int]|是|无|位置或关键字。旧INI段名到所在行号的对应表，用来把错误指向原文件位置。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|
|`code`|str|是|无|位置或关键字。本次转换失败的问题代码，写入报告供调用方识别具体失败类别。|
|`message`|str|是|无|位置或关键字。面向使用者的问题或迁移差异说明文本。|

### 返回说明

无；

### 异常说明

ImportProblem。

源码：[`src/chronaxis/migration/legacy_sum.py:20`](../../../src/chronaxis/migration/legacy_sum.py#L20)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_targets"></a>
## `_targets`

为一原字段保每个真实目标，不把多路径拼成无法解析的字符串。

```python
_targets(fields, section, key, targets, message='保原字段并显式映射')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|
|`targets`|list|是|无|位置或关键字。fields局部报告列表、原位置、targets目标tuple和说明。|
|`message`|str|否|'保原字段并显式映射'|位置或关键字。面向使用者的问题或迁移差异说明文本。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

无；原字段缺失由必填校验处理。相同global可映射多个section参数。

源码：[`src/chronaxis/migration/legacy_sum.py:28`](../../../src/chronaxis/migration/legacy_sum.py#L28)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_constant"></a>
## `_constant`

保旧float优先口径，只有global允许有界纯数字AST回退。

```python
_constant(text, fields, headers, section, key, *, float_only=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。待检查的原文本；JSON常量入口拒绝NaN/Infinity，其余函数按白名单解析常量或公式。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`headers`|dict[str, int]|是|无|位置或关键字。旧INI段名到所在行号的对应表，用来把错误指向原文件位置。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|
|`float_only`|bool|否|False|仅关键字。float_only限定旧period/factor。|

### 返回说明

原生int/float；
不重排结合顺序或先舍入，坏factor不静默沿旧fallback=1.0。

### 异常说明

ImportProblem为非法、过大、非有限或除零；资源/取消原错传播。

本函数直接报告的具体错误：

- `ValueError`：参数必须能精确表示为有限FLOAT64。

源码：[`src/chronaxis/migration/legacy_sum.py:50`](../../../src/chronaxis/migration/legacy_sum.py#L50)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_constant-evaluate"></a>
### `_constant.evaluate`

按原树逐节点算数；

```python
_constant.evaluate(node, depth=0)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.AST|是|无|位置或关键字。常量表达式中当前待求值的语法节点；检查节点是否属于支持的常量和运算。|
|`depth`|int|否|0|位置或关键字。当前AST递归深度，用于拒绝过深的常量表达式。|

#### 返回说明

数值；

#### 异常说明

ValueError/算术错误。

本函数直接报告的具体错误：

- `ValueError`：常量AST超过32层。
- `ValueError`：常量中间值非有限或整数过大。
- `ValueError`：常量仅允许有限数字、括号、正负及加减乘除。
- `ValueError`：常量中间整数超过4096位。

源码：[`src/chronaxis/migration/legacy_sum.py:78`](../../../src/chronaxis/migration/legacy_sum.py#L78)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_formula"></a>
## `_formula`

保数值公式顺序并精确替换signal Name，参数不改名。

```python
_formula(text, signals, parameters, aliases, fields, headers, section)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。待检查的原文本；JSON常量入口拒绝NaN/Infinity，其余函数按白名单解析常量或公式。|
|`signals`|dict[str, str]|是|无|位置或关键字。旧配置中的信号名到字段表达式的映射；本函数检查键名被公式引用，并按aliases替换这些名称。|
|`parameters`|dict[str, int &#124; float]|是|无|位置或关键字。旧公式常量参数名到已读取数值的映射；这些名称不通过aliases改名。|
|`aliases`|Mapping[str, str]|是|无|位置或关键字。旧表达式名称到新信号别名的映射，例如{"Voltage": "u"}；表达式中的Voltage据此改成u。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`headers`|dict[str, int]|是|无|位置或关键字。旧INI段名到所在行号的对应表，用来把错误指向原文件位置。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|

### 返回说明

新DSL文本。

### 异常说明

ImportProblem为危险AST、未知名、缺alias或未使用signal门控。

源码：[`src/chronaxis/migration/legacy_sum.py:115`](../../../src/chronaxis/migration/legacy_sum.py#L115)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_io_fields"></a>
## `_io_fields`

保旧I/O及完整替代政策；

```python
_io_fields(parser, fields, headers, issues)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`parser`|configparser.ConfigParser|是|无|位置或关键字。已经解析的旧INI，用它读取原段落和键值；不在这里重新读取文件。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`headers`|dict[str, int]|是|无|位置或关键字。旧INI段名到所在行号的对应表，用来把错误指向原文件位置。|
|`issues`|list[[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)]|是|无|位置或关键字。接收本次转换的差异、警告和拒绝原因；调用者随后将它们写入迁移报告。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

ImportProblem。

源码：[`src/chronaxis/migration/legacy_sum.py:147`](../../../src/chronaxis/migration/legacy_sum.py#L147)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-convert_legacy_sum"></a>
## `convert_legacy_sum`

整份生成普通或正负legacy指标，保字段、参数及输出标签的逐项关系。

```python
convert_legacy_sum(parser, headers, mapping, analysis, fields, issues)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`parser`|configparser.ConfigParser|是|无|位置或关键字。已经解析的旧INI，用它读取原段落和键值；不在这里重新读取文件。|
|`headers`|dict[str, int]|是|无|位置或关键字。旧INI段名到所在行号的对应表，用来把错误指向原文件位置。|
|`mapping`|dict|是|无|位置或关键字。INI映射对象，必填mapping_version和analysis。path_base、io_policy采用固定默认值；aliases可由唯一原字段名推导，single/start_only/start_end的sections可省略并生成名称；legacy_sum和slope仍需计算单位或模式参数。见[迁移字段表](../migration.md)。|
|`analysis`|dict|是|无|位置或关键字。根据mapping.analysis复制出的新分析配置；转换器把生成的规则、窗口或指标写入此副本。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`issues`|list[[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)]|是|无|位置或关键字。接收本次转换的差异、警告和拒绝原因；调用者随后将它们写入迁移报告。|

### 返回说明

None；只填新message_calculations。

### 异常说明

ImportProblem为原配置/映射拒绝；
不把解析成功或声明SHA当作实际CAN输入/DBC已验证，不修改数值核。

源码：[`src/chronaxis/migration/legacy_sum.py:165`](../../../src/chronaxis/migration/legacy_sum.py#L165)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
