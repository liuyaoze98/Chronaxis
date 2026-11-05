# 第三方代码和依赖

Chronaxis 采用 MIT 许可证。运行依赖独立安装，不因列在依赖中而改用本项目许可证；再分发依赖时应保留对应发行包的许可证和声明。

包内 `chronaxis/legacy/vendor/sclicer_functions_v1/` 的 `utils.py`、`file_processor.py`、`can_processor.py` 来自作者的历史 Sclicer 项目。维护者 liuyaoze 已确认拥有或取得按本项目许可证发布的权利。这三份文件保留原始字节，程序会检查其摘要。

默认运行依赖包括 NumPy、ruamel.yaml、python-can、cantools、natsort，以及用于配置多错误诊断的 jsonschema。文档离线HTML使用 marked 渲染，并包含 highlight.js 产生的高亮样式。发布时一并检查实际打入产物的代码与样式许可；仅安装在开发环境中的工具不自动属于发行内容。

维护者：liuyaoze。

## 本发行核对的直接依赖

|组件|版本|许可证|
|---|---|---|
|NumPy|1.26.3|本体BSD-3-Clause；其wheel另附OpenBLAS、LAPACK、GCC运行库及libquadmath等许可|
|ruamel.yaml|0.19.1|MIT|
|python-can|4.6.1|LGPL-3.0-only|
|cantools|39.4.3|MIT|
|natsort|8.4.0|MIT|
|jsonschema|4.25.1|MIT；由默认依赖安装，不把其源码复制进Chronaxis wheel|
|highlight.js（HTML样式）|11.11.1|BSD-3-Clause；[完整许可](ThirdParty/highlight.js-LICENSE.txt)|
|marked（构建工具）|17.0.5|MIT及其附带的Markdown条款；[完整许可](ThirdParty/marked-LICENSE.txt)|

上表依据本发行依赖包随附的METADATA与许可文件。Python依赖不复制进Chronaxis wheel；NumPy等包的完整再分发条件以各自的许可文件为准。以后若提供捆绑解释器和依赖的便携包，须重新检查完整分发内容。
