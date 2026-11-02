<a id="表达式与派生信号"></a>
# Expressions

Expressions combine previously defined signals, for example `voltage * current` for power or `current > 5` for a condition. Define the input signals first; with DBC inputs, the program can infer their types and units. Write formulas in fields such as `derived.<name>.expr`, `calculations[].expr`, and `rules[].condition`.

The language resembles a restricted subset of Python. A numeric expression produces values; a condition produces true, false, or unknown. An enum mapping such as `7: running` lets you write `mode == "running"`; the numeric code is not interchangeable with the text label in an enum comparison.

<a id="完整最小例与扩展例"></a>
## Complete minimal and extended examples

[expression-minimal.yaml](../examples/expression-minimal.yaml) defines 400 V and 10 A over 0–4 s and returns a maximum derived power of 4000 W. [expression-extended.yaml](../examples/expression-extended.yaml) adds `current > 5 and voltage > 300`, requiring 2 s of continuous agreement. It confirms at 2 s and, with the default onset-based range, integrates the full 0–4 s interval to 16000 J.

<a id="先准备来源和信号"></a>
## Prepare sources and signals

The shared [electrical-base.yaml](../examples/electrical-base.yaml) reads synthetic ASC data through a DBC and analyzes its observed range. The following signal definitions illustrate the names used on this page. They are already in the base configuration: do not append a second `signals` section. The 20 s validity is chosen for these sparse teaching records, not as a production recommendation.

```yaml
signals:                   # Names available to expressions.
  - name: temperature      # Analysis name for the DBC temperature signal.
    field:                 # Locate the original signal.
      frame_id: '0x11d'    # CAN message identifier.
      signal: Temperature  # Signal name in the DBC.
    valid_for: 20s         # Validity for the sparse synthetic example.
  - name: voltage          # Voltage alias.
    field:                 # Original CAN signal.
      frame_id: '0x11f'    # CAN message identifier.
      signal: Voltage      # Signal name in the DBC.
    valid_for: 20s         # Validity for this example.
  - name: current          # Current alias.
    field:                 # Original CAN signal.
      frame_id: '0x114'    # CAN message identifier.
      signal: Current      # Signal name in the DBC.
    valid_for: 20s         # Validity for this example.
  - name: mode             # State alias.
    field:                 # Original CAN signal.
      frame_id: '0x118'    # CAN message identifier.
      signal: Mode         # Signal name in the DBC.
    valid_for: 20s         # Validity for this example.
  - name: request          # Boolean request alias.
    field:                 # Original CAN signal.
      frame_id: '0x11a'    # CAN message identifier.
      signal: Request      # Signal name in the DBC.
    choices:               # Explicit code-to-boolean mapping.
      - [0, false]         # Inactive.
      - [1, true]          # Active.
    valid_for: 20s         # Validity for this example.
  - name: response         # Boolean response alias.
    field:                 # Original CAN signal.
      frame_id: '0x11b'    # CAN message identifier.
      signal: Response     # Signal name in the DBC.
    choices:               # Explicit code-to-boolean mapping.
      - [0, false]         # Inactive.
      - [1, true]          # Active.
    valid_for: 20s         # Validity for this example.
```

<a id="配置片段-功率-工作事件与能量"></a>
## Configuration fragment: power, activity, and energy

For that base file, replace the root-level `derived`, `rules`, and `calculations` sections with this fragment. Do not nest them under `signals` or append duplicate root keys.

```yaml
derived:                                      # Reusable calculated signals, keyed by name.
  power:                                      # Name used by later expressions.
    expr: voltage * current                   # V multiplied by A produces W.
rules:                                        # Event detection rules.
  - name: working                             # Rule name.
    condition: current > 5 and voltage > 300  # Both conditions must be true.
    minimum_duration: 2s                      # Require two continuous seconds.
    rule_type: condition_duration             # Detect sustained conditions.
calculations:                                 # Requested results.
  - name: energy                              # Calculation name.
    expr: power                               # Reuse the derived signal.
    operation: integral                       # Integrate W over time to obtain J.
    scope:                                    # Restrict the calculation range.
      rule: working                           # Calculate over this rule's activity.
```

If a formula is used only once, write it directly in that calculation's `expr`. A named derived signal is useful when several rules or calculations reuse it.

<a id="derived的全部字段"></a>
<a id="派生信号字段"></a>
## Derived signal fields

`derived` is a mapping from a name to an object, not a list. For example, the full expression path is `derived.power.expr`; `power` is the chosen name. Do not add a second `name` inside that object. Derived and original signal names share a namespace; duplicate names and cyclic dependencies are invalid. Omission or `{}` means no derived signals; `null` is invalid.

