# 通过GitHub发布至PyPI

[English](trusted-publishing.en.md)

此流程上传已经构建、安装验证并附在GitHub Release中的发行文件。GitHub向PyPI申请短期发布凭据，无需将密码或API令牌保存在仓库中。

## 首次设置

登录[PyPI发布设置](https://pypi.org/manage/account/publishing/)，在“Add a new pending publisher”中选择GitHub，填写：

|字段|内容|
|---|---|
|PyPI Project Name|`chronaxis`|
|Owner|`liuyaoze98`|
|Repository name|`Chronaxis`|
|Workflow name|`pypi-publish.yml`|
|Environment name|`pypi`|

Workflow name只填文件名，不带`.github/workflows/`。Environment name与工作流中的环境一致，不是Python虚拟环境。点击Add保存。账号需要满足PyPI的邮箱验证及双因素认证要求；创建待发布配置不会提前占用项目名称。已有chronaxis项目时，在该项目的Publishing页面添加相同配置。

## 验证和上传

在[GitHub Actions](https://github.com/liuyaoze98/Chronaxis/actions/workflows/pypi-publish.yml)选择Run workflow，分支选main。

1. 不勾选上传选项先运行：只下载两个发行文件，核对源码标签及SHA256，不上传PyPI。
2. 验证成功且PyPI网页设置完成后，勾选上传选项运行。成功后检查[PyPI项目页](https://pypi.org/project/chronaxis/0.1.0.dev1/)。
3. 按[发布流程](publishing.md#pypi正式上传与回读)在新环境从PyPI安装，核对依赖、指南及能量示例，并更新GitHub Release中的发布状态。

当前工作流固定发布0.1.0.dev1及其已验摘要，不会重建或移动源码标签。下一版本发布前，应完成新包验证，再更新工作流的版本、源码提交及两文件摘要。不要为了绕过上传失败启用skip-existing；先核实远端文件是否与本地一致。

TestPyPI是可选的独立试上传环境。本轮没有TestPyPI账号时，可以先完成本地隔离安装验证，再从正式PyPI安装回读。

维护依据：[PyPI首次可信发布说明](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)。维护者：liuyaoze。
