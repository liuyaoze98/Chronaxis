# Troubleshooting

<a id="故障排查"></a>

First identify the failing step: installation, configuration loading, input reading, calculation, result reading, or publication. Keep the full exception chain. CLI text diagnostics help locate the error; `validate/explain --format json` provides a report for software. The remedies below do not require editing original logs or overwriting results.

<a id="api-errors"></a>
<a id="python调用按失败阶段处理"></a>
<a id="python调用-按失败阶段处理"></a>
## Handle Python failures at the right stage

`PlanValidationError` contains `path`, `message`, and `code`. `path` is a configuration field location; `source` is a file path. Printing only `$.batch_version` does not explain the problem. Keep the actual constraint in `message`, the machine code, and available source positions and hints.

```python
from chronaxis import load_analysis_plan, PlanValidationError
try:
    plan = load_analysis_plan("analysis.yaml")
except PlanValidationError as error:
    print(error.source, error.path, error.code, error.message, error.hint)
    raise  # Preserve the exception chain; a failed load is not an empty plan.
```

| Stage | Common error or result | Caller action |
|---|---|---|
| Load or construct | `PlanValidationError`, with a code such as `unknown_field` | Correct the field using path/message and any source location. |
| Static checking | `ValidationReport.errors` or `execution_ready=False` | Resolve the report; validation does not imply business inputs have been read. |
| Run | `AnalysisError`, possibly caused by `SourceReadError`, `BudgetExceededError`, `ValueError`, etc. | Preserve the chain and correct the read/resource/expression cause; do not turn the failure into “no events.” |
| Stream results | `ResultClosedError`, `ContributionsUnavailableError`, or staging read failure | Read while the result is open. Missing contributions require another run with `full`. |
| Publish | `AnalysisError` and its cause, e.g. existing target or write failure | Choose a new directory and fix the environment. An open result can be published again without rereading input. |
| Batch | A normal report can contain failed jobs; an infrastructure exception may carry `batch_report` | Inspect job `error_type`, `error_message`, and `error_chain`. Preserve completed results; close `cleanup_pending` resources. |
| Close | Actual file/resource-close error | Keep the cleanup object supplied by the result or exception, release the obstruction, and retry `close`. |

`KeyboardInterrupt` and `SystemExit` mean cancellation, not success. Exception-chain attributes `runner_cleanup_owner` and `analysis_result_cleanup_owner` appear only when failed cleanup remains pending. Check for their existence before calling `close`; not every error has them.

<a id="环境与配置"></a>
## Environment and configuration

| Symptom | Cause or check | Remedy |
|---|---|---|
| `No module named chronaxis` | The active interpreter lacks the package, or an editable source directory moved. | Use the installation interpreter and reinstall the current directory as described in [Installation](installation.md). |
| Missing NumPy, `ruamel.yaml`, or CAN modules | Dependencies are absent or installed in a different environment. | Install using the same Python environment. CAN dependencies are included in the ordinary installation. |
| `PlanValidationError` at e.g. `$.signals[0].source` | Missing field, wrong type, or unknown reference. | Check source/line/column/path; `source` names `sources[].name`, not a file. |
| Duplicate key, unknown field, or old-version error | Structure does not match the current format. | Merge duplicate mappings and check spelling/case. `config_version` is integer `3`. |
| Rejected YAML anchor/alias/tag | Unsupported YAML feature. | Use ordinary mappings/lists and [imports](imports.md) for shared definitions. |
| Rejected `unit: 1` | YAML parsed `1` as a number, but units require text. | Write dimensionless `unit: '1'`. An explicit preset version is also `version: '1'`, though it is normally omitted. |
| Invalid expression | Raw column name, arbitrary Python function, or forbidden attribute access. | Bind a signal `name` and use [Expression syntax](expressions.md). YAML `true` and expression `True` belong to different languages. |

<a id="文件时间与解码"></a>
<a id="文件-时间与解码"></a>
## Files, time, and decoding

