# Execution settings and resource management

<a id="执行设置与资源管理"></a>

The root `execution` object controls how one analysis runs: file workers, numerical implementation, managed resources and handling of incomplete results. Select inputs in `sources` and analysis operations in `calculations`, `rules` and related sections.

## Basic configuration: choose the process limit

For ASC/BLF volumes from one experiment, start with a limit of four file workers. Ordinary-analysis workers read, parse and DBC-decode files; the main process preserves signal state, detects events and performs calculations. With the [high-performance integrator](fast-energy.md), workers also evaluate each message's contribution.

Put this fragment at the root of a complete analysis configuration, aligned with `dataset` and `sources`. If `execution` already exists, add or replace only its `process_count` and retain the other settings. Do not duplicate the parent key.

```yaml
execution:          # Runtime settings for this analysis
  process_count: 4  # At most four file workers, excluding the main process
```

Four is the recommended example limit, not the software default: omission still means `1`. Two files can use at most two file workers. A single file is not divided into four parallel calculations. Choose a positive integer such as `2`, `4` or `8` for the CPU, available memory and other applications on your computer. Start with the complete [continuous-volume example](../examples/continuous-parallel.yaml): its two ASC files jointly produce **38 J**, without restarting integration at the file boundary.

| Input or task | Where to set the limit | Basic configuration |
|---|---|---|
| Continuous ASC/BLF volumes in one source | Analysis `execution.process_count` | Set `4` and keep the default requested-signal decoding. See [supported inputs](continuous-files.md). |
| Independent experiments | Root `process_count` in a [batch configuration](batch.md) | Set the batch to `4` and each child analysis to `execution.process_count: 1` to avoid nested pools. |
| CSV, memory, multiple sources or all-signal decoding | Analysis `execution.process_count` | Set `1` for now. Separate independent analyses can use the batch entry above. |

`batch_rows` sets samples per analysis batch, not worker processes. Raising the process limit does not sort files; see [file continuation and time merging](continuous-files.md).

<a id="完整最小例与执行扩展"></a>
## Minimal examples and optional settings

[calculation-minimal.yaml](../examples/calculation-minimal.yaml) reads one supplied ASC file, decodes power with teaching.dbc, and produces 30 J. It retains the basic limit `process_count: 4`. For this single ASC file with the default `file_merge: concatenate`, reading and analysis run in the current process without a file worker. This statement applies to this example's input and file organization.

[execution-diagnostics.yaml](../examples/execution-diagnostics.yaml) uses the same ASC/DBC with the reference backend, one sample per batch, a one-row result buffer, and input tracing. The value remains 30 J and `input_trace` becomes available. These tiny batches demonstrate batching; they are not performance recommendations.

[execution-report.yaml](../examples/execution-report.yaml) and [execution-strict.yaml](../examples/execution-strict.yaml) both request 0–12 seconds, while the 4000 W input is observed only through 8 seconds. They return 32000 J / `partial` and an empty value / `indeterminate`, respectively. Only `partial_policy` differs.

Run `chronaxis run FILE.yaml --output OUTPUT_DIRECTORY`. Choose the process limit using the table above, then add resource or diagnostic settings only when needed. The following block lists every software default for reference; ordinary ASC/BLF examples usually need only the process limit shown above. To use it with [analysis.yaml](../examples/analysis.yaml), replace or add the root `execution` object and retain the other root fields. Do not add a second `execution` key.

```yaml
execution:                        # Runtime and resource settings
  process_count: 1                # Reading/decoding worker limit for this analysis, excluding the main process
  backend: auto                   # Select from the whole plan; omit for the default, or fix reference/numpy
  batch_rows: 65536               # Maximum calculation rows processed in a batch
  memory_budget_bytes: 268435456  # Shared analysis memory budget in bytes
  result_buffer_rows: 4096        # Rows buffered before writing intermediate results
  spool_quota_bytes: null         # Maximum temporary disk usage in bytes
  partial_policy: report          # Whether incomplete observations may yield a partial value
  on_budget_exceeded: error       # Action when the declared resource budget cannot be met
```

<a id="全部运行字段"></a>
## All execution fields

