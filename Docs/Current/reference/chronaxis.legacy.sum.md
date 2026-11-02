# chronaxis.legacy.sum

按旧逐消息算法的顺序累加已经计算出的贡献值，并记录跳过原因。这里的累计不是按时间积分；数值结果和逐次记录由调用方提供。保存状态和临时块都受资源额度限制。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)、[LegacyUpdateOrder](chronaxis.legacy.updates.md#api-LegacyUpdateOrder)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`LegacySkipReason`](#api-LegacySkipReason)|提供者明确选择的一次跳过原因，不由累计器根据原值或质量推断。|
|[`_require_contribution`](#api-_require_contribution)|检查有限原生贡献与显式跳过原因互斥，不转换或修补数值。|
|[`LegacySumContribution`](#api-LegacySumContribution)|关联一次更新身份与提供者已求出的贡献，不保存新的信号缓存。|
|[`LegacySumContribution.__post_init__`](#api-LegacySumContribution-__post_init__)|验证真实更新模型及互斥的贡献/跳过结构。|
|[`LegacySumSnapshot`](#api-LegacySumSnapshot)|保存固定大小的未舍入累计事实，明确区分没有贡献与有效零和。|
|[`LegacySumSnapshot.__post_init__`](#api-LegacySumSnapshot-__post_init__)|核对有限计数关系与空结果原因，并冻结固定四键映射。|
|[`_sum_reference`](#api-_sum_reference)|以独立Python浮点逐项左折叠，发现任一中间溢出立即拒绝本批。|
|[`LegacySumAccumulator`](#api-LegacySumAccumulator)|拥有单来源有限累计状态和实际预算槽，不拥有调用方更新或共用的资源用量记录。|
|[`LegacySumAccumulator.__init__`](#api-LegacySumAccumulator-__init__)|先安装责任槽、校验配置并预付费用，再建立空顺序及累计状态。|
|[`LegacySumAccumulator.closed`](#api-LegacySumAccumulator-closed)|查看当前对象是否已经完成关闭。|
|[`LegacySumAccumulator._ensure_open`](#api-LegacySumAccumulator-_ensure_open)|拒绝关闭或有待恢复费用的owner，防止新批覆盖旧责任槽。|
|[`LegacySumAccumulator._candidate`](#api-LegacySumAccumulator-_candidate)|在已预付空间内生成独立候选，返回时不保留逐次值临时列。|
|[`LegacySumAccumulator._release_failed_batch`](#api-LegacySumAccumulator-_release_failed_batch)|有限重试本批实际费用，清理副错只附注原异常，不关闭正常累计状态。|
|[`LegacySumAccumulator.consume`](#api-LegacySumAccumulator-consume)|整批核验并累计，临时差额实际释放成功后才一次安装全部候选事实。|
|[`LegacySumAccumulator.snapshot`](#api-LegacySumAccumulator-snapshot)|返回调用方拥有的独立冻结快照，不舍入、不封口或证明来源EOF。|
|[`LegacySumAccumulator.close`](#api-LegacySumAccumulator-close)|释放本累计器实际费用，可在释放前后取消或持续失败后重试同一owner。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from copy import copy
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from types import MappingProxyType
from ..core.validation import require_identifier, require_text
from ..results.budget import ResourceBudget, _cleanup_owner, _release_owned_ram, _reserve_owned_ram
from ..results.errors import ResultClosedError
from .updates import LegacyDecodedUpdate, LegacyUpdateOrder
```

</details>

<a id="api-LegacySkipReason"></a>
## `LegacySkipReason`

提供者明确选择的一次跳过原因，不由累计器根据原值或质量推断。

四个固定成员覆盖输入缺项、条件不成立、求值错误和非有限输入。
枚举无可变状态；原因仅解释该提供者为何未给出有限贡献，不补造旧缓存事实。

```python
class LegacySkipReason(Enum)
```

继承关系：Enum。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`MISSING_INPUT`|[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason)|类成员，不作为构造参数填写|'missing_input'|输入或方向缺失，没有可用于累计的完整值。|
|`CONDITION_FALSE`|[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason)|类成员，不作为构造参数填写|'condition_false'|方向或筛选条件不成立，本次消息不加入累计。|
|`EVALUATION_ERROR`|[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason)|类成员，不作为构造参数填写|'evaluation_error'|本次表达式求值失败，保留失败原因而不填零贡献。|
|`NONFINITE_INPUT`|[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason)|类成员，不作为构造参数填写|'nonfinite_input'|输入出现NaN或无穷等非有限值，本次消息不能作为有限贡献累计。|

源码：[`src/chronaxis/legacy/sum.py:31`](../../../src/chronaxis/legacy/sum.py#L31)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_require_contribution"></a>
## `_require_contribution`

检查有限原生贡献与显式跳过原因互斥，不转换或修补数值。

```python
_require_contribution(value: float | None, skip_reason: LegacySkipReason | None) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|float &#124; None|是|无|位置或关键字。value为原生有限float或None|
|`skip_reason`|[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason) &#124; None|是|无|位置或关键字。skip_reason为固定枚举或None。|

### 返回说明

None；合法数值和显式跳过均保持原样。

### 异常说明

TypeError为类型不符；ValueError为非有限数值或贡献/原因关系矛盾。

本函数直接报告的具体错误：

- `TypeError`：skip_reason必须为LegacySkipReason或None。
- `TypeError`：贡献必须为原生float或None。
- `ValueError`：贡献必须为有限float；非有限输入应由提供者显式跳过。
- `ValueError`：有限贡献不能同时携带skip_reason。
- `ValueError`：无贡献时必须显式提供skip_reason。

返回类型：None。

源码：[`src/chronaxis/legacy/sum.py:48`](../../../src/chronaxis/legacy/sum.py#L48)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumContribution"></a>
## `LegacySumContribution`

关联一次更新身份与提供者已求出的贡献，不保存新的信号缓存。

update保留原模型对象；value是有限原生float，或与明确skip_reason配对的
None。即使update.quality非零，有限贡献也不由本层自动否决。该对象由调用方
提供，不证明旧表达式、触发门控、缺失处理或真实日志逐次出口已经接通。

```python
class LegacySumContribution
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|此次求值的原身份，引用保持不变。|
|`value`|float &#124; None|是|无|已计算一次的贡献，不再施加时间或单位倍率。|
|`skip_reason`|[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason) &#124; None|否|None|仅None贡献需要明确原因。|

源码：[`src/chronaxis/legacy/sum.py:72`](../../../src/chronaxis/legacy/sum.py#L72)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumContribution-__post_init__"></a>
### `LegacySumContribution.__post_init__`

验证真实更新模型及互斥的贡献/跳过结构。

```python
LegacySumContribution.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取update、value和skip_reason。

#### 返回说明

None；不复制update或修改其原值、质量。

#### 异常说明

TypeError为非模型或数值/原因类型不符；ValueError为结构或有限性错误。

本函数直接报告的具体错误：

- `TypeError`：update必须为LegacyDecodedUpdate。

返回类型：None。

源码：[`src/chronaxis/legacy/sum.py:84`](../../../src/chronaxis/legacy/sum.py#L84)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumSnapshot"></a>
## `LegacySumSnapshot`

保存固定大小的未舍入累计事实，明确区分没有贡献与有效零和。

evaluation_count包括跳过，contribution_count只数实际加法项；四键
skip_counts复制冻结且始终含零项。没有求值和全部跳过分别以reason说明，
只有曾接收有效贡献才给float总数。快照归调用方，可在累计器关闭后保留；
不保存逐次列表，也不声称普通时间积分的覆盖率或旧整文件行为全等。

```python
class LegacySumSnapshot
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session_id`|str|是|无|原会话身份。|
|`source`|str|是|无|单一来源身份。|
|`legacy_policy`|str|是|无|提供者显式声明的贡献及跳过政策文本。|
|`value`|float &#124; None|是|无|未舍入总数；没有有效贡献时为None。|
|`evaluation_count`|int|是|无|所有已接受求值，包括跳过。|
|`contribution_count`|int|是|无|实际有限贡献数量，包括值为0的项。|
|`skipped_count`|int|是|无|显式跳过的求值数量。|
|`skip_counts`|Mapping[[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason), int]|是|无|固定四键的独立冻结映射。|
|`reason`|str &#124; None|是|无|no_evaluations/all_skipped；有贡献时为None。|

源码：[`src/chronaxis/legacy/sum.py:98`](../../../src/chronaxis/legacy/sum.py#L98)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumSnapshot-__post_init__"></a>
### `LegacySumSnapshot.__post_init__`

核对有限计数关系与空结果原因，并冻结固定四键映射。

```python
LegacySumSnapshot.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取所有快照字段。

#### 返回说明

None；skip_counts转换成新的MappingProxyType，其他事实不改写。

#### 异常说明

TypeError为字段类型不符；ValueError为计数、原因域或结果关系矛盾；
    MemoryError为固定小映射分配失败，不返回部分快照。

返回类型：None。

源码：[`src/chronaxis/legacy/sum.py:117`](../../../src/chronaxis/legacy/sum.py#L117)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_sum_reference"></a>
## `_sum_reference`

以独立Python浮点逐项左折叠，发现任一中间溢出立即拒绝本批。

```python
_sum_reference(carry: float, values: tuple[float, ...]) -> float
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`carry`|float|是|无|位置或关键字。carry是此前有限总数|
|`values`|tuple[float, ...]|是|无|位置或关键字。values是按原求值顺序选出的有限float tuple。|

### 返回说明

float；无舍入、补偿求和或块和重排的候选总数。

### 异常说明

OverflowError为任一中间累计非有限；取消及内存发生异常时直接交给调用者处理。

本函数直接报告的具体错误：

- `OverflowError`：legacy_sum中间累计非有限，整批拒绝。

返回类型：float。

源码：[`src/chronaxis/legacy/sum.py:169`](../../../src/chronaxis/legacy/sum.py#L169)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator"></a>
## `LegacySumAccumulator`

拥有单来源有限累计状态和实际预算槽，不拥有调用方更新或共用的资源用量记录。

_state一次保存顺序器、总数、贡献数及四原因计数。候选顺序器用copy.copy
复制，共享的旧状态tuple不可变；包括skip的全部记录仍检查会话和原序。
_fixed_cost覆盖本层有限元数据及候选重叠；_workspace_cost可预付单条工作区，
_batch_cost只覆盖本批超过预付容量的临时费用。三者之和为_held_cost。
费用清理未完成时拒绝新消费，close可按同owner重试。

```python
LegacySumAccumulator(budget: ResourceBudget, session_id: str, source: str, *, legacy_policy: str, backend: str='numpy', max_batch_rows: int=64, prepay_single: bool=False)
```


源码：[`src/chronaxis/legacy/sum.py:190`](../../../src/chronaxis/legacy/sum.py#L190)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator-__init__"></a>
### `LegacySumAccumulator.__init__`

先安装责任槽、校验配置并预付费用，再建立空顺序及累计状态。

```python
LegacySumAccumulator.__init__(budget: ResourceBudget, session_id: str, source: str, *, legacy_policy: str, backend: str='numpy', max_batch_rows: int=64, prepay_single: bool=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`source`|str|是|无|位置或关键字。session_id/source为固定身份|
|`legacy_policy`|str|是|无|仅关键字。legacy_policy     是必填非空政策|
|`backend`|str|否|'numpy'|仅关键字。backend为reference或numpy|
|`max_batch_rows`|int|否|64|仅关键字。max_batch_rows为正原生int|
|`prepay_single`|bool|否|False|仅关键字。prepay_single为原生bool，True时本owner构造预付4352字节单条工作区，     供内部历史AnalysisRunner在共享余额用尽时继续已有单条计算，不缓存贡献|

#### 返回说明

新累计器；初始无求值、无贡献，不把初始加法carry当正常结果。

#### 异常说明

TypeError/ValueError为配置不符；预算及取消原错传播。构造清理持续
    失败时，原异常的legacy_sum_cleanup_owner保留真实未返回owner。

源码：[`src/chronaxis/legacy/sum.py:200`](../../../src/chronaxis/legacy/sum.py#L200)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator-closed"></a>
### `LegacySumAccumulator.closed`

查看当前对象是否已经完成关闭。

```python
LegacySumAccumulator.closed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

bool；

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/legacy/sum.py:252`](../../../src/chronaxis/legacy/sum.py#L252)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator-_ensure_open"></a>
### `LegacySumAccumulator._ensure_open`

拒绝关闭或有待恢复费用的owner，防止新批覆盖旧责任槽。

```python
LegacySumAccumulator._ensure_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError为已关闭或正在清理。

本函数直接报告的具体错误：

- `ResultClosedError`：legacy累计器已关闭或正在清理。

返回类型：None。

源码：[`src/chronaxis/legacy/sum.py:256`](../../../src/chronaxis/legacy/sum.py#L256)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator-_candidate"></a>
### `LegacySumAccumulator._candidate`

在已预付空间内生成独立候选，返回时不保留逐次值临时列。

```python
LegacySumAccumulator._candidate(contributions: tuple[LegacySumContribution, ...]) -> tuple
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`contributions`|tuple[[LegacySumContribution](chronaxis.legacy.sum.md#api-LegacySumContribution), ...]|是|无|位置或关键字。contributions为本批借用tuple，长度已经检查。|

#### 返回说明

tuple；新顺序器、候选总数、贡献数和四原因计数。

#### 异常说明

TypeError/ValueError为贡献或顺序错误；OverflowError为中间累计溢出；
    数组导入、分配或取消原样传播，原_state始终不被修改。

返回类型：tuple。

源码：[`src/chronaxis/legacy/sum.py:264`](../../../src/chronaxis/legacy/sum.py#L264)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator-_release_failed_batch"></a>
### `LegacySumAccumulator._release_failed_batch`

有限重试本批实际费用，清理副错只附注原异常，不关闭正常累计状态。

```python
LegacySumAccumulator._release_failed_batch(primary: BaseException) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

None；持续未释费用设置_closing，禁止覆盖该责任槽。

#### 异常说明

清理错误只记notes；真正剩余费用由原异常携带的owner.close恢复。

返回类型：None。

源码：[`src/chronaxis/legacy/sum.py:303`](../../../src/chronaxis/legacy/sum.py#L303)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator-consume"></a>
### `LegacySumAccumulator.consume`

整批核验并累计，临时差额实际释放成功后才一次安装全部候选事实。

```python
LegacySumAccumulator.consume(contributions: tuple[LegacySumContribution, ...]) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`contributions`|tuple[[LegacySumContribution](chronaxis.legacy.sum.md#api-LegacySumContribution), ...]|是|无|位置或关键字。contributions为精确tuple，长度不超过max_batch_rows|

#### 返回说明

None；成功提交全部项，任何失败不推进原数值、计数或顺序。

#### 异常说明

TypeError/ValueError为类型、批上限、来源或顺序；OverflowError为累计
    非有限；ResultClosedError为关闭中。预算、导入、分配或取消原样传播并
    附legacy_sum_cleanup_owner。清理成功后普通失败可用合法后续批恢复。

返回类型：None。

源码：[`src/chronaxis/legacy/sum.py:321`](../../../src/chronaxis/legacy/sum.py#L321)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator-snapshot"></a>
### `LegacySumAccumulator.snapshot`

返回调用方拥有的独立冻结快照，不舍入、不封口或证明来源EOF。

```python
LegacySumAccumulator.snapshot() -> LegacySumSnapshot
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

LegacySumSnapshot；四原因键始终存在，计数为0也不省略。

#### 异常说明

ResultClosedError为关闭中；分配或取消原样传播并附真实恢复owner。

返回类型：[LegacySumSnapshot](chronaxis.legacy.sum.md#api-LegacySumSnapshot)。

源码：[`src/chronaxis/legacy/sum.py:358`](../../../src/chronaxis/legacy/sum.py#L358)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacySumAccumulator-close"></a>
### `LegacySumAccumulator.close`

释放本累计器实际费用，可在释放前后取消或持续失败后重试同一owner。

```python
LegacySumAccumulator.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；只有所有自有槽实际归零才closed=True，重复close无操作。

#### 异常说明

原预算或取消异常保持，附legacy_sum_cleanup_owner；半关闭时拒绝继续
    consume/snapshot，不释放调用方借款，不使已返回快照失效。

返回类型：None。

源码：[`src/chronaxis/legacy/sum.py:382`](../../../src/chronaxis/legacy/sum.py#L382)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
