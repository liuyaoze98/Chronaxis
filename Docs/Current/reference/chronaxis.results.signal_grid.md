# `chronaxis.results.signal_grid`

把明确选中的连续信号整理为等间隔记录：实测点保留，可靠相邻点之间线性估计，其余位置输出缺失原因。分析规则不会使用这些估计值。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[Interval](chronaxis.core.models.md#api-Interval)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)

## 对象导航

|对象|用途|
|---|---|
|[`SignalGridSpec`](#api-SignalGridSpec)|规定哪些数值信号可以插值、输出间隔和起点、允许的最大原样本间隔。例如每100ms输出一次电压。|
|[`SignalGridSpec.__post_init__`](#api-SignalGridSpec-__post_init__)|核静态网格。|
|[`GridRow`](#api-GridRow)|一个目标点的估计或缺失；左右引用是实际样本，不能伪造为目标点观测。|
|[`_same_fact`](#api-_same_fact)|判断同一时刻两条样本的值、有效性和质量是否相同；不是只比较时间戳。|
|[`SignalGrid`](#api-SignalGrid)|拥有每信号两个有界样本与单调目标游标；push/finish产出必须在下一次push前耗尽。|
|[`SignalGrid.__init__`](#api-SignalGrid-__init__)|核声明并预付有限状态。|
|[`SignalGrid._row`](#api-SignalGrid-_row)|构造单个有限结果。|
|[`SignalGrid._until`](#api-SignalGrid-_until)|输出limit_ns之前的完整有限块。|
|[`SignalGrid._resolve`](#api-SignalGrid-_resolve)|结算已收齐的同一时刻更新。|
|[`SignalGrid.push`](#api-SignalGrid-push)|处理一个连续信号更新，不跨范围借样本。|
|[`SignalGrid.finish`](#api-SignalGrid-finish)|完整EOF后输出剩余真实点及缺后侧网格。|
|[`SignalGrid.close`](#api-SignalGrid-close)|释放保留样本与有限状态，可重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isnan
from ..core.binding import SignalDefinition
from ..core.models import Interval
from ..core.types import SignalDType
from ..core.validation import require_identifier
from ..core.export_interpolation import linear_reference, linear_numpy
from ..timebase.conversion import require_int64_ns
from ..execution.record_sample import RecordSample
from ..execution.history_records import HistorySample, estimate_record_bytes
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .errors import ResultClosedError
```

</details>

<a id="api-SignalGridSpec"></a>
## `SignalGridSpec`

规定哪些数值信号可以插值、输出间隔和起点、允许的最大原样本间隔。例如每100ms输出一次电压。

```python
class SignalGridSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`continuous`|tuple[str, ...]|是|无|本次可插值的原信号别名，须是signals的非空子集，且不重复。填 `["voltage"]` 表示电压可按两端记录作直线估计。|
|`period_ns`|int &#124; None|是|无|正整数纳秒网格间隔，例如100000000表示100ms。|
|`origin_ns`|int|是|无|整数纳秒网格起点；位置按origin_ns+k*period_ns计算。|
|`max_gap_ns`|int|是|无|正整数纳秒；两条实际端点相隔超过该值时不插值。|

源码：[`src/chronaxis/results/signal_grid.py:24`](../../../src/chronaxis/results/signal_grid.py#L24)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGridSpec-__post_init__"></a>
### `SignalGridSpec.__post_init__`

核静态网格。

```python
SignalGridSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/数量/时间或名称非法。

本函数直接报告的具体错误：

- `ValueError`：连续信号需要有限非空tuple。
- `ValueError`：连续信号重复。
- `ValueError`：网格周期和最大间隔必须为正。
- `TypeError`：网格时间需要原生int纳秒。

源码：[`src/chronaxis/results/signal_grid.py:32`](../../../src/chronaxis/results/signal_grid.py#L32)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-GridRow"></a>
## `GridRow`

一个目标点的估计或缺失；左右引用是实际样本，不能伪造为目标点观测。

```python
class GridRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|目标网格时间，整数纳秒。|
|`name`|str|是|无|原信号别名。|
|`unit`|str|是|无|原绑定的输出单位，如V。|
|`value`|int &#124; float &#124; None|是|无|实测或估计数值；missing时为None，CSV写空值而不是0。|
|`status`|str|是|无|observed为实测点，estimated为线性估计，missing为无法得到可靠值。|
|`reason`|str|是|无|具体原因文字，例如missing_left、invalid_neighbor或same_time_conflict。|
|`quality`|int|是|无|左右实际样本质量标志按位合并后的整数。|
|`left`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|目标时间左侧的实际样本；缺少端点时为None，不创建虚构样本。|
|`right`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|目标时间右侧的实际样本；缺少端点时为None，不向范围外寻找端点。|

源码：[`src/chronaxis/results/signal_grid.py:52`](../../../src/chronaxis/results/signal_grid.py#L52)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_same_fact"></a>
## `_same_fact`

判断同一时刻两条样本的值、有效性和质量是否相同；不是只比较时间戳。

```python
_same_fact(left, right)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)|是|无|位置或关键字。同一时间的一条HistorySample，含值、有效标志和质量。|
|`right`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)|是|无|位置或关键字。待比较的另一HistorySample；比较值类型、有效性和质量，也正确比较无效NaN。|

### 返回说明

True表示两条样本的有效性、质量标记、值的类型和内容都相同；两个同类型的NaN也视为相同。否则返回False。

### 异常说明

模型属性错误。

源码：[`src/chronaxis/results/signal_grid.py:66`](../../../src/chronaxis/results/signal_grid.py#L66)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGrid"></a>
## `SignalGrid`

拥有每信号两个有界样本与单调目标游标；push/finish产出必须在下一次push前耗尽。

```python
SignalGrid(spec, definitions, interval, budget, *, backend='numpy', check_cancel=None)
```


源码：[`src/chronaxis/results/signal_grid.py:74`](../../../src/chronaxis/results/signal_grid.py#L74)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGrid-__init__"></a>
### `SignalGrid.__init__`

核声明并预付有限状态。

```python
SignalGrid.__init__(spec, definitions, interval, budget, *, backend='numpy', check_cancel=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[SignalGridSpec](chronaxis.results.signal_grid.md#api-SignalGridSpec)|是|无|位置或关键字。指定连续信号名、网格步长、网格起点和最大插值间隔。|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。导出信号的完整定义；spec.continuous中的每个名字都应在这里找到唯一的数值信号。|
|`interval`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。本次导出的左闭右开时间范围；网格点按origin_ns和period_ns对齐，不从首个样本重新计时。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选无参数回调，供调用者检查取消状态；请求取消时抛异常。None表示不调用额外取消检查。|

#### 返回说明

__init__返回None；使用类名构造时得到已经初始化的对象。后续由该对象管理并关闭自己创建的资源。

#### 异常说明

声明/预算错；持续释放失败附signal_grid_cleanup_owner。

本函数直接报告的具体错误：

- `TypeError`：线性导出需要明确网格、范围和后端。
- `TypeError`：线性导出需要原绑定定义tuple。

源码：[`src/chronaxis/results/signal_grid.py:77`](../../../src/chronaxis/results/signal_grid.py#L77)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGrid-_row"></a>
### `SignalGrid._row`

构造单个有限结果。

```python
SignalGrid._row(state, time_ns, value, status, reason, left, right)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|dict[str, object]|是|无|位置或关键字。当前信号的网格状态，含definition信号定义、next下一网格时刻、left左端样本及冲突状态；在推进时更新。|
|`time_ns`|int|是|无|位置或关键字。当前目标网格时间，整数纳秒。|
|`value`|int &#124; float &#124; None|是|无|位置或关键字。实测值或有限插值结果；该网格点没有可用值时为None。|
|`status`|str|是|无|位置或关键字。"observed"表示原始实测点，"estimated"表示重采样估计点，"missing"表示无法得到有效值。|
|`reason`|str|是|无|位置或关键字。该点实测、估计或缺失的具体原因，写入导出质量说明；例如缺少端点或间隔过大。|
|`left`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|位置或关键字。左端的实际信号样本；不存在时为None，缺端点不作线性外推。|
|`right`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|位置或关键字。右端的实际信号样本；不存在时为None，缺端点不作线性外推。|

#### 返回说明

GridRow。

#### 异常说明

无。

源码：[`src/chronaxis/results/signal_grid.py:107`](../../../src/chronaxis/results/signal_grid.py#L107)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGrid-_until"></a>
### `SignalGrid._until`

输出limit_ns之前的完整有限块。

```python
SignalGrid._until(state, limit_ns, right, conflict)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|dict[str, object]|是|无|位置或关键字。当前信号的网格状态，含definition信号定义、next下一网格时刻、left左端样本及冲突状态；在推进时更新。|
|`limit_ns`|int|是|无|位置或关键字。本次推进的纳秒上限，不包含此时刻；只生成严格早于它的网格点。|
|`right`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|位置或关键字。右端的实际信号样本；不存在时为None，缺端点不作线性外推。|
|`conflict`|bool|是|无|位置或关键字。右端同一时刻样本是否存在未解决冲突；True时不能使用它进行插值。|

#### 返回说明

GridRow迭代。

#### 异常说明

数值/取消错误。

源码：[`src/chronaxis/results/signal_grid.py:114`](../../../src/chronaxis/results/signal_grid.py#L114)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGrid-_resolve"></a>
### `SignalGrid._resolve`

结算已收齐的同一时刻更新。

```python
SignalGrid._resolve(state)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|dict|是|无|位置或关键字。当前信号的内部状态字典，含尚未处理的同一时刻样本、冲突标记、左端点和下个网格位置。|

#### 返回说明

GridRow迭代。

#### 异常说明

数值/预算/取消错误。

源码：[`src/chronaxis/results/signal_grid.py:148`](../../../src/chronaxis/results/signal_grid.py#L148)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGrid-push"></a>
### `SignalGrid.push`

处理一个连续信号更新，不跨范围借样本。

```python
SignalGrid.push(sample)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)|是|无|位置或关键字。sample历史记录。|

#### 返回说明

已确定网格行迭代。

#### 异常说明

声明/顺序/资源错。

本函数直接报告的具体错误：

- `ResultClosedError`：网格已关闭或完成。
- `TypeError`：网格需要所选连续信号历史。
- `ValueError`：网格样本与原绑定不一致。
- `ValueError`：网格输入同信号时间回退。
- `ValueError`：网格同一时刻原序号重复。

源码：[`src/chronaxis/results/signal_grid.py:166`](../../../src/chronaxis/results/signal_grid.py#L166)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGrid-finish"></a>
### `SignalGrid.finish`

完整EOF后输出剩余真实点及缺后侧网格。

```python
SignalGrid.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

GridRow迭代。

#### 异常说明

资源/取消错。

本函数直接报告的具体错误：

- `ResultClosedError`：网格不可再次完成。

源码：[`src/chronaxis/results/signal_grid.py:201`](../../../src/chronaxis/results/signal_grid.py#L201)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalGrid-close"></a>
### `SignalGrid.close`

释放保留样本与有限状态，可重试。

```python
SignalGrid.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原预算释放错误。

源码：[`src/chronaxis/results/signal_grid.py:211`](../../../src/chronaxis/results/signal_grid.py#L211)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
