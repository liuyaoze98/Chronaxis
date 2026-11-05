<a id="时间与结果质量"></a>
# Time and result quality

These meanings apply across analysis features. `dataset.domain` selects the requested time range, `signals[].valid_for` controls how long a previous value remains usable, and `execution.partial_policy` or the calculation-level field controls partial results. Use this page before configuring [signals](signals.md), [rules](rules.md) and [calculations](calculations.md).

<a id="时间范围和观测范围"></a>
## Requested and observed ranges

`dataset.domain` is the range you ask to analyze. The observed range is where data was actually recorded. A request for `[0,12)` with a log ending at 8 s cannot establish results for the final four seconds.

`[0,1)` means from 0 s inclusive to 1 s exclusive: a duration of one second. The next interval `[1,2)` therefore does not count the boundary twice.

A button transition exactly at the requested endpoint may produce a point event only when there is an actual observation at that time and the rule's trigger conditions hold. The request ending does not itself produce an event. A point event has a timestamp and no end (`end_ns` is null); it is not a one-nanosecond activity. Continuous durations use half-open intervals.

Internally, time uses integer nanoseconds: one second is 1,000,000,000 ns. Conversion records rounding when input is finer than nanoseconds. Converting to integers cannot recover precision already lost in a floating-point timestamp.

<a id="信号有效期"></a>
## Signal validity periods

Suppose current is 10 A at 0 s and `valid_for="2s"`. Without an update, it may remain 10 A before 2 s, provided the source actually records that range; at 2 s it expires. If observations end at 1 s, validity does not create data for 1–2 s. An explicitly invalid update at 1 s invalidates the value immediately, rather than preserving the old value. An empty CSV cell is also an invalid update.

Keep original field names, expression aliases and semantic identifiers separate. Bind `BMS_BatCurr` to `current`, then write `current > 5`. Optional `semantic_id="battery.current"` is a meaning label; `battery.current > 5` is rejected as an expression. Ordinary analyses do not require a semantic catalog.

<a id="条件表达式"></a>
## Condition expressions

`current > 5 and mode == 1` means current exceeds 5 A and mode equals 1. Define both names under `signals`; an unbound input column cannot be referenced directly.

The [expression guide](expressions.md) lists all supported operators and the functions available in each configuration version: unary signs, four arithmetic operations, six comparisons, `and/or/not`, chained comparisons, parentheses, constants, enums, and type/unit restrictions. This page explains how those values behave over time.

<a id="unknown不是false"></a>
## UNKNOWN is not False

When inputs are invalid, the condition's truth is unknown (`UNKNOWN`). `False and UNKNOWN` is known False; `True or UNKNOWN` is known True; `True and UNKNOWN` remains unknown. Quality reasons are retained.

If a device is known to run at 1 s but its status is missing at 2 s, that is an interruption (`interrupted`), not a known stop (`closed`). A rising edge requires known False followed by known True. Unknown followed by True is not normally such an edge. `rising_edge` and `start_only` can use `emit_initial` to emit an event when the first known state of the analysis is True; it does not create an initial falling edge. Initial unknown followed by the first known True qualifies. Once False has already been observed, a later unknown-to-True change is neither an initial state nor evidence of a known False-to-True edge.

<a id="活动-点事件和上下文片段"></a>
<a id="活动点事件和上下文片段"></a>
## Activities, point events and context segments

| Rule/object | Behavior |
|---|---|
| `condition_duration` | True from 1 s with `minimum_duration="3s"` is confirmed at 4 s. Energy may include or exclude the waiting three seconds; see [selection_origin](rules.md#duration-selection-origin). |
| `rising_edge` / `falling_edge` | Record the instant of a known False-to-True or True-to-False change. A transition at 2 s records that point, not how long the state persists. |
| `start_only` | After a button press, take five seconds of data and ignore presses during that interval. A button still held after five seconds does not automatically retrigger. |
| `Event` | An activity's start, confirmation, end and reason, or a point trigger time. |
| `Segment` | The range selected around events, such as one extra second before and after an activity. `parent_event_ids` identifies related events. |

If a device runs during 0–1 s, stops during 1–2 s, and runs during 2–3 s, a rule with no confirmation delay records two activities.

To inspect three seconds after each stop, set window `exit_delay="3s"`. Because the second activity starts during that wait, both can occupy one segment covering 0–6 s. The event table still contains two activities. The one-second stop is included in the segment but is not converted into activity time.

<a id="统计方式"></a>
## Statistics

Sample means and time means use different weights. Ordinary integration and per-message accumulation also use different time bases. See [statistics and integrals](calculations.md) for selection, formulas and coverage thresholds.

<a id="0-空值和partial分别代表什么"></a>
<a id="0空值和partial分别代表什么"></a>
## Zero, null and partial results

| Situation | Result |
|---|---|
| Complete observations establish that the condition is always False | Conditional integral and selected duration are 0. `min/max/mean` are null because no samples were selected. |
| 1000 W with a True condition for one second, followed by one second of unknown condition | Under `report`, the verifiable result is 1000 J with status `partial` and a reason. The public summary has no numeric coverage ratio. Under `strict`, the value is null. |
| Entirely unknown condition, no observations, or a zero-length request | Do not report a normal zero; retain the specific reason. |
| Valid positive and negative contributions cancel to zero | A valid numeric zero, distinct from missing data. |

`partial_policy="report"` keeps the known part; `"strict"` withholds the number when required data is incomplete. `minimum_coverage` specifies the minimum coverage required by the user; it cannot fill missing data. See [execution settings](execution.md) for numeric comparisons. Read `value`, `unit`, `status`, `reason` and `quality` together.

Ordinary scalar `integral`, `duration`, `min_time`, `max_time`, `time_weighted_mean`, `sample_minimum`, `sample_maximum`, `sample_mean`, and v4 sample counts, variance, standard deviation, RMS and sample quantiles return `coverage_status` when `minimum_coverage > 0`. `sufficient` means observation, valid-value and known-condition coverage all meet the threshold; `indeterminate` means insufficient or undetermined. This is not a numeric coverage ratio and does not turn sample statistics into time-weighted statistics. `select` details and per-message accumulation are not in this scalar group. Public summaries do not expose numeric `requested_coverage`, `value_coverage` or `condition_coverage`. See the [implementation summary reference (Chinese)](../reference/chronaxis.results.summary.md).

<a id="时间积分与逐消息累计的区别"></a>
## Time integration versus per-message accumulation

Actual-time integration uses elapsed time. `legacy_sum` adds each matching message's expression result. If the expression already contains `power * period`, 4000 W × 0.1 s is 400 J and two messages at the same timestamp still contribute 800 J; do not multiply by dt again. Messages with missing values are skipped with a reason, without borrowing the previous value. See [per-message calculations](message-calculations.md).
