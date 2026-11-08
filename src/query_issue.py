"""列出调查中的采集复核问题，或按编号查询单个问题。"""

import argparse
import json
from pathlib import Path

from investigator.explain import explain_report
from investigator.reports import ReportError, load_report
from investigator.session import Session


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        usage="%(prog)s (--list | 问题编号) 主报告 [补充报告 ...]",
        allow_abbrev=False,
    )
    parser.add_argument("--list", action="store_true", help="列出采集复核问题，未解决优先")
    parser.add_argument("inputs", nargs="+", metavar="参数", help="按用法给出问题编号及有序报告，或用 --list 只给报告")
    args = parser.parse_args()
    if args.list:
        paths = args.inputs
    else:
        issue_id, *paths = args.inputs
        if not paths:
            parser.error("按编号查询需要主报告；列出问题请用 --list 主报告")

    session = Session()
    for filename in paths:
        path = Path(filename)
        try:
            report = load_report(path)
        except ReportError as exc:
            parser.error(f"{path.name} [{exc.code}] {exc.message}")
        if session.primary is None:
            session.load_primary(report, explain_report(report))
        else:
            session.add_addition(report, explain_report(report))

    if args.list:
        result = {
            "schema_version": 1,
            "investigation_id": session.investigation_id,
            "primary_report_type": session.primary.report_type,
            "issues": [
                {"issue_id": p.ident, "label": p.label, "frame_count": p.frame, "status": p.status}
                for p in session.review_problems_by_priority()
            ],
        }
    else:
        try:
            result = session.get_issue_details(session.investigation_id, issue_id)
        except KeyError:
            available = "、".join(p.ident for p in session.review_problems()) or "无"
            parser.error(f"未找到采集复核问题 {issue_id}。本次调查的问题编号：{available}")
        except ValueError as exc:
            parser.error(f"无效参数：{exc}")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