| Symptom | What to check | Remedy |
|---|---|---|
| Validation succeeds but run cannot find a file/column | Static validation does not read business files. Relative paths start at the declaring file. | Use `config origins` and check actual `path`, `time_column`, and `field` spelling. |
| Time goes backward across files | A later file restarts at zero, or `paths` are ordered incorrectly. | Put only continuous recordings in one source. Use known origins to set `offset`/`offsets`; do not invent shifts to hide a regression. |
| Two sources cannot be analyzed together | Time type, shared clock, unit, or offset does not establish a common instant. | Configure `time.type`, `time.clock`, and alignment from real synchronization evidence; see [Inputs](inputs.md). |
| CAN cannot be decoded | Channel, standard/extended type, FD flag, ID, or DBC differs. | Check `field.channel`, `frame_id`, `signal`, and DBC mapping. Types are normally detected; add `is_extended`/`is_fd` only when ambiguity is reported. Check actual frame length too. |
| ASC/raw CSV format error | `reader.version`, column mapping, delimiter, or time format differs from the file. | See [Text CAN inputs](text-inputs.md). A partial decoding policy does not excuse structural corruption. |

<a id="结果为空或不完整"></a>
## Empty or incomplete results

| Result | Interpretation and checks | Next action |
|---|---|---|
| Empty `value` | Inspect operation, scope, status, reason, and quality. No samples, zero length, unknown data, or strict rejection can all produce blanks. | Compare requested and observed ranges; inspect validity, invalid codes, and conditions. Do not substitute zero. |
| `status=partial` | Only the defensible portion of the requested range was calculated. | Decide whether that portion meets your needs; changing policy does not restore observations. See [Execution](execution.md). |
| No events | Duration too short, no known edge, inadequate validity, or wrong threshold/unit. | Check rule type and `minimum_duration`/`emit_initial`; reproduce with a small hand-checkable input. |
| Pairing `indeterminate` | Waiting interval contains unknown data or observation ends early. | Check response coverage and validity; do not claim the device failed to respond. |
| Coverage field absent | Threshold omitted/zero, or operation not in the relevant group. | Check the actual row model. Public summaries do not provide three numerical coverage ratios. |
| `ContributionsUnavailableError` | Per-message contributions were not retained. | If needed, rerun with `outputs.contributions: full`. |
| `iter_input_trace` raises `AnalysisError` | Input tracing was not enabled. | Rerun with `diagnostics.trace: true`; this is not a complete log backup. |
| `ResultClosedError` | Result/cursor is closed or closing. | Read within the `AnalysisResult` context. Close cursors explicitly in `try/finally`; cursors do not support direct `with` use. |

<a id="资源与发布"></a>
## Resources and publication

| Error | Cause and handling |
|---|---|
| `BudgetExceededError` | Identify the resource named by the error: memory, result buffering, or spool disk. Reduce `batch_rows`/`result_buffer_rows`, or increase the corresponding quota after checking available resources. Required state memory may not shrink with batch size. |
| Output target exists | Select a new directory. Even an existing empty directory is not a new target. |
| Output is inside the owned work directory | Default close cleans that work directory; place final output outside it. |
| Publication fails on non-Windows | The safe publication path is currently validated on Windows; see [Support status](status.md). |
| Standalone signal/CAN export label failure | These paths currently restrict `metadata.device_label` to `home`/`work`; see [Output limitations](exports.md). Ordinary analysis can omit these exports. |
| Corrupt staged format or read `OSError` | Stop using that result, preserve the exception and necessary evidence, and check disk/access. Do not treat the failure as an empty table. |
| Batch report includes failed jobs | Inspect each job's status, error, and output path in `batch_report.json`. Fix and rerun failed jobs independently without overwriting completed directories. |

If reproducing a problem requires retaining staged files, set `diagnostics.retain_work: true` for the next run. Enable trace separately when input positions are needed. Keep the configuration, command, exception chain, manifest, and a shareable minimal synthetic input for reproduction.
