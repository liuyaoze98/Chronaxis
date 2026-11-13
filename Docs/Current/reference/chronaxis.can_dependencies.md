# `chronaxis.can_dependencies`

在真正使用 CAN 库时给出缺依赖诊断，已安装的库仍按需导入。

输入为固定支持的模块名，输出为原模块；仅包装缺少模块的异常，其他导入错误
继续原样报告。不安装依赖、不读取输入、不修改 reader/decoder 的调用顺序。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`CANDependencyError`](#api-CANDependencyError)|保留缺失模块名与机器码的 CAN 环境错误，不冒充配置值错误。|
|[`CANDependencyError.__init__`](#api-CANDependencyError-__init__)|保存缺项及安装建议。|
|[`import_can_dependency`](#api-import_can_dependency)|按既有调用点导入实际需要的 CAN 库。|
|[`runtime_dependency_versions`](#api-runtime_dependency_versions)|取得当前解释器与CAN依赖的实际版本，用于父子环境一致性核对。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from importlib import import_module
```

</details>

<a id="api-CANDependencyError"></a>
## `CANDependencyError`

保留缺失模块名与机器码的 CAN 环境错误，不冒充配置值错误。

```python
CANDependencyError(module_name)
```

继承关系：ImportError。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`code`|str|类成员，不作为构造参数填写|'dependency_missing'|固定为dependency_missing，标明CAN库或其依赖缺失；不表示信号字段配置错误。|

源码：[`src/chronaxis/can_dependencies.py:17`](../../../src/chronaxis/can_dependencies.py#L17)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-CANDependencyError-__init__"></a>
### `CANDependencyError.__init__`

保存缺项及安装建议。

```python
CANDependencyError.__init__(module_name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`module_name`|str|是|无|位置或关键字。实际缺失的Python模块名称，包含CAN库本身或其间接依赖；用于缺依赖诊断和安装建议。|

#### 返回说明

None。

#### 异常说明

无。

源码：[`src/chronaxis/can_dependencies.py:22`](../../../src/chronaxis/can_dependencies.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-import_can_dependency"></a>
## `import_can_dependency`

按既有调用点导入实际需要的 CAN 库。

```python
import_can_dependency(module_name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`module_name`|str|是|无|位置或关键字。需要按当前调用点导入的可选模块，仅接受can、cantools或natsort；其他名称拒绝。|

### 返回说明

原 Python 模块。

### 异常说明

CANDependencyError 表示模块或其依赖缺失；
其他 ImportError 原样传播，避免将损坏或不兼容安装误报成信号错误。

源码：[`src/chronaxis/can_dependencies.py:29`](../../../src/chronaxis/can_dependencies.py#L29)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-runtime_dependency_versions"></a>
## `runtime_dependency_versions`

取得当前解释器与CAN依赖的实际版本，用于父子环境一致性核对。

```python
runtime_dependency_versions()
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

dict[str, str]；四个键为 python、python-can、cantools、natsort，值来自当前解释器或已安装分发的实际版本，不是元数据声明的最低版本。

### 异常说明

任一分发缺少安装元数据时抛 importlib.metadata.PackageNotFoundError。不导入 CAN 库、不读取业务文件，也不代替安装元数据中的支持范围检查。

源码：[`src/chronaxis/can_dependencies.py:45`](../../../src/chronaxis/can_dependencies.py#L45)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
