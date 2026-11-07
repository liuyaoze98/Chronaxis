# Signal CSV export and resampling

<a id="信号csv导出与重采样"></a>

`outputs.signal_csv` exports updates of selected original signals. You can additionally request regularly spaced values estimated by linear interpolation. Export settings do not change the analysis integral. See [Outputs](exports.md) for common scopes, publication, and the current environment restriction.

<a id="完整最小例与网格扩展"></a>
## Complete minimal and grid examples

[export-signal-minimal.yaml](../examples/export-signal-minimal.yaml) reads `power` from the supplied `quickstart.asc` and `teaching.dbc`. Its integral remains **38 J**; it additionally exports the four original updates at 0, 1, 3, and 4 seconds within `[0,6)`. Sources, signals, and the currently required device label are already defined.

[export-signal-grid.yaml](../examples/export-signal-grid.yaml) adds a 500 ms grid and `max_gap=3s`, producing 12 points from 0 to 5.5 seconds. The estimate at 0.5 seconds is **3 W**. The 4.5, 5, and 5.5 second points have no right-hand update inside the range, so remain `missing` instead of being extrapolated. The integral is still **38 J**. Run `chronaxis run FILE.yaml --output RESULT_DIRECTORY`, read the manifest returned by the CLI, then use its `exports.index_file` and `exports.directory` to locate this export's index and `original.csv` or `resampled.csv`.

<a id="原信号csv导出"></a>
## Export original signal updates

The following fragment assumes `signals` already binds the numeric signal `voltage` and the [export label requirement](exports.md) is met. Start from [dual-grid.yaml](../examples/dual-grid.yaml), find root `outputs`, and add or replace only its `signal_csv` child. Keep the other output settings and unshown root fields; do not paste a duplicate `outputs` key.

```yaml
outputs:                # Additional result files to publish
  signal_csv:           # Export selected signals as CSV
    signals: [voltage]  # Use the signal name from the analysis definitions.
```

<a id="扩展设置"></a>
### Add a regular output grid

Replace that `signal_csv` child with the following. The two fragments are alternatives, not two blocks to append together.

```yaml
outputs:                     # Additional result files to publish
  signal_csv:                # Export selected signals as CSV
    signals: [voltage]       # Names of the analysis signals to export
    resampling:              # Optional output grid and value selection
      continuous: [voltage]  # Only signals that can meaningfully be interpolated.
      period: 250ms          # Spacing of exported values.
      max_gap: 2s            # Largest permitted gap between actual observations.
```

These fields are relative to `outputs.signal_csv`. Its `signals` field selects names; it is not the root list that defines signals.

