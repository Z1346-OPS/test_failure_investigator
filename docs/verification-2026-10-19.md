# 2026-10-19 反馈归属与文案断言修正验证记录

日期：2026-10-19（Asia/Shanghai）。范围：修复 Codex 审核发现的两项问题，并补齐本轮新增流程的
验证。历史设计、旧验证报告（`verification-2026-10-18.md`）与计划原文保持原样。

本文件只记录本轮实际执行结果；作者自测与合成材料不等于用户试用或产品验收。

## 0. 起点与备份

- 项目根：`D:\AIProjects\projects\test_failure_investigator`；分支 `main` 尚无首次提交，
  全部文件未跟踪，空 `git diff` 不能证明没有变化。
- 修改前基线：单元测试 75 项 OK；GUI 冒烟 83/83，退出码 0。
- 修改前单文件备份与摘要：`backups/2026-10-19_15-32/`（`MANIFEST.txt` 为 SHA-256）。
  上一轮修改前备份：`backups/2026-10-19_13-50/`（含 `pre-change-manifest.txt`）。
- 两项改动归属的确认依据：`backups/2026-10-19_13-50` 与 `backups/2026-10-19_15-32`
  分别对应上一轮与本轮起点；`src/investigator/guides.py` 不在 13:50 备份中，说明它是上一轮
  新增、本轮再修改。无法由这两个备份区分的更早历史，本文件不猜测。

## 1. 问题一：补充结果后的操作卡反馈

### 复现（修复前）

路径：主报告 `review-consistent` → 添加 `review-missing-image` → 当前卡
`g2.frame.find-image`，上下文“补充记录 1”。

实际结果：

- 点“做不了或不确定”：卡片不变，仍重复显示同一步骤，没有进入交接。
- 点“已做完”：卡片不变，仍重复显示同一步骤。

### 原因

1. `guides.current_card` 在存在补充记录时直接返回 `_addition_card`，而该函数完全不读取
   任何步骤反馈，只按复验结果选择固定汇总卡。
2. `StepFeedback` 只保存 `step_id`/`title`/`choice` 等，没有调查、上下文（主报告或
   “补充记录 N”）、指引版本、报告摘要；`latest_feedback(step_id)` 仅按步骤号查找。
   同一步骤在不同补充记录之间会混用反馈。

### 修复后行为

- `StepFeedback` / `StepSuggestion` 增加 `investigation_id`、`context`、`source_sha256`；
  `latest_feedback(step_id, context=..., guide_version=...)` 同时校验调查、上下文与版本。
  不指定上下文时只匹配主报告。
- 补充记录卡按该记录自身的问题码给出有序步骤（缺图 → 指标 → 记录保留；未知问题码只给
  交接），再逐项检查归属于“补充记录 N”的反馈：
  - “做不了或不确定” → 交接卡（`handoff.save`），说明停止条件。
  - “已做完” → 该记录的下一步；没有下一步时转为 `after.observation`（等待新结果），
    不重复索取同一操作，并保留“不是问题已修好的证明”。
  - “问题仍在 / 暂时没再出现” → `after.observation`，保留用户声明，不改复验或根因。
- 后续补充记录（补充记录 2）重新给出自己的步骤，不继承前一份记录的反馈。
- 新调查清空步骤与反馈；同一调查内历史保留。
- 界面提示、当前卡与导出都读取同一份指引与同一会话记录；导出“用户声明做了什么”现在
  写明上下文、步骤 ID 与指引版本。
- 对象、批次、区域和口径的比较条件未放宽（复验矩阵测试保持不变）。

## 2. 问题二：GUI 文案断言漏检

### 复现（修复前规则）

旧 `tests/gui_smoke.py` 的 `unnegated_claims` 只检查短语前 12 个字符里是否出现否定词：

- `unnegated_claims("不代表相机合格。内容正确。", ...)` 返回空列表，漏掉第二句的错误肯定。
- 输入为拼接后的整段文本、没有控件边界，前一控件的否定会豁免后一控件的肯定结论。

### 修复后规则

辅助函数抽到 `tests/gui_assertions.py`，规则明确且有限：

1. 每个控件文本单独判断（控件边界即断言边界）。
2. 按句子/分句分隔符（`。！？!?；;，,：:`、换行）切分；否定词只作用于同一分句内、
   且出现在短语之前的文本。
3. 不使用“附近出现否定词就整段豁免”，不引入 NLP 依赖。

`tests/gui_smoke.py` 改为按控件列表调用该函数；原有断言未删除、跳过或弱化。

## 3. 修改文件与目的

| 文件 | 本轮改动 | 目的 |
| --- | --- | --- |
| `src/investigator/session.py` | 反馈/建议增加归属字段；`latest_feedback` 按调查+上下文+版本查询；反馈导出文本带上下文与版本 | 防止跨记录、跨调查、跨版本混用 |
| `src/investigator/guides.py` | 补充记录卡先走自身步骤并处理归属反馈；共享记录问题码集合；交接卡支持自定义说明 | 修复“做不了/已做完”不转换 |
| `src/investigator/ui.py` | “找不到材料”页已记录的说明补“（用户声明，未独立验证）” | 界面与导出口径一致 |
| `tests/gui_assertions.py`（新） | 分句、按控件判断的文案断言 | 修复漏检 |
| `tests/test_gui_assertions.py`（新） | 正反例测试（8 项） | 锁定断言规则 |
| `tests/test_addition_feedback.py`（新） | 补充记录反馈、隔离、导出归属（13 项） | 缺陷回归 |
| `tests/gui_smoke.py` | 引用共享断言；新增 D/E/F/G 段真实点击反馈按钮、交接保存、主报告反馈；窗口销毁与 grab 清理 | 覆盖新增流程 |
| `README.md` | 更新三块内容命名与反馈归属说明，链接本记录 | 文档与行为一致 |
| `docs/verification-2026-10-19.md`（新） | 本文件 | 交付记录 |

