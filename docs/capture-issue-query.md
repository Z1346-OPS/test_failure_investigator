# 采集问题详情查询 v1

在助手仓库根目录，用一个问题编号和按实际交接顺序排列的报告直接查询。第一份是主报告，后面是补充报告。

```powershell
$trial = 'D:\Projects\Python\camera-quality-diagnostics\docs\tasks\capture-trial-2026-11-08'
.\.venv\Scripts\python.exe -B -X utf8 src/query_issue.py P01 "$trial/round-1/01.json" "$trial/round-1/02.json"
.\.venv\Scripts\python.exe -B -X utf8 src/query_issue.py P01 "$trial/round-1/01.json" "$trial/round-1/02.json" "$trial/round-2/03.json"
```

| 接手人的问题 | 第一条命令 | 第二条命令 |
| --- | --- | --- |
| 能否关闭 P01？ | `status=open` | `status=closed_in_scope` |
| 查哪份证据？ | `origin` 定位 01.json 的原问题；02.json 的 `verified_frame_counts=[1]`。 | `resolved_by` 指向补充记录 2。在该记录的 `evidence` 条目中，`verified_frames` 给出帧 2 的原数组位置和指标值对。 |
| 还缺什么检查？ | `missing_evidence` 和 `next_step` 指出仍须核实第 2 帧。 | `missing_evidence=[]`，保留原失败与支持此次关闭的证据。 |

命令向标准输出写入完整 v1 JSON。未解决的问题也是有效查询，退出码为 0。报告无效或问题编号无效时，错误写入标准错误，退出码为 2。本版问题编号对应采集复核报告登记的问题。

已有调查可直接调用同一方法。以下示例使用同一组报告。

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

## 先列出问题

在上面的 PowerShell 环境中运行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 src/query_issue.py --list "$trial/round-1/01.json" "$trial/round-1/02.json"
```

输出的 `issues` 每项含 `issue_id`、`label`、`frame_count`、`status`，顺序与 Tk 列表一致。未解决问题置顶，同一状态内按编号排列。这组输入列出 P01 为 `open`；再追加 `round-2/03.json`，仍列出 P01，状态变为 `closed_in_scope`。用相同主报告和相同的追加顺序，将命令里的 `--list` 换成选定编号即可查证据及缺失项。各次命令创建独立调查。`issues=[]` 表示没有已登记的采集复核问题，退出码为 0；报告类型见 `primary_report_type`，QR 或定时采集的诊断请看各自的交接说明。

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
