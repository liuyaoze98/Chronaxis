<a id="计算间隔"></a>
# Calculation intervals

Omit `intervals` to use actual elapsed time. Set the root `intervals` or a node's `interval` only when you need a fixed period or the period declared in a DBC. This selects the duration used for accumulation and waiting. Record timestamps and signal expiry still use actual time, but confirmation, timeout, window triggers, and pairing `delay_ns` can change.

For three 4000 W power records at 0, 0.12, and 0.30 seconds, actual intervals give 4000 × (0.12 + 0.18) = 1200 J. Fixed 100 ms intervals give 4000 × (0.1 + 0.1) = 800 J. A DBC period of 100 ms gives the same 800 J. Three records form two intervals: the first establishes the starting point.

Write durations as `"0.1s"` or `"100ms"`. Internal times and API/exchange-format fields ending in `_ns` use integer nanoseconds; 100 ms is 100000000 ns. Default readable result tables use seconds. Input timestamps expressed in seconds do not need manual conversion.

<a id="完整最小例与单项覆盖扩展"></a>
## Complete minimal example and a per-calculation override

[interval-actual.yaml](../examples/interval-actual.yaml) omits `intervals` and returns 1200 J. [interval-fixed.yaml](../examples/interval-fixed.yaml) also omits global `intervals`, but gives the `energy` calculation a fixed 100 ms interval and returns 800 J. Both define `power` and use the same three records. Run either with `chronaxis run filename.yaml --output results`.

<a id="一个完整的最小例子"></a>
## A complete minimal configuration

The following synthetic input and expected energy can be checked by hand. Save this complete root-level configuration as `energy.yaml`; do not wrap it in another key. The result directory can be reused; files receive a timestamp suffix.

```yaml
config_version: 4        # Current analysis configuration version
dataset:                 # Dataset settings.
  name: demo             # Name included in result identity.
sources:                 # Input sources.
  - source_type: memory  # Synthetic records supplied in the configuration.
    rows:                # Each record supplies a timestamp and updated values.
      - time: 0s         # First observation.
        values:          # Original input field names.
          p: 4000        # Power value; its type and unit are defined below.
      - time: 0.12s      # Second observation.
        values:          # Values updated at this timestamp.
          p: 4000        # Same power.
      - time: 0.3s       # Third observation.
        values:          # Values updated at this timestamp.
          p: 4000        # Same power.
signals:                 # Named analysis signals.
  - name: power          # Name used in expressions.
    field: p             # Original input field.
    dtype: float64       # Numeric type for analysis.
    unit: W              # Target analysis unit; compatible registered units convert when scale/offset are omitted.
    valid_for: 1s        # Maximum age of a valid update.
calculations:            # Requested results.
  - name: energy         # Calculation name.
    operation: integral  # Accumulate power multiplied by duration.
    expr: power          # Signal to integrate.
intervals:               # Duration basis; original timestamps remain intact.
  default:               # Default for nodes without their own override.
    mode: fixed          # actual, fixed, or dbc.
    value: 100ms         # Duration assigned to each driver interval.
execution:               # Execution settings for this analysis
  process_count: 1       # Memory input runs in one process
```

Run `python -m chronaxis run energy.yaml --output work/energy-v2-result`. The result directory can be reused. The `energy（J）` value in `会话结果_<run timestamp>.csv` should be 800. Remove the entire `intervals` object to obtain 1200 J using actual time. Only raw CAN inputs can use `mode: dbc` without `value`; requesting `dbc` for this memory example fails instead of silently substituting a fixed period.

<a id="intervals的全部字段"></a>
## All interval fields

`intervals` is optional and contains only `default`. Omission means `actual`. Put a local override in a rule, sequence, window, calculation, or time-series transform's own `interval` object; there is no name-indexed `overrides` mapping. This setting does not control input batch sizes or enable export resampling.

| Field | Type | Required | When omitted | Meaning |
|---|---|---|---|---|
| `default` | Object | No | `mode: actual` | Task-wide duration basis for the time-dependent nodes described below. |

