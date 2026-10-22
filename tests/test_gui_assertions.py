"""GUI 文案断言辅助的正反例测试。"""

from __future__ import annotations

import unittest

from .gui_assertions import unnegated_claims

PHRASES = ("内容正确。", "内容是正确的", "二维码正常", "内容已验证", "确认为正确")


class UnnegatedClaimsTests(unittest.TestCase):
    def test_negated_claim_is_not_reported(self) -> None:
        self.assertEqual(unnegated_claims("不能证明内容正确。", PHRASES), [])

    def test_plain_claim_is_reported(self) -> None:
        self.assertTrue(unnegated_claims("内容正确。", PHRASES))

    def test_second_sentence_is_not_exempted_by_first(self) -> None:
        hits = unnegated_claims("不代表相机合格。内容正确。", PHRASES)
        self.assertTrue(hits)
        self.assertTrue(any("内容正确" in hit for hit in hits))

    def test_widget_boundary_is_respected(self) -> None:
        texts = ["不能证明内容正确。", "内容正确。"]
        hits = unnegated_claims(texts, PHRASES)
        self.assertTrue(hits)
        self.assertTrue(any("内容正确" in hit for hit in hits))

    def test_mixed_paragraph_is_not_exempted(self) -> None:
        text = "这里只是范围内一致，不能证明内容正确。内容正确。在新批次成立。"
        hits = unnegated_claims(text, PHRASES)
        self.assertTrue(hits)

    def test_negation_in_previous_clause_does_not_exempt(self) -> None:
        hits = unnegated_claims("不是相机问题，内容正确。", PHRASES)
        self.assertTrue(hits)

    def test_real_ui_restriction_is_not_reported(self) -> None:
        texts = [
            "读出本身不代表内容正确，需要独立答案才能判断。",
            "没有独立答案，尚未验证内容是否正确。",
        ]
        self.assertEqual(unnegated_claims(texts, PHRASES), [])

    def test_other_sentences_do_not_exempt_claim(self) -> None:
        # 同一控件里，正确的限制说明之后出现错误结论
        hits = unnegated_claims(
            "不能说明相机合格，也不代表相机正常。\n内容已验证。", PHRASES)
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()
