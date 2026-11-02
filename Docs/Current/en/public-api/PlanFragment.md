# chronaxis.PlanFragment

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.planning.preset_models.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

## Members

- [PlanFragment](#api-PlanFragment)
- [to_dict](#api-PlanFragment-to_dict)

<a id="api-PlanFragment"></a>
## `PlanFragment`

A preset-generated set of derived values, rules, windows, calculations, and pairings. Merge it into a full plan for execution. It contains no real samples and reads no files itself. Generated IDs must still be unique against user-defined IDs.

```python
PlanFragment(derived: tuple[chronaxis.core.expression.DerivedDefinition, ...] = (), rules: tuple[chronaxis.planning.preset_models.PresetRule, ...] = (), windows: tuple[chronaxis.core.windows.WindowSpec, ...] = (), calculations: tuple[chronaxis.planning.preset_models.PresetCalculation, ...] = (), sequences: tuple[chronaxis.planning.sequences.SequencePlan, ...] = ()) -> None
```

The linked lower-level types are Chinese implementation references.

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| `derived` | tuple[[DerivedDefinition](../../reference/chronaxis.core.expression.md#api-DerivedDefinition), ...] | Optional; () | Generated derived definitions; empty means none. |
| `rules` | tuple[[PresetRule](../../reference/chronaxis.planning.preset_models.md#api-PresetRule), ...] | Optional; () | Generated detection rules; empty means none. |
| `windows` | tuple[[WindowSpec](../../reference/chronaxis.core.windows.md#api-WindowSpec), ...] | Optional; () | Generated event windows; empty means none. |
| `calculations` | tuple[[PresetCalculation](../../reference/chronaxis.planning.preset_models.md#api-PresetCalculation), ...] | Optional; () | Generated calculation definitions; empty means none. |
| `sequences` | tuple[[SequencePlan](../../reference/chronaxis.planning.sequences.md#api-SequencePlan), ...] | Optional; () | Generated pairings. Nonempty values become a sequences list in to_dict(); no pairings means empty. |

<a id="api-PlanFragment-to_dict"></a>
### `PlanFragment.to_dict`

Serialize typed definitions to copies using the current configuration format; omit an empty sequences key.

```python
PlanFragment.to_dict()
```

No explicit parameters; reads the immutable generated declarations. Returns a dict that can be merged into input for AnalysisPlan.from_dict. It contains no invented sources or execution results. No proactively raised exceptions are documented; build_preset constructs these instances.

## Source locations

- [`src/chronaxis/planning/preset_models.py:154`](../../../../src/chronaxis/planning/preset_models.py#L154) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
- [`src/chronaxis/planning/preset_models.py:167`](../../../../src/chronaxis/planning/preset_models.py#L167) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
