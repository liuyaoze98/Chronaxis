# chronaxis.convert_time

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-convert_time"></a>
## `convert_time`

Convert a value with an explicit unit to nanoseconds, rounding the final result to nearest, ties to even.

```python
convert_time(value: int | float | str | Decimal, unit: str) -> TimeConversion
```

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `value` | int &#124; float &#124; str &#124; Decimal | Required | Positional or keyword. Finite integer, decimal text, Decimal, or existing float. Negative time coordinates are allowed. |
| `unit` | str | Required | Positional or keyword. Case-sensitive `s`, `ms`, `us`, or `ns`; no default unit. |

Returns [TimeConversion](TimeConversion.md#api-TimeConversion) containing integer nanoseconds, input representation/unit, and separate diagnostics for nanosecond rounding and pre-existing floating-point precision limits.

Raises `TypeError` or `ValueError` for an invalid type, text syntax, significant-digit length, or unit. Raises `TimeOverflowError` when the rounded result exceeds int64.

The conversion separates sign, coefficient, and exponent, scales or divides in integer arithmetic, and rounds to integer nanoseconds. It rejects very large positive exponents early and identifies very large negative exponents as rounding to zero, avoiding unbounded allocation.

No side effects: inputs, Decimal context, and time basis are unchanged.

## Source locations

- [`src/chronaxis/timebase/conversion.py:143`](../../../../src/chronaxis/timebase/conversion.py#L143) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
