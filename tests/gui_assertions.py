"""图形界面文案断言辅助：区分句子、控件边界与否定对象。

只使用有限的确定性规则，不引入 NLP 依赖：
  * 每个控件文本单独判断（控件边界即断言边界）；
  * 按句子/分句分隔符切开，否定只作用于它所在的分句；
  * 肯定式短语出现在没有否定的分句里才算“肯定式宣称”。

这可以避免两种错误：
  * “不能证明内容正确。”被误报为宣称；
  * “不代表相机合格。内容正确。”因为前一句有否定而整体豁免。
"""

from __future__ import annotations

# 句子与分句分隔符：否定词只在同一分句内、且在短语之前才算作用到短语。
CLAUSE_SEPARATORS = "。！？!?\n；;，,：:"

NEGATIONS = (
    "不能证明", "不代表", "不要宣称", "不等于", "无法证明", "不能说明",
    "不能当作", "无法确认", "不能视为", "不能认为", "不是",
)


def unnegated_claims(texts, phrases, negations=NEGATIONS) -> list[str]:
    """找出未被否定的肯定式短语。

    ``texts`` 可以是单个字符串或控件文本列表；列表按控件逐个判断，
    前一个控件里的否定不会豁免后一个控件里的肯定结论。
    """
    if isinstance(texts, str):
        texts = [texts]
    hits: list[str] = []
    for text in texts:
        for phrase in phrases:
            start = 0
            while True:
                index = text.find(phrase, start)
                if index < 0:
                    break
                boundary = max(text.rfind(sep, 0, index) for sep in CLAUSE_SEPARATORS)
                clause_prefix = text[boundary + 1:index]
                if not any(negative in clause_prefix for negative in negations):
                    hits.append(text[boundary + 1:index + len(phrase)])
                start = index + len(phrase)
    return hits
