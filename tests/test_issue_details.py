"""问题详情与现有问题历史、交接导出使用同一批报告。"""
import json
import tempfile
import unittest
from pathlib import Path

from investigator.issue_card import format_issue_card
from investigator.explain import explain_report
from investigator.export import render_markdown, short_conclusion
from investigator.reports import load_report
from investigator.session import Session
from tests import synthetic
from tests.test_issue_lifecycle import missing, review


class IssueDetailsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.file = Path(tmp.name) / "report.json"
        self.session = Session()

    def ingest(self, payload):
        report = load_report(synthetic.write_report(self.file, payload))
        if self.session.primary is None:
            self.session.load_primary(report, explain_report(report))
        else:
            self.session.add_addition(report, explain_report(report))
        return report

    def details(self):
        return self.session.get_issue_details(self.session.investigation_id, "P01")

    def test_partial_repeat_target_only_and_reopening(self):
        self.ingest(review((1,), issues=[missing(2)]))
        partial = review((1,))
        self.ingest(partial)
        before = self.details()
        self.assertEqual(before["status"], "open")
        self.assertNotIn("关闭该问题没有待补检查", short_conclusion(self.session))
        self.assertEqual(before["origin"]["locator"], "issues[0]")
        scope = before["evidence"]["补充记录 1"]
        self.assertEqual(scope["verified_frame_counts"], [1])
        self.assertEqual(scope["verified_frames"][0]["locator"], "frames[0]")
        self.assertEqual(scope["scope_locator"], "frames")
        self.assertIn("帧 2", before["missing_evidence"][0])
        self.assertIn("帧 2", before["next_step"])
        self.assertIn("| 已核实的帧号 | verified_frame_counts=[1] |", render_markdown(self.session))
        self.ingest(partial)
        replay = self.details()
        self.assertTrue(replay["latest_primary_comparison"]["is_repeat"])
        self.assertEqual(replay["last_issue_assessment"], before["last_issue_assessment"])
        self.assertEqual(replay["history"], before["history"])

        fixed = self.ingest(review((2,)))
        closed = self.details()
        self.assertEqual(closed["status"], "closed_in_scope")
        self.assertEqual(closed["missing_evidence"], [])
        self.assertEqual(closed["resolved_by"], "补充记录 3")
        self.assertEqual(closed["history"][:len(before["history"])], before["history"])
        self.assertEqual(closed["latest_primary_comparison"]["result"], "范围内通过")
        summary = short_conclusion(self.session)
        self.assertIn("P01 可在本次帧 2 范围内关闭。关闭该问题没有待补检查。", summary)
        self.assertIn("补充记录 3 核实了帧 2", summary)
        self.assertIn("首次无法核实的原因仍未知", summary)
        evidence = closed["evidence"][closed["resolved_by"]]
        self.assertEqual(evidence["verified_frame_counts"], [2])
        self.assertEqual(evidence["review_id"], fixed.data["review_id"])
        self.assertEqual(evidence["reviewed_at_utc"], fixed.data["reviewed_at_utc"])
        text = render_markdown(self.session)
        for value in ("reviewed_at_utc", evidence["review_id"], evidence["reviewed_at_utc"],
                      evidence["source_sha256"], "verified_frame_counts=[2]", "frames[0] → 帧 2"):
            self.assertIn(value, text)
        evidence["verified_frames"][0]["metrics"]["brightness"].clear()
        self.assertEqual(len(fixed.data["frames"][0]["metrics"]["brightness"]), 2)
        self.ingest(review((1,), issues=[missing(2)]))
        reopened = self.details()
        self.assertEqual(reopened["status"], "open")
        self.assertNotIn("关闭该问题没有待补检查", short_conclusion(self.session))
        self.assertEqual(reopened["history"][-1]["event"], "重新出现")
        self.assertIsNone(reopened["last_issue_assessment"])
        self.assertEqual(before["status"], "open")
        json.dumps(reopened, ensure_ascii=False, allow_nan=False)

    def test_card_reopened_repeat_and_reclosed(self):
        self.ingest(review((1,), issues=[missing(2)]))
        first = review((2,))
        self.ingest(first)
        card = format_issue_card(self.details())
        self.assertIn("frames[0] → 帧 2", card.location)
        self.assertIn(card.summary, render_markdown(self.session))
        self.assertIn("没有待补检查", card.missing)
        self.ingest(review((1,), issues=[missing(2)]))
        reopened = format_issue_card(self.details())
        self.assertIn("重新出现", reopened.decision)
        self.assertIn("核实帧 2", reopened.missing)
        self.ingest(first)
        repeat = format_issue_card(self.details())
        self.assertEqual(repeat.history, reopened.history)
        self.assertEqual(repeat.decision, reopened.decision)
        self.assertIn("补充记录 1 已用这份报告", repeat.repeat_notice)
        self.ingest(review((2,)))
        final = format_issue_card(self.details())
        self.assertIn("再次关闭", final.decision)
        self.assertIn("补充记录 4", final.location)
        self.assertEqual(len(final.history), 4)
        self.assertEqual(final.repeat_notice, "")

    def test_changed_batch_and_legacy_identity(self):
        self.ingest(review((1,), issues=[missing(2)]))
        other = review((2,))
        other["run_id"] = "a" * 32
        self.ingest(other)
        detail = self.details()
        self.assertFalse(detail["last_issue_assessment"]["same_subject"])
        self.assertEqual(detail["latest_primary_comparison"]["result"], "不可比较")
        self.assertEqual(detail["status"], "open")
        legacy = review((2,))
        del legacy["review_id"]
        self.ingest(legacy)
        detail = self.details()
        self.assertEqual(detail["status"], "open")
        self.assertIsNone(detail["evidence"]["补充记录 2"]["review_id"])
        self.assertIn("复核编号", detail["missing_evidence"][0])

    def test_verified_set_comes_from_rows_and_conflicts_stay_visible(self):
        self.ingest(review((1,), issues=[missing(2)]))
        contradictory = review((1, 2))
        contradictory["frames"][1]["image_sha256_match"] = False
        self.ingest(contradictory)
        detail = self.details()
        scope = detail["evidence"]["补充记录 1"]
        self.assertEqual(scope["verified_frame_counts"], [1])
        self.assertTrue(scope["warnings"])
        self.assertEqual(detail["status"], "open")

    def test_same_time_is_insufficient_even_with_matching_target(self):
        first = self.ingest(review((1,), issues=[missing(2)]))
        same_time = review((2,))
        same_time["reviewed_at_utc"] = first.get("reviewed_at_utc")
        self.ingest(same_time)
        detail = self.details()
        self.assertEqual(detail["status"], "open")
        self.assertIn("晚于", detail["missing_evidence"][0])
        self.assertEqual(detail["evidence"]["补充记录 1"]["verified_frame_counts"], [2])

    def test_issue_found_in_addition_and_primary_comparison_are_distinct(self):
        self.ingest(review((1,)))
        self.ingest(review((1,), issues=[missing(2)]))
        self.ingest(review((1,)))
        detail = self.details()
        self.assertEqual(detail["origin"]["context"], "补充记录 1")
        self.assertEqual(detail["latest_primary_comparison"]["result"], "范围内通过")
        self.assertEqual(detail["last_issue_assessment"]["event"], "未解决")
        self.assertEqual(detail["status"], "open")

    def test_missing_or_foreign_ids_and_new_investigation(self):
        report = self.ingest(review((1,), issues=[missing(2)]))
        ident = self.session.investigation_id
        for first, second in ((None, "P01"), (ident, " "), (ident, None)):
            with self.subTest(first=first, second=second), self.assertRaises(ValueError):
                self.session.get_issue_details(first, second)
        for first, second in ((ident, "P99"), ("unknown", "P01")):
            with self.assertRaises(KeyError):
                self.session.get_issue_details(first, second)
        self.session.load_primary(report, explain_report(report))
        with self.assertRaises(KeyError):
            self.session.get_issue_details(ident, "P01")
