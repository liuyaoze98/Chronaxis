# Parallel reading for continuous recordings

Place all ASC/BLF files belonging to one charge or experiment in one `sources` entry. Set `execution.process_count` to limit file-reading, parsing and DBC-decoding workers. The main process maintains one continuous signal, event and calculation state. A file boundary does not end an event or restart integration.

For example, a charge recording spread over ten files can use up to four workers to read and decode several files at once, while producing one result for the charge. For same-frame per-message accumulation, the [high-performance integrator](fast-energy.md) also evaluates message contributions in those workers.

## Run a minimal example

Use [continuous-parallel.yaml](../examples/continuous-parallel.yaml) with its bundled files in `data/can/session` and `data/can/teaching.dbc`. Run from the examples directory:

```powershell
chronaxis validate continuous-parallel.yaml
chronaxis explain continuous-parallel.yaml
chronaxis run continuous-parallel.yaml --output session-result
```

```yaml
config_version: 4                   # Current analysis configuration version
dataset:                            # Identify the complete analysis session
  name: continuous_charge           # One name for the recording across both volumes
sources:                            # A single continuous CAN source
  - paths:                          # Volumes in their continuation order
      - data/can/session/part1.asc  # First volume
      - data/can/session/part2.asc  # Next volume from the same session
    dbc_by_channel:                 # DBC used to interpret each CAN channel
      '1': data/can/teaching.dbc    # DBC for user-facing channel 1
signals:                            # Named inputs for calculations
  - name: power                     # Formula name for the power signal
    field:                          # Locate the signal in the DBC
      frame_id: '0x100'             # Message containing this signal
      signal: Power                 # Exact DBC signal name
    valid_for: 3s                   # A valid reading can be held for at most 3 seconds
calculations:                       # Requested results
  - name: energy                    # Name of the energy result
    operation: integral             # Integrate using actual elapsed time
    expr: power                     # Use the power signal above
execution:                          # Runtime settings for this session
  process_count: 4                  # At most four file workers, excluding the main process
```

This example requests four workers but has only two files, so at most two file workers run. Four is a recommended starting limit; omission still defaults to one. A single file is not split by raising the limit.

File 1 supplies 2 W at 0 s and 4 W at 1 s; file 2 supplies 8 W at 3 s and 10 W at 4 s, with source observation through 6 s. Holding 4 W across the file boundary gives `2×1 + 4×2 + 8×1 + 10×2 = 38 J`. All holds are within the declared validity.

After completion, locate the calculation CSV through `outputs` in this run's completion manifest. Its `energy` row should contain **38**, unit **J**, and complete status. The `explain` output's `source_execution` should describe two files and a limit of two read processes. This is a planned limit, not a measured speedup.

## Choose the file ordering

`sources[].file_merge` controls record ordering independently of the process count. Raising the process count never silently sorts records, shifts timestamps or deduplicates messages.

| Value | Behavior | Use when |
|---|---|---|
| `concatenate`, default | Consume files in declared `paths` order, preserving each file's record order and the task's existing time-check scope. | Files already form a chronological continuation. Directory/glob matches are expanded in natural filename order. |
| `time_order` | Validate each file's required timestamp sequence, then merge by timestamp, declared file position and local record sequence. | Overlapping files have timestamps in a verified common coordinate system. Internal regressions still fail; sorting does not repair a file. |

Two files starting at zero are not evidence of synchronization. Configure a known offset explicitly using the [source time settings](inputs.md); otherwise establish the recording clock first. Duplicate-looking records are retained. Per-message accumulation counts each message; ordinary signals follow `same_time_policy`.

[continuous-time-order.yaml](../examples/continuous-time-order.yaml) is an extended, complete example: two individually ordered but interleaved files produce the same 38 J and one activity crossing a file boundary. It explicitly defines the event, memory limit, temporary-disk quota and every referenced signal.

## Process settings and interfaces

| Setting | Accepted values and effect |
|---|---|
| `execution.process_count` | Positive integer, default `1`. Rejects zero, negative numbers, fractional numbers, text, Boolean values and `null`. This is the analysis-wide worker limit, excluding the main process, capped by file count. There is no automatic CPU-based increase. |
| Ordinary CLI `--process-count` | Supported by `run`, `validate` and `explain`. Overrides the configuration for this invocation only. |
| `AnalysisRunner.run/validate/explain(..., process_count=...)` | Keyword-only. `None` uses the plan; a positive integer overrides this invocation without modifying the original plan. An invalid override raises `ValueError`. |

Parallel reading and time merging currently support one ASC/BLF CAN source, including mixed files, with `reader.decode_scope: requested`. Multiple sources, CSV/memory sources and `all` decoding are rejected before execution; their existing default single-process concatenation remains available. An independent batch worker cannot start an inner file pool. Run a continuous analysis directly with ordinary `run`.

With default `1` and `concatenate`, pure BLF retains its existing single reader subprocess; ASC/mixed inputs are read in the main process. Explicit `time_order` uses file workers even with a limit of one. `explain.source_execution` reports file count, ordering, reader-process limit and temporary-merge use. These are static facts, not measured worker counts or evidence that the log contents are ordered.

```powershell
chronaxis validate continuous-parallel.yaml --process-count 4
chronaxis explain continuous-parallel.yaml --process-count 4
chronaxis run continuous-parallel.yaml --process-count 4 --output session-result
```

Protect the entry point when starting processes from Python, including on Windows:

```python
from chronaxis import AnalysisRunner, load_analysis_plan

def main():
    plan = load_analysis_plan("continuous-parallel.yaml")
    with AnalysisRunner().run(plan, process_count=4) as result:
        result.write("session-result")

if __name__ == "__main__":
    main()
```

## Resources, failure and performance

`concatenate` permits bounded read-ahead and pauses workers when their buffers are full. `time_order` stages validated per-file records, then merges them after all reads succeed. Staging counts against the cumulative `execution.spool_quota_bytes` allowance. Each merge input also requires bounded memory; insufficient resources cause failure.

Managed worker decoding space, transfer buffers and main-process state share one `memory_budget_bytes` allowance. Each worker does not receive a separate copy of that budget. Python and third-party allocations can exceed the managed estimate. An input error, budget failure, worker crash or cancellation cannot masquerade as file EOF or publish a normal result missing later files. Closing reclaims this run's workers and merge staging while preserving inputs and published results.

More processes do not guarantee a faster analysis. Concatenation may wait for the current file; time merging adds disk I/O; continuous calculations remain in the main process. Compare complete 1/2/4/8-process runs with identical inputs, calculations, outputs and ordering. Independent-batch timing is not a substitute for a continuous-session measurement.
