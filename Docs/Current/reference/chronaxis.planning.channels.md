# chronaxis.planning.channels

把用户配置的 CAN 通道转换为内部编号，不读取报文或修改原始数据。

公共配置统一从1开始，底层模型从0开始。只在构造模型前调用；配置展开、
序列化与路径解析保留公共编号，避免往返时反复减1。CSV文件列的channel_origin
描述原始文件格式，不经过此转换。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`channel_index`](#api-channel_index)|校验公共通道并返回0基编号。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .checks import PlanValidationError
```

</details>

<a id="api-channel_index"></a>
## `channel_index`

校验公共通道并返回0基编号。

```python
channel_index(value, path, *, key=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; str|是|无|位置或关键字。用户配置的1基通道。key=False时为正整数；key=True时为不含前导零的正十进制字符串。|
|`path`|str|是|无|位置或关键字。当前配置字段的位置，例如$.sources[0].dbc_by_channel；错误用它定位需要修正的声明。|
|`key`|bool|否|False|仅关键字。key=True时为DBC映射的规范十进制字符串|

### 返回说明

int，用户1对应内部0。

### 异常说明

PlanValidationError，非法或旧0基声明。

源码：[`src/chronaxis/planning/channels.py:12`](../../../src/chronaxis/planning/channels.py#L12)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
