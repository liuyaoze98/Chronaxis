<a id="连续满足条件后对整个区间积分"></a>
# Integrate the full interval after a sustained condition qualifies

This task requires `state == 0x2` and `current >= 10 A` to remain true for **strictly more than 60 seconds**, then integrates `current × voltage` over the entire qualifying interval, including its first 60 seconds. The result is in kWh.

The supplied ASC logs and DBC are synthetic examples. They do not establish the state codes or current direction of a real vehicle. The configuration includes only fields needed for this calculation.

<a id="下载安装和运行位置"></a>
## 1. Files, installation, and working directory

Use [conditional-energy.yaml](../examples/conditional-energy.yaml), [part-1.asc](../examples/data/can/conditional-energy/part-1.asc), [part-2.asc](../examples/data/can/conditional-energy/part-2.asc), and [signals.dbc](../examples/data/can/conditional-energy/signals.dbc). The first log covers 0–89 seconds and the second continues at 90–123 seconds. The teaching DBC defines state, current, and voltage in message `0x100`, with a 1000 ms period.

This example covers Chronaxis 0.1.0.dev4. On Windows, start in the directory containing `examples` and substitute the actual wheel path below. Installation includes the dependencies declared for this version; do not independently install an arbitrary newer `cantools` version. See [Installation](installation.md) for matching source installation and offline dependency preparation.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev4-py3-none-any.whl"
.venv\Scripts\python.exe -m chronaxis validate examples/conditional-energy.yaml --format json
.venv\Scripts\python.exe -m chronaxis explain examples/conditional-energy.yaml --format json
.venv\Scripts\python.exe -m chronaxis run examples/conditional-energy.yaml --output result-conditional-energy
```

CLI paths are relative to your current directory. Input and DBC paths inside the configuration are relative to the configuration file. You need not change into the data directory. The result directory can be reused. Each publication uses timestamped filenames and preserves earlier results.

The two paths belong to one continuous session. `execution.process_count: 4` allows parallel reading; with two files, at most two reading workers are used. The main process consumes the parts in the listed order and retains signal and rule state, so the boundary at 90 seconds does not restart the condition. Use batch tasks when the files represent independent experiments.

<a id="完整配置与可省略内容"></a>
## 2. Complete configuration and omitted defaults

The following is the complete configuration. `sources`, `signals`, `rules`, and `calculations` are root-level lists; `execution` is a sibling mapping. YAML indentation places `rule` beneath `scope`; the reference notation `scope.rule` is not a literal YAML key.

```yaml
config_version: 4                                   # Current analysis configuration version
dataset:                                            # Analysis identity and optional input range
  name: conditional_energy                          # Name used to identify and reference this object
sources:                                            # Input sources used by this analysis
  - paths:                                          # File, continuous file list or directory; relative to this configuration
      - data/can/conditional-energy/part-1.asc
      - data/can/conditional-energy/part-2.asc
    dbc_by_channel:                                 # DBC files indexed by user-facing CAN channel
      '1': data/can/conditional-energy/signals.dbc  # DBC for channel 1; channel keys are strings
signals:                                            # Signals available to expressions
  - name: state                                     # Name used to identify and reference this object
    field:                                          # Locate the original input field
      frame_id: '0x100'                             # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: State                                 # Exact signal name defined in the DBC
  - name: current                                   # Name used to identify and reference this object
    field:                                          # Locate the original input field
      frame_id: '0x100'                             # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Current                               # Exact signal name defined in the DBC
  - name: voltage                                   # Name used to identify and reference this object
    field:                                          # Locate the original input field
      frame_id: '0x100'                             # CAN message identifier; decimal or prefixed hexadecimal/binary
      signal: Voltage                               # Exact signal name defined in the DBC
rules:                                              # Conditions or transitions that produce events
  - name: eligible                                  # Name used to identify and reference this object
    rule_type: condition_duration                   # Event detection algorithm
    condition: state == 0x2 and current >= 10       # Boolean expression used to select an activity
    minimum_duration: 60s                           # Required continuous time for the activity
    duration_comparison: ">"                        # Strictly longer than 60 seconds
calculations:                                       # Requested statistics or selected rows
  - name: energy_kwh                                # Name used to identify and reference this object
    operation: integral                             # Calculation to apply to the expression
    expr: current * voltage                         # Formula using the declared signal or derived names
    scope:                                          # Session, event or window over which to calculate
      rule: eligible                                # Entire qualifying activity
    unit: kWh                                       # Unit in which this value is interpreted or the result is displayed
execution:                                          # Control file reading within this continuous session
  process_count: 4                                  # At most four workers; these two files use at most two
