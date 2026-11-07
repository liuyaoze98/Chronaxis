<a id="完整任务事件窗口与能量"></a>
# Complete task: detect an activity, select a window, and calculate energy

This example detects a temperature of at least 80 °C sustained for 2 seconds, selects a window extending 1 second before and after the activity, and calculates energy for both ranges. `rules` detect events, `windows` select surrounding ranges, and a calculation's `scope` selects which range it uses. See the [example results](example-results.md#activity-yaml).

Complete [installation](installation.md) and the [quick start](quickstart.md) first.

<a id="输入与完整配置"></a>
## 1. Input and complete configuration

The supplied files are [activity.asc](../examples/data/can/activity.asc), [teaching.dbc](../examples/data/can/teaching.dbc), and the annotated [activity.yaml](../examples/activity.yaml).

| Time (s) | Temperature (°C) | Power (W) |
|---|---|---|
| 0 | 70 | 10 |
| 1 | 80 | 10 |
| 3 | 80 | 10 |
| 6 | 70 | 10 |
| 7 | 70 | 10 |

The configuration sets `valid_for: 4s` to cover the longest update gap of 3 seconds. The observed range is `[0, 7)`. Types and units come from the DBC; the last record establishes the observation endpoint.

<a id="来源与信号绑定"></a>
## 2. Bind the source and signals

This is the source and signal portion of the complete configuration. Replace the corresponding sections; do not append duplicate root keys.

```yaml
sources:                          # Input sources used by this analysis
  - paths: data/can/activity.asc  # File, continuous file list or directory; relative to this configuration
    dbc_by_channel:               # DBC files indexed by user-facing CAN channel
      '1': data/can/teaching.dbc  # DBC for channel 1; channel keys are strings
signals:                          # Signals available to expressions
  - name: temperature             # Alias used in the rule
    field:                        # Locate the original input field
      frame_id: '0x11d'           # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Temperature         # Exact signal name defined in the DBC
    valid_for: 4s                 # Maximum age of the latest value
  - name: power                   # Alias used in the calculations
    field:                        # Locate the original input field
      frame_id: '0x100'           # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Power               # Exact signal name defined in the DBC
    valid_for: 4s                 # Maximum time for retaining the latest valid reading
```

<a id="三个配置部分如何配合"></a>
## 3. Connect the rule, window, and calculations

The following excerpt is not a standalone configuration. Keep `config_version`, `dataset`, and the input declarations from the complete example.

```yaml
rules:                             # Conditions or transitions that produce events
  - name: hot                      # Name used to identify and reference this object
    rule_type: condition_duration  # Event detection algorithm
    condition: temperature >= 80   # Enter the candidate activity
    duration_comparison: ">="      # Include the threshold; use > for strictly longer.
    minimum_duration: 2s           # Confirm after 2 seconds
windows:                           # Time ranges selected around events
  - name: hot_context              # Name used to identify and reference this object
    rule: hot                      # Window around this rule's activity
    pre: 1s                        # Time to include before the event
    post: 1s                       # Time to include after the event
calculations:                      # Requested statistics or selected rows
  - name: event_energy             # Name used to identify and reference this object
    scope:                         # Session, event or window over which to calculate
      rule: hot                    # Integrate over the activity
    operation: integral            # Calculation to apply to the expression
    expr: power                    # Formula using the declared signal or derived names
  - name: context_energy           # Name used to identify and reference this object
    scope:                         # Session, event or window over which to calculate
      window: hot_context          # Integrate over the window
    operation: integral            # Calculation to apply to the expression
    expr: power                    # Formula using the declared signal or derived names
```

<a id="运行并核对"></a>
## 4. Run and check

From the repository root, run the following commands. In the offline examples directory, use `activity.yaml` as the configuration path. The output directory can be reused; every publication adds a timestamp to its filenames.

```powershell
chronaxis validate Docs/Current/examples/activity.yaml
chronaxis run Docs/Current/examples/activity.yaml --output activity-result
```

| File | Expected result |
|---|---|
| `事件结果.csv` (event results) | `hot` starts at 1 s, is confirmed at 3 s, and ends at 6 s; `event_energy（J）` is 50 with status `完整` (complete). |
| `窗口结果.csv` (window results) | `hot_context` covers `[0, 7)`, refers to interval 1, and has `context_energy（J）` of 70 with status `完整`. |

The activity lasts 5 seconds, so its energy is `10 W × 5 s = 50 J`. The window lasts 7 seconds and contains `70 J`.

Changing only `selection_origin` to `confirmed` selects the activity from its confirmation time: `[3, 6)`, giving 30 J. The surrounding window still covers `[0, 7)` and gives 70 J.

If a calculation is partial, check the observed range and signal validity periods using the [execution guide](execution.md). Increasing `pre` or `post` does not create observations outside the input data.
