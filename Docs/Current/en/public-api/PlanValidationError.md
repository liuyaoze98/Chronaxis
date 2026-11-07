# chronaxis.PlanValidationError

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.planning.checks.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

## Members

- [`PlanValidationError`](#api-PlanValidationError)
- [`__init__`](#api-PlanValidationError-__init__)
- [`refresh_text`](#api-PlanValidationError-refresh_text)
- [`to_dict`](#api-PlanValidationError-to_dict)
- [`diagnostics`](#api-PlanValidationError-diagnostics)
- [`from_diagnostics`](#api-PlanValidationError-from_diagnostics)

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

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`path`|str|Yes|No default|Positional or keyword. Actual failing field path, such as `$.signals[0].unit`.|
|`message`|str|Yes|No default|Positional or keyword. Human-readable violated requirement, such as a positive integer being required. Do not include complete private input data.|
|`code`|str|No|'invalid_config'|Positional or keyword. Machine-readable category. Classify errors by code rather than matching Chinese message text.|
|`hint`|str or None|No|None|Keyword-only correction hint, such as valid options/names. Does not modify configuration.|
|`source`|str or None|No|None|Keyword-only source file or display name, separate from field path. None when unknown.|
|`location`|ConfigurationLocation or None|No|None|Keyword-only proven original line/column. If unavailable, report only file and field rather than guessing.|
|`object_name`|str or None|No|None|Keyword-only source, signal, or node name for locating the error, not inferring names.|
|`value`|str or None|No|None|Keyword-only shortened value description. Large containers show only type/size, not the entire configuration.|

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

For an aggregate error, `to_dict()` describes its first item. Use `[item.to_dict() for item in error.diagnostics]` to obtain every reported error. `blocked_checks` is a tuple of dictionaries with `path` and `reason`; these checks could not run because required declarations were invalid. They are not additional confirmed errors.

<a id="api-PlanValidationError-diagnostics"></a>
### `PlanValidationError.diagnostics`

```python
PlanValidationError.diagnostics
```

Read this property without parentheses. Returns a tuple of individual `PlanValidationError` objects; a single error also returns a one-item tuple. No parameters or documented exceptions.

<a id="api-PlanValidationError-from_diagnostics"></a>
### `PlanValidationError.from_diagnostics`

```python
PlanValidationError.from_diagnostics(errors, blocked=())
```

Construct an aggregate error from a nonempty sequence of individual errors and optional blocked-check dictionaries (`path` and `reason`). Returns a `PlanValidationError`; raises `ValueError` if `errors` is empty. A single error with no blocked checks is returned unchanged. Application code normally catches the exception produced by the plan loader instead of constructing it.


| Name | Type | Required | Default | Purpose |
|---|---|---|---|---|
|`errors`|Sequence[[PlanValidationError](PlanValidationError.md#api-PlanValidationError)]|Yes|No default|Nonempty sequence of individual configuration errors. A single error without blocked checks is returned unchanged.|
|`blocked`|Iterable[dict]|No|()|Sequence of blocked-check dictionaries with path and reason. An empty tuple means no blocked checks were recorded.|

## Source locations

- [`src/chronaxis/planning/checks.py:26`](../../../../src/chronaxis/planning/checks.py#L26) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
- [`src/chronaxis/planning/checks.py:32`](../../../../src/chronaxis/planning/checks.py#L32) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
- [`src/chronaxis/planning/checks.py:58`](../../../../src/chronaxis/planning/checks.py#L58) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
- [`src/chronaxis/planning/checks.py:78`](../../../../src/chronaxis/planning/checks.py#L78) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
- [`src/chronaxis/planning/checks.py:86`](../../../../src/chronaxis/planning/checks.py#L86) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
- [`src/chronaxis/planning/checks.py:91`](../../../../src/chronaxis/planning/checks.py#L91) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
