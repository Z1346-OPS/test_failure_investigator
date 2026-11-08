"""Cross-report closure rules for capture reviews and QR answer identity."""
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from investigator.explain import explain_report
from investigator.reports import load_report
from investigator.session import RECHECK_PASSED, Session
from tests import synthetic
from tests.test_issue_lifecycle import missing, review


def execution(sequence, numbers=(1, 2), *, issues=()):
    data = review(numbers, issues=issues)
    data["review_id"] = UUID(int=sequence).hex
    data["reviewed_at_utc"] = datetime(2026, 11, 1, 0, 0, sequence, tzinfo=UTC).isoformat()
    return data


class ReviewContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.file = Path(tmp.name) / "report.json"
        self.session = Session()

    def ingest(self, payload, *, indent=None):
        self.file.write_text(json.dumps(payload, indent=indent), encoding="utf-8")
        report = load_report(self.file)
        explanation = explain_report(report)
        if self.session.primary is None:
            self.session.load_primary(report, explanation)
        else:
            return self.session.add_addition(report, explanation)

    def test_reformatted_old_run_and_out_of_order_execution_cannot_close_issue(self):
        first = execution(1)
        self.ingest(first)
        self.ingest(execution(3, (1,), issues=[missing(2)]))
        self.assertTrue(self.ingest(first, indent=2).is_repeat)
        self.ingest(execution(2))
        self.assertEqual([p.frame for p in self.session.unresolved_review_problems()], [2])
        self.ingest(execution(4))
        self.assertFalse(self.session.unresolved_review_problems())

    def test_legacy_or_equal_time_cannot_prove_recovery(self):
        for side, omit in ((0, "review_id"), (1, "review_id"),
                           (0, "reviewed_at_utc"), (1, "reviewed_at_utc"), (1, None)):
            with self.subTest(side=side, omit=omit):
                self.session = Session()
                pair = [execution(2, (1,), issues=[missing(2)]), execution(3)]
                if omit:
                    del pair[side][omit]
                else:
                    pair[1]["reviewed_at_utc"] = pair[0]["reviewed_at_utc"]
                self.ingest(pair[0])
                self.assertNotEqual(self.ingest(pair[1]).recheck_result, RECHECK_PASSED)
                self.assertTrue(self.session.unresolved_review_problems())

    def test_global_csv_issue_needs_declared_frames_even_if_review_aborted(self):
        for scope in ([1, 2], [1], None):
            with self.subTest(scope=scope):
                self.session = Session()
                origin = execution(1, issues=[{"code": "csv_keys_mismatch", "frame_count": None}])
                origin["frames"] = []
                origin["counts"].update(csv_pairs=1, verified_frames=0)
                if scope is not None:
                    origin["declared_frame_counts"] = scope
                else:
                    origin.pop("declared_frame_counts", None)
                self.ingest(origin)
                result = self.ingest(execution(2, (3, 4)))
                self.assertNotEqual(result.recheck_result, RECHECK_PASSED)
                self.assertTrue(self.session.unresolved_review_problems())
                self.ingest(execution(3))
                self.assertEqual(bool(self.session.unresolved_review_problems()), scope != [1, 2])

    def test_missing_or_invalid_answer_digest_on_either_side_blocks_recovery(self):
        for side in (0, 1):
            for value in (None, "invalid"):
                with self.subTest(side=side, value=value):
                    self.session = Session()
                    pair = [synthetic.label_baseline_report(
                        regions=(("full_image", "decoded", truth),), truth_status="provided")
                        for truth in ("incorrect", "correct")]
                    if value is None:
                        del pair[side]["known_truth"]["sha256"]
                    else:
                        pair[side]["known_truth"]["sha256"] = value
                    self.ingest(pair[0])
                    result = self.ingest(pair[1])
                    self.assertNotEqual(result.recheck_result, RECHECK_PASSED)
                    offending = self.session.primary if side == 0 else result.report
                    self.assertTrue(any("sha256" in w for w in offending.warnings))
