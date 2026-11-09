"""离线回答中的原报告、复验范围和待补检查。"""

import unittest

from investigator.answers import QUESTIONS, answer_session
from investigator.explain import explain_report
from investigator.session import Session
from tests import synthetic
from tests.test_boundaries import load


def investigation(*inputs):
    session = Session()
    for index, data in enumerate(inputs):
        report = load(data, f"{index}.json")
        if index == 0:
            session.load_primary(report, explain_report(report))
        else:
            session.add_addition(report, explain_report(report))
    return session


class EvidenceAnswerTests(unittest.TestCase):
    def test_roi_success_does_not_close_full_image_and_refs_match_order(self):
        box = {"x": 8, "y": 12, "width": 90, "height": 100}
        def report(roi):
            return synthetic.label_baseline_report(truth_status="provided", regions=(
                ("roi", *roi, box), ("full_image", "ambiguous", "ambiguous")))
        old = report(("not_decoded", "not_decoded"))
        new = report(("decoded", "correct"))
        answer = answer_session(investigation(old, new, new))
        self.assertIn("未解决", answer.decision)
        self.assertIn("1.json / decode_summaries[0]：ROI", answer.evidence)
        self.assertIn("1.json / decode_summaries[1]：整图", answer.evidence)
        self.assertIn("补充记录 2 重复导入", answer.evidence)
        self.assertIn("整图", answer.text(QUESTIONS[2]))
        self.assertNotIn("选区：", answer.missing)
        self.assertNotIn(synthetic.SYNTHETIC_PAYLOAD, answer.text())

    def test_supplied_answer_changes_content_without_inventing_a_repair(self):
        original = synthetic.label_baseline_report()
        later = synthetic.label_baseline_report(truth_status="provided",
                                               regions=(("full_image", "decoded", "correct"),))
        answer = answer_session(investigation(original, later))
        self.assertIn("未登记问题", answer.decision)
        self.assertEqual(answer.missing, "无。")
        self.assertIn("逐字节一致", answer.evidence)
        self.assertIn("当时未提供独立答案", answer.text(QUESTIONS[1]))
        self.assertIn("本次整图内容比对已完成，没有待补检查", answer.text(QUESTIONS[1]))

    def test_closed_read_failure_without_truth_still_needs_content_verification(self):
        primary = synthetic.label_baseline_report(regions=(("full_image", "not_decoded", "not_provided"),))
        answer = answer_session(investigation(primary, synthetic.label_baseline_report()))
        self.assertIn("范围内关闭", answer.decision)
        self.assertIn("独立答案", answer.missing)
        self.assertNotIn("没有待补检查", answer.evidence)

    def test_verified_other_image_does_not_clear_original_gap(self):
        primary = synthetic.label_baseline_report()
        other = synthetic.label_baseline_report(image_sha=synthetic.OTHER_IMAGE_SHA, truth_status="provided",
                                               regions=(("full_image", "decoded", "correct"),))
        answer = answer_session(investigation(primary, other))
        self.assertIn("不可比较", answer.evidence)
        self.assertNotIn("没有待补检查", answer.evidence)
        self.assertIn("可比复验", answer.missing)

    def test_old_correct_report_does_not_close_original_problem(self):
        old_good = synthetic.label_baseline_report(truth_status="provided",
                                                  regions=(("full_image", "decoded", "correct"),))
        newer_bad = synthetic.label_baseline_report(truth_status="provided",
                                                   regions=(("full_image", "ambiguous", "ambiguous"),))
        answer = answer_session(investigation(newer_bad, old_good))
        self.assertIn("未解决", answer.decision)
        self.assertIn("晚于原问题", answer.missing)
