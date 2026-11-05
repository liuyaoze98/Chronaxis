# Custom analysis operators (Python extensions)

A Python program can add three kinds of analysis: pointwise expression functions, sample statistics that combine selected samples into one result, and temporal transforms that produce values over time. Python supplies and registers the implementation; configuration calls it by name. YAML cannot import or execute arbitrary Python files. The Python program that registers and runs these algorithms is the host program; this mechanism is also called host extensions.

|Kind|Configuration call site|Input → output|
|---|---|---|
|Pointwise FunctionSpec|A function in expr, such as double_current(current)|Values at one time → one value; separate reference and NumPy implementations|
|Sample-statistic ReductionSpec|calculations[].operation|Selected valid real updates in one scope → one scalar result|
|Temporal TransformSpec|transforms[].operation|Window values and duration weights at an output time → a value; may retain state for the session|

## Connect a custom operator

Run the complete supplied Python example before editing callbacks. ExtensionRegistry associates a call name with its types, units, and implementation. Pass the same registry object while loading and running the plan; a name in configuration alone does not install an algorithm.

A host Python application can add its own calibration function, sample reduction or stateful grid calculation. The configuration refers to the registered name. Download the [host program](../examples/temporal/host_extensions.py), [host configuration](../examples/temporal/host-analysis.yaml), [ASC](../examples/temporal/meter.asc) and [DBC](../examples/temporal/meter.dbc) into one directory.

```powershell
python host_extensions.py --plan host-analysis.yaml --backend reference --work-dir host-ref
python host_extensions.py --backend numpy --work-dir host-numpy
```

Use `--plan` to select a configuration file. The first command specifies the file in the current directory. The second omits the option and loads `host-analysis.yaml` beside the Python program. ASC and DBC paths are relative to the selected configuration.

The `double_current` function produces 20, 40, 80 and 10 A. The `peak_reading` reduction returns **80 A, complete**. The `best_grid_mean` transform computes the mean over each 0.12 s window and remembers the highest mean so far. Its outputs at 0.12, 0.24, 0.36 and 0.48 s are 10, 20, 30 and 30 A. At the last tick the current window's mean has fallen to 22.5 A.

## Supply the registry

This registration excerpt belongs after the definitions of `double_reference` and `double_numpy` in the downloadable host program. It depends on those functions and is not a standalone script.

```python
from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.core.types import SignalDType
from chronaxis.extensions import ExtensionRegistry, FunctionSpec, ValueSpec

amp = ValueSpec(SignalDType.FLOAT64, "A")
registry = ExtensionRegistry(functions=(
    FunctionSpec("double_current", "1", (amp,), amp, double_reference, double_numpy),
))
```

This excerpt registers the point function. The downloadable program also supplies the `reductions` and `transforms` tuples. Pass **the same object** to `load_analysis_plan(path, extensions=registry)` or `AnalysisPlan.from_dict(raw, extensions=registry)` and to `AnalysisRunner(backend, extensions=registry)`. The standard CLI only knows built-ins. Run the host program when your YAML uses host names. For built-in point functions, `chronaxis.extensions.builtin_function_specs(4)` returns a read-only catalog with signatures, type, constant, unit, validity, update and backend rules.

|Descriptor|Input|Output and lifetime|
|---|---|---|
|FunctionSpec|Arguments are passed in their declared order. The reference implementation receives a tuple of ScalarValue objects. NumPy receives a tuple of NumericArray columns with only rows where every required input is valid.|Return one value or one correctly sized column of the declared type. Temporary memory reservations end with the call.|
|ReductionSpec|The factory creates one state for each calculation scope, retained across its batches. Its consume(values) receives selected valid real sample updates.|finalize() returns a ScalarValue. A descriptor with mergeable=True may merge two compatible states using the same implementation and backend.|
|TransformSpec|One state per session. Its advance(time_ns, window_ns, values, weights_ns) receives the actual output timestamp, window length, and valid held values with their weights in chronological order.|Return a ScalarValue for that tick. The state may retain information between ticks. history_ns is the largest lookback the implementation accepts.|

