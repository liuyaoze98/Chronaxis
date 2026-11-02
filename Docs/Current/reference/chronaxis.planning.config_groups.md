# chronaxis.planning.config_groups

把当前配置的就地分组送入既有解析器，不改变时间或数值规则。

输入为JSON配置副本，输出独立副本。reader集中读取参数，conversion集中换算，
interval跟随实际消费者，scope对象明确引用规则或窗口。仅复制配置，不读输入、
不推断设备同步、不生成逐帧追溯。反向函数用于配置工具输出当前唯一公共形式。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`public_errors`](#api-public_errors)|将内部字段错误还原到用户声明位置。|
|[`public_errors.checked`](#api-public_errors-checked)|调用原解析器，仅在错误退出时修正已归组字段的路径。|
|[`_leaves`](#api-_leaves)|遍历叶信号及声明路径。|
|[`normalize_configuration`](#api-normalize_configuration)|解析当前公共分组。|
|[`public_configuration`](#api-public_configuration)|把生成器内部结构转成当前公共配置。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from copy import deepcopy
from functools import wraps
from .checks import object_at, array_at, text_at, timezone_at, PlanValidationError
```

</details>

<a id="api-public_errors"></a>
## `public_errors`

将内部字段错误还原到用户声明位置。

```python
public_errors(function)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`function`|Callable|是|无|位置或关键字。计划构建函数；包装器仅把内部字段错误位置还原到公开配置位置。|

### 返回说明

包装方法。

### 异常说明

原PlanValidationError。

不改变错误代码和原因，不读取或保存输入；结构阶段对旧名的拒绝保留旧名位置。

源码：[`src/chronaxis/planning/config_groups.py:17`](../../../src/chronaxis/planning/config_groups.py#L17)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-public_errors-checked"></a>
### `public_errors.checked`

调用原解析器，仅在错误退出时修正已归组字段的路径。

```python
public_errors.checked(config, *args, **kwargs)
```

装饰器：`wraps(function)`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|dict[str, object]|是|无|位置或关键字。调用方的公共配置；包装器只用它把内部错误路径对应回原声明位置。|
|`args`|tuple[object, ...]|否|()|可变位置。原样传给被包装方法的位置实参；本包装器不解析或修改它们。|
|`kwargs`|dict[str, object]|否|{}|可变关键字。原样传给被包装方法的关键字实参，例如base_dir；是否接受由原方法决定。|

源码：[`src/chronaxis/planning/config_groups.py:23`](../../../src/chronaxis/planning/config_groups.py#L23)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_leaves"></a>
## `_leaves`

遍历叶信号及声明路径。

```python
_leaves(signals, path='$.signals')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`signals`|list|是|无|位置或关键字。普通或组式signals数组。|
|`path`|str|否|'$.signals'|位置或关键字。当前数组的公开配置字段路径，默认$.signals。|

### 返回说明

(dict,path)。

### 异常说明

错误数组/对象。

源码：[`src/chronaxis/planning/config_groups.py:52`](../../../src/chronaxis/planning/config_groups.py#L52)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-normalize_configuration"></a>
## `normalize_configuration`

解析当前公共分组。

```python
normalize_configuration(config)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|dict|是|无|位置或关键字。当前公开配置；reader、conversion、scope对象及节点interval转为独立内部副本，旧平铺字段被拒绝。|

### 返回说明

独立内部字典。

### 异常说明

公共结构错误。

只接受当前拼写，旧扁平参数明确拒绝；内部parser/reader_options等仅供既有
解析器消费，不作为第二套用户配置入口。调用应在预设展开之前。

源码：[`src/chronaxis/planning/config_groups.py:64`](../../../src/chronaxis/planning/config_groups.py#L64)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-public_configuration"></a>
## `public_configuration`

把生成器内部结构转成当前公共配置。

```python
public_configuration(config)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|dict|是|无|位置或关键字。内部配置副本；返回可保存的当前公共结构，不读取输入或修改调用方对象。|

### 返回说明

独立字典。

### 异常说明

结构错误。

不读取文件，不改变自由metadata或业务值；已使用新分组的内容原样保留。
用于预设展开、INI导入和resolve，不能用作接受旧用户配置的兼容入口。

源码：[`src/chronaxis/planning/config_groups.py:164`](../../../src/chronaxis/planning/config_groups.py#L164)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
