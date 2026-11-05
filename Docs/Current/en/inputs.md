<a id="数据来源"></a>
# Data sources

Root-level `sources` is a list describing where records come from and how to interpret their original times. With one source, omit its name and `signals[].source`. BLF/ASC are detected by extension. After choosing log paths and DBC, configure [signal bindings](signals.md). [dataset](dataset.md) defines analysis identity and the requested range.

A reader opens the source and interprets its records. `source_type` selects the format: CSV physical-value text is parsed into values; CAN bytes are decoded through a DBC. Signals then name, optionally convert, and validate those values. “Original value” therefore depends on the stage: in a signal declaration it has already been parsed/decoded and is not necessarily the file's original text or bytes.

<a id="选择输入格式"></a>
## Choose an input format

| Available data | `source_type` | Other requirements |
|---|---|---|
| BLF/ASC logs or a continuous log directory | Omit; extensions select the format, including mixed files. | DBC and required message IDs/signal names. |
| CSV rows containing time and signal columns | `signal_csv` | Time column/unit, signal types and units. |
| Raw CSV with IDs and hexadecimal bytes | `raw_can_csv` | DBC, time format, and time/ID/payload column mapping. |
| Times and values already prepared in Python | `memory` | In-memory records and signal definitions. |

`AnalysisRunner` supports the five explicit types `can_blf`, `can_asc`, `raw_can_csv`, `signal_csv`, and `memory`, plus default `asc_or_blf`, which reads ASC and BLF sequentially by extension. `signal_csv` reads decoded physical values; it cannot treat message bytes directly as voltage or current.

<a id="先运行一个完整任务"></a>
### Run a complete task first

Start with the supplied ASC and DBC in the [BLF/ASC quick start](quickstart.md) and check 38 J. Replace its path with your own BLF or log directory without an intermediate CSV conversion.

```powershell
chronaxis run analysis.yaml --output can-result
```

Run from the examples directory with an output directory that can be reused. [CSV](../examples/input-csv-minimal.yaml) and [memory](../examples/input-memory-minimal.yaml) examples serve decoded tables and programmatic records; they are not prerequisites for CAN analysis.

The [offset example](../examples/input-csv-offset.yaml) demonstrates a known 2-second shift: original 0 becomes 2 seconds, while energy remains 38 J. Set common `clock` and `offset` values only from established synchronization evidence; defaults do not synchronize clocks.

The following tables adapt examples to your input. Do not substitute null for omission except where explicitly allowed. Unknown fields or wrong structures are rejected when loading; missing files, mismatched headers, and malformed cells are reported when read.

<a id="来源对象的共同字段"></a>
## Fields common to source objects

Paths below are relative to `sources[]`. Thus `sources[].paths` means the `paths` child of each source list item; dots and `[]` describe nesting, not literal YAML keys. See [configuration](configuration.md) and the format-specific [text input](text-inputs.md) fields.

| Field | Type and requirement | Default | Purpose |
|---|---|---|---|
| `name` | Optional string | `source_1`, `source_2`, etc. | Unique plan name. A signal can omit its source only when there is a unique usable source; otherwise choose explicitly. |
| `source_type` | Optional string | `asc_or_blf` | Detect ASC/BLF by extension, including mixed input. `can_asc` and `can_blf` restrict the format. CSV requires `signal_csv` or `raw_can_csv`; memory requires `memory`. |
| `time` | Optional object; CSV still needs a time unit | Relative; CAN/memory unit s | Groups time type, unit, shared origin, and offset. Source origins are independent by default, not implicitly synchronized. |
| `metadata` | Optional object | `{}` | Source notes, such as acquisition-device model. Keys follow your project conventions and do not execute as extra reader options. |
| `path` | Path string or list; exactly one of `path`/`paths` for file sources | None | File, directory, or wildcard with the same selection rules as `paths`. Prefer consistent `paths`; not used for memory. |
| `paths` | Path string or list; exactly one of `path`/`paths` for file sources | None | File, directory, wildcard, or explicit list. Discovered files use natural order; explicit lists preserve order. Default ASC/BLF, explicit `can_asc`, and `raw_can_csv` also accept `{path: FILE, offset: 2s}` entries. `signal_csv` and explicit `can_blf` do not accept per-file offsets. Required records cannot move backwards across continuous files; full checking/raw export requires the entire source to be ordered. |