`TransformSpec.interval_modes` defaults to actual, fixed and dbc. A particular implementation may declare a smaller set. Fixed and DBC weights prorate the chosen frame period by actual overlap. The grid timestamp stays on the real clock. Reference implementations receive positive integer or Fraction nanoseconds. NumPy receives int64 nanoseconds, or float64 nanoseconds when fractional weights occur. An implementation requiring integer actual weights may specify `interval_modes=("actual",)`. Supply a separate implementation for each supported backend.

Declare fixed state in `state_bytes`. Inside a callback, reserve dynamic bytes with `resources.reserve(n)` before allocating and release them with `resources.release(n)` when done. Stateful implementations provide `cancel()` and `close()` for cancellation and cleanup. Declaring an unused transform creates no runtime state. The program identifies an implementation by its name, algorithm version, input/output types and units, available backends, and memory/history settings. Change the version when changing the algorithm. Registered callbacks run as trusted host Python code.

## Complete descriptor and callback reference

Import these names from chronaxis.extensions. The supplied complete example implements all three kinds. None means a backend implementation is absent, not that every backend is supported. Supply at least one implementation, including the backend selected for execution.

|Constructor signature|Parameters and return|
|---|---|
|ValueSpec(dtype, unit)|SignalDType and registered unit; Boolean uses 1, enum is not accepted directly; returns an immutable value declaration|
|FunctionSpec(name, version, inputs, output, reference=None, numpy=None)|inputs is a tuple of ValueSpec, output is one ValueSpec; callbacks follow the table below; returns a pointwise descriptor|
|ReductionSpec(name, version, input, output, reference=None, numpy=None, state_bytes=0, mergeable=False)|Numeric ValueSpec input/output; callbacks create states; nonnegative integer fixed state_bytes and Boolean mergeable|
|TransformSpec(name, version, input, output, reference=None, numpy=None, state_bytes=0, history_ns=0, interval_modes=('actual','fixed','dbc'))|Numeric input/output; explicitly supply positive int64 history_ns, because default 0 is invalid; interval_modes is a nonempty tuple of distinct supported modes|
|ExtensionRegistry(functions=(), reductions=(), transforms=())|Tuples of the corresponding descriptors; returns an immutable registry; names must be unique across kinds and must not replace built-ins|

name is a valid analysis identifier; version is nonempty algorithm-version text, updated by the author when behavior changes. Invalid types, units, names, or resource settings fail construction. Registration does not verify the algorithm's mathematical correctness.

|Interface|Arguments|Return and lifecycle|
|---|---|---|
|Pointwise reference(args, resources)|ScalarValue tuple in declared order and temporary-memory interface|ScalarValue matching the declaration; called only for valid required inputs|
|Pointwise numpy(args, resources)|NumericArray tuple in declared order, containing rows where all required inputs are valid|Same-length NumericArray of the declared type; preserve row order|
|Reduction reference(resources) / numpy(resources)|Memory-allocation interface for this scope|Independent state for each scope, retained across batches|
|Reduction state.consume(values)|ScalarValue sequence for reference, NumericArray for NumPy; selected valid real updates|None; accumulate this batch into the scope state|
|Reduction state.finalize()|No arguments|ScalarValue of the declared type when the scope ends|
|Reduction state.merge(other)|Another state for the same algorithm, version, and backend|Required only when mergeable=True; merge into the current state|
|Transform reference(resources) / numpy(resources)|Memory interface for this session|Independent per-session state|
|Transform state.advance(time_ns, window_ns, values, weights_ns)|Actual output time, window width, ordered valid held values, and weights|ScalarValue for the output point; retained state may serve later points, within history_ns|
|State cancel() / close()|No arguments|Cancellation notification / final resource release; cleanup must work on success, failure, and cancellation|

Invalid callback signatures, result types, array lengths, or quality declarations fail execution and preserve the original error. Do not replace failures with apparently valid zero values. ScalarValue/NumericArray valid and quality fields express missing values or numeric failures.
