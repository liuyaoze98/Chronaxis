# chronaxis.extensions.ExtensionRegistry

`from chronaxis.extensions import ExtensionRegistry`

<a id="api-ExtensionRegistry"></a>
## `ExtensionRegistry`

Construct an immutable host-extension registry. Pass the same instance when building and running the plan. Configuration references registered names; it does not import Python modules.

```python
ExtensionRegistry(functions=(), reductions=(), transforms=())
```

| Name | Type | Required | Default | Purpose |
|---|---|---|---|---|
|`functions`|tuple[FunctionSpec, ...]|No|()|Tuple of FunctionSpec declarations; empty means no custom pointwise functions.|
|`reductions`|tuple[ReductionSpec, ...]|No|()|Tuple of ReductionSpec declarations; empty means no custom sample reductions.|
|`transforms`|tuple[TransformSpec, ...]|No|()|Tuple of TransformSpec declarations; empty means no custom temporal transforms.|

### Returns

New ExtensionRegistry. Its functions/reductions/transforms are read-only name mappings; identity is a digest of declarations and implementation versions.

### Raises

TypeError for non-tuple containers or incorrectly typed entries; ValueError for duplicate names across categories.

### Execution and resources

Registers declarations without executing callbacks or creating runtime state. Do not replace the registry within a run.

[Worked host example](../host-extensions.md)

Source: [`src/chronaxis/extensions.py:147`](../../../../src/chronaxis/extensions.py#L147) (line number in the Chronaxis 0.1.0.dev6 source).

Source: [`src/chronaxis/extensions.py:154`](../../../../src/chronaxis/extensions.py#L154) (line number in the Chronaxis 0.1.0.dev6 source).
