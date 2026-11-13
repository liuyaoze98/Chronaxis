# `chronaxis.core.temporal_numpy`

按列查找连续TRUE区间和真实边沿，再将匹配结果构造成事件。

输入为完整条件时间组；每批构造成int64时间、内部状态码和uint16诊断列。
布尔掩码找出TRUE区间起止和边沿，整数数组计算持续时长与确认时间。
Python循环负责输入装箱及按活动或匹配点生成Event，不逐点调用参考状态机。
持续候选及边沿前态跨批保留，空批不重置，只在真实会话终点收尾。
默认累计全部事件；主动drain_events仅转交当前输出，finish随后返回剩余未取走事件。
本模块依赖NumPy和核心模型，与参考检测共享协议检查及事件身份，检测算法
独立；不读取来源、不修改输入、不持有全局规则状态。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`NumpyTemporalDetector`](#api-NumpyTemporalDetector)|保存一个规则在一个会话内的开放TRUE区间和边沿前态。|
|[`NumpyTemporalDetector.__init__`](#api-NumpyTemporalDetector-__init__)|校验规则范围并创建全新run/边沿生命周期。|
|[`NumpyTemporalDetector.next_deadline_ns`](#api-NumpyTemporalDetector-next_deadline_ns)|提供当前开放run的精确未确认deadline。|
|[`NumpyTemporalDetector._duration`](#api-NumpyTemporalDetector-_duration)|按布尔掩码寻找TRUE区间并计算门槛，只在活动边界构造事件。|
|[`NumpyTemporalDetector._edges`](#api-NumpyTemporalDetector-_edges)|比较前一连续状态与当前真实点状态，输出已知上升沿或下降沿。|
|[`NumpyTemporalDetector.push`](#api-NumpyTemporalDetector-push)|验证组序后批量检测，空批不改任何跨批状态。|
|[`NumpyTemporalDetector.drain_events`](#api-NumpyTemporalDetector-drain_events)|转交当前未取走的最终事件，保留所有批量run和边沿业务状态。|
|[`NumpyTemporalDetector.finish`](#api-NumpyTemporalDetector-finish)|处理过观测结束标记后结束检测，返回此前尚未取走的事件。|
|[`detect_numpy`](#api-detect_numpy)|真实逐批NumPy检测完整条件轴，跨batch保存run/边沿。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .temporal import ConditionTimeline, make_event
from .temporal_reference import require_batch, require_detector
from .types import QualityFlag as Q, Truth
```

</details>

<a id="api-NumpyTemporalDetector"></a>
## `NumpyTemporalDetector`

保存一个规则在一个会话内的开放TRUE区间和边沿前态。

开放区间的起点、确认时间和诊断跨批保存；内部状态码0、1、2分别表示TRUE、
FALSE和UNKNOWN，只用于数组存储。会话跨度先经过检查，数组时间减法据此
保证范围安全。事件及生命周期属于当前实例，finish后不能继续输入。
start_only边沿候选由数组掩码定位，仅候选索引上的固定窗口抑制保留状态循环；
blocked_until_ns跨批保存，到期不制造边沿，被抑制候选不排队。
drain_events只清空输出，不重置run/前态/抑制或EOF状态；未使用时finish行为不变。

```python
NumpyTemporalDetector(rule, start_ns, end_ns, source_refs=(), *, record_clock=False)
```


源码：[`src/chronaxis/core/temporal_numpy.py:22`](../../../src/chronaxis/core/temporal_numpy.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-NumpyTemporalDetector-__init__"></a>
### `NumpyTemporalDetector.__init__`

校验规则范围并创建全新run/边沿生命周期。

```python
NumpyTemporalDetector.__init__(rule, start_ns, end_ns, source_refs=(), *, record_clock=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|TemporalRule|是|无|位置或关键字。rule、ns域和当前source_refs。|
|`start_ns`|int|是|无|位置或关键字。本次检测请求区间的开始，整数纳秒。|
|`end_ns`|int|是|无|位置或关键字。本次检测请求区间的结束，整数纳秒；连续时间不包含此端点。|
|`source_refs`|tuple[SourceRef, ...]|否|()|位置或关键字。本次事件依赖的原始数据位置。空元组表示没有附加来源定位，不影响事件的开始和结束时间。|
|`record_clock`|bool|否|False|仅关键字。True按实际记录带来的累计步进处理时限；False沿日志真实时间推进，不另存完整计算时间轴。|

#### 返回说明

None，没有共享参考实例或全局缓存。

#### 异常说明

规则/范围/来源结构错误传播。

源码：[`src/chronaxis/core/temporal_numpy.py:33`](../../../src/chronaxis/core/temporal_numpy.py#L33)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-NumpyTemporalDetector-next_deadline_ns"></a>
### `NumpyTemporalDetector.next_deadline_ns`

提供当前开放run的精确未确认deadline。

```python
NumpyTemporalDetector.next_deadline_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；读取当前候选/规则及域。

#### 返回说明

合法ns或None，域外deadline不wrap。

#### 异常说明

无主动异常。

源码：[`src/chronaxis/core/temporal_numpy.py:59`](../../../src/chronaxis/core/temporal_numpy.py#L59)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-NumpyTemporalDetector-_duration"></a>
### `NumpyTemporalDetector._duration`

按布尔掩码寻找TRUE区间并计算门槛，只在活动边界构造事件。

```python
NumpyTemporalDetector._duration(ticks, times, states, diagnostic, advances=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[ConditionTick, ...]|是|无|位置或关键字。已校验的完整时间组。|
|`times`|numpy.ndarray[int64]|是|无|位置或关键字。本批按时间递增的纳秒坐标，逐段检查持续时长是否达到规则要求。|
|`states`|numpy.ndarray|是|无|位置或关键字。与times等长的内部状态码：0为TRUE、1为FALSE、2为UNKNOWN。|
|`diagnostic`|numpy.ndarray|是|无|位置或关键字。与本批条件组对应的QualityFlag位值，记录完整依赖中的质量原因。|
|`advances`|tuple[int, ...] &#124; None|否|None|位置或关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|

#### 返回说明

None: 更新本实例未结束区间、确认时间和最终事件，保留跨批状态。

#### 异常说明

TypeError、ValueError或OverflowError: 事件模型检查失败。
    MemoryError: 数组分配失败；不会丢弃输入继续计算。

#### 边界说明

会话终点不创建新区间；达到门槛的已结束区间输出事件，未结束区间只
    保存状态。输入会话跨度已证明可表示，数组时长及域内确认时间安全。

源码：[`src/chronaxis/core/temporal_numpy.py:75`](../../../src/chronaxis/core/temporal_numpy.py#L75)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-NumpyTemporalDetector-_edges"></a>
### `NumpyTemporalDetector._edges`

比较前一连续状态与当前真实点状态，输出已知上升沿或下降沿。

```python
NumpyTemporalDetector._edges(ticks, times, states, advances=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[ConditionTick, ...]|是|无|位置或关键字。完整时间组，含实际更新证据。|
|`times`|numpy.ndarray[int64]|是|无|位置或关键字。本批纳秒时间轴，用于给上升沿、下降沿和初始化事件定时。|
|`states`|numpy.ndarray|是|无|位置或关键字。与times等长的状态码：0为TRUE、1为FALSE、2为UNKNOWN；比较相邻状态识别边沿。|
|`advances`|tuple[int, ...] &#124; None|否|None|位置或关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|

#### 返回说明

None: 只遍历匹配索引构造点事件；start_only候选执行依赖前次接受触发的
    抑制状态循环，实际边沿定位已数组化，不逐样本推进参考状态机。

#### 异常说明

TypeError、ValueError或OverflowError: 事件模型检查失败。
    MemoryError: 数组分配失败。

#### 边界说明

纯计时器及观测结束不产生边沿；UNKNOWN不能当作FALSE。emit_initial
    仅允许首次已知TRUE的实际更新产生初始化点。

源码：[`src/chronaxis/core/temporal_numpy.py:196`](../../../src/chronaxis/core/temporal_numpy.py#L196)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-NumpyTemporalDetector-push"></a>
### `NumpyTemporalDetector.push`

验证组序后批量检测，空批不改任何跨批状态。

```python
NumpyTemporalDetector.push(ticks, *, advances=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[ConditionTick, ...]|是|无|位置或关键字。ticks完整ConditionTick tuple。|
|`advances`|tuple[int, ...] &#124; None|否|None|仅关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|

#### 返回说明

本批新最终Event tuple；开放run保留实例状态。

#### 异常说明

ValueError为finish后/回退/边界；布局模型错误传播。

本函数直接报告的具体错误：

- `ValueError`：检测器已finish。

源码：[`src/chronaxis/core/temporal_numpy.py:254`](../../../src/chronaxis/core/temporal_numpy.py#L254)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-NumpyTemporalDetector-drain_events"></a>
### `NumpyTemporalDetector.drain_events`

转交当前未取走的最终事件，保留所有批量run和边沿业务状态。

```python
NumpyTemporalDetector.drain_events()
```

参数：无显式参数。


#### 参数说明

无，读取本实例已经产生的events。

#### 返回说明

Event tuple，连续排空允许返回空tuple。

#### 异常说明

MemoryError为tuple构造失败；失败时输出列表保持原内容。

#### 副作用说明

成功只清空events，候选/确认/诊断/前态/抑制及生命周期均不变。

源码：[`src/chronaxis/core/temporal_numpy.py:297`](../../../src/chronaxis/core/temporal_numpy.py#L297)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-NumpyTemporalDetector-finish"></a>
### `NumpyTemporalDetector.finish`

处理过观测结束标记后结束检测，返回此前尚未取走的事件。

```python
NumpyTemporalDetector.finish()
```

参数：无显式参数。


#### 参数说明

无，不能补造EOF或触发额外扫描。

#### 返回说明

尚未drain的Event tuple；未使用drain时仍是全部事件，ID/边界/质量不变。

#### 异常说明

ValueError为缺terminal或重复finish。

本函数直接报告的具体错误：

- `ValueError`：finish需真正terminal且不能重复。

源码：[`src/chronaxis/core/temporal_numpy.py:310`](../../../src/chronaxis/core/temporal_numpy.py#L310)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-detect_numpy"></a>
## `detect_numpy`

真实逐批NumPy检测完整条件轴，跨batch保存run/边沿。

```python
detect_numpy(rule, timeline: ConditionTimeline, *, batch_rows=65536)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|TemporalRule|是|无|位置或关键字。当前时序规则，指定持续条件、边沿或start_only的检测要求。|
|`timeline`|[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)|是|无|位置或关键字。完整条件时间轴，保留同一时刻原子更新、连续状态和终点证据。|
|`batch_rows`|int|否|65536|仅关键字。一次处理的完整时间组数量，必须是正整数；同一时间的更新不能拆到两个批次。|

### 返回说明

稳定Event tuple；不是把reference包在NumPy入口。

### 异常说明

TypeError/ValueError为配置/批大小/模型，检测错误传播。

本函数直接报告的具体错误：

- `TypeError`：detect需timeline及正int batch_rows。

源码：[`src/chronaxis/core/temporal_numpy.py:327`](../../../src/chronaxis/core/temporal_numpy.py#L327)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
