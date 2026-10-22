# 给现有工程提供 Agent 辅助的 GitHub 项目调研

调研日期：2026-10-16（Asia/Shanghai）。
交付状态：完成公开源码抽查、维护与许可核实、指定提交的远程 CI 元数据核验；**未安装、未本机运行、未调用模型、未证明效果或成本优势**。
覆盖：6 类代表性方案、7 个仓库；OpenHands 主仓与 SDK 作为一个项目族。
本轮仅新增本报告，不修改原设计或项目规则，不继续实现原“测试失败调查 Agent”。

## 1. 结论与阅读顺序

值得研究现有工具怎样增强一个工程，而不是先决定自研一个完整 Agent。调研后，最值得优先研究的方向是：

1. **工程上下文准备：Repomix。** 与“整理材料、控制输入范围”最直接相关，已有真实实现、测试和对应 CI。先验证它是否已经满足需求，再考虑自研任务定向选择器。
2. **工程工作流：Spec Kit。** 把规格、计划、任务及缺陷处理接入现有编码助手，适合研究流程如何复用；其价值要扣除文档维护与操作成本。
3. **代码定位工具：Serena。** 适合研究按需读取、符号定位、引用搜索和项目配置；使用成本、语言服务器行为和当前许可需要单独评估。
4. **代码修改协作：Aider。** Repo map 和上下文选择值得读，但本次可见维护间隔、失败 CI 及有写入副作用的默认行为，使其更适合作为有条件参考。
5. **自建执行系统：OpenHands SDK。** 工程结构与验证证据充分，适合深入学习 Agent 的事件、工作区与确认策略；对个人“小工具”目标偏重。
6. **IDE 接入：Continue。** 有历史工程价值，但 README 已声明不再积极维护，不作为当前新的长期接入基础。

这里的优先级来自用户当前“给已有工程增加辅助”的需求与接入成本判断，**不是功能强弱排名，也不是准确率排名**。没有任何候选在本轮获得“本机安装准入通过”或“生产环境安全通过”。

## 2. 范围、方法及质量标准

### 2.1 调研问题

对象是能增强现有项目的工具：上下文准备、代码检索、编码协作、工作流和执行基础设施。重点回答：

- 它为现有工程承担什么工作，是否已有实质代码？
- 测试是否核对行为和边界，CI 是否真的执行相关检查？
- 当前维护状态、许可、安装与运行副作用是否清楚？
- 对个人开发者/测试工程师有没有可验证的使用理由？
- 适合使用、参考、局部复用，还是应暂缓？

本轮不以“是否像原失败调查项目”作为筛选条件；不以 Star、截图、宣传语、模型自报置信度或功能数量判定质量。选择代表性项目而非穷尽 GitHub；未入选不意味着质量不合格。

方法：先检索官方仓库，再通过 GitHub 只读接口取得默认分支提交与目录树，按固定提交读取 README、许可、清单、部分实现、测试和 CI；远程工作流结论与该提交 SHA 对齐。没有克隆仓库、运行远程脚本、读取活凭据或向第三方提交工程内容。

### 2.2 “达标”分成三个门槛

| 门槛 | 本报告判定方式 | 不代表 |
| --- | --- | --- |
| 工程参考达标 | 来源与许可可核对；存在实质实现；抽查测试有真实行为/错误路径；有 CI 配置及对应结果，或明确列出缺口 | 全仓代码均好、测试覆盖充分、没有漏洞 |
| 新选型候选 | 在工程参考基础上，维护与适用场景可接受，接入负担和权限可解释 | 已批准安装、依赖供应链已完整审计 |
| 本机可用/效果达标 | 需要隔离试用、实际任务对照、依赖与副作用检查 | 本轮不判通过 |

每项判断标记为“已核实事实”“分析判断”或“待验证”。重要证据不足时写“有条件/未验证”，不用一个加权分数掩盖硬缺口。

### 2.3 六个检查维度

| 维度 | 检查点 | 否决/降级条件 |
| --- | --- | --- |
| 来源与许可 | 官方 owner、实际 LICENSE、组件差异 | 找不到明确许可或无法确认来源，不建议代码复用 |
| 实现与结构 | 入口、核心数据流、配置与副作用 | 只见演示/模板，却宣传完整执行系统；类型不匹配 |
| 测试与 CI | 正常/边界样本、工作流实际命令、精确 SHA 的运行和 job 状态 | 仅有测试目录、未执行、跳过或失败被说成通过 |
| 维护 | 默认分支最近提交、明确维护声明、版本变更 | 停止维护则不选作新长期基础；长期无更新需补兼容性证据 |
| 权限与供应链 | 读写/命令/网络/安装、可执行配置、hooks、隔离语义 | 把提示词、read-only 标签或工具注册当安全沙箱 |
| 用户价值 | 具体减少哪种工作、什么任务适用、有没有比较证据 | 仅凭架构复杂或摘要更短就声称更快/便宜/准确 |