| Field under `derived.<name>` | Required | Omission / constraints | Purpose |
|---|---|---|---|
| `expr` | Yes | Nonempty expression; all references must exist and dependencies must be acyclic | Formula used to calculate the derived signal. |
| `unit` | No | Inferred where possible, such as V × A → W; an explicit unit must be nonempty and compatible | Declares the result unit. It does not perform another conversion. |
| `semantic_id` | No | Nonempty string when supplied | Optional meaning label, such as `battery.power`. Expressions still use the signal name. Derived signals are currently not preset role candidates. |
| `semantic_contract_version` | No | Nonempty string, such as `"1"`; `null` is invalid | Project-defined semantic version. It is not `config_version` and does not select a preset. |
| `sign_convention` | No | Nonempty string when supplied | Describes the sign, such as `positive_is_charge`; it does not negate the values. |
| `measurement_location` | No | Nonempty string when supplied | Describes where the value was measured, such as `pack_terminal`; it does not alter the measurement. |
| `metadata` | No | Defaults to `{}` | Custom descriptive data, such as `{formula_revision: "1"}`. This is not a container for calculation options. |

Derived signals have no independent `dtype` or `valid_for`: their types and validity follow their inputs. Undefined names, cycles, incompatible types, and incompatible units fail configuration validation. Runtime failures such as division by zero make the affected value invalid and record a reason.

<a id="字面量信号名与括号"></a>
<a id="数字-名字和括号"></a>
## Literals, names, and parentheses

| Syntax | Meaning and restrictions |
|---|---|
| `5`, `-2`, `0x1` | Integer literals. Values used in arithmetic must fit the applicable int64 or uint64 range. |
| `0.5`, `1e3` | Finite floating-point literals; `1e309` is invalid. |
| `True`, `False` | Boolean literals, with this capitalization. |
| `"charge"`, `'charge'` | Declared enum labels, used in equality or inequality comparisons. They are not general string operands. |
| `voltage`, `current` | Case-sensitive names of defined signals. |
| `(voltage * current)` | Grouping; parentheses do not convert the type. |

In YAML, `condition: mode == "charge"` is a string containing an expression. The quotes around `charge` belong to that expression. YAML quoting the entire field is a separate layer.

Analysis aliases start with an ASCII letter or underscore, followed by ASCII letters, digits, or underscores. Chinese characters, dots, and spaces are not allowed in these aliases. Python keywords and reserved function names such as `abs` and `isclose` cannot be aliases. Original CSV headers and DBC signal names can contain other characters: bind them to a legal analysis alias.

<a id="算术运算"></a>
<a id="数值运算"></a>
## Arithmetic

For dimensionless `x = 6.0` and `y = 2`, these are the supported operators:

| Expression | Result |
|---|---|
| `x + y` | 8 |
| `x - y` | 4 |
| `x * y` | 12 |
| `x / y` | 3 |
| `+x` | 6 |
| `-x` | -6 |

Arithmetic requires numeric operands; boolean and enum signals are not numeric operands. Integer division also returns `float64`. Division by zero and numeric overflow produce invalid results, not ordinary zero values.

<a id="比较运算"></a>
## Comparisons

Numeric values support `==`, `!=`, `<`, `<=`, `>`, and `>=`. Boolean and enum operands support only `==` and `!=`; enum comparisons must use the same enum domain. Chained comparisons such as `0 <= x < 10` combine the comparisons with `and`. A single `=` is invalid, as is an undeclared enum label.

<a id="布尔组合与未知状态"></a>
<a id="逻辑-and-or-not"></a>
## Boolean combinations and unknown values

Use `and`, `or`, and `not` on boolean conditions. Numeric values are not implicitly treated as booleans. Operators `&`, `|`, `~`, `&&`, `||`, and `!` are not substitutes.

| A | B | `A and B` | `A or B` |
|---|---|---|---|
| True | True | True | True |
| True | False | False | True |
| True | Unknown | Unknown | True |
| False | False | False | False |
| False | Unknown | False | Unknown |
| Unknown | Unknown | Unknown | Unknown |

`not Unknown` remains unknown. Quality and error information is still recorded: a decisive boolean result does not hide undefined names or turn an invalid numeric value into zero.

<a id="支持的函数"></a>
<a id="内置函数"></a>
## Supported functions

<a id="abs-x-取绝对值"></a>
### `abs(x)`: absolute value

`abs(x)` takes exactly one positional numeric argument. It does not accept keywords such as `abs(x=current)`. Taking the absolute value of the minimum int64 value overflows and is invalid.

