# `chronaxis.planning.lookups`

在静态配置中解析 v4 一维表；仅创建冻结点对，不创建求值数组或打开文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LookupTablePlan](chronaxis.core.lookup.md#api-LookupTablePlan)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`parse_lookups`](#api-parse_lookups)|从根数组建立标定表。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.lookup import LookupTablePlan, MAX_POINTS, MAX_TABLES
from .checks import PlanValidationError, array_at, model_at, number_at, object_at, text_at
```

</details>

<a id="api-parse_lookups"></a>
## `parse_lookups`

从根数组建立标定表。

```python
parse_lookups(raw, version)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|list[dict]|是|无|位置或关键字。根级 lookups 的配置列表，每项按名称、输入单位、输出单位与点对检查。|
|`version`|int|是|无|位置或关键字。加载的配置版本，具名标定表仅对版本 4 开放。|

### 返回说明

冻结表元组。

### 异常说明

含具体位置的配置错误。

源码：[`src/chronaxis/planning/lookups.py:7`](../../../src/chronaxis/planning/lookups.py#L7)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
