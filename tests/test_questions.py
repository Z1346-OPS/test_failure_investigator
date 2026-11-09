"""用同一调查核对口语问法与固定问题是否选择了相同的证据。"""

import unittest

from investigator.answers import QUESTIONS, answer_question, answer_session
from tests import synthetic
from tests.test_answers import investigation
from tests.test_issue_lifecycle import missing, review


class QuestionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.capture = investigation(review((), issues=[missing(1), missing(2)]), review((1,)))

    def test_question_selects_requested_issue_in_multi_issue_session(self):
        for question, ident, intent in [
            ("请问，Ｐ０１现在可以关闭了吗？", "P01", 0),
            ("p02，还要补查什么？", "P02", 2),
            ("哪份报告支持 P01 这个判断？", "P01", 1),
        ]:
            with self.subTest(question=question):
                self.assertEqual(answer_question(self.capture, question),
                                 answer_session(self.capture, ident).text(QUESTIONS[intent]))

    def test_compound_question_preserves_requested_fields(self):
        answer = answer_session(self.capture, "P02")
        self.assertEqual(answer_question(self.capture, "P02 证据在哪、还缺什么？"),
                         answer.text(QUESTIONS[1]) + "\n" + answer.text(QUESTIONS[2]))
        self.assertEqual(answer_question(self.capture, "P02 能关吗？还缺什么检查？"), answer.text())

    def test_rejects_wrong_target_and_unrecognized_clauses(self):
        for text in ("P02 能关吗？", "P01 和 P02 能关闭吗？", "P99现在可以关闭吗？",
                     "哪里能找到依据，摄像头是坏了吗？", "关闭设备吗？", "二维码内容正确吗？", "？"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                answer_question(self.capture, text, "P01")

    def test_qr_answer_uses_existing_evidence_and_has_no_capture_issue_number(self):
        qr = investigation(synthetic.label_baseline_report())
        self.assertEqual(answer_question(qr, "二维码读出的内容正确吗？"), answer_session(qr).evidence)
        self.assertIn("独立答案", answer_question(qr, "下一步做什么？"))
        with self.assertRaises(ValueError):
            answer_question(qr, "P01 能关吗？")
