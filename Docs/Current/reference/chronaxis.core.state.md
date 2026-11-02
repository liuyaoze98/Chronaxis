# chronaxis.core.state

检查内存样本的原行身份，并按有限有效期查询最新观测或提交同一时刻更新。

输入为当前SignalBindings下的规范样本和纳秒查询轴；输出SignalSeries、
StateValue或完整TimeGroup。先检查身份、声明类型及同时间冲突，再取最新更新，
结合有效期和来源、会话范围判断能否使用。无效更新同样覆盖历史，不能回退
取更早有效值。同一时刻多列更新先收齐，再交给调用者求值一次。
本模块只依赖标准库，没有文件操作或全局状态；不执行单位转换或表达式计算。
NumPy保持实现位于state_numpy，数值对齐算法独立。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalSample](chronaxis.core.models.md#api-SignalSample)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)

## 对象导航

|对象|用途|
|---|---|
|[`_collapse`](#api-_collapse)|解析同一别名同时间候选，保留稳定原序号及冲突数量。|
|[`SignalSeries`](#api-SignalSeries)|保存一个信号别名的规范内存观测，以及来源范围和同一时刻冲突计数。|
|[`SignalSeries.__post_init__`](#api-SignalSeries-__post_init__)|校验样本原身份、dtype、顺序，规范同时间候选并冻结来源域。|
|[`StateValue`](#api-StateValue)|保存某个查询时刻的最新观测、可用性和质量原因。|
|[`align_reference`](#api-align_reference)|逐查询点取得最新历史观测，再检查有效期和来源、会话范围。|
|[`_require_series_group`](#api-_require_series_group)|检查局部依赖结构、同绑定和同步，不分配完整时间轴。|
|[`common_timeline`](#api-common_timeline)|构造当前依赖的更新、TTL及来源/会话边界共同轴。|
|[`TimeGroup`](#api-TimeGroup)|保存一个分析时刻所有信号真实更新，供求值一次使用。|
|[`AtomicUpdateBuffer`](#api-AtomicUpdateBuffer)|跨批收集同时间的信号更新，收齐后输出一次完整求值组。|
|[`AtomicUpdateBuffer.__init__`](#api-AtomicUpdateBuffer-__init__)|为当前会话创建空缓冲，用于收齐同一时刻的信号更新。|
|[`AtomicUpdateBuffer._commit`](#api-AtomicUpdateBuffer-_commit)|把缓冲中同一时刻的全部更新一起整理成一组，供表达式计算。|
|[`AtomicUpdateBuffer.push`](#api-AtomicUpdateBuffer-push)|接收一批按时间排列的更新，返回已经收齐的时间组；尚未收齐的末组继续留在缓冲。|
|[`AtomicUpdateBuffer.finish`](#api-AtomicUpdateBuffer-finish)|在完整输入EOF提交最后时间组并关闭当前会话缓冲。|
|[`iter_time_groups`](#api-iter_time_groups)|按时间合并内存中的信号更新，同一时刻的更新即使分在不同批次，也收齐后一起返回。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from heapq import merge
from math import isnan
from .binding import SignalBindings
from .models import SignalSample, SourceSpec
from .types import QualityFlag, SignalDType
from ..timebase.conversion import checked_add_ns, require_int64_ns
```

</details>

<a id="api-_collapse"></a>
## `_collapse`

解析同一别名同时间候选，保留稳定原序号及冲突数量。

```python
_collapse(bindings: SignalBindings, samples: tuple[SignalSample, ...]) -> tuple[SignalSample, int]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)|是|无|位置或关键字。bindings为当前冻结引用|
|`samples`|tuple[[SignalSample](chronaxis.core.models.md#api-SignalSample), ...]|是|无|位置或关键字。samples为非空、同名同时间带有明确类型的候选。|

### 返回说明

选定SignalSample及不同事实被显式覆盖的候选数。

### 异常说明

ValueError为默认error下不同事实冲突；不静默按遍历顺序选值。

返回类型：tuple[[SignalSample](chronaxis.core.models.md#api-SignalSample), int]。

源码：[`src/chronaxis/core/state.py:28`](../../../src/chronaxis/core/state.py#L28)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalSeries"></a>
## `SignalSeries`

保存一个信号别名的规范内存观测，以及来源范围和同一时刻冲突计数。

样本先按原顺序检查时间非递减，再按声明策略处理同一时刻候选，构造结果时间
严格递增。有效值符合声明类型，无效原值保留作诊断。未声明的来源端点取
实际首末行，不补采样周期。序列使用当前冻结绑定，没有全局执行缓存；
原行转换由数值层提供。

```python
class SignalSeries
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)|是|无|当前计划与会话引用。|
|`name`|str|是|无|当前原信号别名。|
|`samples`|tuple[[SignalSample](chronaxis.core.models.md#api-SignalSample), ...]|是|无|已规范化带有明确类型的样本，包含无效更新。|
|`source`|[SourceSpec](chronaxis.core.models.md#api-SourceSpec)|不填写|构造时计算|校验所得实际来源。|
|`observation_start_ns`|int|不填写|构造时计算|分析坐标来源首端。|
|`observation_end_ns`|int|不填写|构造时计算|分析坐标来源末端。|
|`conflict_count`|int|不填写|构造时计算|last_by_sequence显式覆盖数量。|

源码：[`src/chronaxis/core/state.py:53`](../../../src/chronaxis/core/state.py#L53)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalSeries-__post_init__"></a>
### `SignalSeries.__post_init__`

校验样本原身份、dtype、顺序，规范同时间候选并冻结来源域。

```python
SignalSeries.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；bindings/name为真实引用，samples为tuple规范化观测。

#### 返回说明

None；只在构造时规范同时间组，不丢失无效状态。

#### 异常说明

TypeError为结构/dtype；ValueError为归属/原序号/顺序/冲突；
    时间溢出异常由既有时间协议传播。

本函数直接报告的具体错误：

- `TypeError`：SignalSeries需要SignalBindings和tuple samples。
- `TypeError`：samples必须包含SignalSample。
- `ValueError`：样本别名/来源与当前序列不一致。
- `ValueError`：样本原序号不存在或重复。
- `ValueError`：样本不能定位对应原行时间/字段。
- `ValueError`：序列时间必须非递减。

返回类型：None。

源码：[`src/chronaxis/core/state.py:70`](../../../src/chronaxis/core/state.py#L70)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-StateValue"></a>
## `StateValue`

保存某个查询时刻的最新观测、可用性和质量原因。

sample用于追溯原时间、序号和来源；最新更新无效时保留它，不回退旧值。
没有历史时value为None。actual_update只表示查询点恰好有真实样本更新，
有效期到期或观测结束不能伪造更新。point模式可以包含真实末点，连续模式
排除末端，两者均在有效期右端失效。结果不会修改原样本。

```python
class StateValue
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|本次查询的分析纳秒坐标。|
|`value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|最新观测或没有历史时None。|
|`valid`|bool|是|无|质量/TTL/观测范围均满足才可使用。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|是|无|保留输入原因并叠加缺失/过期。|
|`sample`|[SignalSample](chronaxis.core.models.md#api-SignalSample) &#124; None|是|无|最新实际观测；不回退旧有效值。|
|`actual_update`|bool|是|无|该点是否真正发生更新。|

源码：[`src/chronaxis/core/state.py:161`](../../../src/chronaxis/core/state.py#L161)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-align_reference"></a>
## `align_reference`

逐查询点取得最新历史观测，再检查有效期和来源、会话范围。

```python
align_reference(series: SignalSeries, times_ns: tuple[int, ...], *, point: bool=False, strict_before: bool=False) -> tuple[StateValue, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[SignalSeries](chronaxis.core.state.md#api-SignalSeries)|是|无|位置或关键字。当前绑定下已经检查的规范序列。|
|`times_ns`|tuple[int, ...]|是|无|位置或关键字。非递减int64纳秒查询轴，允许空轴和重复点。|
|`point`|bool|否|False|仅关键字。默认False，使用左闭右开连续范围；True包含来源及会话 的真实末端，但有效期右端始终排除。|
|`strict_before`|bool|否|False|仅关键字。默认False；True只取sample_time < t的样本， 仍在当前t检查有效期，用来区分实际更新与同一时刻到期。|

### 返回说明

tuple[StateValue, ...]: 每个查询点一个结果；无历史为MISSING，过期为STALE。
    最新无效更新不会被更早有效值替代，空轴返回空tuple。

### 异常说明

TypeError: 序列、查询容器或模式标志类型错误，或者时间不是非布尔整数。
    ValueError: 查询时间回退。
    TimeOverflowError: 查询坐标超出int64范围。

### 副作用说明

仅使用局部游标和结果集合，不调用NumPy对齐，不修改输入。

返回类型：tuple[[StateValue](chronaxis.core.state.md#api-StateValue), ...]。

源码：[`src/chronaxis/core/state.py:178`](../../../src/chronaxis/core/state.py#L178)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_require_series_group"></a>
## `_require_series_group`

检查局部依赖结构、同绑定和同步，不分配完整时间轴。

```python
_require_series_group(series: tuple[SignalSeries, ...]) -> SignalBindings
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|tuple[[SignalSeries](chronaxis.core.state.md#api-SignalSeries), ...]|是|无|位置或关键字。series为同一冻结绑定下非空tuple SignalSeries。|

### 返回说明

当前SignalBindings；空间只与局部依赖列数有关。

### 异常说明

TypeError为结构；ValueError为不同绑定或同步缺项。

本函数直接报告的具体错误：

- `TypeError`：共同轴需要非空tuple SignalSeries。
- `ValueError`：共同轴序列必须来自同一绑定。

返回类型：[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)。

源码：[`src/chronaxis/core/state.py:250`](../../../src/chronaxis/core/state.py#L250)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-common_timeline"></a>
## `common_timeline`

构造当前依赖的更新、TTL及来源/会话边界共同轴。

```python
common_timeline(series: tuple[SignalSeries, ...], extra_ns: tuple[int, ...]=()) -> tuple[int, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|tuple[[SignalSeries](chronaxis.core.state.md#api-SignalSeries), ...]|是|无|位置或关键字。series为同一绑定下所需序列tuple|
|`extra_ns`|tuple[int, ...]|否|()|位置或关键字。extra_ns为后续规则deadline/window边界。|

### 返回说明

排序唯一tuple int64纳秒，限制在会话闭域以保留末点上下文。

### 异常说明

TypeError/ValueError为结构或不同绑定；时间错误传播。

本函数直接报告的具体错误：

- `TypeError`：extra_ns必须为tuple。

### 副作用说明

显式分配当前依赖共同轴，归并入口不调用本生成操作。

返回类型：tuple[int, ...]。

源码：[`src/chronaxis/core/state.py:273`](../../../src/chronaxis/core/state.py#L273)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-TimeGroup"></a>
## `TimeGroup`

保存一个分析时刻所有信号真实更新，供求值一次使用。

不在逐条样本之间求值；updates按冻结定义顺序排列，保持原样本身份。

```python
class TimeGroup
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|该组公共分析坐标。|
|`updates`|tuple[[SignalSample](chronaxis.core.models.md#api-SignalSample), ...]|是|无|各信号最多一项，冲突已处理。|
|`conflict_count`|int|否|0|本组显式last_by_sequence处理数量。|

源码：[`src/chronaxis/core/state.py:314`](../../../src/chronaxis/core/state.py#L314)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-AtomicUpdateBuffer"></a>
## `AtomicUpdateBuffer`

跨批收集同时间的信号更新，收齐后输出一次完整求值组。

看到更大时间或完整输入finish后才提交当前组，普通批末保留_pending。
输入须已经按时间归并并完成归一化；本类不读取来源或排序。finish后实例
关闭，新会话须创建新实例。缓冲大小取决于同一时刻更新数量；生产预算由上层
执行入口约束，不能只凭分批就认为整体内存有界。

```python
AtomicUpdateBuffer(bindings: SignalBindings)
```


源码：[`src/chronaxis/core/state.py:325`](../../../src/chronaxis/core/state.py#L325)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-AtomicUpdateBuffer-__init__"></a>
### `AtomicUpdateBuffer.__init__`

为当前会话创建空缓冲，用于收齐同一时刻的信号更新。

```python
AtomicUpdateBuffer.__init__(bindings: SignalBindings)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)|是|无|位置或关键字。bindings为当前真实冻结引用。|

#### 返回说明

None；pending空，closed=False，无全局状态。

#### 异常说明

TypeError为非绑定输入。

本函数直接报告的具体错误：

- `TypeError`：buffer需要SignalBindings。

源码：[`src/chronaxis/core/state.py:334`](../../../src/chronaxis/core/state.py#L334)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-AtomicUpdateBuffer-_commit"></a>
### `AtomicUpdateBuffer._commit`

把缓冲中同一时刻的全部更新一起整理成一组，供表达式计算。

```python
AtomicUpdateBuffer._commit() -> TimeGroup
```

参数：无显式参数。


#### 参数说明

无；pending须非空且同时间。

#### 返回说明

TimeGroup，信号按定义顺序，显式冲突有计数。

#### 异常说明

ValueError为默认冲突；只修改当前pending。

返回类型：[TimeGroup](chronaxis.core.state.md#api-TimeGroup)。

源码：[`src/chronaxis/core/state.py:354`](../../../src/chronaxis/core/state.py#L354)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-AtomicUpdateBuffer-push"></a>
### `AtomicUpdateBuffer.push`

接收一批按时间排列的更新，返回已经收齐的时间组；尚未收齐的末组继续留在缓冲。

```python
AtomicUpdateBuffer.push(samples: tuple[SignalSample, ...]) -> tuple[TimeGroup, ...]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`samples`|tuple[[SignalSample](chronaxis.core.models.md#api-SignalSample), ...]|是|无|位置或关键字。samples为非递减tuple样本，可为空，batch尾可处于未完成同时间组。|

#### 返回说明

tuple TimeGroup；最后时间仍留pending，不能在batch尾提前求值。

#### 异常说明

TypeError为结构；ValueError为已finish、归属/回退/冲突。

本函数直接报告的具体错误：

- `ValueError`：buffer已finish，需新会话实例。
- `TypeError`：samples batch必须为tuple。
- `ValueError`：buffer样本绑定不匹配。
- `ValueError`：buffer同组原序号重复。
- `ValueError`：buffer时间回退。

返回类型：tuple[[TimeGroup](chronaxis.core.state.md#api-TimeGroup), ...]。

源码：[`src/chronaxis/core/state.py:386`](../../../src/chronaxis/core/state.py#L386)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-AtomicUpdateBuffer-finish"></a>
### `AtomicUpdateBuffer.finish`

在完整输入EOF提交最后时间组并关闭当前会话缓冲。

```python
AtomicUpdateBuffer.finish() -> tuple[TimeGroup, ...]
```

参数：无显式参数。


#### 参数说明

无；调用者已证明所有参与来源输入结束。

#### 返回说明

剩余一个TimeGroup或空tuple。

#### 异常说明

ValueError为重复finish或未处理冲突；batch尾不能调用本方法。

本函数直接报告的具体错误：

- `ValueError`：buffer不能重复finish。

返回类型：tuple[[TimeGroup](chronaxis.core.state.md#api-TimeGroup), ...]。

源码：[`src/chronaxis/core/state.py:436`](../../../src/chronaxis/core/state.py#L436)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-iter_time_groups"></a>
## `iter_time_groups`

按时间合并内存中的信号更新，同一时刻的更新即使分在不同批次，也收齐后一起返回。

```python
iter_time_groups(series: tuple[SignalSeries, ...], batch_rows: int=65536)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|tuple[[SignalSeries](chronaxis.core.state.md#api-SignalSeries), ...]|是|无|位置或关键字。series为同绑定、不同别名的规范序列tuple|
|`batch_rows`|int|否|65536|位置或关键字。batch_rows为正原生整数。|

### 返回说明

逐个yield TimeGroup；完整内存输入结束后才提交最后组。

### 异常说明

TypeError/ValueError为结构/不同绑定/重复列/批次参数或冲突。

本函数直接报告的具体错误：

- `ValueError`：归并序列别名重复。
- `ValueError`：batch_rows必须为正原生整数。

### 副作用说明

只维护局部heap/一批/pending，不读取旧日志或改样本顺序。

源码：[`src/chronaxis/core/state.py:455`](../../../src/chronaxis/core/state.py#L455)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

## 内部匿名回调


<a id="lambda-36"></a>
### 第36行匿名函数

```python
lambda sample: sample.sequence
```

|参数|含义|返回/异常|
|---|---|---|
|`sample`|已规范化的信号样本。|返回样本sequence以选择同刻最后更新。|

<a id="lambda-476"></a>
### 第476行匿名函数

```python
lambda sample: sample.time_ns
```

|参数|含义|返回/异常|
|---|---|---|
|`sample`|已规范化的信号样本。|返回样本time_ns，以时间合并各个已排序样本流。|
