# Generate, convert, and resolve configurations

<a id="配置生成-转换与展开"></a>

The `chronaxis config` command group works on configuration files: `init` creates a template with inputs, `convert` changes file representation, `resolve` writes the expanded configuration, and `origins` identifies where definitions or fields were declared. These commands do not run the business analysis. Complete [installation](installation.md), then run the commands in a terminal.

<a id="配置工具参数"></a>
## Configuration tool options

`SCENE` and `INPUT` below are command-line placeholders; replace them with a scene name or file path. Options such as `--output` belong to the command line, not to `analysis.yaml`. An option is only valid for the listed subcommands. Choose your own paths and obtain supported scene names with `config init --list`.

| Argument or option | Command | Purpose, accepted values, and omission behavior |
|---|---|---|
| `SCENE` | `init` | Required when generating a template. Select a name from `--list`, such as `can-asc` or `can-blf`. |
| `INPUT` | `convert`, `resolve`, `origins` | Required existing configuration path. Relative paths start at the current working directory. |
| `--list` | `init` | Flag without a value. List all scenes and exit; do not also supply a scene or output directory. |
| `--style` | `init` | `annotated` (default) includes full comments; `minimal` represents the same configuration with fewer comments. It does not remove functionality. |
| `--output` | `init` | Required new template directory; its parent must exist. |
| `--output` | `convert` | Required new file. `.yaml`/`.yml` writes YAML and `.json` writes JSON. Configurations with relative paths must remain in the same directory. |
| `--output` | `resolve` | Optional new file; otherwise print to the terminal. The suffix selects the format; the parent directory must be available. |
| `--format` | `resolve` | `yaml` or `json`. Terminal output defaults to YAML. When writing a file, an explicit format must match its suffix. |
| `--defaults` | `resolve` | Flag without a value. Include applicable defaults; otherwise preserve explicit declarations. Only determinable configuration defaults are expanded. Missing CAN types, input/target units, or enum information may require reading the specified DBC. |
| `--fields` | `origins` | Flag without a value. List individual user-declared field locations; otherwise list source, signal, and derived-definition origins. |
| `--format` | `origins` | `text` (default) or `json`. JSON is an origin report for tools, not an expanded analysis configuration. |

<a id="生成配置模板"></a>
## Generate a template

The [AI guide](ai-guide.md) can help an assistant choose a scene or look up fields. It uses the same published configuration definitions and includes offline field lookup, runnable examples, and diagnostic explanations.

```text
chronaxis config init --list
chronaxis config init can-asc --output demo
chronaxis validate demo/plan.yaml
chronaxis explain demo/plan.yaml
chronaxis run demo/plan.yaml --output result
```

The scene must come from the catalog. `--output` must name a directory that does not exist, with an existing parent. The default `annotated` style explains individual fields; `--style minimal` produces the same values with fewer comments. ASC, BLF, and batch scenes include the small synthetic inputs they need; CSV-specific scenes are also available. Ordinary templates omit unnecessary default fields and retain parameters that serve the selected task.

Existing directories are never overwritten, even if empty. On failure, the command removes content it created; any path it cannot clean up remains in the original exception details.

The `can-export` and `signal-export` templates initially set `metadata.device_label` to `home`, identifying where the bundled synthetic example was made. The program does not detect your current computer. When using your own data, replace it with the label for that output's device; standalone exports currently accept only `home` or `work`. See [Outputs](exports.md). The catalog's own `device_label` and `data_kind` describe bundled resources and are not copied automatically into a run manifest.

Edit the existing blocks in `demo/plan.yaml`. Do not paste commands or dotted reference paths as YAML keys. See [Configuration syntax](configuration-language.md) for indentation, lists, and block replacement.

For BLF, replace `can-asc` with `can-blf`. Both templates include a matching DBC and runnable input. When using your own logs, replace their paths and bindings; converting the logs to CSV first is unnecessary.

<a id="json与yaml互转"></a>
## Convert between JSON and YAML

```text
chronaxis config convert demo/plan.yaml --output demo/plan.json
```

Conversion supports analysis configuration version 4 and batch version 1 as separate document types. It changes representation, not an older configuration structure. Types, numbers, key order, and path text are retained; comments are not. The output is parsed again to check preservation, including large integers and floating-point negative zero. The destination must not exist.

When paths are relative, conversion is allowed only within the same directory, so unchanged text continues to identify the same files. Use `resolve` to write a configuration elsewhere with fixed input locations.

<a id="查看实际采用的配置"></a>
## Inspect the effective configuration

```text
chronaxis config resolve demo/plan.yaml
chronaxis config resolve demo/plan.yaml --defaults --format json
chronaxis config resolve demo/plan.yaml --defaults --output elsewhere/effective.yaml
```

`resolve` expands one level of imports in declaration order, then writes preset-generated derived signals, rules, windows, and calculations as ordinary declarations. It removes imports and expanded presets so they will not create duplicate objects when loaded again.

Without `--output`, the terminal contains only configuration text, in YAML by default. Use `--format json` for JSON or redirection to another program. For file output, the extension selects the format; a conflicting explicit `--format` is an error.

`--defaults` also writes applicable execution budgets, backend, output and diagnostic switches, decoder/CSV settings, signal hold and same-time policies, rule confirmation settings, calculation units and coverage/inheritance policies, sequence capacities, and effective node intervals. It uses the current `reader`, `conversion`, `time.clock`, object `scope`, and node `interval` structures. It does not add irrelevant rule fields, guess business thresholds, or invent a period without reading the DBC. Loading a CAN plan can read the DBC to fill omitted `dtype`, `unit`, or enum `choices`. Version 4 also fills omitted `conversion.input_unit` and obtains the original enum code type when required. No extra DBC read for defaults is needed only when all required information is explicit. Without `--defaults`, explicit values are retained.

Input, DBC, and batch-child plan paths become absolute paths based on their declaring files. They are joined and normalized lexically; symlink and directory-junction targets are not resolved. The command does not read messages or physical signal data, copy data, or modify original files. Directory/glob expansion enumerates filenames, and missing CAN metadata may require a DBC read.

The output can be loaded independently from another directory. On another computer, its input paths must still be accessible. Explicitly adding defaults or expanding a preset changes hashes derived from configuration declarations; that does not mean the algorithm changed.

Exit codes are `2` for configuration errors, `1` for file errors, and `130` for cancellation. Existing destinations, including hard links, are never overwritten.

Use `config origins INPUT` to locate definitions. `--fields` lists explicitly declared fields that supply effective values, such as `signals[0].unit`, without program-generated defaults. This dotted expression describes a location, not a literal key. `--format json` gives a structured report, not a runnable analysis configuration. The command does not write files or mix this report with resolved configuration text. See [Shared definitions](imports.md).
