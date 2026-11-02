# Independent batch analyses

<a id="独立批量任务"></a>

For separate vehicles or unrelated trials, create an analysis configuration for each trial and run them together. Each job has its own signal state, alarm timers, response queue, and output directory.

`execution.batch_rows` controls how many samples **one analysis processes at a time**, preserving state. `batch run` schedules **independent analyses**. Put consecutive files from the same recording in one source's `paths`; splitting them into jobs does not carry alarms between them.

Use `chronaxis batch run` or `load_batch_plan` / `run_batch` with a separate batch file. List configurations in `jobs`, or apply `template` to multiple `inputs`; these forms are mutually exclusive. Root `process_count` limits the number of analysis workers.

<a id="完整批量配置"></a>
## Complete batch configuration

Fields such as `batch_version`, `jobs`, and `process_count` belong at the batch file's root. `jobs[].plan` belongs to a job item. This file is not embedded in an analysis configuration.

[batch-minimal.yaml](../examples/batch-minimal.yaml) references the main ASC example `analysis.yaml`, uses an automatic job name and sequential execution, and produces 38 J. [batch-extended.yaml](../examples/batch-extended.yaml) adds an independent ASC voltage analysis and runs at most two jobs at once. Results are 38 J and 13 V·s; the recordings are not concatenated. Keep the batch file beside the referenced configurations.

```yaml
batch_version: 1
jobs:
  - plan: analysis.yaml
  - plan: input-asc-minimal.yaml
process_count: 2
```

Omit job names, `fail_fast`, and backend settings unless you need to change their defaults. Use `jobs[].name` to customize output-directory names.

| Field | Type | Required | Default | Meaning and choices |
|---|---|---|---|---|
| `batch_version` | integer | Yes | — | `1`, the batch structure version, separate from analysis `config_version`. |
| `jobs` | object array | Alternative to `template` | — | Jobs in report order. An empty list is valid and can produce an empty report. |
| `jobs[].name` | string | No | `job_1`, `job_2`, … | Unique job/output-subdirectory name. Comparison is case-insensitive, so `Trial_A` conflicts with `trial_a`. |
| `jobs[].plan` | string | Yes | — | Complete analysis YAML/JSON file, relative to the batch file or absolute. |
| `process_count` | integer | No | `1` | Positive worker limit. `1` runs jobs sequentially in one worker; `2` or `4` permits that many workers. Choose using available CPU, memory and disk. No automatic all-CPU setting; zero, negatives, floats, Booleans, strings and null are invalid. |
| `fail_fast` | Boolean | No | `false` | `false` continues launching after failures; `true` stops launching new jobs after a failure, while dispatched jobs finish and close. |
| `backend` | string or null | No | `null` | `null` preserves each plan's choice; `reference` or `numpy` overrides all jobs. See [execution settings](execution.md). |

Names start with an ASCII letter or underscore, followed by letters, digits or underscores. Python keywords (`for`, `class`) and expression function names (`abs`, `isclose`) are prohibited. `trial_a` is valid; `trial-a` and `a/b` are not. Names must also be valid directory names on the platform, excluding Windows device names such as CON and NUL.

Input paths inside a child analysis remain relative to **that analysis file**: `a/analysis.yaml` referencing `data.csv` reads `a/data.csv`, not a file next to the batch configuration.

<a id="一个模板处理整个目录"></a>
## Apply one template to a directory

If each input file is an independent trial with the same signals and analysis, reuse one configuration. `template`, `inputs`, and optional `source` are root fields and replace the `jobs` form.

```yaml
batch_version: 1
template: analysis.yaml
inputs: data/can/quickstart*.asc
process_count: 2
```

Change the directory or pattern to your BLF files, or supply a directory containing mixed supported formats.

| Field | Required | Meaning |
|---|---|---|
| `template` | In this form | Analysis YAML/JSON applied independently to each input. Other sources and DBC paths retain their own declaration-file bases. |
| `inputs` | With `template` | A file, directory, wildcard, or list of these. Directories inspect one level and filter by the source format; results use natural order (`file2` before `file10`). Recursion requires an explicit `**` wildcard. Explicit lists retain declared order. Maximum 4096 files. |
| `source` | When the template has multiple sources | Name of the source whose paths are replaced. A single source is inferred. Memory sources cannot be selected. |

Names are `job_1`, `job_2`, etc. Only the selected source's paths change; other sources remain as declared. State and outputs are independent, so a value or alarm from `file2.csv` cannot continue into `file10.csv`. Use one source's `paths` for continuous volumes.

<a id="cli与python"></a>
## CLI and Python

```powershell
python -m chronaxis batch run batch-extended.yaml --output batch-output --process-count 2
```

