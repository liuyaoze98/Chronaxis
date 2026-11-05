# Temporal transforms

Root `transforms` creates new time-varying signals from bound numeric signals or expressions. Rules, calculations, and later transforms can reference the new names. Supported operations cover rolling statistics and rates of change, using CAN logs, decoded CSV, or memory inputs; the feature is not specific to current.

## Start with one rolling mean

Download [the minimal configuration](../examples/temporal/rolling-actual.yaml), [meter.asc](../examples/temporal/meter.asc), and [meter.dbc](../examples/temporal/meter.dbc) into one directory. Synthetic readings include 10 A at 0 s, 20 A at 0.12 s, 40 A at 0.30 s, then 5 A at 0.42 and 0.60 s. The configuration contains one rolling_time_mean and one select, using default actual time. Omitted validity is three times the DBC's 100 ms period.

```yaml
config_version: 4                   # Current analysis configuration version
dataset:                            # Analysis identity and optional input range
  name: rolling_actual              # Name used to identify and reference this object
sources:                            # Input sources used by this analysis
  - paths: meter.asc                # File, continuous file list or directory; relative to this configuration
    dbc_by_channel:                 # DBC files indexed by user-facing CAN channel
      '1': meter.dbc                # DBC for channel 1; channel keys are strings
signals:                            # Signals available to expressions
  - name: current                   # Name used to identify and reference this object
    field:                          # Locate the original input field
      frame_id: 0x100               # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Current               # Exact signal name defined in the DBC
transforms:                         # Time-window calculations producing output signals
  - name: average                   # Name used to identify and reference this object
    operation: rolling_time_mean    # Calculation to apply to the expression
    expr: current                   # Formula using the declared signal or derived names
    window: 0.1s                    # Length of the trailing calculation window
    step: 0.1s                      # Spacing between output times
calculations:                       # Requested statistics or selected rows
  - name: average_rows              # Name used to identify and reference this object
    operation: select               # Calculation to apply to the expression
    expr: average                   # Formula using the declared signal or derived names
```

```powershell
chronaxis validate rolling-actual.yaml
chronaxis run rolling-actual.yaml --output rolling-result
```

Find the selection table through this run's manifest. At 0.20 s, average_rows should be 18 A: in [0.10,0.20), 10 A lasts 0.02 s and 20 A lasts 0.08 s, so (10×0.02+20×0.08)/0.1=18. Under default strict policy, an initial window without enough history has no value.

## Fields and operation matrix

Fields belong to transforms[]. A plan allows at most 64 transforms. Names must be unique across source signals, derived signals, and transforms; circular references are rejected. A transform unused by requested results is not calculated.

|Field|Type, requirement, and default|Meaning|
|---|---|---|
|name|Required valid name|New time-varying signal referenced by later expr or condition|
|operation|Required string|An operation below or a host-registered temporal operator|
|expr|Required numeric expression|float64/int64/uint64 input, not bool or enum|
|window|Required positive duration for grid operations|Lookback width under the selected interval basis|
|step|Required positive duration for grid operations|Actual-time spacing between output points|
|origin|Optional coordinate for grids; defaults to timebase zero|Output times origin+n×step; use a compatible date/time for absolute sources|
|max_gap|Required positive duration for adjacent_rate|Maximum actual-time gap between measured updates|
|unit|Optional compatible unit|Output unit, otherwise derived from the operation|
|partial_policy|Grid-only option; default strict|strict requires complete data; report allows supported partial values with quality|
|minimum_coverage|Grid-only finite number; default 0|Inclusive 0–1 required valid-data proportion; does not invent missing data|
|interval|Optional object; inherits intervals.default, normally actual|actual uses elapsed time; fixed/dbc advance with driver updates; see [intervals](intervals.md)|

|operation|window and step|origin / partial_policy / minimum_coverage|max_gap|Result|
|---|---|---|---|---|
|rolling_time_mean|Required|Optional|Forbidden|Duration-weighted mean in the lookback window|
|rolling_minimum, rolling_maximum|Required|Optional|Forbidden|Extrema of held values with positive duration|
|rolling_integral|Required|Optional|Forbidden|Integral of valid held values in the window|
|adjacent_rate|Forbidden|All forbidden|Required|Difference between current and previous measured values divided by the corresponding interval; output at the right measurement|
|window_rate|Required|Optional|Forbidden|Difference between valid window endpoints divided by window width|
|sample_fit_slope|Required|Optional|Forbidden|Equal-weight straight-line fit of real updates; at least two distinct positions|

Rolling means, integrals, and rates return float64. Rolling extrema retain the numeric input type when conversion permits. Convert absolute Celsius to K before integration; temperature rates use difference-per-time units. Record timestamps and valid_for always use actual time; fixed periods do not restore expired samples.

