"""固定问题的离线回答。状态来自调查会话，引用来自已导入的报告。"""

from dataclasses import dataclass

from .explain import DECODE_TEXT
from .export import scrub
from .issue_card import format_issue_card
from .questions import QUESTIONS, parse_question
from .qr_query import original_issue_status, query_qr_region
from .session import RECHECK_INSUFFICIENT, Session, registered_problem_labels


@dataclass(frozen=True)
class EvidenceAnswer:
    decision: str
    evidence: str
    missing: str

    def text(self, question: str = QUESTIONS[0]) -> str:
        if question == QUESTIONS[0]:
            return scrub(f"{self.decision}\n依据：{self.evidence}\n待补检查：{self.missing}")
        if question == QUESTIONS[1]:
            return scrub(self.evidence)
        if question == QUESTIONS[2]:
            return scrub(self.missing)
        raise ValueError("请选择列出的交接问题。")


def capture_answer(detail: dict) -> EvidenceAnswer:
    view = format_issue_card(detail)
    origin = detail["origin"]
    first = detail["evidence"][origin["context"]]
    references = [f"{origin['context']} {first['source_name']} / {origin['locator']} 登记原问题。"]
    last = detail["history"][-1]
    context = detail["resolved_by"] or last["context"]
    source = detail["evidence"][context]
    if context != origin["context"]:
        if last["event"] in {"再次记录", "重新出现"}:
            references.append(f"{context} {source['source_name']}：{view.basis}。")
        else:
            row = next((r for r in source["verified_frames"] if r["frame_count"] == detail["frame_count"]), None)
            location = row["locator"] if row else source["scope_locator"]
            references.append(f"{context} {source['source_name']} / {location}。{view.basis}")
    if view.repeat_notice:
        references.append(view.repeat_notice)
    missing = view.missing if detail["resolved_by"] else detail["next_step"]
    return EvidenceAnswer(f"{detail['issue_id']} {view.decision}。", " ".join(references), missing)


def _qr_observations(report, context):
    evidence, gaps = [], []
    for kind in dict.fromkeys(row["region"]["kind"] for row in report.data["decode_summaries"]):
        if kind not in {"full_image", "roi"}:
            continue
        result = query_qr_region(report, kind)
        path = next((p.rsplit(".", 1)[0] for p in result["evidence_paths"] if p.endswith(".region")),
                    "decode_summaries")
        label = "整图" if kind == "full_image" else "选区"
        finding = result["judgment"]
        state = result.get("decode_status")
        if result["status"] == "unverified" and state in {"decode_error", "not_decoded", "execution_error", "conflict"}:
            finding = f"{label}{DECODE_TEXT[state]}，内容未验证。"
        evidence.append(f"{context} {report.source_name} / {path}：{finding}")
        if result["status"] == "incorrect":
            gaps.append(f"{label}需取得与独立答案逐字节一致的后续复验。")
        gaps.extend(f"{label}：{gap}" for gap in result["missing_evidence"])
    if not evidence:
        evidence.append(f"{context} {report.source_name} / decode_summaries 缺少可核对的区域。")
        gaps.append("需提供带有检查区域和读码结果的报告。")
    return evidence, gaps


def qr_answer(session: Session) -> EvidenceAnswer:
    primary = session.primary
    evidence, gaps = _qr_observations(primary, "主报告")
    has_issue = bool(registered_problem_labels(primary))
    substantive = [(i, a) for i, a in enumerate(session.additions, 1) if not a.is_repeat]
    if not substantive:
        decision = "原问题仍未解决。" if has_issue else "主报告未登记问题。"
        if has_issue:
            gaps.append("需补充覆盖原问题的独立复验报告。")
    else:
        index, addition = substantive[-1]
        later = addition.report
        status = original_issue_status(primary, addition)
        decision = {"unresolved": "原问题仍未解决。", "closed_in_scope": "原问题可在本次复验范围内关闭。",
                    "no_registered_issue": "主报告未登记问题。"}[status]
        context = f"补充记录 {index}"
        if len(substantive) > 1:
            decision = f"按主报告与{context}的比较，" + decision
        if later.report_type == "label_baseline":
            new_evidence, new_gaps = _qr_observations(later, context)
            evidence.extend(new_evidence)
        else:
            evidence.append(f"{context} {later.source_name} / report_type 为 {later.report_type}。")
            new_gaps = []
        if not addition.comparable or addition.recheck_result == RECHECK_INSUFFICIENT:
            evidence.append(f"复验{addition.recheck_result}。{addition.recheck_reason}")
        elif status == "no_registered_issue":
            evidence.append(f"补充报告复验结果为{addition.recheck_result}。")
        if addition.comparable:
            gaps = new_gaps
        else:
            gaps.append("需按主报告的图片、区域和答案条件补充可比复验。")
        if addition.recheck_result == RECHECK_INSUFFICIENT:
            gaps.append(addition.recheck_reason)
        if status == "closed_in_scope":
            evidence.append(f"{primary.source_name} 与 {later.source_name} / analysis_id、analyzed_at 确认独立复验及先后。")
            gaps = []
    if session.additions and session.additions[-1].is_repeat:
        evidence.append(f"补充记录 {len(session.additions)} 重复导入，没有新增证据。")
    return EvidenceAnswer(decision, " ".join(evidence), " ".join(dict.fromkeys(gaps)) or "无。")


def answer_question(session: Session, question: str, issue_id: str | None = None) -> str:
    qr = session.primary is not None and session.primary.report_type == "label_baseline"
    intents, target = parse_question(question, issue_id, qr=qr)
    answer = answer_session(session, target)
    if QUESTIONS[0] in intents:
        return answer.text()
    return "\n".join(answer.text(intent) for intent in intents)


def answer_session(session: Session, issue_id: str | None = None) -> EvidenceAnswer:
    report = session.primary
    if report is None:
        raise ValueError("请先导入报告。")
    if report.report_type == "label_baseline":
        if issue_id:
            raise ValueError("QR 问答不使用采集问题编号。")
        return qr_answer(session)
    if report.report_type != "capture_task_review":
        raise ValueError("离线问答支持采集复核和 QR 报告。")
    ids = [p.ident for p in session.review_problems_by_priority()]
    if issue_id is None and len(ids) == 1:
        issue_id = ids[0]
    if issue_id not in ids:
        raise ValueError("请选择采集问题编号。可选编号：" + ("、".join(ids) or "无"))
    return capture_answer(session.get_issue_details(session.investigation_id, issue_id))
