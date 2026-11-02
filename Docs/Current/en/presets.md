<a id="业务预设"></a>
# Presets

A preset is a predefined set of rules and calculations. For example, identify which signal represents a request and which represents a response, and a preset creates two rising-edge rules and a pairing definition. A **role** is a signal's purpose within that preset. `role_bindings` maps each role to a name already declared in `signals`.

Presets expand into `derived`, `rules`, `windows`, `sequences`, or `calculations` when the plan loads. Read results through those generated nodes. Prepare signals that meet the role requirements before selecting a preset.

Unless stated otherwise, examples use actual elapsed time. With fixed/DBC intervals, duration confirmation, waiting deadlines, change windows, and pairing `delay_ns` use the selected period. Original timestamps and signal expiry use actual time. See the [duration comparison](intervals.md#timing-basis).

Each preset is an object in the root `presets` list. The table below is relative to `presets[]`, for example `presets[].name`. `parameters` and `role_bindings` differ by preset type.

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `name` | String | Yes | None | Name this preset instance, for example `cmd`. Generated names use it as a prefix, such as `cmd_request`. It must be unique, and its generated names must not collide with existing rules, windows, or calculations. See [naming conventions](configuration.md). |
| `preset_type` | String | Yes | None | `charge_session`: identify charging periods. `fault_context`: select context around fault onset. `command_response`: match requests and responses. `threshold_excursion`: identify threshold-alarm periods. |
| `version` | String | No | `"1"` | Preset definition version. Use the string `"1"`, not number `1`. |
| `parameters` | Object | Yes | None | Business parameters for this preset type, obtained from the analysis requirement or device protocol. Parameters from different types cannot be mixed. |
| `role_bindings` | Object | No, except for threshold presets | `{}` | Map each role to an original bound signal's `signals[].name`, for example `request: start_button`. Role requirements still apply. |

Explicit role mappings are recommended. Except for threshold presets, an omitted role is resolved using declarations such as `semantic_id`. Exactly one signal must match. No match or multiple matches is an error; similar signal names are not a selection rule.

A role's requirements describe acceptable inputs: for example, charging current requires the expected type, unit, sign convention, and measurement location. These requirements are also called a semantic contract. Automatic resolution checks these declarations rather than guessing from CSV column names. An explicit mapping chooses the signal but does not waive its requirements.

<a id="完整最小例与扩展例"></a>
## Complete minimal and extended examples

These independent configurations use the included 0–4 s synthetic CAN input and contain all required sources, signals, and presets. Run `chronaxis run filename.yaml --output new-directory`.

| Feature | Minimal example | Extended example | Expected result |
|---|---|---|---|
| Charging periods | [preset-charge-minimal.yaml](../examples/preset-charge-minimal.yaml): mode 1 from 1–3 s, current 10 A | [preset-charge-energy.yaml](../examples/preset-charge-energy.yaml): adds 400 V, energy, and charge integrals | Activity [1,3); extended energy 8000/3600 Wh and charge 20/3600 Ah. |
| Fault context | [preset-fault-minimal.yaml](../examples/preset-fault-minimal.yaml): alarm rises at 1 s; select 1 s after | [preset-fault-context.yaml](../examples/preset-fault-context.yaml): select 1 s before and 2 s after; allow an initial alarm | Minimal [1,2), extended [0,3). Initial false means enabling `emit_initial` adds no event here. |
| Request/response | [preset-command-minimal.yaml](../examples/preset-command-minimal.yaml): request at 1 s, response at 2 s, explicit roles | [preset-command-automatic.yaml](../examples/preset-command-automatic.yaml): semantic declarations replace explicit bindings | Both produce one pair with a 1 s delay. |
| Threshold alarm | [preset-threshold-minimal.yaml](../examples/preset-threshold-minimal.yaml): temperatures 70, 85, 77, 75, 70 at one-second intervals | [preset-threshold-delay.yaml](../examples/preset-threshold-delay.yaml): 500 ms entry and exit waits | Minimal [1,3); extended [1.5,3.5). Both activities last 2 s. |

<a id="先准备来源和信号"></a>
## Prepare sources and signals

The complete [electrical-base.yaml](../examples/electrical-base.yaml) uses synthetic ASC frames and a DBC and analyzes the observed range. Its relevant signal definitions are reproduced below for reference; do not insert them twice. Dedicated examples above have their own fixed expected results; conceptual timelines below need not all occur in the shared teaching input.

There is one CAN source, so the signals need no repeated `source`. IDs and signal names come from the DBC, which also supplies types and units. The explicit 20 s validity is for sparse teaching records, not a recommended device setting.

```yaml
signals:                                 # Signals available to presets.
  - name: temperature                    # Name used by the threshold role.
    field:                               # Original CAN signal.
      frame_id: '0x11d'                  # Message ID from the DBC.
      signal: Temperature                # Case-sensitive DBC signal name.
    valid_for: 20s                       # Validity for this teaching input.
  - name: voltage                        # Voltage role candidate.
    field:                               # Original CAN signal.
      frame_id: '0x11f'                  # Message ID from the DBC.
      signal: Voltage                    # DBC signal name.
    valid_for: 20s                       # Validity for this teaching input.
    measurement_location: pack_terminal  # Actual measurement is at the pack terminals.
  - name: current                        # Current role candidate.
    field:                               # Original CAN signal.
      frame_id: '0x114'                  # Message ID from the DBC.
      signal: Current                    # DBC signal name.
    valid_for: 20s                       # Validity for this teaching input.
    measurement_location: pack_terminal  # Actual measurement location.
    sign_convention: positive_is_charge  # Positive values mean charging; no sign conversion.
  - name: mode                           # Integer operating-mode signal.
    field:                               # Original CAN signal.
      frame_id: '0x118'                  # Message ID from the DBC.
      signal: Mode                       # DBC signal name.
    valid_for: 20s                       # Validity for this teaching input.
  - name: request                        # Boolean request signal.
    field:                               # Original CAN signal.
      frame_id: '0x11a'                  # Message ID from the DBC.
      signal: Request                    # DBC signal name.
    valid_for: 20s                       # Validity for this teaching input.
    choices:                             # Input code to boolean value.
      - [0, false]
      - [1, true]
  - name: response                       # Boolean response signal.
    field:                               # Original CAN signal.
      frame_id: '0x11b'                  # Message ID from the DBC.
      signal: Response                   # DBC signal name.
    valid_for: 20s                       # Validity for this teaching input.
    choices:                             # Input code to boolean value.
      - [0, false]
      - [1, true]
```

<a id="先判断充电预设是否符合目标"></a>
## Check whether the charging preset matches your objective

Version 1 of `charge_session` has a fixed combination: mode equals a specified integer, current is **strictly greater than** a threshold, and the condition lasts **at least** the specified duration. Once qualified, calculations include the entire interval from condition onset to end. Energy is in Wh; charge is in Ah. Use it when those semantics match your task.

| Requirement | Appropriate entry point |
|---|---|
| Specified mode, current > 5 A, duration >= 3 s, output Wh | Charging preset, with verified current direction and measurement location. |
| Current >= 10 A, including exactly 10 A | [Sustained-condition rule](rules.md) plus [event integral](calculations.md). The preset's `> 10` excludes equality. |
| Duration strictly > 60 s | Ordinary rule with `minimum_duration: 60s` and `duration_comparison: ">"`; do not approximate with 60.1 s. |
| Output kWh directly, or combine several custom state conditions | Ordinary rule retaining the complete condition, plus an integral with `unit: kWh`. |
| Integrate an explicit voltage × current formula with no direction/location requirement | Ordinary integral; it needs no extra semantic declarations merely to fit a preset. |

In the [energy example](../examples/preset-charge-energy.yaml), mode is 1, current 10 A, and voltage 400 V during 1–3 s. Preset threshold 5 A and ordinary condition `mode == 1 and current > 5` both select [1,3): 400 × 10 × 2 = 8000 J = 2.222222… Wh. With threshold 10 A, the preset finds no qualifying interval, while ordinary `current >= 10` still selects it and can output 0.002222222… kWh. Those numbers have different units.

Ordinary rules also default to `selection_origin: onset`, including the qualifying wait. Explicit `confirmed` starts at confirmation instead. Choose a coverage requirement from the actual task; charging analysis does not automatically imply a 95% threshold.

<a id="充电时段charge_sessionparameters"></a>
<a id="充电时段-charge_session-parameters"></a>
## Charging periods: `charge_session.parameters`

`charge_session` is a `preset_type` value, not an additional parent key. These fields belong inside `presets[].parameters`.

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `mode_value` | Integer | Yes | None | Device mode code considered charging. It must fit the bound mode signal's integer type and valid range. Obtain it from the device's state-code definitions. |
| `current_min` | Number | Yes | None | Threshold in A; negative values are allowed. Current must be strictly greater, so exactly 5 A does not satisfy a threshold of 5. |
| `minimum_duration` | Duration string | Yes | None | Nonnegative continuous duration for matching mode and current. `3s` confirms after three seconds, but the selected activity begins at the original onset. |
| `compute_energy` | Boolean | No | `false` | True generates voltage × current power and an energy integral in Wh, requiring the voltage role. False generates neither. |
| `compute_charge` | Boolean | No | `false` | True generates the current integral in Ah. Independent of `compute_energy`; either or both can be enabled. |
| `minimum_coverage` | Number | No | `0` | Inclusive range 0–1. For example, 0.9 requires 90% coverage. Any required coverage below the threshold marks `coverage_status` as `indeterminate`; this does not itself discard a computed value. See [coverage](calculations.md). |
| `partial_policy` | String | No | Inherits `execution.partial_policy` | `report` keeps computable portions and marks incomplete data; `strict` returns null if required time is missing. Applies to the generated energy/charge calculations. See [examples](execution.md). |

For instance name `charge`:

| `compute_energy` | `compute_charge` | Generated nodes |
|---|---|---|
| false | false | `charge_activity` only. |
| true | false | Also `charge_power` and `charge_energy` in Wh. |
| false | true | Also `charge_charge` in Ah. |
| true | true | Activity, power, energy, and charge. |

A different instance name changes the generated prefix.

<a id="故障前后数据fault_contextparameters"></a>
<a id="故障前后数据-fault_context-parameters"></a>
## Fault context: `fault_context.parameters`

These fields belong inside `presets[].parameters`, with `preset_type: fault_context`.

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `pre` | Nonnegative duration string | No | `0s` | Context before fault onset. A fault at 10 s with `2s` begins selection at 8 s. |
| `post` | Nonnegative duration string | No | `0s` | Context after fault onset. At least one of pre/post must be positive. `3s` in the example selects up to, but not including, 13 s. |
| `emit_initial` | Boolean | No | `false` | False does not treat an initially active alarm as a new fault. True emits an initial fault point and its context window. |

The preset generates `<name>_alarm` as a rising-edge rule and `<name>_context` as a window. Windows from neighboring faults remain separate and are not automatically merged.

<a id="请求与响应command_responseparameters"></a>
<a id="请求与响应-command_response-parameters"></a>
## Request/response: `command_response.parameters`

These fields belong inside `presets[].parameters`, with `preset_type: command_response`.

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `min_delay` | Nonnegative duration string | No | `0s` | Earliest allowed response delay. Zero permits response at the request timestamp. |
| `max_delay` | Duration string | Yes | None | Latest allowed response, not less than `min_delay`. A response exactly at the deadline succeeds. |
| `emit_initial` | Boolean | No | `false` | True permits an initial point independently for initially true request and response signals; false permits neither. |
| `max_pending` | Positive integer | No | `65536` | Maximum simultaneous pending requests. Exceeding it raises an error rather than dropping the oldest request. Choose it from expected concurrency and resource budgets. |

Generated nodes are `<name>_request`, `<name>_response`, and `<name>_pair`. See [sequences](sequences.md) for queuing, missing data, and timeout behavior.

<a id="超阈值时段threshold_excursionparameters"></a>
<a id="超阈值时段-threshold_excursion-parameters"></a>
## Threshold alarms: `threshold_excursion.parameters`

These fields belong inside `presets[].parameters`, with `preset_type: threshold_excursion`.

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `unit` | String | No | Bound signal's unit | Threshold unit; it must exactly match the signal unit. Usually omit it for a signal already declared in `degC`. |
| `enter_threshold` | Number | Yes | None | Enter when the value is at least this threshold. Must be greater than `exit_threshold`, for example 80. |
| `exit_threshold` | Number | Yes | None | Clear when the value is at most this threshold, for example 75. Between 75 and 80, retain known state. |
| `enter_delay` | Nonnegative duration string | No | `0ns` | Continuous entry-condition wait; zero confirms immediately. |
| `exit_delay` | Nonnegative duration string | No | `0ns` | Continuous exit-condition wait; zero clears immediately. |

Numeric thresholds must be finite: NaN and Infinity are invalid. Durations support `ns`, `us`, `ms`, and `s`, such as `200ms`. See [configuration conventions](configuration.md).

<a id="preset-role-requirements"></a>
<a id="各角色的要求"></a>
## Role requirements

Each mapping value is a string containing an existing signal name, such as `current: pack_current`. Roles select declared signals; they do not introduce extra input columns.

| Preset | Role | When required | Signal requirements | `semantic_id` for automatic lookup |
|---|---|---|---|---|
| `charge_session` | `mode` | Always | `int64` or `uint64`; unit `"1"` | `battery.mode` |
| `charge_session` | `current` | Always | `float64`; A; `sign_convention: positive_is_charge`; `measurement_location: pack_terminal` | `battery.current` |
| `charge_session` | `voltage` | When `compute_energy` is true; an explicitly supplied binding is checked even otherwise | `float64`; V; `measurement_location: pack_terminal` | `battery.voltage` |
| `fault_context` | `alarm` | Always | `bool`; unit `"1"` | `fault.alarm` |
| `command_response` | `request` | Always | `bool`; unit `"1"` | `command.request` |
| `command_response` | `response` | Always | `bool`; unit `"1"` | `command.response` |
| `threshold_excursion` | `signal` | Explicit mapping required | `int64`, `uint64`, or `float64`; unit equals `parameters.unit` | No automatic lookup |

Automatic lookup also requires `semantic_contract_version: "1"`. Explicit bindings need neither semantic field but still undergo type, unit, and other role checks.

Every role signal requires a positive resolvable validity duration and `backward_hold`. Explicit `valid_for` takes precedence; otherwise it is three times that signal's `period` or its DBC message period. Each role resolves its own period, not the driver's. If held values are needed and no period is available, supply validity explicitly. The latest valid value is held until `valid_for` expires. Missing, nonfinite, and out-of-range values remain subject to quality checks; presets cannot bypass them.

`positive_is_charge` means positive current is charging; `pack_terminal` means measured at the battery pack terminals. If charging current is negative in the device, explicitly preprocess it into a charging-positive input before binding and declaring this convention. The public signal conversion currently rejects A → A with `scale: -1`; changing only the label does not negate values. See [conversion limits](signals.md#signal-conversion). Declarations do not replace checking actual wiring, calibration, and units.

<a id="业务声明何时填写如何取得"></a>
<a id="业务声明-何时填写-如何取得"></a>
## When to provide semantic declarations

| Use | `semantic_id` | `semantic_contract_version` | Other requirements |
|---|---|---|---|
| Ordinary rules/calculations | Optional | Optional | Expressions refer to `name`. |
| Explicit preset `role_bindings` | Optional | Optional | Still meet role type, unit, direction, location, and validity requirements. |
| Omitted role, resolved automatically | Role-specific string from the table, such as `command.request` | String `"1"` from this release's role definition | Exactly one signal must satisfy all requirements; zero or multiple candidates raise `PlanValidationError`. |
| `threshold_excursion` | Not used for role lookup | Not used for role lookup | Explicit `signal` role required. |

For automatic request/response lookup, add `semantic_id: command.request` and `semantic_contract_version: "1"` to the request signal, and `command.response` / `"1"` to the response. These select version 1 of those role contracts. The file still uses `config_version: 3`, while an omitted preset `version` defaults to `"1"`; the three version fields describe different objects.

Optional semantic text on original `signals` may be omitted or null. If `semantic_contract_version` is provided, `semantic_id` must also be provided. Optional semantic text on `derived` must be omitted or nonempty, not null. Derived semantic declarations describe results but do not make them candidates for preset roles in this release. Explicit role bindings also select only original `signals`. See [derived fields](expressions.md).

<a id="请求响应"></a>
## Request/response example

Add or replace the root `presets` section in [electrical-base.yaml](../examples/electrical-base.yaml). This fragment includes its parent key; do not place that key inside the preset list.

```yaml
presets:                           # Predefined combinations of analysis nodes.
  - name: cmd                      # Prefix for generated node names.
    role_bindings:                 # Select existing signals for each role.
      request: request             # Previously defined boolean request.
      response: response           # Previously defined boolean response.
    parameters:                    # Parameters for command_response.
      max_delay: 2s                # Inclusive maximum response delay.
    preset_type: command_response  # Request/response preset.
```

This generates `cmd_request`, `cmd_response`, and `cmd_pair`. Setting `emit_initial: true` permits initially true values on both ends. Do not define ordinary rules with those same names. See [sequences](sequences.md) for pairing and missing data.

<a id="阈值报警和总持续时间"></a>
## Threshold alarms and total duration

Add or replace the root `presets` section in the electrical base:

```yaml
presets:                              # Predefined analysis nodes.
  - name: hot                         # Prefix for generated names.
    role_bindings:                    # Explicit signal selection is required here.
      signal: temperature             # Previously defined numeric signal.
    parameters:                       # Threshold and recovery requirements.
      enter_threshold: 80             # Enter at or above 80.
      exit_threshold: 75              # Clear at or below 75.
    preset_type: threshold_excursion  # Hysteresis alarm preset.
```

This preset always means value >= upper threshold to enter and <= lower threshold to exit. Entry must be strictly above exit. For a low-value alarm, write custom `hysteresis` conditions. Here degC remains the same original unit; input must also be degC. Do not apply a scale, offset, or sign transformation and then claim that this preset has verified that conversion.

It generates `hot_activity` and `hot_duration`. Read per-activity durations through `iter_calculations()`. The total is in `result.metadata.threshold_durations`, or `run.threshold_durations` in the published `run_manifest.json`. The public summary uses `value` and `unit`, with unit always `s`; it does not duplicate the duration in nanoseconds.

| Observation | Total-duration result | Reason |
|---|---|---|
| 85 for 3 s, 77 for 6 s, then clears at 75 | 9 s, `complete` | Alarm state is known throughout. |
| Two alarms lasting 2 and 4 s with complete normal data between | 6 s, `complete` | Sum the two activities, excluding the gap. |
| Known non-alarm throughout | 0 s, `complete` | No alarm was observed. |
| First 3 s at 77, then 85 until 9 s | `value=6`, `unit=s`, `status=partial` | Initial state is unknown; only six known alarm seconds are counted. |
| Only 77 throughout, with no preceding known state | None, `indeterminate` | Unknown is not zero. |
| No valid observation interval, such as a single isolated timestamp | None, `no_observation` | There is no duration to summarize. |

For nine observed seconds with the first three unknown and the last six definitely in alarm, the public summary has five fields:

| Field | Example | Meaning |
|---|---|---|
| `preset_id` | `hot` | Preset instance producing the summary. |
| `rule_id` | `hot_activity` | Generated activity rule. |
| `value` | `6.0` | Known accumulated alarm seconds, not a complete total for all nine seconds. |
| `unit` | `s` | Unit of `value`, always seconds. |
| `status` | `partial` | Some intervals are unknown; retain this status when reading the value. |

Ordinary calculation `partial_policy` and the preset total summary are separate interfaces. Lower-level fields such as `known_active_duration_ns` are not fields of this public summary. In [preset-threshold-partial.yaml](../examples/preset-threshold-partial.yaml), 77 during 0–1 s leaves the preceding alarm state unknown, while 1–3 s is known alarm: `value=2.0`, `status=partial`.

A confirmation wait can also make the initial state unknown. In [preset-threshold-delay.yaml](../examples/preset-threshold-delay.yaml), `exit_delay` is 500 ms: the initial 70°C does not establish a confirmed non-alarm state until 0.5 s. The activity [1.5,3.5) is complete and its per-activity result is 2 s / `complete`, but the session total is 2 s / `partial` because the first 0.5 s is unknown. These statuses describe different ranges.

The summary covers actual observation. If analysis requests through 12 s but the log ends at 9 s, also inspect the manifest's observed range. The summary does not prove there was no alarm during 9–12 s.

<a id="充电与故障前后文"></a>
## Charging and fault-context examples

The charging preset below requires mode 1, current strictly above 5 A, and a continuous duration of at least 3 s, and calculates voltage × current energy. Replace the electrical base's root `presets` section:

```yaml
presets:                         # Predefined analysis nodes.
  - name: charge                 # Prefix for generated names.
    role_bindings:               # Existing signals fulfilling the role requirements.
      mode: mode                 # Integer charging-mode signal.
      current: current           # Current in A, charging-positive at pack terminals.
      voltage: voltage           # Voltage in V at pack terminals.
    parameters:                  # Charging requirements.
      mode_value: 1              # Device's charging-mode code.
      current_min: 5             # Strict lower current threshold in A.
      minimum_duration: 3s       # Minimum continuous qualifying duration.
      compute_energy: true       # Generate power and Wh energy calculation.
    preset_type: charge_session  # Charging-period preset.
```

`fault_context` instead selects data around fault onset. A fault at 10 s with `pre: 2s` and `post: 3s` selects 8–13 s. If the log does not cover that entire range, results describe the observed portion. It does not measure the duration of the fault; use `condition_duration` or `hysteresis` for that.

See [presets](../reference/chronaxis.presets.md) and [preset models](../reference/chronaxis.planning.preset_models.md) for lower-level types and generated fields (Chinese implementation references). Complete runnable inputs are linked from [examples](examples.md).
