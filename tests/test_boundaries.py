"""集中边界测试：输入上限、复验口径、覆盖范围、重复导入与连续保存。

只锁定现有契约（AGENTS.md、docs/workflow-design.md 第 4/7 节、
docs/next-iteration-plan-2026-10-19.md）明确要求的行为：

  * QR 单一读出/整图读出不能掩盖真值不一致或 ROI 范围变化。
  * 未复核、未知计数、未覆盖原问题帧、比较口径缺失不能变成通过。
  * 重复导入较早材料不能掩盖此前登记的未通过。
  * 文件大小/数组长度/结构深度的 N−1、N、N＋1 边界。
  * 连续保存不覆盖已有文件；写入失败后换新目标仍可保存。
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import synthetic  # noqa: F401

from investigator.explain import explain_report
from investigator.export import (
    ExportError,
    render_markdown,
    save_markdown,
    short_conclusion,
)
from investigator.guides import current_card
from investigator.reports import (
    MAX_ARRAY_ELEMENTS,
    MAX_DEPTH,
    MAX_FILE_BYTES,
    ReportError,
    load_report,
)
from investigator.session import (
    RECHECK_FAILED,
    RECHECK_INCOMPARABLE,
    RECHECK_INSUFFICIENT,
    RECHECK_PASSED,
    Session,
)


def load(payload: dict, name: str) -> "LoadedReport":  # noqa: F821 - 避免额外导入
    from investigator.reports import LoadedReport

    return LoadedReport(
        source_name=name,
        source_sha256=hashlib.sha256(name.encode("utf-8")).hexdigest(),
        size_bytes=1,
        report_type=payload["report_type"],
        schema_version=payload["schema_version"],
        data=payload,
    )


def start(session: Session, payload: dict, name: str):
    report = load(payload, name)
    session.load_primary(report, explain_report(report))
    return report


def add(session: Session, payload: dict, name: str):
    report = load(payload, name)
    return session.add_addition(report, explain_report(report))


MISSING_IMAGE = dict(
    verification_status="inconsistent",
    issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "缺少留证图片"}],
    counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
    frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
)

CONSISTENT_ALL_FRAMES = dict(
    verification_status="consistent",
    counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 2},
    frames=[
        {"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()},
        {"frame_count": 2, "image_sha256_match": True, "metrics": synthetic.review_metrics()},
    ],
)

CONSISTENT_FRAME_1_ONLY = dict(
    verification_status="consistent",
    counts={"reported_samples": 1, "csv_pairs": 1, "verified_frames": 1},
    frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}],
)

QR_WITH_ROI_ERROR = dict(
    regions=(
        ("full_image", "decoded", "not_provided"),
        ("roi", "decode_error", "decode_error", {"x": 10, "y": 10, "width": 100, "height": 100}),
    ),
    status="completed_with_errors",
)


class QrTruthBoundaryTests(unittest.TestCase):
    """QR 内容正确性：真值不一致、真值来源变化都不能被“通过”掩盖。"""

    def test_later_incorrect_truth_is_a_new_problem(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "correct"),),
            truth_status="provided"), "primary.json")
        addition = add(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "incorrect"),),
            truth_status="provided"), "later.json")
        self.assertEqual(addition.recheck_result, RECHECK_FAILED)
        self.assertIn("不一致", addition.recheck_reason)
        self.assertTrue(addition.new_problem_keys)
        text = render_markdown(session)
        self.assertIn("与独立答案比对", text)
        self.assertIn("不一致", text)
        self.assertNotIn("在可比较范围内", text)

    def test_same_truth_allows_scoped_recovery(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "incorrect"),),
            truth_status="provided"), "primary.json")
        addition = add(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "correct"),),
            truth_status="provided"), "later.json")
        self.assertTrue(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_PASSED)

    def test_later_without_independent_answer_cannot_close_mismatch(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "incorrect"),),
            truth_status="provided"), "primary.json")
        addition = add(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "not_provided"),),
            truth_status="not_provided"), "later.json")
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)
        self.assertNotEqual(addition.recheck_result, RECHECK_PASSED)

    def test_different_independent_answer_is_incomparable(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "incorrect"),),
            truth_status="provided"), "primary.json")
        payload = synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "correct"),),
            truth_status="provided")
        payload["known_truth"]["sha256"] = "9" * 64
        addition = add(session, payload, "other-answer.json")
        self.assertFalse(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)
        self.assertIn("答案", addition.comparison_reason)

    def test_truth_problem_without_new_comparison_is_insufficient(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "incorrect"),),
            truth_status="provided"), "primary.json")
        payload = synthetic.label_baseline_report(
            regions=(("full_image", "decoded", "not_provided"),),
            truth_status="provided")
        addition = add(session, payload, "uncompared.json")
        self.assertEqual(addition.recheck_result, RECHECK_INSUFFICIENT)
        self.assertIn("比对", addition.recheck_reason)

    def test_empty_region_summary_is_not_a_baseline(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(regions=()), "empty.json")
        addition = add(session, synthetic.label_baseline_report(), "later.json")
        self.assertEqual(addition.recheck_result, RECHECK_INSUFFICIENT)


class QrRegionScopeTests(unittest.TestCase):
    """区域范围是对象身份的一部分；不能按索引把不同 ROI 当成同一区域。"""

    def test_different_roi_geometry_is_incomparable(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(**QR_WITH_ROI_ERROR), "primary.json")
        moved = synthetic.label_baseline_report(regions=(
            ("full_image", "decoded", "not_provided"),
            ("roi", "decoded", "not_provided", {"x": 300, "y": 300, "width": 50, "height": 50}),
        ))
        addition = add(session, moved, "moved.json")
        self.assertFalse(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)
        self.assertIn("区域", addition.comparison_reason)

    def test_disappearing_roi_region_does_not_pass(self) -> None:
        session = Session()
        start(session, synthetic.label_baseline_report(**QR_WITH_ROI_ERROR), "primary.json")
        fewer = synthetic.label_baseline_report(regions=(
            ("full_image", "decoded", "not_provided"),
        ))
        addition = add(session, fewer, "fewer.json")
        self.assertFalse(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)


class ReviewCoverageTests(unittest.TestCase):
    """复核的“一致”只覆盖它实际核实的帧；未覆盖原问题帧不能通过。"""

    def test_zero_verified_frames_is_insufficient(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "primary.json")
        empty = dict(verification_status="consistent",
                     counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 0},
                     frames=[])
        addition = add(session, synthetic.capture_review_report(**empty), "zero.json")
        self.assertEqual(addition.recheck_result, RECHECK_INSUFFICIENT)
        self.assertIn("帧", addition.recheck_reason)

    def test_original_problem_frame_not_covered_is_insufficient(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "primary.json")
        addition = add(session, synthetic.capture_review_report(**CONSISTENT_FRAME_1_ONLY),
                       "frame-1-only.json")
        self.assertEqual(addition.recheck_result, RECHECK_INSUFFICIENT)
        self.assertIn("2", addition.recheck_reason)

    def test_original_problem_frame_covered_passes_in_scope(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "primary.json")
        addition = add(session, synthetic.capture_review_report(**CONSISTENT_ALL_FRAMES),
                       "all-frames.json")
        self.assertEqual(addition.recheck_result, RECHECK_PASSED)
        self.assertIn("范围内", addition.recheck_reason)

    def test_consistent_with_null_counts_is_insufficient(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "primary.json")
        payload = synthetic.capture_review_report(verification_status="consistent")
        payload["counts"] = None
        addition = add(session, payload, "no-counts.json")
        self.assertEqual(addition.recheck_result, RECHECK_INSUFFICIENT)
        self.assertIn("counts", addition.recheck_reason)

    def test_missing_comparison_basis_is_incomparable(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(), "primary.json")
        payload = synthetic.capture_review_report()
        del payload["comparison_basis"]
        addition = add(session, payload, "no-basis.json")
        self.assertFalse(addition.comparable)
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)
        self.assertIn("comparison_basis", addition.comparison_reason)

    def test_both_missing_comparison_basis_is_incomparable(self) -> None:
        session = Session()
        primary = synthetic.capture_review_report()
        del primary["comparison_basis"]
        start(session, primary, "primary.json")
        later = synthetic.capture_review_report()
        del later["comparison_basis"]
        addition = add(session, later, "no-basis.json")
        self.assertEqual(addition.recheck_result, RECHECK_INCOMPARABLE)


class ContradictoryRecordTests(unittest.TestCase):
    def test_unknown_verification_status_is_not_called_problem_found(self) -> None:
        payload = synthetic.capture_review_report(verification_status="future_status")
        explanation = explain_report(load(payload, "future.json"))
        joined = " ".join(explanation.findings)
        self.assertNotIn("本次复核发现了问题", joined)
        self.assertTrue(any("future_status" in item for item in explanation.findings))
        self.assertTrue(any("未预期" in item or "不能判断" in item
                            for item in explanation.unknowns))

        session = Session()
        start(session, payload, "future.json")
        self.assertEqual(current_card(session).step_id, "handoff.save")

    def test_consistent_with_issues_is_surfaced_not_hidden(self) -> None:
        payload = synthetic.capture_review_report(
            verification_status="consistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "x"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}])
        explanation = explain_report(load(payload, "contradict.json"))
        joined = " ".join(explanation.findings)
        self.assertIn("无法核实", joined)
        self.assertTrue(any("矛盾" in item or "冲突" in item
                            for item in explanation.unknowns))

        session = Session()
        start(session, payload, "contradict.json")
        # 不能按“一致”给出下一步；未知/冲突交给技术人员。
        self.assertEqual(current_card(session).step_id, "handoff.save")


class RepeatConclusionTests(unittest.TestCase):
    def test_repeat_import_does_not_hide_earlier_failure(self) -> None:
        session = Session()
        start(session, synthetic.capture_review_report(), "primary.json")
        add(session, synthetic.capture_review_report(**MISSING_IMAGE), "broken.json")
        add(session, synthetic.capture_review_report(), "primary.json")   # 重复导入

        conclusion = short_conclusion(session)
        self.assertIn(RECHECK_FAILED, conclusion)
        self.assertIn("重复", conclusion)
        self.assertNotIn("范围内通过", conclusion)
        text = render_markdown(session)
        self.assertIn(RECHECK_FAILED, text)
        self.assertEqual(session.additions[1].is_repeat, True)


class InputLimitTests(unittest.TestCase):
    """按代码常量验证 N−1 / N / N＋1，构造材料其余结构保持有效。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _load_payload(self, name: str, payload) -> str:
        path = self.tmp / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return load_report(path).report_type

    def test_file_size_boundaries(self) -> None:
        for size in (MAX_FILE_BYTES - 1, MAX_FILE_BYTES):
            with self.subTest(size=size):
                payload = synthetic.capture_task_report()
                payload["padding"] = ""
                base = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                payload["padding"] = "x" * (size - len(base.encode("utf-8")))
                raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                self.assertEqual(len(raw.encode("utf-8")), size)
                path = self.tmp / f"size-{size}.json"
                path.write_text(raw, encoding="utf-8")
                self.assertEqual(load_report(path).report_type, "camera_timed_capture")

        payload = synthetic.capture_task_report()
        payload["padding"] = ""
        base = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        payload["padding"] = "x" * (MAX_FILE_BYTES + 1 - len(base.encode("utf-8")))
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(len(raw.encode("utf-8")), MAX_FILE_BYTES + 1)
        path = self.tmp / "size-over.json"
        path.write_text(raw, encoding="utf-8")
        with self.assertRaises(ReportError) as ctx:
            load_report(path)
        self.assertEqual(ctx.exception.code, "too_large")

    def test_array_element_boundaries(self) -> None:
        for count in (MAX_ARRAY_ELEMENTS - 1, MAX_ARRAY_ELEMENTS):
            with self.subTest(count=count):
                payload = synthetic.capture_task_report()
                payload["big"] = [0] * count
                self.assertEqual(self._load_payload(f"array-{count}.json", payload),
                                 "camera_timed_capture")
        payload = synthetic.capture_task_report()
        payload["big"] = [0] * (MAX_ARRAY_ELEMENTS + 1)
        path = self.tmp / "array-over.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ReportError) as ctx:
            load_report(path)
        self.assertEqual(ctx.exception.code, "too_many_elements")

    def test_depth_boundaries(self) -> None:
        """MAX_DEPTH 是根为 0 时的最深结构层级：32 允许，33 拒绝。"""

        def chain(depth: int) -> dict:
            node: dict = {}
            cursor = node
            for _ in range(depth - 1):
                cursor["next"] = {}
                cursor = cursor["next"]
            return node

        payload = synthetic.capture_task_report()
        payload["deep"] = chain(MAX_DEPTH)
        self.assertEqual(self._load_payload("depth-ok.json", payload), "camera_timed_capture")

        payload = synthetic.capture_task_report()
        payload["deep"] = chain(MAX_DEPTH + 1)
        path = self.tmp / "depth-over.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ReportError) as ctx:
            load_report(path)
        self.assertEqual(ctx.exception.code, "too_deep")

    def test_rejected_file_does_not_change_loaded_investigation(self) -> None:
        session = Session()
        primary = start(session, synthetic.capture_review_report(**MISSING_IMAGE), "p.json")
        session.add_note("保留的说明")
        before_additions = list(session.additions)
        before_id = session.investigation_id

        bad = self.tmp / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(ReportError):
            load_report(bad)

        payload = synthetic.capture_task_report()
        payload["big"] = [0] * (MAX_ARRAY_ELEMENTS + 1)
        over = self.tmp / "over.json"
        over.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ReportError):
            load_report(over)

        self.assertIs(session.primary, primary)
        self.assertEqual(session.additions, before_additions)
        self.assertEqual(session.investigation_id, before_id)
        self.assertEqual([note.text for note in session.notes], ["保留的说明"])


class SequentialSaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        session = Session()
        start(session, synthetic.capture_review_report(**MISSING_IMAGE), "p.json")
        session.add_note("第一条说明")
        self.session = session

    def test_two_saves_to_new_targets_keep_both(self) -> None:
        first = save_markdown(self.session, self.tmp / "first.md")
        first_text = first.read_text(encoding="utf-8")
        self.session.add_note("第二条说明")
        second = save_markdown(self.session, self.tmp / "second.md")
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_text(encoding="utf-8"), first_text)
        self.assertNotIn("第二条说明", first_text)
        self.assertIn("第二条说明", second.read_text(encoding="utf-8"))
        self.assertTrue(self.session.has_unsaved_content())

    def test_write_failure_then_new_target_succeeds(self) -> None:
        failed_target = self.tmp / "failed.md"
        with mock.patch("pathlib.Path.open", side_effect=PermissionError("拒绝访问")):
            with self.assertRaises(ExportError) as ctx:
                save_markdown(self.session, failed_target)
        self.assertEqual(ctx.exception.code, "write_failed")
        self.assertFalse(failed_target.exists())
        self.assertTrue(self.session.has_unsaved_content())

        ok_target = self.tmp / "ok.md"
        saved = save_markdown(self.session, ok_target)
        self.assertTrue(saved.exists())
        self.assertIn("第一条说明", saved.read_text(encoding="utf-8"))
        # 成功保存本身不改未保存标记；由界面在成功后调用 mark_saved。
        self.assertTrue(self.session.has_unsaved_content())


if __name__ == "__main__":
    unittest.main()
