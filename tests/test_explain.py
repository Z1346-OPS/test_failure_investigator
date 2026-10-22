"""确定性解释的边界测试：不允许把未知说成结论。"""

from __future__ import annotations

import unittest

from . import synthetic  # noqa: F401

from investigator.explain import explain_report
from investigator.reports import LoadedReport


def make(payload: dict) -> LoadedReport:
    return LoadedReport(
        source_name="synthetic.json",
        source_sha256="a" * 64,
        size_bytes=len(str(payload)),
        report_type=payload["report_type"],
        schema_version=payload["schema_version"],
        data=payload,
    )


class QrExplanationTests(unittest.TestCase):
    def test_single_read_without_truth_stays_unverified(self) -> None:
        report = make(synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "not_provided"),)))
        explanation = explain_report(report)
        self.assertEqual(explanation.kind, "qr")
        # 发现里只能说“读出了一个二维码”，不能宣称内容正确
        joined = " ".join(explanation.findings)
        self.assertIn("读出了一个二维码", joined)
        self.assertNotIn("内容正确", joined)
        # 未知里必须保留“未验证”
        self.assertTrue(any("未验证" in item for item in explanation.unknowns))
        self.assertTrue(any("独立答案" in item for item in explanation.unknowns))
        self.assertTrue(explanation.next_steps)

    def test_truth_correct_is_scoped_not_overclaimed(self) -> None:
        report = make(synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "correct"),),
            truth_status="provided", truth_source="合成答案来源"))
        explanation = explain_report(report)
        joined = " ".join(explanation.findings)
        self.assertIn("逐字节比对一致", joined)
        # 不能扩展成整机/跨场景结论
        self.assertTrue(any("不能扩展" in item for item in explanation.unknowns))

    def test_full_image_ok_but_roi_error_is_surfaced(self) -> None:
        report = make(synthetic.label_baseline_report(
            regions=(
                ("full_image", "decoded", "not_provided"),
                ("roi", "decode_error", "decode_error", {"x": 10, "y": 10, "width": 100, "height": 100}),
            ),
            status="completed_with_errors"))
        explanation = explain_report(report)
        joined = " ".join(explanation.findings)
        # 两个区域都要出现，不能只报较好的那个
        self.assertIn("整图", joined)
        self.assertIn("ROI", joined)
        self.assertIn("解码报告错误", joined)
        # 有执行错误时整体状态要说明
        self.assertTrue(any("包含错误" in item for item in explanation.unknowns))

    def test_ambiguous_is_reported_as_ambiguity(self) -> None:
        report = make(synthetic.label_baseline_report(
            regions=(("full_image", "ambiguous", "ambiguous"),)))
        explanation = explain_report(report)
        joined = " ".join(explanation.findings)
        self.assertIn("歧义", joined)
        self.assertNotIn("内容正确", joined)

    def test_conflict_is_reported(self) -> None:
        report = make(synthetic.label_baseline_report(
            regions=(("full_image", "conflict", "conflict"),)))
        explanation = explain_report(report)
        self.assertIn("冲突", " ".join(explanation.findings))

    def test_evidence_ids_are_generated_and_located(self) -> None:
        report = make(synthetic.label_baseline_report())
        explanation = explain_report(report)
        self.assertTrue(explanation.evidence)
        identifiers = [item[0] for item in explanation.evidence]
        self.assertEqual(identifiers[0], "E01")
        self.assertEqual(len(set(identifiers)), len(identifiers))
        self.assertTrue(any("decode_summaries" in item[1] for item in explanation.evidence))


