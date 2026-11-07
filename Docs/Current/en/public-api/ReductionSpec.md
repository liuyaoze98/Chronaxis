# chronaxis.extensions.ReductionSpec

`from chronaxis.extensions import ReductionSpec`

<a id="api-ReductionSpec"></a>
## `ReductionSpec`

Declare a sample-reduction factory, factory(resources). Each statistical scope gets its own state.

```python
ReductionSpec(name: str, version: str, input: chronaxis.extensions.ValueSpec, output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None, state_bytes: int = 0, mergeable: bool = False) -> None
```

| Name | Type | Required | Default | Purpose |
|---|---|---|---|---|
|`name`|str|Yes|No default|Expression identifier, unique in the registry and distinct from built-in operations.|
|`version`|str|Yes|No default|Nonempty implementation version; the host must change it when implementation behavior changes.|
|`input`|chronaxis.extensions.ValueSpec|Yes|No default|One ValueSpec numeric port with a registered unit; BOOL and ENUM are not accepted.|
|`output`|chronaxis.extensions.ValueSpec|Yes|No default|Output ValueSpec port declaring the callback result dtype and unit.|
|`reference`|object|No|None|State factory `factory(resources)`, creating one object per reduction scope. It must provide consume(values), finalize(), cancel() and close(); values is a tuple of valid ScalarValue objects and finalize returns a ScalarValue matching output. mergeable=True also requires merge(other). None disables reference; provide at least one backend.|
|`numpy`|object|No|None|State factory `factory(resources)`, with the same required methods as reference. consume(values) receives a valid NumericArray; finalize() still returns ScalarValue. None disables numpy; no reference factory fallback is used.|
|`state_bytes`|int|No|0|Nonnegative integer state reservation in bytes, declared by the host for actual state needs.|
|`mergeable`|bool|No|False|True requires state.merge(other); False makes no mergeability promise.|

### Returns

Immutable ReductionSpec declaration.

### Raises

ValueError/TypeError for invalid ports, backends, state_bytes, or mergeable. Both input and output must be numeric.

### Execution and resources

State.consume receives selected real samples and finalize returns ScalarValue. Both cancel and close are required, for cancellation and resource release respectively. mergeable=True requires merge(other).

Declare ports with `from chronaxis.extensions import ValueSpec` and `from chronaxis.core.types import SignalDType`. For example, `ValueSpec(SignalDType.FLOAT64, "A")` declares a numeric current port.

### `require_backend`

```python
ReductionSpec.require_backend(backend)
```

Inherited method: backend is required and must be reference or numpy. Returns that registered callback/factory; raises ValueError for an unknown or unsupported backend.

[Worked host example](../host-extensions.md)

Source: [`src/chronaxis/extensions.py:92`](../../../../src/chronaxis/extensions.py#L92) (line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`).