`load_analysis_plan` resolves paths from the declaring configuration file. `AnalysisPlan.from_dict` uses `base_dir`, or the current directory when omitted.

<a id="目录与连续文件"></a>
## Directories and continuous files

```yaml
sources:                  # Input sources used by this analysis
  - paths: data/can       # Directory, relative to this configuration
    dbc_by_channel:       # DBC files indexed by user-facing CAN channel
      '1': network.dbc    # DBC for public channel 1
```

Files `part1.asc`, `part2.blf`, and `part10.asc` are read in order 1, 2, 10. Use `paths: data/can/*.asc` for ASC only and explicit `data/can/**/*.asc` for subdirectories. Empty directories or unmatched patterns are errors, not silently skipped. Explicit `[part10.asc, part2.asc]` retains that order.

For known per-file offsets, write `paths: [{path: part1.asc, offset: 0s}, {path: part2.asc, offset: 100s}]`. They add to source `time.offset`. These offsets apply to default ASC/BLF, explicit `can_asc`, and `raw_can_csv`; `signal_csv` and explicit `can_blf` support only source-wide `time.offset`. Applicable sources also accept an `offsets` array, but not together with embedded file offsets. Use [batch tasks](batch.md) for independent experiments.

<a id="time的全部字段"></a>
### All time fields

These fields are inside `sources[].time`. Time `unit` is not `signals[].unit`.

| Field | Type and requirement | Default | Values and meaning |
|---|---|---|---|
| `time_type` | Optional string | `relative` | `relative` means elapsed time from a start; `absolute` means dated time or time since 1970-01-01 UTC. Establish from acquisition settings, not number magnitude. |
| `unit` | String, required for CSV; optional for CAN/memory | s for CAN/memory | `s`, `ms`, `us`, `ns`, or date text `ISO8601`. CSV 5000 with ms means 5 s. BLF is fixed to s; ISO8601 requires absolute time. |
| `clock` | String; optional for relative, absent for absolute | Source-specific name | Name an established common relative origin, such as `test_button`. Equal names declare synchronization; they do not shift timestamps. |
| `offset` | Optional duration string | `"0s"` | Add after input-time conversion. May be positive or negative, based on clock calibration. A CSV starting 2 seconds before the common origin uses -2s, taking original 5 s to common 3 s. |
| `timezone` | String; signal_csv/memory also allow null; requirement depends on format | No timezone supplied | Absolute time only. signal_csv/memory allow supported region names or fixed offsets; ASC/raw CSV allow only UTC or ±HH:MM. ASC absolute requires it; raw CSV ISO8601 text without timezone also needs it. Omit for relative, BLF, and raw CSV numeric time. |

The field is always `sources[].time.timezone`, though accepted values depend on format. ASC/raw CSV reject explicit null. For signal_csv/memory, null means no timezone supplement. A date already containing a timezone uses its own offset. Integer minute-offset notation is not accepted.

<a id="can来源与信号定位"></a>
## CAN sources and signal location

Place the first excerpt in root `sources`, the second in root `signals`. These are partial configurations, requiring your actual `trial.blf`, `network.dbc`, and remaining task declarations. Replace existing lists rather than nesting a second parent key inside an item.

```yaml
sources:                  # Input sources used by this analysis
  - path: trial.blf       # Replace with your actual input
    dbc_by_channel:       # DBC files indexed by user-facing CAN channel
      '1': network.dbc    # DBC for channel 1; channel keys are strings
```

```yaml
signals:                     # Signals available to expressions
  - name: voltage            # Name used to identify and reference this object
    field:                   # Locate the original input field
      frame_id: 0x100        # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: PackVoltage    # Actual case-sensitive DBC name
```