The override is optional: CLI/API override → batch file → default 1. Batch CLI has no `--backend`; set it in the batch file. Single-analysis `run` has that option. The output directory must not already exist.

```python
from chronaxis import load_batch_plan, run_batch

def main():
    plan = load_batch_plan("batch-extended.yaml")
    report = run_batch(plan, "batch-output", process_count=2)
    try:
        print(report.worker_process_count)
        print(report.to_dict())
    finally:
        report.close()

if __name__ == "__main__":
    main()
```

Omitting API `process_count`, or passing `None`, uses the plan. A positive integer overrides only this run. `BatchPlan(..., process_count=4)` and `BatchRunner(process_count=4)` have the same meaning. Neither ordinary `execution` nor `AnalysisRunner` has a process-count parameter.

With `jobs`, `load_batch_plan` reads the batch file; each child's plan and input are read when it starts. With `template`, loading reads the template, expands inputs, and compiles independent plans; DBC metadata may be read to infer signal definitions, but business frames are not scanned yet.

`run_batch` writes `batch_report.json`. Lower-level `BatchRunner.run()` returns an object; call `write_batch_report()` explicitly when using that entry. Detailed signatures: [batch API](../reference/chronaxis.batch.api.md), [BatchRunner](../reference/chronaxis.batch.runner.md), [models](../reference/chronaxis.batch.models.md) (Chinese implementation reference).

Windows starts workers with `spawn`, which imports the script again. Keep startup inside `if __name__ == "__main__":` and run a saved `.py` file so workers do not dispatch the batch again. The process mode has been validated on Windows / Python 3.12.

Actual workers are at most `min(process_count, number of jobs)`. Empty or pre-cancelled batches launch none; a limit of four with two jobs launches two workers. The scheduler and CAN reader subprocesses are additional processes. Workers are reused, but signal and event state are not carried between jobs.

The report stores the effective limit as `process_count`, actual count as `worker_process_count`, and each job's process ID as `jobs[].worker_pid` (`null` for unstarted jobs). Several jobs may share a reused PID. Reports retain declaration order, not completion order.

<a id="批量报告的设备来源标签"></a>
## Device label on the batch report

CLI reads `CHRONAXIS_DEVICE_LABEL`, strips surrounding whitespace, and defaults to `pending` for an unset/blank value. The user supplies the actual device convention; the program does not inspect hardware. In PowerShell, `$env:CHRONAXIS_DEVICE_LABEL = "home"` affects the current process and its children.

Python does not automatically read this variable: pass `run_batch(plan, "batch-output", device_label="home")` if needed; omission gives `pending`. This labels the batch summary, not each child's `metadata.device_label`. See [exports](exports.md) for ordinary analysis and independent-export requirements. Keep `pending` when no device provenance is needed; it is not a business signal.

<a id="失败取消和资源设置"></a>
<a id="失败-取消和资源设置"></a>
## Failure, cancellation, and resources

| Path | Contents |
|---|---|
| `batch-output/job_1/work/` | Temporary calculations and diagnostics. |
| `batch-output/job_1/output/` | Published analysis results. |
| `batch-output/batch_report.json` | Status, errors, and available paths for each job in declaration order. |

`output_dir` is populated only after results are written. If writing succeeds but closing fails, the job is still `failed`, with its output path retained.

Suppose A and B are running and C is waiting. If A fails, B continues; C starts when `fail_fast=false`, but does not start when `true`. API `cancel_event` or Ctrl+C similarly stops new launches and retains completed outputs. Cancellation waits for dispatched jobs to finish writing and closing rather than killing them immediately.

Ordinary task failures follow `fail_fast`. Unexpected worker exit is a scheduling failure: stop dispatch, preserve completed output, and clean up that worker's CAN reader processes. Python infrastructure exceptions carry `batch_report`, whose `close()` can be retried.

If cleanup continues failing, that worker stops accepting jobs and the report marks `cleanup_pending=true`. Resources remain owned by that process. Correct the file-use/environment problem and call `report.close()` to retry remotely. If every worker is waiting for cleanup, unstarted jobs become `cancelled`, not completed. Published JSON records the state when written; the live report's `to_dict()` reflects later cleanup retries.

Exit codes: 0 for all successful, 1 for job or file-operation failure (including an existing output directory), 2 for invalid batch configuration/arguments, and 130 for cancellation. Failure takes precedence over cancellation and returns 1.

Each job has its own analysis memory/disk limits. Two jobs allowing 256 MiB each do not impose a 256 MiB total-process limit; Python and decoders add overhead. First verify one job, then choose `process_count` using actual resources and measurements.

Batch files do not support `imports`; child analyses may each import definitions with paths based on their declaration files. `config origins BATCH` lists child or template paths, not each child's full origins. See [shared definitions](imports.md).
