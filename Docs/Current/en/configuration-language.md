# Configuration file syntax

<a id="配置文件语法"></a>

Use a UTF-8 `.yaml` or `.yml` file for a configuration you edit by hand. Start with the complete `analysis.yaml` in [Quick start](quickstart.md). JSON accepts the same configuration fields.

<a id="先认识字段映射和列表"></a>
<a id="先认识字段-映射和列表"></a>
## Fields, mappings, and lists

In `name: energy`, `name` is a field (or key), and `energy` is its value. A **mapping** groups fields that describe one object. Indentation places a field inside its parent. Root fields have no indentation. Use two spaces per level, and do not use tabs.

A **list** contains several items. Each item starts with `-`. A source list can describe several inputs, and a calculation list can request several results. Text after `#` is a comment, not a configuration value. If indentation is hard to see, enable the editor's display of whitespace.

<a id="field-paths"></a>
<a id="点号路径怎样变成实际配置"></a>
## Turning a dotted field path into YAML

A reference such as `dataset.domain.start` means “the `start` field inside `domain`, inside `dataset`.” It is a lookup notation, not a key to paste into your YAML file. To change the analysis range, edit your existing `dataset` block; do not append a second block with the same name.

```yaml
dataset:        # Analysis identity and optional input range
  name: energy  # Name used to identify and reference this object
  domain:       # Requested analysis start and end
    start: 2s   # Inclusive start of the analysis range
    end: 5s     # End of the analysis range
```

The following inline mapping means exactly the same thing. The braces group the two child fields; the comma separates them.

```yaml
dataset:                        # Analysis identity and optional input range
  name: energy                  # Name used to identify and reference this object
  domain: {start: 2s, end: 5s}  # Requested analysis start and end; Inclusive start of the analysis range; End of the analysis range
```

With the ASC teaching input, this range gives **22 J**. See [Analyze only 2–5 seconds](dataset.md#只分析2到5秒) for the input, command, and calculation.

<a id="列表中的每一项怎样写"></a>
## Writing list items

Replace the existing `calculations` block with this fragment to calculate both energy and an arithmetic sample average. It assumes `power` has already been defined as a signal.

```yaml
calculations:               # Requested statistics or selected rows
  - name: energy            # Name used to identify and reference this object
    operation: integral     # Calculation to apply to the expression
    expr: power             # Formula using the declared signal or derived names
  - name: sample_average    # Name used to identify and reference this object
    operation: sample_mean  # Calculation to apply to the expression
    expr: power             # Formula using the declared signal or derived names
```

In field references, `sources[]` means each item in the source list. `sources[0]` means its first item: list positions start at zero. This notation does not change the one-based channel numbers used in user configurations. `sources[].time.unit` is the `unit` field under `time` in each source.

By contrast, `[power]` in an actual YAML value is an inline list containing one item. Do not confuse this YAML syntax with `[]` in a reference path.

<a id="值引号与表达式"></a>
<a id="值-引号与表达式"></a>
## Values, quotation marks, and expressions

- YAML `true` and `false` are Boolean values. Words such as `yes` and `no` are strings.
- `0` is a number; `0s` is a duration string. `null` is an explicit empty value.
- Omitted fields, `null`, an empty list `[]`, and the number `0` are different. Use the omission/default rules for the particular field.
- Quote strings that contain a colon followed by a space, begin with a special YAML character, or look like a number but must remain text. For example, write a channel key as `'1'` and a preset version as `'1'`.
- Dates and durations remain text for Chronaxis to interpret.

A condition such as `enabled == True` is an expression string. Its `True` belongs to the expression language; it is separate from YAML's `true`. Expressions support the documented [operators and functions](expressions.md), not arbitrary Python code.

<a id="配置api与schema要分开读"></a>
<a id="配置-api与schema要分开读"></a>
## Configuration, Python API, and JSON Schema

| What you are reading | How to use it |
|---|---|
| A YAML fragment | Insert it at the stated parent level, or replace the existing block as instructed. |
| A dictionary passed to `AnalysisPlan.from_dict` | Use Python literals such as `True`, `False`, and `None`. The configuration field meanings remain the same. |
| A Python function argument such as `work_dir` | Pass it to that function. It is not automatically a configuration field. |
| JSON Schema keys such as `properties`, `required`, or `oneOf` | These describe how a validator checks a configuration; do not copy them into the analysis configuration. |

The analysis configuration does not accept a `$schema` field. See [Schema and editor setup](schema-editor.md) for associating a schema through your editor.

<a id="支持的yaml范围"></a>
## Supported YAML features

| Supported | Not accepted |
|---|---|
| One document, mappings with string keys, and lists | Duplicate keys, non-string keys, and multiple YAML documents |
| JSON-compatible scalar values, including finite numbers | `NaN` and infinity |
| Comments and multiline strings | Custom tags, anchors, aliases, and merge keys |
| Dates and durations represented as text | Environment-variable substitution and template expansion |
| Nesting up to 64 levels | Deeper structures |

If you write a YAML version directive, use version 1.2. Dates are not automatically converted into Python date objects. Quote numeric-looking mapping keys when they are intended to be strings.

<a id="各种版本字段"></a>
## Version fields

Each version field belongs to a different kind of document or feature:

| Field | Value and purpose |
|---|---|
| Root `config_version` | Required integer: `4`. |
| Root `batch_version` | Integer `1` in a batch configuration. |
| `presets[].version` | Optional string, default `'1'`, for the selected preset. |
| `sources[].reader.version` | Selects the reader's supported text format. ASC defaults to `vector-asc-v1`; see [Text inputs](text-inputs.md) for other formats. |

A shared definitions file contains only `sources`, `signals`, and/or `derived`. It does not have a `config_version` field.
