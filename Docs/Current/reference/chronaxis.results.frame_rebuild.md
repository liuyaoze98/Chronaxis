# chronaxis.results.frame_rebuild

用同次读取中已解码的连续物理量，在指定时间网格上生成报文。只改选中字段的位，其他位复制同一最近原帧；未选报文默认原样透传。见[导出限制](../exports.md)。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DBCFramePatch](chronaxis.results.frame_patch.md#api-DBCFramePatch)、[ExportCANFrame](chronaxis.results.frame_exports.md#api-ExportCANFrame)、[FrameRebuildRule](chronaxis.results.frame_patch.md#api-FrameRebuildRule)、[FrameSort](chronaxis.results.frame_sort.md#api-FrameSort)、[Interval](chronaxis.core.models.md#api-Interval)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SkippedCANFrame](chronaxis.results.frame_exports.md#api-SkippedCANFrame)

## 对象导航

|对象|用途|
|---|---|
|[`FrameSample`](#api-FrameSample)|一条用于重建的原帧及其已解码字段。layout记录DBC复用选择器的原始整数码，用来判断两端是否属于同一字段布局。|
|[`FrameSample.__post_init__`](#api-FrameSample-__post_init__)|核冻结值与定位结构。|
|[`FrameGridSpec`](#api-FrameGridSpec)|规定输出报文的等间隔时间点，以及两条原帧最多相隔多久还能插值；未选报文可按原时间保留或取最近整帧。|
|[`FrameGridSpec.__post_init__`](#api-FrameGridSpec-__post_init__)|核网格与未知报文策略。|
|[`_frame_packet`](#api-_frame_packet)|编码固定原帧及定位结构。|
|[`_restore_frame`](#api-_restore_frame)|恢复本次认证暂存的固定原帧。|
|[`_sample_packet`](#api-_sample_packet)|保存无效NaN等诊断而不输出非法JSON。|
|[`_restore_sample`](#api-_restore_sample)|恢复已认证样本，不加载DBC。|
|[`_facts`](#api-_facts)|把实际载荷、解码值、布局和有效性整理成可比较的内容，判断同一时刻样本是否冲突；忽略仅用于定位的序号。|
|[`FrameRebuildRead`](#api-FrameRebuildRead)|逐条读取同次采集的帧，按报文种类分组并生成所需网格帧。先完成并排序，再允许调用者逐条取结果；关闭时释放输入与暂存句柄。|
|[`FrameRebuildRead.__init__`](#api-FrameRebuildRead-__init__)|静态核配置并预约资源。|
|[`FrameRebuildRead._cancel`](#api-FrameRebuildRead-_cancel)|检查已关闭及用户取消。|
|[`FrameRebuildRead._output`](#api-FrameRebuildRead-_output)|保存真实/生成/未生成结果到时间排序。|
|[`FrameRebuildRead.prepare`](#api-FrameRebuildRead-prepare)|单次消费同次样本，按身份重建并封口时间序列。|
|[`FrameRebuildRead._group`](#api-FrameRebuildRead-_group)|保相邻两个同一时刻组并处理全部网格。|
|[`FrameRebuildRead._reason`](#api-FrameRebuildRead-_reason)|确定整个两点间隔是否可插值。|
|[`FrameRebuildRead._skip`](#api-FrameRebuildRead-_skip)|记录整个目标帧未生成，不补任一物理字段。|
|[`FrameRebuildRead._emit`](#api-FrameRebuildRead-_emit)|从同一基础帧生成目标并保完整两端引用。|
|[`FrameRebuildRead._nearest`](#api-FrameRebuildRead-_nearest)|未知报文整帧最近邻，等距选左且不越最大距离。|
|[`FrameRebuildRead._segment`](#api-FrameRebuildRead-_segment)|每块最多256网格点计算连续量，实点另外保原字节。|
|[`FrameRebuildRead.__iter__`](#api-FrameRebuildRead-__iter__)|准备完成后开放一个时间游标。|
|[`FrameRebuildRead.export_metadata`](#api-FrameRebuildRead-export_metadata)|返回本次已完成重建的有限清单事实。|
|[`FrameRebuildRead.__next__`](#api-FrameRebuildRead-__next__)|恢复下一生成/透传帧或缺失说明。|
|[`FrameRebuildRead._close_input`](#api-FrameRebuildRead-_close_input)|真正关闭源样本游标。|
|[`FrameRebuildRead.close`](#api-FrameRebuildRead-close)|关闭输入流、排序文件和DBC字段编码对象，释放本对象登记的内存；保留诊断文件。关闭失败会抛出原异常，调用者可重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import groupby
from math import isfinite
from pathlib import Path
from ..core.export_interpolation import linear_reference, linear_numpy
from ..core.models import Interval
from ..execution.history import _metadata_bytes
from ..legacy.records import frame_to_dict, frame_from_dict
from ..timebase.conversion import require_int64_ns, checked_add_ns
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .codec import _pack, _unpack
from .errors import ResultClosedError
from .frame_exports import ExportCANFrame, SkippedCANFrame
from .frame_patch import FrameRebuildRule, DBCFramePatch
from .frame_sort import FrameSort
```

</details>

<a id="api-FrameSample"></a>
## `FrameSample`

一条用于重建的原帧及其已解码字段。layout记录DBC复用选择器的原始整数码，用来判断两端是否属于同一字段布局。

```python
class FrameSample
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[ExportCANFrame](chronaxis.results.frame_exports.md#api-ExportCANFrame)|是|无|包含原报文及来源信息的ExportCANFrame。|
|`values`|tuple[tuple[str, int &#124; float &#124; bool &#124; None], ...]|否|()|(DBC字段名, 已解码物理值)元组；不在这里重新解码。|
|`layout`|tuple[tuple[str, int], ...]|否|()|(复用选择器字段名, 原始整数码)元组；例如某选择器为1表示一组字段布局，码变2时不能跨布局插值。|
|`known`|bool|否|False|本次读取是否在DBC中识别出该报文，默认False。|
|`valid`|bool|否|True|该帧是否可作为重建端点，默认True；False使相关区间不插值。|

源码：[`src/chronaxis/results/frame_rebuild.py:31`](../../../src/chronaxis/results/frame_rebuild.py#L31)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSample-__post_init__"></a>
### `FrameSample.__post_init__`

核冻结值与定位结构。

```python
FrameSample.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/重复字段/布局非法。

本函数直接报告的具体错误：

- `TypeError`：重建样本需要真实导出帧和明确布尔事实。
- `ValueError`：重建样本字段超过有限能力。
- `ValueError`：重建样本字段重复或类型非法。

源码：[`src/chronaxis/results/frame_rebuild.py:40`](../../../src/chronaxis/results/frame_rebuild.py#L40)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameGridSpec"></a>
## `FrameGridSpec`

规定输出报文的等间隔时间点，以及两条原帧最多相隔多久还能插值；未选报文可按原时间保留或取最近整帧。

```python
class FrameGridSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`period_ns`|int &#124; None|是|无|正整数纳秒网格间隔，例如100000000表示100ms。|
|`origin_ns`|int|是|无|整数纳秒网格起点；位置按origin_ns+k*period_ns计算。|
|`max_gap_ns`|int|是|无|正整数纳秒；两条实际端点相隔超过该值时不插值。|
|`unknown_policy`|str|否|'passthrough'|passthrough按原时间透传未选择报文；nearest按网格取最近完整原帧。|
|`max_distance_ns`|int &#124; None|否|None|nearest时必须给出的非负整数纳秒距离上限；超过时不生成，默认None。|

源码：[`src/chronaxis/results/frame_rebuild.py:56`](../../../src/chronaxis/results/frame_rebuild.py#L56)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameGridSpec-__post_init__"></a>
### `FrameGridSpec.__post_init__`

核网格与未知报文策略。

```python
FrameGridSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

非法时间/策略/距离。

本函数直接报告的具体错误：

- `ValueError`：需要正网格/间隔和显式未知策略。
- `ValueError`：未知报文最近邻必须声明最大距离。
- `ValueError`：最近邻距离不能为负。

源码：[`src/chronaxis/results/frame_rebuild.py:65`](../../../src/chronaxis/results/frame_rebuild.py#L65)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_frame_packet"></a>
## `_frame_packet`

编码固定原帧及定位结构。

```python
_frame_packet(record)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[ExportCANFrame](chronaxis.results.frame_exports.md#api-ExportCANFrame)|是|无|位置或关键字。ExportCANFrame，含原帧字节、两个时间坐标、序号、来源与生成类型。|

### 返回说明

JSON dict。

### 异常说明

原模型非法。

源码：[`src/chronaxis/results/frame_rebuild.py:83`](../../../src/chronaxis/results/frame_rebuild.py#L83)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_restore_frame"></a>
## `_restore_frame`

恢复本次认证暂存的固定原帧。

```python
_restore_frame(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|[ExportCANFrame](chronaxis.results.frame_exports.md#api-ExportCANFrame)|是|无|位置或关键字。由_frame_packet生成并经暂存完整性检查的字典；恢复ExportCANFrame。|

### 返回说明

ExportCANFrame。

### 异常说明

非法模型。

源码：[`src/chronaxis/results/frame_rebuild.py:98`](../../../src/chronaxis/results/frame_rebuild.py#L98)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_sample_packet"></a>
## `_sample_packet`

保存无效NaN等诊断而不输出非法JSON。

```python
_sample_packet(sample)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample)|是|无|位置或关键字。FrameSample，含原导出帧、解码值、复用布局、是否识别及有效性。|

### 返回说明

固定dict。

### 异常说明

编码错。

源码：[`src/chronaxis/results/frame_rebuild.py:109`](../../../src/chronaxis/results/frame_rebuild.py#L109)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_restore_sample"></a>
## `_restore_sample`

恢复已认证样本，不加载DBC。

```python
_restore_sample(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample)|是|无|位置或关键字。由_sample_packet生成的字典；恢复FrameSample，不重读DBC或解码。|

### 返回说明

FrameSample。

### 异常说明

结构错。

源码：[`src/chronaxis/results/frame_rebuild.py:116`](../../../src/chronaxis/results/frame_rebuild.py#L116)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_facts"></a>
## `_facts`

把实际载荷、解码值、布局和有效性整理成可比较的内容，判断同一时刻样本是否冲突；忽略仅用于定位的序号。

```python
_facts(sample)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample)|是|无|位置或关键字。待比较的FrameSample；序号和来源不参与值相等判断，实际载荷、布局和值有效性参与。|

### 返回说明

有限JSON。

### 异常说明

编码错。

源码：[`src/chronaxis/results/frame_rebuild.py:123`](../../../src/chronaxis/results/frame_rebuild.py#L123)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead"></a>
## `FrameRebuildRead`

逐条读取同次采集的帧，按报文种类分组并生成所需网格帧。先完成并排序，再允许调用者逐条取结果；关闭时释放输入与暂存句柄。

```python
FrameRebuildRead(records, spec, interval, rules, budget, work_dir, *, backend='numpy', check_cancel=None, periods=None, integrity=True, trace=True)
```


源码：[`src/chronaxis/results/frame_rebuild.py:130`](../../../src/chronaxis/results/frame_rebuild.py#L130)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-__init__"></a>
### `FrameRebuildRead.__init__`

静态核配置并预约资源。

```python
FrameRebuildRead.__init__(records, spec, interval, rules, budget, work_dir, *, backend='numpy', check_cancel=None, periods=None, integrity=True, trace=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`records`|tuple|是|无|位置或关键字。records、网格/范围、(rule,已加载Message)tuple、预算/新目录、后端/取消。|
|`spec`|[FrameGridSpec](chronaxis.results.frame_rebuild.md#api-FrameGridSpec)|是|无|位置或关键字。本次FrameGridSpec，包含网格及间隔限制。|
|`interval`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。允许输出的左闭右开Interval；不借用此范围之外的端点。|
|`rules`|tuple|是|无|位置或关键字。(FrameRebuildRule, 已加载cantools Message)二元组的元组。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。|
|`backend`|str|否|'numpy'|仅关键字。reference或numpy，选择数值计算实现；不改变插值、缺失或时间边界的定义。|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选的无参取消检查函数。需要终止时由它抛出异常；None表示不额外调用取消检查。|
|`periods`|Mapping[tuple, int] &#124; None|否|None|仅关键字。原帧重建所需各报文的正纳秒周期；None沿用统一固定网格。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|
|`trace`|bool|否|True|仅关键字。是否保存此功能的详细来源或输入追溯；False在生成处跳过，不能先构造再隐藏。|

#### 返回说明

可关闭重建owner。

#### 异常说明

配置/预算/I/O错，清理失败附frame_rebuild_cleanup_owner。

本函数直接报告的具体错误：

- `ValueError`：报文重建需要网格、范围及明确后端。
- `ValueError`：重建规则需要有限(rule,Message)tuple。
- `ValueError`：不能对同一报文身份声明两个重建规则。
- `ValueError`：报文重建不能写RefProjects。

源码：[`src/chronaxis/results/frame_rebuild.py:133`](../../../src/chronaxis/results/frame_rebuild.py#L133)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_cancel"></a>
### `FrameRebuildRead._cancel`

检查已关闭及用户取消。

```python
FrameRebuildRead._cancel()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭/取消。

本函数直接报告的具体错误：

- `ResultClosedError`：报文重建已关闭。

源码：[`src/chronaxis/results/frame_rebuild.py:186`](../../../src/chronaxis/results/frame_rebuild.py#L186)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_output"></a>
### `FrameRebuildRead._output`

保存真实/生成/未生成结果到时间排序。

```python
FrameRebuildRead._output(item, identity=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`item`|[SkippedCANFrame](chronaxis.results.frame_exports.md#api-SkippedCANFrame)|是|无|位置或关键字。item和有限身份。|
|`identity`|tuple|否|()|位置或关键字。报文身份元组（通道、ID、扩展标志、FD标志），用于稳定排序和错误定位。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

排序/配额错。

源码：[`src/chronaxis/results/frame_rebuild.py:194`](../../../src/chronaxis/results/frame_rebuild.py#L194)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-prepare"></a>
### `FrameRebuildRead.prepare`

单次消费同次样本，按身份重建并封口时间序列。

```python
FrameRebuildRead.prepare()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

self。

#### 异常说明

输入/解码事实/排序/预算/取消。

本函数直接报告的具体错误：

- `TypeError`：报文重建需要同次FrameSample流。
- `ValueError`：原帧时间或原序回退，不能借离线排序掩盖输入错误。
- `ValueError`：已选报文缺真实DBC解码身份或长度异常。

源码：[`src/chronaxis/results/frame_rebuild.py:209`](../../../src/chronaxis/results/frame_rebuild.py#L209)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_group"></a>
### `FrameRebuildRead._group`

保相邻两个同一时刻组并处理全部网格。

```python
FrameRebuildRead._group(samples, patcher, identity)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`samples`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample)|是|无|位置或关键字。同一个报文身份的FrameSample流，按时间/原序号处理。|
|`patcher`|[DBCFramePatch](chronaxis.results.frame_patch.md#api-DBCFramePatch) &#124; None|是|无|位置或关键字。按DBC位定义写入指定信号的对象；None表示整帧最近邻复制，不修改帧内信号字段。|
|`identity`|tuple|是|无|位置或关键字。报文身份元组（通道、ID、扩展标志、FD标志），用于稳定排序和错误定位。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原重建错。

源码：[`src/chronaxis/results/frame_rebuild.py:283`](../../../src/chronaxis/results/frame_rebuild.py#L283)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_reason"></a>
### `FrameRebuildRead._reason`

确定整个两点间隔是否可插值。

```python
FrameRebuildRead._reason(left, right, left_bad, right_bad, patcher)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample) &#124; None|是|无|位置或关键字。左侧的实际帧样本；缺少该端点时为None，不从观测范围之外补帧。|
|`right`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample) &#124; None|是|无|位置或关键字。右侧的实际帧样本；缺少该端点时为None，不从观测范围之外补帧。|
|`left_bad`|bool|是|无|位置或关键字。左端同一时刻是否存在无法按配置解决的值冲突；True时不能把它当作有效插值端点。|
|`right_bad`|bool|是|无|位置或关键字。右端同一时刻是否存在无法按配置解决的值冲突；True时不能把它当作有效插值端点。|
|`patcher`|[DBCFramePatch](chronaxis.results.frame_patch.md#api-DBCFramePatch) &#124; None|是|无|位置或关键字。按DBC位定义写入指定信号的对象；None表示整帧最近邻复制，不修改帧内信号字段。|

#### 返回说明

原因或None。

#### 异常说明

非法DBC布局。

源码：[`src/chronaxis/results/frame_rebuild.py:308`](../../../src/chronaxis/results/frame_rebuild.py#L308)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_skip"></a>
### `FrameRebuildRead._skip`

记录整个目标帧未生成，不补任一物理字段。

```python
FrameRebuildRead._skip(time_ns, reason, identity)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。不能生成报文的目标网格时间，整数纳秒。|
|`reason`|str|是|无|位置或关键字。原因文字，例如缺少端点、间隔过大、同一时刻冲突。|
|`identity`|tuple|是|无|位置或关键字。报文身份元组，用于指出哪条通道/ID/帧类型不能生成。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

输出错。

源码：[`src/chronaxis/results/frame_rebuild.py:334`](../../../src/chronaxis/results/frame_rebuild.py#L334)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_emit"></a>
### `FrameRebuildRead._emit`

从同一基础帧生成目标并保完整两端引用。

```python
FrameRebuildRead._emit(time_ns, base, left, right, patcher, values, identity, mode)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。当前目标网格位置，整数纳秒。|
|`base`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample)|是|无|位置或关键字。选定的最近实际FrameSample；不改写字段的位全部从这一帧复制。|
|`left`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample) &#124; None|是|无|位置或关键字。左侧的实际帧样本；缺少该端点时为None，不从观测范围之外补帧。|
|`right`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample) &#124; None|是|无|位置或关键字。右侧的实际帧样本；缺少该端点时为None，不从观测范围之外补帧。|
|`patcher`|[DBCFramePatch](chronaxis.results.frame_patch.md#api-DBCFramePatch) &#124; None|是|无|位置或关键字。按DBC位定义写入指定信号的对象；None表示整帧最近邻复制，不修改帧内信号字段。|
|`values`|Mapping[str, int &#124; float] &#124; None|是|无|位置或关键字。要重建的连续信号物理值；None表示完整复制基础帧，不改信号位。|
|`identity`|tuple|是|无|位置或关键字。报文身份元组（通道、ID、扩展标志、FD标志），用于稳定排序和错误定位。|
|`mode`|str|是|无|位置或关键字。本次生成方式的文字标记，例如nearest_frame或linear，写入追溯信息。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

量化/输出错。

源码：[`src/chronaxis/results/frame_rebuild.py:339`](../../../src/chronaxis/results/frame_rebuild.py#L339)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_nearest"></a>
### `FrameRebuildRead._nearest`

未知报文整帧最近邻，等距选左且不越最大距离。

```python
FrameRebuildRead._nearest(time_ns, left, right, left_bad, right_bad, identity)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。当前目标网格位置，整数纳秒。|
|`left`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample) &#124; None|是|无|位置或关键字。左侧的实际帧样本；缺少该端点时为None，不从观测范围之外补帧。|
|`right`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample) &#124; None|是|无|位置或关键字。右侧的实际帧样本；缺少该端点时为None，不从观测范围之外补帧。|
|`left_bad`|bool|是|无|位置或关键字。左端同一时刻是否存在无法按配置解决的值冲突；True时不能把它当作有效插值端点。|
|`right_bad`|bool|是|无|位置或关键字。右端同一时刻是否存在无法按配置解决的值冲突；True时不能把它当作有效插值端点。|
|`identity`|tuple|是|无|位置或关键字。报文身份元组（通道、ID、扩展标志、FD标志），用于稳定排序和错误定位。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

输出错。

源码：[`src/chronaxis/results/frame_rebuild.py:364`](../../../src/chronaxis/results/frame_rebuild.py#L364)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_segment"></a>
### `FrameRebuildRead._segment`

每块最多256网格点计算连续量，实点另外保原字节。

```python
FrameRebuildRead._segment(left, right, left_bad, right_bad, patcher, identity)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample) &#124; None|是|无|位置或关键字。左侧的实际帧样本；缺少该端点时为None，不从观测范围之外补帧。|
|`right`|[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample) &#124; None|是|无|位置或关键字。右侧的实际帧样本；缺少该端点时为None，不从观测范围之外补帧。|
|`left_bad`|bool|是|无|位置或关键字。左端同一时刻是否存在无法按配置解决的值冲突；True时不能把它当作有效插值端点。|
|`right_bad`|bool|是|无|位置或关键字。右端同一时刻是否存在无法按配置解决的值冲突；True时不能把它当作有效插值端点。|
|`patcher`|[DBCFramePatch](chronaxis.results.frame_patch.md#api-DBCFramePatch) &#124; None|是|无|位置或关键字。按DBC位定义写入指定信号的对象；None表示整帧最近邻复制，不修改帧内信号字段。|
|`identity`|tuple|是|无|位置或关键字。报文身份元组（通道、ID、扩展标志、FD标志），用于稳定排序和错误定位。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原计算/输出错。

源码：[`src/chronaxis/results/frame_rebuild.py:375`](../../../src/chronaxis/results/frame_rebuild.py#L375)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-__iter__"></a>
### `FrameRebuildRead.__iter__`

准备完成后开放一个时间游标。

```python
FrameRebuildRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

准备或重复游标错。

源码：[`src/chronaxis/results/frame_rebuild.py:411`](../../../src/chronaxis/results/frame_rebuild.py#L411)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-export_metadata"></a>
### `FrameRebuildRead.export_metadata`

返回本次已完成重建的有限清单事实。

```python
FrameRebuildRead.export_metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

dict或None。

#### 异常说明

无。

源码：[`src/chronaxis/results/frame_rebuild.py:420`](../../../src/chronaxis/results/frame_rebuild.py#L420)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-__next__"></a>
### `FrameRebuildRead.__next__`

恢复下一生成/透传帧或缺失说明。

```python
FrameRebuildRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

ExportCANFrame/SkippedCANFrame。

#### 异常说明

EOF/校验错。

源码：[`src/chronaxis/results/frame_rebuild.py:425`](../../../src/chronaxis/results/frame_rebuild.py#L425)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-_close_input"></a>
### `FrameRebuildRead._close_input`

真正关闭源样本游标。

```python
FrameRebuildRead._close_input()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭错保责任。

源码：[`src/chronaxis/results/frame_rebuild.py:435`](../../../src/chronaxis/results/frame_rebuild.py#L435)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRead-close"></a>
### `FrameRebuildRead.close`

关闭输入流、排序文件和DBC字段编码对象，释放本对象登记的内存；保留诊断文件。关闭失败会抛出原异常，调用者可重试。

```python
FrameRebuildRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭/释放错可重试。

源码：[`src/chronaxis/results/frame_rebuild.py:444`](../../../src/chronaxis/results/frame_rebuild.py#L444)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

## 内部匿名回调


<a id="lambda-370"></a>
### 第370行匿名函数

```python
lambda s: (abs(s.record.time_ns - time_ns), s.record.time_ns)
```

|参数|含义|返回/异常|
|---|---|---|
|`s`|参数按上方签名传入；具体调用语义尚待补充。|返回值由上方表达式决定；具体用途和异常尚待核对，不据模板推断。|

<a id="lambda-252"></a>
### 第252行匿名函数

```python
lambda row: row[0][:-2]
```

|参数|含义|返回/异常|
|---|---|---|
|`row`|参数按上方签名传入；具体调用语义尚待补充。|返回值由上方表达式决定；具体用途和异常尚待核对，不据模板推断。|
