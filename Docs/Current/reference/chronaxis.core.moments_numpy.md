# `chronaxis.core.moments_numpy`

按有限 NumPy 块维护加权中心矩或均方根，不收集历史。

由真实有效掩码选好的值和权重按相同的二进制幂缩放。块内围绕锚点求均值和
离均差，跨块用两总体均值差合并离散度。用根均方形式存储二阶量，开方与
目标倍率在可表示范围内求值，不把两个大均方相减，也不逐样本运行标量实现。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`NumpyMoments`](#api-NumpyMoments)|持有一个锚点、相对均值、根二阶量、总权重和幂指数，跨块大小固定。|
|[`NumpyMoments.__init__`](#api-NumpyMoments-__init__)|初始化归约器。|
|[`NumpyMoments.push`](#api-NumpyMoments-push)|整列合并活动行。|
|[`NumpyMoments.finish`](#api-NumpyMoments-finish)|完成自由度和一次目标转换。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import frexp, hypot, ldexp, sqrt
from .types import QualityFlag as Q
```

</details>

<a id="api-NumpyMoments"></a>
## `NumpyMoments`

持有一个锚点、相对均值、根二阶量、总权重和幂指数，跨块大小固定。

```python
NumpyMoments(operation)
```


源码：[`src/chronaxis/core/moments_numpy.py:13`](../../../src/chronaxis/core/moments_numpy.py#L13)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-NumpyMoments-__init__"></a>
### `NumpyMoments.__init__`

初始化归约器。

```python
NumpyMoments.__init__(operation)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。此累计器专用的方差、标准差或均方根操作名，决定跨批维护中心矩或均方。|

#### 返回说明

无。

#### 异常说明

调用侧校验操作。

源码：[`src/chronaxis/core/moments_numpy.py:16`](../../../src/chronaxis/core/moments_numpy.py#L16)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-NumpyMoments-push"></a>
### `NumpyMoments.push`

整列合并活动行。

```python
NumpyMoments.push(values, weights=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|numpy.ndarray|是|无|位置或关键字。本批通过选择、有效性和数值精度检查的有限数值，按输入的物理尺度提交。|
|`weights`|numpy.ndarray &#124; None|否|None|位置或关键字。与本批数值逐项对应的正权重；样本统计省略时每条读数计一次，时间统计传有效时长。|

#### 返回说明

无。

#### 异常说明

非法权重。

源码：[`src/chronaxis/core/moments_numpy.py:22`](../../../src/chronaxis/core/moments_numpy.py#L22)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-NumpyMoments-finish"></a>
### `NumpyMoments.finish`

完成自由度和一次目标转换。

```python
NumpyMoments.finish(ddof, factor)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ddof`|int &#124; None|是|无|位置或关键字。已验证的分母修正，时间总体取零，样本方差或标准差可取一，RMS 省略。|
|`factor`|float|是|无|位置或关键字。自然结果单位到请求输出单位的正倍率，最终按方差或根统计的量纲应用一次。|

#### 返回说明

(值或None,质量)。

#### 异常说明

配置错误。

源码：[`src/chronaxis/core/moments_numpy.py:71`](../../../src/chronaxis/core/moments_numpy.py#L71)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
