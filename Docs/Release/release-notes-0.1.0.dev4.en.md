# Chronaxis 0.1.0.dev4

[简体中文](release-notes-0.1.0.dev4.md)

> Development preview 0.1.0.dev4. These notes describe its changes, installation and verified support boundaries.

This version improves default inputs, execution efficiency and cleanup, while removing unnecessary usage restrictions. Analysis configurations still require the integer `config_version: 4`; sustained conditions still require an explicit `duration_comparison`.

## Inputs and outputs

| Improvement | Effect on usage |
|---|---|
| Signal CSV memory accounting | Batch delivery considers actual records, text and packing space. `batch_rows` remains an upper bound. Ordinary narrow tables no longer fail because per-record memory was overestimated or charged again during packing; there is no need to change every configuration to 4096. |
| CSV text format | Default `utf-8-sig` accepts plain UTF-8 and a leading BOM. Unnamed trailing header columns are ignored only when their corresponding cells are empty. Nonempty data, unnamed middle columns and duplicate names still fail. |
| Common ASC records | Supported statistical tails, status events and error-frame layouts are recognized by default; malformed rows retain precise errors. Omitted remote-frame DLC stays unknown. ASC export preserves the omission; BLF export does not invent a length. |
| Device labels and directories | Device labels may be omitted or supplied as nonblank text, including `lab-pc` or Chinese names. Customer directories may be called `RefProjects`. Publication still preserves existing results and other users' files. |
| File patterns | Explicit extensions such as `*.asc`, `*.blf`, `*.csv` and `*.txt` match extension letters without regard to case. Stems, directory names and other patterns retain host rules. Recursion still requires explicit `**`. |

See [Input sources](../Current/en/inputs.md) and [Outputs and results](../Current/en/results.md) for the complete rules.

## Default budgets and example acceptance

- Shared signal declarations are charged once per analysis. New expressions, indexes and independent state still incur their own costs; adding signals and calculations no longer repeatedly expands the same declaration in the budget.
- Exact medians and quantiles reserve space for retained samples before allocating each temporary batch. Genuine capacity exhaustion still fails. The default memory budget remains 256 MiB.
- Power-statistics examples consistently use `W^2` for variance. The result index records the generating product-source digest; product changes require rerunning the examples. Installed-package checks independently verify fixed headers, units, statuses and hand-calculated values.

## Execution, cleanup and interfaces

- Ordinary analysis defaults to `execution.backend: auto`, selecting a verified implementation from the whole plan. Explicit `reference` and `numpy` choices are preserved. Explain reports the request, selection and reason.
- Simple actual-time ZOH session integrals of one or two signals in the same CAN message can avoid intermediate grouping and state handoffs. ASC, BLF, raw CAN CSV and continuous volumes follow the same rules; validity, missing values, units, actual boundaries and cleanup remain intact. See [execution settings](../Current/en/execution.md) for eligibility.

- Built-in streaming expressions evaluate the current values directly, avoiding repeated single-element array construction. Genuine array calculations and the independent `reference` numerical implementation remain available. Benefits depend on the input and workload; there is no uniform speedup guarantee.
- Accounting reuses the cost of unchanged state rather than repeatedly traversing it. Necessary temporary arrays, variable payloads and copies remain budgeted. Managed estimates are not a bound on total process RSS.
- Ordinary ASC/BLF concatenation with the default single process reads and decodes inline. File parallelism and `time_order` use their respective worker rules. Independent batch jobs no longer create a separate equivalent reader process solely to read pure BLF. See [execution choices](../Current/en/continuous-files.md).
- CAN reading and BLF writing use shared implementations. Existing source and policy-specific decoding failures remain distinct; shared code does not make every failure behave identically.
- Business data blocks and control messages use fixed fields with size limits. Cancellation, construction failures and failed closes preserve recovery access to resources that remain open; cleanup errors do not replace the initial error.
- `SignalSample` runtime annotations are corrected while preserving the original `ScalarValue` import path and class identity. Unused internal execution modules are retired with behavioral coverage retained at current entry points.
- Compound units use reparsable forms such as `W/s`, `1/W` and `1/J`. This changes canonical display while preserving the `mA` scale, temperature offsets and the quantity kind of `N*m`; it does not convert `N*m` automatically to `J`.
- Omitting `RunMetadata.software_version` reads the current software version. Explicit historical values are preserved.

Performance evidence comes from paired runs using the same task, input and output checks. These notes do not assign measurements from different semantics to a shared speedup claim. The earlier ten-file real-log performance gap has not been closed by these changes.

## Platform and dependency scope

This version declares Python `>=3.12,<3.14`. NumPy is `>=1.26.3,<2.6` on Python 3.12 and `>=2.1,<2.6` on Python 3.13; cantools is `>=39.4.3,<46` and jsonschema is `>=4.25.1,<4.27`. See [Installation](../Current/en/installation.md) for other dependencies and [constraints](../../requirements/README.md) for exact environment snapshots. Testing lower and upper combinations does not test every intervening version or all cross-combinations.

Managed Linux workers require Python pidfd interfaces and actual kernel support for process-group signals. Non-overwriting publication requires libc `renameat2` and target-filesystem support for `RENAME_NOREPLACE`. The worker requirements do not apply to static validation or computations that run without managed workers. Existing Linux candidate checks cover x86_64, WSL2 kernel 6.18.54.1, Debian glibc 2.41, Python 3.12.15 and container overlayfs. They do not establish support for other filesystems, architectures, native Linux hosts or macOS.

DBC loading uses an interface that does not enter persistent caching, including when `CANTOOLS_CACHE_DIR` is set. It does not modify the process environment or imply that the upstream diskcache vulnerability is fixed. See [Security](security.md) and [Third-party licensing](third-party.md) for installation and redistribution details.

## Install this version

Install this version from PyPI in a new environment and check your workload:

```powershell
py -3.12 -m venv .venv-dev4
.\.venv-dev4\Scripts\python.exe -m pip install "chronaxis==0.1.0.dev4"
.\.venv-dev4\Scripts\python.exe -m pip check
.\.venv-dev4\Scripts\python.exe -m chronaxis guide --language en
```

When upgrading, check CSV encoding, dependency constraints, Linux execution capabilities and external code that compares unit strings. Signal validity, sustained-condition comparisons, integration timing and requested outputs do not change automatically because of these performance improvements.

Maintainer: liuyaoze, work@liuyaoze.com.
