# Examples and templates

<a id="示例与模板"></a>

Choose a complete task by goal. All bundled inputs are synthetic and can be checked by hand. For real logs, confirm units, validity periods, direction, synchronization, and business thresholds again.

[Actual results and explanations](example-results.md) provides commands, output tables, arithmetic, and downloads for the runnable YAML, JSON and batch configurations in the current catalog. Select a configuration here, then look it up by filename there. Two base configurations and shared definitions are building blocks, not standalone analysis success cases.

Common results: [Energy and averages](example-results.md#analysis-yaml), [Events and windows](example-results.md#activity-yaml), [Invalid and stale data](example-results.md#quality-yaml), [Actual intervals](example-results.md#interval-actual-yaml) / [Fixed intervals](example-results.md#interval-fixed-yaml), and [State mappings](example-results.md#signal-state-combined-yaml).

<a id="完整教学任务"></a>
## Complete teaching tasks

| Task | Inputs and complete configuration | Guide and result |
|---|---|---|
| Measure variation in bench power and P95 across loads | [Configuration](../examples/power-statistics.yaml), [ASC](../examples/data/can/power-statistics.asc), [DBC](../examples/data/can/teaching.dbc) | P95 is 18 W for five readings and 19.5 W for two individual load means. [Commands and arithmetic](calculations.md#v4-power-statistics) |
| ASC/BLF energy and averages | [quickstart.asc](../examples/data/can/quickstart.asc), [DBC](../examples/data/can/teaching.dbc), [analysis.yaml](../examples/analysis.yaml) | [Quick start](quickstart.md): 38 J, 6 W, and 38/6 W. |
| Event → window → energy | [activity.asc](../examples/data/can/activity.asc), [activity.yaml](../examples/activity.yaml) | [Activity tutorial](activity-tutorial.md): 50 J in the event and 70 J in the window; selecting from confirmation gives 30 J / 70 J. |
| Shared source and derived definitions | [analysis-imports.yaml](../examples/analysis-imports.yaml), [definitions.yaml](../examples/shared/definitions.yaml), quickstart.asc and teaching.dbc | [Shared definitions](imports.md): 38 J, 6 W, 38/6 W, and 76 J from doubled power. |
| Stream rows in Python | [api_example.py](../examples/api_example.py) | Runs the neighboring analysis.yaml by default; accepts your own configuration and a reusable `--output` directory. |
| Rolling mean from actual timestamps | [Temporal transforms](temporal-transforms.md) | Minimal example: 18 A at 0.2 s; DBC-weighted example is separate. |
| Custom Python function/statistic/transform | [Custom analysis operators](host-extensions.md) | Peak: 80 A. |
| Lookup and interpolation | [Lookup reference](expressions.md#lookup-reference) | Table-based conversion with declared units. |
| Result aggregation | [Aggregation guide](aggregations.md) | Combine named event/window results with an explicit operation. |
| High-performance integrator | [Same-frame per-message accumulation](fast-energy.md) | Single file: 800 J; independent-file total: 1200 J. |

<a id="集中绑定周期导出和ini迁移专题"></a>
<a id="集中绑定-周期导出和ini迁移专题"></a>
## Grouped bindings and DBC grids

These focused examples include complete inputs, configuration, and actual outputs, listed separately from the result index above.

| Task | Materials and guide | Result to check |
|---|---|---|
| Bind several signals in one message | [Configuration](../examples/grouped/analysis.yaml), [ASC](../examples/grouped/pack.asc), [DBC](../examples/grouped/pack.dbc); [Signals](signals.md) | [Maximum voltage 42 V](../examples/grouped/results/会话结果.csv), [edge at 0.1 s](../examples/grouped/results/事件结果.csv). |
| Export two grids from DBC periods | [Configuration](../examples/dbc-grid/analysis.yaml), [ASC](../examples/dbc-grid/grid.asc), [DBC](../examples/dbc-grid/grid.dbc); [Signal exports](signal-exports.md), [CAN exports](can-exports.md) | [Four signal rows](../examples/dbc-grid/results/resampled.csv), [five CAN frames](../examples/dbc-grid/results/frames.asc). |

<a id="按功能选择最小配置与扩展示例"></a>
## Minimal and extended configurations by feature

Each file below is a complete analysis configuration, with inputs supplied under `data`. Minimal examples demonstrate one goal; extensions add the stated choice. The linked guides explain the values and references.

| Feature | Minimal complete configuration | Extension and guide |
|---|---|---|
| ASC/BLF directory | [input-can-directory.yaml](../examples/input-can-directory.yaml) | Read two continuous logs in natural order; [Quick start](quickstart.md). |
| Decoded CSV | [input-csv-minimal.yaml](../examples/input-csv-minimal.yaml) | [Time offset](../examples/input-csv-offset.yaml); [Inputs](inputs.md). |
| Numeric signal | [signal-number-minimal.yaml](../examples/signal-number-minimal.yaml) | [mA to A](../examples/signal-number-conversion.yaml); [Signals](signals.md). |
| Boolean and state | [Boolean](../examples/signal-bool-minimal.yaml), [enum](../examples/signal-enum-minimal.yaml) | [Combined condition](../examples/signal-state-combined.yaml), mapping codes to Boolean/state values. |
| Expressions | [expression-minimal.yaml](../examples/expression-minimal.yaml) | [expression-extended.yaml](../examples/expression-extended.yaml); [Expressions](expressions.md). |
| Event rules | [Sustained condition](../examples/rule-condition_duration-minimal.yaml) | Each rule has minimal/extended examples in [Rules](rules.md). |
| Event windows | [window-minimal.yaml](../examples/window-minimal.yaml) | [Merging](../examples/window-merged.yaml), [exit wait](../examples/window-exit-delay.yaml); [Windows](windows.md). |
| Request/response | [sequence-minimal.yaml](../examples/sequence-minimal.yaml) | [Three outcomes](../examples/sequence-outcomes.yaml); [Sequences](sequences.md). |
| Record intervals | [Actual time](../examples/interval-actual.yaml) | [Fixed intervals](../examples/interval-fixed.yaml); [Intervals](intervals.md). |
| Calculations | [calculation-minimal.yaml](../examples/calculation-minimal.yaml) | [Nine operations](../examples/calculation-operations.yaml); [Calculations](calculations.md). |
| Message accumulation | [message-minimal.yaml](../examples/message-minimal.yaml) | [Directional totals](../examples/message-directions.yaml); [Message calculations](message-calculations.md). |
| Threshold preset | [preset-threshold-minimal.yaml](../examples/preset-threshold-minimal.yaml) | [Confirmation wait](../examples/preset-threshold-delay.yaml), [partial result](../examples/preset-threshold-partial.yaml); [Presets](presets.md). |
| Execution and diagnostics | [execution-diagnostics.yaml](../examples/execution-diagnostics.yaml) | [Report partial](../examples/execution-report.yaml), [strict rejection](../examples/execution-strict.yaml); [Execution](execution.md). |
| Batch | [batch-minimal.yaml](../examples/batch-minimal.yaml) | [Two independent jobs](../examples/batch-extended.yaml); [Batch execution](batch.md). |
| Signal export | [Original updates](../examples/export-signal-minimal.yaml) | [500 ms grid](../examples/export-signal-grid.yaml); [Signal exports](signal-exports.md). |
| CAN export | [Original frames](../examples/export-can-minimal.yaml) | [Reconstructed grid](../examples/export-can-grid.yaml), [all windows](../examples/export-can-all-windows.yaml); [CAN exports](can-exports.md). |

Use [prepare_can_examples.py](../examples/prepare_can_examples.py) to create BLF and mixed-format counterparts in a new directory. Commands and the output layout are in [Quick start](quickstart.md).

<a id="生成带输入的配置模板"></a>
## Generate templates with inputs

Installed Chronaxis generates templates, primarily ASC/BLF with DBC and small synthetic logs for the task. CSV scenes retain their appropriate tables. The target directory must not exist. Default `annotated` style includes comments; `--style minimal` generates the same configuration with less explanatory text.

Both styles omit default fields that serve no purpose in the example. Ordinary examples omit `session`/`entity`, a uniquely inferable source reference, and default scopes/policies. Extensions retain settings needed to demonstrate their particular choice, such as a nondefault policy, conversion, or resource limit.

Comments explain what each parent groups and what each child controls. Read sources/signals first, then rules/windows/calculations. Listing imports before their uses and derived expressions before references helps reading; the parser permits other root-key orders too.

```powershell
chronaxis config init --list
chronaxis config init fault-window --output fault-demo
chronaxis validate fault-demo/plan.yaml
chronaxis run fault-demo/plan.yaml --output fault-result
```

| Scene | Purpose | Entry file | Result to check |
|---|---|---|---|
| `can-blf` | CAN BLF and DBC | plan.yaml | Raw codes 1/3/1 decode through `2x+1` to 3/7/3 V, each held 1 s: 13 V·s. The fourth frame is unrelated. |
| `can-asc` | CAN ASC and DBC | plan.yaml | The same 1/3/1 → 3/7/3 V and 13 V·s; fourth frame unrelated. |
| `signal-csv` | Integral and two averages from signal CSV | plan.yaml | 2/4/8/10 W for 1/2/1/2 s: 38 J; sample mean 6 W; time-weighted mean 38/6 W. |
| `charge-session` | Charging with explicit roles, units, and direction | plan.yaml | Activity `[0s,2s)`: 400 V × 10 A × 2 s = 8000 J, output 8000/3600 Wh; 10 A × 2 s = 20 A·s, output 20/3600 Ah. |
| `fault-window` | Fault edge and surrounding window | plan.yaml | Alarm rises at 2 s. With 1 s before and 2 s after, the segment is `[1s,4s)`. |
| `command-response` | Pairing and timeout | plan.yaml | Request at 1 s receives response at 2 s: 1 s delay. Request at 4 s reaches its 2 s wait limit at 6 s without a response. |
| `threshold` | Entry and exit thresholds | plan.yaml | 85°C enters at 0 s, 77°C retains alarm, 75°C exits at 9 s: 9 s duration. The 80/75°C thresholds are synthetic choices. |
| `stability` | Hysteresis and debounce | plan.yaml | Hysteresis `[1s,4s)`, mean 247/3°C; 1 s entry/exit debounce `[2s,4s)`, mean 81°C. |
| `raw-can-csv` | Explicit raw CAN CSV layout | plan.yaml | Codes 1/3/1 decode to 3/7/3 V for 1 s each: 13 V·s. Fourth frame unrelated. |
| `signal-export` | Signal export with an independent interpolation grid | plan.yaml | Analysis remains 38 J. Original samples and 500 ms grid are separate; 12 grid points from 0 to 5.5 s, starting 2/3/4 W. |
| `can-export` | Original CAN frames | plan.yaml | Analysis 13 V·s; original frames within the range retain order, without resampling. |
| `batch` | Two independent jobs | batch.yaml | Both read the same synthetic input independently and complete with 38 J each; they are not slices of one session. |

Run ordinary templates with `chronaxis run DIRECTORY/plan.yaml --output NEW_DIRECTORY`; use `chronaxis batch run DIRECTORY/batch.yaml --output NEW_DIRECTORY` for batch. CAN dependencies are part of the ordinary package installation. Export device labels reflect the [current implementation restriction](exports.md), not a universal label for every machine.



<a id="下载完整案例并运行"></a>
## Download and run complete cases

The configurations and `data` files below are included in the offline manual. Run from the `examples` directory and reuse analysis output directories with timestamped filenames. Inputs are synthetic and do not establish thresholds for real equipment.

<a id="can-joint-analysis"></a>
<a id="can电压与csv电流联合分析"></a>
### Combine CAN voltage with CSV current

[can-joint-analysis.yaml](../examples/can-joint-analysis.yaml) reads [joint.asc](../examples/data/joint.asc), [joint.dbc](../examples/data/joint.dbc), and [joint-current.csv](../examples/data/joint-current.csv). Both sources declare `synthetic_clock` as their shared origin; that declaration does not synchronize clocks automatically. Voltage is 3, 7, and 3 V at 0, 1, and 2 seconds, with current fixed at 2 A. Over `[0,3)`, power is 6, 14, and 6 W for one second each, giving **26 J**.

```powershell
chronaxis run can-joint-analysis.yaml --output joint-result
```

<a id="start-end-case"></a>
<a id="start_end活动与超时"></a>
### Start/end activity and timeout

[start-end.yaml](../examples/start-end.yaml) uses [start-end.asc](../examples/data/can/start-end.asc) and the teaching DBC. `begin>0` starts, `done>0` ends, with at most 5 seconds. The [teaching event CSV](../examples/results/start-end-yaml/事件结果.csv) contains `[0,2)`, `[4,9)`, and `[11,14)`; the second is `超时结束` (ended by timeout). `cycle_mean（1）` is 10, 52, and 110. For the second, `(40×2 + 60×3)/5 = 52`. Time columns are seconds. For a new run, read the timestamped event CSV path from `outputs` in that run's manifest.

```powershell
chronaxis run start-end.yaml --output cycle-result
```

<a id="message-energy"></a>
<a id="每条can消息的贡献与跳过"></a>
### Contributions and skipped CAN messages

[message-energy.yaml](../examples/message-energy.yaml) reads [power.blf](../examples/data/power.blf) and [power.dbc](../examples/data/power.dbc). Two same-time 4000 W messages each multiply by explicit 0.1 s, totaling **800 J**. A third target message lacks required data and contributes a `missing_input` row; an unrelated ID is not an attempt. Use this run’s manifest to locate the contribution table and inspect its three rows, not nonexistent attempt counters in the summary. This example explicitly chooses legacy decoding to demonstrate incomplete messages; it does not recommend relaxed checking for your data.

```powershell
chronaxis run message-energy.yaml --output message-result
```

<a id="dual-grid"></a>
<a id="信号250ms与can500ms两个导出网格"></a>
### A 250 ms signal grid and 500 ms CAN grid

[dual-grid.yaml](../examples/dual-grid.yaml) uses the same joint.asc and joint.dbc, exporting voltage and reconstructed CAN frames. The analysis alias is `voltage`; the DBC field is `Voltage`. They are not interchangeable. The synthetic example uses `metadata.device_label: home` under the current [export limitation](exports.md).

```powershell
chronaxis run dual-grid.yaml --output grid-result
```

`voltage_area` remains **13 V·s**. The signal grid has 12 positions from 0 to 2.75 s, beginning 3, 4, 5, 6, 7 V. The CAN grid requests six positions from 0 to 2.5 s and generates five frames from 0 to 2 s. The excluded 3-second endpoint cannot support interpolation, so the last three signal points are `missing/missing_right`, and the CAN manifest has `skipped_grid_points=1`.

Grids do not change the analysis integral. CAN encoding follows DBC quantization: 5 V can be represented exactly, while 4 V lies halfway between raw codes and uses `nearest_even-v1`. Find both exports through the index named by this run’s manifest at `exports.index_file` rather than assuming directory numbers.

<a id="仅用于组合教学片段的基础文件"></a>
## Building blocks that are not standalone tasks

[teaching-base.yaml](../examples/teaching-base.yaml) and [electrical-base.yaml](../examples/electrical-base.yaml) define only sources and signals. Add the chapter's rules or calculations before running. They load as plans but are not independent analysis examples. [shared/definitions.yaml](../examples/shared/definitions.yaml) is for imports and is not run alone.

<a id="自动核对脚本"></a>
## Automated example checks

[run_example.py](../examples/run_example.py) checks YAML/JSON, both backends, and CLI. [imports_example.py](../examples/imports_example.py) checks shared definitions and standalone resolved configurations. [readability_examples.py](../examples/readability_examples.py) checks expressions, batches, and partial-result semantics. [advanced_examples.py](../examples/advanced_examples.py), with `--output NEW_DIRECTORY`, checks the four complete cases above. These are verification tools; ordinary users can start by running the tutorial commands directly.
