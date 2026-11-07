# chronaxis.extensions.TransformSpec

`from chronaxis.extensions import TransformSpec`

<a id="api-TransformSpec"></a>
## `TransformSpec`

Declare a stateful grid-transform factory, factory(resources). advance(time_ns, window_ns, values, weights_ns) calculates each window value.

```python
TransformSpec(name: str, version: str, input: chronaxis.extensions.ValueSpec, output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None, state_bytes: int = 0, history_ns: int = 0, interval_modes: tuple[str, ...] = ('actual', 'fixed', 'dbc')) -> None
```

| Name | Type | Required | Default | Purpose |
|---|---|---|---|---|
|`name`|str|Yes|No default|Expression identifier, unique in the registry and distinct from built-in operations.|
|`version`|str|Yes|No default|Nonempty implementation version; the host must change it when implementation behavior changes.|
|`input`|chronaxis.extensions.ValueSpec|Yes|No default|One ValueSpec numeric port with a registered unit; BOOL and ENUM are not accepted.|
|`output`|chronaxis.extensions.ValueSpec|Yes|No default|Output ValueSpec port declaring the callback result dtype and unit.|
|`reference`|object|No|None|State factory `factory(resources)`, creating one object per session with required advance(time_ns, window_ns, values, weights_ns), cancel() and close(). advance receives the actual output time, measured window width, valid ScalarValue tuple and corresponding duration weights, returning a ScalarValue matching output. Time values use ns. None disables reference; provide at least one backend.|
|`numpy`|object|No|None|State factory `factory(resources)`, with the same required methods as reference. advance receives a valid NumericArray as values and a matching duration array as weights_ns, and returns ScalarValue. None disables numpy; no reference factory fallback is used.|
|`state_bytes`|int|No|0|Nonnegative integer state reservation in bytes, declared by the host for actual state needs.|
|`history_ns`|int|No|0|Explicit positive int64 lookback width in ns, measured using the selected actual or periodic interval mode. The default 0 is not a valid declaration.|
|`interval_modes`|tuple[str, ...]|No|('actual', 'fixed', 'dbc')|Nonempty unique tuple drawn from actual/fixed/dbc. Declare only the weighting modes implemented correctly.|

### Returns

Immutable TransformSpec declaration.

### Raises

ValueError/TypeError for invalid ports, resources, history width, or duplicate/unknown interval_modes. Both ports must be numeric.

### Execution and resources

Creates state per session. advance receives valid zero-order-hold spans and weights and returns a ScalarValue at the grid time. History and state use the shared budget; close releases resources.

Declare ports with `from chronaxis.extensions import ValueSpec` and `from chronaxis.core.types import SignalDType`. For example, `ValueSpec(SignalDType.FLOAT64, "A")` declares a numeric current port.

### `require_backend`

```python
TransformSpec.require_backend(backend)
```

Inherited method: backend is required and must be reference or numpy. Returns that registered callback/factory; raises ValueError for an unknown or unsupported backend.

[Worked host example](../host-extensions.md)

Source: [`src/chronaxis/extensions.py:117`](../../../../src/chronaxis/extensions.py#L117) (line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`).
