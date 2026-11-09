"""QR 区域查询的范围、证据和不完整报告。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import synthetic


CLI = Path(__file__).resolve().parents[1] / "src" / "query_qr.py"


class QueryQrTests(unittest.TestCase):
    def query(self, payload, region, *, primary=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = synthetic.write_report(Path(tmp) / "analysis.json", payload)
            args = [sys.executable, "-B", "-X", "utf8", CLI, path, "--region", region]
            if primary is not None:
                primary_path = Path(tmp) / "original.json"
                primary_path.write_text(json.dumps(primary, ensure_ascii=False), encoding="utf-8")
                args.extend(["--primary", primary_path])
            proc = subprocess.run(args,
                                  capture_output=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(synthetic.SYNTHETIC_PAYLOAD, proc.stdout)
        return json.loads(proc.stdout)

    def test_compare_keeps_region_success_separate_from_report_result(self):
        box = {"x": 8, "y": 12, "width": 90, "height": 100}
        old = synthetic.label_baseline_report(
            truth_status="provided", regions=(("full_image", "ambiguous", "ambiguous"),
                                               ("roi", "not_decoded", "not_decoded", box)))
        mixed = synthetic.label_baseline_report(
            truth_status="provided", regions=(("full_image", "ambiguous", "ambiguous"),
                                               ("roi", "decoded", "correct", box)))
        result = self.query(mixed, "roi", primary=old)
        self.assertEqual(result["followup_region"]["status"], "correct")
        comparison = result["report_comparison"]
        self.assertEqual(comparison["original_issue_status"], "unresolved")
        self.assertEqual(comparison["recheck_result"], "未通过")
        self.assertIn("decode_summaries[0].decode.status", comparison["followup_evidence_paths"])

    def test_close_only_with_a_new_valid_comparable_followup(self):
        old = synthetic.label_baseline_report(truth_status="provided",
                                              regions=(("full_image", "ambiguous", "ambiguous"),))
        new = synthetic.label_baseline_report(truth_status="provided",
                                              regions=(("full_image", "decoded", "correct"),))
        self.assertEqual(self.query(new, "full_image", primary=old)["report_comparison"]
                         ["original_issue_status"], "closed_in_scope")
        repeated = self.query(old, "full_image", primary=old)["report_comparison"]
        self.assertTrue(repeated["is_repeat"])
        self.assertEqual(repeated["original_issue_status"], "unresolved")
        new["decode_summaries"][0]["decode"]["symbols"] = []
        bad = self.query(new, "full_image", primary=old)
        self.assertEqual(bad["report_comparison"]["recheck_result"], "证据不足")
        self.assertEqual(bad["followup_region"]["status"], "unverified")

    def test_correct_roi_and_ambiguous_full_image(self):
        report = synthetic.label_baseline_report(
            truth_status="provided", regions=(("roi", "decoded", "correct",
                {"x": 8, "y": 12, "width": 90, "height": 100}),
                ("full_image", "ambiguous", "ambiguous")))
        roi = self.query(report, "roi")
        self.assertEqual((roi["status"], roi["missing_evidence"]), ("correct", []))
        self.assertIn("decode_summaries[0].truth_check.status", roi["evidence_paths"])
        full = self.query(report, "full_image")
        self.assertEqual(full["status"], "unverified")
        self.assertTrue(any("单一有效读码" in gap for gap in full["missing_evidence"]))
        self.assertIn("decode_summaries[1].decode.status", full["evidence_paths"])

    def test_older_or_same_execution_cannot_close_an_original_qr_problem(self):
        original = synthetic.label_baseline_report(truth_status="provided",
                                                 regions=(("full_image", "ambiguous", "ambiguous"),))
        for override in ({"analysis_id": original["analysis_id"]}, {"analyzed_at": original["analyzed_at"]},
                         {"analyzed_at": "2020-01-01T00:00:00Z"}, {"analyzed_at": None}):
            with self.subTest(override=override):
                newer = synthetic.label_baseline_report(truth_status="provided",
                                                       regions=(("full_image", "decoded", "correct"),))
                newer.update(override)
                result = self.query(newer, "full_image", primary=original)
                self.assertEqual(result["followup_region"]["status"], "correct")
                self.assertEqual(result["report_comparison"]["original_issue_status"], "unresolved")
                self.assertEqual(result["report_comparison"]["recheck_result"], "证据不足")

    def test_absent_answer_roi_and_mismatch(self):
        report = synthetic.label_baseline_report()
        self.assertEqual(self.query(report, "roi")["status"], "not_checked")
        no_truth = self.query(report, "full_image")
        self.assertEqual(no_truth["status"], "unverified")
        self.assertTrue(any("独立答案" in gap for gap in no_truth["missing_evidence"]))
        wrong = synthetic.label_baseline_report(truth_status="provided",
                                               regions=(("full_image", "decoded", "incorrect"),))
        self.assertEqual(self.query(wrong, "full_image")["status"], "incorrect")

    def test_conflicting_or_non_unique_evidence_does_not_verify(self):
        report = synthetic.label_baseline_report(truth_status="provided",
                                               regions=(("full_image", "decoded", "correct"),))
        row = report["decode_summaries"][0]
        row["decode"]["symbols"] = []
        self.assertEqual(self.query(report, "full_image")["status"], "unverified")
        report["decode_summaries"].append(row.copy())
        self.assertEqual(len(self.query(report, "full_image")["evidence_paths"]), 2)
