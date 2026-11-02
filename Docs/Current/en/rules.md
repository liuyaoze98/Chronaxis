<a id="事件检测规则"></a>
# Event detection rules

Rules turn signal values into events. A **point event** has a timestamp, such as a button being pressed. An **activity event** has a start, end, and duration, such as a nine-second temperature alarm. Define rules in the `rules` list. Windows and calculations refer to each rule by its `name`.

Unless stated otherwise, examples use the default `actual` interval. With `fixed` or `dbc`, sustained-condition confirmation, waiting deadlines, change windows, and pairing `delay_ns` use the selected period. Original timestamps and signal expiry still use actual time. See the [three duration bases](intervals.md#timing-basis).

<a id="规则类型选择"></a>
## Choose a rule type

Every rule requires [`name`](#rule-id) and [`rule_type`](#rule-rule_type). Required fields have no default; omission is an error. Optional fields use the listed defaults. Unlisted fields are rejected. Each rule's detailed table below explains its fields.

| `rule_type` | Required fields | Optional fields and defaults | Use it for |
|---|---|---|---|
| [`condition_duration`](#rule-duration) | `condition`, `minimum_duration` | `duration_comparison: ">="`, `selection_origin: onset` | Record an activity after a condition remains true for a required duration. |
| [`rising_edge`](#rule-rising_edge) | `condition` | `emit_initial: false` | Record the instant a button changes from released to pressed. |
| [`falling_edge`](#rule-falling_edge) | `condition` | `emit_initial: false`; true is forbidden | Record the instant a button changes from pressed to released. |
| [`start_only`](#rule-start-only) | `condition`, `window_duration` | `emit_initial: false` | Trigger a fixed capture interval and suppress further triggers during it. |
| [`debounce`](#rule-debounce) | `condition` | `enter_delay: 0s`, `exit_delay: 0s` | Ignore short true/false fluctuations and change activity state only after a wait. |
| [`hysteresis`](#rule-hysteresis) | `enter_condition`, `exit_condition` | `enter_delay: 0s`, `exit_delay: 0s` | Start an alarm at 80, clear it at 75, and retain the previous state between them. |
| [`start_end`](#rule-start-end) | `start_condition`, `end_condition` | `timeout: null`, `emit_initial: true` | Start on a start signal, finish on an end signal, optionally limit the wait. |
| [`window_delta`](#rule-window-delta) | `signal`, `window`, `direction`, `threshold` | `monotonic: false`, `coverage_policy: full`, `emit_initial: false`, `retrigger: edge` | Record a point when voltage rises by at least 5 V over the last 4 s. |

<a id="每种规则的完整案例"></a>
## Complete examples for every rule

Each file contains its own synthetic input, source, and signals, and only the fields needed for that example. Run `chronaxis run filename.yaml --output new-directory`. Expected times below come from each linked input, not from the shared teaching file later on this page.

| Feature | Minimal configuration | Extended configuration | Independent expected result |
|---|---|---|---|
| `condition_duration` | [Minimal](../examples/rule-condition_duration-minimal.yaml) | [Extended](../examples/rule-condition_duration-extended.yaml) | Minimal activity [1,6), confirmed at 3 s. Extended integrates only [3,6): 10 W × 3 s = 30 J. |
| `rising_edge` | [Minimal](../examples/rule-rising_edge-minimal.yaml) | [Extended](../examples/rule-rising_edge-extended.yaml) | Point at 1 s. Extended selects [1,2) and returns 10 J. |
| `falling_edge` | [Minimal](../examples/rule-falling_edge-minimal.yaml) | [Extended](../examples/rule-falling_edge-extended.yaml) | Point at 5 s. Extended selects [5,6) and returns 10 J. |
| `start_only` | [Minimal](../examples/rule-start_only-minimal.yaml) | [Extended](../examples/rule-start_only-extended.yaml) | Points at 1 and 6 s. Extended creates [1,6) and [6,11); the trigger at 3 s is suppressed. |
| `debounce` | [Minimal](../examples/rule-debounce-minimal.yaml) | [Extended](../examples/rule-debounce-extended.yaml) | Minimal activity [1,5). Extended waits 2 s to enter and 3 s to exit: [3,8). |
| `hysteresis` | [Minimal](../examples/rule-hysteresis-minimal.yaml) | [Extended](../examples/rule-hysteresis-extended.yaml) | Minimal activity [1,6). Extended waits 1 s for both transitions: [2,7). |
| `start_end` | [Minimal](../examples/rule-start_end-minimal.yaml) | [Extended](../examples/rule-start_end-extended.yaml) | Minimal closes normally at [1,5). Extended times out after 2 s: [1,3). |
| `window_delta` | [Minimal](../examples/rule-window_delta-minimal.yaml) | [Extended](../examples/rule-window_delta-extended.yaml) | Minimal suppresses the first already-matching complete window and triggers at 12 s. Extended enables initial emission and monotonic checking, triggering at 4 and 12 s. |

[rule_examples.py](../examples/rule_examples.py) checks the 18 rule/derived examples against independent expectations. Run `python rule_examples.py --output new-directory` to check event boundaries, confirmation times, timeout status, selected windows, and integrals.

<a id="先准备来源和信号"></a>
## Prepare sources and signals

The complete [teaching-base.yaml](../examples/teaching-base.yaml) references synthetic ASC frames and a DBC, and analyzes the entire observed range. Its relevant signal definitions are shown below for reference; do not insert them a second time. Conceptual timelines in individual sections illustrate that rule's behavior. Use the dedicated examples above for fixed, runnable expected results.

There is one CAN source, so individual signal definitions need no repeated `source`. IDs and signal names come from the included DBC; types and units are inferred. The explicit 20 s validity keeps sparse teaching records valid between updates and is not a recommended setting for a real device.

```yaml
signals:                     # Signals used by the rule examples.
  - name: temperature        # Name referenced in expressions.
    field:                   # Original CAN signal.
      frame_id: '0x11d'      # Message ID from the DBC.
      signal: Temperature    # Case-sensitive DBC signal name.
    valid_for: 20s           # Validity for these sparse teaching records.
  - name: power              # Power alias.
    field:                   # Original CAN signal.
      frame_id: '0x100'      # Message ID from the DBC.
      signal: Power          # DBC signal name.
    valid_for: 20s           # Validity for this example.
  - name: voltage            # Voltage alias.
    field:                   # Original CAN signal.
      frame_id: '0x11f'      # Message ID from the DBC.
      signal: Voltage        # DBC signal name.
    valid_for: 20s           # Validity for this example.
  - name: button_pressed     # Boolean button state.
    field:                   # Original CAN signal.
      frame_id: '0x113'      # Message ID from the DBC.
      signal: ButtonPressed  # DBC signal name.
    valid_for: 20s           # Validity for this example.
    choices:                 # Input code to analysis value.
      - [0, false]
      - [1, true]
  - name: start_signal       # Boolean start state.
    field:                   # Original CAN signal.
      frame_id: '0x11c'      # Message ID from the DBC.
      signal: StartSignal    # DBC signal name.
    valid_for: 20s           # Validity for this example.
    choices:                 # Input code to analysis value.
      - [0, false]
      - [1, true]
  - name: end_signal         # Boolean end state.
    field:                   # Original CAN signal.
      frame_id: '0x117'      # Message ID from the DBC.
      signal: EndSignal      # DBC signal name.
    valid_for: 20s           # Validity for this example.
    choices:                 # Input code to analysis value.
      - [0, false]
      - [1, true]
```

<a id="所有规则共用的填写方式"></a>
## Common fields and conventions

The field tables on this page are relative to `rules[]`, for example `rules[].name`. Fields belonging to nested objects are identified explicitly. Do not place these fields directly at the configuration root.

| Field | Type | Required / default | Purpose |
|---|---|---|---|
| <a id="rule-id"></a>`name` | String | Required; no default | Unique rule name, such as `hot`. A window using `rule: hot` selects events produced by this rule. |
| <a id="rule-rule_type"></a>`rule_type` | String | Required; no default | Detection algorithm from the table above. |

Names start with an English letter or underscore, followed by letters, digits, or underscores, for example `hot_1`. Python keywords, `abs`, and `isclose` are reserved. Rule, window, and calculation names must be unique within one plan.

Time-dependent rules may define an `interval`; omission inherits `intervals.default`. Pure rising and falling edges reject `interval`. See [calculation intervals](intervals.md).

A condition is a boolean expression such as `temperature >= 80`. The name must already exist in `signals` or `derived`. Numeric signals require a comparison; `temperature` alone is not a condition. A declared boolean signal such as `button_pressed` can be used directly. A condition may be true, false, or unknown because a value is missing, expired, or cannot be calculated. Unknown is not false: unknown → true does not prove a false → true transition occurred. See [expressions](expressions.md) for all operators.

Examples use synthetic degC temperatures, V voltages, and boolean switches. Unless a gap is mentioned, values remain valid between records and observation continues through the example's end. Actual input validity comes from `valid_for`. Each fragment below includes its parent key and replaces the corresponding root section of `teaching-base.yaml`; do not nest a `rules` key inside a rule list item.

Durations are strings using `ns`, `us`, `ms`, or `s`, such as `500ms` or `2s`. A bare number `2` is invalid; write one minute as `60s`, not `1min`. Nonnegative durations allow `0s`; positive durations must convert to at least one integer nanosecond. Lower-level typed Python fields ending in `_ns` take integers, for example 2000000000 for 2 s. YAML uses `true`, `false`, and `null`; Python uses `True`, `False`, and `None`. Expressions inside strings have their own syntax. See [configuration language](configuration-language.md).

<a id="rule-duration"></a>
<a id="持续条件检测-condition_duration"></a>
## Sustained conditions: `condition_duration`

To record temperature remaining at least 80 for 2 s, add or replace the root `rules` section in [teaching-base.yaml](../examples/teaching-base.yaml):

```yaml
rules:                             # Event detection rules.
  - name: hot                      # Name used by windows and calculations.
    condition: temperature >= 80   # Condition that must remain true.
    minimum_duration: 2s           # Required continuous duration.
    rule_type: condition_duration  # Sustained-condition detector.
```

| Field | Type | Required / default | Meaning and allowed values |
|---|---|---|---|
| <a id="duration-condition"></a>`condition` | String | Required | Boolean expression using defined signals. Here temperature >= 80 is true; below 80 is false. |
| <a id="duration-duration"></a>`minimum_duration` | Duration string | Required | Nonnegative minimum continuous duration. `2s` rejects a 1.9 s activity; `0s` removes the wait. |
| `duration_comparison` | String | Optional; `>=` | `>=` includes the threshold; `>` requires strictly longer. Exactly 60 s satisfies only `>=`; 60.000000001 s satisfies both. For “over 60 s”, use `>` rather than changing the threshold to 60.1 s. |
| <a id="duration-selection-origin"></a>`selection_origin` | String | Optional; `onset` | `onset` includes the confirmation wait in event calculations; `confirmed` starts calculation at confirmation. |

<a id="selection_origin事件计算的起点"></a>
<a id="selection_origin-事件计算的起点"></a>
### `selection_origin`: where an event calculation starts

Suppose temperature reaches 80 at 1 s, remains at or above 80 through 3 s, and falls below 80 at 6 s. The activity meets its 2 s requirement at 3 s, its **confirmation time**.

| Setting | Selected calculation range | Energy at a constant 10 W |
|---|---|---|
| `onset` | 1–6 s, including the confirmation wait: 5 s | 50 J |
| `confirmed` | 3–6 s, excluding the wait: 3 s | 30 J |

Write `selection_origin: confirmed` to change the calculation start. It does not change the condition that qualifies the activity.

Replace the root `rules` and `calculations` sections of the teaching base with:

```yaml
rules:                             # Detection rules.
  - name: hot                      # Rule selected by the calculation below.
    condition: temperature >= 80   # Required condition.
    selection_origin: confirmed    # Exclude the confirmation wait from calculations.
    minimum_duration: 2s           # Require two continuous seconds.
    rule_type: condition_duration  # Sustained-condition detector.
calculations:                      # Requested results.
  - name: hot_energy               # Calculation name.
    expr: power                    # Previously defined power signal in W.
    operation: integral            # Accumulate energy in J.
    scope:                         # Calculate once for each activity.
      rule: hot                    # Select activities from this rule.
```

For the timeline above, this returns 30 J; changing `confirmed` to `onset` returns 50 J. Both use the same 2 s qualification requirement.

A separate window that includes 1 s before and after the activity spans 0–7 s. `selection_origin` does not change that window: it still follows the activity's actual boundaries. See [activity context and energy](windows.md#activity-context-example).

If the condition starts at 1 s and ends exactly at 3 s, it still qualifies under the default `>=`. `onset` selects [1,3). With `confirmed`, confirmation and end coincide, so time calculations return null with a zero-length-range reason.

A confirmed activity closes normally when the condition becomes false. Missing or expired input closes it as a data interruption. If the condition remains true when observation ends, the result indicates that observation ended before the activity's actual end was known.

<a id="rule-rising_edge"></a>
<a id="上升沿检测-rising_edge"></a>
## Rising edges: `rising_edge`

Replace the teaching base's root `rules` with:

```yaml
rules:                         # Detection rules.
  - name: pressed              # Point-event rule name.
    condition: button_pressed  # Previously defined boolean signal.
    rule_type: rising_edge     # Detect false-to-true transitions.
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| <a id="rising_edge-condition"></a>`condition` | String | Required | Boolean signal name or condition; detect false → true. |
| <a id="rising_edge-emit-initial"></a>`emit_initial` | Boolean | Optional; `false` | `true` emits a point when the first known initial value is true; `false` does not. Recovery after a later gap is not another initial observation. |

For false at 0 s, true at 1 and 2 s, false at 3 s, and true at 4 s, the points are 1 and 4 s. If the first value at 0 s is true, only `emit_initial: true` emits at 0 s. Missing → true is not an observed press. A condition that remains true does not emit on every record.

<a id="rule-falling_edge"></a>
<a id="下降沿检测-falling_edge"></a>
## Falling edges: `falling_edge`

Replace the teaching base's root `rules` with:

```yaml
rules:                         # Detection rules.
  - name: released             # Point-event rule name.
    condition: button_pressed  # Previously defined boolean signal.
    rule_type: falling_edge    # Detect true-to-false transitions.
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| <a id="falling_edge-condition"></a>`condition` | String | Required | Boolean signal or condition; detect true → false. |
| <a id="falling_edge-emit-initial"></a>`emit_initial` | Boolean | Optional; `false` | Only `false` is allowed. An initially released button does not establish that a release just occurred; `true` is a configuration error. |

The preceding 0–4 s button timeline emits only at 3 s. Unknown → false is not a falling edge. An initially true value does not emit a point either.

<a id="rule-start-only"></a>
<a id="带重复触发屏蔽的起点检测-start_only"></a>
## Start points with trigger suppression: `start_only`

Replace the teaching base's root `rules` with:

```yaml
rules:                         # Detection rules.
  - name: capture              # Name referenced by the capture window.
    condition: button_pressed  # Trigger on false-to-true transitions.
    window_duration: 5s        # Suppress further triggers for this duration.
    rule_type: start_only      # Start-point detector with suppression.
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| <a id="start-only-condition"></a>`condition` | String | Required | Boolean signal or condition. False → true triggers only outside the preceding trigger's suppression interval. |
| <a id="start-only-window-duration"></a>`window_duration` | Duration string | Required | Positive suppression duration. A 1 s trigger with `5s` suppresses new triggers before 6 s; exactly 6 s is allowed. |
| <a id="start-only-emit-initial"></a>`emit_initial` | Boolean | Optional; `false` | `true` permits one trigger for an initially true value. Later triggers still require new false → true transitions. |

False → true transitions at 1, 3, and 6 s produce points at 1 and 6 s. The suppressed 3 s trigger is discarded, not postponed to 6 s. If the condition remains true after 1 s, expiry at 6 s does not automatically retrigger.

The rule outputs points. To select the associated time ranges, retain that rule and add or replace the root `windows` section:

```yaml
windows:                # Windows selected from rule events.
  - name: capture_data  # Window name for calculations or exports.
    rule: capture       # Previously defined start_only rule.
```

Omitted `post` inherits `window_duration`; an explicit `post` must equal it. This yields [1,6) and [6,11). Set `pre` separately to include earlier data. See [window fields](windows.md#window-fields).

<a id="rule-debounce"></a>
<a id="去抖动活动检测-debounce"></a>
## Debounced activities: `debounce`

Replace the teaching base's root `rules` with:

```yaml
rules:                         # Detection rules.
  - name: stable_pressed       # Activity rule name.
    condition: button_pressed  # True enters; false exits.
    enter_delay: 2s            # Require stable true before entering.
    exit_delay: 3s             # Require stable false before exiting.
    rule_type: debounce        # Ignore shorter fluctuations.
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| <a id="debounce-condition"></a>`condition` | String | Required | Boolean signal or condition; true prepares entry, false prepares exit. |
| <a id="debounce-enter-delay"></a>`enter_delay` | Nonnegative duration string | Optional; `0s` | Continuous true duration before activity starts. True at 1 s with `2s` starts at 3 s. False during the wait cancels it. Zero starts immediately. |
| <a id="debounce-exit-delay"></a>`exit_delay` | Nonnegative duration string | Optional; `0s` | Continuous false duration before activity ends. False at 5 s with `3s` ends at 8 s; those 3 s remain part of the activity. True during the wait cancels exit. Zero ends immediately. |

| Time | Button | Processing |
|---|---|---|
| 1 s | Pressed | Start entry wait. |
| 3 s | Still pressed | Two stable seconds elapsed; activity starts. |
| 5 s | Released | Start exit wait; activity continues. |
| 8 s | Still released | Three stable seconds elapsed; activity ends. |

The activity is [3,8), lasting 5 s. The entry wait is excluded, while the exit wait is included. This differs from `condition_duration`.

Release at 1.5 s prevents entry because the press lasted under 2 s. Pressing again at 6 s cancels the pending exit because release lasted under 3 s. Missing or expired data interrupts the decision; recovery starts a fresh wait, and missing time cannot count as stable.

<a id="rule-hysteresis"></a>
<a id="迟滞活动检测-hysteresis"></a>
## Hysteresis activities: `hysteresis`

Using 80 for both alarm entry and exit can repeatedly switch the alarm around that value. Hysteresis can enter at 80 and clear at 75 instead. At 77, an existing alarm stays on and an existing non-alarm state stays off.

Replace the teaching base's root `rules` with:

```yaml
rules:                                  # Detection rules.
  - name: alarm                         # Activity rule name.
    enter_condition: temperature >= 80  # Enter at the upper threshold.
    exit_condition: temperature <= 75   # Clear at the lower threshold.
    rule_type: hysteresis               # Retain known state between thresholds.
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| <a id="hysteresis-enter-condition"></a>`enter_condition` | String | Required | Entry condition using defined signals and their units. If `enter_delay` is set, it must remain true for that duration. |
| <a id="hysteresis-exit-condition"></a>`exit_condition` | String | Required | Exit condition. Between thresholds, retain the previously known state. Entry and exit must not overlap. |
| <a id="hysteresis-enter-delay"></a>`enter_delay` | Nonnegative duration string | Optional; `0s` | Continuous entry-condition wait. With `2s`, reaching 80 then falling to 77 before the wait completes cancels entry. |
| <a id="hysteresis-exit-delay"></a>`exit_delay` | Nonnegative duration string | Optional; `0s` | Continuous exit-condition wait. With `3s`, reaching 75 then returning to 77 before completion cancels exit; the alarm continues. |

| Time | Temperature | Alarm state |
|---|---|---|
| 0 s | 85 | Entry condition met: alarm begins. |
| 3 s | 77 | Neither condition holds: retain alarm. |
| 6 s | 77 | Still in alarm, including when this record belongs to the next continuous file. |
| 9 s | 75 | Exit condition met: alarm ends. |
| 12 s | 70 | No alarm. |

This produces [0,9), lasting 9 s. The square bracket includes 0 s; the parenthesis excludes 9 s, whose value 75 belongs to the state after exit. Mean temperature over the activity is `(85 × 3 + 77 × 6) / 9 = 239/3`.

If the first record is 77, the preceding state is unknown. Missing or expired data interrupts an active alarm; recovery at 77 does not prove it should resume. Both conditions true is an error, not a priority choice. If either condition cannot be evaluated, state becomes unknown.

`debounce` is the corresponding stable-wait rule with entry `condition` and exit `not condition`. Neither debounce nor hysteresis accepts `duration` or `emit_initial`. Here `degC` is an explicit unit label; this release does not automatically convert it to K.

<a id="rule-start-end"></a>
<a id="开始结束活动检测-start_end"></a>
## Start/end activities: `start_end`

Replace the teaching base's root `rules` with:

```yaml
rules:                             # Detection rules.
  - name: cycle                    # Activity rule name.
    start_condition: start_signal  # Start on the selected condition.
    end_condition: end_signal      # End when this condition is true.
    timeout: 5s                    # Maximum duration from activity start.
    rule_type: start_end           # Start/end detector.
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| <a id="start-end-start-condition"></a>`start_condition` | String | Required | Boolean signal or condition. False → true starts an activity; `emit_initial` controls an initially true value. |
| <a id="start-end-end-condition"></a>`end_condition` | String | Required | After entry, true ends the activity without requiring a new rising edge. If already true at entry, no zero-length activity is output. |
| <a id="start-end-timeout"></a>`timeout` | Positive duration string or null | Optional; `null` | Maximum duration from start. `5s` makes an activity starting at 4 s expire at 9 s. Omission/null means no limit; zero is invalid. Early observation end or missing end data cannot establish a timeout. |
| <a id="start-end-emit-initial"></a>`emit_initial` | Boolean | Optional; `true` | Start if the first known start value is true. With false, wait for a later false → true transition. Its default differs from rising-edge detection. |

An activity starting at 4 s and still unfinished at 9 s produces [4,9) with status `timeout`. If the end condition becomes true exactly at 9 s, normal completion wins and status is `closed`. If observation ends at 7 s, the result indicates incomplete observation rather than a device timeout.

Start signals arriving during an activity are not queued. After it ends, a fresh false → true transition is required. A start condition that stays true from 4 s does not immediately start another activity after the 9 s end. Simultaneous start and end do not produce a zero-length activity.

Once active, missing start data does not directly terminate the activity. Missing end data interrupts it because its end can no longer be determined. A supplied timeout must be positive.

The [runnable example](examples.md#start-end-case) produces normal [0,2), timed-out [4,9), and normal [11,14) activities, with respective signal means 10, 52, and 110. Legacy Sclicer's `start_end` has a different meaning; read [migration](migration.md) before conversion.

<a id="rule-window-delta"></a>
<a id="滑动窗口变化量检测-window_delta"></a>
## Changes over a sliding window: `window_delta`

Replace the teaching base's root `rules` with this minimal rule:

```yaml
rules:                       # Detection rules.
  - name: change             # Point-event rule name.
    signal: voltage          # Numeric signal or expression to compare.
    window: 4s               # History length used for the change.
    direction: rise          # Detect an increase.
    threshold: 5             # Required change, in the signal's unit.
    rule_type: window_delta  # Sliding-window change detector.
```

To require monotonic movement and permit an initially matching complete window, replace the same section with:

```yaml
rules:                       # Detection rules.
  - name: change             # Point-event rule name.
    signal: voltage          # Numeric value to compare.
    window: 4s               # History length.
    direction: rise          # Detect an increase.
    threshold: 5             # Required change in V.
    monotonic: true          # Reject reversals within the window.
    emit_initial: true       # Emit for the first complete matching window.
    rule_type: window_delta  # Sliding-window change detector.
```

| Field | Type | Required / default | Meaning and allowed values |
|---|---|---|---|
| <a id="window-delta-signal"></a>`signal` | String | Required | Numeric signal or supported numeric expression, such as `voltage * 2`. A boolean expression such as `voltage > 5` is invalid. |
| <a id="window-delta-window"></a>`window` | Positive duration string | Required | History length. Under actual time, a 4 s window at 6 s compares 2–6 s; it is neither a four-record count nor a four-second evaluation frequency. |
| <a id="window-delta-direction"></a>`direction` | String | Required | `rise`, `fall`, or `any`, as explained below. |
| <a id="window-delta-threshold"></a>`threshold` | Finite nonnegative number | Required | Inclusive change threshold in the signal's unit. For voltage, number `5` means 5 V; do not write `"5V"`. This is not a rate in V/s. |
| <a id="window-delta-monotonic"></a>`monotonic` | Boolean | Optional; `false` | False compares endpoints. True also forbids reversals: rise must never decrease, fall must never increase, any must move in one direction. Equal plateaus are allowed. |
| <a id="window-delta-coverage-policy"></a>`coverage_policy` | String | Optional; `full` | Only `full` is accepted: the entire window needs valid data. Valid endpoints cannot compensate for a gap in the middle. |
| <a id="window-delta-emit-initial"></a>`emit_initial` | Boolean | Optional; `false` | True permits a point for the first complete evaluable window if it already matches. It does not fill gaps; recovery after a later gap is not another initial window. |
| <a id="window-delta-retrigger"></a>`retrigger` | String | Optional; `edge` | `edge` emits on each nonmatching → matching transition. `once` emits at most once per session, without relaxing the initial requirements. Neither repeatedly emits while the condition stays true. |

| Direction | Change compared with `threshold` | Change from 2 V to 7 V |
|---|---|---|
| `rise` | End minus start | 5 V |
| `fall` | Start minus end | −5 V, so not a fall of at least 5 V |
| `any` | Absolute endpoint difference | 5 V |

For voltages 0, 0, 5, 5, 0, 0, 5, 5 V at 0, 2, 4, 6, 8, 10, 12, 14 s, the extended rule emits at 4 and 12 s. A window extending 1 s before and after each point has mean voltage 2.5 V.

A 4 s history needs four full seconds of valid data. Missing or expired data inside it prevents a decision. The path 0 → 10 → 5 V has a net rise of 5 V but is not monotonically rising. If analysis starts at 10 s, the program does not silently read earlier data to fill the window; the earliest complete window is at 14 s.

In actual mode a moving window can change even without a new record. Suppose voltage is 4 V at 0 s, 0 V at 1 s, and 8 V from 2 s onward, all remaining valid. At 4 s the window includes the 4 → 0 fall and fails monotonic rise. At 5 s it covers 1–5 s, excludes that fall, and can qualify.

This rule outputs points showing when its change condition becomes satisfied. Define a separate window to calculate voltage around those points.

<a id="配窗口和计算项"></a>
## Add windows and calculations

Activity rules use an activity anchor; point rules use a point anchor. The appropriate default is inferred from the rule. To include 2 s before and after the earlier `alarm` activity, keep that hysteresis rule and add or replace these root sections in the teaching base:

```yaml
windows:                           # Selected context around events.
  - name: context                  # Window name.
    rule: alarm                    # Previously defined hysteresis rule.
    pre: 2s                        # Include two seconds before activity start.
    post: 2s                       # Include two seconds after activity end.
calculations:                      # Requested results.
  - name: mean_temperature         # Calculation name.
    expr: temperature              # Previously defined signal.
    operation: time_weighted_mean  # Weight each valid value by duration.
    scope:                         # Calculate for each selected window.
      window: context              # Window definition above.
```

This calculates the mean from 2 s before alarm entry to 2 s after exit. Use `scope: {rule: alarm}` for the alarm activity alone. Unobserved context remains missing; temperatures are not invented to fill it.

See [window configuration](windows.md#window-fields) for merging windows from multiple alarms and [sequences](sequences.md) for request/response pairing. Lower-level parameters are described in [stability](../reference/chronaxis.core.stability.md), [window_delta](../reference/chronaxis.core.window_delta.md), and [rule parsing](../reference/chronaxis.planning.nodes.md) (Chinese implementation references).

<a id="严格超过指定时长"></a>
### Strictly longer than a duration

`minimum_duration: 60s` with `duration_comparison: ">"` requires strictly more than 60 continuous seconds. The default `selection_origin: onset` still integrates the entire qualifying activity; only explicit `confirmed` starts at confirmation.

With 1 ns time precision, actual mode confirms at the first representable instant after 60 s. Fixed/DBC mode advances only on selected messages: exactly 60 s does not qualify, and confirmation waits for the record that takes accumulation beyond 60 s. Continuous file boundaries do not reset the candidate, but invalid updates and expired validity still interrupt continuity.
