<a id="支持范围与限制"></a>

# Supported features and requirements

This manual describes Chronaxis 0.1.0.dev4. Analysis configurations must use the integer `config_version: 4`. This version supports automatic unit conversion, statistics, rolling calculations and rates of change. Follow [Installation](installation.md) to install the matching source tree or local wheel before running the examples, and read the [upgrade notes](../../Release/release-notes-0.1.0.dev4.en.md) when moving from an earlier version. YAML suits hand-written plans; JSON is also supported.

One continuous ASC/BLF source can use an explicit reading/decoding process limit and stable time merging. See [continuous-file multiprocessing](continuous-files.md) for support and resource limits.

| Area | Supported scope |
|---|---|
| Inputs | In-memory records, decoded-signal CSV, and BLF/ASC/raw CAN CSV with DBC. See [sources](inputs.md) for file, channel and format requirements. |
| Analysis | Expressions, sustained conditions, edges, hysteresis, debouncing, start/end activities, window deltas, request/response matching, event windows, statistics, integration and per-message accumulation. |
| Version 4 additions | Automatic unit conversion, conditional expressions, lookups, variance, quantiles, result aggregation, rolling statistics and rates of change. See [Expressions](expressions.md), [Statistics](calculations.md) and [Temporal calculations](temporal-transforms.md). |
| Same-frame accumulation | Fast run supports volumes in one ASC/BLF source, with configured parallel reading, decoding and current-message evaluation, followed by ordered main-process accumulation. Fast batch is for independent trials. See [High-performance integrator](fast-energy.md). |
| Execution | Python API and CLI; `reference` and `numpy` calculation implementations; independent batch tasks; managed memory and temporary-storage budgets. |
| Outputs | CSV or JSONL summaries, run manifests, optional contributions/input provenance, signal CSV and CAN message exports. |
| Configuration tools | Templates, YAML/JSON conversion, standalone configuration export, one level of shared definitions, field origins. |
| Environment | Python `>=3.12,<3.14`; Windows, and Linux with the required process/filesystem capabilities. The actual review environments and untested platform combinations are listed in [Installation](installation.md). Results are closed before timestamped publication without overwrite; the completion manifest is published last. See [result publication](results.md#result-publication). |

<a id="需要自行确认的条件"></a>
## Information needed from your data

Establish time synchronization, signal units and direction, measurement location, validity periods and engineering thresholds. Loading a configuration does not read business messages. If signal `dtype`, `unit`, `period` or enum `choices` are omitted, the relevant rules may obtain them from DBC. Supply `frame_id` and `signal`; channel can be omitted only when unique. Standard/extended and CAN/FD flags can be determined automatically when there is one candidate; otherwise specify them. See [signal binding](signals.md) and [sources](inputs.md). DBC metadata does not validate recorded content. Synthetic examples demonstrate calculations, not a particular device's business results.

Memory budgets cover managed resources, not the entire Python process. Parallel tasks and the NumPy implementation should be measured on your actual workload rather than assumed faster for every input.
