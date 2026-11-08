"""导出一份 Markdown 说明：先预览，再独占新建。

边界（见 docs/simple-app-design.md 第 4 节）：
  * 只生成一份可阅读的文件，内容来自同一份调查记录。
  * 默认不导出本机绝对路径、原图、QR 原始载荷或整段原始日志。
  * 明确说明未附原始文件；它是一份说明，不是完整原始证据包。
  * 不覆盖已有文件；写入失败不显示成功。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from .explain import qr_content_conclusion, unknown_impact
from .guides import current_card
from .issue_card import format_issue_card
from .reports import review_scope_evidence, valid_review_id
from .session import RECHECK_PASSED, Session, new_problem_labels

# 本机路径兜底：即使某处漏了字段，也不把绝对路径写进说明。
_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/][^\s\"'<>|]*)|(?:\\\\[^\s\"'<>|]+)")
_SCRUBBED = "<本机路径已省略>"

NOT_ATTACHED_NOTICE = (
    "本说明只包含已审查的字段，**未附原始报告、原图、二维码载荷或整段日志**。"
    "它是一份说明，不是完整原始证据包；技术人员可能仍需另行索取原始文件。"
)


class ExportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def scrub(text: str) -> str:
    """兜底脱敏：替换绝对路径。不宣称能覆盖所有敏感内容。"""
    return _ABSOLUTE_PATH.sub(_SCRUBBED, text or "")


def _single_frame_closure(session: Session) -> str:
    problems = session.review_problems()
    if len(problems) != 1:
        return ""
    problem = problems[0]
    if problem.frame is None or problem.key != f"frame_unverifiable:{problem.frame}":
        return ""
    detail = session.get_issue_details(session.investigation_id, problem.ident)
    if detail["status"] != "closed_in_scope" or detail["missing_evidence"]:
        return ""
    context = detail["resolved_by"]
    evidence = detail["evidence"][context]
    if evidence["verified_frame_counts"] != [problem.frame]:
        return ""
    return format_issue_card(detail).summary


def short_conclusion(session: Session) -> str:
    """简明结论：整体状态 + 最要紧的一条发现 + 当前建议的一步。"""
    explanation = session.primary_explanation
    if explanation is None:
        if session.notes or session.feedbacks:
            return scrub("尚未选择报告；本次只记录用户声明和交接信息，没有诊断结论。")
        return "尚未选择报告。"
    parts = [explanation.headline]
    is_review = session.primary.report_type == "capture_task_review"
    qr_pair = False
    closure = ""
    if is_review:
        state, summary = session.investigation_summary()
        if state == RECHECK_PASSED:
            closure = _single_frame_closure(session)
        parts.append(f"当前调查：{state}。{closure or summary}")
    if explanation.findings and not closure:
        parts.append(("原主报告：" if is_review else "") + explanation.findings[0])
    # 新结果改变了判断时，简明结论必须反映，不能只讲原始报告。
    # 重复导入不产生新证据：结论仍取最近一次有实质内容的补充记录，
    # 并明确说明重复导入没有改变它，避免把已知异常静默替换成“证据不足”。
    if session.additions:
        latest = session.additions[-1]
        substantive = [item for item in session.additions if not item.is_repeat]
        basis = substantive[-1] if substantive else latest
        qr_pair = (bool(substantive) and session.primary.report_type == "label_baseline"
                   and basis.report.report_type == "label_baseline")
        if qr_pair:
            parts.append("主报告当时" + qr_content_conclusion(session.primary))
            parts.append("补充报告中，本次" + qr_content_conclusion(basis.report))
        if (substantive and session.primary.report_type == "camera_timed_capture"
                and session.primary.get("status") == "failed"
                and session.primary.get("stop_reason") == "open_failed"
                and basis.report.report_type == "camera_timed_capture"
                and not basis.comparable):
            followup = basis.report
            counts = followup.get("counts")
            if (followup.get("status") == "completed"
                    and followup.get("stop_reason") == "duration_reached"
                    and not followup.warnings and not followup.get("primary_error")
                    and not followup.get("cleanup_errors")
                    and 0 < counts["valid_frames"] <= counts["read_attempts"]
                    and 0 < counts["samples_completed"] <= counts["valid_frames"]):
                parts.append(f"编号 {followup.get('config', 'camera_index')} 本次采集成功；"
                             f"编号 {session.primary.get('config', 'camera_index')} 的原问题"
                             "仍待可比复验，根因未知。")
        if is_review and not closure:
            parts.append(f"仅与主报告的单次比较：{basis.recheck_result}；不代表调查全部问题已解决。")
        elif not is_review:
            parts.append(f"补充结果复验：{basis.recheck_result}。")
        new_problems = new_problem_labels(basis)
        if new_problems:
            parts.append("新出现：" + "；".join(new_problems) + "。")
        if latest.is_repeat:
            parts.append(f"最近一次导入（补充记录 {len(session.additions)}）重复导入了"
                         "已有材料，没有新增证据，不改变上一条复验结论。")
    if explanation.unknowns and not qr_pair and not closure:
        parts.append("仍未确认：" + explanation.unknowns[0])
    card = current_card(session)
    if card is not None:
        parts.append(f"当前建议：{card.title}。")
    return scrub(" ".join(parts))


def _unknown_blocks(explanation) -> list[str]:
    if explanation is None or not explanation.unknowns:
        return ["- （无）"]
    lines: list[str] = []
    for item in explanation.unknowns:
        lines.append(f"- {scrub(item)}")
        lines.append(f"  - 影响：{scrub(unknown_impact(item))}")
    return lines


def _bullet_list(items: list[str], empty: str = "（无）") -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- {scrub(item)}" for item in items)


def _table(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return "（无）"
    lines = ["| 项 | 值 |", "| --- | --- |"]
    for label, value in rows:
        cell = scrub(str(value)).replace("|", "\\|")
        lines.append(f"| {scrub(str(label))} | {cell} |")
    return "\n".join(lines)


def render_markdown(session: Session) -> str:
    """把当前调查记录渲染成 Markdown。纯函数，不写文件。"""
    explanation = session.primary_explanation

    lines: list[str] = []
    lines.append("# 排查说明")
    lines.append("")
    lines.append(f"生成时间：{session.created_at}")
    lines.append(f"调查 ID：{session.investigation_id}")
    lines.append("")

    lines.append("## 简明结论")
    lines.append("")
    lines.append(short_conclusion(session))
    lines.append("")

    card = current_card(session)
    lines.append("## 下一步")
    lines.append("")
    if card is not None:
        lines.append(f"当前建议（指引 {card.guide_id} v{card.guide_version}，"
                     f"步骤 {card.step_id}，{card.context}）：")
        lines.append("")
        lines.append(f"**{scrub(card.title)}**")
        lines.append("")
        lines.append(f"- 与哪条发现有关：{scrub(card.related)}")
        lines.append(f"- 去哪里：{scrub(card.step.where)}")
        lines.append("- 具体做什么：")
        for index, action in enumerate(card.step.actions, start=1):
            lines.append(f"  {index}. {scrub(action)}")
        lines.append(f"- 做完看什么：{scrub(card.step.observe)}")
        lines.append(f"- 回来后：{scrub(card.step.return_hint)}")
        lines.append(f"- 做不了或不确定时：{scrub(card.step.stop)}")
    elif explanation is not None and explanation.next_steps:
        lines.append("（尚未选定适用步骤；以下为原报告的解释建议。）")
        lines.append("")
        for index, step in enumerate(explanation.next_steps, start=1):
            marker = "（建议先做）" if index == 1 else ""
            lines.append(f"{index}. **{scrub(step.title)}**{marker}")
            lines.append(f"   - 为什么：{scrub(step.why)}")
            lines.append(f"   - 需要带回：{scrub(step.bring_back)}")
    else:
        lines.append("（无）")
    lines.append("")

    lines.append("## 主报告的发现")
    lines.append("")
    lines.append(_bullet_list(explanation.findings) if explanation is not None else "- （尚未导入报告）")
    lines.append("")

    lines.append("## 这份报告还不能说明什么")
    lines.append("")
    lines.extend(_unknown_blocks(explanation))
    lines.append("")

    lines.append("## 建议过什么")
    lines.append("")
    for label, value in session.suggestion_dimension():
        lines.append(f"- {scrub(label)}：{scrub(value)}")
    lines.append("")

    lines.append("## 用户声明做了什么")
    lines.append("")
    lines.append("以下内容为用户声明，未由本程序独立验证，不能当作复验通过。")
    lines.append("")
    for label, value in session.user_feedback_dimension():
        lines.append(f"- {scrub(label)}：{scrub(value)}")
    lines.append("")

    lines.append("## 带回了什么")
    lines.append("")
    for label, value in session.brought_dimension():
        lines.append(f"- {scrub(label)}：{scrub(value)}")
    lines.append("")

    lines.append("## 仍缺什么")
    lines.append("")
    lines.append(_bullet_list(session.remaining_dimension()))
    lines.append("")

    if session.primary and session.primary.report_type == "capture_task_review":
        lines.append("## 调查问题历史")
        lines.append("")
        lines.append(_table(session.problem_history_dimension()))
        lines.append("")
        lines.extend(["## 复核编号与开始时间", "",
                      "| 调查内记录 | review_id | reviewed_at_utc |",
                      "| --- | --- | --- |"])
        records = [("主报告", session.primary)] + [
            (f"补充记录 {index}", item.report) for index, item in enumerate(session.additions, 1)
            if item.report.report_type == "capture_task_review"]
        for context, report in records:
            execution = report.get("review_id")
            ident = execution if valid_review_id(execution) else "未知"
            lines.append(f"| {context} | {ident} | {_utc_text(report.get('reviewed_at_utc'))} |")
        lines.append("")
    lines.append("## 前后结果与比较限制")
    lines.append("")
    lines.append("以下逐次比较的基线始终为原主报告，仅说明各次比较范围，不替代调查当前状态。")

    lines.append("")
    if not session.additions:
        lines.append("- 本次没有补充结果，未形成前后比较。")
    for index, addition in enumerate(session.additions, start=1):
        lines.append(f"### 补充记录 {index}：{addition.report.type_label}")
        lines.append("")
        lines.append(f"- 复验结果：{scrub(addition.recheck_result)}")
        lines.append(f"- 理由：{scrub(addition.recheck_reason)}")
        new_problems = new_problem_labels(addition)
        if new_problems:
            lines.append("- 新出现的问题（原记录没有登记）：")
            for problem in new_problems:
                lines.append(f"  - {scrub(problem)}")
        lines.append(f"- 关联依据：{scrub(addition.relation.basis)}")
        if addition.comparison_reason != addition.recheck_reason:
            lines.append(f"- 比较限制：{scrub(addition.comparison_reason)}")
        lines.append("- 已核对字段的变化：")
        for change in addition.changes:
            lines.append(f"  - {scrub(change)}")
        if addition.relation.conflict:
            lines.append(f"- 客观冲突：{scrub(addition.relation.conflict)}")
        lines.append("")
        lines.append("#### 该记录自身的发现（不代表与主报告可比）")
        lines.append("")
        lines.append(_bullet_list(addition.explanation.findings))
        lines.append("")
        lines.append("#### 该记录仍不能说明什么")
        lines.append("")
        lines.extend(_unknown_blocks(addition.explanation))
        lines.append("")
    lines.append("")

    lines.append("## 技术详情")
    lines.append("")
    if explanation is not None:
        records = [("主报告", explanation, session.primary)] + [
            (f"补充记录 {index}", addition.explanation, addition.report)
            for index, addition in enumerate(session.additions, start=1)]
        for context, item, report in records:
            lines.append(f"### {context}技术详情")
            lines.append("")
            lines.append(_table(item.technical))
            lines.append("")
            if report.report_type == "capture_task_review":
                lines.append(_table(_review_scope_rows(report)))
                lines.append("")
            lines.append(f"#### {context}证据定位")
            lines.append("")
            if item.evidence:
                lines.append("| 编号 | 字段定位 | 说明 |")
                lines.append("| --- | --- | --- |")
                for ident, locator, note in item.evidence:
                    lines.append(f"| {context}/{ident} | {scrub(locator)} | {scrub(note)} |")
            else:
                lines.append("（无）")
            lines.append("")
        for title, rows in (
            ("执行情况（五维之一）", session.execution_dimension()),
            ("用户反馈（五维之一）", session.user_feedback_dimension()),
            ("复验结果（五维之一）", session.recheck_dimension()),
            ("根因判断（五维之一）", session.root_cause_dimension()),
        ):
            lines.append(f"### {title}")
            lines.append("")
            lines.append(_table(rows))
            lines.append("")
    else:
        lines.append("（尚未选择报告；以下保留用户声明。）")
        lines.append("")
        lines.append(_table(session.execution_dimension()))
        lines.append("")
    lines.append("")

    lines.append("## 未附原始文件")
    lines.append("")
    lines.append(NOT_ATTACHED_NOTICE)
    lines.append("")

    return "\n".join(lines)


def _utc_text(value) -> str:
    try:
        moment = datetime.fromisoformat(value)
        return moment.isoformat() if moment.utcoffset() == timedelta(0) else "未知"
    except (ValueError, TypeError):
        return "未知"


def _review_scope_rows(report) -> list[tuple[str, str]]:
    scope = review_scope_evidence(report)
    declared = scope["declared_frame_counts"]
    valid = isinstance(declared, list) and all(type(n) is int and n > 0 for n in declared)
    verified = scope["verified_frame_counts"]
    return [
        ("报告 SHA-256", scope["source_sha256"]),
        ("declared_frame_counts（声明范围）", str(declared) if valid else "未知"),
        ("已核实的帧号", f"verified_frame_counts={verified}" if verified is not None
         else "verified_frame_counts=null（未知）"),
        ("逐帧依据（摘要匹配且五项指标一致）", "、".join(
            f"{row['locator']} → 帧 {row['frame_count']}" for row in scope["verified_frames"]
        ) or "无可引用的核实帧"),
    ]


def save_markdown(session: Session, target, *, payload: str | None = None) -> Path:
    """独占新建 Markdown 文件。已存在或写入失败都会抛 :class:`ExportError`。

    ``payload`` 是预览时生成的内容；传入后原样写入，保证预览与实际文件一致。
    """
    path = Path(target)
    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    if path.exists():
        raise ExportError("exists", f"目标文件已存在，请换一个新名称：{path.name}")

    if payload is None:
        payload = render_markdown(session)
    if not payload.strip():
        raise ExportError("empty", "没有可导出的内容")

    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except FileExistsError as error:
        raise ExportError("exists", f"目标文件已存在，请换一个新名称：{path.name}") from error
    except OSError as error:
        raise ExportError("write_failed", f"写入失败：{error}") from error
    return path
