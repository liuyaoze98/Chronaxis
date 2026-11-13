<a id="用-ai-编写-chronaxis-分析"></a>
# Use AI to write a Chronaxis analysis

Start with this README, select an example from the [task index](tasks.json), and read only the material needed for the task. Reading the guide in a source checkout requires no installation, generated files, or ZIP export; keep the repository layout intact. The standalone documentation ZIP uses the same text with its own complete directory layout.

Give the AI this README and the [documentation version](../../Current/documentation.json), then supply examples, API descriptions, or field references as needed. Relative commands use the directory containing this README unless noted otherwise; installed users can use the working-directory example below. ASC and DBC paths inside a configuration are relative to that configuration file. Running an analysis requires the matching Chronaxis version; check it with `python -c "from importlib.metadata import version; print(version('chronaxis'))"`. The installed package includes the guide as ordinary files. `python -m chronaxis guide --language en` prints this English README path without writing or extracting anything. Open it directly; source documentation is also directly readable. Version metadata and synthetic examples do not establish that private logs have been verified.

<a id="安装chronaxis及默认运行依赖"></a>
### Use the installed guide directly

Run these PowerShell commands from your own working directory. They read the installed guide and example directly and put results in your working directory, without copying or modifying the installed material:

```powershell
$guide = Split-Path (python -m chronaxis guide)
python "$guide/lookup.py" --language en task CONDITION_ENERGY
python "$guide/run_analysis.py" "$guide/examples/conditional-energy.yaml" result-energy
```

The relative commands below illustrate a source or standalone guide directory. For installed examples, use full input paths and your own output directory as above.

## Install Chronaxis and its default dependencies

A normal installation includes the runtime dependencies for BLF, ASC, raw-message CSV, DBC decoding, decoded-signal CSV, and memory tasks. These Windows PowerShell commands create an environment and install the local 0.1.0.dev4 wheel matching this guide. Substitute its actual file path:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev4-py3-none-any.whl"
.\.venv\Scripts\python.exe -m pip check
```

You can also obtain the matching source tree, create the environment at its root containing `pyproject.toml`, and replace the installation command with `.\.venv\Scripts\python.exe -m pip install .`.

Use the same `.venv\Scripts\python.exe` for subsequent commands; activation is optional. Python 3.12 and 3.13 are allowed. Default CAN dependencies are `python-can==4.6.1`, `cantools>=39.4.3,<46` and `natsort==8.4.0`, constrained by the installed wheel metadata. NumPy requires `>=1.26.3,<2.6` on Python 3.12 and `>=2.1,<2.6` on Python 3.13; jsonschema requires `>=4.25.1,<4.27`. The source `requirements/` directory contains four exact Windows environment snapshots. Allowed ranges do not prove every intermediate or cross-combination was tested. Use the release or wheel requested by the user, and prepare dependency wheels for offline installation. Do not change signals, thresholds or the DBC to fix an installation error.

`dependency_missing` means the environment lacks required CAN dependencies, not that a signal binding is wrong. Follow the local-wheel installation command in the error. Even if every signal's metadata is supplied manually and static validation passes, execution still needs the appropriate reading and decoding dependencies.

<a id="我该读哪几份文件"></a>
## Which files should I read?

First read [from input to results](workflow.md) to choose a single analysis, preset, or independent batch.

After querying a task, read the materials in its `references` list, then open the complete configuration named by `example`. Paths are relative to this language’s README directory. A fragment after `#` in a JSON reference identifies the schema node to read.

Select by calculation meaning, rather than matching only the word “energy”:

| Requested result | Task and entry point |
|---|---|
| Custom analysis operators | `HOST_EXTENSION`; [registry API](../../Current/en/public-api/ExtensionRegistry.md) and the task's host script. |
| Aggregate calculation rows, sequence delays, event counts or segment counts | `POWER_STATISTICS`; [statistics and grouping example](../../Current/examples/power-statistics.yaml). |
| One-dimensional calibration lookup | `CALIBRATION`; [lookup configuration](../../Current/examples/lookup-power.yaml). |
| Accumulate target-message contributions through the general runner, including contribution details | `MESSAGE_ENERGY`, using general `run`; [complete minimal configuration](../../Current/examples/message-minimal.yaml). |
| Integrate over each entire interval whose condition lasts beyond a threshold | `CONDITION_ENERGY`, using general `run` or `run_analysis.py`. |
| In one ASC/BLF source, calculate each target frame's fixed-period contribution using inputs from that frame | `FAST_MESSAGE_ENERGY` in the high-performance integrator (same-frame per-message accumulation), using `fast validate/explain/run`. |
| Process the latter independent files from one template in parallel and total comparable metrics | `FAST_TEMPLATE_TOTAL`, using `fast batch --total`; see [complete batch configuration](../../Current/examples/fast/batch.yaml). |

`run_analysis.py` runs a general analysis; it does not automatically select fast. Follow the task-specific commands for fast. Batch files use root `batch_version: 1`; their referenced analysis files separately declare `config_version`.

