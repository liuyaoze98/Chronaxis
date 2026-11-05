<a id="blfasc快速开始直接计算报文中的能量"></a>
# BLF and ASC quick start: calculate energy from CAN messages

You can analyze CAN logs without first converting them to CSV or writing a Python entry function. Complete [installation](installation.md), then run this small, synthetic CAN example.

<a id="准备日志和dbc"></a>
## 1. Prepare the log and DBC

Use [quickstart.asc](../examples/data/can/quickstart.asc) and [teaching.dbc](../examples/data/can/teaching.dbc). The ASC file uses channel 1, so its configuration also uses channel 1. Message `0x100` in the DBC contains the signal `Power`, measured in W.

| Time (s) | Message ID | Power (W) |
|---|---|---|
| 0 | 0x100 | 2 |
| 1 | 0x100 | 4 |
| 3 | 0x100 | 8 |
| 4 | 0x100 | 10 |
| 6 | 0x7FE | Unrelated message; establishes the end of observation |

The final record is not a power sample. With zero-order hold, each power value applies until the next update, within its validity period. This example integrates over `[0, 6)`. Unequal sample spacing means the sample mean and time-weighted mean are different.

<a id="保存配置并运行"></a>
## 2. Save the configuration and run it

The complete file is [analysis.yaml](../examples/analysis.yaml). Its input paths are relative to the directory containing that configuration file.

In YAML, indentation defines nesting. Here, two spaces indent a child field, and `-` starts a list item. A reference such as `dataset.name` describes the field's location: write `name` indented beneath `dataset`, not a literal key named `dataset.name`. See [configuration notation](configuration-language.md#field-paths).

```yaml
config_version: 4                     # Current analysis configuration version
dataset:                              # Analysis identity and optional input range
  name: energy                        # Name of this analysis
sources:                              # Input sources used by this analysis
  - paths: data/can/quickstart.asc    # Relative to this YAML file
    dbc_by_channel:                   # DBC files indexed by user-facing CAN channel
      '1': data/can/teaching.dbc      # Public channel numbers start at 1
signals:                              # Signals available to expressions
  - name: power                       # Name used in expressions
    field:                            # Locate the original input field
      frame_id: '0x100'               # CAN message ID
      signal: Power                   # Signal name in the DBC
calculations:                         # Requested statistics or selected rows
  - name: energy                      # Result column name
    operation: integral               # Integrate power over time
    expr: power                       # Formula using the declared signal or derived names
  - name: sample_average              # Name used to identify and reference this object
    operation: sample_mean            # Equal weight for each sample
    expr: power                       # Formula using the declared signal or derived names
  - name: time_average                # Name used to identify and reference this object
    operation: time_weighted_mean     # Weight by valid time
    expr: power                       # Formula using the declared signal or derived names
```

Only the analysis name, log and DBC paths, signal, and three calculations are needed. There is no need to specify `session`, `entity`, `source_type`, `time_type`, a reference to the only source, or the default session scope. Signal type and unit come from the DBC; a unique channel is selected automatically. Omitting `domain` uses the observed range.

From the examples directory, run:

```powershell
chronaxis validate analysis.yaml
chronaxis run analysis.yaml --output new-result
```

The output directory can be reused; each publication uses timestamped filenames. `validate` checks the declarations and required DBC metadata; `run` reads the actual messages and produces results. If the virtual environment is not activated, invoke its Python executable with `-m chronaxis`.

<a id="核对结果"></a>
## 3. Check the results

Open `new-result/会话结果_<timestamp>.csv` (session results). The [example output](example-results.md#analysis-yaml) explains the columns.

| Calculation | Expected value | Meaning |
|---|---|---|
| `energy` | 38 J | `2 × 1 + 4 × 2 + 8 × 1 + 10 × 2` |
| `sample_average` | 6 W | `(2 + 4 + 8 + 10) / 4` |
| `time_average` | 6.333333333333333 W | `38 / 6` |

All three values appear in one row, each with status `完整` (complete) and no reason text. Dataset, entity, and session names inherit `energy`; this identity is saved once in the manifest. For programmatic reading, see [Python API usage](api-usage.md).

<a id="直接试用目录和blf"></a>
## 4. Try directory input and BLF

[input-can-directory.yaml](../examples/input-can-directory.yaml) reads `part1.asc` and `part2.asc` from `quickstart-parts` in natural filename order. It produces the same 38 J, 6 W, and `38 / 6` W.

```powershell
chronaxis run input-can-directory.yaml --output directory-result
```

From the examples directory, generate an equivalent BLF example and mixed-format inputs in a new directory:

```powershell
python prepare_can_examples.py --output can-demo
chronaxis run can-demo/blf.json --output blf-result
```

[prepare_can_examples.py](../examples/prepare_can_examples.py) creates three equivalent datasets and their configurations, checks that their results agree, and writes only to the selected working directory. For your own BLF logs, use their paths directly; you do not need this teaching-data generator.

<a id="换成自己的blfasc或日志目录"></a>
## 5. Use your own BLF, ASC, or log directory

1. Replace `paths` with a file or a directory of continuous logs. ASC and BLF are detected from their extensions. Directory input uses natural ordering, so `part2` precedes `part10`.
2. Set `dbc_by_channel` to your DBC files. User-facing channel numbers start at 1.
3. Select `frame_id` and `signal` from the DBC. A message name is unnecessary. IDs accept `0x` hexadecimal, `0b` binary, and unprefixed decimal notation.
4. Set `dataset.name`. Add a `domain` only to analyze a restricted time range, and add other features when the task needs them.

When `valid_for` is omitted, the validity period is three times the signal period obtained from the DBC. If no period is available, supply `period` or `valid_for`. Use actual signal definitions to determine units and current direction; names alone cannot establish them.

Use [batch tasks](batch.md) for independent experiments. Do not concatenate independent files whose clocks each restart at zero. For decoded CSV columns, see [input configuration](inputs.md).

[analysis.json](../examples/analysis.json) contains the same configuration in JSON. [run_example.py](../examples/run_example.py) checks the configuration formats and calculation backends. [api_example.py](../examples/api_example.py) demonstrates the Python interface.
