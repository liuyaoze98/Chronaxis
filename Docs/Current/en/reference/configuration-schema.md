# Complete configuration schema reference

Start with the [configuration guide](../configuration.md). The paths below locate nodes in JSON Schema, not literal keys to paste into YAML. `$defs` holds reusable definitions and `$ref` points to them. This page translates descriptions; the linked original schemas define validation. Runtime plan checks also validate references, units, and supported combinations.

## analysis.schema.json

[Original validation schema](../../../Schema/analysis.schema.json)

### `analysis.schema.json: $`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$comment": "分析配置格式4；本地相对引用。字段结构由本规范检查，展开后的跨字段约束由计划模型检查。",
  "title": "Current Chronaxis analysis configuration",
  "description": "Current analysis configuration version 4 with automatic compatible-unit conversion. Defaults to actual record intervals and requested outputs only; AnalysisPlan checks references, units, drivers and time bounds.",
  "type": "object",
  "required": [
    "config_version",
    "dataset"
  ],
  "dependentRequired": {
    "overrides": [
      "imports"
    ]
  },
  "additionalProperties": false
}
```

### `analysis.schema.json: $.allOf[0].properties.signals`

```json
{
  "description": "Restrict signal fields to those supported by the selected version."
}
```

### `analysis.schema.json: $.allOf[0].properties.signals.items.dependentSchemas.code_dtype.properties.dtype`

```json
{
  "const": "enum",
  "description": "Signal value type; it determines which additional fields apply."
}
```

### `analysis.schema.json: $.allOf[0].properties.signals.items.properties.signals`

```json
{
  "description": "Restrict signal fields to those supported by the selected version."
}
```

### `analysis.schema.json: $.allOf[0].properties.signals.items.properties.signals.items.dependentSchemas.code_dtype.properties.dtype`

```json
{
  "const": "enum",
  "description": "Signal value type; it determines which additional fields apply."
}
```

### `analysis.schema.json: $.allOf[1]`

```json
{
  "$comment": "省略domain时由同次读取确定实际观测范围，普通分析与按需导出均可使用。"
}
```

### `analysis.schema.json: $.allOf[2].then.properties.signals`

```json
{
  "description": "Bind original source fields to simple analysis signal names, specifying type, unit, and validity duration."
}
```

### `analysis.schema.json: $.allOf[2].then.properties.signals.items.not`

```json
{
  "required": [
    "signals"
  ]
}
```

### `analysis.schema.json: $.allOf[2].then.properties.signals.items.properties.field`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Actual field in the source: an original field name for signal tables/memory, or a CAN channel/message/signal locator object."
}
```

### `analysis.schema.json: $.allOf[2].if`

```json
{
  "required": [
    "sources"
  ]
}
```

### `analysis.schema.json: $.allOf[2].if.not`

```json
{
  "required": [
    "imports"
  ]
}
```

### `analysis.schema.json: $.allOf[2].if.properties.sources`

```json
{
  "description": "Sources in declaration order. Put consecutive files in one source's paths. Loading may enumerate filenames and read DBC metadata needed for omitted signal settings, but does not read business records."
}
```

### `analysis.schema.json: $.allOf[2].if.properties.sources.items`

```json
{
  "required": [
    "source_type"
  ]
}
```

### `analysis.schema.json: $.allOf[2].if.properties.sources.items.properties.source_type`

```json
{
  "enum": [
    "memory",
    "signal_csv"
  ],
  "description": "Source type, selecting the reader and required fields. Options: \"memory\", ordered records embedded in configuration; \"signal_csv\", decoded-signal CSV."
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals`

```json
{
  "description": "Bind original source fields to simple analysis signal names, specifying type, unit, and validity duration."
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field`

```json
{
  "type": "object",
  "required": [
    "signal",
    "frame_id"
  ],
  "description": "Actual field in the source: an original field name for signal tables/memory, or a CAN channel/message/signal locator object.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.allOf[0].then.properties.frame_id`

```json
{
  "maximum": 2047,
  "description": "Integer message IDs for standard frames are limited to 2047. The plan loader checks the range after converting string IDs."
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.allOf[0].if`

```json
{
  "required": [
    "is_extended"
  ]
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.allOf[0].if.properties.is_extended`

