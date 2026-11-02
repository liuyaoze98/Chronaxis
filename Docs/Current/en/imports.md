# Sharing source and signal definitions

<a id="公共来源与信号定义"></a>

Use a shared definitions file when several analyses use the same inputs, signals, or derived expressions. It shares configuration, not running state, caches, or results. An analysis refers to these files through root `imports`. Imports are one level deep; `load_analysis_plan` expands them into an ordinary `AnalysisPlan`.

<a id="运行完整例子"></a>
## Run the complete example

The teaching input gives **38 J** for `power` over 0–6 seconds. The shared definition `double_power = power * 2` gives **76 J**.

```text
examples/
  analysis-imports.yaml
  shared/definitions.yaml
  data/can/quickstart.asc
  data/can/teaching.dbc
```

Open [the analysis configuration](../examples/analysis-imports.yaml) and [shared definitions](../examples/shared/definitions.yaml). Run these commands from the repository root, using new output paths:

```powershell
python -m chronaxis validate Docs/Current/examples/analysis-imports.yaml
python -m chronaxis explain Docs/Current/examples/analysis-imports.yaml
python -m chronaxis config origins Docs/Current/examples/analysis-imports.yaml
python -m chronaxis config resolve Docs/Current/examples/analysis-imports.yaml --defaults --output work/independent.yaml
python -m chronaxis run work/independent.yaml --output work/imports-result
```

The executable [imports example](../examples/imports_example.py) creates its own temporary copy, checks **38 J / 76 J** with both backends, exports a standalone configuration, removes its copied shared definitions, and runs the standalone configuration again:

```powershell
python Docs/Current/examples/imports_example.py
```

<a id="主配置怎样引用"></a>
## Refer to a shared file

Add this root field to the analysis configuration:

```yaml
imports: [shared/definitions.yaml]
```

`imports` is an optional list of explicit local paths; an empty list means no imports. Supported suffixes are `.json`, `.yaml`, and `.yml`, matched without case sensitivity. JSON and YAML files can be mixed. Paths can be absolute or relative to the file containing `imports`. URLs, globs, environment substitution, and directory scanning are not supported here.

The shared file can contain:

```yaml
sources:
  - name: bus
    paths: ../data/can/quickstart.asc
    dbc_by_channel:
      '1': ../data/can/teaching.dbc
signals:
  - name: power
    field:
      frame_id: '0x100'
      signal: Power
derived:
  double_power:
    expr: power * 2
```

Shared sources and signals require explicit names so they can be referenced and overridden. With a single source, a signal's `source` can be inferred. In this example, ASC uses relative seconds, and signal type and unit come from the DBC.

Only root `sources`, `signals`, and `derived` are allowed in a shared file, with at least one present. Do not add `config_version`, another wrapper object, nested imports, `dataset`, rules, calculations, execution settings, or outputs.

<a id="合并顺序与重名"></a>
## Merge order and duplicate names

Imports are processed in their listed order, followed by definitions in the main file. List order is preserved. Duplicate names are rejected; there is no automatic replacement or recursive merge. Signal names and derived-expression names share a namespace. Importing the same file twice is not silently deduplicated.

An error points to the second definition and identifies the first. To change a shared signal's `valid_for`, use `overrides` instead of declaring that signal again. References across definitions, units, and expression cycles are still validated after expansion.

<a id="为本次任务调整公共定义"></a>
## Adjust a shared definition for this analysis

For example, a DBC period of 1 second gives the signal a default validity of 3 seconds. To use 1 second in this analysis, add:

```yaml
imports: [shared/definitions.yaml]
overrides:
  signals:
    power:
      valid_for: 1s
```

The nested keys identify existing definitions by name; this is a mapping, not a list.

| Definition | Fields that can be overridden |
|---|---|
| `sources` | `path`, `paths`, `dbc_by_channel`, `time`, `reader` |
| `signals` | `dtype`, `unit`, `valid_for`, `period`, `conversion`, `choices`, `valid_range`, `invalid_values`, `sample_policy`, `same_time_policy` |
| `derived` | `expr`, `unit` |

An override replaces the whole selected field. For example, a new `time` object replaces the old object: omitted child fields use their usual defaults rather than inheriting old values. Replacing `path` or `paths` leaves only the selected path form. Paths introduced by an override are relative to the main configuration.

Overrides cannot create or rename definitions, change signal bindings, or add metadata. The expanded configuration is validated normally. Origin reports identify the actual overriding declaration.

<a id="路径和错误位置属于声明文件"></a>
## Paths and errors belong to the declaring file

A shared source's `path`, `paths`, and `dbc_by_channel` paths are relative to that shared file, not the importing file. Arbitrary metadata text is not rewritten as a path.

Diagnostics identify the actual file, original list positions, and one-based line and column. For a missing field, they identify the nearest existing parent. To inspect origins:

```powershell
python -m chronaxis config origins Docs/Current/examples/analysis-imports.yaml
python -m chronaxis config origins Docs/Current/examples/analysis-imports.yaml --fields --format json
```

The default report lists definition origins. `--fields` lists explicit fields that still contribute to the resolved configuration, without copying their values. Defaults do not receive invented source locations.

| Report field | Meaning |
|---|---|
| `configuration` | Main configuration path. |
| `configuration_type` | Kind of configuration. |
| `scope` | Whether the report describes definitions or fields. |
| `items` | Origin entries. |
| `effective_path` | Location in the expanded configuration. |
| `declared_path` | Location in the original declaring file. |
| `file`, `line`, `column` | Original file and position. |
| `name` | Definition name; `null` for field entries. |
| `resolved_paths` | Resolved source input paths, when applicable. |

<a id="导出与其他入口"></a>
## Exporting and using other entry points

`config resolve` expands imports and presets, removes applied overrides, and writes a new configuration with fixed absolute input paths. Paths are resolved lexically, without resolving symlink targets. The result is revalidated before writing. This does not copy input data; the exported configuration must still be able to access those files.

`config convert` changes the file format only. It preserves imports and path text, so a relative-path output must stay in the same directory as the input.

An INI mapping can use imports inside its `analysis` block when loaded through `load_legacy_ini`. The bytes-based `import_legacy_ini` entry point does not perform implicit file I/O. A batch root has no `imports` field, although each child analysis can use imports; batch origin reporting describes batch paths rather than expanding child analyses.

Use file-based `load_analysis_plan` for imports. `AnalysisPlan.from_dict` expects an already expanded dictionary and rejects unresolved imports. The resulting plan does not retain another full copy of the raw configuration and its locations.

For editor support, use the shared-definitions and analysis schemas in [Schema and editor setup](schema-editor.md). Cross-file duplicates and references still require actual configuration validation.
