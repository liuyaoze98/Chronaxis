# `chronaxis.execution.transform_window`

保留一个变换所需的有限真实记录区间，按原端点裁剪滚动窗口。

actual 以实际纳秒度量历史。fixed/dbc 每对真实驱动贡献一个周期，网格
在该对内部按实际经过比例取权重。只存原起止、值和有效截止，不存第二条
累计时间轴，也不为整个观测域预生成网格。缓存由执行者的共享预算预付。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`TransformSpan`](#api-TransformSpan)|保存一个已确定右端的保持区间；更新标志区分真实输入点与普通调度边界。|
|[`first_grid`](#api-first_grid)|找不早于起点的首个原点网格。|
|[`TransformWindow`](#api-TransformWindow)|仅持有最近窗口及其左边界所在原区间。按实际容量付费，关闭可重复。|
|[`TransformWindow.__init__`](#api-TransformWindow-__init__)||
|[`TransformWindow.append`](#api-TransformWindow-append)|记录已确定的真实区间。|
|[`TransformWindow._weight`](#api-TransformWindow-_weight)|将真实子段按原驱动对比例折算。|
|[`TransformWindow.trim`](#api-TransformWindow-trim)|全部不晚于最新区间右端的网格均消费后逐出旧历史。|
|[`TransformWindow.slices`](#api-TransformWindow-slices)|倒序遍历网格左侧窗口。|
|[`TransformWindow.close`](#api-TransformWindow-close)|丢弃窗口与预算。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from ..results.budget import _reserve_owned_ram, _release_owned_ram
```

</details>

<a id="api-TransformSpan"></a>
## `TransformSpan`

保存一个已确定右端的保持区间；更新标志区分真实输入点与普通调度边界。

```python
class TransformSpan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start`|int|是|无|该段左闭起点的实际纳秒。|
|`end`|int|是|无|保持段右开终点的实际纳秒；须大于start。|
|`value`|ScalarValue|是|无|区间内按保持模型使用的数值、质量与部分估值标记。|
|`deadline`|int &#124; None|是|无|当前保持值失效的实际纳秒；有效时长需裁到此处。|
|`update`|bool|是|无|区间左侧是否有真实输入更新，供样本拟合选择实测点。|
|`point`|ScalarValue|是|无|区间起点经过同一时刻原子更新后的点值，与右侧连续视图分别保存。|
|`pair_width`|int &#124; None|否|None|相邻两次原驱动的实际间隔纳秒，用于将组内重叠比例折算为选定周期；未知时为空。|

源码：[`src/chronaxis/execution/transform_window.py:15`](../../../src/chronaxis/execution/transform_window.py#L15)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-first_grid"></a>
## `first_grid`

找不早于起点的首个原点网格。

```python
first_grid(start, origin, step)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start`|int|是|无|位置或关键字。允许输出的实际起始纳秒，返回的网格点不会早于它。|
|`origin`|int|是|无|位置或关键字。该网格的锚点，位于分析时基上；跨块或跨文件保持不变。|
|`step`|int|是|无|位置或关键字。相邻实际网格点的正整数纳秒间隔。|

### 返回说明

整数ns。

### 异常说明

步长非正。

源码：[`src/chronaxis/execution/transform_window.py:26`](../../../src/chronaxis/execution/transform_window.py#L26)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TransformWindow"></a>
## `TransformWindow`

仅持有最近窗口及其左边界所在原区间。按实际容量付费，关闭可重复。

```python
TransformWindow(budget, window_ns, period_ns)
```


源码：[`src/chronaxis/execution/transform_window.py:33`](../../../src/chronaxis/execution/transform_window.py#L33)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TransformWindow-__init__"></a>
### `TransformWindow.__init__`



```python
TransformWindow.__init__(budget, window_ns, period_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。保留窗口内原始区间时逐段预付费用的共享运行账本。|
|`window_ns`|int|是|无|位置或关键字。需要保留的回看宽度，以选定口径的纳秒计量。|
|`period_ns`|int &#124; None|是|无|位置或关键字。原驱动的固定/DBC周期纳秒；为空时直接使用实际时长。|

#### 返回说明

owner。

#### 异常说明

非法窗口。

源码：[`src/chronaxis/execution/transform_window.py:36`](../../../src/chronaxis/execution/transform_window.py#L36)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TransformWindow-append"></a>
### `TransformWindow.append`

记录已确定的真实区间。

```python
TransformWindow.append(span)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`span`|[TransformSpan](chronaxis.execution.transform_window.md#api-TransformSpan)|是|无|位置或关键字。端点连续、长度为正且已知原驱动跨度的真实保持段，要按本窗口口径登记或计量。|

#### 返回说明

无。

#### 异常说明

端点不连续或预算不足。

源码：[`src/chronaxis/execution/transform_window.py:43`](../../../src/chronaxis/execution/transform_window.py#L43)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TransformWindow-_weight"></a>
### `TransformWindow._weight`

将真实子段按原驱动对比例折算。

```python
TransformWindow._weight(span)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`span`|[TransformSpan](chronaxis.execution.transform_window.md#api-TransformSpan)|是|无|位置或关键字。端点连续、长度为正且已知原驱动跨度的真实保持段，要按本窗口口径登记或计量。|

#### 返回说明

有理数纳秒。

#### 异常说明

非正驱动跨度。

源码：[`src/chronaxis/execution/transform_window.py:51`](../../../src/chronaxis/execution/transform_window.py#L51)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TransformWindow-trim"></a>
### `TransformWindow.trim`

全部不晚于最新区间右端的网格均消费后逐出旧历史。

```python
TransformWindow.trim()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

无。

#### 异常说明

退款失败。

源码：[`src/chronaxis/execution/transform_window.py:56`](../../../src/chronaxis/execution/transform_window.py#L56)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TransformWindow-slices"></a>
### `TransformWindow.slices`

倒序遍历网格左侧窗口。

```python
TransformWindow.slices(time)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time`|int|是|无|位置或关键字。网格右边界的实际整数纳秒，从此刻向前裁剪到声明的回看宽度。|

#### 返回说明

(原区间,裁剪左/右,权重倍率)流。

#### 异常说明

结构错误。

源码：[`src/chronaxis/execution/transform_window.py:67`](../../../src/chronaxis/execution/transform_window.py#L67)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TransformWindow-close"></a>
### `TransformWindow.close`

丢弃窗口与预算。

```python
TransformWindow.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

无。

#### 异常说明

退款失败可重试。

源码：[`src/chronaxis/execution/transform_window.py:81`](../../../src/chronaxis/execution/transform_window.py#L81)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
