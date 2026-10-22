"""补充结果后的步骤反馈：归属、转换与隔离。

缺陷复现（2026-10-19 审核）：
  主报告 review-consistent，补充 review-missing-image 后当前卡为
  g2.frame.find-image / “补充记录 1”；记录“做不了或不确定”后卡片不变，
  记录“已做完”后仍重复索取同一步。
"""

from __future__ import annotations

import unittest

from . import synthetic  # noqa: F401

from investigator.explain import explain_report
from investigator.export import render_markdown
from investigator.guides import (
    FEEDBACK_BLOCKED,
    FEEDBACK_DONE,
    FEEDBACK_STILL,
    current_card,
)
from investigator.reports import LoadedReport
from investigator.session import RECHECK_FAILED, Session


def load(payload: dict, name: str = "synthetic.json") -> LoadedReport:
    return LoadedReport(
        source_name=name,
        source_sha256=(name[0] * 64),
        size_bytes=1,
        report_type=payload["report_type"],
        schema_version=payload["schema_version"],
        data=payload,
    )


MISSING_IMAGE = dict(
    verification_status="inconsistent",
    issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "缺少留证图片"}],
    counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
    frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
)


def start(session: Session, payload: dict, name: str) -> LoadedReport:
    report = load(payload, name)
    session.load_primary(report, explain_report(report))
    return report


def add(session: Session, payload: dict, name: str):
    report = load(payload, name)
    return session.add_addition(report, explain_report(report))


def session_with_missing_image() -> Session:
    """Codex 复现路径：正常复核 → 补充缺图复核。"""
    session = Session()
    start(session, synthetic.capture_review_report(), "consistent.json")
    add(session, synthetic.capture_review_report(**MISSING_IMAGE), "broken.json")
    return session


class AdditionCardFeedbackTests(unittest.TestCase):
    def test_blocked_on_addition_moves_to_handoff(self) -> None:
        session = session_with_missing_image()
        card = current_card(session)
        self.assertEqual(card.context, "补充记录 1")
        self.assertEqual(card.step_id, "g2.frame.find-image")
        self.assertIn((FEEDBACK_BLOCKED, "做不了或不确定"), card.feedback_choices)

        session.add_step_feedback(card, FEEDBACK_BLOCKED)

        next_card = current_card(session)
        self.assertEqual(next_card.step_id, "handoff.save")
        self.assertEqual(next_card.context, "补充记录 1")
        self.assertIn("做不了或不确定", next_card.related)
        self.assertIn("保存", next_card.title)

    def test_done_on_addition_does_not_repeat_same_step(self) -> None:
        session = session_with_missing_image()
        card = current_card(session)
        self.assertEqual(card.step_id, "g2.frame.find-image")

        session.add_step_feedback(card, FEEDBACK_DONE)

        next_card = current_card(session)
        self.assertNotEqual(next_card.step_id, "g2.frame.find-image")
        self.assertEqual(next_card.step_id, "after.observation")
        self.assertIn("已由你记录完成", next_card.related)
        # 不再把同一步骤作为“现在做什么”索取：卡片标题换成等待新结果
        self.assertEqual(next_card.title, "已记录你的观察；需要核对变化时再添加新结果")

    def test_done_on_first_addition_step_moves_to_next_step(self) -> None:
        """同一份补充记录有两步时，做完第一步应给出第二步，而不是等待/交接。"""
        session = Session()
        start(session, synthetic.capture_review_report(), "consistent.json")
        add(session, synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[
                {"code": "frame_unverifiable", "frame_count": 2, "detail": "缺少留证图片"},
                {"code": "metric_mismatch", "frame_count": 1, "detail": "亮度不同"},
            ],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 0},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics(different=True)}],
        ), "two-issues.json")
        card = current_card(session)
        self.assertEqual(card.step_id, "g2.frame.find-image")
        session.add_step_feedback(card, FEEDBACK_DONE)
        next_card = current_card(session)
        self.assertEqual(next_card.step_id, "g2.metric.context")
        self.assertEqual(next_card.context, "补充记录 1")

    def test_still_keeps_declaration_without_upgrading_recheck(self) -> None:
        session = session_with_missing_image()
        card = current_card(session)
        recheck_before = session.recheck_dimension()
        root_before = session.root_cause_dimension()

        session.add_step_feedback(card, FEEDBACK_STILL)

        self.assertEqual(session.recheck_dimension(), recheck_before)
        self.assertTrue(dict(session.recheck_dimension())["补充记录 1 复验"]
                        .startswith(session.additions[0].recheck_result))
        self.assertEqual(session.additions[0].recheck_result, RECHECK_FAILED)
        self.assertEqual(session.root_cause_dimension(), root_before)
        next_card = current_card(session)
        self.assertEqual(next_card.step_id, "after.observation")
        self.assertIn("问题仍在", next_card.note)
        self.assertIn("用户声明", next_card.note)

    def test_feedback_is_scoped_to_investigation_context_and_version(self) -> None:
        session = session_with_missing_image()
        card = current_card(session)
        feedback = session.add_step_feedback(card, FEEDBACK_DONE)

        addition = session.additions[0]
        self.assertEqual(feedback.investigation_id, session.investigation_id)
        self.assertEqual(feedback.context, "补充记录 1")
        self.assertEqual(feedback.guide_version, card.guide_version)
        self.assertEqual(feedback.step_id, card.step_id)
        self.assertEqual(feedback.source_sha256, addition.report.source_sha256)

        # 同一步骤在另一个上下文里查不到这条反馈
        self.assertIsNone(session.latest_feedback(
            "g2.frame.find-image", context="补充记录 2", guide_version=card.guide_version))
        self.assertIsNotNone(session.latest_feedback(
            "g2.frame.find-image", context="补充记录 1", guide_version=card.guide_version))
        # 指引版本不同也不匹配
        self.assertIsNone(session.latest_feedback(
            "g2.frame.find-image", context="补充记录 1", guide_version="2000-01-01.0"))


