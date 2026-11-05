<a id="事件窗口与片段"></a>
# Event windows and segments

Root-level `windows` creates analysis or export segments from existing rule events. A window can extend before/after an event or merge neighboring ranges. This does not change the original event or its actual activity interval.

<a id="window-fields"></a>
Time examples use the default `actual` basis unless stated otherwise. With `fixed` or `dbc`, duration confirmation, waits, change windows and pairing delays use the selected period; timestamps and signal expiration still use actual record time. See [Time-basis comparison](intervals.md#timing-basis).

<a id="完整最小例与合并扩展"></a>
## Complete examples

[window-minimal.yaml](../examples/window-minimal.yaml) contains button presses at 1, 3 and 6 s. A rising-edge rule produces those three points. Extending each point 3 s forward gives [1,4), [3,6), [6,9).

[window-merged.yaml](../examples/window-merged.yaml) adds only `merge: overlap_and_adjacent`, combining those segments into [1,9). The rule still produces three points, and the segment retains all three parent event IDs. [window-exit-delay.yaml](../examples/window-exit-delay.yaml) instead treats each press as an activity and uses `merge: exit_delay` with a 2 s wait after activity ends. Activities [1,2), [3,4), [6,7) produce one [1,9) segment; the separate original activities are retained.

Run `chronaxis run window-minimal.yaml --output new-result` from the examples directory. These complete configurations include sources and signals.

<a id="窗口配置windows"></a>
<a id="窗口配置-windows"></a>
## Window configuration

<a id="activity-context-example"></a>
<a id="活动前后各取1秒并计算能量"></a>
### Include one second before and after an activity

In the [temperature example](rules.md#duration-selection-origin), temperature reaches 80 at 1 s, is confirmed after 2 s at 3 s, and falls below 80 at 6 s. To analyze one second before and after, define `hot_context` and use it as the calculation scope.

Start with [activity.yaml](../examples/activity.yaml). Replace or add the root `windows` and `calculations` lists below; do not nest their parent keys inside items. The file already defines the `hot` rule and `temperature` and `power` signals; see [Sources and signals](activity-tutorial.md).

```yaml
windows:                     # Ranges around existing rule events
  - name: hot_context        # Window name used by calculations
    rule: hot                # Existing rule name
    pre: 1s                  # Include one second before onset
    post: 1s                 # Include one second after the end
calculations:                # Results to compute
  - name: context_energy     # Name shown in the result
    scope:                   # Compute separately for each window segment
      window: hot_context    # Previously defined window
    operation: integral      # Integrate valid power over time
    expr: power              # Previously defined signal
```

- `rule: hot` uses the activities found by that rule.
- The inferred `anchor: activity` extends from actual onset and end.
- `pre: 1s` and `post: 1s` produce the range 0–7 s.
- `scope: {window: hot_context}` computes one energy result per segment.

If power is valid and constantly 10 W over 0–7 s, energy is 70 J. Switching the rule's `selection_origin` between `onset` and `confirmed` leaves this activity-anchored window at 0–7 s and 70 J. Using `scope: {rule: hot}` instead computes the activity selection: 50 J for `onset`, 30 J for `confirmed`.

<a id="窗口的全部字段"></a>
### All fields

Paths are relative to `windows[]`, such as `windows[].name`; do not place these fields at the root.

| Field | Type | Required/default | Purpose and values |
|---|---|---|---|
| name | String | Required | Unique window name referenced by `calculations[].scope.window`, `outputs.signal_csv.scope.window` or `outputs.can_frames.scope.window`, e.g. `context`. |
| rule | String | Required | Existing `rules[].name` supplying the events, e.g. `hot`. |
| anchor | String | Inferred from event type | `activity` extends an entire activity; `point` extends a trigger instant. Must match the rule's event type. |
| pre | Duration string | Default 0s | Nonnegative extension before activity onset or the point. |
| post | Duration string | Usually 0s; `start_only` inherits `window_duration` | Nonnegative extension after activity end or the point. A point window requires positive pre or post. |
| merge | String | Default `none` | How segments from this definition combine; see below. |
| exit_delay | Duration string | Required only for `merge: exit_delay`; otherwise omit | Nonnegative wait after activity ends. Requires `anchor: activity` and `post: 0s` to avoid extending twice. |

| merge | Meaning | Example |
|---|---|---|
| `none` | Keep each segment, including overlaps | 0–3 and 2–5 remain separate |
| `overlap` | Merge overlapping ranges only | 0–3 and 2–5 become 0–5; 0–2 and 2–5 remain separate |
| `overlap_and_adjacent` | Merge overlaps and touching endpoints | 0–2 and 2–5 become 0–5 |
| `exit_delay` | Wait after activity ends; another activity beginning within the wait joins the segment | Activities 0–1 and 2–3 with a 3 s exit delay give segment 0–6; two original activities remain |

| Rule | anchor |
|---|---|
| condition_duration, debounce, hysteresis, start_end | `activity` |
| rising_edge, falling_edge, window_delta | `point` |
| start_only | `point`; post must equal the rule's `window_duration` |

A window may specify its own `interval`; otherwise it inherits `intervals.default`. See [Calculation intervals](intervals.md).

<a id="配置错误与边界"></a>
## Errors and range boundaries

Validation identifies the field for nonexistent rules, mismatched anchors, a point window with both extensions zero, or conflicting exit_delay/post settings. Extending beyond requested or observed data does not manufacture records. Check the resulting segment range, completeness and reason before accepting a calculation.
