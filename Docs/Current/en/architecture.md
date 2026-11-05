<a id="架构与数据处理流程"></a>
# Architecture and data flow

For a typical CAN task, Chronaxis decodes messages, detects activities, calculates energy, and writes result tables. It also accepts already decoded CSV signals. The modules below implement those steps; users do not need to call each module separately.

A *binding* connects an input field to a signal name used in expressions. A *backend* supplies the calculation implementation. Temporary working files support bounded-memory processing and result publication. See [terms](terms.md) for the terminology used in this guide.

<a id="从输入记录到计算结果"></a>
## 1. General analysis from input records to results

```text
CLI or Python API
  → AnalysisPlan.from_dict / load_analysis_plan
      Check sources, names, units, expressions, rules, and outputs
      Expand presets into ordinary declarations
  → AnalysisRunner.validate / explain
      Inspect a loaded plan without reading business records
  → runner.AnalysisRunner → execution.run_session.RunSession
      Open inputs; establish budgets and temporary working storage
      memory: configured times and values
      signal_csv: batches of table rows
      can_blf: isolated reader process → frozen Sclicer reader/decoder
               → fields required by this analysis
      can_asc / raw CAN CSV: explicit text parser → DBC signal decoding
  → Bind and convert signals; combine simultaneous updates
      Apply validity periods; evaluate expressions and conditions
      Use the reference or NumPy core
  → Events → selected windows → session/event/window calculations
      Sequence pairing runs through its own state handling
      Reuse stored signal history where required; do not decode it again
  → ResultSpool: budgeted storage and ordered results
  → AnalysisResult: row iterators
  → write: tables, requested exports, input issues, and manifest
      Publish timestamped output files
```

In the general entry, per-message calculations use a separate path: match a required message, use its current decoded values, evaluate, and accumulate. Summary-only tasks can accumulate directly when no other requested feature needs history. This differs from historical ChrgInfo profiles that may cache a previous value: a missing value in the current message is skipped, not carried forward. A configured per-message period must not also be multiplied by actual elapsed time. See [per-message calculations](message-calculations.md).

The explicit fast entry processes independent ASC/BLF files. Each file worker reads the messages and accumulates same-frame formulas. A target frame missing a required formula value, or a formula evaluation error, fails that file. See [High-performance integrator](fast-energy.md) for complete inputs, configuration and results.

<a id="每一层解决什么问题"></a>
## 2. What each layer does

| Module | Input and output | When to consult it |
|---|---|---|
| `chronaxis`, `runner` | Public plans become validation/explanation reports or execution results. Root exports load lazily. | Public entry points and execution lifecycle. |
| `planning` | Configuration dictionaries become immutable plans, dependencies, and capability checks. | Invalid fields, references, or unsupported combinations. |
| `presets` | Role bindings and parameters become ordinary rules, windows, derived expressions, and calculations. | How a business preset expands. |
| `sources` | Source declarations and requests become `SignalBatch` objects for memory and CSV inputs. | Reading already decoded signals. |
| `timebase` | Time values and units become integer nanoseconds and conversion/rounding information. | Offsets, precision, and overflow. |
| `core` | Signals and conditions become events, windows, values, and quality states. It does not open CAN files. | Analysis semantics and calculation algorithms. |
| `execution` | Plans and batches become result rows while retaining state across batches and managing history and cleanup. | End-to-end execution and resource handling. |
| `legacy` | Frozen reader/decoder interfaces become decoded messages or requested raw-message exports. | CAN adapters, per-message execution, and process transport. |
| `results` | Computed rows become temporary storage and final output directories. | Ordering, iterators, publication, and failure handling. |

The [module index](../reference/index.md) is a Chinese implementation reference. For example, `execution.record_session_calculations` and `execution.record_scope_calculations` implement different calculation scopes, but the runner calls them as needed. Users normally call the [public API](api.md).

<a id="为什么既有历史文件又有结果暂存"></a>
## 3. Why signal history and result storage are separate

An event's final range may be known only when it ends. A window before that event also needs earlier observations. Signal history holds decoded values for these requested operations. Result storage holds completed rows, allowing sorting, streaming reads, and publication without retaining all results in memory.

Managed memory budgets cover buffers and analysis state; disk budgets cover temporary storage. They are not a cap on process RSS: the interpreter, NumPy, and historical libraries also use memory. Measure process memory when that distinction matters. Exceeding a budget raises an error rather than silently dropping data. See [execution](execution.md).

<a id="两个计算后端怎么分工"></a>
## 4. The two calculation backends

`reference` and `numpy` implement the same rules independently. NumPy uses arrays and masks for suitable calculations. Backend comparisons require equal event boundaries, statuses, and quality outcomes; floating-point values use an appropriate unit-aware absolute and relative tolerance. Tolerance handles numerical rounding, not different quality decisions.

Python still controls input files, rule state, budgets, and cleanup. A node shown as NumPy in `explain` does not mean the entire pipeline runs in NumPy.

`AnalysisRunner(backend="reference")` overrides the plan for that run. The manifest's `run.plan_hash` identifies the original plan, while `run.backend` records the actual backend. Equal plan hashes therefore do not prove that two runs used the same backend. Changing batch sizes changes memory use, not where an activity ends.

<a id="与历史项目的关系"></a>
## 5. Relationship to the historical projects

Three vendored Sclicer files provide the frozen read/write and decoding implementation. New outer layers provide plans, rules, budgets, and publication. This does not expose every historical CSVConvert, Filter, or ChrgInfo entry point as a public API; see [per-message calculations](message-calculations.md).

Demand-driven decoding and field selection use plan dependencies. `explain` reports their scope. The frozen decoder implementation and the choice of fields requested from it are separate responsibilities.

<a id="单任务与批量任务的调用关系"></a>
## 6. Single analyses and batch tasks

```text
Single analysis
  AnalysisRunner
    → planning / sources / execution
    → core rules and sequence handling
    → results

Independent batch tasks
  batch runner
    → separate AnalysisRunner, working directory, and result for each task
    → combined task-status report
```

Plan validation and explanation precede record reading. Some errors, including actual frame/DBC decoding failures and backwards timestamps, can only be detected during execution. Raw text is parsed into located frames and then decoded into signals; BLF uses the compatibility reader chain. Both feed the same core, which contains no vehicle-specific IDs or DBC names.

`window_delta` needs earlier observations. Hysteresis, debounce, and `start_end` retain state and deadlines; sequences retain pending matches. State continues across `batch_rows` boundaries and continuous files, while independent tasks have isolated state.

Requested signal or raw-message export retains the necessary data during the first read. Export resampling interpolates before or after sample times according to its settings; it does not change analysis events or integrals. Signal selection, raw-message selection, scope, period, and origin remain separate settings. Budget failure does not authorize dropping data or shortening a range.

See [batch tasks](batch.md), [text inputs](text-inputs.md), [record exports](../reference/chronaxis.execution.record_exports.md) (Chinese implementation reference), and [sequence rules](sequences.md). The [core stability implementation](../reference/chronaxis.core.stability.md) and [sequence implementation](../reference/chronaxis.core.sequence.md) are Chinese implementation references.
