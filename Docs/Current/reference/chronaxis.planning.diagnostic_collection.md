# `chronaxis.planning.diagnostic_collection`

一次收集独立配置错误，并阻断依赖坏声明的检查。

输入是已解析配置，输出为定位诊断或完整计划。Schema只负责结构与单字段约束；
语义仍由原解析器检查。只跳过无效声明，不改配置、不补假值，不创建可运行残缺计划。
上下文仅覆盖本次同步构建，退出后恢复；schema来自唯一维护的Docs/Schema，安装时随包提供。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`schema_validator`](#api-schema_validator)|加载只读结构规范。|
|[`_host_validator`](#api-_host_validator)|在本次验证器中放行宿主已登记的操作名。|
|[`_specific_errors`](#api-_specific_errors)|展开最适用联合分支，避免列出不相关格式的全部缺项。|
|[`DiagnosticCollection`](#api-DiagnosticCollection)|持有本次有限错误、阻断说明和无效对象；不保存输入或运行结果。|
|[`DiagnosticCollection.__init__`](#api-DiagnosticCollection-__init__)|检查所有独立结构字段。|
|[`DiagnosticCollection.add`](#api-DiagnosticCollection-add)|登记唯一错误。|
|[`DiagnosticCollection.usable`](#api-DiagnosticCollection-usable)|判断对象是否有结构错误。|
|[`DiagnosticCollection.block`](#api-DiagnosticCollection-block)|记录依赖阻断，避免派生假错误。|
|[`DiagnosticCollection.stage`](#api-DiagnosticCollection-stage)|隔离一个有明确依赖的检查。|
|[`DiagnosticCollection.finish`](#api-DiagnosticCollection-finish)|有错则统一抛出，不返回残缺计划。|
|[`DiagnosticCollection.finish.priority`](#api-DiagnosticCollection-finish-priority)||
|[`current_collection`](#api-current_collection)|返回当前构建的集合。|
|[`collecting`](#api-collecting)|临时接入本次构建。|
|[`usable_node`](#api-usable_node)|跳过坏节点且记录名称供依赖判断。|
|[`collect_node_error`](#api-collect_node_error)|收集单节点失败；非汇总模式保持原抛出行为。|
|[`require_expression_dependencies`](#api-require_expression_dependencies)|遇到已知坏信号只阻断当前表达式。|
|[`expression_scope`](#api-expression_scope)|给单项静态诊断选择真实依赖，避免无关坏派生项遮蔽此项。|
|[`diagnose_plan`](#api-diagnose_plan)|为计划入口建立唯一诊断上下文。|
|[`diagnose_plan.checked`](#api-diagnose_plan-checked)|调用一次构建。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
from pathlib import Path
from jsonschema import Draft202012Validator, validators
from ..configuration.models import field_path_text
from .checks import PlanValidationError
```

</details>

<a id="api-schema_validator"></a>
## `schema_validator`

加载只读结构规范。

```python
schema_validator(name)
```

装饰器：`lru_cache(maxsize=4)`。

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。要读取的固定JSON Schema文件名，例如analysis.schema.json；只读取包内或开发仓库的规范。|

### 返回说明

validator。

### 异常说明

安装缺资源或规范损坏。

原生整数检查与带有明确类型的 API一致，不让bool或1.0冒充整数；不访问网络引用。

源码：[`src/chronaxis/planning/diagnostic_collection.py:22`](../../../src/chronaxis/planning/diagnostic_collection.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_host_validator"></a>
## `_host_validator`

在本次验证器中放行宿主已登记的操作名。

```python
_host_validator(validator, extensions)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`validator`|jsonschema.protocols.Validator|是|无|位置或关键字。已装入对应版本规范的基础验证器；在其独立副本上补入此宿主的操作名。|
|`extensions`|[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry)|是|无|位置或关键字。已显式登记的宿主操作集合，只将允许的归约/时序名称加入本次检查。|

### 返回说明

独立验证器。

### 异常说明

注册非法。

只复制变化的字典路径；内置操作和无注册的 CLI 始终使用原规范，不改变共享缓存。

源码：[`src/chronaxis/planning/diagnostic_collection.py:37`](../../../src/chronaxis/planning/diagnostic_collection.py#L37)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_specific_errors"></a>
## `_specific_errors`

展开最适用联合分支，避免列出不相关格式的全部缺项。

```python
_specific_errors(error)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|jsonschema.exceptions.ValidationError|是|无|位置或关键字。jsonschema返回的一个ValidationError；可能含oneOf或anyOf子分支错误。|

### 返回说明

叶错误迭代器。

### 异常说明

无。
优先匹配已有字段的const/enum判别，再选择错误最少的分支；未知判别值保留父错误。

源码：[`src/chronaxis/planning/diagnostic_collection.py:55`](../../../src/chronaxis/planning/diagnostic_collection.py#L55)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DiagnosticCollection"></a>
## `DiagnosticCollection`

持有本次有限错误、阻断说明和无效对象；不保存输入或运行结果。

```python
DiagnosticCollection(config, schema_name='analysis.schema.json', *, extensions=None)
```


源码：[`src/chronaxis/planning/diagnostic_collection.py:89`](../../../src/chronaxis/planning/diagnostic_collection.py#L89)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DiagnosticCollection-__init__"></a>
### `DiagnosticCollection.__init__`

检查所有独立结构字段。

```python
DiagnosticCollection.__init__(config, schema_name='analysis.schema.json', *, extensions=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|JSON值|是|无|位置或关键字。已经解析为原生字典的配置；本函数读取结构并收集独立字段错误，不修改配置。|
|`schema_name`|str|否|'analysis.schema.json'|位置或关键字。当前配置使用的JSON Schema文件名，默认analysis.schema.json；批量配置使用batch-v1.schema.json。|
|`extensions`|[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry) &#124; None|否|None|仅关键字。只为本次配置结构检查开放其中已登记的归约与时序操作，不修改公共规范。|

#### 返回说明

新集合。

#### 异常说明

资源错误。

源码：[`src/chronaxis/planning/diagnostic_collection.py:92`](../../../src/chronaxis/planning/diagnostic_collection.py#L92)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DiagnosticCollection-add"></a>
### `DiagnosticCollection.add`

登记唯一错误。

```python
DiagnosticCollection.add(error)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)|是|无|位置或关键字。待登记的PlanValidationError；相同path和code只保留一项。|

#### 返回说明

None。

#### 异常说明

无。

源码：[`src/chronaxis/planning/diagnostic_collection.py:191`](../../../src/chronaxis/planning/diagnostic_collection.py#L191)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DiagnosticCollection-usable"></a>
### `DiagnosticCollection.usable`

判断对象是否有结构错误。

```python
DiagnosticCollection.usable(path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。待检查对象的JSON路径；该位置或子字段有已知错误时返回False。|

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/planning/diagnostic_collection.py:196`](../../../src/chronaxis/planning/diagnostic_collection.py#L196)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DiagnosticCollection-block"></a>
### `DiagnosticCollection.block`

记录依赖阻断，避免派生假错误。

```python
DiagnosticCollection.block(path, reason)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。因依赖无效而暂未执行检查的字段路径。|
|`reason`|str|是|无|位置或关键字。向调用者解释依赖阻断原因的文本；不把阻断当作额外确认错误。|

#### 返回说明

None。

#### 异常说明

无。

源码：[`src/chronaxis/planning/diagnostic_collection.py:201`](../../../src/chronaxis/planning/diagnostic_collection.py#L201)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DiagnosticCollection-stage"></a>
### `DiagnosticCollection.stage`

隔离一个有明确依赖的检查。

```python
DiagnosticCollection.stage(path, *, requires=True, check=True)
```

装饰器：`contextmanager`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。本项检查对应的JSON路径。|
|`requires`|bool|否|True|仅关键字。前置声明是否有效，默认True；False时记录阻断并跳过本项。|
|`check`|bool|否|True|仅关键字。是否先检查path下的已知结构错误，默认True；False只跳过这一步，仍检查requires。|

#### 返回说明

是否执行。

#### 异常说明

非配置错误传播。

源码：[`src/chronaxis/planning/diagnostic_collection.py:208`](../../../src/chronaxis/planning/diagnostic_collection.py#L208)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DiagnosticCollection-finish"></a>
### `DiagnosticCollection.finish`

有错则统一抛出，不返回残缺计划。

```python
DiagnosticCollection.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

PlanValidationError。

源码：[`src/chronaxis/planning/diagnostic_collection.py:225`](../../../src/chronaxis/planning/diagnostic_collection.py#L225)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DiagnosticCollection-finish-priority"></a>
### `DiagnosticCollection.finish.priority`



```python
DiagnosticCollection.finish.priority(error)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)|是|无|位置或关键字。已收集的配置错误；根据错误代码与字段路径，优先展示拼写建议和操作类型的根因，再展示其他独立错误。|

#### 返回说明

根因优先级。

#### 异常说明

无。

源码：[`src/chronaxis/planning/diagnostic_collection.py:229`](../../../src/chronaxis/planning/diagnostic_collection.py#L229)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-current_collection"></a>
## `current_collection`

返回当前构建的集合。

```python
current_collection()
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

集合或None。

### 异常说明

无。

源码：[`src/chronaxis/planning/diagnostic_collection.py:240`](../../../src/chronaxis/planning/diagnostic_collection.py#L240)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-collecting"></a>
## `collecting`

临时接入本次构建。

```python
collecting(collection)
```

装饰器：`contextmanager`。

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`collection`|[DiagnosticCollection](chronaxis.planning.diagnostic_collection.md#api-DiagnosticCollection)|是|无|位置或关键字。本次同步构建使用的DiagnosticCollection；退出上下文时恢复先前集合。|

### 返回说明

无。

### 异常说明

原异常传播，始终恢复上下文。

源码：[`src/chronaxis/planning/diagnostic_collection.py:246`](../../../src/chronaxis/planning/diagnostic_collection.py#L246)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-usable_node"></a>
## `usable_node`

跳过坏节点且记录名称供依赖判断。

```python
usable_node(path, raw=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。当前来源、信号、规则或窗口声明的JSON路径。|
|`raw`|JSON值或None|否|None|位置或关键字。可选原始声明，默认None；有name时登记坏名称，供后续依赖判断。|

### 返回说明

bool。

### 异常说明

无。

源码：[`src/chronaxis/planning/diagnostic_collection.py:255`](../../../src/chronaxis/planning/diagnostic_collection.py#L255)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-collect_node_error"></a>
## `collect_node_error`

收集单节点失败；非汇总模式保持原抛出行为。

```python
collect_node_error(error, path, raw)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)|是|无|位置或关键字。当前节点产生的PlanValidationError；非收集模式直接抛出。|
|`path`|str|是|无|位置或关键字。发生错误节点的JSON路径。|
|`raw`|JSON值或None|是|无|位置或关键字。原始节点声明；用于登记无效名称及其依赖，不修改原配置。|

### 返回说明

None。

### 异常说明

原错误。

源码：[`src/chronaxis/planning/diagnostic_collection.py:292`](../../../src/chronaxis/planning/diagnostic_collection.py#L292)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-require_expression_dependencies"></a>
## `require_expression_dependencies`

遇到已知坏信号只阻断当前表达式。

```python
require_expression_dependencies(text, path, derived)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。待检查的表达式文本；只读取AST中的名称，不执行表达式。|
|`path`|str|是|无|位置或关键字。表达式字段的JSON路径，用于定位依赖阻断。|
|`derived`|tuple[DerivedPlan, ...]|是|无|位置或关键字。已声明的派生项序列，用于沿引用检查所需信号是否已无效。|

### 返回说明

None。

### 异常说明

依赖阻断。

只读取AST名称，不执行表达式；真正的语法、dtype和单位仍由表达式编译器检查。

源码：[`src/chronaxis/planning/diagnostic_collection.py:307`](../../../src/chronaxis/planning/diagnostic_collection.py#L307)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-expression_scope"></a>
## `expression_scope`

给单项静态诊断选择真实依赖，避免无关坏派生项遮蔽此项。

```python
expression_scope(text, bindings, derived)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。本项表达式文本；从中确定静态诊断需要的派生项。|
|`bindings`|DeclarationBindings|是|无|位置或关键字。实际声明绑定，保留信号定义并按依赖选取派生名称。|
|`derived`|tuple[DerivedPlan, ...]|是|无|位置或关键字。全部派生项声明；只为当前诊断返回必要子集，不创建运行计划。|

### 返回说明

仅用于静态诊断的绑定和派生。

### 异常说明

原模型错误。
全计划仍逐项检查所有派生；此处不创建运行计划或修改输入配置。

源码：[`src/chronaxis/planning/diagnostic_collection.py:334`](../../../src/chronaxis/planning/diagnostic_collection.py#L334)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-diagnose_plan"></a>
## `diagnose_plan`

为计划入口建立唯一诊断上下文。

```python
diagnose_plan(function)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`function`|Callable|是|无|位置或关键字。原计划构建方法；包装器只调用一次并在退出时恢复诊断上下文。|

### 返回说明

包装方法。

### 异常说明

完整配置错误。

合法输入只构建一次；错误输入从不返回局部计划，且始终恢复上层上下文。

源码：[`src/chronaxis/planning/diagnostic_collection.py:363`](../../../src/chronaxis/planning/diagnostic_collection.py#L363)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-diagnose_plan-checked"></a>
### `diagnose_plan.checked`

调用一次构建。

```python
diagnose_plan.checked(config, *args, **kwargs)
```

装饰器：`wraps(function)`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|JSON值|是|无|位置或关键字。原配置字典，先检查可接受的JSON值，再调用原构建方法。|
|`args`|tuple|否|()|可变位置。原构建方法的位置参数，原样转交。|
|`kwargs`|dict|否|{}|可变关键字。原构建方法的关键字参数，原样转交。|

#### 返回说明

完整计划。

#### 异常说明

汇总配置错误。

源码：[`src/chronaxis/planning/diagnostic_collection.py:369`](../../../src/chronaxis/planning/diagnostic_collection.py#L369)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

## 内部匿名回调


<a id="lambda-33"></a>
### 第33行匿名函数

```python
lambda checker, value: type(value) is int
```

|参数|含义|返回/异常|
|---|---|---|
|`checker`|校验器传入其类型检查对象和候选 JSON 值，检查只使用后一个实参。|仅原生 int 返回真，拒绝把布尔值或浮点表示当作配置整数。|
|`value`|校验器传入其类型检查对象和候选 JSON 值，检查只使用后一个实参。|仅原生 int 返回真，拒绝把布尔值或浮点表示当作配置整数。|

<a id="lambda-84"></a>
### 第84行匿名函数

```python
lambda item: item[:3]
```

|参数|含义|返回/异常|
|---|---|---|
|`item`|候选 schema 分支的分数、子错误数量优先级、分支序号及实际错误清单。|只以前三项作为排序键，使分支优先级稳定，避免比较错误对象。|