1. Search the [task index](tasks.json) for the requested task. Read that entry's example, applicability, and related fields. Start with BLF/ASC plus DBC for CAN tasks. Decoded CSV tables do not need a DBC. Do not mix configuration or internal functions from another release.
2. Write YAML or JSON using integer `config_version: 4`. Examples are complete files; preserve the layout under `../../Current/examples/data`. Their engineering values apply only to the synthetic inputs. If the real time basis, thresholds, encoding, units, or direction are missing, explain which fact is missing and how it changes the result.
3. For Python, consult the [public API index](../../Current/en/public-api.json), then the individual API page. Use `load_analysis_plan` for files and `AnalysisPlan.from_dict` for expanded dictionaries. Preset construction returns a `PlanFragment`, which cannot be passed directly to `run`. Inspect every task status after a batch returns.
4. Load the configuration, validate declarations, inspect dependencies, run, and write the output. Commands are below; the [complete Python call](../run_analysis.py) provides the executable path. Report actual inputs, units, boundaries, quality, and unverified parts. Returning from calculation is not the same as publishing results.

<a id="一个从输入到结果的任务"></a>
## Choose execution workers

For continuous volumes from one ASC/BLF source, add this block at the analysis root. If `execution` already exists, merge `process_count` into it instead of repeating the parent key:

```yaml
execution:                     # Execution settings for this analysis
  process_count: 4             # File-worker limit 4; creation and count depend on inputs and merge mode
```

In a general analysis, workers read and decode while the main process preserves events and integration across files. High-performance integrator workers also evaluate same-frame contributions. Four is this manual's starting limit; the software default remains one. A single ASC using default concatenation reads in the current process, with ordinary `read_process_limit: 0`. Ordinary `time_order` uses one file child even at a configured limit of 1. Plan limits are not measured PIDs. Four is not optimal on every machine: more workers use more resources, so adjust it for your inputs.

Independent trials use batch-root `process_count: 4` and `execution.process_count: 1` in each child plan to avoid nested file pools. A CSV, memory, multi-source or `decode_scope: all` plan currently sets the limit to 1 and reads in the current process. Independent trials can run in an outer batch; do not split a continuous session merely to obtain parallelism. Put Python execution under `if __name__ == "__main__":`; the supplied `run_analysis.py` already does this.

## A complete task

Query the material with standard Python from this README's directory instead of reading the whole specification:

```text
python ../lookup.py --language en task energy
python ../lookup.py --language en api AnalysisRunner
python ../lookup.py --language en field valid_for --schema analysis
python ../lookup.py --language en field source_type --schema analysis --branch can_asc
```

Field tables identify their specification location and branch. See [semantics and diagnostics](semantics.md) and the [complete field reference](../../Current/en/reference/configuration-schema.md). Conditional requirements, references, time units, and engineering requirements depend on the complete specification and runtime validation. Individual field extracts are not standalone validators. A query without matches exits with code 1: check the version, name, or branch instead of inventing an equivalent field.

On Windows with Python 3.12 and the package's default runtime dependencies installed:

```text
python -m chronaxis config init --list
python -m chronaxis validate ../../Current/examples/conditional-energy.yaml --format json
python -m chronaxis explain ../../Current/examples/conditional-energy.yaml --format json
python ../run_analysis.py ../../Current/examples/conditional-energy.yaml result-energy
```

This example reads two continuous ASC volumes and decodes state, current, and voltage with a DBC. It requires `state == 0x2 and current >= 10` for strictly more than 60 seconds, then integrates over the entire qualifying event. The first activity lasts exactly 60 seconds and is excluded. The second crosses the file boundary, covers `[61,122)` seconds, and gives `4000 × 61 / 3600000 = 0.06777777777777777 kWh`. Integration starts at condition onset by default, including the first 60 seconds. `confirmed_ns=121000000001` is the strict-duration confirmation time, not the integration start. Use task `CONDITION_ENERGY`; `CHARGE` is not a replacement when its current comparison differs.

The output directory can be reused; this publication uses a common timestamp suffix. Default `readable_csv` output places exact-second boundaries and `energy_kwh（kWh）` on the same row in `事件结果_<run timestamp>.csv` (event results). Check each metric's status and explanation. Read the manifest path returned by the CLI or API, then use its `outputs` list to find this publication's files. To consume original interchange tables linked by `parent_id`, explicitly select `outputs.tables: csv` or `jsonl`. CLI and manifest `analysis_outcome` distinguish no observation, unknown conditions, conditions not met, insufficient duration, and detected events. No event does not mean zero energy. [View the actual teaching-example result table](../../Current/examples/results/conditional-energy-yaml/事件结果.csv).

For your own data, replace paths, IDs, signals, and conditions using the actual DBC. Decoded tables can use task `CSV`. Do not treat synthetic thresholds as the user's production parameters.

Validation and explanation establish declaration validity and supported execution paths. Loading may read DBC metadata or enumerate directories as needed, but it does not scan business records. Report success only after actual execution, publication, and cleanup finish. An independent example does not establish that another device has the same business meaning.

## Choose a runner for continuous analysis

Start with `CONTINUOUS_FILES` for ASC/BLF volumes from one recording: one analysis configuration and one source preserve signal state, events and integration across file boundaries. Use ordinary analysis for duration conditions, cross-frame values, events/windows or actual-time integration. The duration-conditioned energy example uses `CONDITION_ENERGY`; splitting its recording into several files does not make it a fast task.

Choose `FAST_CONTINUOUS_SESSION` only when every signal input in a formula comes from the current message, each message provides an independently additive contribution, and none of the capabilities above are needed. Here `execution.process_count` limits read/decode/current-message workers and `file_merge` controls file organization. The main process accumulates in the prescribed order; file partial sums cannot replace ordered session accumulation. Separate trials use ordinary batch or fast `FAST_TEMPLATE_TOTAL` according to their analysis requirements; do not split a continuous session into independent trials.

Cancellation of `fast.run` raises `InterruptedError`. A managed memory budget is not a physical-memory limit for the whole process tree.