The paths below are relative to `execution`, for example `execution.backend`. The object and the fields below are optional. Use an object when supplying it, such as `execution: {batch_rows: 1000}`. Only `spool_quota_bytes` accepts `null`; the other fields must not use `null` as a substitute for omission. Limits and row counts must be positive integers, excluding zero and Boolean values. See [configuration syntax](configuration-language.md).

| Field | Type | Required | Default | Meaning and choices |
|---|---|---|---|---|
| process_count | integer | No | 1 | Positive reading/decoding worker limit for this analysis, excluding the main process and capped by file count. Choose for available CPU and memory; null and Boolean values are invalid. See [supported configurations](continuous-files.md). |
| backend | string | No | `auto` | `auto` selects an implementation from the whole plan; `numpy` and `reference` fix the implementation. See the choices below. |
| batch_rows | integer | No | 65536 | Maximum signal samples delivered in one batch; choose according to available memory and batch overhead. |
| memory_budget_bytes | integer | No | 268435456 | Positive shared managed-memory limit, in bytes, for analysis state and file-worker buffers. |
| result_buffer_rows | integer | No | 4096 | Maximum result rows accumulated in memory before writing them to temporary storage. |
| spool_quota_bytes | integer or null | No | `null` | Positive managed temporary-disk quota in bytes; `null` adds no quota. Physical disk capacity still applies. |
| partial_policy | string | No | `report` | `report` returns the known portion and marks it; `strict` returns an empty value when required data is incomplete. |
| on_budget_exceeded | string | No | `error` | Only `error` is supported: stop and report the exhausted resource. There is no discard-and-continue mode. |

<a id="backend计算实现"></a>
<a id="backend-计算实现"></a>
## backend: calculation implementation

A backend is a calculation implementation, not a server or separate service.

| Value | Behavior | When to use it |
|---|---|---|
| `auto` (default) | Selects reference or numpy from the plan before reading logs, without trial runs. | Omit backend for ordinary use. |
| `numpy` | Evaluates built-in streaming expressions directly at each update; suitable batch calculations still use NumPy arrays, and extensions use their registered numpy implementation. | Fix NumPy for a comparison. |
| `reference` | Uses an independent numeric implementation. | Recalculate the same input and configuration to investigate a result. |

`auto` currently selects reference for actual-time session ZOH integrals of one signal from one signal CSV, or at most two signals sharing one CAN source and message selector. Every calculation must belong to this simple built-in arithmetic category and omit `condition`. Events, windows, temporal transforms, other statistics, lookups and host extensions use numpy. Selection inspects the plan, not the data; runtime errors are reported without retrying another implementation.

For the [minimal integral configuration](../examples/calculation-minimal.yaml), `explain.selected_backend` is `reference`. Copy the file and add only `condition: power > 0` to its existing energy calculation item. Run `python -m chronaxis explain CONFIG --format json` again: `selected_backend` becomes `numpy`, without declaring events or windows. Both plans are valid. This selects the ordinary runner's numerical backend; it does not switch to the independent fast entry point.

Both numerical implementations use the same units, validity and missing-data rules. They need not take the same time, and NumPy is not guaranteed to be faster for every task. `AnalysisRunner(backend="reference")` or the single-run CLI option `--backend reference` overrides the plan for that run. The explain fields `requested_backend`, `selected_backend` and `backend_reason` show the request, static selection and reason. The manifest records the actual reference/numpy backend; auto is a selection policy, not a third numerical algorithm. A batch override of auto selects independently for each job. Both use the project's installed dependencies.

With auto, a same-frame CAN integral uses the direct path when its binding is unambiguous and signal export, raw-frame export, tracing and integrity diagnostics are not requested. The rule applies to ASC, BLF, raw CAN CSV and continuous volumes. If the binding cannot establish eligibility, the general flow is selected before reading the first frame. Runtime failures still fail the task. Explicit reference/numpy uses the corresponding general flow.

This remains actual-time integration: 4000W at 0s, 4800W at 0.12s, and observed end at 0.30s give 4000×0.12 + 4800×0.18 = 1344J while both values remain valid. It does not substitute a DBC period or change the [high-performance integrator](fast-energy.md), which sums each expression contribution.

