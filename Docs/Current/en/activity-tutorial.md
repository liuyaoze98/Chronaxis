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
sources:
  - paths: data/can/activity.asc
    dbc_by_channel:
      '1': data/can/teaching.dbc
signals:
  - name: temperature                      # Alias used in the rule
    field:
      frame_id: '0x11d'
      signal: Temperature
    valid_for: 4s                         # Maximum age of the latest value
  - name: power                            # Alias used in the calculations
    field:
      frame_id: '0x100'
      signal: Power
    valid_for: 4s
```

<a id="三个配置部分如何配合"></a>
## 3. Connect the rule, window, and calculations

The following excerpt is not a standalone configuration. Keep `config_version`, `dataset`, and the input declarations from the complete example.

```yaml
rules:
  - name: hot
    rule_type: condition_duration
    condition: temperature >= 80          # Enter the candidate activity
    minimum_duration: 2s                  # Confirm after 2 seconds
windows:
  - name: hot_context
    rule: hot                             # Window around this rule's activity
    pre: 1s
    post: 1s
calculations:
  - name: event_energy
    scope:
      rule: hot                           # Integrate over the activity
    operation: integral
    expr: power
  - name: context_energy
    scope:
      window: hot_context                 # Integrate over the window
    operation: integral
    expr: power
```

<a id="运行并核对"></a>
## 4. Run and check

From the repository root, run the following commands. In the offline examples directory, use `activity.yaml` as the configuration path. The output directory must be new.

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
