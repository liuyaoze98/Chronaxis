# chronaxis.results.frame_patch

用已有DBC位域工具更新明确的连续信号，其他位沿用同一基础帧。

调用者传入本次已加载的cantools Message及本次已解码的物理值，不再次读取DBC
或解码原帧。整数按nearest_even-v1量化，浮点沿DBC编码后核实际表示误差。
码值或物理值越界立即拒绝。只更新选中位的掩码，计数、校验及未知位保持；
这些生成帧不承诺校验码有效或可用于车辆回放。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`FrameRebuildRule`](#api-FrameRebuildRule)|说明哪种报文、哪些字段允许线性重建。未选中的位来自同一条最近基础帧；不重新计算校验码。|
|[`FrameRebuildRule.__post_init__`](#api-FrameRebuildRule-__post_init__)|核身份和字段分类。|
|[`FrameRebuildRule.matches`](#api-FrameRebuildRule-matches)|按实际帧身份匹配。|
|[`DBCFramePatch`](#api-DBCFramePatch)|借用一条已加载DBC定义，拥有选中位格式与预算；只缓存当前复用布局。|
|[`DBCFramePatch.__init__`](#api-DBCFramePatch-__init__)|核DBC身份与连续字段并预约格式空间。|
|[`DBCFramePatch.accept_frame`](#api-DBCFramePatch-accept_frame)|核对同次实际帧身份，复用已加载DBC，不增加文件扫描。|
|[`DBCFramePatch.selected`](#api-DBCFramePatch-selected)|只取当前复用分支适用的连续字段。|
|[`DBCFramePatch.patch`](#api-DBCFramePatch-patch)|仅按允许掩码更新载荷并记录量化误差。|
|[`DBCFramePatch.close`](#api-DBCFramePatch-close)|释放本格式缓存，不关闭借用DBC。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, replace
from fractions import Fraction
from math import isfinite
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..legacy.records import normalize_frame_id
```

</details>

<a id="api-FrameRebuildRule"></a>
## `FrameRebuildRule`

说明哪种报文、哪些字段允许线性重建。未选中的位来自同一条最近基础帧；不重新计算校验码。

```python
class FrameRebuildRule
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`channel`|int|是|无|内部0基通道编号，须与已解析来源DBC通道一致；用户配置通道1在此为0。|
|`frame_id`|int &#124; str|是|无|原生整数或进制字符串；0x/0X为十六进制，0b/0B为二进制，无前缀为十进制，010表示10。构造后保存0至0x1FFFFFFF的整数；拒绝bool、float、负数、加号、下划线及0o前缀。 Python构造器接受两种输入；对象建立后该属性为int。|
|`continuous`|tuple[str, ...]|是|无|1～4096个可插值的DBC信号名，不是分析别名。例如 `["Voltage"]` 表示只重新计算Voltage所占的位。|
|`is_extended`|bool &#124; None|否|None|None表示未限定，运行时结合DBC及实际帧识别；False限定标准帧且ID不超过0x7FF，True限定扩展帧。Python允许None表达省略，JSON/YAML填写时只能是布尔值。|
|`is_fd`|bool &#124; None|否|None|None表示未限定，按日志实际帧匹配；False限定经典CAN，True限定CAN FD。DBC为FD而实际为经典CAN可按已批准规则兼容，不修改真实帧。JSON/YAML填写时只能是布尔值。|
|`protected`|tuple[str, ...]|否|()|明确禁止插值的DBC信号名，例如 `["Counter","Checksum"]`。这些名称须在DBC中存在，也不能出现在continuous中。|
|`same_time_policy`|str|否|'error'|`"error"`：同一时刻的多个有效值冲突时，把该点视为无法确定，不任选一个值；`"last_by_sequence"`：按来源序号选择最后一条记录。|

源码：[`src/chronaxis/results/frame_patch.py:18`](../../../src/chronaxis/results/frame_patch.py#L18)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRule-__post_init__"></a>
### `FrameRebuildRule.__post_init__`

核身份和字段分类。

```python
FrameRebuildRule.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

非法/重复/保护字段冲突。

本函数直接报告的具体错误：

- `ValueError`：报文重建身份或同一时刻策略非法。
- `ValueError`：必须选择连续量，且不能插值保护的计数或校验字段。
- `ValueError`：报文重建字段需要唯一非空名称tuple。

源码：[`src/chronaxis/results/frame_patch.py:29`](../../../src/chronaxis/results/frame_patch.py#L29)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameRebuildRule-matches"></a>
### `FrameRebuildRule.matches`

按实际帧身份匹配。

```python
FrameRebuildRule.matches(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。原始CAN帧，按通道、ID、扩展帧和FD标志判断是否匹配本重建规则。|

#### 返回说明

通道和ID匹配，且实际帧满足规则中已指定的帧型时返回True；省略的帧型不限制匹配。

#### 异常说明

原模型访问错。

源码：[`src/chronaxis/results/frame_patch.py:46`](../../../src/chronaxis/results/frame_patch.py#L46)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DBCFramePatch"></a>
## `DBCFramePatch`

借用一条已加载DBC定义，拥有选中位格式与预算；只缓存当前复用布局。

```python
DBCFramePatch(rule, message, budget)
```


源码：[`src/chronaxis/results/frame_patch.py:54`](../../../src/chronaxis/results/frame_patch.py#L54)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DBCFramePatch-__init__"></a>
### `DBCFramePatch.__init__`

核DBC身份与连续字段并预约格式空间。

```python
DBCFramePatch.__init__(rule, message, budget)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|[FrameRebuildRule](chronaxis.results.frame_patch.md#api-FrameRebuildRule)|是|无|位置或关键字。FrameRebuildRule，列出报文身份和允许修改的连续字段。|
|`message`|cantools.database.can.Message|是|无|位置或关键字。已加载的DBC消息定义，提供与rule对应的信号位位置、长度和比例。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|

#### 返回说明

patcher。

#### 异常说明

不匹配或预算错。

本函数直接报告的具体错误：

- `TypeError`：需要FrameRebuildRule。
- `ValueError`：重建规则与DBC报文身份/载荷不符或为容器报文。

源码：[`src/chronaxis/results/frame_patch.py:57`](../../../src/chronaxis/results/frame_patch.py#L57)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DBCFramePatch-accept_frame"></a>
### `DBCFramePatch.accept_frame`

核对同次实际帧身份，复用已加载DBC，不增加文件扫描。

```python
DBCFramePatch.accept_frame(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。当前原帧，必须保留实际通道、ID和类型标志。|

#### 返回说明

None；记录本规则首次实际帧类型，后续保持同型。

#### 异常说明

ValueError：帧与规则或已选DBC不符，或后续出现另一种实际类型。

#### 副作用说明

只记录首次匹配的两个类型标志，后续同型帧不扩大状态。

源码：[`src/chronaxis/results/frame_patch.py:85`](../../../src/chronaxis/results/frame_patch.py#L85)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DBCFramePatch-selected"></a>
### `DBCFramePatch.selected`

只取当前复用分支适用的连续字段。

```python
DBCFramePatch.selected(layout)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`layout`|tuple|是|无|位置或关键字。原生复用选择器名称与码值组成的布局；确定当前报文启用哪些信号字段。|

#### 返回说明

名称tuple。

#### 异常说明

布局非法。

本函数直接报告的具体错误：

- `ValueError`：报文复用布局不合法。
- `ValueError`：DBC复用父链非法。

源码：[`src/chronaxis/results/frame_patch.py:100`](../../../src/chronaxis/results/frame_patch.py#L100)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DBCFramePatch-patch"></a>
### `DBCFramePatch.patch`

仅按允许掩码更新载荷并记录量化误差。

```python
DBCFramePatch.patch(base, values, layout, *, exact_values=None, trace=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`base`|LegacyRawFrame|是|无|位置或关键字。base同一基础LegacyRawFrame|
|`values`|Mapping[str, int &#124; float]|是|无|位置或关键字。要写入的信号名到物理值的映射，按DBC比例、偏移和位定义编码。|
|`layout`|tuple|是|无|位置或关键字。该基础帧实际采用的复用选择器布局，决定哪些字段可以写入。|
|`exact_values`|Mapping[str, Fraction] &#124; None|否|None|仅关键字。可选的精确有理数目标值，用于避免浮点舍入改变半个码值的取整结果；None使用values。|
|`trace`|bool|否|True|仅关键字。是否保存此功能的详细来源或输入追溯；False在生成处跳过，不能先构造再隐藏。|

#### 返回说明

(新帧, 每字段目标/码值/实际值/误差tuple)。

#### 异常说明

缺值、范围/格式/编码错误。

本函数直接报告的具体错误：

- `ValueError`：重建基础帧已关闭、身份或长度不符。
- `ValueError`：当前复用布局缺少必须的连续值。
- `ValueError`：精确量化目标需要同组Fraction字段。

源码：[`src/chronaxis/results/frame_patch.py:123`](../../../src/chronaxis/results/frame_patch.py#L123)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DBCFramePatch-close"></a>
### `DBCFramePatch.close`

释放本格式缓存，不关闭借用DBC。

```python
DBCFramePatch.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

费用释放错可重试。

源码：[`src/chronaxis/results/frame_patch.py:180`](../../../src/chronaxis/results/frame_patch.py#L180)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
