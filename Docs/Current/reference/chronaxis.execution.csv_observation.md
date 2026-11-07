# `chronaxis.execution.csv_observation`

在读取CSV的同时记录实际第一行和最后一行的时间。只有读到文件末尾并完成清理后，才能取得完整的观测范围；该范围来自数据行，不从请求窗口推算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[BudgetedSignalCSVSourceAdapter](chronaxis.execution.csv_reader.md#api-BudgetedSignalCSVSourceAdapter)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalCSVSourceAdapter](chronaxis.sources.signal_csv.md#api-SignalCSVSourceAdapter)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)、[_CSVRecords](chronaxis.execution.csv_reader.md#api-_CSVRecords)、[_CSVResources](chronaxis.execution.csv_reader.md#api-_CSVResources)、[_PhysicalLines](chronaxis.execution.csv_reader.md#api-_PhysicalLines)

## 对象导航

|对象|用途|
|---|---|
|[`CSVObservation`](#api-CSVObservation)|保存单个实际完成read的原行时间范围，不代替来源文件身份或同步证明。|
|[`CSVObservation.__post_init__`](#api-CSVObservation-__post_init__)|校验完成事实结构，不读取文件、推测端点或修改原请求。|
|[`CSVObservationRead`](#api-CSVObservationRead)|拥有一次原生成器、可选检查器和单当前批，固定事实费到显式close释放。|
|[`CSVObservationRead.__init__`](#api-CSVObservationRead-__init__)|先申请保存本次请求和观测记录的内存，再创建读取生成器；此时尚未打开输入文件。|
|[`CSVObservationRead.identity`](#api-CSVObservationRead-identity)|读取本read独立身份。|
|[`CSVObservationRead.closed`](#api-CSVObservationRead-closed)|查看本对象负责的资源是否已经全部关闭。|
|[`CSVObservationRead.failed`](#api-CSVObservationRead-failed)|查看此前的读取操作是否失败。|
|[`CSVObservationRead.exhausted`](#api-CSVObservationRead-exhausted)|查看输入是否已经正常读完。|
|[`CSVObservationRead.observation`](#api-CSVObservationRead-observation)|借读本次已完成的冻结观测，借期到本read的close。|
|[`CSVObservationRead._read_resources`](#api-CSVObservationRead-_read_resources)|为本次生成器建立独立事务式检查器，在文件打开前保留最高责任。|
|[`CSVObservationRead._created_iterator`](#api-CSVObservationRead-_created_iterator)|在原活动set登记前接住本次实际生成器。|
|[`CSVObservationRead._opened_handle`](#api-CSVObservationRead-_opened_handle)|在适配器set登记前接住本次真实文件句柄。|
|[`CSVObservationRead._close_handle`](#api-CSVObservationRead-_close_handle)|沿原文件关闭动作保根因，并保留实际未关闭句柄供重试。|
|[`CSVObservationRead._close_resources`](#api-CSVObservationRead-_close_resources)|原生成器退出时清理本次检查器，清理失败不覆盖业务或取消根因。|
|[`CSVObservationRead._end_file`](#api-CSVObservationRead-_end_file)|清理单文件表头及行费用，保留现场正在传播的读取或关闭主异常。|
|[`CSVObservationRead._accept_candidate`](#api-CSVObservationRead-_accept_candidate)|仅接收原生成器最终协议成功后的候选，不在此声明完成。|
|[`CSVObservationRead._adopt_cleanup`](#api-CSVObservationRead-_adopt_cleanup)|接管本路径实际未返回的最高资源检查器。|
|[`CSVObservationRead.__iter__`](#api-CSVObservationRead-__iter__)|返回当前读取对象，继续使用当前读取位置。|
|[`CSVObservationRead._ensure_active`](#api-CSVObservationRead-_ensure_active)|拒绝关闭、清理或失败后的推进。|
|[`CSVObservationRead.__next__`](#api-CSVObservationRead-__next__)|转交原batch，真正StopIteration并成功清理后才安装完成事实。|
|[`CSVObservationRead._close_request`](#api-CSVObservationRead-_close_request)|关闭本次原生成器、文件和检查器，保原首错及每个未完责任供重试。|
|[`CSVObservationRead.close`](#api-CSVObservationRead-close)|可重试释放本read及事实费，不关闭借用来源、其他请求或删除文件。|
|[`_ObservationCSVResources`](#api-_ObservationCSVResources)|只为可选新路径补事务式预算责任，沿用原样本及装箱估算和金额。|
|[`_ObservationCSVResources.__init__`](#api-_ObservationCSVResources-__init__)|建立实际槽后调用原检查器构造，固定读取费用仍为原65536字节。|
|[`_ObservationCSVResources._sync`](#api-_ObservationCSVResources-_sync)|同步原charges视图与实际属性槽。|
|[`_ObservationCSVResources._add`](#api-_ObservationCSVResources-_add)|申请成功前后取消均登记实际自有槽，不从其他owner余额推测。|
|[`_ObservationCSVResources._release_amount`](#api-_ObservationCSVResources-_release_amount)|只抵销某用途一笔已计入的资源字节数，释放前后取消都保留正确剩余。|
|[`_ObservationCSVResources._release`](#api-_ObservationCSVResources-_release)|抵销用途完整余额。|
|[`_ObservationCSVResources._move`](#api-_ObservationCSVResources-_move)|在已付款用途间交接金额，不增加或释放共享预算。|
|[`_ObservationCSVResources.lines`](#api-_ObservationCSVResources-lines)|建立原物理行读取的事务式费用包装。|
|[`_ObservationCSVResources.records`](#api-_ObservationCSVResources-records)|包装原csv.reader的费用交接。|
|[`_ObservationCSVResources.after_pack`](#api-_ObservationCSVResources-after_pack)|沿原金额把装箱workspace交给数组与协议，余量释放取消仍保持可恢复。|
|[`_ObservationCSVResources.close`](#api-_ObservationCSVResources-close)|逐实际用途抵销，全部成功后才closed和移除自有登记。|
|[`_ObservationPhysicalLines`](#api-_ObservationPhysicalLines)|沿原readline限长算法，在临时物理行费用释放前后取消时保留实际槽。|
|[`_ObservationPhysicalLines.__next__`](#api-_ObservationPhysicalLines-__next__)|按原容量真实读取一物理行，只更换已计入的资源字节数的事务式抵销。|
|[`_ObservationCSVRecords`](#api-_ObservationCSVRecords)|保留原csv.reader记录与物理行语义，只显式交接已付款的读取责任槽。|
|[`_ObservationCSVRecords.__next__`](#api-_ObservationCSVRecords-__next__)|先从原解释器取完整记录，再把reading费用转给表头或当前行。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from uuid import uuid4
from ..core.validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
from ..sources.models import ReadRequest
from ..sources.signal_csv import SignalCSVSourceAdapter
from ..sources.protocol import SourceReadError
from ..results.errors import BudgetExceededError, ResultClosedError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .csv_reader import _CSVResources, _PhysicalLines, _CSVRecords
from .history import _metadata_bytes
```

</details>

<a id="api-CSVObservation"></a>
## `CSVObservation`

保存单个实际完成read的原行时间范围，不代替来源文件身份或同步证明。

request是本read实际使用的原对象，read_identity对应生产它的read.identity。
row_count为非空且通过原时间解析的行数；完整无时间行时两个端点均为None。
模型只校验字段，后继调度仍须借实际read及其完成事实，不能凭手造模型证明读取。

```python
class CSVObservation
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|本次实际来源名称。|
|`session_id`|str|是|无|原请求所属会话。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|真正读取所用原请求，保持对象身份而非复制值。|
|`read_identity`|str|是|无|每次独立读取的新身份，同一request的两次读不会相同。|
|`first_ns`|int &#124; None|是|无|第一条实际原时间行的转换后整数ns，空输入为None。|
|`last_ns`|int &#124; None|是|无|最后一条实际原时间行的转换后整数ns，空输入为None。|
|`row_count`|int|是|无|原时间行总数，空投影也计，不按信号列样本数计算。|
|`source_eof`|bool|是|无|仅完整whole-source EOF的事实，完成模型必须为True。|

源码：[`src/chronaxis/execution/csv_observation.py:36`](../../../src/chronaxis/execution/csv_observation.py#L36)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservation-__post_init__"></a>
### `CSVObservation.__post_init__`

校验完成事实结构，不读取文件、推测端点或修改原请求。

```python
CSVObservation.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，使用创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、身份、整数时间或行数矛盾。

本函数直接报告的具体错误：

- `ValueError`：CSV观测须保留实际会话的原ReadRequest。
- `ValueError`：CSV观测须为非负原生行数及完整来源EOF。
- `ValueError`：空CSV观测的首末时间须均为None。
- `ValueError`：CSV观测首末时间不能回退。

源码：[`src/chronaxis/execution/csv_observation.py:53`](../../../src/chronaxis/execution/csv_observation.py#L53)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead"></a>
## `CSVObservationRead`

拥有一次原生成器、可选检查器和单当前批，固定事实费到显式close释放。

_iterator、_resources及_handle分别保留最高真实责任，清理失败可重试。
_candidate仅为原生成器的末端候选；_exhausted要求真正StopIteration和清理成功。
正常完成后移除适配器活动登记，_observation可独立存活至本owner关闭。

```python
CSVObservationRead(owner, request)
```


源码：[`src/chronaxis/execution/csv_observation.py:77`](../../../src/chronaxis/execution/csv_observation.py#L77)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-__init__"></a>
### `CSVObservationRead.__init__`

先申请保存本次请求和观测记录的内存，再创建读取生成器；此时尚未打开输入文件。

```python
CSVObservationRead.__init__(owner, request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BudgetedSignalCSVSourceAdapter](chronaxis.execution.csv_reader.md#api-BudgetedSignalCSVSourceAdapter)|是|无|位置或关键字。owner为实际BudgetedSignalCSVSourceAdapter|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为原ReadRequest。|

#### 返回说明

独立读取owner。

#### 异常说明

原配置或预算异常；持续清理失败附最高恢复owner。

本函数直接报告的具体错误：

- `TypeError`：CSV观测读取需实际预算CSV来源及ReadRequest。

源码：[`src/chronaxis/execution/csv_observation.py:85`](../../../src/chronaxis/execution/csv_observation.py#L85)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-identity"></a>
### `CSVObservationRead.identity`

读取本read独立身份。

```python
CSVObservationRead.identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

非空str。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_observation.py:118`](../../../src/chronaxis/execution/csv_observation.py#L118)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-closed"></a>
### `CSVObservationRead.closed`

查看本对象负责的资源是否已经全部关闭。

```python
CSVObservationRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_observation.py:124`](../../../src/chronaxis/execution/csv_observation.py#L124)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-failed"></a>
### `CSVObservationRead.failed`

查看此前的读取操作是否失败。

```python
CSVObservationRead.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_observation.py:130`](../../../src/chronaxis/execution/csv_observation.py#L130)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-exhausted"></a>
### `CSVObservationRead.exhausted`

查看输入是否已经正常读完。

```python
CSVObservationRead.exhausted
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示输入或结果已正常读完；False表示尚未正常读完。发生异常不等于正常读完。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_observation.py:136`](../../../src/chronaxis/execution/csv_observation.py#L136)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-observation"></a>
### `CSVObservationRead.observation`

借读本次已完成的冻结观测，借期到本read的close。

```python
CSVObservationRead.observation
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

CSVObservation。

#### 异常说明

ResultClosedError为未完成、失败或关闭。

本函数直接报告的具体错误：

- `ResultClosedError`：CSV观测读取尚未正常完成或已关闭。

源码：[`src/chronaxis/execution/csv_observation.py:142`](../../../src/chronaxis/execution/csv_observation.py#L142)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_read_resources"></a>
### `CSVObservationRead._read_resources`

为本次生成器建立独立事务式检查器，在文件打开前保留最高责任。

```python
CSVObservationRead._read_resources()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

_ObservationCSVResources。

#### 异常说明

原预算、登记或构造错误。

源码：[`src/chronaxis/execution/csv_observation.py:152`](../../../src/chronaxis/execution/csv_observation.py#L152)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_created_iterator"></a>
### `CSVObservationRead._created_iterator`

在原活动set登记前接住本次实际生成器。

```python
CSVObservationRead._created_iterator(iterator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`iterator`|Iterator[SignalBatch]|是|无|位置或关键字。本次CSV请求创建的生成器；关闭读取时一并关闭它。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_observation.py:166`](../../../src/chronaxis/execution/csv_observation.py#L166)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_opened_handle"></a>
### `CSVObservationRead._opened_handle`

在适配器set登记前接住本次真实文件句柄。

```python
CSVObservationRead._opened_handle(handle)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|TextIO|是|无|位置或关键字。本次输入文件已经打开的文本读取对象；用于逐行读取或关闭，不传文件名字符串。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_observation.py:174`](../../../src/chronaxis/execution/csv_observation.py#L174)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_close_handle"></a>
### `CSVObservationRead._close_handle`

沿原文件关闭动作保根因，并保留实际未关闭句柄供重试。

```python
CSVObservationRead._close_handle(handle, primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|TextIO|是|无|位置或关键字。本次输入文件已经打开的文本读取对象；用于逐行读取或关闭，不传文件名字符串。|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无业务根因时原关闭错误传播，已有根因只补note。

源码：[`src/chronaxis/execution/csv_observation.py:182`](../../../src/chronaxis/execution/csv_observation.py#L182)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_close_resources"></a>
### `CSVObservationRead._close_resources`

原生成器退出时清理本次检查器，清理失败不覆盖业务或取消根因。

```python
CSVObservationRead._close_resources(primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

正常退出时的原资源关闭错误。

本函数直接报告的具体错误：

- `SourceReadError`：CSV观测文件尚未成功关闭。

源码：[`src/chronaxis/execution/csv_observation.py:199`](../../../src/chronaxis/execution/csv_observation.py#L199)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_end_file"></a>
### `CSVObservationRead._end_file`

清理单文件表头及行费用，保留现场正在传播的读取或关闭主异常。

```python
CSVObservationRead._end_file(resources, primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`resources`|[_CSVResources](chronaxis.execution.csv_reader.md#api-_CSVResources)|是|无|位置或关键字。负责当前CSV读取的缓冲、行大小和资源额度检查对象，必须与本次读取对应。|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

正常文件结束或GeneratorExit时的原清理错误继续传播；
    已有其他主异常时仅给它增加note，事务式费用槽留待同一read.close重试。

源码：[`src/chronaxis/execution/csv_observation.py:216`](../../../src/chronaxis/execution/csv_observation.py#L216)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_accept_candidate"></a>
### `CSVObservationRead._accept_candidate`

仅接收原生成器最终协议成功后的候选，不在此声明完成。

```python
CSVObservationRead._accept_candidate(first, last, count)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`first`|int &#124; None|是|无|位置或关键字。本次读取遇到的第一行时间，单位纳秒；没有任何行时为None。|
|`last`|int &#124; None|是|无|位置或关键字。本次读取遇到的最后一行时间，单位纳秒；没有任何行时为None。|
|`count`|int|是|无|位置或关键字。实际读取的原始行数，空文件为0；不是筛选后返回的样本数。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常，最终带有明确类型的字段在真正耗尽后校验。

源码：[`src/chronaxis/execution/csv_observation.py:232`](../../../src/chronaxis/execution/csv_observation.py#L232)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_adopt_cleanup"></a>
### `CSVObservationRead._adopt_cleanup`

接管本路径实际未返回的最高资源检查器。

```python
CSVObservationRead._adopt_cleanup(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_observation.py:241`](../../../src/chronaxis/execution/csv_observation.py#L241)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-__iter__"></a>
### `CSVObservationRead.__iter__`

返回当前读取对象，继续使用当前读取位置。

```python
CSVObservationRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

ResultClosedError为不可推进。

源码：[`src/chronaxis/execution/csv_observation.py:251`](../../../src/chronaxis/execution/csv_observation.py#L251)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_ensure_active"></a>
### `CSVObservationRead._ensure_active`

拒绝关闭、清理或失败后的推进。

```python
CSVObservationRead._ensure_active()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：CSV观测读取已关闭、正在清理或推进失败。

源码：[`src/chronaxis/execution/csv_observation.py:258`](../../../src/chronaxis/execution/csv_observation.py#L258)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-__next__"></a>
### `CSVObservationRead.__next__`

转交原batch，真正StopIteration并成功清理后才安装完成事实。

```python
CSVObservationRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

原SignalBatch。

#### 异常说明

正常StopIteration；原读取、预算或取消错误
    保留csv_observation_read_cleanup_owner，失败后仅可close。

源码：[`src/chronaxis/execution/csv_observation.py:265`](../../../src/chronaxis/execution/csv_observation.py#L265)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-_close_request"></a>
### `CSVObservationRead._close_request`

关闭本次原生成器、文件和检查器，保原首错及每个未完责任供重试。

```python
CSVObservationRead._close_request()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

首个真实关闭错误，其他错误附note而不覆盖。

源码：[`src/chronaxis/execution/csv_observation.py:300`](../../../src/chronaxis/execution/csv_observation.py#L300)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CSVObservationRead-close"></a>
### `CSVObservationRead.close`

可重试释放本read及事实费，不关闭借用来源、其他请求或删除文件。

```python
CSVObservationRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

原文件、子资源或预算取消，未完责任保留。

源码：[`src/chronaxis/execution/csv_observation.py:344`](../../../src/chronaxis/execution/csv_observation.py#L344)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources"></a>
## `_ObservationCSVResources`

只为可选新路径补事务式预算责任，沿用原样本及装箱估算和金额。

各用途已计入的资源字节数既保留在固定属性槽也同步到原charges检查接口；_held_cost
仅为本资源的实际总额。清理取消前后均能重试，不提前closed或丢已付款槽。

```python
_ObservationCSVResources(owner)
```

继承关系：[_CSVResources](chronaxis.execution.csv_reader.md#api-_CSVResources)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/csv_observation.py:361`](../../../src/chronaxis/execution/csv_observation.py#L361)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-__init__"></a>
### `_ObservationCSVResources.__init__`

建立实际槽后调用原检查器构造，固定读取费用仍为原65536字节。

```python
_ObservationCSVResources.__init__(owner)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BudgetedSignalCSVSourceAdapter](chronaxis.execution.csv_reader.md#api-BudgetedSignalCSVSourceAdapter)|是|无|位置或关键字。创建该资源接收器的CSV适配器，持有本次读取使用的资源额度。|

#### 返回说明

独立检查器。

#### 异常说明

原预算或取消错误，附恢复owner。

源码：[`src/chronaxis/execution/csv_observation.py:368`](../../../src/chronaxis/execution/csv_observation.py#L368)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-_sync"></a>
### `_ObservationCSVResources._sync`

同步原charges视图与实际属性槽。

```python
_ObservationCSVResources._sync(key)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|str|是|无|位置或关键字。本次资源申请的用途名称。归还额度时使用申请时登记的同一名称，便于核对哪一部分仍占用资源。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_observation.py:383`](../../../src/chronaxis/execution/csv_observation.py#L383)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-_add"></a>
### `_ObservationCSVResources._add`

申请成功前后取消均登记实际自有槽，不从其他owner余额推测。

```python
_ObservationCSVResources._add(key, amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|str|是|无|位置或关键字。本次资源申请的用途名称。归还额度时使用申请时登记的同一名称，便于核对哪一部分仍占用资源。|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原预算或取消错误。

源码：[`src/chronaxis/execution/csv_observation.py:393`](../../../src/chronaxis/execution/csv_observation.py#L393)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-_release_amount"></a>
### `_ObservationCSVResources._release_amount`

只抵销某用途一笔已计入的资源字节数，释放前后取消都保留正确剩余。

```python
_ObservationCSVResources._release_amount(key, amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|str|是|无|位置或关键字。本次资源申请的用途名称。归还额度时使用申请时登记的同一名称，便于核对哪一部分仍占用资源。|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放或取消错误。

源码：[`src/chronaxis/execution/csv_observation.py:404`](../../../src/chronaxis/execution/csv_observation.py#L404)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-_release"></a>
### `_ObservationCSVResources._release`

抵销用途完整余额。

```python
_ObservationCSVResources._release(key)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|str|是|无|位置或关键字。本次资源申请的用途名称。归还额度时使用申请时登记的同一名称，便于核对哪一部分仍占用资源。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放取消。

源码：[`src/chronaxis/execution/csv_observation.py:415`](../../../src/chronaxis/execution/csv_observation.py#L415)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-_move"></a>
### `_ObservationCSVResources._move`

在已付款用途间交接金额，不增加或释放共享预算。

```python
_ObservationCSVResources._move(source, target, amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|位置或关键字。转出资源预约量的计数属性名。|
|`target`|str|是|无|位置或关键字。接收资源预约量的计数属性名；转移前后的预约总量保持不变。|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为内部金额矛盾。

本函数直接报告的具体错误：

- `ValueError`：CSV观测资源交接超出原用途余额。

源码：[`src/chronaxis/execution/csv_observation.py:421`](../../../src/chronaxis/execution/csv_observation.py#L421)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-lines"></a>
### `_ObservationCSVResources.lines`

建立原物理行读取的事务式费用包装。

```python
_ObservationCSVResources.lines(handle)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|TextIO|是|无|位置或关键字。本次输入文件已经打开的文本读取对象；用于逐行读取或关闭，不传文件名字符串。|

#### 返回说明

行游标。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_observation.py:435`](../../../src/chronaxis/execution/csv_observation.py#L435)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-records"></a>
### `_ObservationCSVResources.records`

包装原csv.reader的费用交接。

```python
_ObservationCSVResources.records(reader)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|Iterator[list[str]]|是|无|位置或关键字。csv.reader创建的记录迭代器，每次返回一行单元格；引号内的换行仍属于同一条记录。|

#### 返回说明

原记录游标。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_observation.py:442`](../../../src/chronaxis/execution/csv_observation.py#L442)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-after_pack"></a>
### `_ObservationCSVResources.after_pack`

沿原金额把装箱workspace交给数组与协议，余量释放取消仍保持可恢复。

```python
_ObservationCSVResources.after_pack(validator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`validator`|BatchValidator|是|无|位置或关键字。本次读取请求的批次检查器，用它检查样本、进度和结束标记；不同请求不能共用推进状态。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原账本或取消错误。

源码：[`src/chronaxis/execution/csv_observation.py:448`](../../../src/chronaxis/execution/csv_observation.py#L448)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVResources-close"></a>
### `_ObservationCSVResources.close`

逐实际用途抵销，全部成功后才closed和移除自有登记。

```python
_ObservationCSVResources.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

原释放取消，尚未抵销槽保留供重试。

源码：[`src/chronaxis/execution/csv_observation.py:461`](../../../src/chronaxis/execution/csv_observation.py#L461)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationPhysicalLines"></a>
## `_ObservationPhysicalLines`

沿原readline限长算法，在临时物理行费用释放前后取消时保留实际槽。

```python
class _ObservationPhysicalLines(_PhysicalLines)
```

继承关系：[_PhysicalLines](chronaxis.execution.csv_reader.md#api-_PhysicalLines)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/csv_observation.py:477`](../../../src/chronaxis/execution/csv_observation.py#L477)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationPhysicalLines-__next__"></a>
### `_ObservationPhysicalLines.__next__`

按原容量真实读取一物理行，只更换已计入的资源字节数的事务式抵销。

```python
_ObservationPhysicalLines.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

原含换行文本，真实EOF停止。

#### 异常说明

原I/O、预算或取消错误。

本函数直接报告的具体错误：

- `BudgetExceededError`：CSV物理行/引用记录累积超出剩余RAM估算。
- `BudgetExceededError`：CSV物理行超过剩余RAM允许长度，未解析截断行。

源码：[`src/chronaxis/execution/csv_observation.py:480`](../../../src/chronaxis/execution/csv_observation.py#L480)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVRecords"></a>
## `_ObservationCSVRecords`

保留原csv.reader记录与物理行语义，只显式交接已付款的读取责任槽。

```python
class _ObservationCSVRecords(_CSVRecords)
```

继承关系：[_CSVRecords](chronaxis.execution.csv_reader.md#api-_CSVRecords)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/csv_observation.py:510`](../../../src/chronaxis/execution/csv_observation.py#L510)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_ObservationCSVRecords-__next__"></a>
### `_ObservationCSVRecords.__next__`

先从原解释器取完整记录，再把reading费用转给表头或当前行。

```python
_ObservationCSVRecords.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

原单元格list。

#### 异常说明

原EOF、CSV、I/O、预算或取消错误。

源码：[`src/chronaxis/execution/csv_observation.py:513`](../../../src/chronaxis/execution/csv_observation.py#L513)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
