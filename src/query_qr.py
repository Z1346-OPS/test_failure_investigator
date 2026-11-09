"""查询 QR 报告中的区域证据，可与指定主报告核对复验结果。"""

import argparse
import json
from pathlib import Path

from investigator.qr_query import compare_qr_reports, query_qr_region
from investigator.reports import ReportError, load_report


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("report", type=Path, help="一次 QR 分析的 JSON 报告")
    parser.add_argument("--region", choices=("full_image", "roi"), required=True)
    parser.add_argument("--primary", type=Path, help="与本次报告比较的原始 QR 报告")
    args = parser.parse_args()
    path = args.report
    try:
        followup = load_report(path)
        if args.primary is None:
            result = query_qr_region(followup, args.region)
        else:
            path = args.primary
            result = compare_qr_reports(load_report(path), followup, args.region)
    except ReportError as exc:
        parser.error(f"{path.name} [{exc.code}] {exc.message}")
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
