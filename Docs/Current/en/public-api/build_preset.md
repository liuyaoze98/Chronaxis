# chronaxis.build_preset

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.presets.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-build_preset"></a>
## `build_preset`

Validate a version-1 preset and expand public declarations, without I/O or numerical analysis.

```python
build_preset(spec: PresetSpec, signals: tuple[SignalDefinition, ...]) -> PlanFragment
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`spec`|[PresetSpec](PresetSpec.md#api-PresetSpec)|Yes|No default|Positional or keyword. Create through PresetSpec.from_dict using required name/preset_type/parameters and optional version/role_bindings. See the preset API examples.|
|`signals`|tuple[[SignalDefinition](../../reference/chronaxis.core.binding.md#api-SignalDefinition), ...]|Yes|No default|Positional or keyword. Signal definitions for this plan, such as `tuple(item.definition for item in plan.signals)` after load_analysis_plan. Roles refer to definition names, not directly to CSV columns. Type link is a Chinese implementation reference.|

Returns [PlanFragment](PlanFragment.md#api-PlanFragment), generating the requested power/Wh/Ah, alarm context, threshold hysteresis/per-activity durations, or response pairing.

Raises `PlanValidationError` for parameters, role contracts, mode-code ranges, or generated IDs colliding with signals. In particular, mode codes must fit declared dtype/valid_range.

Processing checks roles, generates an expression using simple aliases, constructs typed nodes, and rejects visible ID conflicts. AnalysisPlan checks conflicts against other user nodes and presets when merging the fragment.

## Source locations

- [`src/chronaxis/presets.py:158`](../../../../src/chronaxis/presets.py#L158) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
