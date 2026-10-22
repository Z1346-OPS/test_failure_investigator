"""提交前审查缺陷的回归：真实文件读取、状态判断和导出。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import synthetic
from investigator.explain import explain_report
from investigator.export import render_markdown, scrub
from investigator.guides import current_card
from investigator.reports import ReportError, load_report
from investigator.session import Session, RECHECK_PASSED


class CloseoutRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="closeout-regression-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.serial = 0

    def load(self, data):
        self.serial += 1
        path = self.root / f"report-{self.serial}.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return load_report(path)

    def session(self, data):
        report = self.load(data)
        session = Session()
        session.load_primary(report, explain_report(report))
        return session

    def add(self, session, data):
        report = self.load(data)
        return session.add_addition(report, explain_report(report))

    def test_capture_nested_wrong_types_are_controlled_rejections(self):
        for key, values in (("timings", (None, [], "bad", 1)),
                            ("primary_error", ("bad", [None], 1, True))):
            for value in values:
                with self.subTest(key=key, value=value):
                    data = synthetic.capture_task_report()
                    data[key] = value
                    with self.assertRaises(ReportError):
                        self.load(data)

    def test_qr_attempt_wrong_types_are_controlled_rejections(self):
        for value in ("bad", 1, [None], [1], [{"decode": "bad"}],
                      [{"decode": {"status": []}}]):
            with self.subTest(value=value):
                data = synthetic.label_baseline_report()
                data["attempts"] = value
                with self.assertRaises(ReportError):
                    self.load(data)

    def test_valid_capture_nullable_error_and_optional_timings_still_load(self):
        data = synthetic.capture_task_report()
        data["primary_error"] = None
        data.pop("timings")
        report = self.load(data)
        self.assertTrue(explain_report(report).findings)

    def test_json_float_overflow_is_rejected(self):
        data = synthetic.capture_task_report()
        data["timings"]["capture_elapsed_seconds"] = "OVERFLOW_TOKEN"
        path = self.root / "overflow.json"
        path.write_text(json.dumps(data).replace('"OVERFLOW_TOKEN"', "1e309"),
                        encoding="utf-8")
        with self.assertRaises(ReportError):
            load_report(path)

    def test_qr_incomplete_truth_does_not_pass_or_offer_passed_card(self):
        for state in ("decode_error", "not_provided", "unknown"):
            with self.subTest(state=state):
                session = self.session(synthetic.label_baseline_report(
                    analysis_id="first", truth_status="provided",
                    regions=(("full_image", "decoded", "correct"),)))
                addition = self.add(session, synthetic.label_baseline_report(
                    analysis_id="second", truth_status="provided",
                    regions=(("full_image", "decoded", state),)))
                self.assertNotEqual(addition.recheck_result, RECHECK_PASSED)
                self.assertNotEqual(current_card(session).step_id, "after.added-passed")
                self.assertNotIn("复验：范围内通过", render_markdown(session))

    def test_unknown_image_identity_cannot_prove_same_image(self):
        for value in (None, "", " ", "not-a-sha256", "a" * 63):
            with self.subTest(value=value):
                session = self.session(synthetic.label_baseline_report(
                    analysis_id="before", image_sha=value,
                    regions=(("full_image", "not_decoded", "not_provided"),)))
                addition = self.add(session, synthetic.label_baseline_report(
                    analysis_id="after", image_sha=value))
                self.assertFalse(addition.comparable)
                self.assertNotEqual(addition.recheck_result, RECHECK_PASSED)

    def test_readability_recovery_without_independent_truth_still_works(self):
        session = self.session(synthetic.label_baseline_report(
            analysis_id="before", regions=(("full_image", "not_decoded", "not_provided"),)))
        addition = self.add(session, synthetic.label_baseline_report(analysis_id="after"))
        self.assertEqual(addition.recheck_result, RECHECK_PASSED)
        self.assertIn("没有独立答案", render_markdown(session))

    def test_qr_decode_error_with_truth_can_recover_with_complete_new_result(self):
        session = self.session(synthetic.label_baseline_report(
            analysis_id="before", truth_status="provided", status="completed_with_errors",
            regions=(("full_image", "decode_error", "decode_error"),)))
        addition = self.add(session, synthetic.label_baseline_report(
            analysis_id="after", truth_status="provided",
            regions=(("full_image", "decoded", "correct"),)))
        self.assertEqual(addition.recheck_result, RECHECK_PASSED)

    def test_qr_claim_of_correct_requires_byte_comparison_and_decoded_state(self):
        for change in ("comparison", "decode"):
            with self.subTest(change=change):
                session = self.session(synthetic.label_baseline_report(
                    analysis_id="before", truth_status="provided",
                    regions=(("full_image", "decoded", "correct"),)))
                data = synthetic.label_baseline_report(
                    analysis_id="after", truth_status="provided",
                    regions=(("full_image", "decoded", "correct"),))
                if change == "comparison":
                    data["decode_summaries"][0]["truth_check"]["comparison"] = "unknown"
                else:
                    data["decode_summaries"][0]["decode"]["status"] = "not_decoded"
                addition = self.add(session, data)
                self.assertNotEqual(addition.recheck_result, RECHECK_PASSED)

    def test_capture_count_warning_is_visible_and_exported(self):
        data = synthetic.capture_task_report()
        data["counts"]["samples_completed"] = 9
        session = self.session(data)
        self.assertTrue(session.primary.warnings)
        for warning in session.primary.warnings:
            self.assertIn(warning, " ".join(session.primary_explanation.findings))
            self.assertIn(warning, render_markdown(session))
        self.assertNotIn("按计划完成了 9", " ".join(session.primary_explanation.findings))

    def test_supplement_keeps_own_findings_unknowns_and_evidence(self):
        session = self.session(synthetic.capture_task_report())
        addition = self.add(session, synthetic.capture_task_report(
            run_id="other-run", status="failed", stop_reason="read_failed",
            primary_error={"stage": "read", "type": "SYNTHETIC_ReadError"}))
        text = render_markdown(session)
        for finding in addition.explanation.findings:
            self.assertIn(finding, text)
        for unknown in addition.explanation.unknowns:
            self.assertIn(unknown, text)
        self.assertIn("SYNTHETIC_ReadError", text)
        self.assertIn("补充记录 1/E01", text)
        self.assertFalse(addition.comparable)

    def test_supplement_qr_payload_and_source_path_are_still_excluded(self):
        session = self.session(synthetic.capture_task_report())
        self.add(session, synthetic.label_baseline_report())
        text = render_markdown(session)
        self.assertNotIn(synthetic.SYNTHETIC_PAYLOAD, text)
        self.assertNotIn("not-a-real-image.png", text)

    def test_scrub_windows_paths_both_separators_preserves_urls(self):
        for path in ("C:/Users/TEST/private/report.json",
                     r"C:\Users\TEST\private\report.json",
                     r"\\server\share\report.json"):
            with self.subTest(path=path):
                self.assertNotIn(path, scrub(f"见 {path} 结束"))
                self.assertIn("本机路径已省略", scrub(path))
        for text in ("https://example.test/a/b?q=1", "http://localhost:8000",
                     "decode_summaries[0].truth_check.status"):
            with self.subTest(text=text):
                self.assertEqual(scrub(text), text)

    def test_forward_slash_path_in_note_is_not_exported(self):
        session = self.session(synthetic.capture_task_report())
        session.add_note("见 C:/Users/TEST/private/report.json 结束")
        text = render_markdown(session)
        self.assertNotIn("C:/Users/TEST/private/report.json", text)
        self.assertIn("本机路径已省略", text)


if __name__ == "__main__":
    unittest.main()

