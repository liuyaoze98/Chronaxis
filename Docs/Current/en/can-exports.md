# CAN frame export and resampling

<a id="can报文导出与重采样"></a>

`outputs.can_frames` exports original frames from one CAN source, or reconstructs frames at requested times using explicitly selected continuous fields. See [Outputs](exports.md) for common scopes, publication, and the current environment restriction.

<a id="完整最小例与网格扩展"></a>
## Complete minimal and grid examples

[export-can-minimal.yaml](../examples/export-can-minimal.yaml) defines the `joint.asc`/`joint.dbc` source, a `voltage` binding, and frame export. It exports the three original frames at 0, 1, and 2 seconds within `[0,3)`. The voltage integral is **13 V·s**.

[export-can-grid.yaml](../examples/export-can-grid.yaml) adds a 500 ms frame grid. It reconstructs DBC field `Voltage` while retaining other bits from a base frame. Of six target positions, 0, 0.5, 1, 1.5, and 2 seconds produce five frames. The 2.5-second point has no right-hand frame inside the range and is skipped. The integral remains **13 V·s**.

[export-can-all-windows.yaml](../examples/export-can-all-windows.yaml) defines voltage above 5 V as an activity over `[1,2)`, then creates an activity window and another extending 1 second earlier. `can_frames` uses `scope: {windows: all}` to export the two windows separately. Run `chronaxis run FILE.yaml --output NEW_DIRECTORY` and inspect window/segment identities in `exports.jsonl`.

<a id="原can报文导出"></a>
## Export original CAN frames

With one DBC-configured CAN source, `source` can be omitted. Message IDs and fields must match the actual DBC, and the [export label requirement](exports.md) applies.

Start from [dual-grid.yaml](../examples/dual-grid.yaml), find root `outputs`, and add or replace only its `can_frames` child. Keep other output settings and root fields; do not paste a second `outputs` key.

```yaml
outputs:
  can_frames:
    format: asc    # Text CAN log; use blf for binary BLF output.
```

<a id="扩展设置"></a>
### Add a reconstructed frame grid

Replace the preceding `can_frames` child with this version. The two fragments are alternatives, not blocks to append together.

```yaml
outputs:
  can_frames:
    format: asc
    resampling:
      period: 500ms                # Independent of the signal CSV grid.
      max_gap: 2s                  # Maximum actual gap used for interpolation.
      messages:
        - frame_id: 0x100          # Message ID from the DBC.
          continuous: [Voltage]    # DBC signal names, not analysis aliases.
```

These fields are relative to `outputs.can_frames`:

