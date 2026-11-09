"""按区域查询单份 QR 报告中的内容判断、证据位置和待补检查。"""

import argparse
import json
from pathlib import Path

from investigator.explain import qr_region_finding
from investigator.reports import LoadedReport, ReportError, label_validation_warnings, load_report


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
    if kind == "roi" and any(type(region.get(k)) is not int or region[k] < minimum
                             for k, minimum in (("x", 0), ("y", 0), ("width", 1), ("height", 1))):
        warnings.append("选区坐标或尺寸无效，需核实所选区域。")
    elif kind == "roi":
        for offset, size, bound in (("x", "width", "analysis_width"), ("y", "height", "analysis_height")):
            limit = report.get("preprocessing", bound)
            if type(limit) is int and region[offset] + region[size] > limit:
                warnings.append("选区超出分析图像的范围，需核对选区坐标。")
                break
    if report.get("status") not in {"completed", "completed_with_errors"}:
        warnings.append("报告的执行状态不支持确认本次核验结果。")
    if truth == "provided" and check in {"correct", "incorrect"}:
        if "symbols" in item["decode"]:
            evidence.append(f"{prefix}.decode.symbols")
        symbols = item["decode"].get("symbols")
        if not (isinstance(symbols, list) and len(symbols) == 1 and isinstance(symbols[0], dict)
                and symbols[0].get("valid") is True):
            warnings.append("缺少唯一有效候选码的记录。")
    if warnings:
        gaps.extend(warnings)
        result["judgment"] = "所选区域的内容尚未核实，需核对待补检查。"
    else:
        result["judgment"] = qr_region_finding(item, truth) + "。"
        if truth == "provided" and state == "decoded" and check in {"correct", "incorrect"}:
            result["status"] = check
        elif truth != "provided":
            result["judgment"] += "本次内容正确性尚未验证。"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("report", type=Path, help="一次 QR 分析的 JSON 报告")
    parser.add_argument("--region", choices=("full_image", "roi"), required=True)
    args = parser.parse_args()
    try:
        result = query_qr_region(load_report(args.report), args.region)
    except ReportError as exc:
        parser.error(f"{args.report.name} [{exc.code}] {exc.message}")
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
