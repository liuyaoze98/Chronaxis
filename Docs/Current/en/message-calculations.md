<a id="逐消息累计"></a>
# Per-message accumulation

Root-level `message_calculations` evaluates an expression once per target CAN message and adds the contributions. It uses values in the current message and suits tasks with an explicitly known contribution period. Ordinary signal-time integration uses `calculations`; its timing basis is different.

<a id="完整最小例与方向分组扩展"></a>
## Complete examples and direction groups

[message-minimal.yaml](../examples/message-minimal.yaml) uses [message-clean.asc](../examples/data/message-clean.asc) and [power.dbc](../examples/data/power.dbc). Two messages at 0 s each have ID 0x100 and power 4000 W. With 0.1 s per message, each contributes 400 J, totaling 800 J. Simultaneous messages count separately; they are not deduplicated as signal updates. The record at 1 s falls outside [0,1) and is excluded.

[message-directions.yaml](../examples/message-directions.yaml) uses [direction input](../examples/data/message-direction.asc) and [direction DBC](../examples/data/message-direction.dbc). It binds Power to `power` and Direction to `direction`, then declares separate positive and negative calculations. Direction values at 0, 1, 2 s are 1, -1, 0 and each power is 4000 W. The first two contribute 400 J to their respective groups; zero enters neither group. This example enables contribution details for inspecting skip reasons by calculation ID.

Run either complete file using `chronaxis run filename.yaml --output new-result`. Formula parameters and direction signals are defined in that file. The BLF example below additionally contains a missing-value message; that record is not part of the minimal ASC input.

The examples declare signal `period: 100ms` because the public runner initializes validity for used signals. If the DBC supplies no period, give period or valid_for explicitly. This signal period is not multiplied into the contribution again: the formula's separate `parameters.period` controls each contribution, and the fields are not automatically linked.

<a id="消息能量4000w01秒2次800j"></a>
<a id="消息能量-4000w-0-1秒-2次-800j"></a>
## Message energy: 4000 W × 0.1 s × 2 = 800 J

Use [message-energy.yaml](../examples/message-energy.yaml), which defines power and has one CAN source, selected automatically. Replace its root `message_calculations` list with this block; do not nest the parent key inside a list item.

```yaml
message_calculations:     # Evaluate and accumulate each target message
  - name: energy          # Calculation name in results
    update_message:       # Message that triggers one evaluation
      frame_id: 0x100     # ID from the DBC
    parameters:           # Constants referenced by the formula
      period:             # Duration represented by one message
        value: 0.1        # Period from protocol or business rules
        unit: s           # Seconds
    expr: power * period  # Contribution from this message
    unit: J               # Contribution and total unit
```

Two simultaneous 4000 W messages contribute 400 J each; a third missing-value message is skipped as `missing_input`. Non-target IDs are not attempts. The total is 800 J from 3 attempts, 2 contributions and 1 skip. This period is explicit and fixed; it is neither inferred from nor multiplied by actual inter-message time.

<a id="message_calculations每一项的全部字段"></a>
## All calculation fields

The main table describes `message_calculations[]`. Nested tables describe `update_message`, `parameters.<parameter_name>` and `split_by_sign` inside each item. A parameter name such as period is used in the formula; do not place value directly under parameters.

| Field | Type | Required/default | Meaning |
|---|---|---|---|
| name | String | Required | Unique calculation name such as energy; must not duplicate another generated node. |
| source | String | Required when multiple sources qualify; otherwise the unique raw-message source | Existing asc_or_blf, can_blf, can_asc or raw_can_csv source name. All referenced target signals must belong to this source and message. |
| profile | String | Inferred from source | Normally omit. can_blf uses `sclicer-functions-v1`, consistent with its implementation; asc_or_blf, can_asc and raw_can_csv use `can-text-v1`. |
| operation | String | Default `legacy_sum` | Only `legacy_sum` is supported: add successful evaluations. |
| message_policy | String | Default `current_message-v1` | Only current-message values are used. Do not add cache_policy to enable historical caching. |
| update_message | Object | Required | Message identity triggering evaluation; fields below. |
| expr | Expression string | Required | Contribution per target message, e.g. `power * period`. Uses this message's signals and this calculation's parameters, not ordinary derived signals or values from another message. See [Expressions](expressions.md). |
| unit | String | Required | Physical unit of each contribution and the total, such as J. It does not add another time integration. |
| parameters | Object | Default `{}` | Named constants, each with value and unit; names are referenced by the expression. |
| split_by_sign | Object | Default no direction filter | Accumulate only a selected positive/negative direction group. Declare two differently named calculations to get both groups. |

Only frame_id is required in `update_message`. Channel inherits the source; frame flags are inferred unless matching is ambiguous.

| Field | Type | Meaning |
|---|---|---|
| channel | Integer | User channel numbered from 1, matching the selected source. Channel 1 maps internally automatically; do not subtract one. |
| frame_id | Integer or string | Required DBC message ID. Prefix 0x means hexadecimal, 0b binary, otherwise decimal. Use strings for prefixed IDs in JSON. Ranges match [CAN bindings](inputs.md#can-field). |
| is_extended | Optional bool | false for standard, true for extended IDs; omission infers the frame type. Equal numeric IDs with different frame types remain distinct. Explicit null is invalid. |
| is_fd | Optional bool | false for classic CAN, true for CAN FD; omission infers from actual frames. Explicit null is invalid. |

Each `parameters.<name>` requires both fields, without defaults:

| Field | Type | Meaning |
|---|---|---|
| value | Number | Finite float64-compatible constant, such as 0.1 for a period; not bool, string, NaN or Infinity. Obtain it from protocol or business requirements. |
| unit | String | Actual unit, e.g. s for period or `1` for a dimensionless factor; not a descriptive comment. |

`split_by_sign` requires signal and bucket; value_policy defaults to raw_decoded-v1:

| Field | Type | Meaning |
|---|---|---|
| signal | String | Numeric or bool direction signal alias from the same message. It need not appear in expr. |
| bucket | String | `positive` selects raw direction >0; `negative` selects <0. Zero enters neither. Bool true is positive and false is zero. |
| value_policy | String | Only `raw_decoded-v1`: use the freshly decoded direction before scale, offset or direction conversion, without retaining a previous value. |

The direction signal selects the group; the expression determines the amount. A positive direction with a -10 J expression adds -10 J to the positive group, without absolute-value conversion. Zero enters neither group. Each group's final value is retained to six decimal places. No participating messages is different from valid +10 J and -10 J contributions summing to zero. See the [complete message example](examples.md#message-energy).

<a id="汇总与贡献明细"></a>
## Totals and contribution details

Use `outputs.contributions: none` when only totals are needed. Public calculation results retain value, unit, status, reason, quality and calculation identity, without attempt/skip counts or per-reason counts. Choose full and read contributions when individual contributions and skips are needed. Diagnostics separately controls detailed input/configuration information.

Omitting [dataset.domain](dataset.md) accumulates all files from the referenced CAN source. Default `reader.input_check: auto` does not create a time range solely for this time-independent task. An explicit domain filters messages to that range.

`full` records each attempt; `none` avoids unnecessary details. Performance still depends on the actual input and calculation combination.
