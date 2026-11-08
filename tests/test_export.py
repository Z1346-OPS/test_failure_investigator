"""导出测试：内容边界、重名保护与保存失败。"""

from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import synthetic  # noqa: F401

from investigator.explain import explain_report
from investigator.guides import current_card
from investigator.export import (
    NOT_ATTACHED_NOTICE,
    ExportError,
    render_markdown,
    save_markdown,
    scrub,
    short_conclusion,
)
from investigator.reports import LoadedReport
from investigator.session import Session

SYNTHETIC_PAYLOAD_B64 = base64.b64encode(
    synthetic.SYNTHETIC_PAYLOAD.encode("utf-8")).decode("ascii")


def load(payload: dict, name: str = "synthetic.json") -> LoadedReport:
    return LoadedReport(
        source_name=name,
        source_sha256="a" * 64 if name == "synthetic.json" else (name[0] * 64),
        size_bytes=1,
        report_type=payload["report_type"],
        schema_version=payload["schema_version"],
        data=payload,
    )


def build_session() -> Session:
    session = Session()
    primary = load(synthetic.label_baseline_report(
        regions=(("full_image", "decoded", "not_provided"),
                 ("roi", "decode_error", "decode_error", {"x": 1, "y": 1, "width": 10, "height": 10})),
        status="completed_with_errors"))
    session.load_primary(primary, explain_report(primary))
    session.add_note("我重新拍了一张，看起来正常了")
    other = load(synthetic.capture_review_report(run_id="other" + "0" * 27), "other.json")
    session.add_addition(other, explain_report(other))
    return session


