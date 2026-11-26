# Chronaxis 0.1.0

[简体中文](release-notes-0.1.0.md)

> 0.1.0 is the first regular release of Chronaxis in the 0.x series; the earlier releases 0.1.0.dev0–0.1.0.dev6 were development previews. These notes describe the changes since 0.1.0.dev6, what to change when upgrading, installation, and the verified support boundaries.

This version corrects three problems in 0.1.0.dev6. Two of them are incompatible changes: before upgrading from dev6 or earlier, check your configurations and any programs that read the run manifest against the next section. Analysis plans still use the integer `config_version: 4`. Interfaces and configuration may still change during 0.x; incompatible changes are listed with migration steps in the release notes, as described in the [version policy](versioning.md).

## What to change before upgrading

| Change | Effect | What to do |
|---|---|---|
| Duration rules referenced by calculations must state `selection_origin` | When a `condition_duration` rule is referenced by a calculation's `scope: {rule: name}` and has no `selection_origin`, dev6 silently used `onset`, with no hint in validation or results. This version reports a validation error naming the rule, the calculations that reference it, and both choices. The two choices can give very different results: the conditional energy example gives 0.06777777777777777 kWh with `onset` and 0.00111111111 kWh with `confirmed`. | To keep the dev6 result, add `selection_origin: onset` to the rule; write `confirmed` to start statistics at confirmation. Rules that no calculation references may still omit it. |
| `worker_config` removed from the run manifest | In dev6, `run.worker_config` was always `single-thread`, regardless of the actual parallelism. This version removes the key and adds `run.process_count` (the effective file-worker limit, including command-line or Python overrides) and `run.worker_process_count` (the number of file workers that actually started and did the work; 0 means everything ran in the main process). The public class `RunMetadata` also drops its `worker_config` field, so code passing positional arguments would shift. | Programs that read the manifest should read the two new keys; construct `RunMetadata` with keyword arguments. |

## Other changes

- Event result tables add a `统计开始（s）` (statistics start) column after the metric columns, giving the time from which each event's metrics are calculated; rows without event metrics leave it blank. When duration rules are referenced by event-scoped calculations, the run manifest also records `selection_origins`.
- The AI guide now states the process-count parameter correctly: it belongs to methods such as `AnalysisRunner().run(plan, process_count=4)`, and the `AnalysisRunner(...)` constructor does not accept it. Documentation checks now verify that copyable calls match the actual public signatures.
- The Chinese and English manuals, AI guide, and examples are synchronized: affected examples write `selection_origin: onset` explicitly with unchanged values, and troubleshooting explains what to do when the statistics start is missing.

Apart from the new column, the results of the 78 bundled examples are identical to 0.1.0.dev6 cell by cell. This version does not change the reading, decoding, or integration paths and was not re-benchmarked; the performance figures in the dev5 and dev6 release notes still describe the scenarios they measured.

## Platform and dependency scope

Unchanged from 0.1.0.dev6: Python `>=3.12,<3.14`; NumPy `>=1.26.3,<2.6` on Python 3.12 and `>=2.1,<2.6` on Python 3.13; cantools `>=39.4.3,<46`; jsonschema `>=4.25.1,<4.27`. See [Installation](../Current/en/installation.md) for other dependencies and [constraints](../../requirements/README.md) for exact environment snapshots. Linux worker and publication requirements still follow [Installation](../Current/en/installation.md); this version was verified on Windows with Python 3.12.

## Install this version

Install this version from PyPI in a new environment and check your workload:

```powershell
py -3.12 -m venv .venv-010
.\.venv-010\Scripts\python.exe -m pip install "chronaxis==0.1.0"
.\.venv-010\Scripts\python.exe -m pip check
.\.venv-010\Scripts\python.exe -m chronaxis guide --language en
.\.venv-010\Scripts\python.exe -m chronaxis manual --language en
```

After upgrading, run `python -m chronaxis validate <configuration file>` on your own configurations first; if it reports a missing `selection_origin`, add it as described above before running the analysis.

Maintainer: liuyaoze, work@liuyaoze.com.
