# `chronaxis.planning.dbc_defaults`

仅在信号省略类型/单位或enum映射时读取DBC元数据，不读取报文。

每次计划编译按DBC路径共用一次加载；结果冻结为已有SignalDefinition字段。
数值信号不会因存在VAL表而变成文字枚举。重新加载配置才重新推导默认值。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANDependencyError](chronaxis.can_dependencies.md#api-CANDependencyError)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`scoped_dbc_cache`](#api-scoped_dbc_cache)|在一次 fast 准备期间共享 DBC，嵌套子计划沿用外层缓存，退出即释放。|
|[`load_dbc`](#api-load_dbc)|返回当前准备范围的数据库；普通单任务保持原加载行为。|
|[`requested_enum_codes`](#api-requested_enum_codes)|在加载 DBC 前定位 enum_code 使用的信号，只解析表达式位置和简单派生别名。|
|[`_numeric_dtype`](#api-_numeric_dtype)|按解码后的数值范围选类型；有浮点缩放就使用float64，不丢弃小数。|
|[`_enum_choices`](#api-_enum_choices)|把DBC原码表转换到既有解码值域，不对实际记录再施加一次DBC缩放。|
|[`DBCDefaults`](#api-DBCDefaults)|一次计划编译内的临时数据库缓存，显式完整声明不打开DBC。|
|[`DBCDefaults.__init__`](#api-DBCDefaults-__init__)|创建空缓存，不访问磁盘。|
|[`DBCDefaults.fill`](#api-DBCDefaults-fill)|补全DBC可证明的声明，不重复应用原解码缩放。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from .checks import PlanValidationError
from ..legacy.binding import dbc_candidates
from ..can_dependencies import CANDependencyError, import_can_dependency
from ..dbc_loading import load_dbc_file
```

</details>

<a id="api-scoped_dbc_cache"></a>
## `scoped_dbc_cache`

在一次 fast 准备期间共享 DBC，嵌套子计划沿用外层缓存，退出即释放。

```python
scoped_dbc_cache()
```

装饰器：`contextmanager`。

参数：无显式参数。


源码：[`src/chronaxis/planning/dbc_defaults.py:20`](../../../src/chronaxis/planning/dbc_defaults.py#L20)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-load_dbc"></a>
## `load_dbc`

返回当前准备范围的数据库；普通单任务保持原加载行为。

```python
load_dbc(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。要读取的文件路径。|

源码：[`src/chronaxis/planning/dbc_defaults.py:32`](../../../src/chronaxis/planning/dbc_defaults.py#L32)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-requested_enum_codes"></a>
## `requested_enum_codes`

在加载 DBC 前定位 enum_code 使用的信号，只解析表达式位置和简单派生别名。

```python
requested_enum_codes(config)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|Mapping|是|无|位置或关键字。尚未读取业务记录的分析声明，用来定位表达式显式要求的枚举原始代码。|

### 返回说明

原码别名集合。

### 异常说明

完整语法诊断由稍后的统一编译器报告。

源码：[`src/chronaxis/planning/dbc_defaults.py:44`](../../../src/chronaxis/planning/dbc_defaults.py#L44)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_numeric_dtype"></a>
## `_numeric_dtype`

按解码后的数值范围选类型；有浮点缩放就使用float64，不丢弃小数。

```python
_numeric_dtype(signal)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`signal`|cantools.database.can.Signal|是|无|位置或关键字。DBC信号定义，按解码值范围、符号及缩放推导数值类型，不自动选择enum。|

### 返回说明

float64、int64或uint64文本。

### 异常说明

ValueError为缩放后整数不能用64位类型表示。

源码：[`src/chronaxis/planning/dbc_defaults.py:90`](../../../src/chronaxis/planning/dbc_defaults.py#L90)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_enum_choices"></a>
## `_enum_choices`

把DBC原码表转换到既有解码值域，不对实际记录再施加一次DBC缩放。

```python
_enum_choices(signal)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`signal`|cantools.database.can.Signal|是|无|位置或关键字。含choices和conversion的DBC信号；返回解码值到文字映射，浮点编码不截断。|

### 返回说明

[已解码整数码, 标签]列表。

### 异常说明

ValueError为缺少枚举、解码码值含小数或标签为空。

源码：[`src/chronaxis/planning/dbc_defaults.py:109`](../../../src/chronaxis/planning/dbc_defaults.py#L109)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DBCDefaults"></a>
## `DBCDefaults`

一次计划编译内的临时数据库缓存，显式完整声明不打开DBC。

```python
DBCDefaults()
```


源码：[`src/chronaxis/planning/dbc_defaults.py:131`](../../../src/chronaxis/planning/dbc_defaults.py#L131)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DBCDefaults-__init__"></a>
### `DBCDefaults.__init__`

创建空缓存，不访问磁盘。

```python
DBCDefaults.__init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

内存分配错误传播。

源码：[`src/chronaxis/planning/dbc_defaults.py:133`](../../../src/chronaxis/planning/dbc_defaults.py#L133)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DBCDefaults-fill"></a>
### `DBCDefaults.fill`

补全DBC可证明的声明，不重复应用原解码缩放。

```python
DBCDefaults.fill(raw, config, field, path, *, config_version=4, need_code=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。一条信号声明；仅补缺省dtype、unit或enum的choices。|
|`config`|LegacyCANSpec &#124; CANTextSpec|是|无|位置或关键字。当前原始报文来源规格，提供DBC路径。|
|`field`|CANReferenceTemplate|是|无|位置或关键字。信号定位，含报文ID、DBC信号名与可选帧型限制。|
|`path`|str|是|无|位置或关键字。原声明字段路径，失败用它定位配置。|
|`config_version`|int|否|4|仅关键字。config_version选择规则。|
|`need_code`|bool|否|False|仅关键字。为真时读取枚举原始整数字段的有无符号信息。|

#### 返回说明

独立dict，v4保留DBC原单位作为input_unit。

#### 异常说明

PlanValidationError为缺项、歧义、读取或依赖错误。

源码：[`src/chronaxis/planning/dbc_defaults.py:141`](../../../src/chronaxis/planning/dbc_defaults.py#L141)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
