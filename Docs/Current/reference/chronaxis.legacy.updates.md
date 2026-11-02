# chronaxis.legacy.updates

表示旧路径一次实际求值所见的更新，并校验单来源的求值顺序。

输入是调用方已经取得的时间、原帧身份、SourceRef、原求值序号和完整值字典；
输出是冻结的LegacyDecodedUpdate及只保存最后事实的LegacyUpdateOrder。
无需时间的固定周期消息累计显式使用LegacyUntimedUpdate，其time_ns只能
为None；同一顺序器不能混用有时间和无时间更新，不补造0时间。
模型保留原字段全文、None和非有限浮点，不推断类型、单位、缩放、TTL、缓存
或有效性。QualityFlag.NONE只表示没有记录质量原因，不证明值的新鲜度。

本模块只依赖标准库和共享核心模型，不读取日志、不调用旧解码器，也不提供
旧求值点的采集接口。调用方构造这些对象不能证明真实旧生产者已经暴露求值
过程；真实求值证据仍须由后续来源契约提供。值字典由调用方提供，本层复制
并冻结它，不宣称该复制已有执行预算或IPC大小界限。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 继承字段

- `LegacyUntimedUpdate`同时继承[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)字段：`time_ns`, `source`, `channel`, `frame_id`, `is_extended`, `is_fd`, `is_remote`, `is_error`, `source_ref`, `sequence`, `evaluation_index`, `values`, `quality`。构造时须一并提供基类的必填字段；类型、默认值及约束按基类表。

## 相关类型

