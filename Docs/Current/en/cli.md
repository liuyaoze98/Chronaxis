# Command-line reference

<a id="命令行参考"></a>

Use terminal commands to load and check a configuration, run an analysis, and publish results. Put the analysis definitions in the configuration file; put options such as an output directory or backend override after the appropriate command.

<a id="全部命令"></a>
## Commands

| Command | Arguments and options | Purpose |
|---|---|---|
| `python -m chronaxis config init/convert/resolve/origins` | See [Configuration tools](configuration-tools.md) and [Shared definitions](imports.md). | Generate templates, convert formats, expand configurations, or inspect declared origins. |
| `python -m chronaxis validate PLAN` | Optional `--backend reference/numpy`, `--format text/json`. | Check the plan; readable text is the default, JSON is available for tools. |
| `python -m chronaxis explain PLAN` | Same options as `validate`. | List required signals, resource limits, input-check scope, and calculation implementation. |
| `python -m chronaxis run PLAN` | Required `--output`; optional `--work-dir`, `--backend`. | Analyze, publish, close, then print a completion summary. |
| `python -m chronaxis batch run BATCH` | Required `--output`; optional `--process-count`. | Run independent plans and write a per-job report; see [Batch execution](batch.md). |
| `python -m chronaxis legacy import INI` | Required `--mode`, `--mapping`, `--output`. | Preserve the original text and produce a new plan or a complete rejection report. |

Replace `PLAN` and `INI` with paths. An installed package also provides the `chronaxis` command. Exit codes are `0` for success, `2` for argument/configuration errors, `1` for file/analysis/publication/close failures, and `130` for cancellation. Use `python -m chronaxis --help` and each subcommand's `--help`. The full implementation is in the [CLI reference](../reference/chronaxis.cli.md) (Chinese implementation reference).

Options belong to specific commands. For example, `--process-count` belongs to `batch run`, not the single-analysis `run` command.

| Argument or option | Type | Required for | Default when omitted | Accepted values and effect |
|---|---|---|---|---|
| `PLAN` | File path | `validate`, `explain`, `run` | None | Analysis YAML/JSON path; quote paths containing spaces. |
| `BATCH` | File path | `batch run` | None | [Batch YAML/JSON](batch.md), not one child `analysis.json`. |
| `INI` | File path | `legacy import` | None | Old INI to convert; the original file is not modified. |
| `--format` | String | Optional for `validate`/`explain` | `text` | `text` prints readable diagnostics; `json` returns a report object. It does not change result table formats. |
| `--format` | String | Optional for `config resolve` | Terminal: `yaml`; file: suffix | Expanded configuration as `yaml`/`json`; an explicit value must match the output suffix. |
| `--format` | String | Optional for `config origins` | `text` | `text` lists origins; `json` gives a field-origin report, not analysis results. |
| `--backend` | String | Optional | Plan's `backend` | `reference` selects reference calculations; `numpy` selects array calculations. Applies to `validate`, `explain`, and `run`. |
| `--output` | Path | `run`, `batch run`, `legacy import` | None | The first two write a new result **directory**; `legacy import` writes a new plan **file**, such as `converted/analysis.json`. Existing targets are not overwritten. |
| `--work-dir` | Directory path | Optional; `run` only | Create a dedicated work directory | Holds intermediate data and staged results. An explicit path must not already exist. |
| `--process-count` | Integer | Optional; `batch run` only | Batch file's `process_count`, default `1` | Positive integer overriding the maximum analysis worker count, e.g. `--process-count 2`. Excludes the scheduler and CAN reader subprocesses. |
| `--mode` | String | `legacy import` | None | `legacy_sum`, `sclicer_single`, `sclicer_start_only`, `sclicer_start_end`, or `sclicer_slope`; see [INI import modes](migration.md#import-modes). |
| `--mapping` | File path | `legacy import` | None | YAML/JSON defining signals, inputs, and new node names; see [INI mapping](migration.md#import-mapping). |
| `-h` / `--help` | Flag without a value | Optional | Execute the command | Display help for that level and exit without analysis, e.g. `python -m chronaxis run --help`. |

For `config init`, `convert`, and `resolve` options and file-protection rules, see [Configuration tools](configuration-tools.md). For direct reading and optional guide export, see [AI guide](ai-guide.md).

## AI guide

`chronaxis guide` prints the absolute Chinese README path; `chronaxis guide --language en` selects English. Neither writes files. Optional `--output new-file.zip` saves a complete bilingual copy; its parent must exist and the target must be new. See [AI guide](ai-guide.md).