<a id="batch_rows输入批次大小"></a>
<a id="batch_rows-输入批次大小"></a>
## batch_rows: input batch size

`execution.batch_rows` defaults to 65536 and limits the signal samples delivered in each batch. It is not a duration or a limit on the entire recording. Samples from all signal columns are counted: one CSV row updating both power and state creates two signal samples.

The independent signal CSV reader (`signal_csv`) builds batches from the data actually read and the remaining shared budget; it does not allocate space for 65536 samples up front. Near capacity, it delivers the samples already read before continuing, so a batch can be smaller than the limit. Signals from one row may span adjacent batches while preserving update order, values, validity, and event state. This behavior belongs to the signal CSV reader and does not imply that every source automatically reduces its batches according to the budget.

If even one required record and its necessary parsing and handoff state cannot fit, execution still raises `BudgetExceededError`; it does not truncate or discard data. Start ordinary CSV tasks with the default batch setting, then inspect the named resource if an error occurs before changing configuration. Managed resource estimates do not guarantee that total process memory (RSS) remains below the configured budget.

If an activity runs from 1 to 4 seconds and one batch ends at 2 seconds, the next batch continues its state. The result remains one activity from 1 to 4 seconds rather than separate events at batch boundaries.

Smaller batches generally reduce the amount delivered at once but increase handoffs. Larger batches can reduce handoffs while retaining more data. Neither sets a whole-process memory limit: event state, history, result buffers, and decoding libraries also use memory. Tutorials use `batch_rows=1` to exercise boundaries with five rows, not to recommend processing real logs individually.

<a id="memory_budget_bytes受管理内存额度"></a>
<a id="memory_budget_bytes-受管理内存额度"></a>
## memory_budget_bytes: managed memory

The default is 268435456 bytes, or 256 MiB; 1 MiB is 1024 × 1024 bytes. The engine reserves this allowance for the buffers and state it manages. If insufficient, it raises an error rather than dropping data. This is **not a hard limit on the entire Python process**: decoding libraries, Python itself, and untracked overhead also use memory.

For `BudgetExceededError`, first identify the resource named in the error. Reducing `batch_rows` or `result_buffer_rows` can help with buffers, but may not solve a task whose required state itself needs more space. Increase the budget only when the machine has enough available memory. `on_budget_exceeded` accepts only `error`, not `skip`.

Sample minimum, maximum, and mean reductions automatically use smaller blocks according to the remaining shared budget, which also covers reading queues and other calculations. This does not drop samples or change results, validity, or condition intervals, and needs no extra configuration. If even the smallest workspace cannot fit, the error identifies the calculation, sample-statistics workspace, and available bytes. Remove unneeded statistics or reduce reading batches before increasing the allowance. Budget accounting is a conservative estimate, not the process-memory figure in Task Manager.

<a id="结果缓冲与暂存配额"></a>
## Result buffers and temporary-disk quota

When there are many results, completed rows are written incrementally to the working directory before final output is generated.

| Field | Default | Effect |
|---|---|---|
| `result_buffer_rows` | 4096 | Maximum buffered rows before a temporary write, not a limit on the total results retained. |
| `spool_quota_bytes` | `null` | Managed temporary-disk allowance. `null` adds no limit; the disk can still fill up. |

For example, `spool_quota_bytes=1073741824` allows 1 GiB. Exceeding it fails the run and preserves available diagnostics. By default, `close()` closes resources and removes the run's temporary files. Set `diagnostics.retain_work=true` explicitly to retain them. Input files and published results are not removed.

<a id="partial_policy部分结果处理"></a>
<a id="partial_policy-部分结果处理"></a>
## partial_policy: incomplete results

Request 0–12 seconds at 4000 W, but suppose the recording stops at 8 seconds. The observed energy is `4000 × 8 = 32000 J`. The remaining four seconds are unknown, so the full 12-second total cannot be reported as 48000 J.

| Setting | value | status | Meaning |
|---|---|---|---|
| `report` | 32000 J | `partial` | Return the known portion, explicitly marked as incomplete. |
| `strict` | `null` (`None` in Python) | `indeterminate` | Do not give a value for the incomplete interval; retain the reason and coverage information. |

`report` neither guesses missing values nor replaces them with zero. With no calculable data at all it cannot return a normal zero.

