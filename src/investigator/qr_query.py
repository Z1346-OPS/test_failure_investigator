"""QR 区域证据和主报告复验判断，供命令与桌面问答共用。"""

from .explain import explain_report, qr_region_finding
from .reports import LoadedReport, label_validation_warnings
from .session import RECHECK_PASSED, Session, registered_problem_labels


def query_qr_region(report: LoadedReport, kind: str) -> dict:
    if report.report_type != "label_baseline":
        raise ValueError("请选择 label_baseline v2 的二维码报告")
    if kind not in {"full_image", "roi"}:
        raise ValueError("区域只能是 full_image 或 roi")

    summaries = report.data["decode_summaries"]
    matches = [i for i, item in enumerate(summaries) if item["region"]["kind"] == kind]
    evidence = ["decode_summaries"]
    result = {
        "schema_version": 1, "source_name": report.source_name, "report_sha256": report.source_sha256,
        "region": {"kind": kind}, "status": "unverified", "evidence_paths": evidence,
        "missing_evidence": [],
    }
    if not matches:
        result.update(status="not_checked", judgment="报告没有记录所选区域。",
                      missing_evidence=["需要一份覆盖所选区域的分析报告。"])
        return result
    if len(matches) > 1:
        result.update(judgment="报告记录了多个同类型区域，无法唯一定位。",
                      missing_evidence=["需按区域坐标明确目标记录。"])
        evidence[:] = [f"decode_summaries[{i}].region" for i in matches]
        return result

    index = matches[0]
    item = summaries[index]
    region = item["region"]
    prefix = f"decode_summaries[{index}]"
    truth = report.get("known_truth", "status")
    state = item["decode"]["status"]
    check = item["truth_check"]["status"]
    result.update(decode_status=state, truth_status=truth, truth_check_status=check)
    evidence[:] = ["known_truth.status", f"{prefix}.region", f"{prefix}.decode.status",
                   f"{prefix}.truth_check.status"]
    if report.get("source", "sha256") is not None:
        evidence.append("source.sha256")
    if report.get("known_truth", "sha256") is not None:
        evidence.append("known_truth.sha256")
    if "comparison" in item["truth_check"]:
        evidence.append(f"{prefix}.truth_check.comparison")
    for key in ("x", "y", "width", "height"):
        if type(region.get(key)) is int:
            result["region"][key] = region[key]

    gaps = result["missing_evidence"]
    if truth != "provided":
        gaps.append("需要核实独立答案的来源并提供相应的比对记录。")
    if state != "decoded":
        gaps.append("需要在所选区域取得可用于比对的单一有效读码。")
    warnings = label_validation_warnings(report.data, region_index=index)
    if report.get("status") not in {"completed", "completed_with_errors"}:
        warnings.append("报告的执行状态不支持确认本次核验结果。")
    if truth == "provided" and check in {"correct", "incorrect"}:
        if "symbols" in item["decode"]:
            evidence.append(f"{prefix}.decode.symbols")
    if warnings:
        gaps.extend(warnings)
        result["judgment"] = "所选区域的内容尚未核实，需核对待补检查。"
    else:
        result["judgment"] = qr_region_finding(item, truth) + "。"
        if truth == "provided" and state == "decoded" and check in {"correct", "incorrect"}:
            result["status"] = check
        elif truth == "not_provided":
            result["judgment"] += "该报告当时未提供独立答案，内容正确性尚未验证。"
        elif truth != "provided":
            result["judgment"] += "该报告的独立答案状态未知，内容正确性尚未验证。"
    return result


def original_issue_status(primary: LoadedReport, addition) -> str:
    if not registered_problem_labels(primary):
        return "no_registered_issue"
    if addition.recheck_result == RECHECK_PASSED:
        return "closed_in_scope"
    return "unresolved"


def compare_qr_reports(primary: LoadedReport, followup: LoadedReport, kind: str) -> dict:
    primary_region = query_qr_region(primary, kind)
    followup_region = query_qr_region(followup, kind)
    session = Session()
    session.load_primary(primary, explain_report(primary))
    addition = session.add_addition(followup, explain_report(followup))
    closure = original_issue_status(primary, addition)
    return {
        "schema_version": 1,
        "primary_region": primary_region,
        "followup_region": followup_region,
        "report_comparison": {
            "comparable": addition.comparable, "comparison_reason": addition.comparison_reason,
            "is_repeat": addition.is_repeat, "recheck_result": addition.recheck_result,
            "recheck_reason": addition.recheck_reason, "original_issue_status": closure,
            "primary_evidence_paths": comparison_paths(primary),
            "followup_evidence_paths": comparison_paths(followup),
        },
    }


def comparison_paths(report: LoadedReport) -> list[str]:
    paths = ["status", "analysis_id", "decode_summaries", "known_truth.status"]
    if "analyzed_at" in report.data:
        paths.append("analyzed_at")
    for group in ("source", "known_truth"):
        if report.get(group, "sha256") is not None:
            paths.append(f"{group}.sha256")
    for index, item in enumerate(report.data["decode_summaries"]):
        prefix = f"decode_summaries[{index}]"
        paths.extend([f"{prefix}.region", f"{prefix}.decode.status", f"{prefix}.truth_check.status"])
        if "comparison" in item["truth_check"]:
            paths.append(f"{prefix}.truth_check.comparison")
        if "symbols" in item["decode"]:
            paths.append(f"{prefix}.decode.symbols")
    return paths