The next fields belong inside an interval object. Their global paths are `intervals.default.mode`, `.value`, and `.driver`; local paths are under `rules[].interval`, `windows[].interval`, `sequences[].interval`, `calculations[].interval`, or `transforms[].interval`. Do not write `intervals.mode`.

| Field within the interval object | Type | Required | When omitted | Meaning |
|---|---|---|---|---|
| `mode` | String | Yes when the object is present | No default within an explicit object | `actual`: actual time difference. `fixed`: assign `value` to each driver interval. `dbc`: read `GenMsgCycleTime` from the driver's DBC message. This selects a duration basis, not a file format. |
| `value` | Positive duration string with unit | For `fixed` | No default | Duration per driver interval, such as `100ms`. It must convert to positive int64 nanoseconds. Zero and `null` are invalid. Forbidden for `actual` and `dbc`. |
| `driver` | Original signal name | For `fixed`/`dbc` when there are zero or multiple candidates | Automatically selected when exactly one physical update source exists | A defined `signals[].name` whose updates advance the period. With current every 10 ms and voltage every 100 ms, `current` advances on current updates. Constant expressions have no candidate and need an explicit clock signal. Derived names, expressions, and `null` are invalid. Forbidden for `actual`. |

In `energy.yaml`, remove the root `intervals` and replace `calculations` with this fragment to override only `energy`. Other nodes use actual time.

```yaml
calculations:            # Requested results.
  - name: energy         # Calculation name.
    operation: integral  # Accumulate power multiplied by duration.
    expr: power          # Previously defined signal.
    interval:            # Override the task-wide duration basis for this node.
      mode: fixed        # Advance once per driver interval.
      value: 100ms       # Duration assigned to each interval.
```

`power` is the only candidate, so `driver` can be omitted. When several candidates exist, choose one explicitly. A separate original clock signal is also allowed if its time basis is comparable to the expression inputs. Two aliases of the same physical message count as one candidate. Other formula inputs still update and undergo validity checks even when they are not the driver.

Sample minimum, maximum, and mean; `select`; and pure rising/falling edges do not use intervals. Setting a local interval on them is an error.

Per-message accumulation (`legacy_sum`) adds each target message's `expr` result directly; it does not use the duration selected by `intervals`. To obtain energy from power, include a time parameter in the expression, such as `power * period`, and define it in `parameters`. Here `period` is a user-chosen example name, not a required parameter name. If each message already contains an energy contribution, add it directly without multiplying by time again. See the [complete per-message field reference](message-calculations.md#message-fields).

<a id="实际起止时刻不改累计采用选定的周期"></a>
<a id="实际起止时刻不改-累计采用选定的周期"></a>
## Keep actual event timestamps and accumulate the selected period

An alarm starts at 10.00 s, has another record at 10.12 s, and clears at 10.30 s. Fixed 100 ms intervals give a duration of 0.2 s. Its actual start and end remain 10.00 and 10.30 s; the program does not save an extra rewritten timeline.

If confirmation requires 0.2 s, fixed/DBC mode waits for the third selected message and confirms at 10.30 s. It does not accumulate periods while no new messages arrive. Actual mode can confirm when real time reaches the deadline. Request/response delays, timeouts, entry/exit waits, and window changes each use their selected basis. State carries across continuous input files; a file boundary does not itself end an alarm.

For an event at 10.12 s with 0.1 s before and after, fixed 100 ms mode selects the preceding record at 10.00 s and the following record at 10.30 s, yielding the actual range 10.00–10.30 s. Actual mode extends by 0.1 s on the log timeline. Raw-frame export uses the resulting actual range and does not rewrite frame timestamps.

When a selection cuts through an interval, distribute the selected period by the fraction of actual-time overlap. Two 4000 W records at 10.00 and 10.12 s with a 100 ms period contribute 200 J to 10.06–10.12 s: 4000 × 0.1 × 0.5.

<a id="信号是否过期仍看真实时间"></a>
<a id="信号是否过期-仍看真实时间"></a>
## Signal expiry uses actual time

