# `chronaxis.results.budget`

记录新分析部分已申请多少内存额度，以及还允许申请多少。超过配置上限时抛BudgetExceededError。这里的预算是字节数，不是金额，也不是操作系统对整个Python进程施加的硬限制。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)

## 对象导航

|对象|用途|
|---|---|
|[`_reserve_owned_ram`](#api-_reserve_owned_ram)|预约一笔RAM并按实际账本登记owner及指定槽位，覆盖成功后取消。|
|[`_release_owned_ram`](#api-_release_owned_ram)|抵销一笔实际自有RAM，释放前取消保留金额，释放后取消立即清账。|
|[`_cleanup_owner`](#api-_cleanup_owner)|尝试关闭构造未返回的真实owner，持续失败将恢复句柄附在原异常。|
|[`ResourceBudget`](#api-ResourceBudget)|保存限额与单线程共享计数；每次申请失败都保持原计数不变。|
|[`ResourceBudget.__init__`](#api-ResourceBudget-__init__)|校验并初始化资源计数，不分配数组或创建文件。|
|[`ResourceBudget.reserve_ram`](#api-ResourceBudget-reserve_ram)|在分配前保守申请新层RAM，失败不修改账本。|
|[`ResourceBudget.release_ram`](#api-ResourceBudget-release_ram)|释放已有申请，不能凭负数或重复释放隐藏状态开销。|
|[`ResourceBudget.reserve_spool`](#api-ResourceBudget-reserve_spool)|写入前累计申请磁盘量，失败或部分写入也保守保留申请。|
|[`ResourceBudget._amount`](#api-ResourceBudget-_amount)|检查金额，防止布尔和负数影响预算。|
|[`ResourceBudget.snapshot`](#api-ResourceBudget-snapshot)|返回独立的小型资源快照，不修改计数。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .errors import BudgetExceededError
```

</details>

<a id="api-_reserve_owned_ram"></a>
## `_reserve_owned_ram`

预约一笔RAM并按实际账本登记owner及指定槽位，覆盖成功后取消。

```python
_reserve_owned_ram(owner, amount: int, slot: str) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|资源持有对象|是|无|位置或关键字。已初始化_budget、_held_cost及指定计数属性的对象；预约成功后把字节数记入这些属性。|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

原预算/取消传播，未实际入账不增加自有费用。

### 边界说明

仅围绕一次单线程直接预算调用判断，不用子操作后的总额猜测借用费用。

返回类型：None。

源码：[`src/chronaxis/results/budget.py:14`](../../../src/chronaxis/results/budget.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_release_owned_ram"></a>
## `_release_owned_ram`

抵销一笔实际自有RAM，释放前取消保留金额，释放后取消立即清账。

```python
_release_owned_ram(owner, amount: int, slot: str) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|资源持有对象|是|无|位置或关键字。实际持有预算预约的对象；从其计数中扣除已释放字节，避免重复归还额度。|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`slot`|str|是|无|位置或关键字。owner持有实际_budget/_held_cost/slot；slot为对应实际费用。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

原预算/取消传播，恢复后不得重复抵销已释放资源额度。

返回类型：None。

源码：[`src/chronaxis/results/budget.py:31`](../../../src/chronaxis/results/budget.py#L31)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_cleanup_owner"></a>
## `_cleanup_owner`

尝试关闭构造未返回的真实owner，持续失败将恢复句柄附在原异常。

```python
_cleanup_owner(owner, exc: BaseException, attribute: str, label: str) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|可关闭资源对象|是|无|位置或关键字。构造只完成一部分的对象；调用其清理路径，释放已经取得的资源。|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|
|`attribute`|str|是|无|位置或关键字。attribute为恢复属性名|
|`label`|str|是|无|位置或关键字。label为说明。|

### 返回说明

None，不覆盖原异常。

### 异常说明

关闭错误记录在原异常notes中，不向外替换它。

返回类型：None。

源码：[`src/chronaxis/results/budget.py:49`](../../../src/chronaxis/results/budget.py#L49)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ResourceBudget"></a>
## `ResourceBudget`

保存限额与单线程共享计数；每次申请失败都保持原计数不变。

```python
ResourceBudget(memory_budget_bytes: int=268435456, spool_quota_bytes: int | None=None)
```


源码：[`src/chronaxis/results/budget.py:67`](../../../src/chronaxis/results/budget.py#L67)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ResourceBudget-__init__"></a>
### `ResourceBudget.__init__`

校验并初始化资源计数，不分配数组或创建文件。

```python
ResourceBudget.__init__(memory_budget_bytes: int=268435456, spool_quota_bytes: int | None=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`memory_budget_bytes`|int|否|268435456|位置或关键字。memory_budget_bytes为RAM估算bytes|
|`spool_quota_bytes`|int &#124; None|否|None|位置或关键字。spool_quota_bytes为可选累计限额。|

#### 返回说明

新账本。

#### 异常说明

ValueError为bool、非正数或非原生int。

本函数直接报告的具体错误：

- `ValueError`：RAM限额不能省略。
- `ValueError`：资源限额需要正原生int。

源码：[`src/chronaxis/results/budget.py:70`](../../../src/chronaxis/results/budget.py#L70)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ResourceBudget-reserve_ram"></a>
### `ResourceBudget.reserve_ram`

在分配前保守申请新层RAM，失败不修改账本。

```python
ResourceBudget.reserve_ram(amount: int) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为金额错误；BudgetExceededError为超限。

返回类型：None。

源码：[`src/chronaxis/results/budget.py:86`](../../../src/chronaxis/results/budget.py#L86)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ResourceBudget-release_ram"></a>
### `ResourceBudget.release_ram`

释放已有申请，不能凭负数或重复释放隐藏状态开销。

```python
ResourceBudget.release_ram(amount: int) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为金额错误或超出当前申请。

本函数直接报告的具体错误：

- `ValueError`：RAM释放超出当前申请。

返回类型：None。

源码：[`src/chronaxis/results/budget.py:99`](../../../src/chronaxis/results/budget.py#L99)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ResourceBudget-reserve_spool"></a>
### `ResourceBudget.reserve_spool`

写入前累计申请磁盘量，失败或部分写入也保守保留申请。

```python
ResourceBudget.reserve_spool(amount: int) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为金额错误；BudgetExceededError为累计超配额。

本函数直接报告的具体错误：

- `BudgetExceededError`：累计磁盘暂存超过spool_quota_bytes。

返回类型：None。

源码：[`src/chronaxis/results/budget.py:110`](../../../src/chronaxis/results/budget.py#L110)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ResourceBudget-_amount"></a>
### `ResourceBudget._amount`

检查金额，防止布尔和负数影响预算。

```python
ResourceBudget._amount(amount: int) -> None
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为非法金额。

本函数直接报告的具体错误：

- `ValueError`：资源金额需要非负原生int。

返回类型：None。

源码：[`src/chronaxis/results/budget.py:122`](../../../src/chronaxis/results/budget.py#L122)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ResourceBudget-snapshot"></a>
### `ResourceBudget.snapshot`

返回独立的小型资源快照，不修改计数。

```python
ResourceBudget.snapshot() -> dict
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

限额、当前/峰值RAM估算和累计spool预留。

#### 异常说明

无；整进程RSS不在此模型内。

返回类型：dict。

源码：[`src/chronaxis/results/budget.py:130`](../../../src/chronaxis/results/budget.py#L130)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
