# Chronaxis 0.1.0.dev2

[简体中文](release-notes-0.1.0.dev2.md)

This release expands configuration diagnostics, expressions and statistical calculations, adds the high-performance integrator, and updates the Chinese and English manuals and bundled AI guide. It remains a development preview for Windows and Python 3.12.

Install or upgrade:

```powershell
python -m pip install --upgrade "chronaxis==0.1.0.dev2"
python -m chronaxis guide --language en
```

## Changes since 0.1.0.dev1

| Feature | Behavior in this release |
|---|---|
| Configuration diagnostics | Reports multiple independently identifiable configuration errors with field locations. Checks that depend on an invalid field may still require that error to be fixed first. |
| Result publication | Reuses output directories, gives files from one publication a common timestamp suffix, preserves existing files, and publishes the completion manifest last. |
| Units and expressions | Uses analysis configuration version 4, with automatic conversion of compatible units, unit-bearing constants, conditional expressions, numeric and bitwise operations, and one-dimensional calibration lookup. |
| Statistics and temporal transforms | Adds counts, variance, standard deviation, RMS, quantiles and medians, as well as result aggregation, rolling statistics and rates of change. |
| Custom analysis operators | A host Python program can explicitly register expression, statistical and temporal operators, then reference their registered names in configuration. |
| High-performance integrator | Provides separate `fast validate/explain/run` and `fast batch` entries for same-frame per-message accumulation in independent ASC/BLF files. Batch tasks can process files in parallel. This entry has a defined supported scope and does not automatically replace general analysis. |
| User documentation | Improves feature explanations, configuration examples and actual result interpretation, with bilingual manuals and an AI guide that can be read directly. Teaching results retain their original bytes across distribution formats and are checked against their summaries. |

The high-performance integrator adds the expression result from each matching message. Calculating energy from power requires the appropriate time factor in the expression. Inputs that already represent per-message energy contributions are added directly. Performance depends on the task and input; measurements of this entry do not establish performance for all analyses.

Real-data numerical and functional checks are complete, but some runtime and memory targets remain unmet. Select this integrator according to the task and available resources; this release does not establish that all performance targets have passed.

## Upgrading from an earlier version

**This release accepts only the integer `config_version: 4`.** Version 3 analysis configurations, the dedicated legacy INI import entry points and their mapping configurations have been removed. Independent batch manifests continue to use `batch_version: 1`, a separate version from analysis configuration.

Review older analysis configurations against the current examples. Changing `3` to `4` alone does not establish that the analysis retains the same meaning:

1. Check input units, target units and conversion coefficients. When both `conversion.scale` and `conversion.offset` are omitted, registered compatible units are converted automatically. Supplying either coefficient makes the program validate the complete conversion; it does not apply a second automatic conversion.
2. Check units on expression constants, comparisons and calculation outputs. Resolve errors using the current field rules, then run a small case with known inputs and results before processing actual logs.
3. Express legacy INI tasks in the current analysis format. The YAML/JSON conversion command changes file format only; it does not migrate configuration versions or old business rules.
4. If another program reads output files, locate the timestamped files through the returned run manifest instead of relying on fixed filenames.

See [signal binding](../Current/en/signals.md), [expressions](../Current/en/expressions.md), [statistics and integration](../Current/en/calculations.md), [temporal transforms](../Current/en/temporal-transforms.md), [custom analysis operators](../Current/en/host-extensions.md), and the [high-performance integrator](../Current/en/fast-energy.md).

The [online Chinese manual](https://liuyaoze98.github.io/Chronaxis/) and [English manual](https://liuyaoze98.github.io/Chronaxis/en/) cover the current release. Manuals for earlier versions remain attached to their GitHub Releases. Default runtime dependencies are unchanged from 0.1.0.dev1, and CAN support needs no extra dependency group.

Maintainer: liuyaoze, work@liuyaoze.com.
