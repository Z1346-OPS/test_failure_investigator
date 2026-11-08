# 采集问题详情查询 v1

从助手仓库根目录运行，在已有调查中也可以直接调用同一方法。以下示例按本机走查包的顺序导入三份合成报告。

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path("src").resolve()))
from investigator.explain import explain_report
from investigator.reports import load_report
from investigator.session import Session

trial = Path("D:/Projects/Python/camera-quality-diagnostics/docs/tasks/capture-trial-2026-11-08")
session = Session()
primary = load_report(trial / "round-1/01.json")
session.load_primary(primary, explain_report(primary))
investigation_id = session.investigation_id
for path in ("round-1/02.json", "round-2/03.json"):
    report = load_report(trial / path)
    session.add_addition(report, explain_report(report))
    detail = session.get_issue_details(investigation_id, "P01")
    print(detail["status"], detail["last_issue_assessment"], detail["next_step"])
```

## 返回值

| 字段 | 读取方法 |
| --- | --- |
| `schema_version`、`investigation_id`、`issue_id` | 版本为 1。问题编号限定在当前调查内，可从 `session.review_problems()` 的 `ident` 取得。导入新主报告会更换调查编号。 |
| `key`、`label`、`frame_count` | 问题标识、说明及作用帧。批次级问题的帧号为 `null`。 |
| `status`、`origin`、`resolved_by` | 状态为 `open` 或 `closed_in_scope`。起点由报告上下文和字段定位标识；关闭时记录支持该判断的补充报告上下文。 |
| `history` | 按顺序列出上下文、动作和理由。重新出现沿用同一问题编号，保留之前的范围内关闭。 |
| `last_issue_assessment` | 本轮问题最近一次被后续复核评估的上下文、结果、原因及对象关联判断。刚发现或重新出现、尚无后续评估时为 `null`。 |
| `latest_primary_comparison` | 最近一次追加相对于主报告的比较，包括两份报告摘要、结果和重复标记。尚未追加时为 `null`。重复导入会更新此字段，保留上次问题评估和证据。 |
| `evidence` | 以问题历史中的报告上下文为键。每份证据包含来源文件名、完整 SHA-256、报告自身结论、批次、比较口径、执行编号、UTC 时间和帧范围。 |
| `missing_evidence`、`next_step` | 当前缺失项和下一项人工操作。问题在范围内关闭后缺失项为空，仍应保留原失败。 |

每份证据的 `verified_frame_counts` 来自整个 `frames` 数组。只有图片摘要匹配、五项保存值和重算值一致的帧才入选。每个 `verified_frames` 项保留原数组定位、帧号和五项值对，报告的警告与矛盾随证据保留。缺少 `frames` 时集合为 `null`，有空数组时集合为 `[]`。`declared_frame_counts` 表示报告声明的范围，缺字段保留 `null`。

交接说明以 `verified_frame_counts=[1]` 展示核实集合，以 `frames[0] → 帧 1` 定位原报告中的对应记录。

主案例先返回 `open`。补充记录 1 自身为 `consistent`，完整核实集合为 `[1]`，仍缺第 2 帧证据。随后返回 `closed_in_scope`，补充记录 2 核实了 `[1, 2]`。按 `origin.context` 和 `resolved_by` 找两份证据，对照不同的 `review_id`、严格递增的 `reviewed_at_utc`、同批次与口径，再查目标帧的指标对。对第 2 帧这一单项问题，满足上述条件、只核实第 2 帧的后续报告也足以关闭该项。

调用仅查询当前内存会话。空白、非字符串编号抛 `ValueError`；未知调查、已替换的调查、未知问题或没有采集问题时抛 `KeyError`。无效输入不会改变调查。每次查询返回独立快照，调用者可保留前一轮结果。
