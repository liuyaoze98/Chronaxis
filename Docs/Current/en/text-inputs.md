<a id="读取asc和原始can报文csv"></a>
# Read ASC and raw CAN CSV

Distinguish two CSV inputs. `signal_csv` already contains physical columns such as time, voltage, and current. A `raw_can_csv` row still contains a message ID and hexadecimal bytes, which need DBC decoding. Equal filename extensions do not imply equal contents.

A **DBC** defines CAN message fields: for example, the first byte of ID `0x100` may represent Voltage with scale 1 and unit V. It does not supply acquisition timestamps. It can define message periods used for defaults such as validity, but does not establish measurement points or current direction. ASC is a text message log; BLF is a binary log. Both reader paths feed decoded signals into the same analysis engine.

Sources below are items in the root `sources` list; `signals` refers to their decoded fields. Raw CSV reads mapped columns, while ASC reads message lines. Both produce signal updates with a common time representation.

<a id="完整最小例与列映射扩展"></a>
## Complete minimal examples and column mapping

Download [input-asc-minimal.yaml](../examples/input-asc-minimal.yaml), [joint.asc](../examples/data/joint.asc), and [joint.dbc](../examples/data/joint.dbc), keeping the relative `data` layout. From the examples directory:

```powershell
chronaxis run input-asc-minimal.yaml --output asc-minimal-result
```

This binds only Voltage and integrates it. The DBC applies `2 × raw + 1`: bytes 1, 3, 1 become 3, 7, 3 V, each lasting 1 second, giving 13 V·s. Do not repeat the DBC scaling in `signals`.

[input-raw-csv-minimal.yaml](../examples/input-raw-csv-minimal.yaml) reads [raw-can-example.csv](../examples/data/raw-can-example.csv) using the same DBC and signal definition, also producing 13 V·s. Explicit `id_base: 16` reads text `100` as hexadecimal, matching decimal DBC ID 256. Payload text such as `01 05` is bytes, not a voltage value.

[input-raw-csv-mapping.yaml](../examples/input-raw-csv-mapping.yaml) changes direction from a fixed true value to the `direction` column. Its `value_map` maps Rx→true and Tx→false. `strip: true` removes the leading/trailing spaces in the first row's ` Rx ` before matching. All rows are Rx here, so energy remains 13 V·s. Unlisted text produces a mapping error rather than becoming transmit or receive automatically.

```powershell
chronaxis run input-raw-csv-minimal.yaml --output raw-csv-result
chronaxis run input-raw-csv-mapping.yaml --output raw-mapping-result
```

All three annotated files contain complete source, signal, and calculation declarations. Output directories must be new. The excerpts below adapt real input formats and do not replace those complete examples.

<a id="完整来源字段"></a>
## Complete source fields

Paths are relative to `sources[]`; for example, `reader.decode_policy` is `sources[].reader.decode_policy`. These fields apply to `can_asc` or `raw_can_csv` source items.

