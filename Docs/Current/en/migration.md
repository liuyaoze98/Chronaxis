# Import legacy INI configurations

<a id="旧ini导入"></a>

Converting a business INI file to the current analysis format requires signal bindings, units, and a choice of migration semantics. Use `chronaxis legacy import`. See [CLI](cli.md) for ordinary analysis commands and [Message calculations](message-calculations.md) for current per-message accumulation.

<a id="import-mapping"></a>
<a id="用mapping文件说明旧变量对应什么新信号"></a>
## Map old variables to current signals

A migration mapping is different from the resulting analysis configuration. `mapping_version`, `analysis`, and `sections` are root fields in the mapping. Per-section settings belong under `sections.<old INI section>`, such as `sections.TRIGGER_1.name`. Only the nested `analysis` object uses ordinary `dataset`, `sources`, and `signals` fields.

```powershell
python -m chronaxis legacy import old.ini --mode legacy_sum --mapping mapping.yaml --output converted.json
```

The importer currently writes the generated plan as JSON, so `--output` requires a `.json` suffix. This is a restriction of the import command; ordinary analysis and mapping inputs also accept YAML. To edit the result as YAML, run `chronaxis config convert converted.json --output converted.yaml`, then use that file. Output files must not exist.

The mapping identifies each old variable's input and signal and names the generated rules. Only `mapping_version` and `analysis` are always required:

| Field | Type | Meaning and omission behavior |
|---|---|---|
| `mapping_version` | Integer | Required mapping structure version, currently `1`. |
| `path_base` | String | Default and only value: `"mapping_directory"`. Relative inputs inside `analysis` start at the mapping file's directory and become absolute in the generated plan. |
| `io_policy` | String | Default and only value: `"explicit_mapping"`. Use the inputs and outputs specified in `analysis`. Old INI `INPUT`/`OUTPUT` paths remain in the report but are not reused directly. |
| `analysis` | Object | Base [analysis configuration](configuration.md), including dataset, sources, and signals. Omit `rules`, `windows`, `message_calculations`, and `presets`, or set them to empty lists; the importer generates them. Do not prepopulate other rules. |
| `aliases` | Object | Map old expression variables to new `analysis.signals` names, e.g. `{"BMS_BatCurr":"current"}`. Both sides are strings; several old names may map to one new signal. Omit when an old variable uniquely matches an original signal field. Ambiguous same-named fields across sources require an explicit choice. |
| `sections` | Object | Map each old INI section title to its conversion settings, e.g. `"TRIGGER_1":{"name":"working","window":"context"}`. If supplied, every section must match exactly, with no missing or extra sections. It can be omitted entirely for single, start_only, and start_end: names such as `trigger_1` and `window_1` follow INI order. Legacy sum and slope still need units or mode parameters. |

When supplying `sections`, use the fields for the selected mode without mixing others. Omitting start_end sections uses `start_end_timeout-v1` and `emit_initial=false`; `--mode` still explicitly selects that migration.

| Mode | Fields for each section |
|---|---|
| `sclicer_single`, `sclicer_start_only` | `name`, `window` |
| `sclicer_start_end` | `name`, `window`, `semantics`, `emit_initial` |
| `sclicer_slope` | `name`, `window`, `coverage_policy`, `emit_initial`, `retrigger` |
| `legacy_sum` | `name`, `source`, `unit`, `message_policy`, `update_message`, `parameter_units` |

| Section field | Type | Meaning and choices |
|---|---|---|
| `name` | String | Unique name for the generated rule or metric, e.g. `working`, following the [configuration naming rules](configuration.md). Generated nodes cannot collide. |
| `window` | String | Unique generated-window name, e.g. `context`, distinct from the rule name. |
| `semantics` | String | Only `"start_end_timeout-v1"`: start recording when start holds, end when end holds, and count timeout from start. This differs from the old behavior described below. |
| `emit_initial` | Boolean | `false` does not trigger merely because the first observed state already meets start; `true` does. For slope, this applies to the first fully calculable window. |
| `coverage_policy` | String | Only `"full"`: usable signal data must cover the entire lookback window. The old two-points-are-enough behavior is unsupported. |
| `retrigger` | String | `"edge"` can trigger again after the change condition becomes false then true; `"once"` triggers at most once in this analysis. |
| `source` | String | Raw-message source name from `analysis.sources`, e.g. `bus`. |
| `unit` | String | Unit of the accumulated old formula, derived from the expression and parameter units, e.g. `J`. Must match the actual expression dimension. |
| `message_policy` | String | Only `"current_message-v1"`: each target message uses its own decoded values, without values cached from a previous message. |
| `update_message` | Object | Message that triggers one evaluation. `frame_id` is required; channel defaults to the selected source channel; `is_extended` and `is_fd` can be omitted. See [Message calculations](message-calculations.md). |
| `parameter_units` | Object | Unit for every old `period`, `factor`, and `global` parameter, with exactly matching names and string values, e.g. `{"period":"s","factor":"1"}`. No missing or extra parameters. These units validate the converted expression. |

Complete inputs are linked from [Examples](examples.md). `analysis` accepts the same grouped signals as ordinary analysis. For raw CAN, an unambiguous DBC can fill omitted type, unit, channel, and related metadata; validity follows the three-period default. This reads DBC metadata. Fully explicit declarations do not add a DBC read. Decoded tables have no DBC and still need `dtype` and `unit`. Ambiguous sources, aliases, calculation units, or slope parameters are errors; variable names are not evidence for guessing them.

