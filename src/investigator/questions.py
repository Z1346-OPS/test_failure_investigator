"""识别支持的中文交接问法。整个问题须在支持范围内。"""

import re
import unicodedata


QUESTIONS = ("原问题能关吗？", "依据在哪里？", "还缺什么检查？")
_HELP = "请问能否关闭、依据在哪里或还缺什么检查，例如“还要补查什么？”"
_ISSUE = re.compile(r"(?<![a-z0-9_])p[0-9]+(?![a-z0-9_])")
_SUBJECT = r"(?:原问题|这个问题|该问题|这个异常|原异常|问题)?"
_FORMS = (
    _SUBJECT + r"(?:现在|本次|目前)?(?:能不能|可不可以|是否可以|能否|能|可以|可)"
    r"(?:直接)?(?:关|关闭|关掉|结案)(?:了)?(?:吗)?|"
    + _SUBJECT + r"(?:解决了吗|关闭了吗|是否已解决|当前状态是什么|处理到哪一步了)",
    r"(?:判断)?(?:依据|证据)(?:在哪(?:里|儿)?|是什么|有哪些|来自哪里|在哪里|呢)|"
    r"(?:哪份|哪个)(?:报告|记录|字段)(?:能|可以)?(?:支持|证明)(?:这个|这一|当前)?(?:结论|判断)|"
    r"(?:从)?哪里(?:能|可以)?(?:看出|找到)(?:这个)?(?:判断|依据|证据)",
    r"(?:现在|目前)?(?:还)?(?:缺|差)(?:了)?(?:哪些|什么)(?:证据|材料|检查|复核)?|"
    r"(?:接下来|下一步|现在|还)?(?:还)?(?:要|需要|应该)?(?:补做|补查|补充|复核|检查)(?:哪些|什么)(?:证据|材料|检查|帧)?|"
    r"(?:下一步|接下来)(?:要)?(?:做什么|怎么查)",
)
_SEPARATOR = re.compile(r"[?？,，。;；!！、\n]+|以及|并且")


def parse_question(question: str, selected_issue: str | None, *, qr: bool) -> tuple[list[str], str | None]:
    text = unicodedata.normalize("NFKC", question).casefold().strip()
    mentioned = {m.upper() for m in _ISSUE.findall(text)}
    if len(mentioned) > 1:
        raise ValueError("请一次询问一个问题编号。")
    target = next(iter(mentioned), None)
    selected = selected_issue.strip().upper() if selected_issue else None
    if target and selected and target != selected:
        raise ValueError(f"问题中提到 {target}，当前选择的是 {selected}。请核对问题编号。")
    text = _ISSUE.sub("", text)
    intents = []
    for clause in _SEPARATOR.split(text):
        clause = "".join(clause.split()).strip(":")
        clause = re.sub(r"^(?:请问|请告诉我|我想知道)", "", clause)
        if not clause:
            continue
        if qr and re.fullmatch(r"(?:二维码)?(?:读出的)?内容(?:正确吗|对了吗|核实了吗)", clause):
            if QUESTIONS[1] not in intents:
                intents.append(QUESTIONS[1])
            continue
        for pattern, intent in zip(_FORMS, QUESTIONS, strict=True):
            if re.fullmatch(pattern, clause):
                if intent not in intents:
                    intents.append(intent)
                break
        else:
            raise ValueError(_HELP)
    if not intents:
        raise ValueError(_HELP)
    return intents, target or selected