class FeedbackIsolationTests(unittest.TestCase):
    def test_later_addition_same_step_does_not_inherit_feedback(self) -> None:
        session = session_with_missing_image()
        first = current_card(session)
        self.assertEqual(first.context, "补充记录 1")
        session.add_step_feedback(first, FEEDBACK_DONE)

        add(session, synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 3, "detail": "缺少留证图片"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
        ), "later.json")

        second = current_card(session)
        self.assertEqual(second.context, "补充记录 2")
        self.assertEqual(second.step_id, "g2.frame.find-image")
        self.assertNotIn("已由你记录完成", second.related)
        self.assertIn(session.additions[1].recheck_reason, second.note)

    def test_primary_feedback_does_not_apply_to_addition(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(), "consistent.json")
        add(session, synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "缺少留证图片"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
        ), "broken.json")
        # 人为在“主报告”上下文记录同一步骤的反馈
        primary_card = current_card(session)
        primary_card = type(primary_card)(
            step=primary_card.step, context="主报告", note="")
        session.add_step_feedback(primary_card, FEEDBACK_DONE)

        card = current_card(session)
        self.assertEqual(card.context, "补充记录 1")
        self.assertNotIn("已由你记录完成", card.related)

    def test_new_investigation_clears_feedback_and_suggestions(self) -> None:
        session = session_with_missing_image()
        card = current_card(session)
        session.record_suggestion(card)
        feedback = session.add_step_feedback(card, FEEDBACK_DONE)
        old_id = session.investigation_id
        old_feedback = list(session.feedbacks)

        start(session, synthetic.label_baseline_report(), "new.json")

        self.assertNotEqual(session.investigation_id, old_id)
        self.assertEqual(session.feedbacks, [])
        self.assertEqual(session.suggestions, [])
        self.assertTrue(all(item.investigation_id == old_id for item in old_feedback))

    def test_feedback_history_kept_within_same_investigation(self) -> None:
        session = session_with_missing_image()
        first = current_card(session)
        recorded = session.add_step_feedback(first, FEEDBACK_DONE)
        add(session, synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 3, "detail": "缺少留证图片"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
        ), "later.json")
        self.assertIn(recorded, session.feedbacks)


class PrimaryFeedbackRegressionTests(unittest.TestCase):
    def test_primary_blocked_still_moves_to_handoff(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "broken.json")
        card = current_card(session)
        self.assertEqual(card.context, "主报告")
        session.add_step_feedback(card, FEEDBACK_BLOCKED)
        self.assertEqual(current_card(session).step_id, "handoff.save")

    def test_primary_done_moves_to_observation(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "broken.json")
        card = current_card(session)
        session.add_step_feedback(card, FEEDBACK_DONE)
        next_card = current_card(session)
        self.assertEqual(next_card.step_id, "after.observation")
        self.assertIn("已由你记录完成", next_card.related)


class ExportOwnershipTests(unittest.TestCase):
    def test_export_shows_feedback_context_and_matches_current_card(self) -> None:
        session = session_with_missing_image()
        card = current_card(session)
        session.add_step_feedback(card, FEEDBACK_BLOCKED)

        text = render_markdown(session)
        export_card = current_card(session)

        self.assertIn("步骤反馈", text)
        self.assertIn("补充记录 1", text)
        self.assertIn("做不了或不确定", text)
        self.assertIn("未独立验证", text)
        self.assertIn(export_card.step_id, text)
        self.assertIn(export_card.title, text)
        # 复验与根因不因用户反馈改变
        self.assertIn("未通过", text)
        self.assertIn("根因判断 | 未知", text)
        self.assertIn("比较限制", text)

    def test_export_separates_feedback_from_second_addition(self) -> None:
        session = session_with_missing_image()
        first = current_card(session)
        session.add_step_feedback(first, FEEDBACK_DONE)
        add(session, synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 3, "detail": "缺少留证图片"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
        ), "later.json")
        text = render_markdown(session)
        rows = session.user_feedback_dimension()
        self.assertTrue(any("补充记录 1" in value for _, value in rows))
        self.assertFalse(any("补充记录 2" in value for _, value in rows))
        # 当前卡指向补充记录 2 的步骤，不被第一份记录的“已做完”吞掉
        self.assertIn("补充记录 2", text)
        self.assertIn("g2.frame.find-image", text)


if __name__ == "__main__":
    unittest.main()