```json
{
  "const": false,
  "description": "When standard frame format is explicitly selected, an integer ID must fit in 11 bits."
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "CAN channels in user configuration start at 1; 1 maps to internal channel 0. If omitted, inherits the source's unique channel."
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.properties.signal`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name in the DBC, used with frame_id to locate a signal within that message. This is not the analysis alias."
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.properties.frame_id`

```json
{
  "description": "CAN message ID, as an integer or string. 0x is hexadecimal, 0b binary, and no prefix decimal. The parsed value must be 0 to 536870911; an explicitly standard frame is limited to 2047."
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.properties.is_extended`

```json
{
  "type": "boolean",
  "description": "Optional standard/extended frame constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.allOf[3].then.properties.signals.items.properties.field.properties.is_fd`

```json
{
  "type": "boolean",
  "description": "Optional CAN/CAN FD constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.allOf[3].if`

```json
{
  "required": [
    "sources"
  ]
}
```

### `analysis.schema.json: $.allOf[3].if.not`

```json
{
  "required": [
    "imports"
  ]
}
```

### `analysis.schema.json: $.allOf[3].if.properties.sources`

```json
{
  "description": "Sources in declaration order. Put consecutive files in one source's paths. Loading may enumerate filenames and read DBC metadata needed for omitted signal settings, but does not read business records."
}
```

### `analysis.schema.json: $.allOf[3].if.properties.sources.items`

```json
{
  "required": [
    "source_type"
  ]
}
```

### `analysis.schema.json: $.allOf[3].if.properties.sources.items.properties.source_type`

```json
{
  "enum": [
    "can_blf",
    "can_asc",
    "raw_can_csv"
  ],
  "description": "Source type, selecting the reader and required fields. Options: \"can_blf\", raw CAN binary BLF; \"can_asc\", raw CAN text ASC; \"raw_can_csv\", raw CAN frame CSV with an explicit layout."
}
```

### `analysis.schema.json: $.anyOf[0]`

```json
{
  "required": [
    "imports"
  ]
}
```

### `analysis.schema.json: $.anyOf[1]`

```json
{
  "required": [
    "sources",
    "signals"
  ]
}
```

### `analysis.schema.json: $.properties.config_version`

```json
{
  "type": "integer",
  "description": "Analysis format number. Only integer 4 is accepted; older versions, omissions and incorrect types are rejected without conversion.",
  "const": 4
}
```

### `analysis.schema.json: $.properties.transforms`

```json
{
  "type": "array",
  "maxItems": 64,
  "description": "In version 4, compute rolling values and rates at real record updates or specified output ticks."
}
```

### `analysis.schema.json: $.properties.transforms.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "operation",
    "expr"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.else`

```json
{
  "required": [
    "window",
    "step"
  ]
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.else.properties.max_gap`

```json
{
  "description": "Do not set max_gap for this version or operation."
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.then`

```json
{
  "required": [
    "max_gap"
  ]
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.then.properties.window`

```json
{
  "description": "Do not set window for this version or operation."
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.then.properties.step`

```json
{
  "description": "Do not set step for this version or operation."
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.then.properties.origin`

```json
{
  "description": "Do not set origin for this version or operation."
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.then.properties.partial_policy`

```json
{
  "description": "Do not set partial_policy for this version or operation."
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.then.properties.minimum_coverage`

```json
{
  "description": "Do not set minimum_coverage for this version or operation."
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].then.if.properties.operation`

```json
{
  "const": "adjacent_rate",
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].if`

```json
{
  "required": [
    "operation"
  ]
}
```

### `analysis.schema.json: $.properties.transforms.items.allOf[0].if.properties.operation`

```json
{
  "$ref": "#/properties/transforms/items/properties/operation",
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.name`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Name assigned to this declaration and used by references."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.operation`

```json
{
  "enum": [
    "rolling_time_mean",
    "rolling_minimum",
    "rolling_maximum",
    "rolling_integral",
    "adjacent_rate",
    "window_rate",
    "sample_fit_slope"
  ],
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.expr`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Expression over bound signals or derived values used as input."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Requested result unit; it must be compatible with the quantity."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.window`

```json
{
  "type": "string",
  "pattern": "^\\s*[+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Select the window; the duration of a transform window must be positive."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.step`

```json
{
  "type": "string",
  "pattern": "^\\s*[+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Positive actual-time spacing between scheduled outputs."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.origin`

```json
{
  "type": "string",
  "description": "Actual time origin used to align outputs in the source clock."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.max_gap`

```json
{
  "type": "string",
  "pattern": "^\\s*[+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Longest permitted gap between adjacent actual updates."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.partial_policy`

```json
{
  "enum": [
    "strict",
    "report"
  ],
  "description": "Choose whether to return a partial value or null when data are incomplete."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.minimum_coverage`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "description": "Minimum fraction of the requested window covered by valid data."
}
```

### `analysis.schema.json: $.properties.transforms.items.properties.interval`

```json
{
  "$ref": "#/properties/calculations/items/properties/interval",
  "description": "Use actual intervals, a fixed period or a DBC period from raw messages."
}
```

### `analysis.schema.json: $.properties.aggregations`

```json
{
  "type": "array",
  "description": "Summarize calculations, pairings, events or windows within this run when requested."
}
```

### `analysis.schema.json: $.properties.aggregations.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "source",
    "operation"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[0].else.properties.q`

```json
{
  "description": "Do not set q for this version or operation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[0].then`

```json
{
  "required": [
    "q"
  ]
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[0].if.properties.operation`

```json
{
  "const": "quantile",
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[1].else.properties.ddof`

```json
{
  "description": "Do not set ddof for this version or operation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[1].if.properties.operation`

```json
{
  "const": "variance",
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[2].then.properties.field`

```json
{
  "description": "Do not set field for this version or operation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[2].then.properties.unit`

```json
{
  "const": "1",
  "description": "Requested result unit; it must be compatible with the quantity."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[2].if.properties.operation`

```json
{
  "const": "count",
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[3].then.then.properties.group_by`

```json
{
  "description": "Group rows by identifiers available on the selected source."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[3].then.then.properties.group_by.items`

```json
{
  "enum": [
    "dataset_id",
    "entity_id",
    "session_id",
    "sequence_id"
  ],
  "description": "Grouping key available for this source. Use each key at most once."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[3].then.then.properties.field`

```json
{
  "const": "delay_ns",
  "description": "Numeric column to read from the selected result rows."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[3].then.if.properties.source`

```json
{
  "required": [
    "sequence"
  ],
  "description": "Select the kind and name of the result to aggregate."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[3].if`

```json
{
  "required": [
    "source"
  ]
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[3].if.properties.source`

```json
{
  "$ref": "#/properties/aggregations/items/properties/source",
  "description": "Select exactly one calculation, sequence, rule or window from the current run."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[4].then.then.properties.group_by`

```json
{
  "description": "Group rows by identifiers available on the selected source."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[4].then.then.properties.group_by.items`

```json
{
  "enum": [
    "dataset_id",
    "entity_id",
    "session_id",
    "calculation_id",
    "parent_id"
  ],
  "description": "Grouping key available for this source. Use each key at most once."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[4].then.then.properties.field`

```json
{
  "const": "value",
  "description": "Numeric column to read from the selected result rows."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[4].then.if.properties.source`

```json
{
  "required": [
    "calculation"
  ],
  "description": "Select the kind and name of the result to aggregate."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[4].if`

```json
{
  "required": [
    "source"
  ]
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[4].if.properties.source`

```json
{
  "$ref": "#/properties/aggregations/items/properties/source",
  "description": "Select exactly one calculation, sequence, rule or window from the current run."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[5].then.then.properties.group_by`

```json
{
  "description": "Group rows by identifiers available on the selected source."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[5].then.then.properties.group_by.items`

```json
{
  "enum": [
    "dataset_id",
    "entity_id",
    "session_id",
    "rule_id"
  ],
  "description": "Grouping key available for this source. Use each key at most once."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[5].then.then.properties.operation`

```json
{
  "const": "count",
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[5].then.then.properties.field`

```json
{
  "description": "Do not set field for this version or operation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[5].then.if.properties.source`

```json
{
  "required": [
    "rule"
  ],
  "description": "Select the kind and name of the result to aggregate."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[5].if`

```json
{
  "required": [
    "source"
  ]
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[5].if.properties.source`

```json
{
  "$ref": "#/properties/aggregations/items/properties/source",
  "description": "Select exactly one calculation, sequence, rule or window from the current run."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[6].then.then.properties.group_by`

```json
{
  "description": "Group rows by identifiers available on the selected source."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[6].then.then.properties.group_by.items`

```json
{
  "enum": [
    "dataset_id",
    "entity_id",
    "session_id",
    "window_id"
  ],
  "description": "Grouping key available for this source. Use each key at most once."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[6].then.then.properties.operation`

```json
{
  "const": "count",
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[6].then.then.properties.field`

```json
{
  "description": "Do not set field for this version or operation."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[6].then.if.properties.source`

```json
{
  "required": [
    "window"
  ],
  "description": "Select the kind and name of the result to aggregate."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[6].if`

```json
{
  "required": [
    "source"
  ]
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].then.allOf[6].if.properties.source`

```json
{
  "$ref": "#/properties/aggregations/items/properties/source",
  "description": "Select exactly one calculation, sequence, rule or window from the current run."
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].if`

```json
{
  "required": [
    "operation"
  ]
}
```

### `analysis.schema.json: $.properties.aggregations.items.allOf[0].if.properties.operation`

```json
{
  "$ref": "#/properties/aggregations/items/properties/operation",
  "description": "Operation on the selected result rows. Mean and P95 response delay use successfully matched responses only."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Name assigned to this declaration and used by references."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.source`

```json
{
  "type": "object",
  "description": "Select exactly one calculation, sequence, rule or window from the current run.",
  "minProperties": 1,
  "maxProperties": 1,
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.source.properties.calculation`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Name of the scalar calculation whose rows are to be aggregated."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.source.properties.sequence`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Name of the declared sequence producing request and response outcomes."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.source.properties.rule`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Name of the declared rule that produces the events to count."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.source.properties.window`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Name of the declared window producing the segments to count."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.operation`

```json
{
  "enum": [
    "count",
    "sum",
    "mean",
    "variance",
    "quantile",
    "median"
  ],
  "description": "Operation on the selected result rows. Mean and P95 response delay use successfully matched responses only."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.field`

```json
{
  "enum": [
    "value",
    "delay_ns"
  ],
  "description": "Optional numeric field. Calculations default to value and sequences to delay_ns. Counts have no numeric field."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.group_by`

```json
{
  "type": "array",
  "uniqueItems": true,
  "description": "Group by these stable fields. Omitting group_by produces a single group for the selected source."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.group_by.items`

```json
{
  "enum": [
    "dataset_id",
    "entity_id",
    "session_id",
    "calculation_id",
    "parent_id",
    "sequence_id",
    "rule_id",
    "window_id"
  ],
  "description": "Grouping key available for this source. Use each key at most once."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Unit of the aggregate. Counts use 1; response latency can use ms or s."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.include_partial`

```json
{
  "type": "boolean",
  "description": "Include existing partial values. Including them does not make the aggregate complete."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.partial_policy`

```json
{
  "enum": [
    "report",
    "strict"
  ],
  "description": "For an incomplete population, report may return the known part; strict returns no value."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.q`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "description": "Quantile probability, required for quantile. Median uses 0.5 and does not accept q."
}
```

### `analysis.schema.json: $.properties.aggregations.items.properties.ddof`

```json
{
  "type": "integer",
  "enum": [
    0,
    1
  ],
  "description": "Degrees of freedom correction for variance; defaults to 0."
}
```

### `analysis.schema.json: $.properties.lookups`

```json
{
  "type": "array",
  "maxItems": 64,
  "description": "Version 4 one-dimensional calibration tables referenced by name in lookup. Input coordinates must strictly increase in their declared unit. Step interpolation retains the fixed-width output type."
}
```

### `analysis.schema.json: $.properties.lookups.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "points",
    "input_unit",
    "unit"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.lookups.items.properties.name`

```json
{
  "$ref": "#/properties/dataset/properties/name",
  "description": "Unique table name used by expressions."
}
```

### `analysis.schema.json: $.properties.lookups.items.properties.input_unit`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256,
  "description": "Calibration axis unit. Compatible query values are converted to this unit."
}
```

### `analysis.schema.json: $.properties.lookups.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256,
  "description": "Requested result unit; it must be compatible with the quantity."
}
```

### `analysis.schema.json: $.properties.lookups.items.properties.points`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 4096,
  "description": "Numeric [input, output] pairs in ascending input order. The loader checks finite coordinates, fixed-width integers and precision."
}
```

### `analysis.schema.json: $.properties.lookups.items.properties.points.items`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 2
}
```

### `analysis.schema.json: $.properties.lookups.items.properties.points.items.items`

```json
{
  "type": "number"
}
```

### `analysis.schema.json: $.properties.dataset`

```json
{
  "type": "object",
  "required": [
    "name"
  ],
  "description": "Object, session, and requested time range for this analysis. The requested range does not establish actual data coverage.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.dataset.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.dataset.properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.dataset.properties.entity`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Identifier of the object being analyzed, such as a device or experiment. It has no built-in vehicle meaning. Defaults to dataset.name."
}
```

### `analysis.schema.json: $.properties.dataset.properties.entity.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.dataset.properties.session`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Identifier of this shared analysis session. Signals analyzed together must have explicitly comparable time coordinates. Defaults to dataset.name; runtime state is isolated per task."
}
```

### `analysis.schema.json: $.properties.dataset.properties.session.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.dataset.properties.domain`

```json
{
  "type": "object",
  "required": [
    "start",
    "end"
  ],
  "description": "Requested half-open analysis range [start,end), including the start and excluding the end. Both ordinary analysis and message accumulation may omit it and use actual observations. When provided, both start and end are required; null and an empty object are not omission.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.dataset.properties.domain.properties.start`

```json
{
  "type": "string",
  "description": "Start of the analysis range: a relative time with a unit, or an absolute timestamp with an explicit timezone."
}
```

### `analysis.schema.json: $.properties.dataset.properties.domain.properties.start.anyOf[0]`

```json
{
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$"
}
```

### `analysis.schema.json: $.properties.dataset.properties.domain.properties.start.anyOf[1]`

```json
{
  "pattern": "^\\s*\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}"
}
```

### `analysis.schema.json: $.properties.dataset.properties.domain.properties.end`

```json
{
  "type": "string",
  "description": "Excluded end of the analysis range. It must use the same time coordinates as the start and must not precede it."
}
```

### `analysis.schema.json: $.properties.dataset.properties.domain.properties.end.anyOf[0]`

```json
{
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$"
}
```

### `analysis.schema.json: $.properties.dataset.properties.domain.properties.end.anyOf[1]`

```json
{
  "pattern": "^\\s*\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}"
}
```

### `analysis.schema.json: $.properties.dataset.properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.sources`

```json
{
  "type": "array",
  "minItems": 1,
  "description": "Sources in declaration order. Put consecutive files in one source's paths. Loading may enumerate filenames and read DBC metadata needed for omitted signal settings, but does not read business records."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "rows"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Source name within this plan. If omitted, names such as source_1 and source_2 are assigned by declaration order. References use this name; it does not infer source fields or synchronization."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time`

```json
{
  "description": "Source time type, unit, clock, and offset. time_type defaults to relative; an omitted clock creates an independent source origin. Set a shared clock only for sources with a known synchronization basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[0].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns"
  ],
  "description": "Unit of numeric values. Units are checked during expression evaluation and conversion and are not inferred from field or file names. Options: \"s\" seconds; \"ms\" milliseconds; \"us\" microseconds; \"ns\" nanoseconds."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"relative\", relative to an explicitly defined common origin."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Shared name for the relative time origin. Use the same value only when inputs actually share that origin. Omitting it does not synchronize inputs."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[1].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns",
    "ISO8601"
  ],
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Options: \"s\" seconds; \"ms\" milliseconds; \"us\" microseconds; \"ns\" nanoseconds; \"ISO8601\" timestamp text containing a date and timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Explicit timezone used when an absolute timestamp has no timezone of its own, for example UTC or an IANA name. The machine's default timezone is not used as configuration."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"absolute\", an absolute timestamp with a timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.rows`

```json
{
  "type": "array",
  "description": "Ordered in-memory records, each containing time and original-field values. Records are not automatically sorted to conceal out-of-order input."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.rows.items`

```json
{
  "type": "object",
  "required": [
    "time",
    "values"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.rows.items.properties.time`

```json
{
  "type": "string",
  "description": "Source time type, unit, clock, and offset. time_type defaults to relative; an omitted clock creates an independent source origin. Set a shared clock only for sources with a known synchronization basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.rows.items.properties.time.anyOf[0]`

```json
{
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.rows.items.properties.time.anyOf[1]`

```json
{
  "pattern": "^\\s*\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.rows.items.properties.values`

```json
{
  "type": "object",
  "description": "Mapping from original fields to native values for this in-memory record. Original field names may contain dots; expressions refer to aliases declared in signals."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.rows.items.properties.values.additionalProperties`

```json
{
  "type": [
    "number",
    "string",
    "boolean",
    "null"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[0].properties.source_type`

```json
{
  "const": "memory",
  "description": "Source type, which selects the reader and required fields. Constant: \"memory\", ordered records embedded in configuration."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "time",
    "time_column"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].oneOf[0]`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].oneOf[0].not`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].oneOf[1]`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].oneOf[1].not`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Source name within this plan. If omitted, names such as source_1 and source_2 are assigned by declaration order. References use this name; it does not infer source fields or synchronization."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time`

```json
{
  "description": "Source time type, unit, clock, and offset. time_type defaults to relative; an omitted clock creates an independent source origin. Set a shared clock only for sources with a known synchronization basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "unit"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[0].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns"
  ],
  "description": "Unit of numeric values. Units are checked during expression evaluation and conversion and are not inferred from field or file names. Options: \"s\" seconds; \"ms\" milliseconds; \"us\" microseconds; \"ns\" nanoseconds."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"relative\", relative to an explicitly defined common origin."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Shared name for the relative time origin. Use the same value only when inputs actually share that origin. Omitting it does not synchronize inputs."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type",
    "unit"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[1].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns",
    "ISO8601"
  ],
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Options: \"s\" seconds; \"ms\" milliseconds; \"us\" microseconds; \"ns\" nanoseconds; \"ISO8601\" timestamp text containing a date and timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Explicit timezone used when an absolute timestamp has no timezone of its own, for example UTC or an IANA name. The machine's default timezone is not used as configuration."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"absolute\", an absolute timestamp with a timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.time_column`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Time column in decoded-signal CSV, interpreted using the source time unit and coordinates."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.source_type`

```json
{
  "const": "signal_csv",
  "description": "Source type, which selects the reader and required fields. Constant: \"signal_csv\", decoded-signal CSV."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.reader`

```json
{
  "type": "object",
  "required": [],
  "description": "Reading, text parsing, and decoding options for this source format. Omitted applicable parameters use their documented defaults.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.reader.properties.encoding`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Text encoding used when reading; static validation does not establish that a file is readable. Decoded CSV defaults to utf-8-sig, accepting UTF-8 with or without a file-leading BOM. An explicit encoding takes precedence; U+FEFF inside the file is not removed.",
  "default": "utf-8-sig"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.reader.properties.delimiter`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 1,
  "pattern": "^[^\\r\\n]$",
  "description": "Single-character delimiter for decoded-signal CSV. Newline characters are not allowed.",
  "default": ","
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.reader.properties.missing_values`

```json
{
  "type": "array",
  "uniqueItems": true,
  "description": "Texts explicitly treated as missing values. Missing values are not automatically converted to zero.",
  "default": [
    ""
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[1].properties.reader.properties.missing_values.items`

```json
{
  "type": "string"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "dbc_by_channel"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].oneOf[0]`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].oneOf[0].not`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].oneOf[1]`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].oneOf[1].not`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Source name within this plan. If omitted, names such as source_1 and source_2 are assigned by declaration order. References use this name; it does not infer source fields or synchronization."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time`

```json
{
  "description": "Source time type, unit, clock, and offset. time_type defaults to relative; an omitted clock creates an independent source origin. Set a shared clock only for sources with a known synchronization basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[0].properties.unit`

```json
{
  "const": "s",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Constant: \"s\", seconds."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"relative\", relative to an explicitly defined common origin."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Shared name for the relative time origin. Use the same value only when inputs actually share that origin. Omitting it does not synchronize inputs."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[1].properties.unit`

```json
{
  "const": "s",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Constant: \"s\", seconds."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"absolute\", an absolute timestamp with a timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.legacy_profile`

```json
{
  "const": "sclicer-functions-v1",
  "description": "Existing BLF reader/decoder implementation. Optional; defaults to sclicer-functions-v1. If specified, only that integrated implementation is accepted."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.dbc_by_channel`

```json
{
  "type": "object",
  "minProperties": 1,
  "maxProperties": 1,
  "propertyNames": {
    "pattern": "^[1-9][0-9]*(?![\\s\\S])"
  },
  "description": "Explicit mapping from unique target channels to DBC files. Keys are positive integer strings starting at 1, without leading zeros. DBC paths are resolved relative to the declaring file."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.dbc_by_channel.additionalProperties`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.source_type`

```json
{
  "const": "can_blf",
  "description": "Source type, which selects the reader and required fields. Constant: \"can_blf\", raw CAN binary BLF."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.reader`

```json
{
  "type": "object",
  "required": [],
  "description": "Reading, text parsing, and decoding options for this source format. Omitted applicable parameters use their documented defaults.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.reader.properties.decode_policy`

```json
{
  "enum": [
    "strict",
    "partial",
    "legacy"
  ],
  "default": "strict",
  "description": "Payload-length policy for selected CAN messages; defaults to strict. strict requires the actual payload length to equal the DBC length and DLC to agree with the byte count. partial allows payloads shorter than the DBC length, but not longer payloads or DLC/byte-count inconsistencies; decoding still uses the existing implementation. legacy retains the original decode calls and length handling."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.reader.properties.decode_scope`

```json
{
  "type": "string",
  "enum": [
    "all",
    "requested"
  ],
  "default": "requested",
  "description": "Scope of attempted CAN decoding. The default requested decodes only messages/fields needed by this analysis; all broadens attempted decoding. In serial pure-BLF concatenation, strict/partial skip remote and error frames. all does not guarantee a DBC definition, successful decoding, or a per-frame diagnostic for every frame. Selecting all does not itself require dataset.domain. File multiprocessing and time_order support requested only."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.reader.properties.input_check`

```json
{
  "type": "string",
  "enum": [
    "auto",
    "full"
  ],
  "default": "auto",
  "description": "CAN input checks. auto selects checks required by actual consumers. full checks all raw frames and timestamps without forcing unrelated signal decoding. Options: \"auto\" and \"full\"."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[2].properties.file_merge`

```json
{
  "enum": [
    "concatenate",
    "time_order"
  ],
  "default": "concatenate",
  "description": "Controls how files in one source are combined. concatenate follows paths order and rejects time regressions only within the time-check scope required by the task. time_order requires each file to be ordered for the records being merged, then stably merges by timestamp, file position and local record sequence. Overlapping messages are retained; timestamps are not shifted and records are not deduplicated. This setting is independent of the process count."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "dbc_by_channel"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].oneOf[0]`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].oneOf[0].not`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].oneOf[1]`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].oneOf[1].not`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Source name within this plan. If omitted, names such as source_1 and source_2 are assigned by declaration order. References use this name; it does not infer source fields or synchronization."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time`

```json
{
  "description": "Source time type, unit, clock, and offset. time_type defaults to relative; an omitted clock creates an independent source origin. Set a shared clock only for sources with a known synchronization basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[0].properties.unit`

```json
{
  "const": "s",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Constant: \"s\", seconds."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"relative\", relative to an explicitly defined common origin."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Shared name for the relative time origin. Use the same value only when inputs actually share that origin. Omitting it does not synchronize inputs."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[1].properties.unit`

```json
{
  "const": "s",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Constant: \"s\", seconds."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"absolute\", an absolute timestamp with a timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "description": "Fixed acquisition timezone: UTC or a signed hour/minute offset such as +08:00."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.offsets`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Time offsets in input-file order. The number of offsets must match the file list; offsets must not silently reorder files."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.offsets.items`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed time offset: a number with s/ms/us/ns. Dates are not accepted."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.dbc_by_channel`

```json
{
  "type": "object",
  "minProperties": 1,
  "maxProperties": 1,
  "description": "Explicit mapping from unique target channels to DBC files. Keys are positive integer strings starting at 1, without leading zeros. DBC paths are resolved relative to the declaring file.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.dbc_by_channel.patternProperties.^[1-9][0-9]*(?![\s\S])`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.source_type`

```json
{
  "const": "can_asc",
  "description": "Source type, which selects the reader and required fields. Constant: \"can_asc\", raw CAN text ASC."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.reader`

```json
{
  "type": "object",
  "required": [],
  "description": "Reading, text parsing, and decoding options for this source format. Omitted applicable parameters use their documented defaults.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.reader.properties.version`

```json
{
  "enum": [
    "vector-asc-v1",
    "vector-asc-statistics-v1",
    "sclicer-asc-v1"
  ],
  "description": "Select the ASC row layout. Default vector-asc-v1 reads standard Vector ASC with an optional Length/BitCount/ID suffix, retaining strict field-order, value and ID checks. vector-asc-statistics-v1 remains an explicit standard-statistics selection; sclicer-asc-v1 selects the different Sclicer FD layout. Dialects are not guessed."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.reader.properties.encoding`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Input text encoding used during reading. Static checks do not prove that the file can be read. CAN text parsing defaults to utf-8-sig.",
  "default": "utf-8-sig"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.reader.properties.decode_policy`

```json
{
  "enum": [
    "strict",
    "partial",
    "legacy"
  ],
  "default": "strict",
  "description": "Payload-length policy for selected CAN messages; defaults to strict. strict requires the actual payload length to equal the DBC length and DLC to agree with the byte count. partial allows payloads shorter than the DBC length, but not longer payloads or DLC/byte-count inconsistencies; decoding still uses the existing implementation. legacy retains the original decode calls and length handling."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.reader.properties.input_check`

```json
{
  "type": "string",
  "enum": [
    "auto",
    "full"
  ],
  "default": "auto",
  "description": "auto checks time order according to actual consumers. Ordinary ASC analysis checks only required channels/IDs, while the source range uses the earliest/latest timestamps from all records read in the same pass. full and raw-frame export check all records. No mode automatically sorts records or changes timestamps."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[3].properties.file_merge`

```json
{
  "enum": [
    "concatenate",
    "time_order"
  ],
  "default": "concatenate",
  "description": "Controls how files in one source are combined. concatenate follows paths order and rejects time regressions only within the time-check scope required by the task. time_order requires each file to be ordered for the records being merged, then stably merges by timestamp, file position and local record sequence. Overlapping messages are retained; timestamps are not shifted and records are not deduplicated. This setting is independent of the process count."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "time",
    "dbc_by_channel",
    "reader"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].oneOf[0]`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].oneOf[0].not`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].oneOf[1]`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].oneOf[1].not`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Source name within this plan. If omitted, names such as source_1 and source_2 are assigned by declaration order. References use this name; it does not infer source fields or synchronization."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time`

```json
{
  "description": "Source time type, unit, clock, and offset. time_type defaults to relative; an omitted clock creates an independent source origin. Set a shared clock only for sources with a known synchronization basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "unit"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[0].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns",
    "ISO8601"
  ],
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Options: \"s\" seconds; \"ms\" milliseconds; \"us\" microseconds; \"ns\" nanoseconds; \"ISO8601\" timestamp text containing a date and timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"relative\", relative to an explicitly defined common origin."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Shared name for the relative time origin. Use the same value only when inputs actually share that origin. Omitting it does not synchronize inputs."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type",
    "unit"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[1].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns",
    "ISO8601"
  ],
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Options: \"s\" seconds; \"ms\" milliseconds; \"us\" microseconds; \"ns\" nanoseconds; \"ISO8601\" timestamp text containing a date and timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"absolute\", an absolute timestamp with a timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "description": "Fixed acquisition timezone: UTC or a signed hour/minute offset such as +08:00."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.offsets`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Time offsets in input-file order. The number of offsets must match the file list; offsets must not silently reorder files."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.offsets.items`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed time offset: a number with s/ms/us/ns. Dates are not accepted."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.dbc_by_channel`

```json
{
  "type": "object",
  "minProperties": 1,
  "maxProperties": 1,
  "description": "Explicit mapping from unique target channels to DBC files. Keys are positive integer strings starting at 1, without leading zeros. DBC paths are resolved relative to the declaring file.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.dbc_by_channel.patternProperties.^[1-9][0-9]*(?![\s\S])`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.source_type`

```json
{
  "const": "raw_can_csv",
  "description": "Source type, which selects the reader and required fields. Constant: \"raw_can_csv\", raw CAN frame CSV with an explicit layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader`

```json
{
  "type": "object",
  "required": [
    "layout",
    "time_format"
  ],
  "description": "Reading, text parsing, and decoding options for this source format. Omitted applicable parameters use their documented defaults.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout`

```json
{
  "type": "object",
  "required": [
    "fields"
  ],
  "description": "Raw CAN CSV field layout, explicitly describing the delimiter, column/constant mappings, time representation, and numeric formats.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields`

```json
{
  "type": "object",
  "required": [
    "timestamp",
    "frame_id",
    "data"
  ],
  "description": "Explicit mapping from raw CAN semantic fields to input columns or constants.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp`

```json
{
  "description": "Column or constant for message timestamps, converted using time_format and the source time declaration. A column name or one-based column number may be written directly; constants still use a fixed object."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Column or constant for message timestamps, converted using time_format and the source time declaration.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id`

```json
{
  "description": "Column or constant for the CAN arbitration ID, interpreted using id_base. A column name or one-based column number may be written directly; constants still use a fixed object."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Column or constant for the CAN arbitration ID, interpreted using id_base.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel`

```json
{
  "description": "Channel mapping for raw CSV. Constants retain the file's numbering; channel_origin specifies whether the file starts at 0 or 1. A column name or one-based column number may be written directly; constants still use a fixed object. If omitted, inherits the source's unique DBC channel."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Channel mapping for raw CSV. Constants retain the file's numbering; channel_origin specifies whether the file starts at 0 or 1.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx`

```json
{
  "description": "Input mapping for receive/transmit direction. Values must unambiguously identify the direction. A column name or one-based column number may be written directly; constants still use a fixed object. Optional: omission means unknown direction, which must be supplied only for raw-frame export or reconstruction. Rx/Tx and 接收/发送 are recognized directly."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Input mapping for receive/transmit direction. Values must unambiguously identify the direction.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended`

```json
{
  "description": "Optional column or constant for standard/extended frame type. An actual input field takes precedence. If omitted, bindings and DBC must identify it uniquely; otherwise supply it. A small ID alone does not prove a standard frame. A column name or one-based column number may be written directly; constants still use a fixed object."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Optional column or constant for standard/extended frame type. An actual input field takes precedence. If omitted, bindings and DBC must identify it uniquely; otherwise supply it. A small ID alone does not prove a standard frame.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd`

```json
{
  "description": "Optional CAN/FD column or constant. An actual field takes precedence; otherwise use bindings and DBC. A DBC marked FD may describe actual classic CAN. Supply the type if ambiguous; do not infer it from a short payload. A column name or one-based column number may be written directly; constants still use a fixed object."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Optional CAN/FD column or constant. An actual field takes precedence; otherwise use bindings and DBC. A DBC marked FD may describe actual classic CAN. Supply the type if ambiguous; do not infer it from a short payload.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind`

```json
{
  "description": "Input mapping for CAN frame kind, distinguishing supported data, remote, or error frames. A column name or one-based column number may be written directly; constants still use a fixed object. Defaults to ordinary data frames; remote or error frames must be explicit."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Input mapping for CAN frame kind, distinguishing supported data, remote, or error frames.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data`

```json
{
  "description": "Input mapping for CAN payload bytes, parsed using payload_style. Missing payloads are not filled with zeros. A column name or one-based column number may be written directly; constants still use a fixed object."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Input mapping for CAN payload bytes, parsed using payload_style. Missing payloads are not filled with zeros.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length`

```json
{
  "description": "Input mapping for the actual payload byte count, handled separately from the DLC code. A column name or one-based column number may be written directly; constants still use a fixed object. If omitted, inferred from the data byte count."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Input mapping for the actual payload byte count, handled separately from the DLC code.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code`

```json
{
  "description": "Input mapping for the CAN DLC code. A CAN FD DLC code is not the same as the byte count. A column name or one-based column number may be written directly; constants still use a fixed object."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Input mapping for the CAN DLC code. A CAN FD DLC code is not the same as the byte count.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch`

```json
{
  "description": "Input mapping for the CAN FD bitrate-switch flag. A column name or one-based column number may be written directly; constants still use a fixed object."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Input mapping for the CAN FD bitrate-switch flag.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator`

```json
{
  "description": "Input mapping for the CAN FD error-state indicator. A column name or one-based column number may be written directly; constants still use a fixed object."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "description": "Input mapping for the CAN FD error-state indicator.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].oneOf[0].not`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].oneOf[1].not`

```json
{
  "required": [
    "column"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.column`

```json
{
  "description": "Column name or index to read, mutually exclusive with fixed. It must agree with has_header and the actual layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.fixed`

```json
{
  "description": "Explicit constant for this semantic field, mutually exclusive with column. It is not an automatic replacement for missing data."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "Whether to remove whitespace at both ends of an input field. Interior characters are unchanged."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "maxProperties": 256,
  "description": "Omit or use null for no mapping. An object must contain 1 to 256 entries, with original text keys and string targets each at most 256 characters. These limits differ from fixed text limits.",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.value_map.additionalProperties.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.value_map.additionalProperties.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.value_map.additionalProperties.oneOf[2]`

```json
{
  "type": "boolean"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.encoding`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Input text encoding used during reading. Static checks do not prove that the file can be read. CAN text parsing defaults to utf-8-sig."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.delimiter`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 1,
  "description": "Delimiter for raw CAN CSV; it must match the file format."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.has_header`

```json
{
  "type": "boolean",
  "description": "Whether raw CSV has a header row. Column names require a header; indices use the explicitly declared layout."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.skip_rows`

```json
{
  "type": "integer",
  "minimum": 0,
  "description": "Non-negative number of lines to skip before reading records, for existing introductory lines in the file."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.layout_version`

```json
{
  "const": "raw-can-csv-layout-v1",
  "description": "Fixed version identifier for the raw CAN CSV field layout. Constant: \"raw-can-csv-layout-v1\"."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.time_format`

```json
{
  "enum": [
    "numeric",
    "clock",
    "clock-ms-us-v1",
    "iso8601"
  ],
  "description": "Text representation of raw CAN timestamps; it must match the file. Options: \"numeric\", numbers in the source time unit; \"clock\", hour/minute/second text; \"clock-ms-us-v1\", legacy clock/millisecond/microsecond text; \"iso8601\", ISO 8601 date and time."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.id_base`

```json
{
  "enum": [
    "auto",
    10,
    16
  ],
  "description": "Defaults to auto: 0x means hexadecimal, 0b means binary, and no prefix means decimal. Select 16 explicitly for unprefixed hexadecimal tables."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.length_base`

```json
{
  "enum": [
    10,
    16
  ],
  "description": "Base of message-length text, either 10 or 16. Declare the presence of DLC codes separately. Options: 10 decimal; 16 hexadecimal."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.channel_origin`

```json
{
  "enum": [
    0,
    1
  ],
  "description": "Starting channel number in the original file: 0 or 1. Channels are normalized to zero-based internal numbering. Options: 0, file numbering starts at channel 0; 1, file numbering starts at channel 1."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.payload_style`

```json
{
  "enum": [
    "spaced",
    "contiguous"
  ],
  "description": "Payload text arrangement. Options: \"spaced\", bytes separated by spaces; \"contiguous\", continuous hexadecimal byte text."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.rollover_min_drop`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Minimum timestamp decrease that may be recognized as a day rollover, including a unit. Arbitrary out-of-order records must not be treated as a rollover."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.decode_policy`

```json
{
  "enum": [
    "strict",
    "partial",
    "legacy"
  ],
  "default": "strict",
  "description": "Payload-length policy for selected CAN messages; defaults to strict. strict requires the actual payload length to equal the DBC length and DLC to agree with the byte count. partial allows payloads shorter than the DBC length, but not longer payloads or DLC/byte-count inconsistencies; decoding still uses the existing implementation. legacy retains the original decode calls and length handling."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[4].properties.reader.properties.input_check`

```json
{
  "type": "string",
  "enum": [
    "auto",
    "full"
  ],
  "default": "auto",
  "description": "auto checks time order according to actual consumers. Ordinary ASC analysis checks only required channels/IDs, while the source range uses the earliest/latest timestamps from all records read in the same pass. full and raw-frame export check all records. No mode automatically sorts records or changes timestamps."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5]`

```json
{
  "type": "object",
  "required": [
    "dbc_by_channel"
  ],
  "description": "Automatically choose ASC or BLF reading. Format-specific options are checked against the actual source.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].oneOf[0]`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].oneOf[0].not`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].oneOf[1]`

```json
{
  "required": [
    "paths"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].oneOf[1].not`

```json
{
  "required": [
    "path"
  ]
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Source name within this plan. If omitted, names such as source_1 and source_2 are assigned by declaration order. References use this name; it does not infer source fields or synchronization."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time`

```json
{
  "description": "Source time type, unit, clock, and offset. time_type defaults to relative; an omitted clock creates an independent source origin. Set a shared clock only for sources with a known synchronization basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[0].properties.unit`

```json
{
  "const": "s",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Constant: \"s\", seconds."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"relative\", relative to an explicitly defined common origin."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Shared name for the relative time origin. Use the same value only when inputs actually share that origin. Omitting it does not synchronize inputs."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[1].properties.unit`

```json
{
  "const": "s",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names. Constant: \"s\", seconds."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed offset added to source timestamps. Positive or negative values require s/ms/us/ns; this is not a timezone or date.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "Time coordinates: relative to a shared origin, or absolute with a timezone. Constant: \"absolute\", an absolute timestamp with a timezone basis."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "description": "Fixed acquisition timezone: UTC or a signed hour/minute offset such as +08:00."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.legacy_profile`

```json
{
  "const": "sclicer-functions-v1",
  "description": "Existing BLF reader/decoder implementation. Optional; defaults to sclicer-functions-v1. If specified, only that integrated implementation is accepted."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths`

```json
{
  "description": "Input file, directory, or wildcard, as one item or a list. path and paths are mutually exclusive."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.dbc_by_channel`

```json
{
  "type": "object",
  "minProperties": 1,
  "maxProperties": 1,
  "propertyNames": {
    "pattern": "^[1-9][0-9]*(?![\\s\\S])"
  },
  "description": "Explicit mapping from unique target channels to DBC files. Keys are positive integer strings starting at 1, without leading zeros. DBC paths are resolved relative to the declaring file."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.dbc_by_channel.additionalProperties`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.source_type`

```json
{
  "enum": [
    "asc_or_blf"
  ],
  "description": "If omitted, identify ASC/BLF by extension; both may be mixed in one source in their original order. CSV and memory inputs require an explicit type."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.offsets`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Time offsets in input-file order. The number of offsets must match the file list; offsets must not silently reorder files."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.offsets.items`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed time offset: a number with s/ms/us/ns. Dates are not accepted."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.reader`

```json
{
  "type": "object",
  "required": [],
  "description": "Reading, text parsing, and decoding options for this source format. Omitted applicable parameters use their documented defaults.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.reader.properties.version`

```json
{
  "enum": [
    "vector-asc-v1",
    "vector-asc-statistics-v1",
    "sclicer-asc-v1"
  ],
  "description": "Select the ASC row layout. Default vector-asc-v1 reads standard Vector ASC with an optional Length/BitCount/ID suffix, retaining strict field-order, value and ID checks. vector-asc-statistics-v1 remains an explicit standard-statistics selection; sclicer-asc-v1 selects the different Sclicer FD layout. Dialects are not guessed."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.reader.properties.encoding`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Input text encoding used during reading. Static checks do not prove that the file can be read. CAN text parsing defaults to utf-8-sig.",
  "default": "utf-8-sig"
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.reader.properties.decode_policy`

```json
{
  "enum": [
    "strict",
    "partial",
    "legacy"
  ],
  "default": "strict",
  "description": "Payload-length policy for selected CAN messages; defaults to strict. strict requires the actual payload length to equal the DBC length and DLC to agree with the byte count. partial allows payloads shorter than the DBC length, but not longer payloads or DLC/byte-count inconsistencies; decoding still uses the existing implementation. legacy retains the original decode calls and length handling."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.reader.properties.decode_scope`

```json
{
  "type": "string",
  "enum": [
    "all",
    "requested"
  ],
  "default": "requested",
  "description": "Scope of attempted CAN decoding. The default requested decodes only messages/fields needed by this analysis; all broadens attempted decoding. In serial pure-BLF concatenation, strict/partial skip remote and error frames. all does not guarantee a DBC definition, successful decoding, or a per-frame diagnostic for every frame. Selecting all does not itself require dataset.domain. File multiprocessing and time_order support requested only."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.reader.properties.input_check`

```json
{
  "type": "string",
  "enum": [
    "auto",
    "full"
  ],
  "default": "auto",
  "description": "auto checks time order according to actual consumers. Ordinary ASC analysis checks only required channels/IDs, while the source range uses the earliest/latest timestamps from all records read in the same pass. full and raw-frame export check all records. No mode automatically sorts records or changes timestamps."
}
```

### `analysis.schema.json: $.properties.sources.items.oneOf[5].properties.file_merge`

```json
{
  "enum": [
    "concatenate",
    "time_order"
  ],
  "default": "concatenate",
  "description": "Controls how files in one source are combined. concatenate follows paths order and rejects time regressions only within the time-check scope required by the task. time_order requires each file to be ordered for the records being merged, then stably merges by timestamp, file position and local record sequence. Overlapping messages are retained; timestamps are not shifted and records are not deduplicated. This setting is independent of the process count."
}
```

### `analysis.schema.json: $.properties.signals`

```json
{
  "type": "array",
  "description": "Bind original source fields to simple analysis signal names, specifying type, unit, and validity duration."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "name",
    "field"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[0].then.allOf[0].then`

```json
{
  "required": [
    "choices"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[0].then.allOf[0].if`

```json
{
  "required": [
    "field"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[0].then.allOf[0].if.properties.field`

```json
{
  "type": "string",
  "description": "Decoded signal column names do not provide DBC type or unit metadata, so configuration must declare them."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[0].then.properties.choices`

```json
{
  "minItems": 1,
  "description": "Enum pairs [original_code,label]. Preserve the code's native type; do not stringify integer or Boolean codes through object keys."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[0].if`

```json
{
  "required": [
    "dtype"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[0].if.properties.dtype`

```json
{
  "const": "enum",
  "description": "Explicit enum signals use text labels. CAN may obtain choices from the DBC; decoded inputs require choices."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[1].then`

```json
{
  "required": [
    "dtype",
    "unit"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[1].if`

```json
{
  "required": [
    "field"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].allOf[1].if.properties.field`

```json
{
  "type": "string",
  "description": "Decoded signal column names do not provide DBC type or unit metadata, so configuration must declare them."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Simple name of this source or signal, used by subsequent references. It does not infer or rename the original data field."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.source`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "name of a declared source. The reference must exist; sources are not inferred from matching field or semantic names."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.source.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field`

```json
{
  "description": "Actual field in the source: an original field name for signal tables/memory, or a CAN channel/message/signal locator object."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S"
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "signal",
    "frame_id"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].allOf[0].then.properties.frame_id`

```json
{
  "maximum": 2047,
  "description": "Integer message IDs for standard frames are limited to 2047. The plan loader checks the range after converting string IDs."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].allOf[0].if`

```json
{
  "required": [
    "is_extended"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].allOf[0].if.properties.is_extended`

```json
{
  "const": false,
  "description": "When standard frame format is explicitly selected, an integer ID must fit in 11 bits."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "CAN channels in user configuration start at 1; 1 maps to internal channel 0. If omitted, inherits the source's unique channel."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.signal`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name in the DBC, used with frame_id to locate a signal within that message. This is not the analysis alias."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.frame_id`

```json
{
  "description": "CAN message ID, as an integer or string. 0x is hexadecimal, 0b binary, and no prefix decimal. The parsed value must be 0 to 536870911; an explicitly standard frame is limited to 2047."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.is_extended`

```json
{
  "type": "boolean",
  "description": "Optional standard/extended frame constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.is_fd`

```json
{
  "type": "boolean",
  "description": "Optional CAN/CAN FD constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.dtype`

```json
{
  "enum": [
    "int64",
    "uint64",
    "float64",
    "bool",
    "enum"
  ],
  "description": "Analysis signal type: int64, uint64, float64, bool, or enum. For CAN, omission infers a numeric type from DBC-decoded values; a DBC choice table alone does not select enum. Explicit manual choices with text or Boolean labels can establish enum or bool. Decoded inputs still require dtype."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Unit of numeric values, checked for expressions and conversion rather than inferred from field or file names. For CAN, omission reads the DBC unit; a missing DBC unit becomes unknown and unverified, while logical types use 1. Decoded inputs still require an explicit unit."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.valid_for`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Maximum actual duration for reusing a valid sample. Optional; defaults to three times this signal's period, using an explicit period before the DBC message cycle. If neither is available, supply period or valid_for. An explicit valid_for overrides the default.",
  "examples": [
    "500ms",
    "2s"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.sample_policy`

```json
{
  "const": "backward_hold",
  "description": "Sample reuse policy. Currently only backward_hold is supported: use the most recent valid sample within its validity duration. Constant: \"backward_hold\".",
  "default": "backward_hold"
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.same_time_policy`

```json
{
  "enum": [
    "error",
    "last_by_sequence"
  ],
  "description": "Handling of multiple updates for one signal at the same timestamp. Conflicts are not ignored and records are not arbitrarily reordered. Options: \"error\", fail on conflicting same-time updates; \"last_by_sequence\", use the last update in original order.",
  "default": "error"
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.code_dtype`

```json
{
  "enum": [
    "int64",
    "uint64"
  ],
  "description": "Original integer type of a version 4 enum, used by enum_code. The DBC can supply it for unscaled integer CAN signals."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.choices`

```json
{
  "type": "array",
  "description": "Enum pairs [original_code,label]. Keep the native code type; object keys would turn integer or Boolean codes into strings. With dtype=enum, omission reads DBC choices; an explicit mapping takes precedence. Floating-point enum codes produced by scaling are rejected, not truncated to integers."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.choices.items`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 2,
  "items": false
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.choices.items.prefixItems[0]`

```json
{
  "type": [
    "integer",
    "boolean",
    "string"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.choices.items.prefixItems[1]`

```json
{
  "type": [
    "string",
    "boolean"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.valid_range`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 2,
  "description": "Allowed normalized numeric range, from lower to upper bound. Values outside the range follow the quality policy and are not clipped to the boundary."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.valid_range.items`

```json
{
  "type": "number"
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.invalid_values`

```json
{
  "type": "array",
  "description": "Original codes explicitly marked invalid. An invalid update replaces the previous value; it is not treated as no update.",
  "default": []
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.invalid_values.items`

```json
{
  "type": [
    "number",
    "string",
    "boolean",
    "null"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.semantic_id`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Optional business-meaning identifier for documentation or role contracts. A matching identifier does not bind signals automatically. May be omitted or null; otherwise must be non-empty text."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.semantic_contract_version`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Version of the business meaning identified by this signal's semantic_id, independent of the analysis configuration version. It does not establish that actual inputs were verified. May be omitted or null; every non-null value must be non-empty text and requires semantic_id on the same signal."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.mapping_version`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Version identifier for the caller's signal mapping, identifying the explicit bindings used. May be omitted or null; otherwise must be non-empty text."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.sign_convention`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Explicit meaning of positive/negative normalized values, such as positive for inflow. Signals from different locations or directions must not be merged by name alone. May be omitted or null; otherwise must be non-empty text."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.measurement_location`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Signal measurement location for checking business role contracts. May be omitted or null; otherwise must be non-empty text."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.period`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed period of this signal: a positive duration with a unit, such as 100ms. An explicit period takes precedence over the DBC message cycle; omitted valid_for is three times the period.",
  "examples": [
    "100ms",
    "0.1s"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.conversion`

```json
{
  "type": "object",
  "description": "Additional unit conversion. If both coefficients are omitted, infer conversion from input and target units. Supplying either coefficient selects a complete explicit conversion; DBC scaling is not repeated.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.conversion.properties.input_unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Unit after reading or DBC decoding. Raw CAN inputs infer it from the DBC; decoded CSV and memory inputs use the target unit when omitted. Explicit null is invalid; omit the field instead."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.conversion.properties.scale`

```json
{
  "type": "number",
  "description": "Multiplier. Inferred if both coefficients are omitted; defaults to 1 only when offset is explicitly supplied. Explicit coefficients must match the units."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[0].properties.conversion.properties.offset`

```json
{
  "type": "number",
  "description": "Offset after multiplication, expressed in the target unit. Inferred if both coefficients are omitted; defaults to 0 only when scale is explicitly supplied."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "frame_id",
    "signals"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].allOf[0].then.properties.frame_id`

```json
{
  "maximum": 2047,
  "description": "Integer message IDs for standard frames are limited to 2047. The plan loader checks the range after converting string IDs."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].allOf[0].if`

```json
{
  "required": [
    "is_extended"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].allOf[0].if.properties.is_extended`

```json
{
  "const": false,
  "description": "When standard frame format is explicitly selected, an integer ID must fit in 11 bits."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.frame_id`

```json
{
  "description": "CAN message ID, as an integer or string. 0x is hexadecimal, 0b binary, and no prefix decimal. The parsed value must be 0 to 536870911; an explicitly standard frame is limited to 2047."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "CAN channels in user configuration start at 1; 1 maps to internal channel 0. If omitted, inherits the source's unique channel."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.is_extended`

```json
{
  "type": "boolean",
  "description": "Optional standard/extended frame constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.is_fd`

```json
{
  "type": "boolean",
  "description": "Optional CAN/CAN FD constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.source`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "name of a declared source. The reference must exist; sources are not inferred from matching field or semantic names."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.source.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.period`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed period of this signal: a positive duration with a unit, such as 100ms. An explicit period takes precedence over the DBC message cycle; omitted valid_for is three times the period.",
  "examples": [
    "100ms",
    "0.1s"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.valid_for`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Maximum actual duration for reusing a valid sample. Optional; defaults to three times this signal's period, using an explicit period before the DBC message cycle. If neither is available, supply period or valid_for. An explicit valid_for overrides the default.",
  "examples": [
    "500ms",
    "2s"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.same_time_policy`

```json
{
  "enum": [
    "error",
    "last_by_sequence"
  ],
  "description": "Handling of multiple updates for one signal at the same timestamp. Conflicts are not ignored and records are not arbitrarily reordered. Options: \"error\", fail on conflicting same-time updates; \"last_by_sequence\", use the last update in original order.",
  "default": "error"
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals`

```json
{
  "type": "array",
  "minItems": 1,
  "description": "Signals in the same message. Supply each signal name and any required per-signal overrides."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "signal"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[0].then.allOf[0].then`

```json
{
  "required": [
    "choices"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[0].then.allOf[0].if`

```json
{
  "required": [
    "field"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[0].then.allOf[0].if.properties.field`

```json
{
  "type": "string",
  "description": "Decoded signal column names do not provide DBC type or unit metadata, so configuration must declare them."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[0].then.properties.choices`

```json
{
  "minItems": 1,
  "description": "Enum pairs [original_code,label]. Preserve the code's native type; do not stringify integer or Boolean codes through object keys."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[0].if`

```json
{
  "required": [
    "dtype"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[0].if.properties.dtype`

```json
{
  "const": "enum",
  "description": "Explicit enum signals use text labels. CAN may obtain choices from the DBC; decoded inputs require choices."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[1].then`

```json
{
  "required": [
    "dtype",
    "unit"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[1].if`

```json
{
  "required": [
    "field"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.allOf[1].if.properties.field`

```json
{
  "type": "string",
  "description": "Decoded signal column names do not provide DBC type or unit metadata, so configuration must declare them."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Simple name of this source or signal, used by subsequent references. It does not infer or rename the original data field."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.dtype`

```json
{
  "enum": [
    "int64",
    "uint64",
    "float64",
    "bool",
    "enum"
  ],
  "description": "Analysis signal type: int64, uint64, float64, bool, or enum. For CAN, omission infers a numeric type from DBC-decoded values; a DBC choice table alone does not select enum. Explicit manual choices with text or Boolean labels can establish enum or bool. Decoded inputs still require dtype."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Unit of numeric values, checked for expressions and conversion rather than inferred from field or file names. For CAN, omission reads the DBC unit; a missing DBC unit becomes unknown and unverified, while logical types use 1. Decoded inputs still require an explicit unit."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.valid_for`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Maximum actual duration for reusing a valid sample. Optional; defaults to three times this signal's period, using an explicit period before the DBC message cycle. If neither is available, supply period or valid_for. An explicit valid_for overrides the default.",
  "examples": [
    "500ms",
    "2s"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.sample_policy`

```json
{
  "const": "backward_hold",
  "description": "Sample reuse policy. Currently only backward_hold is supported: use the most recent valid sample within its validity duration. Constant: \"backward_hold\".",
  "default": "backward_hold"
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.same_time_policy`

```json
{
  "enum": [
    "error",
    "last_by_sequence"
  ],
  "description": "Handling of multiple updates for one signal at the same timestamp. Conflicts are not ignored and records are not arbitrarily reordered. Options: \"error\", fail on conflicting same-time updates; \"last_by_sequence\", use the last update in original order.",
  "default": "error"
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.code_dtype`

```json
{
  "enum": [
    "int64",
    "uint64"
  ],
  "description": "Integer type before enum labels are applied in version 4. Only enum_code requests original codes."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.choices`

```json
{
  "type": "array",
  "description": "Enum pairs [original_code,label]. Keep the native code type; object keys would turn integer or Boolean codes into strings. With dtype=enum, omission reads DBC choices; an explicit mapping takes precedence. Floating-point enum codes produced by scaling are rejected, not truncated to integers."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.choices.items`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 2,
  "items": false
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.choices.items.prefixItems[0]`

```json
{
  "type": [
    "integer",
    "boolean",
    "string"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.choices.items.prefixItems[1]`

```json
{
  "type": [
    "string",
    "boolean"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.valid_range`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 2,
  "description": "Allowed normalized numeric range, from lower to upper bound. Values outside the range follow the quality policy and are not clipped to the boundary."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.valid_range.items`

```json
{
  "type": "number"
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.invalid_values`

```json
{
  "type": "array",
  "description": "Original codes explicitly marked invalid. An invalid update replaces the previous value; it is not treated as no update.",
  "default": []
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.invalid_values.items`

```json
{
  "type": [
    "number",
    "string",
    "boolean",
    "null"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.semantic_id`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Optional business-meaning identifier for documentation or role contracts. A matching identifier does not bind signals automatically. May be omitted or null; otherwise must be non-empty text."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.semantic_contract_version`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Version of the business meaning identified by this signal's semantic_id, independent of the analysis configuration version. It does not establish that actual inputs were verified. May be omitted or null; every non-null value must be non-empty text and requires semantic_id on the same signal."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.mapping_version`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Version identifier for the caller's signal mapping, identifying the explicit bindings used. May be omitted or null; otherwise must be non-empty text."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.sign_convention`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Explicit meaning of positive/negative normalized values, such as positive for inflow. Signals from different locations or directions must not be merged by name alone. May be omitted or null; otherwise must be non-empty text."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.measurement_location`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "Signal measurement location for checking business role contracts. May be omitted or null; otherwise must be non-empty text."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.period`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed period of this signal: a positive duration with a unit, such as 100ms. An explicit period takes precedence over the DBC message cycle; omitted valid_for is three times the period.",
  "examples": [
    "100ms",
    "0.1s"
  ]
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.signal`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Bound signal name for a calculation input, or original DBC signal name inside a CAN locator. These contexts are checked separately."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.conversion`

```json
{
  "type": "object",
  "description": "Additional unit conversion. If both coefficients are omitted, infer conversion from input and target units. Supplying either coefficient selects a complete explicit conversion; DBC scaling is not repeated.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.conversion.properties.input_unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Unit after reading or DBC decoding. Raw CAN inputs infer it from the DBC; decoded CSV and memory inputs use the target unit when omitted. Explicit null is invalid; omit the field instead."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.conversion.properties.scale`

```json
{
  "type": "number",
  "description": "Multiplier. Inferred if both coefficients are omitted; defaults to 1 only when offset is explicitly supplied. Explicit coefficients must match the units."
}
```

### `analysis.schema.json: $.properties.signals.items.oneOf[1].properties.signals.items.properties.conversion.properties.offset`

```json
{
  "type": "number",
  "description": "Offset after multiplication, expressed in the target unit. Inferred if both coefficients are omitted; defaults to 0 only when scale is explicitly supplied."
}
```

### `analysis.schema.json: $.properties.derived`

```json
{
  "type": "object",
  "propertyNames": {
    "type": "string",
    "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
    "not": {
      "enum": [
        "abs",
        "isclose",
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield"
      ],
      "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
    }
  },
  "description": "Mapping from derived signal names to expression declarations. Only bound signals and restricted expressions are used; units and dependency cycles are checked.",
  "default": {}
}
```

### `analysis.schema.json: $.properties.derived.additionalProperties`

```json
{
  "type": "object",
  "required": [
    "expr"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.derived.additionalProperties.properties.expr`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Restricted expression using explicitly bound names and supported operations. It does not execute Python, attribute access, or arbitrary functions."
}
```

### `analysis.schema.json: $.properties.derived.additionalProperties.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Optional result unit. If omitted, infer it from supported unit relationships in the expression; fail explicitly if it cannot be determined."
}
```

### `analysis.schema.json: $.properties.derived.additionalProperties.properties.semantic_id`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Optional business-meaning identifier for documentation or role contracts. Matching identifiers do not bind signals automatically."
}
```

### `analysis.schema.json: $.properties.derived.additionalProperties.properties.semantic_contract_version`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Version of this semantic contract, independent of the analysis configuration version. It does not establish that actual inputs were verified."
}
```

### `analysis.schema.json: $.properties.derived.additionalProperties.properties.sign_convention`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Explicit meaning of positive/negative normalized values, such as positive for inflow. Signals from different locations or directions must not be merged by name alone."
}
```

### `analysis.schema.json: $.properties.derived.additionalProperties.properties.measurement_location`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Signal measurement location for checking business role contracts."
}
```

### `analysis.schema.json: $.properties.derived.additionalProperties.properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.rules`

```json
{
  "type": "array",
  "description": "Rules that identify events. Rule names share a unique namespace with windows, calculations, and sequences.",
  "default": []
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition",
    "minimum_duration",
    "duration_comparison"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Boolean condition expression. Unknown values use three-valued logic; nonzero numeric values are not implicitly true."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.selection_origin`

```json
{
  "enum": [
    "onset",
    "confirmed"
  ],
  "description": "Start of statistics for a duration-qualified event. Options: \"onset\", when the condition first becomes true; \"confirmed\", when the duration requirement is confirmed.",
  "default": "onset"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.rule_type`

```json
{
  "const": "condition_duration",
  "description": "Event-rule type, determining the meanings of conditions, durations, thresholds, and other fields. Constant: \"condition_duration\", confirming an activity once the condition remains true for the required duration."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.minimum_duration`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Minimum continuous duration required to confirm a condition, including a unit. This is not sample validity or a maximum waiting time.",
  "examples": [
    "0s",
    "500ms"
  ]
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.duration_comparison`

```json
{
  "type": "string",
  "enum": [
    ">=",
    ">"
  ],
  "description": "Required comparison between the continuous duration and minimum_duration: >= includes the threshold; > requires strictly longer. Exactly 60 seconds satisfies only >=. The activity start is unchanged; selection_origin still defaults to onset."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[0].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Boolean condition expression. Unknown values use three-valued logic; nonzero numeric values are not implicitly true."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.emit_initial`

```json
{
  "type": "boolean",
  "description": "Whether to trigger when the first known condition is already true. The default depends on rule type; falling edges cannot enable it.",
  "default": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.rule_type`

```json
{
  "const": "rising_edge",
  "description": "Event-rule type, determining the meanings of conditions, durations, thresholds, and other fields. Constant: \"rising_edge\", a point event when the condition changes from false to true."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[1].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Boolean condition expression. Unknown values use three-valued logic; nonzero numeric values are not implicitly true."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.emit_initial`

```json
{
  "const": false,
  "description": "Whether to trigger when the first known condition is already true. The default depends on rule type; falling edges cannot enable it. Constant: false.",
  "default": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.rule_type`

```json
{
  "const": "falling_edge",
  "description": "Event-rule type, determining the meanings of conditions, durations, thresholds, and other fields. Constant: \"falling_edge\", a point event when the condition changes from true to false."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[2].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition",
    "window_duration"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Boolean condition expression. Unknown values use three-valued logic; nonzero numeric values are not implicitly true."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.window_duration`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Positive fixed window duration after a start_only trigger. A condition that remains true does not automatically retrigger when the window ends."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.emit_initial`

```json
{
  "type": "boolean",
  "description": "Whether to trigger when the first known condition is already true. The default depends on rule type; falling edges cannot enable it.",
  "default": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.rule_type`

```json
{
  "const": "start_only",
  "description": "Event-rule type, determining the meanings of conditions, durations, thresholds, and other fields. Constant: \"start_only\", a fixed window after triggering, with repeated triggers suppressed inside it."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[3].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "signal",
    "window",
    "direction",
    "threshold"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.signal`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Numeric signal name or allowed numeric expression checked by window_delta. This is neither an original DBC name nor a Boolean condition."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.window`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Full look-back window for calculating change: a positive duration with a unit, not a window ID."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.direction`

```json
{
  "enum": [
    "rise",
    "fall",
    "any"
  ],
  "description": "Direction of change. Options: \"rise\", last minus first; \"fall\", first minus last; \"any\", absolute difference between first and last."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.threshold`

```json
{
  "type": "number",
  "minimum": 0,
  "description": "Non-negative change threshold in the input signal's unit, inclusive of equality. The business threshold must be supplied rather than guessed."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.monotonic`

```json
{
  "type": "boolean",
  "description": "Whether values must remain monotonic within the look-back window. Defaults to false; direction still selects the direction.",
  "default": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.coverage_policy`

```json
{
  "const": "full",
  "description": "Observation-coverage policy for window_delta. Currently only full is accepted, requiring the entire look-back window to be covered. Constant: \"full\".",
  "default": "full"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.emit_initial`

```json
{
  "type": "boolean",
  "description": "Whether to trigger when the first known condition is already true. The default depends on rule type; falling edges cannot enable it.",
  "default": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.retrigger`

```json
{
  "enum": [
    "edge",
    "once"
  ],
  "description": "Retrigger behavior for window_delta. Options: \"edge\", another trigger after the condition changes from false to true again; \"once\", at most one trigger per session.",
  "default": "edge"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.rule_type`

```json
{
  "const": "window_delta",
  "description": "Event-rule type, determining the meanings of conditions, durations, thresholds, and other fields. Constant: \"window_delta\", checking change across the complete look-back window."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[4].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Boolean condition expression. Unknown values use three-valued logic; nonzero numeric values are not implicitly true."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.enter_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "How long the entry condition must remain true before activity starts: a non-negative duration with a unit, defaulting to 0s.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.exit_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "How long the exit condition must remain true before exit, or the exit delay used when merging segments. Its meaning depends on the rule/window; a unit is required.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.rule_type`

```json
{
  "const": "debounce",
  "description": "Event-rule type, determining the meanings of conditions, durations, thresholds, and other fields. Constant: \"debounce\", switching activity state after the condition remains stable for the delay."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[5].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "enter_condition",
    "exit_condition"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.enter_condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Boolean expression for entering hysteresis activity, declared separately from the exit condition."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.exit_condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Boolean expression for exiting hysteresis activity. It is not automatically the negation of the entry condition."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.enter_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "How long the entry condition must remain true before activity starts: a non-negative duration with a unit, defaulting to 0s.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.exit_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "How long the exit condition must remain true before exit, or the exit delay used when merging segments. Its meaning depends on the rule/window; a unit is required.",
  "default": "0s"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.rule_type`

```json
{
  "const": "hysteresis",
  "description": "Event-rule type, determining the meanings of conditions, durations, thresholds, and other fields. Constant: \"hysteresis\", with separate entry and exit conditions and stability delays."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[6].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "start_condition",
    "end_condition"
  ],
  "description": "The start condition begins activity; the end condition ends it normally. Reaching the time limit while the state is determinable produces timeout.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.start_condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Boolean expression that starts activity, paired with end_condition in a start/end rule."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.end_condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Boolean expression that ends the current activity. An unknown condition is not a known end."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.timeout`

```json
{
  "description": "Positive maximum wait after starting. null or omission means no time limit; this differs from sample validity valid_for.",
  "default": null
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.timeout.anyOf[0]`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.timeout.anyOf[1]`

```json
{
  "type": "null"
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.emit_initial`

```json
{
  "type": "boolean",
  "description": "Whether to trigger when the first known condition is already true. The default depends on rule type; falling edges cannot enable it.",
  "default": true
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.rule_type`

```json
{
  "const": "start_end",
  "description": "Event-rule type, determining the meanings of conditions, durations, thresholds, and other fields. Constant: \"start_end\", explicit start/end conditions with an optional wait limit."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.rules.items.oneOf[7].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.windows`

```json
{
  "type": "array",
  "description": "Data segments generated from events, with before/after extensions and a segment merge policy.",
  "default": []
}
```

### `analysis.schema.json: $.properties.windows.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.windows.items.allOf[0].else.not`

```json
{
  "required": [
    "exit_delay"
  ]
}
```

### `analysis.schema.json: $.properties.windows.items.allOf[0].then`

```json
{
  "required": [
    "exit_delay"
  ]
}
```

### `analysis.schema.json: $.properties.windows.items.allOf[0].then.properties.anchor`

```json
{
  "const": "activity",
  "description": "Whether the window is based on a point event or an activity interval; it must match the rule's event type. Constant: \"activity\", based on the activity start/end interval."
}
```

### `analysis.schema.json: $.properties.windows.items.allOf[0].if`

```json
{
  "required": [
    "merge"
  ]
}
```

### `analysis.schema.json: $.properties.windows.items.allOf[0].if.properties.merge`

```json
{
  "const": "exit_delay",
  "description": "How to merge segments generated by neighboring events, without changing the original events. Constant: \"exit_delay\", merging re-entry within the exit delay into one segment."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.rule`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "name of the declared event rule that generates this window."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.rule.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.anchor`

```json
{
  "enum": [
    "point",
    "activity"
  ],
  "description": "Whether the window is based on a point event or an activity interval. It must match the referenced rule's event type. Options: \"point\", centered on a point event; \"activity\", based on activity start/end. Inferred from the rule if omitted."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.pre`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Non-negative extension before the event, with a unit. Defaults to 0s."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.post`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Non-negative extension after the event, with a unit. Usually defaults to 0s; start_only inherits the rule's window_duration. Merge rules still check combination constraints."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.merge`

```json
{
  "enum": [
    "none",
    "overlap",
    "overlap_and_adjacent",
    "exit_delay"
  ],
  "description": "How to merge segments generated by neighboring events, without changing the original events. Options: \"none\", keep each segment; \"overlap\", merge overlaps; \"overlap_and_adjacent\", merge overlapping or touching segments; \"exit_delay\", merge re-entry within the exit delay into one segment.",
  "default": "none"
}
```

### `analysis.schema.json: $.properties.windows.items.properties.exit_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "How long the exit condition must remain true before exit, or the exit delay used when merging segments. Its meaning depends on the rule/window; a unit is required."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.windows.items.properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.calculations`

```json
{
  "type": "array",
  "description": "A statistic, integral, duration, or record-selection calculation. Each item specifies its operation, scope, and input.",
  "default": []
}
```

### `analysis.schema.json: $.properties.calculations.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "operation"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[0].else.else`

```json
{
  "required": [
    "expr"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[0].else.if.properties.operation`

```json
{
  "enum": [
    "point_event_count",
    "activity_count",
    "segment_count"
  ],
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[0].then.oneOf[0]`

```json
{
  "required": [
    "expr"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[0].then.oneOf[0].not`

```json
{
  "required": [
    "condition"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[0].then.oneOf[1]`

```json
{
  "required": [
    "condition"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[0].then.oneOf[1].not`

```json
{
  "required": [
    "expr"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[0].if.properties.operation`

```json
{
  "const": "duration",
  "description": "Calculation operation, distinguishing sample and time-weighted statistics; ambiguous mean/min/max are rejected. Constant: \"duration\", total time for which the condition is true."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[1].else.not`

```json
{
  "required": [
    "method"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[1].if.properties.operation`

```json
{
  "const": "integral",
  "description": "Calculation operation, distinguishing sample and time-weighted statistics; ambiguous mean/min/max are rejected. Constant: \"integral\", integration using the held previous value."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[2].else.properties.rule`

```json
{
  "description": "Do not set rule for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[2].then`

```json
{
  "required": [
    "rule"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[2].if.properties.operation`

```json
{
  "enum": [
    "point_event_count",
    "activity_count"
  ],
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[3].else.properties.window`

```json
{
  "description": "Do not set window for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[3].then`

```json
{
  "required": [
    "window"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[3].if.properties.operation`

```json
{
  "enum": [
    "segment_count"
  ],
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[4].then.properties.unit`

```json
{
  "const": "1",
  "description": "Requested result unit; it must be compatible with the quantity."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[4].if.properties.operation`

```json
{
  "enum": [
    "sample_count",
    "point_event_count",
    "activity_count",
    "segment_count"
  ],
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[5].then.properties.scope`

```json
{
  "const": "session",
  "description": "Select the session, event or window over which this calculation runs."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[5].then.properties.expr`

```json
{
  "description": "Do not set expr for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[5].then.properties.condition`

```json
{
  "description": "Do not set condition for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[5].then.properties.method`

```json
{
  "description": "Do not set method for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[5].then.properties.minimum_coverage`

```json
{
  "description": "Do not set minimum_coverage for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[5].then.properties.interval`

```json
{
  "description": "Do not set interval for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[5].if.properties.operation`

```json
{
  "enum": [
    "point_event_count",
    "activity_count",
    "segment_count"
  ],
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[6].else.properties.ddof`

```json
{
  "description": "Do not set ddof for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[6].if.properties.operation`

```json
{
  "enum": [
    "sample_variance",
    "sample_stddev",
    "time_variance",
    "time_stddev"
  ],
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[7].then.properties.ddof`

```json
{
  "const": 0,
  "description": "Degrees of freedom subtracted in the variance or standard deviation denominator."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[7].if.properties.operation`

```json
{
  "enum": [
    "time_variance",
    "time_stddev"
  ],
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[8].else.properties.q`

```json
{
  "description": "Do not set q for this version or operation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[8].then`

```json
{
  "required": [
    "q"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].then.allOf[8].if.properties.operation`

```json
{
  "const": "sample_quantile",
  "description": "Named operation to run for this calculation."
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].if`

```json
{
  "required": [
    "operation"
  ]
}
```

### `analysis.schema.json: $.properties.calculations.items.allOf[0].if.properties.operation`

```json
{
  "$ref": "#/properties/calculations/items/properties/operation",
  "description": "Calculation operation. Sample statistics weight real samples equally; time statistics use the duration for which a value is valid. select returns matching rows, duration sums true time and integral uses zero-order hold. In version 4, sample_count counts valid samples, point_event_count counts points, activity_count counts activities and segment_count counts final segments. The enum lists the available operations."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.scope`

```json
{
  "description": "Calculation scope, defaulting to session. {rule: name} calculates per event; {window: name} calculates per window. References must already be declared."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.scope.oneOf[0]`

```json
{
  "const": "session",
  "description": "Analyze or export the available range of the whole session."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.scope.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "rule"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.scope.oneOf[1].properties.rule`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Referenced rule or window name, already declared in this configuration."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.scope.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "window"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.scope.oneOf[2].properties.window`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Referenced rule or window name, already declared in this configuration."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.operation`

```json
{
  "enum": [
    "select",
    "sample_minimum",
    "sample_maximum",
    "sample_mean",
    "min_time",
    "max_time",
    "time_weighted_mean",
    "duration",
    "integral",
    "sample_count",
    "point_event_count",
    "activity_count",
    "segment_count",
    "sample_variance",
    "sample_stddev",
    "time_variance",
    "time_stddev",
    "sample_rms",
    "time_rms",
    "sample_quantile",
    "sample_median"
  ],
  "description": "Calculation operation. Sample statistics weight real samples equally; time statistics use the duration for which a value is valid. select returns matching rows, duration sums true time and integral uses zero-order hold. In version 4, sample_count counts valid samples, point_event_count counts points, activity_count counts activities and segment_count counts final segments. The enum lists the available operations."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Boolean condition expression. Unknown values use three-valued logic; nonzero numeric values are not implicitly true."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.method`

```json
{
  "const": "zoh",
  "description": "Integration method. Currently only zoh is supported, accumulating the previous held value over its valid duration without automatic linear interpolation. Constant: \"zoh\"."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.partial_policy`

```json
{
  "enum": [
    "report",
    "strict"
  ],
  "description": "Handling of insufficient valid coverage. A calculation inherits execution when omitted; presets check their own parameter contracts. Options: \"report\", report available partial results and coverage information; \"strict\", apply strict completeness requirements to partial results."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.minimum_coverage`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "description": "Minimum required valid-coverage fraction, from 0 to 1. Do not reach the threshold by filling zeros or extending sample validity.",
  "default": 0
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.expr`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Input signal name or allowed expression for statistics. Dependencies, types, and units are checked during compilation."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.rule`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Name of the point or activity rule to count. Used only for object counts."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.window`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Name of the window whose final segments are counted. Only used by segment_count."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.ddof`

```json
{
  "type": "integer",
  "enum": [
    0,
    1
  ],
  "description": "Degrees of freedom for sample variance and standard deviation: 0 uses the population and 1 uses N−1. Time-weighted variants accept only 0."
}
```

### `analysis.schema.json: $.properties.calculations.items.properties.q`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "description": "Exact quantile probability: 0 for the minimum, 1 for the maximum or 0.95 for P95. Only sample_quantile accepts q."
}
```

### `analysis.schema.json: $.properties.presets`

```json
{
  "type": "array",
  "description": "Expand explicitly bound roles and parameters into ordinary rules, windows, and calculations. Signal names do not imply roles or thresholds.",
  "default": []
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "name",
    "preset_type",
    "parameters"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.version`

```json
{
  "const": "1",
  "description": "Preset contract version. Optional, defaulting to the string \"1\". It controls a different object from the analysis file's integer config_version=4."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.role_bindings`

```json
{
  "type": "object",
  "description": "Explicit mapping from preset roles to bound signals. Role names are not original data field names.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.role_bindings.properties.mode`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Bound signal name for a business-mode role, or the selection mode for a calculation interval/export period. Interpret it in the containing object's context."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.role_bindings.properties.mode.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.role_bindings.properties.current`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Signal bound to the charging preset's current role. Unit, direction, and measurement location must be explicit."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.role_bindings.properties.current.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.role_bindings.properties.voltage`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Signal bound to the charging preset's voltage role. A name containing voltage is not enough for automatic selection."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.role_bindings.properties.voltage.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.parameters`

```json
{
  "type": "object",
  "required": [
    "mode_value",
    "current_min",
    "minimum_duration"
  ],
  "description": "Business parameters required by a preset, or numeric parameters with units for message expressions. No undeclared vehicle-specific defaults are used.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.parameters.properties.mode_value`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615,
  "description": "Explicit integer code for the target operating mode, consistent with the role signal's choices and type."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.parameters.properties.current_min`

```json
{
  "type": "number",
  "description": "Explicit current threshold in A. No vehicle- or device-specific default is guessed."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.parameters.properties.compute_energy`

```json
{
  "type": "boolean",
  "default": false,
  "description": "Whether to generate a charging-energy calculation. Defaults to false; enabling it requires the appropriate roles and units to satisfy the contract."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.parameters.properties.compute_charge`

```json
{
  "type": "boolean",
  "default": false,
  "description": "Whether to generate an electric-charge calculation. Defaults to false; calculation uses the explicit current direction and valid coverage."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.parameters.properties.minimum_coverage`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "default": 0,
  "description": "Minimum required valid-coverage fraction, from 0 to 1. Do not reach the threshold by filling zeros or extending sample validity."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.parameters.properties.partial_policy`

```json
{
  "enum": [
    "report",
    "strict"
  ],
  "description": "Handling of insufficient valid coverage. A calculation inherits execution when omitted; presets check their own parameter contracts. Options: \"report\", report available partial results and coverage information; \"strict\", apply strict completeness requirements to partial results."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.parameters.properties.minimum_duration`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Minimum continuous duration required to confirm a condition, including a unit. This is not sample validity or a maximum waiting time."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[0].properties.preset_type`

```json
{
  "const": "charge_session",
  "description": "Preset type: role contracts are checked before ordinary inspectable nodes are created. Constant: \"charge_session\", charging activities with optional energy/electric-charge calculations."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "name",
    "preset_type",
    "parameters"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.version`

```json
{
  "const": "1",
  "description": "Preset contract version. Optional, defaulting to the string \"1\". It controls a different object from the analysis file's integer config_version=4."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.role_bindings`

```json
{
  "type": "object",
  "description": "Explicit mapping from preset roles to bound signals. Role names are not original data field names.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.role_bindings.properties.alarm`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Boolean signal bound to the alarm role in the fault-context preset."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.role_bindings.properties.alarm.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.parameters`

```json
{
  "type": "object",
  "required": [],
  "description": "Business parameters required by a preset, or numeric parameters with units for message expressions. No undeclared vehicle-specific defaults are used.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.parameters.properties.pre`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Non-negative duration extending before an event, including a unit."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.parameters.properties.post`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Non-negative duration extending after an event, including a unit. Specific merging or fixed-window rules impose additional constraints."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.parameters.properties.emit_initial`

```json
{
  "type": "boolean",
  "default": false,
  "description": "Whether to trigger when the first known condition is already true. The default depends on rule type; falling edges cannot enable it."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[1].properties.preset_type`

```json
{
  "const": "fault_context",
  "description": "Preset type: role contracts are checked before ordinary inspectable nodes are created. Constant: \"fault_context\", segments before and after an alarm."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "name",
    "preset_type",
    "parameters"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.version`

```json
{
  "const": "1",
  "description": "Preset contract version. Optional, defaulting to the string \"1\". It controls a different object from the analysis file's integer config_version=4."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.role_bindings`

```json
{
  "type": "object",
  "description": "Explicit mapping from preset roles to bound signals. Role names are not original data field names.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.role_bindings.properties.request`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Signal name bound to the request role in the request/response preset."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.role_bindings.properties.request.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.role_bindings.properties.response`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Declared signal bound to the response role. This is a preset signal binding, not a rule reference in sequences."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.role_bindings.properties.response.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.parameters`

```json
{
  "type": "object",
  "required": [
    "max_delay"
  ],
  "description": "Business parameters required by a preset, or numeric parameters with units for message expressions. No undeclared vehicle-specific defaults are used.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.parameters.properties.min_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Minimum permitted response delay: a non-negative duration with a unit, inclusive of the endpoint."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.parameters.properties.max_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Maximum permitted response delay, inclusive of the endpoint and no less than min_delay. A missing response by the deadline produces an explicit pairing status."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.parameters.properties.emit_initial`

```json
{
  "type": "boolean",
  "default": false,
  "description": "Whether to trigger when the first known condition is already true. The default depends on rule type; falling edges cannot enable it."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.parameters.properties.max_pending`

```json
{
  "type": "integer",
  "minimum": 1,
  "default": 65536,
  "description": "Maximum number of requests awaiting responses simultaneously. A positive integer defaulting to 65536; this is not the total number of input rows."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[2].properties.preset_type`

```json
{
  "const": "command_response",
  "description": "Preset type: role contracts are checked before ordinary inspectable nodes are created. Constant: \"command_response\", request/response delay pairing."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3]`

```json
{
  "type": "object",
  "required": [
    "name",
    "preset_type",
    "role_bindings",
    "parameters"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.version`

```json
{
  "const": "1",
  "description": "Preset contract version. Optional, defaulting to the string \"1\". It controls a different object from the analysis file's integer config_version=4."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.role_bindings`

```json
{
  "type": "object",
  "required": [
    "signal"
  ],
  "description": "Explicit mapping from preset roles to bound signals. Role names are not original data field names.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.role_bindings.properties.signal`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Analysis signal name for the threshold preset's signal role. It must satisfy that role's numeric type and unit requirements."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.role_bindings.properties.signal.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.parameters`

```json
{
  "type": "object",
  "required": [
    "enter_threshold",
    "exit_threshold"
  ],
  "description": "Business parameters required by a preset, or numeric parameters with units for message expressions. No undeclared vehicle-specific defaults are used.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.parameters.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Threshold unit. Optional; defaults to the bound signal role's unit. An explicit unit must match the signal and does not cause additional conversion."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.parameters.properties.enter_threshold`

```json
{
  "type": "number",
  "description": "Entry threshold for threshold activity, in the role signal's unit. Direction semantics determine its ordering relative to the exit threshold."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.parameters.properties.exit_threshold`

```json
{
  "type": "number",
  "description": "Exit threshold for threshold activity. Do not guess a value to suppress fluctuation."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.parameters.properties.enter_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "How long the entry condition must remain true before activity starts: a non-negative duration with a unit, defaulting to 0s."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.parameters.properties.exit_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "How long the exit condition must remain true before exit, or the exit delay used when merging segments. Its meaning depends on the rule/window; a unit is required."
}
```

### `analysis.schema.json: $.properties.presets.items.oneOf[3].properties.preset_type`

```json
{
  "const": "threshold_excursion",
  "description": "Preset type: role contracts are checked before ordinary inspectable nodes are created. Constant: \"threshold_excursion\", threshold activity that enters on excursion and exits on recovery."
}
```

### `analysis.schema.json: $.properties.message_calculations`

```json
{
  "type": "array",
  "description": "Per-message accumulation for selected CAN messages. Each actual message is evaluated independently; ordinary signal holding is not applied and no extra time difference is multiplied in.",
  "default": []
}
```

### `analysis.schema.json: $.properties.message_calculations.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "update_message",
    "expr",
    "unit"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.source`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Raw CAN source name for message accumulation. May be omitted when exactly one applicable source exists; multiple candidates require a choice."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.source.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.profile`

```json
{
  "enum": [
    "sclicer-functions-v1",
    "can-text-v1"
  ],
  "description": "Message reader/decoder implementation. Optional and determined by the source: the existing BLF path uses sclicer-functions-v1; ASC, raw CAN CSV, and mixed sources use can-text-v1. An explicit value must match the source."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.operation`

```json
{
  "const": "legacy_sum",
  "description": "Message accumulation method. Optional; legacy_sum is currently the only supported method and the default. Each qualifying message contributes once independently."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.message_policy`

```json
{
  "const": "current_message-v1",
  "description": "Optional, defaulting to current_message-v1. Use only the current target message's decoded values, without retaining a previous message's cached values."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.expr`

```json
{
  "type": "string",
  "pattern": "\\S",
  "description": "Restricted expression using explicitly bound names and supported operations. It does not execute Python, attribute access, or arbitrary functions."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.unit`

```json
{
  "type": "string",
  "pattern": "\\S",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message`

```json
{
  "type": "object",
  "required": [
    "frame_id"
  ],
  "description": "CAN message that triggers evaluation. frame_id is required; channel defaults to the source channel. Standard/extended and CAN/FD constraints are optional and otherwise identified from actual input.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.allOf[0].then.properties.frame_id`

```json
{
  "maximum": 2047,
  "description": "Non-negative integer CAN message ID, further constrained by the standard/extended frame flag."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.allOf[0].if`

```json
{
  "required": [
    "is_extended"
  ]
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.allOf[0].if.properties.is_extended`

```json
{
  "const": false,
  "description": "Extended-frame flag, which must be Boolean. Standard and extended frame IDs have different ranges. Constant: false."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "CAN channels in user configuration start at 1; 1 maps to internal channel 0. If omitted, inherits the source's unique channel."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.properties.frame_id`

```json
{
  "description": "CAN message ID, as an integer or string. 0x is hexadecimal, 0b binary, and no prefix decimal. The parsed value must be 0 to 536870911; an explicitly standard frame is limited to 2047."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.properties.is_extended`

```json
{
  "type": "boolean",
  "description": "Optional standard/extended frame constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.update_message.properties.is_fd`

```json
{
  "type": "boolean",
  "description": "Optional CAN/CAN FD constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.split_by_sign`

```json
{
  "type": "object",
  "description": "Select positive/negative accumulation buckets using the current raw decoded field, without extra normalization or reuse of another message's old value.",
  "required": [
    "signal",
    "bucket"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.split_by_sign.properties.signal`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Analysis signal name used to distinguish positive/negative direction. It must come from the same target message but may be independent of contribution expr."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.split_by_sign.properties.signal.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.split_by_sign.properties.bucket`

```json
{
  "enum": [
    "positive",
    "negative"
  ],
  "description": "Select the positive or negative bucket according to the specified current raw decoded field. Options: \"positive\", positive-value bucket; \"negative\", negative-value bucket."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.split_by_sign.properties.value_policy`

```json
{
  "const": "raw_decoded-v1",
  "description": "Value basis for grouping. Optional, defaulting to raw_decoded-v1: use this message's original decoded direction value without extra conversion or reuse of old values."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.parameters`

```json
{
  "type": "object",
  "propertyNames": {
    "type": "string",
    "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
    "not": {
      "enum": [
        "abs",
        "isclose",
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield"
      ],
      "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
    }
  },
  "description": "Business parameters required by a preset, or numeric parameters with units for message expressions. No undeclared vehicle-specific defaults are used."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.parameters.additionalProperties`

```json
{
  "type": "object",
  "required": [
    "value",
    "unit"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.parameters.additionalProperties.properties.value`

```json
{
  "type": "number",
  "description": "Interval text with a unit, or a numeric expression parameter with a separate unit declaration. Type requirements depend on the containing object."
}
```

### `analysis.schema.json: $.properties.message_calculations.items.properties.parameters.additionalProperties.properties.unit`

```json
{
  "type": "string",
  "pattern": "\\S",
  "description": "Unit of numeric values. Units are checked during expressions and conversion and are not inferred from field or file names."
}
```

### `analysis.schema.json: $.properties.execution`

```json
{
  "type": "object",
  "required": [],
  "description": "Execution backend and analysis-layer resource limits. A declared budget is not a static measurement of peak memory.",
  "default": {},
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.execution.properties.backend`

```json
{
  "enum": [
    "numpy",
    "reference",
    "auto"
  ],
  "description": "Numerical implementation selection. auto selects reference or numpy from verified whole-plan categories without reading or trial runs; numpy and reference select their respective numerical implementations. Explicit choices are preserved and runtime errors do not switch backends.",
  "default": "auto"
}
```

### `analysis.schema.json: $.properties.execution.properties.batch_rows`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "Maximum records/samples per read batch. A positive integer defaulting to 65536; it is not the number of parallel independent tasks.",
  "default": 65536
}
```

### `analysis.schema.json: $.properties.execution.properties.memory_budget_bytes`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "Memory budget for the new analysis layer. Positive bytes, default 268435456. It is not an RSS limit for the entire Python process or legacy reader.",
  "default": 268435456
}
```

### `analysis.schema.json: $.properties.execution.properties.result_buffer_rows`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "Maximum buffered result rows before writing. A positive integer defaulting to 4096.",
  "default": 4096
}
```

### `analysis.schema.json: $.properties.execution.properties.partial_policy`

```json
{
  "enum": [
    "report",
    "strict"
  ],
  "description": "Handling of insufficient valid coverage. A calculation inherits execution when omitted; presets check their own parameter contracts. Options: \"report\", report available partial results and coverage information; \"strict\", apply strict completeness requirements to partial results.",
  "default": "report"
}
```

### `analysis.schema.json: $.properties.execution.properties.on_budget_exceeded`

```json
{
  "const": "error",
  "description": "Budget-exceeded behavior. Currently only error is accepted: fail explicitly without dropping data or adding scans of the legacy input. Constant: \"error\".",
  "default": "error"
}
```

### `analysis.schema.json: $.properties.execution.properties.spool_quota_bytes`

```json
{
  "description": "Temporary-disk quota in positive integer bytes. null or omission means no quota is set.",
  "default": null
}
```

### `analysis.schema.json: $.properties.execution.properties.spool_quota_bytes.anyOf[0]`

```json
{
  "type": "null"
}
```

### `analysis.schema.json: $.properties.execution.properties.spool_quota_bytes.anyOf[1]`

```json
{
  "type": "integer",
  "minimum": 1
}
```

### `analysis.schema.json: $.properties.execution.properties.process_count`

```json
{
  "type": "integer",
  "minimum": 1,
  "default": 1,
  "description": "Limit reading and DBC-decoding workers for this analysis, excluding the main process. Supply an integer of at least 1; default 1. An explicit API or CLI override takes precedence. All files remain part of one continuous session."
}
```

### `analysis.schema.json: $.properties.outputs`

```json
{
  "type": "object",
  "description": "Result tables and optional signal/CAN exports. The published output directory can be reused; each run uses distinct timestamped filenames located through its completion manifest.",
  "default": {},
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.contributions`

```json
{
  "enum": [
    "none",
    "full"
  ],
  "description": "Whether to save individual message contributions. none is the default and keeps summaries only; full explicitly saves every contribution. Options: \"none\" and \"full\".",
  "default": "none"
}
```

### `analysis.schema.json: $.properties.outputs.properties.tables`

```json
{
  "enum": [
    "readable_csv",
    "csv",
    "jsonl"
  ],
  "description": "Result table format. Defaults to readable_csv: Chinese column names, exact seconds, and metrics for the same interval combined into one row. csv retains flat interchange tables and integer nanoseconds; jsonl retains one JSON object per line. Only the selected table set is generated. This does not select the configuration file format.",
  "default": "readable_csv"
}
```

### `analysis.schema.json: $.properties.outputs.properties.manifest`

```json
{
  "const": "json",
  "description": "Run-manifest format. Currently fixed to json. Constant: \"json\".",
  "default": "json"
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv`

```json
{
  "description": "Optional signal CSV export. Omission or null disables it. Enabling it requires an explicit signal selection and scope.",
  "default": null
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[0]`

```json
{
  "type": "null"
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "signals"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.signals`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "uniqueItems": true,
  "description": "Explicit list of original signal aliases to export, already declared in analysis signals. All signals are not exported by default."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.signals.items`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])"
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.signals.items.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.scope`

```json
{
  "description": "Explicitly select the whole session, events from a rule, or the range of a window."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.scope.oneOf[0]`

```json
{
  "const": "session",
  "description": "Analyze or export the available range of the whole session."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.scope.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "window"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.scope.oneOf[1].properties.window`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Referenced rule or window name, already declared in this configuration."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling`

```json
{
  "description": "Independent resampling settings for this export. Omission or null keeps original sampling; an export grid must not change the calculation interval."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[0]`

```json
{
  "type": "null"
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "continuous",
    "period",
    "max_gap"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.continuous`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "uniqueItems": true,
  "description": "Numeric signals explicitly allowed to use linear resampling. State, counter, and enum signals must not be treated as continuous merely because their dtype is numeric."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.continuous.items`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])"
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.continuous.items.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.max_gap`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Maximum actual sample gap permitted for interpolation or reconstruction. A positive duration with a unit, not a fixed time offset."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period`

```json
{
  "description": "Export grid period. Use a positive duration string for a fixed period, or a mode: dbc object for a DBC cycle. Periods are not inferred from filenames."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[0]`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed time offset: a number with s/ms/us/ns. Dates are not accepted."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1].properties.driver.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.start`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Origin of the resampling time grid, defaulting to 0ns. It does not change the analysis range or original frame timestamps."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames`

```json
{
  "description": "Optional original/reconstructed CAN frame export. Omission or null disables it; enabling it does not replace the analysis result tables.",
  "default": null
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[0]`

```json
{
  "type": "null"
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "format"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].allOf[0].then`

```json
{
  "required": [
    "timezone"
  ]
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].allOf[0].if`

```json
{
  "required": [
    "capture_date"
  ]
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].allOf[1].then`

```json
{
  "required": [
    "capture_date"
  ]
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].allOf[1].if`

```json
{
  "required": [
    "timezone"
  ]
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].allOf[2].then.not.anyOf[0]`

```json
{
  "required": [
    "capture_date"
  ]
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].allOf[2].then.not.anyOf[1]`

```json
{
  "required": [
    "timezone"
  ]
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].allOf[2].if`

```json
{
  "required": [
    "source_time_reference"
  ]
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].allOf[2].if.properties.source_time_reference`

```json
{
  "const": "epoch",
  "description": "Export time coordinates, relative to an origin or absolute Unix epoch. The original time interpretation must be explicit. Constant: \"epoch\", absolute Unix epoch time."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.source`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "name of a declared source. The reference must exist; sources are not inferred from matching field or semantic names."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.source.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.format`

```json
{
  "enum": [
    "asc",
    "blf"
  ],
  "description": "CAN output format, separate from csv/jsonl result tables. Options: \"asc\", ASC text frames; \"blf\", BLF binary frames."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.scope`

```json
{
  "description": "Explicitly select the whole session, events from a rule, or the range of a window."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[0]`

```json
{
  "const": "session",
  "description": "Analyze or export the available range of the whole session."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "window"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[1].properties.window`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Referenced rule or window name, already declared in this configuration."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "windows"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[2].properties.windows`

```json
{
  "const": "all",
  "description": "Use ranges from all configured windows. all is not interpreted as a window name."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.source_time_reference`

```json
{
  "enum": [
    "relative",
    "epoch"
  ],
  "description": "Export time coordinates, relative to an origin or absolute Unix epoch. The original time interpretation must be explicit. Options: \"relative\" and \"epoch\"."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.capture_date`

```json
{
  "type": "string",
  "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
  "description": "Explicit capture date for exports requiring a date header. The run date must not be substituted for the acquisition date."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.output_offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Explicit fixed offset for exported timestamps, with s/ms/us/ns. It does not change the analysis clock."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling`

```json
{
  "description": "Independent resampling settings for this export. Omission or null keeps original sampling; an export grid must not change the calculation interval."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[0]`

```json
{
  "type": "null"
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "period",
    "max_gap",
    "messages"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.max_gap`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Maximum actual sample gap permitted for interpolation or reconstruction. A positive duration with a unit, not a fixed time offset."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages`

```json
{
  "type": "array",
  "minItems": 0,
  "maxItems": 4096,
  "description": "CAN reconstruction rules, locating messages precisely and declaring continuous fields and protected fields."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items`

```json
{
  "type": "object",
  "required": [
    "frame_id",
    "continuous"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.allOf[0].then.properties.frame_id`

```json
{
  "maximum": 2047,
  "description": "Integer message IDs for standard frames are limited to 2047. The plan loader checks the range after converting string IDs."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.allOf[0].if`

```json
{
  "required": [
    "is_extended"
  ]
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.allOf[0].if.properties.is_extended`

```json
{
  "const": false,
  "description": "When standard frame format is explicitly selected, an integer ID must fit in 11 bits."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "CAN channels in user configuration start at 1; 1 maps to internal channel 0. If omitted, inherits the source's unique channel."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.frame_id`

```json
{
  "description": "CAN message ID, as an integer or string. 0x is hexadecimal, 0b binary, and no prefix decimal. The parsed value must be 0 to 536870911; an explicitly standard frame is limited to 2047."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.is_extended`

```json
{
  "type": "boolean",
  "description": "Optional standard/extended frame constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.is_fd`

```json
{
  "type": "boolean",
  "description": "Optional CAN/CAN FD constraint. If omitted, use DBC and actual frames; request an explicit value only when ambiguous. Explicit null is invalid."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.continuous`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "uniqueItems": true,
  "description": "Numeric signals explicitly allowed to use linear resampling. State, counter, and enum signals must not be treated as continuous merely because their dtype is numeric."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.continuous.items`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.protected`

```json
{
  "type": "array",
  "minItems": 0,
  "maxItems": 4096,
  "uniqueItems": true,
  "description": "DBC signals whose original values must be preserved during reconstruction, such as counters or checksum fields. Unknown algorithms are not recomputed automatically."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.protected.items`

```json
{
  "type": "string",
  "minLength": 1
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.same_time_policy`

```json
{
  "enum": [
    "error",
    "last_by_sequence"
  ],
  "description": "Handling of multiple updates for one signal at the same timestamp. Conflicts are not ignored and records are not arbitrarily reordered. Options: \"error\", fail on conflicting same-time updates; \"last_by_sequence\", use the last update in original order."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.unknown_policy`

```json
{
  "enum": [
    "passthrough",
    "nearest"
  ],
  "description": "Output for messages without a matching reconstruction rule. Options: \"passthrough\", preserve original frames and timestamps; \"nearest\", select the nearest original frame within an explicit time distance."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.max_distance`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Maximum allowed time distance when selecting the nearest original frame. A non-negative duration; 0s accepts only an original frame at exactly the same timestamp."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.period`

```json
{
  "description": "Export grid period. Use a positive duration string for a fixed period, or a mode: dbc object for a DBC cycle. Periods are not inferred from filenames."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[0]`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Fixed time offset: a number with s/ms/us/ns. Dates are not accepted."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.start`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Origin of the resampling time grid, defaulting to 0ns. It does not change the analysis range or original frame timestamps."
}
```

### `analysis.schema.json: $.properties.outputs.properties.can_frames.oneOf[1].properties.timezone`

```json
{
  "type": [
    "string",
    "null"
  ],
  "description": "Fixed acquisition timezone, such as +08:00 or UTC. For BLF export of relative timestamps, provide it together with capture_date."
}
```

### `analysis.schema.json: $.properties.metadata`

```json
{
  "type": "object",
  "description": "Additional notes as an object of JSON-native values. They do not trigger implicit conversion, template execution, or inference of business parameters.",
  "default": {},
  "additionalProperties": true
}
```

### `analysis.schema.json: $.properties.sequences`

```json
{
  "type": "array",
  "description": "Pair request and response point events in FIFO order, specifying allowed delays and the maximum number of pending requests.",
  "default": []
}
```

### `analysis.schema.json: $.properties.sequences.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "start",
    "response",
    "max_delay"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Unique declaration name. Start with a non-reserved English letter or underscore, followed by letters, digits, or underscores. Names must not repeat."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.name.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.start`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Identifier of the request start-point rule, already declared in rules. Activity rules cannot be referenced here."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.start.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.response`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "Identifier of the response point rule, referencing a rising_edge, falling_edge, or start_only rule defined in rules. This is not a signal name or a sequence identifier."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.response.not`

```json
{
  "enum": [
    "abs",
    "isclose",
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield"
  ],
  "description": "Reserved names are not allowed: \"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.min_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Minimum permitted response delay: a non-negative duration with a unit, inclusive of the endpoint."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.max_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "Maximum permitted response delay, inclusive of the endpoint and no less than min_delay. A missing response by the deadline produces an explicit pairing status."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.max_pending`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "Maximum number of requests awaiting responses simultaneously. A positive integer defaulting to 65536; this is not the total number of input rows.",
  "default": 65536
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval`

```json
{
  "description": "Interval source for this node. Omission inherits the global default. Multiple candidate drivers require an explicit driver."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.sequences.items.properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.intervals`

```json
{
  "type": "object",
  "description": "Time intervals used by ordinary temporal calculations. Defaults to actual record gaps and can be overridden per consumer. Signal validity is unchanged.",
  "default": {},
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.intervals.properties.default`

```json
{
  "description": "Calculation interval used by consumers without a specific override. Defaults to actual observed timestamp differences."
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"actual\"."
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"fixed\"."
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "Positive fixed calculation interval with a unit, such as 100ms. actual and dbc do not accept this field."
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "Interval source: actual uses observed timestamp differences, fixed uses an explicit value, and dbc reads the driving message cycle at runtime. Export-period objects allow only dbc. Constant: \"dbc\"."
}
```

### `analysis.schema.json: $.properties.intervals.properties.default.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Original signal name that drives this calculation or selects the DBC cycle. Omission is allowed only when the declaration has a unique identifiable driver."
}
```

### `analysis.schema.json: $.properties.diagnostics`

```json
{
  "type": "object",
  "description": "Opt-in additional provenance, integrity diagnostics, or retention of working files. These three options are independent and all default to off.",
  "default": {},
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.diagnostics.properties.trace`

```json
{
  "type": "boolean",
  "default": false,
  "description": "Whether to generate additional detailed provenance. Defaults to false; necessary results and error handling remain enabled."
}
```

### `analysis.schema.json: $.properties.diagnostics.properties.integrity`

```json
{
  "type": "boolean",
  "default": false,
  "description": "Whether to run additional integrity diagnostics. Defaults to false; this does not disable input checks required for ordinary analysis."
}
```

### `analysis.schema.json: $.properties.diagnostics.properties.retain_work`

```json
{
  "type": "boolean",
  "default": false,
  "description": "Whether to retain this run's own working files. Defaults to false; it does not authorize deleting or retaining unrelated user files."
}
```

### `analysis.schema.json: $.properties.imports`

```json
{
  "type": "array",
  "description": "Optional shared definition files. Import sources/signals/derived in list order, then append this file's declarations. Duplicate names fail; only one import level is allowed. Omission or an empty array means no external definitions."
}
```

### `analysis.schema.json: $.properties.imports.items`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "^(?!.*://)(?!.*[\\*?\\[\\]])[\\s\\S]+$",
  "description": "Explicit local .json/.yaml/.yml file path, relative to the main configuration directory. URLs and wildcards are not supported."
}
```

### `analysis.schema.json: $.properties.overrides`

```json
{
  "type": "object",
  "description": "Explicit local overrides of shared definitions. imports must also be declared; unknown targets and disallowed fields fail.",
  "additionalProperties": false
}
```

### `analysis.schema.json: $.properties.overrides.properties.sources`

```json
{
  "type": "object",
  "description": "Permitted field overrides addressed by existing definition names. Overrides cannot create targets, rename them, or replace arbitrary metadata."
}
```

### `analysis.schema.json: $.properties.overrides.properties.sources.additionalProperties`

```json
{
  "type": "object"
}
```

### `analysis.schema.json: $.properties.overrides.properties.signals`

```json
{
  "type": "object",
  "description": "Permitted field overrides addressed by existing definition names. Overrides cannot create targets, rename them, or replace arbitrary metadata."
}
```

### `analysis.schema.json: $.properties.overrides.properties.signals.additionalProperties`

```json
{
  "type": "object"
}
```

### `analysis.schema.json: $.properties.overrides.properties.derived`

```json
{
  "type": "object",
  "description": "Permitted field overrides addressed by existing definition names. Overrides cannot create targets, rename them, or replace arbitrary metadata."
}
```

### `analysis.schema.json: $.properties.overrides.properties.derived.additionalProperties`

```json
{
  "type": "object"
}
```

## batch-v1.schema.json

[Original validation schema](../../../Schema/batch-v1.schema.json)

### `batch-v1.schema.json: $`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Chronaxis independent batch configuration version 1",
  "description": "Independent batch tasks. jobs load plans when each task starts; template expands files and compiles independent plans while the batch configuration is loaded, reading DBC metadata if needed but not business records. Consecutive files from one session remain in one analysis plan.",
  "type": "object",
  "required": [
    "batch_version"
  ],
  "$comment": "独立批量任务结构；相对引用只指向随包规范。",
  "additionalProperties": false
}
```

### `batch-v1.schema.json: $.oneOf[0]`

```json
{
  "required": [
    "jobs"
  ]
}
```

### `batch-v1.schema.json: $.oneOf[0].not.anyOf[0]`

```json
{
  "required": [
    "template"
  ]
}
```

### `batch-v1.schema.json: $.oneOf[0].not.anyOf[1]`

```json
{
  "required": [
    "inputs"
  ]
}
```

### `batch-v1.schema.json: $.oneOf[0].not.anyOf[2]`

```json
{
  "required": [
    "source"
  ]
}
```

### `batch-v1.schema.json: $.oneOf[1]`

```json
{
  "required": [
    "template",
    "inputs"
  ]
}
```

### `batch-v1.schema.json: $.oneOf[1].not`

```json
{
  "required": [
    "jobs"
  ]
}
```

### `batch-v1.schema.json: $.properties.batch_version`

```json
{
  "type": "integer",
  "const": 1,
  "description": "Structural version of the independent batch manifest, currently the integer 1. It is independent of each analysis plan's config_version. Constant: 1."
}
```

### `batch-v1.schema.json: $.properties.process_count`

```json
{
  "type": "integer",
  "minimum": 1,
  "default": 1,
  "description": "Maximum number of analysis worker processes. A positive integer defaulting to 1; excludes the scheduler parent and CAN reader child processes. Each task has an independent budget."
}
```

### `batch-v1.schema.json: $.properties.fail_fast`

```json
{
  "type": "boolean",
  "default": false,
  "description": "Whether to stop dispatching new tasks after observing a failure. Defaults to false; started tasks complete necessary cleanup."
}
```

### `batch-v1.schema.json: $.properties.backend`

```json
{
  "enum": [
    null,
    "reference",
    "numpy",
    "auto"
  ],
  "default": null,
  "description": "Numerical implementation override. null inherits each analysis plan; auto selects per plan from its static category; reference and numpy fix the numerical implementation. Explicit choices are preserved and runtime errors do not switch backends."
}
```

### `batch-v1.schema.json: $.properties.jobs`

```json
{
  "type": "array",
  "description": "Independent tasks. Each child plan is read when its task starts; failures are isolated according to fail_fast. Consecutive files from one session must not be split into independent tasks."
}
```

### `batch-v1.schema.json: $.properties.jobs.items`

```json
{
  "type": "object",
  "required": [
    "plan"
  ],
  "additionalProperties": false
}
```

### `batch-v1.schema.json: $.properties.jobs.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
  "description": "Task name. If omitted, generate job_1, job_2, etc. by list position. Names must be unique, including case-insensitive comparison."
}
```

### `batch-v1.schema.json: $.properties.jobs.items.properties.plan`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "YAML or JSON path for a child analysis plan, relative to the batch manifest directory. Loaded only when the task starts."
}
```

### `batch-v1.schema.json: $.properties.template`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Analysis template path used for each input file. Each file creates an independent task; cannot be combined with jobs."
}
```

### `batch-v1.schema.json: $.properties.inputs`

```json
{
  "description": "Each input file creates an independent task. Accepts a file, directory, wildcard, or list. Explicit lists keep declaration order; matches use natural order. Directories are not recursive unless an explicit ** wildcard is used."
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "Paths kept in declaration order. Each directory's matched files are sorted in natural order."
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[2].items`

```json
{
  "description": "Path text, or a file declaration with its own offset."
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "A file, directory, or wildcard path."
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "path"
  ],
  "additionalProperties": false
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "This item's file, directory, or wildcard path."
}
```

### `batch-v1.schema.json: $.properties.inputs.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Time offset for this file, including its unit. It is added to the source-wide offset."
}
```

### `batch-v1.schema.json: $.properties.source`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "Source name whose input path is replaced in the template. May be omitted if the template has only one source."
}
```

## definitions.schema.json

[Original validation schema](../../../Schema/definitions.schema.json)

### `definitions.schema.json: $`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Chronaxis shared definition file",
  "description": "Shares only sources, signals, and derived expressions. No version wrapper or nested imports; the structure is interpreted under the referencing current analysis configuration (config_version: 4).",
  "$comment": "公共定义文件结构；由分析配置通过单层imports引用。",
  "type": "object",
  "minProperties": 1,
  "additionalProperties": false
}
```

### `definitions.schema.json: $.properties.sources`

```json
{
  "type": "array",
  "description": "Sources in declaration order. Put consecutive files in one source's paths. Loading may enumerate filenames and read DBC metadata needed for omitted signal settings, but does not read business records."
}
```

### `definitions.schema.json: $.properties.sources.items`

```json
{
  "$ref": "analysis.schema.json#/properties/sources/items"
}
```

### `definitions.schema.json: $.properties.signals`

```json
{
  "type": "array",
  "description": "Bind original source fields to simple analysis signal names, specifying type, unit, and validity duration."
}
```

### `definitions.schema.json: $.properties.signals.items`

```json
{
  "$ref": "analysis.schema.json#/properties/signals/items"
}
```

### `definitions.schema.json: $.properties.derived`

```json
{
  "$ref": "analysis.schema.json#/properties/derived",
  "description": "Derived expressions declared by name, sharing the signals namespace. They cannot override same-named signals from earlier files or this file."
}
```
