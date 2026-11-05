# chronaxis.parse_duration

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-parse_duration"></a>
## `parse_duration`

Parse a nonnegative duration with a unit, including explicit zero.

```python
parse_duration(text: str) -> TimeConversion
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`text`|str|Yes|No default|Positional or keyword. Complete value with suffix, for example `500ms`, `3s`, or `0ns`.|

Returns [TimeConversion](TimeConversion.md#api-TimeConversion) with a nanosecond duration and the original unit-bearing text.

Raises `TypeError` for non-text input; `ValueError` for missing units, invalid syntax, or a negative original value, even if it would round to zero; and `TimeOverflowError` for conversion/rounding outside int64.

## Source locations

- [`src/chronaxis/timebase/conversion.py:204`](../../../../src/chronaxis/timebase/conversion.py#L204) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
