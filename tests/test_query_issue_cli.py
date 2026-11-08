"""通过命令行核对列表与单项查询共用的编号和状态。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import synthetic
from tests.test_issue_lifecycle import missing, review


CLI = Path(__file__).resolve().parents[1] / "src" / "query_issue.py"


class QueryIssueCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def query(self, *args):
        return subprocess.run([sys.executable, "-B", "-X", "utf8", CLI, *args],
                              capture_output=True, encoding="utf-8")

    def result(self, *args):
        proc = self.query(*args)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_list_then_lookup_each_id(self):
        first = synthetic.write_report(self.root / "first.json", review((), issues=[missing(1), missing(2)]))
        later = synthetic.write_report(self.root / "later.json", review((1,)))
        issues = self.result("--list", first, later)["issues"]
        self.assertEqual([(i["issue_id"], i["status"]) for i in issues],
                         [("P02", "open"), ("P01", "closed_in_scope")])
        for item in issues:
            detail = self.result(item["issue_id"], first, later)
            self.assertEqual(item, {key: detail[key] for key in item})

    def test_empty_list_and_bad_followup(self):
        first = synthetic.write_report(self.root / "qr.json", synthetic.label_baseline_report())
        result = self.result("--list", first)
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["primary_report_type"], "label_baseline")
        clean = synthetic.write_report(self.root / "clean.json", review())
        self.assertEqual(self.result("--list", clean)["issues"], [])
        proc = self.query("--list", clean, self.root / "missing.json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
