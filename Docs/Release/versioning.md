# 版本号规则

软件版本遵循 [Python 版本规范](https://packaging.python.org/en/latest/specifications/version-specifiers/)，以 `pyproject.toml` 中的 `project.version` 为唯一发行版本来源。

|示例|含义|
|---|---|
|`0.1.0.dev0`|0.1.0 的第一个开发预览包|
|`0.1.0.dev1`、`0.1.0.dev2`|后续开发预览包；已上传包有变化时递增|
|`0.1.0a1` / `0.1.0b1`|可选的 alpha / beta 预发行|
|`0.1.0rc1`|可选的候选发行|
|`0.1.0`|去掉预发行后缀的正式版本|
|`0.1.1`|保持兼容的缺陷修复|
|`0.2.0`|0.x 阶段新增功能或包含明确告知的不兼容变化|

不要求每次发行经过所有预发行名称。0.x 阶段接口仍可能调整；不兼容变化在发行说明中列出迁移方法，不隐藏在补丁版本里。达到1.0后，主版本表示不兼容变化，次版本表示兼容的新功能，补丁表示兼容的修复。

PyPI 不允许重复使用已上传的发行文件名，删除后也不能覆盖。因此已公开版本不可原地替换；修正后发布新版本。Git 标签可以是 `v0.1.0.dev0`，包元数据版本不加 `v`。

`config_version: 4` 是配置格式版本，不是软件版本。开发阶段 M2/M3/M4、手册修订和内部提交号也不替代软件版本。示例配置和指南应与实际包版本匹配。

维护者：liuyaoze。政策依据：[Python 规范](https://packaging.python.org/en/latest/specifications/version-specifiers/)、[PyPI 文件名规则](https://pypi.org/help/#file-name-reuse)。
