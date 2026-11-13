# `chronaxis.core.expression_math_reference`

逐点解释已统一dtype和单位的极值、限幅与平方根节点。

输入是白名单操作及本时刻的ScalarValue，输出保留必要输入及数值错误原因。
使用标准库标量计算；定宽平方在编译时展开为现有的精确乘法。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`math_reference`](#api-math_reference)|按标量数值协议执行一个极值、限幅或开方节点。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import sqrt
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-math_reference"></a>
## `math_reference`

按标量数值协议执行一个极值、限幅或开方节点。

```python
math_reference(name, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。编译器交给此核的逐点数值操作名，选择最小、最大、限幅或平方根。|
|`args`|Sequence[[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。各个已求值的数值实参，按原始调用位置顺序提交。|

### 返回说明

ScalarValue；有效极值/限幅保持dtype，开方输出FLOAT64。

### 异常说明

ValueError为内部未注册名称。缺失、倒置或开方不可计算表示为质量。

源码：[`src/chronaxis/core/expression_math_reference.py:12`](../../../src/chronaxis/core/expression_math_reference.py#L12)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

## 内部匿名回调


<a id="lambda-40"></a>
### 第40行匿名函数

```python
lambda arg: arg.value
```

|参数|含义|返回/异常|
|---|---|---|
|`arg`|候选 ScalarValue，已核对其类型且数值有效。|取该候选的原物理数值供 min 比较，数值相等时保留靠前的候选。|

<a id="lambda-42"></a>
### 第42行匿名函数

```python
lambda arg: arg.value
```

|参数|含义|返回/异常|
|---|---|---|
|`arg`|本次求最大值的有效标量操作数。|取候选自身的原物理数值作为 max 比较键，同值时沿用首个操作数。|
