# chronaxis.results.spool

把结果行先写到专用临时目录，内存中只保留有限缓冲；写入结束后按稳定顺序合并各部分。之后可顺序读取并发布结果。写入或关闭失败时保留错误和清理所需资源，避免把不完整文件当作完成结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`_buffer_key`](#api-_buffer_key)|取已缓存排序键，避免sort期间生成无界的新对象树。|
|[`ResultSpool`](#api-ResultSpool)|保存building/analysis_complete/failed/cancelled状态及本次固定启用表计数。|
|[`ResultSpool.__init__`](#api-ResultSpool-__init__)|创建唯一工作目录并预留固定状态成本。|
|[`ResultSpool._require_building`](#api-ResultSpool-_require_building)|拒绝关闭或已封口后的追加，保持最终结果不变。|
|[`ResultSpool.row_limit`](#api-ResultSpool-row_limit)|提供本表成功追加的实际最大行长，所有表仍受原编码硬限约束。|
|[`ResultSpool.reader_cost_for`](#api-ResultSpool-reader_cost_for)|按已知表上界预付解析及FD空间，原64倍工作费不降低。|
|[`ResultSpool.append`](#api-ResultSpool-append)|预算检查后编码并暂存一行，必要时先释放已有缓冲。|
|[`ResultSpool._append_core`](#api-ResultSpool-_append_core)|预算先于编码，成功登记后再按有限行数落盘。|
|[`ResultSpool._run_path`](#api-ResultSpool-_run_path)|以受控常量和计数生成run路径，不接受用户行中的路径。|
|[`ResultSpool._write_bytes`](#api-ResultSpool-_write_bytes)|配额预留后完整写bytes，短写继续，零写明确失败。|
|[`ResultSpool._clear_buffer`](#api-ResultSpool-_clear_buffer)|抵销所有缓冲申请并释放对象，不删除已写文件。|
|[`ResultSpool._flush`](#api-ResultSpool-_flush)|将有限缓冲排序并按表依次写run，异常也释放RAM。|
|[`ResultSpool._read_entry`](#api-ResultSpool-_read_entry)|有界读取一行，按当前格式重建稳定键。|
|[`ResultSpool._merge`](#api-ResultSpool-_merge)|用双路预算，将真实FD关闭与恢复交给共用归并owner。|
|[`ResultSpool.seal`](#api-ResultSpool-seal)|落盘并完成有限外部排序，成功后标analysis_complete。|
|[`ResultSpool._seal_table`](#api-ResultSpool-_seal_table)|完成一个有后续消费者的最终表，其他表仍可追加，不另复制中间阶段。|
|[`ResultSpool._fail`](#api-ResultSpool-_fail)|保存明确失败状态，诊断写失败不能掩盖原异常。|
|[`ResultSpool.close`](#api-ResultSpool-close)|取消未完成构建，或释放封口对象的固定RAM；重复关闭安全。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from contextlib import ExitStack
from pathlib import Path
from .budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .codec import decode_row, encode_row, estimate_row_bytes
from .rows import ResultRow, row_table, row_sort_key
from .summary import SUMMARY_MODELS
from .owned_directory import directory_identity
from .errors import AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError
```

</details>

<a id="api-_buffer_key"></a>
## `_buffer_key`

取已缓存排序键，避免sort期间生成无界的新对象树。

```python
_buffer_key(item)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`item`|tuple|是|无|位置或关键字。待排序记录，依次保存排序键、JSONL字节、保留内存字节数及认证索引或None；本函数取出排序键。|

### 返回说明

tuple键。

### 异常说明

内部结构错误直接传播。

源码：[`src/chronaxis/results/spool.py:25`](../../../src/chronaxis/results/spool.py#L25)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool"></a>
## `ResultSpool`

保存building/analysis_complete/failed/cancelled状态及本次固定启用表计数。

序号必须严格递增；每个缓冲排序后写run，seal完成预算内有界归并。
不接受已有工作目录，不删除任何暂存；close取消未完成构建。
路径记录只含有限请求表的当前层和run数量，不随结果数保留Python路径列表。
_fixed_cost/_pending_cost/_buffer_cost/_merge_cost合计为_held_cost，仅含自有RAM。
_closing拒绝半关闭继续构建；_closed只有全部自有费用实际释放后才成立。

```python
ResultSpool(budget: ResourceBudget, work_dir=None, result_buffer_rows: int=4096, *, enable_sequences: bool=False, requested_tables=None, failure_diagnostics=True, enable_contributions=False, enable_trace=False, enable_selections=False)
```


源码：[`src/chronaxis/results/spool.py:34`](../../../src/chronaxis/results/spool.py#L34)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-__init__"></a>
### `ResultSpool.__init__`

创建唯一工作目录并预留固定状态成本。

```python
ResultSpool.__init__(budget: ResourceBudget, work_dir=None, result_buffer_rows: int=4096, *, enable_sequences: bool=False, requested_tables=None, failure_diagnostics=True, enable_contributions=False, enable_trace=False, enable_selections=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|位置或关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。None让入口自动创建唯一目录。|
|`result_buffer_rows`|int|否|4096|位置或关键字。result_buffer_rows为行上限|
|`enable_sequences`|bool|否|False|仅关键字。True增加请求响应配对结果表；False不建立此表。|
|`requested_tables`|Iterable[str] &#124; None|否|None|仅关键字。当前输出实际请求的表名；空表仍可被正常迭代，不隐式开启未请求的明细。|
|`failure_diagnostics`|bool|否|True|仅关键字。是否保留详细失败诊断记录；关闭后只保留必要失败信息。|
|`enable_contributions`|bool|否|False|仅关键字。是否构造并保存逐消息贡献行；False从生成处跳过。|
|`enable_trace`|bool|否|False|仅关键字。是否为本次结果创建输入追溯表；未请求时连对应表和逐行记录都不建立。|
|`enable_selections`|bool|否|False|仅关键字。是否创建真实样本选择结果表；只在本次有select请求时启用。|

#### 返回说明

ResultSpool。

#### 异常说明

ValueError/TypeError为配置；预算/目录/取消原样传播；
    持续清理失败附result_spool_cleanup_owner。已有目录保持原样，不写失败诊断。

源码：[`src/chronaxis/results/spool.py:44`](../../../src/chronaxis/results/spool.py#L44)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_require_building"></a>
### `ResultSpool._require_building`

拒绝关闭或已封口后的追加，保持最终结果不变。

```python
ResultSpool._require_building() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError/AnalysisError为状态不符。

本函数直接报告的具体错误：

- `ResultClosedError`：结果暂存已关闭或正在清理。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:112`](../../../src/chronaxis/results/spool.py#L112)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-row_limit"></a>
### `ResultSpool.row_limit`

提供本表成功追加的实际最大行长，所有表仍受原编码硬限约束。

```python
ResultSpool.row_limit(table: str) -> int
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。table为本次启用的固定表名。|

#### 返回说明

正bytes上界，空表为1。

#### 异常说明

ResultFormatError为未知表或内部行长越界；不读取文件猜大小。

本函数直接报告的具体错误：

- `ResultFormatError`：未启用的结果表。
- `ResultFormatError`：结果表已知最大行长非法。

返回类型：int。

源码：[`src/chronaxis/results/spool.py:122`](../../../src/chronaxis/results/spool.py#L122)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-reader_cost_for"></a>
### `ResultSpool.reader_cost_for`

按已知表上界预付解析及FD空间，原64倍工作费不降低。

```python
ResultSpool.reader_cost_for(table: str) -> int
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。table为固定表名。|

#### 返回说明

整数bytes。

#### 异常说明

沿row_limit的类型/上界检查；不创建reader或分配数组。

返回类型：int。

源码：[`src/chronaxis/results/spool.py:136`](../../../src/chronaxis/results/spool.py#L136)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-append"></a>
### `ResultSpool.append`

预算检查后编码并暂存一行，必要时先释放已有缓冲。

```python
ResultSpool.append(row: ResultRow) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|ResultRow|是|无|位置或关键字。row为最终带有明确类型的行且sequence严格递增。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

AnalysisError/预算/格式错误；失败后不再接受追加。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:146`](../../../src/chronaxis/results/spool.py#L146)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_append_core"></a>
### `ResultSpool._append_core`

预算先于编码，成功登记后再按有限行数落盘。

```python
ResultSpool._append_core(row) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|DirectMessageCalculationRow|是|无|位置或关键字。row为当前行|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原状态、预算、编码、写入或取消错误，失败清理规则保持。

本函数直接报告的具体错误：

- `ResultFormatError`：本次结果暂存未启用legacy表。
- `ResultFormatError`：结果sequence必须严格递增且不重复。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:158`](../../../src/chronaxis/results/spool.py#L158)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_run_path"></a>
### `ResultSpool._run_path`

以受控常量和计数生成run路径，不接受用户行中的路径。

```python
ResultSpool._run_path(table: str, level: int, index: int) -> Path
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。当前已经启用的结果表名称，用于区分各表的临时排序文件。|
|`level`|int|是|无|位置或关键字。归并层号，0为初始排序块，后续层合并前一层文件。|
|`index`|int|是|无|位置或关键字。该层临时文件的序号，从0开始。|

#### 返回说明

Path。

#### 异常说明

无；只生成路径，不创建文件。

返回类型：[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)。

源码：[`src/chronaxis/results/spool.py:211`](../../../src/chronaxis/results/spool.py#L211)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_write_bytes"></a>
### `ResultSpool._write_bytes`

配额预留后完整写bytes，短写继续，零写明确失败。

```python
ResultSpool._write_bytes(handle, payload: bytes) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|BinaryIO|是|无|位置或关键字。本次操作已经打开的二进制文件对象；在此句柄上读写字节，不传文件路径。关闭责任仍由创建句柄的对象承担。|
|`payload`|bytes|是|无|位置或关键字。payload为有限行。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

BudgetExceededError/OSError为配额、磁盘满或短写失败。

本函数直接报告的具体错误：

- `OSError`：结果暂存写入未推进。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:219`](../../../src/chronaxis/results/spool.py#L219)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_clear_buffer"></a>
### `ResultSpool._clear_buffer`

抵销所有缓冲申请并释放对象，不删除已写文件。

```python
ResultSpool._clear_buffer() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放/取消传播，真实未抵销费用可由close重试。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:239`](../../../src/chronaxis/results/spool.py#L239)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_flush"></a>
### `ResultSpool._flush`

将有限缓冲排序并按表依次写run，异常也释放RAM。

```python
ResultSpool._flush() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

文件或预算错误原样传播。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:248`](../../../src/chronaxis/results/spool.py#L248)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_read_entry"></a>
### `ResultSpool._read_entry`

有界读取一行，按当前格式重建稳定键。

```python
ResultSpool._read_entry(handle, maximum=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|BinaryIO|是|无|位置或关键字。本次操作已经打开的二进制文件对象；在此句柄上读写字节，不传文件路径。关闭责任仍由创建句柄的对象承担。|
|`maximum`|int &#124; None|否|None|位置或关键字。本次读取允许的最大行字节数。传None时采用本暂存的max_row_bytes，不表示无限制。实际行还必须不超过max_row_bytes，并以完整换行结束。|

#### 返回说明

(排序键, 原bytes)，EOF返回None。

#### 异常说明

ResultFormatError/IO错误为损坏或超大行。

本函数直接报告的具体错误：

- `ResultFormatError`：暂存行超限或缺少完整换行。
- `ResultFormatError`：内部排序索引比结果行多，不能确认完整EOF。

源码：[`src/chronaxis/results/spool.py:282`](../../../src/chronaxis/results/spool.py#L282)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_merge"></a>
### `ResultSpool._merge`

用双路预算，将真实FD关闭与恢复交给共用归并owner。

```python
ResultSpool._merge(left: Path, right: Path | None, destination: Path, *, table=None) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。已排序的左侧临时结果文件，逐行读取。|
|`right`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|是|无|位置或关键字。已排序的右侧临时文件；None表示只有左侧输入，按单路输出处理。|
|`destination`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。合并后写入的新排序文件，不覆盖输入文件。|
|`table`|str &#124; None|否|None|仅关键字。结果表名称，具体可用名称见[结果文件](../results.md)；None兼容旧的双路归并调用。内部传递时须与当前行所属表一致。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原格式、预算、IO或取消；持续关闭失败保实际owner供重试。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:302`](../../../src/chronaxis/results/spool.py#L302)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-seal"></a>
### `ResultSpool.seal`

落盘并完成有限外部排序，成功后标analysis_complete。

```python
ResultSpool.seal() -> None
```

参数：无显式参数。


#### 参数说明

无；调用侧应已完成结果生成并交付最终行。

#### 返回说明

None，files保存本次固定表的最终排序路径。

#### 异常说明

失败标failed并关闭资源。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:311`](../../../src/chronaxis/results/spool.py#L311)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_seal_table"></a>
### `ResultSpool._seal_table`

完成一个有后续消费者的最终表，其他表仍可追加，不另复制中间阶段。

```python
ResultSpool._seal_table(table)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。将要封存的已登记结果表名称；只封存该表当前已写内容。|

#### 返回说明

最终有序路径；重复调用复用同一文件。

#### 异常说明

未启用表/写入/排序失败；调用方按原运行资源树清理。

源码：[`src/chronaxis/results/spool.py:327`](../../../src/chronaxis/results/spool.py#L327)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-_fail"></a>
### `ResultSpool._fail`

保存明确失败状态，诊断写失败不能掩盖原异常。

```python
ResultSpool._fail(exc: BaseException) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。exc为原失败。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无正常新增异常。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:355`](../../../src/chronaxis/results/spool.py#L355)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ResultSpool-close"></a>
### `ResultSpool.close`

取消未完成构建，或释放封口对象的固定RAM；重复关闭安全。

```python
ResultSpool.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放/取消传播，未释放资源额度保留，重复关闭可重试。

返回类型：None。

源码：[`src/chronaxis/results/spool.py:396`](../../../src/chronaxis/results/spool.py#L396)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
