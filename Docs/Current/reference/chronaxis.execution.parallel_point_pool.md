# `chronaxis.execution.parallel_point_pool`

time_order直接积分的读取段：文件工作进程产出组点，主进程谁先就绪先收并写入暂存。

PERF-P5-ORDER-01 A2-4、A2-5。输入是一个time_order连续来源的全部文件和已验证的数值声明；
输出是每个文件一个`<文件序号>.points`暂存文件（原样保存P5G1组点包）和各文件的最终事实
（观测首末、原帧数、解码次数、帧型兼容提示、实际帧型）。

流程：
1. 复用ParallelIntegralPool启动有限工作槽、核对READY与DBC元数据、下发points模式任务；
2. 轮询全部槽，哪个槽的包先到就先收：只用decode_points_prefix读到事实为止，核对文件号与块号后
   原样追加到该文件的暂存，再许可下一块；事件部分不在这里解码；
3. 文件EOF并收到finished确认后，该槽领取下一个文件；
4. 读取段错误报文件序号最小者：序号更小的文件继续读完或出错，更大的文件不再推进。

所有进程、管道和预算归本池；暂存文件归PointSpool。关闭不删除输入、用户文件或其他目录。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 继承字段

- `ParallelPointPool`同时继承[ParallelIntegralPool](chronaxis.execution.parallel_integral_pool.md#api-ParallelIntegralPool)字段：`_FILE_MERGE`。构造时须一并提供基类的必填字段；类型、默认值及约束按基类表。

## 相关类型

[ControlProtocolError](chronaxis._control_wire.md#api-ControlProtocolError)、[ParallelIntegralPool](chronaxis.execution.parallel_integral_pool.md#api-ParallelIntegralPool)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|
|[`ParallelPointPool`](#api-ParallelPointPool)|一个time_order来源的组点工作槽池；不归并、不累计，只负责读取段与文件事实。|
|[`ParallelPointPool.__init__`](#api-ParallelPointPool-__init__)|登记来源并预约固定声明空间，不读原文件。|
|[`ParallelPointPool.points_minimum_cost`](#api-ParallelPointPool-points_minimum_cost)|查询全部工作槽组点任务的必要费用下界，用于创建进程前排除必然不足的预算。|
|[`ParallelPointPool._dispatch`](#api-ParallelPointPool-_dispatch)|给空槽派发下一文件，文件命令同时声明points模式。|
|[`ParallelPointPool._configuration`](#api-ParallelPointPool-_configuration)|构造points模式任务并计算配置需要的额外预约费用。|
|[`ParallelPointPool._accept_point_facts`](#api-ParallelPointPool-_accept_point_facts)|更新一个文件截至本包的累计事实，不做concatenate的文件边界时间检查。|
|[`ParallelPointPool._store`](#api-ParallelPointPool-_store)|把槽中已收到的一个组点包写入暂存并许可下一块。|
|[`ParallelPointPool._exit_error`](#api-ParallelPointPool-_exit_error)|把管道断开转成指明文件和退出码的工作进程退出错误。|
|[`ParallelPointPool.spool_all`](#api-ParallelPointPool-spool_all)|执行读取段：收齐全部文件的组点包写入暂存，或报出文件序号最小的读取段错误。|
|[`PointSpool`](#api-PointSpool)|本次组点暂存的唯一owner：一个独占目录、每文件一个暂存文件及归并缓冲预约。|
|[`PointSpool.__init__`](#api-PointSpool-__init__)|独占新建暂存目录，不创建文件。|
|[`PointSpool.append`](#api-PointSpool-append)|把一个组点包原样追加到该文件的暂存。|
|[`PointSpool.open_readers`](#api-PointSpool-open_readers)|结束写入并为每个文件打开读回句柄，预约每文件一个块的归并缓冲。|
|[`PointSpool.next_packet`](#api-PointSpool-next_packet)|读回并完整解码一个文件的下一个组点包。|
|[`PointSpool.close`](#api-PointSpool-close)|关闭句柄、删除登记的暂存文件和目录并退还归并预约。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from __future__ import annotations
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from .._control_wire import ControlProtocolError
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.protocol import SourceReadError
from .file_group_points import file_points_cost, file_points_minimum_cost
from .history import _metadata_bytes
from .integral_blocks import BLOCK_RAM, WIRE_LIMIT, decode_points, decode_points_prefix, pack_task
from .parallel_integral_pool import ParallelIntegralPool, _configuration_rows, _task_bytes, _TASK_BASE_COST
```

</details>

<a id="api-ParallelPointPool"></a>
## `ParallelPointPool`

一个time_order来源的组点工作槽池；不归并、不累计，只负责读取段与文件事实。

```python
ParallelPointPool(spec, budget, signals, *, process_count, **options)
```

继承关系：[ParallelIntegralPool](chronaxis.execution.parallel_integral_pool.md#api-ParallelIntegralPool)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`_FILE_MERGE`|类属性|类成员，不作为构造参数填写|'time_order'|组点池只服务time_order来源。|

源码：[`src/chronaxis/execution/parallel_point_pool.py:35`](../../../src/chronaxis/execution/parallel_point_pool.py#L35)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-ParallelPointPool-__init__"></a>
### `ParallelPointPool.__init__`

登记来源并预约固定声明空间，不读原文件。

```python
ParallelPointPool.__init__(spec, budget, signals, *, process_count, **options)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CANTextSpec|是|无|位置或关键字。file_merge为time_order的单一ASC/BLF来源声明。|
|`budget`|ResourceBudget|是|无|位置或关键字。父会话共享预算；池的固定费、工作槽和元数据都在其中预约。|
|`signals`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本来源需要读取的原信号定义。|
|`process_count`|int|是|无|仅关键字。正整数工作进程上限，实际不超过文件数。|
|`options`|dict|否|{}|可变关键字。options为与现有time_order读取相同的读取选项。|

#### 返回说明

None，构造新的池owner。

#### 异常说明

进程数或合并方式非法、空文件列表、原帧上下文时ValueError；预算不足时BudgetExceededError，
    清理失败附parallel_integral_pool_cleanup_owner。

源码：[`src/chronaxis/execution/parallel_point_pool.py:40`](../../../src/chronaxis/execution/parallel_point_pool.py#L40)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-ParallelPointPool-points_minimum_cost"></a>
### `ParallelPointPool.points_minimum_cost`

查询全部工作槽组点任务的必要费用下界，用于创建进程前排除必然不足的预算。

```python
ParallelPointPool.points_minimum_cost(signal_count: int, *, process_count: int, file_count: int) -> int
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`signal_count`|int|是|无|位置或关键字。signal_count为非负信号定义数|
|`process_count`|int|是|无|仅关键字。正整数工作进程上限。|
|`file_count`|int|是|无|仅关键字。来源的文件数，正整数；实际工作槽数取它与进程上限中较小者。|

#### 返回说明

int字节数，含父任务与每个工作槽的固定重建和组点状态；不含DBC和声明图。

#### 异常说明

非法数量时ValueError；不创建进程或修改预算。

返回类型：int。

源码：[`src/chronaxis/execution/parallel_point_pool.py:53`](../../../src/chronaxis/execution/parallel_point_pool.py#L53)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-ParallelPointPool-_dispatch"></a>
### `ParallelPointPool._dispatch`

给空槽派发下一文件，文件命令同时声明points模式。

```python
ParallelPointPool._dispatch(slot, index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict|是|无|位置或关键字。已空闲、可领取下一个文件的工作槽。|
|`index`|int|是|无|位置或关键字。要派发的文件序号。|

#### 返回说明

None。

#### 异常说明

发送失败。

与父类相同地重置槽状态；第7个参数使工作进程在READY前出错时也不附加notes（A2-4）。

源码：[`src/chronaxis/execution/parallel_point_pool.py:65`](../../../src/chronaxis/execution/parallel_point_pool.py#L65)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-ParallelPointPool-_configuration"></a>
### `ParallelPointPool._configuration`

构造points模式任务并计算配置需要的额外预约费用。

```python
ParallelPointPool._configuration(definitions, expressions, specs, binding, session_id, derived, domain, batch_intervals, step_ns=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。已补齐有效期的信号定义。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。与计算项同序的静态表达式。|
|`specs`|tuple[CalculationDefinition, ...]|是|无|位置或关键字。与表达式同序的积分计算项。|
|`binding`|SameFrameBinding|是|无|位置或关键字。同次DBC证明的共同报文定位。|
|`session_id`|str|是|无|位置或关键字。当前会话名。|
|`derived`|tuple[DerivedDefinition, ...]|是|无|位置或关键字。计划声明的派生定义，可为空。|
|`domain`|Interval &#124; None|是|无|位置或关键字。请求范围；省略时为None。|
|`batch_intervals`|int|是|无|位置或关键字。用户正整数区间批上限，传输任务另限到64。|
|`step_ns`|int &#124; None|否|None|位置或关键字。None为实际间隔，正整数为固定间隔纳秒。|

#### 返回说明

tuple[dict, int, int]，依次为固定task、父任务字节费和每子额外字节费（组点状态而非面积缓冲）。

#### 异常说明

批上限非法时ValueError；声明展开或静态费用原错误继续传播。

源码：[`src/chronaxis/execution/parallel_point_pool.py:76`](../../../src/chronaxis/execution/parallel_point_pool.py#L76)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-ParallelPointPool-_accept_point_facts"></a>
### `ParallelPointPool._accept_point_facts`

更新一个文件截至本包的累计事实，不做concatenate的文件边界时间检查。

```python
ParallelPointPool._accept_point_facts(index, facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。事实所属的文件序号。|
|`facts`|dict|是|无|位置或关键字。decode_points_prefix得到的本文件累计事实。|

#### 返回说明

None。

#### 异常说明

计数回退或已记录的实际帧型改变时ControlProtocolError。

源码：[`src/chronaxis/execution/parallel_point_pool.py:95`](../../../src/chronaxis/execution/parallel_point_pool.py#L95)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-ParallelPointPool-_store"></a>
### `ParallelPointPool._store`

把槽中已收到的一个组点包写入暂存并许可下一块。

```python
ParallelPointPool._store(slot, index, spool)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict|是|无|位置或关键字。已收到一个组点包的当前文件槽。|
|`index`|int|是|无|位置或关键字。该槽正在读取的文件序号。|
|`spool`|[PointSpool](chronaxis.execution.parallel_point_pool.md#api-PointSpool)|是|无|位置或关键字。本次组点暂存，包原样追加到该文件的暂存文件。|

#### 返回说明

None。

#### 异常说明

包内身份或块号不符时ControlProtocolError；前缀非法时IntegralBlockError；暂存配额或磁盘错误原样传播。

源码：[`src/chronaxis/execution/parallel_point_pool.py:120`](../../../src/chronaxis/execution/parallel_point_pool.py#L120)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-ParallelPointPool-_exit_error"></a>
### `ParallelPointPool._exit_error`

把管道断开转成指明文件和退出码的工作进程退出错误。

```python
ParallelPointPool._exit_error(error)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|BrokenPipeError &#124; EOFError &#124; ConnectionError|是|无|位置或关键字。轮询或发送读取许可时遇到的管道断开异常。|

#### 返回说明

SourceReadError；找不到已退出的工作进程时返回原error，由调用方原样抛出。

#### 异常说明

无；只等待各进程最多0.5秒以取得真实退出码。

源码：[`src/chronaxis/execution/parallel_point_pool.py:144`](../../../src/chronaxis/execution/parallel_point_pool.py#L144)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-ParallelPointPool-spool_all"></a>
### `ParallelPointPool.spool_all`

执行读取段：收齐全部文件的组点包写入暂存，或报出文件序号最小的读取段错误。

```python
ParallelPointPool.spool_all(spool)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spool`|[PointSpool](chronaxis.execution.parallel_point_pool.md#api-PointSpool)|是|无|位置或关键字。本次组点暂存，负责暂存文件与配额。|

#### 返回说明

None；成功后file_facts含每个文件的最终事实，可关闭本池再归并。

#### 异常说明

读取段错误时SourceReadError('{路径}: {类型}: {信息}')；工作进程退出、协议或暂存错误原样传播；
    任何失败都清理本池的进程与费用（附parallel_integral_pool_cleanup_owner）。

源码：[`src/chronaxis/execution/parallel_point_pool.py:161`](../../../src/chronaxis/execution/parallel_point_pool.py#L161)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-PointSpool"></a>
## `PointSpool`

本次组点暂存的唯一owner：一个独占目录、每文件一个暂存文件及归并缓冲预约。

写入段只追加，读回段每个文件同一时间只展开一个包；关闭时只删除本次登记的文件和目录。

```python
PointSpool(budget, work_dir, file_count, *, integrity=False)
```


源码：[`src/chronaxis/execution/parallel_point_pool.py:230`](../../../src/chronaxis/execution/parallel_point_pool.py#L230)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-PointSpool-__init__"></a>
### `PointSpool.__init__`

独占新建暂存目录，不创建文件。

```python
PointSpool.__init__(budget, work_dir, file_count, *, integrity=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。共享预算；写包时计入spool_quota_bytes，读回前预约归并缓冲。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次会话自有工作目录，暂存目录建在其下。|
|`file_count`|int|是|无|位置或关键字。来源的文件数，正整数。|
|`integrity`|bool|否|False|仅关键字。integrity为True时每包附SHA-256（直接积分计划不开完整性诊断，实际为False）。|

#### 返回说明

None。

#### 异常说明

文件数非法时ValueError；目录已存在或无法创建时OSError；构造清理失败附point_spool_cleanup_owner。

源码：[`src/chronaxis/execution/parallel_point_pool.py:236`](../../../src/chronaxis/execution/parallel_point_pool.py#L236)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-PointSpool-append"></a>
### `PointSpool.append`

把一个组点包原样追加到该文件的暂存。

```python
PointSpool.append(index, packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。包所属的文件序号。|
|`packet`|bytes|是|无|位置或关键字。已核前缀的完整P5G1包。|

#### 返回说明

None。

#### 异常说明

已开始读回或已关闭时ValueError；暂存配额不足时BudgetExceededError；独占创建或写入失败时OSError。
P5G1自带8字节包头分帧，不另存长度；开启integrity时在包头后写SHA-256。

源码：[`src/chronaxis/execution/parallel_point_pool.py:263`](../../../src/chronaxis/execution/parallel_point_pool.py#L263)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-PointSpool-open_readers"></a>
### `PointSpool.open_readers`

结束写入并为每个文件打开读回句柄，预约每文件一个块的归并缓冲。

```python
PointSpool.open_readers()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

某文件没有任何暂存包时SourceReadError；预算不足时BudgetExceededError；打开失败时OSError。

源码：[`src/chronaxis/execution/parallel_point_pool.py:287`](../../../src/chronaxis/execution/parallel_point_pool.py#L287)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-PointSpool-next_packet"></a>
### `PointSpool.next_packet`

读回并完整解码一个文件的下一个组点包。

```python
PointSpool.next_packet(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。要读回下一个包的文件序号。|

#### 返回说明

PointPacket；该文件已读完时None。

#### 异常说明

截断、长度或标志非法、摘要不符、块号不连续、缺少EOF或EOF后仍有数据时SourceReadError；
    包内容非法时IntegralBlockError。

源码：[`src/chronaxis/execution/parallel_point_pool.py:304`](../../../src/chronaxis/execution/parallel_point_pool.py#L304)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-PointSpool-close"></a>
### `PointSpool.close`

关闭句柄、删除登记的暂存文件和目录并退还归并预约。

```python
PointSpool.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；成功后幂等。

#### 异常说明

删除或rmdir失败时OSError原样抛出（目录中有未登记文件时rmdir失败，不递归删除），保留owner供重试。

源码：[`src/chronaxis/execution/parallel_point_pool.py:341`](../../../src/chronaxis/execution/parallel_point_pool.py#L341)（行号对应 Chronaxis 0.1.0 源码）。
