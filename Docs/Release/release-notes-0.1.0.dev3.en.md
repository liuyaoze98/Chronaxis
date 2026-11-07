# Chronaxis 0.1.0.dev3

Fast run now supports ASC/BLF volumes from one recording. execution.process_count controls reading, decoding and current-message workers; the main process accumulates contributions in file_merge order. Python fast.run and CLI accept process-count overrides. Independent fast batch retains local job accumulation and rejects nested pools. See [Fast](../Current/en/fast-energy.md) for fields, limits and complete examples.

Ordinary AnalysisRunner and run/validate/explain now accept a process_count override. execution.process_count limits reading and decoding of ASC/BLF files in one continuous session; file_merge independently selects concatenation or stable time merging. See [continuous recordings](../Current/en/continuous-files.md).

[简体中文](release-notes-0.1.0.dev3.md)

This version requires sustained conditions to explicitly choose whether to reach or strictly exceed the duration threshold, and improves configuration diagnostics. It supports Windows and Python 3.12. Analysis configurations continue to use the integer `config_version: 4`.

## Install the matching version

After obtaining the local wheel, create an environment in Windows PowerShell and substitute its actual file path:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev3-py3-none-any.whl"
.\.venv\Scripts\python.exe -m chronaxis guide --language en
```

To install from the matching source tree, create the environment at its root containing `pyproject.toml` and replace the installation command with `.\.venv\Scripts\python.exe -m pip install .`. See [Installation](../Current/en/installation.md) for dependencies and offline setup.

## Choose how sustained conditions compare duration

Rules with `rule_type: condition_duration` must supply `duration_comparison`. Omitting it produces a missing-field diagnostic during configuration validation, preventing “more than” from being silently interpreted as “at least.”

| Value | Meaning | When the threshold is 60s and the condition holds for exactly 60s |
|---|---|---|
| `">="` | Reach the minimum duration, including equality | The interval qualifies |
| `">"` | Strictly exceed the minimum duration | The interval does not qualify |

When upgrading from 0.1.0.dev2, check each sustained-condition rule:

- Keep any comparison that is already explicit.
- Previously, an omitted comparison used `">="`. To preserve that behavior, add `duration_comparison: ">="`.
- If the requirement is strictly “more than 60 seconds,” use `duration_comparison: ">"` and check whether intervals exactly at the threshold are selected. Do not fill every older rule with the same value regardless of its intended meaning.

The integration algorithm, interval choices and unit conversion are unchanged. The comparison determines which intervals participate in the calculation, so changing it can change the selected events and accumulated energy. See the complete [sustained-condition integral example](../Current/en/conditional-energy.md).

## Other fixes

| Area | Corrected behavior |
|---|---|
| Configuration error text | Converts JSON Schema failures into readable Chinese diagnostics with the relevant field locations, rather than exposing the validator's internal English expressions. |
| Missing calculation operation | When `calculations[].operation` is missing, identifies that field without also demanding `rule`, `window`, or other fields belonging to unrelated calculation types. Other independent errors can still be reported together. |
| Standard-library-only import test | Uses an isolated interpreter to load only the Chronaxis package under test. Root imports and command help are checked without NumPy, python-can, cantools or jsonschema. The test works with source and installed packages without relying on an external `PYTHONPATH`. |

Under the [version policy](versioning.md), changes to an uploaded development preview use a new development version number. These changes use `0.1.0.dev3`; the existing `0.1.0.dev2` distribution remains unchanged.

Maintainer: liuyaoze, work@liuyaoze.com.