[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`_require_nonnegative_int`](#api-_require_nonnegative_int)|校验原生非负整数身份，不把布尔或数值子类转成合法序号。|
|[`LegacyDecodedUpdate`](#api-LegacyDecodedUpdate)|冻结一次求值的原值快照，区分原帧序号与求值序号。|
|[`LegacyDecodedUpdate.__post_init__`](#api-LegacyDecodedUpdate-__post_init__)|校验显式身份并建立不受调用方字典后续修改影响的快照。|
|[`LegacyDecodedUpdate._freeze_fields`](#api-LegacyDecodedUpdate-_freeze_fields)|校验并冻结有时间与无时间更新共有的身份、质量和原值。|
|[`LegacyUntimedUpdate`](#api-LegacyUntimedUpdate)|保存无需时间的固定周期消息求值，复用原更新的完整身份和原值合同。|
|[`LegacyUntimedUpdate.__post_init__`](#api-LegacyUntimedUpdate-__post_init__)|拒绝任何实数或占位时间，仅执行父类的共有字段校验。|
|[`LegacyUpdateOrder`](#api-LegacyUpdateOrder)|校验同一会话和来源的逐次求值，不累计原值或维护旧信号缓存。|
|[`LegacyUpdateOrder.__init__`](#api-LegacyUpdateOrder-__init__)|建立一个来源的空顺序状态，不接收或消费任何更新。|
|[`LegacyUpdateOrder.session_id`](#api-LegacyUpdateOrder-session_id)|返回固定会话标识；|
|[`LegacyUpdateOrder.source`](#api-LegacyUpdateOrder-source)|返回固定来源标识；|
|[`LegacyUpdateOrder.last_time_ns`](#api-LegacyUpdateOrder-last_time_ns)|读取最后接受时间；|
|[`LegacyUpdateOrder.last_sequence`](#api-LegacyUpdateOrder-last_sequence)|读取最后原帧序号；|
|[`LegacyUpdateOrder.last_evaluation_index`](#api-LegacyUpdateOrder-last_evaluation_index)|读取最后求值序号；|
|[`LegacyUpdateOrder.count`](#api-LegacyUpdateOrder-count)|读取已接受次数；|
|[`LegacyUpdateOrder.accept`](#api-LegacyUpdateOrder-accept)|接受一个完整更新，仅在全部身份及顺序检查成功后提交最后事实。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from ..core.models import SourceRef
from ..core.types import QualityFlag
from ..core.validation import require_identifier, require_scalar
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_require_nonnegative_int"></a>
## `_require_nonnegative_int`

校验原生非负整数身份，不把布尔或数值子类转成合法序号。

```python
_require_nonnegative_int(value: int, field: str) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。原生int，表示通道、帧ID、来源序号或求值序号。|
|`field`|str|是|无|位置或关键字。错误消息使用的字段名称。|

### 返回说明

int: 输入的原整数；不重编号，也不设置额外的序号上限。

### 异常说明

TypeError: 输入不是精确的原生int，包括bool和整数子类。
    ValueError: 输入为负数。

返回类型：int。

源码：[`src/chronaxis/legacy/updates.py:27`](../../../src/chronaxis/legacy/updates.py#L27)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyDecodedUpdate"></a>
## `LegacyDecodedUpdate`

冻结一次求值的原值快照，区分原帧序号与求值序号。

time_ns按共享int64纳秒协议规范化；sequence定位原帧，evaluation_index
定位求值点，同一帧可以有多次求值。四个原帧标志必须显式传入，不能由ID
或载荷猜测。source_ref保留原对象并核对source，不补造旧缓存或求值证据。
values只接收精确dict或MappingProxyType，复制后冻结；键与原生不可变
标量保持原样，空字典合法，非有限浮点不会被替换或自动附加质量原因。

```python
class LegacyDecodedUpdate
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|调用方已取得的时间；仅按共享时间协议规范为Python整数。|
|`source`|str|是|无|与SourceRef.source_name一致的来源标识。|
|`channel`|int|是|无|原生非负通道编号，不从其他帧信息推断。|
|`frame_id`|int|是|无|标准帧或扩展帧范围内的原CAN ID。|
|`is_extended`|bool|是|无|原扩展帧标志，决定ID的合法上限。|
|`is_fd`|bool|是|无|原CAN FD标志，不由数据长度推断。|
|`is_remote`|bool|是|无|原远程帧标志，必须由调用方明确提供。|
|`is_error`|bool|是|无|原错误帧标志，不由质量位推断。|
|`source_ref`|[SourceRef](chronaxis.core.models.md#api-SourceRef)|是|无|原来源引用；允许已有SourceRef子类。|
|`sequence`|int|是|无|原帧序号；不要求连续，也不等同于求值序号。|
|`evaluation_index`|int|是|无|旧求值顺序；跨帧及同帧均独立递增。|
|`values`|Mapping[str, int &#124; float &#124; bool &#124; str &#124; None]|是|无|原字段和值的独立冻结副本。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|否|QualityFlag.NONE|只保留明确记录的原因位。|

源码：[`src/chronaxis/legacy/updates.py:48`](../../../src/chronaxis/legacy/updates.py#L48)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyDecodedUpdate-__post_init__"></a>
### `LegacyDecodedUpdate.__post_init__`

校验显式身份并建立不受调用方字典后续修改影响的快照。

```python
LegacyDecodedUpdate.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；读取构造时传入的全部字段。

#### 返回说明

None: 成功后time_ns已规范，values为新MappingProxyType。

#### 异常说明

TypeError: 身份、标志、来源引用、质量位、字典或标量类型不符。
    ValueError: 来源不匹配、负身份、ID越界或值字典含空键。
    TimeOverflowError: time_ns超出共享int64纳秒范围。
    MemoryError: 复制原值快照所需的分配失败；不返回部分模型。

返回类型：None。

源码：[`src/chronaxis/legacy/updates.py:72`](../../../src/chronaxis/legacy/updates.py#L72)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyDecodedUpdate-_freeze_fields"></a>
### `LegacyDecodedUpdate._freeze_fields`

校验并冻结有时间与无时间更新共有的身份、质量和原值。

```python
LegacyDecodedUpdate._freeze_fields() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；读取当前模型中除time_ns外的全部字段。

#### 返回说明

None: values被独立复制并冻结，其他身份及质量保持原值。

#### 异常说明

TypeError: 身份、标志、来源引用、质量或原值类型不合法。
    ValueError: 来源不匹配、负身份、ID越界或值字典含空键。
    MemoryError: 复制失败，调用方不能得到部分构造的模型。

#### 副作用说明

仅在当前待构造模型上安装冻结字典，不访问或伪造时间。

返回类型：None。

源码：[`src/chronaxis/legacy/updates.py:91`](../../../src/chronaxis/legacy/updates.py#L91)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUntimedUpdate"></a>
## `LegacyUntimedUpdate`

保存无需时间的固定周期消息求值，复用原更新的完整身份和原值合同。

time_ns只能显式为None，表示未采集时间；不代表0时刻或无观测数据。
sequence与evaluation_index保留实际原序及求值序，其他字段与父类一致。
本模型仍是LegacyDecodedUpdate，可交由相同逐消息数值核求值；调用方
必须确保没有时间消费者，并且不从本模型构造带时间的贡献或观测范围。

```python
class LegacyUntimedUpdate(LegacyDecodedUpdate)
```

继承关系：[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|None|是|无|显式未采集；必填，禁止借默认0或其他占位满足时间模型。|

源码：[`src/chronaxis/legacy/updates.py:146`](../../../src/chronaxis/legacy/updates.py#L146)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUntimedUpdate-__post_init__"></a>
### `LegacyUntimedUpdate.__post_init__`

拒绝任何实数或占位时间，仅执行父类的共有字段校验。

```python
LegacyUntimedUpdate.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；读取构造字段，time_ns必须为None。

#### 返回说明

None: 原值冻结，身份和质量检查与LegacyDecodedUpdate完全相同。

#### 异常说明

TypeError: time_ns不是None，或共有字段类型不合法。
    ValueError或MemoryError: 共有身份越界、来源冲突或复制失败。

#### 副作用说明

仅冻结当前模型，不构造虚假时间或修改调用方值字典。

返回类型：None。

源码：[`src/chronaxis/legacy/updates.py:157`](../../../src/chronaxis/legacy/updates.py#L157)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder"></a>
## `LegacyUpdateOrder`

校验同一会话和来源的逐次求值，不累计原值或维护旧信号缓存。

session_id和source固定；last_time_ns、last_sequence、
last_evaluation_index初始为None，count初始为0。时间和原帧序号不回退，
求值序号严格递增且允许间隙。首个更新固定是否带时间，之后禁止混用；
无时间模式的last_time_ns始终为None，仅按原序和求值序前进。
同一原帧序号还须保留完全相同的时间、
通道、ID和四个标志；值、质量及section引用可不同。最后事实保存在一个
当前状态tuple中，全部检查和新状态分配完成后才一次替换；拒绝不改状态。

```python
LegacyUpdateOrder(session_id: str, source: str) -> None
```


源码：[`src/chronaxis/legacy/updates.py:176`](../../../src/chronaxis/legacy/updates.py#L176)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder-__init__"></a>
### `LegacyUpdateOrder.__init__`

建立一个来源的空顺序状态，不接收或消费任何更新。

```python
LegacyUpdateOrder.__init__(session_id: str, source: str) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`source`|str|是|无|位置或关键字。沿共享模型规则校验的来源标识。|

#### 返回说明

None: 创建只读身份及初始空状态。

#### 异常说明

TypeError: 会话或来源不是文本。
    ValueError: 会话或来源不是合法的共享简单标识符。

返回类型：None。

源码：[`src/chronaxis/legacy/updates.py:188`](../../../src/chronaxis/legacy/updates.py#L188)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder-session_id"></a>
### `LegacyUpdateOrder.session_id`

返回固定会话标识；

```python
LegacyUpdateOrder.session_id: str
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

原str；

#### 异常说明

无。

返回类型：str。

源码：[`src/chronaxis/legacy/updates.py:206`](../../../src/chronaxis/legacy/updates.py#L206)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder-source"></a>
### `LegacyUpdateOrder.source`

返回固定来源标识；

```python
LegacyUpdateOrder.source: str
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

原str；

#### 异常说明

无。

返回类型：str。

源码：[`src/chronaxis/legacy/updates.py:211`](../../../src/chronaxis/legacy/updates.py#L211)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder-last_time_ns"></a>
### `LegacyUpdateOrder.last_time_ns`

读取最后接受时间；

```python
LegacyUpdateOrder.last_time_ns: int | None
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

int或初始None；

#### 异常说明

无。

返回类型：int &#124; None。

源码：[`src/chronaxis/legacy/updates.py:216`](../../../src/chronaxis/legacy/updates.py#L216)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder-last_sequence"></a>
### `LegacyUpdateOrder.last_sequence`

读取最后原帧序号；

```python
LegacyUpdateOrder.last_sequence: int | None
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

int或初始None；

#### 异常说明

无。

返回类型：int &#124; None。

源码：[`src/chronaxis/legacy/updates.py:221`](../../../src/chronaxis/legacy/updates.py#L221)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder-last_evaluation_index"></a>
### `LegacyUpdateOrder.last_evaluation_index`

读取最后求值序号；

```python
LegacyUpdateOrder.last_evaluation_index: int | None
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

int或初始None；

#### 异常说明

无。

返回类型：int &#124; None。

源码：[`src/chronaxis/legacy/updates.py:226`](../../../src/chronaxis/legacy/updates.py#L226)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder-count"></a>
### `LegacyUpdateOrder.count`

读取已接受次数；

```python
LegacyUpdateOrder.count: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

非负int；

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/legacy/updates.py:231`](../../../src/chronaxis/legacy/updates.py#L231)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyUpdateOrder-accept"></a>
### `LegacyUpdateOrder.accept`

接受一个完整更新，仅在全部身份及顺序检查成功后提交最后事实。

```python
LegacyUpdateOrder.accept(update: LegacyDecodedUpdate) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|位置或关键字。已构造的LegacyDecodedUpdate或LegacyUntimedUpdate； 同帧可携带不同值快照，同一顺序器禁止混用时间模式。|

#### 返回说明

None: 接受成功，count加一，最后事实切换到本次更新。

#### 异常说明

TypeError: update不是LegacyDecodedUpdate。
    ValueError: 会话、来源不符，时间模式混用，时间或原帧序号回退，求值序号不递增，
        或同一原帧序号的时间、通道、ID、四个标志出现冲突。
    MemoryError: 新状态分配失败；旧状态仍保持不变。

返回类型：None。

源码：[`src/chronaxis/legacy/updates.py:235`](../../../src/chronaxis/legacy/updates.py#L235)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
