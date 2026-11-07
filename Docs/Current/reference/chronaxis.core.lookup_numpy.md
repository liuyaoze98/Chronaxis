# `chronaxis.core.lookup_numpy`

通过 NumPy searchsorted 为整批活动样本查表并计算线性或阶梯输出。

从冻结字节借用小端定宽列，不为每个样本或批次复制标定表。输入先按
既有无损规则转为浮点轴，只有有效且位于开区间内部时才执行插值。
临时列随本批行数增长，不调用标量核，也不改变输入与其质量。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`lookup_numpy`](#api-lookup_numpy)|批量查表。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .types import QualityFlag as Q
```

</details>

<a id="api-lookup_numpy"></a>
## `lookup_numpy`

批量查表。

```python
lookup_numpy(table, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|PreparedLookup|是|无|位置或关键字。静态校验并绑定了轴、输出类型、插值模式和越界政策的不可变表。|
|`value`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。已换算到标定轴单位的输入数值及质量，在有效输入上应用表内或越界规则。|

### 返回说明

同长的表值列。

### 异常说明

类型、分配或布局错误。

源码：[`src/chronaxis/core/lookup_numpy.py:13`](../../../src/chronaxis/core/lookup_numpy.py#L13)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
