# `chronaxis.core.moments_reference`

以精确有理数维护参考端的加权中心矩或均方。

输入是通过精度/质量门槛的有限二进制浮点数，正权重来自样本或实际选中区间。
Welford 更新只保存总权重、均值和中心矩。RMS 的有理数平方不会发生浮点中间
溢出；最后一次才按目标倍率和 float64 可表示性给出结果及质量。不依赖 NumPy。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`ReferenceMoments`](#api-ReferenceMoments)|每个归约器独享累计量，无样本列表、临时文件或跨会话缓存。|
|[`ReferenceMoments.__init__`](#api-ReferenceMoments-__init__)|创建零累计。|
|[`ReferenceMoments.push`](#api-ReferenceMoments-push)|合并有限块。|
|[`ReferenceMoments.finish`](#api-ReferenceMoments-finish)|完成目标单位换算。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from math import ldexp, sqrt
from .types import QualityFlag as Q
```

</details>

<a id="api-ReferenceMoments"></a>
## `ReferenceMoments`

每个归约器独享累计量，无样本列表、临时文件或跨会话缓存。

```python
ReferenceMoments(operation)
```


源码：[`src/chronaxis/core/moments_reference.py:13`](../../../src/chronaxis/core/moments_reference.py#L13)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceMoments-__init__"></a>
### `ReferenceMoments.__init__`

创建零累计。

```python
ReferenceMoments.__init__(operation)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。此累计器专用的方差、标准差或均方根操作名，决定跨批维护中心矩或均方。|

#### 返回说明

无。

#### 异常说明

调用方先做操作检查。

源码：[`src/chronaxis/core/moments_reference.py:16`](../../../src/chronaxis/core/moments_reference.py#L16)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceMoments-push"></a>
### `ReferenceMoments.push`

合并有限块。

```python
ReferenceMoments.push(values, weights=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|Sequence[float]|是|无|位置或关键字。本批通过选择、有效性和数值精度检查的有限数值，按输入的物理尺度提交。|
|`weights`|Sequence[int] &#124; None|否|None|位置或关键字。与本批数值逐项对应的正权重；样本统计省略时每条读数计一次，时间统计传有效时长。|

#### 返回说明

无。

#### 异常说明

无效权重或输入。

源码：[`src/chronaxis/core/moments_reference.py:21`](../../../src/chronaxis/core/moments_reference.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceMoments-finish"></a>
### `ReferenceMoments.finish`

完成目标单位换算。

```python
ReferenceMoments.finish(ddof, factor)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ddof`|int &#124; None|是|无|位置或关键字。已验证的分母修正，时间总体取零，样本方差或标准差可取一，RMS 省略。|
|`factor`|float|是|无|位置或关键字。自然结果单位到请求输出单位的正倍率，最终按方差或根统计的量纲应用一次。|

#### 返回说明

(float或None,质量)。

#### 异常说明

配置错误。

源码：[`src/chronaxis/core/moments_reference.py:36`](../../../src/chronaxis/core/moments_reference.py#L36)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
