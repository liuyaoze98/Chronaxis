# chronaxis.TimeOverflowError

使用`from chronaxis import TimeOverflowError`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.timebase.conversion.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`TimeOverflowError`](#api-TimeOverflowError)

<a id="api-TimeOverflowError"></a>
## `TimeOverflowError`

时间坐标、偏移后坐标或非负跨度超出int64时拒绝运算。

异常不携带可被误用的回绕结果；失败由调用者记录为任务校验错误。
本类型没有可变状态，不打开资源或把失败当正常零时长。

```python
class TimeOverflowError(OverflowError)
```

继承关系：OverflowError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/timebase/conversion.py:38`](../../../src/chronaxis/timebase/conversion.py#L38)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