| Field | Type | Required | Default | Meaning and constraints |
|---|---|---|---|---|
| `signals` | String list | Yes | None | 1–4096 distinct original signal aliases from `signals[].name`, e.g. `["voltage","current"]`. Derived signals cannot be selected directly. |
| `scope` | String or object | No | `session` | Whole session, or `{window: context}` for a named window. See [Export scope](exports.md#export-scope). |
| `resampling` | Object or `null` | No | `null` | Omitted/`null` keeps original updates; an object enables the regular grid described below. |

Without resampling, `original.csv` contains one timestamp and one signal update per row. It does not force signals onto the same sampling frequency. Invalid values leave `value` empty, with a reason recorded in `quality`; different updates at the same time remain separate. Its public header is `time_ns,signal,value,unit,quality`, with no `valid`, `status`, or source-reference columns.

With resampling, signals listed in `continuous` go to `resampled.csv`; other selected signals retain their original updates in `original.csv`. `continuous` must be a numeric subset of `signals`. Boolean, enum, state, and counter values should not be treated as continuous physical quantities.

The following fields are relative to `outputs.signal_csv.resampling`:

| Field | Type | Required | Default | Meaning and constraints |
|---|---|---|---|---|
| `continuous` | String list | Yes | None | Nonempty, distinct subset of selected original signals that can physically be linearly estimated, e.g. `["voltage"]`. A numeric representation alone is not sufficient justification. |
| `period` | Positive duration string or mapping | Yes | None | Grid spacing, e.g. `250ms`, or `{mode: dbc}` to obtain a DBC period. The mapping may specify a `driver` from `continuous`; it must identify a DBC message with a valid period. |
| `start` | Time string | No | `"0s"` | Reference grid origin. `start=50ms`, `period=100ms` gives 50, 150, 250 ms, etc.; it does not restart at file or batch boundaries. |
| `max_gap` | Duration string | Yes | None | Positive maximum actual interval between the two interpolation records. With `2s`, a 2-second gap is allowed but a 3-second gap leaves the value missing. |

A mapped `period` accepts these fields. This output grid is independent of root `intervals`.

| Full path | Purpose | Choices and omission behavior |
|---|---|---|
| `outputs.signal_csv.resampling.period.mode` | Select where the grid period comes from. | Only `dbc`. For a fixed period, write `period: 250ms`, not `mode: fixed`. |
| `outputs.signal_csv.resampling.period.driver` | Select the message period through one original signal in `continuous`. | All continuous signals must originate from raw CAN. Omit only when there is one physical-message candidate; multiple candidates require a driver. Explicit `null`, derived signals, or names outside `continuous` are invalid. |

The points arranged from `start` and `period` form the **time grid**. Each point has one of three statuses:

| `status` | How its value is obtained |
|---|---|
| `observed` | A valid actual update exists exactly at that time. |
| `estimated` | No update exists at that time, but valid records on both sides are no farther apart than `max_gap`; the value is interpolated on their straight line. |
| `missing` | A left/right record is absent or invalid, same-time records conflict, or the gap is too large. `value` is empty and `reason` explains why. |

For a 100 ms grid with valid updates only at 10 and 120 ms, 100 ms can be estimated; 0 ms cannot, because it has no left-hand record.

With conflicting records for one signal at one time, `error` marks the point and affected interpolation `missing` with `reason=same_time_conflict` if that signal is used only by the export grid. If it also participates in ordinary calculations or rules, `error` rejects the conflict and fails the analysis. `dual-grid.yaml` also integrates `voltage`, so it follows the latter behavior.

To choose the last record by stable source sequence, explicitly set `signals[].same_time_policy` to `last_by_sequence`. This does not choose by numerical value or thread completion order. The resampled file's public header is `time_ns,signal,value,unit,status,reason,quality`; it does not include endpoint timestamps or source references.

<a id="使用dbc周期的完整导出例"></a>
## Complete example using DBC periods

Download [analysis.yaml](../examples/dbc-grid/analysis.yaml), [grid.asc](../examples/dbc-grid/grid.asc), and [grid.dbc](../examples/dbc-grid/grid.dbc) into one directory and run `chronaxis run analysis.yaml --output grid-result`.

The example exports `power` and `voltage`. The DBC declares a 1000 ms period for the Power message and 500 ms for Voltage; input updates occur at 0, 1, and 2 seconds. Signal CSV uses one grid, so `period.mode=dbc` and `driver=power` explicitly select 1000 ms. Removing the driver is an error because the continuous signals belong to two physical messages; the program does not choose arbitrarily.

CAN reconstruction uses each message's own DBC period, so that export uses `period: {mode: dbc}` without a driver: Power every 1 second and Voltage every 0.5 seconds. Selecting a signal-grid driver does not alter CAN message periods. The observation range is `[0,2)`; inspect both data and manifest generated/skipped counts for endpoint behavior.

The [signal CSV](../examples/dbc-grid/results/resampled.csv) has four rows: at 0 and 1 seconds, `power` is 10/20 W and `voltage` is 20/30 V. The [reconstructed ASC](../examples/dbc-grid/results/frames.asc) has five frames: Power at 0 and 1 seconds, Voltage at 0, 0.5, and 1 seconds with 20, 25, and 30 V. Voltage's 1.5-second point needs the update at 2 seconds, which is outside the half-open request range; that point is skipped. Different row counts follow from the two independent grid rules.