class RenderTests(unittest.TestCase):
    def test_required_sections_present(self) -> None:
        text = render_markdown(build_session())
        for heading in ("## 简明结论", "## 下一步", "## 这份报告还不能说明什么", "## 用户反馈",
                        "## 前后结果与比较限制", "## 技术详情", "## 未附原始文件"):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)

    def test_states_no_original_files_attached(self) -> None:
        text = render_markdown(build_session())
        self.assertIn("未附原始报告、原图、二维码载荷或整段日志", text)
        self.assertIn("不是完整原始证据包", text)
        self.assertIn(NOT_ATTACHED_NOTICE, text)

    def test_no_absolute_path_leaks(self) -> None:
        session = build_session()
        text = render_markdown(session)
        self.assertNotIn("D:\\synthetic", text)
        self.assertNotIn("not-a-real-image.png", text)
        self.assertNotIn("<本机路径已省略>", text)  # 本就没有需要替换的内容

    def test_no_qr_payload_leaks(self) -> None:
        text = render_markdown(build_session())
        self.assertNotIn(synthetic.SYNTHETIC_PAYLOAD, text)
        self.assertNotIn(SYNTHETIC_PAYLOAD_B64, text)

    def test_user_feedback_marked_as_unverified(self) -> None:
        text = render_markdown(build_session())
        self.assertIn("未由本程序独立验证", text)
        self.assertIn("不能当作复验通过", text)

    def test_short_conclusion_reflects_new_problems(self) -> None:
        session = Session()
        primary = load(synthetic.capture_review_report(), "normal.json")
        session.load_primary(primary, explain_report(primary))
        added = load(synthetic.capture_review_report(
            verification_status="inconsistent",
            issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "缺少留证图片"}],
            counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
            frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": synthetic.review_metrics()}]),
            "broken.json")
        session.add_addition(added, explain_report(added))
        conclusion = short_conclusion(session)
        self.assertIn("未通过", conclusion)
        self.assertIn("新出现", conclusion)
        self.assertIn("无法核实", conclusion)

    def test_open_failure_summary_scopes_followup_success_to_its_request(self):
        primary = load(synthetic.capture_task_report(
            camera_index=42, status="failed", stop_reason="open_failed", samples=0), "primary.json")
        for status, samples, warnings, successful in (
            ("completed", 2, [], True), ("completed", 0, [], False),
            ("failed", 0, [], False), ("completed", 2, ["计数矛盾"], False),
        ):
            with self.subTest(status=status, samples=samples, warnings=warnings):
                session = Session()
                session.load_primary(primary, explain_report(primary))
                self.assertNotIn("本次采集成功", short_conclusion(session))
                report = load(synthetic.capture_task_report(
                    run_id="b" * 32, camera_index=3, status=status, samples=samples,
                    stop_reason="duration_reached" if status == "completed" else "open_failed"),
                    "followup.json")
                report.warnings.extend(warnings)
                session.add_addition(report, explain_report(report))
                for repeated in (False, True):
                    if repeated:
                        session.add_addition(primary, explain_report(primary))
                    home = short_conclusion(session)
                    self.assertEqual("本次采集成功" in home, successful)
                    if successful:
                        self.assertIn("编号 3 本次采集成功；编号 42 的原问题仍待可比复验，根因未知", home)
                    self.assertIn("不可比较", home)

    def test_qr_homepage_distinguishes_original_and_latest_truth(self) -> None:
        primary = load(synthetic.label_baseline_report(), "primary.json")
        for state, wording in (("correct", "逐字节一致"), ("incorrect", "逐字节不一致")):
            with self.subTest(state=state):
                session = Session()
                session.load_primary(primary, explain_report(primary))
                self.assertIn("尚未验证内容是否正确", short_conclusion(session))
                report = load(synthetic.label_baseline_report(
                    regions=(("full_image", "decoded", state),), truth_status="provided"
                ), "addition.json")
                session.add_addition(report, explain_report(report))
                for repeat in (False, True):
                    if repeat:
                        session.add_addition(primary, explain_report(primary))
                    home = render_markdown(session).split("## 简明结论\n\n", 1)[1].split("\n## 下一步", 1)[0]
                    self.assertIn("主报告当时整图读出了一个二维码，但未提供独立答案", home)
                    self.assertIn("补充报告中，本次整图读出的内容与所给答案" + wording, home)
                    self.assertNotIn("仍未确认：没有独立答案", home)
                    self.assertEqual("重复导入" in home, repeat)
                    gaps = session.remaining_dimension()
                    self.assertTrue(any(line.startswith("主报告当时：没有独立答案") for line in gaps))
                    self.assertFalse(any(line.startswith("没有独立答案") for line in gaps))
                    self.assertIn("补充记录 1 内容核验：整图读出的内容与所给答案" + wording + "。", gaps)

    def test_qr_homepage_does_not_claim_a_match_without_valid_evidence(self) -> None:
        primary = load(synthetic.label_baseline_report(), "primary.json")
        for decode, check, truth in (("decoded", "not_provided", "not_provided"),
                                     ("ambiguous", "decode_error", "provided"),
                                     ("ambiguous", "correct", "provided")):
            with self.subTest(decode=decode, check=check):
                session = Session()
                session.load_primary(primary, explain_report(primary))
                report = load(synthetic.label_baseline_report(
                    regions=(("full_image", decode, check),), truth_status=truth
                ), "addition.json")
                session.add_addition(report, explain_report(report))
                self.assertNotIn("逐字节一致", short_conclusion(session))

    def test_qr_passed_guidance_reflects_whether_a_problem_was_registered(self) -> None:
        for first_truth, expected, absent in (
            ("not_provided", "两份记录均未登记问题", "登记的问题不再出现"),
            ("incorrect", "登记的问题不再出现", "两份记录均未登记问题"),
        ):
            with self.subTest(first_truth=first_truth):
                session = Session()
                primary = load(synthetic.label_baseline_report(
                    regions=(("full_image", "decoded", first_truth),),
                    truth_status="provided" if first_truth == "incorrect" else "not_provided",
                ), "primary.json")
                session.load_primary(primary, explain_report(primary))
                addition = load(synthetic.label_baseline_report(
                    regions=(("full_image", "decoded", "correct"),), truth_status="provided",
                ), "addition.json")
                result = session.add_addition(addition, explain_report(addition))
                self.assertEqual(result.recheck_result, "范围内通过")
                card = current_card(session)
                self.assertIn(expected, card.title)
                session.record_suggestion(card)
                text = render_markdown(session)
                for heading in ("简明结论", "下一步", "建议过什么"):
                    section = text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
                    self.assertIn(expected, section)
                self.assertNotIn(absent, text)
                if first_truth == "not_provided":
                    self.assertNotIn("旧的失败记录", text)

    def test_qr_homepage_keeps_full_image_and_roi_results_separate(self) -> None:
        session = Session()
        roi = {"x": 1, "y": 2, "width": 10, "height": 12}
        for name, truth, checks in (("primary.json", "not_provided", ("not_provided", "not_provided")),
                                    ("addition.json", "provided", ("correct", "incorrect"))):
            report = load(synthetic.label_baseline_report(regions=(
                ("full_image", "decoded", checks[0]), ("roi", "decoded", checks[1], roi)),
                truth_status=truth), name)
            if session.primary is None:
                session.load_primary(report, explain_report(report))
            else:
                session.add_addition(report, explain_report(report))
        home = short_conclusion(session)
        self.assertIn("本次整图读出的内容与所给答案逐字节一致", home)
        self.assertIn("ROI（x=1, y=2, 宽=10, 高=12）读出的内容与所给答案逐字节不一致", home)

    def test_comparison_limits_included(self) -> None:
        text = render_markdown(build_session())
        self.assertIn("比较限制", text)
        self.assertIn("不可比较", text)

    def test_scrub_replaces_absolute_paths(self) -> None:
        self.assertEqual(scrub(r"见 D:\a\b\c.png 结束"), "见 <本机路径已省略> 结束")
        self.assertEqual(scrub(r"\\server\share\x"), "<本机路径已省略>")


class SaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_save_creates_new_file(self) -> None:
        session = build_session()
        target = self.tmp / "note.md"
        saved = save_markdown(session, target)
        self.assertTrue(saved.exists())
        self.assertIn("## 简明结论", saved.read_text(encoding="utf-8"))

    def test_md_extension_added(self) -> None:
        session = build_session()
        saved = save_markdown(session, self.tmp / "note")
        self.assertEqual(saved.suffix, ".md")
        self.assertTrue(saved.exists())

    def test_existing_file_is_not_overwritten(self) -> None:
        session = build_session()
        target = self.tmp / "note.md"
        target.write_text("原有内容", encoding="utf-8")
        with self.assertRaises(ExportError) as ctx:
            save_markdown(session, target)
        self.assertEqual(ctx.exception.code, "exists")
        self.assertEqual(target.read_text(encoding="utf-8"), "原有内容")

    def test_write_failure_raises_and_does_not_claim_success(self) -> None:
        session = build_session()
        target = self.tmp / "note.md"
        with mock.patch("pathlib.Path.open", side_effect=PermissionError("拒绝访问")):
            with self.assertRaises(ExportError) as ctx:
                save_markdown(session, target)
        self.assertEqual(ctx.exception.code, "write_failed")
        self.assertFalse(target.exists())

    def test_session_content_survives_failed_save(self) -> None:
        session = build_session()
        before = render_markdown(session)
        target = self.tmp / "note.md"
        target.write_text("占用", encoding="utf-8")
        with self.assertRaises(ExportError):
            save_markdown(session, target)
        self.assertEqual(render_markdown(session), before)
        self.assertTrue(session.has_unsaved_content())

    def test_saved_file_reuses_previewed_payload(self) -> None:
        """预览与保存共用同一份生成结果，保存时不再重新渲染。"""
        session = build_session()
        previewed = render_markdown(session)
        session.add_note("预览之后新增、但不应进入本次文件的内容")
        target = self.tmp / "preview.md"
        save_markdown(session, target, payload=previewed)
        self.assertEqual(target.read_text(encoding="utf-8"), previewed)

    def test_mark_saved_clears_flag_only_after_success(self) -> None:
        session = build_session()
        save_markdown(session, self.tmp / "ok.md")
        self.assertTrue(session.has_unsaved_content())  # 保存动作本身不改状态
        session.mark_saved()
        self.assertFalse(session.has_unsaved_content())


if __name__ == "__main__":
    unittest.main()
