# `chronaxis.execution.legacy_frame_samples`

把同次BLF原帧仓与稀疏解码仓按原序连接，供新增报文重建使用。

不重新扫描BLF、不重新解码；新DBC上下文只提供编码布局和复用选择器。
原帧与解码记录的序号、时间和公开帧字段逐项相符，结束时两仓均完整核验。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`LegacyFrameSamples`](#api-LegacyFrameSamples)|最多保留一条原帧与一条解码记录，拥有两游标而借用原仓和DBC。|
|[`LegacyFrameSamples.__init__`](#api-LegacyFrameSamples-__init__)|核同次仓身份后开有限游标。|
|[`LegacyFrameSamples.closed`](#api-LegacyFrameSamples-closed)|返回真实关闭状态。|
|[`LegacyFrameSamples.__iter__`](#api-LegacyFrameSamples-__iter__)|返回独立游标。|
|[`LegacyFrameSamples.__next__`](#api-LegacyFrameSamples-__next__)|连接同原序记录，不跳过完整仓核验。|
|[`LegacyFrameSamples.close`](#api-LegacyFrameSamples-close)|关闭真实两个游标后释放自己的费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..results.frame_exports import as_export_frame
from ..results.frame_rebuild import FrameSample
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError, ResultFormatError
```

</details>

<a id="api-LegacyFrameSamples"></a>
## `LegacyFrameSamples`

最多保留一条原帧与一条解码记录，拥有两游标而借用原仓和DBC。

```python
LegacyFrameSamples(raw_store, message_store, context, budget, *, read_identity, session_id, channel, trace=True)
```


源码：[`src/chronaxis/execution/legacy_frame_samples.py:13`](../../../src/chronaxis/execution/legacy_frame_samples.py#L13)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyFrameSamples-__init__"></a>
### `LegacyFrameSamples.__init__`

核同次仓身份后开有限游标。

```python
LegacyFrameSamples.__init__(raw_store, message_store, context, budget, *, read_identity, session_id, channel, trace=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw_store`|RawFrameStore|是|无|位置或关键字。本次读取保存的原始报文仓，写入已经结束；用于恢复帧内容和位置。|
|`message_store`|DecodedMessageStore &#124; None|是|无|位置或关键字。同次读取的消息仓；None表示没有可借用的消息仓，不能使用另一会话的仓替代。|
|`context`|FrameDBCContext|是|无|位置或关键字。已打开的DBC上下文，提供重建字段和复用布局的信息。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`read_identity`|str|是|无|仅关键字。这一次实际读取的唯一标识；不同次读取即使文件同名也不能混用此标识。|
|`session_id`|str|是|无|仅关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`channel`|int|是|无|仅关键字。本来源的内部0基CAN通道，用来匹配原始报文与字段规则；用户配置通道1已转换为内部0。|
|`trace`|bool|否|True|仅关键字。是否保存此功能的详细来源或输入追溯；False在生成处跳过，不能先构造再隐藏。|

#### 返回说明

__init__返回None；使用类名构造时得到已经初始化的对象。后续由该对象管理并关闭自己创建的资源。

#### 异常说明

合同/IO错。

本函数直接报告的具体错误：

- `ValueError`：重建需要同预算已封口原帧仓。
- `ValueError`：原帧与解码仓不是同次读取。

源码：[`src/chronaxis/execution/legacy_frame_samples.py:16`](../../../src/chronaxis/execution/legacy_frame_samples.py#L16)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyFrameSamples-closed"></a>
### `LegacyFrameSamples.closed`

返回真实关闭状态。

```python
LegacyFrameSamples.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/legacy_frame_samples.py:38`](../../../src/chronaxis/execution/legacy_frame_samples.py#L38)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyFrameSamples-__iter__"></a>
### `LegacyFrameSamples.__iter__`

返回独立游标。

```python
LegacyFrameSamples.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/legacy_frame_samples.py:43`](../../../src/chronaxis/execution/legacy_frame_samples.py#L43)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyFrameSamples-__next__"></a>
### `LegacyFrameSamples.__next__`

连接同原序记录，不跳过完整仓核验。

```python
LegacyFrameSamples.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

FrameSample。

#### 异常说明

EOF/来源不符/IO错。

本函数直接报告的具体错误：

- `ResultFormatError`：解码仓出现无对应原帧记录。
- `ResultFormatError`：已请求重建报文缺同次解码记录。
- `ResultFormatError`：原帧和解码仓没有共同完整结束。
- `ResultFormatError`：重建原帧与解码记录内容不符。

源码：[`src/chronaxis/execution/legacy_frame_samples.py:48`](../../../src/chronaxis/execution/legacy_frame_samples.py#L48)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyFrameSamples-close"></a>
### `LegacyFrameSamples.close`

关闭真实两个游标后释放自己的费用。

```python
LegacyFrameSamples.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close错可重试。

源码：[`src/chronaxis/execution/legacy_frame_samples.py:84`](../../../src/chronaxis/execution/legacy_frame_samples.py#L84)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