| Field | Type | Required | Default | Choices and effect |
|---|---|---|---|---|
| `source` | String | With multiple CAN sources | The sole CAN source | Source name from `sources[].name`, using `asc_or_blf`, `can_blf`, `can_asc`, or `raw_can_csv`, e.g. `"bus"`. |
| `format` | String | Yes | None | `"asc"` for text CAN logs or `"blf"` for binary BLF. Choose according to the receiving tool. |
| `scope` | String or object | No | `session` | Whole session, `{window: context}`, or `{windows: all}`. Window names come from `windows[].name`; see [Export scope](exports.md#export-scope). |
| `resampling` | Object or `null` | No | `null` | Omitted/`null` retains original frames. An object enables regular reconstructed frames using the rules below. |
| `output_offset` | Time string | No | `"0s"` | Adds a known positive or negative offset to exported frame times, without changing analysis time. For example, `"28800s"` adds 8 hours. |
| `source_time_reference` | String | No | `epoch` for absolute sources; `relative` for relative sources | `"relative"` means seconds from an origin; `"epoch"` means seconds since 1970-01-01 UTC. Use acquisition records or format documentation, not the magnitude of the number. |
| `capture_date` | String or `null` | For relative-time BLF output | `null` | Actual capture date as `"YYYY-MM-DD"`, e.g. `"2026-10-23"`, from experiment records. Supply it together with `timezone`; omit for `epoch`. |
| `timezone` | String or `null` | With `capture_date` | `null` | Fixed capture-date timezone, e.g. `+08:00` or `UTC`, using the same syntax as source `time.timezone`. It is not inferred from the computer's locale. |

Without resampling, export retains original frames in range, including IDs absent from the DBC and distinct frames at the same time. The public execution path writes `frames.asc` or `frames.blf` and an export `manifest.json`; it does not add a `frames.jsonl` original-frame copy.

With resampling, only messages listed in `messages` and fields listed in their `continuous` arrays are recomputed. Here `Voltage` is a **DBC field name**, not the analysis alias `voltage`.

These fields are relative to `outputs.can_frames.resampling`:

| Field | Type | Required | Default | Choices and effect |
|---|---|---|---|---|
| `period` | Positive duration string or mapping | Yes | None | Fixed spacing, e.g. `500ms`, or `{mode: dbc}` for each target message's own DBC period. No `driver` is accepted. It can differ from the signal export period. |
| `start` | Time string | No | `"0s"` | Shared reference origin for the CAN grids. Alignment works like the signal grid but is configured separately. |
| `max_gap` | Duration string | Yes | None | Positive maximum actual gap between frames used to interpolate the selected continuous fields. Choose according to acceptable missing-data duration. |
| `messages` | Object list | Yes | None | Up to 4096 message rules, each identifying a message and fields that may change. Message identities must be distinct. An empty list is allowed only with `unknown_policy: nearest`. |
| `unknown_policy` | String | No | `"passthrough"` | `"passthrough"` preserves unlisted messages unchanged at original times. `"nearest"` selects the nearest entire original frame at each grid point without interpolating its fields. |
| `max_distance` | Duration string | With `nearest` | Unset | Nonnegative maximum distance between a nearest-frame candidate and the grid point. `0` requires an exact-time frame. `passthrough` does not use it; `nearest` has no default distance. |

A mapped period accepts only `period: {mode: dbc}`. It reads each listed message's own period and does not accept the signal CSV `driver` option. A missing or invalid DBC period fails initialization; it does not silently fall back to a fixed value.

<a id="messages每一项的七个字段"></a>
### The seven fields in each `messages` item

These fields belong in `outputs.can_frames.resampling.messages[]`. Message identity follows [CAN signal binding](inputs.md#can-field), but there is no `signal` field here; put DBC fields to reconstruct in `continuous`.

| Field | Type | Required | Default | Meaning and constraints |
|---|---|---|---|---|
| `channel` | Positive integer | No | Selected source's channel | One-based user channel matching the source DBC channel, e.g. `1`. The program converts it to the underlying frame numbering. |
| `frame_id` | Integer or string | Yes | None | DBC message ID, accepting decimal, `0x` hexadecimal, and `0b` binary. Quote prefixed values in JSON. Maximum standard ID: 2047; extended ID: 536870911. |
| `is_extended` | Boolean | No | Automatic detection | `false` restricts to standard frames; `true` to extended frames. Omission uses the DBC and actual frames. Explicit `null` is invalid. |
| `is_fd` | Boolean | No | Automatic detection | `false` restricts to classic CAN; `true` to CAN FD. Omission retains the actual frame type. Explicit `null` is invalid. |
| `continuous` | String list | Yes | None | 1–4096 interpolatable DBC signal names, not aliases, e.g. `["Voltage"]`. Choose using the DBC and the physical meaning of each value. Only their bits are recomputed. |
| `protected` | String list | No | `[]` | DBC fields explicitly prohibited from interpolation, e.g. `["Counter","Checksum"]`. Names must exist in the DBC and cannot also occur in `continuous`. |
| `same_time_policy` | String | No | `"error"` | `"error"` does not interpolate from conflicting same-time frames. `"last_by_sequence"` selects the last by original read order. A conflict is not assumed to be a more accurate update. |

`protected` is an explicit guard against selecting a counter or checksum as continuous. Even when it is empty, all bits outside `continuous` retain their base-frame values; an empty list does not make every field interpolatable. The example reconstructs only `Voltage`. `Counter` and `Checksum` are illustrative names and must be replaced with actual DBC fields if used.

For each reconstructed frame, the program:

1. Chooses the original frame nearest the target time as the base, choosing the earlier one on a tie.
2. Estimates the selected continuous fields from observations on both sides and replaces only their bits.
3. Preserves every other bit from that same base frame, including states, counters, checksums, and bits not defined by the DBC.

For a target at 100 ms with original frames at 80 and 120 ms, the 80 ms frame is the base. Voltage can be estimated, while its counter and state remain those from 80 ms.

Boolean, enum, and multiplexor-selector fields cannot be continuous. Interpolation is also unavailable when endpoints use different multiplexing branches, reliable records are missing, or the gap exceeds `max_gap`.

Integer DBC fields use `nearest_even-v1`: an exact half-step rounds to the even integer, so 2.5 becomes 2 and 3.5 becomes 4. Out-of-range raw codes are rejected, not clipped. Checksums are retained, not recalculated, so **reconstructed frames are not guaranteed safe to replay to a physical device**. The manifest records observed/estimated counts and reasons for skipped frames.

If one automatic rule matches two actual frame types, it asks you to specify the relevant type option. It does not turn a standard frame into an extended frame, or classic CAN into FD because the DBC says FD. Message names come from the loaded DBC; do not supply `message`.

<a id="无日期数据输出blf"></a>
## Export relative-time data as BLF

BLF requires calendar time. If the experiment is known to have started at 08:00 Beijing time on 2026-10-23 and original timestamps start at zero, use the following fragment. In [dual-grid.yaml](../examples/dual-grid.yaml), replace only the existing `outputs.can_frames` child and retain other settings.

```yaml
outputs:
  can_frames:
    format: blf
    capture_date: '2026-10-23'    # Actual capture date from experiment records.
    output_offset: 28800s         # Eight hours after that date's midnight.
    timezone: +08:00              # Capture timezone.
```

The date sets midnight; adding 28800 seconds gives 08:00. Use your actual capture date. If original times already count from 1970-01-01 UTC, choose `epoch` and omit `capture_date` and `timezone`.

If original time-of-day is already 14:05:40, do not add another 14 hours. Add the known start-time offset only when timestamps start at zero at experiment start. Analysis `time.offset` aligns sources and does not automatically shift exported original frames. Type and combination checks are documented in [FrameExportSpec](../reference/chronaxis.results.frame_exports.md#api-FrameExportSpec) (Chinese implementation reference).

<a id="使用dbc周期的完整导出例"></a>
## Complete example using DBC periods

Download [analysis.yaml](../examples/dbc-grid/analysis.yaml), [grid.asc](../examples/dbc-grid/grid.asc), and [grid.dbc](../examples/dbc-grid/grid.dbc) into one directory and run `chronaxis run analysis.yaml --output grid-result`.

The DBC gives Power a 1000 ms period and Voltage 500 ms. Inputs update at 0, 1, and 2 seconds. The signal CSV has one grid: `period.mode=dbc` with `driver=power` selects 1000 ms. Removing the driver is an error because two physical messages are candidates.

CAN export uses `period: {mode: dbc}` without a driver, giving Power a 1-second grid and Voltage a 0.5-second grid. These choices are independent. The observation range is `[0,2)`; inspect data and manifest generation/skip counts together.

The [signal CSV](../examples/dbc-grid/results/resampled.csv) has four rows: `power=10/20 W` and `voltage=20/30 V` at 0 and 1 seconds. The [reconstructed ASC](../examples/dbc-grid/results/frames.asc) has five frames: Power at 0 and 1 seconds; Voltage at 0, 0.5, and 1 seconds, with 20, 25, and 30 V. Voltage at 1.5 seconds needs the excluded 2-second endpoint, so is skipped instead of borrowing an out-of-range sample. The two row counts reflect their independent grids.
