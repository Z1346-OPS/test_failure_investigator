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
    def query(self, payload, region):
        with tempfile.TemporaryDirectory() as tmp:
            path = synthetic.write_report(Path(tmp) / "analysis.json", payload)
            proc = subprocess.run([sys.executable, "-B", "-X", "utf8", CLI, path, "--region", region],
                                  capture_output=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(synthetic.SYNTHETIC_PAYLOAD, proc.stdout)
        return json.loads(proc.stdout)

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