Voltage updates only at 0 s and remains valid for 150 ms; current arrives at 0 and 180 ms. Even if each current interval contributes 100 ms, the old voltage is expired at 180 ms. Depending on `partial_policy`, the affected calculation returns the known portion or a null value and marks missing data. It does not substitute zero or fill the gap when voltage later returns.

Structurally damaged input remains an error. If a required message is structurally valid but DBC decoding fails or a required value is absent, the default behavior marks that update invalid and continues, replacing the previous valid value. Unrelated frames receive only the reading and checks actually required by the task; all-source timestamps are processed only when the task needs the complete observation range.

<a id="dbc周期的适用来源"></a>
## Inputs that support a DBC period

BLF, ASC, and raw CAN CSV support DBC periods. Decoded CSV and memory inputs support `actual` and `fixed`, but not `dbc`. The period is resolved once during initialization. A missing, invalid, or ambiguous period produces an error rather than falling back to actual time.

See [CAN input policy](inputs.md#decode-policy), [diagnostics](execution.md#diagnostics), and [configuration tools](configuration-tools.md) for decoding, input evidence, retained files, conversion, and source lookup. These features are separate from `intervals`.

<a id="timing-basis"></a>
<a id="同一输入采用三种时间依据"></a>
## Compare all three duration bases on the same input

Actual mode uses elapsed time. Fixed mode advances one configured period per selected driver update, and DBC mode uses the driver's declared message period. All three retain actual log coordinates in event timestamp fields. The basis for deciding whether enough time has passed differs, so confirmation times and results can differ.

Use [timing.asc](../examples/data/timing.asc) and [timing.dbc](../examples/data/timing.dbc), whose message period is 1000 ms, with the [actual](../examples/timing-actual.yaml), [fixed](../examples/timing-fixed.yaml), or [DBC](../examples/timing-dbc.yaml) configuration. Run from the examples directory:

```powershell
chronaxis run timing-actual.yaml --output timing-actual-result
chronaxis run timing-fixed.yaml --output timing-fixed-result
chronaxis run timing-dbc.yaml --output timing-dbc-result
```

| Actual time (s) | Request | Response | Temperature (degC) | Voltage (V) |
|---|---|---|---|---|
| 0 | 0 | 0 | 70 | 0 |
| 1 | 1 | 0 | 80 | 1 |
| 3 | 0 | 1 | 80 | 5 |
| 6 | 0 | 0 | 70 | 10 |
| 7 | 0 | 0 | 70 | 10 |

| Check | `actual` | `fixed=1s` / `dbc=1000ms` |
|---|---|---|
| Request / response timestamps | 1 s / 3 s | 1 s / 3 s |
| Pairing `decided_ns` | 3000000000 | 3000000000 |
| Pairing `delay_ns` | 2000000000: 2 actual seconds | 1000000000: one driver interval |
| Accumulated duration with temperature >= 80 | 5 s | Two driver intervals: 2 s |
| `hot` requires 1.5 s; `confirmed_ns` | 2500000000 | 6000000000: one period at 3 s, two at 6 s |
| `hot` activity start / end | 1 s / 6 s | 1 s / 6 s; confirmation can coincide with the end |
| `window_delta`: rise >= 5 V over the last 4 s, `emit_initial=true` | First match at 4 s, another trigger at 6 s | First match at 7 s after four driver intervals |

In actual mode, the first change window completes at 4 s: the value held from 3 s is 5 V, compared with 0 V at 0 s. At 5 s, the left boundary reaches 1 s and the difference drops to 4 V; it crosses the threshold again at 6 s. Fixed/DBC mode counts driver periods instead of subtracting 4 s from the log timestamp. This change-history window is also different from ordinary `windows` pre/post expansion.

The [comparison script](../examples/timing_comparison.py) checks actual return values. A pairing's `delay_ns` uses its selected duration basis; only `actual` equals response timestamp minus request timestamp. Export resampling is configured separately through `outputs` and does not determine these waits or integrals.
