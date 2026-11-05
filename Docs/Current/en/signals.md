<a id="信号绑定与有效期"></a>
# Signal bindings and validity

The root `signals` list turns an input column or DBC signal into a named analysis signal. Use `source` to reference `sources[].name` only when several sources are candidates. `field` locates the original field, and `name` is used by expressions. A signal definition controls conversion, validity checks, and how long the latest value can be held; subsequent rules and calculations reference its name.

An **input value** here has already been parsed from CSV text or decoded from CAN using a DBC. Components performing those operations are readers. ASC/BLF are detected by extension; CSV and memory inputs require `sources[].source_type`. DBC scaling and offsets have already been applied during decoding; conversion in `signals` is an additional step. An **enumeration label**, such as `"idle"`, is the text analysis value assigned to a state code, not a field name in another file.

<a id="数值信号先运行ascblf最小配置"></a>
## Numeric signals: run a minimal ASC or BLF configuration

Use [signal-types.asc](../examples/data/can/signal-types.asc) and [teaching.dbc](../examples/data/can/teaching.dbc). `Current_mA` is measured in mA; `Enabled` codes 0/1 mean off/on. `ModeCode` has DBC enumeration entries 0/7 for idle/running. Decoded teaching data is:

| Time | Current_mA | Enabled | ModeCode |
|---|---|---|---|
| 0 ms | 5000 | 0 | 0 |
| 100 ms | 7000 | 1 | 7 |
| 200 ms | 5000 | 1 | 7 |
| 300 ms | 5000 | 0 | 0 |