<a id="逐消息能量迁移的完整示例"></a>
## Complete per-message energy example

Download [energy.ini](../examples/migration-sum/energy.ini) and [mapping.yaml](../examples/migration-sum/mapping.yaml), keeping the accompanying `examples` structure. Inputs are [message-clean.asc](../examples/data/message-clean.asc) and [power.dbc](../examples/data/power.dbc). Old INI paths are retained as origin information; `explicit_mapping` selects the new mapping paths.

| Old INI setting | Meaning and unit basis | Mapping or generated setting |
|---|---|---|
| `signal_P=Power` | DBC power signal, in W. | `aliases.signal_P=power`; `analysis.signals` binds `power`. |
| `period=0.1` | The old formula treats each message as 100 ms = 0.1 s, according to the acquisition/business convention. | `parameter_units.period: s`; generated parameter value `0.1`, unit `s`. |
| `expr=signal_P * period` | Power times fixed duration gives energy per evaluation. | `expr: power * period`; result unit `J`. |

`parameter_units` declares a unit without converting the old number. If the INI says `period=100` meaning milliseconds, use `ms`, not `s`. This constant does not read `signals.period` or use actual inter-message time differences.

Run from the repository root. `sum-import.json`, its same-prefix artifacts, and `sum-result` must not exist:

```powershell
chronaxis legacy import Docs/Current/examples/migration-sum/energy.ini --mode legacy_sum --mapping Docs/Current/examples/migration-sum/mapping.yaml --output sum-import.json
chronaxis run sum-import.json --output sum-result
```

See the actual [session results](../examples/migration-sum/results/会话结果.csv). Each 4000 W message contributes **4000 × 0.1 = 400 J**. The two 4000 W records both occur at 0 seconds but each counts separately; the final 0 W record contributes zero. Total: **800 J**. Check generated `message_calculations` and `energy（J）=800`, status `完整` (“complete”), in `会话结果.csv`. Do not replace the fixed constant with timestamp differences.

Omitting the period unit, adding a unit for a nonexistent INI parameter, or declaring result unit A for this energy expression must fail import. Read the report's section, field path, and explanation, then correct and retry. Changing the output unit cannot fix an inconsistent formula dimension.

<a id="import-modes"></a>
<a id="选择导入模式"></a>
## Select an import mode

| Mode | Generated behavior | Important difference |
|---|---|---|
| `legacy_sum` | Evaluate and accumulate each target message, optionally by direction. | Each evaluation uses only that message. Old cross-message value caching is not migrated. |
| `sclicer_single` | Record each activity, include `pre` before it, and extend by the exit wait. | The segment ends at its specified deadline without waiting for another frame; separate activities remain separate events. |
| `sclicer_start_only` | Record a point on a false-to-true edge and take a fixed-duration window. | An always-true condition does not retrigger automatically when the window expires. |

`sclicer_start_end` and `sclicer_slope` are described below. An unsupported expression or cache use fails the entire conversion. The report identifies the section and key to fix; it does not call a partially converted plan successful. After conversion, run `validate`, `explain`, and `run` to check suitability for the real input.

<a id="起止与变化量转换模式"></a>
### Start/end and change-window modes

| Mode | Required choice | Behavior and differences |
|---|---|---|
| `sclicer_start_end` | Explicit sections supply `semantics="start_end_timeout-v1"` and Boolean `emit_initial`; omitted sections use that semantics and `false`. | Start begins, end finishes. The old implementation prepared at start and began slicing at end. Selecting this mode accepts the defined new behavior. Positive old `duration_sec` becomes a timeout; nonpositive means unlimited waiting. `pre` is retained; the unused old `post` is not added. |
| `sclicer_slope` | Each section supplies name, window, `coverage_policy=full`, `emit_initial`, and `retrigger`. | `_slope_` becomes monotonic `window_delta`; `_slope2_` does not require monotonicity. Both require full-window coverage, unlike the old two-point test. |

In `_slope_rise_4s_BMS_SOC_raw_5`, `BMS_SOC_raw` is one complete signal name. The importer looks it up in aliases rather than splitting it into `BMS`, `SOC`, and `raw`. Unexplained trailing components fail conversion.

The change calculation uses a complete 4-second window. Legacy `legacy_samples` behavior that accepted any two points within it is unsupported. All five modes use `legacy import`, with one mode explicitly chosen per command. See [Examples](examples.md) for mappings.

Python entry points are [import_legacy_ini / load_legacy_ini](../reference/chronaxis.migration.api.md) and [write_legacy_import](../reference/chronaxis.migration.publication.md) (Chinese implementation references). Original INI bytes, report, and successful plan are saved separately.

<a id="导入报告的设备来源标签"></a>
## Import report device label

CLI reads `CHRONAXIS_DEVICE_LABEL`, strips surrounding whitespace, and uses `pending` if unset or empty. The environment's user supplies the label; it identifies report origin, does not change `analysis.metadata`, and does not establish validation of real data.

In PowerShell, `$env:CHRONAXIS_DEVICE_LABEL = 'home'` is appropriate only if `home` actually identifies the current device. Python `load_legacy_ini` accepts `device_label` explicitly and does not inherit the CLI environment handling automatically.
