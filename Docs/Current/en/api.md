# Public Python API index

<a id="python公开api索引"></a>

Find an entry point by task. Each linked object page gives its full constructor signature, public methods/properties, parameters, return values, and exceptions. General analysis, batch, preset and time entries are imported from `chronaxis`; the integrator and custom operator sections state their respective import modules. See the [result row models](../reference/chronaxis.results.summary.md) and [developer reference](../reference/index.md) (Chinese implementation references). For a complete file-based workflow, start with [Python quick start](api-usage.md).

<a id="计划加载与检查"></a>
## Load and check a plan

| Public name | Reference and purpose |
|---|---|
| `chronaxis.AnalysisPlan` | [AnalysisPlan](public-api/AnalysisPlan.md#api-AnalysisPlan): Stores a session's analysis configuration and the objects produced by static checking. |
| `chronaxis.load_analysis_plan` | [load_analysis_plan](public-api/load_analysis_plan.md#api-load_analysis_plan): Loads JSON/YAML and one level of shared definitions, resolving relative source paths against each declaring file. |
| `chronaxis.validate_analysis_plan` | [validate_analysis_plan](public-api/validate_analysis_plan.md#api-validate_analysis_plan): Reports static configuration validity and current reader, execution, and publication limitations. |
| `chronaxis.explain_analysis_plan` | [explain_analysis_plan](public-api/explain_analysis_plan.md#api-explain_analysis_plan): Lists dependencies, node calculations, required history, and declared budgets. |
| `chronaxis.PlanValidationError` | [PlanValidationError](public-api/PlanValidationError.md#api-PlanValidationError): Contains the configuration path, reason, machine error code, and optional original source location and correction hint. |

<a id="执行与结果"></a>
## Run and read results

| Public name | Reference and purpose |
|---|---|
| `chronaxis.AnalysisRunner` | [AnalysisRunner](public-api/AnalysisRunner.md#api-AnalysisRunner): Stores an optional backend override, uses the same static validation, and creates independent resources for each run. |
| `chronaxis.AnalysisResult` | [AnalysisResult](public-api/AnalysisResult.md#api-AnalysisResult): Stores staging paths and small metadata objects; it does not hold full lists of events, segments, or calculations. |
| `chronaxis.OutputManifest` | [OutputManifest](public-api/OutputManifest.md#api-OutputManifest): Stores the successfully published directory, manifest, and row counts for the fixed table whitelist; legacy entries appear only when enabled. |
| `chronaxis.ExportManifest` | [ExportManifest](public-api/ExportManifest.md#api-ExportManifest): Provides the actual directory, completion manifest, and data-file paths returned by direct signal-CSV or raw-message exports. |
| `chronaxis.RunMetadata` | [RunMetadata](public-api/RunMetadata.md#api-RunMetadata): Stores run identity, actual backend, time interpretation, session boundaries, and compatibility limitations. |
| `chronaxis.AnalysisError` | [AnalysisError](public-api/AnalysisError.md#api-AnalysisError): Signals an analysis or result-publication failure. The exception alone does not guarantee that old output was rolled back. |
| `chronaxis.ResultClosedError` | [ResultClosedError](public-api/ResultClosedError.md#api-ResultClosedError): Signals that the result has been closed and can no longer create iterators, be read, or be published. |

<a id="批量任务"></a>
## Batch execution

| Public name | Reference and purpose |
|---|---|
| `chronaxis.BatchPlan` | [BatchPlan](public-api/BatchPlan.md#api-BatchPlan): Stores batch options and independent jobs. Jobs reference a configuration path or a loaded analysis plan. Keep one continuous session in one job. |
| `chronaxis.BatchJob` | [BatchJob](public-api/BatchJob.md#api-BatchJob): Declares one independent analysis. Continuous files belonging to the same session go in this job's single plan. |
| `chronaxis.BatchJobResult` | [BatchJobResult](public-api/BatchJobResult.md#api-BatchJobResult): Stores the final status of a job. A close failure after publication still means failed, with the published path retained. |
| `chronaxis.BatchReport` | [BatchReport](public-api/BatchReport.md#api-BatchReport): Lists results in original job order. Numerical tables remain in each job directory; values from separate jobs are not added together. |
| `chronaxis.BatchRunner` | [BatchRunner](public-api/BatchRunner.md#api-BatchRunner): Uses process_count to select analysis workers. Each run creates and reclaims its workers; plans and state are not cached across batches. |
| `chronaxis.load_batch_plan` | [load_batch_plan](public-api/load_batch_plan.md#api-load_batch_plan): Loads strict batch JSON/YAML. Takes a UTF-8 configuration path, returns BatchPlan, and raises configuration errors with paths. |
| `chronaxis.run_batch` | [run_batch](public-api/run_batch.md#api-run_batch): Runs the batch and publishes its report. |

<a id="业务预设"></a>
## High-performance integrator

| Public entry | When to use it |
|---|---|
| [chronaxis.fast.run](public-api/fast.run.md) | Same-frame per-message accumulation; include the time factor in an energy formula. See [the integrator guide](fast-energy.md). |
| [chronaxis.fast.batch.run_batch](public-api/fast.batch.run_batch.md) | Apply that calculation to independent files with optional compatible totals. |

Import these entries with `from chronaxis.fast import run` and `from chronaxis.fast.batch import run_batch`.

## Custom analysis operators

Import `ExtensionRegistry`, `FunctionSpec`, `ReductionSpec` and `TransformSpec` from `chronaxis.extensions`.

| Public entry | When to use it |
|---|---|
| [ExtensionRegistry](public-api/ExtensionRegistry.md) | Pass the same registry when loading and running a plan. |
| [FunctionSpec](public-api/FunctionSpec.md) | Register an element-wise expression function. |
| [ReductionSpec](public-api/ReductionSpec.md) | Register a statistic over the rows in one scope. |
| [TransformSpec](public-api/TransformSpec.md) | Register a time-window calculation. |

Complete contracts and examples are in [custom analysis operators](host-extensions.md).

## Task presets

| Public name | Reference and purpose |
|---|---|
| `chronaxis.PresetSpec` | [PresetSpec](public-api/PresetSpec.md#api-PresetSpec): Stores a preset instance name, task type, template version, role-to-signal bindings, and business parameters. from_dict creates an immutable declaration. |
| `chronaxis.PlanFragment` | [PlanFragment](public-api/PlanFragment.md#api-PlanFragment): Stores the public nodes generated by a preset, without sources, runners, or actual samples. |
| `chronaxis.build_preset` | [build_preset](public-api/build_preset.md#api-build_preset): Validates a v1 preset and expands public declarations, without I/O or numerical analysis. |
| `chronaxis.resolve_preset_roles` | [resolve_preset_roles](public-api/resolve_preset_roles.md#api-resolve_preset_roles): First uses explicit role_bindings. For unassigned roles, uses semantic_id and semantic_contract_version to find the unique signal satisfying each role. |

<a id="时间转换"></a>
## Time conversion

| Public name | Reference and purpose |
|---|---|
| `chronaxis.TimeConversion` | [TimeConversion](public-api/TimeConversion.md#api-TimeConversion): Stores normalized time and source precision without sharing mutable conversion diagnostics across tasks. |
| `chronaxis.TimeOverflowError` | [TimeOverflowError](public-api/TimeOverflowError.md#api-TimeOverflowError): Rejects time coordinates, shifted coordinates, or nonnegative spans outside int64. |
| `chronaxis.checked_add_ns` | [checked_add_ns](public-api/checked_add_ns.md#api-checked_add_ns): Adds a fixed offset to one nanosecond coordinate and checks that the result remains in int64. |
| `chronaxis.convert_time` | [convert_time](public-api/convert_time.md#api-convert_time): Converts an explicitly specified time unit to nanoseconds, rounding the final result to nearest, ties to even. |
| `chronaxis.parse_datetime_ns` | [parse_datetime_ns](public-api/parse_datetime_ns.md#api-parse_datetime_ns): Converts a complete ISO date/time to integer UTC nanoseconds, preserving sub-microsecond fractions. |
| `chronaxis.parse_duration` | [parse_duration](public-api/parse_duration.md#api-parse_duration): Parses a nonnegative duration with a unit, including an explicit zero duration. |
| `chronaxis.shift_times_reference` | [shift_times_reference](public-api/shift_times_reference.md#api-shift_times_reference): Calculates each fixed offset independently as an integer reference for the array kernel. |
| `chronaxis.time_deltas_reference` | [time_deltas_reference](public-api/time_deltas_reference.md#api-time_deltas_reference): Calculates adjacent spans in nondecreasing integer timestamps, allowing different samples at the same time. |

<a id="功能与配置关联"></a>
## Related features and configuration

| Configuration or task | Guide | Main API |
|---|---|---|
| Configuration files and shared definitions | [Configuration](configuration.md), [Shared definitions](imports.md) | `load_analysis_plan`, `AnalysisPlan.from_dict` |
| Events, windows, and calculations | [Rules](rules.md), [Windows](windows.md), [Calculations](calculations.md) | `AnalysisRunner.run`, `AnalysisResult` iterators |
| Independent batch jobs | [Batch execution](batch.md) | `load_batch_plan`, `run_batch` |
| Preset role resolution and generation | [Presets](presets.md) | `PresetSpec`, `resolve_preset_roles`, `build_preset` |
| Time units and dates | [Time and result quality](concepts.md) | `parse_duration`, `convert_time`, `parse_datetime_ns` |
