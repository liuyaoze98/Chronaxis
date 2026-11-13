# `chronaxis.sources.protocol`

约定来源的描述、分批读取和关闭接口，并检查跨批承诺。

SourceAdapter接收ReadRequest并产生SignalBatch；BatchValidator根据
SourceDescription检查会话、投影、类型、单位、时间顺序、序号和进度。
本模块不打开来源、不排序文件，也不计算业务事件。

校验器保存各列最近时间组的序号、来源最近时间、watermark_ns进度和
结束状态。进度承诺之后不能再接收小于或等于该时间的更新；失败时不推进
已有状态。状态大小取决于信号数量和当前组规模，执行层须将容器计入预算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)

## 对象导航

|对象|用途|
|---|---|
|[`SourceClosedError`](#api-SourceClosedError)|表示已经关闭的来源仍被请求描述或读取；重复close本身应安全。|
|[`SourceReadError`](#api-SourceReadError)|表示来源读取或批次协议失败；具体适配器负责附加位置并保留原异常链。|
|[`SourceAdapter`](#api-SourceAdapter)|约束已解码来源的公共接口，不管理实现的内部资源。|
|[`SourceAdapter.describe`](#api-SourceAdapter-describe)|返回来源描述与能力声明，不推进输入读取。|
|[`SourceAdapter.iter_batches`](#api-SourceAdapter-iter_batches)|按请求传送指定别名的已解码更新。|
|[`SourceAdapter.close`](#api-SourceAdapter-close)|释放适配器持有的活动资源，保留用户输入文件。|
|[`BatchValidator`](#api-BatchValidator)|为一次读取请求核对跨批身份、时间顺序和结束状态。|
|[`BatchValidator.__init__`](#api-BatchValidator-__init__)|为当前来源及请求建立独立的跨批校验状态。|
|[`BatchValidator.accept`](#api-BatchValidator-accept)|检查一批的身份和进度，全部通过后才更新请求状态。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Iterator
from typing import Protocol, runtime_checkable
from .models import ReadRequest, SignalBatch, SourceDescription
```

</details>

<a id="api-SourceClosedError"></a>
## `SourceClosedError`

表示已经关闭的来源仍被请求描述或读取；重复close本身应安全。

```python
class SourceClosedError(RuntimeError)
```

继承关系：RuntimeError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/sources/protocol.py:21`](../../../src/chronaxis/sources/protocol.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SourceReadError"></a>
## `SourceReadError`

表示来源读取或批次协议失败；具体适配器负责附加位置并保留原异常链。

```python
class SourceReadError(RuntimeError)
```

继承关系：RuntimeError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/sources/protocol.py:26`](../../../src/chronaxis/sources/protocol.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SourceAdapter"></a>
## `SourceAdapter`

约束已解码来源的公共接口，不管理实现的内部资源。

describe返回声明，iter_batches按明确请求传送更新，close由实现释放资源。
静态描述不应推进日志输入或加载DBC。此协议不保存实例状态，具体适配器
负责活动生成器、句柄和关闭标记；同一来源的全部文件结束才报告source_eof。

```python
class SourceAdapter(Protocol)
```

继承关系：Protocol。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/sources/protocol.py:32`](../../../src/chronaxis/sources/protocol.py#L32)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SourceAdapter-describe"></a>
### `SourceAdapter.describe`

返回来源描述与能力声明，不推进输入读取。

```python
SourceAdapter.describe() -> SourceDescription
```

参数：无显式参数。


#### 参数说明

无。由实现使用当前来源配置和已有元数据。

#### 返回说明

SourceDescription。未知观测端点和不可用能力保留明确状态。

#### 异常说明

SourceClosedError: 来源已关闭。
    描述模型校验或实现的元数据错误由具体适配器报告。

返回类型：[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)。

源码：[`src/chronaxis/sources/protocol.py:40`](../../../src/chronaxis/sources/protocol.py#L40)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SourceAdapter-iter_batches"></a>
### `SourceAdapter.iter_batches`

按请求传送指定别名的已解码更新。

```python
SourceAdapter.iter_batches(request: ReadRequest) -> Iterator[SignalBatch]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。会话、别名投影、分析域和每批总样本上限。|

#### 返回说明

Iterator[SignalBatch]。允许空批和同时间组跨批，整个来源结束时报告结束标记。

#### 异常说明

SourceClosedError、SourceReadError或请求与协议校验错误，由具体实现报告。

#### 边界说明

请求范围不授权读取下推或改变旧链调用行为。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/sources/protocol.py:54`](../../../src/chronaxis/sources/protocol.py#L54)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SourceAdapter-close"></a>
### `SourceAdapter.close`

释放适配器持有的活动资源，保留用户输入文件。

```python
SourceAdapter.close() -> None
```

参数：无显式参数。


#### 参数说明

无。具体实现关闭自己的生成器和句柄。

#### 返回说明

None。重复关闭应安全。

#### 异常说明

清理失败由实现报告；已有读取错误时应保留原错误及清理证据。

返回类型：None。

源码：[`src/chronaxis/sources/protocol.py:69`](../../../src/chronaxis/sources/protocol.py#L69)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BatchValidator"></a>
## `BatchValidator`

为一次读取请求核对跨批身份、时间顺序和结束状态。

description和request保存本请求声明，catalog按别名索引字段契约。
watermark_ns记录已完整传送的时间进度，last_time_ns记录最近真实样本。
pending保存每列最近时间组的序号集合；进度越过该组后释放集合。
ended为True后不能再接收任何批次，包括空批。accept先在局部副本检查，
全部通过才替换状态，因此失败批次不会污染已有进度。

```python
BatchValidator(description: SourceDescription, request: ReadRequest) -> None
```


源码：[`src/chronaxis/sources/protocol.py:83`](../../../src/chronaxis/sources/protocol.py#L83)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BatchValidator-__init__"></a>
### `BatchValidator.__init__`

为当前来源及请求建立独立的跨批校验状态。

```python
BatchValidator.__init__(description: SourceDescription, request: ReadRequest) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`description`|[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)|是|无|位置或关键字。当前来源的字段、类型、单位和观测声明。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。本次会话、信号别名和批次上限。|

#### 返回说明

None。保存字段目录，并初始化时间、序号和结束状态；不读取来源。

#### 异常说明

TypeError: 输入不是规定的模型类型。
    ValueError: 请求别名在来源描述中不存在。

本函数直接报告的具体错误：

- `TypeError`：BatchValidator需要带有明确类型的描述/请求。

返回类型：None。

源码：[`src/chronaxis/sources/protocol.py:93`](../../../src/chronaxis/sources/protocol.py#L93)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BatchValidator-accept"></a>
### `BatchValidator.accept`

检查一批的身份和进度，全部通过后才更新请求状态。

```python
BatchValidator.accept(batch: SignalBatch) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)|是|无|位置或关键字。已通过单批结构检查的批次。|

#### 返回说明

None。更新最近时间、未完成组序号、进度承诺和来源结束标记。

#### 异常说明

ValueError: 批次类型或归属错误、超过样本上限、列契约变化、时间回退、
        重复观测、违反进度承诺或观测终点冲突；结束后任何批次也被拒绝。

#### 副作用说明

只在全部检查成功后改变本校验器；输入批次不被修改。

#### 边界说明

样本时间等于旧watermark_ns也被拒绝，因为该时间组已经承诺完整。
    真实点可以等于观测终点；分析开始前的保持样本仍可早于请求起点。

返回类型：None。

源码：[`src/chronaxis/sources/protocol.py:126`](../../../src/chronaxis/sources/protocol.py#L126)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
