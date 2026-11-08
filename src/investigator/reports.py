"""只读加载并校验摄像头项目的已有报告。

约束（沿用 docs/workflow-design.md 第 4 节）：
  * 只读取用户明确选择的单个文件；不递归扫描目录。
  * 不跟随报告内出现的路径、链接或 ``result_file``。
  * 不执行输入中的任何命令，不加载 HTML/Markdown 资源。
  * 解析失败只影响该文件，不破坏其他已读取的有效结果。
  * 未知版本、损坏 JSON、重复键、缺必要字段、超限文件都要明确报告，
    不静默补默认值。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 限制

MAX_FILE_BYTES = 5 * 1024 * 1024          # 单文件 5 MiB
MAX_DEPTH = 32                            # 结构化深度
MAX_ARRAY_ELEMENTS = 10_000               # 单数组元素数
ALLOWED_SUFFIXES = frozenset({".json", ".txt"})

# report_type -> 支持的 schema_version 集合
SUPPORTED_TYPES: dict[str, frozenset[int]] = {
    "camera_timed_capture": frozenset({1}),
    "capture_task_review": frozenset({1}),
    "label_baseline": frozenset({2}),
}

TYPE_LABELS = {
    "camera_timed_capture": "定时采集任务",
    "capture_task_review": "采集复核",
    "label_baseline": "QR 分析",
}

KIND_BY_TYPE = {
    "camera_timed_capture": "capture_task",
    "capture_task_review": "capture_review",
    "label_baseline": "qr",
}


class ReportError(Exception):
    """读取或校验一份报告失败。``code`` 是稳定的机器可读标识。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LoadedReport:
    """一份通过校验的报告，保留来源标识与原始字段。"""

    source_name: str
    source_sha256: str
    size_bytes: int
    report_type: str
    schema_version: int
    data: dict
    warnings: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return KIND_BY_TYPE[self.report_type]

    @property
    def type_label(self) -> str:
        return TYPE_LABELS[self.report_type]

    def get(self, *path, default=None):
        """按路径安全取值；任何一层缺失或类型不符都返回 ``default``。"""
        node = self.data
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


# ---------------------------------------------------------------- JSON 解析

def _no_duplicate_keys(pairs):
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise ReportError("duplicate_key", f"JSON 中存在重复键：{key!r}")
        seen[key] = value
    return seen


def _reject_constant(value: str):
    raise ReportError("non_finite_constant", f"不允许非有限 JSON 常量：{value}")


