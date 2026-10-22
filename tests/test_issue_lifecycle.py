"""回归：通过真实读取器验证调查问题累积与帧级证据。"""
import tempfile
import unittest
from pathlib import Path

from tests import synthetic
from investigator.reports import load_report
from investigator.explain import explain_report
from investigator.session import Session, RECHECK_PASSED
from investigator.guides import current_card, AFTER_PASSED
from investigator.export import short_conclusion, render_markdown

METRICS = ("brightness", "dark_ratio", "bright_ratio", "sharpness", "contrast")


def verified_frame(number):
    return {"frame_count": number, "image_sha256_match": True,
            "metrics": {name: ["100.0", "100.0"] for name in METRICS}}


def review(numbers=(1, 2), *, issues=(), tag="initial"):
    frames = [verified_frame(number) for number in numbers]
    for issue in issues:
        number = issue.get("frame_count")
        if type(number) is int and number not in numbers:
            frames.append({"frame_count": number, "image_sha256_match": None, "metrics": None})
    payload = synthetic.capture_review_report(
        verification_status="inconsistent" if issues else "consistent",
        issues=issues,
        counts={"reported_samples": len(frames),
                "csv_pairs": len(frames), "verified_frames": len(numbers)},
        frames=frames)
    payload["test_marker"] = tag
    return payload


def missing(number):
    return {"code": "frame_unverifiable", "frame_count": number, "detail": "合成缺图"}


class IssueLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="issue-lifecycle-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.session = Session()
        self.index = 0

    def read(self, payload):
        self.index += 1
        path = synthetic.write_report(self.root / f"{self.index}.json", payload)
        return load_report(path)

    def start(self, payload):
        report = self.read(payload)
        self.session.load_primary(report, explain_report(report))
        return report

    def add(self, payload):
        report = self.read(payload)
        return self.session.add_addition(report, explain_report(report))

    def test_intermediate_missing_frame_survives_later_partial_normal(self):
        self.start(review())
        self.add(review((1,), issues=[missing(2)], tag="missing"))
        self.add(review((1,), tag="partial"))
        conclusion = short_conclusion(self.session)
        self.assertIn("未解决", conclusion)
        self.assertIn("帧 2", conclusion)
        self.assertNotEqual(current_card(self.session).step_id, AFTER_PASSED.step_id)
        self.assertIn("未解决", render_markdown(self.session))

    def test_listed_but_unverified_frame_is_not_recovery(self):
        self.start(review((1,), issues=[missing(2)], tag="missing"))
        payload = review(tag="contradictory")
        payload["frames"][1]["image_sha256_match"] = False
        payload["frames"][1]["metrics"] = None
        addition = self.add(payload)
        self.assertNotEqual(addition.recheck_result, RECHECK_PASSED)
        self.assertTrue(addition.report.warnings)
        self.assertIn("矛盾", short_conclusion(self.session))


    def active_frames(self):
        return {problem.frame for problem in self.session.unresolved_review_problems()}

    def test_full_later_evidence_resolves_intermediate_problem_and_keeps_comparisons(self):
        original = self.start(review())
        failed = self.add(review((1,), issues=[missing(2)], tag="missing"))
        partial = self.add(review((1,), tag="partial"))
        failed_result = (failed.recheck_result, failed.recheck_reason)
        self.add(review(tag="full-again"))
        self.assertEqual(self.active_frames(), set())
        self.assertEqual(self.session.investigation_summary()[0], RECHECK_PASSED)
        self.assertEqual(current_card(self.session).step_id, AFTER_PASSED.step_id)
        self.assertIs(self.session.primary, original)
        self.assertEqual((failed.recheck_result, failed.recheck_reason), failed_result)
        self.assertEqual(len(self.session.additions), 3)
        self.assertTrue(any(event[1] == "范围内不再出现"
                            for problem in self.session.review_problems() for event in problem.history))
        exported = render_markdown(self.session)
        self.assertIn("调查问题历史", exported)
        self.assertIn(failed.report.source_sha256, exported)
        self.assertIn("仅与主报告的单次比较", short_conclusion(self.session))

    def test_multiple_problems_only_covered_one_resolves(self):
        self.start(review((1,), issues=[missing(2), missing(3)], tag="both"))
        self.add(review((2,), tag="only-2"))
        self.assertEqual(self.active_frames(), {3})
        self.assertIn("帧 3", self.session.investigation_summary()[1])
        closed = [problem for problem in self.session.review_problems() if problem.frame == 2][0]
        self.assertIsNotNone(closed.resolved_by)
        self.assertNotEqual(current_card(self.session).step_id, AFTER_PASSED.step_id)

    def test_separate_valid_reports_can_resolve_all_registered_scopes(self):
        self.start(review((1,), issues=[missing(2), missing(3)], tag="both"))
        self.add(review((2,), tag="only-2"))
        latest = self.add(review((3,), tag="only-3"))
        # 这次对主报告的比较仍缺帧 2；调查已经分别取得帧 2/3 的证据。
        self.assertNotEqual(latest.recheck_result, RECHECK_PASSED)
        self.assertEqual(self.active_frames(), set())
        self.assertEqual(self.session.investigation_summary()[0], RECHECK_PASSED)
        self.assertEqual(current_card(self.session).step_id, AFTER_PASSED.step_id)
        self.assertIn("均有后续可比证据", short_conclusion(self.session))

    def test_closed_problem_reappears_with_new_evidence(self):
        self.start(review((1,), issues=[missing(2)], tag="missing"))
        self.add(review(tag="fixed"))
        self.assertEqual(self.active_frames(), set())
        self.add(review((1,), issues=[missing(2)], tag="reappeared-new-bytes"))
        self.assertEqual(self.active_frames(), {2})
        history = self.session.review_problems()[0].history
        self.assertIn("范围内不再出现", [event[1] for event in history])
        self.assertIn("重新出现", [event[1] for event in history])

    def test_incomparable_unknown_and_conflicting_results_cannot_close(self):
        for kind in ("batch", "basis", "missing_basis", "unknown", "not_reviewed",
                     "counts", "task_status", "warnings", "duplicate_frames"):
            with self.subTest(kind=kind):
                self.session = Session()
                self.start(review((1,), issues=[missing(2)], tag="missing"))
                payload = review(tag=kind)
                if kind == "batch":
                    payload["run_id"] = "b" * 32
                elif kind == "basis":
                    payload["comparison_basis"] = "different"
                elif kind == "missing_basis":
                    del payload["comparison_basis"]
                elif kind == "unknown":
                    payload["verification_status"] = "future_status"
                elif kind == "not_reviewed":
                    payload["verification_status"] = "not_reviewed"
                    payload["counts"] = None
                    payload["frames"] = []
                elif kind == "counts":
                    payload["counts"]["verified_frames"] = 1
                elif kind == "task_status":
                    payload["task_status"] = "failed"
                elif kind == "warnings":
                    payload["warnings"] = [{"code": "measurement_context_differs"}]
                else:
                    payload["frames"].append(verified_frame(2))
                    payload["counts"] = dict(reported_samples=3, csv_pairs=3, verified_frames=3)
                self.add(payload)
                self.assertIn(2, self.active_frames())
                self.assertNotEqual(self.session.investigation_summary()[0], RECHECK_PASSED)

    def test_empty_or_unrecognized_shared_basis_cannot_close(self):
        for basis in ("", "future_unknown_basis"):
            with self.subTest(basis=basis):
                self.session = Session()
                original = review((1,), issues=[missing(2)], tag="missing")
                original["comparison_basis"] = basis
                self.start(original)
                later = review(tag="normal")
                later["comparison_basis"] = basis
                self.add(later)
                self.assertIn(2, self.active_frames())
                self.assertNotEqual(self.session.investigation_summary()[0], RECHECK_PASSED)

    def test_same_primary_basis_cannot_close_issue_from_another_basis(self):
        self.start(review())
        changed = review((1,), issues=[missing(2)], tag="other-basis")
        changed["comparison_basis"] = "other"
        self.add(changed)
        self.add(review(tag="primary-basis"))
        self.assertIn(2, self.active_frames())
        self.assertIn("comparison_basis", short_conclusion(self.session))

    def test_feedback_repeat_and_save_do_not_close(self):
        original_payload = review()
        self.start(original_payload)
        self.add(review((1,), issues=[missing(2)], tag="missing"))
        before = self.session.problem_history_dimension()
        self.session.add_note("用户认为已修好")
        card = current_card(self.session)
        if card.feedback_choices:
            self.session.add_step_feedback(card, card.feedback_choices[0][0])
        self.session.mark_saved()
        repeated = self.add(original_payload)
        self.assertTrue(repeated.is_repeat)
        self.assertEqual(before, self.session.problem_history_dimension())
        self.assertEqual(self.active_frames(), {2})
        self.assertIn("重复导入", short_conclusion(self.session))

    def test_all_frame_failure_variants_are_not_verified_or_recovery(self):
        for kind in ("hash_false", "hash_unknown", "hash_missing", "null_metrics",
                     "empty_metrics", "missing_metric", "different_metric", "numeric_pair",
                     "nonfinite_metric"):
            with self.subTest(kind=kind):
                self.session = Session()
                self.start(review((1,), issues=[missing(2)], tag="missing"))
                payload = review(tag=kind)
                frame = payload["frames"][1]
                if kind == "hash_false":
                    frame["image_sha256_match"] = False
                elif kind == "hash_unknown":
                    frame["image_sha256_match"] = None
                elif kind == "hash_missing":
                    del frame["image_sha256_match"]
                elif kind == "null_metrics":
                    frame["metrics"] = None
                elif kind == "empty_metrics":
                    frame["metrics"] = {}
                elif kind == "missing_metric":
                    del frame["metrics"]["contrast"]
                elif kind == "different_metric":
                    frame["metrics"]["brightness"] = ["100.0", "101.0"]
                elif kind == "numeric_pair":
                    frame["metrics"]["brightness"] = [100.0, 100.0]
                else:
                    frame["metrics"]["brightness"] = ["nan", "nan"]
                addition = self.add(payload)
                self.assertNotEqual(addition.recheck_result, RECHECK_PASSED)
                self.assertIn(2, self.active_frames())
                self.assertTrue(addition.report.warnings)
                self.assertEqual(addition.report.data["frames"][1], frame)
                findings = " ".join(addition.explanation.findings)
                self.assertIn("校验", findings)
                self.assertNotIn("本次检查范围内，记录与重算结果一致", findings)

    def test_valid_complete_frame_facts_allow_scoped_recovery_without_warnings(self):
        self.start(review((1,), issues=[missing(2)], tag="missing"))
        addition = self.add(review(tag="verified"))
        self.assertEqual(addition.report.warnings, [])
        self.assertEqual(addition.recheck_result, RECHECK_PASSED)
        self.assertEqual(self.session.investigation_summary()[0], RECHECK_PASSED)

    def test_failed_frame_rows_do_not_make_legitimate_inconsistent_counts_contradictory(self):
        self.start(review((1,), issues=[missing(2)], tag="missing"))
        payload = review((2,), issues=[missing(1)], tag="frame2-verified-frame1-failed")
        addition = self.add(payload)
        self.assertEqual(addition.report.warnings, [])
        self.assertNotIn(2, self.active_frames())
        self.assertIn(1, self.active_frames())

    def test_frame_issue_contradicting_positive_facts_cannot_close_another_problem(self):
        for code in ("metric_mismatch", "image_hash_mismatch", "frame_unverifiable"):
            with self.subTest(code=code):
                self.session = Session()
                self.start(review((1,), issues=[missing(2)], tag="missing"))
                payload = review(tag=code)
                payload["verification_status"] = "inconsistent"
                payload["issues"] = [{"code": code, "frame_count": 1}]
                addition = self.add(payload)
                self.assertIn(2, self.active_frames())
                self.assertTrue(addition.report.warnings)
                self.assertIn("矛盾", short_conclusion(self.session))

    def test_global_unknown_scope_cannot_close_frame_issue(self):
        self.start(review((1,), issues=[missing(2)], tag="missing"))
        payload = review(tag="context-unknown")
        payload["verification_status"] = "inconsistent"
        payload["issues"] = [{"code": "measurement_context_unavailable", "frame_count": None}]
        self.add(payload)
        self.assertIn(2, self.active_frames())

    def test_global_problem_needs_full_scope(self):
        self.start(review((1, 2), issues=[
            {"code": "csv_keys_mismatch", "frame_count": None}], tag="global"))
        self.add(review((1,), tag="shrunk"))
        self.assertTrue(self.session.unresolved_review_problems())
        self.add(review((1, 2, 3), tag="full"))
        self.assertFalse(self.session.unresolved_review_problems())

    def test_repeated_global_problem_retains_newly_expanded_scope(self):
        issue = {"code": "csv_keys_mismatch", "frame_count": None}
        self.start(review((1, 2), issues=[issue], tag="scope-2"))
        self.add(review((1, 2, 3), issues=[issue], tag="scope-3"))
        self.add(review((1, 2), tag="partial"))
        self.assertTrue(self.session.unresolved_review_problems())
        self.assertNotEqual(self.session.investigation_summary()[0], RECHECK_PASSED)
        self.add(review((1, 2, 3), tag="all-scopes"))
        self.assertFalse(self.session.unresolved_review_problems())
        self.assertEqual(self.session.investigation_summary()[0], RECHECK_PASSED)

    def test_new_investigation_clears_problem_state_without_mutating_old_records(self):
        self.start(review((1,), issues=[missing(2)], tag="missing"))
        addition = self.add(review((1,), tag="partial"))
        old_id = self.session.investigation_id
        history = self.session.problem_history_dimension()
        failed_copy = (addition.recheck_result, addition.recheck_reason)
        self.start(review(tag="new-investigation"))
        self.assertNotEqual(self.session.investigation_id, old_id)
        self.assertEqual(self.session.review_problems(), [])
        self.assertEqual(self.session.additions, [])
        self.assertTrue(history)
        self.assertEqual((addition.recheck_result, addition.recheck_reason), failed_copy)

    def test_card_export_summary_and_history_agree_while_local_comparison_is_retained(self):
        self.start(review())
        failed = self.add(review((1,), issues=[missing(2)], tag="missing"))
        local = self.add(review((1,), tag="partial"))
        self.assertEqual(local.recheck_result, RECHECK_PASSED)  # 主报告原本无问题。
        card = current_card(self.session)
        summary = self.session.investigation_summary()[1]
        self.assertIn(summary, card.note)
        self.assertIn(summary, short_conclusion(self.session))
        exported = render_markdown(self.session)
        self.assertIn(summary, exported)
        self.assertIn(failed.report.source_sha256, exported)
        self.assertIn("缺少帧 2", exported)
        self.assertNotEqual(card.step_id, AFTER_PASSED.step_id)
        self.assertIn("单次比较", exported)


if __name__ == "__main__":
    unittest.main()
