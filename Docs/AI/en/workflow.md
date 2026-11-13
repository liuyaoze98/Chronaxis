<a id="从用户输入到结果"></a>
# From the user's inputs to results

| Task | Public entry point | Result and boundaries |
|---|---|---|
| Connect logs | BLF/ASC with the matching DBC; raw-message CSV with an explicit record format; decoded CSV with column declarations; memory input for controlled data. | Source identity, clocks, and entity scope are input requirements. Combine sources only when the available evidence supports it. |
| Build an analysis | Version 4 YAML/JSON for an analysis, with at most one level of shared definitions. Use `load_analysis_plan` for files and `AnalysisPlan.from_dict` for dictionaries. | Checks references, types, units, and clocks; may enumerate directories or read DBC metadata. This does not verify business meaning in actual records. |
| Choose calculations | Use bound names in conditions, derived expressions, rules, windows, and `calculations`. Use `message_calculations` for per-message accumulation. | Activities and windows can have separate calculations. Integration method, interval basis, and quality affect results. |
| Use business presets | Declare roles and parameters in a complete plan's `presets`. Python construction returns a `PlanFragment`. | Presets expand into ordinary declarations. Role validation does not determine engineering thresholds; a fragment is not a complete plan. |
| Explain before running | `validate_analysis_plan`, `explain_analysis_plan`, then `AnalysisRunner.run`. | Explanation shows dependencies, time requirements, and budgets, not records already read. `run` calculates from real inputs and returns an `AnalysisResult`. |
| Read or deliver results | Stream rows from `AnalysisResult`; close cursors after exhaustion or early exit. Call `write` with a reusable directory and timestamped filenames, then close the result. | Follow each row type's relationship keys and quality fields. Null is not zero. Failed publication is not delivery. |
| Run independent tasks | `load_batch_plan`, `run_batch`, or `python -m chronaxis batch run`. | Each task is independent. Inspect individual statuses even after a normal return. Do not split one stateful session into independent tasks. |

Python compatibility does not establish operating-system support. When managed workers are actually started, Linux process cleanup requires Python pidfd APIs and Linux 6.9 process-group signaling; publication requires libc `renameat2`, filesystem support for `RENAME_NOREPLACE`, and a same-filesystem move. The review environment is x86_64 Docker on WSL2 kernel 6.18.54.1, glibc 2.41, Python 3.12.15 and overlayfs; other filesystems, architectures, native Linux hosts and macOS are not covered by that environment. Static validation and inline computation without managed workers do not require pidfd; an independent batch can start a worker even with a limit of one. Retain capability restrictions reported by the program. Synthetic example values do not validate real business inputs, performance or a different platform.

<a id="写配置前保留用户原意"></a>
Choose the execution scope from the file relationship: one continuous ASC/BLF source uses analysis `execution.process_count: 4`; independent trials use batch-root `process_count: 4` with child plans configured with `execution.process_count: 1`. CSV, memory, multi-source and `decode_scope: all` plans set the limit to 1 and read in the current process. Scheduling depends on the requested limit, file/task count and merge mode; the omitted limit is one. Ordinary single-ASC default concatenation reports a child-process limit of zero: a configured limit of one does not mean one child was started. See [basic configuration and Python entry-point protection](README.md).

## Preserve the user's meaning before writing configuration

Map the requirements already supplied by the user to configuration without asking them to reconfirm those facts. Consider: “state is `0x2`, current is at least `10A`, continuously for more than `60s`; integrate current times voltage over each qualifying interval, in `kWh`.”

| Requirement to preserve | Configuration and handling |
|---|---|
| Signals and expression | Bind `BMS_ChrgSta`, `BMS_BatPackActCur`, and `BMS_BatPackActVol`. Calculate current times voltage; do not substitute another measurement point. |
| Comparisons and logic | Use `state == 0x2 and current >= 10`, binding aliases to those signals. Preserve equality, inclusive `>=`, and logical AND. |
| Continuously longer than 60 seconds | Use `condition_duration`, `minimum_duration: 60s`, and `duration_comparison: ">"`. Exactly 60 seconds does not qualify. Do not replace it with 60.1 seconds or omit continuity by merely filtering frames. |
| Integration boundaries | “Within the qualifying interval” uses default `selection_origin: onset`, from first satisfaction to the interval end. Do not discard the first 60 seconds. Use `confirmed` only when explicitly requested. |
| Unit | Confirm A and V from the DBC or established definitions, and request `kWh` output. Do not relabel a J or Wh value as kWh. |
| File relationships and timing | Put continuous volumes in one source so state continues across files. Batch only independent tasks. Preserve the chosen actual, fixed, or DBC period; do not edit timestamps instead of configuring it correctly. |

