<a id="统计与积分"></a>
# Statistics and integration

The root-level `calculations` list declares scalar calculations or selected sample records. `operation` selects the calculation; `scope` defaults to the entire analysis range and can select individual events or windows. `expr` selects a signal or expression. Results include units and completeness status; see [Results](results.md).

<a id="完整最小例与计算方法对照"></a>
<a id="integrators"></a>
## Choose an integrator

The **general time integrator** multiplies each valid held value by its duration under the chosen time basis, then adds those contributions. Set calculations[].operation to integral and provide expr. Actual elapsed time is the default; see [calculation intervals](intervals.md) for alternatives. The previous value lasts only until its next update or valid_for expiry. Missing data are not zero-filled, and the result reports completeness. Integrating power yields energy; integrating current yields charge. Other physical quantities can also be integrated.

For an ASC/BLF source, including volumes of one recording, with all inputs available in one message and an explicitly defined contribution per message, consider the [high-performance integrator (same-frame per-message accumulation)](fast-energy.md). Its expr supplies each contribution; include the time factor explicitly when needed. It does not automatically use elapsed time between messages. A general integral configuration cannot switch engines merely by changing the command. Use the general path for cross-message holds, sustained conditions, or event windows.


## Complete examples and operation comparison

[calculation-minimal.yaml](../examples/calculation-minimal.yaml) performs one integral using synthetic CAN power records: 0 W at 0 s, 10 W at 1 s, 0 W at 4 s and 5 s. The range is [0,5), with a 4 s validity period. The result is 0×1+10×3+0×1 = 30 J.

[calculation-operations.yaml](../examples/calculation-operations.yaml) demonstrates the basic operations below, explicit output units and coverage controls on the same input. Run `chronaxis run calculation-operations.yaml --output new-result` from the examples directory. The right endpoint at 5 s establishes the observation end and is not a selected sample.

| Calculation | Output | Explanation |
|---|---|---|
| integral | 30 J | 10 W for 3 s |
| sample_minimum / sample_maximum / sample_mean | 0 W / 10 W / 10÷3 W | Three actual updates in [0,5): 0, 10, 0 |
| min_time / max_time | 0 W / 10 W | Minimum/maximum value with positive valid duration, not the timestamp at which it occurred |
| time_weighted_mean | 6 W | 30 J ÷ 5 s |
| duration, condition `power > 0` | 3 s | True over [1,4) |
| select | Three rows at 0, 1, 4 s | Original values and quality, read through selections rather than scalar calculations |
| energy_Wh | 30÷3600 Wh | Convert J to Wh after integration; full coverage meets the 0.9 threshold |

<a id="v4-power-statistics"></a>
## Count readings or loads, and measure power over time

A bench sends **0, 10, 0, 20 and 0 W** at 0, 1, 4, 5 and 7 seconds. An unrelated frame at 9 seconds establishes the observation end. The analysis covers [0,9) seconds. Each power reading stays valid for up to 4 seconds, long enough to bridge the gaps. Download the configuration, ASC and DBC with their relative directory layout. In the downloaded configuration's directory, run the commands below. The output directory can be reused; each run creates timestamped files. [Complete v4 configuration](../examples/power-statistics.yaml) · [Raw ASC](../examples/data/can/power-statistics.asc) · [DBC](../examples/data/can/teaching.dbc)

```console
python -m chronaxis validate power-statistics.yaml --format json
python -m chronaxis run power-statistics.yaml --output power-results
```

| Question | v4 `calculations[].operation` | Result on the recording |
|---|---|---|
| How many valid power readings arrived? | `sample_count` with `expr: power` | 5. The final unrelated frame only establishes the observation end. |
| How often did a load start, and how many loaded intervals occurred? | `point_event_count` and `activity_count`, each naming its `rule` | 2 rising edges and 2 activities, [1,4) and [5,7) s |
| How many test segments are left after merging? | `segment_count`, naming the `window` | 1. The 1 s gap is shorter than the 1.5 s exit delay, producing [1,8.5) s. |
| How much did individual readings vary? | `sample_variance`, `sample_stddev` | Variance with `ddof: 1` is 80 W². Standard deviation with default `ddof: 0` is 8 W. |
| How much did power vary over time? | `time_variance`, `time_stddev` | 5000/81 ≈ 61.7284 W² and its square root, about 7.85674 W |
| What was the root mean square power? | `sample_rms`, `time_rms` | Equal reading weights give 10 W. Valid duration weights give √(1100/9) ≈ 11.05542 W. |
| What were the 95th percentile and median readings? | `sample_quantile` with `q: 0.95`, and `sample_median` | 18 W and 0 W |