This assumes the DBC supplies a unit and message period. Numeric type, unit, and frame type are inferred; validity defaults to three periods. Add `period` or `valid_for` when the needed period is unavailable. Add location fields only when multiple channels/frame candidates cannot be distinguished.

<a id="can共同字段"></a>
### Common CAN fields

Fields are in `sources[]` and apply to BLF, ASC, and raw-message CSV. `signal_csv` and `memory` do not use DBC.

| Field | Type and requirement | Default | Meaning |
|---|---|---|---|
| `dbc_by_channel` | Required object | None | Maps decimal channel strings without leading zeros to DBC paths. Identify the input channel from the log display or acquisition-device configuration; configuration channel numbers start at 1. For the first channel, write `{"1":"network.dbc"}`; the program handles internal numbering. Each source currently uses one channel and its DBC. |
| `reader` | Object; required for raw CSV, otherwise optional | Format defaults | Reader options. Common `decode_policy` defaults to `strict`. See [text input](text-inputs.md) for layouts; not every format accepts every reader field. |
| `reader.input_check` | Optional string | `"auto"` | `auto` checks timestamps according to dependencies; `full` requires whole-source time order. Applies to all four CAN source types. Ordinary ASC checks needed channels/IDs while collecting earliest/latest source time during the same read. |

<a id="blf读取入口的额外选项"></a>
### Additional options for the BLF reader entry point

Only the `can_blf` entry point accepts these options: explicit `source_type: can_blf`, or a default source containing only BLF with no per-file offsets. Mixed ASC/BLF, `can_asc`, and `raw_can_csv` do not accept them explicitly.

| Field relative to `sources[]` | Type and requirement | Default | Meaning |
|---|---|---|---|
| `legacy_profile` | Optional string | `sclicer-functions-v1` | The only supported BLF implementation selector; normally omit. |
| `reader.decode_scope` | Optional string | `"requested"` | `requested` decodes task-required messages; `all` requests full decoding checks. Use all only for needed additional inspection. Plan checks determine whether a task combination supports it. |

<a id="decode-policy"></a>
<a id="readerdecode_policycan解码策略"></a>
### reader.decode_policy: CAN decoding policy

This child of each CAN source's `reader` controls DBC decoding in `asc_or_blf`, `can_blf`, `can_asc`, and `raw_can_csv`. It is neither interval selection nor signal conversion. The excerpt belongs inside a source item, replacing its reader mapping where appropriate:

```yaml
reader:                    # Input-format parsing options
  decode_policy: strict    # Length checks and decoding-failure behavior
```

| Policy | Purpose and behavior |
|---|---|
| `strict` (default) | Require DBC-compatible length and structure. If structure is valid but a required value cannot be decoded, mark this update invalid and continue. |
| `partial` | Explicitly allow partial decoding of a short payload. Return available values and mark unavailable required values invalid. Corrupt structure is still rejected. |
| `legacy` | Retain the path-specific behavior below. Text CAN strictly checks length and fails on DecodeError; the historical BLF path adds no new length check and can produce invalid values after decoding failure. |

