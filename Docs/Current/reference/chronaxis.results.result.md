# `chronaxis.results.result`

管理一次已完成的分析结果。游标逐行读取平坦摘要，write向新目录发布；close关闭读取资源，默认清理本次程序为本次运行创建的临时数据，原输入与已发布结果保留。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[ArtifactExportStore](chronaxis.results.artifact_exports.md#api-ArtifactExportStore)、[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[ContributionsUnavailableError](chronaxis.results.errors.md#api-ContributionsUnavailableError)、[OutputManifest](chronaxis.results.manifest.md#api-OutputManifest)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[ResultSpool](chronaxis.results.spool.md#api-ResultSpool)、[RunMetadata](chronaxis.results.manifest.md#api-RunMetadata)、[SummaryAggregationRow](chronaxis.results.aggregation_row.md#api-SummaryAggregationRow)、[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow)、[SummaryContributionRow](chronaxis.results.summary.md#api-SummaryContributionRow)、[SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow)、[SummaryInputRow](chronaxis.results.summary.md#api-SummaryInputRow)、[SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow)、[SummarySelectionRow](chronaxis.results.summary.md#api-SummarySelectionRow)、[SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow)

## 对象导航

|对象|用途|
|---|---|
|[`_json`](#api-_json)|生成标准紧凑JSON文本，拒绝非有限普通数字。|
|[`_row_fields`](#api-_row_fields)|将当前平坦摘要转换为CSV列；不添加旧row_json或嵌套包装。|
|[`_DigestOutput`](#api-_DigestOutput)|借用本次已打开的输出流，同一次写入计算请求的摘要，不拥有关闭责任。|
|[`_DigestOutput.__init__`](#api-_DigestOutput-__init__)|建立固定状态。|
|[`_DigestOutput.write`](#api-_DigestOutput-write)|完整写出有限payload后更新摘要。|
|[`_DigestOutput.info`](#api-_DigestOutput-info)|返回已关闭文件的有限事实。|
|[`_RowIterator`](#api-_RowIterator)|独立文件位置的有限行迭代器，实际读槽与文件关闭完成后才closed。|
|[`_RowIterator.__init__`](#api-_RowIterator-__init__)|先预留解码槽位，再打开只读暂存并登记活跃资源。|
|[`_RowIterator.__iter__`](#api-_RowIterator-__iter__)|保持当前读取位置，不重读输入。|
|[`_RowIterator.__next__`](#api-_RowIterator-__next__)|读取一条有限行，EOF或异常关闭资源。|
|[`_RowIterator.close`](#api-_RowIterator-close)|抵销槽位、取消登记并关闭句柄；重复调用安全。|
|[`AnalysisResult`](#api-AnalysisResult)|一次成功分析的结果对象。通常由AnalysisRunner.run返回；通过iter_*逐行读取，通过write发布，通过close或with释放资源。内部构造参数用于接管暂存，不建议业务调用者手工构造。|
|[`AnalysisResult.__init__`](#api-AnalysisResult-__init__)|接管已经结束写入的结果暂存，并记录analysis_complete，表示计算完成、结果可供读取。正式输出目录仍由write生成。|
|[`AnalysisResult._require_open`](#api-AnalysisResult-_require_open)|拒绝关闭后迭代/发布，不自动重新打开已关闭对象。|
|[`AnalysisResult._manifest`](#api-AnalysisResult-_manifest)|构造有界清单副本，分开分析状态与发布状态。|
|[`AnalysisResult.run_manifest`](#api-AnalysisResult-run_manifest)|返回当前状态快照，发布失败诊断路径另见manifest_path。|
|[`AnalysisResult._write_state`](#api-AnalysisResult-_write_state)|追加状态清单到暂存，每份保留且计入累计配额。|
|[`AnalysisResult.iter_events`](#api-AnalysisResult-iter_events)|创建独立事件流，不装入全量列表。|
|[`AnalysisResult.iter_sequences`](#api-AnalysisResult-iter_sequences)|逐行读取请求配对结果；未配置配对时返回可关闭空游标。|
|[`AnalysisResult.iter_segments`](#api-AnalysisResult-iter_segments)|创建独立片段流，保留全部父事件关联。|
|[`AnalysisResult.iter_calculations`](#api-AnalysisResult-iter_calculations)|逐行读取计算摘要。检查scope区分会话、事件或片段，同时读取value、unit、status、reason及quality；select样本通过iter_selections读取。|
|[`AnalysisResult.iter_contributions`](#api-AnalysisResult-iter_contributions)|逐行回查真实贡献与skip，原序号和新求值序号分别保留。|
|[`AnalysisResult.iter_aggregations`](#api-AnalysisResult-iter_aggregations)|在结果打开期间，逐组读取本次请求的统计值、群组身份及候选参与和排除计数。|
|[`AnalysisResult.iter_selections`](#api-AnalysisResult-iter_selections)|读取明确请求的真实样本选择行。|
|[`AnalysisResult.iter_input_trace`](#api-AnalysisResult-iter_input_trace)|读取显式请求的所需输入追溯。|
|[`AnalysisResult.contributions_available`](#api-AnalysisResult-contributions_available)|说明本结果是否允许查询逐消息贡献，不将未生成和零行混为一谈。|
|[`AnalysisResult._write_table`](#api-AnalysisResult-_write_table)|逐行生成单表和质量记录，异常或EOF关闭读取句柄。|
|[`AnalysisResult._file_info`](#api-AnalysisResult-_file_info)|以固定读取块计算新输出哈希，不保留全文件内容。|
|[`AnalysisResult._install_directory`](#api-AnalysisResult-_install_directory)|在Windows同文件系统安装单个文件或目录，短暂占用时有限等待且拒绝覆盖。|
|[`AnalysisResult.write`](#api-AnalysisResult-write)|把暂存结果写入可复用目录，本次表和清单使用统一时间后缀。关闭文件后发布，完成清单最后出现；已有文件不覆盖。|
|[`AnalysisResult.close`](#api-AnalysisResult-close)|关闭游标并释放资源；默认清理本次程序为本次运行创建的临时数据，retain_work为true时保留现场。原始输入及正式输出保留。|
|[`AnalysisResult.__enter__`](#api-AnalysisResult-__enter__)|进入结果上下文，不再次执行输入读取。|
|[`AnalysisResult.__exit__`](#api-AnalysisResult-__exit__)|退出上下文时释放资源，保留业务原异常。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from contextlib import nullcontext
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from .codec import decode_row
from .errors import AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError, ContributionsUnavailableError
from .manifest import RunMetadata, OutputManifest
from .artifact_exports import ArtifactExportStore
from .rows import ResultRow, row_table
from .summary import SummaryCalculationRow, SummaryEventRow, SummarySequenceRow, SummarySegmentRow, SummaryContributionRow, SummarySelectionRow, SummaryInputRow, SummaryAggregationRow, summary_fields, SUMMARY_MODELS, SUMMARY_COLUMNS
from .owned_directory import directory_identity, remove_owned_directory
from .spool import ResultSpool, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
```

</details>

<a id="api-_json"></a>
## `_json`

生成标准紧凑JSON文本，拒绝非有限普通数字。

```python
_json(value) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON值 &#124; 冻结JSON值|是|无|位置或关键字。结果中的元数据结构，转换成可由标准JSON编码器输出的dict、list及原生标量。|

### 返回说明

str。

### 异常说明

ValueError为非法数值。

返回类型：str。

源码：[`src/chronaxis/results/result.py:38`](../../../src/chronaxis/results/result.py#L38)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_row_fields"></a>
## `_row_fields`

将当前平坦摘要转换为CSV列；不添加旧row_json或嵌套包装。

```python
_row_fields(row) -> dict
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|当前Summary摘要行|是|无|位置或关键字。已校验的平坦事件、片段、配对、计算或明细行；其真实字段直接对应CSV列。|

### 返回说明

独立字段字典。

### 异常说明

未支持模型或非有限值错误。

返回类型：dict。

源码：[`src/chronaxis/results/result.py:50`](../../../src/chronaxis/results/result.py#L50)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_DigestOutput"></a>
## `_DigestOutput`

借用本次已打开的输出流，同一次写入计算请求的摘要，不拥有关闭责任。

```python
_DigestOutput(stream)
```


源码：[`src/chronaxis/results/result.py:65`](../../../src/chronaxis/results/result.py#L65)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_DigestOutput-__init__"></a>
### `_DigestOutput.__init__`

建立固定状态。

```python
_DigestOutput.__init__(stream)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`stream`|文本或二进制输出流|是|无|位置或关键字。借用本次已打开的输出流，支持write；关闭责任仍由外层with持有。|

#### 返回说明

owner。

#### 异常说明

哈希构造错。

源码：[`src/chronaxis/results/result.py:67`](../../../src/chronaxis/results/result.py#L67)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_DigestOutput-write"></a>
### `_DigestOutput.write`

完整写出有限payload后更新摘要。

```python
_DigestOutput.write(payload)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|str &#124; bytes|是|无|位置或关键字。待写出的有限文本或字节块；只有完整写入后才更新字节数和摘要。|

#### 返回说明

原长度。

#### 异常说明

短写/IO。

源码：[`src/chronaxis/results/result.py:71`](../../../src/chronaxis/results/result.py#L71)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_DigestOutput-info"></a>
### `_DigestOutput.info`

返回已关闭文件的有限事实。

```python
_DigestOutput.info(name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。信号在当前计划中的简单别名，用于查定义和表达式依赖。|

#### 返回说明

dict。

#### 异常说明

无。

源码：[`src/chronaxis/results/result.py:79`](../../../src/chronaxis/results/result.py#L79)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_RowIterator"></a>
## `_RowIterator`

独立文件位置的有限行迭代器，实际读槽与文件关闭完成后才closed。

_reader_cost为实际已付槽位，_held_cost仅含本迭代器费用。关闭中的迭代器仍在
owner登记中，成功关handle后再抵销费用、解除登记；失败可由本对象或父close重试。
handle及内部发布模式的_index_handle保留真实文件，所有实际FD关闭后才抵销读槽。

```python
_RowIterator(owner, table: str)
```


源码：[`src/chronaxis/results/result.py:84`](../../../src/chronaxis/results/result.py#L84)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_RowIterator-__init__"></a>
### `_RowIterator.__init__`

先预留解码槽位，再打开只读暂存并登记活跃资源。

```python
_RowIterator.__init__(owner, table: str)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[AnalysisResult](chronaxis.results.result.md#api-AnalysisResult)|是|无|位置或关键字。当前分析结果对象，提供指定表的暂存文件和读取资源。|
|`table`|str|是|无|位置或关键字。要读取的结果表名称：events为事件，segments为窗口片段，calculations为指标；启用对应结果时还包括message_calculations（逐消息汇总）、legacy_contributions（逐次贡献）和sequences（请求响应配对）。只能读取本结果实际建立的表，不能传任意文件路径。|

#### 返回说明

公共带有明确类型的行迭代器，内部发布模式返回已核完整原行对应的有限质量字段。

#### 异常说明

预算/IO/取消原样传播；持续清理失败附row_iterator_cleanup_owner，父登记仍可达。

本函数直接报告的具体错误：

- `ValueError`：内部认证发布仅接受两类legacy表。
- `ValueError`：未注册结果表。

源码：[`src/chronaxis/results/result.py:92`](../../../src/chronaxis/results/result.py#L92)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_RowIterator-__iter__"></a>
### `_RowIterator.__iter__`

保持当前读取位置，不重读输入。

```python
_RowIterator.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/results/result.py:122`](../../../src/chronaxis/results/result.py#L122)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_RowIterator-__next__"></a>
### `_RowIterator.__next__`

读取一条有限行，EOF或异常关闭资源。

```python
_RowIterator.__next__() -> ResultRow | dict
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

公共带有明确类型的行或内部认证发布的质量字段。

#### 异常说明

StopIteration/关闭/格式/IO错误。

本函数直接报告的具体错误：

- `ResultClosedError`：结果读取器正在清理。
- `ResultFormatError`：结果行超限或未完整结束。
- `ResultFormatError`：结果暂存表与行类型不一致。
- `ResultFormatError`：内部认证发布排序键回退或重复。

返回类型：ResultRow &#124; dict。

源码：[`src/chronaxis/results/result.py:129`](../../../src/chronaxis/results/result.py#L129)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_RowIterator-close"></a>
### `_RowIterator.close`

抵销槽位、取消登记并关闭句柄；重复调用安全。

```python
_RowIterator.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原文件关闭/预算取消传播；失败句柄与未付清费用留待重试。

返回类型：None。

源码：[`src/chronaxis/results/result.py:169`](../../../src/chronaxis/results/result.py#L169)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult"></a>
## `AnalysisResult`

一次成功分析的结果对象。通常由AnalysisRunner.run返回；通过iter_*逐行读取，通过write发布，通过close或with释放资源。内部构造参数用于接管暂存，不建议业务调用者手工构造。

```python
AnalysisResult(spool: chronaxis.results.spool.ResultSpool, metadata: chronaxis.results.manifest.RunMetadata, table_format: str = 'csv', *, artifact_exports=None, owned_work=None)
```


源码：[`src/chronaxis/results/result.py:194`](../../../src/chronaxis/results/result.py#L194)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-__init__"></a>
### `AnalysisResult.__init__`

接管已经结束写入的结果暂存，并记录analysis_complete，表示计算完成、结果可供读取。正式输出目录仍由write生成。

```python
AnalysisResult.__init__(spool: ResultSpool, metadata: RunMetadata, table_format: str='csv', *, artifact_exports=None, owned_work=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spool`|[ResultSpool](chronaxis.results.spool.md#api-ResultSpool)|是|无|位置或关键字。接管内部执行流程已经写完并排序的ResultSpool。普通调用使用AnalysisRunner.run(...)取得AnalysisResult，不需要手工创建spool；接管后由结果对象负责释放。|
|`metadata`|[RunMetadata](chronaxis.results.manifest.md#api-RunMetadata)|是|无|位置或关键字。此次运行的配置、实际输入、计算方式及观测信息；发布时写入运行清单。|
|`table_format`|str|否|'csv'|位置或关键字。"csv"保留机器字段的CSV交换表，"jsonl"每行写一个完整JSON对象，"readable_csv"生成中文可读表格。低层构造器默认csv；普通配置与AnalysisRunner默认readable_csv。|
|`artifact_exports`|[ArtifactExportStore](chronaxis.results.artifact_exports.md#api-ArtifactExportStore) &#124; None|否|None|仅关键字。可选的信号表和报文导出文件仓，成功接管后由本结果负责关闭。|
|`owned_work`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), tuple] &#124; None|否|None|仅关键字。本次私有根路径和创建时目录身份；须是spool直接父目录，None仅接管spool目录。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

传入模型/表格式错误时拒绝构造；预算、暂存或内部清单写入失败可抛AnalysisError并保留cause。构造失败且仍有资源待关时，异常analysis_result_cleanup_owner提供close重试入口。一般调用者应取得AnalysisRunner.run返回的对象，避免自行接管spool。

源码：[`src/chronaxis/results/result.py:204`](../../../src/chronaxis/results/result.py#L204)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-_require_open"></a>
### `AnalysisResult._require_open`

拒绝关闭后迭代/发布，不自动重新打开已关闭对象。

```python
AnalysisResult._require_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：AnalysisResult已关闭或正在清理。

返回类型：None。

源码：[`src/chronaxis/results/result.py:270`](../../../src/chronaxis/results/result.py#L270)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-_manifest"></a>
### `AnalysisResult._manifest`

构造有界清单副本，分开分析状态与发布状态。

```python
AnalysisResult._manifest(status: str, outputs=(), coverage=None) -> dict
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`status`|str|是|无|位置或关键字。本次清单要记录的状态。当前调用流程使用analysis_complete（分析完成，结果可读）、completed（正式输出完成）、output_failed（写出失败）、cancelled（写出被取消）。本辅助函数原样保存传入状态，不会因为填写completed就执行发布。|
|`outputs`|tuple &#124; list|否|()|位置或关键字。已经发布的各输出文件记录，包含文件名、行数、字节数和摘要，写入manifest清单。|
|`coverage`|dict[str, int] &#124; None|否|None|位置或关键字。按覆盖状态累计的结果数量，用于清单中展示完整、部分或无结果等数量。 None表示本次尚未提供逐状态计数。|

#### 返回说明

dict；元数据转换成本已申请。

#### 异常说明

无预期异常。

返回类型：dict。

源码：[`src/chronaxis/results/result.py:278`](../../../src/chronaxis/results/result.py#L278)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-run_manifest"></a>
### `AnalysisResult.run_manifest`

返回当前状态快照，发布失败诊断路径另见manifest_path。

```python
AnalysisResult.run_manifest: dict
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

独立小型dict。

#### 异常说明

关闭后仍可查看诊断，不读文件。

返回类型：dict。

源码：[`src/chronaxis/results/result.py:326`](../../../src/chronaxis/results/result.py#L326)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-_write_state"></a>
### `AnalysisResult._write_state`

追加状态清单到暂存，每份保留且计入累计配额。

```python
AnalysisResult._write_state(path: Path, status: str) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次发布的新清单路径，不覆盖其他任务的清单。|
|`status`|str|是|无|位置或关键字。实际发布状态，写入清单以表示仍在写入、完成或失败；不能提前写成成功。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

配额/IO失败；不能生成虚假completed。

本函数直接报告的具体错误：

- `BudgetExceededError`：运行清单超过有限元数据大小。

返回类型：None。

源码：[`src/chronaxis/results/result.py:333`](../../../src/chronaxis/results/result.py#L333)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-iter_events"></a>
### `AnalysisResult.iter_events`

创建独立事件流，不装入全量列表。

```python
AnalysisResult.iter_events() -> Iterator[SummaryEventRow]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

可关闭迭代器，逐行产生SummaryEventRow；使用try/finally关闭游标；外层AnalysisResult可用with管理，游标本身不支持with。

#### 异常说明

ResultClosedError：结果已关闭或正在关闭，不能创建或继续读取游标。BudgetExceededError：无法为游标保留预算。OSError：创建或迭代期间读取暂存文件失败。ResultFormatError：迭代时发现行格式、类型或长度不合法。先关闭游标；不要将读取失败当成空结果。

返回类型：Iterator[[SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow)]。

源码：[`src/chronaxis/results/result.py:351`](../../../src/chronaxis/results/result.py#L351)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-iter_sequences"></a>
### `AnalysisResult.iter_sequences`

逐行读取请求配对结果；未配置配对时返回可关闭空游标。

```python
AnalysisResult.iter_sequences() -> Iterator[SummarySequenceRow]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

可关闭迭代器，逐行产生SummarySequenceRow；使用try/finally关闭游标；外层AnalysisResult可用with管理，游标本身不支持with。

#### 异常说明

ResultClosedError：结果已关闭或正在关闭，不能创建或继续读取游标。BudgetExceededError：无法为游标保留预算。OSError：创建或迭代期间读取暂存文件失败。ResultFormatError：迭代时发现行格式、类型或长度不合法。先关闭游标；不要将读取失败当成空结果。

返回类型：Iterator[[SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow)]。

源码：[`src/chronaxis/results/result.py:359`](../../../src/chronaxis/results/result.py#L359)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-iter_segments"></a>
### `AnalysisResult.iter_segments`

创建独立片段流，保留全部父事件关联。

```python
AnalysisResult.iter_segments() -> Iterator[SummarySegmentRow]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

可关闭迭代器，逐行产生SummarySegmentRow；使用try/finally关闭游标；外层AnalysisResult可用with管理，游标本身不支持with。

#### 异常说明

ResultClosedError：结果已关闭或正在关闭，不能创建或继续读取游标。BudgetExceededError：无法为游标保留预算。OSError：创建或迭代期间读取暂存文件失败。ResultFormatError：迭代时发现行格式、类型或长度不合法。先关闭游标；不要将读取失败当成空结果。

返回类型：Iterator[[SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow)]。

源码：[`src/chronaxis/results/result.py:367`](../../../src/chronaxis/results/result.py#L367)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-iter_calculations"></a>
### `AnalysisResult.iter_calculations`

逐行读取计算摘要。检查scope区分会话、事件或片段，同时读取value、unit、status、reason及quality；select样本通过iter_selections读取。

```python
AnalysisResult.iter_calculations() -> Iterator[SummaryCalculationRow]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

可关闭迭代器，逐行产生SummaryCalculationRow；相关时间计算设置minimum_coverage大于0时产生带coverage_status的SummaryCoverageCalculationRow。用try/finally关闭游标，不能对游标使用with。

#### 异常说明

ResultClosedError：结果已关闭或正在关闭，不能创建或继续读取游标。BudgetExceededError：无法为游标保留预算。OSError：创建或迭代期间读取暂存文件失败。ResultFormatError：迭代时发现行格式、类型或长度不合法。先关闭游标；不要将读取失败当成空结果。

返回类型：Iterator[[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow)]。

源码：[`src/chronaxis/results/result.py:375`](../../../src/chronaxis/results/result.py#L375)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-iter_contributions"></a>
### `AnalysisResult.iter_contributions`

逐行回查真实贡献与skip，原序号和新求值序号分别保留。

```python
AnalysisResult.iter_contributions() -> Iterator[SummaryContributionRow]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

独立有预算游标；逐行返回SummaryContributionRow。

#### 异常说明

ContributionsUnavailableError：outputs.contributions没有请求full，需要修改计划重新运行才有明细。ResultClosedError：结果已关。读取暂存时发生预算、格式或I/O错误会保留异常链；不是输入解码器重新执行。

返回类型：Iterator[[SummaryContributionRow](chronaxis.results.summary.md#api-SummaryContributionRow)]。

源码：[`src/chronaxis/results/result.py:384`](../../../src/chronaxis/results/result.py#L384)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-iter_aggregations"></a>
### `AnalysisResult.iter_aggregations`

在结果打开期间，逐组读取本次请求的统计值、群组身份及候选参与和排除计数。

```python
AnalysisResult.iter_aggregations() -> Iterator['SummaryAggregationRow']
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

可关闭的独立迭代器，逐行给出 SummaryAggregationRow。未配置聚合时为空。读取中止可关闭迭代器或所属结果。

#### 异常说明

ResultClosedError 表示所属结果已关闭或正在清理。预算不足、暂存读取失败及行格式损坏可分别引发 BudgetExceededError、OSError 和 ResultFormatError。

返回类型：Iterator['[SummaryAggregationRow](chronaxis.results.aggregation_row.md#api-SummaryAggregationRow)']。

源码：[`src/chronaxis/results/result.py:396`](../../../src/chronaxis/results/result.py#L396)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-iter_selections"></a>
### `AnalysisResult.iter_selections`

读取明确请求的真实样本选择行。

```python
AnalysisResult.iter_selections() -> Iterator[SummarySelectionRow]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

有预算游标，未请求为空。

#### 异常说明

ResultClosedError：结果已关闭或正在关闭，不能创建或继续读取游标。BudgetExceededError：无法为游标保留预算。OSError：创建或迭代期间读取暂存文件失败。ResultFormatError：迭代时发现行格式、类型或长度不合法。先关闭游标；不要将读取失败当成空结果。

返回类型：Iterator[[SummarySelectionRow](chronaxis.results.summary.md#api-SummarySelectionRow)]。

源码：[`src/chronaxis/results/result.py:400`](../../../src/chronaxis/results/result.py#L400)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-iter_input_trace"></a>
### `AnalysisResult.iter_input_trace`

读取显式请求的所需输入追溯。

```python
AnalysisResult.iter_input_trace() -> Iterator[SummaryInputRow]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

逐行产生SummaryInputRow的可关闭游标。

#### 异常说明

ResultClosedError：结果已关闭。AnalysisError：本次未生成输入追溯，需配置diagnostics.trace后重新运行。迭代期间可能传播ResultFormatError、BudgetExceededError和OSError。

返回类型：Iterator[[SummaryInputRow](chronaxis.results.summary.md#api-SummaryInputRow)]。

源码：[`src/chronaxis/results/result.py:405`](../../../src/chronaxis/results/result.py#L405)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-contributions_available"></a>
### `AnalysisResult.contributions_available`

说明本结果是否允许查询逐消息贡献，不将未生成和零行混为一谈。

```python
AnalysisResult.contributions_available: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool；默认未配置逐消息指标仍允许原空游标。

#### 异常说明

无；关闭后可查看这项固定运行事实，但不能重新创建游标。

返回类型：bool。

源码：[`src/chronaxis/results/result.py:415`](../../../src/chronaxis/results/result.py#L415)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-_write_table"></a>
### `AnalysisResult._write_table`

逐行生成单表和质量记录，异常或EOF关闭读取句柄。

```python
AnalysisResult._write_table(table: str, destination: Path, quality_handle, coverage: dict)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。本次要发布的已启用结果表，完整表名见[结果文件](../results.md)。|
|`destination`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。该结果表的新文件路径，按JSONL逐行写入。|
|`quality_handle`|TextIO|是|无|位置或关键字。已打开的质量JSONL输出文件，写入当前结果行关联的质量记录。|
|`coverage`|dict|是|无|位置或关键字。按表名和状态累计行数的发布字典，函数原地更新；不是可被补齐的信号覆盖。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算/编码/写入错误传播，输出with保证关闭。

本函数直接报告的具体错误：

- `ResultFormatError`：输出表行数与分析暂存不一致。

源码：[`src/chronaxis/results/result.py:423`](../../../src/chronaxis/results/result.py#L423)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-_file_info"></a>
### `AnalysisResult._file_info`

以固定读取块计算新输出哈希，不保留全文件内容。

```python
AnalysisResult._file_info(path: Path) -> dict
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。path为已关闭输出文件。|

#### 返回说明

名称/bytes/SHA256。

#### 异常说明

IO错误；调用侧已预留发布临时槽位。

返回类型：dict。

源码：[`src/chronaxis/results/result.py:488`](../../../src/chronaxis/results/result.py#L488)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-_install_directory"></a>
### `AnalysisResult._install_directory`

在Windows同文件系统安装单个文件或目录，短暂占用时有限等待且拒绝覆盖。

```python
AnalysisResult._install_directory(temporary: Path, destination: Path) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`temporary`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。已完成写入和检查的临时目录，与目标位于同一父目录。|
|`destination`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。尚不存在的最终发布目录，安装成功后成为用户可读取的结果目录。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

AnalysisError为未支持平台；FileExistsError/IO错误为安装失败。

本函数直接报告的具体错误：

- `AnalysisError`：原子目录安装目前只验收Windows；其他平台需不覆盖安装实现。

#### 副作用说明

只重试当前路径安装，不重新读取、分析或生成任何输出文件。

#### 边界说明

仅原rename的Win5/32最多尝试六次，五次等待合计0.77秒；
系统调用本身不受该等待时长约束。其他错误立即传播，最终保留原异常与源目录。

返回类型：None。

源码：[`src/chronaxis/results/result.py:502`](../../../src/chronaxis/results/result.py#L502)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-write"></a>
### `AnalysisResult.write`

把暂存结果写入可复用目录，本次表和清单使用统一时间后缀。关闭文件后发布，完成清单最后出现；已有文件不覆盖。

```python
AnalysisResult.write(output_dir: str | Path) -> OutputManifest
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`output_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。可重复使用的结果目录，传str或Path，例如Path("results")。本次文件统一增加时间后缀，不覆盖已有文件。返回OutputManifest包含实际manifest_path；结果仍需关闭。|

#### 返回说明

安装成功后的OutputManifest。

#### 异常说明

ResultClosedError：结果已关闭或正在关闭。AnalysisError：输出不是可用目录、位于将清理的自有工作目录内、平台不支持安全发布、预算/格式/文件写入失败；原错误通过__cause__保留。修正环境后，可向同一或其他目录重试，不会重读输入。

#### 副作用说明

发布带时间后缀的结果文件，完成清单最后发布。失败只清理本次文件；retain_work控制临时现场保留。断电或强制结束遗留的无清单文件不表示完成。

返回类型：[OutputManifest](chronaxis.results.manifest.md#api-OutputManifest)。

源码：[`src/chronaxis/results/result.py:531`](../../../src/chronaxis/results/result.py#L531)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-close"></a>
### `AnalysisResult.close`

关闭游标并释放资源；默认清理本次程序为本次运行创建的临时数据，retain_work为true时保留现场。原始输入及正式输出保留。

```python
AnalysisResult.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。可重复调用；失败后仍可重试未完成的清理。

#### 异常说明

先尝试关闭所有已取得的资源；文件句柄、暂存清理或预算释放失败时抛出首先发生的错误，后续错误作为补充诊断。确认占用已解除后再次调用close；close可重复，不能仅捕获异常后丢弃该结果对象。

返回类型：None。

源码：[`src/chronaxis/results/result.py:693`](../../../src/chronaxis/results/result.py#L693)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-__enter__"></a>
### `AnalysisResult.__enter__`

进入结果上下文，不再次执行输入读取。

```python
AnalysisResult.__enter__() -> 'AnalysisResult'
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

ResultClosedError为已关闭。

返回类型：'[AnalysisResult](chronaxis.results.result.md#api-AnalysisResult)'。

源码：[`src/chronaxis/results/result.py:744`](../../../src/chronaxis/results/result.py#L744)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisResult-__exit__"></a>
### `AnalysisResult.__exit__`

退出上下文时释放资源，保留业务原异常。

```python
AnalysisResult.__exit__(exc_type, exc_value, traceback)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc_type`|type[BaseException] &#124; None|是|无|位置或关键字。with代码块抛出的异常类型；正常离开时为None，由Python传入。|
|`exc_value`|BaseException &#124; None|是|无|位置或关键字。with代码块抛出的异常对象；正常离开时为None，由Python传入。|
|`traceback`|TracebackType &#124; None|是|无|位置或关键字。异常发生时的调用栈；正常离开时为None，由Python传入，供异常继续传播。|

#### 返回说明

False，异常会继续传给调用者。

#### 异常说明

正常离开with时close失败会传播关闭错误；with内已有业务异常时保留该业务异常，关闭问题附加到诊断信息，避免掩盖真正失败原因。

源码：[`src/chronaxis/results/result.py:752`](../../../src/chronaxis/results/result.py#L752)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
