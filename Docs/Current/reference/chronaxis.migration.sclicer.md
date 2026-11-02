# chronaxis.migration.sclicer

把受支持Sclicer段转换为新活动或固定窗口，完整报告边界差异。

输入是已定位INI、显式mapping及本次独立分析字典；输出只修改该新字典的
rules/windows并追加字段去向和警告。不执行旧触发器、eval或来源I/O。
single的post只作为exit_delay，start_only的post不再次延长固定duration。
显式sclicer_slope使用完整window_delta和触发点周围的pre/post窗口，差异写入报告。
显式sclicer_start_end还要求mapping确认新开始/结束含义，旧post不附加。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)

## 对象导航

|对象|用途|
|---|---|
|[`_ini_problem`](#api-_ini_problem)|附原字段行列后拒绝，缺失字段回退到原段头。|
|[`_seconds`](#api-_seconds)|把旧秒数转换为显式精确时长，不猜工程参数或接受NaN。|
|[`_boolean`](#api-_boolean)|沿ConfigParser旧布尔词表读取开关；|
|[`_AliasTransformer`](#api-_AliasTransformer)|只替换AST Name，保字符串literal、原大小写和运算结合顺序。|
|[`_AliasTransformer.__init__`](#api-_AliasTransformer-__init__)|保本次显式别名表；|
|[`_AliasTransformer.visit_Name`](#api-_AliasTransformer-visit_Name)|替换一个字段引用；|
|[`_AliasTransformer.visit_Call`](#api-_AliasTransformer-visit_Call)|仅保现有DSL注册函数，不把函数名当字段重写。|
|[`_expression`](#api-_expression)|解析白名单AST并替换Name，最终类型/单位仍交公开计划检查。|
|[`convert_sclicer`](#api-convert_sclicer)|整份转换显式选择的Sclicer模式，遇一项不支持便拒绝整个计划。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from decimal import Decimal, InvalidOperation
from ..timebase import parse_duration
from .ini import field_path, locate, mark, problem
from .models import LegacyImportIssue
from .slope import slope_rule
from .start_end import start_end_options
```

</details>

<a id="api-_ini_problem"></a>
## `_ini_problem`

附原字段行列后拒绝，缺失字段回退到原段头。

```python
_ini_problem(fields, section, key, code, message, *, headers=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|
|`code`|str|是|无|位置或关键字。迁移问题代码，与message一起描述不能转换的原因；section和key定位旧字段。|
|`message`|str|是|无|位置或关键字。准备写入迁移问题报告的中文原因说明，与code共同说明该字段为什么无法转换。|
|`headers`|dict[str, int] &#124; None|否|None|仅关键字。旧INI段名到所在行号的对应表，用来把错误指向原文件位置。 None表示没有可用行号索引，仍保留节名和键名定位。|

### 返回说明

无。

### 异常说明

ImportProblem；不为缺失字段编造一个不存在的字段行。

源码：[`src/chronaxis/migration/sclicer.py:20`](../../../src/chronaxis/migration/sclicer.py#L20)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_seconds"></a>
## `_seconds`

把旧秒数转换为显式精确时长，不猜工程参数或接受NaN。

```python
_seconds(parser, fields, section, key, default, *, positive=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`parser`|configparser.ConfigParser|是|无|位置或关键字。已经解析的旧INI，用它读取原段落和键值；不在这里重新读取文件。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|
|`default`|int &#124; float &#124; None|是|无|位置或关键字。旧配置省略该时长字段时采用的秒数；None表示没有可采用的默认时长。|
|`positive`|bool|否|False|仅关键字。positive限定正值。|

### 返回说明

带s的时长文本。

### 异常说明

ImportProblem为非法或不能精确表示的时长。

本函数直接报告的具体错误：

- `ValueError`：时长必须有限且非负，固定窗口须大于零。

源码：[`src/chronaxis/migration/sclicer.py:32`](../../../src/chronaxis/migration/sclicer.py#L32)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_boolean"></a>
## `_boolean`

沿ConfigParser旧布尔词表读取开关；

```python
_boolean(parser, fields, section, key, default)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`parser`|configparser.ConfigParser|是|无|位置或关键字。已经解析的旧INI，用它读取原段落和键值；不在这里重新读取文件。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|
|`default`|bool|是|无|位置或关键字。原INI未提供此开关时明确采用的布尔默认值。|

### 返回说明

bool；

### 异常说明

ImportProblem。

源码：[`src/chronaxis/migration/sclicer.py:51`](../../../src/chronaxis/migration/sclicer.py#L51)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_AliasTransformer"></a>
## `_AliasTransformer`

只替换AST Name，保字符串literal、原大小写和运算结合顺序。

```python
_AliasTransformer(aliases, fields, section, key)
```

继承关系：ast.NodeTransformer。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/migration/sclicer.py:59`](../../../src/chronaxis/migration/sclicer.py#L59)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_AliasTransformer-__init__"></a>
### `_AliasTransformer.__init__`

保本次显式别名表；

```python
_AliasTransformer.__init__(aliases, fields, section, key)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`aliases`|Mapping[str, str]|是|无|位置或关键字。旧表达式名称到新信号别名的映射，例如{"Voltage": "u"}；表达式中的Voltage据此改成u。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无。

源码：[`src/chronaxis/migration/sclicer.py:62`](../../../src/chronaxis/migration/sclicer.py#L62)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_AliasTransformer-visit_Name"></a>
### `_AliasTransformer.visit_Name`

替换一个字段引用；

```python
_AliasTransformer.visit_Name(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.Name|是|无|位置或关键字。旧表达式中的变量名节点，按aliases映射替换成新信号别名。|

#### 返回说明

新Name；

#### 异常说明

ImportProblem为缺映射。

源码：[`src/chronaxis/migration/sclicer.py:66`](../../../src/chronaxis/migration/sclicer.py#L66)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_AliasTransformer-visit_Call"></a>
### `_AliasTransformer.visit_Call`

仅保现有DSL注册函数，不把函数名当字段重写。

```python
_AliasTransformer.visit_Call(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.Call|是|无|位置或关键字。旧表达式中的函数调用节点，检查支持的函数并转换其中参数。|

#### 返回说明

原节点和改写后的参数。

#### 异常说明

ImportProblem为任意调用。

源码：[`src/chronaxis/migration/sclicer.py:72`](../../../src/chronaxis/migration/sclicer.py#L72)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_expression"></a>
## `_expression`

解析白名单AST并替换Name，最终类型/单位仍交公开计划检查。

```python
_expression(text, aliases, fields, section, key)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。待检查的原文本；JSON常量入口拒绝NaN/Infinity，其余函数按白名单解析常量或公式。|
|`aliases`|Mapping[str, str]|是|无|位置或关键字。旧表达式名称到新信号别名的映射，例如{"Voltage": "u"}；表达式中的Voltage据此改成u。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|

### 返回说明

新DSL文本。

### 异常说明

ImportProblem为危险语法、旧slope或缺映射；取消和资源错误不吞。

源码：[`src/chronaxis/migration/sclicer.py:84`](../../../src/chronaxis/migration/sclicer.py#L84)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-convert_sclicer"></a>
## `convert_sclicer`

整份转换显式选择的Sclicer模式，遇一项不支持便拒绝整个计划。

```python
convert_sclicer(parser, headers, mapping, analysis, fields, issues, mode)
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
|`mode`|str|是|无|位置或关键字。选择legacy_sum、sclicer_single、sclicer_start_only、sclicer_start_end或sclicer_slope。每种模式转换的内容和必填映射见[迁移](../migration.md)。|

### 返回说明

None；新rules/windows按原段序填充。

### 异常说明

ImportProblem为语义问题。

源码：[`src/chronaxis/migration/sclicer.py:108`](../../../src/chronaxis/migration/sclicer.py#L108)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
