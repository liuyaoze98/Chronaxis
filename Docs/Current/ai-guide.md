# 把当前版本交给 AI 使用

让AI生成配置或Python代码时，先提供AI指南的README，再按任务查示例、配置字段或公开API。根据你已经拥有的文件选择入口：

|已有内容|如何打开指南|
|---|---|
|项目源码|直接打开 `Docs/AI/README.md`；英文版为 `Docs/AI/en/README.md`。保留仓库目录结构，即可跟随链接阅读和查询，不需要下载、构建或导出资料。|
|离线HTML手册|直接打开手册附带的[中文指南](_build/html/ai-guide/README.md)或[英文指南](_build/html/ai-guide/en/README.md)，文件已展开，无需再取ZIP。|
|只有已安装的Chronaxis包|用下面的命令查看README路径，然后直接用编辑器打开或交给AI。|

```text
python -m chronaxis guide
python -m chronaxis guide --language en
```

命令只显示路径，不生成或解压文件。安装目录中的 `chronaxis/guide` 已包含说明、字段参考和示例。运行示例时，把结果保存到自己的工作目录。

如需另存完整离线副本，可选用 `python -m chronaxis guide --output my-guide.zip`；目标须为新文件，ZIP始终包含中英两版。日常阅读不需要这一步。

阅读指南无需安装Chronaxis；查询脚本只使用Python标准库。实际运行分析示例时，使用已安装项目依赖的环境。先按任务索引选取匹配示例，核对输入、时间单位与预期结果，再换成自己的数据；会影响结果的信息缺失时先补齐。

生成配置时同时说明文件关系和进程数：一个ASC/BLF来源的连续分卷采用 `execution.process_count: 4`，独立试验采用批量根级 `process_count: 4`，子任务保持1。CSV、内存或多来源计划按当前支持范围使用1。基础示例与完整规则见[执行配置](execution.md)。
