# chronaxis.PresetSpec

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.planning.preset_models.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

## Members

- [PresetSpec](#api-PresetSpec)
- [from_dict](#api-PresetSpec-from_dict)

<a id="api-PresetSpec"></a>
## `PresetSpec`

Freeze a preset ID, type/version, role aliases, and parameters as an independent JSON snapshot. The ID is a simple identifier. Role values reference simple aliases in the current plan, not domain attribute paths. Parameters do not retain caller-owned mutable objects. build_preset validates the actual type-specific parameters.

```python
PresetSpec(id: str, preset_type: str, version: str, role_bindings: collections.abc.Mapping, parameters: collections.abc.Mapping) -> None
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| `id` | str | Required | Unique preset instance name, such as hot; generated names use this prefix and must not collide with existing nodes. |
| `preset_type` | str | Required | charge_session, fault_context, command_response, or threshold_excursion. See [presets](../presets.md) for their purposes and roles. |
| `version` | str | Required | Current template version is string `"1"`, not number 1 or the top-level config_version. |
| `role_bindings` | Mapping | Required | Map permitted roles to defined signals, for example `{"signal": "temperature"}`. Omitted roles require the documented semantic lookup declarations. |
| `parameters` | Mapping | Required | Type-specific parameters, such as threshold unit/enter_threshold/exit_threshold. Obtain values from business requirements and device units; do not mix different preset types' fields. |

<a id="api-PresetSpec-from_dict"></a>
### `PresetSpec.from_dict`

Build an immutable public declaration from the current configuration format.

```python
PresetSpec.from_dict(value)
```

Class method.

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `value` | dict[str, object] | Required | Positional or keyword. Requires name, preset_type, and parameters. Omitted version is string `"1"`; omitted role_bindings is an empty mapping. See [role requirements](../presets.md). |

Returns PresetSpec. Raises `PlanValidationError` for unknown keys, missing fields, or construction-protocol errors.

```python
from chronaxis import PresetSpec

# Full role and threshold semantics are checked when the plan is assembled.
spec = PresetSpec.from_dict({
    "name": "heat_alarm",
    "preset_type": "threshold_excursion",
    "version": "1",
    "role_bindings": {"signal": "temperature"},
    "parameters": {"unit": "degC", "enter_threshold": 80, "exit_threshold": 75},
})
print(spec.id, spec.preset_type)
```

## Source locations

- [`src/chronaxis/planning/preset_models.py:52`](../../../../src/chronaxis/planning/preset_models.py#L52) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
- [`src/chronaxis/planning/preset_models.py:90`](../../../../src/chronaxis/planning/preset_models.py#L90) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
