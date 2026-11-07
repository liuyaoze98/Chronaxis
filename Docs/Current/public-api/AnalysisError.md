# chronaxis.AnalysisError

使用`from chronaxis import AnalysisError`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.results.errors.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`AnalysisError`](#api-AnalysisError)

<a id="api-AnalysisError"></a>
## `AnalysisError`

表示分析或结果交付失败；异常本身不承诺旧输出已回滚。

```python
class AnalysisError(RuntimeError)
```

继承关系：RuntimeError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/results/errors.py:8`](../../../src/chronaxis/results/errors.py#L8)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
