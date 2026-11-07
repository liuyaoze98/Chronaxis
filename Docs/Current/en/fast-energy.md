# High-performance integrator (same-frame per-message accumulation)

This integrator adds the expression result from each matching message. To calculate energy from power, multiply by the duration represented by that message, for example `power * period`. If each message already supplies an energy contribution, add it directly: contributions of 400 J and 600 J total 1000 J without another time factor.

`period` is a parameter name chosen for the example, not a required parameter. The runner does not automatically multiply by the actual interval between adjacent messages. Use the [time integral](calculations.md#integrators) when the integral must follow actual elapsed time.

Use fast when one matched power message represents a fixed contribution time, such as 0.1 s. Use one fast session for volumes of one recording and fast batch for independent trials. Use ordinary analysis for held cross-message values, events or elapsed-time integration. The basic plan explicitly sets `execution.process_count: 4`, allowing up to four file workers to read, decode and evaluate individual contributions. The main process accumulates them in the required order. Two files can use at most two workers; a single file runs inline. Omission still defaults to one.

Download the [ASC plan](../examples/fast/analysis.yaml), [BLF plan](../examples/fast/analysis-blf.yaml), [batch plan](../examples/fast/batch.yaml), [DBC](../examples/fast/data/power.dbc), [first ASC](../examples/fast/data/run2.asc), [second ASC](../examples/fast/data/run10.asc) and [BLF](../examples/fast/data/single.blf).

## Install and run

Install the local Chronaxis 0.1.0.dev3 wheel using its actual file path below, with access to its dependencies. See [Installation](installation.md) to install from the matching source tree. After activating the environment, change to the directory containing the downloaded plans. Preserve the data subdirectory.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install ".\chronaxis-0.1.0.dev3-py3-none-any.whl"
.\.venv\Scripts\Activate.ps1
python -m chronaxis fast --help
```

```powershell
python -m chronaxis fast validate analysis.yaml
python -m chronaxis fast explain analysis.yaml
python -m chronaxis fast run analysis.yaml --output result-asc
python -m chronaxis fast run analysis-blf.yaml --output result-blf
python -m chronaxis fast batch batch.yaml --output result-batch --total
```

## Single-file plan and result

```yaml
config_version: 4          # Current analysis configuration version
dataset:                   # Analysis identity and optional input range
  name: energy_demo        # Name used to identify and reference this object
sources:                   # Input sources used by this analysis
  - paths: data/run2.asc   # One ASC file in this example, relative to the configuration
    dbc_by_channel:        # DBC files indexed by user-facing CAN channel
      '1': data/power.dbc  # DBC for channel 1; channel keys are strings
signals:                   # Signals available to expressions
  - name: power            # Name used to identify and reference this object
    field:                 # Locate the original input field
      frame_id: 0x100      # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Power        # Exact signal name defined in the DBC
    period: 100ms          # Normal signal update period, also used for default validity
message_calculations:      # Accumulate one expression result for each matching message
  - name: energy           # Name used to identify and reference this object
    update_message:        # Message whose arrival triggers this formula
      frame_id: 0x100      # CAN message identifier; decimal or prefixed hexadecimal/binary
    parameters:            # Named constants used in the per-message formula
      period:              # Time represented by each matched message
        value: 0.1         # Count 0.1 seconds per message
        unit: s            # Express this duration in seconds
    expr: power * period   # Formula using the declared signal or derived names
    unit: J                # Result unit, compatible with the expression
execution:                 # File-worker limit for this analysis
  process_count: 4         # Up to four; this single-file example runs inline
```

Indentation groups the fields in YAML. The DBC maps message 0x100 on channel 1 to the Power signal in W. The formula calls this signal power. The signal declaration period is 100 ms. The similarly named formula parameter is the time to count for **each matched message**, 0.1 s. Confirm this assumption for the device. For a time integral based on actual observed intervals, use the general run command with an integral plan.

The first ASC contains two messages at the same timestamp, each at 4000 W. Each contributes 400 J. The CSV energy row therefore contains **800.0 J**, with complete status (完整 in the default Chinese table). The BLF contains the same two power readings and also produces 800 J. Read the manifest_path printed for this run, then open the table named in its outputs. Repeated runs have distinct output filenames.

## Multiple volumes from one recording

`sources[].paths` identifies all volumes of one session. `sources[].file_merge` controls their order, while `execution.process_count` controls workers that read, decode and evaluate current-message contributions. The session publishes one summary. File boundaries do not reset accumulation. ASC and BLF may be mixed; directories and globs follow the [input path rules](inputs.md). No timestamps are shifted and no records are automatically removed.

Download the complete [concatenation plan](../examples/fast/session.yaml) or [time-order plan](../examples/fast/session-time-order.yaml). Both contain all signal and calculation definitions. The two messages in run2.asc and one in run10.asc each contribute 400 J, giving **1200J** for the session. A volume without target messages does not invalidate valid contributions in other volumes.

In the complete plan above, replace the root `sources` and `execution` sections with these two sections. Retain `dataset`, `signals` and `message_calculations`; do not duplicate parent keys. The downloads also supply optional resource quotas to demonstrate resource management.

```yaml
sources:                   # Continuous volumes in one source
  - paths:                 # Ordered files contributing to one session result
      - data/run2.asc      # First volume contains two contributions
      - data/run10.asc     # Second volume contains one contribution
    dbc_by_channel:        # Both volumes use the same channel and DBC
      '1': data/power.dbc  # Signal definitions for channel 1
execution:                 # File-worker limit for this fast session
  process_count: 4         # These two files need at most two workers
```

Start with default memory and staging settings; add the corresponding fields below when a resource limit is needed. Omitting `execution` uses the default of one, whereas setting `process_count: 4` explicitly requests parallel work.

|Field or option|Purpose and accepted values|
|---|---|
|`sources[].paths`|One path, directory, glob or list belonging to one source. Explicit lists retain declaration order; directory/glob expansion uses project natural ordering.|
|`file_merge: concatenate`|Default. Consume files in declaration order and records in their original order. Later files may compute ahead and stage contributions.|
|`file_merge: time_order`|Merge by mapped timestamps, then file position and original record position. Target candidate data messages within each file must be ordered. This check precedes domain filtering and is independent of sign buckets or zero contributions.|
|`execution.process_count`|Positive integer; default 1. API/CLI overrides configuration without editing it. 1 runs inline. Larger values cap workers at the file count and exclude the main process. Reject zero, negatives, fractions, strings, booleans and configuration null.|
|`execution.memory_budget_bytes`|Positive integer; default 268435456. Limits estimated managed buffers/state, including merge buffers. It is not a hard whole-process-tree RSS limit. Insufficient space fails explicitly.|
|`execution.spool_quota_bytes`|Positive integer or null; default null. Limits cumulative temporary-storage reservations. Deleting temporary files does not restore this allowance. Null removes this extra quota, not physical disk limits.|

Only these three execution fields are supported by fast. Explicit ordinary-engine options such as `backend` or `batch_rows` are rejected. Changing worker count does not select a merge mode.

Staging writes contributions that have been evaluated but are not yet due for accumulation into temporary files owned by this run. The main process reads them later; raw logs are not copied. Managed memory accounts for estimated buffers and state. The Python interpreter and third-party libraries consume additional memory, so a 256 MiB budget does not limit the whole task to 256 MiB.

When optional concatenate prefetch cannot obtain staging quota, that later file pauses and resumes direct delivery when it becomes current. This can reduce speed. Multi-file time_order requires staging; insufficient quota fails. Actual disk errors, damaged blocks or missing contributions fail the whole session. Each format retains its existing input checks.

```powershell
python -m chronaxis fast validate session.yaml --process-count 4
python -m chronaxis fast explain session.yaml --process-count 4
python -m chronaxis fast run session.yaml --output result-session --process-count 4
python -m chronaxis fast run session-time-order.yaml --output result-time-order
```

`explain.worker_process_limit` is a declared upper bound, not measured activity; it is 0 for inline execution. The completion manifest lists every file in `inputs`, actual worker PIDs in `execution.worker_pids`, and per-calculation target/valid/selected counts in `calculation_counts`. Inspect `value/status/reason` in the results. Complete processing does not prove the physical recording contains no missing messages.

|Whole-session condition for one calculation|Result|
|---|---|
|All inputs contain no records|null, `empty_file`.|
|Records exist but no target messages for this calculation|null, `no_target_frames`.|
|All its target messages are outside the domain|null, `no_target_in_domain`.|
|Valid evaluations exist but none enter the requested direction bucket|0, `no_selected_direction`.|
|Selected contributions are zero or cancel each other|Valid 0, without a missing-data reason. Zero contributions still count as selected.|
|Any required volume fails to read, decode, evaluate or close|The session fails without publishing a normal successful summary.|

Successful runs with the same input, frozen configuration, merge mode and environment have identical unrounded results across worker counts. Different merge modes may add values in different orders and need not match in the last bit. Independent batch tasks still accumulate locally; their totals follow separate missing-member rules.

## Independent files and totals

```yaml
batch_version: 1               # Independent batch configuration version
template: batch-analysis.yaml  # Single-process child template for each independent input
inputs: data/*.asc             # Files or file pattern expanded into independent tasks
process_count: 4               # Up to four independent jobs; two inputs need at most two workers
```

Download [batch-analysis.yaml](../examples/fast/batch-analysis.yaml) as the child template. It uses the same formula as the standalone plan but explicitly sets `execution.process_count: 1`. The outer batch runs files in parallel; children do not start nested pools. The batch CLI accepts `--process-count` to override the root limit.

The report lists run2.asc before run10.asc in natural order; parallel tasks may complete in another order. The first yields 800 J, the second 400 J. Open the report_path printed by the batch command. Its jobs list reports each file independently. With `--total`, totals contains energy = **1200.0 J** and status = complete. To process independent BLFs, select a BLF template and change inputs to `data/*.blf`. The example keeps the duplicate BLF out of the ASC total.

A complete total requires a valid value from every expected member for that metric. No observed target produces null. Valid targets with no contribution in the requested sign bucket can yield a true zero. An evaluation error such as division by zero fails the file. Fast evaluates the matching formula before selecting its bucket from the original DBC physical reading. Confirm the meaning of current polarity for your device. Multiple paths in an ordinary source describe a continuous recording. Use the batch template when each file is an independent run.

## Check a rejected request

`python -m chronaxis fast validate unsupported.yaml` on the [rejection example](../examples/fast/unsupported.yaml) exits with code 2. Look for `$.outputs.contributions` in errors. The full per-message contribution table, held inputs from other message IDs, duration conditions and time windows require a general analysis plan.

|What the task needs|Entry or setting|
|---|---|
|A number calculated from one message ID on one channel|Use fast with numeric constants, arithmetic and abs. Use the sign bucket when current polarity selects members.|
|A named DBC choice, multiplexed or container payload, a held signal from a different ID, or an event window|Use the general engine for the requested feature where supported, or adjust the input format. Fast reports unsupported bindings before it opens the recording.|
|Managed memory/staging budgets or full contribution evidence|Fast streams files and supports the three execution options above. Full per-message evidence requires ordinary analysis. Neither managed budget is a hard whole-process RSS limit.|
|Missing or bad readings|No target gives null. A relevant decoding or numeric failure fails the file. The default batch policy continues other independent files. See the individual jobs in the batch report.|

## Using Python

```python
from chronaxis.fast import run

if __name__ == "__main__":
    manifest = run("session.yaml", "result-session", process_count=4)
    print(manifest)
```

For independent files, save this as `run_fast_batch.py` and run `python run_fast_batch.py`. The configuration path is relative to the launch directory; paths inside it are relative to that configuration. Windows workers re-import the entry module, so protect the call with `__main__`.

```python
from chronaxis.fast.batch import run_batch

if __name__ == "__main__":
    report_path = run_batch("batch.yaml", "result-batch", total=True)
    print(report_path)
```

The returned value is the batch report path. Read its status before using totals; failed or cancelled members can make a total unavailable.

### Function reference

Import `run` from `chronaxis.fast` and `run_batch` from `chronaxis.fast.batch`. These are separate from the general `chronaxis.run_batch` interface.

| Call | Return value |
|---|---|
| `run(config, output, *, process_count=None, work_dir=None, cancel_event=None)` | `pathlib.Path`: the completed run manifest. Read its `outputs` to locate tables. |
| `run_batch(plan_path, output, *, process_count=None, cancel_event=None, total=False)` | `pathlib.Path`: the batch report, including individual job states and requested totals. |

| Argument | Accepted value and behavior |
|---|---|
| `config`, `plan_path` | A JSON/YAML file path (`str` or path-like), relative to the calling process's working directory. Not an `AnalysisPlan` or dictionary. Paths inside a configuration are relative to that file. |
| `output` | Output directory path. It may already exist; timestamped files preserve earlier runs. |
| `process_count` | Optional positive integer, excluding Boolean values. run uses execution.process_count; run_batch uses the batch root process_count. Both default to 1 and cap workers at the file/job count. |
| `cancel_event` | Optional `threading.Event`. Calling `set()` requests cancellation: no new jobs are dispatched, and active fast workers are asked to stop and then reclaimed. run raises InterruptedError on cancellation without publishing success; run_batch reports individual job states. |
| `work_dir` | run only: optional parent directory for temporary contributions; omission uses the system temporary directory. This invocation cleans up its own temporary files on success, failure and cancellation. |
| `total` | Boolean, default `False`. `True` requires a single analysis template expanded over distinct independent files, with matching definitions and DBC bindings; explicit unrelated jobs are rejected. It does not combine arbitrary same-named columns. |

Configuration errors raise before analysis starts. A read, decode, formula or publication failure in any required session file raises rather than publishing a normal successful total. Batch file failures are recorded per job; other jobs continue unless `fail_fast` is enabled. An infrastructure failure can raise with a `batch_report` attribute when a report was saved; a report is not guaranteed for every error. Keyboard interruption performs cleanup and propagates the interruption. For run_batch, requested cancellation can return a report with cancelled jobs, so a returned path is not itself proof that all files succeeded. A metric's total is unavailable when a required member failed, was cancelled or has no numeric result.

Full definitions: [run](public-api/fast.run.md), [run_batch](public-api/fast.batch.run_batch.md).

Maintainer: liuyaoze.
