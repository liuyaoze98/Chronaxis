# chronaxis.PlanValidationError

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.planning.checks.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [PlanValidationError](#api-PlanValidationError)
- [PlanValidationError.__init__](#api-PlanValidationError-__init__)
- [PlanValidationError.refresh_text](#api-PlanValidationError-refresh_text)
- [PlanValidationError.to_dict](#api-PlanValidationError-to_dict)

<a id="api-PlanValidationError"></a>
## `PlanValidationError`

保存配置字段路径、原因、机器错误码及可选的原文定位和修正建议。

不吞执行异常或数据读取失败；code区分无效配置与尚未接入可运行流程能力。

```python
PlanValidationError(path: str, message: str, code: str = 'invalid_config', *, hint=None, source=None, location=None, object_name=None, value=None)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/planning/checks.py:26`](../../../src/chronaxis/planning/checks.py#L26)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PlanValidationError-__init__"></a>
### `PlanValidationError.__init__`

建立明确路径错误，保留原异常链供load_analysis_plan诊断。

```python
PlanValidationError.__init__(path: str, message: str, code: str='invalid_config', *, hint=None, source=None, location=None, object_name=None, value=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。标识配置中的出错字段，例如$.signals[0].unit；由校验器根据实际声明位置生成。|
|`message`|str|是|无|位置或关键字。解释该字段违反的要求，例如需要正整数；用于面向用户的错误正文，不应包含完整私有输入数据。|
|`code`|str|否|'invalid_config'|位置或关键字。提供机器可识别的错误类别，默认invalid_config表示无效配置；读取异常时用code分类，不依赖中文message匹配。|
|`hint`|str 或 None|否|None|仅关键字。可选修正提示，例如有效枚举值或可用名称；提示不会自动修改原配置。|
|`source`|str 或 None|否|None|仅关键字。配置来源文件或显示名，与字段path分开；没有可靠来源时保留None。|
|`location`|ConfigurationLocation 或 None|否|None|仅关键字。可证明的原始行列；缺失时只给文件与字段，不猜位置。|
|`object_name`|str 或 None|否|None|仅关键字。错误所属的来源、信号或节点名称；只用于定位，不参与名称推断。|
|`value`|str 或 None|否|None|仅关键字。已截短的当前值说明，大容器仅显示类型与大小，避免打印整份配置。|

#### 返回说明

None；异常文本含路径和原因。

#### 异常说明

无；参数由校验器内部构造。

源码：[`src/chronaxis/planning/checks.py:32`](../../../src/chronaxis/planning/checks.py#L32)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PlanValidationError-refresh_text"></a>
### `PlanValidationError.refresh_text`

重建人读消息。

```python
PlanValidationError.refresh_text()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

无；附加定位后调用。

源码：[`src/chronaxis/planning/checks.py:56`](../../../src/chronaxis/planning/checks.py#L56)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PlanValidationError-to_dict"></a>
### `PlanValidationError.to_dict`

返回稳定机器诊断。

```python
PlanValidationError.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

原生dict。

#### 异常说明

无。

源码：[`src/chronaxis/planning/checks.py:70`](../../../src/chronaxis/planning/checks.py#L70)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