```

The file format, sole source, and unambiguous channel are inferred. Public channel numbers start at 1. Types, units, and periods come from the DBC. Here, omitted `valid_for` becomes 3 seconds: three times the 1000 ms period. That expiry period is not the integration interval; integration uses actual elapsed time by default.

`execution.process_count` parallelizes file reading and decoding. It does not split events or integrals at file boundaries. Four is the upper limit chosen for this example, while omission still defaults to one; choose another positive integer to suit available resources. See [continuous-file multiprocessing](continuous-files.md) for overlapping files and resource settings.

The default interval selection starts at the condition's onset, the default interval mode is actual elapsed time, and the default output is a readable table, so those fields are omitted. `duration_comparison` is required: choose `">"` for strictly longer or `">="` to include the threshold. Omitting it produces a missing-field error. Integer state comparisons such as `state == 0x2` (decimal 2) need no Boolean or enumeration mapping. Check the actual state definition for your own data.

<a id="输入发生了什么为什么只有一条能量结果"></a>
## 3. What happens in the input

Current is 10 A and voltage is 400 V, updated once per second.

| Actual interval | State | Condition | Duration and result |
|---|---|---|---|
| `[0, 60)` | 2 | True | Exactly 60 s; excluded |
| `[60, 61)` | 0 | False | Separates the activities |
| `[61, 122)` | 2 | True | 61 s; included, continuing across the file boundary at 90 s |
| `[122, 123)` | 0 | False | Ends the activity |

The qualifying interval contains `4000 W × 61 s = 244000 J`. Dividing by `3600000` gives `0.06777777777777777 kWh`.

Exactly 10 A qualifies because this task uses `>=`. The charging preset's `current_min: 10` uses `> 10`, so it is not an equivalent replacement. See [whether the charging preset matches your task](presets.md#先判断充电预设是否符合目标).

<a id="实际输出与解释"></a>
## 4. Actual output and interpretation

See the supplied [事件结果.csv](../examples/results/conditional-energy-yaml/事件结果.csv) (event results) and [result-summary.json](../examples/results/conditional-energy-yaml/result-summary.json).

| 区间 | 开始时间（s） | 结束时间（s） | 区间状态 | energy_kwh（kWh） | energy_kwh：状态 |
|---|---|---|---|---|---|
| 1 | 61 | 122 | 正常结束 | 0.06777777777777777 | 完整 |

`区间` is the interval number; the next two columns are actual start and end times. `正常结束` means the interval ended normally, and `完整` means the calculation is complete. Only the 61-second activity qualifies. Its calculation range is `[61, 122)`, including the first 60 seconds.

The strict threshold is first met at 121.000000001 seconds—the first nanosecond strictly beyond 60 seconds from the onset. That confirmation does not change the integration start. The ordinary table does not save an extra confirmation timestamp; use `iter_events()` when your task needs it.

The manifest's `analysis_outcome.rules` reports one `eligible` event with `has_unknown: false`; `calculations.complete` is 1. These are counts, not energy values. A run marked completed means it ran and published successfully; calculation quality is reported separately.

Read the table without loading the whole result into memory:

```python
import csv
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
path = next(manifest_path.parent / item["name"]
            for item in manifest["outputs"]
            if item["name"].startswith("事件结果_"))
with path.open(encoding="utf-8-sig", newline="") as stream:
    for row in csv.DictReader(stream):
        print(row["开始时间（s）"], row["结束时间（s）"],
              row["energy_kwh（kWh）"], "kWh", row["energy_kwh：状态"])
```

Save this as `show_energy.py` and run `python show_energy.py "the manifest path from the CLI summary"`. The output is `61 122 0.06777777777777777 kWh 完整`. For existing programs that need the original `events` and `calculations` tables, select the [CSV or JSONL interchange format](results.md#choose-an-exchange-format-for-other-software).

<a id="换成自己的asc或blf"></a>
## 5. Replace the example with your ASC or BLF logs

Replace the log paths, DBC paths, IDs, and signal names. Keep the requested operators, duration comparison, and result unit. Do not approximate `> 60s` with `60.1s`, and do not alter timestamps to make the input pass.

By default, ASC checks the ordering of the required channel and message IDs. Other messages are inspected only as needed for the requested observation range. Full checking or raw-message export requires ordering checks across all frames. A target timestamp moving backwards is an error to investigate at its source; the program does not silently sort or clean it.

After substituting your logs, check the DBC signal positions and units, current direction, and continuity between files. Recalculate one interval with known start and end times. An independent checker must use the same validity, ordering, boundary, and file-continuity rules. A script that sorts the input and reaches the same total has not thereby verified every rule.