`src/investigator/export.py`、`tests/test_export.py`、`tests/test_session.py` 本轮未修改。

## 4. 验证结果（本轮实际执行）

### 修复前证据

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 新回归测试 | `python -m unittest tests.test_addition_feedback tests.test_gui_assertions` | 21 项：5 失败、2 错误，退出码 1 |
| 旧规则反向验证 | 临时把 `gui_assertions.py` 退回“前 12 字符否定即豁免” | 4 项失败 |
| 旧卡片逻辑反向验证（单元） | 临时让 `_addition_card` 直接返回汇总卡 | 11 项失败（3 失败 + 8 错误） |
| 旧卡片逻辑反向验证（GUI） | 同上，运行 `tests/gui_smoke.py`（当时 114 项） | 101/114，13 项失败 |

补充记录：“做不了或不确定 / 已做完 均不改变卡片”在修复前由直接调用 `current_card` 复现，
见 `tests/test_addition_feedback.py` 的 `test_blocked_on_addition_moves_to_handoff`、
`test_done_on_addition_does_not_repeat_same_step`。

### 修复后

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | --- | --- |
| 单元测试 | `.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -t .` | 0 | 96 项全部通过；通过 96、失败 0、错误 0、跳过 0 |
| GUI 冒烟 | `.\.venv\Scripts\python.exe -B -X utf8 tests\gui_smoke.py` | 0 | 125/125 项通过 |

未出现 skipped（符号链接权限用例本机可执行，未跳过）。

### 新增覆盖（对应任务清单）

- 主报告步骤反馈后的卡片转换：单元 `PrimaryFeedbackRegressionTests`；GUI G 段点击“已做完”。
- 补充记录出现新问题后的反馈与交接：单元 `AdditionCardFeedbackTests`；GUI D 段点击
  “做不了或不确定”并检查交接卡与导出。
- 多份补充记录中相同步骤的反馈隔离：单元 `FeedbackIsolationTests`；GUI E 段添加第三份记录。
- 用户反馈不改变复验或根因判断：单元与 GUI 均检查“未通过/待结果”“根因未知”。
- 新结果回来后当前卡更新，不继续索取已处理材料：单元 done 用例与 GUI E 段。
- 无报告时记录“找不到材料”并预览、保存交接说明：GUI F 段（真实预览窗口 + 保存）。
- 导出包含步骤历史、反馈归属、比较限制，与界面一致：单元 `ExportOwnershipTests`；
  GUI D/G 段检查导出中的 `补充记录 1` / `主报告`、步骤 ID、版本与当前卡标题。
- 原有新调查隔离、草稿保护、保存取消/失败保护：原 GUI 段保留并全部通过。

## 5. GUI 真实驱动、模拟部分与未覆盖

真实驱动：启动窗口、选择报告、技术详情折叠、记录说明、补充结果、点击反馈按钮
（“做不了或不确定”“已做完”“问题仍在”）、预览窗口与“保存”按钮、错误提示“返回”、
未保存提示的保存/放弃/返回、交接说明的预览与保存。

模拟（非人工验证）：

- 系统文件选择/保存对话框用固定路径替代（`unittest.mock`）。
- 写入失败通过注入 `Path.open` 的 `PermissionError` 模拟，未修改文件系统权限。
- 截图只证明渲染，不作为行为验证。

未覆盖：

- 系统文件对话框的人工点击、真实用户试用与体验评估。
- 跨会话持久化（本轮不增加数据库/历史中心）。
- 真实摄像头记录重新采集；摄像头项目未运行。

## 6. 对照原计划（`docs/next-iteration-plan-2026-10-19.md`）

已完成（上一轮实现，本轮修复与验证）：

- 材料来源帮助、合成练习入口、无报告交接；“开始另一件问题”与“添加操作后的结果”分离。
- “这份报告还不能说明什么”及每项影响说明；每次只突出一个动作卡。
- 单一指引来源 `guides.py`，界面、卡片与导出同源；导出新增建议历史、用户声明、带回材料、
  仍缺材料。
- 本次修复：补充记录反馈归属、卡片转换、导出归属；GUI 断言分句与控件边界。

未完成或仍受限：

- 用户试用与人工体验尚未进行，不能写为产品验收通过；计划第 6 节的人工体验任务仍待用户执行。
- 跨运行设备恢复判断未扩展；不同批次仍判“不可比较”。
- 系统文件对话框未做人工点击验证。
- 自动化检查只覆盖合成材料与模拟对话框；不是产品效果证据。

## 7. 给 Codex 的审核入口

- 本轮差异依据：`backups/2026-10-19_15-32/`（修改前版本 + `MANIFEST.txt`）；
  上一轮起点：`backups/2026-10-19_13-50/`。
- 重点审核：`src/investigator/guides.py` 的 `_addition_steps` / `_addition_card`、
  `src/investigator/session.py` 的 `latest_feedback` 与归属字段、
  `tests/gui_assertions.py` 的规则、`tests/gui_smoke.py` 新增 D–G 段。
- 缺陷回归：`tests/test_addition_feedback.py`、`tests/test_gui_assertions.py`。
- 验证命令见第 4 节；未暂存、未提交、未推送、未创建分支。