**Choose the weights.** Each valid real update whose selection condition is known true contributes once. A repeated transmission of the same value still counts. Holding a reading, reaching an expiry or checking a condition adds no power reading. Sample calculations accept a session, rule-event or window `scope`. The three object counts use session scope and return unit `1`. They reference the rule or window that produces the objects. Complete observation with no qualifying objects gives zero. If discovery has gaps, `report` can retain a known count marked `partial`, while `strict` withholds a partial value. Without observation evidence, the value is empty. Check `status` and `reason`.

**Check the spread and RMS.** The five readings have mean 6 W and sum of squared deviations 320 W². Sample variance divides by `N-ddof`. Standard deviation takes the square root. Sample variance and standard deviation accept 0 (default) or 1. A single valid sample with `ddof: 1` yields an empty value with reason `insufficient_samples`. At actual elapsed time, 0, 10 and 20 W were held for a total of 4, 3 and 2 seconds respectively. This gives a time mean of 70/9 W and a mean square of 1100/9 W². Time statistics weight each valid selected positive duration using the chosen interval basis. Time variance and standard deviation accept only `ddof: 0`. Omit `ddof` for both RMS operations. Compatible output units can be set with `unit`. The default variance header here reads `W^2`, equivalent to W². Standard deviation of absolute temperature has a temperature-difference unit, variance its square. Convert absolute Celsius temperatures explicitly to K before calculating RMS.

**Check the quantiles.** Sort the selected readings to get [0,0,0,10,20]. The zero-based rank is `(N-1)×q`. P95 falls at rank 3.8, 80% of the way from 10 to 20 W, giving 18 W. Supply a finite `q` from 0 through 1 for a quantile. Median fixes the probability at 0.5 and takes no `q`. Endpoints 0 and 1 need only an extreme value. Interior probabilities retain the selected samples and reserve additional sorting space against `execution.memory_budget_bytes`. Insufficient budget raises a resource error. Smaller read batches still contribute to the same population.

Open the timestamped session CSV (`会话结果`) to check these values. In the events CSV (`事件结果`) the mean powers of the two loaded intervals are 10 and 20 W. Taking P95 across those two rows gives **19.5 W**. Each load contributes once, and the aggregation records two candidates and two included values. [Aggregation populations and exclusions](aggregations.md)

<a id="配置片段"></a>
## Configuration fragment

Use [analysis.yaml](../examples/analysis.yaml), which already defines `power` in W. Replace its root `calculations` list with one of the following blocks. Each name identifies a separate result. These blocks are alternatives: do not repeat the parent key or nest it inside a list item.

```yaml
calculations:            # Calculations to return
  - name: energy         # Name shown in results
    operation: integral  # Sum value multiplied by valid duration
    expr: power          # Previously defined power signal
```

<a id="扩展设置"></a>
### Additional controls

This version adds a 90% coverage requirement. It keeps the default J unit, `zoh` integration and `report` partial-result policy. Set another supported unit or `strict` only when needed.

```yaml
calculations:              # Calculations to return
  - name: energy           # Name shown in results
    operation: integral    # Integrate power over the selected range
    expr: power            # Previously defined power signal
    minimum_coverage: 0.9  # Required data coverage, between 0 and 1
```

<a id="字段参考"></a>
## Field reference

All paths below are relative to `calculations[]`.

