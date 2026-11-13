# chronaxis.resolve_preset_roles

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.presets.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-resolve_preset_roles"></a>
## `resolve_preset_roles`

Resolve actual roles, preferring explicit mappings. Otherwise find exactly one candidate satisfying the versioned semantic requirements.

```python
resolve_preset_roles(spec: PresetSpec, signals: tuple[SignalDefinition, ...]) -> tuple[RoleBinding, ...]
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`spec`|[PresetSpec](PresetSpec.md#api-PresetSpec)|Yes|No default|Positional or keyword. Create through PresetSpec.from_dict with required name/preset_type/parameters and optional version/role_bindings.|
|`signals`|tuple[[SignalDefinition](../../reference/chronaxis.core.binding.md#api-SignalDefinition), ...]|Yes|No default|Positional or keyword. Definitions for this plan, such as `tuple(item.definition for item in plan.signals)` after load_analysis_plan. Roles refer to definition names, not CSV column names. Type link is a Chinese implementation reference.|

Returns a tuple of [RoleBinding](../../reference/chronaxis.planning.preset_models.md#api-RoleBinding) (Chinese implementation reference), preserving original definitions and the `explicit` / `semantic_unique` resolution path.

Raises `PlanValidationError` for wrong types, duplicate aliases, unknown/missing roles, ambiguous candidates, or contract conflicts. Specific failures include requiring PresetSpec plus a SignalDefinition tuple, duplicate signal aliases, and threshold_excursion missing its mandatory explicit signal role.

Explicit aliases do not require semantic_id, but type, unit, direction, location, and quality requirements still apply. The resolver never silently picks the first candidate.

## Source locations

- [`src/chronaxis/presets.py:104`](../../../../src/chronaxis/presets.py#L104) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
