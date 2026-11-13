# chronaxis.extensions.FunctionSpec

`from chronaxis.extensions import FunctionSpec`

<a id="api-FunctionSpec"></a>
## `FunctionSpec`

Declare a stateless pointwise function. impl(args, resources) returns ScalarValue or NumericArray with the matching shape.

```python
FunctionSpec(name: str, version: str, inputs: tuple[chronaxis.extensions.ValueSpec, ...], output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None) -> None
```

| Name | Type | Required | Default | Purpose |
|---|---|---|---|---|
|`name`|str|Yes|No default|Expression identifier, unique in the registry and distinct from built-in operations.|
|`version`|str|Yes|No default|Nonempty implementation version; the host must change it when implementation behavior changes.|
|`inputs`|tuple[chronaxis.extensions.ValueSpec, ...]|Yes|No default|Nonempty tuple of ValueSpec ports in positional argument order. BOOL uses unit 1; extract enum codes before calling.|
|`output`|chronaxis.extensions.ValueSpec|Yes|No default|Output ValueSpec port declaring the callback result dtype and unit.|
|`reference`|object|No|None|Point implementation `impl(args, resources)`. args is a tuple of ScalarValue objects in inputs order; return one ScalarValue matching output. resources reserves/releases temporary memory. None disables this backend; provide at least one backend, with no automatic fallback.|
|`numpy`|object|No|None|Array point implementation `impl(args, resources)`. args is a tuple of NumericArray objects in inputs order; return a NumericArray of matching length and output type. Only rows with all required inputs valid are passed. None disables numpy; reference is not substituted.|

### Returns

Immutable FunctionSpec declaration.

### Raises

Invalid names, ports, versions, or implementations reject construction with ValueError or TypeError and a specific reason.

### Execution and resources

Invalid required inputs propagate invalidity; an unselected where branch is not executed. Registration checks declarations without calling the implementation.

Declare ports with `from chronaxis.extensions import ValueSpec` and `from chronaxis.core.types import SignalDType`. For example, `ValueSpec(SignalDType.FLOAT64, "A")` declares a numeric current port.

### `require_backend`

```python
FunctionSpec.require_backend(backend)
```

Inherited method: backend is required and must be reference or numpy. Returns that registered callback/factory; raises ValueError for an unknown or unsupported backend.

[Worked host example](../host-extensions.md)

Source: [`src/chronaxis/extensions.py:73`](../../../../src/chronaxis/extensions.py#L73) (line at `8904c2f744951857659abd40aaa3535d57faf53c`).
