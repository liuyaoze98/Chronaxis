<a id="先决定什么能算再生成配置"></a>

# Establish what can be calculated before generating configuration

## Choosing the calculation implementation

Ordinary analysis defaults to `execution.backend: auto` when omitted. It selects reference or numpy from the whole plan without reading data, trial runs or runtime retries. It selects reference for simple actual-time session ZOH integrals of one signal from one signal CSV, or at most two signals with the same CAN message selector. Other statistics, rules, windows, temporal transforms, lookups and host extensions select numpy. Explicit reference/numpy choices take priority; batch auto selects per job. Explain reports requested_backend, selected_backend and backend_reason; the run manifest records the actual numerical backend. Built-in streaming expressions process the current normalized values directly; suitable batch calculations still use arrays. Do not describe every step as vectorized. `reference` retains an independent numerical implementation for comparisons with the same input. Host extensions keep the selected backend interface. Backend choice changes neither timing, validity, missing-data rules nor requested outputs, and does not guarantee that one implementation is faster for every task. For eligible same-frame CAN actual integrals, auto uses a direct path when the binding is unambiguous and signal/raw-frame export, trace and integrity are not requested. Otherwise it selects the general flow before the first frame; failures never retry the input. Raw CAN formats and continuous volumes keep the same timing and validity rules. See the [execution schema](../../Schema/analysis.schema.json#/properties/execution).

## Output directories and device labels

Do not require a device label to generate analysis or signal/CAN export configurations. `metadata.device_label` is optional and defaults to `pending`. When users want to record a device, preserve their nonblank label, such as `lab-pc` or `试验台一号`; do not invent `home` or `work`. Explicit null, whitespace-only and non-string values are configuration errors. Existing result directories can be reused without replacing old files; an explicit working directory must still be new. Users choose input and output directories; directory names add no restrictions.

## Simultaneous updates and result comparison

Ordinary signal updates can merge when value, type, validity, quality and raw enum code agree. Conflicts fail by default under same_time_policy: error; last_by_sequence selects the greatest source sequence, not worker arrival order. Per-message accumulation still keeps every contribution. Explicit path entries preserve order; directory/wildcard matches sort naturally within each entry. Validate does not scan business records, so bad rows, timestamps or resource problems may still fail during run. Compare runs by business objects, actual times and parent relationships while preserving duplicate counts; append sequence is not a stable business ID. Unit display may use W/s, 1/W or 1/J, but mA scale, temperature roles and N*m quantity kind remain unchanged; relabeling does not replace numeric conversion.

## Continuous files in one session

Put files from one charge in one ASC/BLF source. execution.process_count is a positive reading/decoding worker limit, default 1; ordinary run/validate/explain and AnalysisRunner accept an explicit override. The main process preserves event, validity and integration state. file_merge: concatenate consumes file order; time_order validates each required sequence then stably merges a verified shared clock, without shifting or deduplicating records. Do not split a continuous recording into independent batch jobs and add their results. Current support is one ASC/BLF source with requested decoding, with no nested file pool inside a batch worker. With default 1 and concatenate, ASC/BLF are read and decoded inline; time_order uses file workers even at a limit of 1. Time merging uses quota-controlled staging and a shared memory budget; more workers do not guarantee speedup. See the [runnable guide](../../Current/en/continuous-files.md).

## Facts needed for every task

| Task | Facts to establish | How to decide |
|---|---|---|
| Identify inputs | BLF/ASC logs, DBC, channel, message, and signal; actual CSV headers and time units. | Joint analysis of different clocks needs a common origin, offset, or other explicit synchronization evidence. Both files starting at zero is insufficient. |
| Bind names | Locate the original input field. `name` is its analysis name; `semantic_id` is optional business metadata. | If `BMS_I` is bound as `pack_current` with semantic ID `battery.current`, write `pack_current > 5`. A dotted semantic ID is not an object attribute. Require an explicit choice when multiple candidates match. |
| Units and direction | Existing DBC conversion and input/target units; establish direction and measurement point when a charging/discharging interpretation needs them. | Version 4 infers conversion when both scale and offset are omitted: a DBC value of 2000 mA with unit: A becomes 2 A. Supplying either coefficient disables additional automatic conversion. sign_convention describes direction without changing values; same-unit scale=-1 is not a general sign-flip mechanism. |
| State codes | The business meaning of each code. | Whether 2 means charging depends on the equipment. Preserve numeric types for a user-supplied comparison such as `state == 0x2`. Use Boolean/enumeration mappings only when true/false or named states are needed. Unknown mapping codes do not mean nonzero=true. Without definitions, identify the missing facts rather than claiming a production-ready charging detector. |
| Validity | `valid_for` is a positive duration. An explicit value wins; otherwise use three times this signal's `period`, obtaining a DBC message period at runtime where applicable. Do not guess without a basis. Explicit null is not omission. | With an update at 0 and `period=100ms`, the value remains valid at 0.299 s and becomes unknown at 0.300 s. An invalid update at 0.2 s makes it unknown from 0.2 s. Validity does not set a sample rate or create records. |
| Conditions and statistics | Requested range, observed range, selected data, and `partial_policy`. | A fully observed, known-false condition may yield zero conditional integral. Minimum/maximum/mean of an empty selection are null. No observations or all-unknown input must not become a normal zero. Explain partial values together with `status`, `reason`, and `quality`. |
| Events and segments | Two activities can merge into one surrounding segment without making their gap an activity. | `segments.parent_event_ids` may reference several `events.event_id` values in the same run. Link calculations using `scope` and `parent_id`, not row number or rule name alone. |
| Timing and output | Batch size changes execution chunks only. Unknown response differs from decidable timeout. Actual-time integration differs from per-message accumulation. | Inspect dependencies, intervals, output units, and requested ranges in `explain`. `coverage_status` exists only for applicable result types and thresholds; it is not a numerical coverage ratio. Do not invent a `coverage` field. |
| Business presets | Charging, for example, needs `mode`/`current` and `voltage` when energy is requested. Direction, units, and measurement point must meet role requirements. | Missing facts or two matching candidates do not authorize choosing the first. Explicit bindings still undergo role validation. Example thresholds and codes do not transfer automatically to another vehicle. |

<a id="从报告定位错误"></a>
## Diagnose using actual reports

Do not infer an error category from exit code 1 or 2 alone. Ordinary commands usually return 1 for a missing configuration file; fast validate/explain/run return 2 when preparing configuration, DBCs or the input list fails. Fast batch has its own classification: failure to write the final batch report can also return 2. Read stderr and any job reports already produced, then use the CLI description for that command and phase. A nonzero exit does not mean existing results were rolled back.

Record the user's required signals, conditions, scope, and outputs first. Request JSON from `validate`. For a constructed plan, inspect `valid`, `execution_ready`, `errors`, `warnings`, and `capability_status`. For loading failure, iterate `errors`, even for one error; `blocked_checks` explains checks prevented by invalid dependencies. Each item provides available fields such as `code`, `source`, `path`, `line`, `column`, `message`, and `hint`. In `explain`, the validation report is under `validation`, with dependencies under `nodes` and `input_requirements`. Environment, I/O, or argument errors may produce only a nonzero exit code and stderr; missing JSON does not mean success.

For example, string `config_version: "4"` is rejected. Change only that value to integer 4, preserve the calculation, and recheck. Do not remove a filter, extend validity, ignore unknown data, or reverse a sign to “fix” a diagnostic. If two correction rounds still fail, report the real error and unresolved facts rather than fabricate runnable output.

```text
python -m chronaxis config origins ../../Current/examples/analysis-imports.yaml --fields --format json
python -m chronaxis config resolve ../../Current/examples/analysis-imports.yaml --defaults --format json
python -m chronaxis validate ../../Current/examples/input-csv-minimal.yaml --format json
python -m chronaxis explain ../../Current/examples/input-csv-minimal.yaml --format json
```

`origins` identifies the declaration supplying a field. `resolve` shows expanded configuration and defaults that can currently be determined; it must not invent a fixed period awaiting DBC lookup. `load_analysis_plan` resolves paths relative to the defining file; `AnalysisPlan.from_dict` takes an already expanded dictionary. Validation does not establish actual observation coverage, real units, or correct results. Deliver the version, inputs, key assumptions, checks actually performed, and unverified conditions.

<a id="持续门槛与积分起点"></a>
## Duration thresholds and integration starts

For `condition_duration`, `duration_comparison` is required and has no default. With `minimum_duration: 60s`, use `">="` for “at least 60 seconds” or `">"` for “more than 60 seconds,” not 60.1 seconds. If the request does not specify whether exactly 60 seconds qualifies and the choice affects the result, ask the user before choosing. Default `selection_origin: onset` includes the entire qualifying interval. Select `confirmed` only when the user asks to start after confirmation. An exactly 60-second activity produces an event with `>=` and no event with `>`. Time precision is 1 ns. Actual-time strict comparison can confirm at threshold plus 1 ns; fixed/DBC mode waits for the next driving message that takes accumulated duration strictly past the threshold.

<a id="资源不足时保留原任务"></a>
## Preserve the task when resources are insufficient

Sample minimum, maximum, and mean use chunked reductions within the shared memory budget; their result does not depend on chunk size. Do not add unrequested statistics for debugging. For a budget error, first inspect the named calculation, workspace, or read buffer instead of attributing every failure to machine RAM. If even the smallest statistical chunk does not fit, execution fails explicitly. Reducing read batches changes processing chunks, not conditions, validity, or retained input. Increase budgets only with an actual resource basis. Managed budget estimates and process RSS are different quantities.

The `signal_csv` reader also delivers batches early according to actual input contents and the remaining shared budget. `batch_rows` is an upper limit, not a promise to allocate a full batch up front. Keep the default for ordinary CSV configurations instead of always changing it to 4096; inspect the actual resource error first. Insufficient capacity for the minimum record, parsing, or handoff state still causes failure without dropping data or guaranteeing a bound on total process RSS. This behavior applies to independent signal CSV input, not every source.

<a id="can通道连续文件与检查范围"></a>
## CAN channels, continuous files, and check scope

DBC mapping keys, explicit signal channels, per-message selectors, and raw-frame resampling channels all start at `1` in public configuration. DBC channel keys are positive-integer strings without leading zeros: write `"1"` for the first channel. Ordinary channel fields take the integer `1`; do not subtract one. A signal or selector can omit `channel` when its source has a single channel, which the program then selects. Keep channel values in the original log unchanged. For raw CSV, `reader.channel_origin` still describes whether the input file's channel column starts at `0` or `1`.

Configuration paths are relative to the file containing that field, including shared definitions. Dictionary APIs use `base_dir`, defaulting to the current directory. `chronaxis explain PLAN --format json` shows plan information; `chronaxis config resolve PLAN --format json` shows expanded configuration. Files within one source are continuous in listed order, retaining candidate state across boundaries. Directory matching uses natural order. Sharing a folder does not prove sharing a session: use batch tasks for independent experiments, and do not invent offsets to concatenate them.

For file discovery, a wildcard ending in the literal extension `.asc`, `.blf`, `.csv`, or `.txt` matches extension letters without regard to case: `*.asc` also matches `.ASC`. Filename stems, directory names, and other wildcard patterns still follow the operating system's rules; do not change the case of a user's path on this basis. Recursion still requires explicit `**`, and the source type still limits accepted formats.

ASC checks timestamp order only for required channels/IDs by default. The source's earliest and latest frame times are still collected during that same read. Required records moving backwards remain errors; full checks or raw-frame export require the whole source to be ordered. Do not add a separate full-file scan followed by automatic cleaning. A small difference of microseconds does not authorize changing the input.

The default ASC reader accepts a strictly matching `Length = … BitCount = … ID = …` suffix; this alone does not require `reader.version`. Known `chip status` events advance the relative clock before being skipped and do not generate signals. Classic error frames accept bare records, eight-bit binary ECC, or a complete ordered Flags/CodeExt/Code/ID/DLC/Position/Length diagnostic suffix and remain error frames. The standard Vector reader also accepts complete CAN FD error diagnostics with an Arb./Data. phase, partial payload and seven timing fields; the diagnostic payload never contributes signal values. Unknown events, unknown diagnostic layouts and malformed fields fail; do not tell users to delete them to bypass checks. A classic remote frame may omit DLC, meaning unknown. ASC export retains the omission; BLF export refuses to invent a length. Raw CAN CSV still requires an explicit remote-frame DLC.

Decoded `signal_csv` defaults to `utf-8-sig`, accepting plain UTF-8 and Excel UTF-8 with a file-leading BOM; explicit encoding still takes precedence. Do not remove `U+FEFF` from within the file. Unnamed trailing columns may be ignored only when their corresponding cells are empty. Nonempty or whitespace-only unnamed data, empty names in the middle, duplicate names and missing named cells still require correction rather than data removal.

<a id="默认可读结果"></a>
## Default readable results

Omitting `outputs.tables` selects `readable_csv`: Chinese filenames and headers, exact seconds, and one row containing the metrics for each event or window. Use the CLI manifest path or API manifest_path, then discover actual files through the manifest outputs list; do not hard-code `events.csv` or `calculations.csv`. Explicit `outputs.tables: csv` or `jsonl` selects the original interchange format and integer nanoseconds. Only the selected table format is produced.

Readable tables retain calculation names and units. Empty cells are not zero. Each metric independently reports `完整` (complete), `部分有效` (partial), or `无法确定` (indeterminate), with its reason. Inspect interval status separately from metric status. Global `has_unknown` does not invalidate a complete calculation within a known interval. For no events, inspect manifest `result_messages`; do not create a false zero-energy result. Preserve the original analysis time coordinates without inventing dates or shifting to zero. Do not duplicate seconds and nanoseconds. Python iterators such as `iter_events` and `iter_calculations` continue to return original typed rows.

<a id="独立批量的进程数"></a>
## Process count for independent batch tasks

Root-level batch `process_count` is a positive integer, default 1, limiting analysis worker processes. It excludes the scheduler and workers for requested exports. Ordinary ASC/BLF concatenation runs inside the analysis worker, without an additional pure-BLF reader subprocess. `run_batch(plan, output, process_count=4)` and CLI `--process-count 4` override it. Only the Python API accepts `None` to inherit the plan; configuration rejects null and Booleans. Call from a Python script inside `if __name__ == "__main__":`. Ordinary AnalysisRunner separately accepts a reading/decoding worker limit from execution.process_count. Continuous paths retain one analysis state and are not split into independent jobs.

Each task has its own budgets and output. Cancellation prevents tasks that have not started; in-flight tasks finish and close. `report.close()` can retry remote cleanup. Unstarted tasks and worker crashes are not successes. Legacy `workers`, `max_workers`, and `--workers` are rejected.

Python callers must also handle cleanup failures. An ordinary analysis error may expose `runner_cleanup_owner`; publication/result-close errors may expose `analysis_result_cleanup_owner`; a fast single-session error may expose `fast_session_cleanup_owner`. Keep the original exception, resolve the resource problem, and retry `close()` only on a recovery object that is actually present. Do not rerun calculations or delete staging still in use. Batch errors may carry `batch_report`; interruption during worker construction may also carry `batch_worker_cleanup_owner`, which may not belong to a report job and must be closed separately. Attributes are optional and may refer to objects closed by a later retry; their presence does not establish failure or success.

<a id="迁移数值与后端核对"></a>
## Numbers and backend comparisons

Both backends must agree on event boundaries, statuses, and diagnostics. Compare floating-point metrics using their unit and agreed error tolerance, without requiring bitwise equality or attributing event/quality differences to rounding.

Ordinary scalar calculations, including sample statistics, can return `coverage_status` when `minimum_coverage > 0`. It records the threshold decision, not a ratio, and does not change the equal weighting of `sample_mean`. Initial-edge `emit_initial` concerns the first known state, not an arbitrary first `True` anywhere in the analysis. A requested endpoint can produce a point event only when it is actually observed and satisfies the rule.

## Choose a version 4 expression

Write a unit-bearing constant as `quantity(500,'mV')` (0.5 V). Use `where` to select between branches: missing data on the unselected branch does not invalidate the result. For a calibration curve, use `lookup(voltage,'curve')` after checking both units and the points. Codes 7 and 9 can have the same label; request `enum_code(mode)` only if the distinction matters. In the calibration example, 3, 7 and 3 V map to 10, 30 and 10 W, giving a sample mean of about 16.67 W. Analysis configurations accept only integer version 4.

In version 4, a signal's `unit` specifies its target unit. Raw CAN input units can come from the DBC; for a decoded table, use `conversion.input_unit` when the input unit differs. For mA input and A output, omit both `conversion.scale` and `conversion.offset` to infer the conversion. If either coefficient is supplied, the other takes its existing identity default and the complete conversion is checked; DBC scaling is not applied again. Relabelling a result without converting its value is not a valid conversion. Task `UNITS` demonstrates conversion between input and target units; do not repeat a multiplier that can be inferred.
## Statistics: power variation and result populations

Establish what counts as one observation for this question. It can be one real power update, valid time held, a load, a final segment, or an already computed row. Sample statistics weight selected valid updates equally. Time statistics weight valid duration with known-true selection. Sample variance and standard deviation accept `ddof: 0` or 1, time versions accept only 0, and RMS omits `ddof`. Object counts reference named rules or windows. A known empty set can yield zero, while unobserved periods need an explicit status. Quantile takes `q`; median omits it. Exact interior quantiles use the run's memory budget.

In the bench task, P95 of five individual readings is 18 W. P95 of the two load means [10,20] W is 19.5 W. For a question about individual loads, calculate one value per activity and reference its calculation `value` from `aggregations`. For successful response delays, use `delay_ns` from the named `sequence`. Report candidates, inclusions, definition and quality exclusions, admitted partials and population discovery status. Exclude partial calculations by default. Use `include_partial: true` only if the requested population admits those values. Task ID: `POWER_STATISTICS`. [Runnable ASC/DBC example](../../Current/examples/power-statistics.yaml)

## Temporal transforms and host extensions

Ask for the actual timebase, TTL, output grid and clock policy. At a fixed/DBC grid tick between two real driver frames, wait for the later frame to determine fractional period weights and keep the original grid timestamp. adjacent_rate uses real value updates and actual max_gap. window_rate compares both boundary values; sample_fit_slope uses only real samples. Default strict warm-up returns unknown. Preserve partial quality in downstream results. For a registered operation ask for its host program, fixed ports, version and backend; run the host script with the same registry at plan load and execution. A YAML module path is never a registration mechanism.

## Choose a runner for continuous analysis

Start with `CONTINUOUS_FILES` for ASC/BLF volumes from one recording: one analysis configuration and one source preserve signal state, events and integration across file boundaries. Use ordinary analysis for duration conditions, cross-frame values, events/windows or actual-time integration. The duration-conditioned energy example uses `CONDITION_ENERGY`; splitting its recording into several files does not make it a fast task.

Choose `FAST_CONTINUOUS_SESSION` only when every signal input in a formula comes from the current message, each message provides an independently additive contribution, and none of the capabilities above are needed. Here `execution.process_count` limits read/decode/current-message workers and `file_merge` controls file organization. The main process accumulates in the prescribed order; file partial sums cannot replace ordered session accumulation. Separate trials use ordinary batch or fast `FAST_TEMPLATE_TOTAL` according to their analysis requirements; do not split a continuous session into independent trials.

Cancellation of `fast.run` raises `InterruptedError`. A managed memory budget is not a physical-memory limit for the whole process tree.
