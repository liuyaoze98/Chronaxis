<a id="统计与积分"></a>
# Statistics and integration

The root-level `calculations` list declares the values to compute. `operation` selects the calculation; `scope` defaults to the entire analysis range and can select individual events or windows. `expr` selects a signal or expression. Results include units and completeness status; see [Results](results.md).

<a id="完整最小例与计算方法对照"></a>
## Complete examples and operation comparison

[calculation-minimal.yaml](../examples/calculation-minimal.yaml) performs one integral using synthetic CAN power records: 0 W at 0 s, 10 W at 1 s, 0 W at 4 s and 5 s. The range is [0,5), with a 4 s validity period. The result is 0×1+10×3+0×1 = 30 J.

[calculation-operations.yaml](../examples/calculation-operations.yaml) adds every operation, explicit output units and coverage controls to the same input. Run `chronaxis run calculation-operations.yaml --output new-result` from the examples directory. The right endpoint at 5 s establishes the observation end and is not a selected sample.

| Calculation | Output | Explanation |
|---|---|---|
| integral | 30 J | 10 W for 3 s |
| sample_minimum / sample_maximum / sample_mean | 0 W / 10 W / 10÷3 W | Three actual updates in [0,5): 0, 10, 0 |
| min_time / max_time | 0 W / 10 W | Minimum/maximum value with positive valid duration, not the timestamp at which it occurred |
| time_weighted_mean | 6 W | 30 J ÷ 5 s |
| duration, condition `power > 0` | 3 s | True over [1,4) |
| select | Three rows at 0, 1, 4 s | Original values and quality, read through selections rather than scalar calculations |
| energy_Wh | 30÷3600 Wh | Convert J to Wh after integration; full coverage meets the 0.9 threshold |

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
| scope | String or object; default `session` | Entire session, `{rule: hot}` for each hot event's selected range, or `{window: context}` for each context window. Referenced names must exist. |
| expr | Expression string, usually required | Signal, derived signal or allowed expression, such as `power` or `voltage * current`. Numeric operations require numeric input; `select` also accepts bool/enum. For `duration`, use a bool expression here or `condition`, never both. |
| condition | Optional expression string | Select data only while a condition is known True, such as `power > 0`. Omission adds no filter. `duration` can use this field directly without `expr`. Unknown is not False. |
| unit | Optional string | Usually inferred from the input and operation. `duration` requires s; `select` preserves the input unit; an integral can use a compatible registered output unit such as J or Wh. This is not an arbitrary label. |
| method | String, only for `integral`; default `zoh` | Hold the valid left-hand value between updates. Only `zoh` is supported; this field is rejected for other operations. |
| partial_policy | Optional string | Inherits `execution.partial_policy`, normally `report`. `report` returns a computable partial result; `strict` withholds the value when required data is incomplete. |
| minimum_coverage | Finite number, default 0 | Required coverage in [0,1]. Zero adds no minimum proportion; it does not replace missing data with zero. Sample statistics still count real samples equally. `select` does not return scalar coverage status. |

Omitting `calculations` or using `[]` requests no ordinary calculations; null is invalid. Provided `expr`, `condition` and `unit` must not be empty strings. Missing names/operations, unresolved references, unit conflicts, or both `expr` and `condition` for duration produce a `PlanValidationError` identifying the field.

An individual calculation can specify `interval`, otherwise it inherits `intervals.default`. Only integration, duration and time-based statistics accept it; sample statistics and `select` do not. See [Calculation intervals](intervals.md).

<a id="计算方法"></a>
## Operations

| operation | Meaning | Example |
|---|---|---|
| integral, method=zoh | Multiply each held valid value by its duration and add the pieces | 1000 W for 2 s = 2000 J |
| sample_minimum / sample_maximum / sample_mean | Each selected valid real sample counts once | Samples 0 at 0 s, 10 at 1 s, 0 at 4 s have mean 10/3 |
| min_time / max_time / time_weighted_mean | The first two return values having positive valid duration, in the input unit, not timestamps; the mean is duration-weighted | In [0,4), 0 is held for 1 s and 10 for 3 s: extremes 0/10, mean 7.5 |
| duration | Accumulate the duration for which the condition is known True | Two True intervals of 1 s give 2 s |
| select | Return selected rows with quality and source information | Inspect individual times and values instead of one summary number |

The selection interval determines whether the final sample is included; the sample-mean example above includes all three records. Integration uses the last still-valid value (zero-order hold, ZOH); omitting `method` selects `zoh`. Linear interpolation integration is not supported. Configure ordinary calculations and per-message accumulation separately.

<a id="结果单位如何选择"></a>
## Output units

Units are case-sensitive. `A·s` uses a middle dot, not an asterisk. The registered conversions are:

| Quantity | Units and factors |
|---|---|
| Dimensionless | `"1"` |
| Voltage | V; 1 mV = 0.001 V |
| Current | A; 1 mA = 0.001 A |
| Power | W; 1 kW = 1000 W |
| Energy | J; 1 Wh = 3600 J; 1 kWh = 3600000 J |
| Time | s; 1 ms = 0.001 s |
| Charge | A·s; 1 Ah = 3600 A·s |

Integrating W/kW defaults to J and permits J/Wh/kWh. Integrating A/mA defaults to A·s and permits A·s/Ah. Integrating dimensionless values defaults to s and permits s/ms. Other input units receive a `*s` suffix, such as `V*s`, and only that same result label is accepted; no other physical quantity is inferred.

Sample statistics and time-based extremes/means retain the input unit by default and may use another registered unit of the same quantity, such as mV instead of V. `duration` outputs s only, not ms. `select` retains the input unit without conversion. Unregistered units can only retain their original label.

<a id="minimum_coverage覆盖门槛"></a>
<a id="minimum_coverage-覆盖门槛"></a>
## minimum_coverage

Suppose the requested range is [0,12) s but observations cover only [0,8). Power is 4000 W and the condition is known throughout those eight seconds, so 32000 J can be calculated.

`minimum_coverage` is a proportion between 0 and 1, not a method for repairing missing data. Set `minimum_coverage: 0.9` to require 90%. Place it in the calculation item or a preset that explicitly supports it, not under `execution`.

For `integral`, `duration`, `min_time`, `max_time`, `time_weighted_mean`, `sample_minimum`, `sample_maximum` and `sample_mean`, a positive threshold adds `coverage_status`. `sufficient` means observation, value validity and condition-known coverage all meet the requirement; `indeterminate` means insufficient or undecidable coverage. It is not a numeric coverage ratio and does not change sample weighting. `select` and per-message accumulation are outside this set. Omission or zero does not add the field.

The following ratios explain the check; they are not exposed as three fields in the public summary:

- `requested_coverage`: observed duration / requested duration = 8/12, about 0.667.
- `value_coverage`: proportion of observed time with valid values = 1.0 here.
- `condition_coverage`: proportion of observed time where the condition is known True or False. With no condition filter, it covers the observed range.

Valid values throughout the observed eight seconds do not establish coverage of all twelve requested seconds. The 90% requirement fails here. With `partial_policy: report`, the computable 32000 J remains available; with `strict`, no value is returned. Read `coverage_status`, `status` and `reason` together.

For expressions evaluated once per message, see [Per-message accumulation](message-calculations.md).
