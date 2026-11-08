"""把采集问题查询快照整理为展示文案，不重新判定关闭条件。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IssueCardView:
    decision: str
    location: str
    basis: str
    missing: str
    note: str
    history: tuple[str, ...]
    repeat_notice: str
    summary: str


def _repeat_notice(detail):
    latest = detail["latest_primary_comparison"]
    if not latest or not latest["is_repeat"]:
        return ""
    note = f"{latest['context']} 重复导入，没有新增证据，问题状态未变。"
    reopened_since = False
    for event in reversed(detail["history"]):
        if event["event"] == "重新出现":
            reopened_since = True
        if event["event"] != "范围内不再出现":
            continue
        context = event["context"]
        if detail["evidence"][context]["source_sha256"] == latest["source_sha256"]:
            note += f"{context} 已用这份报告支持过本问题的范围内关闭。"
            if reopened_since:
                note += "该次关闭后又登记了问题重新出现。"
            return note
    return note


def format_issue_card(detail: dict) -> IssueCardView:
    ident = detail["issue_id"]
    frame = detail["frame_count"]
    closed = detail["status"] == "closed_in_scope"
    events = detail["history"]
    event = events[-1]
    context = detail["resolved_by"] if closed else event["context"]
    evidence = detail["evidence"][context]
    location = f"{context} ({evidence['source_name']})"
    basis = event["reason"]
    scope = f"帧 {frame} 范围" if frame is not None else "核实范围"
    decision = f"可在本次{scope}内关闭" if closed else "仍未解决"
    if closed and any(e["event"] == "重新出现" for e in events):
        decision = f"可在本次{scope}内再次关闭"
    if not closed and event["event"] == "重新出现":
        decision = "重新出现，仍未解决"
    if context == detail["origin"]["context"]:
        location += " | " + detail["origin"]["locator"]
    if closed:
        row = next((r for r in evidence["verified_frames"] if r["frame_count"] == frame), None)
        if row:
            location += f" | {row['locator']} → 帧 {frame}"
            basis = f"{context} 核实了帧 {frame}，图片摘要匹配，五项指标逐项一致。"
    elif event["event"] == "未解决":
        numbers = evidence["verified_frame_counts"]
        if numbers is not None:
            location += f" | verified_frame_counts={numbers}"
    missing = " ".join(detail["missing_evidence"])
    if not missing:
        missing = "无。关闭该问题没有待补检查。" if closed else detail["next_step"]
    cause = ("首次无法核实的原因仍未知。" if detail["key"].startswith("frame_unverifiable:")
             else "根因仍未知。")
    note = cause + (detail["next_step"] if closed else "请保留原问题记录。")
    if closed and any(e["event"] == "重新出现" for e in events):
        note = cause + "请保留先前关闭、重新出现及本次关闭的证据。"
    if not closed and detail["next_step"] not in missing:
        missing = (missing + " " + detail["next_step"]).strip()
    history = tuple(f"{i}. {e['context']} → {e['event']}（{e['reason']}）"
                    for i, e in enumerate(events, 1))
    if closed:
        gap = missing if detail["missing_evidence"] else "关闭该问题没有待补检查。"
        summary = f"{ident} {decision}。{gap}{basis}{note}"
    else:
        summary = f"{ident} {decision}。依据为{location}。{missing}{note}"
    return IssueCardView(decision, location, basis, missing, note, history,
                        _repeat_notice(detail), summary)
