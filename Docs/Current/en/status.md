<a id="支持范围与限制"></a>
# Supported features and requirements

Use this page to determine whether the current version can process your inputs and task. Configuration version is the integer `3`. YAML suits hand-written plans; JSON is also supported. Software version `0.1.0.dev0` is a development preview, installable from a wheel or public source; see [installation](installation.md).

| Area | Supported scope |
|---|---|
| Inputs | In-memory records, decoded-signal CSV, and BLF/ASC/raw CAN CSV with DBC. See [sources](inputs.md) for file, channel and format requirements. |
| Analysis | Expressions, sustained conditions, edges, hysteresis, debouncing, start/end activities, window deltas, request/response matching, event windows, statistics, integration and per-message accumulation. |
| Execution | Python API and CLI; `reference` and `numpy` calculation implementations; independent batch tasks; managed memory and temporary-storage budgets. |
| Outputs | CSV or JSONL summaries, run manifests, optional contributions/input provenance, signal CSV and CAN message exports. |
| Configuration tools | Templates, YAML/JSON conversion, standalone configuration export, one level of shared definitions, field origins, explicit old-INI import. |
| Environment | Python >=3.12 and <3.13; Windows/Python 3.12 verified. Results are first completed in a temporary directory and files closed, then the whole directory is renamed to the target. Existing targets are rejected. This publication procedure has been validated only on Windows; see [result publication](results.md#result-publication). |

<a id="需要自行确认的条件"></a>
## Information needed from your data

Establish time synchronization, signal units and direction, measurement location, validity periods and engineering thresholds. Loading a configuration does not read business messages. If signal `dtype`, `unit`, `period` or enum `choices` are omitted, the relevant rules may obtain them from DBC. Supply `frame_id` and `signal`; channel can be omitted only when unique. Standard/extended and CAN/FD flags can be determined automatically when there is one candidate; otherwise specify them. See [signal binding](signals.md) and [sources](inputs.md). DBC metadata does not validate recorded content. Synthetic examples demonstrate calculations, not a particular device's business results.

Some export paths still require `metadata.device_label` to be `home` or `work`; see [output requirements](exports.md). Memory budgets cover managed resources, not the entire Python process. Parallel tasks and the NumPy implementation should be measured on your actual workload rather than assumed faster for every input.
