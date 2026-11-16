# Chronaxis 0.1.0.dev5

[简体中文](release-notes-0.1.0.dev5.md)

> Development preview 0.1.0.dev5. These notes describe its changes, installation and verified support boundaries.

This version mainly speeds up common integrations and ASC reading, and lets integrals over continuous file volumes be computed in file workers. Analysis plans still use the integer `config_version: 4`. The public API, configuration fields and result formats are unchanged; existing plans need no edits.

## Automatic selection and general computation

| Improvement | What changes in use |
|---|---|
| Automatic implementation selection | When `execution.backend` is omitted (`auto`), validated combinations such as integrals, sustained conditions, windows, extremes and counts now select the `reference` streaming implementation. The choice is made from the whole plan before data is read; explicit `reference` or `numpy` keeps its choice. `selected_backend` in `explain` and the run manifest may therefore differ from dev4; results stay consistent within the existing tolerances. |
| Common ASC data lines | Records matching the classic CAN data-line format use a faster parser; times are still converted exactly to integer nanoseconds. Other line shapes and special cases keep the original parser. Both ordinary analysis and `chronaxis fast` benefit when reading ASC. |
| General numeric overhead | Fixed costs are reduced in quality-flag merging, repeated expression-node work, repeated validation of numeric objects and integral error-term updates. The gain depends on the selected implementation and the requested calculations. |
| Direct integration within one message | With the default `auto`, simple formulas over finite floating-point signals from the same message, integrated over actual frame intervals, are compiled ahead of time with fewer temporary objects. Fixed or DBC cycle intervals do not use this path. |

## Integrals across continuous volumes

When several ASC/BLF files of one source are read consecutively with `file_merge: concatenate` and `execution.process_count` is greater than 1, eligible session integrals can now be computed in file workers. Workers compute the integral area inside each file; the main process handles the boundaries between files and accumulates in the original order. Numeric results, cross-file state, validity and budget rules are unchanged, and no new setting is needed.

See [Continuous files](../Current/en/continuous-files.md) and [Execution](../Current/en/execution.md#integral-path-conditions) for the conditions: default `auto`, simple session integrals within one physical message, actual frame intervals with zero-order hold, and no rules, windows, conditions, lookups, exports or tracing. If the budget does not fit, the original path is used before the first frame is read. Single files, a single process, `time_order`, fixed or DBC cycles, explicit `reference`/`numpy` and `chronaxis fast` do not use this mode.

## Reading the performance results

The figures below come from paired runs with the same task, input and result checks on one Windows computer. They describe only the measured scenarios:

- One ASC file with a fixed cycle: ordinary analysis about 11.22→6.16 s, `chronaxis fast` about 8.10→3.16 s; integration over actual frame intervals about 11.94→5.10 s.
- One real BLF integrated over actual frame intervals: about 8.87→7.61 s.
- Integrals across continuous volumes: sparse ASC took about 49% less time with 4 or 8 workers, and six dense integrals about 38% less with 4 workers. In this data set one process was still fastest or close to four; more processes do not guarantee a faster run.
- The user's ten real BLF files (fixed cycle) changed by about −1.5% to +0.7% between old and new versions, which is not a clear improvement.

## User manual included in the package

After installing from PyPI or a wheel, the installation contains the complete user manual in Markdown: Chinese and English chapters, public API pages and all examples. Run `python -m chronaxis manual` to print the Chinese home page path, or add `--language en` for English; the command only prints the path and writes no files. The manual's examples can be run directly, with results written to a directory you choose. Links to the internal module reference and source code point to the same files for this version on GitHub. The HTML manual with navigation and search remains available on the website and as a Release attachment.

## Manual and AI guide

The manual now explains where to run the bundled examples, clarifies the file-worker limit and optional fields, and separates expression scope, implementation choice, reading mode and where integration is computed. The Chinese and English manuals, API reference and bundled AI guide are synchronized.

## Platform and dependency scope

Unchanged from dev4: Python `>=3.12,<3.14`; NumPy `>=1.26.3,<2.6` on Python 3.12 and `>=2.1,<2.6` on Python 3.13; cantools `>=39.4.3,<46`; jsonschema `>=4.25.1,<4.27`. See [Installation](../Current/en/installation.md) for other dependencies and [constraints](../../requirements/README.md) for exact environment snapshots. Linux worker and publication requirements still follow [Installation](../Current/en/installation.md). This version's performance figures were measured only on Windows; integration across continuous volumes was not benchmarked on Linux.

## Install this version

Install this version from PyPI in a new environment and check your workload:

```powershell
py -3.12 -m venv .venv-dev5
.\.venv-dev5\Scripts\python.exe -m pip install "chronaxis==0.1.0.dev5"
.\.venv-dev5\Scripts\python.exe -m pip check
.\.venv-dev5\Scripts\python.exe -m chronaxis guide --language en
.\.venv-dev5\Scripts\python.exe -m chronaxis manual --language en
```

When upgrading, use `explain` to see which implementation was selected automatically. Signal validity, sustained-condition comparisons, integration timing and requested outputs do not change automatically because of these performance improvements.

Maintainer: liuyaoze, work@liuyaoze.com.