Aliases may be short, but explain their original signal mappings. Obtain facts from inputs, DBC metadata, matching examples, and the user's existing instructions. Ask only when a missing fact can change the result, such as an ambiguous signal match or uncertainty about whether files are continuous volumes or independent experiments. Use supported defaults and explain them where relevant; do not turn every optional field into a question.

Ordinary expression integration does not require current direction or measurement-point metadata used only by a business preset. If the user specifies a raw-current comparison and product, do not add sign conversion merely to label the result “charging” or “discharging.” Ask about that interpretation only when the task actually needs it and the available information is insufficient.

<a id="报错修复与核验范围"></a>
## Fix errors within the task's scope

For installation, missing dependencies, paths, or field errors, fix the actual cause while preserving the requested signals, condition, duration threshold, integration start, and unit. Do not add direction/measurement restrictions, a `95%` coverage threshold, extra minimum/maximum statistics, or change validity, thresholds, or timing just to make execution succeed. Do not automatically sort, deduplicate, filter, or rewrite input after backwards timestamps or similar data errors. Report the actual diagnostic and explain any proposed data treatment's effect on results.

Read, calculate, and deliver only what the task needs. Once installation and entry-point validation pass, run the requested analysis. Contributions, tracing, raw-frame copies, additional statistics, and repeated scans that neither the user nor calculation needs must not be constructed, scanned, saved, or output. Explain empty results using their diagnostics; do not silently loosen conditions and rerun.

Choose independent verification for a specific verification goal; it is not a prerequisite for every normal run. If you write a separate checker, explain whether it preserves original order, how it handles validity (TTL), invalid updates and boundaries, and which files, signals, and results it checks. A script that sorts records and holds the latest voltage forever is not equivalent to an analysis that preserves order and expires voltage. Similar total energy alone does not verify the entire feature. Checking only integration values does not establish event selection, cross-file state, or all quality rules. Investigate discrepancies rather than changing business conditions to fit a reference value.

## CAN messages with a fixed contribution per frame

Use the available evidence to distinguish volumes of one recording from independent trials, confirm that the current CAN frame contains every formula input, and establish the basis for counting a fixed time per message. The high-performance integrator accumulates same-frame contributions per message. For matching ASC/BLF tasks, select `FAST_MESSAGE_ENERGY`; for volumes of one recording select `FAST_CONTINUOUS_SESSION`; for totals across independent files from one template select `FAST_TEMPLATE_TOTAL`. Ask only when missing information can change the result. Fast currently rejects raw-message CSV, multiplexed messages and container messages. Actual-time integrals, dependencies across message IDs, duration conditions and full contribution rows require the general `run` command.

Validate with `python -m chronaxis fast validate`; successful general validation does not establish fast support. Find this run's files through `manifest_path` or `report_path`. The sign bucket uses the DBC physical reading before user conversions, and a negative formula contribution retains its sign. Formula evaluation precedes direction selection: a missing value, division by zero or overflow fails the file, even if direction selection would have excluded that frame.

Read each result separately. A missing accumulation result is null. The reason distinguishes an empty input (`empty_file`), no target frames (`no_target_frames`) and targets entirely outside the requested range (`no_target_in_domain`); valid target frames but none selected for the direction gives zero with `no_selected_direction`. Batch totals require explicit `--total` and independent files from one template with the same DBC and calculation meaning. A missing member value makes that metric's total null, while other metrics with complete member values can still have complete totals. Failed, cancelled or unstarted members cannot form a complete total. Inspect each task and total status, not only the process exit code.

For volumes of one recording, use `FAST_CONTINUOUS_SESSION`: one analysis configuration, one source, and execution.process_count controlling read/decode/current-message workers. file_merge independently controls order. File partial sums do not replace ordered session accumulation. FAST_TEMPLATE_TOTAL is for independent trials. Cancellation of run raises InterruptedError; a managed budget is not a whole-tree RSS limit.
