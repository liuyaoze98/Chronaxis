# Actual results for every example

<a id="每个示例的实际结果与解释"></a>

> These results come from actual runs of bundled synthetic data. They are not expected values for other logs.

This page covers 76 runnable YAML configurations (including two batch plans) and two JSON configurations. Two teaching base files and one shared-definitions file are not standalone tasks and are listed separately at the end.

Run commands from the shared `examples` directory; output directories can be reused with timestamped filenames. Ordinary examples use readable Chinese CSV by default: exact seconds, metrics joined by interval, and individual statuses/explanations. Explicit CSV/JSONL exchange formats and frame/signal exports retain their own layouts. A blank is not zero.

Each `result-summary.json` extracts status, table counts, applicable analysis outcomes, and threshold-preset summaries from the actual run manifest. A full run also creates `run_manifest_<timestamp>.json`. Teaching snapshots use stable download names with the generated time suffix removed; new runs still create timestamped filenames. Teaching outputs omit random run IDs, absolute paths, and resource peaks. Small contribution, trace, or export files are retained only in examples that explicitly request them.

The download inventory records one digest per file. For YAML/JSON configurations, parse the configuration with the safe YAML loader, serialize the resulting object as UTF-8 JSON with sorted keys, no extra whitespace, unescaped Unicode and no non-finite numbers, then calculate SHA-256. Comments, indentation and line endings do not change this semantic digest. For other inputs and result files, calculate SHA-256 directly from the delivered file bytes, preserving line endings. The exact rules are also declared in `examples/results/index.json` under `input_digest_policy`.


The result tables below retain the software's actual Chinese headers and values. Key translations: `区间` = interval; `规则` = rule; `开始时间（s）` / `确认时间（s）` / `结束时间（s）` = start / confirmation / end in seconds; `窗口编号` / `窗口` / `父事件区间` = window number / window name / parent event intervals; `状态` = status; `说明` = explanation; `正常结束` = ended normally; `完整` = complete; `部分有效` = partial; `无法确定` = indeterminate; `超时结束` = ended by timeout; `数据中断` = data interruption; `观测结束，活动尚未确认结束` = observation ended before activity end was confirmed. A metric's `：状态` and `：说明` columns describe that metric alone. `—` displays an empty cell. See [Understanding results](results.md) for all status and quality meanings.

<a id="按文件查找"></a>
## Find an example by filename

