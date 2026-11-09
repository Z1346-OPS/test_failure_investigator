"""从已有报告回答关闭判断、证据位置和待补检查。"""

import argparse
from pathlib import Path

from investigator.answers import QUESTIONS, answer_session
from investigator.explain import explain_report
from investigator.reports import ReportError, load_report
from investigator.session import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("reports", type=Path, nargs="+", help="主报告在前，补充报告依次追加")
    parser.add_argument("--issue", help="采集复核的问题编号，如 P01")
    parser.add_argument("--question", choices=QUESTIONS, default=QUESTIONS[0])
    args = parser.parse_args()
    session = Session()
    try:
        for path in args.reports:
            report = load_report(path)
            explanation = explain_report(report)
            if session.primary is None:
                session.load_primary(report, explanation)
            else:
                session.add_addition(report, explanation)
        print(answer_session(session, args.issue).text(args.question))
    except ReportError as exc:
        parser.error(f"{path.name} [{exc.code}] {exc.message}")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