Default `asc_or_blf` allows mixed formats; explicit `can_asc`/`can_blf` restrict them. Lists preserve order, while directories/wildcards use natural order. Text/column parsing happens first: decoding policy cannot turn malformed text into a valid frame. See [CAN fields](#can-field) for the supported classic-CAN/DBC-FD compatibility.

<a id="解码失败时各读取路径的处理"></a>
### Decoding failures by reader path

These policies apply to selected data frames. Use strict for full-length records, partial for explicitly accepted short records, and legacy only to retain a particular historical path.

| Path and condition | strict | partial | legacy |
|---|---|---|---|
| Text CAN: payload length differs from DBC | Fail. | Allow shorter payload; reject longer payload or DLC/actual-byte mismatch. | Same length checks as strict. |
| Text CAN: cantools raises DecodeError after length checks | Current decoded values invalid; do not hold old values. | Current decoded values invalid; do not hold old values. | Fail the task. |
| Historical can_blf: payload length differs from DBC | Fail. | Allow shorter payload; reject longer payload or DLC/actual-byte mismatch. | No added length check; original decoder handles it. |
| Historical can_blf: original decoder fails | Empty decoded result; required values invalid. | Same. | Same. |
| Unselected message | Read only as required by observation/export scope; do not run this DBC decoding for unselected signals. | Same. | Same. |

Malformed structure, invalid input time, and other I/O or programming errors can still fail a task. Partial does not ignore all errors or fill unavailable fields with zero.

Normalized `source_type` determines the path. `can_asc`, `raw_can_csv`, and retained mixed `asc_or_blf` use the text CAN adapter. `can_blf` uses the historical BLF path. Omitted/`asc_or_blf` normalizes pure ASC to `can_asc`, including with offsets; pure BLF without offsets becomes `can_blf`. Mixed formats, or pure BLF with offsets, retain `asc_or_blf`. A single filename extension therefore does not establish legacy behavior.

<a id="can-field"></a>
<a id="signalsfield选择can报文中的信号"></a>
### signals[].field: select a CAN signal

BLF, ASC, and raw CAN CSV share the same binding structure. `frame_id` and `signal` are required; a unique DBC channel allows omitted `channel`. `message` is not accepted. Channel, ID, and signal name locate the value.

| Field | Type and requirement | Meaning |
|---|---|---|
| `channel` | Positive integer; optional for a unique DBC channel | Public 1-based channel matching `dbc_by_channel`. ASC channel 1 remains configuration 1; internal conversion is automatic. |
| `frame_id` | Required integer or string | DBC message ID: `0x100`, `0b100000000`, and decimal `256` all mean 256. Unprefixed `010` is decimal 10. Range 0–536870911; explicit standard frames allow at most 2047. |
| `signal` | Required nonempty string | Exact, case-sensitive DBC signal name such as `PackVoltage`, not the analysis alias `voltage`. |
| `is_extended` | Optional Boolean; automatic when omitted | False selects standard frames; true selects extended frames. Use DBC and actual frame flags. Small IDs can be extended; do not infer type from ID magnitude. Null is invalid. |
| `is_fd` | Optional Boolean; automatic when omitted | False selects classic CAN, true CAN FD. Use actual frame type, not payload length. Null is invalid. |

JSON needs `"frame_id": "0x100"` or `"frame_id": 256`, because prefixed numeric literals are invalid JSON. YAML can use `frame_id: 0x100`. Prefixes are case-insensitive; negatives, floats, Booleans, and octal prefixes are rejected. Omission means automatic frame-type recognition; explicit null does not.

JSON Schema checks ID text syntax; plan loading also converts it to an integer and validates the range. For example, `is_extended: false` with `frame_id: "0x800"` is rejected because 2048 exceeds 2047. Editor schema success does not replace `chronaxis validate analysis.yaml`.

Suppose standard and extended message `0x100` both contain `PackVoltage`. A log containing only the extended frame can resolve the definition using actual flags. If a matching standard frame later appears for the same binding, the program asks for `is_extended` rather than merging both into one signal. Missing IDs or misspelled signal names produce a specific missing-definition error; type flags cannot conceal that problem.

The supported case where the DBC says FD but the actual log is classic CAN remains compatible and records a notice. Explicit type selection does not modify input frames. Each source uses one channel and DBC, continuous files retain order, and DBC factor/offset must not be applied again.

<a id="解码范围与时间检查范围"></a>
### Decoding scope versus timestamp-check scope

`sources[].reader.decode_scope` applies only to the historical BLF entry point: default `requested` decodes required messages; `all` requests all-message decoding checks.

`sources[].reader.input_check` applies to all CAN sources: default `auto` follows task requirements; `full` checks whole-source ordering. It does not enable all signal decoding or diagnostic output.

A whole-file fixed-period message-energy sum may not need message times. Activities and time-range selections do. Inspect `input_requirements` in `explain` for required signals and time checks. Unchecked records cannot be called verified.

For ordinary ASC and mixed ASC/BLF, auto requires only selected channels/IDs to advance in original order. Microsecond regressions in unrelated Tx frames do not block analysis. Earliest/latest source times are collected during the same read separately from ordering checks; original timestamps are unchanged. Full checks/raw export reject whole-source regressions. Target regressions, including across continuous files, always fail; no automatic sorting, clamping, or cleaning occurs. ASC relative increments still accumulate across all relevant time rows: skipping unrelated decoding does not discard increments. Raw CSV retains its own column parsing/time rules; ASC behavior does not imply arbitrary malformed CSV rows are ignored.

Rules, windows, calculations, and exports can omit `dataset.domain` and use actual observation. Multiple sources use the union of observed ranges. Empty observation produces no events and null session statistics. A whole-file message sum that needs no time can avoid constructing a time domain, but time filters, events, and other temporal features still require time checks. Omitting domain does not disable them. See [analysis range](dataset.md) and [message calculations](message-calculations.md).

<a id="csv每行是一次明确更新"></a>
## CSV: every row is an explicit update

This partial root `sources` section requires actual `part1.csv` and `part2.csv` files containing `time_ms` and the referenced signal columns. Replace the existing root list; do not nest another `sources` key inside an item.

```yaml
sources:                             # Input sources used by this analysis
  - paths: [part1.csv, part2.csv]    # File, continuous file list or directory; relative to this configuration
    source_type: signal_csv          # Input adapter; CSV or memory must be declared explicitly
    time_column: time_ms             # Exact header
    time:                            # Input timestamp interpretation
      unit: ms                       # Unit of the input timestamp values
    reader:                          # Input-format parsing options
      missing_values: ['', NA]       # Invalid updates, not zero
```

| Field relative to `sources[]` | Type and requirement | Default | Meaning |
|---|---|---|---|
| `time_column` | Required string | None | Actual, case-sensitive time header. A mismatch fails when reading the header. |
| `reader.encoding` | Optional string | `"utf-8"` | Encoding from the exporter, such as utf-8, utf-8-sig, or gbk; no automatic guessing. |
| `reader.delimiter` | Optional string | `","` | Exactly one column-separator character. For tab-separated text, use double-quoted `"\t"`. |
| `reader.missing_values` | Optional string array | `[""]` | Exact cell text denoting an invalid update, such as `["", "NA"]`; whitespace is not stripped. `[]` adds no missing markers; null is not a list. `NA` replaces the previous valid value. |

Choose exactly one of `path` and `paths`. Explicit lists retain order; discovered files use natural order. If part 1 ends at 10 seconds and part 2 restarts at zero, joining them directly fails due to backwards time.

With the example missing tokens, current 5 A followed by `NA` becomes unknown at the latter row, not held at 5 A. Enable `diagnostics.trace` and read `input_trace` only when you need input locations; default summaries do not retain per-cell original positions.

Bind original `Current_mA` as `current` with this root `signals` excerpt:

```yaml
signals:                 # Signals available to expressions
  - name: current        # Name used to identify and reference this object
    field: Current_mA    # Locate the original input field
    dtype: float64       # Analysis value type
    unit: A              # Unit in which this value is interpreted or the result is displayed
    valid_for: 200ms     # Example; establish for actual acquisition
    conversion:          # Optional unit conversion after decoding
      input_unit: mA     # Unit of the parsed or decoded input value
      scale: 0.001       # Explicit mA-to-A conversion
```

This explicitly converts milliamperes to amperes. `valid_for` is illustrative and needs an acquisition-based choice in a real task. Expressions use `current` even though the column has another name.

<a id="内存把记录直接写进配置"></a>
## Memory: put records directly in configuration

Memory `rows` contains original times and values, useful for hand-checkable examples. The following root `sources` section needs no external files; add signals and calculations in a complete plan.

```yaml
sources:                   # Input sources used by this analysis
  - source_type: memory    # Input adapter; CSV or memory must be declared explicitly
    rows:                  # Explicit input records for the memory source
      - time: 0s           # Timestamp of this explicit input record
        values:            # Signal values in this input record
          power: 4000      # Power value or named power signal settings in this example
          active: 1        # Activity state in this input record
      - time: 1s           # Timestamp of this explicit input record
        values:            # Signal values in this input record
          power: 4000      # Power value or named power signal settings in this example
          active: 0        # Activity state in this input record
      - time: 8s           # Timestamp of this explicit input record
        values:            # Signal values in this input record
          power: 4000      # Power value or named power signal settings in this example
          active: 0        # Activity state in this input record
```

| Field relative to `sources[]` | Type and requirement | Meaning |
|---|---|---|
| `rows` | Required object array, no default | Time-ordered records prepared in Python or declared as synthetic data. `[]` means no observations, not a normal zero result. |
| `rows[].time` | Required time string, no default | Relative values include units, such as `1s`; absolute values contain explicit date/time. Bare numbers are not interpreted by guessing from `time.unit`. |
| `rows[].values` | Required object, no default | Original fields updated at this time; keys are selected by `signals.field`. Values may be numbers, Booleans, strings, or null. `power: 4000` supplies that value; the signal declaration supplies its unit and validity rules. |

Memory timestamps require units, or an explicit absolute date/time/timezone. The three records above are synthetic, allowing an expected answer before checking the implementation. For large actual inputs, use CSV/BLF streaming instead of placing the whole dataset in configuration. [SourceSpec/MemoryRow](../reference/chronaxis.core.models.md) and [MemorySourceAdapter](../reference/chronaxis.sources.memory.md) are Chinese implementation references for typed interfaces.

<a id="多来源时间同步"></a>
## Synchronize multiple sources

“3 seconds” in two files need not be the same instant. If CAN starts at the experiment button and a CSV instrument started 2 seconds earlier, 3 seconds after the button is CAN 3 seconds and CSV 5 seconds.

Subtract 2 seconds from CSV time to combine them. Conversion first changes units, then adds `offset`, so use `offset: -2s`. If the instrument started 2 seconds later, add 2 seconds instead.

Put this block inside the CAN source item, beside `paths`, replacing its existing `time`:

```yaml
time:                   # Time settings for the CAN source
  clock: test_button    # Established common origin
```

Put this separate block inside the CSV source item, beside `time_column`, replacing its existing `time`:

```yaml
time:                   # Time settings for the CSV source
  unit: ms              # Input time column uses milliseconds
  clock: test_button    # Same established origin as CAN
  offset: -2s           # Instrument started 2 seconds earlier
```

Each block belongs to one source; neither is a complete `sources` list. CSV 5000 ms first becomes 5 seconds, then shifts to common time 3 seconds. See the [CAN/CSV example](examples.md#can-joint-analysis) for a complete configuration.

`clock` declares a known common origin. Assigning the same name to unrelated origins does not synchronize them. Derive offsets from known acquisition starts, synchronization records, or an identifiable simultaneous event. If the offset is unknown, analyze separately rather than combine arbitrarily to calculate power.

If both files contain dated, zoned absolute timestamps, use absolute time normalized to UTC. This version supports known fixed offsets; it does not automatically match waveforms or correct clock drift.

After alignment, signal validity still matters: an expired voltage cannot be multiplied by a new current. See the runnable [joint CAN/CSV example](examples.md#can-joint-analysis).

<a id="asc和原始can-csv"></a>
## ASC and raw CAN CSV

`can_asc` and `raw_can_csv` both read undecoded CAN messages and require a DBC. The former reads the selected ASC dialect; the latter decodes mapped raw-message columns. This differs from `signal_csv`, which already contains voltage/current columns. See [text CAN inputs](text-inputs.md) for all fields, dates/time-of-day, channel origins, and per-file offsets.
