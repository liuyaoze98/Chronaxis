# Chronaxis 0.1.0.dev6

[简体中文](release-notes-0.1.0.dev6.md)

> Development preview 0.1.0.dev6. These notes describe its changes, installation and verified support boundaries.

This version further speeds up ASC/BLF integrals and corrects an error in dev5's parallel integration across continuous volumes: when the same message had different actual frame types in consecutive files, dev5 could return a value, whereas this version reports the same error as the general calculation path (see "Correction" below). Analysis plans still use the integer `config_version: 4`. The public API, configuration fields and result formats are unchanged; existing plans need no edits.

## More integrals use direct and parallel integration

| Improvement | What changes in use |
|---|---|
| Fixed intervals and DBC periods | In dev5, only integrals over actual frame intervals (`actual`) could use direct integration within one message and parallel integration across continuous volumes. In this version, both paths are also available when every integral uses the same fixed interval (`fixed`) or every integral uses the DBC period (`dbc`). The timing driver must be a signal referenced by the integral expression (the driver chosen automatically when `driver` is omitted satisfies this); the DBC period is taken for that message from the DBC loaded for the run. Integrals that mix interval bases, use different fixed values or are driven by a signal from another message keep the general calculation path. |
| Files merged by time (`time_order`) | In dev5, all `time_order` integration ran in the main process. In this version, when the direct integration conditions hold, file workers group each file's messages that share a timestamp; after every file has been read, the main process merges the groups by time and file order, then evaluates and accumulates them under the original rules. This also applies when the process limit is 1. |
| `time_order` read spooling | The main process no longer fully decodes each data block as it receives it from a file; blocks are decoded once when read back for merging. This also applies to `time_order` tasks that do not meet the direct integration conditions, but the gain is limited; see below. |

These paths are selected automatically; they cannot and need not be switched on. Numeric results, cross-file state, validity and budget rules are unchanged. See [Continuous files](../Current/en/continuous-files.md) and [Execution](../Current/en/execution.md#integral-path-conditions) for the complete conditions. Integrals with a calculation `condition`, explicit `reference`/`numpy` and `chronaxis fast` do not use these paths.

## Correction: parallel integration checks frame types across files

In dev5, parallel integration with `file_merge: concatenate` and a process limit greater than 1 did not compare a message's actual frame type across consecutive files. For example, if the DBC marks a message as CAN FD, the plan omits `is_fd`, and the message is an FD frame in one file but a classic CAN frame in the next, the single-process general path reports an error asking for `is_fd`, whereas parallel integration combined both frame types into a value with status complete.

Parallel integration in this version checks frame types in file order and reports the same error as the general path, "同一报文绑定匹配多种实际帧，请补充 is_fd" (the same message binding matches several actual frame types; add is_fd). Only tasks meeting all the conditions above were affected; results for normal input are unchanged. If you obtained such a result with dev5, add the field named in the error to the signal binding (`is_fd` in this example) and run the task again.

## Reading the performance results

The figures below come from paired runs with the same task, input and result checks on one 6-core Windows computer, with three rounds per scenario for each version. They describe only the measured scenarios. Synthetic data had 200,000 raw frames in ten continuous files; "sparse" means one target message every 8 frames and one integral, and "dense" means every frame is a target message, with six integrals.

- Fixed-interval and DBC-period integrals compared with dev5 (synthetic data, `concatenate`): with 1 process, sparse runs were 1.66–1.92× and dense runs 3.44–3.71× faster; with 4 processes, sparse runs were 2.92–3.08× and dense runs 4.26–4.34× faster. For example, dense ASC with a fixed interval and 4 processes took about 115.2→26.6 s.
- Grouped-point parallel `time_order` compared with the previous code (synthetic data): with 1 process, sparse runs were 1.38–1.39× and dense runs 1.93–2.01× faster; with 4 processes, sparse runs were 1.86–1.88× and dense runs 2.48–2.52× faster.
- The user's ten real BLF files (their file times overlap, so only `time_order` applies; two unconditional integrals; fixed 10 ms and the DBC period give the same results; times below are for fixed 10 ms) were measured in two steps. Moving fixed intervals and DBC periods to direct integration took about 146.9→96.6 s with 1 process and 104.6→55.2 s with 4 processes. Moving on from there to grouped-point parallel integration took about 96.9→75.1 s and 55.3→34.5 s. The two steps did not compare dev5 and dev6 directly in one run.
- `time_order` tasks that do not meet the direct integration conditions (the same real BLF files, with conditional integrals): about 135.1→126.1 s with 1 process and 92.6→88.5 s with 4 processes, only about 6.7% and 4.5% faster.
- With file workers, the peak process-tree memory on this computer was about 7–37 MiB higher than before these changes.

In every scenario the old and new versions produced identical result rows, which also matched independent hand calculations or independent reference values. These measurements were taken when each change was completed; the later frame-type check and spool decoding changes were not fully re-timed.

## Manual and AI guide

The integration path conditions in Continuous files and the Execution appendix now cover fixed intervals, DBC periods and `time_order`, and outdated statements such as "only actual frame intervals" and "fixed or DBC periods keep the original processing" were corrected. The API reference adds types and purposes for new modules and parameters. The Chinese and English manuals, API reference and bundled AI guide are synchronized.

## Platform and dependency scope

Unchanged from dev5: Python `>=3.12,<3.14`; NumPy `>=1.26.3,<2.6` on Python 3.12 and `>=2.1,<2.6` on Python 3.13; cantools `>=39.4.3,<46`; jsonschema `>=4.25.1,<4.27`. See [Installation](../Current/en/installation.md) for other dependencies and [constraints](../../requirements/README.md) for exact environment snapshots. Linux worker and publication requirements still follow [Installation](../Current/en/installation.md). This version's performance figures were measured only on Windows; parallel integration was not benchmarked on Linux.

## Install this version

Install this version from PyPI in a new environment and check your workload:

```powershell
py -3.12 -m venv .venv-dev6
.\.venv-dev6\Scripts\python.exe -m pip install "chronaxis==0.1.0.dev6"
.\.venv-dev6\Scripts\python.exe -m pip check
.\.venv-dev6\Scripts\python.exe -m chronaxis guide --language en
.\.venv-dev6\Scripts\python.exe -m chronaxis manual --language en
```

Signal validity, sustained-condition comparisons, integration timing and requested outputs do not change automatically because of these performance improvements.

Maintainer: liuyaoze, work@liuyaoze.com.
