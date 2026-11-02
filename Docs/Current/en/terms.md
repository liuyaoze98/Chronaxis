<a id="术语表"></a>
# Glossary

Suppose you have BLF or ASC logs and a DBC defining power and whether a device is working. You want to count its activities, measure their duration, and calculate their energy. The terms below use that task as a concrete example.

<a id="数据在各步骤中是什么样"></a>
## What data looks like at each step

`5000` in a CSV file initially consists of text. Reading it as a number according to column and signal settings is **parsing**. CAN logs contain message bytes; extracting physical values using the DBC's bit positions, scale, and offset is **DBC decoding**. A component that reads, parses, or decodes input is a **reader**. BLF and ASC readers are selected by extension. Specify `sources[].source_type` for CSV or memory inputs; you do not need to construct a reader yourself.

In signal configuration, **before conversion** means CSV parsing or DBC decoding has finished, but `signals[].conversion.scale` and `conversion.offset` have not been applied. **After conversion** means the additional multiplication and addition have finished. For example, parsing or decoding produces 5000 mA, then multiplying by 0.001 produces 5 A. `invalid_values` contains codes on the 5000 mA side; `valid_range` describes the allowed range on the 5 A side. If the DBC already decodes a value as 5 A, do not repeat its scaling.

An **input code** represents a device state, such as 0 for idle and 7 for running. Consult the protocol or column definition for its meaning. An **enumeration label** is a nonempty text name used in the analysis, such as `"idle"` or `"running"`. `choices: [[0, "idle"], [7, "running"]]` converts the code on the left into the label on the right; then compare `mode == "running"`. Integer `1`, string `"1"`, and Boolean `true` are different types. Input codes refer to parsed types, not just the characters displayed in a CSV file.

