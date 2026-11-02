# chronaxis.planning.dbc_defaults

仅在信号省略类型/单位或enum映射时读取DBC元数据，不读取报文。

每次计划编译按DBC路径共用一次加载；结果冻结为已有SignalDefinition字段。
数值信号不会因存在VAL表而变成文字枚举。重新加载配置才重新推导默认值。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANDependencyError](chronaxis.can_dependencies.md#api-CANDependencyError)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`_numeric_dtype`](#api-_numeric_dtype)|按解码后的数值范围选类型；有浮点缩放就使用float64，不丢弃小数。|
|[`_enum_choices`](#api-_enum_choices)|把DBC原码表转换到既有解码值域，不对实际记录再施加一次DBC缩放。|
|[`DBCDefaults`](#api-DBCDefaults)|一次计划编译内的临时数据库缓存，显式完整声明不打开DBC。|
|[`DBCDefaults.__init__`](#api-DBCDefaults-__init__)|创建空缓存，不访问磁盘。|
|[`DBCDefaults.fill`](#api-DBCDefaults-fill)|参数为信号配置、CAN来源和定位；返回补默认值的独立dict，错误定位到信号。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .checks import PlanValidationError
from ..legacy.binding import dbc_candidates
from ..can_dependencies import CANDependencyError, import_can_dependency
```

</details>

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

源码：[`src/chronaxis/planning/dbc_defaults.py:11`](../../../src/chronaxis/planning/dbc_defaults.py#L11)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

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

源码：[`src/chronaxis/planning/dbc_defaults.py:25`](../../../src/chronaxis/planning/dbc_defaults.py#L25)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DBCDefaults"></a>
## `DBCDefaults`

一次计划编译内的临时数据库缓存，显式完整声明不打开DBC。

```python
DBCDefaults()
```


源码：[`src/chronaxis/planning/dbc_defaults.py:42`](../../../src/chronaxis/planning/dbc_defaults.py#L42)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DBCDefaults-__init__"></a>
### `DBCDefaults.__init__`

创建空缓存，不访问磁盘。

```python
DBCDefaults.__init__()
```

参数：无显式参数。


源码：[`src/chronaxis/planning/dbc_defaults.py:44`](../../../src/chronaxis/planning/dbc_defaults.py#L44)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DBCDefaults-fill"></a>
### `DBCDefaults.fill`

参数为信号配置、CAN来源和定位；返回补默认值的独立dict，错误定位到信号。

```python
DBCDefaults.fill(raw, config, field, path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。一条信号声明；仅补缺省dtype、unit或enum的choices。|
|`config`|LegacyCANSpec &#124; CANTextSpec|是|无|位置或关键字。当前原始报文来源规格，提供DBC路径。|
|`field`|CANReferenceTemplate|是|无|位置或关键字。信号定位，含报文ID、DBC信号名与可选帧型限制。|
|`path`|str|是|无|位置或关键字。原声明字段路径，失败用它定位配置。|

源码：[`src/chronaxis/planning/dbc_defaults.py:48`](../../../src/chronaxis/planning/dbc_defaults.py#L48)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
