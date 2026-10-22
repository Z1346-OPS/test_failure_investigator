"""调查记录测试：关联、比较、复验与五维分离。"""

from __future__ import annotations

import hashlib
import unittest

from . import synthetic  # noqa: F401

from investigator.explain import explain_report
from investigator.reports import LoadedReport
from investigator.session import (
    RECHECK_FAILED,
    RECHECK_INCOMPARABLE,
    RECHECK_INSUFFICIENT,
    RECHECK_PASSED,
    RECHECK_PENDING,
    Session,
)


def load(payload: dict, name: str = "synthetic.json") -> LoadedReport:
    return LoadedReport(
        source_name=name,
        # 摘要按文件名派生：不同文件得到不同摘要，同名文件才是重复导入。
        source_sha256=hashlib.sha256(name.encode("utf-8")).hexdigest(),
        size_bytes=1,
        report_type=payload["report_type"],
        schema_version=payload["schema_version"],
        data=payload,
    )


def start(session: Session, payload: dict, name: str = "synthetic.json") -> LoadedReport:
    report = load(payload, name)
    session.load_primary(report, explain_report(report))
    return report


MISSING_IMAGE = dict(
    verification_status="inconsistent",
    issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "缺少留证图片"}],
    counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
    frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
)


class RelationTests(unittest.TestCase):
    def test_different_batch_cannot_prove_recovery(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE))
        other = load(synthetic.capture_review_report(run_id="other" + "0" * 27), "other.json")
        addition = session.add_addition(other, explain_report(other))
        self.assertFalse(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)
        self.assertIn("不能证明之前的问题已恢复", addition.comparison_reason)

    def test_same_run_id_is_comparable_and_passes_when_clean(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE))
        fixed = load(synthetic.capture_review_report(verification_status="consistent"),
                     "later.json")
        addition = session.add_addition(fixed, explain_report(fixed))
        self.assertTrue(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_PASSED)
        self.assertIn("不说明原因", addition.recheck_reason)

    def test_partial_improvement_stays_failed(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 1, "detail": "x"},
                    {"code": "frame_unverifiable", "frame_count": 2, "detail": "y"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 0},
            frames=[]))
        partial = load(synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "y"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}]),
            "later.json")
        addition = session.add_addition(partial, explain_report(partial))
        self.assertTrue(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_FAILED)
        self.assertIn("部分改善不能关闭其他问题", addition.recheck_reason)

    def test_user_assertion_does_not_override_objective_conflict(self) -> None:
        """用户说“是同一件事”，但 run_id 不同：记录声明，仍按记录判定不可比。"""
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE))
        other = load(synthetic.capture_review_report(run_id="other" + "0" * 27), "other.json")
        addition = session.add_addition(other, explain_report(other), relation_answer="yes")
        self.assertFalse(addition.comparable)
        self.assertEqual(addition.relation.basis, "report_identity")
        self.assertIsNotNone(addition.relation.conflict)
        self.assertIn("不能据此证明", addition.comparison_reason)
        # 用户声明被记录，但没有覆盖客观冲突
        self.assertIn("你说明这是同一件事", addition.comparison_reason)

    def test_uncertain_answer_keeps_incomparable(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE))
        other = load(synthetic.capture_review_report(run_id="other" + "0" * 27), "other.json")
        addition = session.add_addition(other, explain_report(other), relation_answer="unsure")
        self.assertFalse(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)

    def test_different_image_is_incomparable(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(image_sha=synthetic.SYNTHETIC_IMAGE_SHA))
        other = load(synthetic.label_baseline_report(image_sha=synthetic.OTHER_IMAGE_SHA), "other.json")
        addition = session.add_addition(other, explain_report(other))
        self.assertFalse(addition.comparable)
        self.assertIn("不是同一张图", addition.relation.conflict)

    def test_same_image_roi_recovery(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "not_provided"),
                     ("roi", "decode_error", "decode_error", {"x": 1, "y": 1, "width": 10, "height": 10})),
            status="completed_with_errors"))
        fixed = load(synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "not_provided"),
                     ("roi", "decoded", "not_provided", {"x": 1, "y": 1, "width": 10, "height": 10}))),
            "later.json")
        addition = session.add_addition(fixed, explain_report(fixed))
        self.assertTrue(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_PASSED)

    def test_question_asked_only_when_identity_missing(self) -> None:
        """能从记录确定的内容不再问用户；只有标识缺失才问一个问题。"""
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE))
        # 同一 run_id：记录已确定，不问
        same = load(synthetic.capture_review_report(), "same.json")
        self.assertIsNone(session.assess_relation(same).question)
        # 不同 run_id：记录已确定属于不同批次，也不问，直接给出限制
        other = load(synthetic.capture_review_report(run_id="other" + "0" * 27), "other.json")
        relation = session.assess_relation(other)
        self.assertIsNone(relation.question)
        self.assertIsNotNone(relation.conflict)

    def test_question_asked_when_qr_image_identity_missing(self) -> None:
        session = Session()
        payload = synthetic.label_baseline_report()
        del payload["source"]["sha256"]
        report = load(payload, "noident.json")
        session.load_primary(report, explain_report(report))
        without_identity = synthetic.label_baseline_report()
        del without_identity["source"]["sha256"]
        addition = load(without_identity, "later.json")
        relation = session.assess_relation(addition)
        self.assertIsNotNone(relation.question)
        self.assertIsNone(relation.same_subject)


