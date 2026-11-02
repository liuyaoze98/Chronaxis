# chronaxis.TimeConversion

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-TimeConversion"></a>
## `TimeConversion`

Store a normalized time and source-precision diagnostics without mutable conversion state leaking across tasks. Entry points validate `time_ns` as int64. Quantization and pre-existing float limits are recorded separately. `input_text` preserves only the representation seen by conversion, not proof of upstream precision; `source_timezone` records the chosen timezone, not proof of source synchronization.

```python
TimeConversion(time_ns: int, input_representation: str, input_unit: str, input_text: str, quantized: bool, precision_limited: bool = False, rounding: str = 'round_half_even', source_timezone: str | None = None) -> None
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| `time_ns` | int | Required | Core coordinate or duration in signed 64-bit nanoseconds. |
| `input_representation` | str | Required | Actual representation, such as integer/decimal_text/decimal/binary_float/ISO8601. |
| `input_unit` | str | Required | Explicit s/ms/us/ns; datetime entry uses ISO8601. |
| `input_text` | str | Required | Text seen at this entry point; does not store a user log or assume greater source precision. |
| `quantized` | bool | Required | True if the exact representation needed nanosecond rounding, including rounding to zero. |
| `precision_limited` | bool | Optional; False | True for an existing binary float because pre-float precision cannot be recovered. Even 1.0 has True when quantized is False. Integers, decimal text, and Decimal use False; this says nothing about synchronization. |
| `rounding` | str | Optional; `'round_half_even'` | Final nanosecond rounding is fixed to nearest, ties to even. |
| `source_timezone` | str &#124; None | Optional; None | Description of the tzinfo actually used for a datetime; not inferred for numeric time. |

## Source locations

- [`src/chronaxis/timebase/conversion.py:47`](../../../../src/chronaxis/timebase/conversion.py#L47) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
