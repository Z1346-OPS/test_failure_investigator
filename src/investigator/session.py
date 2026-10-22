"""调查记录：五个维度独立保存，界面与导出读取同一份记录。

维度分离（见 docs/product-direction.md）：
  执行情况 / 业务观察 / 用户反馈 / 复验结果 / 根因判断

硬性边界：
  * 导入历史记录不等于本次执行。
  * 用户说恢复不等于复验通过。
  * 复验通过不等于根因确认。
  * 不同批次（不同 run_id / 不同图片）不能证明旧问题已恢复。
  * 用户确认关联只是一项用户声明，不能覆盖客观冲突。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from .explain import DECODE_TEXT, REVIEW_ISSUE_TEXT, STOP_REASON_TEXT, Explanation
from .reports import (
    LoadedReport, label_validation_warnings, review_frame_verified,
    review_validation_warnings, valid_sha256,
)

if TYPE_CHECKING:  # 只用于类型提示，避免与 guides 形成导入环
    from .guides import ActionCard

# 复验结论词汇（见 docs/workflow-design.md 第 7 节）
RECHECK_PENDING = "待结果"
RECHECK_INSUFFICIENT = "证据不足"
RECHECK_INCOMPARABLE = "不可比较"
RECHECK_FAILED = "未通过"
RECHECK_PASSED = "范围内通过"

ASSISTANT_EXECUTION = "未执行（本程序只读取已有记录，不运行摄像头、不重新分析）"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class UserNote:
    text: str
    created_at: str


@dataclass
class StepSuggestion:
    """界面建议过的一步；旧记录保留，不被当前卡覆盖。"""

    guide_id: str
    guide_version: str
    step_id: str
    title: str
    context: str
    created_at: str
    investigation_id: str = ""
    source_sha256: str = ""


@dataclass
class StepFeedback:
    """用户对某一步的简短声明；始终是未独立验证的用户反馈。

    归属字段让同一步骤在不同调查、不同补充记录或不同指引版本下互不串用：
    ``investigation_id`` 调查；``context`` 主报告 / 补充记录 N；
    ``source_sha256`` 该卡片针对的报告内容摘要。
    """

    guide_id: str
    guide_version: str
    step_id: str
    title: str
    choice: str
    label: str
    created_at: str
    investigation_id: str = ""
    context: str = ""
    source_sha256: str = ""


@dataclass
class Relation:
    """前后对象的关联判断。"""

    basis: str            # report_identity | user_asserted | missing
    same_subject: bool | None
    question: str | None = None
    conflict: str | None = None
    condition_conflict: str | None = None   # 对象相同，但比较条件不同


@dataclass
class Addition:
    report: LoadedReport
    explanation: Explanation
    relation: Relation
    comparable: bool
    comparison_reason: str
    changes: list[str] = field(default_factory=list)
    recheck_result: str = RECHECK_INCOMPARABLE
    recheck_reason: str = ""
    is_repeat: bool = False
    new_problem_keys: list[str] = field(default_factory=list)   # 原记录没有登记、新结果出现的


@dataclass
class ReviewProblem:
    """会话内从已导入复核记录推导的问题；来源与历次状态均保留。"""
    ident: str
    key: str
    label: str
    frame: int | None
    origin: LoadedReport
    origin_context: str
    locator: str
    history: list[tuple[str, str, str]] = field(default_factory=list)
    resolved_by: str | None = None
    observed_reports: list[LoadedReport] = field(default_factory=list)


@dataclass
class Session:
    """一次调查的完整状态。只保存用户选择过的材料与用户输入。"""

    investigation_id: str = field(default_factory=lambda: uuid4().hex[:12])
    created_at: str = field(default_factory=_now)
    primary: LoadedReport | None = None
    primary_explanation: Explanation | None = None
    additions: list[Addition] = field(default_factory=list)
    notes: list[UserNote] = field(default_factory=list)
    suggestions: list[StepSuggestion] = field(default_factory=list)
    feedbacks: list[StepFeedback] = field(default_factory=list)
    _dirty: bool = False

    # ------------------------------------------------ 主报告

    def load_primary(self, report: LoadedReport, explanation: Explanation) -> None:
        """开始一份新调查；上一份调查的说明与补充结果不进入新调查。"""
        self.investigation_id = uuid4().hex[:12]
        self.created_at = _now()
        self.primary = report
        self.primary_explanation = explanation
        self.additions.clear()
        self.notes.clear()
        self.suggestions.clear()
        self.feedbacks.clear()
        self._dirty = False

    # ------------------------------------------------ 用户反馈

    def add_note(self, text: str) -> UserNote:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("说明内容为空")
        note = UserNote(text=cleaned, created_at=_now())
        self.notes.append(note)
        self._dirty = True
        return note

    def source_sha256_for_context(self, context: str) -> str:
        """指定卡片上下文对应的报告摘要；找不到时返回空字符串。"""
        if self.primary is None:
            return ""
        if context == "主报告":
            return self.primary.source_sha256
        if context.startswith("补充记录 "):
            try:
                index = int(context.split(" ", 1)[1])
            except (IndexError, ValueError):
                return ""
            if 1 <= index <= len(self.additions):
                return self.additions[index - 1].report.source_sha256
        return ""

    def _record_scope(self, context: str) -> tuple[str, str, str]:
        return (self.investigation_id, context,
                self.source_sha256_for_context(context))

    def record_suggestion(self, card: "ActionCard") -> StepSuggestion | None:
        """记录当前建议过的一步；同一调查、上下文、版本和步骤只记一次。

        建议本身由程序展示产生，不计入“未保存的用户内容”，避免仅因翻看界面就
        反复弹出保存提示。旧建议不因当前卡变化而删除。
        """
        investigation_id, context, source_sha256 = self._record_scope(card.context)
        for item in self.suggestions:
            if (item.investigation_id, item.guide_id, item.guide_version,
                    item.step_id, item.context) == (
                    investigation_id, card.guide_id, card.guide_version,
                    card.step_id, card.context):
                return None
        suggestion = StepSuggestion(
            guide_id=card.guide_id,
            guide_version=card.guide_version,
            step_id=card.step_id,
            title=card.title,
            context=card.context,
            created_at=_now(),
            investigation_id=investigation_id,
            source_sha256=source_sha256,
        )
        self.suggestions.append(suggestion)
        return suggestion

    def add_step_feedback(self, card: "ActionCard", choice: str) -> StepFeedback:
        """记录用户对当前步骤的简短声明；不改变任何复验或根因状态。

        反馈带上调查、上下文（主报告 / 补充记录 N）、版本和报告摘要，
        避免同一步骤在不同记录之间混用。
        """
        labels = dict(card.feedback_choices)
        if choice not in labels:
            raise ValueError(f"当前步骤不接受这种反馈：{choice}")
        investigation_id, context, source_sha256 = self._record_scope(card.context)
        feedback = StepFeedback(
            guide_id=card.guide_id,
            guide_version=card.guide_version,
            step_id=card.step_id,
            title=card.title,
            choice=choice,
            label=labels[choice],
            created_at=_now(),
            investigation_id=investigation_id,
            context=context,
            source_sha256=source_sha256,
        )
        self.feedbacks.append(feedback)
        self._dirty = True
        return feedback

    def latest_feedback(self, step_id: str, *, context: str | None = None,
                        guide_version: str | None = None) -> StepFeedback | None:
        """取当前调查内最近的步骤反馈。

        未指定 ``context`` 时只匹配主报告，避免旧调用把补充记录的反馈
        误当成主报告的反馈；指定版本时版本必须一致。
        """
        wanted = "主报告" if context is None else context
        for item in reversed(self.feedbacks):
            if item.step_id != step_id:
                continue
            if item.investigation_id and item.investigation_id != self.investigation_id:
                continue
            if item.context != wanted:
                continue
            if guide_version is not None and item.guide_version != guide_version:
                continue
            return item
        return None

    # ------------------------------------------------ 补充结果

    def assess_relation(self, addition: LoadedReport) -> Relation:
        return _assess_relation(self.primary, addition)

    def add_addition(self, report: LoadedReport, explanation: Explanation,
                     relation_answer: str | None = None) -> Addition:
        """追加一份结果。``relation_answer`` 是用户对那个必要问题的回答。"""
        relation = self.assess_relation(report)

        if relation.condition_conflict:
            comparable = False
            reason = relation.condition_conflict
        elif relation.same_subject is True:
            comparable = True
            reason = "两份记录的对象标识相同，可以比较。"
            relation.basis = "report_identity"
        elif relation.same_subject is False:
            comparable = False
            reason = relation.conflict or "两份记录属于不同对象，不能比较。"
            if relation_answer == "yes":
                # 记录用户声明，但不让它覆盖客观冲突。
                reason += ("你说明这是同一件事，但记录里的对象标识不同；"
                           "按记录为准，仍不能据此证明之前的问题已恢复。")
        elif relation_answer == "yes":
            # 用户声明关联：记录为用户声明，但仍不能据此证明旧问题恢复。
            relation.basis = "user_asserted"
            comparable = False
            reason = ("按你的说明，这是同一问题的后续结果；但两份记录的对象标识不同，"
                      "程序不能据此证明之前的问题已恢复。")
        elif relation_answer == "no":
            relation.basis = "user_asserted"
            comparable = False
            reason = "你说明这是另一件事的报告，与之前的问题不可比较。"
        else:
            relation.basis = "missing"
            comparable = False
            reason = "没有足够的对象标识，也还没有说明关联，暂不比较。"

        changes = _describe_changes(self.primary, self.primary_explanation, report, explanation)

        # 相同字节重复导入：复用已有证据，不重复计数。
        seen = {self.primary.source_sha256} if self.primary is not None else set()
        seen.update(item.report.source_sha256 for item in self.additions)
        is_repeat = report.source_sha256 in seen

        addition = Addition(
            report=report,
            explanation=explanation,
            relation=relation,
            comparable=comparable,
            comparison_reason=reason,
            changes=changes,
            is_repeat=is_repeat,
        )
        if is_repeat:
            addition.recheck_result = RECHECK_INSUFFICIENT
            addition.recheck_reason = ("重复导入的是同一份材料（内容摘要相同），没有新增证据；"
                                       "请补充指定结果，或保存交接。")
        else:
            addition.recheck_result, addition.recheck_reason = _recheck(
                self.primary, report, comparable, reason
            )
            if comparable and self.primary is not None:
                before_keys = set(_problem_keys(self.primary))
                addition.new_problem_keys = [
                    key for key in _problem_keys(report) if key not in before_keys
                ]
        self.additions.append(addition)
        self._dirty = True
        return addition

    # ------------------------------------------------ 保存状态

    def has_unsaved_content(self) -> bool:
        return self._dirty

    def mark_saved(self) -> None:
        self._dirty = False

    # ------------------------------------------------ 五个维度

    def execution_dimension(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = [("助手本次执行", ASSISTANT_EXECUTION)]
        if self.primary is not None:
            rows.append(("导入的主报告", f"{self.primary.type_label}（{self.primary.source_name}）"))
            rows.append(("主报告摘要（前 16 位）", self.primary.source_sha256[:16]))
            rows.append(("导入方式", "用户选择文件；不是本次运行产生的记录"))
        for index, addition in enumerate(self.additions, start=1):
            rows.append((
                f"补充记录 {index}",
                f"{addition.report.type_label}（{addition.report.source_name}）"
                f" 摘要前 16 位 {addition.report.source_sha256[:16]}",
            ))
        return rows

    def business_dimension(self) -> list[str]:
        rows: list[str] = []
        if self.primary_explanation is not None:
            rows.extend(self.primary_explanation.findings)
        for addition in self.additions:
            rows.extend(addition.explanation.findings)
        return rows

    def user_feedback_dimension(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = [
            (f"用户说明（{note.created_at}）", f"{note.text}（用户声明，未独立验证）")
            for note in self.notes
        ]
        rows.extend(
            (f"步骤反馈（{item.created_at}）",
             f"{item.context or '上下文未记录'}：{item.step_id} {item.title}："
             f"{item.label}（指引 {item.guide_id} v{item.guide_version}；"
             f"用户声明，未独立验证）")
            for item in self.feedbacks
        )
        if not rows:
            return [("用户反馈", "（无）")]
        return rows

    def suggestion_dimension(self) -> list[tuple[str, str]]:
        """建议过什么；按时间保留，不因当前卡变化而覆盖。"""
        if not self.suggestions:
            return [("建议步骤", "（无）")]
        return [
            (f"建议步骤（{item.created_at}）",
             f"{item.context}：{item.step_id} {item.title}（指引 {item.guide_id} "
             f"v{item.guide_version}）")
            for item in self.suggestions
        ]

    def brought_dimension(self) -> list[tuple[str, str]]:
        """实际带回了哪些材料；只列用户选择的文件，不列自动发现的路径。"""
        rows: list[tuple[str, str]] = []
        if self.primary is not None:
            rows.append((
                "带回的主报告",
                f"{self.primary.type_label}（{self.primary.source_name}）摘要前 16 位 "
                f"{self.primary.source_sha256[:16]}",
            ))
        for index, addition in enumerate(self.additions, start=1):
            rows.append((
                f"带回的补充记录 {index}",
                f"{addition.report.type_label}（{addition.report.source_name}）摘要前 16 位 "
                f"{addition.report.source_sha256[:16]}",
            ))
        if not rows:
            rows.append(("带回的材料", "（尚未导入报告）"))
        return rows

    def review_problems(self) -> list[ReviewProblem]:
        """重放会话内报告得到问题历史。反馈、保存与重复导入不会改变它。"""
        if self.primary is None or self.primary.report_type != "capture_task_review":
            return []
        problems: list[ReviewProblem] = []
        seen: set[str] = set()
        records = [("主报告", self.primary)] + [
            (f"补充记录 {index}", item.report)
            for index, item in enumerate(self.additions, start=1)]
        for context, report in records:
            if report.source_sha256 in seen:
                continue
            seen.add(report.source_sha256)
            if report.report_type != "capture_task_review":
                continue
            entries = _review_problem_entries(report)
            for problem in problems:
                if problem.resolved_by is not None:
                    continue
                gap = _review_problem_gap(problem, report)
                if gap:
                    problem.history.append((context, "未解决", gap))
                else:
                    problem.resolved_by = context
                    problem.history.append((context, "范围内不再出现",
                                            f"覆盖同一对象、口径及{_problem_scope(problem)}；不说明原因"))
            for key, label, frame, locator in entries:
                same = next((item for item in problems if item.key == key
                             and _same_review_scope(item.origin, report)), None)
                if same is None:
                    same = ReviewProblem(f"P{len(problems) + 1:02d}", key, label, frame,
                                         report, context, locator)
                    problems.append(same)
                    action = "发现"
                elif same.resolved_by is not None:
                    action = "重新出现"
                else:
                    action = "再次记录"
                same.resolved_by = None
                same.observed_reports.append(report)
                same.history.append((context, action, f"{label}；来源 {locator}"))
        return problems

    def unresolved_review_problems(self) -> list[ReviewProblem]:
        return [problem for problem in self.review_problems() if problem.resolved_by is None]

    def investigation_summary(self) -> tuple[str, str]:
        """调查当前状态，不等同于任意一次“主报告→补充报告”的比较。"""
        problems = self.review_problems()
        active = [problem for problem in problems if problem.resolved_by is None]
        if active:
            details = []
            for problem in active:
                gap = problem.history[-1][2]
                details.append(f"{problem.ident} {problem.label}（来源 {problem.origin_context}；{gap}）")
            state = RECHECK_FAILED if self.additions else RECHECK_PENDING
            return state, "仍有未解决问题：" + "；".join(details)
        substantive = [item for item in self.additions if not item.is_repeat]
        if not substantive:
            return RECHECK_PENDING, "尚无新增的可比复验结果。"
        latest = substantive[-1]
        if (problems and latest.comparable and not _entry_state(latest.report)
                and not _comparison_hazards(latest.report)):
            return RECHECK_PASSED, (
                "调查内已登记问题均有后续可比证据覆盖，在各自已核实范围内不再出现；"
                "旧失败与问题历史保留，不说明根因或整台设备恢复。")
        return latest.recheck_result, latest.recheck_reason

    def problem_history_dimension(self) -> list[tuple[str, str]]:
        rows = []
        for problem in self.review_problems():
            state = "未解决" if problem.resolved_by is None else f"范围内不再出现（{problem.resolved_by}）"
            rows.append((f"{problem.ident} {problem.label}", state))
            rows.append((f"{problem.ident} 来源",
                         f"{problem.origin_context} / {problem.locator} / "
                         f"sha256={problem.origin.source_sha256}"))
            for context, action, reason in problem.history:
                rows.append((f"{problem.ident} {context} {action}", reason))
        return rows

    def remaining_dimension(self) -> list[str]:
        """仍缺什么：保留未知与比较限制，不补猜。"""
        gaps: list[str] = []
        if self.primary and self.primary.report_type == "capture_task_review":
            gaps.append(self.investigation_summary()[1])
        if self.primary_explanation is not None:
            gaps.extend(self.primary_explanation.unknowns)
        for index, addition in enumerate(self.additions, start=1):
            gaps.append(f"补充记录 {index}：{addition.recheck_result}。{addition.recheck_reason}")
            gaps.extend(f"补充记录 {index}：{unknown}"
                        for unknown in addition.explanation.unknowns)
            if addition.comparison_reason != addition.recheck_reason:
                gaps.append(f"补充记录 {index} 比较限制：{addition.comparison_reason}")
        if self.primary is None:
            gaps.append("尚未导入报告；没有可判断的结论。")
        elif not self.additions:
            gaps.append("尚未补充可比较的新结果；复验仍为待结果。")
        return list(dict.fromkeys(gaps))

    def recheck_dimension(self) -> list[tuple[str, str]]:
        if not self.additions:
            return [("复验", RECHECK_PENDING)]
        rows: list[tuple[str, str]] = []
        for index, addition in enumerate(self.additions, start=1):
            rows.append((f"补充记录 {index} 复验", f"{addition.recheck_result}：{addition.recheck_reason}"))
            rows.append((f"补充记录 {index} 比较限制", addition.comparison_reason))
        return rows

    def root_cause_dimension(self) -> list[tuple[str, str]]:
        return [("根因判断", "未知。本程序只整理已有记录，不推断原因，也不给出无依据的置信度。")]


# ---------------------------------------------------------------- 辅助

def _assess_relation(primary: LoadedReport | None, addition: LoadedReport) -> Relation:
    """对任意两份记录核对对象及口径；与主报告比较共用同一规则。"""
    if primary is None:
        return Relation(basis="missing", same_subject=None,
                        question="这份报告是独立的一份，还是刚才那份的后续结果？")

    if primary.report_type != addition.report_type:
        return Relation(
            basis="report_identity", same_subject=False,
            conflict=(f"主报告是 {primary.report_type}，这份是 {addition.report_type}，"
                      f"类型不同，不能当作同一对象的先后结果。"),
        )

    if primary.report_type == "label_baseline":
        first = primary.get("source", "sha256")
        second = addition.get("source", "sha256")
        if valid_sha256(first) and valid_sha256(second):
            if first.lower() != second.lower():
                return Relation(
                    basis="report_identity", same_subject=False,
                    conflict=("两份分析针对的图片内容摘要不同（不是同一张图），"
                              "不能证明之前的问题已恢复。"),
                )
            condition = _label_condition_conflict(primary, addition)
            if condition:
                return Relation(basis="report_identity", same_subject=True,
                                condition_conflict=condition)
            return Relation(basis="report_identity", same_subject=True)
        return Relation(basis="missing", same_subject=None,
                        question="这份分析用的是刚才那张图，还是另一张图？")

    first_run = primary.get("run_id")
    second_run = addition.get("run_id")
    if isinstance(first_run, str) and isinstance(second_run, str):
        if first_run == second_run:
            # 同一标识只是关联依据之一；比较口径不同仍不可直接比较。
            if primary.report_type == "capture_task_review":
                basis_before = primary.get("comparison_basis")
                basis_after = addition.get("comparison_basis")
                if not isinstance(basis_before, str) or not isinstance(basis_after, str):
                    missing = ("两份复核都缺少 comparison_basis"
                               if not isinstance(basis_before, str)
                               and not isinstance(basis_after, str)
                               else "至少一份复核缺少 comparison_basis")
                    return Relation(
                        basis="report_identity", same_subject=True,
                        condition_conflict=(
                            f"{missing}，无法确认两次指标重算口径相同，不能直接比较。"),
                    )
                if basis_before != basis_after:
                    return Relation(
                        basis="report_identity", same_subject=True,
                        condition_conflict=(
                            f"两份复核的 comparison_basis 不同（{basis_before} 与 "
                            f"{basis_after}），指标重算口径可能不同，不能直接比较。"),
                    )
            return Relation(basis="report_identity", same_subject=True)
        return Relation(
            basis="report_identity", same_subject=False,
            conflict=(f"两份记录的 run_id 不同（{first_run[:8]}… 与 {second_run[:8]}…），"
                      f"属于不同批次；不同批次不能证明之前的问题已恢复。"),
        )
    return Relation(basis="missing", same_subject=None,
                    question="这份记录是刚才那个问题的后续结果，还是另一件事的报告？")


def _region_signature(report: LoadedReport) -> list[tuple]:
    """区域范围是对象身份的一部分：同图不同 ROI 或 ROI 消失都不是同一区域。"""
    signature: list[tuple] = []
    for index, summary in enumerate(report.get("decode_summaries", default=[]) or []):
        region = summary.get("region", {}) or {}
        signature.append((
            region.get("kind", f"区域{index}"),
            region.get("x"), region.get("y"),
            region.get("width"), region.get("height"),
        ))
    return signature


def _label_condition_conflict(primary: LoadedReport, addition: LoadedReport) -> str | None:
    """同一张图之外的比较条件：覆盖区域与独立答案必须一致才能比较。"""
    first_regions = _region_signature(primary)
    second_regions = _region_signature(addition)
    if first_regions and second_regions and first_regions != second_regions:
        return ("两份分析覆盖的区域或 ROI 范围不同（"
                f"{len(first_regions)} 个区域与 {len(second_regions)} 个区域），"
                "不能按同一区域比较。")

    first_truth = primary.get("known_truth", default={}) or {}
    second_truth = addition.get("known_truth", default={}) or {}
    first_provided = first_truth.get("status") == "provided"
    second_provided = second_truth.get("status") == "provided"
    if first_provided and not second_provided:
        return ("原报告使用了独立答案，新分析没有独立答案；不能确认内容是否仍与"
                "同一答案一致。")
    if first_provided and second_provided:
        first_sha = first_truth.get("sha256")
        second_sha = second_truth.get("sha256")
        if isinstance(first_sha, str) and isinstance(second_sha, str) and first_sha != second_sha:
            return "两份分析使用的独立答案标识不同，不能直接比较。"
    return None


def _problem_keys(report: LoadedReport) -> dict[str, str]:
    """从报告字段直接提取“问题”标识及可读说明；不使用解释文本做推断。"""
    keys: dict[str, str] = {}
    if report.report_type == "capture_task_review":
        for issue in report.get("issues", default=[]) or []:
            code = issue.get("code")
            frame = issue.get("frame_count")
            label = REVIEW_ISSUE_TEXT.get(code, f"问题码 {code!r}")
            if frame is not None:
                label += f"（帧 {frame}）"
            keys[f"{code}:{frame}"] = label
        if report.get("verification_status") == "not_reviewed":
            keys["not_reviewed"] = "未完成有效复核"
    elif report.report_type == "label_baseline":
        for index, summary in enumerate(report.get("decode_summaries", default=[]) or []):
            decode = summary.get("decode", {}) or {}
            state = decode.get("status")
            kind = (summary.get("region", {}) or {}).get("kind", f"区域{index}")
            if state and state != "decoded":
                keys[f"region{index}:{state}"] = (
                    f"{kind}：{DECODE_TEXT.get(state, f'状态为未预期的 {state!r}')}")
            # 独立答案不一致必须登记为问题；否则整图读出会掩盖内容错误。
            truth_state = (summary.get("truth_check", {}) or {}).get("status")
            if truth_state == "incorrect":
                keys[f"region{index}:truth_incorrect"] = f"{kind}：与独立答案不一致"
    else:
        reason = report.get("stop_reason")
        if report.get("status") != "completed" and isinstance(reason, str):
            keys[f"stop:{reason}"] = STOP_REASON_TEXT.get(reason, f"停止原因 {reason!r}")
    return keys


def _entry_state(report: LoadedReport) -> tuple[str, str] | None:
    """返回 (证据不足 / 未通过 / None, 理由)。未知或未复核不能被当成“没有问题”。"""
    status = report.get("status")
    if report.report_type == "capture_task_review":
        verification = report.get("verification_status")
        if verification == "not_reviewed":
            return (RECHECK_INSUFFICIENT,
                    "这份复核没有完成有效复核，不能用来证明问题消失。")
        if verification not in {"consistent", "inconsistent"}:
            return (RECHECK_INSUFFICIENT,
                    f"复核结论 {verification!r} 不在可评价范围内。")
        if verification == "inconsistent" and not _problem_keys(report):
            return (RECHECK_FAILED,
                    "新结果标记为不一致，但没有列出具体问题码；不能当作没有问题。")
        if verification == "consistent":
            counts = report.get("counts", default=None)
            if counts is None:
                return (RECHECK_INSUFFICIENT,
                        "这份一致性结论没有计数（counts 为 null），"
                        "不能说明覆盖了哪些帧。")
            if counts.get("verified_frames") == 0:
                return (RECHECK_INSUFFICIENT,
                        "这份一致性结论没有核实任何帧（verified_frames 为 0），"
                        "不能用来证明问题消失。")
    elif report.report_type == "label_baseline":
        if status not in {"completed", "completed_with_errors"}:
            return (RECHECK_INSUFFICIENT,
                    f"分析整体状态为 {status!r}，没有可用于比较的完整结果。")
        if not _region_signature(report):
            return (RECHECK_INSUFFICIENT,
                    "这份分析没有区域汇总，没有可比较的基线。")
    elif status != "completed":
        return (RECHECK_INSUFFICIENT,
                f"任务状态为 {status!r}，没有产生可用于比较的完整记录。")
    return None


def _comparison_hazards(report: LoadedReport) -> list[str]:
    """同批次相同标识不能消除的记录级不确定；只影响“通过”的措辞，不阻止暴露新问题。"""
    hazards: list[str] = []
    checks = list(report.warnings)
    if report.report_type == "capture_task_review":
        checks.extend(review_validation_warnings(report.data))
        checks.extend(str(item) for item in (report.get("warnings", default=[]) or []))
    elif report.report_type == "label_baseline":
        checks.extend(label_validation_warnings(report.data))
    for warning in dict.fromkeys(checks):
        hazards.append(f"记录自身校验提示：{warning}")
    if report.report_type == "capture_task_review":
        issues = report.get("issues", default=[]) or []
        for code in ("measurement_context_unavailable", "measurement_context_differs"):
            if any(issue.get("code") == code for issue in issues):
                hazards.append(REVIEW_ISSUE_TEXT[code] + "；比较条件的完整性未知。")
    return hazards


def new_problem_labels(addition: Addition) -> list[str]:
    """新结果中出现、原记录没有登记的问题（可读说明）。"""
    details = _problem_keys(addition.report)
    return [details[key] for key in addition.new_problem_keys if key in details]


def _describe_changes(primary, primary_explanation, addition, addition_explanation) -> list[str]:
    if primary is None:
        return []
    changes: list[str] = []
    if primary.report_type != addition.report_type:
        changes.append("两份报告类型不同，不能逐项比较。")
        return changes
    if primary.report_type == "capture_task_review":
        before = primary.get("verification_status")
        after = addition.get("verification_status")
        if before != after:
            changes.append(f"复核结论从 {before} 变为 {after}。")
        for label, key in (("任务声明样本数", "reported_samples"),
                           ("CSV 配对", "csv_pairs"),
                           ("通过核实帧数", "verified_frames")):
            old, new = primary.get("counts"), addition.get("counts")
            if old is None or new is None:
                changes.append(f"{label}：至少一侧为 null，不能比较。")
            elif old.get(key) != new.get(key):
                changes.append(f"{label}：{old.get(key)} → {new.get(key)}。")
    elif primary.report_type == "label_baseline":
        _append_region_changes(changes, _region_states(primary), _region_states(addition))
        _append_region_changes(
            changes, _region_truth_states(primary), _region_truth_states(addition),
            suffix=" 与独立答案比对",
        )
        old_truth = primary.get("known_truth", "status")
        new_truth = addition.get("known_truth", "status")
        if old_truth != new_truth:
            changes.append(f"独立答案状态：{old_truth} → {new_truth}。")
    else:
        for key in ("status", "stop_reason"):
            if primary.get(key) != addition.get(key):
                changes.append(f"{key}：{primary.get(key)} → {addition.get(key)}。")
    if not changes:
        changes.append("两份记录在已核对的字段上没有差异。")
    return changes


def _region_name(region: dict, index: int) -> str:
    kind = region.get("kind", f"区域{index}")
    if kind == "roi":
        return (f"ROI（x={region.get('x')}, y={region.get('y')}, "
                f"宽={region.get('width')}, 高={region.get('height')}）")
    return str(kind)


def _region_states(report: LoadedReport) -> dict[str, str]:
    states: dict[str, str] = {}
    for index, summary in enumerate(report.get("decode_summaries", default=[]) or []):
        region = summary.get("region", {}) or {}
        states[_region_name(region, index)] = (
            (summary.get("decode", {}) or {}).get("status", "未知"))
    return states


def _region_truth_states(report: LoadedReport) -> dict[str, str]:
    states: dict[str, str] = {}
    for index, summary in enumerate(report.get("decode_summaries", default=[]) or []):
        region = summary.get("region", {}) or {}
        states[_region_name(region, index)] = (
            (summary.get("truth_check", {}) or {}).get("status", "未知"))
    return states


def _append_region_changes(changes: list[str], old: dict[str, str],
                           new: dict[str, str], *, suffix: str = "") -> None:
    for label in sorted(set(old) | set(new)):
        if label not in new:
            changes.append(f"{label}{suffix}：原报告有此区域（{old[label]}），"
                           "新结果没有包含。")
        elif label not in old:
            changes.append(f"{label}{suffix}：新结果新增此区域（{new[label]}），"
                           "原报告没有对应结果。")
        elif old[label] != new[label]:
            changes.append(f"{label}{suffix}：{old[label]} → {new[label]}。")


def _recheck(primary, addition, comparable: bool, reason: str) -> tuple[str, str]:
    if primary is None:
        return RECHECK_INSUFFICIENT, "没有可对照的原始记录。"
    if not comparable:
        return RECHECK_INCOMPARABLE, reason

    if primary.report_type != addition.report_type:
        return RECHECK_INCOMPARABLE, "两份记录类型不同，不能做复验比较。"

    # 先检查新结果能否参与评价，再看旧记录。原记录干净不能跳过新结果的检查。
    addition_blocked = _entry_state(addition)
    if addition_blocked:
        return addition_blocked
    primary_blocked = _entry_state(primary)
    if primary_blocked:
        return RECHECK_INSUFFICIENT, "原始记录不能作为有效基线：" + primary_blocked[1]

    before = _problem_keys(primary)
    after = _problem_keys(addition)

    if after:
        names = list(dict.fromkeys(after.values()))
        if before:
            prefix = "同一对象上仍存在问题："
        else:
            prefix = "新结果出现了原记录中没有登记的问题："
        return RECHECK_FAILED, (prefix + "、".join(names)
                                + "。部分改善不能关闭其他问题。")

    hazards = _comparison_hazards(addition)
    if hazards:
        return RECHECK_INSUFFICIENT, ("新结果没有登记问题，但比较条件仍不完整："
                                      + "；".join(hazards))

    uncovered = _uncovered_problem_frames(primary, addition)
    if uncovered:
        return RECHECK_INSUFFICIENT, (
            "原记录的问题涉及帧 " + "、".join(uncovered)
            + "，但新结果没有核实这些帧；不能把它们当作已消失。")

    uncompared = _uncovered_truth_regions(primary, addition)
    if uncompared:
        return RECHECK_INSUFFICIENT, (
            "原记录中以下区域与独立答案不一致：" + "、".join(uncompared)
            + "；新结果没有完成这些区域的比对，不能当作已恢复。")

    if before:
        return RECHECK_PASSED, ("同一对象上原记录登记的问题在新结果中不再出现；"
                                "这只说明该范围内的问题消失，不说明原因。")
    return RECHECK_PASSED, ("在该对象与本次检查范围内，原记录和新结果都没有登记问题；"
                            "不能外推到其他批次或整台设备。")


def _uncovered_truth_regions(primary, addition) -> list[str]:
    """原记录真值不一致、但新结果没有给出正确/不一致结论的区域。"""
    if primary.report_type != "label_baseline" \
            or addition.report_type != "label_baseline":
        return []
    new_states: dict[int, str] = {}
    for index, summary in enumerate(addition.get("decode_summaries", default=[]) or []):
        new_states[index] = ((summary.get("truth_check", {}) or {}).get("status"))
    uncovered: list[str] = []
    for index, summary in enumerate(primary.get("decode_summaries", default=[]) or []):
        truth = (summary.get("truth_check", {}) or {}).get("status")
        if truth != "incorrect":
            continue
        if new_states.get(index) in {"correct", "incorrect"}:
            continue
        region = summary.get("region", {}) or {}
        label = _region_name(region, index)
        if label not in uncovered:
            uncovered.append(label)
    return uncovered


def _uncovered_problem_frames(primary, addition) -> list[str]:
    """原记录中有问题、但新复核没有实际核实的帧（没有帧号时不做推断）。"""
    if primary.report_type != "capture_task_review" \
            or addition.report_type != "capture_task_review":
        return []
    verified: set[str] = set()
    for frame in addition.get("frames", default=[]) or []:
        if review_frame_verified(frame):
            verified.add(str(frame["frame_count"]))
    uncovered: list[str] = []
    for issue in primary.get("issues", default=[]) or []:
        frame = issue.get("frame_count")
        if frame is None or str(frame) in verified:
            continue
        if str(frame) not in uncovered:
            uncovered.append(str(frame))
    return uncovered


def _same_review_scope(first: LoadedReport, second: LoadedReport) -> bool:
    relation = _assess_relation(first, second)
    return relation.same_subject is True and not relation.condition_conflict


def _problem_scope(problem: ReviewProblem) -> str:
    return f"帧 {problem.frame}" if problem.frame is not None else "原记录检查范围"


def _review_problem_entries(report: LoadedReport) -> list[tuple[str, str, int | None, str]]:
    entries = []
    labels = _problem_keys(report)
    for index, issue in enumerate(report.get("issues", default=[]) or []):
        frame = issue.get("frame_count")
        # 不把未知/无效帧号修正为有效帧号；此类问题按全记录范围保守处理。
        frame = frame if type(frame) is int and frame > 0 else None
        key = f"{issue.get('code')}:{issue.get('frame_count')}"
        entries.append((key, labels[key], frame, f"issues[{index}]"))
    blocked = _entry_state(report)
    hazards = _comparison_hazards(report)
    if hazards:
        entries.append(("record_validation", "记录矛盾或校验条件不完整：" + "；".join(hazards),
                        None, "verification_status / counts / frames / warnings"))
    elif blocked:
        entries.append(("record_state", blocked[1], None, "verification_status / counts"))
    return entries


def _review_problem_gap(problem: ReviewProblem, report: LoadedReport) -> str | None:
    relation = _assess_relation(problem.origin, report)
    if relation.same_subject is not True or relation.condition_conflict:
        return relation.condition_conflict or relation.conflict or "对象/比较口径未知，不能关闭问题"
    blocked = _entry_state(report)
    if blocked:
        return blocked[1]
    hazards = _comparison_hazards(report)
    if hazards:
        return "新结果存在矛盾或未知条件，不能关闭问题：" + "；".join(hazards)
    frames = {frame["frame_count"] for frame in report.get("frames", default=[]) or []
              if review_frame_verified(frame)}
    issues = report.get("issues", default=[]) or []
    if problem.frame is not None:
        if any(type(item.get("frame_count")) is not int for item in issues):
            return "新结果仍有全局或范围未知的问题，不能确认该帧可比条件完整"
        if any(item.get("frame_count") == problem.frame for item in issues):
            return f"帧 {problem.frame} 仍登记问题，需要该帧摘要匹配且五项指标逐项一致的新复核"
        if problem.frame not in frames:
            return f"缺少帧 {problem.frame} 摘要匹配且五项指标逐项一致的核实证据"
        return None
    # 无具体帧号的问题不因一帧正常而消失，要求原报告的范围也被完整覆盖。
    scopes = problem.observed_reports or [problem.origin]
    expected = {frame["frame_count"] for scope in scopes
                for frame in scope.get("frames", default=[]) or []
                if isinstance(frame, dict) and type(frame.get("frame_count")) is int}
    counts = report.get("counts") or {}
    largest_scope = max((scope.get("counts") or {}).get("reported_samples", 0) for scope in scopes)
    if (report.get("verification_status") != "consistent" or issues or not frames
            or not expected.issubset(frames)
            or counts.get("reported_samples", -1) < largest_scope):
        return "缺少覆盖原记录全部相关帧及计数范围、口径一致且无矛盾的复核证据"
    return None