A **preset** is a reusable group of rules and calculations, such as charging analysis. A **role** describes a required input, such as `current`. `role_bindings` explicitly assigns a signal to a role. **Automatic lookup** searches business metadata such as `semantic_id` for exactly one suitable raw signal when no explicit binding is supplied. **Role requirements** specify types, units, current direction, measurement point, validity, and related conditions; they do not infer meaning from a name. The string version `"1"` comes from the [preset role requirements](presets.md#preset-role-requirements).

Business metadata records meaning. For example, `sign_convention: positive_is_charge` declares that positive current means charging; it does not negate values. Check the equipment specification and actual measurement convention first.

<a id="数据和计算"></a>
## Data and calculations

| Term | Meaning here | Example |
|---|---|---|
| Source | A group of input data, such as continuous BLF/ASC logs or a CSV table. | One source reads the ASC and BLF files in `logs/`. |
| Signal | A quantity or state that changes over time. | Power and operating state are separate signals. |
| Sample | One observation of one signal at a time. | “At 2 seconds, power is 4000 W.” |
| Synthetic test data | A small, deliberately constructed input with a known answer. | A few ASC messages can test whether two activities are found. |
| Alias (`name`) | The signal name used in expressions; it may differ from the DBC name or column name. | Bind `Current_mA` as `current`, then write `current > 5`. |
| Derived signal | A new signal calculated from existing signals. | `power = voltage * current`. |
| Expression | A calculation or condition in configuration. | `power / 1000` calculates a value; `active > 0` tests a condition. |
| Unit | Describes the physical meaning of a number. | `4000` with `unit="W"` means 4000 watts. |
| Data type (`dtype`) | The kind of value a signal can contain. | `float64` holds decimals, `int64` integers, `bool` true/false, and `enum` declared state labels. |
| Binding | Connects an input field to an expression name. | `name: power` binds to `signal: Power` under `frame_id: 0x100`; a unique source need not be referenced again. |

`int64` ranges from −2⁶³ to 2⁶³−1; `uint64` ranges from 0 to 2⁶⁴−1. `float64` represents fractional values, but cannot store every decimal or large integer exactly. Boolean `True`/`False` values do not automatically act as 1/0 in arithmetic. See [expressions](expressions.md) for exact restrictions.

<a id="时间和结果"></a>
## Time and results

| Term | Meaning here | Example |
|---|---|---|
| Session | The input and time range of one analysis, not a login session. | Analyze several continuous ASC/BLF logs from one experiment together. |
| Requested range (`dataset.domain`) | The start and end you want to analyze. | Requesting 0–12 seconds does not prove the input contains 12 seconds. |
| Observed range | The time range actually supplied by the input. | A final record at 8 seconds does not support calculation through 12 seconds. |
| Signal validity (`valid_for`) | How long the previous observation may still be used. | A 10 A observation at 0 seconds with a 2-second validity cannot be used at or after 2 seconds without an update. |
| Unknown (`UNKNOWN`) | Insufficient data to decide whether a condition is true or false. | Expired current cannot establish `current > 5`. |
| Event | One detected activity or instantaneous change. | Operation from 0 to 1 seconds is an activity; an alarm changing from false to true is a point event. |
| Segment | A range selected around an event for context. | Five seconds before an alarm and ten seconds after; it can include non-alarm time. |
| Calculation | A value or selection calculated for a range. | Operating duration, maximum current, energy, or matching rows. |
| Scope | Selects the whole session, each event, or each segment for a calculation. | Event energy differs from window energy when the window includes idle time. |
| Coverage | The calculable part as a proportion of the required range. | Eight observed seconds out of twelve requested seconds gives `8 / 12` request coverage. |
| Partial-result policy (`partial_policy`) | Whether to return a value calculated from the known portion. | `report` returns and marks the known portion; `strict` returns null when the required range is incomplete. |
| Quality | Flags explaining why data may be unusable. | Expired signals, empty input, or division by zero; not a score out of 100. |

Coverage has several meanings: whether logs cover the requested time, whether signals are valid within the logs, and whether conditions are decidable are different questions. See [execution](execution.md) for worked calculations and [results](results.md) for fields.

<a id="运行程序"></a>
## Running the program

| Term | Meaning here | Example |
|---|---|---|
| Analysis plan (`AnalysisPlan`) | Checked declarations describing inputs, calculations, and outputs, before business logs are read. | `load_analysis_plan("analysis.yaml")` builds a plan. |
| Backend | An implementation of the same calculation rules; not a web server. | `numpy` uses arrays; `reference` supplies an independent implementation for comparison. |
| Batch | A portion of a large input processed at a time. | Process 1000 records, then the next 1000. A batch boundary does not end an activity. |
| Buffer | Data temporarily retained in memory to reduce frequent reads or writes. | Accumulate result rows before writing them together. |
| Budget | A permitted resource amount measured in bytes or rows, not money. | `memory_budget_bytes=268435456` manages the new analysis components within 256 MiB. |
| Spool | Intermediate data or results written to a working directory for later calculation, sorting, or export. | Results may already be on disk before final CSV publication. |
| Publish (`write`) | Write a complete result to a new local directory, not upload it to the internet. | Publish selected result tables and `run_manifest.json`; interchange CSV can include `events.csv` and `calculations.csv`. |
| Manifest | JSON recording inputs, configuration, calculation settings, and output files. | Check whether two results use the same inputs and settings. |
| Cursor/iterator | An object that returns the next row without loading a whole table. | `for row in result.iter_calculations()`. |
| Close | Release file handles, iterators, and related resources. | Closed objects cannot be read again. Default cleanup removes temporary data created by the run, preserving published outputs and original inputs. |

Keep the default execution settings initially. See [choosing execution settings](execution.md) before changing batches, memory budgets, or incomplete-data handling.

<a id="阅读内部api时还会遇到的词"></a>
## Terms in internal API documentation

| Term | Meaning |
|---|---|
| Finite/non-finite values | `1` and `−2.5` are finite; `NaN` means not-a-number, and `inf`/`-inf` mean positive/negative infinity. Non-finite values are not normal user-facing statistics. |
| Overflow/underflow | A result falls outside a type's representable range. Floating-point underflow may turn a very small nonzero result into zero. |
| Read-only/frozen | Fields cannot be changed directly after construction. An already used plan cannot be mutated into a different configuration. |
| Array shape `(N,)` | A one-dimensional array with N items. Three timestamps have shape `(3,)`. Equal length means times, values, and flags have matching counts. |
| Mask | Boolean flags, one per item, marking valid or selected positions. |
| Reduction | Combine many inputs into fewer outputs, such as one maximum from 100 power samples. |
| Alignment | Find the voltage and current values still valid at a particular calculation time. |
| Normalization | Apply configured type or unit conversion, such as 1000 mA to 1 A. It does not automatically rescale everything to 0–1. |
| Invariant/consistency check | Detect contradictory fields, such as claiming 9 valid seconds within an 8-second range. |
| Identity | Distinguishes inputs, configurations, or bindings. Binding `current` to another column changes the binding identity; this is not a person's identity. |
| Hash | A content-derived string used to detect changes. Equal hashes do not establish equal business meaning for two experiments. |
| Seal | Finish writing temporary storage so it can only be read, not appended to. |
| Owner | An internal object responsible for closing resources or releasing budget. Most callers use `AnalysisRunner` and `with`. |
| Schema | Rules for allowed fields, types, and required items. Structural validity does not prove files exist or data is usable. |
| Expression language (DSL) | Supported formulas such as `current > 5`. Only documented operators and functions are available; it is not full Python. |
| Abstract syntax tree (AST) | A parsed expression structure. `current > 5` becomes a comparison operation and two operands, used for validation and execution planning; users need not write the tree. |
| NumPy | A Python numerical library for array operations, used by the `numpy` backend. |
| ZOH/backward hold | Use the previous still-valid value between updates. With 2 W at 0 seconds and 8 W at 3 seconds, `[0, 3)` uses 2 W rather than linear interpolation. |
| Edge | A false-to-true change is a rising edge; true-to-false is a falling edge. An edge is instantaneous. |
| Dependency | An input required by a result. `power = voltage * current` depends on both signals. |
| Merge | Process multiple inputs in common time order. It does not make equally named fields from different sources one signal. |
| State machine/state advancement | Retain current state and update it as new data arrives, such as continuing a 2-second activity across batches. |
| Watermark | A reader's promise that no earlier records will arrive later, allowing processing at that time to finish. |
| EOF | End of a file or source. It does not necessarily mean the equipment stopped. |
| File descriptor (FD)/file handle | An operating-system resource for an open file. Unclosed handles may prevent moving or deleting it. This FD is unrelated to CAN FD. |
| CAN FD | A CAN frame format supporting longer payloads and related capabilities. `is_fd` distinguishes it from classic CAN; it is not a file descriptor. |
| RSS | Resident physical memory reported by the operating system, not the same as the managed `memory_budget_bytes` amount. |
| Lazy/on-demand reading | Read or calculate more when the caller requests another item, avoiding an all-results list. |
| Atomic publication | Write a complete temporary output directory, then rename it to the final directory so partially written output is not mistaken for completion. |
| Native Python number | Built-in types such as `int`, `float`, and `bool`. Some low-level objects require these rather than unconverted array scalars. |
| Snapshot | Content fixed at a particular point, such as source code at a Git commit; later changes do not alter that version. |

<a id="事件窗口与批量任务"></a>
## Events, windows, and batch tasks

| Term | Meaning | Example |
|---|---|---|
| Request/response pairing | Associate a request point with a response within an allowed delay. | Request at 1 second, response at 3 seconds: delay 2 seconds. |
| FIFO | Give a response to the oldest still-eligible waiting request. | Requests at 1 and 2 seconds; a response at 3 seconds first matches the 1-second request. |
| Hysteresis | Different entry and exit conditions, retaining previous state between them. | Enter at 80, exit at 75; at 77, retain the known prior alarm state. |
| Debounce | Change activity state only after a condition remains true for a duration. | Require 2 continuous seconds; ignore shorter pulses. |
| Complete window | Data allows evaluation throughout the entire window. | Two samples inside a 4-second window do not prove all 4 seconds are valid. |
| Independent batch tasks | Schedule separate plans that do not share analysis state. | Run three vehicles independently, rather than divide one file into three pieces. |
| Resampling | Produce records at specified times; use configured estimation when no actual sample exists there. | Output voltage every 100 ms. |
| Time grid | Equally spaced output times determined by `resampling.start` and `resampling.period`. | Start 50 ms, period 100 ms: 50, 150, 250 ms, etc. |
| Linear interpolation | Estimate along the straight line between two known values. | 0 V at 0 seconds and 10 V at 2 seconds gives 5 V at 1 second. |
| Continuous/state quantity | A continuous quantity has meaningful intermediate values; a state represents a category. | Voltage can be interpolated; gears 1 and 2 do not imply a gear 1.5. |
| Nearest neighbor | Choose the actual record closest to the requested time. | Equidistant records at 0 and 2 seconds select the earlier frame at 0. |
| DBC | Defines signal bit positions and conversions in CAN messages. | Convert two bytes to voltage using the specified scale. |
| DLC | CAN data-length code, not always the number of bytes. | CAN FD DLC 10 represents 16 bytes. |
| Raw frame | A CAN message actually recorded in the input. | Its timestamp, ID, and payload come from the source file. |
| Base frame | The original frame used as the starting point for a resampled frame. | Replace only the voltage bits with the newly estimated voltage; retain other bits from the base frame. |
| Timeout/unknown | Timeout means the allowed waiting time elapsed; unknown means insufficient evidence. | A log ending early cannot prove that a device failed to respond. |
