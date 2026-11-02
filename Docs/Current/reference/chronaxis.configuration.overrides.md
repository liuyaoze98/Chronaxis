# chronaxis.configuration.overrides

只覆盖公共定义中的明确配置项，不允许隐藏改名、添加对象或递归合并自由数据。

覆盖值按主文件定位，随后仍由普通计划校验器检查；来源表同时指回真正的覆盖位置。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConfigurationOrigin](chronaxis.configuration.models.md#api-ConfigurationOrigin)

## 对象导航

|对象|用途|
|---|---|
|[`apply_overrides`](#api-apply_overrides)|修改本次独立副本；参数含原文位置。返回None；非法对象/字段经_imports._reject定位。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from copy import deepcopy
from .models import ConfigurationOrigin
```

</details>

<a id="api-apply_overrides"></a>
## `apply_overrides`

修改本次独立副本；参数含原文位置。返回None；非法对象/字段经_imports._reject定位。

```python
apply_overrides(target, document, prefix, locations, origins)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`target`|dict|是|无|位置或关键字。本次独立合并副本，函数应用覆盖后移除overrides键。|
|`document`|ConfigurationDocument|是|无|位置或关键字。主配置原文及定位信息，覆盖路径以其目录为基准。|
|`prefix`|tuple|是|无|位置或关键字。普通分析为空元组；INI映射为analysis前缀。|
|`locations`|dict|是|无|位置或关键字。最终字段到原位置的可修改索引，删除已被整体替换的旧字段。|
|`origins`|dict|是|无|位置或关键字。最终字段到声明文件/字段位置的可修改索引。|

源码：[`src/chronaxis/configuration/overrides.py:15`](../../../src/chronaxis/configuration/overrides.py#L15)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
