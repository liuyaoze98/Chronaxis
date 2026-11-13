# Command-line reference

Fast single-session commands `fast validate`, `fast explain` and `fast run` accept `--process-count` to override analysis `execution.process_count`. `fast batch --process-count` overrides its batch-root count. One fast session can contain multiple ASC/BLF volumes and publishes one summary. Workers read, decode and evaluate current-message contributions; the main process accumulates in order. See [fast configuration](fast-energy.md).

<a id="命令行参考"></a>

Use terminal commands to load and check a configuration, run an analysis, and publish results. Put the analysis definitions in the configuration file; put options such as an output directory or backend override after the appropriate command.

<a id="按基础并行配置运行"></a>
## Run the basic parallel configuration

Download the complete `examples` directory and open a terminal there. These steps inherit the continuous-volume example's explicit `execution.process_count: 4`:

```text
python -m chronaxis validate continuous-parallel.yaml
python -m chronaxis explain continuous-parallel.yaml --format json
python -m chronaxis run continuous-parallel.yaml --output result-continuous
```

`validate` checks configuration, `explain` describes execution, and `run` reads and analyzes the logs. With two files, `source_execution[].file_count` and `read_process_limit` are both 2; four is only the limit. Use `manifest` in the completion summary to locate this run's actual output files. The integral is 38 J; see the [worked result](example-results.md#continuous-parallel-yaml).

Ordinary `explain` reports `read_process_limit` as a bound derived from configuration and source type, not the number of workers already started. For one ASC, configured limit 4 and default `concatenate`, reading takes place in the current process and `read_process_limit` is 0; two files with that limit yield 2. Ordinary `time_order` uses one file child even at a configured limit of 1. Fast `worker_process_limit` follows its own scheduling rules and is 0 for inline execution. These are plan facts; actual PIDs can only be established during execution.

Append `--process-count 2` for a temporary override without editing the configuration. A single CSV, memory or multi-source plan uses `process_count: 1`. Independent tasks use the batch-root count; see [execution settings](execution.md).

<a id="全部命令"></a>
## Commands

| Command | Arguments and options | Purpose |
|---|---|---|
| `python -m chronaxis config init/convert/resolve/origins` | See [Configuration tools](configuration-tools.md) and [Shared definitions](imports.md). | Generate templates, convert formats, expand configurations, or inspect declared origins. |
| `python -m chronaxis validate PLAN` | Optional `--backend auto/reference/numpy`, `--process-count INTEGER`, `--format text/json`. | Check the plan; readable text is the default, JSON is available for tools. |
| `python -m chronaxis explain PLAN` | Same options as `validate`. | List required signals, resource limits, input-check scope, and calculation implementation. |
| `python -m chronaxis run PLAN` | Required `--output`; optional `--work-dir`, `--backend`, `--process-count`. | Analyze, publish, close, then print a completion summary. |
| `python -m chronaxis batch run BATCH` | Required `--output`; optional `--process-count`. | Run independent plans and write a per-job report; see [Batch execution](batch.md). |
| `python -m chronaxis fast validate PLAN` | Plan path | Check the supported same-frame calculation and DBC bindings; prints JSON. |
| `python -m chronaxis fast explain PLAN` | Plan path | Show the input file, calculation definitions and failure policy as JSON. |
| `python -m chronaxis fast run PLAN` | Required `--output`; optional `--process-count` | Compute one session from its ASC/BLF volumes and publish a summary. |
| `python -m chronaxis fast batch BATCH` | Required `--output`; optional `--total` and `--process-count` | Compute independent files. `--total` requests totals for comparable template calculations; see [fast batch](fast-energy.md). |
| `python -m chronaxis guide` | Optional `--language zh/en`, `--output new.zip` | Print the existing README path; save a bilingual ZIP only if output is requested. |