<a id="isclose-a-b-atol-rtol-允许误差的比较"></a>
### `isclose(a, b, atol=..., rtol=...)`: tolerance comparison

`isclose(a, b, atol=..., rtol=...)` takes exactly two positional arguments and requires both tolerance keywords. Tolerances must be finite, nonnegative numeric literals; they cannot be signals or expressions such as `1/10`.

For example, `isclose(voltage, 400, atol=0.1, rtol=0)` allows an absolute difference of 0.1 V. The operands must have compatible units, `atol` uses their unit, and `rtol` is dimensionless. The test is:

```text
abs(a - b) <= atol + rtol * abs(b)
```

With `a=102`, `b=100`, `atol=0`, and `rtol=0.02`, it returns true. The relative term uses `b`, so the operation is not necessarily symmetric. An invalid operand makes the condition unknown.

<a id="运算优先级"></a>
<a id="运算先后顺序"></a>
## Operator precedence

From highest to lowest: parentheses and function calls; unary `+`/`-`; `*`/`/`; `+`/`-`; comparisons; `not`; `and`; `or`. Arithmetic operators at the same precedence evaluate left to right. For `x=6` and `y=2`, `x + y * 2` is 10, while `(x + y) * 2` is 16. Use parentheses whenever grouping would otherwise be hard to read.

<a id="单位规则"></a>
<a id="单位怎么参与计算"></a>
## Units

A literal in `current > 5` uses the current signal's unit, for example 5 A. Likewise, `voltage + 1` adds 1 V. Multiplication or division by a bare scalar, such as `current * 2` or `current / 2`, retains A.

Supported unit combinations include V × A → W, W × s → J, A × s → A·s, their commutative multiplication forms, and V / V → dimensionless. Addition and comparisons require matching unit labels; A and mA are not automatically converted. Convert an input first using its `conversion.input_unit`, `conversion.scale`, and target `unit`. Unit algebra supports documented combinations, not arbitrary dimensional derivation such as automatically producing ohms from V/A.

For a custom unknown unit combination, you may explicitly label the derived result, but the unit relationship remains `unverified`: the program has not verified that physical relationship. A label does not prove compatibility.

<a id="类型与整数精度"></a>
<a id="类型-整数精度和错误发生在哪里"></a>
## Types and integer precision

Arithmetic between signals requires compatible types. A `float64` signal and an `int64` signal cannot simply be multiplied; make their input types consistent first. There are no `float()` or `int()` expression functions. A numeric literal, such as integer `2` multiplied by a `float64` signal, is handled as a literal and is allowed.

Comparisons between `int64` and `uint64` signals use exact integer comparisons. Comparing a `float64` signal with an integer signal requires consistent input types. A comparison literal can lie outside the signal's range: for example, `9223372036854775808` is greater than every int64 value. An integer literal used in arithmetic must fit the required numeric range.

<a id="配置错误与运行时无效值"></a>
## Configuration errors and runtime invalid values

Undefined names, incompatible units, and unsupported functions are configuration errors. Missing input values, runtime division by zero, and overflow invalidate the affected value and retain the reason. See [concepts](concepts.md) and [execution](execution.md) for quality, missing data, and result handling.

<a id="不支持的语法及替代方式"></a>
<a id="不支持的写法及替代办法"></a>
## Unsupported syntax and alternatives

| Unsupported syntax | Alternative or explanation |
|---|---|
| `**`, `%`, `//`, `@` | Use a supported formula, such as `x * x` when its type and unit are valid, or preprocess the data. |
| `&`, `\|`, `^`, `~`, `<<`, `>>` | Decode a flag into a separate signal first. |
| `in`, `not in`, `is None`, `is not None` | Combine explicit enum comparisons with `or`; use the quality rules for missing data. |
| Attributes, indexing, slicing, such as `battery.current`, `x[0]`, or `x[1:3]` | Bind original values to simple signal aliases. Expressions do not expose arrays or arbitrary history indexing. |
| `min`, `round`, `sqrt`, `float`, `x.mean()` and other calls | Only `abs` and `isclose` are supported. Preprocess unsupported operations or use a calculation operation. |
| `*items`, `**options` argument expansion | Use the fixed signatures above. |
| Containers, comprehensions, `x if flag else y` | Preprocess or express the analysis through separate rules. |
| Assignment, `lambda`, `import` | Expressions are not executable Python programs. |
| `None`, complex numbers, bytes, string operations | Strings are allowed only as declared enum labels in comparisons. |

The runnable [expression checks](../examples/readability_examples.py) verify actual results on both calculation backends. They demonstrate the supported expression language, not general Python execution.
