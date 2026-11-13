# 发布范围与检查

## 各交付物包含什么

|交付物|包含|不包含|
|---|---|---|
|公开源码|运行代码、许可证、README、打包文件、可独立执行的测试与合成夹具、公开手册及所需工具|内部开发计划、问题和审计归档、机器标识、真实车辆日志/DBC、历史项目、缓存、冲突副本|
|wheel|chronaxis包、模板、AI指南、许可证与包元数据|开发测试、完整源码手册、业务日志、独立安装的运行依赖代码|
|sdist|重新构建wheel需要的源码、配置、许可证、指南输入及生成工具，以及公开依赖环境约束|开发工作目录、内部验收材料|
|离线手册|HTML、相对链接、搜索资源、合成示例和配置规范|内部审计附件、作者机器上的文件路径|

从单独导出的清洁源码树构建发行包。内部开发仓库包含历史资料，不直接推送整个开发历史；导出不删除或重写原仓库。

具体操作见[发布流程](publishing.md)（[English](publishing.en.md)），发行说明见[0.1.0.dev4](release-notes-0.1.0.dev4.md)。PyPI只接收wheel和sdist，源码和手册ZIP作为GitHub Release附件。

## 发布前检查

1. 明确版本、许可、仓库地址及支持平台；不能写入占位的项目网址。
2. 核对导出清单、第三方权利、个人路径、凭据、原始数据和冲突副本。
3. 在没有Git、历史项目和既有工作目录的环境构建sdist，再由sdist构建wheel。
4. 检查元数据、wheel/sdist成员与许可证；新环境安装，运行CLI、合成任务和指南校验。
5. 确认手册正文、HTML、AI指南一致，链接可达；保留已知平台限制和未验证项。
6. 汇总文件SHA-256、测试结果及已知问题；用户审阅后再执行上传。

纯Python wheel的`any`标签不代表所有操作系统都已验证。当前支持范围见根README。

维护者：liuyaoze。

## 从公开源码运行测试

```powershell
python -m pip install -e ".[test]"
python -B tools/run_ci_tests.py --group core --report work/ci/core.json
python -B tools/run_ci_tests.py --group input --report work/ci/input.json
python -B tools/run_ci_tests.py --group docs --report work/ci/docs.json
python -B tools/run_ci_tests.py --group install --report work/ci/install.json
```

`core`检查计算与执行，`input`检查读取与导出，`docs`检查手册、AI指南及生成工具，`install`检查版本和安装入口。分组报告列出实际运行、失败及跳过原因；跳过不能计为通过。文档组还需要Node.js及`marked`，安装和定位方式见[维护说明](../Current/maintenance.md)。缺少文档工具应先补齐依赖，不能跳过整组后宣称完整回归通过。可用`--group all`一次运行四组，或用`--list-only`仅核对分组清单。

性能比较应使用同一输入、分析含义、后端和批量配置；专项测试耗时不是产品性能基准。

公开测试使用合成输入。依赖内部资料的9个测试模块不随公开源码分发；具体文件名记录在导出清单 `PUBLIC-SOURCE.json`。受操作系统权限限制的符号链接用例、未提供真实表格的可选对照会明确跳过，不能把跳过写成通过。运行测试会创建独立临时目录及 `work/` 输出，不要求发布既有工作数据。

公开文档可按[维护说明](../Current/maintenance.md)在无私有Git历史的情况下重建；必须显式启用源码树模式，并通过发行摘要检查。