| Field | Type, requirement and default | Purpose and constraints |
|---|---|---|
| name | String, required | Unique calculation name. Must not duplicate a rule, window or other generated node name. |
| operation | String, required | Select an operation below, considering its input type, weighting and result unit. |
| rule / window | String, one required for v4 object counts | Point and activity counts take `rule`. Counts of final segments take `window`. These operations use session scope and need no signal expression. |
| ddof | Integer, only for v4 variance and standard deviation | Sample operations accept 0 (default) or 1. Time operations accept only 0. |
| q | Finite number, required only for v4 `sample_quantile` | Probability in [0,1], such as 0.95 for P95. Omit for median. |
| scope | String or object; default `session` | Entire session, `{rule: hot}` for each hot event's selected range, or `{window: context}` for each context window. Referenced names must exist. |
| expr | Expression string, usually required | Signal, derived signal or allowed expression, such as `power` or `voltage * current`. Numeric operations require numeric input; `select` also accepts bool/enum. For `duration`, use a bool expression here or `condition`, never both. |
| condition | Optional expression string | Select data only while a condition is known True, such as `power > 0`. Omission adds no filter. `duration` can use this field directly without `expr`. Unknown is not False. |
| unit | Optional string | Usually inferred from the input and operation. `duration` requires s; `select` can convert compatible units; an integral can use a compatible registered output unit such as J or Wh. This is not an arbitrary label. |
| method | String, only for `integral`; default `zoh` | Hold the valid left-hand value between updates. Only `zoh` is supported; this field is rejected for other operations. |
| partial_policy | Optional string | Inherits `execution.partial_policy`, normally `report`. `report` returns a computable partial result; `strict` withholds the value when required data is incomplete. |
| minimum_coverage | Finite number, default 0 | Required coverage in [0,1]. Zero adds no minimum proportion; it does not replace missing data with zero. Sample statistics still count real samples equally. `select` does not return scalar coverage status. |

Omitting `calculations` or using `[]` requests no ordinary calculations; null is invalid. Provided `expr`, `condition` and `unit` must not be empty strings. Missing names/operations, unresolved references, unit conflicts, or both `expr` and `condition` for duration produce a `PlanValidationError` identifying the field.

An individual calculation can specify `interval`, otherwise it inherits `intervals.default`. Only integration, duration and time-based statistics accept it; sample statistics and `select` do not. See [Calculation intervals](intervals.md).

<a id="计算方法"></a>
## Operations

| Category | operation | Inputs and weighting | Output and specific parameters |
|---|---|---|---|
|Time integral|integral|Numeric expr; accumulate valid held durations|One integral value; method only zoh (default); optional interval|
|Duration|duration|Exactly one Boolean expr or condition; known-true durations|Seconds; optional interval|
|Sample statistics|sample_count|Each selected valid real update once|Dimensionless count; held refreshes are not new samples|
|Sample statistics|sample_minimum, sample_maximum, sample_mean|Equally weighted valid updates|Minimum, maximum, mean; no value if no valid samples|
|Sample statistics|sample_variance, sample_stddev|Equally weighted valid updates, denominator N-ddof|Variance/stddev; ddof 0 (default) or 1|
|Sample statistics|sample_rms|Equally weighted valid updates|Root mean square; omit ddof|
|Sample statistics|sample_quantile, sample_median|Sorted valid updates; linear interpolation|quantile requires q in [0,1]; median fixes 0.5 and forbids q|
|Time-weighted statistics|min_time, max_time, time_weighted_mean|Values with positive valid durations|Held-value minimum/maximum or mean, not occurrence times; optional interval|
|Time-weighted statistics|time_variance, time_stddev|Valid duration weights|Variance/stddev; ddof only 0; optional interval|
|Time-weighted statistics|time_rms|Duration-weighted squares|Root mean square; omit ddof; optional interval|
|Object counts|point_event_count|Session scope; rule names a point-event rule|Point count; no expr, condition, or interval|
|Object counts|activity_count|Session scope; rule names an activity rule|Activity count; no expr, condition, or interval|
|Object counts|segment_count|Session scope; window names a window|Final segment count; no expr, condition, or interval|
|Sample selection|select|Selected updates and values, including bool/enum|Multiple records with time, value, and quality, not one scalar statistic; no interval|

Sample statistics and select do not use duration weighting and reject interval. q and ddof are accepted only by the operations shown. Object counts require session scope. Other scalar calculations can produce a row per session, event, or window; use [result aggregation](aggregations.md) to summarize those rows.

### Variance, standard deviation, and RMS

Sample variance is Σ(x-mean)²/(N-ddof); standard deviation is its square root. N≤ddof gives no value. Time methods use valid-duration weights and population statistics. RMS is the square root of the mean square, not standard deviation. Absolute-temperature variance/stddev use temperature-difference units; convert absolute Celsius to K before RMS. The power example above includes hand calculations.

