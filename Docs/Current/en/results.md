# Understanding analysis results

<a id="读取分析结果"></a>

<a id="默认输出直接看区间和数值"></a>
<a id="默认输出-直接看区间和数值"></a>
## Default output: intervals and values together

Ordinary configurations can omit `outputs`. After running, open the CSV files with Chinese names. Calculations for the same event or window are already on one row, so you do not need to join IDs or convert nanoseconds yourself. Files use UTF-8 with a BOM for Windows spreadsheet software. Values are not rounded merely for display.

For example, the [conditional energy example](conditional-energy.md) produces one qualifying interval. These are the actual Chinese output headers and values:

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | energy_kwh（kWh） | energy_kwh：状态 | energy_kwh：说明 |
|---|---|---|---|---|---|---|---|
| 1 | eligible | 61 | 122 | 正常结束 | 0.06777777777777777 | 完整 | |

This reads: interval (`区间`) 1 for rule (`规则`) `eligible` starts at 61 seconds and ends at 122 seconds, with energy **0.06777777777777777 kWh**. `正常结束` means it ended normally; `完整` means this calculation is complete. The interval includes 61 and excludes 122: `[61,122)`. A whole-event integral does not also display confirmation time. `确认时间（s）` appears when requested event, window, pairing, or other results need it. Start/end remain actual times; no extra duration is calculated just for presentation.

| Requested result | Default file | How to read it |
|---|---|---|
| Session statistics | `会话结果.csv` | Session results: one row combines the session's metrics, each with its own unit, status, and explanation. |
| Events and event-scoped statistics | `事件结果.csv` | Event results: interval number, rule, and endpoints appear once; metrics follow across the row. |
| Windows and window-scoped statistics | `窗口结果.csv` | Window results: `父事件区间` refers to interval numbers in the event table; several numbers mean several parent events. |
| Request/response pairing | `配对结果.csv` | Pairing results: request/response numbers refer to the event table. Decision times and delays use seconds. |
| `select` details | `选择结果.csv` | Selection results: each update's value, unit, validity, and true/unknown selection state. |
| v4 result aggregations | `聚合结果.csv` | One row per group, with value, unit, candidate and included counts, and exclusions. Published filenames carry the run timestamp. |
| Explicitly requested contributions or input trace | `贡献明细.csv`, `输入追溯.csv` | Contribution details and input trace: requested locations and reasons. Ordinary runs do not produce them. |

Shared dataset, entity, and session names are stored once in the publication manifest under `presentation.common_identity`. Identity columns are added to tables only when several values occur. Interval numbers are local to this output and cannot join separate runs. Signal CSV and ASC/BLF exports retain their own data formats rather than these Chinese result-table layouts.

Time columns use exact decimal seconds, such as `922.346858001`, preserving nanosecond precision. They retain the analysis origin instead of resetting at the first result or inventing a date/timezone. Absolute coordinates also retain their actual numerical meaning; a timestamp lacking a date cannot be interpreted as a clock time on an assumed day.

Read each metric's own status. `完整` means complete, `部分有效` means only the calculable portion is included, and `无法确定` means no usable number can be given. A blank cell is not zero. `数据中断` (data interruption) differs from `观测结束，活动尚未确认结束` (observation ended before the activity was confirmed to have ended). Explanation columns turn quality flags such as missing, stale, or decode error into text; a blank explanation does not establish real-world input correctness.

When no event exists, the output keeps an empty table and a manifest `result_messages` entry, for example `条件曾成立，但持续时间不满足要求` (“the condition occurred, but did not meet the duration requirement”). It does not fabricate a zero-energy row. A rule may encounter unknown periods while still producing a complete calculation for a particular event. One missing metric does not change the status of the others.

<a id="v4-aggregations"></a>
## Read aggregation results

See [result aggregation](aggregations.md) for configuration, sources, and grouping. The readable aggregation table lists name, group, value, unit, status, reason, and candidate/included/excluded counts. Candidates equal included plus definition-excluded plus quality-excluded rows. These counts do not measure time coverage.