The complete [signal-number-minimal.yaml](../examples/signal-number-minimal.yaml) reads only current and calculates its maximum. Type and unit come from the DBC. See [conversion](#signal-conversion) for automatic unit conversion. To display the maximum as mA, the calculation explicitly sets `unit: mA`; omitting that output setting gives the inferred unit A (7 A here). The 200 ms validity is an explicit choice for this example; no additional settings need to be copied.

```yaml
# Synthetic teaching configuration; use the bundled inputs to reproduce this example.
config_version: 4                       # Current analysis configuration version
dataset:                                # Analysis identity and optional input range
  name: signal_example                  # Name used to identify and reference this object
sources:                                # Input sources used by this analysis
  - paths: data/can/signal-types.asc    # File, continuous file list or directory; relative to this configuration
    dbc_by_channel:                     # DBC files indexed by user-facing CAN channel
      '1': data/can/teaching.dbc        # DBC for channel 1; channel keys are strings
signals:                                # Signals available to expressions
  - field:                              # Locate the original input field
      frame_id: '0x101'                 # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Current_mA                # Exact signal name defined in the DBC
    name: current                       # Name used to identify and reference this object
    valid_for: 200ms                    # Maximum time for retaining the latest valid reading
calculations:                           # Requested statistics or selected rows
  - name: maximum_current               # Name used to identify and reference this object
    operation: sample_maximum           # Calculation to apply to the expression
    expr: current                       # Formula using the declared signal or derived names
    unit: mA                            # Output unit; display the maximum current in milliamperes
```

From the examples directory, run `chronaxis run signal-number-minimal.yaml --output out-number`. `maximum_current` should be 7000 mA. For BLF, change the log path without changing the signal structure. An ordinary maximum needs no `conversion`, `scope`, or `session` declaration.

<a id="扩展换算成安培并识别无效值"></a>
### Extension: convert to amperes and recognize invalid values

[signal-number-conversion.yaml](../examples/signal-number-conversion.yaml) uses the same log with additional conversion and quality requirements. First replace the previous `signals` section with:

```yaml
signals:                         # Signals available to expressions
  - field:                       # Locate the original input field
      frame_id: '0x101'          # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Current_mA         # Exact signal name defined in the DBC
    invalid_values: [65535.0]    # Decoded invalid value, before extra conversion
    name: current                # Name used to identify and reference this object
    valid_for: 200ms             # Maximum time for retaining the latest valid reading
    valid_range: [-100, 100]     # Inclusive range after conversion, in A
    conversion:                  # Optional unit conversion after decoding
      input_unit: mA             # DBC-decoded unit
    unit: A                      # Target analysis unit; compatible registered units convert when scale/offset are omitted
```

Then remove `unit: mA` from the previous calculation. The complete `calculations` section is:

```yaml
calculations:                    # Results requested by this example
  - name: maximum_current        # Identify the maximum-current result
    operation: sample_maximum    # Maximum of valid observed samples
    expr: current                # Current converted to A above; omit output unit
```

The signal converts 5000 mA to 5 A, and the calculation displays 7 A using its default output unit. Keeping `unit: mA` on the calculation would still display 7000 mA. These extra fields demonstrate conversion and invalid codes; ordinary calculations do not need them. The DBC scales `Current_mA` by 0.5 and returns a float, so the sentinel is the decoded float `65535.0`. `valid_range` is checked in amperes: 101 A is invalid, while 100 A is valid. The example has no invalid values, so the maximum remains 7 A.

<a id="完整字段参考"></a>
## Complete field reference

This table describes one signal declaration; message groups use the separate structure below. Paths are relative to `signals[]`: `conversion.scale` means `signals[].conversion.scale`, not a `scale` beside `name`. CAN `field` objects are described under [message location](inputs.md#can-field); CSV/memory `field` is a string containing the original field name.

Omitted optional fields use their defaults. Except for metadata explicitly allowing null, do not use `null` instead of omission.

| Field | Type, requirement, and default | Purpose, choices, and effects |
|---|---|---|
| `name` | Required string | Unique analysis name referenced by expressions and calculations, such as `current`. Start with a non-reserved English letter or underscore; no spaces. |
| `source` | String; optional for a unique source | Select an existing `sources[].name`, such as `meter`, not a CSV path. |
| `field` | Required string or mapping | CSV: exact header such as `Current_mA`; memory: a `rows[].values` key; CAN: channel, frame ID, and DBC signal name as described in [CAN fields](inputs.md#can-field). Names are case-sensitive. |
| `dtype` | String; optional for CAN | `float64`: finite fractional values; `int64`: integers from -2^63 to 2^63-1; `uint64`: integers from 0 to 2^64-1; `bool`: true/false; `enum`: named states. For CAN without explicit `choices`, infer numeric type from the DBC physical range. All-Boolean or all-string explicit mapping targets can imply bool/enum. A DBC enumeration alone does not automatically select enum: `state == 1` remains valid. CSV/memory need an explicit type. |
| `unit` | Nonempty string; optional for CAN | Target analysis unit such as `A` or `V`; quote dimensionless `"1"`. CAN defaults to the DBC unit; missing DBC units become `unknown`, while bool/enum use `"1"`. Version 4 converts compatible known units when both scale and offset are omitted. |
| `valid_for` | Optional positive duration | Maximum time an update can be held, such as `200ms`, chosen from sampling and tolerated age. Zero, negative, null, and infinite durations are invalid. Default: three times `period` or the DBC message period. Missing required period information causes a configuration error. |
| `period` | Optional positive duration | Normal update period, used to derive omitted validity. Use acquisition settings or message specifications, such as `100ms`. Overrides the DBC message period; never inferred from adjacent timestamps. Omission can use DBC; zero/null are invalid. Does not create samples. |
| `conversion` | Optional object | Conversion after decoding. Version 4 infers the complete conversion only when both scale and offset are omitted, including in `{}`. If either coefficient is explicit, the other defaults to scale 1 or offset 0, and the complete pair is validated without an additional automatic conversion. Null is invalid. |
| `conversion.input_unit` | Optional nonempty string | Physical unit before extra conversion. In version 4, CAN omission reads it from the DBC; CSV/memory omission inherits `unit`, so supply the input unit when conversion is needed. Omit the field instead of using null: version 4 automatic conversion requires unit text. A nonempty DBC unit must exactly match the resulting input unit. |
| `conversion.scale` | Optional finite number | Formula: input × scale + offset. Version 4 infers the multiplier when both coefficients are omitted, for example 0.001 for mA → A. Otherwise omitted scale is 1. An explicit multiplier must match known units. Bool/enum require 1; Boolean literals cannot be coefficients. |
| `conversion.offset` | Optional finite number | Added after multiplication, in the target unit. Version 4 infers it when both coefficients are omitted, for example 273.15 for degC → K. Otherwise omitted offset is 0. An explicit offset must match known units. Bool/enum require zero. This is not a time offset; Boolean literals are invalid. |
| `code_dtype` | Optional string; version 4 enums only | Original integer type used by enum_code: int64 or uint64. The DBC can supply it for an unscaled integer CAN signal; otherwise declare it when it cannot be inferred. Omit it for label-only comparisons. It must match actual code type and range. |
| `choices` | List of two-item lists; CAN enum may use DBC; otherwise default `[]` | Map `[input code, analysis value]` using equipment definitions. Bool: `[[0,false],[1,true]]`; enum: `[[0,idle],[7,running]]`. Codes may be integers, Booleans, or strings, matched by type. Bool targets must be Boolean; enum targets nonempty text. CAN `dtype: enum` with omitted choices uses the DBC enumeration. Supply a manual table if needed; it replaces rather than merges the DBC table. Float decoded codes, including 0.5 or 1.0, cannot be mapped this way: retain numeric dtype and numeric conditions, without truncating or rescaling again. CSV/memory enums need a manual table. Omitted bool mapping accepts only native Booleans. Numeric signals do not use this field. |
| `valid_range` | Optional two-number list | Inclusive bounds after conversion, such as `[-100,100]` A; lower must not exceed upper. 101 A becomes `OUT_OF_RANGE`, not 100 or zero. Omission adds no physical-range restriction; type and missing-value checks still apply. `[]`/null are invalid. Not applicable to bool/enum. |
| `invalid_values` | Scalar list; default `[]` | Invalid sentinels matched by type and value before extra conversion. Check the parsed/decoded value: integer 65535 uses `[65535]`, not a converted 65.535. Omission/`[]` adds no sentinels; null is invalid. |
| `sample_policy` | String; default `backward_hold` | Only `backward_hold` is supported: retain the latest update within validity, without linear interpolation. Usually omit it. |
| `same_time_policy` | String; default `error` | `error` rejects conflicting same-time values, types, validity, or quality; identical updates may merge. `last_by_sequence` selects the largest stable source sequence. Choose from duplicate-record requirements, not magnitude or filename. |
| `semantic_id` | Nonempty string or null; default null | Business meaning for preset role lookup or requested tracing. Ordinary calculations can omit it. For auto lookup, use the [role table](presets.md#preset-role-requirements), such as `battery.current`, not a guessed name. Expressions use `name`, not the dotted ID. |
| `semantic_contract_version` | Nonempty string or null; default null | Version of the `semantic_id` meaning. Auto role lookup needs string `"1"` plus `semantic_id`, with matching units and role requirements. Ordinary signals can record other nonempty versions, which do not satisfy auto lookup. This is an independent business-role contract version. Automatic role lookup uses string `"1"`; it does not follow the integer analysis `config_version`. |
| `mapping_version` | Nonempty string or null; default null | Optional version of the input-to-signal mapping, such as `"meter-map-2026-01"`, assigned by the project maintainer. Update according to project practice when columns/DBC mappings change. Omission neither affects ordinary calculation nor generates a version. |
| `sign_convention` | Nonempty string or null; default null | Physical direction of positive/negative values, established from equipment and data. Charging-preset current requires `positive_is_charge`. Ordinary signals may omit it or use agreed text. It does not negate or calibrate input; incompatible direction requires explicit input handling. |
| `measurement_location` | Nonempty string or null; default null | Actual measurement point from wiring/sensor documentation. `pack_terminal` means the battery-pack terminal. Charging current/voltage roles require it, including explicit bindings. Ordinary signals may omit it or record agreed text. Names do not infer or alter the measurement point. |
| `metadata` | Mapping; default `{}` | Custom notes such as `{sensor_serial: S001}` under the project's own conventions. Omission/`{}` adds nothing. Metadata does not enable conversion or quality features. |

<a id="signal-field-decisions"></a>
<a id="can信号的默认值与报文集中绑定"></a>
## CAN defaults and grouped message bindings

CAN `dtype` and `unit` can be omitted. DBC lookup infers numeric types for numeric states, so conditions may use `state == 1` or `state == 0x1`. To use state text, declare `dtype: enum`; omitting `choices` then uses the DBC enumeration. A manual `choices` table replaces the DBC table without merging it.

A float DBC output, even `1.0`, cannot currently be an enum code. Manual `choices` does not remove this restriction. Use a numeric type such as `float64` and a numeric comparison; do not truncate or round to bypass it.

The loader reads the DBC when default metadata is missing and reuses the same database within that load. A missing DBC unit is `unknown`, not a confirmed physical unit. CSV and memory have no DBC and still need explicit type and unit. Reload the plan after changing its DBC.

Signals from one message can share location and period. This example uses separate companion files [pack.asc](../examples/grouped/pack.asc), [pack.dbc](../examples/grouped/pack.dbc), and [analysis.yaml](../examples/grouped/analysis.yaml) in the same directory. Message `0x120` contains `PackVoltage` and `ChargeState`; this excerpt cannot be inserted into the earlier `teaching.dbc` example.

The following section is already in the complete configuration. The DBC period of 100 ms gives voltage a default validity of 300 ms; state overrides it to 200 ms.

```yaml
signals:                       # Signals available to expressions
  - frame_id: 0x120            # Shared message location
    signals:                   # Signals available to expressions
      - name: voltage          # Name used to identify and reference this object
        signal: PackVoltage    # Exact signal name defined in the DBC
      - name: state            # Name used to identify and reference this object
        signal: ChargeState    # Exact signal name defined in the DBC
        dtype: enum            # Use the DBC enumeration
        valid_for: 200ms       # Override only this signal's validity
```

Actual outputs: [session results](../examples/grouped/results/会话结果.csv) and [event results](../examples/grouped/results/事件结果.csv). From their input/configuration directory run `chronaxis run analysis.yaml --output pack-result`. Voltage is 40, 42, and 41 V at 0, 0.1, and 0.2 seconds; `peak_voltage` is 42 V. State is idle, charging, idle, producing a charging rising edge at 0.1 seconds. An unrelated message at 0.4 seconds only establishes the source endpoint.

Groups can also share `channel`, `is_extended`, `is_fd`, `valid_for`, and `same_time_policy`. Children do not repeat source or message location. Their type, unit, choices, conversion, and quality settings remain independent. Grouping reduces declarations; it does not combine signal values or update times.

<a id="报文组与组内信号的字段位置"></a>
### Fields in a message group and its children

A message group is an alternative item structure in `signals`, not a single signal with group-level `name`/`field`.

| Location | Purpose and requirements |
|---|---|
| `signals[].frame_id` | Required message ID from the DBC, shared by all children. |
| `signals[].signals` | Required nonempty list of the message's selected signals. |
| Group `source` | Select `sources[].name` when the plan has several sources, even if only one is CAN. Omit only when the entire plan has one source. |
| Group `channel`, `is_extended`, `is_fd` | Optional shared channel and frame type; omission uses a unique match. Not allowed in children. |
| Group `period`, `valid_for`, `same_time_policy` | Optional shared defaults. A child's same-named field overrides only itself. |
| `signals[].signals[].signal` | Required DBC signal name belonging to the group's message. |
| `signals[].signals[].name` | Required analysis alias used by expressions. |
| Child type, unit, choices, conversion, quality, and semantic fields | Apply independently; use the single-signal options and the same CAN inference rules. |
| Forbidden child fields | `field`, `source`, `signals`, `frame_id`, `channel`, `is_extended`, and `is_fd`. Use another group for another message. |

For CAN source `bus` plus CSV source `meter`, place `source: bus` beside the group's `frame_id`, not inside each child. Having one CAN source does not mean the whole plan has one source.

<a id="不同来源怎样填写布尔值"></a>
### Boolean input by source

| Source | Without `choices` | For other encodings |
|---|---|---|
| `memory` | Native true/false in `values`. | Integers 0/1 need `[[0,false],[1,true]]`. |
| `signal_csv` | Exact lowercase cell text `true`/`false`. | `True`, `FALSE`, `1`, and surrounding whitespace do not convert automatically; supply matching choices. |
| CAN | Native bool returned by the reader. | Integer DBC codes 0/1 need explicit mapping; float codes cannot use it. |

CSV matches `reader.missing_values` before Boolean parsing. Thus a declared missing token `NA` becomes invalid rather than a Boolean-format error. Input codes must be unique by type and value; several codes may map to the same result, such as `[[0,false],[1,true],[2,true]]`. CSV also rejects text ambiguity: integer 1 and string `"1"` cannot both be input codes.

<a id="怎样选择转换编码和质量字段"></a>
## Choose conversion, encoding, and quality fields

First establish what CSV parsing or DBC decoding produces. These six settings address different needs. Raw CAN table `value_map` maps frame structure fields, not analysis signal codes.

| Field | When and how to choose it | Example and omission |
|---|---|---|
| `conversion.input_unit` | Use the CSV column or DBC-decoded physical unit; `unit` is the target. | Version 4 can obtain mA from CAN's DBC: target A converts 5000 to 5. CSV/memory need an explicit input mA. See [conversion](#signal-conversion). |
| `conversion.scale` | Usually omit in version 4 to infer a known unit conversion. | mA → A uses 0.001; A → A uses 1. Explicit -1 or 2 does not match A → A and is rejected. |
| `choices` | Map actual parsed codes using equipment definitions. | Bool integers need explicit mapping; CAN enum can use its DBC table. Other enum sources require mapping. See [encoding](#signal-choices). |
| `valid_range` | Use sensor limits or confirmed business limits in converted units; do not enlarge them to force success. | 5 A is within [-100,100]; 101 A becomes `OUT_OF_RANGE` until another valid update. Omission adds no range limit. |
| `invalid_values` | Use invalid sentinels from the specification, confirming decoded type and value. | CSV `65535.0` parses as an integer, so use `[65535]`. Default `[]` adds no sentinels. It does not intercept arbitrary parsing failures. See [original types](#signal-invalid-values). |
| `measurement_location` | Use the actual measurement point for required preset checks or requested tracing, not a guessed signal name. | `pack_terminal` means battery-pack terminal. Ordinary omission adds no location restriction; charging current/voltage roles reject missing or wrong location. See [preset roles](presets.md#preset-role-requirements). |

<a id="signal-choices"></a>
<a id="布尔和枚举"></a>
## Booleans and enumerations

Booleans represent true/false. Enumerations represent discrete state names such as `idle` and `running`, chosen according to equipment definitions; expressions must use the same spelling. Neither supports numeric scaling.

Using this page's `signal-types.asc` and DBC, [signal-bool-minimal.yaml](../examples/signal-bool-minimal.yaml) and [signal-enum-minimal.yaml](../examples/signal-enum-minimal.yaml) each contain a complete dataset, source, signals, and rising-edge rule. Run `chronaxis run FILE.yaml --output NEW-DIRECTORY`.

The Boolean example maps `Enabled` integer 0 to false and 1 to true: `condition: enabled` rises at 100 ms. The enum example obtains `ModeCode` 0→`idle`, 7→`running` from the DBC: `condition: mode == "running"` also produces one event at 100 ms. The 300 ms observation is the analysis endpoint and is outside the half-open session range.

[signal-state-combined.yaml](../examples/signal-state-combined.yaml) binds both signals and produces one `enabled_running` event at 100 ms. Replace the numeric example's signals, remove its calculations, and use the rule below. Both fields exist in this page's log/DBC. Manual choices demonstrate overriding DBC mapping; the ordinary minimal enum example omits them.

```yaml
signals:                                        # Signals available to expressions
  - choices:                                    # Map input codes to Boolean or enum analysis values
      - [0, false]                              # Input integer → Boolean
      - [1, true]
    field:                                      # Locate the original input field
      frame_id: '0x102'                         # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Enabled                           # Exact signal name defined in the DBC
    name: enabled                               # Name used to identify and reference this object
    valid_for: 200ms                            # Maximum time for retaining the latest valid reading
  - choices:                                    # Map input codes to Boolean or enum analysis values
      - [0, idle]                               # Input integer → state label
      - [7, running]
    field:                                      # Locate the original input field
      frame_id: '0x103'                         # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: ModeCode                          # Exact signal name defined in the DBC
    name: mode                                  # Name used to identify and reference this object
    valid_for: 200ms                            # Maximum time for retaining the latest valid reading
    dtype: enum                                 # Analysis value type
rules:                                          # Conditions or transitions that produce events
  - condition: enabled and mode == "running"    # Boolean expression used to select an activity
    name: enabled_running                       # Name used to identify and reference this object
    rule_type: rising_edge                      # Event detection algorithm
```

Each choice has exactly two values: input code and analysis value. `[7,running]` does not mean column 7; `field` selects the column. Bool targets must be YAML Booleans, not string `"true"`; enum targets must be nonempty text. A parseable but unmapped code becomes an invalid update and replaces the old state.

Codes match by type: integer `1`, Boolean `true`, and string `"1"` differ. CSV contains text, so declaring both integer 1 and string `"1"` creates an ambiguous cell representation and is rejected when constructing the source. Normal code text must not also be a missing-value token. Without choices, bool accepts only native Boolean input, never arbitrary nonzero numbers. Enum requires a manual table or readable DBC enumeration. Unparseable CSV text may fail the read; mapping does not turn every malformed value into unknown.

<a id="signal-conversion"></a>
<a id="dbc解码与信号额外换算"></a>
## DBC decoding and additional signal conversion

A CAN reader extracts bit-encoded values, then applies the DBC factor and offset. A CSV reader parses text as numbers or codes. Signal conversion acts on that reader output: `analysis value = reader value × scale + offset`. Do not repeat conversion already performed by the DBC.

| Reader output and target | Signal declaration | Result or check |
|---|---|---|
| Decoded 5000 mA, target A | Version 4: set unit A, omit scale/offset; CAN obtains mA from the DBC, while CSV/memory need conversion.input_unit mA. | 5 A |
| DBC already outputs 5 A, target A | Omit unit and conversion to use the DBC unit. | Remains 5 A |
| Decoded 25 degC, target K | Version 4: set unit K and omit scale/offset; CAN obtains degC from the DBC, while CSV/memory need conversion.input_unit degC. | 298.15 K |
| Known A → A with scale 2 or offset -2 | Rejected by the public entry point | Not an arbitrary calibration interface. |
| Known A → A with scale -1 | Rejected by the public entry point | `sign_convention` declares direction without changing values. |
| Either unit is outside the supported unit table | Finite scale/offset are applied as declared; compatibility is `unverified` | An unchecked unit relationship is not a verified conversion. |

Registered units include electrical units, time, temperature, temperature differences, angle, rotation speed, pressure, and compound units. See [expression unit rules](expressions.md) for the full scope. For example, degC → K permits offset 273.15; absolute temperatures and temperature differences are distinct.

Version 4 infers a conversion only when both scale and offset are omitted. Supplying either means a complete user-specified conversion, with the other defaulting to 1 or 0 respectively. Different unknown units need explicit, justified coefficients and remain `unverified`. An integer signal is promoted to float64 when its conversion multiplier or offset has a fractional part; an integer that cannot be represented exactly is marked `PRECISION_LOSS`. Public signals have no `direction_factor` field.

If calibration or direction reversal is required, explicitly preprocess input before Chronaxis—for example, multiply confirmed discharge-positive current by -1 into a new CSV column, then bind A → A with scale 1 and offset 0. Preserve the original file and record the formula. See the charging preset's [role requirements](presets.md#preset-role-requirements).

<a id="signal-invalid-values"></a>
<a id="原值类型与无效值"></a>
## Original types and invalid values

Before extra conversion, values have already been parsed/decoded; they may differ from both file text and raw CAN bits. `invalid_values` matches native type and value. Target `dtype: float64` does not first turn every input into a float for matching.

| CSV cell text | Reader value | Matching declaration |
|---|---|---|
| `65535` or `65535.0` | Integer 65535 | `[65535]`; `[65535.0]` does not match the integer. |
| `1.5` | Float 1.5 | `[1.5]` |
| `NA`, declared in `sources[].reader.missing_values` | Missing `None` | Prefer `missing_values` for textual missing markers. |
| `bad`, not a missing marker | Cannot parse as a number | Read error; it may never reach `invalid_values`. |

`missing_values` matches original CSV text; `invalid_values` matches parsed type and value. If DBC decoding converts raw code 65535 to 6553.5, declare the decoded value and type rather than copying raw bits.

<a id="读取失败和无效更新"></a>
## Read failures and invalid updates

Processing order is: parse/decode → check missing/non-finite values, input quality, and invalid sentinels → extra numeric conversion or bool/enum mapping → target type and range checks. See [Booleans and enumerations](#signal-choices) for code/text details.

| Input | Execution behavior | Action |
|---|---|---|
| Declared missing token `NA` | Invalid update replaces the previous value; analysis continues with missing-data quality. | Inspect affected periods and result completeness. |
| Undeclared invalid numeric text `bad` | CSV reading fails; public execution raises `AnalysisError`, preserving `SourceReadError`, `ValueError`, and the underlying decimal parsing exception in its cause chain. | Correct the cell or, after confirming its meaning, declare it missing. |
| Converted value outside `valid_range` | `OUT_OF_RANGE` invalid update; no clipping or replacement by zero. | Check input, units, and real business limits. |

`PlanValidationError` identifies invalid declaration paths. Invalid values reaching signal normalization are reflected in result `status`, `reason`, and `quality`. Arbitrary read failures cannot all be treated as `UNKNOWN` and ignored. See [troubleshooting](troubleshooting.md) and [results](results.md).

<a id="valid_for最近值可以沿用多久"></a>
## valid_for: how long the latest value can be held

Omitted `valid_for` uses three times the current signal's period: first explicit `period`, otherwise its DBC message period. Decoded CSV and memory signals can declare `period`. If a needed period is unavailable, provide `period` or `valid_for`; the program does not infer it from adjacent records. Although per-message calculations do not hold previous values, the public execution entry point still completes default validity for used signals, so a usable period, validity, or DBC period is needed there too. Formula `parameters.period` does not populate signal `period`.

A 100 ms voltage period gives 300 ms default validity; a 10 ms current period gives 30 ms. Each signal is independent: the driving signal's period does not become every signal's period. Explicit `valid_for: 500ms` overrides the default. Expiry always uses actual message time. Voltage updated at 1 second with 300 ms validity expires at 1.3 seconds, even if fixed-period accumulation advances more slowly.

Signal `period` does not automatically change a calculation's interval selection or an export resampling grid. Configure those features separately when required.

`valid_for: 3s` permits an update to be held for at most 3 seconds while observation supports it. A new update replaces the old one; without an update, the value becomes unknown exactly at expiry. This is neither sample frequency, event timeout, nor `minimum_duration` confirmation time.

Quick-start power updates occur at 0, 1, 3, and 4 seconds with 2, 4, 8, and 10 W. Their gaps are 1, 2, and 1 seconds. The unrelated `0x7FE` frame at 6 seconds establishes the source endpoint, not a fifth power sample. The last `[4,6)` interval holds 10 W when validity permits:

| Latest update | Validity 3 seconds | Validity 1 second |
|---|---|---|
| 0 s: 2 W | Hold 2 W on `[0,1)`, then replace with 4 W. | Same. |
| 1 s: 4 W | Hold 4 W on `[1,3)`. | 4 W on `[1,2)`; invalid on `[2,3)`. |
| 3 s: 8 W | Hold 8 W on `[3,4)`, then replace with 10 W. | Same. |
| 4 s: 10 W | Hold 10 W on `[4,6)`. | 10 W on `[4,5)`; invalid on `[5,6)`. |

The old value excludes its expiry endpoint. An effective new update exactly then supplies the value from that time. If `NA` arrives at 2 seconds, even 3-second validity cannot retain the old 4 W: the value becomes unknown at 2 seconds. Observation ending at 6 seconds does not let validity create data beyond 6 seconds.

Related pages: [inputs](inputs.md), [expressions](expressions.md), and [business presets](presets.md).

## Read an enum's original integer code

Use `mode == 'ready'` for a label comparison; no code type is needed. If a DBC labels both 7 and 9 as ready but only code 9 should count, use `enum_code(mode) == 9` in version 4. For an unscaled integer CAN signal the DBC supplies signedness. Otherwise, when the original integer type is not known, declare `code_dtype: uint64` or `int64` on the enum signal to match the data. A text label alone cannot tell you whether its original code was 7 or 9.

Before the first sample arrives, integer, Boolean, and enum signals remain unknown. A choices mapping only explains codes after they arrive. An unmapped code or explicit invalid update replaces the previous valid state. A DBC label such as Invalid does not automatically mark a value invalid; invalid_values must use the decoded value before extra conversion, not an unscaled raw code.
