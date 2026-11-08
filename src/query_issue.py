"""在有序的采集复核报告中查询单个问题，输出 Session 的 JSON 快照。"""

import argparse
import json
from pathlib import Path

from investigator.explain import explain_report
from investigator.reports import ReportError, load_report
from investigator.session import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue_id", help="当前调查中的问题编号，例如 P01")
    parser.add_argument("primary", type=Path, help="主报告 JSON")
    parser.add_argument("followups", type=Path, nargs="*", help="按交接顺序追加的报告 JSON")
    args = parser.parse_args()
    session = Session()
    for path in (args.primary, *args.followups):
        try:
            report = load_report(path)
        except ReportError as exc:
            parser.error(f"{path.name} [{exc.code}] {exc.message}")
        if session.primary is None:
            session.load_primary(report, explain_report(report))
        else:
            session.add_addition(report, explain_report(report))
    try:
        details = session.get_issue_details(session.investigation_id, args.issue_id)
    except KeyError:
        available = "、".join(p.ident for p in session.review_problems()) or "无"
        parser.error(f"未找到采集复核问题 {args.issue_id}。本次调查的问题编号：{available}")
    except ValueError as exc:
        parser.error(f"无效参数：{exc}")
    print(json.dumps(details, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