class RecheckMatrixTests(unittest.TestCase):
    """复验必须检查新结果；原记录干净不能跳过新结果的检查。"""

    def test_normal_then_abnormal_is_not_passed(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(), "normal.json")
        broken = load(synthetic.capture_review_report(**MISSING_IMAGE), "broken.json")
        addition = session.add_addition(broken, explain_report(broken))
        self.assertTrue(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_FAILED)
        self.assertIn("无法核实", addition.recheck_reason)
        self.assertNotIn("本次同样没有登记问题", addition.recheck_reason)

    def test_normal_then_normal_passes_only_in_scope(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(), "normal.json")
        again = load(synthetic.capture_review_report(), "normal-later.json")
        addition = session.add_addition(again, explain_report(again))
        self.assertEqual(addition.recheck_result, RECHECK_PASSED)
        self.assertIn("范围内", addition.recheck_reason)

    def test_not_reviewed_addition_is_insufficient_not_passed(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(), "normal.json")
        empty = load(synthetic.capture_review_report(
            verification_status="not_reviewed", counts=None, frames=[]), "empty.json")
        addition = session.add_addition(empty, explain_report(empty))
        self.assertEqual(addition.recheck_result, RECHECK_INSUFFICIENT)
        self.assertIn("没有完成有效复核", addition.recheck_reason)

    def test_inconsistent_without_issue_codes_is_not_passed(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(), "normal.json")
        opaque = load(synthetic.capture_review_report(
            verification_status="inconsistent", issues=[]), "opaque.json")
        addition = session.add_addition(opaque, explain_report(opaque))
        self.assertEqual(addition.recheck_result, RECHECK_FAILED)
        self.assertIn("没有列出具体问题码", addition.recheck_reason)

    def test_different_comparison_basis_is_incomparable(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(), "normal.json")
        payload = synthetic.capture_review_report(verification_status="not_reviewed",
                                                  counts=None, frames=[])
        payload["comparison_basis"] = "legacy_algorithm_two_decimals"
        other_basis = load(payload, "other-basis.json")
        addition = session.add_addition(other_basis, explain_report(other_basis))
        self.assertFalse(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)
        self.assertIn("comparison_basis", addition.comparison_reason)


class NewInvestigationTests(unittest.TestCase):
    def test_load_primary_starts_fresh_investigation(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "first.json")
        session.add_note("只属于第一份调查的说明")
        other = load(synthetic.capture_review_report(run_id="other" + "0" * 27), "other.json")
        session.add_addition(other, explain_report(other))
        old_id = session.investigation_id
        self.assertTrue(session.has_unsaved_content())

        start(session, synthetic.label_baseline_report(), "second.json")

        self.assertNotEqual(session.investigation_id, old_id)
        self.assertEqual(session.notes, [])
        self.assertEqual(session.additions, [])
        self.assertFalse(session.has_unsaved_content())
        feedback = session.user_feedback_dimension()
        self.assertTrue(all("只属于第一份调查" not in value for _, value in feedback))


class RepeatImportTests(unittest.TestCase):
    def test_repeat_import_adds_no_new_evidence(self) -> None:
        session = Session()
        first = load(synthetic.capture_review_report(), "same.json")
        session.load_primary(first, explain_report(first))
        again = load(synthetic.capture_review_report(), "same.json")
        addition = session.add_addition(again, explain_report(again))
        self.assertTrue(addition.is_repeat)
        self.assertEqual(addition.recheck_result, RECHECK_INSUFFICIENT)
        self.assertIn("没有新增证据", addition.recheck_reason)

    def test_conflicting_same_run_id_keeps_both(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "first.json")
        conflict = load(synthetic.capture_review_report(verification_status="consistent"),
                        "second.json")
        session.add_addition(conflict, explain_report(conflict))
        self.assertEqual(len(session.additions), 1)
        self.assertEqual(session.primary.get("verification_status"), "inconsistent")


class DimensionTests(unittest.TestCase):
    def test_five_dimensions_are_separate(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE))
        session.add_note("我把图片目录重新拷了一遍，看起来好了")

        execution = dict(session.execution_dimension())
        self.assertIn("未执行", execution["助手本次执行"])

        feedback = session.user_feedback_dimension()
        self.assertTrue(any("未独立验证" in value for _, value in feedback))

        # 用户反馈不能变成复验结果
        recheck = dict(session.recheck_dimension())
        self.assertEqual(recheck["复验"], RECHECK_PENDING)
        self.assertNotIn("通过", recheck["复验"])

        root_cause = dict(session.root_cause_dimension())
        self.assertIn("未知", root_cause["根因判断"])

        business = session.business_dimension()
        self.assertTrue(any("无法核实" in item for item in business))

    def test_user_feedback_does_not_upgrade_recheck(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE))
        session.add_note("应该已经修好了")
        self.assertEqual(dict(session.recheck_dimension())["复验"], RECHECK_PENDING)

    def test_empty_note_rejected(self) -> None:
        session = Session()
        with self.assertRaises(ValueError):
            session.add_note("   ")

    def test_unsaved_flag_tracks_content(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report())
        self.assertFalse(session.has_unsaved_content())
        session.add_note("备注")
        self.assertTrue(session.has_unsaved_content())
        session.mark_saved()
        self.assertFalse(session.has_unsaved_content())


if __name__ == "__main__":
    unittest.main()
