<a id="先决定什么能算再生成配置"></a>
# Establish what can be calculated before generating configuration

| Task | Facts to establish | How to decide |
|---|---|---|
| Identify inputs | BLF/ASC logs, DBC, channel, message, and signal; actual CSV headers and time units. | Joint analysis of different clocks needs a common origin, offset, or other explicit synchronization evidence. Both files starting at zero is insufficient. |
| Bind names | Locate the original input field. `name` is its analysis name; `semantic_id` is optional business metadata. | If `BMS_I` is bound as `pack_current` with semantic ID `battery.current`, write `pack_current > 5`. A dotted semantic ID is not an object attribute. Require an explicit choice when multiple candidates match. |
| Units and direction | Existing DBC conversion, physical unit, positive direction, and measurement point. | Converting decoded 2000 mA to 2 A needs only the additional unit conversion. Unit labels and `sign_convention` do not change values. There is no public `direction_factor`; same-unit `scale=-1` is not a general sign-flip mechanism. |
| State codes | The business meaning of each code. | Whether 2 means charging depends on the equipment. Preserve numeric types for a user-supplied comparison such as `state == 0x2`. Use Boolean/enumeration mappings only when true/false or named states are needed. Unknown mapping codes do not mean nonzero=true. Without definitions, identify the missing facts rather than claiming a production-ready charging detector. |
| Validity | `valid_for` is a positive duration. An explicit value wins; otherwise use three times this signal's `period`, obtaining a DBC message period at runtime where applicable. Do not guess without a basis. Explicit null is not omission. | With an update at 0 and `period=100ms`, the value remains valid at 0.299 s and becomes unknown at 0.300 s. An invalid update at 0.2 s makes it unknown from 0.2 s. Validity does not set a sample rate or create records. |
| Conditions and statistics | Requested range, observed range, selected data, and `partial_policy`. | A fully observed, known-false condition may yield zero conditional integral. Minimum/maximum/mean of an empty selection are null. No observations or all-unknown input must not become a normal zero. Explain partial values together with `status`, `reason`, and `quality`. |
| Events and segments | Two activities can merge into one surrounding segment without making their gap an activity. | `segments.parent_event_ids` may reference several `events.event_id` values in the same run. Link calculations using `scope` and `parent_id`, not row number or rule name alone. |
| Timing and output | Batch size changes execution chunks only. Unknown response differs from decidable timeout. Actual-time integration differs from per-message accumulation. | Inspect dependencies, intervals, output units, and requested ranges in `explain`. `coverage_status` exists only for applicable result types and thresholds; it is not a numerical coverage ratio. Do not invent a `coverage` field. |
| Business presets | Charging, for example, needs `mode`/`current` and `voltage` when energy is requested. Direction, units, and measurement point must meet role requirements. | Missing facts or two matching candidates do not authorize choosing the first. Explicit bindings still undergo role validation. Example thresholds and codes do not transfer automatically to another vehicle. |

<a id="从报告定位错误"></a>
## Diagnose using actual reports

Record the user's required signals, conditions, scope, and outputs first. Request JSON from `validate`. For a constructed plan, inspect `valid`, `execution_ready`, `errors`, `warnings`, and `capability_status`. For loading failure, use the actual fields supplied in the single `error`, such as `code`, `source`, `path`, `line`, `column`, `message`, and `hint`. In `explain`, the validation report is under `validation`, with dependencies under `nodes` and `input_requirements`. Environment, I/O, or argument errors may produce only a nonzero exit code and stderr; missing JSON does not mean success.

For example, string `config_version: "3"` is rejected. Change only that value to integer 3, preserve the calculation, and recheck. Do not remove a filter, extend validity, ignore unknown data, or reverse a sign to “fix” a diagnostic. If two correction rounds still fail, report the real error and unresolved facts rather than fabricate runnable output.

```text
python -m chronaxis config origins ../../Current/examples/analysis-imports.yaml --fields --format json
python -m chronaxis config resolve ../../Current/examples/analysis-imports.yaml --defaults --format json
python -m chronaxis validate ../../Current/examples/input-csv-minimal.yaml --format json
python -m chronaxis explain ../../Current/examples/input-csv-minimal.yaml --format json
```

`origins` identifies the declaration supplying a field. `resolve` shows expanded configuration and defaults that can currently be determined; it must not invent a fixed period awaiting DBC lookup. `load_analysis_plan` resolves paths relative to the defining file; `AnalysisPlan.from_dict` takes an already expanded dictionary. Validation does not establish actual observation coverage, real units, or correct results. Deliver the version, inputs, key assumptions, checks actually performed, and unverified conditions.

<a id="持续门槛与积分起点"></a>
## Duration thresholds and integration starts

