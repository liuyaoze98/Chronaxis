# Configuration field index

<a id="配置字段参考"></a>

Read [Configuration structure](configuration.md) first to see how the root sections fit together. The linked chapters describe each field's type, required conditions, default, supported choices, and consequences. The generated schema is an additional validation reference.

<a id="怎样读取字段路径"></a>
## Reading a field path

`dataset.domain.start` means the `start` field under `domain`, under `dataset`: three levels in the configuration. Do not write it as a key containing dots.

`signals[]` means each item in the signal list. `signals[0]` identifies the first item, using a zero-based list position. In YAML, list items start with `-`, and child fields use indentation. Use two spaces per level and no tabs.

See [Dotted paths and YAML](configuration-language.md#field-paths) and [Analyze only 2–5 seconds](dataset.md#只分析2到5秒). Edit an existing parent block rather than adding a duplicate root key.

<a id="按根字段查找"></a>
## Find a field by root section

| Root field | Detailed reference | What to look for |
|---|---|---|
| `config_version` | [Configuration syntax](configuration-language.md) | Required analysis version. |
| `dataset` | [Dataset and analysis range](dataset.md) | Ordinary `name`; optional `entity`, `session`, `domain`, and metadata. |
| `sources` | [Inputs](inputs.md), [Text inputs](text-inputs.md) | Source type, paths, DBC, reader settings, and source time. |
| `signals` | [Signals](signals.md) | Binding, type, unit, period, validity, choices, and conversion. |
| `derived` | [Expressions](expressions.md) | Named expressions and units. |
|lookups|[One-dimensional lookup and interpolation](expressions.md#lookup-reference)|
| `transforms` | [Time-series transforms](temporal-transforms.md) | Version 4 rolling statistics and rates. |
|aggregations|[Result aggregation](aggregations.md): fields, operations, grouping and completeness|
| `rules` | [Event rules](rules.md) | Conditions and event generation. |
| `windows` | [Windows](windows.md) | Ranges around events. |
| `sequences` | [Sequences](sequences.md) | Pairing and latency. |
| `calculations` | [Calculations](calculations.md) | Operations, expressions, conditions, and scopes. |
| `message_calculations` | [Message calculations](message-calculations.md) | Per-message accumulation. |
| `intervals` | [Calculation intervals](intervals.md) | Actual, fixed, or DBC periods. |
| `presets` | [Presets](presets.md) | Ready-made combinations and their parameters. |
| `execution` | [Execution](execution.md) | Backend, batching, and resource limits. |
| `outputs` | [Outputs](exports.md), [Signal exports](signal-exports.md), [Raw CAN exports](can-exports.md) | Output formats and explicitly requested exports. |
| `imports`, `overrides` | [Shared definitions](imports.md) | Reuse and override local definitions. |
| `diagnostics`, `metadata` | [Execution](execution.md) | Optional diagnostics and run notes. |

For the complete machine-readable structure, see [Configuration schema](reference/configuration-schema.md). Schema words such as `properties`, `required`, and `oneOf` describe validation; they are not business configuration fields.

Python function arguments are a separate reference. Only functions that explicitly accept a public configuration dictionary accept these root fields. See [Public API](api.md).
