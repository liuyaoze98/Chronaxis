# 手册构建与维护

本页面向文档维护者。人工指南位于Docs/Current，公开名称清单为public-api.json，分组导航为navigation.json；逐对象注解存于annotations.json。documentation.json指定已经提交的源码基线，内部维护默认从该Git对象提取API；公开源码导出树使用下述显式源码树模式，仍核对发行摘要。

## 构建依赖

需要项目Python依赖、Node.js、marked 17.0.5及highlight.js 11.11.1。首次构建可在仓库根安装文档工具：

```powershell
npm install --prefix Docs/Current/_build/tooling marked@17.0.5 highlight.js@11.11.1
```

安装可能访问软件源；渲染和阅读本身不访问网络。已有依赖可通过CHRONAXIS_MARKED_PATH、CHRONAXIS_HIGHLIGHT_PATH指定模块文件。高亮样式从本版工具目录读取，因此仍须保存对应highlight.js样式文件。

## 从公开源码重建

公开导出不携带内部开发Git历史。使用已有发行锁定清单，在运行以下构建命令前显式设置：

```powershell
$env:CHRONAXIS_DOC_SOURCE_TREE = '1'
```

此模式要求运行源码和配置规范与发行清单一致；缺失或修改会报错，不会静默使用其他版本。它不需要私有Git提交。修改产品后准备新发行时，由维护者重新审核源码、示例与资料，再更新锁定清单。仅安装或使用sdist重建wheel不需要重建整套手册。

## 重建与检查

```powershell
python -B tools/build_m2_docs.py --edition Current
node tools/render_m2_docs.mjs --edition Current
python -B tools/verify_m2_docs.py --edition Current
python -B tools/check_current_html.py
node tools/test_manual_search.mjs
```

打开[HTML首页](_build/html/index.html)。整个_build/html目录可复制到其他位置，保留子目录结构；其中包含相对导航、代码样式、搜索脚本、冻结源码、示例和配置规范。无需本地服务器，阅读不需要Python或Node；执行示例仍需安装项目。

## 维护规则

源码AI指南直接引用Current与Schema已有资料。tasks.json中的示例路径相对Docs/AI；lookup.py在源码中按需读取已有API索引与规范，不写生成文件。build_ai_guide.py在打包时把已声明的仓库路径转换为ZIP内部路径；修改入口后同时核对源码链接、任务/字段查询和独立ZIP，不能只检查解压包。

发布用户资料由 `tools/build_ai_guide.py` 从 `Docs/AI/inputs.lock.json` 锁定的公开手册、Schema与合成示例生成；不使用内部索引作应用侧入口。Current HTML与wheel通过同一生成器构建，`package_current_docs.py` 发布前拒绝过期ZIP。在新产品版本统一校核手册时，用 `python -B tools/lock_ai_inputs.py <已审核手册提交> --runtime <已审核产品提交> --device-label <实测标签>` 显式刷新冻结输入，再审阅差异；正式wheel要求整个运行源码/模板树匹配，不因相同包版本或签名而放过语义变化。不要为消除校验失败而随意重锁。按功能或阶段交付检查导入、字段原始位置和样本运行，不逐次重写用户手册。

从干净检出构建wheel；运行 `tests/ai_release/check_bundle.py` 检验独立资料，`tools/verify_ai_distribution.py` 验证sdist到wheel、直接阅读和可选导出，`tools/check_ai_install.py` 在无源码检出的新环境复验随包案例。独立模型评测和程序检验分别保存结果。

修改源码docstring或人工注解后重新生成，不能只编辑生成页。公开构造签名清单应与对应基线的实际Python接口核对；所有类成员、参数、返回和异常仍需阅读校核。HTML隐藏变更履历，源码Markdown保留历史来源。内部参考、冻结vendor与公开入口分别组织。

静态覆盖、链接检查和查询测试只能证明对应结构与算法；不能替代浏览器的视觉、键盘、剪贴板操作，也不能替代完整示例执行和用户试读。_build为可再生交付目录，不提交Git；新检出仓库需重建。

## 中英文资料同步

当前构建同时生成中英文HTML、导航和搜索。英文手册位于`Docs/Current/en/`，英文AI资料位于`Docs/AI/en/`；同一AI包以`en/README.md`提供英文入口，资料修订3包含两种语言。示例输入、配置、结果和Schema共用，不维护另一套英文数据。

每次代码更新检查相关中英文手册、AI说明和README：公开API、CLI、字段/默认值、输入输出、时间/质量语义、依赖、诊断或示例变化时同步对应说明；仅内部实现变化且不影响使用时记录无需修改的依据。机器值和实际结果保持原样，不能用英文摘要替代完整参考。

先运行`python -B tools/english_docs.py --references-only`生成英文字段参考，再逐页核对受影响的来源与译文，包括参数、默认值、单位、边界、示例结果和链接。实际审阅后才运行`python -B tools/english_docs.py --record-reviewed`保存来源/译文摘要。普通`python -B tools/english_docs.py`检查已登记来源是否变化；出现差异须复核译文，不能仅刷新摘要。中英文HTML与AI包沿完整功能或阶段交付点统一重建和验证。

## 指南普通文件交付

`build_ai_guide.build_files()`组装同一套已审核资料。wheel安装到`chronaxis/guide`，HTML附带`ai-guide`目录；`python -m chronaxis guide`只定位README，`--language en`选择英文，可编辑安装直接定位Docs/AI。ZIP是按需独立副本，由同一文件集合生成。

校核安装目录、HTML目录、相对链接、两种语言和可选ZIP的内容一致；直接使用安装目录的输入运行示例，输出放外部工作目录，核对安装资料没有被改写。覆盖缺资源和拒绝覆盖情形。只通过ZIP导出测试不能证明可直接阅读。

## PyPI页面链接

源码README继续使用相对文件链接，便于离线阅读。`setup.py`在构建元数据时通过`tools/pypi_readme.py`生成PyPI正文，依据`pyproject.toml`中的Repository和版本，将文件链接转为对应GitHub版本标签下的网页地址；不保存第二份正文、不改代码围栏或原README。公开源码与sdist必须包含此工具。更换仓库或版本后核对实际wheel的Project-URL、正文链接和对应文件；远端标签需在上传PyPI前公开可访问。
