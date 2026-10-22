"""导出测试：内容边界、重名保护与保存失败。"""

from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import synthetic  # noqa: F401

from investigator.explain import explain_report
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
