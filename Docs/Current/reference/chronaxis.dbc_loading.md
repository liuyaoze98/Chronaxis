# `chronaxis.dbc_loading`

集中加载DBC文本，不进入第三方持久缓存入口。

调用方负责导入cantools、复用数据库和校验文件身份；这里使用公开load接口，
保留load_file无缓存分支的格式、编码和解析默认值，不读取缓存环境变量。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`load_dbc_file`](#api-load_dbc_file)|按文件后缀打开一次文本并交给调用方持有的cantools解析。|

<a id="api-load_dbc_file"></a>
## `load_dbc_file`

按文件后缀打开一次文本并交给调用方持有的cantools解析。

```python
load_dbc_file(path, cantools)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; os.PathLike[str]|是|无|位置或关键字。调用方提供的数据库文件路径；按后缀选择格式，dbc/sym 使用 cp1252，其他后缀使用 UTF-8，解码错误替换。只打开并读取一次，不把未知后缀改成自动探测。|
|`cantools`|types.ModuleType|是|无|位置或关键字。调用方已导入的 cantools 模块；使用其公开 database.load 解析已打开的文本流，不调用可读取 CANTOOLS_CACHE_DIR 的 load_file 缓存入口。|

### 返回说明

cantools.database.load 返回的数据库；保留 frame_id_mask=None、prune_choices=False、strict=True 以及该接口的默认排序和其他解析参数。

### 异常说明

文件打开、格式识别、解析及关闭错误原样传播。不会读取缓存环境变量、进入 diskcache、修改进程环境或保存数据库副本；调用方负责数据库复用和输入身份检查。

源码：[`src/chronaxis/dbc_loading.py:10`](../../../src/chronaxis/dbc_loading.py#L10)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
