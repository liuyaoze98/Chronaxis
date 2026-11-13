# 发布操作流程

[English](publishing.en.md)

本页记录 2026-11-02 发布 `0.1.0.dev1` 时实际走通的流程，供下一次发布复用。该版本已经发布；下次先按[版本规则](versioning.md)确定新版本，不覆盖已有文件或移动已有标签。

顺序为：**本地打包与验收 → 公开源码和版本附件 → HTML 上线 → PyPI 预演 → PyPI 上传 → 全新环境安装验收 → 保存发布结果**。本次使用 GitHub 可信发布，没有使用 TestPyPI，也没有通过本机 Twine 上传。

## 一次性设置

|项目|已采用的设置|
|---|---|
|公开源码仓库|[liuyaoze98/Chronaxis](https://github.com/liuyaoze98/Chronaxis)|
|PyPI|项目 `chronaxis`；按[可信发布设置](trusted-publishing.md)授权 GitHub|
|PyPI 发布身份|Owner=`liuyaoze98`，Repository=`Chronaxis`，Workflow=`pypi-publish.yml`，Environment=`pypi`|
|GitHub Pages|仓库 Settings → Pages → Source 选择 GitHub Actions|
|HTML 地址|[中文](https://liuyaoze98.github.io/Chronaxis/)与[English](https://liuyaoze98.github.io/Chronaxis/en/)|
|维护者与许可|`liuyaoze <work@liuyaoze.com>`，MIT|

PyPI 通过 GitHub 的短期身份凭据接收文件，无需向 AI 提供密码或令牌。现有可信发布配置可以用于后续版本；更改仓库、工作流文件名或环境名时，需要重新核对绑定。两个工作流均手动触发，上传源码不会自动发布网站或安装包。

下一次发布前，还须核对候选公开源码的`verify.yml`四组持续测试及独立安装结果，详见[持续测试要求](../Current/maintenance.md#持续测试与发布前检查)。该验证工作流不改变两个发布入口的手动触发规则；不要用历史dev1/dev3报告代替本次候选的检查。

## 1. 本地打包与验收

以 `pyproject.toml` 的 `project.version` 为唯一发行版本来源，修改该值并同步 README、中英文安装示例、AI 指南和本版说明。构建器自动写入安装包版本；`RunMetadata.software_version` 的默认值从当前软件取得，不另维护版本常量，显式传入的历史版本保持原值。验收时核对运行版本、包元数据和 AI 清单一致。`Documentation` 指向在线 HTML，`Changelog` 指向发行记录入口；README 的相对文件链接在构建时转换为本次公开标签下的地址。

在内部仓库完成验证和提交，再从明确的提交导出。以下工具是本次实际使用的构建链路；参数中的提交必须是已审阅版本。

|工具或检查|用途及通过条件|
|---|---|
|`tools/build_m2_docs.py --edition Current`|从 `Docs/Current/documentation.json` 指定源码生成参考；公开签名与实际接口一致|
|`tools/english_docs.py --record-reviewed`|先核对受影响译文，再登记中英文来源；不能仅刷新摘要消除失败|
|`tools/lock_ai_inputs.py <手册提交> --runtime <运行源码提交> --device-label <home或work>`|锁定同版指南输入；在提交对应资料后执行|
|`tools/export_public_source.py <新目录> --revision <提交>`|按白名单导出公开文件和 `PUBLIC-SOURCE.json`，排除内部 Git 历史、管理记录、真实数据及工作区未提交内容|
|`tools/verify_ai_distribution.py <新构建目录> --public-source <公开导出目录>`|从无 Git 的干净源码构建 sdist，再由 sdist 构建 wheel，检查安装指南与可选 ZIP 一致|
|`node tools/render_current_docs.mjs`|生成中英文 HTML 和可直接阅读的 AI 资料|
|`tools/check_current_html.py`、`node tools/test_manual_search.mjs`、`tools/package_current_docs.py`|检查页面/资源/搜索/复制内容，打包并核对手册移动后仍可用|
|`tools/check_ai_install.py <wheel> <AI ZIP> <已准备的依赖目录> <报告路径> --device-label <home或work>`|在隔离环境核对指南、公开签名和随包任务|
|`python -m twine check <wheel> <sdist>`|检查 PyPI 包格式与 README；这一步不上传|

Python 工具通过 `python -B` 调用。构建依赖和文档工具要求见[文档维护说明](../Current/maintenance.md)。源代码变化时重建受影响资料，并在交付时比较 HTML 与 wheel 中的 AI 指南。测试或构建失败先定位，不通过修改校验摘要、跳过断言来冒充通过。

整理以下五个 GitHub Release 附件，并保存 SHA256：wheel、sdist、`Chronaxis-Source-<版本>.zip`、`Chronaxis-Manual-<版本>.zip`、`SHA256SUMS.txt`。其中摘要文件列出另外四个附件的摘要；上传后再核对五个附件本身。`delivery.json` 和验证日志留在本地交付工作目录；各附件的名字须与工作流一致。PyPI 只接收 wheel 和 sdist。

## 2. GitHub源码与发行附件

内部开发仓库与公开仓库使用独立历史。首次发布时初始化公开仓库；后续发布沿用已有公开检出，先检查工作区、拉取并快进 `main`，再同步本次白名单导出的内容。逐项检查差异后提交并推送；不要把内部仓库直接添加公开 remote 后推送全部历史。

以下命令在已完成公开源码同步的环境使用。`$PublicRepo` 指公开仓库检出目录，不能指内部开发仓库；`$Version` 必须是尚未发布的新版本。

```powershell
$PublicRepo = Read-Host 'Public repository checkout path'
$Version = Read-Host 'New release version'
git -C $PublicRepo status --short
git -C $PublicRepo push origin main
git -C $PublicRepo tag -a "v$Version" -m "Chronaxis $Version"
git -C $PublicRepo push origin "v$Version"
```

当前 PyPI 工作流解析的是**附注标签**，因此使用 `git tag -a`。标签指向已核验的公开源码提交。公开文件应与 `PUBLIC-SOURCE.json` 对应，不能将内部提交 SHA 当作公开提交 SHA。

按该标签创建 GitHub Release 草稿，上传五项附件，核对名称、大小和 SHA256。开发预览版标为 prerelease。附件正确后先公开预发行，正文如实说明 PyPI 尚待上传；这是后续工作流用只读仓库权限取得附件的前提。

## 3. 更新本次发布的工作流

工作流不会自动推断新版本或重新构建文件。**只改本地 `$Version` 变量不够**，每次需检查下表，并将修改提交到公开 `main`。

|文件|每次要更新|当前权限|
|---|---|---|
|`.github/workflows/pages.yml`|Release 标签、手册 ZIP 文件名及 SHA256|`contents: read`、`pages: write`、`id-token: write`|
|`.github/workflows/pypi-publish.yml`|版本说明、Release 标签、该标签指向的公开源码 SHA、wheel/sdist 文件名及各自 SHA256|`contents: read`、`id-token: write`|

两项均限定本仓库和 `main`，官方 Action 固定到提交。源码标签冻结后，可以另外提交发布工作流到 `main`，不为填入公开源码 SHA 而移动标签。本次 `dev1` 就采用这个顺序。工作流锁定的版本和摘要以当前文件为准，不从这份历史记录推断。新候选尚未确定公开源码提交和附件摘要时，保留已有工作流；实际发布前再一次性更新并核对，不能填占位摘要或提前运行。

## 4. HTML上线

```powershell
gh workflow run pages.yml --repo liuyaoze98/Chronaxis --ref main
```

在 Actions 中等到本次运行成功。流程下载公开手册附件、校验 SHA256、解压并部署，不在云端重新生成内容。

从公网检查中英文首页、语言切换目标、样式、脚本、搜索数据、一个实际教程及 AI 指南。核对返回内容与已验手册一致，并确认页面为 HTML；HTTP 200 可能只是错误页或访问挑战，不能单独作为验收结果。在线入口提供当前发布版；历史版本通过对应 Release 的离线手册保留。

## PyPI正式上传与回读

先运行不上传的预演：

```powershell
gh workflow run pypi-publish.yml --repo liuyaoze98/Chronaxis --ref main -f upload=false
```

确认**这一次**运行成功：标签对应源码正确，两项附件摘要通过，上传步骤跳过。随后才执行正式上传：

```powershell
gh workflow run pypi-publish.yml --repo liuyaoze98/Chronaxis --ref main -f upload=true
```

当前发布使用 PyPI Trusted Publishing，并保留发布签名。成功后核对 `https://pypi.org/pypi/chronaxis/<版本>/json` 中的两项文件名/SHA256、版本、Python 和依赖要求、MIT、作者邮箱、README 及项目链接；同时检查项目默认版本的 `Documentation` 确实指向 HTML。

从正式 PyPI 新建环境安装，使用随包指南运行示例：

```powershell
py -3.12 -m venv .venv-pypi
$CheckPython = '.venv-pypi/Scripts/python.exe'
& $CheckPython -m pip install --no-cache-dir --index-url https://pypi.org/simple/ "chronaxis==$Version"
& $CheckPython -m pip check
& $CheckPython -m chronaxis guide --language en
$Guide = Split-Path (& $CheckPython -m chronaxis guide)
& $CheckPython "$Guide/run_analysis.py" "$Guide/examples/conditional-energy.yaml" result-release-check
```

虚拟环境和 `result-release-check` 使用新目录。预期得到一个 61–122 秒的事件、`0.06777777777777777 kWh`、状态“完整”；中英文指南均能直接定位，运行前后指南文件不变。Windows/Python 3.12 是本次实际验证环境，不据此扩大平台支持声明。

最后更新 GitHub Release 正文，去掉“PyPI 待上传”等临时状态；保存发布地址、源码/标签、文件摘要、工作流运行和安装结果，再更新内部计划、问题与交接记忆。仅有工作流成功不能代替安装验收。

## 本次遇到的问题与处理

|现象|实际处理及下次做法|
|---|---|
|dev0 的 PyPI 文档链接打开 GitHub Markdown|先上线 HTML，再发 dev1 修正元数据。PyPI 已上传版本的资料不能靠修改仓库 README 原位覆盖|
|工作流读取 Release 草稿报 `release not found`|草稿对只读身份不可见。先核对并公开附件，再运行 Pages/PyPI；维护者核对草稿时，本次使用 release ID 查询|
|Pages 申请 `contents:write` 被自动审批拒绝|采用公开附件加 `contents:read`，只保留部署需要的 Pages/OIDC 权限|
|Git HTTPS 传输重置|本次改用 GitHub Git Data API 上传同一审核内容，只快进已核对父提交；再 fetch 并快进本地公开镜像。没有强推或重写历史|
|Sigstore/Rekor 返回 HTTP 502|先核对失败阶段及 PyPI 远端文件；本次确认 dev1 尚无文件后原流程重试。若已有部分文件，先核对摘要和状态，不盲目重跑，不默认开启 `skip-existing` 或关闭签名|
|系统临时目录无写权限|改用本次专用工作目录设置 `TEMP`/`TMP`，重新执行受影响的校验|
|旧手册检查器要求英文页包含中文履历|使用适用的双语来源、HTML和指南校核，保留原失败记录；不能把不适用断言说成产品缺陷已修复|
|PyPI HTML 返回 `Client Challenge`|通过官方 JSON 核对发布元数据，另外核对目标 HTML；如实注明未执行浏览器交互验证|

本次 `dev1` 的线上证据：[Pages 第二次部署成功](https://github.com/liuyaoze98/Chronaxis/actions/runs/41463321957)、[PyPI 无上传预演](https://github.com/liuyaoze98/Chronaxis/actions/runs/41464499414)、[PyPI 第二次上传成功](https://github.com/liuyaoze98/Chronaxis/actions/runs/41464970458)、[GitHub 预发行](https://github.com/liuyaoze98/Chronaxis/releases/tag/v0.1.0.dev1)。这些是历史验收记录，不表示下一版本已通过相同检查。

维护者：liuyaoze。详细发布范围见[分发说明](distribution.md)，依赖限制见[安全说明](security.md)。
