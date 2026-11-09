"""从已有报告回答关闭判断、证据位置和待补检查。"""

import argparse
import sys
from pathlib import Path

from investigator.answers import QUESTIONS, answer_question
from investigator.explain import explain_report
from investigator.model_api import ModelConfig, ModelError, explain_with_model
from investigator.model_catalog import ModelCatalog, has_env_config
from investigator.reports import ReportError, load_report
from investigator.session import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("reports", type=Path, nargs="+", help="主报告在前，补充报告依次追加")
    parser.add_argument("--issue", help="采集复核的问题编号，如 P01")
    parser.add_argument("--question", default=QUESTIONS[0], help="询问关闭判断、证据位置或待补检查，可包含问题编号")
    parser.add_argument("--model-note", action="store_true", help="向已配置的服务发送本次规则回答并生成附加说明")
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
        answer = answer_question(session, args.question, args.issue)
        print(answer)
        if args.model_note:
            try:
                config = ModelConfig.from_env()
                if not has_env_config():
                    catalog = ModelCatalog()
                    catalog.load()
                    config = catalog.connection(config)
                note = explain_with_model(config, answer)
            except ModelError as exc:
                print(f"模型说明未生成：{exc} 已保留规则回答。", file=sys.stderr)
                return 1
            print("\n模型补充说明（供参考）\n" + note)
    except ReportError as exc:
        parser.error(f"{path.name} [{exc.code}] {exc.message}")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
