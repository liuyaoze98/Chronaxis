# `chronaxis.core.function_contracts`

列出已实现内置逐点函数的固定签名与编译、质量、更新和后端契约。

本目录供宿主查询现行版本的能力，不创建数据、运行回调或扩大AST白名单。
编译器及对应数值内核负责实际检查；注册时以内置名称集合消除冲突。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`BuiltinFunctionContract`](#api-BuiltinFunctionContract)|只读的内置函数契约。字符串描述明确参数、常量、输出、失效与更新政策。|
|[`_catalog`](#api-_catalog)|构造一个版本的真实内置目录。|
|[`_catalog.add`](#api-_catalog-add)|登记单一语义描述。|
|[`builtin_function_specs`](#api-builtin_function_specs)|查询指定语法版本的内置函数。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from types import MappingProxyType
```

</details>

<a id="api-BuiltinFunctionContract"></a>
## `BuiltinFunctionContract`

只读的内置函数契约。字符串描述明确参数、常量、输出、失效与更新政策。

```python
class BuiltinFunctionContract
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|用于DSL调用的受限函数标识，不包括参数和括号。|
|`version`|str|是|无|本条说明所对应的内置函数契约版本；随配置语义版本选择。|
|`signature`|str|是|无|按DSL写法显示的函数名和正式参数，包括仅限关键字的参数。|
|`inputs`|str|是|无|说明可使用的输入类别、兼容关系与参数个数。|
|`constants`|str|是|无|说明哪些位置要求常量，以及裸值根据哪个尺度解释。|
|`output`|str|是|无|描述求值输出的逻辑类型、单位及需要提升数值类型的情况。|
|`validity`|str|是|无|输入无效、越界或数值失败时如何传播质量的规则。|
|`updates`|str|否|'普通表达式依赖的真实更新'|规定哪些真实输入变化会成为该结果的新样本。|
|`history_ns`|int|否|0|该函数需要的历史长度，单位为纳秒；这些纯逐点函数不读取窗口历史。|
|`pure`|bool|否|True|声明相同输入是否有确定输出且不保留上次调用的状态。|
|`backends`|tuple[str, ...]|否|('reference', 'numpy')|当前内置实现实际提供的后端名称。|

源码：[`src/chronaxis/core/function_contracts.py:11`](../../../src/chronaxis/core/function_contracts.py#L11)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_catalog"></a>
## `_catalog`

构造一个版本的真实内置目录。

```python
_catalog(version)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`version`|int|是|无|位置或关键字。要构造能力目录的表达式版本，当前仅支持4。|

### 返回说明

只读名称映射。

### 异常说明

内部描述冲突。

源码：[`src/chronaxis/core/function_contracts.py:26`](../../../src/chronaxis/core/function_contracts.py#L26)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_catalog-add"></a>
### `_catalog.add`

登记单一语义描述。

```python
_catalog.add(name, args, inputs, constants, output, validity, updates='普通表达式依赖的真实更新')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。用于DSL调用的受限函数标识，不包括参数和括号。|
|`args`|str|是|无|位置或关键字。仅括号内的参数清单文本，与函数名合成公开签名。|
|`inputs`|str|是|无|位置或关键字。说明可使用的输入类别、兼容关系与参数个数。|
|`constants`|str|是|无|位置或关键字。说明哪些位置要求常量，以及裸值根据哪个尺度解释。|
|`output`|str|是|无|位置或关键字。描述求值输出的逻辑类型、单位及需要提升数值类型的情况。|
|`validity`|str|是|无|位置或关键字。输入无效、越界或数值失败时如何传播质量的规则。|
|`updates`|str|否|'普通表达式依赖的真实更新'|位置或关键字。规定哪些真实输入变化会成为该结果的新样本。|

#### 返回说明

None。

#### 异常说明

重复名称。

源码：[`src/chronaxis/core/function_contracts.py:30`](../../../src/chronaxis/core/function_contracts.py#L30)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-builtin_function_specs"></a>
## `builtin_function_specs`

查询指定语法版本的内置函数。

```python
builtin_function_specs(config_version=4)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config_version`|int|否|4|位置或关键字。查内置函数契约时使用的配置版本；v3只列abs和isclose。|

### 返回说明

只读契约映射。

### 异常说明

未支持版本。

源码：[`src/chronaxis/core/function_contracts.py:70`](../../../src/chronaxis/core/function_contracts.py#L70)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
