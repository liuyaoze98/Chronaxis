# `chronaxis.core.units`

检查转换系数和范围端点的原生有限数值；单位关系由 unit_registry 统一提供。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`require_number`](#api-require_number)|要求有限原生数值，拒绝bool及未经声明的隐式标量转换。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
```

</details>

<a id="api-require_number"></a>
## `require_number`

要求有限原生数值，拒绝bool及未经声明的隐式标量转换。

```python
require_number(value: int | float, field: str) -> int | float
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。value为原生int或有限float|
|`field`|str|是|无|位置或关键字。field用于诊断位置。|

### 返回说明

原数值，不改变整数精度。

### 异常说明

TypeError为其他类型；ValueError为非有限float。

返回类型：int &#124; float。

源码：[`src/chronaxis/core/units.py:6`](../../../src/chronaxis/core/units.py#L6)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
