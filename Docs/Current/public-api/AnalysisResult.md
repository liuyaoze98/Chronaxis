# chronaxis.AnalysisResult

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.results.result.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [AnalysisResult](#api-AnalysisResult)
- [AnalysisResult.__init__](#api-AnalysisResult-__init__)
- [AnalysisResult.run_manifest](#api-AnalysisResult-run_manifest)
- [AnalysisResult.iter_events](#api-AnalysisResult-iter_events)
- [AnalysisResult.iter_sequences](#api-AnalysisResult-iter_sequences)
- [AnalysisResult.iter_segments](#api-AnalysisResult-iter_segments)
- [AnalysisResult.iter_calculations](#api-AnalysisResult-iter_calculations)
- [AnalysisResult.iter_contributions](#api-AnalysisResult-iter_contributions)
- [AnalysisResult.iter_selections](#api-AnalysisResult-iter_selections)
- [AnalysisResult.iter_input_trace](#api-AnalysisResult-iter_input_trace)
- [AnalysisResult.contributions_available](#api-AnalysisResult-contributions_available)
- [AnalysisResult.write](#api-AnalysisResult-write)
- [AnalysisResult.close](#api-AnalysisResult-close)
- [AnalysisResult.__enter__](#api-AnalysisResult-__enter__)
- [AnalysisResult.__exit__](#api-AnalysisResult-__exit__)

<a id="api-AnalysisResult"></a>
## `AnalysisResult`

一次成功分析的结果对象。通常由AnalysisRunner.run返回；通过iter_*逐行读取，通过write发布，通过close或with释放资源。内部构造参数用于接管暂存，不建议业务调用者手工构造。

```python
AnalysisResult(spool: chronaxis.results.spool.ResultSpool, metadata: chronaxis.results.manifest.RunMetadata, table_format: str = 'csv', *, artifact_exports=None, owned_work=None)
```


源码：[`src/chronaxis/results/result.py:193`](../../../src/chronaxis/results/result.py#L193)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-AnalysisResult-__init__"></a>
### `AnalysisResult.__init__`

接管已经结束写入的结果暂存，并记录analysis_complete，表示计算完成、结果可供读取。正式输出目录仍由write生成。

```python
AnalysisResult.__init__(spool: ResultSpool, metadata: RunMetadata, table_format: str='csv', *, artifact_exports=None, owned_work=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spool`|[ResultSpool](../reference/chronaxis.results.spool.md#api-ResultSpool)|是|无|位置或关键字。接管内部执行流程已经写完并排序的ResultSpool。普通调用使用AnalysisRunner.run(...)取得AnalysisResult，不需要手工创建spool；接管后由结果对象负责释放。|
|`metadata`|[RunMetadata](RunMetadata.md#api-RunMetadata)|是|无|位置或关键字。此次运行的配置、实际输入、计算方式及观测信息；发布时写入运行清单。|
|`table_format`|str|否|'csv'|位置或关键字。"csv"保留机器字段的CSV交换表，"jsonl"每行写一个完整JSON对象，"readable_csv"生成中文可读表格。低层构造器默认csv；普通配置与AnalysisRunner默认readable_csv。|
|`artifact_exports`|[ArtifactExportStore](../reference/chronaxis.results.artifact_exports.md#api-ArtifactExportStore) &#124; None|否|None|仅关键字。可选的信号表和报文导出文件仓，成功接管后由本结果负责关闭。|
|`owned_work`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), tuple] &#124; None|否|None|仅关键字。本次私有根路径和创建时目录身份；须是spool直接父目录，None仅接管spool目录。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

传入模型/表格式错误时拒绝构造；预算、暂存或内部清单写入失败可抛AnalysisError并保留cause。构造失败且仍有资源待关时，异常analysis_result_cleanup_owner提供close重试入口。一般调用者应取得AnalysisRunner.run返回的对象，避免自行接管spool。

源码：[`src/chronaxis/results/result.py:203`](../../../src/chronaxis/results/result.py#L203)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

源码：[`src/chronaxis/results/result.py:325`](../../../src/chronaxis/results/result.py#L325)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

返回类型：Iterator[[SummaryEventRow](../reference/chronaxis.results.summary.md#api-SummaryEventRow)]。

源码：[`src/chronaxis/results/result.py:350`](../../../src/chronaxis/results/result.py#L350)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

返回类型：Iterator[[SummarySequenceRow](../reference/chronaxis.results.summary.md#api-SummarySequenceRow)]。

源码：[`src/chronaxis/results/result.py:358`](../../../src/chronaxis/results/result.py#L358)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

返回类型：Iterator[[SummarySegmentRow](../reference/chronaxis.results.summary.md#api-SummarySegmentRow)]。

源码：[`src/chronaxis/results/result.py:366`](../../../src/chronaxis/results/result.py#L366)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

返回类型：Iterator[[SummaryCalculationRow](../reference/chronaxis.results.summary.md#api-SummaryCalculationRow)]。

源码：[`src/chronaxis/results/result.py:374`](../../../src/chronaxis/results/result.py#L374)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

返回类型：Iterator[[SummaryContributionRow](../reference/chronaxis.results.summary.md#api-SummaryContributionRow)]。

源码：[`src/chronaxis/results/result.py:383`](../../../src/chronaxis/results/result.py#L383)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

返回类型：Iterator[[SummarySelectionRow](../reference/chronaxis.results.summary.md#api-SummarySelectionRow)]。

源码：[`src/chronaxis/results/result.py:395`](../../../src/chronaxis/results/result.py#L395)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

返回类型：Iterator[[SummaryInputRow](../reference/chronaxis.results.summary.md#api-SummaryInputRow)]。

源码：[`src/chronaxis/results/result.py:400`](../../../src/chronaxis/results/result.py#L400)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

源码：[`src/chronaxis/results/result.py:410`](../../../src/chronaxis/results/result.py#L410)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-AnalysisResult-write"></a>
### `AnalysisResult.write`

把暂存中的结果写到全新目录。所有文件完成后写入completed状态，再把临时目录重命名为正式目录；已有目标不会被覆盖。

```python
AnalysisResult.write(output_dir: str | Path) -> OutputManifest
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`output_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。指定新建的结果目录，传str或Path，例如Path("results/run_01")。按本次输出位置填写；目录已存在时拒绝覆盖。完成后返回OutputManifest，结果对象仍需关闭。|

#### 返回说明

安装成功后的OutputManifest。

#### 异常说明

ResultClosedError：结果已关闭或正在关闭。AnalysisError：目标已存在、目标位于将清理的自有工作目录内、平台不支持安全发布、预算/格式/文件写入失败；原错误通过__cause__保留。修正输出位置或环境后，可向另一新目录重试，不会重读输入。

#### 副作用说明

发布到全新输出目录，不覆盖既有目录。失败时按retain_work决定是否保留本次临时目录；诊断可从异常及run_manifest查看。

返回类型：[OutputManifest](OutputManifest.md#api-OutputManifest)。

源码：[`src/chronaxis/results/result.py:523`](../../../src/chronaxis/results/result.py#L523)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

源码：[`src/chronaxis/results/result.py:660`](../../../src/chronaxis/results/result.py#L660)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

返回类型：'[AnalysisResult](AnalysisResult.md#api-AnalysisResult)'。

源码：[`src/chronaxis/results/result.py:711`](../../../src/chronaxis/results/result.py#L711)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

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

源码：[`src/chronaxis/results/result.py:719`](../../../src/chronaxis/results/result.py#L719)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
