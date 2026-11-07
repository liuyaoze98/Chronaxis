# Output settings and publication

<a id="输出配置与结果发布"></a>

Root `outputs` selects result table formats, per-message contributions, and additional data exports. `AnalysisRunner.run()` performs the analysis and prepares staged output; `result.write(output_directory)` publishes it. CLI `run` performs both steps.

Analysis tables describe what happened and the calculated values. Signal CSV files contain timestamps and values. ASC/BLF files contain CAN message bytes. These outputs serve different purposes and can be requested together. Input and output formats need not match: ASC input can be exported as BLF.

**Resampling** produces values at regularly spaced times you specify. For example, if voltage is 10 V at 10 ms and 120 V at 120 ms, an output every 100 ms can estimate 100 V at 100 ms along the straight line between those observations. The output marks that value `estimated`; it is not an actual sample at 100 ms. Because it uses the later 120 ms observation, this is an offline operation. Rules and integration still use the original data, not these estimates.

<a id="当前导出环境限制"></a>
## Current export environment limitation

Signal CSV and CAN frame exports currently require root `metadata.device_label` to be `home` or `work`. This is an existing development-device label restriction; the label does not affect times or numerical results. `home` in an export example identifies the environment where that example was made, not a label every user should adopt.

Ordinary CSV analysis does not require this field. Batch report labels can use nonempty custom text; those rules do not apply to standalone exports. A missing or unsupported label causes these exports to fail, but does not affect analyses that do not request them.

<a id="outputs的全部字段"></a>
## All `outputs` fields

`outputs` is an optional root object, for example `outputs: {tables: jsonl}`. Paths in this table are relative to it: `tables` means `outputs.tables`. Table format does not change the calculation, and the two additional export types can be enabled independently.

| Field | Type | Required | Default | Choices and effect |
|---|---|---|---|---|
| `tables` | String | No | `"readable_csv"` | `"readable_csv"` creates readable Chinese tables joining related intervals and metrics; `"csv"` preserves the flat exchange fields; `"jsonl"` writes corresponding summary rows as line-delimited JSON. Select the format appropriate to the receiving tool. |
| `manifest` | String | No | `"json"` | Run manifest format; use `json` or omit it. The manifest describes this run's inputs, settings, and outputs. |
| `contributions` | String | No | `"none"` | `"full"` retains each target message's evaluation and skip details. `"none"` accumulates summaries without retaining per-evaluation detail counts. This switch applies to per-message calculations, not ordinary calculations. |
| `signal_csv` | Object or `null` | No | `null`, disabled | Enable selected original-signal export, optionally with resampling. See [Signal exports](signal-exports.md). |
| `can_frames` | Object or `null` | No | `null`, disabled | Enable frame export from one CAN source, choosing format and optional reconstruction. See [CAN exports](can-exports.md). |

BLF, ASC, and raw-message CSV frame exports all use `outputs.can_frames`.

<a id="export-scope"></a>
<a id="导出范围"></a>
### Export scope

| `scope` value | Effect | Supported exports |
|---|---|---|
| Omitted or `session` | Export the session range. | Signal CSV and CAN frames |
| `{window: context}` | Export segments from the window named `context`. | Signal CSV and CAN frames |
| `{windows: all}` | Export segments from every window. | CAN frames only |

Window names come from `windows[].name`. Set the choice in `outputs.signal_csv.scope` or `outputs.can_frames.scope`; do not add a separate `window` field. `null` is not a valid scope. Signal export may omit scope for the session range. Specify one named window only when selecting window-based export; signal export does not accept `windows: all`.

Each export chooses its own scope independently. Ranges include the start and exclude the end: a 1–2 second segment includes 1 second but not 2 seconds. Interpolation does not borrow samples from outside the requested range to fill endpoints.

<a id="选择导出类型"></a>
## Choose an export type

- [Signal CSV and resampling](signal-exports.md): export physical-value updates or regularly spaced values.
- [CAN frames and resampling](can-exports.md): export original ASC/BLF frames or reconstruct selected fields.

<a id="输出文件位置"></a>
## Find the output files

`run` first prepares exports in the work directory. After `result.write()`, they appear beside the analysis tables in the final output directory.

Read the timestamped index named by the run manifest's `exports.index_file` there to find each export's time range, source, and file paths. Data files are under `exports_<timestamp>/export-XXXXXXXX/`. Content digests are retained only with `diagnostics.integrity: true`; default checks cover necessary file identity and size.

Writing the same open result to the same or another output directory checks and copies already generated files; it does not reread or decode the original logs.

The accompanying example holds 3 V, 7 V, and 3 V for one second each, giving **13 V·s**, with voltage above 5 V over `[1,2)`. Requesting a 250 ms signal grid and a 500 ms CAN grid together leaves those analysis results unchanged. See [Examples](examples.md), especially the [dual-grid example](examples.md#dual-grid).

Full classes, functions, and arguments are available in [signal_exports](../reference/chronaxis.results.signal_exports.md), [signal_grid](../reference/chronaxis.results.signal_grid.md), [frame_exports](../reference/chronaxis.results.frame_exports.md), and [frame_rebuild](../reference/chronaxis.results.frame_rebuild.md) (Chinese implementation references).

Direct Python calls to export_signal_csv or export_can_frames return ExportManifest with output_dir, manifest_path and output_files. The directory is reusable and files are timestamped. Read these properties instead of treating the return value as a Path. Exports requested through a plan are located through the run manifest exports entry.
