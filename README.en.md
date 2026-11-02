# Chronaxis

[简体中文](README.md) | **English**

[Repository](https://github.com/liuyaoze98/Chronaxis) · [Issues](https://github.com/liuyaoze98/Chronaxis/issues)

## Why Chronaxis was started

Engineering data analysis often involves repeating similar work: processing another set of logs, adjusting a condition, or recalculating a metric for a particular process. As vehicle variants, test projects, and file formats accumulate, separate scripts tend to duplicate reading and calculation logic, making analysis rules harder to reuse and maintain.

Chronaxis aims to bring log reading, condition filtering, and metric calculation into a reusable Python library. Engineers can describe analysis tasks through configuration, and developers can integrate the same workflows into existing applications, reducing the need to write new scripts whenever data or analysis rules change.

## Intended applications

The project originated from automotive and battery test analysis. Its intended applications include summarizing test results, investigating faults, comparing test batches, and calculating metrics after automated tests. As input formats and analysis methods expand, the project also aims to apply these methods to test data from other equipment.

## Current capabilities

- Find intervals where conditions remain true, such as current exceeding a specified value for one minute.
- Detect when alarms start and clear, match requests with responses, and identify timeouts.
- Calculate integrals, durations, and statistics over selected intervals, or compare values before and after events.
- Analyze consecutive log files as one recording; run independent tests separately and summarize their results.
- Export readable result tables and, when requested, raw message segments around events.
- Run YAML/JSON configurations or integrate through the Python API.

| Input | How it is used |
|---|---|
| BLF, ASC, raw-message CSV | Decode signals with the corresponding DBC; raw-message CSV also requires column and format declarations |
| Decoded-signal CSV | Configure time and signal columns; no DBC required |
| In-memory data | Pass signal values and timestamps already held by your program through the Python API |

## Installation and environment

The current version is **0.1.0.dev1**, a development preview. Use **Windows and Python 3.12** to install and run it. Interfaces and configuration may change during the preview; see the [version policy](Docs/Release/versioning.md) for upgrade guidance.

Install from PyPI:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "chronaxis==0.1.0.dev1"
.\.venv\Scripts\python.exe -m chronaxis --help
```

To install from source, run `python -m pip install .` at the repository root containing `pyproject.toml`. If you have a release wheel, replace the installation command with:

```powershell
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev1-py3-none-any.whl"
```

Installation automatically includes the dependencies needed for CAN reading, DBC decoding, and other features. For offline installation, prepare the dependency packages in advance; see the [installation guide](Docs/Current/en/installation.md).

## Quick start: configuration

This example uses the repository's **synthetic ASC and DBC files** to calculate energy. It first finds intervals where the state equals `0x2` and current is at least `10A` continuously for more than `60s`, then integrates current times voltage over each qualifying interval and converts the result to `kWh`.

The configuration and data are included with the source:

| File | Purpose |
|---|---|
| [conditional-energy.yaml](Docs/Current/examples/conditional-energy.yaml) | Complete configuration with signal bindings, conditions, duration threshold, and integration |
| [part-1.asc](Docs/Current/examples/data/can/conditional-energy/part-1.asc), [part-2.asc](Docs/Current/examples/data/can/conditional-energy/part-2.asc) | Two consecutive log files |
| [signals.dbc](Docs/Current/examples/data/can/conditional-energy/signals.dbc) | Matching signal definitions |

Keep the source directory structure and run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m chronaxis validate Docs/Current/examples/conditional-energy.yaml
.\.venv\Scripts\python.exe -m chronaxis run Docs/Current/examples/conditional-energy.yaml --output result-cli
```

`result-cli` must be a new directory. Command-line paths are relative to the working directory; data paths inside a configuration are relative to that configuration file.

The example produces one qualifying event. The key columns in `result-cli/事件结果.csv` are shown below; the current readable output uses these Chinese headers:

| 开始时间（s） / Start | 结束时间（s） / End | energy_kwh（kWh） | energy_kwh：状态 / Status |
|---|---|---|---|
| 61 | 122 | 0.06777777777777777 | 完整 / Complete |

The first interval lasts exactly 60 seconds and is excluded. The second spans both files and lasts 61 seconds. Its power is 4000 W, giving `4000 × 61 ÷ 3600000` kWh. Integration includes the first 60 seconds of the qualifying interval.

For your own logs, adjust the signal bindings, conditions, and time settings to match your DBC and analysis goal. See the [full tutorial](Docs/Current/en/conditional-energy.md) for instructions and output details.

## Quick start: Python API

This code runs the same task with the same configuration. Save it as `example_energy.py` at the repository root and run it using the virtual environment above. `result-python` must also be a new directory.

```python
from contextlib import closing
from chronaxis import AnalysisRunner, load_analysis_plan

if __name__ == "__main__":
    plan = load_analysis_plan("Docs/Current/examples/conditional-energy.yaml")
    with AnalysisRunner().run(plan) as result:
        with closing(result.iter_calculations()) as rows:
            for row in rows:
                print(row.calculation_id, row.value, row.unit, row.status)
        result.write("result-python")
```

Run:

```powershell
.\.venv\Scripts\python.exe example_energy.py
```

It prints the `energy_kwh` value, unit, and status, and writes the same results as the command-line example. Keep the `if __name__ == "__main__":` block, which is required to start the analysis on Windows. See the [Python API guide](Docs/Current/en/api-usage.md) and [public API reference](Docs/Current/en/api.md).

## Commands and documentation

Append these commands to `python -m chronaxis`; add `--help` for their arguments.

| Command | Purpose |
|---|---|
| `config init --list` | List available example scenarios |
| `validate` / `explain` | Validate configuration / explain dependencies and execution settings |
| `run` | Run one analysis and write results |
| `batch run` | Run independent analysis tasks |
| `config resolve` / `config origins` | Inspect expanded configuration / where definitions originate |
| `guide` | Show the directly readable AI guide path; use `--language en` for English |

- [Online HTML manual](https://liuyaoze98.github.io/Chronaxis/en/): configuration, execution, and result interpretation. The [source manual](Docs/Current/en/index.md) is also readable locally.
- [Configuration guide](Docs/Current/en/configuration.md) and [complete field reference](Docs/Current/en/reference/configuration-schema.md).
- [Source AI guide](Docs/AI/en/README.md): read directly and find task examples, APIs, and fields without exporting first.
- [Independent batch tasks](Docs/Current/en/batch.md) and [results](Docs/Current/en/results.md).
- [Version policy](Docs/Release/versioning.md), [distribution scope](Docs/Release/distribution.md), and [third-party notices](Docs/Release/third-party.md).

## Feedback and contributing

Send questions and suggestions to [work@liuyaoze.com](mailto:work@liuyaoze.com) or [GitHub Issues](https://github.com/liuyaoze98/Chronaxis/issues). When reporting a problem, include the package version, Python and OS versions, a minimal configuration, reproduction steps, and the expected and actual results.

Contributors can start with the [public test commands](Docs/Release/distribution.md) and [documentation maintenance guide](Docs/Current/en/maintenance.md). See the [dependency security notes](Docs/Release/security.md) for known dependency issues.

## Funding acknowledgement

We gratefully acknowledge funding for Chronaxis from Zhengzhou Nissan Automobile Co., Ltd. (郑州日产汽车有限公司) through its 2025 innovation research program.

## AI tools disclosure

Chronaxis was developed using Codex. Workbuddy and Trae CN were used to test how AI interprets the project's documentation and usage instructions.

## License and maintainer

Chronaxis is licensed under the [MIT License](LICENSE). It is maintained by **liuyaoze**, who can be contacted at [work@liuyaoze.com](mailto:work@liuyaoze.com). Third-party dependencies and bundled resources remain subject to their respective licenses.
