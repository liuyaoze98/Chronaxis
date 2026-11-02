# chronaxis.PlanValidationError

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.planning.checks.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

## Members

- [PlanValidationError](#api-PlanValidationError)
- [__init__](#api-PlanValidationError-__init__)
- [refresh_text](#api-PlanValidationError-refresh_text)
- [to_dict](#api-PlanValidationError-to_dict)

<a id="api-PlanValidationError"></a>
## `PlanValidationError`

Store a configuration field path, reason, machine-readable code, and optional source location and correction hint. It does not suppress execution or data-read failures. `code` distinguishes invalid configuration from capabilities not yet connected to an executable path.

```python
PlanValidationError(path: str, message: str, code: str = 'invalid_config', *, hint=None, source=None, location=None, object_name=None, value=None)
```

Base class: `ValueError`.

<a id="api-PlanValidationError-__init__"></a>
### `PlanValidationError.__init__`

Construct a field-specific error, preserving the original exception chain for loader diagnostics.

```python
PlanValidationError.__init__(path: str, message: str, code: str='invalid_config', *, hint=None, source=None, location=None, object_name=None, value=None)
```

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `path` | str | Required | Positional or keyword. Actual failing field path, such as `$.signals[0].unit`. |
| `message` | str | Required | Positional or keyword. Human-readable violated requirement, such as a positive integer being required. Do not include complete private input data. |
| `code` | str | Optional; `'invalid_config'` | Positional or keyword. Machine-readable category. Classify errors by code rather than matching Chinese message text. |
| `hint` | str or None | Optional; None | Keyword-only correction hint, such as valid options/names. Does not modify configuration. |
| `source` | str or None | Optional; None | Keyword-only source file or display name, separate from field path. None when unknown. |
| `location` | ConfigurationLocation or None | Optional; None | Keyword-only proven original line/column. If unavailable, report only file and field rather than guessing. |
| `object_name` | str or None | Optional; None | Keyword-only source, signal, or node name for locating the error, not inferring names. |
| `value` | str or None | Optional; None | Keyword-only shortened value description. Large containers show only type/size, not the entire configuration. |

Returns None; exception text contains path and reason. No documented exceptions: validators construct the arguments internally.

<a id="api-PlanValidationError-refresh_text"></a>
### `PlanValidationError.refresh_text`

Rebuild the human-readable message after attaching location information.

```python
PlanValidationError.refresh_text()
```

No explicit parameters. Returns None. No documented exceptions.

<a id="api-PlanValidationError-to_dict"></a>
### `PlanValidationError.to_dict`

Return stable machine-readable diagnostics as a native dict.

```python
PlanValidationError.to_dict()
```

No explicit parameters. No documented exceptions.

## Source locations

- [`src/chronaxis/planning/checks.py:26`](../../../../src/chronaxis/planning/checks.py#L26) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
- [`src/chronaxis/planning/checks.py:32`](../../../../src/chronaxis/planning/checks.py#L32) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
- [`src/chronaxis/planning/checks.py:56`](../../../../src/chronaxis/planning/checks.py#L56) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
- [`src/chronaxis/planning/checks.py:70`](../../../../src/chronaxis/planning/checks.py#L70) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