Replace `PLAN` and `BATCH` with paths. An installed package also provides the `chronaxis` command. Success returns `0` and cancellation returns `130`. Failure codes `1` and `2` depend on the command and stage, as explained in [Exit codes and failure stages](#退出码与错误位置); “file error” alone does not determine the code. Use `python -m chronaxis --help` and each subcommand's `--help`. The full implementation is in the [CLI reference](../reference/chronaxis.cli.md) (Chinese implementation reference).

Ordinary run, validate and explain accept `--process-count` to override file-reading/decoding workers. The same option for batch run limits independent analysis workers. See [continuous multiprocessing](continuous-files.md).

For fast run, execution.process_count controls session workers; fast batch uses the batch-root count. Both accept --process-count overrides, as do fast validate/explain. `--total` is a flag, omitted by default; the report explains any unavailable total. For `guide`, `--language` defaults to `zh`; `en` selects the English README, and an optional ZIP contains both languages.

| Argument or option | Type | Required for | Default when omitted | Accepted values and effect |
|---|---|---|---|---|
| `PLAN` | File path | `validate`, `explain`, `run` | None | Analysis YAML/JSON path; quote paths containing spaces. |
| `BATCH` | File path | `batch run` | None | [Batch YAML/JSON](batch.md), not one child `analysis.json`. |
| `--format` | String | Optional for `validate`/`explain` | `text` | `text` prints readable diagnostics; `json` returns a report object. It does not change result table formats. |
| `--format` | String | Optional for `config resolve` | Terminal: `yaml`; file: suffix | Expanded configuration as `yaml`/`json`; an explicit value must match the output suffix. |
| `--format` | String | Optional for `config origins` | `text` | `text` lists origins; `json` gives a field-origin report, not analysis results. |
| `--backend` | String | Optional | Plan's `backend` | `auto` selects from the whole plan; `reference` and `numpy` fix the numerical implementation. This option overrides the plan. Applies to `validate`, `explain`, and `run`. |
|--output|Directory path|run, batch run, fast run/batch|Required|Reusable result directory; each run creates distinct timestamped files.|
| `--work-dir` | Directory path | Optional; ordinary `run` only | Create a dedicated work directory | Holds intermediate data and staged results. An explicit path must not already exist. |
| `--process-count` | Integer | Optional; run/validate/explain/batch run and fast equivalents | Ordinary analysis: execution.process_count; batch: root process_count; both default 1 | Positive integer. Ordinary analysis limits read/decode workers; fast session workers also evaluate contributions. Both exclude the main process. Batch limits independent analysis workers, excluding their existing CAN subprocesses. |
| `-h` / `--help` | Flag without a value | Optional | Execute the command | Display help for that level and exit without analysis, e.g. `python -m chronaxis run --help`. |

For `config init`, `convert`, and `resolve` options and file-protection rules, see [Configuration tools](configuration-tools.md). For direct reading and optional guide export, see [AI guide](ai-guide.md).

<a id="退出码与错误位置"></a>
## Exit codes and failure stages

The exit code tells you whether a command succeeded; diagnostics and batch reports explain why it failed. The same file problem may return different codes through different commands. Account for the command when writing a shell script.

| Command | Common failures returning `2` | Common failures returning `1` |
|---|---|---|
| Ordinary `validate`, `explain`, `run` | Invalid arguments or configuration, an empty source directory, or a glob with no matches | Unreadable configuration or DBC; for `run`, log reading, analysis, publication or close failures |
| Ordinary `batch run` | Invalid batch configuration or arguments; configuration errors while expanding `template`/`inputs` or constructing child plans during loading | Unreadable batch or template configuration files; a `jobs` child configuration rejected after its task starts, or another failure in a started task; output, batch-report or cleanup failures |
| `fast validate`, `fast explain`, `fast run` | Configuration, DBC or input-list preparation failures, including file errors at those stages | For `fast run` only: log reading, calculation or result publication failures after preparation |
| `fast batch` | Batch preflight or output-directory setup failures; a final batch-report write failure without a recoverable report attached to the exception | A failed task report, or an execution failure that already carries the current batch report |

Examples:

- A missing configuration returns `1` from ordinary `validate` and `2` from `fast validate`. A missing DBC follows the same distinction.
- An explicitly configured but missing `missing.asc` is not read by static `validate`/`explain`, so those commands may return `0`. The actual `run` reads it and returns `1`. Static success does not prove that the log can be read.
- An ordinary batch using **`jobs`** loads each referenced analysis configuration after its worker starts. If a child configuration references an empty directory or an unmatched glob, that task is marked failed, the batch returns `1`, and a batch task report is available.
- An ordinary batch using **`template`/`inputs`** expands the template and constructs each child plan while loading the batch configuration. For example, a valid template may have two CSV sources, `primary` and `auxiliary`. With `source: primary`, only `primary` is replaced by `inputs`. If the retained `auxiliary` source references an empty directory or an unmatched glob, loading returns `2`: no task has started and no task report exists. This is not limited to expansion errors in batch `inputs` itself. See [`load_batch_plan`](public-api/load_batch_plan.md) for the loading contract.
- **`fast batch`** checks its supported CAN child configurations before dispatch. Preparation errors such as empty directories or unmatched globs return `2`, without starting tasks or producing task reports. It does not support the two-CSV template above.
- If the output path is an existing ordinary file, ordinary `run`, ordinary `batch run`, and `fast run` return `1`; `fast batch` returns `2`. A file error while writing the final fast batch report can also return `2` after child tasks have succeeded. Their completed outputs remain available.

On a nonzero exit, retain stderr and inspect any task reports already written. A nonzero exit does not mean that all published results were rolled back. Failed or cancelled batches must not count unfinished tasks as successes.

## See several configuration errors at once

Run `chronaxis validate plan.yaml --format json`. When fields can be parsed, it lists independently detectable errors together, such as invalid backend, batch_rows and table format. Each diagnostic retains available source, path, line, column, code, message and hint. JSON uses an errors array even for one error; the former singular error field is no longer returned. Text mode numbers the errors.

Repair malformed YAML/JSON syntax first. An invalid source or signal can prevent dependent checks; blocked_checks explains those checks instead of inventing values. Run validation again after repairs. A configuration error prevents run from starting analysis. Static checks may read DBC metadata when configuration defaults require it, but do not read business message contents.

The run summary returns the actual manifest path; batch run returns the actual report path. Output filenames receive a timestamp suffix; see [result publication](results.md#result-publication).

## AI guide

`chronaxis guide` prints the absolute Chinese README path; `chronaxis guide --language en` selects English. Neither writes files. Optional `--output new-file.zip` saves a complete bilingual copy; its parent must exist and the target must be new. See [AI guide](ai-guide.md).