For `condition_duration`, `minimum_duration: 60s` means reaching 60 seconds by default. For “more than 60 seconds,” add `duration_comparison: ">"`, not 60.1 seconds. Default `selection_origin: onset` includes the entire qualifying interval. Select `confirmed` only when the user asks to start after confirmation. An exactly 60-second activity produces an event in the default mode and no event in strict mode. Time precision is 1 ns. Actual-time strict comparison can confirm at threshold plus 1 ns; fixed/DBC mode waits for the next driving message that takes accumulated duration strictly past the threshold.

<a id="资源不足时保留原任务"></a>
## Preserve the task when resources are insufficient

Sample minimum, maximum, and mean use chunked reductions within the shared memory budget; their result does not depend on chunk size. Do not add unrequested statistics for debugging. For a budget error, first inspect the named calculation, workspace, or read buffer instead of attributing every failure to machine RAM. If even the smallest statistical chunk does not fit, execution fails explicitly. Reducing read batches changes processing chunks, not conditions, validity, or retained input. Increase budgets only with an actual resource basis. Managed budget estimates and process RSS are different quantities.

<a id="can通道连续文件与检查范围"></a>
## CAN channels, continuous files, and check scope

DBC mapping keys, explicit signal channels, per-message selectors, and raw-frame resampling channels all start at 1 in public configuration. Channel 1 in ASC is channel 1 in configuration; do not subtract 1. Signal/selector `channel` can be omitted when the source channel is unambiguous. The program converts internal zero-based numbering. For raw CSV, `reader.channel_origin` still describes whether the input column itself starts at 0 or 1. Migrate old zero-based configuration rather than editing the original log.

Configuration paths are relative to the file containing that field, including shared definitions. Dictionary APIs use `base_dir`, defaulting to the current directory. `chronaxis explain PLAN --format json` shows plan information; `chronaxis config resolve PLAN --format json` shows expanded configuration. Files within one source are continuous in listed order, retaining candidate state across boundaries. Directory matching uses natural order. Sharing a folder does not prove sharing a session: use batch tasks for independent experiments, and do not invent offsets to concatenate them.

ASC checks timestamp order only for required channels/IDs by default. The source's earliest and latest frame times are still collected during that same read. Required records moving backwards remain errors; full checks or raw-frame export require the whole source to be ordered. Do not add a separate full-file scan followed by automatic cleaning. A small difference of microseconds does not authorize changing the input.

<a id="默认可读结果"></a>
## Default readable results

Omitting `outputs.tables` selects `readable_csv`: Chinese filenames and headers, exact seconds, and one row containing the metrics for each event or window. Discover actual files through `run_manifest.json.outputs`; do not hard-code `events.csv` or `calculations.csv`. Explicit `outputs.tables: csv` or `jsonl` selects the original interchange format and integer nanoseconds. Only the selected table format is produced.

Readable tables retain calculation names and units. Empty cells are not zero. Each metric independently reports `完整` (complete), `部分有效` (partial), or `无法确定` (indeterminate), with its reason. Inspect interval status separately from metric status. Global `has_unknown` does not invalidate a complete calculation within a known interval. For no events, inspect manifest `result_messages`; do not create a false zero-energy result. Preserve the original analysis time coordinates without inventing dates or shifting to zero. Do not duplicate seconds and nanoseconds. Python iterators such as `iter_events` and `iter_calculations` continue to return original typed rows.

<a id="独立批量的进程数"></a>
## Process count for independent batch tasks

Root-level batch `process_count` is a positive integer, default 1, limiting analysis worker processes. It excludes the scheduler and CAN reader subprocesses. `run_batch(plan, output, process_count=4)` and CLI `--process-count 4` override it. Only the Python API accepts `None` to inherit the plan; configuration rejects null and Booleans. Call from a Python script inside `if __name__ == "__main__":`. Ordinary `AnalysisRunner` has no such parameter. Continuous `paths` in one session are not split into independent processes.

Each task has its own budgets and output. Cancellation prevents tasks that have not started; in-flight tasks finish and close. `report.close()` can retry remote cleanup. Unstarted tasks and worker crashes are not successes. Legacy `workers`, `max_workers`, and `--workers` are rejected.

<a id="迁移数值与后端核对"></a>
## Migrated numbers and backend comparisons

Historical INI seconds accept scientific notation. Import preserves compact representation and checks representable durations; do not expand huge exponents for display. A rejection report is not a successfully generated analysis plan. Both backends must agree on event boundaries, statuses, and diagnostics. Compare floating-point metrics using their unit and agreed error tolerance, without requiring bitwise equality or attributing event/quality differences to rounding.

Ordinary scalar calculations, including sample statistics, can return `coverage_status` when `minimum_coverage > 0`. It records the threshold decision, not a ratio, and does not change the equal weighting of `sample_mean`. Initial-edge `emit_initial` concerns the first known state, not an arbitrary first `True` anywhere in the analysis. A requested endpoint can produce a point event only when it is actually observed and satisfies the rule.
