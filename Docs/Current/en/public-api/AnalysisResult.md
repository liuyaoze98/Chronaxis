# chronaxis.AnalysisResult

Import this object from `chronaxis`. This page lists direct public members and necessary construction/context protocols. See the [module reference](../../reference/chronaxis.results.result.md) for internal implementation (Chinese implementation reference).

Return to the [public API index](../api.md). Linked parameter types lead to their definitions. Check required fields, defaults, returns, and exceptions.

## Members

- [`AnalysisResult`](#api-AnalysisResult)
- [`AnalysisResult.__init__`](#api-AnalysisResult-__init__)
- [`AnalysisResult.run_manifest`](#api-AnalysisResult-run_manifest)
- [`AnalysisResult.iter_events`](#api-AnalysisResult-iter_events)
- [`AnalysisResult.iter_sequences`](#api-AnalysisResult-iter_sequences)
- [`AnalysisResult.iter_segments`](#api-AnalysisResult-iter_segments)
- [`AnalysisResult.iter_calculations`](#api-AnalysisResult-iter_calculations)
- [`AnalysisResult.iter_aggregations`](#api-AnalysisResult-iter_aggregations)
- [`AnalysisResult.iter_contributions`](#api-AnalysisResult-iter_contributions)
- [`AnalysisResult.iter_selections`](#api-AnalysisResult-iter_selections)
- [`AnalysisResult.iter_input_trace`](#api-AnalysisResult-iter_input_trace)
- [`AnalysisResult.contributions_available`](#api-AnalysisResult-contributions_available)
- [`AnalysisResult.write`](#api-AnalysisResult-write)
- [`AnalysisResult.close`](#api-AnalysisResult-close)
- [`AnalysisResult.__enter__`](#api-AnalysisResult-__enter__)
- [`AnalysisResult.__exit__`](#api-AnalysisResult-__exit__)

<a id="api-AnalysisResult"></a>
## `AnalysisResult`

Result of one successful analysis, normally returned by AnalysisRunner.run. Read rows through iter_*, publish through write, and release resources through close or with. Constructor arguments transfer internal staging ownership; ordinary application callers should not construct this object manually.

```python
AnalysisResult(spool: chronaxis.results.spool.ResultSpool, metadata: chronaxis.results.manifest.RunMetadata, table_format: str = 'csv', *, artifact_exports=None, owned_work=None)
```

<a id="api-AnalysisResult-__init__"></a>
### `AnalysisResult.__init__`

Takes ownership of finalized staging and records analysis_complete: computation is finished and results can be read. write separately publishes timestamped files in the final output directory.

```python
AnalysisResult.__init__(spool: ResultSpool, metadata: RunMetadata, table_format: str='csv', *, artifact_exports=None, owned_work=None)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`spool`|[ResultSpool](../../reference/chronaxis.results.spool.md#api-ResultSpool)|Yes|No default|Positional or keyword. Takes ownership of an internally finalized and sorted ResultSpool, then becomes responsible for releasing it. Ordinary callers obtain the result through AnalysisRunner.run(...) instead of constructing staging.|
|`metadata`|[RunMetadata](RunMetadata.md#api-RunMetadata)|Yes|No default|Positional or keyword. This run's configuration, actual input, calculation mode, and observations, written into the published manifest.|
|`table_format`|str|No|'csv'|Positional or keyword. "readable_csv" writes Chinese readable tables; "csv" preserves exchange CSV fields; "jsonl" writes complete JSON records per line. This low-level constructor defaults to csv; AnalysisRunner follows the plan default readable_csv.|
|`artifact_exports`|[ArtifactExportStore](../../reference/chronaxis.results.artifact_exports.md#api-ArtifactExportStore) &#124; None|No|None|Keyword-only. Optional store for signal-table and frame export files. The result owns closure after successful transfer.|
|`owned_work`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), tuple] &#124; None|No|None|Keyword-only. Private root path and creation-time directory identity; must be the spool's direct parent. None transfers only the spool directory.|

#### Returns

None; initializes the instance.

#### Raises

Invalid models/table formats are rejected. Budget, staging, or internal-manifest failures can raise AnalysisError with their cause. If construction fails with cleanup pending, the exception's analysis_result_cleanup_owner provides a close retry. Ordinary callers should use AnalysisRunner.run instead of transferring spool ownership themselves.

<a id="api-AnalysisResult-run_manifest"></a>
### `AnalysisResult.run_manifest`

Returns a snapshot of current state. See manifest_path for publication-failure diagnostics.

```python
AnalysisResult.run_manifest: dict
```

Decorators: `property`.

Read this as a property, without calling parentheses.


#### Parameter notes

None.

#### Returns

Small independent dict.

#### Raises

Diagnostics remain available after close; no files are read.

Return type: dict。

<a id="api-AnalysisResult-iter_events"></a>
### `AnalysisResult.iter_events`

Creates an independent event stream without materializing every row.

```python
AnalysisResult.iter_events() -> Iterator[SummaryEventRow]
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Closable iterator yielding SummaryEventRow. Close it in try/finally. The enclosing AnalysisResult supports with; the cursor itself does not.

#### Raises

ResultClosedError if the result is closed or closing, preventing cursor creation or continued reading. BudgetExceededError if a cursor budget cannot be reserved. OSError if staging reads fail at creation or iteration. ResultFormatError if a row format, type, or length is invalid. Close the cursor; do not interpret read failure as empty results.

Return type: Iterator[[SummaryEventRow](../../reference/chronaxis.results.summary.md#api-SummaryEventRow)]。

<a id="api-AnalysisResult-iter_sequences"></a>
### `AnalysisResult.iter_sequences`

Streams pairing rows; without configured pairing, returns an empty closable cursor.

```python
AnalysisResult.iter_sequences() -> Iterator[SummarySequenceRow]
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Closable iterator yielding SummarySequenceRow. Close it in try/finally. The enclosing AnalysisResult supports with; the cursor itself does not.

#### Raises

ResultClosedError if the result is closed or closing, preventing cursor creation or continued reading. BudgetExceededError if a cursor budget cannot be reserved. OSError if staging reads fail at creation or iteration. ResultFormatError if a row format, type, or length is invalid. Close the cursor; do not interpret read failure as empty results.

Return type: Iterator[[SummarySequenceRow](../../reference/chronaxis.results.summary.md#api-SummarySequenceRow)]。

<a id="api-AnalysisResult-iter_segments"></a>
### `AnalysisResult.iter_segments`

Creates an independent segment stream retaining all parent-event links.

```python
AnalysisResult.iter_segments() -> Iterator[SummarySegmentRow]
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Closable iterator yielding SummarySegmentRow. Close it in try/finally. The enclosing AnalysisResult supports with; the cursor itself does not.

#### Raises

ResultClosedError if the result is closed or closing, preventing cursor creation or continued reading. BudgetExceededError if a cursor budget cannot be reserved. OSError if staging reads fail at creation or iteration. ResultFormatError if a row format, type, or length is invalid. Close the cursor; do not interpret read failure as empty results.

Return type: Iterator[[SummarySegmentRow](../../reference/chronaxis.results.summary.md#api-SummarySegmentRow)]。

<a id="api-AnalysisResult-iter_calculations"></a>
### `AnalysisResult.iter_calculations`

Streams calculation summaries. Use scope to distinguish session, event, and segment, and read value, unit, status, reason, and quality together. Read select samples through iter_selections.

```python
AnalysisResult.iter_calculations() -> Iterator[SummaryCalculationRow]
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Closable iterator yielding SummaryCalculationRow. Applicable time calculations with minimum_coverage > 0 yield SummaryCoverageCalculationRow with coverage_status. Close the cursor in try/finally; the cursor does not support with.

#### Raises

ResultClosedError if the result is closed or closing, preventing cursor creation or continued reading. BudgetExceededError if a cursor budget cannot be reserved. OSError if staging reads fail at creation or iteration. ResultFormatError if a row format, type, or length is invalid. Close the cursor; do not interpret read failure as empty results.

Return type: Iterator[[SummaryCalculationRow](../../reference/chronaxis.results.summary.md#api-SummaryCalculationRow)]。

<a id="api-AnalysisResult-iter_aggregations"></a>
### `AnalysisResult.iter_aggregations`

Read the grouped results requested by this plan's root-level `aggregations` while the result is open. Each call reads the staged rows from the beginning.

```python
AnalysisResult.iter_aggregations() -> Iterator['SummaryAggregationRow']
```

#### Parameters

No explicit arguments.

#### Returns

A closable iterator over one `SummaryAggregationRow` per produced group. An analysis without aggregations yields no rows. `aggregation_id`, `source_kind` and `source_id` identify the request. Pair `group_keys` with `group_values` to identify the group. Read `value` and `unit` together with `status`, `reason`, `quality`, `discovery_complete` and the candidate, inclusion and exclusion counts. If iteration ends early, close the cursor or its owning result. [Python example](../api-usage.md) · [Population and field definitions](../results.md#v4-aggregations)

#### Raises

`ResultClosedError` if the result has closed or is closing, `BudgetExceededError` if the reader cannot reserve its budget, `ResultFormatError` for invalid staged rows, or `OSError` for a failed file read.

<a id="api-AnalysisResult-iter_contributions"></a>
### `AnalysisResult.iter_contributions`

Streams actual contributions and skipped evaluations, retaining original sequence and evaluation sequence separately.

```python
AnalysisResult.iter_contributions() -> Iterator[SummaryContributionRow]
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Independent budgeted cursor yielding SummaryContributionRow.

#### Raises

ContributionsUnavailableError if outputs.contributions did not request full; change the plan and rerun to obtain details. ResultClosedError if closed. Budget, format, or I/O failures during staged reading retain their exception chains. The input decoder is not rerun.

Return type: Iterator[[SummaryContributionRow](../../reference/chronaxis.results.summary.md#api-SummaryContributionRow)]。

<a id="api-AnalysisResult-iter_selections"></a>
### `AnalysisResult.iter_selections`

Reads explicitly requested actual sample-selection rows.

```python
AnalysisResult.iter_selections() -> Iterator[SummarySelectionRow]
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Budgeted cursor, empty when selection was not requested.

#### Raises

ResultClosedError if the result is closed or closing, preventing cursor creation or continued reading. BudgetExceededError if a cursor budget cannot be reserved. OSError if staging reads fail at creation or iteration. ResultFormatError if a row format, type, or length is invalid. Close the cursor; do not interpret read failure as empty results.

Return type: Iterator[[SummarySelectionRow](../../reference/chronaxis.results.summary.md#api-SummarySelectionRow)]。

<a id="api-AnalysisResult-iter_input_trace"></a>
### `AnalysisResult.iter_input_trace`

Reads explicitly requested traces of required inputs.

```python
AnalysisResult.iter_input_trace() -> Iterator[SummaryInputRow]
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Closable cursor yielding SummaryInputRow.

#### Raises

ResultClosedError if closed. AnalysisError if input trace was not generated; enable diagnostics.trace and rerun. Iteration may propagate ResultFormatError, BudgetExceededError, and OSError.

Return type: Iterator[[SummaryInputRow](../../reference/chronaxis.results.summary.md#api-SummaryInputRow)]。

<a id="api-AnalysisResult-contributions_available"></a>
### `AnalysisResult.contributions_available`

Indicates whether per-message contributions can be queried, distinguishing unavailable details from an available empty table.

```python
AnalysisResult.contributions_available: bool
```

Decorators: `property`.

Read this as a property, without calling parentheses.


#### Parameter notes

None.

#### Returns

bool. With no per-message metrics configured, the original empty-cursor behavior remains available by default.

#### Raises

None. This fixed run fact remains readable after close, but no new cursor can be created.

Return type: bool。

<a id="api-AnalysisResult-write"></a>
### `AnalysisResult.write`

Publishes staged results with a shared timestamp suffix in a reusable directory. Files are closed before publication and the completed manifest is published last. Existing files are preserved.

```python
AnalysisResult.write(output_dir: str | Path) -> OutputManifest
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`output_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|Yes|No default|Positional or keyword. Reusable result directory as str or Path, e.g. Path("results"). Files receive a common timestamp suffix. Returns OutputManifest on completion; the result still needs closing.|

#### Returns

OutputManifest after successful publication.

#### Raises

ResultClosedError if closed or closing. AnalysisError for an unusable output directory, a target inside the owned work directory to be cleaned, unsupported safe publication, or budget/format/write failures. __cause__ retains the original error. Correct the destination/environment and retry to the same or another directory without rereading input.

#### Side effects

Publishes timestamped files without overwriting previous files. On failure, retain_work determines whether temporary publication files are retained. Inspect the exception and run_manifest for diagnostics.

Return type: [OutputManifest](OutputManifest.md#api-OutputManifest)。

<a id="api-AnalysisResult-close"></a>
### `AnalysisResult.close`

Closes cursors and releases resources. By default, removes temporary data owned by this run; retain_work=True retains it. Original inputs and published output remain.

```python
AnalysisResult.close() -> None
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

None. Repeated calls are allowed; retry any cleanup left incomplete after a failure.

#### Raises

Attempts to close every acquired resource. If file-handle closure, staging cleanup, or budget release fails, raises the first error with later errors as additional diagnostics. Release any obstruction and retry close. Do not merely catch the exception and discard the result object.

Return type: None。

<a id="api-AnalysisResult-__enter__"></a>
### `AnalysisResult.__enter__`

Enters the result context without rereading input.

```python
AnalysisResult.__enter__() -> 'AnalysisResult'
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Returns this same object; subsequent iteration and the with block use that object.

#### Raises

ResultClosedError if already closed.

Return type: '[AnalysisResult](AnalysisResult.md#api-AnalysisResult)'。

<a id="api-AnalysisResult-__exit__"></a>
### `AnalysisResult.__exit__`

Releases resources on context exit while preserving the original analysis/application exception.

```python
AnalysisResult.__exit__(exc_type, exc_value, traceback)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`exc_type`|type[BaseException] &#124; None|Yes|No default|Positional or keyword. Exception type raised inside with, or None on normal exit; supplied by Python.|
|`exc_value`|BaseException &#124; None|Yes|No default|Positional or keyword. Exception object from the with block, or None on normal exit; supplied by Python.|
|`traceback`|TracebackType &#124; None|Yes|No default|Positional or keyword. Exception traceback, or None on normal exit; supplied by Python for continued propagation.|

#### Returns

False; exceptions continue to propagate to the caller.

#### Raises

On a normal with exit, close failures propagate. If the block already raised an exception, that original exception is preserved and close failures are attached as diagnostics so the primary cause is not hidden.

## Source locations

- [`src/chronaxis/results/result.py:194`](../../../../src/chronaxis/results/result.py#L194) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:204`](../../../../src/chronaxis/results/result.py#L204) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:326`](../../../../src/chronaxis/results/result.py#L326) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:351`](../../../../src/chronaxis/results/result.py#L351) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:359`](../../../../src/chronaxis/results/result.py#L359) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:367`](../../../../src/chronaxis/results/result.py#L367) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:375`](../../../../src/chronaxis/results/result.py#L375) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:384`](../../../../src/chronaxis/results/result.py#L384) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:396`](../../../../src/chronaxis/results/result.py#L396) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:400`](../../../../src/chronaxis/results/result.py#L400) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:405`](../../../../src/chronaxis/results/result.py#L405) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:415`](../../../../src/chronaxis/results/result.py#L415) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:531`](../../../../src/chronaxis/results/result.py#L531) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:693`](../../../../src/chronaxis/results/result.py#L693) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:744`](../../../../src/chronaxis/results/result.py#L744) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/results/result.py:752`](../../../../src/chronaxis/results/result.py#L752) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