| Configuration | Purpose | Actual results |
|---|---|---|
|[activity.yaml](../examples/activity.yaml)|Events, windows, and their energy|[Tables and explanation](#activity-yaml)|
|[analysis-imports.yaml](../examples/analysis-imports.yaml)|Energy, averages, and source reading|[Tables and explanation](#analysis-imports-yaml)|
|[analysis.json](../examples/analysis.json)|Energy, averages, and source reading|[Tables and explanation](#analysis-json)|
|[analysis.yaml](../examples/analysis.yaml)|Energy, averages, and source reading|[Tables and explanation](#analysis-yaml)|
|[batch-extended.yaml](../examples/batch-extended.yaml)|Two independent jobs|[Tables and explanation](#batch-extended-yaml)|
|[batch-minimal.yaml](../examples/batch-minimal.yaml)|One independent job|[Tables and explanation](#batch-minimal-yaml)|
|[calculation-minimal.yaml](../examples/calculation-minimal.yaml)|Power integral|[Tables and explanation](#calculation-minimal-yaml)|
|[calculation-operations.yaml](../examples/calculation-operations.yaml)|Statistics, integration, and selection|[Tables and explanation](#calculation-operations-yaml)|
|[can-joint-analysis.yaml](../examples/can-joint-analysis.yaml)|Combine CAN with an independent current table|[Tables and explanation](#can-joint-analysis-yaml)|
|[conditional-energy.yaml](../examples/conditional-energy.yaml)|Integrate after a sustained condition|[Tables and explanation](#conditional-energy-yaml)|
|[continuous-parallel.yaml](../examples/continuous-parallel.yaml)|Read multipart logs as one continuous session|[Tables and explanation](#continuous-parallel-yaml)|
|[continuous-time-order.yaml](../examples/continuous-time-order.yaml)|Read multipart logs as one continuous session|[Tables and explanation](#continuous-time-order-yaml)|
|[dual-grid.yaml](../examples/dual-grid.yaml)|Original CAN and reconstructed-grid exports|[Tables and explanation](#dual-grid-yaml)|
|[execution-comparison.json](../examples/execution-comparison.json)|Insufficient observation|[Tables and explanation](#execution-comparison-json)|
|[execution-diagnostics.yaml](../examples/execution-diagnostics.yaml)|Explicit input tracing|[Tables and explanation](#execution-diagnostics-yaml)|
|[execution-report.yaml](../examples/execution-report.yaml)|Retain values for the known portion|[Tables and explanation](#execution-report-yaml)|
|[execution-strict.yaml](../examples/execution-strict.yaml)|Reject incomplete values|[Tables and explanation](#execution-strict-yaml)|
|[export-can-all-windows.yaml](../examples/export-can-all-windows.yaml)|Separate export for every window|[Tables and explanation](#export-can-all-windows-yaml)|
|[export-can-grid.yaml](../examples/export-can-grid.yaml)|Regular CAN reconstruction|[Tables and explanation](#export-can-grid-yaml)|
|[export-can-minimal.yaml](../examples/export-can-minimal.yaml)|Original frame export|[Tables and explanation](#export-can-minimal-yaml)|
|[export-signal-grid.yaml](../examples/export-signal-grid.yaml)|Regular signal export|[Tables and explanation](#export-signal-grid-yaml)|
|[export-signal-minimal.yaml](../examples/export-signal-minimal.yaml)|Original signal updates|[Tables and explanation](#export-signal-minimal-yaml)|
|[expression-extended.yaml](../examples/expression-extended.yaml)|Derived power integral within an event|[Tables and explanation](#expression-extended-yaml)|
|[expression-minimal.yaml](../examples/expression-minimal.yaml)|Maximum derived power|[Tables and explanation](#expression-minimal-yaml)|
|[input-asc-minimal.yaml](../examples/input-asc-minimal.yaml)|ASC messages and DBC decoding|[Tables and explanation](#input-asc-minimal-yaml)|
|[input-can-directory.yaml](../examples/input-can-directory.yaml)|Energy, averages, and source reading|[Tables and explanation](#input-can-directory-yaml)|
|[input-csv-minimal.yaml](../examples/input-csv-minimal.yaml)|CSV power integral|[Tables and explanation](#input-csv-minimal-yaml)|
|[input-csv-offset.yaml](../examples/input-csv-offset.yaml)|CSV time alignment|[Tables and explanation](#input-csv-offset-yaml)|
|[input-memory-minimal.yaml](../examples/input-memory-minimal.yaml)|Memory API input|[Tables and explanation](#input-memory-minimal-yaml)|
|[input-raw-csv-mapping.yaml](../examples/input-raw-csv-mapping.yaml)|Raw message reading and DBC decoding|[Tables and explanation](#input-raw-csv-mapping-yaml)|
|[input-raw-csv-minimal.yaml](../examples/input-raw-csv-minimal.yaml)|Raw message reading and DBC decoding|[Tables and explanation](#input-raw-csv-minimal-yaml)|
|[interval-actual.yaml](../examples/interval-actual.yaml)|Integrate using actual intervals|[Tables and explanation](#interval-actual-yaml)|
|[interval-fixed.yaml](../examples/interval-fixed.yaml)|Integrate using fixed periods|[Tables and explanation](#interval-fixed-yaml)|
|[lookup-power.yaml](../examples/lookup-power.yaml)|Average power after a voltage lookup|[Tables and explanation](#lookup-power-yaml)|
|[message-directions.yaml](../examples/message-directions.yaml)|Accumulate messages by direction|[Tables and explanation](#message-directions-yaml)|
|[message-energy.yaml](../examples/message-energy.yaml)|Per-message accumulation|[Tables and explanation](#message-energy-yaml)|
|[message-minimal.yaml](../examples/message-minimal.yaml)|Per-message accumulation|[Tables and explanation](#message-minimal-yaml)|
|[power-statistics.yaml](../examples/power-statistics.yaml)|Power variation and the P95 of loaded-period means|[Tables and explanation](#power-statistics-yaml)|
|[preset-charge-energy.yaml](../examples/preset-charge-energy.yaml)|Charging activity and accumulated quantities|[Tables and explanation](#preset-charge-energy-yaml)|
|[preset-charge-minimal.yaml](../examples/preset-charge-minimal.yaml)|Charging activity detection|[Tables and explanation](#preset-charge-minimal-yaml)|
|[preset-command-automatic.yaml](../examples/preset-command-automatic.yaml)|Request/response pairing|[Tables and explanation](#preset-command-automatic-yaml)|
|[preset-command-minimal.yaml](../examples/preset-command-minimal.yaml)|Request/response pairing|[Tables and explanation](#preset-command-minimal-yaml)|
|[preset-fault-context.yaml](../examples/preset-fault-context.yaml)|Window around an alarm|[Tables and explanation](#preset-fault-context-yaml)|
|[preset-fault-minimal.yaml](../examples/preset-fault-minimal.yaml)|Window after an alarm point|[Tables and explanation](#preset-fault-minimal-yaml)|
|[preset-threshold-delay.yaml](../examples/preset-threshold-delay.yaml)|Alarm after confirmation waits|[Tables and explanation](#preset-threshold-delay-yaml)|
|[preset-threshold-minimal.yaml](../examples/preset-threshold-minimal.yaml)|Hysteresis alarm duration|[Tables and explanation](#preset-threshold-minimal-yaml)|
|[preset-threshold-partial.yaml](../examples/preset-threshold-partial.yaml)|Alarm with unknown initial state|[Tables and explanation](#preset-threshold-partial-yaml)|
|[quality.yaml](../examples/quality.yaml)|Invalid codes and expiry|[Tables and explanation](#quality-yaml)|
|[rule-condition_duration-extended.yaml](../examples/rule-condition_duration-extended.yaml)|Event rule: condition_duration|[Tables and explanation](#rule-condition_duration-extended-yaml)|
|[rule-condition_duration-minimal.yaml](../examples/rule-condition_duration-minimal.yaml)|Event rule: condition_duration|[Tables and explanation](#rule-condition_duration-minimal-yaml)|
|[rule-debounce-extended.yaml](../examples/rule-debounce-extended.yaml)|Event rule: debounce|[Tables and explanation](#rule-debounce-extended-yaml)|
|[rule-debounce-minimal.yaml](../examples/rule-debounce-minimal.yaml)|Event rule: debounce|[Tables and explanation](#rule-debounce-minimal-yaml)|
|[rule-falling_edge-extended.yaml](../examples/rule-falling_edge-extended.yaml)|Event rule: falling_edge|[Tables and explanation](#rule-falling_edge-extended-yaml)|
|[rule-falling_edge-minimal.yaml](../examples/rule-falling_edge-minimal.yaml)|Event rule: falling_edge|[Tables and explanation](#rule-falling_edge-minimal-yaml)|
|[rule-hysteresis-extended.yaml](../examples/rule-hysteresis-extended.yaml)|Event rule: hysteresis|[Tables and explanation](#rule-hysteresis-extended-yaml)|
|[rule-hysteresis-minimal.yaml](../examples/rule-hysteresis-minimal.yaml)|Event rule: hysteresis|[Tables and explanation](#rule-hysteresis-minimal-yaml)|
|[rule-rising_edge-extended.yaml](../examples/rule-rising_edge-extended.yaml)|Event rule: rising_edge|[Tables and explanation](#rule-rising_edge-extended-yaml)|
|[rule-rising_edge-minimal.yaml](../examples/rule-rising_edge-minimal.yaml)|Event rule: rising_edge|[Tables and explanation](#rule-rising_edge-minimal-yaml)|
|[rule-start_end-extended.yaml](../examples/rule-start_end-extended.yaml)|Event rule: start_end|[Tables and explanation](#rule-start_end-extended-yaml)|
|[rule-start_end-minimal.yaml](../examples/rule-start_end-minimal.yaml)|Event rule: start_end|[Tables and explanation](#rule-start_end-minimal-yaml)|
|[rule-start_only-extended.yaml](../examples/rule-start_only-extended.yaml)|Event rule: start_only|[Tables and explanation](#rule-start_only-extended-yaml)|
|[rule-start_only-minimal.yaml](../examples/rule-start_only-minimal.yaml)|Event rule: start_only|[Tables and explanation](#rule-start_only-minimal-yaml)|
|[rule-window_delta-extended.yaml](../examples/rule-window_delta-extended.yaml)|Event rule: window_delta|[Tables and explanation](#rule-window_delta-extended-yaml)|
|[rule-window_delta-minimal.yaml](../examples/rule-window_delta-minimal.yaml)|Event rule: window_delta|[Tables and explanation](#rule-window_delta-minimal-yaml)|
|[sequence-minimal.yaml](../examples/sequence-minimal.yaml)|Request/response pairing|[Tables and explanation](#sequence-minimal-yaml)|
|[sequence-outcomes.yaml](../examples/sequence-outcomes.yaml)|Matched, no response, and indeterminate|[Tables and explanation](#sequence-outcomes-yaml)|
|[signal-bool-minimal.yaml](../examples/signal-bool-minimal.yaml)|Boolean switch edge|[Tables and explanation](#signal-bool-minimal-yaml)|
|[signal-enum-minimal.yaml](../examples/signal-enum-minimal.yaml)|Enum state edge|[Tables and explanation](#signal-enum-minimal-yaml)|
|[signal-number-conversion.yaml](../examples/signal-number-conversion.yaml)|Current unit conversion|[Tables and explanation](#signal-number-conversion-yaml)|
|[signal-number-minimal.yaml](../examples/signal-number-minimal.yaml)|DBC current maximum|[Tables and explanation](#signal-number-minimal-yaml)|
|[signal-state-combined.yaml](../examples/signal-state-combined.yaml)|Combined-state edge|[Tables and explanation](#signal-state-combined-yaml)|
|[start-end.yaml](../examples/start-end.yaml)|Start, normal end, and timeout|[Tables and explanation](#start-end-yaml)|
|[timing-actual.yaml](../examples/timing-actual.yaml)|Rules and pairing using actual time|[Tables and explanation](#timing-actual-yaml)|
|[timing-dbc.yaml](../examples/timing-dbc.yaml)|Rules and pairing using DBC periods|[Tables and explanation](#timing-dbc-yaml)|
|[timing-fixed.yaml](../examples/timing-fixed.yaml)|Rules and pairing using fixed periods|[Tables and explanation](#timing-fixed-yaml)|
|[window-exit-delay.yaml](../examples/window-exit-delay.yaml)|Windows around events|[Tables and explanation](#window-exit-delay-yaml)|
|[window-merged.yaml](../examples/window-merged.yaml)|Windows around events|[Tables and explanation](#window-merged-yaml)|
|[window-minimal.yaml](../examples/window-minimal.yaml)|Windows around events|[Tables and explanation](#window-minimal-yaml)|

<a id="activity-yaml"></a>
## activity.yaml

Purpose: Events, windows, and their energy. Configuration: [Download](../examples/activity.yaml); guide: [Read the chapter](activity-tutorial.md).

```powershell
chronaxis run activity.yaml --output result-activity-yaml
```

Why these results: Temperature reaches 80°C at 1 s, is confirmed after two continuous seconds at 3 s, and clears at 6 s. Activity [1,6) lasts 5 s: 10 W × 5 s = 50 J. Adding 1 s on each side gives window [0,7): 10 W × 7 s = 70 J.

[Run status and table list](../examples/results/activity-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/activity-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | event_energy（J） | event_energy：状态 | event_energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | hot | 1 | 3 | 6 | 正常结束 | — | 50.0 | 完整 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/activity-yaml/窗口结果.csv) (1 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 | context_energy（J） | context_energy：状态 | context_energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | hot_context | 0 | 7 | 完整 | 1 | — | 70.0 | 完整 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="analysis-imports-yaml"></a>
## analysis-imports.yaml

Purpose: Energy, averages, and source reading. Configuration: [Download](../examples/analysis-imports.yaml); guide: [Read the chapter](quickstart.md).

```powershell
chronaxis run analysis-imports.yaml --output result-analysis-imports-yaml
```

Why these results: Power 2, 4, 8, and 10 W lasts 1, 2, 1, and 2 seconds: 2×1 + 4×2 + 8×1 + 10×2 = 38 J. The four-update sample mean is 6 W; the time-weighted mean is 38/6 W. Derived double_power doubles power, so double_energy is 76 J.

[Run status and table list](../examples/results/analysis-imports-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/analysis-imports-yaml/会话结果.csv) (1 rows)**

| double_energy（J） | double_energy：状态 | double_energy：说明 | energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 76.0 | 完整 | — | 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="analysis-json"></a>
## analysis.json

Purpose: Energy, averages, and source reading. Configuration: [Download](../examples/analysis.json); guide: [Read the chapter](quickstart.md).

```powershell
chronaxis run analysis.json --output result-analysis-json
```

Why these results: Power 2, 4, 8, and 10 W lasts 1, 2, 1, and 2 seconds: 2×1 + 4×2 + 8×1 + 10×2 = 38 J. The four-update sample mean is 6 W; the time-weighted mean is 38/6 W.

[Run status and table list](../examples/results/analysis-json/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/analysis-json/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="analysis-yaml"></a>
## analysis.yaml

Purpose: Energy, averages, and source reading. Configuration: [Download](../examples/analysis.yaml); guide: [Read the chapter](quickstart.md).

```powershell
chronaxis run analysis.yaml --output result-analysis-yaml
```

Why these results: Power 2, 4, 8, and 10 W lasts 1, 2, 1, and 2 seconds: 2×1 + 4×2 + 8×1 + 10×2 = 38 J. The four-update sample mean is 6 W; the time-weighted mean is 38/6 W.

[Run status and table list](../examples/results/analysis-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/analysis-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="batch-extended-yaml"></a>
## batch-extended.yaml

Purpose: Two independent jobs. Configuration: [Download](../examples/batch-extended.yaml); guide: [Read the chapter](batch.md).

```powershell
chronaxis batch run batch-extended.yaml --output result-batch-extended-yaml
```

Why these results: job_1 runs the main example and obtains 38 J, 6 W, and 38/6 W. job_2 obtains a voltage integral of 13 V·s. The jobs neither concatenate logs nor inherit state.

[Batch status summary](../examples/results/batch-extended-yaml/batch-summary.json). Each job produces its own output:

<a id="job_1"></a>
### job_1

[Run status and table list](../examples/results/batch-extended-yaml/job_1/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/batch-extended-yaml/job_1/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.

<a id="job_2"></a>
### job_2

[Run status and table list](../examples/results/batch-extended-yaml/job_2/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/batch-extended-yaml/job_2/会话结果.csv) (1 rows)**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="batch-minimal-yaml"></a>
## batch-minimal.yaml

Purpose: One independent job. Configuration: [Download](../examples/batch-minimal.yaml); guide: [Read the chapter](batch.md).

```powershell
chronaxis batch run batch-minimal.yaml --output result-batch-minimal-yaml
```

Why these results: job_1 runs batch/energy.yaml independently and obtains 38 J, 6 W, and 38/6 W. Check completed under jobs and the child results.

[Batch status summary](../examples/results/batch-minimal-yaml/batch-summary.json). Each job produces its own output:

<a id="job_1-1"></a>
### job_1

[Run status and table list](../examples/results/batch-minimal-yaml/job_1/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/batch-minimal-yaml/job_1/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="calculation-minimal-yaml"></a>
## calculation-minimal.yaml

Purpose: Power integral. Configuration: [Download](../examples/calculation-minimal.yaml); guide: [Read the chapter](calculations.md).

```powershell
chronaxis run calculation-minimal.yaml --output result-calculation-minimal-yaml
```

Why these results: Power is 10 W from 1 to 4 s and zero otherwise: 10 W × 3 s = 30 J. Only this integral is requested.

[Run status and table list](../examples/results/calculation-minimal-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/calculation-minimal-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 30.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="calculation-operations-yaml"></a>
## calculation-operations.yaml

Purpose: Statistics, integration, and selection. Configuration: [Download](../examples/calculation-operations.yaml); guide: [Read the chapter](calculations.md).

```powershell
chronaxis run calculation-operations.yaml --output result-calculation-operations-yaml
```

Why these results: Power is 0 W at 0 s, 10 W at 1 s, and 0 W at 4 s; observation ends at 5 s. Positive power lasts 3 s, giving 30 J and duration 3 s. Sample mean is (0+10+0)/3 = 10/3 W, while time-weighted mean is 30/5 = 6 W. Minimum and maximum are 0 and 10 W. select retains the three updates. The Wh result is 30/3600.

[Run status and table list](../examples/results/calculation-operations-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/calculation-operations-yaml/会话结果.csv) (1 rows)**

| duration（s） | duration：状态 | duration：说明 | energy_Wh（Wh） | energy_Wh：状态 | energy_Wh：说明 | integral（J） | integral：状态 | integral：说明 | max_time（W） | max_time：状态 | max_time：说明 | min_time（W） | min_time：状态 | min_time：说明 | sample_maximum（W） | sample_maximum：状态 | sample_maximum：说明 | sample_mean（W） | sample_mean：状态 | sample_mean：说明 | sample_minimum（W） | sample_minimum：状态 | sample_minimum：说明 | time_weighted_mean（W） | time_weighted_mean：状态 | time_weighted_mean：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3.0 | 完整 | — | 0.008333333333333333 | 完整 | — | 30.0 | 完整 | — | 10.0 | 完整 | — | 0.0 | 完整 | — | 10.0 | 完整 | — | 3.3333333333333335 | 完整 | — | 0.0 | 完整 | — | 6.0 | 完整 | — |

**Selection results: [Download full 选择结果.csv](../examples/results/calculation-operations-yaml/选择结果.csv) (3 rows)**

| 计算项 | 统计范围 | 所属区间 | 时间（s） | 值 | 单位 | 数值状态 | 选择状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| select | 会话 | — | 0 | 0.0 | W | 有效 | 满足条件 | — |
| select | 会话 | — | 1 | 10.0 | W | 有效 | 满足条件 | — |
| select | 会话 | — | 4 | 0.0 | W | 有效 | 满足条件 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="can-joint-analysis-yaml"></a>
## can-joint-analysis.yaml

Purpose: Combine CAN with an independent current table. Configuration: [Download](../examples/can-joint-analysis.yaml); guide: [Read the chapter](examples.md#can-joint-analysis).

```powershell
chronaxis run can-joint-analysis.yaml --output result-can-joint-analysis-yaml
```

Why these results: CAN voltage 3, 7, and 3 V lasts one second each; the independent current source is 2 A. After alignment, (3+7+3)×2 = 26 J. The shared clock declares the synchronization basis; source names alone do not align time.

[Run status and table list](../examples/results/can-joint-analysis-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/can-joint-analysis-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 26.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="conditional-energy-yaml"></a>
## conditional-energy.yaml

Purpose: Integrate after a sustained condition. Configuration: [Download](../examples/conditional-energy.yaml); guide: [Read the chapter](conditional-energy.md).

```powershell
chronaxis run conditional-energy.yaml --output result-conditional-energy-yaml
```

Why these results: State is 0x2 and current is exactly 10 A, satisfying >=10 A. [0,60) lasts exactly 60 s and is excluded by strict >60s; [61,122) continues across files for 61 s and qualifies. Default onset selects the entire interval: 400 V × 10 A × 61 s / 3600000 = 0.06777777777777777 kWh.

[Run status and table list](../examples/results/conditional-energy-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/conditional-energy-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | 说明 | energy_kwh（kWh） | energy_kwh：状态 | energy_kwh：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | eligible | 61 | 122 | 正常结束 | — | 0.06777777777777777 | 完整 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="continuous-parallel-yaml"></a>
## continuous-parallel.yaml

Purpose: Read multipart logs as one continuous session. Configuration: [Download](../examples/continuous-parallel.yaml); feature: [Guide](continuous-files.md)。

```powershell
chronaxis run continuous-parallel.yaml --output result-continuous-parallel-yaml
```

Why: The session keeps state across files. Holding 2/4/8/10 W for 1/2/1/2 seconds gives 38 J. The time_order example also produces one activity from 0 to 6 seconds, confirmed at 1 second.

[Run status and table inventory](../examples/results/continuous-parallel-yaml/result-summary.json)：`completed`。

**Session results: [Download full 会话结果.csv](../examples/results/continuous-parallel-yaml/会话结果.csv) (1 row)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

This example requests session calculations only; it does not produce event, window, or sequence tables.


<a id="continuous-time-order-yaml"></a>
## continuous-time-order.yaml

Purpose: Read multipart logs as one continuous session. Configuration: [Download](../examples/continuous-time-order.yaml); feature: [Guide](continuous-files.md)。

```powershell
chronaxis run continuous-time-order.yaml --output result-continuous-time-order-yaml
```

Why: The session keeps state across files. Holding 2/4/8/10 W for 1/2/1/2 seconds gives 38 J. The time_order example also produces one activity from 0 to 6 seconds, confirmed at 1 second.

[Run status and table inventory](../examples/results/continuous-time-order-yaml/result-summary.json)：`completed`。

**Event results: [Download full 事件结果.csv](../examples/results/continuous-time-order-yaml/事件结果.csv) (1 row)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | active | 0 | 1 | 6 | 观测结束，活动尚未确认结束 | 数据缺失 |

**Session results: [Download full 会话结果.csv](../examples/results/continuous-time-order-yaml/会话结果.csv) (1 row)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

This example produces event and session tables. It does not request window or sequence tables.


<a id="dual-grid-yaml"></a>
## dual-grid.yaml

Purpose: Original CAN and reconstructed-grid exports. Configuration: [Download](../examples/dual-grid.yaml); guide: [Read the chapter](can-exports.md).

```powershell
chronaxis run dual-grid.yaml --output result-dual-grid-yaml
```

Why these results: The voltage integral remains 3+7+3 = 13 V·s. The 250 ms signal grid has 12 positions; the last three lack a right endpoint. The 500 ms CAN grid generates five frames and skips one point. Read exports and analysis summaries separately; export row count does not define the integration interval.

[Run status and table list](../examples/results/dual-grid-yaml/result-summary.json): `completed`.

[Export manifest exports/export-00000000/manifest.json](../examples/results/dual-grid-yaml/exports/export-00000000/manifest.json).

**resampled: [Download full exports/export-00000000/resampled.csv](../examples/results/dual-grid-yaml/exports/export-00000000/resampled.csv) (12 rows)**

| time_ns | signal | value | unit | status | reason | quality |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | voltage | 3.0 | V | observed | — | 0 |
| 250000000 | voltage | 4.0 | V | estimated | — | 0 |
| 500000000 | voltage | 5.0 | V | estimated | — | 0 |
| 750000000 | voltage | 6.0 | V | estimated | — | 0 |
| 1000000000 | voltage | 7.0 | V | observed | — | 0 |
| 1250000000 | voltage | 6.0 | V | estimated | — | 0 |
| 1500000000 | voltage | 5.0 | V | estimated | — | 0 |
| 1750000000 | voltage | 4.0 | V | estimated | — | 0 |

The table has 12 rows; the first 8 are shown here. Download the file for every row.

[Download exports/export-00000001/frames.asc](../examples/results/dual-grid-yaml/exports/export-00000001/frames.asc) (210 bytes).

[Export manifest exports/export-00000001/manifest.json](../examples/results/dual-grid-yaml/exports/export-00000001/manifest.json): frames=5, generated=5, passthrough=0, skipped_grid_points=1.

[Download exports.jsonl](../examples/results/dual-grid-yaml/exports.jsonl) (518 bytes).

**Session results: [Download full 会话结果.csv](../examples/results/dual-grid-yaml/会话结果.csv) (1 rows)**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="execution-comparison-json"></a>
## execution-comparison.json

Purpose: Insufficient observation. Configuration: [Download](../examples/execution-comparison.json); guide: [Read the chapter](execution.md).

```powershell
chronaxis run execution-comparison.json --output result-execution-comparison-json
```

Why these results: The request is [0,12) s, but observation ends at 8 s with power 4000 W. The known portion is 4000×8 = 32000 J. report returns 32000 and partial; strict returns an empty value and indeterminate. The final four seconds are not filled with zero. The combined case also gives 4000 J for each of two events and 24000 J for the merged window.

[Run status and table list](../examples/results/execution-comparison-json/result-summary.json): `completed`.

**计算: [Download full calculations.csv](../examples/results/execution-comparison-json/calculations.csv) (4 rows)**

| calculation_id | operation | scope | value | unit | status | reason | quality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| event_energy | integral | event | 4000.0 | J | complete | ok | 0 |
| event_energy | integral | event | 4000.0 | J | complete | ok | 0 |
| segment_energy | integral | segment | 24000.0 | J | complete | ok | 0 |
| session_energy | integral | session | 32000.0 | J | partial | partial_coverage | 0 |

**事件: [Download full events.csv](../examples/results/execution-comparison-json/events.csv) (2 rows)**

| rule_id | start_ns | confirmed_ns | end_ns | status | quality |
| --- | --- | --- | --- | --- | --- |
| working | 0 | 0 | 1000000000 | closed | 0 |
| working | 2000000000 | 2000000000 | 3000000000 | closed | 0 |

**窗口: [Download full segments.csv](../examples/results/execution-comparison-json/segments.csv) (1 rows)**

| window_id | start_ns | end_ns | status |
| --- | --- | --- | --- |
| context | 0 | 6000000000 | complete |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="execution-diagnostics-yaml"></a>
## execution-diagnostics.yaml

Purpose: Explicit input tracing. Configuration: [Download](../examples/execution-diagnostics.yaml); guide: [Read the chapter](execution.md).

```powershell
chronaxis run execution-diagnostics.yaml --output result-execution-diagnostics-yaml
```

Why these results: Power 10 W lasts 3 s, giving 30 J. This example explicitly enables diagnostics.trace and includes 输入追溯.csv (input trace) for the required records; ordinary examples do not. Small batches demonstrate execution settings without changing the result.

[Run status and table list](../examples/results/execution-diagnostics-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/execution-diagnostics-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 30.0 | 完整 | — |

**Input trace: [Download full 输入追溯.csv](../examples/results/execution-diagnostics-yaml/输入追溯.csv) (3 rows)**

| 来源 | 原记录序号 | 时间（s） | 记录类型 | 输入位置 | 字段值 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| source_1 | 1 | 0 | 解码报文 | can:0:256:0:0 | {"Power":0.0} | — |
| source_1 | 2 | 1 | 解码报文 | can:0:256:0:0 | {"Power":10.0} | — |
| source_1 | 3 | 4 | 解码报文 | can:0:256:0:0 | {"Power":0.0} | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="execution-report-yaml"></a>
## execution-report.yaml

Purpose: Retain values for the known portion. Configuration: [Download](../examples/execution-report.yaml); guide: [Read the chapter](execution.md).

```powershell
chronaxis run execution-report.yaml --output result-execution-report-yaml
```

Why these results: The request is [0,12), but only 8 s are observed: 4000 W × 8 s = 32000 J. report retains 32000 with partial status; the unobserved four seconds are not filled with zero.

[Run status and table list](../examples/results/execution-report-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/execution-report-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 32000.0 | 部分有效 | 仅统计有效部分 |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="execution-strict-yaml"></a>
## execution-strict.yaml

Purpose: Reject incomplete values. Configuration: [Download](../examples/execution-strict.yaml); guide: [Read the chapter](execution.md).

```powershell
chronaxis run execution-strict.yaml --output result-execution-strict-yaml
```

Why these results: The request is [0,12), but only 8 s are observed. Although the known portion is 32000 J, strict leaves the requested full-range value empty with indeterminate status, avoiding presentation of a partial value as the full result.

[Run status and table list](../examples/results/execution-strict-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/execution-strict-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| — | 无法确定 | 有效数据不足 |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="export-can-all-windows-yaml"></a>
## export-can-all-windows.yaml

Purpose: Separate export for every window. Configuration: [Download](../examples/export-can-all-windows.yaml); guide: [Read the chapter](can-exports.md).

```powershell
chronaxis run export-can-all-windows.yaml --output result-export-can-all-windows-yaml
```

Why these results: Voltage exceeds 5 V over [1,2). The active window exports one frame at 1 s; before extends one second earlier and exports frames at 0 and 1 s over [0,2). The two files are separate windows; their combined frame count is not the integral sample count.

[Run status and table list](../examples/results/export-can-all-windows-yaml/result-summary.json): `completed`.

[Download exports/export-00000000/frames.asc](../examples/results/export-can-all-windows-yaml/exports/export-00000000/frames.asc) (86 bytes).

[Export manifest exports/export-00000000/manifest.json](../examples/results/export-can-all-windows-yaml/exports/export-00000000/manifest.json): frames=1, generated=0, passthrough=1, skipped_grid_points=0.

[Download exports/export-00000001/frames.asc](../examples/results/export-can-all-windows-yaml/exports/export-00000001/frames.asc) (117 bytes).

[Export manifest exports/export-00000001/manifest.json](../examples/results/export-can-all-windows-yaml/exports/export-00000001/manifest.json): frames=2, generated=0, passthrough=2, skipped_grid_points=0.

[Download exports.jsonl](../examples/results/export-can-all-windows-yaml/exports.jsonl) (648 bytes).

**Event results: [Download full 事件结果.csv](../examples/results/export-can-all-windows-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | high | 1 | 1 | 2 | 正常结束 | — |

**Session results: [Download full 会话结果.csv](../examples/results/export-can-all-windows-yaml/会话结果.csv) (1 rows)**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/export-can-all-windows-yaml/窗口结果.csv) (2 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | active | 1 | 2 | 完整 | 1 | — |
| 2 | before | 0 | 2 | 完整 | 1 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="export-can-grid-yaml"></a>
## export-can-grid.yaml

Purpose: Regular CAN reconstruction. Configuration: [Download](../examples/export-can-grid.yaml); guide: [Read the chapter](can-exports.md).

```powershell
chronaxis run export-can-grid.yaml --output result-export-can-grid-yaml
```

Why these results: The voltage integral remains 13 V·s. The 500 ms grid produces five frames at 0, 0.5, 1, 1.5, and 2 s. The 2.5 s point lacks an in-range right update and is skipped, not extrapolated.

[Run status and table list](../examples/results/export-can-grid-yaml/result-summary.json): `completed`.

[Download exports/export-00000000/frames.asc](../examples/results/export-can-grid-yaml/exports/export-00000000/frames.asc) (210 bytes).

[Export manifest exports/export-00000000/manifest.json](../examples/results/export-can-grid-yaml/exports/export-00000000/manifest.json): frames=5, generated=5, passthrough=0, skipped_grid_points=1.

[Download exports.jsonl](../examples/results/export-can-grid-yaml/exports.jsonl) (258 bytes).

**Session results: [Download full 会话结果.csv](../examples/results/export-can-grid-yaml/会话结果.csv) (1 rows)**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="export-can-minimal-yaml"></a>
## export-can-minimal.yaml

Purpose: Original frame export. Configuration: [Download](../examples/export-can-minimal.yaml); guide: [Read the chapter](can-exports.md).

```powershell
chronaxis run export-can-minimal.yaml --output result-export-can-minimal-yaml
```

Why these results: The voltage integral is 3+7+3 = 13 V·s. Export contains three original frames at 0, 1, and 2 s in [0,3); the excluded 3 s endpoint is not exported. No resampling means no intermediate frames.

[Run status and table list](../examples/results/export-can-minimal-yaml/result-summary.json): `completed`.

[Download exports/export-00000000/frames.asc](../examples/results/export-can-minimal-yaml/exports/export-00000000/frames.asc) (148 bytes).

[Export manifest exports/export-00000000/manifest.json](../examples/results/export-can-minimal-yaml/exports/export-00000000/manifest.json): frames=3, generated=0, passthrough=3, skipped_grid_points=0.

[Download exports.jsonl](../examples/results/export-can-minimal-yaml/exports.jsonl) (257 bytes).

**Session results: [Download full 会话结果.csv](../examples/results/export-can-minimal-yaml/会话结果.csv) (1 rows)**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="export-signal-grid-yaml"></a>
## export-signal-grid.yaml

Purpose: Regular signal export. Configuration: [Download](../examples/export-signal-grid.yaml); guide: [Read the chapter](signal-exports.md).

```powershell
chronaxis run export-signal-grid.yaml --output result-export-signal-grid-yaml
```

Why these results: The integral remains 38 J. The 500 ms grid has 12 rows: four actual updates, five linearly estimated values, and three missing values at 4.5, 5, and 5.5 s because a right update is absent.

[Run status and table list](../examples/results/export-signal-grid-yaml/result-summary.json): `completed`.

[Export manifest exports/export-00000000/manifest.json](../examples/results/export-signal-grid-yaml/exports/export-00000000/manifest.json).

**resampled: [Download full exports/export-00000000/resampled.csv](../examples/results/export-signal-grid-yaml/exports/export-00000000/resampled.csv) (12 rows)**

| time_ns | signal | value | unit | status | reason | quality |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | power | 2.0 | W | observed | — | 0 |
| 500000000 | power | 3.0 | W | estimated | — | 0 |
| 1000000000 | power | 4.0 | W | observed | — | 0 |
| 1500000000 | power | 5.0 | W | estimated | — | 0 |
| 2000000000 | power | 6.0 | W | estimated | — | 0 |
| 2500000000 | power | 7.0 | W | estimated | — | 0 |
| 3000000000 | power | 8.0 | W | observed | — | 0 |
| 3500000000 | power | 9.0 | W | estimated | — | 0 |

The table has 12 rows; the first 8 are shown here. Download the file for every row.

[Download exports.jsonl](../examples/results/export-signal-grid-yaml/exports.jsonl) (260 bytes).

**Session results: [Download full 会话结果.csv](../examples/results/export-signal-grid-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="export-signal-minimal-yaml"></a>
## export-signal-minimal.yaml

Purpose: Original signal updates. Configuration: [Download](../examples/export-signal-minimal.yaml); guide: [Read the chapter](signal-exports.md).

```powershell
chronaxis run export-signal-minimal.yaml --output result-export-signal-minimal-yaml
```

Why these results: The integral remains 38 J. original.csv retains the four power updates at 0, 1, 3, and 4 s. No resampling means no intermediate timestamps.

[Run status and table list](../examples/results/export-signal-minimal-yaml/result-summary.json): `completed`.

[Export manifest exports/export-00000000/manifest.json](../examples/results/export-signal-minimal-yaml/exports/export-00000000/manifest.json).

**original: [Download full exports/export-00000000/original.csv](../examples/results/export-signal-minimal-yaml/exports/export-00000000/original.csv) (4 rows)**

| time_ns | signal | value | unit | quality |
| --- | --- | --- | --- | --- |
| 0 | power | 2.0 | W | 0 |
| 1000000000 | power | 4.0 | W | 0 |
| 3000000000 | power | 8.0 | W | 0 |
| 4000000000 | power | 10.0 | W | 0 |

[Download exports.jsonl](../examples/results/export-signal-minimal-yaml/exports.jsonl) (259 bytes).

**Session results: [Download full 会话结果.csv](../examples/results/export-signal-minimal-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="expression-extended-yaml"></a>
## expression-extended.yaml

Purpose: Derived power integral within an event. Configuration: [Download](../examples/expression-extended.yaml); guide: [Read the chapter](expressions.md).

```powershell
chronaxis run expression-extended.yaml --output result-expression-extended-yaml
```

Why these results: 400 V × 10 A gives 4000 W. Integrating over the four seconds selected by the working event gives 4000×4 = 16000 J.

[Run status and table list](../examples/results/expression-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/expression-extended-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | 说明 | energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | working | 0 | 4 | 观测结束，活动尚未确认结束 | 数据缺失 | 16000.0 | 完整 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="expression-minimal-yaml"></a>
## expression-minimal.yaml

Purpose: Maximum derived power. Configuration: [Download](../examples/expression-minimal.yaml); guide: [Read the chapter](expressions.md).

```powershell
chronaxis run expression-minimal.yaml --output result-expression-minimal-yaml
```

Why these results: voltage * current defines power: 400 V × 10 A = 4000 W. The derived-power sample maximum is 4000 W.

[Run status and table list](../examples/results/expression-minimal-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/expression-minimal-yaml/会话结果.csv) (1 rows)**

| maximum_power（W） | maximum_power：状态 | maximum_power：说明 |
| --- | --- | --- |
| 4000.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="input-asc-minimal-yaml"></a>
## input-asc-minimal.yaml

Purpose: ASC messages and DBC decoding. Configuration: [Download](../examples/input-asc-minimal.yaml); guide: [Read the chapter](inputs.md).

```powershell
chronaxis run input-asc-minimal.yaml --output result-input-asc-minimal-yaml
```

Why these results: Three ASC target frames have raw codes 1, 3, and 1. The DBC converts them to 3, 7, and 3 V, held one second each: 3+7+3 = 13 V·s.

[Run status and table list](../examples/results/input-asc-minimal-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/input-asc-minimal-yaml/会话结果.csv) (1 rows)**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="input-can-directory-yaml"></a>
## input-can-directory.yaml

Purpose: Energy, averages, and source reading. Configuration: [Download](../examples/input-can-directory.yaml); guide: [Read the chapter](quickstart.md).

```powershell
chronaxis run input-can-directory.yaml --output result-input-can-directory-yaml
```

Why these results: Power 2, 4, 8, and 10 W lasts 1, 2, 1, and 2 seconds: 2×1 + 4×2 + 8×1 + 10×2 = 38 J. The four-update sample mean is 6 W; the time-weighted mean is 38/6 W.

[Run status and table list](../examples/results/input-can-directory-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/input-can-directory-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 | sample_average（W） | sample_average：状态 | sample_average：说明 | time_average（W） | time_average：状态 | time_average：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38.0 | 完整 | — | 6.0 | 完整 | — | 6.333333333333333 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="input-csv-minimal-yaml"></a>
## input-csv-minimal.yaml

Purpose: CSV power integral. Configuration: [Download](../examples/input-csv-minimal.yaml); guide: [Read the chapter](inputs.md).

```powershell
chronaxis run input-csv-minimal.yaml --output result-input-csv-minimal-yaml
```

Why these results: Power updates 2, 4, 8, and 10 W last 1, 2, 1, and 2 seconds, giving 38 J. This example requests only the integral, not averages.

[Run status and table list](../examples/results/input-csv-minimal-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/input-csv-minimal-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="input-csv-offset-yaml"></a>
## input-csv-offset.yaml

Purpose: CSV time alignment. Configuration: [Download](../examples/input-csv-offset.yaml); guide: [Read the chapter](inputs.md).

```powershell
chronaxis run input-csv-offset.yaml --output result-input-csv-offset-yaml
```

Why these results: The fixed configured offset aligns CSV timestamps with the analysis clock. Power still lasts 1, 2, 1, and 2 seconds, giving 38 J.

[Run status and table list](../examples/results/input-csv-offset-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/input-csv-offset-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 38.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="input-memory-minimal-yaml"></a>
## input-memory-minimal.yaml

Purpose: Memory API input. Configuration: [Download](../examples/input-memory-minimal.yaml); guide: [Read the chapter](inputs.md).

```powershell
chronaxis run input-memory-minimal.yaml --output result-input-memory-minimal-yaml
```

Why these results: Memory records contain 2 W then 4 W, each for one second: 2×1 + 4×1 = 6 J. This example demonstrates memory records rather than the usual log-reading entry point.

[Run status and table list](../examples/results/input-memory-minimal-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/input-memory-minimal-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 6.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="input-raw-csv-mapping-yaml"></a>
## input-raw-csv-mapping.yaml

Purpose: Raw message reading and DBC decoding. Configuration: [Download](../examples/input-raw-csv-mapping.yaml); guide: [Read the chapter](inputs.md).

```powershell
chronaxis run input-raw-csv-mapping.yaml --output result-input-raw-csv-mapping-yaml
```

Why these results: The DBC converts raw codes 1, 3, and 1 to 3, 7, and 3 V for one second each: 3+7+3 = 13 V·s. Raw CSV column mapping changes field reading, not decoding or calculation.

[Run status and table list](../examples/results/input-raw-csv-mapping-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/input-raw-csv-mapping-yaml/会话结果.csv) (1 rows)**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="input-raw-csv-minimal-yaml"></a>
## input-raw-csv-minimal.yaml

Purpose: Raw message reading and DBC decoding. Configuration: [Download](../examples/input-raw-csv-minimal.yaml); guide: [Read the chapter](inputs.md).

```powershell
chronaxis run input-raw-csv-minimal.yaml --output result-input-raw-csv-minimal-yaml
```

Why these results: The DBC converts raw codes 1, 3, and 1 to 3, 7, and 3 V for one second each: 3+7+3 = 13 V·s. Raw CSV column mapping changes field reading, not decoding or calculation.

[Run status and table list](../examples/results/input-raw-csv-minimal-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/input-raw-csv-minimal-yaml/会话结果.csv) (1 rows)**

| voltage_area（V*s） | voltage_area：状态 | voltage_area：说明 |
| --- | --- | --- |
| 13.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="interval-actual-yaml"></a>
## interval-actual.yaml

Purpose: Integrate using actual intervals. Configuration: [Download](../examples/interval-actual.yaml); guide: [Read the chapter](intervals.md).

```powershell
chronaxis run interval-actual.yaml --output result-interval-actual-yaml
```

Why these results: 4000 W updates at 0, 0.12, and 0.30 s. The actual intervals are 0.12 and 0.18 s, totaling 0.30 s: 4000×0.30 = 1200 J.

[Run status and table list](../examples/results/interval-actual-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/interval-actual-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 1200.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="interval-fixed-yaml"></a>
## interval-fixed.yaml

Purpose: Integrate using fixed periods. Configuration: [Download](../examples/interval-fixed.yaml); guide: [Read the chapter](intervals.md).

```powershell
chronaxis run interval-fixed.yaml --output result-interval-fixed-yaml
```

Why these results: Records remain at 0, 0.12, and 0.30 s, but each of the two calculation intervals uses the configured 0.1 s, totaling 0.20 s: 4000×0.20 = 800 J. Original timestamps are unchanged.

[Run status and table list](../examples/results/interval-fixed-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/interval-fixed-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 800.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="lookup-power-yaml"></a>
## lookup-power.yaml

Purpose: Average power after a voltage lookup. Configuration: [Download](../examples/lookup-power.yaml); guide: [Read the chapter](expressions.md).

```powershell
chronaxis run lookup-power.yaml --output result-lookup-power-yaml
```

Why these results: Three voltage readings are 3, 7, and 3 V. The calibration table maps 3 V to 10 W and 11 V to 50 W; linear interpolation maps 7 V to 30 W. The sample mean power is therefore (10 + 30 + 10) / 3 = 50/3 W, approximately 16.67 W.

[Run status and table list](../examples/results/lookup-power-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/lookup-power-yaml/会话结果.csv) (1 row)**

| rated_power（W） | rated_power：状态 | rated_power：说明 |
| --- | --- | --- |
| 16.666666666666668 | 完整 | — |

No event, window, or request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="message-directions-yaml"></a>
## message-directions.yaml

Purpose: Accumulate messages by direction. Configuration: [Download](../examples/message-directions.yaml); guide: [Read the chapter](message-calculations.md).

```powershell
chronaxis run message-directions.yaml --output result-message-directions-yaml
```

Why these results: Three 4000 W messages occur in [0,3). At 0 s, direction 1 contributes 400 J only to positive_energy; at 1 s, direction -1 contributes 400 J only to negative_energy; direction 0 at 2 s contributes to neither. Each contribution is 4000 W × 0.1 s. Both calculations check three messages, giving six contribution evaluations: two contributed and four condition_false. Each total is 400 J. The 3 s record is at the excluded endpoint.

[Run status and table list](../examples/results/message-directions-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/message-directions-yaml/会话结果.csv) (1 rows)**

| negative_energy（J） | negative_energy：状态 | negative_energy：说明 | positive_energy（J） | positive_energy：状态 | positive_energy：说明 |
| --- | --- | --- | --- | --- | --- |
| 400.0 | 完整 | — | 400.0 | 完整 | — |

**Contribution details: [Download full 贡献明细.csv](../examples/results/message-directions-yaml/贡献明细.csv) (6 rows)**

| 计算项 | 来源 | 原记录序号 | 求值序号 | 贡献值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| negative_energy | source_1 | 0 | 0 | — | 不满足条件，已跳过 |
| negative_energy | source_1 | 1 | 1 | 400.0 | 已计入 |
| negative_energy | source_1 | 2 | 2 | — | 不满足条件，已跳过 |
| positive_energy | source_1 | 0 | 0 | 400.0 | 已计入 |
| positive_energy | source_1 | 1 | 1 | — | 不满足条件，已跳过 |
| positive_energy | source_1 | 2 | 2 | — | 不满足条件，已跳过 |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="message-energy-yaml"></a>
## message-energy.yaml

Purpose: Per-message accumulation. Configuration: [Download](../examples/message-energy.yaml); guide: [Read the chapter](message-calculations.md).

```powershell
chronaxis run message-energy.yaml --output result-message-energy-yaml
```

Why these results: Each complete message contributes 4000 W × 0.1 s = 400 J. Two messages total 800 J even at the same timestamp. Missing current-message input is not replaced by an old value. Full contributions contain two 400 J rows and one skipped missing_input row.

[Run status and table list](../examples/results/message-energy-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/message-energy-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 800.0 | 部分有效 | 输入仅部分有效；数据缺失 |

**Contribution details: [Download full 贡献明细.csv](../examples/results/message-energy-yaml/贡献明细.csv) (3 rows)**

| 计算项 | 来源 | 原记录序号 | 求值序号 | 贡献值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| energy | source_1 | 0 | 0 | 400.0 | 已计入 |
| energy | source_1 | 1 | 1 | 400.0 | 已计入 |
| energy | source_1 | 2 | 2 | — | 缺少计算输入；数据缺失 |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="message-minimal-yaml"></a>
## message-minimal.yaml

Purpose: Per-message accumulation. Configuration: [Download](../examples/message-minimal.yaml); guide: [Read the chapter](message-calculations.md).

```powershell
chronaxis run message-minimal.yaml --output result-message-minimal-yaml
```

Why these results: Each complete message contributes 4000 W × 0.1 s = 400 J. Two messages total 800 J even at the same timestamp. Missing current-message input is not replaced by an old value.

[Run status and table list](../examples/results/message-minimal-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/message-minimal-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 800.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="power-statistics-yaml"></a>
## power-statistics.yaml

Purpose: Power variation and the P95 of loaded-period means. Configuration: [Download](../examples/power-statistics.yaml); guide: [Read the chapter](calculations.md#v4-power-statistics).

```powershell
chronaxis run power-statistics.yaml --output result-power-statistics-yaml
```

Why these results: The five readings are 0, 10, 0, 20, and 0 W. Their mean is 6 W and their sum of squared deviations is 320 W². Dividing by four gives a sample variance of 80 W²; the population standard deviation is 8 W. Values 0, 10, and 20 W are held for four, three, and two seconds, respectively, giving a time-weighted RMS of √(1100/9) W. The P95 of the sorted readings is 18 W. The two loaded intervals, [1,4) and [5,7) seconds, have means of 10 and 20 W; their P95 is 19.5 W, with two candidates and two contributing values. See the statistics guide for hand calculations of the other counts, variance, and median.

[Run status and table list](../examples/results/power-statistics-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/power-statistics-yaml/事件结果.csv) (4 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | load_mean（W） | load_mean：状态 | load_mean：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | load_start | 1 | 1 | — | 瞬时事件 | — | — | 无此项结果 | — |
| 2 | load_start | 5 | 5 | — | 瞬时事件 | — | — | 无此项结果 | — |
| 3 | loaded | 1 | 1 | 4 | 正常结束 | — | 10.0 | 完整 | — |
| 4 | loaded | 5 | 5 | 7 | 正常结束 | — | 20.0 | 完整 | — |

**Session results: [Download full 会话结果.csv](../examples/results/power-statistics-yaml/会话结果.csv) (1 row)**

| cycles（1） | cycles：状态 | cycles：说明 | held_rms（W） | held_rms：状态 | held_rms：说明 | held_spread（W） | held_spread：状态 | held_spread：说明 | held_variance（W^2） | held_variance：状态 | held_variance：说明 | loads（1） | loads：状态 | loads：说明 | reading_median（W） | reading_median：状态 | reading_median：说明 | reading_p95（W） | reading_p95：状态 | reading_p95：说明 | reading_rms（W） | reading_rms：状态 | reading_rms：说明 | reading_spread（W） | reading_spread：状态 | reading_spread：说明 | reading_variance（W^2） | reading_variance：状态 | reading_variance：说明 | readings（1） | readings：状态 | readings：说明 | starts（1） | starts：状态 | starts：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 完整 | — | 11.055415967851332 | 完整 | — | 7.85674201318386 | 完整 | — | 61.72839506172837 | 完整 | — | 2 | 完整 | — | 0.0 | 完整 | — | 18.0 | 完整 | — | 10.0 | 完整 | — | 8.000000000000002 | 完整 | — | 80.00000000000004 | 完整 | — | 5 | 完整 | — | 2 | 完整 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/power-statistics-yaml/窗口结果.csv) (1 row)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | test_cycle | 1 | 8.5 | 完整 | 3、4 | — |

**Aggregation results: [Download full 聚合结果.csv](../examples/results/power-statistics-yaml/聚合结果.csv) (1 row)**

| 聚合项 | 分组 | 结果 | 单位 | 状态 | 原因 | 候选数 | 参与数 | 定义排除数 | 质量排除数 | 参与的部分值 | 匹配 | 确认超时 | 观测不足 | 未决 | 已完整发现总体 | 质量说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| load_mean_p95 | {"session_id":"power_bench"} | 19.5 | W | 完整 | 正常 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 是 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-charge-energy-yaml"></a>
## preset-charge-energy.yaml

Purpose: Charging activity and accumulated quantities. Configuration: [Download](../examples/preset-charge-energy.yaml); guide: [Read the chapter](presets.md).

```powershell
chronaxis run preset-charge-energy.yaml --output result-preset-charge-energy-yaml
```

Why these results: Charging [1,3) lasts 2 s: 400 V × 10 A × 2 s = 8000 J = 8000/3600 Wh; 10 A × 2 s = 20 A·s = 20/3600 Ah.

[Run status and table list](../examples/results/preset-charge-energy-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/preset-charge-energy-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | 说明 | demo_preset_charge（Ah） | demo_preset_charge：状态 | demo_preset_charge：说明 | demo_preset_energy（Wh） | demo_preset_energy：状态 | demo_preset_energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1 | 3 | 正常结束 | — | 0.005555555555555556 | 完整 | — | 2.2222222222222223 | 完整 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-charge-minimal-yaml"></a>
## preset-charge-minimal.yaml

Purpose: Charging activity detection. Configuration: [Download](../examples/preset-charge-minimal.yaml); guide: [Read the chapter](presets.md).

```powershell
chronaxis run preset-charge-minimal.yaml --output result-preset-charge-minimal-yaml
```

Why these results: Current and mode meet the configured condition, producing activity [1,3) s. No energy or charge calculation is requested.

[Run status and table list](../examples/results/preset-charge-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/preset-charge-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1 | 1 | 3 | 正常结束 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-command-automatic-yaml"></a>
## preset-command-automatic.yaml

Purpose: Request/response pairing. Configuration: [Download](../examples/preset-command-automatic.yaml); guide: [Read the chapter](sequences.md).

```powershell
chronaxis run preset-command-automatic.yaml --output result-preset-command-automatic-yaml
```

Why these results: The start edge and response edge are 1 s apart, within the allowed wait. Pairing succeeds with delay_ns=1000000000. Read pairing status and 延迟（s） (delay in seconds) in 配对结果.csv; pairing uses the configured request and response rules.

[Run status and table list](../examples/results/preset-command-automatic-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/preset-command-automatic-yaml/事件结果.csv) (2 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_request | 1 | 1 | — | 瞬时事件 | — |
| 2 | demo_preset_response | 2 | 2 | — | 瞬时事件 | — |

**Pairing results: [Download full 配对结果.csv](../examples/results/preset-command-automatic-yaml/配对结果.csv) (1 rows)**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_pair | 1 | 2 | 2 | 1 | 已响应 | — |

No window table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-command-minimal-yaml"></a>
## preset-command-minimal.yaml

Purpose: Request/response pairing. Configuration: [Download](../examples/preset-command-minimal.yaml); guide: [Read the chapter](sequences.md).

```powershell
chronaxis run preset-command-minimal.yaml --output result-preset-command-minimal-yaml
```

Why these results: The start edge and response edge are 1 s apart, within the allowed wait. Pairing succeeds with delay_ns=1000000000. Read pairing status and 延迟（s） (delay in seconds) in 配对结果.csv; pairing uses the configured request and response rules.

[Run status and table list](../examples/results/preset-command-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/preset-command-minimal-yaml/事件结果.csv) (2 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_request | 1 | 1 | — | 瞬时事件 | — |
| 2 | demo_preset_response | 2 | 2 | — | 瞬时事件 | — |

**Pairing results: [Download full 配对结果.csv](../examples/results/preset-command-minimal-yaml/配对结果.csv) (1 rows)**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_pair | 1 | 2 | 2 | 1 | 已响应 | — |

No window table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-fault-context-yaml"></a>
## preset-fault-context.yaml

Purpose: Window around an alarm. Configuration: [Download](../examples/preset-fault-context.yaml); guide: [Read the chapter](presets.md).

```powershell
chronaxis run preset-fault-context.yaml --output result-preset-fault-context-yaml
```

Why these results: The alarm rising edge at 1 s produces a point event. pre=1s and post=2s create window [0,3); this does not extend the actual alarm activity.

[Run status and table list](../examples/results/preset-fault-context-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/preset-fault-context-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_alarm | 1 | 1 | — | 瞬时事件 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/preset-fault-context-yaml/窗口结果.csv) (1 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_context | 0 | 3 | 完整 | 1 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-fault-minimal-yaml"></a>
## preset-fault-minimal.yaml

Purpose: Window after an alarm point. Configuration: [Download](../examples/preset-fault-minimal.yaml); guide: [Read the chapter](presets.md).

```powershell
chronaxis run preset-fault-minimal.yaml --output result-preset-fault-minimal-yaml
```

Why these results: The alarm rising edge at 1 s produces a point event with empty end_ns. pre=0s and post=1s create window [1,2); window length is not alarm duration.

[Run status and table list](../examples/results/preset-fault-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/preset-fault-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_alarm | 1 | 1 | — | 瞬时事件 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/preset-fault-minimal-yaml/窗口结果.csv) (1 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_context | 1 | 2 | 完整 | 1 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-threshold-delay-yaml"></a>
## preset-threshold-delay.yaml

Purpose: Alarm after confirmation waits. Configuration: [Download](../examples/preset-threshold-delay.yaml); guide: [Read the chapter](presets.md).

```powershell
chronaxis run preset-threshold-delay.yaml --output result-preset-threshold-delay-yaml
```

Why these results: Entry and exit both need 500 ms confirmation. Activity [1.5,3.5) totals 2 s. Initial state is still waiting for exit confirmation, so the overall summary is partial.

[Run status and table list](../examples/results/preset-threshold-delay-yaml/result-summary.json): `completed`.

Session summary for the threshold preset:

| Preset | Accumulated seconds | Status |
|---|---|---|
|demo_preset|2.0|partial|

**Event results: [Download full 事件结果.csv](../examples/results/preset-threshold-delay-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | demo_preset_duration（s） | demo_preset_duration：状态 | demo_preset_duration：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1.5 | 1.5 | 3.5 | 正常结束 | — | 2.0 | 完整 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-threshold-minimal-yaml"></a>
## preset-threshold-minimal.yaml

Purpose: Hysteresis alarm duration. Configuration: [Download](../examples/preset-threshold-minimal.yaml); guide: [Read the chapter](presets.md).

```powershell
chronaxis run preset-threshold-minimal.yaml --output result-preset-threshold-minimal-yaml
```

Why these results: Temperature reaches 80°C at 1 s to enter alarm, and 75°C at 3 s to exit. Activity [1,3) totals 2 s.

[Run status and table list](../examples/results/preset-threshold-minimal-yaml/result-summary.json): `completed`.

Session summary for the threshold preset:

| Preset | Accumulated seconds | Status |
|---|---|---|
|demo_preset|2.0|complete|

**Event results: [Download full 事件结果.csv](../examples/results/preset-threshold-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | demo_preset_duration（s） | demo_preset_duration：状态 | demo_preset_duration：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1 | 1 | 3 | 正常结束 | — | 2.0 | 完整 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="preset-threshold-partial-yaml"></a>
## preset-threshold-partial.yaml

Purpose: Alarm with unknown initial state. Configuration: [Download](../examples/preset-threshold-partial.yaml); guide: [Read the chapter](presets.md).

```powershell
chronaxis run preset-threshold-partial.yaml --output result-preset-threshold-partial-yaml
```

Why these results: The first temperature lies between entry and exit thresholds, so the initial state is unknown. Alarm [1,3) can be confirmed for 2 s; the overall summary is partial.

[Run status and table list](../examples/results/preset-threshold-partial-yaml/result-summary.json): `completed`.

Session summary for the threshold preset:

| Preset | Accumulated seconds | Status |
|---|---|---|
|demo_preset|2.0|partial|

**Event results: [Download full 事件结果.csv](../examples/results/preset-threshold-partial-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | demo_preset_duration（s） | demo_preset_duration：状态 | demo_preset_duration：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | demo_preset_activity | 1 | 1 | 3 | 正常结束 | — | 2.0 | 完整 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="quality-yaml"></a>
## quality.yaml

Purpose: Invalid codes and expiry. Configuration: [Download](../examples/quality.yaml); guide: [Read the chapter](results.md).

```powershell
chronaxis run quality.yaml --output result-quality-yaml
```

Why these results: Power is 10 W at 0 s, an explicit invalid code at 1 s, and 10 W again at 2 s. Validity is 1 s and observation ends at 4 s. Only [0,1) and [2,3) are valid: 10×1 + 10×1 = 20 J. quality=18 combines OUT_OF_RANGE (16) for the invalid code with STALE (2) for expiry. partial means the 20 J covers only known data.

[Run status and table list](../examples/results/quality-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/quality-yaml/会话结果.csv) (1 rows)**

| energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- |
| 20.0 | 部分有效 | 仅统计有效部分；数据过期；数值超出允许范围 |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-condition_duration-extended-yaml"></a>
## rule-condition_duration-extended.yaml

Purpose: Event rule: condition_duration. Configuration: [Download](../examples/rule-condition_duration-extended.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-condition_duration-extended.yaml --output result-rule-condition_duration-extended-yaml
```

Why these results: Activity remains [1,6), but selection_origin=confirmed starts calculation at 3 s: 10 W × 3 s = 30 J.

[Run status and table list](../examples/results/rule-condition_duration-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-condition_duration-extended-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 结束时间（s） | 区间状态 | 说明 | energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 6 | 正常结束 | — | 30.0 | 完整 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-condition_duration-minimal-yaml"></a>
## rule-condition_duration-minimal.yaml

Purpose: Event rule: condition_duration. Configuration: [Download](../examples/rule-condition_duration-minimal.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-condition_duration-minimal.yaml --output result-rule-condition_duration-minimal-yaml
```

Why these results: Temperature meets the condition at 1 s, is confirmed after two seconds at 3 s, and clears at 6 s. Activity is [1,6).

[Run status and table list](../examples/results/rule-condition_duration-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-condition_duration-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 3 | 6 | 正常结束 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-debounce-extended-yaml"></a>
## rule-debounce-extended.yaml

Purpose: Event rule: debounce. Configuration: [Download](../examples/rule-debounce-extended.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-debounce-extended.yaml --output result-rule-debounce-extended-yaml
```

Why these results: Entry and exit both wait for configured confirmation, giving [3,8). The state does not change immediately during the waits.

[Run status and table list](../examples/results/rule-debounce-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-debounce-extended-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 3 | 3 | 8 | 正常结束 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-debounce-minimal-yaml"></a>
## rule-debounce-minimal.yaml

Purpose: Event rule: debounce. Configuration: [Download](../examples/rule-debounce-minimal.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-debounce-minimal.yaml --output result-rule-debounce-minimal-yaml
```

Why these results: The stable-state interval is [1,5), without additional waits.

[Run status and table list](../examples/results/rule-debounce-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-debounce-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | 5 | 正常结束 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-falling_edge-extended-yaml"></a>
## rule-falling_edge-extended.yaml

Purpose: Event rule: falling_edge. Configuration: [Download](../examples/rule-falling_edge-extended.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-falling_edge-extended.yaml --output result-rule-falling_edge-extended-yaml
```

Why these results: The falling edge at 5 s creates window [5,6): 10 W × 1 s = 10 J.

[Run status and table list](../examples/results/rule-falling_edge-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-falling_edge-extended-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 5 | 5 | — | 瞬时事件 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/rule-falling_edge-extended-yaml/窗口结果.csv) (1 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 | energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 5 | 6 | 完整 | 1 | — | 10.0 | 完整 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-falling_edge-minimal-yaml"></a>
## rule-falling_edge-minimal.yaml

Purpose: Event rule: falling_edge. Configuration: [Download](../examples/rule-falling_edge-minimal.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-falling_edge-minimal.yaml --output result-rule-falling_edge-minimal-yaml
```

Why these results: The switch changes from true to false at 5 s, producing one falling-edge point event.

[Run status and table list](../examples/results/rule-falling_edge-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-falling_edge-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 5 | 5 | — | 瞬时事件 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-hysteresis-extended-yaml"></a>
## rule-hysteresis-extended.yaml

Purpose: Event rule: hysteresis. Configuration: [Download](../examples/rule-hysteresis-extended.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-hysteresis-extended.yaml --output result-rule-hysteresis-extended-yaml
```

Why these results: Adding entry and exit confirmation waits to hysteresis gives alarm interval [2,7).

[Run status and table list](../examples/results/rule-hysteresis-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-hysteresis-extended-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 2 | 2 | 7 | 正常结束 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-hysteresis-minimal-yaml"></a>
## rule-hysteresis-minimal.yaml

Purpose: Event rule: hysteresis. Configuration: [Download](../examples/rule-hysteresis-minimal.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-hysteresis-minimal.yaml --output result-rule-hysteresis-minimal-yaml
```

Why these results: Entry and exit use different thresholds; intermediate temperatures retain the known state. Alarm interval is [1,6).

[Run status and table list](../examples/results/rule-hysteresis-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-hysteresis-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | 6 | 正常结束 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-rising_edge-extended-yaml"></a>
## rule-rising_edge-extended.yaml

Purpose: Event rule: rising_edge. Configuration: [Download](../examples/rule-rising_edge-extended.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-rising_edge-extended.yaml --output result-rule-rising_edge-extended-yaml
```

Why these results: The rising edge at 1 s creates a point and a one-second forward window [1,2): 10 W × 1 s = 10 J.

[Run status and table list](../examples/results/rule-rising_edge-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-rising_edge-extended-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | — | 瞬时事件 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/rule-rising_edge-extended-yaml/窗口结果.csv) (1 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 | energy（J） | energy：状态 | energy：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 2 | 完整 | 1 | — | 10.0 | 完整 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-rising_edge-minimal-yaml"></a>
## rule-rising_edge-minimal.yaml

Purpose: Event rule: rising_edge. Configuration: [Download](../examples/rule-rising_edge-minimal.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-rising_edge-minimal.yaml --output result-rule-rising_edge-minimal-yaml
```

Why these results: The switch changes from false to true at 1 s, producing one rising-edge point event.

[Run status and table list](../examples/results/rule-rising_edge-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-rising_edge-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | — | 瞬时事件 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-start_end-extended-yaml"></a>
## rule-start_end-extended.yaml

Purpose: Event rule: start_end. Configuration: [Download](../examples/rule-start_end-extended.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-start_end-extended.yaml --output result-rule-start_end-extended-yaml
```

Why these results: After starting at 1 s, the rule waits at most 2 s and ends by timeout at 3 s instead of waiting for the end condition at 5 s.

[Run status and table list](../examples/results/rule-start_end-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-start_end-extended-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | 3 | 超时结束 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-start_end-minimal-yaml"></a>
## rule-start_end-minimal.yaml

Purpose: Event rule: start_end. Configuration: [Download](../examples/rule-start_end-minimal.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-start_end-minimal.yaml --output result-rule-start_end-minimal-yaml
```

Why these results: The start condition arrives at 1 s and the end condition at 5 s, giving activity [1,5).

[Run status and table list](../examples/results/rule-start_end-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-start_end-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | 5 | 正常结束 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-start_only-extended-yaml"></a>
## rule-start_only-extended.yaml

Purpose: Event rule: start_only. Configuration: [Download](../examples/rule-start_only-extended.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-start_only-extended.yaml --output result-rule-start_only-extended-yaml
```

Why these results: Starts at 1 and 6 s each select a five-second window: [1,6) and [6,11).

[Run status and table list](../examples/results/rule-start_only-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-start_only-extended-yaml/事件结果.csv) (2 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | — | 瞬时事件 | — |
| 2 | detected | 6 | 6 | — | 瞬时事件 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/rule-start_only-extended-yaml/窗口结果.csv) (2 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 6 | 完整 | 1 | — |
| 2 | context | 6 | 11 | 完整 | 2 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-start_only-minimal-yaml"></a>
## rule-start_only-minimal.yaml

Purpose: Event rule: start_only. Configuration: [Download](../examples/rule-start_only-minimal.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-start_only-minimal.yaml --output result-rule-start_only-minimal-yaml
```

Why these results: One start point occurs at 1 s and another at 6 s. A continuously true condition does not repeatedly retrigger.

[Run status and table list](../examples/results/rule-start_only-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-start_only-minimal-yaml/事件结果.csv) (2 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 1 | 1 | — | 瞬时事件 | — |
| 2 | detected | 6 | 6 | — | 瞬时事件 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-window_delta-extended-yaml"></a>
## rule-window_delta-extended.yaml

Purpose: Event rule: window_delta. Configuration: [Download](../examples/rule-window_delta-extended.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-window_delta-extended.yaml --output result-rule-window_delta-extended-yaml
```

Why these results: Initial-window evaluation is enabled. Triggers occur at 4 and 12 s; the first has trigger initial.

[Run status and table list](../examples/results/rule-window_delta-extended-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-window_delta-extended-yaml/事件结果.csv) (2 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 4 | 4 | — | 瞬时事件 | — |
| 2 | detected | 12 | 12 | — | 瞬时事件 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="rule-window_delta-minimal-yaml"></a>
## rule-window_delta-minimal.yaml

Purpose: Event rule: window_delta. Configuration: [Download](../examples/rule-window_delta-minimal.yaml); guide: [Read the chapter](rules.md).

```powershell
chronaxis run rule-window_delta-minimal.yaml --output result-rule-window_delta-minimal-yaml
```

Why these results: The rule compares change across a complete lookback window and triggers at 12 s.

[Run status and table list](../examples/results/rule-window_delta-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/rule-window_delta-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | detected | 12 | 12 | — | 瞬时事件 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="sequence-minimal-yaml"></a>
## sequence-minimal.yaml

Purpose: Request/response pairing. Configuration: [Download](../examples/sequence-minimal.yaml); guide: [Read the chapter](sequences.md).

```powershell
chronaxis run sequence-minimal.yaml --output result-sequence-minimal-yaml
```

Why these results: The start edge and response edge are 1 s apart, within the allowed wait. Pairing succeeds with delay_ns=1000000000. Read pairing status and 延迟（s） (delay in seconds) in 配对结果.csv; pairing uses the configured request and response rules.

[Run status and table list](../examples/results/sequence-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/sequence-minimal-yaml/事件结果.csv) (2 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 2 | response_edge | 2 | 2 | — | 瞬时事件 | — |

**Pairing results: [Download full 配对结果.csv](../examples/results/sequence-minimal-yaml/配对结果.csv) (1 rows)**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 1 | 2 | 2 | 1 | 已响应 | — |

No window table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="sequence-outcomes-yaml"></a>
## sequence-outcomes.yaml

Purpose: Matched, no response, and indeterminate. Configuration: [Download](../examples/sequence-outcomes.yaml); guide: [Read the chapter](sequences.md).

```powershell
chronaxis run sequence-outcomes.yaml --output result-sequence-outcomes-yaml
```

Why these results: The three waits yield matched, no_response, and indeterminate: an eligible response arrived; the full wait was observable but no response arrived; or missing data/early observation end prevented a conclusion. The last case is not proof of no response.

[Run status and table list](../examples/results/sequence-outcomes-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/sequence-outcomes-yaml/事件结果.csv) (4 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 2 | request_edge | 3 | 3 | — | 瞬时事件 | — |
| 3 | request_edge | 6 | 6 | — | 瞬时事件 | — |
| 4 | response_edge | 2 | 2 | — | 瞬时事件 | — |

**Pairing results: [Download full 配对结果.csv](../examples/results/sequence-outcomes-yaml/配对结果.csv) (3 rows)**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 1 | 4 | 2 | 1 | 已响应 | — |
| 2 | pair | 2 | — | 5 | — | 时限内未响应 | — |
| 3 | pair | 3 | — | 8 | — | 无法确定 | 数值超出允许范围 |

No window table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="signal-bool-minimal-yaml"></a>
## signal-bool-minimal.yaml

Purpose: Boolean switch edge. Configuration: [Download](../examples/signal-bool-minimal.yaml); guide: [Read the chapter](signals.md).

```powershell
chronaxis run signal-bool-minimal.yaml --output result-signal-bool-minimal-yaml
```

Why these results: Enabled changes from integer 0 to 1 at 100 ms. choices maps these to false/true, producing a rising edge.

[Run status and table list](../examples/results/signal-bool-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/signal-bool-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | activated | 0.1 | 0.1 | — | 瞬时事件 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="signal-enum-minimal-yaml"></a>
## signal-enum-minimal.yaml

Purpose: Enum state edge. Configuration: [Download](../examples/signal-enum-minimal.yaml); guide: [Read the chapter](signals.md).

```powershell
chronaxis run signal-enum-minimal.yaml --output result-signal-enum-minimal-yaml
```

Why these results: ModeCode changes from 0 to 7 at 100 ms. DBC choices map them to idle/running; mode == "running" becomes true and produces a rising edge.

[Run status and table list](../examples/results/signal-enum-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/signal-enum-minimal-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | activated | 0.1 | 0.1 | — | 瞬时事件 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="signal-number-conversion-yaml"></a>
## signal-number-conversion.yaml

Purpose: Current unit conversion. Configuration: [Download](../examples/signal-number-conversion.yaml); guide: [Read the chapter](signals.md).

```powershell
chronaxis run signal-number-conversion.yaml --output result-signal-number-conversion-yaml
```

Why these results: DBC decoding yields 5000, 7000, 5000, and 5000 mA. The mA-to-A unit relationship automatically applies a factor of 0.001, giving maximum 7 A. No configured invalid code occurs.

[Run status and table list](../examples/results/signal-number-conversion-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/signal-number-conversion-yaml/会话结果.csv) (1 rows)**

| maximum_current（A） | maximum_current：状态 | maximum_current：说明 |
| --- | --- | --- |
| 7.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="signal-number-minimal-yaml"></a>
## signal-number-minimal.yaml

Purpose: DBC current maximum. Configuration: [Download](../examples/signal-number-minimal.yaml); guide: [Read the chapter](signals.md).

```powershell
chronaxis run signal-number-minimal.yaml --output result-signal-number-minimal-yaml
```

Why these results: DBC values are 5000, 7000, 5000, and 5000 mA. sample_maximum selects the largest value and displays 7000 mA in the output unit explicitly requested by the calculation.

[Run status and table list](../examples/results/signal-number-minimal-yaml/result-summary.json): `completed`.

**Session results: [Download full 会话结果.csv](../examples/results/signal-number-minimal-yaml/会话结果.csv) (1 rows)**

| maximum_current（mA） | maximum_current：状态 | maximum_current：说明 |
| --- | --- | --- |
| 7000.0 | 完整 | — |

No event, window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="signal-state-combined-yaml"></a>
## signal-state-combined.yaml

Purpose: Combined-state edge. Configuration: [Download](../examples/signal-state-combined.yaml); guide: [Read the chapter](signals.md).

```powershell
chronaxis run signal-state-combined.yaml --output result-signal-state-combined-yaml
```

Why these results: At 100 ms, Enabled becomes 1 and ModeCode becomes 7. After mapping, enabled is true and state is running; the combined condition rises from false to true.

[Run status and table list](../examples/results/signal-state-combined-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/signal-state-combined-yaml/事件结果.csv) (1 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | enabled_running | 0.1 | 0.1 | — | 瞬时事件 | — |

No window, request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="start-end-yaml"></a>
## start-end.yaml

Purpose: Start, normal end, and timeout. Configuration: [Download](../examples/start-end.yaml); guide: [Read the chapter](examples.md#start-end-case).

```powershell
chronaxis run start-end.yaml --output result-start-end-yaml
```

Why these results: The three activities are [0,2), [4,9), and [11,14) s. Time-weighted means of dimensionless value are (10×2)/2 = 10, (40×2+60×3)/5 = 52, and (110×3)/3 = 110, all unit 1. The second ends at timeout=5s. Default 事件结果.csv joins start/confirmation/end and cycle_mean on one row. For exchange-format joins, see [Result instance IDs](results.md#用实例id关联三张结果表).

[Run status and table list](../examples/results/start-end-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/start-end-yaml/事件结果.csv) (3 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 | cycle_mean（1） | cycle_mean：状态 | cycle_mean：说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cycle | 0 | 0 | 2 | 正常结束 | — | 10.0 | 完整 | — |
| 2 | cycle | 4 | 4 | 9 | 超时结束 | — | 52.0 | 完整 | — |
| 3 | cycle | 11 | 11 | 14 | 正常结束 | — | 110.0 | 完整 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/start-end-yaml/窗口结果.csv) (3 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | cycle_window | 0 | 2 | 完整 | 1 | — |
| 2 | cycle_window | 4 | 9 | 完整 | 2 | — |
| 3 | cycle_window | 11 | 14 | 完整 | 3 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="timing-actual-yaml"></a>
## timing-actual.yaml

Purpose: Rules and pairing using actual time. Configuration: [Download](../examples/timing-actual.yaml); guide: [Read the chapter](intervals.md).

```powershell
chronaxis run timing-actual.yaml --output result-timing-actual-yaml
```

Why these results: Actual timestamp differences give a request/response delay of 2 s and 5 s of temperature-condition duration. Rule waits, windows, and calculations all use actual time; compare the same inputs in the interval guide.

[Run status and table list](../examples/results/timing-actual-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/timing-actual-yaml/事件结果.csv) (5 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | change | 4 | 4 | — | 瞬时事件 | — |
| 2 | change | 6 | 6 | — | 瞬时事件 | — |
| 3 | hot | 1 | 2.5 | 6 | 正常结束 | — |
| 4 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 5 | response_edge | 3 | 3 | — | 瞬时事件 | — |

**Session results: [Download full 会话结果.csv](../examples/results/timing-actual-yaml/会话结果.csv) (1 rows)**

| hot_duration（s） | hot_duration：状态 | hot_duration：说明 |
| --- | --- | --- |
| 5.0 | 完整 | — |

**Pairing results: [Download full 配对结果.csv](../examples/results/timing-actual-yaml/配对结果.csv) (1 rows)**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 4 | 5 | 3 | 2 | 已响应 | — |

No window table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="timing-dbc-yaml"></a>
## timing-dbc.yaml

Purpose: Rules and pairing using DBC periods. Configuration: [Download](../examples/timing-dbc.yaml); guide: [Read the chapter](intervals.md).

```powershell
chronaxis run timing-dbc.yaml --output result-timing-dbc-yaml
```

Why these results: The request message has a DBC period of 1 s, advanced once per driver update. Request/response delay is 1 s and temperature-condition duration is 2 s. No driver update means no additional period.

[Run status and table list](../examples/results/timing-dbc-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/timing-dbc-yaml/事件结果.csv) (4 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | change | 7 | 7 | — | 瞬时事件 | — |
| 2 | hot | 1 | 6 | 6 | 正常结束 | — |
| 3 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 4 | response_edge | 3 | 3 | — | 瞬时事件 | — |

**Session results: [Download full 会话结果.csv](../examples/results/timing-dbc-yaml/会话结果.csv) (1 rows)**

| hot_duration（s） | hot_duration：状态 | hot_duration：说明 |
| --- | --- | --- |
| 2.0 | 完整 | — |

**Pairing results: [Download full 配对结果.csv](../examples/results/timing-dbc-yaml/配对结果.csv) (1 rows)**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 3 | 4 | 3 | 1 | 已响应 | — |

No window table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="timing-fixed-yaml"></a>
## timing-fixed.yaml

Purpose: Rules and pairing using fixed periods. Configuration: [Download](../examples/timing-fixed.yaml); guide: [Read the chapter](intervals.md).

```powershell
chronaxis run timing-fixed.yaml --output result-timing-fixed-yaml
```

Why these results: request is the driver; each update advances the configured 1 s. Request/response delay is 1 s and temperature-condition duration is 2 s. No driver update means no additional period.

[Run status and table list](../examples/results/timing-fixed-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/timing-fixed-yaml/事件结果.csv) (4 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | change | 7 | 7 | — | 瞬时事件 | — |
| 2 | hot | 1 | 6 | 6 | 正常结束 | — |
| 3 | request_edge | 1 | 1 | — | 瞬时事件 | — |
| 4 | response_edge | 3 | 3 | — | 瞬时事件 | — |

**Session results: [Download full 会话结果.csv](../examples/results/timing-fixed-yaml/会话结果.csv) (1 rows)**

| hot_duration（s） | hot_duration：状态 | hot_duration：说明 |
| --- | --- | --- |
| 2.0 | 完整 | — |

**Pairing results: [Download full 配对结果.csv](../examples/results/timing-fixed-yaml/配对结果.csv) (1 rows)**

| 配对编号 | 规则 | 请求区间 | 响应区间 | 判定时间（s） | 延迟（s） | 配对状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pair | 3 | 4 | 3 | 1 | 已响应 | — |

No window table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="window-exit-delay-yaml"></a>
## window-exit-delay.yaml

Purpose: Windows around events. Configuration: [Download](../examples/window-exit-delay.yaml); guide: [Read the chapter](windows.md).

```powershell
chronaxis run window-exit-delay.yaml --output result-window-exit-delay-yaml
```

Why these results: The condition creates actual activities [1,2), [3,4), and [6,7). Each end starts a two-second exit wait. Activity at 3 s starts before the first deadline of 4 s; activity at 6 s starts exactly at the next deadline and still merges. The last end at 7 s closes after waiting to 9 s, giving [1,9). False gaps do not become actual activity.

[Run status and table list](../examples/results/window-exit-delay-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/window-exit-delay-yaml/事件结果.csv) (3 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | pressed | 1 | 1 | 2 | 正常结束 | — |
| 2 | pressed | 3 | 3 | 4 | 正常结束 | — |
| 3 | pressed | 6 | 6 | 7 | 正常结束 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/window-exit-delay-yaml/窗口结果.csv) (1 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 9 | 完整 | 1、2、3 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="window-merged-yaml"></a>
## window-merged.yaml

Purpose: Windows around events. Configuration: [Download](../examples/window-merged.yaml); guide: [Read the chapter](windows.md).

```powershell
chronaxis run window-merged.yaml --output result-window-merged-yaml
```

Why these results: Rising edges at 1, 3, and 6 s extend forward by 3 s, giving [1,4), [3,6), and [6,9). merge=overlap_and_adjacent combines overlapping or touching windows into [1,9).

[Run status and table list](../examples/results/window-merged-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/window-merged-yaml/事件结果.csv) (3 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | pressed | 1 | 1 | — | 瞬时事件 | — |
| 2 | pressed | 3 | 3 | — | 瞬时事件 | — |
| 3 | pressed | 6 | 6 | — | 瞬时事件 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/window-merged-yaml/窗口结果.csv) (1 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 9 | 完整 | 1、2、3 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="window-minimal-yaml"></a>
## window-minimal.yaml

Purpose: Windows around events. Configuration: [Download](../examples/window-minimal.yaml); guide: [Read the chapter](windows.md).

```powershell
chronaxis run window-minimal.yaml --output result-window-minimal-yaml
```

Why these results: button_pressed rises at 1, 3, and 6 s, producing three point events. pre=0s and post=3s create [1,4), [3,6), and [6,9); this example does not merge windows.

[Run status and table list](../examples/results/window-minimal-yaml/result-summary.json): `completed`.

**Event results: [Download full 事件结果.csv](../examples/results/window-minimal-yaml/事件结果.csv) (3 rows)**

| 区间 | 规则 | 开始时间（s） | 确认时间（s） | 结束时间（s） | 区间状态 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | pressed | 1 | 1 | — | 瞬时事件 | — |
| 2 | pressed | 3 | 3 | — | 瞬时事件 | — |
| 3 | pressed | 6 | 6 | — | 瞬时事件 | — |

**Window results: [Download full 窗口结果.csv](../examples/results/window-minimal-yaml/窗口结果.csv) (3 rows)**

| 窗口编号 | 窗口 | 开始时间（s） | 结束时间（s） | 窗口状态 | 父事件区间 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | context | 1 | 4 | 完整 | 1 | — |
| 2 | context | 3 | 6 | 完整 | 2 | — |
| 3 | context | 6 | 9 | 完整 | 3 | — |

No request/response table was produced. Only requested, actually generated results are shown; this tutorial does not enable additional tables. Use the index for other event/window examples.


<a id="不能独立运行的定义文件"></a>
## Definition files that do not run independently

| Configuration | Why there is no standalone result | Complete task results |
|---|---|---|
|[teaching-base.yaml](../examples/teaching-base.yaml)|Only teaching sources/signals are defined; no event or calculation is requested.|[Complete sustained-condition example](#rule-condition_duration-extended-yaml)、[Rules guide](rules.md)|
|[electrical-base.yaml](../examples/electrical-base.yaml)|Only voltage/current and related signals are defined; add an expression or preset.|[Complete expression example](#expression-extended-yaml)、[Complete charging example](#preset-charge-energy-yaml)|
|[shared/definitions.yaml](../examples/shared/definitions.yaml)|Shared imports definitions need a main configuration specifying the task.|[analysis-imports.yaml results](#analysis-imports-yaml)|

These files are not counted as successful standalone runs. Documentation fragments also do not claim independent results: follow their chapter to the complete configuration, then find that file on this page.

<a id="重新生成与核验"></a>
## Regenerate and verify

From the repository root, after installing the project and its dependencies, run the commands below with a new work directory. By default the generator writes a draft only in that directory; `--publish` updates the manual:

```powershell
python tools/build_example_results.py --work work/manual-results-new --publish
python tools/build_example_results.py --check
```

Generation first runs independent mathematical assertions for 74 YAML configurations, then two JSON configurations and explicit expectations in the existing rule, time, window, and related scripts. Explanations are maintained separately, not reverse-engineered from observed output. `--check` compares parsed configuration values and input/result digests: comments and indentation do not affect the configuration digest, while inputs/results are checked byte-for-byte. This establishes file consistency, not a new execution.

Supply `--device-label home` or `--device-label work` according to the actual device. If omitted, the generator reads CHRONAXIS_DEVICE_LABEL, using pending if unknown. This labels newly generated results without changing the teaching inputs' origin.
