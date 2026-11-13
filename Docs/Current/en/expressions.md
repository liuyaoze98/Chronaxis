<a id="表达式与派生信号"></a>
# Expressions

Expressions combine previously defined signals, for example `voltage * current` for power or `current > 5` for a condition. Define the input signals first; with DBC inputs, the program can infer their types and units. Write formulas in fields such as `derived.<name>.expr`, `calculations[].expr`, and `rules[].condition`.

The language resembles a restricted subset of Python. A numeric expression produces values; a condition produces true, false, or unknown. An enum mapping such as `7: running` lets you write `mode == "running"`; use a string to compare the label. To compare the retained integer code, use `enum_code(mode) == 7`; a numeric state signal can use `state == 7` directly. See [integer states and enum codes](#enum-code) for the code requirements.

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
    duration_comparison: ">="                 # Include the threshold; use > for strictly longer.
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
| `unit` | No | Inferred where possible, such as V × A → W; an explicit unit must be nonempty and compatible | Version 4 converts the value to a compatible target unit: 1500 W becomes 1.5 when kW is requested. |
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
| `5`, `-2`, `0x1`, `0b1` | Integer literals. Values used in arithmetic must fit the applicable int64 or uint64 range. |
| `0.5`, `1e3` | Finite floating-point literals; `1e309` is invalid. |
| `True`, `False` | Boolean literals, with this capitalization. |
| `"charge"`, `'charge'` | Declared enum labels, used in equality or inequality comparisons. They are not general string operands. |
| `voltage`, `current` | Case-sensitive names of defined signals. |
| `(voltage * current)` | Grouping; parentheses do not convert the type. |

In YAML, `condition: mode == "charge"` is a string containing an expression. The quotes around `charge` belong to that expression. YAML quoting the entire field is a separate layer.

Analysis aliases start with an ASCII letter or underscore, followed by ASCII letters, digits, or underscores. Chinese characters, dots, and spaces are not allowed in these aliases. Python keywords and function names reserved by the selected configuration version cannot be aliases. All built-in function names listed below are reserved. Original CSV headers and DBC signal names can contain other characters: bind them to a legal analysis alias.

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

Set `config_version: 4` (an integer) to use automatic conversion between registered units and the functions below. The current development version accepts configuration version 4 only.

| Task | Expression | How to read the result |
|---|---|---|
| Report power in kW | `to_unit(power, "kW")` | 1500 W becomes 1.5 kW. Both the number and the unit change. |
| Specify a threshold's unit | `voltage > quantity(500, "mV")` | The threshold is 0.5 V whether the signal uses V or mV. |
| Select a power signal using a switch | `where(use_left, left_power, right_power)` | A true Boolean switch selects the left signal. A missing value or an update on the right has no effect. An unknown switch produces an unknown value. |
| Find the smallest or largest value at this instant | `minimum(t1, t2, t3)`, `maximum(t1, t2)` | Compare at least two compatible numbers. A missing required temperature makes this instant's result unknown. |
| Limit a value to a range | `clip(power, quantity(1.25, "kW"), quantity(2, "kW"))` | For inputs of 1 and 3 kW, the two results expressed in kW are 1.25 and 2. Their sample mean is 1.625 kW. |
| Square a signal or take a square root | `square(current)`, `sqrt(square(current))` | −3 A squared is 9 A²; its square root is 3 A. A negative value has no real square root. A value with unit A cannot be square-rooted directly. |

For sample statistics, each actual update of the selected signal counts. Switching branches also counts. Refreshing a switch without changing its state does not add a sample, nor does updating only the inactive signal. Simultaneous updates form one group. Use `where` to select a value and `calculations[].condition` to decide whether a period participates in a calculation.

### Complete built-in function reference

Parameters are positional unless shown as keywords: the tolerances of `isclose` and the options of `lookup` are keyword arguments. Inputs such as `x`, `a`, and `b` can be declared signals or valid expressions. Quote unit and table literals; `"mV"` is not a signal name. Invalid declarations fail loading/validation. Invalid data at one update produces an invalid result with a quality reason.

| Complete call | Parameters and static requirements | Return value, unit, and data errors |
|---|---|---|
| `abs(x)` | One numeric argument; no keywords | Same-type absolute value; the minimum int64 value overflows |
| `isclose(a, b, atol=value, rtol=value)` | Comparable numbers; both tolerances required, as finite nonnegative numeric literals | Boolean; see the comparison rule and tolerance units below. Invalid inputs or intermediates produce unknown |
| `quantity(value, "unit")` | A finite numeric literal, optionally signed; not a signal or `1/10`. Integers must fit the 64-bit range; registered unit literal required | A constant with explicit scale and unit; quantity(500,"mV") means 500 mV and creates no sample update |
| `to_unit(x, "unit")` | Numeric input and a registered, quantity-compatible unit literal | Converts the same physical value; promotes to float64 if needed. Precision/range failure makes the value invalid |
| `where(condition, when_true, when_false)` | Exactly three arguments; Boolean condition and compatible numeric branches. Both branches must have valid names, syntax, types, and units | Uses only the chosen branch's value and quality. Unknown condition gives unknown; an inactive branch cannot hide an undefined name |
| `minimum(a, b, ...)`, `maximum(a, b, ...)` | At least two compatible numeric inputs. A bare constant can be ambiguous when declared scales differ; use quantity | Pointwise minimum/maximum, normally in [canonical units](#canonical-units); a missing required input propagates rather than being ignored |
| `clip(x, lower, upper)` | Three compatible numbers; lower must not exceed upper. Constant inverted bounds fail validation; dynamic inversion is invalid at runtime | Clamps x to the closed interval. Necessary invalid inputs propagate. Use quantity to make bound units explicit |
| `square(x)` | One numeric argument with a unit that can be squared; explicitly convert absolute Celsius to K first | Squared value and unit; integer or floating overflow is invalid |
| `sqrt(x)` | One numeric argument; known quantity exponents must permit square roots. Scale is normalized first | float64 with the square-root unit; negative values are invalid. sqrt(square(current)) is an absolute magnitude |
| `mod(a, b)` | Same-type int64/uint64 inputs, unit 1; bare integers adapt to that type | Same-type remainder, with the divisor's sign; zero divisor is invalid |
| `bit_test(x, bit)` | Unit-1 integer x; integer literal bit in 0–63 | Boolean; signed values use 64-bit two's complement; input invalidity propagates |
| `bit_extract(x, start, width)` | Unit-1 integer x; integer literals start in 0–63 and width in 1–64-start | uint64, unit 1; bit 0 is the least significant bit |
| `to_int64(x)`, `to_uint64(x)`, `to_float64(x)` | Numeric input; explicit to_unit/quantity scale takes precedence, otherwise use canonical units | Requested type and selected unit; fractions are not truncated, overflow never wraps, and inexact conversion is invalid |
| `enum_code(x)` | Enum input retaining its integer code and code_dtype; not a label string | Original int64/uint64 code, unit 1, with its independent code quality; never inferred from a label |
| `lookup(x, "table", mode="linear", bounds="invalid")` | Numeric x; registered table name and option strings must be literals. Two positional arguments; options keyword-only | Table output unit; linear returns float64, step modes use the table type. See [lookup](#lookup-reference) |

For example, `where(enabled, power, missing_name)` fails validation even if enabled is always true. `minimum(v_in_V, v_in_mV, 1)` cannot decide whether 1 means V or mV; write `quantity(1,"V")`. A bare constant inherits a declared scale only when that scale is unambiguous.

<a id="enum-code"></a>

### Integer flags, enum codes and casts (version 4)

Use these expressions in `derived.<name>.expr`, `rules[].condition` or `calculations[].expr`. For a state declared as `int64` or `uint64`, `state == 0x1` works directly without an enum mapping. With an `enum`, `mode == "charge"` compares labels; `enum_code(mode) == 0x1` compares the retained integer code instead.

| Function and arguments | Meaning and requirements |
|---|---|
| `mod(x, y)` | Remainder of dimensionless integers of the same type; a zero divisor gives an invalid value |
| `bit_test(x, bit)` | Boolean test of one bit; bit is a constant integer from 0 through 63, starting at the least significant bit |
| `bit_extract(x, start, width)` | Extract consecutive bits as uint64; start is 0–63 and width is 1–64-start, both integer constants |
| `to_int64(x)`, `to_uint64(x)`, `to_float64(x)` | Explicit numeric casts; fractions are not truncated and overflow does not wrap. An inexact conversion is invalid |
| `enum_code(x)` | Read the retained integer code rather than reverse-mapping its label. Distinct codes sharing a label stay distinct; a valid unmapped code is also available |

Bit functions require unit `1` int64/uint64 input. For flags=6 (binary 110), `bit_test(flags,0)` is False and `bit_extract(flags,1,2)` is 3. Signed integers use 64-bit two’s complement. In-memory enums require `code_dtype` and original codes when using `enum_code`; DBC enums obtain the code type from the signal definition. Invalid records remain invalid.

Casts retain physical meaning and use canonical units by default. For example, 1500 mV becomes 1.5 V and cannot be represented exactly as an integer. To request integer millivolts, write `to_int64(to_unit(voltage, "mV"))`.

<a id="abs-x-取绝对值"></a>
### `abs(x)`: absolute value

`abs(x)` takes exactly one positional numeric argument. It does not accept keywords such as `abs(x=current)`. Taking the absolute value of the minimum int64 value overflows and is invalid.

<a id="isclose-a-b-atol-rtol-允许误差的比较"></a>
### `isclose(a, b, atol=..., rtol=...)`: tolerance comparison

`isclose(a, b, atol=..., rtol=...)` takes exactly two positional arguments and requires both tolerance keywords. Tolerances must be finite, nonnegative numeric literals; they cannot be signals or expressions such as `1/10`.

For example, `isclose(voltage, 400, atol=0.1, rtol=0)` allows an absolute difference of 0.1 V. A bare comparison constant first inherits the other input's declared unit. Both values then convert to canonical units; `atol` is expressed directly in that canonical unit, and `rtol` is dimensionless. The test is:

```text
abs(a - b) <= atol + rtol * abs(b)
```

With voltage declared in mV and equal to 500.0, `isclose(voltage,501,atol=0.1,rtol=0)` compares 0.5 V and 0.501 V using a 0.1 V tolerance: True. To allow 0.1 mV, use `atol=0.0001` (V): False. The equivalent V input uses `isclose(voltage,0.501,atol=0.0001,rtol=0)` and also gives False. Neither quantity nor a signal/expression is accepted for atol. Using to_unit(...,"mV") does not prevent comparison from normalizing to V.

With `a=102`, `b=100`, `atol=0`, and `rtol=0.02`, it returns true. The relative term uses `b`, so the operation is not necessarily symmetric. An invalid operand makes the condition unknown.

<a id="运算优先级"></a>
<a id="运算先后顺序"></a>
<a id="lookup-reference"></a>
### One-dimensional lookup and interpolation

Root `lookups` defines calibration points supplied by the user. Expression `lookup` maps an input coordinate to an output. Obtain the relationship from equipment specifications, measurements, or confirmed data; it is not a built-in voltage-to-power law.

| Field in `lookups[]` | Type and requirement | Meaning |
|---|---|---|
|name|Required unique table name; at most 64 tables|Chosen by the author and referenced as a string in lookup|
|points|Required 2–4096 `[input, output]` pairs|Strictly increasing, nonduplicate input coordinates; finite numbers only, not Boolean or text|
|input_unit|Required registered unit string|Unit of the first column; call input must convert to it|
|unit|Required registered unit string|Unit of the second column and lookup result|

Input coordinates must be exactly representable as float64. Linear-mode outputs must also convert exactly to float64. Step modes can retain int64/uint64 values. If any output is floating point, every output must convert exactly to float64. A negative integer and a positive integer above the int64 maximum cannot share one integer table.

Call `lookup(x, "curve", mode="linear", bounds="invalid")` with exactly two positional arguments. The optional mode and bounds arguments are keyword-only string literals.

| Option | Default and values | Behavior |
|---|---|---|
|mode|linear (default)|Linear interpolation between neighbors; an exact coordinate returns that point|
|mode|previous|Output at the nearest point to the left; an exact coordinate returns that point|
|mode|next|Output at the nearest point to the right; an exact coordinate returns that point|
|bounds|invalid (default)|Out-of-range inputs become invalid; no extrapolation|
|bounds|clamp|Out-of-range inputs use the closest endpoint output|

Unknown tables, unregistered/incompatible units, repeated coordinates, excessive points, dynamic table names, and invalid options fail validation. Missing data, precision loss, and out-of-range values under the default policy are invalid at runtime. The complete [calibration-curve configuration](../examples/lookup-power.yaml) includes ASC input, DBC bindings, and the point table.

#### Example: voltage to calibrated power

Use the [ASC calibration example](../examples/lookup-power.yaml) with its `data/joint.asc` and `data/joint.dbc`. Run `python -m chronaxis run lookup-power.yaml --output result`. The table maps 3 V to 10 W and 11 V to 50 W. At 7 V, `lookup(voltage,'curve')` interpolates to 30 W; `mode='previous'` selects 10 W and `mode='next'` selects 50 W. Out-of-range input is invalid unless you request `bounds='clamp'` to use the nearest endpoint.

From 0 s up to, but excluding, 3 s the three readings are 3, 7 and 3 V. They give 10, 30 and 10 W, so the session result `rated_power` is about 16.67 W: the sample mean of the three power values.

Use `mod`, `bit_test` or `bit_extract` for integer operations. For a flag word of 6 (binary 110), `bit_test(flags,0)` is false and `bit_extract(flags,1,2)` is 3. Use `to_int64`, `to_uint64` and `to_float64` for explicit conversions. Values that cannot be represented exactly are invalid; fractional values are not silently truncated.

## Operator precedence

From highest to lowest: parentheses and function calls; unary `+`/`-`; `*`/`/`; `+`/`-`; comparisons; `not`; `and`; `or`. Arithmetic operators at the same precedence evaluate left to right. For `x=6` and `y=2`, `x + y * 2` is 10, while `(x + y) * 2` is 16. Use parentheses whenever grouping would otherwise be hard to read.

<a id="单位规则"></a>
<a id="单位怎么参与计算"></a>
## Units

A literal in `current > 5` uses the current signal's unit, for example 5 A. Likewise, `voltage + 1` adds 1 V. Multiplication or division by a bare scalar, such as `current * 2` or `current / 2`, retains A.

Supported unit combinations include V × A → W, W × s → J, A × s → A·s, their commutative multiplication forms, and V / V → dimensionless. Version 4 converts compatible registered units: 500 mV + 2 V gives 2.5 V; V divided by A gives Ohm. A supplied scale or offset describes the whole conversion; the unit factor is not applied again. Subtracting two temperatures yields a temperature difference. Convert Celsius explicitly to K before multiplying.

For a custom unknown unit combination, you may explicitly label the derived result, but the unit relationship remains `unverified`: the program has not verified that physical relationship. A label does not prove compatibility.

<a id="类型与整数精度"></a>
<a id="类型-整数精度和错误发生在哪里"></a>
<a id="canonical-units"></a>
### Canonical units

Canonical units are the common calculation scales. Output units can be selected separately; isclose.atol follows this table.

Compound names prefer registered W and J, such as W/s for a power rate, 1/W for reciprocal power and 1/J for reciprocal energy. These names can be parsed again as units. A shorter name does not replace numeric conversion: mA×V retains its factor of one thousandth, N*m remains torque rather than J, and absolute temperatures remain distinct from temperature differences.

| Input | Canonical unit |
|---|---|
|%, 1|1|
|mV, V; mA, A; kW, W|V; A; W|
|Wh, kWh, J; Ah, A*s|J; A*s|
|ms, us, ns, s|s|
|degC, K; delta_degC, delta_K|K; delta_K|
|mOhm, kOhm, MOhm, Ohm|Ohm|
|deg, rad; rpm, rad/s|rad; rad/s|
|kPa, bar, Pa|Pa|
|m, N, N*m, Hz|m, N, N*m, Hz|

## Types and integer precision

Arithmetic between signals requires compatible types. A `float64` signal and an `int64` signal cannot simply be multiplied; make their input types consistent, or in version 4 use explicit conversions such as `to_float64`, described below. Version 4 unit conversion may also promote integers to float64. Python functions `float()` and `int()` are not supported. A numeric literal, such as integer `2` multiplied by a `float64` signal, is handled as a literal and is allowed.

Comparisons between `int64` and `uint64` signals use exact integer comparisons. Comparing a `float64` signal with an integer signal requires consistent input types. A comparison literal can lie outside the signal's range: for example, `9223372036854775808` is greater than every int64 value. An integer literal used in arithmetic must fit the required numeric range.

<a id="配置错误与运行时无效值"></a>
## Configuration errors and runtime invalid values

Undefined names, incompatible units, and unsupported functions are configuration errors. Missing input values, runtime division by zero, and overflow invalidate the affected value and retain the reason. See [concepts](concepts.md) and [execution](execution.md) for quality, missing data, and result handling.

<a id="不支持的语法及替代方式"></a>
<a id="不支持的写法及替代办法"></a>
## Unsupported syntax and alternatives

| Unsupported syntax | Alternative or explanation |
|---|---|
| `**`, `%`, `//`, `@` | In version 4 use `square(x)` for a square or `mod(x,2)` for an integer remainder. Floor division and matrix multiplication are unsupported. |
| `&`, `\|`, `^`, `~`, `<<`, `>>` | In version 4, use `bit_test(flags,0)` for the lowest bit or `bit_extract(flags,1,2)` for the next two bits. |
| `in`, `not in`, `is None`, `is not None` | Combine explicit enum comparisons with `or`; use the quality rules for missing data. |
| Attributes, indexing, slicing, such as `battery.current`, `x[0]`, or `x[1:3]` | Bind original values to simple signal aliases. Expressions do not expose arrays or arbitrary history indexing. |
| `min`, `round`, `float`, `x.mean()` and other calls | For the smaller value use `minimum(x,y)` in version 4. Use the named functions on this page. |
| `*items`, `**options` argument expansion | Use the fixed signatures above. |
| Containers, comprehensions, `x if flag else y` | Use `where(flag,x,y)` in version 4 for conditional selection. |
| Assignment, `lambda`, `import` | Expressions are not executable Python programs. |
| `None`, complex numbers, bytes, string operations | Use strings for enum labels or literal arguments such as table names and units. |

The runnable [expression checks](../examples/readability_examples.py) verify actual results on both calculation backends. They demonstrate the supported expression language, not general Python execution.
