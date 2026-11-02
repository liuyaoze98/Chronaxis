<a id="chronaxis-用户手册"></a>
# Chronaxis user manual

Chronaxis analyzes time-series data from multiple sources. Bind input columns or message fields to signals, detect events and time intervals, calculate integrals, durations and statistics, then inspect or export the results. Typical inputs are BLF or ASC logs with a DBC; raw-message CSV, decoded-signal CSV and in-memory records are also supported.

This manual describes analysis configuration `config_version: 3` and the corresponding public interfaces. [Install](installation.md) from a local wheel or source, then check the [supported features](status.md). The HTML manual includes offline navigation and search. The AI bundle's `manifest.json` records its documentation revision and product baseline.

<a id="配置使用者的阅读路线"></a>
## Reading path for configuration users

To ask AI to write configuration or Python code, start with the [AI guide](ai-guide.md), which provides the matching offline materials.

1. Follow [installation](installation.md), then run the supplied [BLF/ASC quick start](quickstart.md) and check its 38 J integral.
2. Read [field paths and YAML indentation](configuration-language.md#field-paths), [configuration structure](configuration.md), and [input sources](inputs.md). Replace the log directory, DBC, message ID and signal name with your own.
3. Choose [event rules](rules.md), [request/response matching](sequences.md), or a [calculation interval](intervals.md), then select calculations and outputs.
4. Compare the [worked example results](example-results.md) and consult [result fields](results.md). Check units, status and reasons together with values.

Configuration validation checks declarations; it does not establish that file contents, a DBC, or engineering thresholds are correct. Run each complete example with its supplied inputs before replacing them.

<a id="python开发者的阅读路线"></a>
## Reading path for Python developers

Start with the [Python quick start](api-usage.md): load a plan, validate it, execute it, iterate over results, and close resources. Consult the [public API reference](api.md) and [result structures](results.md) as needed. Implementation details are separate from public usage.

<a id="按任务查找"></a>
## Find a task

| Task | Read |
|---|---|
| Use your own BLF, ASC or CSV logs | [Sources](inputs.md), [CAN text inputs](text-inputs.md) |
| Understand time, validity periods, unknown values and partial results | [Time and result quality](concepts.md), [glossary](terms.md) |
| Build expressions from signals | [Expressions](expressions.md), [configuration structure](configuration.md) |
| Require several conditions for longer than a threshold, then integrate energy over the whole interval | [Two-part ASC energy tutorial](conditional-energy.md), including configuration, actual output and explanation |
| Detect activities, edges, or request/response pairs | [Event rules](rules.md), [sequences](sequences.md) |
| Use a domain preset | [Presets](presets.md) |
| Adjust resources or run independent tasks in a batch | [Execution settings](execution.md), [batch tasks](batch.md) |
| Inspect results or export signals/messages | [Results](results.md), [exports](exports.md) |
| Reuse definitions and inspect where fields come from | [Imports](imports.md), [configuration tools](configuration-tools.md) |
| Find complete examples or import an old INI | [Examples](examples.md), [INI migration](migration.md) |
| Maintain the implementation or build documentation | [Architecture](architecture.md), [documentation maintenance](maintenance.md) |