In [analysis.yaml](../examples/analysis.yaml), add or change `partial_policy` inside the existing root `execution` object. Retain the process limit and other settings; do not duplicate the parent key:

```yaml
execution:                # Runtime and resource settings
  process_count: 4        # Retain this analysis's file-worker limit
  partial_policy: strict  # Whether incomplete observations may yield a partial value
```

A calculation can override that default. Replace the root `calculations` block with the following example while retaining the other declarations, including `power`:

```yaml
calculations:               # Requested statistics or selected rows
  - name: session_energy    # Name used to identify and reference this object
    expr: power             # Formula using the declared signal or derived names
    partial_policy: report  # Whether incomplete observations may yield a partial value
    operation: integral     # Calculation to apply to the expression
```

The calculation's policy takes precedence. These are fragments for a complete configuration; see [quick start](quickstart.md).

<a id="diagnostics"></a>
<a id="诊断与现场保留"></a>
## Diagnostics and retaining temporary work

The root `diagnostics` object controls optional evidence. Its three independent Boolean switches default to `false`. Omission or `{}` uses the defaults; `null` is invalid. They do not change the formula. Per-message contributions have a separate output setting.

| Path | Purpose | `true` | `false` (default) |
|---|---|---|---|
| `diagnostics.trace` | Locate individual input records used by the task. | Retain needed input records; expose `input_trace` and `iter_input_trace()`. | No detailed table; requesting the iterator raises `AnalysisError`. This never means automatically retaining the entire log. |
| `diagnostics.integrity` | Check input/output content using additional digests. | Add relevant content digests and integrity diagnostics. | Keep necessary identity, size, and structure checks, without promising extra content hashes. |
| `diagnostics.retain_work` | Keep temporary files after closing or failure. | Retain this run's work for investigation. | Remove this run's temporary data, preserving inputs and final outputs. |

To enable tracing, add or replace the root object in [analysis.yaml](../examples/analysis.yaml):

```yaml
diagnostics:   # Optional diagnostic material
  trace: true  # Whether to retain binding and calculation trace records
```

Enable message contributions separately with `outputs.contributions: full`. Put descriptive notes in the root `metadata` object (default `{}`); it does not replace `execution` or `diagnostics`. Analysis and exports share the same [optional device label](exports.md).

<a id="计算项的覆盖门槛"></a>
## Calculation coverage thresholds

`minimum_coverage` belongs to a calculation or a supporting preset, not `execution`. See [statistics and integration](calculations.md).

<a id="一份可直接运行的对照"></a>
## Runnable comparison

[readability_examples.py](../examples/readability_examples.py) compares both backends, different `batch_rows`, and `report`/`strict` on the same five-row input, asserting event counts and energy. It also runs the expression examples and raises an error if a check fails.

From the offline manual extraction root, which directly contains `examples`, run:

```powershell
python -B examples/readability_examples.py
```

With a source checkout, run the following from its root containing `pyproject.toml`:

```powershell
python -B Docs/Current/examples/readability_examples.py
```

It creates a new directory under the system temporary directory by default. `--output-root` selects an existing parent directory. Adapt synthetic thresholds to the actual equipment when writing your own analysis.

<a id="根级metadata与运行来源标签"></a>
## Root metadata and device labels

`metadata` defaults to an empty object. `metadata.device_label` is used in the run manifest; other notes do not change calculations.

| Entry | Location, default, and restrictions |
|---|---|
| Ordinary analysis | Root `metadata.device_label`: nonblank text, such as `lab_pc`; defaults to `pending`. Ordinary CLI `run` does not override it from `CHRONAXIS_DEVICE_LABEL`. |
| Analysis with signal/CAN export | The same field is optional and defaults to `pending`; any nonblank string, such as `lab-pc` or `试验台一号`, is accepted. |
| Batch summary | CLI reads `CHRONAXIS_DEVICE_LABEL`; Python uses `run_batch(..., device_label=...)`, default `pending`. Neither overrides child-analysis metadata. |

For an ordinary analysis:

```yaml
metadata:               # Optional descriptive metadata
  device_label: lab_pc  # Optional nonblank device label; defaults to pending without affecting calculations or exports
```
