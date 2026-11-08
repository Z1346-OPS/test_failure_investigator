"""真实 Tk 回归。单独执行，需要图形会话，不加入无图形的单测发现。"""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import synthetic
from tests.test_issue_lifecycle import missing, review
from investigator.issue_card import format_issue_card
from investigator.issue_panel import IssueDetailFrame
from investigator import ui
from investigator.guides import current_card


def widgets(parent):
    yield parent
    for child in parent.winfo_children():
        yield from widgets(child)


def button(app, label):
    for widget in widgets(app):
        if widget.winfo_class() == "TButton" and widget.cget("text") == label:
            return widget
    raise AssertionError(f"缺少按钮：{label}")


class CloseoutGuiRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="closeout-gui-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = ui.InvestigatorApp()
        self.addCleanup(self.app.destroy)
        self.errors = []
        self.app.report_callback_exception = lambda kind, value, tb: self.errors.append(
            (kind.__name__, str(value)))
        self.load(synthetic.capture_review_report(), "main.json")
        self.app.update()

    def load(self, data, name, addition=False):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        self.app._load(str(path), as_addition=addition)
        self.app.update()
        return path

    def draft(self, text="SYNTHETIC-DRAFT"):
        self.app._show_note()
        self.app.note_text.insert("1.0", text)

    def test_feedback_and_refresh_preserve_unrecorded_draft(self):
        self.draft()
        label = current_card(self.app.session).feedback_choices[0][1]
        button(self.app, label).invoke()
        self.app.update()
        self.assertEqual(self.app._note_text_value(), "SYNTHETIC-DRAFT")
        self.assertEqual(self.app.session.notes, [])
        self.app._render()
        self.app.update()
        self.assertEqual(self.app._note_text_value(), "SYNTHETIC-DRAFT")
        self.assertEqual(self.errors, [])

    def test_issue_selection_history_copy_and_fallback(self):
        self.load(review((), issues=[missing(1), missing(2)]), "two.json")
        self.load(review((1,)), "one-closed.json", addition=True)
        panel = next(w for w in self.app.body.winfo_children() if isinstance(w, IssueDetailFrame))
        self.assertEqual(panel.tree.get_children(), ("P02", "P01"))
        self.assertEqual(panel.selected, "P02")
        panel.tree.selection_set("P01")
        self.app.update()
        self.assertEqual(panel.selected, "P01")
        panel.tree.selection_set("P02")
        self.app.update()
        self.assertEqual(panel.selected, "P02")
        with mock.patch.object(panel, "clipboard_clear"), mock.patch.object(panel, "clipboard_append") as copied:
            button(panel, "复制交接摘要").invoke()
            expected = self.app.session.get_issue_details(self.app.session.investigation_id, "P02")
            copied.assert_called_once_with(format_issue_card(expected).summary)
        label = f"展开状态历史（{len(expected['history'])}）"
        source = expected["evidence"]["补充记录 1"]
        source_label = f"one-closed.json | 报告 SHA-256 前 16 位 {source['source_sha256'][:16]}"
        def sources():
            return [w for w in widgets(panel) if w.winfo_class() == "TLabel" and w.cget("text") == source_label]
        self.assertEqual(sources(), [])
        button(panel, label).invoke()
        self.app.update()
        self.assertTrue(sources()[0].winfo_ismapped())
        button(panel, label.replace("展开", "收起")).invoke()
        self.app.update()
        self.assertFalse(sources()[0].winfo_ismapped())
        button(panel, label).invoke()
        self.assertEqual(len(sources()), 1)
        with mock.patch.object(self.app.session, "get_issue_details", return_value=None):
            self.app._render()
            self.assertFalse(any(isinstance(w, IssueDetailFrame) for w in self.app.body.winfo_children()))
        self.load(synthetic.label_baseline_report(), "qr.json")
        self.assertFalse(any(isinstance(w, IssueDetailFrame) for w in self.app.body.winfo_children()))
        self.assertEqual(self.errors, [])

    def test_help_round_trip_preserves_report_draft(self):
        self.draft()
        self.app._set_view("no_report")
        self.app._go_home()
        self.assertEqual(self.app._note_text_value(), "SYNTHETIC-DRAFT")

    def test_recording_note_clears_input_without_reintroducing_old_draft(self):
        self.draft()
        button(self.app, "记录说明").invoke()
        self.app.update()
        self.assertEqual(len(self.app.session.notes), 1)
        self.assertEqual(self.app._note_text_value(), "")
        self.app._render()
        self.assertEqual(self.app._note_text_value(), "")

    def test_recording_handoff_clears_input(self):
        self.app._set_view("no_report")
        self.app.handoff_text.insert("1.0", "SYNTHETIC-HANDOFF")
        button(self.app, "记录找不到 / 不确定").invoke()
        self.app.update()
        self.assertEqual(self.app._handoff_text_value(), "")
        self.assertEqual(len(self.app.session.notes), 1)

    def test_bad_nested_input_has_notice_and_preserves_session_and_draft(self):
        self.draft()
        before = self.app.session.primary
        payload = synthetic.label_baseline_report()
        payload["attempts"] = [None]
        path = self.root / "bad.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.app._ask_report_or_addition = lambda: "new"
        self.app._confirm_new_investigation = lambda: True
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=str(path)):
            button(self.app, "开始另一件问题").invoke()
        self.app.update()
        self.assertEqual(self.errors, [])
        self.assertIs(self.app.session.primary, before)
        self.assertTrue(self.app._notice)
        self.assertEqual(self.app._note_text_value(), "SYNTHETIC-DRAFT")

    def test_unexpected_explanation_error_does_not_mutate_session(self):
        self.draft()
        before = self.app.session.primary
        path = self.root / "valid.json"
        path.write_text(json.dumps(synthetic.label_baseline_report()), encoding="utf-8")
        with mock.patch.object(ui, "explain_report", side_effect=RuntimeError("synthetic")):
            try:
                self.app._load(str(path), as_addition=False)
            except RuntimeError:
                self.fail("解释异常逃逸出导入保护")
        self.assertIs(self.app.session.primary, before)
        self.assertTrue(self.app._notice)
        self.assertEqual(self.app._note_text_value(), "SYNTHETIC-DRAFT")

    def test_new_investigation_clears_old_draft_and_notes(self):
        self.draft()
        self.app.session.add_note("旧调查的记录")
        self.load(synthetic.label_baseline_report(), "new.json")
        self.assertEqual(self.app.session.notes, [])
        self.assertEqual(self.app._note_draft, "")
        self.app._show_note()
        self.assertEqual(self.app._note_text_value(), "")

    def test_supplement_own_error_and_context_evidence_are_visible(self):
        self.load(synthetic.capture_task_report(), "capture.json")
        self.load(synthetic.capture_task_report(
            run_id="different", status="failed", stop_reason="read_failed",
            primary_error={"stage": "read", "type": "SYNTHETIC_ReadError"}),
            "later.json", addition=True)
        text = " ".join(str(w.cget("text")) for w in widgets(self.app.body)
                        if w.winfo_class() in ("TLabel", "Label"))
        self.assertIn("SYNTHETIC_ReadError", text)
        self.app._toggle_technical()
        text = " ".join(str(w.cget("text")) for w in widgets(self.app.body)
                        if w.winfo_class() in ("TLabel", "Label"))
        self.assertIn("补充记录 1/E01", text)


if __name__ == "__main__":
    unittest.main()
