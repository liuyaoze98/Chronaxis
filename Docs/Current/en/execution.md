# Execution settings and resource management

<a id="执行设置与资源管理"></a>

The root `execution` object selects the calculation implementation, input batch size, managed memory and temporary disk limits, and the treatment of incomplete data. Select inputs in `sources` and analysis operations in `calculations`, `rules`, and related sections.

For multiple independent analyses, set `process_count` at the root of a separate [batch configuration](batch.md). It does not belong inside `execution`; `batch_rows` is a sample count, not a process count.

<a id="完整最小例与执行扩展"></a>
## Minimal examples and optional settings

[calculation-minimal.yaml](../examples/calculation-minimal.yaml) omits `execution` and `diagnostics` and produces 30 J with the defaults. [execution-diagnostics.yaml](../examples/execution-diagnostics.yaml) uses the same input with the reference backend, one sample per batch, a one-row result buffer, and input tracing. The value remains 30 J and `input_trace` becomes available. These tiny batches demonstrate batching; they are not performance recommendations.

[execution-report.yaml](../examples/execution-report.yaml) and [execution-strict.yaml](../examples/execution-strict.yaml) both request 0–12 seconds, while the 4000 W input is observed only through 8 seconds. They return 32000 J / `partial` and an empty value / `indeterminate`, respectively. Only `partial_policy` differs.

Run `chronaxis run FILE.yaml --output NEW_DIRECTORY`. Start with the minimal example and add settings only when needed. The following block shows every default; it is a reference, not a required template. To use it with [analysis.yaml](../examples/analysis.yaml), replace or add the root `execution` object and retain the other root fields. Do not add a second `execution` key.

```yaml
execution:
  backend: numpy
  batch_rows: 65536
  memory_budget_bytes: 268435456
  result_buffer_rows: 4096
  spool_quota_bytes: null
  partial_policy: report
  on_budget_exceeded: error
```

<a id="全部运行字段"></a>
## All execution fields

The paths below are relative to `execution`, for example `execution.backend`. The object and all seven fields are optional. Use an object when supplying it, such as `execution: {batch_rows: 1000}`. Only `spool_quota_bytes` accepts `null`; the other fields must not use `null` as a substitute for omission. Limits and row counts must be positive integers, excluding zero and Boolean values. See [configuration syntax](configuration-language.md).

| Field | Type | Required | Default | Meaning and choices |
|---|---|---|---|---|
| backend | string | No | `numpy` | `numpy` uses array calculations; `reference` uses an independent implementation for comparison. |
| batch_rows | integer | No | 65536 | Maximum signal samples delivered in one batch; choose according to available memory and batch overhead. |
| memory_budget_bytes | integer | No | 268435456 | Positive managed-memory limit, in bytes, for the analysis engine. |
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
| `numpy` | Uses NumPy arrays for supported numeric operations; Python still handles input and event state. | Normal analysis. |
| `reference` | Uses an independent numeric implementation. | Recalculate the same input and configuration to investigate a result. |

Both implementations use the same units, validity and missing-data rules. They need not take the same time, and NumPy is not guaranteed to be faster for every task. `AnalysisRunner(backend="reference")` or the single-run CLI option `--backend reference` overrides the plan for that run. The manifest records the effective choice. Both use the project's installed dependencies.

<a id="batch_rows输入批次大小"></a>
<a id="batch_rows-输入批次大小"></a>
## batch_rows: input batch size

`execution.batch_rows` defaults to 65536 and limits the signal samples delivered in each batch. It is not a duration or a limit on the entire recording. Samples from all signal columns are counted: one CSV row updating both power and state creates two signal samples.

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

To change the default for all calculations, replace the root `execution` block in [analysis.yaml](../examples/analysis.yaml):

```yaml
execution:
  partial_policy: strict
```

A calculation can override that default. Replace the root `calculations` block with the following example while retaining the other declarations, including `power`:

```yaml
calculations:
  - name: session_energy
    expr: power
    partial_policy: report
    operation: integral
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
diagnostics:
  trace: true
```

Enable message contributions separately with `outputs.contributions: full`. Put descriptive notes in the root `metadata` object (default `{}`); it does not replace `execution` or `diagnostics`. Independent signal/CAN exports have the [device-label requirements](exports.md) described there.

<a id="计算项的覆盖门槛"></a>
## Calculation coverage thresholds

`minimum_coverage` belongs to a calculation or a supporting preset, not `execution`. See [statistics and integration](calculations.md).

<a id="一份可直接运行的对照"></a>
## Runnable comparison

[readability_examples.py](../examples/readability_examples.py) compares both backends, different `batch_rows`, and `report`/`strict` on the same five-row input, asserting event counts and energy. It also runs the expression examples and raises an error if a check fails.

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
| Analysis with independent signal/CAN export | The same field must be `home` or `work`, identifying a confirmed device; `pending` and custom labels are rejected. |
| Batch summary | CLI reads `CHRONAXIS_DEVICE_LABEL`; Python uses `run_batch(..., device_label=...)`, default `pending`. Neither overrides child-analysis metadata. |
| Legacy INI import report | CLI reads `CHRONAXIS_DEVICE_LABEL`; Python uses the import entry's `device_label` argument. This labels the conversion report, not analysis metadata. |

For an ordinary analysis:

```yaml
metadata:
  device_label: lab_pc
```