class ReviewExplanationTests(unittest.TestCase):
    def test_consistent_does_not_claim_camera_is_good(self) -> None:
        report = make(synthetic.capture_review_report())
        explanation = explain_report(report)
        self.assertEqual(explanation.kind, "capture_review")
        self.assertTrue(any("一致" in item for item in explanation.findings))
        self.assertTrue(any("不能说明相机合格" in item for item in explanation.unknowns))

    def test_frame_unverifiable_is_not_disk_failure(self) -> None:
        report = make(synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "缺少留证图片"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}]))
        explanation = explain_report(report)
        joined = " ".join(explanation.findings)
        self.assertIn("无法核实", joined)
        self.assertNotIn("磁盘", joined)
        self.assertTrue(any("不能证明磁盘写入失败" in item for item in explanation.unknowns))

    def test_metric_mismatch_is_not_hardware_damage(self) -> None:
        report = make(synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "metric_mismatch", "frame_count": 1, "detail": "亮度不同"}],
            counts={"reported_samples": 1, "csv_pairs": 1, "verified_frames": 0},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics(different=True)}]))
        explanation = explain_report(report)
        joined = " ".join(explanation.findings)
        self.assertIn("不同", joined)
        self.assertNotIn("硬件", joined)
        self.assertTrue(any("不能据此认定相机损坏" in item for item in explanation.unknowns))

    def test_not_reviewed_with_null_counts_is_not_zero(self) -> None:
        report = make(synthetic.capture_review_report(
            verification_status="not_reviewed", task_status="failed",
            counts=None, frames=[]))
        explanation = explain_report(report)
        joined = " ".join(explanation.findings + explanation.unknowns)
        self.assertIn("没有完成有效复核", joined)
        self.assertIn("不能当作 0", joined)

    def test_unknown_issue_code_is_preserved(self) -> None:
        report = make(synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "brand_new_code", "frame_count": None, "detail": "x"}],
            counts={"reported_samples": 1, "csv_pairs": 1, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}]))
        explanation = explain_report(report)
        joined = " ".join(explanation.findings)
        self.assertIn("brand_new_code", joined)
        self.assertIn("原样保留", joined)


class CaptureTaskExplanationTests(unittest.TestCase):
    def test_open_failed_keeps_cause_unknown(self) -> None:
        report = make(synthetic.capture_task_report(
            status="failed", stop_reason="open_failed", samples=0, camera_index=9999,
            actual_backend=None,
            primary_error={"stage": "open", "type": "CaptureTaskError", "message": "无法打开摄像头"}))
        explanation = explain_report(report)
        self.assertEqual(explanation.kind, "capture_task")
        joined = " ".join(explanation.findings)
        self.assertIn("没有成功打开", joined)
        self.assertIn("9999", joined)
        self.assertTrue(any("还不能确定" in item for item in explanation.unknowns))
        self.assertTrue(any("编号" in step.title for step in explanation.next_steps))

    def test_completed_does_not_claim_quality(self) -> None:
        report = make(synthetic.capture_task_report())
        explanation = explain_report(report)
        joined = " ".join(explanation.findings)
        self.assertIn("按计划完成", joined)
        self.assertTrue(any("不能说明画面质量" in item for item in explanation.unknowns))

    def test_execution_error_is_not_hardware(self) -> None:
        report = make(synthetic.capture_task_report(
            status="failed", stop_reason="read_failed", samples=0,
            primary_error={"stage": "read", "type": "CaptureTaskError", "message": "读取画面失败"}))
        explanation = explain_report(report)
        joined = " ".join(explanation.findings)
        self.assertIn("读取画面失败", joined)
        self.assertNotIn("硬件", joined)


class NoGuessingTests(unittest.TestCase):
    """解释不得生成根因猜测列表。"""

    FORBIDDEN = ("根因是", "原因就是", "确定是驱动", "一定是硬件", "置信度")

    def test_no_root_cause_guesses(self) -> None:
        payloads = [
            synthetic.label_baseline_report(),
            synthetic.capture_review_report(
                verification_status="inconsistent",
                issues=[{"code": "frame_unverifiable", "frame_count": 1, "detail": "x"}],
                counts={"reported_samples": 1, "csv_pairs": 1, "verified_frames": 0},
                frames=[]),
            synthetic.capture_task_report(status="failed", stop_reason="open_failed", samples=0),
        ]
        for payload in payloads:
            with self.subTest(kind=payload["report_type"]):
                explanation = explain_report(make(payload))
                text = " ".join(explanation.findings + explanation.unknowns)
                for phrase in self.FORBIDDEN:
                    self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