## Extended example: seven transforms and a DBC period

The following example uses the same records and adds seven transforms, DBC-period weighting, and individual selections. Its small batch setting demonstrates resource controls and is not necessary for the minimal task.

The ASC contains 10, 20, 40, 5 and 5 A at 0.00, 0.12, 0.30, 0.42 and 0.60 s. The DBC specifies a 100 ms frame period. At 0.20 s there is no new frame, but the analysis can still ask for the average current over one frame period. Download the [configuration](../examples/temporal/analysis.yaml), [ASC](../examples/temporal/meter.asc) and [DBC](../examples/temporal/meter.dbc) into the same directory.

## Run and read the example

```powershell
python -m chronaxis validate analysis.yaml
python -m chronaxis run analysis.yaml --backend numpy --work-dir work-grid --output result-grid
```

To compare the reference backend, use `--backend reference` with a separate work directory, such as `--work-dir work-grid-reference`. The output directory can be reused; each run creates timestamped results. The input alias `current` refers to Current in channel 1, standard frame 0x100. Each entry under `transforms` names a new series available to rule conditions, calculations or later transforms. This example uses `select` to expose its actual output timestamps.

|Selection|Actual time|Expected value|Meaning|
|---|---:|---:|---|
|average_rows|0.20 s|130/9 ≈ 14.444444 A|Mean over one selected frame period|
|low_rows / high_rows|0.20 s|10 / 20 A|Extrema of held values with positive duration|
|charge_rows|0.20 s|13/9 ≈ 1.444444 A·s|Current integral, with unit label `A*s`|
|adjacent_rows|0.30 s|200 A/s|Change between consecutive measurements divided by one period|
|endpoint_rows / fit_rows|0.30 s|150 / 150 A/s|Endpoint change and equal-weight fitted slope over two periods|

## How to interpret the clock

Output times follow `origin + n × step` on the real clock. The default origin is zero on the analysis timebase. `window` sets the lookback width. `interval` selects actual time, a fixed period, or a verified DBC period for the window measure and rate denominator. A fixed interval looks like `{mode: fixed, value: 0.1s, driver: current}`. DBC mode requires an original CAN frame with a declared period.

For actual time, set `intervals.default` to `{mode: actual}`. The mean at 0.20 s uses [0.10,0.20) on the real clock and equals (0.02×10+0.08×20)/0.1 = **18 A**. In the supplied DBC example, 0.12 to 0.30 s represents one period. At 0.20 s, 4/9 of that period has elapsed. The 10 A reading gets 5/9 of the weight and the 20 A reading gets 4/9. The later frame establishes that split. The calculated row retains its 0.20 s timestamp. After the last driver frame, an unfinished period has no inferred length.

## Choose the rate that answers your question

- `adjacent_rate` emits at the right-hand real input update. `max_gap` and source `valid_for` refer to actual elapsed time. An expired or unknown interval breaks the pair. For independent clocks, suppose driver frames arrive at 0 and 0.12 s and current is 1 A at 0.03 s and 7 A at 0.09 s. With a fixed period of 0.1 s the two readings span 0.05 selected seconds. After receiving the 0.12 s driver, the row at **0.09 s** reports 120 A/s.
- `window_rate` subtracts the held values at the two boundaries and divides by the selected window width. A real update at the right boundary supplies that boundary's value. Rolling means and integrals cover a half-open interval, so the update contributes no area to the preceding window.
- `sample_fit_slope` fits equally weighted real input updates inside the window, including real samples at its boundaries. It needs at least two distinct positions. A clipped boundary adds no measurement. For 20°C at 0 s, 21°C at 1 s and 26°C at 3 s, the adjacent, three-second endpoint and fitted rates at 3 s are 2.5, 2 and approximately 2.071429 `delta_K/s` in actual mode. The [window-change event rule `window_delta`](rules.md#rule-window-delta) checks whether the difference between the window endpoints meets a threshold. It does not divide that difference by elapsed duration, unlike the rate operations described here.

## Warm-up and partial windows

The default `partial_policy: strict` requires a complete window. Early ticks, expired readings or too few fit samples can produce unknown values. With an explicit `report` policy and `minimum_coverage`, supported partial results use only observed valid weight. The mean divides by that weight, and the integral retains only the known area. Selected partial values carry `ESTIMATED` quality. Read a scalar result's status and quality together. An endpoint rate still needs both endpoints. Between ticks, output holds only within the observed range. A shorter grid step samples the series more often, but an excursion shorter than a step may still be missed.

Even with complete coverage of the preceding window, an estimated reading used in the endpoint rate or fitted slope makes the result estimated. With `report`, the result retains its value and estimated status. With `strict`, it has no numeric value.