### Quantiles

q is a probability from 0 to 1, not a percentage from 0 to 100. Position (N-1)×q determines linear interpolation between ordered neighbors; median fixes q=0.5. Interior probabilities retain selected samples and require sorting memory. Exceeding the budget raises a resource error rather than substituting an approximation.


## Output units

Use `config_version: 4`. Compatible registered units are converted automatically. Unit names are case-sensitive.

| Quantity | Units supported in version 4 |
|---|---|
| Dimensionless and ratio | `"1"`, `%`; 1% = 0.01 |
| Voltage, current, power | V, mV; A, mA; W, kW |
| Energy and charge | J, Wh, kWh; Ah, A*s (also A·s) |
| Time | s, ms, us, ns; µs and μs are aliases for us |
| Temperature and differences | K, degC (°C, ℃); delta_K, delta_degC (ΔK, Δ°C, Δ℃) |
| Resistance | Ohm, mOhm, kOhm, MOhm; Ω and Ω are aliases for Ohm; prefixed symbol forms are mΩ, kΩ and MΩ |
| Length, speed, acceleration | m, m/s, m/s^2 |
| Frequency, angular speed, angle | Hz, rpm, rad/s; rad, deg (°) |
| Force, torque, pressure | N, N*m (N·m); Pa, kPa, bar |

Version 4 also accepts multiplication, division, integer powers and parentheses over registered units, such as `V*s` and `A^2`. It does not guess arbitrary prefixes or unknown units. Quantity kinds must also match: N*m does not automatically become J, and Hz does not become rad/s. The rpm to rad/s conversion is explicitly registered.

An integral accumulates using the selected interval, then converts to the requested `unit`: 1000 W for 2 seconds defaults to 2000 J, or about 0.555556 Wh with `unit: Wh`. Integrating V produces V*s, not energy. Convert Celsius explicitly to K in the expression before integrating; a temperature offset cannot be added once to an integral.

In version 4, ordinary means, extremes, quantiles and `select` default to [canonical units](expressions.md#canonical-units): 1500 mV becomes 1.5 V, while explicit `unit: mV` keeps 1500 mV. Compatible target units convert both the number and the unit, including Celsius/Kelvin offsets. Variance, standard deviation and RMS follow the statistical unit rules above. `duration` still outputs only s. Sample counts and the three object counts output only `1`.

Labelling an unknown unit does not establish a verified physical relationship.

<a id="minimum_coverage覆盖门槛"></a>
<a id="minimum_coverage-覆盖门槛"></a>
## minimum_coverage

Suppose the requested range is [0,12) s but observations cover only [0,8). Power is 4000 W and the condition is known throughout those eight seconds, so 32000 J can be calculated.

`minimum_coverage` is a proportion between 0 and 1, not a method for repairing missing data. Set `minimum_coverage: 0.9` to require 90%. Place it in the calculation item or a preset that explicitly supports it, not under `execution`.

A positive threshold adds `coverage_status` to ordinary signal-based scalar calculations. These include integration, duration, extremes, means and the v4 sample count, moments, RMS and sample quantiles. `sufficient` means observation, value validity and condition-known coverage all meet the requirement. `indeterminate` means insufficient or undecidable coverage. This check preserves equal weighting for sample statistics. The three v4 object counts use evidence about discovery and do not accept this threshold. `select` and per-message accumulation also fall outside this set. Omitting the threshold or setting it to zero omits the field.

The following ratios explain the check; they are not exposed as three fields in the public summary:

- `requested_coverage`: observed duration / requested duration = 8/12, about 0.667.
- `value_coverage`: proportion of observed time with valid values = 1.0 here.
- `condition_coverage`: proportion of observed time where the condition is known True or False. With no condition filter, it covers the observed range.

Valid values throughout the observed eight seconds do not establish coverage of all twelve requested seconds. The 90% requirement fails here. With `partial_policy: report`, the computable 32000 J remains available; with `strict`, no value is returned. Read `coverage_status`, `status` and `reason` together.

For expressions evaluated once per message, see [Per-message accumulation](message-calculations.md).
