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
| `python -m chronaxis fast validate PLAN` | Plan path | Check the supported same-frame calculation and DBC bindings; prints JSON. |
| `python -m chronaxis fast explain PLAN` | Plan path | Show the input file, calculation definitions and failure policy as JSON. |
| `python -m chronaxis fast run PLAN` | Required `--output` | Compute one independent ASC/BLF file and publish its results. |
| `python -m chronaxis fast batch BATCH` | Required `--output`; optional `--total` | Compute independent files. `--total` requests totals for comparable template calculations; see [fast batch](fast-energy.md). |
| `python -m chronaxis guide` | Optional `--language zh/en`, `--output new.zip` | Print the existing README path; save a bilingual ZIP only if output is requested. |

Replace `PLAN` and `BATCH` with paths. An installed package also provides the `chronaxis` command. Exit codes are `0` for success, `2` for argument/configuration errors, `1` for file/analysis/publication/close failures, and `130` for cancellation. Use `python -m chronaxis --help` and each subcommand's `--help`. The full implementation is in the [CLI reference](../reference/chronaxis.cli.md) (Chinese implementation reference).

Options belong to specific commands. For example, `--process-count` belongs to `batch run`, not the single-analysis `run` command.

For `fast`, place the process count in the batch configuration. Its CLI options are listed above. `--total` is a flag, omitted by default; the report explains any unavailable total. For `guide`, `--language` defaults to `zh`; `en` selects the English README, and an optional ZIP contains both languages.

| Argument or option | Type | Required for | Default when omitted | Accepted values and effect |
|---|---|---|---|---|
| `PLAN` | File path | `validate`, `explain`, `run` | None | Analysis YAML/JSON path; quote paths containing spaces. |
| `BATCH` | File path | `batch run` | None | [Batch YAML/JSON](batch.md), not one child `analysis.json`. |
| `--format` | String | Optional for `validate`/`explain` | `text` | `text` prints readable diagnostics; `json` returns a report object. It does not change result table formats. |
| `--format` | String | Optional for `config resolve` | Terminal: `yaml`; file: suffix | Expanded configuration as `yaml`/`json`; an explicit value must match the output suffix. |
| `--format` | String | Optional for `config origins` | `text` | `text` lists origins; `json` gives a field-origin report, not analysis results. |
| `--backend` | String | Optional | Plan's `backend` | `reference` selects reference calculations; `numpy` selects array calculations. Applies to `validate`, `explain`, and `run`. |
|--output|Directory path|run, batch run, fast run/batch|Required|Reusable result directory; each run creates distinct timestamped files.|
| `--work-dir` | Directory path | Optional; `run` only | Create a dedicated work directory | Holds intermediate data and staged results. An explicit path must not already exist. |
| `--process-count` | Integer | Optional; `batch run` only | Batch file's `process_count`, default `1` | Positive integer overriding the maximum analysis worker count, e.g. `--process-count 2`. Excludes the scheduler and CAN reader subprocesses. |
| `-h` / `--help` | Flag without a value | Optional | Execute the command | Display help for that level and exit without analysis, e.g. `python -m chronaxis run --help`. |

For `config init`, `convert`, and `resolve` options and file-protection rules, see [Configuration tools](configuration-tools.md). For direct reading and optional guide export, see [AI guide](ai-guide.md).

## See several configuration errors at once

Run `chronaxis validate plan.yaml --format json`. When fields can be parsed, it lists independently detectable errors together, such as invalid backend, batch_rows and table format. Each diagnostic retains available source, path, line, column, code, message and hint. JSON uses an errors array even for one error; the former singular error field is no longer returned. Text mode numbers the errors.

Repair malformed YAML/JSON syntax first. An invalid source or signal can prevent dependent checks; blocked_checks explains those checks instead of inventing values. Run validation again after repairs. A configuration error prevents run from starting analysis. Static checks may read DBC metadata when configuration defaults require it, but do not read business message contents.

The run summary returns the actual manifest path; batch run returns the actual report path. Output filenames receive a timestamp suffix; see [result publication](results.md#result-publication).

## AI guide

`chronaxis guide` prints the absolute Chinese README path; `chronaxis guide --language en` selects English. Neither writes files. Optional `--output new-file.zip` saves a complete bilingual copy; its parent must exist and the target must be new. See [AI guide](ai-guide.md).