def _check_limits(value, depth: int = 0) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ReportError("non_finite_number", "不允许非有限数值（包括浮点溢出）")
    if depth > MAX_DEPTH:
        raise ReportError("too_deep", f"结构化深度超过上限 {MAX_DEPTH}")
    if isinstance(value, dict):
        for item in value.values():
            _check_limits(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_ARRAY_ELEMENTS:
            raise ReportError(
                "too_many_elements", f"数组元素数 {len(value)} 超过上限 {MAX_ARRAY_ELEMENTS}"
            )
        for item in value:
            _check_limits(item, depth + 1)


# ---------------------------------------------------------------- 路径检查

def _check_path(path: Path) -> tuple[Path, os.stat_result]:
    """逐级检查用户选择的路径；resolve 会提前跟随目录联接。"""
    selected = path.absolute()
    if any(str(candidate).startswith(("\\\\", "//")) for candidate in (path, selected)):
        raise ReportError("network_path", "不支持网络位置（UNC 路径）")

    try:
        for component in (*reversed(selected.parents), selected):
            info = os.lstat(component)
            attributes = getattr(info, "st_file_attributes", 0)
            if stat.S_ISLNK(info.st_mode) or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ReportError("link_not_allowed", "报告路径中包含符号链接或重解析点（junction）")
    except FileNotFoundError as error:
        raise ReportError("not_found", f"文件不存在：{selected.name}") from error
    except OSError as error:
        raise ReportError("unreadable", f"无法访问文件：{error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise ReportError("not_a_file", "选择的不是普通文件")

    if selected.suffix.lower() not in ALLOWED_SUFFIXES:
        allowed = "、".join(sorted(ALLOWED_SUFFIXES))
        raise ReportError(
            "unsupported_suffix", f"只支持 {allowed} 文件，实际为 {selected.suffix or '（无扩展名）'}"
        )
    if info.st_size > MAX_FILE_BYTES:
        raise ReportError(
            "too_large",
            f"文件 {info.st_size} 字节超过上限 {MAX_FILE_BYTES} 字节",
        )
    return selected, info


# ---------------------------------------------------------------- 字段校验

def _require_mapping(node, where: str) -> dict:
    if not isinstance(node, dict):
        raise ReportError("field_type_error", f"{where} 必须是对象，实际为 {type(node).__name__}")
    return node


def _require_list(node, where: str) -> list:
    if not isinstance(node, list):
        raise ReportError("field_type_error", f"{where} 必须是数组，实际为 {type(node).__name__}")
    return node


def _require_str(node, key: str, where: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value:
        raise ReportError("missing_required_field", f"{where}.{key} 缺失或不是非空字符串")
    return value


def _require_int(node, key: str, where: str) -> int:
    value = node.get(key)
    if type(value) is not int:
        raise ReportError("missing_required_field", f"{where}.{key} 缺失或不是整数")
    return value


def _validate_capture_task(data: dict) -> list[str]:
    warnings: list[str] = []
    _require_str(data, "run_id", "根")
    _require_str(data, "status", "根")
    _require_str(data, "stop_reason", "根")
    config = _require_mapping(data.get("config"), "config")
    _require_int(config, "camera_index", "config")
    camera = _require_mapping(data.get("camera"), "camera")
    counts = _require_mapping(data.get("counts"), "counts")
    for key in ("planned_sample_slots", "read_attempts", "valid_frames",
                "sample_attempts", "samples_completed"):
        _require_int(counts, key, "counts")
    samples = _require_list(data.get("samples"), "samples")
    if "timings" in data:
        _require_mapping(data["timings"], "timings")
    if data.get("primary_error") is not None:
        _require_mapping(data["primary_error"], "primary_error")
    if counts["samples_completed"] > counts["sample_attempts"]:
        warnings.append("counts.samples_completed 大于 counts.sample_attempts，计数自相矛盾")
    if len(samples) != counts["sample_attempts"]:
        warnings.append(
            f"samples 数组有 {len(samples)} 项，与 counts.sample_attempts={counts['sample_attempts']} 不一致"
        )
    if not isinstance(data.get("cleanup_errors", []), list):
        raise ReportError("field_type_error", "cleanup_errors 必须是数组")
    if camera.get("actual_backend") is not None and not isinstance(camera["actual_backend"], str):
        raise ReportError("field_type_error", "camera.actual_backend 必须是非空字符串或 null")
    return warnings


# capture_task_review v1: compare_frame_metrics 返回五项 (CSV 字符串, 一位小数重算字符串)。
# 只判断报告里的事实，不读原图/CSV，不追随路径。所有调用者共用这一条规则。
REVIEW_METRICS = ("brightness", "dark_ratio", "bright_ratio", "sharpness", "contrast")


def review_frame_verified(frame) -> bool:
    if not isinstance(frame, dict):
        return False
    number = frame.get("frame_count")
    if type(number) is not int or number < 1 or frame.get("image_sha256_match") is not True:
        return False
    return _review_metrics_match(frame.get("metrics"))


def _review_metrics_match(metrics) -> bool:
    if not isinstance(metrics, dict) or not all(name in metrics for name in REVIEW_METRICS):
        return False
    for pair in metrics.values():
        if not isinstance(pair, list) or len(pair) != 2:
            return False
        if not all(isinstance(value, str) for value in pair) or pair[0] != pair[1]:
            return False
        try:
            if not all(math.isfinite(float(value)) for value in pair):
                return False
        except ValueError:
            return False
    return True


def review_validation_warnings(data: dict) -> list[str]:
    """保留结构可读的矛盾输入；提示与通过判定共用，不修正任何原始字段。"""
    warnings: list[str] = []
    frames = data.get("frames", [])
    if not isinstance(frames, list):
        return ["frames 不是数组，无法核实帧级事实"]
    counts = data.get("counts")
    verification = data.get("verification_status")
    if data.get("comparison_basis") != "current_algorithm_one_decimal":
        warnings.append("comparison_basis 缺失、为空或不在已核实的 v1 比较口径内，不能确认可比条件")
    numbers = [frame.get("frame_count") for frame in frames if isinstance(frame, dict)]
    valid_numbers = [number for number in numbers if type(number) is int and number > 0]
    if len(valid_numbers) != len(frames) or len(set(valid_numbers)) != len(valid_numbers):
        warnings.append("frames 帧号缺失、不是正整数或重复，覆盖范围不可靠")
    if "declared_frame_counts" in data:
        declared_frames = data["declared_frame_counts"]
        if (not isinstance(declared_frames, list) or not declared_frames
                or any(type(n) is not int or n < 1 for n in declared_frames)
                or len(set(declared_frames)) != len(declared_frames)
                or not set(valid_numbers).issubset(declared_frames)
                or (verification == "consistent" and set(valid_numbers) != set(declared_frames))):
            warnings.append("declared_frame_counts 与逐帧记录矛盾，原范围无法核实")
    verified = sum(review_frame_verified(frame) for frame in frames)
    if isinstance(counts, dict):
        declared = counts.get("verified_frames")
        if declared != verified:
            warnings.append(f"counts.verified_frames={declared} 与帧级事实实际核实 {verified} 帧自相矛盾")
        if any(type(counts.get(key)) is not int or counts[key] < 0
               for key in ("reported_samples", "csv_pairs", "verified_frames")):
            warnings.append("counts 含未知或负数，不能确认覆盖范围")
    by_number = {frame["frame_count"]: frame for frame in frames
                 if isinstance(frame, dict) and type(frame.get("frame_count")) is int}
    for issue in data.get("issues", []) or []:
        if not isinstance(issue, dict) or type(issue.get("frame_count")) is not int:
            continue
        frame = by_number.get(issue["frame_count"])
        if frame is None:
            continue
        code = issue.get("code")
        conflict = (
            code == "metric_mismatch" and _review_metrics_match(frame.get("metrics"))
            or code == "image_hash_mismatch" and frame.get("image_sha256_match") is True
            or code == "frame_unverifiable" and review_frame_verified(frame))
        if conflict:
            warnings.append(f"帧 {issue['frame_count']} 的问题码 {code} 与帧级核实事实自相矛盾")
    if verification == "consistent":
        if data.get("issues"):
            warnings.append("verification_status=consistent 与非空 issues 自相矛盾")
        if verified != len(frames):
            failed = [str(frame.get("frame_count", "未知")) if isinstance(frame, dict) else "未知"
                      for frame in frames if not review_frame_verified(frame)]
            warnings.append("verification_status=consistent 与帧 " + "、".join(failed)
                            + " 的摘要/指标核实事实自相矛盾")
        if isinstance(counts, dict) and not (
                counts.get("reported_samples") == counts.get("csv_pairs")
                == counts.get("verified_frames") == len(frames)):
            warnings.append("consistent 的样本数、CSV 配对、核实帧数与 frames 覆盖数量自相矛盾")
    if verification in {"consistent", "inconsistent"} and data.get("task_status") != "completed":
        warnings.append("复核结论与未完成/未知的 task_status 自相矛盾")
    if verification == "not_reviewed" and (counts is not None or frames):
        warnings.append("not_reviewed 却携带计数或帧级结果，记录自相矛盾")
    return warnings


def _validate_capture_review(data: dict) -> list[str]:
    warnings: list[str] = []
    _require_str(data, "run_id", "根")
    _require_str(data, "task_status", "根")
    verification = _require_str(data, "verification_status", "根")
    if verification not in {"consistent", "inconsistent", "not_reviewed"}:
        warnings.append(f"verification_status 取值为未预期的 {verification!r}")
    issues = _require_list(data.get("issues"), "issues")
    _require_list(data.get("warnings", []), "warnings")
    frames = _require_list(data.get("frames", []), "frames")
    counts = data.get("counts", None)
    if counts is None:
        # not_reviewed 的合法形态：counts 为 null，不能转换成 0。
        if verification != "not_reviewed":
            warnings.append("counts 为 null 但 verification_status 不是 not_reviewed")
    else:
        counts = _require_mapping(counts, "counts")
        for key in ("reported_samples", "csv_pairs", "verified_frames"):
            _require_int(counts, key, "counts")
    for index, issue in enumerate(issues):
        item = _require_mapping(issue, f"issues[{index}]")
        _require_str(item, "code", f"issues[{index}]")
    warnings.extend(review_validation_warnings(data))
    return warnings


def valid_review_id(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def valid_sha256(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def label_validation_warnings(data: dict) -> list[str]:
    """QR 身份与比对边界；只核对报告声明，不重新解码或比对载荷。"""
    warnings = []
    source = data.get("source")
    if not isinstance(source, dict) or not valid_sha256(source.get("sha256")):
        warnings.append("source.sha256 缺失或不是有效 SHA-256，图片身份未知，不能确认同图比较")
    truth = data.get("known_truth") or {}
    provided = isinstance(truth, dict) and truth.get("status") == "provided"
    if provided and not valid_sha256(truth.get("sha256")):
        warnings.append("known_truth.sha256 缺失或无效，跨报告复验无法确认使用同一答案")
    for index, summary in enumerate(data.get("decode_summaries") or []):
        check = summary.get("truth_check") or {}
        state = check.get("status")
        decode = summary.get("decode") or {}
        if provided and state not in {"correct", "incorrect"}:
            warnings.append(f"区域 {index + 1} 的独立答案比对尚未完成或状态未知（{state!r}）")
        if not provided and state in {"correct", "incorrect"}:
            warnings.append(f"区域 {index + 1} 声称完成答案比对，但独立答案未提供")
        if state in {"correct", "incorrect"}:
            if decode.get("status") != "decoded":
                warnings.append(f"区域 {index + 1} 的答案比对与未成功解码的状态矛盾")
            if check.get("comparison") != "exact_payload_bytes":
                warnings.append(f"区域 {index + 1} 未记录逐字节比对口径，不能确认内容核验结论")
    return warnings


def _validate_label_baseline(data: dict) -> list[str]:
    warnings: list[str] = []
    _require_str(data, "analysis_id", "根")
    _require_str(data, "status", "根")
    summaries = _require_list(data.get("decode_summaries"), "decode_summaries")
    if not summaries:
        warnings.append("decode_summaries 为空数组，没有可解释的区域结果")
    truth = _require_mapping(data.get("known_truth"), "known_truth")
    _require_str(truth, "status", "known_truth")
    if data.get("source") is not None:
        _require_mapping(data["source"], "source")
    attempts = _require_list(data.get("attempts", []), "attempts")
    for index, attempt in enumerate(attempts):
        item = _require_mapping(attempt, f"attempts[{index}]")
        if item.get("decode") is not None:
            decode = _require_mapping(item["decode"], f"attempts[{index}].decode")
            if decode.get("status") is not None:
                _require_str(decode, "status", f"attempts[{index}].decode")
    for index, summary in enumerate(summaries):
        where = f"decode_summaries[{index}]"
        item = _require_mapping(summary, where)
        region = _require_mapping(item.get("region"), f"{where}.region")
        _require_str(region, "kind", f"{where}.region")
        decode = _require_mapping(item.get("decode"), f"{where}.decode")
        _require_str(decode, "status", f"{where}.decode")
        check = _require_mapping(item.get("truth_check"), f"{where}.truth_check")
        _require_str(check, "status", f"{where}.truth_check")
    warnings.extend(label_validation_warnings(data))
    return warnings


_VALIDATORS = {
    "camera_timed_capture": _validate_capture_task,
    "capture_task_review": _validate_capture_review,
    "label_baseline": _validate_label_baseline,
}


# ---------------------------------------------------------------- 入口

def load_report(path) -> LoadedReport:
    """读取并校验一份报告；失败抛 :class:`ReportError`，不返回半成品。"""
    resolved, checked = _check_path(Path(path))
    try:
        with resolved.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not os.path.samestat(checked, opened):
                raise ReportError("changed_during_read", "打开的文件与已检查的文件不同，请重新选择")
            first = handle.read(MAX_FILE_BYTES + 1)
            handle.seek(0)
            raw = handle.read(MAX_FILE_BYTES + 1)
            _, current = _check_path(resolved)
            if not os.path.samestat(opened, current):
                raise ReportError("changed_during_read", "读取期间文件已被替换，请重新选择")
    except OSError as error:
        raise ReportError("unreadable", f"无法读取文件：{error}") from error

    if max(len(first), len(raw)) > MAX_FILE_BYTES:
        raise ReportError("too_large", f"读取内容超过上限 {MAX_FILE_BYTES} 字节")
    if first != raw:
        raise ReportError("changed_during_read", "读取过程中文件内容发生变化，请重新选择")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReportError("invalid_encoding", "文件不是 UTF-8 文本，无法作为 JSON 报告读取") from error

    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys,
                          parse_constant=_reject_constant)
    except ReportError:
        raise
    except RecursionError as error:
        raise ReportError("too_deep", f"结构化深度超过上限 {MAX_DEPTH}") from error
    except json.JSONDecodeError as error:
        raise ReportError(
            "invalid_json", f"JSON 解析失败（第 {error.lineno} 行第 {error.colno} 列）"
        ) from error
    except ValueError as error:
        raise ReportError("invalid_number", "JSON 数值无法安全解析") from error

    if not isinstance(data, dict):
        raise ReportError("not_an_object", "报告顶层必须是 JSON 对象")

    _check_limits(data)

    report_type = data.get("report_type")
    if not isinstance(report_type, str) or not report_type:
        raise ReportError("missing_required_field", "缺少 report_type，无法识别报告类型")
    if report_type not in SUPPORTED_TYPES:
        raise ReportError("unknown_report_type", f"不支持的 report_type：{report_type!r}")

    version = data.get("schema_version")
    if type(version) is not int:
        raise ReportError("missing_required_field", "缺少 schema_version 或不是整数")
    if version not in SUPPORTED_TYPES[report_type]:
        supported = "、".join(str(v) for v in sorted(SUPPORTED_TYPES[report_type]))
        raise ReportError(
            "unsupported_schema_version",
            f"{report_type} 不支持 schema_version={version}（支持：{supported}）",
        )

    warnings = _VALIDATORS[report_type](data)

    return LoadedReport(
        source_name=resolved.name,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        report_type=report_type,
        schema_version=version,
        data=data,
        warnings=warnings,
    )
