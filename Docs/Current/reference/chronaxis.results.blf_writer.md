# `chronaxis.results.blf_writer`

独占持有一份BLF输出文件，委托既有python-can格式写入，不重写BLF编码。

写入器与底层文件属于同一owner；文件头构造、压缩或最终头更新失败时关闭实际句柄。
第三方stop至多调用一次，关闭重试仅处理尚未关闭的文件，不重复压缩或重写完成头。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`BLFWrite`](#api-BLFWrite)|管理一个新的BLF文件及其python-can writer，不接收来源路径或DBC。|
|[`BLFWrite.__init__`](#api-BLFWrite-__init__)|独占创建文件并安装writer。|
|[`BLFWrite.closed`](#api-BLFWrite-closed)|查询实际关闭状态。|
|[`BLFWrite.write`](#api-BLFWrite-write)|写入当前原帧一次。|
|[`BLFWrite.finish`](#api-BLFWrite-finish)|完成压缩与最终文件头。|
|[`BLFWrite.close`](#api-BLFWrite-close)|关闭同一实际文件，第三方stop最多一次。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from .budget import _cleanup_owner
```

</details>

<a id="api-BLFWrite"></a>
## `BLFWrite`

管理一个新的BLF文件及其python-can writer，不接收来源路径或DBC。

```python
BLFWrite(path)
```


源码：[`src/chronaxis/results/blf_writer.py:10`](../../../src/chronaxis/results/blf_writer.py#L10)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BLFWrite-__init__"></a>
### `BLFWrite.__init__`

独占创建文件并安装writer。

```python
BLFWrite.__init__(path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次独占新建的BLF输出文件路径；已有文件不能覆盖。|

#### 返回说明

owner。

#### 异常说明

原创建/文件头错误。

传入文件对象由python-can的stop关闭；本对象只在第三方未完成关闭时收尾同一句柄。
构造失败仍保留blf_write_cleanup_owner，不借重新打开文件修补失败。

源码：[`src/chronaxis/results/blf_writer.py:13`](../../../src/chronaxis/results/blf_writer.py#L13)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BLFWrite-closed"></a>
### `BLFWrite.closed`

查询实际关闭状态。

```python
BLFWrite.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool，不表示失败文件可发布。

#### 异常说明

无。

源码：[`src/chronaxis/results/blf_writer.py:33`](../../../src/chronaxis/results/blf_writer.py#L33)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BLFWrite-write"></a>
### `BLFWrite.write`

写入当前原帧一次。

```python
BLFWrite.write(message)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`message`|can.Message|是|无|位置或关键字。要写入的本条原帧；交给现有python-can writer一次，不在失败后重试写入。|

#### 返回说明

None。

#### 异常说明

原写入错误或已结束时RuntimeError。
不重试写入，避免重复添加帧。

源码：[`src/chronaxis/results/blf_writer.py:40`](../../../src/chronaxis/results/blf_writer.py#L40)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BLFWrite-finish"></a>
### `BLFWrite.finish`

完成压缩与最终文件头。

```python
BLFWrite.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，仅真实stop成功可正常返回。

#### 异常说明

原收尾错误；已经失败的最终写入不能重试，返回RuntimeError。

源码：[`src/chronaxis/results/blf_writer.py:49`](../../../src/chronaxis/results/blf_writer.py#L49)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BLFWrite-close"></a>
### `BLFWrite.close`

关闭同一实际文件，第三方stop最多一次。

```python
BLFWrite.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复关闭安全。

#### 异常说明

保留原收尾错误；实际文件仍未关闭时附可重试owner，其他错误加入notes。

源码：[`src/chronaxis/results/blf_writer.py:60`](../../../src/chronaxis/results/blf_writer.py#L60)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
