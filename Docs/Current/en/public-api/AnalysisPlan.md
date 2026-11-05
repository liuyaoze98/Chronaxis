# chronaxis.AnalysisPlan

Import this object from `chronaxis`. This page lists its direct public members and necessary construction/context protocols. See the [module reference](../../reference/chronaxis.planning.plan.md) for internal implementation (Chinese implementation reference).

Return to the [public API index](../api.md). Linked parameter types lead to their definitions. Check required fields, defaults, return values, and exceptions before use.

Version 4 plans expose `plan.lookups`, the read-only collection of declared calibration tables. The collection is empty when no table is declared.

## Members

- [`AnalysisPlan`](#api-AnalysisPlan)
- [`AnalysisPlan.from_dict`](#api-AnalysisPlan-from_dict)
- [`AnalysisPlan.lookups`](#api-AnalysisPlan-lookups)
- [`AnalysisPlan.extensions`](#api-AnalysisPlan-extensions)

<a id="api-AnalysisPlan"></a>
## `AnalysisPlan`

Stores one session's analysis configuration and the objects produced by static checking.

Construct through from_dict or load_analysis_plan. The plan stores input sources, signals, derived calculations, condition rules, windows, and metrics. Instance fields cannot be reassigned. Configuration and free-form metadata are independent read-only snapshots, not references to mutable caller dictionaries or lists.

bindings describes which signal comes from which source; derived_expressions contains checked expression structures. Neither proves that real data has been read or that the plan is ready to execute. execution and outputs store declarations; construction does not run calculations or publish files.

identity is computed from configuration and source-location declarations to distinguish plans. It does not verify CSV contents, actual columns, memory usage, or analysis results. Bindings and declarations from separate constructions are independent.

```python
AnalysisPlan(config_version: int, dataset: chronaxis.planning.models.DatasetPlan, sources: tuple[chronaxis.planning.models.SourcePlan, ...], signals: tuple[chronaxis.planning.models.SignalPlan, ...], derived: tuple[chronaxis.planning.models.DerivedPlan, ...], rules: tuple[chronaxis.planning.models.RulePlan, ...], windows: tuple[chronaxis.planning.models.WindowPlan, ...], calculations: tuple[chronaxis.planning.models.CalculationPlan, ...], presets: tuple[chronaxis.planning.preset_models.PresetSpec, ...], preset_bindings: tuple[tuple[chronaxis.planning.preset_models.RoleBinding, ...], ...], execution: chronaxis.planning.models.ExecutionPlan, outputs: chronaxis.planning.models.OutputPlan, bindings: chronaxis.core.declarations.DeclarationBindings, derived_expressions: tuple[chronaxis.core.expression.StaticExpression, ...], metadata: collections.abc.Mapping, raw_config: collections.abc.Mapping, base_dir: pathlib.Path, identity: str, message_calculations: tuple[chronaxis.planning.models.MessageCalculationPlan, ...] = (), sequences: tuple[chronaxis.planning.sequences.SequencePlan, ...] = (), intervals: 'IntervalPlan | None' = None, diagnostics: 'DiagnosticPlan | None' = None, aggregations: tuple[chronaxis.planning.aggregations.AggregationPlan, ...] = (), transforms: tuple[chronaxis.planning.transforms.TemporalTransformPlan, ...] = ()) -> None
```

### Properties and data fields

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`config_version`|int|Yes|No default|Analysis configuration structure version: native integer 4. This is not the software or preset version. Boolean values and other versions are rejected.|
|`dataset`|[DatasetPlan](../../reference/chronaxis.planning.models.md#api-DatasetPlan)|Yes|No default|Analysis entity, session, and requested time range.|
|`sources`|tuple[[SourcePlan](../../reference/chronaxis.planning.models.md#api-SourcePlan), ...]|Yes|No default|Parsed source configurations in declaration order.|
|`signals`|tuple[[SignalPlan](../../reference/chronaxis.planning.models.md#api-SignalPlan), ...]|Yes|No default|Original fields, signal names, types, units, and validity declarations.|
|`derived`|tuple[[DerivedPlan](../../reference/chronaxis.planning.models.md#api-DerivedPlan), ...]|Yes|No default|New signals calculated from existing ones, such as power, with their metadata.|
|`rules`|tuple[[RulePlan](../../reference/chronaxis.planning.models.md#api-RulePlan), ...]|Yes|No default|Checked Boolean conditions and temporal rules.|
|`windows`|tuple[[WindowPlan](../../reference/chronaxis.planning.models.md#api-WindowPlan), ...]|Yes|No default|Checked windows around activities or points and their referenced rules.|
|`calculations`|tuple[[CalculationPlan](../../reference/chronaxis.planning.models.md#api-CalculationPlan), ...]|Yes|No default|Metrics with scope, calculation semantics, units, and missing-data policies.|
|`presets`|tuple[[PresetSpec](PresetSpec.md#api-PresetSpec), ...]|Yes|No default|Original frozen v1 preset declarations, retaining generation parameters.|
|`preset_bindings`|tuple[tuple[[RoleBinding](../../reference/chronaxis.planning.preset_models.md#api-RoleBinding), ...], ...]|Yes|No default|Role-to-signal bindings produced at loading. The outer tuple follows plan.presets order. Each inner RoleBinding stores contract (role requirements), definition (selected original signal), and resolution (explicit or semantic_unique). With no presets this is (). Pair using zip(plan.presets, plan.preset_bindings), then read attributes such as binding.definition.name; see the example.|
|`execution`|[ExecutionPlan](../../reference/chronaxis.planning.models.md#api-ExecutionPlan)|Yes|No default|Calculation backend, batch size, and declared resource budgets; execution has not occurred.|
|`outputs`|[OutputPlan](../../reference/chronaxis.planning.models.md#api-OutputPlan)|Yes|No default|Result-table and manifest format declarations; files have not been written.|
|`bindings`|[DeclarationBindings](../../reference/chronaxis.core.declarations.md#api-DeclarationBindings)|Yes|No default|Declared name-to-source relationships, without actual signal values.|
|`derived_expressions`|tuple[[StaticExpression](../../reference/chronaxis.core.expression.md#api-StaticExpression), ...]|Yes|No default|Checked derived-expression structures, with cycles rejected.|
|`metadata`|Mapping|Yes|No default|Caller-supplied read-only notes that do not change calculation rules.|
|`raw_config`|Mapping|Yes|No default|Internal read-only snapshot from parsing, not original user text. Omitted fields are not necessarily all expanded, and fields may use internal parsed forms. Use config resolve for editable current public configuration.|
|`base_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|Yes|No default|Absolute base directory for relative source paths.|
|`identity`|str|Yes|No default|SHA-256 identity of configuration and source-location declarations, not file contents.|
|`message_calculations`|tuple[[MessageCalculationPlan](../../reference/chronaxis.planning.models.md#api-MessageCalculationPlan), ...]|No|()|Parsed per-message calculation tuple; () means none. Executed separately from ordinary calculations.|
|`sequences`|tuple[[SequencePlan](../../reference/chronaxis.planning.sequences.md#api-SequencePlan), ...]|No|()|Parsed request/response pairing tuple; () means no pairing.|
|`intervals`|'[IntervalPlan](../../reference/chronaxis.planning.intervals.md#api-IntervalPlan) &#124; None'|No|None|Finite interval declaration for the current record stream.|
|`diagnostics`|'[DiagnosticPlan](../../reference/chronaxis.planning.intervals.md#api-DiagnosticPlan) &#124; None'|No|None|Separate requests for tracing, integrity checks, and retained work files.|
|`aggregations`|tuple[[AggregationPlan](../../reference/chronaxis.planning.aggregations.md#api-AggregationPlan), ...]|No|()|Validated v4 group reductions in declaration order. Each selects one named result population, operation and grouping policy. An empty tuple requests no group reductions.|
|`transforms`|tuple[[TemporalTransformPlan](../../reference/chronaxis.planning.transforms.md#api-TemporalTransformPlan), ...]|No|()|Declarations in dependency order. Each carries the output unit, timing, coverage policy, and input names for a temporal transform.|

### Example

```python
from chronaxis import load_analysis_plan

# Run from the repository root; this file defines the required sources, signals, and preset.
plan = load_analysis_plan("Docs/Current/examples/preset-charge-minimal.yaml")
for preset, bindings in zip(plan.presets, plan.preset_bindings):
    for binding in bindings:
        print(preset.id, binding.contract.role,
              binding.definition.name, binding.resolution)
# demo_preset mode mode explicit
# demo_preset current current explicit
```

<a id="api-AnalysisPlan-from_dict"></a>
### `AnalysisPlan.from_dict`

Copies the configuration dictionary and validates the requirements for the current configuration version (4). Execution capabilities are validated separately.

```python
AnalysisPlan.from_dict(config: dict, *, base_dir: Path | str | None=None, extensions=None) -> 'AnalysisPlan'
```

Decorators: `classmethod`, `public_errors`.

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`config`|dict[str, object]|Yes|No default|Positional or keyword. Current public analysis dictionary including config_version (4), dataset, sources, and signals. Unexpanded imports are rejected. Directory declarations enumerate filenames and omitted CAN metadata may read DBC; business records are not read. See [Configuration fields](../configuration-reference.md).|
|`base_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; str &#124; None|No|None|Keyword-only. Base directory for relative source paths. None uses the current working directory; a Path or string becomes an absolute path.|
|`extensions`|ExtensionRegistry &#124; None|No|None|Keyword-only host registry used to compile this v4 plan. Pass the same instance to the runner.|

#### Returns

AnalysisPlan containing statically checked sources, signals, and calculation nodes. raw_config and metadata are independent read-only snapshots. Plan construction does not read analysis data.

#### Raises

PlanValidationError for invalid fields/versions, name conflicts, expression/reference errors, invalid input models, or requested capabilities without an execution path. The error retains the configuration location. OSError can propagate from obtaining the working directory or converting paths.

#### Processing

Checks the current public configuration, expands nodes, and parses sources/signals. Directory declarations enumerate filenames; missing CAN metadata is filled from the DBC. References, types, and units are then checked before constructing an independent plan. No business records are read and no analysis is run.

Return type: '[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)'。

<a id="api-AnalysisPlan-lookups"></a>
### `AnalysisPlan.lookups`

```python
AnalysisPlan.lookups
```

Read `plan.lookups` to get the tuple of [LookupTablePlan](../../reference/chronaxis.core.lookup.md#api-LookupTablePlan) objects in declaration order. Each table records the input unit, output unit, and calibration points. The tuple is empty when the plan declares no tables.

<a id="api-AnalysisPlan-extensions"></a>
### `AnalysisPlan.extensions`

```python
AnalysisPlan.extensions
```

Returns the immutable registry passed when compiling this plan, or None if the host omitted it. Reading this property leaves callbacks uninstantiated.

## Host-registered operations

Register trusted callbacks in Python and pass the same immutable registry when loading and running a v4 plan. See the [worked host example](../host-extensions.md).

## Source locations

- [`src/chronaxis/planning/plan.py:63`](../../../../src/chronaxis/planning/plan.py#L63) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/planning/plan.py:109`](../../../../src/chronaxis/planning/plan.py#L109) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/planning/plan.py:114`](../../../../src/chronaxis/planning/plan.py#L114) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
- [`src/chronaxis/planning/plan.py:121`](../../../../src/chronaxis/planning/plan.py#L121) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
