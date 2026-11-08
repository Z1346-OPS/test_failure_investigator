"""报告读取与校验的边界测试。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import synthetic  # noqa: F401  (导入 tests 包即把 src/ 加入 sys.path)

from investigator.reports import (
    MAX_ARRAY_ELEMENTS,
    MAX_FILE_BYTES,
    ReportError,
    load_report,
)


class ReportLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, name: str, payload, *, raw: str | None = None) -> Path:
        path = self.tmp / name
        if raw is not None:
            path.write_text(raw, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    # ------------------------------------------------ 三类有效报告

    def test_three_supported_types_load(self) -> None:
        cases = {
            "capture_task.json": synthetic.capture_task_report(),
            "capture_review.json": synthetic.capture_review_report(),
            "label_baseline.json": synthetic.label_baseline_report(),
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                report = load_report(self.write(name, payload))
                self.assertEqual(report.report_type, payload["report_type"])
                self.assertEqual(report.schema_version, payload["schema_version"])
                self.assertEqual(len(report.source_sha256), 64)

    def test_txt_extension_is_accepted(self) -> None:
        path = self.tmp / "report.txt"
        path.write_text(json.dumps(synthetic.capture_task_report()), encoding="utf-8")
        self.assertEqual(load_report(path).report_type, "camera_timed_capture")

    def test_source_name_has_no_directory(self) -> None:
        report = load_report(self.write("nested.json", synthetic.capture_task_report()))
        self.assertEqual(report.source_name, "nested.json")
        self.assertNotIn(os.sep, report.source_name)

    # ------------------------------------------------ 拒绝情形

    def test_unknown_report_type_rejected(self) -> None:
        payload = synthetic.capture_task_report()
        payload["report_type"] = "something_else"
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("unknown.json", payload))
        self.assertEqual(ctx.exception.code, "unknown_report_type")

    def test_unsupported_schema_version_rejected(self) -> None:
        payload = synthetic.capture_task_report()
        payload["schema_version"] = 2
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("v2.json", payload))
        self.assertEqual(ctx.exception.code, "unsupported_schema_version")

    def test_label_baseline_v1_rejected(self) -> None:
        payload = synthetic.label_baseline_report()
        payload["schema_version"] = 1
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("lb1.json", payload))
        self.assertEqual(ctx.exception.code, "unsupported_schema_version")

    def test_missing_report_type_rejected(self) -> None:
        payload = synthetic.capture_task_report()
        del payload["report_type"]
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("notype.json", payload))
        self.assertEqual(ctx.exception.code, "missing_required_field")

    def test_missing_required_field_rejected(self) -> None:
        payload = synthetic.capture_task_report()
        del payload["counts"]["valid_frames"]
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("missing.json", payload))
        self.assertEqual(ctx.exception.code, "missing_required_field")

    def test_review_missing_counts_key_rejected(self) -> None:
        payload = synthetic.capture_review_report()
        del payload["counts"]["verified_frames"]
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("review.json", payload))
        self.assertEqual(ctx.exception.code, "missing_required_field")

    def test_broken_json_rejected(self) -> None:
        path = self.write("broken.json", None, raw='{"report_type": "camera_timed_capture", ')
        with self.assertRaises(ReportError) as ctx:
            load_report(path)
        self.assertEqual(ctx.exception.code, "invalid_json")

    def test_duplicate_key_rejected(self) -> None:
        raw = '{"report_type": "camera_timed_capture", "schema_version": 1, "schema_version": 1}'
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("dup.json", None, raw=raw))
        self.assertEqual(ctx.exception.code, "duplicate_key")

    def test_non_finite_constant_rejected(self) -> None:
        raw = '{"report_type": "camera_timed_capture", "schema_version": 1, "x": NaN}'
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("nan.json", None, raw=raw))
        self.assertEqual(ctx.exception.code, "non_finite_constant")

    def test_top_level_array_rejected(self) -> None:
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("array.json", [1, 2, 3]))
        self.assertEqual(ctx.exception.code, "not_an_object")

    def test_unsupported_suffix_rejected(self) -> None:
        path = self.tmp / "report.csv"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(ReportError) as ctx:
            load_report(path)
        self.assertEqual(ctx.exception.code, "unsupported_suffix")

    def test_directory_rejected(self) -> None:
        folder = self.tmp / "adir.json"
        folder.mkdir()
        with self.assertRaises(ReportError) as ctx:
            load_report(folder)
        self.assertEqual(ctx.exception.code, "not_a_file")

    def test_missing_file_rejected(self) -> None:
        with self.assertRaises(ReportError) as ctx:
            load_report(self.tmp / "nope.json")
        self.assertEqual(ctx.exception.code, "not_found")

    def test_oversize_file_rejected(self) -> None:
        path = self.tmp / "big.json"
        path.write_bytes(b"{" + b" " * (MAX_FILE_BYTES + 1) + b"}")
        with self.assertRaises(ReportError) as ctx:
            load_report(path)
        self.assertEqual(ctx.exception.code, "too_large")

    def test_too_deep_rejected(self) -> None:
        node: dict = {}
        cursor = node
        for _ in range(40):
            cursor["next"] = {}
            cursor = cursor["next"]
        payload = synthetic.capture_task_report()
        payload["deep"] = node
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("deep.json", payload))
        self.assertEqual(ctx.exception.code, "too_deep")

    def test_too_many_elements_rejected(self) -> None:
        payload = synthetic.capture_task_report()
        payload["big"] = list(range(MAX_ARRAY_ELEMENTS + 1))
        with self.assertRaises(ReportError) as ctx:
            load_report(self.write("wide.json", payload))
        self.assertEqual(ctx.exception.code, "too_many_elements")

    def test_unc_path_rejected(self) -> None:
        with self.assertRaises(ReportError) as ctx:
            load_report(Path(r"\\server\share\report.json"))
        self.assertIn(ctx.exception.code, {"network_path", "not_found"})

    def test_report_replaced_between_check_and_open_is_rejected(self) -> None:
        path = self.write("selected.json", synthetic.capture_task_report())
        replacement = self.write("other.json", synthetic.label_baseline_report())
        original_open = Path.open

        def replace_before_open(selected, *args, **kwargs):
            if selected == path:
                os.replace(replacement, selected)
            return original_open(selected, *args, **kwargs)

        with patch.object(Path, "open", replace_before_open):
            with self.assertRaises(ReportError) as ctx:
                load_report(path)
        self.assertEqual(ctx.exception.code, "changed_during_read")

    def test_report_under_linked_ancestor_is_rejected(self) -> None:
        target = self.tmp / "target"
        nested = target / "nested"
        nested.mkdir(parents=True)
        report_path = nested / "report.json"
        report_path.write_text(json.dumps(synthetic.capture_task_report()), encoding="utf-8")
        alias = self.tmp / "alias"
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(alias))
        else:
            alias.symlink_to(target, target_is_directory=True)
        self.assertEqual(load_report(report_path).report_type, "camera_timed_capture")
        for name in ("report.json", "missing.json"):
            with self.subTest(name=name):
                with self.assertRaises(ReportError) as ctx:
                    load_report(alias / "nested" / name)
                self.assertEqual(ctx.exception.code, "link_not_allowed")

    def test_symlink_rejected(self) -> None:
        target = self.write("target.json", synthetic.capture_task_report())
        link = self.tmp / "link.json"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"本机不允许创建符号链接：{error}")
        with self.assertRaises(ReportError) as ctx:
            load_report(link)
        self.assertEqual(ctx.exception.code, "link_not_allowed")

    # ------------------------------------------------ 部分失败隔离

    def test_failed_file_does_not_break_other_results(self) -> None:
        good = load_report(self.write("good.json", synthetic.capture_task_report()))
        with self.assertRaises(ReportError):
            load_report(self.write("bad.json", None, raw="{oops"))
        self.assertEqual(good.report_type, "camera_timed_capture")
        self.assertEqual(good.data["status"], "completed")

    # ------------------------------------------------ 不静默补默认值

    def test_count_mismatch_is_reported_not_silently_fixed(self) -> None:
        payload = synthetic.capture_task_report(samples=2)
        payload["counts"]["sample_attempts"] = 5  # 与 samples 数组长度不符
        report = load_report(self.write("mismatch.json", payload))
        self.assertTrue(any("sample_attempts" in w for w in report.warnings))
        # 不改写原始数据
        self.assertEqual(report.data["counts"]["sample_attempts"], 5)

    def test_not_reviewed_counts_null_is_preserved(self) -> None:
        payload = synthetic.capture_review_report(verification_status="not_reviewed",
                                                  counts=None, frames=[])
        report = load_report(self.write("nr.json", payload))
        self.assertIsNone(report.data["counts"])


if __name__ == "__main__":
    unittest.main()
