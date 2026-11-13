# chronaxis.TimeConversion

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-TimeConversion"></a>
## `TimeConversion`

Store a normalized time and source-precision diagnostics without mutable conversion state leaking across tasks. Entry points validate `time_ns` as int64. Quantization and pre-existing float limits are recorded separately. `input_text` preserves only the representation seen by conversion, not proof of upstream precision; `source_timezone` records the chosen timezone, not proof of source synchronization.

```python
TimeConversion(time_ns: int, input_representation: str, input_unit: str, input_text: str, quantized: bool, precision_limited: bool = False, rounding: str = 'round_half_even', source_timezone: str | None = None) -> None
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`time_ns`|int|Yes|No default|Core coordinate or duration in signed 64-bit nanoseconds.|
|`input_representation`|str|Yes|No default|Actual representation, such as integer/decimal_text/decimal/binary_float/ISO8601.|
|`input_unit`|str|Yes|No default|Explicit s/ms/us/ns; datetime entry uses ISO8601.|
|`input_text`|str|Yes|No default|Text seen at this entry point; does not store a user log or assume greater source precision.|
|`quantized`|bool|Yes|No default|True if the exact representation needed nanosecond rounding, including rounding to zero.|
|`precision_limited`|bool|No|False|True for an existing binary float because pre-float precision cannot be recovered. Even 1.0 has True when quantized is False. Integers, decimal text, and Decimal use False; this says nothing about synchronization.|
|`rounding`|str|No|'round_half_even'|Final nanosecond rounding is fixed to nearest, ties to even.|
|`source_timezone`|str &#124; None|No|None|Description of the tzinfo actually used for a datetime; not inferred for numeric time.|

## Source locations

- [`src/chronaxis/timebase/conversion.py:47`](../../../../src/chronaxis/timebase/conversion.py#L47) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
