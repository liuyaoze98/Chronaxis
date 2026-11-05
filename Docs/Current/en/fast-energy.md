# High-performance integrator (same-frame per-message accumulation)

This integrator adds the expression result from each matching message. To calculate energy from power, multiply by the duration represented by that message, for example `power * period`. If each message already supplies an energy contribution, add it directly: contributions of 400 J and 600 J total 1000 J without another time factor.

`period` is a parameter name chosen for the example, not a required parameter. The runner does not automatically multiply by the actual interval between adjacent messages. Use the [time integral](calculations.md#integrators) when the integral must follow actual elapsed time.

Use fast when one matched power message represents a fixed contribution time, such as 0.1 s. Use fast batch for independent files; use ordinary analysis when state must carry across continuous volumes. Download the [ASC plan](../examples/fast/analysis.yaml), [BLF plan](../examples/fast/analysis-blf.yaml), [batch plan](../examples/fast/batch.yaml), [DBC](../examples/fast/data/power.dbc), [first ASC](../examples/fast/data/run2.asc), [second ASC](../examples/fast/data/run10.asc) and [BLF](../examples/fast/data/single.blf).

## Install and run

Install Chronaxis 0.1.0.dev2 with access to its dependencies; see [Installation](installation.md) to use a local wheel. After activating the environment, change to the directory containing the downloaded plans. Preserve the data subdirectory.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install "chronaxis==0.1.0.dev2"
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
config_version: 4            # Current analysis configuration version
dataset:                     # Analysis identity and optional input range
  name: energy_demo          # Name used to identify and reference this object
sources:                     # Input sources used by this analysis
  - paths: data/run2.asc     # One ASC/BLF file for this task; relative to this configuration, exactly one file after expansion
    dbc_by_channel:          # DBC files indexed by user-facing CAN channel
      '1': data/power.dbc    # DBC for channel 1; channel keys are strings
signals:                     # Signals available to expressions
  - name: power              # Name used to identify and reference this object
    field:                   # Locate the original input field
      frame_id: 0x100        # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Power          # Exact signal name defined in the DBC
    period: 100ms            # Normal signal update period, also used for default validity
message_calculations:        # Accumulate one expression result for each matching message
  - name: energy             # Name used to identify and reference this object
    update_message:          # Message whose arrival triggers this formula
      frame_id: 0x100        # CAN message identifier; decimal or prefixed hexadecimal/binary
    parameters:              # Named constants used in the per-message formula
      period:                # Time represented by each matched message
        value: 0.1           # Count 0.1 seconds per message
        unit: s              # Express this duration in seconds
    expr: power * period     # Formula using the declared signal or derived names
    unit: J                  # Unit in which this value is interpreted or the result is displayed
```

Indentation groups the fields in YAML. The DBC maps message 0x100 on channel 1 to the Power signal in W. The formula calls this signal power. The signal declaration period is 100 ms. The similarly named formula parameter is the time to count for **each matched message**, 0.1 s. Confirm this assumption for the device. For a time integral based on actual observed intervals, use the general run command with an integral plan.

The first ASC contains two messages at the same timestamp, each at 4000 W. Each contributes 400 J. The CSV energy row therefore contains **800.0 J**, with complete status (完整 in the default Chinese table). The BLF contains the same two power readings and also produces 800 J. Read the manifest_path printed for this run, then open the table named in its outputs. Repeated runs have distinct output filenames.

## Independent files and totals

```yaml
batch_version: 1           # Independent batch configuration version
template: analysis.yaml    # Analysis template applied independently to each input
inputs: data/*.asc         # Files or file pattern expanded into independent tasks
process_count: 2           # Maximum number of analysis worker processes
```

The report lists run2.asc before run10.asc in natural order; parallel tasks may complete in another order. The first yields 800 J, the second 400 J. Open the report_path printed by the batch command. Its jobs list reports each file independently. With `--total`, totals contains energy = **1200.0 J** and status = complete. To process independent BLFs, select a BLF template and change inputs to `data/*.blf`. The example keeps the duplicate BLF out of the ASC total.

A complete total requires a valid value from every expected member for that metric. No observed target produces null. Valid targets with no contribution in the requested sign bucket can yield a true zero. An evaluation error such as division by zero fails the file. Fast evaluates the matching formula before selecting its bucket from the original DBC physical reading. Confirm the meaning of current polarity for your device. Multiple paths in an ordinary source describe a continuous recording. Use the batch template when each file is an independent run.

## Check a rejected request

`python -m chronaxis fast validate unsupported.yaml` on the [rejection example](../examples/fast/unsupported.yaml) exits with code 2. Look for `$.outputs.contributions` in errors. The full per-message contribution table, held inputs from other message IDs, duration conditions and time windows require a general analysis plan.

|What the task needs|Entry or setting|
|---|---|
|A number calculated from one message ID on one channel|Use fast with numeric constants, arithmetic and abs. Use the sign bucket when current polarity selects members.|
|A named DBC choice, multiplexed or container payload, a held signal from a different ID, or an event window|Use the general engine for the requested feature where supported, or adjust the input format. Fast reports unsupported bindings before it opens the recording.|
|A strict RAM budget or full contribution evidence|Choose a supported general plan. Fast reads the whole file in one worker. Watch memory usage when increasing process_count.|
|Missing or bad readings|No target gives null. A relevant decoding or numeric failure fails the file. The default batch policy continues other independent files. See the individual jobs in the batch report.|

## Using Python

```python
from chronaxis.fast import run

manifest = run("analysis.yaml", "result-asc")
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
| `run(config, output)` | `pathlib.Path`: the completed run manifest. Read its `outputs` to locate tables. |
| `run_batch(plan_path, output, *, process_count=None, cancel_event=None, total=False)` | `pathlib.Path`: the batch report, including individual job states and requested totals. |

| Argument | Accepted value and behavior |
|---|---|
| `config`, `plan_path` | A JSON/YAML file path (`str` or path-like), relative to the calling process's working directory. Not an `AnalysisPlan` or dictionary. Paths inside a configuration are relative to that file. |
| `output` | Output directory path. It may already exist; timestamped files preserve earlier runs. |
| `process_count` | Optional positive integer, excluding Boolean values. Omission uses the batch plan. The actual worker count does not exceed the number of jobs. |
| `cancel_event` | Optional `threading.Event`. Calling `set()` requests cancellation: no new jobs are dispatched, and active fast workers are asked to stop and then reclaimed. Check each job's final status. |
| `total` | Boolean, default `False`. `True` requires a single analysis template expanded over distinct independent files, with matching definitions and DBC bindings; explicit unrelated jobs are rejected. It does not combine arbitrary same-named columns. |

Configuration errors raise before analysis starts. A single-file read, decode, formula or publication failure raises rather than publishing a normal successful total. Batch file failures are recorded per job; other jobs continue unless `fail_fast` is enabled. An infrastructure failure can raise with a `batch_report` attribute when a report was saved; a report is not guaranteed for every error. Keyboard interruption performs cleanup and propagates the interruption. Requested cancellation can return a report with cancelled jobs, so a returned path is not itself proof that all files succeeded. A metric's total is unavailable when a required member failed, was cancelled or has no numeric result.

Full definitions: [run](public-api/fast.run.md), [run_batch](public-api/fast.batch.run_batch.md).

Maintainer: liuyaoze.
