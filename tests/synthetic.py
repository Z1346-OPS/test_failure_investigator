"""最小合成报告：结构对齐摄像头项目，但内容全部自造。

不复制实拍图片、真实 QR 载荷或私人报告。载荷统一使用明显的合成字符串。
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import uuid4
from pathlib import Path

SYNTHETIC_PAYLOAD = "SYNTHETIC-PAYLOAD-ALPHA"
SYNTHETIC_IMAGE_SHA = "a1" * 32
OTHER_IMAGE_SHA = "b2" * 32


def _hex(seed: str) -> str:
    return (seed * 32)[:32]


def _payload_b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------- 采集任务

def capture_task_report(*, run_id="run1" + "0" * 28, status="completed",
                        stop_reason="duration_reached", camera_index=0,
                        samples=2, primary_error=None, actual_backend="DSHOW"):
    sample_records = [
        {
            "frame_count": index + 1,
            "slot_index": index,
            "scheduled_elapsed_seconds": index * 5,
            "read_elapsed_seconds": index * 5.0,
            "width": 8,
            "height": 6,
            "quality_status": "written",
            "color_status": "written",
            "image_status": "written",
            "image_file": f"camera_frame_{_hex(run_id)}_{index + 1}.png",
            "image_sha256": "c" * 64,
        }
        for index in range(samples)
    ]
    return {
        "schema_version": 1,
        "report_type": "camera_timed_capture",
        "run_id": _hex(run_id),
        "status": status,
        "stop_reason": stop_reason,
        "config": {"camera_index": camera_index, "duration_seconds": 30, "interval_seconds": 5},
        "camera": {
            "requested_backend": "CAP_DSHOW",
            "actual_backend": actual_backend,
            "first_frame_size": [8, 6] if samples else None,
        },
        "timings": {
            "started_at_utc": "2026-10-17T00:00:00.000+00:00" if samples else None,
            "ended_at_utc": "2026-10-17T00:00:30.000+00:00" if samples else None,
            "capture_elapsed_seconds": 30.0 if samples else None,
        },
        "counts": {
            "planned_sample_slots": 6,
            "read_attempts": samples * 10,
            "valid_frames": samples * 10,
            "sample_attempts": samples,
            "samples_completed": samples,
        },
        "metric_config": {"dark_threshold": 30, "bright_threshold": 225},
        "samples": sample_records,
        "primary_error": primary_error,
        "cleanup_errors": [],
        "provenance": {
            "implementation_version": "timed-capture-1",
            "runtime": {"python": "3.12.10", "opencv": "5.0.0", "numpy": "2.5.3"},
            "source_sha256": {"capture_task.py": "d" * 64},
        },
    }


# ---------------------------------------------------------------- 采集复核

# 夹具中的独立复核按构造次序执行，时间可重复且不依赖系统时钟精度。
_REVIEW_SEQUENCE = count()


def review_metrics(*, different=False):
    """合成的、契约完整的五项保存值/重算值；不是实测数据。"""
    metrics = {name: ["100.0", "100.0"] for name in
               ("brightness", "dark_ratio", "bright_ratio", "sharpness", "contrast")}
    if different:
        metrics["brightness"] = ["101.0", "100.0"]
    return metrics


def capture_review_report(*, run_id="run1" + "0" * 28, task_status="completed",
                          verification_status="consistent", issues=(),
                          counts=None, frames=None):
    if counts is None and verification_status != "not_reviewed":
        counts = {"reported_samples": 2, "csv_pairs": 2, "verified_frames": 2}
    if frames is None:
        frames = [
            {"frame_count": index + 1, "image_sha256_match": True, "metrics": review_metrics()}
            for index in range(counts["verified_frames"] if counts else 0)
        ]
    return {
        "schema_version": 1,
        "report_type": "capture_task_review",
        "review_id": uuid4().hex,
        "reviewed_at_utc": (datetime(2026, 10, 17, tzinfo=UTC)
                            + timedelta(seconds=next(_REVIEW_SEQUENCE))).isoformat(),
        "run_id": _hex(run_id),
        "task_status": task_status,
        "verification_status": verification_status,
        "comparison_basis": "current_algorithm_one_decimal",
        "counts": counts,
        "frames": frames,
        "issues": [dict(issue) for issue in issues],
        "warnings": [],
    }


# ---------------------------------------------------------------- QR 分析

def _summary(index, kind, decode_status, truth_status, roi=None):
    region = {"kind": kind, "x": 0, "y": 0, "width": 640, "height": 480}
    if roi:
        region = {"kind": "roi", **roi}
    symbols = []
    if decode_status == "decoded":
        symbols = [{
            "valid": True,
            "format": "QRCode",
            "text": SYNTHETIC_PAYLOAD,
            "payload_base64": _payload_b64(SYNTHETIC_PAYLOAD),
            "position_region": [[0, 0], [1, 0], [1, 1], [0, 1]],
            "position_analysis_image": [[0, 0], [1, 0], [1, 1], [0, 1]],
            "error": None,
        }]
    return {
        "region": region,
        "attempt_indices": [index],
        "decode": {
            "status": decode_status,
            "symbols": symbols,
            "selected_attempt_index": index if decode_status == "decoded" else None,
            "failed_attempt_indices": [] if decode_status not in {"decode_error", "execution_error"} else [index],
        },
        "truth_check": {"status": truth_status, "comparison": "exact_payload_bytes"},
    }


def label_baseline_report(*, analysis_id="analysis1", regions=(("full_image", "decoded", "not_provided"),),
                          status="completed", image_sha=SYNTHETIC_IMAGE_SHA,
                          truth_status="not_provided", truth_source=None):
    summaries = [
        _summary(index, kind, decode_status, truth_check, roi=roi)
        for index, (kind, decode_status, truth_check, roi) in enumerate(
            [(r[0], r[1], r[2], r[3] if len(r) > 3 else None) for r in regions]
        )
    ]
    attempts = []
    for index, summary in enumerate(summaries):
        attempts.append({
            "region": summary["region"],
            "profile": "baseline",
            "metrics": {"brightness": 100.0, "sharpness": 10.0, "contrast": 30.0},
            "decode": summary["decode"],
            "truth_check": summary["truth_check"],
        })
    known_truth = {"status": truth_status}
    if truth_status == "provided":
        known_truth.update({
            "source_description": truth_source or "合成答案来源",
            "sha256": "e" * 64,
            "text": SYNTHETIC_PAYLOAD,
            "encoding": "utf-8",
            "verification": "user_asserted_independent",
        })
    return {
        "schema_version": 2,
        "report_type": "label_baseline",
        "analysis_id": _hex(analysis_id),
        "status": status,
        "analyzed_at": "2026-10-17T00:00:00+00:00",
        "analysis_duration_seconds": 0.5,
        "provenance": {"implementation_version": "local-label-analysis-2", "source_sha256": {}},
        "warnings": [],
        "source": {
            "path": "D:\\synthetic\\not-a-real-image.png",
            "format": "PNG",
            "bytes": 1234,
            "sha256": image_sha,
            "width": 640,
            "height": 480,
            "mode": "RGB",
        },
        "preprocessing": {"exif_orientation": 1, "region": "full_image"},
        "analysis_config": {"decoder": {"formats": ["QRCode"]}},
        "config_sha256": "f" * 64,
        "known_truth": known_truth,
        "attempts": attempts,
        "decode_summaries": summaries,
    }


# ---------------------------------------------------------------- 落盘

def write_report(path, data, *, as_txt=False) -> Path:
    target = Path(path)
    if as_txt:
        target = target.with_suffix(".txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def write_sample_set(directory) -> dict[str, Path]:
    """写出一组合成报告，供图形界面冒烟使用。"""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "qr_single_read": write_report(
            root / "qr-single-read.json",
            label_baseline_report(),
        ),
        "qr_full_ok_roi_error": write_report(
            root / "qr-full-ok-roi-error.json",
            label_baseline_report(regions=(
                ("full_image", "decoded", "not_provided"),
                ("roi", "decode_error", "decode_error", {"x": 10, "y": 10, "width": 100, "height": 100}),
            ), status="completed_with_errors"),
        ),
        "qr_same_image_later": write_report(
            root / "qr-same-image-later.json",
            label_baseline_report(regions=(
                ("full_image", "decoded", "not_provided"),
                ("roi", "decoded", "not_provided", {"x": 10, "y": 10, "width": 100, "height": 100}),
            )),
        ),
        "review_consistent": write_report(
            root / "review-consistent.json",
            capture_review_report(),
        ),
        "review_missing_image": write_report(
            root / "review-missing-image.json",
            capture_review_report(
                verification_status="inconsistent",
                issues=[{"code": "frame_unverifiable", "frame_count": 2, "detail": "缺少留证图片"}],
                counts={"reported_samples": 2, "csv_pairs": 2, "verified_frames": 1},
                frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": review_metrics()}],
            ),
        ),
        "review_metric_mismatch": write_report(
            root / "review-metric-mismatch.json",
            capture_review_report(
                verification_status="inconsistent",
                issues=[{"code": "metric_mismatch", "frame_count": 1,
                         "detail": "亮度 101.0 与重算 100.0 不同"}],
                counts={"reported_samples": 1, "csv_pairs": 1, "verified_frames": 0},
                frames=[{"frame_count": 1, "image_sha256_match": True, "metrics": review_metrics(different=True)}],
            ),
        ),
        "review_not_reviewed": write_report(
            root / "review-not-reviewed.json",
            capture_review_report(verification_status="not_reviewed", task_status="failed",
                                  counts=None, frames=[]),
        ),
        "task_open_failed": write_report(
            root / "task-open-failed.json",
            capture_task_report(status="failed", stop_reason="open_failed",
                                samples=0, camera_index=9999, actual_backend=None,
                                primary_error={"stage": "open", "type": "CaptureTaskError",
                                               "message": "无法打开摄像头"}),
        ),
        "task_completed": write_report(
            root / "task-completed.txt",
            capture_task_report(), as_txt=True,
        ),
    }
    return files
