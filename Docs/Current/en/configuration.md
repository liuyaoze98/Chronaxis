# Configuration structure

<a id="分析配置结构"></a>

Use YAML for hand-written configurations and JSON for exchange between tools. Both use the same fields. Analysis configurations require the integer `config_version: 4`. A missing or unsupported version is rejected. JSON Schema describes the accepted structure; it is not another configuration format.

The root sections below are siblings. For example, `signals` is not nested inside `sources`, and `calculations` is not nested inside `dataset`.

<a id="根字段"></a>
## Root fields

| Field | What it controls and what omission means |
|---|---|
| `config_version` | Required integer: `4`. Other analysis configuration versions are rejected. |
| `dataset` | Required analysis identity, normally just `name`. `entity` and `session` inherit that name. Omit `domain` to use the actual observed range. |
| `sources` | Input definitions. At least one must exist after shared definitions are expanded. ASC/BLF can be detected automatically; CSV and memory sources need their appropriate source type and reader settings. |
| `signals` | Signal definitions, which may come from shared definitions. CAN data can obtain `dtype` and `unit` from the DBC; decoded CSV and memory inputs need explicit definitions. See the signal chapter for `valid_for` defaults. |
| `imports` | Optional ordered list of local shared files. They can supply `sources`, `signals`, and `derived`, one level deep. Duplicate definitions are rejected; intentional changes use `overrides`. |
| `overrides` | Optional changes to allowed fields of existing named definitions. It cannot create new definitions. |
| `lookups` | Optional. Map an input to a value from calibration points; see the [lookup and interpolation field reference](expressions.md#lookup-reference) and [voltage example](../examples/lookup-power.yaml). |
| `derived` | Optional named expressions; defaults to empty. Units are inferred, and an explicitly supplied unit is checked. |
| `transforms` | Optional. Produce a new time series such as a rolling mean or rate; see [time-series transforms](temporal-transforms.md). |
| `aggregations` | Optional. Summarize scalar calculation results for sessions, events or segments and request/response delays, or count events and final window segments within this analysis; for example, P95 across load means. See [Result aggregation](aggregations.md). |
| `rules` | Event rules, each selected by `rule_type`. |
| `presets` | Optional ready-made combinations selected by `preset_type`, including charging, fault pairing, and threshold alarms. |
| `windows` | Time ranges around events. |
| `sequences` | Request/response pairing and latency analysis. |
| `calculations` | Ordinary calculations selected by `operation`, with an expression or condition and an optional scope. |
| `message_calculations` | Calculations performed for individual matching messages. They have different interval semantics from ordinary time integration. |
| `intervals` | Shared calculation-interval choice; defaults to actual intervals. A local `interval` overrides the shared choice. |
| `outputs` | Defaults to readable Chinese CSV tables and a manifest. CSV/JSONL can be selected explicitly. Contribution details, signal exports, and raw CAN exports are off unless requested. |
| `execution` | Calculation implementation and resource limits; the default backend is NumPy. |
| `diagnostics` | Optional diagnostics; all switches default to false. |
| `metadata` | Optional notes, default `{}`. `device_label` defaults to `pending` and follows its documented value restrictions; other notes do not affect computation. |

Field names are case-sensitive. Unknown fields are errors. A diagnostic may suggest a spelling correction, but the program does not silently accept it. Duplicate YAML keys and conflicting object names are also rejected. Preserve DBC names exactly; use a signal's user-facing `name` as your convenient alias.

<a id="常用字段怎样简写"></a>
## Keeping ordinary configurations short

Omit a field when its documented default, inheritance, or reliable detection already gives the behavior you want. User-assigned names use `name`; references identify their target with fields such as `source`, `rule`, or `window`. A CAN message number is `frame_id`, and the signal's DBC name is `field.signal`. Expressions refer to configured signal names.

For example, replace the existing calculation list with the following to integrate an already defined `power` signal over the dataset:

```yaml
calculations:              # Requested statistics or selected rows
  - name: energy           # Name used to identify and reference this object
    operation: integral    # Calculation to apply to the expression
    expr: power            # Formula using the declared signal or derived names
```

The surrounding source and signal definitions are still required. Specify a calculation scope or an interval only when this task needs a choice other than the defaults.

Reader settings are grouped under `reader`; value conversions are grouped under `conversion`. `time.clock` identifies a shared time origin, whereas `resampling.start` identifies the start of a sampling grid. These names describe different choices.

A dotted path such as `dataset.domain.start` identifies where a field belongs. It is not a literal YAML key; see [Configuration syntax](configuration-language.md#field-paths). Omission uses the documented default. Whether explicit `null` is accepted depends on the field: for example, `execution.spool_quota_bytes: null` sets no additional spool disk quota. Invalid types and values are rejected.

Ordinary execution checks, calculates, and retains what the requested results require. Additional diagnostics are enabled explicitly.

<a id="配置语言"></a>
## Configuration language

The loader accepts a single JSON or restricted YAML document with string-keyed mappings, lists, and JSON-compatible scalar values. Numbers must be finite, and nesting is limited to 64 levels. YAML comments and multiline strings are supported; duplicate keys, non-string keys, multiple documents, custom tags, anchors, aliases, and merge keys are rejected. There is no environment substitution or template expansion. Dates and durations remain text. A YAML version directive, if present, must specify 1.2.

Read [Configuration file syntax](configuration-language.md) before editing nested structures or list items.

<a id="时间与统计术语"></a>
## Time and statistics terms

A signal's `valid_for` limits how long its most recent value can be used after an update. Once that time has passed, the value becomes unknown. A `timeout` limits how long a rule waits. A `minimum_duration` determines how long a condition must hold before it qualifies. These settings serve different purposes.

An arithmetic sample average and a time-weighted average can also differ. In the teaching input, `sample_mean` gives **6 W**, while the time-weighted result is **38 / 6 W**. See [Calculations](calculations.md) for the values and intervals used.

<a id="功能与字段参考"></a>
## Finding a feature or field

Start with the relevant task chapter, such as [Event windows](windows.md) or [Calculations](calculations.md). Use the [configuration field index](configuration-reference.md) to find every root section and its detailed field reference.

<a id="配置错误定位"></a>
## Locating a configuration error

When available, a diagnostic identifies the file, line, column, original field path, object, error code, offending value, and a correction hint. If a field is missing, the location points to the nearest existing parent rather than inventing a line for the missing field.

Use `validate` for a text diagnostic or machine-readable JSON diagnostic. [Schema and editor setup](schema-editor.md) explains editor validation without adding an unsupported `$schema` field.