included_partial_count counts the included partial values. Pairing counters matched_count, timeout_count, insufficient_observation_count, and pending_count distinguish successful, confirmed-timeout, insufficient-observation, and unresolved requests. discovery_complete states whether observation can establish that all candidates were discovered; it does not merely mean the available numbers are complete.

Read status, reason, and quality together. In the power example, load_mean_p95 is 19.5 W with two candidates and two included values. See [the actual output](example-results.md#power-statistics-yaml).

## Choose an exchange format for other software

The default is `readable_csv`; it need not be written. If another program requires the original flat fields, add this root fragment. If `outputs` already exists, add `tables` inside it instead of adding another root block.

```yaml
outputs:         # Additional result files to publish
  tables: csv    # Original flat fields with integer nanosecond times.
```

The only choices are `readable_csv`, `csv`, and `jsonl`. `csv` writes the original `events.csv`, `calculations.csv`, and related tables. `jsonl` writes corresponding line-delimited JSON records containing `row_schema_version` and `row`. One selected format produces one set of results, not readable and exchange copies together.

Python methods such as `iter_events` and `iter_calculations` always return the original typed rows regardless of file format. The low-level `AnalysisResult` constructor still defaults to `csv`; `AnalysisRunner` follows the plan's `readable_csv` default.

Readable export processes already computed results without rereading logs. Because event and metric sort orders differ, it may create a temporary join index, constrained by memory/disk budgets and removed before publication. This adds export work; measure its cost for large outputs. Detail-only outputs are written directly without that index.

The remaining field descriptions apply to explicit `csv`/`jsonl` and typed APIs. For actual files and commands associated with each complete configuration, see [Example results](example-results.md). Configuration and result files have different structures.

An ordinary calculation row directly contains `calculation_id`, `operation`, `scope`, `value`, `unit`, `status`, `reason`, and `quality`, plus dataset/entity/session identity, parent event or segment, and sequence. Access attributes directly, such as `row.value`.

Unless stated otherwise, timing examples below use default `actual` intervals. With `fixed` or `dbc`, confirmation durations, waits, change windows, and pairing `delay_ns` use the chosen period basis. Original time coordinates and signal expiry still use actual record time. See [Timing bases compared](intervals.md#timing-basis).

| Table / API | What each row answers |
|---|---|
| `calculations` / `iter_calculations` | Value, unit, coverage decision, and quality of a calculation in a session, event, or segment. |
| `events` / `iter_events` | Which rule started, was confirmed, and ended at which times, with its status and trigger. |
| `segments` / `iter_segments` | Which window produced which range, and its associated events. |
| `sequences` / `iter_sequences` | Which request matched which response, decision time, and delay. |
| `selections` / `iter_selections` | Explicitly selected sample time, value, type, unit, and validity. |
| `input_trace` / `iter_input_trace` | Input location and record kind when detailed tracing was requested. |
| `contributions` / `iter_contributions` | Per-message contribution or skip reason when `outputs.contributions=full`. |

Calculations return `SummaryCalculationRow` or `SummaryCoverageCalculationRow` with `coverage_status`, according to the operation. Ordinary `integral`, `duration`, `min_time`, `max_time`, `time_weighted_mean`, `sample_minimum`, `sample_maximum`, `sample_mean`, and v4 sample counts, variance, standard deviation, RMS and sample quantiles include `coverage_status` when `minimum_coverage > 0`. `sufficient` means the required observation, valid-value, and known-condition ranges meet the threshold; `indeterminate` means they do not, or cannot be determined. This is not a numerical coverage ratio and does not turn sample statistics into time-weighted statistics. Select details and per-message sums are outside this scalar group. An explicit zero or omitted threshold does not add the field.

Full fields are listed in [Summary row models](../reference/chronaxis.results.summary.md) (Chinese implementation reference). Matching CSV and JSONL fields represent the same facts. Exchange CSV includes a timestamped run manifest; JSONL rows include a version and row object. The manifest records the run and tables actually written. Readable `row_counts` count rows after presentation joins. A configuration hash is not an input-content hash and cannot prove two runs used identical data.

<a id="result-publication"></a>
<a id="结果怎样发布"></a>
## How results are published

The output directory can be reused. Every publication uses one local-time suffix, such as `20261103_091500_123456`, for its tables, manifest and requested export directory. A numeric suffix resolves same-time or concurrent collisions. This naming time does not change message times, interval boundaries or energy values. Existing files are never overwritten, and unrequested outputs are not created.

Files are written and closed in temporary storage, then published individually; the completion manifest is published last. Treat a set as complete only when its manifest exists and reports `completed`. Normal failure cleanup touches only files owned by this publication. An abrupt process termination or power loss may leave files without a completion manifest; they are not completed outputs and subsequent runs do not scan or delete them. The result-publication procedure on this page has been verified on Windows; equivalent verification on other platforms is still pending.

Use `manifest` in the CLI summary or `OutputManifest.manifest_path` from Python, then read the manifest's `outputs` list. Do not construct a fixed `run_manifest.json` path or pick an arbitrary/latest CSV from a shared directory. An open `AnalysisResult` can be published again to the same or another directory without rereading input. An explicit `work_dir` must still be new.

Names such as `事件结果.csv` and `会话结果.csv` in this chapter describe file purposes; actual publications insert the suffix before the extension. Saved teaching results retain their original filenames, so their download links do not imply fixed filenames for new runs.

<a id="缺失不是零"></a>
## Missing is not zero

When `value` is empty, inspect `status`, `reason`, and `quality`. Invalid updates replace previous valid values; expiry makes a value unknown. Gaps are not filled with zero. `minimum_coverage` checks a coverage requirement. `partial_policy=report` retains a defensible partial value, while `strict` rejects insufficient coverage under the operation's rules. Neither policy makes unobserved time known.

<a id="用实际输出理解partial"></a>
### A concrete partial-result example

In [analysis.yaml](../examples/analysis.yaml), explicitly set `power.valid_for` to `1s`, overriding the 3-second default inferred from the DBC's 1-second period, and set the energy calculation's `partial_policy`. Keep the input and `[0,6)` range unchanged. Power expires without a replacement in `[2,3)` and `[5,6)`, leaving four calculable seconds:

**2 W × 1 s + 4 W × 1 s + 8 W × 1 s + 10 W × 1 s = 24 J.**

| `energy.partial_policy` | `value` | `status` | `reason` | Interpretation |
|---|---|---|---|---|
| `report` | 24.0 | `partial` | `partial_coverage` | Energy for the four known seconds, not a total for all six seconds. |
| `strict` | Empty | `indeterminate` | `insufficient_coverage` | Insufficient data for a value over the requested complete range; do not replace the blank with zero. |

Both rows include `STALE` in `quality`. Check actual update patterns, timestamps, and missing records before changing `valid_for`; do not extend validity solely to remove `partial`. `complete` means the calculation met its requirements; `partial` retains a usable portion; `indeterminate` cannot provide a value under the chosen policy/evidence. The individual `reason` supplies the cause.

<a id="事件与配对"></a>
## Events and pairing

Event `start_ns` is activity start, `confirmed_ns` is when its confirmation requirement was reached, and `end_ns` is the end or empty. Every `_ns` field is integer nanoseconds, not a floating-point count of seconds.

Pairing rows directly provide `request_id`, `response_id`, `decided_ns`, `delay_ns`, and `status`. `matched` means a response was found. `no_response` means the full waiting interval was observable and no response occurred. `indeterminate` means missing data or early observation end prevents a no-response conclusion. No request means no pairing row.

<a id="quality-flags"></a>
<a id="quality把数字还原为质量原因"></a>
<a id="quality-把数字还原为质量原因"></a>
## Decode numerical quality flags

CSV/JSONL `quality` is an integer bit mask that can combine causes. It is neither a severity score nor one error number. Zero means none of these flags was recorded; still inspect `status`, `reason`, or `valid`. For example, missing a right interpolation endpoint can have `quality=0`, `status=missing`, and `reason=missing_right`.

| Value | Name | Meaning and what to check |
|---|---|---|
| 1 | `MISSING` | Required observation/value absent; check input columns and missing markers. |
| 2 | `STALE` | Latest value exceeded `valid_for`; check real update intervals and lost frames. |
| 4 | `DECODE_ERROR` | Source decoding error; check DBC and frame structure. |
| 8 | `NONFINITE` | NaN or infinity; check input values. |
| 16 | `OUT_OF_RANGE` | Outside an allowed range or code mapping; check range and choices. |
| 32 | `ESTIMATED` | Estimated value; the base signal quality policy does not treat it as an actual valid observation. |
| 64 | `OVERFLOW` | Arithmetic exceeded the numerical range; check magnitudes and expression. |
| 128 | `PRECISION_LOSS` | Conversion cannot represent the value exactly; check integer size and target type. |
| 256 | `DOMAIN_ERROR` | Mathematical domain error such as division by zero; check the formula. |

For example, `3 = 1 + 2` combines `MISSING` and `STALE`. Test `quality & 1` for missing, not `quality == 1`, which would overlook 3. Python can use the enum directly:

```python
from chronaxis.core.types import QualityFlag
quality = QualityFlag(3)  # Convert CSV text with int first; unknown bits/negative values raise ValueError.
names = [flag.name for flag in QualityFlag if quality & flag]
print(names)             # ['MISSING', 'STALE']
```

The runnable [quality.yaml](../examples/quality.yaml) uses synthetic [quality.asc](../examples/data/can/quality.asc) and [teaching.dbc](../examples/data/can/teaching.dbc). Power is 10 W at 0 seconds, decodes as `-1e100` at 1 second, and returns to 10 W at 2 seconds. A message without Power arrives at 4 seconds and ends observation. The configuration lists `-1e100` in `invalid_values` and uses `valid_for: 1s`.

Only `[0,1)` and `[2,3)` can be integrated, giving **20 J**, `status=partial`, and `reason=partial_coverage`. `quality=18` combines `OUT_OF_RANGE` (16), from the explicit invalid code in `[1,2)`, with `STALE` (2), after the recovered value expires in `[3,4)`. The invalid update replaces the previous valid value. No zero or invalid carried-forward value is used. Run `chronaxis run quality.yaml --output quality-result` from the example directory. The earlier `quality=3` illustrates bit-mask reading; it is not this example's output.

<a id="result-status"></a>
<a id="各种结果的状态字段"></a>
## Status fields differ by result type

Do not assume every row has `status` and `reason`. Identify the row type first. The model links below are Chinese implementation references with complete fields and constraints.

| Result | Fields and meaning | Model |
|---|---|---|
| Ordinary/per-message summary | `status=complete/partial/indeterminate`; `reason` explains why. | [SummaryCalculationRow](../reference/chronaxis.results.summary.md#api-SummaryCalculationRow) |
| Calculation with coverage threshold | Adds `coverage_status=sufficient/indeterminate`, a threshold decision rather than a numerical ratio. | [SummaryCoverageCalculationRow](../reference/chronaxis.results.summary.md#api-SummaryCoverageCalculationRow) |
| Event | `point`: point event; `closed`: normal end; `interrupted`: interrupted by unknown; `truncated`: observation ended; `timeout`: timed out. `trigger` identifies the trigger. No `reason` column. | [SummaryEventRow](../reference/chronaxis.results.summary.md#api-SummaryEventRow) |
| Window segment | `complete/partial/empty`; `empty` has no actual endpoints. No `reason` column. | [SummarySegmentRow](../reference/chronaxis.results.summary.md#api-SummarySegmentRow) |
| Request/response | `matched/no_response/indeterminate`; no `reason` column. Also read quality and linked events. | [SummarySequenceRow](../reference/chronaxis.results.summary.md#api-SummarySequenceRow) |
| Selection | `valid` describes value validity; `selection=true/unknown` describes the condition. No `status` or `reason`. | [SummarySelectionRow](../reference/chronaxis.results.summary.md#api-SummarySelectionRow) |
| Message contribution | `reason=contributed`, `missing_input`, `condition_false`, `evaluation_error`, or `nonfinite_input`. No `status`. | [SummaryContributionRow](../reference/chronaxis.results.summary.md#api-SummaryContributionRow) |
| Interpolated signal export | `observed/estimated/missing`; a reason such as `missing_right` identifies the unavailable endpoint. | [Signal exports](signal-exports.md) |

For contribution reasons, `contributed` means counted, `missing_input` means an input is missing, `condition_false` means the directional condition did not match, `evaluation_error` means expression evaluation failed, and `nonfinite_input` means an input is not finite.

Ordinary time calculations use these reasons; not every empty value means missing input:

| `reason` | Meaning | What to do |
|---|---|---|
| `ok` | Calculation meets current requirements. | Read alongside unit, scope, and quality. |
| `partial_coverage` | `report` retained the available portion. | Check missing ranges; do not present it as a full total. |
| `insufficient_coverage` | `strict` rejected insufficient coverage. | Supply data or reconsider the actual business acceptance requirement. |
| `zero_length_window` | Window has zero duration. | Check endpoints and event. |
| `no_observation` | No observation. | Check inputs and requested range. |
| `calculation_failed` | Numerical calculation failed. | Decode quality and check formula/range. |
| `empty_selection` | Condition was decidable but selected nothing. | Integral/duration may be zero; means are not fabricated as zero. |
| `unknown_selection` | Selection condition could not be decided. | Check missing or stale condition signals. |
| `no_samples` / `no_valid_selected_data` | No samples/valid selected data for the requested operation. | Check sample selection, type, and quality. |

<a id="result-relationships"></a>
<a id="用实例id关联三张结果表"></a>
## Join result tables by instance ID

A rule named `hot` may produce many events. `rule_id=hot` identifies the definition, not one occurrence. Join `event_id` and `segment_id` within the same run directory. Do not join by row order or by `sequence` alone.

The following comes from an actual run of [activity.yaml](../examples/activity.yaml). E1 and S1 are display abbreviations here; actual fields contain the full strings. Read IDs from your own output rather than hard-coding these:

- E1 (`event_id`): `3d7375484e46c0da41755d73629db92c3f87b98da58891b2c238c5a6517b848f`
- S1 (`segment_id`): `127695a43e932e2ceeb70f0319294829572ba84c9af8fb793e9b41eb40013de9`

| Table | Definition name | Instance / parent | Value |
|---|---|---|---|
| `events` | `rule_id=hot` | `event_id=E1` | Start 1 s, confirmed 3 s, end 6 s. |
| `segments` | `window_id=hot_context` | `segment_id=S1`, `parent_event_ids=[E1]` | `[0,7)` seconds. |
| `calculations` | `calculation_id=event_energy` | `scope=event`, `parent_id=E1` | 50 J. |
| `calculations` | `calculation_id=context_energy` | `scope=segment`, `parent_id=S1` | 70 J. |

A merged window can belong to several events, so `parent_event_ids` is a list. Session calculations have `parent_id=None`, an empty CSV cell, or JSONL `null`.

Run this fragment while `AnalysisResult` remains open. It is only suitable for result sets that fit in memory; [activity_relationships.py](../examples/activity_relationships.py) includes the full close lifecycle.

```python
events = {row.event_id: row for row in result.iter_events()}
segments = {row.segment_id: row for row in result.iter_segments()}
for row in result.iter_calculations():
    if row.scope == "event":
        event = events[row.parent_id]
        print(event.rule_id, event.start_ns, row.value, row.unit)
    elif row.scope == "segment":
        segment = segments[row.parent_id]
        parent_events = [events[event_id] for event_id in segment.parent_event_ids]
        print(segment.window_id, len(parent_events), row.value, row.unit)
    else:
        print("session", row.value, row.unit)
```

For large results, use a database or bounded index keyed by full IDs rather than materializing every row. When combining runs, also retain run identity or directory so occurrences from different runs do not mix.

<a id="独立导出"></a>
## Additional exports

Signal CSV and CAN frame exports are explicitly requested through `outputs`, with their actual timestamped index and directory recorded in this run’s manifest as `exports.index_file` and `exports.directory`. Original and interpolated signal values use separate files. Reconstructed CAN frames are distinguished from original input frames. Export grids do not change integration intervals; see [Outputs](exports.md).

<a id="metadata-output"></a>
<a id="运行清单的摘要与详细字段"></a>
## Summary and detailed run metadata

`RunMetadata` stores run information; `to_dict()` selects what is serialized. Default `detailed_diagnostics=False` writes `run_id`, `plan_hash`, `backend`, `config_version`, `started_at`, `device_label`, `software_version`, `source_time_interpretation`, `parsing_policy`, `worker_config`, `retain_work`, and `detailed_diagnostics`. Input identities, session boundaries, limitations, and other conditional fields appear when their conditions apply. Trace/integrity add their corresponding diagnostics.

| Model content | Default summary serialization | `detailed_diagnostics=True` |
|---|---|---|
| A signal definition in `signal_bindings` | No `signal_bindings` key. | Expands that definition. |
| Preset bindings or CAN source details | Nonempty values are not automatically emitted. | Uses detailed serialization branches; empty optional fields may still be omitted. |

A missing detailed key does not prove the model never held that information. Check the serialization mode before indexing optional keys. The public runner creates summary metadata. Configuration `diagnostics` accepts only `trace`, `integrity`, and `retain_work`; it has no `detailed` or `detailed_diagnostics` switch. The table describes a model serialization branch, not a promise that the public runner populates every field. See [Execution](execution.md).

The public runner currently leaves `metadata.can_sources` and `metadata.text_can_sources` as empty tuples. Those fields can receive explicitly supplied caller details; their names do not imply they will be populated after a run. Use supported diagnostics for actual input checks. Converting metadata to detailed mode cannot recreate absent details.

<a id="为什么运行成功却没有事件"></a>
## Why a successful run can have no events

Command completion means no execution error occurred. CLI `analysis_outcome` and manifest `run.analysis_outcome` describe the business outcome. In Python, read `result.metadata.analysis_outcome.to_dict()`. The summary is accumulated during existing work without another input scan.

| Rule outcome | Meaning and checks |
|---|---|
| `no_observation` | Required observations were absent. Check input, channel, ID, and signal; `unobserved_signals` lists unseen signals. |
| `insufficient_data` | Observations exist, but unknown/invalid intervals prevent a decision. Check missing values, invalid codes, and validity periods. |
| `condition_not_met` | Decidable data exists, but the condition never held. |
| `duration_not_met` | The condition held but did not meet the selected duration requirement. |
| `events_found` | Events were generated. Inspect calculation statuses; this does not imply all data was complete. |
| `no_event` | Another rule produced no event, for example because the required edge never occurred. |

`event_count` counts actual events. `has_unknown` records that the rule encountered unknown state and can coexist with generated events. Under `calculations`, `complete`, `partial`, and `indeterminate` count written rows; `no_observation` counts the subset with no observations, not a fourth mutually exclusive status. The summary helps locate a problem and does not replace row-level `reason` and `quality`.

Event endpoints and energy are related through `event_id` / `parent_id`; each calculation row does not duplicate event timestamps. See [Integrate after a condition lasts more than 60 seconds](conditional-energy.md).