| Field | Type and requirement | Default | Meaning and basis |
|---|---|---|---|
| `name` | Optional string | `source_1`, etc. | Unique source name, such as `bus`, referenced by `signals.source`. |
| `source_type` | Required for raw CSV; optional for ASC | `asc_or_blf` | `can_asc` selects ASC; `raw_can_csv` selects raw-message CSV. Choose from contents, not only extension. ASC usually omits it. |
| `path` | Path string/list; exactly one of path/paths | None | File, directory, wildcard, or explicit list using the same selection rules as paths. Relative to the declaring file. |
| `paths` | Path string/list; exactly one of path/paths | None | Expands to 1–4096 continuous files. Explicit lists preserve acquisition order; directories/wildcards use natural order. |
| `dbc_by_channel` | Required object | None | Exactly one channel and DBC per source, such as `{"1":"sample.dbc"}`. Keys are positive decimal strings starting at 1, without leading zeros. Paths are relative to the configuration. |
| `time` | Optional for ASC; CSV must specify unit | Relative; ASC unit s | Time interpretation and synchronization from acquisition settings, headers, and synchronization evidence. |
| `time.time_type` | Optional string | `relative` | Relative common-origin time or `absolute` calendar time. Do not invent absolute time without a reliable date. |
| `time.unit` | Required for CSV; optional for ASC | s for ASC | s/ms/us/ns or ISO8601 date text. ASC must use s. CSV combinations follow the time-format table below. |
| `time.clock` | Optional for relative; absent for absolute | Source-specific name | An established relative origin, such as `test_start`. Naming does not synchronize devices. |
| `time.offset` | Optional duration string | `"0s"` | Source-wide signed correction from calibration. Original 5 s plus -2s becomes common 3 s. |
| `time.timezone` | String, required for ASC absolute or date text needing a timezone | None | Fixed timezone such as UTC or +08:00. Omit for relative and numeric time. Use equipment/location settings; it cannot supply a missing date. |
| `offsets` | Optional duration-string array | `"0s"` per file | Per-file corrections, with one item per expanded path. Add to source `time.offset`, based on known acquisition origins. |
| `reader` | Required object for raw CSV; optional for ASC | ASC defaults below | ASC dialect or CSV columns/time format. Match the actual exporter; do not copy another layout blindly. |
| `reader.decode_policy` | Optional string | `strict` | strict, partial, or legacy DBC behavior. Usually strict; choose alternatives only for a specific requirement. See [decoding policy](inputs.md#decode-policy) for exact failure and missing-value behavior. |
| `metadata` | Optional object | `{}` | Source notes, such as recorder model. Does not change decoding. |

Explicit files retain order; matched files use natural order. Default sources may mix ASC/BLF; explicit can_asc selects only ASC. Time regression does not automatically become the next day. If a second file restarts at zero and is known to begin at session second 100, explicitly set its offset to 100s. Run independent experiments separately.

<a id="asc常见格式直接读取"></a>
## ASC: read common formats directly

This excerpt replaces the root `sources` list of a complete analysis. Supply actual `sample.asc` and `sample.dbc`; do not insert a second `sources` parent inside an existing item.

```yaml
sources:
  - path: sample.asc
    dbc_by_channel:
      '1': sample.dbc
```

Fields below are inside `sources[].reader`.

| ASC field | Type and requirement | Default | Meaning and basis |
|---|---|---|---|
| `version` | Optional string | `"vector-asc-v1"` | Select one of the three line layouts below by actual message structure, not filename. |
| `encoding` | Optional string | `"utf-8-sig"` | utf-8, utf-8-sig, ascii, gbk, cp1252, iso8859-1, or standard aliases. Match the export encoding; no guessing. |

| `reader.version` | Supported layout |
|---|---|
| `vector-asc-v1` (default) | Classic: `0.1 1 123 Rx d 1 FF`; FD: `0.1 CANFD 1 Rx 123 1 0 1 1 FF`. |
| `vector-asc-statistics-v1` | The classic layout with a strictly matching `Length = … BitCount = … ID = …` statistics suffix; trailing ID must match the main ID. |
| `sclicer-asc-v1` | FD: `0.1 CANFD 1 123 Rx 1 0 d 1 1 FF`; classic frames can also appear. |

ASC time unit defaults to s and, if explicit, must be s. Encoding defaults to utf-8-sig; UTF-16/32 are unsupported. A line not matching the selected dialect fails; the reader does not try different parsers until one accepts it.

ASC channel 1 is configuration channel 1. ID suffix `x` marks extended frames; ID magnitude alone cannot decide. FD DLC differs from byte count: DLC 10 means 16 bytes, 15 means 64. A zero-byte FD data frame is not automatically a remote frame.

Two meanings of absolute/relative time must be distinguished:

| Location | Meaning |
|---|---|
| ASC header `timestamps absolute` | Each line is elapsed time from the log-block origin. Values 0.1 and 0.2 mean 0.1 and 0.2 seconds since that origin. |
| ASC header `timestamps relative` | Each line is elapsed time since the preceding record; the reader accumulates increments. |
| Configuration `time.time_type="absolute"` | Analysis time corresponds to a calendar date, using the ASC header date and declared timezone. |

Without a reliable acquisition date, use relative analysis time. Do not substitute today's computer date for the log date.

<a id="原始csv明确每一列代表什么"></a>
## Raw CSV: declare each column's meaning

This partial root `sources` section needs your actual input and DBC plus the rest of the analysis:

```yaml
sources:
  - path: sample.csv
    source_type: raw_can_csv
    dbc_by_channel:
      '1': sample.dbc
    time:
      unit: s
    reader:
      time_format: numeric
      id_base: 16                          # Unprefixed ID text is hexadecimal
      layout:
        fields:
          timestamp: time                 # Original CSV time header
          frame_id: id                    # Original CSV ID header
          data: data                      # Payload bytes, not decoded values
```

<a id="reader时间id和数据字节怎样读取"></a>
### reader: time, ID, and payload parsing

Fields are inside `sources[].reader`; `layout` is another nested object. Do not place layout encoding/delimiter directly in this reader object. A payload such as `01 FF` contains two bytes; the message ID is separate.

| Field | Type and requirement | Default | Meaning and basis |
|---|---|---|---|
| `time_format` | Required string | None | `numeric`, `clock`, `clock-ms-us-v1`, or `iso8601`, selected using the actual time text below. |
| `layout` | Required object | None | CSV encoding, delimiter, headers, and field mappings from actual export definitions. |
| `id_base` | String `auto` or integer 10/16; optional | `auto` | Auto recognizes 0x hexadecimal, 0b binary, otherwise decimal. Explicit 16 is needed for unprefixed hexadecimal. Fixed integer values are not reparsed by textual base. Text 100 means 100 by default, 256 with base 16. |
| `length_base` | Optional integer | 10 | Base 10 or 16 for length/DLC text. Independent of ID base; base 16 can read text such as 0x08. |
| `channel_origin` | Optional integer | 0 | Original CSV channels start at 0 or 1. Convert internally to zero-based numbering while configuration remains 1-based. Origin 1 maps raw 1 to public 1; origin 0 maps raw 0 to public 1. |
| `payload_style` | Optional string | `"spaced"` | `spaced`: whitespace-separated bytes such as `01 FF`; `contiguous`: an even number of adjacent hexadecimal digits such as `01FF`. |
| `rollover_min_drop` | Optional duration string | Backwards time rejected | Only clock/clock-ms-us-v1: a positive threshold below 86400 s for recognizing a next-day rollover. A backwards drop at least this large advances the date. Twelve hours is `"43200s"`, not 12h. Use only for known continuous time-of-day logs, never to conceal ordinary disorder. |

| `time_format` | Input example | Time settings and interpretation |
|---|---|---|
| `numeric` | `1500` | Explicit s/ms/us/ns; with ms this is 1.5 seconds. No unit inference from digit count. |
| `clock` | `14:05:40.1512` | Relative, unit s. Time since midnight; fractional part is 0.1512 seconds. |
| `clock-ms-us-v1` | `14:05:40.151.2` | Relative, unit s. Final groups are 151 ms and 2 µs: 0.151002 seconds. |
| `iso8601` | `2026-10-23T14:05:40+08:00` | Absolute, unit ISO8601. Text already supplies UTC+08:00; text without a timezone needs `time.timezone`, such as +08:00. |

For a continuous log moving from `23:59:59` to `00:00:01`, the clock drops nearly 24 hours. Explicit `rollover_min_drop: "43200s"` interprets a drop of at least 12 hours as next day, giving a 2-second interval. Without it, this is a regression error. A 1-second regression still fails with this setting.

<a id="最小列映射"></a>
### Minimal column mapping

Common tables need only time, ID, and payload mappings; each column need not be wrapped in `column`:

```yaml
sources:
  - source_type: raw_can_csv
    path: data/raw.csv
    dbc_by_channel:
      '1': network.dbc
    time:
      unit: s
    reader:
      time_format: numeric
      layout:
        fields:
          timestamp: time
          frame_id: id
          data: data
```

`timestamp: time` equals `timestamp: {column: time}`. Integer shorthand such as `timestamp: 1` selects the first column. Constants require `{fixed: VALUE}`. The unique DBC channel is supplied automatically; frames default to `frame_kind: data`, with length from actual bytes. Omitted direction remains unknown, allowing ordinary numeric analysis; complete raw-frame export needs actual direction. Standard/extended and CAN/FD flags may be omitted only when bindings and DBC identify them uniquely. Explicit lengths, kinds, and flags are strictly checked rather than replaced by defaults.

<a id="layout表头编码和分隔符"></a>
### layout: headers, encoding, and delimiter

Raw CSV uses `sources[].reader.layout.encoding` and `.delimiter`; decoded `signal_csv` places them directly in `reader`. These are different layouts.

| Field | Type and requirement | Default | Meaning and basis |
|---|---|---|---|
| `fields` | Required object | None | Map each frame attribute to a column or fixed value, using the field table below. |
| `encoding` | Optional string | `"utf-8-sig"` | utf-8, utf-8-sig, ascii, gbk, cp1252, iso8859-1, or standard aliases. Use actual export encoding; no auto detection. |
| `delimiter` | Optional string | `","` | One character, such as comma or double-quoted `"\t"`. Newline, double quote, and NUL are forbidden. |
| `has_header` | Optional Boolean | true | True: first unskipped record supplies column names. False: use integer column numbers, not names. |
| `skip_rows` | Optional integer | 0 | Skip 0–100000 CSV records before the header/data. Two leading explanatory records require 2; the reader does not search for a header. |
| `layout_version` | Optional string | `"raw-can-csv-layout-v1"` | The only current layout-structure version. Use that value or omit. |

Standard CSV double quotes are handled by the reader. This version provides no configurable `quotechar` or quoting options.

<a id="fields每个报文字段代表什么"></a>
### fields: frame attributes

The full path is `sources[].reader.layout.fields.<ATTRIBUTE>`. In `frame_id: id`, `frame_id` is the program attribute and `id` is the original CSV header; do not rename the original ID column to `name`.

Types below are obtained after parsing cell text. Select a column directly or use a `column`/`fixed` object. Common direction text Rx/Tx and `接收`/`发送` is recognized directly; use `value_map` for other codes.

| Field | Parsed type and requirement | Meaning and basis |
|---|---|---|
| `timestamp` | Required string/integer | Time column or a reliably constant timestamp, interpreted by time_format and time.unit. |
| `frame_id` | Required string/integer | CAN ID from a column or confirmed constant. Text uses id_base. Standard range 0–2047; extended 0–536870911. Check against DBC. |
| `channel` | String/integer; optional for a unique DBC channel | Original channel, parsed as decimal then reduced by channel_origin; result must be nonnegative. Fixed is valid only for a confirmed single channel. |
| `is_rx` | Boolean; optional for ordinary analysis | True receive, false transmit. Rx/Tx and `接收`/`发送` are recognized; special encodings use value_map. Omission remains unknown, not invented Rx. Complete raw export requests missing direction. |
| `is_extended` | Optional Boolean | False standard, true extended. Use a real column when present; otherwise infer uniquely from binding/DBC or require clarification. An ID below 2048 does not prove standard type. |
| `is_fd` | Optional Boolean | True CAN FD, false classic CAN. Original flags take precedence; omitted type needs unambiguous binding/DBC evidence. It affects payload limits and DLC interpretation. Do not infer from payload length or signal name. |
| `frame_kind` | Optional string; default `data` | `data` carries data, `remote` requests transmission, `error` is an error frame. Map actual kind codes, or use a fixed value only when confirmed constant. Length rules follow below. |
| `data` | Required string | Actual byte text such as `"01 FF"` or `"01FF"`, parsed using payload_style. Empty payload is an empty string, not a decoded physical value. |
| `payload_length` | String/integer; data frames may omit | Actual byte count: classic 0–8, FD at most 64. If declared, it must equal the payload's actual byte count. |
| `dlc_code` | String/integer; data frames may omit, remote requires it | Data length code. Classic 0–8; FD 0–15, where 9–15 represent 12, 16, 20, 24, 32, 48, 64 bytes. Use actual DLC, not byte count. |
| `bitrate_switch` | Optional Boolean; default false | FD data-phase bitrate switching: true switches, false does not. Classic CAN requires false. Map actual BRS flags rather than invent them. |
| `error_state_indicator` | Optional Boolean; default false | FD transmitting node's ESI: true error-passive, false error-active. Classic CAN requires false. This does not indicate whether analysis failed. |

Omitting type columns works only where analysis bindings and DBC uniquely identify the type. A DBC marked FD may accompany actual classic CAN, so neither DBC marking nor a short payload alone establishes it. Provide binding `is_fd`, or a truthful original column/constant. Standalone raw-frame reading without DBC still needs type information. Exported unbound messages also require reliable type information. ASC/BLF use their actual embedded flags.

Configuration ID syntax does not change file ID syntax: unprefixed ASC IDs may be hexadecimal; CSV follows `id_base`.

Data-frame DLC must agree with byte count. Remote frames must be classic CAN with empty data and an explicit requested DLC; an explicit payload_length must be zero because no bytes are present. Error frames require empty data and omitted/zero DLC. Zero bytes alone do not make a remote frame.

<a id="每个字段怎样取值columnfixedvalue_mapstrip"></a>
### Value selection: column, fixed, value_map, and strip

These belong inside an individual mapping object, such as `sources[].reader.layout.fields.is_rx.value_map`, not directly under layout or fields. Expand shorthand only when extra settings are needed.

| Field | Type and requirement | Default | Meaning and basis |
|---|---|---|---|
| `column` | String/integer; exactly one of column/fixed | None | Header text, such as `"方向"`, or integer column 1–4096. Integer 1 selects the first column; string `"1"` selects a column named 1. Header names have at most 256 characters. |
| `fixed` | String/integer/Boolean; exactly one of column/fixed | None | A confirmed constant for every record, such as `{"fixed":true}` when all frames are received. It must not conceal an unknown flag. Zero, false, and empty text are actual values. |
| `value_map` | Optional object/null | null: no mapping | 1–256 text-to-value entries, such as `{"Rx":true,"Tx":false}`. Unlisted text is an error. Target types must match the frame attribute. |
| `strip` | Optional Boolean | true | Strip leading/trailing cell whitespace before mapping. False preserves meaningful edge whitespace. Does not remove spaces between payload bytes. |

Mapping keys/string targets are at most 256 characters; fixed strings at most 16384. Fixed integers range from −2⁶³ to 2⁶⁴−1, with smaller ID/length-specific limits still enforced. Never supply both column and fixed. Mapping can transform fixed `"Rx"` to true, though directly supplying Boolean true is clearer.

Unused CSV columns are not parsed; missing required columns fail. When only required messages matter and neither full raw frames nor whole-source time is needed, raw CSV checks ID first. Nonmatching rows skip payload/frame-type parsing and usually time. With midnight rollover enabled, their times are still read so the date transition is not missed. Target rows retain format, time, and length checks. Full raw export or whole-source time requires all read records to be checked. Errors identify record locations; correct the input before rerunning.

<a id="怎样选信号和查看来源"></a>
## Select signals and inspect source information

Signal `field` requires frame_id and signal; unique DBC channels allow omitted channel and frame type can be inferred as described under [CAN fields](inputs.md#can-field). A signal name alone is insufficient because different messages may reuse it. Source information retained in output depends on requested analysis/export features; unrequested records are not kept merely to explain provenance.

Some DBC messages use a selector to alternate signals in the same bytes—for example, temperature in one frame and voltage in another. This is multiplexing. If the declared temperature is absent in the current frame, the reader produces an invalid update rather than retaining the previous temperature as currently valid.

Other valid records still expire according to `valid_for`; after expiry and before the next valid update, the value is unknown. For signals or raw messages as outputs, configure the [two export types](exports.md). Input format does not determine output format.

[ASCSpec/ASCRead](../reference/chronaxis.sources.asc.md), [CANCSVSpec/CANCSVRead](../reference/chronaxis.sources.raw_csv.md), and [CANTextDecodeRead](../reference/chronaxis.sources.text_can_decode.md) are Chinese implementation references with low-level arguments, returns, and exceptions. Usually `AnalysisRunner` handles the files for you.

<a id="无关报文的时间回退"></a>
## Backwards timestamps in unrelated messages

Default `reader.input_check: auto` requires only selected ASC channels/IDs to remain ordered. Other frames still establish earliest/latest observation during the same read. An unrelated Tx frame's microsecond regression does not stop analysis and its time is not modified. Full checking or raw export requiring complete order still rejects whole-source regression. Required-message regressions, including across continuous files, always fail; no automatic sorting, clamping, or cleaning occurs.

ASC-header relative timestamps are per-record increments and must accumulate. They differ from relative analysis time in `time.time_type`. Calendar transitions use explicit ASC dates/trigger blocks rather than guesses from ordinary regressions. Raw CSV keeps its declared time layout and channel_origin interpretation.