本轮检查了关键清单和部分入口的安装/运行行为，**没有完成所有传递依赖、发布包内容、postinstall 或全部网络路径审计**。因此本报告不能代替用户全局规则要求的安装前尽调。

## 3. 调研快照与维护状态

以下是查询时默认分支可见的最新提交；时间转换为北京时间。报告内代码链接均绑定这些 SHA。分支或发布包之后可能变化；默认分支源码不等同于已发布版本。

| 仓库 | 固定提交 | 提交时间（+08:00） | 核实的许可/维护说明 |
| --- | --- | --- | --- |
| yamadashy/repomix | [55c6de6](https://github.com/yamadashy/repomix/commit/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d) | 2026-10-11 23:58:43 | MIT；清单版本 1.18.1，Node.js ≥22 |
| oraios/serena | [d9e4c79](https://github.com/oraios/serena/commit/d9e4c796fae0207ba6848d1df4b331122a5567b5) | 2026-10-16 03:39:53 | 应用 GPL-3.0-or-later；SolidLSP MIT；刚经历 v2 变更 |
| Aider-AI/aider | [5dc9490](https://github.com/Aider-AI/aider/commit/5dc9490bb35f9729ef2c95d00a19ccd30c26339c) | 2026-05-22 22:02:20 | Apache-2.0；本次默认分支近五个月未见新提交，不推断所有开发停止 |
| continuedev/continue | [5522c6f](https://github.com/continuedev/continue/commit/5522c6f44ca0ac3528b37244818fbfa39b5af470) | 2026-07-21 12:00:09 | Apache-2.0；README 声明不再积极维护 |
| OpenHands/OpenHands | [8238b7a](https://github.com/OpenHands/OpenHands/commit/8238b7af825b8639191b9d7b4c6b080d4a93f388) | 2026-10-16 14:49:42 | 根 LICENSE 为 MIT；主仓当前以 Agent Canvas/接入层为主 |
| OpenHands/software-agent-sdk | [5fa4dea](https://github.com/OpenHands/software-agent-sdk/commit/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2) | 2026-10-16 09:58:41 | MIT；SDK 清单版本 1.55.1、Python ≥3.12 |
| github/spec-kit | [f6e72bc](https://github.com/github/spec-kit/commit/f6e72bc8523de8ec8368129cbdea78d45f27cef8) | 2026-10-16 02:57:23 | MIT；Python ≥3.11，现有 CLI、集成与可选扩展 |

所有仓库元数据的 archived 字段在本次查询中均为 false。**Continue 的维护声明与 archived=false 并不矛盾：平台没有归档，不等于维护者继续维护。**

维护活跃只能增加可持续性信心，不证明代码正确；更新频繁也可能带来接口和许可变化。Aider 的维护间隔是补充核验理由，不是“项目已死”的证据。

## 4. 质量与适用性总表

| 项目族 | 工程参考是否达标 | 当前新选型判断 | 对个人最有价值的内容 | 关键限制 |
| --- | --- | --- | --- | --- |
| Repomix | 达标，有源码/边界测试/对应 CI；Windows 个别边界未执行 | 优先进入受控试用候选 | 文件选择、输出格式、token 预算与安全扫描链路 | 整仓打包不等于任务相关性；可执行配置；预算检查在输出生成后 |
| Serena | 达标；抽查读取/搜索/越界测试，CI 有实测记录 | 有条件候选 | 项目注册、语义取证、工具配置与信任边界 | LSP 下载/执行成本；REPL 与 read-only 的限制；应用许可变化 |
| Aider | 有条件达标；核心算法和测试值得学，CI 有失败项 | 暂缓成为新方案主依赖 | Repo map、符号图排序、缓存与上下文选择 | 当前维护间隔；Docker CI 失败原因未证实；默认自动提交 |
| Continue | 历史工程参考有价值；当前维护门槛未达标 | 不作为新长期基础 | IDE/CLI 接入、权限规则、压缩及测试组织 | 明确不再积极维护；当前构建/检查失败；模式名不能代替权限检查 |
| OpenHands + SDK | SDK 工程参考达标；主仓仅做架构/许可/运行说明抽查 | 当前轻量目标暂缓，框架研究可优先读 SDK | 事件、工作区、工具、会话与确认策略分层 | 组件/依赖多；本地无沙箱模式可访问文件系统；确认策略不等于隔离 |
| Spec Kit | 达标；下载/解包安全实现和反例测试、跨平台 CI | 工作流目标下可进入候选 | 将规格、计划、任务与缺陷流程附加到已有助手 | 会写入项目资产并可运行 hooks；模板流程不是运行时权限边界 |

“优先候选”只是下一轮试用顺序，不是安装指令。本轮不宣布任何工具提高准确率、节省 API 调用或节省固定比例的费用。

## 5. 逐项目分析

### 5.1 Repomix：最贴近上下文准备，但通用打包与任务选择不同

**用途。** 把选定工程文件整理为模型可消费的输出，支持忽略/包含规则、结构压缩、token 统计及 MCP 等入口。主要减轻材料收集和格式整理。

**已核实的工程证据。**

- 核心 pack 流程组织文件发现、读取/处理、安全过滤与输出；配置和工具层分开。见 [pack 实现](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/src/core/packager.ts)。
- token 预算检查有独立函数与 CLI 调用测试，覆盖超限拒绝；对应源码是对已计算总量进行检查，并非先自动挑出最相关材料。见 [预算检查](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/src/cli/cliTokenBudget.ts)、[预算行为测试](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/tests/cli/actions/defaultAction.tokenBudget.test.ts)。
- 有真实文件系统符号链接反例，检查路径落在根外的文件不会出现在结果中。见 [真实链接反例](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/tests/core/file/fileSearchConfineSymlink.test.ts)。
- [CI 配置](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/.github/workflows/ci.yml)执行类型、lint、测试及跨平台构建；本次固定提交的 [CI 38153526263](https://github.com/yamadashy/repomix/actions/runs/38153526263) 为 success，已检查 job/step 元数据，相关测试步骤实际为 success。

**具体限制。**

1. 符号链接反例的 beforeEach、afterEach 和测试体在 win32 直接 return。这证明该测试在 Windows 没有执行相关断言；不能把 Windows CI 的绿色状态扩大为此路径边界已验证。本轮未运行 Windows junction/symlink 探针，也不泛化为所有路径测试均缺失。
2. [配置加载](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/src/config/configLoad.ts#L146)对 TS/JS 配置使用 jiti 导入，会执行配置代码。README 对远程仓库配置有信任开关；本地工程配置也需要审查，不能把“打包源码”理解成必然只做文本读取。
3. README 明确 token-budget 超限仍产生输出，随后通过非零状态表示超限。调用方必须检查状态，不能继续自动上传已生成的过大输出。见 [预算与 sandbox 参数](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/README.md#L675)。
4. [包清单](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/package.json)有 prepare/build 脚本，构建重写 lib；源码安装和发布包安装行为尚未比较，传递依赖未完整审计。扫描器不能保证发现所有秘密。
5. 结构压缩可能省 token，也可能删除异常分支或断言关联细节；需要看任务结果。整个仓库结构摘要不能替代必要函数原文。

**分析判断。** 代码与质量流程达到“值得参考/进入小范围试用”的门槛。对当前上下文准备方向，应该先用它作现成基线；若任务定向选择没有比人工选择加 Repomix 更省事，重复实现整仓打包没有充分价值。

**待验证。** 本机 Node/Windows 兼容性，固定发布包行为、输出路径、新旧输出覆盖策略、实际秘密扫描误报/漏报、断言与异常路径保留度、整个调查的实际模型用量。不能从 token 统计直接推导 API 账单或调用次数。

### 5.2 Serena：适合代码定位研究，不能将工具限制等同于隔离

**用途。** 为已有助手提供代码检索与编辑能力，按项目配置接入；适合大型工程中定位符号、查引用和按需读取。

**已核实的工程证据。**

- [文件 API](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/src/serena/repl/api/fs_api.py#L181)在读取/搜索前使用项目路径验证；[文件 API 测试](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/test/serena/repl/api/test_fs_api.py)核对行片段、搜索结果、代码过滤及创建路径越界。该样本不是对所有读路径的完整安全审计。
- [开发与依赖配置](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/pyproject.toml)明确测试、格式、类型检查任务；[分批跨平台 CI](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/.github/workflows/pytest.yml)按语言/平台分批，并包含明确的跳过/排除口径。
- 固定提交的 [Tests 38795744692](https://github.com/oraios/serena/actions/runs/38795744692) 为 success，13 个 job 均成功，pytest 步骤为 success；部分依赖安装步骤按批次 skipped，不解释成对应语言在所有平台均已测试。
- [变更记录](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/CHANGELOG.md#L1)在本次 main 快照说明了项目本地 TypeScript 加载与链接路径方面的修复；其位于 Unreleased 部分，不能推断所有正式发布包已包含修复。

**具体限制。**

- [安全模型](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/docs/02-usage/070_security.md)明确：REPL 接受 Python 代码执行；禁用某类 API 或 read_only 不阻止任意代码通过其他方式写文件。工具接口与 REPL 接口的可强制边界不同。
- LSP 后端会按需获取依赖。只读检索功能可能伴随语言服务器安装和进程执行；官方说明列出版本固定、哈希和下载主机约束，但本轮未逐个审计下载器或所有语言。
- 当前 [组件许可](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/LICENSE)将 Serena 应用与 SolidLSP 分别许可。应用 GPL-3.0-or-later，SolidLSP MIT；不能依据旧版印象把当前全部代码当 MIT 直接复用。
- 项目配置、内存、缓存和日志增加接入负担；跨项目共享上下文也要考虑误关联。它不是只加一个轻量文本文件就完成的集成。

**分析判断。** 用于研究“让已有 Agent 更会找代码”有价值；对只涉及两个源码片段的小案例可能得不偿失。首次试用应只选择一个受信工程、必要工具及一种语言，比较原助手的原生搜索，不一次启用编辑、shell、REPL、全语言和自动记忆。

**待验证。** 语言服务器的实际下载/启动范围、本机权限、项目切换和中文路径、索引耗时、缓存磁盘增长，以及符号检索是否减少整个任务的读取和模型用量。

### 5.3 Aider：Repo map 值得读，作为当前主依赖须谨慎

**用途。** 与模型协作修改代码、利用 Git 组织变更、运行 lint/test；Repo map 是降低工程理解成本的一种现成设计。

**已核实的工程证据。**

- [Repo map 实现](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repomap.py)含符号抽取、图排序（包括 PageRank）、缓存与 token 预算内的输出选择。[Repo map 测试](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/tests/basic/test_repomap.py)覆盖刷新、符号、排除已加入文件及多语言样例。
- [算法说明](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/docs/repomap.md)解释符号/引用图如何影响上下文选择；这是机制说明，不是本轮验证的节省比例。
- 固定提交的 [Ubuntu Python Tests](https://github.com/Aider-AI/aider/actions/runs/26292338906)、[Windows Python Tests](https://github.com/Aider-AI/aider/actions/runs/26292338945) 为 success；[Docker Build Test](https://github.com/Aider-AI/aider/actions/runs/26292338794) 为 failure。本轮检查了失败 job 元数据，但没有日志支持根因判断。
- [默认参数](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/args.py#L439)中 auto-commits 与 dirty-commits 默认 True，auto-lint 默认 True，而 auto-test 默认 False。自动提交/有 diff 不证明测试通过或修复成立。

**维护与限制。**

- 本次默认分支 HEAD 时间为 2026-05-22。2026-10-16 仍有定时任务在跑，但其中包括 PyPI 版本检查和 issue 自动处理；**工作流活动不能代替源码维护活动**。
- 不把近五个月无默认分支更新直接解释成停止维护；近期模型/API、依赖与 Windows 兼容性尚无本轮实测证据。
- 它具有修改、命令和 Git 副作用。[打包清单](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/pyproject.toml)从 requirements 动态读取依赖，完整安装链没有审计，不能未经审查直接挂到摄像头原仓库。
- Repo map 是符号层面的缩减；一些根因依赖函数体细节、动态行为或输入数据，需要继续读原文。

**分析判断。** 作为上下文选择算法和完整编码工具的研究对象有价值，工程参考“有条件达标”。当前不优先选作新小工具的强依赖。可独立学习思想，再以现有 Agent 的搜索/文件选择为基线，不能因已有 repo map 就假定更准确。

### 5.4 Continue：历史实现有价值，当前不满足新长期基础的维护要求

**用途。** 提供 CLI/编辑器接入、模型配置、上下文与工具调用。

**已核实的事实。**

- 固定提交 [README](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/README.md#L19)明确声明不再积极维护，并说明 final 2.0.0。平台 archived=false 不能否定这个声明。
- [权限实现](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/extensions/cli/src/permissions/defaultPolicies.ts)和[对应测试](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/extensions/cli/src/permissions/defaultPolicies.test.ts)展示规则顺序与权限策略。普通模式写工具要求 ask；headless 的 Bash/兜底策略为 allow；Plan 模式排除显式写工具，但 Bash 和兜底仍为 allow。
- [CLI CI](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/.github/workflows/cli-pr-checks.yml)有多平台 smoke/e2e 流程，但明确排除 Windows e2e，注明 Windows 输出刷新相关问题；不能称为全平台端到端验证。
- 固定提交 [Main Branch Build 29800025075](https://github.com/continuedev/continue/actions/runs/29800025075) 和 [PR Checks 29800025067](https://github.com/continuedev/continue/actions/runs/29800025067) 为 failure。已读 Main Branch Build 的 job 元数据，失败步骤为 Find PR workflow run，涉及制品重发布查找；**不能据此声称核心 Agent 功能已坏**。

**分析判断。** 维护门槛未达标，因此不推荐作为新长期接入基础。权限配置、接入分层和历史测试仍有研究价值。上述源码策略并不等价于最终执行链的完整权限结论；尤其不能依据“Plan”名称推断所有操作只读。需要进一步追踪执行器才能判断可绕过范围。

本轮没有完整取到 core 子树清单，抽查集中在 extensions/cli；不能把结果扩大为全仓代码审查。之前网页上的工具权限概述与当前快照源码存在值得继续核对的口径，报告采用实际读取的代码，保留未知部分。

### 5.5 OpenHands 主仓与 SDK：适合研究执行系统，轻量目标应控制范围

**用途。** 自建 Agent 会话、工具执行、工作区和接入/自动化系统。

**已核实的结构。**

- 当前 [主仓架构说明](https://github.com/OpenHands/OpenHands/blob/8238b7af825b8639191b9d7b4c6b080d4a93f388/README.md#L146)把 Agent Canvas、SDK/Agent Server、TypeScript client 和 automation 分开；不能照搬旧版“主仓就是全部 Python runtime”的路径认知。
- [SDK 职责说明](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/README.md#L83)把 agents/tools/conversations/workspaces/events 与服务端 API 放在 SDK 仓库。主仓与 SDK 是分别固定的独立快照，本轮未验证二者发布版本组合。
- [确认策略](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/openhands-sdk/openhands/sdk/security/confirmation_policy.py)提供 AlwaysConfirm/NeverConfirm/ConfirmRisky；[策略测试](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/tests/sdk/security/test_confirmation_policy.py)核对风险输入和序列化。策略类的存在不能证明所有入口都强制确认，也不能代替 OS 隔离。
- [测试工作流](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/.github/workflows/tests.yml)检查测试目录纳入范围、按 SDK/tools/workspace/server 等执行，并将部分 live/stress 测试分开。
- 固定 SDK 提交 [Run tests 38838007558](https://github.com/OpenHands/software-agent-sdk/actions/runs/38838007558) 为 success；job 元数据显示 Windows、SDK、tools、workspace、server、live ACP 等相关步骤成功，coverage-report job skipped。不据此编造测试用例总数或覆盖率。另一个 Agent Server 工作流在查询时仍 in_progress，不称为全部工作流已绿。

**接入成本与限制。**

- [运行方式](https://github.com/OpenHands/OpenHands/blob/8238b7af825b8639191b9d7b4c6b080d4a93f388/README.md#L63)区分无沙箱、Docker 与多沙箱配置，明确无沙箱方式直接访问主机文件系统。容器方案仍须检查挂载、凭据、网络和权限，不能只看“Docker”字样。
- [SDK 依赖](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/openhands-sdk/pyproject.toml)需要 Python ≥3.12，依赖含 LiteLLM、FastMCP、Pydantic 等；对原本只需一个供应商和三个读取函数的目标偏重。
- 安装与启动可能写状态、拉镜像/依赖、启动服务和执行代码；本轮未执行，也未核实本机全部组件兼容。
- 主仓本轮只抽查 README、许可和目录架构，实质实现/测试审查重心在 SDK，不能合并宣称整个 OpenHands 栈均已通过代码审查。

**分析判断。** SDK 的工程参考达标，适合学习执行与状态分层；如果目的只是给现有助手整理上下文，采用全套系统会增加不必要的维护工作。只有明确要做持久会话、远程执行或统一工作区时才值得进入更深入选型。

### 5.6 Spec Kit：给既有 Agent 增加工作流，不负责保证推理正确

**用途。** 通过 CLI、模板、集成与扩展把需求、规格、计划、任务、缺陷处理等流程接入已有助手。

**已核实的工程证据。**

- 当前 [工作流与可选扩展](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/README.md#L25)将规格开发、缺陷修复、评估作为不同入口，不要求每个任务都完整执行全部阶段。不能只按旧版“几个 Markdown 模板”概括当前代码。
- [打包与测试配置](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/pyproject.toml)提供 CLI 入口与 bundled assets，包含 Bash/PowerShell/Python 脚本及扩展；并有 subprocess 安全相关 lint 规则。
- [受限下载与解包](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/src/specify_cli/_download_security.py)含下载大小、URL、文件名、路径/归档验证；[安全反例测试](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/tests/test_download_security.py)实际覆盖过大响应、短读取、错误类型等情形。
- [初始化入口](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/src/specify_cli/command_init.py)对 URL 扩展做信任确认并处理初始化选项；这仍是会写入工程的安装/生成器，不是无副作用的只读工具。
- 固定提交 [Test & Lint Python 38789910977](https://github.com/github/spec-kit/actions/runs/38789910977) 为 success，已核查六个 OS/Python 测试 job 和 Ruff job；脚本型测试有平台条件，不能外推本机全部行为。

**内容是否有价值。**

[缺陷评估模板](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/extensions/bug/commands/speckit.bug.assess.md)具体规定了输入核对、可疑代码定位、未知事项、修复建议与输出位置，并区分未复现的判断。这比空泛“你是专家，请修复”更可操作。但：

- 它主要指导宿主 Agent 采用流程，不能靠模板确保事实正确。
- 扩展 hooks 可能触发命令；项目生成资产与 hooks 应先审查。
- 对小 typo/简单断言，完整流程可能比直接提问更慢。
- 下载/解包防护不代表安装后的扩展行为可信，也不保证模型不会执行不该执行的操作。

**分析判断。** 工程参考达标；若你的困难是 Agent 漏需求、跳验收、反复解释步骤，它比再写一个聊天入口更有价值。若困难只是日志太长，Spec Kit 不能直接代替上下文选择器。试用应限定一个轻工作流，记录返工减少是否抵得过文档与操作成本。

## 6. 远程 CI 核验汇总

本表只记录查询时 GitHub API 对固定提交返回的状态与本轮抽查，不是本机复跑结果。没有下载完整日志/制品或核对逐用例结果，故不报告全量用例数或无跳过保证。

| 项目/提交 | 对应工作流 | 已核实状态 | 判断边界 |
| --- | --- | --- | --- |
| Repomix 55c6de6 | [CI 38153526263](https://github.com/yamadashy/repomix/actions/runs/38153526263) | success；29 个 job 的元数据已取得，含实际测试步骤 | 部分 Windows 真实链接测试通过代码直接 return，没有执行断言 |
| Serena d9e4c79 | [Tests 38795744692](https://github.com/oraios/serena/actions/runs/38795744692) | success；13 个 job，pytest 步骤成功 | 语言/安装步骤按批次和平台有跳过，不是全语言全平台全覆盖 |
| Aider 5dc9490 | [Ubuntu Tests](https://github.com/Aider-AI/aider/actions/runs/26292338906)、[Windows Tests](https://github.com/Aider-AI/aider/actions/runs/26292338945) | 两工作流 success（2026-05） | 未抽取这两条全部 job/逐测试日志；不代表当前依赖可安装 |
| Aider 5dc9490 | [Docker Build Test](https://github.com/Aider-AI/aider/actions/runs/26292338794) | failure；失败 job 为 docker_build_and_push | steps 元数据未给出可归因的失败步骤，根因未查明 |
| Continue 5522c6f | [Main Branch Build](https://github.com/continuedev/continue/actions/runs/29800025075)、[PR Checks](https://github.com/continuedev/continue/actions/runs/29800025067) | failure | Main Build 的制品查找步骤失败；不是核心功能坏掉的证明 |
| SDK 5fa4dea | [Run tests 38838007558](https://github.com/OpenHands/software-agent-sdk/actions/runs/38838007558) | success；10 job 中 coverage-report skipped，其他 job 成功 | 不等于整个 OpenHands 栈/发布组合验证完成；另有 Server workflow 查询时进行中 |
| Spec Kit f6e72bc | [Test & Lint 38789910977](https://github.com/github/spec-kit/actions/runs/38789910977) | success；Ruff 与六个 pytest job 成功 | 使用 Python 3.13/3.14 的矩阵，不能拿来证明本机 Python 3.12 已实测 |

定时 issue 管理、标签、文档部署、版本检查的 success 不替代测试 success。一次失败也不能省略失败阶段直接判为“产品不可用”；一次 success 同样不能判为“安全无漏洞”。

## 7. 对个人工程真正有价值的组合

本节为分析判断，未经过本机对照。

| 实际困难 | 优先研究/验证 | 不急着增加 |
| --- | --- | --- |
| 经常手工挑文件、粘日志和拼工程上下文 | Repomix 的选取/输出；必要时自研少量任务定向选择规则 | 完整 Agent runtime、多供应商路由 |
| 助手经常读错模块、需要定位定义与引用 | Serena 的代码工具；与宿主原生搜索直接比较 | 全语言 LSP、REPL、编辑工具全部开启 |
| 需求变更后经常漏约束、漏验收 | Spec Kit 的一个轻量工作流 | 把所有任务强制变成长规格流程 |
| 希望研究符号图与上下文预算 | Aider Repo map 的实现与测试 | 为了一个算法引入整个可写编码工具 |
| 要自建远程执行、会话状态与权限确认系统 | OpenHands SDK 的事件/工作区/策略模块 | 直接复制全套 Web/桌面/自动化架构 |
| 要研究 IDE 接入的历史设计 | Continue 的 CLI/IDE/权限组织 | 在停止积极维护的基础上承担新长期集成 |

具体到原项目思路：

- “将工程打包给模型”已有现成实现，不能仅凭这件事建立差异化。
- “按失败任务挑必要材料，并保留断言/异常链/原始行号”仍是可验证的窄问题，但要先与现成工具加人工选择、宿主 Agent 原生检索比较。
- “有序流程减少漏项”与“上下文更短”是不同问题，应分别选择工作流和材料工具，不自动塞进同一个产品。
- 没有必要为继续做项目而强行自研；如果现成工具足够，使用它们并把投入放在实际工程任务上也是合理结果。

## 8. 下一轮试用应验证什么

本轮只调研；以下不是已执行成果，也不是安装授权。先选一个真实痛点和一个候选，不同时安装全部。

### 8.1 上下文准备（建议第一优先）

同一个受信工程、同一任务、同一模型/宿主及读取权限，对比：

1. 原始日志/任务直接给现有助手，让它按正常方式读取工程。
2. 人工选择必要材料后用 Repomix 整理，再交同一助手。
3. 若第二条仍有明显人工负担，再验证少量任务定向自动选择规则。

记录材料准备时间、人工操作、整个调查用量/调用、关键证据保留、错误归因与后续补读。预处理 token 减少不等于总成本减少；宿主用量不可见时，不报告 API 省钱比例。

失败标准包括：省掉必要断言或异常路径；生成过大输出而调用方未拒绝；助手重复读取相同文件；材料准备比直接提问更麻烦；最终质量下降。小样本用于淘汰方向，不对外宣称统计优势。

### 8.2 代码定位

用一个存在跨模块调用的真实问题，比较宿主原生搜索与 Serena 工具：是否更快定位必要符号、少读无关文件、减少错误位置；同时记录安装/索引/首次语言服务器下载和后续热运行成本。不能只计工具调用响应时间。

### 8.3 工作流辅助

同等复杂度的小变更，比较原有对话方式与 Spec Kit 单工作流：约束遗漏、返工、验收遗漏和维护文档的人工时间。资料更多不是自动成功标准；如果流程没有减少遗漏，就保留原工作方式。

### 8.4 本机试用前仍需核查

- 固定发布版本与本报告 SHA 的关系、发布包内容、依赖锁与安装脚本，尤其动态下载器、prepare/postinstall、hooks。
- 文件/目录写入、输出覆盖、缓存与日志位置；新增大体积数据按用户规则安排到 D 盘。
- 网络目的地、遥测与凭据传递；不关闭 TLS、不要求粘贴 Key、不在报告记录密钥。
- Windows/中文路径、junction/symlink，以及所选权限模式是否实际达到要求。
- 在审查过的新副本中做运行时冒烟和行为/错误反例；副本和 .venv 不是安全沙箱。
- 许可核实到具体组件；本报告只记录文件声明，不替代商业再分发场景的专业判断。

## 9. 已知缺口与调研失败记录

- 未本机安装或执行任何候选；没有实际准确率、速度、费用、稳定性或用户采用证据。
- 未全面审查全部源码、所有依赖、发布包、完整网络行为和所有安全公告；静态抽查不能证明没有漏洞。
- Continue core 子树未成功取得；其 CLI 样本不代表全仓。部分网页检索结果可能滞后，所以主要结论改用固定 SHA 的文件与 API 数据。
- 精确 workflow 文件名的 API 路径被连接器拒绝为不在公开接口白名单内。随后使用允许的仓库 actions/runs 查询，按 head_sha/event 筛选，并读取对应 jobs；没有扩大工具权限或绕过访问控制。
- Aider Docker 失败与 Continue PR Checks 的完整根因未核实，保留失败状态而不猜原因。
- 远程 CI 元数据来自 GitHub，非本轮独立复验；job 成功不能推出测试无跳过，不能推出当前发布包/本机兼容。
- 同一日主仓与 SDK 分别查询到的 HEAD 不保证互相兼容；需试用时固定实际版本组合。
- 维护判断只针对本次本地可见默认分支和已读声明，不覆盖所有分支、私有开发、其他分发渠道或未来版本。
- 没有向作者提问、提交 issue/PR、安装 skill/plugin/MCP、创建其他聊天或委派子代理。

## 10. 证据索引与报告核验

### 10.1 固定版本的主要资料

每个项目至少保留实现、测试/CI与许可入口，便于复查。代码行号是本次快照的一部分，修改版本后不能直接复用。

| 项目 | 主要已读资料 |
| --- | --- |
| Repomix | [README](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/README.md)；[清单](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/package.json)；[实现](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/src/core/packager.ts)；[配置加载](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/src/config/configLoad.ts)；[路径反例](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/tests/core/file/fileSearchConfineSymlink.test.ts)；[预算反例](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/tests/cli/actions/defaultAction.tokenBudget.test.ts)；[CI](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/.github/workflows/ci.yml)；[MIT](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/LICENSE) |
| Serena | [安全模型](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/docs/02-usage/070_security.md)；[清单](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/pyproject.toml)；[文件接口](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/src/serena/repl/api/fs_api.py)；[接口测试](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/test/serena/repl/api/test_fs_api.py)；[CI](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/.github/workflows/pytest.yml)；[维护记录](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/CHANGELOG.md)；[组件许可](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/LICENSE) |
| Aider | [README](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/README.md)；[Repo map](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repomap.py)；[算法测试](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/tests/basic/test_repomap.py)；[默认副作用](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/args.py)；[Windows CI](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/.github/workflows/windows-tests.yml)；[Linux CI](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/.github/workflows/ubuntu-tests.yml)；[Apache-2.0](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/LICENSE.txt) |
| Continue | [维护声明](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/README.md)；[权限策略](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/extensions/cli/src/permissions/defaultPolicies.ts)；[策略测试](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/extensions/cli/src/permissions/defaultPolicies.test.ts)；[CLI CI](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/.github/workflows/cli-pr-checks.yml)；[Apache-2.0](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/LICENSE) |
| OpenHands | [主仓结构/运行](https://github.com/OpenHands/OpenHands/blob/8238b7af825b8639191b9d7b4c6b080d4a93f388/README.md)；[主仓 MIT](https://github.com/OpenHands/OpenHands/blob/8238b7af825b8639191b9d7b4c6b080d4a93f388/LICENSE)；[SDK 结构](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/README.md)；[SDK 依赖](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/openhands-sdk/pyproject.toml)；[策略实现](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/openhands-sdk/openhands/sdk/security/confirmation_policy.py)；[策略测试](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/tests/sdk/security/test_confirmation_policy.py)；[SDK CI](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/.github/workflows/tests.yml)；[SDK MIT](https://github.com/OpenHands/software-agent-sdk/blob/5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2/LICENSE) |
| Spec Kit | [入口说明](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/README.md)；[清单](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/pyproject.toml)；[初始化](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/src/specify_cli/command_init.py)；[下载边界](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/src/specify_cli/_download_security.py)；[反例](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/tests/test_download_security.py)；[缺陷流程](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/extensions/bug/commands/speckit.bug.assess.md)；[CI](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/.github/workflows/test.yml)；[MIT](https://github.com/github/spec-kit/blob/f6e72bc8523de8ec8368129cbdea78d45f27cef8/LICENSE) |

### 10.2 本轮文档核验口径

交付为本文件一个新增 Markdown；原 AGENTS.md 和 docs/design-v0.md 保持原字节，不更新配置，不提交或创建分支。核验固定 SHA、已读文件路径、CI head_sha 对应、链接/围栏/编码、Git 状态及新增文件 diff；原文件前后 SHA-256 对照。

项目没有本轮新增业务实现，因此不运行 build/test/lint/type-check 或摄像头测试。候选项目的远程 CI 被明确列为“查阅到的远程结果”，不能称为本轮本机测试通过。试用和产品效果均留到后续明确任务。
